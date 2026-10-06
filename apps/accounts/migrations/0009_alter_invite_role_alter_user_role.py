from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0008_user_must_change_password_invite_for_student"),
    ]

    operations = [
        migrations.AlterField(
            model_name="invite",
            name="role",
            field=models.CharField(
                choices=[
                    ("student", "Student"),
                    ("parent", "Parent"),
                    ("expert", "Expert"),
                    ("methodist", "Methodist"),
                    ("smm", "SMM"),
                ],
                default="student",
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name="user",
            name="role",
            field=models.CharField(
                choices=[
                    ("student", "Student"),
                    ("parent", "Parent"),
                    ("expert", "Expert"),
                    ("methodist", "Methodist"),
                    ("smm", "SMM"),
                ],
                default="student",
                max_length=16,
            ),
        ),
    ]
