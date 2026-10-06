"""Доработки аватаров: ёж, космос с созвездиями лиг, и пять переделок."""
import math
from pathlib import Path

from avatars import frame
from avatars2 import bg_grad, lin, rad
from avatars3 import stars
from concepts import CONST
import avatars3
import avatars4

HERE = Path(__file__).parent


def constellations(items):
    """items: [(league, x, y, scale)] — бледные созвездия лиг на фоне."""
    out = ""
    for key, ox, oy, s in items:
        for chain in CONST[key]:
            pts = [(ox + x * s, oy + y * s) for x, y in chain]
            out += ('<path d="M' + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts) + '" fill="none" stroke="#CFE0FF" stroke-opacity=".38" stroke-width=".8"/>'
                    + "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="1.3" fill="#fff" opacity=".85"/>' for x, y in pts))
    return out


def with_overlay(svg, overlay):
    """Вставить созвездия под персонажа: сразу после фона внутри маски."""
    marker = 'clip-path="url(#'
    i = svg.index(marker)
    j = svg.index(">", i) + 1
    return svg[:j] + overlay + svg[j:]


# ── Ёж: колючее тело и маленькое светлое пузико ───────────────────────────────
def hedgehog():
    svg = avatars3.hedgehog()
    old = '<path d="M64 96 C88 96 104 110 106 128 H22 C24 110 40 96 64 96 Z" fill="#F0D3AC"/>'
    assert old in svg
    body = ('<path d="M64 92 C92 92 108 108 112 130 H16 C20 108 36 92 64 92 Z" fill="url(#hhback)"/>'
            '<g fill="#5A3A22">' + "".join(
                f'<path d="M{x} {y} L{x + 5} {y - 9} L{x + 10} {y} Z"/>' for x, y in ((20, 118), (30, 108), (88, 108), (98, 118))) + '</g>')
    belly = '<ellipse cx="64" cy="108" rx="19" ry="13" fill="url(#hhface)"/>'
    svg = svg.replace(old, body)
    marker = '<path d="M64 46 C84 46'
    return svg.replace(marker, belly + marker, 1)


def astronaut():
    return with_overlay(avatars3.astronaut(), constellations([("sigma", 12, 18, .2), ("delta", 14, 82, .16)]))


def comet():
    return with_overlay(avatars4.comet(), constellations([("omega", 18, 16, .2), ("beta", 92, 86, .17)]))


def blackhole():
    return with_overlay(avatars4.blackhole(), constellations([("alpha", 16, 14, .18), ("gamma", 94, 92, .16)]))


# ── Кит: в профиль, с поднятым хвостом, в толще воды ──────────────────────────
def whale():
    u = "wl"
    defs = (bg_grad(u, "#8FE3FF", "#1F7FC8", "#062A5C", ".5", ".15")
            + lin(f"{u}body", [(0, "#7CC4FF"), (.5, "#3A82DA"), (1, "#1F4E9E")], "0", "1")
            + lin(f"{u}belly", [(0, "#F4FBFF"), (1, "#BFDDF6")])
            + lin(f"{u}ray", [(0, "#FFFFFF66"), (1, "#FFFFFF00")]))
    rays = "".join(f'<path d="M{x} -4 L{x + 14} -4 L{x + 30} 128 L{x + 6} 128 Z" fill="url(#{u}ray)"/>' for x in (18, 54, 88))
    bubbles = "".join(f'<circle cx="{x}" cy="{y}" r="{r}" fill="#fff" fill-opacity=".15" stroke="#fff" stroke-opacity=".7" stroke-width=".9"/>' for x, y, r in ((98, 30, 4), (106, 20, 2.6), (92, 18, 1.8), (20, 104, 3), (28, 112, 1.8)))
    grooves = "".join(f'<path d="M{30 + i * 8} {88 + i * .6:.1f} Q{34 + i * 8} {94 + i * .4:.1f} {38 + i * 8} {96:.1f}" fill="none" stroke="#9CC4E6" stroke-width="1.1"/>' for i in range(6))
    body = f"""{rays}{bubbles}
<g transform="translate(8 12) scale(.86)"><path d="M14 74 C14 52 36 40 60 40 C84 40 98 52 102 64 C106 54 112 46 122 42 C120 54 117 62 110 68 C117 70 122 78 124 86 C115 84 108 80 102 78 C96 94 80 102 58 102 C32 102 14 92 14 74 Z" fill="url(#{u}body)"/>
<path d="M18 82 C26 94 42 100 60 100 C80 100 94 92 100 80 C88 88 74 92 58 92 C42 92 28 90 18 82 Z" fill="url(#{u}belly)"/>
{grooves}
<path d="M54 86 C58 96 66 102 76 100 C70 96 64 90 60 82 Z" fill="#2A63B8"/>
<path d="M24 58 C32 48 46 44 60 44" fill="none" stroke="#fff" stroke-opacity=".5" stroke-width="3" stroke-linecap="round"/>
<circle cx="38" cy="66" r="5.2" fill="#0E1F44"/><circle cx="36.3" cy="64.2" r="1.9" fill="#fff"/><circle cx="39.8" cy="68" r=".8" fill="#fff" opacity=".8"/>
<ellipse cx="34" cy="78" rx="5" ry="2.8" fill="#FF9BB0" opacity=".45"/>
<path d="M18 76 Q26 84 36 82" fill="none" stroke="#0E1F44" stroke-width="1.8" stroke-linecap="round"/>
<g fill="#E6F7FF"><path d="M40 36 C36 28 30 24 24 24 C30 22 36 24 40 30 Z"/><path d="M44 36 C46 26 52 20 58 18 C54 24 50 30 47 36 Z"/>
<circle cx="24" cy="23" r="2.4"/><circle cx="58" cy="17" r="2.4"/><circle cx="42" cy="22" r="2"/></g></g>"""
    return frame(u, defs, body)


# ── Ниндзя: большеглазый, закат, луна и сакура ────────────────────────────────
def ninja():
    u = "nn"
    petals = "".join(f'<path d="M{x} {y} q3 -4 6 0 q-3 4 -6 0 Z" fill="#FFC2D6" transform="rotate({a} {x} {y})" opacity=".9"/>' for x, y, a in ((20, 36, 20), (104, 30, -30), (110, 84, 40), (16, 92, -10), (30, 20, 60)))
    defs = (bg_grad(u, "#FFD6A8", "#F06A4A", "#5E1638", ".5", ".2")
            + rad(f"{u}moon", [(0, "#FFF6DA"), (1, "#FFD98A")], cx=".4", cy=".35", r=".7")
            + lin(f"{u}cloth", [(0, "#3E4766"), (1, "#151A2C")], ".6", "1", ".3")
            + lin(f"{u}skin", [(0, "#FFE6CC"), (1, "#F5C79E")])
            + lin(f"{u}band", [(0, "#FF5A5A"), (1, "#B0172E")]))
    body = f"""
<circle cx="64" cy="54" r="34" fill="url(#{u}moon)" opacity=".9"/>
{petals}
<path d="M64 100 C90 100 108 112 112 130 H16 C20 112 38 100 64 100 Z" fill="url(#{u}cloth)"/>
<path d="M50 102 L64 116 L78 102" fill="none" stroke="#0B0E1A" stroke-width="2"/>
<path d="M64 30 C90 30 104 48 104 70 C104 92 86 106 64 106 C42 106 24 92 24 70 C24 48 38 30 64 30 Z" fill="url(#{u}cloth)"/>
<path d="M28 60 C44 52 84 52 100 60 L100 76 C84 82 44 82 28 76 Z" fill="url(#{u}skin)"/>
<path d="M26 48 C42 40 86 40 102 48 L102 56 C86 50 42 50 26 56 Z" fill="url(#{u}band)"/>
<path d="M100 50 C110 46 118 38 122 30 C122 42 114 52 104 56 Z M100 54 C112 58 120 60 126 56 C120 66 110 66 102 60 Z" fill="url(#{u}band)"/>
<circle cx="64" cy="50.5" r="4.2" fill="#FFD43B" stroke="#A87705" stroke-width=".8"/>
<circle cx="50" cy="67" r="6.8" fill="#fff"/><circle cx="78" cy="67" r="6.8" fill="#fff"/>
<circle cx="51" cy="68" r="4.4" fill="#1B120E"/><circle cx="77" cy="68" r="4.4" fill="#1B120E"/>
<circle cx="49.6" cy="66.4" r="1.6" fill="#fff"/><circle cx="75.6" cy="66.4" r="1.6" fill="#fff"/>
<path d="M41 59 L58 62 M87 59 L70 62" stroke="#151A2C" stroke-width="2.6" stroke-linecap="round"/>
<path d="M44 76 C52 80 76 80 84 76" fill="none" stroke="#0B0E1A" stroke-opacity=".35" stroke-width="1.4"/>"""
    return frame(u, defs, body)


# ── Волшебник: добродушный, борода-облако, луна и искра ───────────────────────
def wizard():
    u = "wd"
    curl = lambda x, y, r: f'<circle cx="{x}" cy="{y}" r="{r}" fill="url(#{u}beard)"/>'
    beard = (f'<path d="M40 78 C40 92 46 104 54 112 C58 118 62 122 64 124 C66 122 70 118 74 112 C82 104 88 92 88 78 C84 86 76 90 64 90 C52 90 44 86 40 78 Z" fill="url(#{u}beard)"/>'
             + "".join(f'<path d="M{x} {y} q3 -4 6 0 q-1 4 -4 3" fill="none" stroke="#C9D0E2" stroke-width="1.2" stroke-linecap="round"/>' for x, y in ((48, 96), (60, 100), (72, 96), (54, 108), (66, 112))))
    defs = (bg_grad(u, "#B7A6FF", "#4B3AC2", "#140E48", ".5", ".3")
            + lin(f"{u}hat", [(0, "#8A7BFF"), (1, "#3A2AA8")], "1", "1")
            + lin(f"{u}brim", [(0, "#6A5BE8"), (1, "#2A1F7A")])
            + rad(f"{u}skin", [(0, "#FFE9D4"), (1, "#F4C6A0")], cy=".4")
            + rad(f"{u}beard", [(0, "#FFFFFF"), (1, "#DCE2EF")], cx=".4", cy=".35", r=".7")
            + rad(f"{u}moon", [(0, "#FFF6DA"), (1, "#FFD98A")]))
    hat_stars = "".join(f'<path d="M{x} {y - 3} L{x + .9} {y - .9} L{x + 3} {y} L{x + .9} {y + .9} L{x} {y + 3} L{x - .9} {y + .9} L{x - 3} {y} L{x - .9} {y - .9} Z" fill="#FFE27A"/>' for x, y in ((58, 32), (70, 22), (66, 40)))
    body = f"""{stars("wd", 16, (8, 120, 8, 70))}
<path d="M98 22 A13 13 0 1 0 110 38 A10 10 0 1 1 98 22 Z" fill="url(#{u}moon)"/>
<path d="M64 102 C88 102 104 114 108 130 H20 C24 114 40 102 64 102 Z" fill="#5A43C8"/>
<circle cx="64" cy="70" r="24" fill="url(#{u}skin)"/>
<circle cx="40" cy="72" r="6" fill="url(#{u}skin)"/><circle cx="88" cy="72" r="6" fill="url(#{u}skin)"/>
{beard}
<path d="M64 84 C58 78 48 78 42 84 C48 82 54 84 58 88 Z M64 84 C70 78 80 78 86 84 C80 82 74 84 70 88 Z" fill="url(#{u}beard)" stroke="#C9D0E2" stroke-width=".6"/>
<ellipse cx="64" cy="78" rx="5" ry="4" fill="#F2A98A"/>
<circle cx="54" cy="70" r="3.4" fill="#1B120E"/><circle cx="74" cy="70" r="3.4" fill="#1B120E"/>
<circle cx="53" cy="68.8" r="1.2" fill="#fff"/><circle cx="73" cy="68.8" r="1.2" fill="#fff"/>
<path d="M47 63 Q54 58 60 63 M81 63 Q74 58 68 63" fill="none" stroke="#FFFFFF" stroke-width="4" stroke-linecap="round"/>
<ellipse cx="46" cy="78" rx="4" ry="2.4" fill="#FF8C8C" opacity=".4"/><ellipse cx="82" cy="78" rx="4" ry="2.4" fill="#FF8C8C" opacity=".4"/>
<path d="M28 54 C42 48 86 48 100 54 C98 60 88 62 64 62 C40 62 30 60 28 54 Z" fill="url(#{u}brim)"/>
<path d="M38 54 C44 38 54 20 72 6 C70 18 76 34 90 54 C72 58 56 58 38 54 Z" fill="url(#{u}hat)"/>
<path d="M40 52 C56 56 72 56 88 52 L88 47 C72 51 56 51 40 47 Z" fill="#FFD43B"/>
{hat_stars}
<g transform="translate(100 98)"><path d="M0 -8 L2 -2 L8 0 L2 2 L0 8 L-2 2 L-8 0 L-2 -2 Z" fill="#FFE27A"/><circle r="10" fill="#FFE27A" opacity=".2"/></g>
<path d="M90 120 L99 99" stroke="#8A5A2A" stroke-width="3" stroke-linecap="round"/>"""
    return frame(u, defs, body)


# ── Дракон: дружелюбный дракончик ─────────────────────────────────────────────
def dragon():
    u = "dr"
    defs = (bg_grad(u, "#FFE0B8", "#F59A4A", "#7A2E12", ".5", ".3")
            + rad(f"{u}skin", [(0, "#8BF0BC"), (.6, "#2FB57F"), (1, "#0F6A48")], cy=".38", r=".7")
            + lin(f"{u}belly", [(0, "#FFF4C2"), (1, "#F4CF6A")])
            + lin(f"{u}horn", [(0, "#FFF6E2"), (1, "#E3BC80")])
            + lin(f"{u}wing", [(0, "#46C690"), (1, "#137A52")], "0", "1")
            + rad(f"{u}smoke", [(0, "#FFFFFF"), (1, "#E6ECF5")]))
    body = f"""
<path d="M24 92 C10 80 8 58 16 40 C22 52 30 60 40 66 Z M104 92 C118 80 120 58 112 40 C106 52 98 60 88 66 Z" fill="url(#{u}wing)"/>
<path d="M18 48 L28 60 M110 48 L100 60" stroke="#0F6A48" stroke-width="1.4"/>
<path d="M64 98 C88 98 104 112 106 130 H22 C24 112 40 98 64 98 Z" fill="url(#{u}skin)"/>
<path d="M64 102 C74 102 80 112 80 130 H48 C48 112 54 102 64 102 Z" fill="url(#{u}belly)"/>
<path d="M50 110 H78 M49 118 H79" stroke="#D9A83A" stroke-width="1.2"/>
<path d="M44 40 C42 30 44 22 50 16 C51 26 54 32 58 36 Z M84 40 C86 30 84 22 78 16 C77 26 74 32 70 36 Z" fill="url(#{u}horn)"/>
<path d="M64 32 C88 32 102 48 102 68 C102 90 86 102 64 102 C42 102 26 90 26 68 C26 48 40 32 64 32 Z" fill="url(#{u}skin)"/>
<path d="M60 32 L64 26 L68 32 Z M54 34 L57 28 L60 33 Z M68 33 L71 28 L74 34 Z" fill="#FFB347"/>
<circle cx="50" cy="64" r="9" fill="#fff"/><circle cx="78" cy="64" r="9" fill="#fff"/>
<circle cx="51" cy="65" r="6" fill="#2A1A10"/><circle cx="77" cy="65" r="6" fill="#2A1A10"/>
<circle cx="49" cy="62.4" r="2.2" fill="#fff"/><circle cx="75" cy="62.4" r="2.2" fill="#fff"/><circle cx="53" cy="67.6" r="1" fill="#fff" opacity=".8"/><circle cx="79" cy="67.6" r="1" fill="#fff" opacity=".8"/>
<path d="M44 82 C50 76 78 76 84 82 C84 94 76 100 64 100 C52 100 44 94 44 82 Z" fill="#63D6A0"/>
<ellipse cx="57" cy="84" rx="2.2" ry="1.5" fill="#0F6A48"/><ellipse cx="71" cy="84" rx="2.2" ry="1.5" fill="#0F6A48"/>
<path d="M55 92 Q64 98 73 92" fill="none" stroke="#0F6A48" stroke-width="1.8" stroke-linecap="round"/>
<path d="M66 94.2 L67.5 98 L69 94.4 Z" fill="#fff"/>
<ellipse cx="40" cy="78" rx="5" ry="3" fill="#FF8C8C" opacity=".45"/><ellipse cx="88" cy="78" rx="5" ry="3" fill="#FF8C8C" opacity=".45"/>
"""
    return frame(u, defs, body)


# ── Оригами: журавлик из цветной бумаги ───────────────────────────────────────
def origami():
    u = "og"
    grid = "".join(f'<path d="M{x} 0 V128" stroke="#C9B89A" stroke-opacity=".35" stroke-width=".6"/>' for x in range(8, 128, 12)) + \
           "".join(f'<path d="M0 {y} H128" stroke="#C9B89A" stroke-opacity=".35" stroke-width=".6"/>' for y in range(8, 128, 12))
    defs = (bg_grad(u, "#FFF8EC", "#F2E4C8", "#C9AE82", ".5", ".35")
            + lin(f"{u}a", [(0, "#FF8F7A"), (1, "#F2553F")], "1", "1")
            + lin(f"{u}b", [(0, "#E2442F"), (1, "#B32A1C")], "1", "1")
            + lin(f"{u}c", [(0, "#FFB3A3"), (1, "#FF7F68")], "1", "1"))
    body = f"""{grid}
<ellipse cx="64" cy="112" rx="34" ry="5" fill="#000" opacity=".12"/>
<g class="orx-wing orx-wing--l"><path d="M64 70 L10 22 L50 64 Z" fill="url(#{u}c)"/><path d="M64 70 L10 22 L34 70 Z" fill="url(#{u}b)"/><path d="M10 22 L50 64" stroke="#fff" stroke-opacity=".5" stroke-width=".8"/></g>
<g class="orx-wing orx-wing--r"><path d="M64 70 L118 22 L78 64 Z" fill="url(#{u}c)"/><path d="M64 70 L118 22 L94 70 Z" fill="url(#{u}b)"/><path d="M118 22 L78 64" stroke="#fff" stroke-opacity=".5" stroke-width=".8"/></g>
<path d="M64 54 L82 80 L64 104 L46 80 Z" fill="url(#{u}a)"/>
<path d="M64 54 L64 104 L46 80 Z" fill="url(#{u}b)" opacity=".85"/>
<path d="M46 80 L20 98 L30 102 L52 88 Z" fill="url(#{u}b)"/>
<path d="M82 80 L102 46 L108 50 L88 84 Z" fill="url(#{u}a)"/>
<path d="M102 46 L112 40 L108 50 Z" fill="#B32A1C"/>
<path d="M64 54 V104" stroke="#fff" stroke-opacity=".55" stroke-width=".9"/>"""
    return frame(u, defs, body)


BATCH = {"hedgehog": hedgehog, "astronaut": astronaut, "comet": comet, "blackhole": blackhole,
         "whale": whale, "ninja": ninja, "wizard": wizard, "dragon": dragon, "origami": origami}
