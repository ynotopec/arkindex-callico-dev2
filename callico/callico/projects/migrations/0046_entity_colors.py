from django.db import migrations

from callico.annotations.views.entity import random_color
from callico.projects.models import CampaignMode


def update_entity_campaigns(apps, schema_editor):
    Campaign = apps.get_model("projects", "Campaign")

    updated = []
    for campaign in Campaign.objects.filter(mode=CampaignMode.Entity):
        entity_types = []
        for entity in campaign.configuration.get("types", []):
            if "entity_color" not in entity:
                entity["entity_color"] = random_color()
            entity_types.append(entity)

        campaign.configuration["types"] = entity_types
        updated.append(campaign)

    Campaign.objects.bulk_update(updated, fields=["configuration"], batch_size=1000)


class Migration(migrations.Migration):
    dependencies = [
        ("projects", "0045_entity_campaigns_display"),
    ]

    operations = [
        migrations.RunPython(
            update_entity_campaigns,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
