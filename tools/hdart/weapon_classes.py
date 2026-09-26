"""Классы стрелкового оружия для боевых эффектов HD: вспышка у ствола и вид попадания.

Две независимые оси, обе из рулсета, без ручных списков:
  класс оружия  - по имени (MUSKET, SNIPER...), потом по categories (STR_BAT_CAT_PISTOL...),
                  потом по данным (дробь, режимы огня, урон). Задаёт ВСПЫШКУ и базовую ступень.
  попадание     - по патрону: тип урона, взрыв, дробь. Для пуль ступень cal1..cal5 берётся
                  от класса и сдвигается уроном патрона на одну ступень: слабый пистолет и
                  «магнум» попадают по-разному, но магнум всё равно мельче пулемёта.

Пишет census/weapon_classes_<мод>.tsv и печатает сводку.

    python tools/hdart/weapon_classes.py --mod Piratez
    python tools/hdart/weapon_classes.py --mod xcom1
"""
import argparse
import glob
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from pck_census import load_yaml  # noqa: E402

ENC = "utf-8-sig"
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MODS = {
    "Piratez": [os.path.join(ROOT, "Пиратки", "Dioxine_XPiratez", "user", "mods", "Piratez", "Ruleset")],
    "xcom1": [os.path.join(ROOT, "bin", "standard", "xcom1")],
}
# имена типов урона Пираток (их damageTypes), для ванили 0..9 те же по смыслу: AP, IN, HE, LASER...
DT = {0: "CHARM", 1: "PIERCING", 2: "BURN", 3: "CONCUSSIVE", 4: "LASER", 5: "PLASMA", 6: "DAZE",
      7: "CUTTING", 8: "CHEM", 9: "CHOKING", 10: "ANTI-E511", 11: "BIO", 12: "ELECTRIC", 13: "EMP",
      14: "WARP", 15: "MIND", 16: "STABBING", 17: "HEAT", 18: "COLD", 19: "DT19"}

# ------------------------------------------------------------------ классы
# класс: (вспышка, базовая ступень пули, подпись)
CLASSES = {
    "pistol":   ("pistol",  1, "пистолет, револьвер"),
    "smg":      ("smg",     2, "пистолет-пулемёт"),
    "rifle":    ("rifle",   3, "винтовка, автомат, карабин"),
    "sniper":   ("sniper",  4, "снайперская винтовка"),
    "mg":       ("heavy",   4, "пулемёт, миниган"),
    "cannon":   ("cannon",  5, "пушка, гаусс-орудие"),
    "shotgun":  ("shotgun", 1, "дробовик"),
    "musket":   ("powder",  3, "дульнозарядное: кремнёвое, мушкет, мушкетон"),
    "bow":      ("none",    2, "лук, арбалет, праща"),
    "launcher": ("rocket",  4, "гранатомёт, ракетомёт, безоткатное"),
    "flamer":   ("flame",   3, "огнемёт"),
    "thrown":   ("none",    2, "метательное и дальний удар холодным"),
    "creature": ("none",    3, "оружие существа: плевок, взгляд, луч"),
}
# в имени предмета: слово целиком или начало слова; имя сильнее категории
NAME_RULES = [
    (("FLINTLOCK", "MUSKET", "HARQUEBUS", "ARQUEBUS", "BLUNDERBUSS", "MATCHLOCK", "HANDGONNE", "BLACKPOWDER"), "musket"),
    (("BOW", "LONGBOW", "XBOW", "CROSSBOW", "SLING", "SLINGSHOT"), "bow"),
    (("SNIPER", "MARKSMAN", "ANTIMATERIEL", "AMR"), "sniper"),
    (("SMG", "ASMG", "HSMG", "UZI", "SUBMACHINE"), "smg"),
    (("MINIGUN", "GATLING", "CHAINGUN", "MG", "HMG", "MACHINEGUN"), "mg"),
    (("CANNON", "AUTOCANNON", "RECOILLESS"), "cannon"),
    (("FLAMER", "FLAMETHROWER", "INCINERATOR"), "flamer"),
    (("PISTOL", "REVOLVER", "MAGNUM", "DERRINGER"), "pistol"),
    (("LAUNCHER", "BAZOOKA", "RPG", "PANZERFAUST"), "launcher"),
    (("RIFLE", "CARBINE"), "rifle"),
    (("HEAVY",), "mg"),
]
CATEGORY_RULES = [
    ("STR_BAT_CAT_SHOTGUN", "shotgun"), ("STR_BAT_CAT_CHAINGUN", "mg"),
    ("STR_BAT_CAT_PISTOL", "pistol"), ("STR_BAT_CAT_RIFLE", "rifle"),
    ("STR_BAT_CAT_RL", "launcher"), ("STR_BAT_CAT_GL", "launcher"),
    ("STR_BAT_CAT_THROWN", "thrown"),
]
BULLET_DT = {"PIERCING", "STABBING", "CUTTING", "CONCUSSIVE", "ANTI-E511", "DAZE", "HEAT", "COLD"}
# урон, у которого своё попадание, а не пулевое
ENERGY_DT = {"LASER": "laser", "PLASMA": "plasma", "ELECTRIC": "electric", "WARP": "warp", "MIND": "psi",
             "EMP": "electric", "BURN": "fire", "CHEM": "acid", "BIO": "bio", "CHOKING": "gas",
             "CHARM": "charm"}


def words_of(name):
    return [w for w in re.split(r"[^A-Z0-9]+", name.upper()) if w]


def by_name(name):
    ws = words_of(name)
    for keys, cls in NAME_RULES:
        for w in ws:
            if w in keys:
                return cls, w
    return None, None


def by_category(cats):
    for key, cls in CATEGORY_RULES:
        if key in cats:
            return cls, key.replace("STR_BAT_CAT_", "")
    return None, None


# вид удара ближнего боя (клип swing_<вид>_<dir>) - по словам имени, как в fx_census.py:
# слово целиком или начало слова от 4 букв; SPIKED_MACE не копьё, BATTLE_AX не дубина
MELEE_RULES = [
    ("whip", ["WHIP", "LASH", "FLAIL", "KUSARIGAMA", "NOOSE", "CHAIN", "GRAPPLE", "TENTACLE", "TENTACLES"]),
    ("claw", ["CLAW", "CLAWS", "TALON", "PAWS", "REAPER", "CHRYSSALID", "RATT", "HYENA", "DOGG", "WEREDOGE", "CHUPACABRA",
              "SPIDER", "GIANTSPIDER", "MEGASCORPION", "KRAB", "BEETLE", "MAGGOT", "VAMPIRE", "CAT", "TASOTH", "BOOMOSAURUS",
              "ZOMBIGAL", "WOLVERINE"]),
    ("bite", ["BITE", "JAW", "FANG", "BEAK", "MAW", "FISH", "SHARK", "ZOMBIE", "VAMPBAT", "DOGE"]),
    ("fist", ["FIST", "FISTO", "FISTY", "SHOCKAFIST", "PUNCH", "KNUCKLES", "GAUNTLET", "KUNG", "PALM", "KICK", "BRAWL",
              "SLAP", "UNARMED", "WRESTLING", "BAD", "GENTLE", "PEG", "CESTUS", "HANDLE", "GLOVE"]),
    ("sting", ["STING", "NEEDLE", "BEES", "INFECTOR", "SYRINGE", "DRILL"]),
    ("pierce", ["SPEAR", "PIKE", "TRIDENT", "LANCE", "IMPALER", "PITCHFORK", "BOATHOOK", "HALBERD", "GLAIVE", "BAYONET",
                "RAPIER"]),
    ("blade", ["SWORD", "KNOIF", "KNIFE", "BLADE", "SABER", "SABRE", "CUTLASS", "MACHETE", "KATANA", "WAKIZASHI", "GLADIUS",
               "DAGGER", "AX", "SCYTHE", "CLEAVER", "CHAINSAW", "SICKLE", "SLICER", "RAZOR", "BILLHOOK", "GARLAND", "SHIV",
               "MANHACK", "HATCHET"]),
    ("club", ["CLUB", "BAT", "BATTO", "MACE", "HAMMER", "BATON", "CROWBAR", "PIPE", "STAFF", "QUARTERSTAFF", "CANE", "MAUL",
              "STICK", "WRENCH", "ROD", "TONFA", "MORNING", "SLEDGE", "PAN", "SHOVEL", "SCEPTER", "THUNDERSTRIKER",
              "DISCIPLINER", "ANCHOR", "SIGN", "IV", "ROCK", "PILLOW", "GUITAR", "FLAG", "SHIELD", "PADD", "TORCH", "MAG",
              "FIRE", "FAN", "SHAWL", "PROD"]),
]


def melee_kind(name, bt):
    """Вид удара; без совпадения: у стрелкового - приклад, у прочего - кулак."""
    words = name.upper().split("_")
    for kind, ws in MELEE_RULES:
        if any(w == x or (len(x) >= 4 and w.startswith(x)) for w in words for x in ws):
            return kind
    return "butt" if bt == 1 else "fist"


# ------------------------------------------------------------------ чтение рулсетов

def load_items(dirs):
    items = {}
    for d in dirs:
        for p in sorted(glob.glob(os.path.join(d, "**", "*.rul"), recursive=True)):
            try:
                doc = load_yaml(p)
            except Exception as e:  # noqa: BLE001
                print(f"  не прочитан {os.path.basename(p)}: {e}", file=sys.stderr)
                continue
            if not isinstance(doc, dict):
                continue
            for it in doc.get("items") or []:
                if not isinstance(it, dict):
                    continue
                if "delete" in it:
                    items.pop(it["delete"], None)
                    continue
                t = it.get("type")
                if t:
                    items.setdefault(t, {}).update(it)
    return items


def dtype(it):
    v = it.get("damageType")
    if isinstance(v, dict):
        v = v.get("type", v.get("ResistType"))
    try:
        return DT.get(int(v), str(v)) if v is not None else None
    except (TypeError, ValueError):
        return str(v)


def ammo_of(it, items):
    """Патроны оружия: compatibleAmmo, ammo: {слот: {compatibleAmmo}}; без них - само оружие."""
    names = list(it.get("compatibleAmmo") or [])
    for slot in (it.get("ammo") or {}).values():
        if isinstance(slot, dict):
            names += slot.get("compatibleAmmo") or []
    got = [items[n] for n in dict.fromkeys(names) if n in items]
    return got or [it]


def is_ranged(it):
    """Есть ли у предмета выстрел: хоть одна точность дальнего режима или цена выстрела."""
    for m in ("Aimed", "Snap", "Auto"):
        if (it.get("accuracy" + m) or 0) > 0:
            return True
        cost = it.get("cost" + m)
        if isinstance(cost, dict) and (cost.get("time") or 0) > 0:
            return True
        if (it.get("tu" + m) or 0) > 0:
            return True
    return False


def has_auto(it, cheap=None):
    """Есть ли очередь; cheap - только дешёвая (магнум «веером» за 72% ОВ - не пистолет-пулемёт)."""
    cost = it.get("costAuto")
    tu = it.get("tuAuto") or (cost.get("time") if isinstance(cost, dict) else 0) or 0
    if tu <= 0:
        return False
    return cheap is None or tu <= cheap


# ступень пули по урону: сдвиг на одну ступень от базовой класса, не больше
# ступень по урону патрона: пороги, между которыми лежат ступени 1..5
STEP_EDGES = (27, 40, 55, 90)
# в какие ступени вообще может попасть класс: урон Пираток сильно зависит от бонусов
# бойца, и голое число power у снайперской бывает меньше, чем у автомата
CLASS_STEPS = {"pistol": (1, 2), "smg": (1, 2), "rifle": (2, 3), "sniper": (4, 4), "mg": (3, 4),
               "cannon": (4, 5), "musket": (3, 3), "shotgun": (2, 3), "bow": (2, 2), "launcher": (4, 5),
               "flamer": (3, 3), "thrown": (1, 3), "creature": (1, 5)}


def step_by_power(power, cls):
    lo, hi = CLASS_STEPS[cls]
    if power is None:
        return lo
    step = 1 + sum(power >= e for e in STEP_EDGES)
    return max(lo, min(hi, step))


def classify(t, it, items):
    cats = it.get("categories") or []
    ammo = ammo_of(it, items)
    powers = [a.get("power") for a in ammo if isinstance(a.get("power"), (int, float))]
    power = max(powers) if powers else it.get("power")
    pellets = max([a.get("shotgunPellets") or 0 for a in ammo] + [it.get("shotgunPellets") or 0])
    dts = Counter(d for d in (dtype(a) for a in ammo) if d)
    dt = dts.most_common(1)[0][0] if dts else None
    aoe = any((a.get("blastRadius") or 0) > 0 or ((a.get("damageAlter") or {}).get("FixRadius") or 0) > 0
              for a in ammo)
    if not aoe and dt in ("CONCUSSIVE", "BURN", "CHOKING") and any(a is not it for a in ammo):
        # у патрона радиус -1 = из урона: фугас и зажигательный рвутся
        aoe = any(a.get("blastRadius", -1) == -1 and (a.get("power") or 0) > 0 for a in ammo if a is not it)

    # ---- класс: имя, категория, данные
    cls, key = by_name(t)
    why = f"имя {key}" if cls else ""
    if not cls:
        cls, key = by_category(cats)
        why = f"категория {key}" if cls else ""
    if cls == "shotgun" and pellets <= 1:          # лазерный пистолет Пираток в категории дробовиков
        c2, k2 = by_category([c for c in cats if c != "STR_BAT_CAT_SHOTGUN"])
        cls, why = (c2, f"категория {k2}") if c2 else ("pistol", "без дроби")
    # пушка с картечным снарядом остаётся пушкой: дробь только у попадания этого снаряда
    if pellets > 1 and cls not in ("musket", "launcher", "cannon"):
        cls, why = "shotgun", f"дробь {pellets}"
    if cls is None:
        if not t.startswith("STR_"):
            cls, why = "creature", "оружие существа"
        elif dt in ("CUTTING", "STABBING") and it.get("compatibleAmmo") is None:
            cls, why = "thrown", "холодное"
        elif power is not None:
            cls = "pistol" if power < 30 else "rifle" if power < 60 else "mg" if power < 90 else "cannon"
            why = f"урон {power}"
        else:
            cls, why = "rifle", "нет признаков"
    # уточнение внутри класса по режимам огня
    if cls == "pistol" and has_auto(it, cheap=45) and dt not in ENERGY_DT:
        cls, why = "smg", why + ", есть очередь"
    if cls == "rifle" and not has_auto(it) and (power or 0) >= 70 and (it.get("accuracyAimed") or 0) >= 100:
        cls, why = "sniper", why + ", одиночный мощный"

    flash, base, _ = CLASSES[cls]
    # ---- попадание: у КАЖДОГО патрона своё (картечь у кремнёвого рвётся, пуля нет)
    hits = {}
    for a in ammo:
        hits[a.get("type")] = hit_of(a, cls, base, it)
    main_hit = next(iter(hits.values()))
    if main_hit in ("laser", "plasma", "electric") and flash != "none":
        flash = main_hit                            # лучевое: вспышка своего цвета
    return dict(cls=cls, flash=flash, hit=main_hit, hits=hits, power=power, pellets=pellets, dt=dt or "",
                aoe=aoe, why=why, cats=",".join(c.replace("STR_BAT_CAT_", "") for c in cats))


def hit_of(a, cls, base, gun):
    dt = dtype(a) or dtype(gun)
    power = a.get("power") if isinstance(a.get("power"), (int, float)) else gun.get("power")
    radius = a.get("blastRadius", -1)
    fix = (a.get("damageAlter") or {}).get("FixRadius")
    if (fix or 0) > 0 or (radius or 0) > 0 or (radius == -1 and fix is None and dt in ("CONCUSSIVE", "BURN", "CHOKING")
                                              and a is not gun):
        return "boom"
    if (a.get("shotgunPellets") or 0) > 1:
        return "pellet"
    if cls == "bow":
        return "arrow"
    if dt in ENERGY_DT:
        return ENERGY_DT[dt]
    return f"cal{step_by_power(power, cls)}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mod", default="Piratez", choices=list(MODS))
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    items = load_items(MODS[args.mod])
    guns = {t: it for t, it in items.items() if it.get("battleType") == 1 and is_ranged(it)}
    rows = []
    for t, it in sorted(guns.items()):
        r = classify(t, it, items)
        r["type"] = t
        rows.append(r)
    out = args.out or os.path.join(ROOT, "census", f"weapon_classes_{args.mod}.tsv")
    with open(out, "w", encoding=ENC) as f:
        f.write("type\tclass\tflash\thit\tpower\tpellets\tdamage\taoe\twhy\tcategories\tammo_hits\n")
        for r in rows:
            ah = ",".join(f"{a}={h}" for a, h in r["hits"].items())
            f.write(f"{r['type']}\t{r['cls']}\t{r['flash']}\t{r['hit']}\t{r['power']}\t{r['pellets']}\t"
                    f"{r['dt']}\t{int(r['aoe'])}\t{r['why']}\t{r['cats']}\t{ah}\n")
    print(f"{args.mod}: стрелкового оружия {len(rows)}")
    for c, n in Counter(r["cls"] for r in rows).most_common():
        hits = Counter(r["hit"] for r in rows if r["cls"] == c)
        print(f"  {c:9s} {n:4d}  {CLASSES[c][2]:44s} {dict(hits.most_common(6))}")
    print("  откуда класс:", dict(Counter(r["why"].split(" ")[0] for r in rows)))
    print("->", out)


if __name__ == "__main__":
    main()
