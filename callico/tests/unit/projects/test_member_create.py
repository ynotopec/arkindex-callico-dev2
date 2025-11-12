from urllib.parse import quote

import pytest
from django.urls import reverse
from pytest_lazy_fixtures import lf as lazy_fixture

from callico.projects.models import Role

pytestmark = pytest.mark.django_db


def test_member_create_anonymous(anonymous, project):
    "An anonymous user is redirected to the login page"
    create_url = reverse("member-create", kwargs={"project_id": project.id})
    response = anonymous.post(create_url)
    assert response.status_code == 302
    assert response.url == reverse("login") + f"?next={quote(create_url)}"


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
def test_member_create_forbidden(user, forbidden_project):
    response = user.post(reverse("member-create", kwargs={"project_id": forbidden_project.id}))
    assert response.status_code == 403


def test_member_create_wrong_project_id(user):
    response = user.post(reverse("member-create", kwargs={"project_id": "cafecafe-cafe-cafe-cafe-cafecafecafe"}))
    assert response.status_code == 404
    assert response.context["exception"] == "No project matching this ID exists"


def test_member_create_missing_required_fields(user, managed_project):
    response = user.post(
        reverse("member-create", kwargs={"project_id": managed_project.id}),
        {
            "user_email": "",
            "role": "",
        },
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 2
    assert form.errors == {
        "user_email": ["This field is required."],
        "role": ["This field is required."],
    }


@pytest.mark.parametrize(
    "user_email, error",
    [
        ("unknown@callico.org", "There are no users with this email."),
        ("contributor@callico.org", "The user is already a member of this project."),
    ],
)
def test_member_create_invalid_user(user_email, error, user, managed_project):
    response = user.post(
        reverse("member-create", kwargs={"project_id": managed_project.id}),
        {
            "user_email": user_email,
            "role": Role.Contributor,
        },
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 1
    assert form.errors == {
        "user_email": [error],
    }


def test_member_create_invalid_role(user, managed_project, new_contributor):
    response = user.post(
        reverse("member-create", kwargs={"project_id": managed_project.id}),
        {
            "user_email": new_contributor.email,
            "role": "invalid",
        },
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 1
    assert form.errors == {
        "role": ["Select a valid choice. invalid is not one of the available choices."],
    }


def test_member_create_get(user, managed_project, django_assert_num_queries):
    with django_assert_num_queries(4):
        response = user.get(reverse("member-create", kwargs={"project_id": managed_project.id}))
    assert response.status_code == 200

    assert response.context["project"] == managed_project
    assert response.context["action"] == "Add"
    assert response.context["extra_action"] == "Add and create another"


@pytest.mark.parametrize("add_another", [False, True])
def test_member_create_post(add_another, user, managed_project, new_contributor, django_assert_num_queries):
    extra = {}
    if add_another:
        extra["Add and create another"] = "Add and create another"

    with django_assert_num_queries(7):
        response = user.post(
            reverse("member-create", kwargs={"project_id": managed_project.id}),
            {
                "user_email": new_contributor.email,
                "role": Role.Contributor,
                **extra,
            },
        )
    assert response.status_code == 302
    if not add_another:
        assert response.url == reverse("members", kwargs={"project_id": managed_project.id})
    else:
        assert response.url == reverse("member-create", kwargs={"project_id": managed_project.id})

    assert managed_project.memberships.get(user=new_contributor).role == Role.Contributor
