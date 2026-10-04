# 01. Ход стороны: от BattlescapeGame::think до действия юнита

Код: коммит `7cd80e284`. Номера строк проверены чтением. Детали режимов здесь не разбираются, только ссылки:
PATROL — `10_patrol.md`, AMBUSH — `11_ambush.md`, огонь — `12_combat_fire.md`, ближний бой, пси и гранаты —
`13_combat_melee_special.md`, ESCAPE — `14_escape.md`, аптечка, предметы и `carefulGuard` подробно —
`15_items_heal_bot.md`, выбор режима — `03_modes.md`. Исполнение действия и прерывания — `30_execution.md`.

Сокращения: `BG` — `src/Battlescape/BattlescapeGame.cpp`, `AIM` — `src/Battlescape/AIModule.cpp`,
`SBG` — `src/Savegame/SavedBattleGame.cpp`, `BU` — `src/Savegame/BattleUnit.cpp`, `AP` — `src/Battlescape/AiProbe.cpp`.

## 0. Дорожная карта (дерево)

```
BattlescapeState::think (BattlescapeState.cpp:895 AiProbe::think — зонд, затем _battleGame->think)
└─ BattlescapeGame::think                                   BG:217
   ├─ _states не пуст → ничего (очередь состояний идёт через handleState BG:1287)
   ├─ getUnitsFalling → statePushFront(UnitFallBState), return BG:223
   ├─ side != PLAYER || AiProbe::botTurn(save)              BG:230   ← враг, нейтралы, бот
   │  ├─ resetUnitHitStates                                 BG:233  (SBG:3428)
   │  ├─ есть выбранный юнит
   │  │  ├─ handlePanickingUnit(sel) == true → паника      BG:238 → BG:1647 (30_execution §6)
   │  │  └─ иначе handleAI(sel)                            BG:240 → BG:371
   │  │     ├─ TU <= 5 → dontReselect                       BG:375
   │  │     ├─ лимит действий / dontReselect / очнулся → смена юнита  BG:379
   │  │     │  ├─ carefulGuard(unit) (бот)                  BG:381 → BG:307
   │  │     │  └─ selectNextPlayerUnit(true,_AISecondMove); 0 → statePushBack(0)  BG:385
   │  │     ├─ setVisible(false); calculateFOV(pos,1,false) BG:414–416
   │  │     ├─ (бот) ai->setTargetFaction(HOSTILE)          BG:425
   │  │     ├─ _AIActionCounter++                           BG:431
   │  │     ├─ unit->think(&action)                         BG:447 → BU:3388
   │  │     │  ├─ reloadAmmo
   │  │     │  ├─ раз за ход: medikit_think(HEAL)*, (STIMULANT)*  BU:3391–3402 → AIM:290 (карточка 15)
   │  │     │  └─ AIModule::think                           AIM:506 (§3 ниже)
   │  │     ├─ BA_RETHINK → unit->think ещё раз             BG:449
   │  │     ├─ _AIActionCounter = action.number             BG:455
   │  │     ├─ нет оружия/патронов → findItem / findBotWeapon → (подобрал) think ещё раз  BG:462–483
   │  │     ├─ звук агрессии (RNG)                          BG:485–491
   │  │     ├─ зонды и хуки V4                              BG:493–506
   │  │     ├─ BA_WALK → Pathfinding::calculate → UnitWalkBState         BG:507–552
   │  │     ├─ атака → PsiAttackBState | UnitTurnBState + MeleeAttackBState/ProjectileFlyBState  BG:554–577
   │  │     └─ BA_NONE → carefulGuard; counter=0; selectNext…; 0 → statePushBack(0)  BG:579–611
   │  └─ выбранного нет → selectNextPlayerUnit(true,_AISecondMove); 0 → _endTurnRequested, statePushBack(0)  BG:259
   └─ иначе (живой игрок): !_playerPanicHandled → handlePanickingPlayer   BG:278–281
```

После каждого состояния — `BattlescapeGame::popState` (BG:1368): разбор «юнит закончил действия», смена юнита
при гибели выбранного, `0` в голове очереди — `endTurn` (BG:647). Следующий тик с пустой очередью снова
приходит в `think` и в `handleAI` того же выбранного юнита — это и есть «повторный вход в think после действия».

## 1. Кто думает: развилка `think`

### BattlescapeGame::think : очередь пуста, сторона ИИ (BG:230)
УСЛОВИЕ:   `_states.empty() && !getUnitsFalling() && (_save->getSide() != FACTION_PLAYER || AiProbe::botTurn(_save))`
ДАННЫЕ:    `getSide()` — ИСТИНА (чей ход); `AiProbe::botTurn` = `bot() && side == FACTION_PLAYER` (AP:356), `bot()` =
           `OXCE_AI_PROBE && OXCE_AI_BOT` (AP:187); в релизной сборке заглушка `false` (AP:72–169, `#ifndef OXCE_AI_DEV`)
RNG:       нет (сам `resetUnitHitStates` без RNG)
РЕЗУЛЬТАТ: `resetUnitHitStates()` (SBG:3428), затем при `!_debugPlay` — паника или `handleAI` выбранного юнита,
           либо выбор следующего юнита
ПРЕРЫВАНИЕ: нет
ВОЗВРАТ:   в `BattlescapeState::think`; следующий тик — опять сюда, если очередь пуста
СТОРОНЫ:   враг и нейтралы всегда; бот — на ходу игрока при `OXCE_AI_BOT=1`

### BattlescapeGame::think : живой игрок (BG:274–283)
УСЛОВИЕ:   сторона PLAYER и не `botTurn`
РЕЗУЛЬТАТ: `if (!_playerPanicHandled) _playerPanicHandled = handlePanickingPlayer();` (BG:278–281)
СТОРОНЫ:   только живой игрок. **На ходу бота эта ветка не исполняется никогда.** `_playerPanicHandled` ставится в
           `false` в `init()` (BG:292–298) в начале каждого хода игрока с `turn > 1`, а в `true` — только здесь
           (BG:280) и в конструкторе (BG:182). Следствия для обеих сторон боя со стендом — `30_execution.md` §1.

Цепочка, доказывающая, что флаг ложен со 2-го хода до конца боя со стендом:
1. Конструктор: `_playerPanicHandled(true)` (BG:182).
2. `SavedBattleGame::endTurn` (SBG:1523–1528): NEUTRAL → PLAYER, `_turn++`.
3. `BattlescapeGame::endTurn` (BG:837–840): `side != FACTION_NEUTRAL && _endTurnRequested` →
   `pushState(new NextTurnState)`.
4. У стенда `NextTurnState` закрывается таймером (NextTurnState.cpp:312, `AiProbe::active()`), `close()` →
   `_game->popState()` (NextTurnState.cpp:528).
5. `Game.cpp:202` — новое верхнее состояние (`BattlescapeState`) получает `init()`; `BattlescapeState::init` →
   `_battleGame->init()` (BattlescapeState.cpp:816).
6. `BattlescapeGame::init` (BG:294–297): `side == PLAYER && turn > 1` → `_playerPanicHandled = false`.
7. Вернуть `true` может только BG:280, а её `botTurn` закрывает (BG:230). Других записей в поле нет
   (grep `_playerPanicHandled`: BG:182, 278, 280, 296, 1382).

Флаг не привязан к стороне: он ложен и на ходу врага, и на ходу нейтралов до конца боя. Бой, который стартует
с сейва, где `turn > 1`, получает `false` уже при первом `init`. R-120 (docs/rakes/aibench.md) называет только ход
бота; то, что флаг ложен и на ходу врага, в R-120 не записано.

## 2. Выбор юнита и число действий

### Порядок юнитов: `selectPlayerUnit` (SBG:935–990)
УСЛОВИЕ:   любой вызов `selectNextPlayerUnit(checkReselect, setReselect, checkInventory)` (SBG:922 → `selectPlayerUnit(+1, …)`)
ДАННЫЕ:    вектор `_units` (порядок сейва/генерации) — ИСТИНА; `isSelectable` (BU:5301) =
           `_faction == side && !isOut() && (!checkReselect || reselectAllowed())`
RNG:       нет
РЕЗУЛЬТАТ: `setReselect && _selectedUnit` → прежнему выбранному `dontReselect()` (SBG:937–940); обход вектора вперёд
           по кругу от текущего; первый подходящий — выбран. Вернулись к себе: при `checkReselect && !reselectAllowed()`
           выбранный обнуляется (SBG:977–981); `_selectedUnit == 0 && i == begin` → `0` (SBG:983–986)
ВОЗВРАТ:   выбранный юнит или 0 (0 = «в этом проходе больше некого»)
СТОРОНЫ:   оба; начало хода: враг и нейтралы — `selectNextPlayerUnit()` без проверок в конце `SavedBattleGame::endTurn`
           (SBG:1625–1626), выбранный перед этим обнулён (SBG:1500, 1506) → первый по вектору; ход игрока (бот) —
           `_lastSelectedUnit`, если он выбираем, иначе первый по вектору (SBG:1529–1534). `_lastSelectedUnit` — выбранный
           в момент конца хода игрока (SBG:1496–1499); у бота в конце хода выбранный обычно уже 0 (последний
           `selectNext` вернул 0), значит начало — снова с головы вектора

### Два прохода: `_AISecondMove`
- `_AISecondMove = false` в начале `BattlescapeGame::endTurn` (BG:657), то есть в начале хода каждой стороны.
- Первый проход: `selectNextPlayerUnit(true, false)` — покидаемый юнит **не** получает `dontReselect`, если сам его не
  получил (TU ≤ 5, `finalAction` после ходьбы врага, разворот «hiding»). Он снова выбираем.
- Переход через конец вектора: новый выбранный `getId() <= unit->getId()` → `_AISecondMove = true` (BG:402–405, 605–608).
  Признак — сравнение id, а не позиции в векторе; совпадает с порядком вектора, только если id растут вместе с ним
  (не прослежено, что это всегда так: превращённые и подкрепления добавляются в конец вектора с новыми id).
- Второй проход: `selectNextPlayerUnit(true, true)` — покидаемый юнит получает `dontReselect`, конец хода —
  когда выбирать некого.
- Итог: юнит может быть выбран дважды за ход и каждый раз сделать до `maxActions` засчитанных решений. Юнит,
  ответивший `BA_NONE` в первом проходе, в первом проходе `dontReselect` не получает (BG:588 передаёт
  `_AISecondMove == false`) и во втором проходе думает заново — с новыми бросками RNG.

### BattlescapeGame::handleAI : смена юнита (BG:379–410)
УСЛОВИЕ:   `_AIActionCounter >= AiProbe::maxActions(unit) || !unit->reselectAllowed() || unit->getTurnsSinceStunned() == 0`
ДАННЫЕ:    счётчик — ПАМЯТЬ (поле `BattlescapeGame`, общее на сторону); `maxActions` (AP:3826) =
           `n > 2 && careful(unit) ? n : 2`, `n` = `OXCE_AI_ACTIONS` (вне V4) → под V4 всегда 2; `getTurnsSinceStunned()` —
           ИСТИНА (0 = очнулся в этот ход, `incTurnsSinceStunned` в `prepareNewTurn`, BU:2874–2877)
RNG:       нет
РЕЗУЛЬТАТ: `carefulGuard(unit)` → `true` → return (юнит остаётся выбранным, после поворота снова сюда, guard уже
           израсходован); иначе `selectNextPlayerUnit(true, _AISecondMove)`; 0 → `_endTurnRequested = true;
           statePushBack(0)` (BG:385–390); `_AIActionCounter = 0` (BG:407)
ВОЗВРАТ:   return; следующий тик — `handleAI` нового выбранного
СТОРОНЫ:   оба; `carefulGuard` действует только у бота (`AiProbe::careful`)

### BattlescapeGame::handleAI : мало ОВ (BG:375–378)
УСЛОВИЕ:   `unit->getTimeUnits() <= 5`
ДАННЫЕ:    ОВ — ИСТИНА (собственные)
РЕЗУЛЬТАТ: `dontReselect()`; проверка BG:379 тут же даёт смену юнита
СТОРОНЫ:   оба

### Засчитанные и незасчитанные решения
| что | где | эффект на `_AIActionCounter` |
|---|---|---|
| каждый вход в `handleAI` до смены | BG:431 | `++` |
| `action.number` возвращается в счётчик | BG:455 | `= action.number` |
| пси-атака | AIM:667 | `number -= 1` — не засчитана |
| ходьба к точке огня при `_rifle && allowsMoving && SNAPSHOT haveTU` | AIM:804–809 | `number -= 1` — не засчитана |
| `BA_RETHINK` (второй `think`) | BG:449–453 | второй `think` не увеличивает счётчик |
| подбор оружия и третий `think` | BG:478–483 | не увеличивает |
| `BA_NONE` | BG:587 | `= 0` и смена юнита |
| ходьба без пути (`getStartDirection() == -1`) | BG:545–553 | состояние не создано; засчитано, юнит думает снова в следующем тике |
| `popState`, враг/нейтрал, `counter > 2` или выбранный выбыл | BG:1418–1420 | `= 0`; при `OXCE_AI_ACTIONS` вне V4 счётчик больше 2 не бывает, ветка живёт за счёт гибели |

Пример: под V4 враг с винтовкой может сделать «ходьба к точке огня (не засчитана) → выстрел (1) → ходьба (2)»,
затем смена юнита.

## 3. BattleUnit::think и AIModule::think сверху вниз

### BattleUnit::think (BU:3388–3405)
УСЛОВИЕ:   вызов из `handleAI` (BG:447, 452, 482)
ДАННЫЕ:    `_aiMedikitUsed` — ПАМЯТЬ на ход (сброс в `prepareNewTurn`, BU:2871)
RNG:       RNG HERE: внутри `medikit_think` AIM:370, 394, 404 — только при первом `think` юнита за ход и только если есть
           аптечка и условия (карточка 15)
РЕЗУЛЬТАТ: `reloadAmmo()`; раз за ход `while (medikit_think(BMT_HEAL))`, затем `while (medikit_think(BMT_STIMULANT))`
           (каждое успешное применение тратит ОВ, см. карточку 15); затем `_currentAIState->think(action)`
СТОРОНЫ:   оба (бот — тоже через `AIModule`); зонды `AiProbe::medikitBefore/After` только пишут

### AIModule::think (AIM:506–918) — порядок
| шаг | строки | что | RNG |
|---|---|---|---|
| 1 | 509–513 | `_walkAbortCounter > 200` → `clearTimeUnits()` (застрял в чужих юнитах) | нет |
| 2 | 514–530 | `action->type = BA_RETHINK`, `weapon = getMainHandWeapon(false)`, сброс флагов, `_attackAction.diff = getDifficultyCoefficient()` | нет |
| 3 | 532–535 | `_knownEnemies = countKnownTargets()`, `_visibleEnemies = selectNearestTarget()`, `_spottingEnemies = getSpottingUnits(pos)`, `_melee` | нет (карточка 02) |
| 4 | 540–549 | `AiProbe::knownOccupantPath()` (V1, вне V4) | нет |
| 5 | 550 | `_reachable = findReachable(unit, …)` | нет (31_pathfinding) |
| 6 | 551–559 | `AiProbe::revive / flee` (вне V4) → готовое действие, return | нет |
| 7 | 561–567 | `_wasHitBy.clear()`; `_foundBaseModuleToDestroy = false`; цель рывка выбыла → `setCharging(0)` | нет |
| 8 | 598–603 | `isLeeroyJenkins()` → `dont_think(action)`, return | внутри `setupPatrol` (карточка 10, 13) |
| 9 | 605–633 | оружие: `canUseWeapon(weapon, BA_NONE)` → FIREARM (`waypoints` → `_blaster`, иначе `_rifle`) или MELEE (`_melee = true`); иначе `weapon = 0` | нет |
| 10 | 635–636 | `_grenade = getGrenadeFromBelt() != 0` | нет |
| 11 | 639 | `tactical = AiProbe::tactics(unit) \|\| AiProbe::careful(unit)` — у врага ложь (TACTICS выключен), у бота истина | нет |
| 12 | 640–645 | `_spottingEnemies && (!_escapeTUs \|\| tactical)` → `setupEscape()` | AIM:1960, 1995–1996, 2016–2018 (карточка 14) |
| 13 | 647–652 | `_knownEnemies && !_melee && !_ambushTUs` → `setupAmbush()` | карточка 11 |
| 14 | 654 | `setupAttack()` — всегда | AIM:1839, 1904, 2548, 3017, 3884, 4081, 4092, 4168, 4338 (карточки 12, 13) |
| 15 | 655–658 | `setupPatrol()` — всегда | SBG:2305, 2325, 2328, 2378 через `getPatrolNode` (карточка 10) |
| 16 | 661–675 | пси: `_psiAction.type != BA_NONE && !_didPsi && turn >= getAIUseDelay` → действие пси, `number -= 1`, return; иначе `_didPsi = false` | нет |
| 17 | 677–693 | `evaluate` по текущему режиму (см. развилку ниже) | AIM:682 |
| 18 | 695–705 | `_weaponPickedUp` → evaluate; иначе `_spottingEnemies > 2 \|\| health < 2*hp/3` → evaluate | нет |
| 19 | 707–710 | `isCheating() && _AIMode != AI_COMBAT` → evaluate | нет |
| 20 | 712–736 | evaluate → `evaluateAIMode()` | AIM:2845, 2368 (карточка 03) |
| 21 | 738–741 | `_evalChosen` → `AI_COMBAT` (`OXCE_AI_EVAL`, вне V4) | нет |
| 22 | 743–746 | `tactical` → `tacticalMode()` (только бот) | нет |
| 23 | 748–750 | `_reserve = BA_NONE`; `kneelDefault = careful && type == "SOLDIER"` | нет |
| 24 | 752–835 | перенос действия режима в `action` (развилки ниже) | нет |
| 25 | 841–858 | `AiProbe::halfWalk` (вне V4) — укоротить ходьбу патруля | нет |
| 26 | 866–879 | `BA_WALK`: цель ≠ позиция → `_escapeTUs = _ambushTUs = 0`; цель = позиция → `BA_NONE` | нет |
| 27 | 881–917 | зонды `KNOWN_OCCUPANT_PATH_V2` / `FIREPOINT_BLOCKED`: запись полей `_ko2Walk*` (V4, используются в `handleAI` BG:513) и `tally` | нет |

Главное для RNG: шаги 12–15 вычисляют действия **всех** режимов до выбора режима (шаг 20). Броски
`setupEscape`, `setupAttack` и `setupPatrol` делаются при каждом `think`, каким бы ни вышел режим. Число бросков
одного `think` зависит от числа живых юнитов, узлов, клеток поиска и т. п., а не только от итогового решения.

### AIModule::think : evaluate в PATROL (AIM:681–683)
УСЛОВИЕ:   `_AIMode == AI_PATROL`
ДАННЫЕ:    `_spottingEnemies` — ЮНИТ/ИСТИНА (кто видит юнита; карточка 02), `_visibleEnemies` — ЮНИТ, `_knownEnemies` — СТОРОНА
RNG:       RNG HERE: `RNG::percent(10)` AIM:682 — **только если** все три счётчика равны 0 (короткое замыкание `||`)
РЕЗУЛЬТАТ: `evaluate`
ВОЗВРАТ:   шаг 18
СТОРОНЫ:   оба

### AIModule::think : evaluate в AMBUSH / COMBAT / ESCAPE (AIM:684–692)
УСЛОВИЕ:   AMBUSH: `!_rifle || !_ambushTUs || _visibleEnemies`; COMBAT: `_attackAction.type == BA_RETHINK`;
           ESCAPE: `!_spottingEnemies || !_knownEnemies`
ДАННЫЕ:    `_ambushTUs` — ПАМЯТЬ (с прошлых решений; сброс в `reset()` только в начале хода игрока, SBG:1564, и при ходьбе AIM:871–872; кроме того `setupAmbush` обнуляет `_ambushTUs` в начале, AIM:1634, а `setupEscape` — `_escapeTUs`, AIM:1939)
RNG:       нет
РЕЗУЛЬТАТ: `evaluate`
СТОРОНЫ:   оба

### AIModule::think : ESCAPE (AIM:754–766)
РЕЗУЛЬТАТ: `setCharging(0)`, тип и цель из `_escapeAction`, `finalAction = true`, `desperate = true`, `run`,
           `setHiding(true)` (разворот на 180° в конце пути)
ПРЕРЫВАНИЕ: `desperate` отключает остановку ходьбы по новому врагу (UnitWalkBState:235)
СТОРОНЫ:   оба; у бота `finalAction` и `hiding` не работают — `postPathProcedures` разбирает их только для
           `faction != FACTION_PLAYER` (UnitWalkBState:482–513, `30_execution.md` §2.6)

### AIModule::think : PATROL (AIM:767–789)
РЕЗУЛЬТАТ: `setCharging(0)`; при огнестрельном оружии `_reserve` по `getAggression()`: 0 → AIMED, 1 → AUTO,
           2 → SNAP (иначе BA_NONE); тип и цель из `_patrolAction`; `endPatrolIfSpent(action, true)` (AIM:1331)
ДАННЫЕ:    агрессия — РУЛСЕТ (юнит)
СТОРОНЫ:   оба; `_reserve` действует через `checkReservedTU` только на ходу HOSTILE (BG:1536–1552); бот использует резерв
           игрока (`_save->getTUReserved()`), `_reserve` ИИ бота не применяется нигде

### AIModule::endPatrolIfSpent (AIM:1331–1349)
УСЛОВИЕ:   `_patrolAction.type == BA_WALK && _patrolSpent == unitTurn() && pos == _patrolSpentAt && energy <= _patrolSpentEnergy`
ДАННЫЕ:    `_patrolSpent*` — ПАМЯТЬ (этот ход)
RNG:       нет
РЕЗУЛЬТАТ: `retry && _patrolRetry == 0` → `BA_RETHINK` (один раз), иначе `BA_NONE`
ВОЗВРАТ:   `BA_RETHINK` → второй `think` в BG:449; `BA_NONE` → конец решений юнита
СТОРОНЫ:   оба; из `dont_think` вызывается с `retry = false`

### AIModule::think : COMBAT (AIM:790–822)
РЕЗУЛЬТАТ: тип, цель и оружие из `_attackAction` (могло смениться на гранату); граната (`BA_THROW`,
           `isGrenadeOrProxy`) — сразу `spendCost(BA_PRIME)` и `spendTimeUnits(4)` (AIM:795–799, взвод до броска);
           `finalFacing`; `updateTU()`; ходьба к точке огня — `number -= 1`; `BA_LAUNCH` → `waypoints`;
           AIMED/AUTO → `kneel = allowsKneeling(kneelDefault)`; `_evalChosen` → `kneel = _evalKneel` (вне V4)
СТОРОНЫ:   оба; у врага `kneelDefault = false` → присед только если броня разрешает без признака «SOLDIER»
           (`Armor::allowsKneeling`, не прослежено в этой карточке — карточка 15)

### AIModule::think : AMBUSH (AIM:823–832)
РЕЗУЛЬТАТ: `setCharging(0)`, тип и цель из `_ambushAction`, `finalFacing`, `finalAction = true`, `kneel`
СТОРОНЫ:   оба; у бота `finalAction` и `finalFacing` после ходьбы не применяются (UnitWalkBState:482)

### AIModule::dont_think (Leeroy) (AIM:221–284)
УСЛОВИЕ:   `unit->isLeeroyJenkins()` (РУЛСЕТ: юнит)
РЕЗУЛЬТАТ: оружие ближнего боя; можно бить и бежать (`energy > stamina * 0.4`) → `selectNearestTargetLeeroy` →
           `meleeActionLeeroy`; иначе `setupPatrol` + `endPatrolIfSpent(action, false)` (AIM:270–283)
RNG:       только через `setupPatrol` → `getPatrolNode`
СТОРОНЫ:   оба; подробности — карточка 13

### Что пишется в BattleAction
| поле | кто пишет | кто читает |
|---|---|---|
| `type`, `target` | AIM:752–832 | `handleAI` BG:507, 554, 579 |
| `weapon` | AIM:516, 631, 668, 794 | `handleAI` (атака), `ProjectileFlyBState`, `MeleeAttackBState` |
| `number` | BG:443, AIM:530, 667, 808 | `handleAI` BG:455 |
| `finalAction` | ESCAPE, AMBUSH | `UnitWalkBState::postPathProcedures` (только не-игрок) |
| `finalFacing` | COMBAT, AMBUSH | `postPathProcedures` (только не-игрок) |
| `desperate` | ESCAPE | `UnitWalkBState` (нет остановки по новому врагу) |
| `run` | ESCAPE | `Pathfinding` / `getMoveType` |
| `kneel` | COMBAT (AIMED/AUTO), AMBUSH | `UnitTurnBState:122` (присед после поворота) |
| `waypoints` | COMBAT `BA_LAUNCH` | `ProjectileFlyBState` |
| `targeting` | ИИ не ставит (grep `targeting = true` в AIM — нет) | `UnitTurnBState:103` (проверка резерва идёт и для атак ИИ) |

`getReserveMode()` (AIM:4286) возвращает `_reserve`, его читает только `checkReservedTU` (BG:1538) на ходу HOSTILE.

## 4. Превращение действия в состояния (handleAI BG:458–611)

### handleAI : подбор оружия (BG:462–483)
УСЛОВИЕ:   `!weapon || !weapon->haveAnyAmmo()` (weapon = `getMainHandWeapon()`)
ДАННЫЕ:    `getVisibleUnits()` — ЮНИТ; `getPickUpWeaponsMoreActively()` — РУЛСЕТ; `botArms = AiProbe::pickUp(unit)` (`OXCE_AI_ARMS`, вне V4)
RNG:       внутри `findItem` — не прослежено (карточка 15)
РЕЗУЛЬТАТ: не игрок: `(HOSTILE && никого не видит) || pickUpMoreActively` → `findItem(&action, …)`; игрок: `botArms &&
           никого не видит` → `findBotWeapon`. Подобрал при `pickUpMoreActively` → `setWeaponPickedUp()` и `think` ещё раз
СТОРОНЫ:   враг и нейтралы; бот — только вне V4

### handleAI : звук агрессии (BG:485–491)
УСЛОВИЕ:   `unit->getCharging() != 0 && unit->hasAggroSound() && !_playedAggroSound`
ДАННЫЕ:    `getCharging()` — решение ИИ; `hasAggroSound` — РУЛСЕТ
RNG:       RNG HERE: `getRandomAggroSound()` → `RNG::generate(0, size-1)` BU:4858 — **сеяный** RNG ради звука; вызывается
           и при немом звуке (SDL dummy), раз на юнит за выбор (`_playedAggroSound` сбрасывается при `counter == 1`, BG:438)
РЕЗУЛЬТАТ: звук; `_playedAggroSound = true`
СТОРОНЫ:   у кого в рулсете есть `aggroSound` (обычно враги); решение «рывок» (`setCharging`) сразу двигает
           последовательность

### handleAI : BA_WALK (BG:507–552)
УСЛОВИЕ:   `action.type == BA_WALK`
ДАННЫЕ:    `ko2 = knownOccupantV2Walk(action)` — ПАМЯТЬ (V4 `KNOWN_OCCUPANT_PATH_V2`)
RNG:       нет (Pathfinding без RNG — карточка 31)
РЕЗУЛЬТАТ: `setKnownOccupant(actor, ko2)` (V4) → `Pathfinding::calculate(actor, target, BAM_NORMAL)` (BG:521) →
           `blockedStepPlan` (V4 `BLOCKED_STEP`) → снять `knownOccupant`; `patrolStunReserve` (V4 `PATROL_STUN_PREFIX`) →
           `abortPath()`; `patrolOutOfEnergy` (вне V4) → `spendPatrol()`; путь есть → `statePushBack(new UnitWalkBState)`;
           пути нет и шли к предмету → `targetTile->setDangerous(true)`
ПРЕРЫВАНИЕ: см. `30_execution.md` §2
ВОЗВРАТ:   пути нет — состояния нет, следующий тик снова `handleAI` того же юнита (счётчик уже увеличен)
СТОРОНЫ:   оба; ходьба идёт `BAM_NORMAL` и `run` из действия (ESCAPE) — `getMoveType` не прослежен здесь

### handleAI : атака (BG:554–577)
УСЛОВИЕ:   тип ∈ {SNAPSHOT, AUTOSHOT, AIMEDSHOT, THROW, HIT, MINDCONTROL, USE, PANIC, LAUNCH}
RNG:       нет здесь
РЕЗУЛЬТАТ: `updateTU()`; MINDCONTROL/PANIC/USE → `PsiAttackBState`; иначе `UnitTurnBState` и следом `MeleeAttackBState`
           (HIT) или `ProjectileFlyBState`
ВОЗВРАТ:   после атаки — `popState` → следующий тик `handleAI` того же юнита
СТОРОНЫ:   оба

### handleAI : BA_NONE (BG:579–611)
УСЛОВИЕ:   `action.type == BA_NONE`
РЕЗУЛЬТАТ: `carefulGuard` (бот) → return; иначе `_AIActionCounter = 0`, `selectNextPlayerUnit(true, _AISecondMove)`,
           0 → `statePushBack(0)`; при новом выбранном с id ≤ текущего — `_AISecondMove = true`
СТОРОНЫ:   оба

### Остальные типы
`BA_RETHINK` после второго `think` и `BA_TURN` из `think` в `handleAI` не обрабатываются: состояние не создаётся, счётчик
уже увеличен, следующий тик — снова `handleAI` того же юнита. `BA_TURN` создаёт только `carefulGuard` (BG:357–363).

## 5. carefulGuard (BG:307–365), бот

### carefulGuard
УСЛОВИЕ:   `AiProbe::careful(unit) && !unit->isOut()`; раз на юнит за ход (`_guardedTurn`, `_guardedUnits`)
ДАННЫЕ:    враги `faction == HOSTILE && !isOut && getVisible()` — СТОРОНА (`_visible` — видимость игроку);
           ближайший по `distanceSq` — ИСТИНА (позиция видимого врага); если нет — `AiProbe::watchPoint` (`OXCE_AI_WATCH`, вне V4; при выключенном флаге `false` → return false)
RNG:       нет
РЕЗУЛЬТАТ: шагов поворота `min(diff, 8-diff)`; `steps == 0 || TU < steps * getTurnCost()` → false; иначе `BA_TURN`,
           `statePushBack(new UnitTurnBState)`, return true
ВОЗВРАТ:   true — `handleAI` выходит, юнит остаётся выбранным; после поворота `handleAI` снова, guard уже потрачен
СТОРОНЫ:   только бот (`careful` = `bot && OXCE_AI_CAREFUL && faction == PLAYER`, AP:367); подробности — карточка 15

## 6. Конец хода стороны (BG:647–843, часть ИИ)

- Сигнал конца — `statePushBack(0)` (BG:259, 389, 590) при `selectNext… == 0`; `statePushBack(0)` на пустую очередь сразу
  зовёт `endTurn` (BG:1338); иначе `0` доходит до головы очереди и `popState`/`handleState` зовут `endTurn` (BG:1449–1462, 1287).
- `AiProbe::sideEnds` — зонд (BG:649); `_AISecondMove = false` (BG:657).
- Гранаты с таймером и взрывы терраина → `ExplosionBState` и return (BG:667–741, 759–766); `endTurn` вызывается снова,
  когда они отработают.
- `_save->endTurn()` (BG:759) → смена стороны, `prepareNewTurn` юнитов новой стороны (`_dontReselect = false`,
  `_aiMedikitUsed = false`, `_unitsSpottedThisTurn.clear()`, мораль и паника — `30_execution.md` §6); только при новой
  стороне PLAYER — `updateTurnsSince` и `getAIModule()->reset()` у всех (SBG:1547–1567: `_escapeTUs`, `_ambushTUs`,
  `_walkAbortCounter`, AIM:162).
- `checkForCasualties` (BG:782), `calculateLighting`, `recalculateFOV` (BG:785–786).
- Предел ходов, конец боя; `_endTurnRequested && side != NEUTRAL` → `NextTurnState` (BG:837–840).

## Числа

| что | значение | файл:строка | на что влияет |
|---|---|---|---|
| мало ОВ | `TU <= 5` → `dontReselect` | BG:375 | конец решений юнита |
| лимит решений | `maxActions` = 2 (V4); `OXCE_AI_ACTIONS > 2` только у бота, вне V4 | AP:3826 | смена юнита |
| застревание | `_walkAbortCounter > 200` → `clearTimeUnits` | AIM:509 | юнит теряет ход |
| пси-задержка | `turn >= getAIUseDelay` | AIM:661 | разрешение пси |
| patrol re-evaluate | 10 % | AIM:682 | вход в `evaluateAIMode` |
| переоценка по ранениям | `spotting > 2 \|\| health < 2*hp/3` | AIM:700–701 | вход в `evaluateAIMode` |
| резерв патруля | агрессия 0/1/2 → AIMED/AUTO/SNAP | AIM:771–782 | `checkReservedTU` на ходу HOSTILE |
| резерв HOSTILE | SNAP +tu/3, AUTO +2·tu/5, AIMED +tu/2 (база) | BG:1546–1551 | ходьба, поворот |
| граната | `BA_PRIME` + 4 ОВ до броска | AIM:795–799 | ОВ |
| guard | шагов `min(d, 8-d)` × `getTurnCost()` | BG:343–355 | разворот бота |

## RNG (в порядке исполнения одного решения)

| # | вызов | файл:строка | условие вызова |
|---|---|---|---|
| 1 | `medikit_think` | AIM:370, 394, 404 | первый `think` юнита за ход; есть аптечка; условия карточки 15 |
| 2 | `setupEscape` | AIM:1960, 1995–1996, 2016–2018 | `_spottingEnemies && (!_escapeTUs \|\| tactical)` |
| 3 | `setupAmbush` | карточка 11 | `_knownEnemies && !_melee && !_ambushTUs` |
| 4 | `setupAttack`: пси, снайпер, выбор цели снайпером, ближний/дальний, `findFirePoint`, режим огня | AIM:4081, 4092, 4168, 1839, 2548, 4338, 1904, 3017, 3884 | у каждого своё условие (карточки 12, 13) |
| 5 | `setupPatrol` → `getPatrolNode` | SBG:2305, 2325, 2328, 2378 | нет `_toNode` или узел достигнут и т. п. (карточка 10) |
| 6 | `percent(10)` | AIM:682 | режим PATROL и все три счётчика врагов равны 0 |
| 7 | `evaluateAIMode` | AIM:2845, 2368 | `evaluate` |
| 8 | повтор шагов 2–7 | — | `BA_RETHINK` или подбор оружия: полный второй/третий `think` |
| 9 | звук агрессии | BU:4858 | рывок и `aggroSound` в рулсете |
| 10 | исполнение | `30_execution.md` | реакция, полёт, взрыв, паника |

Зонды (`AiProbe::beforeThink` AP:1527–1539, `logDecision`, `tally`, `note`, `walkPlanned`) читают `RNG::getSeed()` и не
бросают.

## Знание

| данные | метка | где |
|---|---|---|
| чей ход, порядок `_units`, id | ИСТИНА | BG:230, SBG:935 |
| ОВ, здоровье, `getTurnsSinceStunned` | ИСТИНА (собственные) | BG:375, 379; AIM:701 |
| `_knownEnemies` | СТОРОНА | AIM:532 (карточка 02) |
| `_visibleEnemies` | ЮНИТ | AIM:533 |
| `_spottingEnemies` | ЮНИТ/ИСТИНА — кто видит юнита (карточка 02) | AIM:534 |
| `_escapeTUs`, `_ambushTUs`, `_AIMode`, `_patrolSpent*`, `_didPsi`, `_wasHitBy` | ПАМЯТЬ | AIM:161–166, 561, 664 |
| агрессия, Leeroy, пси-задержка, `aggroSound`, `pickUpWeaponsMoreActively` | РУЛСЕТ | AIM:598, 661, 771; BG:465, 487 |
| враг для guard | СТОРОНА (`getVisible`) + ИСТИНА позиции | BG:329–340 |

## Слепые пятна (доказаны кодом)

1. `_AIActionCounter` — одно поле на сторону. При гибели выбранного от чужого действия (реакция бота, взрыв)
   `popState` выбирает следующий юнит `selectNextPlayerUnit(true, true)` (BG:1483), но счётчик не сбрасывает:
   сброс BG:1418–1420 идёт, только когда закончил действия юнит **не-игрока** (`actor` не FACTION_PLAYER), а
   выстрел реакции принадлежит юниту бота. Следующий враг начинает с чужим счётчиком 1 или 2: при 2 его сразу
   покидают (BG:379), при 1 он делает одно решение вместо двух. В первом проходе `dontReselect` он не получает, так
   что ход он получит во втором проходе. Прослежено чтением, боем не проверено.
2. Решения ИИ бота, рассчитанные на конец ходьбы (`finalAction`, `finalFacing`, `hiding`), для FACTION_PLAYER не
   применяются (UnitWalkBState:482); ESCAPE и AMBUSH у бота не завершают решения юнита сами по себе.
3. `_reserve` бота не используется: на ходу игрока `checkReservedTU` берёт `_save->getTUReserved()` (BG:1528).
4. Ветка `popState` «AI does three things» (BG:1415) закрыта условием `side != FACTION_PLAYER`; на ходу бота сброс
   счётчика при гибели выбранного не идёт — лишь `setSelectedUnit(0)` (BG:1481).
5. `_escapeTUs` и `_ambushTUs` сбрасываются в начале хода игрока (SBG:1564), при любой ходьбе (AIM:871–872) и в начале
   собственных `setupAmbush`/`setupEscape` (AIM:1634, 1939), которые вызываются только при условиях шагов 12–13. У
   врага значение, посчитанное в его ход, живёт через ход игрока до следующего хода игрока — а там сбрасывается
   до того, как враг снова ходит. У бота: посчитано в ход бота → сброс в начале следующего хода бота.
6. Решения `setupEscape/Attack/Patrol` считаются до выбора режима и тратят RNG при каждом `think`, даже если режим
   их не возьмёт.

## Не прослежено

- Совпадает ли порядок id с порядком `_units` у подкреплений и превращённых юнитов (влияет на `_AISecondMove`).
- `findItem` / `findBotWeapon` изнутри (RNG, знание) — карточка 15.
- `getMoveType()` для `run` у ESCAPE и что меняет `BAM_NORMAL` в BG:520 — карточка 31.
- `Armor::allowsKneeling(kneelDefault)` для врага.
- Ход нейтралов: тот же конвейер, цель — бегство; отдельно не разбирался.
