from django.db import migrations


TRAJECTORIES = [
    ("score78", "78+", 78, 83, 6),
    ("score84", "84+", 84, 89, 8),
    ("score90", "90+", 90, 100, 10),
]


def seed_trajectories(apps, schema_editor):
    Trajectory = apps.get_model("planning", "Trajectory")
    for slug, title, target_min, target_max, weekly_load_hours in TRAJECTORIES:
        Trajectory.objects.update_or_create(
            slug=slug,
            defaults={
                "title": title,
                "target_min": target_min,
                "target_max": target_max,
                "weekly_load_hours": weekly_load_hours,
                "config": {},
            },
        )


class Migration(migrations.Migration):
    dependencies = [("planning", "0003_trajectory_studyplan_trajectory_trajectorytransition")]

    operations = [migrations.RunPython(seed_trajectories, migrations.RunPython.noop)]
