from django.db import migrations


SMM_PERMISSIONS = {
    ("social_agent", "BrandProfile"): ("add", "change", "view"),
    ("social_agent", "Channel"): ("add", "change", "view"),
    ("social_agent", "Rubric"): ("add", "change", "view"),
    ("social_agent", "RubricSlot"): ("add", "change", "delete", "view"),
    ("social_agent", "SocialTaskPermission"): ("add", "change", "view"),
    ("social_agent", "SocialLessonPermission"): ("add", "change", "view"),
    ("social_agent", "ContentIdea"): ("add", "change", "delete", "view"),
    ("social_agent", "Post"): ("add", "change", "view"),
    ("social_agent", "PostCheck"): ("view",),
    ("social_agent", "LlmCall"): ("view",),
    ("social_agent", "MediaAsset"): ("add", "change", "view"),
    ("social_agent", "BotState"): ("view",),
}


def rebuild_smm_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")

    group, _ = Group.objects.get_or_create(name="SMM")
    group.permissions.clear()
    permissions = []
    for (app_label, model_name), actions in SMM_PERMISSIONS.items():
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


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0009_alter_invite_role_alter_user_role"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("social_agent", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(rebuild_smm_group, migrations.RunPython.noop),
    ]
