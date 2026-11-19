"""FIRST CONTACT SURVIVAL V0, stage 4: D0 against the rule, one seed at a time, in the short window (read only).
Equal lines up to the first change; every [FCSACT]: executed? where did the walk end? seen at the next player turn? alive after it? And per turn: hostile in the ranks, player casualties, attacks, TU spent, flights, decisions per unit.
Usage: evalfc.py <out tsv> <d0 dir> <rule dir> [<d0 dir> <rule dir>]..."""
import csv
import gzip
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
KV = re.compile(r"(\w+)=(\S+)")
TAGS = ("[AIDECIDE]", "[AIEXEC]", "[AICASUALTY]", "[AIEVENT]", "[AISTATE]")
ATTACK = {"6", "7", "8", "9"}
LAST = 4


def read(d):
    with gzip.open(Path(d) / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        return [ln.rstrip("\n").split("\t")[-1] for ln in f]


def stats(lines):
    r = dict(cas={}, pcas={}, att=Counter(), tu=Counter(), flee=Counter(), dec=Counter(), per=Counter(), start=0, rethink=Counter(), react=Counter(), fin=None)
    cur = None
    for s in lines:
        if s.startswith("[AISTATE] before"):
            k = dict(KV.findall(s))
            if k.get("turn") == "1" and k.get("faction") == "1":
                r["start"] += 1
        elif s.startswith("[AIDECIDE] "):
            k = dict(KV.findall(s))
            cur = k
            t = int(k["turn"])
            if k["side"] == "1" and t <= LAST:
                r["dec"][t] += 1
                r["per"][(t, k["unit"])] += 1
                if k["act"] in ATTACK:
                    r["att"][t] += 1
                if k["mode"] == "3" and k["act"] == "2":
                    r["flee"][t] += 1
                if k["act"] == "15":
                    r["rethink"][t] += 1
        elif s.startswith("[AIEXEC] ") and cur and cur["side"] == "1":
            try:
                x = json.loads(s[9:])
            except ValueError:
                continue
            t = int(cur["turn"])
            if t <= LAST:
                r["tu"][t] += x.get("spent") or 0
        elif s.startswith("[AIEVENT] "):
            k = dict(KV.findall(s))
            if k.get("what") == "reaction" and int(k.get("turn", 99)) <= LAST:
                r["react"][(int(k["turn"]), k.get("side"))] += 1
        elif s.startswith("[AICASUALTY] "):
            k = dict(KV.findall(s))
            t = int(k["turn"])
            if t > LAST:
                continue
            (r["cas"] if k.get("vfaction") == "1" else r["pcas"]).setdefault(k["victim"], (t, k["side"], k.get("killer"), k.get("kfaction")))
        elif s.startswith("[AIRESULT]"):
            r["fin"] = dict(KV.findall(s))
    return r


def alive(st, t, side):
    """in the ranks at the end of (turn t, side): 1 the hostile turn, 0 the player's turn; the player moves first within a turn"""
    lost = sum(1 for (a, b, _, _) in st["cas"].values() if a < t or (a == t and (b == "0" or side == "1")))
    return st["start"] - lost


rows = []
args = sys.argv[2:]
for i in range(0, len(args), 2):
    a_dir, b_dir = args[i], args[i + 1]
    a, b = read(a_dir), read(b_dir)
    print(f"== {Path(b_dir).name} against {Path(a_dir).name}")
    fa = [s for s in a if s.startswith(TAGS)]
    fb = [s for s in b if s.startswith(TAGS)]
    n = next((j for j in range(min(len(fa), len(fb))) if fa[j] != fb[j]), None)
    acts = [dict(KV.findall(s)) for s in b if s.startswith("[FCSACT]")]
    print(f"  equal lines before the first difference: {n} of {len(fb)}; first [FCSACT] of {len(acts)} at turn {acts[0]['turn'] if acts else '-'}, unit {acts[0]['unit'] if acts else '-'}")
    if n is not None:
        print("    D0  :", fa[n][:210])
        print("    rule:", fb[n][:210])
    # did the first difference sit right at a changed decision?
    sa, sb = stats(a), stats(b)
    # each act: the executed walk and the fate
    idx = {}
    for j, s in enumerate(b):
        if s.startswith("[FCSACT]"):
            k = dict(KV.findall(s))
            exe = None
            dec = None
            for t in b[j + 1:j + 400]:
                if t.startswith("[AIDECIDE] ") and dec is None:
                    d = dict(KV.findall(t))
                    if d["unit"] == k["unit"]:
                        dec = d
                elif t.startswith("[AIEXEC] ") and dec is not None:
                    try:
                        exe = json.loads(t[9:])
                    except ValueError:
                        exe = {}
                    break
            turn = int(k["turn"])
            st = None
            for t in b[j:]:
                if t.startswith(f"[AISTATE] pstart turn={turn + 1} unit={k['unit']} "):
                    st = dict(KV.findall(t))
                    break
            fate = sb["cas"].get(k["unit"])
            row = dict(battle=Path(b_dir).name, turn=turn, unit=k["unit"], tu=k["tu"], frm=k["from"], dest=k["dest"], here=k["here"], there=k["there"], known=k["known"], new=k["new"], checked=k["checked"],
                       to=dec["to"] if dec else "-", act=dec["act"] if dec else "-", mode=dec["mode"] if dec else "-", walk=(exe or {}).get("walk", "-"), pos=(exe or {}).get("pos", "-"), spent=(exe or {}).get("spent", "-"),
                       seenby_next=st.get("seenby", "-") if st else "-", lost=f"t{fate[0]}s{fate[1]}" if fate else "-", lost_by=fate[2] if fate else "-")
            rows.append(row)
            print("   ", row["turn"], row["unit"], "tu" + row["tu"], row["frm"], "dest", row["dest"], "lines", row["here"] + ">" + row["there"], "new", row["new"], "| to", row["to"], "a" + row["act"], "m" + row["mode"], "walk", row["walk"], "end", row["pos"], "spent", row["spent"], "seenNext", row["seenby_next"], "lost", row["lost"], row["lost_by"])
    print("  turn:             " + " ".join(f"t{t:<7}" for t in range(1, LAST + 1)))
    for label, f in (("ranks after enemy", lambda s, t: alive(s, t, "1")), ("ranks after player", lambda s, t: alive(s, t, "0")), ("attacks", lambda s, t: s["att"][t]), ("flights", lambda s, t: s["flee"][t]), ("decisions", lambda s, t: s["dec"][t]), ("TU spent", lambda s, t: s["tu"][t]),
                     ("player lost", lambda s, t: sum(1 for x in s["pcas"].values() if x[0] == t)), ("reactions on own turn", lambda s, t: s["react"][(t, "1")])):
        print(f"  {label:22} D0 " + " ".join(f"{f(sa, t):<4}" for t in range(1, LAST + 1)) + "  rule " + " ".join(f"{f(sb, t):<4}" for t in range(1, LAST + 1)))
    print("  max decisions per unit per turn: D0", max(sa["per"].values()), "rule", max(sb["per"].values()), "; hostile start", sa["start"], sb["start"])
if rows:
    with open(sys.argv[1], "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, list(rows[0].keys()), delimiter="\t")
        w.writeheader()
        w.writerows(rows)
