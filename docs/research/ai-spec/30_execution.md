# 30. Исполнение действия и прерывания

Код: коммит `7cd80e284`. Номера строк проверены чтением. Конвейер решений, превращение `BattleAction` в состояния
и выбор юнита — `01_pipeline.md`. Путь и цены шагов — `31_pathfinding.md`. Сводка RNG — `21_rng.md`.

Сокращения: `BG` — `src/Battlescape/BattlescapeGame.cpp`, `UW` — `src/Battlescape/UnitWalkBState.cpp`,
`UT` — `src/Battlescape/UnitTurnBState.cpp`, `PF` — `src/Battlescape/ProjectileFlyBState.cpp`,
`PR` — `src/Battlescape/Projectile.cpp`, `MA` — `src/Battlescape/MeleeAttackBState.cpp`,
`TE` — `src/Battlescape/TileEngine.cpp`, `UP` — `src/Battlescape/UnitPanicBState.cpp`,
`BU` — `src/Savegame/BattleUnit.cpp`, `AIM` — `src/Battlescape/AIModule.cpp`, `AP` — `src/Battlescape/AiProbe.cpp`.

## 0. Как идёт исполнение

`handleAI` кладёт в очередь `_states` одно или два состояния (`UnitWalkBState`; `UnitTurnBState` +
`ProjectileFlyBState`/`MeleeAttackBState`; `PsiAttackBState`). Каждый тик `handleState` (BG:1287) вызывает `think()`
головы очереди. Состояние снимает себя через `popState()` (BG:1368). В `popState`:
- `deinit`, разбор «юнит закончил действия» (BG:1392–1443, ветка ИИ — только на ходу не-игрока, BG:1415);
- `0` в голове — конец хода (BG:1449–1466);
- `init()` следующего состояния (BG:1471);
- выбранный юнит выбыл → `cancelCurrentAction`; на ходу игрока `setSelectedUnit(0)`, иначе
  `selectNextPlayerUnit(true, true)` (BG:1474–1484).

Когда очередь пуста, `BattlescapeGame::think` снова зовёт `handleAI` выбранного юнита. Так ИИ «возвращается» после
любого действия и любого прерывания: отдельного обработчика прерываний нет, юнит просто думает заново
(`01_pipeline.md` §2, счётчик решений).

Состояния, которые вставляет чужое действие: реакция — `statePushBack` (TE:2896–2903), в хвост очереди; падение —
`statePushFront(UnitFallBState)` (UW:185, BG:225); взрыв ближнего боя — `statePushFront(ExplosionBState)` (MA:239);
гибель — `statePushNext(UnitDieBState)` (BG:1052–1113), сразу за головой.

## 1. Главная находка: `getPanicHandled()` ложен со 2-го хода в боях со стендом

Почему флаг ложен на ходу бота, врага и нейтралов начиная со 2-го хода — `01_pipeline.md` §1 (цепочка BG:182 → BG:296,
BattlescapeState.cpp:816, NextTurnState.cpp:312/528, Game.cpp:202; вернуть `true` может только BG:280, а её закрывает
`botTurn`). В живой игре флаг ложен лишь пока `handlePanickingPlayer` (BG:1629) разбирает панику своих в начале хода
игрока — у движка он значит «идёт берсерк/паника игрока». У стенда он ложен постоянно, и все места, где движок
отличает «паника» от «обычный ход», работают в режиме паники.

| место | при `true` (живая игра) | при `false` (стенд со 2-го хода) | на кого действует |
|---|---|---|---|
| PF:493–498 `accuracyDivider` | 100 | **200 — точность всех выстрелов и бросков вдвое ниже**, включая реакцию | все стороны |
| PF:292 цель выстрела | `canTargetUnit`, точка на юните | центр клетки (`voxelTileCenter`), без поиска видимой точки | все стороны |
| PF:671 реакция после выстрела | `checkReactionFire(стрелок)` | **нет реакции на выстрел** | все стороны |
| PF:562, 605 | текст «нет траектории/линии» | нет текста | только интерфейс |
| PR:136 «попадём не в ту клетку» | проверка и отказ от выстрела | нет проверки | юниты FACTION_PLAYER (бот) |
| UW:235, UW:442 остановка по новому врагу | шаг или поворот, открывший нового врага, останавливает ходьбу | **не останавливает** (`spotted`, `turnspot`) | все стороны |
| UW:338 резерв ОВ при ходьбе | `checkReservedTU` (у врага — `_reserve` патруля) | **резерв не проверяется** | все стороны |
| UW:524 конец ходьбы юнита игрока | — | **`clearTimeUnits()`: юнит бота теряет все ОВ после законченной ходьбы** | FACTION_PLAYER |
| UT:103 резерв перед поворотом | проверка резерва (ИИ не ставит `targeting`) | нет проверки | своя сторона |
| UT:115 поворот открыл врага при `BA_NONE` | стоп | нет | своя сторона |
| UT:140 не хватило ОВ на шаг поворота | снять состояние | **состояние висит вечно** (R-120) | любая сторона |
| UW:111, 320, 330; BG:1382 | тексты, предупреждения | нет | интерфейс |

Что осталось без флага: реакция на каждый шаг ходьбы (UW:248–256), реакция после приседа (BG:633, UT:136), реакция на
удар (MA:168–175) — эти проверки идут всегда.

Следствия, которые важны для обучения ИИ:
- Числа стрельбы со 2-го хода в боях стенда не совпадают с живой игрой ни у врага, ни у бота: попаданий меньше,
  реакции на выстрел нет вовсе, реакция на ходьбу есть.
- Враг со 2-го хода не останавливает ходьбу при виде нового бойца и не держит резерв патруля.
- «77 % ходов без ОВ» у бота в патруле (комментарий `OXCE_AI_HALF`, AIM:841–842) объясняется UW:524: любая ходьба бота,
  дошедшая до конца пути, обнуляет ОВ. Прерванная ходьба (`cancelCurentMove`) `postPathProcedures` не зовёт и ОВ не
  обнуляет.
- Поворот ИИ перед выстрелом при нехватке ОВ на шаг поворота висит (UT:140). ИИ не ставит `targeting`
  (grep по AIM), а проверка ОВ атаки в ИИ (`haveTU` выстрела) поворот не учитывает — у врага это возможно так же,
  как у бота в R-120. Боем не проверено.
- На 1-м ходу всё как в живой игре; бой с сейва, где `turn > 1`, получает `false` сразу.

## 2. UnitWalkBState

### 2.1 Инициализация (UW:63–79)
`_numUnitsSpotted = getUnitsSpottedThisTurn().size()` — база для «нового врага»; `_beforeFirstStep`, если нужен поворот
до первого шага; `addMovingUnit`. `_unitsSpottedThisTurn` очищается в `prepareNewTurn` своей стороны (BU:2866).

### 2.2 Остановки и их следствия

### UnitWalkBState::think : броня не ходит (UW:93–98)
УСЛОВИЕ:   `!getArmor()->allowsMoving()`
РЕЗУЛЬТАТ: `abortPath`, `popState`
ВОЗВРАТ:   `handleAI` того же юнита в следующем тике
СТОРОНЫ:   оба

### UnitWalkBState::think : надо встать из приседа (UW:103–120)
УСЛОВИЕ:   `isKneeled()`
ДАННЫЕ:    ОВ — ИСТИНА
RNG:       RNG HERE (косвенно): `BattlescapeGame::kneel` → `checkReactionFire` (BG:633) — броски реакции
РЕЗУЛЬТАТ: встал → `return` (ходьба продолжится следующим тиком); не встал → `abortPath`, `popState`
СТОРОНЫ:   оба; `kneel()` проверяет `checkReservedTU` (BG:621)

### UnitWalkBState::think : юнит выбыл (UW:122–127)
РЕЗУЛЬТАТ: `abortPath`, `popState`; выбор нового юнита — в `popState` (BG:1474–1484)

### UnitWalkBState::think : следующая клетка занята во время шага (UW:144–159)
УСЛОВИЕ:   в клетке назначения чужой юнит (ИСТИНА), не падаем
РЕЗУЛЬТАТ: `lookAt(destination)` (поворот к невидимому юниту), `abortPath()`; шаг доходит до конца и ниже по коду
           ходьба кончается (`getStartDirection() == -1` → `postPathProcedures`)
СТОРОНЫ:   оба

### UnitWalkBState::think : падение (UW:164–190)
УСЛОВИЕ:   нет пола, не летает, `walkingPhase == 0`; под клеткой стоит юнит
РЕЗУЛЬТАТ: `dequeuePath`, `addFallingUnit`, `statePushFront(UnitFallBState)`, return (ходьба остаётся в очереди)
СТОРОНЫ:   оба; без юнита внизу — `_falling`, путь `DIR_DOWN` (UW:295)

### UnitWalkBState::think : шаг закончен (UW:202–257)
УСЛОВИЕ:   `getStatus() == STATUS_STANDING` после шага
ДАННЫЕ:    `getUnitsSpottedThisTurn()` — ЮНИТ; `getPanicHandled()` — см. §1
RNG:       RNG HERE: `checkForProximityGrenades` (UW:226) — взрыв мины (не прослежено, есть ли бросок); RNG HERE:
           `checkReactionFire` (UW:250) — бросок на каждого пригодного реактора (§3); BURNFLOOR → `hit` (урон — RNG)
РЕЗУЛЬТАТ: по порядку:
           1. `updateSoldierInfo(walkFovKeep)` (V4 `WALKFOV_SKIP` — пропуск FOV интерфейса для бота, FOV шага ниже остаётся);
           2. BURNFLOOR: поджечь, `hit`; провалился → `abortPath`, return;
           3. не игрок → `setVisible(false)`;
           4. `change = checkForProximityGrenades`; свет (`AiProbe::lightSkip`, V4 `LIGHTSKIP`); `calculateFOV(pos, 2, false)`;
           5. `unitSpotted = !ignoreSpottedEnemies && !_falling && !desperate && getPanicHandled() && _numUnitsSpotted != spotted.size()` (UW:235);
           6. `change > 1` → `popState`, return;
           7. `unitSpotted` → `walkStop("spotted")`, `cancelCurentMove`;
           8. не падаем → `checkReactionFire(_unit, _action)` → `true` → `walkStop("reaction")`, `cancelCurentMove`
ПРЕРЫВАНИЕ: шаги 6–8
ВОЗВРАТ:   прерывание → `popState`; `handleAI` того же юнита в следующем тике (если жив)
СТОРОНЫ:   оба; ESCAPE (`desperate`) не останавливается по новому врагу; со 2-го хода у стенда шаг 7 не бывает (§1)

`cancelCurentMove` (UW:128–139): если юнит должен упасть — `_falling = true` (идёт вниз), иначе `abortPath` и `popState`.
`postPathProcedures` **не** вызывается: `finalAction`, `finalFacing`, `hiding`, рывок в ближний бой не применяются.

### UnitWalkBState::think : стоим, следующий шаг (UW:274–420)
| # | условие | строка | результат | след (`AiProbe::walkStop`) |
|---|---|---|---|---|
| 1 | `unitSpotted && !desperate && charging == 0 && !_falling` | UW:276 | `setHiding(false)`, `postPathProcedures` | — (ветка мёртвая: `unitSpotted` ставится только в UW:235 и UW:442, и обе сразу выходят) |
| 2 | цена шага `INVALID_MOVE_COST` | UW:312 | `cancelCurentMove` | `invalid` |
| 3 | `tu > TU` | UW:318 | `cancelCurentMove` | `tu` |
| 4 | `energy > Energy` | UW:328 | `cancelCurentMove` | `energy` |
| 5 | `getPanicHandled() && !_falling && !checkReservedTU(tu, energy)` | UW:338 | `cancelCurentMove` | `reserve` |
| 6 | смотрит не туда, не боком | UW:346 | `lookAt(dir)`, return — поворот бесплатный, кроме первого шага | — |
| 7 | дверь: `unitOpensDoor` 3 (ждать) / 1 (дверь НЛО, ждать) / 0 (звук) | UW:355–369 | return до открытия | — |
| 8 | в клетке юнит (`getOverlappingUnit TUO_IGNORE_SMALL`) | UW:370–386 | `clearTU`, `increaseAIWalkAbortCounter`, `firepointBlocked`, `blockedStepStop` (V4 `BLOCKED_STEP`), `cancelCurentMove` | `unit` |
| 9 | иначе | UW:388–399 | `dequeuePath`, `spendTimeUnits(tu)`, `spendEnergy(energy)`, `startWalking` | — |
| 10 | пути больше нет (`dir == -1`) | UW:414–418 | `postPathProcedures` | — |

`_walkAbortCounter` (шаг 8) копится и в `AIModule::think` при `> 200` обнуляет ОВ (AIM:509–513); сбрасывается в `reset()`
только в начале хода игрока (AIM:169).

### UnitWalkBState::think : поворот во время ходьбы (UW:422–457)
УСЛОВИЕ:   `STATUS_TURNING`
РЕЗУЛЬТАТ: до первого шага поворот стоит ОВ (`getTurnBeforeFirstStep` — сразу, иначе копится `_preMovementCost`);
           `turn()`, `calculateFOV(unit)`; новый враг (с `getPanicHandled()`, UW:442) → списать накопленные ОВ поворота,
           `setHiding(false)`, `abortTurn`, `walkStop("turnspot")`, `cancelCurentMove`
СТОРОНЫ:   оба; со 2-го хода у стенда не срабатывает (§1)

### 2.3 Конец пути: postPathProcedures (UW:479–536)
УСЛОВИЕ:   путь кончился (`dir == -1`) или ветка 1 таблицы (мёртвая)
ДАННЫЕ:    `_action.finalAction`, `finalFacing` — решение ИИ; `getCharging()` — ПАМЯТЬ ИИ; `isHiding()` — решение ESCAPE
RNG:       нет (сам `MeleeAttackBState` — §5)
РЕЗУЛЬТАТ: `clearTU`. Для `faction != FACTION_PLAYER`:
           `finalAction` → `dontReselect()` (юнит закончил ход); рывок и цель в радиусе удара → `statePushBack(MeleeAttackBState)`
           с `BA_HIT` (`setCharging(0)`); иначе `isHiding` → разворот на `dir + 4`, `setHiding(false)`, `dontReselect()`;
           поворот к `dir` с `calculateFOV` на каждом шаге (бесплатно).
           Для FACTION_PLAYER: только `else if (!getPanicHandled()) clearTimeUnits()` (UW:524).
           Затем свет (`lightSkip`), `calculateFOV`, `popState`
ВОЗВРАТ:   `handleAI`: у врага после `dontReselect` — смена юнита; иначе следующее решение
СТОРОНЫ:   враг и нейтралы — полная ветка; бот — только UW:524 (ход 1 — ничего, со 2-го — ОВ = 0)

### 2.4 Что ИИ делает после прерывания ходьбы
- Режим (`_AIMode`), цель рывка (`getCharging`), узел патруля (`_toNode`), `_escapeTUs`/`_ambushTUs` не сбрасываются.
  `_escapeTUs`/`_ambushTUs` обнуляются уже при выборе ходьбы (AIM:871–872), значит после прерывания `setupEscape`
  и `setupAmbush` считаются заново при первом же `think`, если выполнены их условия (`01_pipeline.md` §3, шаги 12–13).
- Юнит не получает `dontReselect` (его ставит только `postPathProcedures`), поэтому ESCAPE/AMBUSH, прерванные
  реакцией или препятствием, не заканчивают ход: юнит думает снова, если остались решения (`_AIActionCounter`) и ОВ > 5.
- Прерывание стоит одного решения из двух: счётчик уже увеличен при выборе ходьбы.
- `_wasHitBy` очищается в начале каждого `think` (AIM:561). Список «кто в меня попал» нужен не самому юниту, а
  реакциям других — `getSpottingUnits` спрашивает его у реактора (TE:2611, §3).

## 3. Огонь на реакцию

### TileEngine::checkReactionFire (TE:2509–2558)
УСЛОВИЕ:   `!isPreview()`; `unit->getFaction() == getSide()` (реакция только на юнит ходящей стороны); юнит на клетке
ДАННЫЕ:    `getSpottingUnits(unit)` — см. ниже
RNG:       RNG HERE: `tryReaction` → `RNG::percent(chance)` TE:2892, по броску на каждого реактора, дошедшего до броска
РЕЗУЛЬТАТ: если юнит не под контролем врага (`faction == originalFaction || faction != HOSTILE`): цикл
           `reactor = getReactor(...)`; `count > 10 || !tryReaction` → убрать из списка; иначе `result = true`,
           `reactionScore -= reactionReduction`, `count++` — **тот же реактор может стрелять снова**, пока его счёт
           выше счёта цели и `count ≤ 10`
ПРЕРЫВАНИЕ: каждый успешный `tryReaction` кладёт `ProjectileFlyBState`/`MeleeAttackBState` в хвост очереди
ВОЗВРАТ:   `true` → ходьба останавливается (UW:250); выстрелы реакции идут после `popState` ходьбы
СТОРОНЫ:   оба; кто вызывает: каждый шаг ходьбы (UW:250), присед (BG:633, UT:136), конец выстрела (PF:671, только при
           `getPanicHandled()`), удар (MA:171, всегда). Юнит, взятый под контроль врагом (HOSTILE, исходно не HOSTILE),
           реакцию не вызывает

### TileEngine::getSpottingUnits (TE:2565–2672)
УСЛОВИЕ:   `side != FACTION_NEUTRAL` (на ходу нейтралов реакции нет)
ДАННЫЕ:    для каждого `bu`: `!isOut && !isOutThresholdExceed`, `bu->getReactionScore() >= unit->getReactionScore()` — ИСТИНА
           (свои ОВ и реакция чужого); `faction != side`; нейтрал — только по HOSTILE, не игнорируемому ИИ;
           `distance2dSq ≤ maxViewDistanceSq` — ИСТИНА; `gotHit` = `ai->getWasHitBy(unit)` у реактора с ИИ — ПАМЯТЬ, без
           ИИ — `getHitState()`; при `EXTENDED_MELEE_REACTIONS == 2` ещё `wasMeleeAttackedBy` — ПАМЯТЬ;
           `(checkViewSector || gotHit) && canTargetUnit && visible(bu, tile)` — ЮНИТ (реактора)
RNG:       нет
РЕЗУЛЬТАТ: **побочные эффекты**: реактор-игрок делает цель видимой (`unit->setVisible(true)`), любой реактор
           добавляет её в свои видимые (`addToVisibleUnits`) — знание стороны и юнита меняется проверкой реакции, даже если
           выстрела не будет. Тип реакции `determineReactionType` (TE:2711): у игрока — оружие для реакций, затем
           оружие ближнего боя, затем основное; HIT, если в радиусе удара, есть заряд и ОВ; иначе SNAPSHOT огнестрелом;
           `reactionReduction = cost.Time * reactions / tu`. Фильтр `getReactionFireThreshold(faction) > 0` — точность с
           поправкой на дальность ≥ порога и не вне дальности
СТОРОНЫ:   оба; у бота ИИ есть, значит у бойцов бота `gotHit` берётся из `_wasHitBy`, как у врага

### TileEngine::getReactor (TE:2681–2702)
ДАННЫЕ:    наибольший `reactionScore` среди живых без `getRespawn` — ИСТИНА
РЕЗУЛЬТАТ: подходит, если `unit->getReactionScore() <= best->reactionScore`; реактору-игроку `addReactionExp()`
           **при каждом выборе** (даже если `tryReaction` не выстрелит) — статистика, не RNG
СТОРОНЫ:   оба

### TileEngine::tryReaction (TE:2831–2909)
УСЛОВИЕ:   `canUseWeapon(weapon, actor, false, type)`; `ammo && haveTU`
ДАННЫЕ:    у HOSTILE: при взрывчатке (`radius > 0`, не HIT) `explosiveEfficacy(target, unit, radius, -1) == 0` → не стрелять
           (оценка ИИ, без RNG, AIM:3173)
RNG:       RNG HERE: `RNG::percent(arg.getFirst())` TE:2892 — только если дошли до `targeting`; шанс 100, у реакции на
           удар (`originalAction.type == BA_HIT`) 100 при `EXTENDED_MELEE_REACTIONS > 0`, иначе 0 — бросок делается и
           при 0; скрипты `ReactionWeaponAction`, `ReactionUnitAction`, `ReactionUnitReaction` меняют шанс (X-Piratez — `40_ruleset.md`)
РЕЗУЛЬТАТ: успех → `statePushBack(MeleeAttackBState | ProjectileFlyBState)`, `true`
СТОРОНЫ:   оба

## 4. Выстрел: ProjectileFlyBState и Projectile

### ProjectileFlyBState::init : проверки (PF:72–170)
УСЛОВИЕ:   оружие, клетка, ОВ (`haveTU` при `_range == 0`), заряд, юнит не выбыл
РЕЗУЛЬТАТ: любая неудача → `popState` без выстрела
СТОРОНЫ:   оба

### ProjectileFlyBState::init : реакция (PF:100, 119–126)
УСЛОВИЕ:   `reactionShoot = _unit->getFaction() != getSide()`
ДАННЫЕ:    цель в клетке — ИСТИНА; выбранный юнит
РЕЗУЛЬТАТ: цели нет, она выбыла, превысила порог или `target != getSelectedUnit()` → `popState`. Значит, выстрел
           реакции, поставленный в очередь, пропадает, если к его началу выбран другой юнит или цель упала от
           предыдущего выстрела реакции
СТОРОНЫ:   оба

### ProjectileFlyBState::init : ближний бой в упор, CQB (PF:173–285)
УСЛОВИЕ:   `getEnableCloseQuartersCombat()` (РУЛСЕТ), не THROW/LAUNCH, без турели, броня не `ignoresMeleeThreat`; рядом
           враг с `createsMeleeThreat`, ОВ и энергией на CQB, видит стрелка (`validMeleeRange`)
RNG:       RNG HERE: `RNG::percent(getCloseQuartersSneakUpGlobal())` PF:206 — на каждого кандидата; RNG HERE: бросок
           `meleeAttack` (через `subSequence`); RNG HERE: `RNG::generate(0, 5)` PF:254 — при провале
РЕЗУЛЬТАТ: провал → цель выстрела уводится (вниз, вверх, вбок), защитник тратит ОВ и энергию
СТОРОНЫ:   оба

### ProjectileFlyBState::init : точка прицела (PF:291–330)
УСЛОВИЕ:   `BA_LAUNCH || forceFire игрока || !getPanicHandled()` → центр клетки; иначе поиск точки на юните (`canTargetUnit`)
РЕЗУЛЬТАТ: `_targetVoxel`
СТОРОНЫ:   оба; со 2-го хода у стенда — всегда центр клетки (§1)

### ProjectileFlyBState::createNewProjectile (PF:449–635)
ДАННЫЕ:    `accuracyDivider = 100`, при `!getPanicHandled()` — 200 (PF:493–498)
RNG:       RNG HERE: `applyAccuracy` PR:415 `generate(0, 100)`; затем PR:436–437 (до 10 повторов при равномерном
           разбросе) или PR:458–459; PR:462 по высоте. Число бросков: от 4, зависит от режима разброса. Бросок
           траектории/броска (`calculateThrow`) — те же функции. RNG HERE: `addVaporCloud` PR:632 —
           `globalRandomState().subSequence()` на каждом шаге полёта (PR:510), если у оружия задан цвет пара:
           длина траектории меняет последовательность
РЕЗУЛЬТАТ: снаряд; нет траектории или линии огня → `abortTurn`, `popState` (PF:566–567, 609–610)
СТОРОНЫ:   оба

### Projectile : проверка «попадём не в ту клетку» (PR:131–175)
УСЛОВИЕ:   `test != V_EMPTY && FACTION_PLAYER && autoShotCounter == 1 && !forceFire && getPanicHandled() && не LAUNCH && не spray`
РЕЗУЛЬТАТ: отказ от выстрела, если первая преграда не цель
СТОРОНЫ:   только юниты игрока (бот); враг стреляет и по преграде

### ProjectileFlyBState::think : конец очереди выстрелов (PF:640–686)
УСЛОВИЕ:   снаряда нет и выстрелов больше нет (или стрелок выбыл, кончился заряд, нет пола)
RNG:       RNG HERE: `checkReactionFire(стрелок)` PF:673 — только при `!getUnitsFalling() && getPanicHandled()`
РЕЗУЛЬТАТ: `abortTurn`, `convertInfected`, `popState`
ВОЗВРАТ:   `handleAI` стрелка (следующее решение) или, для реакции, — продолжение хода ходящей стороны
СТОРОНЫ:   оба; со 2-го хода у стенда реакции на выстрел нет (§1)

Попадание и урон: `ExplosionBState` / `TileEngine::hit` → `BattleUnit::damage`. RNG по ходу: сторона брони
(BU:1699–1705), `RuleDamageType::getRandomDamage` (RuleDamageType.cpp:50, 141, 219, 272–274), особый шанс предмета
(ExplosionBState.cpp:132), анимация взрыва — `RNG::generate` ×2 на каждую вспышку (ExplosionBState.cpp:242–243),
сеяный RNG, число вспышек от силы. Здесь — только как точки, сдвигающие последовательность; подробности не прослежены.
Попадание по юниту прицельным, снэп- или автовыстрелом другой фракции → `setWasHitBy` (BU:1973) — ПАМЯТЬ для реакций.

## 5. MeleeAttackBState

### MeleeAttackBState::init (MA:57–160)
ДАННЫЕ:    `reactionShoot = faction != side` → цель должна быть выбранным юнитом (как у выстрела); ОВ `spendTU` (MA:113);
           цель — `ai->getTarget()` для юнита ходящей стороны, не игрока (MA:128–135, ПАМЯТЬ ИИ), иначе юнит в клетке
           цели (ИСТИНА); у HOSTILE `_hitNumber = getAIMeleeHitCount() - 1` (РУЛСЕТ, MA:154–157)
RNG:       бросок попадания — `meleeAttackCalculate` через `subSequence` (TE:4887) внутри `ExplosionBState`
РЕЗУЛЬТАТ: `performMeleeAttack` → `statePushFront(ExplosionBState)`, `_reaction = true` (MA:220–243)
СТОРОНЫ:   оба; повторные удары `getAIMeleeHitCount` только у HOSTILE — у бота нет

### MeleeAttackBState::think (MA:165–215)
РЕЗУЛЬТАТ: после взрыва — `checkReactionFire(атакующий)` **без** условия на панику (MA:168–175); сработала → return
           (удар закончится после реакции); повторный удар — если своя сторона, цель жива, есть заряд, `spendTU`; иначе
           `popState`
СТОРОНЫ:   оба

## 6. Паника

### BattleUnit::prepareMorale (BU:2819–2851), начало хода стороны
УСЛОВИЕ:   `prepareNewTurn` → `updateUnitStats` → `prepareMorale(recovery)` (BU:2959), юнит не выбыл
ДАННЫЕ:    мораль — ИСТИНА; `getBerserkChance` — РУЛСЕТ
RNG:       RNG HERE: `RNG::percent(100 - 2 * morale)` BU:2825 — **всегда** для живого юнита стороны (и при шансе ≤ 0);
           при провале: `berserkChance == -1` → `generate(0, 2)` BU:2831, иначе `percent(berserkChance)` BU:2835
РЕЗУЛЬТАТ: `STATUS_BERSERK` или `STATUS_PANICKING`, `_wantsToSurrender`
ВОЗВРАТ:   разбор — `handlePanickingUnit` при выборе юнита
СТОРОНЫ:   оба; порядок бросков — порядок `_units` (SBG:1606)

### BattlescapeGame::handlePanickingUnit (BG:1647–1757)
УСЛОВИЕ:   статус PANICKING/BERSERK; вызов из `think` для выбранного юнита ИИ и бота (BG:238); у живого игрока — из
           `handlePanickingPlayer` (BG:1629)
RNG:       RNG HERE: звук `RNG::generate(0, size-1)` BG:1688 — если звуков паники больше одного (сеяный RNG ради звука);
           RNG HERE: `flee = RNG::percent(50)` BG:1715 — всегда; RNG HERE: при PANICKING и `flee` — до 20 попыток
           `generate(-5,5)` ×2 BG:1733, путь до клетки
РЕЗУЛЬТАТ: `setSelectedUnit(unit)`; инфобокс; бегство: бросить оружие из рук, `UnitWalkBState`; затем `UnitPanicBState`
ВОЗВРАТ:   `true` → `handleAI` в этот тик не зовётся; следующий тик — снова этот юнит (статус уже STANDING)
СТОРОНЫ:   оба. У бота паника бойцов разбирается по одному, когда очередь выбора доходит до паникующего, а не
           пачкой в начале хода, как у живого игрока

### UnitPanicBState::think (UP:59–146)
RNG:       берсерк — до 10 выстрелов (AUTO → SNAP → AIMED при `EXTENDED_BERSERK_WITH_AIMED`); цель — ближайший видимый,
           иначе RNG HERE `generate(-6, 6)` ×2 UP:116; плюс броски каждого выстрела (§4)
РЕЗУЛЬТАТ: в конце `abortTurn`, `clearTimeUnits`, `moraleChange(+15)`, `popState` (UP:139–145)
ВОЗВРАТ:   юнит без ОВ → `handleAI`: `TU <= 5` → `dontReselect` и смена юнита
СТОРОНЫ:   оба

## 7. Гибель и оглушение посреди действия

### BattlescapeGame::checkForCasualties (BG:853–1138)
УСЛОВИЕ:   после взрыва/удара/попадания и в `endTurn` (BG:782)
RNG:       прямых вызовов нет
РЕЗУЛЬТАТ: мораль: убийце `+20*mod/100` (BG:999), штраф за своих и нейтралов (BG:1005–1016); своим убитого
           `-(modifier * moraleLossModifierWhenKilled * 200 * bravery / loserMod / 100 / 100)` (BG:1035), победителям
           `+10*winnerMod/100` (BG:1045); оглушение даёт мораль при `getStunningImprovesMorale` (BG:1092–1105).
           Убит HOSTILE → `murderer->setTurnsSinceSpotted(0)` (BG:1039): **враг узнаёт, где убийца, даже если его не
           видел** — СТОРОНА получает ИСТИНУ. `statePushNext(UnitDieBState)`
ВОЗВРАТ:   мораль сказывается на панике только в начале хода стороны (§6)
СТОРОНЫ:   оба

### Гибель выбранного юнита ИИ
- Свой ход, юнит погиб от реакции во время ходьбы: ходьба уже снята (`cancelCurentMove`), реакция — состояние
  реактора. `popState` реакции видит выбывшего выбранного → `cancelCurrentAction`, на ходу врага
  `selectNextPlayerUnit(true, true)` (BG:1483), на ходу бота `setSelectedUnit(0)` (BG:1481) и выбор в `think` (BG:259).
- `_AIActionCounter` при этом не сбрасывается: сброс BG:1418–1420 срабатывает только когда снятое состояние
  принадлежало юниту не-игрока. Следующий юнит начинает с чужим счётчиком (`01_pipeline.md`, слепое пятно 1).
- Цель ИИ выбыла: `setCharging(0)` в начале `think` (AIM:564–567); остальное — в карточках режимов.

## 8. RNG: что зависит от решений ИИ и что можно менять побайтно

Определения RNG (`src/Engine/RNG.h`): `percent(v)` = `generate(0, 99) < v` — **бросок тратится всегда**, при любом `v`;
`generate` двигает зерно ровно раз; `subSequence()` зовёт `next()` и двигает зерно один раз; `shuffle` — `n-1` бросков;
`seedless` и `getSeed` зерно не двигают.

### 8.1 Броски, число которых задаёт решение ИИ
| что | где | от какого решения зависит |
|---|---|---|
| все `setup*` каждого `think` | AIM, SBG (`01_pipeline.md` §3) | число `think` за ход: проходы, `BA_RETHINK`, подбор оружия, прерывания |
| `percent(10)` патруля | AIM:682 | брошен, только если known/visible/spotting = 0 |
| снайпер | AIM:1839 | `_knownEnemies`, без пси-успеха, без бластера, есть `unitRules` (у бойцов бота нет — броска нет) |
| `generate(0, 3)` | AIM:1904 | только при `_spottingEnemies == 0` и без атаки |
| `percent(meleeOdds)` | AIM:4338 | только если `meleeOdds > 0 && health >= 2/3` |
| `evaluateAIMode` | AIM:2845 | только при `evaluate` |
| звук агрессии | BU:4858 | рывок (`setCharging`) и `aggroSound` |
| аптечка | AIM:370, 394, 404 | первый `think` за ход и условия карточки 15 |
| реакция | TE:2892 | **длина пути**: бросок на каждого пригодного реактора на **каждом** шаге; выбор клетки и маршрута |
| CQB | PF:206, 254 | выбор позиции стрельбы рядом с врагом |
| разброс выстрела | PR:415–462 | режим огня (число выстрелов), разброс равномерный или нет |
| пар | PR:632 | длина траектории (цель и оружие) |
| урон, сторона брони, особый шанс, анимация взрыва | RuleDamageType.cpp, BU:1699–1705, ExplosionBState.cpp:132, 242–243 | цель, оружие, сила взрыва |
| паника | BU:2825–2835, BG:1688–1733, UP:116 | порядок `_units`, мораль (в том числе от убийств, которые сделал ИИ) |
| `getPatrolNode` | SBG:2305–2378 | достигнут ли узел, был ли `_toNode` |

### 8.2 Какие правки сохраняют последовательность бросков
Правка не меняет бой побайтно, только если **не меняет ни одного решения и ни одного вызова RNG** до того места, где
она проявится. На практике:
- Безопасно: замена порога или формулы внутри уже вызываемого `percent(x)` / `generate`, **если результат сравнения
  не меняется** на тех данных (меняется — меняется решение, дальше всё расходится). Зонды, читающие `getSeed()`.
  Перестановка проверок без RNG. Кэширование вычислений без RNG (`findReachable`, FOV), если результат тот же.
- Меняет последовательность сразу: перестановка или добавление условий перед бросками с коротким замыканием
  (AIM:682, 1839, 1904, 4338); новое или убранное `think` (`BA_RETHINK`, лимит `maxActions`, второй проход); новый
  `setup*` или его вызов при другом условии (шаги 12–15 конвейера); любое изменение пути (число шагов → число
  проверок реакции); смена режима огня; смена цели (урон, броня, пар); `setCharging` у юнитов со звуком агрессии.
- Меняет бой неизбежно, даже при «тех же» решениях ИИ: исправление флага паники (§1) — меняет точность, цель
  выстрела, реакцию на выстрел и остановки ходьбы на всех ходах после первого; включение/выключение `lightSkip`
  и `walkFovKeep` бросков не трогает (без RNG), но если FOV или свет различаются, различаются и знание и решения.

## Числа

| что | значение | файл:строка | на что влияет |
|---|---|---|---|
| делитель точности | 100, при `!getPanicHandled()` 200 | PF:493–498 | разброс всех выстрелов и бросков |
| реакции одного реактора | `count > 10` — хватит | TE:2534 | максимум выстрелов реакции |
| снижение счёта реакции | `cost.Time * reactions / tu` | TE:2733 | повторная реакция того же юнита |
| шанс реакции | 100; на удар — 100 при `EXTENDED_MELEE_REACTIONS > 0`, иначе 0; скрипты | TE:2875–2890 | бросок TE:2892 |
| порог точности реакции | `getReactionFireThreshold(faction)` | TE:2634 | кто попадает в список реакторов |
| застревание | `_walkAbortCounter > 200` | AIM:509 | ОВ = 0 |
| паника | `100 - 2*morale`; берсерк 1/3 или `berserkChance` | BU:2824–2835 | статус |
| бегство при панике | 50 %; клетка ±5 по x/y, до 20 попыток | BG:1715–1733 | ходьба |
| берсерк | до 10 выстрелов; без цели клетка ±6 | UP:65, 116 | стрельба |
| после паники | ОВ = 0, мораль +15 | UP:142–143 | конец хода юнита |
| мораль убийцы | +20·mod/100 | BG:999 | паника |
| мораль своих за убитого | `-(mod · lossMod · 200 · bravery / loserMod / 10000)` | BG:1035 | паника |

## RNG (в порядке исполнения одного действия)

| # | вызов | файл:строка | условие |
|---|---|---|---|
| 1 | встать из приседа → реакция | BG:633 → TE:2892 | юнит сидел |
| 2 | мина на шаге | UW:226 (не прослежено) | есть мина рядом |
| 3 | реакция на шаг | UW:250 → TE:2892 | на каждом шаге, на каждого реактора, дошедшего до броска |
| 4 | CQB | PF:206, 254 + `meleeAttack` | правило мода, враг вплотную |
| 5 | разброс | PR:415, 436–437 / 458–459, 462 | каждый выстрел (авто — на каждый) |
| 6 | пар | PR:632 | цвет пара у оружия, каждый шаг полёта |
| 7 | урон, сторона брони, особый шанс, анимация взрыва | RuleDamageType.cpp, BU:1699–1705, ExplosionBState.cpp:132, 242–243 | попадание/взрыв |
| 8 | реакция на выстрел | PF:673 → TE:2892 | только при `getPanicHandled()` |
| 9 | удар: попадание | TE:4887 (`subSequence`) | ближний бой |
| 10 | реакция на удар | MA:171 → TE:2892 | всегда |
| 11 | паника на старте хода | BU:2825, 2831/2835 | каждый живой юнит стороны |
| 12 | разбор паники | BG:1688, 1715, 1733; UP:116 | паникующий выбран |
| 13 | опыт (реакция и прочее) | TE:3012–3032, 3133 | начисление опыта (не прослежено, когда именно вызывается) |

## Знание

| данные | метка | где |
|---|---|---|
| занятость клетки на пути, юнит на пути | ИСТИНА | UW:144, 374 |
| новый замеченный враг | ЮНИТ (`_unitsSpottedThisTurn`) | UW:235, 442 |
| реакторы: дистанция, счёт реакции | ИСТИНА | TE:2580–2586 |
| реакторы: сектор, линия, видимость | ЮНИТ (реактора) | TE:2620 |
| `gotHit` | ПАМЯТЬ (`_wasHitBy`, `hitState`, `meleeAttackedBy`) | TE:2611–2616 |
| реакция делает цель видимой стороне игрока и реактору | меняет СТОРОНА/ЮНИТ | TE:2628–2630 |
| убийство HOSTILE раскрывает убийцу | ИСТИНА → СТОРОНА | BG:1039 |
| цель удара врага | ПАМЯТЬ ИИ (`getTarget`) | MA:128–135 |
| мораль, порог паники, `berserkChance`, `getAIMeleeHitCount`, CQB | ИСТИНА / РУЛСЕТ | BU:2824–2835, MA:156, PF:173 |

## Слепые пятна (доказаны кодом)

1. Флаг `getPanicHandled()` в боях стенда ложен со 2-го хода, и все проверки «нет паники» (точность, цель выстрела,
   реакция на выстрел, остановка по новому врагу, резерв ОВ, ОВ бота после ходьбы, поворот) работают как при
   панике (§1).
2. Прерванная ходьба не вызывает `postPathProcedures`: у врага теряются `finalAction` (конец хода), `finalFacing`, разворот
   «hiding» и удар после рывка; юнит думает снова.
3. Ветка «Uh-oh! Company!» (UW:276–281) мёртвая: `unitSpotted` к ней всегда ложен.
4. У бота (FACTION_PLAYER) `postPathProcedures` не делает ничего из решений ИИ (UW:482): нет разворота в конце пути, нет
   удара после рывка, нет конца хода по `finalAction`.
5. Выстрел реакции, поставленный в очередь, отменяется, если выбранный юнит сменился (PF:123, MA:96–102) — например,
   ходящий юнит уже погиб от предыдущего реактора.
6. Повторные удары `getAIMeleeHitCount` получает только HOSTILE (MA:154), бот — нет.
7. Проверка реакции раскрывает цель реактору и стороне игрока (`addToVisibleUnits`, `setVisible`) независимо от
   выстрела (TE:2628–2630).
8. У живого игрока паника своих разбирается в начале хода пачкой; у бота — по одному при выборе юнита (BG:238), с другим
   порядком бросков.

## Не прослежено

- `checkForProximityGrenades` (BG:3376) — есть ли бросок RNG, какие состояния толкает.
- `cancelCurrentAction` при гибели выбранного посреди ходьбы — что делает с состоянием ходьбы в очереди.
- `PsiAttackBState` — порядок бросков и реакция (карточка 13).
- Когда именно начисляется опыт с бросками TE:3012–3032, 3133 (в бою или в конце).
- Встречается ли зависание UT:140 на ходу врага в боях стенда (вывод из кода, боем не проверен).
- `UnitFallBState` и `UnitDieBState` изнутри.
