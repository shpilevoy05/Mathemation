"""Серверная проверка загружаемых работ.

Проверяются три независимых уровня: размер, объявленные расширение и
content-type, фактическая подпись файла. Подделанный `Content-Type` ловится
именно последней проверкой — заголовок приходит от клиента и доверять ему
нельзя.
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError

# Сигнатуры допустимых форматов. HEIC проверяется по box-типу `ftyp`
# со смещением 4 байта.
_SIGNATURES = {
    "jpg": ((0, b"\xff\xd8\xff"),),
    "jpeg": ((0, b"\xff\xd8\xff"),),
    "png": ((0, b"\x89PNG\r\n\x1a\n"),),
    "pdf": ((0, b"%PDF-"),),
    "heic": ((4, b"ftyp"),),
}
_HEADER_BYTES = 32


def _read_header(file) -> bytes:
    position = file.tell() if hasattr(file, "tell") else 0
    try:
        file.seek(0)
        header = file.read(_HEADER_BYTES) or b""
    finally:
        try:
            file.seek(position)
        except (OSError, ValueError):
            pass
    return header


def validate_solution_upload(file) -> None:
    """Проверить загружаемое решение. Поднимает `ValidationError`.

    Работает и с `UploadedFile` (есть `content_type`), и с `FieldFile`
    (content_type отсутствует — проверяется всё остальное).
    """
    max_bytes = settings.SOLUTION_UPLOAD_MAX_BYTES
    size = getattr(file, "size", None)
    if size is None:
        raise ValidationError("Не удалось определить размер файла.")
    if size <= 0:
        raise ValidationError("Файл пустой.")
    if size > max_bytes:
        raise ValidationError(
            "Файл больше %d МБ." % (max_bytes // (1024 * 1024))
        )

    extension = Path(getattr(file, "name", "") or "").suffix.lower().lstrip(".")
    if extension not in settings.SOLUTION_ALLOWED_EXTENSIONS:
        raise ValidationError(
            "Допустимые форматы: %s." % ", ".join(settings.SOLUTION_ALLOWED_EXTENSIONS)
        )

    content_type = getattr(file, "content_type", None)
    if content_type and content_type not in settings.SOLUTION_ALLOWED_CONTENT_TYPES:
        raise ValidationError("Тип файла %s не поддерживается." % content_type)

    header = _read_header(file)
    expected = _SIGNATURES.get(extension, ())
    if not any(header[offset:offset + len(magic)] == magic for offset, magic in expected):
        raise ValidationError(
            "Содержимое файла не соответствует формату .%s." % extension
        )
