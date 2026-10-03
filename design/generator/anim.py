# -*- coding: utf-8 -*-
"""Концепты анимаций и кадры-ключи для Smart Animate в Figma."""
import avatars, frames

# target: frame | avatar (событийная) | avatar-anim (анимированный аватар)
CONCEPTS = [
    # ── Рамки ────────────────────────────────────────────────────────────
    dict(id="saturn-orbit", target="frame", item="saturn", ru="Сатурн · «Орбита»",
         dur="18 s + 26 s", ease="linear", loop="бесконечно",
         idea="Две орбиты вращаются вокруг аватара навстречу друг другу, спутники обходят его "
              "за 14 s. Центр вращения — центр аватара, поэтому кольца не уезжают и не меняют размер.",
         keys=[("0 %", "rotate(0 80 80)"), ("33 %", "rotate(120 80 80)"), ("66 %", "rotate(240 80 80)")]),
    dict(id="gears-mesh", target="frame", item="gears", ru="Механизм · «Ход шестерни»",
         dur="24 s", ease="linear", loop="бесконечно",
         idea="Зубчатое кольцо вращается целиком, одной группой — без расхождения скоростей "
              "и встречных элементов. Зубья и заклёпки идут вместе с ободом, как у настоящей шестерни.",
         keys=[("0 %", "rotate(0 80 80)"), ("33 %", "rotate(12 80 80)"), ("66 %", "rotate(24 80 80)")]),
    dict(id="comet-flight", target="frame", item="comet", ru="Комета · «Уход кометы»",
         dur="4 s", ease="cubic-bezier(.35,0,.25,1)", loop="бесконечно",
         idea="Аватар неподвижен — вращается только комета. На каждом круге голова отходит "
              "от аватара наружу (до +26 %), вытягивая за собой хвост через stroke-dashoffset.",
         keys=[("0 %", "rotate(0 80 80)"),
               ("40 %", "rotate(144 80 80) translate(80,80) scale(1.16) translate(-80,-80)"),
               ("75 %", "rotate(270 80 80)")]),
    dict(id="bitflow-pulse", target="frame", item="bitflow", ru="Битовый ток · «Импульс»",
         dur="2.4 s", ease="linear", loop="бесконечно",
         idea="Светящийся сегмент бежит по кольцу вокруг аватара, нули и единицы загораются "
              "по мере его прохождения и гаснут за 320 ms. Сдвиг фазы задан переменной --i.",
         keys=[("0 %", "rotate(0 80 80)"), ("33 %", "rotate(120 80 80)"), ("66 %", "rotate(240 80 80)")]),
    dict(id="aurora-ribbons", target="frame", item="aurora", ru="Аврора · «Ленты»",
         dur="12 / 16 / 20 s", ease="linear", loop="бесконечно",
         idea="Три ленты обходят аватар с разной скоростью и в разные стороны. У каждой концы "
              "прозрачные, поэтому на наложении получается перелив, а не три отдельных кольца.",
         keys=[("0 %", "rotate(0 80 80)"), ("33 %", "rotate(90 80 80)"), ("66 %", "rotate(180 80 80)")]),
    dict(id="coord-scan", target="frame", item="coordinates", ru="Координаты · «Развёртка»",
         dur="30 s", ease="linear", loop="бесконечно",
         idea="Пунктирная орбита медленно обходит аватар. Оси при начислении XP вытягиваются "
              "строго наружу от центра — это масштаб относительно центра, а не сдвиг.",
         keys=[("0 %", "rotate(0 80 80)"), ("33 %", "rotate(120 80 80)"), ("66 %", "rotate(240 80 80)")]),
    dict(id="flame-breath", target="frame", item="flame", ru="Пламя · «Дыхание огня»",
         dur="1.6 s", ease="ease-in-out", loop="бесконечно",
         idea="Языки по очереди тянутся наружу (scaleY 1 → 1.22) со сдвигом фазы 80 ms по кругу. "
              "Огонь не вращается — вращающееся пламя всегда читается как «загрузка».",
         keys=[("0 %", "translate(80,80) scale(1) translate(-80,-80)"),
               ("50 %", "translate(80,80) scale(1.055) translate(-80,-80)"),
               ("100 %", "translate(80,80) scale(1) translate(-80,-80)")]),
    dict(id="nebula-pulse", target="frame", item="nebula", ru="Туманность · «Пульс»",
         dur="3.6 s", ease="ease-in-out", loop="бесконечно",
         idea="Свечение дышит (scale .96 → 1.05, opacity .8 → 1), звёзды мерцают асинхронно "
              "с периодами 1.2–2.4 s.",
         keys=[("0 %", "translate(80,80) scale(0.96) translate(-80,-80)"),
               ("50 %", "translate(80,80) scale(1.05) translate(-80,-80)"),
               ("100 %", "translate(80,80) scale(0.96) translate(-80,-80)")]),
    dict(id="bloom-open", target="frame", item="bloom", ru="Цветущая · «Распускание»",
         dur="640 ms", ease="cubic-bezier(.34,1.56,.64,1)", loop="один раз при надевании",
         idea="Цветы раскрываются по кругу с задержкой 45 ms друг за другом: scale .3 → 1.12 → 1. "
              "В покое — дыхание ±1.5 %.",
         keys=[("0 %", "translate(80,80) scale(0.86) translate(-80,-80)"),
               ("60 %", "translate(80,80) scale(1.06) translate(-80,-80)"),
               ("100 %", "translate(80,80) scale(1) translate(-80,-80)")]),

    # ── Анимированные аватары (премиум) ──────────────────────────────────
    dict(id="av-tesseract", target="avatar-anim", item="tesseract", ru="Тессеракт · «Разворот»",
         dur="12 s / 24 s", ease="linear", loop="бесконечно",
         idea="Внутренний куб вращается против часовой за 12 s, внешний — по часовой за 24 s. "
              "Рёбра-связки между ними подсвечиваются волной, поэтому проекция четвёртого "
              "измерения читается как непрерывный разворот, а не как мигание.",
         keys=[("0 %", "rotate(0 64 64)"), ("33 %", "rotate(30 64 64)"), ("66 %", "rotate(60 64 64)")]),
    dict(id="av-fractal", target="avatar-anim", item="fractal", ru="Фрактал · «Ветвление»",
         dur="2.8 s", ease="ease-in-out", loop="бесконечно",
         idea="Треугольники загораются волной от вершины к основанию — по одному каждые 90 ms. "
              "Порядок и есть порядок построения Серпинского: видно, как фигура собирает сама себя.",
         keys=[("0 %", "translate(64,64) scale(0.94) translate(-64,-64)"),
               ("50 %", "translate(64,64) scale(1.03) translate(-64,-64)"),
               ("100 %", "translate(64,64) scale(0.94) translate(-64,-64)")]),
    dict(id="av-crystal", target="avatar-anim", item="crystal", ru="Кристалл · «Преломление»",
         dur="4.2 s", ease="ease-in-out", loop="бесконечно",
         idea="Грани по очереди набирают яркость, будто свет обходит камень по кругу, "
              "а по ребру скользит блик. Форма при этом не меняется — двигается только свет.",
         keys=[("0 %", "translate(64,64) scale(1) translate(-64,-64)"),
               ("50 %", "translate(64,64) scale(1.04) translate(-64,-64)"),
               ("100 %", "translate(64,64) scale(1) translate(-64,-64)")]),
    dict(id="av-blackhole", target="avatar-anim", item="blackhole", ru="Чёрная дыра · «Аккреция»",
         dur="9 s", ease="linear", loop="бесконечно",
         idea="Аккреционный диск вращается вокруг горизонта событий, само ядро медленно дышит, "
              "а звёзды по углам мерцают вразнобой. Ядро остаётся тёмным — это точка покоя, "
              "к которой всё стягивается.",
         keys=[("0 %", "rotate(0 64 64)"), ("33 %", "rotate(120 64 64)"), ("66 %", "rotate(240 64 64)")]),
    dict(id="av-comet", target="avatar-anim", item="comet", ru="Комета · «Разгон»",
         dur="3.4 s", ease="cubic-bezier(.3,0,.2,1)", loop="бесконечно",
         idea="Голова уходит вперёд по диагонали и возвращается, хвост при этом удлиняется "
              "и светлеет, а пыль сносит назад со сдвигом фазы. Движение внутри круга, "
              "поэтому аватар не «дёргается» в списке.",
         keys=[("0 %", "translate(0,0)"), ("45 %", "translate(7,-7)"), ("100 %", "translate(0,0)")]),
    dict(id="av-origami", target="avatar-anim", item="origami", ru="Оригами · «Взмах»",
         dur="2.6 s", ease="ease-in-out", loop="бесконечно",
         idea="Крылья журавля складываются и раскрываются — scaleX от осевой линии тела, "
              "с небольшим запаздыванием правого крыла. Бумага не гнётся, только поворачивается: "
              "силуэт остаётся гранёным.",
         keys=[("0 %", "translate(64,64) scale(1,1) translate(-64,-64)"),
               ("50 %", "translate(64,64) scale(0.78,1) translate(-64,-64)"),
               ("100 %", "translate(64,64) scale(1,1) translate(-64,-64)")]),

    dict(id="av-mobius", target="avatar-anim", item="mobius", ru="Лента Мёбиуса · «Обход»",
         dur="6 s", ease="linear", loop="бесконечно",
         idea="По ленте бежит светящаяся метка. У ленты Мёбиуса одна сторона и один край, "
              "поэтому метка возвращается в начало, только пройдя ленту дважды — именно это "
              "и показывает бесконечный цикл штриха по контуру.",
         keys=[("0 %", "translate(64,64) scale(1) translate(-64,-64)"),
               ("50 %", "translate(64,64) scale(1.03) translate(-64,-64)"),
               ("100 %", "translate(64,64) scale(1) translate(-64,-64)")]),

    # ── Событийные анимации аватара ──────────────────────────────────────
    dict(id="avatar-appear", target="avatar", item="pi", ru="Аватар · «Появление»",
         dur="320 ms", ease="cubic-bezier(.34,1.56,.64,1)", loop="один раз",
         idea="Аватар входит с лёгким перелётом: scale .82 → 1.04 → 1, opacity 0 → 1. "
              "Первая загрузка кабинета и смена аватара в магазине.",
         keys=[("0 %", "translate(64,64) scale(0.82) translate(-64,-64)"),
               ("60 %", "translate(64,64) scale(1.04) translate(-64,-64)"),
               ("100 %", "translate(64,64) scale(1) translate(-64,-64)")]),
    dict(id="avatar-win", target="avatar", item="fox", ru="Аватар · «Победа»",
         dur="520 ms", ease="cubic-bezier(.22,1.2,.36,1)", loop="один раз по событию",
         idea="Подскок с приземлением: translateY 0 → −9 → 0 и лёгкое сжатие по Y "
              "(scale 1.06/0.94). Подъём в лиге и закрытие квеста.",
         keys=[("0 %", "translate(0,0)"), ("45 %", "translate(0,-9)"), ("100 %", "translate(0,0)")]),
]


def _wrap(svg, transform):
    head, rest = svg.split("</defs>", 1)
    rest = rest.rsplit("</svg>", 1)[0]
    return f'{head}</defs>\n<g transform="{transform}">{rest}</g>\n</svg>\n'


def keyframes(style="a"):
    AV = avatars.build()
    FR = frames.build(style)
    out = []
    for c in CONCEPTS:
        base = FR[c["item"]][2] if c["target"] == "frame" else AV[c["item"]][2]
        for i, (lab, tr) in enumerate(c["keys"], 1):
            out.append((f'{c["id"]}-{i}', f'{c["ru"]} · кадр {i} ({lab})', _wrap(base, tr), c["id"], i))
    return out
