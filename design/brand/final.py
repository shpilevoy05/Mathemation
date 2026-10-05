"""Чистовики: анимированная рамка «Розетка», вымпел сезона, лис."""
import math
from pathlib import Path

from concepts import doc, glyph, mix
from leagues import DIGITS, LEAGUES, ORDER, placed
from rewards import MEDAL, _ring_defs

HERE = Path(__file__).parent

ROSETTE_CSS = """
.rsx-a, .rsx-b, .rsx-shine { transform-box: view-box; transform-origin: 80px 80px; }
.rsx-a { animation: rsx-spin 48s linear infinite; }
.rsx-b { animation: rsx-spin 72s linear infinite reverse; }
.rsx-shine { animation: rsx-spin 7s linear infinite; }
.rsx-spark { animation: rsx-twinkle 2.8s ease-in-out infinite; animation-delay: calc(var(--i) * .35s); }
@keyframes rsx-spin { to { transform: rotate(360deg) } }
@keyframes rsx-twinkle { 0%, 100% { opacity: .25 } 50% { opacity: 1 } }
@media (prefers-reduced-motion: reduce) { .rsx-a, .rsx-b, .rsx-shine, .rsx-spark { animation: none; } }
"""


def frame_rosette_anim(key, place=None, with_style=True):
    """Рамка «Розетка»: два набора лепестков вращаются навстречу — узор
    переливается, как гильош; по ободу бежит блик, на кромке мерцают искры.
    Кромка по месту: золото, серебро, бронза."""
    L = LEAGUES[key]; t = ORDER.index(key); u = f"fz{key}{place or 0}"
    n = [3, 4, 5, 6, 8, 12][t] * 2
    edge = MEDAL[place] if place else (L["light"], L["mid"], L["deep"])
    defs = (_ring_defs(u, L)
            + f'<linearGradient id="{u}e" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{edge[0]}"/><stop offset=".5" stop-color="{edge[1]}"/><stop offset="1" stop-color="{edge[2]}"/></linearGradient>'
            + f'<linearGradient id="{u}s" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".5" stop-color="#fff" stop-opacity=".85"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>')
    a = "".join(f'<ellipse cx="80" cy="80" rx="70" ry="38" fill="none" stroke="{L["tint"]}" stroke-opacity=".75" stroke-width="1.1" transform="rotate({k * 180 / n:.1f} 80 80)"/>' for k in range(n))
    b = "".join(f'<ellipse cx="80" cy="80" rx="70" ry="22" fill="none" stroke="{L["tint"]}" stroke-opacity=".4" stroke-width=".8" transform="rotate({k * 180 / n + 90 / n:.1f} 80 80)"/>' for k in range(n))
    sparks = "".join(
        f'<circle class="rsx-spark" style="--i:{k}" cx="{80 + 70.5 * math.cos(math.radians(-90 + k * 30)):.1f}" '
        f'cy="{80 + 70.5 * math.sin(math.radians(-90 + k * 30)):.1f}" r="1.9" fill="#fff"/>' for k in range(12))
    style = f"<style>{ROSETTE_CSS}</style>" if with_style else ""
    body = (f'{style}<g mask="url(#{u}m)"><circle cx="80" cy="80" r="76" fill="url(#{u}e)"/><circle cx="80" cy="80" r="72" fill="url(#{u}g)"/>'
            f'<g class="rsx-b">{b}</g><g class="rsx-a">{a}</g>'
            f'<g class="rsx-shine"><path d="M80 6 A74 74 0 0 1 132 28" fill="none" stroke="url(#{u}s)" stroke-width="5" stroke-linecap="round"/></g>'
            f'<circle cx="80" cy="80" r="72" fill="none" stroke="#fff" stroke-opacity=".55" stroke-width="1.2"/>'
            f'<circle cx="80" cy="80" r="55.5" fill="none" stroke="url(#{u}e)" stroke-width="4"/></g>{sparks}')
    return doc(body, defs, "0 0 160 160")


def pennant(key, place=1):
    """Вымпел сезона: ткань цвета лиги со складками, кайма, кисть и древко по металлу места."""
    L = LEAGUES[key]; a, b, c = MEDAL[place]; u = f"pn{key}{place}"
    defs = (f'<linearGradient id="{u}f" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{L["deep"]}"/><stop offset=".18" stop-color="{L["mid"]}"/>'
            f'<stop offset=".34" stop-color="{mix(L["mid"], L["light"], .35)}"/><stop offset=".5" stop-color="{L["mid"]}"/><stop offset=".68" stop-color="{mix(L["mid"], L["light"], .3)}"/>'
            f'<stop offset=".84" stop-color="{L["mid"]}"/><stop offset="1" stop-color="{L["deep"]}"/></linearGradient>'
            f'<linearGradient id="{u}m" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{a}"/><stop offset=".5" stop-color="{b}"/><stop offset="1" stop-color="{c}"/></linearGradient>'
            f'<radialGradient id="{u}md" cx=".38" cy=".32" r=".8"><stop offset="0" stop-color="{a}"/><stop offset=".6" stop-color="{b}"/><stop offset="1" stop-color="{c}"/></radialGradient>')
    trd, dd = placed(DIGITS[place], 12, 64, 96)
    body = (f'<path d="M30 20 H98 V98 L64 118 L30 98 Z" fill="#000" opacity=".18" transform="translate(2 4)"/>'
            f'<path d="M30 20 H98 V98 L64 118 L30 98 Z" fill="url(#{u}f)"/>'
            f'<path d="M35 20 V95.5 L64 112.5 L93 95.5 V20" fill="none" stroke="url(#{u}m)" stroke-width="2.6"/>'
            f'<path d="M30 20 H98 V27 H30 Z" fill="#000" opacity=".22"/>'
            + '<g transform="translate(0 1.6)">' + glyph(key, 30, 64, 56, L["deep"]) + '</g>' + glyph(key, 30, 64, 54, "#fff")
            + f'<circle cx="64" cy="96" r="11" fill="url(#{u}md)" stroke="{c}" stroke-width="1.2"/><circle cx="64" cy="96" r="8.4" fill="none" stroke="#fff" stroke-opacity=".6"/>'
            + f'<path d="{dd}" fill="#fff" {trd}/>'
            + f'<rect x="20" y="14" width="88" height="7" rx="3.5" fill="url(#{u}m)" stroke="{c}" stroke-width=".8"/>'
            + f'<circle cx="19" cy="17.5" r="5.5" fill="url(#{u}md)" stroke="{c}" stroke-width=".8"/><circle cx="109" cy="17.5" r="5.5" fill="url(#{u}md)" stroke="{c}" stroke-width=".8"/>'
            + f'<path d="M64 14 V6" stroke="url(#{u}m)" stroke-width="2"/><circle cx="64" cy="5" r="2.6" fill="url(#{u}md)"/>'
            + f'<path d="M98 22 C104 34 104 46 100 58" fill="none" stroke="url(#{u}m)" stroke-width="1.4"/><path d="M100 58 L96.5 71 L103.5 71 Z" fill="url(#{u}md)"/>')
    return doc(body, defs)
