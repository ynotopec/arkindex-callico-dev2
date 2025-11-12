import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db


def test_user_update_anonymous(anonymous):
    "An anonymous user is redirected to the login page"
    update_url = reverse("user-update")
    response = anonymous.post(update_url)
    assert response.status_code == 302
    assert response.url == reverse("login") + f"?next={update_url}"


def test_user_update_missing_required_fields(user):
    response = user.post(reverse("user-update"), {})
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 2
    assert form.errors == {
        "display_name": ["This field is required."],
        "preferred_language": ["This field is required."],
    }


def test_user_update_invalid_preferred_language(user):
    response = user.post(
        reverse("user-update"), {"display_name": "New username", "preferred_language": "not a valid language"}
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 1
    assert form.errors == {
        "preferred_language": ["Select a valid choice. not a valid language is not one of the available choices."]
    }


def test_user_update_get(user, django_assert_num_queries):
    with django_assert_num_queries(2):
        response = user.get(reverse("user-update"))
    assert response.status_code == 200


def test_user_update_post(user, django_assert_num_queries):
    assert user.user.preferred_language == "en"

    with django_assert_num_queries(3):
        response = user.post(reverse("user-update"), {"display_name": "New username", "preferred_language": "fr"})
    assert response.status_code == 302
    assert response.url == reverse("user-update")

    user.user.refresh_from_db()
    assert user.user.display_name == "New username"
    assert user.user.preferred_language == "fr"
