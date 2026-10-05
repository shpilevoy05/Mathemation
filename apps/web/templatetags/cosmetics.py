"""Отрисовка косметики: аватары, рамки и знаки лиг.

Два способа показать одну и ту же картинку, и выбор между ними не стилистический:

* **из спрайта** — ссылка на `static/img/cosmetics.svg`. Один запрос на всю
  страницу, кеш браузера, минимум разметки. Так рисуется всё, что стоит в
  списках и таблицах;
* **встраиванием** — разметка кладётся прямо в страницу. Нужно там, где вещь
  анимирована: CSS не достаёт до содержимого внешнего спрайта через `<use>`,
  и правила из `cosmetics.css` просто не сработали бы.

Поэтому шаблон не выбирает способ сам: тег смотрит на каталог и встраивает
только то, что действительно движется.
"""

from __future__ import annotations

from functools import lru_cache

from django import template
from django.templatetags.static import static
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from apps.economy.catalog import is_animated
from apps.economy.sprite import SPRITE_PATH, load_symbol, symbol_id

register = template.Library()


@lru_cache(maxsize=128)
def _inline_markup(kind: str, code: str) -> tuple[str, str]:
    """Разметка вещи и атрибуты её корня — строкой, готовой к вставке."""
    attributes, markup = load_symbol(kind, code)
    head = "".join(f' {name}="{value}"' for name, value in attributes.items())
    return head, markup


def _sprite_url() -> str:
    return static(str(SPRITE_PATH).replace("static\\", "").replace("static/", "")
                  .replace("\\", "/"))


@register.simple_tag
def cosmetic(kind: str, code: str, view_box: str = "", css_class: str = ""):
    """Картинка косметики: из спрайта или встроенная, если она анимирована."""
    if not code:
        return ""
    boxes = {
        "avatar": "0 0 128 128", "frame": "0 0 160 160",
        "league": "0 0 128 128", "pennant": "0 0 128 128",
    }
    box = view_box or boxes.get(kind, "0 0 128 128")
    classes = f"{kind}-{code} {css_class}".strip()
    if is_animated(kind, code):
        head, markup = _inline_markup(kind, code)
        if markup:
            # `fill="none"` и прочие атрибуты корня едут вместе с рисунком:
            # без них фигуры без своей заливки становятся чёрными.
            return format_html(
                '<svg class="{}" viewBox="{}"{} aria-hidden="true">{}</svg>',
                classes, box, mark_safe(head), mark_safe(markup),
            )
    return format_html(
        '<svg class="{}" viewBox="{}" fill="none" aria-hidden="true">'
        '<use href="{}#{}"></use></svg>',
        classes, box, _sprite_url(), symbol_id(kind, code),
    )


@register.simple_tag
def league_mark(league: str, place: int | None = None, css_class: str = ""):
    """Знак лиги. Для места 1–3 берётся отдельный знак с жетоном.

    Лига читается по знаку, поэтому подставлять чужой нельзя: лига, для которой
    знака нет, показывается без него, а не с гербом соседней.
    """
    from apps.economy.catalog import LEAGUE_MARKS, LEAGUE_PLACES

    if league not in LEAGUE_MARKS:
        return ""
    code = f"{league}-{place}" if place in LEAGUE_PLACES else league
    return format_html(
        '<svg class="league-mark {}" viewBox="0 0 128 128" fill="none" '
        'aria-hidden="true"><use href="{}#league-{}"></use></svg>',
        css_class, _sprite_url(), code,
    )


@register.simple_tag
def has_league_mark(league: str) -> bool:
    from apps.economy.catalog import LEAGUE_MARKS

    return league in LEAGUE_MARKS
