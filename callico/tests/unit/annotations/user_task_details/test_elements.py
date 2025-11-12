import json

import pytest

from callico.annotations.models import Annotation, AnnotationState, TaskUser
from callico.projects.models import CampaignMode

pytestmark = pytest.mark.django_db


def test_user_task_details(user, contributor, managed_campaign_with_tasks, django_assert_num_queries):
    paragraph = managed_campaign_with_tasks.project.types.create(name="Paragraph")
    line = managed_campaign_with_tasks.project.types.get(name="Line")
    managed_campaign_with_tasks.mode = CampaignMode.Elements
    managed_campaign_with_tasks.configuration = {
        "element_types": [
            str(line.id),
        ]
    }
    managed_campaign_with_tasks.save()

    user_task = TaskUser.objects.filter(user=contributor.user, task__campaign_id=managed_campaign_with_tasks.id).first()

    user_task.task.element.polygon = [[0, 0], [100, 0], [100, 50], [0, 50], [0, 0]]
    user_task.task.element.save()

    Annotation.objects.create(
        value={
            "elements": [
                {"polygon": [[10, 10], [90, 10], [90, 20], [10, 20], [10, 10]], "element_type": str(line.id)},
                {"polygon": [[10, 20], [90, 20], [90, 30], [10, 30], [10, 20]], "element_type": str(line.id)},
                {"polygon": [[10, 30], [90, 30], [90, 40], [10, 40], [10, 30]], "element_type": str(line.id)},
            ]
        },
        version=2,
        user_task=user_task,
        moderator=user.user,
        state=AnnotationState.Validated,
        parent=Annotation.objects.create(
            value={
                "elements": [
                    {"polygon": [[10, 10], [90, 10], [90, 40], [10, 40], [10, 10]], "element_type": str(paragraph.id)},
                ]
            },
            version=1,
            published=True,
            user_task=user_task,
        ),
    )

    with django_assert_num_queries(8):
        response = user.get(user_task.details_url)
    assert response.status_code == 200

    assert response.context["user_task"] == user_task
    assert response.context["element_types"] == [
        {"id": line.id, "name": "Line"},
        {"id": managed_campaign_with_tasks.project.types.get(name="Page").id, "name": "Page"},
        {"id": paragraph.id, "name": "Paragraph"},
    ]
    assert response.context["interactive_mode"] == "select"

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
                    "value": json.dumps(
                        [
                            {
                                "id": 1,
                                "polygon": [[10, 10], [90, 10], [90, 20], [10, 20], [10, 10]],
                                "element_type": str(line.id),
                            },
                            {
                                "id": 2,
                                "polygon": [[10, 20], [90, 20], [90, 30], [10, 30], [10, 20]],
                                "element_type": str(line.id),
                            },
                            {
                                "id": 3,
                                "polygon": [[10, 30], [90, 30], [90, 40], [10, 40], [10, 30]],
                                "element_type": str(line.id),
                            },
                        ]
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
                    "value": json.dumps(
                        [
                            {
                                "id": 1,
                                "polygon": [[10, 10], [90, 10], [90, 40], [10, 40], [10, 10]],
                                "element_type": str(paragraph.id),
                            },
                        ]
                    ),
                }
            ],
        },
    ]
