#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Серия боёв до конца: кто кого и какой ценой.

Меряет не миллисекунды, а ИСХОД. Один и тот же розыгрыш боя прогоняется каждым
вариантом ИИ (парное сравнение), потому что бои между собой различаются сильнее,
чем варианты ИИ: без пар и сотня боёв покажет только шум.

Как это работает:
  1. бой разыгрывается один раз и сохраняется в файл (-aiBenchSave);
  2. этот файл загружается каждым вариантом (-aiBenchLoad) и доигрывается до конца;
  3. движок в конце боя пишет строку [AIRESULT] - живые, оглушённые, убитые по сторонам.

Пример:
  python tools/aibench/run_series.py --battles 40 --jobs 12 --turns 40
      --arm "родной=-brutalAI 0"
      --arm "честный=-brutalAI 0 -aiFairDamage true"
      --data "E:/OpenXCom/Пиратки/Dioxine_XPiratez" --master piratez
      --mods-from E:/OpenXCom/BrutalAI/user_pz --out logs/series_pz.csv
"""

import argparse
import csv
import math
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

ENC = "utf-8-sig"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FORK = os.path.join(ROOT, "BrutalAI")
EXE = os.path.join(FORK, "build-release", "bin", "openxcom.exe")
DATA = os.path.join(FORK, "bin")

RESULT = re.compile(r"\[AIRESULT\] (.*)")
OPTSLINE = re.compile(r"\[AIBENCH\] options: (.*)")
BATTLE = re.compile(r"\[AIBENCH\] battle: (.*)")
HOSTILE = re.compile(r"\[AIBENCH\] turn=\d+ side=HOSTILE .*?totalMs=(\d+)")
KV = re.compile(r"(\w+)=([^\s]*)")

# Ключи ИИ и их значения по умолчанию из Options.cpp Brutal-сборки.
# Передаём их ВСЕ и ВСЕГДА: options.cfg папки прогона запоминает всё, что было
# передано в прошлый раз, и вариант, не назвавший ключ явно, унаследует чужой.
# На этом уже погорел прогон на 1000 боёв: два варианта из трёх вышли одинаковыми
BENCH_OPTS = {
    "brutalAI": "1",
    "brutalCivilians": "0",
    "aiPeformance": "false",
    "aiCheatMode": "0",
    "aiFairDamage": "false",
}
# каким это должно выйти в строке [AIBENCH] options: булево движок печатает как 1/0
BOOLS = {"aiPeformance", "aiFairDamage"}


def opt_norm(key, value):
    """Значение ключа так, как его печатает движок."""
    v = str(value).strip().lower()
    if key in BOOLS:
        return "1" if v in ("1", "true", "yes", "on") else "0"
    return str(int(v))


def arm_opts(text):
    """«-brutalAI 1 -aiFairDamage true» -> полный набор ключей поверх умолчаний."""
    want = dict(BENCH_OPTS)
    parts = text.split()
    for i in range(0, len(parts) - 1, 2):
        key = parts[i].lstrip("-")
        if key not in want:
            raise SystemExit("неизвестный ключ варианта: %s (знаю: %s)"
                             % (parts[i], ", ".join(sorted(want))))
        want[key] = parts[i + 1]
    return want


def opts_cmdline(want):
    out = []
    for k, v in want.items():
        out += ["-" + k, str(v)]
    return out


def opts_mismatch(text, want):
    """Чем реально был запущен движок против того, что просили. Пусто - совпало."""
    m = OPTSLINE.search(text)
    if not m:
        return "строки [AIBENCH] options нет"
    got = dict(KV.findall(m.group(1)))
    bad = []
    for k, v in want.items():
        if k in got and got[k] != opt_norm(k, v):
            bad.append("%s=%s вместо %s" % (k, got[k], opt_norm(k, v)))
    return ", ".join(bad)

_print_lock = threading.Lock()


def say(*a):
    with _print_lock:
        print(*a)
        sys.stdout.flush()


def prepare_dir(path, master, mods_from):
    """Папка прогона: свой options.cfg и свои ссылки на моды.

    Каталог НИКОГДА не стираем целиком: внутри ссылки на установленную игру.
    """
    os.makedirs(path, exist_ok=True)
    if mods_from and os.path.isdir(mods_from):
        src_mods = os.path.join(mods_from, "mods")
        dst_mods = os.path.join(path, "mods")
        if os.path.isdir(src_mods):
            os.makedirs(dst_mods, exist_ok=True)
            for name in os.listdir(src_mods):
                link = os.path.join(dst_mods, name)
                target = os.path.join(src_mods, name)
                if not os.path.exists(link):
                    subprocess.run(["cmd", "/c", "mklink", "/J", link, target],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cfg = os.path.join(mods_from, "options.cfg")
        dst_cfg = os.path.join(path, "options.cfg")
        if os.path.exists(cfg) and not os.path.exists(dst_cfg):
            shutil.copyfile(cfg, dst_cfg)
    if master:
        os.makedirs(os.path.join(path, master), exist_ok=True)
    return path


def run_game(exe, user, data, master, extra, timeout):
    """Один запуск движка. Возвращает текст лога, секунды и признак обрыва."""
    log = os.path.join(user, "openxcom.log")
    if os.path.exists(log):
        os.remove(log)
    cmd = [exe, "-data", data, "-user", user, "-cfg", user,
           "-aiBench", "true",
           "-autoCombat", "true", "-autoCombatEachCombat", "true",
           "-autoCombatEachTurn", "true", "-autoCombatDefaultSoldier", "true",
           "-autoCombatDefaultHWP", "true",
           "-playIntro", "false", "-battleXcomSpeed", "1", "-battleAlienSpeed", "1",
           "-soundVolume", "0", "-musicVolume", "0", "-uiVolume", "0",
           "-displayWidth", "640", "-displayHeight", "400", "-maxFrameSkip", "1"]
    if master:
        cmd += ["-master", master]
    cmd += extra
    # Окна не показываем: серия идёт часами, а машина рабочая. SDL рисует в память,
    # звук в пустоту - заодно уходит спам "No free channels available" в лог
    env = dict(os.environ)
    env["SDL_VIDEODRIVER"] = "dummy"
    env["SDL_AUDIODRIVER"] = "dummy"
    t0 = time.time()
    killed = False
    try:
        # ниже обычного приоритета: серия идёт часами, за машиной в это время работают
        below_normal = getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)
        subprocess.run(cmd, timeout=timeout, cwd=os.path.dirname(exe), env=env,
                       creationflags=below_normal,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        killed = True
    text = ""
    if os.path.exists(log):
        with open(log, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    return text, time.time() - t0, killed


def one_battle(idx, args, arms, user):
    """Разыграть бой, сохранить, прогнать каждым вариантом."""
    seed = args.seed0 + idx
    sav = "series_%05d.sav" % idx
    # бой сохраняется в первом же init(), до первого хода, поэтому ключи ИИ на
    # содержимое файла не влияют; передаём их всё равно, чтобы папка прогона не
    # копила чужие значения
    gen = (["-aiBenchSeed", str(seed), "-aiBenchTurns", "1",
            "-aiBenchSave", sav, "-aiBenchLoad", ""] + opts_cmdline(BENCH_OPTS))
    text, _, killed = run_game(args.exe, user, args.data, args.master, gen, args.timeout)
    m = BATTLE.search(text)
    if killed or not m:
        say("  бой %d: розыгрыш не удался" % idx)
        return []
    setup = dict(KV.findall(m.group(1)))

    rows = []
    for name, want in arms:
        extra = (["-aiBenchTurns", str(args.turns), "-aiBenchSave", "",
                  "-aiBenchLoad", sav] + opts_cmdline(want))
        text, secs, killed = run_game(args.exe, user, args.data, args.master, extra, args.timeout)
        r = RESULT.search(text)
        row = {"battle": idx, "seed": seed, "arm": name, "wallSec": round(secs, 1),
               "mission": setup.get("mission", ""), "terrain": setup.get("terrain", ""),
               "race": setup.get("race", ""), "xcomStart": setup.get("xcom", "")}
        row["aiMs"] = sum(int(x) for x in HOSTILE.findall(text))
        bad = opts_mismatch(text, want)
        if bad and not killed:
            # молча считать такой бой нельзя: именно так три варианта превратились в два
            say("  бой %d, вариант «%s»: ЗАПУЩЕН НЕ ТЕМ - %s" % (idx, name, bad))
            row["outcome"] = "optmismatch"
            row["why"] = bad
        elif killed or not r:
            row["outcome"] = "timeout" if killed else "nofinish"
        else:
            row.update(dict(KV.findall(r.group(1))))
            row["outcome"] = "done"
        rows.append(row)

    path = os.path.join(user, args.master or "xcom1", sav)
    if os.path.exists(path):
        os.remove(path)
    done = [r for r in rows if r["outcome"] == "done"]
    say("  бой %d (%s): %s" % (idx, setup.get("mission", "?"),
        ", ".join("%s ходов=%s потери=%s/%s" % (r["arm"], r.get("turns", "?"),
                  r.get("xcomDead", "?"), r.get("alienDead", "?")) for r in done)
        or "не доигран"))
    return rows


def mean_ci(values):
    """Среднее и половина 95-процентного доверительного интервала."""
    n = len(values)
    if n == 0:
        return 0.0, 0.0
    m = sum(values) / n
    if n < 2:
        return m, 0.0
    var = sum((v - m) ** 2 for v in values) / (n - 1)
    return m, 1.96 * math.sqrt(var / n)


def summarize(rows, arms):
    done = [r for r in rows if r["outcome"] == "done"]
    say("")
    say("=== итог по вариантам (доиграно %d прогонов из %d) ===" % (len(done), len(rows)))
    say("%-20s %5s %7s %13s %8s %8s %11s"
        % ("вариант", "боёв", "ходов", "потери игрока", "убито ИИ", "размен", "победа ИИ"))
    per_arm = {}
    for name, _ in arms:
        sub = [r for r in done if r["arm"] == name]
        if not sub:
            continue
        turns = [int(r["turns"]) for r in sub]
        xdead = [int(r["xcomDead"]) for r in sub]
        adead = [int(r["alienDead"]) for r in sub]
        aiwin = [1.0 if int(r["xcomAlive"]) == 0 else 0.0 for r in sub]
        per_arm[name] = {"rows": {r["battle"]: r for r in sub}}
        mt, _ = mean_ci(turns)
        mx, cx = mean_ci(xdead)
        ma, _ = mean_ci(adead)
        mw, cw = mean_ci(aiwin)
        ratio = mx / ma if ma else float("inf")
        say("%-20s %5d %7.1f %6.2f±%-5.2f %8.2f %8.2f %6.0f%%±%.0f"
            % (name, len(sub), mt, mx, cx, ma, ratio, 100 * mw, 100 * cw))

    if len(arms) < 2 or arms[0][0] not in per_arm:
        return
    base = arms[0][0]
    say("")
    say("=== парное сравнение с «%s» (бои, доигранные обоими) ===" % base)
    for name, _ in arms[1:]:
        if name not in per_arm:
            continue
        common = sorted(set(per_arm[base]["rows"]) & set(per_arm[name]["rows"]))
        if not common:
            continue
        d_x = [int(per_arm[name]["rows"][b]["xcomDead"])
               - int(per_arm[base]["rows"][b]["xcomDead"]) for b in common]
        d_a = [int(per_arm[name]["rows"][b]["alienDead"])
               - int(per_arm[base]["rows"][b]["alienDead"]) for b in common]
        d_t = [int(per_arm[name]["rows"][b]["turns"])
               - int(per_arm[base]["rows"][b]["turns"]) for b in common]
        mx, cx = mean_ci(d_x)
        ma, ca = mean_ci(d_a)
        better = sum(1 for d in d_x if d > 0)
        worse = sum(1 for d in d_x if d < 0)
        say("%s: пар %d" % (name, len(common)))
        say("  потерь у игрока: %+.2f ± %.2f за бой (больше в %d боях, меньше в %d)"
            % (mx, cx, better, worse))
        say("  потерь у ИИ:     %+.2f ± %.2f за бой" % (ma, ca))
        mt2, ct2 = mean_ci(d_t)
        say("  ходов на бой:    %+.2f ± %.2f" % (mt2, ct2))
        if abs(mx) <= cx:
            say("  вывод: разницы не видно, доверительный интервал накрывает ноль")
        else:
            say("  вывод: разница есть, ИИ стал %s" % ("сильнее" if mx > 0 else "слабее"))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--battles", type=int, default=20, help="сколько боёв разыграть")
    p.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 4) // 2))
    p.add_argument("--turns", type=int, default=40, help="потолок ходов, дальше бой бросается")
    p.add_argument("--arm", action="append", default=[],
                   help="вариант ИИ: имя=-ключ значение -ключ значение")
    p.add_argument("--seed0", type=int, default=7000)
    p.add_argument("--exe", default=EXE)
    p.add_argument("--data", default=DATA)
    p.add_argument("--master", default="")
    p.add_argument("--user-base", default=os.path.join(FORK, "user_series"))
    p.add_argument("--mods-from", default="",
                   help="папка, откуда взять options.cfg и ссылки на моды")
    p.add_argument("--timeout", type=int, default=1800, help="потолок на один прогон, секунд")
    p.add_argument("--out", default=os.path.join(ROOT, "logs", "series.csv"))
    args = p.parse_args()

    arms = []
    for a in args.arm:
        name, _, rest = a.partition("=")
        arms.append((name.strip(), arm_opts(rest)))
    if not arms:
        arms = [("родной", arm_opts("-brutalAI 0"))]
    seen = {}
    for name, want in arms:
        key = tuple(sorted(want.items()))
        if key in seen:
            raise SystemExit("варианты «%s» и «%s» заданы одинаково: %s"
                             % (seen[key], name, want))
        seen[key] = name

    jobs = max(1, min(args.jobs, args.battles))
    users = [prepare_dir("%s_w%02d" % (args.user_base, k), args.master, args.mods_from)
             for k in range(jobs)]

    say("боёв: %d, вариантов: %d, потоков: %d, потолок ходов: %d"
        % (args.battles, len(arms), jobs, args.turns))
    t0 = time.time()
    rows = []
    lock = threading.Lock()

    def work(k):
        out = []
        for idx in range(k, args.battles, jobs):
            out += one_battle(idx, args, arms, users[k])
        with lock:
            rows.extend(out)

    with ThreadPoolExecutor(max_workers=jobs) as ex:
        list(ex.map(work, range(jobs)))

    cols = ["battle", "seed", "arm", "outcome", "why", "mission", "terrain", "race", "xcomStart",
            "turns", "abort", "inExit", "xcomAlive", "xcomStunned", "xcomDead",
            "alienAlive", "alienStunned", "alienDead", "civAlive", "civDead", "aiMs", "wallSec"]
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding=ENC, newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in sorted(rows, key=lambda r: (r["battle"], r["arm"])):
            w.writerow(r)

    summarize(rows, arms)
    say("")
    say("всего %.1f мин, записано: %s" % ((time.time() - t0) / 60, args.out))


if __name__ == "__main__":
    main()
