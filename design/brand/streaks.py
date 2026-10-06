"""Значки серии: пламя из логотипа «разогревается» с длиной серии.

Шесть порогов — 7, 15, 30, 50, 100 и 150 дней — и шесть температур огня из
концепта лиг «Пламя бренда»: тлеющий уголь → оранжевый огонь → жёлтый →
белый → голубой → плазма. Цифры — в конструкции логотипа (leagues.DIGITS
плюс 0, 5 и 7, построенные тем же способом), белые с тёмной обводкой тона
пламени: на светлых огнях белая цифра без обводки пропала бы.
"""
from concepts import TEMPS, doc
from leagues import DIGITS, ORDER, P
from logo import FLAME_CORE, FLAME_MID, FLAME_OUTER

THRESHOLDS = [7, 15, 30, 50, 100, 150]

# Цифры, которых нет в leagues.DIGITS: ширина и контур в сетке высотой 100.
# 5 — это 2, отражённая по вертикали; 0 — рамка с отверстием (evenodd).
EXTRA_DIGITS = {
    0: (80, P([(0, 0, 14), (80, 0, 14), (80, 100, 14), (0, 100, 14)], 0) + " "
        + P([(20, 19, 4), (20, 81, 4), (60, 81, 4), (60, 19, 4)], 0)),
    5: (80, P([(0, 100), (80, 100, 14), (80, 41, 8), (20, 41, 4), (20, 19, 4), (80, 19), (80, 0), (0, 0),
               (0, 60, 8), (60, 60, 4), (60, 81, 4), (0, 81)], 0)),
    7: (80, P([(0, 0), (80, 0, 6), (80, 19, 4), (44, 100), (22, 100), (56, 19), (0, 19)], 0)),
}
ALL_DIGITS = {**DIGITS, **EXTRA_DIGITS}
GAP = 14

# Обводка цифр — тёмный тон своего пламени.
INK = {"delta": "#4A1004", "gamma": "#7A1405", "omega": "#9A3A06",
       "beta": "#9A5A00", "alpha": "#1F5E9E", "sigma": "#2A1690"}


def number(value, height, cx, cy, ink):
    """Число из цифр логотипа, по центру (cx, cy), высотой height."""
    digits = [int(ch) for ch in str(value)]
    widths = [ALL_DIGITS[d][0] for d in digits]
    total = sum(widths) + GAP * (len(digits) - 1)
    s = height / 100
    x = cx - total * s / 2
    parts = []
    for d, w in zip(digits, widths):
        parts.append(f'<path d="{ALL_DIGITS[d][1]}" transform="translate({x:.2f} {cy - 50 * s:.2f}) scale({s:.4f})" '
                     f'fill="#fff" fill-rule="evenodd" stroke="{ink}" stroke-width="{2.6 / s:.1f}" '
                     f'stroke-linejoin="round" paint-order="stroke"/>')
        x += (w + GAP) * s
    return "".join(parts)


def streak_badge(days):
    tier = THRESHOLDS.index(days)
    key = ORDER[tier]
    a, b, c = TEMPS[key]
    u = f"stk{days}"
    s = 1.05 + tier * .04
    defs = (f'<linearGradient id="{u}a" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{a}"/><stop offset="1" stop-color="{b}"/></linearGradient>'
            f'<linearGradient id="{u}b" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{b}"/><stop offset="1" stop-color="{c}"/></linearGradient>'
            f'<radialGradient id="{u}g" cx=".5" cy=".6" r=".5"><stop offset="0" stop-color="{b}" stop-opacity=".55"/><stop offset="1" stop-color="{b}" stop-opacity="0"/></radialGradient>')
    tx = 64 - 33 * s
    height = {1: 26, 2: 23, 3: 19}[len(str(days))]
    body = (f'<circle cx="64" cy="70" r="58" fill="url(#{u}g)"/>'
            f'<g transform="translate({tx:.1f} {116 - 90 * s:.1f}) scale({s:.2f})"><path d="{FLAME_OUTER}" fill="url(#{u}a)"/>'
            f'<path d="{FLAME_MID}" fill="url(#{u}b)"/><path d="{FLAME_CORE}" fill="{c}"/></g>'
            + number(days, height, 64, 96, INK[key]))
    return doc(body, defs)
