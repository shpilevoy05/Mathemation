from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("content", "0010_solutionpath_solutionstep")]

    operations = [
        migrations.AddField(
            model_name="assignment",
            name="arena_enabled",
            field=models.BooleanField(default=True, verbose_name="Использовать в арене"),
        ),
    ]
