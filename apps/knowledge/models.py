from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator
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
    """Навык в карте знаний — либо атомарный, либо папка над атомарными.

    Папка («Отбор корней», «ОДЗ и равносильность») существует, потому что так
    устроена методическая разметка: у неё есть имя и место в карте, но нет
    собственной практики. Освоение она не получает напрямую — оно считается по
    детям, а в план она не попадает: занятия по папке не существует.
    """

    class Part(models.IntegerChoices):
        PART1 = 1
        PART2 = 2

    class NodeType(models.TextChoices):
        ATOMIC = "atomic", "Навык"
        GROUP = "group", "Папка"

    class SkillClass(models.TextChoices):
        PROCEDURAL = "procedural", "Приём"
        REASONING = "reasoning", "Рассуждение"
        CROSS_CUTTING = "cross_cutting", "Сквозной навык"
        PROOF = "proof", "Обоснование"
        FORMATTING = "formatting", "Оформление"
        CONCEPT_GROUP = "concept_group", "Понятийная группа"

    class Layer(models.TextChoices):
        SUBJECT = "subject", "Предмет"
        EXAM_READINESS = "exam_readiness", "Экзаменационное оформление"

    class AssessmentMode(models.TextChoices):
        DETERMINISTIC = "deterministic", "Проверяется автоматически"
        RUBRIC = "rubric", "Проверяется экспертом"

    class GroupAggregation(models.TextChoices):
        AVERAGE = "average", "Среднее по детям"
        MINIMUM = "minimum", "Минимум по детям"

    code = models.SlugField(max_length=64, unique=True)
    title = models.CharField(max_length=200)
    cluster = models.ForeignKey(TopicCluster, on_delete=models.CASCADE, related_name="nodes")
    # Папка над навыком. Иерархия ровно на один уровень: папка не вкладывается
    # в папку — так устроена разметка, и глубже её никто не ведёт.
    parent = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="children"
    )
    node_type = models.CharField(
        max_length=16, choices=NodeType.choices, default=NodeType.ATOMIC
    )
    skill_class = models.CharField(
        max_length=16, choices=SkillClass.choices, default=SkillClass.PROCEDURAL
    )
    # Оформление ответа тоже стоит баллов, но предметное освоение оно менять не
    # должно: забытая подпись пунктов не означает, что тема забыта.
    layer = models.CharField(max_length=16, choices=Layer.choices, default=Layer.SUBJECT)
    assessment_mode = models.CharField(
        max_length=16, choices=AssessmentMode.choices, default=AssessmentMode.DETERMINISTIC
    )
    # Как складывается освоение папки из детей. Выбор методический: по минимуму
    # папка закрывается по самому слабому ребёнку, по среднему — раньше.
    group_aggregation = models.CharField(
        max_length=16, choices=GroupAggregation.choices, default=GroupAggregation.AVERAGE
    )
    weight = models.FloatField(default=1.0)
    exam_part = models.PositiveSmallIntegerField(choices=Part.choices, default=Part.PART1)
    # К каким номерам ЕГЭ относится навык, например [6, 12].
    ege_task_numbers = models.JSONField(default=list, blank=True)
    # Навык из другого раздела, нужный как предпосылка (логарифмы внутри
    # тригонометрической задачи). В прогноз по номеру своей задачи он не идёт:
    # иначе номер получал бы баллы за чужое умение.
    is_cross_domain = models.BooleanField(default=False)
    # Часы на освоение узла. 0 — дефолт по части экзамена: тема второй части
    # дороже короткой задачи первой. Используется планом и потолком.
    hours_estimate = models.FloatField(default=0)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["cluster__order", "order"]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(parent=models.F("id")), name="no_self_parent"
            ),
        ]

    def __str__(self):
        return f"{self.code}: {self.title}"

    @property
    def is_group(self) -> bool:
        return self.node_type == self.NodeType.GROUP

    def clean(self):
        """Иерархия ровно на один уровень, и родитель — только папка."""
        super().clean()
        if self.parent_id is None:
            return
        if self.parent_id == self.pk:
            raise ValidationError(f"Узел «{self.code}» не может быть родителем самому себе.")
        if not self.parent.is_group:
            raise ValidationError(
                f"Родителем может быть только папка, а «{self.parent.code}» — навык."
            )
        if self.is_group:
            raise ValidationError("Папка не вкладывается в папку: иерархия на один уровень.")

    @property
    def effective_hours(self) -> float:
        """Оценка часов: своя, иначе дефолт по части экзамена."""
        if self.hours_estimate and self.hours_estimate > 0:
            return float(self.hours_estimate)
        return float(
            settings.HOURS_PER_NODE_BY_PART.get(self.exam_part, settings.HOURS_PER_NODE)
        )


class KnowledgeDependency(models.Model):
    """Связь между навыками. Два вида, и это разные обещания ученику.

    Обязательная связь — ворота: пока предшественник не освоен до порога, тема
    закрыта. Поддерживающая — только порядок и объяснение «почему сейчас
    именно это»: она помогает понять, но не запрещает начинать.

    Разделение не косметическое. В методической разметке поддерживающих связей
    треть, и если считать их воротами, граф захлопнется: простейшие уравнения
    окажутся закрыты до освоения обратных функций, которые для них не нужны.
    """

    class Kind(models.TextChoices):
        PREREQUISITE = "prerequisite", "Обязательная"
        SUPPORTS = "supports", "Поддерживающая"

    node = models.ForeignKey(KnowledgeNode, on_delete=models.CASCADE, related_name="dependencies")
    prerequisite = models.ForeignKey(
        KnowledgeNode, on_delete=models.CASCADE, related_name="dependents"
    )
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.PREREQUISITE)
    min_mastery = models.PositiveSmallIntegerField(
        default=70,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name="минимальное освоение, %",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["node", "prerequisite"], name="uniq_dependency"),
            models.CheckConstraint(
                condition=~models.Q(node=models.F("prerequisite")),
                name="no_self_dependency",
            ),
        ]

    @property
    def is_gate(self) -> bool:
        """Закрывает ли связь тему до освоения предшественника."""
        return self.kind == self.Kind.PREREQUISITE

    def clean(self):
        """Не дать замкнуть граф.

        Цикл раньше проходил молча: топологический порядок дописывал остаток
        в конец, а планировщик и потолок считали по искажённому порядку без
        единой ошибки.

        Проверяем только обязательные связи: порядок изучения задают они, а
        поддерживающие могут быть и взаимными — «одно помогает понять другое»
        в обе стороны это нормальное методическое утверждение.
        """
        if self.node_id is None or self.prerequisite_id is None:
            return
        if self.node_id == self.prerequisite_id:
            raise ValidationError(f"Узел «{self.node}» не может зависеть сам от себя.")
        # Папка складывается из детей и сама ничему не учит: связь с ней ничего
        # не открывает и не закрывает. Разметка ведёт связи между навыками.
        if self.node.is_group or self.prerequisite.is_group:
            raise ValidationError("Связи ведутся между навыками, а не папками.")
        if not self.is_gate:
            return

        from .services import would_create_cycle

        if would_create_cycle(self.node, self.prerequisite, exclude_dependency_id=self.pk):
            raise ValidationError(
                f"Зависимость «{self.prerequisite}» → «{self.node}» создаёт цикл."
            )

    def save(self, *args, **kwargs):
        # Граф проверяется при любом сохранении, а не только через формы.
        self.full_clean()
        return super().save(*args, **kwargs)


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
