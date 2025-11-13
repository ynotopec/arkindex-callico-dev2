import pytest
from django.urls import reverse
from pytest_lazy_fixtures import lf as lazy_fixture

pytestmark = pytest.mark.django_db


def test_element_details_anonymous(anonymous, page_element):
    "An anonymous user is redirected to the login page"
    details_url = reverse("element-details", kwargs={"pk": page_element.id})
    response = anonymous.get(details_url)
    assert response.status_code == 302
    assert response.url == reverse("login") + f"?next={details_url}"


@pytest.mark.parametrize(
    "element",
    [
        lazy_fixture("public_element"),
        lazy_fixture("hidden_element"),
        lazy_fixture("page_element"),
    ],
)
def test_element_details_forbidden(user, element):
    response = user.get(reverse("element-details", kwargs={"pk": element.id}))
    assert response.status_code == 403


def test_element_details_wrong_element_id(user):
    response = user.get(reverse("element-details", kwargs={"pk": "cafecafe-cafe-cafe-cafe-cafecafecafe"}))
    assert response.status_code == 404
    assert response.context["exception"] == "No element matching this ID exists"


@pytest.mark.parametrize(
    "project",
    [lazy_fixture("moderated_project"), lazy_fixture("managed_project")],
)
def test_element_details_folder_element(user, folder_element):
    with pytest.raises(AssertionError) as e:
        user.get(reverse("element-details", kwargs={"pk": folder_element.id}))

    assert str(e.value) == "You can't view details of a folder element"


@pytest.mark.parametrize(
    "project",
    [lazy_fixture("moderated_project"), lazy_fixture("managed_project")],
)
def test_element_details(user, page_element, django_assert_num_queries):
    with django_assert_num_queries(5):
        response = user.get(reverse("element-details", kwargs={"pk": page_element.id}))
    assert response.status_code == 200

    assert response.context["element"] == page_element


@pytest.mark.parametrize(
    "project",
    [lazy_fixture("moderated_project"), lazy_fixture("managed_project")],
)
def test_element_with_tasks_details(user, tasks, page_element, django_assert_num_queries):
    with django_assert_num_queries(8):
        response = user.get(reverse("element-details", kwargs={"pk": page_element.id}))
    assert response.status_code == 200

    assert response.context["element"] == page_element
