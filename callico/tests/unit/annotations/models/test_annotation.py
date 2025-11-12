import re
import uuid

import pytest
from django.core.exceptions import ValidationError

from callico.annotations.models import Annotation, Task, TaskState, TaskUser
from callico.projects.models import CampaignMode

pytestmark = pytest.mark.django_db


def test_parent_not_in_user_task(user, admin, page_element, campaign):
    task = Task.objects.create(element=page_element, campaign=campaign)
    parent = Annotation.objects.create(
        user_task=TaskUser.objects.create(user=admin.user, task=task, state=TaskState.Annotated)
    )
    annotation = Annotation.objects.create(
        parent=parent, user_task=TaskUser.objects.create(user=user.user, task=task, state=TaskState.Annotated)
    )

    assert annotation.user_task != parent.user_task
    with pytest.raises(ValidationError, match=re.escape("{'parent': ['Parent is not part of the same user task']}")):
        annotation.clean()


def test_parent_not_itself(user, page_element, campaign):
    annotation = Annotation.objects.create(
        user_task=TaskUser.objects.create(
            user=user.user, state=TaskState.Annotated, task=Task.objects.create(element=page_element, campaign=campaign)
        )
    )
    Annotation.objects.update(parent=annotation)
    annotation.refresh_from_db()
    with pytest.raises(ValidationError, match=re.escape("{'parent': ['An annotation cannot be its own parent']}")):
        annotation.clean()


def test_version(user, page_element, campaign):
    tasks_user = TaskUser.objects.create(
        user=user.user, state=TaskState.Annotated, task=Task.objects.create(element=page_element, campaign=campaign)
    )
    parent = Annotation.objects.create(user_task=tasks_user, version=42)
    assert parent.version == 1
    annotation = Annotation.objects.create(parent=parent, user_task=tasks_user, version=42)
    assert annotation.version == 2
    annotation = Annotation.objects.create(parent=parent, user_task=tasks_user)
    assert annotation.version == 3

    # Update an annotation should not change its version
    annotation.published = True
    annotation.save()
    assert annotation.version == 3


@pytest.mark.parametrize(
    "mode, value",
    [
        (CampaignMode.Transcription, {"transcription": {str(uuid.uuid4()): {"text": "...", "uncertain": True}}}),
        (
            CampaignMode.EntityForm,
            {
                "values": [
                    {
                        "entity_type": "first_name",
                        "uncertain": True,
                        "instruction": "First name (in the corner)",
                        "value": "Alice",
                    }
                ]
            },
        ),
    ],
)
def test_has_uncertain_value(user, page_element, campaign, mode, value):
    campaign.mode = mode
    campaign.save()

    tasks_user = TaskUser.objects.create(
        user=user.user, state=TaskState.Annotated, task=Task.objects.create(element=page_element, campaign=campaign)
    )

    parent = Annotation.objects.create(user_task=tasks_user)
    assert not tasks_user.has_uncertain_value
    annotation = Annotation.objects.create(parent=parent, user_task=tasks_user)
    assert not tasks_user.has_uncertain_value
    last_annotation = Annotation.objects.create(parent=parent, user_task=tasks_user)
    assert not tasks_user.has_uncertain_value

    # Updating an old annotation should not change the "has_uncertain_value" attribute
    parent.value = value
    parent.save()
    assert not tasks_user.has_uncertain_value
    annotation.value = value
    annotation.save()
    assert not tasks_user.has_uncertain_value

    # Updating the latest annotation should change the "has_uncertain_value" attribute
    last_annotation.value = value
    last_annotation.save()
    assert tasks_user.has_uncertain_value

    last_annotation.value = {}
    last_annotation.save()
    assert not tasks_user.has_uncertain_value
