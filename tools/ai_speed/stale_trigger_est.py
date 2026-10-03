"""PATROL_STALE_ON_FAILURE (гипотеза, аудит п. 17.25): проверять сохранённый узел патруля только после признака беды,
а не на каждом обдумывании. Оценка по записям [AIREC] / [AIEXEC] без новой сборки.
  py -3.13 tools/ai_speed/stale_trigger_est.py <rec.gz> [...]

Признак - по исполнению хода патрулём этого же юнита к этому же узлу N (решение со слотом p, источник patrol.node, цель N):
  A - ход кончился walk.stop.unit;
  B - ход кончился не на N (любая причина остановки, в том числе ОВ);
  B2 - то же, но не из-за ОВ, энергии, резерва (walk.stop.tu / energy / reserve - плановая остановка длинного пути);
  C - ход без продвижения: юнит остался на месте.
Режим: признак ставит флаг (юнит, N), следующее решение юнита проверяет узел и снимает флаг.
Сброс в B (след patrol.stale old N в решении r) пойман без задержки, если последний признак по (юнит, N) до r пришёлся на
решение, за которым следующее решение юнита - r. Иначе флаг сняла проверка раньше r (там путь был) - сброс пропущен.
Проверок по признаку - число признаков; без пути - те, за которыми следующее решение юнита и есть сброс."""
import collections, gzip, json, sys

sys.stdout.reconfigure(encoding="utf-8")
KINDS = ("A", "B", "B2", "C")
PLANNED = ("walk.stop.tu", "walk.stop.energy", "walk.stop.reserve")


def pos3(s):
    return tuple(int(v) for v in s.split(","))


def battles(path):
    """seed -> список решений по порядку: (rec, unit, side, base, trail, exec или None)."""
    out = collections.defaultdict(list)
    last = {}
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            for tag in ("[AIREC] ", "[AIEXEC] "):
                i = line.find(tag)
                if i >= 0:
                    break
            else:
                continue
            try:
                r = json.loads(line[i + len(tag):])
            except ValueError:
                continue
            seed = line.split("seed=", 1)[1].split(" ", 1)[0] if "seed=" in line else "?"
            if tag == "[AIREC] ":
                b = r.get("base") or {}
                d = {"rec": r["rec"], "unit": r["unit"], "side": "p" if r.get("side") == 0 else "h", "base": b,
                     "trail": (b.get("reason") or {}).get("trail") or [], "pos": tuple((r.get("state") or {}).get("pos") or ()),
                     "exec": None}
                out[seed].append(d)
                last[(seed, r["rec"])] = d
            else:
                d = last.get((seed, r.get("rec")))
                if d is not None:
                    d["exec"] = r
    return out


tot = collections.Counter()
for path in sys.argv[1:]:
    for seed, decs in battles(path).items():
        by_unit = collections.defaultdict(list)
        for d in decs:
            by_unit[d["unit"]].append(d)
        for unit, seq in by_unit.items():
            side = seq[0]["side"]
            # признаки по решению: индекс решения -> {вид: узел}
            trig = {}
            for k, d in enumerate(seq):
                b, e = d["base"], d["exec"]
                if not e or b.get("slot") != "p" or b.get("src") != "patrol.node" or not b.get("to"):
                    continue
                node = tuple(b["to"])
                end = tuple(e.get("pos") or ())
                tr = e.get("trail") or []
                kinds = set()
                if any(t.startswith("walk.stop.unit") for t in tr):
                    kinds.add("A")
                if end != node:
                    kinds.add("B")
                    if not any(t.startswith(PLANNED) for t in tr):
                        kinds.add("B2")
                if end == d["pos"]:
                    kinds.add("C")
                if kinds:
                    trig[k] = (node, kinds)
            # проверки по признаку и их ответ
            resets = {}
            for k, d in enumerate(seq):
                for t in d["trail"]:
                    if t.startswith("patrol.stale old "):
                        resets[k] = pos3(t.split()[2])
            for k, (node, kinds) in trig.items():
                nxt = k + 1 if k + 1 < len(seq) else None
                hit = nxt is not None and resets.get(nxt) == node
                for kd in kinds:
                    tot[(side, kd, "проверок")] += 1
                    tot[(side, kd, "без пути" if hit else "путь есть")] += 1
            for r, node in resets.items():
                tot[(side, "*", "сбросов")] += 1
                for kd in KINDS:
                    prev = [k for k, (n, ks) in trig.items() if k < r and n == node and kd in ks]
                    if not prev:
                        tot[(side, kd, "нет признака")] += 1
                    elif max(prev) + 1 == r:
                        tot[(side, kd, "пойман сразу")] += 1
                    else:
                        tot[(side, kd, "признак раньше, флаг снят")] += 1

for side in ("h", "p"):
    n = tot[(side, "*", "сбросов")]
    print(f"== сторона {side}: сбросов {n}")
    print("| признак | пойман сразу | признак раньше, флаг снят | нет признака | проверок по признаку | без пути | путь есть |")
    print("|---|---|---|---|---|---|---|")
    for kd in KINDS:
        g = lambda x: tot[(side, kd, x)]
        print(f"| {kd} | {g('пойман сразу')} | {g('признак раньше, флаг снят')} | {g('нет признака')} | {g('проверок')} | {g('без пути')} | {g('путь есть')} |")
