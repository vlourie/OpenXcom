"""Знание врага и оружия (oxceKnowledgeArmor): выключенная опция не меняет бой, включённая - меняет.

Механика - docs/research/knowledge-armor-2026-10-28.md. Бой играет бот стенда ИИ за обе стороны (tools/ai_probe.py,
bot=True), зерно и кампания одинаковы, отличаются только сборка и oxceKnowledgeArmor в options.cfg. Сравниваются по
порядку [AISTATE], [AIDECIDE], [AICASUALTY], [AIEVENT], [AIRESULT] (как в test_gentle_determinism.py).
  1. сборка до правки (--base) и новая сборка (--build) с выключенной опцией - IDENTICAL в каждом бою;
  2. контроль (R-086): новая сборка с включённой опцией обязана изменить хотя бы один бой, а [AIKNOWARMOR] -
     показать срабатывания всех трёх случаев (известный враг, неизвестное оружие, интеллект врага); в выключенном
     прогоне счётчики обязаны быть нулями.
Одно зерно побоища изредка даёт другой бой и на одной сборке (R-113): расхождение пункта 1 переигрывается
(--retries) до признания провалом.

Обе сборки - стенд с -DOXCE_AI_DEV=ON (R-203). Игра идёт невидимо (ai_probe.Hidden).

  py -3.13 tools/test_knowledge_armor.py --base build-ai-base --build build-ai
"""
import argparse
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

from test_gentle_determinism import COMPARED, first_diff, stream  # noqa: E402

DEFAULT_SEEDS = "3,7"
KNOW = re.compile(r"\[AIKNOWARMOR\] on=(\d) known=(\d+) unknown=(\d+) mirror=(\d+)")


def counts(log):
    """Последняя строка [AIKNOWARMOR] прогона: (on, known, unknown, mirror) или None."""
    text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
    found = KNOW.findall(text)
    return tuple(int(x) for x in found[-1]) if found else None


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", required=True, help="каталог сборки стенда до правки")
    ap.add_argument("--build", default="build-ai", help="каталог сборки стенда с правкой")
    ap.add_argument("--seeds", default=DEFAULT_SEEDS, help="зёрна случайных боёв через запятую")
    ap.add_argument("--turns", type=int, default=6, help="предел ходов")
    ap.add_argument("--campaign", default="NoCodexCatZ.sav", help="сейв кампании для случайных боёв")
    ap.add_argument("--retries", type=int, default=3, help="переигровок выключенного прогона при расхождении (R-113)")
    a = ap.parse_args()
    import ai_probe

    def exe_of(build):
        p = Path(build)
        return (p if p.is_absolute() else ROOT / p) / "bin" / "openxcom.exe"

    base_exe, new_exe = exe_of(a.base), exe_of(a.build)
    for exe, must in ((base_exe, False), (new_exe, True)):
        blob = exe.read_bytes() if exe.is_file() else b""
        if b"[AIDECIDE]" not in blob:
            sys.exit(f"{exe}: не сборка стенда (нет [AIDECIDE], R-203)")
        if (b"oxceKnowledgeArmor" in blob) != must:
            sys.exit(f"{exe}: {'нет' if must else 'уже есть'} oxceKnowledgeArmor - не та сборка (R-087)")

    orig = ai_probe.prepare_user
    knowledge = {"value": "false"}

    def prepare(work):
        orig(work)
        p = work / "options.cfg"
        t = p.read_text(encoding="utf-8")
        t, n = re.subn(r"(?m)^(\s*)oxceKnowledgeArmor: .*$", rf"\g<1>oxceKnowledgeArmor: {knowledge['value']}", t)
        if n == 0:
            t, n = re.subn(r"(?m)^options:\s*$", f"options:\n  oxceKnowledgeArmor: {knowledge['value']}", t, count=1)
        if n != 1:
            sys.exit("в options.cfg прогона не записать oxceKnowledgeArmor")
        p.write_bytes(t.encode("utf-8"))

    ai_probe.prepare_user = prepare

    def play(seed, label, exe, on):
        ai_probe.EXE = exe
        knowledge["value"] = "true" if on else "false"
        r = ai_probe.run(None, turns=a.turns, name=f"knowarmor_{label}", timeout=1800, bot=True, seed=seed,
                         campaign=a.campaign)
        s, _ = stream(r.log)
        if not r.finished or not s["[AIRESULT]"]:
            print(f"  {label}: бой не доигран ({r.log})")
            return None, None
        return s, counts(r.log)

    failed = []
    changed = []
    total = [0, 0, 0]
    for seed in [int(s) for s in a.seeds.split(",") if s.strip()]:
        tag = f"seed{seed}"
        base, _ = play(seed, tag + "_base", base_exe, False)
        off, coff = play(seed, tag + "_off", new_exe, False)
        if base is None or off is None:
            failed.append(f"{tag}: бой не доигран")
            continue
        d = first_diff(base, off)
        tries = 0
        while d and tries < a.retries:
            tries += 1
            print(f"  {tag}: выкл. разошёлся с базой ({d[0]} #{d[1]}), переигровка {tries} (R-113)")
            off, coff = play(seed, f"{tag}_off{tries}", new_exe, False)
            d = first_diff(base, off) if off else d
        sizes = ", ".join(f"{t.strip('[]')} {len(base[t])}" for t in COMPARED)
        print(f"{tag}: база / выкл. {'IDENTICAL' if d is None else 'DIFFERENT'} ({sizes})")
        if d:
            failed.append(f"{tag}: выключенная опция изменила бой - {d[0]} #{d[1]}:\n  база {d[2]}\n  выкл {d[3]}")
        if coff != (0, 0, 0, 0):
            failed.append(f"{tag}: в выключенном прогоне [AIKNOWARMOR] {coff}, ждали нули")
        on, con = play(seed, tag + "_on", new_exe, True)
        if on is None:
            failed.append(f"{tag}: бой с опцией не доигран")
            continue
        dc = first_diff(off, on, play_only=True)
        print(f"  вкл.: {'бой другой - %s #%d' % dc[:2] if dc else 'бой тот же'}; [AIKNOWARMOR] {con}")
        changed.append(bool(dc))
        if not con or con[0] != 1:
            failed.append(f"{tag}: в прогоне с опцией нет [AIKNOWARMOR] on=1 ({con})")
        else:
            total = [x + y for x, y in zip(total, con[1:])]
    if changed and not any(changed):
        failed.append("опция ни в одном бою не изменила игру: сравнение слепое (R-086)")
    print(f"срабатывания с опцией всего: известный враг {total[0]}, неизвестное оружие {total[1]}, интеллект врага {total[2]}")
    for name, n in zip(("известный враг", "неизвестное оружие", "интеллект врага"), total):
        if n == 0:
            failed.append(f"случай «{name}» ни разу не сработал - добавь бой (--seeds), где он есть")
    if failed:
        print("ПРОВАЛ:")
        for f in failed:
            print(" -", f)
        sys.exit(1)
    print("ok: выключенная опция не меняет ни одного решения, состояния и итога; включённая меняет бой")


if __name__ == "__main__":
    main()
