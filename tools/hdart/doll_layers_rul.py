#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Лишний слой на голой кукле - рулсет Ruleset/hd_doll_layers.rul и пустая классика в обе копии мода hd.

Vitali 05.11: чёрные кружки на груди - отдельным слоем: голая кукла = тело + кружки, под бронёй тело чистое.
Слой живёт только в HD: классический образ пустой (индекс 0), поэтому k=1 и режим без HD дают тот же кадр.
Движок показывает HD-куклу, только если HD есть у всех её слоёв, и требует образ у каждого (InventoryState.cpp),
поэтому образ обязателен. Рулсет переопределяет только layersDefinition, префикс брони остаётся (Armor::afterLoad).
Файлы вне гита (/user/ в .gitignore), в выпуск идут с папкой мода; рулсет пересобирается этим скриптом.
Без --yes - сухой прогон. Ставить под очередью правок.

    py -3.13 tools/hdart/doll_layers_rul.py
    py -3.13 tools/hdart/doll_layers_rul.py --yes
"""
import argparse
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.dirname(os.path.dirname(HERE))

import doll_b2_render as db                          # noqa: E402
from PIL import Image                                # noqa: E402

RULESET = "hd_doll_layers.rul"
EMPTY = "Resources/Doll/empty_320x200.png"
# префикс расы -> (слот, имя слоя, брони, которым он добавляется)
EXTRA = {"LOKNAR": (3, "PASTIES", ("STR_LOKNAR_NUDE_UC", "STR_LOKNAR_NUDE_SEA_UC", "STR_LOKNAR_NUDE_DREAMLAND_UC"))}
# UBERGAL: брони с открытой грудью по выбору Vitali 06.11; у каждой внешности свой круг, tools/hdart/doll_ubergal_pasties.py
UBERGAL = ("STR_PIR_NUDE_UC", "STR_PIR_NUDE_SEA_UC", "STR_PIR_NUDE_DREAMLAND_UC", "STR_PIR_TOPLESS_UC", "STR_TOPLESS_SEA_UC", "STR_PIR_CHAINS_UC",
           "STR_ARMOR_SAINT_UC", "STR_ARMOR_SAINT_FAKE_UC", "STR_PATIENT_OUTFIT_UC", "STR_HYENA_RIDER_ARMOR_UC", "STR_PIR_SLAVE_ARMOR_UC",
           "STR_PIR_SLAVE_ARMOR_FAKE_UC", "STR_BRAINER_OUTFIT_SEA_UC", "STR_AMAZON_ARMOR_SEA_UC", "STR_THEBAN_DRESS_UC", "STR_THEBAN_DRESS_SEA_UC",
           "STR_SAVAGE_ARMOR_UC", "STR_PIR_MINX_UC", "STR_PIR_GREMRIN_UC", "STR_PIR_GREMRIN_DREAMLAND_UC", "STR_MONOKINI_SHELL_SEA_UC", "STR_RAGS_UC",
           "STR_HERMIT_UC", "STR_DEMONIC_ARMOR_UC", "STR_DEMONIC_ARMOR_SEA_UC", "STR_PIR_SWASHBUCKLER_UC")
# GNOME: голые брони и открытая грудь, страница 07.11; слот 4 у них свободен, свой круг у внешности, tools/hdart/doll_gnome_pasties.py
GNOME = (4, ("STR_GNOME_NUDE_UC", "STR_GNOME_NUDE_DREAMLAND_UC", "STR_GNOME_EXPERIMENT_UC", "STR_GNOME_EXPLORER_SEA_UC", "STR_GNOME_EXPLORER_UC"))
COVERS = "__SWASH_BRA_"                             # лежит в слоте ниже круга и закрывает его: у таких внешностей круга нет
ROOTS = [os.path.join(ROOT, "user", "mods", "hd"),
         os.path.join(ROOT, "Пиратки", "Dioxine_XPiratez", "user", "mods", "hd")]


def uber_slot(names):
    """Слот круга UBERGAL: первый свободный над телом (слот 2), ниже него лежит только то, что грудь не задевает; None - круга нет."""
    if any(COVERS in n for n in names if n):
        return None
    used = {int(n.split("__")[1]) for n in names if n}
    slot = 3
    while slot in used:
        slot += 1
    return slot


def uber_layers(arms):
    """{(броня, внешность): (слот, имя слоя)} для всех кругов UBERGAL."""
    res = {}
    for arm in UBERGAL:
        for look, names in arms[arm].items():
            slot = uber_slot(names)
            if slot is not None:
                res[arm, look] = (slot, "PASTIES_%s" % look)
    return res


def layer_names():
    """Имена слоёв, у которых образ в этом рулсете, - их нет в рулсетах Пираток."""
    res = {"%s__%d__%s" % (race, slot, name) for race, (slot, name, _) in EXTRA.items()}
    arms = db.armor_layers()
    res |= {"UBERGAL__%d__%s" % v for v in uber_layers(arms).values()}
    res |= {"GNOME__%d__PASTIES_%s" % (GNOME[0], look) for arm in GNOME[1] for look in arms[arm]}
    return res


def definition(names, slot, name):
    """Строка layersDefinition: как в Пиратках, без префикса, со слоем в своём слоте.
    armor_layers отдаёт только непустые, поэтому слот берётся из имени PREFIX__<слот>__<имя>."""
    row = {}
    for n in names:
        if n:
            _, i, short = n.split("__", 2)
            row[int(i)] = short
    if slot in row:
        raise SystemExit("слот %d занят: %s" % (slot, names))
    if slot is not None:
        row[slot] = name
    return [row.get(i, "") for i in range(max(row) + 1)]


def ruleset():
    lines = ["# OXCE-HD: extra layers of the soldier doll, HD only: the classic image is empty, so the classic",
             "# picture stays the same. Made by tools/hdart/doll_layers_rul.py.",
             "extraSprites:"]
    for n in sorted(layer_names()):
        lines += ["  - typeSingle: %s" % n, "    fileSingle: %s" % EMPTY]
    lines.append("armors:")
    arms = db.armor_layers()
    for race, (slot, name, armors) in EXTRA.items():
        for arm in armors:
            lines += ["  - type: %s" % arm, "    layersDefinition:"]
            for look, names in sorted(arms[arm].items()):
                row = definition(names, slot, name)
                lines.append("      %s: [%s]" % (look, ", ".join('"%s"' % v for v in row)))
    uber = uber_layers(arms)
    for arm in UBERGAL:
        lines += ["  - type: %s" % arm, "    layersDefinition:"]
        for look, names in sorted(arms[arm].items()):
            row = definition(names, *uber.get((arm, look), (None, None)))
            lines.append("      %s: [%s]" % (look, ", ".join('"%s"' % v for v in row)))
    for arm in GNOME[1]:
        lines += ["  - type: %s" % arm, "    layersDefinition:"]
        for look, names in sorted(arms[arm].items()):
            row = definition(names, GNOME[0], "PASTIES_" + look)
            lines.append("      %s: [%s]" % (look, ", ".join('"%s"' % v for v in row)))
    return ("\n".join(lines) + "\n").encode("utf-8")


def empty_png():
    im = Image.new("P", (db.W, db.H), 0)
    im.putpalette(db.game_palette().reshape(-1).tolist())
    b = io.BytesIO()
    im.save(b, "PNG", optimize=True)
    return b.getvalue()


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--yes", action="store_true", help="записать в обе копии мода hd")
    a = ap.parse_args()
    rul = ruleset()
    print(rul.decode("utf-8")[:700])
    print("рулсет %d строк; копии: %s" % (rul.count(b"\n"), ", ".join(ROOTS)))
    if not a.yes:
        return 0
    for root in ROOTS:
        for rel, data in (("Ruleset/" + RULESET, rul), (EMPTY, empty_png())):
            p = os.path.join(root, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "wb") as fh:
                fh.write(data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
