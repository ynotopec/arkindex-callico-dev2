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
        USER_TASK_ANNOTATE_URL_NAMES[CampaignMode.Classification],
        USER_TASK_MODERATE_URL_NAMES[CampaignMode.Classification],
    ],
)
def test_manage_classification(user_task_url_name, contributor, managed_campaign_with_tasks, django_assert_num_queries):
    if "moderate" in user_task_url_name:
        managed_campaign_with_tasks.project.memberships.filter(user=contributor.user).update(role=Role.Moderator)

    managed_campaign_with_tasks.mode = CampaignMode.Classification
    managed_campaign_with_tasks.save()

    user_task = (
        TaskUser.objects.filter(user=contributor.user, task__campaign=managed_campaign_with_tasks)
        .filter(state=TaskState.Pending)
        .first()
    )

    with django_assert_num_queries(12):
        response = contributor.get(reverse(user_task_url_name, kwargs={"pk": user_task.id}))
    assert response.status_code == 200
    assert response.context["user_task"] == user_task
    assert "previous" in response.context
    assert "next" in response.context
    assert response.context["add_pending_filter"]
    assert user_task.annotations.count() == 0


@pytest.mark.parametrize("default_parent", [True, False])
@pytest.mark.parametrize("has_parent", [True, False])
def test_annotate_classification(
    contributor,
    managed_campaign_with_tasks,
    default_parent,
    has_parent,
    django_assert_num_queries,
):
    dog_class = managed_campaign_with_tasks.project.classes.create(name="dog")
    cat_class = managed_campaign_with_tasks.project.classes.create(name="cat")
    fish_class = managed_campaign_with_tasks.project.classes.create(name="fish")

    managed_campaign_with_tasks.mode = CampaignMode.Classification
    managed_campaign_with_tasks.save()

    user_task = TaskUser.objects.filter(
        task__campaign_id=managed_campaign_with_tasks.id, state=TaskState.Pending, user=contributor.user
    ).first()

    other_annotation = None
    last_annotation = None
    if has_parent:
        other_annotation = user_task.annotations.create(
            version=6,
            value={"classification": str(dog_class.id)},
        )
        last_annotation = user_task.annotations.create(
            version=42,
            value={"classification": str(cat_class.id)},
        )
        user_task.state = TaskState.Annotated
        user_task.save()

    value = str(fish_class.id)
    data = {value: fish_class.name}

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
    assert annotation.value == {"classification": value}


@pytest.mark.parametrize("new_value", [True, False])
def test_validate_classification(
    user,
    managed_campaign_with_tasks,
    new_value,
    django_assert_num_queries,
):
    dog_class = managed_campaign_with_tasks.project.classes.create(name="dog")
    cat_class = managed_campaign_with_tasks.project.classes.create(name="cat")
    fish_class = managed_campaign_with_tasks.project.classes.create(name="fish")

    managed_campaign_with_tasks.mode = CampaignMode.Classification
    managed_campaign_with_tasks.save()

    user_task = (
        TaskUser.objects.filter(task__campaign_id=managed_campaign_with_tasks.id, state=TaskState.Pending)
        .order_by("task__created", "task_id", "created", "id")
        .first()
    )

    user_task.annotations.create(
        version=6,
        value={"classification": str(dog_class.id)},
    )
    last_annotation = user_task.annotations.create(
        version=42,
        value={"classification": str(cat_class.id)},
    )
    user_task.state = TaskState.Annotated
    user_task.save()

    project_type = fish_class if new_value else cat_class
    value = str(project_type.id)
    data = {value: project_type.name}

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
        assert annotation.value == {"classification": value}
    else:
        assert annotation == last_annotation
