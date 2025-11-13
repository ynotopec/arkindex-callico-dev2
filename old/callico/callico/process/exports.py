# -*- coding: utf-8 -*-
import logging
from urllib.parse import urljoin

from django.conf import settings
from django.db.models import Sum

from callico.process.utils import get_entity_display_string
from callico.projects.models import CampaignMode, Class
from callico.projects.utils import flatten_campaign_fields

SIMPLE_EXPORT_MODE_MAPPING = {
    CampaignMode.Entity: "entities",
    CampaignMode.ElementGroup: "groups",
    CampaignMode.Elements: "elements",
}


def create_table_header(campaign):
    """
    Returns a list of strings which could compose a table header in CSV and XLSX exports.
    """
    if campaign.mode == CampaignMode.Transcription:
        extra_data = extra_columns = ["transcriptions"]
    elif campaign.mode == CampaignMode.EntityForm:
        extra_data = [
            (field["entity_type"], field["instruction"], group) for group, field in flatten_campaign_fields(campaign)
        ]
        extra_columns = map(lambda data: get_entity_display_string(*data), extra_data)
    elif campaign.mode == CampaignMode.Classification:
        extra_data = extra_columns = ["ml_class_callico_id", "ml_class_provider_id", "ml_class_name"]
    else:
        extra_data = extra_columns = [f"number_of_annotated_{SIMPLE_EXPORT_MODE_MAPPING[campaign.mode]}"]

    return [
        "id",
        "state",
        "annotator_email",
        "created",
        "completion_time_in_seconds",
        "number_of_comments",
        "callico_task_url",
        "provider_element_url",
        "iiif_url",
        "element_thumbnail_url",
        *extra_columns,
    ], extra_data


def create_table_row(process, campaign, user_task, extra_data):
    """
    Returns a list of various typed values from a TaskUser object which could compose a table line
    in CSV and XLSX exports. All values are serializable to text.
    """
    duration_sum = user_task.annotations.aggregate(Sum("duration"))["duration__sum"]
    values = [
        str(user_task.id),
        user_task.get_state_display(),
        user_task.user.email,
        user_task.created,
        duration_sum.seconds if duration_sum else None,
        user_task.task.comments.count(),
        urljoin(settings.INSTANCE_URL, user_task.annotate_url),
        user_task.task.element.provider_url,
        user_task.task.element.image.iiif_url if user_task.task.element.image else None,
        user_task.task.element.build_thumbnail(size_max_height=1600) if user_task.task.element.image else None,
    ]

    last_annotation = user_task.annotations.order_by("-version").first()
    if campaign.mode == CampaignMode.Transcription:
        transcriptions = last_annotation.value["transcription"]

        # Order value according to the children order
        element_ids = [str(user_task.task.element.id)] + [
            str(child_id) for child_id in user_task.task.element.all_children().values_list("id", flat=True)
        ]
        ordered_transcriptions = [
            transcriptions[element_id] for element_id in element_ids if element_id in transcriptions
        ]

        missing_elements = len(transcriptions) - len(ordered_transcriptions)
        if missing_elements:
            process.add_log(
                f"{missing_elements} annotations are associated with an element that no longer exists", logging.WARNING
            )

        values.append(
            "\n".join([transcription["text"] for transcription in ordered_transcriptions if transcription.get("text")])
        )
    elif campaign.mode == CampaignMode.EntityForm:
        values += [
            next(
                (
                    field["value"]
                    for field in last_annotation.value["values"]
                    if field["entity_type"] == entity_type and field["instruction"] == entity_instr
                ),
                None,
            )
            for (entity_type, entity_instr, _group) in extra_data
        ]
    elif campaign.mode == CampaignMode.Classification:
        ml_class_callico_id = last_annotation.value["classification"]

        try:
            ml_class = campaign.project.classes.get(id=ml_class_callico_id)
            ml_class_provider_id = ml_class.provider_object_id
            ml_class_name = ml_class.name
        except Class.DoesNotExist:
            ml_class_provider_id = None
            ml_class_name = None

        values += [ml_class_callico_id, ml_class_provider_id, ml_class_name]
    else:
        # Some annotations are too complex to be represented in CSV/XLSX format,
        # so we choose to export only the total number of annotated items for each task.
        values.append(len(last_annotation.value[SIMPLE_EXPORT_MODE_MAPPING[campaign.mode]]))

    return values
