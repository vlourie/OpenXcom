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
# XP-000311 (26.10, выбор A): голос бойца держится за портретом, а не за типом. Портрет бойца - ключ look + 4 * вариант
# облика, раздельно по полу (движок: RuleSoldier::getRandomVoiceSet, те же ключи, что у слоёв брони); у типов группы
# ключи одни и те же, поэтому при смене типа (Псих -> Боец -> Воин) голос остаётся тем же. Портретов столько, сколько
# ключей в layersDefinition нулевой брони типа (Piratez_Armors.rul): у уберов 60 на пол, у нэкомими 24.
# Портреты делятся на отрезки подряд (по 10; если портретов меньше, чем 10 на голос, - поровну), голоса идут по кругу.
# Типы вне групп остаются с одним голосом типа. Ручной выбор на базе по-прежнему главнее.
PORTRAIT_GROUPS = [
    {"types": ["STR_SOLDIER", "STR_SOLDIER_S", "STR_SOLDIER_M", "STR_SOLDIER_V"], "portraits": 60, "pool": ["V001", "V002"]},
    {"types": ["STR_SOLDIER_NEKOMIMI", "STR_SOLDIER_NEKOMIMI_O", "STR_SOLDIER_NEKOMIMI_H", "STR_SOLDIER_NEKOMIMI_W"],
     "portraits": 24, "pool": ["V014", "V015", "V016", "V017"]},
]
PORTRAIT_RUN = 10             # портретов подряд на один голос
# XP-000541 (10.11): у каждого типа несколько голосов-тонов одной расы (tools/sfx/voice_tones.tsv, звук в
# art/sfx/voicepack/V###/xp541/<n>.ogg, у V201-V203 <n>.proc.ogg). Набор тона VP_V### повторяет события и
# соответствие реплик основы (реплика n тона = реплика n основы). Голос по портрету: пул типа = голоса типа по
# умолчанию + их тоны, голос = пул[ключ % N]; ключ - тот же, что у движка (пол + look + 4 * вариант).
# Тона русские, поэтому только в hd_voices_ru; в английском моде всё как было.
PORTRAIT_COUNT = {t: 60 for t in ("STR_SOLDIER", "STR_SOLDIER_S", "STR_SOLDIER_M", "STR_SOLDIER_V",
                                  "STR_SOLDIER_X", "STR_SOLDIER_W", "STR_SOLDIER_R")}
PORTRAIT_COUNT.update({t: 64 for t in ("STR_SOLDIER_SLAVE", "STR_SOLDIER_PUREBLOOD", "STR_SOLDIER_HERO",
                                       "STR_SOLDIER_PEASANT", "STR_SOLDIER_DAMSEL")})
PORTRAIT_COUNT.update({"STR_SOLDIER_GNOME": 24, "STR_SOLDIER_OGRE": 16, "STR_SOLDIER_SYNTH": 12,
                       "STR_SOLDIER_HYBRID": 8, "STR_SOLDIER_LAMIA": 8, "STR_SOLDIER_CHORT": 4})


def pool_pick(pool, key):
    """Голос портрета: pool[ключ % N]. При N кратном 4 ключ % N совпал бы с look (голос привязан к лицу-классу,
    а не перемешан по вариантам) - тогда к ключу добавляется номер варианта (ключ // 4)."""
    n = len(pool)
    return pool[(key + (key // 4 if n % 4 == 0 else 0)) % n]


def tone_file(tone, line):
    d = SRC / tone / "xp541"
    for suffix in (".ogg", ".proc.ogg"):
        if (d / f"{line}{suffix}").is_file():
            return d / f"{line}{suffix}"
    return None


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


def read_excluded():
    """Реплики, стёртые проверяющим (tools/review/apply.py): {(голос, номер)}. Файлов нет - ничего не исключено.
    Сами ogg и voice.json не трогаются; вернуть реплику - убрать строку из art/review/excluded.tsv."""
    p = ROOT / "art/review/excluded.tsv"
    if not p.is_file():
        return set()
    with open(p, encoding="utf-8-sig") as f:
        return {(r["voice"], r["n"]) for r in csv.DictReader(f, delimiter="\t")}


def build(lang, hold, events, rows, states, doge_steps, rejected, tones):
    mod = B.MODS / f"hd_voices_{lang}"
    # rmtree не должен уйти через junction или за пределы двух наших модов.
    if mod.is_symlink() or mod.resolve().parent != B.MODS.resolve():
        raise ValueError(f"unsafe mod path: {mod}")
    # прежний мод - в сторону: файл с тем же звуком вернётся байт в байт и не станет новым блобом выпуска.
    # Не в user/mods: при падении сборки движок увидел бы второй мод с тем же id (R-074)
    old = B.MODS.parent / f".{mod.name}.old"
    if old.exists():
        shutil.rmtree(old)
    if mod.exists():
        mod.rename(old)
    used = sorted({r["voice"] for r in rows} - hold)
    excluded = read_excluded()
    files, sets = [], {}          # sets: голос -> событие -> [номера]
    idx = FIRST
    jobs = []
    for vid in used:
        chosen = {it["n"]: it for it in states[vid]["lines"] if it.get("chosen") and it["lang"] == lang}
        for ev in events.get(vid, []):
            if ev["event"] not in EVENTS:
                continue
            if (vid, ev["line"]) in excluded:
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
    tone_ids = []                 # тона, попавшие в мод (основа есть, файлы на месте)
    for tn in tones:
        base = tn["base"]
        if base in hold or base not in sets:
            continue
        got = 0
        for ev in events.get(base, []):
            if ev["event"] not in EVENTS or (base, ev["line"]) in excluded:
                continue
            src = tone_file(tn["id"], ev["line"])
            if src is None:
                if (base, ev["line"], lang) in rejected:
                    continue
                raise ValueError(f"missing tone line: {tn['id']}/{ev['line']}")
            y, _ = sf.read(str(src), dtype="float32")
            if not len(y) or float(abs(y).max()) < 0.002:     # тишина в серии (брак генерации): в мод не идёт
                print(f"тон {tn['id']} реплика {ev['line']}: тишина в исходнике, пропущена")
                continue
            rel = f"Resources/Sounds/voices/{tn['id']}/{ev['line']}.ogg"
            jobs.append((src, mod / rel, False))   # как все реплики: к -12 LUFS и лимитер (после Vorbis пик тона был до 1.5)
            files.append((idx, rel))
            sets.setdefault(tn["id"], {}).setdefault(ev["event"], []).append(idx)
            idx += 1
            got += 1
        if not got:
            raise ValueError(f"tone without lines: {tn['id']}")
        tone_ids.append(tn["id"])
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
    for vid in used + tone_ids:
        for event in EVENTS:
            if not sets.get(vid, {}).get(event):
                raise ValueError(f"empty event after audit: {vid}/{event}")
    def encode(job):
        loud_ogg(job[0], job[1], robot=job[2])
    with ThreadPoolExecutor(max_workers=8) as pool:
        for _ in pool.map(encode, jobs):
            pass
    kept = 0
    for _, rel in files:
        if (old / rel).is_file() and B.ogg_same(old / rel, mod / rel):
            shutil.copyfile(old / rel, mod / rel)
            kept += 1
    print(f"hd_voices_{lang}: {kept} из {len(files)} звуков прежние байт в байт")
    if old.exists():
        shutil.rmtree(old)

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
    # голос по портрету: тип -> {ключ портрета: голос}; голоса, которых нет в моде (на починке), в круг не идут
    portrait = {}
    tone_of = {tn["id"]: tn for tn in tones if tn["id"] in tone_ids}
    for tid, tn in tone_of.items():      # набор тона виден в «Голос бойца» там же, где и основа
        choice[tid] = {"types": set(choice[tn["base"]]["types"]), "genders": set(choice[tn["base"]]["genders"])}
    tone_types = []
    for tn in tone_of.values():
        if tn["types"] not in tone_types:
            tone_types.append(tn["types"])
    for types in tone_types:             # пул типа и пола: основы по умолчанию + их тона
        for t in types:
            per = {}
            for g, gl in ((0, "M"), (1, "F")):
                own = []              # голоса по умолчанию всей группы типов (XP-000311: при смене типа голос тот же)
                for t2 in types:
                    own += [v for v in soldier.get(t2, {0: [], 1: []})[g] if v not in own]
                pool = own + [tid for tid, tn in tone_of.items() if tn["base"] in own and t in tn["types"]]
                per[gl] = pool
            if all(len(p) < 2 for p in per.values()):
                continue
            portrait[t] = {f"{gl}{n}": pool_pick(per[gl], n) for gl in "MF" for n in range(PORTRAIT_COUNT[t])
                           if per[gl]}
            for pool in per.values():
                for v in pool:
                    choice[v]["types"].add(t)
    for grp in PORTRAIT_GROUPS:
        if any(t in portrait for t in grp["types"]):
            continue                      # тип уже раскладан по пулу с тонами
        pool = [v for v in grp["pool"] if v in sets]
        if len(pool) < 2:
            continue
        run = min(PORTRAIT_RUN, math.ceil(grp["portraits"] / len(pool)))
        for t in grp["types"]:
            portrait[t] = {f"{g}{n}": pool[(n // run) % len(pool)] for g in "MF" for n in range(grp["portraits"])}
            for v in pool:   # голос портрета виден в «Голос бойца» у всех типов группы
                choice[v]["types"].add(t)
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
        if s in portrait:
            L.append("    voiceSets:   # по портрету: пол + look + 4 * вариант облика")
            L += [f"      {k}: [{name(v)}]" for k, v in portrait[s].items()]
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
            elif vid in tone_of:
                b = tone_of[vid]["base"]
                label = (states[b]["name"] + f" (тон {tone_of[vid]['tone']})" if code == "ru"
                         else f"{vid} " + states[b].get("for_en", b) + f" (tone {tone_of[vid]['tone']})")
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
    # тона XP-000541 (V158-V203) идут отдельной серией (xp541/), в аудите основных голосов их нет
    tone_ids_all = {r["id"] for r in read_tsv("voice_tones.tsv")}
    expected = {(v['id'], lang, ln['n']): ln[lang] for v in voice_script.parse(
                more=voice_script.MORE100, only=voice_script.pinned()) if v['id'] not in tone_ids_all
                for ln in v['lines'] for lang in ('ru','en')}
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
    tones = [{"id": r["id"], "types": r["types"].split(","), "base": r["base"], "tone": r["tone"]}
             for r in read_tsv("voice_tones.tsv")]
    for lang in a.lang.split(","):
        n, k, s, u, nu = build(lang, hold, events, rows, states, doge, rejected, tones if lang == "ru" else [])
        print(f"hd_voices_{lang}: звуков {n}, наборов {k}, типов бойцов {s}, голосов врагов {u} на {nu} юнитов")
    print("на починке (не в моде):", " ".join(sorted(hold)) or "нет")


if __name__ == "__main__":
    main()
