import uuid

import pytest
from django.urls import reverse

from callico.annotations.models import (
    USER_TASK_ANNOTATE_URL_NAMES,
    USER_TASK_MODERATE_URL_NAMES,
    AnnotationState,
    TaskState,
    TaskUser,
)
from callico.projects.forms import (
    ENTITY_TRANSCRIPTION_DISPLAY_CHOICES,
    ENTITY_TRANSCRIPTION_DISPLAY_NEXT_TO_IMAGE,
)
from callico.projects.models import CampaignMode, Role

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "user_task_url_name",
    [
        USER_TASK_ANNOTATE_URL_NAMES[CampaignMode.Entity],
        USER_TASK_MODERATE_URL_NAMES[CampaignMode.Entity],
    ],
)
@pytest.mark.parametrize("transcription_display", dict(ENTITY_TRANSCRIPTION_DISPLAY_CHOICES).keys())
def test_manage_entity(
    user_task_url_name, contributor, transcription_display, managed_campaign_with_tasks, django_assert_num_queries
):
    if "moderate" in user_task_url_name:
        managed_campaign_with_tasks.project.memberships.filter(user=contributor.user).update(role=Role.Moderator)

    managed_campaign_with_tasks.mode = CampaignMode.Entity
    managed_campaign_with_tasks.configuration = {
        "types": [
            {"entity_type": "person", "entity_color": "#80def5"},
            {"entity_type": "city", "entity_color": "#80def5"},
            {"entity_type": "birthday", "entity_color": "#80def5"},
        ],
        "transcription_display": transcription_display,
    }
    managed_campaign_with_tasks.save()

    entities = [
        {"entity_type": "person", "offset": 0, "length": 28},
        {"entity_type": "city", "offset": 58, "length": 5},
    ]
    user_task = TaskUser.objects.filter(
        task__campaign_id=managed_campaign_with_tasks.id, state=TaskState.Pending, user=contributor.user
    ).first()
    user_task.annotations.create(
        value={
            "entities": entities
            + [
                # Invalid entity type that should be filtered by the view
                {"entity_type": "invalid", "offset": 0, "length": 28},
                # Invalid entity offset + length that should be filtered by the view
                {"entity_type": "person", "offset": 0, "length": 65},
            ]
        },
    )

    user_task.task.element.transcription = {
        "id": str(uuid.uuid4()),
        "text": "Emma Charlotte Duerre Watson was born on 15 April 1990 in Paris.",
    }
    user_task.task.element.save()

    expected_queries = 11 + 3 * ("annotate" in user_task_url_name)
    with django_assert_num_queries(expected_queries):
        response = contributor.get(reverse(user_task_url_name, kwargs={"pk": user_task.id}))
    assert response.status_code == 200
    assert response.context["user_task"] == user_task
    assert "previous" in response.context
    assert "next" in response.context
    assert response.context["add_pending_filter"]
    assert response.context["previous_entities"] == entities
    assert response.context["labels"] == {"birthday": "#80def5", "city": "#80def5", "person": "#80def5"}
    assert response.context["display_image"] == (transcription_display == ENTITY_TRANSCRIPTION_DISPLAY_NEXT_TO_IMAGE)
    assert response.context["light_display"]
    assert not response.context["rtl_oriented_element"]
    assert response.context["full_word_selection"] == "true"
    assert user_task.annotations.count() == 1


@pytest.mark.parametrize(
    "user_task_url_name",
    [
        USER_TASK_ANNOTATE_URL_NAMES[CampaignMode.Entity],
        USER_TASK_MODERATE_URL_NAMES[CampaignMode.Entity],
    ],
)
def test_manage_entity_errors(user_task_url_name, contributor, managed_campaign_with_tasks, django_assert_num_queries):
    if "moderate" in user_task_url_name:
        managed_campaign_with_tasks.project.memberships.filter(user=contributor.user).update(role=Role.Moderator)

    managed_campaign_with_tasks.mode = CampaignMode.Entity
    managed_campaign_with_tasks.configuration = {
        "types": [
            {"entity_type": "first_name", "entity_color": "#80def5"},
            {"entity_type": "city", "entity_color": "#80def5"},
        ]
    }
    managed_campaign_with_tasks.save()

    user_task = TaskUser.objects.filter(
        task__campaign_id=managed_campaign_with_tasks.id, state=TaskState.Pending, user=contributor.user
    ).first()

    user_task.task.element.transcription = {
        "id": str(uuid.uuid4()),
        "text": "Emma Charlotte Duerre Watson was born on 15 April 1990.",
    }
    user_task.task.element.save()

    values = [
        {"entity_type": "first_name", "offset": 0, "length": 21},
        # Check that all three fields are required (empty forms are allowed)
        {"entity_type": "", "offset": "2", "length": ""},
        {"entity_type": "first_name", "offset": "", "length": "3"},
        # Invalid type and invalid offset/length
        {"entity_type": "location", "offset": 42, "length": 42},
        # Invalid min value for offset/length
        {"entity_type": "city", "offset": -1, "length": -1},
    ]
    data = {
        "form-TOTAL_FORMS": len(values),
        "form-INITIAL_FORMS": 0,
        **{f"form-{i}-{key}": val for i, value in enumerate(values) for key, val in value.items()},
    }

    expected_queries = 12 + ("annotate" in user_task_url_name)
    with django_assert_num_queries(expected_queries):
        response = contributor.post(reverse(user_task_url_name, kwargs={"pk": user_task.id}), data)
    assert response.status_code == 200

    form = response.context["form"]
    assert len(form.errors) == 5
    assert form.errors == [
        {},
        {
            "entity_type": ["This field is required."],
            "length": ["This field is required."],
        },
        {"offset": ["This field is required."]},
        {
            "entity_type": ["Select a valid choice. location is not one of the available choices."],
            "__all__": [
                "The entity is not part of the transcription",
            ],
        },
        {
            "offset": ["Ensure this value is greater than or equal to 0."],
            "length": ["Ensure this value is greater than or equal to 1."],
        },
    ]

    user_task.refresh_from_db()

    assert user_task.state == TaskState.Pending
    assert not user_task.annotations.exists()


@pytest.mark.parametrize("default_parent", [True, False])
@pytest.mark.parametrize("has_parent", [True, False])
def test_annotate_entity(
    contributor,
    managed_campaign_with_tasks,
    default_parent,
    has_parent,
    django_assert_num_queries,
):
    managed_campaign_with_tasks.mode = CampaignMode.Entity
    managed_campaign_with_tasks.configuration = {
        "types": [
            {"entity_type": "person", "entity_color": "#4de39f"},
            {"entity_type": "city", "entity_color": "#63e34d"},
            {"entity_type": "birthday", "entity_color": "#e3964d"},
        ]
    }
    managed_campaign_with_tasks.save()

    user_task = TaskUser.objects.filter(
        task__campaign_id=managed_campaign_with_tasks.id, state=TaskState.Pending, user=contributor.user
    ).first()

    user_task.task.element.transcription = {
        "id": str(uuid.uuid4()),
        "text": "Emma Charlotte Duerre Watson was born on 15 April 1990 in Paris.",
    }
    user_task.task.element.save()

    other_annotation = None
    last_annotation = None
    if has_parent:
        other_annotation = user_task.annotations.create(
            version=6,
            value={"entities": [{"entity_type": "person", "offset": 0, "length": 21}]},
        )
        last_annotation = user_task.annotations.create(
            version=42,
            value={
                "entities": [
                    {"entity_type": "person", "offset": 0, "length": 28},
                    {"entity_type": "city", "offset": 58, "length": 5},
                ]
            },
        )
        user_task.state = TaskState.Annotated
        user_task.save()

    expected = [
        {"entity_type": "person", "offset": 0, "length": 28},
        {"entity_type": "birthday", "offset": 41, "length": 13},
        {"entity_type": "city", "offset": 58, "length": 5},
    ]
    data = {
        "form-TOTAL_FORMS": len(expected),
        "form-INITIAL_FORMS": 0,
        **{f"form-{i}-{key}": val for i, value in enumerate(expected) for key, val in value.items()},
    }

    expected_queries = 17 + (not has_parent)
    with django_assert_num_queries(expected_queries):
        annotate_url = user_task.annotate_url
        if has_parent and not default_parent:
            annotate_url += f"?parent_id={other_annotation.id}"
        response = contributor.post(annotate_url, data)
    assert response.status_code == 302

    user_task.refresh_from_db()

    assert user_task.state == TaskState.Annotated
    assert user_task.annotations.count() == (3 if has_parent else 1)

    annotation = user_task.annotations.order_by("-created").first()
    if has_parent:
        assert annotation.parent == last_annotation if default_parent else other_annotation
    else:
        assert not annotation.parent
    assert annotation.version == (last_annotation.version + 1 if has_parent else 1)
    assert annotation.value == {"entities": expected}


@pytest.mark.parametrize("new_value", [True, False])
def test_validate_entity(
    user,
    managed_campaign_with_tasks,
    new_value,
    django_assert_num_queries,
):
    managed_campaign_with_tasks.mode = CampaignMode.Entity
    managed_campaign_with_tasks.configuration = {
        "types": [
            {"entity_type": "person", "entity_color": "#4de39f"},
            {"entity_type": "city", "entity_color": "#63e34d"},
            {"entity_type": "birthday", "entity_color": "#e3964d"},
        ]
    }
    managed_campaign_with_tasks.save()

    user_task = (
        TaskUser.objects.filter(task__campaign_id=managed_campaign_with_tasks.id, state=TaskState.Pending)
        .order_by("task__created", "task_id", "created", "id")
        .first()
    )

    user_task.task.element.transcription = {
        "id": str(uuid.uuid4()),
        "text": "Emma Charlotte Duerre Watson was born on 15 April 1990 in Paris.",
    }
    user_task.task.element.save()

    user_task.annotations.create(
        version=6,
        value={"entities": [{"entity_type": "person", "offset": 0, "length": 21}]},
    )
    last_annotation = user_task.annotations.create(
        version=42,
        value={
            "entities": [
                {"entity_type": "person", "offset": 0, "length": 28},
                {"entity_type": "city", "offset": 58, "length": 5},
            ]
        },
    )
    user_task.state = TaskState.Annotated
    user_task.save()

    expected = (
        [
            {"entity_type": "person", "offset": 0, "length": 28},
            {"entity_type": "birthday", "offset": 41, "length": 13},
            {"entity_type": "city", "offset": 58, "length": 5},
        ]
        if new_value
        else last_annotation.value["entities"]
    )
    data = {
        "form-TOTAL_FORMS": len(expected),
        "form-INITIAL_FORMS": 0,
        **{f"form-{i}-{key}": val for i, value in enumerate(expected) for key, val in value.items()},
    }

    expected_queries = 12 + (new_value) * 4
    with django_assert_num_queries(expected_queries):
        response = user.post(user_task.moderate_url, data)
    assert response.status_code == 302

    user_task.refresh_from_db()

    assert user_task.state == TaskState.Validated
    assert user_task.annotations.count() == 2 + new_value

    annotation = user_task.annotations.order_by("-created").first()
    assert annotation.moderator == user.user
    assert annotation.state == (AnnotationState.Validated if not new_value else None)

    if new_value:
        assert annotation.parent == last_annotation
        assert annotation.version == last_annotation.version + 1
        assert annotation.value == {"entities": expected}
    else:
        assert annotation == last_annotation
