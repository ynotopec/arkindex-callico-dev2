# -*- coding: utf-8 -*-
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from callico.projects.models import Provider, ProviderType


class ArkindexCommand(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument(
            "--arkindex-provider",
            help="The name or UUID of the Arkindex provider to use",
            type=str,
            required=False,
        )

    def check_arkindex_provider_param(self, arkindex_provider_param, project=None):
        """
        The Arkindex provider is optional if the project used has one.
        """
        if not arkindex_provider_param and not project:
            raise CommandError("The --arkindex-provider CLI option is required")

        if not arkindex_provider_param and not project.provider:
            raise CommandError(
                "Either the Arkindex provider of the project or --arkindex-provider CLI option should be defined"
            )

        if not arkindex_provider_param:
            return project.provider.id

        if (
            project.provider
            and str(project.provider.id) != arkindex_provider_param
            and project.provider.name != arkindex_provider_param
        ):
            raise CommandError("The Arkindex provider of the project and the --arkindex-provider CLI are not the same")

        return arkindex_provider_param

    def get_arkindex_provider(self, arkindex_provider_param):
        if not arkindex_provider_param:
            self.arkindex_provider = None
            return
        try:
            try:
                self.arkindex_provider = Provider.objects.get(id=arkindex_provider_param, type=ProviderType.Arkindex)
            except (ValidationError, Provider.DoesNotExist):
                self.arkindex_provider = Provider.objects.get(name=arkindex_provider_param, type=ProviderType.Arkindex)
        except Provider.DoesNotExist:
            raise CommandError("Arkindex provider doesn't exist")

    def handle(self, *args, check_provider=True, **options):
        if check_provider:
            arkindex_provider_param = self.check_arkindex_provider_param(
                options["arkindex_provider"], options.get("project")
            )
        else:
            arkindex_provider_param = options["arkindex_provider"]
        self.get_arkindex_provider(arkindex_provider_param)
