"""SIDE-FIRST COMBAT: where D and XN differ, per mission over its four seeds. args: zip prefix

Rates per battle turn; attacks by the faction aimed at; who brought the player's units down (in whose turn); how the psi actions go; what a psi-capable unit did in a hostile turn; first hostile turn pair by pair."""
import gzip
import io
import json
import re
import sys
import zipfile
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
KV = re.compile(r"(\w+)=([^ ]*)")
MISSIONS = ["M3", "M8", "L4", "L8"]
SEEDS = [1, 2, 3, 4]
ACT = {2: "walk", 6: "throw", 7: "auto", 8: "snap", 9: "aim", 10: "hit", 13: "psi", 14: "mc", 0: "none"}


def read(z, label):
    raw = gzip.open(io.BytesIO(z.read(f"out/{label}/openxcom.log.gz")), "rt", encoding="utf-8", errors="replace").read().splitlines()
    return [s.split("\t")[-1] for s in raw]


def battle(z, label):
    c = Counter()
    pdown = Counter()
    hdown = Counter()
    fac = {}
    pend = None
    psi_units = set()
    psi_turn = defaultdict(Counter)
    seen = set()
    hp0, hp1 = {}, {}
    for s in read(z, label):
        if s.startswith("[AISTATE] "):
            d = dict(KV.findall(s))
            if "unit" in d and "faction" in d:
                fac[d["unit"]] = d["faction"]
                if d["faction"] == "0" and "hp" in d:
                    h = max(0, int(d["hp"].split("/")[0]))
                    k = s.split(" ", 2)[1]
                    if k == "aistart" and d.get("turn") == "1":
                        hp0[d["unit"]] = h
                    elif k == "pstart" and d.get("turn") == "2":
                        hp1[d["unit"]] = h
        elif s.startswith("[AIDECIDE] "):
            pend = dict(KV.findall(s.split(" hu=")[0]))
        elif s.startswith("[AIEXEC] ") and pend:
            x = json.loads(s[9:])
            d, pend = pend, None
            if d.get("side") != "1" or str(x.get("unit")) != d.get("unit"):
                continue
            a = int(d.get("act", 0))
            spent = x.get("spent") or 0
            if a in (7, 8, 9, 10) and spent > 0:
                f = fac.get(d.get("aim"), "?") if d.get("aim") != "-1" else "place"
                c["att_at_" + f] += 1
                c["attdmg_at_" + f] += x.get("dmg") or 0
                c["attff_at_" + f] += x.get("fdmg") or 0
            if a in (13, 14):
                c["psi_" + ACT[a]] += 1
                psi_units.add(d["unit"])
            c["tu_" + ACT.get(a, "o")] += spent
        elif s.startswith("[AICASUALTY] "):
            d = dict(KV.findall(s))
            k = (d.get("victim"), d.get("how"))
            if k in seen:
                continue
            seen.add(k)
            if d.get("vfaction") == "0":
                pdown[("h" if d.get("side") == "1" else "p", d.get("ktype"), d.get("weapon"), d.get("how"))] += 1
            elif d.get("vfaction") == "1":
                hdown[("h" if d.get("side") == "1" else "p", "own" if d.get("kfaction") == "1" else "player" if d.get("kfaction") == "0" else "?", d.get("how"))] += 1
        elif s.startswith("[AIRESULT] "):
            c.update({"turns": int(dict(KV.findall(s)).get("turn") or 0), "phplost": int(dict(KV.findall(s)).get("phplost") or 0)})
    c["t1_ph"] = sum(h - hp1.get(u, 0) for u, h in hp0.items())
    return c, pdown, hdown


def main():
    z = zipfile.ZipFile(sys.argv[1])
    P = sys.argv[2]
    t1 = Counter()
    for m in MISSIONS:
        print(f"\n== {m}")
        for arm in ("D", "XN"):
            tot, pd, hd = Counter(), Counter(), Counter()
            for s in SEEDS:
                c, p, h = battle(z, f"{P}_{arm}_{m}_s{s}")
                tot.update(c)
                pd.update(p)
                hd.update(h)
            print(f" {arm}: ходов {tot['turns']}, phplost {tot['phplost']} ({tot['phplost'] / tot['turns']:.1f} за ход), врагов сбито {sum(hd.values())} ({sum(hd.values()) / tot['turns']:.2f} за ход)")
            print("   атаки по фракции (0 игрок, 2 гражд.):", {k: v for k, v in sorted(tot.items()) if k.startswith(("att_at", "attdmg", "attff"))})
            print("   ОВ:", {k: v for k, v in sorted(tot.items()) if k.startswith("tu_")}, "пси:", {k: v for k, v in tot.items() if k.startswith("psi_")})
            print("   игрок сбит:", pd.most_common(9))
            print("   враг сбит (чей ход, кем, как):", sorted(hd.items(), key=lambda x: -x[1])[:8])
    print("\n== первый ход врага по парам: здоровье игрока D -> XN")
    for m in MISSIONS:
        for s in SEEDS:
            a = battle(z, f"{P}_D_{m}_s{s}")[0]["t1_ph"]
            b = battle(z, f"{P}_XN_{m}_s{s}")[0]["t1_ph"]
            t1["+" if b > a else "-" if b < a else "="] += 1
            print(f" {m} s{s}: {a} -> {b}")
    print(" знаки:", dict(t1))


main()
