from django.db import models


class ProgressSnapshot(models.Model):
    student = models.ForeignKey(
        "accounts.StudentProfile", on_delete=models.CASCADE, related_name="progress_snapshots"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    start_score = models.PositiveSmallIntegerField(null=True, blank=True)
    predicted_score = models.PositiveSmallIntegerField()
    target_score = models.PositiveSmallIntegerField()
    average_mastery = models.FloatField(default=0)
    # [{"node_id": ..., "code": ..., "title": ..., "mastery": ...}, ...]
    weak_topics = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["-created_at"]


class ParentReport(models.Model):
    """Weekly pulse для родителя: факт недели, динамика, риски, слабые темы, следующий шаг."""

    student = models.ForeignKey(
        "accounts.StudentProfile", on_delete=models.CASCADE, related_name="parent_reports"
    )
    week_start = models.DateField()
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["student", "week_start"], name="uniq_weekly_report")
        ]
        ordering = ["-week_start"]
