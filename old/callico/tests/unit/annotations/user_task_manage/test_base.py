import json
import random
import uuid

import pytest
from django.urls import reverse

from callico.annotations.models import (
    USER_TASK_ANNOTATE_URL_NAMES,
    USER_TASK_MODERATE_URL_NAMES,
    Task,
    TaskState,
    TaskUser,
)
from callico.projects.models import CAMPAIGN_CLOSED_STATES, CampaignMode, Element, Role

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "mode, user_task_url_name",
    [
        random.choice(list(USER_TASK_ANNOTATE_URL_NAMES.items())),
        random.choice(list(USER_TASK_MODERATE_URL_NAMES.items())),
    ],
)
def test_user_task_manage_anonymous(mode, user_task_url_name, anonymous, managed_campaign_with_tasks):
    "An anonymous user is redirected to the login page"
    managed_campaign_with_tasks.mode = mode
    managed_campaign_with_tasks.save()

    user_task = TaskUser.objects.filter(task__campaign_id=managed_campaign_with_tasks.id).first()
    user_task_url = reverse(user_task_url_name, kwargs={"pk": user_task.id})

    response = anonymous.get(user_task_url)
    assert response.status_code == 302
    assert response.url == reverse("login") + f"?next={user_task_url}"


@pytest.mark.parametrize(
    "mode, user_task_url_name",
    [
        random.choice(list(USER_TASK_ANNOTATE_URL_NAMES.items())),
        random.choice(list(USER_TASK_MODERATE_URL_NAMES.items())),
    ],
)
def test_user_task_manage_manager_user_redirection_from_task_id(
    mode, user_task_url_name, user, managed_campaign_with_tasks
):
    """
    Checks backward compatibility with versions ⩽ 0.5.0-post1
    """
    managed_campaign_with_tasks.mode = mode
    managed_campaign_with_tasks.save()

    task = Task.objects.filter(campaign_id=managed_campaign_with_tasks.id).first()
    task.user_tasks.all().delete()

    response = user.get(reverse(user_task_url_name, kwargs={"pk": task.id}))

    assert response.status_code == 302
    assert response.url == reverse("element-details", kwargs={"pk": task.element.id})


@pytest.mark.parametrize(
    "user_task_url_name",
    [
        random.choice(list(USER_TASK_ANNOTATE_URL_NAMES.values())),
        random.choice(list(USER_TASK_MODERATE_URL_NAMES.values())),
    ],
)
def test_user_task_manage_wrong_user_task_id(user_task_url_name, contributor):
    user_task_url = reverse(user_task_url_name, kwargs={"pk": "cafecafe-cafe-cafe-cafe-cafecafecafe"})

    response = contributor.get(user_task_url)
    assert response.status_code == 404
    assert response.context["exception"] == "No user task matching this ID exists"


@pytest.mark.parametrize(
    "mode, user_task_url_name",
    [
        random.choice(list(USER_TASK_ANNOTATE_URL_NAMES.items())),
        random.choice(list(USER_TASK_MODERATE_URL_NAMES.items())),
    ],
)
def test_user_task_manage_non_member_user(mode, user_task_url_name, contributor, managed_campaign_with_tasks):
    managed_campaign_with_tasks.project.memberships.filter(user=contributor.user).delete()
    managed_campaign_with_tasks.mode = mode
    managed_campaign_with_tasks.save()

    user_task = TaskUser.objects.filter(task__campaign_id=managed_campaign_with_tasks.id, user=contributor.user).first()
    user_task_url = reverse(user_task_url_name, kwargs={"pk": user_task.id})

    response = contributor.get(user_task_url)
    assert response.status_code == 403
    assert str(response.context["error_message"]) == "You don't have access to this project"


@pytest.mark.parametrize(
    "mode, user_task_url_name",
    [
        random.choice(list(USER_TASK_ANNOTATE_URL_NAMES.items())),
        random.choice(list(USER_TASK_MODERATE_URL_NAMES.items())),
    ],
)
@pytest.mark.parametrize("state", CAMPAIGN_CLOSED_STATES)
def test_user_task_manage_closed_campaign(mode, user_task_url_name, state, contributor, managed_campaign_with_tasks):
    managed_campaign_with_tasks.mode = mode
    managed_campaign_with_tasks.state = state
    managed_campaign_with_tasks.save()

    user_task = TaskUser.objects.filter(
        task__campaign_id=managed_campaign_with_tasks.id, state=TaskState.Pending, user=contributor.user
    ).first()
    user_task_url = reverse(user_task_url_name, kwargs={"pk": user_task.id})
    action = "annotate" if "annotate" in user_task_url_name else "moderate"

    response = contributor.get(user_task_url)
    assert response.status_code == 403
    assert (
        str(response.context["error_message"])
        == f"You cannot {action} a task for a campaign marked as {user_task.task.campaign.get_state_display()}"
    )


@pytest.mark.parametrize(
    "mode, user_task_url_name",
    [
        random.choice(list(USER_TASK_ANNOTATE_URL_NAMES.items())),
        random.choice(list(USER_TASK_MODERATE_URL_NAMES.items())),
    ],
)
def test_user_task_manage_from_task_id(
    mode, user_task_url_name, contributor, managed_campaign_with_tasks, django_assert_num_queries
):
    """
    Checks backward compatibility with versions ⩽ 0.5.0-post1
    """
    managed_campaign_with_tasks.mode = mode
    managed_campaign_with_tasks.save()

    if "moderate" in user_task_url_name:
        managed_campaign_with_tasks.project.memberships.filter(user=contributor.user).update(role=Role.Moderator)

    user_task = TaskUser.objects.filter(
        task__campaign_id=managed_campaign_with_tasks.id, state=TaskState.Pending, user=contributor.user
    ).first()

    expected_queries = (
        (14 if "annotate" in user_task_url_name else (13 + (mode == CampaignMode.Classification)))
        + (mode == CampaignMode.Transcription)
        + (mode == CampaignMode.ElementGroup) * 2
        + (mode == CampaignMode.Elements) * 3
    )
    with django_assert_num_queries(expected_queries):
        response = contributor.get(reverse(user_task_url_name, kwargs={"pk": user_task.task_id}))

    assert response.status_code == 200
    assert response.context["user_task"] == user_task


@pytest.mark.parametrize("with_context_ancestor", [True, False])
@pytest.mark.parametrize(
    "mode, user_task_url_name",
    [
        random.choice(
            [
                (mode, user_task_url_name)
                for mode, user_task_url_name in USER_TASK_ANNOTATE_URL_NAMES.items()
                if mode not in [CampaignMode.Transcription, CampaignMode.Elements, CampaignMode.ElementGroup]
            ]
        ),
        random.choice(
            [
                (mode, user_task_url_name)
                for mode, user_task_url_name in USER_TASK_MODERATE_URL_NAMES.items()
                if mode not in [CampaignMode.Transcription, CampaignMode.Elements, CampaignMode.ElementGroup]
            ]
        ),
    ],
)
def test_user_task_manage_get_common_context(
    with_context_ancestor, mode, user_task_url_name, contributor, managed_campaign_with_tasks, django_assert_num_queries
):
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

    managed_campaign_with_tasks.mode = mode
    if with_context_ancestor:
        managed_campaign_with_tasks.configuration = {"context_type": str(parent.type.id)}
    managed_campaign_with_tasks.save()

    if "moderate" in user_task_url_name:
        managed_campaign_with_tasks.project.memberships.filter(user=contributor.user).update(role=Role.Moderator)

    expected_queries = (
        12 if "annotate" in user_task_url_name else (11 + (mode == CampaignMode.Classification))
    ) + 4 * with_context_ancestor
    with django_assert_num_queries(expected_queries):
        response = contributor.get(reverse(user_task_url_name, kwargs={"pk": user_task.id}))
    assert response.status_code == 200
    assert response.context["user_task"] == user_task
    assert user_task.annotations.count() == 0

    if with_context_ancestor:
        assert (
            response.context["help_text"]
            == 'The element to annotate is highlighted in green, currently displayed in the context of its first ancestor of type "Page".'
        )
        assert json.loads(response.context["element"]) == parent.serialize_frontend()
        assert json.loads(response.context["children"]) == [child.serialize_frontend()]
    else:
        assert "help_text" not in response.context
        assert json.loads(response.context["element"]) == child.serialize_frontend()
        assert json.loads(response.context["children"]) == []
