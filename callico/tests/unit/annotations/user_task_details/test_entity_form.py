import pytest

from callico.annotations.models import Annotation, AnnotationState, TaskUser
from callico.projects.models import CampaignMode

pytestmark = pytest.mark.django_db


def test_user_task_details(user, contributor, managed_campaign_with_tasks, django_assert_num_queries):
    managed_campaign_with_tasks.configuration["fields"] = [
        {"mode": "group", "legend": "Group", "fields": [{"entity_type": "field", "instruction": "Field in group"}]}
    ]
    managed_campaign_with_tasks.mode = CampaignMode.EntityForm
    managed_campaign_with_tasks.save()

    user_task = TaskUser.objects.filter(user=contributor.user, task__campaign_id=managed_campaign_with_tasks.id).first()

    Annotation.objects.create(
        value={
            "values": [
                {"entity_type": "firstname", "instruction": "First name", "value": "Alice"},
                {"entity_type": "lastname", "instruction": "Last name", "value": "Doe", "uncertain": False},
                {"entity_type": "field", "instruction": "Field in group", "value": "My value"},
            ]
        },
        version=2,
        user_task=user_task,
        moderator=user.user,
        state=AnnotationState.Validated,
        parent=Annotation.objects.create(
            value={
                "values": [
                    {"entity_type": "firstname", "instruction": "First name", "value": "Alice"},
                    {"entity_type": "lastname", "instruction": "Last name", "value": "Boo", "uncertain": True},
                    {"entity_type": "field", "instruction": "Field in group", "value": "My value"},
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
                    "label": "Field in group",
                    "value": "My value",
                    "group": "Group",
                    "uncertain": False,
                    "rtl_oriented": False,
                },
                {
                    "label": "First name",
                    "value": "Alice",
                    "group": "",
                    "uncertain": False,
                    "rtl_oriented": False,
                },
                {
                    "label": "Last name",
                    "value": "Doe",
                    "group": "",
                    "uncertain": False,
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
                    "label": "Field in group",
                    "value": "My value",
                    "group": "Group",
                    "uncertain": False,
                    "rtl_oriented": False,
                },
                {
                    "label": "First name",
                    "value": "Alice",
                    "group": "",
                    "uncertain": False,
                    "rtl_oriented": False,
                },
                {
                    "label": "Last name",
                    "value": "Boo",
                    "group": "",
                    "uncertain": True,
                    "rtl_oriented": False,
                },
            ],
        },
    ]
