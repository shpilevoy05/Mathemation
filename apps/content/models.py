from django.core.exceptions import ValidationError
from django.db import models


class Lesson(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Черновик"
        PUBLISHED = "published", "Опубликован"
        ARCHIVED = "archived", "В архиве"

    class VideoProvider(models.TextChoices):
        KINESCOPE = "kinescope", "Kinescope"
        YOUTUBE = "youtube", "YouTube"
        VK = "vk", "VK Видео"
        RUTUBE = "rutube", "Rutube"
        OTHER = "other", "Другой"

    node = models.ForeignKey(
        "knowledge.KnowledgeNode", on_delete=models.CASCADE, related_name="lessons"
    )
    title = models.CharField(max_length=200)
    order = models.PositiveSmallIntegerField(default=0)
    # Видео живёт на хостинге (по умолчанию Kinescope): в поле кладут либо
    # идентификатор ролика, либо готовую ссылку.
    video_provider = models.CharField(
        max_length=16, choices=VideoProvider.choices, default=VideoProvider.KINESCOPE
    )
    video_url = models.CharField(max_length=500, blank=True)
    video_duration_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    # Черновик виден только методисту: урок собирают по частям, и ученик не
    # должен получить в плане пустую карточку.
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.title

    @property
    def is_published(self) -> bool:
        return self.status == self.Status.PUBLISHED

    def clean(self):
        """Ссылка на видео проверяется при сохранении, а не при показе.

        Поле заполняет методист, а результат исполняется в iframe на странице
        ученика: чужой хост здесь — это чужой код в нашем интерфейсе.
        """
        from .video import validate_video_url

        super().clean()
        validate_video_url(self.video_url)

    @property
    def has_video(self) -> bool:
        return bool((self.video_url or "").strip())


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

    class AnswerType(models.TextChoices):
        TEXT = "text", "Строка"
        NUMBER = "number", "Число"
        EXPRESSION = "expression", "Выражение"
        ROOT_SET = "root_set", "Множество корней"
        ROOT_FAMILIES = "root_families", "Семейства корней"

    lesson = models.ForeignKey(
        Lesson, on_delete=models.SET_NULL, null=True, blank=True, related_name="assignments"
    )
    title = models.CharField(max_length=200)
    statement = models.TextField()
    # Canonical short answer for part 1 auto-check; empty for part 2.
    correct_answer = models.CharField(max_length=200, blank=True)
    # Чем является ответ. Для тригонометрии это множество или семейства корней,
    # и сравнивать их как строки нельзя: «π/6+2πn» и «π/6+2πk» — один ответ.
    answer_type = models.CharField(
        max_length=16, choices=AnswerType.choices, default=AnswerType.TEXT
    )
    # Эталон в разобранном виде: {"families": [...]} или {"roots": [...]}.
    # Отдельно от `correct_answer`, потому что тот показывается человеку, а
    # это — данные для сравнения.
    answer_spec = models.JSONField(default=dict, blank=True)
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

    def clean(self):
        """Эталон проверяем при сохранении, а не при ответе ученика.

        Опечатка в эталоне тихо превращает верные ответы в неверные, а узнать
        об этом можно было бы только по жалобе.
        """
        from .answers import AnswerParseError, canonical_answer

        super().clean()
        if self.answer_type not in (
            self.AnswerType.ROOT_SET, self.AnswerType.ROOT_FAMILIES
        ):
            return
        try:
            canonical_answer(self.answer_spec or {})
        except AnswerParseError as error:
            raise ValidationError({"answer_spec": str(error)}) from error

    def check_answer(self, answer: str) -> bool | None:
        """Проверить ответ. `None` — «не разобрал», а не «неверно».

        Разница принципиальная: описка в записи не должна списываться ученику
        в незнание темы и заводить ошибку на полку.
        """
        from .answers import check

        return check(self.answer_type, self.answer_spec or {}, self.correct_answer, answer)



class SolutionPath(models.Model):
    """Эталонный путь решения задачи: упорядоченный список наблюдаемых шагов.

    Задача второй части решается не одним действием, а десятком. Плоский набор
    навыков у задачи отвечает на вопрос «что здесь может понадобиться», но не
    на вопрос «что именно сделал ученик», — а слабое место находится только во
    втором.

    Путей у задачи может быть несколько: канонический — тот, которому учим, и
    альтернативный — другой корректный маршрут. Решение, идущее альтернативным
    путём, не ошибка, и платформа должна уметь его узнать.
    """

    class PathType(models.TextChoices):
        CANONICAL = "canonical", "Канонический"
        ALTERNATIVE = "alternative", "Альтернативный"

    assignment = models.ForeignKey(
        Assignment, on_delete=models.CASCADE, related_name="solution_paths"
    )
    code = models.SlugField(max_length=64, unique=True)
    title = models.CharField(max_length=200)
    path_type = models.CharField(
        max_length=16, choices=PathType.choices, default=PathType.CANONICAL
    )
    # Как решается уравнение и как отбираются корни: две развилки, по которым
    # пути и различаются между собой.
    equation_stage = models.CharField(max_length=300, blank=True)
    selection_method = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["assignment_id", "order", "id"]

    def __str__(self):
        return f"{self.code}: {self.title}"

    @property
    def is_canonical(self) -> bool:
        return self.path_type == self.PathType.CANONICAL


class SolutionStep(models.Model):
    """Шаг эталонного пути: одно наблюдаемое действие и его вес как свидетельство.

    Роль и сила сигнала независимы (RULE-03 разметки): вспомогательный шаг
    может давать сильное свидетельство, если оно чистое и однозначное. Поэтому
    это два поля, а не одно «сколько весит».
    """

    class Stage(models.TextChoices):
        TRANSFORM = "transform", "Преобразование"
        EQUATION = "equation", "Решение простого уравнения"
        ALGEBRA = "algebra", "Алгебраическое решение"
        CONSTRAINTS = "constraints", "Ограничения и допустимость"
        SELECTION = "selection", "Отбор и проверка"
        CHECK = "check", "Контроль ответа"
        FORMAT = "format", "Оформление"

    class Role(models.TextChoices):
        PRIMARY = "primary", "Ключевой шаг"
        SUPPORTING = "supporting", "Вспомогательный шаг"

    class Signal(models.TextChoices):
        STRONG = "strong", "Сильный сигнал"
        WEAK = "weak", "Слабый сигнал"

    path = models.ForeignKey(SolutionPath, on_delete=models.CASCADE, related_name="steps")
    order = models.PositiveSmallIntegerField(default=1)
    stage = models.CharField(max_length=16, choices=Stage.choices, default=Stage.EQUATION)
    node = models.ForeignKey(
        "knowledge.KnowledgeNode", on_delete=models.PROTECT, related_name="solution_steps"
    )
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.PRIMARY)
    signal = models.CharField(max_length=16, choices=Signal.choices, default=Signal.STRONG)
    # Требуется ли шаг в корректном решении. Необязательный шаг может
    # отсутствовать, и это не ошибка.
    is_required = models.BooleanField(default=True)
    description = models.CharField(max_length=300)

    class Meta:
        ordering = ["path_id", "order"]
        constraints = [
            models.UniqueConstraint(fields=["path", "order"], name="uniq_step_order"),
        ]

    def __str__(self):
        return f"{self.path.code} #{self.order}: {self.description}"

    def clean(self):
        """Шаг указывает на навык, а не на папку: папка ничему не учит."""
        super().clean()
        if self.node_id and self.node.is_group:
            raise ValidationError(
                {"node": "Шаг должен указывать на навык, а не на папку навыков."}
            )


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


class LessonProgress(models.Model):
    """Где ученик находится внутри занятия по теме.

    Занятие проходится этапами: материал, задачи, отработка. Задачи и отработку
    можно посчитать по попыткам и полке ошибок, а вот «материал посмотрел»
    известно только от самого ученика — это единственное, что здесь хранится.
    """

    student = models.ForeignKey(
        "accounts.StudentProfile", on_delete=models.CASCADE, related_name="lesson_progress"
    )
    node = models.ForeignKey(
        "knowledge.KnowledgeNode", on_delete=models.CASCADE, related_name="lesson_progress"
    )
    material_viewed_at = models.DateTimeField(null=True, blank=True)
    summary_downloaded_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["student", "node"], name="uniq_lesson_progress_per_node"
            )
        ]

    def __str__(self):
        return f"{self.student_id} · {self.node_id}"


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
