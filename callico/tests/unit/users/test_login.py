import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db


def test_login_failed(user_with_password):
    response = user_with_password.post(
        reverse("login"), {"username": user_with_password.user.email, "password": "wrong"}
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 1
    assert tuple(form.errors) == ("__all__",)


def test_login(user_with_password):
    "A user can access the login view and log in"
    response = user_with_password.post(
        reverse("login"), {"username": user_with_password.user.email, "password": "user"}
    )
    assert response.status_code == 302
    assert response.url == reverse("projects")


def test_login_next(user_with_password):
    next_path = "/next/page/"
    response = user_with_password.post(
        reverse("login") + f"?next={next_path}", {"username": user_with_password.user.email, "password": "user"}
    )
    assert response.status_code == 302
    assert response.url == next_path
