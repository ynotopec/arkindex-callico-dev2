import pytest
from django.urls import reverse
from pytest_lazy_fixtures import lf as lazy_fixture

pytestmark = pytest.mark.django_db


def test_project_details_forbidden(user, hidden_project):
    response = user.get(reverse("project-details", kwargs={"project_id": hidden_project.id}))
    assert response.status_code == 403


def test_project_details_wrong_project_id(user):
    response = user.get(reverse("project-details", kwargs={"project_id": "cafecafe-cafe-cafe-cafe-cafecafecafe"}))
    assert response.status_code == 404
    assert response.context["exception"] == "No project matching this ID exists"


@pytest.mark.parametrize("client", [lazy_fixture("anonymous"), lazy_fixture("user")])
def test_project_details_public_project(django_assert_num_queries, client, public_project, public_campaign):
    num_queries = 7 if client.user else 4
    with django_assert_num_queries(num_queries):
        response = client.get(reverse("project-details", kwargs={"project_id": public_project.id}))
    assert response.status_code == 200

    assert response.context["project"] == public_project
    assert response.context["can_manage"] is False
    assert response.context["can_moderate"] is False
    assert [campaign.name for campaign in response.context["campaigns"]] == ["Campaign"]


@pytest.mark.parametrize(
    "client, project_name",
    [
        (lazy_fixture("user"), "Project 1"),
        (lazy_fixture("admin"), "Project 4"),
    ],
)
def test_project_details_contributed_project(django_assert_num_queries, client, project_name, projects, campaigns):
    project = projects.get(name=project_name)
    with django_assert_num_queries(10):
        response = client.get(reverse("project-details", kwargs={"project_id": project.id}))
    assert response.status_code == 200

    assert response.context["project"] == project
    assert response.context["can_manage"] is False
    assert response.context["can_moderate"] is False
    assert [campaign.name for campaign in response.context["campaigns"]] == [
        "Campaign closed",
        "Campaign created",
        "Campaign running",
    ]


@pytest.mark.parametrize(
    "client, project_name",
    [
        (lazy_fixture("user"), "Project 2"),
        (lazy_fixture("admin"), "Project 5"),
    ],
)
def test_project_details_moderated_project(django_assert_num_queries, client, project_name, projects, campaigns):
    project = projects.get(name=project_name)
    with django_assert_num_queries(10):
        response = client.get(reverse("project-details", kwargs={"project_id": project.id}))
    assert response.status_code == 200

    assert response.context["project"] == project
    assert response.context["can_manage"] is False
    assert response.context["can_moderate"] is True
    assert [campaign.name for campaign in response.context["campaigns"]] == [
        "Campaign closed",
        "Campaign created",
        "Campaign running",
    ]


@pytest.mark.parametrize(
    "client, project_name",
    [
        (lazy_fixture("user"), "Project 3"),
        (lazy_fixture("admin"), "Project 6"),
    ],
)
def test_project_details_managed_project(django_assert_num_queries, client, project_name, projects, campaigns):
    project = projects.get(name=project_name)
    with django_assert_num_queries(10):
        response = client.get(reverse("project-details", kwargs={"project_id": project.id}))
    assert response.status_code == 200

    assert response.context["project"] == project
    assert response.context["can_manage"] is True
    assert response.context["can_moderate"] is False
    assert [campaign.name for campaign in response.context["campaigns"]] == [
        "Campaign closed",
        "Campaign created",
        "Campaign running",
    ]
