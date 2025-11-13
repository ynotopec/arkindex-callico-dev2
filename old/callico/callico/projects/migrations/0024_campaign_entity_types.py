from django.db import migrations

from callico.projects.models import CampaignMode


def update_campaigns(apps, schema_editor, campaign_mode, key):
    Campaign = apps.get_model("projects", "Campaign")

    updated = []
    for campaign in Campaign.objects.filter(mode=campaign_mode):
        items = []
        for item in campaign.configuration[key]:
            item["entity_type"] = item["entity_subtype"] or item["entity_type"]
            del item["entity_subtype"]
            items.append(item)
        campaign.configuration = {key: items}

        updated.append(campaign)

    Campaign.objects.bulk_update(updated, fields=["configuration"], batch_size=1000)


def update_entity_campaign_types(apps, schema_editor):
    update_campaigns(apps, schema_editor, campaign_mode=CampaignMode.Entity, key="types")


def update_entity_form_campaign_types(apps, schema_editor):
    update_campaigns(apps, schema_editor, campaign_mode=CampaignMode.EntityForm, key="fields")


class Migration(migrations.Migration):
    dependencies = [
        ("projects", "0023_type_folder"),
    ]

    operations = [
        migrations.RunPython(
            update_entity_campaign_types,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.RunPython(
            update_entity_form_campaign_types,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
