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
    # Поправка прогноза в ПЕРВИЧНЫХ баллах: таблица перевода нелинейна, поэтому
    # сдвиг в тестовых означал разную ошибку на разных участках шкалы.
    primary_calibration = models.FloatField(default=0)
    # Дисперсия ошибки прогноза (первичные баллы²) — из неё считается интервал.
    primary_error_variance = models.FloatField(default=0)
    # Сколько пробников уже сверено с прогнозом.
    calibration_samples = models.PositiveSmallIntegerField(default=0)

    def __str__(self):
        return f"Student {self.user.username}"


class ParentProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="parent_profile")
    children = models.ManyToManyField(StudentProfile, related_name="parents", blank=True)

    def __str__(self):
        return f"Parent {self.user.username}"


class StudentGroup(models.Model):
    """Поток или класс: методист выдаёт домашку и следит за группой целиком."""

    title = models.CharField(max_length=200)
    curator = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="curated_groups"
    )
    students = models.ManyToManyField(StudentProfile, related_name="groups", blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return self.title


class Invite(models.Model):
    """Одноразовый код приглашения.

    Учеников не заводят вручную с паролем: методист выдаёт код, человек
    регистрируется сам. Код одноразовый и со сроком — иначе он утекает и по
    нему в группу попадают посторонние.
    """

    code = models.CharField(max_length=32, unique=True)
    role = models.CharField(
        max_length=16, choices=User.Role.choices, default=User.Role.STUDENT
    )
    group = models.ForeignKey(
        StudentGroup, on_delete=models.SET_NULL, null=True, blank=True, related_name="invites"
    )
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_invites"
    )
    expires_at = models.DateTimeField()
    used_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="used_invites"
    )
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.code} ({self.get_role_display()})"

    @property
    def is_used(self) -> bool:
        return self.used_by_id is not None
