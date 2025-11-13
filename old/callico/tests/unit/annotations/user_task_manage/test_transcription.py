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
        USER_TASK_ANNOTATE_URL_NAMES[CampaignMode.Transcription],
        USER_TASK_MODERATE_URL_NAMES[CampaignMode.Transcription],
    ],
)
def test_manage_transcription(user_task_url_name, contributor, managed_campaign_with_tasks, django_assert_num_queries):
    if "moderate" in user_task_url_name:
        managed_campaign_with_tasks.project.memberships.filter(user=contributor.user).update(role=Role.Moderator)

    managed_campaign_with_tasks.mode = CampaignMode.Transcription
    page_type = managed_campaign_with_tasks.project.types.get(name="Page")
    managed_campaign_with_tasks.configuration = {"children_types": [str(page_type.id)], "display_grouped_inputs": True}
    managed_campaign_with_tasks.save()

    user_task = TaskUser.objects.filter(
        task__campaign_id=managed_campaign_with_tasks.id, state=TaskState.Pending, user=contributor.user
    ).first()

    expected_queries = 12 + ("annotate" in user_task_url_name)
    with django_assert_num_queries(expected_queries):
        response = contributor.get(reverse(user_task_url_name, kwargs={"pk": user_task.id}))
    assert response.status_code == 200
    assert response.context["user_task"] == user_task
    assert "previous" in response.context
    assert "next" in response.context
    assert response.context["add_pending_filter"]
    assert response.context["interactive_mode"] == "select"
    assert response.context["light_display"]
    assert user_task.annotations.count() == 0


@pytest.mark.parametrize("default_parent", [True, False])
@pytest.mark.parametrize("children_exist", [True, False])
@pytest.mark.parametrize("has_parent", [True, False])
def test_annotate_transcription(
    contributor,
    managed_campaign_with_tasks,
    default_parent,
    children_exist,
    has_parent,
    django_assert_num_queries,
):
    managed_campaign_with_tasks.mode = CampaignMode.Transcription
    managed_campaign_with_tasks.save()

    user_task = TaskUser.objects.filter(
        task__campaign_id=managed_campaign_with_tasks.id, state=TaskState.Pending, user=contributor.user
    ).first()

    element = user_task.task.element

    other_annotation = None
    last_annotation = None
    if has_parent:
        other_annotation = user_task.annotations.create(
            version=6,
            value={"transcription": {str(element.id): {"text": "...", "uncertain": True}}},
        )
        last_annotation = user_task.annotations.create(
            version=42,
            value={
                "transcription": {
                    str(element.id): {
                        "text": "Er det lykkedes dig at find sproget i denne sætning?",
                        "uncertain": True,
                    }
                }
            },
        )
        user_task.state = TaskState.Annotated
        user_task.save()

    elements = [element]
    if children_exist:
        values = ["Bonjour", "Ciao", "Hello", "Hola", "你好", "侵入者だ!", "Päivää", "Pozdravljeni", "Witaj"]
        elements += Element.objects.bulk_create(
            Element(
                name=f"Line {i}",
                type=element.project.types.get(name="Line"),
                parent=element,
                project=element.project,
                provider=element.provider,
                provider_object_id=str(uuid.uuid4()),
                image=element.image,
                polygon=[[1, 2], [2, 3], [3, 4]],
                order=i,
            )
            for i in range(len(values) - 1)
        )
    else:
        values = ["If you are reading this,\n know that you are a wonderful person"]

    expected = {str(element.id): {"text": value, "uncertain": False} for element, value in zip(elements, values)}
    data = {
        "form-TOTAL_FORMS": len(values),
        "form-INITIAL_FORMS": len(values),
        **{f"form-{i}-annotation": f"\n {value} \n\t" for i, value in enumerate(values)},
    }

    expected_queries = 18 + children_exist + (not has_parent)
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
    assert annotation.value == {"transcription": expected}


@pytest.mark.parametrize("children_exist", [True, False])
@pytest.mark.parametrize("new_value", [True, False])
def test_validate_transcription(
    user,
    managed_campaign_with_tasks,
    children_exist,
    new_value,
    django_assert_num_queries,
):
    managed_campaign_with_tasks.mode = CampaignMode.Transcription
    managed_campaign_with_tasks.save()

    user_task = (
        TaskUser.objects.filter(task__campaign_id=managed_campaign_with_tasks.id, state=TaskState.Pending)
        .order_by("task__created", "task_id", "created", "id")
        .first()
    )

    element = user_task.task.element
    elements = [element]

    values = (
        ["Bonjour", "Ciao", "Hello", "Hola", "你好", "侵入者だ!", "Päivää", "Pozdravljeni", "Witaj"]
        if children_exist
        else ["If you are reading this,\n know that you are a wonderful person"]
    )
    if len(values) > 1:
        elements += Element.objects.bulk_create(
            Element(
                name=f"Line {i}",
                type=element.project.types.get(name="Line"),
                parent=element,
                project=element.project,
                provider=element.provider,
                provider_object_id=str(uuid.uuid4()),
                image=element.image,
                polygon=[[1, 2], [2, 3], [3, 4]],
                order=i,
            )
            for i in range(len(values) - 1)
        )

    user_task.annotations.create(
        version=6,
        value={"transcription": {str(element.id): {"text": "...", "uncertain": True}}},
    )
    last_annotation = user_task.annotations.create(
        version=42,
        value={
            "transcription": {
                str(element.id): {"text": value, "uncertain": True} for element, value in zip(elements, values)
            }
        },
    )
    user_task.state = TaskState.Annotated
    user_task.save()

    expected = (
        {str(element.id): {"text": f"new {value}", "uncertain": False} for element, value in zip(elements, values)}
        if new_value
        else last_annotation.value["transcription"]
    )
    data = {
        "form-TOTAL_FORMS": len(values),
        "form-INITIAL_FORMS": len(values),
        **{
            f"form-{i}-{key}": f"\n {val} \n\t" if isinstance(val, str) else val
            for i, transcription in enumerate(expected.values())
            for key, val in zip(["annotation", "uncertain"], [transcription["text"], transcription["uncertain"]])
        },
    }

    expected_queries = 13 + children_exist + (new_value) * 5
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
        assert annotation.value == {"transcription": expected}
    else:
        assert annotation == last_annotation
