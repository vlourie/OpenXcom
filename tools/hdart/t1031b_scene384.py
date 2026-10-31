#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Сцена карты игрока (тикет XP-000384) из УСТАНОВЛЕННЫХ файлов мода: классика | стоит сейчас (с ковром .vN по хэшу клетки).
Только чтение.

    py -3.13 tools\hdart\t1031b_scene384.py A|B [--k 4] [--shrink 0.5]
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))

from PIL import Image, ImageDraw                     # noqa: E402

import t384_build as tb                              # noqa: E402


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    area = sys.argv[1] if len(sys.argv) > 1 else "A"
    k = int(sys.argv[sys.argv.index("--k") + 1]) if "--k" in sys.argv else 4
    sc = float(sys.argv[sys.argv.index("--shrink") + 1]) if "--shrink" in sys.argv else 0.5
    box = tb.AREAS[area]
    ims = [tb.render_save(box, "classic", None, k), tb.render_save(box, "now", None, k)]
    panels = [im.resize((int(im.width * sc), int(im.height * sc)), Image.LANCZOS) for im in ims]
    labels = ["классика", "установлено (MOUNTMUD 1 2 7 9 + ковры .v1-.v3, куст 19, BLACKFOREST:18)"]
    hh = max(p.height for p in panels)
    sh = Image.new("RGB", (panels[0].width, 2 * (hh + 24)), (12, 12, 14))
    d = ImageDraw.Draw(sh)
    for i, (t, p) in enumerate(zip(labels, panels)):
        d.text((6, i * (hh + 24) + 4), t, fill=(255, 220, 0), font=tb.FONT)
        sh.paste(p, (0, i * (hh + 24) + 24))
    out = os.path.join(tb.REV, "install_384_scene_%s.png" % area)
    sh.save(out)
    print("лист:", out, sh.size)


if __name__ == "__main__":
    main()
