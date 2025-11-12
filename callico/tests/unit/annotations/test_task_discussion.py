import pytest
from django.urls import reverse

from callico.annotations.models import Task
from callico.projects.models import CAMPAIGN_CLOSED_STATES, Role
from callico.users.models import Comment

pytestmark = pytest.mark.django_db


def test_task_discussion_anonymous(anonymous, managed_campaign_with_tasks):
    "An anonymous user is redirected to the login page"
    task = Task.objects.filter(campaign=managed_campaign_with_tasks).first()
    discussion_url = reverse("task-discussion", kwargs={"pk": task.id})

    response = anonymous.get(discussion_url)
    assert response.status_code == 302
    assert response.url == reverse("login") + f"?next={discussion_url}"


def test_task_discussion_wrong_task_id(user):
    response = user.get(reverse("task-discussion", kwargs={"pk": "cafecafe-cafe-cafe-cafe-cafecafecafe"}))
    assert response.status_code == 404
    assert response.context["exception"] == "No task matching this ID exists"


def test_task_discussion_non_member_forbidden(contributor, managed_campaign_with_tasks):
    managed_campaign_with_tasks.project.memberships.filter(user=contributor.user).delete()

    task = Task.objects.filter(campaign=managed_campaign_with_tasks, user_tasks__user__in=[contributor.user]).first()

    response = contributor.get(reverse("task-discussion", kwargs={"pk": task.id}))
    assert response.status_code == 403
    assert str(response.context["error_message"]) == "You don't have the required rights to comment on this task"


def test_task_discussion_unassigned_contributor_forbidden(contributor, managed_campaign_with_tasks):
    task = (
        Task.objects.filter(campaign=managed_campaign_with_tasks)
        .exclude(user_tasks__user__in=[contributor.user])
        .first()
    )

    response = contributor.get(reverse("task-discussion", kwargs={"pk": task.id}))
    assert response.status_code == 403
    assert str(response.context["error_message"]) == "You don't have the required rights to comment on this task"


@pytest.mark.parametrize("state", CAMPAIGN_CLOSED_STATES)
def test_task_discussion_closed_campaign(state, user, managed_campaign_with_tasks):
    managed_campaign_with_tasks.state = state
    managed_campaign_with_tasks.save()

    task = Task.objects.filter(campaign=managed_campaign_with_tasks).first()

    response = user.get(reverse("task-discussion", kwargs={"pk": task.id}))
    assert response.status_code == 403
    assert (
        str(response.context["error_message"])
        == f"You cannot comment a task for a campaign marked as {state.capitalize()}"
    )


def test_task_discussion_missing_required_field(user, managed_campaign_with_tasks):
    task = Task.objects.filter(campaign=managed_campaign_with_tasks).first()

    response = user.post(
        reverse("task-discussion", kwargs={"pk": task.id}),
        {"content": ""},
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 1
    assert form.errors == {
        "content": ["This field is required."],
    }


def test_task_discussion_get(user, managed_campaign_with_tasks, django_assert_num_queries):
    task = Task.objects.filter(campaign=managed_campaign_with_tasks).first()

    with django_assert_num_queries(6):
        response = user.get(reverse("task-discussion", kwargs={"pk": task.id}))
    assert response.status_code == 200

    assert response.context["task"] == task
    assert list(response.context["managers"].values_list("id")) == list(
        managed_campaign_with_tasks.project.memberships.filter(role=Role.Manager).values_list("user")
    )
    assert list(response.context["moderators"].values_list("id")) == list(
        managed_campaign_with_tasks.project.memberships.filter(role=Role.Moderator).values_list("user")
    )
    assert response.context["can_admin"]
    assert not response.context["add_pending_filter"]
    assert response.context["extra_breadcrumb"] == {"title": "Discussion", "link_title": task.element}


@pytest.mark.parametrize("role", Role)
def test_task_discussion_post(mocker, user, contributor, managed_campaign_with_tasks, django_assert_num_queries, role):
    celery_mock = mocker.patch("callico.users.tasks.send_email.delay")

    managed_campaign_with_tasks.project.memberships.filter(user=user.user).update(role=role)
    task = Task.objects.filter(campaign=managed_campaign_with_tasks, user_tasks__isnull=False).first()
    task.comments.create(
        user=contributor.user,
        content="An old comment form another contributor...",
    )

    user_task = None
    if role == Role.Contributor:
        user_task = task.user_tasks.first()
        user_task.user = user.user
        user_task.save()

    expected_queries = 11 if role == Role.Contributor else 10
    with django_assert_num_queries(expected_queries):
        response = user.post(
            reverse("task-discussion", kwargs={"pk": task.id}),
            {"content": "I encountered a problem on my task"},
        )
    assert response.status_code == 302
    assert response.url == reverse("task-discussion", kwargs={"pk": task.id})

    assert Comment.objects.count() == 2

    comment = Comment.objects.order_by("created").last()
    assert comment.user == user.user
    assert comment.task == task
    assert comment.content == "I encountered a problem on my task"

    # We send as many emails as we have participants on the discussion (i.e. the old contributor).
    # And also to project managers if the commenting user is a contributor.
    nb_mails = 1
    if role == Role.Contributor:
        nb_mails += managed_campaign_with_tasks.project.memberships.filter(role=Role.Manager).count()
    assert celery_mock.call_count == nb_mails
