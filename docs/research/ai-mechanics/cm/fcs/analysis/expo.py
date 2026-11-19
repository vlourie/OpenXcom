"""FIRST CONTACT SURVIVAL, stage 1: was the fallen unit already under the killer's eyes when the phase began, and did the killer have to move (read only)?
From the [AISTATE] snapshots at the start of each side's turn: for the loss in a player turn the snapshot of that turn's start; for the loss inside the hostile turn the snapshot of its start.
Usage: expo.py <tsv in> <tsv out> <dir with battles>"""
import csv
import gzip
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
KV = re.compile(r"(\w+)=(\S+)")
POS = re.compile(r"pos=\((-?\d+),(-?\d+),(-?\d+)\)")


def snaps(d):
    out = defaultdict(dict)  # (when, turn) -> unit -> state
    with gzip.open(Path(d) / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        for ln in f:
            s = ln.rstrip("\n").split("\t")[-1]
            if s.startswith("[AISTATE] "):
                w = s.split()[1]
                k = dict(KV.findall(s))
                m = POS.search(s)
                k["p"] = tuple(int(x) for x in m.groups()) if m else None
                out[(w, int(k["turn"]))][k["unit"]] = k
    return out


rows = list(csv.DictReader(open(sys.argv[1], encoding="utf-8-sig"), delimiter="\t"))
cache = {}
res = []
print_kinds = None
for r in rows:
    b = r["battle"]
    if b not in cache:
        cache[b] = snaps(Path(sys.argv[3]) / b)
    sn = cache[b]
    if print_kinds is None:
        print_kinds = Counter(k[0] for k in sn)
        print("snapshots:", print_kinds.most_common())
    t = int(r["turn"])
    # the snapshot at the start of the phase the unit fell in
    when = ("before", "pstart") if r["side"] == "0" else ("aistart",)
    st = None
    for w in when:
        st = sn.get((w, t))
        if st:
            used = w
            break
    if not st:
        r.update(snap="-", v_seenby="-", k_sees="-", k_pos="-", k_d0="-", k_moved="-", v_near="-", v_known="-", v_threat="-", v_tu="-")
        res.append(r)
        continue
    v = st.get(r["victim"], {})
    k = st.get(r["killer"], {})
    vp, kp = v.get("p"), k.get("p")
    d0 = round(((vp[0] - kp[0]) ** 2 + (vp[1] - kp[1]) ** 2) ** 0.5) if vp and kp else "-"
    sees = k.get("sees", "-").split(",") if k else []
    pos = tuple(int(x) for x in r["pos"].split(",")) if r["pos"] else None
    r.update(snap=used, v_seenby=v.get("seenby", "-"), k_sees=int(r["victim"] in sees), k_pos=",".join(map(str, kp)) if kp else "-", k_d0=d0, v_near=v.get("near", "-"), v_known=v.get("known", "-"),
             v_threat=v.get("threat", "-"), v_tu=v.get("tu", "-"), v_moved_in_phase=int(bool(vp) and vp != pos))
    res.append(r)
cols = list(rows[0].keys())
for c in ("v_moved_in_phase",):
    if c not in cols:
        cols.append(c)
with open(sys.argv[2], "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, cols, delimiter="\t", extrasaction="ignore")
    w.writeheader()
    w.writerows(res)

first = {}
for r in res:
    first.setdefault((r["battle"], r["victim"]), r)
u = list(first.values())
print("units lost", len(u), "of which never acted", sum(int(r["own_decisions"]) == 0 for r in u))
print("by battle and window:")
for b in sorted({r["battle"] for r in u}):
    x = [r for r in u if r["battle"] == b]
    never = sum(int(r["own_decisions"]) == 0 for r in x)
    t1 = [r for r in x if r["turn"] == "1"]
    w2 = [r for r in x if int(r["turn"]) == 1 or (r["turn"] == "2" and r["side"] == "0")]
    print(f"  {b}: lost {len(x)}, never acted {never}; turn 1 {len(t1)} (never acted {sum(int(r['own_decisions']) == 0 for r in t1)}); through the player's turn 2: {len(w2)} (never acted {sum(int(r['own_decisions']) == 0 for r in w2)})")
acted = [r for r in u if int(r["own_decisions"]) > 0]
print("acted units:", len(acted))
print(" at the phase start, the killer already saw the victim:", Counter(str(r.get("k_sees")) for r in acted).most_common())
print(" player-turn losses, killer saw at the start of the turn:", Counter(str(r.get("k_sees")) for r in acted if r["side"] == "0").most_common())
print(" player-turn losses, last own decision mode/act:", Counter((r["last_mode"], r["last_act"]) for r in acted if r["side"] == "0").most_common())
print(" player-turn losses, TU left at the loss 0-6 / more:", Counter(int(r["tu_at_loss"]) <= 6 for r in acted if r["side"] == "0").most_common())
print(" own-turn losses, cause:", Counter((r["cause"], r["actor_is_victim"]) for r in acted if r["side"] == "1").most_common())
print()
for r in u:
    if int(r["own_decisions"]) > 0 and r["side"] == "0" and r["turn"] in ("2", "3"):
        print(r["battle"][6:], "t" + r["turn"], r["victim"], r["type"][5:12], "at", r["pos"], "by", r["killer"], "from", r.get("k_pos"), "d" + str(r.get("k_d0")), ">d" + r["dist"], "sawAtStart" + str(r.get("k_sees")), "seenbyStart" + str(r.get("v_seenby")),
              "tuL" + r["tu_at_loss"], "m" + r["last_mode"], "a" + r["last_act"], "kSeen" + r["killer_seen_at_last"])
