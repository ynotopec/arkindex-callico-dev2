import re
import uuid

import pytest
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError

from callico.projects.models import Class

pytestmark = pytest.mark.django_db


def test_clean_provider_without_identifier(project):
    with pytest.raises(
        ValidationError,
        match=re.escape("{'provider': ['An identifier must be provided if you specify a provider and vice versa']}"),
    ):
        Class(name="My class", project=project, provider=project.provider).clean()


def test_clean_identifier_without_provider(project):
    with pytest.raises(
        ValidationError,
        match=re.escape(
            "{'provider_object_id': ['A provider must be specified if you provide an identifier and vice versa']}"
        ),
    ):
        Class(name="My class", project=project, provider_object_id="test").clean()


@pytest.mark.parametrize(
    "provider_fields",
    [{"provider_id": uuid.uuid4()}, {"provider_object_id": str(uuid.uuid4())}],
)
def test_provider_fields_class_both_null_or_both_set(project, provider_fields):
    with pytest.raises(
        IntegrityError,
        match=re.escape(
            'new row for relation "projects_class" violates check constraint "provider_fields_class_all_set_or_none_set"'
        ),
    ):
        Class.objects.create(name="My class", project=project, **provider_fields)
