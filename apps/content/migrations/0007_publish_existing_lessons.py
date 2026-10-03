"""Существующие уроки уже показывались ученикам — значит, они опубликованы.

Новый урок по умолчанию черновик, но задним числом переводить живой контент в
черновики нельзя: у учеников он пропал бы из плана и с дорожки.
"""

from django.db import migrations
from django.utils import timezone


def publish_existing(apps_registry, schema_editor):
    Lesson = apps_registry.get_model("content", "Lesson")
    Lesson.objects.filter(status="draft").update(
        status="published", published_at=timezone.now()
    )


def unpublish(apps_registry, schema_editor):
    Lesson = apps_registry.get_model("content", "Lesson")
    Lesson.objects.update(status="draft", published_at=None)


class Migration(migrations.Migration):

    dependencies = [
        ("content", "0006_lesson_published_at_lesson_status_and_more"),
    ]

    operations = [migrations.RunPython(publish_existing, unpublish)]
