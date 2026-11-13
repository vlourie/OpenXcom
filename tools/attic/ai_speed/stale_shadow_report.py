"""STALE_REACH_SHADOW (аудит п. 17.25): профиль поиска пути проверки STALE и тот же вопрос другим поиском.
Читает строки "[AIPF] stale ..." из result.txt прогонов (OXCE_AI_STALE_SHADOW=1 вместе с OXCE_AI_STALE_PATROL_NODE).
  py -3.13 tools/ai_speed/stale_shadow_report.py <result.txt или папка прогона> [...]

Настоящий поиск: b - прямой путь (bresenham), a - A* нашёл, f - A* не нашёл, r - отказ до поиска.
Тень w<N>: ответ/узлы/цена/нс; ответ 1 найден, 0 нет (вся связная часть пройдена, срез по cap ничего не отрезал),
2 не решено (cap отрезал клетку, до которой поиск так и не дошёл), -1 отказ до поиска.
Замена «точная», если ответ тени совпадает с настоящим: 1 у a/b, 0 у f, -1 у r; 2 у f - откат на настоящий A*.
Опасно: тень 1 при f (путь есть, A* не нашёл) и тень 0 при a/b (тень не нашла существующий путь)."""
import collections, re, statistics, sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
RX = re.compile(r"\[AIPF\] stale (.*)$")


def files(args):
    for a in args:
        p = Path(a)
        if p.is_dir():
            yield from sorted(p.rglob("result.txt"))
        else:
            yield p


def parse(line):
    m = RX.search(line)
    if not m:
        return None
    kv = dict(t.split("=", 1) for t in m.group(1).split() if "=" in t)
    r = {"side": kv["side"], "d": int(kv["d"]), "real": kv["real"], "exp": int(kv["exp"]), "cost": int(kv["cost"]),
         "ns": int(kv["ns"]), "w": {}}
    for k, v in kv.items():
        if k.startswith("w") and k[1:].isdigit():
            ans, exp, cost, ns = (int(x) for x in v.split("/"))
            r["w"][int(k[1:])] = (ans, exp, cost, ns)
    return r


def med(xs):
    return statistics.median(xs) if xs else 0


def report(name, rows):
    print(f"== {name}: проверок {len(rows)}")
    if not rows:
        return
    by = collections.defaultdict(list)
    for r in rows:
        by[r["real"]].append(r)
    tot_ns = sum(r["ns"] for r in rows)
    print("| настоящий | проверок | время, мс | доля времени | узлов A* (медиана / среднее) | расстояние (медиана) | нс на проверку (медиана) |")
    print("|---|---|---|---|---|---|---|")
    for k in "bafr":
        g = by.get(k, [])
        if not g:
            continue
        ns = sum(r["ns"] for r in g)
        exps = [r["exp"] for r in g]
        print(f"| {k} | {len(g)} | {ns / 1e6:.1f} | {100 * ns / tot_ns:.1f} % | {med(exps):.0f} / {sum(exps) / len(g):.0f} | "
              f"{med([r['d'] for r in g]):.0f} | {med([r['ns'] for r in g]):.0f} |")
    b_med = med([r["ns"] for r in by.get("b", [])])
    weights = sorted({w for r in rows for w in r["w"]})
    print("| тень | совпало | откат (2 при f) | опасно: 1 при f | опасно: 0 при a/b | прочее | узлов на a (сумма) | время тени на a, мс | оценка замены, мс | быстрее в |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for w in weights:
        same = back = d1 = d0 = other = 0
        exp_a = ns_a = 0
        new = 0
        for r in rows:
            ans, exp, cost, ns = r["w"][w]
            k = r["real"]
            ok = (k in "ab" and ans == 1) or (k == "f" and ans == 0) or (k == "r" and ans == -1)
            if ok:
                same += 1
            elif k == "f" and ans == 2:
                back += 1
            elif k == "f" and ans == 1:
                d1 += 1
            elif k in "ab" and ans == 0:
                d0 += 1
            else:
                other += 1
            if k == "a":
                exp_a += exp
                ns_a += ns
            # замена: прямой путь и отказ - как сейчас; A* - попытка прямого пути (медиана b) плюс тень; откат - плюс настоящий
            if k in "br":
                new += r["ns"]
            else:
                new += b_med + ns + (r["ns"] if (k == "f" and ans == 2) or (k == "a" and ans != 1) else 0)
        print(f"| w{w} | {same} | {back} | {d1} | {d0} | {other} | {exp_a} | {ns_a / 1e6:.1f} | {new / 1e6:.1f} | {tot_ns / max(new, 1):.2f} |")
    a = by.get("a", [])
    if a:
        print("  цена пути на a: настоящий / тень w1 / тень w-макс, медиана:",
              med([r["cost"] for r in a]), med([r["w"][weights[0]][2] for r in a]), med([r["w"][weights[-1]][2] for r in a]))
        far = sorted(a, key=lambda r: -r["ns"])[:5]
        print("  самые дорогие a: " + "; ".join(f"d={r['d']} exp={r['exp']} ns={r['ns']} " +
                                                 " ".join(f"w{w}={r['w'][w][1]}" for w in weights) for r in far))


allrows = []
for f in files(sys.argv[1:]):
    rows = []
    with open(f, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            r = parse(line)
            if r:
                rows.append(r)
    report(str(f.parent.name if f.name == "result.txt" else f.name), rows)
    allrows += rows
if len(sys.argv) > 2:
    report("все", allrows)
