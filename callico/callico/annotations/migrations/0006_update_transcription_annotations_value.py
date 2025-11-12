from django.db import migrations

from callico.projects.models import CampaignMode


def new_transcription_annotations(apps, schema_editor):
    Annotation = apps.get_model("annotations", "Annotation")

    updated = []
    for annotation in Annotation.objects.filter(user_task__task__campaign__mode=CampaignMode.Transcription):
        annotation.value = {
            "transcription": {
                element_id: {"text": transcription_text}
                for element_id, transcription_text in annotation.value.get("transcription", {}).items()
            }
        }
        updated.append(annotation)

    Annotation.objects.bulk_update(updated, fields=["value"], batch_size=1000)


def old_transcription_annotations(apps, schema_editor):
    Annotation = apps.get_model("annotations", "Annotation")

    updated = []
    for annotation in Annotation.objects.filter(user_task__task__campaign__mode=CampaignMode.Transcription):
        annotation.value = {
            "transcription": {
                element_id: transcription.get("text", "")
                for element_id, transcription in annotation.value.get("transcription", {}).items()
            }
        }
        updated.append(annotation)

    Annotation.objects.bulk_update(updated, fields=["value"], batch_size=1000)


class Migration(migrations.Migration):
    dependencies = [
        ("annotations", "0005_taskuser_is_preview"),
    ]

    operations = [
        migrations.RunPython(
            new_transcription_annotations,
            reverse_code=old_transcription_annotations,
        ),
    ]
