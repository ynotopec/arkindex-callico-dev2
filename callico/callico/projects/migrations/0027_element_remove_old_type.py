import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("projects", "0026_element_add_new_type"),
    ]

    operations = [
        migrations.AlterField(
            model_name="element",
            name="type",
            field=models.CharField(default="temp", max_length=250, verbose_name="Type"),
        ),
        migrations.RemoveField(
            model_name="element",
            name="type",
        ),
        migrations.RenameField(
            model_name="element",
            old_name="new_type",
            new_name="type",
        ),
        migrations.AlterField(
            model_name="element",
            name="type",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="elements",
                to="projects.type",
                verbose_name="Type",
            ),
        ),
    ]
