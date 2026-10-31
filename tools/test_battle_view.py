"""Проверка tools/hdart/battle_view.py: числа ракурса сходятся с формулами движка, фразы на месте.

Запуск: py -3.13 tools/test_battle_view.py
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "hdart"))
import battle_view as bv  # noqa: E402


def map_to_screen(x, y, z):
    """Camera::convertMapToScreen при k = 1 (src/Battlescape/Camera.cpp)."""
    w, h = bv.FRAME_W, bv.FRAME_H
    return x * (w // 2) - y * (w // 2), x * (w // 4) + y * (w // 4) - z * ((h + w // 4) // 2)


def main():
    sys.stdout.reconfigure(encoding="utf-8")    # вывод в трубу у питона - cp1252 (R-001)
    fails = []

    def check(cond, what):
        if not cond:
            fails.append(what)

    # проекция: шаг клетки и этажа как у движка
    check(map_to_screen(1, 0, 0) == (16, 8), "ось x клетки -> (16, 8)")
    check(map_to_screen(0, 1, 0) == (-16, 8), "ось y клетки -> (-16, 8)")
    check(map_to_screen(0, 0, 1) == (0, -bv.LEVEL_PX), "этаж -> 24 пикселя")
    # ромб 2:1 даёт камеру под 30 градусов и края под arctg(1/2)
    check(abs(bv.CAMERA_ELEVATION_DEG - 30.0) < 1e-9, "высота камеры 30")
    check(abs(bv.EDGE_SLOPE_DEG - math.degrees(math.atan(0.5))) < 1e-9, "наклон краёв 26.565")
    check(abs(bv.LEVEL_TO_TILE - math.sqrt(1.5)) < 1e-9, "этаж к клетке sqrt(1.5)")
    # честная ортографическая проекция с этими числами даёт ровно 24 пикселя на этаж
    s = 1 / math.cos(math.radians(bv.CAMERA_AZIMUTH_DEG))   # пикселей на горизонтальный воксель
    level = bv.LEVEL_TO_TILE * bv.VOXEL_XY * s * math.cos(math.radians(bv.CAMERA_ELEVATION_DEG))
    check(abs(level - bv.LEVEL_PX) < 1e-6, f"этаж в проекции {level:.3f} != 24")
    # центр ромба пола - середина его строк
    check(bv.FLOOR_CENTER[1] == (bv.FLOOR_ROWS[0] + bv.FLOOR_ROWS[1] + 1) // 2, "центр ромба по строкам")

    # фразы
    for kind, k in bv.KINDS.items():
        pb, sh = bv.prompt_block(kind), bv.short(kind)
        if k["iso"] is True:
            check(pb is not None, f"{kind}: нет фраз")
            if pb:
                for word in ("orthographic", "45 degrees", "30 degrees", "2:1"):
                    check(word in pb["positive"], f"{kind}: в промпте нет '{word}'")
                check("perspective" in pb["negative"], f"{kind}: в негативе нет 'perspective'")
                if k["light"] == "day":
                    check("from the left" in pb["positive"], f"{kind}: нет света слева")
                    check("light from the right" in pb["negative"], f"{kind}: в негативе нет света справа")
                # юнит смотрит к зрителю и в профиль - негатив не должен запрещать его направления
                for word in ("front view", "side view", "profile"):
                    check(word not in pb["negative"], f"{kind}: негатив запрещает '{word}' - это направление юнита")
                check(len(sh["positive"].split()) + len(sh["negative"].split()) < 40, f"{kind}: SDXL-блок длинный")
        elif k["iso"] == "unrolled":
            check(bool(pb) and "straight from above" in pb["positive"] and "isometric" in pb["negative"],
                  f"{kind}: развёртка не сверху")
        else:
            check(pb is None and sh is None, f"{kind}: не боевой вид получил фразы ракурса боя")
        check(bool(bv.brief(kind)), f"{kind}: пустая справка")
    check(sorted(bv.FACING) == list(range(8)), "8 направлений словами")
    check("viewer" in bv.facing(3) and "back" in bv.facing(7), "dir 3 к зрителю, dir 7 спиной")
    vs = bv.view_sentence("object")
    check(vs.endswith(".") and vs[0].isupper(), "ракурс отдельным предложением")
    check(bv.light_sentence("cursor") == "", "курсор без света")

    # охват: каждый генератор с моделью берёт фразы отсюда или назван с причиной, почему нет
    rows = bv.audit()
    check(len(rows) > 0, "audit не нашёл генераторов из tools/gpu_scripts.txt")
    known = ("USES", "MISSING", "no-words", "NOT_BATTLE", "NO_PROMPT", "PROTECTED")
    check(all(st in known for _, st, _ in rows), "audit: неизвестный статус")
    for n, st, why in rows:
        check(st not in ("MISSING", "no-words"), f"audit: {n} - {st} ({why})")

    for f in fails:
        print("FAIL", f)
    print("ok" if not fails else f"{len(fails)} fail(s)")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
