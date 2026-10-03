from django.conf import settings
from django.db import models


class ConsentRecord(models.Model):
    class Kind(models.TextChoices):
        PERSONAL_DATA = "personal_data", "Обработка персональных данных"
        TERMS = "terms", "Пользовательское соглашение"
        PARENT_FOR_CHILD = "parent_for_child", "Согласие законного представителя"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="consent_records"
    )
    kind = models.CharField(max_length=32, choices=Kind.choices)
    document_version = models.CharField(max_length=32)
    subject_student = models.ForeignKey(
        "accounts.StudentProfile", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="parent_consent_records",
    )
    accepted_at = models.DateTimeField(auto_now_add=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-accepted_at", "-id"]
        indexes = [
            models.Index(
                fields=["user", "kind", "document_version"],
                name="consent_user_current",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise RuntimeError("Записи согласий являются append-only.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError("Записи согласий являются append-only.")


class DataDeletionRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Ожидает обработки"
        DONE = "done", "Выполнен"
        REJECTED = "rejected", "Отклонён"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="data_deletion_requests",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="processed_deletion_requests",
    )
    processed_at = models.DateTimeField(null=True, blank=True)
    comment = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class Feedback(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "Новое"
        IN_PROGRESS = "in_progress", "В работе"
        DONE = "done", "Готово"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="feedback_messages",
    )
    page_url = models.CharField(max_length=500, blank=True)
    message = models.TextField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.NEW)
    staff_comment = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
