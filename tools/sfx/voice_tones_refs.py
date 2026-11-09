"""Папка для прослушивания опорных голосов тонов (XP-000541, этап 1): census/tickets/XP-000541/refs/.

По каждому типу бойца: нынешний голос (cur_V###_<реплика>.ogg - одна реплика из мода, кладёт её xp541_cur.py) и опорные
новых тонов (V###_t<N>.ogg: ref.d*.wav голоса из art/sfx/voicepack, ogg 22050 Гц моно, громкость к -12 LUFS как в моде).
refs.tsv: номер, тип, пол, основа, высота (pyin и yin, медиана), F3, ворота gen_voicepack (женские - высота >= 180, F3 >= 2650,
yin >= 175; мужские тона - полоса вокруг цели из voice_tones.tsv; Н - без ворот), безопасная полоса, файл.
Цифрами «голос женский» не утверждается: решает слух Vitali.

Только CPU (ffmpeg, librosa). Интерпретатор VoiceFactory, как у gen_voicepack:
    D:/VoiceFactory/runtime/venv/Scripts/python.exe tools/sfx/voice_tones_refs.py
Повторный запуск безопасен: готовое пересобирается заново, новые голоса подхватываются по voice.json.
"""
import csv
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gen_voicepack as GV                      # noqa: E402
import voice_script                             # noqa: E402
import soundfile as sf                          # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
REFS = ROOT / "census/tickets/XP-000541/refs"
MOD_VOICES = ROOT / "Пиратки/Dioxine_XPiratez/user/mods/hd_voices_ru/Resources/Sounds/voices"
COLS = ["id", "kind", "types", "sex", "base", "tone", "target_hz", "f0_pyin", "f0_yin", "f3", "gate", "safe", "file", "samples"]


def folder(types, sex):
    t = types.split(",")[0]
    return t + "_" + {"М": "M", "Ж": "F"}[sex] if t == "STR_SOLDIER_HYBRID" else t


def measure(wav, sr):
    import librosa
    import numpy as np
    y = np.asarray(wav, dtype=np.float32)
    yin = float(np.median(librosa.yin(y, fmin=60, fmax=500, sr=sr, frame_length=2048)))
    return GV.G.pitch(wav, sr), round(yin, 1), GV.formant3(wav, sr)


def to_ogg(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-af", "loudnorm=I=-12:TP=-2:LRA=11", "-ac", "1",
                    "-ar", "22050", "-c:a", "libvorbis", "-q:a", "5", str(dst)], check=True)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    GV.load_tones()
    voices = {v["id"]: v for v in voice_script.parse(more=voice_script.MORE100)}
    tones = list(csv.DictReader(open(GV.TONE_F0_FILE, encoding="utf-8-sig", newline=""), delimiter="\t"))
    groups = {}                                   # папка -> [основа, ...] в порядке таблицы
    for r in tones:
        f = folder(r["types"], r["sex"])
        if r["base"] not in groups.setdefault(f, []):
            groups[f].append(r["base"])
    base_folder = {b: f for f, bs in groups.items() for b in bs}
    rows = []
    # нынешние голоса: cur_V###_<реплика>.ogg лежат в корне refs (xp541_cur.py) или уже в папке типа
    cur = {}
    sf_path = REFS / "cur_voices_f0.tsv"
    stats = {r["id"]: r for r in csv.DictReader(open(sf_path, encoding="utf-8-sig", newline=""), delimiter="\t")} \
        if sf_path.exists() else {}
    for p in list(REFS.glob("cur_V*.ogg")) + list(REFS.glob("*/cur_V*.ogg")):
        cur[p.name.split("_")[1]] = p
    for b, p in sorted(cur.items()):
        dst = REFS / base_folder[b] / p.name
        if p != dst:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(p), str(dst))
        # высота нынешнего голоса - медиана по всем его репликам из мода (cur_voices_f0.tsv): по одной реплике yin и pyin
        # ошибаются октавой (V002 433, V018 pyin 442, R-509)
        m = stats.get(b)
        t = next(r for r in tones if r["base"] == b)
        rows.append(dict(id=b, kind="нынешний", types=t["types"], sex=voices[b]["reg"], base=b, tone=1, target_hz="",
                         f0_pyin=m["pyin_median"] if m else "", f0_yin=m["yin_median"] if m else "",
                         f3=m["f3_median"] if m else "", gate="- (оригинал)", safe="", file=str(dst.relative_to(REFS)),
                         samples=f"{m['replies']} реплик мода" if m else ""))
    for r in tones:
        v = voices[r["id"]]
        p = GV.OUT / r["id"] / "voice.json"
        row = dict(id=r["id"], kind="опорный", types=r["types"], sex=r["sex"], base=r["base"], tone=r["tone"],
                   target_hz=r["f0"], f0_pyin="", f0_yin="", f3="", gate="не готов", safe="", file="", samples="")
        if p.exists():
            st = json.loads(p.read_text(encoding="utf-8-sig"))
            if st.get("ref"):
                wav, sr = sf.read(str(GV.OUT / st["ref"]), dtype="float32")
                j = GV.judge(v, wav, sr, GV.F3_MIN_REF)
                f0, yin, f3 = measure(wav, sr)
                dst = REFS / folder(r["types"], r["sex"]) / f"{r['id']}_t{r['tone']}.ogg"
                to_ogg(GV.OUT / st["ref"], dst)
                gate = "да" if j["band"] else "нет"
                if v["reg"] == "Н":
                    gate = "- (Н, без ворот)"
                row.update(f0_pyin=f0, f0_yin=yin, f3=f3, gate=gate, safe="да" if GV.safe_ok(v, f0) else "нет",
                           file=str(dst.relative_to(REFS)), samples=f"опорная фраза {len(wav) / sr:.1f} с")
        rows.append(row)
    with open(REFS / "refs.tsv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, COLS, delimiter="\t", lineterminator="\r\n")
        w.writeheader()
        w.writerows(rows)
    ready = sum(r["kind"] == "опорный" and r["file"] != "" for r in rows)
    print(f"refs.tsv: строк {len(rows)}, нынешних {len(cur)}, опорных готово {ready} из {len(tones)}")


if __name__ == "__main__":
    main()
