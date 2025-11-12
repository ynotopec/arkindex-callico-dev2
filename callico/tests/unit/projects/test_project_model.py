import re
import uuid

import pytest
from django.contrib.admin.sites import AdminSite
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from pytest_lazy_fixtures import lf as lazy_fixture

from callico.process.models import Process, ProcessMode
from callico.projects.admin import ProjectAdmin
from callico.projects.models import Project

pytestmark = pytest.mark.django_db


def test_clean_provider_without_identifier(arkindex_provider):
    with pytest.raises(
        ValidationError,
        match=re.escape("{'provider': ['An identifier must be provided if you specify a provider and vice versa']}"),
    ):
        Project(name="My project", provider=arkindex_provider).clean()


def test_clean_identifier_without_provider():
    with pytest.raises(
        ValidationError,
        match=re.escape(
            "{'provider_object_id': ['A provider must be specified if you provide an identifier and vice versa']}"
        ),
    ):
        Project(name="My project", provider_object_id="test").clean()


@pytest.mark.parametrize(
    "provider_fields",
    [{"provider_id": uuid.uuid4()}, {"provider_object_id": str(uuid.uuid4())}],
)
def test_provider_fields_both_null_or_both_set(provider_fields):
    with pytest.raises(
        IntegrityError,
        match=re.escape(
            'new row for relation "projects_project" violates check constraint "provider_fields_all_set_or_none_set"'
        ),
    ):
        Project.objects.create(name="My project", **provider_fields)


class MockRequest(object):
    def __init__(self, user=None):
        self.user = user


class MockForm(object):
    def __init__(self, cleaned_data=None):
        self.changed_data = cleaned_data
        self.cleaned_data = cleaned_data


@pytest.mark.parametrize("update", [False, True])
@pytest.mark.parametrize("provider", [None, lazy_fixture("iiif_provider")])
def test_admin_save_model_no_arkindex_provider_associated(mocker, admin, public_project, update, provider):
    """Creating or updating a project not associated to an Arkindex provider shouldn't trigger the async task"""
    celery_fetch_mock = mocker.patch("callico.process.arkindex.tasks.arkindex_fetch_extra_info.apply_async")

    project_admin = ProjectAdmin(model=Project, admin_site=AdminSite())
    if update:
        obj = public_project
    else:
        obj = Project(
            name="Project",
            public=False,
            provider_id=provider.id if provider else None,
            provider_object_id="test" if provider else None,
        )

    project_admin.save_model(
        obj=obj,
        request=MockRequest(user=admin.user),
        form=MockForm(cleaned_data=({"provider": provider} if update else None)),
        change=update,
    )

    assert Process.objects.count() == 0
    assert celery_fetch_mock.call_count == 0


@pytest.mark.parametrize("update", [False, True])
def test_admin_save_model_fetch_arkindex_extra_info(
    mocker, django_capture_on_commit_callbacks, admin, project, arkindex_provider, update
):
    """Creating or updating a project associated to an Arkindex provider should trigger the async task"""
    celery_fetch_mock = mocker.patch("callico.process.arkindex.tasks.arkindex_fetch_extra_info.apply_async")

    project_admin = ProjectAdmin(model=Project, admin_site=AdminSite())
    if update:
        obj = project
    else:
        obj = Project(name="Project", public=False, provider_id=arkindex_provider.id, provider_object_id="test")

    with django_capture_on_commit_callbacks(execute=True):
        project_admin.save_model(
            obj=obj,
            request=MockRequest(user=admin.user),
            form=MockForm(cleaned_data=({"provider": arkindex_provider} if update else None)),
            change=update,
        )

    assert Process.objects.count() == 1
    assert list(Process.objects.all().values("name", "mode", "configuration", "project", "creator")) == [
        {
            "name": "Retrieval of extra information from Arkindex upon Project creation or update",
            "mode": ProcessMode.ArkindexImport.value,
            "configuration": {
                "arkindex_provider": str(arkindex_provider.id),
                "project_id": str(obj.id),
            },
            "project": obj.id,
            "creator": admin.user.id,
        },
    ]
    assert celery_fetch_mock.call_count == 1
