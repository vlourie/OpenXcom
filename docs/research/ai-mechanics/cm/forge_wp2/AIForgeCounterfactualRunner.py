"""AI FORGE WP2: the counterfactual arena. INITIAL STATE + CONFIG + RNG -> REPLAY PREFIX -> DECISION N -> BRANCH A/B.
Every run starts its battle from the start in its own process: nothing is carried from one branch to another, no save in the middle of a turn.

  up                     exe FW, env, the arms and the expected chain value to rabota, hashes compared
  freeze                 the build is frozen -> FROZEN.txt; every run refuses any other exe
  run <id>               one run of the plan (A1 A2 W1 S1 B1 B2 C1 P1); the budget (8) is kept in ledger.tsv and checked first
  replay                 the same as run P1: replay to decision N and stop
  aa <a> <b>             control A/A: two runs must be the same to the last event; the first difference exactly
  ab <a> <b>             branch compare: the same state up to decision N, what each did there, the first difference, real consequences
  seedless <a> <b>       two runs under different starts of the auxiliary generator: what depends on it
  report                 all of them -> WP2_COMPARE.json

Normalised, and only these: NORMALISED below (real-time reports of the engine's lines). The virtual clock's origin is outside the chain: the monitor counts
C from its first reading and writes the origin to [FORGETIME]. Game time, RNG, time units and the state are never normalised."""
import gzip
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import zipfile
from collections import Counter
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
EXE = HERE / "b-w" / "bin" / X
TURNS = 60
SCEN = "L8"
SEEDLESS = 20261106
SEEDLESS_OTHER = 20261107
# the branch point, from pick_branch.py on the WP1 log R5, before any new run; WP2_PLAN.md says the same
N = 49
UNIT = 1000006
TO = "12.17.0"
WEAPON = "STR_PIR_PLASMA_RIFLE"
TYPE_D0 = 7  # BA_AUTOSHOT, what D0 did there in R5
TYPE_ALT = 8  # BA_SNAPSHOT, the first other shot of that weapon at that target in the engine's candidate list
TARGET_R5 = 324
PLAN = {
    "A1": ("WA", "A: D0, the diagnostic replay: what D0 proposes at N, the dump there"),
    "A2": ("WA", "A: the same again: control A/A"),
    "W1": ("WO", "OFF: no arena variable at all, against the archived D0"),
    "S1": ("WS", "A under another start of the auxiliary generator"),
    "B1": ("WB", "B: the legal alternative at N in place of think()"),
    "B2": ("WB", "B again: control B/B"),
    "C1": ("WC", "C: D0's own action at N in place of think(): what skipping think() does by itself"),
    "P1": ("WP", "replay to decision N and stop: the cost of the prefix"),
}
ARCHIVE_D0 = S / "sfc" / "res" / "res_sfF.zip"
ARCHIVE_R5 = S / "forge" / "res" / "res_fgR5.zip"
# The one field taken out of the engine's lines: [AIRESULT] ms=, the battle's length on the wall clock (AiProbe.cpp, SDL_GetTicks - startTicks, written to the log, read by nothing).
# Nothing else is taken out, so anything else that moves with real time shows as a difference. vms=, the game's clock, stays in.
NORMALISED = {"[AIRESULT] ms=": re.compile(r" ms=\d+")}
# Added after B1/B2, outside WP2_PLAN.md (see WP2_PLAN_ADDENDUM.md): [AIREUSE] fallback_us=, the wall-clock time of the record's own ask (AiProbe.cpp:1359-1363, written there, read only by the log line at :1300).
# It stays 0 until the fallback runs, which D0 never did on this scene and B does at N. fallback= (how many) stays in. aa() gives the verdict under the plan's list beside the verdict under this one.
NORMALISED_AFTER_PLAN = {"[AIREUSE] fallback_us=": re.compile(r" fallback_us=\d+")}
# outside every comparison: [FORGETIME] (real time and the virtual clock's origin) and the lines without [AI / [FORGE (the engine's start-up, paths, HD stall reports)
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
    return f"fw{rid}_{PLAN[rid][0]}_{SCEN}_s1"


def source_of(name):
    if name == "arch:D0":
        return ARCHIVE_D0, "sfF_D_L8_s1"
    if name == "arch:R5":
        return ARCHIVE_R5, "fgR5_FGS_L8_s1"
    if name.startswith("wp1:"):
        rid, arm, scen = name[4:].split("_")
        return S / "forge" / "res" / f"res_fg{rid}.zip", f"fg{rid}_{arm}_{scen}_s1"
    return RES / f"res_fw{name}.zip", label_of(name)


def normal_plan(s):
    """The plan's list as it was written before the first run."""
    return NORMALISED["[AIRESULT] ms="].sub("", s) if s.startswith("[AIRESULT]") else s


def normal(s):
    return NORMALISED_AFTER_PLAN["[AIREUSE] fallback_us="].sub("", s) if s.startswith("[AIREUSE]") else normal_plan(s)


def normalised_fields(lines):
    """How many values were taken out: the list is checked, not assumed."""
    return {"[AIRESULT] ms=": sum(len(NORMALISED["[AIRESULT] ms="].findall(s)) for s in lines if s.startswith("[AIRESULT]")),
            "[AIREUSE] fallback_us=": sum(len(NORMALISED_AFTER_PLAN["[AIREUSE] fallback_us="].findall(s)) for s in lines if s.startswith("[AIREUSE]"))}


class Run:
    """One log, by kind of line."""

    def __init__(self, name):
        self.name = name
        self.lines = sic.read_log(*source_of(name))
        self.game = []
        self.game_plan = []
        self.forge = []
        self.dumps = {}
        self.time = []
        self.branch = []
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
            elif s.startswith("[AI"):
                self.game.append(normal(s))
                self.game_plan.append(normal_plan(s))

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


def first_difference(xs, ys):
    for i, (x, y) in enumerate(zip(xs, ys)):
        if x != y:
            return {"index": i, "a": x[:700], "b": y[:700]}
    if len(xs) != len(ys):
        return {"index": min(len(xs), len(ys)), "a": (xs[min(len(xs), len(ys))][:700] if len(xs) > len(ys) else "<end>"), "b": (ys[min(len(xs), len(ys))][:700] if len(ys) > len(xs) else "<end>")}
    return None


def fp_sections(text):
    d = dict(sic.KV.findall(text))
    return {k: d.get(k) for k in SECTIONS}


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
    for what, pick in (("actions", lambda d: d.get("ev") == "act"), ("tu_changes", lambda d: d.get("ev") == "tu"), ("fingerprints", lambda d: d.get("ev") == "fp"), ("casualties", lambda d: d.get("ev") == "casualty")):
        xa = [t for _, _, t, d in ea if pick(d)]
        xb = [t for _, _, t, d in eb if pick(d)]
        out[what] = {"counts": [len(xa), len(xb)], "identical": xa == xb}
    out["rng_identical"] = [d.get("rng") for *_, d in ea] == [d.get("rng") for *_, d in eb]
    out["last_section_values"] = fp_sections(next((t for _, _, t, d in reversed(ea) if d.get("ev") == "fp"), ""))
    state_same = out["chain_identical"] and out["dump_first_difference"] is None and not out["dumps_only_one"]
    out["verdict"] = "IDENTICAL" if state_same and out["game_identical"] else "DIFFERENT"
    out["verdict_plan_list"] = "IDENTICAL" if state_same and a.game_plan == b.game_plan else "DIFFERENT"
    out["plan_list_first_difference"] = first_difference(a.game_plan, b.game_plan)
    out["normalised"] = normalised_fields(a.lines)
    return out


def decision_at(run):
    """The events of decision N: the decide line and its fingerprint."""
    ev = run.events()
    for i, (n, h, t, d) in enumerate(ev):
        if d.get("ev") == "decide" and d.get("d") == str(N):
            for j in range(i + 1, len(ev)):
                if ev[j][3].get("ev") == "fp":
                    return i, j, ev
    raise SystemExit(f"{run.name}: no decision {N}")


def what_happened(run, start):
    """What the run did from its event start on, by the engine's own lines: the first few, then the total."""
    ev = run.events()[start:]
    return [t.strip()[:230] for _, _, t, d in ev if d.get("ev") in ("branch", "act", "tu", "casualty", "react", "VIOLATION")][:14]


def after_dump(run):
    for n, rows in run.dumps.items():
        if rows and "why=after_branch" in rows[0]:
            return n, rows
    return None, []


def one_dump(rows):
    """Dumps are kept by the event number, and a frozen chain (mode stop) gives the next dump the same number: only the first of them."""
    return rows[:next((i for i, r in enumerate(rows) if i and r.startswith("why=")), len(rows))]


def first_floor(ra, rb):
    """The floor hash is cumulative (the monitor copies the running map hash): every floor after the first differing one differs too, so only the first says anything."""
    return next((x.split(" ")[0] for x, y in zip([r for r in ra if r.startswith("floor=")], [r for r in rb if r.startswith("floor=")]) if x != y), None)


def unit_rows(rows):
    out = {}
    for r in rows:
        m = re.match(r"u=(\d+) ", r)
        if m:
            out[m.group(1)] = r
    return out


def row_changes(a, b):
    """Field by field, the units that differ; hashes kept apart as the last resort."""
    ua, ub = unit_rows(a), unit_rows(b)
    changes = []
    for u in sorted(set(ua) | set(ub), key=int):
        if ua.get(u) != ub.get(u):
            da, db = dict(sic.KV.findall(ua.get(u, ""))), dict(sic.KV.findall(ub.get(u, "")))
            changes.append({"unit": u, "type": da.get("type") or db.get("type"), "fields": {k: [da.get(k), db.get(k)] for k in sorted(set(da) | set(db)) if da.get(k) != db.get(k)}})
    return changes


def casualties(run):
    return [{"n": n, "turn": d.get("t"), "side": d.get("s"), "unit": d.get("unit"), "dead": d.get("dead"), "fac": d.get("fac")} for n, _, _, d in run.events() if d.get("ev") == "casualty"]


def ab(na, nb):
    a, b = Run(na), Run(nb)
    ia, ja, ea = decision_at(a)
    ib, jb, eb = decision_at(b)
    out = {"a": na, "b": nb}
    prefix_a, prefix_b = a.forge[:ja + 1], b.forge[:jb + 1]
    out["prefix_events"] = [len(prefix_a), len(prefix_b)]
    out["prefix_chain_identical"] = prefix_a == prefix_b
    out["prefix_first_difference"] = first_difference(prefix_a, prefix_b)
    # up to the fingerprint of N; a line the engine wrote after it belongs to what follows
    ga, gb = a.game_before(ea[ja][0]), b.game_before(eb[jb][0])
    out["prefix_game_lines"] = [len(ga), len(gb)]
    out["prefix_game_identical"] = ga == gb
    out["fingerprint_at_N"] = {"a": fp_sections(ea[ja][2]), "b": fp_sections(eb[jb][2]), "chain": [ea[ja][1], eb[jb][1]], "rng": [ea[ja][3].get("rng"), eb[jb][3].get("rng")]}
    da = one_dump(next((rows for n, rows in a.dumps.items() if rows and "why=branch" in rows[0]), []))
    db = one_dump(next((rows for n, rows in b.dumps.items() if rows and "why=branch" in rows[0]), []))
    out["dump_at_N_lines"] = [len(da), len(db)]
    out["dump_at_N_identical"] = bool(da) and da == db
    actor = unit_rows(da).get(str(UNIT), "")
    out["actor_at_N"] = actor[:300]
    out["what_a_did"] = what_happened(a, ja + 1)
    out["what_b_did"] = what_happened(b, jb + 1)
    out["first_difference"] = first_difference(a.forge[ja + 1:], b.forge[jb + 1:])
    out["first_difference_event"] = [ea[ja + 1][0] if ja + 1 < len(ea) else None, eb[jb + 1][0] if jb + 1 < len(eb) else None]
    # the first fingerprint where each kind of state differs: state after a different number of random values is compared by what it holds
    fa = [(n, d, t) for n, _, t, d in ea[ja + 1:] if d.get("ev") == "fp"]
    fb = [(n, d, t) for n, _, t, d in eb[jb + 1:] if d.get("ev") == "fp"]
    firsts = {}
    for (na_, xa, ta), (nb_, xb, tb) in zip(fa, fb):
        for k in SECTIONS:
            if k not in firsts and xa.get(k) != xb.get(k):
                firsts[k] = {"section": SECTION_NAME[k], "event_a": na_, "event_b": nb_, "turn": [xa.get("t"), xb.get("t")]}
    out["first_section_difference"] = firsts
    na2, ra = after_dump(a)
    nb2, rb = after_dump(b)
    out["after_decision_dump_events"] = [na2, nb2]
    out["after_decision_units"] = row_changes(ra, rb)[:24]
    out["after_decision_first_floor"] = first_floor(ra, rb)
    ca, cb = casualties(a), casualties(b)
    ra_, rb_ = a.result(), b.result()
    out["end"] = {"a": {"result": {k: ra_.get(k) for k in ("how", "turn", "ms", "vms")}, "casualties": len(ca), "dead": sum(1 for c in ca if c["dead"] == "1"), "decisions": sum(1 for *_, d in ea if d.get("ev") == "decide"),
                        "last_fp": fp_sections(fa[-1][2]) if fa else {}},
                  "b": {"result": {k: rb_.get(k) for k in ("how", "turn", "ms", "vms")}, "casualties": len(cb), "dead": sum(1 for c in cb if c["dead"] == "1"), "decisions": sum(1 for *_, d in eb if d.get("ev") == "decide"),
                        "last_fp": fp_sections(fb[-1][2]) if fb else {}}}
    out["casualties_first_difference"] = first_difference([f"{c['turn']}/{c['side']}/{c['unit']}/{c['dead']}" for c in ca], [f"{c['turn']}/{c['side']}/{c['unit']}/{c['dead']}" for c in cb])
    out["monitor"] = {na: monitor(a), nb: monitor(b)}
    return out


def monitor(run):
    c = sic.check(run.lines)
    return {"events": c["events"], "violations": c["violations"], "first_violations": c["first_violations"][:4], "notes": c["notes"], "tu_kinds": {k: v for k, v in c["counts"].items() if k.startswith("tu")}}


SEEDLESS_FIELDS = re.compile(r" (L|V)=[0-9a-f]+")


def seedless_compare(na, nb):
    """Everything but what the auxiliary generator holds and gave: L and V in the fingerprints, the chain value they enter. The rest must not move."""
    a, b = Run(na), Run(nb)
    ta = [SEEDLESS_FIELDS.sub("", t) for _, _, t, _ in a.events()]
    tb = [SEEDLESS_FIELDS.sub("", t) for _, _, t, _ in b.events()]
    ea, eb = a.events(), b.events()
    fa = [d for *_, d in ea if d.get("ev") == "fp"]
    fb = [d for *_, d in eb if d.get("ev") == "fp"]
    strip = lambda rows: {n: [SEEDLESS_FIELDS.sub("", r) for r in v] for n, v in rows.items()}
    da, db = strip(a.dumps), strip(b.dumps)
    common = sorted(set(da) & set(db))
    return {"a": na, "b": nb, "events": [len(ta), len(tb)], "events_identical_without_L_V": ta == tb, "first_difference": first_difference(ta, tb), "game_identical": a.game == b.game, "game_first_difference": first_difference(a.game, b.game),
            "fingerprints": [len(fa), len(fb)], "L_differs": sum(1 for x, y in zip(fa, fb) if x.get("L") != y.get("L")), "V_differs": sum(1 for x, y in zip(fa, fb) if x.get("V") != y.get("V")),
            "L_first": [fa[0].get("L") if fa else None, fb[0].get("L") if fb else None], "dumps_identical_without_L_V": all(da[n] == db[n] for n in common), "dumps_compared": len(common)}


def game_compare(na, nb):
    """Engine's lines only: a run with the monitor off against any other."""
    a, b = Run(na), Run(nb)
    return {"a": na, "b": nb, "game_lines": [len(a.game), len(b.game)], "identical": a.game == b.game, "first_difference": first_difference(a.game, b.game)}


def costs(rid):
    run = Run(rid)
    log = (RES / f"run_fw{rid}.txt")
    wall = None
    if log.exists():
        m = re.findall(r"(\d+(?:\.\d+)?) ?s\b", log.read_text(encoding="utf-8", errors="replace"))
        wall = m[-1] if m else None
    with zipfile.ZipFile(source_of(rid)[0]) as z:
        size = len(gzip.decompress(z.read(f"out/{label_of(rid)}/openxcom.log.gz")))
    return {"run": rid, "time": run.time, "result": {k: run.result().get(k) for k in ("how", "turn", "ms", "vms")}, "wall_text": wall, "log_bytes": size, "forge_events": len(run.forge), "dump_lines": sum(len(v) for v in run.dumps.values())}


def cmd_up():
    d = ST / "exe" / "FW"
    d.mkdir(parents=True, exist_ok=True)
    h = sha(EXE)
    (d / X).write_bytes(EXE.read_bytes())
    (d / "BUILD_INFO.txt").write_text(f"build_label=cmrun-FW\ngit_commit=07680cadb\nnote=HEAD + al.diff + al3.diff + AI FORGE WP1 monitor + WP2 arena (flags only)\nmonitor_sha256={sha(HERE / 'mon' / 'SchedulerIntegrityMonitor.cpp')}\n", encoding="utf-8")
    env = (ST / "env_D0.txt").read_text(encoding="utf-8").replace("/exe/D0/", "/exe/FW/")
    (ST / "env_FW.txt").write_text(env, encoding="utf-8")
    run = (ST / "run_cm.py").read_text(encoding="utf-8")
    base = f'"OXCE_AI_FORGE=1", "OXCE_AI_FORGE_BRANCH_AT={N}", "OXCE_AI_FORGE_BRANCH_UNIT={UNIT}", "OXCE_AI_FORGE_BRANCH_TO={TO}", "OXCE_AI_FORGE_BRANCH_WEAPON={WEAPON}"'
    chain = '"OXCE_AI_FORGE_BRANCH_CHAIN=" + ((HERE / "forge2_chain.txt").read_text().strip() if (HERE / "forge2_chain.txt").exists() else "")'
    new = f'''        # AI FORGE WP2 (GO Vitali 06.11, at most 8 runs): exe FW; WO - nothing set; WA - D0, observed at decision {N}; WS - the same, the other start of the auxiliary generator;
        # WB - the alternative in place of that think() (offline arena only), WC - D0's own action in its place, WP - replay to that decision and stop
        "WO": ("env_FW.txt", [], COMMON_D0),
        "WA": ("env_FW.txt", [{base}, "OXCE_AI_FORGE_SEEDLESS={SEEDLESS}", "OXCE_AI_FORGE_BRANCH_MODE=observe"], COMMON_D0),
        "WS": ("env_FW.txt", [{base}, "OXCE_AI_FORGE_SEEDLESS={SEEDLESS_OTHER}", "OXCE_AI_FORGE_BRANCH_MODE=observe"], COMMON_D0),
        "WB": ("env_FW.txt", [{base}, "OXCE_AI_FORGE_SEEDLESS={SEEDLESS}", "OXCE_AI_FORGE_BRANCH_MODE=act", "OXCE_AI_FORGE_BRANCH_TYPE={TYPE_ALT}", {chain}], COMMON_D0),
        "WC": ("env_FW.txt", [{base}, "OXCE_AI_FORGE_SEEDLESS={SEEDLESS}", "OXCE_AI_FORGE_BRANCH_MODE=act", "OXCE_AI_FORGE_BRANCH_TYPE={TYPE_D0}", {chain}], COMMON_D0),
        "WP": ("env_FW.txt", [{base}, "OXCE_AI_FORGE_SEEDLESS={SEEDLESS}", "OXCE_AI_FORGE_BRANCH_MODE=stop"], COMMON_D0),
}}
TURNS = 60
'''
    if '"WO":' not in run:
        old = "}\nTURNS = 60\n"
        assert run.count(old) == 1
        run = run.replace(old, new)
        (ST / "run_cm.py").write_text(run, encoding="utf-8")
    ssh(f"if not exist {R}\\exe\\FW mkdir {R}\\exe\\FW")
    scp(str(d / X), str(d / "BUILD_INFO.txt"), f"{HOST}:C:/OXCE_AIWorker/cmrun/exe/FW/")
    scp(str(ST / "env_FW.txt"), str(ST / "run_cm.py"), f"{HOST}:C:/OXCE_AIWorker/cmrun/")
    rh = remote_hash(f"{R}\\exe\\FW\\{X}")
    print("local ", h)
    print("remote", rh, "OK" if rh == h else "DIFFERENT")
    print("run_cm", sha(ST / "run_cm.py") == remote_hash(f"{R}\\run_cm.py"))
    if rh != h:
        raise SystemExit(2)


def cmd_freeze():
    FROZEN.write_text(f"exe_sha256={sha(EXE)}\nfrozen={time.strftime('%Y-%m-%dT%H:%M:%S')}\nmonitor_cpp={sha(HERE / 'mon' / 'SchedulerIntegrityMonitor.cpp')}\nrunner={sha(Path(__file__))}\n", encoding="utf-8")
    print(FROZEN.read_text(encoding="utf-8"))


def ledger():
    if not LEDGER.exists():
        return []
    return [s.split("\t") for s in LEDGER.read_text(encoding="utf-8").splitlines() if s.strip()]


def expected_chain():
    """The chain value decision N's fingerprint must show in any branch: from A1, and A2 must agree."""
    a1, a2 = Run("A1"), Run("A2")
    verdict = aa("A1", "A2")["verdict"]
    if verdict != "IDENTICAL":
        raise SystemExit("A/A differs: no branch")
    return decision_at(a1)[2][decision_at(a1)[1]][1]


def cmd_run(rid):
    if rid not in PLAN:
        raise SystemExit(f"{rid}: not in the plan")
    done = ledger()
    if len(done) >= BUDGET:
        raise SystemExit(f"budget: {len(done)} of {BUDGET} used")
    if any(x[0] == rid for x in done):
        raise SystemExit(f"{rid}: already run")
    arm, role = PLAN[rid]
    rh = remote_hash(f"{R}\\exe\\FW\\{X}")
    frozen = dict(x.split("=", 1) for x in FROZEN.read_text(encoding="utf-8").splitlines() if "=" in x)["exe_sha256"]
    if rh != frozen:
        raise SystemExit(f"{rid}: exe on rabota {rh} is not the frozen one {frozen}")
    if arm in ("WB", "WC"):
        value = expected_chain()
        (ST / "forge2_chain.txt").write_text(value, encoding="utf-8")
        scp(str(ST / "forge2_chain.txt"), f"{HOST}:C:/OXCE_AIWorker/cmrun/")
        print("expected chain at decision", N, value, flush=True)
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
    P = f"fw{rid}"
    t0 = time.time()
    ssh(f"powershell -NoProfile -ExecutionPolicy Bypass -File {R}\\cm_launch.ps1 -Jobs 1 -Tag {P} -Arms {arm} -Prefix {P} -Turns {TURNS} -Pairs {SCEN}:1")
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
    print((RES / f"run_{P}.txt").read_text(encoding="utf-8", errors="replace")[-400:], flush=True)
    print(json.dumps(costs(rid), ensure_ascii=False), flush=True)
    if rid != "W1":  # the monitor is off there
        print(json.dumps(monitor(Run(rid)), ensure_ascii=False), flush=True)


def have(rid):
    return rid.startswith("arch:") or (RES / f"res_fw{rid}.zip").exists()


def cmd_report():
    out = {"plan": {k: list(v) for k, v in PLAN.items()}, "branch_point": {"decision": N, "unit": UNIT, "to": TO, "weapon": WEAPON, "D0_type": TYPE_D0, "alternative_type": TYPE_ALT}, "ledger": ledger()}
    if have("A1") and have("A2"):
        out["AA"] = aa("A1", "A2")
    if have("B1") and have("B2"):
        out["BB"] = aa("B1", "B2")
    out["off"] = [game_compare(a, b) for a, b in (("W1", "arch:D0"), ("W1", "A1"), ("A1", "arch:R5")) if have(a) and have(b)]
    if have("A1") and have("S1"):
        out["seedless"] = seedless_compare("A1", "S1")
    for key, a, b in (("AB", "A1", "B1"), ("AC", "A1", "C1"), ("CB", "C1", "B1")):
        if have(a) and have(b):
            out[key] = ab(a, b)
    if have("P1") and have("A1"):
        a1, p1 = Run("A1"), Run("P1")
        out["replay_to_N"] = {"events": [len(a1.forge), len(p1.forge)], "same_prefix": a1.forge[:len(p1.forge)] == p1.forge, "last": p1.forge[-1][:200] if p1.forge else None,
                              "dump_identical": one_dump(next((r for r in a1.dumps.values() if "why=branch" in r[0]), [])) == one_dump(next((r for r in p1.dumps.values() if "why=branch" in r[0]), []))}
    out["costs"] = [costs(r) for r in PLAN if have(r)]
    out["monitor"] = {r: monitor(Run(r)) for r in PLAN if have(r) and r != "W1"}
    (HERE / "WP2_COMPARE.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8-sig")
    for k in ("AA", "BB"):
        if k in out:
            print(k, out[k]["verdict"], "under the plan's list:", out[k]["verdict_plan_list"], out[k]["forge_events"], out[k]["game_lines"], "dumps", out[k]["dumps_compared"], {x: out[k][x]["identical"] for x in ("actions", "tu_changes", "fingerprints", "casualties")})
    for g in out["off"]:
        print("game", g["a"], g["b"], g["game_lines"], g["identical"], g["first_difference"])
    print("seedless", {k: v for k, v in out.get("seedless", {}).items() if k != "first_difference"})
    for k in ("AB", "AC", "CB"):
        if k in out:
            x = out[k]
            print(k, "prefix", x["prefix_chain_identical"], x["prefix_game_identical"], "dump", x["dump_at_N_identical"], "first", x["first_difference_event"], x["first_difference"]["a"][:160] if x["first_difference"] else None, "|", x["first_difference"]["b"][:160] if x["first_difference"] else None)
    print("replay", out.get("replay_to_N"))
    for c in out["costs"]:
        print(c)
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
    elif a[0] == "replay":
        cmd_run("P1")
    elif a[0] == "aa":
        print(json.dumps(aa(a[1], a[2]), ensure_ascii=False, indent=1))
    elif a[0] == "ab":
        print(json.dumps(ab(a[1], a[2]), ensure_ascii=False, indent=1))
    elif a[0] == "seedless":
        print(json.dumps(seedless_compare(a[1], a[2]), ensure_ascii=False, indent=1))
    elif a[0] == "report":
        cmd_report()


if __name__ == "__main__":
    main()
