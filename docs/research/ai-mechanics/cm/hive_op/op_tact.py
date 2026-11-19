"""COORDINATED OPERATION, phase C: the tactical part, kept apart from the functional chain. For the active runs and their base: the target's health and place at each AI turn, fates of the operation's two fighters, what they did and hurt on the operation's turns and the turn after, how the target's side killed a fighter (the bot's decisions before it), deferred charges, the same fighters and target in the base. FAIR lines of the headquarters by kind; spent over TU of the fighters. Read only."""
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
PAIRS = [("op1_OA_M3_s1", "op2_OO_M3_s1"), ("op4_OA_M3_s1", "op2_OO_M3_s1"), ("op5_OG_M3_s1", "op2_OO_M3_s1"), ("op6_OG_M3_s2", "scpa_D_M3_s2")]


def decisions(L):
    out = []
    recs = {}
    cur = None
    for s in L:
        if s.startswith("[AIDECIDE]"):
            cur = kv(s)
            out.append(cur)
        elif s.startswith("[AIREC]") and cur:
            try:
                j = json.loads(s[8:])
                cur["src"] = (j.get("base") or {}).get("src")
                recs[j["rec"]] = cur
            except ValueError:
                pass
        elif s.startswith("[AIEXEC]"):
            try:
                j = json.loads(s[9:])
            except ValueError:
                continue
            d = recs.get(j.get("rec"))
            if d:
                d["exec"] = j
    return out


def track(L, unit, name):
    rows = []
    for s in L:
        if s.startswith("[AISTATE] aistart"):
            k = kv(s)
            if k.get("unit") == unit:
                rows.append(f"t{k['turn']} {k['pos']} dir{k['dir']} hp{k['hp']}")
    print(f"   {name} {unit} at aistart:", "; ".join(rows))
    for s in L:
        if s.startswith("[AICASUALTY]"):
            k = kv(s)
            if k.get("victim") == unit and k.get("how") == "dead":
                print(f"     dead: t{k['turn']} side {k['side']} at {k.get('pos')} tu {k.get('tu')} seenby {k.get('seenby')} by {k.get('killer')} {k.get('weapon')} dist {k.get('dist')} hit {k.get('hit')}")


def blows(D, unit, t0, t1):
    rows = []
    for d in D:
        if d["unit"] == unit and t0 <= int(d["turn"]) <= t1:
            e = d.get("exec") or {}
            if e.get("dmg"):
                rows.append(f"t{d['turn']} {d['from']}>{d['to']} aim {d['aim']} src {d.get('src')} spent {e.get('spent')} dmg {e.get('dmg')}")
    return rows


for run, base in PAIRS:
    L, B = read(run), read(base)
    D, DB = decisions(L), decisions(B)
    print("=====", run, "base", base)
    ops = [kv(s) for s in L if s.startswith("[HIVEOP] event=ASSIGN")]
    prop = next(kv(s) for s in L if s.startswith("[HIVEOP] event=PROPOSED"))
    res = next(s for s in L if s.startswith("[HIVEOP] event=RESULT"))
    print("  ", res[9:220])
    target = prop["target"]
    stage = int(ops[0]["turn"])
    for tag, LL in ((run, L), (base, B)):
        print("  --", tag)
        track(LL, target, "target")
        for o in ops:
            track(LL, o["unit"], "fighter")
    for o in ops:
        print("   active blows", o["unit"], blows(D, o["unit"], stage, stage + 3))
        print("   base   blows", o["unit"], blows(DB, o["unit"], stage, stage + 3))
    print("   deferred:", [s[9:130] for s in L if s.startswith("[HIVEOP] event=DEFER")])
    print("   diverted:", Counter(kv(s)["unit"] for s in L if s.startswith("[HIVEOP] event=DIVERT")))
    print("   released/recell:", [s[9:110] for s in L if s.startswith(("[HIVEOP] event=RELEASED", "[HIVEOP] event=RECELL"))])
    fair = Counter()
    for s in L:
        if s.startswith("[HIVEFAIR]"):
            k = kv(s)
            fair[tuple(sorted((a, b) for a, b in k.items() if a in ("event", "kind", "why", "ok", "bad", "viol")))] += 1
    print("   HIVEFAIR kinds:", dict(fair))
    sample = [s[:170] for s in L if s.startswith("[HIVEFAIR]")][:2]
    print("   HIVEFAIR sample:", sample)
    ids = {o["unit"] for o in ops}
    over = [(d["turn"], d["unit"], d["tu"], d["exec"]["spent"]) for d in D if d["unit"] in ids and d.get("exec") and d["exec"].get("spent", 0) > int(d["tu"])]
    print("   fighters spent>tu:", over)
    bot = [f"t{d['turn']} {d['from']} tu{d['tu']} mode{d['mode']} act{d['act']} to{d['to']} aim{d['aim']} dmg{(d.get('exec') or {}).get('dmg')}" for d in D if d["unit"] == target and int(d["turn"]) in (stage + 1,) and d.get("side") == "0"]
    print("   bot target on the player's next turn:", bot[:12])
    for tag, LL in ((run, L), (base, B)):
        states = [kv(s) for s in LL if s.startswith("[AISTATE] aistart")]
        by = {}
        for k in states:
            by.setdefault(int(k["turn"]), []).append(k)
        last = max(t for t in by if t <= 8)
        alive = [k for k in by[last] if k.get("faction") == "1" and int(k.get("status", 0)) < 6]
        pl = [k for k in by[last] if k.get("faction") == "0" and int(k.get("status", 0)) < 6]
        hp = sum(int(k["hp"].split("/")[0]) for k in pl)
        print(f"   {tag}: aistart t{last}: AI alive {len(alive)}, player's alive {len(pl)}, their hp sum {hp}")
