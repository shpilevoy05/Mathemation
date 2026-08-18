import os
from pathlib import Path


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if not value:
        return default

    normalized_value = value.strip().lower()
    if normalized_value in {"1", "true", "yes", "on"}:
        return True
    if normalized_value in {"0", "false", "no", "off"}:
        return False
    return default


def _load_env(path: Path) -> None:
    try:
        if not path.exists():
            return
        with path.open(encoding="utf-8-sig") as env_file:
            for raw_line in env_file:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                if not key:
                    continue
                is_quoted = (
                    len(value) >= 2
                    and value[0] == value[-1]
                    and value[0] in {"'", '"'}
                )
                if is_quoted:
                    value = value[1:-1]
                try:
                    os.environ.setdefault(key, value)
                except (OSError, ValueError):
                    continue
    except (OSError, UnicodeError):
        return


BASE_DIR = Path(__file__).resolve().parent.parent
_load_env(BASE_DIR / ".env")

from .security import (  # noqa: E402 — после загрузки .env
    DEV_SECRET_KEY,
    hardening_settings,
    postgres_ssl_options,
    validate_production_config,
)

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", DEV_SECRET_KEY)
DEBUG = _env_bool("DJANGO_DEBUG", default=True)
ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "*" if DEBUG else "").split(",")
    if host.strip()
]
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "apps.accounts",
    "apps.knowledge",
    "apps.content",
    "apps.diagnostics",
    "apps.planning",
    "apps.practice",
    "apps.mocks",
    "apps.expert_review",
    "apps.progress",
    "apps.ai_mentor",
    "apps.gamification",
    "apps.adminpanel",
    "apps.exams",
    "apps.economy",
    "apps.billing",
    "apps.events",
    "apps.web",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    # Без этого middleware настройка X_FRAME_OPTIONS не действует.
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Второй фактор проверяется перед каждым запросом сотрудника: входов в
    # систему несколько (своя форма, /admin/login/), а правило должно быть одно.
    "apps.accounts.middleware.TwoFactorMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                # Тема, аватар и рамка меняют весь кабинет, поэтому доступны
                # в каждом шаблоне, а не только на своей странице.
                "apps.web.context_processors.cosmetics",
                # Состояние подписки видно в шапке на любой странице: ученик
                # не должен узнавать о закрытом доступе, только упёршись в него.
                "apps.web.context_processors.access",
                # Рельс собирается из данных: активный пункт и раскрытая
                # группа — правила, а не разметка.
                "apps.web.context_processors.navigation",
            ],
        },
    },
]

# PostgreSQL in production (set POSTGRES_DB), SQLite fallback for dev/tests.
if os.environ.get("POSTGRES_DB"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ["POSTGRES_DB"],
            "USER": os.environ.get("POSTGRES_USER", "postgres"),
            "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
            "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
            "PORT": os.environ.get("POSTGRES_PORT", "5432"),
            "CONN_MAX_AGE": int(os.environ.get("POSTGRES_CONN_MAX_AGE") or 60),
            "CONN_HEALTH_CHECKS": True,
            # Управляемая база живёт в чужой сети: трафик до неё шифруется, а
            # сертификат проверяется. `verify-full` требует корневой сертификат
            # провайдера — путь к нему задаётся POSTGRES_SSLROOTCERT.
            "OPTIONS": postgres_ssl_options(
                sslmode=os.environ.get("POSTGRES_SSLMODE", ""),
                sslrootcert=os.environ.get("POSTGRES_SSLROOTCERT", ""),
            ),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_USER_MODEL = "accounts.User"

# Ученики заводят пароль сами на странице приглашения, поэтому политика
# стойкости нужна и вне админки.
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# После логина/логаута через api-auth возвращаем в кабинет, а не на
# несуществующий дефолтный /accounts/profile/.
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/accounts/login/"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    # Лимиты частоты. Общий потолок защищает базу, именованные — то, что стоит
    # денег (подсказка наставника) или меняет баланс.
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.AnonRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "user": os.environ.get("THROTTLE_USER") or "600/hour",
        "anon": os.environ.get("THROTTLE_ANON") or "60/hour",
        "attempt": os.environ.get("THROTTLE_ATTEMPT") or "120/hour",
        "hint": os.environ.get("THROTTLE_HINT") or "30/hour",
        "purchase": os.environ.get("THROTTLE_PURCHASE") or "30/hour",
        "upload": os.environ.get("THROTTLE_UPLOAD") or "40/hour",
        # Колбэк приходит без сессии: лимит держим широким (провайдер повторяет
        # доставку), но конечным — иначе это открытая точка входа.
        "webhook": os.environ.get("THROTTLE_WEBHOOK") or "600/hour",
    },
}

LANGUAGE_CODE = "ru"
TIME_ZONE = "Europe/Moscow"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# --- Приватные файлы (работы учеников) ---
# Каталог намеренно вне MEDIA_ROOT: у файлов нет публичного URL, они отдаются
# только через apps.expert_review.api.SolutionFileView с проверкой прав.
PRIVATE_MEDIA_ROOT = Path(
    os.environ.get("PRIVATE_MEDIA_ROOT", BASE_DIR / "private-media")
)
# Internal-location nginx для X-Accel-Redirect (например "/private-media").
PRIVATE_MEDIA_NGINX_LOCATION = os.environ.get("PRIVATE_MEDIA_NGINX_LOCATION", "")

# Загрузка решений второй части: белый список типов и лимит размера.
SOLUTION_UPLOAD_MAX_BYTES = int(
    os.environ.get("SOLUTION_UPLOAD_MAX_BYTES") or 10 * 1024 * 1024
)
SOLUTION_ALLOWED_EXTENSIONS = ["jpg", "jpeg", "png", "heic", "pdf"]
SOLUTION_ALLOWED_CONTENT_TYPES = [
    "image/jpeg",
    "image/png",
    "image/heic",
    "image/heif",
    "application/pdf",
]
DATA_UPLOAD_MAX_MEMORY_SIZE = SOLUTION_UPLOAD_MAX_BYTES + 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CELERY_BROKER_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = CELERY_BROKER_URL
CELERY_TASK_ALWAYS_EAGER = _env_bool("CELERY_EAGER", default=False)

# --- Кеш ---
# Общий кеш обязателен для ограничения частоты запросов: с локальным кешем у
# каждого воркера свой счётчик, и лимит перестаёт быть лимитом. В разработке и
# тестах Redis не нужен — там процесс один.
if os.environ.get("REDIS_URL") and not DEBUG:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": os.environ["REDIS_URL"],
            "KEY_PREFIX": "matemacia",
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "matemacia-dev",
        }
    }

# --- Логи ---
# Без логов запуск слепой: пишем в stdout (его собирает docker/systemd), а
# события безопасности выносим в отдельный логгер, чтобы их можно было
# отфильтровать и завести на них алерт.
import sys  # noqa: E402 — нужен только для режима тестов

# В тестах логи мешают читать результат: сам факт срабатывания лимита или
# аудита проверяется тестом, а не глазами в выводе.
_TESTING = "test" in sys.argv
LOG_LEVEL = os.environ.get(
    "DJANGO_LOG_LEVEL", "ERROR" if _TESTING else ("INFO" if not DEBUG else "WARNING")
)
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "plain": {
            "format": "{asctime} {levelname} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "plain"},
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django.request": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        "django.security": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        # Попытки перебора, срабатывания лимитов, отказ провайдеров.
        "matemacia.security": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        "matemacia.integrations": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
    },
}

# --- Mathemation domain config ---
# Streak period is an MVP experiment: "daily" or "weekly".
STREAK_MODE = "daily"
# Mastery threshold above which a node is considered mastered and skipped in the plan.
MASTERY_THRESHOLD = 70
# Learning rate of the synchronous mastery micro-update.
BKT_ALPHA = 0.3
# Spaced-repetition intervals in days for mistake rework.
REVIEW_INTERVALS_DAYS = [1, 3, 7, 30]
REVIEW_EASE = 1.6
MIN_REVIEW_INTERVAL_DAYS = 1
MAX_REVIEW_INTERVAL_DAYS = 60
# Open mistakes on one node that force the topic back into the plan.
FREQUENT_MISTAKE_THRESHOLD = 3
# Expert review SLA (hours), stored per-request but defaulted here.
EXPERT_REVIEW_SLA_HOURS = 48
# Max leading hints per assignment per student.
AI_MENTOR_MAX_HINTS = 2
# Hint provider (dotted path); swap for an LLM-backed provider in production.
AI_MENTOR_PROVIDER = os.environ.get(
    "AI_MENTOR_PROVIDER", "apps.ai_mentor.providers.MockHintProvider"
) or "apps.ai_mentor.providers.MockHintProvider"
AI_MENTOR_LLM_FORMAT = os.environ.get("AI_MENTOR_LLM_FORMAT") or "openai"
AI_MENTOR_LLM_BASE_URL = os.environ.get("AI_MENTOR_LLM_BASE_URL", "")
AI_MENTOR_LLM_API_KEY = os.environ.get("AI_MENTOR_LLM_API_KEY", "")
AI_MENTOR_LLM_MODEL = os.environ.get("AI_MENTOR_LLM_MODEL", "")
AI_MENTOR_LLM_FOLDER_ID = os.environ.get("AI_MENTOR_LLM_FOLDER_ID", "")
AI_MENTOR_LLM_TIMEOUT_SECONDS = int(
    os.environ.get("AI_MENTOR_LLM_TIMEOUT_SECONDS") or "20"
)
AI_MENTOR_LLM_MAX_TOKENS = int(os.environ.get("AI_MENTOR_LLM_MAX_TOKENS") or "400")
AI_MENTOR_LLM_TEMPERATURE = float(
    os.environ.get("AI_MENTOR_LLM_TEMPERATURE") or "0.3"
)

# --- Внутренняя валюта и магазин ---
# Монеты идут за тем же событием, что и XP: XP отвечает за прогресс, монеты —
# за покупки в магазине косметики. Ноль отключает выдачу монет.
COINS_PER_XP = 1
COIN_REWARDS = {
    "daily_challenge": 15,
    "homework_done": 20,
    "mock_completed": 50,
    "mistake_resolved": 5,
    "lesson_done": 5,
}

# --- Платежи ---
# Провайдер эквайринга (dotted path). Боевой провайдер подключается сюда;
# он же отвечает за фискализацию чека по 54-ФЗ.
BILLING_PROVIDER = os.environ.get(
    "BILLING_PROVIDER", "apps.billing.providers.MockPaymentProvider"
) or "apps.billing.providers.MockPaymentProvider"

# Секрет подписи колбэков. Без него вебхук отклоняет любой запрос: колбэк
# приходит из интернета без сессии, и единственное доказательство источника —
# подпись тела провайдером.
BILLING_WEBHOOK_SECRET = os.environ.get("BILLING_WEBHOOK_SECRET", "")

# --- Доступ к платной части ---
# Гейт выключен по умолчанию: пока эквайринг не подключён, закрывать доступ
# нечем. Включение — решение владельца продукта, а не побочный эффект деплоя.
BILLING_ENFORCED = _env_bool("BILLING_ENFORCED", default=False)
# Что остаётся бесплатным при включённом гейте. Разрез меняет маркетинг, а не
# релиз, поэтому он в настройке, а не в коде.
FREE_FEATURES = [
    item.strip()
    for item in (os.environ.get("FREE_FEATURES") or "").split(",")
    if item.strip()
]
# Пробный период от даты регистрации ученика, дней. 0 — без пробного периода.
TRIAL_DAYS = int(os.environ.get("TRIAL_DAYS") or 7)

# --- Второй фактор ---
# Сотрудник видит чужие персональные данные, публикует контент и двигает
# деньги: одного пароля для бэкофиса мало. Ученику и родителю фактор не
# навязываем — он не открывает чужих данных, а порог входа поднимает заметно.
TWO_FACTOR_ENFORCED = _env_bool("TWO_FACTOR_ENFORCED", default=not DEBUG)
TWO_FACTOR_REQUIRED_ROLES = [
    role.strip()
    for role in (
        os.environ.get("TWO_FACTOR_REQUIRED_ROLES") or "methodist,expert"
    ).split(",")
    if role.strip()
]
TWO_FACTOR_ISSUER = os.environ.get("TWO_FACTOR_ISSUER") or "Матемация"

# --- Видео занятий ---
# Хосты, чей плеер разрешено встраивать. iframe исполняется в контексте
# страницы ученика, поэтому список закрытый: опечатка или чужая ссылка в поле
# урока не должна превращаться в чужой код на нашей странице.
VIDEO_ALLOWED_HOSTS = [
    host.strip().lower()
    for host in (
        os.environ.get("VIDEO_ALLOWED_HOSTS")
        or "kinescope.io,youtube.com,youtu.be,vk.com,vkvideo.ru,rutube.ru"
    ).split(",")
    if host.strip()
]
# Сколько живёт выданная ссылка на плеер. Минуты, а не часы: пересланная
# ссылка должна протухать раньше, чем ею успеют воспользоваться.
VIDEO_LINK_TTL_SECONDS = int(os.environ.get("VIDEO_LINK_TTL_SECONDS") or 600)

# Приватные ролики Kinescope. Без ключа подписи ссылки остаются публичными —
# это видно в ответе API полем `is_private`.
KINESCOPE_SIGNING_KEY = os.environ.get("KINESCOPE_SIGNING_KEY", "")
KINESCOPE_KEY_ID = os.environ.get("KINESCOPE_KEY_ID", "")
KINESCOPE_TOKEN_PARAM = os.environ.get("KINESCOPE_TOKEN_PARAM") or "token"
# Имена полей токена: если контракт хостинга отличается, подстраивается
# конфигурация, а не код.
KINESCOPE_TOKEN_CLAIMS = {}

# --- Forgetting curve (индикатор забывания) ---
# Days after the last practice before a skill starts to decay.
DECAY_GRACE_DAYS = 14
# Exponential decay rate per day past the grace period (~половина за месяц).
DECAY_RATE_PER_DAY = 0.02

# --- Score forecast ---
# Maximum primary score of the profile EGE (12 задач части 1 + 20 баллов части 2).
MAX_PRIMARY_SCORE = 32
# EMA weight of the latest mock when calibrating a forecast.
FORECAST_CALIBRATION_ALPHA = 0.3
# Bootstrap IRT 2PL parameters; real attempt logs can calibrate them later.
IRT_THETA_SCALE = 6.0
IRT_DIFFICULTY_STEP = 1.2
IRT_DEFAULT_DISCRIMINATION = 1.0
IRT_GUESS = 0.0
# Официальная таблица перевода первичных баллов в тестовые (кладётся конфигом
# на каждый год; ниже — приближение шкалы профильной математики).
PRIMARY_TO_SCALED = [
    0, 5, 9, 14, 18, 22, 27, 33, 39, 45, 50, 56, 62, 68, 70, 72, 74,
    76, 78, 80, 82, 84, 86, 88, 90, 92, 94, 96, 98, 99, 100, 100, 100,
]
# Ceiling simulation: сколько часов нужно на освоение одного узла и до какого
# уровня mastery реалистично довести узел до экзамена.
HOURS_PER_NODE = 2
# Дефолт по части экзамена; конкретный узел может задать hours_estimate.
HOURS_PER_NODE_BY_PART = {1: 2, 2: 4}
ATTAINABLE_MASTERY = 85
# Интервал прогноза: пока пробников нет, разброс берётся отсюда (первичные
# баллы). Одно число выглядит точнее, чем прогноз есть на самом деле.
FORECAST_PRIOR_SIGMA_PRIMARY = 3.0
FORECAST_INTERVAL_Z = 1.0
# Дней без активности, после которых план перестраивается под сжатое время.
INACTIVITY_REBUILD_DAYS = 14
# Повторное изменение по той же причине и узлу не зашумляет карточку плана.
PLAN_CHANGE_LOG_DEDUP_HOURS = 24

# Periodic jobs (celery -A config worker -B).
from celery.schedules import crontab  # noqa: E402

CELERY_BEAT_SCHEDULE = {
    "generate-weekly-quests": {
        "task": "apps.gamification.tasks.generate_weekly_quests_all",
        "schedule": crontab(day_of_week="mon", hour=5, minute=0),
    },
    "apply-decay-daily": {
        "task": "apps.knowledge.tasks.apply_decay_all",
        "schedule": crontab(hour=3, minute=0),
    },
    "mark-missed-reviews-daily": {
        "task": "apps.practice.tasks.mark_missed_reviews",
        "schedule": crontab(hour=3, minute=30),
    },
    "detect-inactivity-daily": {
        "task": "apps.progress.tasks.detect_inactivity",
        "schedule": crontab(hour=4, minute=0),
    },
    # После забывания и просрочек — переоценка очереди: за ночь мог измениться
    # и порядок тем, и то, что вообще осталось в плане.
    "refresh-plans-daily": {
        "task": "apps.planning.tasks.refresh_plans",
        "schedule": crontab(hour=4, minute=30),
    },
    "expire-subscriptions-daily": {
        "task": "apps.billing.tasks.expire_subscriptions_task",
        "schedule": crontab(hour=2, minute=0),
    },
    "weekly-parent-reports": {
        "task": "apps.progress.tasks.generate_weekly_parent_reports",
        "schedule": crontab(day_of_week="mon", hour=8, minute=0),
    },
}

# --- Security ---
# Пороги защиты от перебора. Значения по умолчанию заданы в
# apps/accounts/throttling.py; здесь они становятся настраиваемыми на сервере,
# не требуя выкладки кода.
LOGIN_MAX_ATTEMPTS = int(os.environ.get("LOGIN_MAX_ATTEMPTS") or 10)
LOGIN_BLOCK_SECONDS = int(os.environ.get("LOGIN_BLOCK_SECONDS") or 15 * 60)
INVITE_MAX_ATTEMPTS = int(os.environ.get("INVITE_MAX_ATTEMPTS") or 20)
INVITE_BLOCK_SECONDS = int(os.environ.get("INVITE_BLOCK_SECONDS") or 60 * 60)

# Значения зависят от режима; логика и её тесты — в config/security.py.
SECURE_HTTPS_BEHIND_PROXY = _env_bool("DJANGO_BEHIND_PROXY", default=True)
globals().update(hardening_settings(debug=DEBUG, behind_proxy=SECURE_HTTPS_BEHIND_PROXY))

# Fail-fast: прод-процесс не поднимается с dev-ключом, ALLOWED_HOSTS='*'
# или приватным каталогом внутри публичного MEDIA_ROOT.
validate_production_config(
    debug=DEBUG,
    secret_key=SECRET_KEY,
    allowed_hosts=ALLOWED_HOSTS,
    private_media_root=PRIVATE_MEDIA_ROOT,
    media_root=MEDIA_ROOT,
    database_engine=DATABASES["default"]["ENGINE"],
    billing_provider=BILLING_PROVIDER,
    billing_webhook_secret=BILLING_WEBHOOK_SECRET,
)
