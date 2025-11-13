import json
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
from callico.projects.models import CampaignMode, Element, Role

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "user_task_url_name",
    [
        USER_TASK_ANNOTATE_URL_NAMES[CampaignMode.ElementGroup],
        USER_TASK_MODERATE_URL_NAMES[CampaignMode.ElementGroup],
    ],
)
def test_manage_element_group(user_task_url_name, contributor, managed_campaign_with_tasks, django_assert_num_queries):
    if "moderate" in user_task_url_name:
        managed_campaign_with_tasks.project.memberships.filter(user=contributor.user).update(role=Role.Moderator)

    page = managed_campaign_with_tasks.project.types.get(name="Page")
    paragraph = managed_campaign_with_tasks.project.types.create(name="Paragraph")
    managed_campaign_with_tasks.mode = CampaignMode.ElementGroup
    managed_campaign_with_tasks.configuration = {"carousel_type": str(page.id), "group_type": str(paragraph.id)}
    managed_campaign_with_tasks.save()

    user_task = TaskUser.objects.filter(
        task__campaign_id=managed_campaign_with_tasks.id,
        state=TaskState.Pending,
        user=contributor.user,
        task__element__parent_id__isnull=False,
    ).first()

    element = user_task.task.element
    user_task.task.element = element.parent
    user_task.task.save()

    lines = Element.objects.bulk_create(
        Element(
            name=f"Line {i}",
            type=element.project.types.get(name="Line"),
            parent=element,
            project=element.project,
            provider=element.provider,
            provider_object_id=str(uuid.uuid4()),
            image=element.image,
            polygon=[[i, i], [i + 1, i + 1], [i + 2, i + 2]],
            order=i + 3,
        )
        for i in range(1, 5)
    )
    line_ids = [str(line.id) for line in lines]
    groups = [
        {"elements": line_ids[:2]},
        {"elements": line_ids[2:4]},
        {"elements": line_ids[3:]},
    ]

    user_task.annotations.create(
        value={
            # Invalid element ID that should be filtered by the view
            "groups": [
                {
                    **group,
                    "elements": group["elements"] + ["cafecafe-cafe-cafe-cafe-cafecafecafe"],
                }
                for group in groups
            ]
        },
    )

    expected_queries = 15 + 3 * ("annotate" in user_task_url_name)
    with django_assert_num_queries(expected_queries):
        response = contributor.get(reverse(user_task_url_name, kwargs={"pk": user_task.id}))
    assert response.status_code == 200
    assert response.context["user_task"] == user_task
    assert "previous" in response.context
    assert "next" in response.context
    assert response.context["add_pending_filter"]
    assert response.context["carousel_type"] == page.name
    assert response.context["carousel_element_ids"] == json.dumps(
        [
            str(element_id)
            for element_id in user_task.task.element.all_children().filter(type=page).values_list("id", flat=True)
        ]
    )
    assert response.context["previous_groups"] == groups
    assert response.context["group_type"] == paragraph.name
    assert response.context["interactive_mode"] == "select"
    assert user_task.annotations.count() == 1


@pytest.mark.parametrize(
    "user_task_url_name",
    [
        USER_TASK_ANNOTATE_URL_NAMES[CampaignMode.ElementGroup],
        USER_TASK_MODERATE_URL_NAMES[CampaignMode.ElementGroup],
    ],
)
def test_manage_element_group_errors(
    user_task_url_name, contributor, managed_campaign_with_tasks, django_assert_num_queries
):
    if "moderate" in user_task_url_name:
        managed_campaign_with_tasks.project.memberships.filter(user=contributor.user).update(role=Role.Moderator)

    page = managed_campaign_with_tasks.project.types.get(name="Page")
    paragraph = managed_campaign_with_tasks.project.types.create(name="Paragraph")
    managed_campaign_with_tasks.mode = CampaignMode.ElementGroup
    managed_campaign_with_tasks.configuration = {"carousel_type": str(page.id), "group_type": str(paragraph.id)}
    managed_campaign_with_tasks.save()

    user_task = TaskUser.objects.filter(
        task__campaign_id=managed_campaign_with_tasks.id,
        state=TaskState.Pending,
        user=contributor.user,
        task__element__parent_id__isnull=False,
    ).first()

    element = user_task.task.element
    user_task.task.element = element.parent
    user_task.task.save()

    lines = Element.objects.bulk_create(
        Element(
            name=f"Line {i}",
            type=element.project.types.get(name="Line"),
            parent=element,
            project=element.project,
            provider=element.provider,
            provider_object_id=str(uuid.uuid4()),
            image=element.image,
            polygon=[[i, i], [i + 1, i + 1], [i + 2, i + 2]],
            order=i + 3,
        )
        for i in range(1, 5)
    )
    line_ids = [str(line.id) for line in lines]

    values = [
        {"elements": line_ids[:2]},
        # Invalid element ID
        {"elements": line_ids[3:] + ["cafecafe-cafe-cafe-cafe-cafecafecafe"]},
    ]
    data = {
        "form-TOTAL_FORMS": len(values),
        "form-INITIAL_FORMS": 0,
        **{f"form-{i}-{key}": val for i, value in enumerate(values) for key, val in value.items()},
    }

    expected_queries = 18 + ("annotate" in user_task_url_name)
    with django_assert_num_queries(expected_queries):
        response = contributor.post(reverse(user_task_url_name, kwargs={"pk": user_task.id}), data)
    assert response.status_code == 200

    form = response.context["form"]
    assert len(form.errors) == 2
    assert form.errors == [
        {},
        {
            "elements": [
                "Select a valid choice. cafecafe-cafe-cafe-cafe-cafecafecafe is not one of the available choices.",
            ],
        },
    ]

    user_task.refresh_from_db()

    assert user_task.state == TaskState.Pending
    assert not user_task.annotations.exists()


@pytest.mark.parametrize(
    "user_task_url_name",
    [
        USER_TASK_ANNOTATE_URL_NAMES[CampaignMode.ElementGroup],
        USER_TASK_MODERATE_URL_NAMES[CampaignMode.ElementGroup],
    ],
)
def test_manage_element_group_keep_order(
    user_task_url_name, contributor, managed_campaign_with_tasks, django_assert_num_queries
):
    if "moderate" in user_task_url_name:
        managed_campaign_with_tasks.project.memberships.filter(user=contributor.user).update(role=Role.Moderator)

    page = managed_campaign_with_tasks.project.types.get(name="Page")
    paragraph = managed_campaign_with_tasks.project.types.create(name="Paragraph")
    managed_campaign_with_tasks.mode = CampaignMode.ElementGroup
    managed_campaign_with_tasks.configuration = {"carousel_type": str(page.id), "group_type": str(paragraph.id)}
    managed_campaign_with_tasks.save()

    user_task = TaskUser.objects.filter(
        task__campaign_id=managed_campaign_with_tasks.id,
        state=TaskState.Pending,
        user=contributor.user,
        task__element__parent_id__isnull=False,
    ).first()

    element = user_task.task.element
    user_task.task.element = element.parent
    user_task.task.save()

    line = Element.objects.create(
        name="Line x",
        type=element.project.types.get(name="Line"),
        parent=element,
        project=element.project,
        provider=element.provider,
        provider_object_id=str(uuid.uuid4()),
        image=element.image,
        polygon=[[1, 1], [2, 2], [3, 3]],
    )

    paragraph = Element.objects.create(
        name="Paragraph x",
        type=paragraph,
        parent=element,
        project=element.project,
        provider=element.provider,
        provider_object_id=str(uuid.uuid4()),
        image=element.image,
        polygon=[[10, 10], [20, 20], [30, 30]],
    )

    expected = [
        {"elements": [str(line.id), str(paragraph.id)]},
        {"elements": [str(paragraph.id), str(line.id)]},
    ]
    data = {
        "form-TOTAL_FORMS": len(expected),
        "form-INITIAL_FORMS": 0,
        **{f"form-{i}-{key}": val for i, value in enumerate(expected) for key, val in value.items()},
    }

    expected_queries = 20 + ("annotate" in user_task_url_name)
    with django_assert_num_queries(expected_queries):
        response = contributor.post(reverse(user_task_url_name, kwargs={"pk": user_task.id}), data)
    assert response.status_code == 302

    user_task.refresh_from_db()

    assert user_task.state == TaskState.Annotated if "annotate" in user_task_url_name else TaskState.Validated
    assert user_task.annotations.count() == 1

    annotation = user_task.annotations.order_by("-created").first()
    assert annotation.value == {"groups": expected}


@pytest.mark.parametrize("default_parent", [True, False])
@pytest.mark.parametrize("has_parent", [True, False])
def test_annotate_element_group(
    contributor,
    managed_campaign_with_tasks,
    default_parent,
    has_parent,
    django_assert_num_queries,
):
    page = managed_campaign_with_tasks.project.types.get(name="Page")
    paragraph = managed_campaign_with_tasks.project.types.create(name="Paragraph")
    managed_campaign_with_tasks.mode = CampaignMode.ElementGroup
    managed_campaign_with_tasks.configuration = {"carousel_type": str(page.id), "group_type": str(paragraph.id)}
    managed_campaign_with_tasks.save()

    user_task = TaskUser.objects.filter(
        task__campaign_id=managed_campaign_with_tasks.id,
        state=TaskState.Pending,
        user=contributor.user,
        task__element__parent_id__isnull=False,
    ).first()

    element = user_task.task.element
    user_task.task.element = element.parent
    user_task.task.save()

    lines = Element.objects.bulk_create(
        Element(
            name=f"Line {i}",
            type=element.project.types.get(name="Line"),
            parent=element,
            project=element.project,
            provider=element.provider,
            provider_object_id=str(uuid.uuid4()),
            image=element.image,
            polygon=[[i, i], [i + 1, i + 1], [i + 2, i + 2]],
            order=i + 3,
        )
        for i in range(1, 10)
    )
    line_ids = [str(line.id) for line in lines]

    other_annotation = None
    last_annotation = None
    if has_parent:
        other_annotation = user_task.annotations.create(
            version=6,
            value={"groups": [{"elements": line_ids[:3]}]},
        )
        last_annotation = user_task.annotations.create(
            version=42,
            value={"groups": [{"elements": line_ids[4:]}]},
        )
        user_task.state = TaskState.Annotated
        user_task.save()

    expected = [
        {"elements": line_ids[:2]},
        {"elements": line_ids[2:4]},
        {"elements": line_ids[4:]},
    ]
    data = {
        "form-TOTAL_FORMS": len(expected),
        "form-INITIAL_FORMS": 0,
        **{f"form-{i}-{key}": val for i, value in enumerate(expected) for key, val in value.items()},
    }

    expected_queries = 22 + (not has_parent)
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
    assert annotation.value == {"groups": expected}


@pytest.mark.parametrize("new_value", [True, False])
def test_validate_element_group(
    user,
    managed_campaign_with_tasks,
    new_value,
    django_assert_num_queries,
):
    page = managed_campaign_with_tasks.project.types.get(name="Page")
    paragraph = managed_campaign_with_tasks.project.types.create(name="Paragraph")
    managed_campaign_with_tasks.mode = CampaignMode.ElementGroup
    managed_campaign_with_tasks.configuration = {"carousel_type": str(page.id), "group_type": str(paragraph.id)}
    managed_campaign_with_tasks.save()

    user_task = (
        TaskUser.objects.filter(
            task__campaign_id=managed_campaign_with_tasks.id,
            state=TaskState.Pending,
            task__element__parent_id__isnull=False,
        )
        .order_by("task__created", "task_id", "created", "id")
        .first()
    )

    element = user_task.task.element
    user_task.task.element = element.parent
    user_task.task.save()

    lines = Element.objects.bulk_create(
        Element(
            name=f"Line {i}",
            type=element.project.types.get(name="Line"),
            parent=element,
            project=element.project,
            provider=element.provider,
            provider_object_id=str(uuid.uuid4()),
            image=element.image,
            polygon=[[i, i], [i + 1, i + 1], [i + 2, i + 2]],
            order=i + 3,
        )
        for i in range(1, 10)
    )
    line_ids = [str(line.id) for line in lines]

    user_task.annotations.create(
        version=6,
        value={"groups": [{"elements": line_ids[:3]}]},
    )
    last_annotation = user_task.annotations.create(
        version=42,
        value={"groups": [{"elements": line_ids[4:]}]},
    )
    user_task.state = TaskState.Annotated
    user_task.save()

    expected = (
        [
            {"elements": line_ids[:2]},
            {"elements": line_ids[2:4]},
            {"elements": line_ids[4:]},
        ]
        if new_value
        else last_annotation.value["groups"]
    )
    data = {
        "form-TOTAL_FORMS": len(expected),
        "form-INITIAL_FORMS": 0,
        **{f"form-{i}-{key}": val for i, value in enumerate(expected) for key, val in value.items()},
    }

    expected_queries = 15 + (new_value) * 6
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
        assert annotation.value == {"groups": expected}
    else:
        assert annotation == last_annotation
