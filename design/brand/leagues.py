"""Знаки лиг в фирменной конструкции логотипа.

Символ лиги (Δ Γ Ω Β Α Σ) и цифры мест построены тем же способом, что и
вордмарк: многоугольник, штрих 20 на кегль 100, скругления кривыми. Пластина —
металл с фаской: обод с линейным градиентом, светлая и тёмная кромки фаски,
грань с радиальным градиентом и бликом, тиснёный символ с тенью. Убранство
растёт с лигой: заклёпки → камень → лавр → корона.
"""
import math
from pathlib import Path

from logo import P, SIGMA, A as WORD_A

HERE = Path(__file__).parent

LEAGUES = {
    "delta": dict(ru="Дельта", light="#F1D2AE", mid="#B9824F", deep="#5E3A17", tint="#FFF3E4"),
    "gamma": dict(ru="Гамма", light="#B9E4FA", mid="#3B95CC", deep="#0B3E62", tint="#E6F6FF"),
    "omega": dict(ru="Омега", light="#CDB8FA", mid="#7656D2", deep="#33217A", tint="#F2ECFF"),
    "beta": dict(ru="Бетта", light="#86E5BD", mid="#109A66", deep="#07533A", tint="#E3FAEF"),
    "alpha": dict(ru="Альфа", light="#FFCC86", mid="#EE8320", deep="#7E3F04", tint="#FFF1DE"),
    "sigma": dict(ru="Сигма", light="#FFE58A", mid="#D9A31B", deep="#6E4F03", tint="#FFF8DC"),
}
ORDER = ["delta", "gamma", "omega", "beta", "alpha", "sigma"]
MEDALS = {
    1: dict(a="#FFF4C8", b="#F4C23A", c="#A87705"),
    2: dict(a="#FFFFFF", b="#C9D3E6", c="#6F7C99"),
    3: dict(a="#F9DDC2", b="#D2914F", c="#7E4B1E"),
}

# Пластины (сетка 128), центр масштабирования и место символа (центр Y, кегль).
PLATES = {
    "delta": ("M58.5 13 C61 8.5 67 8.5 69.5 13 L117 103 C120 109 116.5 117 109.5 117 H18.5 "
              "C11.5 117 8 109 11 103 Z", (64, 78), 81, 46),
    "gamma": ("M57 11.5 C61 7.5 67 7.5 71 11.5 L116.5 57 C120.5 61 120.5 67 116.5 71 L71 116.5 "
              "C67 120.5 61 120.5 57 116.5 L11.5 71 C7.5 67 7.5 61 11.5 57 Z", (64, 64), 64, 46),
    "omega": ("M60 9.2 C62.5 7.8 65.5 7.8 68 9.2 L109 32 C111.5 33.4 113 36 113 39 V89 C113 92 111.5 94.6 109 96 "
              "L68 118.8 C65.5 120.2 62.5 120.2 60 118.8 L19 96 C16.5 94.6 15 92 15 89 V39 C15 36 16.5 33.4 19 32 Z",
              (64, 64), 64, 50),
    "beta": ("M64 9 C82 9 98 14 107 20 C108 62 99 98 64 119 C29 98 20 62 21 20 C30 14 46 9 64 9 Z",
             (64, 60), 57, 52),
    "alpha": ("M60.5 9.5 C62.6 8 65.4 8 67.5 9.5 L115 44 C117 45.5 118 48 117.2 50.5 L99 106.5 "
              "C98.2 109 96 110.5 93.4 110.5 H34.6 C32 110.5 29.8 109 29 106.5 L10.8 50.5 C10 48 11 45.5 13 44 Z",
              (64, 64), 66, 50),
    "sigma": ("M44 10 H84 C86 10 88 10.8 89.4 12.2 L115.8 38.6 C117.2 40 118 42 118 44 V84 C118 86 117.2 88 115.8 89.4 "
              "L89.4 115.8 C88 117.2 86 118 84 118 H44 C42 118 40 117.2 38.6 115.8 L12.2 89.4 C10.8 88 10 86 10 84 V44 "
              "C10 42 10.8 40 12.2 38.6 L38.6 12.2 C40 10.8 42 10 44 10 Z", (64, 64), 64, 52),
}


# ── Символы в конструкции логотипа (кегль 100, штрих 20) ────────────────────
def g_delta():
    return 100, P([(50, 0, 10), (100, 100, 8), (0, 100, 8)], 0) + " " + P(
        [(50, 44.7, 3), (32.4, 80, 3), (67.6, 80, 3)], 0)


def g_gamma():
    return 80, P([(0, 0), (80, 0), (80, 19), (20, 19), (20, 100), (0, 100)], 0)


def g_omega():
    # Арка из двух концентрических дуг (штрих 20) и ножки-«ступни» наружу.
    return 100, ("M0 100 V83 Q0 81 2 81 H9 V44 A41 41 0 0 1 91 44 V81 H98 Q100 81 100 83 V100 H71 V44 "
                 "A21 21 0 0 0 29 44 V100 Z")


def g_beta():
    outer = P([(0, 0), (82, 0, 14), (82, 40, 6), (92, 50, 6), (92, 100, 14), (0, 100)], 0)
    h1 = P([(20, 19, 4), (20, 38, 4), (62, 38, 4), (62, 19, 4)], 0)
    h2 = P([(20, 58, 4), (20, 81, 4), (72, 81, 4), (72, 58, 4)], 0)
    return 92, outer + " " + h1 + " " + h2


def g_alpha():
    return WORD_A(0)


def g_sigma():
    return SIGMA(0)


GLYPHS = {"delta": g_delta, "gamma": g_gamma, "omega": g_omega, "beta": g_beta, "alpha": g_alpha, "sigma": g_sigma}

DIGITS = {
    1: (46, P([(18, 0, 3), (42, 0, 3), (42, 100), (22, 100), (22, 21, 2), (6, 29, 2), (6, 10, 2)], 0)),
    2: (80, P([(0, 0), (80, 0, 14), (80, 59, 8), (20, 59, 4), (20, 81, 4), (80, 81), (80, 100), (0, 100),
               (0, 40, 8), (60, 40, 4), (60, 19, 4), (0, 19)], 0)),
    3: (80, P([(0, 0), (80, 0, 14), (80, 100, 14), (0, 100), (0, 81), (60, 81, 4), (60, 59, 4), (14, 59),
               (14, 40), (60, 40, 4), (60, 19, 4), (0, 19)], 0)),
}


def placed(path_w, size, cx, cy):
    w, d = path_w
    s = size / 100
    return f'transform="translate({cx - w * s / 2:.2f} {cy - 50 * s:.2f}) scale({s:.4f})"', d


def scaled(cx, cy, k):
    return f'transform="translate({cx:.2f} {cy:.2f}) scale({k}) translate({-cx:.2f} {-cy:.2f})"'


def laurel(side, color_a, color_b, uid):
    """Лавровая ветвь вдоль нижней половины пластины; side = -1 слева, 1 справа."""
    leaves = []
    for i in range(9):
        t = i / 8
        ang = math.radians(200 - 95 * t) if side < 0 else math.radians(-20 + 95 * t)
        r = 58
        x = 64 + r * math.cos(ang)
        y = 66 + r * math.sin(ang) * 0.95
        rot = math.degrees(ang) + (90 if side < 0 else -90) + (25 * side)
        leaves.append(f'<ellipse cx="{x:.1f}" cy="{y:.1f}" rx="4.4" ry="9.5" transform="rotate({rot:.1f} {x:.1f} {y:.1f})" '
                      f'fill="url(#{uid}leaf)" stroke="{color_b}" stroke-opacity=".5" stroke-width=".6"/>')
    a0 = math.radians(200) if side < 0 else math.radians(-20)
    a1 = math.radians(105) if side < 0 else math.radians(75)
    x0, y0 = 64 + 58 * math.cos(a0), 66 + 58 * math.sin(a0) * .95
    x1, y1 = 64 + 58 * math.cos(a1), 66 + 58 * math.sin(a1) * .95
    sweep = 0 if side < 0 else 1
    stem = f'<path d="M{x0:.1f} {y0:.1f} A58 55 0 0 {sweep} {x1:.1f} {y1:.1f}" fill="none" stroke="{color_b}" stroke-width="1.6" stroke-linecap="round"/>'
    return stem + "".join(leaves)


def crown(uid, L):
    return (f'<path d="M38 22 L36 6 L48 14 L56 2 L64 11 L72 2 L80 14 L92 6 L90 22 C80 25 48 25 38 22 Z" '
            f'fill="url(#{uid}rim)" stroke="{L["deep"]}" stroke-width="1.4" stroke-linejoin="round"/>'
            f'<path d="M39 18.5 C49 21 79 21 89 18.5" fill="none" stroke="{L["deep"]}" stroke-opacity=".45" stroke-width="1.2"/>'
            f'<circle cx="64" cy="15.5" r="3" fill="#E64060" stroke="#7A1830" stroke-width=".7"/>'
            f'<circle cx="49" cy="17" r="2.1" fill="#3E86F0" stroke="#123D8C" stroke-width=".5"/>'
            f'<circle cx="79" cy="17" r="2.1" fill="#3E86F0" stroke="#123D8C" stroke-width=".5"/>'
            f'<circle cx="36" cy="6" r="1.8" fill="{L["light"]}"/><circle cx="56" cy="2" r="1.8" fill="{L["light"]}"/>'
            f'<circle cx="72" cy="2" r="1.8" fill="{L["light"]}"/><circle cx="92" cy="6" r="1.8" fill="{L["light"]}"/>')


def gem(cx, cy, r, uid, color="#3E86F0", deep="#123D8C"):
    return (f'<g><path d="M{cx} {cy - r} L{cx + r} {cy} L{cx} {cy + r} L{cx - r} {cy} Z" fill="{color}" stroke="{deep}" stroke-width=".8"/>'
            f'<path d="M{cx} {cy - r} L{cx + r} {cy} L{cx} {cy} Z" fill="#fff" opacity=".45"/></g>')


def rivets(points, L):
    return "".join(
        f'<circle cx="{x}" cy="{y}" r="2.6" fill="{L["tint"]}" stroke="{L["deep"]}" stroke-width=".8"/>'
        f'<circle cx="{x - .7}" cy="{y - .8}" r=".9" fill="#fff"/>' for x, y in points)


def medal(place, uid):
    M = MEDALS[place]
    tr, d = placed(DIGITS[place], 15, 101, 101)
    return (f'<g><circle cx="101" cy="103" r="19" fill="#000" opacity=".18"/>'
            f'<circle cx="101" cy="101" r="19" fill="url(#{uid}m1)" stroke="{M["c"]}" stroke-width="1.2"/>'
            f'<circle cx="101" cy="101" r="14.5" fill="url(#{uid}m2)" stroke="{M["c"]}" stroke-opacity=".6" stroke-width="1"/>'
            f'<g {tr}><path d="{d}" fill="{M["c"]}" transform="translate(0 7)" opacity=".55"/>'
            f'<path d="{d}" fill="#fff"/></g></g>')


def league_svg(key, place=None):
    L = LEAGUES[key]
    plate, (cx, cy), gy, gs = PLATES[key]
    uid = f"lg{key}{place or 0}"
    tier = ORDER.index(key)
    gtr, gd = placed(GLYPHS[key](), gs, 64, gy)
    defs = f"""<defs>
<linearGradient id="{uid}rim" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{L['light']}"/><stop offset=".45" stop-color="{L['mid']}"/><stop offset="1" stop-color="{L['deep']}"/></linearGradient>
<radialGradient id="{uid}face" cx=".38" cy=".3" r=".85"><stop offset="0" stop-color="{L['light']}"/><stop offset=".55" stop-color="{L['mid']}"/><stop offset="1" stop-color="{L['deep']}"/></radialGradient>
<linearGradient id="{uid}glyph" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FFFFFF"/><stop offset="1" stop-color="{L['tint']}"/></linearGradient>
<linearGradient id="{uid}shine" x1="0" y1="0" x2=".6" y2=".9"><stop offset="0" stop-color="#fff" stop-opacity=".55"/><stop offset=".55" stop-color="#fff" stop-opacity="0"/></linearGradient>
<linearGradient id="{uid}leaf" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#9BE38A"/><stop offset="1" stop-color="#2F8A3A"/></linearGradient>
<radialGradient id="{uid}m1" cx=".35" cy=".3" r=".9"><stop offset="0" stop-color="{MEDALS[place or 1]['a']}"/><stop offset=".6" stop-color="{MEDALS[place or 1]['b']}"/><stop offset="1" stop-color="{MEDALS[place or 1]['c']}"/></radialGradient>
<linearGradient id="{uid}m2" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{MEDALS[place or 1]['b']}"/><stop offset="1" stop-color="{MEDALS[place or 1]['c']}"/></linearGradient>
<clipPath id="{uid}clip"><path d="{plate}" {scaled(cx, cy, .82)}/></clipPath>
<filter id="{uid}drop" x="-20%" y="-20%" width="140%" height="150%"><feGaussianBlur stdDeviation="2.2"/></filter>
</defs>"""
    body = []
    # Убранство под пластиной (лавр).
    if tier >= 4:
        body.append(laurel(-1, None, "#2F7A34", uid) + laurel(1, None, "#2F7A34", uid))
    body.append(f'<path d="{plate}" fill="{L["deep"]}" opacity=".35" transform="translate(0 3)" filter="url(#{uid}drop)"/>')
    body.append(f'<path d="{plate}" fill="url(#{uid}rim)"/>')
    body.append(f'<path d="{plate}" fill="none" stroke="#fff" stroke-opacity=".55" stroke-width="1.3" {scaled(cx, cy, .965)}/>')
    body.append(f'<path d="{plate}" fill="{L["deep"]}" {scaled(cx, cy, .855)}/>')
    body.append(f'<path d="{plate}" fill="url(#{uid}face)" {scaled(cx, cy, .82)}/>')
    body.append(f'<g clip-path="url(#{uid}clip)"><path d="M0 0 H128 L0 96 Z" fill="url(#{uid}shine)"/>'
                f'<circle cx="{cx}" cy="{cy}" r="30" fill="{L["light"]}" opacity=".18"/>'
                + "".join(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#fff" stroke-opacity=".09" stroke-width=".8"/>' for r in range(8, 62, 4))
                + '</g>')
    # Символ: тень, тёмная кромка, светлое тело.
    body.append(f'<g {gtr}><path d="{gd}" fill="{L["deep"]}" fill-rule="evenodd" transform="translate(0 9)" opacity=".7"/>'
                f'<path d="{gd}" fill="#fff" fill-rule="evenodd" transform="translate(0 -3)" opacity=".75"/>'
                f'<path d="{gd}" fill="url(#{uid}glyph)" fill-rule="evenodd" stroke="{L["deep"]}" stroke-opacity=".35" stroke-width="2.5"/></g>')
    # Убранство поверх.
    if tier == 1:
        body.append(rivets([(26, 64), (102, 64)], L))
    if tier == 2:
        body.append(rivets([(64, 20), (28, 86), (100, 86)], L))
    if tier == 3:
        body.append(gem(64, 19, 5.5, uid, "#E64060", "#7A1830"))
    if tier == 4:
        body.append(gem(64, 17, 5.5, uid))
    if tier == 5:
        body.append(crown(uid, L))
        body.append(gem(64, 108, 4.5, uid, "#E64060", "#7A1830"))
    if place:
        body.append(medal(place, uid))
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">{defs}{"".join(body)}</svg>'
