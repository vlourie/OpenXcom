"""REINFORCE member table at the moment of assignment and every later REINFORCE turn: what the side could know, what the unit did. Read only.
Also classifies every standing decision by its cause. Usage: members.py run ...; writes members.tsv, stand.tsv."""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read, tup  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
ATT = set(range(4, 21))
HERE = Path(__file__).parent


def d2(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def load(run):
    R = dict(orders={}, dec=defaultdict(list), state={}, contact={}, rec={}, hive=defaultdict(list), turns=set())
    for s in read(run):
        if s.startswith("[HIVECC]"):
            k = kv(s)
            if k["event"] == "ORDER":
                R["orders"][(int(k["turn"]), int(k["unit"]))] = k
            elif k["event"] == "CONTACT":
                R["contact"][(int(k["turn"]), k["target"])] = k
        elif s.startswith("[AIDECIDE]"):
            k = kv(s)
            if k["side"] == "1":
                R["dec"][(int(k["turn"]), int(k["unit"]))].append(k)
                R["turns"].add(int(k["turn"]))
        elif s.startswith("[AISTATE] aistart"):
            k = kv(s)
            R["state"][(int(k["turn"]), int(k["unit"]))] = k
        elif s.startswith("[AIREC]"):
            try:
                j = json.loads(s[8:])
            except ValueError:
                continue
            if j["side"] == 1:
                R["rec"][(j["turn"], j["unit"], j["n"])] = j
        elif s.startswith("[HIVEORD]"):
            k = kv(s)
            if k.get("state") in ("COMPLETED", "VALIDATED"):
                R["hive"][(int(k["turn"]), int(k["unit"]))].append(k)
    return R


def fate(ds):
    if any(int(d["act"]) in ATT for d in ds):
        return "attack"
    if any(d["act"] == "2" for d in ds):
        return "walk"
    return "stand"


def cause(R, t, u, d, o):
    """The reason of one decision with no action or an escape walk."""
    j = R["rec"].get((t, u, int(d["n"]))) or {}
    b = j.get("base") or {}
    odds = (b.get("reason") or {}).get("odds") or []
    dice = odds[-1]["mode"] if odds else None
    prev_arrived = any(k["state"] == "COMPLETED" for k in R["hive"].get((t, u), []))
    props = (b.get("reason") or {}).get("props") or []
    return dice, prev_arrived, b.get("src"), len(props)


def main():
    rows, stand = [], []
    tally = Counter()
    for run in sys.argv[1:]:
        R = load(run)
        for (t, u), o in sorted(R["orders"].items()):
            if o["role"] != "REINFORCE":
                continue
            st = R["state"].get((t, u), {})
            ds = R["dec"].get((t, u), [])
            nxt = R["dec"].get((t + 1, u), [])
            c = o["contact"]
            ct = R["contact"].get((t, c), {})
            cp = tup(ct["pos"]) if ct.get("pos") else None
            at = tup(o["at"])
            tgt = tup(o["target"]) if o.get("target") else at
            d_now = d2(at, cp) if cp else -1
            d_tgt = d2(tgt, cp) if cp else -1
            cost = int(o.get("cost", 0) or 0)
            shot = int(o.get("shot", 0) or 0)
            tu = int(st.get("tu", o.get("tu", 0)) or 0)
            tumax = int(st.get("tumax", tu) or tu)
            prev = R["dec"].get((t - 1, u), [])
            prev_mode = prev[-1]["mode"] if prev else "-"
            prev_fate = fate(prev) if prev else "-"
            hit_c = sum(1 for x in ds if int(x["act"]) in ATT and x["aim"] == c)
            hit_o = sum(1 for x in ds if int(x["act"]) in ATT and x["aim"] != c)
            hit_c1 = sum(1 for x in nxt if int(x["act"]) in ATT and x["aim"] == c)
            hit_o1 = sum(1 for x in nxt if int(x["act"]) in ATT and x["aim"] != c)
            rows.append([run, o["squad"], t, u, o["kind"], c, d_now, d_tgt, cost, shot, tu, tumax, st.get("hp", "?"), st.get("morale", "?"), st.get("known", "?"), st.get("spare", "?"), st.get("weapon", "?").replace("STR_", ""), prev_mode, prev_fate, fate(ds), "/".join(x["mode"] for x in ds), "/".join(x["act"] for x in ds), hit_c, hit_o, hit_c1, hit_o1])
        # every decision of the side that does nothing with TU left
        for (t, u), ds in R["dec"].items():
            o = R["orders"].get((t, u))
            label = (o["role"] + ":" + o["kind"]) if o else "no_coord_order"
            for d in ds:
                if d["act"] != "0" or d["mode"] != "3":
                    continue
                dice, arrived, src, nprops = cause(R, t, u, d, o)
                tu = int(d["tu"])
                st = R["state"].get((t, u), {})
                tumax = int(st.get("tumax", tu) or tu)
                why = ("arrived_then_hold" if arrived else "dice_escape" if dice == 3 else "kept_escape" if dice is None else "fallback")
                tally[(run, label, why)] += 1
                tally[(run, "TOTAL", why)] += 1
                stand.append([run, t, u, label, why, dice, src, tu, tumax, d["from"], d["seen"] if "seen" in d else "", d["aim"]])
    with open(HERE / "members.tsv", "w", encoding="utf-8-sig") as f:
        f.write("run squad turn unit kind contact d_now d_tgt cost shot tu tumax hp morale known spare weapon prev_mode prev_fate fate modes acts att_c att_o att_c_next att_o_next".replace(" ", "\t") + "\n")
        for r in rows:
            f.write("\t".join(str(x) for x in r) + "\n")
    with open(HERE / "stand.tsv", "w", encoding="utf-8-sig") as f:
        f.write("run turn unit order why dice src tu tumax from seen aim".replace(" ", "\t") + "\n")
        for r in stand:
            f.write("\t".join(str(x) for x in r) + "\n")
    runs = sys.argv[1:]
    labels = sorted({k[1] for k in tally})
    whys = ["arrived_then_hold", "fallback", "kept_escape", "dice_escape"]
    for run in runs:
        print("==", run)
        for lab in labels:
            vals = [tally[(run, lab, w)] for w in whys]
            if sum(vals):
                print(f"{lab:24s}", "\t".join(f"{w}={v}" for w, v in zip(whys, vals)))


if __name__ == "__main__":
    main()
