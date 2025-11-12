import pytest
from django.db.models.query import QuerySet
from django.urls import reverse
from pytest_lazy_fixtures import lf as lazy_fixture

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "client, expected_projects",
    [
        (
            lazy_fixture("user"),
            ["Managed project", "Project 1", "Project 2", "Project 3"],
        ),
        (
            lazy_fixture("admin"),
            ["Managed project", "Project 4", "Project 5", "Project 6"],
        ),
        (
            lazy_fixture("contributor"),
            ["Managed project"],
        ),
    ],
)
def test_project_list_my_projects(
    client,
    expected_projects,
    projects,
    managed_campaign_with_tasks,
    django_assert_num_queries,
):
    "All logged-in users can list projects of which they are members"
    with django_assert_num_queries(4):
        response = client.get(reverse("projects"))
    assert response.status_code == 200

    assert isinstance(response.context.get("object_list"), QuerySet)
    assert list(response.context["projects"].values_list("name", flat=True)) == expected_projects


@pytest.mark.parametrize(
    "client",
    [
        lazy_fixture("anonymous"),
        lazy_fixture("user"),
        lazy_fixture("contributor"),
    ],
)
def test_project_list_public_projects(
    client,
    projects,
    django_assert_num_queries,
):
    "All users (even anonymous ones) can list projects that are public"
    num_queries = 4 if client.user else 2
    with django_assert_num_queries(num_queries):
        response = client.get(reverse("projects") + "?public=True")
    assert response.status_code == 200

    assert isinstance(response.context.get("object_list"), QuerySet)
    # Listing a public project without role nor assigned tasks
    assert list(response.context["projects"].values_list("name", flat=True)) == ["Public project"]
