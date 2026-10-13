"""floor_batch plan: стопка одной группы по этажам снимается с верхнего этажа (R-324).

Синтетический индекс без игры и без очереди на диске:
  1. группа G стоит в одних x,y на z1 и z2 - план обязан взять z2;
  2. пол F на z1 под крышей ДРУГОЙ группы R на z2 - F остаётся на z1 (полы под крышами не теряются);
  3. копия группы над основой (основа z1, копия z2) - это тоже стопка, план берёт z2.
Контроль: FLOOR_BATCH_DIR=<папка с floor_batch.py до правила> - случаи 1 и 3 обязаны упасть (план берёт z1).
Запуск: py -3.13 tools/test_floor_batch_plan.py
"""
import os
import json
import sys
import tempfile
import types
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent / "hdart"))
if os.environ.get("FLOOR_BATCH_DIR"):
    sys.path.insert(0, os.environ["FLOOR_BATCH_DIR"])
import floor_batch as fb  # noqa: E402


def block(x0, y0, z, n=3):
    return [[x0 + i, y0 + j, z] for i in range(n) for j in range(n)]


def run(frames, rows, groups):
    q = {r["группа"]: dict(r) for r in rows}
    idx = {"syn.sav": {"size": [30, 30, 4], "frames": frames}}
    tmp = Path(tempfile.mkdtemp())
    fb.load_queue = lambda: q
    fb.save_queue = lambda _q: None
    fb.load_index = lambda: idx
    fb.WORK = tmp
    fb.say = lambda *a: None
    sys.modules["map_screen_check"] = types.SimpleNamespace(units=lambda _p: ([], None))
    a = types.SimpleNamespace(batch="t", groups=",".join(groups), redo=False, n=24, min_cells=3, max_shots=16,
                              reviewed=True)      # проверка рецепта (recipe_guard) - не предмет этого теста
    fb.cmd_plan(a)
    plan = json.loads((tmp / "t" / "plan.json").read_text(encoding="utf-8-sig"))
    return {g: s["center"][2] for s in plan["shots"] for g in s["groups"]}


def row(g, copies=""):
    return {"группа": g, "копии": copies, "клеток": "9", "статус": "queued", "партия": "", "метод": "", "заметка": ""}


def main():
    bad = []
    # 1. стопка одной группы
    z = run({"S:1": block(10, 10, 1) + block(10, 10, 2)}, [row("S:1")], ["S:1"])
    if z.get("S:1") != 2:
        bad.append("стопка: план взял z%s, нужен z2" % z.get("S:1"))
    # 2. пол под крышей другой группы
    z = run({"F:1": block(10, 10, 1), "R:1": block(10, 10, 2)}, [row("F:1"), row("R:1")], ["F:1", "R:1"])
    if z.get("F:1") != 1 or z.get("R:1") != 2:
        bad.append("пол под крышей: F z%s (нужен 1), R z%s (нужен 2)" % (z.get("F:1"), z.get("R:1")))
    # 3. копия над основой
    z = run({"A:1": block(10, 10, 1), "B:7": block(10, 10, 2)}, [row("A:1", "B:7")], ["A:1"])
    if z.get("A:1") != 2:
        bad.append("копия над основой: план взял z%s, нужен z2" % z.get("A:1"))
    for b in bad:
        print("FAIL", b)
    print("OK" if not bad else "FAIL: %d" % len(bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
