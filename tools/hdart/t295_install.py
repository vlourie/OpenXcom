"""XP-000295: лестницы URBAN40K 49/50/55/56 (и копия URBAN40K2MOON 49/50/59/60) - готовый HD MUCONCRETE 18/19/22/23.

Классика у них идентична (маска 1.00), у URBAN40K HD нарисован уже классики и с приподнятым низом - лестница висит,
половинки не стыкуются. Вариант A по выбору Vitali 23.10 (страница выбора, r295).
    .venv\\Scripts\\python.exe tools\\hdart\\t295_install.py          # сухой прогон: какие кадры и размеры
    .venv\\Scripts\\python.exe tools\\hdart\\t295_install.py --yes    # в мод hd (манифест, обе копии; под очередью правок)
"""
import argparse
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image  # noqa: E402
import build_hd_pack as bp  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STAGE = os.path.join(ROOT, "art", "_review", "tickets_2026-10-23", "after", "t295", "A")
# цель: источник MUCONCRETE (18/19 - основы 49/50, 23/22 - их зеркала 55/56)
MAP = {
    ("URBAN40K", 49): 18, ("URBAN40K", 50): 19, ("URBAN40K", 55): 23, ("URBAN40K", 56): 22,
    ("URBAN40K2MOON", 49): 18, ("URBAN40K2MOON", 50): 19, ("URBAN40K2MOON", 59): 23, ("URBAN40K2MOON", 60): 22,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    game = bp.TARGETS["game"]
    files = {}
    for (s, f), src in MAP.items():
        rel = "TERRAIN/%s.PCK/%d.png" % (s, f)
        srcp = os.path.join(game, "TERRAIN", "MUCONCRETE.PCK", "%d.png" % src)
        old = os.path.join(game, rel)
        si, oi = Image.open(srcp), Image.open(old)
        print("%-28s <- MUCONCRETE:%d  %s / сейчас %s" % (rel, src, si.size, oi.size))
        if si.size != oi.size:
            raise SystemExit("размер не совпадает: " + rel)
        dst = os.path.join(STAGE, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(srcp, dst)
        files[rel] = dst
    if not a.yes:
        raise SystemExit("сухой прогон; --yes - записать в мод (только по слову Vitali, под очередью правок)")
    import ticket_scene as ts
    ts.install_files(files, "t295_install", "t295_install.py 23.10, копия HD MUCONCRETE 18/19/22/23",
                     "Vitali: вариант A r295 на странице выбора 23.10",
                     "t295: лестницы URBAN40K/URBAN40K2MOON - HD MUCONCRETE по маске классики")


if __name__ == "__main__":
    main()
