"""Чистовые розетки лиг, созвездия-аватары чемпионов, варианты рамок и трофеев."""
import math
import random
from pathlib import Path

from avatars import frame as avatar_frame
from concepts import CONST, doc, glyph, mix, poly_pts
from leagues import DIGITS, LEAGUES, ORDER, gem, laurel, placed
from logo import FLAME_CORE, FLAME_MID, FLAME_OUTER

HERE = Path(__file__).parent
MEDAL = {1: ("#FFF4C8", "#F4C23A", "#A87705"), 2: ("#FFFFFF", "#C9D3E6", "#6F7C99"), 3: ("#F9DDC2", "#D2914F", "#7E4B1E")}


def place_token(place, uid, cx=101, cy=101, r=19):
    a, b, c = MEDAL[place]
    tr, d = placed(DIGITS[place], r * .8, cx, cy)
    return (f'<defs><radialGradient id="{uid}pt" cx=".35" cy=".3" r=".9"><stop offset="0" stop-color="{a}"/><stop offset=".6" stop-color="{b}"/><stop offset="1" stop-color="{c}"/></radialGradient></defs>'
            f'<circle cx="{cx}" cy="{cy + 2}" r="{r}" fill="#000" opacity=".2"/><circle cx="{cx}" cy="{cy}" r="{r}" fill="url(#{uid}pt)" stroke="{c}" stroke-width="1.2"/>'
            f'<circle cx="{cx}" cy="{cy}" r="{r * .76:.1f}" fill="none" stroke="#fff" stroke-opacity=".6" stroke-width="1"/>'
            f'<g transform="translate(0 1.4)"><path d="{d}" fill="{c}" {tr}/></g><path d="{d}" fill="#fff" {tr}/>')


# ── 1. Розетки — чистовик ─────────────────────────────────────────────────────
def rosette(key, place=None):
    L = LEAGUES[key]; t = ORDER.index(key)
    n = [3, 4, 5, 6, 8, 12][t]
    u = f"ro{key}{place or 0}"
    defs = (f'<linearGradient id="{u}rim" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{L["light"]}"/><stop offset=".45" stop-color="{L["mid"]}"/><stop offset="1" stop-color="{L["deep"]}"/></linearGradient>'
            f'<radialGradient id="{u}face" cx=".5" cy=".42" r=".62"><stop offset="0" stop-color="{mix(L["mid"], L["light"], .35)}"/><stop offset=".7" stop-color="{L["mid"]}"/><stop offset="1" stop-color="{L["deep"]}"/></radialGradient>'
            f'<radialGradient id="{u}med" cx=".38" cy=".32" r=".8"><stop offset="0" stop-color="{L["tint"]}"/><stop offset=".6" stop-color="{L["light"]}"/><stop offset="1" stop-color="{L["mid"]}"/></radialGradient>'
            f'<linearGradient id="{u}shine" x1="0" y1="0" x2=".7" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".5"/><stop offset=".5" stop-color="#fff" stop-opacity="0"/></linearGradient>'
            f'<clipPath id="{u}clip"><circle cx="64" cy="64" r="51"/></clipPath>')
    petals = "".join(f'<ellipse cx="64" cy="64" rx="50" ry="{17 + t * 2}" fill="none" stroke="{L["tint"]}" stroke-opacity=".85" stroke-width="1.3" transform="rotate({k * 180 / n:.2f} 64 64)"/>' for k in range(n))
    guill = "".join(f'<ellipse cx="64" cy="64" rx="48" ry="{9 + t}" fill="none" stroke="{L["tint"]}" stroke-opacity=".28" stroke-width=".7" transform="rotate({k * 180 / n + 90 / n:.2f} 64 64)"/>' for k in range(n))
    notches = "".join(f'<circle cx="{64 + 56.5 * math.cos(math.radians(-90 + k * 360 / n)):.1f}" cy="{64 + 56.5 * math.sin(math.radians(-90 + k * 360 / n)):.1f}" r="1.7" fill="{L["tint"]}"/>' for k in range(n))
    body = (f'<circle cx="64" cy="66.5" r="61" fill="#000" opacity=".18"/>'
            f'<circle cx="64" cy="64" r="61" fill="url(#{u}rim)"/><circle cx="64" cy="64" r="58.5" fill="none" stroke="#fff" stroke-opacity=".55" stroke-width="1.2"/>'
            + notches
            + f'<circle cx="64" cy="64" r="53" fill="{L["deep"]}"/><circle cx="64" cy="64" r="51" fill="url(#{u}face)"/>'
            + f'<g clip-path="url(#{u}clip)">{guill}{petals}<path d="M0 0 H128 L0 100 Z" fill="url(#{u}shine)"/></g>'
            + f'<circle cx="64" cy="64" r="28" fill="url(#{u}rim)"/><circle cx="64" cy="64" r="24.5" fill="url(#{u}med)"/>'
            + '<g transform="translate(0 1.6)">' + glyph(key, 24, 64, 64, L["deep"]) + '</g>' + glyph(key, 24, 64, 64, "#fff"))
    if place:
        body += place_token(place, u)
    return doc(body, defs)


# ── 2. Созвездия — чемпионские аватары ─────────────────────────────────────────
def constellation_avatar(key):
    L = LEAGUES[key]; t = ORDER.index(key)
    u = f"ca{key}"
    rnd = random.Random("ca" + key)
    s, ox, oy = .6, 34, 32
    lines, stars = [], []
    for chain in CONST[key]:
        pts = [(ox + x * s, oy + y * s) for x, y in chain]
        lines.append('<path d="M' + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts) + f'" fill="none" stroke="{L["tint"]}" stroke-opacity=".8" stroke-width="1.3" stroke-linejoin="round"/>')
        for i, (x, y) in enumerate(pts):
            big = 2.6 if i % 2 == 0 else 1.9
            stars.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{big * 3:.1f}" fill="url(#{u}halo)"/><circle cx="{x:.1f}" cy="{y:.1f}" r="{big:.1f}" fill="#fff"/>')
    dust = "".join(f'<circle cx="{rnd.uniform(6, 122):.1f}" cy="{rnd.uniform(6, 122):.1f}" r="{rnd.uniform(.35, 1.1):.2f}" fill="#fff" opacity="{rnd.uniform(.25, .85):.2f}"/>' for _ in range(60))
    bg = (f'<radialGradient id="{u}bg" cx=".5" cy=".45" r=".7"><stop offset="0" stop-color="{L["mid"]}"/><stop offset=".45" stop-color="{mix(L["deep"], "#0B0E2A", .45)}"/><stop offset="1" stop-color="#070918"/></radialGradient>'
          f'<radialGradient id="{u}neb" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="{L["light"]}" stop-opacity=".45"/><stop offset="1" stop-color="{L["light"]}" stop-opacity="0"/></radialGradient>'
          f'<radialGradient id="{u}halo" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="{L["tint"]}" stop-opacity=".85"/><stop offset="1" stop-color="{L["tint"]}" stop-opacity="0"/></radialGradient>')
    body = (dust + f'<ellipse cx="44" cy="40" rx="38" ry="22" fill="url(#{u}neb)" transform="rotate(-25 44 40)"/>'
            f'<ellipse cx="92" cy="94" rx="30" ry="18" fill="url(#{u}neb)" transform="rotate(20 92 94)" opacity=".7"/>'
            + "".join(lines) + "".join(stars)
            + f'<path d="M64 104 L66.5 110 L73 110.5 L68 114.6 L69.6 121 L64 117.6 L58.4 121 L60 114.6 L55 110.5 L61.5 110 Z" fill="#FFD43B" opacity="{.4 + t * .1:.1f}"/>')
    return avatar_frame(u, bg, body)


# ── 3. Рамки: шесть вариантов (160×160, окно Ø104) ─────────────────────────────
def _ring_defs(u, L):
    return (f'<linearGradient id="{u}g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{L["light"]}"/><stop offset=".5" stop-color="{L["mid"]}"/><stop offset="1" stop-color="{L["deep"]}"/></linearGradient>'
            f'<mask id="{u}m"><rect width="160" height="160" fill="#fff"/><circle cx="80" cy="80" r="52" fill="#000"/></mask>')


def frame_letters(key):
    L = LEAGUES[key]; u = f"fl{key}"
    marks = ""
    for i in range(6):
        a = math.radians(-90 + i * 60 + 30)
        tr, d = placed(__import__("leagues").GLYPHS[key](), 9, 80 + 63 * math.cos(a), 80 + 63 * math.sin(a))
        marks += f'<path d="{d}" fill="#fff" fill-rule="evenodd" {tr}/>'
    return doc(f'<g mask="url(#{u}m)"><circle cx="80" cy="80" r="74" fill="url(#{u}g)"/><circle cx="80" cy="80" r="70" fill="none" stroke="#fff" stroke-opacity=".5" stroke-width="1.4"/><circle cx="80" cy="80" r="56" fill="none" stroke="{L["deep"]}" stroke-width="3"/></g>{marks}',
               _ring_defs(u, L), "0 0 160 160")


def frame_laurel(key):
    L = LEAGUES[key]; u = f"fw{key}"
    leaves = ""
    for side in (-1, 1):
        for i in range(11):
            t = i / 10
            ang = math.radians(90 + side * (12 + 150 * t))
            x, y = 80 + 64 * math.cos(ang), 80 + 64 * math.sin(ang)
            rot = math.degrees(ang) + 90 + side * 35
            leaves += f'<ellipse cx="{x:.1f}" cy="{y:.1f}" rx="5" ry="11" transform="rotate({rot:.1f} {x:.1f} {y:.1f})" fill="url(#{u}g)" stroke="{L["deep"]}" stroke-opacity=".5" stroke-width=".8"/>'
    tr, d = placed(__import__("leagues").GLYPHS[key](), 11, 80, 146)
    ribbon = (f'<path d="M56 140 L50 154 L58 151 L62 158 L66 146 Z M104 140 L110 154 L102 151 L98 158 L94 146 Z" fill="{L["deep"]}"/>'
              f'<rect x="60" y="136" width="40" height="20" rx="5" fill="url(#{u}g)" stroke="{L["deep"]}" stroke-width="1.2"/><path d="{d}" fill="#fff" fill-rule="evenodd" {tr}/>')
    return doc(leaves + ribbon, _ring_defs(u, L), "0 0 160 160")


def frame_orbits(key):
    L = LEAGUES[key]; u = f"fo{key}"
    body = (f'<g fill="none" stroke="{L["light"]}" stroke-width="2.2"><ellipse cx="80" cy="80" rx="74" ry="36" transform="rotate(-28 80 80)"/>'
            f'<ellipse cx="80" cy="80" rx="74" ry="36" transform="rotate(28 80 80)" stroke="{L["mid"]}"/></g>'
            f'<circle cx="80" cy="80" r="56" fill="none" stroke="{L["light"]}" stroke-opacity=".6" stroke-width="1.4" stroke-dasharray="2 4"/>'
            f'<circle cx="20" cy="54" r="7" fill="url(#{u}g)"/><circle cx="140" cy="106" r="5" fill="url(#{u}g)"/><circle cx="128" cy="34" r="3.5" fill="#fff"/>'
            '<path d="M38 128 L40 133 L45 135 L40 137 L38 142 L36 137 L31 135 L36 133 Z" fill="#fff"/>')
    return doc(f'<g mask="url(#{u}m)">{body}</g>', _ring_defs(u, L), "0 0 160 160")


def frame_rosette(key):
    L = LEAGUES[key]; t = ORDER.index(key); u = f"fr{key}"
    n = [3, 4, 5, 6, 8, 12][t] * 2
    petals = "".join(f'<ellipse cx="80" cy="80" rx="74" ry="40" fill="none" stroke="{L["tint"]}" stroke-opacity=".8" stroke-width="1.1" transform="rotate({k * 180 / n:.1f} 80 80)"/>' for k in range(n))
    body = (f'<circle cx="80" cy="80" r="75" fill="url(#{u}g)"/>{petals}<circle cx="80" cy="80" r="74" fill="none" stroke="#fff" stroke-opacity=".6" stroke-width="1.4"/>'
            f'<circle cx="80" cy="80" r="55" fill="none" stroke="{L["deep"]}" stroke-width="3"/>')
    return doc(f'<g mask="url(#{u}m)">{body}</g>', _ring_defs(u, L), "0 0 160 160")


def frame_flames(key):
    L = LEAGUES[key]; u = f"ff{key}"
    fl = ""
    for i in range(10):
        a = -90 + i * 36
        fl += (f'<g transform="rotate({a + 90} 80 80) translate(68 0) scale(.36)"><path d="{FLAME_OUTER}" fill="url(#{u}f1)"/>'
               f'<path d="{FLAME_MID}" fill="url(#{u}f2)"/></g>')
    defs = (_ring_defs(u, L) + f'<linearGradient id="{u}f1" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{L["deep"]}"/><stop offset="1" stop-color="{L["mid"]}"/></linearGradient>'
            f'<linearGradient id="{u}f2" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{L["light"]}"/><stop offset="1" stop-color="#FFF6D8"/></linearGradient>')
    return doc(f'<g mask="url(#{u}m)">{fl}<circle cx="80" cy="80" r="56" fill="none" stroke="url(#{u}g)" stroke-width="5"/></g>', defs, "0 0 160 160")


def frame_rays(key):
    L = LEAGUES[key]; u = f"fy{key}"
    rays = "".join(f'<path d="M80 80 L{80 + 78 * math.cos(math.radians(a - 4)):.1f} {80 + 78 * math.sin(math.radians(a - 4)):.1f} L{80 + 78 * math.cos(math.radians(a + 4)):.1f} {80 + 78 * math.sin(math.radians(a + 4)):.1f} Z" fill="url(#{u}g)"/>'
                   for a in range(0, 360, 15))
    short = "".join(f'<path d="M80 80 L{80 + 66 * math.cos(math.radians(a - 3)):.1f} {80 + 66 * math.sin(math.radians(a - 3)):.1f} L{80 + 66 * math.cos(math.radians(a + 3)):.1f} {80 + 66 * math.sin(math.radians(a + 3)):.1f} Z" fill="{L["tint"]}"/>'
                    for a in range(7, 360, 15))
    return doc(f'<g mask="url(#{u}m)">{rays}{short}<circle cx="80" cy="80" r="56" fill="none" stroke="{L["deep"]}" stroke-width="3"/></g>', _ring_defs(u, L), "0 0 160 160")


FRAMES = [("Буквы по кругу", frame_letters), ("Лавровый венок", frame_laurel), ("Орбиты", frame_orbits),
          ("Розетка", frame_rosette), ("Пламя", frame_flames), ("Лучи", frame_rays)]


# ── 4. Трофеи: пять вариантов ─────────────────────────────────────────────────
def trophy_cup(key, place):
    from concepts import reward_badge
    return reward_badge(key, place)


def trophy_star(key, place):
    L = LEAGUES[key]; a, b, c = MEDAL[place]; u = f"ts{key}{place}"
    star = "M" + " L".join(f"{64 + (50 if i % 2 == 0 else 24) * math.cos(math.radians(-90 + i * 36)):.1f} {58 + (50 if i % 2 == 0 else 24) * math.sin(math.radians(-90 + i * 36)):.1f}" for i in range(10)) + " Z"
    defs = (f'<linearGradient id="{u}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{a}"/><stop offset=".5" stop-color="{b}"/><stop offset="1" stop-color="{c}"/></linearGradient>'
            f'<radialGradient id="{u}c" cx=".4" cy=".35" r=".7"><stop offset="0" stop-color="{L["light"]}"/><stop offset="1" stop-color="{L["mid"]}"/></radialGradient>')
    body = (f'<path d="M44 92 L34 124 L48 118 L56 128 L62 98 Z M84 92 L94 124 L80 118 L72 128 L66 98 Z" fill="{L["deep"]}"/>'
            f'<path d="{star}" fill="url(#{u})" stroke="{c}" stroke-width="1.4" stroke-linejoin="round"/>'
            f'<circle cx="64" cy="58" r="20" fill="url(#{u}c)" stroke="{c}" stroke-width="1.2"/>' + glyph(key, 17, 64, 58, "#fff"))
    tr, d = placed(DIGITS[place], 10, 64, 112)
    return doc(body + f'<circle cx="64" cy="112" r="9" fill="url(#{u})" stroke="{c}"/><path d="{d}" fill="#fff" {tr}/>', defs)


def trophy_pennant(key, place):
    L = LEAGUES[key]; a, b, c = MEDAL[place]; u = f"tp{key}{place}"
    defs = (f'<linearGradient id="{u}" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{L["deep"]}"/><stop offset=".5" stop-color="{L["mid"]}"/><stop offset="1" stop-color="{L["deep"]}"/></linearGradient>'
            f'<linearGradient id="{u}m" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{a}"/><stop offset="1" stop-color="{c}"/></linearGradient>')
    tr, d = placed(DIGITS[place], 16, 64, 92)
    body = (f'<rect x="22" y="10" width="84" height="7" rx="3.5" fill="url(#{u}m)"/><circle cx="22" cy="13.5" r="5" fill="url(#{u}m)"/><circle cx="106" cy="13.5" r="5" fill="url(#{u}m)"/>'
            f'<path d="M28 17 H100 V100 L64 122 L28 100 Z" fill="url(#{u})"/>'
            f'<path d="M34 17 V96 L64 114 L94 96 V17" fill="none" stroke="url(#{u}m)" stroke-width="2.4"/>'
            + glyph(key, 30, 64, 50, "#fff")
            + f'<path d="{d}" fill="url(#{u}m)" {tr}/>')
    return doc(body, defs)


def trophy_prize_rosette(key, place):
    L = LEAGUES[key]; a, b, c = MEDAL[place]; u = f"tr{key}{place}"
    pleats = "".join(f'<path d="M64 52 L{64 + 44 * math.cos(math.radians(k)):.1f} {52 + 44 * math.sin(math.radians(k)):.1f} L{64 + 44 * math.cos(math.radians(k + 10)):.1f} {52 + 44 * math.sin(math.radians(k + 10)):.1f} Z" fill="{L["mid"] if (k // 10) % 2 else L["light"]}"/>' for k in range(0, 360, 10))
    defs = f'<radialGradient id="{u}" cx=".4" cy=".35" r=".7"><stop offset="0" stop-color="{a}"/><stop offset=".6" stop-color="{b}"/><stop offset="1" stop-color="{c}"/></radialGradient>'
    body = (f'<path d="M48 80 L36 126 L50 120 L58 128 L64 86 Z M80 80 L92 126 L78 120 L70 128 L64 86 Z" fill="{L["deep"]}"/>'
            + pleats + f'<circle cx="64" cy="52" r="44" fill="none" stroke="{L["deep"]}" stroke-opacity=".4" stroke-width="1"/>'
            + f'<circle cx="64" cy="52" r="24" fill="url(#{u})" stroke="{c}" stroke-width="1.4"/>'
            + glyph(key, 18, 64, 52, "#fff"))
    tr, d = placed(DIGITS[place], 9, 64, 116)
    return doc(body + f'<path d="{d}" fill="#fff" {tr}/>', defs)


def trophy_crown(key, place):
    L = LEAGUES[key]; a, b, c = MEDAL[place]; u = f"tc{key}{place}"
    defs = (f'<linearGradient id="{u}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{a}"/><stop offset=".5" stop-color="{b}"/><stop offset="1" stop-color="{c}"/></linearGradient>'
            f'<linearGradient id="{u}v" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{L["light"]}"/><stop offset="1" stop-color="{L["deep"]}"/></linearGradient>')
    body = (f'<path d="M22 46 L40 66 L50 26 L64 56 L78 26 L88 66 L106 46 L98 96 H30 Z" fill="url(#{u})" stroke="{c}" stroke-width="1.6" stroke-linejoin="round"/>'
            f'<rect x="28" y="92" width="72" height="16" rx="4" fill="url(#{u}v)" stroke="{c}" stroke-width="1.2"/>'
            f'<circle cx="50" cy="24" r="4" fill="url(#{u}v)"/><circle cx="78" cy="24" r="4" fill="url(#{u}v)"/><circle cx="22" cy="44" r="3.4" fill="url(#{u}v)"/><circle cx="106" cy="44" r="3.4" fill="url(#{u}v)"/>'
            f'<circle cx="64" cy="74" r="14" fill="url(#{u}v)" stroke="#fff" stroke-opacity=".6"/>' + glyph(key, 13, 64, 74, "#fff"))
    tr, d = placed(DIGITS[place], 10, 64, 100)
    return doc(body + f'<path d="{d}" fill="#fff" {tr}/>', defs)


TROPHIES = [("Кубок", trophy_cup), ("Звезда-орден", trophy_star), ("Вымпел", trophy_pennant),
            ("Наградная розетка", trophy_prize_rosette), ("Корона", trophy_crown)]
