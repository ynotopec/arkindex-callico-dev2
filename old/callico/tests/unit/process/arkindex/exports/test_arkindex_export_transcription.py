import logging
import uuid

import pytest

from callico.annotations.models import Annotation, TaskState, TaskUser
from callico.process.arkindex.exports import EMPTY_SET_CHARACTER, ArkindexExport
from callico.projects.models import Element, Provider, ProviderType

pytestmark = pytest.mark.django_db

WORKER_RUN_ID = "12341234-1234-1234-1234-123412341234"


@pytest.fixture()
def base_config(arkindex_provider, managed_campaign, use_raw_publication):
    return {
        "arkindex_provider": str(arkindex_provider.id),
        "campaign": str(managed_campaign.id),
        "worker_run": str(WORKER_RUN_ID),
        "corpus": managed_campaign.project.provider_object_id,
        "exported_states": [TaskState.Annotated, TaskState.Validated],
        "use_raw_publication": use_raw_publication,
    }


@pytest.mark.parametrize(
    "annotation_value", [{"no_transcription": "oops"}, {"transcription": {}}, {"transcription": "not a dict"}]
)
@pytest.mark.parametrize("use_raw_publication", [True, False])
def test_export_transcription_annotations_annotation_value_error(
    caplog,
    mock_arkindex_client,
    managed_campaign,
    contributor,
    annotation_value,
    use_raw_publication,
    process,
    base_config,
):
    task = managed_campaign.tasks.create(element=managed_campaign.project.elements.filter(image__isnull=False).first())
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
                f"Skipping the task {task.id} as at least one of its last transcription annotations holds an invalid value",
            ),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


@pytest.mark.parametrize("use_raw_publication", [True, False])
def test_export_transcription_annotations_api_createtranscriptions_error(
    caplog,
    mock_arkindex_client,
    managed_campaign,
    contributor,
    use_raw_publication,
    process,
    base_config,
):
    element = managed_campaign.project.elements.filter(image__isnull=False).first()
    task = managed_campaign.tasks.create(element=element)
    user_task = task.user_tasks.create(user=contributor.user, state=TaskState.Validated)
    annotation = Annotation.objects.create(
        user_task=user_task,
        value={"transcription": {str(element.id): {"text": f"An annotation for the element {element.id}"}}},
    )

    mock_arkindex_client.add_error_response(
        "CreateTranscriptions",
        status_code=400,
        body={
            "worker_run_id": WORKER_RUN_ID,
            "transcriptions": [
                {
                    "element_id": element.provider_object_id,
                    "text": f"An annotation for the element {element.id}",
                    "confidence": 1,
                    "orientation": "horizontal-lr",
                }
            ],
        },
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
                f"Failed to publish 1 transcriptions retrieved from the annotations on the task {task.id}: 400 - Mock error response",
            ),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


@pytest.mark.parametrize("use_raw_publication", [True, False])
def test_export_transcription_annotations_skip_empty_transcription(
    caplog,
    mock_arkindex_client,
    managed_campaign,
    contributor,
    use_raw_publication,
    process,
    base_config,
):
    element = managed_campaign.project.elements.filter(image__isnull=False).first()
    task = managed_campaign.tasks.create(element=element)
    user_task = task.user_tasks.create(user=contributor.user, state=TaskState.Validated)
    annotation = Annotation.objects.create(
        user_task=user_task,
        value={"transcription": {str(element.id): {"text": ""}}},
    )

    mock_arkindex_client.add_response(
        "CreateTranscriptions",
        {"transcriptions": []},
        body={
            "worker_run_id": WORKER_RUN_ID,
            "transcriptions": [
                {
                    "element_id": element.provider_object_id,
                    "text": EMPTY_SET_CHARACTER,
                    "confidence": 1,
                    "orientation": "horizontal-lr",
                }
            ],
        },
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
                logging.WARNING,
                f"The transcription for the element {element.id} on annotation {annotation.id} is empty, publishing ∅ instead",
            ),
            (
                logging.INFO,
                f"Successfully published 1 transcriptions with their confidence for task {task.id}",
            ),
            (logging.INFO, f"Replaced 1 empty transcriptions on the task {task.id} by ∅"),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


@pytest.mark.parametrize("use_raw_publication", [True, False])
def test_export_transcription_annotations_skip_element_from_another_provider(
    caplog,
    mock_arkindex_client,
    managed_campaign,
    contributor,
    use_raw_publication,
    process,
    base_config,
):
    element = managed_campaign.project.elements.filter(image__isnull=False).first()
    element.provider = Provider.objects.create(
        name="Another provider",
        type=ProviderType.Arkindex,
        api_url="https://foreign.arkindex.com/api/v1",
        api_token="987654321",
    )
    element.save()
    arkindex_provider = element.project.provider
    assert element.provider != arkindex_provider
    task = managed_campaign.tasks.create(element=element)
    user_task = task.user_tasks.create(user=contributor.user, state=TaskState.Validated)
    annotation = Annotation.objects.create(
        user_task=user_task,
        value={"transcription": {str(element.id): {"text": f"An annotation for the element {element.id}"}}},
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
                logging.WARNING,
                f'Skipping the transcription for the element {element.id} on annotation {annotation.id} as it is not an element from the Arkindex provider "{arkindex_provider}"',
            ),
            (
                logging.INFO,
                f"Skipped 1 transcriptions on the task {task.id} that were on elements from another Arkindex provider",
            ),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


@pytest.mark.parametrize("use_raw_publication", [True, False])
def test_export_transcription_annotations_with_children_transcriptions(
    caplog,
    mock_arkindex_client,
    managed_campaign,
    contributor,
    use_raw_publication,
    process,
    base_config,
):
    element = managed_campaign.project.elements.filter(image__isnull=False).first()
    children = Element.objects.bulk_create(
        Element(
            name=f"Line {i}",
            type=element.project.types.get(name="Line"),
            parent=element,
            project=element.project,
            provider=element.project.provider,
            provider_object_id=str(uuid.uuid4()),
            image=element.image,
            polygon=[[1, 2], [2, 3], [3, 4]],
            order=i - 1,
        )
        for i in range(1, 8)
    )
    # Elements are ordered by creation date by default in the publication script
    all_elements = [element, *children]
    task = managed_campaign.tasks.create(element=element)
    user_task = task.user_tasks.create(user=contributor.user, state=TaskState.Validated)
    annotation = Annotation.objects.create(
        user_task=user_task,
        value={
            "transcription": {
                str(elem.id): {"text": f"An annotation for the element {elem.id}"} for elem in all_elements
            }
        },
    )

    mock_arkindex_client.add_response(
        "CreateTranscriptions",
        {"transcriptions": []},
        body={
            "worker_run_id": WORKER_RUN_ID,
            "transcriptions": [
                {
                    "element_id": elem.provider_object_id,
                    "text": f"An annotation for the element {elem.id}",
                    "confidence": 1,
                    "orientation": "horizontal-lr",
                }
                for elem in all_elements
            ],
        },
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
            (
                logging.INFO,
                f"Successfully published {len(all_elements)} transcriptions with their confidence for task {task.id}",
            ),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


@pytest.mark.parametrize("use_raw_publication", [True, False])
def test_export_transcription_annotations_with_uncertain_values(
    caplog,
    mock_arkindex_client,
    managed_campaign,
    contributor,
    use_raw_publication,
    process,
    base_config,
):
    element = managed_campaign.project.elements.filter(image__isnull=False).first()
    task = managed_campaign.tasks.create(element=element)
    user_task = task.user_tasks.create(user=contributor.user, state=TaskState.Validated)
    annotation = Annotation.objects.create(
        user_task=user_task,
        value={
            "transcription": {
                str(element.id): {"text": f"Another annotation for the element {element.id}", "uncertain": True}
            }
        },
    )

    mock_arkindex_client.add_response(
        "CreateTranscriptions",
        {"transcriptions": []},
        body={
            "worker_run_id": WORKER_RUN_ID,
            "transcriptions": [
                {
                    "element_id": element.provider_object_id,
                    "text": f"Another annotation for the element {element.id}",
                    "confidence": 0.5,  # Low confidence since the value was marked as uncertain
                    "orientation": "horizontal-lr",
                }
            ],
        },
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
            (logging.INFO, f"Successfully published 1 transcriptions with their confidence for task {task.id}"),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


@pytest.mark.parametrize("use_raw_publication", [True, False])
def test_export_transcription_annotations_with_parent_annotation(
    caplog,
    mock_arkindex_client,
    managed_campaign,
    contributor,
    use_raw_publication,
    process,
    base_config,
):
    element = managed_campaign.project.elements.filter(image__isnull=False).first()
    task = managed_campaign.tasks.create(element=element)
    user_task = task.user_tasks.create(user=contributor.user, state=TaskState.Validated)
    parent_annotation = Annotation.objects.create(
        user_task=user_task,
        value={"transcription": {str(element.id): {"text": f"An annotation for the element {element.id}"}}},
        published=True,
    )
    annotation = Annotation.objects.create(
        parent=parent_annotation,
        user_task=user_task,
        value={"transcription": {str(element.id): {"text": f"Another annotation for the element {element.id}"}}},
    )

    mock_arkindex_client.add_response(
        "CreateTranscriptions",
        {"transcriptions": []},
        body={
            "worker_run_id": WORKER_RUN_ID,
            "transcriptions": [
                {
                    "element_id": element.provider_object_id,
                    "text": f"Another annotation for the element {element.id}",
                    "confidence": 1,
                    "orientation": "horizontal-lr",
                }
            ],
        },
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
            (logging.INFO, f"Successfully published 1 transcriptions with their confidence for task {task.id}"),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


@pytest.mark.parametrize("use_raw_publication", [True, False])
def test_export_transcription_annotations_multiple_same_annotations(
    caplog,
    mock_arkindex_client,
    managed_campaign,
    contributor,
    new_contributor,
    use_raw_publication,
    process,
    base_config,
):
    element = managed_campaign.project.elements.filter(image__isnull=False).first()
    task = managed_campaign.tasks.create(element=element)
    user_tasks = TaskUser.objects.bulk_create(
        [TaskUser(task=task, user=user, state=TaskState.Pending) for user in [contributor.user, new_contributor]]
    )
    for user_task in user_tasks:
        Annotation.objects.create(
            user_task=user_task,
            value={"transcription": {str(element.id): {"text": f"An annotation for the element {element.id}"}}},
        )
        user_task.state = TaskState.Annotated
        user_task.save()

    nb_publications = 1 if not use_raw_publication else len(user_tasks)
    mock_arkindex_client.add_response(
        "CreateTranscriptions",
        {"transcriptions": []},
        body={
            "worker_run_id": WORKER_RUN_ID,
            "transcriptions": [
                {
                    "element_id": element.provider_object_id,
                    "text": f"An annotation for the element {element.id}",
                    "confidence": 1,
                    "orientation": "horizontal-lr",
                }
            ]
            * nb_publications,
        },
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
                f"Successfully published {nb_publications} transcriptions with their confidence for task {task.id}",
            ),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


@pytest.mark.parametrize("use_raw_publication", [True, False])
def test_export_transcription_annotations_multiple_differing_annotations(
    caplog,
    mock_arkindex_client,
    managed_campaign,
    contributor,
    new_contributor,
    use_raw_publication,
    process,
    base_config,
):
    element = managed_campaign.project.elements.filter(image__isnull=False).first()
    task = managed_campaign.tasks.create(element=element)
    TaskUser.objects.bulk_create(
        [TaskUser(task=task, user=user, state=TaskState.Pending) for user in [contributor.user, new_contributor]]
    )
    transcriptions = [f"An annotation for the element {element.id}", f"Another annotation for the element {element.id}"]
    for index, user_task in enumerate(task.user_tasks.all().order_by("-created", "id")):
        Annotation.objects.create(
            user_task=user_task,
            value={"transcription": {str(element.id): {"text": transcriptions[index]}}},
        )
        user_task.state = TaskState.Annotated
        user_task.save()

    confidence = 0.5 if not use_raw_publication else 1
    mock_arkindex_client.add_response(
        "CreateTranscriptions",
        {"transcriptions": []},
        body={
            "worker_run_id": WORKER_RUN_ID,
            "transcriptions": [
                {
                    "element_id": element.provider_object_id,
                    "text": f"An annotation for the element {element.id}",
                    "confidence": confidence,
                    "orientation": "horizontal-lr",
                },
                {
                    "element_id": element.provider_object_id,
                    "text": f"Another annotation for the element {element.id}",
                    "confidence": confidence,
                    "orientation": "horizontal-lr",
                },
            ],
        },
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
                logging.WARNING,
                f"Differing transcriptions for the element {element.id} were found on the task {task.id}",
            ),
            (logging.INFO, f"Successfully published 2 transcriptions with their confidence for task {task.id}"),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


@pytest.mark.parametrize("state", [TaskState.Annotated, TaskState.Validated])
@pytest.mark.parametrize("use_raw_publication", [True, False])
def test_export_transcription_annotations_single_annotation(
    caplog,
    mock_arkindex_client,
    managed_campaign,
    contributor,
    state,
    use_raw_publication,
    process,
    base_config,
):
    project = managed_campaign.project

    element = project.elements.filter(image__isnull=False).first()
    task = managed_campaign.tasks.create(element=element)
    user_task = task.user_tasks.create(user=contributor.user, state=state)
    annotation = Annotation.objects.create(
        user_task=user_task,
        value={"transcription": {str(element.id): {"text": f"An annotation for the element {element.id}"}}},
    )

    mock_arkindex_client.add_response(
        "CreateTranscriptions",
        {"transcriptions": []},
        body={
            "worker_run_id": WORKER_RUN_ID,
            "transcriptions": [
                {
                    "element_id": element.provider_object_id,
                    "text": f"An annotation for the element {element.id}",
                    "confidence": 1,
                    "orientation": "horizontal-lr",
                }
            ],
        },
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
            (logging.INFO, f"Successfully published 1 transcriptions with their confidence for task {task.id}"),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )
