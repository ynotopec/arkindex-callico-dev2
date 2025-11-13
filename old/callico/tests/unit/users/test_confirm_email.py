import pytest
from django.contrib.messages import get_messages
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from callico.users.tokens import account_activation_token

pytestmark = pytest.mark.django_db


def test_confirm_email_wrong_user(user):
    assert not user.user.email_validated

    wrong_uidb64 = urlsafe_base64_encode(force_bytes("cafecafe-cafe-cafe-cafe-cafecafecafe"))
    token = account_activation_token.make_token(user.user)
    response = user.get(reverse("confirm-email", kwargs={"uidb64": wrong_uidb64, "token": token}))
    assert response.status_code == 302
    assert response.url == reverse("home")
    user.user.refresh_from_db()
    assert not user.user.email_validated
    assert [m.message for m in get_messages(response.wsgi_request)] == [
        "The confirmation link was invalid, possibly because it has already been used."
    ]


def test_confirm_email_wrong_token(user):
    assert not user.user.email_validated

    uidb64 = urlsafe_base64_encode(force_bytes(user.user.pk))
    wrong_token = account_activation_token.make_token(user.user)[:5] + "wrong"
    response = user.get(reverse("confirm-email", kwargs={"uidb64": uidb64, "token": wrong_token}))
    assert response.status_code == 302
    assert response.url == reverse("home")
    user.user.refresh_from_db()
    assert not user.user.email_validated
    assert [m.message for m in get_messages(response.wsgi_request)] == [
        "The confirmation link was invalid, possibly because it has already been used."
    ]


def test_confirm_email_already_validated(user):
    assert not user.user.email_validated

    uidb64 = urlsafe_base64_encode(force_bytes(user.user.pk))
    token = account_activation_token.make_token(user.user)
    # Validate the email with a token a first time
    user.get(reverse("confirm-email", kwargs={"uidb64": uidb64, "token": token}))
    user.user.refresh_from_db()
    assert user.user.email_validated

    response = user.get(reverse("confirm-email", kwargs={"uidb64": uidb64, "token": token}))
    assert response.status_code == 302
    assert response.url == reverse("home")
    user.user.refresh_from_db()
    assert user.user.email_validated
    assert [m.message for m in get_messages(response.wsgi_request)] == [
        "Your account has been confirmed.",
        "The confirmation link was invalid, possibly because it has already been used.",
    ]


def test_confirm_email(user):
    assert not user.user.email_validated

    uidb64 = urlsafe_base64_encode(force_bytes(user.user.pk))
    token = account_activation_token.make_token(user.user)
    response = user.get(reverse("confirm-email", kwargs={"uidb64": uidb64, "token": token}))
    assert response.status_code == 302
    assert response.url == reverse("home")
    user.user.refresh_from_db()
    assert user.user.email_validated
    assert [m.message for m in get_messages(response.wsgi_request)] == ["Your account has been confirmed."]
