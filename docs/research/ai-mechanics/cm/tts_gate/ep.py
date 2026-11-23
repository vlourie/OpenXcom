"""NATURAL GATE: one episode in full, from the raw log. Args: battle, turn, B, A, T. Every line of the turn about the three, B's list and near cells, T's history with this weapon (read only)."""
import gzip
import io
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import gate_lib as G

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ARC = "E:/OXCE_AIWorker/battles_archive/side_turn_scheduler_pilot_2026-10-30/res_scpa.zip"
name, turn, B, A, T = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])
with zipfile.ZipFile(ARC) as z:
    raw = z.read(f"out/scpa_D_{name}/openxcom.log.gz")
L = [s.rstrip("\n").split("\t")[-1] for s in gzip.open(io.BytesIO(raw), "rt", encoding="utf-8", errors="replace")]
b = G.Battle(L)
ids = {B: "B", A: "A", T: "T"}
print("== timeline turn", turn)
for i, s in enumerate(L):
    if s.startswith("[AIEXEC]") or s.startswith("[AIREC]"):
        continue
    if s.startswith("[AICAND]"):
        continue
    k = G.kv(s) if s.startswith(("[AISTATE]", "[AICASUALTY]", "[AIDECIDE]")) else None
    if not k or str(k.get("turn")) != str(turn):
        continue
    u = int(k.get("unit") or k.get("victim") or -1)
    if u in ids or int(k.get("killer", -1)) in ids:
        print(i, ids.get(u, "?"), s[:235])
    if s.startswith("[AIDECIDE]") and u in (B, A):
        rec = [d for d in b.by_unit[u] if d["turn"] == turn and d["i"] > i][:1]
        e = b.exec.get(rec[0]["rec"]) if rec else None
        if e:
            print("      exec", {x: e.get(x) for x in ("pos", "tu", "spent", "seen", "spotted", "dmg", "stunned", "downed", "fdmg", "fdowned", "hp")})
print("\n== first list of B in the turn with T")
for d in b.by_unit[B]:
    if d["turn"] != turn or not d["acts"]:
        continue
    acts = b.acts(d["acts"])
    print("rec", d["rec"], "n", d["n"], "pos", d["pos"], "tu", d["tu"], "kneel", d["kneel"], "src", d["src"], "t", d["t"], "to", d["to"])
    for c in acts:
        if c.get("k") == "a" and c.get("u") == T:
            print("   ", c)
    print("   lof 1 targets:", sorted({c.get("u") for c in acts if c.get("k") == "a" and c.get("lof") == 1 and c.get("t") in G.SHOT}))
    mv = b.moves(d["moves"])
    p = d["pos"]
    print("   near cells:", sorted(((c, t) for c, t in mv.items() if G.cheb(c, p) <= 3 and c[2] == p[2]), key=lambda x: x[1])[:40])
    i = d["i"]
    print("   who stands near the lane:", [(u, a[0], a[1], round(G.lane(a[0], p, tuple(next(c["to"] for c in acts if c.get("u") == T)))[1] ** 0.5, 2)) for u, a in b.comrades(i, B).items() if G.near_line(a[0], p, tuple(next(c["to"] for c in acts if c.get("u") == T)))] if any(c.get("u") == T for c in acts) else None)
    break
print("\n== all lists of A on its cell in the turn")
for d in b.by_unit.get(A, []):
    if d["turn"] != turn or not d["acts"]:
        continue
    s = G.shots_by_target(b.acts(d["acts"]))
    print("rec", d["rec"], "n", d["n"], "pos", d["pos"], "tu", d["tu"], "t", d["t"], "to", d["to"], "src", d["src"], "T:", s.get(T), "with a line:", [(u, x["tu"], x["p"], x["d"]) for u, x in s.items() if x["lof"]])
print("\n== B's own list through the battle around the turn: did the line to T ever exist from this cell")
p0 = None
for d in b.by_unit[B]:
    if d["turn"] == turn:
        p0 = d["pos"]
        break
for d in b.by_unit[B]:
    if abs(d["turn"] - turn) <= 2 and d["acts"]:
        s = G.shots_by_target(b.acts(d["acts"])).get(T)
        if s:
            print(" turn", d["turn"], "n", d["n"], "pos", d["pos"], "tu", d["tu"], "T at", s["to"], "lof", s["lof"], "d", s["d"], "w", s["w"], "tu", s["tu"], "did t", d["t"], "to", d["to"], "dmg", (b.exec.get(d["rec"]) or {}).get("dmg"))
print("\n== shots at T in the battle by this side")
for d in b.dec:
    if d["side"] == 1 and d["t"] in G.SHOT and G.attack_target(b, d) == T:
        e = b.exec.get(d["rec"]) or {}
        print(" turn", d["turn"], "unit", d["unit"], "from", d["pos"], "mode", d["t"], d["w"], "dmg", e.get("dmg"), "stun", e.get("stunned"), "fdmg", e.get("fdmg"), "downed", e.get("downed"))
print("\n== T state")
for s in L:
    if s.startswith("[AISTATE]"):
        k = G.kv(s)
        if k.get("unit") == str(T) and abs(int(k.get("turn", 0)) - turn) <= 1:
            print(s[:210])
for s in L:
    if s.startswith("[AICASUALTY]") and f"victim={T} " in s:
        print(s[:200])
