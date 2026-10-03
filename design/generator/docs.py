# -*- coding: utf-8 -*-
"""ANIMATIONS.md и README.md."""
import anim, avatars, frames, leagues, glyphs
from lib import LEAGUES

ORIGIN_NOTE = """> **Главное правило.** У элементов внутри SVG браузер ставит
> `transform-origin: 0 0` — левый верхний угол, а не центр, как у обычных
> HTML-элементов. Без явного центра любое вращение уводит фигуру за кадр,
> а масштаб превращается в сдвиг вправо-вниз. Поэтому каждому анимируемому
> элементу рамки нужны две строки:
>
> ```css
> transform-box: view-box;      /* координаты из viewBox, а не из бокса элемента */
> transform-origin: 80px 80px;  /* центр холста рамки 160×160 */
> ```
>
> Для аватара 128×128 центр — `64px 64px`. Корневой `<svg>` — обычный CSS-бокс,
> ему хватает `transform-origin: 50% 50%` по умолчанию."""

CSS_SNIPPET = {
 "saturn-orbit": """.frame-saturn .st-r0,
.frame-saturn .st-r1,
.frame-saturn .st-moon { transform-box: view-box; transform-origin: 80px 80px; }

.frame-saturn .st-r0   { animation: spin 18s linear infinite; }
.frame-saturn .st-r1   { animation: spin 26s linear infinite reverse; }
.frame-saturn .st-moon { animation: spin 14s linear infinite; }""",
 "gears-mesh": """.frame-gears .gr-ring {
  transform-box: view-box; transform-origin: 80px 80px;
  animation: spin 24s linear infinite;
}
/* Зубья, обод и заклёпки лежат в одной группе .gr-ring и вращаются вместе —
   расхождения скоростей больше нет. */""",
 "comet-flight": """.frame-comet .cm-orbit,
.frame-comet .cm-head { transform-box: view-box; transform-origin: 80px 80px; }

.frame-comet .cm-orbit { animation: orbit 4s linear infinite; }      /* облёт аватара */
.frame-comet .cm-head  { animation: depart 4s ease-in-out infinite; } /* уход наружу */
.frame-comet .cm-tail  { stroke-dasharray: 62 100;                    /* pathLength=100 */
                         animation: tail 4s ease-in-out infinite; }

@keyframes orbit  { to { transform: rotate(360deg) } }
@keyframes depart { 0%,100% { transform: scale(1) }  45% { transform: scale(1.26) } }
@keyframes tail   { 0%,100% { stroke-dashoffset: 0 } 45% { stroke-dashoffset: -32 } }

/* Аватар лежит ОТДЕЛЬНЫМ слоем под рамкой и не входит в .cm-orbit —
   поэтому он остаётся неподвижным. */""",
 "bitflow-pulse": """.frame-bitflow .bt-pulse { transform-box: view-box; transform-origin: 80px 80px;
                           animation: spin 2.4s linear infinite; }
.frame-bitflow .bt-bit   { animation: blink 2.4s linear infinite;
                           animation-delay: calc(var(--i) * -100ms); }""",
 "aurora-ribbons": """.frame-aurora .au-band {
  transform-box: view-box; transform-origin: 80px 80px;
  animation: spin calc(12s + var(--i) * 4s) linear infinite;
}
.frame-aurora .au-band:nth-of-type(even) { animation-direction: reverse; }""",
 "coord-scan": """.frame-coordinates .cd-orbit,
.frame-coordinates .cd-tick { transform-box: view-box; transform-origin: 80px 80px; }

.frame-coordinates .cd-orbit { animation: spin 30s linear infinite; }
.frame-coordinates .cd-tick  { animation: tick 2.6s ease-in-out infinite; }

@keyframes tick { 0%,100% { transform: scale(1) } 50% { transform: scale(1.09) } }
/* Масштаб от центра аватара — оси растут наружу симметрично.
   На событии XP: animation: tick 400ms cubic-bezier(.34,1.56,.64,1) 1; */""",
 "flame-breath": """.frame-flame .fl-tongue > path:first-child {
  transform-box: fill-box;        /* здесь центр — сам язык, а не холст */
  transform-origin: 50% 100%;     /* основание языка */
  animation: stretch 1.6s ease-in-out infinite;
  animation-delay: calc(var(--i) * -80ms);
}""",
 "nebula-pulse": """.frame-nebula .nb-glow { transform-box: view-box; transform-origin: 80px 80px;
                        animation: breathe 3.6s ease-in-out infinite; }
.frame-nebula .nb-star { animation: twinkle calc(1.2s + var(--i) * .2s) ease-in-out infinite; }""",
 "bloom-open": """.frame-bloom .bl-flower {
  transform-box: view-box;
  transform-origin: var(--cx) var(--cy);   /* центр конкретного цветка, из разметки */
  animation: pop 640ms cubic-bezier(.34,1.56,.64,1) 1;
  animation-delay: calc(var(--i) * 45ms);
}""",
 "avatar-appear": """.avatar-art { animation: appear 320ms cubic-bezier(.34,1.56,.64,1) 1; }
@keyframes appear { from { transform: scale(.82); opacity: 0 }
                    60%  { transform: scale(1.04); opacity: 1 }
                    to   { transform: scale(1) } }""",
 "avatar-win": """.avatar-badge.is-win .avatar-art { animation: win 520ms cubic-bezier(.22,1.2,.36,1) 1; }
@keyframes win { 0%,100% { transform: translateY(0) scaleY(1) }
                 45%     { transform: translateY(-9px) scaleY(1.05) }
                 70%     { transform: translateY(0) scaleY(.93) } }""",

 "av-tesseract": """.avatar-tesseract .tsr-inner,
.avatar-tesseract .tsr-outer { transform-box: view-box; transform-origin: 64px 64px; }

.avatar-tesseract .tsr-inner { animation: spin 12s linear infinite reverse; }
.avatar-tesseract .tsr-outer { animation: spin 24s linear infinite; }
.avatar-tesseract .tsr-link  { animation: glow 3s ease-in-out infinite;
                               animation-delay: calc(var(--i) * -.42s); }""",
 "av-fractal": """.avatar-fractal .frc-tri {
  animation: glow 2.8s ease-in-out infinite;
  animation-delay: calc(var(--i) * -90ms);   /* --i — порядок построения Серпинского */
}""",
 "av-crystal": """.avatar-crystal .cr-facet { animation: glow 4.2s ease-in-out infinite;
                            animation-delay: calc(var(--i) * -.55s); }
.avatar-crystal .cr-shine { transform-box: view-box; transform-origin: 64px 64px;
                            animation: shine 4.2s ease-in-out infinite; }
@keyframes shine { 0%,100% { opacity: .25; transform: translate(-6px,0) }
                   40%     { opacity: .95; transform: translate(6px,0) } }""",
 "av-blackhole": """/* Диск не вращается целиком — по нему «течёт» вещество:
   pathLength=100 делает штрих в процентах, а не в пикселях. */
.avatar-blackhole .bh-flow { animation: flow 2.6s linear infinite; }
.avatar-blackhole .bh-core { transform-box: view-box; transform-origin: 64px 64px;
                             animation: breathe 4s ease-in-out infinite; }
.avatar-blackhole .bh-star { animation: twinkle calc(1.4s + var(--i) * .3s) ease-in-out infinite; }

@keyframes flow { to { stroke-dashoffset: -12 } }""",
 "av-comet": """.avatar-comet .cmv-head,
.avatar-comet .cmv-dust { transform-box: view-box; transform-origin: 64px 64px; }

.avatar-comet .cmv-head { animation: dash 3.4s cubic-bezier(.3,0,.2,1) infinite; }
.avatar-comet .cmv-tail { animation: tailfade 3.4s ease-in-out infinite; }
.avatar-comet .cmv-dust { animation: drift 3.4s ease-in-out infinite;
                          animation-delay: calc(var(--i) * -.2s); }

@keyframes dash     { 0%,100% { transform: translate(0,0) } 45% { transform: translate(7px,-7px) } }
@keyframes tailfade { 0%,100% { opacity: .55 }              45% { opacity: 1 } }
@keyframes drift    { 0%,100% { transform: translate(0,0); opacity: .7 }
                      45%     { transform: translate(-7px,7px); opacity: .2 } }""",
 "av-mobius": """.avatar-mobius .mb-flow { animation: flow2 6s linear infinite; }
.avatar-mobius .mb-face { animation: glow 6s ease-in-out infinite;
                          animation-delay: calc(var(--i) * -2s); }

@keyframes flow2 { to { stroke-dashoffset: -28 } }""",
 "av-origami": """.avatar-origami .orx-wing { transform-box: view-box; transform-origin: 64px 64px; }
.avatar-origami .orx-wing--l { animation: flap 2.6s ease-in-out infinite; }
.avatar-origami .orx-wing--r { animation: flap 2.6s ease-in-out infinite; animation-delay: -.13s; }

@keyframes flap { 0%,100% { transform: scaleX(1) } 50% { transform: scaleX(.74) } }
/* Крылья сжимаются по X от осевой линии тела — бумага поворачивается, а не гнётся. */""",
}

KEYFRAMES = """@keyframes spin    { to { transform: rotate(360deg) } }
@keyframes breathe { 0%,100% { transform: scale(1) }    50% { transform: scale(1.045) } }
@keyframes stretch { 0%,100% { transform: scaleY(1) }   50% { transform: scaleY(1.22) } }
@keyframes pop     { 0%,100% { transform: scale(1) }    35% { transform: scale(1.3) } }
@keyframes blink   { 0%,100% { opacity: .3 }  18% { opacity: 1 }  45% { opacity: .3 } }
@keyframes twinkle { 0%,100% { opacity: .2 }  50% { opacity: 1 } }
@keyframes glow    { 0%,100% { opacity: .32 } 28% { opacity: 1 }  60% { opacity: .32 } }"""


def animations_md():
    L = ["# Анимации аватаров и рамок",
         "",
         "Восемнадцать концептов: девять для рамок, семь для анимированных аватаров "
         "и два событийных. "
         "Всё построено на `transform` и `opacity` — свойствах, которые браузер анимирует "
         "на композиторе. Единственное исключение — хвост кометы на `stroke-dashoffset`: "
         "это перерисовка без пересчёта раскладки.",
         "",
         "## Что изменилось",
         "",
         "* Исправлен центр вращения — см. правило ниже. До этого Сатурн, Битовый ток, "
         "Аврора и Координаты вращались вокруг угла холста и уезжали из кадра.",
         "* «Механизм» вернулся вместо «Цепи»: зубчатое кольцо вращается целиком, одной "
         "группой, без расхождения скоростей.",
         "* У Кометы аватар не вращается — движется только сама комета, а вместо вспышки "
         "голова отходит наружу и вытягивает хвост.",
         "* «Дыхание» аватара и моргание убраны.",
         "* Добавлены семь анимированных аватаров премиум-уровня.",
         "* Пламя, Туманность и Распускание оставлены без изменений.",
         "",
         ORIGIN_NOTE,
         "",
         "## Общие правила",
         "",
         "1. Одновременно на экране — не больше двух анимированных рамок. В таблице лиги и "
         "в списках анимация выключена: там аватар работает как данные.",
         "2. Равномерное вращение — только у объектов, где круговое движение осмысленно: "
         "Сатурн, Цепь, Комета, Битовый ток, Аврора, Координаты. Огонь, цветы и туманность дышат.",
         "3. Только `transform` и `opacity` (плюс `stroke-dashoffset` у хвоста кометы). "
         "Ни фильтров, ни теней в кадре, ни анимации геометрии (`r`, `width`, `stroke-width`).",
         "4. `prefers-reduced-motion: reduce` выключает всё; ни один знак не зависит от "
         "движения, чтобы быть узнанным.",
         "5. Событийные анимации проигрываются один раз. У зациклённых период не короче 1.6 с.",
         "",
         "## Базовые кейфреймы",
         "",
         "```css", KEYFRAMES, "```",
         "",
         "## Концепты",
         ""]
    for n, c in enumerate(anim.CONCEPTS, 1):
        tag = {"frame": "FR", "avatar-anim": "AN", "avatar": "EV"}[c["target"]] + f"-{n:02d}"
        L += [f"### {tag} · {c['ru']}", "",
              f"**Длительность** `{c['dur']}` · **кривая** `{c['ease']}` · **повтор** {c['loop']}", "",
              c["idea"], "",
              "```css", CSS_SNIPPET[c["id"]], "```", ""]
    L += ["## Классы и переменные в разметке", "",
          "Классы уже проставлены в SVG, ничего размечать вручную не нужно:", "",
          "| класс | где | зачем |",
          "|---|---|---|",
          "| `.st-r0`, `.st-r1`, `.st-moon` | Сатурн | внешняя орбита, внутренняя, спутники |",
          "| `.ch-ring` | Цепь | всё кольцо одной группой |",
          "| `.cm-orbit`, `.cm-head`, `.cm-tail`, `.cm-dust` | Комета | облёт, голова, хвост, пыль |",
          "| `.bt-pulse`, `.bt-bit` | Битовый ток | импульс и разряды |",
          "| `.au-band` | Аврора | три ленты |",
          "| `.cd-orbit`, `.cd-tick` | Координаты | пунктирная орбита и оси |",
          "| `.fl-tongue` | Пламя | языки |",
          "| `.nb-glow`, `.nb-star` | Туманность | свечение и звёзды |",
          "| `.bl-flower` | Цветущая | цветы |",
          "| `.gr-ring` | Механизм | всё зубчатое кольцо одной группой |",
          "| `.tsr-outer`, `.tsr-inner`, `.tsr-link` | Тессеракт | внешний куб, внутренний, рёбра |",
          "| `.frc-tri` | Фрактал | треугольники Серпинского |",
          "| `.cr-facet`, `.cr-shine` | Кристалл | грани и блик |",
          "| `.bh-flow`, `.bh-core`, `.bh-star` | Чёрная дыра | диск, ядро, звёзды |",
          "| `.cmv-head`, `.cmv-tail`, `.cmv-dust` | Комета | голова, хвост, пыль |",
          "| `.orx-wing--l`, `.orx-wing--r` | Оригами | крылья |",
          "| `.mb-face`, `.mb-flow` | Лента Мёбиуса | грани ленты и бегущая метка |",
          "", "Переменная `--i` на элементе — его номер по кругу, для сдвига фазы. "
          "У цветов дополнительно `--cx` / `--cy` — собственный центр.", "",
          "## Кадры для Figma", "",
          "В `svg/animation-keyframes/` лежат по три кадра на концепт "
          "(`<id>-1.svg`, `-2`, `-3`). Плагин раскладывает их в ряд и проставляет между ними "
          "Smart Animate — это позволяет показать движение внутри Figma, где CSS не работает. "
          "Кадры приблизительные: точный тайминг задаётся кодом по таблице выше.", ""]
    return "\n".join(L)


def readme_md():
    def tier(t):
        return ", ".join(a[1] for a in avatars.SPEC if a[3] == t)
    fr = ", ".join(f[1] for f in frames.SPEC)
    return f"""# Аватары, рамки и символы лиг · трек «Призма»

Объёмный градиент и стекло: сфера строится радиальным градиентом, фигура лежит
под стеклянным бликом, край держат внутренняя тень и светлый ободок. Сетка:
аватар 128×128, рамка 160×160 с отверстием Ø104 в центре, знак лиги 128×128.

## Аватары: три уровня

**Бесплатно (4):** {tier("base")}.
Нейтральные математические знаки — доступны сразу, ничего не сообщают о владельце.

**Покупные (9):** {tier("paid")}.
Сова, Робот и Космонавт оставлены без изменений. Лис, Кит, Ёж, Волшебник и Ниндзя
переделаны; Медведь — новый.

**Анимированные (6):** {tier("anim")}.
Самый дорогой уровень. Движение у каждого вырастает из самой фигуры, а не
добавлено сверху. Их намеренно мало: чем реже анимация встречается в списке,
тем дороже она читается.

## Рамки (14)

{fr}.
«Механизм» — зубчатое кольцо, вращается целиком одной группой.

## Знаки лиг

Порядок лестницы: Дельта → Гамма → Омега → Бетта → Альфа → Сигма.
Форма пластины усложняется вверх по лестнице — от треугольника к восьмиграннику.

| Лига | Пластина | Символ |
|---|---|---|
| Дельта | треугольник | δ |
| Гамма | ромб | γ |
| Бетта | щит | β |
| Альфа | пятиугольная печать | α |
| Сигма | восьмигранная плита | Σ |
| Омега | шестигранник | ω |

Начертание — в языке фирменного знака: только прямые, плоские срезы, ровная
толщина штриха, заливка градиентом слева направо. Σ повторяет логотип буквально,
остальные три построены по тем же правилам. Место читается металлом пластины
и жетоном с номером; цвет лиги при этом не меняется.

Альтернативные пластины и четыре других начертания остались в
`svg/league-variants/` — если понадобится вернуться к выбору.

## Что внутри

```
design/
├─ figma-plugin/       локальный плагин: manifest.json · code.js · ui.html
├─ svg/
│  ├─ avatars/               19 файлов, 128×128
│  ├─ frames/                14 файлов, 160×160
│  ├─ leagues/               16 файлов (4 лиги × базовый знак и 3 места)
│  ├─ league-variants/       альтернативные пластины и начертания
│  └─ animation-keyframes/   51 файл (17 концептов × 3 кадра)
├─ preview.html        страница с живыми анимациями
├─ ANIMATIONS.md       спецификация всех 17 концептов с CSS
└─ README.md           этот файл
```

## Как открыть в Figma

1. Figma **Desktop** (в браузере импорта плагинов нет).
2. `Plugins → Development → Import plugin from manifest…` → выбрать
   `design/figma-plugin/manifest.json`. Если плагин уже импортирован —
   просто запустите, он подхватит новый код.
3. Отметить, что собирать: основной набор, варианты знаков лиг, кадры анимаций.
4. Плагин создаст новую страницу с наборами компонентов («Аватар», «Рамка»,
   «Лига + Место»), доской вариантов и полосами кадров со Smart Animate —
   `Present` проигрывает движение.

Запасной путь: перетащить содержимое `svg/` на холст. Слои и группы сохранятся,
но компонентов, вариантов и прототипов не будет.

## Как это лечь в код

SVG самодостаточны: без внешних шрифтов (греческие символы переведены в контуры),
без фильтров и растровых подложек — только пути и градиенты.

* Аватары ложатся в спрайт из `templates/base.html`:
  `<symbol id="avatar-fox" viewBox="0 0 128 128">…`. В `templates/partials/avatar.html`
  сейчас `viewBox="0 0 60 60"` — поменять на `0 0 128 128`.
* Рамка перестаёт быть `box-shadow` (`.avatar-badge.frame-*` в `static/css/app.css`)
  и становится отдельным слоем поверх аватара: контейнер 160×160, аватар 104×104
  по центру. Именно поэтому у Кометы аватар остаётся неподвижным — он не входит
  в анимируемую группу.
* Уровень аватара (`base` / `paid` / `anim`) стоит хранить в модели: анимированные
  дороже и должны продаваться отдельно, а бесплатные выдаваться сразу при регистрации.
* Классы для анимаций проставлены внутри SVG — список в `ANIMATIONS.md`.
  **Обязательно** задайте `transform-box: view-box` и центр (`80px 80px` для рамок,
  `64px 64px` для аватаров): без этого браузер крутит элементы вокруг угла холста.

## Как менять

Исходники генератора — в `generator/`. Палитра каждой позиции и её уровень —
одна строка в `SPEC` (`avatars.py`, `frames.py`); формы пластин и начертания —
в `leagues.py` и `glyphs.py` (константы `DEFAULT_PLATE` и `DEFAULT_GLYPH`).
После правок: `python3 export.py && python3 build_page.py && python3 docs.py`.
Шрифты для альтернативных начертаний — в `generator/fonts/`.
"""


if __name__ == "__main__":
    open("out/ANIMATIONS.md", "w", encoding="utf-8").write(animations_md())
    open("out/README.md", "w", encoding="utf-8").write(readme_md())
    print("docs ok")
