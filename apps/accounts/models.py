from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        STUDENT = "student"
        PARENT = "parent"
        EXPERT = "expert"
        METHODIST = "methodist"

    role = models.CharField(max_length=16, choices=Role.choices, default=Role.STUDENT)


class StudentProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="student_profile")
    target_score = models.PositiveSmallIntegerField(default=80)
    exam_date = models.DateField(null=True, blank=True)
    # Filled from the entry diagnostic; None until diagnostics are completed.
    start_score = models.PositiveSmallIntegerField(null=True, blank=True)
    weekly_hours = models.PositiveSmallIntegerField(default=6)
    # Поправка прогноза, калибруется по факту каждого пробника (EMA ошибки).
    forecast_calibration = models.FloatField(default=0)

    def __str__(self):
        return f"Student {self.user.username}"


class ParentProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="parent_profile")
    children = models.ManyToManyField(StudentProfile, related_name="parents", blank=True)

    def __str__(self):
        return f"Parent {self.user.username}"
