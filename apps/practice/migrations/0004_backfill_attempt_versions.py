"""Проставить уже сделанным попыткам версию задания.

Версий раньше не было: для каждого задания создаётся версия 1 из его текущих
полей, и все попытки без версии привязываются к ней. До введения
версионирования условие и было тем, что видел ученик.
"""

from django.db import migrations


def backfill(apps_registry, schema_editor):
    Assignment = apps_registry.get_model("content", "Assignment")
    AssignmentVersion = apps_registry.get_model("content", "AssignmentVersion")
    Attempt = apps_registry.get_model("practice", "Attempt")

    for assignment in Assignment.objects.all():
        version = (
            AssignmentVersion.objects.filter(assignment=assignment)
            .order_by("number")
            .first()
        )
        if version is None:
            version = AssignmentVersion.objects.create(
                assignment=assignment, number=1,
                statement=assignment.statement,
                correct_answer=assignment.correct_answer,
                reference_solution=assignment.reference_solution,
                max_score=assignment.max_score,
                difficulty=assignment.difficulty,
                change_note="Версия до введения версионирования",
            )
        Attempt.objects.filter(
            assignment=assignment, assignment_version__isnull=True
        ).update(assignment_version=version)


def unset(apps_registry, schema_editor):
    Attempt = apps_registry.get_model("practice", "Attempt")
    Attempt.objects.update(assignment_version=None)


class Migration(migrations.Migration):

    dependencies = [
        ("practice", "0003_attempt_assignment_version"),
        ("content", "0004_assignmentversion"),
    ]

    operations = [migrations.RunPython(backfill, unset)]
