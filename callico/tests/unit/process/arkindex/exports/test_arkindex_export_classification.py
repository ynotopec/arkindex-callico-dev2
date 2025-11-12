import logging
import uuid

import pytest

from callico.annotations.models import Annotation, TaskState, TaskUser
from callico.process.arkindex.exports import ArkindexExport
from callico.projects.models import CampaignMode, Role

pytestmark = pytest.mark.django_db

WORKER_RUN_ID = "12341234-1234-1234-1234-123412341234"


@pytest.fixture()
def managed_classification_campaign(mock_arkindex_client, managed_campaign, new_contributor):
    managed_campaign.project.memberships.create(user=new_contributor, role=Role.Contributor)

    project = managed_campaign.project
    dog = project.classes.create(name="dog", provider=project.provider, provider_object_id=str(uuid.uuid4()))
    cat = project.classes.create(name="cat", provider=project.provider, provider_object_id=str(uuid.uuid4()))
    mock_arkindex_client.add_response(
        "ListCorpusMLClasses",
        [
            {"id": dog.provider_object_id, "name": "Dog"},
            {"id": cat.provider_object_id, "name": "Cat"},
        ],
        id=project.provider_object_id,
    )
    managed_campaign.mode = CampaignMode.Classification
    managed_campaign.save()

    return managed_campaign


@pytest.fixture
def base_config(managed_classification_campaign):
    return {
        "arkindex_provider": str(managed_classification_campaign.project.provider.id),
        "campaign": str(managed_classification_campaign.id),
        "worker_run": str(WORKER_RUN_ID),
        "corpus": str(managed_classification_campaign.project.provider_object_id),
        "exported_states": [TaskState.Annotated, TaskState.Validated],
    }


@pytest.mark.parametrize(
    "annotation_value", [{"no_classification": "oops"}, {"classification": None}, {"classification": ["not a string"]}]
)
def test_export_classification_annotations_annotation_value_error(
    process,
    caplog,
    managed_classification_campaign,
    contributor,
    annotation_value,
    base_config,
):
    project = managed_classification_campaign.project
    task = managed_classification_campaign.tasks.create(element=project.elements.filter(image__isnull=False).first())
    user_task = task.user_tasks.create(user=contributor.user, state=TaskState.Validated)
    annotation = Annotation.objects.create(user_task=user_task, value=annotation_value)

    import_process = ArkindexExport.from_configuration(process, base_config)
    import_process.run()

    annotation.refresh_from_db()
    assert not annotation.published
    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == [
            (logging.INFO, 'Using campaign "Campaign"'),
            (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
            (
                logging.ERROR,
                f"Skipping the task {task.id} as at least one of its last classification annotations holds an invalid value",
            ),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


def test_export_classification_annotations_api_createclassifications_error(
    caplog,
    mock_arkindex_client,
    managed_classification_campaign,
    contributor,
    base_config,
    process,
):
    project = managed_classification_campaign.project
    task = managed_classification_campaign.tasks.create(element=project.elements.filter(image__isnull=False).first())
    user_task = task.user_tasks.create(user=contributor.user, state=TaskState.Validated)
    dog = project.classes.get(name="dog")
    annotation = Annotation.objects.create(
        user_task=user_task,
        value={"classification": str(dog.id)},
    )

    mock_arkindex_client.add_error_response(
        "CreateClassifications",
        status_code=400,
        body={
            "parent": task.element.provider_object_id,
            "worker_run_id": WORKER_RUN_ID,
            "classifications": [{"ml_class": dog.provider_object_id, "confidence": 1}],
        },
    )

    import_process = ArkindexExport.from_configuration(process, base_config)
    import_process.run()

    annotation.refresh_from_db()
    assert not annotation.published
    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == [
            (logging.INFO, 'Using campaign "Campaign"'),
            (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
            (
                logging.ERROR,
                f"Failed to publish classifications retrieved from the annotations on the task {task.id}: 400 - Mock error response",
            ),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


def test_export_classification_annotations_skip_not_allowed_classification(
    caplog,
    managed_classification_campaign,
    contributor,
    base_config,
    process,
):
    project = managed_classification_campaign.project
    task = managed_classification_campaign.tasks.create(element=project.elements.filter(image__isnull=False).first())
    user_task = task.user_tasks.create(user=contributor.user, state=TaskState.Validated)
    wolf = project.classes.create(name="wolf", provider=project.provider, provider_object_id=str(uuid.uuid4()))
    annotation = Annotation.objects.create(user_task=user_task, value={"classification": str(wolf.id)})

    import_process = ArkindexExport.from_configuration(process, base_config)
    import_process.run()

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
                f"Skipped 1 classification annotations for task {task.id} because no class matches them in the Arkindex corpus",
            ),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


def test_export_classification_annotations_with_parent_annotation(
    caplog,
    mock_arkindex_client,
    managed_classification_campaign,
    contributor,
    base_config,
    process,
):
    project = managed_classification_campaign.project
    task = managed_classification_campaign.tasks.create(element=project.elements.filter(image__isnull=False).first())
    user_task = task.user_tasks.create(user=contributor.user, state=TaskState.Validated)
    wolf = project.classes.create(name="wolf", provider=project.provider, provider_object_id=str(uuid.uuid4()))
    parent_annotation = Annotation.objects.create(
        user_task=user_task, value={"classification": str(wolf.id)}, published=True
    )
    dog = project.classes.get(name="dog")
    annotation = Annotation.objects.create(
        parent=parent_annotation, user_task=user_task, value={"classification": str(dog.id)}
    )

    mock_arkindex_client.add_response(
        "CreateClassifications",
        {"classifications": []},
        body={
            "parent": task.element.provider_object_id,
            "worker_run_id": WORKER_RUN_ID,
            "classifications": [{"ml_class": dog.provider_object_id, "confidence": 1}],
        },
    )

    import_process = ArkindexExport.from_configuration(process, base_config)
    import_process.run()

    annotation.refresh_from_db()
    assert annotation.published
    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == [
            (logging.INFO, 'Using campaign "Campaign"'),
            (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
            (logging.INFO, f"Successfully published 1 classifications with their confidence for task {task.id}"),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


def test_export_classification_annotations_multiple_same_annotations(
    caplog,
    mock_arkindex_client,
    managed_classification_campaign,
    contributor,
    new_contributor,
    base_config,
    process,
):
    project = managed_classification_campaign.project
    task = managed_classification_campaign.tasks.create(element=project.elements.filter(image__isnull=False).first())
    user_tasks = TaskUser.objects.bulk_create(
        [TaskUser(task=task, user=user, state=TaskState.Pending) for user in [contributor.user, new_contributor]]
    )
    dog = project.classes.get(name="dog")
    for user_task in user_tasks:
        Annotation.objects.create(
            user_task=user_task,
            value={"classification": str(dog.id)},
        )
        user_task.state = TaskState.Annotated
        user_task.save()

    mock_arkindex_client.add_response(
        "CreateClassifications",
        {"classifications": []},
        body={
            "parent": task.element.provider_object_id,
            "worker_run_id": WORKER_RUN_ID,
            "classifications": [{"ml_class": dog.provider_object_id, "confidence": 1}],
        },
    )

    import_process = ArkindexExport.from_configuration(process, base_config)
    import_process.run()

    assert all(annotation.published for annotation in Annotation.objects.all())
    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == [
            (logging.INFO, 'Using campaign "Campaign"'),
            (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
            (
                logging.INFO,
                f"Successfully published 1 classifications with their confidence for task {task.id}",
            ),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


def test_export_classification_annotations_multiple_differing_annotations(
    caplog,
    mock_arkindex_client,
    managed_classification_campaign,
    contributor,
    new_contributor,
    base_config,
    process,
):
    project = managed_classification_campaign.project
    task = managed_classification_campaign.tasks.create(element=project.elements.filter(image__isnull=False).first())
    TaskUser.objects.bulk_create(
        [TaskUser(task=task, user=user, state=TaskState.Pending) for user in [contributor.user, new_contributor]]
    )
    classes = list(project.classes.order_by("name").values_list("id", flat=True))
    for index, user_task in enumerate(task.user_tasks.all().order_by("-created", "id")):
        Annotation.objects.create(user_task=user_task, value={"classification": str(classes[index])})
        user_task.state = TaskState.Annotated
        user_task.save()

    mock_arkindex_client.add_response(
        "CreateClassifications",
        {"classifications": []},
        body={
            "parent": task.element.provider_object_id,
            "worker_run_id": WORKER_RUN_ID,
            "classifications": [
                {"ml_class": project.classes.get(name="cat").provider_object_id, "confidence": 0.5},
                {"ml_class": project.classes.get(name="dog").provider_object_id, "confidence": 0.5},
            ],
        },
    )

    import_process = ArkindexExport.from_configuration(process, base_config)
    import_process.run()

    assert all(annotation.published for annotation in Annotation.objects.all())
    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == [
            (logging.INFO, 'Using campaign "Campaign"'),
            (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
            (logging.INFO, f"Successfully published 2 classifications with their confidence for task {task.id}"),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


@pytest.mark.parametrize("state", [TaskState.Annotated, TaskState.Validated])
def test_export_classification_annotations_single_annotation(
    caplog,
    mock_arkindex_client,
    managed_classification_campaign,
    contributor,
    state,
    base_config,
    process,
):
    project = managed_classification_campaign.project

    task = managed_classification_campaign.tasks.create(element=project.elements.filter(image__isnull=False).first())
    user_task = task.user_tasks.create(user=contributor.user, state=state)
    dog = project.classes.get(name="dog")
    annotation = Annotation.objects.create(user_task=user_task, value={"classification": str(dog.id)})

    mock_arkindex_client.add_response(
        "CreateClassifications",
        {"classifications": []},
        body={
            "parent": task.element.provider_object_id,
            "worker_run_id": WORKER_RUN_ID,
            "classifications": [{"ml_class": dog.provider_object_id, "confidence": 1}],
        },
    )

    import_process = ArkindexExport.from_configuration(process, base_config)
    import_process.run()

    annotation.refresh_from_db()
    assert annotation.published
    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == [
            (logging.INFO, 'Using campaign "Campaign"'),
            (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
            (logging.INFO, f"Successfully published 1 classifications with their confidence for task {task.id}"),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )
