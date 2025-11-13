import json
from operator import itemgetter

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from callico.annotations.models import TaskState
from callico.process.models import Process
from callico.process.utils import get_entity_display_string
from callico.projects.forms import EMPTY_CHOICE, REQUIRED_CSS_CLASS
from callico.projects.models import CampaignMode
from callico.projects.utils import flatten_campaign_fields


class ArkindexImportProcessCreateForm(forms.ModelForm):
    required_css_class = REQUIRED_CSS_CLASS

    element = forms.UUIDField(
        required=False,
        label=_("Element"),
        help_text=_("The UUID of an Arkindex element to import, by default the entire corpus will be imported"),
    )
    dataset = forms.UUIDField(
        required=False,
        label=_("Dataset"),
        help_text=_("The UUID of an Arkindex dataset to import, by default the entire corpus will be imported"),
    )
    dataset_sets = forms.CharField(
        required=False,
        label=_("Filter sets to import"),
        widget=forms.TextInput(attrs={"placeholder": _('Input a set name and hit the "Enter" key')}),
        help_text=_("Restrict to elements from the specified sets, by default all sets will be imported"),
    )
    types = forms.MultipleChoiceField(
        required=False,
        choices=[],
        label=_("Filter types to import"),
        help_text=_("Restrict to elements with the given type slugs, by default all elements will be imported"),
    )
    ml_class = forms.ChoiceField(
        required=False,
        choices=[],
        label=_("Filter the class to import"),
        help_text=_("Restrict to elements with the given class name, by default all elements will be imported"),
    )
    transcriptions = forms.MultipleChoiceField(
        required=False,
        choices=[],
        label=_("Filter the transcriptions to import (sort from most to least suitable)"),
        widget=forms.CheckboxSelectMultiple(),
        help_text=_(
            "Allow to import one transcription (if available) per element that was either manually annotated or produced by one of the listed worker runs"
        ),
    )
    entities = forms.MultipleChoiceField(
        required=False,
        choices=[],
        label=_("Filter the transcription entities to import (sort from most to least suitable)"),
        widget=forms.CheckboxSelectMultiple(),
        help_text=_(
            "Allow to import transcription entities from one source (if available) per element that was either manually annotated or produced by one of the listed worker runs"
        ),
    )
    elements_worker_run = forms.CharField(
        required=False,
        label=_("Filter the worker results to import"),
        widget=forms.TextInput(
            attrs={
                "placeholder": _('Selected filters will appear here once you\'ve clicked on the "Save" button'),
                "readonly": True,
            }
        ),
        help_text=_("Restrict to elements produced by the given worker run for their type"),
    )
    metadata = forms.CharField(
        required=False,
        label=_("Filter the metadata to import"),
        widget=forms.TextInput(attrs={"placeholder": _('Input a metadata name and hit the "Enter" key')}),
        help_text=_(
            "Allow to import metadata matching the given names on each imported element. Metadata can either be retrieved from the element or its parents."
        ),
    )

    class Meta:
        model = Process
        fields = (
            "name",
            "element",
            "dataset",
            "dataset_sets",
            "types",
            "ml_class",
            "transcriptions",
            "entities",
            "elements_worker_run",
            "metadata",
        )

    def __init__(self, *args, **kwargs):
        self.types = kwargs.pop("types")
        self.ml_classes = kwargs.pop("ml_classes")
        self.worker_runs = kwargs.pop("worker_runs")

        super().__init__(*args, **kwargs)

        self.fields["name"].label = _("Process name")

        if self.types:
            self.fields["types"].choices = [(type["provider_object_id"], type["name"]) for type in self.types]
        else:
            self.fields["types"].widget.attrs["disabled"] = True
            self.fields["types"].help_text = _(
                "No type was found for this project, it means that an error might have occurred during the retrieval of extra information from Arkindex. Therefore this filter is disabled, please contact an administrator if you wish to use it."
            )

        if not self.types or not self.worker_runs:
            self.fields["elements_worker_run"].widget.attrs["disabled"] = True
            self.fields["elements_worker_run"].help_text = _(
                "No type and/or worker run was found for this project, it means that an error might have occurred during the retrieval of extra information from Arkindex. Therefore this filter is disabled, please contact an administrator if you wish to use it."
            )

        if self.ml_classes:
            self.fields["ml_class"].choices = [("", _("All classes"))] + [
                (ml_class, ml_class.capitalize()) for ml_class in self.ml_classes
            ]
        else:
            self.fields["ml_class"].widget.attrs["disabled"] = True
            self.fields["ml_class"].help_text = _(
                "No class was found for this project, it means that an error might have occurred during the retrieval of extra information from Arkindex. Therefore this filter is disabled, please contact an administrator if you wish to use it."
            )

        wr_choices = [(wr["id"], wr["summary"]) for wr in self.worker_runs]
        self.fields["transcriptions"].choices = self.fields["entities"].choices = [("manual", _("Manual"))] + wr_choices

    def clean_metadata(self):
        return [name.strip() for name in self.cleaned_data["metadata"].split(",") if name]

    def clean_dataset_sets(self):
        return [name.strip() for name in self.cleaned_data["dataset_sets"].split(",") if name]

    def clean_elements_worker_run(self):
        elements_worker_run = {}

        try:
            for couple in self.cleaned_data["elements_worker_run"].split(","):
                if not couple:
                    continue
                [type, source] = couple.split("=")
                elements_worker_run[type] = source
        except Exception:
            self.add_error(
                "elements_worker_run",
                ValidationError(_("The value of this field is malformed and impossible to parse.")),
            )

        return elements_worker_run

    def clean(self):
        entities = self.cleaned_data.get("entities")
        transcriptions = self.cleaned_data.get("transcriptions")
        if not transcriptions and entities:
            self.add_error("entities", _("It is not possible to import entities without also importing transcriptions"))

        element = self.cleaned_data.get("element")
        dataset = self.cleaned_data.get("dataset")
        dataset_sets = self.cleaned_data.get("dataset_sets")
        if element and dataset:
            self.add_error("element", _("The dataset and element fields are mutually exclusive"))
            self.add_error("dataset", _("The dataset and element fields are mutually exclusive"))

        if dataset_sets and not dataset:
            self.add_error("dataset", _("The dataset field must be filled in order to select sets"))


class ArkindexExportProcessCreateForm(forms.ModelForm):
    required_css_class = REQUIRED_CSS_CLASS

    exported_states = forms.MultipleChoiceField(
        required=True,
        choices=[
            (state.value, state.label) for state in TaskState if state in [TaskState.Annotated, TaskState.Validated]
        ],
        label=_("Status of tasks to be exported"),
    )
    force_republication = forms.BooleanField(
        required=False,
        label=_("Force the republication of annotations"),
        help_text=_(
            "Existing <code>WorkerResults</code> produced by Callico should be deleted from Arkindex before using this option if an export was previously made"
        ),
    )
    use_raw_publication = forms.BooleanField(
        required=False,
        label=_("Publish each annotation separately"),
        help_text=_("Annotations will not be grouped before publication even if they have the same value"),
    )

    class Meta:
        model = Process
        fields = ("name", "exported_states", "force_republication", "use_raw_publication")

    def __init__(self, *args, **kwargs):
        campaign = kwargs.pop("campaign")

        super().__init__(*args, **kwargs)

        self.fields["name"].label = _("Process name")
        self.fields["exported_states"].widget.attrs["size"] = 2
        if campaign.mode == CampaignMode.Classification:
            del self.fields["use_raw_publication"]

        if campaign.mode == CampaignMode.EntityForm:
            configured_fields = [
                (
                    json.dumps([field["entity_type"], field["instruction"]]),
                    get_entity_display_string(field["entity_type"], field["instruction"], group),
                )
                for group, field in flatten_campaign_fields(campaign)
            ]
            if configured_fields:
                self.fields["entities_order"] = forms.MultipleChoiceField(
                    required=True,
                    choices=configured_fields,
                    initial=list(map(itemgetter(0), configured_fields)),
                    label=_("Sort the entities to export, by default the order from the configuration will be used"),
                    widget=forms.CheckboxSelectMultiple(),
                )

            self.fields["concatenation_parent_type"] = forms.ChoiceField(
                required=False,
                choices=[EMPTY_CHOICE] + list(campaign.project.types.order_by("name").values_list("id", "name")),
                label=_("Also export entities on a parent"),
                help_text=_(
                    "Annotations will also be exported in a concatenated transcription on a parent matching the chosen type"
                ),
            )

    def clean_entities_order(self):
        return list(map(json.loads, self.cleaned_data["entities_order"]))
