import logging
import re
import uuid

import pytest

from callico.process.arkindex.imports import ArkindexImport
from callico.projects.models import Element, Image

pytestmark = pytest.mark.django_db

worker_run_id = str(uuid.uuid4())
worker_run = {"id": worker_run_id, "summary": "Worker (abcdefgh) - Commit"}
worker_run_id_2 = str(uuid.uuid4())
worker_run_2 = {"id": worker_run_id_2, "summary": "Worker (ijklmnop) - Commit"}
dataset_id = str(uuid.uuid4())

volume_payload = {
    "id": str(uuid.uuid4()),
    "name": "Volume",
    "type": "volume",
    "zone": None,
    "has_children": True,
    "classes": [],
    "worker_run": None,
}
folder_payload = {
    "id": str(uuid.uuid4()),
    "name": "Folder",
    "type": "folder",
    "zone": None,
    "has_children": False,
    "classes": [],
    "worker_run": worker_run,
}
page1_payload = {
    "id": str(uuid.uuid4()),
    "name": "Page 1 - Fish",
    "type": "page",
    "zone": {
        "polygon": [[0, 0], [0, 105], [666, 105], [666, 0], [0, 0]],
        "image": {"url": "http://image/url/1", "width": 666, "height": 105},
    },
    "has_children": False,
    "classes": [{"ml_class": {"name": "fish"}}],
    "worker_run": None,
}
# A second page with a single line
page2_payload = {
    "id": str(uuid.uuid4()),
    "name": "Page 2 - Cat Fish",
    "type": "page",
    "zone": {
        "polygon": None,
        "image": {"url": "http://image/url/2", "width": 42, "height": 45},
    },
    "classes": [{"ml_class": {"name": "cat"}}, {"ml_class": {"name": "fish"}}],
    "has_children": True,
    "worker_run": worker_run,
}
line_payload = {
    "id": str(uuid.uuid4()),
    "name": "Line 1 - Fish",
    "type": "line",
    "zone": {
        "polygon": [[0, 0], [0, 4], [2, 4], [2, 0], [0, 0]],
        "image": {"url": "http://image/url/2", "width": 42, "height": 45},
    },
    "has_children": False,
    "classes": [{"ml_class": {"name": "fish"}}],
    "worker_run": worker_run,
}


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
        "corpus": project.provider_object_id,
        "element": None,
        "dataset": None,
        "dataset_sets": [],
    }


def prepare_default_calls(mock_arkindex_client, corpus_id):
    """ A corpus
        /     \
     Folder  Volume
             /    \
         Page 1  Page 2
                   |
                 Line
    """
    mock_arkindex_client.add_response("RetrieveCorpus", id=corpus_id, response={"name": "A corpus"})
    mock_arkindex_client.add_response(
        "ListElements",
        corpus=corpus_id,
        top_level=True,
        with_has_children=True,
        with_classes=True,
        response=[volume_payload, folder_payload],
    )
    mock_arkindex_client.add_response(
        "ListElementChildren",
        id=volume_payload["id"],
        with_has_children=True,
        with_classes=True,
        order="position",
        response=[page1_payload, page2_payload],
    )
    mock_arkindex_client.add_response(
        "ListElementChildren",
        id=folder_payload["id"],
        with_has_children=True,
        with_classes=True,
        order="position",
        response=[],
    )
    mock_arkindex_client.add_response(
        "ListElementChildren",
        id=page2_payload["id"],
        with_has_children=True,
        with_classes=True,
        order="position",
        response=[line_payload],
    )


def test_arkindex_import_filter_type_pages(
    caplog, arkindex_provider, mock_arkindex_client, base_config, project, process
):
    """Imported elements can be recursively filtered by a single type"""
    prepare_default_calls(mock_arkindex_client, project.provider_object_id)

    config = {**base_config, "types": ["page"]}
    import_process = ArkindexImport.from_configuration(process, config)
    import_process.run(element_id=config["element"], corpus_id=config["corpus"])

    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == [
            (logging.INFO, 'Using project "Test project"'),
            (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
            (logging.INFO, 'Using Arkindex corpus "A corpus"'),
            (logging.INFO, 'Element "Page 1 - Fish" processed'),
            (logging.INFO, 'Element "Page 2 - Cat Fish" processed'),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )

    assert list(
        Element.objects.filter(project=project, provider=arkindex_provider)
        .order_by("created")
        .values_list(
            "provider_object_id",
            "name",
            "type__provider_object_id",
            "parent__provider_object_id",
            "image__iiif_url",
            "polygon",
            "transcription",
            "text_orientation",
            "metadata",
            "entities",
        )
    ) == [
        (
            page1_payload["id"],
            "Page 1 - Fish",
            "page",
            None,
            "http://image/url/1",
            None,
            {},
            "left_to_right",
            {},
            [],
        ),
        (
            page2_payload["id"],
            "Page 2 - Cat Fish",
            "page",
            None,
            "http://image/url/2",
            None,
            {},
            "left_to_right",
            {},
            [],
        ),
    ]
    assert list(
        Image.objects.filter(elements__project=project)
        .order_by("created")
        .distinct()
        .values_list("iiif_url", "width", "height")
    ) == [
        ("http://image/url/1", 666, 105),
        ("http://image/url/2", 42, 45),
    ]


def test_arkindex_import_filter_type_volumes_and_lines(
    caplog, arkindex_provider, mock_arkindex_client, base_config, project, process
):
    """Imported elements can be recursively filtered by multiple types
    Hierarchical links are preserved among any levels
    """
    prepare_default_calls(mock_arkindex_client, project.provider_object_id)

    config = {**base_config, "types": ["volume", "line"]}
    import_process = ArkindexImport.from_configuration(process, config)
    import_process.run(element_id=config["element"], corpus_id=config["corpus"])

    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == [
            (logging.INFO, 'Using project "Test project"'),
            (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
            (logging.INFO, 'Using Arkindex corpus "A corpus"'),
            (logging.INFO, 'Element "Volume" processed'),
            (logging.INFO, 'Element "Line 1 - Fish" processed'),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )

    assert list(
        Element.objects.filter(project=project, provider=arkindex_provider)
        .order_by("created")
        .values_list(
            "provider_object_id",
            "name",
            "type__provider_object_id",
            "parent__provider_object_id",
            "image__iiif_url",
            "polygon",
            "transcription",
            "text_orientation",
            "metadata",
            "entities",
        )
    ) == [
        (
            volume_payload["id"],
            "Volume",
            "volume",
            None,
            None,
            None,
            {},
            "left_to_right",
            {},
            [],
        ),
        (
            line_payload["id"],
            "Line 1 - Fish",
            "line",
            volume_payload["id"],
            "http://image/url/2",
            [[0, 0], [0, 4], [2, 4], [2, 0], [0, 0]],
            {},
            "left_to_right",
            {},
            [],
        ),
    ]
    assert list(
        Image.objects.filter(elements__project=project)
        .order_by("created")
        .distinct()
        .values_list("iiif_url", "width", "height")
    ) == [("http://image/url/2", 42, 45)]


@pytest.mark.parametrize(
    "ml_class, expected",
    [
        ("cat", [(page2_payload, None)]),
        ("fish", [(page1_payload, None), (page2_payload, None), (line_payload, page2_payload)]),
    ],
)
def test_arkindex_import_filter_class(
    caplog, arkindex_provider, mock_arkindex_client, base_config, project, process, ml_class, expected
):
    """Imported elements can be filtered by class"""
    prepare_default_calls(mock_arkindex_client, project.provider_object_id)

    config = {**base_config, "class_name": ml_class}
    import_process = ArkindexImport.from_configuration(process, config)
    import_process.run(element_id=config["element"], corpus_id=config["corpus"])

    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == [
            (logging.INFO, 'Using project "Test project"'),
            (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
            (logging.INFO, 'Using Arkindex corpus "A corpus"'),
            *((logging.INFO, f"""Element "{elt['name']}" processed""") for (elt, _) in expected),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )

    assert list(
        Element.objects.filter(project=project, provider=arkindex_provider)
        .order_by("created")
        .values_list(
            "provider_object_id",
            "name",
            "type__provider_object_id",
            "parent__provider_object_id",
            "image__iiif_url",
            "polygon",
            "transcription",
            "text_orientation",
            "metadata",
            "entities",
        )
    ) == [
        (
            elt["id"],
            elt["name"],
            elt["type"],
            parent and parent["id"],
            elt["zone"] and elt["zone"]["image"]["url"],
            # Page 1 has a polygon covering the entire image so the field is set to null
            None if elt["id"] == page1_payload["id"] else elt["zone"] and elt["zone"]["polygon"],
            {},
            "left_to_right",
            {},
            [],
        )
        for elt, parent in expected
    ]
    images = list(
        Image.objects.filter(elements__project=project)
        .order_by("created")
        .distinct()
        .values_list("iiif_url", "width", "height")
    )
    if ml_class == "cat":
        assert images == [("http://image/url/2", 42, 45)]
    else:
        assert images == [("http://image/url/1", 666, 105), ("http://image/url/2", 42, 45)]


@pytest.mark.parametrize(
    "workerrun_filters, expected",
    [
        (
            {"page": worker_run_id},
            [
                (volume_payload, None),
                (page2_payload, volume_payload),
                (line_payload, page2_payload),
                (folder_payload, None),
            ],
        ),
        (
            {
                "volume": worker_run_id,
                "page": worker_run_id,
                "line": worker_run_id,
            },
            [
                (page2_payload, None),
                (line_payload, page2_payload),
                (folder_payload, None),
            ],
        ),
    ],
)
def test_arkindex_import_filter_worker_run(
    caplog, arkindex_provider, mock_arkindex_client, base_config, project, process, workerrun_filters, expected
):
    """It is possible to filter elements depending on their worker run, specified by type
    If no worker run is associated to a type, all elements of this type will be imported by default
    """
    prepare_default_calls(mock_arkindex_client, project.provider_object_id)

    config = {**base_config, "elements_worker_run": workerrun_filters}
    import_process = ArkindexImport.from_configuration(process, config)
    import_process.run(element_id=config["element"], corpus_id=config["corpus"])

    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == [
            (logging.INFO, 'Using project "Test project"'),
            (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
            (logging.INFO, 'Using Arkindex corpus "A corpus"'),
            *((logging.INFO, f"""Element "{elt['name']}" processed""") for (elt, _) in expected),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )

    assert list(
        Element.objects.filter(project=project, provider=arkindex_provider)
        .order_by("created")
        .values_list(
            "provider_object_id",
            "name",
            "type__provider_object_id",
            "parent__provider_object_id",
            "image__iiif_url",
            "polygon",
            "transcription",
            "text_orientation",
            "metadata",
            "entities",
        )
    ) == [
        (
            elt["id"],
            elt["name"],
            elt["type"],
            parent and parent["id"],
            elt["zone"] and elt["zone"]["image"]["url"],
            # Page 1 has a polygon covering the entire image so the field is set to null
            None if elt["id"] == page1_payload["id"] else elt["zone"] and elt["zone"]["polygon"],
            {},
            "left_to_right",
            {},
            [],
        )
        for elt, parent in expected
    ]
    assert list(
        Image.objects.filter(elements__project=project)
        .order_by("created")
        .distinct()
        .values_list("iiif_url", "width", "height")
    ) == [("http://image/url/2", 42, 45)]


def test_arkindex_import_from_element_using_combined_filters(
    caplog, arkindex_provider, mock_arkindex_client, base_config, project, process
):
    """It is possible to filter elements depending on their type, class and worker run. The import
    from a specific element also works, we are defining required attributes not returned by the RetrieveElement
    endpoint (e.g: worker_run_id, classes, etc) when we retrieve the element in question.
    """
    elt_payload = {
        "id": volume_payload["id"],
        "name": volume_payload["name"],
        "type": volume_payload["type"],
        "zone": None,
        "has_children": True,
        "classifications": [{"ml_class": {"name": "cat"}}],
        "worker_run": worker_run,
        "corpus": {"id": project.provider_object_id},
    }

    mock_arkindex_client.add_response(
        "RetrieveElement",
        id=volume_payload["id"],
        response=elt_payload,
    )
    mock_arkindex_client.add_response(
        "ListElementChildren",
        id=volume_payload["id"],
        with_has_children=True,
        with_classes=True,
        order="position",
        response=[page1_payload, page2_payload],
    )
    mock_arkindex_client.add_response(
        "ListElementChildren",
        id=page2_payload["id"],
        with_has_children=True,
        with_classes=True,
        order="position",
        response=[line_payload],
    )

    config = {
        **base_config,
        "element": volume_payload["id"],
        "elements_worker_run": {"page": worker_run_id},
        "types": ["volume", "page"],
        "class_name": "cat",
    }
    import_process = ArkindexImport.from_configuration(process, config)
    import_process.run(element_id=config["element"], corpus_id=config["corpus"])

    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == [
            (logging.INFO, 'Using project "Test project"'),
            (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
            (logging.INFO, 'Using Arkindex element "Volume Volume"'),
            (logging.INFO, 'Element "Volume" processed'),
            (logging.INFO, 'Element "Page 2 - Cat Fish" processed'),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )

    assert list(
        Element.objects.filter(project=project, provider=arkindex_provider)
        .order_by("created")
        .values_list(
            "provider_object_id",
            "name",
            "type__provider_object_id",
            "parent__provider_object_id",
            "image__iiif_url",
            "polygon",
            "transcription",
            "text_orientation",
            "metadata",
            "entities",
        )
    ) == [
        (
            volume_payload["id"],
            "Volume",
            "volume",
            None,
            None,
            None,
            {},
            "left_to_right",
            {},
            [],
        ),
        (
            page2_payload["id"],
            "Page 2 - Cat Fish",
            "page",
            volume_payload["id"],
            "http://image/url/2",
            None,
            {},
            "left_to_right",
            {},
            [],
        ),
    ]
    assert list(
        Image.objects.filter(elements__project=project)
        .order_by("created")
        .distinct()
        .values_list("iiif_url", "width", "height")
    ) == [("http://image/url/2", 42, 45)]


def test_arkindex_import_filter_transcriptions_api_error(
    caplog, arkindex_provider, mock_arkindex_client, base_config, project, process
):
    """Handle a potential API error while retrieving transcriptions"""
    transcription_workerrun_id = str(uuid.uuid4())

    elt_payload = {
        "id": line_payload["id"],
        "name": line_payload["name"],
        "type": line_payload["type"],
        "zone": None,
        "has_children": False,
        "classifications": [],
        "worker_run": None,
        "corpus": {"id": project.provider_object_id},
    }

    mock_arkindex_client.add_response(
        "RetrieveElement",
        id=line_payload["id"],
        response=elt_payload,
    )
    mock_arkindex_client.add_error_response(
        "ListTranscriptions",
        id=elt_payload["id"],
        status_code=500,
    )
    # The import script will always fetch children as we do not have the information
    mock_arkindex_client.add_response(
        "ListElementChildren",
        id=line_payload["id"],
        with_has_children=True,
        with_classes=True,
        order="position",
        response=[],
    )

    config = {
        **base_config,
        "element": line_payload["id"],
        "transcriptions": [transcription_workerrun_id],
    }
    import_process = ArkindexImport.from_configuration(process, config)
    import_process.run(element_id=config["element"], corpus_id=config["corpus"])

    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == [
            (logging.INFO, 'Using project "Test project"'),
            (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
            (logging.INFO, 'Using Arkindex element "Line Line 1 - Fish"'),
            (logging.INFO, 'Element "Line 1 - Fish" processed'),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )

    assert list(
        Element.objects.filter(project=project, provider=arkindex_provider)
        .order_by("created")
        .values_list(
            "provider_object_id",
            "name",
            "type__provider_object_id",
            "parent__provider_object_id",
            "image__iiif_url",
            "polygon",
            "transcription",
            "text_orientation",
            "metadata",
            "entities",
        )
    ) == [
        (
            line_payload["id"],
            "Line 1 - Fish",
            "line",
            None,
            None,
            None,
            {},
            "left_to_right",
            {},
            [],
        ),
    ]
    assert Image.objects.filter(elements__project=project).exists() is False


def test_arkindex_import_filter_transcriptions(
    caplog, arkindex_provider, mock_arkindex_client, base_config, project, process
):
    """A transcription sources filter can be added, allowing to fetch a potential transcription
    produced by one of the specified worker runs or manually annotated for each covered element.
    Only the most relevant transcription is stored.
    """
    transcription_wr_id = str(uuid.uuid4())
    second_transcription_wr_id = str(uuid.uuid4())
    relevant_transcription_id = str(uuid.uuid4())

    prepare_default_calls(mock_arkindex_client, project.provider_object_id)
    mock_arkindex_client.add_response(
        "ListTranscriptions",
        id=line_payload["id"],
        response=[
            {
                "id": relevant_transcription_id,
                "text": "Pluto 1st of his name",  # Funny name for a fish
                "confidence": 0.33,
                "orientation": "horizontal-rl",
                "worker_run": {"id": transcription_wr_id, "summary": "Worker (abcdefgh) - Commit"},
            },
            {
                "id": str(uuid.uuid4()),
                "text": "Pluto is a planet",  # Totally unrelated to our fish
                "confidence": 0.01,
                "orientation": "horizontal-rl",
                "worker_run": {"id": transcription_wr_id, "summary": "Worker (abcdefgh) - Commit"},
            },
            # Transcriptions with a null score are also supported
            {
                "id": str(uuid.uuid4()),
                "text": "A left to right text",
                "confidence": None,
                "orientation": "horizontal-lr",
                "worker_run": {"id": transcription_wr_id, "summary": "Worker (abcdefgh) - Commit"},
            },
        ],
    )

    sources = [transcription_wr_id, second_transcription_wr_id, "manual"]
    # We will import transcriptions following the preference order, first the ones produced by transcription_wr_id if any exists,
    # then the ones produced by second_transcription_wr_id if any exists and finally the ones that were manually annotated if any exists.
    for elt in (volume_payload, page1_payload, page2_payload, folder_payload):
        mock_arkindex_client.add_response(
            "ListTranscriptions",
            id=elt["id"],
            response=[
                {
                    "id": relevant_transcription_id if index == 0 else str(uuid.uuid4()),
                    "text": f"Transcription produced by {source} source",
                    "confidence": 0.99,
                    "orientation": "horizontal-rl",
                    "worker_run": {"id": transcription_wr_id, "summary": "Worker (abcdefgh) - Commit"}
                    if source != "manual"
                    else None,
                }
                for index, source in enumerate(sources)
            ],
        )
        sources = sources[1:]

    config = {
        **base_config,
        "transcriptions": [transcription_wr_id, second_transcription_wr_id, "manual"],
    }
    import_process = ArkindexImport.from_configuration(process, config)
    import_process.run(element_id=config["element"], corpus_id=config["corpus"])

    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == [
            (logging.INFO, 'Using project "Test project"'),
            (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
            (logging.INFO, 'Using Arkindex corpus "A corpus"'),
            (logging.INFO, 'Element "Volume" processed'),
            (logging.INFO, 'Element "Page 1 - Fish" processed'),
            (logging.INFO, 'Element "Page 2 - Cat Fish" processed'),
            (logging.INFO, 'Element "Line 1 - Fish" processed'),
            (logging.INFO, 'Element "Folder" processed'),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )

    assert list(
        Element.objects.filter(project=project, provider=arkindex_provider)
        .order_by("created")
        .values_list(
            "provider_object_id",
            "name",
            "type__provider_object_id",
            "parent__provider_object_id",
            "image__iiif_url",
            "polygon",
            "transcription__id",
            "transcription__text",
            "text_orientation",
            "metadata",
            "entities",
        )
    ) == [
        (
            volume_payload["id"],
            "Volume",
            "volume",
            None,
            None,
            None,
            relevant_transcription_id,
            f"Transcription produced by {transcription_wr_id} source",
            "right_to_left",
            {},
            [],
        ),
        (
            page1_payload["id"],
            "Page 1 - Fish",
            "page",
            volume_payload["id"],
            "http://image/url/1",
            None,
            relevant_transcription_id,
            f"Transcription produced by {second_transcription_wr_id} source",
            "right_to_left",
            {},
            [],
        ),
        (
            page2_payload["id"],
            "Page 2 - Cat Fish",
            "page",
            volume_payload["id"],
            "http://image/url/2",
            None,
            relevant_transcription_id,
            "Transcription produced by manual source",
            "right_to_left",
            {},
            [],
        ),
        (
            line_payload["id"],
            "Line 1 - Fish",
            "line",
            page2_payload["id"],
            "http://image/url/2",
            [[0, 0], [0, 4], [2, 4], [2, 0], [0, 0]],
            relevant_transcription_id,
            "Pluto 1st of his name",
            "right_to_left",
            {},
            [],
        ),
        (
            folder_payload["id"],
            "Folder",
            "folder",
            None,
            None,
            None,
            None,
            None,
            "left_to_right",
            {},
            [],
        ),
    ]
    assert list(
        Image.objects.filter(elements__project=project)
        .order_by("created")
        .distinct()
        .values_list("iiif_url", "width", "height")
    ) == [
        ("http://image/url/1", 666, 105),
        ("http://image/url/2", 42, 45),
    ]


def test_arkindex_import_filter_metadata_name_api_error(
    caplog, arkindex_provider, mock_arkindex_client, base_config, project, process
):
    """Handle a potential API error while retrieving element's metadata"""
    mock_arkindex_client.add_response(
        "RetrieveElement",
        id=line_payload["id"],
        response={
            **line_payload,
            "classifications": [],
            "worker_run": None,
            "corpus": {"id": project.provider_object_id},
        },
    )
    mock_arkindex_client.add_response(
        "ListElementChildren",
        id=line_payload["id"],
        with_has_children=True,
        with_classes=True,
        order="position",
        response=[],
    )
    mock_arkindex_client.add_error_response(
        "ListElementMetaData",
        id=line_payload["id"],
        load_parents=True,
        status_code=500,
    )

    config = {
        **base_config,
        "element": line_payload["id"],
        "metadata": ["any"],
    }
    import_process = ArkindexImport.from_configuration(process, config)
    import_process.run(element_id=config["element"], corpus_id=config["corpus"])

    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == [
            (logging.INFO, 'Using project "Test project"'),
            (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
            (logging.INFO, 'Using Arkindex element "Line Line 1 - Fish"'),
            (logging.INFO, 'Element "Line 1 - Fish" processed'),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )

    assert list(
        Element.objects.filter(project=project, provider=arkindex_provider)
        .order_by("created")
        .values_list(
            "provider_object_id",
            "name",
            "type__provider_object_id",
            "parent__provider_object_id",
            "image__iiif_url",
            "polygon",
            "transcription",
            "text_orientation",
            "metadata",
            "entities",
        )
    ) == [
        (
            line_payload["id"],
            "Line 1 - Fish",
            "line",
            None,
            "http://image/url/2",
            [[0, 0], [0, 4], [2, 4], [2, 0], [0, 0]],
            {},
            "left_to_right",
            {},
            [],
        ),
    ]
    assert list(
        Image.objects.filter(elements__project=project).distinct().values_list("iiif_url", "width", "height")
    ) == [("http://image/url/2", 42, 45)]


@pytest.mark.parametrize(
    "metadata, expected_page_md, expected_line_md",
    [
        (("location",), {}, {}),
        (("folio", "location"), {"folio": "page 2"}, {"folio": "line 1"}),
        (
            ("folio", "date", "words"),
            {"folio": "page 2", "date": "2000-01-01"},
            {"folio": "line 1", "date": "2000-01-01", "words": "5"},
        ),
    ],
)
def test_arkindex_import_filter_metadata_name(
    caplog,
    arkindex_provider,
    mock_arkindex_client,
    base_config,
    project,
    process,
    metadata,
    expected_page_md,
    expected_line_md,
):
    """A metadata parameter can be set to fetch and filter metadata from the API"""
    page_metadata = [
        {
            "id": str(uuid.uuid4()),
            "type": "text",
            "name": "folio",
            "value": "page 2",
            "dates": [],
            "entity": None,
            "worker_run": None,
        },
        {
            "id": str(uuid.uuid4()),
            "type": "date",
            "name": "date",
            "value": "2000-01-01",
            "dates": [
                {
                    "type": "exact",
                    "year": 2000,
                    "month": 1,
                    "day": 1,
                }
            ],
            "entity": str(uuid.uuid4()),
            "worker_run": {"id": str(uuid.uuid4()), "summary": "Worker (abcdefgh) - Commit"},
        },
    ]
    line_metadata = [
        *page_metadata,
        {
            "id": str(uuid.uuid4()),
            "type": "numerical",
            "name": "words",
            "value": 5,
            "dates": [],
            "entity": None,
            "worker_run": None,
        },
        {
            "id": str(uuid.uuid4()),
            "type": "text",
            "name": "folio",
            "value": "line 1",
            "dates": [],
            "entity": None,
            "worker_run": None,
        },
    ]
    mock_arkindex_client.add_response(
        "RetrieveElement",
        id=page2_payload["id"],
        response={
            **page2_payload,
            "classifications": [],
            "worker_run": None,
            "corpus": {"id": project.provider_object_id},
        },
    )
    mock_arkindex_client.add_response(
        "ListElementChildren",
        id=page2_payload["id"],
        with_has_children=True,
        with_classes=True,
        order="position",
        response=[line_payload],
    )
    mock_arkindex_client.add_response(
        "ListElementMetaData",
        id=page2_payload["id"],
        load_parents=True,
        response=page_metadata,
    )
    mock_arkindex_client.add_response(
        "ListElementMetaData",
        id=line_payload["id"],
        load_parents=True,
        response=line_metadata,
    )

    config = {
        **base_config,
        "element": page2_payload["id"],
        "metadata": metadata,
    }
    import_process = ArkindexImport.from_configuration(process, config)
    import_process.run(element_id=config["element"], corpus_id=config["corpus"])

    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == [
            (logging.INFO, 'Using project "Test project"'),
            (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
            (logging.INFO, 'Using Arkindex element "Page Page 2 - Cat Fish"'),
            (logging.INFO, 'Element "Page 2 - Cat Fish" processed'),
            (logging.INFO, 'Element "Line 1 - Fish" processed'),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )

    assert list(
        Element.objects.filter(project=project, provider=arkindex_provider)
        .order_by("created")
        .values_list(
            "provider_object_id",
            "name",
            "type__provider_object_id",
            "parent__provider_object_id",
            "image__iiif_url",
            "polygon",
            "transcription",
            "text_orientation",
            "metadata",
            "entities",
        )
    ) == [
        (
            page2_payload["id"],
            "Page 2 - Cat Fish",
            "page",
            None,
            "http://image/url/2",
            None,
            {},
            "left_to_right",
            expected_page_md,
            [],
        ),
        (
            line_payload["id"],
            "Line 1 - Fish",
            "line",
            page2_payload["id"],
            "http://image/url/2",
            [[0, 0], [0, 4], [2, 4], [2, 0], [0, 0]],
            {},
            "left_to_right",
            expected_line_md,
            [],
        ),
    ]
    assert list(
        Image.objects.filter(elements__project=project).distinct().values_list("iiif_url", "width", "height")
    ) == [("http://image/url/2", 42, 45)]


def test_arkindex_import_filter_entities_api_error(
    caplog, arkindex_provider, mock_arkindex_client, base_config, project, process
):
    """Handle a potential API error while retrieving transcription entities"""
    transcription_workerrun_id = str(uuid.uuid4())
    transcription_id = str(uuid.uuid4())

    entity_workerrun_id = str(uuid.uuid4())

    elt_payload = {
        "id": line_payload["id"],
        "name": line_payload["name"],
        "type": line_payload["type"],
        "zone": None,
        "has_children": False,
        "classifications": [],
        "worker_run": None,
        "corpus": {"id": project.provider_object_id},
    }

    mock_arkindex_client.add_response(
        "RetrieveElement",
        id=line_payload["id"],
        response=elt_payload,
    )
    mock_arkindex_client.add_response(
        "ListTranscriptions",
        id=elt_payload["id"],
        response=[
            {
                "id": transcription_id,
                "text": "Pluto 1st of his name",  # Funny name for a fish
                "confidence": 0.33,
                "orientation": "horizontal-rl",
                "worker_run": {"id": transcription_workerrun_id, "summary": "Worker (abcdefgh) - Commit"},
            },
        ],
    )
    mock_arkindex_client.add_error_response(
        "ListTranscriptionEntities",
        id=transcription_id,
        status_code=500,
    )
    # The import script will always fetch children as we do not have the information
    mock_arkindex_client.add_response(
        "ListElementChildren",
        id=line_payload["id"],
        with_has_children=True,
        with_classes=True,
        order="position",
        response=[],
    )

    config = {
        **base_config,
        "element": line_payload["id"],
        "transcriptions": [transcription_workerrun_id],
        "entities": [entity_workerrun_id],
    }
    import_process = ArkindexImport.from_configuration(process, config)
    import_process.run(element_id=config["element"], corpus_id=config["corpus"])

    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == [
            (logging.INFO, 'Using project "Test project"'),
            (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
            (logging.INFO, 'Using Arkindex element "Line Line 1 - Fish"'),
            (logging.INFO, 'Element "Line 1 - Fish" processed'),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )

    assert list(
        Element.objects.filter(project=project, provider=arkindex_provider)
        .order_by("created")
        .values_list(
            "provider_object_id",
            "name",
            "type__provider_object_id",
            "parent__provider_object_id",
            "image__iiif_url",
            "polygon",
            "transcription__id",
            "transcription__text",
            "text_orientation",
            "metadata",
            "entities",
        )
    ) == [
        (
            line_payload["id"],
            "Line 1 - Fish",
            "line",
            None,
            None,
            None,
            transcription_id,
            "Pluto 1st of his name",
            "right_to_left",
            {},
            [],
        ),
    ]
    assert Image.objects.filter(elements__project=project).exists() is False


def test_arkindex_import_filter_entities(
    caplog, arkindex_provider, mock_arkindex_client, base_config, project, process
):
    """An entity sources filter can be added, allowing to fetch potential entities
    produced by one of the specified worker runs or manually annotated for each covered element.
    Only the most relevant entities of the most relevant transcription are stored.
    """
    entity_ids = {line_payload["id"]: [str(uuid.uuid4()), str(uuid.uuid4())]}
    second_worker_run_id = str(uuid.uuid4())
    relevant_transcription_id = str(uuid.uuid4())

    prepare_default_calls(mock_arkindex_client, project.provider_object_id)
    mock_arkindex_client.add_response(
        "ListTranscriptions",
        id=line_payload["id"],
        response=[
            {
                "id": relevant_transcription_id,
                "text": "Pluto 1st of his name",  # Funny name for a fish
                "confidence": 0.33,
                "orientation": "horizontal-rl",
                "worker_run": worker_run,
            },
            {
                "id": str(uuid.uuid4()),
                "text": "Pluto is a planet",  # Totally unrelated to our fish
                "confidence": 0.01,
                "orientation": "horizontal-rl",
                "worker_run": worker_run,
            },
            # Transcriptions with a null score are also supported
            {
                "id": str(uuid.uuid4()),
                "text": "A left to right text",
                "confidence": None,
                "orientation": "horizontal-lr",
                "worker_run": worker_run,
            },
        ],
    )

    sources = [worker_run_id, second_worker_run_id, "manual"]
    # We will import transcriptions following the preference order, first the ones produced by worker_run_id if any exists,
    # then the ones produced by second_worker_run_id if any exists and finally the ones that were manually annotated if any exists.
    for elt in (volume_payload, page1_payload, page2_payload, folder_payload):
        mock_arkindex_client.add_response(
            "ListTranscriptions",
            id=elt["id"],
            response=[
                {
                    "id": relevant_transcription_id if index == 0 else str(uuid.uuid4()),
                    "text": f"Transcription produced by {source} source",
                    "confidence": 0.99,
                    "orientation": "horizontal-rl",
                    "worker_run": {"id": source, "summary": "Worker (abcdefgh) - Commit"}
                    if source != "manual"
                    else None,
                }
                for index, source in enumerate(sources)
            ],
        )
        if len(sources):
            source = sources[0]
            entity_id_1, entity_id_2 = str(uuid.uuid4()), str(uuid.uuid4())
            entity_ids[elt["id"]] = [entity_id_1, entity_id_2]
            mock_arkindex_client.add_response(
                "ListTranscriptionEntities",
                id=relevant_transcription_id,
                response=[
                    {
                        "entity": {
                            "id": entity_id_1,
                            "name": "Transcription",
                            "type": {"name": "text"},
                        },
                        "offset": 0,
                        "length": 13,
                        "confidence": 0.42,
                        "worker_run": {"id": source, "summary": "Worker (abcdefgh) - Commit"}
                        if source != "manual"
                        else None,
                    },
                    {
                        "entity": {
                            "id": entity_id_2,
                            "name": source,
                            "type": {"name": "source"},
                        },
                        "offset": 26,
                        "length": len(source),
                        "confidence": 0.18,
                        "worker_run": {"id": source, "summary": "Worker (abcdefgh) - Commit"}
                        if source != "manual"
                        else None,
                    },
                ],
            )
        sources = sources[1:]

    # Line transcription entities
    mock_arkindex_client.add_response(
        "ListTranscriptionEntities",
        id=relevant_transcription_id,
        response=[
            {
                "entity": {
                    "id": entity_ids[line_payload["id"]][0],
                    "name": "Pluto",
                    "type": {"name": "surname"},
                },
                "offset": 0,
                "length": 5,
                "confidence": 0.83,
                "worker_run": worker_run,
            },
            {
                "entity": {
                    "id": entity_ids[line_payload["id"]][1],
                    "name": "1",
                    "type": {"name": "number"},
                },
                "offset": 6,
                "length": 1,
                "confidence": 0.1,
                "worker_run": worker_run,
            },
        ],
    )

    config = {
        **base_config,
        "transcriptions": [worker_run_id, second_worker_run_id, "manual"],
        "entities": [worker_run_id, second_worker_run_id, "manual"],
    }
    import_process = ArkindexImport.from_configuration(process, config)
    import_process.run(element_id=config["element"], corpus_id=config["corpus"])

    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == [
            (logging.INFO, 'Using project "Test project"'),
            (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
            (logging.INFO, 'Using Arkindex corpus "A corpus"'),
            (logging.INFO, 'Element "Volume" processed'),
            (logging.INFO, 'Element "Page 1 - Fish" processed'),
            (logging.INFO, 'Element "Page 2 - Cat Fish" processed'),
            (logging.INFO, 'Element "Line 1 - Fish" processed'),
            (logging.INFO, 'Element "Folder" processed'),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )

    assert list(
        Element.objects.filter(project=project, provider=arkindex_provider)
        .order_by("created")
        .values_list(
            "provider_object_id",
            "name",
            "type__provider_object_id",
            "parent__provider_object_id",
            "image__iiif_url",
            "polygon",
            "transcription__id",
            "transcription__text",
            "text_orientation",
            "metadata",
            "entities",
        )
    ) == [
        (
            volume_payload["id"],
            "Volume",
            "volume",
            None,
            None,
            None,
            relevant_transcription_id,
            f"Transcription produced by {worker_run_id} source",
            "right_to_left",
            {},
            [
                {
                    "provider_object_id": entity_ids[volume_payload["id"]][0],
                    "name": "Transcription",
                    "type": "text",
                    "offset": 0,
                    "length": 13,
                    "confidence": 0.42,
                },
                {
                    "provider_object_id": entity_ids[volume_payload["id"]][1],
                    "name": worker_run_id,
                    "type": "source",
                    "offset": 26,
                    "length": len(worker_run_id),
                    "confidence": 0.18,
                },
            ],
        ),
        (
            page1_payload["id"],
            "Page 1 - Fish",
            "page",
            volume_payload["id"],
            "http://image/url/1",
            None,
            relevant_transcription_id,
            f"Transcription produced by {second_worker_run_id} source",
            "right_to_left",
            {},
            [
                {
                    "provider_object_id": entity_ids[page1_payload["id"]][0],
                    "name": "Transcription",
                    "type": "text",
                    "offset": 0,
                    "length": 13,
                    "confidence": 0.42,
                },
                {
                    "provider_object_id": entity_ids[page1_payload["id"]][1],
                    "name": second_worker_run_id,
                    "type": "source",
                    "offset": 26,
                    "length": len(second_worker_run_id),
                    "confidence": 0.18,
                },
            ],
        ),
        (
            page2_payload["id"],
            "Page 2 - Cat Fish",
            "page",
            volume_payload["id"],
            "http://image/url/2",
            None,
            relevant_transcription_id,
            "Transcription produced by manual source",
            "right_to_left",
            {},
            [
                {
                    "provider_object_id": entity_ids[page2_payload["id"]][0],
                    "name": "Transcription",
                    "type": "text",
                    "offset": 0,
                    "length": 13,
                    "confidence": 0.42,
                },
                {
                    "provider_object_id": entity_ids[page2_payload["id"]][1],
                    "name": "manual",
                    "type": "source",
                    "offset": 26,
                    "length": 6,
                    "confidence": 0.18,
                },
            ],
        ),
        (
            line_payload["id"],
            "Line 1 - Fish",
            "line",
            page2_payload["id"],
            "http://image/url/2",
            [[0, 0], [0, 4], [2, 4], [2, 0], [0, 0]],
            relevant_transcription_id,
            "Pluto 1st of his name",
            "right_to_left",
            {},
            [
                {
                    "provider_object_id": entity_ids[line_payload["id"]][0],
                    "name": "Pluto",
                    "type": "surname",
                    "offset": 0,
                    "length": 5,
                    "confidence": 0.83,
                },
                {
                    "provider_object_id": entity_ids[line_payload["id"]][1],
                    "name": "1",
                    "type": "number",
                    "offset": 6,
                    "length": 1,
                    "confidence": 0.1,
                },
            ],
        ),
        (
            folder_payload["id"],
            "Folder",
            "folder",
            None,
            None,
            None,
            None,
            None,
            "left_to_right",
            {},
            [],
        ),
    ]
    assert list(
        Image.objects.filter(elements__project=project)
        .order_by("created")
        .distinct()
        .values_list("iiif_url", "width", "height")
    ) == [
        ("http://image/url/1", 666, 105),
        ("http://image/url/2", 42, 45),
    ]


def test_arkindex_import_filter_dataset_set_error(base_config, mock_arkindex_client, process):
    mock_arkindex_client.add_response(
        "RetrieveDataset",
        id=dataset_id,
        response={
            "name": "A dataset",
            "corpus_id": base_config["corpus"],
            "sets": [
                {"id": str(uuid.uuid4()), "name": "train"},
                {"id": str(uuid.uuid4()), "name": "validation"},
                {"id": str(uuid.uuid4()), "name": "test"},
            ],
        },
    )
    config = {**base_config, "dataset_sets": ["unit-00", "unit-01"]}
    import_process = ArkindexImport.from_configuration(process, config)
    with pytest.raises(
        Exception,
        match=re.escape(
            "Some of the dataset sets provided in the configuration (unit-00/unit-01) are not part of dataset A dataset"
        ),
    ):
        import_process.run(
            corpus_id=base_config["corpus"],
            dataset_id=dataset_id,
        )


@pytest.mark.parametrize(
    "sets, expected_elements_key",
    [(["test"], "test"), (["validation", "test"], "test_and_validation")],
)
def test_arkindex_import_filter_dataset_set(
    base_config, mock_arkindex_client, process, project, sets, expected_elements_key
):
    # Create required project element types
    if len(sets) > 1:
        project.types.create(name="Paragraph", provider=project.provider, provider_object_id="paragraph")
        project.types.create(name="Text Line", provider=project.provider, provider_object_id="text_line")

    # Arkindex elements
    page_1 = {
        "id": str(uuid.uuid4()),
        "name": "Unit-01",
        "type": "page",
        "zone": {
            "polygon": [[0, 0], [0, 105], [666, 105], [666, 0], [0, 0]],
            "image": {"url": "http://image/url/1", "width": 666, "height": 105},
        },
        "has_children": False,
        "worker_run": worker_run_2,
    }
    page_2 = {
        "id": str(uuid.uuid4()),
        "name": "Unit-02",
        "type": "page",
        "zone": {
            "polygon": [[0, 0], [0, 105], [666, 105], [666, 0], [0, 0]],
            "image": {"url": "http://image/url/2", "width": 666, "height": 105},
        },
        "has_children": False,
        "worker_run": worker_run,
    }
    page_3 = {
        "id": str(uuid.uuid4()),
        "name": "Unit-00",
        "type": "page",
        "zone": {
            "polygon": [[0, 0], [0, 105], [666, 105], [666, 0], [0, 0]],
            "image": {"url": "http://image/url/3", "width": 666, "height": 105},
        },
        "has_children": False,
        "worker_run": worker_run,
    }
    paragraph = {
        "id": str(uuid.uuid4()),
        "name": "1",
        "type": "paragraph",
        "zone": {
            "polygon": [[0, 0], [0, 80], [20, 80], [20, 0], [0, 0]],
            "image": {"url": "http://image/url/2", "width": 666, "height": 105},
        },
        "has_children": True,
        "worker_run": None,
    }
    tl_1 = {
        "id": str(uuid.uuid4()),
        "name": "1",
        "type": "text_line",
        "zone": {
            "polygon": [[0, 0], [0, 20], [20, 20], [20, 0], [0, 0]],
            "image": {"url": "http://image/url/2", "width": 666, "height": 105},
        },
        "has_children": False,
        "worker_run": worker_run,
    }
    tl_2 = {
        "id": str(uuid.uuid4()),
        "name": "2",
        "type": "text_line",
        "zone": {
            "polygon": [[0, 0], [0, 20], [20, 20], [20, 0], [0, 0]],
            "image": {"url": "http://image/url/2", "width": 666, "height": 105},
        },
        "has_children": False,
        "worker_run": worker_run_2,
    }

    # API responses
    mock_arkindex_client.add_response(
        "RetrieveDataset",
        id=dataset_id,
        response={
            "name": "A dataset",
            "corpus_id": base_config["corpus"],
            "sets": [
                {"id": str(uuid.uuid4()), "name": "train"},
                {"id": str(uuid.uuid4()), "name": "validation"},
                {"id": str(uuid.uuid4()), "name": "test"},
            ],
        },
    )
    if len(sets) == 1:
        mock_arkindex_client.add_response(
            "ListDatasetElements",
            id=dataset_id,
            set="test",
            response=[
                {"set": "test", "element": page_3},
            ],
        )
    else:
        mock_arkindex_client.add_response(
            "ListDatasetElements",
            id=dataset_id,
            response=[
                {"set": "train", "element": page_1},
                {"set": "validation", "element": page_2},
                {"set": "test", "element": page_3},
            ],
        )
    mock_arkindex_client.add_response(
        "RetrieveElement",
        id=page_1["id"],
        response={
            **page_1,
            "classifications": [{"ml_class": {"name": "incident report"}}],
        },
    )
    mock_arkindex_client.add_response(
        "RetrieveElement",
        id=page_2["id"],
        response={**page_2, "classifications": []},
    )
    mock_arkindex_client.add_response(
        "RetrieveElement",
        id=page_3["id"],
        response={
            **page_3,
            "classifications": [{"ml_class": {"name": "internal note"}}],
        },
    )
    mock_arkindex_client.add_response(
        "ListElementChildren", id=page_1["id"], order="position", with_has_children=True, with_classes=True, response=[]
    )
    mock_arkindex_client.add_response(
        "ListElementChildren",
        id=page_2["id"],
        order="position",
        with_has_children=True,
        with_classes=True,
        response=[{**paragraph, "classes": []}],
    )
    mock_arkindex_client.add_response(
        "ListElementChildren", id=page_3["id"], order="position", with_has_children=True, with_classes=True, response=[]
    )
    mock_arkindex_client.add_response(
        "ListElementChildren",
        id=paragraph["id"],
        order="position",
        with_has_children=True,
        with_classes=True,
        response=[
            {**tl_1, "classes": [{"ml_class": {"name": "incident report"}}]},
            {**tl_2, "classes": []},
        ],
    )

    elements_and_parents = {
        "test": [(page_3, None)],
        "test_and_validation": [
            (page_2, None),
            (paragraph, page_2),
            (tl_1, paragraph),
            (tl_2, paragraph),
            (page_3, None),
        ],
    }

    config = {**base_config, "dataset": dataset_id, "dataset_sets": sets}
    import_process = ArkindexImport.from_configuration(process, config)
    import_process.run(
        corpus_id=base_config["corpus"],
        dataset_id=dataset_id,
    )

    assert list(
        Element.objects.filter(project=project, provider=project.provider.id)
        .order_by("created")
        .values_list(
            "provider_object_id",
            "name",
            "type__provider_object_id",
            "parent__provider_object_id",
            "image__iiif_url",
            "polygon",
            "transcription",
            "text_orientation",
            "metadata",
            "entities",
        )
    ) == [
        (
            elt["id"],
            elt["name"],
            elt["type"],
            parent and parent["id"],
            elt["zone"]["image"]["url"],
            # Page elements have a polygon that is the full image
            elt["zone"]["polygon"] if elt["type"] != "page" else None,
            {},
            "left_to_right",
            {},
            [],
        )
        for elt, parent in elements_and_parents[expected_elements_key]
    ]


def test_arkindex_import_from_dataset_using_combined_filters(
    caplog, arkindex_provider, mock_arkindex_client, base_config, project, process
):
    volume_details = {
        "id": volume_payload["id"],
        "name": volume_payload["name"],
        "type": volume_payload["type"],
        "zone": None,
        "classifications": [{"ml_class": {"name": "cat"}}],
        "worker_run": worker_run,
        "corpus": {"id": project.provider_object_id},
    }
    folder_details = {
        "id": folder_payload["id"],
        "name": folder_payload["name"],
        "type": folder_payload["type"],
        "zone": None,
        "classifications": [{"ml_class": {"name": "dog"}}],
        "worker_run": None,
        "corpus": {"id": project.provider_object_id},
    }
    other_volume = {
        "id": str(uuid.uuid4()),
        "name": "Another volume",
        "type": volume_payload["type"],
        "zone": None,
        "classifications": [{"ml_class": {"name": "cat"}}],
        "worker_run": worker_run,
        "corpus": {"id": project.provider_object_id},
    }

    mock_arkindex_client.add_response(
        "RetrieveDataset",
        id=dataset_id,
        response={
            "name": "A dataset",
            "corpus_id": base_config["corpus"],
            "sets": [
                {"id": str(uuid.uuid4()), "name": "training"},
                {"id": str(uuid.uuid4()), "name": "validation"},
                {"id": str(uuid.uuid4()), "name": "test"},
            ],
        },
    )
    mock_arkindex_client.add_response(
        "ListDatasetElements",
        id=dataset_id,
        response=[
            {"set": "training", "element": volume_payload},
            {"set": "validation", "element": folder_payload},
            {"set": "test", "element": other_volume},
        ],
    )
    mock_arkindex_client.add_response(
        "RetrieveElement",
        id=volume_payload["id"],
        response=volume_details,
    )
    mock_arkindex_client.add_response(
        "RetrieveElement",
        id=folder_payload["id"],
        response=folder_details,
    )
    mock_arkindex_client.add_response(
        "ListElementChildren",
        id=volume_payload["id"],
        with_has_children=True,
        with_classes=True,
        order="position",
        response=[page1_payload, page2_payload],
    )
    mock_arkindex_client.add_response(
        "ListElementChildren",
        id=page2_payload["id"],
        with_has_children=True,
        with_classes=True,
        order="position",
        response=[line_payload],
    )
    mock_arkindex_client.add_response(
        "ListElementChildren",
        id=folder_payload["id"],
        with_has_children=True,
        with_classes=True,
        order="position",
        response=[],
    )

    config = {
        **base_config,
        "dataset": dataset_id,
        "dataset_sets": ["training", "validation"],
        "elements_worker_run": {"page": worker_run_id},
        "types": ["volume", "page"],
        "class_name": "cat",
    }
    import_process = ArkindexImport.from_configuration(process, config)
    import_process.run(dataset_id=config["dataset"], corpus_id=config["corpus"])

    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == [
            (logging.INFO, 'Using project "Test project"'),
            (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
            (logging.INFO, 'Using Arkindex dataset "A dataset"'),
            (logging.INFO, 'Retrieving elements from Arkindex dataset "A dataset"'),
            (logging.INFO, 'Element "Volume" processed'),
            (logging.INFO, 'Element "Page 2 - Cat Fish" processed'),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )

    assert list(
        Element.objects.filter(project=project, provider=arkindex_provider)
        .order_by("created")
        .values_list(
            "provider_object_id",
            "name",
            "type__provider_object_id",
            "parent__provider_object_id",
            "image__iiif_url",
            "polygon",
            "transcription",
            "text_orientation",
            "metadata",
            "entities",
        )
    ) == [
        (
            volume_payload["id"],
            "Volume",
            "volume",
            None,
            None,
            None,
            {},
            "left_to_right",
            {},
            [],
        ),
        (
            page2_payload["id"],
            "Page 2 - Cat Fish",
            "page",
            volume_payload["id"],
            "http://image/url/2",
            None,
            {},
            "left_to_right",
            {},
            [],
        ),
    ]
    assert list(
        Image.objects.filter(elements__project=project)
        .order_by("created")
        .distinct()
        .values_list("iiif_url", "width", "height")
    ) == [("http://image/url/2", 42, 45)]
