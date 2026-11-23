"""Per assignment, the same count for CC and RI: from ASSIGN to REINFORCE to its end, attacks on the contact by the units that held a help order in it, first attack delay, the units lost. Attacks of the turn of the order and of later turns of the role count alike (a unit keeps the order it holds, so a turn without an ORDER record is not a turn without one). Read only."""
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
ATT = set(range(4, 21))
LAST = 8


def ana(run):
    role = {}
    spans = []
    orders = defaultdict(set)
    attacks = defaultdict(list)
    fell = {}
    for s in read(run):
        if s.startswith("[HIVECC]"):
            k = kv(s)
            e = k["event"]
            if int(k.get("turn", 0)) > LAST:
                continue
            if e == "ASSIGN":
                sq = k["squad"]
                if k["from"] == "REINFORCE" and sq in role:
                    role[sq]["to"] = int(k["turn"])
                    role[sq]["end"] = k["why"]
                    spans.append(role.pop(sq))
                if k["to"] == "REINFORCE":
                    role[sq] = dict(squad=sq, frm=int(k["turn"]), to=None, contact=k["contact"], why=k["why"], end="-")
            elif e == "ORDER" and k["role"] == "REINFORCE" and k["squad"] in role:
                orders[(k["squad"], role[k["squad"]]["frm"])].add(k["unit"])
        elif s.startswith("[AIDECIDE]"):
            k = kv(s)
            if k["side"] == "1" and int(k["act"]) in ATT and int(k["turn"]) <= LAST:
                attacks[k["unit"]].append((int(k["turn"]), k["aim"]))
        elif s.startswith("[AICASUALTY]"):
            k = kv(s)
            if k.get("vfaction") == "1":
                fell.setdefault(k["victim"], int(k["turn"]))
    spans.extend(role.values())
    rows = []
    for a in spans:
        hi = a["to"] if a["to"] else LAST + 1
        us = orders[(a["squad"], a["frm"])]
        hit = [t for u in us for t, aim in attacks[u] if a["frm"] <= t < hi and aim == a["contact"]]
        oth = [t for u in us for t, aim in attacks[u] if a["frm"] <= t < hi and aim != a["contact"]]
        lost = sum(u in us and a["frm"] <= t <= hi for u, t in fell.items())
        rows.append(dict(a, units=len(us), hit=len(hit), other=len(oth), delay=min(hit) - a["frm"] if hit else None, lost=lost))
    return rows


for run in sys.argv[1:]:
    rows = ana(run)
    fresh = [r for r in rows if not r["why"].startswith("contact_not_in_sight")]
    print(run, "assign", len(rows), "fresh", len(fresh), "with_units", sum(r["units"] > 0 for r in rows), "with_hit", sum(r["hit"] > 0 for r in rows), "hits", sum(r["hit"] for r in rows), "other", sum(r["other"] for r in rows), "lost", sum(r["lost"] for r in rows), "delays", [r["delay"] for r in rows])
    for r in rows:
        print("   sq", r["squad"], "t", r["frm"], "-", r["to"], "c", r["contact"], "units", r["units"], "hit", r["hit"], "other", r["other"], "delay", r["delay"], "lost", r["lost"], r["why"], "->", r["end"])
