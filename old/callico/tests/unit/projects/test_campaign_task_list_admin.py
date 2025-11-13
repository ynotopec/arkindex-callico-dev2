import random

import pytest
from django.db.models.query import QuerySet
from django.urls import reverse
from pytest_lazy_fixtures import lf as lazy_fixture

from callico.annotations.models import TaskState
from callico.projects.forms import (
    NO_USER,
    USER_TASK_ALL_FEEDBACKS,
    USER_TASK_NO_FEEDBACK,
    USER_TASK_UNCERTAIN_FEEDBACK,
    USER_TASK_WITH_COMMENTS,
)

pytestmark = pytest.mark.django_db


def test_campaign_task_list_admin_anonymous(anonymous, campaign):
    "An anonymous user is redirected to the login page"
    list_url = reverse("admin-campaign-task-list", kwargs={"pk": campaign.id})
    response = anonymous.get(list_url)
    assert response.status_code == 302
    assert response.url == reverse("login") + f"?next={list_url}"


@pytest.mark.parametrize(
    "forbidden_campaign",
    [
        # Hidden campaign
        lazy_fixture("hidden_campaign"),
        # Public campaign
        lazy_fixture("public_campaign"),
        # Contributor rights on campaign project
        lazy_fixture("campaign"),
    ],
)
def test_campaign_task_list_admin_forbidden(user, forbidden_campaign):
    response = user.get(reverse("admin-campaign-task-list", kwargs={"pk": forbidden_campaign.id}))
    assert response.status_code == 403


def test_campaign_task_list_archived_campaign(user, archived_campaign):
    response = user.get(reverse("admin-campaign-task-list", kwargs={"pk": archived_campaign.id}))
    assert response.status_code == 403
    assert str(response.context["error_message"]) == "You cannot list the tasks of a campaign marked as Archived"


def test_campaign_task_list_admin_wrong_campaign_id(user):
    response = user.get(reverse("admin-campaign-task-list", kwargs={"pk": "cafecafe-cafe-cafe-cafe-cafecafecafe"}))
    assert response.status_code == 404
    assert response.context["exception"] == "No campaign matching this ID exists"


def test_campaign_task_list_admin_invalid_user(user, managed_campaign_with_tasks):
    response = user.get(
        reverse("admin-campaign-task-list", kwargs={"pk": managed_campaign_with_tasks.id}),
        {"state": TaskState.Pending, "user_id": user.user.id},
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 1
    assert form.errors == {"user_id": [f"Select a valid choice. {user.user.id} is not one of the available choices."]}


def test_campaign_task_list_admin_invalid_state(user, contributor, managed_campaign_with_tasks):
    response = user.get(
        reverse("admin-campaign-task-list", kwargs={"pk": managed_campaign_with_tasks.id}),
        {"state": "unknown state", "user_id": contributor.user.id},
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 1
    assert form.errors == {"state": ["Select a valid choice. unknown state is not one of the available choices."]}


def test_campaign_task_list_admin_invalid_user_feedback(user, contributor, managed_campaign_with_tasks):
    response = user.get(
        reverse("admin-campaign-task-list", kwargs={"pk": managed_campaign_with_tasks.id}),
        {"user_feedback": "unknown feedback", "user_id": contributor.user.id},
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 1
    assert form.errors == {
        "user_feedback": ["Select a valid choice. unknown feedback is not one of the available choices."]
    }


@pytest.mark.parametrize("state_filter", ["", random.choice(list(TaskState))])
def test_campaign_task_list_admin_state_filter(
    user, managed_campaign_with_tasks, state_filter, django_assert_num_queries
):
    filters = {"user_tasks__isnull": False}
    if state_filter:
        filters["user_tasks__state"] = state_filter

    tasks = managed_campaign_with_tasks.tasks.filter(**filters).distinct().order_by("created")

    with django_assert_num_queries(12):
        response = user.get(
            reverse("admin-campaign-task-list", kwargs={"pk": managed_campaign_with_tasks.id}),
            {"state": state_filter},
        )
    assert response.status_code == 200

    assert isinstance(response.context.get("object_list"), QuerySet)
    assert list(response.context["tasks"].values_list("id", flat=True)) == list(tasks.values_list("id", flat=True))

    assert response.context["campaign"] == managed_campaign_with_tasks


@pytest.mark.parametrize(
    "user_feedback_filter",
    ["", USER_TASK_NO_FEEDBACK, USER_TASK_WITH_COMMENTS, USER_TASK_UNCERTAIN_FEEDBACK, USER_TASK_ALL_FEEDBACKS],
)
def test_campaign_task_list_admin_user_feedback_filter(
    user, managed_campaign_with_tasks, user_feedback_filter, django_assert_num_queries
):
    tasks = managed_campaign_with_tasks.tasks.filter(user_tasks__isnull=False)
    # Add comments on the first task
    with_comments_task = tasks.first()
    with_comments_task.comments.create(user=user.user, content="Something went wrong")
    # Update the "has_uncertain_value" of the second user tasks
    uncertain_task = tasks.exclude(id=with_comments_task.id).first()
    uncertain_task.user_tasks.update(has_uncertain_value=True)
    # Add a comment + update the "has_uncertain_value" of the third user tasks
    all_feedbacks_task = tasks.exclude(id__in=[with_comments_task.id, uncertain_task.id]).first()
    all_feedbacks_task.comments.create(user=user.user, content="Oops")
    all_feedbacks_task.user_tasks.update(has_uncertain_value=True)

    filters = {"user_tasks__isnull": False}
    if user_feedback_filter in [USER_TASK_WITH_COMMENTS, USER_TASK_ALL_FEEDBACKS]:
        filters["comments__isnull"] = False
    if user_feedback_filter in [USER_TASK_UNCERTAIN_FEEDBACK, USER_TASK_ALL_FEEDBACKS]:
        filters["user_tasks__has_uncertain_value"] = True
    if user_feedback_filter == USER_TASK_NO_FEEDBACK:
        filters["comments__isnull"] = True
        filters["user_tasks__has_uncertain_value"] = False

    tasks = managed_campaign_with_tasks.tasks.filter(**filters).distinct().order_by("created")

    with django_assert_num_queries(12):
        response = user.get(
            reverse("admin-campaign-task-list", kwargs={"pk": managed_campaign_with_tasks.id}),
            {"user_feedback": user_feedback_filter},
        )
    assert response.status_code == 200

    assert isinstance(response.context.get("object_list"), QuerySet)
    assert list(response.context["tasks"].values_list("id", flat=True)) == list(tasks.values_list("id", flat=True))

    assert response.context["campaign"] == managed_campaign_with_tasks


@pytest.mark.parametrize("user_filter", ["", NO_USER, lazy_fixture("contributor")])
def test_campaign_task_list_admin_user_filter(
    user, managed_campaign_with_tasks, user_filter, django_assert_num_queries
):
    filters = {}
    if user_filter == NO_USER:
        filters["user_tasks__isnull"] = True
    elif user_filter:
        filters["user_tasks__user"] = user_filter.user
    else:
        filters["user_tasks__isnull"] = False

    tasks = managed_campaign_with_tasks.tasks.filter(**filters).distinct().order_by("created")

    expected_query = 8 if user_filter == NO_USER else 12
    with django_assert_num_queries(expected_query):
        response = user.get(
            reverse("admin-campaign-task-list", kwargs={"pk": managed_campaign_with_tasks.id}),
            {"user_id": user_filter.user.id if not isinstance(user_filter, str) else user_filter},
        )
    assert response.status_code == 200

    assert isinstance(response.context.get("object_list"), QuerySet)
    assert list(response.context["tasks"].values_list("id", flat=True)) == list(tasks.values_list("id", flat=True))
    if not isinstance(user_filter, str):
        for task in response.context["tasks"]:
            assert set(task.user_tasks.values_list("user_id", flat=True)) == {user_filter.user.id}

    assert response.context["campaign"] == managed_campaign_with_tasks
