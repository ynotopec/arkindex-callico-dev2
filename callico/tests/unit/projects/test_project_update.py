import uuid

import pytest
from django.urls import reverse
from pytest_lazy_fixtures import lf as lazy_fixture

pytestmark = pytest.mark.django_db


def test_project_update_anonymous(anonymous, project):
    "An anonymous user is redirected to the login page"
    update_url = reverse("project-update", kwargs={"pk": project.id})
    response = anonymous.post(update_url)
    assert response.status_code == 302
    assert response.url == reverse("login") + f"?next={update_url}"


@pytest.mark.parametrize(
    "forbidden_project",
    [
        # Hidden project
        lazy_fixture("hidden_project"),
        # Public project
        lazy_fixture("public_project"),
        # Contributor rights on the project
        lazy_fixture("project"),
        # Moderator rights on the project
        lazy_fixture("moderated_project"),
    ],
)
def test_project_update_forbidden(user, forbidden_project):
    response = user.post(reverse("project-update", kwargs={"pk": forbidden_project.id}))
    assert response.status_code == 403


def test_project_update_wrong_project_id(user):
    response = user.post(reverse("project-update", kwargs={"pk": "cafecafe-cafe-cafe-cafe-cafecafecafe"}))
    assert response.status_code == 404
    assert response.context["exception"] == "No Project found matching the query"


def test_project_update_missing_required_fields(user, managed_project):
    response = user.post(reverse("project-update", kwargs={"pk": managed_project.id}), {})
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 1
    assert form.errors == {"name": ["This field is required."]}


def test_project_update_invalid_provider(user, managed_project):
    response = user.post(
        reverse("project-update", kwargs={"pk": managed_project.id}),
        {
            "name": "A project",
            "provider": "cafecafe-cafe-cafe-cafe-cafecafecafe",
            "provider_object_id": str(uuid.uuid4()),
        },
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 1
    assert form.errors == {"provider": ["Select a valid choice. That choice is not one of the available choices."]}


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
def test_project_update_provider_both_null_or_both_set(
    user, managed_project, arkindex_provider, missing_field, expected_errors
):
    provider_fields = {"provider": str(arkindex_provider.id), "provider_object_id": str(uuid.uuid4())}
    del provider_fields[missing_field]
    response = user.post(
        reverse("project-update", kwargs={"pk": managed_project.id}),
        {"name": "A project", **provider_fields},
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 1
    assert form.errors == expected_errors


def test_project_update_uuid_for_arkindex_provider(user, managed_project, arkindex_provider):
    response = user.post(
        reverse("project-update", kwargs={"pk": managed_project.id}),
        {
            "name": "A project",
            "provider": str(arkindex_provider.id),
            "provider_object_id": "Not an UUID",
        },
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 1
    assert form.errors == {
        "provider_object_id": ["The identifier must be an UUID when an Arkindex provider is specified"]
    }


def test_project_update_get(user, managed_project, django_assert_num_queries):
    with django_assert_num_queries(5):
        response = user.get(reverse("project-update", kwargs={"pk": managed_project.id}))
    assert response.status_code == 200


@pytest.mark.parametrize("fill_provider", [True, False])
def test_project_update_post(
    mocker,
    managed_campaign_with_tasks,
    user,
    arkindex_provider,
    iiif_provider,
    fill_provider,
    django_assert_num_queries,
    django_capture_on_commit_callbacks,
):
    celery_fetch_mock = mocker.patch("callico.process.arkindex.tasks.arkindex_fetch_extra_info.apply_async")

    managed_project = managed_campaign_with_tasks.project
    managed_project.provider = iiif_provider
    managed_project.provider_object_id = uuid.uuid4()
    managed_project.save()

    current_invite_token = managed_project.invite_token

    provider_object_id = str(uuid.uuid4())
    expected_query = 11 if fill_provider else 8
    with django_assert_num_queries(expected_query):
        with django_capture_on_commit_callbacks(execute=True):
            response = user.post(
                reverse("project-update", kwargs={"pk": managed_project.id}),
                {
                    "name": "A new name",
                    "provider": str(arkindex_provider.id) if fill_provider else "",
                    "provider_object_id": provider_object_id if fill_provider else "",
                },
            )
    assert response.status_code == 302

    # Check project attributes
    managed_project.refresh_from_db()
    assert managed_project.name == "A new name"
    assert not managed_project.public
    assert managed_project.provider == (arkindex_provider if fill_provider else None)
    assert managed_project.provider_object_id == (provider_object_id if fill_provider else None)
    assert managed_project.invite_token == current_invite_token

    assert celery_fetch_mock.call_count == int(fill_provider)
    assert response.url == reverse("project-details", kwargs={"project_id": managed_project.id})
