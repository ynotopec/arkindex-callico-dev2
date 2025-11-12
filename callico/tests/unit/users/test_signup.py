import pytest
from django.test import override_settings
from django.urls import reverse

pytestmark = pytest.mark.django_db


@override_settings(SIGNUP_ENABLED=True)
def test_signup_required_fields(anonymous):
    response = anonymous.post(reverse("signup"), {"email": "", "password1": "", "password2": ""})
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 5
    assert form.errors == {
        "display_name": ["This field is required."],
        "email": ["This field is required."],
        "password1": ["This field is required."],
        "password2": ["This field is required."],
        "preferred_language": ["This field is required."],
    }


@override_settings(SIGNUP_ENABLED=True)
def test_signup_invalid_fields(anonymous):
    "A user can access the login view and log in"
    response = anonymous.post(
        reverse("signup"),
        {
            "display_name": "Test user",
            "email": "not a valid email",
            "password1": "sTr0nG_p4SsW0rD",
            "password2": "not the same",
            "preferred_language": "en",
        },
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 2
    assert form.errors == {
        "email": ["Enter a valid email address."],
        "password2": ["The two password fields didn’t match."],
    }


def test_signup_not_enabled(anonymous):
    response = anonymous.get(reverse("signup"))
    assert response.status_code == 404


@override_settings(SIGNUP_ENABLED=True)
def test_signup(mocker, anonymous):
    celery_mock = mocker.patch("callico.users.tasks.send_email.delay")

    response = anonymous.post(
        reverse("signup"),
        {
            "display_name": "Test user",
            "email": "test_user@callico.com",
            "password1": "sTr0nG_p4SsW0rD",
            "password2": "sTr0nG_p4SsW0rD",
            "preferred_language": "en",
        },
    )
    assert response.status_code == 302
    assert response.url == reverse("home")

    assert celery_mock.call_count == 1


@override_settings(SIGNUP_ENABLED=True)
def test_signup_next(mocker, anonymous):
    celery_mock = mocker.patch("callico.users.tasks.send_email.delay")
    next_param = "next/page/"

    response = anonymous.post(
        reverse("signup") + f"?next={next_param}",
        {
            "display_name": "Test user",
            "email": "test_user@callico.com",
            "password1": "sTr0nG_p4SsW0rD",
            "password2": "sTr0nG_p4SsW0rD",
            "preferred_language": "en",
        },
    )
    assert response.status_code == 302
    assert response.url == next_param

    assert celery_mock.call_count == 1
