#!/usr/bin/env python3
"""Профиль засады стенда: разбор строк [AIAMB] / [AIAMBN] прогона run_one.py (флаг OXCE_AI_AMBUSHPROF=1, с build-ai43).

  py -3.13 tools/ai_speed/ambush_prof.py amb_st1 amb_bm1 [--json out.json]

Что считает прибор (AiProbe::ambushBegin..ambushEnd, вызовы в AIModule::setupAmbush): на каждый вызов setupAmbush - сколько
узлов карты просмотрено (nodes), сколько прошло дешёвые проверки (near: до 10 клеток, тот же этаж, не опасен, в досягаемости
с атакой; hidden: враг не видит; own: свой путь дошёл), сколько поисков пути врага (A* без потолка ОВ) дошло (eok) и не дошло
(efail), их раскрытые узлы A* (expok/expfail) и время (tok/tfail, мкс), сколько раз лучший менялся (taken), выбран ли узел,
ранний выход (fast). На каждый поиск врага - строка [AIAMBN]: узел, расстояние до юнита (d) и до врага (de), свой путь (own),
дошёл ли враг (ok), его ОВ и шаги (cost, len), раскрытые узлы (exp), время (us), счёт до укрытия (s0) против лучшего на тот
момент (best), укрытие (cover), итоговый счёт (s), стал ли лучшим (take). Узел, который отрицательная память засады
(OXCE_AI_AMBUSH_MEMO=1) ответила без поиска, идёт строкой [AIAMBN] ... memo=1 (exp=0, us=0): в счёт поисков не входит,
считается отдельно; в режиме проверки (=2) поиск идёт, а в [AIAMB] mver - сколько узлов память ответила, mbad - сколько
ответов разошлись с поиском (обязано быть 0). Итог памяти за бой - строка [AIAMBMEMO] (пишется и без профиля).

Ответы, которые нужны второму мнению: сколько узлов рассматривается; сколько A* успешны; сколько отсеивается уже после
дорогого A*; стоимость выбранного узла относительно остальных; сколько узлов можно было бы отвергнуть до A* по заведомо
безопасным условиям (счёт даже с укрытием не выше лучшего: s0 + 25 <= best - код берёт узел только при score > best);
сколько раскрытых узлов на запрос; время успешных и безуспешных поисков; неудачные поиски врага по вызовам - сколько из них
повторные к тому же врагу в том же вызове (неудачный A* уже обошёл весь объём, доступный врагу) и на каком этаже узел
относительно врага. Алгоритм не меняется: только счёт."""
import argparse
import json
import re
import statistics
import sys

from _common import ENC_R, ENC_W, probe_work

KV = re.compile(r"(\w+)=(-?\d+(?:,-?\d+,-?\d+)?)")
COVER_BONUS = 25  # AIModule::setupAmbush COVER_BONUS


def parse_line(body):
    out = {}
    for k, v in KV.findall(body):
        out[k] = tuple(int(x) for x in v.split(",")) if "," in v else int(v)
    return out


def read_run(work, name):
    """Строки прогона: вызовы setupAmbush, поиски врага, итог; время think из [AIPF] total, если профиль пути был включён."""
    calls, nodes, memo, total, think_us, memo_total = [], [], [], None, None, None
    log = work / ("var_" + name) / "openxcom.log"
    with open(log, encoding=ENC_R, errors="replace") as f:
        for raw in f:
            body = raw.rstrip("\n").split("\t", 2)[-1]
            if body.startswith("[AIAMB] total "):
                total = parse_line(body[14:])
            elif body.startswith("[AIAMBMEMO] "):
                memo_total = parse_line(body[12:])
            elif body.startswith("[AIAMB] "):
                calls.append(parse_line(body[8:]))
            elif body.startswith("[AIAMBN] "):
                n = parse_line(body[9:])
                n["call"] = len(calls)  # the call this search belongs to: its [AIAMB] line follows its [AIAMBN] lines
                (memo if n.get("memo") else nodes).append(n)  # a node the memo answered is not a search
            elif body.startswith("[AIPF] total "):
                think_us = parse_line(body[13:]).get("tt")
    return calls, nodes, memo, total, think_us, memo_total


def pct(a, b):
    return f"{100.0 * a / b:5.1f}%" if b else "    -"


def dist(xs):
    if not xs:
        return "-"
    xs = sorted(xs)
    return f"ср {statistics.mean(xs):.0f}, медиана {xs[len(xs) // 2]}, макс {xs[-1]}"


def summary(name, calls, nodes, memo, total, think_us, memo_total):
    t = total
    print(f"=== {name}")
    if memo_total:
        print(f"  отрицательная память засады: режим {memo_total['mode']}, узлов отвечено без поиска {memo_total['skip']},"
              f" проверено поиском {memo_total['verify']}, разошлось {memo_total['bad']}" + (" - ОШИБКА" if memo_total["bad"] else ""))
    if not t:
        print("  нет строки [AIAMB] total - бой не дошёл до итога или флаг выключен")
        return {"memo": memo_total} if memo_total else {}
    out = {"calls": t["calls"], "chosen": t["chosen"], "fast": t["fast"], "us": t["us"], "think_us": think_us,
           "nodes": t["nodes"], "near": t["near"], "hidden": t["hidden"], "own": t["own"],
           "eok": t["eok"], "efail": t["efail"], "tok": t["tok"], "tfail": t["tfail"], "expok": t["expok"], "expfail": t["expfail"]}
    print(f"  вызовов setupAmbush {t['calls']}, выбрали узел {t['chosen']} ({pct(t['chosen'], t['calls'])}), ранний выход {t['fast']};"
          f" время {t['us'] / 1e6:.2f} с" + (f" = {pct(t['us'], think_us)} think" if think_us else ""))
    print(f"  узлов просмотрено {t['nodes']}: рядом и в досягаемости {t['near']} ({pct(t['near'], t['nodes'])}),"
          f" скрыты от врага {t['hidden']} ({pct(t['hidden'], t['nodes'])}), свой путь дошёл {t['own']} ({pct(t['own'], t['nodes'])})")
    print(f"  свой путь: {t['ownn']} поисков, дошло {t['ownok']}, раскрыто узлов {t['ownexp']}, {t['ownus'] / 1e6:.2f} с")
    e = t["eok"] + t["efail"]
    print(f"  путь врага (A* без потолка ОВ): {e} поисков, дошло {t['eok']} ({pct(t['eok'], e)}), не дошло {t['efail']};"
          f" время дошедших {t['tok'] / 1e6:.2f} с ({t['tok'] / t['eok'] / 1e3 if t['eok'] else 0:.2f} мс на поиск),"
          f" не дошедших {t['tfail'] / 1e6:.2f} с ({t['tfail'] / t['efail'] / 1e3 if t['efail'] else 0:.2f} мс)")
    print(f"  раскрыто узлов A*: дошедшие {t['expok']} ({t['expok'] / t['eok'] if t['eok'] else 0:.0f} на поиск),"
          f" не дошедшие {t['expfail']} ({t['expfail'] / t['efail'] if t['efail'] else 0:.0f} на поиск)")
    wasted = e - t["chosen"]
    print(f"  отсеяно после дорогого A*: {wasted} из {e} ({pct(wasted, e)}) - не дошёл враг {t['efail']},"
          f" дошёл, но счёт не выше лучшего {t['eok'] - t['taken']}, стал лучшим и перебит позже {t['taken'] - t['chosen']}")
    out["wasted"] = wasted
    if memo_total:
        out["memo"] = memo_total
        print(f"  память засады по вызовам: отвечено без поиска {t.get('memo', 0)} в {sum(1 for c in calls if c.get('memo'))} вызовах,"
              f" проверено {t.get('mver', 0)}, разошлось {t.get('mbad', 0)}; узлов memo=1 в строках {len(memo)}")
    if nodes:
        # safe pre-filter: the node cannot beat the best so far even with cover - the code takes a node only at score > best
        safe = [n for n in nodes if n["s0"] + COVER_BONUS <= n["best"]]
        safe_us = sum(n["us"] for n in safe)
        print(f"  можно было отвергнуть до A* врага без изменения выбора (s0 + {COVER_BONUS} <= best): {len(safe)} из {len(nodes)}"
              f" ({pct(len(safe), len(nodes))}), их время {safe_us / 1e6:.2f} с ({pct(safe_us, t['tok'] + t['tfail'])} времени A* врага)")
        out["safe_skip"] = len(safe)
        out["safe_skip_us"] = safe_us
        # the same with the cover looked up before the search (faceWindow is cheap): the node cannot beat the best as it is
        nocover = [n for n in nodes if n["cover"] != -1 and n["s0"] + (COVER_BONUS if n["cover"] else 0) <= n["best"]]
        print(f"  ... и ещё при проверке укрытия до A* (только дошедшие, у не дошедших укрытие не считалось): {len(nocover)}")
        print(f"  раскрытые узлы на поиск врага: дошедшие {dist([n['exp'] for n in nodes if n['ok']])};"
              f" не дошедшие {dist([n['exp'] for n in nodes if not n['ok']])}")
        print(f"  время поиска врага, мкс: дошедшие {dist([n['us'] for n in nodes if n['ok']])};"
              f" не дошедшие {dist([n['us'] for n in nodes if not n['ok']])}")
        print(f"  ОВ пути врага у дошедших: {dist([n['cost'] for n in nodes if n['ok']])}; шагов {dist([n['len'] for n in nodes if n['ok']])}")
        print(f"  расстояние узла от врага (de), клеток: дошедшие {dist([n['de'] for n in nodes if n['ok']])};"
              f" не дошедшие {dist([n['de'] for n in nodes if not n['ok']])}")
        # the chosen node against the others of its call: rank by own cost and by distance among the nodes the enemy search ran on
        by_call = {}
        for n in nodes:
            by_call.setdefault((n["u"], n["e"]), []).append(n)
        ranks_own, ranks_de, first_wins, kept = [], [], 0, 0
        for c in calls:
            if not c["chosen"]:
                continue
            group = by_call.get((c["u"], c["e"]), [])
            win = [n for n in group if n["pos"] == c["target"]]
            if not win:
                continue
            w = win[-1]
            ranks_own.append(1 + sum(1 for n in group if n["own"] < w["own"]))
            ranks_de.append(1 + sum(1 for n in group if n["de"] < w["de"]))
            kept += 1
            if next((n for n in group if n["take"]), None) is w:
                first_wins += 1
        print(f"  выбранный узел среди узлов своего вызова (с поиском врага): по своему пути {dist(ranks_own)} место;"
              f" по близости к врагу {dist(ranks_de)} место; первый ставший лучшим и остался им в {first_wins} из {kept}")
        out["rank_own"] = ranks_own
        # failed enemy searches by call: a failed A* has walked the whole volume the enemy can reach, so every later failure
        # to the same enemy in the same call asks a question that walk already answered (not acted on - a figure for the audit)
        fails = {}
        for n in nodes:
            if not n["ok"]:
                fails.setdefault(n["call"], []).append(n)
        if fails:
            beyond = sum(len(v) - 1 for v in fails.values())
            first_us = sum(v[0]["us"] for v in fails.values())
            rest_us = sum(x["us"] for v in fails.values() for x in v[1:])
            per = {}
            for v in fails.values():
                per[len(v)] = per.get(len(v), 0) + 1
            dz = {}
            for v in fails.values():
                for n in v:
                    dz[n["dze"]] = dz.get(n["dze"], 0) + 1
            print(f"  неудачные A* врага по вызовам: вызовов {len(fails)}, неудач {t['efail']}, из них повторные к тому же врагу"
                  f" в том же вызове {beyond} ({rest_us / 1e6:.2f} с" + (f" = {pct(rest_us, think_us)} think" if think_us else "") +
                  f"; первые неудачи вызовов {first_us / 1e6:.2f} с); неудач на вызов: " + ", ".join(f"{k}×{v}" for k, v in sorted(per.items())))
            print("  этаж узла минус этаж врага у неудач (dze): " + ", ".join(f"{k}: {v}" for k, v in sorted(dz.items())))
            out["efail_calls"] = len(fails)
            out["efail_beyond_first"] = beyond
            out["efail_beyond_first_us"] = rest_us
    heavy = sorted(calls, key=lambda c: -c["us"])[:5]
    if heavy:
        print("  самые дорогие вызовы (юнит: мкс, узлов/рядом/скрыто/свой, A* врага дошло/нет, выбран):")
        for c in heavy:
            print(f"    {c['u']:5d}: {c['us']:8d}  {c['nodes']}/{c['near']}/{c['hidden']}/{c['own']}  {c['eok']}/{c['efail']}  {c['chosen']}")
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8")  # R-001
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("names", nargs="+", help="имена прогонов run_one.py")
    ap.add_argument("--json", default="", help="сводку всех прогонов записать в этот файл")
    a = ap.parse_args()
    work = probe_work()
    allsum = {}
    for name in a.names:
        calls, nodes, memo, total, think_us, memo_total = read_run(work, name)
        allsum[name] = summary(name, calls, nodes, memo, total, think_us, memo_total)
    if a.json:
        with open(a.json, "w", encoding=ENC_W) as f:
            json.dump(allsum, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
