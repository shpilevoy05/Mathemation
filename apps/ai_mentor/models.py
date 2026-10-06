import uuid

from django.db import models


class AiHintSession(models.Model):
    """Лог использования ИИ-наставника внутри одной задачи (виден родителю)."""

    student = models.ForeignKey(
        "accounts.StudentProfile", on_delete=models.CASCADE, related_name="hint_sessions"
    )
    assignment = models.ForeignKey("content.Assignment", on_delete=models.CASCADE)
    node = models.ForeignKey(
        "knowledge.KnowledgeNode", on_delete=models.SET_NULL, null=True, blank=True
    )
    hints_used = models.PositiveSmallIntegerField(default=0)
    escalated_to_expert = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["student", "assignment"], name="uniq_hint_session")
        ]


class AiHintMessage(models.Model):
    class Role(models.TextChoices):
        STUDENT = "student"
        MENTOR = "mentor"

    session = models.ForeignKey(AiHintSession, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=16, choices=Role.choices)
    text = models.TextField()
    is_blocked = models.BooleanField(default=False)
    failed_claims = models.JSONField(default=list, blank=True)
    unverified_claims = models.JSONField(default=list, blank=True)
    prompt_tokens = models.PositiveIntegerField(default=0)
    completion_tokens = models.PositiveIntegerField(default=0)
    estimated_cost_rub = models.DecimalField(max_digits=12, decimal_places=6, default=0)
    counts_toward_daily_limit = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class AiOutboundRequest(models.Model):
    """Local-only metadata for an outbound LLM request; prompt text is never stored."""

    class Purpose(models.TextChoices):
        HINT = "hint", "Подсказка"
        MOCK_CHECK = "mock_check", "Проверка пробника"

    student = models.ForeignKey(
        "accounts.StudentProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ai_outbound_requests",
    )
    pseudonym = models.CharField(max_length=28, db_index=True)
    request_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    purpose = models.CharField(max_length=24, choices=Purpose.choices)
    provider = models.CharField(max_length=80)
    model = models.CharField(max_length=160, blank=True)
    redaction_counts = models.JSONField(default=dict, blank=True)
    prompt_tokens = models.PositiveIntegerField(default=0)
    completion_tokens = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
