import logging
import random
import uuid

import pytest

from callico.annotations.models import Annotation, TaskState
from callico.process.arkindex.exports import ArkindexExport
from callico.projects.models import CampaignMode, Element, Role
from callico.users.models import User

pytestmark = pytest.mark.django_db

WORKER_RUN_ID = "12341234-1234-1234-1234-123412341234"


@pytest.fixture()
def managed_entity_form_campaign(mocker, managed_campaign, new_contributor, mock_arkindex_client):
    # Mocking the publication at element level as it is already fully tested in another test file
    mocker.patch("callico.process.arkindex.exports.ArkindexExport.publish_annotations_at_element_level")

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
def folder_type(managed_entity_form_campaign):
    return managed_entity_form_campaign.project.types.get(name="Folder")


@pytest.fixture()
def base_config(arkindex_provider, managed_entity_form_campaign, folder_type):
    return {
        "arkindex_provider": str(arkindex_provider.id),
        "campaign": str(managed_entity_form_campaign.id),
        "worker_run": str(WORKER_RUN_ID),
        "corpus": managed_entity_form_campaign.project.provider_object_id,
        "exported_states": [TaskState.Annotated, TaskState.Validated],
        "entities_order": [
            ["first_name", "First name"],
            ["last_name", "Last name"],
            ["city", "City"],
            ["date", "Date"],
        ],
        "concatenation_parent_type": str(folder_type.id),
    }


def test_export_entity_form_annotations_on_parent_wrong_parent_type(
    process,
    base_config,
):
    config = {**base_config, "concatenation_parent_type": "cafecafe-cafe-cafe-cafe-cafecafecafe"}
    with pytest.raises(Exception, match="Type matching query does not exist."):
        export_process = ArkindexExport.from_configuration(process, config)
        export_process.run()


def test_export_entity_form_annotations_on_parent_no_parent_found(
    caplog,
    managed_entity_form_campaign,
    process,
    base_config,
):
    # Pages don't have children on our test data, thus they won't be listed as parent
    config = {
        **base_config,
        "concatenation_parent_type": str(managed_entity_form_campaign.project.types.get(name="Page").id),
    }
    export_process = ArkindexExport.from_configuration(process, config)
    export_process.run()

    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == [
            (logging.INFO, 'Using campaign "Campaign"'),
            (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
            (logging.INFO, "Starting to export entities in concatenated transcriptions on the chosen parent type Page"),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


def test_export_entity_form_annotations_on_parent_no_valid_children(
    caplog,
    managed_entity_form_campaign,
    folder_type,
    process,
    base_config,
):
    page_element = managed_entity_form_campaign.project.elements.filter(
        image__isnull=False, parent__type=folder_type
    ).first()

    # Deleting other parent elements to avoid a spam of logs
    managed_entity_form_campaign.project.elements.exclude(id=page_element.parent.id).filter(type=folder_type).delete()

    export_process = ArkindexExport.from_configuration(process, base_config)
    export_process.run()

    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == [
            (logging.INFO, 'Using campaign "Campaign"'),
            (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
            (
                logging.INFO,
                "Starting to export entities in concatenated transcriptions on the chosen parent type Folder",
            ),
            (
                logging.WARNING,
                f"Skipping the Folder parent {page_element.parent.id} as no annotated child elements were found on it",
            ),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


def test_export_entity_form_annotations_on_parent_multiple_children_types(
    caplog,
    managed_entity_form_campaign,
    folder_type,
    arkindex_provider,
    image,
    contributor,
    process,
    base_config,
):
    page_element = managed_entity_form_campaign.project.elements.filter(
        image__isnull=False, parent__type=folder_type
    ).first()
    line_type = managed_entity_form_campaign.project.types.get(name="Line")
    line_element = managed_entity_form_campaign.project.elements.create(
        name="Line 1",
        type=line_type,
        provider=arkindex_provider,
        provider_object_id=str(uuid.uuid4()),
        image=image,
        order=1,
        parent=page_element,
    )

    # Deleting other parent elements to avoid a spam of logs
    managed_entity_form_campaign.project.elements.exclude(id=page_element.parent.id).filter(type=folder_type).delete()

    for element in [page_element, line_element]:
        task = managed_entity_form_campaign.tasks.create(element=element)
        user_task = task.user_tasks.create(user=contributor.user, state=TaskState.Validated)
        Annotation.objects.create(user_task=user_task, value={"values": []})

    export_process = ArkindexExport.from_configuration(process, base_config)
    export_process.run()

    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == [
            (logging.INFO, 'Using campaign "Campaign"'),
            (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
            (
                logging.INFO,
                "Starting to export entities in concatenated transcriptions on the chosen parent type Folder",
            ),
            (
                logging.ERROR,
                f"Skipping the Folder parent {page_element.parent.id} as multiple children types to concatenate were found",
            ),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


def test_export_entity_form_annotations_on_parent_child_missing_good_annotation(
    caplog,
    managed_entity_form_campaign,
    folder_type,
    contributor,
    process,
    base_config,
):
    parent = managed_entity_form_campaign.project.elements.get(name="A")
    first_child = managed_entity_form_campaign.project.elements.filter(image__isnull=False, parent=parent).first()
    second_child = managed_entity_form_campaign.project.elements.filter(image__isnull=False, parent=parent).last()

    # Deleting other parent elements to avoid a spam of logs
    managed_entity_form_campaign.project.elements.exclude(id=parent.id).filter(type=folder_type).delete()

    # First child is properly annotated
    task = managed_entity_form_campaign.tasks.create(element=first_child)
    user_task = task.user_tasks.create(user=contributor.user, state=TaskState.Validated)
    Annotation.objects.create(
        user_task=user_task,
        value={
            "values": [
                {
                    "value": "Harry",
                    "entity_type": "first_name",
                    "instruction": "First name",
                }
            ]
        },
    )

    # Second child has 4 invalid assigned tasks...
    task = managed_entity_form_campaign.tasks.create(element=second_child)
    # Isn't an exported state
    user_task = task.user_tasks.create(user=contributor.user, state=TaskState.Rejected)
    Annotation.objects.create(
        user_task=user_task,
        value={
            "values": [
                {
                    "value": "Harry",
                    "entity_type": "first_name",
                    "instruction": "First name",
                }
            ]
        },
    )
    # Doesn't have an annotation
    contributor_2 = User.objects.create(display_name="Contributor 2", email="contrib2@callico.org", password="contrib2")
    user_task = task.user_tasks.create(user=contributor_2, state=TaskState.Validated)
    # Is for preview purposes
    contributor_3 = User.objects.create(display_name="Contributor 3", email="contrib3@callico.org", password="contrib3")
    user_task = task.user_tasks.create(user=contributor_3, state=TaskState.Validated, is_preview=True)
    Annotation.objects.create(
        user_task=user_task,
        value={
            "values": [
                {
                    "value": "Harry",
                    "entity_type": "first_name",
                    "instruction": "First name",
                }
            ]
        },
    )
    # Holds an invalid value
    contributor_4 = User.objects.create(display_name="Contributor 4", email="contrib4@callico.org", password="contrib4")
    user_task = task.user_tasks.create(user=contributor_4, state=TaskState.Validated)
    Annotation.objects.create(user_task=user_task, value={"values": []})

    export_process = ArkindexExport.from_configuration(process, base_config)
    export_process.run()

    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == [
            (logging.INFO, 'Using campaign "Campaign"'),
            (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
            (
                logging.INFO,
                "Starting to export entities in concatenated transcriptions on the chosen parent type Folder",
            ),
            (
                logging.WARNING,
                f"Couldn't find a good annotation on the child {second_child.id} to concatenate and publish on its Folder parent {parent.id}",
            ),
            (
                logging.ERROR,
                f"Skipping the Folder parent {parent.id} as at least one child was missing an annotation to concatenate",
            ),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


def test_export_entity_form_annotations_on_parent_api_createtranscription_error(
    caplog,
    mock_arkindex_client,
    managed_entity_form_campaign,
    folder_type,
    contributor,
    process,
    base_config,
):
    parent = managed_entity_form_campaign.project.elements.get(name="A")
    first_child = managed_entity_form_campaign.project.elements.filter(image__isnull=False, parent=parent).first()
    second_child = managed_entity_form_campaign.project.elements.filter(image__isnull=False, parent=parent).last()

    # Deleting other parent elements to avoid a spam of logs
    managed_entity_form_campaign.project.elements.exclude(id=parent.id).filter(type=folder_type).delete()

    first_entities = [
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
    second_entities = [
        {
            "value": "Ron",
            "entity_type": "first_name",
            "instruction": "First name",
        },
        {
            "value": "Weasley",
            "entity_type": "last_name",
            "instruction": "Last name",
        },
        {
            "value": "Ottery St Catchpole",
            "entity_type": "city",
            "instruction": "City",
        },
    ]
    for child, entities in zip([first_child, second_child], [first_entities, second_entities]):
        task = managed_entity_form_campaign.tasks.create(element=child)
        user_task = task.user_tasks.create(user=contributor.user, state=TaskState.Validated)
        Annotation.objects.create(user_task=user_task, value={"values": entities})

    mock_arkindex_client.add_error_response(
        "CreateTranscription",
        status_code=400,
        body={
            "text": "Harry Potter Little Whinging\nRon Weasley Ottery St Catchpole",
            "worker_run_id": WORKER_RUN_ID,
            "confidence": 1,
        },
        id=parent.provider_object_id,
    )

    export_process = ArkindexExport.from_configuration(process, base_config)
    export_process.run()

    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == [
            (logging.INFO, 'Using campaign "Campaign"'),
            (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
            (
                logging.INFO,
                "Starting to export entities in concatenated transcriptions on the chosen parent type Folder",
            ),
            (
                logging.ERROR,
                f"Failed to publish the transcription forged from 2 concatenated annotations to publish on the Folder parent {parent.id}: 400 - Mock error response",
            ),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


def test_export_entity_form_annotations_on_parent_new_entity_type_error(
    caplog,
    mock_arkindex_client,
    managed_entity_form_campaign,
    folder_type,
    contributor,
    process,
    base_config,
):
    corpus_id = managed_entity_form_campaign.project.provider_object_id
    random.seed(2)

    parent = managed_entity_form_campaign.project.elements.get(name="A")
    first_child = managed_entity_form_campaign.project.elements.filter(image__isnull=False, parent=parent).first()
    second_child = managed_entity_form_campaign.project.elements.filter(image__isnull=False, parent=parent).last()

    # Deleting other parent elements to avoid a spam of logs
    managed_entity_form_campaign.project.elements.exclude(id=parent.id).filter(type=folder_type).delete()

    first_entities = [
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
    second_entities = [
        {
            "value": "Ron",
            "entity_type": "first_name",
            "instruction": "First name",
            "type_id": "type2id",  # For debug only
            "offset": 29,  # For debug only
        },
        {
            "value": "Weasley",
            "entity_type": "last_name",
            "instruction": "Last name",
            "type_id": "type3id",  # For debug only
            "offset": 33,  # For debug only
        },
        {
            "value": "Ottery St Catchpole",
            "entity_type": "city",
            "instruction": "City",
            "type_id": "type1id",  # For debug only
            "offset": 41,  # For debug only
        },
    ]
    for child, entities in zip([first_child, second_child], [first_entities, second_entities]):
        task = managed_entity_form_campaign.tasks.create(element=child)
        user_task = task.user_tasks.create(user=contributor.user, state=TaskState.Validated)
        Annotation.objects.create(user_task=user_task, value={"values": entities})

    ark_transcription_id = str(uuid.uuid4())
    mock_arkindex_client.add_response(
        "CreateTranscription",
        {"id": ark_transcription_id},
        body={
            "text": "Harry Potter Little Whinging\nRon Weasley Ottery St Catchpole",
            "worker_run_id": WORKER_RUN_ID,
            "confidence": 1,
        },
        id=parent.provider_object_id,
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
                for entity in [*first_entities[:2], *second_entities]
            ],
        },
    )

    export_process = ArkindexExport.from_configuration(process, base_config)
    export_process.run()

    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == [
            (logging.INFO, 'Using campaign "Campaign"'),
            (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
            (
                logging.INFO,
                "Starting to export entities in concatenated transcriptions on the chosen parent type Folder",
            ),
            (
                logging.INFO,
                f"Successfully published the transcription forged from 2 concatenated annotations to publish on the Folder parent {parent.id}",
            ),
            (
                logging.ERROR,
                f"Failed to publish entity Little Whinging of type new type from the concatenated annotations to publish on the Folder parent {parent.id}; an error occurred while creating the entity type new type in the corpus {corpus_id}: 400 - Mock error response",
            ),
            (
                logging.INFO,
                f"Successfully published and linked 5 entities with the transcription forged from the concatenated annotations to publish on the Folder parent {parent.id}",
            ),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


def test_export_entity_form_annotations_on_parent_new_entity_type(
    caplog,
    mock_arkindex_client,
    managed_entity_form_campaign,
    folder_type,
    contributor,
    process,
    base_config,
):
    corpus_id = managed_entity_form_campaign.project.provider_object_id
    random.seed(0)

    parent = managed_entity_form_campaign.project.elements.get(name="A")
    first_child = managed_entity_form_campaign.project.elements.filter(image__isnull=False, parent=parent).first()
    second_child = managed_entity_form_campaign.project.elements.filter(image__isnull=False, parent=parent).last()

    # Deleting other parent elements to avoid a spam of logs
    managed_entity_form_campaign.project.elements.exclude(id=parent.id).filter(type=folder_type).delete()

    first_entities = [
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
    second_entities = [
        {
            "value": "Ron",
            "entity_type": "first_name",
            "instruction": "First name",
            "type_id": "type2id",  # For debug only
            "offset": 29,  # For debug only
        },
        {
            "value": "Weasley",
            "entity_type": "last_name",
            "instruction": "Last name",
            "type_id": "type3id",  # For debug only
            "offset": 33,  # For debug only
        },
        {
            "value": "Ottery St Catchpole",
            "entity_type": "city",
            "instruction": "City",
            "type_id": "type1id",  # For debug only
            "offset": 41,  # For debug only
        },
    ]
    for child, entities in zip([first_child, second_child], [first_entities, second_entities]):
        task = managed_entity_form_campaign.tasks.create(element=child)
        user_task = task.user_tasks.create(user=contributor.user, state=TaskState.Validated)
        Annotation.objects.create(user_task=user_task, value={"values": entities})

    ark_transcription_id = str(uuid.uuid4())
    mock_arkindex_client.add_response(
        "CreateTranscription",
        {"id": ark_transcription_id},
        body={
            "text": "Harry Potter Little Whinging\nRon Weasley Ottery St Catchpole",
            "worker_run_id": WORKER_RUN_ID,
            "confidence": 1,
        },
        id=parent.provider_object_id,
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
                for entity in first_entities + second_entities
            ],
        },
    )

    export_process = ArkindexExport.from_configuration(process, base_config)
    export_process.run()

    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == [
            (logging.INFO, 'Using campaign "Campaign"'),
            (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
            (
                logging.INFO,
                "Starting to export entities in concatenated transcriptions on the chosen parent type Folder",
            ),
            (
                logging.INFO,
                f"Successfully published the transcription forged from 2 concatenated annotations to publish on the Folder parent {parent.id}",
            ),
            (
                logging.INFO,
                f"Successfully published and linked 6 entities with the transcription forged from the concatenated annotations to publish on the Folder parent {parent.id}",
            ),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


def test_export_entity_form_annotations_on_parent_api_createtranscriptionentities_error(
    caplog,
    mock_arkindex_client,
    managed_entity_form_campaign,
    folder_type,
    contributor,
    process,
    base_config,
):
    parent = managed_entity_form_campaign.project.elements.get(name="A")
    first_child = managed_entity_form_campaign.project.elements.filter(image__isnull=False, parent=parent).first()
    second_child = managed_entity_form_campaign.project.elements.filter(image__isnull=False, parent=parent).last()

    # Deleting other parent elements to avoid a spam of logs
    managed_entity_form_campaign.project.elements.exclude(id=parent.id).filter(type=folder_type).delete()

    first_entities = [
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
    second_entities = [
        {
            "value": "Ron",
            "entity_type": "first_name",
            "instruction": "First name",
            "type_id": "type2id",  # For debug only
            "offset": 29,  # For debug only
        },
        {
            "value": "Weasley",
            "entity_type": "last_name",
            "instruction": "Last name",
            "type_id": "type3id",  # For debug only
            "offset": 33,  # For debug only
        },
        {
            "value": "Ottery St Catchpole",
            "entity_type": "city",
            "instruction": "City",
            "type_id": "type1id",  # For debug only
            "offset": 41,  # For debug only
        },
    ]
    for child, entities in zip([first_child, second_child], [first_entities, second_entities]):
        task = managed_entity_form_campaign.tasks.create(element=child)
        user_task = task.user_tasks.create(user=contributor.user, state=TaskState.Validated)
        Annotation.objects.create(user_task=user_task, value={"values": entities})

    ark_transcription_id = str(uuid.uuid4())
    mock_arkindex_client.add_response(
        "CreateTranscription",
        {"id": ark_transcription_id},
        body={
            "text": "Harry Potter Little Whinging\nRon Weasley Ottery St Catchpole",
            "worker_run_id": WORKER_RUN_ID,
            "confidence": 1,
        },
        id=parent.provider_object_id,
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
                for entity in first_entities + second_entities
            ],
        },
    )

    export_process = ArkindexExport.from_configuration(process, base_config)
    export_process.run()

    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == [
            (logging.INFO, 'Using campaign "Campaign"'),
            (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
            (
                logging.INFO,
                "Starting to export entities in concatenated transcriptions on the chosen parent type Folder",
            ),
            (
                logging.INFO,
                f"Successfully published the transcription forged from 2 concatenated annotations to publish on the Folder parent {parent.id}",
            ),
            (
                logging.ERROR,
                f"Failed to publish and link 6 entities with the transcription forged from the concatenated annotations to publish on the Folder parent {parent.id}: 400 - Mock error response",
            ),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


def test_export_entity_form_annotations_on_parent_skip_empty_entity(
    caplog,
    mock_arkindex_client,
    managed_entity_form_campaign,
    folder_type,
    contributor,
    process,
    base_config,
):
    parent = managed_entity_form_campaign.project.elements.get(name="A")
    first_child = managed_entity_form_campaign.project.elements.filter(image__isnull=False, parent=parent).first()
    second_child = managed_entity_form_campaign.project.elements.filter(image__isnull=False, parent=parent).last()

    # Deleting other parent elements to avoid a spam of logs
    managed_entity_form_campaign.project.elements.exclude(id=parent.id).filter(type=folder_type).delete()

    first_entities = [
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
    second_entities = [
        {
            "value": "Ron",
            "entity_type": "first_name",
            "instruction": "First name",
            "type_id": "type2id",  # For debug only
            "offset": 22,  # For debug only
        },
        {
            "value": "",
            "entity_type": "last_name",
            "instruction": "Last name",
            "type_id": "type3id",  # For debug only
            "offset": 26,  # For debug only
        },
        {
            "value": "Ottery St Catchpole",
            "entity_type": "city",
            "instruction": "City",
            "type_id": "type1id",  # For debug only
            "offset": 26,  # For debug only
        },
    ]
    for child, entities in zip([first_child, second_child], [first_entities, second_entities]):
        task = managed_entity_form_campaign.tasks.create(element=child)
        user_task = task.user_tasks.create(user=contributor.user, state=TaskState.Validated)
        Annotation.objects.create(user_task=user_task, value={"values": entities})

    ark_transcription_id = str(uuid.uuid4())
    mock_arkindex_client.add_response(
        "CreateTranscription",
        {"id": ark_transcription_id},
        body={
            "text": "Harry Little Whinging\nRon Ottery St Catchpole",
            "worker_run_id": WORKER_RUN_ID,
            "confidence": 1,
        },
        id=parent.provider_object_id,
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
                for entity in first_entities + second_entities
                if entity["value"]
            ],
        },
    )

    export_process = ArkindexExport.from_configuration(process, base_config)
    export_process.run()

    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == [
            (logging.INFO, 'Using campaign "Campaign"'),
            (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
            (
                logging.INFO,
                "Starting to export entities in concatenated transcriptions on the chosen parent type Folder",
            ),
            (
                logging.INFO,
                f"Successfully published the transcription forged from 2 concatenated annotations to publish on the Folder parent {parent.id}",
            ),
            (
                logging.INFO,
                f"Successfully published and linked 4 entities with the transcription forged from the concatenated annotations to publish on the Folder parent {parent.id}",
            ),
            (
                logging.INFO,
                f"Skipped 2 empty entities from the concatenated annotations to publish on the Folder parent {parent.id}",
            ),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


def test_export_entity_form_annotations_on_parent_with_uncertain_values(
    caplog,
    mock_arkindex_client,
    managed_entity_form_campaign,
    folder_type,
    contributor,
    process,
    base_config,
):
    parent = managed_entity_form_campaign.project.elements.get(name="A")
    first_child = managed_entity_form_campaign.project.elements.filter(image__isnull=False, parent=parent).first()
    second_child = managed_entity_form_campaign.project.elements.filter(image__isnull=False, parent=parent).last()

    # Deleting other parent elements to avoid a spam of logs
    managed_entity_form_campaign.project.elements.exclude(id=parent.id).filter(type=folder_type).delete()

    first_entities = [
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
    second_entities = [
        {
            "value": "Gon",
            "uncertain": True,
            "entity_type": "first_name",
            "instruction": "First name",
            "type_id": "type2id",  # For debug only
            "offset": 28,  # For debug only
        },
        {
            "value": "Measley",
            "uncertain": True,
            "entity_type": "last_name",
            "instruction": "Last name",
            "type_id": "type3id",  # For debug only
            "offset": 32,  # For debug only
        },
        {
            "value": "Attery St Cotchpale",
            "uncertain": True,
            "entity_type": "city",
            "instruction": "City",
            "type_id": "type1id",  # For debug only
            "offset": 40,  # For debug only
        },
    ]
    for child, entities in zip([first_child, second_child], [first_entities, second_entities]):
        task = managed_entity_form_campaign.tasks.create(element=child)
        user_task = task.user_tasks.create(user=contributor.user, state=TaskState.Validated)
        Annotation.objects.create(user_task=user_task, value={"values": entities})

    ark_transcription_id = str(uuid.uuid4())
    mock_arkindex_client.add_response(
        "CreateTranscription",
        {"id": ark_transcription_id},
        body={
            "text": "Garry Dotter Title Mhinging\nGon Measley Attery St Cotchpale",
            "worker_run_id": WORKER_RUN_ID,
            "confidence": 1,
        },
        id=parent.provider_object_id,
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
                for entity in first_entities + second_entities
            ],
        },
    )

    export_process = ArkindexExport.from_configuration(process, base_config)
    export_process.run()

    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == [
            (logging.INFO, 'Using campaign "Campaign"'),
            (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
            (
                logging.INFO,
                "Starting to export entities in concatenated transcriptions on the chosen parent type Folder",
            ),
            (
                logging.INFO,
                f"Successfully published the transcription forged from 2 concatenated annotations to publish on the Folder parent {parent.id}",
            ),
            (
                logging.INFO,
                f"Successfully published and linked 6 entities with the transcription forged from the concatenated annotations to publish on the Folder parent {parent.id}",
            ),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


def test_export_entity_form_annotations_on_parent_without_order(
    caplog,
    mock_arkindex_client,
    managed_entity_form_campaign,
    folder_type,
    contributor,
    process,
    base_config,
):
    parent = managed_entity_form_campaign.project.elements.get(name="A")
    first_child = managed_entity_form_campaign.project.elements.filter(image__isnull=False, parent=parent).first()
    second_child = managed_entity_form_campaign.project.elements.filter(image__isnull=False, parent=parent).last()

    # Deleting other parent elements to avoid a spam of logs
    managed_entity_form_campaign.project.elements.exclude(id=parent.id).filter(type=folder_type).delete()

    first_entities = [
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
    second_entities = [
        {
            "value": "Ron",
            "entity_type": "first_name",
            "instruction": "First name",
            "type_id": "type2id",  # For debug only
            "offset": 49,  # For debug only
        },
        {
            "value": "Weasley",
            "entity_type": "last_name",
            "instruction": "Last name",
            "type_id": "type3id",  # For debug only
            "offset": 53,  # For debug only
        },
        {
            "value": "Ottery St Catchpole",
            "entity_type": "city",
            "instruction": "City",
            "type_id": "type1id",  # For debug only
            "offset": 29,  # For debug only
        },
    ]
    for child, entities in zip([first_child, second_child], [first_entities, second_entities]):
        task = managed_entity_form_campaign.tasks.create(element=child)
        user_task = task.user_tasks.create(user=contributor.user, state=TaskState.Validated)
        Annotation.objects.create(user_task=user_task, value={"values": entities})

    ark_transcription_id = str(uuid.uuid4())
    mock_arkindex_client.add_response(
        "CreateTranscription",
        {"id": ark_transcription_id},
        # Default alphabetical order is "city", "first_name", "last_name"
        body={
            "text": "Little Whinging Harry Potter\nOttery St Catchpole Ron Weasley",
            "worker_run_id": WORKER_RUN_ID,
            "confidence": 1,
        },
        id=parent.provider_object_id,
    )

    sorted_first_entities = sorted(
        first_entities, key=lambda entity: ["city", "first_name", "last_name"].index(entity["entity_type"])
    )
    sorted_second_entities = sorted(
        second_entities, key=lambda entity: ["city", "first_name", "last_name"].index(entity["entity_type"])
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
                for entity in sorted_first_entities + sorted_second_entities
            ],
        },
    )

    # Removing the configured order, we'll order entities alphabetically by default
    base_config.pop("entities_order")
    export_process = ArkindexExport.from_configuration(process, base_config)
    export_process.run()

    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == [
            (logging.INFO, 'Using campaign "Campaign"'),
            (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
            (
                logging.INFO,
                "Starting to export entities in concatenated transcriptions on the chosen parent type Folder",
            ),
            (
                logging.INFO,
                f"Successfully published the transcription forged from 2 concatenated annotations to publish on the Folder parent {parent.id}",
            ),
            (
                logging.INFO,
                f"Successfully published and linked 6 entities with the transcription forged from the concatenated annotations to publish on the Folder parent {parent.id}",
            ),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


def test_export_entity_form_annotations_on_parent_with_empty_line(
    caplog,
    mock_arkindex_client,
    managed_entity_form_campaign,
    folder_type,
    contributor,
    process,
    base_config,
):
    parent = managed_entity_form_campaign.project.elements.get(name="A")
    first_child = managed_entity_form_campaign.project.elements.filter(image__isnull=False, parent=parent).first()
    second_child = managed_entity_form_campaign.project.elements.filter(image__isnull=False, parent=parent).last()
    third_child = Element.objects.get(name="Page 15")
    third_child.parent = parent
    third_child.save()

    # Deleting other parent elements to avoid a spam of logs
    managed_entity_form_campaign.project.elements.exclude(id=parent.id).filter(type=folder_type).delete()

    first_entities = [
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
    second_entities = [
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
    third_entities = [
        {
            "value": "Ron",
            "entity_type": "first_name",
            "instruction": "First name",
            "type_id": "type2id",  # For debug only
            "offset": 31,  # For debug only
        },
        {
            "value": "Weasley",
            "entity_type": "last_name",
            "instruction": "Last name",
            "type_id": "type3id",  # For debug only
            "offset": 35,  # For debug only
        },
        {
            "value": "Ottery St Catchpole",
            "entity_type": "city",
            "instruction": "City",
            "type_id": "type1id",  # For debug only
            "offset": 43,  # For debug only
        },
    ]
    for child, entities in zip(
        [first_child, second_child, third_child], [first_entities, second_entities, third_entities]
    ):
        task = managed_entity_form_campaign.tasks.create(element=child)
        user_task = task.user_tasks.create(user=contributor.user, state=TaskState.Validated)
        Annotation.objects.create(user_task=user_task, value={"values": entities})

    ark_transcription_id = str(uuid.uuid4())
    mock_arkindex_client.add_response(
        "CreateTranscription",
        {"id": ark_transcription_id},
        body={
            "text": "Harry Potter Little Whinging\n∅\nRon Weasley Ottery St Catchpole",
            "worker_run_id": WORKER_RUN_ID,
            "confidence": 1,
        },
        id=parent.provider_object_id,
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
                for entity in first_entities + third_entities
            ],
        },
    )

    export_process = ArkindexExport.from_configuration(process, base_config)
    export_process.run()

    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == [
            (logging.INFO, 'Using campaign "Campaign"'),
            (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
            (
                logging.INFO,
                "Starting to export entities in concatenated transcriptions on the chosen parent type Folder",
            ),
            (
                logging.INFO,
                f"Successfully published the transcription forged from 3 concatenated annotations to publish on the Folder parent {parent.id}",
            ),
            (
                logging.INFO,
                f"Successfully published and linked 6 entities with the transcription forged from the concatenated annotations to publish on the Folder parent {parent.id}",
            ),
            (
                logging.INFO,
                f"Skipped 3 empty entities from the concatenated annotations to publish on the Folder parent {parent.id}",
            ),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


@pytest.mark.parametrize("state", [TaskState.Annotated, TaskState.Validated])
def test_export_entity_form_annotations_on_parent(
    caplog,
    mock_arkindex_client,
    state,
    managed_entity_form_campaign,
    folder_type,
    contributor,
    process,
    base_config,
):
    parent = managed_entity_form_campaign.project.elements.get(name="A")
    first_child = managed_entity_form_campaign.project.elements.filter(image__isnull=False, parent=parent).first()
    second_child = managed_entity_form_campaign.project.elements.filter(image__isnull=False, parent=parent).last()

    # Deleting other parent elements to avoid a spam of logs
    managed_entity_form_campaign.project.elements.exclude(id=parent.id).filter(type=folder_type).delete()

    first_entities = [
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
    second_entities = [
        {
            "value": "Ron",
            "entity_type": "first_name",
            "instruction": "First name",
            "type_id": "type2id",  # For debug only
            "offset": 29,  # For debug only
        },
        {
            "value": "Weasley",
            "entity_type": "last_name",
            "instruction": "Last name",
            "type_id": "type3id",  # For debug only
            "offset": 33,  # For debug only
        },
        {
            "value": "Ottery St Catchpole",
            "entity_type": "city",
            "instruction": "City",
            "type_id": "type1id",  # For debug only
            "offset": 41,  # For debug only
        },
    ]
    for child, entities in zip([first_child, second_child], [first_entities, second_entities]):
        task = managed_entity_form_campaign.tasks.create(element=child)
        user_task = task.user_tasks.create(user=contributor.user, state=state)
        Annotation.objects.create(user_task=user_task, value={"values": entities})

    ark_transcription_id = str(uuid.uuid4())
    mock_arkindex_client.add_response(
        "CreateTranscription",
        {"id": ark_transcription_id},
        body={
            "text": "Harry Potter Little Whinging\nRon Weasley Ottery St Catchpole",
            "worker_run_id": WORKER_RUN_ID,
            "confidence": 1,
        },
        id=parent.provider_object_id,
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
                for entity in first_entities + second_entities
            ],
        },
    )

    export_process = ArkindexExport.from_configuration(process, base_config)
    export_process.run()

    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == [
            (logging.INFO, 'Using campaign "Campaign"'),
            (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
            (
                logging.INFO,
                "Starting to export entities in concatenated transcriptions on the chosen parent type Folder",
            ),
            (
                logging.INFO,
                f"Successfully published the transcription forged from 2 concatenated annotations to publish on the Folder parent {parent.id}",
            ),
            (
                logging.INFO,
                f"Successfully published and linked 6 entities with the transcription forged from the concatenated annotations to publish on the Folder parent {parent.id}",
            ),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )
