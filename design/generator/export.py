# -*- coding: utf-8 -*-
"""Сборка файлов: SVG (стиль «Призма»), Figma-плагин."""
import json, os, shutil
import avatars, frames, leagues, glyphs, anim
from lib import LEAGUES, MEDALS

OUT = "out"
STYLE = "a"

ALPHA_PLATES = ["pentagon", "rosette", "gem", "star"]
SIGMA_PLATES = ["octagon", "crown", "cup", "pennant"]
PLATE_RU = {"rosette": "Розетка", "gem": "Самоцвет", "pentagon": "Пентагон", "star": "Звезда (было)",
            "crown": "Корона", "cup": "Кубок", "octagon": "Октагон", "pennant": "Вымпел (было)",
            "shield": "Щит", "hex": "Шестигранник"}


def w(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w", encoding="utf-8").write(data)


def collect():
    AV = avatars.build(STYLE)
    FR = frames.build(STYLE)
    LG = leagues.build()
    d = {"avatars": [], "frames": [], "leagues": [], "anim": [],
         "plateVariants": [], "glyphVariants": []}
    for key, ru, cat, tier, *_ in avatars.SPEC:
        d["avatars"].append(dict(key=key, ru=ru, cat=cat, tier=tier,
                                 tierRu=avatars.TIER_RU[tier], svg=AV[key][2]))
    for key, ru, cat, *_ in frames.SPEC:
        d["frames"].append(dict(key=key, ru=ru, cat=cat, svg=FR[key][2]))
    for k in leagues.ORDER:
        d["leagues"].append(dict(key=f"league-{k}", league=LEAGUES[k]["ru"], place="—",
                                 ru=LEAGUES[k]["ru"], svg=LG[f"league-{k}"][1]))
        for pl in (1, 2, 3):
            d["leagues"].append(dict(key=f"league-{k}-{pl}", league=LEAGUES[k]["ru"], place=str(pl),
                                     ru=f'{LEAGUES[k]["ru"]} · {MEDALS[pl]["ru"]}',
                                     svg=LG[f"league-{k}-{pl}"][1]))
    # варианты пластин (для выбора)
    for lg_key, plates in (("alpha", ALPHA_PLATES), ("sigma", SIGMA_PLATES)):
        for p in plates:
            d["plateVariants"].append(dict(
                key=f"plate-{lg_key}-{p}", league=LEAGUES[lg_key]["ru"], plate=p,
                ru=PLATE_RU[p], svg=leagues.mark(lg_key, None, p, leagues.DEFAULT_GLYPH),
                svgGold=leagues.mark(lg_key, 1, p, leagues.DEFAULT_GLYPH)))
    # варианты начертания (для выбора)
    for v, ru, note in glyphs.VARIANTS:
        for k in leagues.ORDER:
            d["glyphVariants"].append(dict(key=f"glyph-{v}-{k}", variant=v, ru=ru, note=note,
                                           league=LEAGUES[k]["ru"], leagueKey=k,
                                           svg=leagues.mark(k, None, None, v)))
    for name, ru, svg, cid, idx in anim.keyframes(STYLE):
        d["anim"].append(dict(key=name, ru=ru, concept=cid, idx=idx, svg=svg))
    return d


def main():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    d = collect()
    root = f"{OUT}/svg"
    for grp, folder in (("avatars", "avatars"), ("frames", "frames"), ("leagues", "leagues"),
                        ("anim", "animation-keyframes"),
                        ("plateVariants", "league-variants/plates"),
                        ("glyphVariants", "league-variants/glyphs")):
        for it in d[grp]:
            w(f"{root}/{folder}/{it['key']}.svg", it["svg"])

    slim = {
        "avatars": [{"k": i["key"], "n": i["ru"], "c": i["cat"], "t": i["tierRu"], "s": i["svg"]} for i in d["avatars"]],
        "frames": [{"k": i["key"], "n": i["ru"], "c": i["cat"], "s": i["svg"]} for i in d["frames"]],
        "leagues": [{"k": i["key"], "n": i["ru"], "l": i["league"], "p": i["place"], "s": i["svg"]} for i in d["leagues"]],
        "plates": [{"k": i["key"], "l": i["league"], "n": i["ru"], "s": i["svgGold"]} for i in d["plateVariants"]],
        "glyphs": [{"k": i["key"], "l": i["league"], "n": i["ru"], "v": i["variant"], "s": i["svg"]} for i in d["glyphVariants"]],
        "anim": [{"k": i["key"], "n": i["ru"], "cid": i["concept"], "i": i["idx"], "s": i["svg"]} for i in d["anim"]],
    }
    concepts = [{k: c[k] for k in ("id", "ru", "dur", "ease", "loop", "idea", "target")} for c in anim.CONCEPTS]
    code = open("plugin_code.js", encoding="utf-8").read()
    code = code.replace("/*__DATA__*/null", json.dumps(slim, ensure_ascii=False))
    code = code.replace("/*__CONCEPTS__*/null", json.dumps(concepts, ensure_ascii=False))
    w(f"{OUT}/figma-plugin/code.js", code)
    w(f"{OUT}/figma-plugin/manifest.json", json.dumps({
        "name": "Mathemation · Аватары, рамки, лиги",
        "id": "mathemation-avatars-frames-leagues",
        "api": "1.0.0", "main": "code.js", "ui": "ui.html", "editorType": ["figma"],
    }, ensure_ascii=False, indent=2))
    w(f"{OUT}/figma-plugin/ui.html", open("plugin_ui.html", encoding="utf-8").read())
    json.dump(d, open(f"{OUT}/data.json", "w", encoding="utf-8"), ensure_ascii=False)
    n = sum(len(d[g]) for g in ("avatars", "frames", "leagues", "anim", "plateVariants", "glyphVariants"))
    print(f"готово: {n} SVG + плагин")


if __name__ == "__main__":
    main()
