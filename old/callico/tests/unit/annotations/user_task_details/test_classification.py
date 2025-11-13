import pytest

from callico.annotations.models import Annotation, AnnotationState, TaskUser
from callico.projects.models import CampaignMode

pytestmark = pytest.mark.django_db


def test_user_task_details(user, contributor, managed_campaign_with_tasks, django_assert_num_queries):
    dog_class = managed_campaign_with_tasks.project.classes.create(name="dog")
    cat_class = managed_campaign_with_tasks.project.classes.create(name="cat")

    managed_campaign_with_tasks.mode = CampaignMode.Classification
    managed_campaign_with_tasks.save()

    user_task = TaskUser.objects.filter(user=contributor.user, task__campaign_id=managed_campaign_with_tasks.id).first()

    Annotation.objects.create(
        value={"classification": str(cat_class.id)},
        version=2,
        user_task=user_task,
        moderator=user.user,
        state=AnnotationState.Validated,
        parent=Annotation.objects.create(
            value={"classification": str(dog_class.id)},
            version=1,
            published=True,
            user_task=user_task,
        ),
    )

    with django_assert_num_queries(9):
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
                    "label": "Class",
                    "value": "Cat",
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
                    "label": "Class",
                    "value": "Dog",
                },
            ],
        },
    ]
