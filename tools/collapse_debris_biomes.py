"""Завал v2, этап A: предложение таблицы краёв. Каждому участку заголовка без завала v1 (ключ - первый набор блока,
как census/collapse/debris/blocks.tsv) - край, краю - записи четырёх видов обломков по короткому листу
(art/collapse_debris/short.png, census/collapse/debris/short.tsv): камень, дерево, металл, растение (бурелом).
Записи чужих наборов бой берёт заимствованием набора (docs/research/collapse-debris-mechanics-2026-10-21.md, «Доноры»).
Это предложение на выбор Vitali, не данные игры.
    py -3.13 tools/collapse_debris_biomes.py
-> census/collapse/debris/biomes.tsv"""
import os
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
DIR = "census/collapse/debris"

# край -> (камень, дерево, металл, растение): номера карточек короткого листа
CITY_WOOD, CITY_METAL = "Ст6 Ст7", "Ст15 Ст16"
BIOMES = {
    "лес": ("Кр2", CITY_WOOD, CITY_METAL, "Б1 Б2 Б3"),
    "тёмный лес": ("Кр3", CITY_WOOD, CITY_METAL, "Б10 Б11 Б12"),
    "джунгли": ("Кр5 Кр6", CITY_WOOD, CITY_METAL, "Б7 Б8 Б9"),
    "снег": ("Кр4", CITY_WOOD, CITY_METAL, "Б16 Б17 Б18 Б19 Б20"),
    "пустошь": ("Кр1 Кр7 Кр8", CITY_WOOD, CITY_METAL, "Б13 Б14 Б15"),
    "скалы": ("Кр1", CITY_WOOD, CITY_METAL, "Б4 Б5 Б6"),
    "пустыня": ("Кр7 Кр8", CITY_WOOD, CITY_METAL, "Б21 Б22 Б23"),
    "трущобы": ("Кр11 Кр12 Кр13 Кр14", CITY_WOOD, CITY_METAL, "Б1 Б2 Б3"),
    "город": ("Ст1 Ст2 Ст3", CITY_WOOD, CITY_METAL, "Б1 Б2 Б3"),
    "подземье": ("Кр9 Кр10", CITY_WOOD, CITY_METAL, "Б10 Б11 Б12"),
}
KEYS = {
    "лес": "FOREST FORESTRED FORESTBITS3 FORESTBITSRED FOREST_NORD CULTAREA CULTIVAT BARN_PP MOUNTGRASS",
    "тёмный лес": "BLACKFOREST BLACKJUNGLE MOUNTMUD",
    "джунгли": "JUNGLE JUNGLESTYX NEOJUNGLE JUNGLEBITS FORESTJUNGLESTYX MOUNTTROP",
    "снег": "FOREST_SNOW FORESTBITS_SNOW MOUNTSNOW2",
    "пустошь": "FOREST_WASTE FORESTBITSWASTE FORESTSWAMP_WASTE MOUNTWASTE2 ROADS_WASTE FRNITURE_WASTE MADDECOR_WASTE",
    "скалы": "MOUNTROCK",
    "пустыня": "MUMMY_VILLAGE MUMMY_RUINS DESERT DESERTBITS XOPSDESERT XOPSDESERTRED MOUNTSAND",
    "трущобы": "INDUSLUM RUSTSHACKS FRN_OLD BRICKBAR",
    "подземье": "U_PLANET_VOID CAVEBLACK CATACDECOR",
}


def read_tsv(path):
    with open(path, encoding="utf-8-sig") as f:
        lines = f.read().splitlines()
    head = lines[0].split("\t")
    return [dict(zip(head, ln.split("\t"))) for ln in lines[1:] if ln.strip()]


def main():
    card = {r["card"]: r["record"] for r in read_tsv(os.path.join(DIR, "short.tsv"))}
    key_biome = {k: b for b, ks in KEYS.items() for k in ks.split()}
    per = defaultdict(lambda: [0, 0, set()])
    for b in read_tsv(os.path.join(DIR, "blocks.tsv")):
        if b["rubble_v1"]:
            continue
        bio = key_biome.get(b["key"], "город")
        per[bio][0 if b["to"] == "игрокам" else 1] += 1
        per[bio][2].add(b["key"])
    rows = []
    for bio, (st, wd, mt, pl) in BIOMES.items():
        pp, ex, keys = per.get(bio, [0, 0, set()])
        recs = [" ".join(card[c] for c in v.split()) for v in (st, wd, mt, pl)]
        donor_sets = sorted({r.split(":")[0] for v in recs for r in v.split()})
        rows.append((bio, pp, ex, st, wd, mt, pl, *recs, " ".join(donor_sets), " ".join(sorted(keys))))
    with open(os.path.join(DIR, "biomes.tsv"), "w", encoding="utf-8-sig", newline="") as f:
        f.write("\t".join(["biome", "blocks_players", "blocks_exp", "stone", "wood", "metal", "plant", "stone_rec",
                           "wood_rec", "metal_rec", "plant_rec", "sets", "keys"]) + "\n")
        for r in rows:
            f.write("\t".join(map(str, r)) + "\n")
    tot = sum(r[1] for r in rows)
    print("участков игрокам без завала v1 по краям: %d" % tot)
    for r in rows:
        print("  %-11s %3d (+%d эксп.)  наборов-доноров: %s" % (r[0], r[1], r[2], r[11]))


if __name__ == "__main__":
    main()
