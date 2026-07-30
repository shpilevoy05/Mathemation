"""Приватное хранилище работ учеников.

Файлы лежат в `settings.PRIVATE_MEDIA_ROOT` — вне `MEDIA_ROOT`, поэтому их не
раздаёт ни `django.conf.urls.static`, ни nginx-локация статики. Публичного URL
у файла нет: `FieldFile.url` поднимает `ValueError`. Единственный путь к
содержимому — `apps.expert_review.api.SolutionFileView` с проверкой прав.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage


class PrivateMediaStorage(FileSystemStorage):
    """FileSystemStorage без публичного URL, читающий путь из настроек лениво.

    `base_location` и `base_url` переопределены обычными property вместо
    `cached_property` родителя: иначе каталог фиксируется на момент загрузки
    модели и `override_settings` в тестах не работает.
    """

    def __init__(self, **kwargs):
        kwargs.setdefault("base_url", None)
        super().__init__(**kwargs)

    @property
    def base_location(self):
        return self._value_or_setting(self._location, settings.PRIVATE_MEDIA_ROOT)

    @property
    def location(self):
        return os.path.abspath(self.base_location)

    @property
    def base_url(self):
        # None => FileSystemStorage.url() поднимает ValueError.
        return None


def private_media_storage() -> PrivateMediaStorage:
    """Вызываемая ссылка для `FileField(storage=...)` — так миграция не
    сериализует состояние конкретной машины."""
    return PrivateMediaStorage()


def solution_upload_path(instance, filename: str) -> str:
    """`solutions/<student_id>/<uuid>.<ext>` — имя не угадывается.

    Исходное имя файла от пользователя не используется: оно и предсказуемо,
    и может содержать путь. Расширение берётся только из белого списка.
    """
    extension = Path(filename or "").suffix.lower().lstrip(".")
    if extension not in settings.SOLUTION_ALLOWED_EXTENSIONS:
        extension = "bin"
    student_id = getattr(instance, "student_id", None) or "unknown"
    return f"solutions/{student_id}/{uuid.uuid4().hex}.{extension}"
