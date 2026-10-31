#!/usr/bin/env python3
"""REPEATED_FAILED_GOAL - пассивная перепись по архивам серий (второе мнение 02.10, аудит п. 17.6). Движок не трогается.

Срыв решения - причина из следа [AIEXEC]:
  последняя walk.stop.<причина> (unit, energy, reserve, tu, spotted, reaction, turnspot, invalid);
  supp_none - V1 подавил первый шаг, обхода нет (blockstep.suppressed dX -> none);
  nomove - ходьба (t=2) без остановки и подавления, юнит не сдвинулся и ОВ не потратил.
Сдвиг сорванного: moved (сменил клетку), spent (потратил ОВ на месте), idle (ничего).
Повтор - следующее решение того же юнита в том же ходу с той же base.to и тем же t.

Что пишется про каждый повтор:
  kr - известная обстановка между срывом и повтором: kr остановки юнитом против kr.dec повтора, у supp_none kr.dec
       против kr.dec. kr.dec движок пишет, только если юнит стоит там, где его остановил юнит (AiProbe, krWatch),
       поэтому у срывов не по юниту - na;
  own - свои клетка и ОВ в начале повтора те же, что в начале сорванного;
  passed - сам повтор сдвинулся: при own=same это внешняя перемена (верхняя граница ложного подавления любой памяти
       «эта цель сорвалась»);
  pstop - прогноз остановки патруля из [AIPATROL] повтора (energy, nopath, reserve, kneel, tu, occupied, none).

  py -3.13 tools/ai_speed/failed_goal.py --arena E:/OXCE_AIWorker/results/arena c53s23 c53s24 ... --label c53
Построчно - runs/failed_goal_<метка>.tsv, цепочки - runs/failed_goal_chains_<метка>.tsv.
"""
import argparse
import collections
import gzip
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import OUT, ENC_W  # noqa: E402

STOP = re.compile(r"walk\.stop\.unit (\d+,\d+,\d+)>(\d+,\d+,\d+) d(\d+) .* bu(\d+) kr([0-9a-f]+)")
SUPP = re.compile(r"blockstep\.suppressed d(\d+) -> (\S+)")
ABORT_CAP = 200     # AIModule::think: счётчик сорванных ходов кончает ход юнита
SIDES = {0: "бот", 1: "враг", 2: "нейтралы"}


def key_of(head):
    f = dict(p.split("=", 1) for p in head.split(" [", 1)[0].split() if "=" in p)
    return f.get("seed"), f.get("want")


def cell(p):
    return ",".join(str(x) for x in p) if p else None


def load(rec_gz, path_gz):
    """бой -> {rec: решение}"""
    B = collections.defaultdict(dict)
    with gzip.open(rec_gz, "rt", encoding="utf-8") as f:
        for line in f:
            if "{" not in line:
                continue
            i = line.index("{")
            head = line[:i]
            if "[AIREC]" in head:
                r = json.loads(line[i:])
                b = r.get("base") or {}
                d = B[key_of(head)].setdefault(r["rec"], {})
                d.update(turn=r["turn"], side=r["side"], unit=r["unit"], start=cell(r["state"]["pos"]), tu0=r["state"]["tu"],
                         to=cell(b.get("to")), t=b.get("t"), src=b.get("src") or "?", exp=b.get("exp"), sid=r["state"]["state_id"])
            elif "[AIEXEC]" in head:
                r = json.loads(line[i:])
                d = B[key_of(head)].setdefault(r["rec"], {})
                trail = r.get("trail") or []
                d["stops"] = [(m.group(1), m.group(2), int(m.group(4)), m.group(5)) for m in (STOP.search(t) for t in trail) if m]
                d["supp"] = [m.group(2) for m in (SUPP.search(t) for t in trail) if m]
                d["krdec"] = next((t.split()[1] for t in trail if t.startswith("kr.dec ")), None)
                d["why"] = next((t.split()[0][len("walk.stop."):] for t in reversed(trail) if t.startswith("walk.stop.")), None)
                d["spent"] = r.get("spent", 0)
                d["end"] = cell(r.get("pos"))
    if path_gz.is_file():
        with gzip.open(path_gz, "rt", encoding="utf-8") as f:
            for line in f:
                if "[AIPATROL]" not in line:
                    continue
                i = line.index("{")
                r = json.loads(line[i:])
                d = B[key_of(line[:i])].get(r["rec"])
                if d is not None:
                    d["pstop"] = r.get("stop")
    return B


def failure(d):
    if d.get("why"):
        return d["why"]
    if "none" in d.get("supp", []):
        return "supp_none"
    if d.get("t") == 2 and "end" in d and d.get("spent", 0) == 0 and d["end"] == d.get("start"):
        return "nomove"
    return None


def progress(d):
    return "moved" if d.get("end") != d.get("start") else ("spent" if d.get("spent", 0) else "idle")


def kr_after(d):
    """ревизия известного сразу после срыва"""
    return d["stops"][-1][3] if d.get("stops") else d.get("krdec")


def end_of(chain, last, nxt):
    if chain["n"] >= ABORT_CAP:
        return "abort_cap"
    if failure(last) is None:
        return "succeeded"
    if nxt is None or nxt["turn"] != chain["turn"]:
        return "turn_end"
    return "new_goal"


def battle(recs):
    rows, chains = [], []
    byunit = collections.defaultdict(list)
    for rec in sorted(recs):
        if "unit" in recs[rec]:
            byunit[recs[rec]["unit"]].append((rec, recs[rec]))
    for u, seq in byunit.items():
        chain = None
        for j, (rec, d) in enumerate(seq):
            prev = seq[j - 1][1] if j else None
            fp = failure(prev) if prev else None
            if (fp and prev["turn"] == d["turn"] and d.get("to") is not None and prev.get("to") == d["to"]
                    and prev.get("t") == d.get("t")):
                ka, kb = kr_after(prev), d.get("krdec")
                rows.append(dict(
                    unit=u, side=d["side"], turn=d["turn"], rec=rec, fail=fp, prog=progress(prev), src=d["src"], exp=d.get("exp"),
                    kr="na" if ka is None or kb is None else ("same" if ka == kb else "changed"),
                    sid="same" if prev["sid"] == d["sid"] else "changed",
                    own="same" if prev["start"] == d["start"] and prev["tu0"] == d["tu0"] else "changed",
                    passed=int(progress(d) == "moved"), pstop=d.get("pstop"),
                    goal_blocked=int(bool(prev.get("stops")) and prev["stops"][-1][1] == d["to"])))
                if chain is None:
                    chain = dict(unit=u, side=d["side"], turn=d["turn"], goal=d["to"], src=d["src"], first_fail=fp, n=1)
                chain["n"] += 1
            else:
                if chain:
                    chain["end"] = end_of(chain, prev, d)
                    chains.append(chain)
                chain = None
        if chain:
            chain["end"] = end_of(chain, seq[-1][1], None)
            chains.append(chain)
    return rows, chains


def tops(c, n=8):
    tot = sum(c.values()) or 1
    return ", ".join(f"{k} {v} ({100 * v / tot:.0f}%)" for k, v in c.most_common(n))


def main():
    sys.stdout.reconfigure(encoding="utf-8")   # R-001: вывод в файл иначе в cp1252
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--arena", required=True)
    ap.add_argument("--label", required=True, help="метка итога: runs/failed_goal_<метка>.tsv")
    ap.add_argument("series", nargs="+")
    a = ap.parse_args()
    arena = Path(a.arena)
    allrows, allchains, per_battle = [], [], collections.Counter()
    for s in a.series:
        B = load(arena / f"{s}.rec.gz", arena / f"{s}.path.gz")
        for key, recs in B.items():
            rows, chains = battle(recs)
            for r in rows + chains:
                r["series"], r["seed"], r["want"] = s, key[0], key[1]
            allrows += rows
            allchains += chains
            if rows:
                per_battle[(s, key[0], key[1])] = len(rows)
    cols = ("series", "seed", "want", "unit", "side", "turn", "rec", "fail", "prog", "src", "exp", "kr", "sid", "own", "passed",
            "pstop", "goal_blocked")
    with open(OUT / f"failed_goal_{a.label}.tsv", "w", encoding=ENC_W, newline="") as f:
        f.write("\t".join(cols) + "\n")
        f.writelines("\t".join(str(r[c]) for c in cols) + "\n" for r in allrows)
    ccols = ("series", "seed", "want", "unit", "side", "turn", "goal", "src", "first_fail", "n", "end")
    with open(OUT / f"failed_goal_chains_{a.label}.tsv", "w", encoding=ENC_W, newline="") as f:
        f.write("\t".join(ccols) + "\n")
        f.writelines("\t".join(str(c[k]) for k in ccols) + "\n" for c in allchains)

    print(f"=== {a.label}: повторов цели после срыва {len(allrows)}, цепочек {len(allchains)}, боёв с повторами {len(per_battle)}")
    for side in sorted({r["side"] for r in allrows}):
        rs = [r for r in allrows if r["side"] == side]
        print(f" сторона {side} ({SIDES.get(side, '?')}): {len(rs)}; источник {tops(collections.Counter(r['src'] for r in rs), 5)}")
        for fl, n in collections.Counter(r["fail"] for r in rs).most_common():
            sub = [r for r in rs if r["fail"] == fl]
            idle = [r for r in sub if r["prog"] == "idle"]
            passed = sum(r["passed"] for r in idle if r["own"] == "same" and r["kr"] != "changed")
            line = (f"   {fl} {n}: сдвиг {tops(collections.Counter(r['prog'] for r in sub), 3)}; kr {tops(collections.Counter(r['kr'] for r in sub), 3)};"
                    f" источник {tops(collections.Counter(r['src'] for r in sub), 3)}")
            if idle:
                line += f"; без сдвига {len(idle)}, из них повтор прошёл при тех же своих ОВ и клетке {passed}"
            ps = collections.Counter(r["pstop"] for r in idle if r["pstop"])
            if ps:
                line += f"; прогноз патруля {tops(ps, 4)}"
            gb = sum(r["goal_blocked"] for r in sub)
            if gb:
                line += f"; цель - клетка блокирующего {gb}"
            print(line)
        cs = [c for c in allchains if c["side"] == side]
        ln = collections.Counter("2" if c["n"] == 2 else "3-5" if c["n"] <= 5 else "6-20" if c["n"] <= 20
                                 else "21-199" if c["n"] < ABORT_CAP else "200+" for c in cs)
        print(f"   цепочки {len(cs)}: длина {tops(ln)}; конец {tops(collections.Counter(c['end'] for c in cs))}")
    print(" боёв с наибольшим числом повторов:", ", ".join(f"{s}/{sd}/{w}:{n}" for (s, sd, w), n in per_battle.most_common(8)))


if __name__ == "__main__":
    main()
