"""Нежный режим не меняет бой: один и тот же бой с нежным режимом и без даёт одну и ту же игру.

Обязательная проверка каждого этапа нежного режима (указание Vitali 02.10). Бой играет бот стенда ИИ за обе стороны
(tools/ai_probe.py, bot=True), с кадрами (OXCE_AI_FAST=0: нежный режим весь в рисовании, без кадров он не работает).
Исходный бой, зерно и действия одинаковы, отличается только oxceGentle в options.cfg. Сравниваются по порядку:
  [AISTATE]    - состояние всех юнитов на границах ходов,
  [AIDECIDE]   - каждое решение ИИ с хэшами юнитов, предметов, карты и RNG до решения,
  [AICASUALTY] - каждая смерть и оглушение,
  [AIEVENT]    - каждый выстрел с овера и каждый взрыв с площадью (камера - what=view - картинка: только покрытие),
  [AIRESULT]   - итог боя (без замеров времени).
В последнем снимке ([AISTATE] end) у юнита с hp <= 0 статус и поворот не сравниваются: бой кончается, пока убитый
доигрывает смерть, и кадр анимации зависит от темпа; исход за него решает DebriefingState (instaFalling).
Покрытие: в сумме по боям обязаны быть овер, взрыв, смерть юнита и смена этажа (юнит на другом этаже или камера
сменила этаж) - иначе проверка ничего не проверила.
Контроль (R-086): каждый бой ещё раз без нежного режима, но с изменённым правилом ИИ (OXCE_AI_TACTICS). Хотя бы в
одном бою обязана измениться сама игра (решения, состояния, итог без счётчика tac=), иначе сравнение слепое:
на seed 3 правило срабатывает, а бой идёт тот же - разница только в tac=.

Сборка - стенд с -DOXCE_AI_DEV=ON из проверяемого дерева (OXCE_AI_BUILD или --build). Игра идёт невидимо (ai_probe.Hidden).

  py -3.13 tools/test_gentle_determinism.py --build <каталог сборки стенда>
  py -3.13 tools/test_gentle_determinism.py --save <бой.asav> --turns 14     (бой из сейва; turns - номер хода-предела)
"""
import argparse
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

COMPARED = ("[AISTATE]", "[AIDECIDE]", "[AICASUALTY]", "[AIEVENT]", "[AIRESULT]")
# зёрна случайных боёв (отряд из кампании ai_arena): на них есть овер, гранаты, смерти и этажи
DEFAULT_SEEDS = "3,7"


def stream(log):
    """Строки сравнения по тегам, по порядку. Камера (what=view) и время прогона - не механика."""
    out = {t: [] for t in COMPARED}
    cover = {"reaction": 0, "explosion": 0, "dead": 0, "view": 0, "floor": 0}
    floors = {}
    text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
    for raw in text.splitlines():
        body = raw.split("\t", 2)[-1]
        tag = body.split(" ", 1)[0]
        if tag not in out:
            continue
        if tag == "[AIEVENT]":
            what = re.search(r" what=(\w+)", body).group(1)
            cover[what] = cover.get(what, 0) + 1
            if what == "view":
                continue
        elif tag == "[AICASUALTY]" and " how=dead" in body:
            cover["dead"] += 1
        elif tag == "[AISTATE]" and body.startswith("[AISTATE] end ") and re.search(r" hp=(-\d+|0)/", body):
            # бой кончился, пока убитый доигрывает смерть: статус и поворот - кадр анимации, а не исход;
            # итог за него решает DebriefingState (isOutThresholdExceed -> instaFalling), им не пользуясь
            body = re.sub(r" (status|dir)=\d+", r" \1=*", body)
        elif tag == "[AIRESULT]":
            body = re.sub(r" ms=.*$", "", body)
        elif tag == "[AIDECIDE]":
            m = re.search(r" unit=(\d+) .*? from=\((\d+),(\d+),(\d+)\)", body)
            floors.setdefault(m.group(1), set()).add(m.group(4))
        out[tag].append(body)
    cover["floor"] = sum(1 for zs in floors.values() if len(zs) > 1)
    return out, cover


def first_diff(a, b, play_only=False):
    """Первое расхождение. play_only - без счётчиков правил стенда (tac= в итоге): контролю мало, что правило
    сработало, нужно, чтобы бой пошёл иначе."""
    for tag in COMPARED:
        x, y = a[tag], b[tag]
        if play_only and tag == "[AIRESULT]":
            x, y = [re.sub(r" tac=\S+", "", s) for s in x], [re.sub(r" tac=\S+", "", s) for s in y]
        for i in range(max(len(x), len(y))):
            if i >= len(x) or i >= len(y) or x[i] != y[i]:
                return tag, i, x[i] if i < len(x) else "(нет)", y[i] if i < len(y) else "(нет)"
    return None


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--build", default="", help="каталог сборки стенда (иначе OXCE_AI_BUILD или build-ai)")
    ap.add_argument("--seeds", default=DEFAULT_SEEDS, help="зёрна случайных боёв через запятую; пусто - только --save")
    ap.add_argument("--save", action="append", default=[], help="бой из сейва (можно несколько)")
    ap.add_argument("--turns", type=int, default=6, help="предел ходов (для сейва - номер хода, не число)")
    ap.add_argument("--campaign", default="NoCodexCatZ.sav", help="сейв кампании для случайных боёв")
    ap.add_argument("--no-control", action="store_true", help="без контрольного опыта (только для отладки теста)")
    ap.add_argument("--set", default="", help="ключи options.cfg всем прогонам: a=1;b=false")
    ap.add_argument("--off-set", default="", help="ключи options.cfg только прогону без нежного режима")
    a = ap.parse_args()
    if a.build:
        os.environ["OXCE_AI_BUILD"] = a.build
    os.environ["OXCE_AI_FAST"] = "0"
    import ai_probe

    exe = ai_probe.EXE
    blob = exe.read_bytes() if exe.is_file() else b""
    for mark in (b"oxceGentle", b"[AIEVENT]"):
        if mark not in blob:
            sys.exit(f"в {exe} нет {mark.decode()}: сборка стенда старше нежного режима или проверки (R-087)")

    orig = ai_probe.prepare_user
    gentle = {"value": "false"}

    def pairs(s):
        return [tuple(kv.split("=", 1)) for kv in s.split(";") if kv.strip()]

    def prepare(work):
        orig(work)
        p = work / "options.cfg"
        t = p.read_text(encoding="utf-8")
        keys = [("oxceGentle", gentle["value"]), ("oxceGentleAsk", "false")] + pairs(a.set)
        if gentle["value"] == "false":
            keys += pairs(a.off_set)
        for key, val in keys:
            t, n = re.subn(rf"(?m)^(\s*){key}: .*$", rf"\g<1>{key}: {val}", t)
            if n == 0:  # ключа нет - в установке он по умолчанию; дописываем в раздел options
                t, n = re.subn(r"(?m)^options:\s*$", f"options:\n  {key}: {val}", t, count=1)
            if n != 1:
                sys.exit(f"в options.cfg прогона не записать {key}")
        p.write_bytes(t.encode("utf-8"))

    ai_probe.prepare_user = prepare

    scenarios = [("save", Path(s)) for s in a.save]
    scenarios += [("seed", int(s)) for s in a.seeds.split(",") if s.strip()]
    if not scenarios:
        sys.exit("нет боёв: --seeds или --save")

    def play(kind, what, label, on, tactics=False):
        gentle["value"] = "true" if on else "false"
        name = f"gentle_det_{label}"
        if kind == "save":
            r = ai_probe.run(what, turns=a.turns, name=name, timeout=1800, bot=True, tactics=tactics)
        else:
            r = ai_probe.run(None, turns=a.turns, name=name, timeout=1800, bot=True, seed=what, campaign=a.campaign,
                             tactics=tactics)
        s, c = stream(r.log)
        if not r.finished or not s["[AIRESULT]"]:
            print(f"  {label}: бой не доигран ({r.log})")
            return None, c
        return s, c

    failed = []
    total = {}
    controls = []
    for i, (kind, what) in enumerate(scenarios):
        tag = f"{kind}{Path(str(what)).stem}"
        off, cov = play(kind, what, tag + "_off", False)
        on, _ = play(kind, what, tag + "_on", True)
        for k, v in cov.items():
            total[k] = total.get(k, 0) + v
        if off is None or on is None:
            failed.append(f"{tag}: бой не доигран")
            continue
        sizes = ", ".join(f"{t.strip('[]')} {len(off[t])}" for t in COMPARED)
        d = first_diff(off, on)
        print(f"{tag}: {'IDENTICAL' if d is None else 'DIFFERENT'} ({sizes}); покрытие {cov}")
        if d:
            failed.append(f"{tag}: нежный режим изменил бой - {d[0]} #{d[1]}:\n  выкл {d[2]}\n  вкл  {d[3]}")
        if not a.no_control:
            ctl, _ = play(kind, what, tag + "_ctl", False, tactics=True)
            dc = first_diff(off, ctl, play_only=True) if ctl else None
            print(f"  контроль (правило ИИ tactics): {'разошёлся - %s #%d' % dc[:2] if dc else 'не разошёлся'}")
            controls.append(bool(dc))
    if not a.no_control and not any(controls):
        failed.append("контроль ни в одном бою не изменил игру: сравнение слепое (R-086)")
    missing = [k for k in ("reaction", "explosion", "dead") if not total.get(k)]
    if not total.get("floor") and not total.get("view"):
        missing.append("floor")
    print(f"покрытие всего: {total}")
    if missing:
        failed.append(f"не покрыто: {', '.join(missing)} - добавь бой (--seeds/--save), где это есть")
    if failed:
        print("ПРОВАЛ:")
        for f in failed:
            print(" -", f)
        sys.exit(1)
    print("ok: нежный режим не меняет ни одного решения, состояния и итога")


if __name__ == "__main__":
    main()
