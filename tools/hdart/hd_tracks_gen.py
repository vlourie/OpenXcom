# -*- coding: utf-8 -*-
"""hd/tracks.txt (тикет XP-000421, вариант B): вид кровавого следа по броне - из рулсетов Пираток (только чтение).

Строка таблицы: "ИМЯ вид"; ИМЯ - точный тип брони или префикс со звёздочкой; вид - boot (армейский протектор),
bare (босая стопа), wheel (колёса), track (гусеницы), paw (лапы), none (следа нет). Запасное правило игры без строки
(HdFx::trackKind): MT_FLY/MT_FLOAT/MT_SLIDE/MT_SINK - none; размер 2: drawingRoutine 2 и 11 - track, 5 - paw; иначе boot.
Скрипт пишет строку только там, где вид брони расходится с запасным правилом (повторяет его в fallback()).

  python tools/hdart/hd_tracks_gen.py            # печать сводки и запись user/mods/hd/hd/tracks.txt
  python tools/hdart/hd_tracks_gen.py --copy     # то же + копия в Пиратки/Dioxine_XPiratez/user/mods/hd/hd (побайтно равна)
  python tools/hdart/hd_tracks_gen.py --check    # только сводка и сверка с уже лежащими файлами
"""
import argparse
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from tracks_load import ROOT, load_armors  # noqa: E402

MT_WALK, MT_FLY, MT_SLIDE, MT_FLOAT, MT_SINK = 0, 1, 2, 3, 4

# --- правила по именам (проверены по данным: movementType, size, drawingRoutine, имена предметов в Language/en-US) ---
# голые и полуголые: имена брони прямо говорят (NUDE, BIKINI, SWIMSUIT, LINGERIE_*, THONG, LOINCLOTH, TOPLESS)
BARE = re.compile(r"NUDE|BIKINI|SWIMSUIT|SWIM_|_SWIM|LINGERIE|THONG|LOINCLOTH|TOPLESS|MONOKINI|^STR_PIR_NUDE")
# колёса: бронеавтомобили, мотоцикл, квадроцикл
WHEEL = re.compile(r"^(STR_)?(ACAR_|ARMORED_CAR_|BIKE_ARMOR|QUAD_ARMOR)")
# гусеницы: танки (в т.ч. Think Tank и биотанк)
CRAWLER = re.compile(r"^(STR_)?(PIRATE_TANK_TURRET|TIGER_TURRET|TANK_ARMOR|TANK_MSDF|TANKP_|BOMBARD_|BIOTANK_|MASTERMIND_)")
# следа нет: неподвижные башни и орудия, камеры, дроны-парители, слизь и подобное
NONE = re.compile(
    r"TURRET|PILLBOX|FIELD_GUN|SENTRY_LAUNCHER|CAMERA_|BOSSBRAIN|HOLOGAL|CYBERDISC|"
    r"^(STR_)?(OOZE_|MAGGOT_|SLIMEGAL_|SILACOID_|CELATID_|TENTACLEHIVE_|TREE_OF_LIFF|LAMIA_|ERIDIAN_ARMOR)")
# лапы: звери и шагоходы
PAW = re.compile(
    r"^(STR_)?(DOGE_|DOG_|BLOODOGE_|DOGG_|CYBERDOG_|LOKNAR_PET|MONGORN_|GIANT_RAT|BLACK_CAT|WHITERABBIT|CHRYSSALID_|"
    r"CHUPACABRA_|GIANT_BEETLE|KRAB_|MEGASCORPION|GIANTSPIDER|CYBERSCARAB|SPIDERGIRL|WEREWOLF|CLICKOR|"
    r"WOLVERIN_|XEC_|HYENA_RIDER|REAPER_|SECTOPOD_|CYBERPOD_|MEGAZOMBIE|BOOMOSAURUS|SHAMBLER|BULLFROG|"
    r"DOOM_ARMOR_[689]$)")


def kind_of(t, a):
    """Вид следа по имени и данным брони."""
    mt = a.get("movementType") or 0
    if mt in (MT_FLY, MT_FLOAT, MT_SINK):
        return "none"
    if WHEEL.search(t):
        return "wheel"
    if CRAWLER.search(t):
        return "track"
    if NONE.search(t):
        return "none"
    if PAW.search(t):
        return "paw"
    if BARE.search(t) and (a.get("size") or 1) == 1:
        return "bare"
    return "boot"


def fallback(a):
    """Запасное правило игры без строки (то же в HdFx::trackKind)."""
    mt = a.get("movementType") or 0
    if mt in (MT_FLY, MT_FLOAT, MT_SLIDE, MT_SINK):
        return "none"
    if (a.get("size") or 1) == 2:
        dr = a.get("drawingRoutine") or 0
        return "track" if dr in (2, 11) else "paw" if dr == 5 else "boot"
    return "boot"


HEAD = """# hd/tracks.txt: the look of a bloody footprint by the one who walks (option 'Bloody footprints'; picture only).
# A line is NAME kind: the type of an armour (exact), or a prefix ending in '*' (the longest prefix wins, an exact name beats it).
# kind: boot (army tread), bare (a bare foot with toes), wheel (two wheel ruts), track (two caterpillar tracks), paw (pad and claws), none (no footprint).
# A 2x2 unit lays its mark on all four tiles it covers: ruts and tracks run the length of its walk, a walker leaves big prints.
# No file, or no line for an armour: the rule of the game - flying, floating and sliding (movementType 1, 3, 2) leave none; size 2 with
# drawingRoutine 2 or 11 is a track, with 5 a paw; everything else is a boot (the log says which: 'HD tracks: armour').
# Written by tools/hdart/hd_tracks_gen.py from the Piratez rulesets: only the armours that differ from that rule have a line. Edit by hand if needed.
"""

TITLES = [
    ("wheel", "wheeled machines: armoured cars, the assault bike, the quads"),
    ("track", "tracked machines: tanks, the bombard, the biotank, the think tank"),
    ("paw", "walkers and beasts on paws: mecha suits, XEC suits, reapers, sectopods, dogs, spiders, beetles and the like"),
    ("bare", "bare feet: the nude, bikinis, swimsuits, lingerie, thongs and loincloths"),
    ("none", "no footprint: turrets and guns, slime and snakes (those that would walk by the rule), discs"),
    ("boot", "army tread where the rule of the game would say otherwise (sliders in suits, loaders and so on)"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--copy", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    arm = load_armors()
    kinds = {t: kind_of(t, a) for t, a in arm.items()}
    lines = {k: [] for k, _ in TITLES}
    for t, a in sorted(arm.items()):
        if kinds[t] != fallback(a):
            lines[kinds[t]].append(t)
    out = [HEAD]
    for k, title in TITLES:
        if lines[k]:
            out.append("# " + title)
            out.extend("%s %s" % (t, k) for t in lines[k])
            out.append("")
    text = "\n".join(out)
    total = Counter(kinds.values())
    print("armours: %d; by kind: %s" % (len(arm), dict(total)))
    print("lines in the table: %s (the rest follow the rule of the game)" % {k: len(v) for k, v in lines.items()})
    # те, где правило даёт то же самое, что и таблица (без строки): сколько
    same = Counter(kinds[t] for t, a in arm.items() if kinds[t] == fallback(a))
    print("on the fallback rule: %s" % dict(same))
    targets = [ROOT / "user" / "mods" / "hd" / "hd" / "tracks.txt",
               ROOT / "Пиратки" / "Dioxine_XPiratez" / "user" / "mods" / "hd" / "hd" / "tracks.txt"]
    data = ("﻿" + text).encode("utf-8")
    if args.check:
        for p in targets:
            print(p, "same" if p.exists() and p.read_bytes() == data else "DIFFERENT or missing")
        return
    targets[0].write_bytes(data)
    print("wrote", targets[0], len(data), "bytes")
    if args.copy:
        targets[1].write_bytes(data)
        print("wrote", targets[1])


if __name__ == "__main__":
    main()
