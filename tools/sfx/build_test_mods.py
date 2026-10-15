"""Собрать тестовые моды звука и страницу прослушивания из art/sfx/test_set/.

Три мода в user/mods установки Пираток (как intro_voice), по умолчанию выключены:
  hd_test_steps      шаги по классу обуви: брони получают moveSound (начало своего банка шагов)
                     и скрипт selectMoveSoundUnit, который на фазах 3 и 7 берёт из банка звук
                     по материалу пола и варианту. Вариант - по номеру юнита и клетке, без
                     генератора боя: механика и сейвы не меняются.
  hd_test_voices_ru  голоса бойцов, русский: voiceSets + voiceSetsMale/Female у типов бойцов,
  hd_test_voices_en  то же по-английски. Типы наборов одинаковые - боец сохраняет голос
                     (voiceSetID в сейве) при смене языкового мода. Включать один из двух.

Звук в моде - OGG Vorbis моно 22050 Гц (частота устройства игры, AUDIO_ROADMAP.md).
Запуск (CPU, ffmpeg из PATH):
    E:/OpenXCom/tools/sfx/.venv-sa3/Scripts/python.exe tools/sfx/build_test_mods.py
"""
import argparse
import html
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_set as T          # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "art/sfx/test_set"
MODS = ROOT / "Пиратки/Dioxine_XPiratez/user/mods"
FIRST = 200                   # свои номера BATTLE.CAT: выше общих звуков ванили, ниже 1000
RATE = 22050
BANK = len(T.MATERIALS) * T.STEP_VARIANTS


def load_json(name):
    with open(SRC / name, encoding="utf-8-sig") as f:
        return json.load(f)


def to_ogg(src, dst, robot=False, gain_db=0.0):
    dst.parent.mkdir(parents=True, exist_ok=True)
    if robot:
        x, sr = sf.read(str(src), dtype="float32", always_2d=True)
        x = robotize(x.mean(axis=1), sr)
        tmp = dst.with_suffix(".robot.wav")
        sf.write(str(tmp), x, sr, subtype="PCM_16")
        src = tmp
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-af", f"volume={gain_db}dB",
                    "-ac", "1", "-ar", str(RATE), "-c:a", "libvorbis", "-q:a", "5", str(dst)],
                   check=True)
    if robot:
        src.unlink()


def robotize(x, sr):
    """Металл: кольцевая модуляция 70 Гц, гребёнка 6 мс с обратной связью, лёгкое огрубление."""
    t = np.arange(len(x)) / sr
    y = x * (0.55 + 0.45 * np.sin(2 * np.pi * 70 * t))
    d = int(sr * 0.006)
    out = y.copy()
    for i in range(d, len(out)):
        out[i] += 0.45 * out[i - d]
    out = np.round(out * 48) / 48
    out = np.concatenate([out, np.zeros(int(sr * 0.05), dtype=out.dtype)])
    return (out / (np.max(np.abs(out)) or 1) * 0.89).astype(np.float32)


def pick(items, key, n):
    """n лучших кандидатов по score (меньше - лучше) в каждой группе key."""
    groups = {}
    for it in items:
        groups.setdefault(key(it), []).append(it)
    return {k: sorted(v, key=lambda it: it["score"])[:n] for k, v in groups.items()}


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8-sig")


def metadata(mod_id, name, desc):
    return (f'name: "{name}"\nversion: 0.1\nauthor: "Vitali + Claude"\n'
            f'description: "{desc}"\nid: {mod_id}\nmaster: piratez\nreservedSpace: 1\n')


STEP_SCRIPT = """\
var int phase;
var int v;
var int x;
var int y;
var int walking;
var int mt;
set phase walking_phase;
unit.isWalking walking;
unit.getMovementType mt;
set sound_index -1;
if eq walking 0;
  if and eq phase 1 eq mt 1;
    set sound_index base_fly_sound_index;
  end;
else lt tile_sound_index 0;
  set sound_index -1;
else lt base_tile_sound_offset 1;
  set sound_index tile_sound_index;
else gt base_tile_sound_offset {mats};
  set sound_index tile_sound_index;
else;
  # variant without battle RNG: unit id, tile and step phase
  unit.getId v;
  unit.getPosition.getX x;
  unit.getPosition.getY y;
  mul x 3;
  mul y 5;
  add v x;
  add v y;
  add v phase;
  offsetmod v 7 0 {var};
  set sound_index base_tile_sound_offset;
  sub sound_index 1;
  mul sound_index {var};
  add sound_index v;
  add sound_index unit_sound_index;
end;
return sound_index;
"""


def build_steps(steps):
    mod = MODS / "hd_test_steps"
    if mod.exists():
        shutil.rmtree(mod)
    best = pick([it for it in steps["items"] if it["group"] == "steps"],
                lambda it: (it["dir"], it["name"]), T.STEP_VARIANTS)
    files, armors = [], []
    idx = FIRST
    for cls, title, _, arm in T.STEP_CLASSES:
        base = idx
        for _, mat, _ in T.MATERIALS:
            cands = best[(f"steps/{cls}", mat)]
            for v in range(T.STEP_VARIANTS):
                it = cands[v % len(cands)]
                rel = f"Resources/Sounds/steps/{cls}/{mat}_{v + 1}.ogg"
                # кандидаты нормированы на пик -3 dB, шаги игры - пик около -8 (census/sounds.tsv)
                to_ogg(SRC / it["file"], mod / rel, gain_db=-5.0)
                files.append((idx, rel))
                it["used"] = True
                idx += 1
        for a in arm:
            armors.append((a, base, cls, title))
    script = STEP_SCRIPT.replace("{mats}", str(len(T.MATERIALS))).replace(
        "{var}", str(T.STEP_VARIANTS))
    lines = ["# Сделано tools/sfx/build_test_mods.py - руками не править", "",
             "extraSounds:", "  - type: BATTLE.CAT", "    files:"]
    lines += [f"      {i}: {r}" for i, r in files]
    lines += ["", "armors:"]
    for a, base, cls, title in armors:
        lines += [f"  - type: {a}   # {title}", f"    moveSound: {base}", "    scripts:",
                  "      selectMoveSoundUnit: |"]
        lines += ["        " + s if s else "" for s in script.splitlines()]
    write(mod / "Ruleset/hd_test_steps.rul", "\n".join(lines) + "\n")
    write(mod / "metadata.yml", metadata(
        "hd_test_steps", "Тест звука: шаги по персонажу",
        "Шаги зависят от обуви: босиком, ботинки, каблуки, тяжёлая броня, лапы догов. "
        "По 4 варианта на материал пола. Механику не меняет."))
    return len(files), len(armors)


def build_voices(lang, voices, steps):
    mod = MODS / f"hd_test_voices_{lang}"
    if mod.exists():
        shutil.rmtree(mod)
    chosen = [it for it in voices["lines"] if it.get("chosen") and it["lang"] == lang]
    files = []
    sets = {}     # имя набора -> {категория: [номера]}
    idx = FIRST
    for it in sorted(chosen, key=lambda it: (it["voice"], T.CATEGORIES.index(it["cat"]), it["line"])):
        rel = f"Resources/Sounds/voices/{it['voice']}/{it['cat']}_{it['line']}.ogg"
        to_ogg(SRC / it["file"], mod / rel, robot=T.VOICES[it["voice"]].get("robot", False))
        files.append((idx, rel))
        sets.setdefault(it["voice"], {}).setdefault(it["cat"], []).append(idx)
        idx += 1
    # доги - звук, а не речь: общий для обоих языков, лучший кандидат каждого промпта
    best = pick([it for it in steps["items"] if it["group"] == "doge"],
                lambda it: (it["dir"], it["name"]), 1)
    for (d, name), cands in sorted(best.items()):
        cat = d.split("/")[1]
        rel = f"Resources/Sounds/voices/doge/{cat}_{name}.ogg"
        to_ogg(SRC / cands[0]["file"], mod / rel)
        files.append((idx, rel))
        sets.setdefault("doge", {}).setdefault(cat, []).append(idx)
        idx += 1

    persona = dict(T.VOICES)
    persona["doge"] = T.DOGE
    lines = ["# Сделано tools/sfx/build_test_mods.py - руками не править", "",
             "enableUnitResponseSounds: true",
             f"unitResponseSoundsFrequency: {T.RESPONSE_FREQUENCY}   # выбор, ход, оружие, отстань",
             "", "extraSounds:", "  - type: BATTLE.CAT", "    files:"]
    lines += [f"      {i}: {r}" for i, r in files]
    lines += ["", "voiceSets:"]
    key = {"select": "selectUnit", "move": "startMoving", "weapon": "selectWeapon",
           "annoyed": "annoyed"}
    for name, cats in sets.items():
        p = persona[name]
        lines += [f"  - type: HD_VOICE_{name.upper()}   # {p['title']}"]
        for cat in T.CATEGORIES:
            if cats.get(cat):
                lines.append(f"    {key[cat]}: {cats[cat]}")
        lines.append(f"    allowedGenders: {p['genders']}")
        lines.append(f"    allowedSoldierTypes: [{', '.join(p['soldiers'])}]")
    # кому какой набор: тип бойца -> мужские и женские наборы
    who = {}
    for name in sets:
        p = persona[name]
        for s in p["soldiers"]:
            for g in p["genders"]:
                who.setdefault(s, {0: [], 1: []})[g].append(f"HD_VOICE_{name.upper()}")
    lines += ["", "soldiers:"]
    for s, g in who.items():
        lines.append(f"  - type: {s}")
        if g[0]:
            lines.append(f"    voiceSetsMale: [{', '.join(g[0])}]")
        if g[1]:
            lines.append(f"    voiceSetsFemale: [{', '.join(g[1])}]")
    write(mod / f"Ruleset/hd_test_voices_{lang}.rul", "\n".join(lines) + "\n")
    title = "русский" if lang == "ru" else "English"
    write(mod / "metadata.yml", metadata(
        f"hd_test_voices_{lang}", f"Тест звука: голоса бойцов ({title})",
        "Реплики при выборе бойца, начале хода, выборе оружия и «отстань»: боцманша, кавайка, "
        "громила, кошкодевочка, киллбот, доги. Включать один язык."))
    return len(files), len(sets)


def listen_page(steps, voices):
    """Страница прослушивания: всё сгенерированное, выбранное в мод - отмечено."""
    rows = []
    rows.append("<h2>Шаги</h2>")
    for cls, title, _, arm in T.STEP_CLASSES:
        rows.append(f"<h3>{html.escape(title)} <small>{html.escape(', '.join(arm))}</small></h3><table>")
        for _, mat, _ in T.MATERIALS:
            cells = [it for it in steps["items"] if it["dir"] == f"steps/{cls}" and it["name"] == mat]
            cells.sort(key=lambda it: it["cand"])
            tds = "".join(
                f'<td class="{"used" if it.get("used") else ""}"><audio controls preload="none" '
                f'src="{it["file"]}"></audio><br>{it["score"]:.2f} · {it["dur"]:.2f} с</td>'
                for it in cells)
            rows.append(f"<tr><th>{mat}</th>{tds}</tr>")
        rows.append("</table>")
    rows.append("<h2>Голоса</h2>")
    rows.append("<h3>Опорные голоса (VoxCPM2 по описанию)</h3><table>")
    for r in voices["refs"]:
        rows.append(f'<tr class="{"used" if r.get("chosen") else ""}"><th>{r["voice"]} {r["take"]}</th>'
                    f'<td><audio controls preload="none" src="{r["file"]}"></audio></td>'
                    f'<td>{html.escape(r.get("heard", ""))}</td></tr>')
    rows.append("</table>")
    for name, v in T.VOICES.items():
        rows.append(f"<h3>{html.escape(v['title'])}</h3><table>")
        for it in voices["lines"]:
            if it["voice"] != name or "file" not in it:
                continue
            rows.append(
                f'<tr class="{"used" if it.get("chosen") else ""}"><th>{it["lang"]} {it["cat"]}</th>'
                f'<td>{html.escape(it["text"])}</td><td><audio controls preload="none" '
                f'src="{it["file"]}"></audio></td><td>{html.escape(it.get("heard", ""))}</td>'
                f'<td>{it["dur"]:.1f} с</td></tr>')
        rows.append("</table>")
    rows.append("<h3>Доги (Stable Audio 3)</h3><table>")
    for it in steps["items"]:
        if it["group"] == "doge":
            rows.append(f'<tr><th>{it["dir"].split("/")[1]} {it["name"]}.{it["cand"]}</th>'
                        f'<td>{html.escape(it["prompt"])}</td><td><audio controls preload="none" '
                        f'src="{it["file"]}"></audio></td><td>{it["score"]:.2f}</td></tr>')
    rows.append("</table>")
    page = ("<!doctype html><meta charset=utf-8><title>Тестовый набор звука</title><style>"
            "body{font:14px sans-serif;margin:16px;background:#1b1b1b;color:#ddd}"
            "td,th{padding:3px 6px;text-align:left;vertical-align:top}"
            ".used{background:#24402a}audio{height:28px;width:220px}small{color:#888}"
            "</style><h1>Тестовый набор звука</h1>"
            "<p>Зелёным - что попало в тестовые моды. Шаги: число - оценка (меньше лучше), "
            "длина. Голоса: справа - что распознал whisper.</p>" + "\n".join(rows))
    write(SRC / "listen.html", page)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="steps или voices")
    a = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    steps = load_json("steps.json")
    voices = load_json("voices.json") if (SRC / "voices.json").exists() else {"refs": [], "lines": []}
    if a.only in ("", "steps"):
        n, k = build_steps(steps)
        print(f"hd_test_steps: {n} звуков шагов, брони: {k}")
    if a.only in ("", "voices") and voices["lines"]:
        for lang in ("ru", "en"):
            n, k = build_voices(lang, voices, steps)
            print(f"hd_test_voices_{lang}: {n} звуков, наборов: {k}")
    listen_page(steps, voices)
    print("страница:", SRC / "listen.html")


if __name__ == "__main__":
    main()
