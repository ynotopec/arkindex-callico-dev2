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
            {
                "entity_type": "firstname",
                "instruction": "Firstname",
                "confidence_threshold": 0.42,
                "validation_regex": "^.*$",
            },
            # Field group
            {
                "mode": "group",
                "legend": "Author",
                "fields": [
                    # Field in group
                    {
                        "entity_type": "author_firstname",
                        "instruction": "Firstname",
                        "confidence_threshold": 0.42,
                        "validation_regex": "^.*$",
                    },
                ],
            },
        ]
    }
    managed_campaign.save()
    managed_campaign.refresh_from_db()
    return managed_campaign


@pytest.mark.parametrize("position, mode", POSITIONS_MODES)
def test_object_update_anonymous(anonymous, campaign, position, mode):
    "An anonymous user is redirected to the login page"
    update_url = (
        reverse("entity-form-object-update", kwargs={"pk": campaign.id, "position": position}) + f"?mode={mode}"
    )
    response = anonymous.post(update_url)
    assert response.status_code == 302
    assert response.url == reverse("login") + f"?next={quote(update_url)}"


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
def test_object_update_forbidden(user, forbidden_campaign, position, mode):
    forbidden_campaign.mode = CampaignMode.EntityForm
    forbidden_campaign.save()

    response = user.post(
        reverse("entity-form-object-update", kwargs={"pk": forbidden_campaign.id, "position": position})
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
def test_field_update_wrong_campaign_id(user, wrong_campaign, position, mode):
    if not wrong_campaign:
        wrong_id = "cafecafe-cafe-cafe-cafe-cafecafecafe"
    else:
        wrong_id = str(wrong_campaign.id)

    response = user.post(
        reverse("entity-form-object-update", kwargs={"pk": wrong_id, "position": position}) + f"?mode={mode}"
    )
    assert response.status_code == 404
    assert response.context["exception"] == "No EntityForm campaign matching this ID exists"


@pytest.mark.parametrize("state", CAMPAIGN_CLOSED_STATES)
@pytest.mark.parametrize("object, position, mode", OBJECTS_POSITIONS_MODES)
def test_field_update_closed_campaign(state, user, managed_entity_form_campaign, object, position, mode):
    managed_entity_form_campaign.state = state
    managed_entity_form_campaign.save()

    response = user.post(
        reverse("entity-form-object-update", kwargs={"pk": managed_entity_form_campaign.id, "position": position})
        + f"?mode={mode}"
    )
    assert response.status_code == 403
    assert (
        str(response.context["error_message"])
        == f"You cannot edit {object + 's'} on a campaign marked as {state.capitalize()}"
    )


@pytest.mark.parametrize("object, position, mode", OBJECTS_POSITIONS_MODES)
def test_object_update_wrong_position(user, managed_entity_form_campaign, object, position, mode):
    position += len(managed_entity_form_campaign.configuration["fields"])
    response = user.post(
        reverse("entity-form-object-update", kwargs={"pk": managed_entity_form_campaign.id, "position": position})
        + f"?mode={mode}"
    )
    assert response.status_code == 404
    assert response.context["exception"] == f"No {object} matching this position exists in your campaign"


def test_field_update_wrong_group_to_search_in(user, managed_entity_form_campaign):
    response = user.post(
        reverse("entity-form-object-update", kwargs={"pk": managed_entity_form_campaign.id, "position": 0}) + "?group=2"
    )
    assert response.status_code == 404
    assert response.context["exception"] == "The group to search your field in does not exist in your campaign"


def test_field_update_wrong_position_in_group(user, managed_entity_form_campaign):
    response = user.post(
        reverse("entity-form-object-update", kwargs={"pk": managed_entity_form_campaign.id, "position": 1}) + "?group=1"
    )
    assert response.status_code == 404
    assert response.context["exception"] == "No field matching this position exists in your campaign"


def test_field_update_missing_required_fields(user, managed_entity_form_campaign):
    current_config = managed_entity_form_campaign.configuration["fields"]

    response = user.post(
        reverse("entity-form-object-update", kwargs={"pk": managed_entity_form_campaign.id, "position": 0}),
        {
            "entity_type": "",
            "instruction": "",
        },
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 2
    assert form.errors == {
        "entity_type": ["This field is required."],
        "instruction": ["This field is required."],
    }
    assert managed_entity_form_campaign.configuration["fields"] == current_config


def test_group_update_missing_required_field(user, managed_entity_form_campaign):
    current_config = managed_entity_form_campaign.configuration["fields"]

    response = user.post(
        reverse("entity-form-object-update", kwargs={"pk": managed_entity_form_campaign.id, "position": 1})
        + "?mode=group",
        {"legend": ""},
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 1
    assert form.errors == {
        "legend": ["This field is required."],
    }
    assert managed_entity_form_campaign.configuration["fields"] == current_config


def test_field_update_invalid_from_authority(user, managed_entity_form_campaign):
    current_config = managed_entity_form_campaign.configuration["fields"]

    response = user.post(
        reverse("entity-form-object-update", kwargs={"pk": managed_entity_form_campaign.id, "position": 0}),
        {"entity_type": "country", "instruction": "Country", "from_authority": "cafecafe-cafe-cafe-cafe-cafecafecafe"},
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 1
    assert form.errors == {
        "from_authority": ["Select a valid choice. That choice is not one of the available choices."]
    }
    assert managed_entity_form_campaign.configuration["fields"] == current_config


def test_field_update_authority_or_predefined_error(user, managed_entity_form_campaign, authority):
    current_config = managed_entity_form_campaign.configuration["fields"]

    response = user.post(
        reverse("entity-form-object-update", kwargs={"pk": managed_entity_form_campaign.id, "position": 0}),
        {
            "entity_type": "country",
            "instruction": "Country",
            "from_authority": str(authority.id),
            "allow_predefined_choices": True,
            "predefined_choices": "england,usa",
        },
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 2
    assert form.errors == {
        "from_authority": [
            "The fields to limit allowed annotations, either from an authority or a custom list, are mutually exclusive"
        ],
        "predefined_choices": [
            "The fields to limit allowed annotations, either from an authority or a custom list, are mutually exclusive"
        ],
    }
    assert managed_entity_form_campaign.configuration["fields"] == current_config


def test_field_update_invalid_predefined_choices(user, managed_entity_form_campaign):
    current_config = managed_entity_form_campaign.configuration["fields"]

    # Checkbox for allowed annotations was checked but no choices were provided
    response = user.post(
        reverse("entity-form-object-update", kwargs={"pk": managed_entity_form_campaign.id, "position": 0}),
        {
            "entity_type": "firstname",
            "instruction": "Firstname",
            "allow_predefined_choices": True,
            "predefined_choices": "",
        },
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 1
    assert form.errors == {"predefined_choices": ["You must set at least one custom choice."]}
    assert managed_entity_form_campaign.configuration["fields"] == current_config


def test_field_update_invalid_confidence_threshold(user, managed_entity_form_campaign):
    current_config = managed_entity_form_campaign.configuration["fields"]

    # Invalid confidence_threshold
    response = user.post(
        reverse("entity-form-object-update", kwargs={"pk": managed_entity_form_campaign.id, "position": 0}),
        {
            "entity_type": "firstname",
            "instruction": "Firstname",
            "confidence_threshold": 542,
        },
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 1
    assert form.errors == {"confidence_threshold": ["Ensure this value is less than or equal to 1."]}
    assert managed_entity_form_campaign.configuration["fields"] == current_config


def test_field_update_invalid_regular_expression(user, managed_entity_form_campaign):
    current_config = managed_entity_form_campaign.configuration["fields"]

    # Invalid validation_regex
    response = user.post(
        reverse("entity-form-object-update", kwargs={"pk": managed_entity_form_campaign.id, "position": 0}),
        {
            "entity_type": "firstname",
            "instruction": "Firstname",
            "validation_regex": "^*$",
        },
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 1
    assert form.errors == {"validation_regex": ["The regular expression is invalid."]}
    assert managed_entity_form_campaign.configuration["fields"] == current_config


def test_field_update_duplicated_type_instruction(user, managed_entity_form_campaign):
    current_config = managed_entity_form_campaign.configuration["fields"]

    # An entity with the same type "author_firstname" and instruction "Firstname" is already configured on this campaign
    response = user.post(
        reverse("entity-form-object-update", kwargs={"pk": managed_entity_form_campaign.id, "position": 0}),
        {
            "entity_type": "author_firstname",
            "instruction": "Firstname",
        },
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 2
    assert form.errors == {
        "entity_type": ["The entity type/instruction combination must be unique across configured fields."],
        "instruction": ["The entity type/instruction combination must be unique across configured fields."],
    }
    assert managed_entity_form_campaign.configuration["fields"] == current_config


def test_group_update_duplicated_legend(user, managed_entity_form_campaign):
    managed_entity_form_campaign.configuration["fields"].append({"mode": "group", "legend": "Author 2", "fields": []})
    managed_entity_form_campaign.save()
    current_config = managed_entity_form_campaign.configuration["fields"]

    # A group with the same legend "Author 2" is already configured on this campaign
    response = user.post(
        reverse("entity-form-object-update", kwargs={"pk": managed_entity_form_campaign.id, "position": 1})
        + "?mode=group",
        {"legend": "Author 2"},
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 1
    assert form.errors == {
        "legend": ["The legend must be unique across configured field groups."],
    }
    assert managed_entity_form_campaign.configuration["fields"] == current_config


@pytest.mark.parametrize("object, position, mode", OBJECTS_POSITIONS_MODES)
def test_object_update_get(user, managed_entity_form_campaign, django_assert_num_queries, object, position, mode):
    with django_assert_num_queries(4 + (mode == "field")):
        response = user.get(
            reverse("entity-form-object-update", kwargs={"pk": managed_entity_form_campaign.id, "position": position})
            + f"?mode={mode}"
        )
    assert response.status_code == 200

    assert response.context["campaign"] == managed_entity_form_campaign
    assert response.context["display_configuration"] is True
    assert response.context["action"] == "Edit"
    assert response.context["obj"] == object
    assert response.context["is_field_group"] == (mode == "group")


@pytest.mark.parametrize("state", [state for state in CampaignState if state not in CAMPAIGN_CLOSED_STATES])
@pytest.mark.parametrize(
    "from_group, to_group",
    [
        # Not moved from root
        (-1, -1),
        # Not moved from current group
        (1, 1),
        # Moved from root to a group
        (-1, 1),
        # Moved from a group to another group
        (1, 2),
        # Moved from a group to root
        (1, -1),
    ],
)
def test_field_update_post(user, state, managed_entity_form_campaign, django_assert_num_queries, from_group, to_group):
    managed_entity_form_campaign.configuration["fields"].append({"mode": "group", "legend": "Author 2", "fields": []})
    managed_entity_form_campaign.state = state
    managed_entity_form_campaign.save()
    current_config = managed_entity_form_campaign.configuration["fields"]

    with django_assert_num_queries(5):
        response = user.post(
            reverse("entity-form-object-update", kwargs={"pk": managed_entity_form_campaign.id, "position": 0})
            + f"?group={from_group}",
            {
                "entity_type": "gender",
                "instruction": "Gender",
                "help_text": "Pick a gender in the displayed list",
                "from_authority": "",
                "allow_predefined_choices": True,
                "predefined_choices": "female, male, non-binary",
                "confidence_threshold": 0.26,
                "group": to_group,
            },
        )
    assert response.status_code == 302
    assert response.url == reverse("campaign-update", kwargs={"pk": managed_entity_form_campaign.id})

    managed_entity_form_campaign.refresh_from_db()
    updated_field = {
        "entity_type": "gender",
        "instruction": "Gender",
        "help_text": "Pick a gender in the displayed list",
        "from_authority": None,
        "predefined_choices": "female, male, non-binary",
        "confidence_threshold": 0.26,
        "validation_regex": "",
    }
    if from_group == to_group:
        if from_group < 0:
            assert managed_entity_form_campaign.configuration["fields"] == [
                # Only the first field was updated
                updated_field,
                current_config[1],
                current_config[2],
            ]
        else:
            assert managed_entity_form_campaign.configuration["fields"] == [
                current_config[0],
                # Only the first field in the group Author was updated
                {**current_config[1], "fields": [updated_field]},
                current_config[2],
            ]
    elif from_group < 0:
        assert managed_entity_form_campaign.configuration["fields"] == [
            # The root field was moved to the group Author and updated
            {
                **current_config[1],
                "fields": [
                    current_config[1]["fields"][0],
                    updated_field,
                ],
            },
            current_config[2],
        ]
    elif to_group < 0:
        assert managed_entity_form_campaign.configuration["fields"] == [
            # The field from the group Author was moved to the root and updated
            current_config[0],
            {**current_config[1], "fields": []},
            current_config[2],
            updated_field,
        ]
    else:
        assert managed_entity_form_campaign.configuration["fields"] == [
            current_config[0],
            {**current_config[1], "fields": []},
            # The field from the group Author was moved to the group Author 2 and updated
            {**current_config[2], "fields": [updated_field]},
        ]


@pytest.mark.parametrize("state", [state for state in CampaignState if state not in CAMPAIGN_CLOSED_STATES])
def test_group_update_post(user, state, managed_entity_form_campaign, django_assert_num_queries):
    current_config = managed_entity_form_campaign.configuration["fields"]
    managed_entity_form_campaign.state = state
    managed_entity_form_campaign.save()

    with django_assert_num_queries(5):
        response = user.post(
            reverse("entity-form-object-update", kwargs={"pk": managed_entity_form_campaign.id, "position": 1})
            + "?mode=group",
            {"legend": "Author 2"},
        )
    assert response.status_code == 302
    assert response.url == reverse("campaign-update", kwargs={"pk": managed_entity_form_campaign.id})

    managed_entity_form_campaign.refresh_from_db()
    assert managed_entity_form_campaign.configuration["fields"] == [
        current_config[0],
        {**current_config[1], "legend": "Author 2"},
    ]
