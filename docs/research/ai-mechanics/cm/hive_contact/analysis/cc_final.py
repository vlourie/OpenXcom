"""CONTACT_COORDINATION_V0, the closing tables by run: orders to stand with a line, what REINFORCE unit-turns came to against a baseline, every REINFORCE spell, the guards, the side (read only).
Usage: cc_final.py <active run> <baseline run> [last turn]"""
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from cc_eval import ATT, casualties, damage, side_dec  # noqa: E402
from lib import kv, read, tup  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")


def fate(ds):
    if not ds:
        return "no decision"
    acts = [int(d["act"]) for d in ds]
    if any(a in ATT for a in acts):
        return "attacked"
    if any(a == 2 for a in acts):
        return "walked"
    return "stood mode " + "/".join(sorted({d["mode"] for d in ds}))


def main():
    run, base = sys.argv[1], sys.argv[2]
    last = int(sys.argv[3]) if len(sys.argv) > 3 else 8
    L, B = read(run), read(base)
    dec, dec0 = side_dec(L), side_dec(B)
    dmg, dmg0 = damage(L), damage(B)
    cc = [kv(s) for s in L if s.startswith("[HIVECC]")]
    print("==", run, "against", base)

    print("== stand with a line (kind=in_place): what it came to, TU first->last, the same unit-turn in the baseline")
    tally = Counter()
    for k in cc:
        if k["event"] == "ORDER" and k["kind"] == "in_place":
            t, u = int(k["turn"]), int(k["unit"])
            ds = dec[t].get(u, [])
            f, f0 = fate(ds), fate(dec0[t].get(u, []))
            tally[(k["role"], f)] += 1
            first = int(ds[0]["tu"]) if ds else 0
            lastu = int(ds[-1]["tu"]) if ds else 0
            print(f"   t{t} {k['role']} {u} {f} tu {first}->{lastu} modes {dict(Counter(d['mode'] for d in ds))}; baseline {f0}")
    print("   sum", tally.most_common())

    print("== REINFORCE unit-turns, by kind: on and the same unit-turn in the baseline")
    rows = Counter()
    ru = []
    for k in cc:
        if k["event"] == "ORDER" and k["role"] == "REINFORCE":
            t, u = int(k["turn"]), int(k["unit"])
            ru.append((t, u))
            rows[(k["kind"], fate(dec[t].get(u, [])), fate(dec0[t].get(u, [])))] += 1
    for r, n in sorted(rows.items()):
        print("  ", r, n)
    on = Counter(fate(dec[t].get(u, [])) for t, u in ru)
    off = Counter(fate(dec0[t].get(u, [])) for t, u in ru)
    print("   all on ", on.most_common())
    print("   all off", off.most_common())
    a_on = sum(sum(int(d["act"]) in ATT for d in dec[t].get(u, [])) for t, u in ru)
    a_off = sum(sum(int(d["act"]) in ATT for d in dec0[t].get(u, [])) for t, u in ru)
    d_on, d_off = Counter(), Counter()
    for t, u in ru:
        d_on.update(dmg.get((t, u), Counter()))
        d_off.update(dmg0.get((t, u), Counter()))
    print("   attacks on", a_on, "off", a_off, "damage on", dict(d_on), "off", dict(d_off))

    print("== REINFORCE spells")
    spell = {}
    done = []
    for k in cc:
        if k["event"] != "ASSIGN":
            continue
        sq = k["squad"]
        if k["to"] == "REINFORCE" and k["from"] != "REINFORCE":
            spell[sq] = {"squad": sq, "from": int(k["turn"]), "contacts": [k["contact"]], "why_end": "battle_over", "to": last}
        elif sq in spell and k["to"] == "REINFORCE":
            spell[sq]["contacts"].append(k["contact"])
        elif sq in spell:
            spell[sq]["why_end"] = k["why"]
            spell[sq]["to"] = int(k["turn"]) - 1
            done.append(spell.pop(sq))
    done += spell.values()
    killers = defaultdict(list)
    fallen = defaultdict(list)
    for s in L:
        if s.startswith("[AICASUALTY]"):
            k = kv(s)
            killers[(int(k["turn"]), k.get("killer"))].append(k)
            fallen[(int(k["turn"]), k.get("victim"))].append(k)
    for sp in sorted(done, key=lambda x: x["from"]):
        us = sorted({int(k["unit"]) for k in cc if k["event"] == "ORDER" and k["role"] == "REINFORCE" and k["squad"] == sp["squad"] and sp["from"] <= int(k["turn"]) <= sp["to"]})
        kinds = Counter(k["kind"] for k in cc if k["event"] == "ORDER" and k["role"] == "REINFORCE" and k["squad"] == sp["squad"] and sp["from"] <= int(k["turn"]) <= sp["to"])
        att = hit = rc = kills = lost = 0
        for t in range(sp["from"], sp["to"] + 1):
            for u in us:
                for d in dec[t].get(u, []):
                    if int(d["act"]) in ATT:
                        att += 1
                        rc += d["aim"] in sp["contacts"]
                hit += dmg.get((t, u), Counter())["dmg"]
                kills += len([x for x in killers.get((t, str(u)), []) if x.get("vfaction") == "0"])
                lost += len(fallen.get((t, str(u)), []))
        print(f"   squad {sp['squad']} t{sp['from']}-{sp['to']} contacts {sp['contacts']} units {len(us)} kinds {dict(kinds)} attacks {att} (on a role contact {rc}) damage {hit} downed {kills} own lost {lost} end {sp['why_end']}")

    print("== guards: from the headquarters' records")
    holds = {}
    for s in L:
        if s.startswith("[HIVEHOLD]"):
            k = kv(s)
            holds.setdefault(int(k["squad"]), k)
    # a guard as a squad: its roles over the decisions, its units' distance from the anchor, attacks and hold exits
    roles = defaultdict(list)
    for s in L:
        if s.startswith("[HIVECC]") and "event=DECISION" in s:
            k = kv(s)
            t = int(k["turn"])
            for part in s.split("squads: ")[1].split(" "):
                if "=" in part:
                    sq, r = part.split("=")
                    roles[int(sq)].append((t, r.split(":")[0][0]))
    exits = defaultdict(list)
    for s in L:
        if s.startswith("[HIVETASK]") and "from=HOLD" in s:
            k = kv(s)
            exits[int(k["squad"])].append((k["turn"], k.get("why")))
    members = defaultdict(set)
    for s in L:
        if s.startswith("[HIVECC]") and "event=EXEC" in s:
            k = kv(s)
            members[int(k["squad"])].add(int(k["unit"]))
    for sq, h in sorted(holds.items()):
        a = tup(h["anchor"])
        rr = "".join(f"{x[1]}" for x in roles[sq])
        far = att = 0
        for u in members[sq]:
            for t in dec:
                for d in dec[t].get(u, []):
                    p = tup(d["from"])
                    far = max(far, max(abs(p[0] - a[0]), abs(p[1] - a[1])))
                    att += int(d["act"]) in ATT
        print(f"   squad {sq} anchor {a} why {h['why']} roles by turn {rr} units {len(members[sq])} attacks {att} farthest from anchor {far} hold exits {exits[sq]}")

    print("== side, turns 1 to", last)
    for name, dc, dm, LL in (("on ", dec, dmg, L), ("off", dec0, dmg0, B)):
        a = sum(int(d["act"]) in ATT for t in dc if t <= last for ds in dc[t].values() for d in ds)
        dd = sum(v["dmg"] for (t, u), v in dm.items() if t <= last)
        alive = len(dc.get(last, {}))
        print("  ", name, "attacks", a, "damage by the side", dd, "casualties", dict(casualties(LL, last)), "units deciding at the last turn", alive)
    print("   attacks by aim kinds in run on the side's own: friendly damage", sum(v["fdmg"] for v in dmg.values()), "off", sum(v["fdmg"] for v in dmg0.values()))
    res = [s[:190] for s in L if s.startswith("[AIRESULT]")]
    print("  ", res[-1:] )

    print("== orders in all")
    print("  ", Counter((k["role"], k["kind"]) for k in cc if k["event"] == "ORDER").most_common())
    d3 = []
    for s in L:
        if s.startswith("[HIVECC]") and "event=DECISION" in s:
            k = kv(s)
            r = {p.split("=")[1].split(":")[0] for p in s.split("squads: ")[1].split(" ") if "=" in p}
            d3.append((int(k["turn"]), "".join(sorted(x[0] for x in r))))
    print("   roles in one decision by turn", d3)


if __name__ == "__main__":
    main()
