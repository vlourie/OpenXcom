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
ROOTS = [os.path.join(ROOT, "user", "mods", "hd"),
         os.path.join(ROOT, "Пиратки", "Dioxine_XPiratez", "user", "mods", "hd")]


def layer_names():
    """Имена слоёв, у которых образ в этом рулсете, - их нет в рулсетах Пираток."""
    return {"%s__%d__%s" % (race, slot, name) for race, (slot, name, _) in EXTRA.items()}


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
