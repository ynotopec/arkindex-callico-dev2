import pytest
from django.urls import reverse
from pytest_lazy_fixtures import lf as lazy_fixture

from callico.projects.models import CAMPAIGN_CLOSED_STATES, CampaignState

pytestmark = pytest.mark.django_db


def test_campaign_update_state_anonymous(anonymous, campaign):
    "An anonymous user is redirected to the login page"
    update_url = reverse("campaign-update-state", kwargs={"pk": campaign.id})
    response = anonymous.post(update_url)
    assert response.status_code == 302
    assert response.url == reverse("login") + f"?next={update_url}"


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
def test_campaign_update_state_forbidden(user, forbidden_campaign):
    response = user.post(reverse("campaign-update-state", kwargs={"pk": forbidden_campaign.id}))
    assert response.status_code == 403


def test_campaign_update_state_archived_campaign(user, archived_campaign):
    response = user.post(reverse("campaign-update-state", kwargs={"pk": archived_campaign.id}))
    assert response.status_code == 403
    assert str(response.context["error_message"]) == "You cannot update the state of a campaign marked as Archived"


def test_campaign_update_state_wrong_campaign_id(user):
    response = user.post(reverse("campaign-update-state", kwargs={"pk": "cafecafe-cafe-cafe-cafe-cafecafecafe"}))
    assert response.status_code == 404
    assert response.context["exception"] == "No campaign matching this ID exists"


@pytest.mark.parametrize("state", [state for state in CampaignState if state not in CAMPAIGN_CLOSED_STATES])
def test_campaign_update_state_close(user, state, managed_campaign, django_assert_num_queries):
    managed_campaign.state = state
    managed_campaign.save()

    with django_assert_num_queries(5):
        response = user.post(
            reverse("campaign-update-state", kwargs={"pk": managed_campaign.id}),
            {"close": "Close"},
        )
    assert response.status_code == 302
    assert response.url == reverse("campaign-details", kwargs={"pk": managed_campaign.id})

    managed_campaign.refresh_from_db()
    assert managed_campaign.state == CampaignState.Closed


def test_campaign_update_state_reopen(user, managed_campaign, django_assert_num_queries):
    managed_campaign.state = CampaignState.Closed
    managed_campaign.save()

    with django_assert_num_queries(5):
        response = user.post(
            reverse("campaign-update-state", kwargs={"pk": managed_campaign.id}),
            {"reopen": "Reopen"},
        )
    assert response.status_code == 302
    assert response.url == reverse("campaign-details", kwargs={"pk": managed_campaign.id})

    managed_campaign.refresh_from_db()
    assert managed_campaign.state == CampaignState.Running


@pytest.mark.parametrize("state", [state for state in CampaignState if state != CampaignState.Archived])
def test_campaign_update_state_archive(user, state, managed_campaign, django_assert_num_queries):
    managed_campaign.state = state
    managed_campaign.save()

    with django_assert_num_queries(5):
        response = user.post(
            reverse("campaign-update-state", kwargs={"pk": managed_campaign.id}),
            {"archive": "Archive"},
        )
    assert response.status_code == 302
    assert response.url == reverse("project-details", kwargs={"project_id": managed_campaign.project.id})

    managed_campaign.refresh_from_db()
    assert managed_campaign.state == CampaignState.Archived
