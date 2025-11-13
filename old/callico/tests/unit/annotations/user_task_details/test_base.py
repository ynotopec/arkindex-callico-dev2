import json
import random
import uuid

import pytest
from django.urls import reverse
from pytest_lazy_fixtures import lf as lazy_fixture

from callico.annotations.models import USER_TASK_DETAILS_URL_NAMES, Task, TaskState, TaskUser
from callico.projects.models import CampaignMode, Element

pytestmark = pytest.mark.django_db


def test_user_task_details_anonymous(anonymous, user, arkindex_provider, image, campaign):
    "An anonymous user is redirected to the login page"
    mode, user_task_url_name = random.choice(list(USER_TASK_DETAILS_URL_NAMES.items()))
    campaign.mode = mode
    campaign.save()

    page_type = campaign.project.types.get(name="Page")
    task = Task.objects.create(
        element=Element.objects.create(
            name="Page 1",
            type=page_type,
            project=campaign.project,
            provider=arkindex_provider,
            provider_object_id=str(uuid.uuid4()),
            image=image,
        ),
        campaign=campaign,
    )
    user_task = TaskUser.objects.create(task=task, user=user.user, state=TaskState.Pending)

    details_url = reverse(user_task_url_name, kwargs={"pk": user_task.id})
    response = anonymous.get(details_url)
    assert response.status_code == 302
    assert response.url == reverse("login") + f"?next={details_url}"


@pytest.mark.parametrize("client", [lazy_fixture("user"), lazy_fixture("contributor")])
@pytest.mark.parametrize(
    "forbidden_campaign",
    [
        # Hidden campaign
        lazy_fixture("hidden_campaign"),
        # Public campaign
        lazy_fixture("public_campaign"),
        # Contributor rights on campaign project
        lazy_fixture("campaign"),
    ],
)
def test_user_task_details_forbidden(client, arkindex_provider, image, forbidden_campaign):
    mode, user_task_url_name = random.choice(list(USER_TASK_DETAILS_URL_NAMES.items()))
    forbidden_campaign.mode = mode
    forbidden_campaign.save()

    page_type, _created = forbidden_campaign.project.types.get_or_create(name="Page")
    task = Task.objects.create(
        element=Element.objects.create(
            name="Page 1",
            type=page_type,
            project=forbidden_campaign.project,
            provider=arkindex_provider,
            provider_object_id=str(uuid.uuid4()),
            image=image,
        ),
        campaign=forbidden_campaign,
    )
    user_task = TaskUser.objects.create(task=task, user=client.user, state=TaskState.Pending)

    response = client.get(reverse(user_task_url_name, kwargs={"pk": user_task.id}))
    assert response.status_code == 403


def test_user_task_details_archived_campaign(user, arkindex_provider, image, archived_campaign):
    mode, user_task_url_name = random.choice(list(USER_TASK_DETAILS_URL_NAMES.items()))
    archived_campaign.mode = mode
    archived_campaign.save()

    page_type, _created = archived_campaign.project.types.get_or_create(name="Page")
    task = Task.objects.create(
        element=Element.objects.create(
            name="Page 1",
            type=page_type,
            project=archived_campaign.project,
            provider=arkindex_provider,
            provider_object_id=str(uuid.uuid4()),
            image=image,
        ),
        campaign=archived_campaign,
    )
    user_task = TaskUser.objects.create(task=task, user=user.user, state=TaskState.Pending)

    response = user.get(reverse(user_task_url_name, kwargs={"pk": user_task.id}))
    assert response.status_code == 403
    assert str(response.context["error_message"]) == "You cannot view the details of a campaign marked as Archived"


def test_user_task_details_wrong_user_task_id(user):
    user_task_url_name = random.choice(list(USER_TASK_DETAILS_URL_NAMES.values()))
    response = user.get(reverse(user_task_url_name, kwargs={"pk": "cafecafe-cafe-cafe-cafe-cafecafecafe"}))
    assert response.status_code == 404
    assert response.context["exception"] == "No user task matching this ID exists"


@pytest.mark.parametrize("with_context_ancestor", [True, False])
def test_user_task_details_get_common_context(user, with_context_ancestor, contributor, managed_campaign_with_tasks):
    parent = managed_campaign_with_tasks.project.elements.filter(image__isnull=False).first()
    child = Element.objects.create(
        name="Line 1",
        type=parent.project.types.get(name="Line"),
        parent=parent,
        project=parent.project,
        provider=parent.project.provider,
        provider_object_id=str(uuid.uuid4()),
        image=parent.image,
        polygon=[[1, 2], [2, 3], [3, 4]],
        order=0,
    )
    task = managed_campaign_with_tasks.tasks.create(element=child)
    user_task = task.user_tasks.create(user=contributor.user, state=TaskState.Pending)

    FILTERED_USER_TASK_DETAILS_URL_NAMES = [
        (mode, user_task_url_name)
        for mode, user_task_url_name in USER_TASK_DETAILS_URL_NAMES.items()
        if mode not in [CampaignMode.Transcription, CampaignMode.ElementGroup]
    ]
    mode, user_task_url_name = random.choice(FILTERED_USER_TASK_DETAILS_URL_NAMES)
    managed_campaign_with_tasks.mode = mode
    if with_context_ancestor:
        managed_campaign_with_tasks.configuration = {"context_type": str(parent.type.id)}
    managed_campaign_with_tasks.save()

    response = user.get(reverse(user_task_url_name, kwargs={"pk": user_task.id}))
    assert response.status_code == 200
    assert response.context["user_task"] == user_task

    if with_context_ancestor:
        assert (
            response.context["help_text"]
            == 'The annotated element is highlighted in green, currently displayed in the context of its first ancestor of type "Page".'
        )
        assert json.loads(response.context["element"]) == parent.serialize_frontend()
        assert json.loads(response.context["children"]) == [child.serialize_frontend()]
    else:
        assert "help_text" not in response.context
        assert json.loads(response.context["element"]) == child.serialize_frontend()
        assert json.loads(response.context["children"]) == []
