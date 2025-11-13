import pytest
from django.db.models import Count
from django.db.models.query import QuerySet
from django.urls import reverse
from pytest_lazy_fixtures import lf as lazy_fixture

from callico.projects.models import Element

pytestmark = pytest.mark.django_db


def test_project_browse_anonymous(anonymous, project):
    "An anonymous user is redirected to the login page"
    browse_url = reverse("project-browse", kwargs={"project_id": project.id})
    response = anonymous.get(browse_url)
    assert response.status_code == 302
    assert response.url == reverse("login") + f"?next={browse_url}"


def test_project_browse_in_parent_anonymous(anonymous, project, folder_element):
    "An anonymous user is redirected to the login page"
    browse_url = reverse("project-browse", kwargs={"project_id": project.id, "element_id": folder_element.id})
    response = anonymous.get(browse_url)
    assert response.status_code == 302
    assert response.url == reverse("login") + f"?next={browse_url}"


@pytest.mark.parametrize(
    "forbidden_project",
    [lazy_fixture("public_project"), lazy_fixture("hidden_project"), lazy_fixture("project")],
)
def test_project_browse_forbidden(user, forbidden_project):
    response = user.get(reverse("project-browse", kwargs={"project_id": forbidden_project.id}))
    assert response.status_code == 403


def test_project_browse_wrong_project_id(user):
    response = user.get(reverse("project-browse", kwargs={"project_id": "cafecafe-cafe-cafe-cafe-cafecafecafe"}))
    assert response.status_code == 404
    assert response.context["exception"] == "No project matching this ID exists"


@pytest.mark.parametrize("project", [lazy_fixture("moderated_project"), lazy_fixture("managed_project")])
def test_project_browse_wrong_element_id(user, project):
    response = user.get(
        reverse(
            "project-browse",
            kwargs={"project_id": project.id, "element_id": "cafecafe-cafe-cafe-cafe-cafecafecafe"},
        )
    )
    assert response.status_code == 404
    assert response.context["exception"] == "No element matching this ID exists on this project"


@pytest.mark.parametrize("project", [lazy_fixture("moderated_project"), lazy_fixture("managed_project")])
def test_project_browse_page_element(user, project, page_element):
    with pytest.raises(AssertionError) as e:
        user.get(reverse("project-browse", kwargs={"project_id": project.id, "element_id": page_element.id}))

    assert str(e.value) == "You can't browse children of a non-folder element"


@pytest.mark.parametrize(
    "project, can_manage",
    [(lazy_fixture("moderated_project"), False), (lazy_fixture("managed_project"), True)],
)
@pytest.mark.parametrize(
    "parent_element_name, expected_elements",
    [
        (None, ["A", "Page 1", "Page 2"]),
        ("A", ["B", "C", "Page 3", "Page 4"]),
        ("B", ["D", "Page 5", "Page 6"]),
        ("C", []),
        ("D", ["Page 7"]),
    ],
)
def test_project_browse(
    user, project, can_manage, parent_element_name, expected_elements, build_architecture, django_assert_num_queries
):
    parent = None
    extra_kwargs = {}
    if parent_element_name:
        parent = project.elements.get(name=parent_element_name)
        extra_kwargs["element_id"] = parent.id

    num_queries = 9 + bool(parent_element_name) * 2 + bool(parent_element_name and len(expected_elements))
    with django_assert_num_queries(num_queries):
        response = user.get(reverse("project-browse", kwargs={"project_id": project.id, **extra_kwargs}))
    assert response.status_code == 200

    assert isinstance(response.context.get("object_list"), QuerySet)
    assert list(response.context["elements"].values_list("name", flat=True)) == expected_elements
    assert response.context["project"] == project
    assert response.context["parent"] == parent
    assert response.context["can_manage"] == can_manage
    assert response.context["types_counts"] == list(
        Element.objects.filter(project=project)
        .values("type__name")
        .annotate(total=Count("type__name"))
        .order_by("-total")
    )
