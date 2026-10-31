# PATROL: выбор узла, путь к нему, конец патруля, префикс оглушения бота

Код: `src/Battlescape/AIModule.cpp` (`setupPatrol`, `endPatrolIfSpent`, `spendPatrol`, ветка `AI_PATROL` в `think`),
`src/Savegame/SavedBattleGame.cpp` (`getPatrolNode`), `src/Battlescape/BattlescapeGame.cpp` (`handleAI`, ходьба),
`src/Battlescape/AiProbe.cpp` (флаги стенда). Флаги V4, которые здесь меняют ветку: `STALE_PATROL_NODE`, `STALE_EXACT`,
`PATROL_STUN_PREFIX` (только бот), `KNOWN_OCCUPANT_PATH_V2` (только враг, на патруль не действует, см. ниже).

## 1. Дерево вызовов

```
BattlescapeGame::handleAI(unit)                                 BattlescapeGame.cpp:371
  unit->think(&action) -> AIModule::think                         BattlescapeGame.cpp:447, AIModule.cpp:506
    _patrolWalk = false; _patrolRetry = (_patrolRetry==1 ? 2 : 0)  AIModule.cpp:517-518
    _knownEnemies / _visibleEnemies / _spottingEnemies            AIModule.cpp:532-534
    _reachable = findReachable(...)                               AIModule.cpp:550
    [isLeeroyJenkins -> dont_think -> setupPatrol (враг)]         AIModule.cpp:598-602, 271
    setupEscape / setupAmbush / setupAttack                       AIModule.cpp:640-654
    setupPatrol()   <- вызывается в КАЖДОМ think                  AIModule.cpp:657
      узел достигнут -> _fromNode=_toNode, freePatrolTarget, faceWindow-поворот   :1385-1406
      _fromNode==0 -> ближайший не-dummy узел на том же z          :1408-1428
      [STALE_PATROL_NODE] проверка пути к сохранённому _toNode     :1438-1493
        witnessReach / calculate+abortPath / settleWitness (Pathfinding)
      while (_toNode==0 && triesLeft) (5 попыток)                  :1496-1598
        scout = ...                                               :1500-1513
        [STR_BASE_DEFENSE] стрельба по модулю / узел-цель           :1517-1579
        getPatrolNode(scout) -> getPatrolNode(!scout)              :1581-1588 -> SavedBattleGame.cpp:2317
        calculate(BAM_NORMAL), startDirection==-1 -> _toNode=0      :1590-1597
      allocateNode, _patrolAction = BA_WALK к узлу | BA_RETHINK     :1610-1621
    evaluate (AI_PATROL: ... || RNG::percent(10))                 AIModule.cpp:682
    evaluateAIMode -> (03_modes.md)                               AIModule.cpp:714
    tacticalMode (бот)                                            AIModule.cpp:745
    case AI_PATROL: _reserve по агрессии, action <- _patrolAction  AIModule.cpp:767-789
      endPatrolIfSpent(action, true)                              AIModule.cpp:788 -> :1331
    halfWalk (вне V4)                                             AIModule.cpp:843
    BA_WALK на свою клетку -> BA_NONE "walk.self"                  AIModule.cpp:866-878
  BA_RETHINK -> второй think                                      BattlescapeGame.cpp:449-453
  BA_WALK: calculate(action.target, BAM_NORMAL)                   BattlescapeGame.cpp:521
    isPatrolWalk && patrolStunReserve -> abortPath (бот, V4)       BattlescapeGame.cpp:535-539
    isPatrolWalk && patrolOutOfEnergy -> spendPatrol (вне V4)      BattlescapeGame.cpp:541-544
    startDirection != -1 -> UnitWalkBState                        BattlescapeGame.cpp:545-548
UnitWalkBState: остановка при новом замеченном враге, огне на реакцию, нехватке ОВ/энергии/резерва
```

## 2. Развилки

### think : пересмотр режима из патруля (AIModule.cpp:681-683)
УСЛОВИЕ:   `case AI_PATROL: evaluate = (bool)(_spottingEnemies || _visibleEnemies || _knownEnemies || RNG::percent(10));`
ДАННЫЕ:    `_spottingEnemies` (ИСТИНА положения + СТОРОНА отбора, см. `getSpottingUnits` AIModule.cpp:2201), `_visibleEnemies` (ЮНИТ, `TileEngine::visible`, AIModule.cpp:2249), `_knownEnemies` (СТОРОНА; у не-HOSTILE всегда 0, AIModule.cpp:2183)
RNG:       RNG HERE: `RNG::percent(10)` AIModule.cpp:682 — пересматривать ли режим без врагов; вызывается ТОЛЬКО если все три счётчика равны 0 (короткое замыкание `||`). `percent` всегда тратит один `generate(0,99)` (RNG.h:52-55)
РЕЗУЛЬТАТ: `evaluate` -> `evaluateAIMode()` (AIModule.cpp:714); также `evaluate=true` при `_weaponPickedUp`, `_spottingEnemies > 2`, здоровье `< 2*health/3` (:695-704) и при `isCheating() && _AIMode != AI_COMBAT` (:707-710)
ВОЗВРАТ:   дальше `tacticalMode` (бот), затем `switch (_AIMode)`
СТОРОНЫ:   оба. У бота `_knownEnemies == 0` всегда (countKnownTargets считает только для `FACTION_HOSTILE`), поэтому бросок `percent(10)` у бота тратится в каждом think, где он никого не видит и его никто не видит

### setupPatrol : узел достигнут (AIModule.cpp:1385-1406)
УСЛОВИЕ:   `_toNode != 0 && _unit->getPosition() == _toNode->getPosition()`
ДАННЫЕ:    позиция юнита (ИСТИНА о себе), `_toNode` (ПАМЯТЬ), стены клетки (ИСТИНА карты)
RNG:       нет
РЕЗУЛЬТАТ: `_fromNode = _toNode`; `freePatrolTarget()` (снимает `allocate`, :4408-4414); `_toNode = 0`; `faceWindow(pos)` (TileEngine.cpp:5673) — первая из 4 сторон клетки (N, E, S, W), где стена не закрывает обзор (`getBlock(DT_NONE)==0`, это блок зрения, MapData.cpp:172-173); если направление `!= -1` и не текущее — юнит поворачивается сразу, без траты ОВ в этой функции (`lookAt`, цикл `turn()`)
ВОЗВРАТ:   дальше поиск `_fromNode`/нового узла
СТОРОНЫ:   оба. Поворот выполняется внутри think, до выбора режима, то есть даже если режим потом не PATROL

### setupPatrol : нет исходного узла (AIModule.cpp:1408-1428)
УСЛОВИЕ:   `_fromNode == 0`
ДАННЫЕ:    все узлы карты (ИСТИНА карты), позиция юнита, размер брони (РУЛСЕТ)
RNG:       нет
РЕЗУЛЬТАТ: ближайший по `Position::distanceSq` не-dummy узел, у которого `z` равен `z` юнита и `(!(type & TYPE_SMALL) || size == 1)`; при равенстве — первый по порядку (`d < closest`)
ПРЕРЫВАНИЕ: если на уровне юнита подходящего узла нет — `_fromNode` остаётся 0
ВОЗВРАТ:   дальше
СТОРОНЫ:   оба. У бота модуль создаётся с `node = 0` (BattlescapeGame.cpp:422), поэтому первый патруль бота всегда начинается с этого поиска; врагу узел задаётся при генерации (`setStartNode`, AIModule.h:184)

### setupPatrol : проверка сохранённого узла STALE_PATROL_NODE (AIModule.cpp:1438-1493)
УСЛОВИЕ:   `staleCheck = keptNode && AiProbe::stalePatrolNode()`, `keptNode = _toNode != 0` (:1431). Флаг `OXCE_AI_STALE_PATROL_NODE` (AiProbe.cpp:4185)
ДАННЫЕ:    `_toNode` (ПАМЯТЬ), путь юнита (поиск `Pathfinding` с блокировкой юнитами по правилу фракции — см. `31_pathfinding.md`)
RNG:       нет (в Pathfinding RNG нет)
РЕЗУЛЬТАТ: `exact = AiProbe::staleExact()` (0..3, AiProbe.cpp:4242; V4: 1). При `exact && !pf->getKnownOccupant(_unit)` — `witnessReach(_unit, node, 4, ...)`: `1` -> путь есть (`ans=1`), `0` или `-1` -> пути нет (`ans=0`), иначе (`2` не решено, `3` юнит стоит на узле) -> `ans=2`. `exact==3` — сломанный контроль (вне V4). При `ans==2 || exact==2` — полный `calculate(_unit, node, BAM_NORMAL)` + `abortPath()`; иначе `settleWitness(_unit)` (оставляет состояние Pathfinding таким, каким его оставил бы `calculate`+`abortPath`, Pathfinding.h:109-111). Нет пути -> `freePatrolTarget(); _toNode = 0` (:1488-1492), запоминается `staleOld`
ПРЕРЫВАНИЕ: —
ВОЗВРАТ:   цикл поиска нового узла (он запустится, потому что `_toNode == 0`)
СТОРОНЫ:   оба (флаг глобальный, счётчики `p.`/`h.patrol_stale.*`). Без флага (OXCE) сохранённый узел НЕ проверяется вовсе: `while (_toNode == 0 ...)` не входит, `_patrolAction` остаётся BA_WALK к старому узлу. `STALE_SHADOW` (AiProbe.cpp:4215) — зонд времени, вне V4

### setupPatrol : разведчик или страж (AIModule.cpp:1500-1513)
УСЛОВИЕ:   миссия не `"STR_BASE_DEFENSE"`: `scout = _save->isCheating() || !_fromNode || _fromNode->getRank() == 0 || (клетка юнита существует && getFire())`; иначе `scout = false`. В базовой обороне `scout` остаётся `true` (инициализация :1499)
ДАННЫЕ:    `isCheating()` (общий флаг боя, SavedBattleGame.cpp:1542-1545), ранг `_fromNode` (ИСТИНА карты), огонь на своей клетке (ИСТИНА)
RNG:       нет
РЕЗУЛЬТАТ: `scout` решает, из каких узлов выбирать (см. `getPatrolNode`)
СТОРОНЫ:   оба. `isCheating` не зависит от стороны: после хода `_cheatTurn` (по умолчанию 20, SavedBattleGame.cpp:76) или после `_cheatTurn/2` при `liveAliens <= 2` — разведчиками становятся ВСЕ, включая бота и нейтралов

### setupPatrol : базовая оборона, стрельба по модулю (AIModule.cpp:1517-1547)
УСЛОВИЕ:   `getMissionType() == "STR_BASE_DEFENSE"` и `size == 1 && getOriginalFaction() == FACTION_HOSTILE && _attackAction.weapon && accuracySnap && !arcingShot` оружия и патрона снапа, урон прямой, `ToTile > 0.01f`; затем `_fromNode->isTarget() && canUseWeapon(..., BA_SNAPSHOT) && getModuleMap()[x/10][y/10].second > 0`
ДАННЫЕ:    оружие (РУЛСЕТ), узел (ИСТИНА карты), карта модулей базы (ИСТИНА)
RNG:       нет
РЕЗУЛЬТАТ: перебор клеток `x..x+8`, `y..y+8` на `z = 1` (9×9, `i < x+9`), первая клетка с объектом `isBaseModule()` -> `_patrolAction = BA_SNAPSHOT` по клетке, `_foundBaseModuleToDestroy = getAIDestroyBaseFacilities()`; `return` из `setupPatrol` (узел не выбирается, не аллоцируется)
ПРЕРЫВАНИЕ: `_fromNode->isTarget()` разыменовывается без проверки на 0 (:1530); `_fromNode == 0` возможен, если на уровне юнита нет подходящего узла (см. выше) — не проверено, бывает ли на картах
ВОЗВРАТ:   think; в `evaluateAIMode` патруль с `BA_SNAPSHOT` остаётся патрулём (AIModule.cpp:2918)
СТОРОНЫ:   только исходный HOSTILE; в fair22 базовой обороны нет — проверить по `missions/fair22.txt` (не прослежено)

### setupPatrol : базовая оборона, ближайший узел-цель (AIModule.cpp:1548-1579)
УСЛОВИЕ:   то же оружие, но стрелять не по чему
ДАННЫЕ:    все узлы; юнит на клетке узла `getTile(...)->getUnit()` (ИСТИНА, без проверки tile на 0); `isTarget()` (`_reserved == 5`, Node.cpp:186-188); `isAllocated`; карта модулей
RNG:       нет
РЕЗУЛЬТАТ: узел-цель, не занятый юнитом своей фракции, не аллоцированный, в живом модуле; `if (!_toNode || (d < closest && node != _fromNode))` — первый подходящий берётся даже если он `_fromNode`
ВОЗВРАТ:   к `getPatrolNode`, если ничего не нашлось; затем проверка пути
СТОРОНЫ:   исходный HOSTILE

### setupPatrol : выбор узла (AIModule.cpp:1581-1588)
УСЛОВИЕ:   `_toNode == 0`
ДАННЫЕ:    см. `getPatrolNode`
RNG:       внутри `getPatrolNode` (ниже)
РЕЗУЛЬТАТ: `_toNode = getPatrolNode(scout, _unit, _fromNode)`; при 0 — `getPatrolNode(!scout, ...)`
ВОЗВРАТ:   проверка пути

### SavedBattleGame::getPatrolNode : потерянный юнит (SavedBattleGame.cpp:2322-2331)
УСЛОВИЕ:   `fromNode == 0`
RNG:       RNG HERE: `RNG::generate(0, nodes-1)` SavedBattleGame.cpp:2325 и в цикле :2328 — случайный исходный узел, повтор, пока узел dummy; вызывается только при `fromNode == 0`, число вызовов не ограничено (1 + число попаданий в dummy)
РЕЗУЛЬТАТ: случайный не-dummy `fromNode` (на любом уровне)
СТОРОНЫ:   оба

### SavedBattleGame::getPatrolNode : фильтр кандидатов (SavedBattleGame.cpp:2333-2361)
УСЛОВИЕ:   `end = scout ? все узлы : ссылки fromNode`; у стража пропуск ссылок `< 1` (:2337). Кандидат годен, если (дословно по :2340-2350): `!n->isDummy()`, `(n->getFlags() > 0 || n->getRank() > 0 || scout)`, `(!(type & TYPE_SMALL) || unit->isSmallUnit())`, `(!(type & TYPE_FLYING) || unit->getMovementType() == MT_FLY)`, `!n->isAllocated()`, `!(type & TYPE_DANGEROUS)`, `setUnitPosition(unit, pos, true)`, `getTile(pos) && !getTile(pos)->getFire()`, `(unit->getFaction() != FACTION_HOSTILE || !getTile(pos)->getDangerous())`, `(!scout || n != fromNode)`, `pos.x > 0 && pos.y > 0`
ДАННЫЕ:    узлы, флаги, ранги, типы (ИСТИНА карты); `isAllocated` (общий для ВСЕХ фракций, Node.cpp:171-184); занятость клетки `setUnitPosition(..., testOnly=true)` (ИСТИНА — любой юнит, SavedBattleGame.cpp:2632-2676); огонь (ИСТИНА); `getDangerous` (метка граната ИИ); `TYPE_DANGEROUS` ставится на узлы в `distanceSq < 4` от погибшего HOSTILE (UnitDieBState.cpp:116-128)
RNG:       нет
РЕЗУЛЬТАТ: `compliantNodes`; `preferred` — см. следующую развилку
СТОРОНЫ:   оба; запрет `getDangerous` — только для HOSTILE

### SavedBattleGame::getPatrolNode : предпочтительный узел (SavedBattleGame.cpp:2352-2358)
УСЛОВИЕ:   `if (!preferred || (unit->getRankInt() >= 0 && preferred->getRank() == Node::nodeRank[unit->getRankInt()][0] && preferred->getFlags() < n->getFlags()) || preferred->getFlags() < n->getFlags())`
РЕЗУЛЬТАТ: второе условие — частный случай третьего (оба требуют `preferred->getFlags() < n->getFlags()`), поэтому ранговая таблица `nodeRank` на выбор не влияет. Итог: первый по порядку обхода узел с наибольшим `flags` (строгое `<`, при равенстве остаётся первый)
RNG:       нет

### SavedBattleGame::getPatrolNode : итог (SavedBattleGame.cpp:2363-2387)
УСЛОВИЕ:   `compliantNodes.empty()` -> у большого не-разведчика рекурсия `getPatrolNode(true, ...)` (:2366-2369), иначе `return 0`. Разведчик -> случайный кандидат. Страж -> `preferred`
RNG:       RNG HERE: `RNG::generate(0, compliantNodes.size() - 1)` SavedBattleGame.cpp:2378 — какой узел возьмёт разведчик; вызывается только при `scout` и непустом списке (в т. ч. при рекурсии большого юнита)
РЕЗУЛЬТАТ: узел или 0
СТОРОНЫ:   оба

### setupPatrol : путь к выбранному узлу (AIModule.cpp:1590-1597)
УСЛОВИЕ:   `_toNode != 0`
ДАННЫЕ:    `calculate(_unit, node, BAM_NORMAL)` — лимит `maxTUCost = 1000` по умолчанию (Pathfinding.h:243), то есть НЕ текущие ОВ; блокировка юнитами — по правилу фракции (31_pathfinding.md)
RNG:       нет
РЕЗУЛЬТАТ: `getStartDirection() == -1` -> `_toNode = 0`; `abortPath()` всегда
ВОЗВРАТ:   следующая попытка цикла (всего 5, `triesLeft` :1429). Узел, отвергнутый по пути, НЕ помечается и не аллоцируется — следующий вызов `getPatrolNode` может вернуть его же
СТОРОНЫ:   оба. `KNOWN_OCCUPANT_PATH_V2` этот поиск не трогает (у него свои вызовы только в засаде и точке огня)

### setupPatrol : итог (AIModule.cpp:1600-1621)
УСЛОВИЕ:   `_toNode != 0`
РЕЗУЛЬТАТ: `_toNodeTurn = getTurn()`, если узел новый или очищен проверкой (:1601-1605); `stalePatrolChecked` — зонд записи (:1606-1609); `allocateNode()`; `_patrolAction = {BA_WALK, target = позиция узла}`. Иначе `_patrolAction.type = BA_RETHINK`
ВОЗВРАТ:   think
СТОРОНЫ:   оба. Узел аллоцируется в КАЖДОМ think, где он есть (`allocate` идемпотентен — `_allocated = true`), и освобождается только при достижении, при проверке STALE, при смерти юнита (UnitDieBState.cpp:114) — смена режима на COMBAT/ESCAPE его не освобождает

### think : действие патруля (AIModule.cpp:767-789)
УСЛОВИЕ:   `_AIMode == AI_PATROL` после `evaluateAIMode` и `tacticalMode`
ДАННЫЕ:    агрессия юнита (РУЛСЕТ/юнит), тип оружия в руке (РУЛСЕТ)
RNG:       нет
РЕЗУЛЬТАТ: `setCharging(0)`; если оружие `BT_FIREARM`: агрессия 0 -> `_reserve = BA_AIMEDSHOT`, 1 -> `BA_AUTOSHOT`, 2 -> `BA_SNAPSHOT`, иначе нет; `action->type/target = _patrolAction`; `endPatrolIfSpent(action, true)`
ВОЗВРАТ:   `halfWalk` (вне V4), затем `BA_WALK` на свою клетку -> `BA_NONE`, иначе `_escapeTUs = _ambushTUs = 0` (:866-878)
СТОРОНЫ:   оба. `_reserve` действует только у HOSTILE в свой ход: `checkReservedTU` берёт `ai->getReserveMode()` и прибавляет 33/40/50 % БАЗОВЫХ ОВ к цене шага (BattlescapeGame.cpp:1536-1553); у бота (PLAYER) резерв берётся из настройки сейва `getTUReserved()` (:1528, :1556+), `_reserve` модуля не читается

### endPatrolIfSpent (AIModule.cpp:1331-1349)
УСЛОВИЕ:   `_patrolWalk = _patrolAction.type == BA_WALK;` затем `_patrolWalk && _patrolSpent == unitTurn() && позиция == _patrolSpentAt && getEnergy() <= _patrolSpentEnergy`
ДАННЫЕ:    `_patrolSpent*` (ПАМЯТЬ, пишет только `spendPatrol`)
RNG:       нет
РЕЗУЛЬТАТ: при `retry && _patrolRetry == 0` -> `_patrolRetry = 1`, `action->type = BA_RETHINK` (второй think в том же `handleAI`); иначе `BA_NONE`
ВОЗВРАТ:   think
СТОРОНЫ:   оба, но `spendPatrol` вызывается ТОЛЬКО из BattlescapeGame.cpp:543 при `patrolOutOfEnergy` (`OXCE_AI_ENERGY_PATROL_END`, вне V4, AiProbe.cpp:3834). Начальное `_patrolSpent = -1` (AIModule.h:75), поэтому при V4 условие ложно всегда; функция только выставляет `_patrolWalk`, который нужен `isPatrolWalk` (AIModule.cpp:930-933) для префикса оглушения

### handleAI : ходьба патруля (BattlescapeGame.cpp:509-552)
УСЛОВИЕ:   `action.type == BA_WALK`
ДАННЫЕ:    `calculate(action.actor, action.target, BAM_NORMAL)` (:521) — путь заново, лимит 1000 ОВ
RNG:       нет (в этой части)
РЕЗУЛЬТАТ: `startDirection != -1` -> `UnitWalkBState`; иначе состояние не создаётся, действие уже посчитано в `_AIActionCounter` (:431) — ход юнита тратит одно из `maxActions` (2, AiProbe.cpp:3826-3831) впустую
ВОЗВРАТ:   следующий `handleAI` этого юнита (до 2 действий) или следующий юнит
СТОРОНЫ:   оба

### handleAI : префикс оглушения PATROL_STUN_PREFIX (BattlescapeGame.cpp:535-539, AiProbe.cpp:3888-3970)
УСЛОВИЕ:   `!walkToItem && ai->isPatrolWalk(action) && AiProbe::patrolStunReserve(_save, unit, action, startDirection != -1)`; внутри: `(v1 || v2) && pushed && careful(unit)`; v1 = `OXCE_AI_PATROL_STUN_RESERVE` (вне V4), v2 = `OXCE_AI_PATROL_STUN_PREFIX` (V4)
ДАННЫЕ:    путь (сейчас посчитанный), ОВ и энергия юнита (ИСТИНА о себе), броня: восстановление энергии и регенерация оглушения (РУЛСЕТ, формулы брони и бонусы солдата), смертельные раны в торс
RNG:       нет. Состояние юнита меняется временно: `stunRecoveryAt` ставит энергию через `spendEnergy` и возвращает её (AiProbe.cpp:3855-3884)
РЕЗУЛЬТАТ: шаги, которые оплатят ОВ и энергия (`steps`); `block = energy > 0 && after <= 0 && after < full`, где `after` — регенерация оглушения на начало следующего хода при энергии `now - energy`, `full` — при полной. v2: самый длинный префикс `k`, после которого условие не выполняется -> `keepPathPrefix(keep, cost)` (путь обрезан, ходьба идёт); `keep == 0` -> функция возвращает `true` и handleAI делает `abortPath()` — ходьбы нет. v1: при `block` ходьбы нет
ПРЕРЫВАНИЕ: —
ВОЗВРАТ:   дальше `patrolOutOfEnergy` (вне V4) и создание `UnitWalkBState` по (обрезанному) пути
СТОРОНЫ:   только бот (`careful`), только патрульная ходьба (`_patrolWalk`); ходьба засады, бегства, точки огня этим не ограничена

### UnitWalkBState : враг замечен по пути (UnitWalkBState.cpp:235-256, 441-455)
УСЛОВИЕ:   `unitSpotted = (!_action.ignoreSpottedEnemies && !_falling && !_action.desperate && _parent->getPanicHandled() && _numUnitsSpotted != _unit->getUnitsSpottedThisTurn().size())`
ДАННЫЕ:    список замеченных юнитом в этом ходу (ЮНИТ), обновляется `calculateFOV` после шага (:232) и после поворота (:441)
RNG:       нет здесь; огонь на реакцию `checkReactionFire` (:248) — см. `30_execution.md`
РЕЗУЛЬТАТ: `cancelCurentMove()` — ходьба прервана на текущей клетке; при повороте до первого шага списывается цена поворота (:446-450)
ВОЗВРАТ:   следующий `handleAI` этого юнита (если `_AIActionCounter < 2`) -> новый think с новым `_visibleEnemies`
СТОРОНЫ:   оба. У патруля `desperate == false` (ставится только в ESCAPE, AIModule.cpp:761), поэтому патруль останавливается на ПЕРВОМ замечании каждого нового в этом ходу врага; уже замеченный в этом ходу враг ходьбу не останавливает (размер списка не меняется)

## 3. Что делает патрульный, увидев врага по пути

1. Шаг -> `calculateFOV` -> если список замеченных в этом ходу вырос — остановка (UnitWalkBState.cpp:235, 241-244). Огонь
   на реакцию по нему — тоже остановка (:248-254). Иначе идёт дальше (`ignoreSpottedEnemies` у ИИ не ставится — не
   найдено в AIModule.cpp).
2. Если у юнита осталось действие (`_AIActionCounter < maxActions`), `handleAI` зовёт think заново. Теперь
   `_visibleEnemies > 0` -> `evaluate = true` (AIModule.cpp:682) без броска `percent(10)`.
3. `setupEscape` вызывается, если враг видит юнит (`_spottingEnemies`; у врага — если ещё и `!_escapeTUs`, у бота
   всегда, :640); `setupAmbush` — только у HOSTILE с известными врагами (:647); `setupAttack` — всегда; `setupPatrol` —
   тоже всегда, и старый `_toNode` сохраняется (проверяется STALE).
4. `evaluateAIMode` бросает режим (03_modes.md): при видимых врагах `patrolOdds = 15`, при видящих — 0 (AIModule.cpp:2689,
   2694); бой получает множитель по числу видимых.
5. У бота при `_spottingEnemies` `tacticalMode` (AIModule.cpp:2941): PATROL с годным укрытием -> ESCAPE («cover.patrol»,
   :2994-2995); без укрытия («nocover») режим остаётся каким выпал, в т. ч. PATROL — бот идёт к узлу на виду.
6. Если действий не осталось — юнит отложен (`selectNextPlayerUnit(true, _AISecondMove)`, BattlescapeGame.cpp:385);
   повторный выбор того же юнита — не прослежено.

## 4. Числа

| что | значение | выражение | файл:строка | на что влияет |
|---|---|---|---|---|
| шанс пересмотра режима без врагов | 10 % | `RNG::percent(10)` | AIModule.cpp:682 | выход из PATROL без контакта |
| попыток выбрать узел | 5 | `triesLeft = 5` | AIModule.cpp:1429 | сколько раз узел без пути заменяется |
| поиск исходного узла | тот же `z`, min `distanceSq` | `d < closest` | AIModule.cpp:1418-1425 | от какого узла считаются ссылки |
| сила проверки STALE | вес 4 | `witnessReach(..., 4, ...)` | AIModule.cpp:1451 | когда нужен полный `calculate` |
| «сломанный контроль» STALE | `wcost > 300` | `exact == 3` | AIModule.cpp:1453 | вне V4 |
| лимит пути к узлу | 1000 ОВ | `maxTUCost = 1000` | Pathfinding.h:243 | путь есть, даже если на него нужно несколько ходов |
| годность узла для стража | `flags > 0 || rank > 0` | | SavedBattleGame.cpp:2341 | узлы с нулём не берутся без `scout` |
| предпочтение стража | max `flags`, первый | `preferred->getFlags() < n->getFlags()` | SavedBattleGame.cpp:2352-2358 | детерминированный выбор |
| граница карты | `x > 0 && y > 0` | | SavedBattleGame.cpp:2350 | узлы в строке/столбце 0 не берутся |
| опасный узел | `distanceSq < 4` от погибшего HOSTILE | | UnitDieBState.cpp:124-126 | узел исключён навсегда |
| резерв HOSTILE на патруле | 50/40/33 % базовых ОВ | агрессия 0/1/2 -> AIMED/AUTO/SNAP | AIModule.cpp:770-785, BattlescapeGame.cpp:1546-1551 | ходьба останавливается раньше, «reserve» |
| `_cheatTurn` | 20 (по умолчанию) | `_turn > _cheatTurn` или `_turn > _cheatTurn/2 && liveAliens <= 2` | SavedBattleGame.cpp:76, 1542-1545 | все становятся разведчиками |
| модуль базы | клетки 9×9 на `z = 1` | `i < x+9`, `j < y+9` | AIModule.cpp:1535-1537 | по чему стреляет HOSTILE в обороне |
| действий на юнит | 2 | `maxActions` | AiProbe.cpp:125, 3826-3831 | сорванная ходьба съедает действие |
| префикс оглушения | `energy > 0 && after <= 0 && after < full` | | AiProbe.cpp:3923 | обрезка пути бота |

## 5. RNG (в порядке выполнения)

| # | вызов | файл:строка | что решает | когда вызывается |
|---|---|---|---|---|
| 1 | `RNG::generate(0, nodes-1)` (1 + повторы на dummy) | SavedBattleGame.cpp:2325, 2328 | случайный `fromNode` | только `fromNode == 0` (на уровне юнита нет годного узла); в каждом вызове `getPatrolNode`, т. е. до 2 раз за попытку |
| 2 | `RNG::generate(0, size-1)` | SavedBattleGame.cpp:2378 | узел разведчика | при `scout == true` и непустом списке; если первый вызов (scout) пуст, а второй (`!scout`) — страж, броска нет; если первый — страж и вернул 0, второй (scout) бросает; большой страж с пустым списком бросает через рекурсию |
| 3 | повторы 1-2 | — | — | до 5 попыток, следующая — только если у выбранного узла нет пути; число бросков зависит от результата поиска пути |
| 4 | `RNG::percent(10)` | AIModule.cpp:682 | пересмотр режима | только в AI_PATROL и при `_spottingEnemies == _visibleEnemies == _knownEnemies == 0` |
| 5 | `RNG::generate(1, sum)` в `evaluateAIMode` | AIModule.cpp:2845 | режим | при `evaluate` (03_modes.md) |

Хрупкость: (а) `setupPatrol` вызывается в каждом think, а разведчик бросает при каждом новом выборе — любая правка,
меняющая, есть ли путь к узлу (STALE, блокировка юнитами, проход), меняет число бросков в потоке; (б) бросок
`percent(10)` зависит от трёх счётчиков — правка, меняющая `_visibleEnemies` с 0 на 1 (например, видимость), убирает
бросок и сдвигает весь хвост; (в) `isCheating` переключает всех в разведчики одновременно — с этого хода патруль
тратит по броску на выбор.

## 6. Знание

| что читает патруль | метка | где |
|---|---|---|
| узлы, ранги, флаги, типы, ссылки | ИСТИНА карты | SavedBattleGame.cpp:2333-2351 |
| занятость клетки узла | ИСТИНА (любой юнит, видимый или нет) | `setUnitPosition(..., true)`, SavedBattleGame.cpp:2346 |
| узел занят планом другого юнита | ИСТИНА чужих планов (allocate общий для всех фракций) | Node.cpp:171-184, SavedBattleGame.cpp:2344 |
| огонь на клетке | ИСТИНА | SavedBattleGame.cpp:2347 |
| `getDangerous` | метка ИИ (граната), только HOSTILE | SavedBattleGame.cpp:2348 |
| `TYPE_DANGEROUS` | ИСТИНА гибели HOSTILE (видел ли кто — не проверяется) | UnitDieBState.cpp:116-128 |
| путь к узлу | поиск с блокировкой юнитами по правилу фракции | 31_pathfinding.md |
| свой `_toNode`, `_fromNode`, `_toNodeTurn` | ПАМЯТЬ | AIModule.h:61, 129 |
| `isCheating` | ИСТИНА (номер хода и число живых HOSTILE) | SavedBattleGame.cpp:1542-1545 |
| остановка по пути | ЮНИТ (список замеченных в этом ходу) | UnitWalkBState.cpp:235 |
| префикс оглушения | ИСТИНА о себе + РУЛСЕТ брони | AiProbe.cpp:3855-3884 |

## 7. Карточка режима PATROL

| пункт | ответ по коду |
|---|---|
| цель | дойти до узла сети (`Node`); у разведчика — случайный годный узел карты, у стража — соседний по ссылкам с наибольшими `flags`; в базовой обороне HOSTILE — узел-цель модуля или выстрел по модулю |
| кандидаты | узлы: все (разведчик) или ссылки `_fromNode` (страж); фильтр SavedBattleGame.cpp:2340-2350 |
| жёсткие отказы | dummy; `flags==0 && rank==0` у стража; размер/полёт; аллоцирован; `TYPE_DANGEROUS`; занят юнитом; огонь; `getDangerous` (HOSTILE); `fromNode` у разведчика; `x==0 || y==0`; нет пути (`calculate` -> `startDirection == -1`) |
| оценка | нет числовой оценки; страж — max `flags`, разведчик — равновероятно |
| штрафы | нет |
| видимость | не учитывается при выборе узла вовсе (ни своя, ни врага); только остановка по пути при новом замеченном |
| RNG | разведчик: 1 бросок на выбор; потерянный юнит: бросок исходного узла; см. §5 |
| первая или лучшая | страж — лучшая по `flags` (первая из равных); разведчик — случайная; попытки — первая с путём |
| ОВ | путь до 1000 ОВ (не текущих); узел может быть на несколько ходов вперёд; HOSTILE держит резерв 33-50 % базовых ОВ при огнестреле |
| энергия | при выборе не учитывается; у бота V4 — префикс оглушения (только патрульная ходьба); `ENERGY_PATROL_END` вне V4 |
| угроза ближнего боя врага | не учитывается (ни при выборе, ни при ходьбе) |
| другие враги | не учитываются; только косвенно — занятость клетки узла любым юнитом и блокировка пути |
| пропал путь | V4: STALE — проверка в каждом think, нет пути -> новый выбор; без флага — старый узел остаётся; в `handleAI` пути нет -> ходьбы нет, действие потрачено |
| запасные ветки | `getPatrolNode(!scout)`; 5 попыток; итог `BA_RETHINK`; в `evaluateAIMode` PATROL без `_toNode` и без модуля -> AMBUSH -> ESCAPE (AIModule.cpp:2911-2931) |

## 8. Слепые пятна (доказано кодом)

1. Выбор узла не смотрит ни на одного врага: в `getPatrolNode` и в цикле `setupPatrol` нет обращения к видимости,
   `_spottingEnemies`, знанию стороны или линии огня (SavedBattleGame.cpp:2317-2388, AIModule.cpp:1496-1598). Узел на
   виду у врага равен узлу в укрытии.
2. Занятость узла проверяется по ИСТИНЕ: `setUnitPosition(unit, pos, true)` видит и невидимого врага на клетке
   (SavedBattleGame.cpp:2346). Узел, где стоит незамеченный враг, отвергается — утечка истины в выбор.
3. `allocate` общий для всех сторон: узел, выбранный ботом, недоступен врагу и наоборот (SavedBattleGame.cpp:2344,
   AIModule.cpp:1612). Присутствие бота меняет патруль врага не через знание, а через сеть узлов.
4. Ранговая таблица `Node::nodeRank` в выборе не участвует: её условие — подмножество последующего
   (SavedBattleGame.cpp:2353-2356).
5. Страж выбирает детерминированно: если у `preferred` нет пути, тот же узел возвращается во всех 5 попытках
   (`calculate` не меняет кандидатов, аллокация — только в конце, :1612), затем `getPatrolNode(!scout)` не зовётся
   повторно — он зовётся, только если первый вызов вернул 0 (:1584-1587). Итог — `BA_RETHINK`, хотя другие соседи
   могли быть достижимы.
6. Путь к узлу ограничен 1000 ОВ, а не текущими: узел «с путём» может быть недостижим в этом ходу, ходьба обрывается
   по ОВ/резерву где придётся (AIModule.cpp:1592, Pathfinding.h:243).
7. Бот (PLAYER) не избегает клеток с меткой `getDangerous` — запрет только для HOSTILE (SavedBattleGame.cpp:2348).
8. Узел остаётся аллоцированным при смене режима: освобождение только при достижении, STALE и смерти (AIModule.cpp:1394,
   1490, UnitDieBState.cpp:114).
9. Угроза ближнего боя, раны, мораль, свет и дым в выборе узла не участвуют (полей нет в функциях выбора).
10. Остановка по пути реагирует только на НОВОГО в этом ходу замеченного; враг, уже замеченный ранее в ходу, патруль
    не останавливает (UnitWalkBState.cpp:235).
11. Префикс оглушения бота ограничивает только патрульную ходьбу (`isPatrolWalk`, BattlescapeGame.cpp:535); ходьба
    бегства и точки огня может опустить регенерацию оглушения до нуля.
12. Базовая оборона разыменовывает `_fromNode` без проверки (AIModule.cpp:1530) и клетку узла без проверки
    (`getTile(...)->getUnit()`, :1559).

## 9. Не прослежено

- Как `selectNextPlayerUnit(true, _AISecondMove)` возвращает отложенного юнита и сколько think он получает за ход.
- Есть ли в fair22 базовая оборона и бывает ли `_fromNode == 0` у HOSTILE на реальных картах.
- `witnessReach`/`settleWitness` внутри — см. `31_pathfinding.md`; совпадение с полным `calculate` доказано, по
  комментарию, режимом `exact == 2` на стенде, не в коде.
- Используется ли `UnitDieBState` и при потере сознания (тогда узлы помечаются и при оглушении HOSTILE).
- Сохраняются ли `_toNode`/`_fromNode` в сейве (AIModule::save/load) и что с аллокацией после загрузки.
- Влияние `getRankInt()` у юнитов без ранга на выбор (условие мёртвое, но `nodeRank[...]` читается при `rankInt >= 0`).
