import re

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from callico.annotations.models import Task
from callico.base.fields import validate_polygon
from callico.projects.forms import REQUIRED_CSS_CLASS
from callico.projects.models import AuthorityValue


class AnnotateForm(forms.ModelForm):
    required_css_class = REQUIRED_CSS_CLASS

    annotation = forms.CharField(
        widget=forms.Textarea(attrs={"autofocus": True, "placeholder": _("Your annotation")}),
        required=False,
        label=_("Annotation"),
    )

    class Meta:
        model = Task
        fields = ("annotation",)


class AnnotationParentForm(forms.Form):
    required_css_class = REQUIRED_CSS_CLASS

    parent_id = forms.ModelChoiceField(
        queryset=None,
        required=True,
        label=_("Parent version"),
    )

    def __init__(self, user_task, initial_parent, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["parent_id"].queryset = user_task.annotations.order_by("version")
        if initial_parent:
            self.fields["parent_id"].initial = initial_parent
            self.fields["parent_id"].empty_label = None


class ClassificationAnnotateForm(forms.ModelForm):
    required_css_class = REQUIRED_CSS_CLASS

    annotation = forms.ChoiceField(
        required=True,
        label=_("Annotation"),
    )

    class Meta:
        model = Task
        fields = ("annotation",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        class_ids = (
            self.instance.campaign.configuration["classes"]
            if "classes" in self.instance.campaign.configuration
            else self.instance.campaign.project.classes.values_list("id", flat=True)
        )
        self.fields["annotation"].choices = [
            (str(class_id), class_name.capitalize())
            for class_id, class_name in self.instance.campaign.project.classes.filter(id__in=class_ids)
            .order_by("name")
            .values_list("id", "name")
        ]


class EntityAnnotateForm(forms.ModelForm):
    required_css_class = REQUIRED_CSS_CLASS

    entity_type = forms.ChoiceField(
        widget=forms.HiddenInput(),
        required=True,
        choices=[],
    )
    offset = forms.IntegerField(
        widget=forms.HiddenInput(),
        required=True,
        min_value=0,
    )
    length = forms.IntegerField(
        widget=forms.HiddenInput(),
        required=True,
        min_value=1,
    )

    class Meta:
        model = Task
        fields = ("entity_type", "offset", "length")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["entity_type"].choices = [
            (entity_type["entity_type"], entity_type["entity_type"])
            for entity_type in self.instance.campaign.configuration.get("types", [])
        ]

    def clean(self):
        if not self.instance.element.transcription.get("text") or (
            not self.has_error("offset")
            and not self.has_error("length")
            and self.cleaned_data["offset"] + self.cleaned_data["length"]
            > len(self.instance.element.transcription["text"])
        ):
            self.add_error("__all__", _("The entity is not part of the transcription"))


class EntityFormAnnotateForm(AnnotateForm):
    def clean_annotation(self):
        annotation = self.cleaned_data["annotation"]

        if not annotation:
            return annotation

        # - Authority validation -
        authority = self.fields["annotation"].widget.attrs.get("authority_id")
        if authority and not AuthorityValue.objects.filter(authority_id=authority, value=annotation).exists():
            raise ValidationError(
                _("%(annotation)s is not one of the allowed authority values.") % {"annotation": annotation}
            )

        # - Regular expression validation -
        # We don't even try to validate long inputs to have some kind of security even if it's not enough
        if len(annotation) > 100:
            return annotation

        regex_string = self.fields["annotation"].widget.attrs["validation_regex"]
        if regex_string:
            regex = re.compile(regex_string)
            match = regex.fullmatch(annotation)
            if match is None:
                raise ValidationError(_("Invalid format, please refer to the instructions."))

        return annotation


class ElementsAnnotateForm(forms.ModelForm):
    required_css_class = REQUIRED_CSS_CLASS

    polygon = forms.JSONField(
        widget=forms.HiddenInput(),
        required=True,
        validators=[validate_polygon],
    )
    element_type = forms.ChoiceField(
        widget=forms.HiddenInput(),
        required=True,
        choices=[],
    )

    class Meta:
        model = Task
        fields = ("polygon", "element_type")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["element_type"].choices = [
            (str(element_type), str(element_type))
            for element_type in self.instance.campaign.configuration.get(
                "element_types", self.instance.campaign.project.types.filter(folder=False).values_list("id", flat=True)
            )
        ]


class OrderedModelMultipleChoiceField(forms.ModelMultipleChoiceField):
    def clean(self, value):
        qs = super().clean(value)
        # Order the list according to the values sent
        return [str(item.id) for item in sorted(qs, key=lambda item: value.index(str(item.id)))]


class ElementGroupAnnotateForm(forms.ModelForm):
    required_css_class = REQUIRED_CSS_CLASS

    elements = OrderedModelMultipleChoiceField(
        widget=forms.MultipleHiddenInput(),
        queryset=None,
        required=True,
    )

    class Meta:
        model = Task
        fields = ("elements",)

    def __init__(self, *args, **kwargs):
        queryset = kwargs.pop("queryset")

        super().__init__(*args, **kwargs)

        self.fields["elements"].queryset = queryset


class CommentCreateForm(forms.Form):
    content = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": _("Type your comment here...")}),
        required=True,
        label="",
    )

    class Meta:
        fields = ("content",)
