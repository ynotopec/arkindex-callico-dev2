import logging
import random
import uuid

import pytest

from callico.annotations.models import Annotation, TaskState, TaskUser
from callico.process.arkindex.exports import ArkindexExport
from callico.projects.models import CampaignMode, Role

pytestmark = pytest.mark.django_db

WORKER_RUN_ID = "12341234-1234-1234-1234-123412341234"


@pytest.fixture()
def managed_entity_form_campaign(managed_campaign, new_contributor, mock_arkindex_client):
    managed_campaign.project.memberships.create(user=new_contributor, role=Role.Contributor)
    managed_campaign.mode = CampaignMode.EntityForm
    managed_campaign.save()
    managed_campaign.refresh_from_db()
    mock_arkindex_client.add_response(
        "ListCorpusEntityTypes",
        id=managed_campaign.project.provider_object_id,
        response=[
            {"name": "city", "color": "ffffff", "id": "type1id"},
            {"name": "first_name", "color": "000000", "id": "type2id"},
            {"name": "last_name", "color": "ffffff", "id": "type3id"},
            {"name": "date", "color": "ffffff", "id": "type4id"},
        ],
    )
    return managed_campaign


@pytest.fixture()
def base_config(arkindex_provider, managed_entity_form_campaign, use_raw_publication):
    return {
        "arkindex_provider": str(arkindex_provider.id),
        "campaign": str(managed_entity_form_campaign.id),
        "worker_run": str(WORKER_RUN_ID),
        "corpus": managed_entity_form_campaign.project.provider_object_id,
        "exported_states": [TaskState.Annotated, TaskState.Validated],
        "use_raw_publication": use_raw_publication,
        "entities_order": [
            ["first_name", "First name"],
            ["last_name", "Last name"],
            ["city", "City"],
            ["date", "Date"],
        ],
    }


@pytest.mark.parametrize("annotation_value", [{"no_values": "oops"}, {"values": []}, {"values": "not a list"}])
@pytest.mark.parametrize("use_raw_publication", [True, False])
def test_export_entity_form_annotations_annotation_value_error(
    caplog,
    managed_entity_form_campaign,
    contributor,
    annotation_value,
    use_raw_publication,
    process,
    base_config,
):
    task = managed_entity_form_campaign.tasks.create(
        element=managed_entity_form_campaign.project.elements.filter(image__isnull=False).first()
    )
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
                f"Skipping the task {task.id} as at least one of its last entity form annotations holds an invalid value",
            ),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


@pytest.mark.parametrize("use_raw_publication", [True, False])
def test_export_entity_form_annotations_api_createtranscription_error(
    caplog,
    mock_arkindex_client,
    managed_entity_form_campaign,
    contributor,
    use_raw_publication,
    process,
    base_config,
):
    element = managed_entity_form_campaign.project.elements.filter(image__isnull=False).first()
    task = managed_entity_form_campaign.tasks.create(element=element)
    user_task = task.user_tasks.create(user=contributor.user, state=TaskState.Validated)
    annotation = Annotation.objects.create(
        user_task=user_task,
        value={
            "values": [
                {
                    "value": "Harry",
                    "entity_type": "first_name",
                    "instruction": "First name",
                },
                {
                    "value": "Potter",
                    "entity_type": "last_name",
                    "instruction": "Last name",
                },
                {
                    "value": "Little Whinging",
                    "entity_type": "city",
                    "instruction": "City",
                },
            ]
        },
    )

    mock_arkindex_client.add_error_response(
        "CreateTranscription",
        status_code=400,
        body={"text": "Harry Potter Little Whinging", "worker_run_id": WORKER_RUN_ID, "confidence": 1},
        id=element.provider_object_id,
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
                f"Failed to publish the transcription forged with 3 valid entities from the annotations on the task {task.id}: 400 - Mock error response",
            ),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


@pytest.mark.parametrize("use_raw_publication", [True, False])
def test_export_entity_form_annotations_api_createtranscription_error_all_entities_empty(
    caplog,
    mock_arkindex_client,
    managed_entity_form_campaign,
    contributor,
    use_raw_publication,
    process,
    base_config,
):
    element = managed_entity_form_campaign.project.elements.filter(image__isnull=False).first()
    task = managed_entity_form_campaign.tasks.create(element=element)
    user_task = task.user_tasks.create(user=contributor.user, state=TaskState.Validated)
    annotation = Annotation.objects.create(
        user_task=user_task,
        value={
            "values": [
                {
                    "value": "",
                    "entity_type": "first_name",
                    "instruction": "First name",
                },
                {
                    "value": "",
                    "entity_type": "last_name",
                    "instruction": "Last name",
                },
                {
                    "value": "",
                    "entity_type": "city",
                    "instruction": "City",
                },
            ]
        },
    )

    mock_arkindex_client.add_error_response(
        "CreateTranscription",
        status_code=400,
        body={"text": "∅", "worker_run_id": WORKER_RUN_ID, "confidence": 1},
        id=element.provider_object_id,
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
                logging.WARNING,
                f"All 3 entities from the annotations on the task {task.id} are empty, publishing a ∅ transcription in replacement",
            ),
            (
                logging.ERROR,
                f"Failed to publish the empty transcription using the ∅ character from the annotations on the task {task.id}: 400 - Mock error response",
            ),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


@pytest.mark.parametrize("use_raw_publication", [True, False])
def test_export_entity_form_annotations_all_entities_empty(
    caplog,
    mock_arkindex_client,
    managed_entity_form_campaign,
    contributor,
    use_raw_publication,
    process,
    base_config,
):
    element = managed_entity_form_campaign.project.elements.filter(image__isnull=False).first()
    task = managed_entity_form_campaign.tasks.create(element=element)
    user_task = task.user_tasks.create(user=contributor.user, state=TaskState.Validated)
    annotation = Annotation.objects.create(
        user_task=user_task,
        value={
            "values": [
                {
                    "value": "",
                    "entity_type": "first_name",
                    "instruction": "First name",
                },
                {
                    "value": "",
                    "entity_type": "last_name",
                    "instruction": "Last name",
                },
                {
                    "value": "",
                    "entity_type": "city",
                    "instruction": "City",
                },
            ]
        },
    )

    mock_arkindex_client.add_response(
        "CreateTranscription",
        {"id": str(uuid.uuid4())},
        body={"text": "∅", "worker_run_id": WORKER_RUN_ID, "confidence": 1},
        id=element.provider_object_id,
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
                logging.WARNING,
                f"All 3 entities from the annotations on the task {task.id} are empty, publishing a ∅ transcription in replacement",
            ),
            (
                logging.INFO,
                f"Successfully published the empty transcription using the ∅ character from the annotations on the task {task.id}",
            ),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


@pytest.mark.parametrize("use_raw_publication", [True, False])
def test_export_entity_form_annotations_new_entity_type_error(
    caplog,
    mock_arkindex_client,
    managed_entity_form_campaign,
    contributor,
    use_raw_publication,
    process,
    base_config,
):
    corpus_id = managed_entity_form_campaign.project.provider_object_id
    random.seed(2)
    element = managed_entity_form_campaign.project.elements.filter(image__isnull=False).first()
    task = managed_entity_form_campaign.tasks.create(element=element)
    user_task = task.user_tasks.create(user=contributor.user, state=TaskState.Validated)
    entities = [
        {
            "value": "Harry",
            "entity_type": "first_name",
            "instruction": "First name",
            "type_id": "type2id",  # For debug only
            "offset": 0,  # For debug only
        },
        {
            "value": "Potter",
            "entity_type": "last_name",
            "instruction": "Last name",
            "type_id": "type3id",  # For debug only
            "offset": 6,  # For debug only
        },
        {
            "value": "Little Whinging",
            "entity_type": "new type",
            "instruction": "New type",
            "type_id": "newtypeid",  # For debug only
            "offset": 13,  # For debug only
        },
    ]
    annotation = Annotation.objects.create(
        user_task=user_task,
        value={"values": entities},
    )

    ark_transcription_id = str(uuid.uuid4())
    mock_arkindex_client.add_response(
        "CreateTranscription",
        {"id": ark_transcription_id},
        body={"text": "Harry Potter Little Whinging", "worker_run_id": WORKER_RUN_ID, "confidence": 1},
        id=element.provider_object_id,
    )

    mock_arkindex_client.add_error_response(
        "CreateEntityType", status_code=400, body={"name": "new type", "corpus": corpus_id, "color": "1cf44d"}
    )

    mock_arkindex_client.add_response(
        "CreateTranscriptionEntities",
        {"entities": []},
        id=ark_transcription_id,
        body={
            "worker_run_id": WORKER_RUN_ID,
            "transcription_entities": [
                {
                    "offset": entity["offset"],
                    "length": len(entity["value"]),
                    "type_id": entity["type_id"],
                    "confidence": 1,
                }
                for entity in entities[:2]
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
                logging.INFO,
                f"Successfully published the transcription forged with 3 valid entities from the annotations on the task {task.id}",
            ),
            (
                logging.ERROR,
                f"Failed to publish entity Little Whinging of type new type from the annotations on the task {task.id}; an error occurred while creating the entity type new type in the corpus {corpus_id}: 400 - Mock error response",
            ),
            (
                logging.INFO,
                f"Successfully published and linked 2 entities with the transcription from the annotations on the task {task.id}",
            ),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


@pytest.mark.parametrize("use_raw_publication", [True, False])
def test_export_entity_form_annotations_new_entity_type(
    caplog,
    mock_arkindex_client,
    managed_entity_form_campaign,
    contributor,
    use_raw_publication,
    process,
    base_config,
):
    corpus_id = managed_entity_form_campaign.project.provider_object_id
    random.seed(0)
    element = managed_entity_form_campaign.project.elements.filter(image__isnull=False).first()
    task = managed_entity_form_campaign.tasks.create(element=element)
    user_task = task.user_tasks.create(user=contributor.user, state=TaskState.Validated)
    entities = [
        {
            "value": "Harry",
            "entity_type": "first_name",
            "instruction": "First name",
            "type_id": "type2id",  # For debug only
            "offset": 0,  # For debug only
        },
        {
            "value": "Potter",
            "entity_type": "last_name",
            "instruction": "Last name",
            "type_id": "type3id",  # For debug only
            "offset": 6,  # For debug only
        },
        {
            "value": "Little Whinging",
            "entity_type": "new type",
            "instruction": "New type",
            "type_id": "newtypeid",  # For debug only
            "offset": 13,  # For debug only
        },
    ]
    annotation = Annotation.objects.create(
        user_task=user_task,
        value={"values": entities},
    )

    ark_transcription_id = str(uuid.uuid4())
    mock_arkindex_client.add_response(
        "CreateTranscription",
        {"id": ark_transcription_id},
        body={"text": "Harry Potter Little Whinging", "worker_run_id": WORKER_RUN_ID, "confidence": 1},
        id=element.provider_object_id,
    )

    mock_arkindex_client.add_response(
        "CreateEntityType",
        body={"name": "new type", "corpus": corpus_id, "color": "c53edf"},
        response={"name": "new type", "id": "newtypeid"},
    )

    mock_arkindex_client.add_response(
        "CreateTranscriptionEntities",
        {"entities": []},
        id=ark_transcription_id,
        body={
            "worker_run_id": WORKER_RUN_ID,
            "transcription_entities": [
                {
                    "offset": entity["offset"],
                    "length": len(entity["value"]),
                    "type_id": entity["type_id"],
                    "confidence": 1,
                }
                for entity in entities
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
                f"Successfully published the transcription forged with 3 valid entities from the annotations on the task {task.id}",
            ),
            (
                logging.INFO,
                f"Successfully published and linked 3 entities with the transcription from the annotations on the task {task.id}",
            ),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


@pytest.mark.parametrize("use_raw_publication", [True, False])
def test_export_entity_form_annotations_api_createtranscriptionentities_error(
    caplog,
    mock_arkindex_client,
    managed_entity_form_campaign,
    contributor,
    use_raw_publication,
    process,
    base_config,
):
    element = managed_entity_form_campaign.project.elements.filter(image__isnull=False).first()
    task = managed_entity_form_campaign.tasks.create(element=element)
    user_task = task.user_tasks.create(user=contributor.user, state=TaskState.Validated)
    entities = [
        {
            "value": "Harry",
            "entity_type": "first_name",
            "instruction": "First name",
            "type_id": "type2id",  # For debug only
            "offset": 0,  # For debug only
        },
        {
            "value": "Potter",
            "entity_type": "last_name",
            "instruction": "Last name",
            "type_id": "type3id",  # For debug only
            "offset": 6,  # For debug only
        },
        {
            "value": "Little Whinging",
            "entity_type": "city",
            "instruction": "City",
            "type_id": "type1id",  # For debug only
            "offset": 13,  # For debug only
        },
    ]
    annotation = Annotation.objects.create(
        user_task=user_task,
        value={"values": entities},
    )

    ark_transcription_id = str(uuid.uuid4())
    mock_arkindex_client.add_response(
        "CreateTranscription",
        {"id": ark_transcription_id},
        body={"text": "Harry Potter Little Whinging", "worker_run_id": WORKER_RUN_ID, "confidence": 1},
        id=element.provider_object_id,
    )

    mock_arkindex_client.add_error_response(
        "CreateTranscriptionEntities",
        status_code=400,
        id=ark_transcription_id,
        body={
            "worker_run_id": WORKER_RUN_ID,
            "transcription_entities": [
                {
                    "offset": entity["offset"],
                    "length": len(entity["value"]),
                    "type_id": entity["type_id"],
                    "confidence": 1,
                }
                for entity in entities
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
                logging.INFO,
                f"Successfully published the transcription forged with 3 valid entities from the annotations on the task {task.id}",
            ),
            (
                logging.ERROR,
                f"Failed to publish and link 3 entities with the transcription from the annotations on the task {task.id}: 400 - Mock error response",
            ),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


@pytest.mark.parametrize("use_raw_publication", [True, False])
def test_export_entity_form_annotations_skip_empty_entity(
    caplog,
    mock_arkindex_client,
    managed_entity_form_campaign,
    contributor,
    use_raw_publication,
    process,
    base_config,
):
    element = managed_entity_form_campaign.project.elements.filter(image__isnull=False).first()
    task = managed_entity_form_campaign.tasks.create(element=element)
    user_task = task.user_tasks.create(user=contributor.user, state=TaskState.Validated)
    entities = [
        {
            "value": "Harry",
            "entity_type": "first_name",
            "instruction": "First name",
            "type_id": "type2id",  # For debug only
            "offset": 0,  # For debug only
        },
        {
            "value": "",
            "entity_type": "last_name",
            "instruction": "Last name",
            "type_id": "type3id",  # For debug only
            "offset": 0,  # For debug only
        },
        {
            "value": "Little Whinging",
            "entity_type": "city",
            "instruction": "City",
            "type_id": "type1id",  # For debug only
            "offset": 6,  # For debug only
        },
    ]
    annotation = Annotation.objects.create(
        user_task=user_task,
        value={"values": entities},
    )

    ark_transcription_id = str(uuid.uuid4())
    mock_arkindex_client.add_response(
        "CreateTranscription",
        {"id": ark_transcription_id},
        body={"text": "Harry Little Whinging", "worker_run_id": WORKER_RUN_ID, "confidence": 1},
        id=element.provider_object_id,
    )

    mock_arkindex_client.add_response(
        "CreateTranscriptionEntities",
        {"entities": []},
        id=ark_transcription_id,
        body={
            "worker_run_id": WORKER_RUN_ID,
            "transcription_entities": [
                {
                    "offset": entity["offset"],
                    "length": len(entity["value"]),
                    "type_id": entity["type_id"],
                    "confidence": 1,
                }
                for entity in entities
                if entity["value"]
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
                f"Successfully published the transcription forged with 2 valid entities from the annotations on the task {task.id}",
            ),
            (
                logging.WARNING,
                f"Skipping the entity of type last_name from the annotations on the task {task.id} as it is empty",
            ),
            (
                logging.INFO,
                f"Successfully published and linked 2 entities with the transcription from the annotations on the task {task.id}",
            ),
            (
                logging.INFO,
                f"Skipped 1 empty entities from the annotations on the task {task.id}",
            ),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


@pytest.mark.parametrize("use_raw_publication", [True, False])
def test_export_entity_form_annotations_with_uncertain_values(
    caplog,
    mock_arkindex_client,
    managed_entity_form_campaign,
    contributor,
    use_raw_publication,
    process,
    base_config,
):
    element = managed_entity_form_campaign.project.elements.filter(image__isnull=False).first()
    task = managed_entity_form_campaign.tasks.create(element=element)
    user_task = task.user_tasks.create(user=contributor.user, state=TaskState.Validated)
    entities = [
        {
            "value": "Garry",
            "uncertain": True,
            "entity_type": "first_name",
            "instruction": "First name",
            "type_id": "type2id",  # For debug only
            "offset": 0,  # For debug only
        },
        {
            "value": "Dotter",
            "uncertain": True,
            "entity_type": "last_name",
            "instruction": "Last name",
            "type_id": "type3id",  # For debug only
            "offset": 6,  # For debug only
        },
        {
            "value": "Title Mhinging",
            "uncertain": True,
            "entity_type": "city",
            "instruction": "City",
            "type_id": "type1id",  # For debug only
            "offset": 13,  # For debug only
        },
    ]
    annotation = Annotation.objects.create(
        user_task=user_task,
        value={"values": entities},
    )

    ark_transcription_id = str(uuid.uuid4())
    mock_arkindex_client.add_response(
        "CreateTranscription",
        {"id": ark_transcription_id},
        body={"text": "Garry Dotter Title Mhinging", "worker_run_id": WORKER_RUN_ID, "confidence": 1},
        id=element.provider_object_id,
    )

    mock_arkindex_client.add_response(
        "CreateTranscriptionEntities",
        {"entities": []},
        id=ark_transcription_id,
        body={
            "worker_run_id": WORKER_RUN_ID,
            "transcription_entities": [
                {
                    "offset": entity["offset"],
                    "length": len(entity["value"]),
                    "type_id": entity["type_id"],
                    "confidence": 0.5,  # Low confidence since the value was marked as uncertain
                }
                for entity in entities
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
                f"Successfully published the transcription forged with 3 valid entities from the annotations on the task {task.id}",
            ),
            (
                logging.INFO,
                f"Successfully published and linked 3 entities with the transcription from the annotations on the task {task.id}",
            ),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


@pytest.mark.parametrize("use_raw_publication", [True, False])
def test_export_entity_form_annotations_without_order(
    caplog,
    mock_arkindex_client,
    managed_entity_form_campaign,
    contributor,
    use_raw_publication,
    process,
    base_config,
):
    element = managed_entity_form_campaign.project.elements.filter(image__isnull=False).first()
    task = managed_entity_form_campaign.tasks.create(element=element)
    user_task = task.user_tasks.create(user=contributor.user, state=TaskState.Validated)
    entities = [
        {
            "value": "Harry",
            "entity_type": "first_name",
            "instruction": "First name",
            "type_id": "type2id",  # For debug only
            "offset": 16,  # For debug only
        },
        {
            "value": "Potter",
            "entity_type": "last_name",
            "instruction": "Last name",
            "type_id": "type3id",  # For debug only
            "offset": 22,  # For debug only
        },
        {
            "value": "Little Whinging",
            "entity_type": "city",
            "instruction": "City",
            "type_id": "type1id",  # For debug only
            "offset": 0,  # For debug only
        },
    ]
    annotation = Annotation.objects.create(
        user_task=user_task,
        value={"values": entities},
    )

    ark_transcription_id = str(uuid.uuid4())
    mock_arkindex_client.add_response(
        "CreateTranscription",
        {"id": ark_transcription_id},
        # Default alphabetical order is ("city", "City"), ("first_name", "First name"), ("last_name", "Last name")
        body={"text": "Little Whinging Harry Potter", "worker_run_id": WORKER_RUN_ID, "confidence": 1},
        id=element.provider_object_id,
    )

    mock_arkindex_client.add_response(
        "CreateTranscriptionEntities",
        {"entities": []},
        id=ark_transcription_id,
        body={
            "worker_run_id": WORKER_RUN_ID,
            "transcription_entities": [
                {
                    "offset": entity["offset"],
                    "length": len(entity["value"]),
                    "type_id": entity["type_id"],
                    "confidence": 1,
                }
                for entity in sorted(
                    entities,
                    key=lambda entity: [
                        ("city", "City"),
                        ("first_name", "First name"),
                        ("last_name", "Last name"),
                    ].index((entity["entity_type"], entity["instruction"])),
                )
            ],
        },
    )

    # Removing the configured order, we'll order entities alphabetically by default
    base_config.pop("entities_order")
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
                f"Successfully published the transcription forged with 3 valid entities from the annotations on the task {task.id}",
            ),
            (
                logging.INFO,
                f"Successfully published and linked 3 entities with the transcription from the annotations on the task {task.id}",
            ),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


@pytest.mark.parametrize("use_raw_publication", [True, False])
def test_export_entity_form_annotations_with_parent_annotation(
    caplog,
    mock_arkindex_client,
    managed_entity_form_campaign,
    contributor,
    use_raw_publication,
    process,
    base_config,
):
    element = managed_entity_form_campaign.project.elements.filter(image__isnull=False).first()
    task = managed_entity_form_campaign.tasks.create(element=element)
    user_task = task.user_tasks.create(user=contributor.user, state=TaskState.Validated)
    parent_annotation = Annotation.objects.create(
        user_task=user_task,
        value={
            "values": [
                {
                    "value": "Harry",
                    "entity_type": "first_name",
                    "instruction": "First name",
                },
                {
                    "value": "Potter",
                    "entity_type": "last_name",
                    "instruction": "Last name",
                },
                {
                    "value": "Little Whinging",
                    "entity_type": "city",
                    "instruction": "City",
                },
            ]
        },
        published=True,
    )
    entities = [
        {
            "value": "Garry",
            "entity_type": "first_name",
            "instruction": "First name",
            "type_id": "type2id",  # For debug only
            "offset": 0,  # For debug only
        },
        {
            "value": "Dotter",
            "entity_type": "last_name",
            "instruction": "Last name",
            "type_id": "type3id",  # For debug only
            "offset": 6,  # For debug only
        },
        {
            "value": "Title Mhinging",
            "entity_type": "city",
            "instruction": "City",
            "type_id": "type1id",  # For debug only
            "offset": 13,  # For debug only
        },
    ]
    annotation = Annotation.objects.create(
        parent=parent_annotation,
        user_task=user_task,
        value={"values": entities},
    )

    ark_transcription_id = str(uuid.uuid4())
    mock_arkindex_client.add_response(
        "CreateTranscription",
        {"id": ark_transcription_id},
        body={"text": "Garry Dotter Title Mhinging", "worker_run_id": WORKER_RUN_ID, "confidence": 1},
        id=element.provider_object_id,
    )

    mock_arkindex_client.add_response(
        "CreateTranscriptionEntities",
        {"entities": []},
        id=ark_transcription_id,
        body={
            "worker_run_id": WORKER_RUN_ID,
            "transcription_entities": [
                {
                    "offset": entity["offset"],
                    "length": len(entity["value"]),
                    "type_id": entity["type_id"],
                    "confidence": 1,
                }
                for entity in entities
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
                f"Successfully published the transcription forged with 3 valid entities from the annotations on the task {task.id}",
            ),
            (
                logging.INFO,
                f"Successfully published and linked 3 entities with the transcription from the annotations on the task {task.id}",
            ),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


@pytest.mark.parametrize("use_raw_publication", [True, False])
def test_export_entity_form_annotations_multiple_same_annotations(
    caplog,
    mock_arkindex_client,
    managed_entity_form_campaign,
    contributor,
    new_contributor,
    use_raw_publication,
    process,
    base_config,
):
    element = managed_entity_form_campaign.project.elements.filter(image__isnull=False).first()
    task = managed_entity_form_campaign.tasks.create(element=element)
    user_tasks = TaskUser.objects.bulk_create(
        [TaskUser(task=task, user=user, state=TaskState.Pending) for user in [contributor.user, new_contributor]]
    )
    entities = [
        {
            "value": "Harry",
            "entity_type": "first_name",
            "instruction": "First name",
            "type_id": "type2id",  # For debug only
            "offset": 0,  # For debug only
        },
        {
            "value": "Potter",
            "entity_type": "last_name",
            "instruction": "Last name",
            "type_id": "type3id",  # For debug only
            "offset": 6,  # For debug only
        },
        {
            "value": "Little Whinging",
            "entity_type": "city",
            "instruction": "City",
            "type_id": "type1id",  # For debug only
            "offset": 13,  # For debug only
        },
    ]
    for user_task in user_tasks:
        annotation = Annotation.objects.create(
            user_task=user_task,
            value={"values": entities},
        )
        user_task.state = TaskState.Annotated
        user_task.save()

    nb_publications = 1 if not use_raw_publication else len(user_tasks)
    for _i in range(nb_publications):
        ark_transcription_id = str(uuid.uuid4())
        mock_arkindex_client.add_response(
            "CreateTranscription",
            {"id": ark_transcription_id},
            body={"text": "Harry Potter Little Whinging", "worker_run_id": WORKER_RUN_ID, "confidence": 1},
            id=element.provider_object_id,
        )

        mock_arkindex_client.add_response(
            "CreateTranscriptionEntities",
            {"entities": []},
            id=ark_transcription_id,
            body={
                "worker_run_id": WORKER_RUN_ID,
                "transcription_entities": [
                    {
                        "offset": entity["offset"],
                        "length": len(entity["value"]),
                        "type_id": entity["type_id"],
                        "confidence": 1,
                    }
                    for entity in entities
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
        ]
        + [
            (
                logging.INFO,
                f"Successfully published the transcription forged with 3 valid entities from the annotations on the task {task.id}",
            ),
            (
                logging.INFO,
                f"Successfully published and linked 3 entities with the transcription from the annotations on the task {task.id}",
            ),
        ]
        * nb_publications
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


@pytest.mark.parametrize("use_raw_publication", [True, False])
def test_export_entity_form_annotations_multiple_differing_annotations(
    caplog,
    mock_arkindex_client,
    managed_entity_form_campaign,
    contributor,
    new_contributor,
    use_raw_publication,
    process,
    base_config,
):
    element = managed_entity_form_campaign.project.elements.filter(image__isnull=False).first()
    task = managed_entity_form_campaign.tasks.create(element=element)
    TaskUser.objects.bulk_create(
        [TaskUser(task=task, user=user, state=TaskState.Pending) for user in [contributor.user, new_contributor]]
    )

    first_name_values = ["Harry", "Garry"]
    last_name_values = ["Potter", "Dotter"]
    city_values = ["Little Whinging", "Title Mhinging"]
    total_entities = {}
    for index, user_task in enumerate(task.user_tasks.all().order_by("-created", "id")):
        entities = [
            {
                "value": first_name_values[index],
                "entity_type": "first_name",
                "instruction": "First name",
                "type_id": "type2id",  # For debug only
                "offset": 0,  # For debug only
            },
            {
                "value": last_name_values[index],
                "entity_type": "last_name",
                "instruction": "Last name",
                "type_id": "type3id",  # For debug only
                "offset": 6,  # For debug only
            },
            {
                "value": city_values[index],
                "entity_type": "city",
                "instruction": "City",
                "type_id": "type1id",  # For debug only
                "offset": 13,  # For debug only
            },
        ]
        Annotation.objects.create(
            user_task=user_task,
            value={"values": entities},
        )
        user_task.state = TaskState.Annotated
        user_task.save()
        total_entities[index] = entities

    confidence = 0.5 if not use_raw_publication else 1
    first_ark_transcription_id = str(uuid.uuid4())
    mock_arkindex_client.add_response(
        "CreateTranscription",
        {"id": first_ark_transcription_id},
        body={"text": "Harry Potter Little Whinging", "worker_run_id": WORKER_RUN_ID, "confidence": confidence},
        id=element.provider_object_id,
    )
    second_ark_transcription_id = str(uuid.uuid4())
    mock_arkindex_client.add_response(
        "CreateTranscription",
        {"id": second_ark_transcription_id},
        body={"text": "Garry Dotter Title Mhinging", "worker_run_id": WORKER_RUN_ID, "confidence": confidence},
        id=element.provider_object_id,
    )

    mock_arkindex_client.add_response(
        "CreateTranscriptionEntities",
        {"entities": []},
        id=first_ark_transcription_id,
        body={
            "worker_run_id": WORKER_RUN_ID,
            "transcription_entities": [
                {
                    "length": len(entity["value"]),
                    "offset": entity["offset"],
                    "confidence": 1,
                    "type_id": entity["type_id"],
                }
                for entity in total_entities[0]
            ],
        },
    )

    mock_arkindex_client.add_response(
        "CreateTranscriptionEntities",
        {"entities": []},
        id=second_ark_transcription_id,
        body={
            "worker_run_id": WORKER_RUN_ID,
            "transcription_entities": [
                {
                    "length": len(entity["value"]),
                    "offset": entity["offset"],
                    "confidence": 1,
                    "type_id": entity["type_id"],
                }
                for entity in total_entities[1]
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
            (logging.WARNING, f"Differing sets of entities were found on annotations from task {task.id}"),
            (
                logging.INFO,
                f"Successfully published the transcription forged with 3 valid entities from the annotations on the task {task.id}",
            ),
            (
                logging.INFO,
                f"Successfully published and linked 3 entities with the transcription from the annotations on the task {task.id}",
            ),
            (
                logging.INFO,
                f"Successfully published the transcription forged with 3 valid entities from the annotations on the task {task.id}",
            ),
            (
                logging.INFO,
                f"Successfully published and linked 3 entities with the transcription from the annotations on the task {task.id}",
            ),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


@pytest.mark.parametrize("state", [TaskState.Annotated, TaskState.Validated])
@pytest.mark.parametrize("use_raw_publication", [True, False])
def test_export_entity_form_annotations_single_annotation(
    caplog,
    mock_arkindex_client,
    managed_entity_form_campaign,
    contributor,
    state,
    use_raw_publication,
    process,
    base_config,
):
    element = managed_entity_form_campaign.project.elements.filter(image__isnull=False).first()
    task = managed_entity_form_campaign.tasks.create(element=element)
    user_task = task.user_tasks.create(user=contributor.user, state=state)
    entities = [
        {
            "value": "Harry",
            "entity_type": "first_name",
            "instruction": "First name",
            "type_id": "type2id",  # For debug only
            "offset": 0,  # For debug only
        },
        {
            "value": "Potter",
            "entity_type": "last_name",
            "instruction": "Last name",
            "type_id": "type3id",  # For debug only
            "offset": 6,  # For debug only
        },
        {
            "value": "Little Whinging",
            "entity_type": "city",
            "instruction": "City",
            "type_id": "type1id",  # For debug only
            "offset": 13,  # For debug only
        },
    ]
    annotation = Annotation.objects.create(
        user_task=user_task,
        value={"values": entities},
    )

    ark_transcription_id = str(uuid.uuid4())
    mock_arkindex_client.add_response(
        "CreateTranscription",
        {"id": ark_transcription_id},
        body={"text": "Harry Potter Little Whinging", "worker_run_id": WORKER_RUN_ID, "confidence": 1},
        id=element.provider_object_id,
    )

    mock_arkindex_client.add_response(
        "CreateTranscriptionEntities",
        {"entities": []},
        id=ark_transcription_id,
        body={
            "worker_run_id": WORKER_RUN_ID,
            "transcription_entities": [
                {
                    "offset": entity["offset"],
                    "length": len(entity["value"]),
                    "type_id": entity["type_id"],
                    "confidence": 1,
                }
                for entity in entities
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
                f"Successfully published the transcription forged with 3 valid entities from the annotations on the task {task.id}",
            ),
            (
                logging.INFO,
                f"Successfully published and linked 3 entities with the transcription from the annotations on the task {task.id}",
            ),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )
