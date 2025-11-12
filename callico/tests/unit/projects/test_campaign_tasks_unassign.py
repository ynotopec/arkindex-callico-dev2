import pytest
from django.db.models.query import QuerySet
from django.urls import reverse
from pytest_lazy_fixtures import lf as lazy_fixture

from callico.annotations.models import Annotation, TaskState, TaskUser

pytestmark = pytest.mark.django_db


def test_campaign_tasks_unassign_anonymous(anonymous, campaign):
    "An anonymous user is redirected to the login page"
    unassign_url = reverse("tasks-unassign", kwargs={"pk": campaign.id})

    response = anonymous.get(unassign_url)
    assert response.status_code == 302
    assert response.url == reverse("login") + f"?next={unassign_url}"


@pytest.mark.parametrize(
    "forbidden_campaign",
    [
        # Hidden campaign
        lazy_fixture("hidden_campaign"),
        # Public campaign
        lazy_fixture("public_campaign"),
        # Contributor rights on campaign project
        lazy_fixture("campaign"),
        # Moderator rights on campaign project
        lazy_fixture("moderated_campaign"),
    ],
)
def test_campaign_tasks_unassign_forbidden(user, forbidden_campaign):
    unassign_url = reverse("tasks-unassign", kwargs={"pk": forbidden_campaign.id})

    response = user.get(unassign_url)
    assert response.status_code == 403


def test_campaign_tasks_unassign_archived_campaign(user, archived_campaign):
    response = user.get(reverse("tasks-unassign", kwargs={"pk": archived_campaign.id}))
    assert response.status_code == 403
    assert str(response.context["error_message"]) == "You cannot unassign tasks on a campaign marked as Archived"


def test_campaign_tasks_unassign_wrong_campaign_id(user):
    unassign_url = reverse("tasks-unassign", kwargs={"pk": "cafecafe-cafe-cafe-cafe-cafecafecafe"})

    response = user.get(unassign_url)
    assert response.status_code == 404
    assert response.context["exception"] == "No campaign matching this ID exists"


def test_campaign_tasks_unassign_get(
    user, managed_campaign_with_tasks, contributor, new_contributor, django_assert_num_queries
):
    for user_task in TaskUser.objects.filter(user=contributor.user, state=TaskState.Annotated):
        last_annotation = Annotation.objects.create(user_task=user_task)

    with django_assert_num_queries(7):
        response = user.get(
            reverse("tasks-unassign", kwargs={"pk": managed_campaign_with_tasks.id}),
        )
    assert response.status_code == 200

    assert response.context["nb_unassigned_tasks"] == 1
    assert isinstance(response.context.get("object_list"), QuerySet)
    assert list(
        response.context["users"].values_list(
            "id", "email", "pending_user_tasks_count", "draft_user_tasks_count", "last_annotation"
        )
    ) == [
        (contributor.user.id, contributor.user.email, 2, 2, last_annotation.created),
        (new_contributor.id, new_contributor.email, 3, 3, None),
    ]


@pytest.mark.parametrize("state", [TaskState.Draft, TaskState.Pending])
def test_campaign_tasks_unassign_post_invalid_user(user, state, managed_campaign_with_tasks):
    filters = {"state": state, "task__campaign": managed_campaign_with_tasks}

    total_tasks = TaskUser.objects.filter(**filters).count()
    assert total_tasks > 0

    response = user.post(reverse("tasks-unassign", kwargs={"pk": managed_campaign_with_tasks.id}), {"user_id": 1000000})
    assert response.status_code == 404
    assert response.context["exception"] == "No user matching this ID has draft or pending tasks on this campaign"

    managed_campaign_with_tasks.refresh_from_db()
    new_total_tasks = TaskUser.objects.filter(**filters).count()
    assert new_total_tasks == total_tasks


@pytest.mark.parametrize("state", [TaskState.Draft, TaskState.Pending])
def test_campaign_tasks_unassign_post_no_tasks(user, state, managed_campaign_with_tasks):
    "This should never happen since we only list users that have at least one draft or one pending tasks in the frontend"
    filters = {"state": state, "task__campaign": managed_campaign_with_tasks}

    total_tasks = TaskUser.objects.filter(**filters).count()
    assert total_tasks > 0

    response = user.post(
        reverse("tasks-unassign", kwargs={"pk": managed_campaign_with_tasks.id}), {"user_id": user.user.id}
    )
    assert response.status_code == 404
    assert response.context["exception"] == "No user matching this ID has draft or pending tasks on this campaign"

    managed_campaign_with_tasks.refresh_from_db()
    new_total_tasks = TaskUser.objects.filter(**filters).count()
    assert new_total_tasks == total_tasks


@pytest.mark.parametrize("state", [TaskState.Draft, TaskState.Pending])
def test_campaign_tasks_unassign_post(
    user, state, managed_campaign_with_tasks, contributor, new_contributor, django_assert_num_queries
):
    for user_task in TaskUser.objects.filter(user=contributor.user, state=TaskState.Annotated):
        last_annotation = Annotation.objects.create(user_task=user_task)

    filters = {"state": state, "task__campaign": managed_campaign_with_tasks}

    total_tasks = TaskUser.objects.filter(**filters).count()
    assert total_tasks > 0
    tasks_for_user = new_contributor.user_tasks.filter(**filters).count()
    assert tasks_for_user > 0

    with django_assert_num_queries(13):
        response = user.post(
            reverse("tasks-unassign", kwargs={"pk": managed_campaign_with_tasks.id}),
            {"user_id": new_contributor.id, state.value: "whatever"},
        )
    assert response.status_code == 200

    assert response.context["nb_unassigned_tasks"] == 1
    assert isinstance(response.context.get("object_list"), QuerySet)
    assert list(
        response.context["users"].values_list(
            "id", "email", "pending_user_tasks_count", "draft_user_tasks_count", "last_annotation"
        )
    ) == [
        (contributor.user.id, contributor.user.email, 2, 2, last_annotation.created),
        (
            new_contributor.id,
            new_contributor.email,
            3 if state == TaskState.Draft else 0,
            3 if state == TaskState.Pending else 0,
            None,
        ),
    ]
    assert response.context["campaign"] == managed_campaign_with_tasks

    managed_campaign_with_tasks.refresh_from_db()
    new_contributor.refresh_from_db()
    new_total_tasks = TaskUser.objects.filter(**filters).count()
    assert new_total_tasks == total_tasks - tasks_for_user
    assert not new_contributor.user_tasks.filter(**filters).exists()


def test_campaign_tasks_delete_post(
    user, managed_campaign_with_tasks, contributor, new_contributor, django_assert_num_queries
):
    for user_task in TaskUser.objects.filter(user=contributor.user, state=TaskState.Annotated):
        last_annotation = Annotation.objects.create(user_task=user_task)

    assert managed_campaign_with_tasks.tasks.filter(user_tasks__isnull=True).exists()

    with django_assert_num_queries(13):
        response = user.post(
            reverse("tasks-unassign", kwargs={"pk": managed_campaign_with_tasks.id}),
            {"user_id": new_contributor.id, "unassigned": "whatever"},
        )
    assert response.status_code == 200

    assert response.context["nb_unassigned_tasks"] == 0
    assert isinstance(response.context.get("object_list"), QuerySet)
    assert list(
        response.context["users"].values_list(
            "id", "email", "pending_user_tasks_count", "draft_user_tasks_count", "last_annotation"
        )
    ) == [
        (contributor.user.id, contributor.user.email, 2, 2, last_annotation.created),
        (new_contributor.id, new_contributor.email, 3, 3, None),
    ]
    assert response.context["campaign"] == managed_campaign_with_tasks

    managed_campaign_with_tasks.refresh_from_db()
    assert not managed_campaign_with_tasks.tasks.filter(user_tasks__isnull=True).exists()
