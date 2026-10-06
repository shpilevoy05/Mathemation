"""Аватары нового стиля — партия 1: интеграл, пи, лемниската, кот, пингвин, медведь."""
import math
import random
from pathlib import Path

from avatars import frame
from logo import P

HERE = Path(__file__).parent


def bg_grad(u, a, b, c, cx=".35", cy=".28"):
    return (f'<radialGradient id="{u}bg" cx="{cx}" cy="{cy}" r=".85"><stop offset="0" stop-color="{a}"/>'
            f'<stop offset=".5" stop-color="{b}"/><stop offset="1" stop-color="{c}"/></radialGradient>')


def lin(id_, stops, x2="0", y2="1", x1="0", y1="0"):
    s = "".join(f'<stop offset="{o}" stop-color="{c}"/>' for o, c in stops)
    return f'<linearGradient id="{id_}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}">{s}</linearGradient>'


def rad(id_, stops, cx=".5", cy=".5", r=".6"):
    s = "".join(f'<stop offset="{o}" stop-color="{c}"/>' for o, c in stops)
    return f'<radialGradient id="{id_}" cx="{cx}" cy="{cy}" r="{r}">{s}</radialGradient>'


# ── Математические скульптуры (в пару к Σ) ────────────────────────────────────
def sculpture(u, bg, glow, face, side, shape, deco=""):
    """shape(kind) -> svg-элемент; kind: 'side' (боковина) или 'face'."""
    extrude = "".join(f'<g transform="translate({k * .5:.2f} {k * .9:.2f})">{shape("side")}</g>' for k in range(8, 0, -1))
    defs = (bg + rad(f"{u}glow", [(0, glow + "E6"), (1, glow + "00")])
            + lin(f"{u}face", [(0, "#FFFFFF"), (.45, face[0]), (1, face[1])], "1", "1")
            + lin(f"{u}side", [(0, side[0]), (1, side[1])], "1", "0"))
    body = (f'<circle cx="64" cy="66" r="44" fill="url(#{u}glow)"/>'
            f'<g fill="none" stroke="#fff" stroke-opacity=".3" stroke-width="1"><circle cx="64" cy="66" r="30"/><circle cx="64" cy="66" r="38" stroke-dasharray="2 5"/></g>'
            + deco + extrude + shape("face")
            + '<g fill="#fff"><path d="M26 34 L28 40 L34 42 L28 44 L26 50 L24 44 L18 42 L24 40 Z" opacity=".85"/>'
              '<path d="M98 98 L99.4 102 L103 103 L99.4 104.4 L98 108 L96.6 104.4 L93 103 L96.6 102 Z" opacity=".7"/></g>')
    return frame(u, defs, body)


def integral():
    u = "ig"
    d = "M80 26 C72 18 62 22 60 36 L56 92 C54 106 44 110 36 102"
    def shape(kind):
        col = f"url(#{u}side)" if kind == "side" else f"url(#{u}face)"
        hi = '' if kind == "side" else f'<path d="M79 27 C74 23 67 24 64 31" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" opacity=".9"/>'
        return f'<path d="{d}" fill="none" stroke="{col}" stroke-width="13" stroke-linecap="round"/>{hi}'
    deco = ('<text x="84" y="104" font-family="Onest, sans-serif" font-size="11" font-weight="700" fill="#fff" opacity=".55">dx</text>'
            '<g fill="#fff" opacity=".5"><circle cx="34" cy="84" r="1.4"/><circle cx="96" cy="40" r="1.6"/></g>')
    return sculpture(u, bg_grad(u, "#7CF0C8", "#14A07A", "#063E33"), "#9AF5D5", ("#D6FFF0", "#5BD7AA"), ("#0B6A50", "#20A57D"), shape, deco)


def pi():
    u = "pi"
    pts = [(0, 0), (104, 0, 4), (104, 19), (82, 19), (82, 100, 3), (62, 100), (62, 19), (42, 19), (42, 100), (22, 100), (22, 19), (0, 19)]
    d = P([(x, y, *(r)) for x, y, *r in pts], 0)
    s = .5
    tx, ty = 64 - 104 * s / 2, 64 - 50 * s + 4
    def shape(kind):
        col = f"url(#{u}side)" if kind == "side" else f"url(#{u}face)"
        return f'<path d="{d}" fill="{col}" transform="translate({tx:.2f} {ty:.2f}) scale({s})"/>' + (
            '' if kind == "side" else f'<path d="M{tx + 2:.1f} {ty + 1.6:.1f} H{tx + 48:.1f}" stroke="#fff" stroke-width="1.6" stroke-linecap="round" opacity=".9"/>')
    deco = ('<text x="22" y="100" font-family="Onest, sans-serif" font-size="8.5" font-weight="700" fill="#fff" opacity=".45">3,14159</text>'
            '<circle cx="64" cy="66" r="47" fill="none" stroke="#FFD6E2" stroke-opacity=".35" stroke-width="1.2" stroke-dasharray="1 3"/>')
    return sculpture(u, bg_grad(u, "#FF9DBB", "#D2336E", "#5C0E2E"), "#FFB5CB", ("#FFE3EC", "#FF7FA6"), ("#8E1A44", "#C9356A"), shape, deco)


def infinity():
    u = "inf"
    d = "M64 66 C73 52 95 50 95 66 C95 82 73 80 64 66 C55 52 33 50 33 66 C33 82 55 80 64 66 Z"
    def shape(kind):
        col = f"url(#{u}side)" if kind == "side" else f"url(#{u}face)"
        hi = '' if kind == "side" else '<path d="M38 58 C43 53 52 54 58 60" fill="none" stroke="#fff" stroke-width="1.8" stroke-linecap="round" opacity=".9"/>'
        return f'<path d="{d}" fill="none" stroke="{col}" stroke-width="12" stroke-linejoin="round"/>{hi}'
    deco = '<ellipse cx="64" cy="70" rx="50" ry="15" fill="none" stroke="#C7D7FF" stroke-opacity=".6" stroke-width="1.4" transform="rotate(-14 64 70)"/>'
    return sculpture(u, bg_grad(u, "#7FD8FF", "#1E7FD0", "#0A2E66"), "#9BE0FF", ("#E3F6FF", "#6FC2F5"), ("#0D4C8F", "#2378C8"), shape, deco)


# ── Кот: серый полосатый, зелёные глаза, ошейник с жетоном Σ ───────────────────
def cat():
    u = "ct"
    defs = (bg_grad(u, "#D2B8FF", "#7A52D6", "#2E1A70")
            + lin(f"{u}fur", [(0, "#A9B4C6"), (.55, "#7A869C"), (1, "#4A5468")], ".6", "1", ".3")
            + rad(f"{u}head", [(0, "#B9C3D3"), (.65, "#8590A6"), (1, "#5A6479")], cy=".38", r=".7")
            + lin(f"{u}white", [(0, "#FFFFFF"), (1, "#E6E9F0")])
            + lin(f"{u}ear", [(0, "#F7C9D2"), (1, "#D98FA0")])
            + rad(f"{u}iris", [(0, "#D8FF9A"), (.6, "#5DBB3A"), (1, "#1F6A18")], cx=".45", cy=".4")
            + lin(f"{u}col", [(0, "#E64060"), (1, "#9A1F3A")])
            + rad(f"{u}tag", [(0, "#FFF4C8"), (.6, "#F4C23A"), (1, "#A87705")], cx=".35", cy=".3", r=".9"))
    stripes = "".join(f'<path d="{d}" fill="#4E5870" opacity=".55"/>' for d in (
        "M60 34 C61 40 61 44 64 46 C67 44 67 40 68 34 C66 36 62 36 60 34 Z",
        "M50 38 C51 43 53 46 56 47 C55 43 54 40 50 38 Z", "M78 38 C77 43 75 46 72 47 C73 43 74 40 78 38 Z",
        "M28 66 C33 66 37 67 40 69 C36 70 32 70 28 66 Z", "M100 66 C95 66 91 67 88 69 C92 70 96 70 100 66 Z"))
    whisk = "".join(f'<path d="M{a}" fill="none" stroke="#fff" stroke-opacity=".85" stroke-width=".8" stroke-linecap="round"/>' for a in (
        "56 80 Q42 77 30 79", "56 83 Q43 84 32 88", "72 80 Q86 77 98 79", "72 83 Q85 84 96 88"))
    body = f"""
<path d="M64 94 C88 94 104 108 108 128 H20 C24 108 40 94 64 94 Z" fill="url(#{u}fur)"/>
<path d="M64 98 C74 98 80 108 80 128 H48 C48 108 54 98 64 98 Z" fill="url(#{u}white)"/>
<path d="M30 52 C27 38 28 24 32 14 C42 20 50 30 54 40 Z" fill="url(#{u}fur)"/>
<path d="M98 52 C101 38 100 24 96 14 C86 20 78 30 74 40 Z" fill="url(#{u}fur)"/>
<path d="M34 46 C32 36 33 27 35 21 C41 26 46 32 49 39 Z" fill="url(#{u}ear)"/>
<path d="M94 46 C96 36 95 27 93 21 C87 26 82 32 79 39 Z" fill="url(#{u}ear)"/>
<path d="M64 32 C88 32 102 48 102 68 C102 80 98 88 92 92 C84 98 74 100 64 100 C54 100 44 98 36 92 C30 88 26 80 26 68 C26 48 40 32 64 32 Z" fill="url(#{u}head)"/>
<path d="M26 70 C20 72 16 70 13 66 C18 66 22 64 26 60 Z M102 70 C108 72 112 70 115 66 C110 66 106 64 102 60 Z" fill="url(#{u}head)"/>
{stripes}
<path d="M64 70 C70 70 80 74 82 82 C82 92 74 98 64 98 C54 98 46 92 46 82 C48 74 58 70 64 70 Z" fill="url(#{u}white)"/>
<path d="M40 63 Q50 52 60 63 Q50 70 40 63 Z" fill="url(#{u}iris)" stroke="#2B3040" stroke-width="1.4"/>
<path d="M88 63 Q78 52 68 63 Q78 70 88 63 Z" fill="url(#{u}iris)" stroke="#2B3040" stroke-width="1.4"/>
<ellipse cx="50" cy="62" rx="1.9" ry="5.2" fill="#12141C"/><ellipse cx="78" cy="62" rx="1.9" ry="5.2" fill="#12141C"/>
<circle cx="47" cy="59.6" r="1.5" fill="#fff"/><circle cx="75" cy="59.6" r="1.5" fill="#fff"/>
<path d="M60 78 Q64 76 68 78 Q66 82 64 82.5 Q62 82 60 78 Z" fill="#F08AA0"/>
<path d="M64 82.5 V85 M64 85 Q60.5 88 57.5 86 M64 85 Q67.5 88 70.5 86" fill="none" stroke="#3A3F52" stroke-width="1.3" stroke-linecap="round"/>
{whisk}
<path d="M38 100 C50 106 78 106 90 100 L92 107 C78 113 50 113 36 107 Z" fill="url(#{u}col)"/>
<circle cx="64" cy="114" r="7.5" fill="url(#{u}tag)" stroke="#A87705" stroke-width=".8"/>
<path d="M60.2 110.6 H67.8 V112 H62.6 L65.4 114 L62.6 116 H67.8 V117.4 H60.2 V116 L63 114 L60.2 112 Z" fill="#7A5405"/>"""
    return frame(u, defs, body)


# ── Пингвин: ледяной фон, галстук-бабочка ─────────────────────────────────────
def penguin():
    u = "pg"
    rnd = random.Random(3)
    snow = "".join(f'<circle cx="{rnd.uniform(8, 120):.1f}" cy="{rnd.uniform(8, 80):.1f}" r="{rnd.uniform(.6, 1.6):.1f}" fill="#fff" opacity="{rnd.uniform(.4, .9):.2f}"/>' for _ in range(16))
    defs = (bg_grad(u, "#D9F3FF", "#5FB7E8", "#18578F")
            + lin(f"{u}black", [(0, "#3A4256"), (1, "#141824")], ".7", "1", ".3")
            + lin(f"{u}white", [(0, "#FFFFFF"), (1, "#DDE6F0")])
            + lin(f"{u}beak", [(0, "#FFC24D"), (1, "#E07A12")])
            + lin(f"{u}bow", [(0, "#4C6CF0"), (1, "#2433A8")]))
    body = f"""{snow}
<path d="M64 26 C92 26 108 48 108 78 C108 104 92 128 64 128 C36 128 20 104 20 78 C20 48 36 26 64 26 Z" fill="url(#{u}black)"/>
<path d="M20 86 C10 96 12 112 22 122 C26 108 28 98 32 90 Z M108 86 C118 96 116 112 106 122 C102 108 100 98 96 90 Z" fill="url(#{u}black)"/>
<path d="M64 48 C72 40 88 42 92 54 C96 66 92 80 84 90 C80 104 74 116 64 128 C54 116 48 104 44 90 C36 80 32 66 36 54 C40 42 56 40 64 48 Z" fill="url(#{u}white)"/>
<circle cx="52" cy="62" r="6.5" fill="#141824"/><circle cx="76" cy="62" r="6.5" fill="#141824"/>
<circle cx="50" cy="59.8" r="2.2" fill="#fff"/><circle cx="74" cy="59.8" r="2.2" fill="#fff"/><circle cx="54" cy="64.4" r=".9" fill="#fff" opacity=".8"/><circle cx="78" cy="64.4" r=".9" fill="#fff" opacity=".8"/>
<ellipse cx="44" cy="74" rx="5" ry="3" fill="#FF9BB0" opacity=".45"/><ellipse cx="84" cy="74" rx="5" ry="3" fill="#FF9BB0" opacity=".45"/>
<path d="M56 70 Q64 66 72 70 Q68 80 64 81 Q60 80 56 70 Z" fill="url(#{u}beak)" stroke="#B5600A" stroke-width=".8"/>
<path d="M57 71 Q64 70 71 71" fill="none" stroke="#B5600A" stroke-width=".8"/>
<path d="M64 98 L48 90 C46 96 46 102 48 106 Z M64 98 L80 90 C82 96 82 102 80 106 Z" fill="url(#{u}bow)" stroke="#1A237A" stroke-width=".8"/>
<rect x="59.5" y="94" width="9" height="8" rx="2.5" fill="#3B55D6" stroke="#1A237A" stroke-width=".8"/>"""
    return frame(u, defs, body)


# ── Медведь: бурый, вязаная шапка с помпоном цвета бренда ──────────────────────
def bear():
    u = "br"
    knit = "".join(f'<path d="M{x} 33 L{x + 3} 40 L{x + 6} 33" fill="none" stroke="#2B36A8" stroke-opacity=".55" stroke-width="1.4"/>' for x in range(36, 92, 7))
    defs = (bg_grad(u, "#FFE2A6", "#E8A23A", "#7A4A0A")
            + rad(f"{u}fur", [(0, "#B87A4A"), (.6, "#8A5530"), (1, "#5A3418")], cy=".4", r=".7")
            + lin(f"{u}muz", [(0, "#F3DDBF"), (1, "#D6B48A")])
            + lin(f"{u}hat", [(0, "#6E86FF"), (1, "#3343C8")])
            + lin(f"{u}cuff", [(0, "#4F64E8"), (1, "#2433A8")])
            + rad(f"{u}pom", [(0, "#FFFFFF"), (1, "#DDE3F6")], cx=".4", cy=".35", r=".7"))
    body = f"""
<path d="M64 96 C90 96 108 110 112 128 H16 C20 110 38 96 64 96 Z" fill="url(#{u}fur)"/>
<circle cx="30" cy="48" r="14" fill="url(#{u}fur)"/><circle cx="98" cy="48" r="14" fill="url(#{u}fur)"/>
<circle cx="30" cy="48" r="7.5" fill="#D6A57A"/><circle cx="98" cy="48" r="7.5" fill="#D6A57A"/>
<path d="M64 34 C90 34 104 52 104 72 C104 92 86 104 64 104 C42 104 24 92 24 72 C24 52 38 34 64 34 Z" fill="url(#{u}fur)"/>
<path d="M30 46 C30 24 46 10 64 10 C82 10 98 24 98 46 Z" fill="url(#{u}hat)"/>
<path d="M44 14 L44 46 M54 11 L54 46 M64 10 L64 46 M74 11 L74 46 M84 14 L84 46" stroke="#2433A8" stroke-opacity=".35" stroke-width="1.2"/>
<rect x="27" y="38" width="74" height="13" rx="6.5" fill="url(#{u}cuff)"/>
{knit.replace(" 33 ", " 41 ").replace(" 40 ", " 48 ")}
<circle cx="64" cy="9" r="8" fill="url(#{u}pom)"/>
<circle cx="50" cy="66" r="5" fill="#1E120A"/><circle cx="78" cy="66" r="5" fill="#1E120A"/>
<circle cx="48.4" cy="64.2" r="1.7" fill="#fff"/><circle cx="76.4" cy="64.2" r="1.7" fill="#fff"/>
<path d="M44 59 Q50 56 55 59 M73 59 Q78 56 84 59" fill="none" stroke="#3A2010" stroke-width="1.6" stroke-linecap="round"/>
<ellipse cx="64" cy="84" rx="18" ry="14" fill="url(#{u}muz)"/>
<path d="M57 78 Q64 74 71 78 Q69 84 64 85 Q59 84 57 78 Z" fill="#2A1A10"/>
<ellipse cx="62" cy="77.8" rx="2.2" ry="1" fill="#fff" opacity=".6"/>
<path d="M64 85 V89 M64 89 Q59.5 93 55.5 90.5 M64 89 Q68.5 93 72.5 90.5" fill="none" stroke="#3A2010" stroke-width="1.5" stroke-linecap="round"/>
<ellipse cx="40" cy="80" rx="5" ry="3" fill="#FF8C7A" opacity=".35"/><ellipse cx="88" cy="80" rx="5" ry="3" fill="#FF8C7A" opacity=".35"/>"""
    return frame(u, defs, body)


BATCH = {"integral": integral, "pi": pi, "infinity": infinity, "cat": cat, "penguin": penguin, "bear": bear}
