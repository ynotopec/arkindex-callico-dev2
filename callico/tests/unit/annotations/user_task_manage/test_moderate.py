import random

import pytest
from django.db.models import Q
from django.urls import reverse
from pytest_lazy_fixtures import lf as lazy_fixture

from callico.annotations.models import USER_TASK_MODERATE_URL_NAMES, AnnotationState, TaskState, TaskUser
from callico.projects.forms import (
    USER_TASK_ALL_FEEDBACKS,
    USER_TASK_NO_FEEDBACK,
    USER_TASK_UNCERTAIN_FEEDBACK,
    USER_TASK_WITH_COMMENTS,
)
from callico.projects.models import CampaignMode
from callico.users.models import User

pytestmark = pytest.mark.django_db

MODERATE_EXCLUDED_STATES = [TaskState.Draft]
MODERATE_INCLUDED_STATES = [state for state in TaskState if state not in MODERATE_EXCLUDED_STATES]


def test_user_task_manage_non_member_user(contributor, managed_campaign_with_tasks):
    mode, user_task_url_name = random.choice(list(USER_TASK_MODERATE_URL_NAMES.items()))
    managed_campaign_with_tasks.mode = mode
    managed_campaign_with_tasks.save()

    user_task = TaskUser.objects.filter(task__campaign_id=managed_campaign_with_tasks.id).first()
    user_task_url = reverse(user_task_url_name, kwargs={"pk": user_task.id})

    response = contributor.get(user_task_url)
    assert response.status_code == 403
    assert (
        str(response.context["error_message"]) == "You don't have the required rights on this project to moderate tasks"
    )


@pytest.mark.parametrize("state", MODERATE_EXCLUDED_STATES)
def test_user_task_moderate_excluded_state_manager_redirection(
    state, user, managed_campaign_with_tasks, django_assert_num_queries
):
    mode, user_task_url_name = random.choice(list(USER_TASK_MODERATE_URL_NAMES.items()))
    managed_campaign_with_tasks.mode = mode
    managed_campaign_with_tasks.save()

    user_task = TaskUser.objects.filter(task__campaign_id=managed_campaign_with_tasks.id).first()
    user_task.state = state
    user_task.save()

    with django_assert_num_queries(6):
        response = user.get(reverse(user_task_url_name, kwargs={"pk": user_task.task_id}))

    assert response.status_code == 302
    assert response.url == reverse("element-details", kwargs={"pk": user_task.task.element.id})


@pytest.mark.parametrize("has_annotation", [True, False])
def test_user_task_moderate_reject_with_or_without_annotation(
    has_annotation,
    user,
    managed_campaign_with_tasks,
    django_assert_num_queries,
):
    mode, user_task_url_name = random.choice(list(USER_TASK_MODERATE_URL_NAMES.items()))
    managed_campaign_with_tasks.mode = mode
    managed_campaign_with_tasks.save()

    user_task = TaskUser.objects.filter(
        task__campaign_id=managed_campaign_with_tasks.id, state__in=MODERATE_INCLUDED_STATES
    ).first()

    annotation = user_task.annotations.create() if has_annotation else None

    # Removing potential next user tasks to keep a steady queries count
    TaskUser.objects.exclude(id=user_task.id).delete()

    expected_queries = (
        10
        + (mode in [CampaignMode.Transcription, CampaignMode.Classification, CampaignMode.ElementGroup])
        + (mode in [CampaignMode.Transcription, CampaignMode.EntityForm]) * has_annotation
        + has_annotation * 3
    )
    with django_assert_num_queries(expected_queries):
        response = user.post(
            reverse(user_task_url_name, kwargs={"pk": user_task.id}),
            {
                "form-TOTAL_FORMS": 1,
                "form-INITIAL_FORMS": 1,
                "annotation": "some useless value",
                "form-0-annotation": "some useless value",
                "form-0-entity_type": "person",
                "form-0-offset": 0,
                "form-0-length": 1,
                "reject": "Reject",
            },
        )
    assert response.status_code == 302

    user_task.refresh_from_db()

    # The user task was rejected and no annotation was created
    assert user_task.state == TaskState.Rejected
    assert user_task.annotations.count() == bool(annotation)

    # The annotation (if exists) was moderated
    if annotation:
        annotation.refresh_from_db()
        assert annotation.moderator == user.user
        assert annotation.state == AnnotationState.Rejected


@pytest.mark.parametrize("next_user_task_exists", [True, False])
@pytest.mark.parametrize("state_filter", [None, "", random.choice(MODERATE_INCLUDED_STATES), TaskState.Rejected])
def test_user_task_moderate_reject_state_filter(
    next_user_task_exists,
    state_filter,
    user,
    managed_campaign_with_tasks,
    django_assert_num_queries,
):
    mode, user_task_url_name = random.choice(list(USER_TASK_MODERATE_URL_NAMES.items()))
    managed_campaign_with_tasks.mode = mode
    managed_campaign_with_tasks.save()

    user_tasks = (
        TaskUser.objects.filter(task__campaign=managed_campaign_with_tasks)
        .exclude(state__in=MODERATE_EXCLUDED_STATES)
        .order_by("task__created", "task_id", "created", "id")
    )
    user_task = user_tasks.first()

    if not next_user_task_exists:
        TaskUser.objects.exclude(id=user_task.id).delete()

    expected_queries = (
        8
        + (not next_user_task_exists) * 2
        + (mode in [CampaignMode.Transcription, CampaignMode.Classification, CampaignMode.ElementGroup])
    )
    with django_assert_num_queries(expected_queries):
        query_params = f"?state={state_filter}" if state_filter is not None else ""
        response = user.post(
            reverse(user_task_url_name, kwargs={"pk": user_task.id}) + query_params,
            {
                "form-TOTAL_FORMS": 1,
                "form-INITIAL_FORMS": 1,
                "annotation": "some useless value",
                "form-0-annotation": "some useless value",
                "form-0-entity_type": "person",
                "form-0-offset": 0,
                "form-0-length": 1,
                "reject": "Reject",
            },
        )
    assert response.status_code == 302

    user_task.refresh_from_db()

    # The user task was rejected and no annotation was created
    assert user_task.state == TaskState.Rejected
    assert user_task.annotations.count() == 0

    if not next_user_task_exists:
        if state_filter and state_filter != TaskState.Rejected:
            query_params = ""

        assert (
            response.url
            == reverse("admin-campaign-task-list", kwargs={"pk": managed_campaign_with_tasks.id}) + query_params
        )
    else:
        filters = Q(id=user_task.id) | Q(state=state_filter) if state_filter else Q()
        all_user_tasks = list(user_tasks.filter(filters))
        current_index = all_user_tasks.index(user_task)
        next_user_task = all_user_tasks[current_index + 1]

        assert response.url == next_user_task.moderate_url + query_params


@pytest.mark.parametrize("next_user_task_exists", [True, False])
@pytest.mark.parametrize(
    "user_feedback_filter",
    [
        None,
        "",
        USER_TASK_NO_FEEDBACK,
        USER_TASK_WITH_COMMENTS,
        USER_TASK_UNCERTAIN_FEEDBACK,
        USER_TASK_ALL_FEEDBACKS,
    ],
)
def test_user_task_moderate_reject_user_feedback_filter(
    next_user_task_exists,
    user_feedback_filter,
    user,
    managed_campaign_with_tasks,
    django_assert_num_queries,
):
    mode, user_task_url_name = random.choice(list(USER_TASK_MODERATE_URL_NAMES.items()))
    managed_campaign_with_tasks.mode = mode
    managed_campaign_with_tasks.save()

    user_tasks = (
        TaskUser.objects.filter(task__campaign=managed_campaign_with_tasks)
        .exclude(state__in=MODERATE_EXCLUDED_STATES)
        .order_by("task__created", "task_id", "created", "id")
    )
    user_task = user_tasks.first()

    with_comments_user_task, uncertain_user_task, all_feedbacks_user_task = None, None, None
    for tmp_user_id in user_tasks.order_by("user_id").values_list("user_id", flat=True).distinct():
        filtered_user_tasks = user_tasks.exclude(id=user_task.id).filter(user_id=tmp_user_id)

        # Add a comment for the first user task
        with_comments_user_task = filtered_user_tasks.first()
        with_comments_user_task.task.comments.create(user=with_comments_user_task.user, content="Something went wrong")

        # Update the "has_uncertain_value" of the second user task
        uncertain_user_task = filtered_user_tasks.exclude(id=with_comments_user_task.id).first()
        uncertain_user_task.has_uncertain_value = True
        uncertain_user_task.save()

        # Add a comment + update the "has_uncertain_value" of the third user task
        all_feedbacks_user_task = filtered_user_tasks.exclude(
            id__in=[with_comments_user_task.id, uncertain_user_task.id]
        ).first()
        all_feedbacks_user_task.has_uncertain_value = True
        all_feedbacks_user_task.save()
        all_feedbacks_user_task.task.comments.create(user=all_feedbacks_user_task.user, content="Oops")

    if not next_user_task_exists:
        TaskUser.objects.exclude(id=user_task.id).delete()

    expected_queries = (
        8
        + (not next_user_task_exists) * 2
        + (mode in [CampaignMode.Transcription, CampaignMode.Classification, CampaignMode.ElementGroup])
    )
    with django_assert_num_queries(expected_queries):
        query_params = f"?user_feedback={user_feedback_filter}" if user_feedback_filter is not None else ""
        response = user.post(
            reverse(user_task_url_name, kwargs={"pk": user_task.id}) + query_params,
            {
                "form-TOTAL_FORMS": 1,
                "form-INITIAL_FORMS": 1,
                "annotation": "some useless value",
                "form-0-annotation": "some useless value",
                "form-0-entity_type": "person",
                "form-0-offset": 0,
                "form-0-length": 1,
                "reject": "Reject",
            },
        )
    assert response.status_code == 302

    user_task.refresh_from_db()

    # The user task was rejected and no annotation was created
    assert user_task.state == TaskState.Rejected
    assert user_task.annotations.count() == 0

    if not next_user_task_exists:
        if user_feedback_filter and user_feedback_filter in [
            USER_TASK_WITH_COMMENTS,
            USER_TASK_UNCERTAIN_FEEDBACK,
            USER_TASK_ALL_FEEDBACKS,
        ]:
            query_params = ""

        assert (
            response.url
            == reverse("admin-campaign-task-list", kwargs={"pk": managed_campaign_with_tasks.id}) + query_params
        )
    else:
        next_user_task = None
        if user_feedback_filter == USER_TASK_WITH_COMMENTS:
            next_user_task = with_comments_user_task
        elif user_feedback_filter == USER_TASK_UNCERTAIN_FEEDBACK:
            next_user_task = uncertain_user_task
        elif user_feedback_filter == USER_TASK_ALL_FEEDBACKS:
            next_user_task = all_feedbacks_user_task
        else:
            filters = (
                Q(id=user_task.id) | (Q(has_uncertain_value=False) & Q(task__comments__isnull=True))
                if user_feedback_filter == USER_TASK_NO_FEEDBACK
                else Q()
            )
            all_user_tasks = list(user_tasks.filter(filters))
            current_index = all_user_tasks.index(user_task)
            next_user_task = all_user_tasks[current_index + 1]

        assert response.url == next_user_task.moderate_url + query_params


@pytest.mark.parametrize("next_user_task_exists", [True, False])
@pytest.mark.parametrize("user_filter", [None, "", lazy_fixture("contributor")])
def test_user_task_moderate_reject_user_filter(
    next_user_task_exists,
    user_filter,
    user,
    managed_campaign_with_tasks,
    django_assert_num_queries,
):
    mode, user_task_url_name = random.choice(list(USER_TASK_MODERATE_URL_NAMES.items()))
    managed_campaign_with_tasks.mode = mode
    managed_campaign_with_tasks.save()

    user_tasks = (
        TaskUser.objects.filter(task__campaign=managed_campaign_with_tasks)
        .exclude(state__in=MODERATE_EXCLUDED_STATES)
        .order_by("task__created", "task_id", "created", "id")
    )
    user_task = user_tasks.first()

    user_id = user_filter
    if user_filter:
        user_id = user_filter.id if isinstance(user_filter, User) else user_filter.user.id

    if not next_user_task_exists:
        TaskUser.objects.exclude(id=user_task.id).delete()

    expected_queries = (
        8
        + (not next_user_task_exists) * 2
        + (mode in [CampaignMode.Transcription, CampaignMode.Classification, CampaignMode.ElementGroup])
    )
    with django_assert_num_queries(expected_queries):
        query_params = f"?user_id={user_id}" if user_filter is not None else ""
        response = user.post(
            reverse(user_task_url_name, kwargs={"pk": user_task.id}) + query_params,
            {
                "form-TOTAL_FORMS": 1,
                "form-INITIAL_FORMS": 1,
                "annotation": "some useless value",
                "form-0-annotation": "some useless value",
                "form-0-entity_type": "person",
                "form-0-offset": 0,
                "form-0-length": 1,
                "reject": "Reject",
            },
        )
    assert response.status_code == 302

    user_task.refresh_from_db()

    # The user task was rejected and no annotation was created
    assert user_task.state == TaskState.Rejected
    assert user_task.annotations.count() == 0

    if not next_user_task_exists:
        if user_id and user_id != user_task.user_id:
            query_params = ""

        assert (
            response.url
            == reverse("admin-campaign-task-list", kwargs={"pk": managed_campaign_with_tasks.id}) + query_params
        )
    else:
        filters = Q(id=user_task.id) | Q(user_id=user_id) if user_filter else Q()
        all_user_tasks = list(user_tasks.filter(filters))
        current_index = all_user_tasks.index(user_task)
        next_user_task = all_user_tasks[current_index + 1]

        assert response.url == next_user_task.moderate_url + query_params
