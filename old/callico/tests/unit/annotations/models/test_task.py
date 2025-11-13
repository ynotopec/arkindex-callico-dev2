import re

import pytest
from django.core.exceptions import ValidationError

from callico.annotations.models import Task, TaskUser
from callico.projects.models import NO_IMAGE_SUPPORTED_CAMPAIGN_MODES, CampaignMode

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("mode", [mode for mode in CampaignMode if mode not in NO_IMAGE_SUPPORTED_CAMPAIGN_MODES])
def test_task_no_image(folder_element, campaign, mode):
    campaign.mode = mode
    campaign.save()

    task = Task.objects.create(element=folder_element, campaign=campaign)
    with pytest.raises(
        ValidationError,
        match=re.escape(
            "{'element': ['You cannot create a task for an element that does not have an image on this type of campaign']}"
        ),
    ):
        task.clean()


def test_task_different_project(hidden_element, campaign):
    task = Task.objects.create(element=hidden_element, campaign=campaign)
    error = {
        "__all__": [
            f"Element is part of project {hidden_element.project} while campaign is for project {campaign.project}"
        ]
    }

    assert hidden_element.project != campaign.project
    with pytest.raises(ValidationError, match=re.escape(str(error))):
        task.clean()


def test_user_task_not_in_project(hidden_element, hidden_campaign, user):
    task = Task.objects.create(element=hidden_element, campaign=hidden_campaign)
    user_task = TaskUser.objects.create(task=task, user=user.user)
    error = {"user": [f"User is not member of the project {hidden_campaign.project}"]}

    with pytest.raises(ValidationError, match=re.escape(str(error))):
        user_task.clean()
