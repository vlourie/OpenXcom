# OXCE-HD — статический аудит ИИ игрока против OXCE v8.7.1 (27.10.2026)

**Метод.** Только чтение кода и git. Сборок и запуска игры не было, дерево не менялось. Сравнение `git diff v8.7.1 HEAD`
(для AIModule — `--diff-algorithm=patience -U0`: 111 строк оригинала, которых нет в HEAD, разобраны все).
Релиз = `OXCE_AI_DEV` не определён (`CMakeLists.txt:25`, по умолчанию OFF), опции игрока по умолчанию:
`oxceBetterAi=false`, `oxceBetterAiFixes=true`, `oxceBetterAiAi3=false` (`Options.cpp:536–538`).
**HEAD: 2584494de** (в ходе аудита сдвинулся с dacd5060a; между ними менялись только `src/Engine/HdUiArt.cpp` и
`src/Engine/Screen.cpp` — графика; файлы ИИ те же). Номера строк — по рабочему дереву; файлы ИИ в нём не отличаются от HEAD
(в дереве есть правка только `src/Engine/Screen.cpp` и `Surface.cpp`, графика). База форка совпадает с тегом v8.7.1 (`03421b28a`).

Ключ: `betterAi()` (`AiProbe.cpp:94`) = `{ fixes = oxceBetterAi && oxceBetterAiFixes, ai3 = oxceBetterAi && oxceBetterAiAi3 }`,
читается один раз (static) — смена опций действует после перезапуска. **При `oxceBetterAi=false` обе величины false при любых
значениях двух других опций.**

---

## 1. Вердикт

**Релиз с BetterAI выкл = OXCE v8.7.1 по коду решений ИИ: ДА с оговорками** (оговорки — не решения ИИ и не порядок RNG ИИ,
но видны в бою; см. ниже). Все изменения в `AIModule.cpp`, `Pathfinding.cpp`, `TileEngine.cpp`, `BattlescapeGame.cpp`
(ветка `handleAI`), `BattleUnit.cpp`, `SavedBattleGame.cpp`, `UnitWalkBState.cpp` либо вынесены за переключатель, значение
которого в релизе равно значению оригинала (константа-заглушка `AiProbe.cpp:84–430`), либо дают то же самое по значению
(`AiKnownPlace` с пустым `_moved`, `fairKnowledge()==0`). Порядок вызовов RNG ИИ (`RNG::shuffle` в findFirePoint/setupEscape,
`RNG::generate(0,20)` в selectRandomTarget, `RNG::generate(-im,im)` в extendedFireModeChoice, `RNG::percent` в setupAttack,
`RNG::generate(1,…)` в think) на прежних местах; единственный новый вызов `RNG::generate(1, ++ambTies)` (`AIModule.cpp:2329`)
под `BC_AMB_BEST`, а `bestCell()` в релизе 0 (`AiProbe.cpp:168`).

Оговорки:

1. **Взрыв мины/гранаты с таймером в конце хода** (`BattlescapeGame.cpp:761`): z центра взрыва зажат сверху в
   `getMapSizeZ()*24-1`. Верхний уровень + высокая приподнятая плитка + высокий юнит (`-terrainLevel + height/2 ≥ 24`) раньше давали
   центр над картой. Редкий случай, но это изменение механики (правило 2 проекта), одинаково для всех сторон. Не под опцией.
2. **Упор назад** (`UnitWalkBState.cpp:74`, `Pathfinding.cpp:1593/1971`, `BattleUnit.cpp:1196`): TU-цена и поворот пути, начинающегося
   строго «за спиной», только для юнита игрока (`FACTION_PLAYER`), ходом игрока, при `armor.allowsReverse` (по умолчанию false;
   включается пользовательским модом `piratez_tank_reverse` в установке Пираток). ИИ врага не затрагивается (`getFaction()==PLAYER`).
   Это механика игрока, не ИИ.
3. **Опции HD-темпа по умолчанию ВКЛ**: `oxceHdQuickFlight`, `oxceHdLooseHits` (`Options.cpp:567–568`), `oxceHdFrameSkip=4`.
   Утверждение «только картинка и темп» держится на том, что RNG не читается в `Map`/`Explosion`/`Camera` (grep, пусто);
   вихрь RNG снаряда (`Projectile.cpp:662`) считается на тех же шагах. Статикой порядок RNG между кадрами **не доказан** (см. п. 5).
4. Рабочее дерево отличается от HEAD правками графики (`Screen.cpp`, `Surface.cpp`); на ИИ не влияют.

---

## 2. Таблица проверенных фрагментов

Колонки: файл:строка (HEAD) — что изменено — переключатель — значение в релизе — вердикт.
Вердикт: **inert** — исполняется тот же код/то же значение, что в v8.7.1; **не ИИ** — графика, звук, камера, журнал;
**ИЗМЕНЯЕТ** — отдельной строкой.

### 2.1. Строки, которые ИЗМЕНЯЮТ поведение (механика, не решения ИИ)

| № | файл:строка | что | переключатель | в релизе | вердикт |
|---|---|---|---|---|---|
| И1 | `BattlescapeGame.cpp:761` | центр взрыва таймерной гранаты на плитке зажат по z в `mapSizeZ*24-1` | нет | всегда исполняется | **ИЗМЕНЯЕТ** (крайний случай; не ИИ; для всех сторон) |
| И2 | `UnitWalkBState.cpp:74–77,87,349`, `Pathfinding.cpp:1593,1971`, `BattleUnit.cpp:1196,1236–1245`, `BattleUnit.h:127,281–285` | ход задом: путь с первым шагом «за спиной» идёт без поворота, корпус не разворачивается, цена пути без поворота | `Armor::allowsReverse` (нет в v8.7.1, `Armor.cpp:134`) + `FACTION_PLAYER` + `getPanicHandled()` + `!botTurn` | false, пока мод `piratez_tank_reverse` не включён | **ИЗМЕНЯЕТ** при включённом моде; только юниты игрока; ИИ врага — нет |
| И3 | `BattlescapeGame.cpp:2526–2565` (`catchThrownItem`, вызов `ProjectileFlyBState.cpp:733`) | брошенный предмет подхватывает боец игрока на плитке падения | `Options::oxceCatchThrown` | false (`Options.cpp:514`) | inert по умолчанию; при включении ИЗМЕНЯЕТ (ход игрока) |
| И4 | `BattlescapeGame.cpp:199,233,825`, `ExplosionBState.cpp:531`, `Map.cpp`, `UnitFallBState.cpp:271`, `BattlescapeGenerator.cpp:765,962`, `SavedBattleGame.cpp:427–474,676–692`, `CollapsePilot.cpp:1583,1594,1658,1914` | обрушение зданий | `Options::oxceCollapse` | false (`Options.inc.h:318`); ключ сейва читается/пишется только при `oxceCollapse` | inert по умолчанию; при включении ИЗМЕНЯЕТ (механика, не ИИ). Без RNG |

### 2.2. AIModule.cpp (111 изменённых строк оригинала, все разобраны) — inert

| файл:строка | что | переключатель | значение в релизе | вердикт |
|---|---|---|---|---|
| `AIModule.cpp:50–155`, `AIModule.h:53,71` | класс `AiKnownPlace`: `_moved` пуст, `unitOn(tile)==tile->getUnit()`, `any()==false` | `fairKnowledge()` | 0 (`AiProbe.cpp:415`) | inert |
| `:664–703` (dont_think, «леерой») | `meleeActionLeeroy` стал `int`; ветка `rejected>0` | `ZERO_EFFECT` | `param(...,0)`=0 → `zeroEffectReject` всегда false → `rejected==0` (`:4978–5036`, `:6507`) | inert. **Ловушка:** `param("OXCE_AI_LEEROY_STALE_FIX", 1)` (`:679`) по умолчанию 1, но читается только при `rejected>0` |
| `:995–1016` | `_wasHitBy.clear()` → `if(!oxceFixes()) clear()` | O14 | `oxceFixes()==false` → `clear()` как в оригинале | inert |
| `:1066–1082`, функция `reachableWithAttack` | прямой `findReachable(...)` обёрнут в функцию; запоминание стоимости клеток | `BC_REACHCOST` (`bestCell()`) | 0: `_reachCost` не заполняется | inert (тот же вызов findReachable, в том же месте) |
| `:1094–1099, :1118, :1217, :1380` | условие эскейпа `(!_escapeTUs \|\| tactical)`; `escapePlanBroken()`; `probeSlot` | `tactics/careful` O4 `staleEscapeFix` | false/false/false | inert |
| `:1213, :1303, :1318` | `allowsKneeling(false)` → `allowsKneeling(kneelDefault)` | `careful()` | false → `kneelDefault=false` | inert |
| `:2013–2060` (setupPatrol) | `(!oxceFixes \|\| _fromNode)`; окно 9→`span`; O8, O12 | O8, O12 `oxceFixes` | false → 9×9, прежнее условие | inert |
| `:1956–1964` | проверка устаревшего узла патруля | O5 `stalePatrolNode()`, `staleExact()` | false/0 | inert |
| `:2200–2340` (setupAmbush) | `ambLevels`, `ambBest`, `memo`, `cellProf`; `RNG::generate(1,++ambTies)` на `:2329` | `BC_LEVELS`, `BC_AMB_BEST`, `ambushMemo()` | `bestCell()==0`, `ambushMemo()==0` | inert, RNG-вызов недостижим |
| `:2430–2470, :2512, :5055, :6068` | `botSpecial`, `wpMeleeOn`; условия `_knownEnemies \|\| botSpecial`, `!botSpecial && getUnitRules()` | `BOT_SPECIAL`, `BOT_WP_MELEE` и `careful()` | param=0, careful=false → условия оригинала; `RNG::percent(sniperPercentage)` (`:2470`) на прежнем месте | inert |
| `:2564, :3902–3922` | результат `findFirePoint()` и `selectRandomTarget() && findFirePoint()` сохранён в `found/picked` ради `probeSlot` | — | `probeMark/probeSlot` только читают | inert (порядок вызовов и RNG тот же: `picked && findFirePoint()`) |
| `:2605–2812` (setupEscape) | `selectNearestTarget` в начале; `escapeAggroAt`; `tries&1`; `escapeReachFirst`; O1 `escapeSignFix`; O13 `lastCover` | O1, O13 | false | inert. `RNG::shuffle(randomTileSearch)` на прежнем месте |
| `:2711–2722` | знак расстояния при оценке клетки эскейпа | O1 `escapeSignFix()` | false → ветка оригинала `else if (dist>=distanceFromTarget)` | inert |
| `:2838–2845` | `_unit->lastCover = bestTile` | O13 `oxceFixes()` | false → не пишется | inert |
| `:2985–3030` (selectNearestTarget) | `validTarget && visible` → `fairNearestMode` + `AiKnownPlace` | `fairKnowledge()` | `fairNearestMode` возвращает 1 (`:3050`) → условие то же, порядок вызовов (validTarget, потом visible) тот же | inert |
| `:3101–3114` (…Leeroy), `:3147, :3175, :3222, :3290` | `Position::distance2d`/`validMeleeRange`/`getDirectionTo` через `knownPos/knownMeleeRange` | `knownPlace` kind | 0 (kind==0 → истинные позиции) | inert |
| `:3175–3178` selectRandomTarget | `RNG::generate(0,20)` один раз на каждую подходящую цель, как в оригинале | — | порядок тот же (`kind==2` → continue только при fair) | inert |
| `:3361–3392` sniper | `ffSec`, `zeroEffectReject`, `sniperAoeEfficacyReject` | `FF_RISK`, `ZERO_EFFECT`, `SNIPER_AOE_EFFICACY` | 0/0/0 | inert; `RNG::generate(0,n-1)` на `:3388` прежний |
| `:4034` | подход к огневой точке в ближнем бою | `meleeFirepointApproach()` | `betterAi().ai3`=false | inert |
| `:4187–4263` (findFirePoint) | `reachCostAt`, `calculateKnownOccupantV2`, `firePointTerms` | `BC_REACHCOST`, `knownOccupantPathV2()` | `reachCostAt` возвращает -1 (`:~4930`), V2=false | inert; `RNG::shuffle` прежний |
| `:4684–4884` (explosiveEfficacy) | `bpos`/`knownDangerous`/`hypo`/`ffTrade`/`probe` | `fairKnowledge`, `HYPO_LOS`, `FF_RISK`, `blastProbe` | 0 | inert (при kind 0 `bpos==bu->getPosition()`) |
| `:4902–5036` (meleeAction/Leeroy) | O9: `newDistance==1 && (!oxceFixes \|\| …)`, `knownAdjacent` | O9 `oxceFixes()` | false → условие оригинала | inert |
| `:4959` `leeroyHitUnaffordable` | отказ от удара без TU | `LEEROY_TU_FIX` | 0 | inert |
| `:5070–5157` (wayPointAction) | `calculate(...)` через знание, O10 `bot \|\| oxceFixes()` | O10 | false, `bot=false` | inert |
| `:5193–5210` (projectileAction) | `knownPos`, `zeroEffectReject`, `ffLineRisk` | 0 | inert |
| `:5663–5700` (extendedFireModeChoice) | `noise` и `aggro` вынесены в переменные; `fireModeEv` | `FIRE_MODE_EV` | 0 | inert. Порядок: `scoreFiringMode` (без RNG) → `RNG::generate(-im,im)` один раз за режим, как в оригинале |
| `:5741–5746` (grenadeAction) | `knownPos` | kind 0 | inert |
| `:6089` | `std::find(visible)` → `AiProbe::upstreamSees(_unit,bu,0)` | O6 `upstreamVis()` | false → `std::find` по `getVisibleUnits()` как в оригинале | inert |
| `:6260–6267` (meleeAttack) | `lookAt(knownPos…)` | kind 0 | inert |
| `:6337` (validTarget) | `getDangerous()` → `knownDangerous` | `fairKnowledge` | 0 → `getTile()->getDangerous()` | inert |
| `:6440–6462` | радиус узла: `dist<radius \|\| (dist==radius && oxceFixes)` | O11 | false → `dist<radius` | inert |
| `:6507–6520, :6882` | режимы `ZERO_EFFECT`, `SNIPER_AOE`, `ZERO_HONEST` | `param(…,0)` | 0 | inert |
| `AIModule.cpp:358–385, 589–630` | load/save/конструктор | — | **не менялись** (новые поля `_escapePlan`, `_fp*`, `_wasHitByTurn` не сохраняются) | inert: формат сейва ИИ тот же |

### 2.3. Остальные файлы

| файл:строка | что | переключатель | в релизе | вердикт |
|---|---|---|---|---|
| `BattlescapeGame.cpp:233–245` | `think()`: условие `side != PLAYER` → `side != PLAYER \|\| botTurn`; ветка бота | `botTurn()` | false (`AiProbe.cpp:188`) | inert |
| `BattlescapeGame.cpp:384–406` (`handleAI`) | `counterCheck` перед проверкой счётчика | O3 `counterFix()` | false → `counterCheck` false | inert; `maxActions()==2` |
| `BattlescapeGame.cpp:424, 667` | `secondPassWrapped` вместо `getId() <= unit->getId()` | `botTurn` | заглушка = то же сравнение id (`AiProbe.cpp:189`) | inert |
| `BattlescapeGame.cpp:444–470` | `careful` → `setTargetFaction`; `counterOwn`; `tally`; `beforeThink`; `retryBegin` | `careful`, O3, `FAILED_RETRY` | false/false/0 | inert (`retryRule=false`) |
| `BattlescapeGame.cpp:486–500` | `pickUp`, `findBotWeapon` | `ARMS`, `careful` | false | inert |
| `BattlescapeGame.cpp:525–556` | `retryBanned`, `logDecision`, `blockedStepDecide`, `knownOccupant*`, `patrolReuse*` | BLOCKED_STEP (ai3), прочее | пусто/false | inert |
| `BattlescapeGame.cpp:566–600` | `knownOccupantV2Walk`, `blockedStepPlan`, `walkPlanned`, `patrolStunReserve`, `patrolOutOfEnergy`, `spendPatrol` | ai3 и env | false | inert |
| `BattlescapeGame.cpp:639–646, 1104–1115, 1621` | `retryRemember`; `updateHonestKnownPosition(...KILLER_SEEN)`; `reserveAffordable` | `fairKnowledge`, `RESERVE_AFFORDABLE` | `updateHonestKnownPosition` возвращает false (`BattleUnit.cpp:5138`); режим 0 → `reserveAffordable` не вызывается (`:1621` под `reserveAffordableMode()>=1`) | inert |
| `BattlescapeGame.cpp:2122,2190` | `std::find(visible)` → `upstreamSees` | O6 | false → прежний `find` | inert |
| `BattlescapeGame.cpp:196–199, 710, 1004–1010` | `CollapsePilot::begin`, `sideEnds`, `logCasualty` | `oxceCollapse`, заглушки | no-op | inert |
| `TileEngine.cpp:1513–1531` | `seesHostiles` и `updateHonestKnownPosition(...FOV...)` | O6 `upstreamSpot()`, `fairKnowledge` | false/false → условие `unit->getFaction()==PLAYER` оригинала | inert |
| `TileEngine.cpp:1872–1931, 2208–2212, 4848, 4881` | `AiKnownPlace::unitOn/any/knownOn`, `voxelCheckKnown` | `fairKnowledge` | `any()==false` → условие и ветка оригинала | inert |
| `TileEngine.cpp:2218–2330` | `canTargetUnit`: HYPO_LOS | `param("OXCE_AI_HYPO_LOS",0)` | 0 → `diag=false`, остальной код прежний | inert |
| `TileEngine.cpp:2679–2692` | `getSpottingUnits`: `setTurnsSinceSpottedByFaction` и т.д. | O6 `upstreamSpot()` | false | inert |
| `TileEngine.cpp:2931–2937, 2963, 3234–3237, 3429–3605` | `FF_RISK` бит 4; `event`; `blastBefore/After/Begin/Tile/End` | 0 / заглушки | no-op | inert |
| `TileEngine.cpp:1061–1130` | вынесена `unitLightPower` из `calculateUnitLighting` | — | тот же расчёт | inert |
| `TileEngine.cpp:3631–3770` | новая `explosionArea` (показ зоны взрыва, «без RNG») | — | вызывается только показом | не ИИ |
| `Pathfinding.cpp:174–300` | `Trace`/`Ask` (журнал), `_expanded`, `_searchCap`, `_bannedFirst` | `param(TRACE_PATH)`, `pathProf()`, ai3 | false, пусто | inert |
| `Pathfinding.cpp:388–395` | `_totalTUCost = currentNode->getTUCost(missile)` | O2 `astarCostFix()` | false | inert |
| `Pathfinding.cpp:1212–1233` | `isBlocked`: `_probeIgnore`, `upstreamSpot`, `_knownOccupant` | O6, `_knownOccupant==nullptr` | false/0/nullptr | inert |
| `Pathfinding.cpp:1862–1941` | `findReachable`: журнал и `reachWanted` | `pathProf()`, `reachWanted()` | false | inert |
| `Pathfinding.cpp:964–1180` | `probeReach`, `witnessReach`, `settleWitness`, `closedTiles` | вызываются только из `AIModule` под O5/ai3/probe | не вызываются | inert |
| `Pathfinding.cpp:2016–2059` | `keepPathPrefix`, `pathCost` | `#ifdef OXCE_AI_DEV` | в релиз не попадают | — |
| `Pathfinding.cpp:1645` | `setPreviewStep` | `oxceHdPathStretch` | только картинка пути | не ИИ |
| `UnitWalkBState.cpp:205–207, 230–236, 247–343, 385–387, 459, 486–490, 540–545` | `walkFovKeep/Before/After`, `lightSkip`, `walkStop`, `firepointBlocked`, `blockedStepStop`, `postWalkAi/Begin/End` | заглушки; `blockedStepStop` — ai3 | `walkFovKeep=true` (полный FOV), `lightSkip=false` (пересчёт света как в v8.7.1), `postWalkAi=false` | inert |
| `BattleUnit.cpp:763–776, 937–946, 2001–2105, 3458–3469, 5002–5010, 5136–5200` | `_aiSeen`: загрузка (только если ключ есть), сохранение (только при `fairKnowledge()`), `updateHonestKnownPosition` (ранний `return false`), `medikitBefore/After`, `resetTurnsSince` | `fairKnowledge()` | 0 | inert. Ключ `aiSeen` в сейв не пишется |
| `BattleUnit.cpp:1797–1860` | `dmgNote` | `armed` | false | inert (журнал) |
| `SavedBattleGame.cpp:2421–2437` | `getPatrolNode`: O7 порядок выбора узла | O7 `oxceFixes()` | false → ветка оригинала (`else if (!preferred …`) | inert |
| `SavedBattleGame.cpp:2777` | `eyesOnTarget`: `upstreamSees(bu,unit,4)` | O6 | false → `std::find` | inert |
| `SavedBattleGame.cpp:1553, 1595, 1687, 1690` | `turnStage` | заглушка | no-op | inert |
| `SavedBattleGame.cpp:97–99` | `AiCoverMap::reset` | `#ifdef OXCE_AI_DEV` | в релиз не попадает | — |
| `Tile.cpp:224,402,424` | `AiCoverMap::touch` | `g.built==false` | выход сразу | inert |
| `ProjectileFlyBState.cpp:~733`, `Projectile.cpp:51,86–110,515–540` | `shotDivider` (заглушка); скорость снаряда `HdGentle::fireSpeed()`, «быстрый полёт», дым `oxceHdPlainSmoke` с собственным генератором | `oxceGentle`, `oxceHdQuickFlight`, `oxceHdPlainSmoke` | см. оговорку 3 | не ИИ (картинка и темп); RNG-порядок не доказан тестом |
| `ExplosionBState.cpp:52–440` | HD-эффекты (`HdFx`), `_loose` | `oxceHdLooseHits` (ВКЛ) | `_loose=true` для выстрелов, `explode()` вызывается сразу, без ожидания спрайтов | не ИИ; оговорка 3 |
| `Map.cpp`, `Camera` (`focusOn` вместо `centerOnPosition`), `UnitDieBState.cpp`, `MeleeAttackBState.cpp:`, `NextTurnState.cpp`, `InventoryState.cpp`, `InfoboxOKState.cpp`, `ConfirmEndMissionState.cpp`, `BriefingState.cpp`, `StartState.cpp`, `MainMenuState.cpp`, `CrossPlatform.cpp`, `Game.cpp:177` | `autoClose()/fast()/harness()` | заглушки | false | не ИИ (стенд; в релизе нули) |
| `NewBattleState.cpp:664,762` | `RNG::setSeed` при создании тестового боя | «Новый бой» | не кампания | не ИИ |
| `Engine/RNG.cpp/.h` | — | — | **нет разницы** с v8.7.1 | inert |
| `Engine/Feedback.cpp:57`, `HdPilotVoice.cpp:46` | `std::random_device`, `mt19937` | свои генераторы, не `RNG::` | не трогают боевой RNG | не ИИ |

---

## 3. Вопрос 2 — что включает oxceBetterAi=true

Все переключатели читаются из `AiProbe.cpp:84–430` (`betterAi()` строка 94) и опрашиваются по следующим местам.

**BetterAI вкл, Fixes вкл, AI3 выкл (`fixes=true, ai3=false`):**

| код | что | где (HEAD) |
|---|---|---|
| O1 `escapeSignFix` | знак расстояния при оценке клетки отхода | `AIModule.cpp:2712` |
| O2 `astarCostFix` | `_totalTUCost` пути A* = цена терминального узла | `Pathfinding.cpp:391` |
| O3 `counterFix` (COUNTER) | счётчик действий сбрасывается, если его вёл другой юнит, ход или сторона | `BattlescapeGame.cpp:396,454` (`AiProbe.cpp:210–226`) |
| O4 `staleEscapeFix` | сброс плана/резерва отхода, если план сломан | `AIModule.cpp:1003,1099,1217,1380` |
| O5 `stalePatrolNode` + `staleExact()==1` | проверка устаревшего узла патруля (witnessReach там, где доказывает ответ) | `AIModule.cpp:1956,1964` |
| O6 `upstreamSpot` | нейтралы видят врагов; блокировка плитки юнитом, замеченным этим ходом; реакция помечает наблюдателя замеченным | `Pathfinding.cpp:1224`, `TileEngine.cpp:1515,2679` |
| O6 `upstreamVis` | `hasVisibleUnit` вместо `std::find` по списку | `AIModule.cpp:6089`, `BattlescapeGame.cpp:2122,2190`, `BattlescapeState.cpp:2573`, `SavedBattleGame.cpp:2777` |
| O7 | порядок выбора узла патруля по рангу | `SavedBattleGame.cpp:2421` |
| O8 | узел без пути держится занятым до конца попыток | `AIModule.cpp:2013` |
| O9 | `distance2d` без этажа: юнит этажом выше/ниже считался соседним | `AIModule.cpp:4911, 4996` |
| O10 | запуск с ракетницей без маршрута точек не делается | `AIModule.cpp:5149` |
| O11 | юнит на краю взрыва входит в него (`<=`) | `AIModule.cpp:6458` |
| O12 | модуль 10×10 целиком, не 9×9 | `AIModule.cpp:2056` |
| O13 | `lastCover` запоминается | `AIModule.cpp:2838` |
| O14 | «кто попал» хранится до конца хода врага (`_wasHitByTurn` в сейв не пишется) | `AIModule.cpp:1007–1016` |

**+ AI3 вкл (`ai3=true`):**

- `param()` отдаёт таблицу `AI3_PLAYER` (9 записей, `AiProbe.cpp:104`): `ZERO_EFFECT=3`, `ZERO_HONEST=2`, `SNIPER_AOE_EFFICACY=2`,
  `EFFICACY_NO_DIFF=1`, `RESERVE_AFFORDABLE=2`, `HYPO_LOS=1`, `MELEE_FIREPOINT_APPROACH=1`, `LEEROY_STALE_FIX=1`, `LEEROY_TU_FIX=1`;
  читаются: `AIModule.cpp:6507, 6517, 6882, 4732, 679, 4959`; `BattlescapeGame.cpp:1709` (`RESERVE_AFFORDABLE`, действует на резерв ТU в `checkReservedTU`, `:1621`);
  `TileEngine.cpp:2224` (`HYPO_LOS`).
- `meleeFirepointApproach()==true` (`AIModule.cpp:4034`).
- `BLOCKED_STEP` (релизная реализация `AiProbe.cpp:323–395`): запоминание заблокированных первых шагов, вызовы `UnitWalkBState.cpp:387`,
  `BattlescapeGame.cpp:550, 579`, `Pathfinding::setBannedFirst`; `knownRevision` (хэш видимых юнитов и плиток) — `AIModule.cpp:1508,1527`.
- **Не** включается: `FAIR_KNOWLEDGE` (`fairKnowledge()==0` намеренно, отложено 22.10), `LIGHTSKIP`, `WALKFOV_SKIP`, `AMBUSH_MEMO`,
  `ESCAPE_REACH_FIRST`, `BOT_SPECIAL`, `BOT_WP_MELEE`, `PATROL_STUN_PREFIX` (в DEV-профиле они есть, в `AI3_PLAYER` нет).

Комбинации: `B=1,F=0,A=0` = выкл (`fixes=false, ai3=false`); `B=1,F=0,A=1` = AI3 без O1–O14 и без O5; `B=1,F=1,A=1` = всё выше.
Состав включённых переключателей проверен по коду; **что именно меняется в решениях — вне этого аудита** (это предмет серий).

---

## 4. Вопрос 3 — этап «0В»: где DEV решает иначе, чем релиз

### 4.1. Сверка документов AUDIT-DEV-RELEASE-DIFF и AUDIT-VERIFY (23.10)

Проверено по текущему `AiProbe.cpp` (HEAD):

| пункт | верно ли для HEAD | где |
|---|---|---|
| harness / play / active (D01) | **да** | `harness = rawOn("OXCE_AI_PROBE")` `:697`, `play = !harness && ((B && A) \|\| OXCE_AI3_PLAY)` `:703`, `active = harness \|\| play` `:709`. В релизе все три false (`:147–149`) |
| О1–О4, О6 всегда при active (D02) | **да** | `counterFix/astarCostFix/escapeSignFix/staleEscapeFix/upstreamSpot/upstreamVis = active()`: `:1980, 2043, 2049, 2055, 2069, 2075` |
| О7–О14 в play всегда, в harness по `OXCE_AI_OXCE_FIXES` | **да** | `:2063` |
| профиль AI3 стенда 20 записей против 9 | **да** | `AI3_PROFILE` `:438–448` (20 записей), `AI3_PLAYER` `:104` (9) |
| FAIR_KNOWLEDGE в play=1, в релизе 0 | **да** | `:5951–5955` против `:415` |
| BLOCKED_STEP — две реализации | **да**, и разница уточнена: логика записи/сброса/пути в обеих совпадает; DEV дополнительно ведёт счётчики и вызывает `firepointStepSuppressed` только при `OXCE_AI_FIREPOINT_BLOCKED` + `…_V1_INTEROP` (`:5202`), которые в play не доступны (`ai3Env` отдаёт null), в harness — только из окружения | `:5102–5207` против `:323–395` |
| STALE_PATROL_NODE/EXACT: в релизе привязаны к fixes, а не к AI3 | **да** | `:4941, 4998` против `:323, 327` |
| `lightSkip` | **да**: DEV `active() && env LIGHTSKIP && unitLightPower==0`, релиз false | `:732` |
| `beforeThink/logDecision/logState` | **да**: в DEV наблюдатели, в релизе пустые | `:2184, 3796, 5209` |

### 4.2. Чего в документах нет (найдено сейчас)

1. **DEV при `B=1,F=1,A=0` (только «Исправления») = релиз с BetterAI ВЫКЛ, а не релиз с исправлениями.** `play()` требует `oxceBetterAiAi3`
   (`:703`), `active()` false, поэтому О1–О4, О6, О7–О14, О5 выключены (`:1980–2075`, `:4943`). В релизе при тех же опциях они включены
   (`betterAi().fixes`). Комбинацию «только исправления» DEV-сборка по опциям воспроизвести **не может**; только через harness и переменные (п. 4.4).
2. **Серии 22.10 без играемого эталона:** harness не может быть «релиз с BetterAI выкл» — О1–О4, О6 принудительно включены при `active()`.
   (В VERIFY это сказано; здесь подтверждено построчно и показано, что это следствие того, что у них нет собственных переменных.)
3. **В play `ai3Env` отдаёт `null` всем `OXCE_AI_*`, кроме профиля и списка `AI3_ENV_OK`** (`:450–484`), но прямой `getenv` в обход остаётся:
   `maxActions` (`OXCE_AI_ACTIONS`, `:4582`, только `careful`), `battleSeed` (`OXCE_AI_SEED`, `:840`, перезаписывает засев нового боя), `OXCE_AI3_QUIT_TURN`
   (`:897`), `OXCE_AI_RECORD*`. Из них решение меняет только засев боя (не кампания).
4. **`hdPace()`: DEV-harness = false, релиз/play = true** (`:726`): темп снарядов и «свободных» попаданий (`Projectile.cpp:518`,
   `ExplosionBState.cpp:293`). Картинка и темп, но порядок состояний в harness иной, чем у игрока.
5. **Виртуальные часы harness** (`Timer::probeClock`, `Game.cpp:177`) и отключённое автосохранение (`BattlescapeState.cpp:980`), `fast()` — без кадров.
   Решения ИИ часы не читают (в `AIModule.cpp` `std::chrono` стоит только под профильными флагами `cellProf`/`shadow`, `SDL_GetTicks` нет), но это отличие среды.
6. **`active()`-наблюдатели выполняются на каждом решении**: `stateHash`, `probeHash`, `pathOpen`, `logState → updateSightings/threatOf`
   (`canTargetTile`, `voxelCheck`, читают кэш плиток движка). RNG не двигают (`RNG::getSeed` только читает). Пассивность подтверждена
   сериями (VERIFY, cp1o: 38 пар без отличий), но **не доказана построчно**.
7. **Режим `DEV без PROBE и без AI3_PLAY при B=0`**: `active()=false`, все переключатели равны релизным (п. 4.3) — но и все наблюдатели, запись и бот
   (`bot()` требует `active()`, `:523`) отключены.
8. `AiCoverMap::update` на входе `handleAI` (`BattlescapeGame.cpp:388–390`): режим 0 без `OXCE_AI_COVERMAP` → выход сразу; `Tile::touch` → выход при `!g.built`. Пассивно.
9. DEV-реализации, действующие по env внутри harness (решения меняют, в релизе их нет): `BEST_CELL` (`:2398`), `FIREPOINT_BLOCKED*`
   (`:4761, 4799, 4805`), `KNOWN_OCCUPANT_PATH(_V2)` (`:4824, 4869`), `PATROL_STUN_PREFIX`/`ENERGY_PATROL_END` (`:4586–4720`),
   `STALE_EXACT` режимы 2–3 (`:5000`), `TACTICS` (`:780`), `WATCH/HALF/GAP/REVIVE/TURRET/FLEE/ARMS/EVAL` (`careful()`-юниты игрока, на врага не действуют).
   Пока переменные не заданы — выключены.

### 4.3. Таблица соответствия переключателей врага: DEV и релиз при одних опциях

| опции (B,F,A) | релиз | DEV без env | DEV harness (`OXCE_AI_PROBE=1`) | DEV play (`B&&A` или `OXCE_AI3_PLAY`) |
|---|---|---|---|---|
| (0,*,*) | всё выкл | **= релиз** (всё выкл, наблюдатели выкл) | О1–О4, О6 вкл (принудительно) → **≠** | не наступает без `OXCE_AI3_PLAY` |
| (1,0,0) | всё выкл | **= релиз** | ≠ (как выше) | — |
| (1,1,0) | О1–О14 + О5 вкл, AI3 выкл | **≠** (все выкл) | **= релиз** при env `OXCE_AI_OXCE_FIXES=1 OXCE_AI_STALE_PATROL_NODE=1 OXCE_AI_STALE_EXACT=1`, остальные `OXCE_AI_*` не задавать | — |
| (1,0,1) | AI3 (9+BLOCKED_STEP), О1–О14 выкл | ≠ | ≠ (О1–О4, О6 принудительно) | **≠** (О1–О14 и О5 принудительно, профиль 20) |
| (1,1,1) | О1–О14, О5, AI3 без FAIR | ≠ | **= релиз** при env: 9 флагов `AI3_PLAYER` + `OXCE_AI_BLOCKED_STEP=1` + три выше | **≠**: `FAIR_KNOWLEDGE=1`, + LIGHTSKIP, WALKFOV_SKIP, AMBUSH_MEMO, ESCAPE_REACH_FIRST (ускорители; «решения не меняют» — не доказано), PATROL_STUN_PREFIX/BOT_* (только `careful`) |

### 4.4. Ответ: есть ли настройка DEV, где все переключатели врага равны релизным

- **BetterAI выкл:** только «DEV без PROBE/PLAY» (p. 4.3) — равенство по значениям, но без записи, без бота, без наблюдателей.
  **В harness (где работает запись) — нет такой настройки**: О1–О4, О6 завязаны на `active()` без собственных переменных. Для этапа «0В»
  это значит: «релиз-выкл» в стенде с записью воспроизвести нельзя без кода (предложение: дать `counterFix/astarCostFix/escapeSignFix/staleEscapeFix/
  upstreamSpot/upstreamVis` свои переменные, по умолчанию «как сейчас»; код не менялся).
- **BetterAI вкл, Fixes вкл, AI3 выкл:** да, harness + три переменные (таблица 4.3). Остальное (hdPace, часы, наблюдатели) — отличия среды.
- **BetterAI вкл, AI3 вкл:** да по значениям — harness + env 9 флагов + `BLOCKED_STEP=1` + три выше (+ F). Play-режим даёт **другое** (FAIR, ускорители,
  принудительные О1–О14). Комбинация «AI3 без исправлений» (1,0,1) нигде в DEV не воспроизводится.

---

## 5. Что статикой доказать нельзя и чем проверять

| что | почему | чем проверять |
|---|---|---|
| Что бинарный релиз собран из этого кода и без `OXCE_AI_DEV` | в аудите нет exe и лога сборки | `build.ps1`/`release.ps1` уже ищут `OXCE-AI-DEV-BUILD-MARK` в exe; сверка `strings`/поиск метки в выпуске + `git describe` в логе сборки |
| Равенство решений «выкл» с v8.7.1 побайтно | статически видно равенство значений и порядка вызовов, но не побочные эффекты кэшей (`TileEngine` tile cache, `AiKnownPlace`) | собрать v8.7.1 (тег) и релиз HEAD с одним ruleset (Пиратки), загрузить один сейв боя, выставить один засев, прогнать N ходов врага и сравнить: журнал решений (`[AIDECIDE]` нет в релизе → внешний наблюдатель) либо хэш состояния боя (юниты, предметы, `RNG::getSeed`) на границах хода |
| Порядок RNG при HD-темпе (`QuickFlight`, `LooseHits`, `FrameSkip`) | RNG вне `Map/Explosion/Camera` по grep, но порядок между состояниями зависит от стека состояний | тот же бой с опциями ВКЛ/ВЫКЛ, сравнить `RNG::getSeed` в конце каждого хода и итоговые потери |
| Пассивность наблюдателей DEV (`logState`, `threatOf`, `stateHash`) и ускорителей (`LIGHTSKIP`, `WALKFOV_SKIP`, `AMBUSH_MEMO`, `ESCAPE_REACH_FIRST`) | для них нужны сопоставимые прогоны | парные бои «флаг вкл/выкл» с одним засевом, как cp1o в VERIFY; расширить на ускорители |
| `U1…U3`, О7–О14 как исправления — «лучше» или «хуже» | вне статики | серии на сильнейшей фракции по `ai-process-v2` |
| Случай И1 (потолок центра взрыва) | зависит от карт и предметов | поиск в рулсетах Пираток плиток с `terrainLevel ≤ -13` на верхнем уровне; иначе пометить «редко» |
| Влияние `piratez_tank_reverse` на врага | мод игрока, ИИ врага через `getFaction()` отсечён | не нужно; проверить, что мод не отмечен как включённый по умолчанию |
| Действует ли пользовательский `options.cfg` игрока | опции BetterAI могут быть иные | лог запуска (`Options::oxceBetterAi*`) или выгрузка `options.cfg` у игрока |
