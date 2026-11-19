#!/usr/bin/env python3
"""MUTUAL_DIAGONAL_BLOCK - пассивный аудит класса по архивам серий (второе мнение 02.10, после FAIL
FIREPOINT_BLOCKED_V2_INTEROP на 1458). Движок не трогает, игра не запускается.

Пара: A упирается в B (walk.stop.unit клетка_A>клетка_B ... buB) и B упирается в A на тех же двух клетках.
Попытка - остановка или подавление V1 того же шага (blockstep.suppressed dN -> none, юнит на своей клетке,
направление в клетку партнёра): в сборках с V1 повтор в том же ходу виден только так. Эпизод - ходы с
попытками обеих сторон подряд; промежуток не рвёт, если оба остались на своих клетках (как mutual_episodes.py).
Класс (как MUTUAL_BLOCKED_STEP): никто никого не увидел (seen 0 в исполнении и нет в sees снимков AISTATE на
этих клетках), не меньше 2 ходов и 3 попыток с каждой стороны, 80 % попыток со своей клетки.

По каждому эпизоду: диагональ или прямо, стороны (бот-враг, враг-враг, бот-бот), карта, ходы, попытки,
наибольшее число попыток одного юнита за ход (цепочка), knownRevision (kr из остановки: сколько разных и
меняется ли между попытками одного хода), кандидаты атаки на партнёра в решениях с этой клетки (AICAND acts:
рукопашная t10 и её lof = validMeleeRange, выстрелы t7-9 и lof = canTargetUnit), обход (подавление V1 с
другим шагом, '-> dN'), чем кончился (ушёл / выбыл / бой кончился / до конца записи на клетках) и исход боя.

  py -3.13 tools/ai_speed/mutual_diag_audit.py --arena E:/OXCE_AIWorker/results/arena c53s23 v53s23 ...
Таблица эпизодов - runs/mutual_diag_<метка>.tsv, кандидаты атаки кэшируются в runs/mutual_acts_<метка>.txt."""
import argparse
import collections
import csv
import gzip
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import ENC_W, OUT, probe_work  # noqa: E402

HOSTILE = 1000000
RX_STOP = re.compile(r"walk\.stop\.unit (\d+),(\d+),(\d+)>(\d+),(\d+),(\d+) d(\d)\b.*? bu(-?\d+)(?: kr(\w+))?")
RX_SUPP = re.compile(r"blockstep\.suppressed d(\d) -> (none|d\d)")
RX_POS = re.compile(r"pos=\((-?\d+),(-?\d+),(-?\d+)\)")
# Pathfinding::dir_x / dir_y (src/Battlescape/Pathfinding.h), направление 0 - (0,-1), R-084
DIR = [(0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1)]
MIN_TURNS, MIN_TRY, ON_CELL, CHAIN = 2, 3, 0.8, 20
T_HIT = 10


def side(u):
    return "e" if u >= HOSTILE else "b"


def step(c, d):
    return (c[0] + DIR[d][0], c[1] + DIR[d][1], c[2])


def load_rec(path):
    """бой -> recs {rec: (ход, юнит, клетка, src, acts)}, tries [(rec, юнит, из, в, вид, партнёр, kr, seen)],
    detour [(rec, юнит, из, в)], pos {юнит: {ход: клетка первого решения}}"""
    B = collections.defaultdict(lambda: {"recs": {}, "ex": [], "pos": collections.defaultdict(dict)})
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            i = line.find("{")
            if i < 0:
                continue
            head = line[:i]
            if "[AIREC]" in head:
                r = json.loads(line[i:])
                b = B[head.split(" [", 1)[0]]
                c = tuple(r["state"]["pos"])
                b["recs"][r["rec"]] = (r["turn"], r["unit"], c, (r.get("base") or {}).get("src"), (r.get("cand") or {}).get("acts"))
                b["pos"][r["unit"]].setdefault(r["turn"], c)
            elif "[AIEXEC]" in head and ("walk.stop.unit" in line or "blockstep.suppressed" in line):
                r = json.loads(line[i:])
                B[head.split(" [", 1)[0]]["ex"].append((r["rec"], r["unit"], r.get("seen", 0), r.get("trail") or []))
    return B


def attempts(b):
    """Остановки юнитом и подавления V1 как попытки шага: (ход, rec, юнит, из, в, вид, партнёр, kr, seen)."""
    stops, supp, detour = [], [], collections.Counter()
    for rec, u, seen, trail in b["ex"]:
        if rec not in b["recs"]:
            continue
        turn, _, c0, src, _ = b["recs"][rec]
        for t in trail:
            m = RX_STOP.search(t)
            if m:
                g = m.groups()
                fa, ta = tuple(map(int, g[0:3])), tuple(map(int, g[3:6]))
                stops.append((turn, rec, u, fa, ta, "stop", int(g[7]), g[8], seen, src))
                continue
            m = RX_SUPP.search(t)
            if m:
                ta = step(c0, int(m.group(1)))
                if m.group(2) == "none":
                    supp.append((turn, rec, u, c0, ta, "supp", None, None, seen, src))
                else:
                    detour[(u, c0, ta)] += 1
    return stops, supp, detour


def stayed(b, a, p, fa, fb, t0, t1):
    pa, pb = b["pos"].get(a, {}), b["pos"].get(p, {})
    return all(pa.get(t, fa) == fa and pb.get(t, fb) == fb for t in range(t0 + 1, t1 + 1))


def ending(b, a, p, fa, fb, last):
    pa, pb = b["pos"].get(a, {}), b["pos"].get(p, {})
    later = sorted(t for t in set(pa) | set(pb) if t > last)
    if not later:
        return "end", None
    for t in later:
        ma, mb = t in pa and pa[t] != fa, t in pb and pb[t] != fb
        if ma or mb:
            who = "".join(sorted((side(a) if ma else "") + (side(p) if mb else "")))
            return f"moved_{who}", t
        if max(pa, default=0) < t or max(pb, default=0) < t:
            return "out", t
    return "held", later[-1]


def episodes(b):
    stops, supp, detour = attempts(b)
    pairs = collections.defaultdict(list)          # (a, p, fa, fb) -> попытки a
    for s in stops:
        turn, rec, u, fa, ta, kind, p, kr, seen, src = s
        pairs[(u, p, fa, ta)].append(s)
    occ = {}                                        # (юнит, из, в) -> партнёр по остановкам
    for (u, p, fa, ta) in pairs:
        occ[(u, fa, ta)] = p
    for s in supp:
        turn, rec, u, fa, ta = s[:5]
        p = occ.get((u, fa, ta))
        if p is not None:
            pairs[(u, p, fa, ta)].append(s)
    out, done = [], set()
    for key, xa in pairs.items():
        a, p, fa, fb = key
        rev = (p, a, fb, fa)
        if rev not in pairs or key in done or not any(x[5] == "stop" for x in xa) or not any(x[5] == "stop" for x in pairs[rev]):
            continue
        done |= {key, rev}
        xb = pairs[rev]
        ta_ = collections.defaultdict(list)
        tb_ = collections.defaultdict(list)
        for x in xa:
            ta_[x[0]].append(x)
        for x in xb:
            tb_[x[0]].append(x)
        both = sorted(set(ta_) & set(tb_))
        if not both:
            continue
        runs, cur = [], [both[0]]
        for t in both[1:]:
            if t - cur[-1] <= 1 or stayed(b, a, p, fa, fb, cur[-1], t):
                cur.append(t)
            else:
                runs.append(cur)
                cur = [t]
        runs.append(cur)
        for run in runs:
            sa = [x for t in range(run[0], run[-1] + 1) for x in ta_.get(t, [])]
            sb = [x for t in range(run[0], run[-1] + 1) for x in tb_.get(t, [])]
            out.append(dict(a=a, p=p, fa=fa, fb=fb, t0=run[0], t1=run[-1], sa=sa, sb=sb,
                            detour=detour.get((a, fa, fb), 0) + detour.get((p, fb, fa), 0)))
    return out


def tiles_states(path, keys):
    """бой -> {(ход, юнит): (клетка, sees, type)} по снимкам AISTATE aistart/pstart."""
    S = collections.defaultdict(dict)
    want = set(keys)
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            head, sep, rest = line.partition(" [")
            if not sep or head not in want or not rest.startswith("AISTATE] "):
                continue
            d = dict(t.split("=", 1) for t in rest.split(" ")[2:] if "=" in t)
            m = RX_POS.search(rest)
            sees = [int(x) for x in d.get("sees", "-").split(",")] if d.get("sees", "-") not in ("-", "") else []
            S[head][(int(d["turn"]), int(d["unit"]))] = (tuple(map(int, m.groups())) if m else None, sees, d.get("type", "?"))
    return S


def acts_for(arena, label, keys, hashes):
    """{hash: [act]} для нужных боёв; кэш runs/mutual_acts_<метка>.txt (строки боя целиком)."""
    cache = OUT / f"mutual_acts_{label}.txt"
    want = set(keys)
    rows = []
    if cache.is_file():
        with cache.open("r", encoding="utf-8", errors="replace") as f:
            rows = [line for line in f if line.split(" [", 1)[0] in want]
    meta = OUT / f"mutual_acts_{label}.keys"
    done = set(meta.read_text(encoding="utf-8-sig").splitlines()) if meta.is_file() else set()
    missing = want - done
    if missing:
        print(f"  {label}: кандидаты атаки для {len(missing)} боёв из cand.gz (один проход)", flush=True)
        new = []
        with gzip.open(arena / f"{label}.cand.gz", "rt", encoding="utf-8", errors="replace") as f:
            for line in f:
                if "[AICAND] acts=" not in line or '"k":"a"' not in line:
                    continue
                if line.split(" [", 1)[0] in missing:
                    new.append(line)
        with cache.open("a", encoding="utf-8") as f:
            f.writelines(new)
        meta.write_text("\n".join(sorted(done | want)), encoding=ENC_W)
        rows.extend(new)
    out = {}
    for line in rows:
        rest = line.split(" [", 1)[1]
        h = rest[len("AICAND] acts="):].split(" ", 1)[0]
        if h in hashes:
            out[h] = [x for x in json.loads(rest[rest.index(" list=") + 6:]) if x.get("k") == "a"]
    return out


def describe(e, b, states, acts, row):
    a, p, fa, fb = e["a"], e["p"], e["fa"], e["fb"]
    sa, sb = e["sa"], e["sb"]
    diag = abs(fa[0] - fb[0]) == 1 and abs(fa[1] - fb[1]) == 1 and fa[2] == fb[2]
    straight = fa[2] == fb[2] and abs(fa[0] - fb[0]) + abs(fa[1] - fb[1]) == 1
    turns = range(e["t0"], e["t1"] + 1)
    seen_exec = sum(1 for x in sa + sb if x[8])
    seen_snap = 0
    for t in turns:
        for u, c, q in ((a, fa, p), (p, fb, a)):
            st = states.get((t, u))
            if st and st[0] == c and q in st[1]:
                seen_snap += 1
    on = [sum(x[3] == c for x in xs) / len(xs) for xs, c in ((sa, fa), (sb, fb))]
    per_turn = collections.Counter((x[2], x[0]) for x in sa + sb)
    chain = max(per_turn.values())
    # knownRevision у остановок: разные значения и смена между остановками одного юнита в одном ходу
    krs = [x for x in sa + sb if x[5] == "stop" and x[7]]
    kr_n = len({(x[2], x[7]) for x in krs})
    kr_chg = kr_pairs = 0
    prev = {}
    for x in sorted(krs, key=lambda x: x[1]):
        k = (x[2], x[0])
        if k in prev:
            kr_pairs += 1
            kr_chg += prev[k] != x[7]
        prev[k] = x[7]
    # кандидаты атаки на партнёра в решениях со своей клетки во время эпизода, по сторонам
    C = {s: collections.Counter() for s in "be"}
    for rec, (turn, u, c, src, h) in b["recs"].items():
        if turn not in turns or not ((u == a and c == fa) or (u == p and c == fb)):
            continue
        cc = C[side(u)]
        cc["dec"] += 1
        lst = acts.get(h, []) if h else []   # в кэше только списки с атаками: нет списка - нет ни одной атаки
        q = p if u == a else a
        on_q = [x for x in lst if x.get("u") == q]
        if not lst:
            cc["noatt"] += 1
        if any(x.get("t") == T_HIT for x in on_q):
            cc["melee"] += 1
            cc["melee_lof"] += any(x.get("t") == T_HIT and x.get("lof") == 1 for x in on_q)
        if any(x.get("t") in (7, 8, 9) for x in on_q):
            cc["rng"] += 1
            cc["rng_lof"] += any(x.get("t") in (7, 8, 9) and x.get("lof") == 1 for x in on_q)
        if any(x.get("lof") == 1 for x in lst if x.get("u") != q):
            cc["other_lof"] += 1
    fmtc = lambda k: " ".join(f"{s}:{C[s][k]}" for s in "be" if C[s]["dec"])
    end, et = ending(b, a, p, fa, fb, e["t1"])
    cls = (seen_exec == 0 and seen_snap == 0 and len(turns) >= MIN_TURNS and min(len(sa), len(sb)) >= MIN_TRY
           and min(on) >= ON_CELL)
    ty = lambda u: next((v[2] for (t, uu), v in states.items() if uu == u), "?")
    src = collections.Counter(x[9] for x in sa + sb)
    return dict(geom="diag" if diag else ("straight" if straight else "other"), sides="".join(sorted(side(a) + side(p))),
                a=a, p=p, ta=ty(a), tp=ty(p), fa=",".join(map(str, fa)), fb=",".join(map(str, fb)),
                t0=e["t0"], t1=e["t1"], nturns=len(turns), na=len(sa), nb=len(sb),
                stops=sum(x[5] == "stop" for x in sa + sb), supp=sum(x[5] == "supp" for x in sa + sb), chain=chain,
                seen_exec=seen_exec, seen_snap=seen_snap, on=round(min(on), 2), cls=int(cls),
                kr_n=kr_n, kr_chg=f"{kr_chg}/{kr_pairs}", dec=fmtc("dec"), noatt=fmtc("noatt"), melee=fmtc("melee"),
                melee_lof=fmtc("melee_lof"), rng=fmtc("rng"), rng_lof=fmtc("rng_lof"), other_lof=fmtc("other_lof"),
                detour=e["detour"], end=end, end_turn=et if et is not None else "", how=row.get("how", "?"),
                bturn=row.get("turn", "?"), terrain=row.get("terrain", "?"), src=";".join(f"{k}:{v}" for k, v in src.most_common(3)))


COLS = ("label", "battle", "geom", "sides", "cls", "a", "ta", "fa", "p", "tp", "fb", "t0", "t1", "nturns", "na", "nb", "stops",
        "supp", "chain", "seen_exec", "seen_snap", "on", "kr_n", "kr_chg", "dec", "noatt", "melee", "melee_lof", "rng", "rng_lof",
        "other_lof", "detour", "end", "end_turn", "how", "bturn", "terrain", "src")


def main():
    sys.stdout.reconfigure(encoding="utf-8")  # R-001
    ap = argparse.ArgumentParser()
    ap.add_argument("labels", nargs="+")
    ap.add_argument("--arena", default="", help="папка архивов; пусто - рабочая папка стенда")
    ap.add_argument("--no-acts", action="store_true", help="не читать cand.gz (кандидаты атаки не считать)")
    a = ap.parse_args()
    arena = Path(a.arena) if a.arena else probe_work() / "arena"  # R-092
    OUT.mkdir(parents=True, exist_ok=True)
    for label in a.labels:
        with open(arena / f"{label}.tsv", encoding="utf-8-sig", newline="") as f:
            rows = {f"seed={r['seed']} want={r['want']}": r for r in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE)}
        B = load_rec(arena / f"{label}.rec.gz")
        eps = {k: episodes(b) for k, b in B.items()}
        eps = {k: v for k, v in eps.items() if v}
        states = tiles_states(arena / f"{label}.tiles.gz", eps)
        hashes = {B[k]["recs"][r][4] for k in eps for r in B[k]["recs"]} if not a.no_acts else set()
        acts = acts_for(arena, label, eps, hashes) if eps and not a.no_acts else {}
        res = []
        for k, lst in eps.items():
            for e in lst:
                d = describe(e, B[k], states.get(k, {}), acts, rows.get(k, {}))
                d.update(label=label, battle=k)
                res.append(d)
        with open(OUT / f"mutual_diag_{label}.tsv", "w", encoding=ENC_W, newline="") as f:
            w = csv.DictWriter(f, COLS, delimiter="\t", quoting=csv.QUOTE_NONE, escapechar="|")
            w.writeheader()
            w.writerows(res)
        dg = [d for d in res if d["geom"] == "diag"]
        dc = [d for d in dg if d["cls"]]
        print(f"== {label}: боёв {len(rows)}, с взаимной парой {len(eps)}; эпизодов {len(res)} "
              f"(диагональ {len(dg)}, в классе {len(dc)}; прямо {sum(d['geom'] == 'straight' for d in res)})", flush=True)


if __name__ == "__main__":
    main()
