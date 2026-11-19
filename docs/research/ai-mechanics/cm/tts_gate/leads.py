"""NATURAL GATE, read only: the leads with a dangerous target. For every decision of B in the turn: cell, TU, lof to T, the shot; where A stood. T's casualties caused (by killer=T), B's attacks with their targets. Whether the comrade ever left while B stood on that cell.
Openings: all attacks at the first decision after an opening, damage over any target. Args: zip, cands.jsonl, then battle|turn|B|A|T."""
import gzip
import io
import json
import sys
import zipfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import gate_lib as G

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ATT = {5, 6, 7, 8, 9, 10, 11, 12}
z = zipfile.ZipFile(sys.argv[1])
for q in sys.argv[3:]:
    name, turn, B, A, T = q.split("|")
    turn, B, A, T = int(turn), int(B), int(A), int(T)
    raw = z.read(f"out/scpa_D_{name}/openxcom.log.gz")
    L = [s.rstrip("\n").split("\t")[-1] for s in gzip.open(io.BytesIO(raw), "rt", encoding="utf-8", errors="replace")]
    b = G.Battle(L)
    print(f"\n=== {name} turn {turn} B {B} A {A} T {T}")
    for d in b.by_unit.get(B, []):
        if d["turn"] != turn or d["side"] != 1:
            continue
        sh = G.shots_by_target(b.acts(d["acts"])) if d["acts"] else {}
        e = b.exec.get(d["rec"]) or {}
        o = sh.get(T)
        ap = b.at(A, d["i"])
        others = [(u, x["tu"], x["d"]) for u, x in sh.items() if x["lof"] and x["tu"] <= d["tu"]]
        print(" line", d["i"], "B", d["pos"], "kneel", d["kneel"], "tu", d["tu"], "T", (o["to"], "lof", o["lof"], "tu", o["tu"], "p", o["p"], "d", o["d"]) if o else None, "| A at", ap[0] if ap else None, "tu", ap[1] if ap else None, "| other lines", others[:4], "| did t", d["t"], "src", d["src"], "to", d["to"], "at", G.attack_target(b, d) if d["t"] in ATT else None, "sp", e.get("spent"), "dmg", e.get("dmg"), "f", e.get("fdmg"))
    for d in b.by_unit.get(A, []):
        if d["turn"] == turn and d["side"] == 1:
            e = b.exec.get(d["rec"]) or {}
            print(" A line", d["i"], d["pos"], "tu", d["tu"], "did t", d["t"], "src", d["src"], "to", d["to"], "at", G.attack_target(b, d) if d["t"] in ATT else None, "sp", e.get("spent"), "dmg", e.get("dmg"), "f", e.get("fdmg"))
    for s in L:
        if s.startswith("[AICASUALTY]") and f"killer={T} " in s:
            k = G.kv(s)
            if turn - 1 <= int(k["turn"]) <= turn + 2:
                print(" T's casualty: turn", k["turn"], "side", k["side"], "victim", k["victim"], k["how"], k.get("weapon"))
    hp = []
    for s in L:
        if s.startswith("[AISTATE]") and f" unit={T} " in s:
            k = G.kv(s)
            if turn <= int(k.get("turn", -1)) <= turn + 2:
                hp.append((s.split(" ")[1], k.get("turn"), k.get("hp"), k.get("wounds"), k.get("pos"), k.get("weapon")))
    print(" T:", hp[:6])

# all first decisions at an opening with TU, every target
o = Counter()
for s in Path(sys.argv[2]).open(encoding="utf-8"):
    r = json.loads(s)
    for c in r["cands"]:
        for f in c["flips"]:
            if f["after"] and f["turn"] == c["turn"] and any(not x["out"] and x["now"] != x["was"] for x in f["comrades"]) and f["tu"] >= f["shot"]["tu"]:
                d = f["did"]
                if d["t"] in ATT:
                    o["attacks"] += 1
                    o["dmg"] += d["dmg"] or 0
                    o["fdmg"] += d["fdmg"] or 0
                    o["wounding"] += 1 if (d["dmg"] or 0) > 0 else 0
                break
print("\nfirst decision at an opening, any target:", dict(o))
