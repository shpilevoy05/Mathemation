# -*- coding: utf-8 -*-
"""Страница третьей итерации: доработанные аватары, анимированный премиум-набор,
финальные знаки лиг."""
import json, re
import anim, leagues
from lib import LEAGUES

D = json.load(open("out/data.json", encoding="utf-8"))


def strip(svg, cls, size):
    svg = svg.replace('<svg xmlns="http://www.w3.org/2000/svg" ',
                      f'<svg xmlns="http://www.w3.org/2000/svg" class="{cls}" ', 1)
    svg = re.sub(r'width="\d+" height="\d+"', f'width="{size}" height="{size}"', svg, count=1)
    return svg.replace("\n", "")


def by_key(group):
    return {i["key"]: i for i in D[group]}


AV, FR = by_key("avatars"), by_key("frames")
ANIM_KEYS = {"tesseract", "fractal", "crystal", "blackhole", "comet", "origami", "mobius"}
CONCEPT_OF = {c["item"]: c for c in anim.CONCEPTS if c["target"] == "avatar-anim"}


def compose(frame_key, size=144, avatar="owl"):
    inner = round(size * 104 / 160)
    pad = round(size * 28 / 160)
    return (f'<div class="compose" style="width:{size}px;height:{size}px">'
            f'<span class="compose__av" style="inset:{pad}px">{strip(AV[avatar]["svg"], "art", inner)}</span>'
            f'{strip(FR[frame_key]["svg"], "art", size)}</div>')


TIER_LABEL = {"base": ("бесплатно", "free"), "paid": ("покупной", "paid"),
              "anim": ("анимированный", "anim")}
NOTE = {
    "cat": "новый", "penguin": "новый", "dragon": "новый",
    "icosa": "новый", "spiral": "новый", "mobius": "новый",
    "crystal": "правка",
}


def sec_avatars(tier):
    cards = []
    for i in D["avatars"]:
        if i["tier"] != tier:
            continue
        cls = "card" + (f' d-av-{i["key"]}' if i["key"] in ANIM_KEYS else "")
        note = NOTE.get(i["key"])
        badge = f'<span class="mark">{note}</span>' if note else ""
        cards.append(f'<figure class="{cls}">{badge}{strip(i["svg"], "art", 96)}'
                     f'<figcaption><b>{i["ru"]}</b><span>{i["cat"]}</span></figcaption></figure>')
    return "".join(cards)


def sec_anim_avatars():
    out = []
    for n, key in enumerate(["tesseract", "fractal", "crystal", "blackhole",
                             "comet", "origami", "mobius"], 1):
        c = CONCEPT_OF[key]
        out.append(
            f'<article class="anim d-{c["id"]}">'
            f'<div class="anim__stage">{strip(AV[key]["svg"], "art", 128)}</div>'
            f'<div class="anim__body">'
            f'<div class="anim__meta"><span class="tag">AN-{n:02d}</span>'
            f'<span class="badge badge--anim">анимированный</span></div>'
            f'<h4>{c["ru"]}</h4><p>{c["idea"]}</p>'
            f'<div class="spec">{c["dur"]} · {c["ease"]} · {c["loop"]}</div>'
            f'</div></article>')
    return "".join(out)


def sec_anim_frames(targets, prefix):
    out = []
    n = 0
    for c in anim.CONCEPTS:
        if c["target"] not in targets:
            continue
        n += 1
        stage = compose(c["item"]) if c["target"] == "frame" else strip(AV[c["item"]]["svg"], "art", 116)
        out.append(
            f'<article class="anim d-{c["id"]}">'
            f'<div class="anim__stage">{stage}</div>'
            f'<div class="anim__body">'
            f'<div class="anim__meta"><span class="tag">{prefix}-{n:02d}</span></div>'
            f'<h4>{c["ru"]}</h4><p>{c["idea"]}</p>'
            f'<div class="spec">{c["dur"]} · {c["ease"]} · {c["loop"]}</div>'
            f'</div></article>')
    return "".join(out)


def sec_frames():
    return "".join(f'<figure class="card">{compose(i["key"], 124, "pi")}'
                   f'<figcaption><b>{i["ru"]}</b><span>{i["cat"]}</span></figcaption></figure>'
                   for i in D["frames"])


def sec_leagues():
    rows = []
    for lgru in [LEAGUES[k]["ru"] for k in leagues.ORDER]:
        cells = []
        for it in D["leagues"]:
            if it["league"] != lgru:
                continue
            lab = {"—": "базовый знак", "1": "1 место · золото",
                   "2": "2 место · серебро", "3": "3 место · бронза"}[it["place"]]
            cells.append(f'<div class="lg-cell">{strip(it["svg"], "art", 84)}<span>{lab}</span></div>')
        rows.append(f'<div class="lg-row"><h4>{lgru}</h4><div class="lg-cells">{"".join(cells)}</div></div>')
    return "".join(rows)


CSS = r"""
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Unbounded:wght@500;700&family=Golos+Text:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap">
<style>
:root{
  --bg:#EBEFF9; --surface:#FFFFFF; --surface-2:#F5F7FE; --ink:#10162A; --muted:#66708C;
  --line:#DCE3F6; --line-2:#EDF0F9; --accent:#4F6BEA; --accent-soft:#E2E8FB;
  --ok:#0E9A64; --ok-soft:#DFF3E9; --gold:#B98407; --gold-soft:#FAEFD9;
  --shadow:0 18px 40px -30px rgba(16,22,42,.55);
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --bg:#0C1020; --surface:#151B2E; --surface-2:#111729; --ink:#E8EDFC; --muted:#8B96B8;
    --line:#26304C; --line-2:#1C2440; --accent:#8FA2FF; --accent-soft:#1E2745;
    --ok:#5FD6A4; --ok-soft:#123528; --gold:#F5C63C; --gold-soft:#332708;
    --shadow:0 18px 40px -28px rgba(0,0,0,.8);
  }
}
:root[data-theme="dark"]{
  --bg:#0C1020; --surface:#151B2E; --surface-2:#111729; --ink:#E8EDFC; --muted:#8B96B8;
  --line:#26304C; --line-2:#1C2440; --accent:#8FA2FF; --accent-soft:#1E2745;
  --ok:#5FD6A4; --ok-soft:#123528; --gold:#F5C63C; --gold-soft:#332708;
  --shadow:0 18px 40px -28px rgba(0,0,0,.8);
}

*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:400 15px/1.6 "Golos Text","Segoe UI",system-ui,sans-serif;-webkit-font-smoothing:antialiased}
.wrap{max-width:1180px;margin:0 auto;padding:0 28px 96px}
h1,h2,h3,h4{margin:0;text-wrap:balance}
h1{font:700 clamp(30px,5vw,52px)/1.06 Unbounded,"Golos Text",sans-serif;letter-spacing:-.02em}
h2{font:500 clamp(21px,3vw,29px)/1.2 Unbounded,"Golos Text",sans-serif;letter-spacing:-.01em}
h3{font:500 17px Unbounded,"Golos Text",sans-serif}
h4{font:600 16px/1.3 "Golos Text",sans-serif}
p{margin:0}
.eyebrow{font:600 11px/1 "JetBrains Mono",ui-monospace,monospace;letter-spacing:.16em;
  text-transform:uppercase;color:var(--accent)}
.art{display:block}

header.hero{padding:70px 0 36px;display:grid;gap:20px}
.hero .lede{max-width:64ch;color:var(--muted);font-size:17px}

.bar{position:sticky;top:0;z-index:20;margin:0 -28px 40px;padding:12px 28px;
  background:color-mix(in srgb,var(--bg) 88%,transparent);backdrop-filter:blur(12px);
  border-bottom:1px solid var(--line);display:flex;flex-wrap:wrap;gap:8px;align-items:center}
.bar a{color:var(--muted);text-decoration:none;font-size:13.5px;font-weight:500;
  padding:7px 12px;border-radius:8px}
.bar a:hover,.bar a:focus-visible{background:var(--surface);color:var(--ink)}
#pause{margin-left:auto;border:1px solid var(--line);background:var(--surface);color:var(--muted);
  border-radius:9px;padding:8px 14px;font:600 13px "Golos Text",sans-serif;cursor:pointer}

section{margin:0 0 72px;display:grid;gap:24px;scroll-margin-top:76px}
.sec-head{display:grid;gap:8px;max-width:68ch}
.sec-head p{color:var(--muted)}
.tier{display:grid;gap:14px}
.tier__head{display:flex;gap:12px;align-items:baseline;flex-wrap:wrap}
.tier__head p{color:var(--muted);font-size:13.5px}

.compose{position:relative}
.compose .art{position:absolute;inset:0}
.compose__av{position:absolute}
.compose__av .art{position:static}

.changes{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(300px,1fr))}
.change{background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:18px 20px;
  display:grid;gap:6px;box-shadow:var(--shadow)}
.change b{font-weight:600;font-size:14.5px}
.change p{color:var(--muted);font-size:13.5px}

.grid{display:grid;gap:14px;grid-template-columns:repeat(auto-fill,minmax(140px,1fr))}
.card{margin:0;background:var(--surface);border:1px solid var(--line);border-radius:18px;
  padding:16px 12px 12px;display:grid;gap:10px;justify-items:center;box-shadow:var(--shadow);
  position:relative}
.card figcaption{display:grid;gap:2px;text-align:center}
.card figcaption b{font-weight:600;font-size:13px}
.card figcaption span{font-size:11px;color:var(--muted)}
.mark{position:absolute;top:10px;right:10px;font:600 9.5px/1 "JetBrains Mono",monospace;
  letter-spacing:.06em;color:var(--accent);background:var(--accent-soft);padding:4px 6px;border-radius:5px}

.anims{display:grid;gap:14px;grid-template-columns:repeat(auto-fill,minmax(330px,1fr))}
.anim{background:var(--surface);border:1px solid var(--line);border-radius:18px;overflow:hidden;
  display:grid;grid-template-rows:auto 1fr;box-shadow:var(--shadow)}
.anim__stage{background:var(--surface-2);border-bottom:1px solid var(--line-2);padding:24px;
  display:grid;place-items:center;min-height:196px}
.anim__stage .art{overflow:visible}
.anim__body{padding:16px 20px 20px;display:grid;gap:8px;align-content:start}
.anim__meta{display:flex;gap:8px;align-items:center}
.tag{font:600 10px/1 "JetBrains Mono",monospace;letter-spacing:.1em;color:var(--accent);
  background:var(--accent-soft);padding:5px 8px;border-radius:6px}
.badge{font-size:11px;font-weight:600;padding:5px 9px;border-radius:6px}
.badge--anim{color:var(--gold);background:var(--gold-soft)}
.anim__body p{color:var(--muted);font-size:13.5px}
.spec{font:400 11.5px/1.6 "JetBrains Mono",monospace;background:var(--surface-2);
  border:1px solid var(--line-2);border-radius:9px;padding:8px 10px}

.lg-row{background:var(--surface);border:1px solid var(--line);border-radius:18px;padding:20px 22px;
  display:grid;gap:14px;box-shadow:var(--shadow)}
.lg-row h4{font:500 15px Unbounded,"Golos Text",sans-serif}
.lg-cells{display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(150px,1fr))}
.lg-cell{display:grid;gap:8px;justify-items:center;padding:14px 8px;border-radius:14px;
  background:var(--surface-2)}
.lg-cell>span{font-size:11.5px;color:var(--muted)}

.howto{background:var(--surface);border:1px solid var(--line);border-radius:22px;padding:28px;
  display:grid;gap:18px;box-shadow:var(--shadow)}
.steps{counter-reset:s;display:grid;gap:14px;margin:0;padding:0;list-style:none}
.steps li{display:grid;grid-template-columns:30px 1fr;gap:14px;align-items:start}
.steps li::before{counter-increment:s;content:counter(s,decimal-leading-zero);
  font:600 12px/26px "JetBrains Mono",monospace;color:var(--accent);background:var(--accent-soft);
  border-radius:8px;text-align:center;height:26px}
.steps b{font-weight:600}
.steps span{color:var(--muted);display:block;font-size:13.5px;margin-top:2px}
code{font:400 12.5px "JetBrains Mono",monospace;background:var(--surface-2);
  border:1px solid var(--line-2);border-radius:6px;padding:2px 6px}
footer{color:var(--muted);font-size:13px;border-top:1px solid var(--line);padding-top:24px}

/* ═══ АНИМАЦИИ ═══ */
@keyframes mfSpin{to{transform:rotate(360deg)}}
@keyframes mfSpinR{to{transform:rotate(-360deg)}}
@keyframes mfBreath{0%,100%{transform:scale(1)}50%{transform:scale(1.045)}}
@keyframes mfStretch{0%,100%{transform:scaleY(1)}50%{transform:scaleY(1.22)}}
@keyframes mfBlink{0%,100%{opacity:.3}18%{opacity:1}45%{opacity:.3}}
@keyframes mfTwinkle{0%,100%{opacity:.2}50%{opacity:1}}
@keyframes mfGlow{0%,100%{opacity:.32}28%{opacity:1}60%{opacity:.32}}
@keyframes mfPop{0%,100%{transform:scale(1)}35%{transform:scale(1.3)}}
@keyframes mfTick{0%,100%{transform:scale(1)}50%{transform:scale(1.09)}}
@keyframes mfDepart{0%,100%{transform:scale(1)}45%{transform:scale(1.26)}}
@keyframes mfTail{0%,100%{stroke-dashoffset:0}45%{stroke-dashoffset:-32}}
@keyframes mfDash{0%,100%{transform:translate(0,0)}45%{transform:translate(7px,-7px)}}
@keyframes mfTailFade{0%,100%{opacity:.55}45%{opacity:1}}
@keyframes mfDrift{0%,100%{transform:translate(0,0);opacity:.7}
  45%{transform:translate(-7px,7px);opacity:.2}}
@keyframes mfFlap{0%,100%{transform:scaleX(1)}50%{transform:scaleX(.74)}}
@keyframes mfFlow{to{stroke-dashoffset:-12}}
@keyframes mfFlow2{to{stroke-dashoffset:-28}}
@keyframes mfShine{0%,100%{opacity:.25;transform:translate(-6px,0)}
  40%{opacity:.95;transform:translate(6px,0)}}
@keyframes mfAppear{0%{transform:scale(.82);opacity:0}9%{transform:scale(1.05);opacity:1}
  16%,100%{transform:scale(1);opacity:1}}
@keyframes mfWin{0%,62%,100%{transform:translateY(0) scaleY(1)}
  70%{transform:translateY(-10px) scaleY(1.05)}79%{transform:translateY(0) scaleY(.93)}
  86%{transform:translateY(0) scaleY(1)}}

/* центр вращения: у элементов внутри SVG он по умолчанию 0 0, а не центр */
svg .st-r0,svg .st-r1,svg .st-moon,svg .gr-ring,svg .cm-orbit,svg .cm-head,
svg .bt-pulse,svg .au-band,svg .cd-orbit,svg .cd-tick,svg .nb-glow,svg .bl-flower{
  transform-box:view-box;transform-origin:80px 80px}
svg .tsr-inner,svg .tsr-outer,svg .bh-disc,svg .bh-core,svg .cmv-head,svg .cmv-tail,
svg .cmv-dust,svg .orx-wing,svg .cr-shine{transform-box:view-box;transform-origin:64px 64px}

.d-saturn-orbit .st-r0{animation:mfSpin 18s linear infinite}
.d-saturn-orbit .st-r1{animation:mfSpinR 26s linear infinite}
.d-saturn-orbit .st-moon{animation:mfSpin 14s linear infinite}
.d-gears-mesh .gr-ring{animation:mfSpin 24s linear infinite}
.d-comet-flight .cm-orbit{animation:mfSpin 4s linear infinite}
.d-comet-flight .cm-head{animation:mfDepart 4s ease-in-out infinite}
.d-comet-flight .cm-tail{stroke-dasharray:62 100;animation:mfTail 4s ease-in-out infinite}
.d-comet-flight .cm-dust{animation:mfTwinkle 4s ease-in-out infinite;animation-delay:calc(var(--i)*-120ms)}
.d-bitflow-pulse .bt-pulse{animation:mfSpin 2.4s linear infinite}
.d-bitflow-pulse .bt-bit{animation:mfBlink 2.4s linear infinite;animation-delay:calc(var(--i)*-100ms)}
.d-aurora-ribbons .au-band{animation:mfSpin calc(12s + var(--i)*4s) linear infinite}
.d-aurora-ribbons .au-band:nth-of-type(even){animation-direction:reverse}
.d-coord-scan .cd-orbit{animation:mfSpin 30s linear infinite}
.d-coord-scan .cd-tick{animation:mfTick 2.6s ease-in-out infinite}
.d-flame-breath .fl-tongue>path:first-child{transform-box:fill-box;transform-origin:50% 100%;
  animation:mfStretch 1.6s ease-in-out infinite;animation-delay:calc(var(--i)*-80ms)}
.d-nebula-pulse .nb-glow{animation:mfBreath 3.6s ease-in-out infinite}
.d-nebula-pulse .nb-star{animation:mfTwinkle calc(1.2s + var(--i)*.2s) ease-in-out infinite}
.d-bloom-open .bl-flower{transform-origin:var(--cx) var(--cy);
  animation:mfPop 2.4s cubic-bezier(.34,1.56,.64,1) infinite;animation-delay:calc(var(--i)*-.2s)}
.d-avatar-appear .art{animation:mfAppear 3.4s cubic-bezier(.34,1.56,.64,1) infinite}
.d-avatar-win .art{animation:mfWin 2.8s cubic-bezier(.22,1.2,.36,1) infinite}

/* анимированные аватары */
.d-av-tesseract .tsr-inner{animation:mfSpinR 12s linear infinite}
.d-av-tesseract .tsr-outer{animation:mfSpin 24s linear infinite}
.d-av-tesseract .tsr-link{animation:mfGlow 3s ease-in-out infinite;animation-delay:calc(var(--i)*-.42s)}
.d-av-fractal .frc-tri{animation:mfGlow 2.8s ease-in-out infinite;animation-delay:calc(var(--i)*-90ms)}
.d-av-crystal .cr-facet{animation:mfGlow 4.2s ease-in-out infinite;animation-delay:calc(var(--i)*-.55s)}
.d-av-crystal .cr-shine{animation:mfShine 4.2s ease-in-out infinite}
.d-av-blackhole .bh-flow{animation:mfFlow 2.6s linear infinite}
.d-av-blackhole .bh-core{animation:mfBreath 4s ease-in-out infinite}
.d-av-blackhole .bh-star{animation:mfTwinkle calc(1.4s + var(--i)*.3s) ease-in-out infinite}
.d-av-comet .cmv-head{animation:mfDash 3.4s cubic-bezier(.3,0,.2,1) infinite}
.d-av-comet .cmv-tail{animation:mfTailFade 3.4s ease-in-out infinite}
.d-av-comet .cmv-dust{animation:mfDrift 3.4s ease-in-out infinite;animation-delay:calc(var(--i)*-.2s)}
.d-av-origami .orx-wing--l{animation:mfFlap 2.6s ease-in-out infinite}
.d-av-origami .orx-wing--r{animation:mfFlap 2.6s ease-in-out infinite;animation-delay:-.13s}
.d-av-mobius .mb-flow{animation:mfFlow2 6s linear infinite}
.d-av-mobius .mb-face{animation:mfGlow 6s ease-in-out infinite;animation-delay:calc(var(--i)*-2s)}

body.paused .anim *,body.paused .card *{animation-play-state:paused!important}
@media (prefers-reduced-motion:reduce){.anim *,.card *{animation:none!important}}
@media (max-width:640px){.wrap{padding:0 16px 64px}.bar{margin:0 -16px 28px;padding:10px 16px}}
</style>
"""

JS = r"""
<script>
(function(){
  var p=document.getElementById('pause');
  if(p) p.addEventListener('click',function(){
    document.body.classList.toggle('paused');
    var on=document.body.classList.contains('paused');
    p.textContent=on?'Продолжить анимации':'Остановить анимации';
    p.setAttribute('aria-pressed',String(on));
  });
})();
</script>
"""

HEAD = "<title>Аватары, рамки и лиги</title>"


def body():
    return f"""
<div class="wrap">
<header class="hero">
  <span class="eyebrow">Mathemation · итерация 5 · трек «Призма»</span>
  <h1>Аватары, рамки и лиги</h1>
  <p class="lede">Лестница лиг закрыта целиком: добавлены Дельта и Гамма, теперь шесть знаков
  от треугольника до восьмигранника. Аватаров 25 в трёх уровнях, семь из них анимированные.</p>
</header>

<div class="bar">
  <a href="#avatars">Аватары</a>
  <a href="#animated">Анимированные</a>
  <a href="#leagues">Лиги</a>
  <a href="#frames">Рамки</a>
  <a href="#motion">Анимации рамок</a>
  <button id="pause" aria-pressed="false">Остановить анимации</button>
</div>

<section id="changes">
  <div class="sec-head">
    <span class="eyebrow">Что изменилось</span>
    <h2>По вашим правкам</h2>
  </div>
  <div class="changes">
    <div class="change"><b>Дельта и Гамма дорисованы</b><p>Лестница больше не обрывается:
      шесть знаков вместо четырёх. Форма пластины теперь работает как шкала —
      треугольник, ромб, шестигранник, щит, пентагон, восьмигранник: чем выше лига,
      тем сложнее силуэт.</p></div>
    <div class="change"><b>δ и γ в том же языке</b><p>Только прямые, плоские срезы,
      та же толщина штриха и то же выравнивание по контуру, что у остальных четырёх.
      У γ хвост с изломом уходит влево-вниз — иначе в гранёном начертании она
      неотличима от латинской Y.</p></div>
    <div class="change"><b>Что было раньше</b><p>Альфа с ромбовидной чашей, символы
      выровнены по собственному bbox, Кристалл без центрального шва, шесть новых
      аватаров (Кот, Пингвин, Дракон, Икосаэдр, Спираль, Лента Мёбиуса).</p></div>
  </div>
</section>

<section id="avatars">
  <div class="sec-head">
    <span class="eyebrow">25 позиций · три уровня</span>
    <h2>Аватары</h2>
    <p>Уровень задаёт не только цену, но и роль: бесплатные — нейтральные знаки, которые
    не навязывают характер; покупные — персонажи; анимированные — геометрия и космос,
    где движение осмысленно.</p>
  </div>

  <div class="tier">
    <div class="tier__head"><h3>Бесплатно</h3>
      <p>Доступны сразу. Нейтральные математические знаки — ничего не сообщают о владельце,
      кроме того, что он здесь учится.</p></div>
    <div class="grid">{sec_avatars("base")}</div>
  </div>

  <div class="tier">
    <div class="tier__head"><h3>Покупные</h3>
      <p>Звери, персонажи и «спокойная» геометрия. Сова, Робот и Космонавт без изменений.</p></div>
    <div class="grid">{sec_avatars("paid")}</div>
  </div>

  <div class="tier">
    <div class="tier__head"><h3>Анимированные</h3>
      <p>Самый дорогой уровень, семь позиций. Здесь и ниже они двигаются по-настоящему.</p></div>
    <div class="grid">{sec_avatars("anim")}</div>
  </div>
</section>

<section id="animated">
  <div class="sec-head">
    <span class="eyebrow">7 концептов · премиум-набор</span>
    <h2>Анимированные аватары</h2>
    <p>У каждого движение вырастает из самой фигуры: тессеракт разворачивается, фрактал
    достраивает себя, кристалл ловит свет, дыра затягивает диск, комета разгоняется,
    журавль машет крыльями, по ленте Мёбиуса бежит метка. Ни один не крутится просто так.</p>
  </div>
  <div class="anims">{sec_anim_avatars()}</div>
</section>

<section id="leagues">
  <div class="sec-head">
    <span class="eyebrow">6 лиг × 4 статуса</span>
    <h2>Символы лиг</h2>
    <p>Треугольник, ромб, шестигранник, щит, пентагон, октагон — шесть силуэтов,
    различимых в 24 px, и они усложняются вверх по лестнице.
    Место читается металлом пластины и жетоном с номером; цвет лиги при этом не меняется.</p>
  </div>
  {sec_leagues()}
</section>

<section id="frames">
  <div class="sec-head">
    <span class="eyebrow">14 рамок</span>
    <h2>Рамки</h2>
    <p>Рамка — отдельный слой 160 × 160 с отверстием Ø 104 в центре, сочетается с любым аватаром.
    «Цепь» заменена обратно на «Механизм».</p>
  </div>
  <div class="grid">{sec_frames()}</div>
</section>

<section id="motion">
  <div class="sec-head">
    <span class="eyebrow">9 концептов рамок + 2 событийных</span>
    <h2>Анимации рамок</h2>
    <p>Всё вращается вокруг центра аватара. Пламя, Туманность и Распускание не тронуты.</p>
  </div>
  <div class="anims">{sec_anim_frames({"frame"}, "FR")}</div>
  <div class="anims">{sec_anim_frames({"avatar"}, "EV")}</div>
</section>

<section id="figma">
  <div class="sec-head">
    <span class="eyebrow">Локально, без облака</span>
    <h2>Как открыть в Figma</h2>
  </div>
  <div class="howto">
    <ol class="steps">
      <li><div><b>Figma Desktop → <code>Plugins → Development → Import plugin from manifest…</code></b>
        <span>Выбрать <code>design/figma-plugin/manifest.json</code>. Если плагин уже импортирован —
        просто запустите, он подхватит новый код.</span></div></li>
      <li><div><b>Отметить, что собирать</b>
        <span>Основной набор, варианты знаков лиг, кадры анимаций — три переключателя.</span></div></li>
      <li><div><b>Компоненты с вариантами</b>
        <span>«Аватар» (19 вариантов), «Рамка» (14), «Лига + Место» (16). Плюс полосы кадров
        со Smart Animate — Present проигрывает движение.</span></div></li>
    </ol>
  </div>
</section>

<footer>Кадры в Figma задают движение приблизительно — точные тайминги и кривые берутся
из <code>ANIMATIONS.md</code>. Там же CSS с центром вращения: у элементов внутри SVG
<code>transform-origin</code> по умолчанию <code>0 0</code>, и без явного центра всё уезжает
за кадр.</footer>
</div>
"""


def main():
    b = body()
    open("out/page_body.html", "w", encoding="utf-8").write(HEAD + CSS + b + JS)
    open("out/preview.html", "w", encoding="utf-8").write(
        '<!doctype html><html lang="ru"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        + HEAD + CSS + '</head><body>' + b + JS + '</body></html>')
    print("page:", len(b) // 1024, "KB")


if __name__ == "__main__":
    main()
