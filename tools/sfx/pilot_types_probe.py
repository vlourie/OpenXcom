"""Проба голосов пилотов по типам бойцов (тикет XP-000519): для каждого из 27 типов бойцов (раздел soldiers мода
hd_voices_ru без собак) три реплики пилота - select, attack, damaged - голосом этого типа. Только проба для
прослушивания Vitali: в мод и в движок ничего не ставится, прежние голоса (art/sfx/voicepack) не трогаются.

1. Таблица: тип -> основной голос V### (самый частый в его voiceSets; при равенстве - тот, что стоит в
   voiceSetsMale/Female), пол и имя из карточки сценария, русское имя типа из строк мода. Если основной голос уже взят
   другим типом, берётся следующий по частоте; нет следующего - повтор (в таблице отмечен «делит с»).
2. Тексты: из docs/research/voice-script-pilots.md - Ж из V901, М и Н из V903. Реплика события у типа своя
   (по номеру типа в таблице), чтобы типы с общим голосом не говорили одно и то же.
3. Запись (видеокарта): VoxCPM2, клон по опорному голосу этого V### (ref и ref_text из его voice.json), подача и
   ворота дублей - как в gen_voicepack (line_params, judge: полоса высоты, для TIMBRE ещё F3 и yin, R-367; нулевой f0
   мужского голоса перемеряется yin, R-509), 2 годных дубля из 3, лучший - распознаванием (живой и близкий к тексту).
4. Радио (без видеокарты): выбранные реплики через RADIO из build_pilot_voices -> .ogg рядом с .wav, probe.tsv.

Выход: art/sfx/pilot_types_probe/<тип>/<событие>.wav и .ogg, probe.tsv, state.json (продолжение с места), _takes/ (дубли).
Готовое при перезапуске не переделывается. Карту уступает: после каждой реплики проверяется GPUQ_YIELD_FILE, код 75.

    py -3 tools/sfx/pilot_types_probe.py --list           таблица и тексты, без видеокарты и VoiceFactory
    py -3 tools/sfx/pilot_types_probe.py --encode         только радио и probe.tsv из уже выбранного, без видеокарты
Запись - только через очередь видеокарты, интерпретатор VoiceFactory абсолютным путём (R-097):
    py -3 tools/gpuq.py add --name pilot-types-probe --prio 2 --preemptible -- D:/VoiceFactory/runtime/venv/Scripts/python.exe E:/OpenXCom/tools/sfx/pilot_types_probe.py
"""
import argparse
import collections
import json
import logging
import re
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import voice_script                                  # noqa: E402  (только стандартная библиотека)

ROOT = HERE.parents[1]
PILOTS = ROOT / "docs/research/voice-script-pilots.md"
MODS = ROOT / "Пиратки/Dioxine_XPiratez/user/mods"
RUL = MODS / "hd_voices_ru/Ruleset/hd_voices_ru.rul"
LANG_RU = (MODS / "Piratez/Language/ru.yml", MODS / "XPZ RU-patch/Language/ru.yml")   # позднее перекрывает раннее
VOICEPACK = ROOT / "art/sfx/voicepack"
OUT = ROOT / "art/sfx/pilot_types_probe"
STATE = OUT / "state.json"
TAKES = OUT / "_takes"
SKIP_TYPES = {"STR_SOLDIER_DOGE", "STR_SOLDIER_BLOODOGE"}
EVENTS = ("select", "attack", "damaged")
PILOT_CARD = {"Ж": "V901", "М": "V903", "Н": "V903"}
TAKES_GOOD, TAKES_MAX = 2, 3                         # годных дублей до остановки, дублей не больше
TAKE_SEED_BASE = 1000                                # сид дубля = SEED_LINE + 1000 + 10 * номер типа + дубль: не как у боевых голосов
RECOGNIZED = 0.85                                    # gen_voicepack.CLOSE_LIVE
log = logging.getLogger("pilot_types_probe")


# ---------- таблица типов ----------

def soldier_types():
    """{тип: {"map": Counter по voiceSets, "default": [voiceSetsMale, voiceSetsFemale без повторов]}} в порядке рулсета."""
    lines = RUL.read_text(encoding="utf-8-sig").splitlines()
    i0 = lines.index("soldiers:")
    i1 = next(i for i in range(i0 + 1, len(lines)) if re.match(r"^\S", lines[i]))
    out = collections.OrderedDict()
    cur = None
    for ln in lines[i0 + 1:i1]:
        m = re.match(r"^  - type: (\S+)", ln)
        if m:
            cur = out[m.group(1)] = {"map": collections.Counter(), "default": []}
            continue
        m = re.match(r"^    voiceSets(?:Male|Female): \[(.*)\]", ln)
        if m and cur is not None:
            for v in re.findall(r"VP_(V\d+)", m.group(1)):
                if v not in cur["default"]:
                    cur["default"].append(v)
            continue
        m = re.match(r"^      [A-Za-z]+\d+: \[(.*)\]", ln)
        if m and cur is not None:
            for v in re.findall(r"VP_(V\d+)", m.group(1)):
                cur["map"][v] += 1
    return out


def type_names():
    names = {}
    for p in LANG_RU:
        if p.exists():
            for ln in p.read_text(encoding="utf-8-sig").splitlines():
                m = re.match(r'^\s+(STR_SOLDIER(?:_[A-Z]+)*):\s*"(.*)"\s*$', ln)
                if m:
                    names[m.group(1)] = m.group(2)
    return names


def ranked(info):
    """Голоса типа: по убыванию частоты в voiceSets, при равенстве - сперва заданные в voiceSetsMale/Female."""
    order = {}
    for v in info["default"] + list(info["map"]):
        order.setdefault(v, len(order))
    return sorted(order, key=lambda v: (-info["map"].get(v, 0), order[v]))


def pilot_cards():
    return {v["id"]: v for v in voice_script._read(PILOTS, {})}


def build_table():
    types = soldier_types()
    names = type_names()
    cards = {v["id"]: v for v in voice_script.parse()}       # карточки голосов бойцов (с запасными V4xx+)
    pil = pilot_cards()
    rows, used = [], {}
    for t, info in types.items():
        if t in SKIP_TYPES:
            continue
        rk = ranked(info)
        pick = next((v for v in rk if v not in used), None)
        repeat = pick is None
        if repeat:
            pick = rk[0]
        used.setdefault(pick, t)
        reg = cards[pick]["reg"]
        rows.append({"type": t, "ti": len(rows), "name": names.get(t, ""), "voice": pick, "reg": reg,
                     "ranked": rk, "counts": dict(info["map"]), "repeat": repeat,
                     "next_taken": (not repeat) and pick != rk[0]})
    by_voice = collections.defaultdict(list)
    for r in rows:
        by_voice[r["voice"]].append(r["type"])
    for r in rows:
        r["shares"] = [t for t in by_voice[r["voice"]] if t != r["type"]]
        card = pil[PILOT_CARD[r["reg"]]]
        r["lines"] = {}
        for ev in EVENTS:
            ls = sorted((ln for ln in card["lines"] if ln["part"] == ev), key=lambda ln: ln["n"])
            ln = ls[r["ti"] % len(ls)]
            r["lines"][ev] = {"n": ln["n"], "ru": ln["ru"], "part": ev, "card": card["id"]}
    return rows


def print_table(rows):
    print(f"типов: {len(rows)}")
    for r in rows:
        extra = []
        if r["shares"]:
            extra.append("делит с " + ", ".join(s.replace("STR_SOLDIER_", "").replace("STR_SOLDIER", "BASE") for s in r["shares"]))
        if r["repeat"]:
            extra.append("ПОВТОР: следующего голоса нет")
        elif r["next_taken"]:
            extra.append(f"взят следующий по частоте (первый {r['ranked'][0]} занят)")
        print(f"{r['type']:24} {r['name']:18} {r['voice']} [{r['reg']}]  голоса: {r['ranked']}  {'; '.join(extra)}")
        for ev in EVENTS:
            ln = r["lines"][ev]
            print(f"      {ev:8} {ln['card']}#{ln['n']}  {ln['ru']}")


# ---------- состояние ----------

def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8-sig"))
    return {"items": {}}


def save_state(st):
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8-sig")
    tmp.replace(STATE)


def items_of(rows, st):
    """Задания (тип, событие); запись, у которой изменились голос или текст, начинается заново."""
    out = []
    for r in rows:
        for ev in EVENTS:
            key = f"{r['type']}/{ev}"
            ln = r["lines"][ev]
            it = st["items"].get(key)
            if it is None or it["voice"] != r["voice"] or it["text"] != ln["ru"]:
                it = st["items"][key] = {"type": r["type"], "event": ev, "voice": r["voice"], "reg": r["reg"],
                                         "card": ln["card"], "n": ln["n"], "text": ln["ru"], "takes": []}
            out.append((r, ev, ln, it))
    return out


# ---------- запись ----------

def wav_rel(p):
    return str(Path(p).relative_to(OUT)).replace("\\", "/")


def yin_median(wav, sr):
    """Медиана yin по кадрам громче медианы (R-509): pyin на коротком хриплом выкрике даёт 0."""
    import librosa
    import numpy as np
    y = np.asarray(wav, dtype=np.float32)
    f = librosa.yin(y, fmin=60, fmax=400, sr=sr, frame_length=2048)
    rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=512)[0]
    n = min(len(f), len(rms))
    f, rms = f[:n], rms[:n]
    sel = rms > np.median(rms)
    return float(np.median(f[sel])) if sel.any() else 0.0


def judge_take(GV, card, wav, sr):
    """gen_voicepack.judge по карточке голоса + ворота мужского f0 из R-509 (для голосов не из оригинала игры)."""
    j = GV.judge(card, wav, sr)
    if card["reg"] == "М" and card["id"] not in GV.ORIG and not GV.gated(card):
        y = yin_median(wav, sr)
        j["yin"] = round(y, 1)
        if j["f0"] == 0:
            j["band"] = 60 <= y <= 130                  # pyin не нашёл тон: судит yin
        elif y and max(j["f0"] / y, y / j["f0"]) >= 1.8:
            j["band"] = False                           # pyin и yin разошлись вдвое: октавная ошибка, дубль не берём
    return j


def record(GV, rows, todo, st, cards):
    G = GV.G
    cfg = G.C.load(G.VF)
    eng = GV.line_engine(cfg)
    profiles = {}
    t0 = time.time()
    done = 0
    for r, ev, ln, it in todo:
        vid = r["voice"]
        if vid not in profiles:
            vs = json.loads((VOICEPACK / vid / "voice.json").read_text(encoding="utf-8-sig"))
            if not vs.get("ref") or not vs.get("ref_text"):
                raise SystemExit(f"{vid}: в voice.json нет ref/ref_text")
            profiles[vid] = GV.line_profile({"id": vid}, vs)
        d = TAKES / r["type"]
        d.mkdir(parents=True, exist_ok=True)
        card = cards[vid]
        line = {"ru": ln["ru"], "part": ev, "n": ln["n"]}
        it["takes"] = []
        good = 0
        for k in range(TAKES_MAX):
            if good >= TAKES_GOOD:
                break
            take = {"take": k + 1}
            try:
                wav, sr, _ = eng.generate(ln["ru"], profiles[vid], GV.line_params(line, TAKE_SEED_BASE + 10 * r["ti"] + k))
                wav = G.post(wav, sr)
                path = d / f"{ev}.t{k + 1}.wav"
                GV.sf.write(str(path), wav, sr, subtype="PCM_16")
                take.update(file=wav_rel(path), dur=round(len(wav) / sr, 2), **judge_take(GV, card, wav, sr))
                good += take["band"] and take["dur"] <= GV.LINE_MAX_S
            except Exception as e:
                take["error"] = str(e)[:300]
                log.warning("%s %s: %s", r["type"], ev, e)
            it["takes"].append(take)
        it["takes_done"] = True
        done += 1
        log.info("%s %s (%s): дублей %d, годных %d [%d/%d, %.0f мин]", r["type"], ev, vid, len(it["takes"]), good,
                 done, len(todo), (time.time() - t0) / 60)
        save_state(st)
        GV.yield_now()                                   # состояние уже сохранено; в voicepack ничего не пишется
    G.free(eng)


def choose(GV, todo, st):
    """Выбор дубля распознаванием - как gen_voicepack.asr_pass: из годных по высоте и длине самый живой, который
    распознан близко к тексту; иначе лучший по (полоса, длина, близость)."""
    G = GV.G

    def hear(t, text):
        if "close" not in t:
            t["heard"] = G.heard(OUT / t["file"], "ru")
            t["close"] = round(G.closeness(text, t["heard"]), 3)

    done = 0
    for r, ev, ln, it in todo:
        tk = [t for t in it["takes"] if "file" in t]
        if not tk:
            it["error"] = "ни одного дубля"
            continue
        pick = None
        for t in sorted((t for t in tk if t["band"] and t["dur"] <= GV.LINE_MAX_S), key=lambda t: -t["expr"]):
            hear(t, it["text"])
            if t["close"] >= GV.CLOSE_LIVE:
                pick = t
                break
        if pick is None:
            for t in tk:
                hear(t, it["text"])
            pick = max(tk, key=lambda t: (t["band"], t["dur"] <= GV.LINE_MAX_S, t["close"], -t["dur"]))
        dst = OUT / r["type"] / f"{ev}.wav"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(OUT / pick["file"], dst)
        it["chosen"] = {"take": pick["take"], "file": wav_rel(dst), "dur": pick["dur"], "f0": pick.get("f0"),
                        "band": pick["band"], "heard": pick["heard"], "close": pick["close"]}
        done += 1
        save_state(st)
        GV.yield_now()
    GV.Q.free_asr()
    log.info("выбрано реплик: %d", done)


# ---------- радио и таблица (без видеокарты) ----------

def encode_all(rows, st):
    import build_pilot_voices as B
    OUT.mkdir(parents=True, exist_ok=True)
    lines = ["\t".join(("тип", "имя типа", "голос", "пол", "событие", "текст", "файл", "распознано", "длительность, с",
                        "близость", "услышано", "делит голос с"))]
    n = 0
    for r in rows:
        for ev in EVENTS:
            it = st["items"].get(f"{r['type']}/{ev}")
            if not it or "chosen" not in it:
                continue
            c = it["chosen"]
            wav = OUT / c["file"]
            ogg = wav.with_suffix(".ogg")
            if not ogg.exists() or ogg.stat().st_mtime < wav.stat().st_mtime:
                B.encode(wav, ogg)
            n += 1
            lines.append("\t".join(str(x) for x in (
                r["type"], r["name"], r["voice"], r["reg"], ev, it["text"], wav_rel(ogg),
                "да" if c["close"] >= RECOGNIZED else "нет", c["dur"], c["close"], c["heard"].replace("\t", " "),
                " ".join(r["shares"]))))
    (OUT / "probe.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    log.info("радио: %d реплик -> %s, таблица %s", n, OUT, OUT / "probe.tsv")
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="таблица типов и тексты; без видеокарты")
    ap.add_argument("--encode", action="store_true", help="только радио и probe.tsv из выбранного; без видеокарты")
    ap.add_argument("--only", default="", help="через запятую: типы (STR_SOLDIER_X), остальные пропустить")
    a = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    rows = build_table()
    if a.list:
        print_table(rows)
        return
    only = {x.strip() for x in a.only.split(",") if x.strip()}
    if only:
        bad = only - {r["type"] for r in rows}
        if bad:
            raise SystemExit(f"--only: нет типов {sorted(bad)}")
    st = load_state()
    items = items_of(rows, st)
    save_state(st)
    if not a.encode:
        import gen_voicepack as GV                       # окружение VoiceFactory
        cards = {v["id"]: v for v in voice_script.parse()}
        want = [x for x in items if not only or x[0]["type"] in only]
        todo = [x for x in want if not x[3].get("takes_done")]
        log.info("реплик всего %d, к записи %d", len(want), len(todo))
        if todo:
            record(GV, rows, todo, st, cards)
        pick = [x for x in want if "chosen" not in x[3]]
        if pick:
            choose(GV, pick, st)
    try:
        encode_all(rows, st)
    except Exception as e:                               # нет ffmpeg в PATH задания - не повод терять запись
        log.warning("радио не собрано (%s): запустить --encode отдельно", e)


if __name__ == "__main__":
    main()
