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
  py -3.13 tools/ai_arena.py --missions @tools/ai_missions.txt --seeds 1-50 --jobs 8 --label maps27 [--resume]

С --missions каждая миссия играется на всех зёрнах (местность, раса и отряд - по зерну), в сводке строка на миссию.
Таблица пишется по строке после каждого боя; --resume продолжает прерванную серию с того же места.

Таблица боёв - <label>.tsv рядом с логами прогона (%TEMP%/oxce_ai_probe/arena), сводка - в stdout и --out.
"""
import argparse, collections, gzip, os, queue, re, statistics, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ai_probe

ENC_W = "utf-8-sig"
# поведение из [AIDECIDE]: p - сторона игрока (бот), h - враг
MOVES = ("decisions", "run", "kneel", "throw", "psi", "melee")
COLS = ("seed", "want", "how", "mission", "kind", "month", "units", "terrain", "race", "craft", "shade", "turn", "player", "pdead", "pout",
        "pwounded", "phplost", "hostile", "hdead", "hout", "hleft", "livesoldiers", "livealiens", "aborted",
        "pattacks", "hattacks", "tac") + tuple(s + m for s in "ph" for m in MOVES) + ("seconds", "note")
DECIDE = re.compile(r"\[AIDECIDE\] turn=\d+ side=(\d) .*? act=(\d+) to=\S+ run=(\d)(?: kneel=(\d))?")


def behaviour(log):
    """Счётчики решений по сторонам из лога боя: сам лог перезапишет следующий бой того же потока."""
    c = collections.Counter()
    try:
        text = Path(log).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    for side, act, run, kneel in DECIDE.findall(text):
        s = {"0": "p", "1": "h"}.get(side)
        if not s:
            continue
        act = int(act)
        c[s + "decisions"] += 1
        c[s + "run"] += act == 2 and run == "1"
        # присед - и отдельным действием, и флагом при выстреле или засаде (AIModule.cpp, action->kneel)
        c[s + "kneel"] += act == 3 or kneel == "1"
        c[s + "throw"] += act in (6, 12)
        c[s + "psi"] += act in (13, 14)
        c[s + "melee"] += act == 10
    return {s + m: c[s + m] for s in "ph" for m in MOVES}


def seeds_of(spec):
    out = []
    for part in spec.split(","):
        a, _, b = part.partition("-")
        out += list(range(int(a), int(b) + 1)) if b else [int(a)]
    return out


SLOTS = queue.Queue()
LABEL = "arena"


def one(seed, turns, diff, timeout, campaign, mission=None, tactics=False, careful=False, squad=0):
    # папка прогона - по потоку, а не по зерну: одно зерно идёт на разных миссиях одновременно;
    # у каждой серии (--label) свои папки - серии идут рядом, в том числе на одной сборке
    slot = SLOTS.get()
    try:
        r = ai_probe.run(None, turns, name=f"arena_{LABEL}_w{slot}", timeout=timeout, bot=True, seed=seed, diff=diff,
                         campaign=campaign, mission=mission, tactics=tactics, careful=careful, squad=squad)
        moves = behaviour(r.log)
    finally:
        SLOTS.put(slot)
    row = {"seed": seed, "want": mission or "", "seconds": f"{r.seconds:.0f}", "note": "",
           "_casualties": r.tagged("[AICASUALTY]"), "_tiles": r.tagged("[AISTATE]"),
           # решения и, по OXCE_AI_TRACE_MELEE, кандидаты ближнего боя ([AIMELEE]), по OXCE_AI_TRACE_PATH -
           # расчёты пути ([AIPATH]) - в порядке лога
           "_decide": [l for l in r.lines if l.startswith(("[AIDECIDE]", "[AIMELEE]", "[AIPATH]"))] if os.environ.get("OXCE_AI_KEEP_DECIDE") else []}
    row.update(moves)
    battle = r.tagged("[AIPROBE] battle")
    if battle:
        row.update({k: v for k, v in ai_probe.fields(battle[0]).items() if k in COLS})
    res = r.tagged("[AIRESULT]")
    if res:
        got = ai_probe.fields(res[0])
        # mission в [AIRESULT] - тип боя движка (у любого НЛО STR_UFO_GROUND_ASSAULT), миссия - из строки battle
        row["kind"] = got.pop("mission", "")
        row.update({k: v for k, v in got.items() if k in COLS})
    else:
        stuck = r.tagged("[AIPROBE] stuck")
        row["how"] = "stuck" if stuck else ("nobattle" if not battle else "timeout-real")
        row["note"] = stuck[0].split(": ", 1)[-1] if stuck else str(r.log)
    return row


def outcome(row):
    """win - врагов на ногах не осталось, loss - у игрока, draw - предел ходов, иначе прогон не дошёл."""
    if row.get("want") and row.get("mission") and row["want"] != row["mission"]:
        return "unpinned"  # такой миссии нет в списке быстрого боя, игра взяла случайную
    if "could not be placed" in row.get("note", ""):
        return "nomap"  # корабль не встаёт на карту миссии: генератор падает так же и в игре
    if row.get("how") not in ("over", "abort", "timeout"):
        return row.get("how", "?")
    if row["how"] == "timeout":
        return "draw"
    if row.get("livealiens", "") != "":
        # подсчёт движка: сдавшихся, пленённых пси и оглушённых сверх порога он живыми не считает
        if int(row["livealiens"]) == 0:
            return "win"
        if int(row["livesoldiers"]) == 0:
            return "loss"
        # бот не отступает никогда: прерванный бой - это таймер миссии (turnLimit + chronoTrigger), отряд продержался
        return "held" if row["how"] == "abort" or row.get("aborted") == "1" else "end-other"
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
    done = [r for r in rows if outcome(r) in ("win", "loss", "draw", "held", "abort", "end-other")]
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
    moves = {m: sum(int(r.get(m) or 0) for r in done) for m in COLS if m[1:] in MOVES}
    for s, who in (("p", "бот-игрок"), ("h", "враг")):
        d = moves[s + "decisions"] or 1
        lines.append(f"{who}: решений {moves[s + 'decisions']}, бегом {100 * moves[s + 'run'] / d:.1f} %,"
                     f" присел {100 * moves[s + 'kneel'] / d:.1f} %, гранат и ракет {moves[s + 'throw']},"
                     f" пси {moves[s + 'psi']}, вплотную {moves[s + 'melee']}")
    bad = [r for r in rows if r not in done]
    for r in bad:
        lines.append(f"  не доиграно: зерно {r['seed']} {r.get('how')} {r.get('mission', '-')} {r.get('note', '')[:160]}")
    return lines


def by_mission(rows):
    """Строка на миссию: сколько сыграно, исходы, погибших и раненых за бой, длина боя."""
    groups = collections.defaultdict(list)
    for r in rows:
        groups[r.get("want") or r.get("mission") or "-"].append(r)
    lines = ["", "по миссиям (сыграно | победа/поражение/предел | погибло, ранено из отряда | ходов медиана | nomap):"]
    for m, rs in sorted(groups.items()):
        done = [r for r in rs if outcome(r) in ("win", "loss", "draw", "held", "abort", "end-other")]
        out = collections.Counter(outcome(r) for r in rs)
        if not done:
            lines.append(f"  {m}: не сыграно ни одного, {dict(out)}")
            continue
        n = len(done)
        mean = lambda k: sum(int(r[k]) for r in done) / n
        lines.append(f"  {m}: {n} | {out['win']}/{out['loss']}/{out['draw']} | {mean('pdead'):.1f}, {mean('pwounded'):.1f}"
                     f" из {mean('player'):.0f} | {statistics.median(int(r['turn']) for r in done):.0f}"
                     f" | {out['nomap']}" + (f" | прочее {n - out['win'] - out['loss'] - out['draw']}"
                                              if n > out['win'] + out['loss'] + out['draw'] else "")
                     + (f" | не доиграно {len(rs) - n - out['nomap']}" if len(rs) - n - out['nomap'] else ""))
    return lines


def read_table(table):
    """Уже сыгранные строки таблицы - чтобы продолжить прерванную серию (--resume)."""
    if not table.exists():
        return []
    lines = table.read_text(encoding=ENC_W).splitlines()
    head = lines[0].split("\t")
    return [dict(zip(head, ln.split("\t"))) for ln in lines[1:] if ln.strip()]


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
    ap.add_argument("--missions", default="", help="миссии через запятую или @файл (строка на миссию): каждая на всех зёрнах")
    ap.add_argument("--resume", action="store_true", help="продолжить серию: уже сыгранные миссия+зерно из таблицы пропустить")
    ap.add_argument("--tactics", action="store_true", help="враг с правилами опыта (OXCE_AI_TACTICS): стреляет или уходит в укрытие")
    ap.add_argument("--careful", action="store_true", help="осторожный бот за игрока (OXCE_AI_CAREFUL): укрытие, отвод раненых, присед и бег по правилам игрока")
    ap.add_argument("--squad", type=int, default=0, help="отряд как у Vitali (OXCE_AI_SQUAD): n самых опытных бойцов самого опытного экипажа, остальные дома")
    ap.add_argument("--label", default="arena")
    ap.add_argument("--out", default="")
    ap.add_argument("--env", action="append", default=[], metavar="K=V",
                    help="переменная окружения боя OXCE_AI_*, повторяемый: --env OXCE_AI_EVAL=1 --env OXCE_AI_EVAL_RISK=0.12")
    a = ap.parse_args()
    global LABEL
    LABEL = a.label
    for kv in a.env:
        k, _, v = kv.partition("=")
        if not k.startswith("OXCE_AI_"):
            raise SystemExit(f"--env {kv}: только OXCE_AI_*")
        os.environ[k] = v  # ai_probe.run копирует окружение в процесс боя

    seeds = seeds_of(a.seeds)
    missions = [None]
    if a.missions:
        text = Path(a.missions[1:]).read_text(encoding=ENC_W) if a.missions.startswith("@") else a.missions.replace(",", "\n")
        missions = [m.strip() for m in text.splitlines() if m.strip() and not m.startswith("#")]
    table = ai_probe.WORK / "arena" / f"{a.label}.tsv"
    table.parent.mkdir(parents=True, exist_ok=True)
    rows = read_table(table) if a.resume else []
    played = {(r.get("want", ""), str(r["seed"])) for r in rows}
    jobs = [(m, s) for m in missions for s in seeds if (m or "", str(s)) not in played]
    if not rows:
        table.write_text("\t".join(COLS + ("outcome",)) + "\n", encoding=ENC_W)
    for slot in range(a.jobs):
        SLOTS.put(slot)
    campaign = None if a.recruits else a.campaign
    total = len(jobs) + len(rows)
    print(f"правила: враг {'опыт' if a.tactics else 'родной'}, бот {'осторожный' if a.careful else 'родной'}"
          + (f", окружение {' '.join(a.env)}" if a.env else ""), flush=True)
    print(f"боёв {len(jobs)} (уже сыграно {len(rows)}), миссий {len(missions)}, зёрен {len(seeds)}, потоков {a.jobs}", flush=True)
    t0 = time.time()
    with ThreadPoolExecutor(a.jobs) as pool:
        # по мере готовности, а не по порядку: бой, чей процесс не закрылся и ждёт таймаута, не держит запись остальных
        futures = [pool.submit(one, s, a.turns, a.diff, a.timeout, campaign, m, a.tactics, a.careful, a.squad) for m, s in jobs]
        for fut in as_completed(futures):
            row = fut.result()
            rows.append(row)
            # строка в таблицу сразу: серия на часы, обрыв не должен стоить уже сыгранного
            with open(table, "a", encoding="utf-8") as f:
                f.write("\t".join(str(row.get(c, "")).replace("\t", " ") for c in COLS) + "\t" + outcome(row) + "\n")
            # павшие и оглушённые боя - рядом, строка [AICASUALTY] как есть: кто, чем, откуда, на чьём ходу
            if row.get("_casualties"):
                with open(table.with_suffix(".casualties.txt"), "a", encoding="utf-8") as f:
                    f.writelines(f"seed={row['seed']} want={row['want']} {line}\n" for line in row["_casualties"])
            # снимки всех юнитов в начале каждого хода стороны - данные «каждой клеткой» (docs/AI_TRAINING.md):
            # признаки клетки в конце хода и её исход после хода противника; gzip дописывается членами
            if row.get("_tiles"):
                with gzip.open(table.with_suffix(".tiles.gz"), "at", encoding="utf-8") as f:
                    f.writelines(f"seed={row['seed']} want={row['want']} {line}\n" for line in row["_tiles"])
            # каждое решение ИИ ([AIDECIDE]) - только по OXCE_AI_KEEP_DECIDE=1: разбор «почему стоял», на порцию это сотни МБ
            if row.get("_decide"):
                with gzip.open(table.with_suffix(".decide.gz"), "at", encoding="utf-8") as f:
                    f.writelines(f"seed={row['seed']} want={row['want']} {line}\n" for line in row["_decide"])
            print(f"[{len(rows)}/{total}] зерно {row['seed']}: {outcome(row)}, {row.get('mission', '-')},"
                  f" ход {row.get('turn', '-')}, раненых {row.get('pwounded', '-')}, {row['seconds']} с", flush=True)
    lines = summary(rows, a.label) + (by_mission(rows) if a.missions else []) + [
        f"таблица: {table}", f"вся серия {time.time() - t0:.0f} с"]
    print("\n".join(lines))
    if a.out:
        Path(a.out).write_text("\n".join(lines) + "\n", encoding=ENC_W)
    return 0


if __name__ == "__main__":
    sys.exit(main())
