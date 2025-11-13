from urllib.parse import quote

import pytest
from django.urls import reverse
from pytest_lazy_fixtures import lf as lazy_fixture

from callico.projects.models import CAMPAIGN_CLOSED_STATES, CampaignMode, CampaignState

pytestmark = pytest.mark.django_db

MODES = ["field", "group"]
OBJECTS_MODES = list(zip(["field", "field group"], MODES))


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


@pytest.mark.parametrize("mode", MODES)
def test_object_create_anonymous(anonymous, campaign, mode):
    "An anonymous user is redirected to the login page"
    create_url = reverse("entity-form-object-create", kwargs={"pk": campaign.id}) + f"?mode={mode}"
    response = anonymous.post(create_url)
    assert response.status_code == 302
    assert response.url == reverse("login") + f"?next={quote(create_url)}"


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
@pytest.mark.parametrize("mode", MODES)
def test_object_create_forbidden(user, forbidden_campaign, mode):
    forbidden_campaign.mode = CampaignMode.EntityForm
    forbidden_campaign.save()

    response = user.post(reverse("entity-form-object-create", kwargs={"pk": forbidden_campaign.id}) + f"?mode={mode}")
    assert response.status_code == 403


@pytest.mark.parametrize(
    "wrong_campaign",
    [
        None,
        # Transcription campaign
        lazy_fixture("managed_campaign"),
    ],
)
@pytest.mark.parametrize("mode", MODES)
def test_object_create_wrong_campaign_id(user, wrong_campaign, mode):
    if not wrong_campaign:
        wrong_id = "cafecafe-cafe-cafe-cafe-cafecafecafe"
    else:
        wrong_id = str(wrong_campaign.id)

    response = user.post(reverse("entity-form-object-create", kwargs={"pk": wrong_id}) + f"?mode={mode}")
    assert response.status_code == 404
    assert response.context["exception"] == "No EntityForm campaign matching this ID exists"


@pytest.mark.parametrize("state", CAMPAIGN_CLOSED_STATES)
@pytest.mark.parametrize("object, mode", OBJECTS_MODES)
def test_object_create_closed_campaign(state, user, managed_entity_form_campaign, object, mode):
    managed_entity_form_campaign.state = state
    managed_entity_form_campaign.save()

    response = user.post(
        reverse("entity-form-object-create", kwargs={"pk": managed_entity_form_campaign.id}) + f"?mode={mode}"
    )
    assert response.status_code == 403
    assert (
        str(response.context["error_message"])
        == f"You cannot add a new {object} on a campaign marked as {state.capitalize()}"
    )


def test_field_create_missing_required_fields(user, managed_entity_form_campaign):
    current_config = managed_entity_form_campaign.configuration["fields"]

    response = user.post(
        reverse("entity-form-object-create", kwargs={"pk": managed_entity_form_campaign.id}),
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


def test_group_create_missing_required_field(user, managed_entity_form_campaign):
    current_config = managed_entity_form_campaign.configuration["fields"]

    response = user.post(
        reverse("entity-form-object-create", kwargs={"pk": managed_entity_form_campaign.id}) + "?mode=group",
        {"legend": ""},
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 1
    assert form.errors == {
        "legend": ["This field is required."],
    }
    assert managed_entity_form_campaign.configuration["fields"] == current_config


def test_field_create_invalid_from_authority(user, managed_entity_form_campaign):
    current_config = managed_entity_form_campaign.configuration["fields"]

    response = user.post(
        reverse("entity-form-object-create", kwargs={"pk": managed_entity_form_campaign.id}),
        {"entity_type": "country", "instruction": "Country", "from_authority": "cafecafe-cafe-cafe-cafe-cafecafecafe"},
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 1
    assert form.errors == {
        "from_authority": ["Select a valid choice. That choice is not one of the available choices."]
    }
    assert managed_entity_form_campaign.configuration["fields"] == current_config


def test_field_create_authority_or_predefined_error(user, managed_entity_form_campaign, authority):
    current_config = managed_entity_form_campaign.configuration["fields"]

    response = user.post(
        reverse("entity-form-object-create", kwargs={"pk": managed_entity_form_campaign.id}),
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


def test_field_create_invalid_predefined_choices(user, managed_entity_form_campaign):
    current_config = managed_entity_form_campaign.configuration["fields"]

    # Checkbox for allowed annotations was checked but no choices were provided
    response = user.post(
        reverse("entity-form-object-create", kwargs={"pk": managed_entity_form_campaign.id}),
        {
            "entity_type": "gender",
            "instruction": "Gender",
            "allow_predefined_choices": True,
            "predefined_choices": "",
        },
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 1
    assert form.errors == {"predefined_choices": ["You must set at least one custom choice."]}
    assert managed_entity_form_campaign.configuration["fields"] == current_config


def test_field_create_invalid_confidence_threshold(user, managed_entity_form_campaign):
    current_config = managed_entity_form_campaign.configuration["fields"]

    # Invalid confidence_threshold
    response = user.post(
        reverse("entity-form-object-create", kwargs={"pk": managed_entity_form_campaign.id}),
        {
            "entity_type": "gender",
            "instruction": "Gender",
            "confidence_threshold": 542,
        },
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 1
    assert form.errors == {"confidence_threshold": ["Ensure this value is less than or equal to 1."]}
    assert managed_entity_form_campaign.configuration["fields"] == current_config


def test_field_create_invalid_regular_expression(user, managed_entity_form_campaign):
    current_config = managed_entity_form_campaign.configuration["fields"]

    # Invalid validation_regex
    response = user.post(
        reverse("entity-form-object-create", kwargs={"pk": managed_entity_form_campaign.id}),
        {
            "entity_type": "gender",
            "instruction": "Gender",
            "validation_regex": "^*$",
        },
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 1
    assert form.errors == {"validation_regex": ["The regular expression is invalid."]}
    assert managed_entity_form_campaign.configuration["fields"] == current_config


def test_field_create_duplicated_type_instruction(user, managed_entity_form_campaign):
    current_config = managed_entity_form_campaign.configuration["fields"]

    # An entity with the same type "firstname" and instruction "Firstname" is already configured on this campaign
    response = user.post(
        reverse("entity-form-object-create", kwargs={"pk": managed_entity_form_campaign.id}),
        {
            "entity_type": "firstname",
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


def test_group_create_duplicated_legend(user, managed_entity_form_campaign):
    current_config = managed_entity_form_campaign.configuration["fields"]

    # A group with the same legend "Author" is already configured on this campaign
    response = user.post(
        reverse("entity-form-object-create", kwargs={"pk": managed_entity_form_campaign.id}) + "?mode=group",
        {"legend": "Author"},
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 1
    assert form.errors == {
        "legend": ["The legend must be unique across configured field groups."],
    }
    assert managed_entity_form_campaign.configuration["fields"] == current_config


@pytest.mark.parametrize("object, mode", OBJECTS_MODES)
def test_object_create_get(user, managed_entity_form_campaign, django_assert_num_queries, object, mode):
    with django_assert_num_queries(4 + (mode == "field")):
        response = user.get(
            reverse("entity-form-object-create", kwargs={"pk": managed_entity_form_campaign.id}) + f"?mode={mode}",
        )
    assert response.status_code == 200

    assert response.context["campaign"] == managed_entity_form_campaign
    assert response.context["display_configuration"] is True
    assert response.context["action"] == "Add"
    assert response.context["extra_action"] == "Add and create another"
    assert response.context["obj"] == object
    assert response.context["is_field_group"] == (mode == "group")


@pytest.mark.parametrize("state", [state for state in CampaignState if state not in CAMPAIGN_CLOSED_STATES])
@pytest.mark.parametrize("to_group", [-1, 1])
@pytest.mark.parametrize("add_another", [False, True])
def test_field_create_post(user, state, to_group, add_another, managed_entity_form_campaign, django_assert_num_queries):
    current_config = managed_entity_form_campaign.configuration["fields"]
    managed_entity_form_campaign.state = state
    managed_entity_form_campaign.save()

    extra = {}
    if add_another:
        extra["Add and create another"] = "Add and create another"

    with django_assert_num_queries(5):
        response = user.post(
            reverse("entity-form-object-create", kwargs={"pk": managed_entity_form_campaign.id}),
            {
                "entity_type": "gender",
                "instruction": "Gender",
                "help_text": "Pick a gender in the displayed list",
                "from_authority": "",
                "allow_predefined_choices": True,
                "predefined_choices": "female, male, non-binary",
                "confidence_threshold": 0.26,
                "group": to_group,
                **extra,
            },
        )
    assert response.status_code == 302
    if not add_another:
        assert response.url == reverse("campaign-update", kwargs={"pk": managed_entity_form_campaign.id})
    else:
        assert (
            response.url
            == reverse("entity-form-object-create", kwargs={"pk": managed_entity_form_campaign.id}) + "?mode=field"
        )

    managed_entity_form_campaign.refresh_from_db()
    new_field = {
        "entity_type": "gender",
        "instruction": "Gender",
        "help_text": "Pick a gender in the displayed list",
        "from_authority": None,
        "predefined_choices": "female, male, non-binary",
        "confidence_threshold": 0.26,
        "validation_regex": "",
    }
    # Adding the new field to the root
    if to_group < 0:
        assert managed_entity_form_campaign.configuration["fields"] == current_config + [new_field]
    # Adding the new field in the group Author at position 1
    else:
        assert managed_entity_form_campaign.configuration["fields"] == [
            current_config[0],
            {
                "mode": "group",
                "legend": "Author",
                "fields": [
                    {"entity_type": "author_firstname", "instruction": "Firstname"},
                    new_field,
                ],
            },
        ]


@pytest.mark.parametrize("state", [state for state in CampaignState if state not in CAMPAIGN_CLOSED_STATES])
@pytest.mark.parametrize("add_another", [False, True])
def test_group_create_post(user, state, add_another, managed_entity_form_campaign, django_assert_num_queries):
    current_config = managed_entity_form_campaign.configuration["fields"]
    managed_entity_form_campaign.state = state
    managed_entity_form_campaign.save()

    extra = {}
    if add_another:
        extra["Add and create another"] = "Add and create another"

    with django_assert_num_queries(5):
        response = user.post(
            reverse("entity-form-object-create", kwargs={"pk": managed_entity_form_campaign.id}) + "?mode=group",
            {"legend": "Author 2", **extra},
        )
    assert response.status_code == 302
    if not add_another:
        assert response.url == reverse("campaign-update", kwargs={"pk": managed_entity_form_campaign.id})
    else:
        assert (
            response.url
            == reverse("entity-form-object-create", kwargs={"pk": managed_entity_form_campaign.id}) + "?mode=group"
        )

    managed_entity_form_campaign.refresh_from_db()
    assert managed_entity_form_campaign.configuration["fields"] == current_config + [
        {"mode": "group", "legend": "Author 2", "fields": []}
    ]
