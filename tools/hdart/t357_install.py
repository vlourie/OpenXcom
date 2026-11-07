# -*- coding: utf-8 -*-
r"""Тикет XP-000357 (выбор Vitali: вариант A, процедурно по классике, без видеокарты): пол дома URBAN_WASTE:40 (целый) и
:41 (повреждённый, dieMCD 40->41) с вариантами .v1-.v3 и побайтные копии URBAN_WASTE_WALLS:40/:41 - 16 файлов в обе копии
мода hd через манифест. Кадры делает t357_floor.py (низкие частоты классики в изорешётке, зерно на торе, пятно 41 рваным
краем в поле 40; силуэт - классики x4).

    py -3.13 tools\hdart\t357_install.py                  # собрать в art/_review/tickets_2026-10-28/t357_install и проверить
    py -3.13 tools\hdart\t357_install.py --yes            # и записать в мод (ТОЛЬКО под очередью правок)
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
os.chdir(ROOT)
OUT = os.path.join(ROOT, "art", "_review", "tickets_2026-10-28", "t357_install")
SETS = ("URBAN_WASTE", "URBAN_WASTE_WALLS")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    import numpy as np
    from PIL import Image
    import t357_floor as fl
    frames = fl.build()
    files = {}
    for s in SETS:
        d = os.path.join(OUT, "TERRAIN", s + ".PCK")
        os.makedirs(d, exist_ok=True)
        for name, arr in frames.items():
            assert arr.shape == (160, 128, 4) and arr.dtype == np.uint8, name
            p = os.path.join(d, name + ".png")
            Image.fromarray(arr, "RGBA").save(p, optimize=True)
            files["TERRAIN/%s.PCK/%s.png" % (s, name)] = p
    # маска каждого кадра - классика x4 (силуэт 40 и 41 одинаков)
    for name, arr in frames.items():
        f = int(name.split(".")[0])
        assert ((arr[..., 3] > 0) == (fl.alpha_frame(f) > 0)).all(), name + ": силуэт не классики"
    print("файлов:", len(files))
    for r in files:
        print("  ", r)
    if not a.yes:
        raise SystemExit("сухой прогон; --yes - записать в мод (под очередью правок)")
    import ticket_scene as ts
    n = ts.install_files(files, "t357_install", "t357_floor.py 28.10 (изорешётка по классике, варианты v1-v3)",
                         "Vitali: вариант A (процедурно по классике), тикет XP-000357",
                         "t357: пол дома URBAN_WASTE:40/41 с вариантами и копии URBAN_WASTE_WALLS - сплошной песок вместо плиток-подушек")
    print("установлено файлов:", n)


if __name__ == "__main__":
    main()
