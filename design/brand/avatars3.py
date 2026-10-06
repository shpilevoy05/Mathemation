"""Аватары нового стиля — партия 2: ёж, кит, робот, космонавт, ниндзя, волшебник, дракон, икосаэдр, спираль."""
import math
import random
from pathlib import Path

from avatars import frame
from avatars2 import bg_grad, lin, rad

HERE = Path(__file__).parent


def stars(seed, n, area=(8, 120, 8, 120), op=(.3, .9)):
    r = random.Random(seed)
    return "".join(f'<circle cx="{r.uniform(area[0], area[1]):.1f}" cy="{r.uniform(area[2], area[3]):.1f}" r="{r.uniform(.4, 1.3):.2f}" fill="#fff" opacity="{r.uniform(*op):.2f}"/>' for _ in range(n))


def eyes(lx, rx, y, r=5.5, iris=None, u=""):
    fill = f'url(#{iris})' if iris else "#1B120E"
    out = f'<circle cx="{lx}" cy="{y}" r="{r}" fill="{fill}"/><circle cx="{rx}" cy="{y}" r="{r}" fill="{fill}"/>'
    if iris:
        out += f'<circle cx="{lx + .3}" cy="{y + .4}" r="{r * .5:.1f}" fill="#120B08"/><circle cx="{rx - .3}" cy="{y + .4}" r="{r * .5:.1f}" fill="#120B08"/>'
    out += (f'<circle cx="{lx - r * .35:.1f}" cy="{y - r * .4:.1f}" r="{r * .34:.1f}" fill="#fff"/><circle cx="{rx - r * .35:.1f}" cy="{y - r * .4:.1f}" r="{r * .34:.1f}" fill="#fff"/>'
            f'<circle cx="{lx + r * .4:.1f}" cy="{y + r * .45:.1f}" r="{r * .16:.1f}" fill="#fff" opacity=".8"/><circle cx="{rx + r * .4:.1f}" cy="{y + r * .45:.1f}" r="{r * .16:.1f}" fill="#fff" opacity=".8"/>')
    return out


def hedgehog():
    u = "hh"
    spikes = ""
    for ring, (rad_, ln, col) in enumerate(((44, 20, "#5A3A22"), (40, 16, "#7A5232"))):
        for i in range(26):
            a = math.radians(-200 + i * 220 / 25)
            b1 = math.radians(math.degrees(a) - 5); b2 = math.radians(math.degrees(a) + 5)
            x0, y0 = 64 + rad_ * math.cos(b1), 70 + rad_ * math.sin(b1)
            x1, y1 = 64 + rad_ * math.cos(b2), 70 + rad_ * math.sin(b2)
            xt, yt = 64 + (rad_ + ln) * math.cos(a + .02 * ring), 70 + (rad_ + ln) * math.sin(a + .02 * ring)
            spikes += f'<path d="M{x0:.1f} {y0:.1f} L{xt:.1f} {yt:.1f} L{x1:.1f} {y1:.1f} Z" fill="{col}"/>'
    defs = (bg_grad(u, "#D7F7A8", "#6DBB3C", "#245A12")
            + rad(f"{u}back", [(0, "#8C6440"), (1, "#4A2E18")], cy=".4", r=".65")
            + rad(f"{u}face", [(0, "#FFF1DC"), (.7, "#F0D3AC"), (1, "#D9B080")], cx=".5", cy=".4", r=".65")
            + rad(f"{u}apple", [(0, "#FF8A7A"), (.6, "#E5312E"), (1, "#8E1414")], cx=".35", cy=".3", r=".8"))
    body = f"""
<path d="M64 96 C88 96 104 110 106 128 H22 C24 110 40 96 64 96 Z" fill="#F0D3AC"/>
{spikes}
<circle cx="64" cy="70" r="42" fill="url(#{u}back)"/>
<path d="M64 46 C84 46 96 60 96 76 C96 84 92 90 86 94 C80 98 74 100 64 100 C54 100 48 98 42 94 C36 90 32 84 32 76 C32 60 44 46 64 46 Z" fill="url(#{u}face)"/>
<path d="M64 76 C70 76 84 80 92 84 C86 92 78 96 72 97 C68 92 66 86 64 76 Z" fill="#E8C59A" opacity=".6"/>
{eyes(52, 76, 70, 5)}
<ellipse cx="44" cy="82" rx="5" ry="3" fill="#FF8C8C" opacity=".4"/><ellipse cx="84" cy="82" rx="5" ry="3" fill="#FF8C8C" opacity=".4"/>
<ellipse cx="64" cy="84" rx="5" ry="3.8" fill="#24160E"/><ellipse cx="62.6" cy="82.8" rx="1.7" ry=".9" fill="#fff" opacity=".6"/>
<path d="M64 88 Q59 92 55 89.5 M64 88 Q69 92 73 89.5" fill="none" stroke="#5A3A22" stroke-width="1.5" stroke-linecap="round"/>
<circle cx="96" cy="32" r="9" fill="url(#{u}apple)"/><path d="M96 23 C96 20 98 18 100 17" fill="none" stroke="#5A3A22" stroke-width="1.6" stroke-linecap="round"/>
<path d="M98 21 C102 18 106 19 107 21 C104 23 101 23 98 21 Z" fill="#5DBB3A"/><ellipse cx="92.5" cy="29" rx="2.2" ry="1.4" fill="#fff" opacity=".55"/>"""
    return frame(u, defs, body)


def whale():
    u = "wh"
    bubbles = "".join(f'<circle cx="{x}" cy="{y}" r="{r}" fill="none" stroke="#fff" stroke-opacity=".7" stroke-width="1"/>' for x, y, r in ((24, 40, 3), (30, 30, 2), (104, 70, 2.6), (110, 60, 1.6), (20, 96, 2.2)))
    defs = (bg_grad(u, "#9DE7FF", "#2B8FD6", "#0A3A73")
            + lin(f"{u}body", [(0, "#6FB5F2"), (.55, "#3A7FD0"), (1, "#1E4E99")], "1", "1")
            + lin(f"{u}belly", [(0, "#F4FBFF"), (1, "#C9E3F7")])
            + lin(f"{u}water", [(0, "#FFFFFF"), (1, "#9BD9FF")]))
    grooves = "".join(f'<path d="M{40 + i * 7} 92 Q{44 + i * 7} 104 {50 + i * 7} 112" fill="none" stroke="#9CC4E6" stroke-width="1.2"/>' for i in range(6))
    body = f"""{bubbles}
<path d="M58 30 C54 20 46 16 40 18 C46 22 50 26 52 32 M70 30 C74 20 82 16 88 18 C82 22 78 26 76 32 M64 34 C64 22 64 14 64 8" fill="none" stroke="url(#{u}water)" stroke-width="4" stroke-linecap="round"/>
<circle cx="40" cy="18" r="3" fill="#fff"/><circle cx="88" cy="18" r="3" fill="#fff"/><circle cx="64" cy="7" r="3.4" fill="#fff"/>
<path d="M14 84 C14 56 36 36 66 36 C96 36 116 54 116 78 C116 104 94 122 64 122 C44 122 28 114 20 102 C12 106 6 104 4 98 C10 96 14 92 14 84 Z" fill="url(#{u}body)"/>
<path d="M28 96 C40 110 56 116 72 116 C90 116 104 108 112 94 C104 100 90 104 72 104 C56 104 40 102 28 96 Z" fill="url(#{u}belly)"/>
{grooves}
{eyes(50, 86, 72, 5.5)}
<ellipse cx="42" cy="84" rx="5.5" ry="3" fill="#FF9BB0" opacity=".45"/><ellipse cx="94" cy="84" rx="5.5" ry="3" fill="#FF9BB0" opacity=".45"/>
<path d="M58 86 Q68 94 78 86" fill="none" stroke="#123A73" stroke-width="2" stroke-linecap="round"/>
<path d="M30 56 C40 46 52 42 66 42" fill="none" stroke="#fff" stroke-opacity=".45" stroke-width="3" stroke-linecap="round"/>"""
    return frame(u, defs, body)


def robot():
    u = "rb"
    defs = (bg_grad(u, "#FFD29A", "#F27A1F", "#7A2E05")
            + lin(f"{u}metal", [(0, "#F3F6FA"), (.45, "#C3CCD8"), (1, "#7C889A")], "1", "1")
            + lin(f"{u}screen", [(0, "#1B2340"), (1, "#0B1022")])
            + rad(f"{u}led", [(0, "#E8FFFF"), (.6, "#5EE6FF"), (1, "#1A9AC8")], r=".55")
            + rad(f"{u}bulb", [(0, "#FFB0B0"), (.6, "#FF3B3B"), (1, "#8E0F0F")], cx=".35", cy=".3", r=".8"))
    body = f"""
<rect x="36" y="100" width="56" height="34" rx="10" fill="url(#{u}metal)"/>
<rect x="50" y="108" width="28" height="16" rx="4" fill="url(#{u}screen)"/>
<path d="M58.6 111.4 H69.4 V113.4 H62 L66 116 L62 118.6 H69.4 V120.6 H58.6 V118.8 L62.6 116 L58.6 113.2 Z" fill="#5EE6FF"/>
<rect x="56" y="92" width="16" height="10" rx="3" fill="#8A95A8"/>
<path d="M64 28 V14" stroke="#8A95A8" stroke-width="3" stroke-linecap="round"/><circle cx="64" cy="11" r="6" fill="url(#{u}bulb)"/>
<rect x="24" y="52" width="10" height="22" rx="4" fill="#8A95A8"/><rect x="94" y="52" width="10" height="22" rx="4" fill="#8A95A8"/>
<rect x="30" y="26" width="68" height="68" rx="20" fill="url(#{u}metal)"/>
<rect x="30" y="26" width="68" height="68" rx="20" fill="none" stroke="#fff" stroke-opacity=".7" stroke-width="1.4"/>
<rect x="38" y="40" width="52" height="40" rx="12" fill="url(#{u}screen)"/>
<path d="M46 58 Q52 50 58 58 M70 58 Q76 50 82 58" fill="none" stroke="url(#{u}led)" stroke-width="4" stroke-linecap="round"/>
<path d="M54 68 Q64 76 74 68" fill="none" stroke="#5EE6FF" stroke-width="2.6" stroke-linecap="round"/>
<ellipse cx="46" cy="70" rx="4" ry="2" fill="#FF6B9A" opacity=".55"/><ellipse cx="82" cy="70" rx="4" ry="2" fill="#FF6B9A" opacity=".55"/>
<circle cx="38" cy="34" r="2" fill="#7C889A"/><circle cx="90" cy="34" r="2" fill="#7C889A"/><circle cx="38" cy="86" r="2" fill="#7C889A"/><circle cx="90" cy="86" r="2" fill="#7C889A"/>
<path d="M42 44 Q50 41 58 42" fill="none" stroke="#fff" stroke-opacity=".25" stroke-width="2" stroke-linecap="round"/>"""
    return frame(u, defs, body)


def astronaut():
    u = "as"
    defs = (bg_grad(u, "#B49CFF", "#4B2FB8", "#120A3A")
            + lin(f"{u}suit", [(0, "#FFFFFF"), (1, "#C9D0E0")], ".7", "1", ".3")
            + rad(f"{u}helm", [(0, "#FFFFFF"), (.75, "#E3E8F2"), (1, "#A9B3C8")], cx=".4", cy=".35", r=".7")
            + lin(f"{u}visor", [(0, "#2A1E6E"), (.55, "#6E3FD0"), (1, "#F59E3A")], "1", "1")
            + rad(f"{u}planet", [(0, "#FFD27A"), (1, "#E0761A")], cx=".35", cy=".3", r=".8")
            + lin(f"{u}flame", [(0, "#FF4A2A"), (1, "#FFD43B")]))
    body = f"""{stars("as", 28)}
<circle cx="104" cy="26" r="10" fill="url(#{u}planet)"/><ellipse cx="104" cy="26" rx="17" ry="4" fill="none" stroke="#FFE3A6" stroke-width="1.6" transform="rotate(-20 104 26)"/>
<path d="M64 98 C90 98 106 112 108 130 H20 C22 112 38 98 64 98 Z" fill="url(#{u}suit)"/>
<rect x="44" y="108" width="40" height="12" rx="4" fill="#3E4A6A"/><circle cx="52" cy="114" r="2.4" fill="#5EE6FF"/><circle cx="60" cy="114" r="2.4" fill="#FF5A6A"/><circle cx="68" cy="114" r="2.4" fill="#FFD43B"/>
<ellipse cx="64" cy="98" rx="30" ry="7" fill="#C9D0E0"/>
<circle cx="64" cy="62" r="38" fill="url(#{u}helm)"/>
<path d="M34 64 C34 46 46 36 64 36 C82 36 94 46 94 64 C94 82 82 90 64 90 C46 90 34 82 34 64 Z" fill="url(#{u}visor)"/>
<path d="M42 54 C46 44 56 40 66 40" fill="none" stroke="#fff" stroke-opacity=".75" stroke-width="3.2" stroke-linecap="round"/>
<circle cx="78" cy="74" r="6" fill="#FFD27A" opacity=".55"/><path d="M46 78 L50 70 L54 78" fill="none" stroke="#fff" stroke-opacity=".35" stroke-width="1.4"/>
{stars("visor", 8, (40, 88, 46, 86), (.4, .9))}
<circle cx="30" cy="62" r="5" fill="#C9D0E0"/><circle cx="98" cy="62" r="5" fill="#C9D0E0"/>
<g transform="translate(86 104) scale(.18)"><path d="M24 0 C40 6 50 20 50 34 C54 30 56 24 55 17 C63 28 67 44 65 57 C62 77 49 90 33 90 C14 90 2 78 2 60 C2 46 10 36 18 30 C16 38 18 44 22 47 C20 34 27 17 24 0 Z" fill="url(#{u}flame)"/></g>"""
    return frame(u, defs, body)


def ninja():
    u = "nj"
    defs = (bg_grad(u, "#FFB1A0", "#E0402E", "#5E0E0A")
            + lin(f"{u}cloth", [(0, "#3A3F55"), (1, "#14161F")], ".7", "1", ".3")
            + lin(f"{u}skin", [(0, "#FFE2C6"), (1, "#F2C49A")])
            + lin(f"{u}band", [(0, "#4C6CF0"), (1, "#2433A8")])
            + lin(f"{u}steel", [(0, "#FFFFFF"), (1, "#8A95A8")], "1", "1"))
    body = f"""
<circle cx="64" cy="64" r="44" fill="#FFD6A0" opacity=".25"/>
<path d="M64 98 C90 98 106 112 110 130 H18 C22 112 38 98 64 98 Z" fill="url(#{u}cloth)"/>
<path d="M64 26 C90 26 104 46 104 68 C104 92 86 106 64 106 C42 106 24 92 24 68 C24 46 38 26 64 26 Z" fill="url(#{u}cloth)"/>
<path d="M30 56 C42 50 86 50 98 56 L98 74 C86 80 42 80 30 74 Z" fill="url(#{u}skin)"/>
<path d="M26 44 C40 36 88 36 102 44 L102 52 C88 46 40 46 26 52 Z" fill="url(#{u}band)"/>
<path d="M100 46 C108 46 116 40 120 34 C118 44 112 52 104 54 Z M100 50 C110 54 118 54 124 50 C118 58 110 60 102 56 Z" fill="url(#{u}band)"/>
<circle cx="64" cy="47" r="4.5" fill="#FFD43B" stroke="#A87705"/>
<path d="M40 64 Q50 58 58 64 Q50 69 40 64 Z M88 64 Q78 58 70 64 Q78 69 88 64 Z" fill="#fff"/>
<circle cx="50" cy="64" r="3.6" fill="#1B120E"/><circle cx="78" cy="64" r="3.6" fill="#1B120E"/>
<circle cx="48.8" cy="62.8" r="1.2" fill="#fff"/><circle cx="76.8" cy="62.8" r="1.2" fill="#fff"/>
<path d="M39 58 L58 61 M89 58 L70 61" stroke="#14161F" stroke-width="2.4" stroke-linecap="round"/>
<path d="M50 84 C58 88 70 88 78 84" fill="none" stroke="#000" stroke-opacity=".35" stroke-width="1.4"/>
<g transform="translate(22 104) rotate(20)"><path d="M0 -9 L2.5 -2.5 L9 0 L2.5 2.5 L0 9 L-2.5 2.5 L-9 0 L-2.5 -2.5 Z" fill="url(#{u}steel)" stroke="#5A6478" stroke-width=".6"/><circle r="1.6" fill="#3A3F55"/></g>"""
    return frame(u, defs, body)


def wizard():
    u = "wz"
    defs = (bg_grad(u, "#A6B8FF", "#3B3FB8", "#100E3E")
            + lin(f"{u}hat", [(0, "#6E86FF"), (1, "#2433A8")], "1", "1")
            + lin(f"{u}brim", [(0, "#4F64E8"), (1, "#1A237A")])
            + lin(f"{u}skin", [(0, "#FFE2C6"), (1, "#F2C49A")])
            + lin(f"{u}beard", [(0, "#FFFFFF"), (1, "#D6DCEA")])
            + rad(f"{u}gold", [(0, "#FFF4C8"), (.6, "#F4C23A"), (1, "#A87705")], cx=".35", cy=".3", r=".9"))
    hat_stars = "".join(f'<path d="M{x} {y - 3} L{x + .9} {y - .9} L{x + 3} {y} L{x + .9} {y + .9} L{x} {y + 3} L{x - .9} {y + .9} L{x - 3} {y} L{x - .9} {y - .9} Z" fill="#FFE27A"/>' for x, y in ((56, 34), (72, 24), (64, 44), (78, 40)))
    body = f"""{stars("wz", 18, (8, 120, 8, 60))}
<path d="M64 100 C88 100 104 112 108 130 H20 C24 112 40 100 64 100 Z" fill="#5B3FB8"/>
<path d="M40 66 C40 52 50 44 64 44 C78 44 88 52 88 66 C88 78 78 86 64 86 C50 86 40 78 40 66 Z" fill="url(#{u}skin)"/>
<path d="M38 70 C42 76 50 78 56 76 C58 82 61 86 64 86 C67 86 70 82 72 76 C78 78 86 76 90 70 C94 92 84 118 64 124 C44 118 34 92 38 70 Z" fill="url(#{u}beard)"/>
<path d="M50 96 C54 104 58 110 64 114 M78 96 C74 104 70 110 64 114 M64 90 V112" fill="none" stroke="#B9C2D6" stroke-width="1.2"/>
<path d="M52 76 C56 72 62 74 64 77 C66 74 72 72 76 76 C72 80 66 80 64 78 C62 80 56 80 52 76 Z" fill="#E9EDF5"/>
<path d="M46 58 Q52 52 59 57 M82 58 Q76 52 69 57" fill="none" stroke="#F4F6FB" stroke-width="3.4" stroke-linecap="round"/>
<circle cx="53" cy="64" r="3.4" fill="#1B120E"/><circle cx="75" cy="64" r="3.4" fill="#1B120E"/>
<circle cx="52" cy="62.8" r="1.1" fill="#fff"/><circle cx="74" cy="62.8" r="1.1" fill="#fff"/>
<ellipse cx="64" cy="70" rx="4" ry="3.4" fill="#F0A98A"/>
<path d="M26 50 C40 44 88 44 102 50 C100 56 90 58 64 58 C38 58 28 56 26 50 Z" fill="url(#{u}brim)"/>
<path d="M36 50 C44 34 52 16 74 4 C70 16 74 30 92 50 C74 54 54 54 36 50 Z" fill="url(#{u}hat)"/>
<path d="M38 48 C56 52 74 52 90 48 L90 44 C74 48 56 48 38 44 Z" fill="#FFD43B" opacity=".9"/>
{hat_stars}
<circle cx="74" cy="4" r="3.6" fill="url(#{u}gold)"/>"""
    return frame(u, defs, body)


def dragon():
    u = "dg"
    scales = "".join(f'<path d="M{x - 4} {y} Q{x} {y + 4} {x + 4} {y}" fill="none" stroke="#0E6A4A" stroke-opacity=".5" stroke-width="1.2"/>' for y, xs in ((40, (56, 64, 72)), (46, (52, 60, 68, 76))) for x in xs)
    defs = (bg_grad(u, "#FFD9A0", "#F08A2A", "#6E2A05")
            + rad(f"{u}skin", [(0, "#7DE8B0"), (.6, "#22A877"), (1, "#0B5A3C")], cy=".4", r=".7")
            + lin(f"{u}belly", [(0, "#FFF0B8"), (1, "#F0CC6A")])
            + lin(f"{u}horn", [(0, "#FFF6E0"), (1, "#D9B27A")])
            + rad(f"{u}iris", [(0, "#FFF29A"), (.6, "#F5B21A"), (1, "#A86A05")], cx=".45", cy=".4")
            + lin(f"{u}wing", [(0, "#1F8A5E"), (1, "#0B4A30")]))
    body = f"""
<path d="M18 90 C8 70 10 46 22 32 C24 48 30 58 40 64 Z M110 90 C120 70 118 46 106 32 C104 48 98 58 88 64 Z" fill="url(#{u}wing)"/>
<path d="M64 96 C90 96 106 110 108 130 H20 C22 110 38 96 64 96 Z" fill="url(#{u}skin)"/>
<path d="M64 100 C74 100 80 110 80 130 H48 C48 110 54 100 64 100 Z" fill="url(#{u}belly)"/>
<path d="M50 104 H78 M49 112 H79 M48 120 H80" stroke="#D9A83A" stroke-width="1.2"/>
<path d="M42 40 C38 26 40 14 46 6 C48 18 52 28 56 34 Z M86 40 C90 26 88 14 82 6 C80 18 76 28 72 34 Z" fill="url(#{u}horn)"/>
<path d="M64 30 C88 30 102 46 102 66 C102 80 96 88 88 94 C80 100 72 102 64 102 C56 102 48 100 40 94 C32 88 26 80 26 66 C26 46 40 30 64 30 Z" fill="url(#{u}skin)"/>
{scales}
<path d="M30 64 C22 60 18 54 16 46 C24 50 28 54 32 58 Z M98 64 C106 60 110 54 112 46 C104 50 100 54 96 58 Z" fill="#22A877"/>
<path d="M44 80 C50 72 78 72 84 80 C84 92 76 98 64 98 C52 98 44 92 44 80 Z" fill="#5FD39C"/>
<ellipse cx="57" cy="82" rx="2.4" ry="1.6" fill="#0B4A30"/><ellipse cx="71" cy="82" rx="2.4" ry="1.6" fill="#0B4A30"/>
<path d="M54 90 Q64 96 74 90" fill="none" stroke="#0B4A30" stroke-width="1.8" stroke-linecap="round"/>
<path d="M58 91 L59.5 95 L61 91.5 M67 91.5 L68.5 95 L70 91" fill="#fff" stroke="#fff" stroke-width=".8" stroke-linejoin="round"/>
<path d="M40 60 Q48 52 58 60 Q48 66 40 60 Z M88 60 Q80 52 70 60 Q80 66 88 60 Z" fill="url(#{u}iris)" stroke="#0B4A30" stroke-width="1.2"/>
<ellipse cx="49" cy="60" rx="1.6" ry="4" fill="#120B08"/><ellipse cx="79" cy="60" rx="1.6" ry="4" fill="#120B08"/>
<circle cx="46.6" cy="57.6" r="1.3" fill="#fff"/><circle cx="76.6" cy="57.6" r="1.3" fill="#fff"/>
<path d="M38 52 L56 55 M90 52 L72 55" stroke="#0B4A30" stroke-width="2" stroke-linecap="round"/>
<g fill="#fff" opacity=".7"><circle cx="50" cy="74" r="2.4"/><circle cx="46" cy="70" r="1.6"/><circle cx="78" cy="74" r="2.4"/><circle cx="82" cy="70" r="1.6"/></g>"""
    return frame(u, defs, body)


def icosa():
    u = "ic"
    pts = lambda n, r, cx, cy, rot=-90: [(cx + r * math.cos(math.radians(rot + i * 360 / n)), cy + r * math.sin(math.radians(rot + i * 360 / n))) for i in range(n)]
    d = lambda p: "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in p) + " Z"
    hexp = pts(6, 46, 64, 66); tri = pts(3, 25, 64, 68)
    shades = ["#7FE7FF", "#3FB2EA", "#1E7FC2", "#145A96", "#2A8BD0", "#5CCBF2"]
    faces = ""
    for i in range(6):
        a, b = hexp[i], hexp[(i + 1) % 6]
        c = tri[((i + 1) // 2) % 3]
        faces += f'<path d="{d([a, b, c])}" fill="{shades[i]}" stroke="#0B3A66" stroke-opacity=".4" stroke-width=".8"/>'
    for i in range(3):
        faces += f'<path d="{d([tri[i], tri[(i + 1) % 3], hexp[(2 * i + 1) % 6]])}" fill="{["#9BEFFF", "#4CC2F0", "#2F98D8"][i]}" stroke="#0B3A66" stroke-opacity=".4" stroke-width=".8"/>'
    faces += f'<path d="{d(tri)}" fill="url(#{u}top)" stroke="#fff" stroke-opacity=".7" stroke-width="1"/>'
    defs = bg_grad(u, "#B6E9FF", "#2D6FD0", "#0A1F5C") + rad(f"{u}top", [(0, "#FFFFFF"), (1, "#A6EEFF")], cx=".4", cy=".35", r=".8") + rad(f"{u}glow", [(0, "#9BE0FFAA"), (1, "#9BE0FF00")])
    body = (f'<circle cx="64" cy="66" r="50" fill="url(#{u}glow)"/>' + stars("ic", 10)
            + f'<ellipse cx="64" cy="114" rx="30" ry="5" fill="#000" opacity=".25"/>' + faces
            + '<path d="M30 40 L32 45 L37 47 L32 49 L30 54 L28 49 L23 47 L28 45 Z" fill="#fff" opacity=".85"/>')
    return frame(u, defs, body)


def spiral():
    u = "sp"
    phi = (1 + 5 ** .5) / 2
    # Золотые прямоугольники и спираль Фибоначчи
    squares, arcs = "", ""
    x, y, s = 30.0, 34.0, 68 / phi
    sizes = [68 / phi ** k for k in range(1, 8)]
    box = [30.0, 34.0, 68.0, 68 / phi]
    cx, cy = box[0], box[1]
    d = ""
    x0, y0, w, h = 30.0, 38.0, 68.0, 68 / phi
    dirs = 0
    path = f"M{x0:.1f} {y0 + h:.1f}"
    for k in range(7):
        sq = h if dirs % 4 in (0, 2) else w
        if dirs % 4 == 0:   # квадрат слева
            squares += f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{h:.1f}" height="{h:.1f}"/>'
            path += f" A{h:.1f} {h:.1f} 0 0 1 {x0 + h:.1f} {y0:.1f}"
            x0, w = x0 + h, w - h
        elif dirs % 4 == 1:  # сверху
            squares += f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{w:.1f}" height="{w:.1f}"/>'
            path += f" A{w:.1f} {w:.1f} 0 0 1 {x0 + w:.1f} {y0 + w:.1f}"
            y0, h = y0 + w, h - w
        elif dirs % 4 == 2:  # справа
            squares += f'<rect x="{x0 + w - h:.1f}" y="{y0:.1f}" width="{h:.1f}" height="{h:.1f}"/>'
            path += f" A{h:.1f} {h:.1f} 0 0 1 {x0 + w - h:.1f} {y0 + h:.1f}"
            w = w - h
        else:                # снизу
            squares += f'<rect x="{x0:.1f}" y="{y0 + h - w:.1f}" width="{w:.1f}" height="{w:.1f}"/>'
            path += f" A{w:.1f} {w:.1f} 0 0 1 {x0:.1f} {y0 + h - w:.1f}"
            h = h - w
        dirs += 1
    defs = (bg_grad(u, "#5A4A2A", "#2A2010", "#0E0A04", ".5", ".45")
            + lin(f"{u}gold", [(0, "#FFF4C8"), (.5, "#F4C23A"), (1, "#A87705")], "1", "1")
            + rad(f"{u}glow", [(0, "#FFD86A88"), (1, "#FFD86A00")]))
    body = (f'<circle cx="64" cy="66" r="54" fill="url(#{u}glow)"/>'
            f'<g transform="translate(64 60) scale(1.18) translate(-64 -59)"><g fill="none" stroke="#F4C23A" stroke-opacity=".45" stroke-width="1">{squares}</g>'
            f'<rect x="30" y="38" width="68" height="{68 / phi:.1f}" fill="none" stroke="url(#{u}gold)" stroke-width="2"/>'
            f'<path d="{path}" fill="none" stroke="#000" stroke-opacity=".35" stroke-width="6" transform="translate(1 2)"/>'
            f'<path d="{path}" fill="none" stroke="url(#{u}gold)" stroke-width="5" stroke-linecap="round"/>'
            f'<path d="{path}" fill="none" stroke="#FFF8DC" stroke-width="1.2" stroke-linecap="round" opacity=".8"/></g>'
            '<text x="64" y="108" text-anchor="middle" font-family="Onest, sans-serif" font-size="11" font-weight="800" fill="#F4C23A" opacity=".85">φ</text>')
    return frame(u, defs, body)


BATCH = {"hedgehog": hedgehog, "whale": whale, "robot": robot, "astronaut": astronaut, "ninja": ninja,
         "wizard": wizard, "dragon": dragon, "icosa": icosa, "spiral": spiral}
