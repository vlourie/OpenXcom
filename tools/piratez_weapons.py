"""Оружие X-Piratez и патроны к нему: таблица и страница по классам Vitali.

Источник - слитые рулсеты Пираток (.index/mod/Piratez/rul/values.tsv, строит tools/rul_map.py)
и строки ru.yml мода с RU-патчем поверх. Классы присваиваются автоматически по полям рулсета;
в TSV рядом с классом записано основание - по нему видно, что поправить руками.

    py -3.13 tools/piratez_weapons.py [--apply arsenal-popravki-....json ...]

Выход: docs/research/piratez-weapons.tsv (оружие x патрон), docs/research/piratez-weapons.html
(страница для Artifact) и docs/research/piratez-weapons-review.html - тот же арсенал отдельным
файлом для другой машины: открывается без сети, поправки (класс, патроны, комментарий) хранятся
в браузере и выгружаются JSON. --apply переносит классы из таких JSON в таблицу и страницы,
комментарии к патронам печатает - их правят в classify руками.
"""
import argparse
import collections
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VALUES = ROOT / ".index/mod/Piratez/rul/values.tsv"
MODS = ROOT / "Пиратки/Dioxine_XPiratez/user/mods"
LANG = [MODS / "Piratez/Language/ru.yml", MODS / "XPZ RU-patch/Language/ru.yml"]
OUT_TSV = ROOT / "docs/research/piratez-weapons.tsv"
OUT_HTML = ROOT / "docs/research/piratez-weapons.html"
OUT_REVIEW = ROOT / "docs/research/piratez-weapons-review.html"
STANDALONE_HEAD = ('<!doctype html>\n<html lang="ru">\n<head>\n<meta charset="utf-8">\n'
                   '<meta name="viewport" content="width=device-width, initial-scale=1">\n')
TEMPLATE = ROOT / "tools/piratez_weapons.html.in"

CLASSES = {
    1: "Одноручное холодное",
    2: "Двуручное холодное",
    3: "Холодное длинное (досягаемость 2+ клетки)",
    4: "Холодное экзотическое",
    5: "Пистолеты",
    6: "Пистолеты-пулемёты",
    7: "Дробовое оружие",
    8: "Пулемёты",
    9: "Карабины",
    10: "Автоматические карабины (автоматы)",
    11: "Снайперское оружие",
    12: "Навесное: метательное и стрелковое",
    13: "Тяжёлое оружие, «полевая артиллерия»",
    14: "Магическое (пси, чары, магия)",
    15: "Дальнобойное специальное",
    16: "Навык (встроено в броню бойца)",
    0: "Вне классификации: гранаты, бомбы, мины",
}

DAMAGE = ["Очарование", "Бронебойный", "Огненный", "Контузящий", "Лазерный", "Плазменный",
          "Оглушение", "Режущий", "Химический", "Удушающий", "Анти-Э511", "Биологический",
          "Электрический", "ЭМИ", "Варп", "Псионика", "Колющий", "Тепло", "Холод"]

MODES = [("Aimed", "Прицельный"), ("Snap", "Навскидку"), ("Auto", "Очередь"), ("Melee", "Удар")]

# не оружие игрока: служебные предметы, ауры, ловушки, живность на плече, пульты
SKIP_ID = re.compile(r"^(AURA_|ALIEN_|INV_|STR_DEATH_TRAP_)|^(STR_REMOTE_CONTROL|STR_RANGEFINDER|STR_PARROT|"
                     r"STR_ROBO_PARROT|STR_DESTROPORTAL|STR_GLAMOUR)$")
MAGIC_ID = re.compile(r"WAND_|SKULL_ROD|ICE_ROSE|TOME_|GRIMOIRE|SCROLL_|RUNES_|ARCANE|DIVINE_BOLT|MAGIC_HAMMER|"
                      r"FLAME_GLOVE|PRISM_STAFF|COBRA_STAFF|STAFF_OF|THROWING_CARDS|DEMONIC_ESSENCE|"
                      r"ACCURSED_SWILL|BONE_SHIELD|TK_DEVICE|GREAT_HORN|DEATH_BLASTER|HELLGUN|FLAME_WHIP|"
                      r"DEATHBLADE|RAGE_BOMB|PERSUADOTRON")
EXOTIC_ID = re.compile(r"CHAINSAW|AUTO_AXE|RIPPER|_FAN$|SHAWL|NOOSE|CAT_PAWS|SHIELD|ENERGY_SCYTHE|THERMAL_LANCE")
SMG_ID = re.compile(r"SMG|TOMMYGUN|MP40|^STR_MP$|TEC9|PPSH|SKORPION|LYNX|WOLFGUN|ASMG|PAINBRINGER|DEATH_BLOSSOM")
SNIPER_ID = re.compile(r"SNIPER|MARKSMAN")
HEAVY_ID = re.compile(r"CANNON|LACC|SUPERHEAVY|AT_RIFLE|HEAVY_PARTICLE")
ARCHERY_ID = re.compile(r"(^|_)X?BOW(_|$)|BLOWPIPE|EXECUTIONER_XBOW|BALLISTA|LONGBOW")


def read_values():
    csv.field_size_limit(1 << 30)
    sec = collections.defaultdict(lambda: collections.defaultdict(dict))
    with open(VALUES, encoding="utf-8-sig", newline="") as f:
        # R-109: QUOTE_NONE, иначе строковые JSON-значения теряют кавычки
        for row in csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
            if len(row) < 4 or row[0] not in ("items", "armors", "soldiers"):
                continue
            try:
                sec[row[0]][row[1]][row[2]] = json.loads(row[3])
            except ValueError:
                sec[row[0]][row[1]][row[2]] = row[3]
    return sec


KEY = re.compile(r"^  ([A-Za-z0-9_\-\.]+):\s*(.*)$")


def read_lang():
    d = {}
    for p in LANG:
        with open(p, encoding="utf-8-sig") as f:
            for line in f:
                m = KEY.match(line.rstrip("\n"))
                if not m:
                    continue
                v = m.group(2)
                if v.startswith('"'):
                    out, i = [], 1
                    while i < len(v) and v[i] != '"':
                        if v[i] == chr(92) and i + 1 < len(v):
                            i += 1
                        out.append(v[i])
                        i += 1
                    v = "".join(out)
                else:
                    v = v.split(" #")[0].strip()
                d[m.group(1)] = v.replace("{NEWLINE}", " ").replace("{ALT}", "").split("{SMALLLINE}")[0].strip()
    return d


def player_builtin(sec):
    soldiers = set(sec["soldiers"])
    use = collections.defaultdict(set)
    for aid, a in sec["armors"].items():
        if not any(u in soldiers for u in (a.get("units") or [])):
            continue
        for w in (a.get("builtInWeapons") or []):
            use[w].add(aid)
        if a.get("specialWeapon"):
            use[a["specialWeapon"]].add(aid)
    return use


def cost_time(it, mode):
    c = it.get("cost" + mode)
    if isinstance(c, dict) and c.get("time") is not None:
        return c["time"]
    return it.get("tu" + mode)


def modes_of(it):
    out = []
    for key, label in MODES:
        tu = cost_time(it, key)
        if tu:
            conf = it.get("conf" + key) or {}
            slot = conf.get("ammoSlot", 0) if isinstance(conf, dict) else 0
            shots = conf.get("shots") if isinstance(conf, dict) else None
            if key == "Auto" and not shots:
                shots = it.get("autoShots", 3)
            out.append({"m": label, "tu": tu, "slot": slot, "shots": shots})
    return out


def ammo_slots(it):
    slots = {}
    if it.get("compatibleAmmo"):
        slots[0] = list(it["compatibleAmmo"])
    if isinstance(it.get("ammo"), dict):
        for k, v in it["ammo"].items():
            if isinstance(v, dict) and v.get("compatibleAmmo"):
                slots[int(k)] = list(v["compatibleAmmo"])
    return slots


def cats_of(it):
    return [c.replace("STR_BAT_CAT_", "") for c in (it.get("categories") or [])]


PRIMARY = ("SHOTGUN", "PISTOL", "RIFLE", "CHAINGUN", "GL", "RL", "GUIDED", "THROWN",
           "ONE_HANDED", "TWO_HANDED")


def primary_cat(cats):
    for c in cats:
        if c in PRIMARY:
            return c
    return ""


def classify(iid, it, name, builtin):
    """(класс, основание). None - не оружие игрока."""
    bt = it.get("battleType")
    fixed = bool(it.get("fixedWeapon"))
    if fixed or iid.startswith(("AUX_", "SPC_")):
        if iid in builtin and bt in (1, 3, 9, 10):
            return 16, "встроено в броню бойца"
        return None
    if SKIP_ID.search(iid):
        return None
    if bt in (4, 5):
        # ловушки карты, призыв юнитов, рабы и проклятые артефакты - не снаряжение бойца
        if it.get("invWidth") == 0 or it.get("recover") is False or (it.get("costSell") or 0) < 0:
            return None
        if it.get("spawnUnit") or iid.startswith(("STR_SPAWN", "TRAP_", "TIMEBOMB_")):
            return None
        return 0, "граната/мина (battleType %d)" % bt
    if bt not in (1, 3, 9):
        return None
    cats = cats_of(it)
    if "INTELLIGENCE" in cats or "LIABILITIES" in cats:
        return None
    slots = ammo_slots(it)
    two = bool(it.get("twoHanded"))
    mr = it.get("maxRange")
    if bt == 9:
        return 14, "пси-усилитель (battleType 9)"
    if it.get("psiRequired") or "PSI_ONLY" in cats:
        return 14, "требует пси (psiRequired / PSI_ONLY)"
    if MAGIC_ID.search(iid):
        return 14, "по имени: магический предмет"
    if bt == 3:
        if EXOTIC_ID.search(iid) or "ARTIFACT" in cats or "SHIELD" in cats:
            return 4, "ближний бой: артефакт/щит/механизм"
        return (2, "ближний бой, двуручное") if two else (1, "ближний бой, одноручное")
    pc = primary_cat(cats)
    if ARCHERY_ID.search(iid):
        return 12, "лук/арбалет/духовая трубка"
    # холодное, сделанное «огнестрелом» без патронов (удар на дистанцию)
    if not slots and pc in ("ONE_HANDED", "TWO_HANDED"):
        if EXOTIC_ID.search(iid) or "ARTIFACT" in cats:
            return 4, "холодное: артефакт/механизм"
        if mr is not None and mr > 7:
            return 15, "распылитель/излучатель на %d клеток" % mr
        if mr is not None and 2 <= mr <= 7:
            return 3, "холодное, бьёт на %d клетки" % mr
        return (2, "холодное, двуручное") if two else (1, "холодное, одноручное")
    if "MORALE" in cats or "STIM" in cats:
        return 15, "знамя/инструмент/стимулятор"
    if pc == "THROWN" or not pc and it.get("arcingShot"):
        clip = it.get("clipSize")
        if not slots and clip is not None and clip > 0:
            return 12, "метательное: %s шт. в связке" % clip
        if it.get("arcingShot") and not slots and clip == 1:
            return 12, "метательное, по дуге"
        return 15, "особое (категория мода THROWN)"
    if pc in ("RL", "GUIDED"):
        return 13, "пусковая установка (RL/GUIDED)"
    if HEAVY_ID.search(iid):
        return 13, "по имени: пушка / ПТР"
    if pc == "GL":
        return 12, "навесная траектория (GL)"
    if pc == "SHOTGUN" or it.get("shotgunPellets"):
        return 7, "дробовики (категория мода)"
    has_auto = bool(cost_time(it, "Auto"))
    if SMG_ID.search(iid) or re.search(r"(^|[^А-Яа-я])ПП([^А-Яа-я]|$)|Пистолет-пулемет", name):
        return 6, "по имени: ПП"
    if pc == "PISTOL":
        return 5, "пистолеты (категория мода)"
    if pc == "CHAINGUN":
        return 8, "огонь на подавление (CHAINGUN)"
    acc = it.get("accuracyAimed") or 0
    if SNIPER_ID.search(iid) or it.get("minRange") or (acc >= 150 and not has_auto):
        return 11, "снайперское: minRange или точность %d" % acc
    if pc == "RIFLE" or not pc:
        if has_auto:
            return 10, "винтовка с очередью"
        if not two and not pc:
            return 5, "одноручное без категории"
        return 9, "винтовка без очереди"
    return None


def charge_of(it):
    """Заряд самого предмета (без отдельных патронов)."""
    if it.get("power") is None and it.get("damageType") is None:
        return None
    return {"p": it.get("power"), "dt": it.get("damageType"), "clip": it.get("clipSize"),
            "pel": it.get("shotgunPellets"), "br": it.get("blastRadius")}


def read_corrections(paths):
    """Классы из файлов поправок страницы: {id: (класс, основание)}; позднейший файл побеждает."""
    out, notes = {}, []
    for p in paths:
        d = json.loads(Path(p).read_text(encoding="utf-8-sig"))
        if d.get("format") != "piratez-weapons-corrections":
            raise SystemExit("%s: не файл поправок арсенала" % p)
        who = d.get("reviewer") or Path(p).stem
        if d.get("general"):
            notes.append("%s, общее: %s" % (who, d["general"]))
        for iid, x in d.get("items", {}).items():
            c = x.get("class_new")
            if isinstance(c, int) and c in CLASSES:
                out[iid] = (c, "поправка (%s)%s" % (who, ": " + x["note"] if x.get("note") else ""))
            elif c is None and x.get("note"):
                out[iid] = (None, "замечание (%s): %s" % (who, x["note"]))
            elif c is not None:
                notes.append("%s, %s: класс %s, %s" % (who, iid, c, x.get("note") or "-"))
            if x.get("ammo"):
                notes.append("%s, %s, патроны: %s" % (who, iid, x["ammo"]))
    return out, notes


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", nargs="*", default=[], help="файлы поправок JSON со страницы")
    args = ap.parse_args()
    fixes, notes = read_corrections(args.apply)
    sec = read_values()
    items = sec["items"]
    ru = read_lang()
    builtin = player_builtin(sec)

    def nm(iid):
        it = items.get(iid, {})
        key = it.get("name", iid)
        return ru.get(key) or ru.get(iid) or iid

    weapons, ammo_used = [], collections.defaultdict(list)
    for iid, it in items.items():
        name = nm(iid)
        got = classify(iid, it, name, builtin)
        if got is None:
            continue
        cls, why = fixes.get(iid, got)
        if cls is None:
            cls, why = got[0], got[1] + "; " + why
        slots = ammo_slots(it)
        modes = modes_of(it)
        w = {"id": iid, "n": name, "c": cls, "why": why, "h": 2 if it.get("twoHanded") else 1,
             "wt": it.get("weight"), "o": it.get("listOrder", 0), "modes": modes,
             "slots": [{"s": s, "a": a, "use": [m["m"] for m in modes if m["slot"] == s]}
                       for s, a in sorted(slots.items())],
             "own": None if slots else charge_of(it)}
        if cls == 16 and iid in builtin:
            w["arm"] = len(builtin[iid])
        weapons.append(w)
        for s, a in slots.items():
            for am in a:
                ammo_used[am].append(iid)
    weapons.sort(key=lambda w: (w["c"] if w["c"] else 99, w["o"], w["n"]))

    ammo = {}
    for am in ammo_used:
        it = items.get(am, {})
        ammo[am] = {"n": nm(am), "p": it.get("power"), "dt": it.get("damageType"),
                    "clip": it.get("clipSize"), "pel": it.get("shotgunPellets"),
                    "br": it.get("blastRadius"), "wt": it.get("weight"),
                    "miss": am not in items}

    # TSV: строка на пару оружие x патрон
    OUT_TSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_TSV, "w", encoding="utf-8-sig", newline="") as f:
        wr = csv.writer(f, delimiter="\t", lineterminator="\n")
        wr.writerow(["класс", "класс_название", "оружие", "оружие_id", "руки", "вес", "слот",
                     "патрон", "патрон_id", "урон", "тип_урона", "ёмкость", "основание_класса"])
        for w in weapons:
            base = [w["c"], CLASSES[w["c"]], w["n"], w["id"], w["h"], w["wt"]]
            if not w["slots"]:
                o = w["own"] or {}
                dt = o.get("dt")
                wr.writerow(base + ["", "(свой заряд)", "", o.get("p", ""),
                                    DAMAGE[dt] if isinstance(dt, int) and dt < len(DAMAGE) else "",
                                    o.get("clip", ""), w["why"]])
                continue
            for sl in w["slots"]:
                for am in sl["a"]:
                    a = ammo[am]
                    dt = a["dt"]
                    wr.writerow(base + [sl["s"], a["n"], am, a["p"] if a["p"] is not None else "",
                                        DAMAGE[dt] if isinstance(dt, int) and dt < len(DAMAGE) else "",
                                        a["clip"] if a["clip"] is not None else "", w["why"]])

    data = {"classes": [{"c": k, "n": v} for k, v in sorted(CLASSES.items(), key=lambda x: x[0] or 99)],
            "damage": DAMAGE, "weapons": weapons, "ammo": ammo,
            "built": __import__("datetime").date.today().isoformat()}
    page = TEMPLATE.read_text(encoding="utf-8").replace(
        "/*DATA*/null", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    OUT_HTML.write_text(page, encoding="utf-8")
    # отдельный файл: полный документ, кодировка объявлена, данные внутри - откроется с диска без сети
    head, body = page.split("</style>", 1)
    OUT_REVIEW.write_text(STANDALONE_HEAD + head + "</style>\n</head>\n<body>\n" + body.lstrip()
                          + "</body>\n</html>\n", encoding="utf-8")

    cnt = collections.Counter(w["c"] for w in weapons)
    for k in sorted(cnt, key=lambda x: x or 99):
        print("%2d  %-45s %4d" % (k, CLASSES[k], cnt[k]))
    pairs = sum(len(sl["a"]) for w in weapons for sl in w["slots"])
    print("оружия %d, патронов %d, пар оружие-патрон %d" % (len(weapons), len(ammo), pairs))
    if args.apply:
        applied = sum(1 for w in weapons if fixes.get(w["id"], (None,))[0] is not None)
        remarks = sum(1 for w in weapons if fixes.get(w["id"], (0,))[0] is None)
        print("поправок класса применено %d из %d, замечаний без смены класса %d из %d"
              % (applied, sum(1 for f in fixes.values() if f[0] is not None),
                 remarks, sum(1 for f in fixes.values() if f[0] is None)))
        print("не найдено в таблице:", sorted(set(fixes) - {w["id"] for w in weapons}) or "-")
        for n in notes:
            print("  руками:", n)
    print(OUT_TSV)
    print(OUT_HTML)
    print(OUT_REVIEW)


if __name__ == "__main__":
    main()
