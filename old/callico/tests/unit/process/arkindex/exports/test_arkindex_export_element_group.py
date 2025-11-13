import logging

import pytest

from callico.annotations.models import Annotation, TaskState, TaskUser
from callico.process.arkindex.exports import ArkindexExport
from callico.projects.models import CampaignMode, Provider, ProviderType, Role

pytestmark = pytest.mark.django_db

WORKER_RUN_ID = "12341234-1234-1234-1234-123412341234"


@pytest.fixture()
def managed_element_group_campaign(mock_arkindex_client, managed_campaign, new_contributor):
    managed_campaign.project.memberships.create(user=new_contributor, role=Role.Contributor)

    project = managed_campaign.project
    article = project.types.create(name="Article", provider=project.provider, provider_object_id="article")
    mock_arkindex_client.add_response(
        "RetrieveCorpus",
        {
            "types": [
                {"slug": article.provider_object_id},
            ]
        },
        id=project.provider_object_id,
    )
    managed_campaign.mode = CampaignMode.ElementGroup
    managed_campaign.configuration = {"group_type": str(article.id)}
    managed_campaign.save()

    return managed_campaign


@pytest.fixture()
def base_config(arkindex_provider, managed_element_group_campaign, use_raw_publication):
    return {
        "arkindex_provider": str(arkindex_provider.id),
        "campaign": str(managed_element_group_campaign.id),
        "worker_run": str(WORKER_RUN_ID),
        "corpus": managed_element_group_campaign.project.provider_object_id,
        "exported_states": [TaskState.Annotated, TaskState.Validated],
        "use_raw_publication": use_raw_publication,
    }


@pytest.mark.parametrize("annotation_value", [{"no_groups": "oops"}, {"groups": None}, {"groups": "not a list"}])
@pytest.mark.parametrize("use_raw_publication", [True, False])
def test_export_element_group_annotations_annotation_value_error(
    caplog,
    managed_element_group_campaign,
    contributor,
    annotation_value,
    use_raw_publication,
    process,
    base_config,
):
    project = managed_element_group_campaign.project
    task = managed_element_group_campaign.tasks.create(element=project.elements.filter(image__isnull=True).first())
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
                f"Skipping the task {task.id} as at least one of its last element group annotations holds an invalid value",
            ),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


@pytest.mark.parametrize("use_raw_publication", [True, False])
def test_export_element_group_annotations_api_createelement_error(
    caplog,
    mock_arkindex_client,
    managed_element_group_campaign,
    contributor,
    use_raw_publication,
    process,
    base_config,
):
    project = managed_element_group_campaign.project
    arkindex_ids = list(project.elements.filter(image__isnull=False).values_list("id", flat=True))
    task = managed_element_group_campaign.tasks.create(element=project.elements.filter(image__isnull=True).first())
    user_task = task.user_tasks.create(user=contributor.user, state=TaskState.Validated)
    annotation = Annotation.objects.create(
        user_task=user_task,
        value={"groups": [{"elements": [str(id) for id in arkindex_ids[0:3]]}]},
    )

    mock_arkindex_client.add_error_response(
        "CreateElement",
        status_code=400,
        body={
            "worker_run_id": WORKER_RUN_ID,
            "name": "1",
            "type": "article",
            "corpus": project.provider_object_id,
            "parent": task.element.provider_object_id,
            "confidence": 1,
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
                f"Failed to publish a group of elements from the annotations on the task {task.id}: 400 - Mock error response",
            ),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


@pytest.mark.parametrize("use_raw_publication", [True, False])
def test_export_element_group_annotations_api_createelementparent_error(
    caplog,
    mock_arkindex_client,
    managed_element_group_campaign,
    contributor,
    use_raw_publication,
    process,
    base_config,
):
    project = managed_element_group_campaign.project
    mapping_arkindex = list(project.elements.filter(image__isnull=False).values_list("id", "provider_object_id"))
    task = managed_element_group_campaign.tasks.create(element=project.elements.filter(image__isnull=True).first())
    user_task = task.user_tasks.create(user=contributor.user, state=TaskState.Validated)
    annotation = Annotation.objects.create(
        user_task=user_task,
        value={"groups": [{"elements": [str(callico_id) for callico_id, _arkindex_id in mapping_arkindex[0:3]]}]},
    )

    mock_arkindex_client.add_response(
        "CreateElement",
        {"id": "11111111-1111-1111-1111-111111111111"},
        body={
            "worker_run_id": WORKER_RUN_ID,
            "name": "1",
            "type": "article",
            "corpus": project.provider_object_id,
            "parent": task.element.provider_object_id,
            "confidence": 1,
        },
    )
    for _callico_id, arkindex_id in mapping_arkindex[0:3]:
        mock_arkindex_client.add_error_response(
            "CreateElementParent",
            status_code=400,
            parent="11111111-1111-1111-1111-111111111111",
            child=arkindex_id,
        )

    export_process = ArkindexExport.from_configuration(process, base_config)
    export_process.run()

    annotation.refresh_from_db()
    # The publication is unsuccessful since we were only able to create the group element on Arkindex
    assert not annotation.published
    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == [
            (logging.INFO, 'Using campaign "Campaign"'),
            (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
            (
                logging.ERROR,
                f"Failed to link an element to the group 1 from the annotations on the task {task.id}: 400 - Mock error response",
            ),
            (
                logging.ERROR,
                f"Failed to link an element to the group 1 from the annotations on the task {task.id}: 400 - Mock error response",
            ),
            (
                logging.ERROR,
                f"Failed to link an element to the group 1 from the annotations on the task {task.id}: 400 - Mock error response",
            ),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


@pytest.mark.parametrize("use_raw_publication", [True, False])
def test_export_element_group_annotations_skip_empty_groups(
    caplog,
    managed_element_group_campaign,
    contributor,
    use_raw_publication,
    process,
    base_config,
):
    project = managed_element_group_campaign.project
    task = managed_element_group_campaign.tasks.create(element=project.elements.filter(image__isnull=True).first())
    user_task = task.user_tasks.create(user=contributor.user, state=TaskState.Validated)
    annotation = Annotation.objects.create(
        user_task=user_task,
        value={"groups": [{"elements": []}]},
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
                f"Skipped 1 groups of elements from the annotations on the task {task.id} that were either empty or only containing elements from another Arkindex provider",
            ),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


@pytest.mark.parametrize("use_raw_publication", [True, False])
def test_export_element_group_annotations_skip_element_from_another_provider(
    caplog,
    managed_element_group_campaign,
    contributor,
    use_raw_publication,
    process,
    base_config,
):
    project = managed_element_group_campaign.project
    selected_element = project.elements.filter(image__isnull=False).first()
    selected_element.provider = Provider.objects.create(
        name="Another provider",
        type=ProviderType.Arkindex,
        api_url="https://foreign.arkindex.com/api/v1",
        api_token="987654321",
    )
    selected_element.save()
    assert selected_element.provider != project.provider
    task = managed_element_group_campaign.tasks.create(element=project.elements.filter(image__isnull=True).first())
    user_task = task.user_tasks.create(user=contributor.user, state=TaskState.Validated)
    annotation = Annotation.objects.create(
        user_task=user_task,
        value={"groups": [{"elements": [str(selected_element.id)]}]},
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
                f"Skipped 1 groups of elements from the annotations on the task {task.id} that were either empty or only containing elements from another Arkindex provider",
            ),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


@pytest.mark.parametrize("use_raw_publication", [True, False])
def test_export_element_group_annotations_nothing_annotated(
    caplog,
    managed_element_group_campaign,
    contributor,
    use_raw_publication,
    process,
    base_config,
):
    project = managed_element_group_campaign.project
    task = managed_element_group_campaign.tasks.create(element=project.elements.filter(image__isnull=True).first())
    user_task = task.user_tasks.create(user=contributor.user, state=TaskState.Validated)
    annotation = Annotation.objects.create(user_task=user_task, value={"groups": []})

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
def test_export_element_group_annotations_with_parent_annotation(
    caplog,
    mock_arkindex_client,
    managed_element_group_campaign,
    contributor,
    use_raw_publication,
    process,
    base_config,
):
    project = managed_element_group_campaign.project
    mapping_arkindex = list(project.elements.filter(image__isnull=False).values_list("id", "provider_object_id"))
    task = managed_element_group_campaign.tasks.create(element=project.elements.filter(image__isnull=True).first())
    user_task = task.user_tasks.create(user=contributor.user, state=TaskState.Validated)
    parent_annotation = Annotation.objects.create(
        user_task=user_task,
        value={"groups": [{"elements": [str(callico_id) for callico_id, _arkindex_id in mapping_arkindex[0:1]]}]},
        published=True,
    )
    annotation = Annotation.objects.create(
        parent=parent_annotation,
        user_task=user_task,
        value={"groups": [{"elements": [str(callico_id) for callico_id, _arkindex_id in mapping_arkindex[0:3]]}]},
    )

    mock_arkindex_client.add_response(
        "CreateElement",
        {"id": "11111111-1111-1111-1111-111111111111"},
        body={
            "worker_run_id": WORKER_RUN_ID,
            "name": "1",
            "type": "article",
            "corpus": project.provider_object_id,
            "parent": task.element.provider_object_id,
            "confidence": 1,
        },
    )
    for _callico_id, arkindex_id in mapping_arkindex[0:3]:
        mock_arkindex_client.add_response(
            "CreateElementParent",
            {},
            parent="11111111-1111-1111-1111-111111111111",
            child=arkindex_id,
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
                f"Successfully published the group 1 and linked 3 elements to it from the annotations on the task {task.id}",
            ),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


@pytest.mark.parametrize("use_raw_publication", [True, False])
def test_export_element_group_annotations_multiple_same_annotations(
    caplog,
    mock_arkindex_client,
    managed_element_group_campaign,
    contributor,
    new_contributor,
    use_raw_publication,
    process,
    base_config,
):
    project = managed_element_group_campaign.project
    mapping_arkindex = list(project.elements.filter(image__isnull=False).values_list("id", "provider_object_id"))
    task = managed_element_group_campaign.tasks.create(element=project.elements.filter(image__isnull=True).first())
    user_tasks = TaskUser.objects.bulk_create(
        [TaskUser(task=task, user=user, state=TaskState.Pending) for user in [contributor.user, new_contributor]]
    )
    for user_task in user_tasks:
        Annotation.objects.create(
            user_task=user_task,
            value={"groups": [{"elements": [str(callico_id) for callico_id, _arkindex_id in mapping_arkindex[0:3]]}]},
        )
        user_task.state = TaskState.Annotated
        user_task.save()

    nb_publications = 1 if not use_raw_publication else len(user_tasks)
    for i in range(nb_publications):
        mock_arkindex_client.add_response(
            "CreateElement",
            {"id": "11111111-1111-1111-1111-111111111111"},
            body={
                "worker_run_id": WORKER_RUN_ID,
                "name": str(i + 1),
                "type": "article",
                "corpus": project.provider_object_id,
                "parent": task.element.provider_object_id,
                "confidence": 1,
            },
        )
        for _callico_id, arkindex_id in mapping_arkindex[0:3]:
            mock_arkindex_client.add_response(
                "CreateElementParent",
                {},
                parent="11111111-1111-1111-1111-111111111111",
                child=arkindex_id,
            )

    export_process = ArkindexExport.from_configuration(process, base_config)
    export_process.run()

    assert all(annotation.published for annotation in Annotation.objects.all())
    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == [
            (logging.INFO, 'Using campaign "Campaign"'),
            (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
        ]
        + [
            (
                logging.INFO,
                f"Successfully published the group {i+1} and linked 3 elements to it from the annotations on the task {task.id}",
            )
            for i in range(nb_publications)
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


@pytest.mark.parametrize("use_raw_publication", [True, False])
def test_export_element_group_annotations_multiple_differing_annotations(
    caplog,
    mock_arkindex_client,
    managed_element_group_campaign,
    contributor,
    new_contributor,
    use_raw_publication,
    process,
    base_config,
):
    project = managed_element_group_campaign.project
    mapping_arkindex = list(project.elements.filter(image__isnull=False).values_list("id", "provider_object_id"))
    task = managed_element_group_campaign.tasks.create(element=project.elements.filter(image__isnull=True).first())
    TaskUser.objects.bulk_create(
        [TaskUser(task=task, user=user, state=TaskState.Pending) for user in [contributor.user, new_contributor]]
    )
    elements_groups = [
        [str(callico_id) for callico_id, _arkindex_id in mapping_arkindex[0:3]],
        [str(callico_id) for callico_id, _arkindex_id in mapping_arkindex[3:5]],
    ]
    for index, user_task in enumerate(task.user_tasks.all().order_by("-created", "id")):
        Annotation.objects.create(
            user_task=user_task,
            value={"groups": [{"elements": elements_groups[index]}]},
        )
        user_task.state = TaskState.Annotated
        user_task.save()

    parent_ids = ["11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"]
    confidence = 0.5 if not use_raw_publication else 1
    for index in range(0, 2):
        mock_arkindex_client.add_response(
            "CreateElement",
            {"id": parent_ids[index]},
            body={
                "worker_run_id": WORKER_RUN_ID,
                "name": str(index + 1),
                "type": "article",
                "corpus": project.provider_object_id,
                "parent": task.element.provider_object_id,
                "confidence": confidence,
            },
        )

    for index, (_id, arkindex_id) in enumerate(mapping_arkindex[0:5]):
        mock_arkindex_client.add_response(
            "CreateElementParent",
            {},
            parent=parent_ids[0] if index < 3 else parent_ids[1],
            child=arkindex_id,
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
                f"Successfully published the group 1 and linked 3 elements to it from the annotations on the task {task.id}",
            ),
            (
                logging.INFO,
                f"Successfully published the group 2 and linked 2 elements to it from the annotations on the task {task.id}",
            ),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )


@pytest.mark.parametrize("state", [TaskState.Annotated, TaskState.Validated])
@pytest.mark.parametrize("use_raw_publication", [True, False])
def test_export_element_group_annotations_single_annotation(
    caplog,
    mock_arkindex_client,
    managed_element_group_campaign,
    contributor,
    state,
    use_raw_publication,
    process,
    base_config,
):
    project = managed_element_group_campaign.project

    mapping_arkindex = list(project.elements.filter(image__isnull=False).values_list("id", "provider_object_id"))
    task = managed_element_group_campaign.tasks.create(element=project.elements.filter(image__isnull=True).first())
    user_task = task.user_tasks.create(user=contributor.user, state=state)
    annotation = Annotation.objects.create(
        user_task=user_task,
        value={"groups": [{"elements": [str(callico_id) for callico_id, _arkindex_id in mapping_arkindex[0:3]]}]},
    )

    mock_arkindex_client.add_response(
        "CreateElement",
        {"id": "11111111-1111-1111-1111-111111111111"},
        body={
            "worker_run_id": WORKER_RUN_ID,
            "name": "1",
            "type": "article",
            "corpus": project.provider_object_id,
            "parent": task.element.provider_object_id,
            "confidence": 1,
        },
    )
    for _callico_id, arkindex_id in mapping_arkindex[0:3]:
        mock_arkindex_client.add_response(
            "CreateElementParent",
            {},
            parent="11111111-1111-1111-1111-111111111111",
            child=arkindex_id,
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
                f"Successfully published the group 1 and linked 3 elements to it from the annotations on the task {task.id}",
            ),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )
