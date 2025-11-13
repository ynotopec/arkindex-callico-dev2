import random

import pytest
from django.db.models import Q
from django.urls import reverse

from callico.annotations.models import USER_TASK_ANNOTATE_URL_NAMES, TaskState, TaskUser
from callico.projects.forms import USER_TASK_AVAILABLE_STATE, USER_TASK_UNCERTAIN_FEEDBACK
from callico.projects.models import CampaignMode, Role

pytestmark = pytest.mark.django_db

ANNOTATE_EXCLUDED_STATES = [TaskState.Draft, TaskState.Validated]
ANNOTATE_INCLUDED_STATES = [state for state in TaskState if state not in ANNOTATE_EXCLUDED_STATES]


def test_user_task_annotate_unassigned_manager_redirected(user, managed_campaign_with_tasks, django_assert_num_queries):
    mode, user_task_url_name = random.choice(list(USER_TASK_ANNOTATE_URL_NAMES.items()))
    managed_campaign_with_tasks.mode = mode
    managed_campaign_with_tasks.save()

    user_task = TaskUser.objects.filter(task__campaign_id=managed_campaign_with_tasks.id).first()

    with django_assert_num_queries(6):
        response = user.get(reverse(user_task_url_name, kwargs={"pk": user_task.task_id}))

    assert response.status_code == 302
    assert response.url == reverse("element-details", kwargs={"pk": user_task.task.element.id})


def test_user_task_annotate_unassigned_user(user, managed_campaign_with_tasks):
    managed_campaign_with_tasks.project.memberships.filter(user=user.user).update(role=Role.Contributor)

    mode, user_task_url_name = random.choice(list(USER_TASK_ANNOTATE_URL_NAMES.items()))
    managed_campaign_with_tasks.mode = mode
    managed_campaign_with_tasks.save()

    user_task = TaskUser.objects.filter(task__campaign_id=managed_campaign_with_tasks.id).first()
    user_task_url = reverse(user_task_url_name, kwargs={"pk": user_task.id})

    response = user.get(user_task_url)
    assert response.status_code == 403
    assert str(response.context["error_message"]) == "You are not assigned to this task"


@pytest.mark.parametrize("state", ANNOTATE_EXCLUDED_STATES)
def test_user_task_annotate_excluded_state(state, contributor, managed_campaign_with_tasks):
    mode, user_task_url_name = random.choice(list(USER_TASK_ANNOTATE_URL_NAMES.items()))
    managed_campaign_with_tasks.mode = mode
    managed_campaign_with_tasks.save()

    user_task = TaskUser.objects.filter(
        task__campaign_id=managed_campaign_with_tasks.id, state=state, user=contributor.user
    ).first()
    user_task_url = reverse(user_task_url_name, kwargs={"pk": user_task.id})

    response = contributor.get(user_task_url)
    assert response.status_code == 404
    assert response.context["exception"] == f"You cannot annotate a task marked as {user_task.get_state_display()}"


@pytest.mark.parametrize("next_user_task_exists", [True, False])
@pytest.mark.parametrize(
    "state_filter", [None, "", random.choice(ANNOTATE_INCLUDED_STATES), TaskState.Skipped, TaskState.Pending]
)
def test_user_task_annotate_skip_state_filter(
    next_user_task_exists,
    state_filter,
    contributor,
    managed_campaign_with_tasks,
    django_assert_num_queries,
):
    mode, user_task_url_name = random.choice(list(USER_TASK_ANNOTATE_URL_NAMES.items()))
    managed_campaign_with_tasks.mode = mode
    managed_campaign_with_tasks.save()

    user_tasks = (
        TaskUser.objects.filter(user=contributor.user, task__campaign=managed_campaign_with_tasks)
        .exclude(state__in=ANNOTATE_EXCLUDED_STATES)
        .order_by("created")
    )
    user_task = user_tasks.first()

    if not next_user_task_exists:
        TaskUser.objects.exclude(id=user_task.id).delete()

    expected_queries = (
        9
        + (not next_user_task_exists) * 2
        + (not next_user_task_exists and state_filter == TaskState.Pending)
        + (mode in [CampaignMode.Transcription, CampaignMode.Classification, CampaignMode.ElementGroup])
    )
    with django_assert_num_queries(expected_queries):
        query_params = f"?state={state_filter}" if state_filter is not None else ""
        response = contributor.post(
            reverse(user_task_url_name, kwargs={"pk": user_task.id}) + query_params,
            {
                "form-TOTAL_FORMS": 1,
                "form-INITIAL_FORMS": 1,
                "annotation": "some useless value",
                "form-0-annotation": "some useless value",
                "form-0-entity_type": "person",
                "form-0-offset": 0,
                "form-0-length": 1,
                "skip": "Skip task",
            },
        )
    assert response.status_code == 302

    user_task.refresh_from_db()

    # The user task was skipped and no annotation was created
    assert user_task.state == TaskState.Skipped
    assert user_task.annotations.count() == 0

    if not next_user_task_exists:
        if state_filter == TaskState.Pending:
            query_params = f"?state={USER_TASK_AVAILABLE_STATE}"
        elif state_filter and state_filter != TaskState.Skipped:
            query_params = ""

        assert (
            response.url
            == reverse("contributor-campaign-task-list", kwargs={"pk": managed_campaign_with_tasks.id}) + query_params
        )
    else:
        filters = Q(id=user_task.id) | Q(state=state_filter) if state_filter else Q()
        all_user_tasks = list(user_tasks.filter(filters))
        current_index = all_user_tasks.index(user_task)
        next_user_task = all_user_tasks[current_index + 1]

        assert response.url == next_user_task.annotate_url + query_params


@pytest.mark.parametrize("next_user_task_exists", [True, False])
@pytest.mark.parametrize("user_feedback_filter", [None, "", USER_TASK_UNCERTAIN_FEEDBACK])
def test_user_task_annotate_skip_user_feedback_filter(
    next_user_task_exists,
    user_feedback_filter,
    contributor,
    managed_campaign_with_tasks,
    django_assert_num_queries,
):
    mode, user_task_url_name = random.choice(list(USER_TASK_ANNOTATE_URL_NAMES.items()))
    managed_campaign_with_tasks.mode = mode
    managed_campaign_with_tasks.save()

    user_tasks = (
        TaskUser.objects.filter(user=contributor.user, task__campaign=managed_campaign_with_tasks)
        .exclude(state__in=ANNOTATE_EXCLUDED_STATES)
        .order_by("created")
    )
    user_task = user_tasks.first()

    filtered_user_tasks = user_tasks.exclude(id=user_task.id)
    # Update the "has_uncertain_value" of the latest user task
    uncertain_user_task = filtered_user_tasks.last()
    uncertain_user_task.has_uncertain_value = True
    uncertain_user_task.save()

    if not next_user_task_exists:
        TaskUser.objects.exclude(id=user_task.id).delete()

    expected_queries = (
        9
        + (not next_user_task_exists) * 2
        + (mode in [CampaignMode.Transcription, CampaignMode.Classification, CampaignMode.ElementGroup])
    )
    with django_assert_num_queries(expected_queries):
        query_params = f"?user_feedback={user_feedback_filter}" if user_feedback_filter is not None else ""
        response = contributor.post(
            reverse(user_task_url_name, kwargs={"pk": user_task.id}) + query_params,
            {
                "form-TOTAL_FORMS": 1,
                "form-INITIAL_FORMS": 1,
                "annotation": "some useless value",
                "form-0-annotation": "some useless value",
                "form-0-entity_type": "person",
                "form-0-offset": 0,
                "form-0-length": 1,
                "skip": "Skip task",
            },
        )
    assert response.status_code == 302

    user_task.refresh_from_db()

    # The user task was skipped and no annotation was created
    assert user_task.state == TaskState.Skipped
    assert user_task.annotations.count() == 0

    if not next_user_task_exists:
        if user_feedback_filter:
            query_params = ""

        assert (
            response.url
            == reverse("contributor-campaign-task-list", kwargs={"pk": managed_campaign_with_tasks.id}) + query_params
        )
    else:
        next_user_task = None
        if user_feedback_filter == USER_TASK_UNCERTAIN_FEEDBACK:
            next_user_task = uncertain_user_task
        else:
            all_user_tasks = list(user_tasks)
            current_index = all_user_tasks.index(user_task)
            next_user_task = all_user_tasks[current_index + 1]

        assert response.url == next_user_task.annotate_url + query_params
