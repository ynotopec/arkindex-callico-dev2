from urllib.parse import quote

import pytest
from django.urls import reverse
from pytest_lazy_fixtures import lf as lazy_fixture

from callico.projects.models import CAMPAIGN_CLOSED_STATES, CampaignMode, CampaignState

pytestmark = pytest.mark.django_db

MODES = ["field", "group"]
POSITIONS_MODES = list(enumerate(MODES))
OBJECTS_POSITIONS_MODES = list(zip(["field", "field group"], [0, 1], MODES))


@pytest.fixture()
def managed_entity_form_campaign(managed_campaign):
    managed_campaign.mode = CampaignMode.EntityForm
    managed_campaign.configuration = {
        "fields": [
            # Field in root
            {"entity_type": "firstname", "instruction": "Firstname"},
            # Field group
            {
                "mode": "group",
                "legend": "Author",
                "fields": [
                    # Field in group
                    {"entity_type": "author_firstname", "instruction": "Firstname"},
                ],
            },
        ]
    }
    managed_campaign.save()
    managed_campaign.refresh_from_db()
    return managed_campaign


@pytest.mark.parametrize("position, mode", POSITIONS_MODES)
def test_object_delete_anonymous(anonymous, campaign, position, mode):
    "An anonymous user is redirected to the login page"
    delete_url = (
        reverse("entity-form-object-delete", kwargs={"pk": campaign.id, "position": position}) + f"?mode={mode}"
    )
    response = anonymous.post(delete_url)
    assert response.status_code == 302
    assert response.url == reverse("login") + f"?next={quote(delete_url)}"


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
@pytest.mark.parametrize("position, mode", POSITIONS_MODES)
def test_object_delete_forbidden(user, forbidden_campaign, position, mode):
    forbidden_campaign.mode = CampaignMode.EntityForm
    forbidden_campaign.save()

    response = user.post(
        reverse("entity-form-object-delete", kwargs={"pk": forbidden_campaign.id, "position": position})
        + f"?mode={mode}"
    )
    assert response.status_code == 403


@pytest.mark.parametrize(
    "wrong_campaign",
    [
        None,
        # Transcription campaign
        lazy_fixture("managed_campaign"),
    ],
)
@pytest.mark.parametrize("position, mode", POSITIONS_MODES)
def test_object_delete_wrong_campaign_id(user, wrong_campaign, position, mode):
    if not wrong_campaign:
        wrong_id = "cafecafe-cafe-cafe-cafe-cafecafecafe"
    else:
        wrong_id = str(wrong_campaign.id)

    response = user.post(
        reverse("entity-form-object-delete", kwargs={"pk": wrong_id, "position": position}) + f"?mode={mode}"
    )
    assert response.status_code == 404
    assert response.context["exception"] == "No EntityForm campaign matching this ID exists"


@pytest.mark.parametrize("state", CAMPAIGN_CLOSED_STATES)
@pytest.mark.parametrize("object, position, mode", OBJECTS_POSITIONS_MODES)
def test_object_delete_closed_campaign(state, user, managed_entity_form_campaign, object, position, mode):
    managed_entity_form_campaign.state = state
    managed_entity_form_campaign.save()

    response = user.post(
        reverse("entity-form-object-delete", kwargs={"pk": managed_entity_form_campaign.id, "position": position})
        + f"?mode={mode}"
    )
    assert response.status_code == 403
    assert (
        str(response.context["error_message"])
        == f"You cannot delete {object + 's'} on a campaign marked as {state.capitalize()}"
    )


@pytest.mark.parametrize("object, position, mode", OBJECTS_POSITIONS_MODES)
def test_object_delete_wrong_position(user, managed_entity_form_campaign, object, position, mode):
    position += len(managed_entity_form_campaign.configuration["fields"])
    response = user.post(
        reverse("entity-form-object-delete", kwargs={"pk": managed_entity_form_campaign.id, "position": position})
        + f"?mode={mode}"
    )
    assert response.status_code == 404
    assert response.context["exception"] == f"No {object} matching this position exists in your campaign"


def test_field_delete_wrong_group_to_search_in(user, managed_entity_form_campaign):
    response = user.post(
        reverse("entity-form-object-delete", kwargs={"pk": managed_entity_form_campaign.id, "position": 0}) + "?group=2"
    )
    assert response.status_code == 404
    assert response.context["exception"] == "The group to search your field in does not exist in your campaign"


def test_field_delete_wrong_position_in_group(user, managed_entity_form_campaign):
    response = user.post(
        reverse("entity-form-object-delete", kwargs={"pk": managed_entity_form_campaign.id, "position": 1}) + "?group=1"
    )
    assert response.status_code == 404
    assert response.context["exception"] == "No field matching this position exists in your campaign"


@pytest.mark.parametrize("object, position, mode", OBJECTS_POSITIONS_MODES)
def test_object_delete_get(user, managed_entity_form_campaign, django_assert_num_queries, object, position, mode):
    with django_assert_num_queries(4):
        response = user.get(
            reverse("entity-form-object-delete", kwargs={"pk": managed_entity_form_campaign.id, "position": position})
            + f"?mode={mode}"
        )
    assert response.status_code == 200

    assert response.context["campaign"] == managed_entity_form_campaign
    assert response.context["display_configuration"] is True
    assert response.context["action"] == "Delete"
    assert response.context["obj"] == object
    assert response.context["is_field_group"] == (mode == "group")
    assert response.context["object"] == ("Author" if mode == "group" else "Firstname")


@pytest.mark.parametrize("state", [state for state in CampaignState if state not in CAMPAIGN_CLOSED_STATES])
@pytest.mark.parametrize("from_group", [-1, 1])
def test_field_delete_post(user, state, managed_entity_form_campaign, django_assert_num_queries, from_group):
    current_config = managed_entity_form_campaign.configuration["fields"]
    managed_entity_form_campaign.state = state
    managed_entity_form_campaign.save()

    with django_assert_num_queries(5):
        response = user.post(
            reverse("entity-form-object-delete", kwargs={"pk": managed_entity_form_campaign.id, "position": 0})
            + f"?group={from_group}",
        )
    assert response.status_code == 302
    assert response.url == reverse("campaign-update", kwargs={"pk": managed_entity_form_campaign.id})

    managed_entity_form_campaign.refresh_from_db()
    # Deleting the field from the root
    if from_group < 0:
        assert managed_entity_form_campaign.configuration["fields"] == current_config[1:]
    # Deleting the field from the group Author
    else:
        assert managed_entity_form_campaign.configuration["fields"] == [
            current_config[0],
            {"mode": "group", "legend": "Author", "fields": []},
        ]


@pytest.mark.parametrize("state", [state for state in CampaignState if state not in CAMPAIGN_CLOSED_STATES])
def test_group_delete_post(user, state, managed_entity_form_campaign, django_assert_num_queries):
    current_config = managed_entity_form_campaign.configuration["fields"]
    managed_entity_form_campaign.state = state
    managed_entity_form_campaign.save()

    with django_assert_num_queries(5):
        response = user.post(
            reverse("entity-form-object-delete", kwargs={"pk": managed_entity_form_campaign.id, "position": 1})
            + "?mode=group",
        )
    assert response.status_code == 302
    assert response.url == reverse("campaign-update", kwargs={"pk": managed_entity_form_campaign.id})

    managed_entity_form_campaign.refresh_from_db()
    assert managed_entity_form_campaign.configuration["fields"] == [
        # Root field still here
        current_config[0],
        # Fields from the deleted group are appended to the root
        *current_config[1]["fields"],
    ]
