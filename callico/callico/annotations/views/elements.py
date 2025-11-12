import json

from django.forms import formset_factory

from callico.annotations.forms import ElementsAnnotateForm
from callico.annotations.views import (
    BaseTaskUserAnnotate,
    BaseTaskUserDetails,
    BaseTaskUserManage,
    BaseTaskUserModerate,
)


class ElementsTaskUserDetails(BaseTaskUserDetails):
    template_name = "user_task_details_elements.html"

    def get_formatted_annotation(self, annotation):
        formatted_annotation = super().get_formatted_annotation(annotation)
        formatted_annotation["answers"] = [
            {
                "label": "",
                "value": json.dumps(
                    [{"id": index, **element} for index, element in enumerate(annotation.value["elements"], start=1)]
                ),
            }
        ]
        return formatted_annotation

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Contain all project types since some of the annotated ones could have been removed from the campaign configuration
        context["element_types"] = list(self.task.campaign.project.types.filter(folder=False).values("id", "name"))

        context["interactive_mode"] = "select"

        return context


class ElementsTaskUserManage(BaseTaskUserManage):
    form_class = ElementsAnnotateForm
    template_name = "user_task_manage_elements.html"

    def get_form(self, form_class=None):
        if not form_class:
            form_class = self.get_form_class()

        formset_args = {"data": self.request.POST} if self.request.POST else {}
        ElementsFormSet = formset_factory(form_class, extra=0)
        formset = ElementsFormSet(**formset_args, form_kwargs=self.get_form_kwargs())

        return formset

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        # To use empty_form, we should not provide a prefix
        del kwargs["prefix"]
        return kwargs

    def get_value(self, form):
        # Filter the subforms because a formset without input will create an empty dictionary
        # This happens when an element is deleted to keep the synchronization between ID and list index
        return {"elements": [subform.cleaned_data for subform in form if subform.cleaned_data]}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Associate types stored in the configuration with their name for display
        configured_types = self.object.task.campaign.configuration.get("element_types")
        context["element_types"] = [
            {"id": str(type_id), "name": type_name}
            for type_id, type_name in self.object.task.campaign.project.types.filter(folder=False).values_list(
                "id", "name"
            )
            # If not configured, add all project types, else only the configured ones
            if configured_types is None or str(type_id) in configured_types
        ]

        # Remove invalid elements to avoid form errors
        # This can happen if the configuration has changed
        valid_element_types = [element_type["id"] for element_type in context["element_types"]]

        # Pre-fill annotation
        if self.parent:
            elements = self.parent.value.get("elements", [])
            elements = [element for element in elements if element["element_type"] in valid_element_types]
        # If nothing has already been annotated and the element has children
        # imported from the provider, then we pre-fill the annotation with it
        else:
            elements = self.object.task.element.all_children().filter(type_id__in=valid_element_types)
            elements = [{"polygon": element.polygon, "element_type": str(element.type_id)} for element in elements]

        context["previous_elements"] = elements

        # The frontend will display the elements according to the localStorage
        context["children"] = []

        if context["element_types"]:
            context["interactive_mode"] = "create"

        return context


class ElementsTaskUserAnnotate(ElementsTaskUserManage, BaseTaskUserAnnotate):
    pass


class ElementsTaskUserModerate(ElementsTaskUserManage, BaseTaskUserModerate):
    pass
