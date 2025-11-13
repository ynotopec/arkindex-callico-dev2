import uuid
from urllib.parse import quote

import pytest
from django.urls import reverse
from pytest_lazy_fixtures import lf as lazy_fixture

from callico.annotations.models import Task, TaskState, TaskUser
from callico.projects.models import Project, Role
from callico.users.models import User

pytestmark = pytest.mark.django_db


@pytest.fixture()
def membership(project, contributor):
    return project.memberships.get(user__email=contributor.user.email)


def test_member_update_anonymous(anonymous, project, membership):
    "An anonymous user is redirected to the login page"
    update_url = reverse("member-update", kwargs={"project_id": project.id, "pk": membership.id})
    response = anonymous.post(update_url)
    assert response.status_code == 302
    assert response.url == reverse("login") + f"?next={quote(update_url)}"


@pytest.mark.parametrize(
    "forbidden_project",
    [
        # Hidden project
        lazy_fixture("hidden_project"),
        # Public project
        lazy_fixture("public_project"),
        # Contributor rights on the project
        lazy_fixture("project"),
        # Moderator rights on the project
        lazy_fixture("moderated_project"),
    ],
)
def test_member_update_forbidden(user, forbidden_project, membership):
    response = user.post(reverse("member-update", kwargs={"project_id": forbidden_project.id, "pk": membership.id}))
    assert response.status_code == 403


def test_member_update_own_membership(user, managed_project):
    membership = managed_project.memberships.get(user__email=user.user.email)
    response = user.post(reverse("member-update", kwargs={"project_id": managed_project.id, "pk": membership.id}))
    assert response.status_code == 403
    assert (
        str(response.context["error_message"])
        == "For security reasons, you are not allowed to edit your own membership"
    )


def test_member_update_wrong_project_id(user, membership):
    response = user.post(
        reverse("member-update", kwargs={"project_id": "cafecafe-cafe-cafe-cafe-cafecafecafe", "pk": membership.id})
    )
    assert response.status_code == 404
    assert response.context["exception"] == "No project matching this ID exists"


def test_member_update_wrong_membership_id(user, project):
    response = user.post(reverse("member-update", kwargs={"project_id": project.id, "pk": 999}))
    assert response.status_code == 404
    assert response.context["exception"] == "No membership matching this ID exists"


def test_member_update_missing_required_fields(user, managed_project, membership):
    response = user.post(
        reverse("member-update", kwargs={"project_id": managed_project.id, "pk": membership.id}),
        {
            "role": "",
        },
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 1
    assert form.errors == {
        "role": ["This field is required."],
    }


def test_member_update_invalid_role(user, managed_project, membership):
    response = user.post(
        reverse("member-update", kwargs={"project_id": managed_project.id, "pk": membership.id}),
        {
            "role": "invalid",
        },
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 1
    assert form.errors == {
        "role": ["Select a valid choice. invalid is not one of the available choices."],
    }


def test_member_update_get(user, managed_project, membership, django_assert_num_queries):
    with django_assert_num_queries(5):
        response = user.get(reverse("member-update", kwargs={"project_id": managed_project.id, "pk": membership.id}))
    assert response.status_code == 200

    assert response.context["project"] == managed_project
    assert response.context["action"] == "Edit"


@pytest.mark.parametrize("old_role", Role)
@pytest.mark.parametrize("new_role", Role)
def test_member_update_post(
    old_role, new_role, user, managed_project, arkindex_provider, managed_campaign_with_tasks, django_assert_num_queries
):
    # Cleanup existing TaskUser objects
    TaskUser.objects.all().delete()

    other_user = User.objects.create(display_name="Other", email="other@callico.org", password="other", is_admin=False)

    # Create TaskUser in all states (+ preview task) in another project
    other_project = Project.objects.create(name="Another project")
    other_project.memberships.create(role=Role.Contributor, user=other_user)
    other_page_type = other_project.types.create(name="Another page")
    other_campaign = other_project.campaigns.create(name="Another campaign", creator=user.user)
    TaskUser.objects.bulk_create(
        TaskUser(
            user=other_user,
            state=state,
            task=Task.objects.create(
                element=other_project.elements.create(
                    name="A page", type=other_page_type, provider=arkindex_provider, provider_object_id=uuid.uuid4()
                ),
                campaign=other_campaign,
            ),
        )
        for state in TaskState
    )
    other_finished_task = (
        TaskUser.objects.filter(task__campaign=other_campaign)
        .exclude(state__in=[TaskState.Pending, TaskState.Draft])
        .first()
    )
    other_finished_task.is_preview = True
    other_finished_task.save()

    # Create TaskUser in all states (+ preview task) in this project
    membership = managed_project.memberships.create(role=old_role, user=other_user)
    TaskUser.objects.bulk_create(
        TaskUser(
            user=other_user,
            state=state,
            task=task,
        )
        for task, state in zip(managed_campaign_with_tasks.tasks.all(), TaskState)
    )
    finished_task = (
        TaskUser.objects.filter(task__campaign=managed_campaign_with_tasks)
        .exclude(state__in=[TaskState.Pending, TaskState.Draft])
        .first()
    )
    finished_task.is_preview = True
    finished_task.save()

    # Checking tasks were properly created
    user_tasks = TaskUser.objects.filter(user=other_user)
    project_user_tasks = user_tasks.filter(task__campaign__project=managed_project)
    assert project_user_tasks.filter(state__in=[TaskState.Pending, TaskState.Draft]).exists()
    assert project_user_tasks.exclude(state__in=[TaskState.Pending, TaskState.Draft]).exists()
    assert project_user_tasks.filter(is_preview=True).exists()
    other_user_tasks = user_tasks.filter(task__campaign__project=other_project)
    assert other_user_tasks.filter(state__in=[TaskState.Pending, TaskState.Draft]).exists()
    assert other_user_tasks.exclude(state__in=[TaskState.Pending, TaskState.Draft]).exists()
    assert other_user_tasks.filter(is_preview=True).exists()

    expected_query = 6 if old_role == Role.Moderator or new_role == old_role else 9
    with django_assert_num_queries(expected_query):
        response = user.post(
            reverse("member-update", kwargs={"project_id": managed_project.id, "pk": membership.id}),
            {
                # The email won't change even if a value is provided (the field is disabled on the frontend)
                "user_email": "big_hack@callico.org",
                "role": new_role,
            },
        )
    assert response.status_code == 302
    assert response.url == reverse("members", kwargs={"project_id": managed_project.id})

    membership.refresh_from_db()

    # The member was updated (only their role, not their email)
    assert membership.user.email == other_user.email
    assert membership.role == new_role
    user_tasks = TaskUser.objects.filter(user=other_user)

    # ... their tasks (finished, draft/pending, preview) on another project are untouched
    assert other_user_tasks.exclude(state__in=[TaskState.Pending, TaskState.Draft]).exists()
    assert other_user_tasks.filter(state__in=[TaskState.Pending, TaskState.Draft]).exists()
    assert other_user_tasks.filter(is_preview=True).exists()

    # ... their finished tasks still exist
    assert project_user_tasks.exclude(state__in=[TaskState.Pending, TaskState.Draft]).exists()

    if old_role == Role.Contributor and new_role != old_role:
        # ... their unfinished tasks were deleted
        assert not project_user_tasks.filter(state__in=[TaskState.Pending, TaskState.Draft]).exists()
        # ... their preview tasks still exist
        assert project_user_tasks.filter(is_preview=True).exists()
    elif old_role == Role.Manager and new_role != old_role:
        # ... their unfinished tasks still exist
        assert project_user_tasks.filter(state__in=[TaskState.Pending, TaskState.Draft]).exists()
        # ... their preview tasks were deleted
        assert not project_user_tasks.filter(is_preview=True).exists()
    # ... they were a moderator or their role did not change (no task cleanup)
    else:
        # ... their unfinished tasks still exist
        assert project_user_tasks.filter(state__in=[TaskState.Pending, TaskState.Draft]).exists()
        # ... their preview tasks still exist
        assert project_user_tasks.filter(is_preview=True).exists()
