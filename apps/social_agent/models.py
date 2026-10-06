import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class BrandProfile(models.Model):
    name = models.CharField("Название", max_length=200)
    description = models.TextField("Описание", blank=True)
    tone_of_voice = models.TextField("Тон голоса", blank=True)
    good_post_examples = models.TextField("Примеры хороших постов", blank=True)
    forbidden_phrases = models.JSONField("Запретные формулировки", default=list, blank=True)
    competitors = models.JSONField("Конкуренты", default=list, blank=True)
    evergreen_topics = models.JSONField("Вечнозелёные темы", default=list, blank=True)
    signature = models.CharField("Подпись", max_length=500, blank=True)
    hashtags = models.JSONField("Хэштеги", default=list, blank=True)
    exam_date = models.DateField("Дата ЕГЭ", null=True, blank=True)
    language = models.CharField("Язык", max_length=10, default="ru")

    class Meta:
        verbose_name = "Профиль бренда"
        verbose_name_plural = "Профиль бренда"

    def clean(self):
        super().clean()
        if type(self).objects.exclude(pk=self.pk).exists():
            raise ValidationError("Допустима только одна запись профиля бренда.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Channel(models.Model):
    class Platform(models.TextChoices):
        TELEGRAM = "telegram", "Telegram"
        VK_CLIPS = "vk_clips", "VK Клипы"
        RUTUBE = "rutube", "Rutube"
        DZEN = "dzen", "Дзен"
        YOUTUBE = "youtube", "YouTube"
        TIKTOK = "tiktok", "TikTok"

    class Mode(models.TextChoices):
        MANUAL = "manual", "Ручной"
        AUTO_SAFE = "auto_safe", "Автоматический для безопасных рубрик"

    platform = models.CharField("Платформа", max_length=20, choices=Platform.choices)
    title = models.CharField("Название", max_length=200)
    external_id = models.CharField("Внешний идентификатор", max_length=200)
    is_active = models.BooleanField("Активен", default=False)
    mode = models.CharField("Режим", max_length=16, choices=Mode.choices, default=Mode.MANUAL)

    class Meta:
        verbose_name = "Канал"
        verbose_name_plural = "Каналы"

    def clean(self):
        super().clean()
        if self.is_active:
            from .adapters import is_platform_supported

            if not is_platform_supported(self.platform):
                raise ValidationError({"is_active": "Для платформы не зарегистрирован адаптер."})

    def __str__(self):
        return f"{self.title} ({self.get_platform_display()})"


class Rubric(models.Model):
    class Audience(models.TextChoices):
        STUDENTS = "students", "Ученики"
        PARENTS = "parents", "Родители"
        BOTH = "both", "Все"

    class SourceKind(models.TextChoices):
        ASSIGNMENT_OF_DAY = "assignment_of_day", "Задача дня"
        LESSON_TIP = "lesson_tip", "Совет из урока"
        EXAM_COUNTDOWN = "exam_countdown", "Отсчёт до ЕГЭ"
        STAFF_IDEA = "staff_idea", "Идея сотрудника"
        EVERGREEN = "evergreen", "Вечнозелёная тема"

    class Risk(models.TextChoices):
        LOW = "low", "Низкий"
        HIGH = "high", "Высокий"

    slug = models.SlugField("Код", unique=True)
    title = models.CharField("Название", max_length=200)
    audience = models.CharField("Аудитория", max_length=16, choices=Audience.choices)
    source_kind = models.CharField("Источник", max_length=32, choices=SourceKind.choices)
    prompt_hint = models.TextField("Подсказка для промпта", blank=True)
    risk = models.CharField("Риск", max_length=8, choices=Risk.choices, default=Risk.HIGH)
    autopublish_allowed = models.BooleanField("Автопубликация разрешена", default=False)
    is_active = models.BooleanField("Активна", default=True)

    class Meta:
        verbose_name = "Рубрика"
        verbose_name_plural = "Рубрики"

    def clean(self):
        super().clean()
        if self.autopublish_allowed and self.risk != self.Risk.LOW:
            raise ValidationError({"autopublish_allowed": "Автопубликация допустима только при низком риске."})

    def __str__(self):
        return self.title


class RubricSlot(models.Model):
    rubric = models.ForeignKey(Rubric, on_delete=models.CASCADE, related_name="slots", verbose_name="Рубрика")
    channel = models.ForeignKey(Channel, on_delete=models.CASCADE, related_name="rubric_slots", verbose_name="Канал")
    weekday = models.PositiveSmallIntegerField("День недели", choices=[(i, name) for i, name in enumerate(("Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"))])
    time = models.TimeField("Время")
    is_active = models.BooleanField("Активен", default=True)

    class Meta:
        verbose_name = "Слот рубрики"
        verbose_name_plural = "Слоты рубрик"

    def __str__(self):
        return f"{self.rubric} — {self.channel}, {self.get_weekday_display()} {self.time:%H:%M}"


class PermissionBase(models.Model):
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Кто одобрил")
    approved_at = models.DateTimeField("Когда одобрено", null=True, blank=True)

    class Meta:
        abstract = True


class SocialTaskPermission(PermissionBase):
    assignment = models.OneToOneField("content.Assignment", on_delete=models.CASCADE, related_name="social_permission", verbose_name="Задача")

    class Meta:
        verbose_name = "Разрешение на задачу"
        verbose_name_plural = "Разрешения на задачи"

    def __str__(self):
        return str(self.assignment)


class SocialLessonPermission(PermissionBase):
    lesson = models.OneToOneField("content.Lesson", on_delete=models.CASCADE, related_name="social_permission", verbose_name="Урок")

    class Meta:
        verbose_name = "Разрешение на урок"
        verbose_name_plural = "Разрешения на уроки"

    def __str__(self):
        return str(self.lesson)


class ContentIdea(models.Model):
    title = models.CharField("Название", max_length=200)
    body = models.TextField("Текст")
    audience = models.CharField("Аудитория", max_length=16, choices=Rubric.Audience.choices)
    rubric = models.ForeignKey(Rubric, on_delete=models.SET_NULL, null=True, blank=True, related_name="content_ideas", verbose_name="Рубрика")
    used_at = models.DateTimeField("Использовано", null=True, blank=True)

    class Meta:
        verbose_name = "Идея контента"
        verbose_name_plural = "Идеи контента"

    def __str__(self):
        return self.title


class Post(models.Model):
    class Kind(models.TextChoices):
        TEXT = "text", "Текст"
        IMAGE = "image", "Изображение"
        VIDEO = "video", "Видео"

    class Status(models.TextChoices):
        DRAFT = "draft", "Черновик"
        CHECKING = "checking", "Проверка"
        NEEDS_REVIEW = "needs_review", "Нужно согласование"
        NEEDS_HUMAN = "needs_human", "Нужен человек"
        APPROVED = "approved", "Одобрен"
        REJECTED = "rejected", "Отклонён"
        REWRITING = "rewriting", "Переписывается"
        SCHEDULED = "scheduled", "Запланирован"
        PUBLISHED = "published", "Опубликован"
        FAILED = "failed", "Ошибка"

    channel = models.ForeignKey(Channel, on_delete=models.PROTECT, related_name="posts", verbose_name="Канал")
    rubric = models.ForeignKey(Rubric, on_delete=models.PROTECT, related_name="posts", verbose_name="Рубрика")
    kind = models.CharField("Вид", max_length=8, choices=Kind.choices, default=Kind.TEXT)
    status = models.CharField("Статус", max_length=16, choices=Status.choices, default=Status.DRAFT)
    text = models.TextField("Текст", blank=True)
    scheduled_for = models.DateTimeField("Время публикации")
    published_at = models.DateTimeField("Опубликовано", null=True, blank=True)
    external_message_id = models.CharField("ID сообщения", max_length=200, blank=True)
    source_ref = models.CharField("Ссылка на источник", max_length=200, blank=True)
    group_key = models.UUIDField("Группа публикаций", default=uuid.uuid4, editable=False)
    rewrite_count = models.PositiveSmallIntegerField("Число переписываний", default=0)
    review_notes = models.TextField("Комментарий согласования", blank=True)
    failure_reason = models.TextField("Причина ошибки", blank=True)
    views = models.PositiveIntegerField("Просмотры", null=True, blank=True)
    reactions = models.PositiveIntegerField("Реакции", null=True, blank=True)
    created_at = models.DateTimeField("Создан", auto_now_add=True)
    updated_at = models.DateTimeField("Изменён", auto_now=True)

    class Meta:
        verbose_name = "Публикация"
        verbose_name_plural = "Публикации"
        constraints = [models.UniqueConstraint(fields=("channel", "rubric", "scheduled_for"), name="social_unique_planned_post")]

    def __str__(self):
        return f"{self.rubric}: {self.scheduled_for:%d.%m.%Y %H:%M}"


class PostCheck(models.Model):
    class Kind(models.TextChoices):
        BANNED_PHRASE = "banned_phrase", "Запретная формулировка"
        NUMBER_WHITELIST = "number_whitelist", "Белый список чисел"
        ANSWER_INTEGRITY = "answer_integrity", "Целостность ответа"
        LENGTH = "length", "Длина"
        COMPETITOR = "competitor", "Конкурент"
        PERSONAL_DATA = "personal_data", "Персональные данные"

    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="checks", verbose_name="Публикация")
    kind = models.CharField("Проверка", max_length=24, choices=Kind.choices)
    passed = models.BooleanField("Пройдена")
    detail = models.TextField("Подробности", blank=True)

    class Meta:
        verbose_name = "Проверка публикации"
        verbose_name_plural = "Проверки публикаций"

    def __str__(self):
        return f"{self.get_kind_display()}: {'да' if self.passed else 'нет'}"


class LlmCall(models.Model):
    class Purpose(models.TextChoices):
        DRAFT = "draft", "Черновик"
        REWRITE = "rewrite", "Переписывание"
        CHECK = "check", "Проверка"

    purpose = models.CharField("Назначение", max_length=16, choices=Purpose.choices)
    model = models.CharField("Модель", max_length=200, blank=True)
    prompt_tokens = models.PositiveIntegerField("Входные токены", default=0)
    completion_tokens = models.PositiveIntegerField("Выходные токены", default=0)
    cost = models.DecimalField("Стоимость", max_digits=12, decimal_places=6, default=0)
    post = models.ForeignKey(Post, on_delete=models.SET_NULL, null=True, blank=True, related_name="llm_calls", verbose_name="Публикация")
    created_at = models.DateTimeField("Создан", auto_now_add=True)

    class Meta:
        verbose_name = "Вызов LLM"
        verbose_name_plural = "Вызовы LLM"

    def __str__(self):
        return f"{self.purpose}: {self.model}"


class MediaAsset(models.Model):
    class Kind(models.TextChoices):
        IMAGE = "image", "Изображение"
        VIDEO = "video", "Видео"

    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="media_assets", verbose_name="Публикация")
    kind = models.CharField("Вид", max_length=8, choices=Kind.choices)
    file = models.FileField("Файл", upload_to="social_agent/")
    duration_seconds = models.PositiveIntegerField("Длительность, сек.", null=True, blank=True)
    width = models.PositiveIntegerField("Ширина", null=True, blank=True)
    height = models.PositiveIntegerField("Высота", null=True, blank=True)

    class Meta:
        verbose_name = "Медиафайл"
        verbose_name_plural = "Медиафайлы"

    def __str__(self):
        return f"{self.get_kind_display()} для {self.post}"


class BotState(models.Model):
    key = models.CharField("Ключ", max_length=100, unique=True)
    value = models.TextField("Значение", blank=True)

    class Meta:
        verbose_name = "Состояние бота"
        verbose_name_plural = "Состояние бота"

    def __str__(self):
        return self.key
