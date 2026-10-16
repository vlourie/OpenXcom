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
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_test_mods as B   # noqa: E402  to_ogg, robotize, pick, write

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "art/sfx/voicepack"
HERE = Path(__file__).resolve().parent
FIRST = 200                   # свои номера BATTLE.CAT: выше общих звуков, до 2000 (reservedSpace 2)
RESERVED = 2
FREQUENCY = [60, 20, 40, 20]  # выбор, ход, оружие, «отстань» - проценты
EVENTS = {"select": "selectUnit", "move": "startMoving", "weapon": "selectWeapon", "annoyed": "annoyed"}
ROBOT = {"V025", "V026", "V027", "V029"}
# 16.10 Vitali: женские, звучащие мужиком - на починке (gen_voicepack.TIMBRE)
HOLD = "V005 V012 V016 V017 V019 V032 V043 V055 V060 V063 V072 V086 V109 V129 V133 V141 V155"
GENDER = {"М": [0], "Ж": [1], "оба": [0, 1]}


def read_tsv(name):
    with open(HERE / name, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def q(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def build(lang, hold, events, rows, states, doge_steps):
    mod = B.MODS / f"hd_voices_{lang}"
    if mod.exists():
        shutil.rmtree(mod)
    used = sorted({r["voice"] for r in rows} - hold)
    files, sets = [], {}          # sets: голос -> событие -> [номера]
    idx = FIRST
    for vid in used:
        chosen = {it["n"]: it for it in states[vid]["lines"] if it.get("chosen") and it["lang"] == lang}
        for ev in events.get(vid, []):
            if ev["event"] not in EVENTS or ev["line"] not in chosen:
                continue
            rel = f"Resources/Sounds/voices/{vid}/{ev['line']}.ogg"
            B.to_ogg(SRC / chosen[ev["line"]]["file"], mod / rel, robot=vid in ROBOT)
            files.append((idx, rel))
            sets.setdefault(vid, {}).setdefault(ev["event"], []).append(idx)
            idx += 1
    best = B.pick([it for it in doge_steps["items"] if it["group"] == "doge"],
                  lambda it: (it["dir"], it["name"]), 1)
    for (d, name), cands in sorted(best.items()):
        cat = d.split("/")[1]
        rel = f"Resources/Sounds/voices/doge/{cat}_{name}.ogg"
        B.to_ogg(B.SRC / cands[0]["file"], mod / rel)
        files.append((idx, rel))
        sets.setdefault("doge", {}).setdefault(cat, []).append(idx)
        idx += 1
    assert idx <= 1000 * RESERVED, idx

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
        f'name: "HD: голоса бойцов ({title})"\nversion: 1.0\nauthor: "Vitali + Claude"\n'
        f'description: "Голоса по сценарию записи: реплики на выбор бойца, ход, оружие и «отстань» '
        f'для команды, национальные голоса (выбор на базе), враги под контролем. Включать один язык."\n'
        f"id: hd_voices_{lang}\nmaster: piratez\nreservedSpace: {RESERVED}\n"))
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
    # английская подпись: для кого (первое имя из карточки)
    for r in rows:
        if r["voice"] in states and r["target_en"]:
            states[r["voice"]].setdefault("for_en", r["target_en"])
    doge = B.load_json("steps.json")
    for lang in a.lang.split(","):
        n, k, s, u, nu = build(lang, hold, events, rows, states, doge)
        print(f"hd_voices_{lang}: звуков {n}, наборов {k}, типов бойцов {s}, голосов врагов {u} на {nu} юнитов")
    print("на починке (не в моде):", " ".join(sorted(hold)) or "нет")


if __name__ == "__main__":
    main()
