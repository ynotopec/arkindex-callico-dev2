import logging
import uuid

import pytest

from callico.process.arkindex.imports import ArkindexFetchExtraInfo
from callico.projects.models import Class, Type

pytestmark = pytest.mark.django_db


def test_arkindex_fetch_extra_info_create_classes(caplog, mock_arkindex_client, project, process):
    dog_id = str(uuid.uuid4())
    cat_id = str(uuid.uuid4())

    fetch_process = ArkindexFetchExtraInfo(process, project.provider.id, str(project.id))
    mock_arkindex_client.add_response(
        "ListCorpusMLClasses",
        [
            {"id": dog_id, "name": "Dog"},
            {"id": cat_id, "name": "Cat"},
        ],
        id=project.provider_object_id,
    )

    fetch_process.create_classes(project)
    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == [
            (logging.INFO, 'Using project "Test project"'),
            (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
            (logging.INFO, 'Class "Dog" processed'),
            (logging.INFO, 'Class "Cat" processed'),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )

    assert list(
        Class.objects.filter(project_id=project.id)
        .order_by("name")
        .values_list("name", "provider_object_id", "provider")
    ) == [
        ("Cat", cat_id, fetch_process.arkindex_provider.id),
        ("Dog", dog_id, fetch_process.arkindex_provider.id),
    ]


def test_arkindex_fetch_extra_info_create_types(caplog, mock_arkindex_client, project, process):
    fetch_process = ArkindexFetchExtraInfo(process, project.provider.id, str(project.id))
    mock_arkindex_client.add_response(
        "RetrieveCorpus",
        {
            "name": "A corpus",
            "types": [
                {
                    "id": str(uuid.uuid4()),
                    "slug": "folder",
                    "display_name": "Folder",
                    "folder": True,
                    "color": "aaaaaa",
                },
                {
                    "id": str(uuid.uuid4()),
                    "slug": "paragraph",
                    "display_name": "Paragraph",
                    "folder": False,
                    "color": "bbbbbb",
                },
                {
                    "id": str(uuid.uuid4()),
                    "slug": "text_line",
                    "display_name": "Text line",
                    "folder": False,
                    "color": "cccccc",
                },
                {"id": str(uuid.uuid4()), "slug": "word", "display_name": "Word", "folder": False, "color": "dddddd"},
            ],
        },
        id=project.provider_object_id,
    )

    fetch_process.create_types(project)
    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == [
            (logging.INFO, 'Using project "Test project"'),
            (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
            (logging.INFO, 'Type "Folder" processed'),
            (logging.INFO, 'Type "Paragraph" processed'),
            (logging.INFO, 'Type "Text line" processed'),
            (logging.INFO, 'Type "Word" processed'),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )

    assert list(
        Type.objects.filter(project_id=project.id)
        .order_by("name")
        .values_list("name", "folder", "color", "provider_object_id", "provider_id")
    ) == [
        ("Folder", True, "aaaaaa", "folder", fetch_process.arkindex_provider.id),
        ("Line", False, "28b62c", "line", fetch_process.arkindex_provider.id),
        ("Page", False, "28b62c", "page", fetch_process.arkindex_provider.id),
        ("Paragraph", False, "bbbbbb", "paragraph", fetch_process.arkindex_provider.id),
        ("Text line", False, "cccccc", "text_line", fetch_process.arkindex_provider.id),
        ("Volume", False, "28b62c", "volume", fetch_process.arkindex_provider.id),
        ("Word", False, "dddddd", "word", fetch_process.arkindex_provider.id),
    ]


def test_arkindex_fetch_extra_info_store_worker_runs(caplog, mock_arkindex_client, project, process):
    fetch_process = ArkindexFetchExtraInfo(process, project.provider.id, str(project.id))
    wr_payload = [
        {
            "id": str(uuid.uuid4()),
            "parents": [],
            "worker_version": {},
            "process": {},
            "configuration": {},
            "model_version": {},
            "summary": "My worker (blablabla) - My super commit",
        }
    ]
    mock_arkindex_client.add_response(
        "ListCorpusWorkerRuns",
        wr_payload,
        id=project.provider_object_id,
    )

    fetch_process.store_worker_runs(project)
    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == [
            (logging.INFO, 'Using project "Test project"'),
            (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
            (logging.INFO, "Worker runs stored"),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )

    assert project.provider_extra_information == {"worker_runs": wr_payload}


def test_arkindex_fetch_extra_info_store_entity_types(caplog, mock_arkindex_client, project, process):
    fetch_process = ArkindexFetchExtraInfo(process, project.provider.id, str(project.id))
    entity_types_payload = [
        {
            "id": str(uuid.uuid4()),
            "color": "ffffff",
            "name": "surname",
        }
    ]
    mock_arkindex_client.add_response(
        "ListCorpusEntityTypes",
        entity_types_payload,
        id=project.provider_object_id,
    )

    fetch_process.store_entity_types(project)
    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == [
            (logging.INFO, 'Using project "Test project"'),
            (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
            (logging.INFO, "Entity types stored"),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )

    assert project.provider_extra_information == {"entity_types": entity_types_payload}


def test_arkindex_fetch_extra_info_run_skip_non_linked_project(
    caplog, mock_arkindex_client, project, public_project, process
):
    fetch_process = ArkindexFetchExtraInfo(process, project.provider.id, str(public_project.id))

    fetch_process.run()
    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == [
            (logging.INFO, 'Using project "Public project"'),
            (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
            (logging.INFO, "Skipping the retrieval of additional information as the project does not have a corpus"),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )

    assert list(Class.objects.filter(project_id=public_project.id).values_list("name", flat=True)) == []
    assert list(Type.objects.filter(project_id=public_project.id).values_list("name", flat=True)) == []
    assert public_project.provider_extra_information == {}


def test_arkindex_fetch_extra_info_run_create_classes_error(mock_arkindex_client, project, process):
    fetch_process = ArkindexFetchExtraInfo(process, project.provider.id, str(project.id))
    mock_arkindex_client.add_error_response(
        "ListCorpusMLClasses",
        id=project.provider_object_id,
        status_code=500,
    )

    with pytest.raises(Exception, match="Failed creating classes: 500 - Mock error response"):
        fetch_process.run()


def test_arkindex_fetch_extra_info_run_create_types_error(mocker, mock_arkindex_client, project, process):
    mock_create_classes = mocker.patch("callico.process.arkindex.imports.ArkindexFetchExtraInfo.create_classes")

    fetch_process = ArkindexFetchExtraInfo(process, project.provider.id, str(project.id))
    mock_arkindex_client.add_error_response(
        "RetrieveCorpus",
        id=project.provider_object_id,
        status_code=400,
    )

    with pytest.raises(Exception, match="Failed creating element types: 400 - Mock error response"):
        fetch_process.run()

    assert mock_create_classes.call_count == 1


def test_arkindex_fetch_extra_info_run_store_worker_runs_error(mocker, mock_arkindex_client, project, process):
    mock_create_classes = mocker.patch("callico.process.arkindex.imports.ArkindexFetchExtraInfo.create_classes")
    mock_create_types = mocker.patch("callico.process.arkindex.imports.ArkindexFetchExtraInfo.create_types")

    fetch_process = ArkindexFetchExtraInfo(process, project.provider.id, str(project.id))
    mock_arkindex_client.add_error_response(
        "ListCorpusWorkerRuns",
        id=project.provider_object_id,
        status_code=500,
    )

    with pytest.raises(
        Exception, match="Failed adding worker runs to the project extra information: 500 - Mock error response"
    ):
        fetch_process.run()

    assert mock_create_classes.call_count == 1
    assert mock_create_types.call_count == 1


def test_arkindex_fetch_extra_info_run_store_entity_types_error(mocker, mock_arkindex_client, project, process):
    mock_create_classes = mocker.patch("callico.process.arkindex.imports.ArkindexFetchExtraInfo.create_classes")
    mock_create_types = mocker.patch("callico.process.arkindex.imports.ArkindexFetchExtraInfo.create_types")
    mock_store_worker_runs = mocker.patch("callico.process.arkindex.imports.ArkindexFetchExtraInfo.store_worker_runs")

    fetch_process = ArkindexFetchExtraInfo(process, project.provider.id, str(project.id))
    mock_arkindex_client.add_error_response(
        "ListCorpusEntityTypes",
        id=project.provider_object_id,
        status_code=500,
    )

    with pytest.raises(
        Exception, match="Failed adding entity types to the project extra information: 500 - Mock error response"
    ):
        fetch_process.run()

    assert mock_create_classes.call_count == 1
    assert mock_create_types.call_count == 1
    assert mock_store_worker_runs.call_count == 1


def test_arkindex_fetch_extra_info_run(mocker, mock_arkindex_client, project, process):
    mock_create_classes = mocker.patch("callico.process.arkindex.imports.ArkindexFetchExtraInfo.create_classes")
    mock_create_types = mocker.patch("callico.process.arkindex.imports.ArkindexFetchExtraInfo.create_types")
    mock_store_worker_runs = mocker.patch("callico.process.arkindex.imports.ArkindexFetchExtraInfo.store_worker_runs")
    mock_store_entity_types = mocker.patch("callico.process.arkindex.imports.ArkindexFetchExtraInfo.store_entity_types")

    fetch_process = ArkindexFetchExtraInfo(process, project.provider.id, str(project.id))

    fetch_process.run()
    assert mock_create_classes.call_count == 1
    assert mock_create_types.call_count == 1
    assert mock_store_worker_runs.call_count == 1
    assert mock_store_entity_types.call_count == 1
