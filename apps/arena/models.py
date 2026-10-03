"""Арена: друзья и соревновательные партии.

Зачем это в учебной платформе: подготовка к экзамену — это месяцы одиночной
работы, и главная причина бросить — не сложность, а скука. Соревнование даёт
короткий цикл «сыграл — увидел результат», которого нет у плана на полгода.

Три правила, из которых выведена вся модель:

* партия не подменяет учёбу. Ответы в арене пишутся в общий журнал попыток, но
  освоение тем не двигают: скорость под таймером — свидетельство собранности,
  а не понимания, и учить план по ней нельзя;
* соперник-бот честен. Его прогон разыгрывается один раз при создании партии и
  не зависит от того, как играет человек: бот, который «подстраивается», — это
  не соперник, а декорация;
* результат считает сервер. Ответ, время и очки приходят не от клиента, иначе
  первая же партия превратится в состязание по правке JavaScript.
"""

from __future__ import annotations

from django.db import models
from django.utils import timezone


class Friendship(models.Model):
    """Заявка в друзья и сама дружба — одной записью.

    Дружба симметрична, поэтому пара хранится один раз, а порядок
    «кто кого позвал» остаётся в полях: он нужен, чтобы показать заявку тому,
    кто её получил.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Заявка отправлена"
        ACCEPTED = "accepted", "В друзьях"
        DECLINED = "declined", "Отклонено"

    from_student = models.ForeignKey(
        "accounts.StudentProfile", on_delete=models.CASCADE, related_name="friend_requests_sent"
    )
    to_student = models.ForeignKey(
        "accounts.StudentProfile", on_delete=models.CASCADE, related_name="friend_requests_received"
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    answered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["from_student", "to_student"], name="uniq_friendship_pair"
            ),
            models.CheckConstraint(
                condition=~models.Q(from_student=models.F("to_student")),
                name="no_self_friendship",
            ),
        ]

    def __str__(self):
        return f"{self.from_student} → {self.to_student} ({self.status})"


class Match(models.Model):
    """Партия: набор задач, два участника и правило подсчёта очков."""

    class Mode(models.TextChoices):
        SPEED = "speed", "Нарешивание на скорость"
        QUIZ = "quiz", "Квиз по теории"
        BOARD = "board", "Своя игра"

    class Limit(models.TextChoices):
        """Чем кончается нарешивание: набором задач или временем.

        Это два разных состязания. «Кто быстрее решит восемь» награждает
        скорость на дистанции, «кто больше решит за три минуты» — плотность
        работы. В первом варианте отставший всё равно дорешивает до конца, во
        втором таймер останавливает обоих одновременно.
        """

        QUESTIONS = "questions", "До набора задач"
        TIME = "time", "На время"

    class Status(models.TextChoices):
        INVITED = "invited", "Приглашение отправлено"
        # Оба согласились, но партия ещё не началась: ждём, пока каждый
        # откроет экран. Иначе таймер идёт у того, кого ещё нет за столом.
        LOBBY = "lobby", "Сбор игроков"
        ACTIVE = "active", "Идёт"
        FINISHED = "finished", "Завершена"
        DECLINED = "declined", "Отклонена"
        CANCELLED = "cancelled", "Отменена"

    mode = models.CharField(max_length=16, choices=Mode.choices, default=Mode.SPEED)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    created_by = models.ForeignKey(
        "accounts.StudentProfile", on_delete=models.CASCADE, related_name="matches_created"
    )
    # Номер задания ЕГЭ, если партия по конкретному прототипу. Пусто — случайный
    # набор: «просто поиграть» тоже нужно.
    ege_task_number = models.PositiveSmallIntegerField(null=True, blank=True)
    # Уровень бота 1..5. У партии с человеком не заполняется.
    bot_level = models.PositiveSmallIntegerField(null=True, blank=True)
    seconds_per_question = models.PositiveSmallIntegerField(default=90)
    limit_kind = models.CharField(
        max_length=16, choices=Limit.choices, default=Limit.QUESTIONS
    )
    # Общий лимит партии в режиме «на время». Ноль — лимита нет.
    time_limit_seconds = models.PositiveSmallIntegerField(default=0)
    # Чей ход в «своей игре». В остальных режимах не используется: там
    # очередности нет, оба играют одновременно.
    turn_participant = models.ForeignKey(
        "MatchParticipant", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+",
    )
    # Рейтинговая партия — только подбор случайного соперника: вызов друга и
    # игра с ботом на рейтинг не влияют.
    is_ranked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    # Номер состояния: растёт при каждом изменении партии. По нему экран
    # понимает, что смотреть нечего, и не тянет состояние целиком — на живой
    # партии подавляющее большинство опросов не приносят новостей.
    revision = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"], name="match_status_recent"),
        ]

    def __str__(self):
        return f"{self.get_mode_display()} #{self.pk}"

    def save(self, *args, **kwargs):
        """Любое изменение партии двигает номер состояния.

        Считать вручную нельзя: одна забытая отметка — и экран игрока навсегда
        застревает на старом состоянии, потому что сервер честно отвечает
        «изменений нет». Поэтому номер двигается здесь, а не в сервисах.
        """
        fields = kwargs.get("update_fields")
        if self.pk and fields is not None and "revision" not in fields:
            self.revision = models.F("revision") + 1
            kwargs["update_fields"] = [*fields, "revision"]
            super().save(*args, **kwargs)
            self.refresh_from_db(fields=["revision"])
            return
        super().save(*args, **kwargs)

    def touch(self) -> None:
        """Отметить изменение, пришедшее со стороны участника или вопроса."""
        type(self).objects.filter(pk=self.pk).update(revision=models.F("revision") + 1)

    @property
    def is_finished(self) -> bool:
        return self.status == self.Status.FINISHED

    @property
    def is_running(self) -> bool:
        return self.status == self.Status.ACTIVE

    @property
    def is_waiting(self) -> bool:
        """Партия собрана, но ещё не началась: ждём игроков."""
        return self.status in (self.Status.INVITED, self.Status.LOBBY)

    @property
    def is_over(self) -> bool:
        return self.status in (
            self.Status.FINISHED, self.Status.DECLINED, self.Status.CANCELLED
        )

    @property
    def against_bot(self) -> bool:
        return self.bot_level is not None

    @property
    def is_theory(self) -> bool:
        """Режимы по теории: спрашивают знание, а не решение задачи."""
        return self.mode in (self.Mode.QUIZ, self.Mode.BOARD)


class MatchChild(models.Model):
    """Запись, принадлежащая партии.

    Любое сохранение двигает номер состояния партии: экран узнаёт о новостях
    по нему, а не по времени.
    """

    class Meta:
        abstract = True

    def match_pk(self) -> int | None:
        return self.match_id

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        match_pk = self.match_pk()
        if match_pk:
            Match.objects.filter(pk=match_pk).update(revision=models.F("revision") + 1)


class MatchParticipant(MatchChild):
    """Сторона партии. Бот — участник без профиля ученика."""

    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="participants")
    student = models.ForeignKey(
        "accounts.StudentProfile", on_delete=models.CASCADE, null=True, blank=True,
        related_name="match_participations",
    )
    is_bot = models.BooleanField(default=False)
    # Со знаком: в «своей игре» неверный ответ списывает цену клетки, и счёт
    # уходит в минус — это часть правил, а не ошибка.
    score = models.IntegerField(default=0)
    correct_count = models.PositiveSmallIntegerField(default=0)
    # Суммарное время ответов, миллисекунды: им разводятся равные результаты.
    total_time_ms = models.PositiveIntegerField(default=0)
    # Когда игрок открыл экран партии. Пока пусто — он ещё не за столом, и
    # партия не начинается: соперник не должен играть в одни ворота.
    joined_at = models.DateTimeField(null=True, blank=True)
    # Личный старт: в режиме «на время» отсчёт идёт от первого вопроса игрока,
    # а не от создания партии — иначе опоздавший уже проиграл.
    started_at = models.DateTimeField(null=True, blank=True)
    # Когда игрок вышел из партии. Ушедший проигрывает независимо от счёта:
    # иначе выгодно уходить, пока ведёшь.
    left_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-score", "total_time_ms"]
        constraints = [
            models.UniqueConstraint(
                fields=["match", "student"], name="uniq_match_student",
                condition=models.Q(student__isnull=False),
            ),
        ]

    def __str__(self):
        return f"{'бот' if self.is_bot else self.student}: {self.score}"

    @property
    def title(self) -> str:
        if self.is_bot:
            return f"Бот · уровень {self.match.bot_level}"
        return self.student.user.get_full_name() or self.student.user.username

    @property
    def has_left(self) -> bool:
        return self.left_at is not None


class MatchQuestion(MatchChild):
    """Вопрос партии. Набор общий для обеих сторон — иначе сравнивать нечего.

    Вопрос бывает двух видов: задача из банка (нарешивание) или вопрос по
    теории (квиз и «своя игра»). Заполнено ровно одно поле из двух.
    """

    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="questions")
    order = models.PositiveSmallIntegerField(default=1)
    assignment = models.ForeignKey(
        "content.Assignment", on_delete=models.PROTECT, null=True, blank=True
    )
    theory = models.ForeignKey(
        "content.TheoryQuestion", on_delete=models.PROTECT, null=True, blank=True
    )
    # Цена вопроса: в «своей игре» она разная и видна на доске.
    points = models.PositiveSmallIntegerField(default=100)
    # Столбец доски и его подпись. Тема фиксируется в момент партии: если её
    # потом переименуют, разбор всё равно покажет то, что видел игрок.
    column = models.PositiveSmallIntegerField(default=0)
    topic_title = models.CharField(max_length=200, blank=True)
    # Порядок вариантов квиза фиксируется при создании партии: оба игрока
    # должны видеть одно и то же, иначе «кто первый нажал» ничего не значит.
    options = models.JSONField(default=list, blank=True)
    # Когда вопрос открыт обоим (квиз) или выбран с доски («своя игра»).
    opened_at = models.DateTimeField(null=True, blank=True)
    picked_by = models.ForeignKey(
        "MatchParticipant", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="picked_questions",
    )
    # Кто забрал вопрос. Пусто при закрытии по таймеру: очки не достались никому.
    resolved_by = models.ForeignKey(
        "MatchParticipant", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="won_questions",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    # Перехват в «своей игре»: после неверного ответа клетка достаётся
    # сопернику вместе с самим ответом — как в телеигре, где на ошибке
    # соперник получает право сказать своё.
    rebound_by = models.ForeignKey(
        "MatchParticipant", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="rebound_questions",
    )
    rebound_at = models.DateTimeField(null=True, blank=True)
    # Прогон бота: знает ли он этот вопрос и за сколько ответит. Разыгрывается
    # при создании партии, до первого хода человека, — бот не подстраивается.
    bot_correct = models.BooleanField(null=True, blank=True)
    bot_time_ms = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(fields=["match", "order"], name="uniq_match_question_order"),
        ]

    def __str__(self):
        return f"{self.match_id}#{self.order}: {self.title}"

    @property
    def title(self) -> str:
        return self.assignment.title if self.assignment_id else self.topic_title

    @property
    def prompt(self) -> str:
        """Текст вопроса: задача или теория — для интерфейса это одно и то же."""
        return self.theory.prompt if self.theory_id else self.assignment.statement

    @property
    def correct_answer(self) -> str:
        return (
            self.theory.correct_answer if self.theory_id else self.assignment.correct_answer
        )

    @property
    def is_resolved(self) -> bool:
        return self.resolved_at is not None

    @property
    def answering_id(self) -> int | None:
        """Кто отвечает на клетку прямо сейчас: выбравший или перехвативший."""
        return self.rebound_by_id or self.picked_by_id

    @property
    def clock_from(self):
        """С какого момента идёт таймер: перехват получает свои полминуты."""
        return self.rebound_at or self.opened_at

    def check_answer(self, value: str) -> bool:
        """Верен ли ответ. Для теории — сравнение по смыслу записи."""
        if self.theory_id:
            return self.theory.check_answer(value)
        return bool(self.assignment.check_answer(value))


class MatchAnswer(MatchChild):
    """Ответ участника. Время считает сервер, клиенту здесь верить нельзя."""

    participant = models.ForeignKey(
        MatchParticipant, on_delete=models.CASCADE, related_name="answers"
    )
    question = models.ForeignKey(MatchQuestion, on_delete=models.CASCADE, related_name="answers")
    submitted_answer = models.CharField(max_length=300, blank=True)
    # Номер выбранного варианта в квизе; в остальных режимах пусто.
    chosen_option = models.SmallIntegerField(null=True, blank=True)
    is_correct = models.BooleanField(default=False)
    # Сколько очков стоил ответ: в «своей игре» промах списывает цену клетки.
    points_delta = models.SmallIntegerField(default=0)
    time_ms = models.PositiveIntegerField(default=0)
    answered_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["question__order"]
        constraints = [
            models.UniqueConstraint(
                fields=["participant", "question"], name="uniq_participant_question"
            ),
        ]

    def __str__(self):
        return f"{self.participant_id}/{self.question_id}: {'верно' if self.is_correct else 'неверно'}"

    def match_pk(self) -> int | None:
        # У ответа нет своей ссылки на партию: она берётся у вопроса, который
        # почти всегда уже загружен в память.
        return self.question.match_id if self.question_id else None


class ArenaProfile(models.Model):
    """Рейтинг игрока для подбора соперника.

    Рейтинг нужен не ради таблицы лидеров, а ради подбора: играть интересно с
    тем, кто примерно равен. Стартовое значение берётся из прогноза балла —
    так первая же случайная партия попадает в свой уровень, а не в лотерею.

    Обновляется только в партиях с людьми: бот не рейтингованный соперник, и
    фармить рейтинг о него нельзя.
    """

    BASE_RATING = 1000

    student = models.OneToOneField(
        "accounts.StudentProfile", on_delete=models.CASCADE, related_name="arena_profile"
    )
    rating = models.PositiveSmallIntegerField(default=BASE_RATING)
    matches_played = models.PositiveIntegerField(default=0)
    wins = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-rating"]

    def __str__(self):
        return f"{self.student}: {self.rating}"


class MatchmakingTicket(models.Model):
    """Заявка на случайного соперника.

    Очередь, а не мгновенный подбор: партнёра может не быть прямо сейчас.
    Окно поиска расширяется со временем ожидания — сначала ищем ровню, потом
    ближайшего из доступных, как в шахматных клубах.
    """

    class Status(models.TextChoices):
        WAITING = "waiting", "Ищет соперника"
        MATCHED = "matched", "Соперник найден"
        CANCELLED = "cancelled", "Отменена"

    student = models.ForeignKey(
        "accounts.StudentProfile", on_delete=models.CASCADE, related_name="arena_tickets"
    )
    mode = models.CharField(max_length=16, choices=Match.Mode.choices, default=Match.Mode.QUIZ)
    ege_task_number = models.PositiveSmallIntegerField(null=True, blank=True)
    # Правило партии — часть заявки: «кто быстрее решит восемь» и «кто больше
    # решит за три минуты» — разные состязания, и сводить их нельзя.
    limit_kind = models.CharField(
        max_length=16, choices=Match.Limit.choices, default=Match.Limit.QUESTIONS
    )
    time_limit_seconds = models.PositiveSmallIntegerField(default=0)
    question_count = models.PositiveSmallIntegerField(default=0)
    rating = models.PositiveSmallIntegerField(default=ArenaProfile.BASE_RATING)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.WAITING)
    match = models.ForeignKey(
        Match, on_delete=models.SET_NULL, null=True, blank=True, related_name="tickets"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["status", "mode", "created_at"], name="ticket_queue"),
        ]

    def __str__(self):
        return f"{self.student} ждёт соперника ({self.mode})"
