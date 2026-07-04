from django.db import models


class StudyPlan(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active"
        ARCHIVED = "archived"

    student = models.ForeignKey(
        "accounts.StudentProfile", on_delete=models.CASCADE, related_name="study_plans"
    )
    target_score = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)


class StudyPlanItem(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending"
        IN_PROGRESS = "in_progress"
        DONE = "done"

    class ItemType(models.TextChoices):
        LESSON = "lesson"
        PRACTICE = "practice"
        REVIEW = "review"
        MOCK = "mock"

    plan = models.ForeignKey(StudyPlan, on_delete=models.CASCADE, related_name="items")
    node = models.ForeignKey(
        "knowledge.KnowledgeNode", on_delete=models.CASCADE, null=True, blank=True
    )
    item_type = models.CharField(max_length=16, choices=ItemType.choices, default=ItemType.LESSON)
    order = models.PositiveIntegerField(default=0)
    # Scheduling: week index from plan start + concrete due date for day plans.
    week_index = models.PositiveSmallIntegerField(default=0)
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)

    class Meta:
        ordering = ["order"]


class PlanChangeLog(models.Model):
    """«Карточка изменений плана»: что поменялось, когда и почему.

    `is_major` — резкое изменение (плохой пробник, частые ошибки, простой),
    показывается ученику большим всплывающим окном, пока не подтверждено.
    """

    class Reason(models.TextChoices):
        INACTIVITY = "inactivity"
        POOR_MOCK = "poor_mock"
        FREQUENT_MISTAKES = "frequent_mistakes"
        DECAY = "decay"  # тема подзабылась и вернулась в план
        MANUAL = "manual"

    plan = models.ForeignKey(StudyPlan, on_delete=models.CASCADE, related_name="change_logs")
    reason = models.CharField(max_length=32, choices=Reason.choices)
    description = models.TextField(blank=True)
    is_major = models.BooleanField(default=False)
    acknowledged = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
