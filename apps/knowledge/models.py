from django.db import models


class TopicCluster(models.Model):
    """Coarse topic grouping (e.g. 'Планиметрия'), maps to EGE task numbers."""

    title = models.CharField(max_length=200)
    # Relative weight of the cluster in the exam (used by plan builder / forecast).
    exam_weight = models.FloatField(default=1.0)
    order = models.PositiveSmallIntegerField(default=0)

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
    """Per-student mastery 0-100 for one node. Not in the original entity list,
    but required to store the knowledge-map state per student."""

    class Status(models.TextChoices):
        NOT_STARTED = "not_started"
        IN_PROGRESS = "in_progress"
        PRACTICED = "practiced"
        MASTERED = "mastered"

    student = models.ForeignKey(
        "accounts.StudentProfile", on_delete=models.CASCADE, related_name="masteries"
    )
    node = models.ForeignKey(KnowledgeNode, on_delete=models.CASCADE, related_name="masteries")
    mastery = models.FloatField(default=0)  # 0..100
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.NOT_STARTED)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["student", "node"], name="uniq_student_node")
        ]

    def refresh_status(self):
        if self.mastery >= 70:
            self.status = self.Status.MASTERED
        elif self.mastery >= 40:
            self.status = self.Status.PRACTICED
        elif self.mastery > 0:
            self.status = self.Status.IN_PROGRESS
        else:
            self.status = self.Status.NOT_STARTED
