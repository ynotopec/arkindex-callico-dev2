import json

from django.forms import formset_factory
from django.utils.functional import cached_property

from callico.annotations.forms import ElementGroupAnnotateForm
from callico.annotations.views import (
    BaseTaskUserAnnotate,
    BaseTaskUserDetails,
    BaseTaskUserManage,
    BaseTaskUserModerate,
    get_carousel_context_parameters,
    get_carousel_element_ids,
)
from callico.projects.models import Element, Type


def get_element_group_manager_context_parameters(task):
    params = {}

    group_type_id = task.campaign.configuration.get("group_type")
    group_type = Type.objects.filter(id=group_type_id).first()
    if group_type:
        params["group_type"] = group_type.name

    return params


class ElementGroupTaskUserDetails(BaseTaskUserDetails):
    template_name = "user_task_details_element_group.html"

    def get_formatted_annotation(self, annotation):
        formatted_annotation = super().get_formatted_annotation(annotation)
        formatted_annotation["answers"] = [
            {
                "label": "",
                "value": json.dumps(annotation.value["groups"]),
            }
        ]
        return formatted_annotation

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        carousel_params = get_carousel_context_parameters(self.task)
        context.update(carousel_params)

        element_group_manager_params = get_element_group_manager_context_parameters(self.task)
        context.update(element_group_manager_params)

        return context


class ElementGroupTaskUserManage(BaseTaskUserManage):
    form_class = ElementGroupAnnotateForm
    template_name = "user_task_manage_element_group.html"

    @cached_property
    def carousel_element_ids(self):
        return get_carousel_element_ids(self.object.task)

    def get_allowed_elements_queryset(self):
        return Element.objects.filter(parent_id__in=self.carousel_element_ids)

    def get_form(self, form_class=None):
        if not form_class:
            form_class = self.get_form_class()

        formset_args = {"data": self.request.POST} if self.request.POST else {}
        ElementGroupFormSet = formset_factory(form_class, extra=0)
        formset = ElementGroupFormSet(**formset_args, form_kwargs=self.get_form_kwargs())

        return formset

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        # To use empty_form, we should not provide a prefix
        del kwargs["prefix"]
        # Retrieve the queryset once to avoid duplicating queries
        kwargs["queryset"] = self.get_allowed_elements_queryset()
        return kwargs

    def get_value(self, form):
        # Filter the subforms because a formset without input will create an empty dictionary
        # This happens when a group is deleted to keep the synchronization between ID and list index
        return {"groups": [subform.cleaned_data for subform in form if subform.cleaned_data]}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["interactive_mode"] = "select"

        carousel_params = get_carousel_context_parameters(self.object.task, self.carousel_element_ids)
        context.update(carousel_params)

        element_group_manager_params = get_element_group_manager_context_parameters(self.object.task)
        context.update(element_group_manager_params)

        allowed_uuids = self.get_allowed_elements_queryset().values_list("id", flat=True)
        allowed_ids = [str(element_id) for element_id in allowed_uuids]

        groups = self.parent.value.get("groups", []) if self.parent else []
        groups = [
            {
                **group,
                # Remove invalid elements to avoid form errors
                # This can happen if the configuration has changed
                "elements": [element_id for element_id in group["elements"] if element_id in allowed_ids],
            }
            for group in groups
        ]
        context["previous_groups"] = groups

        return context


class ElementGroupTaskUserAnnotate(ElementGroupTaskUserManage, BaseTaskUserAnnotate):
    pass


class ElementGroupTaskUserModerate(ElementGroupTaskUserManage, BaseTaskUserModerate):
    pass
