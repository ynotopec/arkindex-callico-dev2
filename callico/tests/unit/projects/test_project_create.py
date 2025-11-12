import uuid

import pytest
from django.conf import settings
from django.urls import reverse
from pytest_lazy_fixtures import lf as lazy_fixture

from callico.projects.models import Project, Role

pytestmark = pytest.mark.django_db


def test_project_create_anonymous(anonymous):
    "An anonymous user is redirected to the login page"
    create_url = reverse("project-create")
    response = anonymous.post(create_url)
    assert response.status_code == 302
    assert response.url == reverse("login") + f"?next={create_url}"


def test_project_create_forbidden(user):
    assert not settings.PROJECT_CREATION_ALLOWED
    response = user.post(reverse("project-create"))
    assert response.status_code == 403


def test_project_create_missing_required_fields(admin):
    response = admin.post(reverse("project-create"))
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 1
    assert form.errors == {"name": ["This field is required."]}
    assert Project.objects.count() == 0


def test_project_create_invalid_provider(admin):
    response = admin.post(
        reverse("project-create"), {"name": "A project", "provider": "cafecafe-cafe-cafe-cafe-cafecafecafe"}
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 1
    assert form.errors == {"provider": ["Select a valid choice. That choice is not one of the available choices."]}
    assert Project.objects.count() == 0


@pytest.mark.parametrize(
    "missing_field, expected_errors",
    [
        (
            "provider",
            {"provider_object_id": ["A provider must be specified if you provide an identifier and vice versa"]},
        ),
        (
            "provider_object_id",
            {"provider": ["An identifier must be provided if you specify a provider and vice versa"]},
        ),
    ],
)
def test_project_create_provider_both_null_or_both_set(admin, arkindex_provider, missing_field, expected_errors):
    provider_fields = {"provider": str(arkindex_provider.id), "provider_object_id": str(uuid.uuid4())}
    del provider_fields[missing_field]
    response = admin.post(reverse("project-create"), {"name": "A project", **provider_fields})
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 1
    assert form.errors == expected_errors
    assert Project.objects.count() == 0


def test_project_create_get(admin, django_assert_num_queries):
    with django_assert_num_queries(3):
        response = admin.get(reverse("project-create"))
    assert response.status_code == 200


@pytest.mark.parametrize(
    "client, allowed_setting",
    [
        # Non-staff users can create projects when the PROJECT_CREATION_ALLOWED is set to True
        (lazy_fixture("user"), True),
        # Staff users are always allowed to create projects
        (lazy_fixture("admin"), False),
        (lazy_fixture("admin"), True),
    ],
)
@pytest.mark.parametrize("fill_provider", [True, False])
def test_project_create_post(
    mocker,
    django_assert_num_queries,
    django_capture_on_commit_callbacks,
    arkindex_provider,
    client,
    allowed_setting,
    fill_provider,
):
    old_setting = settings.PROJECT_CREATION_ALLOWED
    settings.PROJECT_CREATION_ALLOWED = allowed_setting

    celery_fetch_mock = mocker.patch("callico.process.arkindex.tasks.arkindex_fetch_extra_info.apply_async")

    provider_object_id = str(uuid.uuid4())
    expected_query = 12 if fill_provider else 9
    with django_assert_num_queries(expected_query):
        with django_capture_on_commit_callbacks(execute=True):
            response = client.post(
                reverse("project-create"),
                {
                    "name": "A project",
                    "provider": str(arkindex_provider.id) if fill_provider else "",
                    "provider_object_id": provider_object_id if fill_provider else "",
                },
            )
    assert response.status_code == 302
    assert Project.objects.count() == 1

    created = Project.objects.first()
    assert created.name == "A project"
    assert not created.public
    assert created.provider == (arkindex_provider if fill_provider else None)
    assert created.provider_object_id == (provider_object_id if fill_provider else None)
    assert created.invite_token

    assert created.memberships.count() == 1

    membership = created.memberships.first()
    assert membership.user == client.user
    assert membership.role == Role.Manager

    assert celery_fetch_mock.call_count == int(fill_provider)
    assert response.url == reverse("project-details", kwargs={"project_id": created.id})

    # Restore the setting to its default value
    settings.PROJECT_CREATION_ALLOWED = old_setting
