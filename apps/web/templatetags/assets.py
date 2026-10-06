"""Template helpers for cache-busting project-owned static assets."""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

from django import template
from django.conf import settings
from django.contrib.staticfiles import finders
from django.templatetags.static import static

register = template.Library()


@lru_cache(maxsize=256)
def _content_hash(absolute_path: str, modified_ns: int) -> str:
    """Hash a file once for each path and modification time."""
    del modified_ns  # It is part of the cache key; the file contents are the value.
    digest = hashlib.sha256()
    with Path(absolute_path).open("rb") as asset_file:
        for chunk in iter(lambda: asset_file.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()[:10]


def _find_asset(path: str) -> Path | None:
    found = finders.find(path)
    if found:
        return Path(found).resolve()

    static_root = getattr(settings, "STATIC_ROOT", None)
    if static_root:
        candidate = (Path(static_root) / path).resolve()
        if candidate.is_file():
            return candidate
    return None


@register.simple_tag
def asset(path: str) -> str:
    """Return a static URL with a version derived from the file contents."""
    url = static(path)
    try:
        asset_path = _find_asset(path)
        if asset_path is None:
            return url
        version = _content_hash(str(asset_path), asset_path.stat().st_mtime_ns)
    except OSError:
        return url
    return f"{url}?v={version}"
