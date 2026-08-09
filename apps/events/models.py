from django.db import models


class Event(models.Model):
    class Type(models.TextChoices):
        ATTEMPT_SUBMITTED = "attempt_submitted"
        HINT_ISSUED = "hint_issued"
        HINT_BLOCKED_BY_GUARDRAIL = "hint_blocked_by_guardrail"
        DIAGNOSTIC_STARTED = "diagnostic_started"
        DIAGNOSTIC_SUBMITTED = "diagnostic_submitted"
        MOCK_STARTED = "mock_started"
        MOCK_SUBMITTED = "mock_submitted"
        EXPERT_REVIEW_COMPLETED = "expert_review_completed"
        PLAN_REBUILT = "plan_rebuilt"
        PLAN_CHANGE_LOGGED = "plan_change_logged"
        REVIEW_COMPLETED = "review_completed"
        TRAJECTORY_ASSIGNED = "trajectory_assigned"
        TRAJECTORY_TRANSITION = "trajectory_transition"
        TARGET_SCORE_CHANGED = "target_score_changed"
        XP_AWARDED = "xp_awarded"
        STREAK_ADVANCED = "streak_advanced"
        STREAK_RESET = "streak_reset"
        QUEST_COMPLETED = "quest_completed"
        # Действия бэкофиса: кто опубликовал урок, поменял цену,
        # начислил сигмы или вернул деньги.
        ADMIN_ACTION = "admin_action"

    student = models.ForeignKey(
        "accounts.StudentProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events",
    )
    event_type = models.CharField(max_length=64, choices=Type.choices)
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        # Индексы под горячие выборки: без них ленты ученика и ночные
        # джобы читают таблицу целиком уже на первой тысяче учеников.
        indexes = [
            models.Index(fields=["event_type", "-created_at"], name="event_type_recent"),
            models.Index(fields=["student", "-created_at"], name="event_student_recent"),
        ]
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise RuntimeError("События являются append-only и не могут быть изменены.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError("События являются append-only и не могут быть удалены.")
