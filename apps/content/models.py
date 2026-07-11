from django.db import models


class Lesson(models.Model):
    node = models.ForeignKey(
        "knowledge.KnowledgeNode", on_delete=models.CASCADE, related_name="lessons"
    )
    title = models.CharField(max_length=200)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.title


class TheoryBlock(models.Model):
    """Конспект/теория внутри урока (markdown)."""

    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="theory_blocks")
    title = models.CharField(max_length=200, blank=True)
    body = models.TextField()
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order"]


class Assignment(models.Model):
    class Part(models.IntegerChoices):
        PART1 = 1  # short answer, auto-checked
        PART2 = 2  # full solution, expert-checked

    lesson = models.ForeignKey(
        Lesson, on_delete=models.SET_NULL, null=True, blank=True, related_name="assignments"
    )
    title = models.CharField(max_length=200)
    statement = models.TextField()
    # Canonical short answer for part 1 auto-check; empty for part 2.
    correct_answer = models.CharField(max_length=200, blank=True)
    # Эталонное пошаговое решение: питает наводящие подсказки ИИ-наставника
    # (он объясняет из проверенного разбора, а не сочиняет) и проверку экспертов.
    reference_solution = models.TextField(blank=True)
    exam_part = models.PositiveSmallIntegerField(choices=Part.choices, default=Part.PART1)
    difficulty = models.PositiveSmallIntegerField(default=1)  # 1..5
    max_score = models.PositiveSmallIntegerField(default=1)
    skills = models.ManyToManyField(
        "knowledge.KnowledgeNode", through="AssignmentSkillTag", related_name="assignments"
    )

    def __str__(self):
        return self.title

    def check_answer(self, answer: str) -> bool:
        """Part 1 auto-check: normalized string/number comparison."""
        norm = lambda s: s.strip().lower().replace(",", ".").replace(" ", "")
        return norm(answer) == norm(self.correct_answer)


class AssignmentSkillTag(models.Model):
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name="skill_tags")
    node = models.ForeignKey("knowledge.KnowledgeNode", on_delete=models.CASCADE)
    weight = models.FloatField(default=1.0)  # contribution of this skill, 0..1

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["assignment", "node"], name="uniq_assignment_node")
        ]
