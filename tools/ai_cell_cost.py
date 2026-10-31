"""Цена «проверки всего окна» вместо выхода по порогу (125 точка стрельбы, 80 засада, 100 бегство) - по замеру CELL_PROF.

Источник - архивы <метка>.cell.gz (строки [AICELL]). Для каждого поиска:
  сейчас  = ns     - реальный поиск с выходом по порогу;
  полный  = nsFull - тень: каждая клетка (узел) окна оценена со своим A*, как без порога (без REACHCOST - верхняя оценка);
  +уровни = nsZ    - то же окно на соседних уровнях (бит LEVELS).
Бегство тени не имеет: полный = ns / window * 122 (попытки -1..120 окна 11x11, без случайного бега) - оценка по цене
одной попытки этого же поиска.
Суммы - по поиску, по ходу стороны (seed, want, turn, side) и по бою. Время - машины, где шёл бой.

Запуск: py -3.13 tools/ai_cell_cost.py <файл.cell.gz> [...] [--side 1] [--out отчёт.md]
"""
import argparse
import gzip
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

SIDE = {0: "игрок (бот)", 1: "враг", 2: "нейтралы"}
CTX = {"fp": "точка стрельбы (порог 125)", "amb": "засада (порог 80)", "esc": "бегство (порог 100)"}
ESC_TRIES = 122


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))] if xs else 0.0


def row(name, xs, unit=1e6, fmt="{:.1f}"):
    xs = [x / unit for x in xs]
    if not xs:
        return f"| {name} | — | — | — | — | — |"
    return "| " + name + " | " + " | ".join(fmt.format(v) for v in (pct(xs, .5), pct(xs, .9), pct(xs, .99), max(xs), sum(xs) / len(xs))) + " |"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--side", type=int, default=1)
    ap.add_argument("--out")
    a = ap.parse_args()
    per = defaultdict(lambda: defaultdict(list))   # ctx -> kind -> [ns по поиску]
    turn = defaultdict(lambda: [0, 0, 0])          # (бой, ход) -> сейчас, полный, полный+уровни
    battle = defaultdict(lambda: [0, 0, 0])
    for p in a.files:
        label = Path(p).name.split(".")[0]
        with gzip.open(p, "rt", encoding="utf-8", errors="replace") as f:
            for line in f:
                m = re.match(r"seed=(\S+) want=(\S+) \[AICELL\] (.*)", line)
                if not m:
                    continue
                d = json.loads(m.group(3))
                if d["side"] != a.side:
                    continue
                now = d["ns"]
                if d["ctx"] == "esc":
                    full = now / max(1, d["window"]) * ESC_TRIES
                    lv = full
                else:
                    full = d["nsFull"]
                    lv = d["nsFull"] + d["nsZ"]
                per[d["ctx"]]["now"].append(now)
                per[d["ctx"]]["full"].append(full)
                per[d["ctx"]]["lv"].append(lv)
                b = (label, m.group(1), m.group(2))
                for acc in (turn[b + (d["turn"],)], battle[b]):
                    acc[0] += now; acc[1] += full; acc[2] += lv
    out = [f"# Цена полного перебора вместо порога — {SIDE.get(a.side, a.side)}", "",
           f"Файлы: {', '.join(Path(f).name for f in a.files)}; боёв {len(battle)}, ходов стороны {len(turn)}", "",
           "## Один поиск, мс", "", "| | медиана | p90 | p99 | макс | среднее |", "|---|---|---|---|---|---|"]
    for ctx in ("fp", "amb", "esc"):
        if ctx not in per:
            continue
        out.append(row(f"{CTX[ctx]}: сейчас ({len(per[ctx]['now'])} поисков)", per[ctx]["now"]))
        out.append(row(f"{CTX[ctx]}: полный перебор" + (" (оценка)" if ctx == "esc" else ""), per[ctx]["full"]))
        if ctx != "esc":
            out.append(row(f"{CTX[ctx]}: полный + соседние уровни", per[ctx]["lv"]))
    out += ["", "## Все поиски клеток за один ход стороны, мс", "", "| | медиана | p90 | p99 | макс | среднее |", "|---|---|---|---|---|---|"]
    t = list(turn.values())
    out.append(row("сейчас", [x[0] for x in t]))
    out.append(row("полный перебор", [x[1] for x in t]))
    out.append(row("полный + уровни", [x[2] for x in t]))
    out.append(row("прибавка к ходу (полный − сейчас)", [x[1] - x[0] for x in t]))
    out += ["", "## Весь бой, с", "", "| | медиана | p90 | p99 | макс | среднее |", "|---|---|---|---|---|---|"]
    bt = list(battle.values())
    out.append(row("сейчас", [x[0] for x in bt], 1e9, "{:.2f}"))
    out.append(row("полный перебор", [x[1] for x in bt], 1e9, "{:.2f}"))
    out.append(row("полный + уровни", [x[2] for x in bt], 1e9, "{:.2f}"))
    text = "\n".join(out) + "\n"
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8-sig")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(text)


if __name__ == "__main__":
    main()
