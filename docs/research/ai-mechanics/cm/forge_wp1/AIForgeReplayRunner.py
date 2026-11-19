"""AI FORGE WP1: the deterministic replay runner: INITIAL STATE + CONFIG + SEED + VIRTUAL CLOCK -> EVENT N. Every run starts the battle from the start, no save in the middle.

  fingerprint                  the fingerprint of D0 (exe, commit, data, flags, scenario, bot, clock) -> D0_FINGERPRINT.json
  up                           exe FG, env, runner's arms and the stop point to rabota, hashes compared
  freeze                       the build is frozen -> FROZEN.txt; the final runs refuse any other exe
  run <id> [--stop N]          one run of the plan on rabota; the budget (8) is kept in ledger.tsv and checked before anything starts
  compare <a> <b>              two runs: engine lines, chain, sections, dumps; the first difference, exactly
  report                       all the planned comparisons -> WP1_COMPARE.json
"""
import gzip
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import scheduler_integrity_check as sic

HERE = Path(__file__).resolve().parent
S = HERE.parent
ST = S / "cm" / "st"
RES = HERE / "res"
LEDGER = HERE / "ledger.tsv"
FROZEN = HERE / "FROZEN.txt"
BUDGET = 8
KEY = os.path.expanduser("~/.ssh/oxce_worker")
HOST = "user@100.93.184.94"
R = "C:\\OXCE_AIWorker\\cmrun"
X = "openxcom" ".exe"
EXE = HERE / "b-f" / "bin" / X
TURNS = 60
ARCHIVE = S / "sfc" / "res" / "res_sfF.zip"
# id: arm, scenario, what it is. Written before the first run; WP1_PLAN.md says the same.
PLAN = {
    "P1": ("FGS", "L8", "smoke, SHADOW"),
    "P2": ("FGS", "L8", "reserve: after one fix only"),
    "R1": ("FGO", "M3", "OFF"),
    "R2": ("FGS", "M3", "SHADOW"),
    "R3": ("FGR", "M3", "REPLAY to the limit"),
    "R4": ("FGO", "L8", "OFF"),
    "R5": ("FGS", "L8", "SHADOW"),
    "R6": ("FGT", "L8", "REPLAY to event N and stop"),
}
FINAL = ("R1", "R2", "R3", "R4", "R5", "R6")
ARCHIVED = {"M3": "sfF_D_M3_s1", "L8": "sfF_D_L8_s1"}
SEP = re.compile(r'"(us|ms|t_us)":\d+,?')
MS = re.compile(r" ms=\d+")
SECTIONS = ("S", "U", "A", "I", "O", "M", "N", "B", "J", "R", "C")
SECTION_NAME = {"S": "scheduler", "U": "units", "A": "AI modules", "I": "items", "O": "inventory order", "M": "map", "N": "nodes", "B": "bot", "J": "item ids",
                "R": "RNG", "C": "virtual clock"}


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def ssh(cmd):
    return subprocess.run(["ssh", "-o", "ConnectTimeout=15", "-i", KEY, HOST, cmd], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout


def ps(cmd):
    return ssh(f'powershell -NoProfile -ExecutionPolicy Bypass -Command "{cmd}"')


def scp(*args):
    subprocess.check_call(["scp", "-q", "-i", KEY, *args])


def remote_hash(path):
    return ps(f"(Get-FileHash '{path}').Hash").strip().lower()


def label_of(rid):
    arm, scen, _ = PLAN[rid]
    return f"fg{rid}_{arm}_{scen}_s1"


def source_of(name):
    """A run of the plan, or an archived arm: arch:M3."""
    if name.startswith("arch:"):
        return ARCHIVE, ARCHIVED[name[5:]]
    return RES / f"res_fg{name}.zip", label_of(name)


def prov(zp, label):
    with zipfile.ZipFile(zp) as z:
        t = z.read(f"arena/{label}.prov.txt").decode("utf-8", errors="replace")
    fp = dict(re.findall(r"(\w+)=([0-9a-f]{16,})", next(s for s in t.splitlines() if s.startswith("fingerprint:"))))
    flags = next(s for s in t.splitlines() if s.startswith("effective_flags=")).split("=", 1)[1]
    return fp, dict(kv.split("=", 1) for kv in flags.split(";") if kv), t


def split(lines):
    game = []
    forge = []
    dumps = {}
    for s in lines:
        if s.startswith("[FORGE] "):
            forge.append(s)
        elif s.startswith("[FORGEDUMP] "):
            m = re.match(r"\[FORGEDUMP\] at=(\d+) (.*)", s)
            dumps.setdefault(int(m.group(1)), []).append(m.group(2))
        elif s.startswith("[AI"):
            game.append(MS.sub("", SEP.sub("", s)))
    return game, forge, dumps


def section_diff(a, b):
    da = dict(sic.KV.findall(a))
    db = dict(sic.KV.findall(b))
    return [k for k in SECTIONS if da.get(k) != db.get(k)]


CLOCK = re.compile(r" C=(\d+)")
CHAIN = re.compile(r"^\[FORGE\] n=(\d+) h=[0-9a-f]+")


def relative_clock(forge, dumps):
    """The clock counted from the run's own first reading, the chain's hash taken out of the text.
    Added after the first look at R2/R3: the raw chain parts at n=3 only in the clock's origin, and every comparison still reports the raw result too."""
    readings = [int(m.group(1)) for x in forge for m in [CLOCK.search(x)] if m]
    c0 = readings[0] if readings else 0
    move = lambda s: CLOCK.sub(lambda m: f" C=+{int(m.group(1)) - c0}", s)
    return [CHAIN.sub(lambda m: f"[FORGE] n={m.group(1)}", move(x)) for x in forge], {n: [move(x) for x in v] for n, v in dumps.items()}


def game_before(lines, n):
    """The engine's lines written before forge event n."""
    head = f"[FORGE] n={n} "
    out = []
    for s in lines:
        if s.startswith(head):
            break
        if s.startswith("[AI"):
            out.append(MS.sub("", SEP.sub("", s)))
    return out


def compare(na, nb, stop_ok=False):
    za, la = source_of(na)
    zb, lb = source_of(nb)
    la_, lb_ = sic.read_log(za, la), sic.read_log(zb, lb)
    ga, fa, da = split(la_)
    gb, fb, db = split(lb_)
    out = {"a": na, "b": nb, "game_lines": [len(ga), len(gb)], "forge_events": [len(fa), len(fb)]}
    if fa and fb:
        na_, da_ = relative_clock(fa, da)
        nb_, db_ = relative_clock(fb, db)
        fx = next(({"event": i + 1, "a": x[:600], "b": y[:600]} for i, (x, y) in enumerate(zip(na_, nb_)) if x != y), None)
        out["relative_first_difference"] = fx
        out["relative_identical"] = fx is None and len(na_) == len(nb_)
        out["relative_same_prefix"] = fx is None
        out["relative_chain"] = [hashlib.sha256("\n".join(v[:min(len(na_), len(nb_))]).encode("utf-8")).hexdigest() for v in (na_, nb_)]
        common_ = sorted(set(da_) & set(db_))
        out["relative_dumps_compared"] = len(common_)
        out["relative_dump_first_difference"] = next(({"at": n, "a": x[:300], "b": y[:300]} for n in common_ for x, y in zip(da_[n], db_[n]) if x != y), None)
        out["relative_dump_lines_equal"] = all(len(da_[n]) == len(db_[n]) for n in common_)
        ca = [int(m.group(1)) for x in fa for m in [CLOCK.search(x)] if m]
        cb = [int(m.group(1)) for x in fb for m in [CLOCK.search(x)] if m]
        out["clock_shifts"] = {str(k): sum(1 for x, y in zip(ca, cb) if x - y == k) for k in {x - y for x, y in zip(ca, cb)}}
        if len(fa) != len(fb):
            last = int(CHAIN.match((fa if len(fa) < len(fb) else fb)[-1]).group(1))
            pa, pb = game_before(la_, last), game_before(lb_, last)
            out["stop_event"] = last
            out["game_before_stop"] = [len(pa), len(pb)]
            out["game_before_stop_identical"] = pa == pb
            out["stop_section_values"] = next(({"a": x[:600], "b": y[:600]} for x, y in zip(na_, nb_) if x.startswith(f"[FORGE] n={last} ")), None)
    first = None
    for i, (x, y) in enumerate(zip(ga, gb)):
        if x != y:
            first = {"line": i, "a": x[:500], "b": y[:500]}
            break
    prefix = min(len(ga), len(gb))
    out["game_first_difference"] = first
    out["game_identical"] = first is None and len(ga) == len(gb)
    out["game_same_prefix"] = first is None
    if fa and fb:
        first = None
        for x, y in zip(fa, fb):
            if x != y:
                first = {"a": x[:600], "b": y[:600], "sections": section_diff(x, y)}
                break
        out["chain_first_difference"] = first
        out["chain_identical"] = first is None and len(fa) == len(fb)
        out["chain_same_prefix"] = first is None
        fps = [(x, y) for x, y in zip(fa, fb) if " ev=fp " in x]
        out["fingerprints_compared"] = len(fps)
        out["fingerprints_equal"] = sum(1 for x, y in fps if x == y)
        wanted = [k for k in SECTIONS]
        out["section_differs_count"] = {k: sum(1 for x, y in fps if k in section_diff(x, y)) for k in wanted}
        common = sorted(set(da) & set(db))
        bad = next(({"at": n, "a": x[:300], "b": y[:300]} for n in common for x, y in zip(da[n], db[n]) if x != y), None)
        out["dumps_compared"] = len(common)
        out["dump_first_difference"] = bad
        boundaries = [dict(sic.KV.findall(x)) for x in (fa if len(fa) >= len(fb) else fb) if " ev=boundary " in x]
        out["boundaries"] = {b["kind"]: int(re.search(r"n=(\d+)", x).group(1)) for b, x in zip(boundaries, [x for x in (fa if len(fa) >= len(fb) else fb) if " ev=boundary " in x])}
    return out


def resource(name):
    z, l = source_of(name)
    lines = sic.read_log(z, l)
    res = next((s for s in lines if s.startswith("[AIRESULT]")), "")
    d = dict(sic.KV.findall(res))
    size = 0
    with zipfile.ZipFile(z) as zf:
        size = len(gzip.decompress(zf.read(f"out/{l}/openxcom.log.gz")))
    return {"run": name, "ms": int(d.get("ms", 0)), "vms": int(d.get("vms", 0)), "how": d.get("how"), "turn": d.get("turn"), "log_bytes": size,
            "forge_lines": sum(1 for s in lines if s.startswith("[FORGE] ")), "dump_lines": sum(1 for s in lines if s.startswith("[FORGEDUMP] "))}


def cmd_fingerprint():
    fp, flags, text = prov(ARCHIVE, ARCHIVED["M3"])
    fp8, flags8, _ = prov(ARCHIVE, ARCHIVED["L8"])
    remote = {}
    for name, path in {"exe_D0": f"{R}\\exe\\D0\\{X}", "base_cfg": f"{R}\\cfg\\base.cfg", "save_strim": f"{R}\\saves\\strim.sav", "save_NoCodexCatZ": f"{R}\\saves\\NoCodexCatZ.sav",
                       "scen_tsv": f"{R}\\scen.tsv", "ai_arena": f"{R}\\stand\\ai_arena.py", "ai_probe": f"{R}\\stand\\ai_probe.py"}.items():
        remote[name] = remote_hash(path)
    cfg = ps(f"Get-Content {R}\\cfg\\base.cfg | Select-String -Pattern 'oxceBetterAi|BetterAi|oxceAi|Ai3|Fixes' | ForEach-Object {{ $_.Line.Trim() }}")
    out = {"exe_sha256": fp.get("exe"), "commit": "07680cadb7f7246fd57d663ca7a7ae1cde531b36", "build": "HEAD 07680cadb + al.diff + al3.diff, DEV, Release",
           "archive": str(ARCHIVE), "archive_sha256": sha(ARCHIVE), "M3_s1": {"label": ARCHIVED["M3"], "seed": 2015001, "fingerprints": fp, "flags": flags, "campaign": "strim.sav", "mission": "STR_ERIDIAN_TERROR", "race": "STR_ERIDIAN"},
           "L8_s1": {"label": ARCHIVED["L8"], "seed": 2032001, "fingerprints": fp8, "flags": flags8, "campaign": "NoCodexCatZ.sav", "mission": "STR_BATTLESHIP", "race": "STR_ETHEREAL"},
           "squad": 8, "turn_limit": TURNS, "clock": "virtual (OXCE_AI_FAST=1: Timer::probeClock)", "bot": "the bench bot of exe D0 and ai_probe.py (hash above), no bot flag beyond these",
           "rabota_now": remote, "cfg_ai_lines": cfg.split("\n")}
    (HERE / "D0_FINGERPRINT.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8-sig")
    print(json.dumps({k: out[k] for k in ("exe_sha256", "rabota_now", "cfg_ai_lines")}, ensure_ascii=False, indent=1))


def cmd_up(stop):
    T = ST
    d = T / "exe" / "FG"
    d.mkdir(parents=True, exist_ok=True)
    h = sha(EXE)
    (d / X).write_bytes(EXE.read_bytes())
    (d / "BUILD_INFO.txt").write_text(f"build_label=cmrun-FG\ngit_commit=07680cadb\nnote=HEAD + al.diff + al3.diff + AI FORGE WP1 SchedulerIntegrityMonitor (read only)\nmonitor_sha256={sha(HERE / 'mon' / 'SchedulerIntegrityMonitor.cpp')}\n", encoding="utf-8")
    env = (T / "env_D0.txt").read_text(encoding="utf-8").replace("/exe/D0/", "/exe/FG/")
    (T / "env_FG.txt").write_text(env, encoding="utf-8")
    run = (T / "run_cm.py").read_text(encoding="utf-8")
    new = '''        # AI FORGE WP1 (GO Vitali 06.11, at most 8 runs): exe FG (D0 + the read-only monitor): FGO - off; FGS, FGR - shadow, replay; FGT - replay to event N (forge_stop.txt) and stop
        "FGO": ("env_FG.txt", [], COMMON_D0), "FGS": ("env_FG.txt", ["OXCE_AI_FORGE=1"], COMMON_D0), "FGR": ("env_FG.txt", ["OXCE_AI_FORGE=1"], COMMON_D0),
        "FGT": ("env_FG.txt", ["OXCE_AI_FORGE=1"] + [k + "=" + ((HERE / "forge_stop.txt").read_text().strip() if (HERE / "forge_stop.txt").exists() else "0") for k in ("OXCE_AI_FORGE_STOP", "OXCE_AI_FORGE_DUMP")], COMMON_D0),
}
TURNS = 60
'''
    if '"FGO"' not in run:
        old = "}\nTURNS = 60\n"
        assert run.count(old) == 1
        run = run.replace(old, new)
        (T / "run_cm.py").write_text(run, encoding="utf-8")
    ssh(f"if not exist {R}\\exe\\FG mkdir {R}\\exe\\FG")
    scp(str(d / X), str(d / "BUILD_INFO.txt"), f"{HOST}:C:/OXCE_AIWorker/cmrun/exe/FG/")
    files = [str(T / "env_FG.txt"), str(T / "run_cm.py")]
    if stop:
        (T / "forge_stop.txt").write_text(str(stop), encoding="utf-8")
        files.append(str(T / "forge_stop.txt"))
    scp(*files, f"{HOST}:C:/OXCE_AIWorker/cmrun/")
    rh = remote_hash(f"{R}\\exe\\FG\\{X}")
    print("local ", h)
    print("remote", rh, "OK" if rh == h else "DIFFERENT")
    print("run_cm", sha(T / "run_cm.py") == remote_hash(f"{R}\\run_cm.py"))
    if rh != h:
        raise SystemExit(2)


def cmd_freeze():
    h = sha(EXE)
    FROZEN.write_text(f"exe_sha256={h}\nfrozen={time.strftime('%Y-%m-%dT%H:%M:%S')}\nmonitor_cpp={sha(HERE / 'mon' / 'SchedulerIntegrityMonitor.cpp')}\n", encoding="utf-8")
    print(FROZEN.read_text(encoding="utf-8"))


def ledger():
    if not LEDGER.exists():
        return []
    return [s.split("\t") for s in LEDGER.read_text(encoding="utf-8").splitlines() if s.strip()]


def cmd_run(rid, stop):
    if rid not in PLAN:
        raise SystemExit(f"{rid}: not in the plan")
    done = ledger()
    if len(done) >= BUDGET:
        raise SystemExit(f"budget: {len(done)} of {BUDGET} used")
    if any(x[0] == rid for x in done):
        raise SystemExit(f"{rid}: already run")
    arm, scen, role = PLAN[rid]
    rh = remote_hash(f"{R}\\exe\\FG\\{X}")
    if rid in FINAL:
        frozen = dict(x.split("=", 1) for x in FROZEN.read_text(encoding="utf-8").splitlines() if "=" in x)["exe_sha256"]
        if rh != frozen:
            raise SystemExit(f"{rid}: exe on rabota {rh} is not the frozen one {frozen}")
    if arm == "FGT":
        if not stop:
            raise SystemExit("FGT needs --stop N")
        cmd_up(stop)
    st = ps("(Get-ScheduledTask oxce_cmrun).State").strip()
    if st == "Running":
        raise SystemExit("the task is running")
    # no battle starts here: an unknown scenario stops run_cm after the arm has been accepted
    dry = subprocess.run(["ssh", "-o", "ConnectTimeout=15", "-i", KEY, HOST, f"cd /d {R} && C:\\OXCE_AIWorker\\python\\python.exe -u run_cm.py --arms {arm} --pairs ZZ:1 --prefix dry"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
    if "unknown scenario" not in dry:
        raise SystemExit(f"arm {arm} is not accepted on rabota: {dry[-300:]}")
    with open(LEDGER, "a", encoding="utf-8") as f:
        f.write(f"{rid}\t{time.strftime('%Y-%m-%dT%H:%M:%S')}\t{rh}\t{arm}\t{scen}\t{role}\tturns={TURNS}\tstop={stop or 0}\n")
    print(f"run {rid}: {arm} {scen} s1 ({role}), used {len(done) + 1} of {BUDGET}", flush=True)
    P = f"fg{rid}"
    ssh(f"powershell -NoProfile -ExecutionPolicy Bypass -File {R}\\cm_launch.ps1 -Jobs 1 -Tag {P} -Arms {arm} -Prefix {P} -Turns {TURNS} -Pairs {scen}:1")
    t0 = time.time()
    time.sleep(10)
    while True:
        st = ps("(Get-ScheduledTask oxce_cmrun).State").strip()
        if st == "Ready":
            break
        if time.time() - t0 > 3400:
            raise SystemExit("still running after 3400 s")
        time.sleep(15)
    print(ssh(f"C:\\OXCE_AIWorker\\python\\python.exe -I {R}\\pack_logs.py {R} {P} {R}\\res_{P}.zip").strip()[:160], flush=True)
    RES.mkdir(exist_ok=True)
    scp(f"{HOST}:C:/OXCE_AIWorker/cmrun/res_{P}.zip", f"{HOST}:C:/OXCE_AIWorker/cmrun/logs/run_{P}.txt", str(RES))
    print((RES / f"run_{P}.txt").read_text(encoding="utf-8", errors="replace")[-300:], flush=True)
    print(json.dumps(resource(rid), ensure_ascii=False), flush=True)


def prov_check(a, ref):
    fa, fla, _ = prov(*source_of(a))
    fr, flr, _ = prov(*source_of(ref))
    same = {k: fa.get(k) == fr.get(k) for k in ("ai_probe", "arena", "data", "scenario", "flags")}
    extra = {k: v for k, v in fla.items() if flr.get(k) != v}
    return {"run": a, "ref": ref, "same": same, "exe": fa.get("exe"), "exe_ref": fr.get("exe"), "flags_beyond_ref": extra, "flags_missing": [k for k in flr if k not in fla]}


def cmd_report():
    out = {"prov": [], "compare": [], "monitor": {}, "resources": []}
    pairs = [("R1", "arch:M3"), ("R4", "arch:L8"), ("R1", "R2"), ("R4", "R5"), ("R2", "R3"), ("R5", "R6")]
    if all(x in {r[0] for r in ledger()} for x in ("P1",)) and (RES / "res_fgP1.zip").exists():
        pairs.append(("P1", "R5"))
    for a, b in pairs:
        if a.startswith("arch") or (RES / f"res_fg{a}.zip").exists():
            if b.startswith("arch") or (RES / f"res_fg{b}.zip").exists():
                out["compare"].append(compare(a, b))
                out["prov"].append(prov_check(a, b))
    for rid in ("P1", "R2", "R3", "R5", "R6"):
        if (RES / f"res_fg{rid}.zip").exists():
            out["monitor"][rid] = sic.check(sic.read_log(*source_of(rid)))
    for rid in ("arch:M3", "arch:L8", *FINAL, "P1"):
        if rid.startswith("arch") or (RES / f"res_fg{rid}.zip").exists():
            out["resources"].append(resource(rid))
    (HERE / "WP1_COMPARE.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8-sig")
    for c in out["compare"]:
        print(c["a"], c["b"], "game", "IDENTICAL" if c["game_identical"] else ("prefix" if c["game_same_prefix"] else "DIFFER"), c["game_lines"], "chain",
              "-" if "chain_identical" not in c else ("IDENTICAL" if c["chain_identical"] else ("prefix" if c["chain_same_prefix"] else "DIFFER")), c["forge_events"],
              "fp", c.get("fingerprints_equal"), "/", c.get("fingerprints_compared"), "dumps", c.get("dumps_compared"), "dumpdiff", bool(c.get("dump_first_difference")),
              "| relative", "-" if "relative_identical" not in c else ("IDENTICAL" if c["relative_identical"] else ("prefix" if c["relative_same_prefix"] else "DIFFER")),
              "dumps", c.get("relative_dumps_compared"), "dumpdiff", bool(c.get("relative_dump_first_difference")), "shifts", c.get("clock_shifts"),
              "stop", c.get("stop_event"), c.get("game_before_stop"), c.get("game_before_stop_identical"))
    for p in out["prov"]:
        print(p)
    for k, v in out["monitor"].items():
        print(k, "events", v["events"], "violations", v["violations"], "notes", v["notes"], v["first_violations"][:2])
    for r in out["resources"]:
        print(r)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    a = sys.argv[1:]
    stop = int(a[a.index("--stop") + 1]) if "--stop" in a else 0
    if a[0] == "fingerprint":
        cmd_fingerprint()
    elif a[0] == "up":
        cmd_up(stop)
    elif a[0] == "freeze":
        cmd_freeze()
    elif a[0] == "run":
        cmd_run(a[1], stop)
    elif a[0] == "compare":
        print(json.dumps(compare(a[1], a[2]), ensure_ascii=False, indent=1))
    elif a[0] == "report":
        cmd_report()


if __name__ == "__main__":
    main()
