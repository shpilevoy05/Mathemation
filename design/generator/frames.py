# -*- coding: utf-8 -*-
"""14 рамок × 2 стиля. Холст 160×160, отверстие под аватар r=52 в центре."""
import math
from lib import svg_doc, lg, rg

C = 80.0
W = "#FFFFFF"


def pol(r, a, cx=C, cy=C):
    t = math.radians(a)
    return cx + r * math.cos(t), cy + r * math.sin(t)


def ring_arc(r, a0, a1, cx=C, cy=C):
    x0, y0 = pol(r, a0, cx, cy)
    x1, y1 = pol(r, a1, cx, cy)
    large = 1 if abs(a1 - a0) > 180 else 0
    sweep = 1 if a1 > a0 else 0
    return f"M{x0:.2f} {y0:.2f} A{r} {r} 0 {large} {sweep} {x1:.2f} {y1:.2f}"


# key, ru, категория, свет, основной, глубокий, «чернила» для стиля B
SPEC = [
    ("coordinates", "Координаты", "Математика",  "#A9BAFF", "#4F6BEA", "#22318E", "#22318E"),
    ("integral",    "Интеграл",   "Математика",  "#7FE0CD", "#17A88E", "#075949", "#075949"),
    ("tessellation","Тесселяция", "Математика",  "#9FD6FF", "#3E8FD8", "#12456F", "#12456F"),
    ("flame",       "Пламя",      "Природа",     "#FFD36B", "#F5751E", "#8A2E05", "#8A2E05"),
    ("bloom",       "Цветущая",   "Природа",     "#FFC2DA", "#EE5C93", "#8A1E4A", "#8A1E4A"),
    ("ivy",         "Плющ",       "Природа",     "#9BE8A8", "#2FA85A", "#0C5A2A", "#0C5A2A"),
    ("saturn",      "Сатурн",     "Космос",      "#C7B4FF", "#7B5CD6", "#37237A", "#37237A"),
    ("comet",       "Комета",     "Космос",      "#FFE08A", "#F0A81E", "#8A5A05", "#8A5A05"),
    ("nebula",      "Туманность", "Космос",      "#E0A8FF", "#9A3FD8", "#4A0E76", "#4A0E76"),
    ("pcb",         "Плата",      "Информатика", "#8FE8C0", "#0E9A64", "#065138", "#065138"),
    ("bitflow",     "Битовый ток","Информатика", "#8ADCF6", "#1E9AD0", "#0A5476", "#0A5476"),
    ("aurora",      "Аврора",     "Новые",       "#7FF0D8", "#2FC9C0", "#0A5A6E", "#0A5A6E"),
    ("vitrage",     "Витраж",     "Новые",       "#FFC4A8", "#D8543C", "#7A1E12", "#7A1E12"),
    ("gears",       "Механизм",   "Новые",       "#F2D6A8", "#C08A3E", "#6B4412", "#6B4412"),
]


# ══════════════════════════════════════════════════════════════════════════
def base_a(uid, light, mid, deep, r=62, w=7):
    defs = lg(f"{uid}r", [("0", light, 1), ("0.5", mid, 1), ("1", deep, 1)],
              x1="10%", y1="0%", x2="90%", y2="100%")
    body = (f'<circle cx="80" cy="80" r="{r}" stroke="url(#{uid}r)" stroke-width="{w}"/>'
            f'<circle cx="80" cy="80" r="{r - w/2 + 0.8:.1f}" stroke="{W}" stroke-opacity=".38" stroke-width="1.4"/>')
    return defs, body


def base_b(uid, light, mid, ink, r=62, w=9):
    body = (f'<circle cx="80" cy="80" r="{r}" stroke="{mid}" stroke-width="{w}"/>'
            f'<circle cx="80" cy="80" r="{r + w/2:.1f}" stroke="{ink}" stroke-width="3"/>'
            f'<circle cx="80" cy="80" r="{r - w/2:.1f}" stroke="{ink}" stroke-width="3"/>')
    return "", body


def decor(key, style, light, mid, deep, ink):
    """Возвращает (defs, body) для декора рамки."""
    uid = f"{style}{key}"
    A = style == "a"
    fill_main = mid
    op = ' fill-opacity=".92"' if A else ""
    S = f' stroke="{ink}" stroke-width="2.6" stroke-linejoin="round"' if not A else ""
    defs, out = "", []

    if key == "coordinates":
        d, b = (base_a(uid, light, mid, deep, 62, 3) if A else base_b(uid, light, mid, ink, 62, 4))
        defs += d
        out.append(f'<circle class="cd-orbit" cx="80" cy="80" r="70" stroke="{mid}" stroke-width="{3 if A else 3}" stroke-dasharray="2 8" stroke-linecap="round" opacity="{0.9 if A else 1}"/>')
        out.append(b)
        for a in (0, 90, 180, 270):
            x0, y0 = pol(56, a); x1, y1 = pol(76, a)
            out.append(f'<path class="cd-tick" d="M{x0:.1f} {y0:.1f} L{x1:.1f} {y1:.1f}" stroke="{mid}" stroke-width="4.5" stroke-linecap="round"/>')
        for a in range(22, 360, 45):
            x, y = pol(70, a)
            out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.4" fill="{fill_main}"{op}{S}/>')

    elif key == "integral":
        d, b = (base_a(uid, light, mid, deep, 61, 3.5) if A else base_b(uid, light, mid, ink, 61, 4))
        defs += d; out.append(b)
        swash = "M58 16 C76 6 92 16 88 30 C85 44 70 47 64 34"
        for rot in (0, 180):
            under = "" if A else (f'<path d="{swash}" fill="none" stroke="{ink}" stroke-width="9.5" stroke-linecap="round"/>')
            out.append(f'<g transform="rotate({rot} 80 80)">{under}'
                       f'<path d="{swash}" fill="none" '
                       f'stroke="{fill_main}" stroke-width="5.5" stroke-linecap="round"/></g>')
        for a in range(0, 360, 20):
            x, y = pol(69, a)
            out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2" fill="{fill_main}" fill-opacity="{0.7 if A else 1}"/>')

    elif key == "tessellation":
        for i, a in enumerate(range(0, 360, 20)):
            x, y = pol(68, a)
            pts = " ".join(f"{px:.1f},{py:.1f}" for px, py in
                           [pol(11, a, x, y), pol(11, a + 130, x, y), pol(11, a + 230, x, y)])
            col = light if i % 2 else mid
            out.append(f'<polygon class="ts-tri" style="--i:{i}" points="{pts}" fill="{col}"{S}/>')
        d, b = (base_a(uid, light, mid, deep, 58, 4) if A else base_b(uid, light, mid, ink, 58, 5))
        defs += d; out.append(b)

    elif key == "flame":
        defs += lg(f"{uid}f", [("0", light, 1), ("1", mid, 1)])
        for i, a in enumerate(range(0, 360, 24)):
            x, y = pol(64, a)
            g = f"rotate({a + 90} {x:.1f} {y:.1f}) translate({x:.1f} {y:.1f})"
            out.append(f'<g class="fl-tongue" style="--i:{i}" transform="{g}"><path d="M0 -13 C6 -5 8 0 8 4 C8 10 4 14 0 14 C-4 14 -8 10 -8 4 C-8 0 -6 -5 0 -13 Z" '
                       f'fill="{f"url(#{uid}f)" if A else mid}"{S}/>'
                       f'<path d="M0 -3 C3 1 4 4 4 6 C4 9 2 11 0 11 C-2 11 -4 9 -4 6 C-4 4 -3 1 0 -3 Z" fill="{light if not A else W}" fill-opacity="{0.75 if A else 1}"/></g>')
        d, b = (base_a(uid, light, mid, deep, 56, 3) if A else base_b(uid, light, mid, ink, 56, 3.5))
        defs += d; out.append(b)

    elif key == "bloom":
        d, b = (base_a(uid, light, mid, deep, 60, 3) if A else base_b(uid, light, mid, ink, 60, 3.5))
        defs += d; out.append(b)
        for i, a in enumerate(range(0, 360, 45)):
            x, y = pol(68, a)
            petals = "".join(
                f'<ellipse cx="{px:.1f}" cy="{py:.1f}" rx="4.6" ry="7" fill="{light if A else "#FFD9E6"}" '
                f'fill-opacity="{0.95 if A else 1}"{S} transform="rotate({a + 72*k + 90} {px:.1f} {py:.1f})"/>'
                for k, (px, py) in enumerate(pol(5.2, a + 72 * k, x, y) for k in range(5)))
            out.append(f'<g class="bl-flower" style="--i:{i};--cx:{x:.1f}px;--cy:{y:.1f}px">{petals}<circle cx="{x:.1f}" cy="{y:.1f}" r="3.6" fill="{mid if A else "#FFC24E"}"{S}/></g>')
        for a in range(22, 360, 45):
            x, y = pol(70, a)
            out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.4" fill="{fill_main}" fill-opacity="{0.7 if A else 1}"/>')

    elif key == "ivy":
        pts = []
        for a in range(0, 361, 6):
            rr = 63 + 5 * math.sin(math.radians(a * 6))
            pts.append("%.1f %.1f" % pol(rr, a))
        out.append(f'<path d="M{pts[0]} ' + " L".join(pts[1:]) + f'" fill="none" stroke="{mid}" stroke-width="{3.8 if A else 4}" stroke-linecap="round" opacity="{0.9 if A else 1}"/>')
        if not A:
            out.append(f'<path d="M{pts[0]} ' + " L".join(pts[1:]) + f'" fill="none" stroke="{ink}" stroke-width="1.4" opacity=".35"/>')
        for i, a in enumerate(range(0, 360, 30)):
            x, y = pol(69 if i % 2 == 0 else 57, a)
            out.append(f'<g class="iv-leaf" style="--i:{i}" transform="rotate({a + 40} {x:.1f} {y:.1f}) translate({x:.1f} {y:.1f})">'
                       f'<path d="M0 0 C9 -11 19 -8 20 3 C11 12 1 9 0 0 Z" fill="{light if A else "#7BD68F"}" '
                       f'fill-opacity="{0.95 if A else 1}"{S}/>'
                       f'<path d="M0.5 0.5 L18 2" stroke="{deep if A else ink}" stroke-opacity="{0.35 if A else 0.55}" stroke-width="1.8"/></g>')

    elif key == "saturn":
        defs += lg(f"{uid}o", [("0", light, 1), ("0.5", mid, 1), ("1", deep, 1)], x1="0%", y1="0%", x2="100%", y2="100%")
        d, b = (base_a(uid, light, mid, deep, 56, 3) if A else base_b(uid, light, mid, ink, 56, 4))
        defs += d; out.append(b)
        for rx, ry, wdt in ((76, 26, 7), (66, 22, 3)):
            if not A:
                out.append(f'<ellipse cx="80" cy="80" rx="{rx}" ry="{ry}" stroke="{ink}" stroke-width="{wdt+5}" transform="rotate(-20 80 80)" fill="none"/>')
            out.append(f'<g class="st-ring st-r{0 if rx>70 else 1}"><ellipse cx="80" cy="80" rx="{rx}" ry="{ry}" stroke="{f"url(#{uid}o)" if A else mid}" '
                       f'stroke-width="{wdt}" transform="rotate(-20 80 80)" fill="none"/></g>')
        for a, rr, rad in ((28, 78, 5.5), (208, 78, 4.4)):
            x, y = pol(rr, a)
            out.append(f'<circle class="st-moon" cx="{x:.1f}" cy="{y:.1f}" r="{rad}" fill="{light if A else "#FFD34E"}"{S}/>')

    elif key == "comet":
        defs += lg(f"{uid}t", [("0", light, 0.05), ("0.5", light, 0.85), ("1", mid, 1)], x1="0%", y1="0%", x2="100%", y2="0%")
        seg = []
        tail = ring_arc(64, 200, 480)
        seg.append(f'<path class="cm-tail" pathLength="100" d="{tail}" fill="none" stroke="{f"url(#{uid}t)" if A else mid}" stroke-width="7" stroke-linecap="round"/>')
        if not A:
            seg.append(f'<path class="cm-tail" d="{tail}" fill="none" stroke="{ink}" stroke-width="2.4" opacity=".4"/>')
        for i, a in enumerate(range(150, 205, 12)):
            x, y = pol(64, a)
            seg.append(f'<circle class="cm-dust" style="--i:{i}" cx="{x:.1f}" cy="{y:.1f}" r="{4.4 - i*0.8:.1f}" fill="{mid}" fill-opacity="{0.85 - i*0.15:.2f}"/>')
        hx, hy = pol(64, 120)
        seg.append(f'<g class="cm-head"><circle cx="{hx:.1f}" cy="{hy:.1f}" r="12" fill="{mid if A else "#FFD34E"}"{S}/>'
                   f'<circle cx="{hx-3:.1f}" cy="{hy-3:.1f}" r="4.6" fill="{light if A else W}" fill-opacity=".95"/></g>')
        out.append(f'<g class="cm-orbit">{"".join(seg)}</g>')
        for a in (35, 95, 300):
            x, y = pol(74, a)
            out.append(f'<path class="cm-spark" d="M{x:.1f} {y-5:.1f} L{x+1.6:.1f} {y-1.6:.1f} L{x+5:.1f} {y:.1f} L{x+1.6:.1f} {y+1.6:.1f} L{x:.1f} {y+5:.1f} L{x-1.6:.1f} {y+1.6:.1f} L{x-5:.1f} {y:.1f} L{x-1.6:.1f} {y-1.6:.1f} Z" fill="{mid if A else "#FFD34E"}" fill-opacity=".95"/>')

    elif key == "nebula":
        defs += rg(f"{uid}n", [("0.68", deep, 0), ("0.82", mid, 0.75), ("0.92", light, 0.9), ("1", light, 0)])
        out.append(f'<circle class="nb-glow" cx="80" cy="80" r="80" fill="url(#{uid}n)"/>')
        if not A:
            out.append(f'<circle cx="80" cy="80" r="70" stroke="{ink}" stroke-width="3"/>'
                       f'<circle cx="80" cy="80" r="55" stroke="{ink}" stroke-width="3"/>')
        for i, (a, rr, rad) in enumerate(((20, 72, 3), (75, 66, 2), (130, 74, 3.6), (190, 68, 2.2), (250, 73, 3), (310, 67, 2.4), (345, 70, 2))):
            x, y = pol(rr, a)
            out.append(f'<circle class="nb-star" style="--i:{i}" cx="{x:.1f}" cy="{y:.1f}" r="{rad}" fill="{W}" fill-opacity=".95"/>')
        for a in (60, 240):
            x, y = pol(71, a)
            out.append(f'<path d="M{x:.1f} {y-7:.1f} L{x+2:.1f} {y-2:.1f} L{x+7:.1f} {y:.1f} L{x+2:.1f} {y+2:.1f} L{x:.1f} {y+7:.1f} L{x-2:.1f} {y+2:.1f} L{x-7:.1f} {y:.1f} L{x-2:.1f} {y-2:.1f} Z" fill="{W}"/>')

    elif key == "pcb":
        d, b = (base_a(uid, light, mid, deep, 60, 3.4) if A else base_b(uid, light, mid, ink, 60, 4))
        defs += d; out.append(b)
        for i, a in enumerate(range(0, 360, 30)):
            x0, y0 = pol(60, a); x1, y1 = pol(72, a)
            out.append(f'<path d="M{x0:.1f} {y0:.1f} L{x1:.1f} {y1:.1f}" stroke="{mid}" '
                       f'stroke-width="{3.2 if A else 3.6}" stroke-linecap="round"/>')
            out.append(f'<circle cx="{x1:.1f}" cy="{y1:.1f}" r="4.6" fill="{light if A else "#FFD34E"}"{S}/>')
            out.append(f'<circle cx="{x1:.1f}" cy="{y1:.1f}" r="1.8" fill="{deep if A else ink}" fill-opacity="{0.55 if A else 1}"/>')
        for a in range(15, 360, 90):
            out.append(f'<path d="{ring_arc(72, a, a + 60)}" fill="none" stroke="{mid}" stroke-width="{2.6 if A else 3}" stroke-linecap="round" opacity="{0.8 if A else 1}"/>')

    elif key == "bitflow":
        d, b = (base_a(uid, light, mid, deep, 58, 2.4) if A else base_b(uid, light, mid, ink, 58, 3))
        defs += d; out.append(b)
        defs += lg(f"{uid}p", [("0", light, 0), ("0.5", light, 1), ("1", deep, 1)], x1="0%", y1="100%", x2="100%", y2="0%")
        for i, a in enumerate(range(0, 360, 15)):
            x, y = pol(69, a)
            if i % 2 == 0:
                out.append(f'<ellipse class="bt-bit" style="--i:{i}" cx="{x:.1f}" cy="{y:.1f}" rx="3.4" ry="5" fill="none" stroke="{mid}" stroke-width="2.8" transform="rotate({a+90} {x:.1f} {y:.1f})"/>')
            else:
                x0, y0 = pol(64, a); x1, y1 = pol(74, a)
                out.append(f'<path class="bt-bit" style="--i:{i}" d="M{x0:.1f} {y0:.1f} L{x1:.1f} {y1:.1f}" stroke="{mid}" stroke-width="3" stroke-linecap="round"/>')
        out.append(f'<path class="bt-pulse" d="{ring_arc(69, 200, 290)}" fill="none" stroke="{f"url(#{uid}p)" if A else "#FFD34E"}" stroke-width="6" stroke-linecap="round" opacity=".95"/>')

    elif key == "aurora":
        defs += lg(f"{uid}a1", [("0", light, 0), ("0.25", light, 1), ("0.75", mid, 1), ("1", mid, 0)], x1="0%", y1="0%", x2="100%", y2="100%")
        defs += lg(f"{uid}a2", [("0", "#B79BF2", 0), ("0.3", "#B79BF2", 1), ("0.8", "#7B5CD6", 1), ("1", "#7B5CD6", 0)], x1="100%", y1="0%", x2="0%", y2="100%")
        defs += lg(f"{uid}a3", [("0", deep, 0), ("0.35", mid, 1), ("1", light, 0)], x1="0%", y1="100%", x2="100%", y2="0%")
        bands = [(75, 6.5, 165, 415, f"{uid}a1", mid),
                 (66, 5.0, 40, 265, f"{uid}a2", "#7B5CD6"),
                 (57.5, 3.2, 250, 470, f"{uid}a3", light)]
        for bi, (rr, wdt, a0, a1, g, flat) in enumerate(bands):
            if not A:
                out.append(f'<path d="{ring_arc(rr, a0, a1)}" fill="none" stroke="{ink}" stroke-width="{wdt+4}" stroke-linecap="round"/>')
            out.append(f'<path class="au-band" style="--i:{bi}" d="{ring_arc(rr, a0, a1)}" fill="none" stroke="{f"url(#{g})" if A else flat}" stroke-width="{wdt}" stroke-linecap="round"/>')
        for a, rr in ((40, 78), (140, 52), (215, 79), (300, 53), (350, 70)):
            x, y = pol(rr, a)
            out.append(f'<path d="M{x:.1f} {y-5:.1f} L{x+1.4:.1f} {y-1.4:.1f} L{x+5:.1f} {y:.1f} L{x+1.4:.1f} {y+1.4:.1f} L{x:.1f} {y+5:.1f} L{x-1.4:.1f} {y+1.4:.1f} L{x-5:.1f} {y:.1f} L{x-1.4:.1f} {y-1.4:.1f} Z" fill="{mid if A else "#FFD34E"}"{S}/>')

    elif key == "vitrage":
        palette = ["#D8543C", "#F0A81E", "#2FA85A", "#3E8FD8", "#7B5CD6", "#EE5C93"]
        for i, a in enumerate(range(0, 360, 30)):
            x0, y0 = pol(55, a); x1, y1 = pol(75, a)
            x2, y2 = pol(75, a + 30); x3, y3 = pol(55, a + 30)
            col = palette[i % len(palette)]
            out.append(f'<path d="M{x0:.1f} {y0:.1f} L{x1:.1f} {y1:.1f} A75 75 0 0 1 {x2:.1f} {y2:.1f} L{x3:.1f} {y3:.1f} A55 55 0 0 0 {x0:.1f} {y0:.1f} Z" '
                       f'fill="{col}" fill-opacity="{0.85 if A else 1}" stroke="{"#FFFFFF" if A else ink}" stroke-opacity="{0.5 if A else 1}" stroke-width="{2 if A else 3}"/>')
        out.append(f'<circle cx="80" cy="80" r="75" stroke="{W if A else ink}" stroke-opacity="{0.6 if A else 1}" stroke-width="{2.6 if A else 3.4}"/>')
        out.append(f'<circle cx="80" cy="80" r="55" stroke="{W if A else ink}" stroke-opacity="{0.6 if A else 1}" stroke-width="{2.6 if A else 3.4}"/>')

    elif key == "gears":
        defs += lg(f"{uid}m", [("0", light, 1), ("0.45", mid, 1), ("1", deep, 1)], x1="0%", y1="0%", x2="100%", y2="100%")
        parts = []
        for a in range(0, 360, 12):
            x, y = pol(70, a)
            parts.append(f'<rect x="{x-4.4:.1f}" y="{y-4.4:.1f}" width="8.8" height="8.8" rx="1.8" '
                         f'fill="{f"url(#{uid}m)" if A else mid}" transform="rotate({a} {x:.1f} {y:.1f})"{S}/>')
        parts.append(f'<circle cx="80" cy="80" r="66" stroke="{f"url(#{uid}m)" if A else mid}" stroke-width="10"/>')
        if A:
            parts.append(f'<circle cx="80" cy="80" r="62.5" stroke="{W}" stroke-opacity=".4" stroke-width="1.6"/>')
            parts.append(f'<circle cx="80" cy="80" r="71" stroke="{deep}" stroke-opacity=".18" stroke-width="1.6"/>')
        else:
            parts.append(f'<circle cx="80" cy="80" r="71" stroke="{ink}" stroke-width="3"/>')
            parts.append(f'<circle cx="80" cy="80" r="61" stroke="{ink}" stroke-width="3"/>')
        for a in range(0, 360, 30):
            x, y = pol(66, a)
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.6" fill="{deep if A else ink}" fill-opacity="{0.3 if A else 1}"/>')
        out.append(f'<g class="gr-ring">{"".join(parts)}</g>')

    return defs, "\n".join(out)


def build(style):
    out = {}
    for key, ru, cat, light, mid, deep, ink in SPEC:
        d, b = decor(key, style, light, mid, deep, ink)
        out[key] = (ru, cat, svg_doc(160, 160, d, b))
    return out
