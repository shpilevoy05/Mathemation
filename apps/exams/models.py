"""Профиль экзамена: структура заданий и таблица перевода баллов.

Раньше прогноз строился по банку задач и нормировался на его суммарный балл,
поэтому загрузка десяти лёгких задач поднимала прогноз всем ученикам, не
сделавшим ни одной попытки (замер на демо-данных: +10 тестовых баллов).
Профиль фиксирует структуру экзамена на год, и прогноз перестаёт зависеть от
работы контент-редактора.

У каждого задания свой номер, часть, максимальный балл, сложность и набор
узлов графа; сумма баллов заданий и есть максимальный первичный балл, поэтому
нормировка в движке выключается. Таблица перевода тоже живёт в профиле: после
её смены старые снапшоты остаются интерпретируемыми.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models


class ExamProfile(models.Model):
    """Конфигурация экзамена на конкретный год."""

    year = models.PositiveSmallIntegerField(unique=True)
    title = models.CharField(max_length=200)
    max_primary_score = models.PositiveSmallIntegerField()
    # Официальная таблица перевода: индекс — первичный балл, значение — тестовый.
    primary_to_scaled = models.JSONField(default=list)
    # Активным может быть только один профиль: по нему считается прогноз.
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-year"]
        constraints = [
            models.UniqueConstraint(
                fields=["is_active"],
                condition=models.Q(is_active=True),
                name="uniq_active_exam_profile",
            )
        ]

    def __str__(self):
        return f"{self.title} ({self.year})"

    def clean(self):
        table = self.primary_to_scaled or []
        if len(table) != self.max_primary_score + 1:
            raise ValidationError(
                {
                    "primary_to_scaled": (
                        "В таблице должно быть %d значений (0..%d первичных баллов), "
                        "получено %d."
                        % (self.max_primary_score + 1, self.max_primary_score, len(table))
                    )
                }
            )

    def scaled_for(self, primary: float) -> int:
        """Тестовый балл по первичному; вне таблицы — обрезается по краям."""
        table = self.primary_to_scaled or [0]
        index = min(max(int(round(primary)), 0), len(table) - 1)
        return int(table[index])

    @classmethod
    def active(cls) -> "ExamProfile | None":
        return (
            cls.objects.filter(is_active=True)
            .prefetch_related("tasks__skills")
            .first()
        )


class ExamTask(models.Model):
    """Задание экзамена: номер, часть, вес в баллах и связь с навыками."""

    class Part(models.IntegerChoices):
        PART1 = 1
        PART2 = 2

    profile = models.ForeignKey(ExamProfile, on_delete=models.CASCADE, related_name="tasks")
    number = models.PositiveSmallIntegerField()
    exam_part = models.PositiveSmallIntegerField(choices=Part.choices, default=Part.PART1)
    max_score = models.PositiveSmallIntegerField(default=1)
    # 1..5; задаёт порог логистической кривой P(верно) от mastery.
    difficulty = models.PositiveSmallIntegerField(default=3)
    # Через ExamTaskSkill, чтобы у связи был вес; сами связи доступны как
    # `task.skills` (reverse от through-модели).
    nodes = models.ManyToManyField(
        "knowledge.KnowledgeNode", through="ExamTaskSkill", related_name="exam_tasks"
    )

    class Meta:
        ordering = ["number"]
        constraints = [
            models.UniqueConstraint(fields=["profile", "number"], name="uniq_profile_task")
        ]

    def __str__(self):
        return f"№{self.number} ({self.max_score} б.)"


class ExamTaskSkill(models.Model):
    """Вклад узла графа в задание (0..1], как AssignmentSkillTag."""

    task = models.ForeignKey(ExamTask, on_delete=models.CASCADE, related_name="skills")
    node = models.ForeignKey("knowledge.KnowledgeNode", on_delete=models.CASCADE)
    weight = models.FloatField(default=1.0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["task", "node"], name="uniq_task_node")
        ]
