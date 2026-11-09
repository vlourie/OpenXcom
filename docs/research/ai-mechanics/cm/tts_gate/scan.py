"""NATURAL GATE, phase A, read only. Over D0 logs: decisions where a soldier can afford a firearm shot at a known enemy, the engine says no line, and a comrade stands on the lane.
Every candidate is written with all that the log holds about it; verdicts are made by judge.py. Args: out dir, then logs (zip of the 48 D0 battles, or .log files)."""
import ctypes
import gzip
import io
import json
import multiprocessing as mp
import sys
import zipfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import gate_lib as G

ARC = "E:/OXCE_AIWorker/battles_archive/side_turn_scheduler_pilot_2026-10-30/res_scpa.zip"


def lines_of(src, member=None):
    if member:
        with zipfile.ZipFile(src) as z:
            raw = z.read(member)
        text = gzip.open(io.BytesIO(raw), "rt", encoding="utf-8", errors="replace")
    else:
        text = open(src, encoding="utf-8", errors="replace")
    with text:
        return [s.rstrip("\n").split("\t")[-1] for s in text]


def after(b, unit, i, turn):
    return [d for d in b.by_unit.get(unit, []) if d["i"] > i and d["turn"] == turn and d["side"] == 1]


def act_view(b, d):
    e = b.exec.get(d["rec"]) or {}
    return {"n": d["n"], "from": d["pos"], "tu": d["tu"], "t": d["t"], "to": d["to"], "w": d["w"], "u": G.attack_target(b, d) if d["t"] in (5, 6, 7, 8, 9, 10, 11, 12) else None,
            "src": d["src"], "spent": e.get("spent"), "dmg": e.get("dmg"), "fdmg": e.get("fdmg"), "pos": e.get("pos")}


def off_lane_cost(moves, apos, bpos, tpos, taken, tu):
    """cheapest reachable free cell of a comrade on the lane, on its floor, off the solver's lane, within its TU; flat, walls unknown"""
    best = None
    for c, cost in moves.items():
        if c in taken or c[2] != apos[2] or G.near_line(c, bpos, tpos) or (tu is not None and cost > tu):
            continue
        if best is None or cost < best[0]:
            best = (cost, c)
    return best


def own_cost(moves, me, tpos, others, need, tu):
    """B's cheapest reachable free cell whose flat lane to T holds no comrade, and how many such cells leave TU for one shot; optimistic: walls unknown"""
    best, fit = None, 0
    for c, cost in moves.items():
        if cost > tu or c in others or any(p != c and G.near_line(p, c, tpos) for p in others if p != me):
            continue
        if cost + need <= tu:
            fit += 1
        if best is None or cost < best[0]:
            best = (cost, c)
    return best, fit


def scan(name, lines):
    b = G.Battle(lines)
    out, seen = [], set()
    st = Counter()
    hurt, hurt_w = Counter(), Counter()
    for d in b.dec:
        if d["side"] == 1 and d["t"] in G.SHOT:
            u = G.attack_target(b, d)
            e = b.exec.get(d["rec"]) or {}
            hurt[(d["w"], u)] += e.get("dmg") or 0
            hurt_w[d["w"]] += e.get("dmg") or 0
    for d in b.dec:
        if d["side"] != 1 or not d["acts"]:
            continue
        st["decisions"] += 1
        acts = b.acts(d["acts"])
        shots = G.shots_by_target(acts)
        if not shots:
            continue
        st["with_gun_target"] += 1
        com = None
        for t, o in shots.items():
            if o["lof"]:
                st["shot_lof1"] += 1
                continue
            st["shot_lof0"] += 1
            if o["tu"] > d["tu"]:
                continue
            st["shot_lof0_affordable"] += 1
            if com is None:
                com = b.comrades(d["i"], d["unit"])
            onl = [(u, a) for u, a in com.items() if G.near_line(a[0], d["pos"], o["to"])]
            if not onl:
                continue
            st["lof0_comrade_flat"] += 1
            key = (d["turn"], d["unit"], t)
            if key in seen:
                continue
            seen.add(key)
            others = {a[0] for a in com.values()} | {d["pos"]}
            rec_a = []
            for u, a in sorted(onl, key=lambda x: G.cheb(x[1][0], d["pos"])):
                same = [x for x in b.by_unit.get(u, []) if x["pos"] == a[0] and x["side"] == 1 and x["acts"]]
                sameturn = [x for x in same if x["turn"] == d["turn"]]
                lofT = None
                for x in sameturn or same[:0]:
                    s2 = G.shots_by_target(b.acts(x["acts"])).get(t)
                    if s2 and s2["to"] == o["to"]:
                        lofT = max(lofT or 0, s2["lof"])
                own_shot = None
                for x in sameturn:
                    for t2, s2 in G.shots_by_target(b.acts(x["acts"])).items():
                        if s2["lof"] and s2["tu"] <= a[1] if a[1] is not None else False:
                            if own_shot is None or s2["p"] > own_shot["p"]:
                                own_shot = {"u": t2, "p": s2["p"], "tu": s2["tu"], "w": s2["w"], "d": s2["d"]}
                mv = {}
                for x in (sameturn or same)[:1]:
                    mv = b.moves(x["moves"])
                off = off_lane_cost(mv, a[0], d["pos"], o["to"], others, a[1]) if mv else None
                acted_before = [x for x in b.by_unit.get(u, []) if x["i"] < d["i"] and x["turn"] == d["turn"] and x["side"] == 1]
                later = after(b, u, d["i"], d["turn"])
                k, d2 = G.lane(a[0], d["pos"], o["to"])
                rec_a.append({"id": u, "pos": a[0], "tu": a[1], "k": round(k, 3), "dist": round(d2 ** 0.5, 2), "dB": G.cheb(a[0], d["pos"]), "dT": G.cheb(a[0], o["to"]),
                              "lofT": lofT, "own_shot": own_shot, "off": off, "acted_before": len(acted_before),
                              "later": [act_view(b, x) for x in later[:12]]})
            mvb = b.moves(d["moves"]) if d["moves"] else {}
            own, fit = own_cost(mvb, d["pos"], o["to"], others, o["tu"], d["tu"])
            other_lof = [{"u": t2, "tu": s2["tu"], "p": s2["p"], "d": s2["d"], "w": s2["w"]} for t2, s2 in shots.items() if s2["lof"] and s2["tu"] <= d["tu"]]
            # the same B on the same cell, the same T on the same cell, before and after: did the engine's line differ
            flips = []
            still = []
            for x in b.by_unit.get(d["unit"], []):
                if x["i"] == d["i"] or abs(x["turn"] - d["turn"]) > 1 or x["pos"] != d["pos"] or x["kneel"] != d["kneel"] or not x["acts"] or x["side"] != 1:
                    continue
                s2 = G.shots_by_target(b.acts(x["acts"])).get(t)
                if s2 and s2["to"] == o["to"] and not s2["lof"] and x["i"] > d["i"]:
                    gone = [u for u, a in onl if (b.at(u, x["i"]) or (None, None, True))[2] or (b.at(u, x["i"]) or (None,))[0] != a[0]]
                    if gone:
                        still.append({"turn": x["turn"], "n": x["n"], "gone": gone})
                if s2 and s2["to"] == o["to"] and s2["lof"]:
                    pa = [{"id": u, "was": a[0], "now": (b.at(u, x["i"]) or (None, None, True))[0], "out": (b.at(u, x["i"]) or (None, None, True))[2]} for u, a in onl]
                    flips.append({"turn": x["turn"], "n": x["n"], "after": x["i"] > d["i"], "comrades": pa, "tu": x["tu"], "did": act_view(b, x), "shot": s2, "others": sum(1 for t3, s3 in G.shots_by_target(b.acts(x["acts"])).items() if s3["lof"] and t3 != t)})
            out.append({"battle": name, "turn": d["turn"], "rec": d["rec"], "n": d["n"], "src": d["src"],
                        "B": {"id": d["unit"], "pos": d["pos"], "tu": d["tu"], "kneel": d["kneel"]},
                        "T": {"id": t, "pos": o["to"], "at": b.at(t, d["i"])},
                        "shot": o, "A": rec_a, "other_lof": other_lof, "own": own, "own_fit": fit, "flips": flips, "still": still,
                        "hurtT": hurt[(o["w"], t)], "hurtW": hurt_w[o["w"]],
                        "b_this": act_view(b, d), "b_later": [act_view(b, x) for x in after(b, d["unit"], d["i"], d["turn"])[:12]]})
    # friendly hits of plain shots with the engine's line there and a comrade on the lane: a comrade in the way the lof check lets through
    ff = Counter()
    ffw = Counter()
    for d in b.dec:
        if d["side"] != 1 or d["t"] not in G.SHOT or not d["acts"]:
            continue
        e = b.exec.get(d["rec"]) or {}
        ff["shots"] += 1
        ff["fdmg_all"] += e.get("fdmg") or 0
        ff["dmg_all"] += e.get("dmg") or 0
        if e.get("fdmg"):
            ff["shots_fdmg"] += 1
            ffw[d["w"]] += e.get("fdmg") or 0
            com = b.comrades(d["i"], d["unit"])
            if any(G.near_line(a[0], d["pos"], d["to"]) for a in com.values()):
                ff["shots_fdmg_lane"] += 1
                ff["fdmg_lane"] += e.get("fdmg") or 0
    return {"name": name, "stats": dict(st), "cands": out, "ff": dict(ff), "ffw": dict(ffw), "turns": max([x["turn"] for x in b.dec] or [0]),
            "tts": [j for _, j in b.tts if j.get("ev") == "cand"]}


def work(job):
    ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)
    name, src, member = job
    r = scan(name, lines_of(src, member))
    print(name, r["stats"].get("decisions"), len(r["cands"]), flush=True)
    return r


def main():
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    jobs = []
    for a in sys.argv[2:]:
        if a.endswith(".zip"):
            with zipfile.ZipFile(a) as z:
                jobs += [(n.split("/")[-2].replace("scpa_D_", ""), a, n) for n in sorted(z.namelist()) if n.endswith("openxcom.log.gz")]
        else:
            jobs.append((Path(a).stem, a, None))
    with mp.Pool(min(8, len(jobs))) as p, (out / "cands.jsonl").open("w", encoding="utf-8") as f:
        for r in p.imap_unordered(work, jobs):
            f.write(json.dumps(r) + "\n")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
