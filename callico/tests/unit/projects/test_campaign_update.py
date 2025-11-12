import json

import pytest
from django.urls import reverse
from pytest_lazy_fixtures import lf as lazy_fixture

from callico.projects.forms import ENTITY_TRANSCRIPTION_DISPLAY_CHOICES, ENTITY_TRANSCRIPTION_DISPLAY_NEXT_TO_IMAGE
from callico.projects.models import CAMPAIGN_CLOSED_STATES, CampaignMode, CampaignState

pytestmark = pytest.mark.django_db


def test_campaign_update_anonymous(anonymous, campaign):
    "An anonymous user is redirected to the login page"
    update_url = reverse("campaign-update", kwargs={"pk": campaign.id})
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
def test_campaign_update_forbidden(user, forbidden_campaign):
    response = user.post(reverse("campaign-update", kwargs={"pk": forbidden_campaign.id}))
    assert response.status_code == 403


def test_campaign_update_wrong_campaign_id(user):
    response = user.post(reverse("campaign-update", kwargs={"pk": "cafecafe-cafe-cafe-cafe-cafecafecafe"}))
    assert response.status_code == 404
    assert response.context["exception"] == "No campaign matching this ID exists"


@pytest.mark.parametrize("state", CAMPAIGN_CLOSED_STATES)
def test_campaign_update_closed_campaign(user, state, managed_campaign):
    page_type = managed_campaign.project.types.get(name="Page")
    line_type = managed_campaign.project.types.get(name="Line")

    managed_campaign.state = state
    managed_campaign.save()
    response = user.post(
        reverse("campaign-update", kwargs={"pk": managed_campaign.id}),
        {
            "name": "A campaign",
            "nb_tasks_auto_assignment": 50,
            "max_user_tasks": 1,
            "children_types": [page_type.id, line_type.id],
        },
    )
    assert response.status_code == 403
    assert (
        str(response.context["error_message"])
        == f"You cannot configure a campaign marked as {managed_campaign.get_state_display()}"
    )


@pytest.mark.parametrize(
    "mode",
    [
        mode
        for mode in CampaignMode
        if mode not in [CampaignMode.ElementGroup, CampaignMode.Elements, CampaignMode.Transcription]
    ],
)
def test_contextualized_campaign_update_invalid_context_type(user, mode, managed_campaign):
    managed_campaign.mode = mode
    managed_campaign.save()
    response = user.post(
        reverse("campaign-update", kwargs={"pk": managed_campaign.id}),
        {"name": "A campaign", "context_type": "unknown type"},
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert form.errors.get("context_type") == [
        "Select a valid choice. unknown type is not one of the available choices."
    ]


def test_campaign_update_missing_required_fields(user, managed_campaign):
    response = user.post(
        reverse("campaign-update", kwargs={"pk": managed_campaign.id}),
        {"name": "", "nb_tasks_auto_assignment": "", "max_user_tasks": "", "children_types": []},
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 4
    assert form.errors == {
        "name": ["This field is required."],
        "nb_tasks_auto_assignment": ["This field is required."],
        "max_user_tasks": ["This field is required."],
        "children_types": ["This field is required."],
    }


def test_transcription_campaign_update_invalid_children_types(user, managed_campaign):
    managed_campaign.mode = CampaignMode.Transcription
    managed_campaign.save()
    response = user.post(
        reverse("campaign-update", kwargs={"pk": managed_campaign.id}),
        {
            "name": "A campaign",
            "nb_tasks_auto_assignment": 50,
            "max_user_tasks": 1,
            "children_types": ["unknown type"],
        },
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 1
    assert form.errors == {
        "children_types": ["Select a valid choice. unknown type is not one of the available choices."]
    }


def test_transcription_campaign_update_invalid_confidence_threshold(user, managed_campaign):
    page_type = managed_campaign.project.types.get(name="Page")

    managed_campaign.mode = CampaignMode.Transcription
    managed_campaign.save()
    response = user.post(
        reverse("campaign-update", kwargs={"pk": managed_campaign.id}),
        {
            "name": "A campaign",
            "nb_tasks_auto_assignment": 50,
            "max_user_tasks": 1,
            "children_types": [page_type.id],
            "confidence_threshold": 542,
        },
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 1
    assert form.errors == {"confidence_threshold": ["Ensure this value is less than or equal to 1."]}


@pytest.mark.parametrize("state", [state for state in CampaignState if state not in CAMPAIGN_CLOSED_STATES])
def test_transcription_campaign_update(user, state, managed_campaign, django_assert_num_queries):
    page_type = managed_campaign.project.types.get(name="Page")

    managed_campaign.mode = CampaignMode.Transcription
    managed_campaign.state = state
    managed_campaign.configuration = {"key": "value"}
    managed_campaign.save()

    with django_assert_num_queries(8):
        response = user.post(
            reverse("campaign-update", kwargs={"pk": managed_campaign.id}),
            {
                "name": "New name!",
                "nb_tasks_auto_assignment": 50,
                "max_user_tasks": 1,
                "children_types": [page_type.id],
                "description": "New description",
                "confidence_threshold": 0.26,
            },
        )
    assert response.status_code == 302
    assert response.url == reverse("campaign-details", kwargs={"pk": managed_campaign.id})

    managed_campaign.refresh_from_db()
    assert managed_campaign.name == "New name!"
    assert managed_campaign.description == "New description"
    assert managed_campaign.configuration == {
        "key": "value",
        "display_grouped_inputs": False,
        "children_types": [str(page_type.id)],
        "confidence_threshold": 0.26,
    }


@pytest.mark.parametrize("state", [state for state in CampaignState if state not in CAMPAIGN_CLOSED_STATES])
def test_entity_form_campaign_update(user, state, managed_campaign, django_assert_num_queries):
    page_type = managed_campaign.project.types.get(name="Page")

    managed_campaign.mode = CampaignMode.EntityForm
    managed_campaign.state = state
    expected = [
        {
            "entity_type": "last_name",
            "instruction": "Last name",
            "confidence_threshold": None,
            "validation_regex": None,
        },
        {
            "entity_type": "first_name",
            "instruction": "First name",
            "confidence_threshold": 0.2,
            "validation_regex": "^.*$",
        },
        {"entity_type": "gender", "instruction": "Gender"},
        {
            "mode": "group",
            "legend": "Author",
            "fields": [
                {"entity_type": "author_last_name", "instruction": "Last name"},
                {"entity_type": "author_first_name", "instruction": "First name"},
            ],
        },
    ]
    managed_campaign.configuration = {"key": "value", "fields": expected}
    managed_campaign.save()

    # Reversing root and group orders
    order_list = [
        ["Author", "", ""],
        ["Author", "author_first_name", "First name"],
        ["Author", "author_last_name", "Last name"],
        ["", "gender", "Gender"],
        ["", "first_name", "First name"],
        ["", "last_name", "Last name"],
    ]
    with django_assert_num_queries(9):
        response = user.post(
            reverse("campaign-update", kwargs={"pk": managed_campaign.id}),
            {
                "name": "New name!",
                "nb_tasks_auto_assignment": 50,
                "max_user_tasks": 1,
                "description": "New description",
                "context_type": page_type.id,
                "entities_order": json.dumps(order_list),
            },
        )
    assert response.status_code == 302
    assert response.url == reverse("campaign-details", kwargs={"pk": managed_campaign.id})

    managed_campaign.refresh_from_db()
    assert managed_campaign.name == "New name!"
    assert managed_campaign.description == "New description"

    # Reversing lists to obtain the expected value
    expected[3]["fields"].reverse()
    expected.reverse()
    assert managed_campaign.configuration == {
        "key": "value",
        "context_type": str(page_type.id),
        "fields": expected,
    }


def test_classification_campaign_update_invalid_classes(user, managed_campaign):
    page_type = managed_campaign.project.types.get(name="Page")

    managed_campaign.mode = CampaignMode.Classification
    managed_campaign.save()
    response = user.post(
        reverse("campaign-update", kwargs={"pk": managed_campaign.id}),
        {
            "name": "A campaign",
            "nb_tasks_auto_assignment": 50,
            "max_user_tasks": 1,
            "classes": "unknown class",
            "context_type": page_type.id,
        },
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 1
    assert form.errors == {"classes": ["Select a valid choice. unknown class is not one of the available choices."]}


@pytest.mark.parametrize("state", [state for state in CampaignState if state not in CAMPAIGN_CLOSED_STATES])
def test_classification_campaign_update(user, state, managed_campaign, django_assert_num_queries):
    page_type = managed_campaign.project.types.get(name="Page")
    dog_class = managed_campaign.project.classes.create(name="Dog")
    managed_campaign.project.classes.create(name="Cat")

    managed_campaign.mode = CampaignMode.Classification
    managed_campaign.state = state
    managed_campaign.configuration = {"key": "value"}
    managed_campaign.save()

    with django_assert_num_queries(10):
        response = user.post(
            reverse("campaign-update", kwargs={"pk": managed_campaign.id}),
            {
                "name": "New name!",
                "nb_tasks_auto_assignment": 50,
                "max_user_tasks": 1,
                "classes": [dog_class.id],
                "description": "New description",
                "context_type": page_type.id,
            },
        )
    assert response.status_code == 302
    assert response.url == reverse("campaign-details", kwargs={"pk": managed_campaign.id})

    managed_campaign.refresh_from_db()
    assert managed_campaign.name == "New name!"
    assert managed_campaign.description == "New description"
    assert managed_campaign.configuration == {
        "key": "value",
        "context_type": str(page_type.id),
        "classes": [str(dog_class.id)],
    }


def test_element_group_campaign_update_invalid_carousel_type(user, managed_campaign):
    paragraph_type = managed_campaign.project.types.create(name="Paragraph")

    managed_campaign.mode = CampaignMode.ElementGroup
    managed_campaign.save()
    response = user.post(
        reverse("campaign-update", kwargs={"pk": managed_campaign.id}),
        {
            "name": "A campaign",
            "nb_tasks_auto_assignment": 50,
            "max_user_tasks": 1,
            "carousel_type": "unknown type",
            "group_type": paragraph_type.id,
        },
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 1
    assert form.errors == {
        "carousel_type": ["Select a valid choice. unknown type is not one of the available choices."]
    }


def test_element_group_campaign_update_invalid_group_type(user, managed_campaign):
    page_type = managed_campaign.project.types.get(name="Page")

    managed_campaign.mode = CampaignMode.ElementGroup
    managed_campaign.save()
    response = user.post(
        reverse("campaign-update", kwargs={"pk": managed_campaign.id}),
        {
            "name": "A campaign",
            "nb_tasks_auto_assignment": 50,
            "max_user_tasks": 1,
            "carousel_type": page_type.id,
            "group_type": "unknown type",
        },
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 1
    assert form.errors == {"group_type": ["Select a valid choice. unknown type is not one of the available choices."]}


def test_element_group_campaign_update_same_carousel_and_group_types(user, managed_campaign, arkindex_provider):
    element_type = managed_campaign.project.types.get(name="Page")

    managed_campaign.mode = CampaignMode.ElementGroup
    managed_campaign.save()
    response = user.post(
        reverse("campaign-update", kwargs={"pk": managed_campaign.id}),
        {
            "name": "A campaign",
            "nb_tasks_auto_assignment": 50,
            "max_user_tasks": 1,
            "carousel_type": element_type.id,
            "group_type": element_type.id,
        },
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 1
    assert form.errors == {"group_type": ["Carousel and group types cannot be the same"]}


@pytest.mark.parametrize("state", [state for state in CampaignState if state not in CAMPAIGN_CLOSED_STATES])
def test_element_group_campaign_update(user, state, managed_campaign, arkindex_provider, django_assert_num_queries):
    page_type = managed_campaign.project.types.get(name="Page")
    paragraph_type = managed_campaign.project.types.create(
        name="Paragraph", provider=arkindex_provider, provider_object_id="paragraph"
    )

    managed_campaign.mode = CampaignMode.ElementGroup
    managed_campaign.state = state
    managed_campaign.configuration = {"key": "value"}
    managed_campaign.save()

    with django_assert_num_queries(10):
        response = user.post(
            reverse("campaign-update", kwargs={"pk": managed_campaign.id}),
            {
                "name": "New name!",
                "nb_tasks_auto_assignment": 50,
                "max_user_tasks": 1,
                "carousel_type": page_type.id,
                "group_type": paragraph_type.id,
                "description": "New description",
            },
        )
    assert response.status_code == 302
    assert response.url == reverse("campaign-details", kwargs={"pk": managed_campaign.id})

    managed_campaign.refresh_from_db()
    assert managed_campaign.name == "New name!"
    assert managed_campaign.description == "New description"
    assert managed_campaign.configuration == {
        "key": "value",
        "carousel_type": str(page_type.id),
        "group_type": str(paragraph_type.id),
    }


def test_elements_campaign_update_invalid_types(user, managed_campaign):
    managed_campaign.mode = CampaignMode.Elements
    managed_campaign.save()
    response = user.post(
        reverse("campaign-update", kwargs={"pk": managed_campaign.id}),
        {"name": "A campaign", "nb_tasks_auto_assignment": 50, "max_user_tasks": 1, "element_types": "unknown type"},
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 1
    assert form.errors == {
        "element_types": ["Select a valid choice. unknown type is not one of the available choices."]
    }


@pytest.mark.parametrize("state", [state for state in CampaignState if state not in CAMPAIGN_CLOSED_STATES])
def test_elements_campaign_update(user, state, managed_campaign, django_assert_num_queries):
    paragraph_type = managed_campaign.project.types.create(name="Paragraph")

    managed_campaign.mode = CampaignMode.Elements
    managed_campaign.state = state
    managed_campaign.configuration = {"key": "value"}
    managed_campaign.save()

    with django_assert_num_queries(8):
        response = user.post(
            reverse("campaign-update", kwargs={"pk": managed_campaign.id}),
            {
                "name": "New name!",
                "nb_tasks_auto_assignment": 50,
                "max_user_tasks": 1,
                "element_types": [paragraph_type.id],
                "description": "New description",
            },
        )
    assert response.status_code == 302
    assert response.url == reverse("campaign-details", kwargs={"pk": managed_campaign.id})

    managed_campaign.refresh_from_db()
    assert managed_campaign.name == "New name!"
    assert managed_campaign.description == "New description"
    assert managed_campaign.configuration == {"key": "value", "element_types": [str(paragraph_type.id)]}


def test_entity_campaign_update_duplicate_fields(user, managed_campaign):
    page_type = managed_campaign.project.types.get(name="Page")

    managed_campaign.mode = CampaignMode.Entity
    managed_campaign.configuration = {
        "key": "value",
        "types": [
            {"entity_type": "birthday", "entity_color": "#80def5"},
            {"entity_type": "name", "entity_color": "#80def5"},
            {"entity_type": "date", "entity_color": "#80def5"},
            {"entity_type": "person", "entity_color": "#80def5"},
        ],
    }
    managed_campaign.save()

    invalid_entities = [
        # No entity_type: should not raise any errors
        {"entity_type": "", "entity_color": ""},
        # Duplicate values with entity_type
        {"entity_type": "date", "entity_color": "#80def5"},
        {"entity_type": "date", "entity_color": "#fe8f9c"},
    ]

    response = user.post(
        reverse("campaign-update", kwargs={"pk": managed_campaign.id}),
        {
            "name": "New name!",
            "nb_tasks_auto_assignment": 50,
            "max_user_tasks": 1,
            "form-TOTAL_FORMS": len(invalid_entities),
            "form-INITIAL_FORMS": 0,
            **{f"form-{i}-{key}": value for i, field in enumerate(invalid_entities) for key, value in field.items()},
            "description": "New description",
            "context_type": page_type.id,
        },
    )
    assert response.status_code == 200
    formset = response.context["formset"]
    assert len(formset.errors) == len(invalid_entities)
    assert formset.errors == [
        {},
        {"entity_type": ["There are several forms with these values"]},
        {"entity_type": ["There are several forms with these values"]},
    ]


@pytest.mark.parametrize("state", [state for state in CampaignState if state not in CAMPAIGN_CLOSED_STATES])
@pytest.mark.parametrize("transcription_display", dict(ENTITY_TRANSCRIPTION_DISPLAY_CHOICES).keys())
def test_entity_campaign_update(user, state, transcription_display, managed_campaign, django_assert_num_queries):
    page_type = managed_campaign.project.types.get(name="Page")

    managed_campaign.mode = CampaignMode.Entity
    managed_campaign.state = state
    managed_campaign.configuration = {
        "key": "value",
        "types": [
            {"entity_type": "last_name", "entity_color": "#80def5"},
            {"entity_type": "first_name", "entity_color": "#80def5"},
            {"entity_type": "test (1)", "entity_color": "#80def5"},
            {"entity_type": "test (2)", "entity_color": "#80def5"},
        ],
    }
    managed_campaign.save()

    expected = [
        {"entity_type": "name", "entity_color": "#80def5"},
        {"entity_type": "person", "entity_color": "#f7e2d2"},
        {"entity_type": "new_entity", "entity_color": "#80def5"},
    ]

    empty_entities = [
        {"entity_type": ""},
        {"entity_type": ""},
    ]

    context_type = str(page_type.id) if transcription_display == ENTITY_TRANSCRIPTION_DISPLAY_NEXT_TO_IMAGE else ""

    with django_assert_num_queries(8):
        response = user.post(
            reverse("campaign-update", kwargs={"pk": managed_campaign.id}),
            {
                "name": "New name!",
                "nb_tasks_auto_assignment": 50,
                "max_user_tasks": 1,
                "form-TOTAL_FORMS": len(expected + empty_entities),
                "form-INITIAL_FORMS": 0,
                **{
                    f"form-{i}-{key}": f"\n {value} \n\t" if key != "entity_type" else value
                    for i, field in enumerate(expected + empty_entities)
                    for key, value in field.items()
                },
                "description": "New description",
                "transcription_display": transcription_display,
                "context_type": context_type,
                "full_word_selection": True,
            },
        )
    assert response.status_code == 302
    assert response.url == reverse("campaign-details", kwargs={"pk": managed_campaign.id})

    managed_campaign.refresh_from_db()
    assert managed_campaign.name == "New name!"
    assert managed_campaign.description == "New description"
    assert managed_campaign.configuration == {
        "key": "value",
        "context_type": context_type,
        "transcription_display": transcription_display,
        "types": expected,
        "full_word_selection": True,
    }
