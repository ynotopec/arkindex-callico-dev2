import pytest
from django.urls import reverse
from pytest_lazy_fixtures import lf as lazy_fixture

from callico.annotations.models import TaskState, TaskUser
from callico.projects.models import CAMPAIGN_CLOSED_STATES, CampaignState

pytestmark = pytest.mark.django_db


def test_publish_draft_tasks_anonymous(anonymous, campaign):
    "An anonymous user is redirected to the login page"
    publish_url = reverse("tasks-publish", kwargs={"pk": campaign.id})
    response = anonymous.post(publish_url)
    assert response.status_code == 302
    assert response.url == reverse("login") + f"?next={publish_url}"


@pytest.mark.parametrize(
    "forbidden_campaign",
    [
        # Hidden campaign
        lazy_fixture("hidden_campaign"),
        # Public campaign
        lazy_fixture("public_campaign"),
        # Contributor rights on campaign project
        lazy_fixture("campaign"),
        # Moderator rights on campaign project
        lazy_fixture("moderated_campaign"),
    ],
)
def test_publish_draft_tasks_forbidden(user, forbidden_campaign):
    response = user.post(reverse("tasks-publish", kwargs={"pk": forbidden_campaign.id}))
    assert response.status_code == 403


@pytest.mark.parametrize("state", CAMPAIGN_CLOSED_STATES)
def test_publish_draft_tasks_closed_campaign(user, state, managed_campaign):
    managed_campaign.state = state
    managed_campaign.save()
    response = user.post(reverse("tasks-publish", kwargs={"pk": managed_campaign.id}))
    assert response.status_code == 403
    assert (
        str(response.context["error_message"])
        == f"You cannot publish draft tasks for a campaign marked as {state.capitalize()}"
    )


def test_publish_draft_tasks_wrong_id(user):
    response = user.post(reverse("tasks-publish", kwargs={"pk": "cafecafe-cafe-cafe-cafe-cafecafecafe"}))
    assert response.status_code == 404
    assert response.context["exception"] == "No campaign matching this ID exists"


def test_publish_draft_tasks(
    mocker,
    user,
    managed_campaign_with_tasks,
    django_assert_num_queries,
):
    celery_mock = mocker.patch("callico.users.tasks.send_email.delay")

    assert managed_campaign_with_tasks.state == CampaignState.Created

    draft_tasks = TaskUser.objects.filter(task__campaign=managed_campaign_with_tasks, state=TaskState.Draft)
    draft_count = draft_tasks.count()
    old_pending_count = TaskUser.objects.filter(
        task__campaign=managed_campaign_with_tasks, state=TaskState.Pending
    ).count()
    assert draft_tasks.exists()

    with django_assert_num_queries(7):
        response = user.post(reverse("tasks-publish", kwargs={"pk": managed_campaign_with_tasks.id}))

    managed_campaign_with_tasks.refresh_from_db()
    assert response.status_code == 302
    assert managed_campaign_with_tasks.state == CampaignState.Running

    assert not draft_tasks.exists()
    assert (
        TaskUser.objects.filter(task__campaign=managed_campaign_with_tasks, state=TaskState.Pending).count()
        == old_pending_count + draft_count
    )

    assert celery_mock.call_count == 2
    assert response.url == reverse("admin-campaign-task-list", kwargs={"pk": managed_campaign_with_tasks.id})
