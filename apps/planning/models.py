from django.db import models


class Trajectory(models.Model):
    slug = models.SlugField(max_length=32, unique=True)
    title = models.CharField(max_length=64)
    target_min = models.PositiveSmallIntegerField()
    target_max = models.PositiveSmallIntegerField()
    weekly_load_hours = models.PositiveSmallIntegerField(default=6)
    description = models.TextField(blank=True)
    config = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["target_min"]

    def __str__(self):
        return self.title


class StudyPlan(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active"
        ARCHIVED = "archived"

    student = models.ForeignKey(
        "accounts.StudentProfile", on_delete=models.CASCADE, related_name="study_plans"
    )
    target_score = models.PositiveSmallIntegerField()
    trajectory = models.ForeignKey(
        Trajectory,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="study_plans",
    )
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
    # Узел, из-за которого изменился план: по нему же гасится повторный шум.
    node = models.ForeignKey(
        "knowledge.KnowledgeNode", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="plan_changes",
    )
    reason = models.CharField(max_length=32, choices=Reason.choices)
    description = models.TextField(blank=True)
    is_major = models.BooleanField(default=False)
    acknowledged = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class TrajectoryTransition(models.Model):
    student = models.ForeignKey(
        "accounts.StudentProfile",
        on_delete=models.CASCADE,
        related_name="trajectory_transitions",
    )
    from_trajectory = models.ForeignKey(
        Trajectory,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="transitions_from",
    )
    to_trajectory = models.ForeignKey(
        Trajectory,
        on_delete=models.PROTECT,
        related_name="transitions_to",
    )
    reasons = models.JSONField(default=list)
    recovery_actions = models.JSONField(default=list)
    acknowledged = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
