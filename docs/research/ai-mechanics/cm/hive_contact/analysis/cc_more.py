"""CONTACT_COORDINATION_V0: REINFORCE attacks by what they aimed at; MAINTAIN unit-turns' attacks and damage against a baseline; guards that lost their task by turn; modes of one squad; casualties of one squad (read only).
Usage: cc_more.py <run> <base> [squad to show]"""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from cc_eval import ATT, damage, side_dec  # noqa: E402
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")


def main():
    run, base = sys.argv[1], sys.argv[2]
    show = sys.argv[3] if len(sys.argv) > 3 else None
    L, B = read(run), read(base)
    dec, dec0 = side_dec(L), side_dec(B)
    dmg, dmg0 = damage(L), damage(B)
    cc = [kv(s) for s in L if s.startswith("[HIVECC]")]
    print("==", run, "against", base)
    aims = Counter()
    rc = {}
    for k in cc:
        if k["event"] == "ORDER" and k["role"] == "REINFORCE":
            t, u = int(k["turn"]), int(k["unit"])
            for d in dec[t].get(u, []):
                if int(d["act"]) in ATT:
                    a = d["aim"]
                    if a == k.get("contact"):
                        aims["role contact"] += 1
                    elif a == "-1":
                        aims["no unit"] += 1
                    elif int(a) >= 1000000:
                        aims["not a soldier"] += 1
                    else:
                        aims["other soldier"] += 1
    print(" REINFORCE attacks by aim", aims.most_common())
    mt = set()
    for k in cc:
        if k["event"] == "EXEC" and k["role"] == "MAINTAIN":
            mt.add((int(k["turn"]), int(k["unit"])))
    a_on = sum(int(d["act"]) in ATT for t, u in mt for d in dec[t].get(u, []))
    a_off = sum(int(d["act"]) in ATT for t, u in mt for d in dec0[t].get(u, []))
    d_on = sum(dmg.get((t, u), Counter())["dmg"] for t, u in mt)
    d_off = sum(dmg0.get((t, u), Counter())["dmg"] for t, u in mt)
    print(" MAINTAIN unit-turns", len(mt), "attacks on", a_on, "off", a_off, "damage on", d_on, "off", d_off, "alive in the baseline", sum(1 for t, u in mt if u in dec0[t]))
    for name, LL in ((run, L), (base, B)):
        print(" hold left", name, Counter(kv(s).get("why") for s in LL if s.startswith("[HIVETASK]") and "from=HOLD" in s).most_common(), [(kv(s)["turn"], kv(s)["squad"], kv(s).get("why")) for s in LL if s.startswith("[HIVETASK]") and "from=HOLD" in s][:8])
    if show:
        print(" squad", show)
        us = sorted({int(k["unit"]) for k in cc if k["event"] == "EXEC" and k["squad"] == show})
        for t in sorted(dec):
            print("  t", t, {u: dict(Counter(d["mode"] for d in dec[t][u])) for u in us if u in dec[t]})
        print("  casualties", [(kv(s)["turn"], kv(s)["victim"], kv(s)["how"], kv(s).get("killer")) for s in L if s.startswith("[AICASUALTY]") and kv(s)["victim"].isdigit() and int(kv(s)["victim"]) in us])


if __name__ == "__main__":
    main()
