"""Разбор замера поисков клеток CELL_PROF (OXCE_AI_CELLPROF=1): архивы <метка>.cell.gz серий ai_arena.

Строка архива: "seed=N want=M [AICELL] {json}" - одна на поиск ИИ (fp - точка стрельбы findFirePoint, amb - засада
setupAmbush, esc - бегство setupEscape). Поля - AiProbe::cellSearch. По каждому поиску и стороне печатает:
время цикла (ns реального поиска; тень nsFull/nsZ/nsFar - цена замера, в игре её нет), окно и выход по порогу,
насколько выбранная клетка хуже лучшей в окне (rank - сколько клеток окна лучше выбранной), что дают другие уровни
(zBest) и клетки за окном (farBest), mismatch (обязан быть 0: теневой счёт выбранной клетки = реальному).

Запуск: py -3.13 tools/ai_cell_report.py <файл.cell.gz> [...] [--out отчёт.md]
"""
import argparse
import gzip
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

CTX = {"fp": "точка стрельбы (порог 125)", "amb": "засада (порог 80)", "esc": "бегство (порог 100)"}
SIDE = {0: "игрок (бот)", 1: "враг", 2: "нейтралы"}


def read(paths):
    for p in paths:
        label = Path(p).name.split(".")[0]
        with gzip.open(p, "rt", encoding="utf-8", errors="replace") as f:
            for line in f:
                i = line.find("[AICELL] ")
                if i < 0:
                    continue
                head = dict(kv.split("=", 1) for kv in line[:i].split() if "=" in kv)
                d = json.loads(line[i + 9:])
                d["label"], d["seed"], d["want"] = label, head.get("seed"), head.get("want")
                yield d


def pct(xs, q):
    if not xs:
        return 0.0
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))]


def ms(ns):
    return ns / 1e6


def share(n, total):
    return f"{n} ({100.0 * n / total:.1f} %)" if total else "0"


def block(rows):
    n = len(rows)
    out = []
    t = [ms(r["ns"]) for r in rows]
    out.append(f"- поисков: {n}; время цикла, мс: медиана {statistics.median(t):.2f}, p90 {pct(t, .9):.2f}, "
               f"p99 {pct(t, .99):.2f}, макс {max(t):.2f}, всего {sum(t) / 1000:.1f} с")
    shadow = [ms(r["nsFull"] + r["nsZ"] + r["nsFar"]) for r in rows]
    out.append(f"- тень замера (в игре её нет), мс: медиана {statistics.median(shadow):.2f}, всего {sum(shadow) / 1000:.1f} с")
    out.append(f"- окно (кандидатов): медиана {statistics.median([r['window'] for r in rows]):.0f}; "
               f"оценено: медиана {statistics.median([r['scanned'] for r in rows]):.0f}; "
               f"прошли порог: медиана {statistics.median([r['passed'] for r in rows]):.0f}")
    early = [r for r in rows if r["breakAt"] >= 0]
    # breakAt: fp - номер смещения в randomTileSearch (все смещения, не только окно), amb - номер узла после дешёвых
    # проверок, esc - номер попытки (0-120 окно, 121-149 случайный бег)
    out.append(f"- выход по порогу (breakAt): {share(len(early), n)}"
               + (f"; номер кандидата при выходе: медиана {statistics.median([r['breakAt'] for r in early]):.0f}, "
                  f"окно медиана {statistics.median([r['window'] for r in early]):.0f}" if early else ""))
    none = [r for r in rows if r["chosen"] is None]
    out.append(f"- ничего не выбрано: {share(len(none), n)}")
    if all(r["nsFull"] == 0 and r["best"] is None for r in rows):
        out.append("- теневого перебора у этого поиска нет: сравнение с лучшей клеткой, уровни и даль не считались")
        out.append(f"- mismatch (обязан быть 0): {sum(1 for r in rows if r['mismatch'])}")
        return out
    cmp_ = [r for r in rows if r["chosen"] is not None and r["best"] is not None]
    worse = [r for r in cmp_ if r["best"] > r["chosen"]]
    out.append(f"- в окне была клетка лучше выбранной: {share(len(worse), len(cmp_))}")
    if worse:
        gap = [r["best"] - r["chosen"] for r in worse]
        rk = [r["rank"] for r in worse]
        out.append(f"  - отставание счёта: медиана {statistics.median(gap):.0f}, p90 {pct(gap, .9):.0f}, макс {max(gap)}; "
                   f"клеток лучше выбранной: медиана {statistics.median(rk):.0f}, макс {max(rk)}")
    above = [r["fullAbove"] for r in rows]
    out.append(f"- клеток окна выше порога (тень): медиана {statistics.median(above):.0f}, p90 {pct(above, .9):.0f}")
    multi = [r for r in rows if r["mapZ"] > 1]
    zgain = [r for r in multi if r["zBest"] is not None
             and (r["best"] is None or r["zBest"] > r["best"])]
    out.append(f"- карта в несколько уровней: {share(len(multi), n)}; соседний уровень дал клетку лучше лучшей в окне: "
               f"{share(len(zgain), len(multi))}")
    if zgain:
        g = [r["zBest"] - (r["best"] if r["best"] is not None else 0) for r in zgain if r["best"] is not None]
        if g:
            out.append(f"  - выигрыш счёта: медиана {statistics.median(g):.0f}, p90 {pct(g, .9):.0f}")
        out.append(f"  - кандидатов на других уровнях: медиана {statistics.median([r['zCand'] for r in multi]):.0f}")
    fgain = [r for r in rows if r["farBest"] is not None and (r["best"] is None or r["farBest"] > r["best"])]
    out.append(f"- достижимая клетка за окном лучше лучшей в окне: {share(len(fgain), n)}"
               + (f"; кандидатов за окном: медиана {statistics.median([r['farCand'] for r in rows]):.0f}" if rows else ""))
    mm = sum(1 for r in rows if r["mismatch"])
    out.append(f"- mismatch (обязан быть 0): {mm}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--out")
    a = ap.parse_args()
    rows = list(read(a.files))
    lines = [f"# Замер поисков клеток CELL_PROF", "", f"Файлы: {', '.join(Path(f).name for f in a.files)}; "
             f"боёв: {len({(r['label'], r['seed'], r['want']) for r in rows})}; поисков: {len(rows)}", ""]
    groups = defaultdict(list)
    for r in rows:
        groups[(r["label"], r["ctx"], r["side"])].append(r)
    for label in sorted({k[0] for k in groups}):
        lines.append(f"## {label}")
        for ctx in ("fp", "amb", "esc"):
            for side in sorted({k[2] for k in groups if k[0] == label and k[1] == ctx}):
                lines += ["", f"### {CTX.get(ctx, ctx)} - {SIDE.get(side, side)}"] + block(groups[(label, ctx, side)])
        lines.append("")
    text = "\n".join(lines) + "\n"
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8-sig")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(text)


if __name__ == "__main__":
    main()
