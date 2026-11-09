# P-6: ID рас для OXCE_AI_RACE по сценариям этапа 1

Построено `p6_races.py` из `AUDIT-STAGE-1-BENCHMARK-DESIGN.md` (6.2-6.4) и разобранных рулсетов Пираток (`.index/mod/Piratez/rul`, сборка 2026-10-14). Исходники и рулсеты не менялись.

## Формат `OXCE_AI_RACE`

- Значение - **точный ID расы из `alienRaces` с префиксом `STR_`**: `STR_NINJA`, `STR_SECTOID_NONCOM`, `STR_BANDIT_ROBBERS`. Сравнение `std::find` по строке, без регистра-нормализации и без добавления `STR_` (`NewBattleState.cpp:900-906`).
- Опечатка или не тот ID: **молча, без ошибки**. В лог пишется только `[AIPROBE] no race X in the quick battle list: random instead` (`LOG_WARNING`, строка 909), бой идёт дальше с прежней расой: расой от siteType-миссии, а нет такой - **случайной** из списка. Пустая строка вообще не пишет предупреждения.
- Список, по которому ищет `std::find`, - **не весь `alienRaces`**, а отфильтрованный под выбранное развёртывание (`cbxMissionChange`, 1244-1270): без `*_UNDERWATER`; число членов расы строго больше максимального `alienRank` в `data` развёртывания; если у развёртывания `depth` > 0 - должна существовать раса `<ID>_UNDERWATER` (и в ней хватать членов). Корректный ID, не прошедший фильтр, ведёт себя как опечатка (статус `не выбирается стендом`).
- Порядок: расу по `siteType` и случайную стенд выбирает первой, `OXCE_AI_RACE` перекрывает её после; броски зерна не сдвигаются. Для `depth` > 0 движок сам добавит `_UNDERWATER` (`deployAliens`, 1828).
- **Перекрытие развёртыванием.** `BattlescapeGenerator::deployAliens` (1822-1826) при `monthsPassed > -1` (бой поверх кампании-сейва, то есть стадии M и L) заменяет расу полем `race` развёртывания. Ни один из сценариев документа такого поля не имеет (проверено скриптом), но у других развёртываний оно есть (`STR_LOC_THULEBASE`, `STR_ALIEN_BASE_ASSAULT_ACADEMY` и др.).

## Итог

Основные сценарии (36): ok - 35, не выбирается стендом - 1.

Запасные (12): ok - 12.

Ключ к статусам: `ok` - раса есть, проходит фильтр списка стенда и встречается у развёртывания в рулсете для месяцев этой стадии; остальные - см. колонку замечаний.

## Отдельно: STR_NINJA_BASE_OUTPOST_ASSAULT (M5)

Вывод: раса - **`STR_NINJA`**. У самого развёртывания расы нет (нет поля `race`, `Ruleset/Piratez_Factions.rul:104320`), у порождающей его миссии `raceWeights` пуст, а раса приходит от аванпоста-основателя.

Цепочка по рулсету (файл `Ruleset/Piratez_Factions.rul`):

1. Развёртывание порождает миссия `STR_MISSION_NINJA_ESTABLISH_OUTPOST` (строки 37804-37810): `siteType: STR_NINJA_BASE_OUTPOST_ASSAULT` (37807), `objective: 2`, **`raceWeights: {}`** (37810) - то есть пусто.
2. Эту миссию никто не запускает скриптом (в `missionScripts.missionWeights` её нет). Её создают сами ниндзя-базы через `genMission`: `STR_NINJA_BASE_1_ASSAULT` (`STR_MISSION_NINJA_ESTABLISH_OUTPOST: 150`, 104784), `STR_NINJA_BASE_HQ_1_ASSAULT` (105680), `STR_NINJA_BASE_HQ_2_ASSAULT` (105962).
3. Раса миссии, созданной базой, - раса базы: `GeoscapeState.cpp:2401-2409` (`mission->setRace(base->getAlienRace())`, если у развёртывания `genMissionRaceFromAlienBase` = true; по умолчанию true, в рулсетах Пираток поле не задано).
4. Раса самих баз: миссия-основатель `STR_MISSION_NINJA_ESTABLISH_BASE` (37853): `siteType: STR_NINJA_BASE_1_ASSAULT`, `raceWeights: 0: STR_NINJA: 100` (37858-37860); так же `ESTABLISH_BASE_2` (37878) и `ESTABLISH_HQ` (37903).
5. Значит, в игре аванпост всегда `STR_NINJA` (100% с месяца 0).

Почему в стенде и в истории получилось «UNKNOWN»/случайное: стенд берёт расу так (`NewBattleState.cpp:880-897`): миссия с `siteType` = развёртывание -> `generateRace(month)`; но у `ESTABLISH_OUTPOST` распределение пустое, и `RuleAlienMission::generateRace` (`RuleAlienMission.cpp:163-169`) возвращает `""`. Пустая строка в списке рас не находится, остаётся случайная раса из списка. Откуда именно слово UNKNOWN в истории боёв, по рулсету и коду стенда установить нельзя - это поле разбора истории, не рулсета.

То же касается всех развёртываний, которые порождают миссии с пустым `raceWeights` (`STR_NINJA_RAID_SITE`, `STR_GOVT_BASE_DEFENSE`, `STR_NINJA_BASE_OUTPOST_2_ASSAULT`): у них без `OXCE_AI_RACE` раса случайная.

## Отдельно: M4 STR_VESSEL_LABSHIP / STR_SECTOID_ELITE

- В документе раса `SECTOID_ELITE`. Мерка расы `STR_MISSION_LABSHIP` (38334): месяцы 0-23 - `STR_SECTOID_NONCOM`, с 24 - `STR_SECTOID_ELITE`.
- У `STR_VESSEL_LABSHIP` в `data` есть ранги до 12 (без `customUnitType`). У `STR_SECTOID_ELITE` членов 8 (ранги 0-7), у `STR_SECTOID_NONCOM` - 15. `AlienDeployment::getMaxAlienRank` = 12, фильтр списка стенда выкидывает расы с числом членов <= 12, поэтому `OXCE_AI_RACE=STR_SECTOID_ELITE` для LABSHIP **молча не сработает**, а сам движок (`deployAliens`/`checkAlienRanks`) на ранге 11-12 при ELITE сообщит `Invalid alien deployment` / бросит исключение в `getMember`.
- Рабочий вариант для M4: `STR_SECTOID_NONCOM` (месяцы 12-23 по рулсету; в месяцах 24-35 рулсет даёт ELITE, а он невалиден для этой карты). Решение за автором мерки: либо заменить расу M4 на NONCOM, либо заменить развёртывание.

## Основные сценарии

| № | развёртывание | в документе | ID для OXCE_AI_RACE | статус | рулсет даёт |
|---|---|---|---|---|---|
| E1 | STR_BASE_DEFENSE | SECTOID_NONCOM | `STR_SECTOID_NONCOM` | ok | в стадии: STR_SECTOID 100%, STR_RATMEN 100%, STR_CANNYS 100%, STR_BANDIT 100% ... |
| E2 | STR_VESSEL_BANDIT_CAR | BANDIT | `STR_BANDIT` | ok | в стадии: STR_BANDIT 65%, STR_BANDIT_ROBBERS 60%, STR_RATMEN 30%, STR_BANDIT_VILLAGE 30% ... |
| E3 | STR_VESSEL_NIN_APC | NINJA | `STR_NINJA` | ok | в стадии: STR_NINJA 100% |
| E4 | STR_LARGE_SCOUT | SECTOID_NONCOM | `STR_SECTOID_NONCOM` | ok | в стадии: STR_FLOATER_INDUSTRIAL 55%, STR_SECTOID_NONCOM 41%, STR_CHURCH_NONCOM 40%, STR_FLOATER_NONCOM 35% ... |
| E5 | STR_VESSEL_RAIDER | RAIDER | `STR_RAIDER` | ok | в стадии: STR_RAIDER 70%, STR_SPARTANS 25%, STR_ZOMBIE_SMART 5% |
| E6 | STR_LOC_RATLING_VILLAGE | RATMEN | `STR_RATMEN` | ok | в стадии: STR_RATMEN 95%, STR_ZOMBIE 5% |
| E7 | STR_LOC_GUILD_OUTPOST_TEMPERATE | FLOATER_NONCOM | `STR_FLOATER_NONCOM` | ok | в стадии: STR_FLOATER_NONCOM 95%, STR_ZOMBIE 5% |
| E8 | STR_LOC_SINS_OF_THE_FATHER | CHURCH_NONCOM | `STR_CHURCH_NONCOM` | ok | в стадии: STR_CHURCH_NONCOM 100% |
| E9 | STR_PUNK_TERROR | BANDIT_ROBBERS | `STR_BANDIT_ROBBERS` | ok | в стадии: STR_BANDIT_ROBBERS 100% |
| E10 | STR_LOC_HIGHWAY_STATION | BANDIT | `STR_BANDIT` | ok | в стадии: STR_BANDIT 100% |
| E11 | STR_LOC_CRACKHOUSE | BANDIT_TOWN | `STR_BANDIT_TOWN` | ok | в стадии: STR_BANDIT_TOWN 100% |
| E12 | STR_LOC_BANDIT_CAMP_TEMPERATE | BANDIT_VILLAGE | `STR_BANDIT_VILLAGE` | ok | в стадии: STR_BANDIT_VILLAGE 100%, STR_ZOMBIE 15% |
| M1 | STR_BASE_DEFENSE | NINJA | `STR_NINJA` | ok | в стадии: STR_SECTOID 100%, STR_RATMEN 100%, STR_CANNYS 100%, STR_BANDIT 100% ... |
| M2 | STR_GOVT_BASE_DEFENSE | NINJA | `STR_NINJA` | ok | в стадии: STR_NINJA 100% |
| M3 | STR_ERIDIAN_TERROR | ERIDIAN | `STR_ERIDIAN` | ok | в стадии: STR_ERIDIAN 100% |
| M4 | STR_VESSEL_LABSHIP | SECTOID_ELITE | `STR_SECTOID_ELITE` | не выбирается стендом | в стадии: STR_SECTOID_NONCOM 100%, STR_SECTOID_ELITE 100% |
| M5 | STR_NINJA_BASE_OUTPOST_ASSAULT | уточнить (в истории UNKNOWN) | `STR_NINJA` | ok | в стадии: STR_NINJA 100% |
| M6 | STR_VESSEL_FRIGATE | MUTON | `STR_MUTON` | ok | в стадии: STR_MUTON 100%, STR_SECTOID_TERROR 100%, STR_SNAKEMAN 100%, STR_FLOATER 100% ... |
| M7 | STR_VESSEL_GUNSHIP | SNAKEMAN | `STR_SNAKEMAN` | ok | в стадии: STR_SECTOID_TERROR 100%, STR_FLOATER 100%, STR_SNAKEMAN 100%, STR_ETHEREAL 100% ... |
| M8 | STR_LOC_HUMANIST_VILLA | MIXED_KKK | `STR_MIXED_KKK` | ok | в стадии: STR_MIXED_KKK 100% |
| M9 | STR_SEA_DEVILS_REEF | DEEP_ONE | `STR_DEEP_ONE` | ok | в стадии: STR_DEEP_ONE 100% |
| M10 | STR_LOC_DOOMED_FARM2 | DOOM | `STR_DOOM` | ok | в стадии: STR_DOOM 100% |
| M11 | STR_LOC_CATACOMBS_UNDERGROUND_PRESS | ZOMBIE_VAMPIRES | `STR_ZOMBIE_VAMPIRES` | ok | в стадии: STR_ZOMBIE_VAMPIRES 20%, STR_ZOMBIE 15%, STR_DEMON 15%, STR_RACE_RAT 15% ... |
| M12 | STR_VESSEL_NIN_APC | NINJA | `STR_NINJA` | ok | в стадии: STR_NINJA 100% |
| L1 | STR_VESSEL_GUNSHIP | FLOATER_ELITE | `STR_FLOATER_ELITE` | ok | в стадии: STR_SECTOID_TERROR 100%, STR_FLOATER 100%, STR_SNAKEMAN 100%, STR_ETHEREAL 100% ... |
| L2 | STR_VESSEL_NIN_LANDCRUISER_BA | NINJA | `STR_NINJA` | ok | в стадии: STR_NINJA 100% |
| L3 | STR_SUPPLY_SHIP | FLOATER | `STR_FLOATER` | ok | в стадии: STR_MUTON 100%, STR_SECTOID_TERROR 100%, STR_SNAKEMAN 100%, STR_FLOATER 100% |
| L4 | STR_BASE_DEFENSE | DOOM | `STR_DOOM` | ok | в стадии: STR_RATMEN 100%, STR_CANNYS 100%, STR_BANDIT 100%, STR_DOOM 100% ... |
| L5 | STR_LOC_GUNS_OF_THE_PATRIOTS_BLACKMARCH | NAZIS | `STR_NAZIS` | ok | в стадии: STR_NAZIS 100% |
| L6 | STR_VESSEL_HEAVY_GUNSHIP | MUTON | `STR_MUTON` | ok | в стадии: STR_SECTOID_TERROR 100%, STR_FLOATER 100%, STR_SNAKEMAN 100%, STR_MUTON 100% ... |
| L7 | STR_VESSEL_BOMBER | FLOATER_ELITE | `STR_FLOATER_ELITE` | ok | в стадии: STR_MUTON 36%, STR_SECTOID_ELITE 30%, STR_FLOATER_ELITE 30%, STR_SECTOID 20% ... |
| L8 | STR_BATTLESHIP | ETHEREAL | `STR_ETHEREAL` | ok | в стадии: STR_MUTON 100%, STR_SECTOID_TERROR 100%, STR_SNAKEMAN 100%, STR_FLOATER 100% ... |
| L9 | STR_VESSEL_USO_HEAVY_CRUISER | DEEP_ONE | `STR_DEEP_ONE` | ok | в стадии: STR_DEEP_ONE 100% |
| L10 | STR_LOC_RITUAL_CAVE | RATMEN | `STR_RATMEN` | ok | в стадии: STR_RATMEN 95%, STR_ZOMBIE 5% |
| L11 | STR_LOC_SMUGGLER_LAIR | SMUGGLER | `STR_SMUGGLER` | ok | в стадии: STR_SMUGGLER 100% |
| L12 | STR_LOC_PIRATE_CRUISE | DEEP_ONE | `STR_DEEP_ONE` | ok | в стадии: STR_DEEP_ONE 100% |

## Запасные

| № | развёртывание | в документе | ID для OXCE_AI_RACE | статус | рулсет даёт |
|---|---|---|---|---|---|
| E-з1 | STR_VESSEL_GOVSHIP | GOVT | `STR_GOVT` | ok | в стадии: STR_GOVT_ELITES 100%, STR_GOVT 90%, STR_ZOMBIE_SMART 10% |
| E-з2 | STR_LOC_HUMANIST_VILLA | MIXED_KKK | `STR_MIXED_KKK` | ok | в стадии: STR_MIXED_KKK 100% |
| E-з3 | STR_VESSEL_CRASHPLANE | CANNYS | `STR_CANNYS` | ok | в стадии: STR_CANNYS 100% |
| E-з4 | STR_LOC_OLD_FORT_DEFENSE | BANDIT_ELITE | `STR_BANDIT_ELITE` | ok | в стадии: STR_BANDIT_ELITE 100% |
| M-з1 | STR_LOC_SINS_OF_THE_FATHER | CHURCH_NONCOM | `STR_CHURCH_NONCOM` | ok | в стадии: STR_CHURCH_NONCOM 100% |
| M-з2 | STR_HARVESTER | SNAKEMAN | `STR_SNAKEMAN` | ok | в стадии: STR_SNAKEMAN 100%, STR_CHURCH_NONCOM 50% |
| M-з3 | STR_VESSEL_HEAVY_GUNSHIP | MUTON | `STR_MUTON` | ok | в стадии: STR_SECTOID_TERROR 100%, STR_FLOATER 100%, STR_SNAKEMAN 100%, STR_MUTON 100% ... |
| M-з4 | STR_NINJA_RAID_SITE | NINJA | `STR_NINJA` | ok | в стадии: STR_NINJA 100% |
| L-з1 | STR_VESSEL_HEAVY_FREIGHTER | FLOATER | `STR_FLOATER` | ok | в стадии: STR_FLOATER 100% |
| L-з2 | STR_TERROR_SHIP | FLOATER_ELITE | `STR_FLOATER_ELITE` | ok | в стадии: STR_SECTOID_TERROR 100%, STR_FLOATER 100%, STR_SNAKEMAN 100%, STR_ETHEREAL 100% ... |
| L-з3 | STR_LOC_ACADEMY_TOWN_TEMPERATE | SECTOID_NONCOM | `STR_SECTOID_NONCOM` | ok | в стадии: STR_SECTOID_NONCOM 100% |
| L-з4 | STR_VESSEL_HARBINGER_OF_DOOM | DOOM | `STR_DOOM` | ok | в стадии: STR_DOOM 100% |

## Проблемные (подробно)

### M4 STR_VESSEL_LABSHIP - не выбирается стендом

- раса в документе: `SECTOID_ELITE`, ID: `STR_SECTOID_ELITE`
- рулсет даёт: в стадии: STR_SECTOID_NONCOM 100%, STR_SECTOID_ELITE 100%
- замечания: в списке стенда расы НЕТ: членов 8 <= maxAlienRank 12 - OXCE_AI_RACE промахнётся | членов 8, maxAlienRank 12 | движок на этом развёртывании с этой расой бросит исключение (rank 12 >= членов 8, deployAliens/getMember) | waves.ufo=STR_VESSEL_LABSHIP: STR_MISSION_LABSHIP | СТЕНД: миссии с siteType=это развёртывание нет - без OXCE_AI_RACE раса случайная | при этом рулсет для этой стадии именно эту расу и даёт: стендом её закрепить нельзя (молча случайная)
- источник: alienDeployments STR_VESSEL_LABSHIP @ Ruleset/Piratez_Factions.rul:96115; alienRaces STR_SECTOID_ELITE @ Ruleset/Piratez_Factions.rul:25260; alienMissions STR_MISSION_LABSHIP.raceWeights @ Ruleset/Piratez_Factions.rul:38334

## Источники по всем строкам

Полная таблица с источниками, замечаниями и долями - `p6_races.tsv`.
