import pytest

from callico.users.models import User

pytestmark = pytest.mark.django_db


def test_create_user():
    "create_user creates a non-admin user"
    user = User.objects.create_user(display_name="User", email="user@callico", password="user")
    assert User.objects.count() == 1
    assert not user.is_admin
    assert not user.is_staff


def test_create_superuser():
    "create_superuser creates an admin user"
    user = User.objects.create_superuser(display_name="User", email="user@callico", password="user")
    assert User.objects.count() == 1
    assert user.is_admin
    assert user.is_staff
