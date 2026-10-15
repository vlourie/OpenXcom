# Корабли и НЛО в бою: постановка, опоры корпуса, группы террейнов (для модели обрушения)
Дата: 2026-10-07 | Уверенность: высокая по п.1-5 и по группам 2-3; средняя по группе 4 (подземные - по именам, скриптам и наборам, а не по свойству движка); низкая по 13 помеченным террейнам группы 1 и по 5 группы 4

## Краткий ответ
1. Корабль и НЛО в бою - это не «здание на земле»: они грузятся как карта-блок поверх уже собранной карты (`addCraft`/`addUFO`), у корпуса своя высота z (`_craftZ`/`_ufoZ`) и свой пол z=0 блока. У 25 из 86 блоков кораблей игрока (`craft`) и 12 из 161 блока кораблей-НЛО корпус стоит на «ногах» (редкие колонны и рампы на z=0 с бронёй 255), у одного (VES_300) z=0 пуст вовсе. Правило v1 «нет связи с землёй по частям - падает» помечает «неопёртыми» 13,0 процента частей выше z=0 у `craft` и 7,7 у НЛО-судов, и почти все эти пометки ложные: корпус - один связный объём (проверено, п.6).
2. Разбитый НЛО (`CRASHED`) движок не меняет: карта та же, что у севшего. Единственная разница - `explodePowerSources` (источники питания взрываются с шансом 75 процентов каждый) и тип миссии `STR_UFO_CRASH_RECOVERY`. Структурного обрушения в движке нет вовсе.
3. Броня 255 (неразрушима взрывом): у `craft` 21,6 процента частей (24 из 86 блоков - 90 процентов и больше; это ноги, шасси, рампы и целые корпуса вертолётов и самолётов), у НЛО-судов 1,3, у НЛО-зданий 1,0. На орбитальных станциях 35-98 процентов, и там это невидимая плита вакуума.
4. Колонка `kind=ufo` в переписи - это не только суда: 76 из 287 блоков - **здания-локации** (STR_LOC_*, HTHOUSE, SURVHOUSE, BANDIT_CAMP...), 161 - суда и техника. Разделение - `ships/ship_groups.tsv`.
5. Классификация 249 террейнов (`ships/terrain_groups.tsv`): наземные постройки 134, суда и аппараты на земле 4, суда без земли 19, подземные 66, без конструкций 26. Модель «нет опоры снизу - падает» разумна только для группы 1; в группе 3 земли нет по построению (z=0 - невидимая неразрушимая плита или палуба над пустотой/водой), в группе 4 потолок держит порода.

## Детали

### 1. Как корабль и НЛО ставятся в бой
- Порядок: блоки карты по mapscript, затем `addUFO` и `addCraft` (в `MSC_ADDUFO` / `MSC_ADDCRAFT`, они грузят блок корабля поверх), затем z=0 «выжженная земля» под ними. Высота: `loadMAP` ставит корабль на первый пол в угловой клетке посадочного блока (`_craftZ = i`), либо mapscript задаёт её через `verticalLevels` (уровень типа `craft`).
- Ни одного места, где бы движок проверял «стоит ли нижний этаж корабля на земле», нет: корабль кладётся блоком, части под ним не достраиваются.
- Корабль не на земле, конкретные примеры:
  - `ORBIT_S1`, `S1B`, `S2`, `S2B`, `S3`, `S4`, `S4B`, `S5`, `ORBIT_COMMS_DISRUPTION` (Piratez_Mapscripts.rul: ORBIT_S1 5630, ORBIT_S1B 5676, ORBIT_S4B 5911, ORBIT_COMMS_DISRUPTION 5958): `verticalLevels` = `ground` (1 этаж) + `empty` (8, 12 или 16) + `craft` (8). Корабль игрока висит на z = 9, 13 или 17 над плитой 1x1x1. Под кораблём 8-16 этажей пустого воздуха.
  - Сама станция STATION_01 (блок 20x20x30): z=0 и z=1 - сплошные плиты (400 клеток пола каждая), z=2..9 пусто, объекты с z=10, основная конструкция z=14..21 (`view_STATION_01.txt`). Нижняя часть станции с 2 по 9 этаж - воздух.
  - `VES_300` (НЛО «Серебряные башни», блок 20x20x10): `z=0` пуст, самая нижняя часть корпуса на z>=1; 229 клеток и 1359 частей выше z=0 - единственный блок судов с категорией «z0 пуст: корпус выше».
  - 25 блоков `craft` и 12 блоков НЛО-судов стоят на «ногах» (категория `ноги: z0 редкий`): z=0 содержит 3-25 клеток с колоннами, колёсами или рампой, корпус от z=1.
  - `JELLYFISH` (Sapphire Jellyfish, 20x20x6): ног нет вообще, корпус держится на излучателях `LIFTER:0` (пол, броня 200) и `LIFTER:1` (объект, броня 180) - то есть на разрушимых элементах.
- Пол z=0 корабля в космосе и на воде - не земля, а невидимая плита (п.7, вопрос б).

### 2. Разбитый НЛО (`CRASHED`)
- `ConfirmLandingState::btnYesClick`: для `Ufo::CRASHED` тип миссии `STR_UFO_CRASH_RECOVERY` (ConfirmLandingState.cpp:267-268). Развёртывание берётся по тому же `ufo->getRules()`, что и для приземлившегося (`LANDED`, строка 210).
- `BattlescapeGenerator.cpp:956-959`: `if (!isPreview && _ufo && _ufo->getStatus() == Ufo::CRASHED) explodePowerSources();`. Функция (2525-2547) для каждой клетки с `UFO_POWER_SOURCE` в 75 процентах случаев взрывает HE-заряд силой 180-250 радиусом 10, затем обрабатывает цепочку `checkForTerrainExplosions`.
- Блоки у разбившегося и севшего одинаковые. В Пиратках отдельных deployments для `CRASHED` в рулсетах нет (grep `STR_UFO_CRASH_RECOVERY` по Piratez Ruleset - пусто).
- Вывод для модели: на старте боя «разбитый» корабль по геометрии идентичен целому; целостность корпуса ломает только взрыв источников питания (броня 255 не взрывается: TileEngine.cpp:3735).

### 3. Доля частей с бронёй 255 (по MCD кораблей и НЛО)
Источник: `ships/s4_armor.log`, `ships/split_stats.tsv` (по блокам без дедупа одинаковых клеток).

| Группа | блоков | частей | броня 255 | из них выше z=0 |
|---|---|---|---|---|
| craft (корабли игрока) | 86 | 26 234 | **21,6 %** | 22,2 % |
| ufo-суда и техника | 161 | 95 535 | 1,3 % | 0,2 % |
| ufo-здания (локации) | 123 | 154 215 | 1,0 % | 0,9 % |
| terrain (все 4906 блоков) | 4906 | 3 555 709 | 2,3 % | 1,3 % |

- `craft` по слотам: пол 20,3 % (2808 из 13 818), объект 32,5 % (2530 из 7782), стена З 8,5 %, стена С 4,6 %; класс `hard` (нерушимые стойки): 1932 части, все 255.
- Блоков `craft` с долей 255 не меньше 0,9: 24 из 86 (BLAZER, CADILLAC, CRAB, DEVASTATOR 0,983, DROPSHIP, VENTURA, GOLDENCLAW, HIGHSTAR, HUNTERKILLER, KRAKEN, MI8 0,982, NIGHTMARE, NKF_CONVOY, PLANE, SABRE 0,966, TAUROX, TRITON_U1, UH_1B_HUEY, MI_24_HIND, WHALER); 33 блока без единой части 255. Медиана блока - 0,15.
- В НЛО-кораблях 255 почти нет (блоков с долей не меньше 0,5: 3; из судов - USO_PYRAMID 0,42, TIGER_TANK 0,70, BANDIT_TRUCK_TAUROX 0,72, затонувшие GAL08/GAL10/GAL11 0,38-0,48).
- Террейны с огромной долей 255: орбитальные станции (ORBIT_COMMS_DISRUPTION 0,936, ORBIT_S5 0,984, остальные 0,35-0,82), `U_PLANET_VOID` 0,57, `TLETHBASEMAIN` 0,63, `GDX_DUEL` 0,79, `BLANKSPACE` 1,0 (`terrain_features.tsv`).
- Наборы MCD: самолётные/вертолётные наборы целиком 255 (plane, PLANE_VR, mi8, UH_1B_HUEY, XOPSTRANSPORT2/3, TRITON_U, TRITON_PURR, TAUROX, QTAXI, NKF_APC_PIR_BROWN: 1.000 в `armor255_by_set.tsv`), то есть корпус из таких кадров неразрушим.

### 4. Опоры корпуса: примеры (блок на z=0, xy - клетка в блоке, кадры 32x40 смотрел на листе `frames_legs.png`)
Все - классы `hard`/`object`, броня 255, LOFT 12 или 4-7 слоёв, тип записи 3 (объект). Источник - `ships/legs_z0.tsv`.

| Корабль (блок) | Запись MCD: набор:номер | Клетки z=0 (x,y) | Что на кадре |
|---|---|---|---|
| Lightning (CRAB 20x10x3) | LIGHTNIN:14-17 hard 255 | (10,7) (10,3) (6,7) (6,3) | стойка-колонна с круглым основанием |
| то же | LIGHTNIN:38, 39 object 255 | (13,5) (12,5) | ступенчатая рампа с розовым краем |
| Ми-8 (MI8 10x20x4) | mi8:0, mi8:1 hard 255 | (2,9) (7,9) / (5,15) | шасси: 2-3 колеса на штанге |
| то же | mi8:47-49 object 255 (LOFT 4) | (4,4..6) (5,4..6) | наклонный плоский трап |
| Skyranger (PLANE 10x20x3) | PLANE:0, PLANE:1 hard 255 | (3,9) / (4,15) (5,15) | колёсные стойки |
| то же | PLANE:62-64 object 255 | (4,6..8) (5,6..8) | плоский трап из трёх пластин |
| Devastator (DEVASTATOR 20x20x4) | XOPSTRANSPORT2:41 hard 255 | (5,14) (5,15) (9,3) (9,4) (10,3) (10,4) | тёмная трубная стойка |
| то же | XOPSTRANSPORT2:38-40 object 255 | (9,11..13) | решётчатые плиты |
| Brig (BRIG 10x20x4) | AVENGER_EDIT:49, 50 hard 255; :53-55 object 255; U_WALL_G_X:13 object 200 | (3,15) (3,6); (4,2..4); (4,13) (4,14) | пьедестал-опора; три пластины; низкая стенка |
| Goldenclaw (GOLDENCLAW 10x20x3) | GOLDENCLAW:36 hard 255; :35 floor 255 | (3,8) (3,12) (6,10); (4,10) | латунная опора; зелёный светящийся ромб в полу |
| Sabre (SABRE 20x20x3) | PLANE2:107, :12 hard 255; :96 object 255; :104 floor 255 | (6,9) (9,14) (12,9); (6,12) (12,12); (9,13); (10,14) | чёрные стойки; клетчатая плита; светящийся пол |
| Firefox (KITSUNE 20x20x3) | KITSUNE:2, :5 hard 255 (big_wall 1); :0, :1 object 255 | (4,7) (5,7); (4,8) (4,9) | боксы-гондолы с рампой |
| Jellyfish (JELLYFISH 20x20x6) | LIFTER:1 object 180; LIFTER:0 floor 200 | 9 клеток, например (2,9) (3,6) (6,3) | синий ромб-излучатель и зелёные огни; **не 255** |

Наблюдение: у ног 255 - «опора корпуса» состоит из колонны (`hard`) плюс рампы/трапа (`object`) на отдельных клетках, корпус начинается этажом выше. У JELLYFISH и вообще у корпусов с `LIFTER` опора - разрушимый излучатель.

### 5. Статистика parts_up и unsupported (модель опор v1, `census/collapse/static.tsv`)
`parts_up` - части выше z=0; `unsupported` - части, которые правило v1 считает неопёртыми. Раскладка - `ships/split_stats.tsv`, `ships/s5_static.log`.

| Группа | блоков | parts_up | unsupported | доля | блоков с неопёртым | блоков с долей не меньше 0,3 (parts_up не меньше 20) |
|---|---|---|---|---|---|---|
| craft | 86 (73 с частями выше z0) | 19 633 | 2 553 | **13,00 %** | 56 | 19 |
| ufo-суда | 161 | 60 535 | 4 651 | **7,68 %** | 63 | 7 |
| ufo-здания | 123 | 104 279 | 2 009 | 1,93 % | 58 | 8 |
| terrain | 3881 с частями выше z0 | 1 942 269 | 49 774 | 2,56 % | 1135 | 222 (без порога по parts_up) |

Топ-10 блоков по доле неопёртых (parts_up не меньше 20, `ships/top10_by_group.tsv`):

| craft | доля | | ufo-суда | доля |
|---|---|---|---|---|
| JELLYFISH | 1,00 (447 из 447: висит 244, на неопёртом полу 100, под клеткой только block 52) | | SUNKEN_CARGO_SHIP MSUNK02 | 1,00 (103: висит 103) |
| MI8 | 0,971 (101 из 104) | | VES_300 | 1,00 (1359 из 1359) |
| GOLDENCLAW | 0,933 | | VES_NIN_MIG | 0,963 |
| SABRE | 0,765 | | VES_NIN_INTERCEPTOR | 0,667 |
| HUNTERKILLER | 0,698 | | VES_EXCV | 0,461 |
| DEVASTATOR | 0,698 (157 из 225; далеко от опоры 52) | | VES_160 | 0,357 |
| WHALER | 0,674 | | VES_LAB | 0,317 |
| NKF_CONVOY | 0,607 | | GHULCRAWLER | 0,25 |
| LITTLE_BIRD | 0,545 | | VES_120 | 0,20 |
| CAPSULE8 | 0,453 | | VES_R_020 | 0,158 |

Причины в топе: «висит» (под клеткой ничего) - основная; «стоит на неопёртом полу»; «далеко от опоры» (консоль больше C=2 или пролёт больше L=12); «под клеткой только block/object (висит)».
Топ ufo-зданий (для сравнения): SURVHOUSE_JUNGLE01 0,66, BANDIT_CAMP_02 0,61, BANDIT_CAMP_04 0,49, ESCAPE_TOWER 0,34, HTHOUSE_16 0,28.

Позы корпуса по блокам (`stance.tsv`): craft - ноги 25, частично 36, пол z=0 по большей части следа 12, плоский 13; НЛО-суда - плоский 18, пол z=0 по большей части 101, частично 29, ноги 12, z0 пуст 1; НЛО-здания - плоский 10, пол 83, частично 28, ноги 2.

### 6. Гипотеза «корпус - единое тело» и что проверяемо статически
Гипотеза: корпус держится, пока связан с опорой (ноги, посадочная площадка, дно) через неразрушенные части; разрушение обшивки (локально) отдельно от потери опоры (всего тела).

Статическая проверка топологии (`ships/s14_conn.py`, `conn_blocks.tsv`): занятые клетки блока (любая часть MCD) собраны в компоненты (соседство по граням), якорь - клетка z=0 с любой частью (A2) или только с нерушимой стойкой/рампой `hard`/`object` 255 (A1). Доля частей выше z=0 **вне компоненты с якорем** (A2):

| Группа / поза | parts_up | v1 «неопёрто» | вне компоненты с якорем A2 | то же при A1 (только 255) |
|---|---|---|---|---|
| craft, ноги | 4 190 | 1 367 | **12** | 1 297 |
| craft, частично | 6 244 | 822 | 4 | 2 940 |
| craft, пол z=0 | 9 199 | 364 | 0 | 8 938 |
| ufo-суда, ноги | 6 398 | 1 514 | **0** | 6 398 |
| ufo-суда, частично | 20 855 | 1 021 | 0 | 15 952 |
| ufo-суда, пол z=0 | 31 923 | 757 | 61 | 30 372 |
| ufo-суда, z=0 пуст (VES_300) | 1 359 | 1 359 | 1 359 | 1 359 |
| ufo-здания (все позы) | 104 279 | 2 009 | 24 | - |

- Из 1367 «неопёртых» частей у кораблей на ногах корпус связан с z=0 у 1355: v1 ловит не отрыв корпуса, а то, что часть рассматривается по отдельности (консоль, `block` без пола под ним). Единственные настоящие отрывы от z=0: MI8 (12 частей, винт), MI_24_HIND (4), SUNKEN_CARGO_SHIP MSUNK02 (61, полузатонувшая), DEEPS (24), VES_300 (весь корпус).
- Якорь только из брони 255 (A1) слишком строг: у 31 блока `craft` (AIRBIKE, AIRCAR, JELLYFISH, CAPSULE5-8, SWORDFISH, WORM...) нерушимых ног нет совсем - ноги и пол обычные разрушимые.
- Следствие: выводы про «неопёртость» надо делать по компоненту связности, а не по частям; якорем считать любую часть z=0 в компоненте.
- Не проверяется статикой: какие части разрушит конкретный урон; ломается ли корпус по связности после урона (нужна динамика); как движок опускает корабль при посадке (`loadMAP` подъём на первый пол); что стоит под z=0 блока корабля на карте (земля террейна, вода, вакуум, крыша) - это определяет сочетание блока и террейна на старте.
- Для группы 3 якоря нет по построению: ни в космосе, ни на воде корпус ни на чём не стоит, «потеря опоры» бессмысленна; остаётся только локальное разрушение обшивки.

### 7. Группы террейнов: суда и конструкции среди `kind=terrain` (ответ на дополнение)
Результат: `ships/terrain_groups.tsv` (террейн, группа, довод, уверенность; 249 террейнов секции terrains), `ships/ship_groups.tsv` (287 типов ufo/craft с террейном, группа, довод), сводные признаки - `ships/terrain_features.tsv`, скрипт - `ships/s9_groups.py`.

Правило определения (по данным, приоритет сверху вниз):
1. **Группа 3 (суда без земли)**: у deployment enviroEffects `SPACE`, `SPACE_FREIGHTER` или `SEA_SURFACE`; либо имя `ORBIT_*`, `SPACE_FREIGHTER_*`; либо `BLANKSPACE`.
2. **Группа 2 (на земле)**: в `mapDataSets` террейна набор `CRASHEDPLANE`.
3. **Группа 4 (подземные)**: mapscript deployment содержит `digTunnel` (ALIENBASE, THULEBASE, WHITEBASE, XBASE, TLETH_COLONY_P2, BOSSBATTLE, CAVES_LABYRINTHUS_NOCTIS) - подземные базы, прорытые в породе; либо токен имени CATACOMB, CAVE, METRO, SEWER, TUNNEL, VAULT, DUNGEON, CRYPT, SUBWAY, UNDERGROUND; либо те же блоки, что у террейна с `digTunnel` (UBASE, ABASE и т.п.). Дополнительный признак (не решающий): `cells_with_up` 0,98 и выше - им обладают и лайнеры, и станции.
4. **Группа 0 (нет конструкций)**: над z=0 меньше 150 частей (рельеф, равнина, плоский пол, служебные карты EXITMAP и HANGAR_PREVIEW).
5. **Группа 1 (наземные постройки)**: всё остальное; уверенность выше у явных городов, посёлков и природного рельефа.
Ручные пометки (низкая уверенность) вынесены в `OVERRIDE` в скрипте, у каждой - довод.

Сводка: группа 0 - 26, группа 1 - 134 (высокая 95, средняя 26, низкая 13), группа 2 - 4, группа 3 - 19, группа 4 - 66 (высокая 51, средняя 10, низкая 5).

**Группа 3, суда без земли (19):**
- `ORBIT_S1`, `S1B`, `S2`, `S2B`, `S3`, `S4`, `S4B`, `S5`, `ORBIT_COMMS_DISRUPTION` - орбитальные станции, deployments STR_LOC_SPACE_STATION_1..5, STR_LOC_COMMS_DISRUPTION, 60x60x30, enviro SPACE. Доля неопёртых v1 = 1,000 у всех девяти, `max_sz` 30. Корабль игрока висит над плитой (п.1).
- `SPACE_FREIGHTER_BASE`, `AGRARIAN`, `CARGO`, `COMMAND`, `PASSENGER`, `STRUCTURE` - космический грузовик, deployment STR_SPACE_FREIGHTER 80x80x13, enviro STR_ENVIRO_SPACE_FREIGHTER, mapscript SPACE_FREIGHTER (13 verticalLevels ground/middle/ceiling). z=0: видимая палуба FREIGHTER_MAIN:8 (броня 18) и :0 (броня 100), невидимая плита FREIGHTER_MAIN:28; в STRUCTURE 45 процентов клеток z=0 пусты, у остальных 4-10.
- `CRUISE_LINER`, `CRUISE_LINER_ACADEMY`, `CARGO_LINER` - круизный лайнер и грузовой корабль на море, enviro SEA_SURFACE (STR_LOC_ACADEMY_CRUISE, STR_LOC_PIRATE_CRUISE 30x70x15). addBlock без addCraft; z=0 - невидимая плита LINERSHIPB:1 (512-574 клетки на блок) плюс палубы LINERSHIPD:8, LINERSHIPA:24; у CARGO_LINER палубы CARGO1:46, CARGO3:4.
- `BLANKSPACE` - пустой космос, броня 255 у 100 процентов частей, deployments нет.
Затопленные суда (`SUNKEN_*`, `SUNKURBAN`-террейн и прочее) сюда не входят: дно есть (SEASAND6), корпус лежит на нём.

**Группа 2, суда и аппараты на земле (4):** `DESERTPLANE`, `POLARPLANE`, `TUNDRAPLANE`, `SEAPLANE` - наборы `DESERTPLANE`/`CRASHEDPLANE` на рельефе (SEAPLANE - на морском дне, enviro SEA). Корабль добавляется `addCraft` плюс `addUFO` (VES_CRASHPLANE). Доля неопёртых v1 0,387 - ложные тревоги модели на корпусе, который стоит на земле. Все остальные суда на земле - это `ufo/craft` с собственными блоками (`ship_groups.tsv`: 82 craft и 129 ufo в группе 2).

**Группа 4, подземные (66):** по правилу 3. Подробно:
- Базы с `digTunnel` (высокая): `ABASE`, `UBASE`, `UBASE_VR`, `BLACKBASE`, `CHURCHBASE`, `DREADBASE`, `GUILDBASE`, `THULEBASE`, `WHITEBASE`, `WHITEBASE_INFLIL1`, `XBASE`, `ICEKING_CAVE_BOSSBATTLE`, `TLETHBASEMAIN` (средняя).
- Катакомбы (17 террейнов `CATACOMBS*`), пещеры (`CAVES_*`, 16, из них AQUA 4 - подводные), метро (`METRO`, `_ALTERLANDING`, `_IRRADIATED`), канализация (`SEWERS`, `CITY_OF_THE_DEAD_SEWERS`), подземелья и туннели (`APOC_TUNNEL`, `RETICULAN_DUNGEON`, `CYDSUBWAY`, `NINJA_BASE_2_UNDERGROUND`, `RITUAL_CAVE`, `LOKNAR_ALTAR_CAVES`, `SACREDCAVE`, `CRYPTEK`, `CRYPTEK_LABIRYNTH`, `UAC_VAULTS` x3 - у последних один этаж и нет частей выше z=0).
- Низкая уверенность: `GDX_PRISON`, `STORMMOUNTAIN`, `UAC_BASE_4`, `TEC_BASE_TUNNELS`, `TLETHBASEENTRY` - по наборам и именам.

**Группа 0, без конструкций (26):** `ASYLUM_FENCE`, `BEACH_SAVANNA`, `COMRCURBAN_LANDING_31`, `DESERT`, `DESERT2RED`, `DESERTX`, `DESERT_DUST_STORM`, `EXITMAP`, `HANGAR_PREVIEW`, `MARS_NO_PYRAMIDS`, `NINJA_HQ_HANGAR`, `NINJA_RAID_SITE`, `PLAINS_*` (7), `POLAR`, `POLAR_SOLID`, `ROADWASTE`, `RURAL_LANDING`, `SEABED`, `STR_CORAL_ENTRY`, `URBAN_LANDING_ARMY`.

**Группа 1, наземные постройки (134):** города и посёлки (URBAN*, CHEMTOWN*, COMRCURBAN*, INDUSTRIALSLUM*, ISLANDURBAN*, NUKE_CITY*, PORT*, POLISURBAN*, WESTOWN*, RURAL*, CULTA*, FOREST*, JUNGLE*, MOUNT*, MOUNTBD_*, RICE_FARM*...), отдельные здания (EMANSION, MAGAZYNMAFII, GDX_HOUSE, DTAVERN, PRECINT13, STYXTOWER, COMMS_TOWER, DARK_TOWER, WHITE_CASTLE, OLD_FORT_SLUM...), Кидония (CYD*, низкая: ярусные базы MARTIANBASETOP/MIDDLE/BOTTOM, Марс), подводные посёлки на дне (SUNKURBAN, UCITY, SEACORAL, STR_CORAL_*: пол есть). Низкая уверенность: `CYDCOLLEGE`, `CYDHABITATION`, `CYDHANGAR`, `CYDHANGAR_ALT`, `CYDLABS`, `MARS`, `MARS_VR`, `NECROPOLIS`, `VAMPIRE_CASTLE`, `WHITE_CASTLE`, `MUMMY_VILLAGE_SETTLEMENT`, `EMANSION_MAG`, `U_PLANET_VOID`. Особые случаи внутри группы: `DARK_TOWER` (пол z=0 только у 24 процентов клеток), `EMANSION_MAG` (пола z=0 около 52 процентов), `GDX_DUEL` (79 процентов частей с бронёй 255), `U_PLANET_VOID` (57 процентов 255): модель опор для них либо не применима, либо вырождена.

Ответ (а): что за карты и как стоят - в группе 3: станция висит над плитой, корабль игрока над ней на 8-16 этажей выше; грузовик и лайнеры - единое судно по блокам, пол z=0 которого - палуба или невидимая плита; в группе 2 корабль на рельефе земли, дна или снега. Ответ (б): что на z=0 - ORBIT: невидимая плита STATIONBITS:7 / SPACEVOID:0, :1 (кадры целиком прозрачные, nonzero_px=0, tu_walk 255, броня 255, тип 0 - пол: непроходимо, неразрушимо, не видно); FREIGHTER: палуба (видимая, броня 18/100) и невидимая плита FREIGHTER_MAIN:28; лайнеры: невидимая плита LINERSHIPB:1 (броня 255, tu_walk 255) и палубы LINERSHIPD:8-9 (броня 255 у :1 и :9); CRASHEDPLANE: обычное дно/земля; BLANKSPACE: пустые клетки с бронёй 255. Ответ (в): таблица `terrain_groups.tsv`.

Дополнение по `kind=ufo`: в группы 1 и 2 разложены и типы ufo (`ship_groups.tsv`). Здания-локации (76 блоков и ~76 типов: STR_LOC_*, SURVHOUSE_*, HT*HOUSE, BANDIT_CAMP*, STR_BUNKER, STYX_DARKTOWER_*, STR_UFO_AIRSTRIP_NS, STR_UFO_TURRET_14MM, пеший патруль STR_VESSEL_FOOT_PATROL*) - группа 1. Техника на земле (HUMVEE, STRYKER, GOVTCAR, STRAGAN1, DELOREAN_UFO, LOC_SHUTTLE, VES_NIN_APC, TIGER_TANK, BANDIT_CAR) и суда с реальной скоростью (VES_*, UFO_*, USO*, VESSEL_*) - группа 2. SUNKEN_CARGO_SHIP, SUNKEN_GALLEON, SUNKEN_UFO, SUNKEN_USO - группа 2 (на дне, терраин SEABED/SEACORAL).

## Проверено в коде
- src/Battlescape/BattlescapeGenerator.cpp:956-959 - `explodePowerSources()` только при `Ufo::CRASHED` и не в предпросмотре.
- src/Battlescape/BattlescapeGenerator.cpp:2525-2547 - `explodePowerSources`: каждый `UFO_POWER_SOURCE`, шанс 75 процентов, сила 180+RNG(0,70), радиус 10, затем `checkForTerrainExplosions`.
- src/Battlescape/BattlescapeGenerator.cpp:2118-2124 - `loadMAP`: `_craftZ`/`_ufoZ` берутся по первому полу блока корабля.
- src/Battlescape/BattlescapeGenerator.cpp:3009 (MSC_ADDCRAFT), 3072 (MSC_ADDUFO), 3815-3819 (`_craftZ`/`_ufoZ` из уровня `craft` у `verticalLevels`), 2936-3005 и 3064, 3152 (loadVerticalLevels из команд).
- src/Geoscape/ConfirmLandingState.cpp:210, 267-268 - статусы LANDED/CRASHED, тип миссии `STR_UFO_CRASH_RECOVERY`.
- src/Battlescape/TileEngine.cpp:3735 - взрыв не трогает части с бронёй 255.
- Пиратки/Dioxine_XPiratez/user/mods/Piratez/Ruleset/Piratez_Mapscripts.rul: ORBIT_S1 5630, ORBIT_S1B 5676, ORBIT_S4B 5911, ORBIT_COMMS_DISRUPTION 5958 (verticalLevels ground/empty/craft); SPACE_FREIGHTER 4764; CRUISE_LINER 2188; CARGO_SHIP 2184; CRASHEDPLANE 2142; ALIENBASE 321 (digTunnel); METRO 4733; DARK_TOWER_LANDING 2241. Скрипты с `digTunnel`: ALIENBASE, BOSSBATTLE, CAVES_LABYRINTHUS_NOCTIS, THULEBASE, TLETH_COLONY_P2, WHITEBASE, WHITEBASE_INFLIL1, XBASE (разбор файла, `s9_groups.py`). Скриптов с `verticalLevels` 63 вхождения (ORBIT_* по 3, SPACE_FREIGHTER 13, CAVES_UAC_SHELTER_A 9, CAVES_LABYRINTHUS_NOCTIS 13).
- MCD записи (62 байта, поля: кадры 0-7, tu_walk 39, броня 42, die 44, alt 46, stop_los 31, тип 53): `ships/s11_blank.py` - STATIONBITS:7, SPACEVOID:0/1, LINERSHIPB:1, FREIGHTER_MAIN:28 - 8 кадров по 0 непрозрачных пикселей, броня 255, tu_walk 255; FREIGHTER_MAIN:0 броня 100, 256 пикселей.
- Мои скрипты (все в census/collapse/ships/): s1_rules, s2_terrains, s3_scan, s4_armor, s5_static, s6_view, s7_legs, s8_lz, s9c_deploy, s9d_features, s9e_deps, s9_groups, s10_sheet, s11_blank, s12_merge, s13_split, s14_conn; данные - см. список ниже.

Файлы данных (census/collapse/ships/, вне гита): terrain_groups.tsv, ship_groups.tsv, terrain_features.tsv, terrain_use.tsv, terrain_deps.tsv, deploy_terrains.tsv, ship_rules.tsv, split_stats.tsv, top10_by_group.tsv, top_unsupported.tsv, stance.tsv, legs_z0.tsv, lz_corner.tsv, z0_floor.tsv, armor255_by_block.tsv, armor255_by_set.tsv, conn_blocks.tsv, records_ships.tsv, view_*.txt (блоки CAPSULE8, DEVASTATOR, DROPSHIP, GOLDENCLAW, JELLYFISH, MI8, MSUNK02, ORBIT_00, ORBIT_01, SABRE, STATION_01, VES_160, VES_300, VES_NIN_MIG), листы кадров frames_legs.png и frames_floors.png.

## Источники
- Локальные: рулсеты Пираток (Piratez_Planet.rul - террейны, Piratez_Factions.rul - ufos и alienDeployments, Piratez_Mapscripts.rul), MCD/PCK Пираток, `census/collapse/static.tsv` (модель опор v1, tools/collapse_census.py), `census/collapse/stage0d/records_all.tsv` (названа координатором ориентиром; построчно не сверял).
- Веб не использовался: ответы получены из кода и данных проекта.

## Чего НЕ выяснил
- Что стоит под z=0 корабля игрока на конкретных картах (земля террейна, крыша, вода): статически видно только блок корабля; итоговая высота зависит от сочетания блока и террейна при загрузке.
- Свойство «потолок держит порода» в данных не выражено: группа 4 построена по `digTunnel`, именам и наборам, а не по полю движка. 5 террейнов группы 4 (GDX_PRISON, STORMMOUNTAIN, UAC_BASE_4, TEC_BASE_TUNNELS, TLETHBASEENTRY) и 13 террейнов группы 1 (CYD*, MARS*, замки, NECROPOLIS, MUMMY_VILLAGE_SETTLEMENT, EMANSION_MAG, U_PLANET_VOID) помечены низкой уверенностью; решение за Vitali.
- Специальные деплойменты и скрипты для `CRASHED` в Пиратках: в рулсетах не нашёл, но в движке они возможны через `ufo->getRules()` без отдельной ветки; полным перебором всех mapscripts на `CRASHED` не проверял.
- Применимость 20x20+ посадочных блоков в `addCraft` (как именно подбирается блок с LZ под большой корабль): правило выбора блока по `lz_corner.tsv` разобрано частично.
- Сверка с `stage0d/records_all.tsv` по ролям и `hang_RA` не сделана.
- Динамика: проверялась только топология (связность), поведение корпуса при уроне и порядок разрушения частей не моделировались; доля «настоящих» отрывов (5 блоков) получена при определении якоря как любой части z=0.
- Пара «блок - число ног» по всем 86 блокам `craft` не описана построчно (описаны 12 блоков, остальные - в `legs_z0.tsv`).
- Визуальное описание кадров опор сделано по листу x4 глазами, без сверки с педией.
