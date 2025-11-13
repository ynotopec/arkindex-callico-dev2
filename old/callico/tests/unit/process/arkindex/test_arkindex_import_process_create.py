import uuid

import pytest
from django.urls import reverse
from pytest_lazy_fixtures import lf as lazy_fixture

from callico.process.models import Process, ProcessMode

pytestmark = pytest.mark.django_db


def test_arkindex_import_process_create_anonymous(anonymous, project):
    "An anonymous user is redirected to the login page"
    create_url = reverse("arkindex-import-create", kwargs={"pk": project.id})
    response = anonymous.post(create_url)
    assert response.status_code == 302
    assert response.url == reverse("login") + f"?next={create_url}"


@pytest.mark.parametrize(
    "forbidden_project",
    [
        # Hidden project
        lazy_fixture("hidden_project"),
        # Public project
        lazy_fixture("public_project"),
        # Contributor rights on project
        lazy_fixture("project"),
        # Moderator rights on project
        lazy_fixture("moderated_project"),
    ],
)
def test_arkindex_import_process_create_forbidden(user, forbidden_project):
    response = user.post(reverse("arkindex-import-create", kwargs={"pk": forbidden_project.id}))
    assert response.status_code == 403


def test_arkindex_import_process_create_wrong_project_id(admin):
    response = admin.post(reverse("arkindex-import-create", kwargs={"pk": "cafecafe-cafe-cafe-cafe-cafecafecafe"}))
    assert response.status_code == 404
    assert response.context["exception"] == "No project matching this ID exists"


def test_arkindex_import_process_create_missing_or_wrong_provider(admin, managed_project, iiif_provider):
    managed_project.provider = iiif_provider
    managed_project.save()
    response = admin.post(reverse("arkindex-import-create", kwargs={"pk": managed_project.id}))
    assert response.status_code == 404
    assert (
        response.context["exception"]
        == "You can't create an Arkindex import process on a project that isn't linked to an Arkindex provider"
    )

    managed_project.provider = None
    managed_project.provider_object_id = None
    managed_project.save()
    response = admin.post(reverse("arkindex-import-create", kwargs={"pk": managed_project.id}))
    assert response.status_code == 404
    assert (
        response.context["exception"]
        == "You can't create an Arkindex import process on a project that isn't linked to an Arkindex provider"
    )


def test_arkindex_import_process_form_errors(admin, managed_project):
    response = admin.post(
        reverse("arkindex-import-create", kwargs={"pk": managed_project.id}),
        {
            "name": "",
            "element": "not uuid",
            "dataset": "not uuid",
            "types": ["unknown type"],
            "ml_class": "unknown class",
            "transcriptions": ["unknown worker_run"],
            "entities": ["unknown worker_run"],
            "elements_worker_run": ["invalid value"],
        },
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 8
    assert form.errors == {
        "name": ["This field is required."],
        "element": ["Enter a valid UUID."],
        "dataset": ["Enter a valid UUID."],
        "types": ["Select a valid choice. unknown type is not one of the available choices."],
        "ml_class": ["Select a valid choice. unknown class is not one of the available choices."],
        "transcriptions": ["Select a valid choice. unknown worker_run is not one of the available choices."],
        "entities": ["Select a valid choice. unknown worker_run is not one of the available choices."],
        "elements_worker_run": ["The value of this field is malformed and impossible to parse."],
    }
    assert Process.objects.count() == 0


def test_arkindex_import_process_form_element_or_dataset_error(admin, managed_project):
    response = admin.post(
        reverse("arkindex-import-create", kwargs={"pk": managed_project.id}),
        {
            "name": "Import process",
            "element": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "dataset": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        },
    )

    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 2
    assert form.errors == {
        "element": ["The dataset and element fields are mutually exclusive"],
        "dataset": ["The dataset and element fields are mutually exclusive"],
    }
    assert Process.objects.count() == 0


def test_arkindex_import_process_form_dataset_sets_requires_dataset_error(admin, managed_project):
    response = admin.post(
        reverse("arkindex-import-create", kwargs={"pk": managed_project.id}),
        {
            "name": "Import process",
            "dataset_sets": ["unit-01", "unit-00"],
        },
    )

    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 1
    assert form.errors == {"dataset": ["The dataset field must be filled in order to select sets"]}
    assert Process.objects.count() == 0


def test_arkindex_import_process_form_entities_error(admin, managed_project):
    response = admin.post(
        reverse("arkindex-import-create", kwargs={"pk": managed_project.id}),
        {
            "name": "A Process",
            "entities": ["manual"],
        },
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 1
    assert form.errors == {
        "entities": ["It is not possible to import entities without also importing transcriptions"],
    }
    assert Process.objects.count() == 0


def test_arkindex_import_process_create_no_type_no_class_no_wr_help_texts(admin, managed_project):
    response = admin.get(reverse("arkindex-import-create", kwargs={"pk": managed_project.id}))
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.fields) == 10
    assert (
        form.fields["types"].help_text
        == "No type was found for this project, it means that an error might have occurred during the retrieval of extra information from Arkindex. Therefore this filter is disabled, please contact an administrator if you wish to use it."
    )
    assert "disabled" in form.fields["types"].widget.attrs
    assert (
        form.fields["ml_class"].help_text
        == "No class was found for this project, it means that an error might have occurred during the retrieval of extra information from Arkindex. Therefore this filter is disabled, please contact an administrator if you wish to use it."
    )
    assert "disabled" in form.fields["ml_class"].widget.attrs
    assert (
        form.fields["elements_worker_run"].help_text
        == "No type and/or worker run was found for this project, it means that an error might have occurred during the retrieval of extra information from Arkindex. Therefore this filter is disabled, please contact an administrator if you wish to use it."
    )
    assert "disabled" in form.fields["elements_worker_run"].widget.attrs


@pytest.mark.parametrize(
    "form_values, expected_config",
    [
        (
            {
                "element": "",
                "dataset": "",
                "dataset_sets": "",
                "types": [],
                "ml_class": "",
                "transcriptions": [],
                "entities": [],
                "elements_worker_run": "",
                "metadata": "",
            },
            {
                "element": None,
                "dataset": None,
                "dataset_sets": [],
                "types": [],
                "class_name": "",
                "transcriptions": [],
                "entities": [],
                "elements_worker_run": {},
                "metadata": [],
            },
        ),
        (
            {
                "element": "cafecafe-cafe-cafe-cafe-cafecafecafe",
                "dataset": "",
                "dataset_sets": "",
                "types": ["folder", "page"],
                "ml_class": "train",
                "transcriptions": [
                    "22222222-2222-2222-2222-222222222222",
                    "manual",
                    "11111111-1111-1111-1111-111111111111",
                ],
                "entities": [
                    "manual",
                    "33333333-3333-3333-3333-333333333333",
                ],
                "elements_worker_run": "page=22222222-2222-2222-2222-222222222222,text_line=11111111-1111-1111-1111-111111111111",
                "metadata": "    year   , month,day ",
            },
            {
                "element": "cafecafe-cafe-cafe-cafe-cafecafecafe",
                "dataset": None,
                "dataset_sets": [],
                "types": ["folder", "page"],
                "class_name": "train",
                "transcriptions": [
                    "22222222-2222-2222-2222-222222222222",
                    "manual",
                    "11111111-1111-1111-1111-111111111111",
                ],
                "entities": [
                    "manual",
                    "33333333-3333-3333-3333-333333333333",
                ],
                "elements_worker_run": {
                    "page": "22222222-2222-2222-2222-222222222222",
                    "text_line": "11111111-1111-1111-1111-111111111111",
                },
                "metadata": ["year", "month", "day"],
            },
        ),
        (
            {
                "element": "",
                "dataset": "cafecafe-cafe-cafe-cafe-cafecafecafe",
                "dataset_sets": "  train   , val",
                "types": ["folder", "page"],
                "ml_class": "train",
                "transcriptions": [
                    "22222222-2222-2222-2222-222222222222",
                    "manual",
                    "11111111-1111-1111-1111-111111111111",
                ],
                "entities": [
                    "manual",
                    "33333333-3333-3333-3333-333333333333",
                ],
                "elements_worker_run": "page=22222222-2222-2222-2222-222222222222,text_line=11111111-1111-1111-1111-111111111111",
                "metadata": "    year   , month,day ",
            },
            {
                "element": None,
                "dataset": "cafecafe-cafe-cafe-cafe-cafecafecafe",
                "dataset_sets": ["train", "val"],
                "types": ["folder", "page"],
                "class_name": "train",
                "transcriptions": [
                    "22222222-2222-2222-2222-222222222222",
                    "manual",
                    "11111111-1111-1111-1111-111111111111",
                ],
                "entities": [
                    "manual",
                    "33333333-3333-3333-3333-333333333333",
                ],
                "elements_worker_run": {
                    "page": "22222222-2222-2222-2222-222222222222",
                    "text_line": "11111111-1111-1111-1111-111111111111",
                },
                "metadata": ["year", "month", "day"],
            },
        ),
        (
            {
                "element": "",
                "dataset": "cafecafe-cafe-cafe-cafe-cafecafecafe",
                "dataset_sets": "validation",
                "types": ["folder", "page"],
                "ml_class": "train",
                "transcriptions": [
                    "22222222-2222-2222-2222-222222222222",
                    "manual",
                    "11111111-1111-1111-1111-111111111111",
                ],
                "entities": [
                    "manual",
                    "33333333-3333-3333-3333-333333333333",
                ],
                "elements_worker_run": "page=22222222-2222-2222-2222-222222222222,text_line=11111111-1111-1111-1111-111111111111",
                "metadata": "    year   , month,day ",
            },
            {
                "element": None,
                "dataset": "cafecafe-cafe-cafe-cafe-cafecafecafe",
                "dataset_sets": ["validation"],
                "types": ["folder", "page"],
                "class_name": "train",
                "transcriptions": [
                    "22222222-2222-2222-2222-222222222222",
                    "manual",
                    "11111111-1111-1111-1111-111111111111",
                ],
                "entities": [
                    "manual",
                    "33333333-3333-3333-3333-333333333333",
                ],
                "elements_worker_run": {
                    "page": "22222222-2222-2222-2222-222222222222",
                    "text_line": "11111111-1111-1111-1111-111111111111",
                },
                "metadata": ["year", "month", "day"],
            },
        ),
    ],
)
def test_arkindex_import_process_create(
    mocker, django_assert_num_queries, user, form_values, expected_config, managed_project
):
    celery_mock = mocker.patch("callico.process.arkindex.tasks.arkindex_import.apply_async")

    managed_project.types.create(
        name="Folder", folder=True, provider=managed_project.provider, provider_object_id="folder"
    )
    managed_project.types.create(name="Page", provider=managed_project.provider, provider_object_id="page")
    managed_project.types.create(name="Paragraph", provider=managed_project.provider, provider_object_id="paragraph")
    managed_project.classes.create(
        name="train", provider=managed_project.provider, provider_object_id=str(uuid.uuid4())
    )
    managed_project.classes.create(name="test", provider=managed_project.provider, provider_object_id=str(uuid.uuid4()))
    managed_project.provider_extra_information = {
        "worker_runs": [
            {"id": "11111111-1111-1111-1111-111111111111", "summary": "My worker (abcdefgh.....) - Release 1000"},
            {"id": "22222222-2222-2222-2222-222222222222", "summary": "My other worker (ijklmnop.....) - Test commit"},
            {"id": "33333333-3333-3333-3333-333333333333", "summary": "My fake worker"},
        ]
    }
    managed_project.save()

    with django_assert_num_queries(7):
        response = user.post(
            reverse("arkindex-import-create", kwargs={"pk": managed_project.id}), {"name": "My process", **form_values}
        )

    assert response.status_code == 302

    process = Process.objects.get()
    assert process.name == "My process"
    assert process.mode == ProcessMode.ArkindexImport.value
    assert process.configuration == {
        "arkindex_provider": str(managed_project.provider.id),
        "project_id": str(managed_project.id),
        "corpus": str(managed_project.provider_object_id),
        "elements_worker_run": {},
        "metadata": [],
        "transcriptions": [],
        "entities": [],
        **expected_config,
    }
    assert process.project == managed_project
    assert process.creator == user.user

    assert celery_mock.call_count == 1

    assert response.url == reverse("process-details", kwargs={"pk": process.id})
