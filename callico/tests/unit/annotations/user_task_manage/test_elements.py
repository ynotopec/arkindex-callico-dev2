import json

import pytest
from django.urls import reverse

from callico.annotations.models import (
    USER_TASK_ANNOTATE_URL_NAMES,
    USER_TASK_MODERATE_URL_NAMES,
    AnnotationState,
    TaskState,
    TaskUser,
)
from callico.projects.models import CampaignMode, Role

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "user_task_url_name",
    [
        USER_TASK_ANNOTATE_URL_NAMES[CampaignMode.Elements],
        USER_TASK_MODERATE_URL_NAMES[CampaignMode.Elements],
    ],
)
def test_manage_elements(user_task_url_name, contributor, managed_campaign_with_tasks, django_assert_num_queries):
    if "moderate" in user_task_url_name:
        managed_campaign_with_tasks.project.memberships.filter(user=contributor.user).update(role=Role.Moderator)

    paragraph = managed_campaign_with_tasks.project.types.create(name="Paragraph")
    line = managed_campaign_with_tasks.project.types.get(name="Line")
    word = managed_campaign_with_tasks.project.types.create(name="Word")
    managed_campaign_with_tasks.mode = CampaignMode.Elements
    managed_campaign_with_tasks.configuration = {
        "element_types": [
            str(paragraph.id),
            str(line.id),
            str(word.id),
        ]
    }
    managed_campaign_with_tasks.save()

    elements = [
        {"polygon": [[10, 10], [90, 10], [90, 40], [10, 40], [10, 10]], "element_type": str(paragraph.id)},
        {"polygon": [[10, 10], [90, 10], [90, 20], [10, 20], [10, 10]], "element_type": str(line.id)},
        {"polygon": [[10, 20], [90, 20], [90, 30], [10, 30], [10, 20]], "element_type": str(line.id)},
        {"polygon": [[10, 30], [90, 30], [90, 40], [10, 40], [10, 30]], "element_type": str(line.id)},
    ]
    user_task = (
        TaskUser.objects.filter(user=contributor.user, task__campaign=managed_campaign_with_tasks)
        .filter(state=TaskState.Pending)
        .first()
    )
    user_task.annotations.create(
        value={
            "elements": elements
            + [
                # Invalid element type that should be filtered by the view
                {
                    "polygon": [[10, 30], [90, 30], [90, 40], [10, 40], [10, 30]],
                    "element_type": "cafecafe-cafe-cafe-cafe-cafecafecafe",
                }
            ]
        },
    )

    user_task.task.element.polygon = [[0, 0], [100, 0], [100, 50], [0, 50], [0, 0]]
    user_task.task.element.save()

    expected_queries = 12 + 3 * ("annotate" in user_task_url_name)
    with django_assert_num_queries(expected_queries):
        response = contributor.get(reverse(user_task_url_name, kwargs={"pk": user_task.id}))
    assert response.status_code == 200
    assert response.context["user_task"] == user_task
    assert "previous" in response.context
    assert "next" in response.context
    assert response.context["add_pending_filter"]
    assert response.context["previous_elements"] == elements
    assert response.context["element_types"] == [
        {"id": str(line.id), "name": "Line"},
        {"id": str(paragraph.id), "name": "Paragraph"},
        {"id": str(word.id), "name": "Word"},
    ]
    assert response.context["interactive_mode"] == "create"
    assert user_task.annotations.count() == 1


@pytest.mark.parametrize(
    "user_task_url_name",
    [
        USER_TASK_ANNOTATE_URL_NAMES[CampaignMode.Elements],
        USER_TASK_MODERATE_URL_NAMES[CampaignMode.Elements],
    ],
)
def test_manage_elements_errors(
    user_task_url_name, contributor, managed_campaign_with_tasks, django_assert_num_queries
):
    if "moderate" in user_task_url_name:
        managed_campaign_with_tasks.project.memberships.filter(user=contributor.user).update(role=Role.Moderator)

    paragraph = managed_campaign_with_tasks.project.types.create(name="Paragraph")
    line = managed_campaign_with_tasks.project.types.get(name="Line")
    managed_campaign_with_tasks.mode = CampaignMode.Elements
    managed_campaign_with_tasks.configuration = {
        "element_types": [
            str(paragraph.id),
            str(line.id),
        ]
    }
    managed_campaign_with_tasks.save()

    user_task = TaskUser.objects.filter(
        task__campaign_id=managed_campaign_with_tasks.id, state=TaskState.Pending, user=contributor.user
    ).first()

    user_task.task.element.polygon = [[0, 0], [100, 0], [100, 50], [0, 50], [0, 0]]
    user_task.task.element.save()

    values = [
        {"polygon": "[[10, 10], [90, 10], [90, 20], [10, 20], [10, 10]]", "element_type": str(line.id)},
        # Invalid polygon and element_type
        {"polygon": "[[1, 1], [2, 2]]", "element_type": "unknown type"},
    ]
    data = {
        "form-TOTAL_FORMS": len(values),
        "form-INITIAL_FORMS": 0,
        **{f"form-{i}-{key}": val for i, value in enumerate(values) for key, val in value.items()},
    }

    expected_queries = 14 + ("annotate" in user_task_url_name)
    with django_assert_num_queries(expected_queries):
        response = contributor.post(reverse(user_task_url_name, kwargs={"pk": user_task.id}), data)
    assert response.status_code == 200

    form = response.context["form"]
    assert len(form.errors) == 2
    assert form.errors == [
        {},
        {
            "polygon": ["Polygon field must be a list of at least 3 positive integer couples"],
            "element_type": ["Select a valid choice. unknown type is not one of the available choices."],
        },
    ]

    user_task.refresh_from_db()

    assert user_task.state == TaskState.Pending
    assert not user_task.annotations.exists()


@pytest.mark.parametrize("default_parent", [True, False])
@pytest.mark.parametrize("has_parent", [True, False])
def test_annotate_elements(
    contributor,
    managed_campaign_with_tasks,
    default_parent,
    has_parent,
    django_assert_num_queries,
):
    paragraph = managed_campaign_with_tasks.project.types.create(name="Paragraph")
    line = managed_campaign_with_tasks.project.types.get(name="Line")
    managed_campaign_with_tasks.mode = CampaignMode.Elements
    managed_campaign_with_tasks.configuration = {
        "element_types": [
            str(paragraph.id),
            str(line.id),
        ]
    }
    managed_campaign_with_tasks.save()

    user_task = TaskUser.objects.filter(
        task__campaign_id=managed_campaign_with_tasks.id, state=TaskState.Pending, user=contributor.user
    ).first()

    user_task.task.element.polygon = [[0, 0], [100, 0], [100, 50], [0, 50], [0, 0]]
    user_task.task.element.save()

    other_annotation = None
    last_annotation = None
    if has_parent:
        other_annotation = user_task.annotations.create(
            version=6,
            value={
                "elements": [
                    {"polygon": [[10, 10], [90, 10], [90, 40], [10, 40], [10, 10]], "element_type": str(paragraph.id)}
                ]
            },
        )
        last_annotation = user_task.annotations.create(
            version=42,
            value={
                "elements": [
                    {"polygon": [[10, 10], [90, 10], [90, 20], [10, 20], [10, 10]], "element_type": str(line.id)},
                ]
            },
        )
        user_task.state = TaskState.Annotated
        user_task.save()

    expected = [
        {"polygon": [[10, 10], [90, 10], [90, 20], [10, 20], [10, 10]], "element_type": str(line.id)},
        {"polygon": [[10, 20], [90, 20], [90, 30], [10, 30], [10, 20]], "element_type": str(line.id)},
        {"polygon": [[10, 30], [90, 30], [90, 40], [10, 40], [10, 30]], "element_type": str(line.id)},
    ]
    data = {
        "form-TOTAL_FORMS": len(expected),
        "form-INITIAL_FORMS": 0,
        **{
            f"form-{i}-{key}": val if isinstance(val, str) else json.dumps(val)
            for i, value in enumerate(expected)
            for key, val in value.items()
        },
    }

    annotate_url = user_task.annotate_url
    with django_assert_num_queries(18):
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
    assert annotation.value == {"elements": expected}


@pytest.mark.parametrize("new_value", [True, False])
def test_validate_elements(
    user,
    managed_campaign_with_tasks,
    new_value,
    django_assert_num_queries,
):
    paragraph = managed_campaign_with_tasks.project.types.create(name="Paragraph")
    line = managed_campaign_with_tasks.project.types.get(name="Line")
    managed_campaign_with_tasks.mode = CampaignMode.Elements
    managed_campaign_with_tasks.configuration = {
        "element_types": [
            str(paragraph.id),
            str(line.id),
        ]
    }
    managed_campaign_with_tasks.save()

    user_task = (
        TaskUser.objects.filter(task__campaign_id=managed_campaign_with_tasks.id, state=TaskState.Pending)
        .order_by("task__created", "task_id", "created", "id")
        .first()
    )

    user_task.task.element.polygon = [[0, 0], [100, 0], [100, 50], [0, 50], [0, 0]]
    user_task.task.element.save()

    user_task.annotations.create(
        version=6,
        value={
            "elements": [
                {"polygon": [[10, 10], [90, 10], [90, 40], [10, 40], [10, 10]], "element_type": str(paragraph.id)}
            ]
        },
    )
    last_annotation = user_task.annotations.create(
        version=42,
        value={
            "elements": [
                {"polygon": [[10, 10], [90, 10], [90, 20], [10, 20], [10, 10]], "element_type": str(line.id)},
            ]
        },
    )
    user_task.state = TaskState.Annotated
    user_task.save()

    expected = (
        [
            {"polygon": [[10, 10], [90, 10], [90, 20], [10, 20], [10, 10]], "element_type": str(line.id)},
            {"polygon": [[10, 20], [90, 20], [90, 30], [10, 30], [10, 20]], "element_type": str(line.id)},
            {"polygon": [[10, 30], [90, 30], [90, 40], [10, 40], [10, 30]], "element_type": str(line.id)},
        ]
        if new_value
        else last_annotation.value["elements"]
    )
    data = {
        "form-TOTAL_FORMS": len(expected),
        "form-INITIAL_FORMS": 0,
        **{
            f"form-{i}-{key}": val if isinstance(val, str) else json.dumps(val)
            for i, value in enumerate(expected)
            for key, val in value.items()
        },
    }

    expected_queries = 13 + (new_value) * 4
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
        assert annotation.value == {"elements": expected}
    else:
        assert annotation == last_annotation
