import json
import random

from django.forms import formset_factory

from callico.annotations.forms import EntityAnnotateForm
from callico.annotations.views import (
    BaseTaskUserAnnotate,
    BaseTaskUserDetails,
    BaseTaskUserManage,
    BaseTaskUserModerate,
)
from callico.projects.forms import ENTITY_TRANSCRIPTION_DISPLAY_NEXT_TO_IMAGE, ENTITY_TRANSCRIPTION_DISPLAY_ONLY
from callico.projects.models import TextOrientation


def random_color():
    return f"#{random.randint(0, 0xFFFFFF):06x}"


def build_labels(campaign):
    return {item["entity_type"]: item["entity_color"] for item in campaign.configuration.get("types", [])}


class EntityTaskUserDetails(BaseTaskUserDetails):
    template_name = "user_task_details_entity.html"

    def preprocess_answers(self):
        self.labels = build_labels(self.task.campaign)

    def get_formatted_annotation(self, annotation):
        formatted_annotation = super().get_formatted_annotation(annotation)
        formatted_annotation["answers"] = [
            {
                "label": "",
                "value": self.task.element.transcription.get("text"),
                "rtl_oriented": self.task.element.text_orientation == TextOrientation.RightToLeft,
                "entities": json.dumps({str(self.task.element.id): annotation.value["entities"]}),
            }
        ]
        return formatted_annotation

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["labels"] = self.labels

        transcription_display = self.task.campaign.configuration.get(
            "transcription_display", ENTITY_TRANSCRIPTION_DISPLAY_ONLY
        )
        context["display_image"] = transcription_display == ENTITY_TRANSCRIPTION_DISPLAY_NEXT_TO_IMAGE

        return context


class EntityTaskUserManage(BaseTaskUserManage):
    form_class = EntityAnnotateForm
    template_name = "user_task_manage_entity.html"

    def get_form(self, form_class=None):
        if not form_class:
            form_class = self.get_form_class()

        formset_args = {"data": self.request.POST} if self.request.POST else {}
        EntityFormSet = formset_factory(form_class, extra=0)
        formset = EntityFormSet(**formset_args, form_kwargs=self.get_form_kwargs())

        return formset

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        # To use empty_form, we should not provide a prefix
        del kwargs["prefix"]
        return kwargs

    def get_value(self, form):
        return {"entities": [subform.cleaned_data for subform in form]}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["labels"] = build_labels(self.object.task.campaign)

        # Remove invalid entities to avoid form errors
        # This can happen if the configuration/transcription has changed
        entities = (
            self.parent.value.get("entities", [])
            if self.parent
            # If nothing has already been annotated and the element holds entities
            # imported from the provider, then we pre-fill the input with it
            else [
                {"entity_type": entity["type"], "offset": entity["offset"], "length": entity["length"]}
                for entity in self.object.task.element.entities
            ]
        )
        entities = [
            entity
            for entity in entities
            if
            (
                # Check if the entity_type exists
                entity["entity_type"] in context["labels"]
                # Check the element holds an imported transcription
                and self.object.task.element.transcription.get("text")
                # Check if the entity is part of the transcription
                and entity["offset"] + entity["length"] <= len(self.object.task.element.transcription["text"])
            )
        ]
        context["previous_entities"] = entities

        transcription_display = self.object.task.campaign.configuration.get(
            "transcription_display", ENTITY_TRANSCRIPTION_DISPLAY_ONLY
        )
        # The transcription should be scrollable
        context["light_display"] = True
        context["display_image"] = transcription_display == ENTITY_TRANSCRIPTION_DISPLAY_NEXT_TO_IMAGE

        context["rtl_oriented_element"] = self.object.task.element.text_orientation == TextOrientation.RightToLeft

        context["full_word_selection"] = json.dumps(
            self.object.task.campaign.configuration.get("full_word_selection", True)
        )

        return context


class EntityTaskUserAnnotate(EntityTaskUserManage, BaseTaskUserAnnotate):
    pass


class EntityTaskUserModerate(EntityTaskUserManage, BaseTaskUserModerate):
    pass
