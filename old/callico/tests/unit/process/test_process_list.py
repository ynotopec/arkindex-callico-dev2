import pytest
from django.db.models.query import QuerySet
from django.urls import reverse

pytestmark = pytest.mark.django_db


def test_process_list_anonymous(anonymous, project):
    "An anonymous user is redirected to the login page"
    list_url = reverse("processes", kwargs={"pk": project.id})
    response = anonymous.get(list_url)
    assert response.status_code == 302
    assert response.url == reverse("login") + f"?next={list_url}"


def test_process_list_forbidden(user, hidden_project):
    response = user.get(reverse("processes", kwargs={"pk": hidden_project.id}))
    assert response.status_code == 403


def test_process_list_wrong_project_id(user):
    response = user.get(reverse("processes", kwargs={"pk": "cafecafe-cafe-cafe-cafe-cafecafecafe"}))
    assert response.status_code == 404
    assert response.context["exception"] == "No project matching this ID exists"


def test_process_list(user, managed_project, processes, django_assert_num_queries):
    with django_assert_num_queries(6):
        response = user.get(reverse("processes", kwargs={"pk": managed_project.id}))
    assert response.status_code == 200

    assert isinstance(response.context.get("object_list"), QuerySet)
    assert list(response.context["processes"].values_list("name", flat=True)) == [
        "Error process",
        "Completed process",
        "Running process",
        "Created process",
    ]
    assert response.context["project"] == managed_project
