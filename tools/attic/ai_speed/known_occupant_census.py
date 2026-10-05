#!/usr/bin/env python3
"""ENEMY_KNOWN_OCCUPANT_PATH_INCONSISTENCY - узкая пассивная перепись поверх unknown_occupant_census (второе мнение
02.10 по п. 17.12). Только враг (side 1), только чужой блокер. Движок не трогает, игра не запускается.

Откуда враг знает о блокере (по коду, не по памяти):
  AIModule::getTargetAttackWeight - цель известна, если turnsSinceSpottedByFaction(своя) <= _intelligence; позиция при
    этом ЖИВАЯ (bu->getPosition()), отдельной «последней известной позиции» в этом пути нет;
  AIModule::findFirePoint -> selectClosestKnownEnemy: _aggroTarget = ближайшая по Position::distance2d известная цель
    (validTarget, строгое <, первая в порядке getUnits при равенстве);
  AiCandidates: кандидаты атаки (AICAND k=a) - враги, видимые юниту сами ИЛИ замеченные стороной не дольше intelligence
    ходов назад; d = тот же distance2d;
  Pathfinding::isBlocked для врага - только юниты из getUnitsSpottedThisTurn() ЭТОГО юнита, а addToVisibleUnits кладёт
    каждого видимого и туда. Значит, блокер, на которого наступили, юниту сам не виден: если враг его знал, то только
    знанием стороны.

По каждому эпизоду (первая настоящая остановка в ходу):
  cls        - aggro (блокер = ближайшая известная цель, то есть цель findFirePoint), known (в кандидатах, не ближайший),
               unknown (нет в кандидатах);
  tie        - у ближайшей цели есть равный по d (порядок getUnits решает, отмечено);
  d_b, d_min - distance2d до блокера и до ближайшей известной цели;
  lof        - у кандидатов атаки на блокера с места решения есть линия огня (max по оружию/режимам);
  age        - spotted= блокера в AISTATE aistart этого хода (turnsSinceSpotted стороной врага на начало хода);
  pos_q      - позиция блокера в aistart == Q;
  sees       - юнит видел блокера в aistart (по коду должно быть 0 для настоящей остановки);
  moved_unseen - age >= 1 и позиция в последнем aistart с age 0 не Q (блокер ушёл без свидетелей, а ИИ держит живую
               позицию); none - снимка с age 0 до этого хода нет.

  py -3.13 tools/ai_speed/known_occupant_census.py c53s23 ...      (нужны runs/unknown_occ_<метка>.tsv)
  py -3.13 tools/ai_speed/known_occupant_census.py --summary c53 v53 f46fp"""
import argparse
import collections
import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import ENC_R, ENC_W, OUT  # noqa: E402
import unknown_occupant_census as uoc  # noqa: E402

RX_AISTART = re.compile(r"\[AISTATE\] aistart turn=(\d+) unit=(\d+) type=\S+ faction=(\d) status=\d+ pos=\((\d+),(\d+),(\d+)\)"
                        r".*? spotted=(-?\d+) sniped=-?\d+ sees=(\S+)")
COLS = ["label", "battle", "terrain", "how", "unit", "turn", "q", "blocker", "src", "first", "rep", "run", "outcome",
        "goal_q", "cls", "tie", "d_b", "d_min", "lof", "age", "pos_q", "sees", "moved_unseen"]


def read_tsv(path):
    with open(path, encoding=ENC_R, newline="") as f:
        return list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE, escapechar="\\"))


def main_src(r):
    return max(((kv.rsplit(":", 1)[0], int(kv.rsplit(":", 1)[1])) for kv in r["src"].split(";") if kv), key=lambda x: x[1])[0]


def load_cands(arena, label, need):
    """{(бой, acts): {T: (min d, max lof, {позиции})}} для нужных acts."""
    out = {}
    pat = OUT / f"known_occ_{label}.acts.txt"
    pat.write_text("".join(f"acts={h} \n" for h in sorted({h for _, h in need})), encoding="ascii")
    for line in uoc.gz_lines(arena / f"{label}.cand.gz", ["-F", "-f", str(pat)]):
        b, rest = line.split(" [", 1)
        if not rest.startswith("AICAND] acts="):
            continue
        h = rest[len("AICAND] acts="):].split(" ", 1)[0]
        if (b, h) not in need:
            continue
        tg = {}
        for x in json.loads(rest[rest.index(" list=") + 6:]):
            if x.get("k") == "a" and "u" in x:
                d, lof, ps = tg.get(x["u"], (10 ** 6, 0, set()))
                ps.add(tuple(x["to"]))
                tg[x["u"]] = (min(d, x.get("d", 10 ** 6)), max(lof, x.get("lof", 0)), ps)
        out[(b, h)] = tg
    pat.unlink()
    return out


def load_aistart(arena, label):
    """{(бой, юнит): [(ход, позиция, spotted, sees)]} по возрастанию хода."""
    out = collections.defaultdict(list)
    for line in uoc.gz_lines(arena / f"{label}.tiles.gz", ["-F", "[AISTATE] aistart"]):
        m = RX_AISTART.search(line)
        if not m:
            continue
        g = m.groups()
        sees = set() if g[7] == "-" else {int(x) for x in g[7].split(",")}
        out[(line.split(" [", 1)[0], int(g[1]))].append((int(g[0]), (int(g[3]), int(g[4]), int(g[5])), int(g[6]), sees))
    for v in out.values():
        v.sort(key=lambda x: x[0])
    return out


def census(arena, label):
    rows = [r for r in read_tsv(OUT / f"unknown_occ_{label}.tsv") if r["side"] == "1" and r["rel"] == "enemy"]
    fac = uoc.factions(arena, label)
    recs, order = uoc.load_rec(arena, label)
    st = load_aistart(arena, label)
    first = {}
    for r in rows:
        b, a, turn = r["battle"], int(r["unit"]), int(r["turn"])
        q = tuple(map(int, r["q"].split(",")))
        rs = sorted(rec for rec in order[(b, a)] if recs[(b, rec)][0] == turn)
        first[id(r)] = next(rec for rec in rs if any(x[0] == q and x[1] is not None for x in recs[(b, rec)][8]))
    need = {(r["battle"], recs[(r["battle"], first[id(r)])][4]) for r in rows if recs[(r["battle"], first[id(r)])][4]}
    cands = load_cands(arena, label, need)
    out = []
    for r in rows:
        b, a, turn, t = r["battle"], int(r["unit"]), int(r["turn"]), int(r["blocker"])
        q = tuple(map(int, r["q"].split(",")))
        tg = cands.get((b, recs[(b, first[id(r)])][4]), {})
        # цели findFirePoint врага - сторона игрока (validTarget без гражданских); нейтралы отдельно не считаем
        enemy_t = {u: v for u, v in tg.items() if fac.get((b, u)) == 0}
        d_min = min((v[0] for v in enemy_t.values()), default=None)
        closest = sorted(u for u, v in enemy_t.items() if v[0] == d_min)
        if t not in tg:
            cls = "unknown"
        elif closest and closest[0] == t:
            cls = "aggro"
        else:
            cls = "known"
        hist = st.get((b, t), [])
        now = next((x for x in hist if x[0] == turn), None)
        me = next((x for x in st.get((b, a), []) if x[0] == turn), None)
        age = now[2] if now else ""
        moved = ""
        if now and now[2] >= 1:
            seen = [x for x in hist if x[0] < turn and x[2] == 0]
            moved = "none" if not seen else int(seen[-1][1] != q)
        out.append({"label": label, "battle": b, "terrain": r["terrain"], "how": r["how"], "unit": a, "turn": turn,
                    "q": r["q"], "blocker": t, "src": main_src(r), "first": int(int(r["n_first"]) > 0),
                    "rep": int(int(r["n_stop"]) + int(r["n_supp"]) >= 2), "run": r["run"], "outcome": r["outcome"],
                    "goal_q": int(int(r["goal_q"]) > 0), "cls": cls, "tie": int(len(closest) > 1 and t in closest),
                    "d_b": tg[t][0] if t in tg else "", "d_min": "" if d_min is None else d_min,
                    "lof": tg[t][1] if t in tg else "", "age": age, "pos_q": int(now[1] == q) if now else "",
                    "sees": int(t in me[3]) if me else "", "moved_unseen": moved})
    path = OUT / f"known_occ_{label}.tsv"
    with open(path, "w", encoding=ENC_W, newline="") as f:
        w = csv.DictWriter(f, COLS, delimiter="\t", quoting=csv.QUOTE_NONE, escapechar="\\")
        w.writeheader()
        w.writerows(out)
    print(f"{label}: эпизодов врага {len(out)} -> {path.name}", flush=True)


def line(name, Y):
    n = len(Y)
    if not n:
        return f"    {name:22} 0"
    c = collections.Counter(r["cls"] for r in Y)
    ages = collections.Counter("-" if r["age"] == "" else ("0" if r["age"] == "0" else "1" if r["age"] == "1" else "2+")
                               for r in Y if r["cls"] != "unknown")
    mv = collections.Counter(r["moved_unseen"] for r in Y if r["cls"] != "unknown")
    return (f"    {name:22} {n:4} | aggro {c['aggro']:3} (tie {sum(int(r['tie']) for r in Y if r['cls'] == 'aggro')}) "
            f"known {c['known']:3} unknown {c['unknown']:3} | goal=Q {sum(int(r['goal_q']) for r in Y):3} "
            f"lof {sum(1 for r in Y if r['lof'] == '1'):3} | age 0/1/2+ {ages['0']}/{ages['1']}/{ages['2+']} "
            f"moved_unseen {mv[1] + mv['1']} (без снимка {mv['none']}) | pos_q {sum(1 for r in Y if r['pos_q'] == '1')} "
            f"sees {sum(1 for r in Y if r['sees'] == '1')} | timeout {sum(1 for r in Y if r['how'] == 'timeout')}")


def summary(prefixes):
    for pre in prefixes:
        R = []
        for path in sorted(OUT.glob(f"known_occ_{pre}*.tsv")):
            R += read_tsv(path)
        if not R:
            continue
        print(f"=== {pre}: эпизодов врага с чужим блокером {len(R)}")
        print(line("все", R))
        print(line("first step", [r for r in R if r["first"] == "1"]))
        print(line("mid-path only", [r for r in R if r["first"] == "0"]))
        print(line("одиночные", [r for r in R if r["rep"] == "0"]))
        print(line("повторы", [r for r in R if r["rep"] == "1"]))
        for s in ("firepoint", "patrol", "escape", "melee", "ambush", "leeroy", "other"):
            Y = [r for r in R if r["src"] == s]
            if Y:
                print(line(s, Y))
                print(line(f"{s} серия>=3", [r for r in Y if int(r["run"]) >= 3]))
                print(line(f"{s} held", [r for r in Y if r["outcome"] == "held"]))


def main():
    sys.stdout.reconfigure(encoding="utf-8")  # R-001
    ap = argparse.ArgumentParser()
    ap.add_argument("--arena", default="E:/OXCE_AIWorker/results/arena")
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("labels", nargs="+")
    a = ap.parse_args()
    if a.summary:
        summary(a.labels)
        return
    for label in a.labels:
        census(Path(a.arena), label)


if __name__ == "__main__":
    main()
