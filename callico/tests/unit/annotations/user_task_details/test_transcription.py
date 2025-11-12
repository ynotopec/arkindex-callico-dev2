import uuid

import pytest

from callico.annotations.models import Annotation, AnnotationState, TaskUser
from callico.projects.models import CampaignMode

pytestmark = pytest.mark.django_db


def test_user_task_details(user, contributor, managed_campaign_with_tasks, django_assert_num_queries):
    managed_campaign_with_tasks.mode = CampaignMode.Transcription
    managed_campaign_with_tasks.save()

    user_task = TaskUser.objects.filter(user=contributor.user, task__campaign_id=managed_campaign_with_tasks.id).first()

    random_uuid = str(uuid.uuid4())
    Annotation.objects.create(
        value={
            "transcription": {
                str(user_task.task.element.id): {"text": "Value xxxx"},
                random_uuid: {"text": "Value zzzz", "uncertain": False},
            },
        },
        version=2,
        user_task=user_task,
        moderator=user.user,
        state=AnnotationState.Validated,
        parent=Annotation.objects.create(
            value={
                "transcription": {
                    str(user_task.task.element.id): {"text": "Value x"},
                    random_uuid: {"text": "Value z", "uncertain": True},
                },
            },
            version=1,
            published=True,
            user_task=user_task,
        ),
    )

    with django_assert_num_queries(10):
        response = user.get(user_task.details_url)
    assert response.status_code == 200

    assert response.context["user_task"] == user_task

    # Comparison failed randomly
    annotations = response.context["annotations"]
    for annotation in annotations:
        annotation["answers"] = sorted(annotation["answers"], key=lambda a: a["label"])

    assert annotations == [
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
                    "label": "Annotation",
                    "value": "Value zzzz",
                    "uncertain": False,
                    "element_id": random_uuid,
                    "rtl_oriented": False,
                },
                {
                    "label": f'Annotation on element "{str(user_task.task.element)}"',
                    "value": "Value xxxx",
                    "uncertain": False,
                    "element_id": str(user_task.task.element.id),
                    "rtl_oriented": False,
                },
            ],
        },
        {
            "version": 1,
            "published": True,
            "state": None,
            "moderator": None,
            "answers": [
                {
                    "label": "Annotation",
                    "value": "Value z",
                    "uncertain": True,
                    "element_id": random_uuid,
                    "rtl_oriented": False,
                },
                {
                    "label": f'Annotation on element "{str(user_task.task.element)}"',
                    "value": "Value x",
                    "uncertain": False,
                    "element_id": str(user_task.task.element.id),
                    "rtl_oriented": False,
                },
            ],
        },
    ]
