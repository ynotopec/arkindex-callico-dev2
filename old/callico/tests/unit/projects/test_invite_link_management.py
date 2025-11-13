import pytest
from django.urls import reverse
from pytest_lazy_fixtures import lf as lazy_fixture

pytestmark = pytest.mark.django_db


def test_invite_link_management_anonymous(anonymous, project):
    "An anonymous user is redirected to the login page"
    manage_url = reverse("invite-link-management", kwargs={"project_id": project.id})

    response = anonymous.get(manage_url)
    assert response.status_code == 302
    assert response.url == reverse("login") + f"?next={manage_url}"


def test_invite_link_management_wrong_project_id(user):
    manage_url = reverse("invite-link-management", kwargs={"project_id": "cafecafe-cafe-cafe-cafe-cafecafecafe"})

    response = user.get(manage_url)
    assert response.status_code == 404
    assert response.context["exception"] == "No project matching this ID exists"


@pytest.mark.parametrize(
    "forbidden_project",
    [
        # Hidden project
        lazy_fixture("hidden_project"),
        # Public project
        lazy_fixture("public_project"),
        # Contributor rights on project
        lazy_fixture("project"),
        # Moderator rights on project
        lazy_fixture("moderated_project"),
    ],
)
def test_invite_link_management_forbidden(user, forbidden_project):
    manage_url = reverse("invite-link-management", kwargs={"project_id": forbidden_project.id})

    response = user.get(manage_url)
    assert response.status_code == 403


def test_invite_link_management_get(user, managed_project, django_assert_num_queries):
    with django_assert_num_queries(4):
        response = user.get(reverse("invite-link-management", kwargs={"project_id": managed_project.id}))
    assert response.status_code == 200


def test_invite_link_management_post(user, managed_project, django_assert_num_queries):
    previous_invite_token = managed_project.invite_token

    manage_url = reverse("invite-link-management", kwargs={"project_id": managed_project.id})
    with django_assert_num_queries(6):
        response = user.post(manage_url)
    assert response.status_code == 302

    managed_project.refresh_from_db()
    assert managed_project.invite_token != previous_invite_token

    assert response.url == manage_url
