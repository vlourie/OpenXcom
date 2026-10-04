# 13. Бой: ближний бой, Leeroy, граната и взрывчатка, пси, путевые точки (AIModule.cpp)

Область: `src/Battlescape/AIModule.cpp` — `selectMeleeOrRanged`, `meleeAction`, `meleeAttack`, `selectPointNearTarget`,
`getTargetAttackWeight`, `validTarget`, `selectNearestTarget`, Leeroy (`dont_think`, `selectNearestTargetLeeroy`,
`selectPointNearTargetLeeroy`, `meleeActionLeeroy`), `grenadeAction`, `explosiveEfficacy`, `getNodeOfBestEfficacy`,
`psiAction`, `wayPointAction`, а также `TileEngine::validMeleeRange` и `TileEngine::psiAttackCalculate`, если они
вызываются отсюда. Номера строк сверены с текущим деревом (ветка hd-render, после f14085833).

Кто чем играет: **враг** — FACTION_HOSTILE, родной AIModule без TACTICS. **Бот** — FACTION_PLAYER, AIModule
+ OXCE_AI_BOT + OXCE_AI_CAREFUL. `AiProbe::careful(unit)` (src/Battlescape/AiProbe.cpp:367) — истина только у бота.

Вызовы AiProbe внутри области: только зонды `probeMark/probeSlot`, `AiProbe::chosen`, трасса `OXCE_AI_TRACE_MELEE`
(AIModule.cpp:2410-2427, только запись в лог). `AiProbe::closeEnemies`, `AiProbe::turretsSeeing`,
`AiProbe::knownOccupantV2` в функциях области **не вызываются**: closeEnemies и turretsSeeing зовёт только setupEscape
(AIModule.cpp:2088-2089, 2139-2147), knownOccupantV2 — только findFirePoint (AIModule.cpp:3009). Ни один флаг V4
ветку в функциях области не меняет; влияние V4 только косвенное, через `_reachable` (findReachable) и пути `calculate`
(BLOCKED_STEP — запрет первого шага в Pathfinding.cpp:257, WALKFOV_SKIP/LIGHTSKIP/FAST — вне этой карточки, см. 31).

---

## 1. Схема вызовов

```
AIModule::think()
  ├── :526  _attackAction.diff = getDifficultyCoefficient()           (0..4)
  ├── :532  _knownEnemies = countKnownTargets()                      (только HOSTILE, :2183; у бота 0)
  ├── :533  _visibleEnemies = selectNearestTarget()                  (! до :535-537 и до :550 — старые _melee/_rifle/_reachable)
  ├── :535  _melee = getUtilityWeapon(BT_MELEE) != 0;  :536 _rifle=false;  :537 _blaster=false
  ├── :550  _reachable = findReachable(_unit, BattleActionCost())    (все ОВ)
  ├── :551-560 revive / flee (только careful; вне V4 REVIVE)
  ├── :598  isLeeroyJenkins() ──► dont_think(action) ──► return
  │           ├── :245 canRun
  │           ├── :246 selectNearestTargetLeeroy(canRun)  ──► selectPointNearTargetLeeroy (:2452)
  │           ├── :251 >0 && _melee ──► meleeActionLeeroy(canRun) (:3338) ──► meleeAttack (:4190)
  │           └── :267 иначе setupPatrol, setCharging(0), endPatrolIfSpent
  ├── :605-633 оружие в руке: BT_FIREARM с waypoints → _blaster; иначе _rifle; BT_MELEE → _melee
  ├── :635  _grenade = getGrenadeFromBelt(_save) != 0
  ├── :640  setupEscape (при _spottingEnemies)
  ├── :647  setupAmbush — только если !_melee (у бота с кулаком брони _melee почти всегда true)
  ├── :654  setupAttack()
  │     ├── :1813 _attackAction.type = BA_RETHINK; _psiAction.type = BA_NONE
  │     ├── :1820 if (_knownEnemies)                                   (у бота и нейтрала — никогда)
  │     │     ├── :1823 psiAction()  ── true ──► return               (RNG; TileEngine::psiAttackCalculate)
  │     │     ├── :1830 _blaster ──► wayPointAction() (:3385)         (explosiveEfficacy, без RNG)
  │     │     └── :1839 else RNG::percent(sniperPercentage) ──► sniperAction (карточка 12)
  │     ├── :1849 evalFire (вне V4, OXCE_AI_EVAL)
  │     ├── :1862 !sniperAttack && selectNearestTarget()
  │     │     ├── :1865 _melee && _rifle ──► selectMeleeOrRanged() (:4295)   (RNG)
  │     │     ├── :1869 _grenade ──► grenadeAction() (:3912)
  │     │     │        ├── explosiveEfficacy(цель, grenade=true) (:3173)
  │     │     │        └── иначе getNodeOfBestEfficacy (:4354)
  │     │     ├── :1875 _melee ──► meleeAction() (:3284)
  │     │     │        ├── validMeleeRange с места ──► meleeAttack (:4190)
  │     │     │        └── цикл по юнитам ──► selectPointNearTarget (:2385) ──► setCharging, BA_WALK
  │     │     └── :1881 _rifle ──► projectileAction (карточка 12)
  │     ├── :1889 type != BA_RETHINK ──► return
  │     └── :1904 _spottingEnemies || aggression < RNG::generate(0,3) ──► findFirePoint (карточка 12)
  ├── :661  psi выполняется: _psiAction.type != BA_NONE && !_didPsi && turn >= AIUseDelay ──► return
  ├── :714  evaluateAIMode (charging → COMBAT, :2671 и :2871)
  ├── :743  tacticalMode (бот: scoot/pullback могут отменить BA_HIT и BA_THROW)
  └── :790  AI_COMBAT: action = _attackAction; BA_THROW гранаты — сразу spendCost(prime) и spendTimeUnits(4) (:795-799)
```

Порядок в setupAttack важен: каждая следующая функция **перезаписывает** `_attackAction.type`. wayPointAction
(BA_LAUNCH) может быть перекрыт гранатой (BA_THROW) или ближним боем (BA_HIT/BA_WALK); граната обнуляет `_melee` и
`_rifle` (:3970-3971), поэтому после неё meleeAction и projectileAction не вызываются; выбор ближнего боя в
selectMeleeOrRanged обнуляет `_rifle` (:4340), выбор дальнего — `_melee` (:4346).

---

## 2. Развилки

### think : selectNearestTarget до обновления флагов (AIModule.cpp:533)
УСЛОВИЕ:   вызов `_visibleEnemies = selectNearestTarget();` стоит раньше `_melee = (_unit->getUtilityWeapon(BT_MELEE) != 0); _rifle = false;` (:535-536) и раньше `_reachable = ...findReachable(...)` (:550)
ДАННЫЕ:    `_melee`, `_rifle` — ПАМЯТЬ (с прошлого think; в новом AIModule оба false, AIModule.cpp:54-55); `_reachable` — ПАМЯТЬ (с прошлого think, от прошлой позиции юнита; у нового модуля пуст)
RNG:       нет
РЕЗУЛЬТАТ: `_visibleEnemies` и `_aggroTarget` считаются по устаревшей ветке выбора (LOS или клетка подхода); `_attackAction.target` может быть переписан selectPointNearTarget
ВОЗВРАТ:   think, :534
СТОРОНЫ:   оба

### selectNearestTarget : фильтр и ветка проверки (AIModule.cpp:2248-2276)
УСЛОВИЕ:   `validTarget(bu, true, true) && _save->getTileEngine()->visible(_unit, bu->getTile())`; затем `dist < _closestDist` (стартовое 100, :2243); затем `if (_rifle || !_melee)` — canTargetUnit из `getOriginVoxel` (:2256-2263); иначе `selectPointNearTarget(bu, _unit->getTimeUnits())` и `validMeleeRange(_attackAction.target, dir, _unit, bu, 0)` (:2267-2270)
ДАННЫЕ:    позиция цели — ИСТИНА; знание о цели — СТОРОНА (через validTarget → getTargetAttackWeight, :4217); видимость — пересчёт LOS `TileEngine::visible` (TileEngine.cpp:1864), конус обзора не проверяется (ЮНИТ по смыслу, считается заново)
RNG:       нет
РЕЗУЛЬТАТ: `_aggroTarget` = ближайшая по `distance2d` (потолок от евклида, без z, Position.h:118-120) видимая валидная цель, по которой проходит проверка; `tally` — число видимых валидных (до проверки)
ВОЗВРАТ:   `tally`, только если `_aggroTarget` найден, иначе 0 (:2281-2286)
СТОРОНЫ:   оба

### validTarget (AIModule.cpp:4259-4280)
УСЛОВИЕ:   `target->isOut() || (assessDanger && target->getTile()->getDangerous()) || (target->getFaction() != FACTION_PLAYER && target->isIgnoredByAI())` → false; затем `includeCivs ? getTargetAttackWeight(target) > AIW_IGNORED : getTargetAttackWeight(target) > getAITargetWeightThreatThreshold()`
ДАННЫЕ:    isOut — ИСТИНА; dangerous клетки — ИСТИНА (общий флаг клетки, ставит setDangerZone от гранаты не игрока, ProjectileFlyBState.cpp:728-730, и BattlescapeGame для недостижимых предметов :552, :2848, :3152); вес — СТОРОНА + РУЛСЕТ
RNG:       нет
РЕЗУЛЬТАТ: фильтр цели; вес не ранжирует
СТОРОНЫ:   оба

### getTargetAttackWeight (AIModule.cpp:4207-4250)
УСЛОВИЕ:   (1) `target->getFaction() == _unit->getFaction()` → AsFriendly; (2) иначе `_intelligence < target->getTurnsSinceSpottedByFaction(_unit->getFaction()) && (!_unit->isSniper() || !target->getTurnsLeftSpottedForSnipersByFaction(...))` → AIW_IGNORED; (3) иначе `target->getFaction() == FACTION_HOSTILE || _unit->getFaction() == FACTION_HOSTILE`: `target->getFaction() == _targetFaction` → AsHostile, иначе AsHostileCivilians; (4) иначе один из них NEUTRAL → AsNeutral; затем скрипт `AiCalculateTargetWeight` брони (:4239-4243)
ДАННЫЕ:    фракции — ИСТИНА; turnsSinceSpotted — СТОРОНА; _intelligence — РУЛСЕТ юнита (солдат: 2, BattleUnit.cpp:85); веса — РУЛСЕТ (Mod.h:247-251, броня может переопределить)
RNG:       нет (скрипт по умолчанию без random)
РЕЗУЛЬТАТ: вес. Для бота `_targetFaction = FACTION_HOSTILE` (BattlescapeGame.cpp:429): враг 100, свои −200, нейтралы −100 (нейтралы для бота не цель). Для врага: игрок 100, мирные 50
СТОРОНЫ:   оба; у бота ветка (3) срабатывает за счёт `target == HOSTILE`

### selectMeleeOrRanged : отказ без боеприпасов (AIModule.cpp:4300-4310)
УСЛОВИЕ:   `!melee || !melee->haveAnyAmmo()` → `_melee = false`, return; `!range || !range->haveAnyAmmo()` → `_rifle = false`, return
ДАННЫЕ:    оружие и патроны — ЮНИТ/РУЛСЕТ
RNG:       нет
ВОЗВРАТ:   setupAttack :1869
СТОРОНЫ:   оба

### selectMeleeOrRanged : бросок ближнего боя (AIModule.cpp:4314-4346)
УСЛОВИЕ:   `meleeOdds = 10`; `dmg = _aggroTarget->reduceByResistance(powerBonus(BA_HIT), ResistType)`; `dmg > 50` → `+= (dmg - 50) / 2`; `_visibleEnemies > 1` → `-= 20 * (_visibleEnemies - 1)`; `if (meleeOdds > 0 && _unit->getHealth() >= 2 * base.health / 3)`: агрессия 0 → −20, агрессия >1 → +10×агрессия; `RNG::percent(meleeOdds)`
ДАННЫЕ:    сопротивление цели — ИСТИНА (броня цели); `_visibleEnemies` — ЮНИТ, но по устаревшей ветке (:533); здоровье, агрессия — ЮНИТ/РУЛСЕТ
RNG:       RNG HERE: `RNG::percent(meleeOdds)` AIModule.cpp:4338 — решает ближний или дальний; вызывается только если `meleeOdds > 0` и здоровье ≥ 2/3 (после поправки на агрессию бросок тратится даже при meleeOdds ≤ 0: percent всегда зовёт generate, RNG.h:52-55)
РЕЗУЛЬТАТ: успех → `_rifle = false; _attackAction.weapon = melee; reachableWithAttack(BA_HIT)`; провал или нет условия → `_melee = false`
ВОЗВРАТ:   setupAttack :1869
СТОРОНЫ:   оба. Бот: агрессия 1 (BattleUnit.cpp:86) → поправки нет; шанс 10 % при одном видимом враге и dmg ≤ 50, 0 при двух и больше (тогда условие `meleeOdds > 0` ложно и броска нет)

### meleeAction : нет ОВ на удар (AIModule.cpp:3286-3291)
УСЛОВИЕ:   `!attackCost.haveTU()` для `BattleActionCost(BA_HIT, _unit, getUtilityWeapon(BT_MELEE))`
ДАННЫЕ:    ОВ, энергия — ЮНИТ; стоимость — РУЛСЕТ (STR_UNARMED_BASIC: costMelee time 8, energy 2)
RNG:       нет
ВОЗВРАТ:   return; `_attackAction.type` остаётся прежним (RETHINK или перекрытое ранее)
СТОРОНЫ:   оба

### meleeAction : удар с места (AIModule.cpp:3292-3299)
УСЛОВИЕ:   `_aggroTarget != 0 && !_aggroTarget->isOut()` и `validMeleeRange(_unit, _aggroTarget, getDirectionTo(...))`
ДАННЫЕ:    `_aggroTarget` от selectNearestTarget (ближайшая видимая) — ЮНИТ/СТОРОНА; позиции — ИСТИНА; geometry validMeleeRange (TileEngine.cpp:5368, :5382) — ИСТИНА
RNG:       нет
РЕЗУЛЬТАТ: meleeAttack → BA_HIT в позицию цели
ВОЗВРАТ:   return
СТОРОНЫ:   оба

### meleeAction : выбор жертвы для рывка (AIModule.cpp:3300-3319)
УСЛОВИЕ:   `chargeReserve = std::min(TU - attackCost.Time, 2 * (energy - attackCost.Energy))`; `distance = chargeReserve / 4 + 1`; `_aggroTarget = 0`; по всем юнитам: пропуск `newDistance > 20 || !validTarget(bu, true, true)`; `(newDistance < distance || newDistance == 1) && !bu->isOut()` и `(newDistance == 1 || selectPointNearTarget(bu, chargeReserve))`
ДАННЫЕ:    список юнитов, позиции — ИСТИНА; знание — СТОРОНА (видимость не требуется!); ОВ, энергия — ЮНИТ
RNG:       нет
РЕЗУЛЬТАТ: `_aggroTarget = bu; _attackAction.type = BA_WALK; _unit->setCharging(_aggroTarget); distance = newDistance`. Ближайшая побеждает строго (`<`), а соседняя по `distance2d == 1` принимается всегда, то есть последняя такая в списке юнитов
ПРЕРЫВАНИЕ: нет; цикл идёт до конца списка
ВОЗВРАТ:   :3322
СТОРОНЫ:   оба

### meleeAction : удар после выбора (AIModule.cpp:3322-3328)
УСЛОВИЕ:   `_aggroTarget != 0` и `validMeleeRange(_unit, _aggroTarget, dir)`
RNG:       нет
РЕЗУЛЬТАТ: meleeAttack (BA_HIT); иначе остаётся BA_WALK к `_attackAction.target`
СТОРОНЫ:   оба

### selectPointNearTarget : клетки подхода (AIModule.cpp:2385-2441)
УСЛОВИЕ:   клетки `target->getPosition() + (x, y, z)`, z ∈ [−1, 1], x, y ∈ [−size, sizeTarget], без `x == 0 && y == 0`; пропуск, если клетки нет или её индекса нет в `_reachable` (:2403); `valid = validMeleeRange(checkPath, dir, _unit, target, 0)`; `fitHere = setUnitPosition(_unit, checkPath, true)`; `valid && fitHere && !getTile(checkPath)->getDangerous()` (:2417); `calculate(_unit, checkPath, BAM_NORMAL, 0, maxTUs)`; `distanceCurrent = path.size() - dodgeChanceDiff * getArcDirection(dir - 4, dirTarget)` (:2422); принять при `getStartDirection() != -1 && distanceCurrent < distance` (:2428)
ДАННЫЕ:    `_reachable` — ПАМЯТЬ этого think (или прошлого — при вызове из :533); занятость `setUnitPosition` — ИСТИНА (SavedBattleGame.cpp:2632-2676: настоящие юниты, в том числе невидимые); dangerous — ИСТИНА; направление цели — ИСТИНА; meleeDodge и meleeDodgeBackPenalty брони цели — РУЛСЕТ
RNG:       нет
РЕЗУЛЬТАТ: `_attackAction.target = checkPath` для клетки с наименьшим `distanceCurrent`; при равенстве — первая в порядке z, x, y
ВОЗВРАТ:   true, если найдена
СТОРОНЫ:   оба; зонд OXCE_AI_TRACE_MELEE — только лог

### meleeAttack : поворот (AIModule.cpp:4190-4199)
УСЛОВИЕ:   безусловно: `_unit->lookAt(...)`; `while (_unit->getStatus() == STATUS_TURNING) _unit->turn();`
ДАННЫЕ:    позиция цели — ИСТИНА
RNG:       нет
РЕЗУЛЬТАТ: юнит разворачивается к цели прямо во время think (turn() ОВ не списывает); `_attackAction.target = _aggroTarget->getPosition(); type = BA_HIT; weapon = getUtilityWeapon(BT_MELEE)`
ПРЕРЫВАНИЕ: поворот остаётся, даже если атаку потом отменит tacticalMode или evaluateAIMode выберет другой режим
СТОРОНЫ:   оба

### dont_think : вход Leeroy (AIModule.cpp:598-603, 221-284)
УСЛОВИЕ:   `_unit->isLeeroyJenkins()`; в dont_think: `_melee = false; action->weapon = getUtilityWeapon(BT_MELEE)`; `_melee = true`, если `BT_MELEE && canUseWeapon(..., BA_HIT)` (:230-243); `canRun = _melee && allowsRunning(false) && energy > stamina * 0.4f` (:245)
ДАННЫЕ:    isLeeroyJenkins — РУЛСЕТ (Unit.cpp:107 поле `isLeeroyJenkins`, BattleUnit.cpp:502); энергия — ЮНИТ
RNG:       нет (в своей части; setupPatrol — RNG, карточка 14)
РЕЗУЛЬТАТ: `selectNearestTargetLeeroy(canRun) > 0 && _melee` → meleeActionLeeroy, копирование type/run/target/finalFacing, updateTU (:251-266); иначе setupPatrol, `setCharging(0)`, `_reserve = BA_NONE`, endPatrolIfSpent(action, false) (:267-283)
ВОЗВРАТ:   return из think — setupAttack, evaluateAIMode, tacticalMode, граната, огнестрел не выполняются
СТОРОНЫ:   только юниты с флагом рулсета; солдат — никогда (`_isLeeroyJenkins(false)`, BattleUnit.cpp:76)

### selectPointNearTargetLeeroy (AIModule.cpp:2452-2489)
УСЛОВИЕ:   те же клетки, без проверки `_reachable`, без dangerous, без уклонения; `valid && fitHere` → `calculate(_unit, checkPath, canRun ? BAM_RUN : BAM_NORMAL, 0, 100000)`; принять при `getStartDirection() != -1 && path.size() < distance`
ДАННЫЕ:    как у обычной, кроме `_reachable` и dangerous
RNG:       нет
РЕЗУЛЬТАТ: ближайшая по числу шагов клетка; ОВ не ограничены
СТОРОНЫ:   Leeroy

### meleeActionLeeroy (AIModule.cpp:3338-3378)
УСЛОВИЕ:   удар с места, как у обычной; затем `distance = 1000`, без отсечки 20 и без проверки ОВ; `validTarget(bu, true, true)`; `(newDistance < distance || newDistance == 1) && !bu->isOut()` и `(newDistance == 1 || selectPointNearTargetLeeroy(bu, canRun))`
ДАННЫЕ:    позиции — ИСТИНА; знание — СТОРОНА (видимость не требуется)
RNG:       нет
РЕЗУЛЬТАТ: BA_WALK, `_attackAction.run = canRun`, setCharging; при validMeleeRange — meleeAttack
СТОРОНЫ:   Leeroy

### grenadeAction : хватает ли ОВ (AIModule.cpp:3915-3925)
УСЛОВИЕ:   `BattleAction action{weapon = getGrenadeFromBelt, type = BA_THROW}`; `updateTU(); action.Time += 4; action += getActionTUs(BA_PRIME, grenade)`; `if (action.haveTU())`
ДАННЫЕ:    граната — ЮНИТ (любой предмет isGrenadeOrProxy, у которого `turn >= getAIUseDelay`, BattleUnit.cpp:3795; руки тоже); ОВ — ЮНИТ; стоимость — РУЛСЕТ
RNG:       нет
РЕЗУЛЬТАТ: нет ОВ → функция ничего не меняет
СТОРОНЫ:   оба

### grenadeAction : куда бросать (AIModule.cpp:3927-3939)
УСЛОВИЕ:   `explosiveEfficacy(_aggroTarget->getPosition(), _unit, radius, _attackAction.diff, true)` → цель — клетка `_aggroTarget`; иначе `!getNodeOfBestEfficacy(&action, radius)` → return; иначе узел (`_probeSource = "grenade.node"`, зонд)
ДАННЫЕ:    см. explosiveEfficacy и getNodeOfBestEfficacy
RNG:       нет
СТОРОНЫ:   оба; у бота узел не находится никогда (см. getNodeOfBestEfficacy)

### grenadeAction : сдвиг и проверка броска (AIModule.cpp:3940-3974)
УСЛОВИЕ:   `getBattleType() == BT_PROXIMITYGRENADE` → 4 соседние клетки (±x, ±y, в пределах карты), отсортированные по `distance3dToPositionSq` до бросающего (`std::sort`, неустойчивый; `RNG::shuffle` закомментирован, :3948); иначе сдвиг (0,0,0); для каждой `validateThrow(action, originVoxel, targetVoxel, getDepth())` (TileEngine.cpp:5700, без RNG)
ДАННЫЕ:    геометрия — ИСТИНА
RNG:       нет
РЕЗУЛЬТАТ: первая годная клетка: `weapon = grenade; target = targetTile; type = BA_THROW; _rifle = false; _melee = false`; break
ПРЕРЫВАНИЕ: ни одна не прошла — ничего не меняется
СТОРОНЫ:   оба

### explosiveEfficacy (AIModule.cpp:3173-3278)
УСЛОВИЕ:   `grenade && targetPos.z > 0 && targetTile->hasNoFloor(_save)` → 0; `desperation = (100 - morale) / 10`, `+3` при `injurylevel > (health / 3) * 2`; `efficacy = AIW_SCALE * desperation`; `abs(dz) <= Options::battleExplosionHeight && distance <= radius` → `-= AIW_SCALE * 4`; `+= AIW_SCALE * diff/2`; юнит на целевой клетке при `!targetTile->getDangerous()` → `++enemiesAffected; += getTargetAttackWeight(target)` (:3208-3212); прочие юниты: `!isOut && bu != attackingUnit && bu != target && abs(dz) <= battleExplosionHeight && distance2d <= radius`, пропуск при dangerous клетке и при `weight == 0`; `calculateLineVoxel(центр цели → центр юнита)` даёт `V_UNIT` в клетке юнита → `bu->getFaction() == _targetFaction` ? `++enemiesAffected`; `efficacy += weight` (:3244-3254); `grenade && desperation < 6 && enemiesAffected < 2` → 0 (:3259); `enemiesAffected >= 10` → вернуть enemiesAffected; `efficacy > 0` → `efficacy / AIW_SCALE`; иначе 0
ДАННЫЕ:    мораль, здоровье бросающего — ЮНИТ; юниты в радиусе, их позиции — ИСТИНА; вес (известен ли) — СТОРОНА; линия до юнита — ИСТИНА; battleExplosionHeight — опция (код 0, Options.cpp:262; установка 2); радиус — РУЛСЕТ
RNG:       нет
РЕЗУЛЬТАТ: оценка «стоит ли взрыв»; юнит на целевой клетке считается в enemiesAffected независимо от фракции
СТОРОНЫ:   оба

### getNodeOfBestEfficacy (AIModule.cpp:4354-4401)
УСЛОВИЕ:   `bestScore = 2`; узлы `!isDummy()`, `dist <= 20 && dist > radius` и `canTargetTile(getSightOriginVoxel(_unit), узел, O_FLOOR)`; юниты `!bu->isOut() && dist < radius` (distance2d, z не учитывается) и `canTargetTile` из точки обзора юнита; `(_unit HOSTILE && bu не HOSTILE) || (_unit NEUTRAL && bu HOSTILE)` → `+1` при `getTurnsSinceSpottedByFaction <= _intelligence`; иначе `-= 2`; принять `nodePoints > bestScore`
ДАННЫЕ:    узлы карты — РУЛСЕТ/карта; позиции юнитов — ИСТИНА; знание — СТОРОНА (только для +1; −2 за своих и за неизвестных противников не ставится — см. ниже); линии — ИСТИНА
RNG:       нет
РЕЗУЛЬТАТ: `action->target = позиция узла` с наибольшим счётом; вернуть `bestScore > 2` (нужно минимум 3 очка)
СТОРОНЫ:   враг и нейтрал. У бота (PLAYER) ни одна ветка +1 не срабатывает, каждый юнит даёт −2 → узел не находится никогда

### psiAction : вход (AIModule.cpp:3986-4021)
УСЛОВИЕ:   `item = getUtilityWeapon(BT_PSIAMP)`, нет → false; для BA_USE, BA_PANIC, BA_MINDCONTROL с `cost.Time > 0`: `Time += _escapeTUs; Energy += _escapeTUs / 2; have |= haveTU()`; `_aggroTarget = 0`; `getOriginalFaction() == getFaction() && have && !_didPsi`
ДАННЫЕ:    пси-предмет — ЮНИТ/РУЛСЕТ; `_escapeTUs` — ПАМЯТЬ (от setupEscape этого или прошлого think); `_didPsi` — ПАМЯТЬ
RNG:       нет
РЕЗУЛЬТАТ: условие ложно → false
СТОРОНЫ:   только враг: вызывается из setupAttack при `_knownEnemies` (у бота и нейтрала 0)

### psiAction : кандидаты и оценка (AIModule.cpp:4026-4129)
УСЛОВИЕ:   `bu->getArmor()->getSize() == 1 && validTarget(bu, true, false) && bu->getOriginalFaction() != _unit->getFaction() && (!LOSRequired || bu ∈ _unit->getVisibleUnits())`; пропуск `isOutOfRange(distance3dToUnitSq)`; по типам с `haveTU()`: `w = psiAttackCalculate(...)`, `w < 0` → пропуск; MC: `!canBeMindControlled` → пропуск, controlOdds (см. «Числа»), `RNG::percent(controlOdds)` → `+60`, иначе пропуск; USE: `RNG::percent(80 - diff*10)` → пропуск; радиус > 0 → `explosiveEfficacy(..., grenade=false)`, 0 → пропуск, иначе `+= 2 * eff * _intelligence`; радиус 0 → `+= getPowerBonus`; PANIC: `!canPanic` → пропуск, `+40`; лучший `weightToAttackMe > weightToAttack`
ДАННЫЕ:    validTarget с порогом threshold (50) — СТОРОНА; `getVisibleUnits` — ЮНИТ; позиция и статы жертвы (пси-защита, храбрость, мораль) — ИСТИНА; пси-сила — ЮНИТ/РУЛСЕТ
RNG:       RNG HERE: `RNG::globalRandomState().subSequence()` в TileEngine.cpp:4721 — один `next()` глобального генератора на каждую пару (жертва, тип с ОВ), сам случайный разброс 0..55 скрипта TryPsiAttackItem; RNG HERE: `RNG::percent(controlOdds)` AIModule.cpp:4081 — только для MC с `w ≥ 0` и управляемой жертвой; RNG HERE: `RNG::percent(80 - diff*10)` AIModule.cpp:4092 — только для USE с `w ≥ 0`
РЕЗУЛЬТАТ: `_aggroTarget`, `typeToAttack`, `weightToAttack`
СТОРОНЫ:   враг

### psiAction : сравнение с оружием и финальный бросок (AIModule.cpp:4133-4183)
УСЛОВИЕ:   `!_aggroTarget || !weightToAttack` → false; `if (_visibleEnemies && _attackAction.weapon)`: для AIMED, AUTO, SNAP, HIT с патроном: `weightPower = powerBonus` (HIT `/= 2`, иначе `*= shots`), `weightPower >= weightToAttack` → false; `else if (RNG::generate(35, 155) >= weightToAttack)` → false
ДАННЫЕ:    `_visibleEnemies` — устаревшая ветка (:533); оружие — РУЛСЕТ
RNG:       RNG HERE: `RNG::generate(35, 155)` AIModule.cpp:4168 — только если нет видимых врагов или нет оружия в руке
РЕЗУЛЬТАТ: `_psiAction.type = typeToAttack; target = _aggroTarget->getPosition()` (ИСТИНА — текущая клетка жертвы); `weapon = item`; true
ВОЗВРАТ:   setupAttack → return (никакая другая атака не считается); think :661 исполняет, если `turn >= getAIUseDelay` и `!_didPsi`
СТОРОНЫ:   враг

### think : исполнение пси и чередование (AIModule.cpp:661-675)
УСЛОВИЕ:   `_psiAction.type != BA_NONE && !_didPsi && _save->getTurn() >= _psiAction.weapon->getRules()->getAIUseDelay(_save->getMod())`
ДАННЫЕ:    `_didPsi` — ПАМЯТЬ; задержка — РУЛСЕТ (`ai: psionic`, по умолчанию 0, Mod.cpp:441)
RNG:       нет
РЕЗУЛЬТАТ: `_didPsi = true; action = пси; action->number -= 1`; return. Иначе `_didPsi = false`
ПРЕРЫВАНИЕ: следующий think psiAction откажет (`!_didPsi` ложно), потом флаг снимется — пси не чаще раза за два think; reset (:162-170) `_didPsi` не трогает, флаг переходит через границу хода
СТОРОНЫ:   враг

### wayPointAction : выбор цели (AIModule.cpp:3385-3409)
УСЛОВИЕ:   `!attackCost.haveTU()` для BA_LAUNCH → return; цикл по юнитам до первой найденной (`if (_aggroTarget != 0) break;`): `validTarget(bu, true, true)`; `calculate(_unit, bu->getPosition(), BAM_MISSILE, bu, -1)` (A* до 10000, Pathfinding.cpp:272-275); `getStartDirection() != -1 && explosiveEfficacy(bu->getPosition(), _unit, radius, diff)` (grenade=false)
ДАННЫЕ:    позиция цели — ИСТИНА; знание — СТОРОНА (видимость не требуется); `ammo = getAmmoForAction(BA_LAUNCH)` — на null не проверяется (:3402-3404)
RNG:       нет
РЕЗУЛЬТАТ: `_aggroTarget` = первая в списке юнитов цель с путём ракеты и положительной оценкой взрыва (не лучшая)
СТОРОНЫ:   враг (у бота `_knownEnemies == 0`, вызова нет)

### wayPointAction : путевые точки (AIModule.cpp:3411-3465)
УСЛОВИЕ:   `type = BA_LAUNCH; updateTU(); !haveTU()` → RETHINK, return; `maxWaypoints = getCurrentWaypoints()`, `-1` → `6 + diff * 2`; повторный путь BAM_MISSILE; по шагам: линия вокселей от текущей клетки к последней точке; `V_EMPTY < CollidesWith < V_UNIT` → точка в предыдущей клетке; `CollidesWith == V_UNIT` и юнит этой клетки — цель → точка в текущей; `_attackAction.target = waypoints.front()`; `LastWayPoint != _aggroTarget->getPosition()` → RETHINK
ДАННЫЕ:    геометрия, юниты на пути — ИСТИНА
RNG:       нет
РЕЗУЛЬТАТ: BA_LAUNCH с waypoints (копируются в action на :810-813) или RETHINK
ПРЕРЫВАНИЕ: дальше в setupAttack граната и ближний бой могут перезаписать тип
СТОРОНЫ:   враг

### tacticalMode : отмена атаки ближнего боя и гранаты у бота (AIModule.cpp:2961-2994)
УСЛОВИЕ:   только при `_spottingEnemies`, есть укрытие (`_escapeAction.type == BA_WALK`, клетка не своя, смотрящих меньше); `wounded = careful && (getFatalWounds() > 0 || getHealth() < base.health / 2)` → ESCAPE "pullback"; `careful && weapon && type != BA_WALK && TU - BattleActionCost(type, ...).Time < _escapeTUs` → ESCAPE "scoot"
ДАННЫЕ:    ОВ — ЮНИТ; `_escapeTUs` — ПАМЯТЬ
RNG:       нет
РЕЗУЛЬТАТ: BA_HIT и BA_THROW (стоимость без prime и +4) могут смениться отходом; рывок BA_WALK проходит как "attack"
СТОРОНЫ:   бот (careful). Не в этой области — описано в 11; здесь только как прерывание атак области

### UnitWalkBState : удар в конце рывка (UnitWalkBState.cpp:481-503)
УСЛОВИЕ:   `_unit->getFaction() != FACTION_PLAYER` и `getCharging() != 0` и `validMeleeRange(_unit, charging, dir)`
RNG:       нет (в самом ветвлении)
РЕЗУЛЬТАТ: враг бьёт сразу по приходу (MeleeAttackBState). Бот (PLAYER) — нет: удар только на следующем think
СТОРОНЫ:   оба, по-разному; `charging` также запрещает останавливать ходьбу при новом замеченном враге (:276, :444) у любой фракции

---

## 3. Числа

| что | значение | выражение / геттер | файл:строка | на что влияет |
|---|---|---|---|---|
| стартовый `_closestDist` | 100 | `_closestDist = 100` | AIModule.cpp:2243, 2297 | отсечка цели в selectNearestTarget(Leeroy) |
| порог веса угрозы | 50 | `getAITargetWeightThreatThreshold()` (рулсет `ai: targetWeightThreatThreshold`) | Mod.h:247; AIModule.cpp:4279 | psiAction и прочие `validTarget(..., false)` |
| вес врага | 100 | `getAITargetWeightAsHostile` | Mod.h:248; AIModule.cpp:4229 | фильтр, efficacy |
| вес мирных (для врага) | 50 | `getAITargetWeightAsHostileCivilians` | Mod.h:249; AIModule.cpp:4234 | фильтр (>0 проходит, >50 нет — мирные не цель пси) |
| вес своих | −200 | `getAITargetWeightAsFriendly` | Mod.h:250; AIModule.cpp:4214 | efficacy |
| вес нейтрала (для бота) | −100 | `getAITargetWeightAsNeutral` | Mod.h:251; AIModule.cpp:4239 | нейтрал не цель бота |
| AIW_IGNORED | 0 | `AIW_IGNORED` | AIModule.h:42 | неизвестная цель |
| AIW_SCALE | 100 | `AIW_SCALE` | AIModule.h:41 | единицы efficacy |
| Пиратки, веса | не заданы | `targetWeight*` в values.tsv нет; `ai:` Piratez_Globals.rul:9151 без весов | — | действуют умолчания |
| интеллект солдата (бот) | 2 | `_intelligence = 2` | BattleUnit.cpp:85 | окно знания (ходов) |
| агрессия солдата (бот) | 1 | `_aggression = 1` | BattleUnit.cpp:86 | selectMeleeOrRanged, :1904 |
| коэффициент сложности | 0..4 | `DIFFICULTY_COEFFICIENT[min(diff,4)]` | Mod.cpp:287-291; SavedGame.cpp:957; AIModule.cpp:526 | уклонение, efficacy, waypoints, пси USE |
| meleeOdds база | 10 | `int meleeOdds = 10` | AIModule.cpp:4314 | шанс ближнего |
| бонус урона | `(dmg - 50) / 2` при dmg > 50 | `reduceByResistance(powerBonus(BA_HIT))` | AIModule.cpp:4316-4321 | шанс ближнего |
| штраф за видимых | `−20 × (vis − 1)` | `_visibleEnemies` | AIModule.cpp:4322-4325 | шанс ближнего |
| порог здоровья | ≥ 2/3 | `getHealth() >= 2 * base.health / 3` | AIModule.cpp:4327 | бросок вообще |
| агрессия 0 / >1 | −20 / +10×агр | | AIModule.cpp:4329-4336 | шанс ближнего |
| запас на рывок | `min(TU − cost.Time, 2 × (energy − cost.Energy))` | | AIModule.cpp:3300 | дальность и maxTU пути |
| досягаемость | `chargeReserve / 4 + 1` | | AIModule.cpp:3301 | кого атаковать (distance2d) |
| отсечка жертвы | 20 клеток | `newDistance > 20` | AIModule.cpp:3306 | ближний бой |
| соседство | `distance2d == 1` | только по осям: диагональ даёт `ceil(√2) = 2`, z не учитывается | AIModule.cpp:3310; Position.h:118-120 | принятие без поиска клетки |
| уклонение | `meleeDodge × meleeDodgeBackPenalty × diff / 160` | `getMeleeDodge(target)` Armor.cpp:765, `getMeleeDodgeBackPenalty()` :773 (умолч. 0) | AIModule.cpp:2391 | бонус за удар в спину |
| дуга | `abs(((a − b) + 12) % 8 − 4)` | `getArcDirection(dir − 4, dirTarget)` 0..4 | TileEngine.cpp:5851; AIModule.cpp:2422 | ×уклонение |
| оценка клетки | `path.size() − dodge × arc` (усечение в int) | | AIModule.cpp:2422 | меньше лучше |
| Leeroy: стартовая дальность | 1000 | | AIModule.cpp:3348 | без предела |
| Leeroy: maxTU пути | 100000 | | AIModule.cpp:2475 | ОВ не важны |
| Leeroy: бег | энергия > 0.4 × стамина | `allowsRunning(false)` | AIModule.cpp:245 | BAM_RUN |
| граната: подъём | +4 ОВ | `action.Time += 4` | AIModule.cpp:3922; списание :798 | хватит ли ОВ |
| граната: взвод | `getActionTUs(BA_PRIME)` | | AIModule.cpp:3923; списание :797 | хватит ли ОВ |
| desperation | `(100 − morale) / 10`, +3 если ранение > 2/3 | | AIModule.cpp:3189-3193 | efficacy и фильтр одиночной цели |
| камикадзе | −400 | `AIW_SCALE * 4` при |dz| ≤ height и dist ≤ radius | AIModule.cpp:3198-3201 | efficacy |
| сложность в efficacy | `100 × diff / 2` | `AIW_SCALE * diff/2` | AIModule.cpp:3204 | efficacy |
| одиночная цель (граната) | 0, если desperation < 6 и enemiesAffected < 2 | | AIModule.cpp:3259-3262 | бросок по одному |
| «много врагов» | ≥ 10 → вернуть число | | AIModule.cpp:3264-3267 | игнор потерь своих |
| высота взрыва | код 0, установка 2 | `Options::battleExplosionHeight` | Options.cpp:262; options.cfg | учёт юнитов по z |
| узел: старт счёта | 2 (нужно ≥ 3) | `bestScore = 2` | AIModule.cpp:4356, 4400 | бросок в узел |
| узел: дальность | `radius < dist ≤ 20` | | AIModule.cpp:4366 | узлы-кандидаты |
| узел: очки | +1 противник (известен), −2 прочие | | AIModule.cpp:4381-4389 | счёт |
| проксимити: сдвиги | 4 соседние клетки | | AIModule.cpp:3941-3953 | точка броска |
| задержка гранаты, Пиратки | 1 | `turnAIUseGrenade: 1` (умолч. 3) | Piratez_Globals.rul:8866; Mod.cpp:441; RuleItem.cpp:2104 | с какого хода |
| задержка бластера, Пиратки | 1 | `turnAIUseBlaster: 1` (умолч. 3) | Piratez_Globals.rul:8867 | с какого хода |
| задержка пси | 0 | умолчание, у предметов Пираток поля нет | Mod.cpp:441 | исполнение пси (:661) |
| пси: резерв | + `_escapeTUs` ОВ, + `_escapeTUs / 2` энергии | | AIModule.cpp:4006-4007 | хватает ли на пси |
| пси MC: база | 40 | `controlOdds = 40` | AIModule.cpp:4061 | |
| пси MC: храбрость | `bravery = reduceByBravery(10) = (110 − bravery) × 10 / 100`; > 6 → −15, < 4 → +15 | BattleUnit.cpp:2989 | AIModule.cpp:4063-4067 | трусливых (большое значение) реже |
| пси MC: мораль | ≥ 40: −15 если `morale − 10 × bravery < 50`; < 40: +15; 0 → 100 | | AIModule.cpp:4068-4080 | |
| пси MC: бонус | +60 | | AIModule.cpp:4083 | вес |
| пси USE: отказ | `80 − diff × 10` % | | AIModule.cpp:4092 | 80 % на diff 0, 40 % на diff 4 |
| пси USE: бонус взрыва | `2 × efficacy × _intelligence` | | AIModule.cpp:4103 | вес |
| пси PANIC: бонус | +40 | | AIModule.cpp:4120 | вес |
| пси против оружия | HIT `power / 2`, огонь `power × shots` | | AIModule.cpp:4153-4165 | отказ от пси |
| пси: порог без оружия | `generate(35, 155) ≥ weight` → нет | | AIModule.cpp:4168 | |
| пси: защита | `30 + psiDefence` (умолч. скрипт TryPsiAttackItem: attack + random 0..55 − defense − distance) | | TileEngine.cpp:4707-4739; BattleItem.cpp:1711 | `w < 0` — пропуск |
| бластер: точки | `getCurrentWaypoints()`, при −1 `6 + diff × 2` | рулсет `waypoints`, Пиратки 2..9 | AIModule.cpp:3424-3428 | длина маршрута |
| бластер: путь | A* до 10000 | `maxTUCost == -1 && BAM_MISSILE` | Pathfinding.cpp:272-275 | досягаемость цели |

---

## 4. RNG (в порядке выполнения think)

| № | файл:строка | вызов | что решает | когда вызывается |
|---|---|---|---|---|
| 1 | TileEngine.cpp:4721 | `RNG::globalRandomState().subSequence()` (1 `next()` глобального) | разброс пси-атаки в оценке psiAttackCalculate | враг: `_knownEnemies > 0`, есть пси-предмет, `have`, `!_didPsi`, на каждую пару (жертва size 1, валидна с порогом, в дальности, при LOSRequired — в поле зрения) × (тип с ОВ) |
| 2 | AIModule.cpp:4081 | `RNG::percent(controlOdds)` | годится ли MC | только MC с `w ≥ 0` и управляемой жертвой |
| 3 | AIModule.cpp:4092 | `RNG::percent(80 - diff*10)` | отказ от USE | только BA_USE с `w ≥ 0` |
| 4 | AIModule.cpp:4168 | `RNG::generate(35, 155)` | финальный порог пси | только если пси-кандидат найден и (`_visibleEnemies == 0` или нет оружия в руке) |
| 5 | AIModule.cpp:1839 | `RNG::percent(getSniperPercentage())` | снайперская атака (карточка 12) | враг, пси не выбран, не `_blaster`, есть unitRules |
| 6 | AIModule.cpp:4338 | `RNG::percent(meleeOdds)` | ближний или дальний | `selectNearestTarget() > 0`, `_melee && _rifle`, оба с патронами, `meleeOdds > 0` до поправки на агрессию и здоровье ≥ 2/3 |
| 7 | AIModule.cpp:1904 | `RNG::generate(0, 3)` | искать огневую точку (вне области) | атака не выбрана и `_spottingEnemies == 0` (короткое замыкание `||`) |

Без RNG: selectNearestTarget(Leeroy), selectPointNearTarget(Leeroy), meleeAction(Leeroy), meleeAttack,
getTargetAttackWeight (скрипт по умолчанию без random, BattleUnit.cpp:7210), validTarget, grenadeAction
(`RNG::shuffle` закомментирован, :3948), validateThrow, explosiveEfficacy, getNodeOfBestEfficacy, wayPointAction,
validMeleeRange. Выбор между равными — порядком перебора (список юнитов, клетки z→x→y), а не броском.

Чувствительность: точка 1 вызывается столько раз, сколько пар прошло фильтры, — смена порядка юнитов, дальности или
ОВ меняет число вызовов глобального генератора и сдвигает все броски дальше в ходу. Точки 2-3 — то же внутри цикла.
Точка 6 зависит от `_visibleEnemies`, посчитанного по устаревшей ветке (:533): правка порядка в think меняет, будет ли бросок.

---

## 5. Знание

| вход решения | где | метка | примечание |
|---|---|---|---|
| известна ли цель | getTargetAttackWeight :4217 | СТОРОНА | `turnsSinceSpotted ≤ intelligence`, снайперы-споттеры |
| позиция цели | везде (`bu->getPosition()`) | ИСТИНА | текущая, а не последняя увиденная |
| видна ли цель (вход в бой) | selectNearestTarget :2249 | ЮНИТ (LOS пересчитан, без конуса) | TileEngine::visible :1864-1928 |
| видна ли цель (рывок, бластер) | meleeAction :3306, wayPointAction :3397 | — | не проверяется: достаточно знания стороны |
| видна ли цель (пси) | psiAction :4031-4032 | ЮНИТ | только при `isLOSRequired`; иначе СТОРОНА |
| статус цели (isOut) | validTarget :4268 | ИСТИНА | |
| фракция цели | getTargetAttackWeight | ИСТИНА | |
| dangerous клетки | validTarget, selectPointNearTarget, explosiveEfficacy | ИСТИНА | общий флаг клетки, два смысла |
| занятость клетки подхода | setUnitPosition (SavedBattleGame.cpp:2632-2676) | ИСТИНА | невидимые юниты тоже |
| досягаемость клеток | `_reachable` | ПАМЯТЬ | этот think или прошлый (вызов с :533) |
| пути подхода | Pathfinding::calculate | ИСТИНА (+ isBlocked: известная игроку видимость, Pathfinding.cpp:1206-1226) | см. 31 |
| направление и уклонение цели | selectPointNearTarget :2389-2391 | ИСТИНА + РУЛСЕТ | |
| сопротивление цели | selectMeleeOrRanged :4316 | ИСТИНА + РУЛСЕТ | |
| юниты в радиусе взрыва | explosiveEfficacy, узел | ИСТИНА позиций, СТОРОНА веса | свои (−200) учитываются всегда, неизвестные противники (вес 0) пропускаются |
| линия до юнита в радиусе | explosiveEfficacy :3244 | ИСТИНА | |
| пси-защита, мораль, храбрость жертвы | psiAction, psiAttackCalculate | ИСТИНА | |
| ОВ, энергия, мораль, здоровье своего | всё | ЮНИТ | |
| `_escapeTUs`, `_didPsi`, charging | psiAction, think, meleeAction | ПАМЯТЬ | |
| веса, задержки, waypoints, meleeDodge, isLeeroyJenkins, LOSRequired | | РУЛСЕТ | |

---

## 6. Карточки режимов

### 6.1. Ближний бой врага (meleeAction + selectPointNearTarget)

| пункт | как в коде |
|---|---|
| вход | setupAttack :1875 при `_melee` после `selectNearestTarget() > 0` (хоть одна видимая валидная цель); `_melee` — утилитарное melee есть (:535) и не обнулено гранатой/selectMeleeOrRanged |
| выбор цели | 1) если ближайшая видимая (`_aggroTarget` из selectNearestTarget) уже в досягаемости удара — удар (:3292-3299). 2) иначе перебор **всех** юнитов: ближайшая по `distance2d` валидная (включая мирных для врага), не дальше 20 и ближе `chargeReserve/4 + 1`, к которой есть клетка подхода; соседняя (`distance2d == 1`) принимается без поиска клетки |
| ранжирование | только расстояние; вес — фильтр (> 0), не ранг. Бойцы и мирные (вес 100 и 50) равны |
| клетки-кандидаты | кольцо вокруг цели на z−1..z+1, только из `_reachable` (все ОВ хода), свободные по истине, не dangerous, с годной `validMeleeRange` |
| жёсткие отказы | нет ОВ+энергии на удар (:3287); цель дальше 20; dangerous клетка цели; клетка не в `_reachable`; занята; dangerous клетка подхода; путь пуст (`getStartDirection() == -1`) |
| оценка | `path.size() − dodge × arc` — меньше лучше; бонус за удар в спину растёт со сложностью и `meleeDodgeBackPenalty` брони цели |
| штраф за видимость / реакцию | нет: `getSpottingUnits`, реакция, огонь на реакцию не читаются ни в meleeAction, ни в selectPointNearTarget, ни в validMeleeRange |
| RNG | нет (кроме выбора melee/ranged в selectMeleeOrRanged, если есть и огнестрел) |
| первая или лучшая | цель — ближайшая (строго `<`) с поправкой «соседняя всегда»; клетка — лучшая по оценке, при равенстве первая; оба цикла идут до конца |
| ОВ | резерв — только стоимость удара (ОВ и энергия×2); `maxTUs = chargeReserve` ограничивает лишь A*, прямой путь `bresenhamPath` предела по ОВ не имеет (Pathfinding.cpp:258, параметр `maxTUCost` в теле не используется, :1704) |
| энергия | учтена в chargeReserve; при беге — нет (BAM_NORMAL) |
| угроза ближнего боя врага | не учитывается |
| другие враги | не учитываются (кроме того, что они могут занимать клетки) |
| путь пропал | клетка отбрасывается; нет клеток — цель отбрасывается; нет целей — тип остаётся прежним (обычно RETHINK → findFirePoint) |
| исполнение | BA_WALK к клетке, `setCharging(цель)`; evaluateAIMode форсирует COMBAT (:2671, :2871); при приходе — автоудар (UnitWalkBState.cpp:481-503) |
| запасные ветки | граната перед ним (:1869) перекрывает ближний бой (`_melee = false`); огнестрел после него может перезаписать тип, только если `_rifle` уцелел |

### 6.2. Ближний бой бота (careful)

| пункт | как в коде |
|---|---|
| вход | тот же путь. `_melee` у бота почти всегда true: броня солдат Пираток даёт специальное оружие `STR_UNARMED_BASIC` (battleType 3 = BT_MELEE, costMelee 8 ОВ / 2 энергии), `STR_UNARMED_GAUNTLET`, `AUX_FISTO` и др.; getUtilityWeapon смотрит руки, затем специальное (BattleUnit.cpp:5415, 5617) |
| careful-ветки | в функциях ближнего боя нет ни одной ветки по `AiProbe::careful` или флагам V4 |
| выбор ближний/дальний | при огнестреле в руке — `selectMeleeOrRanged`: 10 % при одном видимом враге, 0 % (броска нет) при двух и больше; успех отключает выстрел в этом think (`_rifle = false`, :4340) |
| цели | только HOSTILE (`_targetFaction = FACTION_HOSTILE`, BattlescapeGame.cpp:429); нейтралы −100 — не цель |
| досягаемость `ОВ/4+1` | это дальность **самого атакующего** (:3301), не досягаемость врагов |
| враги ближнего боя рядом с клеткой атаки | не учитываются: `AiProbe::closeEnemies` вызывается только из setupEscape (:2088, :2139) и вне V4 (OXCE_AI_GAP); в selectPointNearTarget нет ни перебора врагов, ни их ОВ |
| реакция | не учитывается |
| прерывание | tacticalMode (бот, при замеченности и наличии укрытия): BA_HIT отменяется на отход, если после удара ОВ < `_escapeTUs` ("scoot") или юнит ранен ("pullback"); рывок BA_WALK проходит ("attack") |
| после рывка | автоудара нет (UnitWalkBState.cpp:481 — только не PLAYER); удар на следующем think, если цель ещё в досягаемости и tacticalMode не отменит |
| charging | ставится и у бота; запрещает останавливать ходьбу при новом замеченном враге (UnitWalkBState.cpp:276, :444) и форсирует COMBAT (evaluateAIMode :2671, :2871) |
| засада | при `_melee` setupAmbush не вызывается (:647) — у бота с кулаком брони засады нет вовсе |
| пси, бластер, снайпер | никогда (`_knownEnemies == 0` у не-HOSTILE, :2183) |

### 6.3. Leeroy (dont_think)

| пункт | как в коде |
|---|---|
| кто | `isLeeroyJenkins` из рулсета юнита. В Пиратках 16: STR_AUR_2, STR_CHUPACABRA_TERRORIST, STR_DEEP_ONE_BERSERKER, STR_DOOM_DEMON_TERRORIST, STR_DOOM_SOUL_TERRORIST, STR_ERIDIAN_FENCER, STR_MAGGOT_TERRORIST, STR_MEGAZOMBIE_TERRORIST, STR_MUTON_HEAVY, STR_SKELETON_TERRORIST, STR_ZOMBIE, STR_ZOMBIE_BUSTER_TERRORIST, STR_ZOMBIE_GRUBAS_TERRORIST, STR_ZOMBIE_PIMP_TERRORIST, STR_ZOMBIE_STERILE_TERRORIST, STR_ZOMBIE_TROOPER_2 (values.tsv) |
| вход в атаку | хоть одна видимая валидная цель, к которой есть клетка (selectNearestTargetLeeroy), и утилитарное BT_MELEE с canUseWeapon |
| выбор цели | ближайшая по distance2d среди **всех известных** (без отсечки 20, без видимости), соседняя всегда |
| клетки | кольцо вокруг цели, без `_reachable`, без dangerous, без уклонения; лучшая по числу шагов |
| ОВ | не проверяются вовсе (ни на удар, ни на путь: maxTU 100000) |
| бег | BAM_RUN, если энергия > 0.4×стамины |
| RNG | нет в атаке; в патруле — по setupPatrol |
| что не делает | граната, огнестрел, пси, бластер, отход, засада, evaluateAIMode, tacticalMode — не вызываются (return на :602). STR_AUR_2 с огнестрелом AUX_TEC_0_WEAPON его не применяет |
| нет цели | патруль, `setCharging(0)`, `_reserve = BA_NONE` |

### 6.4. Граната (grenadeAction + explosiveEfficacy + getNodeOfBestEfficacy)

| пункт | как в коде |
|---|---|
| вход | setupAttack :1869 при `_grenade` после `selectNearestTarget() > 0`; граната — первый предмет с поясом/руками, у которого `turn ≥ turnAIUseGrenade` (Пиратки 1) |
| цель 1 | клетка `_aggroTarget` (ближайшая видимая), если explosiveEfficacy(grenade=true) > 0 |
| цель 2 | узел карты по getNodeOfBestEfficacy: `radius < dist ≤ 20`, виден с точки обзора бросающего, ≥ 3 очков (+1 известный противник, −2 любой другой, в том числе свой и мирный для нейтрала; z не учитывается, строго `< radius`) |
| жёсткие отказы | нет ОВ на бросок + взвод + 4; цель летит над пустотой (z > 0 без пола); одиночная цель при desperation < 6; efficacy ≤ 0; ни одна клетка не прошла validateThrow |
| свои | вес −200 за каждого своего в радиусе с прямой линией от центра взрыва; самого бросающего — только −400 «камикадзе», если он в радиусе |
| ≥ 10 врагов | потери своих игнорируются |
| проксимити | бросок в соседнюю клетку цели, ближнюю к бросающему; оценка своих делается для клетки цели, а не для клетки падения |
| RNG | нет |
| первая или лучшая | узел — лучший; клетка броска — первая годная |
| ОВ | prime и +4 списываются в think сразу при выборе COMBAT с BA_THROW (:795-799), до броска |
| реакция, угроза ближнего боя | не учитываются |
| бот | клетка цели — да; узел — никогда (все −2); у бота с моралью 100 desperation 0 → нужно ≥ 2 врагов в радиусе с линией, а каждый свой рядом съедает 200 |

### 6.5. Взрывчатка снаряда и пси-взрыв (explosiveEfficacy при grenade=false)

| пункт | как в коде |
|---|---|
| где | wayPointAction (:3404) — для каждой цели по очереди; psiAction BA_USE с радиусом (:4100) |
| отличие от гранаты | нет фильтра «одиночная цель», нет отказа по полёту над пустотой: достаточно `efficacy > 0` |
| итог | `100×desperation + 50×diff + вес цели + Σвесов в радиусе − 400 (если сам в радиусе)` / 100, или число врагов при ≥ 10 |

### 6.6. Пси (psiAction)

| пункт | как в коде |
|---|---|
| кто | враг с утилитарным BT_PSIAMP, `_knownEnemies > 0`, не под контролем, ОВ на тип + `_escapeTUs`, `!_didPsi` |
| кандидаты | size 1, вес > 50 (мирные для врага не цели), исходная фракция ≠ своей, при LOSRequired — в `getVisibleUnits`, в дальности предмета |
| типы | USE, PANIC, MINDCONTROL; на каждую пару — psiAttackCalculate (бросок генератора) |
| оценка | `w` из psiAttackCalculate + MC 60 (после броска controlOdds) / USE 2×eff×int или powerBonus (после броска 80−10×diff на отказ) / PANIC 40 |
| выбор | лучшая пара строго `>`, при равенстве первая |
| финальный порог | при видимом враге и оружии в руке — пси, только если вес больше мощности каждого режима оружия (огонь ×выстрелов, удар /2); иначе бросок 35..155 |
| ОВ | единственная атака области, резервирующая ОВ на отход (`_escapeTUs`) |
| исполнение | цель — истинная клетка жертвы; исполняется на think :661, если `turn ≥ ai.psionic` (0); иначе setupAttack уже вернулся без другой атаки, и think идёт дальше с RETHINK |
| чередование | после пси следующий think пси не выбирает (`_didPsi`), флаг не сбрасывается между ходами |
| бот | никогда |

### 6.7. Путевые точки (wayPointAction)

| пункт | как в коде |
|---|---|
| кто | враг с огнестрелом, у которого `getCurrentWaypoints() != 0` (Пиратки: AUX_RETRIBUTION_LAUNCHER 3, STR_ARCANE_RAY 7, STR_ATGM 3, STR_BLASTER_MULTI_LAUNCHER 6, STR_HWP_SENTRY_SPIKE 2, STR_PIR_BLASTER_LAUNCHER 7, STR_PRED_DISC 3, STR_VR_BLASTER_LAUNCHER 9, STR_WIZ_SPELL_MENTAL_RAY 7), `_knownEnemies > 0`, пси не выбран |
| цель | **первая** в списке юнитов известная (вес > 0, включая мирных), с путём ракеты и `efficacy > 0`; видимость не нужна |
| маршрут | точки на поворотах, где прямая линия задевает стены; не больше waypoints оружия; маршрут обязан закончиться на цели, иначе RETHINK |
| свои на линии полёта | не проверяются (V_UNIT чужого юнита просто пропускается, :3448-3456) |
| RNG | нет |
| ОВ | BA_LAUNCH; резерва на отход нет |
| запасные ветки | граната и ближний бой дальше в setupAttack перезаписывают BA_LAUNCH; если RETHINK — обычный путь (findFirePoint) |
| бот | никогда |

---

## 7. Слепые пятна (доказано кодом)

1. **Реакция и замеченность при ближнем бое.** meleeAction, selectPointNearTarget, validMeleeRange, meleeAttack не
   вызывают `getSpottingUnits` и не читают ОВ/реакцию врагов; рывок идёт через открытую местность без штрафа.
2. **Враги ближнего боя рядом с клеткой атаки (бот и враг).** В selectPointNearTarget нет перебора других юнитов,
   кроме занятости клетки (`setUnitPosition`); `AiProbe::closeEnemies` в области не вызывается и вне V4.
3. **Резерв после удара.** chargeReserve оставляет ровно стоимость удара; на укрытие, второй удар или отход не
   оставляется ничего (`_escapeTUs` в ближнем бою не читается, только в psiAction и tacticalMode).
4. **maxTUs не ограничивает прямой путь.** Pathfinding::calculate вызывает bresenhamPath без maxTU (Pathfinding.cpp:258),
   у bresenhamPath параметр `maxTUCost` не используется (:1704); клетка допускается, если она в `_reachable` (все ОВ
   хода), поэтому рывок может съесть ОВ, отложенные на удар, — удар не состоится.
5. **Устаревшие данные на :533.** selectNearestTarget вызывается до обновления `_melee/_rifle` (:535-536) и до
   `_reachable` (:550): `_visibleEnemies` (штраф в selectMeleeOrRanged, порог пси) и ветка LOS/клетка могут быть по
   прошлому think; `_attackAction.target` может переписаться клеткой от прошлой позиции.
6. **Соседство по distance2d.** `newDistance == 1` — только соседи по осям и на любом z (z не учитывается);
   диагональный сосед (`ceil(√2) = 2`) идёт через поиск клетки. Для соседа по `distance2d == 1` клетка не ищется и
   `_attackAction.target` не обновляется: если validMeleeRange не проходит (другой этаж, стена), остаётся BA_WALK к
   клетке, записанной раньше (для другой цели или из :533), при этом `charging` указывает на новую цель.
7. **Цель рывка не обязана быть видимой.** Перебор в meleeAction и meleeActionLeeroy фильтрует только validTarget
   (знание стороны), а позицию берёт истинную (`bu->getPosition()`): юнит идёт в клетку рядом с текущим положением
   цели, которую никто из своих сейчас не видит. То же у wayPointAction и узла гранаты.
8. **Вес не ранжирует.** Во всём ближнем бое вес — только фильтр: мирный (50) и боец (100) равны, решает расстояние;
   выбор в пользу последней соседней по порядку списка юнитов.
9. **dangerous — общий флаг с двумя смыслами** (зона гранаты не игрока и клетка с недостижимым предметом,
   BattlescapeGame.cpp:552, :2848, :3152): им исключаются и цели (validTarget), и клетки подхода, и юниты из оценки
   взрыва; это истина клетки, одинаковая для бота и врага.
10. **Занятость по истине.** setUnitPosition(test) видит невидимых юнитов: клетка подхода, занятая невидимым врагом,
    тихо исключается (утечка знания).
11. **Бот никогда не бросает в узел** (getNodeOfBestEfficacy даёт −2 любому юниту при фракции PLAYER, :4379-4389).
12. **Узел гранаты не учитывает z** (distance2d, :4372) и строго `< radius`, тогда как explosiveEfficacy — `≤ radius`
    и `|dz| ≤ battleExplosionHeight`: две оценки одной гранаты не согласованы.
13. **Проксимити: оценка не там, куда падает.** explosiveEfficacy считается для клетки цели, бросок — в соседнюю; свои
    у соседней клетки не перепроверяются; сама клетка цели исключена из сдвигов.
14. **Юнит на целевой клетке взрыва считается врагом** (`++enemiesAffected`, :3210) при любой фракции.
15. **wayPointAction берёт первую, а не лучшую цель;** `ammo` не проверяется на null (:3402-3404); при пустом
    `waypoints` вызывается `front()` (:3460) — неопределённое поведение (возможно, недостижимо, см. «Не прослежено»).
16. **Свои на линии ракеты не проверяются** при прокладке маршрута (V_UNIT не-цели пропускается).
17. **Бонус храбрости в MC работает наоборот названию:** `reduceByBravery(10)` растёт у трусливых, и именно им
    controlOdds снижен на 15 (:4063-4065).
18. **Пси исполняется не чаще раза в два think** (`_didPsi`), флаг переносится через ход; до `ai.psionic` хода
    выбранный пси блокирует все прочие атаки этого think (setupAttack вернулся на :1825).
19. **Leeroy не проверяет ОВ** ни на удар, ни на путь, и не применяет огнестрел, гранату, отход.
20. **Бесплатный поворот** в meleeAttack (turn() в цикле во время think), остающийся при отмене атаки.
21. **Перезапись в setupAttack:** BA_LAUNCH, выбранный wayPointAction, перекрывается гранатой и ближним боем без
    сравнения оценок; граната всегда главнее ближнего боя и выстрела.
22. **У бота засада исключена кулаком брони:** `_melee = (getUtilityWeapon(BT_MELEE) != 0)` (:535) истинно при
    специальном оружии брони, а setupAmbush требует `!_melee` (:647).

---

## 8. Не прослежено

- Шанс попадания и уклонения при исполнении удара (MeleeAttackBState, TileEngine::meleeAttack и т. п.) — карточка 30.
- sniperAction, projectileAction, findFirePoint, extendedFireModeChoice (другой путь броска гранаты и выстрела) — карточка 12.
- Может ли `waypoints` оказаться пустым при `_aggroTarget != 0` (путь BAM_MISSILE с непустым первым шагом и без
  столкновений до цели) — `front()` на пустом векторе не исключён кодом, но достижимость не проверена.
- Поведение `calculate`, когда клетка подхода — своя клетка юнита (start == end): `tryCalculateFinalPosition` и
  `bresenhamPath` до конца не прочитаны; вероятно, путь пуст и клетка отбрасывается (`getStartDirection() == -1`).
- Как setupEscape выставляет `_escapeTUs` в том же think до psiAction — карточка 11/14.
- Как `isBlocked` и флаги V4 (BLOCKED_STEP, WALKFOV_SKIP, FAST, LIGHTSKIP) меняют пути selectPointNearTarget — карточка 31.
- Правила `validMeleeRange` для юнитов 2×2 и `preferEnemy` (TileEngine.cpp:5382-5465) прочитаны без разбора всех веток.
- Живёт ли AIModule между ходами (влияет на перенос `_didPsi`, `_melee`, `_reachable` на :533) — код создания модуля не открыт.
- Скрипты `aiCalculateTargetWeight` и пси-скрипты в других модах, кроме Пираток (в Пиратках не переопределены).
