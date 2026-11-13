# Данные Пираток, от которых зависит поведение ИИ

Фаза 1 программы `PLAN.md`. Источник — рулсеты Пираток после слияния (`.index/mod/Piratez/rul/values.tsv`, строит
`tools/rul_map.py`). Таблицы целиком — вывод `census/ai4_2026-10-14/scripts/piratez_ai_data.py` (21.10). Код — сборка
стенда `src_ai4`; строки указаны на неё.

## 1. Характер юнитов (302 юнита, входящих хоть в одну расу)

| aggression | юнитов | что это значит в коде |
|---|---|---|
| 0 | 47 | резерв ОВ на прицельный выстрел (50 %) в патруле |
| 1 | 102 | резерв на автоочередь (40 %) |
| 2 | 76 | резерв на выстрел навскидку (33 %) |
| 3 и выше | 77 | резерва нет: в патруле тратит всё |

- Резерв действует только в PATROL и только у юнита с огнестрелом (`checkReservedTU`). В бою (COMBAT) резерва нет ни у кого.
  Поэтому 64 % врагов, которые видят бойца, встречают ход игрока с остатком меньше 20 % ОВ (`phase2-results.md`, П8).
- intelligence (сколько ходов сторона помнит настоящую позицию бойца после последнего взгляда): 1×26, 2×36, 3×46,
  4×73, 5×42, 6×43, 7×16, 8×12, 9×2, 10×5, 0×1. Середина — 4. У бойца игрока (для бота) — 2, константа.
- sniper (процент шанса стрелять по бойцу, которого видит другой юнит стороны, `AIModule.cpp:1839`): у 126 из 302;
  чаще всего 25, 33 и 50.
- isLeeroyJenkins (бежит в ближний бой, не думает): 13 юнитов — STR_AUR_2, STR_CHUPACABRA_TERRORIST,
  STR_DEEP_ONE_BERSERKER, STR_DOOM_DEMON_TERRORIST, STR_ERIDIAN_FENCER, STR_MAGGOT_TERRORIST, STR_MEGAZOMBIE_TERRORIST,
  STR_MUTON_HEAVY, STR_SKELETON_TERRORIST и четыре зомби-террориста.

## 2. Ранг юнита и место появления

- Ранг юнита — индекс в `members` расы: 0 commander, 1 leader, 2 engineer, 3 medic, 4 navigator, 5 soldier,
  6 terrorist, 7 terrorist2. У части рас членов больше восьми (STR_DOOM — 15, STR_BANDIT — 17).
- `addAlien` (`BattlescapeGenerator.cpp:1797`) обрезает ранг больше 7 до 7: такой юнит ищет узлы по строке terrorist2
  таблицы `Node::nodeRank` ({2,5,3,4,6,8,0}) и получает ранг 7.
- Узел ищется по таблице `Node::nodeRank` (`Node.cpp:57`): commander и leader {4,3,5,8,7,2,0}, engineer
  {5,4,3,2,7,8,0}, medic {7,6,2,8,3,4,0}, navigator {3,4,5,2,7,8,0}, soldier и terrorist {2,5,3,4,6,8,0}.
- `percentageOutsideUfo` действует только в бою с кораблём (сбитый или севший). Если корабля нет (террор, локация,
  штурм базы), то `outside = false` (`BattlescapeGenerator.cpp:1738`), кроме развёртываний с
  `forcePercentageOutsideUfo` — в Пиратках таких нет. Значит, в бою без корабля все враги встают на узлы по рангу.
- 19 рас задают `membersRandom` (тип юнита на ранге выбирается броском): STR_CANNYS, STR_CHURCH_NONCOM,
  STR_CIVILIANZ_1, STR_CULT_OF_CHERNOBOG, STR_CYD_RACE_A/B/C, STR_DEATH_DUNGEON_RACE, STR_DEMON_EX,
  STR_FLOATER_MANSION, STR_GOVT_INDUSTRIAL, STR_MEGAPOL_AND_FACTIONS_MIXED, STR_NIGHTOSPHERE_RACE, STR_PASSENGERS,
  STR_RIMRIDERS, STR_STYGIAN_RACE, STR_TRANS_STELLAR, STR_ZOMBIE, STR_ZOMBIE_VAMPIRES.

## 3. Развёртывания стенда (наборы k7, mercs, guild)

Доля «снаружи» по рангам (низ-верх + прирост по сложности):

| набор | миссия | корабль | снаружи |
|---|---|---|---|
| k7 | STR_ERIDIAN_TERROR | нет | не действует; на узлах по рангу |
| k7 | STR_BATTLESHIP | да | soldier 50 %, navigator/medic/engineer 20 %, terrorist 50 %, командиры 0 |
| k7 | STR_VESSEL_BOMBER_SECTOID_ELITE | да | terrorist 100 %, navigator (8-13) 70 %, soldier 40 %, engineer 50 % |
| k7 | STR_ABDUCTOR | да | soldier и navigator 70 %, engineer 30 %, medic 20 % |
| k7 | STR_VESSEL_USO_HEAVY_CRUISER_TASOTH | да | все — leader (16-26), 50 % |
| k7 | STR_LOC_LOKNAR_VILLAGE_DEFENSE | нет | не действует |
| k7 | STR_LOC_DRIFTER_CAMP | нет | ранги 10 и 16 → строка terrorist2 |
| mercs | STR_ALIEN_BASE_ASSAULT | нет | 0 % везде |
| mercs | STR_BATTLESHIP, STR_VESSEL_CORVETTE, STR_VESSEL_DESTROYER, STR_VESSEL_HEAVY_GUNSHIP | да | soldier 20-60 %, navigator 40-60 % |
| guild | пять кораблей STR_*_FLOATER_ELITE | да | terrorist 100 %, medic 70 %, soldier 50 %, navigator и выше 0 |

- Связь с П2 (`phase2-results.md`): меньше всего «топчутся» в BOMBER (7 % и 17 %) — там большинство (террористы
  и навигаторы) стоит снаружи, то есть разведчики с первого хода. Больше всего — LOKNAR (80 %, 45 %), где корабля
  нет и все встают на узлы по рангу. Это совпадает с кодом; что именно делает стража разведчиком внутри корабля —
  проверяет прогон mpa/mpb (запись `what=spawn` / `what=pnode`).
- Расы на стенде K7 случайные (STR_SPAIN, STR_BAD_COPS, STR_REBELS, STR_DOOM, STR_RACE_VAMPIRE и другие), а не раса
  корабля. Это искажение стенда: состав «командир-навигаторы-солдаты» у этих рас другой.

## 4. Составы рас стенда (aggression / intelligence / reactions / ОВ)

- STR_MUTON: командир 2/7/100/100, лидер 3/6/85/90, инженер 1/6/70/65, medic — тот же солдат 2/4/60/65,
  навигатор 2/5/65/75, солдат 2/4/60/65, terrorist — STR_MUTON_HEAVY 5/5/45/80 (Leeroy), terrorist2 — танк.
- STR_FLOATER_ELITE (Гильдия): командир 0/8/65/60, лидер 0/8/45/55, инженер 1/7/40/65, medic STR_MARSEC_TROOPER
  1/6/65/80, navigator STR_MARSEC_BODYGUARD 2/6/45/45. Верх Гильдии — aggression 0: в патруле держит половину ОВ.
- Остальные (STR_SPAIN, STR_BAD_COPS, STR_REBELS, STR_DOOM, STR_RACE_VAMPIRE, STR_BANDIT) — в выводе скрипта.
  У STR_DOOM рядовые (STR_DOOM_SOLDIER) — aggression 3: резерва нет.

## 5. cheatTurn

489 развёртываний — 20 (по умолчанию), одно — 5: `STR_MARS_THE_FINAL_ASSAULT_2` (`Piratez_Factions.rul:114631`).
После cheat вся сторона врага знает всех бойцов (`turnsSinceSpotted = 0`), все патрульные становятся разведчиками
(`10_patrol.md`, `scout = isCheating() || ...`) и каждый ход переоценивают режим (`AIModule.cpp:707`) — то есть
переходят в бой по известным позициям.

## Что из этого следует для фазы 3

- Ответный огонь упирается в резерв: у 77 юнитов (aggression ≥ 3) резерва нет совсем, у остальных он есть только
  в патруле. В бою, когда враг уже видит бойца, ОВ на реакцию никто не оставляет — это рычаг «стрелять чаще в ответ».
- Память стороны о бойце — 1-10 ходов по intelligence; честное знание без читов — в этих рамках.
- Расстановка на стенде K7 не та, что в игре (случайные расы), поэтому выводы о патруле проверять и на наборах
  mercs и guild, где раса своя.
