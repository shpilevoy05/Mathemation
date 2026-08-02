from django.db import models


class GamificationProfile(models.Model):
    student = models.OneToOneField(
        "accounts.StudentProfile",
        on_delete=models.CASCADE,
        related_name="gamification_profile",
    )
    xp = models.PositiveIntegerField(default=0)
    level = models.PositiveIntegerField(default=1)
    streak_current = models.PositiveIntegerField(default=0)
    streak_best = models.PositiveIntegerField(default=0)
    streak_period_anchor = models.DateField(null=True, blank=True)
    # Заморозки, купленные в магазине: одна закрывает один пропущенный период,
    # чтобы серия не сгорала из-за болезни или поездки.
    streak_freezes = models.PositiveSmallIntegerField(default=0)
    streak_frozen_periods = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.student}: {self.xp} XP"


class WeeklyQuest(models.Model):
    class QuestType(models.TextChoices):
        SOLVE_TASKS = "solve_tasks", "Решить задачи"
        COMPLETE_REVIEWS = "complete_reviews", "Завершить повторы"
        FINISH_PLAN_ITEMS = "finish_plan_items", "Выполнить пункты плана"

    student = models.ForeignKey(
        "accounts.StudentProfile",
        on_delete=models.CASCADE,
        related_name="weekly_quests",
    )
    week_start = models.DateField()
    title = models.CharField(max_length=160)
    quest_type = models.CharField(max_length=32, choices=QuestType.choices)
    target_count = models.PositiveIntegerField()
    progress_count = models.PositiveIntegerField(default=0)
    completed = models.BooleanField(default=False)
    reward_xp = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["week_start", "quest_type"]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "week_start", "quest_type"],
                name="unique_student_weekly_quest_type",
            )
        ]

    def __str__(self):
        return f"{self.student}: {self.title} ({self.week_start})"

