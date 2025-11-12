import re
import secrets
import uuid
from functools import partial
from urllib.parse import urljoin

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models, transaction
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from django_resized import ResizedImageField

from callico.base.fields import PolygonField
from callico.process.models import Process, ProcessMode
from callico.projects.utils import bounding_box, build_iiif_url


def simple_dict(value):
    if not isinstance(value, dict) or not all(isinstance(item, str) for item in value.values()):
        raise ValidationError(_("This field must be a dictionary containing simple key:value strings."))


def list_of_dict(value):
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValidationError(_("This field must be a list containing dictionaries."))


def generate_token():
    return secrets.token_urlsafe(16)


class Role(models.TextChoices):
    Contributor = "Contributor", _("Contributor")
    Moderator = "Moderator", _("Moderator")
    Manager = "Manager", _("Manager")


ADMIN_ROLES = [Role.Moderator, Role.Manager]


class Project(models.Model):
    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    name = models.CharField(unique=True, max_length=100, verbose_name=_("Name"))
    invite_token = models.SlugField(unique=True, max_length=50, default=generate_token, verbose_name=_("Invite token"))
    public = models.BooleanField(default=False, verbose_name=_("Public"))
    description = models.TextField(blank=True, default="", verbose_name=_("Description"))
    illustration = ResizedImageField(
        size=[600, 600], null=True, blank=True, upload_to="project_illustrations/", verbose_name=_("Illustration")
    )

    provider = models.ForeignKey(
        "projects.Provider",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="projects",
        verbose_name=_("Provider"),
    )
    provider_object_id = models.CharField(
        max_length=512, null=True, blank=True, verbose_name=_("Object identifier in provider")
    )
    provider_extra_information = models.JSONField(
        blank=True, default=dict, verbose_name=_("Extra information from the provider")
    )

    created = models.DateTimeField(auto_now_add=True, verbose_name=_("Created"))
    updated = models.DateTimeField(auto_now=True, verbose_name=_("Updated"))

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _("Project")
        verbose_name_plural = _("Projects")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(provider__isnull=True, provider_object_id__isnull=True)
                | models.Q(provider__isnull=False, provider_object_id__isnull=False),
                name="provider_fields_all_set_or_none_set",
            )
        ]

    @property
    def invite_link(self):
        return urljoin(
            settings.INSTANCE_URL,
            reverse(
                "project-join",
                kwargs={
                    "invite_token": self.invite_token,
                },
            ),
        )

    def clean(self):
        if self.provider and self.provider_object_id is None:
            raise ValidationError(
                {"provider": _("An identifier must be provided if you specify a provider and vice versa")}
            )

        if not self.provider and self.provider_object_id is not None:
            raise ValidationError(
                {"provider_object_id": _("A provider must be specified if you provide an identifier and vice versa")}
            )

        if self.provider and self.provider.type == ProviderType.Arkindex and self.provider_object_id:
            try:
                self.provider_object_id = uuid.UUID(self.provider_object_id)
            except ValueError:
                raise ValidationError(
                    {"provider_object_id": _("The identifier must be an UUID when an Arkindex provider is specified")}
                )

    def fetch_extra_info(self, creator):
        # Circular dependencies
        from callico.process.arkindex.tasks import arkindex_fetch_extra_info

        # We only want to fetch extra info if an Arkindex provider is associated to the project
        if not self.provider or self.provider.type != ProviderType.Arkindex:
            return

        fetch_process = Process.objects.create(
            name="Retrieval of extra information from Arkindex upon Project creation or update",
            mode=ProcessMode.ArkindexImport,
            configuration={
                "arkindex_provider": str(self.provider.id),
                "project_id": str(self.id),
            },
            project=self,
            creator=creator,
        )

        # To retrieve extra information and populate the database with it (classes, types, worker runs)
        # We use transaction.on_commit() to avoid a race condition preventing Celery from seeing the newly created Process
        transaction.on_commit(
            partial(
                arkindex_fetch_extra_info.apply_async, kwargs=fetch_process.configuration, task_id=str(fetch_process.id)
            )
        )


class Membership(models.Model):
    user = models.ForeignKey("users.User", on_delete=models.CASCADE, related_name="memberships", verbose_name=_("User"))
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="memberships", verbose_name=_("Project")
    )
    role = models.CharField(max_length=32, choices=Role, default=Role.Contributor, verbose_name=_("Role"))

    created = models.DateTimeField(auto_now_add=True, verbose_name=pgettext_lazy("feminine", "Created"))
    updated = models.DateTimeField(auto_now=True, verbose_name=pgettext_lazy("feminine", "Updated"))

    class Meta:
        verbose_name = _("Membership")
        verbose_name_plural = _("Memberships")
        unique_together = (("project", "user"),)


class ProviderType(models.TextChoices):
    Arkindex = "arkindex", _("Arkindex")
    IIIF = "iiif", _("IIIF")


class Provider(models.Model):
    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    name = models.CharField(unique=True, max_length=100, verbose_name=_("Name"))
    type = models.CharField(max_length=32, choices=ProviderType, default=ProviderType.Arkindex, verbose_name=_("Type"))
    api_url = models.URLField(unique=True, verbose_name=_("API URL"))
    api_token = models.CharField(max_length=100, verbose_name=_("API token"))
    extra_information = models.JSONField(blank=True, default=dict, verbose_name=_("Extra information"))

    class Meta:
        verbose_name = _("Provider")
        verbose_name_plural = _("Providers")

    def __str__(self):
        return self.name


class TextOrientation(models.TextChoices):
    LeftToRight = "left_to_right", _("Left to right")
    RightToLeft = "right_to_left", _("Right to left")


class Element(models.Model):
    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="elements", verbose_name=_("Project")
    )

    name = models.CharField(max_length=250, verbose_name=_("Name"))
    type = models.ForeignKey(
        "projects.Type",
        on_delete=models.RESTRICT,
        related_name="elements",
        verbose_name=_("Type"),
    )
    parent = models.ForeignKey(
        "projects.Element",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
        verbose_name=_("Parent"),
    )

    image = models.ForeignKey(
        "projects.Image",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="elements",
        verbose_name=_("Image"),
    )
    polygon = PolygonField(null=True, blank=True, verbose_name=_("Polygon"))
    order = models.PositiveIntegerField(verbose_name=_("Order"))
    text_orientation = models.TextField(
        max_length=32,
        choices=TextOrientation,
        default=TextOrientation.LeftToRight,
        verbose_name=_("Text orientation"),
    )

    provider = models.ForeignKey(
        "projects.Provider",
        on_delete=models.CASCADE,
        related_name="elements",
        verbose_name=_("Provider"),
    )
    provider_object_id = models.CharField(max_length=512, verbose_name=_("Object identifier in provider"))

    transcription = models.JSONField(
        validators=[simple_dict], blank=True, default=dict, verbose_name=_("Transcription")
    )
    metadata = models.JSONField(
        validators=[simple_dict], blank=True, default=dict, verbose_name=pgettext_lazy("plural", "Metadata")
    )
    entities = models.JSONField(validators=[list_of_dict], blank=True, default=list, verbose_name=_("Entities"))

    created = models.DateTimeField(auto_now_add=True, verbose_name=_("Created"))
    updated = models.DateTimeField(auto_now=True, verbose_name=_("Updated"))

    class Meta:
        verbose_name = _("Element")
        verbose_name_plural = _("Elements")
        unique_together = (("provider", "provider_object_id", "project"),)
        constraints = [
            # Add order unicity
            # Two constraints are required as Null values are not compared for unicity
            models.UniqueConstraint(
                fields=["order", "parent"],
                name="element_unique_order_in_parent",
                condition=models.Q(parent__isnull=False),
            ),
            models.UniqueConstraint(
                fields=["order", "project"],
                name="element_unique_order_in_project",
                condition=models.Q(parent__isnull=True),
            ),
        ]
        ordering = ("order",)

    def __str__(self):
        return f"{self.type.name} {self.name}"

    @property
    def provider_url(self):
        if self.provider.type != ProviderType.Arkindex:
            raise NotImplementedError(
                _("The provider type '%(type)s' isn't supported for now") % {"type": self.provider.type}
            )

        return f"{self.provider.api_url.rstrip('api/v1')}/element/{self.provider_object_id}"

    @property
    def small_thumbnail(self):
        return self.build_thumbnail(size_max_width=400)

    @property
    def medium_thumbnail(self):
        return self.build_thumbnail(size_max_width=800)

    def build_thumbnail(self, **kwargs):
        if not self.polygon:
            return build_iiif_url(self.image, **kwargs)

        x, y, width, height = bounding_box(self.polygon)
        return build_iiif_url(self.image, x=x, y=y, width=width, height=height, **kwargs)

    def all_children(self):
        query = """
        WITH RECURSIVE children AS (
            SELECT id
            FROM projects_element
            WHERE parent_id = %s

            UNION ALL

            SELECT elements.id
            FROM projects_element AS elements, children
            WHERE elements.parent_id = children.id
        )
        SELECT id
        FROM children;
        """
        return (
            Element.objects.filter(id__in=[element.id for element in Element.objects.raw(query, [self.id])])
            .select_related("image")
            .order_by("created", "order")
        )

    def all_ancestors(self):
        query = """
        WITH RECURSIVE ancestors AS (
            SELECT id, parent_id
            FROM projects_element
            WHERE id = %(id)s

            UNION ALL

            SELECT element.id, element.parent_id
            FROM projects_element AS element, ancestors
            WHERE element.id = ancestors.parent_id
        )
        SELECT id
        FROM ancestors
        WHERE id <> %(id)s;
        """
        return (
            Element.objects.filter(id__in=[element.id for element in Element.objects.raw(query, {"id": self.id})])
            .select_related("image")
            .order_by("created", "order")
        )

    def clean(self):
        if self.polygon and not self.image:
            raise ValidationError({"image": _("An element cannot have polygon without image")})

        if not self.parent:
            return

        if self.parent.id == self.id:
            raise ValidationError({"parent": _("An element cannot be its own parent")})

        if not self.project_id:
            return

        if self.parent.project != self.project:
            raise ValidationError(
                {"parent": _("Parent is not part of the project %(project)s") % {"project": self.project}}
            )

    def serialize_frontend(self):
        """
        Serialize the element in a specific format to be used by the Vue.JS library
        """
        return {
            "id": str(self.id),
            "name": str(self),
            "polygon": self.polygon,
            "image": self.serialize_image(),
        }

    def serialize_image(self):
        """
        Serialize the element image in a specific format to be used by the Vue.JS library
        """
        if not self.image:
            return

        return {
            "url": self.image.iiif_url,
            "width": self.image.width,
            "height": self.image.height,
        }


class Image(models.Model):
    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    iiif_url = models.URLField(unique=True, max_length=512, verbose_name=_("IIIF URL"))
    width = models.PositiveIntegerField(default=0, verbose_name=_("Width"))
    height = models.PositiveIntegerField(default=0, verbose_name=_("Height"))

    created = models.DateTimeField(auto_now_add=True, verbose_name=pgettext_lazy("feminine", "Created"))
    updated = models.DateTimeField(auto_now=True, verbose_name=pgettext_lazy("feminine", "Updated"))

    class Meta:
        verbose_name = _("Image")
        verbose_name_plural = _("Images")


class Class(models.Model):
    """
    Classification class of a project
    """

    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    name = models.CharField(max_length=250, verbose_name=_("Name"))
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="classes", verbose_name=_("Project")
    )

    provider = models.ForeignKey(
        "projects.Provider",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="classes",
        verbose_name=_("Provider"),
    )
    provider_object_id = models.CharField(
        max_length=512, null=True, blank=True, verbose_name=_("Object identifier in provider")
    )

    created = models.DateTimeField(auto_now_add=True, verbose_name=_("Created"))
    updated = models.DateTimeField(auto_now=True, verbose_name=_("Updated"))

    class Meta:
        verbose_name = _("Class")
        verbose_name_plural = _("Classes")
        unique_together = (("name", "project"), ("project", "provider", "provider_object_id"))
        constraints = [
            models.CheckConstraint(
                condition=models.Q(provider__isnull=True, provider_object_id__isnull=True)
                | models.Q(provider__isnull=False, provider_object_id__isnull=False),
                name="provider_fields_class_all_set_or_none_set",
            )
        ]

    def __str__(self):
        return self.name

    def clean(self):
        if self.provider and self.provider_object_id is None:
            raise ValidationError(
                {"provider": _("An identifier must be provided if you specify a provider and vice versa")}
            )

        if not self.provider and self.provider_object_id is not None:
            raise ValidationError(
                {"provider_object_id": _("A provider must be specified if you provide an identifier and vice versa")}
            )


class Type(models.Model):
    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    name = models.CharField(max_length=250, verbose_name=_("Name"))
    folder = models.BooleanField(default=False, verbose_name=_("Folder"))
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="types", verbose_name=_("Project")
    )
    color = models.CharField(
        max_length=6,
        default="28b62c",
        validators=[
            RegexValidator("^[0-9a-f]{6}$", flags=re.IGNORECASE, message=_("Color should be a hexadecimal color code"))
        ],
        verbose_name=_("Color"),
    )

    provider = models.ForeignKey(
        "projects.Provider",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="types",
        verbose_name=_("Provider"),
    )
    provider_object_id = models.CharField(
        max_length=512, null=True, blank=True, verbose_name=_("Object identifier in provider")
    )

    created = models.DateTimeField(auto_now_add=True, verbose_name=_("Created"))
    updated = models.DateTimeField(auto_now=True, verbose_name=_("Updated"))

    class Meta:
        verbose_name = _("Type")
        verbose_name_plural = _("Types")
        unique_together = (("name", "project"), ("project", "provider", "provider_object_id"))
        constraints = [
            models.CheckConstraint(
                condition=models.Q(provider__isnull=True, provider_object_id__isnull=True)
                | models.Q(provider__isnull=False, provider_object_id__isnull=False),
                name="provider_fields_type_all_set_or_none_set",
            )
        ]
        ordering = ("name",)

    def __str__(self):
        return self.name

    def clean(self):
        if self.provider and self.provider_object_id is None:
            raise ValidationError(
                {"provider": _("An identifier must be provided if you specify a provider and vice versa")}
            )

        if not self.provider and self.provider_object_id is not None:
            raise ValidationError(
                {"provider_object_id": _("A provider must be specified if you provide an identifier and vice versa")}
            )


class CampaignMode(models.TextChoices):
    Transcription = "transcription", _("Transcription")
    Classification = "classification", _("Classification")
    Entity = "entity", _("Entity")
    EntityForm = "entity form", _("Entity form")
    ElementGroup = "element_group", _("Element group")
    Elements = "elements", _("Elements")


class CampaignState(models.TextChoices):
    Created = "created", pgettext_lazy("feminine", "Created")
    Running = "running", _("Running")
    Closed = "closed", pgettext_lazy("feminine", "Closed")
    Archived = "archived", pgettext_lazy("feminine", "Archived")


CAMPAIGN_CLOSED_STATES = [CampaignState.Closed, CampaignState.Archived]
NO_IMAGE_SUPPORTED_CAMPAIGN_MODES = [
    CampaignMode.Transcription,
    CampaignMode.Classification,
    CampaignMode.Entity,
    CampaignMode.EntityForm,
    CampaignMode.ElementGroup,
]
CSV_SUPPORTED_CAMPAIGN_MODES = [
    CampaignMode.Transcription,
    CampaignMode.Classification,
    CampaignMode.Entity,
    CampaignMode.EntityForm,
    CampaignMode.ElementGroup,
    CampaignMode.Elements,
]
XLSX_SUPPORTED_CAMPAIGN_MODES = CSV_SUPPORTED_CAMPAIGN_MODES


class Campaign(models.Model):
    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    name = models.CharField(max_length=250, verbose_name=_("Name"))
    creator = models.ForeignKey(
        "users.User", on_delete=models.CASCADE, related_name="campaigns", verbose_name=_("Creator")
    )
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="campaigns", verbose_name=_("Project")
    )
    mode = models.CharField(max_length=32, choices=CampaignMode, verbose_name=_("Mode"))
    state = models.CharField(
        max_length=32, choices=CampaignState, default=CampaignState.Created, verbose_name=_("State")
    )
    description = models.TextField(blank=True, default="", verbose_name=_("Description"))
    nb_tasks_auto_assignment = models.PositiveIntegerField(
        default=50, verbose_name=_("Number of tasks to assign per volunteer")
    )
    max_user_tasks = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        verbose_name=_("Number of allowed assignments for available tasks"),
    )
    configuration = models.JSONField(blank=True, default=dict, verbose_name=_("Configuration"))
    csv_export = models.FileField(null=True, upload_to="csv_exports/")
    xlsx_export = models.FileField(null=True, upload_to="xlsx_exports/")

    created = models.DateTimeField(auto_now_add=True, verbose_name=pgettext_lazy("feminine", "Created"))
    updated = models.DateTimeField(auto_now=True, verbose_name=pgettext_lazy("feminine", "Updated"))

    class Meta:
        verbose_name = _("Campaign")
        verbose_name_plural = _("Campaigns")

    def __str__(self):
        return self.name

    @property
    def is_closed(self):
        return self.state in CAMPAIGN_CLOSED_STATES


class Authority(models.Model):
    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    name = models.CharField(unique=True, max_length=100, verbose_name=_("Name"))
    description = models.TextField(blank=True, default="", verbose_name=_("Description"))

    class Meta:
        verbose_name = _("Authority")
        verbose_name_plural = _("Authorities")

    def __str__(self):
        return self.name


class AuthorityValue(models.Model):
    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    authority = models.ForeignKey(
        "projects.Authority", on_delete=models.CASCADE, related_name="values", verbose_name=_("Authority")
    )
    authority_value_id = models.CharField(null=True, blank=True, verbose_name=_("Value identifier in authority"))
    value = models.TextField(verbose_name=_("Value"))
    metadata = models.JSONField(blank=True, default=dict, verbose_name=pgettext_lazy("plural", "Metadata"))

    class Meta:
        verbose_name = _("Authority value")
        verbose_name_plural = _("Authority values")

    def __str__(self):
        return self.value
