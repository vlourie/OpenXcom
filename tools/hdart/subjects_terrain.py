# -*- coding: utf-8 -*-
"""Темы наборов через террейны мода.

Наборов плиток в X-Piratez 625, а террейнов, в которых они участвуют, - около 170.
Один и тот же набор (ROADS, URBITS, FOREST) живёт сразу в нескольких террейнах, и
именно террейн задаёт, что это за место. Поэтому тему удобнее писать не на набор,
а на террейн: одно описание закрывает сразу 4-7 наборов.

Порядок разрешения темы в gen_hd.py:
    --subject  ->  SUBJECTS[набор]  ->  тема террейна отсюда  ->  заглушка

Источник связи "набор -> террейн" - .index/mod/Piratez/set_terrains.tsv, его строит
tools/index_mod.py по рулсетам мода. Руками сопоставление НЕ пишем: ровно на этом
я уже ошибся с A_PODS и ACHURCH (см. RAKES.md, R-013).

Описания ниже выверены глазами: каждый набор был распакован и просмотрен листом
кадров. Если добавляешь террейн - сначала посмотри его наборы, потом пиши.

Длина: тема идёт в промпт ПЕРЕД стилевым хвостом, CLIP режет всё после 77 токенов.
Держать в пределах 10-12 слов (gen_hd.py предупредит, если длинно).

ЧТО ПИСАТЬ. Материал и палитру, а не приметные цветные предметы. Тема одна на весь
набор, а кадры в нём разные: то, что названо в теме, модель рисует на КАЖДОМ кадре.
"red stripes, cyan glass" в теме MAGAZYNMAFII дали красные полосы и бирюзовые затёки
на ровном сером полу, где в оригинале не было ничего (см. RAKES.md, R-016).
Приметы можно называть только если они есть на большинстве кадров набора - например
зелёные излучатели в ABASE. Разовая примета идёт не в тему, а в покадровую подсказку
(hints.py).

ДВЕ ЧАСТИ ЧЕРЕЗ « | ». Слева поверхности, справа предметы. В полы идёт только левая часть,
в объекты - обе. Это нужно там, где террейн смешивает пол и обстановку: в GDX_HOUSE есть и
плиточные полы (набор GDXOPSFLOORS), и садовая зелень (набор FLORASET). Пока тема была
единой, на ровный сиреневый пол ложились зелёные и лиловые разводы - модель честно рисовала
названные кусты. Без разделителя тема идёт и туда, и туда, как раньше.
"""

import os

# террейн -> тема. Отсортировано по числу кадров-полов, которые тема закрывает
# (tools/subject_plan.py, колонка floors).
TERRAIN_SUBJECTS = {
    # --- 1-10: самые крупные по площади пола ---
    "PORTTFTD6": "sea port: dark asphalt road, concrete kerbs, worn road paint, wet sand",
    "BEACH_SAVANNA": "tropical beach and savanna: pale sand, shells, dry earth, green scrub tufts",
    "FORESTWASTE": "dead forest: reddish-brown dry soil, dead twigs, rotten stumps, fallen logs",
    "FORESTSNOW": "snowy forest: white snow, brown mud patches, snowy stumps, bare shrubs",
    "STYXSWAMP": "lush swamp: dark green grass, bright green reeds, pink flowers, wet mud",
    "FORESTSWAMP": "wet forest: green grass, marsh water, pines, bushes, mud",
    "TEC_BASE_TUNNELS": "tech tunnel: grey rock walls, dark steel panels, worn concrete floor, dust",
    "POLAR_SOLID": "polar: white snow, frozen brown dirt, blue ice slabs, dark water",
    "NECROPOLIS": "black cave: dark speckled rock walls, grey rubble floor, stone debris",
    "GDX_HOUSE": "garden house: tiled floor, painted concrete, short grass | green bushes, fruit trees, wooden fence",
    # --- 11-20 ---
    "WHITEBASE_INFLIL1": "white base: orange rubber floor, white concrete slabs, grey tiles, short grass",
    "WHITE_CASTLE": "white castle: pale marble floor, white stone blocks, green ivy",
    "THULEBASE": "arctic bunker: metal grating floor, grey steel walls, painted steel, wooden crates",
    "CITY_OF_THE_DEAD_SEWERS": "jungle ruins: pale stone blocks, sandy floor, green vines, grey rubble",
    "CYDSUBWAY": "underground dig: brown earth floor, dirt walls, packed soil, loose stones",
    "SACREDCAVE": "earth cave: brown soil walls, dirt floor, damp earth, mineral crust",
    "DARK_TOWER": "ashen waste: black ash ground, dark grey rock, charred boulders, grey snow",
    "LAMIA_VILLAGE": "shrine: mossy green ground, pale golden sand floor, grey stone brick, cave rock",
    "RICE_FARM": "rice farm: flooded paddy water, mud dykes, green shoots, wooden barn floor",
    "URBANJUNKUFO": "farmland: crop fields, hedges, dirt track, grass, fruit trees",
    # --- 21-30 ---
    "STYXTOWER": "grey stone keep: flagstone floor, grey block walls, dark stone stairs",
    "UCITY": "seabed: pale sand, green algae mesh, silt, alien hull plating",
    "EMANSION_MAG": "mansion: marble tiles, wood parquet, coloured carpets, pool water, garden",
    "CRUISE_LINER_ACADEMY": "cruise liner deck: wooden planking, painted steel floor, carpet, white bulkheads",
    "DESERTREFINERY": "desert refinery: sand, cracked dirt, rusty steel sheets, concrete pads",
    "GOTHIC_LANDING": "stone church: grey block walls, worn flagstone floor, dressed stone, wooden pews",
    "NUKE_ZONE": "nuked ruin: grey ash rubble, burnt debris, cracked concrete",
    "RURAL": "village: dirt road, grass, wooden barn floor, farm yard",
    "EMANSION": "mansion: marble tiles, wood parquet, coloured carpets, garden lawn",
    "GOVT_BASE_DEFENSE": "military base: concrete apron, painted road, grass verge, bunker floor",
    # --- 31-40 ---
    "JUNGLETEMPLE": "jungle temple: mossy stone floor, wet earth, green vines, grey rocks",
    "URBANLUX": "luxury city: clean asphalt, paving slabs, marble plaza, trimmed lawn",
    "SUNKURBAN": "sunken city: silted asphalt, seabed sand, algae-covered concrete",
    "U_PLANET_VOID": "void planetoid: dark blue-grey rock, glowing golden energy cracks, blue crystals",
    "STORMMOUNTAIN": "mountains: grey rock, scree, snow patches, frozen dirt",
    "CHURCHBASE": "alien church: golden glowing panels, orange energy pools, green light emitters",
    "UBASE": "alien base: dark metal floor, glowing panels, smooth curved walls",
    "ABASE": "alien base floor: pale panels, cyan energy pools, green light emitters",
    "NINJA_BASE_OUTPOST": "ninja outpost: white painted road, concrete floor, tatami, dark tech panels",
    "WINTER_WALL": "winter industrial: grey slush road, concrete yard, dirty snow, steel plates",
    # --- дальше по убыванию; сюда же те, где имя террейна совпадает с именем набора ---
    "MAGAZYNMAFII": "mafia warehouse: bare concrete floor, dark grey steel walls, oil stains, crates",
    "JUNGLE": "jungle: wet earth, tropical trees, palms, dense green bushes, mud",
    "FOREST": "forest: green grass, pine trees, bushes, dirt track, rocks, logs",
    "URBAN": "city street: asphalt road, pavement, concrete, shop fronts, grass verge",
    "MOUNT": "mountains: grey rock, scree, snow patches, frozen dirt, cliffs",
    "DESERT": "desert: sand dunes, cracked dry earth, rocks, dry bushes",
    "CULTA": "farmland: ploughed field, crops, grass, dirt track, hedges, fruit trees",
    "INDUSTRIALSLUM": "industrial slum: cracked asphalt, oil-stained concrete, rusty steel, rubble",
    "CARGO_LINER": "cargo ship deck: painted steel floor, rusty plating, sea water | wooden crates",
    "CRUISE_LINER": "cruise liner deck: wooden planking, painted steel floor, carpet, white bulkheads",
    "ISLANDURBAN": "island town: pale sand, paved street, concrete, palms, sea water",
    "GDX_PRISON": "prison block: grey concrete floor, steel bars, painted walls, drain grates",
}


# Вес террейна = его место в TERRAIN_SUBJECTS (dict помнит порядок вставки), а порядок
# там - по числу кадров-полов. Набор вроде ROADS живёт в десятке террейнов; берём тот,
# ради которого тема и писалась, то есть самый весомый.
_RANK = {t: i for i, t in enumerate(TERRAIN_SUBJECTS)}


def load_set_terrains(path):
    """set_terrains.tsv -> {"НАБОР.PCK": ["TERRAIN", ...]}. Пустой dict, если файла нет."""
    out = {}
    if not path or not os.path.exists(path):
        return out
    with open(path, encoding="utf-8-sig") as f:
        head = f.readline()
        if not head:
            return out
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 2:
                continue
            name = parts[0].strip()
            if not name:
                continue
            key = name.upper()
            if not key.endswith(".PCK"):
                key += ".PCK"
            out[key] = [t.strip() for t in parts[1].split(",") if t.strip()]
    return out


def default_index_path(start=None):
    """.index/mod/Piratez/set_terrains.tsv рядом с корнем репозитория."""
    here = os.path.abspath(start or __file__)
    d = os.path.dirname(here)
    for _ in range(6):
        p = os.path.join(d, ".index", "mod", "Piratez", "set_terrains.tsv")
        if os.path.exists(p):
            return p
        nd = os.path.dirname(d)
        if nd == d:
            break
        d = nd
    return ""


def subject_for_set(set_name, table=None, tsv_path=None):
    """Тема набора через его террейны, или (None, None).

    Возвращает (тема, террейн). Если набор в нескольких террейнах - берётся самый
    весомый из тех, для которых тема написана (см. _RANK).
    """
    if table is None:
        table = load_set_terrains(tsv_path or default_index_path())
    key = set_name.upper()
    if not key.endswith(".PCK"):
        key += ".PCK"
    have = [t for t in table.get(key, []) if t in TERRAIN_SUBJECTS]
    if not have:
        return None, None
    # имя набора == имя террейна: набор сделан ровно под него, он и главный
    stem = key[:-4]
    for t in have:
        if t == stem:
            return TERRAIN_SUBJECTS[t], t
    best = min(have, key=lambda t: _RANK[t])
    return TERRAIN_SUBJECTS[best], best


# Последний рубеж: по имени набора, когда террейн неизвестен (140 наборов вообще не
# упомянуты в terrains: - это плитки кораблей, НЛО и отдельных карт). Порядок важен:
# берётся ПЕРВОЕ совпадение, поэтому частное идёт раньше общего - например MARSEC
# раньше C_INT (иначе MARSEC_INT_2 уедет в "корабль игрока"), SPACESTATION раньше
# STATION, CULTIVAT раньше CULT. Тест на пересечения - tools/subject_report.py.
NAME_HINTS = [
    # --- пещеры: форма одинаковая, отличается цвет (сверено листами) ---
    ("CAVEMEAT", "flesh cave: violet organic walls, magenta fleshy growths, brown membrane floor"),
    ("CAVEBONE", "bone cave: pale beige bone-coloured rock walls, tan gravel floor"),
    ("CAVEAQUA", "aquamarine cave: turquoise crystal rock walls, cyan gravel floor"),
    ("CAVERED", "red cave: crimson rock walls, orange glowing cracks, dark red gravel"),
    ("CAVEPINK", "pink cave: rose-coloured rock walls, pale pink gravel floor"),
    ("CAVEMARS", "martian cave: rust-red rock walls, orange dust floor"),
    ("CAVEDOOM", "hell cave: dark red rock, black scorch marks, glowing embers"),
    ("CAVE", "cave: rock walls, rubble floor, damp stone, gravel"),
    # --- корабли игрока (C_*) и корпоративные (MARSEC) ---
    ("MARSEC", "corporate ship interior: red painted panel walls, dark metal deck plating"),
    ("UAC_", "industrial base: stained concrete floor, dark steel panels | pipes, grates"),
    ("C_EXT_ROOF", "ship roof plate: smooth painted metal, plain flat surface, panel seams"),
    ("C_EXT_WALL", "ship hull wall: painted metal plating, panel seams, rivets"),
    ("C_EXT", "ship hull: painted metal plating, panel seams, rivets"),
    ("C_INT", "ship interior: grey metal deck plating, bulkheads, consoles"),
    ("C_WALL", "ship bulkhead: painted metal plating, panel seams, rivets"),
    ("C_BITS", "ship fittings: metal deck plating | consoles, pipes, lockers"),
    ("LIGHTNIN", "sleek craft hull: dark painted metal plating, ramp, panel seams"),
    ("AVENGER", "advanced craft hull: alien alloy plating, ramp, panel seams"),
    ("RET_", "retro spaceship interior: grey-blue metal panels, gold trim, consoles"),
    ("DREADSHIP", "warship interior: dark steel deck, heavy bulkheads, riveted plating"),
    # --- НЛО и подлодки пришельцев ---
    ("XOPSUFO", "alien craft interior: dark metal deck plating, glowing panels, curved walls"),
    ("UFOAA", "alien craft interior: dark metal deck plating, glowing panels, curved walls"),
    ("UFOL", "alien craft hull: dark grey metal plating, curved walls, glowing seams"),
    ("USO", "alien submarine interior: wet metal deck, glowing panels, curved hull"),
    ("U_WALL", "alien craft wall: metal panels, doors, glowing alien technology"),
    ("U_EXT", "alien craft hull: dark grey metal plating, curved walls"),
    ("U_BITS", "alien craft parts: power source, navigation console, glowing panels"),
    ("U_DISEC", "alien examination room: metal tables, tanks, instruments"),
    ("U_BASE", "alien base: dark metal floor, glowing panels, smooth curved walls"),
    ("DREAD_", "warship interior: dark steel deck, heavy bulkheads, riveted plating"),
    # --- станции, метро, подземка ---
    ("SPACESTATION", "space station interior: white-grey metal walls, panel seams, metal deck"),
    ("COMPLEX", "moon base: grey metal deck, panel walls, panel seams"),
    ("STATION", "space station: beige panel walls, grey tech panels, panel seams"),
    ("METRO", "metro tunnel: brown brick walls, red brick, dark concrete floor, dirt"),
    ("SGR_", "underground station: grey metal floor, brown earth walls, packed soil, worn concrete"),
    # --- руины и гробницы ---
    ("CRYPTEK", "crypt: glowing cyan floor slabs, red stone walls, dark portal"),
    ("MUMMY", "stone ruins: grey carved stone blocks, rubble, worn steps"),
    ("ICEKING", "frozen ruins: pale lavender ice-stone blocks, rubble, worn steps"),
    ("EARTHTEMPLE", "dark temple: black stone floor, dark grey walls, tan trim"),
    ("PYRAMID", "dark pyramid: black stone blocks, sand floor, carved walls"),
    ("SHOGG", "village ruins: weathered stone blocks, dirt floor, broken walls"),
    ("MEDIEVAL", "medieval town: flagstone street, timber walls, thatch, dirt"),
    # --- военные и базы X-Com ---
    ("MILWARE", "military warehouse: concrete floor, grey lockers, crates, missile racks"),
    ("MILBARR", "military barracks: concrete floor, rust-orange walls, dirt yard"),
    ("MIL", "military post: concrete floor, painted steel walls, crates"),
    ("XBASE", "military base interior: concrete floor, metal walls, doors, machinery"),
    ("XB", "base barracks: wooden plank walls, painted steel, sandy floor, shelves"),
    ("XARMY", "military base interior: concrete floor, metal walls, crates"),
    ("DOOM_", "hell base: stained concrete floor, dark steel panels, glowing embers"),
    ("GOVT", "government building: polished floor, painted walls, official decor"),
    # --- ферма, город, прочее ---
    ("CULTIVAT", "farmland: ploughed field, crops, grass, dirt track, hedges"),
    ("CULTEXTRA", "farm market: produce stalls, flowers, brown earth, ash patches"),
    ("CULT", "rural buildings: wooden plank walls, grey concrete, dirt yard"),
    ("BARN_", "farm barn: wooden plank walls, hay, dirt floor, wooden doors"),
    ("ASYLUM", "asylum grounds: grass, dirt path, white fence, grey stone wall"),
    ("ARENA", "arena: sandy floor, wooden barriers, water channel, grass patch"),
    ("GRUNGE", "dirty pit: rusty brown rims, grey gritty surface, worn metal"),
    ("TAVERN", "tavern: wooden floor, timber walls, barrels, tables"),
    ("BRICKBAR", "brick bar: brick walls, wooden floor, bar counter, stools"),
    ("CAFE", "cafe: tiled floor, glass front, tables, chairs"),
    ("ATLANVILLA", "seaside villa: pale marble floor, white walls, pool water"),
    ("DAWN", "city props: asphalt, pavement, benches, lamps, hydrants"),
    ("WEST", "wild west town: dusty boardwalk, sandy street, timber buildings"),
    ("MOORINGS", "quay: wooden decking, concrete edge, bollards, sea water"),
    ("MANHOLE", "street drain: asphalt, concrete rim, metal grate"),
    ("SANDS", "sand: dry pale sand, small stones, wind ripples"),
    ("TECHFLOOR", "tech floor: metal deck plating, panel seams, cable runs"),
    ("40K", "war-torn city: cracked rubble, broken concrete, twisted steel"),
    ("ORKP", "scrap fort: rusty steel sheets, scrap plating, mud"),
    ("MADDECOR", "wasteland junk: scrap metal, tyres, barrels, cracked dirt"),
    # --- техника и транспорт ---
    ("LITTLE_BIRD", "helicopter: dark metal hull panels, cockpit glass, cabin floor"),
    ("HUEY", "helicopter: olive metal hull panels, cockpit glass, cabin floor"),
    ("HIND", "helicopter: olive metal hull panels, cockpit glass, cabin floor"),
    ("MI8", "helicopter: olive metal hull panels, cockpit glass, cabin floor"),
    ("TAUROX", "armoured truck: olive steel plating, road wheels, hatches"),
    ("STRYKER", "armoured car: olive steel plating, road wheels, hatches"),
    ("PREDATOR", "battle tank: painted steel plating, tracks, turret hatches"),
    ("NKF", "armoured carrier: painted steel plating, road wheels, hatches"),
    ("ASSAULTBIKE", "motorbike: painted metal, tyres, chrome pipes"),
    ("CADILLAC", "classic car: glossy painted metal, chrome trim, tyres"),
    ("DELOREAN", "sports car: brushed steel panels, glass, tyres"),
    ("XCARS", "parked cars: painted metal, glass, tyres, asphalt"),
    ("TRITON", "submarine interior: wet metal deck, round hatches, pipes"),
    ("BOAT", "boat: wooden decking, painted hull plating, rope, sea water"),
    ("LIFTER", "cargo lifter deck: painted steel floor, crates, hatches"),
    ("KITSUNE", "small craft interior: metal deck plating, seats, hatch"),
    # --- родовые, в самом конце ---
    ("FREIGHTER", "cargo ship interior: painted steel deck, bulkheads, crates, pipes"),
    ("TRANSPORT", "transport aircraft interior: metal deck plating, seats, ramp, bulkheads"),
    ("PLANE", "aircraft interior: metal deck plating, seats, ramp, bulkheads"),
    ("HANGAR", "hangar: painted concrete floor, worn floor paint, steel walls, machinery"),
    ("MOUNTSNOW", "snowy mountain: white snow, grey rock, frozen dirt, bare shrubs"),
    ("MOUNTSAND", "sandy mountain: pale sand, eroded rock, dry dirt, sparse scrub"),
    ("MOUNTWASTE", "dead highland: grey ash soil, cracked rock, dead scrub"),
    ("MOUNTROCK", "rocky highland: eroded grey rock, gravel, dry dirt"),
    ("MOUNTGRASS", "green highland: grass slopes, grey rock outcrops, dirt track"),
    ("MOUNTTROP", "tropical highland: wet earth, green undergrowth, mossy rock"),
    ("MOUNTMUD", "muddy highland: wet brown mud, slick rock, puddles"),
    ("MOUNTMOON", "moon surface: grey dust, craters, pale rock, no vegetation"),
    ("MOUNT", "mountains: grey rock, scree, snow patches, frozen dirt"),
    ("NEOJUNGLE", "alien jungle: violet-green undergrowth, wet earth, strange trees"),
    ("BLACKJUNGLE", "black jungle: dark soil, near-black foliage, wet roots, mud"),
    ("JUNGLE", "jungle: wet earth, tropical trees, palms, dense green bushes, mud"),
    ("FORESTSNOW", "snowy forest: white snow, brown mud patches, snowy stumps, bare shrubs"),
    ("FORESTSWAMP", "wet forest: green grass, marsh water, pines, bushes, mud"),
    ("FOREST", "forest: green grass, pine trees, bushes, dirt track, rocks, logs"),
    ("CATACOMB", "catacombs: dry stone floor, carved rock walls, bone niches, dust"),
    ("SIETCH", "desert cave dwelling: sand floor, carved rock walls, woven mats"),
    ("MUICE", "ice cavern: blue ice floor, frozen rock, snow drifts"),
    ("MUCONCRETE", "concrete bunker: grey concrete floor, stained walls, rubble"),
    ("DESERT", "desert: sand dunes, cracked dry earth, rocks, dry bushes"),
    ("POLAR", "polar: white snow, frozen brown dirt, blue ice slabs, dark water"),
    ("SEA", "seabed: pale sand, green algae, coral, silt"),
    ("URBAN", "city street: asphalt road, pavement, concrete, shop fronts, grass verge"),
    ("ROAD", "road: dark asphalt, concrete kerbs, painted markings, gravel verge"),
    ("BASE", "military base interior: concrete floor, metal walls, doors, machinery"),
]


def subject_by_name(set_name):
    """Тема по имени набора, если террейн ничего не дал. (тема, образец) или (None, None)."""
    key = set_name.upper()
    if key.endswith(".PCK"):
        key = key[:-4]
    for pat, subj in NAME_HINTS:
        if pat in key:
            return subj, pat
    return None, None
