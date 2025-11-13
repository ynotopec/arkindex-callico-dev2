import re
import uuid

import pytest
from django.core.exceptions import ValidationError

from callico.projects.models import Element, Project

pytestmark = pytest.mark.django_db


def test_polygon_without_image(project, arkindex_provider):
    page_type = project.types.get(name="Page")
    element = Element.objects.create(
        project=project,
        type=page_type,
        polygon=[[1, 2], [2, 3], [3, 4]],
        provider=arkindex_provider,
        provider_object_id=str(uuid.uuid4()),
    )
    with pytest.raises(ValidationError, match=re.escape("{'image': ['An element cannot have polygon without image']}")):
        element.clean()


def test_parent_not_in_project(project, arkindex_provider):
    other_project = Project.objects.create(name="New project")
    folder_type = other_project.types.create(
        name="Folder", folder=True, provider=arkindex_provider, provider_object_id="folder"
    )
    page_type = other_project.types.create(name="Page", provider=arkindex_provider, provider_object_id="page")
    parent = Element.objects.create(
        project=other_project,
        type=folder_type,
        provider=arkindex_provider,
        provider_object_id=str(uuid.uuid4()),
    )
    element = Element.objects.create(
        project=project,
        type=page_type,
        parent=parent,
        provider=arkindex_provider,
        provider_object_id=str(uuid.uuid4()),
    )
    error = {"parent": [f"Parent is not part of the project {project}"]}

    assert element.project != parent.project
    with pytest.raises(ValidationError, match=re.escape(str(error))):
        element.clean()


def test_parent_not_itself(project, arkindex_provider):
    folder_type = project.types.get(name="Folder")
    element = Element.objects.create(
        project=project,
        type=folder_type,
        provider=arkindex_provider,
        provider_object_id=str(uuid.uuid4()),
    )
    Element.objects.update(parent=element)
    element.refresh_from_db()
    with pytest.raises(ValidationError, match=re.escape("{'parent': ['An element cannot be its own parent']}")):
        element.clean()


def test_build_thumbnail(public_element):
    assert public_element.build_thumbnail(size_max_height=50) == "http://iiif/url/0,0,42,666/,50/0/default.jpg"


def test_build_thumbnail_limit_iiif_size(public_element):
    """No interest to query for an image with increased resolution for thumbnails"""
    assert public_element.build_thumbnail(size_max_height=5000) == "http://iiif/url/0,0,42,666/,666/0/default.jpg"
