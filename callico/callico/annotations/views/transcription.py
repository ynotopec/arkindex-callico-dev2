from django.forms import BooleanField, HiddenInput, formset_factory
from django.utils.translation import gettext as _

from callico.annotations.views import (
    BaseTaskUserAnnotate,
    BaseTaskUserDetails,
    BaseTaskUserManage,
    BaseTaskUserModerate,
)
from callico.projects.models import Element, TextOrientation


class TranscriptionTaskUserDetails(BaseTaskUserDetails):
    template_name = "user_task_details_transcription.html"

    def get_children(self):
        children = self.task.element.all_children()
        children_types = self.task.campaign.configuration.get("children_types")
        if children_types is not None:
            children = children.filter(type_id__in=children_types)
        return list(children)

    def preprocess_answers(self):
        # Retrieve all elements in a single query to display their names
        self.configuration_elements = [self.task.element] + self.children
        self.configuration_element_ids = [str(elt.id) for elt in self.configuration_elements]

        # The annotated elements may differ if the configuration has changed
        element_ids = [
            element_id
            for annotation in self.object.annotations.all()
            for element_id in annotation.value["transcription"].keys()
        ]
        all_elements = (
            Element.objects.filter(id__in=element_ids)
            if set(element_ids).difference(set(self.configuration_element_ids))
            else self.configuration_elements
        )
        self.elements = {str(element.id): element for element in all_elements}

    def get_formatted_annotation(self, annotation):
        transcription = annotation.value["transcription"]

        formatted_annotation = super().get_formatted_annotation(annotation)
        formatted_annotation["answers"] = [
            {
                "label": _('Annotation on element "%(element)s"') % {"element": element},
                "value": transcription[str(element.id)]["text"],
                "uncertain": transcription[str(element.id)].get("uncertain", False),
                "element_id": str(element.id),
                "rtl_oriented": element.text_orientation == TextOrientation.RightToLeft,
            }
            # Browse through the elements filtered by the configuration to keep the display order
            for element in self.configuration_elements
            if str(element.id) in transcription.keys()
        ]

        # Browse through the missing elements because the configuration may have changed
        if len(formatted_annotation["answers"]) != len(transcription):
            formatted_annotation["answers"].extend(
                [
                    {
                        "label": _('Annotation on element "%(element)s"') % {"element": self.elements[element_id]}
                        if element_id in self.elements
                        else _("Annotation"),
                        "value": value["text"],
                        "uncertain": value.get("uncertain", False),
                        "element_id": element_id,
                        "rtl_oriented": self.elements[element_id].text_orientation == TextOrientation.RightToLeft
                        if element_id in self.elements
                        else False,
                    }
                    for element_id, value in transcription.items()
                    if element_id not in self.configuration_element_ids
                ]
            )

        return formatted_annotation

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["interactive_mode"] = "select"
        return context


class TranscriptionTaskUserManage(BaseTaskUserManage):
    template_name = "user_task_manage_transcription.html"

    def get_initial_value(self, element):
        # Pre-fill annotation
        if self.parent:
            previous_value = self.parent.value.get("transcription", {}).get(str(element.id), {})
            return {"annotation": previous_value.get("text"), "uncertain": previous_value.get("uncertain", False)}

        # If nothing has already been annotated and the element holds a transcription
        # imported from the provider, then we pre-fill the input with it
        if element.transcription.get("id"):
            return {"annotation": element.transcription["text"], "uncertain": False}

        return {"annotation": None, "uncertain": False}

    def get_form(self, form_class=None):
        if not form_class:
            form_class = self.get_form_class()

        self.all_children = self.object.task.element.all_children().select_related("type")
        children_types = self.object.task.campaign.configuration.get("children_types")
        if children_types is not None:
            self.all_children = self.all_children.filter(type_id__in=children_types)
        self.all_children = list(self.all_children)

        elements = self.all_children.copy()
        if children_types is None or str(self.object.task.element.type_id) in children_types:
            elements.insert(0, self.object.task.element)

        # Bound the form on GET requests to allow us to add errors when the confidence is too low
        formset_args = (
            {"data": self.request.POST}
            if self.request.POST
            else {
                "data": {
                    "form-TOTAL_FORMS": len(elements),
                    "form-INITIAL_FORMS": len(elements),
                    **{
                        f"form-{i}-{key}": value
                        for i, element in enumerate(elements)
                        for key, value in self.get_initial_value(element).items()
                    },
                }
            }
        )
        TranscriptionFormSet = formset_factory(form_class, extra=0)
        formset = TranscriptionFormSet(**formset_args)

        light_display = self.object.task.campaign.configuration.get("display_grouped_inputs", False)

        for form, element in zip(formset, elements):
            form.fields["annotation"].label = _('Annotation on element "%(element)s"') % {"element": element}
            form.fields["annotation"].widget.attrs["id"] = str(element.id)
            form.fields["annotation"].widget.attrs["rows"] = 2

            if light_display:
                form.fields["annotation"].widget.attrs["hidden-label"] = form.fields["annotation"].label
                form.fields["annotation"].label = ""
                form.fields["annotation"].widget.attrs["rows"] = 1
                form.fields["annotation"].widget.attrs["class"] = (
                    form.fields["annotation"].widget.attrs.get("class", "") + " light-input"
                )

            # Orient the annotation input according to the text orientation on the element
            if element.text_orientation == TextOrientation.RightToLeft:
                form.fields["annotation"].widget.attrs["class"] = (
                    form.fields["annotation"].widget.attrs.get("class", "") + " rtl-text"
                )

            form.fields["annotation"].widget.attrs["class"] = (
                form.fields["annotation"].widget.attrs.get("class", "") + " annotation-field"
            )
            form.fields["uncertain"] = BooleanField(widget=HiddenInput(), required=False, initial=False)

            # Display transcription confidence
            if not self.parent:
                confidence_threshold = self.object.task.campaign.configuration.get("confidence_threshold")
                imported_transcription_confidence = element.transcription.get("confidence")

                if confidence_threshold is not None and imported_transcription_confidence is not None:
                    # Always display the transcription confidence
                    form.fields["annotation"].widget.attrs["confidence"] = imported_transcription_confidence * 100

                    if imported_transcription_confidence < confidence_threshold:
                        form.fields["annotation"].widget.attrs["low_confidence"] = True
                        if not self.request.POST:
                            # Set the "cleaned_data" attribute
                            form.is_valid()
                            form.add_error("annotation", "")

        return formset

    def get_value(self, form):
        return {
            "transcription": {
                subform.fields["annotation"].widget.attrs["id"]: {
                    "text": subform.cleaned_data.get("annotation"),
                    "uncertain": subform.cleaned_data.get("uncertain"),
                }
                for subform in form
            }
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["interactive_mode"] = "select"

        # Useful for the "display_grouped_inputs" mode
        context["light_display"] = self.object.task.campaign.configuration.get("display_grouped_inputs", False)

        return context


class TranscriptionTaskUserAnnotate(TranscriptionTaskUserManage, BaseTaskUserAnnotate):
    pass


class TranscriptionTaskUserModerate(TranscriptionTaskUserManage, BaseTaskUserModerate):
    pass
