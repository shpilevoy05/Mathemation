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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
