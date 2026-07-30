from django.db import models


class Lesson(models.Model):
    node = models.ForeignKey(
        "knowledge.KnowledgeNode", on_delete=models.CASCADE, related_name="lessons"
    )
    title = models.CharField(max_length=200)
    order = models.PositiveSmallIntegerField(default=0)
    video_url = models.URLField(blank=True)
    video_duration_minutes = models.PositiveSmallIntegerField(null=True, blank=True)

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


class Homework(models.Model):
    """Домашнее задание к уроку: набор задач и срок сдачи.

    Домашка не подменяет план: план ведёт по зависимостям графа, домашка
    выдаётся адресно — ученику или группе.
    """

    class Status(models.TextChoices):
        DRAFT = "draft"
        PUBLISHED = "published"
        CLOSED = "closed"

    lesson = models.ForeignKey(
        Lesson, on_delete=models.CASCADE, related_name="homeworks", null=True, blank=True
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    assignments = models.ManyToManyField(
        "Assignment", through="HomeworkTask", related_name="homeworks"
    )
    due_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="created_homeworks",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    @property
    def is_published(self) -> bool:
        return self.status == self.Status.PUBLISHED


class HomeworkTask(models.Model):
    homework = models.ForeignKey(Homework, on_delete=models.CASCADE, related_name="tasks")
    assignment = models.ForeignKey("Assignment", on_delete=models.CASCADE)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["homework", "assignment"], name="uniq_homework_assignment"
            )
        ]


class HomeworkSubmission(models.Model):
    """Выдача домашки ученику и её состояние.

    Ответы остаются обычными `Attempt`: домашка не заводит вторую систему
    проверки, вторая часть по-прежнему уходит эксперту.
    """

    class Status(models.TextChoices):
        ASSIGNED = "assigned"
        IN_PROGRESS = "in_progress"
        SUBMITTED = "submitted"
        CHECKED = "checked"

    homework = models.ForeignKey(
        Homework, on_delete=models.CASCADE, related_name="submissions"
    )
    student = models.ForeignKey(
        "accounts.StudentProfile", on_delete=models.CASCADE, related_name="homeworks"
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.ASSIGNED
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    checked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-assigned_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["homework", "student"], name="uniq_homework_student"
            )
        ]


class DailyChallenge(models.Model):
    """Задание дня: одна задача на дату с наградой.

    Живёт рядом с планом, а не вместо него: план ведёт по зависимостям,
    задание дня — короткая привычка возвращаться в сервис.
    """

    date = models.DateField(unique=True)
    title = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    assignment = models.ForeignKey(
        "Assignment", on_delete=models.PROTECT, related_name="daily_challenges"
    )
    reward_xp = models.PositiveSmallIntegerField(default=20)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="created_challenges",
    )

    class Meta:
        ordering = ["-date"]

    def __str__(self):
        return f"Задание дня {self.date}"


class AssignmentVersion(models.Model):
    """Снимок задания на момент, когда его видел ученик.

    Условие и эталонный разбор правятся: находят опечатку, уточняют
    формулировку. Если править на месте, история попыток начинает врать —
    ученик решал одно, а в отчёте и в калибровке прогноза учитывается другое.
    """

    assignment = models.ForeignKey(
        Assignment, on_delete=models.CASCADE, related_name="versions"
    )
    number = models.PositiveSmallIntegerField()
    statement = models.TextField()
    correct_answer = models.CharField(max_length=200, blank=True)
    reference_solution = models.TextField(blank=True)
    max_score = models.PositiveSmallIntegerField(default=1)
    difficulty = models.PositiveSmallIntegerField(default=1)
    change_note = models.CharField(max_length=300, blank=True)
    created_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="assignment_versions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["assignment_id", "-number"]
        constraints = [
            models.UniqueConstraint(
                fields=["assignment", "number"], name="uniq_assignment_version"
            )
        ]

    def __str__(self):
        return f"{self.assignment_id} v{self.number}"


class AssignmentSkillTag(models.Model):
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name="skill_tags")
    node = models.ForeignKey("knowledge.KnowledgeNode", on_delete=models.CASCADE)
    weight = models.FloatField(default=1.0)  # contribution of this skill, 0..1

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["assignment", "node"], name="uniq_assignment_node")
        ]
