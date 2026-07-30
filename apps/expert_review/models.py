from django.conf import settings
from django.db import models

from .storage import private_media_storage, solution_upload_path
from .validators import validate_solution_upload


class ExpertReviewRequest(models.Model):
    """Загрузка решения второй части на экспертную проверку.

    Auto-check is never the final arbiter for part 2 — a human expert is.
    TODO (post-MVP): AI-assisted pre-check to speed experts up.
    """

    class Status(models.TextChoices):
        SUBMITTED = "submitted"
        IN_REVIEW = "in_review"
        REVIEWED = "reviewed"
        NEEDS_RESUBMISSION = "needs_resubmission"

    student = models.ForeignKey(
        "accounts.StudentProfile", on_delete=models.CASCADE, related_name="expert_reviews"
    )
    assignment = models.ForeignKey("content.Assignment", on_delete=models.CASCADE)
    attempt = models.ForeignKey(
        "practice.Attempt", on_delete=models.SET_NULL, null=True, blank=True
    )
    mock_result = models.ForeignKey(
        "mocks.MockExamResult", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="expert_reviews",
    )
    # Приватное хранилище вне MEDIA_ROOT: публичного URL у файла нет,
    # содержимое отдаётся только SolutionFileView с проверкой прав.
    solution_file = models.FileField(
        upload_to=solution_upload_path,
        storage=private_media_storage,
        validators=[validate_solution_upload],
    )
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.SUBMITTED)
    sla_hours = models.PositiveSmallIntegerField(default=settings.EXPERT_REVIEW_SLA_HOURS)
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="reviews_done",
    )
    # Result: {"criterion": score, ...} по критериям ЕГЭ.
    score_by_criteria = models.JSONField(default=dict, blank=True)
    total_score = models.PositiveSmallIntegerField(null=True, blank=True)
    lost_points = models.PositiveSmallIntegerField(null=True, blank=True)
    comment = models.TextField(blank=True)
    # Типы misconception; допускаются строки или записи
    # {"node_id": <id>, "error_type": <choice>}.
    error_tags = models.JSONField(default=list, blank=True)
    related_nodes = models.ManyToManyField("knowledge.KnowledgeNode", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
