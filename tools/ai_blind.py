#!/usr/bin/env python3
"""Тест слепоты ИИ: решения врага не должны зависеть от того, чего он не видит.

Берёт сохранённый бой (ход игрока), делает копии, в которых меняет то, что стороне ИИ не видно:
  swap  - меняет местами двух невидимых врагу бойцов игрока (засвеченного недавно и другого);
  stats - невидимым бойцам игрока вдвое срезает здоровье и ОВ.
На оригинале и на каждой копии гоняет пробу хода ИИ (tools/ai_probe.py) и сравнивает отпечатки
[AIDECIDE] до первого решения, принятого после того, как сторона ИИ честно увидела изменённого бойца.

Совпали - ИИ слеп к скрытому (честен). Разошлись - ИИ знает то, чего не видел: печатается первое
расхождение. На родном ИИ тест обязан ПАДАТЬ (контрольный опыт, R-086), на новом - проходить.
Копия невалидна, если в начале хода ИИ враг видит не тех же, что на оригинале.

  py -3.13 tools/ai_blind.py <сейв> [--mutation swap|stats|both] [--swap 7,11] [--turns 1] [--out отчёт.txt]

Код выхода: 0 - слеп, 1 - подглядывает, 2 - опыт невалиден. Справка: docs/AI_ROADMAP.md, Ф2.3.
"""
import argparse, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ai_probe

ENC_W = "utf-8-sig"
ENC_R = "utf-8-sig"


def units_section(text):
    """Границы списка units в разделе battleGame: у предметов тоже есть '- id:', путать нельзя."""
    bg = text.index("\nbattleGame:\n")
    start = text.index("\n  units:\n", bg) + len("\n  units:\n")
    end = text.index("\n  items:", start)
    return start, end


def edit_units(text, edits):
    """edits: {id: {поле: новое значение строкой}} - правит строки полей юнитов боя."""
    start, end = units_section(text)
    part = text[start:end]
    blocks = re.split(r"(?m)^(?=    - id: )", part)
    out = []
    for b in blocks:
        m = re.match(r"    - id: (\d+)\n", b)
        if m and int(m.group(1)) in edits:
            for key, value in edits[int(m.group(1))].items():
                b, n = re.subn(rf"(?m)^(      {key}: ).*$", lambda mm: mm.group(1) + value, b, count=1)
                if n != 1:
                    sys.exit(f"у юнита {m.group(1)} нет поля {key}")
        out.append(b)
    return text[:start] + "".join(out) + text[end:]


def unit_fields(text, uid, keys):
    start, end = units_section(text)
    m = re.search(rf"(?ms)^    - id: {uid}\n(.*?)(?=^    - id: |\Z)", text[start:end])
    got = {}
    for key in keys:
        mm = re.search(rf"(?m)^      {key}: (.*)$", m.group(1))
        got[key] = mm.group(1)
    return got


def first_ai_turn(lines):
    """Строки aistart первого хода ИИ."""
    starts = [l for l in lines if l.startswith("[AISTATE] aistart")]
    if not starts:
        return []
    turn = ai_probe.fields(starts[0])["turn"]
    return [l for l in starts if ai_probe.fields(l)["turn"] == turn]


def sight(aistart):
    """Кого видит каждый юнит стороны ИИ в начале её хода: {id: frozenset(ids)}."""
    out = {}
    for l in aistart:
        f = ai_probe.fields(l)
        if f["faction"] == "1":
            out[f["unit"]] = frozenset() if f["sees"] == "-" else frozenset(f["sees"].split(","))
    return out


def compare(base, mutant, touched):
    """Решения до первого, принятого после того, как ИИ увидел изменённого бойца.
    Возвращает (сколько сравнили, первое расхождение или None, где отсекли)."""
    a = base.tagged("[AIDECIDE]")
    b = mutant.tagged("[AIDECIDE]")
    n = 0
    for la, lb in zip(a, b):
        for line in (la, lb):
            seen = ai_probe.fields(line).get("seen", "-")
            if seen != "-" and touched & set(seen.split(",")):
                return n, None, f"решение {n + 1}: ИИ увидел изменённого бойца ({seen})"
        if la != lb:
            return n, (la, lb), None
        n += 1
    if len(a) != len(b):
        return n, (a[n] if n < len(a) else "(конец)", b[n] if n < len(b) else "(конец)"), None
    return n, None, "конец отпечатков"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("save", help="сейв боя на ходу игрока")
    ap.add_argument("--mutation", choices=("swap", "stats", "both"), default="both")
    ap.add_argument("--swap", default="", help="пара бойцов для перестановки, например 7,11")
    ap.add_argument("--turns", type=int, default=1)
    ap.add_argument("--out", default="")
    a = ap.parse_args()

    report = []
    def say(s=""):
        print(s)
        report.append(s)

    text = Path(a.save).read_text(encoding=ENC_R)
    base = ai_probe.run(a.save, a.turns, name="blind_base")
    if not base.finished:
        say(f"проба на оригинале не дошла до конца: {base.log} {' '.join(base.tagged('[AIPROBE] stuck'))}")
        return 2
    aistart = first_ai_turn(base.lines)
    base_sight = sight(aistart)
    seen_by_ai = set().union(*base_sight.values()) if base_sight else set()
    players = [ai_probe.fields(l) for l in aistart if ai_probe.fields(l)["faction"] == "0"]
    unseen = [p for p in players if p["unit"] not in seen_by_ai and p["status"] == "0"]
    known = [p for p in unseen if p["spotted"] != "255"]
    fresh = [p for p in unseen if p["spotted"] == "255"]
    say(f"сейв {a.save}: бойцов игрока {len(players)}, врагу не видны {len(unseen)} "
        f"(засвечены раньше: {', '.join(p['unit'] for p in known) or 'нет'}), решений ИИ {len(base.tagged('[AIDECIDE]'))}")

    mutants = []
    if a.mutation in ("swap", "both"):
        if a.swap:
            x, y = a.swap.split(",")
        elif known and fresh:
            x, y = known[0]["unit"], fresh[-1]["unit"]
        elif len(known) >= 2:
            x, y = known[0]["unit"], known[1]["unit"]
        else:
            x = y = None
        if x:
            fx = unit_fields(text, x, ("position", "direction"))
            fy = unit_fields(text, y, ("position", "direction"))
            mutants.append((f"swap {x}<->{y}", {int(x): fy, int(y): fx}, {x, y}))
        else:
            say("swap: нечего переставлять - нужны два невидимых врагу бойца, из них один засвеченный")
    if a.mutation in ("stats", "both") and unseen:
        edits = {}
        for p in unseen:
            f = unit_fields(text, p["unit"], ("health", "tu"))
            edits[int(p["unit"])] = {"health": str(max(1, int(f["health"]) // 2)), "tu": str(int(f["tu"]) // 2)}
        mutants.append((f"stats {','.join(p['unit'] for p in unseen)}", edits, {p["unit"] for p in unseen}))

    verdict = 0
    for label, edits, touched in mutants:
        mpath = Path(ai_probe.WORK) / f"blind_{label.split()[0]}.asav"
        mpath.parent.mkdir(parents=True, exist_ok=True)
        mpath.write_bytes(edit_units(text, edits).encode("utf-8"))
        mut = ai_probe.run(mpath, a.turns, name="blind_mut")
        if not mut.finished:
            say(f"{label}: проба не дошла до конца - {mut.log} {' '.join(mut.tagged('[AIPROBE] stuck'))}")
            verdict = max(verdict, 2)
            continue
        mut_sight = sight(first_ai_turn(mut.lines))
        if mut_sight != base_sight:
            diff = sorted(u for u in set(base_sight) | set(mut_sight) if base_sight.get(u) != mut_sight.get(u))
            say(f"{label}: НЕВАЛИДНО - в начале хода враг видит не тех же (юниты {', '.join(diff)})")
            verdict = max(verdict, 2)
            continue
        n, diff, cut = compare(base, mut, touched)
        if diff:
            say(f"{label}: ПОДГЛЯДЫВАЕТ - совпали {n} решений, расхождение на {n + 1}-м:")
            say(f"  оригинал: {diff[0]}")
            say(f"  копия:    {diff[1]}")
            verdict = max(verdict, 1)
        else:
            say(f"{label}: слеп - совпали {n} решений ({cut})")
    say({0: "ИТОГ: ИИ слеп к скрытому", 1: "ИТОГ: ИИ подглядывает", 2: "ИТОГ: опыт невалиден"}[verdict])
    if a.out:
        Path(a.out).write_text("\n".join(report) + "\n", encoding=ENC_W)
    return verdict


if __name__ == "__main__":
    sys.exit(main())
