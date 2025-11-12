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
        USER_TASK_ANNOTATE_URL_NAMES[CampaignMode.EntityForm],
        USER_TASK_MODERATE_URL_NAMES[CampaignMode.EntityForm],
    ],
)
def test_manage_entity_form(user_task_url_name, contributor, managed_campaign_with_tasks, django_assert_num_queries):
    if "moderate" in user_task_url_name:
        managed_campaign_with_tasks.project.memberships.filter(user=contributor.user).update(role=Role.Moderator)

    managed_campaign_with_tasks.mode = CampaignMode.EntityForm
    managed_campaign_with_tasks.save()

    user_task = TaskUser.objects.filter(
        task__campaign_id=managed_campaign_with_tasks.id, state=TaskState.Pending, user=contributor.user
    ).first()

    expected_queries = 11 + ("annotate" in user_task_url_name)
    with django_assert_num_queries(expected_queries):
        response = contributor.get(reverse(user_task_url_name, kwargs={"pk": user_task.id}))
    assert response.status_code == 200
    assert response.context["user_task"] == user_task
    assert "previous" in response.context
    assert "next" in response.context
    assert response.context["add_pending_filter"]
    assert user_task.annotations.count() == 0


@pytest.mark.parametrize(
    "user_task_url_name",
    [
        USER_TASK_ANNOTATE_URL_NAMES[CampaignMode.EntityForm],
        USER_TASK_MODERATE_URL_NAMES[CampaignMode.EntityForm],
    ],
)
def test_manage_entity_form_errors(
    user_task_url_name, contributor, managed_campaign_with_tasks, authority, django_assert_num_queries
):
    if "moderate" in user_task_url_name:
        managed_campaign_with_tasks.project.memberships.filter(user=contributor.user).update(role=Role.Moderator)

    managed_campaign_with_tasks.mode = CampaignMode.EntityForm
    managed_campaign_with_tasks.configuration = {
        "fields": [
            {"entity_type": "first_name", "instruction": "The first name", "validation_regex": "^[A-Z]+.*$"},
            {"entity_type": "last_name", "instruction": "The last name"},
            {
                "entity_type": "country",
                "instruction": "The country",
                "from_authority": str(authority.id),
            },
            {
                "entity_type": "gender",
                "instruction": "The gender",
                "predefined_choices": "female, male, non-binary",
            },
        ]
    }
    managed_campaign_with_tasks.save()

    user_task = TaskUser.objects.filter(
        task__campaign_id=managed_campaign_with_tasks.id, state=TaskState.Pending, user=contributor.user
    ).first()

    # The first_name doesn't match the validation_regex
    # The country is not one of the available values
    values = ["bob", "Doe", "Oops", "non-binary"]

    data = {
        "form-TOTAL_FORMS": len(values),
        "form-INITIAL_FORMS": 0,
        **{f"form-{i}-annotation": f"\n {value} \n\t" for i, value in enumerate(values)},
    }

    expected_queries = 12 + ("annotate" in user_task_url_name)
    with django_assert_num_queries(expected_queries):
        response = contributor.post(reverse(user_task_url_name, kwargs={"pk": user_task.id}), data)
    assert response.status_code == 200

    form = response.context["form"]
    assert len(form.errors) == 4
    assert form.errors == [
        {
            "annotation": [
                "Invalid format, please refer to the instructions.",
            ],
        },
        {},
        {
            "annotation": [
                "Oops is not one of the allowed authority values.",
            ],
        },
        {},
    ]

    user_task.refresh_from_db()

    assert user_task.state == TaskState.Pending
    assert not user_task.annotations.exists()


@pytest.mark.parametrize("default_parent", [True, False])
@pytest.mark.parametrize("has_parent", [True, False])
def test_annotate_entity_form(
    contributor,
    managed_campaign_with_tasks,
    authority,
    default_parent,
    has_parent,
    django_assert_num_queries,
):
    managed_campaign_with_tasks.mode = CampaignMode.EntityForm
    managed_campaign_with_tasks.configuration = {
        "fields": [
            {"entity_type": "first_name", "instruction": "The first name", "validation_regex": "^[A-Z]+.*$"},
            {"entity_type": "last_name", "instruction": "The last name"},
            {
                "entity_type": "country",
                "instruction": "The country",
                "from_authority": str(authority.id),
            },
            {
                "entity_type": "gender",
                "instruction": "The gender",
                "predefined_choices": "female, male, non-binary",
            },
        ]
    }
    managed_campaign_with_tasks.save()

    user_task = TaskUser.objects.filter(
        task__campaign_id=managed_campaign_with_tasks.id, state=TaskState.Pending, user=contributor.user
    ).first()

    other_annotation = None
    last_annotation = None
    if has_parent:
        other_annotation = user_task.annotations.create(
            version=6,
            value={
                "values": [
                    {
                        "entity_type": "first_name",
                        "value": "Bouloum",
                        "uncertain": True,
                        "instruction": "The first name",
                    },
                    {
                        "entity_type": "last_name",
                        "value": "Ooops",
                        "uncertain": True,
                        "instruction": "The last name",
                    },
                    {
                        "entity_type": "country",
                        "value": "Italy",
                        "uncertain": True,
                        "instruction": "The country",
                    },
                    {
                        "entity_type": "gender",
                        "value": "male",
                        "uncertain": True,
                        "instruction": "The gender",
                    },
                ]
            },
        )
        last_annotation = user_task.annotations.create(
            version=42,
            value={
                "values": [
                    {
                        "entity_type": "first_name",
                        "value": "Boooooby",
                        "uncertain": True,
                        "instruction": "The first name",
                    },
                    {
                        "entity_type": "last_name",
                        "value": "Doe",
                        "uncertain": True,
                        "instruction": "The last name",
                    },
                    {
                        "entity_type": "country",
                        "value": "Germany",
                        "uncertain": True,
                        "instruction": "The country",
                    },
                    {
                        "entity_type": "gender",
                        "value": "female",
                        "uncertain": True,
                        "instruction": "The gender",
                    },
                ]
            },
        )
        user_task.state = TaskState.Annotated
        user_task.save()

    values = ["Bob", "Doe", "France", "non-binary"]

    expected = [
        {
            "entity_type": entity_type,
            "value": value,
            "uncertain": False,
            "instruction": f"The {entity_type.replace('_', ' ')}",
        }
        for entity_type, value in zip(["first_name", "last_name", "country", "gender"], values)
    ]
    data = {
        "form-TOTAL_FORMS": len(values),
        "form-INITIAL_FORMS": len(values),
        **{f"form-{i}-annotation": f"\n {value} \n\t" for i, value in enumerate(values)},
    }

    expected_queries = 18 + (not has_parent) * 2
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
    assert annotation.value == {"values": expected}


@pytest.mark.parametrize("new_value", [True, False])
def test_validate_entity_form(
    user,
    managed_campaign_with_tasks,
    authority,
    new_value,
    django_assert_num_queries,
):
    managed_campaign_with_tasks.mode = CampaignMode.EntityForm
    managed_campaign_with_tasks.configuration = {
        "fields": [
            {"entity_type": "first_name", "instruction": "The first name", "validation_regex": "^[A-Z]+.*$"},
            {"entity_type": "last_name", "instruction": "The last name"},
            {
                "entity_type": "country",
                "instruction": "The country",
                "from_authority": str(authority.id),
            },
            {
                "entity_type": "gender",
                "instruction": "The gender",
                "predefined_choices": "female, male, non-binary",
            },
        ]
    }
    managed_campaign_with_tasks.save()

    user_task = (
        TaskUser.objects.filter(task__campaign_id=managed_campaign_with_tasks.id, state=TaskState.Pending)
        .order_by("task__created", "task_id", "created", "id")
        .first()
    )

    user_task.annotations.create(
        version=6,
        value={
            "values": [
                {
                    "entity_type": "first_name",
                    "value": "Bouloum",
                    "uncertain": True,
                    "instruction": "The first name",
                },
                {
                    "entity_type": "last_name",
                    "value": "Ooops",
                    "uncertain": True,
                    "instruction": "The last name",
                },
                {
                    "entity_type": "country",
                    "value": "Italy",
                    "uncertain": True,
                    "instruction": "The country",
                },
                {
                    "entity_type": "gender",
                    "value": "male",
                    "uncertain": True,
                    "instruction": "The gender",
                },
            ]
        },
    )
    last_annotation = user_task.annotations.create(
        version=42,
        value={
            "values": [
                {
                    "entity_type": "first_name",
                    "value": "Boooooby",
                    "uncertain": True,
                    "instruction": "The first name",
                },
                {
                    "entity_type": "last_name",
                    "value": "Doe",
                    "uncertain": True,
                    "instruction": "The last name",
                },
                {
                    "entity_type": "country",
                    "value": "Germany",
                    "uncertain": True,
                    "instruction": "The country",
                },
                {
                    "entity_type": "gender",
                    "value": "female",
                    "uncertain": True,
                    "instruction": "The gender",
                },
            ]
        },
    )
    user_task.state = TaskState.Annotated
    user_task.save()

    expected = (
        [
            {
                "entity_type": entity_type,
                "value": value,
                "uncertain": False,
                "instruction": f"The {entity_type.replace('_', ' ')}",
            }
            for entity_type, value in zip(
                ["first_name", "last_name", "country", "gender"], ["Bob", "Doe", "France", "non-binary"]
            )
        ]
        if new_value
        else last_annotation.value["values"]
    )
    data = {
        "form-TOTAL_FORMS": len(expected),
        "form-INITIAL_FORMS": len(expected),
        **{
            f"form-{i}-{key}": f"\n {val} \n\t" if isinstance(val, str) else val
            for i, entity in enumerate(expected)
            for key, val in zip(["annotation", "uncertain"], [entity["value"], entity["uncertain"]])
        },
    }

    expected_queries = 13 + (new_value) * 5
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
        assert annotation.value == {"values": expected}
    else:
        assert annotation == last_annotation
