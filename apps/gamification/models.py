from django.db import models


class League(models.TextChoices):
    """Лиги снизу вверх. Порядок задан здесь и больше нигде не дублируется."""

    DELTA = "delta", "Дельта"
    GAMMA = "gamma", "Гамма"
    OMEGA = "omega", "Омега"
    BETA = "beta", "Бетта"
    ALPHA = "alpha", "Альфа"
    SIGMA = "sigma", "Сигма"


LEAGUE_ORDER = [
    League.DELTA, League.GAMMA, League.OMEGA,
    League.BETA, League.ALPHA, League.SIGMA,
]


def next_league(league: str) -> str:
    """Следующая лига или та же, если игрок уже наверху."""
    index = LEAGUE_ORDER.index(league)
    return LEAGUE_ORDER[min(index + 1, len(LEAGUE_ORDER) - 1)]


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
    # Участие в лигах — по желанию и по умолчанию выключено. Соревнование
    # мотивирует не всех: для части учеников таблица с чужими результатами —
    # повод бросить, а не повод заниматься.
    leagues_enabled = models.BooleanField(default=False)
    league = models.CharField(
        max_length=16, choices=League.choices, default=League.DELTA
    )

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



class LeagueSeason(models.Model):
    """Месяц соревнования. Сезон закрывается один раз и целиком.

    Границы — календарный месяц: у соревнования должен быть понятный всем
    срок, а «месяц с момента входа» превращает таблицу в лотерею.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Идёт"
        CLOSED = "closed", "Завершён"

    starts_on = models.DateField(unique=True)
    ends_on = models.DateField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-starts_on"]

    def __str__(self):
        return f"Сезон {self.starts_on:%m.%Y}"

    @property
    def is_active(self) -> bool:
        return self.status == self.Status.ACTIVE


class LeagueCohort(models.Model):
    """Группа соревнующихся: двадцать мест в одной лиге одного сезона.

    Соревноваться со всей платформой бессмысленно — в таблице из тысячи имён
    место не двигается. Двадцать человек дают видимую борьбу.
    """

    season = models.ForeignKey(LeagueSeason, on_delete=models.CASCADE, related_name="cohorts")
    league = models.CharField(max_length=16, choices=League.choices)
    index = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["league", "index"]
        constraints = [
            models.UniqueConstraint(
                fields=["season", "league", "index"], name="uniq_league_cohort"
            ),
        ]

    def __str__(self):
        return f"{self.get_league_display()} #{self.index + 1}"


class LeagueMember(models.Model):
    """Место в когорте: живой ученик или заполнитель.

    Заполнитель нужен, пока учеников мало: пустая таблица не мотивирует.
    Он не человек и не выдаётся за человека — помечен как бот и всегда стоит
    ниже самого слабого живого участника.
    """

    cohort = models.ForeignKey(LeagueCohort, on_delete=models.CASCADE, related_name="members")
    student = models.ForeignKey(
        "accounts.StudentProfile", on_delete=models.CASCADE, null=True, blank=True,
        related_name="league_memberships",
    )
    is_filler = models.BooleanField(default=False)
    # Номер заполнителя внутри когорты: по нему берётся имя и разброс очков.
    filler_index = models.PositiveSmallIntegerField(default=0)
    xp = models.PositiveIntegerField(default=0)
    # Итоги сезона проставляются при закрытии и дальше не меняются.
    place = models.PositiveSmallIntegerField(null=True, blank=True)
    promoted = models.BooleanField(default=False)
    coins_awarded = models.PositiveIntegerField(default=0)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-xp", "joined_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["cohort", "student"], name="uniq_cohort_student",
                condition=models.Q(student__isnull=False),
            ),
        ]

    def __str__(self):
        return f"{self.title}: {self.xp} XP"

    @property
    def title(self) -> str:
        if self.is_filler:
            return f"Бот · {FILLER_NAMES[self.filler_index % len(FILLER_NAMES)]}"
        return self.student.user.get_full_name() or self.student.user.username


# Имена заполнителей: буквы греческого алфавита — сразу видно, что это не
# однокурсник, а место, которое пока некому занять.
FILLER_NAMES = [
    "Тау", "Ро", "Пси", "Хи", "Фи", "Ню", "Кси", "Дзета",
    "Эта", "Йота", "Каппа", "Лямбда", "Мю", "Тета", "Эпсилон",
    "Ипсилон", "Омикрон", "Пи", "Стигма", "Коппа",
]


class LeagueTrophy(models.Model):
    """Награда за призовое место. История, а не текущее состояние.

    Место хранится вместе с наградой: в списке наград человек видит не просто
    «был в Альфе», а «второе место в Альфе» — и знак с жетоном места.
    """

    student = models.ForeignKey(
        "accounts.StudentProfile", on_delete=models.CASCADE, related_name="league_trophies"
    )
    season = models.ForeignKey(LeagueSeason, on_delete=models.CASCADE, related_name="trophies")
    league = models.CharField(max_length=16, choices=League.choices)
    place = models.PositiveSmallIntegerField(default=1)
    # Сохранено для совместимости: теперь вымпел получают во всех лигах.
    trophy = models.BooleanField(default=False)
    prize = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "season", "league"], name="uniq_league_trophy"
            ),
        ]

    def __str__(self):
        return f"{self.student}: {self.get_league_display()}, {self.place} место"

    @property
    def pennant_code(self) -> str:
        return f"pennant-{self.league}-{self.place}"
