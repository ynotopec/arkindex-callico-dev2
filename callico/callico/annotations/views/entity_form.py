from django.forms import BooleanField, HiddenInput, Select, TextInput, formset_factory

from callico.annotations.forms import EntityFormAnnotateForm
from callico.annotations.views import (
    BaseTaskUserAnnotate,
    BaseTaskUserDetails,
    BaseTaskUserManage,
    BaseTaskUserModerate,
)
from callico.projects.forms import EMPTY_CHOICE
from callico.projects.models import TextOrientation
from callico.projects.utils import flatten_campaign_fields


class EntityFormTaskUserDetails(BaseTaskUserDetails):
    template_name = "user_task_details_entity_form.html"

    def get_formatted_annotation(self, annotation):
        formatted_annotation = super().get_formatted_annotation(annotation)

        # Sorting annotated values from currently configured fields
        values = annotation.value["values"]
        sorted_values = []
        for group, field in flatten_campaign_fields(self.object.task.campaign):
            index = next(
                (
                    index
                    for index, value in enumerate(values)
                    if value["entity_type"] == field["entity_type"] and value["instruction"] == field["instruction"]
                ),
                None,
            )
            if index is not None:
                sorted_values.append((group, values.pop(index)))

        # Some values might not be associated to configured fields anymore, so we add them all at the end of the list
        sorted_values += [("", value) for value in values]

        formatted_annotation["answers"] = [
            {
                "label": field["instruction"],
                "value": field["value"],
                "group": group,
                "uncertain": field.get("uncertain", False),
                "rtl_oriented": self.task.element.text_orientation == TextOrientation.RightToLeft,
            }
            for group, field in sorted_values
        ]
        return formatted_annotation


class EntityFormTaskUserManage(BaseTaskUserManage):
    form_class = EntityFormAnnotateForm
    template_name = "user_task_manage_entity_form.html"

    def get_entity_attr(self, field, attr):
        return [
            entity[attr]
            for entity in filter(
                lambda entity: entity["type"] == field["entity_type"],
                self.object.task.element.entities,
            )
        ]

    def get_initial_value(self, field):
        # Pre-fill annotation
        if self.parent:
            previous_value = next(
                filter(
                    lambda value: value["entity_type"] == field["entity_type"]
                    and value["instruction"] == field["instruction"],
                    self.parent.value.get("values", []),
                ),
                {},
            )
            return {"annotation": previous_value.get("value"), "uncertain": previous_value.get("uncertain", False)}

        # If nothing has already been annotated and the element holds entities
        # imported from the provider, then we pre-fill the input with it
        if self.object.task.element.entities:
            return {"annotation": " ".join(self.get_entity_attr(field, "name")), "uncertain": False}

        return {"annotation": None, "uncertain": False}

    def get_form(self, form_class=None):
        if not form_class:
            form_class = self.get_form_class()

        flattened_fields = flatten_campaign_fields(self.object.task.campaign)

        # Bound the form on GET requests to allow us to add errors when the confidence is too low
        formset_args = (
            {"data": self.request.POST}
            if self.request.POST
            else {
                "data": {
                    "form-TOTAL_FORMS": len(flattened_fields),
                    "form-INITIAL_FORMS": len(flattened_fields),
                    **{
                        f"form-{i}-{key}": value
                        for i, (_group, field) in enumerate(flattened_fields)
                        for key, value in self.get_initial_value(field).items()
                    },
                }
            }
        )
        EntityFormFormSet = formset_factory(form_class, extra=0)
        formset = EntityFormFormSet(**formset_args)

        for form, (group, field) in zip(formset, flattened_fields):
            form.fields["annotation"].label = field["instruction"]

            if field.get("predefined_choices"):
                raw_choices = [raw_choice.strip() for raw_choice in field["predefined_choices"].split(",")]
                choices = [EMPTY_CHOICE] + [(choice, choice.capitalize()) for choice in raw_choices]

                form.fields["annotation"].widget = Select(choices=choices)
                form.fields["annotation"].widget.attrs["class"] = (
                    form.fields["annotation"].widget.attrs.get("class", "") + " truncate-long-words"
                )
                form.fields["annotation"].widget.attrs["style"] = "width: 100%;"
            elif from_authority := field.get("from_authority"):
                form.fields["annotation"].widget = TextInput()
                form.fields["annotation"].widget.attrs["authority_id"] = from_authority
            else:
                form.fields["annotation"].widget.attrs["rows"] = 1

                # Orient the annotation input according to the text orientation on the element
                if self.object.task.element.text_orientation == TextOrientation.RightToLeft:
                    form.fields["annotation"].widget.attrs["class"] = (
                        form.fields["annotation"].widget.attrs.get("class", "") + " rtl-text"
                    )

            form.fields["annotation"].widget.attrs["entity_type"] = field["entity_type"]
            form.fields["annotation"].widget.attrs["instruction"] = field["instruction"]
            form.fields["annotation"].widget.attrs["group"] = group
            form.fields["annotation"].widget.attrs["help_text"] = field.get("help_text", "")
            form.fields["annotation"].widget.attrs["validation_regex"] = field.get("validation_regex", "")

            form.fields["annotation"].widget.attrs["class"] = (
                form.fields["annotation"].widget.attrs.get("class", "") + " annotation-field"
            )
            form.fields["uncertain"] = BooleanField(widget=HiddenInput(), required=False, initial=False)

            # Display entity confidence
            if not self.parent:
                confidence_threshold = field.get("confidence_threshold")

                imported_entity_confidence = None
                confidences = self.get_entity_attr(field, "confidence")
                if confidences:
                    imported_entity_confidence = sum(confidences) / len(confidences)

                if confidence_threshold is not None and imported_entity_confidence is not None:
                    # Always display the entity confidence
                    form.fields["annotation"].widget.attrs["confidence"] = imported_entity_confidence * 100

                    if imported_entity_confidence < confidence_threshold:
                        form.fields["annotation"].widget.attrs["low_confidence"] = True
                        if not self.request.POST:
                            # Set the "cleaned_data" attribute
                            form.is_valid()
                            form.add_error("annotation", "")

        return formset

    def get_value(self, form):
        return {
            "values": [
                {
                    "entity_type": subform.fields["annotation"].widget.attrs["entity_type"],
                    "instruction": subform.fields["annotation"].label,
                    "value": subform.cleaned_data.get("annotation"),
                    "uncertain": subform.cleaned_data.get("uncertain"),
                }
                for subform in form
            ]
        }


class EntityFormTaskUserAnnotate(EntityFormTaskUserManage, BaseTaskUserAnnotate):
    pass


class EntityFormTaskUserModerate(EntityFormTaskUserManage, BaseTaskUserModerate):
    pass
