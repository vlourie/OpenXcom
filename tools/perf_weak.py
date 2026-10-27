# Слабый ПК на сильной машине: игра на 2/4/8 медленных ядрах (E-ядра 285K) и столько же потоков HD-рисования,
# невидимо через живой стенд (hdbench, R-124). Меряет время до меню, глобуса, базы, входа в бой, кадр боя
# (покадровый журнал движка OXCE_HD_FRAMELOG: loop/draw/flip по состояниям, p50/p95/max) и память процесса
# (рабочий набор и частная, пик и по шагам).
#   py -3.13 tools/perf_weak.py run [--cfg full,8c,4c,2c] [--set "oxceHdMode=2;..."] [--tag имя]
#   py -3.13 tools/perf_weak.py report
#   py -3.13 tools/perf_weak.py mem [--variants all,no_hd,...]   - чья память: меню/глобус/база при разных наборах модов
# Ограничения: файловый кэш ОС прогрет (холодный диск HDD не изображён); частота E-ядер выше, чем у старых ПК;
# hardware_concurrency не видит маску ядер, поэтому oxceHdThreads задаётся явно, как у игрока с таким числом ядер.
import argparse, json, os, re, subprocess, sys, tempfile, threading, time
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import hidden_game

OUT = Path(os.environ.get("PERF_WEAK_OUT", Path(tempfile.gettempdir()) / "perf_weak"))
HB = [sys.executable, str(ROOT / "tools" / "hdbench.py")]
E_CORES = list(range(8, 24))   # Core Ultra 9 285K: 0-7 P-ядра, 8-23 E-ядра
# имя -> (ядра или None = вся машина, oxceHdThreads как у игрока с таким ПК: ядер больше 4 -> ядра-2)
CFGS = {"full": (None, 0), "8c": (E_CORES[:8], 6), "4c": (E_CORES[:4], 4), "2c": (E_CORES[:2], 2)}


class Mem(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.pid, self.peak_rss, self.peak_priv, self.stop = None, 0, 0, False

    def now(self):
        try:
            m = psutil.Process(self.pid).memory_info()
            return m.rss >> 20, getattr(m, "private", m.vms) >> 20
        except (psutil.Error, TypeError, ValueError):
            return 0, 0

    def run(self):
        while not self.stop:
            if self.pid:
                r, p = self.now()
                self.peak_rss, self.peak_priv = max(self.peak_rss, r), max(self.peak_priv, p)
            time.sleep(0.25)


def hb(*args, timeout=1800, env=None):
    t0 = time.perf_counter()
    r = subprocess.run(HB + list(args), capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=timeout, env=env)
    return r.returncode, r.stdout + r.stderr, time.perf_counter() - t0


def pid_of(name):
    f = ROOT / "scratchpad" / "hdbench" / name / "pid"   # hdbench.STANDS
    return int(f.read_text()) if f.exists() else None


def frames(tsv):
    """Покадровый журнал движка -> по состоянию: число кадров и p50/p95/max для loop/draw/flip, мс."""
    by = {}
    if not tsv.exists():
        return by
    lines = tsv.read_text(encoding="utf-8", errors="replace").splitlines()
    head = lines[0].split("\t") if lines else []
    for l in lines[1:]:
        v = l.split("\t")
        if len(v) < len(head):
            continue
        r = dict(zip(head, v))
        st = r["state"].replace("N8OpenXcom", "").lstrip("0123456789").rstrip("E")
        by.setdefault(st, []).append(r)

    def pct(xs, q):
        xs = sorted(xs)
        return round(xs[min(len(xs) - 1, int(len(xs) * q))], 1) if xs else None
    res = {}
    for st, rows in by.items():
        d = {"n": len(rows)}
        for k in ("loop_us", "draw_us", "flip_us"):
            xs = [int(r[k]) / 1000 for r in rows if r.get("dump") != "1"]
            d[k[:-3]] = (pct(xs, .5), pct(xs, .95), round(max(xs), 1) if xs else None)
        res[st] = d
    return res


def stand(name, cfg_set, mem, steps, out, part):
    """Один запуск стенда: start, затем шаги [(метка, сценарий)], у каждого - время и память после."""
    user = OUT / f"u_{name}"
    tsv = out / f"frames_{part}.tsv"
    tsv.unlink(missing_ok=True)
    env = dict(os.environ, OXCE_HD_FRAMELOG=str(tsv))
    rc, txt, secs = hb("start", "--name", name, "--save", "", "--user", str(user), "--timeout", "1500", "--set", cfg_set,
                       env=env)
    m = re.search(r"pid (\d+)", txt)
    mem.pid = int(m.group(1)) if m else pid_of(name)
    rows = [{"step": "start", "rc": rc, "s": round(secs, 1), "rss": mem.now()[0], "priv": mem.now()[1]}]
    if rc != 0:
        rows[0]["err"] = txt[-600:]
        return rows
    for label, script in steps:
        rc, txt, secs = hb("run", "--name", name, "--timeout", "900", script.format(d=out.as_posix()))
        row = {"step": label, "rc": rc, "s": round(secs, 1), "rss": mem.now()[0], "priv": mem.now()[1]}
        st = re.findall(r"state (\w+)", txt)
        if st:
            row["state"] = st[-1]
        if rc != 0:
            row["err"] = txt[-600:]
        rows.append(row)
    hb("stop", "--name", name)
    rows.append({"step": "frames_log", "by_state": frames(tsv)})
    log = user / "openxcom.log"
    if log.exists():
        lt = log.read_text(encoding="utf-8", errors="replace")
        rows.append({"step": "log", "fatal": "[FATAL]" in lt,
                     "hd": [l.split("]", 2)[-1].strip() for l in lt.splitlines() if "HD render:" in l and "thread" in l][:1],
                     "stalls": [l.split("]", 2)[-1].strip()[:240] for l in lt.splitlines() if "HD stall:" in l]})
    return rows


# бой: курсор ходит по карте (перерисовка), колесо меняет уровень (полная перерисовка), всего ~10 с
SAMPLE = "; ".join([f"hover {x},{y}; wait 150" for y in (380, 520, 660) for x in range(360, 1600, 140)]
                   + ["wheel up 960,540; wait 400", "wheel down 960,540; wait 400"] * 3 + ["state"])


def run_cfg(cfg, extra, tag):
    cores, threads = CFGS[cfg]
    me = psutil.Process()
    me.cpu_affinity(cores or list(range(psutil.cpu_count())))   # игра наследует маску ядер (CreateProcess)
    name = f"pw_{tag}_{cfg}"
    out = OUT / name
    out.mkdir(parents=True, exist_ok=True)
    cfg_set = ";".join(x for x in [f"oxceHdThreads={threads}", extra] if x)
    mem = Mem()
    mem.start()
    res = {"cfg": cfg, "cores": cores, "threads": threads, "set": cfg_set, "tag": tag}
    res["ui"] = stand(name, cfg_set, mem, [
        ("geoscape", "open geoscape; wait 3000; shot {d}/geo.png; state"),
        ("base", "open base; wait 3000; shot {d}/base.png; state"),
    ], out, "ui")
    res["ui_peak"] = (mem.peak_rss, mem.peak_priv)
    mem.peak_rss = mem.peak_priv = 0
    res["battle"] = stand(name, cfg_set, mem, [
        ("battle_open", "open battle; state"),
        ("inventory", "key 13; wait 8000; state"),
        ("battle", "key 27; wait 3000; key 13; wait 6000; shot {d}/battle.png; state"),
        ("frames", SAMPLE),
    ], out, "battle")
    res["battle_peak"] = (mem.peak_rss, mem.peak_priv)
    mem.stop = True
    (out / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8-sig")
    print(summary(res), flush=True)
    return res


def summary(r):
    def step(part, s):
        return next((x for x in r[part] if x.get("step") == s), {})
    def fr(part, st):
        d = step(part, "frames_log").get("by_state", {}).get(st)
        return f"{st} n{d['n']} loop p50/p95/max {d['loop']} draw {d['draw']}" if d else f"{st} -"
    return (f"{r['tag']}/{r['cfg']}: потоков {r['threads']} | меню {step('ui', 'start').get('s')} с, глобус "
            f"{step('ui', 'geoscape').get('s')} с, база {step('ui', 'base').get('s')} с | бой: вход "
            f"{step('battle', 'battle_open').get('s')} с, до хода {step('battle', 'battle').get('s')} с | память пик: "
            f"интерфейс {r['ui_peak'][0]} МБ, бой {r['battle_peak'][0]} МБ (частная {r['battle_peak'][1]})\n  "
            f"{fr('ui', 'GeoscapeState')}\n  {fr('ui', 'BasescapeState')}\n  {fr('battle', 'BattlescapeState')}")


# Чья память: тот же стенд в меню и на глобусе с разными наборами модов и опций (всё прочее - как у игрока)
MEM_VARIANTS = {
    "all": "",
    "no_hd": "mods:hd=false",
    "no_voices": "mods:hd_voices_ru=false",
    "no_hd_stack": "mods:hd=false;hd_core=false;hd_voices_ru=false;hd_test_steps=false;intro_voice=false",
    "mode0": "set:oxceHdMode=0;oxceHdUi=0",
}


def mem_probe(variants):
    rows = []
    for v in variants:
        kind, _, val = MEM_VARIANTS[v].partition(":")
        name = f"pw_mem_{v}"
        user = OUT / f"u_{name}"
        args = ["start", "--name", name, "--save", "", "--user", str(user), "--timeout", "900"]
        args += ["--mods", val] if kind == "mods" else ["--set", val] if kind == "set" else []
        rc, txt, secs = hb(*args)
        m = re.search(r"pid (\d+)", txt)
        pid = int(m.group(1)) if m else pid_of(name)
        mem = Mem()
        mem.pid = pid
        row = {"variant": v, "rc": rc, "menu_s": round(secs, 1)}
        hb("run", "--name", name, "wait 3000")
        row["menu"] = mem.now()
        hb("run", "--name", name, "open geoscape; wait 4000")
        row["geoscape"] = mem.now()
        hb("run", "--name", name, "open base; wait 3000")
        row["base"] = mem.now()
        hb("stop", "--name", name)
        print(f"{v}: меню {row['menu_s']} с | RSS/частная МБ: меню {row['menu']}, глобус {row['geoscape']}, "
              f"база {row['base']}", flush=True)
        rows.append(row)
    (OUT / "mem.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8-sig")


def main():
    hidden_game.utf8_streams()
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "report", "mem"])
    ap.add_argument("--variants", default=",".join(MEM_VARIANTS))
    ap.add_argument("--cfg", default="full,4c,2c")
    ap.add_argument("--set", default="", help="доп. опции через ;")
    ap.add_argument("--tag", default="def")
    a = ap.parse_args()
    if a.cmd == "report":
        for f in sorted(OUT.glob("pw_*/result.json")):
            print(summary(json.loads(f.read_text(encoding="utf-8-sig"))))
        return
    psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    if a.cmd == "mem":
        mem_probe(a.variants.split(","))
        return
    for c in a.cfg.split(","):
        run_cfg(c, a.set, a.tag)


if __name__ == "__main__":
    main()
