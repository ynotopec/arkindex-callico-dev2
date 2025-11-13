import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils.formats import localize
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy

from callico.projects.models import NO_IMAGE_SUPPORTED_CAMPAIGN_MODES, CampaignMode, Membership

USER_TASK_ANNOTATE_URL_NAMES = {
    CampaignMode.Transcription: "annotate-transcription",
    CampaignMode.Entity: "annotate-entity",
    CampaignMode.EntityForm: "annotate-entity-form",
    CampaignMode.Classification: "annotate-classification",
    CampaignMode.Elements: "annotate-elements",
    CampaignMode.ElementGroup: "annotate-element-group",
}

USER_TASK_MODERATE_URL_NAMES = {
    CampaignMode.Transcription: "moderate-transcription",
    CampaignMode.Entity: "moderate-entity",
    CampaignMode.EntityForm: "moderate-entity-form",
    CampaignMode.Classification: "moderate-classification",
    CampaignMode.Elements: "moderate-elements",
    CampaignMode.ElementGroup: "moderate-element-group",
}

USER_TASK_DETAILS_URL_NAMES = {
    CampaignMode.Transcription: "user-task-details-transcription",
    CampaignMode.Entity: "user-task-details-entity",
    CampaignMode.EntityForm: "user-task-details-entity-form",
    CampaignMode.Classification: "user-task-details-classification",
    CampaignMode.Elements: "user-task-details-elements",
    CampaignMode.ElementGroup: "user-task-details-element-group",
}


class Task(models.Model):
    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    element = models.ForeignKey(
        "projects.Element", on_delete=models.CASCADE, related_name="tasks", verbose_name=_("Element")
    )
    campaign = models.ForeignKey(
        "projects.Campaign", on_delete=models.CASCADE, related_name="tasks", verbose_name=_("Campaign")
    )

    created = models.DateTimeField(auto_now_add=True, verbose_name=pgettext_lazy("feminine", "Created"))
    updated = models.DateTimeField(auto_now=True, verbose_name=pgettext_lazy("feminine", "Updated"))

    class Meta:
        verbose_name = _("Task")
        verbose_name_plural = _("Tasks")
        unique_together = (("element", "campaign"),)

    @property
    def annotate_url(self):
        annotate_url_name = USER_TASK_ANNOTATE_URL_NAMES.get(self.campaign.mode)
        if annotate_url_name:
            return reverse(annotate_url_name, kwargs={"pk": self.id})

    def clean(self):
        if not self.element_id:
            return

        if not self.campaign_id:
            return

        if self.campaign.mode not in NO_IMAGE_SUPPORTED_CAMPAIGN_MODES and not self.element.image:
            raise ValidationError(
                {
                    "element": _(
                        "You cannot create a task for an element that does not have an image on this type of campaign"
                    )
                }
            )

        if self.element.project != self.campaign.project:
            raise ValidationError(
                {
                    "__all__": _(
                        "Element is part of project %(element_project)s while campaign is for project %(campaign_project)s"
                    )
                    % {"element_project": self.element.project, "campaign_project": self.campaign.project}
                }
            )


class TaskState(models.TextChoices):
    Draft = "draft", _("Draft")
    Pending = "pending", _("Pending")
    Annotated = "annotated", pgettext_lazy("feminine", "Annotated")
    Validated = "validated", pgettext_lazy("feminine", "Validated")
    Rejected = "rejected", pgettext_lazy("feminine", "Rejected")
    Skipped = "skipped", pgettext_lazy("feminine", "Skipped")


USER_TASK_COMPLETED_STATES = [TaskState.Annotated, TaskState.Validated, TaskState.Rejected, TaskState.Skipped]


class TaskUser(models.Model):
    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    user = models.ForeignKey("users.User", on_delete=models.CASCADE, related_name="user_tasks", verbose_name=_("User"))
    task = models.ForeignKey(
        "annotations.Task", on_delete=models.CASCADE, related_name="user_tasks", verbose_name=_("Task")
    )
    state = models.CharField(max_length=32, choices=TaskState, default=TaskState.Draft, verbose_name=_("State"))
    is_preview = models.BooleanField(default=False, verbose_name=_("Is preview"))
    has_uncertain_value = models.BooleanField(default=False, verbose_name=_("Has uncertain value"))

    created = models.DateTimeField(auto_now_add=True, verbose_name=pgettext_lazy("feminine", "Created"))
    updated = models.DateTimeField(auto_now=True, verbose_name=pgettext_lazy("feminine", "Updated"))

    class Meta:
        verbose_name = _("User task")
        verbose_name_plural = _("User tasks")
        unique_together = (("task", "user"),)

    def clean(self):
        if not self.user_id or not self.task_id:
            return

        if not Membership.objects.filter(user=self.user, project=self.task.element.project).exists():
            raise ValidationError(
                {"user": _("User is not member of the project %(project)s") % {"project": self.task.element.project}}
            )

    @property
    def annotate_url(self):
        annotate_url_name = USER_TASK_ANNOTATE_URL_NAMES.get(self.task.campaign.mode)
        if annotate_url_name:
            return reverse(annotate_url_name, kwargs={"pk": self.id})

    @property
    def moderate_url(self):
        moderate_url_name = USER_TASK_MODERATE_URL_NAMES.get(self.task.campaign.mode)
        if moderate_url_name:
            return reverse(moderate_url_name, kwargs={"pk": self.id})

    @property
    def details_url(self):
        details_url_name = USER_TASK_DETAILS_URL_NAMES.get(self.task.campaign.mode)
        if details_url_name:
            return reverse(details_url_name, kwargs={"pk": self.id})


class AnnotationState(models.TextChoices):
    Validated = "validated", pgettext_lazy("feminine", "Validated")
    Rejected = "rejected", pgettext_lazy("feminine", "Rejected")


class Annotation(models.Model):
    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    user_task = models.ForeignKey(
        "annotations.TaskUser", on_delete=models.CASCADE, related_name="annotations", verbose_name=_("User task")
    )
    parent = models.ForeignKey(
        "annotations.Annotation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
        verbose_name=_("Parent"),
    )
    value = models.JSONField(blank=True, default=dict, verbose_name=_("Value"))
    version = models.PositiveIntegerField(default=1, verbose_name=_("Version"))
    published = models.BooleanField(default=False, verbose_name=pgettext_lazy("feminine", "Published"))
    duration = models.DurationField(null=True, blank=True, verbose_name=_("Completion time"))

    state = models.CharField(max_length=32, null=True, blank=True, choices=AnnotationState, verbose_name=_("State"))
    moderator = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="moderated_annotations",
        verbose_name=_("Moderator"),
    )

    created = models.DateTimeField(auto_now_add=True, verbose_name=pgettext_lazy("feminine", "Created"))
    updated = models.DateTimeField(auto_now=True, verbose_name=pgettext_lazy("feminine", "Updated"))

    class Meta:
        verbose_name = _("Annotation")
        verbose_name_plural = _("Annotations")
        unique_together = (("user_task", "version"),)

    def __str__(self):
        return _("Version n°%(version)s - %(created)s") % {"version": self.version, "created": localize(self.created)}

    def clean(self):
        if not self.parent:
            return

        if self.parent.id == self.id:
            raise ValidationError({"parent": _("An annotation cannot be its own parent")})

        if self.parent.user_task != self.user_task:
            raise ValidationError({"parent": _("Parent is not part of the same user task")})
