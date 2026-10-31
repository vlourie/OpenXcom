"""floor_batch: кадр ковра ground_seam с вариантами .vN - копии и раскладка партии.

Без игры и без установки (временные папки, инструмент сборки подменён):
  1. build: группа S:1 с копией T:5, метод ground_seam - копия получает 5.png и 5.v1..v3 из 1.png и 1.v1..v3;
     вариант прежней сборки T:5 (5.v4) снимается;
  2. layout: в наборе установки стоят 1.png и 1.v1..v4 - после раскладки 1.png и 1.v1..v3 новые, 1.v4 снят.
     Порядок glob не важен: .v1 сборки не снимается своим же кадром 1.png.
Контроль: FLOOR_BATCH_DIR=<папка с floor_batch.py до правки> - случаи падают (копия без вариантов, вариант снят).
Запуск: py -3.13 tools/test_floor_batch_variants.py
"""
import json
import os
import sys
import tempfile
import types
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent / "hdart"))
if os.environ.get("FLOOR_BATCH_DIR"):
    sys.path.insert(0, os.environ["FLOOR_BATCH_DIR"])
import floor_batch as fb  # noqa: E402


def put(p, text):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(text.encode())


def main():
    bad = []
    tmp = Path(tempfile.mkdtemp())
    fb.WORK = tmp / "work"
    fb.say = lambda *a: None
    q = {"S:1": {"группа": "S:1", "копии": "T:5", "клеток": "9", "статус": "queued", "партия": "b", "метод":
                 "ground_seam --iso --speckle", "заметка": ""}}
    fb.load_queue = lambda: q
    fb.save_queue = lambda _q: None
    (fb.WORK / "b").mkdir(parents=True)
    (fb.WORK / "b" / "plan.json").write_text(json.dumps({"groups": ["S:1"], "shots": []}), encoding="utf-8-sig")
    out = fb.WORK / "b" / "TERRAIN"
    put(out / "T.PCK" / "5.v4.png", "old")       # прежняя сборка копии

    def fake(cmd):
        a = cmd[cmd.index("--out") + 1]
        s, f = cmd[cmd.index("--set") + 1], cmd[cmd.index("--carpet") + 1]
        for n in [f] + ["%s.v%d" % (f, v) for v in (1, 2, 3)]:
            put(Path(a) / (s + ".PCK") / (n + ".png"), "new " + n)
        return types.SimpleNamespace(returncode=0, stdout="S кадров 4", stderr="")
    fb.run_tool = fake
    fb.cmd_build(types.SimpleNamespace(batch="b"))
    got = sorted(p.name for p in (out / "T.PCK").glob("*.png"))
    if got != ["5.png", "5.v1.png", "5.v2.png", "5.v3.png"]:
        bad.append("копия T:5: %s" % got)
    elif (out / "T.PCK" / "5.v2.png").read_text() != "new 1.v2":
        bad.append("копия T:5: 5.v2 не из 1.v2")
    if q["S:1"]["метод"] != "ground_seam --iso --speckle" or q["S:1"]["статус"] != "built":
        bad.append("очередь: %s %s" % (q["S:1"]["метод"], q["S:1"]["статус"]))

    # 2. раскладка поверх установки
    mods = tmp / "mods"
    terr = mods / "hd" / "hd" / "TERRAIN"
    for n in ["1", "1.v1", "1.v2", "1.v3", "1.v4", "2"]:
        put(terr / "S.PCK" / (n + ".png"), "inst " + n)
    put(mods / "hd" / "metadata.yml", "id: hd")
    fb.GAME_MODS = mods
    fb.junction = lambda link, target: None     # прочих модов нет
    root = fb.layout("b")
    lt = root / "hd" / "hd" / "TERRAIN" / "S.PCK"
    names = sorted(p.name for p in lt.glob("*.png"))
    if names != ["1.png", "1.v1.png", "1.v2.png", "1.v3.png", "2.png"]:
        bad.append("раскладка S: %s" % names)
    else:
        for n in ["1", "1.v1", "1.v2", "1.v3"]:
            if (lt / (n + ".png")).read_text() != "new " + n:
                bad.append("раскладка S: %s не из сборки" % n)
    for b in bad:
        print("FAIL", b)
    print("OK" if not bad else "FAIL: %d" % len(bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
