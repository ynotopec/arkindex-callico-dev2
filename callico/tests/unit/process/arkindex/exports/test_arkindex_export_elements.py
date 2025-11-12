import logging

import pytest

from callico.annotations.models import Annotation, TaskState, TaskUser
from callico.process.arkindex.exports import ArkindexExport
from callico.projects.models import CampaignMode, Role

pytestmark = pytest.mark.django_db

WORKER_RUN_ID = "12341234-1234-1234-1234-123412341234"


@pytest.fixture()
def managed_elements_campaign(mock_arkindex_client, managed_campaign, new_contributor):
    managed_campaign.project.memberships.create(user=new_contributor, role=Role.Contributor)

    project = managed_campaign.project
    line = project.types.get(name="Line")
    word = project.types.create(name="Word", provider=project.provider, provider_object_id="word")
    mock_arkindex_client.add_response(
        "RetrieveCorpus",
        {
            "types": [
                {"slug": line.provider_object_id},
                {"slug": word.provider_object_id},
            ]
        },
        id=project.provider_object_id,
    )
    managed_campaign.mode = CampaignMode.Elements
    managed_campaign.save()

    return managed_campaign


@pytest.fixture()
def base_config(arkindex_provider, managed_elements_campaign, use_raw_publication):
    return {
        "arkindex_provider": str(arkindex_provider.id),
        "campaign": str(managed_elements_campaign.id),
        "worker_run": str(WORKER_RUN_ID),
        "corpus": managed_elements_campaign.project.provider_object_id,
        "exported_states": [TaskState.Annotated, TaskState.Validated],
        "use_raw_publication": use_raw_publication,
    }


@pytest.mark.parametrize("annotation_value", [{"no_elements": "oops"}, {"elements": None}, {"elements": "not a list"}])
@pytest.mark.parametrize("use_raw_publication", [True, False])
def test_export_elements_annotations_annotation_value_error(
    caplog,
    managed_elements_campaign,
    contributor,
    annotation_value,
    use_raw_publication,
    process,
    base_config,
):
    project = managed_elements_campaign.project
    task = managed_elements_campaign.tasks.create(element=project.elements.filter(image__isnull=False).first())
    user_task = task.user_tasks.create(user=contributor.user, state=TaskState.Validated)
    annotation = Annotation.objects.create(user_task=user_task, value=annotation_value)

    export_process = ArkindexExport.from_configuration(process, base_config)
    export_process.run()

    annotation.refresh_from_db()
    assert not annotation.published
    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == [
            (logging.INFO, 'Using campaign "Campaign"'),
            (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
            (
                logging.ERROR,
                f"Skipping the task {task.id} as at least one of its last element annotations holds an invalid value",
            ),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


@pytest.mark.parametrize("use_raw_publication", [True, False])
def test_export_elements_annotations_api_createelements_error(
    caplog,
    mock_arkindex_client,
    managed_elements_campaign,
    contributor,
    use_raw_publication,
    process,
    base_config,
):
    project = managed_elements_campaign.project
    task = managed_elements_campaign.tasks.create(element=project.elements.filter(image__isnull=False).first())
    user_task = task.user_tasks.create(user=contributor.user, state=TaskState.Validated)
    annotation = Annotation.objects.create(
        user_task=user_task,
        value={
            "elements": [{"element_type": str(project.types.get(name="Line").id), "polygon": [[1, 1], [2, 2], [3, 3]]}]
        },
    )

    mock_arkindex_client.add_error_response(
        "CreateElements",
        status_code=400,
        body={
            "worker_run_id": WORKER_RUN_ID,
            "elements": [{"name": "1", "type": "line", "polygon": [[1, 1], [2, 2], [3, 3]], "confidence": 1}],
        },
        id=task.element.provider_object_id,
    )

    export_process = ArkindexExport.from_configuration(process, base_config)
    export_process.run()

    annotation.refresh_from_db()
    assert not annotation.published
    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == [
            (logging.INFO, 'Using campaign "Campaign"'),
            (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
            (
                logging.ERROR,
                f"Failed to publish elements retrieved from the annotations on the task {task.id}: 400 - Mock error response",
            ),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


@pytest.mark.parametrize("use_raw_publication", [True, False])
def test_export_elements_annotations_skip_not_allowed_element_type(
    caplog,
    managed_elements_campaign,
    contributor,
    use_raw_publication,
    process,
    base_config,
):
    project = managed_elements_campaign.project
    task = managed_elements_campaign.tasks.create(element=project.elements.filter(image__isnull=False).first())
    user_task = task.user_tasks.create(user=contributor.user, state=TaskState.Validated)
    folder = project.types.get(name="Folder")
    annotation = Annotation.objects.create(
        user_task=user_task, value={"elements": [{"element_type": str(folder.id), "polygon": [[1, 1], [2, 2], [3, 3]]}]}
    )

    export_process = ArkindexExport.from_configuration(process, base_config)
    export_process.run()

    annotation.refresh_from_db()
    # When we skip an annotation, the publication is still considered as successful and published attribute is updated
    assert annotation.published
    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == [
            (logging.INFO, 'Using campaign "Campaign"'),
            (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
            (
                logging.INFO,
                f"Skipped 1 element annotations for task {task.id} because no type matches them in the Arkindex corpus",
            ),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


@pytest.mark.parametrize("use_raw_publication", [True, False])
def test_export_elements_annotations_nothing_annotated(
    caplog,
    managed_elements_campaign,
    contributor,
    use_raw_publication,
    process,
    base_config,
):
    project = managed_elements_campaign.project
    task = managed_elements_campaign.tasks.create(element=project.elements.filter(image__isnull=False).first())
    user_task = task.user_tasks.create(user=contributor.user, state=TaskState.Validated)
    annotation = Annotation.objects.create(user_task=user_task, value={"elements": []})

    export_process = ArkindexExport.from_configuration(process, base_config)
    export_process.run()

    annotation.refresh_from_db()
    # When an annotation is empty, the publication is still considered as successful and published attribute is updated
    assert annotation.published
    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == [
            (logging.INFO, 'Using campaign "Campaign"'),
            (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


@pytest.mark.parametrize("use_raw_publication", [True, False])
def test_export_elements_annotations_with_parent_annotation(
    caplog,
    mock_arkindex_client,
    managed_elements_campaign,
    contributor,
    use_raw_publication,
    process,
    base_config,
):
    project = managed_elements_campaign.project
    task = managed_elements_campaign.tasks.create(element=project.elements.filter(image__isnull=False).first())
    user_task = task.user_tasks.create(user=contributor.user, state=TaskState.Validated)
    folder = project.types.get(name="Folder")
    parent_annotation = Annotation.objects.create(
        user_task=user_task,
        value={"elements": [{"element_type": str(folder.id), "polygon": [[1, 1], [2, 2], [3, 3]]}]},
        published=True,
    )
    annotation = Annotation.objects.create(
        parent=parent_annotation,
        user_task=user_task,
        value={
            "elements": [{"element_type": str(project.types.get(name="Line").id), "polygon": [[1, 1], [2, 2], [3, 3]]}]
        },
    )

    mock_arkindex_client.add_response(
        "CreateElements",
        {"elements": []},
        body={
            "worker_run_id": WORKER_RUN_ID,
            "elements": [{"name": "1", "type": "line", "polygon": [[1, 1], [2, 2], [3, 3]], "confidence": 1}],
        },
        id=task.element.provider_object_id,
    )

    export_process = ArkindexExport.from_configuration(process, base_config)
    export_process.run()

    annotation.refresh_from_db()
    assert annotation.published
    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == [
            (logging.INFO, 'Using campaign "Campaign"'),
            (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
            (logging.INFO, f"Successfully published 1 elements with their confidence for task {task.id}"),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


@pytest.mark.parametrize("use_raw_publication", [True, False])
def test_export_elements_annotations_multiple_same_annotations(
    caplog,
    mock_arkindex_client,
    managed_elements_campaign,
    contributor,
    new_contributor,
    use_raw_publication,
    process,
    base_config,
):
    project = managed_elements_campaign.project
    task = managed_elements_campaign.tasks.create(element=project.elements.filter(image__isnull=False).first())
    user_tasks = TaskUser.objects.bulk_create(
        [TaskUser(task=task, user=user, state=TaskState.Pending) for user in [contributor.user, new_contributor]]
    )
    for user_task in user_tasks:
        Annotation.objects.create(
            user_task=user_task,
            value={
                "elements": [
                    {"element_type": str(project.types.get(name="Line").id), "polygon": [[1, 1], [2, 2], [3, 3]]}
                ]
            },
        )
        user_task.state = TaskState.Annotated
        user_task.save()

    nb_publications = 1 if not use_raw_publication else len(user_tasks)
    mock_arkindex_client.add_response(
        "CreateElements",
        {"elements": []},
        body={
            "worker_run_id": WORKER_RUN_ID,
            "elements": [
                {"name": str(i + 1), "type": "line", "polygon": [[1, 1], [2, 2], [3, 3]], "confidence": 1}
                for i in range(nb_publications)
            ],
        },
        id=task.element.provider_object_id,
    )

    export_process = ArkindexExport.from_configuration(process, base_config)
    export_process.run()

    assert all(annotation.published for annotation in Annotation.objects.all())
    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == [
            (logging.INFO, 'Using campaign "Campaign"'),
            (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
            (
                logging.INFO,
                f"Successfully published {nb_publications} elements with their confidence for task {task.id}",
            ),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


@pytest.mark.parametrize("use_raw_publication", [True, False])
def test_export_elements_annotations_multiple_differing_annotations(
    caplog,
    mock_arkindex_client,
    managed_elements_campaign,
    contributor,
    new_contributor,
    use_raw_publication,
    process,
    base_config,
):
    project = managed_elements_campaign.project
    task = managed_elements_campaign.tasks.create(element=project.elements.filter(image__isnull=False).first())
    TaskUser.objects.bulk_create(
        [TaskUser(task=task, user=user, state=TaskState.Pending) for user in [contributor.user, new_contributor]]
    )
    element_types = list(project.types.filter(name__in=["Line", "Word"]).order_by("name").values_list("id", flat=True))
    for index, user_task in enumerate(task.user_tasks.all().order_by("-created", "id")):
        Annotation.objects.create(
            user_task=user_task,
            value={"elements": [{"element_type": str(element_types[index]), "polygon": [[1, 1], [2, 2], [3, 3]]}]},
        )
        user_task.state = TaskState.Annotated
        user_task.save()

    confidence = 0.5 if not use_raw_publication else 1
    mock_arkindex_client.add_response(
        "CreateElements",
        {"elements": []},
        body={
            "worker_run_id": WORKER_RUN_ID,
            "elements": [
                {"name": "1", "type": "line", "polygon": [[1, 1], [2, 2], [3, 3]], "confidence": confidence},
                {"name": "1", "type": "word", "polygon": [[1, 1], [2, 2], [3, 3]], "confidence": confidence},
            ],
        },
        id=task.element.provider_object_id,
    )

    export_process = ArkindexExport.from_configuration(process, base_config)
    export_process.run()

    assert all(annotation.published for annotation in Annotation.objects.all())
    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == [
            (logging.INFO, 'Using campaign "Campaign"'),
            (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
            (logging.INFO, f"Successfully published 2 elements with their confidence for task {task.id}"),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


@pytest.mark.parametrize("state", [TaskState.Annotated, TaskState.Validated])
@pytest.mark.parametrize("use_raw_publication", [True, False])
def test_export_elements_annotations_single_annotation(
    caplog,
    mock_arkindex_client,
    managed_elements_campaign,
    contributor,
    state,
    use_raw_publication,
    process,
    base_config,
):
    project = managed_elements_campaign.project

    task = managed_elements_campaign.tasks.create(element=project.elements.filter(image__isnull=False).first())
    user_task = task.user_tasks.create(user=contributor.user, state=state)
    annotation = Annotation.objects.create(
        user_task=user_task,
        value={
            "elements": [{"element_type": str(project.types.get(name="Line").id), "polygon": [[1, 1], [2, 2], [3, 3]]}]
        },
    )

    mock_arkindex_client.add_response(
        "CreateElements",
        {"elements": []},
        body={
            "worker_run_id": WORKER_RUN_ID,
            "elements": [{"name": "1", "type": "line", "polygon": [[1, 1], [2, 2], [3, 3]], "confidence": 1}],
        },
        id=task.element.provider_object_id,
    )

    export_process = ArkindexExport.from_configuration(process, base_config)
    export_process.run()

    annotation.refresh_from_db()
    assert annotation.published
    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == [
            (logging.INFO, 'Using campaign "Campaign"'),
            (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
            (logging.INFO, f"Successfully published 1 elements with their confidence for task {task.id}"),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )
