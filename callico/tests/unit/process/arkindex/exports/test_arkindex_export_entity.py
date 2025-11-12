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
def managed_entity_campaign(managed_campaign, new_contributor, mock_arkindex_client):
    managed_campaign.project.memberships.create(user=new_contributor, role=Role.Contributor)
    managed_campaign.mode = CampaignMode.Entity
    managed_campaign.save()
    managed_campaign.refresh_from_db()

    element = managed_campaign.project.elements.filter(image__isnull=False).first()
    element.transcription = {
        "id": str(uuid.uuid4()),
        "text": "Emma Charlotte-\nDuerre\nWatson was born on 15 April\n1990 in Paris.",
    }
    element.save()
    element.refresh_from_db()

    mock_arkindex_client.add_response(
        "ListCorpusEntityTypes",
        id=managed_campaign.project.provider_object_id,
        response=[
            {"name": "city", "color": "ffffff", "id": "type1id"},
            {"name": "birthday", "color": "000000", "id": "type2id"},
            {"name": "person", "color": "ffffff", "id": "type3id"},
            {"name": "date", "color": "ffffff", "id": "type4id"},
        ],
    )

    return managed_campaign


@pytest.fixture()
def base_config(arkindex_provider, managed_entity_campaign, use_raw_publication):
    return {
        "arkindex_provider": str(arkindex_provider.id),
        "campaign": str(managed_entity_campaign.id),
        "worker_run": str(WORKER_RUN_ID),
        "corpus": managed_entity_campaign.project.provider_object_id,
        "exported_states": [TaskState.Annotated, TaskState.Validated],
        "use_raw_publication": use_raw_publication,
    }


@pytest.mark.parametrize("annotation_value", [{"no_entities": "oops"}, {"entities": "not a list"}])
@pytest.mark.parametrize("use_raw_publication", [True, False])
def test_export_entity_annotations_annotation_value_error(
    caplog,
    managed_entity_campaign,
    contributor,
    annotation_value,
    use_raw_publication,
    process,
    base_config,
):
    task = managed_entity_campaign.tasks.create(
        element=managed_entity_campaign.project.elements.filter(image__isnull=False).first()
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
                f"Skipping the task {task.id} as at least one of its last entity annotations holds an invalid value",
            ),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


@pytest.mark.parametrize("use_raw_publication", [True, False])
def test_export_entity_annotations_new_entity_type_error(
    caplog,
    mock_arkindex_client,
    managed_entity_campaign,
    contributor,
    use_raw_publication,
    process,
    base_config,
):
    corpus_id = managed_entity_campaign.project.provider_object_id
    random.seed(1)

    element = managed_entity_campaign.project.elements.filter(transcription__text__isnull=False).first()
    task = managed_entity_campaign.tasks.create(element=element)
    user_task = task.user_tasks.create(user=contributor.user, state=TaskState.Validated)

    entities = [
        {
            "offset": 0,
            "length": 29,
            "entity_type": "person",
            "expected_value": "Emma Charlotte-Duerre Watson",  # For debug only
            "type_id": "type3id",  # For debug only
        },
        {
            "offset": 42,
            "length": 13,
            "entity_type": "birthday",
            "expected_value": "15 April 1990",  # For debug only
            "type_id": "type2id",  # For debug only
        },
        {
            "offset": 59,
            "length": 5,
            "entity_type": "new type",
            "expected_value": "Paris",  # For debug only
            "type_id": "newtypeid",  # For debug only
        },
    ]
    annotation = Annotation.objects.create(
        user_task=user_task,
        value={"entities": entities},
    )

    mock_arkindex_client.add_error_response(
        "CreateEntityType", status_code=400, body={"name": "new type", "corpus": corpus_id, "color": "44cb63"}
    )
    mock_arkindex_client.add_response(
        "CreateTranscriptionEntities",
        {"entities": []},
        id=element.transcription["id"],
        body={
            "worker_run_id": WORKER_RUN_ID,
            "transcription_entities": [
                {
                    "offset": entity["offset"],
                    "length": entity["length"],
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
                logging.ERROR,
                f"Failed to publish entity of type new type from the annotations on the task {task.id}; an error occurred while creating the entity type new type in the corpus {corpus_id}: 400 - Mock error response",
            ),
            (
                logging.INFO,
                f"Successfully published and linked 2 entities with the transcription from the annotations on the task {task.id}",
            ),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


@pytest.mark.parametrize("use_raw_publication", [True, False])
def test_export_entity_annotations_new_entity_type(
    caplog,
    mock_arkindex_client,
    managed_entity_campaign,
    contributor,
    use_raw_publication,
    process,
    base_config,
):
    corpus_id = managed_entity_campaign.project.provider_object_id
    random.seed(0)

    element = managed_entity_campaign.project.elements.filter(transcription__text__isnull=False).first()
    task = managed_entity_campaign.tasks.create(element=element)
    user_task = task.user_tasks.create(user=contributor.user, state=TaskState.Validated)

    entities = [
        {
            "offset": 0,
            "length": 29,
            "entity_type": "person",
            "expected_value": "Emma Charlotte-Duerre Watson",  # For debug only
            "type_id": "type3id",  # For debug only
        },
        {
            "offset": 42,
            "length": 13,
            "entity_type": "birthday",
            "expected_value": "15 April 1990",  # For debug only
            "type_id": "type2id",  # For debug only
        },
        {
            "offset": 59,
            "length": 5,
            "entity_type": "new type",
            "expected_value": "Paris",  # For debug only
            "type_id": "newtypeid",  # For debug only
        },
    ]
    annotation = Annotation.objects.create(
        user_task=user_task,
        value={"entities": entities},
    )

    mock_arkindex_client.add_response(
        "CreateEntityType",
        body={"name": "new type", "corpus": corpus_id, "color": "c53edf"},
        response={"name": "new type", "id": "newtypeid"},
    )
    mock_arkindex_client.add_response(
        "CreateTranscriptionEntities",
        {"entities": []},
        id=element.transcription["id"],
        body={
            "worker_run_id": WORKER_RUN_ID,
            "transcription_entities": [
                {
                    "offset": entity["offset"],
                    "length": entity["length"],
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
                f"Successfully published and linked 3 entities with the transcription from the annotations on the task {task.id}",
            ),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


@pytest.mark.parametrize("use_raw_publication", [True, False])
def test_export_entity_annotations_api_createtranscriptionentities_error(
    caplog,
    mock_arkindex_client,
    managed_entity_campaign,
    contributor,
    use_raw_publication,
    process,
    base_config,
):
    element = managed_entity_campaign.project.elements.filter(transcription__text__isnull=False).first()
    task = managed_entity_campaign.tasks.create(element=element)
    user_task = task.user_tasks.create(user=contributor.user, state=TaskState.Validated)
    entities = [
        {
            "offset": 0,
            "length": 29,
            "entity_type": "person",
            "expected_value": "Emma Charlotte-Duerre Watson",  # For debug only
            "type_id": "type3id",  # For debug only
        },
        {
            "offset": 42,
            "length": 13,
            "entity_type": "birthday",
            "expected_value": "15 April 1990",  # For debug only
            "type_id": "type2id",  # For debug only
        },
        {
            "offset": 59,
            "length": 5,
            "entity_type": "city",
            "expected_value": "Paris",  # For debug only
            "type_id": "type1id",  # For debug only
        },
    ]
    annotation = Annotation.objects.create(
        user_task=user_task,
        value={"entities": entities},
    )

    mock_arkindex_client.add_error_response(
        "CreateTranscriptionEntities",
        status_code=400,
        id=element.transcription["id"],
        body={
            "worker_run_id": WORKER_RUN_ID,
            "transcription_entities": [
                {
                    "offset": entity["offset"],
                    "length": entity["length"],
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
                logging.ERROR,
                f"Failed to publish and link 3 entities with the transcription from the annotations on the task {task.id}: 400 - Mock error response",
            ),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


@pytest.mark.parametrize("use_raw_publication", [True, False])
def test_export_entity_annotations_skip_no_transcription_id(
    caplog,
    managed_entity_campaign,
    contributor,
    use_raw_publication,
    process,
    base_config,
):
    element = managed_entity_campaign.project.elements.filter(transcription__text__isnull=False).first()
    element.transcription = {}
    element.save()

    task = managed_entity_campaign.tasks.create(element=element)
    user_task = task.user_tasks.create(user=contributor.user, state=TaskState.Validated)
    annotation = Annotation.objects.create(user_task=user_task)

    export_process = ArkindexExport.from_configuration(process, base_config)
    export_process.run()

    annotation.refresh_from_db()
    assert not annotation.published
    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == [
            (logging.INFO, 'Using campaign "Campaign"'),
            (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
            (logging.WARNING, f"Skipping the task {task.id} as there is no transcription ID"),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


@pytest.mark.parametrize("use_raw_publication", [True, False])
def test_export_entity_annotations_skip_empty_entity(
    caplog,
    mock_arkindex_client,
    managed_entity_campaign,
    contributor,
    use_raw_publication,
    process,
    base_config,
):
    element = managed_entity_campaign.project.elements.filter(transcription__text__isnull=False).first()
    task = managed_entity_campaign.tasks.create(element=element)
    user_task = task.user_tasks.create(user=contributor.user, state=TaskState.Validated)
    entities = [
        {
            "offset": 0,
            "length": 0,
            "entity_type": "person",  # For debug only
            "type_id": "type3id",  # For debug only
        },
        {
            "offset": 42,
            "length": 13,
            "entity_type": "date",
            "expected_value": "15 April 1990",  # For debug only
            "type_id": "type4id",  # For debug only
        },
        {
            "offset": 59,
            "length": 5,
            "entity_type": "city",
            "expected_value": "Paris",  # For debug only
            "type_id": "type1id",  # For debug only
        },
    ]
    annotation = Annotation.objects.create(
        user_task=user_task,
        value={"entities": entities},
    )

    mock_arkindex_client.add_response(
        "CreateTranscriptionEntities",
        {"entities": []},
        id=element.transcription["id"],
        body={
            "worker_run_id": WORKER_RUN_ID,
            "transcription_entities": [
                {
                    "offset": entity["offset"],
                    "length": entity["length"],
                    "type_id": entity["type_id"],
                    "confidence": 1,
                }
                for entity in entities
                if entity["length"]
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
                logging.WARNING,
                f"Skipping the entity of type person from the annotations on the task {task.id} as it is empty",
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
def test_export_entity_annotations_nothing_annotated(
    caplog,
    managed_entity_campaign,
    contributor,
    use_raw_publication,
    process,
    base_config,
):
    element = managed_entity_campaign.project.elements.filter(transcription__text__isnull=False).first()
    task = managed_entity_campaign.tasks.create(element=element)
    user_task = task.user_tasks.create(user=contributor.user, state=TaskState.Validated)
    annotation = Annotation.objects.create(user_task=user_task, value={"entities": []})

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
def test_export_entity_annotations_with_parent_annotation(
    caplog,
    mock_arkindex_client,
    managed_entity_campaign,
    contributor,
    use_raw_publication,
    process,
    base_config,
):
    element = managed_entity_campaign.project.elements.filter(transcription__text__isnull=False).first()
    task = managed_entity_campaign.tasks.create(element=element)
    user_task = task.user_tasks.create(user=contributor.user, state=TaskState.Validated)

    parent_annotation = Annotation.objects.create(
        user_task=user_task,
        value={
            "entities": [
                {
                    "offset": 0,
                    "length": 0,
                    "entity_type": "person",
                },
                {
                    "offset": 0,
                    "length": 0,
                    "entity_type": "birthday",
                },
                {
                    "offset": 0,
                    "length": 0,
                    "entity_type": "city",
                },
            ]
        },
        published=True,
    )
    entities = [
        {
            "offset": 0,
            "length": 29,
            "entity_type": "person",
            "expected_value": "Emma Charlotte-Duerre Watson",  # For debug only
            "type_id": "type3id",  # For debug only
        },
        {
            "offset": 42,
            "length": 13,
            "entity_type": "birthday",
            "expected_value": "15 April 1990",  # For debug only
            "type_id": "type2id",  # For debug only
        },
        {
            "offset": 59,
            "length": 5,
            "entity_type": "city",
            "expected_value": "Paris",  # For debug only
            "type_id": "type1id",  # For debug only
        },
    ]
    annotation = Annotation.objects.create(
        parent=parent_annotation,
        user_task=user_task,
        value={"entities": entities},
    )

    mock_arkindex_client.add_response(
        "CreateTranscriptionEntities",
        {"entities": []},
        id=element.transcription["id"],
        body={
            "worker_run_id": WORKER_RUN_ID,
            "transcription_entities": [
                {
                    "offset": entity["offset"],
                    "length": entity["length"],
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
                f"Successfully published and linked 3 entities with the transcription from the annotations on the task {task.id}",
            ),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


@pytest.mark.parametrize("use_raw_publication", [True, False])
def test_export_entity_annotations_multiple_same_annotations(
    caplog,
    mock_arkindex_client,
    managed_entity_campaign,
    contributor,
    new_contributor,
    use_raw_publication,
    process,
    base_config,
):
    element = managed_entity_campaign.project.elements.filter(transcription__text__isnull=False).first()
    task = managed_entity_campaign.tasks.create(element=element)
    user_tasks = TaskUser.objects.bulk_create(
        [TaskUser(task=task, user=user, state=TaskState.Pending) for user in [contributor.user, new_contributor]]
    )
    entities = [
        {
            "offset": 0,
            "length": 29,
            "entity_type": "person",
            "expected_value": "Emma Charlotte-Duerre Watson",  # For debug only
            "type_id": "type3id",  # For debug only
        },
        {
            "offset": 42,
            "length": 13,
            "entity_type": "birthday",
            "expected_value": "15 April 1990",  # For debug only
            "type_id": "type2id",  # For debug only
        },
        {
            "offset": 59,
            "length": 5,
            "entity_type": "city",
            "expected_value": "Paris",  # For debug only
            "type_id": "type1id",  # For debug only
        },
    ]
    for user_task in user_tasks:
        annotation = Annotation.objects.create(
            user_task=user_task,
            value={"entities": entities},
        )
        user_task.state = TaskState.Annotated
        user_task.save()

    nb_publications = 1 if not use_raw_publication else len(user_tasks)
    mock_arkindex_client.add_response(
        "CreateTranscriptionEntities",
        {"entities": []},
        id=element.transcription["id"],
        body={
            "worker_run_id": WORKER_RUN_ID,
            "transcription_entities": [
                {
                    "offset": entity["offset"],
                    "length": entity["length"],
                    "type_id": entity["type_id"],
                    "confidence": 1,
                }
                for entity in sorted(entities * nb_publications, key=lambda i: i["offset"])
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
                f"Successfully published and linked {3 * nb_publications} entities with the transcription from the annotations on the task {task.id}",
            ),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


@pytest.mark.parametrize("use_raw_publication", [True, False])
def test_export_entity_annotations_multiple_differing_annotations(
    caplog,
    mock_arkindex_client,
    managed_entity_campaign,
    contributor,
    new_contributor,
    use_raw_publication,
    process,
    base_config,
):
    element = managed_entity_campaign.project.elements.filter(transcription__text__isnull=False).first()
    task = managed_entity_campaign.tasks.create(element=element)
    TaskUser.objects.bulk_create(
        [TaskUser(task=task, user=user, state=TaskState.Pending) for user in [contributor.user, new_contributor]]
    )

    person_values = ["Emma Charlotte-Duerre Watson", "Emma"]
    bithday_values = ["15 April 1990", "15 April"]
    city_values = ["Paris", ""]
    total_entities = []
    for index, user_task in enumerate(task.user_tasks.all().order_by("-created", "id")):
        entities = [
            {
                "offset": 0,
                "length": len(person_values[index]) + 1 * (index == 0),
                "entity_type": "person",
                "type_id": "type3id",  # For debug only
                "expected_value": person_values[index],  # For debug only
            },
            {
                "offset": 42,
                "length": len(bithday_values[index]),
                "entity_type": "birthday",
                "type_id": "type2id",  # For debug only
                "expected_value": bithday_values[index],  # For debug only
            },
        ]
        if city_values[index]:
            entities.append(
                {
                    "offset": 59,
                    "length": len(city_values[index]),
                    "entity_type": "city",
                    "type_id": "type1id",  # For debug only
                    "expected_value": city_values[index],  # For debug only
                }
            )
        Annotation.objects.create(
            user_task=user_task,
            value={"entities": entities},
        )
        user_task.state = TaskState.Annotated
        user_task.save()
        total_entities.extend(entities)

    confidence = 0.5 if not use_raw_publication else 1
    mock_arkindex_client.add_response(
        "CreateTranscriptionEntities",
        {"entities": []},
        id=element.transcription["id"],
        body={
            "worker_run_id": WORKER_RUN_ID,
            "transcription_entities": [
                {
                    "type_id": entity["type_id"],
                    "offset": entity["offset"],
                    "length": entity["length"],
                    "confidence": confidence,
                }
                for entity in total_entities
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
                logging.INFO,
                f"Successfully published and linked 5 entities with the transcription from the annotations on the task {task.id}",
            ),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


@pytest.mark.parametrize("state", [TaskState.Annotated, TaskState.Validated])
@pytest.mark.parametrize("use_raw_publication", [True, False])
def test_export_entity_annotations_single_annotation(
    caplog,
    mock_arkindex_client,
    managed_entity_campaign,
    contributor,
    state,
    use_raw_publication,
    process,
    base_config,
):
    element = managed_entity_campaign.project.elements.filter(transcription__text__isnull=False).first()
    task = managed_entity_campaign.tasks.create(element=element)
    user_task = task.user_tasks.create(user=contributor.user, state=state)
    entities = [
        {
            "offset": 0,
            "length": 29,
            "entity_type": "person",
            "expected_value": "Emma Charlotte-Duerre Watson",  # For debug only
            "type_id": "type3id",  # For debug only
        },
        {
            "offset": 42,
            "length": 13,
            "entity_type": "birthday",
            "expected_value": "15 April 1990",  # For debug only
            "type_id": "type2id",  # For debug only
        },
        {
            "offset": 59,
            "length": 5,
            "entity_type": "city",
            "expected_value": "Paris",  # For debug only
            "type_id": "type1id",  # For debug only
        },
    ]
    annotation = Annotation.objects.create(
        user_task=user_task,
        value={"entities": entities},
    )

    mock_arkindex_client.add_response(
        "CreateTranscriptionEntities",
        {"entities": []},
        id=element.transcription["id"],
        body={
            "worker_run_id": WORKER_RUN_ID,
            "transcription_entities": [
                {
                    "offset": entity["offset"],
                    "length": entity["length"],
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
                f"Successfully published and linked 3 entities with the transcription from the annotations on the task {task.id}",
            ),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )
