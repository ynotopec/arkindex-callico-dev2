import json
import uuid

import pytest

from callico.annotations.models import Annotation, AnnotationState, TaskUser
from callico.projects.forms import (
    ENTITY_TRANSCRIPTION_DISPLAY_CHOICES,
    ENTITY_TRANSCRIPTION_DISPLAY_NEXT_TO_IMAGE,
)
from callico.projects.models import CampaignMode

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("transcription_display", dict(ENTITY_TRANSCRIPTION_DISPLAY_CHOICES).keys())
def test_user_task_details(
    user, contributor, transcription_display, managed_campaign_with_tasks, django_assert_num_queries
):
    managed_campaign_with_tasks.mode = CampaignMode.Entity
    managed_campaign_with_tasks.configuration = {
        "types": [
            {"entity_type": "first_name", "entity_color": "#80def5"},
            {"entity_type": "last_name", "entity_color": "#80def5"},
            {"entity_type": "city", "entity_color": "#80def5"},
            {"entity_type": "birthday", "entity_color": "#80def5"},
        ],
        "transcription_display": transcription_display,
    }
    managed_campaign_with_tasks.save()

    user_task = TaskUser.objects.filter(user=contributor.user, task__campaign_id=managed_campaign_with_tasks.id).first()

    transcription_text = "Emma Charlotte Duerre Watson was born on 15 April 1990 in Paris."
    user_task.task.element.transcription = {"id": str(uuid.uuid4()), "text": transcription_text}
    user_task.task.element.save()

    Annotation.objects.create(
        value={
            "entities": [
                {"entity_type": "first_name", "offset": 0, "length": 21},
                {"entity_type": "city", "offset": 58, "length": 5},
            ]
        },
        version=2,
        user_task=user_task,
        moderator=user.user,
        state=AnnotationState.Validated,
        parent=Annotation.objects.create(
            value={
                "entities": [
                    {"entity_type": "first_name", "offset": 0, "length": 21},
                    {"entity_type": "last_name", "offset": 22, "length": 6},
                ]
            },
            version=1,
            published=True,
            user_task=user_task,
        ),
    )

    with django_assert_num_queries(7):
        response = user.get(user_task.details_url)
    assert response.status_code == 200

    assert response.context["user_task"] == user_task
    assert response.context["labels"] == {
        "first_name": "#80def5",
        "last_name": "#80def5",
        "city": "#80def5",
        "birthday": "#80def5",
    }
    assert response.context["display_image"] == (transcription_display == ENTITY_TRANSCRIPTION_DISPLAY_NEXT_TO_IMAGE)

    assert response.context["annotations"] == [
        {
            "version": 2,
            "published": False,
            "state": {
                "value": AnnotationState.Validated,
                "label": AnnotationState.Validated.label,
            },
            "moderator": user.user,
            "answers": [
                {
                    "label": "",
                    "value": transcription_text,
                    "rtl_oriented": False,
                    "entities": json.dumps(
                        {
                            str(user_task.task.element.id): [
                                {
                                    "length": 21,
                                    "offset": 0,
                                    "entity_type": "first_name",
                                },
                                {
                                    "length": 5,
                                    "offset": 58,
                                    "entity_type": "city",
                                },
                            ]
                        }
                    ),
                }
            ],
        },
        {
            "version": 1,
            "published": True,
            "state": None,
            "moderator": None,
            "answers": [
                {
                    "label": "",
                    "value": transcription_text,
                    "rtl_oriented": False,
                    "entities": json.dumps(
                        {
                            str(user_task.task.element.id): [
                                {
                                    "length": 21,
                                    "offset": 0,
                                    "entity_type": "first_name",
                                },
                                {
                                    "length": 6,
                                    "offset": 22,
                                    "entity_type": "last_name",
                                },
                            ]
                        }
                    ),
                }
            ],
        },
    ]
