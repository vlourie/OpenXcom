"""AI FORGE WP1, the last check under the waiver, no new runs: every replay pair, compared raw field by field.
  1. the shift of the clock within each pair: every reading, fingerprints and dump headers;
  2. intervals between consecutive readings, raw, no origin taken out;
  3. everything but C, raw: event text, rng=, sections, unit lines of dumps;
  4. the engine's lines: raw, and which fields differ when they do;
  5. where the origin lies: reading minus vms, per run.
Also writes both chains of every run: n, raw h, canonical h (same FNV over the text with the clock from the run's own first reading). args: none"""
import gzip
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, __file__.rsplit("\\", 1)[0] if "\\" in __file__ else __file__.rsplit("/", 1)[0])
import AIForgeReplayRunner as rr
import scheduler_integrity_check as sic

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = Path(__file__).resolve().parent
CHAINS = HERE / "chains"
CHAINS.mkdir(exist_ok=True)
C = rr.CLOCK
RAWH = re.compile(r"^\[FORGE\] n=(\d+) h=([0-9a-f]+) (.*)$", re.S)
out = {"pairs": {}, "runs": {}}
logs = {}


def log(r):
    if r not in logs:
        logs[r] = sic.read_log(*rr.source_of(r))
    return logs[r]


def readings(lines):
    """every clock reading in the order of the log: forge fingerprints and dump headers"""
    v = []
    for s in lines:
        if s.startswith("[FORGE] ") or s.startswith("[FORGEDUMP] "):
            m = C.search(s)
            if m:
                v.append(int(m.group(1)))
    return v


def fields(s):
    return dict(sic.KV.findall(s))


for a, b, scen in (("R2", "R3", "M3"), ("P1", "R5", "L8"), ("R5", "R6", "L8 to n=889")):
    la, lb = log(a), log(b)
    ga, fa, da = rr.split(la)
    gb, fb, db = rr.split(lb)
    n = min(len(fa), len(fb))
    res = {"scenario": scen, "events_compared": n}
    # 1, 2: as many readings as both have, up to the stop
    last = int(RAWH.match(fb[n - 1] if len(fb) <= len(fa) else fa[n - 1]).group(1))
    fp_a = [int(C.search(x).group(1)) for x in fa[:n] if C.search(x)]
    fp_b = [int(C.search(x).group(1)) for x in fb[:n] if C.search(x)]
    common = sorted(set(da) & set(db))
    dump_a = {k: int(C.search(da[k][0]).group(1)) for k in common if C.search(da[k][0])}
    dump_b = {k: int(C.search(db[k][0]).group(1)) for k in common if C.search(db[k][0])}
    shifts = Counter(x - y for x, y in zip(fp_a, fp_b))
    shifts.update(dump_a[k] - dump_b[k] for k in dump_a)
    res["clock_readings"] = sum(shifts.values())
    res["shifts"] = {str(k): v for k, v in shifts.items()}
    ia = [q - p for p, q in zip(fp_a, fp_a[1:])]
    ib = [q - p for p, q in zip(fp_b, fp_b[1:])]
    res["intervals"] = len(ia)
    res["intervals_different_raw"] = sum(1 for x, y in zip(ia, ib) if x != y)
    res["interval_min_max"] = [min(ia), max(ia)]
    res["clock_goes_back"] = sum(1 for x in ia if x < 0)
    res["reading_max"] = max(fp_a + fp_b)
    # 3: everything but C, raw
    differs = Counter()
    text_equal = 0
    for x, y in zip(fa[:n], fb[:n]):
        mx, my = RAWH.match(x), RAWH.match(y)
        if mx.group(1) != my.group(1):
            differs["n"] += 1
        tx, ty = mx.group(3), my.group(3)
        if tx == ty:
            text_equal += 1
            continue
        dx, dy = fields(tx), fields(ty)
        for k in set(dx) | set(dy):
            if dx.get(k) != dy.get(k):
                differs[k] += 1
        if C.sub("", tx) != C.sub("", ty):
            differs["text_without_C"] += 1
    res["events_text_equal_raw"] = text_equal
    res["event_fields_differing_raw"] = dict(differs)
    res["fingerprints_compared"] = sum(1 for x in fa[:n] if " ev=fp " in x)
    fp_fields = Counter()
    for x, y in zip(fa[:n], fb[:n]):
        if " ev=fp " in x:
            dx, dy = fields(x), fields(y)
            for k in rr.SECTIONS:
                if k != "C" and dx.get(k) == dy.get(k) and k in dx:
                    fp_fields[k] += 1
            if dx.get("rng") == dy.get("rng"):
                fp_fields["rng"] += 1
    res["fingerprint_fields_equal_raw"] = dict(fp_fields)
    ul = 0
    ud = 0
    hd = Counter()
    for k in common:
        res_a, res_b = da[k], db[k]
        for i, (x, y) in enumerate(zip(res_a, res_b)):
            if x == y:
                ul += 1
                continue
            if C.sub("", x) == C.sub("", y):
                hd["only C"] += 1
            else:
                ud += 1
    res["dumps_compared"] = len(common)
    res["dump_lines_equal_raw"] = ul
    res["dump_lines_differ_only_in_C"] = hd["only C"]
    res["dump_lines_differ_otherwise"] = ud
    # 4: the engine's lines, raw: up to the stop when one run stopped
    pa = [s for s in rr.game_before(la, last)] if len(fa) != len(fb) else ga
    raw_a = [s for s in la if s.startswith("[AI")]
    raw_b = [s for s in lb if s.startswith("[AI")]
    limit = len(pa)
    kinds = Counter()
    other = 0
    for x, y in zip(raw_a[:limit], raw_b[:limit]):
        if x == y:
            continue
        if rr.MS.sub("", rr.SEP.sub("", x)) == rr.MS.sub("", rr.SEP.sub("", y)):
            kinds[x.split(" ", 1)[0]] += 1
        else:
            other += 1
    res["game_lines"] = limit
    res["game_lines_differ_raw_only_in_real_time_fields"] = dict(kinds)
    res["game_lines_differ_otherwise"] = other
    res["other_log_lines"] = [sum(1 for s in la if not s.startswith("[")), sum(1 for s in lb if not s.startswith("["))]
    out["pairs"][f"{a}-{b}"] = res
    print(a, b, json.dumps(res, ensure_ascii=False))

# 5 and the two chains
for r in ("P1", "R2", "R3", "R5", "R6"):
    lines = log(r)
    _, f, d = rr.split(lines)
    canon, _ = rr.relative_clock(f, d)
    h = 0xCBF29CE484222325
    rows = ["n\traw_h\tcanonical_h"]
    for x, y in zip(f, canon):
        m = RAWH.match(x)
        text = y.split(" ", 2)[2]
        h = sic.chain_step(h, text)
        rows.append(f"{m.group(1)}\t{m.group(2)}\t{h:x}")
    with gzip.open(CHAINS / f"chain_{r}.tsv.gz", "wt", encoding="utf-8", compresslevel=9, newline="\n") as z:
        z.write("\n".join(rows) + "\n")
    v = sic.check(lines)
    res = next(s for s in lines if s.startswith("[AIRESULT]"))
    vms = int(fields(res)["vms"])
    cs = [int(C.search(x).group(1)) for x in f if C.search(x)]
    out["runs"][r] = {"events": len(f), "raw_chain_last": rows[-1].split("\t")[1], "canonical_chain_last": rows[-1].split("\t")[2], "chain_violations": v["violations"], "first_reading": cs[0], "last_reading": cs[-1],
                      "vms": vms, "last_reading_minus_vms": cs[-1] - vms, "first_reading_after_start": cs[0] - (cs[-1] - vms)}
    print(r, json.dumps(out["runs"][r], ensure_ascii=False))
(HERE / "WP1_FINAL_CHECK.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8-sig")
