from django.db import models


class MockExam(models.Model):
    title = models.CharField(max_length=200)
    assignments = models.ManyToManyField("content.Assignment", related_name="mock_exams")
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.title


class MockExamResult(models.Model):
    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress"
        # Part 1 checked automatically; part 2 may still be with an expert.
        PART1_CHECKED = "part1_checked"
        COMPLETED = "completed"

    student = models.ForeignKey(
        "accounts.StudentProfile", on_delete=models.CASCADE, related_name="mock_results"
    )
    exam = models.ForeignKey(MockExam, on_delete=models.CASCADE, related_name="results")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.IN_PROGRESS)
    primary_score = models.PositiveSmallIntegerField(default=0)
    scaled_score = models.PositiveSmallIntegerField(null=True, blank=True)  # 0-100
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
