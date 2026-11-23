"""SIDE-FIRST COMBAT: the final series. D against XN by pairs, missions of equal weight; the rule of FINAL_PLAN.md applied. args: zip prefix out.json

The battle's numbers from its log: [AIRESULT] totals, [AIDECIDE]+[AIEXEC] hostile actions, [AICASUALTY] who brought whom down (a victim once, the stun lines repeat), [AISTATE] the first hostile turn's segment
(aistart 1 -> pstart 2), [AISCD] the director's own acts; joint actions: a target hurt by two or more shooters in one turn on both arms; on XN a target that came into sight through one unit's action and was then shot by another,
a step aside followed by the helped unit's shot."""
import gzip
import io
import json
import random
import re
import sys
import zipfile
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
KV = re.compile(r"(\w+)=([^ ]*)")
ACT = {2: "walk", 6: "throw", 7: "auto", 8: "snap", 9: "aim", 10: "hit", 13: "psi", 14: "mc"}
ATT = {6, 7, 8, 9, 10, 13, 14}
SHOT = {7, 8, 9, 10}
MISSIONS = ["M3", "M8", "L4", "L8"]
SEEDS = [1, 2, 3, 4]
N = 10000


def battle(z, label):
    raw = gzip.open(io.BytesIO(z.read(f"out/{label}/openxcom.log.gz")), "rt", encoding="utf-8", errors="replace").read().splitlines()
    tsv = z.read(f"arena/{label}.tsv").decode("utf-8-sig").splitlines()
    head, row = tsv[0].split("\t"), tsv[-1].split("\t")
    arena = dict(zip(head, row))
    b = Counter()
    b["seconds"] = float(arena.get("seconds") or 0)
    outcome = arena.get("outcome")
    pend = None
    conc = defaultdict(set)
    down = Counter()
    seen_vict = set()
    hp_a, hp_p, snap, first_lost = {}, {}, None, None
    revealed = {}
    last_c = {}
    res = {}
    scd_aim = {}
    for s in raw:
        s = s.split("\t")[-1]
        if s.startswith("[AIDECIDE] "):
            pend = dict(KV.findall(s.split(" hu=")[0]))
            # aim of the director's own attack is what the unit's think last aimed at, or -1: the target is in its act,
            # which comes before this record (the order: act, the previous record's [AIEXEC], this [AIDECIDE])
            if pend.get("unit") in scd_aim:
                pend["aim"] = scd_aim.pop(pend["unit"])
        elif s.startswith("[AIEXEC] ") and pend:
            x = json.loads(s[9:])
            d, pend = pend, None
            if d.get("side") != "1" or str(x.get("unit")) != d.get("unit"):
                continue
            act = int(d.get("act", 0))
            spent = x.get("spent") or 0
            dm, fd = x.get("dmg") or 0, x.get("fdmg") or 0
            n = ACT.get(act, "other")
            b["n_" + n] += 1
            b["tu_" + n] += spent
            b["tu"] += spent
            b["dmg"] += dm
            b["fdmg"] += fd
            b["stun"] += x.get("stunned") or 0
            if act in ATT and spent > 0:
                b["att"] += 1
                b["att_tu"] += spent
                b["att_dmg"] += dm
                b["att_hit"] += 1 if dm else 0
                b["att_fdmg"] += fd
                b["att_ff"] += 1 if fd else 0
            if act in SHOT and spent > 0 and d.get("aim") not in (None, "-1"):
                if dm:
                    conc[(d["turn"], d["aim"])].add(d["unit"])
                    down[(d["turn"], d["aim"])] += x.get("downed") or 0
            if d.get("turn") == "1":
                b["t1_dmg"] += dm
                b["t1_fdmg"] += fd
                b["t1_tu"] += spent
                if act in ATT and spent > 0:
                    b["t1_att"] += 1
                    b["t1_hit"] += 1 if dm else 0
                if act == 2:
                    b["t1_walk"] += 1
        elif s.startswith("[AICASUALTY] "):
            d = dict(KV.findall(s))
            key = (d.get("victim"), d.get("how"))
            if key in seen_vict:
                continue
            seen_vict.add(key)
            vf, kf, side = d.get("vfaction"), d.get("kfaction"), d.get("side")
            if vf == "1":
                b["h_down"] += 1
                if kf == "1":
                    b["h_by_own"] += 1
                    b["h_by_own_" + ("own_turn" if side == "1" else "player_turn")] += 1
                elif side == "1":
                    b["h_by_p_in_h_turn"] += 1
                elif kf == "0":
                    b["h_by_p_in_p_turn"] += 1
                if d.get("turn") == "1" and side == "1":
                    b["t1_h_down"] += 1
            elif vf == "2":
                b["civ_by_h"] += 1 if kf == "1" else 0
            elif vf == "0":
                b["p_down"] += 1
                if side == "1":
                    b["p_down_h_turn"] += 1
                if d.get("turn") == "1" and side == "1":
                    b["t1_p_down"] += 1
        elif s.startswith("[AISTATE] "):
            kind = s.split(" ", 2)[1]
            d = dict(KV.findall(s))
            if d.get("faction") == "0" and "hp" in d:
                h = max(0, int(d["hp"].split("/")[0]))
                if kind == "aistart" and d.get("turn") == "1":
                    hp_a[d["unit"]] = h
                elif kind == "pstart" and d.get("turn") == "2":
                    hp_p[d["unit"]] = h
        elif s.startswith("[AISCD] "):
            j = json.loads(s[8:])
            e = j.get("ev")
            if e == "act":
                b["d_" + j["kind"]] += 1
                if j["kind"] == "C":
                    last_c[j["helps"]] = (j["turn"], j["goal"])
                if j["kind"] == "A":
                    scd_aim[str(j["actor"])] = str(j["target"])
                    t = (j["turn"], j["target"])
                    if t in revealed and revealed[t] not in (-1, j["actor"]):
                        b["j_reveal_fire"] += 1
                    if last_c.get(j["actor"]) == (j["turn"], j["target"]):
                        b["j_clear_fire"] += 1
                if j["turn"] == 1:
                    b["t1_d_" + j["kind"]] += 1
            elif e == "result" and j["kind"] == "A":
                b["d_A_dmg"] += j.get("tDmg", 0)
                b["d_A_hit"] += j.get("tHit", 0)
                b["d_A_tu"] += j.get("spent", 0)
                b["d_A_eff"] += j.get("eff", 0)
                b["d_A_n"] += 1
            elif e == "result" and j["kind"] in ("M", "P", "C"):
                b["d_walk_lost"] += j.get("ownLoss", 0)
                b["d_walk_down"] += j.get("ownDown", 0)
                b["d_walk_tu"] += j.get("spent", 0)
            elif e == "veto":
                b["d_veto"] += 1
                b["d_veto_blind"] += 1 if j["target"] == -1 else 0
            elif e == "special":
                b["d_special"] += 1
            elif e == "revealed":
                for i in j.get("ids", []):
                    revealed.setdefault((j["turn"], i), j["by"])
            elif e == "rng_touched":
                b["d_rng"] += 1
            elif e == "turn_end":
                b["d_us"] = j["usTotal"]
                b["d_lines_over"] += j["over"]
                b["d_banned"] += j["banned"]
                b["d_turn_ms_max"] = max(b["d_turn_ms_max"], j["us"] // 1000)
        elif s.startswith("[AIRESULT] "):
            res = dict(KV.findall(s))
    b["j_conc"] = sum(1 for v in conc.values() if len(v) >= 2)
    b["j_conc_down"] = sum(1 for k, v in conc.items() if len(v) >= 2 and down[k])
    b["t1_phplost"] = sum(h - hp_p.get(u, 0) for u, h in hp_a.items())
    for k in ("phplost", "pdead", "pout", "pwounded", "hostile", "hdead", "hout", "hleft", "turn", "player", "livesoldiers"):
        b[k] = int(res.get(k) or 0)
    b["p_out"] = b["pdead"] + b["pout"]
    b["h_out"] = b["hdead"] + b["hout"]
    return b, outcome


def m_ratio(b, a, c):
    return b[a] / b[c] if b[c] else None


METRICS = [
    ("phplost", "1 здоровье, потерянное игроком", lambda b: b["phplost"]),
    ("p_out", "1 бойцов игрока вне строя", lambda b: b["p_out"]),
    ("h_out", "2 врагов вне строя", lambda b: b["h_out"]),
    ("h_by_p_in_h_turn", "2 врагов сбито игроком в ход врага", lambda b: b["h_by_p_in_h_turn"]),
    ("h_by_p_in_p_turn", "2 врагов сбито игроком в ход игрока", lambda b: b["h_by_p_in_p_turn"]),
    ("turn", "5 ходов в бою", lambda b: b["turn"]),
    ("civ_by_h", "7 гражданских сбито врагом", lambda b: b["civ_by_h"]),
    ("loss_rate", "5 игрок проиграл (0/1)", None),
    ("dmg", "1 урон действий врага (все цели не своей стороны)", lambda b: b["dmg"]),
    ("stun", "1 оглушение от действий врага", lambda b: b["stun"]),
    ("fdmg", "3 урон по своим от действий врага", lambda b: b["fdmg"]),
    ("h_by_own", "3 своих сбито своими", lambda b: b["h_by_own"]),
    ("h_by_own_own_turn", "3 своих сбито своими в свой ход", lambda b: b["h_by_own_own_turn"]),
    ("att", "4 атак исполнено", lambda b: b["att"]),
    ("att_hit", "4 атак с раной", lambda b: b["att_hit"]),
    ("hit_share", "4 доля атак с раной", lambda b: m_ratio(b, "att_hit", "att")),
    ("att_dmg_tu", "4 урон атак на 100 ОВ атак", lambda b: 100 * b["att_dmg"] / b["att_tu"] if b["att_tu"] else None),
    ("ff_share", "3 урон по своим на единицу урона атак", lambda b: b["att_fdmg"] / b["att_dmg"] if b["att_dmg"] else None),
    ("dmg_tu", "4 урон всех действий на 100 ОВ", lambda b: 100 * b["dmg"] / b["tu"] if b["tu"] else None),
    ("tu", "4 ОВ потрачено", lambda b: b["tu"]),
    ("tu_walk", "4 ОВ на ходьбу", lambda b: b["tu_walk"]),
    ("j_conc", "6 целей, раненных двумя и более за ход", lambda b: b["j_conc"]),
    ("j_conc_down", "6 из них сбито в этот ход", lambda b: b["j_conc_down"]),
    ("n_throw", "сп. бросков", lambda b: b["n_throw"]),
    ("n_psi", "сп. пси-атак", lambda b: b["n_psi"]),
    ("n_mc", "сп. захватов", lambda b: b["n_mc"]),
    ("n_hit", "сп. рукопашных", lambda b: b["n_hit"]),
    ("seconds", "8 секунд на бой", lambda b: b["seconds"]),
    ("sec_turn", "8 секунд на ход", lambda b: b["seconds"] / b["turn"] if b["turn"] else None),
    ("t1_phplost", "Х1 здоровье игрока, потерянное в первый ход врага", lambda b: b["t1_phplost"]),
    ("t1_dmg", "Х1 урон действий врага", lambda b: b["t1_dmg"]),
    ("t1_fdmg", "Х1 урон по своим", lambda b: b["t1_fdmg"]),
    ("t1_att", "Х1 атак", lambda b: b["t1_att"]),
    ("t1_hit", "Х1 атак с раной", lambda b: b["t1_hit"]),
    ("t1_h_down", "Х1 врагов сбито", lambda b: b["t1_h_down"]),
    ("t1_p_down", "Х1 бойцов игрока сбито", lambda b: b["t1_p_down"]),
]


def means(by, fn):
    """by: {mission: [(a, b)]}; missions of equal weight; the mean of A, B and of the differences"""
    ma, mb, md = [], [], []
    for pairs in by.values():
        v = [(fn(a), fn(b)) for a, b in pairs]
        va = [x for x, _ in v if x is not None]
        vb = [y for _, y in v if y is not None]
        vd = [y - x for x, y in v if x is not None and y is not None]
        if va:
            ma.append(sum(va) / len(va))
        if vb:
            mb.append(sum(vb) / len(vb))
        if vd:
            md.append(sum(vd) / len(vd))
    f = lambda l: sum(l) / len(l) if l else float("nan")
    return f(ma), f(mb), f(md)


def boot(by, fn):
    rnd = random.Random(20261106)
    keys = list(by)
    out = []
    for _ in range(N):
        d = {}
        for i in range(len(keys)):
            k = rnd.choice(keys)
            d[i] = [rnd.choice(by[k]) for _ in by[k]]
        out.append(means(d, fn)[2])
    out.sort()
    return out[int(0.025 * N)], out[int(0.975 * N) - 1]


def main():
    z = zipfile.ZipFile(sys.argv[1])
    P = sys.argv[2]
    data = {}
    outs = {}
    for m in MISSIONS:
        for s in SEEDS:
            for arm in ("D", "XN"):
                b, o = battle(z, f"{P}_{arm}_{m}_s{s}")
                data[(arm, m, s)] = b
                outs[(arm, m, s)] = o
    by = {m: [(data[("D", m, s)], data[("XN", m, s)]) for s in SEEDS] for m in MISSIONS}
    for (arm, m, s), b in data.items():
        b["loss"] = 1 if outs[(arm, m, s)] == "loss" else 0
    report = {"metrics": {}, "missions": {}, "pairs": []}
    print(f"{'мера':<56}{'D':>9}{'XN':>9}{'XN-D':>9}  95% (грубо, 4 миссии)")
    for key, name, fn in METRICS:
        f = fn or (lambda b: b["loss"])
        a, c, d = means(by, f)
        lo, hi = boot(by, f)
        report["metrics"][key] = {"name": name, "D": a, "XN": c, "diff": d, "lo": lo, "hi": hi}
        print(f"{name:<56}{a:9.2f}{c:9.2f}{d:+9.2f}  [{lo:+.2f}, {hi:+.2f}]")
    print("\nпо миссиям: D -> XN")
    sign = Counter()
    for m in MISSIONS:
        r = {}
        for key, name, fn in METRICS:
            f = fn or (lambda b: b["loss"])
            a, c, _ = means({m: by[m]}, f)
            r[key] = (a, c)
        report["missions"][m] = r
        sign["m+" if r["phplost"][1] > r["phplost"][0] else "m-" if r["phplost"][1] < r["phplost"][0] else "m="] += 1
        print(f" {m}: phplost {r['phplost'][0]:.0f}->{r['phplost'][1]:.0f}, игрок вне строя {r['p_out'][0]:.1f}->{r['p_out'][1]:.1f}, враг вне строя {r['h_out'][0]:.1f}->{r['h_out'][1]:.1f}, ходов {r['turn'][0]:.1f}->{r['turn'][1]:.1f}, урон по своим {r['fdmg'][0]:.0f}->{r['fdmg'][1]:.0f}, своих своими {r['h_by_own'][0]:.1f}->{r['h_by_own'][1]:.1f}, "
              f"атак {r['att'][0]:.0f}->{r['att'][1]:.0f}, с раной {r['att_hit'][0]:.0f}->{r['att_hit'][1]:.0f}, броски {r['n_throw'][0]:.1f}->{r['n_throw'][1]:.1f}, пси {r['n_psi'][0]:.1f}->{r['n_psi'][1]:.1f}, захват {r['n_mc'][0]:.1f}->{r['n_mc'][1]:.1f}, рук {r['n_hit'][0]:.1f}->{r['n_hit'][1]:.1f}")
    print("\nпары: phplost D -> XN, игрок вне строя, враг вне строя, ходов, исход")
    for m in MISSIONS:
        for s in SEEDS:
            a, c = data[("D", m, s)], data[("XN", m, s)]
            sign["p+" if c["phplost"] > a["phplost"] else "p-" if c["phplost"] < a["phplost"] else "p="] += 1
            row = {"m": m, "s": s, "D": {k: a[k] for k in ("phplost", "p_out", "h_out", "turn", "fdmg", "att", "att_hit", "h_by_own")}, "XN": {k: c[k] for k in ("phplost", "p_out", "h_out", "turn", "fdmg", "att", "att_hit", "h_by_own")}, "outD": outs[("D", m, s)], "outXN": outs[("XN", m, s)]}
            report["pairs"].append(row)
            print(f" {m} s{s}: {a['phplost']:>5}->{c['phplost']:<5} игрок {a['p_out']}/{a['player']}->{c['p_out']}/{c['player']} враг {a['h_out']}/{a['hostile']}->{c['h_out']}/{c['hostile']} ходов {a['turn']}->{c['turn']} {outs[('D', m, s)]}->{outs[('XN', m, s)]} своим {a['fdmg']}->{c['fdmg']} атак {a['att']}->{c['att']} рана {a['att_hit']}->{c['att_hit']}")
    print("знаки phplost:", dict(sign))
    print("исходы D", dict(Counter(outs[k] for k in outs if k[0] == "D")), "XN", dict(Counter(outs[k] for k in outs if k[0] == "XN")))
    xn = Counter()
    for k, b in data.items():
        if k[0] == "XN":
            for f in b:
                if f.startswith(("d_", "j_")) and f != "d_turn_ms_max":
                    xn[f] += b[f]
    print("\nдиректор, всего по 16 боям:", dict(sorted(xn.items())))
    print("макс. мс директора за ход:", max(b["d_turn_ms_max"] for k, b in data.items() if k[0] == "XN"))
    t_d = sum(b["d_us"] for k, b in data.items() if k[0] == "XN") / 1e6
    t_s = sum(b["seconds"] for k, b in data.items() if k[0] == "XN")
    print(f"время директора {t_d:.1f} с из {t_s:.0f} с боя = {100 * t_d / t_s if t_s else 0:.2f} %")
    report["sign"] = dict(sign)
    report["xn"] = dict(xn)
    report["director_s"] = t_d
    report["battle_s"] = t_s
    report["outcomes"] = {"D": dict(Counter(outs[k] for k in outs if k[0] == "D")), "XN": dict(Counter(outs[k] for k in outs if k[0] == "XN"))}
    report["ms_max"] = max(b["d_turn_ms_max"] for k, b in data.items() if k[0] == "XN")
    a = report["metrics"]["phplost"]
    h = report["metrics"]["h_out"]
    ratio = a["XN"] / a["D"] - 1
    hr = h["XN"] / h["D"] - 1
    mp, pp = sign["m+"], sign["p+"]
    print(f"\nправило: phplost {100 * ratio:+.1f} % (нужно +10 %), миссий с ростом {mp}/4 (нужно 3), пар с ростом {pp}/16 (нужно 10), потери врага {100 * hr:+.1f} % (не выше +10 %)")
    report["rule"] = {"phplost_pct": 100 * ratio, "hostile_pct": 100 * hr, "missions_up": mp, "pairs_up": pp}
    json.dump(report, open(sys.argv[3], "w", encoding="utf-8"), ensure_ascii=False, indent=1)


main()
