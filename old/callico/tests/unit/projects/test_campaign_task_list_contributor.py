import random

import pytest
from django.db.models import Count, F, Q
from django.db.models.query import QuerySet
from django.urls import reverse
from pytest_lazy_fixtures import lf as lazy_fixture

from callico.annotations.models import TaskState
from callico.projects.forms import USER_TASK_AVAILABLE_STATE, USER_TASK_UNCERTAIN_FEEDBACK
from callico.projects.models import CAMPAIGN_CLOSED_STATES

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("client", [lazy_fixture("anonymous"), lazy_fixture("user")])
@pytest.mark.parametrize(
    "forbidden_campaign",
    [
        # Hidden campaign
        lazy_fixture("hidden_campaign"),
        # Moderator rights on campaign project
        lazy_fixture("moderated_campaign"),
        # Manager rights on campaign project
        lazy_fixture("managed_campaign"),
    ],
)
def test_campaign_task_list_contributor_forbidden(client, forbidden_campaign):
    response = client.get(reverse("contributor-campaign-task-list", kwargs={"pk": forbidden_campaign.id}))
    assert response.status_code == 403


def test_campaign_task_list_contributor_wrong_campaign_id(contributor):
    response = contributor.get(
        reverse("contributor-campaign-task-list", kwargs={"pk": "cafecafe-cafe-cafe-cafe-cafecafecafe"})
    )
    assert response.status_code == 404
    assert response.context["exception"] == "No campaign matching this ID exists"


@pytest.mark.parametrize("state", CAMPAIGN_CLOSED_STATES)
def test_campaign_task_list_contributor_closed_campaign(state, contributor, managed_campaign_with_tasks):
    managed_campaign_with_tasks.state = state
    managed_campaign_with_tasks.save()

    response = contributor.get(reverse("contributor-campaign-task-list", kwargs={"pk": managed_campaign_with_tasks.id}))
    assert response.status_code == 403
    assert (
        str(response.context["error_message"])
        == f"You cannot list the tasks of a campaign marked as {state.capitalize()}"
    )


def test_campaign_task_list_contributor_invalid_state(contributor, managed_campaign_with_tasks):
    response = contributor.get(
        reverse("contributor-campaign-task-list", kwargs={"pk": managed_campaign_with_tasks.id}),
        {"state": "unknown state"},
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 1
    assert form.errors == {"state": ["Select a valid choice. unknown state is not one of the available choices."]}


def test_campaign_task_list_contributor_invalid_user_feedback(contributor, managed_campaign_with_tasks):
    response = contributor.get(
        reverse("contributor-campaign-task-list", kwargs={"pk": managed_campaign_with_tasks.id}),
        {"user_feedback": "unknown feedback"},
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 1
    assert form.errors == {
        "user_feedback": ["Select a valid choice. unknown feedback is not one of the available choices."]
    }


@pytest.mark.parametrize("state_filter", ["", USER_TASK_AVAILABLE_STATE, random.choice(list(TaskState))])
def test_campaign_task_list_anonymous_state_filter(
    anonymous, managed_campaign_with_tasks, state_filter, django_assert_num_queries
):
    managed_campaign_with_tasks.project.public = True
    managed_campaign_with_tasks.project.save()

    tasks = (
        (
            managed_campaign_with_tasks.tasks.annotate(
                nb_user_tasks=Count("user_tasks", filter=Q(user_tasks__is_preview=False))
            )
            .filter(nb_user_tasks__lt=F("campaign__max_user_tasks"))
            .order_by("created")
        )
        if state_filter == USER_TASK_AVAILABLE_STATE
        else managed_campaign_with_tasks.tasks.none()
    )

    expected_query = 6 if state_filter == USER_TASK_AVAILABLE_STATE else 4
    with django_assert_num_queries(expected_query):
        response = anonymous.get(
            reverse("contributor-campaign-task-list", kwargs={"pk": managed_campaign_with_tasks.id}),
            {"state": state_filter},
        )
    assert response.status_code == 200

    assert isinstance(response.context.get("object_list"), QuerySet)
    assert list(response.context["tasks"].values_list("id", flat=True)) == list(tasks.values_list("id", flat=True))

    for task in response.context["tasks"]:
        assert task.user_tasks.count() == 0

    assert response.context["campaign"] == managed_campaign_with_tasks


@pytest.mark.parametrize("user_feedback_filter", ["", USER_TASK_UNCERTAIN_FEEDBACK])
def test_campaign_task_list_anonymous_user_feedback_filter(
    anonymous, managed_campaign_with_tasks, user_feedback_filter, django_assert_num_queries
):
    managed_campaign_with_tasks.project.public = True
    managed_campaign_with_tasks.project.save()

    with django_assert_num_queries(4):
        response = anonymous.get(
            reverse("contributor-campaign-task-list", kwargs={"pk": managed_campaign_with_tasks.id}),
            {"user_feedback": user_feedback_filter},
        )
    assert response.status_code == 200

    assert isinstance(response.context.get("object_list"), QuerySet)
    assert list(response.context["tasks"].values_list("id", flat=True)) == []

    assert response.context["campaign"] == managed_campaign_with_tasks


@pytest.mark.parametrize(
    "state_filter", ["", USER_TASK_AVAILABLE_STATE, TaskState.Draft, random.choice(list(TaskState))]
)
def test_campaign_task_list_contributor_state_filter(
    contributor, managed_campaign_with_tasks, state_filter, django_assert_num_queries
):
    filters = (
        {"user_tasks__isnull": True}
        if state_filter == USER_TASK_AVAILABLE_STATE
        else {"user_tasks__user": contributor.user}
    )
    if state_filter and state_filter != USER_TASK_AVAILABLE_STATE:
        filters["user_tasks__state"] = state_filter

    contributor_draft_tasks = contributor.user.user_tasks.filter(
        task__campaign=managed_campaign_with_tasks, state=TaskState.Draft
    ).values_list("id", flat=True)

    tasks = (
        managed_campaign_with_tasks.tasks.filter(**filters).exclude(user_tasks__in=contributor_draft_tasks).distinct()
    ).order_by("created")

    expected_query = (
        9
        + (state_filter == USER_TASK_AVAILABLE_STATE)
        + (state_filter not in [USER_TASK_AVAILABLE_STATE, TaskState.Draft]) * 4
    )
    with django_assert_num_queries(expected_query):
        response = contributor.get(
            reverse("contributor-campaign-task-list", kwargs={"pk": managed_campaign_with_tasks.id}),
            {"state": state_filter},
        )
    assert response.status_code == 200

    assert isinstance(response.context.get("object_list"), QuerySet)
    # When filtering by Draft, nothing will be returned
    if state_filter == TaskState.Draft:
        assert not response.context["tasks"]
    # However, for other states, we should always have tasks
    else:
        assert response.context["tasks"]
        assert list(response.context["tasks"].values_list("id", flat=True)) == list(tasks.values_list("id", flat=True))

        for task in response.context["tasks"]:
            if state_filter == USER_TASK_AVAILABLE_STATE:
                assert task.user_tasks.count() == 0
            else:
                assert task.user_tasks.count() == 1
                assert task.user_tasks.first().user_id == contributor.user.id

    assert response.context["campaign"] == managed_campaign_with_tasks


@pytest.mark.parametrize("user_feedback_filter", ["", USER_TASK_UNCERTAIN_FEEDBACK])
def test_campaign_task_list_contributor_user_feedback_filter(
    contributor, managed_campaign_with_tasks, user_feedback_filter, django_assert_num_queries
):
    filters = {"user_tasks__user": contributor.user}
    if user_feedback_filter == USER_TASK_UNCERTAIN_FEEDBACK:
        filters["user_tasks__has_uncertain_value"] = True

    contributor_draft_tasks = contributor.user.user_tasks.filter(
        task__campaign=managed_campaign_with_tasks, state=TaskState.Draft
    ).values_list("id", flat=True)

    tasks = managed_campaign_with_tasks.tasks.filter(user_tasks__isnull=False).exclude(
        user_tasks__in=contributor_draft_tasks
    )
    # Update the "has_uncertain_value" of the latest user tasks
    tasks.last().user_tasks.update(has_uncertain_value=True)

    tasks = (
        managed_campaign_with_tasks.tasks.filter(**filters).exclude(user_tasks__in=contributor_draft_tasks).distinct()
    ).order_by("created")

    with django_assert_num_queries(13):
        response = contributor.get(
            reverse("contributor-campaign-task-list", kwargs={"pk": managed_campaign_with_tasks.id}),
            {"user_feedback": user_feedback_filter},
        )
    assert response.status_code == 200

    assert isinstance(response.context.get("object_list"), QuerySet)

    assert response.context["tasks"]
    assert list(response.context["tasks"].values_list("id", flat=True)) == list(tasks.values_list("id", flat=True))

    for task in response.context["tasks"]:
        assert task.user_tasks.count() == 1
        assert task.user_tasks.first().user_id == contributor.user.id

    assert response.context["campaign"] == managed_campaign_with_tasks
