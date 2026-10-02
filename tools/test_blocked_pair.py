"""Регрессия классификатора V1 (R-176): признак «затронут» в tools/ai_speed/blocked_pair.py обязан повторять правило движка
(AiProbe::blockedStepStop / blockedStepDecide / blockedStepPlan) - память у ЛЮБОЙ остановки юнитом, в том числе посреди
пути, а не только на первом шаге решения. Образец - бой 1102 STR_ERIDIAN_TERROR из c53s23/v53s23 (юнит 1000061, ход 3,
решения 555-556: встал на 5,11,0 посреди пути, следующее решение с той же клетки выбрало тот же шаг d3). Контроль:
прежняя модель blocked_kr.classify этот случай не видит. Без игры и сборки.
  py -3.13 tools/test_blocked_pair.py"""
import gzip, json, sys, tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parent / "ai_speed"
sys.path.insert(0, str(HERE))
import blocked_pair as bp  # noqa: E402
import blocked_kr as bk  # noqa: E402

fails = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        fails.append(name)


FX = HERE / "fixtures"
c = next(iter(bp.load(FX / "r176_1102_c.rec.gz").values()))
v = next(iter(bp.load(FX / "r176_1102_v.rec.gz").values()))
would, repeat, goal, supp, first = bp.simulate(c)
check("1102 база: остановка посреди пути - V1 подавил бы решение 556", would == 1 and first == 556)
check("1102 база: физический повтор шага", repeat == 1)
wv, rv, _, sv, _ = bp.simulate(v)
check("1102 вариант: настоящее подавление в следе", sv == 1)
check("1102 вариант: повтора нет", wv == 0 and rv == 0)
check("1102: признаки совпали", bool(would) == bool(sv))
old = [x[0] for x in bk.classify(next(iter(bk.load(FX / "r176_1102_c.rec.gz").values())))]
check("контроль: прежняя модель blocked_kr случай не видит", not any(x.startswith("та же ревизия, тот же шаг") for x in old))


def rec(n, turn, unit, pos, to=(9, 9, 0)):
    return (f"seed=1 want=X [AIREC] " + json.dumps({"rec": n, "turn": turn, "unit": unit, "state": {"pos": list(pos)},
                                                    "base": {"to": list(to)}}) + "\n")


def exe(n, unit, trail):
    return f"seed=1 want=X [AIEXEC] " + json.dumps({"rec": n, "unit": unit, "trail": trail}) + "\n"


def sim(lines):
    with tempfile.TemporaryDirectory() as t:
        p = Path(t) / "s.rec.gz"
        p.write_bytes(gzip.compress("".join(lines).encode()))
        return bp.simulate(next(iter(bp.load(p).values())))


stop = "walk.stop.unit 1,1,0>2,1,0 d2 bam0 bu7 kr{}"
# первый шаг: остановлен на клетке начала, следующее решение - тот же шаг при той же ревизии
w = sim([rec(1, 1, 5, (1, 1, 0)), exe(1, 5, ["kr.dec aa", "walk.first d2", stop.format("aa")]),
         rec(2, 1, 5, (1, 1, 0)), exe(2, 5, ["kr.dec aa", "walk.first d2", stop.format("aa")])])
check("синтетика: первый шаг - подавил бы, повтор, повтор цели", w[:3] == (1, 1, 1))
# ревизия сменилась - память стёрта
w = sim([rec(1, 1, 5, (1, 1, 0)), exe(1, 5, ["kr.dec aa", "walk.first d2", stop.format("aa")]),
         rec(2, 1, 5, (1, 1, 0)), exe(2, 5, ["kr.dec bb", "walk.first d2"])])
check("синтетика: другая ревизия - не подавил бы", w[0] == 0)
# другой ход - память стёрта
w = sim([rec(1, 1, 5, (1, 1, 0)), exe(1, 5, ["kr.dec aa", "walk.first d2", stop.format("aa")]),
         rec(2, 2, 5, (1, 1, 0)), exe(2, 5, ["kr.dec aa", "walk.first d2"])])
check("синтетика: другой ход - не подавил бы", w[0] == 0)
# другой шаг с той же клетки - не подавил бы; цель та же - повтор цели
w = sim([rec(1, 1, 5, (1, 1, 0)), exe(1, 5, ["kr.dec aa", "walk.first d2", stop.format("aa")]),
         rec(2, 1, 5, (1, 1, 0)), exe(2, 5, ["kr.dec aa", "walk.first d3"])])
check("синтетика: другой шаг - не подавил бы, цель та же", w[0] == 0 and w[2] == 1)

print("итог:", "OK" if not fails else f"FAIL {len(fails)}")
sys.exit(1 if fails else 0)
