# Анимации аватаров и рамок

Восемнадцать концептов: девять для рамок, семь для анимированных аватаров и два событийных. Всё построено на `transform` и `opacity` — свойствах, которые браузер анимирует на композиторе. Единственное исключение — хвост кометы на `stroke-dashoffset`: это перерисовка без пересчёта раскладки.

## Что изменилось

* Исправлен центр вращения — см. правило ниже. До этого Сатурн, Битовый ток, Аврора и Координаты вращались вокруг угла холста и уезжали из кадра.
* «Механизм» вернулся вместо «Цепи»: зубчатое кольцо вращается целиком, одной группой, без расхождения скоростей.
* У Кометы аватар не вращается — движется только сама комета, а вместо вспышки голова отходит наружу и вытягивает хвост.
* «Дыхание» аватара и моргание убраны.
* Добавлены семь анимированных аватаров премиум-уровня.
* Пламя, Туманность и Распускание оставлены без изменений.

> **Главное правило.** У элементов внутри SVG браузер ставит
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
> ему хватает `transform-origin: 50% 50%` по умолчанию.

## Общие правила

1. Одновременно на экране — не больше двух анимированных рамок. В таблице лиги и в списках анимация выключена: там аватар работает как данные.
2. Равномерное вращение — только у объектов, где круговое движение осмысленно: Сатурн, Цепь, Комета, Битовый ток, Аврора, Координаты. Огонь, цветы и туманность дышат.
3. Только `transform` и `opacity` (плюс `stroke-dashoffset` у хвоста кометы). Ни фильтров, ни теней в кадре, ни анимации геометрии (`r`, `width`, `stroke-width`).
4. `prefers-reduced-motion: reduce` выключает всё; ни один знак не зависит от движения, чтобы быть узнанным.
5. Событийные анимации проигрываются один раз. У зациклённых период не короче 1.6 с.

## Базовые кейфреймы

```css
@keyframes spin    { to { transform: rotate(360deg) } }
@keyframes breathe { 0%,100% { transform: scale(1) }    50% { transform: scale(1.045) } }
@keyframes stretch { 0%,100% { transform: scaleY(1) }   50% { transform: scaleY(1.22) } }
@keyframes pop     { 0%,100% { transform: scale(1) }    35% { transform: scale(1.3) } }
@keyframes blink   { 0%,100% { opacity: .3 }  18% { opacity: 1 }  45% { opacity: .3 } }
@keyframes twinkle { 0%,100% { opacity: .2 }  50% { opacity: 1 } }
@keyframes glow    { 0%,100% { opacity: .32 } 28% { opacity: 1 }  60% { opacity: .32 } }
```

## Концепты

### FR-01 · Сатурн · «Орбита»

**Длительность** `18 s + 26 s` · **кривая** `linear` · **повтор** бесконечно

Две орбиты вращаются вокруг аватара навстречу друг другу, спутники обходят его за 14 s. Центр вращения — центр аватара, поэтому кольца не уезжают и не меняют размер.

```css
.frame-saturn .st-r0,
.frame-saturn .st-r1,
.frame-saturn .st-moon { transform-box: view-box; transform-origin: 80px 80px; }

.frame-saturn .st-r0   { animation: spin 18s linear infinite; }
.frame-saturn .st-r1   { animation: spin 26s linear infinite reverse; }
.frame-saturn .st-moon { animation: spin 14s linear infinite; }
```

### FR-02 · Механизм · «Ход шестерни»

**Длительность** `24 s` · **кривая** `linear` · **повтор** бесконечно

Зубчатое кольцо вращается целиком, одной группой — без расхождения скоростей и встречных элементов. Зубья и заклёпки идут вместе с ободом, как у настоящей шестерни.

```css
.frame-gears .gr-ring {
  transform-box: view-box; transform-origin: 80px 80px;
  animation: spin 24s linear infinite;
}
/* Зубья, обод и заклёпки лежат в одной группе .gr-ring и вращаются вместе —
   расхождения скоростей больше нет. */
```

### FR-03 · Комета · «Уход кометы»

**Длительность** `4 s` · **кривая** `cubic-bezier(.35,0,.25,1)` · **повтор** бесконечно

Аватар неподвижен — вращается только комета. На каждом круге голова отходит от аватара наружу (до +26 %), вытягивая за собой хвост через stroke-dashoffset.

```css
.frame-comet .cm-orbit,
.frame-comet .cm-head { transform-box: view-box; transform-origin: 80px 80px; }

.frame-comet .cm-orbit { animation: orbit 4s linear infinite; }      /* облёт аватара */
.frame-comet .cm-head  { animation: depart 4s ease-in-out infinite; } /* уход наружу */
.frame-comet .cm-tail  { stroke-dasharray: 62 100;                    /* pathLength=100 */
                         animation: tail 4s ease-in-out infinite; }

@keyframes orbit  { to { transform: rotate(360deg) } }
@keyframes depart { 0%,100% { transform: scale(1) }  45% { transform: scale(1.26) } }
@keyframes tail   { 0%,100% { stroke-dashoffset: 0 } 45% { stroke-dashoffset: -32 } }

/* Аватар лежит ОТДЕЛЬНЫМ слоем под рамкой и не входит в .cm-orbit —
   поэтому он остаётся неподвижным. */
```

### FR-04 · Битовый ток · «Импульс»

**Длительность** `2.4 s` · **кривая** `linear` · **повтор** бесконечно

Светящийся сегмент бежит по кольцу вокруг аватара, нули и единицы загораются по мере его прохождения и гаснут за 320 ms. Сдвиг фазы задан переменной --i.

```css
.frame-bitflow .bt-pulse { transform-box: view-box; transform-origin: 80px 80px;
                           animation: spin 2.4s linear infinite; }
.frame-bitflow .bt-bit   { animation: blink 2.4s linear infinite;
                           animation-delay: calc(var(--i) * -100ms); }
```

### FR-05 · Аврора · «Ленты»

**Длительность** `12 / 16 / 20 s` · **кривая** `linear` · **повтор** бесконечно

Три ленты обходят аватар с разной скоростью и в разные стороны. У каждой концы прозрачные, поэтому на наложении получается перелив, а не три отдельных кольца.

```css
.frame-aurora .au-band {
  transform-box: view-box; transform-origin: 80px 80px;
  animation: spin calc(12s + var(--i) * 4s) linear infinite;
}
.frame-aurora .au-band:nth-of-type(even) { animation-direction: reverse; }
```

### FR-06 · Координаты · «Развёртка»

**Длительность** `30 s` · **кривая** `linear` · **повтор** бесконечно

Пунктирная орбита медленно обходит аватар. Оси при начислении XP вытягиваются строго наружу от центра — это масштаб относительно центра, а не сдвиг.

```css
.frame-coordinates .cd-orbit,
.frame-coordinates .cd-tick { transform-box: view-box; transform-origin: 80px 80px; }

.frame-coordinates .cd-orbit { animation: spin 30s linear infinite; }
.frame-coordinates .cd-tick  { animation: tick 2.6s ease-in-out infinite; }

@keyframes tick { 0%,100% { transform: scale(1) } 50% { transform: scale(1.09) } }
/* Масштаб от центра аватара — оси растут наружу симметрично.
   На событии XP: animation: tick 400ms cubic-bezier(.34,1.56,.64,1) 1; */
```

### FR-07 · Пламя · «Дыхание огня»

**Длительность** `1.6 s` · **кривая** `ease-in-out` · **повтор** бесконечно

Языки по очереди тянутся наружу (scaleY 1 → 1.22) со сдвигом фазы 80 ms по кругу. Огонь не вращается — вращающееся пламя всегда читается как «загрузка».

```css
.frame-flame .fl-tongue > path:first-child {
  transform-box: fill-box;        /* здесь центр — сам язык, а не холст */
  transform-origin: 50% 100%;     /* основание языка */
  animation: stretch 1.6s ease-in-out infinite;
  animation-delay: calc(var(--i) * -80ms);
}
```

### FR-08 · Туманность · «Пульс»

**Длительность** `3.6 s` · **кривая** `ease-in-out` · **повтор** бесконечно

Свечение дышит (scale .96 → 1.05, opacity .8 → 1), звёзды мерцают асинхронно с периодами 1.2–2.4 s.

```css
.frame-nebula .nb-glow { transform-box: view-box; transform-origin: 80px 80px;
                        animation: breathe 3.6s ease-in-out infinite; }
.frame-nebula .nb-star { animation: twinkle calc(1.2s + var(--i) * .2s) ease-in-out infinite; }
```

### FR-09 · Цветущая · «Распускание»

**Длительность** `640 ms` · **кривая** `cubic-bezier(.34,1.56,.64,1)` · **повтор** один раз при надевании

Цветы раскрываются по кругу с задержкой 45 ms друг за другом: scale .3 → 1.12 → 1. В покое — дыхание ±1.5 %.

```css
.frame-bloom .bl-flower {
  transform-box: view-box;
  transform-origin: var(--cx) var(--cy);   /* центр конкретного цветка, из разметки */
  animation: pop 640ms cubic-bezier(.34,1.56,.64,1) 1;
  animation-delay: calc(var(--i) * 45ms);
}
```

### AN-10 · Тессеракт · «Разворот»

**Длительность** `12 s / 24 s` · **кривая** `linear` · **повтор** бесконечно

Внутренний куб вращается против часовой за 12 s, внешний — по часовой за 24 s. Рёбра-связки между ними подсвечиваются волной, поэтому проекция четвёртого измерения читается как непрерывный разворот, а не как мигание.

```css
.avatar-tesseract .tsr-inner,
.avatar-tesseract .tsr-outer { transform-box: view-box; transform-origin: 64px 64px; }

.avatar-tesseract .tsr-inner { animation: spin 12s linear infinite reverse; }
.avatar-tesseract .tsr-outer { animation: spin 24s linear infinite; }
.avatar-tesseract .tsr-link  { animation: glow 3s ease-in-out infinite;
                               animation-delay: calc(var(--i) * -.42s); }
```

### AN-11 · Фрактал · «Ветвление»

**Длительность** `2.8 s` · **кривая** `ease-in-out` · **повтор** бесконечно

Треугольники загораются волной от вершины к основанию — по одному каждые 90 ms. Порядок и есть порядок построения Серпинского: видно, как фигура собирает сама себя.

```css
.avatar-fractal .frc-tri {
  animation: glow 2.8s ease-in-out infinite;
  animation-delay: calc(var(--i) * -90ms);   /* --i — порядок построения Серпинского */
}
```

### AN-12 · Кристалл · «Преломление»

**Длительность** `4.2 s` · **кривая** `ease-in-out` · **повтор** бесконечно

Грани по очереди набирают яркость, будто свет обходит камень по кругу, а по ребру скользит блик. Форма при этом не меняется — двигается только свет.

```css
.avatar-crystal .cr-facet { animation: glow 4.2s ease-in-out infinite;
                            animation-delay: calc(var(--i) * -.55s); }
.avatar-crystal .cr-shine { transform-box: view-box; transform-origin: 64px 64px;
                            animation: shine 4.2s ease-in-out infinite; }
@keyframes shine { 0%,100% { opacity: .25; transform: translate(-6px,0) }
                   40%     { opacity: .95; transform: translate(6px,0) } }
```

### AN-13 · Чёрная дыра · «Аккреция»

**Длительность** `9 s` · **кривая** `linear` · **повтор** бесконечно

Аккреционный диск вращается вокруг горизонта событий, само ядро медленно дышит, а звёзды по углам мерцают вразнобой. Ядро остаётся тёмным — это точка покоя, к которой всё стягивается.

```css
/* Диск не вращается целиком — по нему «течёт» вещество:
   pathLength=100 делает штрих в процентах, а не в пикселях. */
.avatar-blackhole .bh-flow { animation: flow 2.6s linear infinite; }
.avatar-blackhole .bh-core { transform-box: view-box; transform-origin: 64px 64px;
                             animation: breathe 4s ease-in-out infinite; }
.avatar-blackhole .bh-star { animation: twinkle calc(1.4s + var(--i) * .3s) ease-in-out infinite; }

@keyframes flow { to { stroke-dashoffset: -12 } }
```

### AN-14 · Комета · «Разгон»

**Длительность** `3.4 s` · **кривая** `cubic-bezier(.3,0,.2,1)` · **повтор** бесконечно

Голова уходит вперёд по диагонали и возвращается, хвост при этом удлиняется и светлеет, а пыль сносит назад со сдвигом фазы. Движение внутри круга, поэтому аватар не «дёргается» в списке.

```css
.avatar-comet .cmv-head,
.avatar-comet .cmv-dust { transform-box: view-box; transform-origin: 64px 64px; }

.avatar-comet .cmv-head { animation: dash 3.4s cubic-bezier(.3,0,.2,1) infinite; }
.avatar-comet .cmv-tail { animation: tailfade 3.4s ease-in-out infinite; }
.avatar-comet .cmv-dust { animation: drift 3.4s ease-in-out infinite;
                          animation-delay: calc(var(--i) * -.2s); }

@keyframes dash     { 0%,100% { transform: translate(0,0) } 45% { transform: translate(7px,-7px) } }
@keyframes tailfade { 0%,100% { opacity: .55 }              45% { opacity: 1 } }
@keyframes drift    { 0%,100% { transform: translate(0,0); opacity: .7 }
                      45%     { transform: translate(-7px,7px); opacity: .2 } }
```

### AN-15 · Оригами · «Взмах»

**Длительность** `2.6 s` · **кривая** `ease-in-out` · **повтор** бесконечно

Крылья журавля складываются и раскрываются — scaleX от осевой линии тела, с небольшим запаздыванием правого крыла. Бумага не гнётся, только поворачивается: силуэт остаётся гранёным.

```css
.avatar-origami .orx-wing { transform-box: view-box; transform-origin: 64px 64px; }
.avatar-origami .orx-wing--l { animation: flap 2.6s ease-in-out infinite; }
.avatar-origami .orx-wing--r { animation: flap 2.6s ease-in-out infinite; animation-delay: -.13s; }

@keyframes flap { 0%,100% { transform: scaleX(1) } 50% { transform: scaleX(.74) } }
/* Крылья сжимаются по X от осевой линии тела — бумага поворачивается, а не гнётся. */
```

### AN-16 · Лента Мёбиуса · «Обход»

**Длительность** `6 s` · **кривая** `linear` · **повтор** бесконечно

По ленте бежит светящаяся метка. У ленты Мёбиуса одна сторона и один край, поэтому метка возвращается в начало, только пройдя ленту дважды — именно это и показывает бесконечный цикл штриха по контуру.

```css
.avatar-mobius .mb-flow { animation: flow2 6s linear infinite; }
.avatar-mobius .mb-face { animation: glow 6s ease-in-out infinite;
                          animation-delay: calc(var(--i) * -2s); }

@keyframes flow2 { to { stroke-dashoffset: -28 } }
```

### EV-17 · Аватар · «Появление»

**Длительность** `320 ms` · **кривая** `cubic-bezier(.34,1.56,.64,1)` · **повтор** один раз

Аватар входит с лёгким перелётом: scale .82 → 1.04 → 1, opacity 0 → 1. Первая загрузка кабинета и смена аватара в магазине.

```css
.avatar-art { animation: appear 320ms cubic-bezier(.34,1.56,.64,1) 1; }
@keyframes appear { from { transform: scale(.82); opacity: 0 }
                    60%  { transform: scale(1.04); opacity: 1 }
                    to   { transform: scale(1) } }
```

### EV-18 · Аватар · «Победа»

**Длительность** `520 ms` · **кривая** `cubic-bezier(.22,1.2,.36,1)` · **повтор** один раз по событию

Подскок с приземлением: translateY 0 → −9 → 0 и лёгкое сжатие по Y (scale 1.06/0.94). Подъём в лиге и закрытие квеста.

```css
.avatar-badge.is-win .avatar-art { animation: win 520ms cubic-bezier(.22,1.2,.36,1) 1; }
@keyframes win { 0%,100% { transform: translateY(0) scaleY(1) }
                 45%     { transform: translateY(-9px) scaleY(1.05) }
                 70%     { transform: translateY(0) scaleY(.93) } }
```

## Классы и переменные в разметке

Классы уже проставлены в SVG, ничего размечать вручную не нужно:

| класс | где | зачем |
|---|---|---|
| `.st-r0`, `.st-r1`, `.st-moon` | Сатурн | внешняя орбита, внутренняя, спутники |
| `.ch-ring` | Цепь | всё кольцо одной группой |
| `.cm-orbit`, `.cm-head`, `.cm-tail`, `.cm-dust` | Комета | облёт, голова, хвост, пыль |
| `.bt-pulse`, `.bt-bit` | Битовый ток | импульс и разряды |
| `.au-band` | Аврора | три ленты |
| `.cd-orbit`, `.cd-tick` | Координаты | пунктирная орбита и оси |
| `.fl-tongue` | Пламя | языки |
| `.nb-glow`, `.nb-star` | Туманность | свечение и звёзды |
| `.bl-flower` | Цветущая | цветы |
| `.gr-ring` | Механизм | всё зубчатое кольцо одной группой |
| `.tsr-outer`, `.tsr-inner`, `.tsr-link` | Тессеракт | внешний куб, внутренний, рёбра |
| `.frc-tri` | Фрактал | треугольники Серпинского |
| `.cr-facet`, `.cr-shine` | Кристалл | грани и блик |
| `.bh-flow`, `.bh-core`, `.bh-star` | Чёрная дыра | диск, ядро, звёзды |
| `.cmv-head`, `.cmv-tail`, `.cmv-dust` | Комета | голова, хвост, пыль |
| `.orx-wing--l`, `.orx-wing--r` | Оригами | крылья |
| `.mb-face`, `.mb-flow` | Лента Мёбиуса | грани ленты и бегущая метка |

Переменная `--i` на элементе — его номер по кругу, для сдвига фазы. У цветов дополнительно `--cx` / `--cy` — собственный центр.

## Кадры для Figma

В `svg/animation-keyframes/` лежат по три кадра на концепт (`<id>-1.svg`, `-2`, `-3`). Плагин раскладывает их в ряд и проставляет между ними Smart Animate — это позволяет показать движение внутри Figma, где CSS не работает. Кадры приблизительные: точный тайминг задаётся кодом по таблице выше.
