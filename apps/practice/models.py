from django.db import models


class Attempt(models.Model):
    class Context(models.TextChoices):
        LESSON = "lesson"
        DIAGNOSTIC = "diagnostic"
        MOCK = "mock"
        REVIEW = "review"  # интервальная отработка ошибок

    student = models.ForeignKey(
        "accounts.StudentProfile", on_delete=models.CASCADE, related_name="attempts"
    )
    assignment = models.ForeignKey(
        "content.Assignment", on_delete=models.CASCADE, related_name="attempts"
    )
    # Версия задания, которую видел ученик: условие правится, история — нет.
    assignment_version = models.ForeignKey(
        "content.AssignmentVersion", on_delete=models.PROTECT,
        null=True, blank=True, related_name="attempts",
    )
    context = models.CharField(max_length=16, choices=Context.choices, default=Context.LESSON)
    submitted_answer = models.CharField(max_length=500, blank=True)
    # None for part-2 attempts until expert review resolves them.
    is_correct = models.BooleanField(null=True)
    diagnostic_result = models.ForeignKey(
        "diagnostics.DiagnosticResult", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="attempts",
    )
    mock_result = models.ForeignKey(
        "mocks.MockExamResult", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="attempts",
    )
    created_at = models.DateTimeField(auto_now_add=True)


class MistakeBacklogItem(models.Model):
    class Status(models.TextChoices):
        OPEN = "open"
        IN_REVIEW = "in_review"  # queued for spaced repetition
        RESOLVED = "resolved"

    class ErrorType(models.TextChoices):
        ALGEBRAIC_SLIP = "algebraic_slip"
        ARITHMETIC_SLIP = "arithmetic_slip"
        WRONG_METHOD = "wrong_method"
        INCOMPLETE_ARGUMENT = "incomplete_argument"
        RUBRIC_MISS = "rubric_miss"
        GRAPH_MISREAD = "graph_misread"
        MISREAD_CONDITION = "misread_condition"
        UNKNOWN = "unknown"

    student = models.ForeignKey(
        "accounts.StudentProfile", on_delete=models.CASCADE, related_name="mistake_backlog"
    )
    assignment = models.ForeignKey("content.Assignment", on_delete=models.CASCADE)
    node = models.ForeignKey("knowledge.KnowledgeNode", on_delete=models.CASCADE)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    error_count = models.PositiveSmallIntegerField(default=1)
    error_type = models.CharField(
        max_length=32,
        choices=ErrorType.choices,
        default=ErrorType.UNKNOWN,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)


class ReviewSchedule(models.Model):
    """Интервальный повтор для одного пункта backlog: 1/3/7/30 дней."""

    class Status(models.TextChoices):
        PENDING = "pending"
        COMPLETED = "completed"
        MISSED = "missed"

    backlog_item = models.ForeignKey(
        MistakeBacklogItem, on_delete=models.CASCADE, related_name="reviews"
    )
    interval_days = models.PositiveSmallIntegerField()
    due_date = models.DateField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)

    class Meta:
        ordering = ["due_date"]
