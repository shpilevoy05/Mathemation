# Образ приложения: тот же для веба, воркера и расписания — разница только в
# команде запуска. Один образ означает, что воркер не может оказаться на
# версии кода, отличной от той, что отвечает на запросы.
FROM python:3.13-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_SETTINGS_MODULE=config.settings

WORKDIR /app

# Зависимости ставятся до копирования кода: слой переиспользуется, пока
# requirements не менялись.
COPY requirements.txt requirements-production.txt ./
RUN pip install --no-cache-dir -r requirements-production.txt

COPY . .

# Статика собирается на сборке, а не на старте: одинаковый результат в каждой
# реплике и никакой записи в файловую систему во время работы.
# Ключ и хосты нужны только чтобы settings прошли валидацию на этапе сборки.
RUN DJANGO_DEBUG=1 python manage.py collectstatic --noinput

# Процесс работает не от root: если приложение скомпрометировано, у него нет
# прав на образ.
RUN useradd --system --create-home --uid 10001 app \
    && mkdir -p /app/media /app/private-media \
    && chown -R app:app /app/media /app/private-media /app/staticfiles
USER app

EXPOSE 8000

# Проверка живости внутри контейнера — тот же эндпоинт, что и у балансировщика.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4).status == 200 else 1)"

CMD ["/app/infra/production/entrypoint.sh", "web"]
