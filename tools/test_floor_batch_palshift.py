"""floor_batch: группа pixel_lines в наборе под подменой палитры боя (R-314) проверяется только под подменой.

Синтетика без игры и без очереди на диске:
  1. palette_shift_sets.shifted - подмена PAL_BATTLESCAPE на глубине 0 и PAL_BATTLESCAPE_<d> на глубине d;
  2. shift_members - с риском в план идут только копии наборов, которые это окружение красит;
  3. audit_set - группа с риском, ни разу не снятая под подменой, остаётся installed с заметкой R-314; снятая - verified;
     ковёр (не pixel_lines) и установленная группа без метода (правлена вне конвейера) - verified без снимка;
  4. cmd_plan - клетки группы с риском берутся только из сейва с подменой, даже если в сейве без подмены их больше;
     группа, у которой сейва с подменой нет, - no_save с заметкой R-314.
Контроль: FLOOR_PALSHIFT_CONTROL=1 выключает защиту (shift_risk пустой) - случаи 3 и 4 обязаны упасть.
Запуск: py -3.13 tools/test_floor_batch_palshift.py
"""
import os
import json
import sys
import tempfile
import types
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent / "hdart"))
import floor_batch as fb  # noqa: E402
import palette_shift_sets as pss  # noqa: E402

ENV = "STR_ENVIRO_SYN"
PS = {"SETX": {"state": "always", "envs": {ENV: 1}, "to": {ENV: {"PAL_BATTLESCAPE": "PAL_PURPLED"}}},
      "SETD": {"state": "some", "envs": {ENV: 1}, "to": {ENV: {"PAL_BATTLESCAPE_2": "PAL_PURPLED"}}}}
pss._CACHE["sets"] = PS
if os.environ.get("FLOOR_PALSHIFT_CONTROL"):
    fb.shift_risk = lambda r, ps=None: {}


def block(x0, y0, z, n=3):
    return [[x0 + i, y0 + j, z] for i in range(n) for j in range(n)]


def row(g, copies="", st="queued", method=""):
    return {"группа": g, "копии": copies, "клеток": "9", "статус": st, "партия": "", "метод": method, "заметка": ""}


def plan(idx, rows, groups):
    q = {r["группа"]: dict(r) for r in rows}
    tmp = Path(tempfile.mkdtemp())
    fb.load_queue = lambda: q
    fb.save_queue = lambda _q: None
    fb.load_index = lambda: idx
    fb.WORK = tmp
    fb.say = lambda *a: None
    sys.modules["map_screen_check"] = types.SimpleNamespace(units=lambda _p: ([], None))
    a = types.SimpleNamespace(batch="t", groups=",".join(groups), redo=False, n=24, min_cells=3, max_shots=16,
                              reviewed=True)
    fb.cmd_plan(a)
    p = json.loads((tmp / "t" / "plan.json").read_text(encoding="utf-8-sig"))
    return {g: s["save"] for s in p["shots"] for g in s["groups"]}, q


def main():
    bad = []
    # 1
    if not (pss.shifted(PS["SETX"], ENV, 0) and not pss.shifted(PS["SETX"], ENV, 2)
            and pss.shifted(PS["SETD"], ENV, 2) and not pss.shifted(PS["SETD"], ENV, 0)
            and not pss.shifted(PS["SETX"], "", 0)):
        bad.append("shifted: глубина или окружение разобраны неверно")
    # 2
    risk = fb.shift_risk(row("SETX:1", "PLAIN:4"), PS)
    if fb.shift_members(["SETX:1", "PLAIN:4"], risk, [ENV, 0]) != ["SETX:1"] and risk:
        bad.append("shift_members: в план пошла копия без подмены")
    # 3
    r = row("SETX:1", st="installed", method="pixel_lines --checker")
    fb.audit_set(r, "ok", "", seen=set(), ps=PS)
    if r["статус"] != "installed" or "R-314" not in r["заметка"]:
        bad.append("audit_set: группа с риском без снимка под подменой стала %s" % r["статус"])
    fb.audit_set(r, "ok", "", seen={"SETX:1"}, ps=PS)
    if r["статус"] != "verified" or "R-314" in r["заметка"]:
        bad.append("audit_set: снятая под подменой группа - %s, заметка '%s'" % (r["статус"], r["заметка"]))
    r = row("SETX:2", st="installed", method="ground_seam --carpet")
    fb.audit_set(r, "ok", "", seen=set(), ps=PS)
    if r["статус"] != "verified":
        bad.append("audit_set: ковёр не pixel_lines - %s" % r["статус"])
    r = row("SETX:4", st="installed")            # установленный кадр, правленный вне конвейера: метод пустой
    fb.audit_set(r, "ok", "", seen=set(), ps=PS)
    if r["статус"] != "verified":
        bad.append("audit_set: установленная группа без метода (не pixel_lines) - %s" % r["статус"])
    # 4
    idx = {"plain.sav": {"size": [30, 30, 4], "env": ["", 0],
                         "frames": {"SETX:1": block(2, 2, 0, 5), "SETX:3": block(2, 20, 0, 4)}},
           "hot.sav": {"size": [30, 30, 4], "env": [ENV, 0], "frames": {"SETX:1": block(10, 10, 0, 3)}}}
    got, q = plan(idx, [row("SETX:1"), row("SETX:3")], ["SETX:1", "SETX:3"])
    if got.get("SETX:1") != "hot.sav":
        bad.append("plan: SETX:1 снята на %s, нужен hot.sav" % got.get("SETX:1"))
    if "SETX:3" in got or "R-314" not in q["SETX:3"]["заметка"]:
        bad.append("plan: SETX:3 без сейва с подменой - %s, заметка '%s'" % (got.get("SETX:3"), q["SETX:3"]["заметка"]))
    for b in bad:
        print("FAIL", b)
    print("OK" if not bad else "FAIL: %d" % len(bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
