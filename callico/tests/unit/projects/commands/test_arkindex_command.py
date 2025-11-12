import uuid

import pytest
from django.core.management.base import CommandError
from pytest_lazy_fixtures import lf as lazy_fixture

from callico.projects.management.commands import ArkindexCommand

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "project_param, arkindex_provider_param, error_message",
    [
        (
            None,
            None,
            "The --arkindex-provider CLI option is required",
        ),
        (
            lazy_fixture("public_project"),
            None,
            "Either the Arkindex provider of the project or --arkindex-provider CLI option should be defined",
        ),
        (
            lazy_fixture("project"),
            "Wrong name",
            "The Arkindex provider of the project and the --arkindex-provider CLI are not the same",
        ),
    ],
)
def test_arkindex_command_check_arkindex_provider_param_error(project_param, arkindex_provider_param, error_message):
    with pytest.raises(CommandError, match=error_message):
        ArkindexCommand().check_arkindex_provider_param(arkindex_provider_param, project_param)


def test_arkindex_command_get_arkindex_provider_error_wrong_id():
    with pytest.raises(CommandError, match="Arkindex provider doesn't exist"):
        ArkindexCommand().get_arkindex_provider(str(uuid.uuid4()))


def test_arkindex_command_get_arkindex_provider_error_wrong_type(iiif_provider):
    with pytest.raises(CommandError, match="Arkindex provider doesn't exist"):
        ArkindexCommand().get_arkindex_provider(str(iiif_provider.id))


@pytest.mark.parametrize("arkindex_provider_param", [None, str(uuid.uuid4()), "Arkindex test"])
def test_arkindex_command(arkindex_provider_param, project):
    try:
        uuid.UUID(arkindex_provider_param)
        # If no exception is raised, it means we are waiting for an UUID in the parameter (not a name)
        arkindex_provider_param = str(project.provider.id)
    except (ValueError, TypeError):
        pass

    command = ArkindexCommand()
    command.project = project
    command.handle(project=project, arkindex_provider=arkindex_provider_param)

    assert command.arkindex_provider == project.provider


@pytest.mark.parametrize("arkindex_provider_param", [None, str(uuid.uuid4()), "Arkindex test"])
def test_arkindex_command_check_provider_false(arkindex_provider_param, arkindex_provider):
    command = ArkindexCommand()
    try:
        uuid.UUID(arkindex_provider_param)
        # If no exception is raised, it means we are waiting for an UUID in the parameter (not a name)
        arkindex_provider_param = str(arkindex_provider.id)
    except (ValueError, TypeError):
        pass
    command.handle(check_provider=False, arkindex_provider=arkindex_provider_param)

    assert command.arkindex_provider == (arkindex_provider if arkindex_provider_param else None)
