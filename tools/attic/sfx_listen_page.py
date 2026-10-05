"""Страница прослушивания проб звука (этап 0, docs/AUDIO_ROADMAP.md).

Собирает art/sfx/probe/listen.html из probe.json каждой модели: по заданию три модели
рядом, у каждого файла - огибающая, тишина в начале, пик и громкость. Выбор Vitali страница
пишет в свою базу (коллекция picks, документ на задание), оттуда его читает Claude.

    tools/sfx/.venv/Scripts/python.exe tools/sfx/listen_page.py

Модель не грузит, видеокарта не нужна.
"""
import json
import logging
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

from probe_tasks import REFS, TASKS

log = logging.getLogger("listen_page")

ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "art/sfx/probe"
TEMPLATE = Path(__file__).with_name("listen_template.html")
GAME = ROOT / "Пиратки/Dioxine_XPiratez"
# огибающая по времени, а не по числу столбиков: короткий звук рисуется короче длинного
ENV_MS = 20

# (папка, подпись, лицензия весов)
MODELS = [
    ("mmaudio", "MMAudio large 44k", "веса CC-BY-NC: только некоммерческое"),
    ("stable_audio_open", "Stable Audio Open 1.0", "Stability Community License"),
    ("stable_audio_3_sfx", "Stable Audio 3 Small SFX", "Stability Community License"),
]

RU = {
    "step_metal": "Шаг по металлу",
    "pistol": "Выстрел пистолета",
    "laser_rifle": "Выстрел лазерной винтовки",
    "knife_hit": "Удар ножом",
    "grenade": "Взрыв гранаты",
    "alien_roar": "Рык пришельца",
    "scream_female": "Предсмертный крик женщины",
    "ricochet": "Промах, рикошет",
    "reload": "Перезарядка",
    "door_slide": "Раздвижная дверь",
}


def measure(path):
    x, sr = sf.read(str(path), always_2d=True)
    return measure_mono(x.mean(axis=1), sr, x.shape[1])


def measure_mono(m, sr, ch=1):
    a = np.abs(m)
    peak = float(a.max())
    nz = np.nonzero(a > max(peak, 1e-9) * 0.05)[0]
    step = max(1, sr * ENV_MS // 1000)
    bins = [a[i:i + step] for i in range(0, len(a), step)]
    return {
        "dur": round(len(m) / sr, 2),
        "ch": int(ch),
        "sr": int(sr),
        "peak": round(float(20 * np.log10(peak + 1e-9)), 1),
        "rms": round(float(20 * np.log10(np.sqrt((m.astype(np.float64) ** 2).mean()) + 1e-9)), 1),
        "lead": int(nz[0] / sr * 1000) if len(nz) else -1,
        "env": [round(float(b.max()) if len(b) else 0.0, 3) for b in bins],
    }


def originals(clips):
    """Эталоны из игры (REFS) - читаются так же, как в переписи tools/sound_census.py."""
    sys.path.insert(0, str(ROOT / "tools"))
    import sound_census
    sets = sound_census.load_sets(GAME, GAME / "user/mods/Piratez")
    refs = {}
    for task, items in REFS.items():
        refs[task] = []
        for n, (st, idx, label) in enumerate(items, 1):
            source, x, rate = sets[st][idx]
            web = Path("web/orig") / f"{st.split('.')[0].lower()}_{idx}.ogg"
            (PROBE / web).parent.mkdir(parents=True, exist_ok=True)
            sf.write(str(PROBE / web), x, rate, format="OGG", subtype="VORBIS")
            c = measure_mono(x, rate)
            c.update(file=web.as_posix(), label=label, source=f"{st} {idx}: {source}")
            clips[f"orig/{task}/{n}"] = c
            refs[task].append(n)
    return refs


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    models, clips = [], {}
    refs = originals(clips)
    for folder, title, lic in MODELS:
        d = PROBE / folder
        man = json.loads((d / "probe.json").read_text(encoding="utf-8-sig"))
        gen = sum(r["gen_seconds"] for r in man)
        models.append({"id": folder, "title": title, "license": lic, "files": len(man),
                       "gen": round(gen, 1), "steps": man[0]["steps"], "cfg": man[0]["cfg"]})
        for r in man:
            c = measure(d / r["file"])
            # FLAC страница не раздаёт; OGG Vorbis - и для браузера, и формат игры
            web = Path("web") / folder / Path(r["file"]).with_suffix(".ogg").name
            (PROBE / web).parent.mkdir(parents=True, exist_ok=True)
            x, sr = sf.read(str(d / r["file"]), always_2d=True)
            sf.write(str(PROBE / web), x, sr, format="OGG", subtype="VORBIS")
            c.update(file=web.as_posix(), seed=r["seed"], gen=r["gen_seconds"])
            clips[f"{folder}/{r['task']}/{r['variant']}"] = c
    tasks = [{"id": n, "ru": RU.get(n, n), "dur": dur, "prompt": p, "refs": refs.get(n, [])}
             for n, dur, p in TASKS]
    data = {"models": models, "tasks": tasks, "variants": 3, "clips": clips}
    html = TEMPLATE.read_text(encoding="utf-8-sig").replace(
        "/*DATA*/null", json.dumps(data, ensure_ascii=False))
    out = PROBE / "listen.html"
    # страницу читает браузер, а не PowerShell: спецификация ей не нужна (исключение R-001)
    out.write_text(html, encoding="utf-8")  # НЕ ТРОГАТЬ
    log.info("страница: %s, файлов %d, моделей %d", out, len(clips), len(models))


if __name__ == "__main__":
    main()
