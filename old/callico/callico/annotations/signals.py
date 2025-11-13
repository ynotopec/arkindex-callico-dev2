# -*- coding: utf-8 -*-
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from callico.annotations.models import Annotation
from callico.projects.models import CampaignMode


@receiver(pre_save, sender=Annotation)
def update_version(sender, instance, **kwargs):
    # The annotation is updating, its version should not change
    # This only occurs when publishing and updating the date
    if sender.objects.filter(id=instance.id).exists():
        return

    last_annotation = sender.objects.filter(user_task=instance.user_task).order_by("-version").first()
    instance.version = last_annotation.version + 1 if last_annotation else 1


@receiver(post_save, sender=Annotation)
def update_has_uncertain_value(sender, instance, **kwargs):
    # Check if this annotation is the latest version
    last_annotation = sender.objects.filter(user_task=instance.user_task).order_by("-version").first()
    if instance != last_annotation:
        return

    campaign_mode = instance.user_task.task.campaign.mode

    if campaign_mode == CampaignMode.Transcription:
        instance.user_task.has_uncertain_value = (
            isinstance(instance.value, dict)
            and isinstance(instance.value.get("transcription"), dict)
            and any(transcription.get("uncertain", False) for transcription in instance.value["transcription"].values())
        )
        instance.user_task.save()
    elif campaign_mode == CampaignMode.EntityForm:
        instance.user_task.has_uncertain_value = (
            isinstance(instance.value, dict)
            and isinstance(instance.value.get("values"), list)
            and any(entity.get("uncertain", False) for entity in instance.value["values"])
        )
        instance.user_task.save()
