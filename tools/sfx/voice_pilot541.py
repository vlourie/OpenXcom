"""XP-000541: пилот голосов типов бойцов на четырёх голосах (V201 Ламия, V203 Чертовка, V173 раб, V179 герой).

Прошлые опорные Vitali забраковал: педия не учтена, ударений нет, вопросы звучат утверждением, на знаках нет пауз.
Путь пилота:
1. VoxCPM2 (design) - ТОЛЬКО тембр опорного: описание голоса по педии (docs/research/voice-types-pedia.md, карточки
   voice-script-extra.md), текст опорной фразы из xp541_text.tsv; кандидаты оцениваются по высоте/тембру, распознаванию
   и подъёму тона на «?».
2. ESpeech (stress plus): реплики с итоговыми ударениями (колонка ударения_итог); ударения стоят И в тексте реплики,
   И в тексте опорного. Фраза с «?» проверяется на подъём тона последнего слова вопроса; не прошла - дубли ESpeech
   с другим seed, затем VoxCPM2 с инструкцией вопроса (vf/expressive.py); берётся лучший по критерию.
3. Микропаузы: тишина вставляется в готовый звук по словам faster-whisper (vf/pauses.apply, но своя короткая таблица
   PAUSE_TAB); пауза только удлиняется.
4. Обработка на CPU: ламия - усиление и растяжение шипящих + шипящий выдох в конце; Чертовка - понижение высоты,
   подголосок на октаву ниже, перегруз, хрип, металлическое эхо. Варианты «plain» (без обработки) и «proc».
5. ogg 22050 Гц моно, -12 LUFS; pilot.tsv.

С 10.11 критерий вопроса - интонация всей фразы (функция rises, docs/research/voice-types-pedia.md п.5); ниже прежний
критерий пилота 1 (rises_old).
Критерий подъёма на «?» (ПОДЪЁМ, прежний): pyin (60-450 Гц) по озвученным кадрам; база - медиана F0 предыдущей части вопроса
(для однословного вопроса - первые 40% озвученных кадров слова), последнее слово вопроса по временам whisper.
Подъём пройден, если пик F0 последнего слова (медиана по 3 кадрам) выше базы не меньше чем на 3,0 полутона ИЛИ
медиана последних 30% озвученных кадров слова выше базы не меньше чем на 1,0 полутона. Кадры дальше 12 полутонов от
медианы файла считаются ошибкой октавы и отбрасываются.

Только через очередь видеокарты (R-097):
    py -3 tools/gpuq.py add --name voices-xp541-pilot --prio 5 -- D:/VoiceFactory/runtime/venv/Scripts/python.exe -u tools/sfx/voice_pilot541.py
"""
import argparse
import csv
import difflib
import json
import logging
import math
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gen_voices_test as G                      # noqa: E402  (окружение VoiceFactory)
import gen_voicepack as GV                       # noqa: E402  (formant3)
from vf import audio as A                        # noqa: E402
from vf import config as C                       # noqa: E402
from vf import pauses as PZ                      # noqa: E402
from vf import qc as Q                           # noqa: E402
from vf.engines.base import GenParams, VoiceProfile   # noqa: E402
import numpy as np                               # noqa: E402
import soundfile as sf                           # noqa: E402

log = logging.getLogger("voice_pilot541")
ROOT = Path(__file__).resolve().parents[2]
TEXTS = ROOT / "art/sfx/voicepack/xp541_text.tsv"
OUT = ROOT / "census/tickets/XP-000541/pilot"
SR = 24000                                       # рабочая частота; в ogg - 22050
OUT_SR = 22050
LUFS = -12.0

# микропаузы на знаках ВНУТРИ реплики, мс (итоговая длина паузы; пауза только удлиняется)
PAUSE_TAB = {",": 150, ";": 200, ":": 215, "—": 215, "–": 215, ".": 275, "!": 275, "?": 275, "…": 275}
RISE_PEAK_ST, RISE_END_ST = 3.0, 1.0
CLOSE_OK = 0.90                                  # распознанный текст близок к написанному
ESP_TAKES_Q, ESP_TAKES = 6, 3                    # дублей ESpeech: у фразы с «?» / без
VOX_TAKES = 6                                   # дублей VoxCPM2 с инструкцией вопроса
DESIGN_N = 16
SHIFT_MAX = 2.0                                  # опорный вне полосы сдвигается к ней не больше чем на столько полутонов
PROC_LEVELS = [1.0, 0.7, 0.45]                   # сила обработки: следующая, если слова перестали распознаваться
SEED_DESIGN, SEED_VOX = 5410, 5450
TIMBRE_WORD = GV.TIMBRE_WORD                     # «молодая женщина, звонкий высокий женский голос, сопрано...» - рецепт V019

VOICES = {
    "V201": dict(
        name="Ламия", base="V019", sex="Ж", speed=0.92, proc="lamia", lines=["01", "04", "15", "35", "33"],
        f0=(200, 400), f3_min=2550,
        design=TIMBRE_WORD + ". Персонаж: ламия-змееженщина, воительница. "
               "Певучий гибкий голос, спокойное достоинство, ленивая угроза. Свистящие и шипящие «с», «ш», «з», «щ» "
               "произносит протяжно и отчётливо, «с-с-с», мягкий шипящий выдох в конце фраз; слова при этом разборчивы, "
               "темп неторопливый.",
        q_instr="женский певучий голос ламии, вопросительная интонация, подъём тона к концу вопроса, ленивая угроза"),
    "V203": dict(
        name="Чертовка", base="V024", sex="Н", speed=0.92, proc="chort", lines=["01", "09", "11", "28", "04"],
        f0=(150, 330), f3_min=2500,
        design=TIMBRE_WORD + ". Персонаж: Чертовка - девичья душа в теле демона. Голос утробный, "
               "металлический, хриплый, с гортанным злорадным смешком, демонический и нечеловеческий, но речь "
               "разборчива; не мужской рык.",
        q_instr="женский хриплый утробный голос чертовки, вопросительная интонация, подъём тона в конце вопроса, злорадство"),
    "V173": dict(
        name="Раб-солдат", base="V006", sex="М", speed=0.95, proc=None, lines=["01", "02", "03", "20", "04"],
        f0=(115, 245), f3_max=2500,
        design="мужской голос, мужчина, негромкий тенор, голос выше среднего. Персонаж: бывший раб, ставший солдатом, мужчина лет "
               "пятидесяти. Сухой слегка сиплый голос, говорит медленно и устало, короткими фразами, без бравады, "
               "с горькой усмешкой; послушание и закалка, не женский голос.",
        q_instr="мужской сухой усталый голос, вопросительная интонация, подъём тона в конце вопроса, недоверие"),
    "V179": dict(
        name="Герой", base="V007", sex="М", speed=1.0, proc=None, lines=["03", "04", "10", "02", "07"],
        f0=(135, 260), f3_max=2500,
        design="мужской голос, мужчина. Персонаж: герой, мужчина лет тридцати пяти. Бархатный звучный баритон, "
               "самодовольный пафос, интонации как со сцены, с оттенками иронии и усталости; не фальцет.",
        q_instr="мужской бархатный баритон, вопросительная интонация, подъём тона в конце вопроса, ирония"),
}


# ----------------------------------------------------------------------------- тексты
def load_texts():
    """-> ({голос: ударения_итог опорного}, {(голос, n): (текст, ударения_итог)}) из xp541_text.tsv."""
    refs, lines = {}, {}
    with open(TEXTS, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            if r["вид"] == "ref":
                refs[r["голос"]] = r["ударения_итог"]
            elif r["вид"] == "line":
                lines[(r["голос"], r["n"])] = (r["текст"], r["ударения_итог"])
    return refs, lines


def plain(t):
    return t.replace("+", "")


# ----------------------------------------------------------------------------- звук
def to_sr(wav, sr, target=SR):
    wav = np.asarray(wav, dtype=np.float32)
    if sr != target:
        import librosa
        wav = librosa.resample(wav, orig_sr=sr, target_sr=target)
    return wav.astype(np.float32)


def trim(wav):
    return A.trim_silence(np.asarray(wav, dtype=np.float32), SR, threshold_db=-45.0, lead_pad_ms=30, tail_pad_ms=90)


def words_of(path):
    """-> [(слово, начало, конец)] faster-whisper (кэш рядом с файлом)."""
    return PZ.word_times(str(path))


def closeness_words(expected_plain, words):
    return G.closeness(expected_plain, " ".join(w for w, _, _ in words))


def mismatches(expected_plain, words):
    """Слова, которые whisper услышал иначе: 'ожидалось>услышано' (ударения whisper не размечает - сравниваются слова)."""
    a = [w for w, _ in PZ.source_words(expected_plain)]
    b = [w for w, _, _ in words]
    out = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag != "equal":
            out.append("%s>%s" % ("_".join(a[i1:i2]) or "-", "_".join(b[j1:j2]) or "-"))
    return out


def f0_track(wav, sr=SR):
    import librosa
    y = librosa.resample(np.asarray(wav, dtype=np.float32), orig_sr=sr, target_sr=16000) if sr != 16000 else wav
    f0, voiced, _ = librosa.pyin(y, fmin=60, fmax=450, sr=16000, frame_length=1024)
    t = librosa.times_like(f0, sr=16000, hop_length=256)
    ok = voiced & ~np.isnan(f0)
    if ok.sum() >= 5:
        med = np.median(f0[ok])
        ok &= np.abs(12 * np.log2(np.where(ok, f0, med) / med)) <= 12
    return t, np.where(ok, f0, np.nan)


def question_ends(text):
    """[(номер слова-конца вопроса, номер первого слова предложения)] для каждого «?» (текст без «+»)."""
    src = PZ.source_words(text)
    tail = text.rstrip()[-1:]
    marks = [(i, mk) for i, (_, mk) in enumerate(src)]
    if src:
        marks[-1] = (len(src) - 1, tail if tail in ".!?…" else "")
    out, start = [], 0
    for i, mk in marks:
        if mk in (".", "!", "?", "…"):
            if mk == "?":
                out.append((i, start))
            start = i + 1
    return out


def rises_old(wav, text, words, sr=SR):
    """Критерий пилота 1 (только подъём последнего слова): оставлен для пересчёта. По каждому «?» -> ok/peak/end."""
    qs = question_ends(text)
    if not qs:
        return []
    src = PZ.source_words(text)
    m = PZ._align(src, words)
    t, f0 = f0_track(wav, sr)
    res = []
    for i, start in qs:
        if i in m:
            w1 = words[m[i][1]]
        elif words:
            w1 = words[-1]
        else:
            res.append({"ok": False, "peak": 0.0, "end": 0.0, "why": "нет слов"})
            continue
        t0, t1 = w1[1] - 0.03, w1[2] + 0.05
        ts = words[m[start][0]][1] if start in m else 0.0
        last = (t >= t0) & (t <= t1) & ~np.isnan(f0)
        base = (t >= ts) & (t < t0) & ~np.isnan(f0)
        lf = f0[last]
        if base.sum() >= 5:
            bm = float(np.median(f0[base]))
        elif last.sum() >= 8:
            k = max(3, int(last.sum() * 0.4))
            bm = float(np.median(lf[:k]))
            lf = lf[k:]
        else:
            res.append({"ok": False, "peak": 0.0, "end": 0.0, "why": "мало тона"})
            continue
        if len(lf) < 3:
            res.append({"ok": False, "peak": 0.0, "end": 0.0, "why": "мало тона"})
            continue
        sm = np.array([np.median(lf[max(0, k - 1):k + 2]) for k in range(len(lf))])
        peak = 12 * math.log2(float(sm.max()) / bm)
        tailn = max(2, int(len(lf) * 0.3))
        end = 12 * math.log2(float(np.median(lf[-tailn:])) / bm)
        res.append({"ok": bool(peak >= RISE_PEAK_ST or end >= RISE_END_ST), "peak": round(peak, 1),
                    "end": round(end, 1)})
    return res


WH_WORDS = set("кто кого кому кем ком что чего чему чем чём где куда откуда когда как почему зачем отчего сколько "
               "какой какая какое какие какого какому каким каком какую каких какими чей чья чьё чьи чьего чьей "
               "чьим чьих ли".split())
SKIP_FOCUS = set("же бы ли ведь вот то".split())
YN_PEAK_ST, WH_PEAK_ST = 2.0, 2.0          # пик ударного слога над остальной фразой, полутоны
YN_END_TOL, WH_FALL_TOL = 0.5, 1.0         # допуск измерения pyin: конец >= середина-0,5; конец >= начало-1,0
VOWELS = "аеёиоуыэюяАЕЁИОУЫЭЮЯ"


def stress_info(acc, pl):
    """[(слово, номер ударного слога или None, слогов)] по словам PZ._WORD в pl; ударение - «+» перед гласной в acc."""
    stress, pi = [], 0
    for i, ch in enumerate(acc):
        if ch == "+" and i + 1 < len(acc):
            stress.append(pi)
        else:
            pi += 1
    out = []
    for m in PZ._WORD.finditer(pl):
        w = m.group(0)
        sts = [s - m.start() for s in stress if m.start() <= s < m.end()]
        nsyl = sum(c in VOWELS for c in w)
        k = None
        if sts:
            k = sum(c in VOWELS for c in w[:sts[-1]])             # последнее ударение слова (кое-чт+о)
        elif "ё" in w.lower():
            k = sum(c in VOWELS for c in w[:w.lower().index("ё")])
        out.append((w, k, nsyl))
    return out


def _sm(a):
    return np.array([np.median(a[max(0, k - 1):k + 2]) for k in range(len(a))])


def rises(wav, text, words, sr=SR, acc=None):
    """Вопросительная интонация ВСЕЙ фразы (docs/research/voice-types-pedia.md, «Как озвучивать» п.5).
    По каждому «?» -> {'ok','kind':'wh'|'yn','peak','end'}.
    yn (нет вопросительного слова): пик F0 на ударном слоге слова-фокуса (последнее значимое) выше медианы остальной
    фразы >= 2,0 пт И конец фразы (последние 25% озвученных кадров) не ниже медианы фразы (допуск 0,5 пт).
    wh (кто, что, где, ... ли): пик F0 на ударном слоге вопросительного слова выше медианы остальной фразы >= 2,0 пт
    И конец фразы не ниже её начала (первые 25% кадров; допуск 1,0 пт) - нет падения в утвердительный конец.
    Однословная фраза: «остальное» - первые 40% озвученных кадров слова."""
    qs = question_ends(text)
    if not qs:
        return []
    src = PZ.source_words(text)
    st = stress_info(acc if acc else text, text)
    if len(st) != len(src):
        st = [(w, None, 1) for w, _ in src]
    m = PZ._align(src, words)
    t, f0 = f0_track(wav, sr)
    res = []
    for i, start in qs:
        if i not in m or start not in m:
            res.append({"ok": False, "kind": "?", "peak": 0.0, "end": 0.0, "why": "нет слов"})
            continue
        ts, te = words[m[start][0]][1] - 0.03, words[m[i][1]][2] + 0.05
        sel = np.where((t >= ts) & (t <= te) & ~np.isnan(f0))[0]
        wh = [j for j in range(start, i + 1) if src[j][0] in WH_WORDS]
        kind = "wh" if wh else "yn"
        cand = [j for j in range(start, i + 1) if src[j][0] not in SKIP_FOCUS and j in m]
        fj = wh[0] if wh else (cand[-1] if cand else i)
        if len(sel) < 8 or fj not in m:
            res.append({"ok": False, "kind": kind, "peak": 0.0, "end": 0.0, "why": "мало тона"})
            continue
        w0, w1 = words[m[fj][0]][1] - 0.03, words[m[fj][1]][2] + 0.05
        fr = np.where((t >= w0) & (t <= w1) & ~np.isnan(f0))[0]
        if len(fr) < 3:
            res.append({"ok": False, "kind": kind, "peak": 0.0, "end": 0.0, "why": "мало тона в слове"})
            continue
        _, k, nsyl = st[fj]
        win = fr
        if k is not None and nsyl > 1:                 # ударный слог: k-я из nsyl равных долей озвученных кадров слова
            a = int(len(fr) * k / nsyl)
            win = fr[a:max(a + 2, int(len(fr) * (k + 1) / nsyl))]
        frs = set(fr.tolist())
        rest = np.array([x for x in sel if x not in frs])
        if len(rest) >= 5:
            base = float(np.median(f0[rest]))
        else:
            kk = max(3, int(len(fr) * 0.4))
            base = float(np.median(f0[fr[:kk]]))
            win = fr[kk:] if len(fr) - kk >= 3 else fr
        peak = 12 * math.log2(float(_sm(f0[win]).max()) / base)
        allf = f0[sel]
        q = max(3, int(len(allf) * 0.25))
        end_med, start_med, mid = float(np.median(allf[-q:])), float(np.median(allf[:q])), float(np.median(allf))
        if kind == "yn":
            end_rel = 12 * math.log2(end_med / mid)
            ok = peak >= YN_PEAK_ST and end_rel >= -YN_END_TOL
        else:
            end_rel = 12 * math.log2(end_med / start_med)
            ok = peak >= WH_PEAK_ST and end_rel >= -WH_FALL_TOL
        emax = 12 * math.log2(float(_sm(allf[-q:]).max()) / (mid if kind == "yn" else start_med))
        res.append({"ok": bool(ok), "kind": kind, "peak": round(peak, 1), "end": round(end_rel, 1),
                    "emax": round(emax, 1)})
    return res


def lufs_of(y, sr):
    import pyloudnorm as pyln
    y = y.astype(np.float64)
    if len(y) and len(y) < int(0.5 * sr):
        # реплика короче блока 400 мс («Хм.»): меряем повтором, громкость та же
        y = np.tile(y, int(0.5 * sr) // len(y) + 1)
    return float(pyln.Meter(sr).integrated_loudness(y))


def soft_limit(y, knee=0.7, top=0.95):
    a = np.abs(y)
    over = a > knee
    out = y.copy()
    out[over] = np.sign(y[over]) * (knee + (top - knee) * np.tanh((a[over] - knee) / (top - knee)))
    return out.astype(np.float32)


def finalize(y):
    """24000 -> 22050, -12 LUFS (подтяжка пересчётом с мягким ограничением пиков) -> (wav, LUFS)."""
    y = to_sr(y, SR, OUT_SR)
    for _ in range(4):
        cur = lufs_of(y, OUT_SR)
        if not math.isfinite(cur):
            break
        y = soft_limit(y * 10 ** ((LUFS - cur) / 20.0))
        if abs(lufs_of(y, OUT_SR) - LUFS) < 0.4:
            break
    return y, lufs_of(y, OUT_SR)


def write_ogg(path, y):
    sf.write(str(path), y, OUT_SR, format="OGG", subtype="VORBIS")


# ----------------------------------------------------------------------------- обработка ламии
def _fric_runs(y, sr, min_frames=4):
    from scipy.signal import butter, sosfiltfilt
    hop = int(sr * 0.01)
    n = len(y) // hop
    hp = sosfiltfilt(butter(4, 3500 / (sr / 2), "high", output="sos"), y)
    fr, fh = y[:n * hop].reshape(n, hop), hp[:n * hop].reshape(n, hop)
    e, eh = (fr ** 2).mean(1), (fh ** 2).mean(1)
    lim = (float(np.max(np.abs(y))) * 10 ** (-38 / 20)) ** 2
    zc = (np.signbit(fr[:, 1:]) != np.signbit(fr[:, :-1])).mean(1)
    flag = (e > lim) & (eh / (e + 1e-12) > 0.4) & (zc > 0.12)
    runs, s = [], None
    for k, f in enumerate(list(flag) + [False]):
        if f and s is None:
            s = k
        elif not f and s is not None:
            if k - s >= min_frames:
                runs.append((s * hop, k * hop))
            s = None
    return runs


def _xcat(parts, xf):
    out = parts[0].astype(np.float32)
    for p in parts[1:]:
        k = min(xf, len(out), len(p))
        if k <= 0:
            out = np.concatenate([out, p])
            continue
        w = np.linspace(0, 1, k, dtype=np.float32)
        mix = out[-k:] * np.cos(w * np.pi / 2) + p[:k] * np.sin(w * np.pi / 2)
        out = np.concatenate([out[:-k], mix, p[k:]])
    return out.astype(np.float32)


def lamia(y, lv=1.0, sr=SR):
    """Шипение: растянуть шумовые отрезки шипящих (+70%, не больше 160 мс), усилить 4-10 кГц на них, шипящий выдох в конце.
    lv - сила обработки (1.0 полная; ниже, если разборчивость упала). -> (wav, сведения)."""
    from scipy.signal import butter, sosfiltfilt
    xf = int(sr * 0.012)
    y0, stretched, added = y, 0, 0
    for a, b in reversed(_fric_runs(y, sr)):
        seg = y[a:b]
        length = len(seg)
        mid = seg[length // 5: length - length // 5]
        extra = int(min(0.7 * lv * length, 0.16 * lv * sr))
        if len(mid) < 3 * xf or extra < xf:
            continue
        c = length // 2
        reps = int(math.ceil(extra / (len(mid) - xf)))
        y = np.concatenate([y[:a], _xcat([seg[:c]] + [mid] * reps + [seg[c:]], xf), y[b:]])
        stretched += 1
    added = int(round((len(y) - len(y0)) / sr * 1000))
    runs = _fric_runs(y, sr)
    env = np.zeros(len(y), np.float32)
    for a, b in runs:
        env[a:b] = 1.0
    k = int(sr * 0.015)
    env = np.convolve(env, np.ones(k, np.float32) / k, mode="same")
    bp = sosfiltfilt(butter(4, [4000 / (sr / 2), 10000 / (sr / 2)], "bandpass", output="sos"), y)
    y = y + 1.4 * lv * env * bp
    # шипящий выдох: 230 мс шума 4-9 кГц, спад по экспоненте, -19 дБ от речи
    rng = np.random.default_rng(541)
    n = int(sr * 0.23)
    noise = sosfiltfilt(butter(4, [4000 / (sr / 2), 9000 / (sr / 2)], "bandpass", output="sos"),
                        rng.standard_normal(n).astype(np.float32))
    t = np.arange(n) / sr
    noise *= np.exp(-t / 0.09) * np.minimum(1.0, t / 0.015)
    rms = float(np.sqrt(np.mean(y ** 2)))
    noise *= rms * 10 ** (-19 / 20) / (float(np.sqrt(np.mean(noise ** 2))) + 1e-9) * 2.2 * lv
    s0 = max(0, len(y) - int(sr * 0.03))
    out = np.concatenate([y, np.zeros(max(0, s0 + n - len(y)), np.float32)])
    out[s0:s0 + n] += noise

    def hf_db(sig):
        sp = np.abs(np.fft.rfft(sig)) ** 2
        fr = np.fft.rfftfreq(len(sig), 1.0 / sr)
        return 10 * math.log10(sp[(fr >= 4000) & (fr <= 10000)].sum() / sp.sum() + 1e-12)
    info = "ламия lv=%.2f: растянуто %d отрезков шипящих (+%d мс), доля 4-10 кГц %+.1f дБ, выдох 230 мс" % (
        lv, stretched, added, hf_db(out) - hf_db(y0))
    return out.astype(np.float32), info


# ----------------------------------------------------------------------------- обработка Чертовки
def chort(y, lv=1.0, sr=SR):
    """Демон поверх женской основы: -3 пт, подголосок -12 пт, нижний бас, перегруз, хрип 68 Гц, металл и эхо.
    lv - сила обработки (1.0 полная; ниже, если разборчивость упала). -> (wav, сведения)."""
    import librosa
    from scipy.signal import butter, sosfiltfilt
    y = y.astype(np.float32)
    dn = librosa.effects.pitch_shift(y, sr=sr, n_steps=-3.0 * lv)
    sub = librosa.effects.pitch_shift(dn, sr=sr, n_steps=-12.0)
    sub = sosfiltfilt(butter(4, 500 / (sr / 2), "low", output="sos"), sub)
    x = dn + 0.30 * lv * sub
    x = x + 0.6 * lv * sosfiltfilt(butter(2, 250 / (sr / 2), "low", output="sos"), x)
    pk = float(np.max(np.abs(x))) + 1e-9
    # перегруз мягкий: замер на CPU (whisper) - при 0.38 и tanh(5x) слова рассыпались (0,74), без него 1,0
    x = (1 - 0.12 * lv) * x + 0.12 * lv * np.tanh(3.0 * x / pk) * pk
    t = np.arange(len(x)) / sr
    x = x * (1.0 - 0.27 * lv * (0.5 + 0.5 * np.sin(2 * np.pi * 68.0 * t))).astype(np.float32)

    def delayed(sig, sec, g):
        d = int(sec * sr)
        out = np.zeros(len(sig), np.float32)
        out[d:] = sig[:len(sig) - d] * g
        return out
    x = x + delayed(x, 0.0071, 0.42 * lv) + delayed(x, 0.0123, 0.28 * lv)
    tail = int(sr * 0.30)
    x = np.concatenate([x, np.zeros(tail, np.float32)])
    echo = sosfiltfilt(butter(4, [800 / (sr / 2), 4500 / (sr / 2)], "bandpass", output="sos"), x)
    x = x + delayed(echo, 0.11, 0.30 * lv) + delayed(echo, 0.23, 0.14 * lv)
    return x.astype(np.float32), ("чертовка lv=%.2f: высота %.1f пт, подголосок -12 пт %.2f, перегруз %.2f, хрип 68 Гц %.2f, "
                                  "металл 7/12 мс, эхо 110/230 мс" % (lv, -3.0 * lv, 0.30 * lv, 0.12 * lv, 0.27 * lv))


PROC = {"lamia": lamia, "chort": chort}


# ----------------------------------------------------------------------------- пилот
class Pilot:
    def __init__(self, cfg):
        local = G.VF + "/models/openbmb/VoxCPM2"
        self.vox = G.engine(cfg, "voxcpm2", local_dir=local if Path(local).is_dir() else "")
        self.esp = G.engine(cfg, "espeech")
        self.refs, self.lines = load_texts()

    # --- опорный (VoxCPM2 design)
    def design(self, vid, cfgv, work):
        ref_acc = self.refs[vid]
        ref_pl = plain(ref_acc)
        cands = []
        for k in range(DESIGN_N):
            p = GenParams(instruction=cfgv["design"] + " Вопросительные фразы произносит с заметным подъёмом тона в конце вопроса.",
                          seed=SEED_DESIGN + 100 * int(vid[1:]) % 997 + k, cfg_value=2.0,
                          inference_timesteps=10)
            wav, sr, _ = self.vox.generate(ref_pl, None, p)
            wav = trim(to_sr(wav, sr))
            path = work / ("ref.d%d.wav" % (k + 1))
            sf.write(str(path), wav, SR, subtype="PCM_16")
            cands.append({"k": k + 1, "path": path, "wav": wav, "dur": len(wav) / SR})
        for c in cands:
            c["words"] = words_of(c["path"])
            c["close"] = closeness_words(ref_pl, c["words"])
            c["f0"] = G.pitch(c["wav"], SR)
            c["f3"] = GV.formant3(c["wav"], SR)
            c["q"] = rises(c["wav"], ref_pl, c["words"], acc=ref_acc)
            lo, hi = cfgv["f0"]
            gate = lo <= c["f0"] <= hi
            if "f3_min" in cfgv:
                gate = gate and c["f3"] >= cfgv["f3_min"]
            if "f3_max" in cfgv:
                gate = gate and 0 < c["f3"] <= cfgv["f3_max"]
            c["gate"] = gate
            tgt = math.sqrt(lo * hi)
            c["margin"] = -abs(12 * math.log2(max(c["f0"], 1) / tgt))
            c["key"] = (3.0 <= c["dur"] <= 11.5, gate, c["close"] >= 0.9, sum(r["ok"] for r in c["q"]),
                        round(c["margin"], 1), c["close"])
            log.info("%s опорный d%d: %.1f с, F0 %.0f, F3 %.0f, ворота %s, близость %.2f, подъём %s", vid, c["k"],
                     c["dur"], c["f0"], c["f3"], gate, c["close"], [r["ok"] for r in c["q"]])
        best = max(cands, key=lambda c: c["key"])
        log.info("%s опорный: кандидат d%d", vid, best["k"])
        lo, hi = cfgv["f0"]
        if best["f0"] > 0 and not lo <= best["f0"] <= hi:        # вне полосы: сдвиг к ней, не больше SHIFT_MAX
            import librosa
            tgt = lo if best["f0"] < lo else hi
            steps = float(np.clip(12 * math.log2(tgt / best["f0"]), -SHIFT_MAX, SHIFT_MAX))
            best["wav"] = librosa.effects.pitch_shift(best["wav"], sr=SR, n_steps=steps).astype(np.float32)
            best["shift"] = round(steps, 2)
            best["f0"] = G.pitch(best["wav"], SR)
            log.info("%s опорный сдвинут на %+.2f пт, F0 теперь %.0f", vid, steps, best["f0"])
        return best

    # --- реплики
    def esp_take(self, prof, text_acc, seed, speed):
        p = GenParams(style="neutral", seed=seed, cfg_value=2.0, speed=speed)
        wav, sr, _ = self.esp.generate(text_acc, prof, p)
        return trim(to_sr(wav, sr))

    def vox_take(self, prof, text_pl, seed, instr):
        p = GenParams(instruction=instr, seed=seed, cfg_value=2.0, inference_timesteps=10, style="neutral",
                      extra={"force_controllable": True})
        wav, sr, _ = self.vox.generate(text_pl, prof, p)
        return trim(to_sr(wav, sr))

    def line(self, vid, cfgv, n, ref_pf, vprof, eprof, work):
        text, acc = self.lines[(cfgv["base"], n)]
        pl = plain(acc)
        nq = len(question_ends(pl))
        takes = []

        def add(tag, wav):
            path = work / ("%s.%s.wav" % (n, tag))
            sf.write(str(path), wav, SR, subtype="PCM_16")
            words = words_of(path)
            c = {"tag": tag, "wav": wav, "path": path, "words": words, "close": closeness_words(pl, words),
                 "q": rises(wav, pl, words, acc=acc)}
            c["npass"] = sum(r["ok"] for r in c["q"])
            c["key"] = (c["close"] >= CLOSE_OK, c["npass"], tag.startswith("esp"),
                        sum(min(r["peak"], 8.0) for r in c["q"]), c["close"])
            takes.append(c)
            log.info("%s %s %s: близость %.2f, подъём %s", vid, n, tag, c["close"],
                     ["%s%+.1f/%+.1f" % ("да" if r["ok"] else "нет", r["peak"], r["end"]) for r in c["q"]])
            return c

        def good(c):
            return c["close"] >= CLOSE_OK and c["npass"] == nq

        for s in range(1, (ESP_TAKES_Q if nq else ESP_TAKES) + 1):
            add("esp%d" % s, self.esp_take(eprof, acc, s, cfgv["speed"]))
            if good(takes[-1]):
                break
        first_ok = good(takes[0])
        first_pass = takes[0]["npass"]
        if nq and not any(good(c) for c in takes):
            for s in range(1, VOX_TAKES + 1):
                add("vox%d" % s, self.vox_take(vprof, pl, SEED_VOX + s, cfgv["q_instr"]))
                if good(takes[-1]):
                    break
        best = max(takes, key=lambda c: c["key"])
        return dict(n=n, text=text, acc=acc, pl=pl, nq=nq, best=best, takes=takes, first_ok=first_ok,
                    first_pass=first_pass)

    # --- вывод варианта
    def emit(self, vid, cfgv, kind, n, acc, pl, wav, engine_tag, variant, outdir, work, extra):
        """Паузы -> (обработка) -> ogg; строка pilot.tsv."""
        words = extra["words"]
        pw, ins = PZ.apply(wav, SR, pl, words, pauses=PAUSE_TAB)
        added = int(round((len(pw) - len(wav)) / SR * 1000))
        base = ("ref" if kind == "ref" else n) + "." + variant
        chk = work / (base + ".final.wav")
        plain_close = closeness_words(pl, words)
        info = "-"
        levels = PROC_LEVELS if variant == "proc" else [None]
        for li, lv in enumerate(levels):
            if lv is None:
                y, lufs = finalize(pw)
            else:
                pr, info = PROC[cfgv["proc"]](pw, lv)
                y, lufs = finalize(pr)
            sf.write(str(chk), y, OUT_SR, subtype="PCM_16")
            if chk.with_name(chk.name + ".words.json").exists():
                chk.with_name(chk.name + ".words.json").unlink()
            fw = PZ.word_times(str(chk))
            # обработка не должна съедать слова: разборчивость не ниже варианта без обработки минус 0,08
            if lv is None or closeness_words(pl, fw) >= max(0.8, plain_close - 0.08) or li == len(levels) - 1:
                break
        write_ogg(outdir / (base + ".ogg"), y)
        q = extra["q"]                         # подъём мерится на сыром дубле: паузы и обработка тон не меняют
        qtxt = "; ".join("%s %+.1f/%+.1f" % ("да" if r["ok"] else "нет", r["peak"], r["end"]) for r in q) or "-"
        return {"голос": vid, "вид": kind, "n": n, "текст_с_ударениями": acc, "вариант": variant,
                "движок": engine_tag, "f0_ср_Гц": G.pitch(y, OUT_SR), "вопросов": len(q),
                "подъём_да_нет(пик/конец,пт)": qtxt, "вопросов_прошло": sum(r["ok"] for r in q),
                "паузы_вставлено_мс": "%d (%d мест)" % (added, ins), "обработка": info, "LUFS": round(lufs, 1),
                "whisper": " ".join(w for w, _, _ in fw), "похожесть": round(closeness_words(pl, fw), 2),
                "расхождения": " ".join(mismatches(pl, fw)), "файл": str((outdir / (base + ".ogg")).relative_to(ROOT))
                .replace("\\", "/")}

    def voice(self, vid):
        cfgv = VOICES[vid]
        outdir = OUT / vid
        work = outdir / "_work"
        work.mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        best = self.design(vid, cfgv, work)
        ref_acc = self.refs[vid]
        ref_pf = work / "ref.chosen.wav"
        sf.write(str(ref_pf), best["wav"], SR, subtype="PCM_16")
        # ударения нужны и в тексте референса: плюсы остаются в text, движки без ударений их не получают
        eprof = VoiceProfile(vid, "espeech", {"neutral": [{"wav": str(ref_pf), "text": ref_acc}]})
        vprof = VoiceProfile(vid, "voxcpm2", {"neutral": [{"wav": str(ref_pf), "text": plain(ref_acc)}]})
        variants = ["plain"] + (["proc"] if cfgv["proc"] else [])
        rows = []
        for var in variants:
            rows.append(self.emit(vid, cfgv, "ref", "", ref_acc, plain(ref_acc), best["wav"], "voxcpm2-design d%d" % best["k"],
                                  var, outdir, work, {"path": best["path"], "q": best["q"], "words": best["words"]}))
        stats = {"q_total": 0, "q_first": 0, "q_final": 0, "lines": []}
        for n in cfgv["lines"]:
            r = self.line(vid, cfgv, n, ref_pf, vprof, eprof, work)
            b = r["best"]
            stats["q_total"] += r["nq"]
            stats["q_first"] += r["first_pass"]
            stats["q_final"] += b["npass"]
            for var in variants:
                rows.append(self.emit(vid, cfgv, "line", n, r["acc"], r["pl"], b["wav"], "%s (дублей %d)" % (b["tag"], len(r["takes"])),
                                      var, outdir, work, b))
            stats["lines"].append({"n": n, "nq": r["nq"], "first": r["first_pass"], "final": b["npass"],
                                   "takes": [t["tag"] for t in r["takes"]], "chosen": b["tag"]})
        (outdir / "stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8-sig")
        (outdir / "rows.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8-sig")
        log.info("%s готов за %.0f с: вопросов %d, с первого дубля %d, после дублей %d", vid, time.time() - t0,
                 stats["q_total"], stats["q_first"], stats["q_final"])
        return rows


def write_tsv():
    rows = []
    for vid in VOICES:
        p = OUT / vid / "rows.json"
        if p.exists():
            rows += json.loads(p.read_text(encoding="utf-8-sig"))
    if not rows:
        return
    cols = list(rows[0].keys())
    with open(OUT / "pilot.tsv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter="\t")
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--voices", default=",".join(VOICES))
    a = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    OUT.mkdir(parents=True, exist_ok=True)
    cfg = C.load(G.VF)
    pilot = Pilot(cfg)
    for vid in [v for v in a.voices.split(",") if v]:
        try:
            pilot.voice(vid)
        except Exception:
            log.exception("%s: сбой", vid)
        write_tsv()
    Q.free_asr()
    write_tsv()
    log.info("pilot.tsv: %s", OUT / "pilot.tsv")


if __name__ == "__main__":
    main()
