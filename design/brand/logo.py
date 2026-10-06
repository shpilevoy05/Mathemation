"""Вордмарк «МАТΣМАЦИЯ» по фирменному начертанию (референс владельца).

Единицы: прописная = 100 (верх 0, линия шрифта 100), штрих 20. Каждая буква —
многоугольник со своим радиусом на каждом углу; углы скругляются кривыми, так
что все буквы, включая Σ, построены одним способом и одной толщиной штриха.
Σ отличается только заливкой, пламя стоит на её верхней перекладине.
Эмблема — та же Σ с пламенем, вырезанная из слова.
"""
import math
from pathlib import Path

HERE = Path(__file__).parent
SW = 20       # штрих
R = 3.2       # базовое скругление углов


def rounded(points):
    """points: [(x, y, r)] → замкнутый путь со скруглёнными углами."""
    n = len(points)
    out = []
    for i in range(n):
        x0, y0, _ = points[i - 1]
        x1, y1, r = points[i]
        x2, y2, _ = points[(i + 1) % n]
        v1 = (x0 - x1, y0 - y1)
        v2 = (x2 - x1, y2 - y1)
        l1, l2 = math.hypot(*v1), math.hypot(*v2)
        r = min(r, l1 / 2.2, l2 / 2.2)
        a = (x1 + v1[0] / l1 * r, y1 + v1[1] / l1 * r)
        b = (x1 + v2[0] / l2 * r, y1 + v2[1] / l2 * r)
        out.append((a, (x1, y1), b))
    d = f"M{out[0][2][0]:.2f} {out[0][2][1]:.2f}"
    for i in range(1, n + 1):
        a, c, b = out[i % n]
        d += f" L{a[0]:.2f} {a[1]:.2f} Q{c[0]:.2f} {c[1]:.2f} {b[0]:.2f} {b[1]:.2f}"
    return d + " Z"


def P(pts, dx, default=R):
    return rounded([(x + dx, y, (p[0] if p else default)) for (x, y, *p) in pts])


# ── Буквы: функции возвращают (ширина, путь) ───────────────────────────────
def M(dx, tail=False):
    low = 159 if tail else 100
    t = SW
    pts = [(0, 0), (t + 1.7, 0), (70.6, 58), (122, 0), (142, 0), (142, 100), (122, 100),
           (122, 31), (70.6, 88.5), (t, 31), (t, low), (0, low)]
    return 142, P(pts, dx)


def A(dx):
    t = SW
    outer = [(0, 0, 13), (102, 0, 13), (102, 100), (102 - t, 100), (102 - t, 80), (t, 80), (t, 100), (0, 100)]
    hole = [(t, 19), (t, 61), (102 - t, 61), (102 - t, 19)]
    return 102, P(outer, dx) + " " + P(hole, dx, 4)


def T(dx):
    pts = [(0, 0), (102, 0), (102, 19), (61, 19), (61, 100), (41, 100), (41, 19), (0, 19)]
    return 102, P(pts, dx)


def SIGMA(dx):
    pts = [(0, 0), (81, 0), (81, 19), (29, 19), (72.4, 50, 3.6), (29, 81), (81, 81), (81, 100),
           (0, 100), (0, 77.2), (36.7, 50, 2), (0, 22.8)]
    return 81, P(pts, dx)


def TS(dx):  # Ц
    t = SW
    pts = [(0, 0), (t, 0), (t, 81, 6), (82, 81), (82, 0), (102, 0), (102, 81), (112, 81),
           (112, 100), (0, 100, 27)]
    return 112, P(pts, dx)


def I(dx):  # И
    t = SW
    pts = [(0, 0), (t, 0), (t, 69), (82, 0), (102, 0), (102, 100), (82, 100), (82, 31),
           (t, 100), (0, 100)]
    return 102, P(pts, dx)


def YA(dx, tail=False):  # Я
    t = SW
    low = 159 if tail else 100
    outer = [(0, 0, 22), (103, 0), (103, low), (83, low), (83, 80), (53, 80), (31, 100),
             (7, 100), (29, 80), (0, 80, 22)]
    hole = [(t, 19, 6), (t, 61, 6), (83, 61), (83, 19)]
    return 103, P(outer, dx) + " " + P(hole, dx, 4)


# (функция, зазор после буквы) — зазоры сняты с референса, оптический кернинг.
def layout(tails):
    return [(lambda dx: M(dx, tails), 15), (A, 9), (T, 8), (SIGMA, 10), (M, 15), (A, 15),
            (TS, 12), (I, 14), (lambda dx: YA(dx, tails), 0)]


# Пламя в собственной сетке 66×90, основание внизу; кончик загибается влево.
FLAME_OUTER = ("M24 0 C40 6 50 20 50 34 C54 30 56 24 55 17 C63 28 67 44 65 57 "
               "C62 77 49 90 33 90 C14 90 2 78 2 60 C2 46 10 36 18 30 "
               "C16 38 18 44 22 47 C20 34 27 17 24 0 Z")
FLAME_MID = ("M34 38 C41 47 51 55 49 68 C47 80 39 87 31 87 C20 87 12 79 13 68 "
             "C14 60 19 54 24 50 C24 56 26 60 30 62 C28 54 30 46 34 38 Z")
FLAME_CORE = "M31 61 C35 66 39 70 39 76 C39 82 35 86 31 86 C26 86 22 82 22 76 C22 71 27 66 31 61 Z"


def build(prefix, tails=True):
    x = 0
    ink, sigma = [], None
    for fn, gap in layout(tails):
        w, d = fn(x)
        if fn is SIGMA:
            sigma, sx, sw = d, x, w
        else:
            ink.append(d)
        x += w + gap
    width = x
    fw = 62
    scale = fw / 66
    fx = sx + (sw - fw) / 2 - 1
    fy = -90 * scale - 3
    low = 159 if tails else 100
    defs = (f'<defs><linearGradient id="{prefix}S" x1="0" y1="0" x2="1" y2="0">'
            f'<stop offset="0" stop-color="#3B3FF5"/><stop offset="1" stop-color="#6E9CE6"/></linearGradient>'
            f'<linearGradient id="{prefix}F1" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#E5241E"/>'
            f'<stop offset=".55" stop-color="#FF5B1E"/><stop offset="1" stop-color="#FF9C22"/></linearGradient>'
            f'<linearGradient id="{prefix}F2" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FF8A1E"/>'
            f'<stop offset="1" stop-color="#FFE03A"/></linearGradient>'
            f'<linearGradient id="{prefix}F3" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FFEE8A"/>'
            f'<stop offset="1" stop-color="#FFFBE2"/></linearGradient></defs>')
    flame = (f'<g transform="translate({fx:.2f} {fy:.2f}) scale({scale:.4f})">'
             f'<path fill="url(#{prefix}F1)" d="{FLAME_OUTER}"/><path fill="url(#{prefix}F2)" d="{FLAME_MID}"/>'
             f'<path fill="url(#{prefix}F3)" d="{FLAME_CORE}"/></g>')
    ink_el = f'<path fill="currentColor" fill-rule="evenodd" d="{" ".join(ink)}"/>'
    sig_el = f'<path fill="url(#{prefix}S)" d="{sigma}"/>'
    top = fy - 1
    vb_word = f"-1 {top:.2f} {width + 2:.2f} {low - top + 1:.2f}"
    vb_mark = f"{sx - 8:.2f} {top:.2f} {sw + 16:.2f} {100 - top + 1:.2f}"
    return defs, ink_el, sig_el, flame, vb_word, vb_mark


def svg(kind, prefix, tails=True):
    defs, ink, sig, flame, vbw, vbm = build(prefix, tails)
    if kind == "word":
        return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vbw}">{defs}{ink}{sig}{flame}</svg>'
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vbm}">{defs}{sig}{flame}</svg>'
