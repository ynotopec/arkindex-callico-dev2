from urllib.parse import quote

import pytest
from django.db.models.query import QuerySet
from django.urls import reverse
from pytest_lazy_fixtures import lf as lazy_fixture

from callico.projects.models import Role

pytestmark = pytest.mark.django_db


def test_member_list_anonymous(anonymous, project):
    "An anonymous user is redirected to the login page"
    list_url = reverse("members", kwargs={"project_id": project.id})
    response = anonymous.get(list_url)
    assert response.status_code == 302
    assert response.url == reverse("login") + f"?next={quote(list_url)}"


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
def test_member_list_forbidden(user, forbidden_project):
    response = user.get(reverse("members", kwargs={"project_id": forbidden_project.id}))
    assert response.status_code == 403


def test_member_list_wrong_project_id(user):
    response = user.get(reverse("members", kwargs={"project_id": "cafecafe-cafe-cafe-cafe-cafecafecafe"}))
    assert response.status_code == 404
    assert response.context["exception"] == "No project matching this ID exists"


def test_member_list(user, managed_project, django_assert_num_queries):
    with django_assert_num_queries(6):
        response = user.get(reverse("members", kwargs={"project_id": managed_project.id}))
    assert response.status_code == 200

    assert isinstance(response.context.get("object_list"), QuerySet)
    assert list(response.context["memberships"].values_list("user__email", "role")) == [
        ("contributor@callico.org", Role.Contributor),
        ("root@callico.org", Role.Manager),
        ("user@callico.org", Role.Manager),
    ]
    assert response.context["project"] == managed_project
