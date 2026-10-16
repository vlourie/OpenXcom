"""Полный набор голосов по сценарию озвучки (docs/research/voice-recording-script.md): 157 голосов, RU и EN.

Тот же путь, что у тестового набора (gen_voices_test.py), но по голосу на папку и с продолжением:
1. VoxCPM2, режим design: опорный голос по карточке (регистр, имя, «как играть голосом»), опорная фраза -
   первые реплики голоса по-русски. Кандидаты, пока DESIGN_GOOD не лягут в полосу высоты регистра
   (Ж >= 180 Гц, М <= 130 Гц - слово Vitali 15.10; Н без полосы), не больше DESIGN_MAX.
   Опорный - в полосе, распознаётся близко к тексту, дальше от границы полосы.
2. Fish S2 Pro: каждая реплика RU и EN опорным голосом, дубли, пока LINE_GOOD не лягут в полосу и по
   длине (LINE_MAX_S), не больше LINE_MAX.
3. faster-whisper: распознавание дублей, лучший - chosen.

Выход: art/sfx/voicepack/<V###>/ref.d<k>.wav, <ru|en>/<NN>.t<k>.wav, voice.json (пишется после каждого
голоса - упавшее задание продолжается с того же места тем же запуском). Обработка (робот, демон, рация)
- после, при сборке мода: сценарий велит писать разборчивую основу.

Только через очередь видеокарты, интерпретатор VoiceFactory абсолютным путём (R-097):
    py -3 tools/gpuq.py add --name voicepack-crew -- D:/VoiceFactory/runtime/venv/Scripts/python.exe tools/sfx/gen_voicepack.py --ids V001-V024
"""
import argparse
import json
import logging
import math
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gen_voices_test as G                      # noqa: E402  (окружение VoiceFactory, post/pitch/heard)
import voice_script                              # noqa: E402
from vf import qc as Q                           # noqa: E402
from vf.engines.base import GenParams, VoiceProfile   # noqa: E402
import soundfile as sf                           # noqa: E402

log = logging.getLogger("gen_voicepack")
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "art/sfx/voicepack"

BAND = {"Ж": (180, 500), "М": (60, 130)}         # Н - без полосы
REG_WORD = {"Ж": "явно женский голос средней высоты, женщина", "М": "мужской голос, мужчина",
            "Н": "нечеловеческий голос, но речь разборчивая"}
# «низкий» и «грудной» в женской карточке VoxCPM2 делает мужским (проба V001 16.10: 0 из 10 в полосе) -
# высоту задаёт REG_WORD, из указаний актёру она убирается
FEMALE_DROP = re.compile(r"\b(?:[Оо]чень )?(?:[Нн]изк|[Гг]рудн)\w*\s*")
# опорный у границы полосы: Fish в репликах уводит голос ниже опорного (15.10: 182 -> 150 Гц),
# поэтому опорный сдвигается внутрь полосы до TARGET, не дальше SHIFT_MAX полутонов
SAFE = {"Ж": (215, 500), "М": (75, 115)}      # ниже 75 у pyin - скрип связок, а не тон
TARGET = {"Ж": 225.0, "М": 105.0}
SHIFT_MAX = 5.0
DESIGN_GOOD, DESIGN_MAX = 3, 10
LINE_GOOD, LINE_MAX = 2, 4
FIX_MORE = 6                                     # --fix: ещё дублей реплике вне полосы
LINE_MAX_S = 3.0                                 # сценарий: реплика 1-3 с
REF_CHARS = 70                                   # опорная фраза ~5-9 с
SEED_DESIGN, SEED_LINE = 9100, 9300
DESIGN_SEED_OFF = 0                                # --design-seed: другие кандидаты опорного при --redo
COMPILE = True
PART_TAG = {"Повторные нажатия": "[annoyed]", "Под огнём": "[angry]"}
# 16.10 Vitali на слух: женские голоса - мужики, хотя высота в полосе. Тембр мужской: третья форманта
# (длина тракта) у них 2408 Гц, у мужских 2304, у принятых женских 2611 (R-367). Этим - звонкое описание
# и ворота по F3 и yin (pyin у Hologal ошибся октавой: 418 против 118)
TIMBRE = set("V005 V012 V016 V017 V019 V032 V043 V055 V060 V063 V072 V086 V109 V129 V133 V141 V155".split())
TIMBRE_WORD = "молодая женщина, звонкий высокий женский голос, сопрано, никаких мужских нот"
F3_MIN_REF, F3_MIN_LINE, YIN_MIN = 2650, 2550, 175
TIMBRE_DESIGN_MAX, TIMBRE_LINE_MAX = 20, 6
# описание голоса вместо карточки: «мощный... мужского стража» даёт модели мужчину (V086: 17 из 20 кандидатов
# ниже 180 Гц, выбран 93 Гц). Сценарий не правим - только текст для модели
DIRECTION = {"V086": "Сильная уверенная женщина-воин, звучный женский голос; насмешливая, спокойная."}


def gated(v):
    """Ворота по F3 и yin: голоса на починке тембра и все новые женские запасные (V4xx-V7xx)."""
    return v["id"] in TIMBRE or (v["reg"] == "Ж" and "same_as" in v)


def band_ok(v, f0):
    lo, hi = BAND.get(v["reg"], (0, 10000))
    return lo <= f0 <= hi


def formant3(wav, sr):
    """Медиана третьей форманты (LPC 12, 10 кГц) по громким кадрам: у женщин выше - тракт короче."""
    import librosa
    import numpy as np
    y = librosa.resample(np.asarray(wav, dtype=np.float32), orig_sr=sr, target_sr=10000)
    if len(y) < 800:
        return 0.0
    fr = librosa.util.frame(y, frame_length=400, hop_length=200).T
    rms = np.sqrt((fr ** 2).mean(1))
    out = []
    for f in fr[rms > np.percentile(rms, 60)]:
        f = f * np.hamming(len(f))
        f = np.append(f[0], f[1:] - 0.97 * f[:-1])
        try:
            r = np.roots(librosa.lpc(f, order=12))
        except Exception:
            continue
        r = r[np.imag(r) > 0]
        ang = np.arctan2(np.imag(r), np.real(r)) * 10000 / (2 * np.pi)
        bw = -0.5 * 10000 / np.pi * np.log(np.abs(r))
        fs = sorted(a for a, b in zip(ang, bw) if a > 200 and b < 400)
        if len(fs) >= 3:
            out.append(fs[2])
    return round(float(np.median(out)), 0) if out else 0.0


def judge(v, wav, sr, f3_min=F3_MIN_LINE):
    """Высота и полоса; голосам TIMBRE ещё F3 и yin (в полосе - только с женским трактом)."""
    f0 = G.pitch(wav, sr)
    res = {"f0": f0, "band": band_ok(v, f0)}
    if gated(v):
        import librosa
        import numpy as np
        yin = float(np.median(librosa.yin(np.asarray(wav, dtype=np.float32), fmin=60, fmax=500, sr=sr,
                                          frame_length=2048)))
        res.update(f3=formant3(wav, sr), yin=round(yin, 1))
        res["band"] = res["band"] and res["f3"] >= f3_min and yin >= YIN_MIN
    return res


def safe_ok(v, f0):
    lo, hi = SAFE.get(v["reg"], (0, 10000))
    return lo <= f0 <= hi


def margin(v, f0):
    """Близость к TARGET в полутонах (не середина полосы: у Ж она 340 Гц - писк, с него реплики падают)."""
    if v["reg"] not in TARGET:
        return 0
    return -abs(12 * math.log2(f0 / TARGET[v["reg"]])) if f0 > 0 else -99


def design_text(v):
    direction = DIRECTION.get(v["id"], v["direction"])
    if v["reg"] == "Ж":
        direction = FEMALE_DROP.sub("", direction)
        direction = direction[:1].upper() + direction[1:]
    reg = TIMBRE_WORD if v["id"] in TIMBRE else REG_WORD[v["reg"]]
    return f"{reg}. Персонаж: {v['name']}. {direction}"


def shift_into_safe(v, path, f0):
    """Опорный вне безопасной полосы - сдвиг высоты к TARGET (librosa); новый файл, f0 после сдвига."""
    lo, hi = SAFE.get(v["reg"], (0, 10000))
    if lo <= f0 <= hi or f0 <= 0:
        return None
    import librosa
    import numpy as np
    steps = float(np.clip(12 * np.log2(TARGET[v["reg"]] / f0), -SHIFT_MAX, SHIFT_MAX))
    wav, sr = sf.read(str(path), dtype="float32")
    wav = librosa.effects.pitch_shift(wav, sr=sr, n_steps=steps)
    out = path.with_name(path.stem + ".shift.wav")
    sf.write(str(out), G.post(wav, sr), sr, subtype="PCM_16")
    f1 = G.pitch(wav, sr)
    # сдвиг, после которого тон не мерится или ушёл из полосы, хуже исходного (V114: бас +5 пт в писк)
    return (out, round(steps, 2), f1) if band_ok(v, f1) else None


def ref_text(v):
    out = ""
    for ln in v["lines"]:
        out = (out + " " + ln["ru"]).strip()
        if len(out) >= REF_CHARS:
            break
    return out


def tag(ln):
    if ln["part"] in PART_TAG:
        return PART_TAG[ln["part"]]
    return "[excited]" if "!" in ln["ru"] else ""


def vdir(v):
    return OUT / v["id"]


def load_state(v):
    p = vdir(v) / "voice.json"
    if p.exists():
        with open(p, encoding="utf-8-sig") as f:
            return json.load(f)
    return fresh(v)


def fresh(v):
    return {"id": v["id"], "name": v["name"], "reg": v["reg"], "section": v["section"],
            "design": design_text(v), "ref_text": ref_text(v), "script": script(v), "refs": [], "ref": None,
            "lines": []}


def script(v):
    return [[ln["n"], ln["ru"], ln["en"]] for ln in v["lines"]]


def save_state(st):
    d = OUT / st["id"]
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / "voice.json.tmp"
    with open(tmp, "w", encoding="utf-8-sig") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)
    tmp.replace(d / "voice.json")


def rel(path):
    return str(Path(path).relative_to(OUT)).replace("\\", "/")


def design_pass(cfg, todo, states):
    local = G.VF + "/models/openbmb/VoxCPM2"
    eng = G.engine(cfg, "voxcpm2", local_dir=local if Path(local).is_dir() else "")
    for v in todo:
        st = states[v["id"]]
        st["refs"] = []
        d = vdir(v)
        d.mkdir(parents=True, exist_ok=True)
        good = 0
        for k in range(TIMBRE_DESIGN_MAX if gated(v) else DESIGN_MAX):
            if good >= DESIGN_GOOD:
                break
            p = GenParams(instruction=st["design"], seed=SEED_DESIGN + DESIGN_SEED_OFF + k, cfg_value=2.0,
                          inference_timesteps=10)
            wav, sr, _ = eng.generate(st["ref_text"], None, p)
            wav = G.post(wav, sr)
            path = d / f"ref.d{k + 1}.wav"
            sf.write(str(path), wav, sr, subtype="PCM_16")
            j = judge(v, wav, sr, F3_MIN_REF)
            f0 = j["f0"]
            safe = safe_ok(v, f0) and j["band"]
            good += safe
            st["refs"].append({"take": k + 1, "file": rel(path), "dur": round(len(wav) / sr, 2), **j,
                               "safe": safe})
        log.info("%s %s: кандидатов %d, в полосе %d", v["id"], v["name"], len(st["refs"]), good)
    G.free(eng)
    # выбор опорного - распознаванием, модель синтеза уже выгружена
    for v in todo:
        st = states[v["id"]]
        best = None
        for r in st["refs"]:
            r["heard"] = G.heard(OUT / r["file"], "ru")
            r["close"] = round(G.closeness(st["ref_text"], r["heard"]), 3)
            key = (3.0 <= r["dur"] <= 14.0, r["safe"], r["close"] >= 0.9, r["band"], r.get("f3", 0) // 100,
                   margin(v, r["f0"]), r["close"])
            if best is None or key > best[0]:
                best = (key, r)
        st["ref"] = best[1]["file"]
        st["ref_f0"] = best[1]["f0"]
        shifted = shift_into_safe(v, OUT / best[1]["file"], best[1]["f0"])
        if shifted:
            st["ref"], st["ref_shift"], st["ref_f0"] = rel(shifted[0]), shifted[1], shifted[2]
        st["ref_band"] = band_ok(v, st["ref_f0"])
        save_state(st)
        log.info("%s опорный: кандидат %d, %.0f Гц%s, похожесть %.2f%s", v["id"], best[1]["take"], st["ref_f0"],
                 f" (сдвиг {st['ref_shift']:+.1f} пт с {best[1]['f0']:.0f})" if shifted else "",
                 best[1]["close"], "" if st["ref_band"] else " - ВНЕ ПОЛОСЫ")
    Q.free_asr()


def lines_pass(cfg, todo, states):
    eng = G.engine(cfg, "fish", compile=COMPILE)
    t0 = last = time.time()
    # дополнение сценария: готовые реплики голоса остаются, пишутся только новые (main, extend)
    keep = {v["id"]: {(it["lang"], it["n"]) for it in states[v["id"]]["lines"]} for v in todo}
    total = sum(1 for v in todo for lang in ("ru", "en") for ln in v["lines"] if (lang, ln["n"]) not in keep[v["id"]])
    log.info("реплик к записи: %d (голосов %d)", total, len(todo))
    done = takes = outside = 0
    for v in todo:
        st = states[v["id"]]
        prof = VoiceProfile(v["id"], "fish", {"neutral": [{"wav": str(OUT / st["ref"]), "text": st["ref_text"]}]})
        have = keep[v["id"]]
        for lang in ("ru", "en"):
            d = vdir(v) / lang
            d.mkdir(parents=True, exist_ok=True)
            for f in d.glob("*.wav"):
                if (lang, f.name[:2]) not in have:
                    f.unlink()
            for ln in v["lines"]:
                if (lang, ln["n"]) in have:
                    continue
                good = 0
                for k in range(TIMBRE_LINE_MAX if gated(v) else LINE_MAX):
                    if good >= LINE_GOOD:
                        break
                    item = {"lang": lang, "n": ln["n"], "part": ln["part"], "take": k + 1, "text": ln[lang]}
                    try:
                        wav, sr, _ = eng.generate(ln[lang], prof, GenParams(instruction=tag(ln), seed=SEED_LINE + k))
                        wav = G.post(wav, sr)
                        path = d / f"{ln['n']}.t{k + 1}.wav"
                        sf.write(str(path), wav, sr, subtype="PCM_16")
                        item.update(file=rel(path), dur=round(len(wav) / sr, 2), **judge(v, wav, sr))
                        good += item["band"] and item["dur"] <= LINE_MAX_S
                        outside += not item["band"]
                    except Exception as e:
                        item.update(error=str(e)[:300])
                        log.warning("%s %s %s: %s", v["id"], lang, ln["n"], e)
                    st["lines"].append(item)
                    takes += 1
                done += 1
                if time.time() - last > 300:
                    log.info("реплики: %d/%d, дублей %d (вне полосы %d) за %.0f мин", done, total, takes, outside,
                             (time.time() - t0) / 60)
                    last = time.time()
        st["lines_done"] = True
        save_state(st)
        log.info("%s %s: реплики готовы", v["id"], v["name"])
    G.free(eng)


def asr_pass(todo, states):
    for v in todo:
        st = states[v["id"]]
        groups = {}
        for it in st["lines"]:
            if "file" not in it:
                continue
            if "close" not in it:
                it["heard"] = G.heard(OUT / it["file"], it["lang"])
                it["close"] = round(G.closeness(it["text"], it["heard"]), 3)
            it.pop("chosen", None)
            groups.setdefault((it["lang"], it["n"]), []).append(it)
        for tk in groups.values():
            best = max(tk, key=lambda t: (t["band"], t["dur"] <= LINE_MAX_S, t["close"], -t["dur"]))
            best["chosen"] = True
        st["asr_done"] = True
        save_state(st)
    Q.free_asr()


def ref_up(v, st, steps):
    """Поднять (опустить) высоту опорного на steps полутонов; реплики голоса - заново."""
    import librosa
    wav, sr = sf.read(str(OUT / st["ref"]), dtype="float32")
    wav = librosa.effects.pitch_shift(wav, sr=sr, n_steps=steps)
    out = vdir(v) / "ref.up.wav"
    sf.write(str(out), G.post(wav, sr), sr, subtype="PCM_16")
    st["ref"], st["ref_f0"] = rel(out), G.pitch(wav, sr)
    st["ref_shift"] = round(st.get("ref_shift", 0) + steps, 2)
    st["ref_band"] = band_ok(v, st["ref_f0"])
    st["lines"], st["lines_done"], st["asr_done"] = [], False, False
    save_state(st)
    log.info("%s опорный поднят на %+.1f пт: %.0f Гц", v["id"], steps, st["ref_f0"])


def fix_pass(cfg, todo, states):
    """Дубли сверх LINE_MAX только репликам, чей лучший дубль вне полосы высоты (до FIX_MORE штук)."""
    eng = G.engine(cfg, "fish", compile=COMPILE)
    for v in todo:
        st = states[v["id"]]
        prof = VoiceProfile(v["id"], "fish", {"neutral": [{"wav": str(OUT / st["ref"]), "text": st["ref_text"]}]})
        fixed = left = 0
        for lang in ("ru", "en"):
            for ln in v["lines"]:
                tk = [it for it in st["lines"] if it["lang"] == lang and it["n"] == ln["n"] and "file" in it]
                if any(it["band"] and it["dur"] <= LINE_MAX_S for it in tk):
                    continue
                k0 = max([it["take"] for it in tk] + [0])
                ok = False
                for k in range(k0, k0 + FIX_MORE):
                    item = {"lang": lang, "n": ln["n"], "part": ln["part"], "take": k + 1, "text": ln[lang]}
                    wav, sr, _ = eng.generate(ln[lang], prof, GenParams(instruction=tag(ln), seed=SEED_LINE + k))
                    wav = G.post(wav, sr)
                    path = vdir(v) / lang / f"{ln['n']}.t{k + 1}.wav"
                    sf.write(str(path), wav, sr, subtype="PCM_16")
                    item.update(file=rel(path), dur=round(len(wav) / sr, 2), **judge(v, wav, sr))
                    st["lines"].append(item)
                    if item["band"] and item["dur"] <= LINE_MAX_S:
                        ok = True
                        break
                fixed += ok
                left += not ok
        st["asr_done"] = False
        save_state(st)
        log.info("%s исправление: реплик в полосе %d, осталось вне %d", v["id"], fixed, left)
    G.free(eng)


def pick(voices, spec):
    if not spec:
        return voices
    want = set()
    for part in spec.split(","):
        if "-" in part:
            a, b = (int(x.strip().lstrip("V")) for x in part.split("-"))
            want.update(f"V{i:03d}" for i in range(a, b + 1))
        elif part.strip():
            want.add(part.strip())
    return [v for v in voices if v["id"] in want]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="", help="V001-V024,V111; пусто - все 157")
    ap.add_argument("--redo", default="", help="через запятую: голоса сделать заново целиком")
    ap.add_argument("--no-compile", action="store_true", help="Fish без torch.compile (без компиляции ~5 ток/с)")
    ap.add_argument("--fix", action="store_true",
                    help="готовым голосам из --ids: дубли репликам вне полосы высоты (до FIX_MORE)")
    ap.add_argument("--ref-up", type=float, default=0.0,
                    help="с --fix: сдвинуть опорный на N полутонов и сделать реплики голоса заново")
    ap.add_argument("--design-seed", type=int, default=0,
                    help="сдвиг семени кандидатов опорного (с --redo, чтобы не получить тех же)")
    a = ap.parse_args()
    global COMPILE, DESIGN_SEED_OFF
    COMPILE = not a.no_compile
    DESIGN_SEED_OFF = a.design_seed
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    voices = pick(voice_script.parse(), a.ids)
    redo = {x.strip() for x in a.redo.split(",") if x.strip()}
    states = {}
    for v in voices:
        states[v["id"]] = load_state(v)
        # заново: по просьбе или если в сценарии поменялись реплики голоса
        old = states[v["id"]]
        new = script(v)
        if v["id"] in redo or old.get("design") != design_text(v):
            states[v["id"]] = fresh(v)
        elif old.get("script") != new:
            n = len(old.get("script") or [])
            if old.get("ref") and n and new[:n] == old["script"]:
                # реплики дописаны в конец (voice-script-extra.md): опорный и готовые реплики остаются
                old.update(script=new, lines_done=False, asr_done=False)
            else:
                states[v["id"]] = fresh(v)
    cfg = G.C.load(G.VF)
    t0 = time.time()
    if a.fix:
        ready = [v for v in voices if states[v["id"]].get("asr_done")]
        if a.ref_up:
            for v in ready:
                ref_up(v, states[v["id"]], a.ref_up)
        else:
            fix_pass(cfg, ready, states)
    need_ref =[v for v in voices if not states[v["id"]].get("ref")]
    if need_ref:
        design_pass(cfg, need_ref, states)
    need_lines = [v for v in voices if not states[v["id"]].get("lines_done")]
    if need_lines:
        lines_pass(cfg, need_lines, states)
    need_asr = [v for v in voices if not states[v["id"]].get("asr_done")]
    if need_asr:
        asr_pass(need_asr, states)
    bad_ref = [v["id"] for v in voices if not states[v["id"]].get("ref_band", True)]
    chosen = [it for v in voices for it in states[v["id"]]["lines"] if it.get("chosen")]
    log.info("готово за %.0f мин: голосов %d, реплик выбрано %d, вне полосы %d, плохо слышно %d, длинных %d; "
             "опорный вне полосы: %s", (time.time() - t0) / 60, len(voices), len(chosen),
             sum(not it["band"] for it in chosen), sum(it["close"] < 0.7 for it in chosen),
             sum(it["dur"] > LINE_MAX_S for it in chosen), bad_ref or "нет")


if __name__ == "__main__":
    main()
