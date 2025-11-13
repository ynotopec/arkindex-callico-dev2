# -*- coding: utf-8 -*-
import logging

from django.core.management.base import BaseCommand

from callico.annotations.models import TaskUser

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    def handle(self, *args, **options):
        to_delete = TaskUser.objects.filter(is_preview=True)
        logger.info(f"Retrieved {to_delete.count()} preview user tasks to be deleted.")
        to_delete.delete()
        logger.info("Deleted all preview user tasks.")
