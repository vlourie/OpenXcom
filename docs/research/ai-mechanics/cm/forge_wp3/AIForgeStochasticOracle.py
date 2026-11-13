"""AI FORGE WP3: Stochastic Combat Oracle V0. How much of what follows one legal alternative is the alternative and how much is the RNG.
INITIAL STATE + CONFIG -> REPLAY -> DECISION 49 -> full think() -> STATE COMPARED -> mode of the shot -> game RNG := seed of the pair -> carried out by the engine.
Every run starts its battle from the start in its own process. The same seed in both branches is the same state at the point of intervention and no more: nothing synchronises them afterwards.

  seeds                  the seeds, from fixed text: not chosen, not looked at beforehand
  up                     exe F3, env, the arms to rabota, hashes compared
  freeze                 exe, monitor, this file and the seeds are frozen -> FROZEN.txt; every run refuses anything else
  run c|p|q              a batch: c - six controls, p - pairs 1-12, q - pairs 13-24; the budget (54) in ledger.tsv; q only after p's check has passed
  check c|p|q            the checks of a batch -> check_<batch>.json; any defect is a STOP
  analyze                every run -> WP3_RUNS.jsonl, WP3_RESULTS.json, WP3_TABLES.md

Normalised, and only these, as in WP2 and WP2.1: [AIRESULT] ms=, [AIREUSE] fallback_us=. Raw differences are kept beside the verdict."""
import gzip
import hashlib
import io
import json
import math
import os
import random
import re
import subprocess
import sys
import time
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import scheduler_integrity_check as sic

S = HERE.parent
ST = S / "cm" / "st"
RES = HERE / "res"
LEDGER = HERE / "ledger.tsv"
FROZEN = HERE / "FROZEN.txt"
BUDGET = 54
KEY = os.path.expanduser("~/.ssh/oxce_worker")
HOST = "user@100.93.184.94"
R = "C:\\OXCE_AIWorker\\cmrun"
X = "openxcom" ".exe"
EXE = HERE / "b-x" / "bin" / X
TURNS = 60
SCEN = "L8"
SEEDLESS = 20261106
N = 49
UNIT = 1000006
TARGET = "324"
TO = "12.17.0"
WEAPON = "STR_PIR_PLASMA_RIFLE"
TYPE_A = 7  # BA_AUTOSHOT
TYPE_B = 8  # BA_SNAPSHOT
TIME = {TYPE_A: 31, TYPE_B: 23}
# the state at the point of intervention, from WP2.1 (AI_FORGE_WP2_1_RESULT.md): every run must find it
REF_CHAIN = "867d455d5479b994"
REF_STATE = "f9f520b4481108e4"
REF_RNG = "c7bcd5cc1f42ddf4"
PREFIX_EVENTS = 611
PREFIX_GAME = 369
DEAD, UNCONSCIOUS = 6, 7
ARCHIVE_D0 = S / "sfc" / "res" / "res_sfF.zip", "sfF_D_L8_s1"
ARCHIVE_WP21_A1 = S / "forge21" / "res" / "res_fxA1.zip", "fxA1_YA_L8_s1"
NORMALISED = {"[AIRESULT] ms=": re.compile(r" ms=\d+"), "[AIREUSE] fallback_us=": re.compile(r" fallback_us=\d+")}
JOBS = {"c": 6, "p": 12, "q": 12}
PAIRS = 24
BOOTSTRAP = 10000
FLIPS = 50000
STAT_SEED = 20261106
T95 = {11: 2.2010, 23: 2.0687}


def seed_of(kind, i):
    """From fixed text; 0 would stop the generator for good."""
    v = int.from_bytes(hashlib.sha256(f"AI FORGE WP3 {kind} {i}".encode()).digest()[:8], "big")
    assert v != 0
    return v


K1, K2 = seed_of("control", 1), seed_of("control", 2)
SEEDS = [seed_of("experiment", i) for i in range(1, PAIRS + 1)]
assert len(set(SEEDS + [K1, K2])) == PAIRS + 2


def arms():
    """arm -> (mode type or None, seed or None)"""
    out = {"Z3O": (None, None), "Z3KA1": (TYPE_A, K1), "Z3KA2": (TYPE_A, K1), "Z3KB1": (TYPE_B, K1), "Z3KB2": (TYPE_B, K1), "Z3KD": (TYPE_A, K2)}
    for i, s in enumerate(SEEDS, 1):
        out[f"Z3A{i:02d}"] = (TYPE_A, s)
        out[f"Z3B{i:02d}"] = (TYPE_B, s)
    return out


ARMS = arms()
BATCH = {"c": ["Z3O", "Z3KA1", "Z3KA2", "Z3KB1", "Z3KB2", "Z3KD"],
         "p": [f"Z3{b}{i:02d}" for i in range(1, 13) for b in "AB"],
         "q": [f"Z3{b}{i:02d}" for i in range(13, 25) for b in "AB"]}
assert sum(len(v) for v in BATCH.values()) == BUDGET and set(sum(BATCH.values(), [])) == set(ARMS)
PREFIX = {"c": "f3c", "p": "f3p", "q": "f3q"}


def batch_of(arm):
    return next(b for b, v in BATCH.items() if arm in v)


def label_of(arm):
    return f"{PREFIX[batch_of(arm)]}_{arm}_{SCEN}_s1"


def zip_of(arm):
    return RES / f"res_{PREFIX[batch_of(arm)]}.zip"


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


def normal(s):
    for head, pattern in NORMALISED.items():
        if s.startswith(head.split(" ")[0]):
            return pattern.sub("", s)
    return s


class Run:
    """One log, by kind of line."""

    def __init__(self, name, source=None):
        self.name = name
        self.source = source or (zip_of(name), label_of(name))
        self.lines = sic.read_log(*self.source)
        self.game, self.raw, self.forge, self.time, self.branch, self.legal = [], [], [], [], [], []
        self.dumps = {}
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
        s = next((x for x in self.branch if f" phase={name} " in x), "")
        return dict(sic.KV.findall(s))

    def clock(self, at):
        s = next((x for x in self.time if f" at={at} " in x), "")
        d = dict(sic.KV.findall(s))
        return int(d["battle_real_ms"]) if "battle_real_ms" in d else None

    def clock_turn(self, at):
        s = next((x for x in self.time if f" at={at} " in x), "")
        return dict(sic.KV.findall(s)).get("turn")


def one_dump(rows):
    """Dumps are kept by the event number, and two can share one: only the first of them."""
    return rows[:next((i for i, r in enumerate(rows) if i and r.startswith("why=")), len(rows))]


def dump_of(run, why):
    return one_dump(next((rows[i:] for rows in run.dumps.values() for i, r in enumerate(rows) if r.startswith(f"why={why}")), []))


def unit_rows(rows):
    out = {}
    for r in rows:
        m = re.match(r"u=(\d+) ", r)
        if m:
            out[m.group(1)] = dict(sic.KV.findall(r))
    return out


def number(d, key):
    return int(d.get(key, 0))


def armor_sum(d):
    return sum(int(x) for x in d.get("armor", "0").split(","))


def is_dead(d):
    return number(d, "st") == DEAD or number(d, "hp") <= 0


def is_unconscious(d):
    return not is_dead(d) and (number(d, "st") == UNCONSCIOUS or number(d, "stun") >= number(d, "hp"))


def unit_change(a, b):
    """One unit from the intervention to a horizon; what it gained back does not cancel what another lost."""
    return {"hp_lost": max(0, number(a, "hp") - max(0, number(b, "hp"))), "armor_lost": max(0, armor_sum(a) - armor_sum(b)), "stun_gain": max(0, number(b, "stun") - number(a, "stun")),
            "morale_loss": max(0, number(a, "mor") - number(b, "mor")), "wounds_gain": max(0, number(b, "wounds") - number(a, "wounds")),
            "burning_new": int(number(b, "fire") > 0 and number(a, "fire") == 0),
            "dead_new": int(is_dead(b) and not is_dead(a)), "unconscious_new": int(is_unconscious(b) and not is_unconscious(a) and not is_dead(a)),
            "out_new": int((is_dead(b) or is_unconscious(b)) and not (is_dead(a) or is_unconscious(a)))}


FIELDS = ("hp_lost", "armor_lost", "stun_gain", "morale_loss", "wounds_gain", "burning_new", "dead_new", "unconscious_new", "out_new")


def tiles_row(rows):
    r = next((x for x in rows if x.startswith("tiles_changed=")), "")
    return dict(sic.KV.findall(r))


def horizon_metrics(before, after):
    """Relative to the state at the intervention, by the side a unit fought for at the start: the sums are what they say, no weights."""
    ua, ub = unit_rows(before), unit_rows(after)
    out = {}
    side = {"player": "0", "hostile": "1", "neutral": "2"}
    for name, fac in side.items():
        total = dict.fromkeys(FIELDS, 0)
        for u, a in ua.items():
            if a.get("ofac", a.get("fac")) == fac and u in ub:
                for k, v in unit_change(a, ub[u]).items():
                    total[k] += v
        for k, v in total.items():
            out[f"{name}_{k}"] = v
        out[f"{name}_new_units"] = sum(1 for u, b in ub.items() if u not in ua and b.get("ofac", b.get("fac")) == fac)
    actor = str(UNIT)
    if actor in ua and actor in ub:
        change = unit_change(ua[actor], ub[actor])
        out["actor_hp_lost"] = change["hp_lost"]
        for k in FIELDS:
            out[f"own_{k}"] = out[f"hostile_{k}"] - change[k]
        out["tu_spent"] = number(ua[actor], "tu") - number(ub[actor], "tu")
        out["ammo_spent"] = number(ua[actor], "ammo") - number(ub[actor], "ammo")
    if TARGET in ua and TARGET in ub:
        for k, v in unit_change(ua[TARGET], ub[TARGET]).items():
            out[f"target_{k}"] = v
    t = tiles_row(after)
    for k in ("objects", "fire_new", "smoke_new", "fire_now", "smoke_now", "light_only", "tiles_changed"):
        out[k] = int(t.get(k, 0))
    return out


def act_index(ev):
    for i, (_, _, _, d) in enumerate(ev):
        if d.get("ev") == "decide" and d.get("d") == str(N):
            for j in range(i + 1, len(ev)):
                if ev[j][3].get("ev") == "act":
                    return j
    return None


def run_metrics(run):
    before = dump_of(run, "intervene")
    h1 = dump_of(run, "after_branch")
    r0 = dump_of(run, "round0")
    r1 = dump_of(run, "round1")
    end = dump_of(run, "end")
    ev = run.events()
    j = act_index(ev)
    nxt = next((k for k in range(j + 1, len(ev)) if ev[k][3].get("ev") == "decide"), len(ev)) if j is not None else None
    out = {"h1": horizon_metrics(before, h1) if h1 else None, "round0": horizon_metrics(before, r0) if r0 else None, "h2": horizon_metrics(before, r1 or end) if (r1 or end) else None, "end": horizon_metrics(before, end) if end else None}
    if out["h1"] is not None and j is not None:
        out["h1"]["reactions"] = sum(1 for k in range(j, nxt) if ev[k][3].get("ev") == "react")
    if out["h2"] is not None:
        out["h2"]["ended_before_h2"] = int(not r1)
    return out


def run_record(run):
    t, s = ARMS.get(run.name, (None, None))
    res = run.result()
    return {"arm": run.name, "label": run.source[1], "type": t, "seed": s, "metrics": run_metrics(run), "result": {k: res.get(k) for k in ("how", "turn", "player", "pdead", "pout", "pwounded", "phplost", "hostile", "hdead", "hout", "hleft", "pmoves", "pattacks", "hmoves", "hattacks", "ms", "vms")},
            "cost_ms": {"prefix": run.clock("intervene"), "h1": run.clock("after_branch"), "round0": run.clock("round0"), "h2": run.clock("round1"), "end": run.clock("end")}, "h2_turn": run.clock_turn("round1")}


# the checks: any defect is a STOP


def prov_of(run):
    with zipfile.ZipFile(run.source[0]) as z:
        return z.read(f"arena/{run.source[1]}.prov.txt").decode("utf-8", errors="replace")


def prov_fields(run):
    """Line by line: the pattern of key=value would run on across a line end."""
    return dict(x.split("=", 1) for x in prov_of(run).split("effective_env:")[0].splitlines()[1:] if "=" in x)


def post_modes(run):
    """The first from= and to= of the line: the action's text after them has a to= of its own, the target."""
    m = re.search(r" phase=post from=(\d+) to=(\d+) ", next((x for x in run.branch if " phase=post " in x), ""))
    return (m.group(1), m.group(2)) if m else (None, None)


def frozen():
    return dict(x.split("=", 1) for x in FROZEN.read_text(encoding="utf-8").splitlines() if "=" in x)


def check_run(run):
    """One run with the arena on: what it must have found and done, whatever its seed."""
    t, s = ARMS[run.name]
    bad = []
    prov = prov_fields(run)
    exe = frozen()["exe_sha256"]
    if prov.get("exe_sha256") != exe or "\\exe\\F3\\" not in prov.get("exe_path", ""):
        bad.append(f"exe {prov.get('exe_sha256')} {prov.get('exe_path')}")
    pre, post, re_ = run.phase("pre"), run.phase("post"), run.phase("reseed")
    for k, v in (("chain", REF_CHAIN), ("state", REF_STATE), ("rng", REF_RNG)):
        if pre.get(k) != v:
            bad.append(f"pre {k} {pre.get(k)} is not {v}")
    if pre.get("type") != str(TYPE_A):
        bad.append(f"think() chose {pre.get('type')}")
    if post_modes(run) != (str(TYPE_A), str(t)) or post.get("time_after") != str(TIME[t]):
        bad.append(f"post {post_modes(run)} {post.get('time_after')}")
    if re_.get("seed") != str(s) or re_.get("now") != f"{s:x}" or re_.get("was") != REF_RNG:
        bad.append(f"reseed {re_}")
    ev = run.events()
    j = act_index(ev)
    if j is None:
        bad.append("no action after the decision")
    else:
        if ev[j][3].get("type") != str(t):
            bad.append(f"carried out type {ev[j][3].get('type')}")
        if ev[j][3].get("rng") != f"{s:x}":
            bad.append(f"the action line's rng {ev[j][3].get('rng')} is not the seed")
        if j != PREFIX_EVENTS:
            bad.append(f"prefix {j} events")
        if len(run.game_before(ev[j][0])) != PREFIX_GAME:
            bad.append("prefix engine lines")
    c = sic.check(run.lines)
    if c["violations"]:
        bad.append(f"violations {c['first_violations'][:3]}")
    if not dump_of(run, "after_branch"):
        bad.append("no dump after the action")
    if not (dump_of(run, "round1") or dump_of(run, "end")):
        bad.append("no second horizon")
    if not run.result().get("how"):
        bad.append("no result line")
    if TARGET not in unit_rows(dump_of(run, "intervene")):
        bad.append("target not in the dump")
    return {"arm": run.name, "defects": bad, "events": c["events"], "violations": c["violations"], "tu_kinds": {k: v for k, v in c["counts"].items() if k.startswith("tu")}, "notes": c["notes"]}


def first_difference(xs, ys):
    for i, (x, y) in enumerate(zip(xs, ys)):
        if x != y:
            return {"index": i, "a": x[:600], "b": y[:600]}
    if len(xs) != len(ys):
        k = min(len(xs), len(ys))
        return {"index": k, "a": (xs[k][:600] if len(xs) > k else "<end>"), "b": (ys[k][:600] if len(ys) > k else "<end>")}
    return None


def same_run(a, b):
    """Two runs with one seed and one mode: to the last event."""
    common = sorted(set(a.dumps) & set(b.dumps))
    out = {"a": a.name, "b": b.name, "forge_events": [len(a.forge), len(b.forge)], "game_lines": [len(a.game), len(b.game)], "chain_identical": a.forge == b.forge, "chain_first_difference": first_difference(a.forge, b.forge),
           "game_identical": a.game == b.game, "game_first_difference": first_difference(a.game, b.game), "dumps_compared": len(common), "dumps_only_one": sorted(set(a.dumps) ^ set(b.dumps)),
           "dump_first_difference": next((first_difference(a.dumps[n], b.dumps[n]) for n in common if a.dumps[n] != b.dumps[n]), None), "branch_lines_equal": a.branch == b.branch, "legal_lines_equal": a.legal == b.legal,
           "raw_differences": sum(1 for x, y in zip(a.raw, b.raw) if x != y) + abs(len(a.raw) - len(b.raw))}
    out["verdict"] = "IDENTICAL" if all((out["chain_identical"], out["game_identical"], out["dump_first_difference"] is None, not out["dumps_only_one"], out["branch_lines_equal"], out["legal_lines_equal"])) else "DIFFERENT"
    return out


def rng_values(run):
    ev = run.events()
    j = act_index(ev)
    return [d.get("rng") for *_, d in ev[j:]]


def different_seeds(a, b):
    """Not the same state used twice: the generator's states after the point of intervention have nothing in common, and the runs differ."""
    xa, xb = rng_values(a), rng_values(b)
    return {"a": a.name, "b": b.name, "values": [len(xa), len(xb)], "first_rng": [xa[0], xb[0]], "common_values": len(set(xa) & set(xb)), "same_course": a.game == b.game}


def coupling(a, b):
    """One seed, two modes: how far the same seed really keeps them together. It is the same stream of numbers, read by different consumers."""
    ea, eb = a.events(), b.events()
    ja, jb = act_index(ea), act_index(eb)
    xa, xb = [e[3].get("rng") for e in ea[ja:]], [e[3].get("rng") for e in eb[jb:]]
    together = next((k for k, (x, y) in enumerate(zip(xa, xb)) if x != y), min(len(xa), len(xb)))
    return {"a": a.name, "b": b.name, "events_in_step": together, "shared_state_share_of_b": round(len(set(xa) & set(xb)) / max(1, len(set(xb))), 4), "act_fields_differ": {k: [ea[ja][3].get(k), eb[jb][3].get(k)] for k in sorted(set(ea[ja][3]) | set(eb[jb][3])) if ea[ja][3].get(k) != eb[jb][3].get(k)}}


def pair_check(a, b):
    ea, eb = a.events(), b.events()
    ja, jb = act_index(ea), act_index(eb)
    bad = []
    if a.forge[:ja] != b.forge[:jb]:
        bad.append(f"chain before the action differs {first_difference(a.forge[:ja], b.forge[:jb])}")
    if a.game_before(ea[ja][0]) != b.game_before(eb[jb][0]):
        bad.append("engine lines before the action differ")
    if dump_of(a, "intervene") != dump_of(b, "intervene"):
        bad.append("dump at the intervention differs")
    if a.phase("pre") != b.phase("pre"):
        bad.append("phase pre differs")
    c = coupling(a, b)
    if set(c["act_fields_differ"]) != {"type"}:
        bad.append(f"the action differs in {c['act_fields_differ']}")
    return {"pair": [a.name, b.name], "defects": bad, "coupling": c}


def check_batch(batch):
    out = {"batch": batch, "frozen": frozen()}
    runs = {arm: Run(arm) for arm in BATCH[batch]}
    defects = []
    active = [r for arm, r in runs.items() if ARMS[arm][0] is not None]
    out["runs"] = [check_run(r) for r in active]
    defects += [f"{x['arm']}: {d}" for x in out["runs"] for d in x["defects"]]
    if batch == "c":
        off = runs["Z3O"]
        d0 = Run("arch:D0", ARCHIVE_D0)
        out["off_vs_d0"] = {"game_lines": [len(off.game), len(d0.game)], "identical": off.game == d0.game, "first_difference": first_difference(off.game, d0.game), "raw_differences": sum(1 for x, y in zip(off.raw, d0.raw) if x != y) + abs(len(off.raw) - len(d0.raw)), "monitor_lines": len(off.forge) + len(off.branch) + sum(len(v) for v in off.dumps.values())}
        prov = prov_fields(off)
        out["off_exe"] = [prov.get("exe_sha256"), prov.get("exe_path")]
        if not out["off_vs_d0"]["identical"] or out["off_vs_d0"]["monitor_lines"]:
            defects.append("OFF is not D0")
        if out["off_exe"][0] != frozen()["exe_sha256"]:
            defects.append("OFF ran another exe")
        a1 = Run("arch:WP21A1", ARCHIVE_WP21_A1)
        ka = runs["Z3KA1"]
        ja = act_index(ka.events())
        out["prefix_vs_wp21"] = {"chain_identical": ka.forge[:ja] == a1.forge[:ja], "dump_identical": [re.sub(r" ofac=\d", "", x) for x in dump_of(ka, "intervene")] == dump_of(a1, "intervene")}
        if not all(out["prefix_vs_wp21"].values()):
            defects.append(f"the prefix is not WP2.1's {out['prefix_vs_wp21']}")
        out["AA"] = same_run(runs["Z3KA1"], runs["Z3KA2"])
        out["BB"] = same_run(runs["Z3KB1"], runs["Z3KB2"])
        for k in ("AA", "BB"):
            if out[k]["verdict"] != "IDENTICAL":
                defects.append(f"{k} differs")
        out["different_seeds"] = different_seeds(runs["Z3KA1"], runs["Z3KD"])
        if out["different_seeds"]["common_values"] or out["different_seeds"]["same_course"]:
            defects.append("two seeds gave one course")
        out["pair"] = pair_check(runs["Z3KA1"], runs["Z3KB1"])
        defects += out["pair"]["defects"]
    else:
        idx = sorted({arm[3:] for arm in BATCH[batch]})
        out["pairs"] = [pair_check(runs[f"Z3A{i}"], runs[f"Z3B{i}"]) for i in idx]
        defects += [f"{x['pair']}: {d}" for x in out["pairs"] for d in x["defects"]]
        values = {arm: set(rng_values(runs[arm])) for arm in BATCH[batch] if arm.startswith("Z3A")}
        names = sorted(values)
        out["overlaps_between_seeds"] = sum(len(values[x] & values[y]) for i, x in enumerate(names) for y in names[i + 1:])
        out["distinct_courses"] = len({tuple(runs[arm].game) for arm in names})
        if out["overlaps_between_seeds"] or out["distinct_courses"] != len(names):
            defects.append(f"seeds not independent: overlaps {out['overlaps_between_seeds']}, courses {out['distinct_courses']} of {len(names)}")
    out["defects"] = defects
    out["verdict"] = "STOP" if defects else "PASS"
    return out


# the statistics: only the standard library, every random draw from a fixed seed


def mean(xs):
    return sum(xs) / len(xs)


def var(xs):
    m = mean(xs)
    return sum((x - m) ** 2 for x in xs) / (len(xs) - 1)


def t_interval(ds):
    n = len(ds)
    se = math.sqrt(var(ds) / n)
    if se == 0:
        return None
    h = T95[n - 1] * se
    return [mean(ds) - h, mean(ds) + h]


def bootstrap_interval(ds, rng):
    if len(set(ds)) == 1:
        return None
    n = len(ds)
    ms = sorted(sum(rng.choices(ds, k=n)) / n for _ in range(BOOTSTRAP))
    return [ms[int(0.025 * BOOTSTRAP)], ms[int(0.975 * BOOTSTRAP) - 1]]


def sign_flip_p(ds, rng):
    """Two-sided: how often random signs of the differences give a mean at least as far from zero. Assumes nothing about their shape."""
    if not any(ds):
        return 1.0
    seen = abs(sum(ds))
    n = len(ds)
    hits = 0
    for _ in range(FLIPS):
        bits = rng.getrandbits(n)
        total = 0
        for i, d in enumerate(ds):
            total += d if (bits >> i) & 1 else -d
        if abs(total) >= seen:
            hits += 1
    return (hits + 1) / (FLIPS + 1)


def holm(ps):
    """Adjusted p-values for {name: p}."""
    order = sorted(ps, key=ps.get)
    out = {}
    worst = 0.0
    m = len(order)
    for i, k in enumerate(order):
        worst = max(worst, min(1.0, ps[k] * (m - i)))
        out[k] = worst
    return out


def describe(xa, xb, direction, rng=None, with_p=False):
    """B - A by pairs. direction: +1 more is better for the side that shoots, -1 less is better, None no direction agreed in advance."""
    ds = [b - a for a, b in zip(xa, xb)]
    n = len(ds)
    va, vb, vd = var(xa), var(xb), var(ds)
    rng = rng or random.Random(STAT_SEED)
    out = {"n": n, "mean_a": mean(xa), "mean_b": mean(xb), "diff": mean(ds), "sd_a": math.sqrt(va), "sd_b": math.sqrt(vb), "sd_diff": math.sqrt(vd), "ci95_t": t_interval(ds), "ci95_bootstrap": bootstrap_interval(ds, rng),
           "se_paired": math.sqrt(vd / n), "se_independent": math.sqrt((va + vb) / n), "correlation": None if va == 0 or vb == 0 else (va + vb - vd) / (2 * math.sqrt(va * vb)), "b_more": sum(d > 0 for d in ds), "b_less": sum(d < 0 for d in ds), "equal": sum(d == 0 for d in ds)}
    if out["se_independent"] > 0:
        out["variance_ratio_paired_to_independent"] = vd / (va + vb)
    if direction is None:
        out["b_better"] = out["b_worse"] = None
    else:
        out["b_better"] = out["b_more"] if direction > 0 else out["b_less"]
        out["b_worse"] = out["b_less"] if direction > 0 else out["b_more"]
    if with_p:
        out["p_sign_flip"] = sign_flip_p(ds, rng)
    return out


# metric -> Russian name, direction for the side that shoots; agreed in the plan before the first run
H1_TABLE = [("tu_spent", "ОВ стрелка", -1), ("ammo_spent", "патроны стрелка", -1), ("target_hp_lost", "цель 324: HP", 1), ("target_armor_lost", "цель 324: броня", 1), ("target_stun_gain", "цель 324: оглушение", 1), ("target_morale_loss", "цель 324: мораль", 1),
            ("target_wounds_gain", "цель 324: раны", 1), ("target_burning_new", "цель 324: загорелась", 1), ("target_out_new", "цель 324: выбыла", 1), ("player_hp_lost", "игрок: HP", 1), ("player_armor_lost", "игрок: броня", 1), ("player_stun_gain", "игрок: оглушение", 1),
            ("player_morale_loss", "игрок: мораль", 1), ("player_wounds_gain", "игрок: раны", 1), ("player_burning_new", "игрок: загорелись", 1), ("player_out_new", "игрок: выбыли", 1), ("own_hp_lost", "свои без стрелка: HP", -1), ("own_armor_lost", "свои без стрелка: броня", -1),
            ("own_stun_gain", "свои без стрелка: оглушение", -1), ("own_morale_loss", "свои без стрелка: мораль", -1), ("own_out_new", "свои без стрелка: выбыли", -1), ("actor_hp_lost", "стрелок: HP", -1), ("reactions", "реакций до следующего решения", None), ("objects", "клетки с изменённым объектом", None), ("fire_new", "новые клетки с огнём", None), ("smoke_new", "новые клетки с дымом", None)]
H2_TABLE = [("player_hp_lost", "игрок: HP", 1), ("player_armor_lost", "игрок: броня", 1), ("player_stun_gain", "игрок: оглушение", 1), ("player_morale_loss", "игрок: мораль", 1), ("player_wounds_gain", "игрок: раны", 1), ("player_burning_new", "игрок: загорелись", 1), ("player_dead_new", "игрок: погибли", 1),
            ("player_out_new", "игрок: выбыли всего", 1), ("hostile_hp_lost", "враг: HP", -1), ("hostile_armor_lost", "враг: броня", -1), ("hostile_stun_gain", "враг: оглушение", -1), ("hostile_morale_loss", "враг: мораль", -1), ("hostile_dead_new", "враг: погибли", -1), ("hostile_out_new", "враг: выбыли всего", -1),
            ("objects", "клетки с изменённым объектом", None), ("fire_new", "новые клетки с огнём", None), ("smoke_new", "новые клетки с дымом", None), ("fire_now", "клетки с огнём сейчас", None), ("smoke_now", "клетки с дымом сейчас", None), ("ended_before_h2", "бой кончился раньше", None)]
PRIMARY = [("h1", "player_hp_lost", 1), ("h1", "player_out_new", 1), ("h1", "own_hp_lost", -1), ("h2", "player_hp_lost", 1), ("h2", "player_out_new", 1), ("h2", "hostile_hp_lost", -1), ("h2", "hostile_out_new", -1)]
DYNAMICS = [("player_hp_lost", "игрок: HP", 1), ("player_out_new", "игрок: выбыли всего", 1), ("hostile_hp_lost", "враг: HP", -1), ("hostile_out_new", "враг: выбыли всего", -1)]
END_FIELDS = [("turn", "ход конца боя"), ("pdead", "погибло бойцов"), ("phplost", "HP игрока за весь бой"), ("hdead", "погибло врагов"), ("hout", "врагов без сознания"), ("hattacks", "атак врага"), ("pattacks", "атак игрока")]


def series(records, kind, horizon, metric):
    arms_ = [f"Z3{kind}{i:02d}" for i in range(1, PAIRS + 1)]
    return [records[a]["metrics"][horizon].get(metric, 0) for a in arms_]


def analyze():
    runs = {arm: Run(arm) for arm in ARMS}
    records = {arm: run_record(r) for arm, r in runs.items() if ARMS[arm][0] is not None}
    records["Z3O"] = {"arm": "Z3O", "label": label_of("Z3O"), "result": runs["Z3O"].result()}
    with open(HERE / "WP3_RUNS.jsonl", "w", encoding="utf-8") as f:
        for arm in ARMS:
            f.write(json.dumps(records[arm], ensure_ascii=False) + "\n")
    rng = random.Random(STAT_SEED)
    out = {"frozen": frozen(), "seeds": {"control": [K1, K2], "experiment": SEEDS}, "ledger": ledger(), "bootstrap": BOOTSTRAP, "flips": FLIPS}
    primary = {(h, m) for h, m, _ in PRIMARY}
    for horizon, table in (("h1", H1_TABLE), ("h2", H2_TABLE)):
        out[horizon] = {m: {"name": name, "direction": d, **describe(series(records, "A", horizon, m), series(records, "B", horizon, m), d, rng, (horizon, m) in primary)} for m, name, d in table}
    out["dynamics"] = {}
    for m, name, d in DYNAMICS:
        xa = [y - x for x, y in zip(series(records, "A", "h1", m), series(records, "A", "h2", m))]
        xb = [y - x for x, y in zip(series(records, "B", "h1", m), series(records, "B", "h2", m))]
        out["dynamics"][m] = {"name": name, "direction": d, **describe(xa, xb, d, rng)}
    ps = {f"{h}.{m}": out[h][m]["p_sign_flip"] for h, m, _ in PRIMARY}
    adj = holm(ps)
    out["primary"] = {k: {"p": ps[k], "p_holm": adj[k], "signal": adj[k] < 0.05} for k in ps}
    # the negative control: two runs of one mode with unrelated seeds, disjoint pairs; whatever shows here is the RNG alone
    out["placebo"] = {}
    for kind in "AB":
        for h, m, d in PRIMARY:
            xs = series(records, kind, h, m)
            out["placebo"][f"{kind}.{h}.{m}"] = describe(xs[:12], xs[12:], d, rng, True)
    out["placebo_signals_before_holm"] = sum(v["p_sign_flip"] < 0.05 for v in out["placebo"].values())
    out["same_seed_AA"] = json.loads((HERE / "check_c.json").read_text(encoding="utf-8-sig"))["AA"]["verdict"]
    out["end_of_battle_descriptive"] = {k: {"name": name, **describe([float(records[f"Z3A{i:02d}"]["result"][k]) for i in range(1, 25)], [float(records[f"Z3B{i:02d}"]["result"][k]) for i in range(1, 25)], None, rng)} for k, name in END_FIELDS}
    ca = [coupling(runs[f"Z3A{i:02d}"], runs[f"Z3B{i:02d}"]) for i in range(1, 25)]
    out["coupling"] = {"events_in_step": sorted(c["events_in_step"] for c in ca), "shared_state_share_of_b": sorted(c["shared_state_share_of_b"] for c in ca)}
    values = {f"Z3A{i:02d}": set(rng_values(runs[f"Z3A{i:02d}"])) for i in range(1, 25)}
    names = sorted(values)
    out["independence"] = {"pairs_of_seeds": len(names) * (len(names) - 1) // 2, "common_states": sum(len(values[x] & values[y]) for i, x in enumerate(names) for y in names[i + 1:]), "distinct_courses_a": len({tuple(runs[n].game) for n in names}), "distinct_courses_b": len({tuple(runs[f"Z3B{i:02d}"].game) for i in range(1, 25)})}
    cost = {k: [records[f"Z3{b}{i:02d}"]["cost_ms"][k] for b in "AB" for i in range(1, 25) if records[f"Z3{b}{i:02d}"]["cost_ms"][k] is not None] for k in ("prefix", "h1", "h2", "end")}
    out["cost_ms"] = {k: {"n": len(v), "mean": mean(v), "min": min(v), "max": max(v)} for k, v in cost.items() if v}
    out["log_mb_total"] = sum((RES / f"res_{p}.zip").stat().st_size for p in PREFIX.values()) / 1e6
    out["signals"] = [k for k, v in out["primary"].items() if v["signal"]]
    out["verdict_use"] = "SIGNAL" if out["signals"] else "NO EVIDENCE"
    (HERE / "WP3_RESULTS.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8-sig")
    (HERE / "WP3_TABLES.md").write_text(tables(out), encoding="utf-8-sig")
    print(tables(out))
    return out


def fmt(x, digits=2):
    if x is None:
        return "—"
    return f"{x:.{digits}f}".replace(".", ",")


def interval(i):
    return "нет разброса" if i is None else f"{fmt(i[0])} … {fmt(i[1])}"


def table_of(section):
    rows = ["| Метрика | A среднее | B среднее | B − A | SD A | SD B | SD разности | 95% ДИ (t) | 95% ДИ (бутстреп) | B лучше / хуже / равно |", "|---|---|---|---|---|---|---|---|---|---|"]
    for m, v in section.items():
        share = f"{v['b_better']} / {v['b_worse']} / {v['equal']}" if v["direction"] is not None else f"больше {v['b_more']} / меньше {v['b_less']} / равно {v['equal']}"
        rows.append(f"| {v['name']} | {fmt(v['mean_a'])} | {fmt(v['mean_b'])} | {fmt(v['diff'])} | {fmt(v['sd_a'])} | {fmt(v['sd_b'])} | {fmt(v['sd_diff'])} | {interval(v['ci95_t'])} | {interval(v['ci95_bootstrap'])} | {share} |")
    return "\n".join(rows)


def tables(out):
    t = ["## Сразу после действия", "", table_of(out["h1"]), "", "## После следующего полного раунда", "", table_of(out["h2"]), "", "## Только последующая динамика (второй горизонт минус первый)", "", table_of(out["dynamics"]), ""]
    t += ["## Основные метрики", "", "| Метрика | p (случайные знаки) | p по Холму | Сигнал |", "|---|---|---|---|"]
    for k, v in out["primary"].items():
        t.append(f"| {k} | {fmt(v['p'], 4)} | {fmt(v['p_holm'], 4)} | {'да' if v['signal'] else 'нет'} |")
    t += ["", "## Парный анализ против независимых групп", "", "| Горизонт | Метрика | SE пар | SE независимых | Отношение дисперсий | Корреляция |", "|---|---|---|---|---|---|"]
    for h in ("h1", "h2"):
        for m, v in out[h].items():
            if m in [x[1] for x in PRIMARY if x[0] == h]:
                t.append(f"| {h} | {v['name']} | {fmt(v['se_paired'])} | {fmt(v['se_independent'])} | {fmt(v.get('variance_ratio_paired_to_independent'))} | {fmt(v['correlation'])} |")
    t += ["", "## Отрицательный контроль: A с A и B с B на разных сидах (12 непересекающихся пар)", "", "| Сравнение | Разность | SD разности | 95% ДИ | p |", "|---|---|---|---|---|"]
    for k, v in out["placebo"].items():
        t.append(f"| {k} | {fmt(v['diff'])} | {fmt(v['sd_diff'])} | {interval(v['ci95_t'])} | {fmt(v['p_sign_flip'], 4)} |")
    t += ["", "## Конец боя (описательно, на вывод не влияет)", "", "| Поле | A | B | B − A | SD разности | 95% ДИ |", "|---|---|---|---|---|---|"]
    for k, v in out["end_of_battle_descriptive"].items():
        t.append(f"| {v['name']} | {fmt(v['mean_a'])} | {fmt(v['mean_b'])} | {fmt(v['diff'])} | {fmt(v['sd_diff'])} | {interval(v['ci95_t'])} |")
    return "\n".join(t) + "\n"


# the stand


def cmd_seeds():
    print("control", K1, K2)
    for i, s in enumerate(SEEDS, 1):
        print(i, s)


def block():
    base = ["OXCE_AI_FORGE=1", f"OXCE_AI_FORGE_SEEDLESS={SEEDLESS}", f"OXCE_AI_FORGE_BRANCH_AT={N}", f"OXCE_AI_FORGE_BRANCH_UNIT={UNIT}", f"OXCE_AI_FORGE_BRANCH_TO={TO}", f"OXCE_AI_FORGE_BRANCH_WEAPON={WEAPON}", f"OXCE_AI_FORGE_BRANCH_FROM={TYPE_A}", "OXCE_AI_FORGE_BRANCH_MODE=act", f"OXCE_AI_FORGE_BRANCH_CHAIN={REF_CHAIN}", f"OXCE_AI_FORGE_BRANCH_STATE={REF_STATE}"]
    lines = ["# AI FORGE WP3 (GO Vitali 06.11, at most 54 runs): exe F3; Z3O - nothing set; the rest - the state checked at decision 49, the mode of the shot, the game RNG := the seed of the pair (offline arena only)", f"_F3 = {base!r}", 'ARMS["Z3O"] = ("env_F3.txt", [], COMMON_D0)']
    lines += [f'ARMS["{a}"] = ("env_F3.txt", _F3 + ["OXCE_AI_FORGE_BRANCH_TYPE={t}", "OXCE_AI_FORGE_RESEED={s}"], COMMON_D0)' for a, (t, s) in ARMS.items() if t is not None]
    return "\n".join(lines) + "\n"


def cmd_up():
    d = ST / "exe" / "F3"
    d.mkdir(parents=True, exist_ok=True)
    h = sha(EXE)
    (d / X).write_bytes(EXE.read_bytes())
    (d / "BUILD_INFO.txt").write_text(f"build_label=cmrun-F3\ngit_commit=07680cadb\nnote=HEAD + al.diff + al3.diff + AI FORGE monitor + WP2.1 arena + WP3 reseed and horizons (flags only)\nmonitor_sha256={sha(HERE / 'mon' / 'SchedulerIntegrityMonitor.cpp')}\n", encoding="utf-8")
    env = (ST / "env_D0.txt").read_text(encoding="utf-8").replace("/exe/D0/", "/exe/F3/")
    assert "/exe/F3/" in env
    (ST / "env_F3.txt").write_text(env, encoding="utf-8")
    run = (ST / "run_cm.py").read_text(encoding="utf-8")
    # R-773, R-785: an arm name already taken would silently keep the old arm and its exe
    if 'ARMS["Z3O"]' not in run:
        assert '"Z3' not in run, "arm name taken"
        old = "}\nTURNS = 60\n"
        assert run.count(old) == 1
        run = run.replace(old, "}\n" + block() + "TURNS = 60\n")
        (ST / "run_cm.py").write_text(run, encoding="utf-8")
    ssh(f"if not exist {R}\\exe\\F3 mkdir {R}\\exe\\F3")
    scp(str(d / X), str(d / "BUILD_INFO.txt"), f"{HOST}:C:/OXCE_AIWorker/cmrun/exe/F3/")
    scp(str(ST / "env_F3.txt"), str(ST / "run_cm.py"), f"{HOST}:C:/OXCE_AIWorker/cmrun/")
    rh = remote_hash(f"{R}\\exe\\F3\\{X}")
    print("local ", h)
    print("remote", rh, "OK" if rh == h else "DIFFERENT")
    print("run_cm", sha(ST / "run_cm.py") == remote_hash(f"{R}\\run_cm.py"))
    if rh != h:
        raise SystemExit(2)


def cmd_freeze():
    if FROZEN.exists():
        raise SystemExit("already frozen")
    FROZEN.write_text(f"exe_sha256={sha(EXE)}\nfrozen={time.strftime('%Y-%m-%dT%H:%M:%S')}\nmonitor_cpp={sha(HERE / 'mon' / 'SchedulerIntegrityMonitor.cpp')}\nlegal_h={sha(HERE / 'ForgeLegal.h')}\noracle={sha(Path(__file__))}\nrun_cm={sha(ST / 'run_cm.py')}\nplan={sha(HERE / 'WP3_PLAN.md')}\nseeds={hashlib.sha256(repr((K1, K2, SEEDS)).encode()).hexdigest()}\n", encoding="utf-8")
    print(FROZEN.read_text(encoding="utf-8"))


def ledger():
    if not LEDGER.exists():
        return []
    return [s.split("\t") for s in LEDGER.read_text(encoding="utf-8").splitlines() if s.strip()]


def preflight(batch):
    """Not by what is written down: the file itself on rabota, the arm itself in run_cm, nothing else running."""
    fr = frozen()
    if sha(EXE) != fr["exe_sha256"] or sha(Path(__file__)) != fr.get("oracle_after_addendum", fr["oracle"]):
        raise SystemExit("the exe or the oracle is not the frozen one")
    rh = remote_hash(f"{R}\\exe\\F3\\{X}")
    if rh != fr["exe_sha256"]:
        raise SystemExit(f"exe on rabota {rh}")
    if sha(ST / "run_cm.py") != fr["run_cm"] or remote_hash(f"{R}\\run_cm.py") != fr["run_cm"]:
        raise SystemExit("run_cm differs")
    env_ok = ssh(f"type {R}\\env_F3.txt").replace("/exe/F3/", "/exe/D0/").strip() == (ST / "env_D0.txt").read_text(encoding="utf-8").strip()
    if not env_ok:
        raise SystemExit("env_F3 is not env_D0 with another exe folder")
    text = (ST / "run_cm.py").read_text(encoding="utf-8")
    for arm in BATCH[batch]:
        if text.count(f'ARMS["{arm}"] = ("env_F3.txt"') != 1:
            raise SystemExit(f"arm {arm}")
    if ps("(Get-ScheduledTask oxce_cmrun).State").strip() != "Ready":
        raise SystemExit("the task is not Ready")
    if ps("(Get-Process openxcom -ErrorAction SilentlyContinue | Measure-Object).Count").strip() != "0":
        raise SystemExit("a game is running on rabota")
    dry = subprocess.run(["ssh", "-o", "ConnectTimeout=15", "-i", KEY, HOST, f"cd /d {R} && C:\\OXCE_AIWorker\\python\\python.exe -u run_cm.py --arms {BATCH[batch][0]} --pairs ZZ:1 --prefix dry"], capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
    if "unknown scenario" not in dry:
        raise SystemExit(f"the arm is not accepted on rabota: {dry[-300:]}")


def gate(batch):
    need = {"p": "c", "q": "p"}.get(batch)
    if need:
        p = HERE / f"check_{need}.json"
        if not p.exists() or json.loads(p.read_text(encoding="utf-8-sig"))["verdict"] != "PASS":
            raise SystemExit(f"{batch}: the check of {need} has not passed: STOP")


def cmd_run(batch):
    done = ledger()
    if any(x[0] in BATCH[batch] for x in done):
        raise SystemExit(f"{batch}: already run")
    if len(done) + len(BATCH[batch]) > BUDGET:
        raise SystemExit(f"budget: {len(done)} + {len(BATCH[batch])} of {BUDGET}")
    gate(batch)
    preflight(batch)
    fr = frozen()
    with open(LEDGER, "a", encoding="utf-8") as f:
        for arm in BATCH[batch]:
            t, s = ARMS[arm]
            f.write(f"{arm}\t{time.strftime('%Y-%m-%dT%H:%M:%S')}\t{fr['exe_sha256']}\t{t}\t{s}\t{SCEN}\tturns={TURNS}\n")
    P = PREFIX[batch]
    print(f"batch {batch}: {len(BATCH[batch])} runs, used {len(done) + len(BATCH[batch])} of {BUDGET}", flush=True)
    t0 = time.time()
    ssh(f"powershell -NoProfile -ExecutionPolicy Bypass -File {R}\\cm_launch.ps1 -Jobs {JOBS[batch]} -Tag {P} -Arms {','.join(BATCH[batch])} -Prefix {P} -Turns {TURNS} -Pairs {SCEN}:1")
    seen = ""
    for _ in range(25):
        seen = ps("Get-Process openxcom -ErrorAction SilentlyContinue | ForEach-Object { $_.Path + ' ' + (Get-FileHash $_.Path).Hash } | Sort-Object -Unique").strip()
        if seen:
            break
        time.sleep(1)
    (HERE / f"process_{batch}.txt").write_text(seen + "\n", encoding="utf-8")
    print("process", seen, flush=True)
    time.sleep(10)
    while True:
        if ps("(Get-ScheduledTask oxce_cmrun).State").strip() == "Ready":
            break
        if time.time() - t0 > 3400:
            raise SystemExit("still running after 3400 s")
        time.sleep(15)
    print(f"{time.time() - t0:.0f} s", flush=True)
    print(ssh(f"C:\\OXCE_AIWorker\\python\\python.exe -I {R}\\pack_logs.py {R} {P} {R}\\res_{P}.zip").strip()[:160], flush=True)
    RES.mkdir(exist_ok=True)
    scp(f"{HOST}:C:/OXCE_AIWorker/cmrun/res_{P}.zip", f"{HOST}:C:/OXCE_AIWorker/cmrun/logs/run_{P}.txt", str(RES))
    print((RES / f"run_{P}.txt").read_text(encoding="utf-8", errors="replace")[-300:], flush=True)
    cmd_check(batch)


def cmd_check(batch):
    out = check_batch(batch)
    (HERE / f"check_{batch}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8-sig")
    print(batch, out["verdict"], json.dumps(out["defects"], ensure_ascii=False)[:1500])
    for k in ("off_vs_d0", "off_exe", "prefix_vs_wp21", "different_seeds", "overlaps_between_seeds", "distinct_courses"):
        if k in out:
            print(k, json.dumps(out[k], ensure_ascii=False)[:500])
    for k in ("AA", "BB"):
        if k in out:
            print(k, out[k]["verdict"], out[k]["forge_events"], out[k]["game_lines"], "dumps", out[k]["dumps_compared"], "raw", out[k]["raw_differences"])
    if "pair" in out:
        print("pair", json.dumps(out["pair"]["coupling"], ensure_ascii=False)[:300])
    if "pairs" in out:
        print("pairs", len(out["pairs"]), "in step", [x["coupling"]["events_in_step"] for x in out["pairs"]])
    print("violations", sum(x["violations"] for x in out["runs"]), "notes", sum(x["notes"] for x in out["runs"]))
    if out["verdict"] != "PASS":
        raise SystemExit("STOP")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    a = sys.argv[1:]
    if a[0] == "seeds":
        cmd_seeds()
    elif a[0] == "up":
        cmd_up()
    elif a[0] == "freeze":
        cmd_freeze()
    elif a[0] == "run":
        cmd_run(a[1])
    elif a[0] == "check":
        cmd_check(a[1])
    elif a[0] == "analyze":
        analyze()


if __name__ == "__main__":
    main()
