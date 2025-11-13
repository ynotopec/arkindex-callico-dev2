# -*- coding: utf-8 -*-
from django.db.models.signals import pre_save
from django.dispatch import receiver

from callico.projects.models import Element


@receiver(pre_save, sender=Element)
def update_order(sender, instance, **kwargs):
    # If no order was provided, it is defined according to the previous element if it exists or not
    if instance.order is None:
        previous_element = (
            sender.objects.filter(project=instance.project, parent=instance.parent).order_by("-order").first()
        )
        instance.order = previous_element.order + 1 if previous_element else 0
