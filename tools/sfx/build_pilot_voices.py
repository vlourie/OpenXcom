"""Голоса пилотов на глобусе (тикет XP-000246) -> мод hd: hd/PILOT/<air|ground>/<событие>/<ru|en>_<N>.ogg.

Источник - записанные голоса art/sfx/voicepack/V901 (пилот, летающая техника) и V902 (водитель, наземная),
tools/sfx/gen_pilot_voices.py по docs/research/voice-script-pilots.md; берётся выбранный дубль (chosen) каждой
реплики. Звук - как из рации: полоса 300-3400 Гц, лёгкое сжатие, громкость к общей. Номера в папке события
идут подряд с 1 - движок (HdPilotVoice) перебирает их до первого пропуска.

    py -3.13 tools/sfx/build_pilot_voices.py              # перегнать в art/sfx/pilot_pack/PILOT/
    py -3.13 tools/sfx/build_pilot_voices.py --install    # + в мод hd через манифест (обе копии)
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SRC = ROOT / "art/sfx/voicepack"
OUT = ROOT / "art/sfx/pilot_pack/PILOT"
# XP-000339 (вариант Б, Vitali): голос по полу пилота корабля - V901/V902 женские (air, ground), V903/V904 мужские
# (air_male, ground_male); пилот-собака - лай без речи (dog), одни и те же файлы под ru_N и en_N
KINDS = {"V901": "air", "V902": "ground", "V903": "air_male", "V904": "ground_male"}
DOG = "dog"
NEW_KINDS = ("air_male", "ground_male", DOG)          # слух Vitali ещё впереди: --install требует --approval
EVENTS = ("select", "order", "attack", "escort", "return", "rebase", "wing", "cancel", "damaged", "noammo")
RADIO_BAND = "highpass=f=300,lowpass=f=3400,acompressor=threshold=-20dB:ratio=3:attack=5:release=80"
RADIO = RADIO_BAND + ",loudnorm=I=-18:TP=-2:LRA=7"
# лай: тестовый набор собак (art/sfx/test_set/doge, Stable Audio, tools/sfx/gen_steps_test.py; тот же лай стоит
# в голосовых модах бойцов). Событие -> (папка/промпт, сколько лучших кандидатов по score). Ключи промптов:
# select p1 радостный лай, p2 дружелюбное «гав», p3 любопытное фырканье и лай; move p1 азартное дыхание,
# p2 нетерпеливый тявк; weapon p1 рык, p2 оскал с лаем; annoyed p1 скулёж, p2 ворчание
DOGE = ROOT / "art/sfx/test_set"
DOG_PICKS = {
    "select": (("select/p1", 2), ("select/p2", 2), ("select/p3", 2)),
    "order": (("move/p2", 2), ("move/p1", 1), ("select/p2", 1)),
    "attack": (("weapon/p2", 3), ("weapon/p1", 1)),
    "escort": (("select/p3", 2), ("select/p2", 1)),
    "return": (("move/p1", 2), ("select/p1", 1)),
    "rebase": (("move/p2", 2), ("select/p3", 1)),
    "wing": (("select/p1", 2), ("weapon/p2", 1)),
    "cancel": (("annoyed/p2", 2), ("annoyed/p1", 1)),
    "damaged": (("annoyed/p1", 3), ("weapon/p2", 1)),
    "noammo": (("annoyed/p2", 3), ("annoyed/p1", 1)),
}
PEAK_DB = -6.0                                        # лай короткий: loudnorm на нём врёт, громкость - по пику


def ffmpeg():
    return shutil.which("ffmpeg") or "ffmpeg"


def encode(src, dst, dog=False):
    dst.parent.mkdir(parents=True, exist_ok=True)
    af = RADIO
    if dog:
        # тот же радиоканал без loudnorm; усиление до пика PEAK_DB по volumedetect
        det = subprocess.run([ffmpeg(), "-v", "info", "-i", str(src), "-af", RADIO_BAND + ",volumedetect",
                              "-f", "null", "-"], capture_output=True, text=True, check=True).stderr
        peak = float(det.split("max_volume:")[1].split("dB")[0])
        af = f"{RADIO_BAND},volume={PEAK_DB - peak:.2f}dB,afade=t=in:d=0.004,areverse,afade=t=in:d=0.02,areverse"
    # bitexact: те же входы - те же байты Ogg (R-494)
    subprocess.run([ffmpeg(), "-v", "error", "-y", "-i", str(src), "-af", af,
                    "-ac", "1", "-ar", "22050", "-c:a", "libvorbis", "-q:a", "4",
                    "-fflags", "+bitexact", "-flags:a", "+bitexact", str(dst)], check=True)


def plan_dog():
    """Лай по событиям: [(rel, исходный wav, 'dog', {lang, n, src})]; файл под ru_N и en_N один и тот же."""
    items = json.loads((DOGE / "steps.json").read_text(encoding="utf-8-sig"))["items"]
    out = []
    for ev in EVENTS:
        picked = []
        for key, n in DOG_PICKS[ev]:
            cands = sorted((it for it in items if it["group"] == "doge" and f"{it['dir'].split('/')[1]}/{it['name']}" == key),
                           key=lambda it: it["score"])[:n]
            if len(cands) < n:
                raise SystemExit(f"dog {ev}: у {key} нет {n} кандидатов в {DOGE / 'steps.json'}")
            picked += cands
        for lang in ("ru", "en"):
            for i, it in enumerate(picked, 1):
                out.append((f"PILOT/{DOG}/{ev}/{lang}_{i}.ogg", DOGE / it["file"], DOG,
                            {"lang": lang, "n": i, "src": it["file"], "score": it["score"], "dur": it["dur"]}))
    return out


def plan(only=None):
    out = []
    for vid, kind in KINDS.items():
        if only and kind not in only:
            continue
        st = json.loads((SRC / vid / "voice.json").read_text(encoding="utf-8-sig"))
        if not st.get("asr_done"):
            raise SystemExit(f"{vid}: голос не дописан (asr_done нет) - сначала gen_pilot_voices.py")
        chosen = [ln for ln in st["lines"] if ln.get("chosen")]
        for lang in ("ru", "en"):
            for ev in EVENTS:
                lines = sorted((ln for ln in chosen if ln["lang"] == lang and ln["part"] == ev), key=lambda ln: ln["n"])
                if not lines:
                    raise SystemExit(f"{vid} {lang} {ev}: нет ни одной реплики")
                for i, ln in enumerate(lines, 1):
                    rel = f"PILOT/{kind}/{ev}/{lang}_{i}.ogg"
                    out.append((rel, SRC / ln["file"], vid, ln))
    if not only or DOG in only:
        out += plan_dog()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--install", action="store_true", help="в мод hd через манифест build_hd_pack")
    ap.add_argument("--only", default="",
                    help="через запятую: air, ground, air_male, ground_male, dog - собрать (и поставить) только их; "
                         "остальное в art/sfx/pilot_pack/PILOT не трогается")
    ap.add_argument("--approval", default="",
                    help="слово Vitali для --install мужских голосов и лая (XP-000339): после прослушивания")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    os.chdir(ROOT)
    only = {x.strip() for x in a.only.split(",") if x.strip()}
    bad = only - set(KINDS.values()) - {DOG}
    if bad:
        raise SystemExit(f"--only: неизвестно {sorted(bad)}")
    items = plan(only)
    if a.install and not a.approval and any(it[0].split("/")[1] in NEW_KINDS for it in items):
        raise SystemExit("--install мужских голосов и лая только после прослушивания: --approval \"Vitali ДД.ММ: ...\"")
    if only:
        for kind in only:
            if (OUT / kind).exists():
                shutil.rmtree(OUT / kind)
    elif OUT.exists():
        shutil.rmtree(OUT)
    for rel, src, vid, _ln in items:
        encode(src, OUT.parent / rel, dog=vid == DOG)
    size = sum((OUT.parent / rel).stat().st_size for rel, *_ in items)
    print(f"{len(items)} реплик, {size / 1e6:.1f} МБ -> {OUT}")
    if not a.install:
        return
    sys.path.insert(0, str(ROOT / "tools/hdart"))
    import build_hd_pack as bp
    man = bp.load()
    for rel, src, vid, ln in items:
        new = rel.split("/")[1] in NEW_KINDS
        bp.stage(man, rel, str(OUT.parent / rel), generator="pilot_voices",
                 generator_version="build_pilot_voices.py 22.10 radio q4" if not new else
                 "build_pilot_voices.py 27.10 radio q4 bitexact",
                 source_path=str(src.relative_to(ROOT)).replace("\\", "/"), approved=True,
                 approval=a.approval if new else "Vitali 22.10: «сегодняшние все нужно исправить» - тикет XP-000246",
                 source_frame=f"{vid}:{ln['lang']}:{ln['n']}")
    rels = [rel for rel, *_ in items]
    bp.save(man, why=f"pilot_voices: {len(rels)} реплик пилотов и водителей (XP-000246)")
    print("game:", bp.install(man, "game", only=rels))
    print("repo:", bp.install(man, "repo", only=rels))


if __name__ == "__main__":
    main()
