"""Десять концепций знаков лиг + награды топ-3 (рамки, значки, чемпионские аватары).

Каждая концепция — функция (key) -> SVG 128×128. Символы лиг и цифры — из
конструкции логотипа (leagues.GLYPHS / DIGITS), поэтому любая концепция
остаётся в одном семействе с вордмарком.
"""
import math
import random
from pathlib import Path

from leagues import DIGITS, GLYPHS, LEAGUES, ORDER, PLATES, gem, laurel, league_svg, placed, scaled
from logo import FLAME_CORE, FLAME_MID, FLAME_OUTER

HERE = Path(__file__).parent


def doc(body, defs="", vb="0 0 128 128"):
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}" fill="none"><defs>{defs}</defs>{body}</svg>'


def glyph(key, size, cx, cy, fill, extra=""):
    tr, d = placed(GLYPHS[key](), size, cx, cy)
    return f'<path d="{d}" fill="{fill}" fill-rule="evenodd" {tr} {extra}/>'


def mix(c1, c2, t):
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02X}" for x, y in zip(a, b))


def poly_pts(n, r, cx, cy, rot=-90):
    return [(cx + r * math.cos(math.radians(rot + i * 360 / n)), cy + r * math.sin(math.radians(rot + i * 360 / n)))
            for i in range(n)]


def pts_d(pts):
    return "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts) + " Z"


# 1. Металл и фаска — текущий вариант из leagues.py
def c_metal(key):
    return league_svg(key)


# 2. Кристаллы — огранка усложняется: 3 → 8 граней
def c_crystal(key):
    L = LEAGUES[key]; t = ORDER.index(key); n = t + 3
    rot = -90 if n % 2 else -90 + 180 / n
    outer = poly_pts(n, 58, 64, 66, rot)
    table = poly_pts(n, 27, 64, 64, rot)
    facets = []
    for i in range(n):
        a, b = outer[i], outer[(i + 1) % n]
        ta, tb = table[i], table[(i + 1) % n]
        mx, my = (a[0] + b[0]) / 2 - 64, (a[1] + b[1]) / 2 - 64
        shade = (-mx * .7 - my * .7) / 58  # свет слева сверху
        col = mix(L["deep"], L["light"], max(0, min(1, .45 + shade * .55)))
        facets.append(f'<path d="{pts_d([a, b, tb, ta])}" fill="{col}" stroke="{L["deep"]}" stroke-opacity=".35" stroke-width=".8"/>')
        facets.append(f'<path d="M{ta[0]:.1f} {ta[1]:.1f} L{(a[0] + b[0]) / 2:.1f} {(a[1] + b[1]) / 2:.1f}" stroke="#fff" stroke-opacity=".25" stroke-width=".7"/>')
    defs = (f'<radialGradient id="cr{key}" cx=".4" cy=".35" r=".7"><stop offset="0" stop-color="#fff" stop-opacity=".95"/>'
            f'<stop offset=".5" stop-color="{L["light"]}"/><stop offset="1" stop-color="{L["mid"]}"/></radialGradient>')
    sparkle = "".join(f'<path d="M{x} {y - 6} L{x + 1.4} {y - 1.4} L{x + 6} {y} L{x + 1.4} {y + 1.4} L{x} {y + 6} L{x - 1.4} {y + 1.4} L{x - 6} {y} L{x - 1.4} {y - 1.4} Z" fill="#fff"/>'
                      for x, y in [(98, 24), (28, 98), (104, 92)][: max(0, t - 2)])
    body = (f'<path d="{pts_d(outer)}" fill="{L["deep"]}" transform="translate(0 3)" opacity=".3"/>' + "".join(facets)
            + f'<path d="{pts_d(table)}" fill="url(#cr{key})" stroke="#fff" stroke-opacity=".6" stroke-width="1"/>'
            + glyph(key, 22, 64, 64, L["deep"], 'opacity=".75"') + sparkle)
    return doc(body, defs)


# 3. Созвездия — символ лиги из звёзд на ночном диске
CONST = {
    "delta": [[(50, 4), (96, 96), (4, 96), (50, 4)]],
    "gamma": [[(86, 6), (12, 6), (12, 96)]],
    "omega": [[(6, 96), (28, 96), (14, 58), (26, 22), (50, 8), (74, 22), (86, 58), (72, 96), (94, 96)]],
    "beta": [[(14, 96), (14, 4), (66, 4), (80, 26), (66, 48), (14, 48)], [(66, 48), (86, 70), (72, 96), (14, 96)]],
    "alpha": [[(8, 96), (8, 8), (92, 8), (92, 96)], [(8, 60), (92, 60)]],
    "sigma": [[(88, 6), (12, 6), (54, 50), (12, 94), (88, 94)]],
}


def c_stars(key):
    L = LEAGUES[key]; t = ORDER.index(key)
    rnd = random.Random(key)
    s, ox, oy = .52, 38, 38
    lines, stars = [], []
    for chain in CONST[key]:
        pts = [(ox + x * s, oy + y * s) for x, y in chain]
        lines.append(f'<path d="M' + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts) + f'" fill="none" stroke="{L["light"]}" stroke-opacity=".75" stroke-width="1.2"/>')
        for x, y in pts:
            stars.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" fill="{L["light"]}" opacity=".35"/><circle cx="{x:.1f}" cy="{y:.1f}" r="2.1" fill="#fff"/>')
    dust = "".join(f'<circle cx="{rnd.uniform(14, 114):.1f}" cy="{rnd.uniform(14, 114):.1f}" r="{rnd.uniform(.4, 1.1):.1f}" fill="#fff" opacity="{rnd.uniform(.3, .8):.2f}"/>'
                   for _ in range(14 + t * 8))
    defs = (f'<radialGradient id="st{key}" cx=".5" cy=".45" r=".6"><stop offset="0" stop-color="{L["mid"]}" stop-opacity=".55"/>'
            f'<stop offset=".6" stop-color="#14183A"/><stop offset="1" stop-color="#090B1E"/></radialGradient>'
            f'<clipPath id="stc{key}"><circle cx="64" cy="64" r="56"/></clipPath>')
    ring = "".join(f'<circle cx="64" cy="64" r="{58 + k * 3}" fill="none" stroke="{L["light"]}" stroke-opacity="{.5 - k * .12:.2f}" stroke-width="1.2"/>' for k in range(1 + t // 2))
    body = (f'<circle cx="64" cy="64" r="56" fill="url(#st{key})"/><g clip-path="url(#stc{key})">{dust}</g>'
            + "".join(lines) + "".join(stars) + ring)
    return doc(body, defs)


# 4. Математические тела — тетраэдр → куб → октаэдр → додекаэдр → икосаэдр → сфера-геодезия
def c_solids(key):
    L = LEAGUES[key]
    light, mid, deep = L["light"], L["mid"], L["deep"]
    sh = lambda k: mix(deep, light, k)
    if key == "delta":
        faces = [((64, 14), (22, 96), (64, 112), sh(.75)), ((64, 14), (64, 112), (106, 96), sh(.35))]
        polys = "".join(f'<path d="{pts_d(f[:3])}" fill="{f[3]}"/>' for f in faces)
    elif key == "gamma":
        polys = (f'<path d="M64 14 L106 36 L64 58 L22 36 Z" fill="{sh(.9)}"/><path d="M22 36 L64 58 V110 L22 88 Z" fill="{sh(.6)}"/>'
                 f'<path d="M106 36 L64 58 V110 L106 88 Z" fill="{sh(.3)}"/>')
    elif key == "omega":
        polys = (f'<path d="M64 10 L28 62 L64 72 Z" fill="{sh(.85)}"/><path d="M64 10 L100 62 L64 72 Z" fill="{sh(.55)}"/>'
                 f'<path d="M28 62 L64 118 L64 72 Z" fill="{sh(.45)}"/><path d="M100 62 L64 118 L64 72 Z" fill="{sh(.2)}"/>')
    elif key == "beta":
        outer = poly_pts(10, 52, 64, 64, -90)
        inner = poly_pts(5, 26, 64, 64, -90)
        polys = f'<path d="{pts_d(outer)}" fill="{sh(.35)}"/>'
        for i in range(5):
            a, b = inner[i], inner[(i + 1) % 5]
            o1, o2, o3 = outer[2 * i], outer[2 * i + 1], outer[(2 * i + 2) % 10]
            k = .45 + .4 * math.cos(math.radians(-90 + i * 72 + 36 + 135))
            polys += f'<path d="{pts_d([a, o1, o2, o3, b])}" fill="{sh(max(.15, k))}" stroke="{deep}" stroke-opacity=".3" stroke-width=".8"/>'
        polys += f'<path d="{pts_d(inner)}" fill="{sh(.9)}" stroke="{deep}" stroke-opacity=".3" stroke-width=".8"/>'
    elif key == "alpha":
        hexp = poly_pts(6, 54, 64, 64, -90)
        tri = poly_pts(3, 30, 64, 66, -90)
        polys = ""
        for i in range(6):
            a, b = hexp[i], hexp[(i + 1) % 6]
            c = tri[(i // 2) % 3] if i % 2 == 0 else tri[((i + 1) // 2) % 3]
            k = .35 + .45 * math.cos(math.radians(-90 + i * 60 + 30 + 135))
            polys += f'<path d="{pts_d([a, b, c])}" fill="{sh(max(.1, k))}" stroke="{deep}" stroke-opacity=".3" stroke-width=".8"/>'
        for i in range(3):
            a, b = tri[i], tri[(i + 1) % 3]
            o = hexp[(2 * i + 1) % 6]
            polys += f'<path d="{pts_d([a, b, o])}" fill="{sh(.55 + .1 * i)}" stroke="{deep}" stroke-opacity=".3" stroke-width=".8"/>'
        polys += f'<path d="{pts_d(tri)}" fill="{sh(.92)}" stroke="{deep}" stroke-opacity=".3" stroke-width=".8"/>'
    else:
        polys = (f'<circle cx="64" cy="64" r="52" fill="url(#so{key})"/>'
                 + "".join(f'<ellipse cx="64" cy="64" rx="52" ry="{r}" fill="none" stroke="#fff" stroke-opacity=".35" stroke-width="1"/>' for r in (14, 32, 46))
                 + "".join(f'<ellipse cx="64" cy="64" rx="{r}" ry="52" fill="none" stroke="#fff" stroke-opacity=".3" stroke-width="1"/>' for r in (14, 32, 46)))
    defs = f'<radialGradient id="so{key}" cx=".35" cy=".3" r=".75"><stop offset="0" stop-color="{light}"/><stop offset=".55" stop-color="{mid}"/><stop offset="1" stop-color="{deep}"/></radialGradient>'
    shadow = f'<ellipse cx="64" cy="118" rx="34" ry="5" fill="#000" opacity=".18"/>'
    plaque = (f'<rect x="46" y="96" width="36" height="24" rx="7" fill="#fff" stroke="{deep}" stroke-width="1.6"/>'
              + glyph(key, 15, 64, 108, deep))
    return doc(shadow + polys + plaque, defs)


# 5. Медаль на ленте
def c_medal(key):
    L = LEAGUES[key]; t = ORDER.index(key)
    defs = (f'<radialGradient id="md{key}" cx=".38" cy=".3" r=".8"><stop offset="0" stop-color="{L["light"]}"/><stop offset=".6" stop-color="{L["mid"]}"/><stop offset="1" stop-color="{L["deep"]}"/></radialGradient>'
            f'<linearGradient id="mr{key}" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{L["deep"]}"/><stop offset=".5" stop-color="{L["mid"]}"/><stop offset="1" stop-color="{L["deep"]}"/></linearGradient>'
            f'<linearGradient id="md{key}leaf" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#9BE38A"/><stop offset="1" stop-color="#2F8A3A"/></linearGradient>')
    ribbon = (f'<path d="M34 4 H58 L74 54 H50 Z" fill="url(#mr{key})"/><path d="M94 4 H70 L54 54 H78 Z" fill="url(#mr{key})"/>'
              f'<path d="M42 4 L58 54 M86 4 L70 54" stroke="#fff" stroke-opacity=".6" stroke-width="2.4"/>')
    lr = (laurel(-1, None, "#2F7A34", f"md{key}") + laurel(1, None, "#2F7A34", f"md{key}")) if t >= 4 else ""
    medal = (f'<circle cx="64" cy="78" r="38" fill="{L["deep"]}"/><circle cx="64" cy="78" r="35" fill="url(#md{key})"/>'
             f'<circle cx="64" cy="78" r="28" fill="none" stroke="#fff" stroke-opacity=".45" stroke-width="1.2" stroke-dasharray="{1.5 + t} 3"/>'
             + '<g transform="translate(0 1.8)" opacity=".55">' + glyph(key, 30, 64, 78, L["deep"]) + '</g>'
             + glyph(key, 30, 64, 78, "#fff"))
    star = '<path d="M64 6 L67 13 L74 13.6 L68.6 18 L70.4 25 L64 21 L57.6 25 L59.4 18 L54 13.6 L61 13 Z" fill="#FFD43B" stroke="#8A6206" stroke-width=".8"/>' if t == 5 else ""
    return doc(ribbon + f'<g transform="translate(0 6) scale(1) ">{lr}</g>' + medal + star, defs)


# 6. Неон
def c_neon(key):
    L = LEAGUES[key]; t = ORDER.index(key)
    plate, (cx, cy), gy, gs = PLATES[key]
    tr, d = placed(GLYPHS[key](), gs * .95, 64, gy)
    defs = (f'<filter id="ng{key}" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="2.4" result="b"/>'
            f'<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>')
    body = (f'<path d="{plate}" fill="#0C0E22"/>'
            f'<path d="{plate}" fill="none" stroke="{L["light"]}" stroke-width="2.4" filter="url(#ng{key})" {scaled(cx, cy, .92)}/>'
            + "".join(f'<path d="{plate}" fill="none" stroke="{L["mid"]}" stroke-opacity=".5" stroke-width="1" {scaled(cx, cy, .82 - k * .06)}/>' for k in range(t // 2))
            + f'<path d="{d}" fill="none" stroke="{L["light"]}" stroke-width="5" stroke-linejoin="round" filter="url(#ng{key})" {tr}/>'
            + f'<path d="{d}" fill="none" stroke="#fff" stroke-width="2" stroke-linejoin="round" {tr}/>')
    return doc(body, defs)


# 7. Гербовые щиты
SHIELD = "M64 8 C84 8 100 13 110 18 C111 64 100 100 64 120 C28 100 17 64 18 18 C28 13 44 8 64 8 Z"


def c_heraldic(key):
    L = LEAGUES[key]; t = ORDER.index(key)
    div = {
        0: "",
        1: f'<path d="M64 0 V128 H128 V0 Z" fill="{L["deep"]}" opacity=".45"/>',
        2: f'<path d="M0 128 L64 62 L128 128 Z" fill="{L["deep"]}" opacity=".45"/>',
        3: f'<path d="M64 0 V64 H128 V0 Z M0 64 H64 V128 H0 Z" fill="{L["deep"]}" opacity=".45"/>',
        4: f'<path d="M0 0 H128 V40 H0 Z" fill="{L["deep"]}" opacity=".5"/><path d="M0 40 H128" stroke="#fff" stroke-opacity=".5" stroke-width="1.5"/>',
        5: f'<path d="M0 0 L128 128 M128 0 L0 128" stroke="{L["deep"]}" stroke-opacity=".45" stroke-width="22"/>',
    }[t]
    defs = (f'<linearGradient id="hs{key}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{L["light"]}"/><stop offset="1" stop-color="{L["mid"]}"/></linearGradient>'
            f'<clipPath id="hc{key}"><path d="{SHIELD}" {scaled(64, 64, .86)}/></clipPath>'
            f'<linearGradient id="hm{key}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#FFF4C8"/><stop offset=".5" stop-color="#D9A631"/><stop offset="1" stop-color="#7A5405"/></linearGradient>')
    metal = "#hm" + key if t >= 3 else None
    rim = f'url({metal})' if metal else "#C9D3E6"
    body = (f'<path d="{SHIELD}" fill="{rim}" stroke="#3A2A08" stroke-opacity=".4"/>'
            f'<path d="{SHIELD}" fill="url(#hs{key})" {scaled(64, 64, .86)}/>'
            f'<g clip-path="url(#hc{key})">{div}</g>'
            + '<g transform="translate(0 2.2)">' + glyph(key, 40, 64, 60, "#00000055") + '</g>' + glyph(key, 40, 64, 60, "#fff"))
    if t == 5:
        body += ('<path d="M42 16 L44 2 L54 10 L64 0 L74 10 L84 2 L86 16 C76 19 52 19 42 16 Z" fill="url(#hmsigma)" stroke="#6E4F03" stroke-width="1.2"/>'
                 '<circle cx="64" cy="10" r="2.6" fill="#E64060"/>')
    return doc(body, defs)


# 8. Эмалевые значки-пины: сам символ лиги — силуэт значка
def c_pin(key):
    L = LEAGUES[key]; t = ORDER.index(key)
    metal = ["#B9824F", "#C9D3E6", "#C9D3E6", "#E3B54A", "#E3B54A", "#F2CF63"][t]
    tr, d = placed(GLYPHS[key](), 84, 64, 62)
    body = (f'<g transform="translate(0 4)"><path d="{d}" fill="#000" opacity=".22" fill-rule="evenodd" {tr}/></g>'
            f'<path d="{d}" fill="{L["mid"]}" fill-rule="evenodd" stroke="{metal}" stroke-width="9" stroke-linejoin="round" {tr}/>'
            f'<path d="{d}" fill="{L["mid"]}" fill-rule="evenodd" stroke="{mix(metal, "#000000", .35)}" stroke-width="2.6" stroke-linejoin="round" {tr}/>'
            f'<path d="{d}" fill="url(#pg{key})" fill-rule="evenodd" {tr}/>')
    defs = (f'<linearGradient id="pg{key}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".55"/>'
            f'<stop offset=".35" stop-color="#fff" stop-opacity="0"/><stop offset="1" stop-color="{L["deep"]}" stop-opacity=".35"/></linearGradient>')
    if t >= 3:
        body += gem(64, 22, 6, f"pn{key}", "#E64060" if t == 3 else "#3E86F0", "#7A1830" if t == 3 else "#123D8C")
    if t == 5:
        body += gem(64, 102, 5, "pns2", "#E64060", "#7A1830")
    return doc(body, defs)


# 9. Сакральная геометрия — розетка усложняется с лигой
def c_rosette(key):
    L = LEAGUES[key]; t = ORDER.index(key)
    n = [3, 4, 5, 6, 8, 12][t]
    lines = ""
    for k in range(n):
        ang = k * 180 / n
        lines += f'<ellipse cx="64" cy="64" rx="52" ry="{18 + t * 2}" fill="none" stroke="{L["light"]}" stroke-opacity=".75" stroke-width="1.2" transform="rotate({ang:.1f} 64 64)"/>'
    defs = f'<radialGradient id="ro{key}" cx=".5" cy=".5" r=".55"><stop offset="0" stop-color="{L["mid"]}"/><stop offset="1" stop-color="{L["deep"]}"/></radialGradient>'
    body = (f'<circle cx="64" cy="64" r="60" fill="url(#ro{key})"/><circle cx="64" cy="64" r="58" fill="none" stroke="{L["light"]}" stroke-width="1.6"/>'
            + lines + f'<circle cx="64" cy="64" r="22" fill="{L["deep"]}" stroke="{L["light"]}" stroke-width="2"/>'
            + glyph(key, 22, 64, 64, "#fff"))
    return doc(body, defs)


# 10. Пламя бренда — температура пламени растёт с лигой
TEMPS = {
    "delta": ("#7A1E0A", "#C2410C", "#F07A2A"), "gamma": ("#C2250F", "#FF6A1A", "#FFB23B"),
    "omega": ("#F05A16", "#FFA51F", "#FFE45A"), "beta": ("#FFB020", "#FFE16A", "#FFFBD8"),
    "alpha": ("#7AD7FF", "#CDEFFF", "#FFFFFF"), "sigma": ("#5B3BFF", "#7FA4FF", "#E8F0FF"),
}


def c_flame(key):
    a, b, c = TEMPS[key]
    t = ORDER.index(key)
    s = 1.05 + t * .04
    defs = (f'<linearGradient id="fa{key}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{a}"/><stop offset="1" stop-color="{b}"/></linearGradient>'
            f'<linearGradient id="fb{key}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{b}"/><stop offset="1" stop-color="{c}"/></linearGradient>'
            f'<radialGradient id="fg{key}" cx=".5" cy=".6" r=".5"><stop offset="0" stop-color="{b}" stop-opacity=".55"/><stop offset="1" stop-color="{b}" stop-opacity="0"/></radialGradient>')
    tx = 64 - 33 * s
    body = (f'<circle cx="64" cy="70" r="58" fill="url(#fg{key})"/>'
            f'<g transform="translate({tx:.1f} {116 - 90 * s:.1f}) scale({s:.2f})"><path d="{FLAME_OUTER}" fill="url(#fa{key})"/>'
            f'<path d="{FLAME_MID}" fill="url(#fb{key})"/><path d="{FLAME_CORE}" fill="{c}"/></g>'
            + '<g transform="translate(0 1.6)">' + glyph(key, 24, 64, 95, "#00000040") + '</g>' + glyph(key, 24, 64, 95, "#fff"))
    return doc(body, defs)


CONCEPTS = [
    ("Металл и фаска", "Пластины от треугольника к восьмиграннику, металл с фаской, тиснёная буква; убранство растёт от заклёпок к короне.", c_metal),
    ("Кристаллы", "Огранка усложняется с лигой: 3 грани у Дельты → 8 у Сигмы. Свет играет на гранях, буква протравлена в площадке.", c_crystal),
    ("Созвездия", "Ночное небо: буква лиги выложена звёздами. Чем выше лига, тем гуще звёздная пыль и больше орбит вокруг.", c_stars),
    ("Математические тела", "Тетраэдр → куб → октаэдр → додекаэдр → икосаэдр → сфера. Математика как ступени роста; буква — на табличке.", c_solids),
    ("Медаль на ленте", "Классическая наградная медаль: лента цвета лиги, тиснёная буква, лавр у старших лиг, звезда у Сигмы.", c_medal),
    ("Неон", "Тёмная пластина и светящийся контур — игровой, «киберспортивный» тон. Внутренние контуры добавляются с лигой.", c_neon),
    ("Гербовые щиты", "Геральдика: деление щита усложняется (рассечение, стропило, четверти, глава, андреевский крест), у Сигмы — корона.", c_heraldic),
    ("Эмалевые значки", "Сама буква — силуэт значка-пина: эмаль цвета лиги в металлической оправе; бронза → серебро → золото, камни у старших.", c_pin),
    ("Розетки", "Сакральная геометрия: розетка из эллипсов, 3 лепестка у Дельты → 12 у Сигмы. Строгий «научный» орнамент.", c_rosette),
    ("Пламя бренда", "Пламя из логотипа «разогревается» с лигой: тлеющий уголь → оранжевый огонь → белое → голубое → плазма у Сигмы.", c_flame),
]


# ── Награды топ-3 ────────────────────────────────────────────────────────────
def reward_frame(key):
    """Рамка 160×160 с отверстием Ø104 (формат рамок магазина)."""
    L = LEAGUES[key]; t = ORDER.index(key)
    defs = (f'<linearGradient id="rf{key}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{L["light"]}"/><stop offset=".5" stop-color="{L["mid"]}"/><stop offset="1" stop-color="{L["deep"]}"/></linearGradient>'
            f'<mask id="rm{key}"><rect width="160" height="160" fill="#fff"/><circle cx="80" cy="80" r="52" fill="#000"/></mask>')
    ring = (f'<g mask="url(#rm{key})"><circle cx="80" cy="80" r="74" fill="url(#rf{key})"/>'
            f'<circle cx="80" cy="80" r="70" fill="none" stroke="#fff" stroke-opacity=".5" stroke-width="1.4"/>'
            f'<circle cx="80" cy="80" r="56" fill="none" stroke="{L["deep"]}" stroke-width="3"/></g>')
    marks = ""
    for i in range(6):
        ang = math.radians(-90 + i * 60 + 30)
        x, y = 80 + 63 * math.cos(ang), 80 + 63 * math.sin(ang)
        tr, d = placed(GLYPHS[key](), 9, x, y)
        marks += f'<path d="{d}" fill="#fff" fill-rule="evenodd" {tr} opacity=".9"/>'
    gems = "".join(gem(80 + 63 * math.cos(math.radians(a)), 80 + 63 * math.sin(math.radians(a)), 4.5, f"rg{key}{a}",
                       "#E64060", "#7A1830") for a in (-90, 90)) if t >= 3 else ""
    crown = ('<path d="M60 22 L58 4 L70 12 L80 0 L90 12 L102 4 L100 22 C92 25 68 25 60 22 Z" fill="#F2CF63" stroke="#6E4F03" stroke-width="1.4"/>'
             '<circle cx="80" cy="15" r="3" fill="#E64060"/>') if t == 5 else ""
    return doc(ring + marks + gems + crown, defs, "0 0 160 160")


def owl_preview():
    p = HERE / "avatars" / "owl.svg"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def reward_badge(key, place):
    """Значок-трофей сезона: кубок цвета лиги, место — медалькой."""
    L = LEAGUES[key]
    metal = {1: ("#FFF4C8", "#F4C23A", "#A87705"), 2: ("#FFFFFF", "#C9D3E6", "#6F7C99"), 3: ("#F9DDC2", "#D2914F", "#7E4B1E")}[place]
    defs = (f'<linearGradient id="bc{key}{place}" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{metal[2]}"/><stop offset=".35" stop-color="{metal[0]}"/><stop offset="1" stop-color="{metal[1]}"/></linearGradient>'
            f'<linearGradient id="be{key}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{L["light"]}"/><stop offset="1" stop-color="{L["mid"]}"/></linearGradient>')
    cup = (f'<path d="M30 14 H98 V40 C98 66 82 82 70 85 V98 H86 C90 98 94 102 94 106 V116 H34 V106 C34 102 38 98 42 98 H58 V85 C46 82 30 66 30 40 Z" fill="url(#bc{key}{place})" stroke="{metal[2]}" stroke-width="1.4"/>'
           f'<path d="M30 22 H16 C16 40 22 50 32 54 M98 22 H112 C112 40 106 50 96 54" fill="none" stroke="url(#bc{key}{place})" stroke-width="5" stroke-linecap="round"/>'
           f'<path d="M38 20 H90 V40 C90 60 78 74 64 76 C50 74 38 60 38 40 Z" fill="url(#be{key})"/>'
           + glyph(key, 26, 64, 44, "#fff"))
    tr, d = placed(DIGITS[place], 13, 64, 108)
    num = f'<path d="{d}" fill="{metal[2]}" {tr}/>'
    return doc(cup + num, defs)


def champion_avatar(key):
    """Чемпионский аватар: буква лиги скульптурой в сфере цвета лиги, с лавром."""
    L = LEAGUES[key]
    w, d = GLYPHS[key]()
    s = .5
    tx, ty = 64 - w * s / 2, 64 - 50 * s + 2
    extrude = "".join(f'<path d="{d}" fill="{L["deep"]}" fill-rule="evenodd" transform="translate({tx + k * .5:.2f} {ty + k * .9:.2f}) scale({s})"/>' for k in range(8, 0, -1))
    defs = (f'<radialGradient id="cb{key}" cx=".4" cy=".3" r=".85"><stop offset="0" stop-color="{L["light"]}"/><stop offset=".55" stop-color="{L["mid"]}"/><stop offset="1" stop-color="{L["deep"]}"/></radialGradient>'
            f'<linearGradient id="cf{key}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#fff"/><stop offset="1" stop-color="{L["tint"]}"/></linearGradient>'
            f'<clipPath id="cc{key}"><circle cx="64" cy="64" r="60"/></clipPath>'
            f'<linearGradient id="cg{key}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".42"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>')
    rays = "".join(f'<path d="M64 64 L{64 + 90 * math.cos(math.radians(a)):.1f} {64 + 90 * math.sin(math.radians(a)):.1f} L{64 + 90 * math.cos(math.radians(a + 8)):.1f} {64 + 90 * math.sin(math.radians(a + 8)):.1f} Z" fill="#fff" opacity=".07"/>' for a in range(0, 360, 24))
    body = (f'<circle cx="64" cy="64" r="60" fill="url(#cb{key})"/><g clip-path="url(#cc{key})">{rays}</g>'
            + laurel(-1, None, "#2F7A34", f"ca{key}").replace("66 +", "66 +") + laurel(1, None, "#2F7A34", f"ca{key}")
            + extrude + f'<path d="{d}" fill="url(#cf{key})" fill-rule="evenodd" transform="translate({tx:.2f} {ty:.2f}) scale({s})"/>'
            + f'<path d="M22 46 C30 22 52 10 74 12 C58 18 40 30 30 50 Z" fill="url(#cg{key})"/>'
            + f'<circle cx="64" cy="64" r="59.2" fill="none" stroke="#fff" stroke-opacity=".55" stroke-width="1.6"/>')
    return doc(body, defs + '<linearGradient id="caleaf" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#9BE38A"/><stop offset="1" stop-color="#2F8A3A"/></linearGradient>'
               .replace("caleaf", f"ca{key}leaf"))
