import uuid

import pytest

from callico.annotations.models import TaskState
from callico.process.arkindex.tasks import arkindex_export, arkindex_fetch_extra_info, arkindex_import

pytestmark = pytest.mark.django_db


def test_arkindex_fetch_extra_info(mocker, mock_arkindex_client, project, process_with_celery_mock):
    mock_run = mocker.patch("callico.process.arkindex.imports.ArkindexFetchExtraInfo.run")
    config = {
        "arkindex_provider": str(project.provider.id),
        "project_id": str(project.id),
    }

    arkindex_fetch_extra_info(**config)

    assert mock_run.call_count == 1
    assert mock_run.call_args == ()


def test_arkindex_import(mocker, mock_arkindex_client, project, process_with_celery_mock):
    mock_run = mocker.patch("callico.process.arkindex.imports.ArkindexImport.run")
    config = {
        "arkindex_provider": str(project.provider.id),
        "project_id": str(project.id),
        "types": [],
        "class_name": None,
        "elements_worker_run": {},
        "metadata": [],
        "transcriptions": [],
        "entities": [],
        "corpus": str(uuid.uuid4()),
        "element": None,
        "dataset": None,
        "dataset_sets": [],
    }

    arkindex_import(**config)

    assert mock_run.call_count == 1
    assert mock_run.call_args == (
        (),
        {"element_id": config["element"], "dataset_id": config["dataset"], "corpus_id": config["corpus"]},
    )


def test_arkindex_export(mocker, mock_arkindex_client, managed_campaign, arkindex_provider, process_with_celery_mock):
    mock_run = mocker.patch("callico.process.arkindex.exports.ArkindexExport.run")
    config = {
        "arkindex_provider": str(arkindex_provider.id),
        "campaign": str(managed_campaign.id),
        "corpus": str(managed_campaign.project.provider_object_id),
        "worker_run": str(uuid.uuid4()),
        "exported_states": [TaskState.Annotated, TaskState.Validated],
    }

    arkindex_export(**config)
    assert mock_run.call_count == 1
    assert mock_run.call_args == (())
