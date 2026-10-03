# -*- coding: utf-8 -*-
"""Варианты начертания греческих символов лиг.

Каждый вариант — функция (key, cx, cy, size, colors) → SVG-разметка.
Ключи: beta, alpha, sigma, omega.
"""
import os
from lib import glyph_path

FONTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")

# ── Скелеты для монолинейных вариантов (координаты в боксе 128×128) ───────
SKELETON = {
    "beta":  "M44 26 V108 M44 30 A17 17 0 1 1 44 64 A21 21 0 1 1 44 106",
    "alpha": "M82 48 C60 40 36 53 36 76 C36 99 60 110 79 99 M82 48 C72 65 70 84 80 99 L93 110",
    "sigma": "M92 28 H40 L70 64 L40 100 H96",
    "omega": "M34 42 V78 C34 93 43 102 55 102 C67 102 73 92 73 80 C73 92 79 102 91 102 C103 102 112 93 112 78 V42",
    "delta": "M64 58 C82 58 96 72 96 88 C96 104 82 116 64 116 C46 116 32 104 32 88 C32 72 46 58 64 58 M64 58 C50 48 44 34 56 26 C68 18 84 24 90 32",
    "gamma": "M24 30 C34 54 48 70 60 80 M100 30 C88 56 74 78 62 100 C56 112 50 118 44 120",
}

# Каждому скелету — своя оптическая коррекция масштаба, чтобы буквы
# выглядели одного кегля рядом друг с другом.
SK_SCALE = {"beta": 1.0, "alpha": 0.98, "sigma": 1.0, "omega": 1.0,
            "delta": 1.0, "gamma": 1.0}

# ── Гранёные скелеты в языке логотипа: только прямые, плоские срезы ───────
LOGO = {
    "beta":  "M38 10 V120 M38 26 H66 L78 40 V50 L66 62 H38 M38 62 H74 L88 78 V88 L74 102 H38",
    "alpha": "M80 44 L50 44 L20 77 L50 110 L80 110 M80 40 V110 L100 114",
    "sigma": "M98 26 H34 L66 64 L34 102 H102",
    "delta": "M64 58 L30 78 V96 L64 116 L98 96 V78 Z M64 58 L46 42 L58 24 L92 30",
    "gamma": "M38 30 L62 56 M108 22 L62 56 L48 90 L30 120",
    "omega": "M24 36 V78 L34 102 H62 L68 92 H78 L84 102 H112 L122 78 V36",
}
# оптическая высота относительно базовой: β с выносными выше, ω приземистее
LOGO_OPT = {"beta": 1.20, "alpha": 0.96, "sigma": 1.0, "omega": 0.88,
            "delta": 1.12, "gamma": 1.10}

VARIANTS = [
    ("logo",   "Логотип",     "язык фирменного знака: только прямые, плоские срезы, ровная толщина"),
    ("mono",   "Конструктив", "монолиния постоянной толщины, построенная циркулем и линейкой"),
    ("facet",  "Огранка",     "гранёный штрих со светом сверху-слева — родной язык «Призмы»"),
    ("round",  "Округлый",    "Comfortaa: геометричный дружелюбный гротеск"),
    ("antiqua","Антиква",     "EB Garamond: контрастная засечная, «дипломная»"),
    ("techno", "Техно",       "Advent Pro: узкая техничная, «космическая»"),
]

FONT_OF = {"round": "comfortaa.ttf", "antiqua": "ebgaramond.ttf", "techno": "adventpro.ttf"}
FONT_SIZE = {"round": 1.14, "antiqua": 1.42, "techno": 1.46}


def _path_bbox(d):
    """bbox для путей из абсолютных M/L/H/V — этого хватает для гранёных скелетов."""
    import re as _re
    toks = _re.findall(r"[MLHV]|-?\d+(?:\.\d+)?", d)
    x = y = 0.0
    xs, ys, cmd = [], [], "M"
    i = 0
    while i < len(toks):
        t = toks[i]
        if t in "MLHV":
            cmd = t
            i += 1
            continue
        if cmd in ("M", "L"):
            x, y = float(t), float(toks[i + 1]); i += 2
        elif cmd == "H":
            x = float(t); i += 1
        else:
            y = float(t); i += 1
        xs.append(x); ys.append(y)
    return min(xs), min(ys), max(xs), max(ys)


def _skeleton(key, cx, cy, scale):
    """Скелет, отмасштабированный и перенесённый в (cx, cy)."""
    k = scale * SK_SCALE[key]
    return (f'translate({cx:.2f} {cy:.2f}) scale({k:.4f}) translate(-64 -64)', SKELETON[key])


def draw(variant, key, cx, cy, size, light, mid, deep, ink="#FFFFFF", uid=""):
    """size — условный кегль (46 ≈ прежний). Возвращает SVG-разметку."""
    if variant == "logo":
        d = LOGO[key]
        x0, y0, x1, y1 = _path_bbox(d)
        bx, by = (x0 + x1) / 2, (y0 + y1) / 2
        target = size * 1.02 * LOGO_OPT[key]      # высота контура после масштабирования
        k = target / (y1 - y0)
        sw = 13.0 / k                              # чтобы отрисованный штрих был ровно 15
        tr = f'translate({cx:.2f} {cy:.2f}) scale({k:.4f}) translate({-bx:.2f} {-by:.2f})'
        common = 'fill="none" stroke-linecap="butt" stroke-linejoin="miter" stroke-miterlimit="2"'
        gid = f"g{uid}logo"
        off = 2.4 / k
        return (f'<defs><linearGradient id="{gid}" x1="0%" y1="0%" x2="100%" y2="100%">'
                f'<stop offset="0" stop-color="#FFFFFF"/><stop offset="1" stop-color="{light}"/>'
                f'</linearGradient></defs>'
                f'<g transform="{tr}">'
                f'<path d="{d}" {common} stroke="{deep}" stroke-opacity=".34" stroke-width="{sw*1.06:.2f}" '
                f'transform="translate({off:.2f} {off*1.3:.2f})"/>'
                f'<path d="{d}" {common} stroke="url(#{gid})" stroke-width="{sw:.2f}"/></g>')

    if variant == "mono":
        tr, d = _skeleton(key, cx, cy, size / 46.0 * 0.76)
        return (f'<g transform="{tr}">'
                f'<path d="{d}" fill="none" stroke="{deep}" stroke-opacity=".3" stroke-width="13" '
                f'stroke-linecap="round" stroke-linejoin="round" transform="translate(1.5 2.5)"/>'
                f'<path d="{d}" fill="none" stroke="{ink}" stroke-width="11" '
                f'stroke-linecap="round" stroke-linejoin="round"/></g>')

    if variant == "facet":
        tr, d = _skeleton(key, cx, cy, size / 46.0 * 0.76)
        return (f'<g transform="{tr}">'
                f'<path d="{d}" fill="none" stroke="{deep}" stroke-opacity=".55" stroke-width="15" '
                f'stroke-linecap="butt" stroke-linejoin="miter" transform="translate(3 4)"/>'
                f'<path d="{d}" fill="none" stroke="{deep}" stroke-width="14" '
                f'stroke-linecap="butt" stroke-linejoin="miter"/>'
                f'<path d="{d}" fill="none" stroke="{ink}" stroke-width="9.5" '
                f'stroke-linecap="butt" stroke-linejoin="miter" transform="translate(-1.6 -2.2)"/>'
                f'<path d="{d}" fill="none" stroke="{light}" stroke-width="3.4" '
                f'stroke-linecap="butt" transform="translate(-4 -5.2)"/></g>')

    fnt = os.path.join(FONTS, FONT_OF[variant])
    s = size * FONT_SIZE[variant]
    ch = {"beta": "β", "alpha": "α", "sigma": "Σ", "omega": "ω",
          "delta": "δ", "gamma": "γ"}[key]
    d1 = glyph_path(ch, s, cx + 1.5, cy + 2.5, fnt)
    d2 = glyph_path(ch, s, cx, cy, fnt)
    return (f'<path d="{d1}" fill="{deep}" fill-opacity=".3"/>'
            f'<path d="{d2}" fill="{ink}"/>')
