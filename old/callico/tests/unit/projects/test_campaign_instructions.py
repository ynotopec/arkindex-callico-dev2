import pytest
from django.urls import reverse

from callico.projects.models import Role

pytestmark = pytest.mark.django_db


def test_campaign_instructions_anonymous(anonymous, campaign):
    "An anonymous user is redirected to the login page"
    instructions_url = reverse("campaign-instructions", kwargs={"pk": campaign.id})
    response = anonymous.get(instructions_url)
    assert response.status_code == 302
    assert response.url == reverse("login") + f"?next={instructions_url}"


def test_campaign_instructions_forbidden(user, hidden_campaign):
    assert not hidden_campaign.project.memberships.filter(user=user.user).exists()
    response = user.get(reverse("campaign-instructions", kwargs={"pk": hidden_campaign.id}))
    assert response.status_code == 403


def test_campaign_instructions_archived_campaign(user, archived_campaign):
    response = user.get(reverse("campaign-instructions", kwargs={"pk": archived_campaign.id}))
    assert response.status_code == 403
    assert str(response.context["error_message"]) == "You cannot view the instructions of a campaign marked as Archived"


def test_campaign_instructions_wrong_campaign_id(user):
    response = user.get(reverse("campaign-instructions", kwargs={"pk": "cafecafe-cafe-cafe-cafe-cafecafecafe"}))
    assert response.status_code == 404
    assert response.context["exception"] == "No campaign matching this ID exists"


@pytest.mark.parametrize("role", Role)
def test_campaign_instructions(user, role, campaign, django_assert_num_queries):
    campaign.project.memberships.update_or_create(user=user.user, defaults={"role": role})

    with django_assert_num_queries(7):
        response = user.get(reverse("campaign-instructions", kwargs={"pk": campaign.id}))
    assert response.status_code == 200

    assert response.context["campaign"] == campaign
    assert response.context["can_admin"] == (role != Role.Contributor)
    assert not response.context["has_pending_tasks"]
