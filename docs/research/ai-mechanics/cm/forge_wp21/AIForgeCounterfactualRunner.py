"""AI FORGE WP2.1: isolated action intervention. INITIAL STATE + CONFIG + RNG -> REPLAY -> DECISION N -> full think() -> STATE COMPARED -> mode of the shot -> carried out.
Every run starts its battle from the start in its own process: nothing is carried from one branch to another, no save in the middle of a turn.

  up                     exe FX, env, the arms to rabota, hashes compared
  freeze                 the build is frozen -> FROZEN.txt; every run refuses any other exe
  run <id>               one run of the plan (OFF A1 A2 B1 B2 C1); the budget (6) is kept in ledger.tsv and checked first
  aa <a> <b>             control: two runs must be the same to the last event; the first difference exactly
  iso <a> <b>            the same state up to the point of intervention; what is different in the action; first differences of the chain, RNG and TU; real effects
  report                 all of them -> WP21_COMPARE.json

Normalised, and only these, both argued in WP2: [AIRESULT] ms=, [AIREUSE] fallback_us=. Raw differences are kept beside the verdict. The virtual clock's origin is outside the chain.
The whole battle after the shot is one realisation of the RNG: 'end' is printed as it is and is no measure of the use of the decision."""
import gzip
import hashlib
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
BUDGET = 7  # 6 of the GO, one exception by Vitali for the real OFF after the stray run (WP2_1_PLAN_ADDENDUM.md)
KEY = os.path.expanduser("~/.ssh/oxce_worker")
HOST = "user@100.93.184.94"
R = "C:\\OXCE_AIWorker\\cmrun"
X = "openxcom" ".exe"
EXE = HERE / "b-x" / "bin" / X
TURNS = 60
SCEN = "L8"
SEEDLESS = 20261106
# the scene and the decision of WP2, as GO WP2.1 says: not changed for a better-looking result
N = 49
UNIT = 1000006
TO = "12.17.0"
WEAPON = "STR_PIR_PLASMA_RIFLE"
TYPE_D0 = 7  # BA_AUTOSHOT
TYPE_ALT = 8  # BA_SNAPSHOT
PLAN = {
    "OFF": ("YO", "no arena variable at all, against the archived D0"),
    "A1": ("YA", "A: full think(), the action through the arena unchanged"),
    "A2": ("YA", "A again: control A/A"),
    "B1": ("YB", "B: the same full think(), the mode of the shot changed before it is carried out"),
    "B2": ("YB", "B again: control B/B"),
    "C1": ("YC", "C: passive interception: the state and the action written, nothing changed"),
}
ARCHIVE_D0 = S / "sfc" / "res" / "res_sfF.zip"
ARCHIVE_WP2_A1 = S / "forge2" / "res" / "res_fwA1.zip"
NORMALISED = {"[AIRESULT] ms=": re.compile(r" ms=\d+"), "[AIREUSE] fallback_us=": re.compile(r" fallback_us=\d+")}
SECTIONS = ("S", "U", "A", "I", "O", "M", "N", "B", "J", "R", "C", "L", "V")
SECTION_NAME = {"S": "scheduler", "U": "units", "A": "AI modules", "I": "items", "O": "inventory order", "M": "map", "N": "nodes", "B": "bot", "J": "item ids",
                "R": "RNG", "C": "virtual clock from its first reading", "L": "auxiliary generator", "V": "what the auxiliary generator gave units and tiles"}


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
    return f"fx{rid}_{PLAN[rid][0]}_{SCEN}_s1"


def source_of(name):
    if name == "arch:D0":
        return ARCHIVE_D0, "sfF_D_L8_s1"
    if name == "arch:WP2A1":
        return ARCHIVE_WP2_A1, "fwA1_WA_L8_s1"
    return RES / f"res_fx{name}.zip", label_of(name)


def normal(s):
    for head, pattern in NORMALISED.items():
        if s.startswith(head.split(" ")[0]):
            return pattern.sub("", s)
    return s


def normalised_fields(lines):
    """How many values were taken out, and how many of them were not zero: the list is checked, not assumed."""
    out = {}
    for head, pattern in NORMALISED.items():
        values = [v for s in lines if s.startswith(head.split(" ")[0]) for v in pattern.findall(s)]
        out[head] = {"values": len(values), "not_zero": sum(1 for v in values if not v.endswith("=0"))}
    return out


class Run:
    """One log, by kind of line."""

    def __init__(self, name):
        self.name = name
        self.lines = sic.read_log(*source_of(name))
        self.game = []
        self.raw = []
        self.forge = []
        self.dumps = {}
        self.time = []
        self.branch = []
        self.legal = []
        for s in self.lines:
            if s.startswith("[FORGE] "):
                self.forge.append(s)
            elif s.startswith("[FORGEDUMP] "):
                m = re.match(r"\[FORGEDUMP\] at=(\d+) (.*)", s)
                self.dumps.setdefault(int(m.group(1)), []).append(m.group(2))
            elif s.startswith("[FORGETIME] "):
                self.time.append(s)
            elif s.startswith("[FORGEBRANCH] "):
                self.branch.append(s)
            elif s.startswith("[FORGELEGAL] "):
                self.legal.append(s)
            elif s.startswith("[AI"):
                self.game.append(normal(s))
                self.raw.append(s)

    def events(self):
        out = []
        for s in self.forge:
            m = sic.LINE.match(s)
            out.append((int(m.group(1)), m.group(2), m.group(3), dict(sic.KV.findall(m.group(3)))))
        return out

    def game_before(self, n):
        head = f"[FORGE] n={n} "
        out = []
        for s in self.lines:
            if s.startswith(head):
                break
            if s.startswith("[AI"):
                out.append(normal(s))
        return out

    def result(self):
        s = next((x for x in self.lines if x.startswith("[AIRESULT]")), "")
        return dict(sic.KV.findall(s))

    def phase(self, name):
        return next((s for s in self.branch if f" phase={name} " in s), "")


def first_difference(xs, ys):
    for i, (x, y) in enumerate(zip(xs, ys)):
        if x != y:
            return {"index": i, "a": x[:900], "b": y[:900]}
    if len(xs) != len(ys):
        k = min(len(xs), len(ys))
        return {"index": k, "a": (xs[k][:900] if len(xs) > k else "<end>"), "b": (ys[k][:900] if len(ys) > k else "<end>")}
    return None


def fp_sections(text):
    d = dict(sic.KV.findall(text))
    return {k: d.get(k) for k in SECTIONS}


def raw_differences(a, b):
    """Which engine lines differ before normalising, kept beside the verdict."""
    out = [(x, y) for x, y in zip(a.raw, b.raw) if x != y]
    return {"lines": len(out) + abs(len(a.raw) - len(b.raw)), "first": [[x[:300], y[:300]] for x, y in out[:6]]}


def aa(na, nb):
    a, b = Run(na), Run(nb)
    ea, eb = a.events(), b.events()
    out = {"a": na, "b": nb, "forge_events": [len(ea), len(eb)], "game_lines": [len(a.game), len(b.game)]}
    out["chain_identical"] = a.forge == b.forge
    out["chain_first_difference"] = first_difference(a.forge, b.forge)
    out["game_identical"] = a.game == b.game
    out["game_first_difference"] = first_difference(a.game, b.game)
    common = sorted(set(a.dumps) & set(b.dumps))
    out["dumps_compared"] = len(common)
    out["dumps_only_one"] = sorted(set(a.dumps) ^ set(b.dumps))
    out["dump_first_difference"] = next(({"at": n, **first_difference(a.dumps[n], b.dumps[n])} for n in common if a.dumps[n] != b.dumps[n]), None)
    out["branch_lines_equal"] = a.branch == b.branch
    out["legal_lines_equal"] = a.legal == b.legal
    for what, pick in (("actions", lambda d: d.get("ev") == "act"), ("tu_changes", lambda d: d.get("ev") == "tu"), ("fingerprints", lambda d: d.get("ev") == "fp"), ("casualties", lambda d: d.get("ev") == "casualty")):
        xa = [t for _, _, t, d in ea if pick(d)]
        xb = [t for _, _, t, d in eb if pick(d)]
        out[what] = {"counts": [len(xa), len(xb)], "identical": xa == xb}
    out["rng_identical"] = [d.get("rng") for *_, d in ea] == [d.get("rng") for *_, d in eb]
    out["last_section_values"] = fp_sections(next((t for _, _, t, d in reversed(ea) if d.get("ev") == "fp"), ""))
    same = out["chain_identical"] and out["dump_first_difference"] is None and not out["dumps_only_one"] and out["branch_lines_equal"] and out["legal_lines_equal"]
    out["verdict"] = "IDENTICAL" if same and out["game_identical"] else "DIFFERENT"
    out["raw_differences"] = raw_differences(a, b)
    out["normalised"] = normalised_fields(a.lines)
    return out


def act_at(run):
    """Decision N and the first action written after it: everything before that line was before the intervention's effects could show."""
    ev = run.events()
    for i, (n, h, t, d) in enumerate(ev):
        if d.get("ev") == "decide" and d.get("d") == str(N):
            for j in range(i + 1, len(ev)):
                if ev[j][3].get("ev") == "act":
                    return i, j, ev
    raise SystemExit(f"{run.name}: no action after decision {N}")


def one_dump(rows):
    """Dumps are kept by the event number, and two can share one: only the first of them."""
    return rows[:next((i for i, r in enumerate(rows) if i and r.startswith("why=")), len(rows))]


def dump_of(run, why):
    return one_dump(next((rows[i:] for rows in run.dumps.values() for i, r in enumerate(rows) if r.startswith(f"why={why}")), []))


def first_floor(ra, rb):
    """The floor hash is cumulative: only the first differing floor says anything."""
    return next((x.split(" ")[0] for x, y in zip([r for r in ra if r.startswith("floor=")], [r for r in rb if r.startswith("floor=")]) if x != y), None)


def unit_rows(rows):
    out = {}
    for r in rows:
        m = re.match(r"u=(\d+) ", r)
        if m:
            out[m.group(1)] = r
    return out


def row_changes(a, b):
    """Field by field, the units that differ."""
    ua, ub = unit_rows(a), unit_rows(b)
    changes = []
    for u in sorted(set(ua) | set(ub), key=int):
        if ua.get(u) != ub.get(u):
            da, db = dict(sic.KV.findall(ua.get(u, ""))), dict(sic.KV.findall(ub.get(u, "")))
            changes.append({"unit": u, "type": da.get("type") or db.get("type"), "fields": {k: [da.get(k), db.get(k)] for k in sorted(set(da) | set(db)) if da.get(k) != db.get(k)}})
    return changes


def tiles(rows):
    return [r for r in rows if r.startswith("tile=")]


def casualties(run):
    return [{"n": n, "turn": d.get("t"), "side": d.get("s"), "unit": d.get("unit"), "dead": d.get("dead"), "fac": d.get("fac")} for n, _, _, d in run.events() if d.get("ev") == "casualty"]


def effects(run):
    """What this branch's action did by the next decision: the events on the way, and the state against the state at the intervention."""
    i, j, ev = act_at(run)
    nxt = next((k for k in range(j + 1, len(ev)) if ev[k][3].get("ev") == "decide"), len(ev))
    before, after = dump_of(run, "intervene"), dump_of(run, "after_branch")
    return {"events_to_next_decision": nxt - j, "kinds": sorted({ev[k][3].get("ev") for k in range(j, nxt)}), "lines": [ev[k][2].strip()[:230] for k in range(j, nxt) if ev[k][3].get("ev") in ("act", "tu", "casualty", "react", "VIOLATION")][:14],
            "units": row_changes(before, after)[:24], "first_floor": first_floor(before, after), "tiles": tiles(after)[:40], "tiles_changed": next((r for r in after if r.startswith("tiles_changed=")), None)}


def iso(na, nb):
    a, b = Run(na), Run(nb)
    ia, ja, ea = act_at(a)
    ib, jb, eb = act_at(b)
    out = {"a": na, "b": nb, "prefix_events": [ja, jb]}
    # the chain and the engine's lines up to the action line of decision N: both full think() included
    out["prefix_chain_identical"] = a.forge[:ja] == b.forge[:jb]
    out["prefix_first_difference"] = first_difference(a.forge[:ja], b.forge[:jb])
    ga, gb = a.game_before(ea[ja][0]), b.game_before(eb[jb][0])
    out["prefix_game_lines"] = [len(ga), len(gb)]
    out["prefix_game_identical"] = ga == gb
    fp = next(k for k in range(ia, ja) if ea[k][3].get("ev") == "fp")
    out["fingerprint_at_decide"] = {"sections": fp_sections(ea[fp][2]), "chain": ea[fp][1], "rng": ea[fp][3].get("rng")}
    # the state at the point of intervention: the monitor's own hash, the action, the whole dump
    pa, pb = dict(sic.KV.findall(a.phase("pre"))), dict(sic.KV.findall(b.phase("pre")))
    out["pre"] = {k: [pa.get(k), pb.get(k)] for k in ("chain", "state", "rng", "actor", "type", "to", "weapon", "time", "number", "kneel")}
    out["pre_all_same"] = all(pa.get(k) == pb.get(k) for k in pa if k not in ("mode",)) and set(pa) == set(pb) and bool(pa)
    da, db = dump_of(a, "intervene"), dump_of(b, "intervene")
    out["dump_lines"] = [len(da), len(db)]
    out["dump_identical"] = bool(da) and da == db
    actor = unit_rows(da).get(str(UNIT), "")
    out["actor_at_intervention"] = dict(sic.KV.findall(actor))
    out["sections_at_intervention"] = fp_sections(da[0]) if da else {}
    # the first line of the chain that differs: it has to be the action itself, with only its type different
    out["chain_first_difference"] = first_difference(a.forge, b.forge)
    out["chain_first_difference_is_the_action"] = out["chain_first_difference"] is not None and out["chain_first_difference"]["index"] == ja == jb
    xa, xb = ea[ja][3], eb[jb][3]
    out["act_lines"] = [ea[ja][2].strip(), eb[jb][2].strip()]
    out["act_fields_differ"] = {k: [xa.get(k), xb.get(k)] for k in sorted(set(xa) | set(xb)) if xa.get(k) != xb.get(k)}
    out["post"] = b.phase("post")
    # the first differences after it
    ka = [e for e in ea]
    kb = [e for e in eb]
    first_rng = next((k for k, (x, y) in enumerate(zip(ka, kb)) if x[3].get("rng") != y[3].get("rng")), None)
    out["first_rng_difference"] = None if first_rng is None else {"event_index": first_rng, "events_after_act": first_rng - ja, "a": ka[first_rng][2].strip()[:300], "b": kb[first_rng][2].strip()[:300], "rng": [ka[first_rng][3].get("rng"), kb[first_rng][3].get("rng")]}
    tua = [e for e in ea if e[3].get("ev") == "tu"]
    tub = [e for e in eb if e[3].get("ev") == "tu"]
    first_tu = next((k for k, (x, y) in enumerate(zip(tua, tub)) if x[2] != y[2]), None)
    out["first_tu_difference"] = None if first_tu is None else {"a": tua[first_tu][2].strip()[:300], "b": tub[first_tu][2].strip()[:300]}
    fa = [(n, d) for n, _, _, d in ea[ja:] if d.get("ev") == "fp"]
    fb = [(n, d) for n, _, _, d in eb[jb:] if d.get("ev") == "fp"]
    firsts = {}
    for (na_, x), (nb_, y) in zip(fa, fb):
        for k in SECTIONS:
            if k not in firsts and x.get(k) != y.get(k):
                firsts[k] = {"section": SECTION_NAME[k], "event_a": na_, "event_b": nb_, "turn": [x.get("t"), y.get("t")]}
    out["first_section_difference"] = firsts
    out["effects"] = {na: effects(a), nb: effects(b)}
    ra, rb = dump_of(a, "after_branch"), dump_of(b, "after_branch")
    out["next_decision_units"] = row_changes(ra, rb)[:24]
    out["next_decision_first_floor"] = first_floor(ra, rb)
    ca, cb = casualties(a), casualties(b)
    out["end_raw_not_a_measure_of_use"] = {x.name: {"result": {k: x.result().get(k) for k in ("how", "turn", "vms")}, "casualties": len(c), "dead": sum(1 for u in c if u["dead"] == "1"), "decisions": sum(1 for *_, d in x.events() if d.get("ev") == "decide")} for x, c in ((a, ca), (b, cb))}
    out["monitor"] = {na: monitor(a), nb: monitor(b)}
    return out


def monitor(run):
    c = sic.check(run.lines)
    return {"events": c["events"], "violations": c["violations"], "first_violations": c["first_violations"][:4], "notes": c["notes"], "tu_kinds": {k: v for k, v in c["counts"].items() if k.startswith("tu")}}


def game_compare(na, nb):
    """Engine's lines only: a run with the monitor off against any other."""
    a, b = Run(na), Run(nb)
    return {"a": na, "b": nb, "game_lines": [len(a.game), len(b.game)], "identical": a.game == b.game, "first_difference": first_difference(a.game, b.game), "raw_differences": raw_differences(a, b)}


def chain_compare(na, nb):
    """The chain and its RNG values, event by event: lines of the intervention stay out of the chain, so a run that changed nothing keeps it."""
    a, b = Run(na), Run(nb)
    return {"a": na, "b": nb, "events": [len(a.forge), len(b.forge)], "identical": a.forge == b.forge, "first_difference": first_difference(a.forge, b.forge)}


def costs(rid):
    run = Run(rid)
    with zipfile.ZipFile(source_of(rid)[0]) as z:
        size = len(gzip.decompress(z.read(f"out/{label_of(rid)}/openxcom.log.gz")))
    return {"run": rid, "time": run.time, "result": {k: run.result().get(k) for k in ("how", "turn", "ms", "vms")}, "log_bytes": size, "forge_events": len(run.forge), "dump_lines": sum(len(v) for v in run.dumps.values())}


def cmd_up():
    d = ST / "exe" / "FX"
    d.mkdir(parents=True, exist_ok=True)
    h = sha(EXE)
    (d / X).write_bytes(EXE.read_bytes())
    (d / "BUILD_INFO.txt").write_text(f"build_label=cmrun-FX\ngit_commit=07680cadb\nnote=HEAD + al.diff + al3.diff + AI FORGE WP1 monitor + WP2.1 arena (flags only)\nmonitor_sha256={sha(HERE / 'mon' / 'SchedulerIntegrityMonitor.cpp')}\n", encoding="utf-8")
    env = (ST / "env_D0.txt").read_text(encoding="utf-8").replace("/exe/D0/", "/exe/FX/")
    (ST / "env_FX.txt").write_text(env, encoding="utf-8")
    run = (ST / "run_cm.py").read_text(encoding="utf-8")
    base = f'"OXCE_AI_FORGE=1", "OXCE_AI_FORGE_SEEDLESS={SEEDLESS}", "OXCE_AI_FORGE_BRANCH_AT={N}", "OXCE_AI_FORGE_BRANCH_UNIT={UNIT}", "OXCE_AI_FORGE_BRANCH_TO={TO}", "OXCE_AI_FORGE_BRANCH_WEAPON={WEAPON}", "OXCE_AI_FORGE_BRANCH_FROM={TYPE_D0}"'
    chain ='"OXCE_AI_FORGE_BRANCH_CHAIN=" + ((HERE / "forge21_chain.txt").read_text().strip() if (HERE / "forge21_chain.txt").exists() else ""), "OXCE_AI_FORGE_BRANCH_STATE=" + ((HERE / "forge21_state.txt").read_text().strip() if (HERE / "forge21_state.txt").exists() else "")'
    new = f'''        # AI FORGE WP2.1 (GO Vitali 06.11, at most 6 runs): exe FX, full think() in every arm; YO - nothing set; YA - the action through the arena unchanged;
        # YB - the mode of the shot changed before it is carried out (offline arena only), the state checked first; YC - passive interception
        "YO": ("env_FX.txt", [], COMMON_D0),
        "YA": ("env_FX.txt", [{base}, "OXCE_AI_FORGE_BRANCH_MODE=act", "OXCE_AI_FORGE_BRANCH_TYPE={TYPE_D0}"], COMMON_D0),
        "YB": ("env_FX.txt", [{base}, "OXCE_AI_FORGE_BRANCH_MODE=act", "OXCE_AI_FORGE_BRANCH_TYPE={TYPE_ALT}", {chain}], COMMON_D0),
        "YC": ("env_FX.txt", [{base}, "OXCE_AI_FORGE_BRANCH_MODE=observe"], COMMON_D0),
}}
TURNS = 60
'''
    # R-773: an arm name already taken would silently keep the old arm and its exe
    if '"YO": ("env_FX.txt"' not in run:
        assert not any(f'"{arm}":' in run for arm in ("YO", "YA", "YB", "YC")), "arm name taken"
        old = "}\nTURNS = 60\n"
        assert run.count(old) == 1
        run = run.replace(old, new)
        (ST / "run_cm.py").write_text(run, encoding="utf-8")
    ssh(f"if not exist {R}\\exe\\FX mkdir {R}\\exe\\FX")
    scp(str(d / X), str(d / "BUILD_INFO.txt"), f"{HOST}:C:/OXCE_AIWorker/cmrun/exe/FX/")
    scp(str(ST / "env_FX.txt"), str(ST / "run_cm.py"), f"{HOST}:C:/OXCE_AIWorker/cmrun/")
    rh = remote_hash(f"{R}\\exe\\FX\\{X}")
    print("local ", h)
    print("remote", rh, "OK" if rh == h else "DIFFERENT")
    print("run_cm", sha(ST / "run_cm.py") == remote_hash(f"{R}\\run_cm.py"))
    if rh != h:
        raise SystemExit(2)


def cmd_freeze():
    FROZEN.write_text(f"exe_sha256={sha(EXE)}\nfrozen={time.strftime('%Y-%m-%dT%H:%M:%S')}\nmonitor_cpp={sha(HERE / 'mon' / 'SchedulerIntegrityMonitor.cpp')}\nlegal_h={sha(HERE / 'ForgeLegal.h')}\nrunner={sha(Path(__file__))}\n", encoding="utf-8")
    print(FROZEN.read_text(encoding="utf-8"))


def ledger():
    if not LEDGER.exists():
        return []
    return [s.split("\t") for s in LEDGER.read_text(encoding="utf-8").splitlines() if s.strip()]


def gate(rid):
    """The next run only if the last controls hold: nothing left to spend on a stand that has already failed."""
    if rid in ("B1", "B2", "C1") and aa("A1", "A2")["verdict"] != "IDENTICAL":
        raise SystemExit("A/A differs: STOP")
    if rid == "B1":
        pre = dict(sic.KV.findall(Run("A1").phase("pre")))
        for name, value in (("forge21_chain.txt", pre["chain"]), ("forge21_state.txt", pre["state"])):
            (ST / name).write_text(value, encoding="utf-8")
            scp(str(ST / name), f"{HOST}:C:/OXCE_AIWorker/cmrun/")
        print("expected at the intervention", pre["chain"], pre["state"], flush=True)
    if rid == "B2" and sic.check(Run("B1").lines)["violations"]:
        raise SystemExit("B1 has violations: STOP")


def cmd_run(rid):
    if rid not in PLAN:
        raise SystemExit(f"{rid}: not in the plan")
    done = ledger()
    if len(done) >= BUDGET:
        raise SystemExit(f"budget: {len(done)} of {BUDGET} used")
    if any(x[0] == rid for x in done):
        raise SystemExit(f"{rid}: already run")
    arm, role = PLAN[rid]
    # R-773: the arm itself must point at the frozen exe, not only the exe's folder
    if f'"{arm}": ("env_FX.txt"' not in (ST / "run_cm.py").read_text(encoding="utf-8") or sha(ST / "run_cm.py") != remote_hash(f"{R}\\run_cm.py"):
        raise SystemExit(f"{rid}: arm {arm} does not run the frozen exe, or run_cm differs on rabota")
    rh = remote_hash(f"{R}\\exe\\FX\\{X}")
    frozen = dict(x.split("=", 1) for x in FROZEN.read_text(encoding="utf-8").splitlines() if "=" in x)["exe_sha256"]
    if rh != frozen:
        raise SystemExit(f"{rid}: exe on rabota {rh} is not the frozen one {frozen}")
    gate(rid)
    st = ps("(Get-ScheduledTask oxce_cmrun).State").strip()
    if st == "Running":
        raise SystemExit("the task is running")
    # no battle starts here: an unknown scenario stops run_cm after the arm has been accepted
    dry = subprocess.run(["ssh", "-o", "ConnectTimeout=15", "-i", KEY, HOST, f"cd /d {R} && C:\\OXCE_AIWorker\\python\\python.exe -u run_cm.py --arms {arm} --pairs ZZ:1 --prefix dry"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
    if "unknown scenario" not in dry:
        raise SystemExit(f"arm {arm} is not accepted on rabota: {dry[-300:]}")
    with open(LEDGER, "a", encoding="utf-8") as f:
        f.write(f"{rid}\t{time.strftime('%Y-%m-%dT%H:%M:%S')}\t{rh}\t{arm}\t{SCEN}\t{role}\tturns={TURNS}\n")
    print(f"run {rid}: {arm} {SCEN} s1 ({role}), used {len(done) + 1} of {BUDGET}", flush=True)
    P = f"fx{rid}"
    t0 = time.time()
    ssh(f"powershell -NoProfile -ExecutionPolicy Bypass -File {R}\\cm_launch.ps1 -Jobs 1 -Tag {P} -Arms {arm} -Prefix {P} -Turns {TURNS} -Pairs {SCEN}:1")
    if rid == "OFF":
        # the file that is really running, asked of the system while the battle goes on
        seen = ""
        for _ in range(25):
            seen = ps("Get-Process openxcom -ErrorAction SilentlyContinue | ForEach-Object { $_.Path + ' ' + (Get-FileHash $_.Path).Hash }").strip()
            if seen:
                break
            time.sleep(1)
        (HERE / "OFF_process.txt").write_text(seen + "\n", encoding="utf-8")
        print("process", seen, flush=True)
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
    print(json.dumps(costs(rid), ensure_ascii=False), flush=True)
    if rid != "OFF":  # the monitor is off there
        print(json.dumps(monitor(Run(rid)), ensure_ascii=False), flush=True)
        run = Run(rid)
        print(run.phase("pre")[:500], flush=True)
        print(run.phase("post")[:500], flush=True)


def have(rid):
    return rid.startswith("arch:") or (RES / f"res_fx{rid}.zip").exists()


def cmd_report():
    out = {"plan": {k: list(v) for k, v in PLAN.items()}, "branch_point": {"decision": N, "unit": UNIT, "to": TO, "weapon": WEAPON, "D0_type": TYPE_D0, "alternative_type": TYPE_ALT}, "ledger": ledger()}
    if have("A1") and have("A2"):
        out["AA"] = aa("A1", "A2")
    if have("B1") and have("B2"):
        out["BB"] = aa("B1", "B2")
    out["off"] = [game_compare(a, b) for a, b in (("OFF", "arch:D0"), ("OFF", "A1"), ("OFF", "C1"), ("A1", "arch:D0"), ("C1", "arch:D0"), ("A1", "C1")) if have(a) and have(b)]
    out["chains"] = [chain_compare(a, b) for a, b in (("A1", "C1"), ("C1", "arch:WP2A1"), ("A1", "arch:WP2A1")) if have(a) and have(b)]
    for key, a, b in (("AB", "A1", "B1"), ("AC", "A1", "C1")):
        if have(a) and have(b):
            out[key] = iso(a, b)
    if have("B1"):
        out["legal_probes"] = Run("B1").legal
    out["costs"] = [costs(r) for r in PLAN if have(r)]
    out["monitor"] = {r: monitor(Run(r)) for r in PLAN if have(r) and r != "OFF"}
    (HERE / "WP21_COMPARE.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8-sig")
    for k in ("AA", "BB"):
        if k in out:
            print(k, out[k]["verdict"], out[k]["forge_events"], out[k]["game_lines"], "dumps", out[k]["dumps_compared"], {x: out[k][x]["identical"] for x in ("actions", "tu_changes", "fingerprints", "casualties")}, "raw", out[k]["raw_differences"]["lines"], out[k]["normalised"])
    for g in out["off"]:
        print("game", g["a"], g["b"], g["game_lines"], g["identical"], g["first_difference"], "raw", g["raw_differences"]["lines"])
    for g in out["chains"]:
        print("chain", g["a"], g["b"], g["events"], g["identical"], g["first_difference"])
    for k in ("AB", "AC"):
        if k in out:
            x = out[k]
            print(k, "prefix", x["prefix_chain_identical"], x["prefix_game_identical"], "pre", x["pre_all_same"], "dump", x["dump_identical"], x["dump_lines"], "first is the action", x["chain_first_difference_is_the_action"], "act fields", x["act_fields_differ"])
            print("   post", x["post"][:300])
            print("   rng", x["first_rng_difference"])
            print("   tu", x["first_tu_difference"])
    for s in out.get("legal_probes", []):
        print(s)
    for c in out["costs"]:
        print({k: c[k] for k in ("run", "result", "log_bytes", "forge_events", "dump_lines")})
    for r, m in out["monitor"].items():
        print(r, m)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    a = sys.argv[1:]
    if a[0] == "up":
        cmd_up()
    elif a[0] == "freeze":
        cmd_freeze()
    elif a[0] == "run":
        cmd_run(a[1])
    elif a[0] == "aa":
        print(json.dumps(aa(a[1], a[2]), ensure_ascii=False, indent=1))
    elif a[0] == "iso":
        print(json.dumps(iso(a[1], a[2]), ensure_ascii=False, indent=1))
    elif a[0] == "report":
        cmd_report()


if __name__ == "__main__":
    main()
