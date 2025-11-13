import logging
import re
import uuid

import pytest

from callico.process.arkindex.imports import ArkindexImport
from callico.projects.models import Element, Project

pytestmark = pytest.mark.django_db


@pytest.fixture
def base_config(project):
    return {
        "arkindex_provider": project.provider.id,
        "project_id": str(project.id),
        "types": [],
        "class_name": None,
        "elements_worker_run": {},
        "metadata": [],
        "transcriptions": [],
        "entities": [],
        "corpus": None,
        "element": None,
        "dataset": None,
        "dataset_sets": [],
    }


@pytest.mark.parametrize(
    "status_code, content, message",
    [
        (
            403,
            "Forbidden",
            'Invalid Arkindex token for provider "Arkindex test"',
        ),
        (
            404,
            "Not found",
            "Arkindex corpus (corpus_id) doesn't exist or you don't have the reading rights on the corpus",
        ),
        (
            400,
            "Bad request",
            "Failed retrieving corpus: 400 - Bad request",
        ),
    ],
)
def test_arkindex_import_corpus_api_error(
    mock_arkindex_client, base_config, project, process, status_code, content, message
):
    message = message.replace("corpus_id", project.provider_object_id)

    mock_arkindex_client.add_error_response(
        "RetrieveCorpus",
        status_code=status_code,
        content=content,
        id=project.provider_object_id,
    )

    config = {**base_config, "corpus": project.provider_object_id}
    with pytest.raises(Exception, match=re.escape(message)):
        import_process = ArkindexImport.from_configuration(process, config)
        import_process.run(element_id=config["element"], corpus_id=config["corpus"])


@pytest.mark.parametrize(
    "status_code, content, message",
    [
        (
            403,
            "Forbidden",
            'Invalid Arkindex token for provider "Arkindex test"',
        ),
        (
            404,
            "Not found",
            "Arkindex element (element_id) doesn't exist or you don't have the reading rights on the corpus",
        ),
        (
            400,
            "Bad request",
            "Failed retrieving element: 400 - Bad request",
        ),
    ],
)
def test_arkindex_import_element_api_error(mock_arkindex_client, base_config, process, status_code, content, message):
    element_id = str(uuid.uuid4())
    message = message.replace("element_id", element_id)

    mock_arkindex_client.add_error_response(
        "RetrieveElement",
        status_code=status_code,
        content=content,
        id=element_id,
    )

    config = {**base_config, "element": element_id}
    with pytest.raises(Exception, match=re.escape(message)):
        import_process = ArkindexImport.from_configuration(process, config)
        import_process.run(element_id=config["element"], corpus_id=config["corpus"])


def test_arkindex_import_element_error(mock_arkindex_client, base_config, process):
    element_id = str(uuid.uuid4())

    mock_arkindex_client.add_response(
        "RetrieveElement",
        {
            "id": element_id,
            "name": "Volume",
            "type": "volume",
            "zone": None,
            "classifications": [],
            "corpus": {"id": str(uuid.uuid4())},
        },
        id=element_id,
    )

    config = {**base_config, "element": element_id}
    with pytest.raises(Exception, match="The element provided in the configuration is not part of the project corpus"):
        import_process = ArkindexImport.from_configuration(process, config)
        import_process.run(element_id=config["element"], corpus_id=config["corpus"])


def test_arkindex_import_error(mock_arkindex_client, base_config, project, process):
    volume_id = str(uuid.uuid4())

    mock_arkindex_client.add_response("RetrieveCorpus", {"name": "A corpus"}, id=project.provider_object_id)
    mock_arkindex_client.add_response(
        "ListElements",
        [
            {
                "id": volume_id,
                "name": "Volume",
                "type": "volume",
                "zone": None,
                "has_children": True,
                "classes": [],
                "corpus": {"id": project.provider_object_id},
            }
        ],
        corpus=project.provider_object_id,
        top_level=True,
        with_has_children=True,
        with_classes=True,
    )
    mock_arkindex_client.add_error_response(
        "ListElementChildren",
        404,
        content="oops",
        id=volume_id,
        with_has_children=True,
        with_classes=True,
        order="position",
    )

    config = {**base_config, "corpus": project.provider_object_id}
    with pytest.raises(Exception, match="Failed creating elements: 404 - oops"):
        import_process = ArkindexImport.from_configuration(process, config)
        import_process.run(element_id=config["element"], corpus_id=config["corpus"])


def test_arkindex_import_get_type_error(mock_arkindex_client, base_config, project, process):
    element_id = str(uuid.uuid4())

    mock_arkindex_client.add_response(
        "RetrieveElement",
        id=element_id,
        response={
            "id": element_id,
            "name": "An element",
            "type": "wrong_type",
            "zone": None,
            "classifications": [],
            "worker_run": None,
            "corpus": {"id": project.provider_object_id},
        },
    )

    config = {**base_config, "element": element_id}
    with pytest.raises(
        Exception,
        match=re.escape(
            'Failed retrieving the type "wrong_type" to link to the element, you should update your project in the admin to launch a new task to retrieve extra information (types included) from Arkindex'
        ),
    ):
        import_process = ArkindexImport.from_configuration(process, config)
        import_process.run(element_id=config["element"], corpus_id=config["corpus"])


def test_arkindex_import_clone_existing_element_from_another_project(
    mock_arkindex_client, base_config, project, process
):
    """An element that was imported on a project can be imported in another project.
    In that case, it should still be referenced in the first project and duplicated in the other project.
    """
    volume_id = str(uuid.uuid4())

    # Creating an element at pos 0 in a project
    existing_project = Project.objects.create(
        name="Existing project",
        provider=project.provider,
        provider_object_id=project.provider_object_id,
    )
    volume_type = existing_project.types.create(name="Volume")
    existing_project.elements.create(
        name="Volume",
        type=volume_type,
        provider=existing_project.provider,
        provider_object_id=volume_id,
        order=0,
    )
    # Creating an element at pos 0 in another project
    other_volume_id = str(uuid.uuid4())
    project.elements.create(
        name="Another volume at position 0",
        type=volume_type,
        provider=project.provider,
        provider_object_id=other_volume_id,
        order=0,
    )

    mock_arkindex_client.add_response(
        "RetrieveCorpus", {"name": "A corpus", "types": []}, id=project.provider_object_id
    )
    mock_arkindex_client.add_response(
        "ListElements",
        [
            {
                "id": volume_id,
                "name": "Updated volume name",
                "type": "volume",
                "zone": None,
                "has_children": False,
                "classes": [],
                "corpus": {"id": project.provider_object_id},
            }
        ],
        corpus=project.provider_object_id,
        top_level=True,
        with_has_children=True,
        with_classes=True,
    )
    mock_arkindex_client.add_response("ListCorpusMLClasses", [], id=project.provider_object_id)

    config = {**base_config, "corpus": project.provider_object_id}
    import_process = ArkindexImport.from_configuration(process, config)
    import_process.run(element_id=config["element"], corpus_id=config["corpus"])

    # Check that the element from the existing_project was properly cloned/renamed in project
    assert existing_project.elements.count() == 1
    assert list(existing_project.elements.all().values("name", "order", "provider_object_id")) == [
        {"name": "Volume", "order": 0, "provider_object_id": volume_id},
    ]
    assert project.elements.count() == 2
    assert list(project.elements.all().order_by("order").values("name", "order", "provider_object_id")) == [
        {"name": "Another volume at position 0", "order": 0, "provider_object_id": other_volume_id},
        {"name": "Updated volume name", "order": 1, "provider_object_id": volume_id},
    ]


def test_arkindex_import_from_element(caplog, arkindex_provider, mock_arkindex_client, base_config, project, process):
    """It is possible to recursively import elements from a specific Arkindex element.
    Arkindex corpus may be linked to the project or set as parameter.
    """
    element_id = str(uuid.uuid4())
    page_id = str(uuid.uuid4())

    mock_arkindex_client.add_response(
        "RetrieveElement",
        id=element_id,
        response={
            "id": element_id,
            "name": "An element",
            "type": "volume",
            "zone": None,
            "classifications": [],
            "worker_run": None,
            "corpus": {"id": project.provider_object_id},
        },
    )
    mock_arkindex_client.add_response(
        "ListElementChildren",
        id=element_id,
        with_has_children=True,
        with_classes=True,
        order="position",
        response=[
            {
                "id": page_id,
                "name": "Page",
                "type": "page",
                "zone": {
                    "polygon": [[10, 10], [20, 20], [10, 20]],
                    "image": {"url": "http://image/url/1", "width": 100, "height": 200},
                },
                "has_children": False,
                "classes": [],
                "worker_run": None,
            }
        ],
    )

    config = {**base_config, "element": element_id}
    import_process = ArkindexImport.from_configuration(process, config)
    import_process.run(element_id=config["element"], corpus_id=config["corpus"])

    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == [
            (logging.INFO, 'Using project "Test project"'),
            (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
            (logging.INFO, 'Using Arkindex element "Volume An element"'),
            (logging.INFO, 'Element "An element" processed'),
            (logging.INFO, 'Element "Page" processed'),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )

    assert list(
        Element.objects.filter(project=project, provider=arkindex_provider)
        .order_by("created")
        .values_list(
            "name",
            "type__provider_object_id",
            "parent__provider_object_id",
            "image__iiif_url",
            "polygon",
            "provider_object_id",
            "transcription",
            "text_orientation",
            "metadata",
        )
    ) == [
        (
            "An element",
            "volume",
            None,
            None,
            None,
            element_id,
            {},
            "left_to_right",
            {},
        ),
        (
            "Page",
            "page",
            element_id,
            "http://image/url/1",
            [[10, 10], [20, 20], [10, 20]],
            page_id,
            {},
            "left_to_right",
            {},
        ),
    ]
    image = Element.objects.get(name="Page", project=project).image
    assert (image.width, image.height) == (100, 200)


def test_arkindex_import_from_corpus(caplog, arkindex_provider, mock_arkindex_client, base_config, project, process):
    """It is possible to recursively import elements from an Arkindex corpus on a project.
    Arkindex corpus may be linked to the project or set as parameter.
    """
    assert project.provider == arkindex_provider
    corpus_id = str(uuid.uuid4())
    volume_id = str(uuid.uuid4())
    page_id = str(uuid.uuid4())
    empty_volume_id = str(uuid.uuid4())

    project.provider_object_id = corpus_id
    project.save()

    mock_arkindex_client.add_response(
        "RetrieveCorpus",
        id=corpus_id,
        response={"name": "A corpus", "types": []},
    )
    mock_arkindex_client.add_response(
        "ListElements",
        corpus=corpus_id,
        top_level=True,
        with_has_children=True,
        with_classes=True,
        response=[
            {
                "id": volume_id,
                "name": "Volume",
                "type": "volume",
                "zone": None,
                "has_children": True,
                "classes": [],
                "worker_run": None,
            },
            {
                "id": empty_volume_id,
                "name": "Volume 2",
                "type": "volume",
                "zone": None,
                "has_children": False,
                "classes": [],
                "worker_run": None,
            },
        ],
    )
    mock_arkindex_client.add_response(
        "ListElementChildren",
        id=volume_id,
        with_has_children=True,
        with_classes=True,
        order="position",
        response=[
            {
                "id": page_id,
                "name": "Page",
                "type": "page",
                "zone": {
                    "polygon": [[10, 10], [20, 20], [10, 20]],
                    "image": {"url": "http://image/url/2", "width": 100, "height": 200},
                },
                "has_children": False,
                "classes": [],
                "worker_run": None,
            }
        ],
    )

    config = {**base_config, "corpus": corpus_id}
    import_process = ArkindexImport.from_configuration(process, config)
    import_process.run(element_id=config["element"], corpus_id=config["corpus"])

    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == [
            (logging.INFO, 'Using project "Test project"'),
            (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
            (logging.INFO, 'Using Arkindex corpus "A corpus"'),
            (logging.INFO, 'Element "Volume" processed'),
            (logging.INFO, 'Element "Page" processed'),
            (logging.INFO, 'Element "Volume 2" processed'),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )

    assert list(
        Element.objects.filter(project=project, provider=arkindex_provider)
        .order_by("created")
        .values_list(
            "name",
            "type__provider_object_id",
            "parent__provider_object_id",
            "image__iiif_url",
            "polygon",
            "provider_object_id",
            "transcription",
            "text_orientation",
            "metadata",
        )
    ) == [
        (
            "Volume",
            "volume",
            None,
            None,
            None,
            volume_id,
            {},
            "left_to_right",
            {},
        ),
        (
            "Page",
            "page",
            volume_id,
            "http://image/url/2",
            [[10, 10], [20, 20], [10, 20]],
            page_id,
            {},
            "left_to_right",
            {},
        ),
        (
            "Volume 2",
            "volume",
            None,
            None,
            None,
            empty_volume_id,
            {},
            "left_to_right",
            {},
        ),
    ]
    image = Element.objects.get(project=project, provider_object_id=page_id).image
    assert (image.width, image.height) == (100, 200)


def test_arkindex_import_element_xor_dataset_error(base_config, project, process):
    config = {**base_config, "element": str(uuid.uuid4()), "dataset": str(uuid.uuid4())}
    with pytest.raises(
        Exception, match="Only one of dataset_id and element_id can be provided to start an Arkindex import"
    ):
        import_process = ArkindexImport.from_configuration(process, config)
        import_process.run(
            element_id=config["element"],
            corpus_id=config["corpus"],
            dataset_id=config["dataset"],
        )


@pytest.mark.parametrize(
    "status_code, content, message",
    [
        (
            403,
            "Forbidden",
            'Invalid Arkindex token for provider "Arkindex test"',
        ),
        (
            404,
            "Not found",
            "Arkindex dataset (dataset_id) doesn't exist or you don't have the reading rights on the corpus",
        ),
        (
            400,
            "Bad request",
            "Failed retrieving dataset: 400 - Bad request",
        ),
    ],
)
def test_arkindex_import_dataset_api_error(base_config, mock_arkindex_client, process, status_code, content, message):
    dataset_id = str(uuid.uuid4())
    message = message.replace("dataset_id", dataset_id)

    mock_arkindex_client.add_error_response(
        "RetrieveDataset",
        status_code=status_code,
        content=content,
        id=dataset_id,
    )

    config = {**base_config, "dataset": dataset_id}
    with pytest.raises(Exception, match=re.escape(message)):
        import_process = ArkindexImport.from_configuration(process, config)
        import_process.run(
            corpus_id=config["corpus"],
            dataset_id=config["dataset"],
        )


def test_arkindex_import_dataset_error(base_config, mock_arkindex_client, process):
    dataset_id = str(uuid.uuid4())
    config = {**base_config, "dataset": dataset_id}

    mock_arkindex_client.add_response(
        "RetrieveDataset",
        id=dataset_id,
        response={"name": "A dataset", "corpus_id": config["corpus"], "sets": []},
    )

    with pytest.raises(Exception, match="The dataset provided in the configuration is not part of the project corpus"):
        import_process = ArkindexImport.from_configuration(process, config)
        import_process.run(
            corpus_id=config["corpus"],
            dataset_id=config["dataset"],
        )


def test_arkindex_import_from_dataset(caplog, arkindex_provider, mock_arkindex_client, base_config, project, process):
    assert project.provider == arkindex_provider
    corpus_id = str(uuid.uuid4())
    dataset_id = str(uuid.uuid4())
    volume_id = str(uuid.uuid4())
    page_id = str(uuid.uuid4())
    empty_volume_id = str(uuid.uuid4())

    project.provider_object_id = corpus_id
    project.save()

    mock_arkindex_client.add_response(
        "RetrieveDataset",
        id=dataset_id,
        response={
            "name": "A dataset",
            "corpus_id": corpus_id,
            "sets": [
                {"id": str(uuid.uuid4()), "name": "train"},
                {"id": str(uuid.uuid4()), "name": "validation"},
                {"id": str(uuid.uuid4()), "name": "test"},
            ],
        },
    )
    mock_arkindex_client.add_response(
        "ListDatasetElements",
        id=dataset_id,
        response=[
            {
                "set": "train",
                "element": {
                    "id": volume_id,
                    "name": "Volume",
                    "type": "volume",
                    "zone": None,
                    "worker_run": None,
                },
            },
            {
                "set": "validation",
                "element": {
                    "id": empty_volume_id,
                    "name": "Volume 2",
                    "type": "volume",
                    "zone": None,
                    "worker_run": None,
                },
            },
        ],
    )
    mock_arkindex_client.add_response(
        "RetrieveElement",
        id=volume_id,
        response={
            "id": volume_id,
            "name": "Volume",
            "type": "volume",
            "zone": None,
            "classifications": [{"ml_class": {"name": "incident report"}}],
            "worker_run": None,
        },
    )
    mock_arkindex_client.add_response(
        "RetrieveElement",
        id=empty_volume_id,
        response={
            "id": empty_volume_id,
            "name": "Volume 2",
            "type": "volume",
            "zone": None,
            "classifications": [{"ml_class": {"name": "map"}}],
            "worker_run": None,
        },
    )
    mock_arkindex_client.add_response(
        "ListElementChildren",
        id=volume_id,
        with_has_children=True,
        with_classes=True,
        order="position",
        response=[
            {
                "id": page_id,
                "name": "Page",
                "type": "page",
                "zone": {
                    "polygon": [[10, 10], [20, 20], [10, 20]],
                    "image": {"url": "http://image/url/2", "width": 100, "height": 200},
                },
                "has_children": False,
                "classes": [],
                "worker_run": None,
            }
        ],
    )
    mock_arkindex_client.add_response(
        "ListElementChildren",
        id=empty_volume_id,
        with_has_children=True,
        with_classes=True,
        order="position",
        response=[],
    )

    config = {**base_config, "corpus": corpus_id, "dataset": dataset_id}
    import_process = ArkindexImport.from_configuration(process, config)
    import_process.run(
        corpus_id=config["corpus"],
        dataset_id=config["dataset"],
    )

    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == [
            (logging.INFO, 'Using project "Test project"'),
            (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
            (logging.INFO, 'Using Arkindex dataset "A dataset"'),
            (logging.INFO, 'Retrieving elements from Arkindex dataset "A dataset"'),
            (logging.INFO, 'Element "Volume" processed'),
            (logging.INFO, 'Element "Page" processed'),
            (logging.INFO, 'Element "Volume 2" processed'),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )

    assert list(
        Element.objects.filter(project=project, provider=arkindex_provider)
        .order_by("created")
        .values_list(
            "name",
            "type__provider_object_id",
            "parent__provider_object_id",
            "image__iiif_url",
            "polygon",
            "provider_object_id",
            "transcription",
            "text_orientation",
            "metadata",
        )
    ) == [
        (
            "Volume",
            "volume",
            None,
            None,
            None,
            volume_id,
            {},
            "left_to_right",
            {},
        ),
        (
            "Page",
            "page",
            volume_id,
            "http://image/url/2",
            [[10, 10], [20, 20], [10, 20]],
            page_id,
            {},
            "left_to_right",
            {},
        ),
        (
            "Volume 2",
            "volume",
            None,
            None,
            None,
            empty_volume_id,
            {},
            "left_to_right",
            {},
        ),
    ]
    image = Element.objects.get(project=project, provider_object_id=page_id).image
    assert (image.width, image.height) == (100, 200)
