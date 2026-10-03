#!/usr/bin/env python3
"""Замер кадра боя для HD-юнитов (docs/HD_UNITS.md, раздел 9): p50/p95/p99 по каждому нарисованному кадру.

Бой идёт невидимо (ai_probe.Hidden: свой рабочий стол, SDL dummy - R-124): бот стенда ведёт обе стороны
на НАСТОЯЩИХ часах (OXCE_AI_REALTIME=1), с анимацией и темпом кадров игрока (OXCE_AI_FAST=0). Движок пишет
строку на каждый нарисованный кадр (OXCE_HD_FRAMELOG, Engine/Game.cpp): loop_us - работа прохода без ожидания
кадра, draw_us - рисование состояний и HD-слоя, flip_us - вывод, pack_fr / pack_ms - чтение кадров паков.
Флаги стенда, меняющие расчёт ИИ (LIGHTSKIP и др.), выключены: в сборке игрока их нет.

  py -3.13 tools/unit_perf.py --build <каталог сборки с OXCE_AI_DEV> --name b201_m2k4 \
      --mission STR_VESSEL_BOMBER_SECTOID_ELITE --seed 201 --mode 2 --scale 4 --display 2560x1440 --turns 3

Итог: census/perf_units/<имя>/frames.tsv, memory.tsv, summary.json и строка в census/perf_units/runs.tsv.
Ограничение: SDL dummy выводит кадр в никуда - flip_us меньше, чем на настоящем экране; draw_us - настоящий."""
import argparse, hashlib, json, os, re, shutil, sys, threading, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "census" / "perf_units"
ENC = "utf-8-sig"  # R-001
COLS = ("loop_us", "think_us", "draw_us", "flip_us")


class Memory(threading.Thread):
    """Рабочий набор и частная память процесса игры раз в 250 мс, пока он жив."""

    def __init__(self, pid):
        super().__init__(daemon=True)
        self.pid, self.rows, self.t0 = pid, [], time.time()

    def run(self):
        import psutil
        try:
            p = psutil.Process(self.pid)
        except psutil.Error:
            return
        while True:
            try:
                m = p.memory_info()
                self.rows.append((round(time.time() - self.t0, 2), m.rss, getattr(m, "private", 0)))
            except psutil.Error:
                return
            time.sleep(0.25)


def pct(values, q):
    if not values:
        return None
    v = sorted(values)
    return v[min(len(v) - 1, int(round(q / 100 * (len(v) - 1))))]


def summarize(frames):
    """Кадры боя: распределения по столбцам, счёт медленных, чтение паков."""
    battle = [f for f in frames if "BattlescapeState" in f["state"] and not f["dump"]]
    out = {"frames_all": len(frames), "frames_battle": len(battle)}
    if not battle:
        return out
    span = (battle[-1]["t_ms"] - battle[0]["t_ms"]) / 1000
    out["battle_seconds"] = round(span, 1)
    out["fps_drawn"] = round(len(battle) / span, 1) if span > 0 else None
    out["entry_ms"] = battle[0]["t_ms"]  # от первого прохода цикла до первого кадра боя: моды, сборка боя
    for c in COLS:
        v = [f[c] / 1000 for f in battle]
        out[c[:-3] + "_ms"] = {"p50": round(pct(v, 50), 3), "p95": round(pct(v, 95), 3), "p99": round(pct(v, 99), 3),
                               "max": round(max(v), 3), "mean": round(sum(v) / len(v), 3)}
    loop = [f["loop_us"] / 1000 for f in battle]
    out["over_16ms"] = sum(1 for x in loop if x >= 16.7)
    out["over_33ms"] = sum(1 for x in loop if x >= 33)
    out["over_100ms"] = sum(1 for x in loop if x >= 100)
    packs = [f for f in battle if f["pack_fr"]]
    out["pack_reads"] = {"frames_with_reads": len(packs), "sprites": sum(f["pack_fr"] for f in packs),
                         "ms_total": round(sum(f["pack_ms"] for f in packs), 1),
                         "ms_max_frame": round(max((f["pack_ms"] for f in packs), default=0), 2)}
    # прогрев: первые 10 с боя против остального - холодные кэши паков и сглаживания
    t0 = battle[0]["t_ms"]
    early = [f["loop_us"] / 1000 for f in battle if f["t_ms"] - t0 < 10000]
    late = [f["loop_us"] / 1000 for f in battle if f["t_ms"] - t0 >= 10000]
    out["first10s_loop_p95"] = round(pct(early, 95), 3) if early else None
    out["after10s_loop_p95"] = round(pct(late, 95), 3) if late else None
    # куда ушло рисование (столбцы HdDrawStats): медленные кадры по одному и медиана обычного кадра
    if "record_us" in battle[0]:
        parts = ("record_us", "units_us", "script_us", "smooth_us", "smooth_n", "toned_us", "toned_n",
                 "flush_us", "strip_max_us", "cmds")
        out["draw_parts_p50"] = {c: pct([f[c] for f in battle], 50) for c in parts}
        slow = sorted((f for f in battle if f["draw_us"] >= 50000), key=lambda f: -f["draw_us"])
        out["slow_draw"] = [dict({"t_ms": f["t_ms"], "draw_us": f["draw_us"], "pack_fr": f["pack_fr"],
                                  "ui_ms": f["ui_ms"]}, **{c: f[c] for c in parts}) for f in slow[:20]]
    return out


def log_summary(text):
    """То же, что движок пишет и без журнала кадров: окна HD frame по 2 с и строки HD stall, только бой.
    По ним сравниваются прогоны с журналом и без (цена самого журнала)."""
    body = [l.split("\t", 2)[-1] for l in text.splitlines()]
    start = next((i for i, l in enumerate(body) if "BattlescapeState" in l and l.startswith("HD ")), None)
    if start is None:
        return {}
    end = next((i for i, l in enumerate(body) if l.startswith("[AIPROBE] done")), len(body))
    wins, stalls = [], []
    for l in body[start:end]:
        m = re.match(r"HD frame: (\d+) fr, worst (\d+) ms \((\S+)\), >=33 ms (\d+), >=100 ms (\d+)", l)
        if m:
            wins.append(tuple(int(m.group(i)) for i in (1, 2, 4, 5)))
        m = re.match(r"HD stall: (\d+) ms on \S+ \|.* think (\d+) blit (\d+) flip (\d+)", l)
        if m:
            stalls.append(tuple(int(x) for x in m.groups()))
    worst = [w[1] for w in wins]
    return {"windows": len(wins), "loops": sum(w[0] for w in wins), "loops_per_window": round(sum(w[0] for w in wins) / len(wins), 1) if wins else None,
            "window_worst_p50": pct(worst, 50), "window_worst_p95": pct(worst, 95), "window_worst_max": max(worst, default=None),
            "ge33": sum(w[2] for w in wins), "ge100": sum(w[3] for w in wins),
            "stalls_think": sum(1 for s in stalls if s[1] >= 100), "stalls_blit": sum(1 for s in stalls if s[2] >= 100),
            "stall_blit_max": max((s[2] for s in stalls), default=0)}


def read_frames(path):
    rows = []
    with open(path, encoding="utf-8", errors="replace") as f:
        head = f.readline().rstrip("\n").split("\t")
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) != len(head):
                continue  # хвост, оборванный на выходе
            r = dict(zip(head, p))
            for k in ("t_ms", "loop_us", "think_us", "draw_us", "flip_us", "pack_fr", "dump", "record_us", "units_us",
                      "script_us", "smooth_us", "smooth_n", "toned_us", "toned_n", "flush_us", "strip_max_us", "cmds"):
                if k in r:
                    r[k] = int(r[k])
            r["pack_ms"], r["ui_ms"] = float(r["pack_ms"]), float(r["ui_ms"])
            rows.append(r)
    return rows


def main():
    sys.stdout.reconfigure(encoding="utf-8")  # R-001
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", required=True, help="каталог сборки с OXCE_AI_DEV (bin/openxcom.exe внутри)")
    ap.add_argument("--name", required=True)
    ap.add_argument("--mission", required=True)
    ap.add_argument("--seed", type=int, default=201)
    ap.add_argument("--mode", type=int, default=2, help="oxceHdMode: 0 nearest, 1 паки, 2 паки + xBRZ")
    ap.add_argument("--scale", type=int, default=4, help="oxceHdScale")
    ap.add_argument("--threads", type=int, default=0, help="oxceHdThreads: 0 - все ядра, как у игрока")
    ap.add_argument("--display", default="2560x1440")
    ap.add_argument("--turns", type=int, default=3)
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--opt", action="append", default=[], help="ещё ключ options.cfg прогона: oxceHdLight=false")
    ap.add_argument("--no-framelog", action="store_true",
                    help="без журнала кадров: только строки HD frame / HD stall лога - замер цены самого журнала")
    a = ap.parse_args()

    os.environ["OXCE_AI_BUILD"] = a.build
    for k in [k for k in os.environ if k.startswith("OXCE_AI_RECORD")]:
        os.environ.pop(k)
    # сборка игрока: ни одного флага стенда, который меняет расчёт; кадры и анимация как у игрока
    for k in ("OXCE_AI_LIGHTSKIP", "OXCE_AI_AMBUSH_MEMO", "OXCE_AI_ESCAPE_REACH_FIRST", "OXCE_AI_WALKFOV_SKIP",
              "OXCE_AI_FAST"):
        os.environ[k] = "0"
    os.environ["OXCE_AI_REALTIME"] = "1"
    sys.path.insert(0, str(ROOT / "tools"))
    import ai_probe

    if not ai_probe.EXE.is_file():
        sys.exit(f"нет exe: {ai_probe.EXE}")
    run_dir = OUT / a.name
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)
    work = ai_probe.WORK / ("perf_" + a.name)
    framelog = work / "frames.tsv"
    if framelog.exists():
        framelog.unlink()
    opts = {"oxceHdMode": a.mode, "oxceHdScale": a.scale, "oxceHdThreads": a.threads}
    for kv in a.opt:
        k, v = kv.split("=", 1)
        opts[k] = v
    base_prepare, base_hidden, holder = ai_probe.prepare_user, ai_probe.Hidden, {}

    def prepare(w):
        """Как ai_probe.prepare_user, но графика - как задано (стенд ставит масштаб 1, режим 0, один поток)."""
        base_prepare(w)
        cfg = (w / "options.cfg").read_bytes().decode("utf-8")
        for k, v in opts.items():
            cfg, n = re.subn(rf"(?m)^(\s*){k}: .*$", rf"\g<1>{k}: {v}", cfg)
            if not n:
                cfg = re.sub(r"(?m)^options:\s*$", lambda m: m.group(0) + f"\n  {k}: {v}", cfg, count=1)
        (w / "options.cfg").write_bytes(cfg.encode("utf-8"))  # читает игра - без спецификации (R-001)

    class Measured(base_hidden):
        def __init__(self, args, cwd, env):
            if not a.no_framelog:
                env["OXCE_HD_FRAMELOG"] = str(framelog)
            wdt, hgt = a.display.split("x")
            args[args.index("-displayWidth") + 1] = wdt
            args[args.index("-displayHeight") + 1] = hgt
            super().__init__(args, cwd, env)
            holder["mem"] = Memory(self.pid)
            holder["mem"].start()

    ai_probe.prepare_user, ai_probe.Hidden = prepare, Measured
    t0 = time.time()
    res = ai_probe.run(None, a.turns, name="perf_" + a.name, timeout=a.timeout, bot=True, seed=a.seed,
                       campaign="NoCodexCatZ.sav", mission=a.mission, careful=True, squad=8)
    wall = time.time() - t0
    if not a.no_framelog and not framelog.is_file():
        sys.exit(f"нет журнала кадров {framelog}: сборка без OXCE_HD_FRAMELOG? лог {res.log}")
    if not a.no_framelog:
        shutil.copyfile(framelog, run_dir / "frames.tsv")
    shutil.copyfile(res.log, run_dir / "openxcom.log")
    mem = holder["mem"].rows
    with open(run_dir / "memory.tsv", "w", encoding=ENC) as f:
        f.write("t_s\trss_mb\tprivate_mb\n")
        for t, rss, priv in mem:
            f.write(f"{t}\t{rss / 2**20:.0f}\t{priv / 2**20:.0f}\n")
    s = {} if a.no_framelog else summarize(read_frames(framelog))
    log = res.log.read_text(encoding="utf-8", errors="replace")
    s["framelog"] = not a.no_framelog
    s["log"] = log_summary(log)
    perf = re.findall(r"HD perf: (\d+x\d+ k=\d+ mode=\d+[^\n]*)", log)
    st = ai_probe.EXE.stat()
    s.update({"name": a.name, "mission": a.mission, "seed": a.seed, "mode": a.mode, "scale": a.scale,
              "threads": a.threads, "display": a.display, "turns": a.turns, "opts": opts, "wall_s": round(wall, 1),
              "finished": res.finished, "rss_peak_mb": round(max((r[1] for r in mem), default=0) / 2**20),
              "private_peak_mb": round(max((r[2] for r in mem), default=0) / 2**20),
              "hd_perf_last": perf[-1] if perf else "",
              "exe": str(ai_probe.EXE), "exe_mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime)),
              "exe_sha256": hashlib.sha256(ai_probe.EXE.read_bytes()).hexdigest()[:16],
              "host": os.environ.get("COMPUTERNAME", ""), "when": time.strftime("%Y-%m-%d %H:%M")})
    (run_dir / "summary.json").write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding=ENC)
    runs = OUT / "runs.tsv"
    fields = ("when", "host", "name", "mission", "seed", "mode", "scale", "display", "frames_battle", "fps_drawn",
              "entry_ms", "loop_p50", "loop_p95", "loop_p99", "loop_max", "draw_p50", "draw_p95", "draw_p99",
              "flip_p95", "think_p95", "over_33ms", "over_100ms", "pack_sprites", "pack_ms", "rss_peak_mb",
              "private_peak_mb", "finished", "framelog", "log_loops", "log_ge33", "log_ge100", "log_stalls_blit",
              "log_stall_blit_max", "exe_sha256")
    row = dict(s)
    for k in ("loops", "ge33", "ge100", "stalls_blit", "stall_blit_max"):
        row["log_" + k] = s["log"].get(k, "")
    for c in ("loop", "draw", "flip", "think"):
        for q in ("p50", "p95", "p99", "max"):
            row[f"{c}_{q}"] = s.get(f"{c}_ms", {}).get(q, "")
    row["pack_sprites"] = s.get("pack_reads", {}).get("sprites", "")
    row["pack_ms"] = s.get("pack_reads", {}).get("ms_total", "")
    new = not runs.exists()
    with open(runs, "a", encoding=ENC) as f:
        if new:
            f.write("\t".join(fields) + "\n")
        f.write("\t".join(str(row.get(k, "")) for k in fields) + "\n")
    lp = s.get("loop_ms", {})
    print(f"{a.name}: {s.get('frames_battle', 0)} кадров боя за {s.get('battle_seconds', 0)} с, "
          f"проход p50/p95/p99 {lp.get('p50')}/{lp.get('p95')}/{lp.get('p99')} мс, макс {lp.get('max')}, "
          f">=33 мс {s.get('over_33ms')}, вход {s.get('entry_ms')} мс, память {s['rss_peak_mb']} МБ, "
          f"{'закончен' if res.finished else 'НЕ закончен'} за {wall:.0f} с")


if __name__ == "__main__":
    main()
