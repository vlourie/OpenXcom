"""Собрать игровые моды голосов по сценарию записи: hd_voices_ru и hd_voices_en.

Источник - art/sfx/voicepack/ (gen_voicepack.py), раскладка - tools/sfx/voicepack_map.tsv,
события реплик - tools/sfx/voicepack_events.tsv (docs/research/voicepack-mapping.md).
Моды кладутся в user/mods установки Пираток. Включать один язык: типы наборов одинаковые
(VP_V001 ...), боец сохраняет голос в сейве при смене языкового мода.

  бойцы      тип бойца -> voiceSetsMale/Female (голос на оба пола; лупоглаз раздельно);
             набор VP_V### с allowedSoldierTypes - виден на базе в «Голос бойца» только своему типу
  национальные  наборы VP_V### без голоса по умолчанию: ручной выбор на базе, фильтр по типу и полу
  враги      units -> voiceSets [VPU_V###] с allowedUnitTypes (звучит под контролем игрока, на базе не виден)
  доги       лай из тестового набора (art/sfx/test_set)

События движка 4: выбор, ход, оружие, «отстань»; «после убийства» и «под огнём» в мод не идут.
Голоса из --hold (на починке) в мод не идут, их типы остаются без голоса.
Запуск (CPU, ffmpeg из PATH):
    E:/OpenXCom/tools/sfx/.venv-sa3/Scripts/python.exe tools/sfx/build_voicepack_mods.py
"""
import argparse
import csv
import json
import math
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_test_mods as B   # noqa: E402  to_ogg, robotize, pick, write
import voice_script

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "art/sfx/voicepack"
HERE = Path(__file__).resolve().parent
FIRST = 200                   # выше общих звуков; reservedSpace растёт по числу файлов
RESERVED = 2                  # минимальный резерв (фактический вычисляется ниже)
FREQUENCY = [60, 20, 40, 20]  # выбор, ход, оружие, «отстань» - проценты
EVENTS = {"select": "selectUnit", "move": "startMoving", "weapon": "selectWeapon", "annoyed": "annoyed"}
ROBOT = {"V025", "V026", "V027", "V029"}
# 17.10: подключить проверенные реплики всех записанных голосов.
HOLD = ""
GENDER = {"М": [0], "Ж": [1], "оба": [0, 1]}
# 16.10 Vitali: «голоса ОЧЕНЬ тихие». Реплики были -18 LUFS (rms -18.6), звуки боя Пираток - rms -13.5 с пиком
# под 0 (census/sounds.tsv), а канал голосов не громче файла. Два прохода: замер громкости, потом усиление
# к -12 LUFS и лимитер на -1 dB (однопроходный loudnorm упирался в пик: выходило от -13 до -19)
TARGET_LUFS = -12.0


def loudness(path):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af",
                        "loudnorm=print_format=json", "-f", "null", "-"], capture_output=True, text=True, check=True)
    m = re.search(r'"input_i"\s*:\s*"(-?[\d.]+|-inf)"', r.stderr)
    return float(m.group(1)) if m and m.group(1) != "-inf" else None


def loud_ogg(src, dst, robot=False):
    tmp = dst.with_suffix(".tmp.wav")
    dst.parent.mkdir(parents=True, exist_ok=True)
    x, sr = sf.read(str(src), dtype="float32", always_2d=True)
    x = x.mean(axis=1)
    sf.write(str(tmp), B.robotize(x, sr) if robot else x, sr, subtype="PCM_16")
    # короче 0.6 с громкость по стандарту не меряется (ворота 400 мс) - тогда пик к -2 dB;
    # лимитер на -2 dB: Vorbis при сжатии добавляет к пику около 1 dB
    i = loudness(tmp) if len(x) >= 0.6 * sr else None
    if i is None or i < -60:
        peak = float(abs(x).max()) or 1.0
        gain = -2.0 - 20 * math.log10(peak)
    else:
        gain = TARGET_LUFS - i
    ceiling = 0.794
    for attempt in range(4):
        B.to_ogg(tmp, dst, af=f"volume={min(18.0, gain):.2f}dB,alimiter=limit={ceiling:.6f}:attack=3:release=50:level=disabled")
        decoded, _ = sf.read(str(dst), dtype="float32")
        peak = float(abs(decoded).max())
        if peak <= 0.98:
            break
        ceiling *= 0.95 / peak
        gain -= max(0.0, 20 * math.log10(peak / 0.95))
    else:
        raise ValueError(f"Vorbis peak remains too high: {dst}")
    tmp.unlink()


def read_tsv(name):
    with open(HERE / name, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def q(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def build(lang, hold, events, rows, states, doge_steps, rejected):
    mod = B.MODS / f"hd_voices_{lang}"
    # rmtree не должен уйти через junction или за пределы двух наших модов.
    if mod.is_symlink() or mod.resolve().parent != B.MODS.resolve():
        raise ValueError(f"unsafe mod path: {mod}")
    if mod.exists():
        shutil.rmtree(mod)
    used = sorted({r["voice"] for r in rows} - hold)
    files, sets = [], {}          # sets: голос -> событие -> [номера]
    idx = FIRST
    jobs = []
    for vid in used:
        chosen = {it["n"]: it for it in states[vid]["lines"] if it.get("chosen") and it["lang"] == lang}
        for ev in events.get(vid, []):
            if ev["event"] not in EVENTS:
                continue
            if ev["line"] not in chosen:
                if (vid, ev['line'], lang) in rejected:
                    continue
                raise ValueError(f"missing unaudited line: {vid}/{lang}/{ev['line']}")
            rel = f"Resources/Sounds/voices/{vid}/{ev['line']}.ogg"
            jobs.append((SRC / chosen[ev["line"]]["file"], mod / rel, vid in ROBOT))
            files.append((idx, rel))
            sets.setdefault(vid, {}).setdefault(ev["event"], []).append(idx)
            idx += 1
    best = B.pick([it for it in doge_steps["items"] if it["group"] == "doge"],
                  lambda it: (it["dir"], it["name"]), 1)
    for (d, name), cands in sorted(best.items()):
        cat = d.split("/")[1]
        rel = f"Resources/Sounds/voices/doge/{cat}_{name}.ogg"
        jobs.append((B.SRC / cands[0]["file"], mod / rel, False))
        files.append((idx, rel))
        sets.setdefault("doge", {}).setdefault(cat, []).append(idx)
        idx += 1
    reserved = max(RESERVED, math.ceil(idx / 1000))
    for vid in used:
        for event in EVENTS:
            if not sets.get(vid, {}).get(event):
                raise ValueError(f"empty event after audit: {vid}/{event}")
    def encode(job):
        loud_ogg(job[0], job[1], robot=job[2])
    with ThreadPoolExecutor(max_workers=4) as pool:
        for _ in pool.map(encode, jobs):
            pass

    # кто чем звучит
    soldier, choice, unit = {}, {}, {}
    for r in rows:
        if r["voice"] not in sets:
            continue
        if r["kind"] == "soldier":
            for g in GENDER[r["gender"]]:
                soldier.setdefault(r["target"], {0: [], 1: []})[g].append(r["voice"])
            choice.setdefault(r["voice"], {"types": set(), "genders": set()})
            choice[r["voice"]]["types"].add(r["target"])
            choice[r["voice"]]["genders"].update(GENDER[r["gender"]])
        elif r["kind"] == "choice":
            choice.setdefault(r["voice"], {"types": set(), "genders": set()})
            choice[r["voice"]]["types"].add(r["target"])
            choice[r["voice"]]["genders"].update(GENDER[r["gender"]])
        elif r["kind"] == "unit":
            unit.setdefault(r["voice"], set()).add(r["target"])
    for s in ("STR_SOLDIER_DOGE", "STR_SOLDIER_BLOODOGE"):
        soldier[s] = {0: ["doge"], 1: ["doge"]}
    choice["doge"] = {"types": {"STR_SOLDIER_DOGE", "STR_SOLDIER_BLOODOGE"}, "genders": {0, 1}}

    def name(vid):
        return "VP_DOGE" if vid == "doge" else f"VP_{vid}"

    def body(vid):
        return [f"    {EVENTS[e]}: {sets[vid][e]}" for e in EVENTS if sets[vid].get(e)]

    L = ["# Сделано tools/sfx/build_voicepack_mods.py - руками не править", "",
         "enableUnitResponseSounds: true",
         f"unitResponseSoundsFrequency: {FREQUENCY}   # выбор, ход, оружие, отстань", "",
         "extraSounds:", "  - type: BATTLE.CAT", "    files:"]
    L += [f"      {i}: {r}" for i, r in files]
    L += ["", "voiceSets:"]
    for vid, c in sorted(choice.items()):
        L += [f"  - type: {name(vid)}"] + body(vid)
        L += [f"    allowedGenders: {sorted(c['genders'])}",
              f"    allowedSoldierTypes: [{', '.join(sorted(c['types']))}]"]
    for vid, us in sorted(unit.items()):
        L += [f"  - type: VPU_{vid}"] + body(vid)
        L += [f"    allowedUnitTypes: [{', '.join(sorted(us))}]"]
    L += ["", "soldiers:"]
    for s, g in sorted(soldier.items()):
        L.append(f"  - type: {s}")
        if g[0]:
            L.append(f"    voiceSetsMale: [{', '.join(name(v) for v in g[0])}]")
        if g[1]:
            L.append(f"    voiceSetsFemale: [{', '.join(name(v) for v in g[1])}]")
    L += ["", "units:"]
    for u, vs in sorted((u, sorted(v for v, us in unit.items() if u in us)) for u in
                        {u for us in unit.values() for u in us}):
        L += [f"  - type: {u}", f"    voiceSets: [{', '.join('VPU_' + v for v in vs)}]"]
    # имена наборов в списке «Голос бойца»
    L += ["", "extraStrings:"]
    for code in ("ru", "en-US", "en-GB"):
        L += [f"  - type: {code}", "    strings:"]
        for vid in sorted(choice):
            if vid == "doge":
                label = "Пёс: лай" if code == "ru" else "Dog: barks"
            else:
                label = states[vid]["name"] if code == "ru" else f"{vid} " + states[vid].get("for_en", vid)
            L.append(f"      {name(vid)}: {q(label)}")
    B.write(mod / f"Ruleset/hd_voices_{lang}.rul", "\n".join(L) + "\n")
    title = "русский" if lang == "ru" else "English"
    B.write(mod / "metadata.yml", (
        f'name: "HD: голоса бойцов ({title})"\nversion: 1.1\nauthor: "Vitali + Claude"\n'
        f'description: "Голоса по сценарию записи: реплики на выбор бойца, ход, оружие и «отстань» '
        f'для команды, национальные голоса (выбор на базе), враги под контролем. Включать один язык."\n'
        f"id: hd_voices_{lang}\nmaster: piratez\nreservedSpace: {reserved}\n"))
    return len(files), len(sets), len(soldier), len(unit), sum(len(us) for us in unit.values())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hold", default=HOLD, help="голоса, которые не брать (через пробел или запятую)")
    ap.add_argument("--lang", default="ru,en")
    a = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    hold = set(a.hold.replace(",", " ").split())
    events = {}
    for r in read_tsv("voicepack_events.tsv"):
        events.setdefault(r["voice"], []).append(r)
    rows = read_tsv("voicepack_map.tsv")
    states = {}
    for p in sorted(SRC.glob("V*/voice.json")):
        with open(p, encoding="utf-8-sig") as f:
            states[p.parent.name] = json.load(f)
    # Все варианты прочитаны CPU-аудитором. Отбор не меняет исходный manifest генератора.
    audit = json.loads((SRC / 'audit.json').read_text(encoding='utf-8-sig'))
    if audit['missing']:
        raise ValueError('audit has missing lines')
    selected = {(r['voice'], r['lang'], r['line']): r['file'] for r in audit['selected']}
    rejected = {(r['voice'], r['line'], r['lang']) for r in audit['rejected']}
    expected = {(v['id'], lang, ln['n']): ln[lang] for v in voice_script.parse(
                more=voice_script.MORE100, only=voice_script.pinned()) for ln in v['lines'] for lang in ('ru','en')}
    decided = set(selected) | {(vid,lang,n) for vid,n,lang in rejected}
    if decided != set(expected):
        raise ValueError('audit does not match current script; run audit_voicepack.py again')
    for r in audit['selected']:
        if r['text'] != expected[(r['voice'], r['lang'], r['line'])]:
            raise ValueError('audit text differs from script')
        if not (SRC / r['file']).is_file():
            raise ValueError(f"missing audited audio: {r['file']}")
        stat = (SRC / r['file']).stat()
        if (stat.st_size, stat.st_mtime_ns) != (r['signal']['bytes'], r['signal']['mtime_ns']):
            raise ValueError(f"audio changed after audit: {r['file']}")
    for vid, state in states.items():
        for it in state['lines']:
            it['chosen'] = selected.get((vid, it['lang'], it['n'])) == it.get('file') and 'file' in it
    # английская подпись: для кого (первое имя из карточки)
    for r in rows:
        if r["voice"] in states and r["target_en"]:
            states[r["voice"]].setdefault("for_en", r["target_en"])
    doge = B.load_json("steps.json")
    for lang in a.lang.split(","):
        n, k, s, u, nu = build(lang, hold, events, rows, states, doge, rejected)
        print(f"hd_voices_{lang}: звуков {n}, наборов {k}, типов бойцов {s}, голосов врагов {u} на {nu} юнитов")
    print("на починке (не в моде):", " ".join(sorted(hold)) or "нет")


if __name__ == "__main__":
    main()
