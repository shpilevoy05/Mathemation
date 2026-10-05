"""Пробные аватары нового стиля: сова, лис, сигма (сетка 128, круг r60)."""
from pathlib import Path

from logo import SIGMA

HERE = Path(__file__).parent


def frame(uid, bg, body):
    """Общая оправа: фон-диск, содержимое под круглой маской, блик и кромка."""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128" fill="none">
<defs>
{bg}
<clipPath id="{uid}clip"><circle cx="64" cy="64" r="60"/></clipPath>
<linearGradient id="{uid}gloss" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".42"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>
<radialGradient id="{uid}vig" cx=".5" cy=".5" r=".5"><stop offset=".7" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".28"/></radialGradient>
</defs>
<circle cx="64" cy="64" r="60" fill="url(#{uid}bg)"/>
<g clip-path="url(#{uid}clip)">{body}<circle cx="64" cy="64" r="60" fill="url(#{uid}vig)"/></g>
<path d="M22 46 C30 22 52 10 74 12 C58 18 40 30 30 50 Z" fill="url(#{uid}gloss)"/>
<circle cx="64" cy="64" r="59.2" fill="none" stroke="#fff" stroke-opacity=".55" stroke-width="1.6"/>
<circle cx="64" cy="64" r="61" fill="none" stroke="#000" stroke-opacity=".18" stroke-width="1.2"/>
</svg>"""


def owl():
    u = "ow"
    bg = f"""<radialGradient id="{u}bg" cx=".35" cy=".28" r=".85"><stop offset="0" stop-color="#9FB2FF"/><stop offset=".5" stop-color="#4C60D8"/><stop offset="1" stop-color="#1E2770"/></radialGradient>
<linearGradient id="{u}body" x1=".2" y1="0" x2=".8" y2="1"><stop offset="0" stop-color="#D9995A"/><stop offset=".55" stop-color="#A9672F"/><stop offset="1" stop-color="#6E3E17"/></linearGradient>
<linearGradient id="{u}wing" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#8E5626"/><stop offset="1" stop-color="#5A3110"/></linearGradient>
<radialGradient id="{u}belly" cx=".5" cy=".35" r=".7"><stop offset="0" stop-color="#FFF3DC"/><stop offset="1" stop-color="#E8C893"/></radialGradient>
<radialGradient id="{u}disc" cx=".5" cy=".45" r=".6"><stop offset="0" stop-color="#FFF9EE"/><stop offset=".75" stop-color="#F3DDB8"/><stop offset="1" stop-color="#D9B27E"/></radialGradient>
<radialGradient id="{u}iris" cx=".45" cy=".4" r=".6"><stop offset="0" stop-color="#FFE27A"/><stop offset=".7" stop-color="#F29A12"/><stop offset="1" stop-color="#B8620A"/></radialGradient>
<linearGradient id="{u}beak" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FFC14D"/><stop offset="1" stop-color="#D9781A"/></linearGradient>
<linearGradient id="{u}gold" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#FFE9A3"/><stop offset=".5" stop-color="#D9A631"/><stop offset="1" stop-color="#8A6206"/></linearGradient>"""
    feathers = "".join(
        f'<path d="M{x - 4} {y} Q{x} {y + 4.5} {x + 4} {y}" fill="none" stroke="#C59A62" stroke-width="1.4" stroke-linecap="round"/>'
        for y, xs in ((88, (56, 64, 72)), (95, (52, 60, 68, 76)), (102, (56, 64, 72)), (109, (52, 60, 68, 76)))
        for x in xs)
    wing_lines = "".join(
        f'<path d="M{a}" fill="none" stroke="#3E2008" stroke-opacity=".35" stroke-width="1.3" stroke-linecap="round"/>'
        for a in ("30 80 Q28 92 34 104", "35 78 Q33 90 38 102", "98 80 Q100 92 94 104", "93 78 Q95 90 90 102"))
    body = f"""
<g opacity=".35" fill="#fff"><circle cx="24" cy="30" r="1.2"/><circle cx="104" cy="24" r="1.5"/><circle cx="110" cy="52" r="1"/><circle cx="16" cy="70" r="1"/><circle cx="96" cy="14" r=".9"/></g>
<path d="M38 44 C30 32 30 20 33 12 C40 20 48 28 54 36 Z" fill="url(#{u}wing)"/>
<path d="M90 44 C98 32 98 20 95 12 C88 20 80 28 74 36 Z" fill="url(#{u}wing)"/>
<path d="M64 30 C92 30 108 52 108 80 C108 106 90 124 64 124 C38 124 20 106 20 80 C20 52 36 30 64 30 Z" fill="url(#{u}body)"/>
<path d="M24 74 C14 90 18 112 34 122 C32 104 34 88 42 76 Z" fill="url(#{u}wing)"/>
<path d="M104 74 C114 90 110 112 94 122 C96 104 94 88 86 76 Z" fill="url(#{u}wing)"/>
{wing_lines}
<path d="M64 76 C80 76 90 88 90 104 C90 118 78 128 64 128 C50 128 38 118 38 104 C38 88 48 76 64 76 Z" fill="url(#{u}belly)"/>
{feathers}
<path d="M64 46 C72 40 84 38 92 44 C100 52 100 70 90 78 C82 84 70 82 64 76 C58 82 46 84 38 78 C28 70 28 52 36 44 C44 38 56 40 64 46 Z" fill="url(#{u}disc)"/>
<path d="M40 50 Q50 44 60 52" fill="none" stroke="#7A4719" stroke-width="2.6" stroke-linecap="round"/>
<path d="M88 50 Q78 44 68 52" fill="none" stroke="#7A4719" stroke-width="2.6" stroke-linecap="round"/>
<circle cx="50" cy="62" r="11.5" fill="url(#{u}iris)"/><circle cx="78" cy="62" r="11.5" fill="url(#{u}iris)"/>
<circle cx="51" cy="63" r="6" fill="#1B1626"/><circle cx="79" cy="63" r="6" fill="#1B1626"/>
<circle cx="47.5" cy="58.5" r="3" fill="#fff"/><circle cx="75.5" cy="58.5" r="3" fill="#fff"/>
<circle cx="54" cy="66" r="1.3" fill="#fff" opacity=".8"/><circle cx="82" cy="66" r="1.3" fill="#fff" opacity=".8"/>
<circle cx="50" cy="62" r="15" fill="none" stroke="url(#{u}gold)" stroke-width="2.6"/>
<circle cx="78" cy="62" r="15" fill="none" stroke="url(#{u}gold)" stroke-width="2.6"/>
<path d="M60.5 60 Q64 57 67.5 60" fill="none" stroke="url(#{u}gold)" stroke-width="2.4" stroke-linecap="round"/>
<path d="M35 60 L30 57 M93 60 L98 57" stroke="url(#{u}gold)" stroke-width="2.2" stroke-linecap="round"/>
<path d="M64 69 L58.5 75 Q64 84 69.5 75 Z" fill="url(#{u}beak)" stroke="#9A520E" stroke-width=".8" stroke-linejoin="round"/>
<path d="M64 69 L61.5 74 Q64 76 66.5 74 Z" fill="#fff" opacity=".35"/>"""
    return frame(u, bg, body)


def fox():
    u = "fx"
    bg = f"""<radialGradient id="{u}bg" cx=".35" cy=".28" r=".85"><stop offset="0" stop-color="#A6F2DA"/><stop offset=".5" stop-color="#24A98A"/><stop offset="1" stop-color="#0B4E45"/></radialGradient>
<linearGradient id="{u}fur" x1=".3" y1="0" x2=".7" y2="1"><stop offset="0" stop-color="#F7934A"/><stop offset=".55" stop-color="#E2661F"/><stop offset="1" stop-color="#A9420E"/></linearGradient>
<radialGradient id="{u}head" cx=".5" cy=".35" r=".7"><stop offset="0" stop-color="#FBA55E"/><stop offset=".6" stop-color="#E8702A"/><stop offset="1" stop-color="#B74A12"/></radialGradient>
<linearGradient id="{u}white" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FFFFFF"/><stop offset="1" stop-color="#EDE3DA"/></linearGradient>
<linearGradient id="{u}inner" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#F4ECE6"/><stop offset="1" stop-color="#FFFFFF"/></linearGradient>
<radialGradient id="{u}iris" cx=".45" cy=".4" r=".6"><stop offset="0" stop-color="#FFD27A"/><stop offset=".6" stop-color="#D9821C"/><stop offset="1" stop-color="#7A3D06"/></radialGradient>
<linearGradient id="{u}tail" x1="0" y1="1" x2=".3" y2="0"><stop offset="0" stop-color="#B9480F"/><stop offset=".6" stop-color="#EE7A2E"/><stop offset="1" stop-color="#F59A55"/></linearGradient>"""
    fluff = lambda pts: "M" + " L".join(f"{x} {y}" for x, y in pts) + " Z"
    whisk = "".join(f'<path d="M{a}" fill="none" stroke="#fff" stroke-opacity=".8" stroke-width=".7" stroke-linecap="round"/>' for a in (
        "56 82 Q44 80 34 82", "56 84 Q45 85 36 88", "72 82 Q84 80 94 82", "72 84 Q83 85 92 88"))
    fur = "".join(f'<path d="M{a}" fill="none" stroke="#B5501A" stroke-opacity=".22" stroke-width="1" stroke-linecap="round"/>' for a in (
        "58 36 Q60 42 59 47", "64 34 Q64 41 64 46", "70 36 Q68 42 69 47", "38 56 Q42 58 44 62", "90 56 Q86 58 84 62"))
    body = f"""<g transform="translate(9 14) scale(.86)">
<path d="M62 140 C90 132 119 110 123 82 C125 64 118 50 104 43 C109 64 103 86 85 103 C78 109 70 114 60 119 Z" fill="url(#{u}tail)"/>
<path d="M104 43 C117 45 126 56 126 71 C121 66 113 63 105 64 C107 56 106 49 104 43 Z" fill="url(#{u}white)"/>
<path d="M126 71 L123 66 L121.5 72 L117 66.5 L114.5 71" fill="none" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/>
<g fill="none" stroke="#A9420E" stroke-opacity=".55" stroke-width="1.2" stroke-linecap="round"><path d="M112 74 Q108 90 96 104"/><path d="M118 80 Q114 98 100 112"/><path d="M106 70 Q103 84 92 96"/></g>
<path d="M64 90 C86 90 100 104 106 140 H22 C28 104 42 90 64 90 Z" fill="url(#{u}fur)"/>
<path d="{fluff([(64, 90), (72, 94), (78, 100), (75, 103), (82, 110), (78, 113), (84, 122), (82, 140), (46, 140), (44, 122), (50, 113), (46, 110), (53, 103), (50, 100), (56, 94)])}" fill="url(#{u}white)"/>
<path d="M26 58 C21 40 20 20 26 5 C40 11 55 24 60 40 Z" fill="#45200D"/>
<path d="M102 58 C107 40 108 20 102 5 C88 11 73 24 68 40 Z" fill="#45200D"/>
<path d="M29.5 55 C25.5 39 25 22 29 10 C40 16 52 27 56.5 40 Z" fill="url(#{u}fur)"/>
<path d="M98.5 55 C102.5 39 103 22 99 10 C88 16 76 27 71.5 40 Z" fill="url(#{u}fur)"/>
<path d="{fluff([(33, 50), (31, 40), (32, 30), (34, 20), (39, 25), (44, 30), (48, 35), (52, 41), (47, 43), (50, 47), (44, 47), (45, 51), (39, 50), (38, 54)])}" fill="url(#{u}inner)"/>
<path d="{fluff([(95, 50), (97, 40), (96, 30), (94, 20), (89, 25), (84, 30), (80, 35), (76, 41), (81, 43), (78, 47), (84, 47), (83, 51), (89, 50), (90, 54)])}" fill="url(#{u}inner)"/>
<path d="M64 30 C83 30 96 40 100 55 C102 63 104 69 110 75 C102 78 95 82 89 87 C82 93 73 97 64 97 C55 97 46 93 39 87 C33 82 26 78 18 75 C24 69 26 63 28 55 C32 40 45 30 64 30 Z" fill="url(#{u}head)"/>
{fur}
<path d="{fluff([(64, 64), (69, 72), (80, 72), (92, 70), (110, 75), (103, 78), (106, 81), (97, 82), (99, 86), (90, 87), (91, 91), (82, 92), (78, 96), (64, 98), (50, 96), (46, 92), (37, 91), (38, 87), (29, 86), (31, 82), (22, 81), (25, 78), (18, 75), (36, 70), (48, 72), (59, 72)])}" fill="url(#{u}white)"/>
<path d="M57 62 C59 70 60 75 64 78 C68 75 69 70 71 62 C68 58 60 58 57 62 Z" fill="#F08A44" opacity=".8"/>
<circle cx="50" cy="61.5" r="7.2" fill="#2B140A"/><circle cx="78" cy="61.5" r="7.2" fill="#2B140A"/>
<circle cx="50" cy="61.8" r="5.8" fill="url(#{u}iris)"/><circle cx="78" cy="61.8" r="5.8" fill="url(#{u}iris)"/>
<circle cx="50.3" cy="62.2" r="3.1" fill="#140A06"/><circle cx="77.7" cy="62.2" r="3.1" fill="#140A06"/>
<circle cx="47.9" cy="60.8" r="1.8" fill="#fff"/><circle cx="75.9" cy="60.8" r="1.8" fill="#fff"/>
<circle cx="52.4" cy="64.6" r=".9" fill="#fff" opacity=".8"/><circle cx="80.4" cy="64.6" r=".9" fill="#fff" opacity=".8"/>
<path d="M42.3 60 C44.5 53 55.5 53 57.7 60 C54 57.4 46 57.4 42.3 60 Z" fill="#E36D27"/>
<path d="M70.3 60 C72.5 53 83.5 53 85.7 60 C82 57.4 74 57.4 70.3 60 Z" fill="#E36D27"/>
<path d="M42.3 60 C46 57.4 54 57.4 57.7 60 M70.3 60 C74 57.4 82 57.4 85.7 60" fill="none" stroke="#2B140A" stroke-width="1.5" stroke-linecap="round"/>
<path d="M41.6 59.2 L39.6 57.6 M86.4 59.2 L88.4 57.6" stroke="#2B140A" stroke-width="1.3" stroke-linecap="round"/>
<path d="M42 55 Q50 51 58 55" fill="none" stroke="#fff" stroke-opacity=".75" stroke-width="1.6" stroke-linecap="round"/>
<path d="M86 55 Q78 51 70 55" fill="none" stroke="#fff" stroke-opacity=".75" stroke-width="1.6" stroke-linecap="round"/>
<path d="M59 78 Q64 75.5 69 78 Q68 83 64 84 Q60 83 59 78 Z" fill="#1A0F0C"/>
<ellipse cx="62.4" cy="77.9" rx="1.9" ry=".9" fill="#fff" opacity=".6"/>
<path d="M64 84 V86.5 M64 86.5 Q60.5 89.5 57.5 87.5 M64 86.5 Q67.5 89.5 70.5 87.5" fill="none" stroke="#3A221A" stroke-width="1.3" stroke-linecap="round"/>
{whisk}
<g fill="none" stroke="#1A1416" stroke-width="1.8"><circle cx="50" cy="61" r="12"/><circle cx="78" cy="61" r="12"/>
<path d="M62 59.5 Q64 57.5 66 59.5"/><path d="M38 60 L30 57.5 M90 60 L98 57.5" stroke-linecap="round"/></g>
<path d="M42 54 A12 12 0 0 1 56 52" fill="none" stroke="#fff" stroke-opacity=".55" stroke-width="1.4" stroke-linecap="round"/>
<path d="M70 54 A12 12 0 0 1 84 52" fill="none" stroke="#fff" stroke-opacity=".55" stroke-width="1.4" stroke-linecap="round"/></g>"""
    return frame(u, bg, body)


def sigma():
    u = "sg"
    _, d = SIGMA(0)
    bg = f"""<radialGradient id="{u}bg" cx=".5" cy=".42" r=".7"><stop offset="0" stop-color="#4A58F0"/><stop offset=".55" stop-color="#2A2FA8"/><stop offset="1" stop-color="#121548"/></radialGradient>
<radialGradient id="{u}glow" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="#8FB6FF" stop-opacity=".9"/><stop offset="1" stop-color="#8FB6FF" stop-opacity="0"/></radialGradient>
<linearGradient id="{u}face" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#FFFFFF"/><stop offset=".45" stop-color="#C9DCFF"/><stop offset="1" stop-color="#7EA6FF"/></linearGradient>
<linearGradient id="{u}side" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#2B36C9"/><stop offset="1" stop-color="#4C7BE6"/></linearGradient>
<linearGradient id="{u}flame" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FF4A2A"/><stop offset="1" stop-color="#FFD43B"/></linearGradient>"""
    s = 0.52
    tx, ty = 64 - 81 * s / 2, 64 - 50 * s + 4
    extrude = "".join(
        f'<path d="{d}" fill="url(#{u}side)" transform="translate({tx + k * .5:.2f} {ty + k * .9:.2f}) scale({s})"/>'
        for k in range(8, 0, -1))
    body = f"""
<circle cx="64" cy="66" r="44" fill="url(#{u}glow)"/>
<g fill="none" stroke="#B9CCFF" stroke-opacity=".35" stroke-width="1"><circle cx="64" cy="66" r="30"/><circle cx="64" cy="66" r="38" stroke-dasharray="2 5"/></g>
<ellipse cx="64" cy="70" rx="50" ry="15" fill="none" stroke="#9EC0FF" stroke-opacity=".75" stroke-width="1.6" transform="rotate(-18 64 70)"/>
<circle cx="110" cy="56" r="3.2" fill="#FFD43B"/><circle cx="20" cy="84" r="2.4" fill="#fff" opacity=".9"/>
{extrude}
<path d="{d}" fill="url(#{u}face)" transform="translate({tx:.2f} {ty:.2f}) scale({s})"/>
<path d="M{tx + 2:.1f} {ty + 1.5:.1f} H{tx + 40:.1f}" stroke="#fff" stroke-width="1.6" stroke-linecap="round" opacity=".9"/>
<g fill="#fff"><path d="M26 34 L28 40 L34 42 L28 44 L26 50 L24 44 L18 42 L24 40 Z" opacity=".85"/><path d="M98 98 L99.4 102 L103 103 L99.4 104.4 L98 108 L96.6 104.4 L93 103 L96.6 102 Z" opacity=".7"/></g>"""
    return frame(u, bg, body)
