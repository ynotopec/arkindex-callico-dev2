import json
import re

from django import forms
from django.core.exceptions import ValidationError
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy

from callico.annotations.models import TaskState
from callico.projects.models import (
    NO_IMAGE_SUPPORTED_CAMPAIGN_MODES,
    Authority,
    Campaign,
    CampaignMode,
    Membership,
    Project,
    Role,
)
from callico.projects.utils import ENTITY_FORM_GROUP_MODE, flatten_campaign_fields, get_campaign_field_groups
from callico.users.models import User

REQUIRED_CSS_CLASS = "is-required"

EMPTY_CHOICE = (None, "---------")

ALGORITHM_RANDOM = "random"
ALGORITHM_SEQUENTIAL = "sequential"

ALGORITHM_CHOICES = (
    (ALGORITHM_RANDOM, _("Random")),
    (ALGORITHM_SEQUENTIAL, _("Sequential")),
)

ELEMENT_SELECTION_ALL = "all"
ELEMENT_SELECTION_UNUSED = "unused"

ELEMENT_SELECTION_CHOICES = (
    (ELEMENT_SELECTION_ALL, _("All elements")),
    (ELEMENT_SELECTION_UNUSED, _("Only unused elements")),
)

NO_USER = "no_user"

ENTITY_TRANSCRIPTION_DISPLAY_ONLY = "only"
ENTITY_TRANSCRIPTION_DISPLAY_NEXT_TO_IMAGE = "next_to_image"
# Display modes available during Entity campaigns configuration, allowing to show either:
# - only the transcription,
# - the transcription next to the image.
ENTITY_TRANSCRIPTION_DISPLAY_CHOICES = (
    (ENTITY_TRANSCRIPTION_DISPLAY_ONLY, _("Transcription only")),
    (ENTITY_TRANSCRIPTION_DISPLAY_NEXT_TO_IMAGE, _("Transcription next to the image")),
)

USER_TASK_AVAILABLE_STATE = "available"

USER_TASK_NO_FEEDBACK = "no_feedback"
USER_TASK_ALL_FEEDBACKS = "all_feedbacks"
USER_TASK_WITH_COMMENTS = "with_comments"
USER_TASK_UNCERTAIN_FEEDBACK = "uncertain"


class BulmaClearableImageInput(forms.widgets.ClearableFileInput):
    clear_checkbox_label = _("Clear the current image")
    template_name = "bulma_clearable_image_input.html"


class ProjectManagementForm(forms.ModelForm):
    required_css_class = REQUIRED_CSS_CLASS

    class Meta:
        model = Project
        fields = ("name", "description", "illustration", "provider", "provider_object_id")
        widgets = {"illustration": BulmaClearableImageInput()}


class MembershipForm(forms.ModelForm):
    required_css_class = REQUIRED_CSS_CLASS

    user_email = forms.EmailField(
        required=True,
        label=_("Email"),
    )
    role = forms.ChoiceField(
        choices=[EMPTY_CHOICE] + [(role, role.label) for role in Role],
        required=True,
        label=_("Role"),
    )

    class Meta:
        model = Membership
        fields = ("user_email", "role")

    def __init__(self, *args, **kwargs):
        self.project = kwargs.pop("project")
        super().__init__(*args, **kwargs)

        self.editing = self.instance and self.instance.pk
        if self.editing:
            self.fields["user_email"].initial = self.instance.user.email
            self.fields["user_email"].disabled = True

    def clean_user_email(self):
        # In edition mode, the user email should not change
        if self.editing:
            return self.instance.user

        user_email = self.cleaned_data["user_email"]

        # The provided email should match an existing user
        user = User.objects.filter(email=user_email).first()
        if not user:
            raise ValidationError(_("There are no users with this email."))

        # The user should not have multiple memberships on the same project
        if Membership.objects.filter(project=self.project, user=user).exists():
            raise ValidationError(_("The user is already a member of this project."))

        return user


class BaseCampaignForm(forms.Form):
    required_css_class = REQUIRED_CSS_CLASS

    def __init__(self, *args, **kwargs):
        self.campaign = kwargs.pop("campaign")
        super().__init__(*args, **kwargs)

    @property
    def contributors(self):
        return User.objects.filter(
            memberships__project=self.campaign.project, memberships__role=Role.Contributor
        ).order_by(Lower("display_name"))

    @property
    def all_types(self):
        return self.campaign.project.types.order_by("name").values_list("id", "name")

    @property
    def all_nonfolder_types(self):
        return self.all_types.filter(folder=False)

    @property
    def all_used_types(self):
        return self.all_types.filter(elements__isnull=False).distinct()

    @property
    def all_used_nonfolder_types(self):
        return self.all_used_types.filter(folder=False)


class CampaignCreateForm(forms.ModelForm):
    required_css_class = REQUIRED_CSS_CLASS

    class Meta:
        model = Campaign
        fields = ("name", "mode", "description")

    def __init__(self, *args, **kwargs):
        self.project = kwargs.pop("project")

        super().__init__(*args, **kwargs)

    def clean_mode(self):
        mode = self.cleaned_data["mode"]

        if mode == CampaignMode.Classification and not self.project.classes.count():
            raise ValidationError(_("There are no classes available for this project"))

        if mode == CampaignMode.Elements and not self.project.types.filter(folder=False).count():
            raise ValidationError(_("There are no non-folder element types available for this project"))

        if mode == CampaignMode.ElementGroup and not self.project.types.count():
            raise ValidationError(_("There are no element types available for this project"))

        return mode


class BaseCampaignUpdateForm(BaseCampaignForm, forms.ModelForm):
    required_css_class = REQUIRED_CSS_CLASS

    class Meta:
        model = Campaign
        fields = ("name", "description", "nb_tasks_auto_assignment", "max_user_tasks")

    def __init__(self, *args, **kwargs):
        kwargs["campaign"] = kwargs.get("instance")
        super().__init__(*args, **kwargs)
        self.fields["nb_tasks_auto_assignment"].help_text = _(
            'The number of tasks that could be assigned per volunteering contributor if you have available tasks. If this number is equal to zero then the "Request tasks" button will not appear.'
        )
        self.fields["max_user_tasks"].help_text = _(
            "By default, available tasks will be requestable by only 1 annotator at a time, if you want to gather double inputs from various annotators, you can increase this number to 2 and so on"
        )


class ContextualizedCampaignUpdateForm(BaseCampaignUpdateForm):
    context_type = forms.ChoiceField(
        choices=[],
        required=False,
        label=_("Context ancestor type"),
        help_text=_(
            "Allows to display context surrounding the element to annotate if an ancestor of the selected type exists"
        ),
    )

    class Meta:
        model = Campaign
        fields = BaseCampaignUpdateForm.Meta.fields + ("context_type",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["context_type"].choices = [EMPTY_CHOICE] + list(self.all_used_nonfolder_types)
        self.fields["context_type"].initial = self.instance.configuration.get("context_type")


class TranscriptionCampaignUpdateForm(BaseCampaignUpdateForm):
    display_grouped_inputs = forms.BooleanField(
        required=False,
        label=_(
            "Group the transcription inputs for a lighter display during annotation (recommended when only one element type is picked)"
        ),
    )
    children_types = forms.MultipleChoiceField(
        choices=[],
        required=True,
        label=_("Element types to annotate"),
        widget=forms.CheckboxSelectMultiple(),
    )
    confidence_threshold = forms.FloatField(
        min_value=0,
        max_value=1,
        required=False,
        label=_("Confidence threshold (between 0 and 1) to highlight imported transcriptions needing validation"),
        help_text=_(
            "Imported transcriptions associated to a confidence level below this threshold will be highlighted in red during annotation. If this value is unset, the confidence will be ignored."
        ),
    )

    class Meta:
        model = Campaign
        fields = BaseCampaignUpdateForm.Meta.fields + (
            "display_grouped_inputs",
            "children_types",
            "confidence_threshold",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["display_grouped_inputs"].initial = self.instance.configuration.get("display_grouped_inputs", False)
        self.fields["children_types"].choices = self.all_used_nonfolder_types
        self.fields["children_types"].initial = (
            self.instance.configuration["children_types"]
            if "children_types" in self.instance.configuration
            else list(dict(self.fields["children_types"].choices).keys())
        )
        self.fields["confidence_threshold"].initial = self.instance.configuration.get("confidence_threshold")


class ElementGroupCampaignUpdateForm(BaseCampaignUpdateForm):
    carousel_type = forms.ChoiceField(
        choices=[],
        required=True,
        label=_("Element type to display in a carousel"),
        help_text=_("It is the direct children of these elements that will be grouped"),
    )
    group_type = forms.ChoiceField(
        choices=[],
        required=True,
        label=_("Element type to use to publish the grouped elements"),
    )

    class Meta:
        model = Campaign
        fields = BaseCampaignUpdateForm.Meta.fields + ("carousel_type", "group_type")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["carousel_type"].choices = self.all_used_nonfolder_types
        if "carousel_type" in self.instance.configuration:
            self.fields["carousel_type"].initial = self.instance.configuration["carousel_type"]
        else:
            self.fields["carousel_type"].choices.insert(0, EMPTY_CHOICE)

        self.fields["group_type"].choices = self.all_types
        if "group_type" in self.instance.configuration:
            self.fields["group_type"].initial = self.instance.configuration["group_type"]
        else:
            self.fields["group_type"].choices.insert(0, EMPTY_CHOICE)

    def clean(self):
        carousel_type = self.cleaned_data.get("carousel_type")
        group_type = self.cleaned_data.get("group_type")

        if carousel_type and group_type and carousel_type == group_type:
            raise ValidationError({"group_type": _("Carousel and group types cannot be the same")})

        return self.cleaned_data


class ElementsCampaignUpdateForm(BaseCampaignUpdateForm):
    element_types = forms.MultipleChoiceField(
        choices=[],
        required=True,
        label=_("Element types to use to annotate"),
        widget=forms.CheckboxSelectMultiple(),
    )

    class Meta:
        model = Campaign
        fields = BaseCampaignUpdateForm.Meta.fields + ("element_types",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["element_types"].choices = self.all_nonfolder_types
        self.fields["element_types"].initial = (
            self.instance.configuration["element_types"]
            if "element_types" in self.instance.configuration
            else list(dict(self.fields["element_types"].choices).keys())
        )


class ClassificationCampaignUpdateForm(ContextualizedCampaignUpdateForm):
    classes = forms.MultipleChoiceField(
        choices=[],
        required=True,
        label=_("Classes to use to annotate"),
        widget=forms.CheckboxSelectMultiple(),
    )

    class Meta:
        model = Campaign
        fields = ContextualizedCampaignUpdateForm.Meta.fields + ("classes",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["classes"].choices = [
            (class_id, class_name.capitalize())
            for class_id, class_name in self.instance.project.classes.order_by("name").values_list("id", "name")
        ]
        self.fields["classes"].initial = (
            self.instance.configuration["classes"]
            if "classes" in self.instance.configuration
            else list(dict(self.fields["classes"].choices).keys())
        )


class EntityCampaignUpdateForm(ContextualizedCampaignUpdateForm):
    transcription_display = forms.ChoiceField(
        required=True,
        choices=ENTITY_TRANSCRIPTION_DISPLAY_CHOICES,
        label=_("Display"),
    )
    full_word_selection = forms.BooleanField(
        required=False,
        label=_("Prevents contributors from partially selecting words when annotating"),
    )

    class Meta:
        model = Campaign
        fields = ContextualizedCampaignUpdateForm.Meta.fields + ("transcription_display",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["transcription_display"].initial = self.instance.configuration.get(
            "transcription_display", ENTITY_TRANSCRIPTION_DISPLAY_ONLY
        )
        self.fields["full_word_selection"].initial = self.instance.configuration.get("full_word_selection", True)


class EntityFormCampaignUpdateForm(ContextualizedCampaignUpdateForm):
    entities_order = forms.CharField(
        widget=forms.HiddenInput(),
        required=False,
    )

    class Meta:
        model = Campaign
        fields = ContextualizedCampaignUpdateForm.Meta.fields + ("entities_order",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        entities_order = []
        for field in self.instance.configuration.get("fields", []):
            if field.get("mode") != ENTITY_FORM_GROUP_MODE:
                entities_order.append(("", field["entity_type"], field["instruction"]))
                continue

            legend = field["legend"]
            entities_order.extend(
                [(legend, "", "")]
                + [(legend, group_field["entity_type"], group_field["instruction"]) for group_field in field["fields"]]
            )

        self.fields["entities_order"].initial = json.dumps(entities_order)

    def clean_entities_order(self):
        if not self.cleaned_data["entities_order"]:
            return []

        return json.loads(self.cleaned_data["entities_order"])


class BaseEntityCampaignUpdateFormset(forms.Form):
    required_css_class = REQUIRED_CSS_CLASS

    entity_type = forms.CharField(
        required=True,
        label=_("Entity type"),
    )

    class Meta:
        fields = ("entity_type",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["entity_type"].widget.attrs["list"] = "entity-type-list"
        self.fields["entity_type"].widget.attrs["autocomplete"] = "off"


class EntityCampaignUpdateFormset(BaseEntityCampaignUpdateFormset):
    entity_color = forms.CharField(
        required=True,
        label=_("Display color for the entity"),
        widget=forms.TextInput(attrs={"type": "color"}),
    )

    class Meta:
        fields = BaseEntityCampaignUpdateFormset.Meta.fields + ("entity_color",)


class EntityFormFieldForm(BaseEntityCampaignUpdateFormset):
    instruction = forms.CharField(
        required=True,
        label=_("Instruction for the contributor to annotate"),
    )
    help_text = forms.CharField(
        required=False,
        label=_("Further instructions to help the contributor, hidden behind an icon during the annotation"),
    )
    group = forms.ChoiceField(
        choices=[(-1, EMPTY_CHOICE[1])],
        required=False,
        label=_("Group"),
    )
    confidence_threshold = forms.FloatField(
        min_value=0,
        max_value=1,
        required=False,
        label=_("Confidence threshold (between 0 and 1) to highlight imported entities needing validation"),
        help_text=_(
            "Imported entities associated to a confidence level below this threshold will be highlighted in red during annotation. If this value is unset, the confidence will be ignored."
        ),
    )
    validation_regex = forms.CharField(
        required=False,
        label=_("Regular expression to use to validate the input"),
        help_text=_(
            'Enter a valid regular expression that will be used to validate the inputs of less than 100 characters for this field. You can find help on <a href="https://regex101.com/" target="_blank">https://regex101.com/</a> to write regular expressions.'
        ),
    )
    from_authority = forms.ModelChoiceField(
        queryset=Authority.objects.all(),
        required=False,
        label=_("Authority record to restrict allowed annotations"),
    )
    allow_predefined_choices = forms.BooleanField(
        required=False,
        label=_("Customize allowed annotations for this field"),
    )
    predefined_choices = forms.CharField(
        required=False,
        label=_('List of custom annotations for this field, separated by ","'),
        help_text=_('e.g.: "woman,man" will result in ["woman", "man"]'),
    )

    class Meta:
        fields = EntityCampaignUpdateFormset.Meta.fields + ("instruction",)

    def __init__(self, *args, **kwargs):
        self.campaign = kwargs.pop("campaign")
        self.position = kwargs.pop("position")
        self.group = kwargs.pop("group")
        super().__init__(*args, **kwargs)

        self.fields["group"].choices += [
            (index, field["legend"]) for (index, field) in get_campaign_field_groups(self.campaign)
        ]
        self.fields["group"].initial = self.group

        self.initial_couple = (None, None)
        if self.position is not None:
            field = (
                self.campaign.configuration["fields"][self.position]
                if self.group < 0
                else self.campaign.configuration["fields"][self.group]["fields"][self.position]
            )
            self.initial_couple = (field.get("entity_type"), field.get("instruction"))

    def clean_validation_regex(self):
        regex_string = self.cleaned_data["validation_regex"]

        try:
            re.compile(regex_string)
        except re.error:
            raise ValidationError(_("The regular expression is invalid."))

        return regex_string

    def clean(self):
        cleaned_couple = (self.cleaned_data.get("entity_type"), self.cleaned_data.get("instruction"))
        existing_couples = [
            (field.get("entity_type"), field.get("instruction"))
            for _group, field in flatten_campaign_fields(self.campaign)
        ]
        if self.initial_couple != cleaned_couple and cleaned_couple in existing_couples:
            raise ValidationError(
                {
                    "entity_type": _(
                        "The entity type/instruction combination must be unique across configured fields."
                    ),
                    "instruction": _(
                        "The entity type/instruction combination must be unique across configured fields."
                    ),
                }
            )

        from_authority = self.cleaned_data.get("from_authority")
        # We don't need to keep "allow_predefined_choices" in the configuration
        allow_predefined_choices = self.cleaned_data.pop("allow_predefined_choices")
        predefined_choices = self.cleaned_data.get("predefined_choices")

        # If some choices were provided before the input was hidden, we need to clear them
        # We do this here to allow checking/unchecking the checkbox without losing entered choices
        if not allow_predefined_choices:
            del self.cleaned_data["predefined_choices"]
            predefined_choices = None

        # We want either allowed annotations from an authority or from a custom list, not both
        if from_authority and predefined_choices:
            self.add_error(
                "from_authority",
                _(
                    "The fields to limit allowed annotations, either from an authority or a custom list, are mutually exclusive"
                ),
            )
            self.add_error(
                "predefined_choices",
                _(
                    "The fields to limit allowed annotations, either from an authority or a custom list, are mutually exclusive"
                ),
            )

        if allow_predefined_choices and not predefined_choices:
            raise ValidationError({"predefined_choices": _("You must set at least one custom choice.")})

        # Only store the authority ID as a string to make the formset JSON serializable
        if from_authority:
            self.cleaned_data["from_authority"] = str(from_authority.id)

        return self.cleaned_data


class EntityFormGroupForm(forms.Form):
    required_css_class = REQUIRED_CSS_CLASS

    legend = forms.CharField(
        required=True,
        label=_("Legend of the field group"),
    )

    class Meta:
        fields = ("legend",)

    def __init__(self, *args, **kwargs):
        self.campaign = kwargs.pop("campaign")
        self.position = kwargs.pop("position")
        self.group = kwargs.pop("group")
        super().__init__(*args, **kwargs)

    def clean_legend(self):
        legend = self.cleaned_data.get("legend")
        # Each group legend should be unique
        if legend in [
            field["legend"]
            for (index, field) in get_campaign_field_groups(self.campaign)
            if self.position is None or index != self.position
        ]:
            raise ValidationError(_("The legend must be unique across configured field groups."))

        return legend

    def clean(self):
        self.cleaned_data["mode"] = ENTITY_FORM_GROUP_MODE
        # After group edition, we should keep its configured fields
        self.cleaned_data["fields"] = (
            self.campaign.configuration["fields"][self.position]["fields"] if self.position is not None else []
        )

        return self.cleaned_data


class CampaignTasksCreateForm(BaseCampaignForm):
    type = forms.ChoiceField(
        choices=[],
        required=True,
        label=_("Element type"),
    )
    users = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(),
        widget=forms.CheckboxSelectMultiple(),
        label=_("Users"),
        required=False,
    )
    algorithm = forms.ChoiceField(
        choices=sorted(ALGORITHM_CHOICES, key=lambda algo: algo[1]),
        initial=ALGORITHM_SEQUENTIAL,
        label=_("Attribution algorithm"),
    )
    element_selection = forms.ChoiceField(
        choices=sorted(ELEMENT_SELECTION_CHOICES, key=lambda selection: selection[1]),
        initial=ELEMENT_SELECTION_ALL,
        required=False,
        label=_("Elements to use"),
    )
    max_number = forms.IntegerField(
        min_value=1,
        initial=50,
        required=False,
        label=_("Maximum number of tasks per user"),
        help_text=_("If the input is empty, all elements will be used"),
    )
    create_unassigned_tasks = forms.BooleanField(
        required=False,
        label=_("Create unassigned tasks"),
        help_text=_(
            "All remaining elements that aren't yet used or to use with this form, will be made available for open annotation by volunteering contributors"
        ),
    )

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)

        self.fields["type"].choices = self.all_used_nonfolder_types
        if self.campaign.mode == CampaignMode.ElementGroup:
            self.fields["type"].choices = self.all_used_types
        elif self.campaign.mode not in NO_IMAGE_SUPPORTED_CAMPAIGN_MODES:
            self.fields["type"].choices = self.all_used_nonfolder_types.exclude(elements__image__isnull=True)

        if self.campaign.mode == CampaignMode.Transcription:
            self.fields["type"].label = _("Element type to use and display to the user")
            self.fields["type"].help_text = _(
                'This element type is not the same as the element types to annotate defined in the campaign configuration. See the <a href="https://doc.callico.eu/tasks/create/#special-case-transcription-campaign" target="_blank">documentation</a>.'
            )

        if self.campaign.mode == CampaignMode.ElementGroup:
            self.fields["type"].label = _("Element type to use for the user")
            self.fields["type"].help_text = _(
                'This element type is not the same as the carousel type to display defined in the campaign configuration. See the <a href="https://doc.callico.eu/tasks/create/#special-case-element-group-campaign" target="_blank">documentation</a>.'
            )

        if self.contributors:
            self.fields["users"].queryset = self.contributors
        else:
            self.fields["users"].help_text = _(
                "No contributor is available in this project, you can still create unassigned tasks that could be assigned to volunteering contributors"
            )

    def clean_element_selection(self):
        element_selection = self.cleaned_data["element_selection"]
        if element_selection == ELEMENT_SELECTION_UNUSED:
            element_type = self.cleaned_data["type"]
            assigned_tasks = self.campaign.tasks.filter(user_tasks__isnull=False).values_list("id", flat=True)
            nb_elements = (
                self.campaign.project.elements.filter(type_id=element_type).exclude(tasks__in=assigned_tasks).count()
            )

            if not nb_elements:
                type_name = self.campaign.project.types.get(id=element_type).name
                raise ValidationError(
                    _("There is no unused %(element_type)s elements on this campaign") % {"element_type": type_name}
                )

        return element_selection

    def clean(self):
        if (
            "preview" not in self.request.POST
            and "create_unassigned_tasks" not in self.request.POST
            and "users" not in self.request.POST
        ):
            self.add_error(
                "users",
                _(
                    "When you aren't creating unassigned tasks for volunteers or generating a preview task, this field is required."
                ),
            )

        if (
            "preview" in self.request.POST or "users" in self.request.POST
        ) and "element_selection" not in self.request.POST:
            self.add_error(
                "element_selection",
                _(
                    "When you are creating assigned tasks for contributors or generating a preview task, this field is required."
                ),
            )


class BaseCampaignTasksListForm(BaseCampaignForm):
    state = forms.ChoiceField(
        choices=[("", _("All status"))] + [(state.value, state.label) for state in TaskState],
        required=False,
        label=_("Status"),
    )
    user_feedback = forms.ChoiceField(
        choices=[EMPTY_CHOICE],
        required=False,
        label=_("Users feedback"),
    )


class ContributorCampaignTasksListForm(BaseCampaignTasksListForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["state"].choices += [(USER_TASK_AVAILABLE_STATE, _("Available"))]

        if self.campaign.mode in [CampaignMode.Transcription, CampaignMode.EntityForm]:
            self.fields["user_feedback"].choices.append(
                (USER_TASK_UNCERTAIN_FEEDBACK, pgettext_lazy("feminine", "Uncertain"))
            )


class AdminCampaignTasksListForm(BaseCampaignTasksListForm):
    user_id = forms.ChoiceField(
        choices=[(NO_USER, _("Without user")), ("", _("All users"))],
        required=False,
        label=_("User"),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["user_feedback"].choices += [
            (USER_TASK_NO_FEEDBACK, _("No feedback")),
            (USER_TASK_WITH_COMMENTS, _("With comments")),
        ]
        if self.campaign.mode in [CampaignMode.Transcription, CampaignMode.EntityForm]:
            self.fields["user_feedback"].choices += [
                (USER_TASK_UNCERTAIN_FEEDBACK, _("Marked as uncertain by the user")),
                (USER_TASK_ALL_FEEDBACKS, _("With comments and marked as uncertain by the user")),
            ]

        project_members_with_user_tasks = User.objects.filter(user_tasks__task__campaign=self.campaign)
        user_choices = self.contributors | project_members_with_user_tasks
        self.fields["user_id"].choices += list(
            user_choices.distinct().order_by(Lower("display_name")).values_list("id", "display_name")
        )
        self.fields["user_id"].widget.attrs["class"] = (
            self.fields["user_id"].widget.attrs.get("class", "") + " truncate-long-words restricted-max-width-100"
        )
