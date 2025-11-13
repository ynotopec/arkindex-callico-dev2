import json
import uuid

import pytest

from callico.annotations.models import Annotation, AnnotationState, TaskUser
from callico.projects.models import CampaignMode, Element

pytestmark = pytest.mark.django_db


def test_user_task_details(user, contributor, managed_campaign_with_tasks, django_assert_num_queries):
    page = managed_campaign_with_tasks.project.types.get(name="Page")
    paragraph = managed_campaign_with_tasks.project.types.create(name="Paragraph")
    managed_campaign_with_tasks.mode = CampaignMode.ElementGroup
    managed_campaign_with_tasks.configuration = {"carousel_type": str(page.id), "group_type": str(paragraph.id)}
    managed_campaign_with_tasks.save()

    user_task = TaskUser.objects.filter(
        user=contributor.user, task__campaign_id=managed_campaign_with_tasks.id, task__element__parent_id__isnull=False
    ).first()
    element = user_task.task.element
    user_task.task.element = user_task.task.element.parent
    user_task.task.save()

    lines = Element.objects.bulk_create(
        Element(
            name=f"Line {i}",
            type=element.project.types.get(name="Line"),
            parent=element,
            project=element.project,
            provider=element.provider,
            provider_object_id=str(uuid.uuid4()),
            image=element.image,
            polygon=[[i, i], [i + 1, i + 1], [i + 2, i + 2]],
            order=i + 3,
        )
        for i in range(1, 5)
    )
    line_ids = [str(line.id) for line in lines]

    Annotation.objects.create(
        value={
            "groups": [
                {"elements": line_ids[:2]},
                {"elements": line_ids[2:4]},
                {"elements": line_ids[3:]},
            ]
        },
        version=2,
        user_task=user_task,
        moderator=user.user,
        state=AnnotationState.Validated,
        parent=Annotation.objects.create(
            value={
                "groups": [
                    {"elements": line_ids[:4]},
                ]
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
    assert response.context["carousel_type"] == page.name
    assert response.context["carousel_element_ids"] == json.dumps(
        [
            str(element_id)
            for element_id in user_task.task.element.all_children().filter(type=page).values_list("id", flat=True)
        ]
    )
    assert response.context["group_type"] == paragraph.name

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
                            {"elements": line_ids[:2]},
                            {"elements": line_ids[2:4]},
                            {"elements": line_ids[3:]},
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
                            {"elements": line_ids[:4]},
                        ]
                    ),
                }
            ],
        },
    ]
