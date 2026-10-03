# -*- coding: utf-8 -*-
"""Аватары трека «Призма». 19 позиций: базовые, обычные, анимированные."""
import math
from lib import svg_doc, shell_a, txt, _SANS

W = "#FFFFFF"

# key, ru, категория, tier, light, mid, deep
# tier: base — бесплатный набор, paid — покупной, anim — анимированный (премиум)
SPEC = [
    ("sigma",     "Сигма",       "Математика", "base", "#9FB2FF", "#4F6BEA", "#22318E"),
    ("integral",  "Интеграл",    "Математика", "base", "#7FE0CD", "#17A88E", "#075949"),
    ("pi",        "Пи",          "Математика", "base", "#6EDCA9", "#0E9A64", "#065138"),
    ("infinity",  "Лемниската",  "Математика", "base", "#86D4F0", "#2C9BC8", "#0B5476"),

    ("owl",       "Сова",        "Звери",      "paid", "#A9BAFF", "#5C74E8", "#25358F"),
    ("fox",       "Лис",         "Звери",      "paid", "#FFC486", "#F58A1E", "#9A5405"),
    ("bear",      "Медведь",     "Звери",      "paid", "#D9A877", "#A0703E", "#4E2E12"),
    ("whale",     "Кит",         "Звери",      "paid", "#8ADCF6", "#2FA5D8", "#0F5E86"),
    ("hedgehog",  "Ёж",          "Звери",      "paid", "#E6BE96", "#B87B45", "#6B4118"),
    ("robot",     "Робот",       "Персонажи",  "paid", "#B9C4DE", "#7B88A8", "#2E374F"),
    ("astronaut", "Космонавт",   "Персонажи",  "paid", "#C0B0F5", "#8467E0", "#3A2688"),
    ("wizard",    "Волшебник",   "Персонажи",  "paid", "#C79CF0", "#7B5CD6", "#37237A"),
    ("ninja",     "Ниндзя",      "Персонажи",  "paid", "#6C7896", "#3A4460", "#0D1223"),
    ("cat",       "Кот",         "Звери",      "paid", "#A8C0E0", "#5F7FA8", "#21384F"),
    ("penguin",   "Пингвин",     "Звери",      "paid", "#9DB6D6", "#3E5170", "#101A2C"),
    ("dragon",    "Дракон",      "Персонажи",  "paid", "#FF9E8A", "#D8392E", "#6E120B"),
    ("icosa",     "Икосаэдр",    "Геометрия",  "paid", "#9FE0FF", "#3C9AD0", "#0C4468"),
    ("spiral",    "Спираль",     "Геометрия",  "paid", "#FFD98A", "#D8A02E", "#6E4A05"),

    ("tesseract", "Тессеракт",   "Геометрия",  "anim", "#A9B0FF", "#4A50C8", "#171B52"),
    ("fractal",   "Фрактал",     "Геометрия",  "anim", "#FFA8C0", "#E0507A", "#7A1030"),
    ("crystal",   "Кристалл",    "Геометрия",  "anim", "#F0A2DA", "#C755A8", "#6E2058"),
    ("blackhole", "Чёрная дыра", "Космос",     "anim", "#6E6BB8", "#2C2E60", "#0A0B22"),
    ("comet",     "Комета",      "Космос",     "anim", "#FFE08A", "#F0A81E", "#8A5A05"),
    ("origami",   "Оригами",     "Стихии",     "anim", "#FFA694", "#EE6350", "#8E2A1B"),
    ("mobius",    "Лента Мёбиуса","Геометрия", "anim", "#B7E8DC", "#2FA890", "#0A4E42"),
]

TIER_RU = {"base": "базовый набор", "paid": "покупной", "anim": "анимированный"}


def _eye(cx, cy, d, rx=5.0, ry=6.2):
    """Глаз со зрачком и бликом."""
    return (f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="{d}" fill-opacity=".82"/>'
            f'<circle cx="{cx + rx*0.42:.1f}" cy="{cy - ry*0.34:.1f}" r="{rx*0.32:.1f}" fill="{W}" fill-opacity=".9"/>')


def _sierpinski(p1, p2, p3, depth):
    if depth == 0:
        return [(p1, p2, p3)]
    m = lambda a, b: ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    return (_sierpinski(p1, m(p1, p2), m(p1, p3), depth - 1)
            + _sierpinski(m(p1, p2), p2, m(p2, p3), depth - 1)
            + _sierpinski(m(p1, p3), m(p2, p3), p3, depth - 1))


def _icosahedron(rot_y=0.0, rot_x=0.5535, r=52, cx=64, cy=64):
    """Видимые грани икосаэдра в ортографической проекции: [(points, затенение)]."""
    p = (1 + 5 ** 0.5) / 2
    v = []
    for s1 in (1, -1):
        for s2 in (1, -1):
            v += [(0.0, s1 * 1.0, s2 * p), (s1 * 1.0, s2 * p, 0.0), (s2 * p, 0.0, s1 * 1.0)]
    v = list(dict.fromkeys(v))
    n = len(v)
    d2 = lambda a, b: sum((a[i] - b[i]) ** 2 for i in range(3))
    edge = min(d2(v[0], v[j]) for j in range(1, n))
    faces = []
    for i in range(n):
        for j in range(i + 1, n):
            if abs(d2(v[i], v[j]) - edge) > 1e-6:
                continue
            for k in range(j + 1, n):
                if abs(d2(v[i], v[k]) - edge) < 1e-6 and abs(d2(v[j], v[k]) - edge) < 1e-6:
                    faces.append((i, j, k))
    cy_, sy = math.cos(rot_y), math.sin(rot_y)
    cx_, sx = math.cos(rot_x), math.sin(rot_x)

    def rot(pt):
        x, y, z = pt
        x, z = x * cy_ + z * sy, -x * sy + z * cy_
        y, z = y * cx_ - z * sx, y * sx + z * cx_
        return (x, y, z)

    rv = [rot(pt) for pt in v]
    k = r / (1 + p ** 2) ** 0.5
    out = []
    for f in faces:
        a, b, c = (rv[i] for i in f)
        ux, uy, uz = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
        wx, wy, wz = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
        nz = ux * wy - uy * wx
        if nz <= 0:
            continue
        depth = (a[2] + b[2] + c[2]) / 3
        pts = " ".join(f"{cx + q[0]*k:.1f},{cy - q[1]*k:.1f}" for q in (a, b, c))
        out.append((pts, depth))
    out.sort(key=lambda o: o[1])
    lo = min(o[1] for o in out); hi = max(o[1] for o in out)
    faces = [(pts, 0.26 + 0.70 * (dp - lo) / (hi - lo + 1e-9)) for pts, dp in out]
    # силуэт — выпуклая оболочка всех спроецированных вершин
    pp = sorted(((cx + q[0] * k, cy - q[1] * k) for q in rv))
    def half(seq):
        h = []
        for q in seq:
            while len(h) > 1 and ((h[-1][0]-h[-2][0])*(q[1]-h[-2][1])
                                  - (h[-1][1]-h[-2][1])*(q[0]-h[-2][0])) <= 0:
                h.pop()
            h.append(q)
        return h
    hull = half(pp)[:-1] + half(pp[::-1])[:-1]
    sil = " ".join(f"{x:.1f},{y:.1f}" for x, y in hull)
    return faces, sil


def _golden_spiral(turns=7):
    """Дуги золотой спирали, вписанные в холст 128×128."""
    phi = (1 + 5 ** 0.5) / 2
    segs, pts = [], []
    r, ang = 8.0, 0.0
    px, py = 0.0, 0.0
    for _ in range(turns):
        a0 = math.radians(ang)
        a1 = math.radians(ang + 90)
        x0, y0 = px + r * math.cos(a0), py + r * math.sin(a0)
        x1, y1 = px + r * math.cos(a1), py + r * math.sin(a1)
        segs.append((px, py, r, x0, y0, x1, y1))
        pts += [(x0, y0), (x1, y1), (px, py)]
        nr = r * phi
        px, py = x1 - nr * math.cos(a1), y1 - nr * math.sin(a1)
        r = nr
        ang += 90
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    sc = 96.0 / max(max(xs) - min(xs), max(ys) - min(ys))
    ox = 64 - (min(xs) + max(xs)) / 2 * sc
    oy = 64 - (min(ys) + max(ys)) / 2 * sc
    out = []
    for cxx, cyy, rr, x0, y0, x1, y1 in segs:
        out.append((f"M{x0*sc+ox:.1f} {y0*sc+oy:.1f} A{rr*sc:.1f} {rr*sc:.1f} 0 0 1 "
                    f"{x1*sc+ox:.1f} {y1*sc+oy:.1f}",
                    cxx * sc + ox, cyy * sc + oy, rr * sc))
    return out


def art(key, d):
    # ── Математика: базовый набор ────────────────────────────────────────
    if key in ("sigma", "integral", "pi", "infinity"):
        glyph = {"sigma": "Σ", "integral": "∫", "pi": "π", "infinity": "∞"}[key]
        size = {"sigma": 66, "integral": 80, "pi": 70, "infinity": 74}[key]
        return (f'<g>{txt(64, 67, glyph, size, W, 700, opacity=.20, font=_SANS)}'
                f'{txt(64, 64, glyph, size, W, 700, opacity=.97, font=_SANS)}</g>')

    if key == "owl":
        return f"""<g>
<path d="M38 40 L34 22 L52 32 Z" fill="{W}" fill-opacity=".9"/>
<path d="M90 40 L94 22 L76 32 Z" fill="{W}" fill-opacity=".9"/>
<path d="M64 30 C87 30 101 48 101 70 C101 91 85 106 64 106 C43 106 27 91 27 70 C27 48 41 30 64 30 Z" fill="{W}" fill-opacity=".95"/>
<circle cx="50" cy="63" r="14" fill="{d}" fill-opacity=".14"/>
<circle cx="78" cy="63" r="14" fill="{d}" fill-opacity=".14"/>
<circle cx="50" cy="63" r="6.5" fill="{d}" fill-opacity=".85"/>
<circle cx="78" cy="63" r="6.5" fill="{d}" fill-opacity=".85"/>
<circle cx="52.5" cy="60.5" r="2.2" fill="{W}"/>
<circle cx="80.5" cy="60.5" r="2.2" fill="{W}"/>
<path d="M64 74 L57 82 L64 90 L71 82 Z" fill="{d}" fill-opacity=".7"/>
<path d="M40 88 C48 98 56 103 64 105 C72 103 80 98 88 88" stroke="{d}" stroke-opacity=".12" stroke-width="5" stroke-linecap="round"/>
</g>"""

    if key == "fox":
        return f"""<g>
<path d="M31 58 L33 18 L62 40 Z" fill="{W}" fill-opacity=".94"/>
<path d="M97 58 L95 18 L66 40 Z" fill="{W}" fill-opacity=".94"/>
<path d="M40 30 L41 49 L53 40 Z" fill="{d}" fill-opacity=".2"/>
<path d="M88 30 L87 49 L75 40 Z" fill="{d}" fill-opacity=".2"/>
<path d="M64 34 C86 34 100 47 100 63 C100 73 96 81 90 87 C85 95 76 105 64 110 C52 105 43 95 38 87 C32 81 28 73 28 63 C28 47 42 34 64 34 Z" fill="{W}" fill-opacity=".96"/>
<path d="M64 70 C75 70 84 78 84 88 C84 99 75 110 64 110 C53 110 44 99 44 88 C44 78 53 70 64 70 Z" fill="{d}" fill-opacity=".10"/>
{_eye(50, 62, d)}
{_eye(78, 62, d)}
<path d="M64 88 C60 88 56 85 56 82 C56 79 60 78 64 78 C68 78 72 79 72 82 C72 85 68 88 64 88 Z" fill="{d}" fill-opacity=".82"/>
<path d="M64 88 V95 M64 95 C61 100 55 100 52 96 M64 95 C67 100 73 100 76 96" stroke="{d}" stroke-opacity=".3" stroke-width="3" stroke-linecap="round" fill="none"/>
</g>"""

    if key == "bear":
        return f"""<g>
<circle cx="34" cy="38" r="16" fill="{W}" fill-opacity=".94"/>
<circle cx="94" cy="38" r="16" fill="{W}" fill-opacity=".94"/>
<circle cx="34" cy="38" r="7.5" fill="{d}" fill-opacity=".2"/>
<circle cx="94" cy="38" r="7.5" fill="{d}" fill-opacity=".2"/>
<path d="M64 34 C89 34 105 51 105 72 C105 93 88 108 64 108 C40 108 23 93 23 72 C23 51 39 34 64 34 Z" fill="{W}" fill-opacity=".96"/>
<ellipse cx="64" cy="86" rx="25" ry="18" fill="{d}" fill-opacity=".11"/>
{_eye(49, 65, d, 4.6, 5.6)}
{_eye(79, 65, d, 4.6, 5.6)}
<path d="M64 84 C59 84 54 81 54 77 C54 74 59 72 64 72 C69 72 74 74 74 77 C74 81 69 84 64 84 Z" fill="{d}" fill-opacity=".8"/>
<path d="M64 84 V90 M64 90 C61 95 55 95 52 91 M64 90 C67 95 73 95 76 91" stroke="{d}" stroke-opacity=".32" stroke-width="3.2" stroke-linecap="round" fill="none"/>
</g>"""

    if key == "whale":
        return f"""<g>
<path d="M94 55 C102 45 116 35 126 36 C122 47 112 55 103 60 C112 65 122 73 126 84 C116 85 102 75 94 65 Z" fill="{W}" fill-opacity=".84"/>
<path d="M12 62 C12 40 32 26 58 26 C80 26 94 36 100 50 C103 56 103 66 100 72 C93 88 76 98 52 98 C27 98 12 84 12 62 Z" fill="{W}" fill-opacity=".96"/>
<path d="M14 74 C26 88 46 95 68 92 C82 90 92 84 99 74 C93 89 76 98 52 98 C29 98 16 88 14 74 Z" fill="{d}" fill-opacity=".14"/>
<path d="M12 64 C28 76 54 82 82 78" stroke="{d}" stroke-opacity=".34" stroke-width="3.4" fill="none"/>
<path d="M18 74 C30 84 48 89 68 87 M22 82 C33 89 48 92 64 91 M28 89 C37 93 48 95 60 95" stroke="{d}" stroke-opacity=".2" stroke-width="2.4" fill="none"/>
<path d="M16 44 C26 38 40 35 56 35" stroke="{W}" stroke-opacity=".5" stroke-width="3" fill="none"/>
{_eye(32, 56, d, 5.2, 5.8)}
<path d="M40 28 C40 18 46 14 46 6 M54 27 C56 19 62 16 64 9" stroke="{W}" stroke-opacity=".8" stroke-width="5" stroke-linecap="round"/>
<circle cx="46" cy="5" r="3.4" fill="{W}" fill-opacity=".8"/>
<circle cx="65" cy="7" r="2.6" fill="{W}" fill-opacity=".8"/>
</g>"""

    if key == "hedgehog":
        sp1 = "".join(f'<path d="M{x} {y} L{x+11} {y-22} L{x+22} {y} Z" fill="{W}" fill-opacity=".55"/>'
                      for x, y in [(12, 66), (28, 54), (46, 46), (66, 46), (84, 54)])
        sp2 = "".join(f'<path d="M{x} {y} L{x+10} {y-18} L{x+20} {y} Z" fill="{W}" fill-opacity=".85"/>'
                      for x, y in [(18, 76), (36, 62), (56, 56), (76, 62), (92, 76)])
        return f"""<g>
{sp1}{sp2}
<path d="M16 84 C16 62 37 48 64 48 C91 48 112 62 112 84 Z" fill="{W}" fill-opacity=".9"/>
<path d="M16 84 H112" stroke="{d}" stroke-opacity=".16" stroke-width="4"/>
<path d="M64 62 C84 62 97 74 97 90 C97 104 83 114 64 114 C45 114 31 104 31 90 C31 74 44 62 64 62 Z" fill="{W}" fill-opacity=".97"/>
{_eye(52, 84, d, 4.4, 5.2)}
{_eye(76, 84, d, 4.4, 5.2)}
<path d="M64 102 C60 102 57 99 57 96 C57 94 60 93 64 93 C68 93 71 94 71 96 C71 99 68 102 64 102 Z" fill="{d}" fill-opacity=".82"/>
</g>"""

    if key == "robot":
        return f"""<g>
<path d="M64 34 V20" stroke="{W}" stroke-opacity=".85" stroke-width="5" stroke-linecap="round"/>
<circle cx="64" cy="17" r="6" fill="{W}" fill-opacity=".92"/>
<rect x="20" y="56" width="10" height="24" rx="5" fill="{W}" fill-opacity=".75"/>
<rect x="98" y="56" width="10" height="24" rx="5" fill="{W}" fill-opacity=".75"/>
<rect x="30" y="34" width="68" height="62" rx="20" fill="{W}" fill-opacity=".95"/>
<rect x="40" y="50" width="48" height="30" rx="15" fill="{d}" fill-opacity=".78"/>
<circle cx="54" cy="65" r="6" fill="{W}"/>
<circle cx="74" cy="65" r="6" fill="{W}"/>
<path d="M54 87 H74" stroke="{d}" stroke-opacity=".35" stroke-width="5" stroke-linecap="round"/>
</g>"""

    if key == "astronaut":
        return f"""<g>
<rect x="34" y="72" width="60" height="30" rx="14" fill="{W}" fill-opacity=".7"/>
<circle cx="64" cy="60" r="36" fill="{W}" fill-opacity=".95"/>
<path d="M36 58 C36 42 49 32 64 32 C79 32 92 42 92 58 C92 73 79 82 64 82 C49 82 36 73 36 58 Z" fill="{d}" fill-opacity=".8"/>
<path d="M46 62 C46 50 54 42 64 40" stroke="{W}" stroke-opacity=".75" stroke-width="6" stroke-linecap="round"/>
<path d="M56 68 C56 60 60 54 66 51" stroke="{W}" stroke-opacity=".35" stroke-width="4" stroke-linecap="round"/>
<rect x="52" y="90" width="24" height="8" rx="4" fill="{d}" fill-opacity=".2"/>
</g>"""

    if key == "wizard":
        return f"""<g>
<path d="M64 4 C60 22 50 46 42 62 H86 C78 46 68 22 64 4 Z" fill="{W}" fill-opacity=".96"/>
<path d="M30 62 H98 C98 70 88 74 64 74 C40 74 30 70 30 62 Z" fill="{W}" fill-opacity=".96"/>
<path d="M30 62 H98 C98 66 94 68.5 87 70 C79 71.5 71 72 64 72 C57 72 49 71.5 41 70 C34 68.5 30 66 30 62 Z" fill="{d}" fill-opacity=".16"/>
<path d="M64 20 L67.5 30 L77 33.5 L67.5 37 L64 47 L60.5 37 L51 33.5 L60.5 30 Z" fill="{d}" fill-opacity=".55"/>
<circle cx="55" cy="52" r="2.8" fill="{d}" fill-opacity=".4"/>
<path d="M64 74 C79 74 89 83 89 95 C89 98 88 101 87 104 C81 98 73 94 64 94 C55 94 47 98 41 104 C40 101 39 98 39 95 C39 83 49 74 64 74 Z" fill="{W}" fill-opacity=".95"/>
{_eye(54, 86, d, 4.4, 5.0)}
{_eye(74, 86, d, 4.4, 5.0)}
<path d="M44 98 C48 96 56 95 64 95 C72 95 80 96 84 98 C82 114 74 124 64 124 C54 124 46 114 44 98 Z" fill="{W}" fill-opacity=".88"/>
<path d="M44 98 C48 96 56 95 64 95 C72 95 80 96 84 98" stroke="{d}" stroke-opacity=".2" stroke-width="2.6" fill="none"/>
<path d="M57 103 C60 105 68 105 71 103" stroke="{d}" stroke-opacity=".3" stroke-width="3" stroke-linecap="round" fill="none"/>
</g>"""

    if key == "ninja":
        return f"""<g>
<path d="M96 50 C108 44 120 44 126 48 C118 52 110 56 104 60 C114 62 122 68 126 74 C116 74 106 70 98 66 Z" fill="{W}" fill-opacity=".6"/>
<circle cx="64" cy="64" r="35" fill="{W}" fill-opacity=".95"/>
<path d="M30 56 C42 47 86 47 98 56 L98 76 C86 85 42 85 30 76 Z" fill="{d}" fill-opacity=".84"/>
<path d="M42 66 C47 61 56 60 61 65 C56 70 47 71 42 66 Z" fill="{W}"/>
<path d="M67 65 C72 60 81 61 86 66 C81 71 72 70 67 65 Z" fill="{W}"/>
<circle cx="52" cy="65.5" r="2.6" fill="{d}"/>
<circle cx="76" cy="65.5" r="2.6" fill="{d}"/>
<path d="M40 55 L60 60 M88 55 L68 60" stroke="{W}" stroke-opacity=".45" stroke-width="2.6" stroke-linecap="round"/>
</g>"""

    if key == "cat":
        return f"""<g>
<path d="M32 50 L34 14 L62 36 Z" fill="{W}" fill-opacity=".94"/>
<path d="M96 50 L94 14 L66 36 Z" fill="{W}" fill-opacity=".94"/>
<path d="M40 26 L41 44 L53 37 Z" fill="{d}" fill-opacity=".2"/>
<path d="M88 26 L87 44 L75 37 Z" fill="{d}" fill-opacity=".2"/>
<path d="M64 32 C88 32 104 48 104 68 C104 90 88 106 64 106 C40 106 24 90 24 68 C24 48 40 32 64 32 Z" fill="{W}" fill-opacity=".96"/>
<ellipse cx="50" cy="64" rx="4.4" ry="8" fill="{d}" fill-opacity=".82"/>
<ellipse cx="78" cy="64" rx="4.4" ry="8" fill="{d}" fill-opacity=".82"/>
<circle cx="52" cy="60" r="1.8" fill="{W}"/><circle cx="80" cy="60" r="1.8" fill="{W}"/>
<path d="M64 84 L57 78 H71 Z" fill="{d}" fill-opacity=".82"/>
<path d="M64 84 V89 M64 89 C61 93 56 93 54 90 M64 89 C67 93 72 93 74 90" stroke="{d}" stroke-opacity=".32" stroke-width="2.8" stroke-linecap="round" fill="none"/>
<path d="M44 76 L20 70 M44 82 L21 84 M84 76 L108 70 M84 82 L107 84" stroke="{W}" stroke-opacity=".7" stroke-width="2.6" stroke-linecap="round"/>
</g>"""

    if key == "penguin":
        return f"""<g>
<path d="M28 66 L10 96 L30 98 Z" fill="{W}" fill-opacity=".7"/>
<path d="M100 66 L118 96 L98 98 Z" fill="{W}" fill-opacity=".7"/>
<path d="M64 20 C86 20 100 40 100 70 C100 98 84 114 64 114 C44 114 28 98 28 70 C28 40 42 20 64 20 Z" fill="{W}" fill-opacity=".55"/>
<path d="M64 56 C80 56 90 70 90 88 C90 105 79 114 64 114 C49 114 38 105 38 88 C38 70 48 56 64 56 Z" fill="{W}" fill-opacity=".98"/>
<circle cx="52" cy="46" r="7.5" fill="{W}" fill-opacity=".95"/>
<circle cx="76" cy="46" r="7.5" fill="{W}" fill-opacity=".95"/>
<circle cx="53" cy="47" r="3.6" fill="{d}" fill-opacity=".9"/>
<circle cx="77" cy="47" r="3.6" fill="{d}" fill-opacity=".9"/>
<path d="M64 54 L53 62 L64 70 L75 62 Z" fill="{d}" fill-opacity=".5"/>
<path d="M50 114 L38 122 H60 Z M78 114 L90 122 H68 Z" fill="{d}" fill-opacity=".5"/>
</g>"""

    if key == "dragon":
        crest = "".join(f'<path d="M{x} {y} L{x-5} {y-17} L{x+13} {y-7} Z" fill="{W}" fill-opacity=".72"/>'
                        for x, y in [(22, 78), (30, 62), (44, 48)])
        up = "".join(f'<path d="M{x} 66 L{x+4} 76 L{x+8} 66 Z" fill="{W}"/>' for x in (74, 86, 96))
        lo = "".join(f'<path d="M{x} 82 L{x+4} 73 L{x+8} 82 Z" fill="{W}"/>' for x in (72, 84))
        return f"""<g>
{crest}
<path d="M58 32 L30 8 L82 20 Z" fill="{W}" fill-opacity=".93"/>
<path d="M60 30 L46 15 L76 24 Z" fill="{d}" fill-opacity=".18"/>
<path d="M16 76 C11 50 30 30 58 28 C80 26 96 36 104 48 L120 52 L102 60 L100 68 L58 70 C40 70 26 72 16 76 Z" fill="{W}" fill-opacity=".96"/>
{up}
<path d="M36 78 C56 84 84 84 100 78 L102 88 C90 98 62 102 44 96 C36 93 33 85 36 78 Z" fill="{W}" fill-opacity=".9"/>
{lo}
<path d="M62 44 L86 50 L62 56 Z" fill="{d}" fill-opacity=".86"/>
<circle cx="71" cy="50" r="2.8" fill="{W}"/>
<path d="M56 38 L90 44" stroke="{d}" stroke-opacity=".32" stroke-width="3.6" stroke-linecap="round"/>
<circle cx="110" cy="53" r="3.2" fill="{d}" fill-opacity=".6"/>
<path d="M22 60 C32 64 44 66 58 66" stroke="{d}" stroke-opacity=".14" stroke-width="4" fill="none"/>
</g>"""

    if key == "icosa":
        fc, sil = _icosahedron()
        faces = "".join(
            f'<polygon points="{p}" fill="{W}" fill-opacity="{o:.2f}" stroke="{W}" '
            f'stroke-opacity=".6" stroke-width="1.8" stroke-linejoin="round"/>'
            for p, o in fc)
        return (f'<g><polygon points="{sil}" fill="{W}" fill-opacity=".22"/>{faces}'
                f'<polygon points="{sil}" fill="none" stroke="{W}" stroke-opacity=".95" '
                f'stroke-width="3.4" stroke-linejoin="round"/></g>')

    if key == "spiral":
        segs = _golden_spiral()
        boxes = "".join(
            f'<rect x="{cxx-rr:.1f}" y="{cyy-rr:.1f}" width="{2*rr:.1f}" height="{2*rr:.1f}" '
            f'fill="none" stroke="{W}" stroke-opacity=".16" stroke-width="1.6"/>'
            for _, cxx, cyy, rr in segs[2:])
        arcs = "".join(
            f'<path d="{p}" fill="none" stroke="{W}" stroke-opacity=".96" '
            f'stroke-width="{min(7.0, 2.2 + n * 0.85):.1f}" stroke-linecap="round"/>'
            for n, (p, cxx, cyy, rr) in enumerate(segs))
        return f'<g>{boxes}{arcs}</g>' 

    # ── Анимированные ────────────────────────────────────────────────────
    if key == "tesseract":
        o = [(22, 22), (106, 22), (106, 106), (22, 106)]
        i = [(48, 48), (80, 48), (80, 80), (48, 80)]
        links = "".join(
            f'<path class="tsr-link" style="--i:{n}" d="M{a[0]} {a[1]} L{b[0]} {b[1]}" '
            f'stroke="{W}" stroke-opacity=".55" stroke-width="3"/>'
            for n, (a, b) in enumerate(zip(o, i)))
        op = " ".join(f"{x},{y}" for x, y in o)
        ip = " ".join(f"{x},{y}" for x, y in i)
        dots = "".join(f'<circle cx="{x}" cy="{y}" r="3.2" fill="{W}" fill-opacity=".9"/>' for x, y in o)
        return f"""<g>
{links}
<polygon class="tsr-outer" points="{op}" fill="none" stroke="{W}" stroke-opacity=".95" stroke-width="4.5"/>
<polygon class="tsr-inner" points="{ip}" fill="{W}" fill-opacity=".10" stroke="{W}" stroke-opacity=".9" stroke-width="4"/>
{dots}
</g>"""

    if key == "fractal":
        tris = _sierpinski((64, 16), (16, 106), (112, 106), 2)
        body = "".join(
            f'<polygon class="frc-tri" style="--i:{n}" points="'
            + " ".join(f"{p[0]:.1f},{p[1]:.1f}" for p in t)
            + f'" fill="{W}" fill-opacity=".92"/>' for n, t in enumerate(tris))
        return f"""<g>
<polygon points="64,12 12,110 116,110" fill="none" stroke="{W}" stroke-opacity=".35" stroke-width="3"/>
{body}
</g>"""

    if key == "crystal":
        outer = "M46 12 H82 L108 44 L64 118 L20 44 Z"
        facets = [
            ("46,12 82,12 92,32 36,32", .95),   # площадка
            ("46,12 36,32 20,44", .55),         # корона слева
            ("82,12 92,32 108,44", .32),        # корона справа
            ("36,32 92,32 108,44 20,44", .70),  # рундист
            ("20,44 108,44 64,118", .42),       # павильон одной гранью — без шва по центру
        ]
        fs = "".join(
            f'<polygon class="cr-facet" style="--i:{n}" points="{p}" fill="{W}" fill-opacity="{o}"/>'
            for n, (p, o) in enumerate(facets))
        return f"""<g>
<path d="{outer}" fill="{W}" fill-opacity=".16"/>
{fs}
<path d="{outer}" fill="none" stroke="{W}" stroke-opacity=".9" stroke-width="3.5" stroke-linejoin="round"/>
<path d="M36 32 H92 M20 44 H108" stroke="{W}" stroke-opacity=".55" stroke-width="2.6"/>
<path class="cr-shine" d="M52 16 L40 31" stroke="{W}" stroke-width="4" stroke-opacity=".9" stroke-linecap="round" fill="none"/>
</g>"""

    if key == "blackhole":
        stars = "".join(
            f'<circle class="bh-star" style="--i:{n}" cx="{x}" cy="{y}" r="{r}" fill="{W}" fill-opacity=".85"/>'
            for n, (x, y, r) in enumerate([(26, 34, 2.4), (100, 30, 2), (108, 92, 2.6), (22, 96, 2)]))
        return f"""<g>
{stars}
<g class="bh-disc">
<ellipse class="bh-flow" pathLength="100" stroke-dasharray="9 3" cx="64" cy="64" rx="52" ry="18" stroke="{W}" stroke-opacity=".9" stroke-width="7" transform="rotate(-18 64 64)"/>
<ellipse class="bh-flow" pathLength="100" stroke-dasharray="6 4" cx="64" cy="64" rx="42" ry="12" stroke="{W}" stroke-opacity=".45" stroke-width="4" transform="rotate(-18 64 64)"/>
</g>
<circle class="bh-core" cx="64" cy="64" r="23" fill="{d}" fill-opacity=".94"/>
<circle class="bh-core" cx="64" cy="64" r="23" stroke="{W}" stroke-opacity=".7" stroke-width="3"/>
<path class="bh-flow" pathLength="100" stroke-dasharray="9 3" d="M28 55 A52 18 0 0 1 100 55" stroke="{W}" stroke-opacity=".9" stroke-width="7" transform="rotate(-18 64 64)" fill="none"/>
</g>"""

    if key == "comet":
        dust = "".join(
            f'<circle class="cmv-dust" style="--i:{n}" cx="{x}" cy="{y}" r="{r}" fill="{W}" fill-opacity=".7"/>'
            for n, (x, y, r) in enumerate([(40, 82, 3.4), (30, 94, 2.6), (52, 96, 2.2), (22, 74, 2)]))
        return f"""<g>
<g class="cmv-tail">
<path d="M74 44 L16 102 M80 54 L26 108 M68 34 L12 90" stroke="{W}" stroke-opacity=".5" stroke-width="7" stroke-linecap="round"/>
</g>
{dust}
<g class="cmv-head">
<circle cx="84" cy="42" r="27" stroke="{W}" stroke-opacity=".3" stroke-width="3"/>
<circle cx="84" cy="42" r="19" fill="{W}" fill-opacity=".96"/>
<circle cx="78" cy="36" r="6" fill="{W}"/>
<circle cx="90" cy="48" r="3.4" fill="{d}" fill-opacity=".18"/>
</g>
</g>"""

    if key == "mobius":
        R = 46.0
        V = [(64 + R * math.cos(math.radians(-90 + i * 120)),
              64 + R * math.sin(math.radians(-90 + i * 120))) for i in range(3)]
        segs = []
        for i in range(3):
            a, b = V[i], V[(i + 1) % 3]
            mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
            # внутрь треугольника
            cxv, cyv = 64 - mx, 64 - my
            ln = math.hypot(cxv, cyv) or 1
            nx, ny = cxv / ln, cyv / ln
            wa, wm, wb = 5.0, 17.0, 5.0
            p1 = f"{a[0]-nx*wa:.1f},{a[1]-ny*wa:.1f}"
            p2 = f"{mx-nx*wm:.1f},{my-ny*wm:.1f}"
            p3 = f"{b[0]-nx*wb:.1f},{b[1]-ny*wb:.1f}"
            p4 = f"{b[0]+nx*wb:.1f},{b[1]+ny*wb:.1f}"
            p5 = f"{mx+nx*wm:.1f},{my+ny*wm:.1f}"
            p6 = f"{a[0]+nx*wa:.1f},{a[1]+ny*wa:.1f}"
            op = [0.97, 0.66, 0.40][i]
            segs.append(f'<polygon class="mb-face" style="--i:{i}" points="{p1} {p2} {p3} {p4} {p5} {p6}" '
                        f'fill="{W}" fill-opacity="{op}"/>')
            # ребро ленты: у последнего сегмента переходит на другую сторону — это и есть перекрут
            e = (f'M{p6} L{p5} L{p4}' if i < 2 else f'M{p1} L{p5} L{p4}')
            segs.append(f'<path d="{e}" fill="none" stroke="{d}" stroke-opacity=".30" stroke-width="2.4"/>')
        return f"""<g>
{"".join(segs)}
<path class="mb-flow" pathLength="100" stroke-dasharray="7 7"
      d="M{V[0][0]:.1f} {V[0][1]:.1f} L{V[1][0]:.1f} {V[1][1]:.1f} L{V[2][0]:.1f} {V[2][1]:.1f} Z"
      fill="none" stroke="{W}" stroke-opacity=".85" stroke-width="3.4" stroke-linejoin="round"/>
</g>"""

    if key == "origami":
        return f"""<g>
<path d="M46 100 L18 114 L54 106 Z" fill="{W}" fill-opacity=".7"/>
<path class="orx-wing orx-wing--l" d="M62 62 L12 32 L52 88 Z" fill="{W}" fill-opacity=".96"/>
<path class="orx-wing orx-wing--r" d="M66 62 L116 32 L76 88 Z" fill="{W}" fill-opacity=".76"/>
<path d="M64 54 L82 102 L46 102 Z" fill="{W}" fill-opacity=".9"/>
<path d="M62 56 L84 20 L106 14 L88 34 Z" fill="{W}" fill-opacity=".96"/>
<path d="M62 56 L84 20" stroke="{d}" stroke-opacity=".2" stroke-width="3"/>
<path d="M64 54 V102" stroke="{d}" stroke-opacity=".18" stroke-width="3"/>
<circle cx="90" cy="26" r="2.8" fill="{d}" fill-opacity=".8"/>
</g>"""

    raise KeyError(key)


def build(style="a"):
    out = {}
    for key, ru, cat, tier, light, mid, deep in SPEC:
        defs, body = shell_a(f"a{key}", light, mid, deep, art(key, deep))
        out[key] = (ru, cat, svg_doc(128, 128, defs, body), tier)
    return out
