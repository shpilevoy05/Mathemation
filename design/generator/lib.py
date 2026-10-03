# -*- coding: utf-8 -*-
"""Общие примитивы для генерации SVG-набора Mathemation."""

FONT = "Inter, DejaVu Sans, Arial, sans-serif"

# ── Палитра сервиса (из Кабинет - визуальный апгрейд.dc.html) ─────────────
INK        = "#10162A"
MUTED      = "#6B7590"
LINE       = "#DCE3F6"
PRIMARY    = "#4F6BEA"
PRIMARY_D  = "#2E45B8"
PRIMARY_L  = "#8FA2FF"

LEAGUES = {
    "delta": dict(ru="Дельта", glyph="δ", light="#E7C9A6", mid="#B8865C", deep="#6B4520", tint="#F6E8D8"),
    "gamma": dict(ru="Гамма", glyph="γ", light="#A8D8F0", mid="#3E9AD0", deep="#0C4468", tint="#DDF0FA"),
    "beta":  dict(ru="Бетта", glyph="β", light="#5FD6A4", mid="#0E9A64", deep="#0A6244", tint="#DFF3E9"),
    "alpha": dict(ru="Альфа", glyph="α", light="#FFB765", mid="#F58A1E", deep="#8A4A06", tint="#FDECD8"),
    "sigma": dict(ru="Сигма", glyph="Σ", light="#FFD34E", mid="#D8A21C", deep="#7A5A05", tint="#FAEFD9"),
    "omega": dict(ru="Омега", glyph="ω", light="#B79BF2", mid="#7B5CD6", deep="#3E2A85", tint="#EDE8FB"),
}

MEDALS = {
    1: dict(ru="1 место", label="золото",  a="#FFF0BE", b="#F5C63C", c="#B98407", d="#7A5405"),
    2: dict(ru="2 место", label="серебро", a="#FBFCFF", b="#D2DAEA", c="#8E9AB8", d="#5C6884"),
    3: dict(ru="3 место", label="бронза",  a="#F7DCC0", b="#D79A62", c="#9E5F2A", d="#6B3D18"),
}


def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def svg_doc(w, h, defs, body, extra=""):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" fill="none"{extra}>\n'
        f'<defs>\n{defs}\n</defs>\n{body}\n</svg>\n'
    )


def rg(idn, stops, cx="50%", cy="50%", r="50%", fx=None, fy=None):
    """radialGradient; stops = [(offset, color, opacity), ...]"""
    f = f' fx="{fx}" fy="{fy}"' if fx is not None else ""
    s = "".join(
        f'<stop offset="{o}" stop-color="{c}" stop-opacity="{op}"/>' for o, c, op in stops
    )
    return f'<radialGradient id="{idn}" cx="{cx}" cy="{cy}" r="{r}"{f}>{s}</radialGradient>'


def lg(idn, stops, x1="0%", y1="0%", x2="0%", y2="100%"):
    s = "".join(
        f'<stop offset="{o}" stop-color="{c}" stop-opacity="{op}"/>' for o, c, op in stops
    )
    return f'<linearGradient id="{idn}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}">{s}</linearGradient>'


_FONTS = {}
_SANS = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
_SERIF = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"


def _font(path):
    from fontTools.ttLib import TTFont
    if path not in _FONTS:
        _FONTS[path] = TTFont(path)
    return _FONTS[path]


def glyph_path(s, size, cx, cy, font=None):
    """Контур текста как <path d>: центрируется по (cx, cy). Без зависимости от шрифтов."""
    from fontTools.pens.svgPathPen import SVGPathPen
    from fontTools.pens.transformPen import TransformPen
    from fontTools.pens.boundsPen import BoundsPen
    from fontTools.misc.transform import Transform
    path = font or _SERIF
    f = _font(path)
    upem = f["head"].unitsPerEm
    gs = f.getGlyphSet()
    cmap = f.getBestCmap()
    names = [cmap[ord(ch)] for ch in s]
    k = size / upem
    # общая ширина и bbox
    adv, bb = 0, [1e9, 1e9, -1e9, -1e9]
    for n in names:
        bp = BoundsPen(gs)
        gs[n].draw(bp)
        if bp.bounds:
            x0, y0, x1, y1 = bp.bounds
            bb = [min(bb[0], adv + x0), min(bb[1], y0), max(bb[2], adv + x1), max(bb[3], y1)]
        adv += gs[n].width
    w = (bb[2] - bb[0]) * k
    h = (bb[3] - bb[1]) * k
    ox = cx - w / 2 - bb[0] * k
    oy = cy + h / 2 + bb[1] * k
    out, adv = [], 0
    for n in names:
        pen = SVGPathPen(gs, ntos=lambda v: f"{v:.2f}")
        tp = TransformPen(pen, Transform(k, 0, 0, -k, ox + adv * k, oy))
        gs[n].draw(tp)
        out.append(pen.getCommands())
        adv += gs[n].width
    return " ".join(x for x in out if x)


def txt(x, y, s, size, color, weight=700, anchor="middle", opacity=1, extra="", font=None):
    d = glyph_path(s, size * 1.0, x, y, font)
    op = f' fill-opacity="{opacity}"' if opacity != 1 else ""
    fl = f' fill="{color}"' if color else ""
    return f'<path d="{d}"{fl}{op}{extra}/>'


# ── Оболочка аватара, стиль A: «Призма» (объёмный градиент + стекло) ──────
def shell_a(uid, light, mid, deep, art, rim_op=0.75):
    defs = "\n".join([
        rg(f"{uid}b", [("0", light, 1), ("0.52", mid, 1), ("1", deep, 1)],
           cx="34%", cy="26%", r="82%"),
        rg(f"{uid}s", [("0.62", deep, 0), ("0.88", deep, 0.18), ("1", deep, 0.42)],
           cx="50%", cy="50%", r="50%"),
        rg(f"{uid}g", [("0", "#FFFFFF", 0.62), ("0.55", "#FFFFFF", 0.20), ("1", "#FFFFFF", 0)],
           cx="50%", cy="50%", r="50%"),
        lg(f"{uid}r", [("0", "#FFFFFF", 0.9), ("0.45", "#FFFFFF", 0.25), ("1", "#FFFFFF", 0)]),
    ])
    body = f"""<circle cx="64" cy="64" r="60" fill="url(#{uid}b)"/>
{art}
<circle cx="64" cy="64" r="60" fill="url(#{uid}s)"/>
<ellipse cx="60" cy="33" rx="40" ry="23" fill="url(#{uid}g)"/>
<circle cx="64" cy="64" r="59" stroke="url(#{uid}r)" stroke-width="2" opacity="{rim_op}"/>
<circle cx="64" cy="64" r="62.5" stroke="{deep}" stroke-opacity="0.14" stroke-width="3"/>"""
    return defs, body


# ── Оболочка аватара, стиль B: «Артель» (иллюстративный, персонажный) ─────
def shell_b(uid, tint, mid, ink, art):
    defs = "\n".join([
        lg(f"{uid}b", [("0", tint, 1), ("1", mid, 1)]),
    ])
    body = f"""<circle cx="64" cy="64" r="60" fill="url(#{uid}b)"/>
<path d="M4 64a60 60 0 0 0 120 0c0-4-.4-8-1.2-12C110 66 88 76 64 76S18 66 5.2 52A60 60 0 0 0 4 64Z" fill="{ink}" fill-opacity="0.06"/>
{art}
<circle cx="64" cy="64" r="60" stroke="{ink}" stroke-width="4"/>"""
    return defs, body
