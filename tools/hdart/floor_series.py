"""Серия полов: объём очереди отдельно от размера проверки.

Серия - до --n групп очереди (по умолчанию 500), разложенных по рецепту и нарезанных на подсерии по --min..--size
групп (50-100). Подсерия - это партия floor_batch: план, сборка, съёмка, лист (листы мелкие, --per-page 8).
Ошибка одной группы даёт ей свой статус (failed, hold, no_save), остальные идут дальше.

Рецепты подсерий:
  lines   - queued, проверка pixel_lines ok (recipe_guard.lines_verdict)
  carpet  - queued, pixel_lines не годится, ковёр ground_seam проходит проверку орнамента и рисунка (R-332, R-298)
  verify  - installed: установлено, но не проверено игровым кадром - только съёмка, без сборки
  fix     - needs_fix: пересборка тем же рецептом
Группа, которой не подошёл ни один рецепт, в серию не идёт: hold с причиной, отдельной строкой в отчёте.

  py -3.13 tools/hdart/floor_series.py make --name S1
  py -3.13 tools/hdart/floor_series.py run --name S1 --sub S1_lines_01
  py -3.13 tools/hdart/floor_series.py status --name S1
"""
import argparse
import collections
import json
import math
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import floor_batch as fb      # noqa: E402
import recipe_guard as rg     # noqa: E402

ENC_W = "utf-8-sig"
ENC_R = "utf-8-sig"
RECIPES = ("verify", "fix", "lines", "carpet")


def say(*a):
    print(*a, flush=True)


def series_path(name):
    return fb.WORK / ("series_%s.json" % name)


def load_series(name):
    p = series_path(name)
    if not p.exists():
        raise SystemExit("нет серии " + str(p))
    return json.loads(p.read_text(encoding=ENC_R))


def recipe_of(r):
    """-> (рецепт, метод для очереди или None, причина отказа)."""
    st = r["статус"]
    if st == "installed":
        return "verify", None, ""
    if st == "needs_fix":
        return "fix", None, ""
    if st == "hold":
        # только hold самой проверки рецепта: пробуем другой рецепт; hold человека (лист, R-314, «не пол») не трогаем
        other = {"проверка pixel_lines: нужен": ("carpet", "ground_seam"),
                 "проверка ковра: нужен": ("lines", "pixel_lines")}
        for head, (kind, meth) in other.items():
            if r["заметка"].startswith(head):
                v, why, _m = rg.check(r["группа"], meth)
                return (kind, meth, "") if v == "ok" else (None, None, r["заметка"])
        return None, None, r["заметка"]
    meth = r["метод"]
    if meth:                                    # метод уже назначен человеком или прежней партией - не менять
        v, why, _m = rg.check(r["группа"], meth)
        kind = "carpet" if meth.split()[0] == "ground_seam" else "lines"
        return (kind, meth, "") if v == "ok" else (None, None, rg.note(kind, v, why))
    v, why, _m = rg.check(r["группа"], "pixel_lines")
    if v == "ok":
        return "lines", "pixel_lines", ""
    v2, why2, _m = rg.check(r["группа"], "ground_seam")
    if v2 == "ok":
        return "carpet", "ground_seam", ""
    return None, None, rg.note("lines", v, why) + " | " + rg.note("carpet", v2, why2)


def chunks(items, size, low):
    """Ровные куски не больше size; меньше low - только если всего меньше low."""
    if not items:
        return []
    k = max(1, math.ceil(len(items) / size))
    while k > 1 and len(items) / k < low:
        k -= 1
    step = math.ceil(len(items) / k)
    return [items[i:i + step] for i in range(0, len(items), step)]


def cmd_make(a):
    q = fb.load_queue()
    busy = {g for s in fb.WORK.glob("series_*.json")
            for sub in json.loads(s.read_text(encoding=ENC_R))["subs"] for g in sub["groups"]
            if s != series_path(a.name)}
    pri = {"needs_fix": 0, "installed": 1, "queued": 2, "hold": 3}
    cand = [r for r in q.values() if r["статус"] in pri and r["группа"] not in busy]
    # порядок отбора: исправление и проверка установленного первыми (они уже в игре), дальше по числу клеток
    cand.sort(key=lambda r: (pri[r["статус"]], -int(r["клеток"])))
    by = collections.defaultdict(list)
    held, swapped = [], []
    for r in cand:
        if sum(len(v) for v in by.values()) >= a.n:
            break
        rec, meth, why = recipe_of(r)
        if rec is None:
            if r["статус"] != "hold":
                r["статус"] = "hold"
                r["заметка"] = why[:400]
                held.append(r["группа"])
            continue
        if r["статус"] == "hold":
            r["статус"] = "queued"
            r["метод"] = meth
            r["заметка"] = ("смена рецепта на %s (серия %s), было: %s" % (meth, a.name, r["заметка"]))[:400]
            swapped.append(r["группа"])
        elif meth and not r["метод"]:
            r["метод"] = meth
        by[rec].append(r)
    say("из hold другим рецептом: %d %s" % (len(swapped), " ".join(swapped[:12])))
    subs = []
    for rec in RECIPES:
        # внутри рецепта - по набору (материал рядом на листе), затем по клеткам
        rs = sorted(by[rec], key=lambda r: (r["группа"].split(":")[0], -int(r["клеток"])))
        for i, part in enumerate(chunks(rs, a.size, a.min), 1):
            subs.append({"name": "%s_%s_%02d" % (a.name, rec, i), "recipe": rec,
                         "groups": [r["группа"] for r in part], "cells": sum(int(r["клеток"]) for r in part)})
    say("серия %s: групп %d в %d подсериях, в hold без рецепта %d" % (
        a.name, sum(len(s["groups"]) for s in subs), len(subs), len(held)))
    for s in subs:
        say("  %-22s %-7s групп %3d  клеток %7d" % (s["name"], s["recipe"], len(s["groups"]), s["cells"]))
    if a.dry:
        say("всухую: очередь и серия не записаны")
        return
    fb.save_queue(q)
    data = {"name": a.name, "made": time.strftime("%Y-%m-%d %H:%M"), "n": a.n, "size": a.size, "min": a.min,
            "subs": subs, "held": held}
    series_path(a.name).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding=ENC_W)
    say("файл", series_path(a.name))


def fb_run(args, log):
    cmd = [sys.executable, str(HERE / "floor_batch.py")] + args
    say(">", " ".join(args))
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env=dict(__import__("os").environ, PYTHONIOENCODING="utf-8"))
    out = (p.stdout or "") + (p.stderr or "")
    with open(log, "a", encoding="utf-8") as f:
        f.write("\n> %s\n%s\nкод %d\n" % (" ".join(args), out, p.returncode))
    tail = [s for s in out.strip().splitlines() if s.strip()][-3:]
    for s in tail:
        say("   ", s)
    return p.returncode


def cmd_run(a):
    data = load_series(a.name)
    sub = next((s for s in data["subs"] if s["name"] == a.sub), None)
    if sub is None:
        raise SystemExit("нет подсерии %s в серии %s" % (a.sub, a.name))
    q = fb.load_queue()
    open_st = ("queued", "installed", "needs_fix", "failed", "built", "need_view") if sub["recipe"] != "verify" \
        else ("installed",)
    groups = [g for g in sub["groups"] if g in q and q[g]["статус"] in open_st]
    if not groups:
        raise SystemExit("в подсерии %s нечего делать: все группы уже прошли дальше" % a.sub)
    log = fb.WORK / ("%s.log" % a.sub)
    say("подсерия %s (%s): групп %d из %d" % (a.sub, sub["recipe"], len(groups), len(sub["groups"])))
    steps = [["plan", "--batch", a.sub, "--groups", ",".join(groups), "--max-shots", str(a.max_shots)]]
    if sub["recipe"] in ("fix", "verify"):
        steps[0].append("--edges")      # края площадок: там сосед не закрывает потерю контура (R-326)
    if sub["recipe"] != "verify":
        steps.append(["build", "--batch", a.sub])
    steps += [["shoot", "--batch", a.sub], ["sheet", "--batch", a.sub, "--per-page", "8"]]
    names = [st[0] for st in steps]
    if a.only:
        keep = a.only.split(",")
        bad = [k for k in keep if k not in names]
        if bad:
            raise SystemExit("нет шагов %s в подсерии %s (есть %s)" % (bad, a.sub, names))
        steps = [st for st in steps if st[0] in keep]
    for st in steps:
        if fb_run(st, log):
            raise SystemExit("шаг %s подсерии %s упал - лог %s" % (st[0], a.sub, log))
    say("подсерия %s готова к просмотру, лог %s" % (a.sub, log))


def cmd_status(a):
    data = load_series(a.name)
    q = fb.load_queue()
    tot = collections.Counter()
    for s in data["subs"]:
        c = collections.Counter(q[g]["статус"] if g in q else "?" for g in s["groups"])
        tot.update(c)
        say("  %-22s %-7s %3d: %s" % (s["name"], s["recipe"], len(s["groups"]),
                                      ", ".join("%s %d" % kv for kv in sorted(c.items()))))
    say("серия %s всего: %s; в hold без рецепта при сборке серии %d" % (
        a.name, ", ".join("%s %d" % kv for kv in sorted(tot.items())), len(data["held"])))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("make")
    p.add_argument("--name", required=True)
    p.add_argument("--n", type=int, default=500)
    p.add_argument("--size", type=int, default=100)
    p.add_argument("--min", type=int, default=50)
    p.add_argument("--dry", action="store_true")
    p = sp.add_parser("run")
    p.add_argument("--name", required=True)
    p.add_argument("--sub", required=True)
    p.add_argument("--max-shots", type=int, default=48)
    p.add_argument("--only", default="", help="шаги через запятую: plan,build,shoot,sheet (съёмку - не параллельно)")
    p = sp.add_parser("status")
    p.add_argument("--name", required=True)
    a = ap.parse_args()
    {"make": cmd_make, "run": cmd_run, "status": cmd_status}[a.cmd](a)


if __name__ == "__main__":
    main()
