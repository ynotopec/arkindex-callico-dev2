# -*- coding: utf-8 -*-
import logging
import random
import string
import uuid
from urllib.parse import urljoin

from django.conf import settings
from django.core.management.base import CommandError
from django.urls import reverse

from callico.projects.management.commands import ArkindexCommand
from callico.projects.models import Campaign, Project

logger = logging.getLogger(__name__)


def get_campaign(campaign_id):
    try:
        return Campaign.objects.get(id=campaign_id)
    except Campaign.DoesNotExist:
        raise CommandError(f"Campaign with id {campaign_id} doesn't exist")


class Command(ArkindexCommand):
    help = "Clone an existing campaign."

    def add_arguments(self, parser):
        super().add_arguments(parser)

        parser.add_argument(
            "--campaign",
            help="The UUID of the campaign to clone",
            type=uuid.UUID,
            required=True,
        )
        parser.add_argument(
            "--project-name",
            help="A name for the new project in which the campaign will be cloned. Defaults to 'Clone of $cloned-campaign-project-name'",
            type=str,
        )
        parser.add_argument(
            "--corpus",
            help="The UUID of the Arkindex corpus to link to the new project in which the campaign will be cloned",
            type=uuid.UUID,
        )

    def handle(self, *args, **options):
        campaign = get_campaign(options["campaign"])
        rand_4 = "".join(random.choice(string.digits) for _i in range(4))
        name = options["project_name"] or f"Clone of {campaign.project.name} {rand_4}"

        arkindex_provider = options["arkindex_provider"]
        corpus = options["corpus"]
        if (arkindex_provider is not None) ^ (corpus is not None):
            raise CommandError(
                "Either both or neither of the --arkindex-provider and --corpus arguments must be provided to create the new project"
            )

        super().handle(check_provider=False, *args, **options)

        logger.info(f'Creating a new project "{name}"')

        new_project = Project.objects.create(
            name=name,
            provider=self.arkindex_provider,
            provider_object_id=corpus,
        )

        logger.info(f'Cloning the campaign "{campaign.name}" in the new project "{name}"')

        Campaign.objects.create(
            name=campaign.name,
            creator=campaign.creator,
            project=new_project,
            mode=campaign.mode,
            description=campaign.description,
            nb_tasks_auto_assignment=campaign.nb_tasks_auto_assignment,
            configuration=campaign.configuration,
        )

        configure_url = urljoin(settings.INSTANCE_URL, reverse("admin:projects_project_change", args=[new_project.id]))
        extra_hint = (
            ""
            if options["project_name"] and self.arkindex_provider
            else "might need to update its name, provider and identifier, and "
        )
        logger.info(
            f'Campaign "{campaign.name}" was successfully cloned in a new project! '
            f"You can finish configuring the project by following this link: {configure_url}\n"
            f"You {extra_hint}should add members to it. Don't forget to import elements in it before creating tasks for your campaign."
        )
