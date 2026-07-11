import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-insecure-key")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",")

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

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CELERY_BROKER_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = CELERY_BROKER_URL
CELERY_TASK_ALWAYS_EAGER = os.environ.get("CELERY_EAGER", "0") == "1"

# --- Mathemation domain config ---
# Mastery threshold above which a node is considered mastered and skipped in the plan.
MASTERY_THRESHOLD = 70
# Learning rate of the synchronous mastery micro-update.
BKT_ALPHA = 0.3
# Spaced-repetition intervals in days for mistake rework.
REVIEW_INTERVALS_DAYS = [1, 3, 7, 30]
# Open mistakes on one node that force the topic back into the plan.
FREQUENT_MISTAKE_THRESHOLD = 3
# Expert review SLA (hours), stored per-request but defaulted here.
EXPERT_REVIEW_SLA_HOURS = 48
# Max leading hints per assignment per student.
AI_MENTOR_MAX_HINTS = 2
# Hint provider (dotted path); swap for an LLM-backed provider in production.
AI_MENTOR_PROVIDER = os.environ.get(
    "AI_MENTOR_PROVIDER", "apps.ai_mentor.providers.MockHintProvider"
)

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
# Официальная таблица перевода первичных баллов в тестовые (кладётся конфигом
# на каждый год; ниже — приближение шкалы профильной математики).
PRIMARY_TO_SCALED = [
    0, 5, 9, 14, 18, 22, 27, 33, 39, 45, 50, 56, 62, 68, 70, 72, 74,
    76, 78, 80, 82, 84, 86, 88, 90, 92, 94, 96, 98, 99, 100, 100, 100,
]
# Ceiling simulation: сколько часов нужно на освоение одного узла и до какого
# уровня mastery реалистично довести узел до экзамена.
HOURS_PER_NODE = 2
ATTAINABLE_MASTERY = 85
# Дней без активности, после которых план перестраивается под сжатое время.
INACTIVITY_REBUILD_DAYS = 14

# Periodic jobs (celery -A config worker -B).
from celery.schedules import crontab  # noqa: E402

CELERY_BEAT_SCHEDULE = {
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
    "weekly-parent-reports": {
        "task": "apps.progress.tasks.generate_weekly_parent_reports",
        "schedule": crontab(day_of_week="mon", hour=8, minute=0),
    },
}
