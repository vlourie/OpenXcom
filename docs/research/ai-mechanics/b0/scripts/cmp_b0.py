"""Stage 0B: compare the battle saves the configurations left after one enemy turn from the same fixture.

  py -3.13 cmp_b0.py <out dir> <fixtures dir> <report.txt> [scenario ...]

Per pair of configurations: the RNG seed, every unit (position, direction, TU, energy, health, stun, morale, kneel,
status, wounds, the AI node and the rest of its fields), items, tiles (binTiles record by record) and the other battle
fields; the first differing unit in the order the engine walks the units (hostile first, as the AI turn plays them)."""
import base64
import sys
from pathlib import Path

import yaml

PAIRS = [
    ("P0", "P0b", "noise of the player exe"),
    ("D0", "D0b", "noise of the stand"),
    ("U0", "U0b", "noise of v8.7.1"),
    ("P0", "D0", "B: the stand reproduces the player's AI"),
    ("D0", "D0n", "stand accelerators off"),
    ("P0", "U0", "A: the player's AI against v8.7.1"),
    ("P0", "P1", "C: BetterAI on, the player exe"),
    ("P1", "D1", "B': the stand reproduces BetterAI"),
    ("P1", "P1A", "BetterAI + AI3"),
    ("D0", "DH", "stand defaults: O1-O4, O6 forced"),
    ("DH", "DS", "protocol flags on top of the defaults"),
    ("DS", "DSE", "inertness of the 0B switches (AL against E)"),
    ("P0", "DS", "D: the protocol stand against the player's AI"),
    ("D0", "U0", "A': the stand (release base) against v8.7.1"),
    ("P1", "DH", "stand defaults against BetterAI on"),
    ("P1", "DS", "the protocol stand against BetterAI on"),
    ("D1", "DS", "the protocol stand against the stand with BetterAI on"),
]
UNIT_KEYS = ("position", "direction", "tu", "energy", "health", "stunlevel", "morale", "kneeled", "status", "fatalWounds",
             "AI", "visible", "turnsSinceSpotted", "fire", "motionPoints", "mana")


def load(p):
    text = Path(p).read_text(encoding="utf-8", errors="replace")
    docs = text.split("\n---\n")
    return yaml.load(docs[-1], Loader=yaml.CSafeLoader)


def tiles(bg):
    raw = base64.b64decode(bg.get("binTiles") or b"")
    per = int(bg["tileTotalBytesPer"])
    isz = ord(str(bg["tileIndexSize"])[0]) if isinstance(bg["tileIndexSize"], str) else int(bg["tileIndexSize"])
    out = {}
    for k in range(0, len(raw) - per + 1, per):
        rec = raw[k:k + per]
        out[int.from_bytes(rec[:isz], "little")] = rec[isz:]
    return out


def state(p):
    g = load(p)
    bg = g["battleGame"]
    units = bg.get("units") or []
    return {"rng": g.get("rng"), "units": units, "byid": {u["id"]: u for u in units},
            "items": {i["id"]: i for i in (bg.get("items") or [])}, "tiles": tiles(bg),
            "other": {k: v for k, v in bg.items() if k not in ("units", "items", "binTiles")}, "w": bg["width"], "l": bg["length"]}


def faction(u):
    return {0: "p", 1: "h", 2: "n"}.get(u.get("faction"), str(u.get("faction")))


# cosmetic, drawn by RNG::seedless (BattleUnit.cpp 632, 5360), not the game's RNG: a unit born during the turn gets any value
IGNORE = {"rankIntUnified", "recolor"}


# the mod's HitFX tags (Piratez/Ruleset/HitFX-basic.rul): damageUnit stores the battle's frame counter and the hit totals
# of that frame and returns nothing (the damage stays), only recolorUnitSprite reads them (the hit flash); the frames follow
# the drawing, which the player exe does in real time and the stand by its virtual clock
FRAME_TAGS = ("LAST_HIT_", "HITFX_")
# animFrame: the frame counter; selectedUnit: the unit the screen selected (the player exe selects one when the turn comes)
OTHER_NOISE = {"animFrame", "selectedUnit"}


def tags_clean(t):
    return {k: v for k, v in t.items() if not k.startswith(FRAME_TAGS)} if isinstance(t, dict) else t


def udiff(a, b):
    keys = sorted((set(a) | set(b)) - IGNORE, key=lambda k: (k not in UNIT_KEYS, UNIT_KEYS.index(k) if k in UNIT_KEYS else 0, k))
    out = []
    for k in keys:
        x, y = a.get(k), b.get(k)
        if k == "tags":
            x, y = tags_clean(x), tags_clean(y)
            if x != y:
                ks = sorted(set(x or {}) | set(y or {}))
                x2 = {q: (x or {}).get(q) for q in ks if (x or {}).get(q) != (y or {}).get(q)}
                y = {q: (y or {}).get(q) for q in x2}
                x = x2
        if x != y:
            out.append((k, x, y))
    return out


def compare(A, B):
    r = {"rng": A["rng"] == B["rng"], "units": [], "items": 0, "tiles": [], "other": []}
    order = sorted(A["units"], key=lambda u: {"h": 0, "n": 1, "p": 2}.get(faction(u), 3))
    for u in order:
        v = B["byid"].get(u["id"])
        d = udiff(u, v) if v else [("missing", "", "")]
        if d:
            r["units"].append((u["id"], faction(u), d))
    r["units"] += [(i, "?", [("extra", "", "")]) for i in B["byid"] if i not in A["byid"]]
    di = [i for i in set(A["items"]) | set(B["items"]) if A["items"].get(i) != B["items"].get(i)]
    r["items"] = len(di)
    # the body of a unit that bled to death at the start of the turn: one save still has its unconscious body (dropped on
    # the enemy turn), the other already the corpse UnitDieBState made of it (new id, dropped on the player's turn) - the
    # autosave came before or after that state ran; the same item otherwise
    def body(it):
        return (it.get("type"), it.get("unit"), str(it.get("position")), it.get("inventoryslot"))
    oa = sorted(body(A["items"][i]) for i in di if i in A["items"] and i not in B["items"] and A["items"][i].get("unit"))
    ob = sorted(body(B["items"][i]) for i in di if i in B["items"] and i not in A["items"] and B["items"][i].get("unit"))
    both = [i for i in di if i in A["items"] and i in B["items"]]
    r["items_body"] = len(oa) if oa and oa == ob and len(oa) * 2 == len(di) - len(both) and not both else 0
    for i in set(A["tiles"]) | set(B["tiles"]):
        if A["tiles"].get(i) != B["tiles"].get(i):
            w, l = A["w"], A["l"]
            r["tiles"].append((i % w, (i // w) % l, i // (w * l)))
    r["other"] = [k for k in set(A["other"]) | set(B["other"]) if A["other"].get(k) != B["other"].get(k) and k not in OTHER_NOISE]
    r["same"] = r["rng"] and not r["units"] and not r["items"] and not r["tiles"] and not r["other"]
    # a unit falling at the start of the player's turn (stun up to its health, or no health left): UnitDieBState turns it
    # to direction 3 one step a frame, and the autosave catches the turn at some step - only the direction differs
    def falling(uid, d):
        u = A["byid"].get(uid)
        return u and [k for k, _, _ in d] == ["direction"] and (int(u.get("stunlevel", 0)) >= int(u.get("health", 0)) or int(u.get("health", 0)) <= 0)
    r["units_fall"] = sum(1 for uid, _, d in r["units"] if falling(uid, d))
    r["same_snap"] = (r["rng"] and r["units_fall"] == len(r["units"]) and r["items_body"] * 2 == r["items"] and not r["tiles"]
                      and not r["other"] and (r["units"] or r["items"]))
    return r


def short(v, n=90):
    s = str(v)
    return s if len(s) <= n else s[:n] + "..."


def moved(F, A):
    """Units the AI turn changed against the fixture: how much happened."""
    c = {"h": 0, "n": 0, "p": 0}
    for u in A["units"]:
        f = F["byid"].get(u["id"])
        if f and (f.get("position") != u.get("position") or f.get("tu") != u.get("tu") or f.get("health") != u.get("health")
                  or f.get("status") != u.get("status") or f.get("direction") != u.get("direction")):
            c[faction(u)] = c.get(faction(u), 0) + 1
    return c


MKEYS = ("h_tu", "h_moved", "modes", "p_hp", "p_stun", "p_down", "h_down", "ammo")


def metrics(F, A):
    """What the turn did, against the fixture: hostile TU spent (TU of the stats minus TU left), hostiles that moved, the
    AI modes, the player's health and stun lost, player units down, rounds fired (ammo of hostile-held items)."""
    m = {"h_tu": 0, "h_moved": 0, "modes": {}, "p_hp": 0, "p_stun": 0, "p_down": 0, "h_down": 0, "ammo": 0}
    for u in A["units"]:
        f = F["byid"].get(u["id"])
        if not f:
            continue
        fac = faction(u)
        alive = u.get("status") not in (6, 7)
        if fac == "h":
            if alive:
                m["h_tu"] += int((u.get("currStats") or {}).get("tu", 0)) - int(u.get("tu", 0))
                mode = (u.get("AI") or {}).get("AIMode")
                m["modes"][mode] = m["modes"].get(mode, 0) + 1
            m["h_moved"] += f.get("position") != u.get("position")
            m["h_down"] += f.get("status") not in (6, 7) and not alive
        elif fac == "p":
            m["p_hp"] += int(f.get("health", 0)) - int(u.get("health", 0))
            m["p_stun"] += int(u.get("stunlevel", 0)) - int(f.get("stunlevel", 0))
            m["p_down"] += f.get("status") not in (6, 7) and not alive
    hostile = {u["id"] for u in A["units"] if faction(u) == "h"}
    for i, it in F["items"].items():
        if it.get("owner") in hostile:
            b = A["items"].get(i)
            m["ammo"] += int(it.get("ammoqty", 0)) - int((b or {}).get("ammoqty", 0)) if b else 0
    m["modes"] = ",".join(f"{k}:{v}" for k, v in sorted(m["modes"].items(), key=lambda x: str(x[0])))
    return m


def main():
    out, fxd, rep = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    args = sys.argv[4:]
    # auto.sav - the player's turn autosave (every configuration but DSE); after.sav - the stand's and U0's own save,
    # once the player's side is ready (after the panicking units acted)
    snap = args.pop(0)[5:] if args and args[0].startswith("file=") else "auto.sav"
    scen = args or sorted({p.stem for p in fxd.glob("*.sav")})
    lines, rows = [f"# snapshot {snap}"], ["scen\tpair\tverdict\trng\tunits\th_units\titems\ttiles\tother\tfirst"]
    mrows = ["scen\tcfg\trng\t" + "\t".join(MKEYS)]
    for s in scen:
        F = state(fxd / f"{s}.sav")
        S = {}
        for d in out.glob(f"*_{s}"):
            cfg = d.name[: -len(s) - 1]
            if (d / snap).is_file():
                try:
                    S[cfg] = state(d / snap)
                except Exception as e:
                    lines.append(f"{s} {cfg}: unreadable {e}")
        lines.append(f"== {s}: fixture turn {F['other'].get('turn')} units {len(F['units'])}; runs: {' '.join(sorted(S))}")
        for cfg in sorted(S):
            mt = metrics(F, S[cfg])
            lines.append(f"   {cfg}: turn {S[cfg]['other'].get('turn')} changed {moved(F, S[cfg])} rng {S[cfg]['rng']} {mt}")
            mrows.append(f"{s}\t{cfg}\t{S[cfg]['rng']}\t" + "\t".join(str(mt[k]) for k in MKEYS))
        for a, b, why in PAIRS:
            if a not in S or b not in S:
                lines.append(f"  {a}~{b}: n/a ({why})")
                continue
            r = compare(S[a], S[b])
            hu = [u for u in r["units"] if u[1] == "h"]
            first = r["units"][0] if r["units"] else None
            fs = f"unit {first[0]}{first[1]} " + "; ".join(f"{k}: {short(x, 60)} | {short(y, 60)}" for k, x, y in first[2][:4]) if first else "-"
            verdict = "IDENTICAL" if r["same"] else "SAME_BUT_SNAPSHOT" if r["same_snap"] else "DIFF"
            rows.append(f"{s}\t{a}~{b}\t{verdict}\t{int(r['rng'])}\t{len(r['units'])}\t{len(hu)}\t{r['items']}\t{len(r['tiles'])}\t"
                        f"{','.join(sorted(r['other']))}\t{fs}")
            lines.append(f"  {a}~{b}: {verdict} ({why}) rng={'=' if r['rng'] else '!='} units={len(r['units'])} "
                         f"(h {len(hu)}) items={r['items']} tiles={len(r['tiles'])} other={sorted(r['other'])}")
            for uid, fac, d in r["units"][:3]:
                lines.append(f"     unit {uid}{fac}: " + "; ".join(f"{k}: {short(x)} | {short(y)}" for k, x, y in d[:6]))
            if r["tiles"]:
                lines.append(f"     tiles {r['tiles'][:6]}")
    rep.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    rep.with_suffix(".tsv").write_text("\n".join(rows) + "\n", encoding="utf-8-sig")
    rep.with_name(rep.stem + "_metrics.tsv").write_text("\n".join(mrows) + "\n", encoding="utf-8-sig")
    sys.stdout.reconfigure(encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
