"""Собрать косметику и знаки лиг в design/svg/ — единый источник рисунков.

    python design/brand/build.py

Пишет: аватары (25 обычных + 6 чемпионских), знаки лиг-розетки с жетонами
мест, рамки-розетки призёров (лига × место, анимированные) и вымпелы сезона.
После сборки: `manage.py build_cosmetics_sprite`, чтобы обновить спрайт.

Модули рядом — генераторы по слоям: logo (конструкция букв), leagues
(буквы лиг и цифры), concepts/rewards/final (лиги и награды), avatars*
(аватары). Рисунки не правят руками в design/svg: правят генератор и
пересобирают, иначе следующая сборка затрёт правку.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import avatars  # noqa: E402
import avatars2  # noqa: E402
import avatars3  # noqa: E402
import avatars4  # noqa: E402
import avatars5  # noqa: E402
import final  # noqa: E402
import rewards  # noqa: E402
from leagues import ORDER  # noqa: E402

SVG = HERE.parent / "svg"

AVATARS = {
    "sigma": avatars.sigma, "owl": avatars.owl, "fox": avatars.fox,
    "integral": avatars2.integral, "pi": avatars2.pi, "infinity": avatars2.infinity,
    "cat": avatars2.cat, "penguin": avatars2.penguin, "bear": avatars2.bear,
    "robot": avatars3.robot, "icosa": avatars3.icosa, "spiral": avatars3.spiral,
    "tesseract": avatars4.tesseract, "fractal": avatars4.fractal, "crystal": avatars4.crystal,
    "mobius": avatars4.mobius,
    "hedgehog": avatars5.hedgehog, "astronaut": avatars5.astronaut, "comet": avatars5.comet,
    "blackhole": avatars5.blackhole, "whale": avatars5.whale, "ninja": avatars5.ninja,
    "wizard": avatars5.wizard, "dragon": avatars5.dragon, "origami": avatars5.origami,
}


def write(folder: str, name: str, markup: str) -> None:
    path = SVG / folder / f"{name}.svg"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markup, encoding="utf-8")


def main() -> dict:
    counts = {"avatars": 0, "champions": 0, "leagues": 0, "frames": 0, "pennants": 0}
    for code, fn in AVATARS.items():
        write("avatars", code, fn()); counts["avatars"] += 1
    for league in ORDER:
        write("avatars", f"champion-{league}", rewards.constellation_avatar(league)); counts["champions"] += 1
        write("leagues", f"league-{league}", rewards.rosette(league)); counts["leagues"] += 1
        for place in (1, 2, 3):
            write("leagues", f"league-{league}-{place}", rewards.rosette(league, place)); counts["leagues"] += 1
            write("frames", f"rosette-{league}-{place}", final.frame_rosette_anim(league, place, with_style=False)); counts["frames"] += 1
            write("pennants", f"pennant-{league}-{place}", final.pennant(league, place)); counts["pennants"] += 1
    return counts


if __name__ == "__main__":
    print(main())
