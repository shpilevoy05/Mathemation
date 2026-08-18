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
        QUIZ = "quiz", "Квиз"
        BOARD = "board", "Своя игра"

    class Status(models.TextChoices):
        INVITED = "invited", "Приглашение отправлено"
        ACTIVE = "active", "Идёт"
        FINISHED = "finished", "Завершена"
        DECLINED = "declined", "Отклонена"

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
    # Рейтинговая партия — только подбор случайного соперника: вызов друга и
    # игра с ботом на рейтинг не влияют.
    is_ranked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"], name="match_status_recent"),
        ]

    def __str__(self):
        return f"{self.get_mode_display()} #{self.pk}"

    @property
    def is_finished(self) -> bool:
        return self.status == self.Status.FINISHED

    @property
    def against_bot(self) -> bool:
        return self.bot_level is not None


class MatchParticipant(models.Model):
    """Сторона партии. Бот — участник без профиля ученика."""

    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="participants")
    student = models.ForeignKey(
        "accounts.StudentProfile", on_delete=models.CASCADE, null=True, blank=True,
        related_name="match_participations",
    )
    is_bot = models.BooleanField(default=False)
    score = models.PositiveIntegerField(default=0)
    correct_count = models.PositiveSmallIntegerField(default=0)
    # Суммарное время ответов, миллисекунды: им разводятся равные результаты.
    total_time_ms = models.PositiveIntegerField(default=0)
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


class MatchQuestion(models.Model):
    """Задача партии. Набор общий для обеих сторон — иначе сравнивать нечего."""

    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="questions")
    order = models.PositiveSmallIntegerField(default=1)
    assignment = models.ForeignKey("content.Assignment", on_delete=models.PROTECT)
    # Цена вопроса: в «своей игре» она разная и видна на доске.
    points = models.PositiveSmallIntegerField(default=100)

    class Meta:
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(fields=["match", "order"], name="uniq_match_question_order"),
        ]

    def __str__(self):
        return f"{self.match_id}#{self.order}: {self.assignment.title}"


class MatchAnswer(models.Model):
    """Ответ участника. Время считает сервер, клиенту здесь верить нельзя."""

    participant = models.ForeignKey(
        MatchParticipant, on_delete=models.CASCADE, related_name="answers"
    )
    question = models.ForeignKey(MatchQuestion, on_delete=models.CASCADE, related_name="answers")
    submitted_answer = models.CharField(max_length=300, blank=True)
    is_correct = models.BooleanField(default=False)
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
