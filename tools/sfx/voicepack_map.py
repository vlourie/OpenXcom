"""Предложение раскладки голосов сценария по бойцам и юнитам Пираток -> tools/sfx/voicepack_map.tsv.

Три вида привязки (как в движке, BattleUnit::prepareUnitResponseSounds):
  soldier - тип бойца (soldiers: voiceSetsMale/voiceSetsFemale); пол у типа Пираток не виден
            (у всех, кроме лупоглазов, одинаковые звуки смерти), поэтому голос на оба пола;
  choice  - только ручной выбор на базе (voiceSets: allowedSoldierTypes + allowedGenders):
            национальные варианты для бойцов с национальными именами;
  unit    - юнит врага (units: voiceSets); слышно, только когда игрок взял юнит под контроль.
Юниты ищутся по английскому имени из «для кого» карточки (Language/en-US.yml Пираток -> units:).

  py -3 tools/sfx/voicepack_map.py         -> таблица + сводка
"""
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import voice_script  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
PZ = ROOT / "Пиратки/Dioxine_XPiratez/user/mods/Piratez"
VALUES = ROOT / ".index/mod/Piratez/rul/values.tsv"
OUT = Path(__file__).with_name("voicepack_map.tsv")

# тип бойца -> (голос мужского пола, голос женского пола); сверено с «для кого» карточек
SOLDIERS = {
    "STR_SOLDIER": ("V001", "V001"),            # Lunatic / Псих - стартовые
    "STR_SOLDIER_S": ("V001", "V001"),          # Hand / Боец
    "STR_SOLDIER_M": ("V002", "V002"),          # Warrior / Воин
    "STR_SOLDIER_V": ("V002", "V002"),          # Veteran / Ветеран
    "STR_SOLDIER_X": ("V003", "V003"),          # Freak / Фрик
    "STR_SOLDIER_W": ("V004", "V004"),          # Weirdgal / Странненькая
    "STR_SOLDIER_R": ("V005", "V005"),          # Repentia / Кающаяся
    "STR_SOLDIER_SLAVE": ("V006", "V006"),      # Slave Soldier / Раб-солдат
    "STR_SOLDIER_PUREBLOOD": ("V006", "V006"),  # Pureblood Soldier
    "STR_SOLDIER_HERO": ("V007", "V007"),       # Hero / Герой
    "STR_SOLDIER_PEASANT": ("V008", "V008"),    # Peasant / Крестьянка
    "STR_SOLDIER_DAMSEL": ("V009", "V009"),     # Damsel / Барышня
    "STR_SOLDIER_HYBRID": ("V010", "V011"),     # Bugeye / Лупоглаз - единственный тип, где пол слышен
    "STR_SOLDIER_LOKNAR": ("V012", "V012"),     # Lokk'Naar
    "STR_SOLDIER_GNOME": ("V013", "V013"),      # Gnome / Гномка
    "STR_SOLDIER_NEKOMIMI": ("V014", "V014"),   # Catgirl
    "STR_SOLDIER_NEKOMIMI_O": ("V015", "V015"),  # Outlaw Catgirl
    "STR_SOLDIER_NEKOMIMI_W": ("V016", "V016"),  # Catwarrior
    "STR_SOLDIER_NEKOMIMI_H": ("V017", "V017"),  # Herbalist
    "STR_SOLDIER_OGRE": ("V018", "V018"),       # Ogre
    "STR_SOLDIER_LAMIA": ("V019", "V019"),      # Lamia (V020 - гражданский o2, у нас юнит)
    "STR_SOLDIER_SYNTH": ("V021", "V021"),      # Syn
    "STR_SOLDIER_DOLL": ("V022", "V022"),       # Soul Doll
    "STR_SOLDIER_SPECTRE": ("V023", "V023"),    # Shade / Дух
    "STR_SOLDIER_CHORT": ("V024", "V024"),      # Chort / Чертовка
    "STR_SOLDIER_KILLBOT": ("V025", "V025"),    # Destroid - сейчас свои звуки 326-342, решает Vitali
    "STR_SOLDIER_XENFORCER": ("V026", "V026"),  # Xenforcer - сейчас свои звуки 343-363, решает Vitali
}
NO_SPEECH = {"STR_SOLDIER_DOGE": "лай (тестовый набор hd_test_voices)", "STR_SOLDIER_BLOODOGE": "лай"}
# бойцы с национальными именами: кому предлагать национальный голос вручную и какого пола
NATION_SOLDIERS = {"М": ["STR_SOLDIER_SLAVE", "STR_SOLDIER_HERO", "STR_SOLDIER_PUREBLOOD"],
                   "Ж": ["STR_SOLDIER_PEASANT", "STR_SOLDIER_DAMSEL"]}
GENDER = {"М": 0, "Ж": 1}


def load_values():
    csv.field_size_limit(10**9)
    sol, units = defaultdict(dict), set()
    with open(VALUES, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            if r["section"] == "soldiers":
                sol[r["id"]][r["field"]] = r["value"]
            elif r["section"] == "units":
                units.add(r["id"])
    return sol, units


def load_en():
    en = {}
    with open(PZ / "Language/en-US.yml", encoding="utf-8-sig") as f:
        for line in f:
            m = re.match(r"\s+(STR_\w+):\s*\"?(.*?)\"?\s*$", line)
            if m:
                en[m.group(1)] = m.group(2)
    return en


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    voices = {v["id"]: v for v in voice_script.parse()}
    sol, units = load_values()
    en = load_en()
    by_name = defaultdict(set)
    for k, val in en.items():
        by_name[val.strip().lower()].add(k)
    rows = []
    for sid, (vm, vf) in SOLDIERS.items():
        assert sid in sol, sid
        if vm == vf:
            rows.append(("soldier", sid, en.get(sid, ""), "оба", vm, voices[vm]["name"]))
        else:
            rows.append(("soldier", sid, en.get(sid, ""), "М", vm, voices[vm]["name"]))
            rows.append(("soldier", sid, en.get(sid, ""), "Ж", vf, voices[vf]["name"]))
    for v in voices.values():
        if v["section"].startswith("Национальные"):
            for sid in NATION_SOLDIERS[v["reg"]]:
                rows.append(("choice", sid, en.get(sid, ""), v["reg"], v["id"], v["name"]))
    unit_voice, miss = {}, []
    for v in voices.values():
        if v["section"].startswith("Национальные"):
            continue
        for n in re.split(r";", v["for"]):
            n = re.sub(r"\s+—.*$", "", n).strip(" .")
            if not n:
                continue
            keys = [k for k in by_name.get(n.lower(), ()) if k in units]
            if not keys and v["id"] > "V024":
                miss.append((v["id"], n))
            for k in keys:
                unit_voice.setdefault(k, (v["id"], n))
    for k, (vid, n) in sorted(unit_voice.items()):
        rows.append(("unit", k, n, "-", vid, voices[vid]["name"]))
    with open(OUT, "w", encoding="utf-8-sig", newline="") as f:
        f.write("kind\ttarget\ttarget_en\tgender\tvoice\tvoice_name\n")
        for r in rows:
            f.write("\t".join(r) + "\n")
    used = {r[4] for r in rows}
    print(f"типов бойцов с голосом {len(SOLDIERS)} из {len(sol)}; без речи: {', '.join(NO_SPEECH)}")
    print(f"юнитов с голосом {len(unit_voice)} из {len(units)}")
    print("голоса без привязки:", ",".join(sorted(set(voices) - used)) or "-")
    print(f"имена карточек врагов, не найденные среди юнитов ({len(miss)}):",
          "; ".join(f"{a} {b}" for a, b in miss))
    print("таблица:", OUT)


if __name__ == "__main__":
    main()
