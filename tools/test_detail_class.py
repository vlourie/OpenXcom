"""detail_class: слова DETAIL_CRITICAL, контуры, контроль регрессионного набора (без игры и видеокарты).

    py -3.13 tools/test_detail_class.py
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "hdart"))
os.chdir(ROOT)

import numpy as np                  # noqa: E402
from PIL import Image               # noqa: E402
import detail_class as dc           # noqa: E402

fails = []


def check(ok, what):
    print(("ok   " if ok else "FAIL ") + what)
    if not ok:
        fails.append(what)


# слова: тип из списка специалиста - да, ящик и стол - нет, часть слова не считается
for text in ("wall painting", "Wall Poster", "Command Console", "display cabinet", "Computer Terminal",
             "metal shelves with jars", "air vent grille", "Radiation hazard sign"):
    check(bool(dc.words(text)), "слово в %r" % text)
for text in ("wooden crate", "round table", "Crashed plane debris", "designer chair", "toilet"):
    check(not dc.words(text), "нет слова в %r" % text)

# контуры: ровный квадрат - SIMPLE, шахматка с перепадом 255 - UNSURE, слово - DETAIL_CRITICAL всегда
flat = np.zeros((40, 32, 4), np.uint8)
flat[5:35, 4:28] = (120, 90, 60, 255)
px = dc.pixel_numbers([Image.fromarray(flat)])
check(dc.classify([], px)[0] == "SIMPLE_SHAPE", "ровный квадрат - SIMPLE_SHAPE (контуров %.2f)" % px["edge_share"])
check(dc.classify(["picture:poster"], px)[0] == "DETAIL_CRITICAL", "слово сильнее ровных пикселей")
busy = flat.copy()
busy[5:35, 4:28][::2, ::2, :3] = 250
busy[5:35, 4:28][1::2, 1::2, :3] = 250
px = dc.pixel_numbers([Image.fromarray(busy)])
check(dc.classify([], px)[0] == "UNSURE", "шахматка без слова - UNSURE (контуров %.2f)" % px["edge_share"])

# контроль: опознание каждого предмета регрессионного набора даёт слово (не SIMPLE_SHAPE)
reg = os.path.join(ROOT, dc.REGRESSION)
if os.path.exists(reg):
    with open(reg, encoding="utf-8-sig") as f:
        doc = json.load(f)
    for a in doc["assets"]:
        check(bool(dc.words(a["identity"]["text"])), "регрессия %s: %r" % (a["asset_id"], a["identity"]["text"]))
    check(len(doc["assets"]) == 10 and set(doc["gate"]) == {
        "BLURRED_UPSCALE_FAIL", "DETAIL_RECONSTRUCTION_FAIL", "RECONSTRUCTED_BUT_INVENTED"}, "набор: 10 предметов и три класса гейта")
else:
    check(False, "нет %s" % dc.REGRESSION)

# гейт пилота: DETAIL_RECONSTRUCTION_FAIL critical только с changes_function, invented - всегда, blurred - нет
import tempfile                     # noqa: E402
import pilot_report as pr           # noqa: E402
tmp = os.path.join(tempfile.mkdtemp(), "v.tsv")


def verdicts(text):
    with open(tmp, "w", encoding="utf-8-sig") as f:
        f.write(text)
    return pr.read_verdicts(tmp, set("abcde"))


rows = [{"asset_id": i, "ai_jobs": "OK"} for i in "abcde"]
ex, fns = verdicts("asset_id\tverdict\tnote\tchanges_function\n"
                   "a\tDETAIL_RECONSTRUCTION_FAIL\tрейки\t1\nb\tDETAIL_RECONSTRUCTION_FAIL\t\t\n"
                   "c\tBLURRED_UPSCALE_FAIL\t\t\nd\tRECONSTRUCTED_BUT_INVENTED\t\t\n")
_c, _n, crit, hard = pr.tally(rows, ex, fns)
check((crit, hard) == (2, 4), "гейт: critical 2 (потеря назначения + invented), hard 4 - вышло %d/%d" % (crit, hard))
ex, fns = verdicts("asset_id\tverdict\tnote\nb\tDETAIL_RECONSTRUCTION_FAIL\tx\n")
check(pr.tally(rows, ex, fns)[2:] == (0, 1), "старый TSV без changes_function: не critical")
try:
    verdicts("asset_id\tverdict\tnote\tchanges_function\nc\tBLURRED_UPSCALE_FAIL\t\t1\n")
    check(False, "флаг потери назначения при чужом вердикте не отклонён")
except SystemExit:
    check(True, "флаг потери назначения при чужом вердикте отклонён")

# решения человека: у каждой строки класс из списка и источник
if os.path.exists(os.path.join(ROOT, dc.OVERRIDES)):
    ov = dc.read_overrides(os.path.join(ROOT, dc.OVERRIDES))
    check(ov.get("CULTAN:94", {}).get("class") == "DETAIL_CRITICAL", "overrides: CULTAN:94 - DETAIL_CRITICAL")

print("\n%s" % ("ВСЁ ПРОШЛО" if not fails else "УПАЛО: %d" % len(fails)))
sys.exit(1 if fails else 0)
