import logging
import random
import uuid

import pytest

from callico.annotations.models import Annotation, Task, TaskState, TaskUser
from callico.process.arkindex.exports import ARKINDEX_PUBLISH_METHODS, ArkindexExport
from callico.projects.models import CampaignMode, Provider, ProviderType

pytestmark = pytest.mark.django_db


@pytest.fixture
def base_config(arkindex_provider, managed_campaign):
    return {
        "arkindex_provider": str(arkindex_provider.id),
        "campaign": str(managed_campaign.id),
        "worker_run": str(uuid.uuid4()),
        "corpus": str(managed_campaign.project.provider_object_id),
        "exported_states": [TaskState.Annotated, TaskState.Validated],
    }


@pytest.mark.parametrize("mode", [CampaignMode.Classification])
def test_export_arkindex_annotations_use_raw_publication_error(
    caplog, mock_arkindex_client, managed_campaign, mode, process, base_config
):
    managed_campaign.mode = mode
    managed_campaign.save()

    with pytest.raises(
        Exception,
        match="Duplicated ML classes are not allowed from the same worker run in Arkindex. Annotations must always be grouped before export.",
    ):
        export_process = ArkindexExport.from_configuration(process, {**base_config, "use_raw_publication": True})
        export_process.run()

    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == [
            (logging.INFO, 'Using campaign "Campaign"'),
            (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


@pytest.mark.parametrize("api_error", [True, False])
@pytest.mark.parametrize("mode", [CampaignMode.Classification])
def test_export_arkindex_annotations_no_classes(
    caplog, mock_arkindex_client, managed_campaign, api_error, mode, process, base_config
):
    managed_campaign.mode = mode
    managed_campaign.save()
    project = managed_campaign.project
    project.classes.create(name="dog", provider=project.provider, provider_object_id=str(uuid.uuid4()))
    another_provider = Provider.objects.create(
        name="Another instance",
        type=ProviderType.Arkindex,
        api_url="https://foreign.arkindex.com/api/v1",
        api_token="987654321",
    )
    wolf = project.classes.create(name="wolf", provider=another_provider, provider_object_id=str(uuid.uuid4()))

    expected_logs = [
        (logging.INFO, 'Using campaign "Campaign"'),
        (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
    ]
    if api_error:
        mock_arkindex_client.add_error_response(
            "ListCorpusMLClasses",
            status_code=500,
            id=project.provider_object_id,
        )
        expected_logs.append(
            (
                logging.ERROR,
                f"Failed to retrieve available classes on the Arkindex corpus {project.provider_object_id}: 500 - Mock error response",
            )
        )
    else:
        mock_arkindex_client.add_response(
            "ListCorpusMLClasses",
            [
                {"id": str(uuid.uuid4()), "name": "Cat"},
                # Exists on the project but not for the correct provider
                {"id": wolf.provider_object_id, "name": "Wolf"},
            ],
            id=project.provider_object_id,
        )

    with pytest.raises(
        Exception,
        match=f"No available matching class on the Arkindex corpus {project.provider_object_id}, publication aborted",
    ):
        export_process = ArkindexExport.from_configuration(process, base_config)
        export_process.run()

    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == expected_logs
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


@pytest.mark.parametrize("api_error", [True, False])
@pytest.mark.parametrize("mode", [CampaignMode.ElementGroup, CampaignMode.Elements])
def test_export_arkindex_annotations_no_element_types(
    caplog, mock_arkindex_client, managed_campaign, api_error, mode, process, base_config
):
    managed_campaign.mode = mode
    managed_campaign.save()
    project = managed_campaign.project
    another_provider = Provider.objects.create(
        name="Another instance",
        type=ProviderType.Arkindex,
        api_url="https://foreign.arkindex.com/api/v1",
        api_token="987654321",
    )
    word = project.types.create(name="Word", provider=another_provider, provider_object_id="word")

    expected_logs = [
        (logging.INFO, 'Using campaign "Campaign"'),
        (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
    ]
    if api_error:
        mock_arkindex_client.add_error_response(
            "RetrieveCorpus",
            status_code=400,
            id=project.provider_object_id,
        )
        expected_logs.append(
            (
                logging.ERROR,
                f"Failed to retrieve available types on the Arkindex corpus {project.provider_object_id}: 400 - Mock error response",
            )
        )
    else:
        mock_arkindex_client.add_response(
            "RetrieveCorpus",
            {
                "types": [
                    {"slug": "another_type"},
                    # Exists on the project but not for the correct provider
                    {"slug": word.provider_object_id},
                ]
            },
            id=project.provider_object_id,
        )

    with pytest.raises(
        Exception,
        match=f"No available matching type on the Arkindex corpus {project.provider_object_id}, publication aborted",
    ):
        export_process = ArkindexExport.from_configuration(process, base_config)
        export_process.run()

    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == expected_logs
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


@pytest.mark.parametrize("configuration", [{}, {"group_type": "cafecafe-cafe-cafe-cafe-cafecafecafe"}])
@pytest.mark.parametrize("mode", [CampaignMode.ElementGroup])
def test_export_arkindex_annotations_no_configured_group_type(
    caplog, mock_arkindex_client, managed_campaign, configuration, mode, process, base_config
):
    managed_campaign.mode = mode
    managed_campaign.configuration = configuration
    managed_campaign.save()
    project = managed_campaign.project
    article = project.types.create(name="Article", provider=project.provider, provider_object_id="article")
    mock_arkindex_client.add_response(
        "RetrieveCorpus",
        {"types": [{"slug": article.provider_object_id}]},
        id=managed_campaign.project.provider_object_id,
    )

    with pytest.raises(
        Exception,
        match=f"The group type defined in the campaign configuration doesn't exist on the Arkindex corpus {project.provider_object_id}, publication aborted",
    ):
        export_process = ArkindexExport.from_configuration(process, base_config)
        export_process.run()

    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == [
            (logging.INFO, 'Using campaign "Campaign"'),
            (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


def quick_setup_for_specific_campaigns(mode, campaign, mock_arkindex_client):
    if mode == CampaignMode.Classification:
        project = campaign.project
        dog = project.classes.create(name="dog", provider=project.provider, provider_object_id=str(uuid.uuid4()))
        mock_arkindex_client.add_response(
            "ListCorpusMLClasses",
            [{"id": dog.provider_object_id, "name": "Dog"}],
            id=project.provider_object_id,
        )

    if mode in [CampaignMode.ElementGroup, CampaignMode.Elements]:
        project = campaign.project
        line = project.types.get(name="Line")
        types = [{"slug": line.provider_object_id}]

        if mode == CampaignMode.ElementGroup:
            article = project.types.create(name="Article", provider=project.provider, provider_object_id="article")
            campaign.configuration["group_type"] = str(article.id)
            types.append({"slug": article.provider_object_id})

        mock_arkindex_client.add_response(
            "RetrieveCorpus",
            {"types": types},
            id=project.provider_object_id,
        )

    if mode in [CampaignMode.Entity, CampaignMode.EntityForm]:
        mock_arkindex_client.add_response(
            "ListCorpusEntityTypes",
            id=campaign.project.provider_object_id,
            response=[
                {"name": "city", "color": "ffffff", "id": "type1id"},
                {"name": "birthday", "color": "000000", "id": "type2id"},
                {"name": "person", "color": "ffffff", "id": "type3id"},
                {"name": "date", "color": "ffffff", "id": "type4id"},
            ],
        )


@pytest.mark.parametrize("mode", ARKINDEX_PUBLISH_METHODS)
def test_export_arkindex_annotations_unassigned_task(
    caplog, mock_arkindex_client, managed_campaign, mode, process, base_config
):
    quick_setup_for_specific_campaigns(mode, managed_campaign, mock_arkindex_client)

    managed_campaign.mode = mode
    managed_campaign.save()
    managed_campaign.tasks.create(element=managed_campaign.project.elements.filter(image__isnull=False).first())
    assert Task.objects.filter(campaign=managed_campaign).count() == 1
    assert TaskUser.objects.filter(task__campaign=managed_campaign).count() == 0

    # Nothing special should happen because the task isn't assigned
    export_process = ArkindexExport.from_configuration(process, base_config)
    export_process.run()

    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == [
            (logging.INFO, 'Using campaign "Campaign"'),
            (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


@pytest.mark.parametrize("mode", ARKINDEX_PUBLISH_METHODS)
@pytest.mark.parametrize("state", random.choice(list(TaskState)))
def test_export_arkindex_annotations_wrong_user_task_state(
    caplog, mock_arkindex_client, managed_campaign, mode, state, contributor, process, base_config
):
    quick_setup_for_specific_campaigns(mode, managed_campaign, mock_arkindex_client)

    managed_campaign.mode = mode
    managed_campaign.save()
    task = managed_campaign.tasks.create(element=managed_campaign.project.elements.filter(image__isnull=False).first())
    task.user_tasks.create(user=contributor.user, state=state)
    assert Task.objects.filter(campaign=managed_campaign).count() == 1
    assert TaskUser.objects.filter(task__campaign=managed_campaign).count() == 1

    # Nothing special should happen because the task assignment is in the wrong state
    export_process = ArkindexExport.from_configuration(
        process, {**base_config, "exported_states": [s for s in TaskState if s != state]}
    )
    export_process.run()

    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == [
            (logging.INFO, 'Using campaign "Campaign"'),
            (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


@pytest.mark.parametrize("mode", ARKINDEX_PUBLISH_METHODS)
def test_export_arkindex_annotations_skip_published_task(
    caplog,
    mock_arkindex_client,
    managed_campaign,
    contributor,
    new_contributor,
    mode,
    process,
    base_config,
):
    quick_setup_for_specific_campaigns(mode, managed_campaign, mock_arkindex_client)

    managed_campaign.mode = mode
    managed_campaign.save()
    task = managed_campaign.tasks.create(element=managed_campaign.project.elements.filter(image__isnull=False).first())
    user_tasks = TaskUser.objects.bulk_create(
        [TaskUser(task=task, user=user, state=TaskState.Pending) for user in [contributor.user, new_contributor]]
    )
    for index, user_task in enumerate(user_tasks):
        annotation = Annotation.objects.create(
            user_task=user_task,
            # We don't really care about the Annotation value here
            value={},
        )
        user_task.state = TaskState.Annotated
        user_task.save()

        # Mark the first annotation as published
        if index == 0:
            annotation.published = True
            annotation.save()

    export_process = ArkindexExport.from_configuration(process, base_config)
    export_process.run()

    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == [
            (logging.INFO, 'Using campaign "Campaign"'),
            (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
            (
                logging.INFO,
                f"Skipping the task {task.id} as at least one of its latest version annotations has already been published",
            ),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


@pytest.mark.parametrize("mode", ARKINDEX_PUBLISH_METHODS)
def test_export_arkindex_annotations_force_republication(
    caplog,
    mock_arkindex_client,
    managed_campaign,
    contributor,
    new_contributor,
    mode,
    process,
    base_config,
):
    quick_setup_for_specific_campaigns(mode, managed_campaign, mock_arkindex_client)

    managed_campaign.mode = mode
    managed_campaign.save()
    task = managed_campaign.tasks.create(element=managed_campaign.project.elements.filter(image__isnull=False).first())

    # Update the transcription attributes for the entity publication
    if mode == CampaignMode.Entity:
        task.element.transcription = {"id": str(uuid.uuid4()), "text": "some text"}
        task.element.save()

    user_tasks = TaskUser.objects.bulk_create(
        [TaskUser(task=task, user=user, state=TaskState.Pending) for user in [contributor.user, new_contributor]]
    )
    for index, user_task in enumerate(user_tasks):
        annotation = Annotation.objects.create(
            user_task=user_task,
            # We don't really care about the Annotation value here
            value={},
        )
        user_task.state = TaskState.Annotated
        user_task.save()

        # Mark the first annotation as published
        if index == 0:
            annotation.published = True
            annotation.save()

    export_process = ArkindexExport.from_configuration(process, {**base_config, "force_republication": True})
    export_process.run()

    assert [(level, message) for _module, level, message in caplog.record_tuples] == [
        (log["level"], log["content"]) for log in process.parsed_logs
    ]

    # Check the first common messages
    assert [
        (logging.INFO, 'Using campaign "Campaign"'),
        (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
    ] == [(log["level"], log["content"]) for log in process.parsed_logs[:-1]]
    # Check the last message that proves the task was being processed even if there were published annotations
    last_log = process.parsed_logs[-1]
    assert last_log["level"] == logging.ERROR
    assert last_log["content"].startswith(f"Skipping the task {task.id} as at least one of its last") and last_log[
        "content"
    ].endswith("annotations holds an invalid value")


@pytest.mark.parametrize("mode", ARKINDEX_PUBLISH_METHODS)
def test_export_arkindex_annotations_ignore_preview_task(
    caplog, mock_arkindex_client, managed_campaign, mode, contributor, process, base_config
):
    quick_setup_for_specific_campaigns(mode, managed_campaign, mock_arkindex_client)

    managed_campaign.mode = mode
    managed_campaign.save()
    task = managed_campaign.tasks.create(element=managed_campaign.project.elements.filter(image__isnull=False).first())
    task.user_tasks.create(user=contributor.user, state=TaskState.Annotated, is_preview=True)
    assert Task.objects.filter(campaign=managed_campaign).count() == 1
    assert TaskUser.objects.filter(task__campaign=managed_campaign).count() == 1

    export_process = ArkindexExport.from_configuration(process, base_config)
    export_process.run()

    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == [
            (logging.INFO, 'Using campaign "Campaign"'),
            (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )
