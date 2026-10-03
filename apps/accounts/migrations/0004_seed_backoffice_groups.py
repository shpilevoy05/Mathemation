from django.db import migrations


EXPERT_PERMISSIONS = {
    ("expert_review", "ExpertReviewRequest"): ("add", "change", "delete", "view"),
    ("ai_mentor", "AiHintSession"): ("view",),
    ("ai_mentor", "AiHintMessage"): ("view",),
    ("content", "Assignment"): ("view",),
    ("knowledge", "KnowledgeNode"): ("view",),
    ("mocks", "MockExamResult"): ("view",),
}

METHODIST_PERMISSIONS = {
    ("content", "Lesson"): ("add", "change", "delete", "view"),
    ("content", "TheoryBlock"): ("add", "change", "delete", "view"),
    ("content", "Assignment"): ("add", "change", "delete", "view"),
    ("content", "AssignmentSkillTag"): ("add", "change", "delete", "view"),
    ("knowledge", "TopicCluster"): ("add", "change", "delete", "view"),
    ("knowledge", "KnowledgeNode"): ("add", "change", "delete", "view"),
    ("knowledge", "KnowledgeDependency"): ("add", "change", "delete", "view"),
    ("mocks", "MockExam"): ("add", "change", "delete", "view"),
    ("diagnostics", "DiagnosticTest"): ("add", "change", "delete", "view"),
    ("planning", "Trajectory"): ("add", "change", "delete", "view"),
    ("planning", "StudyPlan"): ("add", "change", "delete", "view"),
    ("planning", "StudyPlanItem"): ("add", "change", "delete", "view"),
    ("accounts", "StudentProfile"): ("view",),
}


def rebuild_group(apps, group_name, permission_spec):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")

    group, _ = Group.objects.get_or_create(name=group_name)
    group.permissions.clear()
    permissions = []
    for (app_label, model_name), actions in permission_spec.items():
        model = apps.get_model(app_label, model_name)
        content_type, _ = ContentType.objects.get_or_create(
            app_label=model._meta.app_label,
            model=model._meta.model_name,
        )
        for action in actions:
            codename = f"{action}_{model._meta.model_name}"
            permission, _ = Permission.objects.get_or_create(
                content_type=content_type,
                codename=codename,
                defaults={"name": f"Can {action} {model._meta.verbose_name}"},
            )
            permissions.append(permission)
    group.permissions.set(permissions)


def seed_backoffice_groups(apps, schema_editor):
    rebuild_group(apps, "Эксперты", EXPERT_PERMISSIONS)
    rebuild_group(apps, "Методисты", METHODIST_PERMISSIONS)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0003_alter_user_role"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("ai_mentor", "0002_aihintmessage_failed_claims_aihintmessage_is_blocked_and_more"),
        ("content", "0003_lesson_video_fields"),
        ("diagnostics", "0001_initial"),
        ("expert_review", "0002_expertreviewrequest_error_tags"),
        ("knowledge", "0002_alter_knowledgenode_options_and_more"),
        ("mocks", "0002_mockexam_duration_minutes_and_more"),
        ("planning", "0004_seed_named_trajectories"),
    ]

    operations = [
        migrations.RunPython(seed_backoffice_groups, migrations.RunPython.noop),
    ]
