"""Сборка спрайта косметики из дизайн-исходников.

Дизайн лежит в `design/svg/` — по файлу на аватар, рамку и знак лиги. В
интерфейсе они нужны одним файлом: спрайт грузится один раз и кешируется, а не
тянется по картинке на каждый кружок в списке.

Почему сборка отдельным шагом, а не чтением на лету: `design/` — исходники, а
не ассеты приложения. Продакшену незачем зависеть от папки, которую дизайнер
пересобирает генератором; в образ едет один собранный `static/img/cosmetics.svg`.

Идентификаторы градиентов внутри файлов делаются уникальными: в общем документе
одинаковый `id` из двух картинок означал бы, что вторая покрасится в цвета
первой.
"""

from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings

SPRITE_PATH = Path("static") / "img" / "cosmetics.svg"
SOURCES = (
    ("avatar", "avatars", "0 0 128 128"),
    ("frame", "frames", "0 0 160 160"),
    ("league", "leagues", "0 0 128 128"),
)
# Файлы знаков лиг названы `league-alpha.svg`: приставку в идентификаторе не
# дублируем, иначе получится `league-league-alpha`.
_LEAGUE_PREFIX = re.compile(r"^league-")


def design_root() -> Path:
    return Path(settings.BASE_DIR) / "design" / "svg"


def _namespace_ids(markup: str, prefix: str) -> str:
    """Развести одинаковые идентификаторы из разных файлов."""
    ids = set(re.findall(r'id="([^"]+)"', markup))
    for name in sorted(ids, key=len, reverse=True):
        unique = f"{prefix}-{name}"
        markup = markup.replace(f'id="{name}"', f'id="{unique}"')
        markup = markup.replace(f"url(#{name})", f"url(#{unique})")
        markup = markup.replace(f'href="#{name}"', f'href="#{unique}"')
    return markup


def _inner(markup: str) -> str:
    """Содержимое корневого `<svg>` без него самого."""
    start = markup.index(">", markup.index("<svg")) + 1
    end = markup.rindex("</svg>")
    return markup[start:end].strip()


# Атрибуты корневого `<svg>`, которые описывают холст, а не рисунок: их несёт
# сам символ или обёртка, повторять их не нужно.
_CANVAS_ATTRIBUTES = {"xmlns", "xmlns:xlink", "width", "height", "viewBox", "version"}


def root_attributes(markup: str) -> dict[str, str]:
    """Оформительские атрибуты корневого `<svg>`.

    Главный из них — `fill="none"`: фигуры без собственной заливки наследуют
    его от корня. Потеряв атрибут, они заливаются чёрным, и аватар превращается
    в чёрный круг.
    """
    head = markup[markup.index("<svg"):markup.index(">", markup.index("<svg"))]
    found = dict(re.findall(r'([\w:-]+)="([^"]*)"', head))
    return {
        name: value for name, value in found.items()
        if name not in _CANVAS_ATTRIBUTES
    }


def _attributes_markup(attributes: dict[str, str]) -> str:
    return "".join(f' {name}="{value}"' for name, value in attributes.items())


def symbol_id(kind: str, name: str) -> str:
    if kind == "league":
        return f"league-{_LEAGUE_PREFIX.sub('', name)}"
    return f"{kind}-{name}"


def read_symbol(kind: str, folder: str, view_box: str, path: Path) -> str:
    key = symbol_id(kind, path.stem)
    markup = _namespace_ids(path.read_text(encoding="utf-8"), key)
    attributes = _attributes_markup(root_attributes(markup))
    return (
        f'<symbol id="{key}" viewBox="{view_box}"{attributes}>'
        f"{_inner(markup)}</symbol>"
    )


def build_sprite() -> tuple[str, dict]:
    """Собрать спрайт. Возвращает разметку и отчёт по количеству символов."""
    root = design_root()
    parts: list[str] = []
    report: dict[str, int] = {}
    for kind, folder, view_box in SOURCES:
        files = sorted((root / folder).glob("*.svg"))
        report[kind] = len(files)
        for path in files:
            parts.append(read_symbol(kind, folder, view_box, path))
    markup = (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'xmlns:xlink="http://www.w3.org/1999/xlink" style="display:none">\n'
        + "\n".join(parts)
        + "\n</svg>\n"
    )
    return markup, report


def write_sprite() -> dict:
    markup, report = build_sprite()
    target = Path(settings.BASE_DIR) / SPRITE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(markup, encoding="utf-8")
    report["bytes"] = len(markup.encode("utf-8"))
    report["path"] = str(SPRITE_PATH)
    return report


def load_symbol(kind: str, code: str) -> tuple[dict[str, str], str]:
    """Атрибуты корня и содержимое одного символа для встраивания в страницу.

    Нужно там, где косметика анимируется: CSS не достаёт до содержимого
    внешнего спрайта через `<use>`, и анимация просто не сработала бы.
    Атрибуты корня возвращаются отдельно — без `fill="none"` рисунок
    заливается чёрным.
    """
    root = design_root()
    folder = {"avatar": "avatars", "frame": "frames", "league": "leagues"}.get(kind)
    if folder is None:
        return {}, ""
    name = code if kind != "league" else f"league-{code}"
    path = root / folder / f"{name}.svg"
    if not path.exists():
        return {}, ""
    markup = path.read_text(encoding="utf-8")
    return (
        root_attributes(markup),
        _namespace_ids(_inner(markup), symbol_id(kind, name)),
    )
