# -*- coding: utf-8 -*-
"""Знаки лиг: пластина + начертание символа. Стиль «Призма»."""
import math
from lib import svg_doc, lg, rg, txt, LEAGUES, MEDALS
import glyphs

W = "#FFFFFF"


def _star8(cx=64, cy=64, ro=58, ri=27, n=8, rot=-90):
    pts = []
    for i in range(n * 2):
        r = ro if i % 2 == 0 else ri
        a = math.radians(rot + i * 180.0 / n)
        pts.append(f"{cx + r*math.cos(a):.1f},{cy + r*math.sin(a):.1f}")
    return "M" + "L".join(pts) + "Z"


def _rosette(n=12, r=45, br=15, cx=64, cy=64):
    pts = [(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a)))
           for a in range(-90, 270, 360 // n)]
    d = f"M{pts[0][0]:.1f} {pts[0][1]:.1f}"
    for x, y in pts[1:] + [pts[0]]:
        d += f"A{br} {br} 0 0 1 {x:.1f} {y:.1f}"
    return d + "Z"


# ── Пластины: key → {вариант: (путь, центр глифа по Y, кегль)} ────────────
PLATES = {
    "delta": {
        "triangle": ("M58 14 C61 8 67 8 70 14 L116 104 C119 110 116 117 109 117 H19 "
                     "C12 117 9 110 12 104 Z", 76, 32),
    },
    "gamma": {
        "rhombus": ("M58 12 C61 9 67 9 70 12 L116 58 C119 61 119 67 116 70 L70 116 "
                    "C67 119 61 119 58 116 L12 70 C9 67 9 61 12 58 Z", 64, 42),
    },
    "beta": {
        "shield": ("M64 10 C84 10 100 16 106 21 C106 60 98 98 64 118 C30 98 22 60 22 21 C28 16 44 10 64 10 Z", 58, 44),
    },
    "alpha": {
        "rosette":  (_rosette(), 64, 40),
        "gem":      ("M44 10 H84 L112 44 L64 122 L16 44 Z", 50, 34),
        "pentagon": ("M64 8 L118 47 L97 116 H31 L10 47 Z", 64, 44),
        "star":     (_star8(), 64, 38),
    },
    "sigma": {
        "crown":   ("M14 30 L34 54 L48 16 L64 44 L80 16 L94 54 L114 30 L106 102 "
                    "C106 111 99 118 90 118 H38 C29 118 22 111 22 102 Z", 82, 38),
        "cup":     ("M26 12 H102 V36 C102 65 85 85 72 89 V102 H90 C95 102 99 106 99 111 V120 H29 V111 "
                    "C29 106 33 102 38 102 H56 V89 C43 85 26 65 26 36 Z", 46, 32),
        "octagon": ("M42 8 H86 L120 42 V86 L86 120 H42 L8 86 V42 Z", 64, 44),
        "pennant": ("M26 8 H102 C106 8 108 10 108 14 V102 C108 106 104 108 101 106 L64 86 L27 106 "
                    "C24 108 20 106 20 102 V14 C20 10 22 8 26 8 Z", 54, 38),
    },
    "omega": {
        "hex": ("M64 8 L112 34 V94 L64 120 L16 94 V34 Z", 64, 42),
    },
}

# Выбранные по умолчанию пластины
DEFAULT_PLATE = {"delta": "triangle", "gamma": "rhombus", "beta": "shield",
                 "alpha": "pentagon", "sigma": "octagon", "omega": "hex"}
DEFAULT_GLYPH = "logo"

# порядок лестницы: от младшей лиги к старшей
ORDER = ["delta", "gamma", "omega", "beta", "alpha", "sigma"]


def mark(key, place=None, plate=None, glyph=None):
    L = LEAGUES[key]
    plate = plate or DEFAULT_PLATE[key]
    glyph = glyph or DEFAULT_GLYPH
    p, gy, gs = PLATES[key][plate]
    uid = f"L{key}{plate}{glyph}{place or 0}"

    if place:
        M = MEDALS[place]
        c1, c2, c3, c4 = M["a"], M["b"], M["c"], M["d"]
    else:
        c1, c2, c3, c4 = L["light"], L["mid"], L["deep"], L["deep"]

    defs = "\n".join([
        lg(f"{uid}p", [("0", c1, 1), ("0.35", c2, 1), ("0.72", c3, 1), ("1", c4, 1)],
           x1="12%", y1="0%", x2="88%", y2="100%"),
        lg(f"{uid}i", [("0", c2, 1), ("0.55", c3, 1), ("1", c4, 1)],
           x1="0%", y1="0%", x2="60%", y2="100%"),
        lg(f"{uid}g", [("0", W, 0.55), ("0.45", W, 0.10), ("1", W, 0)],
           x1="0%", y1="0%", x2="70%", y2="100%"),
        rg(f"{uid}c", [("0", L["light"], 1), ("1", L["mid"], 1)], cx="35%", cy="25%", r="80%"),
    ])
    body = [
        f'<path d="{p}" fill="url(#{uid}p)"/>',
        f'<g transform="translate(64,64) scale(.86) translate(-64,-64)"><path d="{p}" fill="url(#{uid}i)" opacity=".55"/></g>',
        f'<g transform="translate(64,64) scale(.74) translate(-64,-64)"><path d="{p}" fill="url(#{uid}c)"/></g>',
        glyphs.draw(glyph, key, 64, gy, gs, L["light"], L["mid"], L["deep"], W, uid),
        f'<path d="{p}" fill="url(#{uid}g)"/>',
        f'<path d="{p}" fill="none" stroke="{c4}" stroke-opacity=".45" stroke-width="2.5" stroke-linejoin="round"/>',
    ]
    if place:
        body.append(
            f'<circle cx="101" cy="103" r="18" fill="url(#{uid}p)" stroke="{c4}" stroke-opacity=".5" stroke-width="2"/>'
            + txt(101, 103, str(place), 21, c4, 800))
    return svg_doc(128, 128, defs, "\n".join(body))


def build(plate_map=None, glyph=None):
    """{key: (подпись, svg)} — базовые знаки и три места для каждой лиги."""
    pm = dict(DEFAULT_PLATE)
    pm.update(plate_map or {})
    out = {}
    for k in ORDER:
        out[f"league-{k}"] = (LEAGUES[k]["ru"], mark(k, None, pm[k], glyph))
        for pl in (1, 2, 3):
            out[f"league-{k}-{pl}"] = (f'{LEAGUES[k]["ru"]} · {MEDALS[pl]["ru"]}',
                                       mark(k, pl, pm[k], glyph))
    return out
