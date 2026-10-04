# ESCAPE: отход на клетку, которую видит меньше врагов

Код: `src/Battlescape/AIModule.cpp` (`setupEscape` :1931-2173, вызовы в `think` :638-645 и `evaluateAIMode` :2692-2732,
ветка `AI_ESCAPE` в `think` :754-766, `tacticalMode` :2941-2996, `getSpottingUnits` :2201-2233, `selectNearestTarget` :2240-2287),
`src/Battlescape/BattlescapeGame.cpp` (`handleAI`), `src/Battlescape/UnitWalkBState.cpp` (`desperate`, `postPathProcedures`),
`src/Battlescape/AiProbe.cpp` (флаги и зонды).
Флаги V4, меняющие ветку: `ESCAPE_REACH_FIRST` (порядок «достижимость, потом линии огня»), `CAREFUL` у бота (бег по правилу
игрока, вызов `setupEscape` на каждом think, `tacticalMode`). Вне V4: `OXCE_AI_GAP`, `OXCE_AI_TURRET`, `OXCE_AI_FLEE`,
`OXCE_AI_REVIVE`, `OXCE_AI_TACTICS`, `OXCE_AI_ESCAPE_ALT_PROBE`, `OXCE_AI_ESCAPEPROF`.

## 1. Дерево вызовов

```
BattlescapeGame::handleAI                                          BattlescapeGame.cpp:371
  careful -> ai->setTargetFaction(FACTION_HOSTILE)                    :425-430
  _AIActionCounter == 1 -> unit->setHiding(false)                     :436-439
  unit->think(&action) -> AIModule::think                             :447
    _knownEnemies = countKnownTargets()   (0 у не-HOSTILE)            AIModule.cpp:532 -> :2179-2194
    _visibleEnemies = selectNearestTarget()                           :533 -> :2240-2287
    _spottingEnemies = getSpottingUnits(pos)                          :534 -> :2201-2233
    _reachable = findReachable(_unit, BattleActionCost())   (BAM_NORMAL, все ОВ и энергия)   :550
    [вне V4] AiProbe::revive / AiProbe::flee -> return                :551-560
    tactical = tactics(HOSTILE, вне V4) || careful(бот)               :638
    if (_spottingEnemies && (!_escapeTUs || tactical)) setupEscape()  :639-644
      selectNearestTarget() -> _aggroTarget  (видимая цель с линией огня)   :1938
      _escapeTUs = 0                                                  :1939
      dist = distance2d(pos, _aggroTarget) или 0                      :1941
      randomTileSearch = копия getTileSearch(); RNG::shuffle          :1959-1960
      while (tries < 150 && !coverFound)                              :1962
        run = allowsRunning(careful && small) && (tries & 1)          :1966
        tries -1: своя клетка (lastCover всегда invalid)              :1975-1983
        tries 0..120: pos + сдвиг 11x11, score 100 (+15 / RNG(-20,20)x2 для своей)   :1984-2003
        tries 121..149: pos + RNG(-10,10), RNG(-10,10), z + RNG(-1,1), score 110      :2004-2027
        tries++                                                       :2029
        член расстояния +10*|d(T) - dist|                             :2033-2041
        нет клетки -> -100001                                         :2043-2047
        [ESCAPE_REACH_FIRST] не в _reachable -> continue              :2052-2062
        spotters = getSpottingUnits(T)                                :2063
        не в _reachable -> continue                                   :2065-2066
        экспозиция ±10, огонь -40, опасная -100, [вне V4] GAP -60, TURRET -100   :2068-2089
        score > best -> calculate(T, getMoveType()) -> принять        :2104-2124
        best > 100 -> coverFound                                      :2126
      [вне V4] escapeAlt (зонд)                                       :2129-2134
      _escapeAction.target/run = лучшее                               :2135-2136
      best <= -100000 -> BA_RETHINK, иначе BA_WALK, _probeScore       :2155-2172
    setupAmbush / setupAttack / setupPatrol                           :646-658
    evaluate по режиму (AI_ESCAPE: !_spottingEnemies || !_knownEnemies)   :678-692
    evaluateAIMode()                                                  :712-714 -> :2669
      escapeOdds 15/12/5                                              :2677-2685
      _spottingEnemies && _escapeTUs == 0 -> setupEscape()            :2692-2700
      _knownEnemies && _escapeTUs == 0 && selectClosestKnownEnemy() -> setupEscape()  :2714-2733
      множители, RNG::generate(1, sum)                                :2750-2845
      запасная цепочка COMBAT -> PATROL -> AMBUSH -> ESCAPE           :2878-2932
    _evalChosen -> AI_COMBAT                                          :738-741
    tactical -> tacticalMode()  (переход в AI_ESCAPE)                 :743-746 -> :2941-2996
    case AI_ESCAPE: type/target/run из _escapeAction, finalAction, desperate, setHiding(true)   :754-766
    BA_WALK на свою клетку -> BA_NONE; иначе _escapeTUs = _ambushTUs = 0   :866-878
  BA_RETHINK -> второй think                                          BattlescapeGame.cpp:448-452
  нет оружия -> findItem / findBotWeapon могут переписать action      :459-482
  BA_WALK: calculate(actor, target, BAM_NORMAL) -> UnitWalkBState     :507-549
  BA_NONE: carefulGuard (бот) или следующий юнит                      :579-608
UnitWalkBState
  desperate -> новые замеченные не останавливают                     UnitWalkBState.cpp:235, 276, 442-444
  огонь на реакцию -> cancelCurentMove (без postPathProcedures)       :247-255
  шаги оплачиваются по getMoveType() (run)                            :306
  postPathProcedures: не PLAYER -> finalAction: dontReselect; hiding: разворот dir+4   :478-516
```

## 2. Развилки

### think : вызов отхода (AIModule.cpp:638-644)
УСЛОВИЕ:   `if (_spottingEnemies && (!_escapeTUs || tactical))`, `tactical = AiProbe::tactics(_unit) || AiProbe::careful(_unit)`
ДАННЫЕ:    `_spottingEnemies` (СТОРОНА отбора + ИСТИНА позиций, см. `getSpottingUnits` ниже); `_escapeTUs` (ПАМЯТЬ: с прошлого вызова в этом ходу, сброс `reset()` в начале хода, :162-170, SavedBattleGame.cpp:1564, и выбором ходьбы на другую клетку, :871); `careful` = бот и `FACTION_PLAYER` (AiProbe.cpp:367-371); `tactics` — только HOSTILE и `OXCE_AI_TACTICS` (вне V4, AiProbe.cpp:361-365)
RNG:       внутри `setupEscape` — см. ниже
РЕЗУЛЬТАТ: `setupEscape()`; без вызова `_escapeAction` остаётся с прошлого раза
ВОЗВРАТ:   `setupAmbush` (:646)
СТОРОНЫ:   HOSTILE при V4 — только пока `_escapeTUs == 0` (первый раз за ход или после ходьбы); бот — на каждом think, пока его видят. Зонды `probeMark('e')` / `probeSlot` пишут слот «escape»

### setupEscape : цель отхода (AIModule.cpp:1938-1941, 2240-2287)
УСЛОВИЕ:   `selectNearestTarget()`: обнуляет `_aggroTarget` и `_closestDist = 100` (:2243-2244); перебор юнитов с `validTarget(bu, true, true)` и `TileEngine::visible(_unit, bu->getTile())`; при `dist < _closestDist`: у `_rifle || !_melee` — `canTargetUnit` от точки выстрела своим оружием (:2259-2266), иначе `selectPointNearTarget` + `validMeleeRange` (:2268-2275)
ДАННЫЕ:    видимость юнитом (ЮНИТ), вес цели (СТОРОНА: `turnsSinceSpotted` против `_intelligence`, :4217-4224), позиция цели — ИСТИНА
RNG:       нет
РЕЗУЛЬТАТ: `_aggroTarget` — ближайшая видимая цель, по которой можно стрелять/до которой можно дойти; `dist = distance2d(pos, _aggroTarget)` или 0, если цели нет (:1941)
ПРЕРЫВАНИЕ: результат `selectClosestKnownEnemy()`, которым `evaluateAIMode` открывает вызов (:2723), здесь затирается — он служит только условием вызова. У ближнего бойца `selectPointNearTarget` пишет `_attackAction.target` (:2430); из `evaluateAIMode` это происходит уже после `setupAttack`
СТОРОНЫ:   все

### setupEscape : список кандидатов (AIModule.cpp:1959-1960, SavedBattleGame.cpp:79-84)
УСЛОВИЕ:   всегда
ДАННЫЕ:    `_tileSearch` — 121 сдвиг: `x = i%11 - 5`, `y = i/11 - 5`, i = 0..120 (квадрат 11x11 вокруг себя, включая (0,0)); копия перемешивается
RNG:       RNG HERE: `RNG::shuffle(randomTileSearch)` AIModule.cpp:1960 — порядок обхода 121 клетки; всегда, 120 вызовов `generate(0, i)` (RNG.h:83-89)
РЕЗУЛЬТАТ: порядок систематических попыток
СТОРОНЫ:   все

### setupEscape : бег на попытке (AIModule.cpp:1966)
УСЛОВИЕ:   `_escapeAction.run = allowsRunning(AiProbe::careful(_unit) && _unit->isSmallUnit()) && (tries & 1)`
ДАННЫЕ:    броня (РУЛСЕТ `allowsRunning`, nullable: не задано — берётся аргумент, Armor.cpp:1210-1213); `tries` до инкремента
RNG:       нет
РЕЗУЛЬТАТ: на нечётных `tries` (1, 3, ..., 149) кандидат проверяется путём бегом. Попытка −1 (`(-1) & 1 == 1`) — тоже «бегом»
СТОРОНЫ:   AI (не бот): бег только если броня явно разрешает (умолчание false). Бот: умолчание true для юнитов 1x1, броня может запретить

### setupEscape : попытка −1 — своя клетка (AIModule.cpp:1975-1983)
УСЛОВИЕ:   `tries == -1`; `_save->getTile(_unit->lastCover) != 0`
ДАННЫЕ:    `lastCover` — ИСТИНА о себе; присваивается только `TileEngine::invalid` = (−1,−1,−1) в обоих конструкторах (BattleUnit.cpp:118, 535; других записей в src нет), `getTile` для отрицательных координат даёт 0 (SavedBattleGame.h:271-278)
RNG:       нет
РЕЗУЛЬТАТ: ветка `lastCover` мёртвая; кандидат — своя клетка, `score = 0`
СТОРОНЫ:   все

### setupEscape : попытки 0..120 — систематический поиск (AIModule.cpp:1984-2003)
УСЛОВИЕ:   `tries < 121`; своя клетка (`target == pos`, сдвиг (0,0)) — отдельная ветка
ДАННЫЕ:    `unitsSpottingMe = getSpottingUnits(pos)` (:1934); z не меняется
RNG:       RNG HERE: `RNG::generate(-20,20)` AIModule.cpp:1995 и `RNG::generate(-20,20)` :1996 — сдвиг вместо своей клетки; только когда в перемешанном списке дошли до (0,0) и `unitsSpottingMe > 0` (один раз за вызов)
РЕЗУЛЬТАТ: `score = 100`; своя клетка без видящих — `+15` (`currentTilePreference`, :1935, :2000); своя клетка при видящих — случайная клетка в квадрате 41x41 (может уйти за карту -> −100001)
СТОРОНЫ:   все

### setupEscape : попытки 121..149 — отчаянный поиск (AIModule.cpp:2004-2027)
УСЛОВИЕ:   `tries >= 121`
ДАННЫЕ:    позиция юнита, `getMapSizeZ()`
RNG:       RNG HERE: `RNG::generate(-10,10)` AIModule.cpp:2016 (x), `RNG::generate(-10,10)` :2017 (y), `RNG::generate(-1,1)` :2018 (z) — случайная клетка; на каждой отчаянной попытке, 3 вызова; попыток до 29
РЕЗУЛЬТАТ: `score = 110`; z < 0 -> 0; z >= высоты -> свой z
СТОРОНЫ:   все

### setupEscape : член расстояния (AIModule.cpp:2033-2041)
УСЛОВИЕ:   `if (dist >= distanceFromTarget) score -= (distanceFromTarget - dist) * 10; else score += (distanceFromTarget - dist) * 10;`
ДАННЫЕ:    `distanceFromTarget = distance2d(_aggroTarget, T)` или 0 без цели; позиция цели — ИСТИНА
RNG:       нет
РЕЗУЛЬТАТ: обе ветки дают `+10 * |distanceFromTarget - dist|`: шаг к цели награждается так же, как шаг от неё. Без `_aggroTarget` член 0
СТОРОНЫ:   все

### setupEscape : клетка за картой (AIModule.cpp:2043-2047)
УСЛОВИЕ:   `!tile`
ДАННЫЕ:    размер карты
RNG:       нет
РЕЗУЛЬТАТ: `score = -100001`; зонд `escapeProbe(2)`; дальше `tile == 0` — ни трассы, ни принятия
СТОРОНЫ:   все

### setupEscape : достижимость и ESCAPE_REACH_FIRST (AIModule.cpp:2051-2066)
УСЛОВИЕ:   `inReach = std::find(_reachable..., getTileIndex(T)) != end`; при `!inReach && AiProbe::escapeReachFirst()` -> `continue` до `getSpottingUnits`; иначе `spotters = getSpottingUnits(T)`, затем `if (!inReach) continue`
ДАННЫЕ:    `_reachable` — ИСТИНА о себе, этот think (:550): Dijkstra `BAM_NORMAL` с бюджетом всех ОВ и энергии, стартовая клетка входит (Pathfinding.cpp:1855-1891); `escapeReachFirst` = `active() && OXCE_AI_ESCAPE_REACH_FIRST` (AiProbe.cpp:1891-1895)
RNG:       нет (`getSpottingUnits` — const; в теле `canTargetUnit`, TileEngine.cpp:2196+, вызовов RNG нет)
РЕЗУЛЬТАТ: недостижимая клетка отбрасывается в обоих режимах; флаг убирает только трассы линий огня к ней. `tries++` уже сделан (:2029) — попытка истрачена в обоих режимах. Итог и поток RNG одинаковы
СТОРОНЫ:   все; зонды `escapeMark` / `escapeSkipped` / `escapeProbe(0|1)` считают трассы и время (OXCE_AI_ESCAPEPROF)

### setupEscape : экспозиция (AIModule.cpp:2068-2078)
УСЛОВИЕ:   `if (_spottingEnemies || spotters)`: `_spottingEnemies <= spotters` -> `score -= (1 + spotters - _spottingEnemies) * 10`; иначе `score += (_spottingEnemies - spotters) * 10`
ДАННЫЕ:    `_spottingEnemies` из think (:534), `spotters` — `getSpottingUnits(T)`
RNG:       нет
РЕЗУЛЬТАТ: клетка, видимая тем же числом врагов, что и сейчас, — −10; на каждого лишнего — ещё −10; на каждого, кто перестаёт видеть, — +10. При `_spottingEnemies == 0 && spotters == 0` члена нет
СТОРОНЫ:   все

### getSpottingUnits : кто «видит» клетку (AIModule.cpp:2201-2233)
УСЛОВИЕ:   по всем юнитам `validTarget(bu, false, false)`; `distance2d(pos, bu) > 20` -> пропуск; `canTargetUnit(origin, tile(pos), ..., bu, false[, _unit])`
ДАННЫЕ:    отбор — СТОРОНА (вес > `getAITargetWeightThreatThreshold()`, т. е. цели, которых сторона знает не дольше `_intelligence` ходов; гражданские обычно ниже порога); позиции и глаза (`getSightOriginVoxel(bu)`, `z -= 2`) — ИСТИНА; для чужой клетки линия огня к гипотетическому юниту (`potentialUnit = _unit`)
RNG:       нет
РЕЗУЛЬТАТ: число врагов в 20 клетках с линией огня к клетке. Не проверяются: свет, дым, дальность зрения, направление взгляда врага, видит ли он клетку сейчас
СТОРОНЫ:   у бота `_targetFaction = HOSTILE` (BattlescapeGame.cpp:425-430) — считаются враги-HOSTILE; у HOSTILE — `FACTION_PLAYER` (конструктор, AIModule.cpp:65-69)

### setupEscape : огонь, опасность, GAP, TURRET (AIModule.cpp:2079-2089)
УСЛОВИЕ:   `tile->getFire()` -> −40; `tile->getDangerous()` -> −100; `closeEnemies(T) * 60`; `turretsSeeing(T) * 100`
ДАННЫЕ:    огонь — ИСТИНА карты; `getDangerous` — метка гранаты (ПАМЯТЬ стороны, общая для всех); GAP — видимые сейчас враги в 2 клетках на том же z (СТОРОНА, AiProbe.cpp:3576-3596); TURRET — известные турели с линией огня
RNG:       нет
РЕЗУЛЬТАТ: штрафы. При V4 `closeEnemies` и `turretsSeeing` возвращают 0: нужны `OXCE_AI_GAP` / `OXCE_AI_TURRET` (вне V4) и бот (AiProbe.cpp:3578-3582, 3706-3710)
СТОРОНЫ:   GAP/TURRET — только бот и только вне V4

### setupEscape : принятие кандидата (AIModule.cpp:2104-2127)
УСЛОВИЕ:   `tile && score > bestTileScore` -> `calculate(_unit, T, _escapeAction.getMoveType())` (лимит ОВ 1000, Pathfinding.h:243); принять, если `T == pos || getStartDirection() != -1`
ДАННЫЕ:    поиск пути — ИСТИНА о карте и юнитах (по правилам блокировки своей фракции); move type — `BAM_RUN` при `run`, иначе `BAM_NORMAL` (BattlescapeGame.h:98-101); цена бега — множитель брони `getMoveCostRun` (РУЛСЕТ, Pathfinding.cpp:892-901)
RNG:       нет (в Pathfinding.cpp вызовов RNG нет)
РЕЗУЛЬТАТ: `bestTileScore`, `bestTile`, `run`, `_escapeTUs = getTotalTUCost()` (только ОВ, энергия не пишется), для своей клетки `_escapeTUs = 1`; `abortPath()`; `bestTileScore > 100` -> `coverFound` и выход из цикла
ПРЕРЫВАНИЕ: путь отказа (`getStartDirection() == -1`) не меняет лучшее, но попытка истрачена. Путь «бегом» по A* может отличаться от пути Dijkstra `BAM_NORMAL`, по которому клетка попала в `_reachable`; цена бега не сверяется с оставшимися ОВ
СТОРОНЫ:   все

### setupEscape : итог (AIModule.cpp:2135-2172)
УСЛОВИЕ:   `bestTileScore <= -100000` -> `BA_RETHINK`; иначе `_probeScore = bestTileScore`, `BA_WALK`
ДАННЫЕ:    —
RNG:       нет
РЕЗУЛЬТАТ: `_escapeAction.target = bestTile`, `run`. Ветка `BA_RETHINK` недостижима: попытка −1 — своя клетка, она есть на карте и всегда в `_reachable` (старт, Pathfinding.cpp:1863-1891), её счёт `0 − экспозиция − огонь − опасность` > −100000, а своя клетка принимается без пути (:2108). Итог всегда `BA_WALK`, возможно на свою клетку
СТОРОНЫ:   все. Зонд `escapeAlt` (OXCE_AI_ESCAPE_ALT_PROBE && record && careful, AiProbe.cpp:3323-3327) и тэлли `gap.away/stuck`, `turret.away/stuck` (:2137-2149) решения не меняют

### evaluateAIMode : повторный вызов при видящих (AIModule.cpp:2692-2700)
УСЛОВИЕ:   `if (_spottingEnemies) { patrolOdds = 0; if (_escapeTUs == 0) setupEscape(); }`
ДАННЫЕ:    `_escapeTUs` после think
RNG:       внутри `setupEscape`
РЕЗУЛЬТАТ: так как think при видящих уже позвал `setupEscape` и тот всегда даёт `_escapeTUs >= 1`, здесь повторного вызова не бывает, кроме случая, когда think пропустил вызов (`_escapeTUs != 0` с прошлого вызова, не tactical) — тогда и здесь `_escapeTUs != 0`. Практически мёртвый вызов
СТОРОНЫ:   все

### evaluateAIMode : вызов по известным врагам (AIModule.cpp:2714-2738)
УСЛОВИЕ:   `_knownEnemies && _escapeTUs == 0`: `selectClosestKnownEnemy()` -> `setupEscape()`, иначе `escapeOdds = 0`; `else if (HOSTILE)` -> `combatOdds = 0; escapeOdds = 0`
ДАННЫЕ:    `_knownEnemies` (СТОРОНА, только HOSTILE, :2183); `selectClosestKnownEnemy` — `validTarget(bu, true, false)` (:2336-2353)
RNG:       внутри `setupEscape`
РЕЗУЛЬТАТ: HOSTILE, которого никто не видит, но который знает врагов, рассчитывает отход (`_spottingEnemies = 0`, `unitsSpottingMe = 0`); известны только гражданские -> `escapeOdds = 0`; HOSTILE без известных врагов — отход невозможен броском
СТОРОНЫ:   бот: `_knownEnemies == 0` всегда, ни эта ветка, ни обнуление не работают — `escapeOdds` остаётся базовым

### evaluateAIMode : шанс отхода (AIModule.cpp:2677-2845)
УСЛОВИЕ:   база 15; `_melee` -> 12; HOSTILE с `TU > base.tu/2` или `getCharging()` -> 5; затем множители (int, каждое `*=` усекает): в режиме ESCAPE ×1.1 (:2754); здоровье < 1/3 ×1.7, < 2/3 ×1.4, < полного ×1.1 (:2759-2774); агрессия 0 ×1.4, 2 ×0.7, иначе ×`Clamp(0.9 − aggr/10, 0.1, 2.0)` (:2777-2794); видящие: `escapeOdds = 10*escapeOdds*(_spottingEnemies+10)/100`, иначе `/= 2` (:2802-2810); `STR_BASE_DEFENSE` ×0.75 (:2832-2836)
ДАННЫЕ:    ЮНИТ (ОВ, здоровье, агрессия — РУЛСЕТ юнита), СТОРОНА (`_spottingEnemies`)
RNG:       RNG HERE: `RNG::generate(1, std::max(1, patrolOdds + ambushOdds + escapeOdds + combatOdds))` AIModule.cpp:2845 — выбор режима; при `evaluate` (:712)
РЕЗУЛЬТАТ: `decision <= escapeOdds` -> `AI_ESCAPE` (:2847, :2865-2868) — отрезок отхода первый
ПРЕРЫВАНИЕ: читерство HOSTILE или `getCharging()` -> `AI_COMBAT` (:2870-2874)
СТОРОНЫ:   бот: `escapeOdds` не обнуляется (нет ветки HOSTILE), без видящих — половина базы (7 для 15 после усечений)

### evaluateAIMode : запасная цепочка (AIModule.cpp:2878-2932)
УСЛОВИЕ:   COMBAT без годной атаки -> PATROL; PATROL без `_toNode`, модуля базы и `BA_SNAPSHOT` -> AMBUSH; AMBUSH при `_ambushTUs == 0` -> ESCAPE
ДАННЫЕ:    `_escapeAction` НЕ проверяется
RNG:       `findFirePoint` / `selectRandomTarget` — см. 12_combat_fire.md
РЕЗУЛЬТАТ: `AI_ESCAPE` с тем `_escapeAction`, что есть: если в этом ходу отход не считался — с прошлого вызова (любого прошлого хода) или пустой (`BA_NONE`, target (−1,−1,−1), BattlescapeGame.h:95)
СТОРОНЫ:   все; у бота засады не бывает (`_ambushTUs == 0`), поэтому каждый провал атаки или патруля без узла кончается ESCAPE

### think : пересмотр режима из отхода (AIModule.cpp:690-691, 700-704)
УСЛОВИЕ:   `evaluate = (!_spottingEnemies || !_knownEnemies)`; плюс `_spottingEnemies > 2 || health < 2*base/3` -> `evaluate = true`; читерство и не COMBAT -> true (:707-710)
ДАННЫЕ:    СТОРОНА
RNG:       через `evaluateAIMode`
РЕЗУЛЬТАТ: HOSTILE, которого видят и который знает врагов, остаётся в ESCAPE без броска; иначе — новый бросок
СТОРОНЫ:   бот: `_knownEnemies == 0` -> пересмотр на каждом think

### tacticalMode : переход в отход (AIModule.cpp:2941-2996)
УСЛОВИЕ:   только `tactical` (:743-746). `!_spottingEnemies` -> выход; уже `AI_ESCAPE` -> «escaping», выход; укрытия нет, если `_escapeAction.type != BA_WALK || target == pos || getSpottingUnits(target) >= _spottingEnemies` -> «nocover»; `wounded = careful && (getFatalWounds() > 0 || health < base/2)`; AMBUSH и не ранен -> держит; COMBAT с атакой и не ранен: прицельный/автоматический -> снап, если после него хватает ОВ на `_escapeTUs`; бот, у которого после атаки ОВ меньше `_escapeTUs` -> «scoot», ESCAPE; иначе «attack»; всё остальное -> «pullback» / «cover.patrol» / «cover.combat», ESCAPE
ДАННЫЕ:    свежий `_escapeAction` этого think (при видящих tactical-вызов был на :643); `_escapeTUs` — цена пути к укрытию; раны — ЮНИТ
RNG:       нет
РЕЗУЛЬТАТ: `_AIMode = AI_ESCAPE` при наличии строго лучшего укрытия
ПРЕРЫВАНИЕ: режим ESCAPE, выпавший броском, проверку «nocover» не проходит — уходит как есть
СТОРОНЫ:   при V4 только бот (`TACTICS` выключен)

### think : действие отхода (AIModule.cpp:754-766, 866-878)
УСЛОВИЕ:   `case AI_ESCAPE`; затем `action->type == BA_WALK`: `target != pos` -> `_escapeTUs = _ambushTUs = 0`, иначе `BA_NONE` (тэлли «walk.self»)
ДАННЫЕ:    `_escapeAction`
RNG:       нет
РЕЗУЛЬТАТ: `setCharging(0)`; `type`, `target`, `run` из `_escapeAction`; `finalAction = true`; `desperate = true`; `setHiding(true)`; `kneel` не трогается; `updateTU()` не вызывается
СТОРОНЫ:   все

### handleAI : исполнение (BattlescapeGame.cpp:448-452, 459-482, 507-549, 579-608)
УСЛОВИЕ:   `BA_RETHINK` -> второй `think`; нет оружия -> `findItem` (не PLAYER) / `findBotWeapon` (бот, никого не видит) могут заменить действие ходьбой к предмету; `BA_WALK` -> `calculate(actor, target, BAM_NORMAL)` (:521), путь есть -> `UnitWalkBState`; `BA_NONE` -> `carefulGuard` (бот) или следующий юнит
ДАННЫЕ:    ИСТИНА карты
RNG:       нет в этих строках
РЕЗУЛЬТАТ: путь строится заново обычной ходьбой, а оплачивается шагами по `getMoveType()` (бег, UnitWalkBState.cpp:306); пути нет — действия нет, ход юнита не кончается
СТОРОНЫ:   все

### UnitWalkBState : ходьба отхода (UnitWalkBState.cpp:235-255, 276-281, 442-455, 478-534)
УСЛОВИЕ:   `unitSpotted` требует `!_action.desperate` — при отходе новые замеченные не останавливают; огонь на реакцию (`checkReactionFire`) останавливает всегда -> `cancelCurentMove()` (без `postPathProcedures`); конец пути -> `postPathProcedures`
ДАННЫЕ:    —
RNG:       в реакции — см. 30_execution.md
РЕЗУЛЬТАТ: не PLAYER: `finalAction` -> `dontReselect()`; `isHiding()` -> `dir = getDirection() + 4` (разворот на 180 градусов от последнего шага), `setHiding(false)`, `dontReselect()`. PLAYER (бот): этих веток нет; при `!getPanicHandled()` — `clearTimeUnits()`
СТОРОНЫ:   HOSTILE/NEUTRAL — ход кончен и спина к пути; бот — может действовать дальше

## 3. Числа

| что | значение | выражение | файл:строка | на что влияет |
|---|---|---|---|---|
| база систематической попытки | 100 | `BASE_SYSTEMATIC_SUCCESS` | AIModule.cpp:1953, 1989 | |
| база отчаянной попытки | 110 | `BASE_DESPERATE_SUCCESS` | AIModule.cpp:1954, 2014 | любая принятая отчаянная клетка без штрафов > 100 -> выход |
| база попытки −1 (своя клетка) | 0 | `score = 0` | AIModule.cpp:1973 | почти всегда проигрывает |
| своя клетка без видящих | +15 | `currentTilePreference` | AIModule.cpp:1935, 2000 | своя клетка 115 -> выход, если попалась в списке до другой > 100 |
| досрочный выход | > 100 | `FAST_PASS_THRESHOLD` | AIModule.cpp:1955, 2126 | первая принятая клетка с бонусом любого знака расстояния или экспозиции |
| расстояние | +10 за клетку разницы | `±(d − dist)*10`, обе ветки «+» | AIModule.cpp:2034-2041 | ближе и дальше одинаково выгодно |
| экспозиция | −10*(1+s−S) при S <= s; +10*(S−s) при S > s | `EXPOSURE_PENALTY` | AIModule.cpp:1951, 2068-2077 | |
| огонь | −40 | `FIRE_PENALTY` | AIModule.cpp:1952, 2081 | |
| опасная клетка (граната) | −100 | `BASE_SYSTEMATIC_SUCCESS` | AIModule.cpp:2085 | |
| GAP (вне V4) | −60 за врага в 2 клетках | `GAP_PENALTY` | AIModule.cpp:1956, 2088 | 0 при V4 |
| TURRET (вне V4) | −100 за турель | `TURRET_PENALTY` | AIModule.cpp:1957, 2089 | 0 при V4 |
| клетка за картой | −100001 | | AIModule.cpp:2045 | |
| начальное лучшее | −100000 | `bestTileScore` | AIModule.cpp:1943 | порог `BA_RETHINK` (:2155) |
| квадрат поиска | 11x11 (−5..5) | `_tileSearch` | SavedBattleGame.cpp:79-84 | z свой |
| сдвиг вместо своей клетки | −20..20 по x и y | | AIModule.cpp:1995-1996 | квадрат 41x41 |
| отчаянный сдвиг | −10..10 по x, y; −1..1 по z | | AIModule.cpp:2016-2018 | |
| число попыток | до 151: −1, 0..120 (121), 121..149 (29) | `tries < 150` | AIModule.cpp:1936, 1962 | |
| радиус видящих | `distance2d <= 20` | `dist > 20` -> пропуск | AIModule.cpp:2211 | |
| глаза видящего | −2 вокселя | `originVoxel.z -= 2` | AIModule.cpp:2213 | |
| `_escapeTUs` своей клетки | 1 | | AIModule.cpp:2116 | «отход посчитан» |
| лимит поиска пути | 1000 ОВ | умолчание `calculate` | Pathfinding.h:243 | |
| шанс: база | 15 / 12 (ближний бой) / 5 (HOSTILE, ОВ > половины или в атаке) | | AIModule.cpp:2677-2685 | |
| шанс: свой режим | ×1.1 | | AIModule.cpp:2754 | |
| шанс: здоровье | ×1.7 (< 1/3), ×1.4 (< 2/3), ×1.1 (< полного) | | AIModule.cpp:2759-2774 | |
| шанс: агрессия | 0: ×1.4; 2: ×0.7; иначе ×Clamp(0.9 − a/10, 0.1, 2.0) | | AIModule.cpp:2777-2794 | |
| шанс: видящие | `10*e*(S+10)/100`; без видящих `/2` | | AIModule.cpp:2802-2810 | при S = 1 ×1.1 |
| шанс: оборона базы | ×0.75 | | AIModule.cpp:2832-2836 | |
| бросок режима | `generate(1, max(1, сумма))` | | AIModule.cpp:2845 | отрезок отхода — первый |
| `intelligence` солдата | 2 | | BattleUnit.cpp:85 | бот «знает» врага 2 хода после того, как его видели |
| порог веса цели | `getAITargetWeightThreatThreshold()` | | AIModule.cpp:4278 | кто «видящий» |
| ранение для pullback | `getFatalWounds() > 0 || health < base/2` | | AIModule.cpp:2961-2962 | только бот |

## 4. RNG (в порядке выполнения)

| # | вызов | файл:строка | что решает | когда |
|---|---|---|---|---|
| 1 | `RNG::percent(10)` | AIModule.cpp:682 | пересмотр в патруле | до отхода не относится; при AI_PATROL без видящих/видимых/известных (короткое замыкание `||`) |
| — | ниже — один вызов `setupEscape` | | | think :643 и/или evaluateAIMode :2698, :2726 |
| 2 | `RNG::shuffle(randomTileSearch)` = 120 × `generate(0, i)` | AIModule.cpp:1960 | порядок 121 клетки | всегда при вызове `setupEscape` |
| 3 | `RNG::generate(-20,20)`, `RNG::generate(-20,20)` | AIModule.cpp:1995, 1996 | замена своей клетки | только если цикл дошёл до (0,0) до `coverFound` и `unitsSpottingMe > 0` |
| 4 | на каждую отчаянную попытку: `generate(-10,10)`, `generate(-10,10)`, `generate(-1,1)` | AIModule.cpp:2016, 2017, 2018 | случайная клетка | только если за 121 систематическую попытку лучший счёт не превысил 100; до 29 раз (до 87 вызовов) |
| 5 | `RNG::generate(1, sum)` | AIModule.cpp:2845 | выбор режима | при `evaluate`; `sum` зависит от того, найден ли отход, только косвенно (через `_escapeTUs` нет; `escapeOdds` от отхода не зависит) |

Хрупкость (что сдвигает поток):
- Число вызовов `setupEscape` за think: 0, 1 или 2 (think :643 при видящих; evaluateAIMode :2726 у HOSTILE с известными
  врагами и `_escapeTUs == 0`). Любая правка условия `_escapeTUs`/`tactical` меняет, тратится ли 120+ бросков.
- Число бросков внутри вызова зависит от позиции (0,0) в перемешанном списке и от того, когда сработал `coverFound`:
  клетка с бонусом > 100 раньше (0,0) — броски :1995-1996 не тратятся. Любая правка счёта (штраф, бонус, порог 100,
  состав `_reachable`, видящие) меняет момент выхода и, значит, тратятся ли броски (0,0) и отчаянные.
- `ESCAPE_REACH_FIRST` поток не сдвигает: недостижимая клетка отбрасывается в той же попытке, `getSpottingUnits` без RNG.
- Флаги вне V4 GAP/TURRET меняют счёт -> момент `coverFound` -> число бросков.
- `BA_RETHINK` из отхода (второй `think`, полный новый поток) при живом `_reachable` не возникает (см. §2 «итог»).

## 5. Знание

| что | метка | где |
|---|---|---|
| видящие сейчас (`_spottingEnemies`) | СТОРОНА отбора (вес по `turnsSinceSpotted` против `_intelligence`), ИСТИНА позиций и линий огня | AIModule.cpp:534, 2201-2233, 4217-4224 |
| видящие клетку-кандидат | то же, к гипотетическому юниту | AIModule.cpp:2063 |
| линия огня | ИСТИНА геометрии; свет, дым, дальность зрения, направление взгляда — не учитываются | TileEngine.cpp:2196+ |
| цель для члена расстояния | ЮНИТ (`visible`) + СТОРОНА (вес), позиция ИСТИНА | AIModule.cpp:2240-2287 |
| достижимость | ИСТИНА о себе (этот think) | AIModule.cpp:550 |
| путь к клетке | поиск пути своей фракции, ИСТИНА карты | AIModule.cpp:2107 |
| огонь на клетке | ИСТИНА карты | AIModule.cpp:2079 |
| граната на клетке | метка `getDangerous` (ПАМЯТЬ, общая) | AIModule.cpp:2083 |
| GAP / TURRET (вне V4) | СТОРОНА (видимые сейчас / известные турели) | AiProbe.cpp:3576-3596, 3704+ |
| `_escapeTUs`, `_escapeAction` | ПАМЯТЬ: `_escapeTUs` до конца хода или ходьбы; `_escapeAction` — без сброса вообще | AIModule.cpp:162-170, 61, 871 |
| `lastCover` | ИСТИНА о себе, всегда invalid | BattleUnit.cpp:118, 535 |
| шанс отхода | ЮНИТ (ОВ, здоровье, агрессия), СТОРОНА (видящие, известные) | AIModule.cpp:2677-2836 |

## 6. Карточка режима ESCAPE

| пункт | ответ по коду |
|---|---|
| цель | клетка, которую видит (линией огня) меньше известных врагов, чем сейчас, без огня и гранаты; первая «достаточно хорошая» (> 100) |
| кандидаты | своя клетка (попытка −1); 121 клетка квадрата 11x11 на своём z в случайном порядке; затем до 29 случайных клеток в 21x21 и z ±1. Узлы не используются |
| жёсткие отказы | за картой; не в `_reachable` (не дойти с текущими ОВ и энергией обычной ходьбой); нет пути типом попытки (бег на нечётных) |
| оценка | база (0 / 100 / 110, +15 своей без видящих) + 10 за каждую клетку изменения расстояния до цели (в любую сторону) ± экспозиция |
| штрафы | экспозиция −10 и более, огонь −40, граната −100; GAP −60 и TURRET −100 только вне V4; цена пути в счёт не входит |
| видимость | линия огня от известных врагов в 20 клетках (по истинным позициям) к гипотетическому юниту; свет, дым, дальность, взгляд — нет |
| RNG | порядок клеток (shuffle, всегда), замена своей клетки при видящих (2 броска), отчаянные клетки (3 броска на попытку) |
| первая или лучшая | лучшая до первого счёта > 100, затем выход; при равенстве — раньше в порядке обхода; отчаянная клетка без штрафов почти всегда сразу > 100 |
| ОВ | клетка из `_reachable` (все ОВ, обычная ходьба); `_escapeTUs` = ОВ пути бегом/шагом; в `handleAI` путь строится заново обычной ходьбой, оплачивается бегом при `run`; резерва на огонь нет; после ходьбы `finalAction` (не бот) |
| энергия | только через `_reachable`; цена бега по энергии не проверяется |
| угроза ближнего боя врага | не учитывается при V4 (GAP — вне V4, только бот); член расстояния даже награждает подход к цели |
| другие враги | только через счёт видящих в 20 клетках; их пути, ОВ и ближний бой — нет |
| пропал путь | `handleAI` пересчитывает путь (`BAM_NORMAL`); нет — действия нет, юнит не завершает ход; на ходу огонь на реакцию обрывает ходьбу без разворота и `finalAction` |
| запасные ветки | `BA_RETHINK` (недостижимо); итог на свою клетку -> `BA_NONE` (стоять, следующий юнит); ESCAPE как конец запасной цепочки — со старым `_escapeAction` |

## 7. Отход у бота (CAREFUL)

### Источники отхода в записях

| источник | условие | что видно в записи | `_escapeAction` |
|---|---|---|---|
| tacticalMode «cover.patrol» | видят, режим PATROL, есть строго лучшее укрытие | тэлли `p.cover.patrol`, слот `e` | свежий (этот think) |
| tacticalMode «cover.combat» | видят, COMBAT без атаки (`BA_RETHINK`/`BA_NONE`), есть укрытие | `p.cover.combat`, слот `e` | свежий |
| tacticalMode «pullback» | видят, ранен (смертельная рана или здоровье < 1/2), есть укрытие; кроме уже ESCAPE | `p.pullback`, слот `e` | свежий |
| tacticalMode «scoot» | видят, атака, после неё ОВ меньше `_escapeTUs` | `p.scoot`, слот `e`; атака не выполняется | свежий |
| бросок режима | `decision <= escapeOdds` (видят: ×(S+10)/10; не видят: база/2) | `modeOdds` с `"mode":3`, тэлли `p.escaping`, если видят | при видящих свежий; без видящих — СТАРЫЙ |
| запасная цепочка | COMBAT без атаки -> PATROL без узла -> AMBUSH без засады -> ESCAPE | `modeOdds` с `"mode"` 0 или 2, слот `e`, отдельной тэлли нет | при видящих свежий; без видящих — СТАРЫЙ |
| (вне V4) `AiProbe::flee` | `OXCE_AI_FLEE` | слот `b` «flee» | свой выбор, не `setupEscape` |

`modeOdds` пишет режим броска до запасной цепочки (AiProbe.cpp:2386-2395, вызов AIModule.cpp:2875); итоговый режим —
слот `chosen` (`"paxe"[_AIMode]`, AIModule.cpp:836-839; `e` = AI_ESCAPE = 3, AIModule.h:37). `_evalChosen` переводит
в COMBAT до `tacticalMode` (:738-741), поэтому «scoot» возможен и после выбора оценщика.

### Что меняет careful

| место | без careful (AI) | с careful (бот) | строка |
|---|---|---|---|
| враги для подсчёта | цели — PLAYER | `setTargetFaction(HOSTILE)` | BattlescapeGame.cpp:425-430 |
| частота `setupEscape` | раз в ход (пока `_escapeTUs == 0`) | на каждом think при видящих | AIModule.cpp:638-639 |
| `tacticalMode` | нет (TACTICS выключен) | да: укрытие при PATROL/COMBAT без атаки, ранение, «scoot», снап вместо прицельного | :743-746, 2941-2996 |
| бег | броня должна явно разрешать | разрешён юнитам 1x1, если броня не запрещает | :1966 |
| GAP/TURRET | 0 | 0 при V4 (нужны `OXCE_AI_GAP` / `OXCE_AI_TURRET`) | AiProbe.cpp:3578-3582, 3706-3710 |
| `finalAction` / разворот 180 | ход кончен, спина к пути | нет: ветки только для не-PLAYER, бот может действовать снова (до `maxActions` = 2 при V4) | UnitWalkBState.cpp:482-509; AiProbe.cpp:3826-3832 |
| поворот в конце | разворот +4 | `carefulGuard`: в конце выбора юнита поворот к ближайшему видимому врагу, если хватает ОВ | BattlescapeGame.cpp:307-360, 377-382, 581-584 |
| пересмотр режима | ESCAPE держится, пока видят и знают врагов | `_knownEnemies == 0` -> пересмотр на каждом think | AIModule.cpp:690-691 |
| `escapeOdds` | 0 у HOSTILE без известных | не обнуляется, без видящих — база/2 | :2735-2739, 2809 |
| колени | не трогаются | не трогаются (`kneel` в ветке ESCAPE не задаётся) | :754-766 |

## 8. Слепые пятна (доказано кодом)

1. Член расстояния награждает подход к врагу: обе ветки :2034-2041 дают `+10*|Δ|`. Клетка на 3 ближе к цели стоит
   столько же, сколько клетка на 3 дальше; при сдвиге до 5 клеток это до +50 — больше штрафа за одного лишнего видящего.
2. «Достаточно хорошая» клетка (> 100) не обязана быть лучше текущей по видимости: при S видящих клетка с теми же S
   видящими получает 100 − 10 + 10*|Δ|, и уже при |Δ| >= 2 прекращает поиск (AIModule.cpp:2068-2077, 2126). С ростом
   расстояния на 2 клетки принимается и клетка, которую видит S+1 врагов (100 − 20 + 20 = 100 — нет; при |Δ| = 3 — да).
3. Отчаянная клетка без штрафов принимается сразу: база 110 > 100 (AIModule.cpp:2014, 2126), даже если её видят столько
   же врагов (110 − 10 = 100 — нет; с любым |Δ| >= 1 — да).
4. Ветка `lastCover` мёртвая (BattleUnit.cpp:118, 535 — единственные записи, обе invalid).
5. Ветка «Escape estimation failed» / `BA_RETHINK` недостижима: своя клетка всегда в `_reachable` и принимается без пути.
6. Видящие считаются по ИСТИННЫМ позициям врагов, которых сторона знает до `_intelligence` ходов назад (у солдата 2),
   и линией огня без света, дыма, дальности зрения и направления взгляда (AIModule.cpp:2201-2233). У бота это знание
   больше, чем у игрока: враг, ушедший из виду на прошлом ходу, учитывается в своём настоящем месте.
7. Попытка с недостижимой клеткой тратит одну из 151 попыток (`tries++` до проверки, :2029); в тесном месте большая
   часть 121 систематической попытки уходит на недостижимые клетки.
8. Путь проверки (бегом на нечётных попытках, :2107) и путь исполнения (`BAM_NORMAL`, BattlescapeGame.cpp:521) разные;
   `_escapeTUs` — цена первого. На нём же решается «scoot» и снап в `tacticalMode`.
9. `_escapeTUs` не сбрасывается после выстрела или другого действия без ходьбы (сброс только `reset()` и :871): у
   HOSTILE отход второго действия этого хода берётся из расчёта до выстрела, с прежними ОВ.
10. Бот, у которого выпал ESCAPE броском или запасной цепочкой без видящих, исполняет `_escapeAction` прошлого вызова —
    возможно прошлого хода и с другой позиции (`_escapeAction` нигде не сбрасывается). Путь к старой цели строится
    заново и идёт, пока хватает ОВ.
11. Отход из броска режима не проверяет, есть ли укрытие: `tacticalMode` при `AI_ESCAPE` выходит до проверки «nocover»
    (AIModule.cpp:2948-2951); итог может быть своей клеткой (-> `BA_NONE`) или клеткой без выигрыша по видимости.
12. Огонь на реакцию обрывает ходьбу через `cancelCurentMove` без `postPathProcedures` (UnitWalkBState.cpp:247-255):
    у HOSTILE пропадают `dontReselect` и разворот, юнит может быть выбран снова и подумать ещё раз в этом выборе.
13. Разворот на 180 — от направления последнего шага, а не от врага (UnitWalkBState.cpp:504-506).
14. `selectClosestKnownEnemy()` перед вызовом из `evaluateAIMode` бесполезен: `setupEscape` тут же затирает
    `_aggroTarget` через `selectNearestTarget` (:1938, :2244) — член расстояния считается от видимой цели или не считается.
15. У ближнего бойца вызов `setupEscape` из `evaluateAIMode` (после `setupAttack`) переписывает `_attackAction.target`
    через `selectPointNearTarget` (:2430).
16. Цена пути в счёт не входит: из двух клеток с одним счётом берётся первая в случайном порядке, даже если до неё вдвое
    дальше.
17. Угроза ближнего боя врага при V4 не учитывается ни в счёте, ни в видимости (GAP только вне V4).

## 9. Не прослежено

- Что делает `selectNextPlayerUnit(true, _AISecondMove)` после `BA_NONE` (BattlescapeGame.cpp:587): вернётся ли юнит,
  оставшийся стоять после «отхода на свою клетку», во втором проходе.
- Совпадает ли точка `selectPointNearTarget`, записанная из `setupEscape`, с выбором `setupAttack` (входы те же, но
  промежуточные вызовы между ними не сверялись).
- Функции, которые вызывает `canTargetUnit` (`calculateLineVoxel` и т. п.), на RNG целиком не проверены; в теле
  `canTargetUnit` вызовов RNG нет.
- Хватает ли ОВ и энергии на путь бегом, найденный `calculate` с лимитом 1000 (`_reachable` считан для обычной ходьбы);
  поведение при нехватке на ходу — см. 30_execution.md (остановка UnitWalkBState по ОВ/энергии, :306-341).
- Состав «известных» целей при `isSniper` (ветка снайпера в `getTargetAttackWeight`, :4218) для подсчёта видящих.
- `AiProbe::flee` и `revive` (вне V4) по существу не разбирались.
