#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Прогон боёв Brutal-OXCE без единого клика и сбор времени ИИ.

Движок с патчем tools/aibench/aibench.patch умеет:
  -aiBench true -aiBenchTurns N   случайный быстрый бой, автобой, выход после N ходов
  [AIBENCH] строки в openxcom.log  время думанья по фракциям на каждый ход

Пример:
  python tools/aibench/run_bench.py --runs 3 --turns 6 --brutal 1
  python tools/aibench/run_bench.py --runs 3 --turns 6 --brutal 0 --label vanilla
"""

import argparse
import csv
import os
import re
import shutil
import subprocess
import sys
import time

ENC = "utf-8-sig"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FORK = os.path.join(ROOT, "BrutalAI")
EXE = os.path.join(FORK, "build-release", "bin", "openxcom.exe")
DATA = os.path.join(FORK, "bin")
# папка прогона задаётся ключом --user; в ней может лежать ссылка на чужую установку,
# поэтому целиком её не стираем НИКОГДА, только лог
DEFAULT_USER = os.path.join(FORK, "user_bench_%d" % os.getpid())

LINE = re.compile(r"\[AIBENCH\] (.*)")
KV = re.compile(r"(\w+)=([^\s]+)")
PHASE = re.compile(r"\[AIPHASE\] (.*)")


def parse_log(path):
    """Возвращает список словарей по строкам [AIBENCH] turn=..."""
    rows = []
    meta = {}
    if not os.path.exists(path):
        return rows, meta
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            # строка фаз идёт следом за своим ходом; posScanned - единственное число,
            # которое повторяется от прогона к прогону, по нему и сравнивают правки (R-025)
            p = PHASE.search(line)
            if p:
                if rows:
                    rows[-1].update(KV.findall(p.group(1)))
                continue
            m = LINE.search(line)
            if not m:
                continue
            body = m.group(1)
            if body.startswith("battle:"):
                meta = dict(KV.findall(body))
            elif body.startswith("turn="):
                rows.append(dict(KV.findall(body)))
    return rows, meta


def run_once(args, run_no):
    user = args.user
    log = os.path.join(user, "openxcom.log")
    os.makedirs(user, exist_ok=True)
    # options.cfg не трогаем: в нём список найденных модов, без него -master не сработает
    for stale in ("openxcom.log", "battle.cfg"):
        try:
            os.remove(os.path.join(user, stale))
        except OSError:
            pass

    cmd = [
        args.exe,
        "-data", args.data,
        "-user", user,
        "-cfg", user,
        "-aiBench", "true",
        "-aiBenchTurns", str(args.turns),
        "-aiBenchSeed", str(args.seed + run_no - 1 if args.seed else 0),
        "-brutalAI", str(args.brutal),
        "-aiPeformance", "true" if args.perf else "false",
        "-aiCheatMode", str(args.cheat),
        "-aiFairDamage", "true" if args.fair else "false",
    ]
    # BOXCE-BENCH: фиксированный бой - сохранить один раз, дальше грузить его же.
    # Обе строки передаём ВСЕГДА: options.cfg запоминает их с прошлого прогона,
    # и без явного пустого значения следующий прогон снова сохранит бой и выйдет
    cmd += ["-aiBenchSave", args.save_battle, "-aiBenchLoad", args.load_battle]
    cmd += [
        "-autoCombat", "true",
        "-autoCombatEachCombat", "true",
        "-autoCombatEachTurn", "true",
        "-autoCombatDefaultSoldier", "true",
        "-autoCombatDefaultHWP", "true",
        "-playIntro", "false",
        "-battleXcomSpeed", "1",
        "-battleAlienSpeed", "1",
        "-soundVolume", "0",
        "-musicVolume", "0",
        "-uiVolume", "0",
        "-displayWidth", "640",
        "-displayHeight", "400",
        "-maxFrameSkip", "1",
    ]
    if args.master:
        cmd += ["-master", args.master]

    t0 = time.time()
    try:
        subprocess.run(cmd, timeout=args.timeout, cwd=os.path.dirname(args.exe))
    except subprocess.TimeoutExpired:
        subprocess.run(["taskkill", "/IM", "openxcom.exe", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("    прогон %d: таймаут %d с, процесс убит" % (run_no, args.timeout))
    wall = time.time() - t0

    rows, meta = parse_log(log)
    # следующий прогон сотрёт openxcom.log, поэтому оставляем копию: без неё
    # разбираться, откуда взялось число, уже не по чему
    try:
        shutil.copyfile(log, os.path.join(user, "log_%s_%d.log" % (args.label or "run", run_no)))
    except OSError:
        pass
    for r in rows:
        r["run"] = run_no
        r["seed"] = (args.seed + run_no - 1) if args.seed else 0
        r["wall"] = round(wall, 1)
        r["mission"] = meta.get("mission", "?")
        r["terrain"] = meta.get("terrain", "?")
        r["race"] = meta.get("race", "?")
        r["xcom"] = meta.get("xcom", "?")
    return rows, meta, wall


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--runs", type=int, default=1)
    p.add_argument("--turns", type=int, default=6)
    p.add_argument("--brutal", type=int, default=1, help="0 ваниль, 1 Brutal, 2 Seek&Destroy")
    p.add_argument("--perf", type=int, default=0, help="aiPeformance: 1 включить оптимизацию")
    p.add_argument("--cheat", type=int, default=0, help="aiCheatMode")
    p.add_argument("--fair", type=int, default=0, help="aiFairDamage: 1 - не читать закрытые характеристики цели")
    p.add_argument("--save-battle", default="", help="разыграть бой, сохранить в этот файл и выйти")
    p.add_argument("--load-battle", default="", help="грузить этот бой вместо розыгрыша: единственный способ сравнить два прогона")
    p.add_argument("--seed", type=int, default=0, help="0 - случайный бой, иначе тот же бой на всех ИИ")
    p.add_argument("--data", default=DATA, help="папка с данными игры")
    p.add_argument("--user", default=DEFAULT_USER, help="папка прогона (моды, лог); целиком не стирается")
    p.add_argument("--master", default="", help="id основного мода, например piratez")
    p.add_argument("--exe", default=EXE, help="какой бинарник гонять: для сравнения правок держим рядом эталонный")
    p.add_argument("--timeout", type=int, default=900)
    p.add_argument("--label", default="")
    p.add_argument("--out", default=os.path.join(ROOT, "logs", "aibench.csv"))
    args = p.parse_args()

    if not os.path.exists(args.exe):
        sys.exit("нет сборки: %s" % args.exe)

    # чужой прогон испортит лог: строки двух боёв перемешаются
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq %s" % os.path.basename(args.exe)],
                             capture_output=True, text=True).stdout
        if os.path.basename(args.exe) in out:
            sys.exit("openxcom.exe уже запущен - закрой его, иначе замер смешается")
    except FileNotFoundError:
        pass

    label = args.label or "brutal%d_perf%d" % (args.brutal, args.perf)
    all_rows = []
    for i in range(1, args.runs + 1):
        rows, meta, wall = run_once(args, i)
        side_ms = {}
        for r in rows:
            side_ms.setdefault(r["side"], []).append(float(r["totalMs"]))
        summary = ", ".join("%s %.0f мс/ход" % (s, sum(v) / len(v))
                            for s, v in sorted(side_ms.items()))
        print("  %s прогон %d: %s, %s, ходов %d, %.0f с — %s"
              % (label, i, meta.get("mission", "?"), meta.get("terrain", "?"),
                 len(rows), wall, summary or "нет данных ИИ"))
        for r in rows:
            r["label"] = label
        all_rows += rows

    if args.save_battle and not all_rows:
        print("бой сохранён: %s" % os.path.join(args.user, args.save_battle))
        return
    if not all_rows:
        sys.exit("ни одной строки [AIBENCH] - смотри %s" % os.path.join(args.user, "openxcom.log"))

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    new = not os.path.exists(args.out)
    cols = ["label", "run", "seed", "turn", "side", "brutal", "perfOpt", "cheat", "calls",
            "totalMs", "avgMs", "maxMs", "avgReach", "maxReach",
            "posScanned", "posLoopMs", "posLoopRuns", "usPerPos", "fairBlind", "fairKnown",
            "mission", "terrain", "race", "xcom", "wall"]
    # мс на просмотренную позицию: сравнивать правки можно только по нормированному числу
    for r in all_rows:
        try:
            r["usPerPos"] = "%.3f" % (float(r["posLoopMs"]) * 1000.0 / float(r["posScanned"]))
        except (KeyError, ValueError, ZeroDivisionError):
            pass
    with open(args.out, "a", encoding=ENC, newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerows(all_rows)

    host = [r for r in all_rows if r["side"] == "HOSTILE"]
    if host:
        tot = sum(float(r["totalMs"]) for r in host)
        mx = max(float(r["maxMs"]) for r in host)
        print("\n%s: ход стороны ИИ в среднем %.0f мс, худший юнит %.0f мс"
              % (label, tot / len(host), mx))
        print("1000 боёв по %d ходов в один поток: %.1f ч"
              % (args.turns, tot / len(host) * args.turns * 1000 / 3600000.0))
    print("записано: %s" % args.out)


if __name__ == "__main__":
    main()
