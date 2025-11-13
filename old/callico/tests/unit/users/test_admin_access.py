import pytest
from django.urls import reverse
from pytest_lazy_fixtures import lf as lazy_fixture

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("client", [lazy_fixture("user"), lazy_fixture("anonymous")])
def test_forbidden_admin_panel(client):
    """A simple user can't access the Django administration panel"""
    response = client.post(reverse("admin:index"))
    assert response.wsgi_request.user.is_superuser is False
    assert response.status_code == 302
    assert response.url == "/admin/login/?next=/admin/"


def test_admin_panel(admin):
    """An admin user can access the Django administration panel"""
    response = admin.post(reverse("admin:index"))
    assert response.wsgi_request.user.is_superuser is True
    assert response.status_code == 200
