"""Рамки магазина: общий объёмный обод и мотив поверх него.

Рамка — кольцо 160×160 с отверстием Ø104 под аватар. Обод у всех рамок один
и тот же по построению (градиент по диагонали, блик сверху слева, тень
изнутри): так плоские линейные рамки встают в один ряд с объёмными аватарами
и розетками лиг. Цвета обода — свои у каждой рамки.

Шесть рамок нарисованы заново (saturn, comet, integral, coordinates,
tessellation, aurora). Остальные восемь берутся из legacy/ — это рисунки
прежнего генератора — и получают обод. legacy/ читается, а не design/svg:
иначе каждая сборка добавляла бы ещё один обод.

Движутся только рамки уровня «анимированный» (saturn, comet, aurora, gears,
bitflow, nebula); их классы совпадают с static/css/cosmetics.css. Элементу
с CSS-анимацией transform не ставим атрибут transform: CSS его перезапишет,
поэтому сдвиг и поворот живут на обёртке.
"""
import math
from pathlib import Path

LEGACY = Path(__file__).resolve().parent / "legacy"
R_IN = 55.5  # внутренний край обода — чуть шире края аватара (r = 52)


def doc(body, defs=""):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 160" fill="none">'
            f'<defs>{defs}</defs>{body}</svg>')


def pt(r, deg):
    a = math.radians(deg)
    return 80 + r * math.cos(a), 80 + r * math.sin(a)


def arc(r, a0, a1):
    (x0, y0), (x1, y1) = pt(r, a0), pt(r, a1)
    large = 1 if (a1 - a0) % 360 > 180 else 0
    return f"M{x0:.2f} {y0:.2f} A{r} {r} 0 {large} 1 {x1:.2f} {y1:.2f}"


def bezel(u, light, mid, deep, width=6):
    """Объёмный обод: возвращает (defs, разметка)."""
    r = R_IN + width / 2
    defs = (f'<linearGradient id="{u}bz" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{light}"/>'
            f'<stop offset=".5" stop-color="{mid}"/><stop offset="1" stop-color="{deep}"/></linearGradient>')
    body = (f'<circle cx="80" cy="80" r="{r}" stroke="url(#{u}bz)" stroke-width="{width}"/>'
            f'<circle cx="80" cy="80" r="{R_IN + .4}" stroke="#000" stroke-opacity=".28" stroke-width=".9"/>'
            f'<path d="{arc(r + width / 2 - 1.2, 200, 290)}" stroke="#fff" stroke-opacity=".7" stroke-width="1.3" stroke-linecap="round"/>')
    return defs, body


# — Нарисованные заново —

def saturn():
    """Кольцо уходит за аватар: внутри диска его не видно, поэтому оно не
    перечёркивает лицо. По пунктирной орбите ходит спутник."""
    u = "fsa"
    bd, bb = bezel(u, "#E9DDFF", "#8C6CF0", "#4B32A8")
    defs = bd + (f'<linearGradient id="{u}r" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#5B3FD0"/>'
                 f'<stop offset=".3" stop-color="#C9B6FF"/><stop offset=".5" stop-color="#F3EDFF"/><stop offset=".7" stop-color="#B49CFF"/>'
                 f'<stop offset="1" stop-color="#5B3FD0"/></linearGradient>'
                 f'<mask id="{u}m"><rect width="160" height="160" fill="#fff"/><circle cx="80" cy="80" r="{R_IN + 6}" fill="#000"/></mask>'
                 f'<radialGradient id="{u}moon" cx=".35" cy=".3" r=".8"><stop offset="0" stop-color="#FFF6D8"/><stop offset="1" stop-color="#E0A93A"/></radialGradient>')
    ring = (f'<g mask="url(#{u}m)"><g transform="rotate(-18 80 80)">'
            f'<ellipse cx="80" cy="80" rx="77" ry="21" stroke="url(#{u}r)" stroke-width="7"/>'
            f'<ellipse cx="80" cy="80" rx="77" ry="21" stroke="#2A1C6E" stroke-opacity=".35" stroke-width="1"/>'
            f'<ellipse class="sa-glint" cx="80" cy="80" rx="69" ry="16" stroke="#C9B6FF" stroke-opacity=".7" stroke-width="1.6"/></g></g>')
    mx, my = pt(70, -60)
    moon = (f'<circle class="sa-track" cx="80" cy="80" r="70" stroke="#8C6CF0" stroke-opacity=".3" stroke-width=".8" stroke-dasharray="1.5 4"/>'
            f'<g class="sa-moon"><circle cx="{mx:.1f}" cy="{my:.1f}" r="5.5" fill="url(#{u}moon)"/>'
            f'<circle cx="{mx - 1.6:.1f}" cy="{my - 1.8:.1f}" r="1.6" fill="#fff" fill-opacity=".8"/></g>')
    return doc(moon + bb + ring, defs)


def comet():
    """Полная орбита и комета с хвостом в треть круга; хвост и белая струя
    в нём гаснут от головы к концу. Вращается вся группа."""
    u = "fco"
    bd, bb = bezel(u, "#FFF0C2", "#F2B33D", "#B8701A")
    (tx0, ty0), (tx1, ty1) = pt(68, 150), pt(68, 270)
    (wx0, wy0), (wx1, wy1) = pt(68, 190), pt(68, 268)
    defs = bd + (f'<linearGradient id="{u}t" gradientUnits="userSpaceOnUse" x1="{tx0:.1f}" y1="{ty0:.1f}" x2="{tx1:.1f}" y2="{ty1:.1f}">'
                 f'<stop offset="0" stop-color="#FFB547" stop-opacity="0"/><stop offset="1" stop-color="#FFE7A3"/></linearGradient>'
                 f'<linearGradient id="{u}w" gradientUnits="userSpaceOnUse" x1="{wx0:.1f}" y1="{wy0:.1f}" x2="{wx1:.1f}" y2="{wy1:.1f}">'
                 f'<stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".6" stop-color="#fff" stop-opacity=".45"/>'
                 f'<stop offset="1" stop-color="#fff" stop-opacity=".95"/></linearGradient>'
                 f'<radialGradient id="{u}h" cx=".4" cy=".35" r=".7"><stop offset="0" stop-color="#fff"/><stop offset=".5" stop-color="#FFE7A3"/><stop offset="1" stop-color="#F29A1F"/></radialGradient>')
    track = '<circle cx="80" cy="80" r="68" stroke="#F2B33D" stroke-opacity=".28" stroke-width="1" stroke-dasharray="2 5"/>'
    stars = "".join(f'<circle class="co-star" style="--i:{k}" cx="{pt(r, a)[0]:.1f}" cy="{pt(r, a)[1]:.1f}" r="{s}" fill="#FFE7A3"/>'
                    for k, (r, a, s) in enumerate(((74, 20, 1.4), (73, 60, 1), (75, 110, 1.6), (72, 330, 1.1), (74, 300, 1))))
    hx, hy = pt(68, 270)
    head = (f'<g class="co-orbit"><path d="{arc(68, 150, 270)}" stroke="url(#{u}t)" stroke-width="9" stroke-linecap="round"/>'
            f'<path d="{arc(68, 190, 268)}" stroke="url(#{u}w)" stroke-width="2" stroke-linecap="round"/>'
            f'<circle class="co-halo" cx="{hx:.1f}" cy="{hy:.1f}" r="11" fill="#FFD36B" fill-opacity=".3"/>'
            f'<circle cx="{hx:.1f}" cy="{hy:.1f}" r="7.5" fill="url(#{u}h)"/></g>')
    return doc(track + stars + bb + head, defs)


def integral():
    """Сумма Римана: столбики по кругу, высота идёт по волне — площадь под
    кривой, из которой вырастает интеграл."""
    u = "fig"
    bd, bb = bezel(u, "#C6F5E6", "#22B08C", "#0D6B57")
    n = 36
    bars = []
    for k in range(n):
        a0 = k * 360 / n - 90
        a1 = a0 + 360 / n - 2.2
        h = 5 + 6 * (0.5 + 0.5 * math.cos(math.radians(k * 360 / n * 6)))
        r0, r1 = R_IN + 6.5, R_IN + 6.5 + h
        (x0, y0), (x1, y1), (x2, y2), (x3, y3) = pt(r0, a0), pt(r1, a0), pt(r1, a1), pt(r0, a1)
        fill = "#22B08C" if k % 2 else "#4FD2AE"
        bars.append(f'<path d="M{x0:.1f} {y0:.1f} L{x1:.1f} {y1:.1f} '
                    f'A{r1:.1f} {r1:.1f} 0 0 1 {x2:.1f} {y2:.1f} L{x3:.1f} {y3:.1f} Z" fill="{fill}"/>')
    curve = []
    for k in range(0, 361, 4):
        r = R_IN + 6.5 + 5 + 6 * (0.5 + 0.5 * math.cos(math.radians((k + 5) * 6)))
        x, y = pt(r, k - 90)
        curve.append(f"{'M' if k == 0 else 'L'}{x:.1f} {y:.1f}")
    body = ("".join(bars)
            + f'<path d="{" ".join(curve)}Z" stroke="#0D6B57" stroke-width="1.3" stroke-linejoin="round"/>' + bb)
    return doc(body, bd)


def coordinates():
    """Транспортир: деления через 5°, оси со стрелками и точка на шкале."""
    u = "fcd"
    bd, bb = bezel(u, "#DDE4FF", "#5B73F0", "#2C3FA8", width=5)
    ticks = []
    for k in range(72):
        a = k * 5
        major, mid = a % 90 == 0, a % 15 == 0
        r1 = R_IN + 5 + (13 if major else 8 if mid else 4.5)
        (x0, y0), (x1, y1) = pt(R_IN + 5.5, a), pt(r1, a)
        ticks.append(f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" stroke="#4F6BEA" '
                     f'stroke-width="{2.2 if major else 1.3 if mid else .8}" stroke-opacity="{1 if mid else .55}"/>')
    band = f'<circle cx="80" cy="80" r="{R_IN + 13}" stroke="#4F6BEA" stroke-opacity=".12" stroke-width="15"/>'
    heads = "".join(
        f'<path d="M{pt(77, a)[0]:.1f} {pt(77, a)[1]:.1f} L{pt(70, a - 4)[0]:.1f} {pt(70, a - 4)[1]:.1f} '
        f'L{pt(70, a + 4)[0]:.1f} {pt(70, a + 4)[1]:.1f} Z" fill="#2C3FA8"/>' for a in (0, 90, 180, 270))
    px, py = pt(70, -45)
    point = (f'<g><circle cx="{px:.1f}" cy="{py:.1f}" r="6" fill="#FF7A59" fill-opacity=".25"/>'
             f'<circle cx="{px:.1f}" cy="{py:.1f}" r="3.6" fill="#FF7A59" stroke="#fff" stroke-width="1.2"/></g>')
    return doc(band + "".join(ticks) + heads + bb + point, bd)


def tessellation():
    """Замощение треугольниками в два тона — паркет Эшера по кругу."""
    u = "fts"
    bd, bb = bezel(u, "#D7ECFF", "#3E8FE0", "#1C4E9A")
    n, r0, r1 = 24, R_IN + 6, 76
    tri = []
    for k in range(n):
        a0 = k * 360 / n
        a1, am = a0 + 360 / n, a0 + 180 / n
        p = [pt(r0, a0), pt(r1, am), pt(r0, a1)]
        q = [pt(r1, am), pt(r0, a1), pt(r1, am + 360 / n)]
        tri.append(f'<path d="M{p[0][0]:.1f} {p[0][1]:.1f} L{p[1][0]:.1f} {p[1][1]:.1f} L{p[2][0]:.1f} {p[2][1]:.1f} Z" '
                   f'fill="{"#3E8FE0" if k % 2 else "#6FB2F2"}"/>')
        tri.append(f'<path d="M{q[0][0]:.1f} {q[0][1]:.1f} L{q[1][0]:.1f} {q[1][1]:.1f} '
                   f'L{q[2][0]:.1f} {q[2][1]:.1f} Z" fill="{"#BFE0FF" if k % 2 else "#9ACBF8"}"/>')
    edge = (f'<circle cx="80" cy="80" r="{r1}" stroke="#1C4E9A" stroke-width="1.6"/>'
            f'<circle cx="80" cy="80" r="{r1 - .9}" stroke="#fff" stroke-opacity=".5" stroke-width=".8"/>')
    return doc("".join(tri) + edge + bb, bd)


def aurora():
    """Три ленты сияния с волной; вращаются с разной скоростью навстречу."""
    u = "fau"
    bd, bb = bezel(u, "#D9FFF3", "#38C9A4", "#5B47D6")
    defs = bd + (f'<linearGradient id="{u}g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#6DF2C8"/>'
                 f'<stop offset=".45" stop-color="#47B8F0"/><stop offset="1" stop-color="#9A6CF2"/></linearGradient>'
                 f'<filter id="{u}f" x="-.2" y="-.2" width="1.4" height="1.4"><feGaussianBlur stdDeviation="2.4"/></filter>')
    waves = []
    for i, (w, op, ph) in enumerate(((13, .5, 0), (5, .85, 120), (2.2, .95, 240))):
        pts = []
        for k in range(0, 361, 6):
            x, y = pt(R_IN + 12 + 2.6 * math.sin(math.radians(k * 5 + ph)), k)
            pts.append(f"{'M' if k == 0 else 'L'}{x:.1f} {y:.1f}")
        stroke = f'stroke="url(#{u}g)" stroke-width="{w}" stroke-opacity="{op}" stroke-linejoin="round"'
        path = f'<path d="{" ".join(pts)}Z" {stroke}/>'
        waves.append(f'<g class="au-wave" style="--i:{i}">'
                     + (f'<g filter="url(#{u}f)">{path}</g>' if i == 0 else path) + '</g>')
    return doc("".join(waves) + bb, defs)


# — Прежние рисунки с ободом —

def _legacy(code):
    return (LEGACY / f"{code}.svg").read_text(encoding="utf-8")


def _with_bezel(markup, u, colors, under=False):
    """Добавить обод поверх рисунка (или под ним, если мотив должен лежать сверху)."""
    bd, bb = bezel(u, *colors)
    markup = markup.replace("<defs>", f"<defs>{bd}", 1)
    if under:
        return markup.replace("</defs>", "</defs>" + bb, 1)
    return markup.replace("</svg>", bb + "</svg>")


def bitflow():
    return _with_bezel(_legacy("bitflow"), "fbt", ("#D8F1FF", "#3BA4D9", "#1D5E8C"))


def pcb():
    return _with_bezel(_legacy("pcb"), "fpc", ("#D5F7E4", "#2BAE6E", "#136B43"))


def bloom():
    return _with_bezel(_legacy("bloom"), "fbl", ("#FFE0EC", "#EC6A9A", "#A8325E"))


def ivy():
    """Лоза лежит поверх обода, как настоящая."""
    return _with_bezel(_legacy("ivy"), "fiv", ("#DDF5D0", "#4FAF5A", "#2A6E33"), under=True)


def flame():
    return _with_bezel(_legacy("flame"), "ffl", ("#FFE2A6", "#F5751E", "#8A2E05"))


def nebula():
    return _with_bezel(_legacy("nebula"), "fnb", ("#F1DDFF", "#9A3FD8", "#4A0E76"))


def gears():
    return _with_bezel(_legacy("gears"), "fgr", ("#F2D6A8", "#C08A3E", "#6B4412"))


def vitrage():
    return _with_bezel(_legacy("vitrage"), "fvt", ("#FFFFFF", "#B9C3DA", "#6C7790"))


FRAMES = {
    "saturn": saturn, "comet": comet, "integral": integral, "coordinates": coordinates,
    "tessellation": tessellation, "aurora": aurora,
    "bitflow": bitflow, "pcb": pcb, "bloom": bloom, "ivy": ivy,
    "flame": flame, "nebula": nebula, "gears": gears, "vitrage": vitrage,
}
