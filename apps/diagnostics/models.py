from django.db import models


class DiagnosticTest(models.Model):
    """Входная диагностика / стартовый пробник."""

    title = models.CharField(max_length=200)
    assignments = models.ManyToManyField("content.Assignment", related_name="diagnostic_tests")
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.title


class DiagnosticResult(models.Model):
    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress"
        COMPLETED = "completed"

    student = models.ForeignKey(
        "accounts.StudentProfile", on_delete=models.CASCADE, related_name="diagnostic_results"
    )
    test = models.ForeignKey(DiagnosticTest, on_delete=models.CASCADE, related_name="results")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.IN_PROGRESS)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    primary_score = models.PositiveSmallIntegerField(default=0)
    estimated_score = models.PositiveSmallIntegerField(null=True, blank=True)  # scaled 0-100
