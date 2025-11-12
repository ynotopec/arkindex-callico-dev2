import re

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from callico.projects.models import Campaign, CampaignState, Project

pytestmark = pytest.mark.django_db


def test_clone_arkindex_campaign_campaign_required():
    with pytest.raises(CommandError, match=r"the following arguments are required: --campaign"):
        call_command("clone_arkindex_campaign")


def test_clone_arkindex_campaign_campaign_not_uuid():
    with pytest.raises(CommandError, match=r"invalid UUID value: 'my_campaign'"):
        call_command(
            "clone_arkindex_campaign",
            "--campaign",
            "my_campaign",
        )


def test_clone_arkindex_campaign_campaign_does_not_exist():
    with pytest.raises(CommandError, match=r"Campaign with id aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa doesn't exist"):
        call_command(
            "clone_arkindex_campaign",
            "--campaign",
            "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        )


@pytest.mark.parametrize(
    "arguments",
    [
        ["--arkindex-provider", "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"],
        ["--corpus", "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"],
    ],
)
def test_clone_arkindex_campaign_provider_and_corpus_or_neither(managed_campaign, arguments):
    with pytest.raises(
        CommandError,
        match=r"Either both or neither of the --arkindex-provider and --corpus arguments must be provided to create the new project",
    ):
        call_command("clone_arkindex_campaign", "--campaign", str(managed_campaign.id), *arguments)


@pytest.mark.parametrize("name_argument", [False, True])
@pytest.mark.parametrize("provider_arguments", [False, True])
def test_clone_arkindex_campaign(arkindex_provider, managed_campaign, name_argument, provider_arguments):
    command_arguments = []
    if name_argument:
        command_arguments.extend(["--project-name", "Dolly"])
    if provider_arguments:
        command_arguments.extend(
            ["--arkindex-provider", str(arkindex_provider.id), "--corpus", "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"]
        )
    call_command("clone_arkindex_campaign", "--campaign", str(managed_campaign.id), *command_arguments)

    if name_argument:
        created_project = Project.objects.get(name="Dolly")
    else:
        created_project = Project.objects.get(name__contains="Clone of Managed project")
        assert re.match(r"Clone of Managed project [0-9]{4}", created_project.name)

    assert created_project.provider == (arkindex_provider if provider_arguments else None)
    assert created_project.provider_object_id == (
        "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" if provider_arguments else None
    )

    created_campaign = Campaign.objects.get(project=created_project)
    assert created_campaign.name == managed_campaign.name
    assert created_campaign.state == CampaignState.Created
    assert bool(created_campaign.csv_export) is False
    assert bool(created_campaign.xlsx_export) is False
    assert created_campaign.creator == managed_campaign.creator
    assert created_campaign.mode == managed_campaign.mode
    assert created_campaign.description == managed_campaign.description
    assert created_campaign.nb_tasks_auto_assignment == managed_campaign.nb_tasks_auto_assignment
    assert created_campaign.configuration == managed_campaign.configuration
