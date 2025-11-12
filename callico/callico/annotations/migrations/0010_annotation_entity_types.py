from django.db import migrations

from callico.projects.models import CampaignMode


def update_annotations(apps, schema_editor, campaign_mode, key):
    Annotation = apps.get_model("annotations", "Annotation")

    updated = []
    for annotation in Annotation.objects.filter(user_task__task__campaign__mode=campaign_mode):
        if annotation.value.get(key):
            items = []
            for item in annotation.value[key]:
                if not item:
                    # There should not be any empty annotations, but there might be
                    continue
                item["entity_type"] = item["entity_subtype"] or item["entity_type"]
                del item["entity_subtype"]
                items.append(item)
            annotation.value = {key: items}

        updated.append(annotation)

    Annotation.objects.bulk_update(updated, fields=["value"], batch_size=1000)


def update_annotations_entity(apps, schema_editor):
    update_annotations(apps, schema_editor, campaign_mode=CampaignMode.Entity, key="entities")


def update_annotations_entity_form(apps, schema_editor):
    update_annotations(apps, schema_editor, campaign_mode=CampaignMode.EntityForm, key="values")


class Migration(migrations.Migration):
    dependencies = [
        ("annotations", "0009_annotation_duration"),
    ]

    operations = [
        migrations.RunPython(
            update_annotations_entity,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.RunPython(
            update_annotations_entity_form,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
