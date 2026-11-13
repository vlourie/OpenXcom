# Таблица погоды боя hd/weather.txt: terrain -> биом (docs/research/battle-weather-2026-11-11.md, §2).
# Читает terrains рулсетов Пираток (только чтение) и делит по имени и enviroEffects; неоднозначное и внутреннее -
# NONE (погоды нет). Движок (Map::hdWeatherBiome) берёт биом terrain, из которого большинство блоков карты.
#   py -3.13 tools/hdart/weather_table.py            - пишет в обе копии мода hd
#   py -3.13 tools/hdart/weather_table.py --print    - только показать
import argparse
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RULES = ROOT / "Пиратки" / "Dioxine_XPiratez" / "user" / "mods" / "Piratez" / "Ruleset"
OUTS = [ROOT / "user" / "mods" / "hd" / "hd" / "weather.txt",
        ROOT / "Пиратки" / "Dioxine_XPiratez" / "user" / "mods" / "hd" / "hd" / "weather.txt"]

# порядок важен: первое совпадение решает
NONE_WORDS = ["BASE", "CAVE", "CATACOMB", "METRO", "SEWER", "SUBWAY", "TUNNEL", "INTERIOR", "LAB", "BUNKER", "PRISON",
              "DUNGEON", "MINE", "CRYPT", "MAZE", "_VR", "VOID", "SPACE", "MOON", "MARS", "CYDONIA", "ORBIT", "ASTEROID",
              "AQUA", "UNDERWATER", "SEABED", "DEEP", "SHIP", "CARGO", "LINER", "STATION", "HQ", "CASTLE",
              "PALACE", "TOWER", "MANSION", "TAVERN", "ARENA", "HIDEOUT", "HIVE", "LAIR", "WAREHOUSE", "FACTORY",
              "CHURCH", "HALL", "VAULT", "MEAT", "ASYLUM", "TRAIN", "BOAT", "SUB_", "VESSEL"]
RULES_BY_NAME = [
    ("SNOW", ["SNOW", "ICE", "ARCTIC", "POLAR", "WINTER", "TUNDRA", "FROZEN", "GLACIER"]),
    ("DESERT", ["DESERT", "DUNE", "SAND", "MESA", "COLORADO", "CANYON", "BADLAND"]),
    ("JUNGLE", ["JUNGLE", "TROPIC", "RAINFOREST"]),
    ("SWAMP", ["SWAMP", "MARSH", "BOG", "FEN"]),
    ("FOREST", ["FOREST", "WOOD", "TAIGA"]),
    ("SEA", ["SEA", "PORT", "ISLAND", "BEACH", "COAST", "HARBO", "DOCK", "SHORE", "LAKE", "RIVER"]),
    ("WASTE", ["WASTE", "NUKE", "RAD", "ASH", "ERODED", "APOC", "RUIN", "CHEM", "TOXIC", "SCRAP", "JUNK", "DUMP"]),
    ("CITY", ["URBAN", "CITY", "TOWN", "STREET", "MALL", "SUBURB", "VILLAGE", "SETTLEMENT", "SLUM", "DISTRICT"]),
    ("STEPPE", ["RURAL", "PLAIN", "FARM", "FIELD", "STEPPE", "SAVANNA", "MOUNT", "HILL", "CULTIV", "GRASS", "MEADOW",
                "PRAIRIE", "VALLEY", "ROCK", "CRATER"]),
]
ENVIRO_NONE = ("SPACE", "MOON", "MARS", "CYDONIA", "SEA", "SHADOWLANDS", "PSYCHEDELIC", "MAGMA", "LABYRINTH")


def terrains():
    """(имя, enviroEffects) всех terrains рулсетов Пираток."""
    out = {}
    for path in sorted(RULES.glob("*.rul")):
        section = None
        name = None
        for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            top = re.match(r"^([A-Za-z]\w*):", line)
            if top:
                section = top.group(1)
                name = None
                continue
            if section != "terrains":
                continue
            m = re.match(r"^  - name: *(\S+)", line)
            if m:
                name = m.group(1)
                out.setdefault(name, "")
                continue
            m = re.match(r"^    enviroEffects: *(\S+)", line)
            if m and name:
                out[name] = m.group(1)
    return out


def has(up, word):
    """Короткое слово (до трёх букв: ICE, RAD, ASH, BOG, LAB) - только целой частью имени: RICE_FARM - не лёд."""
    if len(word.strip("_")) <= 3:
        return word.strip("_") in up.split("_")
    return word in up


def biome(name, enviro):
    up = name.upper()
    env = enviro.upper()
    if any(w in env for w in ENVIRO_NONE) and "SEA_SURFACE" not in env:
        return "NONE"
    if "DUST_STORM" in env:
        return "DESERT"
    if "SEA_SURFACE" in env:
        return "SEA"
    for word in NONE_WORDS:
        if has(up, word):
            return "NONE"
    for b, words in RULES_BY_NAME:
        if any(has(up, w) for w in words):
            return b
    if "COLD" in env:
        return "SNOW"
    if "HEAT" in env:
        return "STEPPE"
    if "IRRADIATED" in env or "NUKEZONE" in env or "ACID" in env:
        return "WASTE"
    return "NONE"


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--print", action="store_true")
    o = a.parse_args()
    t = terrains()
    rows = []
    for name in sorted(t):
        b = biome(name, t[name])
        cold = "COLD" in t[name].upper() and b in ("CITY", "STEPPE", "FOREST", "SWAMP", "SEA", "WASTE")
        rows.append((name, b + ("_COLD" if cold else ""), t[name]))
    head = ["# hd/weather.txt: the weather of a battle by its ground (option 'Weather in battle', picture only).",
            "# A line is NAME BIOME: a terrain (the one most of the map's blocks come from) or a mission type. BIOME is NONE",
            "# (no weather), CITY, STEPPE, SNOW, SEA, WASTE, DESERT, JUNGLE, FOREST, SWAMP; _COLD lets snow fall instead of rain.",
            "# No line - no weather. Made by tools/hdart/weather_table.py from the terrains of Piratez; edit by hand."]
    body = [f"{n} {b}" for n, b, _ in rows]
    count = Counter(b for _, b, _ in rows)
    print("terrains:", len(rows), " ".join(f"{k}={v}" for k, v in sorted(count.items())))
    if o.print:
        for n, b, e in rows:
            print(f"{n:40} {b:12} {e}")
        return
    text = "\n".join(head + body) + "\n"
    for out in OUTS:
        out.write_text(text, encoding="utf-8-sig", newline="\n")
        print("ok:", str(out).encode("ascii", "replace").decode())


if __name__ == "__main__":
    main()
