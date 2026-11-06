"""Голоса пилотов по типам бойцов (тикет XP-000519, Vitali 06.11 на странице пробы: «все годятся»): все 120 реплик
сценария docs/research/voice-script-pilots.md на двух языках голосом типа. Таблица тип -> голос - из пробы
(pilot_types_probe.build_table), опорный голос, подача и ворота дублей - те же. Женские типы читают тексты V901 и V902,
мужские и нелюди - V903 и V904 (как в пробе; у нелюдей и в боевых репликах мужской род). Общие реплики воздуха и земли
(9 из 60) пишутся один раз; три пары типов с одним голосом (ALIAS) пишутся один раз, движок берёт набор пары.

Проходы: запись -> выбор дубля распознаванием -> дубли слабым репликам (распознаны ниже RECOGNIZED, вне полосы, длинные) ->
выбор среди них. Выход - art/sfx/pilot_types/<V###>/<ru|en>/*.wav, state.json (продолжение с места), report.tsv.
Прежние голоса (art/sfx/voicepack) не трогаются. В мод ставит build_pilot_voices.py --types.

    py -3 tools/sfx/gen_pilot_types.py --list             сколько реплик, без видеокарты и VoiceFactory
Запись - только через очередь видеокарты, интерпретатор VoiceFactory абсолютным путём (R-097):
    py -3 tools/gpuq.py add --name pilot-types --prio 2 --preemptible -- D:/VoiceFactory/runtime/venv/Scripts/python.exe E:/OpenXCom/tools/sfx/gen_pilot_types.py
"""
import argparse
import hashlib
import json
import logging
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pilot_types_probe as P                        # noqa: E402  (только стандартная библиотека)

ROOT = HERE.parents[1]
OUT = ROOT / "art/sfx/pilot_types"
VOICEPACK = ROOT / "art/sfx/voicepack"
# у этих типов в паке нет другого голоса: набор один на пару, те же имена в HdPilotVoice.cpp (typeSet)
ALIAS = {"STR_SOLDIER_S": "STR_SOLDIER", "STR_SOLDIER_V": "STR_SOLDIER_M", "STR_SOLDIER_PUREBLOOD": "STR_SOLDIER_SLAVE"}
CARD = {"air": {"Ж": "V901", "М": "V903", "Н": "V903"}, "ground": {"Ж": "V902", "М": "V904", "Н": "V904"}}
LANGS = ("ru", "en")
TAKES_GOOD, TAKES_MAX, FIX_MORE = 2, 3, 4            # годных дублей до остановки, дублей не больше, ещё слабой реплике
SEED_BASE = 2000                                     # сид дубля = SEED_LINE + 2000 + 10 * номер голоса + дубль
RECOGNIZED = P.RECOGNIZED
DROP_BELOW, EVENT_KEEP = 0.7, 3                      # в мод не идёт реплика с близостью ниже, пока в событии остаётся столько
log = logging.getLogger("gen_pilot_types")


def rows_own():
    """Строки таблицы типов без типов-двойников; ALIAS сверяется с таблицей."""
    rows = P.build_table()
    by = {r["type"]: r for r in rows}
    for t, own in ALIAS.items():
        if by[t]["voice"] != by[own]["voice"]:
            raise SystemExit(f"{t} и {own}: голоса разошлись, ALIAS устарел")
    left = [r["type"] for r in rows if r["shares"] and r["type"] not in ALIAS and r["type"] not in ALIAS.values()]
    if left:
        raise SystemExit(f"новые типы с общим голосом: {left}")
    return [r for r in rows if r["type"] not in ALIAS]


def key_of(lang, text):
    return lang + "/" + text


def script_of(reg, cards=None):
    """Реплики типа: [(kind, lang, ln)] в порядке сценария."""
    cards = cards or P.pilot_cards()
    return [(kind, lang, ln) for kind in CARD for lang in LANGS for ln in cards[CARD[kind][reg]]["lines"]]


def load_state(vid):
    p = OUT / vid / "state.json"
    return json.loads(p.read_text(encoding="utf-8-sig")) if p.exists() else {"id": vid, "items": {}}


def save_state(st):
    d = OUT / st["id"]
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / "state.json.tmp"
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=0), encoding="utf-8-sig")
    tmp.replace(d / "state.json")


def build_states(rows):
    """{голос: состояние} с заданиями; общие реплики воздуха и земли - одно задание."""
    cards = P.pilot_cards()
    states = {}
    for vi, r in enumerate(rows):
        vid = r["voice"]
        st = states.get(vid) or load_state(vid)
        st["vi"] = vi
        for _kind, lang, ln in script_of(r["reg"], cards):
            st["items"].setdefault(key_of(lang, ln[lang]), {
                "lang": lang, "text": ln[lang], "ru": ln["ru"], "part": ln["part"], "n": ln["n"],
                "file": hashlib.md5(ln[lang].encode("utf-8")).hexdigest()[:10], "takes": []})
        states[vid] = st
    return states


def gen_take(GV, eng, prof, card, st, it, k):
    G = GV.G
    take = {"take": k + 1}
    try:
        line = {"ru": it["ru"], "part": it["part"], "n": it["n"]}
        wav, sr, _ = eng.generate(it["text"], prof, GV.line_params(line, SEED_BASE + 10 * st["vi"] + k))
        wav = G.post(wav, sr)
        path = OUT / st["id"] / it["lang"] / f"{it['file']}.t{k + 1}.wav"
        path.parent.mkdir(parents=True, exist_ok=True)
        GV.sf.write(str(path), wav, sr, subtype="PCM_16")
        take.update(file=str(path.relative_to(OUT)).replace("\\", "/"), dur=round(len(wav) / sr, 2),
                    **P.judge_take(GV, card, wav, sr))
    except Exception as e:
        take["error"] = str(e)[:300]
        log.warning("%s %s: %s", st["id"], it["text"], e)
    it["takes"].append(take)
    return bool(take.get("band")) and take.get("dur", 99) <= GV.LINE_MAX_S


def good_take(GV, it, t):
    return "file" in t and t["band"] and t["dur"] <= GV.LINE_MAX_S


def weak(GV, it):
    c = it.get("chosen")
    return not c or c["close"] < RECOGNIZED or not c["band"] or c["dur"] > GV.LINE_MAX_S


def gen_pass(GV, states, cards, jobs, more):
    """jobs: [(голос, задание)]; more=False - обычная запись, True - ещё дубли слабым."""
    if not jobs:
        return
    G = GV.G
    eng = GV.line_engine(G.C.load(G.VF))
    profiles = {}
    t0 = last = time.time()
    for i, (vid, it) in enumerate(jobs, 1):
        st = states[vid]
        if vid not in profiles:
            vs = json.loads((VOICEPACK / vid / "voice.json").read_text(encoding="utf-8-sig"))
            if not vs.get("ref") or not vs.get("ref_text"):
                raise SystemExit(f"{vid}: в voice.json нет ref/ref_text")
            profiles[vid] = GV.line_profile({"id": vid}, vs)
        if more:
            k0 = max((t["take"] for t in it["takes"]), default=0)
            for k in range(k0, k0 + FIX_MORE):
                gen_take(GV, eng, profiles[vid], cards[vid], st, it, k)
            it["fix_done"] = True
        else:
            good = 0
            it["takes"] = []
            for k in range(TAKES_MAX):
                if good >= TAKES_GOOD:
                    break
                good += gen_take(GV, eng, profiles[vid], cards[vid], st, it, k)
            it["takes_done"] = True
        save_state(st)
        GV.yield_now()                                   # состояние уже сохранено
        if time.time() - last > 300:
            log.info("%s: %d/%d, %.0f мин", "дубли" if more else "запись", i, len(jobs), (time.time() - t0) / 60)
            last = time.time()
    G.free(eng)
    log.info("%s: %d реплик за %.0f мин", "дубли" if more else "запись", len(jobs), (time.time() - t0) / 60)


def choose_pass(GV, states, jobs):
    """Как gen_voicepack.asr_pass: из годных самый живой, распознанный близко к тексту; иначе лучший по всем."""
    G = GV.G

    def hear(t, it):
        if "close" not in t:
            t["heard"] = G.heard(OUT / t["file"], it["lang"])
            t["close"] = round(G.closeness(it["text"], t["heard"]), 3)

    for vid, it in jobs:
        tk = [t for t in it["takes"] if "file" in t]
        if not tk:
            it["error"] = "ни одного дубля"
            continue
        pick = None
        for t in sorted((t for t in tk if good_take(GV, it, t)), key=lambda t: -t["expr"]):
            hear(t, it)
            if t["close"] >= RECOGNIZED:
                pick = t
                break
        if pick is None:
            for t in tk:
                hear(t, it)
            pick = max(tk, key=lambda t: (t["band"], t["dur"] <= GV.LINE_MAX_S, t["close"], -t["dur"]))
        it["chosen"] = {k: pick[k] for k in ("take", "file", "dur", "band", "heard", "close")}
        save_state(states[vid])
        GV.yield_now()
    GV.Q.free_asr()
    log.info("выбрано реплик: %d", len(jobs))


def write_report(rows, states):
    lines = ["\t".join(("голос", "тип", "имя", "реплик", "без выбора", "распознано плохо", "ниже " + str(DROP_BELOW)))]
    total = bad = low = 0
    for r in rows:
        items = list(states[r["voice"]]["items"].values())
        ch = [it["chosen"] for it in items if "chosen" in it]
        w = sum(c["close"] < RECOGNIZED for c in ch)
        d = sum(c["close"] < DROP_BELOW for c in ch)
        total += len(ch)
        bad += w
        low += d
        lines.append("\t".join(str(x) for x in (r["voice"], r["type"], r["name"], len(items), len(items) - len(ch), w, d)))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "report.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    log.info("выбрано %d, распознано плохо %d, ниже %s: %d -> %s", total, bad, DROP_BELOW, low, OUT / "report.tsv")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="сколько реплик; без видеокарты")
    a = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    rows = rows_own()
    states = build_states(rows)
    jobs = [(vid, it) for vid, st in states.items() for it in st["items"].values()]
    log.info("голосов %d, реплик %d, записано %d, выбрано %d", len(states), len(jobs),
             sum("takes_done" in it for _v, it in jobs), sum("chosen" in it for _v, it in jobs))
    if a.list:
        write_report(rows, states)
        return
    import gen_voicepack as GV                           # окружение VoiceFactory
    import voice_script
    cards = {v["id"]: v for v in voice_script.parse()}
    gen_pass(GV, states, cards, [(v, it) for v, it in jobs if not it.get("takes_done")], False)
    choose_pass(GV, states, [(v, it) for v, it in jobs if "chosen" not in it and it["takes"]])
    fix = [(v, it) for v, it in jobs if weak(GV, it) and not it.get("fix_done")]
    log.info("слабых реплик после первого выбора: %d", len(fix))
    gen_pass(GV, states, cards, fix, True)
    choose_pass(GV, states, [(v, it) for v, it in jobs if it.get("fix_done") and not it.get("fix_chosen")])
    for v, it in jobs:
        if it.get("fix_done") and not it.get("fix_chosen"):
            it["fix_chosen"] = True
    for st in states.values():
        save_state(st)
    write_report(rows, states)


if __name__ == "__main__":
    main()
