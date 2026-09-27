#!/usr/bin/env python3
"""Побоища: серия случайных боёв Пираток, где обе стороны ведёт ИИ, и статистика по ним.

Каждое зерно - свой бой: миссия, местность, раса и тьма выбираются игрой по зерну
(NewBattleState::probeRandomize); отряд - самый большой экипаж кампании Vitali (копия сейва, со снаряжением,
сложностью и месяцем кампании), с --recruits - новобранцы быстрого боя в корабле от 8 мест. Обе стороны играет ИИ (OXCE_AI_BOT), итог - строка [AIRESULT].
Одно и то же зерно на той же сборке даёт тот же бой: серию можно повторить после правки ИИ и
сравнить мерило - раненые за бой, потерянное здоровье, доля боёв с ранеными, длина боя
(docs/AI_ROADMAP.md, «Цель»).

Прогоны невидимые и тихие (tools/ai_probe.py): скрытые окна, звук в dummy, приоритет ниже обычного,
по умолчанию 4 боя одновременно. Нужна локальная сборка стенда build-ai (cmake -DOXCE_AI_DEV=ON).

  py -3.13 tools/ai_arena.py --seeds 1-40 [--jobs 4] [--turns 60] [--diff 4] [--label base] [--out итог.txt]

Таблица боёв - <label>.tsv рядом с логами прогона (%TEMP%/oxce_ai_probe/arena), сводка - в stdout и --out.
"""
import argparse, statistics, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ai_probe

ENC_W = "utf-8-sig"
COLS = ("seed", "how", "mission", "month", "units", "terrain", "race", "craft", "shade", "turn", "player", "pdead", "pout",
        "pwounded", "phplost", "hostile", "hdead", "hout", "hleft", "pattacks", "hattacks", "seconds", "note")


def seeds_of(spec):
    out = []
    for part in spec.split(","):
        a, _, b = part.partition("-")
        out += list(range(int(a), int(b) + 1)) if b else [int(a)]
    return out


def one(seed, turns, diff, timeout, campaign):
    r = ai_probe.run(None, turns, name=f"arena_{seed}", timeout=timeout, bot=True, seed=seed, diff=diff,
                     campaign=campaign)
    row = {"seed": seed, "seconds": f"{r.seconds:.0f}", "note": ""}
    battle = r.tagged("[AIPROBE] battle")
    if battle:
        row.update({k: v for k, v in ai_probe.fields(battle[0]).items() if k in COLS})
    res = r.tagged("[AIRESULT]")
    if res:
        row.update({k: v for k, v in ai_probe.fields(res[0]).items() if k in COLS})
    else:
        stuck = r.tagged("[AIPROBE] stuck")
        row["how"] = "stuck" if stuck else ("nobattle" if not battle else "timeout-real")
        row["note"] = stuck[0].split(": ", 1)[-1] if stuck else str(r.log)
    return row


def outcome(row):
    """win - врагов на ногах не осталось, loss - у игрока, draw - предел ходов, иначе прогон не дошёл."""
    if row.get("how") not in ("over", "abort", "timeout"):
        return row.get("how", "?")
    if row["how"] == "timeout":
        return "draw"
    if int(row["hleft"]) == 0:
        return "win"
    if int(row["pdead"]) + int(row["pout"]) >= int(row["player"]):
        return "loss"
    return "abort"


def summary(rows, label):
    lines = [f"серия {label}: боёв {len(rows)}"]
    by = {}
    for r in rows:
        by.setdefault(outcome(r), []).append(r)
    lines.append("исходы: " + ", ".join(f"{k} {len(v)}" for k, v in sorted(by.items())))
    done = [r for r in rows if outcome(r) in ("win", "loss", "draw", "abort")]
    if not done:
        return lines
    n = len(done)
    num = lambda r, k: int(r[k])
    wounded = [num(r, "pwounded") for r in done]
    lines += [
        f"сыгранных {n}: раненых за бой {sum(wounded) / n:.2f}, боёв с ранеными {100 * sum(w > 0 for w in wounded) / n:.0f} %,"
        f" погибших за бой {sum(num(r, 'pdead') for r in done) / n:.2f}, без сознания {sum(num(r, 'pout') for r in done) / n:.2f}",
        f"потеряно здоровья за бой {sum(num(r, 'phplost') for r in done) / n:.1f},"
        f" ходов в бою медиана {statistics.median(num(r, 'turn') for r in done):.0f},"
        f" врагов убито/оглушено {sum(num(r, 'hdead') + num(r, 'hout') for r in done)} из {sum(num(r, 'hostile') for r in done)}",
        f"атак за бой: игрок {sum(num(r, 'pattacks') for r in done) / n:.1f}, враг {sum(num(r, 'hattacks') for r in done) / n:.1f};"
        f" время боя медиана {statistics.median(float(r['seconds']) for r in done):.0f} с",
    ]
    bad = [r for r in rows if r not in done]
    for r in bad:
        lines.append(f"  не доиграно: зерно {r['seed']} {r.get('how')} {r.get('mission', '-')} {r.get('note', '')}")
    return lines


def main():
    sys.stdout.reconfigure(encoding="utf-8")  # R-001
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seeds", default="1-20", help="зёрна боёв: 1-40 или 3,7,10-12")
    ap.add_argument("--jobs", type=int, default=4, help="боёв одновременно")
    ap.add_argument("--turns", type=int, default=60, help="предел ходов боя")
    ap.add_argument("--diff", type=int, default=None, help="сложность 0-4 (по умолчанию из кампании, иначе 4)")
    ap.add_argument("--campaign", default="NoCodexCatZ.sav", help="сейв кампании: отряд - самый большой экипаж оттуда")
    ap.add_argument("--recruits", action="store_true", help="вместо кампании новобранцы быстрого боя")
    ap.add_argument("--timeout", type=int, default=1200, help="секунд на бой")
    ap.add_argument("--label", default="arena")
    ap.add_argument("--out", default="")
    a = ap.parse_args()

    seeds = seeds_of(a.seeds)
    table = ai_probe.WORK / "arena" / f"{a.label}.tsv"
    table.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    t0 = time.time()
    with ThreadPoolExecutor(a.jobs) as pool:
        for row in pool.map(lambda s: one(s, a.turns, a.diff, a.timeout, None if a.recruits else a.campaign), seeds):
            rows.append(row)
            print(f"[{len(rows)}/{len(seeds)}] зерно {row['seed']}: {outcome(row)}, {row.get('mission', '-')},"
                  f" ход {row.get('turn', '-')}, раненых {row.get('pwounded', '-')}, {row['seconds']} с", flush=True)
    with open(table, "w", encoding=ENC_W) as f:
        f.write("\t".join(COLS + ("outcome",)) + "\n")
        for r in rows:
            f.write("\t".join(str(r.get(c, "")) for c in COLS) + "\t" + outcome(r) + "\n")
    lines = summary(rows, a.label) + [f"таблица: {table}", f"вся серия {time.time() - t0:.0f} с"]
    print("\n".join(lines))
    if a.out:
        Path(a.out).write_text("\n".join(lines) + "\n", encoding=ENC_W)
    return 0


if __name__ == "__main__":
    sys.exit(main())
