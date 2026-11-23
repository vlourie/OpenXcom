"""NATURAL GATE, phase A, read only: the GO's six conditions over the scan, one gate after another; every gate says what stands behind it. Args: cands.jsonl, optional M10 scan for calibration."""
import json
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ATT = {5, 6, 7, 8, 9, 10, 11, 12}
RES = [json.loads(s) for s in Path(sys.argv[1]).open(encoding="utf-8")]


def b_acts(c):
    return [c["b_this"]] + c["b_later"]


def tight(a, c=None):
    """strictly ahead of B and short of T, within a cell of the flat ray, and on the height of the ray there within half a floor"""
    if not (a["dB"] >= 1 and a["dT"] >= 1 and a["dist"] <= 1.0):
        return False
    bz, tz = c["B"]["pos"][2], c["T"]["pos"][2]
    return abs(bz + a["k"] * (tz - bz) - a["pos"][2]) <= 0.5


def moved_flip(c):
    """the same B and T on the same cells and the same stance: lof 0 now, lof 1 later, and a comrade of the lane has left it"""
    for f in c["flips"]:
        if f["after"] and any(x["out"] or x["now"] != x["was"] for x in f["comrades"]):
            return f
    return None


def facts(c):
    t = [a for a in c["A"] if tight(a, c)]
    a = t[0] if t else c["A"][0]
    s = c["shot"]
    tu = c["B"]["tu"]
    place = tu // s["tu"] if s["tu"] else 0
    own = c["own"]
    selfn = (tu - own[0]) // s["tu"] if own and s["tu"] else 0
    acts = b_acts(c)
    attacks = [x for x in acts if x["t"] in ATT]
    a_att = [x for x in a["later"] if x["t"] in ATT]
    need_a = sum(x["spent"] or 0 for x in a_att)
    off = a["off"]
    return {
        "a": a, "n_tight": len(t),
        "refuted": any(a["id"] in x["gone"] for x in c.get("still", [])),
        "a_sees_line": a["lofT"] == 1,
        "a_close": a["dB"] <= 3,
        "flip": moved_flip(c) is not None,
        "b_no_other": not c["other_lof"],
        "b_no_attack": not attacks,
        "b_no_dmg": sum(x["dmg"] or 0 for x in attacks) == 0,
        "b_fired_t": any(x["u"] == c["T"]["id"] for x in attacks),
        "wounds_t": c["hurtT"] > 0,
        "self_worse": place > selfn,
        "self_none": c["own_fit"] == 0,
        "a_off": off is not None and a["tu"] is not None,
        "a_keeps": off is not None and a["tu"] is not None and off[0] + need_a <= a["tu"],
        "place": place, "selfn": selfn, "need_a": need_a,
    }


def line(c, f):
    a = f["a"]
    s = c["shot"]
    return (f"{c['battle']} t{c['turn']} B{c['B']['id']}{tuple(c['B']['pos'])} tu{c['B']['tu']} T{c['T']['id']}{tuple(c['T']['pos'])} d{s['d']} {s['w']} m{s['mode']} {s['tu']}TU p{s['p']} hurtT {c['hurtT']}"
            f" | A{a['id']}{tuple(a['pos'])} tu{a['tu']} dB{a['dB']} dT{a['dT']} perp{a['dist']} lofT {a['lofT']} off {a['off']} needA {f['need_a']} acted {a['acted_before']} |"
            f" own {c['own']} fit {c['own_fit']} shots place {f['place']} self {f['selfn']} | B did {[(x['t'], x['u'], x['spent'], x['dmg'], x['fdmg']) for x in b_acts(c)][:6]} flip {moved_flip(c) is not None} other {len(c['other_lof'])}")


GATES = [
    ("1 tight", "lof 0, TU for a shot, one comrade strictly on the lane within a cell of the ray"),
    ("2 evidence", "line evidence: that comrade has the line to T from its cell and stands within 3 of B, or the same B got the line once the comrade left"),
    ("3 A cell", "A has a free cell off the lane within its TU"),
    ("4 A keeps", "the step leaves A all it spent on attacks in D0"),
    ("5 wounds", "this weapon wounded this T in this battle"),
    ("6 no other", "B has no other shot with a line"),
    ("7 self", "own move costs B at least one shot, even by the optimistic flat cell"),
]
tot = Counter()
per = {}
fun = Counter()
short = []
wide = []
ffa = Counter()
ffw = Counter()
flips = Counter()
for r in RES:
    tot.update(r["stats"])
    ffa.update(r["ff"])
    ffw.update(r["ffw"])
    tot["battles"] += 1
    tot["turns"] += r["turns"]
    m = Counter()
    for c in r["cands"]:
        f = facts(c)
        m["flat"] += 1
        fun["0 flat"] += 1
        if moved_flip(c):
            flips["after comrade left"] += 1
            flips["same turn" if moved_flip(c)["turn"] == c["turn"] else "next turn"] += 1
        if f["n_tight"] != 1:
            continue
        fun[GATES[0][0]] += 1
        m["tight"] += 1
        if not ((f["a_sees_line"] and f["a_close"]) or f["flip"]):
            continue
        if f["refuted"] and not f["flip"]:
            fun["2x refuted: the comrade left, the engine still said lof 0"] += 1
            continue
        fun[GATES[1][0]] += 1
        m["line"] += 1
        if not f["a_off"]:
            continue
        fun[GATES[2][0]] += 1
        if not f["a_keeps"]:
            continue
        fun[GATES[3][0]] += 1
        if not f["wounds_t"]:
            continue
        fun[GATES[4][0]] += 1
        m["wound"] += 1
        wide.append((c, f))
        if not f["b_no_other"]:
            continue
        fun[GATES[5][0]] += 1
        if not f["self_worse"]:
            continue
        fun[GATES[6][0]] += 1
        m["self"] += 1
        fun["8a B did not attack at all in D0" if f["b_no_attack"] else "8b B attacked in D0"] += 1
        short.append((c, f))
    per[r["name"]] = (r["turns"], m["flat"], m["tight"], m["line"], m["wound"], m["self"], r["stats"].get("decisions", 0))

print("battles", tot["battles"], "turns", tot["turns"], "decisions", tot["decisions"], "with a gun and a known target", tot["with_gun_target"])
print("target pairs at decisions: lof 1", tot["shot_lof1"], "lof 0", tot["shot_lof0"], "lof 0 with TU", tot["shot_lof0_affordable"], "and a comrade on the flat lane", tot["lof0_comrade_flat"])
print(f"{fun['0 flat']:7d}  0 (turn, B, T) with lof 0, TU for a shot, a comrade within 1.5 of the flat lane")
for k, text in GATES:
    print(f"{fun[k]:7d}  {text}")
for k in sorted(fun):
    if k[0] == "8" or k.startswith("2x"):
        print(f"{fun[k]:7d}  {k}")
print("natural flips (engine line appears on the same cells once a comrade of the lane left):", dict(flips))
print("\nbattle: turns flat tight line wound self decisions")
for k in sorted(per):
    print(k, *per[k])
print("\nfriendly fire of plain shots:", dict(ffa))
print("by weapon:", ffw.most_common(10))
print("\nshortlist (all gates):", len(short))
for c, f in sorted(short, key=lambda x: (not x[1]["b_no_attack"], x[0]["battle"], x[0]["turn"])):
    print(line(c, f))
print("\nwounding, before gates 6 and 7:", len(wide), "B without attack", sum(f["b_no_attack"] for _, f in wide), "B without damage", sum(f["b_no_dmg"] for _, f in wide), "B fired at T", sum(f["b_fired_t"] for _, f in wide))

if len(sys.argv) > 2:
    # calibration: the M10 battle where the solver's engine checks are in the log
    m = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8").splitlines()[0])
    eng = {(j["turn"], j["B"]["id"], j["T"]["id"]) for j in m["tts"]}
    flat = {(c["turn"], c["B"]["id"], c["T"]["id"]) for c in m["cands"]}
    tig, strong = set(), set()
    for c in m["cands"]:
        f = facts(c)
        k = (c["turn"], c["B"]["id"], c["T"]["id"])
        if f["n_tight"] == 1:
            tig.add(k)
            if (f["a_sees_line"] and f["a_close"]) or f["flip"]:
                strong.add(k)
    print("\ncalibration M10: engine", len(eng), "flat", len(flat), "engine in flat", len(eng & flat), "tight", len(tig), "tight in engine", len(tig & eng), "evidence", len(strong), "evidence in engine", len(strong & eng))
