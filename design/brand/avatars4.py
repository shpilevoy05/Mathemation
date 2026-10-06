"""Аватары нового стиля — партия 3, анимированные.

Классы анимируемых элементов совпадают с прежними рисунками: cosmetics.css
(tsr-*, frc-tri, cr-*, orx-wing*, mb-*, cmv-*, bh-*) подхватывает их без
изменений. Центр вращения у аватаров — 64px (transform-box: view-box).
"""
import math
from pathlib import Path

from avatars import frame
from avatars2 import bg_grad, lin, rad
from avatars3 import stars

HERE = Path(__file__).parent


def sq(cx, cy, r, rot=0):
    return [(cx + r * math.cos(math.radians(rot + 45 + i * 90)), cy + r * math.sin(math.radians(rot + 45 + i * 90))) for i in range(4)]


def d_of(p):
    return "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in p) + " Z"


def tesseract():
    u = "ts"
    defs = (bg_grad(u, "#5B5FFF", "#1E1A8C", "#08062E", ".5", ".45")
            + lin(f"{u}edge", [(0, "#9BF2FF"), (1, "#8A6BFF")], "1", "1")
            + rad(f"{u}core", [(0, "#FFFFFF"), (.4, "#9BE7FF"), (1, "#9BE7FF00")], r=".5"))
    outer, inner = sq(64, 64, 40), sq(64, 64, 21, 45)
    links = "".join(f'<circle class="tsr-link" style="--i:{i}" cx="{64 + 30 * math.cos(math.radians(i * 90)):.1f}" cy="{64 + 30 * math.sin(math.radians(i * 90)):.1f}" r="3.4" fill="#9BF2FF"/>' for i in range(4))
    body = (stars("ts", 22) + f'<circle cx="64" cy="64" r="34" fill="url(#{u}core)" opacity=".55"/>'
            + f'<g class="tsr-outer"><path d="{d_of(outer)}" fill="#8A6BFF" fill-opacity=".14" stroke="url(#{u}edge)" stroke-width="4" stroke-linejoin="round"/>'
            + "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="#fff"/>' for x, y in outer) + '</g>'
            + f'<g class="tsr-inner"><path d="{d_of(inner)}" fill="#9BF2FF" fill-opacity=".22" stroke="#fff" stroke-width="3" stroke-linejoin="round"/>'
            + "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.4" fill="#9BF2FF"/>' for x, y in inner) + '</g>'
            + f'<circle cx="64" cy="64" r="30" fill="none" stroke="#9BF2FF" stroke-opacity=".35" stroke-width="1" stroke-dasharray="2 4"/>' + links
            + f'<circle cx="64" cy="64" r="5" fill="#fff"/>')
    return frame(u, defs, body)


def fractal():
    u = "fr"
    tris = []
    def sier(x, y, s, depth):
        if depth == 0:
            tris.append((x, y, s)); return
        h = s / 2
        sier(x, y, h, depth - 1); sier(x + h / 2, y + h * .866, h, depth - 1); sier(x - h / 2, y + h * .866, h, depth - 1)
    sier(64, 22, 84, 2)
    defs = (bg_grad(u, "#FF8AD8", "#9A1F8A", "#2A0630", ".5", ".4")
            + lin(f"{u}tri", [(0, "#FFF0FA"), (.5, "#FF7ACB"), (1, "#C21F86")], "0", "1"))
    body = stars("fr", 16)
    for i, (x, y, s) in enumerate(tris):
        p = [(x, y), (x + s / 2, y + s * .866), (x - s / 2, y + s * .866)]
        body += f'<path class="frc-tri" style="--i:{i}" d="{d_of(p)}" fill="url(#{u}tri)" stroke="#FFE3F6" stroke-width="1" stroke-linejoin="round"/>'
    body += f'<path d="{d_of([(64, 20), (108, 96), (20, 96)])}" fill="none" stroke="#FFD6F2" stroke-opacity=".5" stroke-width="1.4"/>'
    return frame(u, defs, body)


def crystal():
    u = "cs"
    top, left, right, bottom, mid_l, mid_r = (64, 18), (30, 50), (98, 50), (64, 112), (46, 50), (82, 50)
    facets = [[top, mid_l, left], [top, mid_r, mid_l], [top, right, mid_r], [left, mid_l, bottom], [mid_l, mid_r, bottom], [mid_r, right, bottom]]
    shades = ["#FFE0FF", "#FFFFFF", "#F2B6FF", "#C27BFF", "#E3A6FF", "#8A4BE0"]
    defs = (bg_grad(u, "#E2B8FF", "#7A3FD6", "#200A52", ".5", ".4")
            + rad(f"{u}glow", [(0, "#F2C8FFAA"), (1, "#F2C8FF00")]))
    body = stars("cs", 14) + f'<circle cx="64" cy="64" r="52" fill="url(#{u}glow)"/><ellipse cx="64" cy="116" rx="28" ry="4" fill="#000" opacity=".3"/>'
    for i, f in enumerate(facets):
        cls = ' class="cr-facet"' if i < 5 else ""
        body += f'<path{cls} style="--i:{i}" d="{d_of(f)}" fill="{shades[i]}" stroke="#5A1FA8" stroke-opacity=".45" stroke-width="1" stroke-linejoin="round"/>'
    body += ('<g class="cr-shine"><path d="M92 26 L94.5 33 L101 35.5 L94.5 38 L92 45 L89.5 38 L83 35.5 L89.5 33 Z" fill="#fff"/></g>'
             '<path d="M46 50 L64 20" stroke="#fff" stroke-opacity=".8" stroke-width="1.4" stroke-linecap="round"/>')
    return frame(u, defs, body)


def origami():
    u = "or"
    defs = (bg_grad(u, "#B8F3E6", "#2BA68C", "#0A4A40")
            + lin(f"{u}pa", [(0, "#FFFFFF"), (1, "#E3ECF5")], "1", "1")
            + lin(f"{u}pb", [(0, "#DCE6F2"), (1, "#AFC0D6")], "1", "1")
            + lin(f"{u}pc", [(0, "#FF8A7A"), (1, "#E0453A")], "1", "1"))
    body = (f'<g opacity=".25" fill="#fff"><circle cx="20" cy="40" r="9"/><circle cx="30" cy="36" r="11"/><circle cx="104" cy="96" r="8"/><circle cx="96" cy="100" r="10"/></g>'
            f'<g class="orx-wing orx-wing--l"><path d="M64.0 70.0 L4.2 23.2 L51.0 59.6 Z" fill="url(#{u}pa)"/><path d="M64.0 70.0 L4.2 23.2 L32.8 64.8 Z" fill="url(#{u}pb)"/></g>'
            f'<g class="orx-wing orx-wing--r"><path d="M64.0 70.0 L123.8 23.2 L77.0 59.6 Z" fill="url(#{u}pa)"/><path d="M64.0 70.0 L123.8 23.2 L95.2 64.8 Z" fill="url(#{u}pb)"/></g>'
            f'<path d="M64.0 54.4 L82.2 80.4 L64.0 109.0 L45.8 80.4 Z" fill="url(#{u}pa)" stroke="#8EA3BF" stroke-width="1"/>'
            f'<path d="M64.0 54.4 L64.0 109.0 L45.8 80.4 Z" fill="url(#{u}pb)"/>'
            f'<path d="M45.8 80.4 L19.8 98.6 L32.8 103.8 L53.6 88.2 Z" fill="url(#{u}pb)"/>'
            f'<path d="M82.2 80.4 L105.6 49.2 L110.8 54.4 L90.0 85.6 Z" fill="url(#{u}pa)"/><path d="M105.6 49.2 L116.0 44.0 L110.8 54.4 Z" fill="url(#{u}pc)"/>'
            f'<path d="M64.0 54.4 L64.0 109.0" stroke="#8EA3BF" stroke-width="1"/>')
    return frame(u, defs, body)


def mobius():
    u = "mb"
    d = "M64 64 C74 46 104 44 104 64 C104 84 74 82 64 64 C54 46 24 44 24 64 C24 84 54 82 64 64 Z"
    defs = (bg_grad(u, "#9CE8FF", "#2E6FE0", "#0B1A5C", ".5", ".4")
            + lin(f"{u}band", [(0, "#FFFFFF"), (.5, "#7FD8FF"), (1, "#3A6BFF")], "1", "0")
            + lin(f"{u}band2", [(0, "#3A6BFF"), (.5, "#7FD8FF"), (1, "#FFFFFF")], "1", "0"))
    faces = "".join(f'<circle class="mb-face" style="--i:{i}" cx="{x}" cy="{y}" r="4" fill="#fff"/>' for i, (x, y) in enumerate(((34, 56), (64, 64), (94, 72))))
    body = (stars("mb", 14)
            + f'<path d="{d}" fill="none" stroke="#0B1A5C" stroke-opacity=".4" stroke-width="18" transform="translate(1.5 3)"/>'
            + f'<path d="{d}" fill="none" stroke="url(#{u}band)" stroke-width="16" stroke-linejoin="round"/>'
            + f'<path d="M64 64 C54 46 24 44 24 64" fill="none" stroke="url(#{u}band2)" stroke-width="16"/>'
            + f'<path class="mb-flow" d="{d}" pathLength="100" fill="none" stroke="#fff" stroke-width="2.4" stroke-dasharray="10 4" stroke-linecap="round"/>'
            + faces)
    return frame(u, defs, body)


def comet():
    u = "cm"
    defs = (bg_grad(u, "#3B4BB8", "#141A5C", "#05071E", ".6", ".35")
            + lin(f"{u}tail", [(0, "#9BE7FF00"), (.55, "#9BE7FF99"), (1, "#FFFFFF")], "1", "0", "0", "1")
            + rad(f"{u}head", [(0, "#FFFFFF"), (.45, "#BDF1FF"), (1, "#3AB8F0")], cx=".4", cy=".35", r=".6"))
    dust = "".join(f'<circle class="cmv-dust" style="--i:{i}" cx="{x}" cy="{y}" r="{r}" fill="#BDF1FF"/>' for i, (x, y, r) in enumerate(((40, 82, 1.8), (52, 92, 1.3), (34, 70, 1.2), (60, 100, 1))))
    body = (stars("cm", 30)
            + f'<path class="cmv-tail" d="M8 120 C36 102 60 82 80 50 L98 62 C74 90 44 110 8 120 Z" fill="url(#{u}tail)"/>'
            + dust
            + f'<g class="cmv-head"><circle cx="88" cy="54" r="22" fill="#9BE7FF" opacity=".22"/><circle cx="88" cy="54" r="13" fill="url(#{u}head)"/>'
              '<circle cx="83.5" cy="49.5" r="3.6" fill="#fff"/></g>')
    return frame(u, defs, body)


def blackhole():
    u = "bh"
    defs = (bg_grad(u, "#4A2A8C", "#120A33", "#020108", ".5", ".5")
            + lin(f"{u}disc", [(0, "#FF5A1F"), (.35, "#FFC14D"), (.5, "#FFFFFF"), (.65, "#FFC14D"), (1, "#FF5A1F")], "1", "0")
            + rad(f"{u}lens", [(0, "#FFD27A00"), (.7, "#FFD27A00"), (.85, "#FFD27A88"), (1, "#FFD27A00")], r=".5"))
    flows = "".join(f'<ellipse class="bh-flow" cx="64" cy="66" rx="{rx}" ry="{ry}" pathLength="100" fill="none" stroke="{c}" stroke-width="{w}" stroke-dasharray="6 6" transform="rotate(-12 64 66)"/>'
                    for rx, ry, c, w in ((54, 12, "#FFE3A0", 1.2), (46, 10, "#FFFFFF", 1), (38, 8, "#FFB14D", 1.2)))
    st = "".join(f'<circle class="bh-star" style="--i:{i}" cx="{x}" cy="{y}" r="1.4" fill="#fff"/>' for i, (x, y) in enumerate(((22, 28), (104, 24), (110, 100), (18, 98))))
    body = (stars("bh", 20) + st
            + f'<circle cx="64" cy="64" r="34" fill="url(#{u}lens)"/>'
            + f'<ellipse class="bh-disc" cx="64" cy="66" rx="56" ry="14" fill="none" stroke="url(#{u}disc)" stroke-width="7" transform="rotate(-12 64 66)"/>'
            + flows
            + '<circle class="bh-core" cx="64" cy="64" r="20" fill="none" stroke="#FFE3A0" stroke-width="2.4" opacity=".9"/>'
            + '<circle class="bh-core" cx="64" cy="64" r="17" fill="#000"/>'
            + f'<path d="M14 70 A56 14 0 0 0 114 62" transform="rotate(-12 64 66)" fill="none" stroke="url(#{u}disc)" stroke-width="7" opacity="0"/>'
            + f'<path d="M30 74 C44 82 84 80 98 70" fill="none" stroke="url(#{u}disc)" stroke-width="6" stroke-linecap="round"/>')
    return frame(u, defs, body)


BATCH = {"tesseract": tesseract, "fractal": fractal, "crystal": crystal, "origami": origami,
         "mobius": mobius, "comet": comet, "blackhole": blackhole}
