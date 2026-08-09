#!/bin/sh
# Точка входа контейнера. Роль передаётся аргументом: web, worker, beat,
# release. Один образ — четыре режима.
set -eu

role="${1:-web}"

wait_for_db() {
    # Управляемая база может быть недоступна первые секунды после
    # переключения: ждём вместо падения в рестарт-петлю.
    python - <<'PY'
import os
import sys
import time

import django
from django.db import connections
from django.db.utils import OperationalError

django.setup()
deadline = time.time() + int(os.environ.get("DB_WAIT_SECONDS", "60"))
while True:
    try:
        connections["default"].cursor().execute("SELECT 1")
        break
    except OperationalError as error:
        if time.time() >= deadline:
            print("База недоступна: %s" % error, file=sys.stderr)
            raise SystemExit(1)
        time.sleep(2)
PY
}

case "$role" in
    release)
        # Миграции выполняет ровно один процесс релиза, а не каждая реплика:
        # параллельный migrate на одной базе — это гонка на схеме.
        wait_for_db
        python manage.py migrate --noinput
        python manage.py check --deploy
        ;;
    web)
        wait_for_db
        exec gunicorn config.wsgi:application \
            --bind "0.0.0.0:${PORT:-8000}" \
            --workers "${GUNICORN_WORKERS:-3}" \
            --threads "${GUNICORN_THREADS:-4}" \
            --timeout "${GUNICORN_TIMEOUT:-60}" \
            --graceful-timeout 30 \
            --max-requests 1000 \
            --max-requests-jitter 100 \
            --access-logfile - \
            --error-logfile - \
            --forwarded-allow-ips '*'
        ;;
    worker)
        wait_for_db
        exec celery -A config worker \
            --loglevel "${CELERY_LOG_LEVEL:-info}" \
            --concurrency "${CELERY_CONCURRENCY:-4}"
        ;;
    beat)
        wait_for_db
        # Расписание — один процесс на всю установку: две копии beat означают
        # две ночные пересборки плана и двойные начисления.
        exec celery -A config beat --loglevel "${CELERY_LOG_LEVEL:-info}"
        ;;
    *)
        echo "Неизвестная роль: $role (ожидались web, worker, beat, release)" >&2
        exit 2
        ;;
esac
