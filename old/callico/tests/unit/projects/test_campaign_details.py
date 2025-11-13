from datetime import timedelta

import pytest
from django.urls import reverse
from pytest_lazy_fixtures import lf as lazy_fixture

from callico.annotations.models import TaskState
from callico.projects.models import CampaignState

pytestmark = pytest.mark.django_db


def test_campaign_details_anonymous(anonymous, campaign):
    "An anonymous user is redirected to the login page"
    details_url = reverse("campaign-details", kwargs={"pk": campaign.id})
    response = anonymous.get(details_url)
    assert response.status_code == 302
    assert response.url == reverse("login") + f"?next={details_url}"


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
def test_campaign_details_forbidden(user, forbidden_campaign):
    response = user.get(reverse("campaign-details", kwargs={"pk": forbidden_campaign.id}))
    assert response.status_code == 403


def test_campaign_details_archived_campaign(user, archived_campaign):
    response = user.get(reverse("campaign-details", kwargs={"pk": archived_campaign.id}))
    assert response.status_code == 403
    assert str(response.context["error_message"]) == "You cannot view the details of a campaign marked as Archived"


def test_campaign_details_wrong_campaign_id(user):
    response = user.get(reverse("campaign-details", kwargs={"pk": "cafecafe-cafe-cafe-cafe-cafecafecafe"}))
    assert response.status_code == 404
    assert response.context["exception"] == "No campaign matching this ID exists"


@pytest.mark.parametrize("state", [state for state in CampaignState if state != CampaignState.Archived])
def test_campaign_details(user, contributor, managed_campaign, state, django_assert_num_queries):
    managed_campaign.state = state
    managed_campaign.save()

    with django_assert_num_queries(10):
        response = user.get(reverse("campaign-details", kwargs={"pk": managed_campaign.id}))
    assert response.status_code == 200

    assert response.context["campaign"] == managed_campaign
    assert response.context["can_manage"] == (user.user != contributor)
    assert response.context["tracked_median"] is None


@pytest.mark.parametrize(
    "times, expected",
    [
        ([1, 4, 2, 3, 1], 2),
        ([10, 100, 10, 10000, 1000, 2000, None], 550),
        ([None, None, 2], 2),
    ],
)
def test_campaign_details_median_completion_time(
    managed_campaign, page_element, user, contributor, django_assert_num_queries, times, expected
):
    """Displays the median time spent annotating tasks on this campaign"""
    task = managed_campaign.tasks.create(element=page_element)
    user_task = task.user_tasks.create(user=contributor.user, state=TaskState.Annotated)
    for index, time in enumerate(times):
        # Create a task and its annotation
        user_task.annotations.create(value={}, version=index, duration=time and timedelta(seconds=time))

    with django_assert_num_queries(10):
        response = user.get(reverse("campaign-details", kwargs={"pk": managed_campaign.id}))
    assert response.status_code == 200
    assert response.context["tracked_median"] == timedelta(seconds=expected)
