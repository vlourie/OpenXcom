#!/usr/bin/env python3
"""Перепись неудачных поисков пути врага в setupAmbush по логам стенда (OXCE_AI_AMBUSHPROF=1, память засады выключена):
три числа для второго мнения (01.10) - сколько неудач можно отвергнуть до A* по простому статическому признаку, сколько
из них другой этаж (узел всегда на этаже юнита, dze = z узла - z врага), сколько разных врагов, клеток и узлов их дают.
Только счёт по строкам [AIAMBN] / [AIAMB] - ИИ и движок не трогает.

  py -3.13 tools/ai_speed/ambush_fail.py am_st0c am_bm1 am_ct0

Что печатает: поиски врага (дошёл / не дошёл), неудачи ранним отказом до A* (exp=0: tryCalculateFinalPosition отверг
клетку - за картой, занята, часть непроходима для типа движения) и полным обходом объёма врага (exp>0: A* опустошил
открытый список); первая неудача вызова к врагу - потолок выигрыша отсева до A* после памяти (повторы память уже снимает);
разный этаж среди неудач и среди удач (признак негоден, если он есть и у удач); кто - враги, (враг, клетка), узлы,
(враг, узел), вызовы, засадчики; объём врага при неудаче (раскрыто узлов - размер его досягаемого куска карты) и при
удаче; расстояние узел-враг; та же пара в другом вызове - для справки, кэш между решениями отвергнут (DECISIONS 01.10).
Разбор строк - ambush_prof.read_run."""
import sys
from collections import Counter

from _common import probe_work
from ambush_prof import read_run


def dist(xs):
    if not xs:
        return "-"
    xs = sorted(xs)
    return f"мин {xs[0]}, медиана {xs[len(xs) // 2]}, макс {xs[-1]}, ср {sum(xs) / len(xs):.0f}"


def census(name):
    calls, nodes, memo, total, think_us, memo_total = read_run(probe_work(), name)
    print(f"=== {name}: вызовов {len(calls)}, поисков врага {len(nodes)}, think {think_us / 1e6 if think_us else 0:.1f} с")
    if memo:
        print(f"  !! в логе {len(memo)} узлов, отвеченных памятью - перепись неполная, нужен прогон с OXCE_AI_AMBUSH_MEMO=0")
    if not nodes:
        own0 = sum(1 for c in calls if c.get("own", 0) == 0)
        print(f"  поисков врага нет: вызовов без своего пути к узлу {own0} из {len(calls)}; узлов near {sum(c.get('near', 0) for c in calls)},"
              f" hidden {sum(c.get('hidden', 0) for c in calls)}, own {sum(c.get('own', 0) for c in calls)}; засада всего {total.get('us', 0) / 1e6 if total else 0:.2f} с")
        return
    for n in nodes:  # the call's [AIAMB] line follows its node lines: n["call"] is its index in calls
        c = calls[n["call"]] if n["call"] < len(calls) else {}
        n["epos"] = c.get("epos", (-1, -1, -1))
    fail = [n for n in nodes if not n["ok"]]
    ok = [n for n in nodes if n["ok"]]
    f_early = [n for n in fail if n["exp"] == 0]
    f_sweep = [n for n in fail if n["exp"] > 0]
    sec = lambda xs: sum(n["us"] for n in xs) / 1e6
    print(f"  дошло {len(ok)} ({sec(ok):.2f} с), не дошло {len(fail)} ({sec(fail):.2f} с): ранний отказ до A* (exp=0) {len(f_early)}"
          f" ({sec(f_early):.2f} с), полный обход объёма врага (exp>0) {len(f_sweep)} ({sec(f_sweep):.2f} с)")
    first = {}
    for n in fail:
        first.setdefault((n["call"], n["e"]), n)
    fs = [n for n in first.values() if n["exp"] > 0]
    print(f"  первая неудача вызова к врагу: {len(first)} ({sec(first.values()):.2f} с), из них полным обходом {len(fs)} ({sec(fs):.2f} с)"
          f" - потолок выигрыша отсева до A* после памяти")
    dz = Counter(n["dze"] for n in fail)
    hz = [n for n in fail if n["dze"] != 0]
    hzs = [n for n in hz if n["exp"] > 0]
    print(f"  разный этаж (dze != 0): неудач {len(hz)} из {len(fail)} ({sec(hz):.2f} с), полным обходом {len(hzs)};"
          f" по dze {dict(sorted(dz.items()))}; удач с разным этажом {sum(1 for n in ok if n['dze'] != 0)} из {len(ok)}")
    es = Counter(n["e"] for n in fail)
    print(f"  кто: врагов {len(es)}, (враг, клетка врага) {len(Counter((n['e'], n['epos']) for n in fail))}, узлов {len(Counter(n['pos'] for n in fail))},"
          f" (враг, узел) {len(Counter((n['e'], n['pos']) for n in fail))}, вызовов с неудачей {len(Counter(n['call'] for n in fail))},"
          f" засадчиков {len(set(n['u'] for n in fail))} из {len(set(n['u'] for n in nodes))} с поисками")
    print("  враги по числу неудач (враг: неудач / клеток врага / узлов / обход A* медиана / по dze):")
    for e, k in es.most_common(8):
        xs = [n for n in fail if n["e"] == e]
        print(f"    {e}: {k} / {len(set(n['epos'] for n in xs))} / {len(set(n['pos'] for n in xs))} /"
              f" {sorted(n['exp'] for n in xs)[len(xs) // 2]} / {dict(Counter(n['dze'] for n in xs))}")
    print("  объём врага (раскрыто узлов) по (враг, клетка врага) при неудаче полным обходом:")
    for (e, ep), k in Counter((n["e"], n["epos"]) for n in f_sweep).most_common(10):
        xs = sorted(set(n["exp"] for n in f_sweep if n["e"] == e and n["epos"] == ep))
        print(f"    e={e} в {ep}: {k} неудач, exp {xs[:5]}{'...' if len(xs) > 5 else ''}")
    ex = [n["exp"] for n in f_sweep]
    print(f"  объём врага при неудаче: {dist(ex)}; обходов до 20 узлов {sum(1 for x in ex if x <= 20)}, свыше 200 {sum(1 for x in ex if x > 200)};"
          f" мкс на узел {sum(n['us'] for n in f_sweep) / max(1, sum(ex)):.1f}")
    print(f"  объём при удаче: {dist([n['exp'] for n in ok])}")
    print(f"  расстояние узел-враг (de): неудачи {dist([n['de'] for n in fail])}; удачи {dist([n['de'] for n in ok])}")
    pairs = Counter((n["e"], n["pos"]) for n in fail)
    same = Counter((n["e"], n["epos"], n["pos"]) for n in fail)
    print(f"  для справки: та же пара (враг, узел) в другом вызове {sum(k - 1 for k in pairs.values() if k > 1)} раз,"
          f" из них враг с той же клетки {sum(k - 1 for k in same.values() if k > 1)}")


if __name__ == "__main__":
    for name in sys.argv[1:]:
        census(name)
