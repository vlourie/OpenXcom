"""Перепись звуков игры по событиям: какой длины звук у выстрела, попадания, шага и т.д.

Этап 0 озвучки (docs/AUDIO_ROADMAP.md): длительность и огибающую новых звуков брать из того,
что игра уже играет на этом событии, а не на глаз.

Звуки читаются так же, как их читает движок:
  - BATTLE.CAT и GEO.CAT - SOUND/SAMPLE2.CAT и SAMPLE.CAT установки (Mod.cpp: сначала версия
    Windows, потом DOS SOUND1/SOUND2). Таблица CAT - пары смещение/размер, размер берётся по
    следующему смещению (CatFile.cpp); у записи байт длины имени, имя, дальше WAV. Заголовок WAV
    чинится, если данных меньше, чем в нём написано (SoundSet::loadCatByIndex).
  - extraSounds мода Пиратки (Piratez_Resources.rul) - номер в поле files кладётся в тот же набор;
    папка (имя на '/') раскладывается по порядку имён с номера записи (ExtraSounds::load).
Номер звука в рулсете и номер в наборе здесь одно и то же: смещение мода (loadSoundOffset)
одинаково добавляется к обоим, и перепись ведётся в номерах самого мода.

Какое поле рулсета в какой набор и на какое событие - по вызовам loadSoundOffset в src/Mod/*.cpp;
значения полей - итог слияния .index/mod/Piratez/rul/values.tsv (tools/rul_map.py). Постоянные
(двери, взрывы, шаги) - умолчания Mod.cpp, поверх - constants Пираток.

    tools/sfx/.venv/Scripts/python.exe tools/sound_census.py

Пишет census/sounds.tsv (звук на строку) и census/sound_events.tsv (событие на строку).
"""
import argparse
import csv
import json
import logging
import re
import struct
from collections import defaultdict
from pathlib import Path

import numpy as np
import soundfile as sf
import yaml
from yaml.events import AliasEvent

log = logging.getLogger("sound_census")
csv.field_size_limit(1 << 30)  # в values.tsv есть поля в мегабайт (MCDPatches, списки)

ROOT = Path(__file__).resolve().parents[1]
RUL = ROOT / ".index/mod/Piratez/rul"
ENC_R = "utf-8-sig"
ENC_W = "utf-8-sig"

# (раздел рулсета или * для любого, поле) -> (набор, событие); по loadSoundOffset в src/Mod
FIELDS = [
    ("items", "fireSound", "BATTLE.CAT", "выстрел"),
    ("items", "hitSound", "BATTLE.CAT", "попадание"),
    ("items", "explosionHitSound", "BATTLE.CAT", "взрыв"),
    ("items", "hitMissSound", "BATTLE.CAT", "промах"),
    ("items", "meleeSound", "BATTLE.CAT", "замах ближнего боя"),
    ("items", "meleeHitSound", "BATTLE.CAT", "удар ближнего боя"),
    ("items", "meleeMissSound", "BATTLE.CAT", "промах"),
    ("items", "psiSound", "BATTLE.CAT", "пси"),
    ("items", "psiMissSound", "BATTLE.CAT", "промах"),
    ("items", "reloadSound", "BATTLE.CAT", "перезарядка"),
    ("items", "primeSound", "BATTLE.CAT", "взвод и снятие"),
    ("items", "unprimeSound", "BATTLE.CAT", "взвод и снятие"),
    ("units", "deathSound", "BATTLE.CAT", "смерть"),
    ("armors", "deathMale", "BATTLE.CAT", "смерть"),
    ("armors", "deathFemale", "BATTLE.CAT", "смерть"),
    ("soldiers", "deathMale", "BATTLE.CAT", "смерть"),
    ("soldiers", "deathFemale", "BATTLE.CAT", "смерть"),
    ("units", "panicSound", "BATTLE.CAT", "паника и берсерк"),
    ("units", "berserkSound", "BATTLE.CAT", "паника и берсерк"),
    ("soldiers", "panicMale", "BATTLE.CAT", "паника и берсерк"),
    ("soldiers", "panicFemale", "BATTLE.CAT", "паника и берсерк"),
    ("soldiers", "berserkMale", "BATTLE.CAT", "паника и берсерк"),
    ("soldiers", "berserkFemale", "BATTLE.CAT", "паника и берсерк"),
    ("units", "aggroSound", "BATTLE.CAT", "агро"),
    ("units", "moveSound", "BATTLE.CAT", "ход техники"),
    ("armors", "moveSound", "BATTLE.CAT", "ход техники"),
    ("terrains", "ambience", "BATTLE.CAT", "фон карты"),
    ("terrains", "ambienceRandom", "BATTLE.CAT", "фон карты"),
    ("craftWeapons", "sound", "GEO.CAT", "геоскейп: бой кораблей"),
    ("ufos", "fireSound", "GEO.CAT", "геоскейп: бой кораблей"),
    ("ufos", "hitSound", "GEO.CAT", "геоскейп: бой кораблей"),
    ("ufos", "alertSound", "GEO.CAT", "геоскейп: тревога"),
    ("ufos", "huntAlertSound", "GEO.CAT", "геоскейп: тревога"),
    ("alienDeployments", "alertSound", "GEO.CAT", "геоскейп: тревога"),
    ("facilities", "fireSound", "GEO.CAT", "геоскейп: оборона базы"),
    ("facilities", "hitSound", "GEO.CAT", "геоскейп: оборона базы"),
    ("facilities", "placeSound", "GEO.CAT", "геоскейп: интерфейс"),
    ("crafts", "selectSound", "GEO.CAT", "геоскейп: интерфейс"),
    ("crafts", "takeoffSound", "GEO.CAT", "геоскейп: взлёт"),
    ("interfaces", "sound", "GEO.CAT", "геоскейп: интерфейс"),
]
# отклики юнита: поля Unit, Armor, RuleSoldier, RuleVoiceSet
for _sec in ("units", "armors", "soldiers", "voiceSets"):
    for _f in ("selectUnitSound", "startMovingSound", "selectWeaponSound", "annoyedSound",
               "selectUnitMale", "selectUnitFemale", "startMovingMale", "startMovingFemale",
               "selectWeaponMale", "selectWeaponFemale", "annoyedMale", "annoyedFemale",
               "selectUnit", "startMoving", "selectWeapon", "annoyed"):
        FIELDS.append((_sec, _f, "BATTLE.CAT", "отклик юнита"))

# постоянные Mod.cpp (умолчания) -> (ключ constants, набор, событие)
CONSTANTS = [
    ("doorSound", 3, "BATTLE.CAT", "двери"),
    ("slidingDoorSound", 20, "BATTLE.CAT", "двери"),
    ("slidingDoorClose", 21, "BATTLE.CAT", "двери"),
    ("smallExplosion", 2, "BATTLE.CAT", "взрыв"),
    ("largeExplosion", 5, "BATTLE.CAT", "взрыв"),
    ("itemDrop", 38, "BATTLE.CAT", "предмет: бросить и уронить"),
    ("itemThrow", 39, "BATTLE.CAT", "предмет: бросить и уронить"),
    ("itemReload", 17, "BATTLE.CAT", "перезарядка"),
    ("flyingSound", 15, "BATTLE.CAT", "ход техники"),
    ("buttonPress", 0, "GEO.CAT", "геоскейп: интерфейс"),
    ("ufoFire", 8, "GEO.CAT", "геоскейп: бой кораблей"),
    ("ufoHit", 12, "GEO.CAT", "геоскейп: бой кораблей"),
    ("ufoCrash", 10, "GEO.CAT", "геоскейп: бой кораблей"),
    ("ufoExplode", 11, "GEO.CAT", "геоскейп: бой кораблей"),
    ("interceptorHit", 10, "GEO.CAT", "геоскейп: бой кораблей"),
    ("interceptorExplode", 13, "GEO.CAT", "геоскейп: бой кораблей"),
]
WALK_DEFAULT = 22       # Mod::WALK_OFFSET
# WALK_OFFSET + 2 * тип пола + фаза шага (UnitWalkBState), тип - байт Footstep записи MCD.
# Тип 0 стоит у 13 полов из 7 тысяч и попадает на 22/23 - удар и крик, не шаг: в перепись не берём
WALK_TYPES = range(1, 7)
POPUP_DEFAULT = [1, 2, 3]  # Mod::WINDOW_POPUP

ENV_MS = 10             # окно огибающей
AUDIBLE_DB = -30.0      # слышимая часть: окна не тише пика на столько


class Tolerant(yaml.SafeLoader):
    """Повторный якорь, как у yaml-cpp (R-046; копия из tools/pck_census.py)."""

    def compose_node(self, parent, index):
        ev = self.peek_event()
        if (ev is not None and not isinstance(ev, AliasEvent)
                and getattr(ev, "anchor", None) and ev.anchor in self.anchors):
            del self.anchors[ev.anchor]
        return super().compose_node(parent, index)


# ------------------------------------------------------------------ чтение звуков

def cat_items(path):
    """Записи CAT так, как их режет CatFile: размер - до следующего смещения или конца файла."""
    data = path.read_bytes()
    off0 = struct.unpack_from("<I", data, 0)[0]
    offs = []
    for i in range(off0 // 8):
        o = struct.unpack_from("<I", data, i * 8)[0]
        if o >= len(data):
            log.warning("%s: запись %d за концом файла", path.name, i)
            continue
        offs.append(o)
    ends = offs[1:] + [len(data)]
    return [data[o:e] for o, e in zip(offs, ends)]


def decode_cat_item(item):
    """(выборки float mono, частота) как у SoundSet::loadCatByIndex, или None для пустой записи."""
    snd = item[1 + item[0]:]  # байт длины имени, имя
    if len(snd) < 12:
        return None
    if snd[0:4] == b"RIFF" and snd[8:12] == b"WAVE":
        ch = struct.unpack_from("<H", snd, 0x16)[0]
        rate = struct.unpack_from("<i", snd, 0x18)[0]
        bits = struct.unpack_from("<H", snd, 0x22)[0]
        raw = snd[44:]
        if bits == 16:
            x = np.frombuffer(raw[:len(raw) // 2 * 2], "<i2").astype(np.float32) / 32768
        else:
            x = (np.frombuffer(raw, np.uint8).astype(np.float32) - 128) / 128
        if ch > 1:
            x = x[:len(x) // ch * ch].reshape(-1, ch).mean(axis=1)
        return x, rate
    # DOS: 8 кГц, 6 бит, заголовок 5 байт, последний байт мусор; движок умножает на 4
    raw = np.frombuffer(snd[5:len(snd) - 1], np.uint8).astype(np.float32) * 4
    return (raw - 128) / 128, 8000


def decode_file(path):
    x, rate = sf.read(str(path), always_2d=True, dtype="float32")
    return x.mean(axis=1), rate


def measure(x, rate):
    peak = float(np.abs(x).max()) if len(x) else 0.0
    rms = float(np.sqrt((x.astype(np.float64) ** 2).mean())) if len(x) else 0.0
    n = max(1, rate * ENV_MS // 1000)
    w = len(x) // n
    res = {"dur": len(x) / rate, "rate": rate, "peak_db": 20 * np.log10(peak + 1e-9),
           "rms_db": 20 * np.log10(rms + 1e-9), "lead_ms": 0.0, "audible": 0.0, "tail_ms": 0.0}
    if w == 0 or peak <= 1e-6:
        return res
    env = np.sqrt((x[:w * n].astype(np.float64).reshape(w, n) ** 2).mean(axis=1))
    loud = np.nonzero(env >= env.max() * 10 ** (AUDIBLE_DB / 20))[0]
    first, last = int(loud[0]), int(loud[-1])
    res["lead_ms"] = first * ENV_MS
    res["audible"] = (last - first + 1) * ENV_MS / 1000
    res["tail_ms"] = max(0.0, res["dur"] * 1000 - (last + 1) * ENV_MS)
    return res


# ------------------------------------------------------------------ наборы

def natural_key(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def load_sets(game, mod):
    """{набор: {номер: (источник, выборки, частота)}} - ванильные CAT, поверх extraSounds мода."""
    sets = {}
    for set_id, win, dos in (("GEO.CAT", "SAMPLE.CAT", "SOUND2.CAT"),
                             ("BATTLE.CAT", "SAMPLE2.CAT", "SOUND1.CAT")):
        sets[set_id] = {}
        for name in (win, dos):
            p = game / "UFO/SOUND" / name
            if not p.exists():
                continue
            for i, item in enumerate(cat_items(p)):
                dec = decode_cat_item(item)
                if dec is not None:
                    sets[set_id][i] = (f"{name}#{i}", *dec)
            log.info("%s: %s, звуков %d", set_id, p, len(sets[set_id]))
            break
    res = mod / "Ruleset/Piratez_Resources.rul"
    with open(res, "rb") as f:
        doc = yaml.load(f, Loader=Tolerant)
    for entry in doc.get("extraSounds") or []:
        set_id = entry.get("type")
        files = entry.get("files") or {}
        target = sets.setdefault(set_id, {})
        added = 0
        for start, fname in files.items():
            fname = str(fname)
            if fname.endswith("/"):
                folder = mod / fname
                names = sorted((p.name for p in folder.iterdir() if p.is_file()), key=natural_key)
                todo = [(int(start) + k, folder / n, fname + n) for k, n in enumerate(names)]
            else:
                todo = [(int(start), mod / fname, fname)]
            for idx, path, label in todo:
                try:
                    target[idx] = (label, *decode_file(path))
                    added += 1
                except Exception as e:  # движок тоже пропускает нечитаемый файл с предупреждением
                    log.warning("%s: %s", label, e)
        log.info("%s: extraSounds мода %d", set_id, added)
    return sets


# ------------------------------------------------------------------ ссылки из рулсетов

def ints(value):
    return [int(n) for n in re.findall(r"-?\d+", value) if int(n) >= 0]


def load_refs(mod):
    """{(набор, номер): [(событие, 'раздел:id:поле'), ...]}"""
    fields = {(s, f): (st, ev) for s, f, st, ev in FIELDS}
    refs = defaultdict(list)
    with open(RUL / "values.tsv", encoding=ENC_R, newline="") as f:
        for row in csv.reader(f, delimiter="\t"):
            if len(row) < 4:
                continue
            hit = fields.get((row[0], row[2]))
            if hit:
                for n in ints(row[3]):
                    refs[(hit[0], n)].append((hit[1], f"{row[0]}:{row[1]}:{row[2]}"))
    # в globals.tsv значение constants обрезано - читаем сам рулсет
    consts = {}
    for path in sorted((mod / "Ruleset").glob("*.rul")):
        with open(path, "rb") as f:
            text = f.read()
        if b"\nconstants:" not in text and not text.startswith(b"constants:"):
            continue
        v = (yaml.load(text, Loader=Tolerant) or {}).get("constants")
        if isinstance(v, dict):
            consts.update(v)
    log.info("constants мода, звуковые: %s", {k: consts[k] for k, *_ in CONSTANTS if k in consts}
             or "нет, умолчания движка")
    for key, default, st, ev in CONSTANTS:
        for n in ([consts[key]] if key in consts else [default]):
            refs[(st, int(n))].append((ev, f"constants:{key}"))
    walk = int(consts.get("walkOffset", WALK_DEFAULT))
    for t in WALK_TYPES:
        for phase in (0, 1):
            refs[("BATTLE.CAT", walk + 2 * t + phase)].append(("шаги", f"constants:walkOffset+{2 * t + phase}"))
    for n in consts.get("windowPopup", POPUP_DEFAULT):
        refs[("GEO.CAT", int(n))].append(("геоскейп: интерфейс", "constants:windowPopup"))
    return refs


# ------------------------------------------------------------------ сводка

def stats(values):
    v = np.array(values, dtype=np.float64)
    return {"mean": v.mean(), "median": float(np.median(v)), "p10": float(np.percentile(v, 10)),
            "p90": float(np.percentile(v, 90)), "min": v.min(), "max": v.max()}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--game", default=str(ROOT / "Пиратки/Dioxine_XPiratez"))
    p.add_argument("--out", default=str(ROOT / "census"))
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    for stream in (__import__("sys").stdout, __import__("sys").stderr):
        stream.reconfigure(encoding="utf-8")

    game = Path(a.game)
    mod = game / "user/mods/Piratez"
    sets = load_sets(game, mod)
    refs = load_refs(mod)

    rows, missing = [], defaultdict(int)
    by_event = defaultdict(list)
    for (st, idx), rs in sorted(refs.items()):
        if idx not in sets.get(st, {}):
            for ev, _ in rs:
                missing[ev] += 1
    for st in sorted(sets):
        for idx in sorted(sets[st]):
            label, x, rate = sets[st][idx]
            m = measure(x, rate)
            rs = refs.get((st, idx), [])
            events = sorted({ev for ev, _ in rs})
            row = {"set": st, "index": idx, "source": label, **m,
                   "events": ",".join(events), "refs": len(rs),
                   "examples": " ".join(r for _, r in rs[:3])}
            rows.append(row)
            for ev in events:
                by_event[(st, ev)].append((row, sum(1 for e, _ in rs if e == ev)))

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    cols = ["set", "index", "source", "dur", "audible", "lead_ms", "tail_ms", "peak_db", "rms_db",
            "rate", "refs", "events", "examples"]
    with open(out / "sounds.tsv", "w", encoding=ENC_W, newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(cols)
        for r in rows:
            w.writerow([round(r[c], 3) if isinstance(r[c], float) else r[c] for c in cols])

    ecols = ["set", "event", "sounds", "refs", "dur_mean", "dur_median", "dur_p10", "dur_p90",
             "dur_min", "dur_max", "aud_mean", "aud_median", "aud_p10", "aud_p90",
             "lead_ms_median", "top"]
    lines = []
    with open(out / "sound_events.tsv", "w", encoding=ENC_W, newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(ecols)
        for (st, ev), items in sorted(by_event.items(), key=lambda kv: -sum(n for _, n in kv[1])):
            d = stats([r["dur"] for r, _ in items])
            au = stats([r["audible"] for r, _ in items])
            lead = float(np.median([r["lead_ms"] for r, _ in items]))
            top = sorted(items, key=lambda t: -t[1])[:5]
            top_s = " ".join(f"{r['index']}({n})" for r, n in top)
            w.writerow([st, ev, len(items), sum(n for _, n in items),
                        *(round(d[k], 2) for k in ("mean", "median", "p10", "p90", "min", "max")),
                        *(round(au[k], 2) for k in ("mean", "median", "p10", "p90")),
                        round(lead), top_s])
            lines.append(f"{st:10s} {ev:28s} звуков {len(items):4d}  длина медиана {d['median']:5.2f} "
                         f"(10-90%: {d['p10']:.2f}-{d['p90']:.2f})  слышно {au['median']:5.2f}  "
                         f"тишина в начале {lead:4.0f} мс")
    print("\n".join(lines))
    unref = sum(1 for r in rows if not r["refs"])
    log.info("звуков %d, без ссылок из рулсетов %d; ссылок на отсутствующий звук: %s",
             len(rows), unref, dict(missing) or "нет")
    log.info("записано: %s, %s", out / "sounds.tsv", out / "sound_events.tsv")


if __name__ == "__main__":
    main()
