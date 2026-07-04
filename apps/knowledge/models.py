from django.db import models
from django.utils import timezone


class TopicCluster(models.Model):
    """Coarse topic grouping (e.g. 'Планиметрия'), maps to EGE task numbers."""

    title = models.CharField(max_length=200)
    # Relative weight of the cluster in the exam (used by plan builder / forecast).
    exam_weight = models.FloatField(default=1.0)
    order = models.PositiveSmallIntegerField(default=0)
    # Цвет темы на «дорожке» (hex, как в Дуолинго — своя палитра на кластер).
    color = models.CharField(max_length=7, default="#58cc02")

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.title


class KnowledgeNode(models.Model):
    """Granular skill in the knowledge map."""

    class Part(models.IntegerChoices):
        PART1 = 1
        PART2 = 2

    code = models.SlugField(max_length=64, unique=True)
    title = models.CharField(max_length=200)
    cluster = models.ForeignKey(TopicCluster, on_delete=models.CASCADE, related_name="nodes")
    weight = models.FloatField(default=1.0)
    exam_part = models.PositiveSmallIntegerField(choices=Part.choices, default=Part.PART1)
    # К каким номерам ЕГЭ относится навык, например [6, 12].
    ege_task_numbers = models.JSONField(default=list, blank=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["cluster__order", "order"]

    def __str__(self):
        return f"{self.code}: {self.title}"


class KnowledgeDependency(models.Model):
    """`prerequisite` must be learned before `node`."""

    node = models.ForeignKey(KnowledgeNode, on_delete=models.CASCADE, related_name="dependencies")
    prerequisite = models.ForeignKey(
        KnowledgeNode, on_delete=models.CASCADE, related_name="dependents"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["node", "prerequisite"], name="uniq_dependency")
        ]


class SkillMastery(models.Model):
    """Per-student mastery 0-100 for one node.

    `peak_mastery`/`peak_at` fix the level at the moment of the last practice;
    the effective (decayed) value is recomputed from them idempotently, so the
    forgetting curve can be re-applied after every session/mock or by cron.
    """

    class Status(models.TextChoices):
        NOT_STARTED = "not_started"
        IN_PROGRESS = "in_progress"
        PRACTICED = "practiced"
        MASTERED = "mastered"
        DECAYED = "decayed"  # «подзабылось»: было освоено, но остыло

    student = models.ForeignKey(
        "accounts.StudentProfile", on_delete=models.CASCADE, related_name="masteries"
    )
    node = models.ForeignKey(KnowledgeNode, on_delete=models.CASCADE, related_name="masteries")
    mastery = models.FloatField(default=0)  # текущее (с учётом забывания), 0..100
    peak_mastery = models.FloatField(default=0)  # уровень на момент последней практики
    peak_at = models.DateTimeField(default=timezone.now)
    last_practiced_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.NOT_STARTED)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["student", "node"], name="uniq_student_node")
        ]

    @property
    def decay_percent(self) -> float:
        """Индикатор забывания: сколько % от пика уже потеряно."""
        if self.peak_mastery <= 0:
            return 0.0
        return round(100 * (1 - self.mastery / self.peak_mastery), 1)

    def refresh_status(self):
        was_mastered = self.status in (self.Status.MASTERED, self.Status.DECAYED)
        if self.mastery >= 70:
            self.status = self.Status.MASTERED
        elif was_mastered and self.peak_mastery >= 70:
            # Тема была освоена, но mastery упал из-за забывания/ошибок.
            self.status = self.Status.DECAYED
        elif self.mastery >= 40:
            self.status = self.Status.PRACTICED
        elif self.mastery > 0:
            self.status = self.Status.IN_PROGRESS
        else:
            self.status = self.Status.NOT_STARTED
