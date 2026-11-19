# Приложение к форензик-аудиту: указатели на факты

Для каждого ключевого заключения: код, документ, журнал или анализатор. Номера строк: дерево `hd-render` на 07.11.2026; «up» — чистый upstream OXCE 8.7.1 (`441cae1b0`), временная копия AIModule в scratchpad сессии, повторить: `git show 441cae1b0:src/Battlescape/AIModule.cpp`.

## A. Код

| Метка | Что | Где |
|---|---|---|
| A-01 | Диспетчер | `src/Battlescape/BattlescapeGame.cpp:222 think`, `:388 handleAI`, `:396-399` ОВ≤5, `:405-436` следующий юнит и `_AISecondMove`, `:471-488` BattleAction, `think`, RETHINK, `:568-615` ходьба, `:617-639` атаки, `:646-677` BA_NONE |
| A-02 | Смерть и перезапуск обхода | `BattlescapeGame.cpp:1449 popState`, `:1499`, `:1556-1565`, `:928 checkForCasualties`, `:2581 convertUnit` |
| A-03 | Резерв | `BattlescapeGame.cpp:1609 checkReservedTU`, `:1628` только стенд, `:1637-1639` 33/40/50 %; `AIModule.cpp:1213,1263-1269,6370`; `UnitWalkBState.cpp:346` |
| A-04 | Выбор юнита | `src/Savegame/SavedBattleGame.cpp:1005 selectPlayerUnit`, `:1007-1010` setReselect; `BattleUnit.cpp:5509 isSelectable` |
| A-05 | Конец хода, чит | `SavedBattleGame.cpp:1560 endTurn`, `:1620-1623 _cheating`, `:1635 updateTurnsSince`, `:1636-1639` чит видимости; `AlienDeployment.cpp:42` cheatTurn=20 |
| A-06 | dontReselect | `BattleUnit.cpp:3100,3108,3118`, `:2965`, `:859`; `UnitWalkBState.cpp:530,553`; `TileEngine.cpp:5321`; `BattlescapeState.cpp:1563,3433`; `SavedBattleGame.cpp:2244,2265` |
| A-07 | Решение бойца | up `AIModule.cpp`: think 422-656, setupPatrol 732, setupAmbush 906, setupAttack 1023, setupEscape 1114, selectNearestTarget 1376 (своё `visible` :1385), selectSpottedUnitForSniper 1617, scoreFiringMode 1693-1785, evaluateAIMode 1790, findFirePoint 2046, meleeAction 2250, projectileAction 2459, grenadeAction 2643, psiAction 2713 (проверка зрения :2759), getTargetAttackWeight 2933, getSpottingUnits 1338 |
| A-08 | Патруль | `SavedBattleGame.cpp:2407 getPatrolNode`: враг в выборе не участвует |
| A-09 | Реакция | `TileEngine.cpp:2569 checkReactionFire`, `:2625 getSpottingUnits(unit)`, `:2754 getReactor`, `:2784 determineReactionType`, `:2904 tryReaction` |
| A-10 | Кровотечение и перезарядка | `BattleUnit.cpp:2864 prepareHealth`, `:2953 prepareNewTurn`, `:3010 updateUnitStats`, `:3485` reloadAmmo в think, `:3969 reloadAmmo`; `AIModule.cpp:735 medikit_think` (только на себя) |
| A-11 | Сохранение | `AIModule.cpp:591,615`; `SavedBattleGame.cpp:289-304`; `BattleUnit.cpp:859` |
| A-12 | Журнал | `AiProbe.cpp:3825-3846` `seen=` = `getTurnsSinceSpottedByFaction==0`; `:5226-5250` AISTATE `sees`, `known`; `:1557-1626` AIEXEC `dmg/fdmg`; `AiCandidates.cpp:98` `p`=`getFiringAccuracy`, `:101-126` `lof` |
| A-13 | Brutal, только справка | `E:\BrutalAI\src\Battlescape\AIModule.cpp:3345 brutalThink`, `:3349-3454` очередь по достижимым; `docs/research/brutal-ai-internals.md`; R-028 |
| A-14 | Опции | `src/Engine/Options.cpp:543-545` |
| A-15 | Честность знания | `AiProbe.cpp:416` `fairKnowledge()` в выпуске 0; `:3921-3957` `lastSeen` на стенде; `:5955-5957` флаг стенда; перезарядка `BattleUnit.cpp:4007`, аптечка `:3492,3496` |

## B. Правила Пираток

`Пиратки/Dioxine_XPiratez/user/mods/Piratez/Ruleset/Piratez_Globals.rul:9171` блок `ai`, глобалы; юниты `Piratez.rul`. Сводка: `forensic/data/piratez_rules.txt` (436 юнитов, 4007 предметов). Анализатор `piratez_rules.py` текстовый, YAML не загружает; значения, перекрытые позднейшими модами, не учтены.

## C. Архив и анализаторы

Все в `docs/research/ai-mechanics/forensic/analyzers/`, данные в `forensic/data/`. Входные архивы не менялись.

| Заключение | Анализатор и результат | Вход |
|---|---|---|
| Бюджет ОВ, решения по src, причины нулевых, участие, потери, потоки HP | `d0_census.py`, `census_report.py` → `census_d0p.txt`, `census_sfD.txt` | `E:\OXCE_AIWorker\battles_archive\commander_2026-10-29\res_d0p.zip`; `side_first_v0\res\res_sfF.zip` фильтр `_D_` |
| Режим×дистанция, оружие, цели, поведение по информации, убийцы, FF, пси | `d0_census2.py` → `census2_*.txt` | те же |
| Воронка бойцо-ходов, «кто способен навредить», экспозиция, потолок рычага | `d0_census3.py` → `census3_*.txt` | те же |
| Случаи A, B, D | `case_view.py <zip> <бой> <ход> <юнит>` | `res_d0p.zip`: `d0p_D_L4_s1 2 1000035`, `d0p_D_L2_s2 2 1000016`, `d0p_D_L8_s1 1 1000000,1000001` |
| Случай C | журнал `out/d0p_D_L5_s2/openxcom.log.gz`, записи между AIREC и AIEXEC `rec=58`; `arena/d0p_D_L5_s2.tsv` | `res_d0p.zip` |
| Контроль без боёв d0p | `d0_census3.py <out> sfD34 res_sfF.zip '_D_.*_s[34]'` → `census3_sfD34.txt` | 8 боёв с другими сидами |
| d0p без M1 | `d0_census3.py <out> d0pNoM1 res_d0p.zip '^(?!.*_M1_)'` → `census3_d0pNoM1.txt` | 46 боёв |
| Экспозиция в серии PV | `d0_census3.py <out> pvD0 pv_all.zip 'D0_'` → `census3_pvD0.txt`; в этом архиве решений нет, годится только раздел экспозиции | `real_ai_p0_vs_p1_2026-10-27/results/pv_all.zip` |
| D0 разных серий — одни и те же бои | `d0_identity.py`: 48/48 `scpa_D` и `svo_SO`, 8/16 `sfF_D` (сид, ход, потери, число решений) | `arena/*.tsv` |

### Определения в воронке (`d0_census3.py`)
- **Атаковал.** Хоть одно решение типа 6,7,8,9,10,12,16.
- **Линия огня по засечённой стороной цели.** Кандидат `k=a`, тип 7,8,9,10,12, `lof=1`, цель-игрок (`u<1000000`), цена ≤ ОВ, `u` в `seen=` последнего AIDECIDE бойца. **Это не собственное зрение.** Дальность оружия и штраф за отсутствие зрения не учтены.
- **Своё зрение на старте.** Цель в `sees` из AISTATE `aistart` этого хода.
- **Своё зрение в конце.** В `sees` из AISTATE `pstart` следующего хода есть игрок, и остатка ОВ после последнего действия хватает на самую дешёвую дальнюю атаку (типы 7, 8, 9, 12; рукопашная исключена: первая версия с ней завышала оценку вдвое). Зрение внутри хода журнал не пишет.
- **Оценка рычага.** Сумма по таким бойцо-ходам средней отдачи этого оружия на атаку по игроку в этом бою. Один выстрел, без дальности, без штрафа и без ответного огня. Это порядок величины, не прогноз прироста. «Любая линия огня» дополнительно считает цели, засечённые стороной.
- **Экспозиция.** `seenby>0` в AISTATE `pstart`; потери — разница HP до `aistart` того же номера хода; в обе стороны могут быть ошибки на ходах с превращениями. Смешение с близостью к игроку не устранено.
- **Известен ближе 15.** `near` из AISTATE `aistart` (сторона, `==0`), не меняется во время хода.

### Что считается вместе и может смещать
- `dmg` в AIEXEC смешан с гражданскими и за окно записи (R-711); в `census3` урон считается только у атак с выбранным кандидатом-игроком, поэтому он ниже общего.
- Взрывы и реакции не приписаны атаке: потолок и «кто способен навредить» занижают гранатомётчиков.
- 46 % урона по игроку в двух боях M1, отряд 60.
- Выборка d0p: месяц 60+; бот; один набор сидов на 24 сценария, тот же, что у D0 в Scheduler и STRIKE. `sfF_D`: 16 боёв, 4 сценария (L4, L8, M3, M8), сиды s1, s2 совпадают с d0p, независимы только s3, s4 (8 боёв). Эти 4 сценария отличаются от среднего, поэтому расхождение контроля (например 1,5 % против 7,7 %) говорит и о сценариях, и о случайности: разделить их на 8 боях нельзя.

## D. Документы

| Метка | Что | Файл |
|---|---|---|
| D-1 | Реестр 27.09–23.10 | `forensic/registry_1_sep27_oct23.md` |
| D-2 | Реестр 27.10–30.10 | `forensic/registry_2_oct27_oct30.md` |
| D-3 | Реестр 05.11–07.11 | `forensic/registry_3_nov05_nov07.md` |
| D-4 | Определение D0, P0, U0, DS | `docs/research/ai-mechanics/AI_BASELINE_0B_FINAL.md` |
| D-5 | Живой игрок против бота; снимки людей (стр. 379) | `AUDIT-STAGE-1-BENCHMARK-DESIGN.md:47-66,379` |
| D-6 | Различия DEV/выпуск | `AUDIT-DEV-RELEASE-DIFF-2026-10-23.md`, `AUDIT-VERIFY-2026-10-23.md` |
| D-7 | Мощность | `POWER-CLUSTER-2026-10-27.md`; `AI_FORGE_WP3`-отчёт |
| D-8 | Прочие результаты | `AI_ACTION_SELECTION_RESULT.md`, `AI_FORGE_WP1/2/2_1_RESULT.md`, остальные через D-2 и D-3 |
| D-9 | Контракт честности | `docs/DECISIONS.md:2464-2475` (27.09), `:2456-2460` (Brutal только справка); инфраструктура знания `docs/research/ai-knowledge-infra.md` (прочитаны только заголовки) |
| D-10 | Грабли | `python tools/rake.py show R-717` (наступал 2 раза, защиты нет); R-025, R-028, R-120, R-206, R-434, R-635, R-674, R-686, R-703, R-711, R-735, R-767, R-795, R-800 |

## E. Числа, взятые только из отчётов (не пересчитывал)

WP3 (SD 188–207, 150–158 пар, 3 общих события); PV (+0,3 п.п. [−3,2; +4,7]); POWER-CLUSTER (17,8 % / 2 %); T1, T2 (2 из 4376, −0,8 п.п.); ACTION_SELECTION (11 из 514); STRIKE (81/81, 12,3 % / 18,6 %, 63→56, 67 из 746); TD (50/0); MLT (27/56, 4/15); FCS (42 %); все HIVE; UA T9 343–371 мс; COORDINATED 0/4; TTS 24 996→16; HDE (129 из 4452, 34 %, FF 14 461); SF (500→493 [−208; +182], 467→165, ≥36); WP4 (76 из 100); E37–E60 из `registry_1`; S1 (живой игрок). При использовании в споре проверять по первоисточнику.

## F. Что не сверено с первоисточником, хотя на него опираюсь

- Семь расхождений стенд/игрок: `AI-HOW-IT-WORKS` §14 не прочитан.
- Состав окружения cp1n: только через VER.
- M4/M7/M10 «без оружия»: поле `weapon=-` у бойцов в `AISTATE`; инвентарь не проверял.
- Авторство директив: в репозитории нет.
