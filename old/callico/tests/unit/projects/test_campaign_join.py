import uuid

import pytest
from django.contrib import messages
from django.db.models import Count, Q
from django.urls import reverse

from callico.annotations.models import Task, TaskState, TaskUser
from callico.projects.models import CAMPAIGN_CLOSED_STATES, CampaignState, Element, Role

pytestmark = pytest.mark.django_db


def test_campaign_join_anonymous(anonymous, campaign):
    join_url = reverse("campaign-join", kwargs={"pk": campaign.id})
    response = anonymous.post(join_url)
    assert response.status_code == 302
    assert response.url == reverse("login") + f"?next={join_url}"


def test_campaign_join_wrong_campaign_id(user):
    response = user.post(reverse("campaign-join", kwargs={"pk": uuid.uuid4()}))
    assert response.status_code == 404
    assert response.context["exception"] == "No Campaign found matching the query"


@pytest.mark.parametrize("state", CAMPAIGN_CLOSED_STATES)
def test_campaign_join_closed_campaign(state, contributor, managed_campaign_with_tasks):
    campaign = managed_campaign_with_tasks
    campaign.state = state
    campaign.save()

    response = contributor.post(reverse("campaign-join", kwargs={"pk": campaign.id}))
    assert response.status_code == 403
    assert (
        str(response.context["error_message"])
        == f"You cannot request tasks from a campaign marked as {state.capitalize()}"
    )


def test_campaign_join_user_has_pending_tasks(contributor, managed_campaign_with_tasks):
    response = contributor.post(reverse("campaign-join", kwargs={"pk": managed_campaign_with_tasks.id}))
    assert response.status_code == 400
    assert str(response.context["error_message"]) == "You already have pending tasks on this campaign"


def test_campaign_join_no_nb_tasks_auto_assignment(user, managed_campaign_with_tasks):
    campaign = managed_campaign_with_tasks
    campaign.nb_tasks_auto_assignment = 0
    campaign.save()

    response = user.post(reverse("campaign-join", kwargs={"pk": campaign.id}))
    assert response.status_code == 400
    assert str(response.context["error_message"]) == "The campaign does not allow to request tasks"


def test_campaign_join_no_available_tasks(user, campaign):
    response = user.post(reverse("campaign-join", kwargs={"pk": campaign.id}))
    assert response.status_code == 400
    assert str(response.context["error_message"]) == "All tasks on this campaign are already assigned"


def test_campaign_join_available_tasks_but_not_for_the_user(contributor, managed_campaign_with_tasks):
    """
    The campaign is configured to allow three assignments per task, the current user is already assigned
    to all existing tasks so even if there are available tasks he will not be able to request some
    """
    campaign = managed_campaign_with_tasks
    campaign.max_user_tasks = 3
    campaign.save()

    # Assert that the user is already assigned on all existing tasks
    contributor.user.user_tasks.filter(state=TaskState.Pending).delete()
    campaign.tasks.exclude(user_tasks__user=contributor.user).delete()
    assert campaign.tasks.count() == contributor.user.user_tasks.filter(task__campaign=campaign).count()

    # Assert that there are available tasks on the campaign
    assert (
        Task.objects.filter(campaign=campaign)
        .annotate(nb_user_tasks=Count("user_tasks", filter=Q(user_tasks__is_preview=False)))
        .filter(nb_user_tasks__lt=campaign.max_user_tasks)
        .exists()
    )

    response = contributor.post(reverse("campaign-join", kwargs={"pk": campaign.id}))
    assert response.status_code == 400
    assert str(response.context["error_message"]) == "All tasks on this campaign are already assigned"


@pytest.mark.parametrize("role", [Role.Moderator, Role.Manager])
def test_campaign_join_non_contributor(role, user, managed_campaign_with_tasks):
    campaign = managed_campaign_with_tasks
    campaign.project.save()
    campaign.project.memberships.filter(user=user.user).update(role=role)

    response = user.post(reverse("campaign-join", kwargs={"pk": campaign.id}))
    assert response.status_code == 403
    assert str(response.context["error_message"]) == "Only contributors can request tasks"


@pytest.mark.parametrize("public", [False, True])
@pytest.mark.parametrize("multiple_assignment", [False, True])
@pytest.mark.parametrize("single_task", [False, True])
def test_campaign_join_new_contributor(
    mocker, public, multiple_assignment, single_task, user, managed_campaign_with_tasks, django_assert_num_queries
):
    """
    When joining a campaign on a new project, the user is also added as a contributor
    """
    celery_mock = mocker.patch("callico.users.tasks.send_email.delay")

    campaign = managed_campaign_with_tasks
    campaign.nb_tasks_auto_assignment = 1
    campaign.max_user_tasks = 3 if multiple_assignment else 1
    campaign.save()
    campaign.project.public = public
    campaign.project.save()
    campaign.project.memberships.filter(user=user.user).delete()

    assert campaign.state == CampaignState.Created

    task_id = (
        Task.objects.filter(campaign=campaign)
        .annotate(nb_user_tasks=Count("user_tasks", filter=Q(user_tasks__is_preview=False)))
        .filter(nb_user_tasks__lt=campaign.max_user_tasks)
        .first()
        .id
    )
    data = {"task_id": task_id} if single_task else {}

    num_queries = 14 + (not multiple_assignment)
    with django_assert_num_queries(num_queries):
        response = user.post(reverse("campaign-join", kwargs={"pk": campaign.id}), data)
    assert response.status_code == 302
    assert (
        response.url
        == TaskUser.objects.filter(task__campaign=campaign, user=user.user, state=TaskState.Pending)
        .first()
        .annotate_url
        + f"?state={TaskState.Pending}"
    )

    # The user is now a member of the project
    assert campaign.project.memberships.filter(user=user.user, role=Role.Contributor).exists() is True
    # The user was assigned a single task
    assigned_tasks = TaskUser.objects.filter(user=user.user, task__campaign=campaign)
    assert assigned_tasks.count() == 1
    if single_task:
        assert assigned_tasks.first().task.id == task_id

    # The campaign was marked as running
    campaign.refresh_from_db()
    assert campaign.state == CampaignState.Running

    assert [(msg.level, msg.message) for msg in messages.get_messages(response.wsgi_request)] == [
        (messages.SUCCESS, "You are now contributor on project Managed project. 1 tasks have been assigned to you."),
    ]

    if multiple_assignment:
        # With the multiple assignment, there will still be available tasks for other users
        assert (
            Task.objects.filter(campaign=campaign)
            .annotate(nb_user_tasks=Count("user_tasks", filter=Q(user_tasks__is_preview=False)))
            .filter(nb_user_tasks__lt=campaign.max_user_tasks)
            .exists()
        )
        assert celery_mock.call_count == 0
    else:
        # Without the multiple assignment, all tasks will be assigned at least once and no more will be available
        assert (
            not Task.objects.filter(campaign=campaign)
            .annotate(nb_user_tasks=Count("user_tasks", filter=Q(user_tasks__is_preview=False)))
            .filter(nb_user_tasks__lt=campaign.max_user_tasks)
            .exists()
        )
        assert celery_mock.call_count == 1


@pytest.mark.parametrize("public", [False, True])
@pytest.mark.parametrize("single_task", [False, True])
def test_campaign_join_assigned_tasks(
    mocker, public, single_task, contributor, managed_project, managed_campaign_with_tasks, django_assert_num_queries
):
    """
    New tasks are automatically assigned with the sequential algorithm, up to campaign.nb_tasks_auto_assignment
    The user may have existing tasks on the campaign
    """
    celery_mock = mocker.patch("callico.users.tasks.send_email.delay")

    managed_project.public = public
    managed_project.save()

    campaign = managed_campaign_with_tasks
    campaign.nb_tasks_auto_assignment = 8
    campaign.save()

    assert campaign.state == CampaignState.Created

    # Free up the existing tasks, except 2 that are assigned to that user
    user_tasks = TaskUser.objects.filter(task__campaign=campaign)
    user_tasks.filter(state=TaskState.Pending).delete()
    existing_tasks_ids = list(
        user_tasks.filter(user=contributor.user).distinct("task_id")[:2].values_list("task_id", flat=True)
    )
    user_tasks.exclude(task_id__in=existing_tasks_ids).delete()

    user_tasks_qs = TaskUser.objects.filter(user=contributor.user, task__campaign__project=managed_project)
    assert user_tasks_qs.count() == 2

    expected_used_elements = list(
        (
            Element.objects.filter(tasks__campaign=campaign)
            .exclude(tasks__id__in=existing_tasks_ids)
            .order_by("parent_id", "order", "id")
            .values_list("id", flat=True)
        )[:8]
    )

    data = {}
    if single_task:
        expected_used_element = expected_used_elements.pop()
        expected_used_elements = [expected_used_element]
        data["task_id"] = Task.objects.get(element_id=expected_used_element).id

    with django_assert_num_queries(11):
        response = contributor.post(reverse("campaign-join", kwargs={"pk": campaign.id}), data)
    assert response.status_code == 302
    assert (
        response.url
        == (
            user_tasks.filter(user=contributor.user, state=TaskState.Pending)
            .exclude(task_id__in=existing_tasks_ids)
            .order_by("created")
            .first()
        ).annotate_url
        + f"?state={TaskState.Pending}"
    )

    # The user was assigned 1 or 8 new tasks
    nb_new_tasks = 1 if single_task else 8
    assert user_tasks_qs.count() == 2 + nb_new_tasks
    # The campaign was marked as running
    campaign.refresh_from_db()
    assert campaign.state == CampaignState.Running
    assert [(msg.level, msg.message) for msg in messages.get_messages(response.wsgi_request)] == [
        (messages.SUCCESS, f"{nb_new_tasks} tasks have been assigned to you."),
    ]

    # Tasks are ordered according to the sequential algorithm
    assert (
        list(
            Task.objects.filter(campaign=campaign, user_tasks__user=contributor.user)
            .exclude(id__in=existing_tasks_ids)
            .order_by("element__parent_id", "element__order")
            .values_list("element_id", flat=True)
        )
        == expected_used_elements
    )

    # Check if there are available tasks
    assert (
        Task.objects.filter(campaign=campaign)
        .annotate(nb_user_tasks=Count("user_tasks", filter=Q(user_tasks__is_preview=False)))
        .filter(nb_user_tasks__lt=campaign.max_user_tasks)
        .exists()
    )
    assert celery_mock.call_count == 0
