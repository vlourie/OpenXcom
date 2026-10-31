# 03. Выбор режима и порядок между режимами (`evaluateAIMode`, `tacticalMode`, `think`)

Код: коммит `7cd80e284`. Все ссылки — `src/...:строка` по текущему файлу. Метки знания и формат развилки — из
`00_README.md`. Враг = `FACTION_HOSTILE`, родной ИИ без `OXCE_AI_TACTICS`; бот = `FACTION_PLAYER`, `OXCE_AI_BOT=1`,
`OXCE_AI_CAREFUL=1` (`AiProbe::careful`); флаги V4 — см. README. Флаги, которых нет в V4, помечены «вне V4».

Режимы: `enum AIMode { AI_PATROL, AI_AMBUSH, AI_COMBAT, AI_ESCAPE }` (`src/Battlescape/AIModule.h:37`), поле
`_AIMode` (`AIModule.h:60`), начальное значение `AI_PATROL` (`src/Battlescape/AIModule.cpp:55`).

---

## 1. Краткая схема

```
BattlescapeGame::handleAI(unit)                                   src/Battlescape/BattlescapeGame.cpp:371
  ├── пропуск юнита: _AIActionCounter >= maxActions(2) || !reselectAllowed || getTurnsSinceStunned()==0   :379
  ├── бот: ai->setTargetFaction(FACTION_HOSTILE)  (AiProbe::careful)                                     :425-430
  ├── unit->think(&action)  → BattleUnit::think → (аптечка) → AIModule::think                            :447
  ├── если action.type == BA_RETHINK → ещё один ПОЛНЫЙ think (заново все броски)                        :449-453
  └── подобрал оружие (pickUpWeaponsMoreActively) → setWeaponPickedUp(); третий think                    :478-483

AIModule::think(action)                                                AIModule.cpp:506
  ├── сброс полей хода решения; _attackAction.type не трогается здесь                                    :508-531
  ├── _knownEnemies   = countKnownTargets()        (только у HOSTILE, иначе 0)                          :532
  ├── _visibleEnemies = selectNearestTarget()      (ВНИМАНИЕ: _rifle/_melee ещё с прошлого think)       :533
  ├── _spottingEnemies= getSpottingUnits(свой тайл)                                                     :534
  ├── _melee/_rifle(false) → findReachable → [вне V4: revive/flee бота → return]                        :535-560
  ├── Leeroy → dont_think, return                                                                        :598-603
  ├── _rifle/_blaster/_melee по оружию в руке; _grenade по поясу                                        :604-636
  ├── tactical = tactics(враг, вне V4) || careful(бот)                                                   :639
  ├── setupEscape()   если _spottingEnemies && (!_escapeTUs || tactical)                                 :640-645
  ├── setupAmbush()   если _knownEnemies && !_melee && !_ambushTUs                                       :647-652
  ├── setupAttack()   всегда                                                                             :654
  ├── setupPatrol()   всегда                                                                             :655-659
  ├── ПСИ: _psiAction готов и !_didPsi и ход >= aiUseDelay → действие пси, return (режим не трогается)  :661-675
  ├── evaluate? (по текущему режиму; RNG::percent(10) в PATROL)                                         :677-711
  │     └── evaluateAIMode()                                                                             :712-736
  │            ├── charging && attack!=RETHINK → COMBAT, return                                          :2671-2675
  │            ├── шансы (escape/ambush/combat/patrol) + до двух setupEscape внутри                      :2677-2843
  │            ├── RNG::generate(1, сумма) → режим                                                       :2845-2868
  │            ├── принудительно COMBAT: (HOSTILE && isCheating) || charging                             :2871-2874
  │            └── проверка годности: COMBAT → (findFirePoint) → PATROL → AMBUSH → ESCAPE               :2879-2932
  ├── _evalChosen (вне V4, OXCE_AI_EVAL) → COMBAT                                                        :738-741
  ├── tacticalMode()  если tactical (бот всегда)                                                         :743-746
  ├── перенос действия выбранного режима в action                                                        :752-835
  ├── [вне V4: halfWalk бота в PATROL]                                                                   :843-865
  └── BA_WALK: цель ≠ свой тайл → _escapeTUs=_ambushTUs=0; цель = свой тайл → BA_NONE                  :867-877
```

---

## 2. Входы шансов

### 2.1 `countKnownTargets` (AIModule.cpp:2179)

### countKnownTargets : подсчёт (AIModule.cpp:2179-2194)
УСЛОВИЕ:   `if (_unit->getFaction() == FACTION_HOSTILE)` (:2183); иначе цикл не выполняется и возвращается 0 (:2193)
ДАННЫЕ:    все `_save->getUnits()`; `validTarget(bu, true, true)` (:2187) → `isOut()` ИСТИНА, `getTile()->getDangerous()`
           ИСТИНА, `isIgnoredByAI()` РУЛСЕТ/состояние, `getTargetAttackWeight(bu) > AIW_IGNORED (0)` (:4274) — внутри
           `_intelligence < getTurnsSinceSpottedByFaction(своя фракция)` СТОРОНА (:4217), снайперский канал
           `getTurnsLeftSpottedForSnipersByFaction` СТОРОНА (:4218), веса брони/мода РУЛСЕТ (:4229, :4234, :4240), скрипт
           `aiCalculateTargetWeight` (:4243-4247; в рулсетах Пираток не задан — grep по `Пиратки/Dioxine_XPiratez/**/*.rul`
           пусто)
RNG:       нет
РЕЗУЛЬТАТ: число «известных» живых целей, **включая гражданских** (`includeCivs = true`: вес 50 > 0) и исключая тех,
           кто стоит на тайле с `getDangerous()` (под брошенной гранатой)
ВОЗВРАТ:   в `think` → `_knownEnemies` (:532)
СТОРОНЫ:   враг — да. **Бот и нейтралы — всегда 0** (фракция не HOSTILE). Это же подтверждает комментарий стенда
           `AiProbe.cpp:3558`: «the engine's known-enemies count is kept for the alien side only»

Позиции целей здесь не читаются — только факт «знаю». Но всё, что дальше работает с «известной» целью
(`selectClosestKnownEnemy`, `getSpottingUnits`), берёт её **текущую** позицию `bu->getPosition()` — ИСТИНА.

### 2.2 `getSpottingUnits(pos)` (AIModule.cpp:2201)

### getSpottingUnits : подсчёт «наблюдающих» (AIModule.cpp:2201-2233)
УСЛОВИЕ:   для каждого `bu` с `validTarget(bu, false, false)` (:2208): не `isOut`, тайл-опасность **не** проверяется
           (`assessDanger=false`), не `isIgnoredByAI` (кроме игрока), вес `> getAITargetWeightThreatThreshold()` (:4278;
           по умолчанию 50, `src/Mod/Mod.h:247`) — значит гражданские (вес 50) для врага **не** наблюдатели;
           `Position::distance2d(pos, bu->getPosition()) > 20 → continue` (:2210-2211, высота не учитывается)
ДАННЫЕ:    `getSightOriginVoxel(bu)` ИСТИНА (текущая точка глаз), `originVoxel.z -= 2` (:2213); трасса
           `canTargetUnit(&originVoxel, tile(pos), &targetVoxel, bu, false[, _unit])` ИСТИНА-геометрия:
           если `pos != своя позиция` (`checking`, :2204) — виртуальный юнит `_unit` на тайле (:2218), иначе — реальный
           (:2225). Отбор целей — СТОРОНА (знает ли фракция `bu` в пределах `intelligence` хода/снайперский канал)
RNG:       нет. `AiProbe::escapeTarget()` (:2215) — счётчик зонда
РЕЗУЛЬТАТ: число известных врагов в пределах 20 клеток по горизонтали, у которых есть **линия огня** из глаз в тайл
ВОЗВРАТ:   число
СТОРОНЫ:   оба. У бота `_targetFaction = FACTION_HOSTILE` (`BattlescapeGame.cpp:425-430`), поэтому враги для него —
           вес 100 (`AIModule.cpp:4226-4229`); без этого бот видел бы «наблюдателями» своих

Чего здесь нет (доказано телом :2201-2233 и `validTarget`/`getTargetAttackWeight` :4207-4280): направления взгляда
(сектор обзора), дальности зрения по свету/дыму (используется только трасса `canTargetUnit` и отсечка 20 клеток), того,
видит ли враг юнита на самом деле, оружия врага и его досягаемости, ОВ врага.

### 2.3 `selectNearestTarget` → `_visibleEnemies`, `_closestDist`, `_aggroTarget` (AIModule.cpp:2240)

### selectNearestTarget : видимые цели (AIModule.cpp:2240-2287)
УСЛОВИЕ:   `validTarget(bu, true, true) && TileEngine::visible(_unit, bu->getTile())` (:2248-2249)
ДАННЫЕ:    знание СТОРОНА (как в 2.1, гражданские входят); `TileEngine::visible` (`TileEngine.cpp:1864-1929`) —
           дальность, пси-зрение, трасса из глаз юнита, дым/свет — **без сектора обзора** (в функции нет чтения
           направления), позиции ИСТИНА; для ближайшего — проверка атаки: если `_rifle || !_melee` (:2256) —
           `canTargetUnit` из точки выстрела (:2263) ИСТИНА; иначе `selectPointNearTarget(bu, TU)` (:2267) и
           `validMeleeRange` — путь по `_reachable`
RNG:       нет
РЕЗУЛЬТАТ: `tally` = число видимых годных целей, но **0, если ни по одной нет атаки** (`_aggroTarget == 0`, :2281-2286);
           `_closestDist` = расстояние до выбранной (100 если нет, :2243); `_aggroTarget`
ПРЕРЫВАНИЕ: побочный эффект — в ветке ближнего боя `selectPointNearTarget` пишет `_attackAction.target = checkPath`
           (:2430)
ВОЗВРАТ:   число
СТОРОНЫ:   оба

**Устаревшие флаги на :533.** В `think` `selectNearestTarget()` вызывается на :533, а `_melee` и `_rifle`
выставляются только на :535-536 и :604-633. Поэтому ветка «огнестрел или ближний бой» при подсчёте `_visibleEnemies`
выбирается по флагам **прошлого** think этого юнита (в первом think — `false/false` из конструктора `:54`, то есть по
линии огня), а `selectPointNearTarget` ходит по `_reachable` прошлого think (новый считается на :550). Если оружие в
руке сменилось (подобрал, выронил, кончились патроны), `_visibleEnemies` этого решения посчитан по старому оружию.

`_closestDist`, который читает `evaluateAIMode` (:2816), — это значение **последнего** вызова `selectNearestTarget`
в этом think: на :533, либо внутри `setupEscape` (:1940), либо в `setupAttack` (:1859).

### 2.4 Прочие входы

| вход | где ставится | что значит |
|---|---|---|
| `_escapeTUs` | `setupEscape`: 0 в начале (:1939), ОВ пути к лучшей клетке (:2113) или 1, если клетка — свой тайл (:2114-2117) | «укрытие найдено»; 0 — не найдено или не считалось |
| `_ambushTUs` | `setupAmbush`: 0 в начале (:1634), ОВ (или 1 на своём тайле) у лучшей клетки (:1749) | «засада найдена» |
| сброс `_escapeTUs/_ambushTUs` | `AIModule::reset()` (:162-170) из `SavedBattleGame::endTurn` при смене стороны на игрока (`src/Savegame/SavedBattleGame.cpp:1547-1566`); в `think` при ходьбе на другой тайл (:867-873); после revive/flee (:557-558, вне V4) | живут в пределах хода юнита, пока он не сдвинулся |
| `_melee` | `getUtilityWeapon(BT_MELEE) != 0` (:535), `true` при оружии ближнего боя в руке (:625) | |
| `_rifle` / `_blaster` | огнестрел в руке, `canUseWeapon` (:609-621); бластер = есть путевые точки (:612) | |
| `_grenade` | `getGrenadeFromBelt` (:635-636) | |
| `_unit->getCharging()` | ставит `meleeAction` при броске к цели (:3316); сбрасывает `think`, если цель выбыла (:564-567), и ветки ESCAPE/PATROL/AMBUSH (:755, :768, :824) | |
| `isCheating()` | `SavedBattleGame::endTurn`: `(_turn > _cheatTurn/2 && liveAliens <= 2) || _turn > _cheatTurn` (`SavedBattleGame.cpp:1542-1545`); `_cheatTurn` из `alienDeployments.cheatTurn`, по умолчанию 20 (`src/Mod/AlienDeployment.cpp:42,170`) | |

---

## 3. Когда `think` вообще зовёт `evaluateAIMode`

### think : решение «переоценить режим» (AIModule.cpp:677-711)
УСЛОВИЕ:   по **текущему** `_AIMode` (с прошлого решения или хода):
           - `AI_PATROL`: `evaluate = (bool)(_spottingEnemies || _visibleEnemies || _knownEnemies || RNG::percent(10))` (:682)
           - `AI_AMBUSH`: `evaluate = (!_rifle || !_ambushTUs || _visibleEnemies)` (:685)
           - `AI_COMBAT`: `evaluate = (_attackAction.type == BA_RETHINK)` (:688)
           - `AI_ESCAPE`: `evaluate = (!_spottingEnemies || !_knownEnemies)` (:691)
           затем: `if (_weaponPickedUp) { evaluate = true; _weaponPickedUp = false; }` (:695-699)
           `else if (_spottingEnemies > 2 || _unit->getHealth() < 2 * _unit->getBaseStats()->health / 3) evaluate = true;` (:700-704)
           `if (_save->isCheating() && _AIMode != AI_COMBAT) evaluate = true;` (:707-710) — **без проверки фракции**
ДАННЫЕ:    `_spottingEnemies`, `_visibleEnemies`, `_knownEnemies` (раздел 2); `_ambushTUs` ПАМЯТЬ/этот think;
           `_attackAction.type` — итог `setupAttack` этого think; здоровье ИСТИНА (своё); `isCheating` ИСТИНА
RNG:       RNG HERE: `RNG::percent(10)` :682 — только если режим PATROL и все три счётчика равны 0 (короткое
           замыкание `||`). Бросок делается **до** проверок :695-710, то есть расходуется, даже если переоценка потом
           всё равно вынуждена
РЕЗУЛЬТАТ: `evaluate`
ВОЗВРАТ:   `evaluate` → `evaluateAIMode()` (:712-714); иначе режим остаётся прежним
СТОРОНЫ:   оба; различия:
           - бот: `_knownEnemies == 0` всегда → в ESCAPE `evaluate` всегда `true`; в PATROL бросок `percent(10)` идёт при
             любом «нет видимых и не наблюдают»;
           - враг: в ESCAPE, пока его наблюдают и он кого-то знает, режим **не пересчитывается** (инерция бегства).

Следствие (инерция, без броска):
- COMBAT держится, пока `setupAttack` хоть что-то нашёл (`_attackAction.type != BA_RETHINK`), — ни шанса бегства, ни
  `isCheating`-переоценки (условие :707 исключает COMBAT). Сменить его может только :695-704 (подобрал оружие,
  наблюдающих > 2, здоровье < 2/3) или `tacticalMode` бота.
- ESCAPE у врага держится между решениями и **между ходами** (`_AIMode` не сбрасывается в `reset()` :162-170, хранится в
  сейве :180, :206), пока `_spottingEnemies && _knownEnemies` и нет :695-710.
- AMBUSH держится, пока есть огнестрел, найдена засада (`_ambushTUs != 0`) и никого не видно.
- PATROL держится с вероятностью 90 %, пока никого не видно, не знают, не наблюдают.

Пороги здоровья в `think` и в `evaluateAIMode` записаны по-разному: `2 * health / 3` (:701) против
`2 * (health / 3)` (:2765) — при целочисленном делении это разные числа (база 50: 33 против 32).

---

## 4. `evaluateAIMode` (AIModule.cpp:2669-2933) полностью

### evaluateAIMode : атака с разбега (AIModule.cpp:2671-2675)
УСЛОВИЕ:   `(_unit->getCharging() && _attackAction.type != BA_RETHINK)`
ДАННЫЕ:    `getCharging()` ПАМЯТЬ (поставил `meleeAction` этого или прошлого решения); `_attackAction.type` — этот think
RNG:       нет (бросок режима не делается)
РЕЗУЛЬТАТ: `_AIMode = AI_COMBAT`
ВОЗВРАТ:   return — ни шансов, ни проверки годности
СТОРОНЫ:   оба

### evaluateAIMode : начальные шансы (AIModule.cpp:2677-2689)
УСЛОВИЕ / РЕЗУЛЬТАТ:
           `escapeOdds = 15` (:2677); `if (_melee) escapeOdds = 12` (:2678-2681);
           `if (_unit->getFaction() == FACTION_HOSTILE && (_unit->getTimeUnits() > _unit->getBaseStats()->tu / 2 || _unit->getCharging())) escapeOdds = 5` (:2682-2685);
           `ambushOdds = 12` (:2686); `combatOdds = 20` (:2687); `patrolOdds = _visibleEnemies ? 15 : 30` (:2689)
ДАННЫЕ:    ОВ ИСТИНА (своё), базовые ОВ РУЛСЕТ/статы; `_melee`, `_visibleEnemies`
RNG:       нет
СТОРОНЫ:   правило «ОВ больше половины → бегство 5» — **только враг**; у бота и нейтралов бегство 15 (12) при любых ОВ

### evaluateAIMode : наблюдают (AIModule.cpp:2692-2701)
УСЛОВИЕ:   `if (_spottingEnemies)`
РЕЗУЛЬТАТ: `patrolOdds = 0`; `if (_escapeTUs == 0)` → `setupEscape()` (:2695-2700)
RNG:       RNG HERE (внутри `setupEscape`): `RNG::shuffle` :1960 всегда при вызове; `RNG::generate` :1995-1996, :2016-2018 —
           по ходу перебора (см. `14_escape.md`). Вызывается, только если наблюдают и укрытие ещё не найдено (в `think`
           на :640 не звалось или не нашло)
ПРЕРЫВАНИЕ: побочные эффекты `setupEscape`: перезаписывает `_escapeAction`, `_escapeTUs`, через `selectNearestTarget`
           (:1940) — `_aggroTarget`, `_closestDist` и (у юнита только с ближним боем) `_attackAction.target` (:2430),
           хотя `setupAttack` этого think уже отработал
СТОРОНЫ:   оба

### evaluateAIMode : без засады (AIModule.cpp:2704-2711)
УСЛОВИЕ:   `if (!_rifle || _ambushTUs == 0)`
РЕЗУЛЬТАТ: `ambushOdds = 0`; `if (_melee) combatOdds *= 1.3`
СТОРОНЫ:   оба. Бот: `setupAmbush` не вызывается никогда (`_knownEnemies == 0`, :647) → `_ambushTUs == 0` → засада у бота
           всегда 0, и ветка ×1.3 срабатывает у любого бота с ближним оружием

### evaluateAIMode : знает врагов (AIModule.cpp:2714-2739)
УСЛОВИЕ:   `if (_knownEnemies)`:
           `if (_knownEnemies == 1) combatOdds *= 1.2` (:2716-2719);
           `if (_escapeTUs == 0)`: `if (selectClosestKnownEnemy())` → `setupEscape()` (:2723-2728), `else escapeOdds = 0` (:2729-2732)
           `else if (_unit->getFaction() == FACTION_HOSTILE) { combatOdds = 0; escapeOdds = 0; }` (:2735-2739)
ДАННЫЕ:    `selectClosestKnownEnemy` (:2336-2352): `validTarget(bu, true, false)` — порог 50, **гражданские не входят**;
           ближайший по `distance2d` к текущей позиции ИСТИНА
RNG:       RNG HERE: второй/третий `setupEscape` за think (:2726) — только у врага, если `_escapeTUs == 0` и есть известный
           не-гражданский. Вызывается **и когда юнита никто не наблюдает**
РЕЗУЛЬТАТ: см. условие. Если `setupEscape` здесь не нашёл укрытия, `escapeOdds` **не** обнуляется (обнуляется только
           при `selectClosestKnownEnemy() == false`)
СТОРОНЫ:   ветка `_knownEnemies` — только враг. У бота и нейтралов ни ×1.2, ни обнуления «никого не знаю», ни этого
           `setupEscape`: при пустом поле у бота остаются combat 20 и escape 15

Тонкость: если враг знает **только гражданских**, `_knownEnemies > 0`, но `selectClosestKnownEnemy()` = false →
`escapeOdds = 0`, а `combatOdds` не обнуляется.

### evaluateAIMode : инерция режима (AIModule.cpp:2742-2756)
РЕЗУЛЬТАТ: шанс **текущего** режима ×1.1: PATROL → `patrolOdds *= 1.1`, AMBUSH → `ambushOdds *= 1.1`, COMBAT →
           `combatOdds *= 1.1`, ESCAPE → `escapeOdds *= 1.1`
ДАННЫЕ:    `_AIMode` ПАМЯТЬ (между решениями и ходами, в сейве)

### evaluateAIMode : здоровье (AIModule.cpp:2759-2774)
УСЛОВИЕ / РЕЗУЛЬТАТ:
           `health < base/3` → escape ×1.7, combat ×0.6, ambush ×0.75;
           `else health < 2 * (base/3)` → escape ×1.4, combat ×0.8, ambush ×0.8;
           `else health < base` → escape ×1.1
ДАННЫЕ:    `getHealth()` ИСТИНА (своё), `getBaseStats()->health` РУЛСЕТ/статы. Оглушение (`getStunlevel`), смертельные
           раны, мораль, энергия **не читаются** (grep по :506-922, :2669-2933 пуст)

### evaluateAIMode : агрессия (AIModule.cpp:2777-2794)
РЕЗУЛЬТАТ: `aggression 0` → escape ×1.4, combat ×0.7; `1` → ambush ×1.1; `2` → combat ×1.4, escape ×0.7;
           иначе (≥3) → `combatOdds *= Clamp(1.2 + aggression/10.0, 0.1, 2.0)`,
           `escapeOdds *= Clamp(0.9 - aggression/10.0, 0.1, 2.0)`
ДАННЫЕ:    `getAggression()` РУЛСЕТ (`units.aggression`, по умолчанию 0 — `src/Mod/Unit.cpp:37`; у бойца-игрока
           константа 1 — `src/Savegame/BattleUnit.cpp:86`)

### evaluateAIMode : уже в бою (AIModule.cpp:2796-2799)
УСЛОВИЕ:   `if (_AIMode == AI_COMBAT)` → `ambushOdds *= 1.5`

### evaluateAIMode : наблюдатели (AIModule.cpp:2802-2810)
УСЛОВИЕ / РЕЗУЛЬТАТ:
           `if (_spottingEnemies)`: `escapeOdds = 10 * escapeOdds * (_spottingEnemies + 10) / 100;`
           `combatOdds = 5 * combatOdds * (_spottingEnemies + 20) / 100;`
           `else escapeOdds /= 2;`
Итог: при наблюдателях бегство ×(1.0+0.1·n), бой ×(1.0+0.05·n) — бегство растёт вдвое быстрее; без наблюдателей
бегство пополам.

### evaluateAIMode : видимые (AIModule.cpp:2813-2820)
УСЛОВИЕ:   `if (_visibleEnemies)`: `combatOdds = 10 * combatOdds * (_visibleEnemies + 10) / 100;`
           `if (_closestDist < 5) ambushOdds = 0;`

### evaluateAIMode : засада готова? (AIModule.cpp:2822-2829)
УСЛОВИЕ:   `if (_ambushTUs) ambushOdds *= 1.7; else ambushOdds = 0;`

### evaluateAIMode : тип миссии (AIModule.cpp:2832-2836)
УСЛОВИЕ:   `if (_save->getMissionType() == "STR_BASE_DEFENSE")` → escape ×0.75, ambush ×0.6

### evaluateAIMode : нечем драться (AIModule.cpp:2839-2843)
УСЛОВИЕ:   `if (!_melee && !_rifle && !_blaster && !_grenade && _unit->getBaseStats()->psiSkill == 0)` →
           `combatOdds = 0; ambushOdds = 0;`

### evaluateAIMode : бросок (AIModule.cpp:2845-2868)
RNG:       RNG HERE: `RNG::generate(1, std::max(1, patrolOdds + ambushOdds + escapeOdds + combatOdds))` :2845 —
           **всегда**, если не было возврата на :2674 (`generate` включительно с обеих сторон, `src/Engine/RNG.h:73`)
РЕЗУЛЬТАТ: интервалы в порядке **ESCAPE → AMBUSH → COMBAT → PATROL**:
           `decision <= escape` → ESCAPE; `<= escape+ambush` → AMBUSH; `<= escape+ambush+combat` → COMBAT; иначе PATROL.
           При сумме 0 бросок `generate(1,1) = 1`, `1 > 0` трижды → **PATROL**. Равенства «весов» не бывает —
           граница целочисленная, интервал нулевой ширины пропускается

### evaluateAIMode : принуждение (AIModule.cpp:2871-2874)
УСЛОВИЕ:   `(_unit->getFaction() == FACTION_HOSTILE && _save->isCheating()) || _unit->getCharging() != 0`
РЕЗУЛЬТАТ: `_AIMode = AI_COMBAT` (бросок уже израсходован)
СТОРОНЫ:   `isCheating` — только враг; charging — оба (сюда попадает charging при `_attackAction.type == BA_RETHINK`)
           `AiProbe::modeOdds` (:2875) — зонд записи, только пишет шансы и бросок

### evaluateAIMode : годность COMBAT (AIModule.cpp:2879-2909)
УСЛОВИЕ:   `xtile = _save->getTile(_attackAction.target)`; `throwingGrenadeOrProxy = type == BA_THROW && weapon && isGrenadeOrProxy()`
           - `if (xtile && (xtile->getUnit() || throwingGrenadeOrProxy))`:
               `if (_attackAction.type != BA_RETHINK) return;` (:2885-2888) — атака `setupAttack` остаётся;
               иначе `findFirePoint()` (:2890) → нашёл → return
           - `else`: `picked = selectRandomTarget(); found = picked && findFirePoint();` (:2899-2901) → нашёл → return
           - не вернулись → `_AIMode = AI_PATROL` (:2908)
ДАННЫЕ:    `_attackAction.target` — цель атаки этого think **или остаток прошлых** (`setupAttack` сбрасывает только тип,
           :1813); `xtile->getUnit()` ИСТИНА (любой юнит любой фракции на тайле)
RNG:       RNG HERE: `selectRandomTarget` :2368 — `RNG::generate(0,20)` на **каждую** годную цель (`validTarget(bu,true,true)`),
           только в ветке `else`; `findFirePoint` :3017 `RNG::shuffle` — только если `selectClosestKnownEnemy()` внутри
           нашёл цель (:3005-3006)
РЕЗУЛЬТАТ: COMBAT с атакой `setupAttack`, или с новой огневой точкой, или переход в PATROL
ПРЕРЫВАНИЕ: см. «ловушки» ниже
СТОРОНЫ:   оба

Ловушки этой проверки (доказаны кодом):
1. **Атака с пустым тайлом цели пересчитывается.** Если `setupAttack` выбрал действие, цель которого — тайл без юнита
   (ходьба к огневой точке `findFirePoint`: `BA_WALK` на пустую клетку), и не граната, то идёт ветка `else`:
   `selectRandomTarget` + новый `findFirePoint` (новый `shuffle`), а при неудаче — PATROL, хотя путь к огневой точке
   уже был. Бросок к цели ближнего боя защищён раньше (`charging`, :2671). Срабатывает, только если `evaluate` было
   истинно, то есть режим был не COMBAT (или вынужденная переоценка).
2. **Случайная цель не используется.** `selectRandomTarget` ставит `_aggroTarget`, но `findFirePoint` первым делом
   вызывает `selectClosestKnownEnemy()` (:3005) и переписывает `_aggroTarget`. Итог `selectRandomTarget` влияет только на
   (а) число бросков RNG и (б) отказ, когда годных целей нет вовсе (он берёт гражданских, `includeCivs=true`).
3. **Решение по устаревшей цели.** При `_attackAction.type == BA_RETHINK` ветка выбирается по тому, стоит ли сейчас
   кто-то на тайле старой цели (прошлый think, прошлый ход, клетка из `selectPointNearTarget`). От этого зависит,
   будут ли броски `selectRandomTarget`.
4. `findFirePoint` здесь вызывается и у юнита без огнестрела (проверки `_rifle` нет) — что он вернёт такому юниту, см.
   `12_combat_fire.md`.

### evaluateAIMode : годность PATROL (AIModule.cpp:2911-2923)
УСЛОВИЕ:   `if (_toNode || _foundBaseModuleToDestroy) return;` `if (_patrolAction.type == BA_SNAPSHOT) return;`
           иначе `_AIMode = AI_AMBUSH`
ДАННЫЕ:    `_toNode`, `_patrolAction` — итог `setupPatrol` этого think (:655-659)

### evaluateAIMode : годность AMBUSH (AIModule.cpp:2925-2932)
УСЛОВИЕ:   `if (_ambushTUs != 0) return;` иначе `_AIMode = AI_ESCAPE`

### evaluateAIMode : ESCAPE не проверяется
Проверки годности ESCAPE нет: функция заканчивается на :2933. ESCAPE может быть выбран броском или цепочкой
PATROL→AMBUSH→ESCAPE при `_escapeAction.type == BA_RETHINK` (укрытие не найдено) или при `_escapeAction`, который в
этом think **не пересчитывался** (см. раздел 7).

---

## 5. `tacticalMode` (AIModule.cpp:2941-2996)

Что это: правила стенда «опыт» (комментарий :2935-2940). Включается в `think` при
`tactical = AiProbe::tactics(_unit) || AiProbe::careful(_unit)` (:639, :743-746).
`tactics` = `OXCE_AI_TACTICS` и `FACTION_HOSTILE` (`AiProbe.cpp:361-365`) — **вне V4, у врага выключено**;
`careful` = `OXCE_AI_BOT` и `OXCE_AI_CAREFUL` и `FACTION_PLAYER` (`AiProbe.cpp:367-371`) — **у бота всегда**.
В сборке без `OXCE_AI_DEV` обе функции — заглушки `false` (`AiProbe.cpp:115-116`). Вызывается **после**
`evaluateAIMode` и после `_evalChosen`, то есть поверх броска.

### tacticalMode : не наблюдают (AIModule.cpp:2944-2947)
УСЛОВИЕ:   `!_spottingEnemies` → return (режим не трогается)

### tacticalMode : уже бегство (AIModule.cpp:2949-2953)
УСЛОВИЕ:   `_AIMode == AI_ESCAPE` → return

### tacticalMode : нет укрытия (AIModule.cpp:2955-2960)
УСЛОВИЕ:   `_escapeAction.type != BA_WALK || _escapeAction.target == _unit->getPosition() || getSpottingUnits(_escapeAction.target) >= _spottingEnemies`
ДАННЫЕ:    `_escapeAction` (бот считает его на :640 в каждом think, где его наблюдают); `getSpottingUnits` СТОРОНА+ИСТИНА
RNG:       нет (`getSpottingUnits` const, RNG не трогает)
РЕЗУЛЬТАТ: return — режим остаётся. «Укрытие» = клетка, которую видит строго меньше известных врагов, чем свою

### tacticalMode : ранен (AIModule.cpp:2961-2962)
`wounded = careful && (getFatalWounds() > 0 || getHealth() < base/2)` — у врага с TACTICS всегда `false`

### tacticalMode : засада (AIModule.cpp:2963-2968)
УСЛОВИЕ:   `_AIMode == AI_AMBUSH && !wounded` → return (у бота недостижимо — засады у него нет, раздел 6)

### tacticalMode : атакует (AIModule.cpp:2969-2992)
УСЛОВИЕ:   `attacking = _AIMode == AI_COMBAT && _attackAction.type != BA_RETHINK && _attackAction.type != BA_NONE`; `attacking && !wounded`:
           1. прицельный/очередь → снап: `left = TU - cost(type)`; если `left < _escapeTUs && snap.haveTU() && TU - snap.Time >= _escapeTUs` → `_attackAction.type = BA_SNAPSHOT` (:2972-2981)
           2. бот: `careful && weapon && type != BA_WALK && TU - cost(type).Time < _escapeTUs` → `_AIMode = AI_ESCAPE` («scoot», :2983-2989)
           3. иначе атака остаётся (:2990-2991)
ДАННЫЕ:    ОВ ИСТИНА (своё), стоимость действия РУЛСЕТ, `_escapeTUs` (ОВ пути к укрытию)
РЕЗУЛЬТАТ: снап вместо прицельного; или бегство вместо выстрела/удара, если после него не хватит ОВ дойти до укрытия.
           Ходьба к огневой точке (`BA_WALK`) под правило 2 не попадает. Энергия не проверяется

### tacticalMode : всё остальное (AIModule.cpp:2994-2995)
УСЛОВИЕ:   наблюдают, укрытие есть, и (PATROL, или COMBAT без атаки, или ранен в любом режиме кроме ESCAPE)
РЕЗУЛЬТАТ: `_AIMode = AI_ESCAPE`. Раненый бот уходит в укрытие **даже из готовой атаки**
СТОРОНЫ:   бот

---

## 6. Правки бота относительно врага (всё, что меняет выбор режима)

| что | враг (V4) | бот (V4, CAREFUL=1) | где |
|---|---|---|---|
| `_targetFaction` | `FACTION_PLAYER` (конструктор) | `FACTION_HOSTILE` перед каждым think | `AIModule.cpp:65-69`; `BattlescapeGame.cpp:425-430` |
| `_knownEnemies` | число известных целей | **всегда 0** | `AIModule.cpp:2183` |
| `setupAmbush` | при `_knownEnemies && !_melee && !_ambushTUs` | **никогда** → `_ambushTUs = 0` | `:647` |
| psi / бластер / снайпер в `setupAttack` | при `_knownEnemies` | **никогда** | `:1820-1847` |
| бегство «полные ОВ → 5» | да | нет: 15 (ближний бой 12) | `:2682-2685` |
| `combatOdds ×1.2` при одном известном, `setupEscape` по известным | да | нет | `:2714-2734` |
| обнуление combat/escape «никого не знаю» | да | **нет** (combat 20, escape 15/2 при пустом поле) | `:2735-2739` |
| `setupEscape` в `think` | только при `_escapeTUs == 0` | в **каждом** think, где наблюдают (`tactical`) | `:640` |
| переоценка в ESCAPE | только если не наблюдают или никого не знает | всегда | `:691` |
| `isCheating` → COMBAT | да | нет (переоценка при читах — да, :707 без фракции) | `:2871`, `:707` |
| `tacticalMode` | нет (TACTICS вне V4) | да | `:639`, `:743` |
| итоговые режимы | все четыре | PATROL, COMBAT, ESCAPE; **AMBUSH недостижим** (шанс 0, цепочка AMBUSH→ESCAPE) | `:2822-2829`, `:2925-2932` |
| `finalAction` ESCAPE/AMBUSH | ход юнита кончается (`dontReselect`), разворот на 180° | **не кончается**: в `UnitWalkBState::postPathProcedures` ветка только для `getFaction() != FACTION_PLAYER` | `src/Battlescape/UnitWalkBState.cpp:481-487, 504-509` |
| присед в атаке/засаде | `allowsKneeling(false)` — по броне | `allowsKneeling(true)` для типа `SOLDIER` | `:750`, `:816`, `:831` |

Вне V4 (у бота, если включить): `OXCE_AI_REVIVE`, `OXCE_AI_FLEE` — действие до всякого режима (:551-560);
`OXCE_AI_EVAL` — `evalFireAction` и `_evalChosen` → принудительный COMBAT (:738-741, :3813), при «eval.none»
`setupAttack` возвращает `BA_RETHINK` без обычной атаки и без `findFirePoint` (:3806-3810, :1851-1856);
`OXCE_AI_HALF` — урезание патрульной ходьбы (:843-865, `AiProbe.cpp:3551`); `OXCE_AI_ACTIONS` — больше двух
действий за выбор (`AiProbe.cpp:3826-3832`); `OXCE_AI_GAP`, `OXCE_AI_TURRET` — штрафы клеток бегства (14_escape).
`AiProbe::param` в функциях этой карточки не вызывается (только `OXCE_AI_TRACE_MELEE` в зонде `selectPointNearTarget`
:2410 и `OXCE_AI_EVAL_*` в `evalFireAction`, вне V4). `AiProbe::modeOdds` — только запись шансов в протокол
(`AiProbe.cpp:2386-2395`), RNG и состояние не трогает.

---

## 7. Порядок между режимами

### 7.1 Внутри одного решения (`think`)

```
                ┌────────────── подготовка кандидатов (до выбора режима) ──────────────┐
 входы :532-534 │ setupEscape?(:640)  setupAmbush?(:647)  setupAttack(:654)  setupPatrol(:655) │
                └──────────────────────────────────────────────────────────────────────┘
                                   │
                    psi готов? ──да──► действие пси, return (режим прежний)            :661-670
                                   │нет
                       evaluate? (:677-711) ──нет──► режим прежний ─────────────┐
                                   │да                                         │
                         evaluateAIMode                                        │
                           charging&&атака ──► COMBAT ─────────────────────────┤
                           [setupEscape ещё до 2 раз]                          │
                           бросок → E | A | C | P ; читы/charging → C           │
                           C: атака на тайле с юнитом/граната → C ─────────────┤
                              иначе findFirePoint → C | ↓                      │
                           P: _toNode/модуль/снап → P ──────────────────────────┤
                              иначе ↓                                          │
                           A: _ambushTUs → A ───────────────────────────────────┤
                              иначе ↓                                          │
                           E (без проверки) ────────────────────────────────────┤
                                                                               ▼
                       _evalChosen (вне V4) → C
                       tacticalMode (бот): P/C(без атаки)/ранен → E;  C(атака, мало ОВ на укрытие) → E
                                   │
                       действие режима → action                                   :752-835
                       BA_WALK на свой тайл → BA_NONE                              :874-877
```

Порядок `setup*` в `think` фиксирован (:640-659): **бегство → засада → атака → патруль**, все — до выбора режима.
Готовность кандидатов влияет на шансы так:
- `_escapeTUs` — только на то, будет ли ещё `setupEscape` внутри `evaluateAIMode` (в сам шанс бегства не входит);
- `_ambushTUs` — шанс засады ×1.7 или 0;
- итог `setupAttack` — на `evaluate` в COMBAT и на проверку годности COMBAT; в шансы боя не входит (кроме `_rifle` и др.);
- итог `setupPatrol` — на проверку годности PATROL.

Сколько раз за одно решение может вызваться `setupEscape`: до трёх — :640, :2698 (если первое не нашло), :2726 (если
и второе не нашло, только враг со знанием). Каждый вызов — новый `shuffle` и новые броски.

### 7.2 Между решениями в одном ходу юнита

- После действия `handleAI` вызывается снова для того же юнита, пока `_AIActionCounter < maxActions` (2 по умолчанию,
  `AiProbe.cpp:125`, `:3826-3832`), `reselectAllowed()` и юнит не очнулся в этот ход (`getTurnsSinceStunned() == 0` —
  юнит пропускается целиком, `BattlescapeGame.cpp:379`). ОВ ≤ 5 → `dontReselect()` (:375-378).
- Ходьба к огневой точке не тратит счётчик (`action->number -= 1`, :804-809), если хватает ОВ на снимок.
- `BA_RETHINK` (например, ESCAPE без укрытия: `action->type = _escapeAction.type = BA_RETHINK`, :756, :2160-2167) —
  второй полный think сразу (:449-453): все броски заново.
- Подобрал оружие → `setWeaponPickedUp()` (:1365) → третий think с вынужденной переоценкой (:695-699).
- Враг: ESCAPE и AMBUSH ставят `finalAction` (:759, :830) → после ходьбы `dontReselect()` (`UnitWalkBState.cpp:484-487`)
  и разворот при `isHiding()` (:504-509) — до конца хода решений у юнита больше нет. Бот — см. таблицу раздела 6: ход не
  заканчивается, следующий think возможен.
- Ходьба на другой тайл сбрасывает `_escapeTUs/_ambushTUs` (:867-873) → в следующем think укрытие и засада считаются
  заново.

### 7.3 Между ходами

| состояние | переживает ход? | где |
|---|---|---|
| `_AIMode` | да (и сейв) | `reset()` его не трогает (:162-170); load/save :180, :206 |
| `_escapeTUs`, `_ambushTUs`, `_walkAbortCounter` | нет | `reset()` из `SavedBattleGame::endTurn` при `_side == FACTION_PLAYER` (`SavedBattleGame.cpp:1547-1566`) |
| `_escapeAction`, `_ambushAction`, `_attackAction.target`, `_patrolAction` | да (поля объекта, `reset()` их не чистит) | `AIModule.h`, `:162-170` |
| `_toNode`, `_fromNode` | да (и сейв) | :180-198 |
| charging | да, пока цель жива | :564-567 |

Следствия:
- Враг, ушедший в ESCAPE, начинает следующий ход в ESCAPE; если его по-прежнему наблюдают и он кого-то знает — бежит
  снова **без броска** (:691), с новым `setupEscape` (:640, `_escapeTUs` сброшен).
- Инерция ×1.1 тянется через ходы.
- **Устаревшее бегство бота.** Бот без наблюдателей не вызывает `setupEscape` ни в `think` (:640 требует
  `_spottingEnemies`), ни в `evaluateAIMode` (:2692 и :2714 — наблюдатели или `_knownEnemies`, у бота 0). Но шанс бегства у
  него не 0 (15/2 = 7 при пустом поле). Выпал ESCAPE — исполняется `_escapeAction` из последнего вызова, возможно прошлого
  хода (`BA_WALK` к старой клетке против старой угрозы) или `BA_NONE` из конструктора (:61, `BattleActionCost()` →
  `BA_NONE`, `BattlescapeGame.h:53`). `tacticalMode` это не правит (выход на :2944). То же у нейтралов. У врага такое
  возможно только по цепочке PATROL→AMBUSH→ESCAPE, когда никого не знает и не наблюдают (шанс бегства тогда 0).

---

## 8. Особый вопрос: когда юнит идёт стрелять, а не бежать/прятаться/патрулировать

1. `setupAttack` выполняется **всегда** (:654) до выбора режима и сам решает, нужен ли `findFirePoint`:
   первая попытка — `else if (_spottingEnemies || _unit->getAggression() < RNG::generate(0, 3))` (:1904), только если
   ни пси, ни снайпер, ни обычная атака по видимому ничего не дали. При `aggression >= 3` условие `aggression < generate(0,3)`
   никогда не выполняется (максимум 3) — такой юнит ищет огневую точку здесь, **только если его наблюдают**; у
   `aggression 0/1/2` — с вероятностью 3/4, 1/2, 1/4. Бросок делается, только если не наблюдают.
2. Если режим уже COMBAT и `setupAttack` что-то нашёл (выстрел, удар, граната, ходьба к огневой точке) — переоценки
   нет (:688), идёт атака. Это главный путь «продолжать стрелять».
3. Иначе бросок `evaluateAIMode`; при COMBAT — проверка годности: атака с юнитом на тайле цели (или граната) остаётся,
   иначе вторая попытка `findFirePoint` (:2890 / :2901) **без** проверки агрессии и наблюдателей.
4. У врага `isCheating` → COMBAT принудительно после броска (:2871); charging → COMBAT без броска (:2671).
5. Бот: `tacticalMode` снимает атаку в пользу ESCAPE, если после неё ОВ меньше `_escapeTUs` (:2983) или боец ранен (:2961).

Что выбор режима учитывает и что нет:

| фактор | учитывается? | как / доказательство |
|---|---|---|
| число врагов, «видящих» клетку | да | `_spottingEnemies` (линия огня из глаз известных врагов ≤ 20 клеток): патруль 0, бегство ×(1+0.1n), бой ×(1+0.05n), n > 2 → вынужденная переоценка (:700) |
| число видимых врагов | да | `_visibleEnemies`: патруль 15 вместо 30, бой ×(1+0.1n), засада 0 при `_closestDist < 5` |
| число известных врагов | только враг | `_knownEnemies == 1` → бой ×1.2; 0 → бой и бегство 0 |
| угроза ближнего боя врага (досягаемость, оружие, ОВ врага) | **нет** | ни в шансах (:2677-2843), ни в `countKnownTargets`/`getSpottingUnits`/`selectNearestTarget`/`validTarget`/`getTargetAttackWeight` (:2179-2287, :4207-4280) нет чтения оружия, ОВ или пути врага; враг в упор без линии огня в «наблюдатели» не попадает |
| своё ближнее оружие | да | бегство 12 вместо 15; бой ×1.3 при отсутствии засады |
| ОВ | частично | только враг: ОВ > половины базовых → бегство 5 (:2682); бот: `tacticalMode` сравнивает ОВ после атаки с `_escapeTUs` |
| энергия | **нет** | `getEnergy` в :506-922, :2179-2290, :2669-2996 не вызывается |
| оглушение | **нет** (кроме пропуска очнувшегося юнита целиком, `BattlescapeGame.cpp:379`) | `getStunlevel` не читается; `getHealth()` без учёта оглушения |
| мораль | **нет** | `getMorale` не читается (паника — вне `AIModule`) |
| смертельные раны | только бот, в `tacticalMode` | :2962 |
| здоровье | да | три полосы (:2759-2774) и вынужденная переоценка < 2/3 (:701) |

---

## 9. Таблица «Числа»

| значение | выражение | файл:строка | на что влияет |
|---|---|---|---|
| 15 | `escapeOdds = 15` | AIModule.cpp:2677 | базовый шанс бегства |
| 12 | `escapeOdds = 12` при `_melee` | :2680 | бегство юнита с ближним оружием |
| 5 | `escapeOdds = 5` при HOSTILE и (`TU > base.tu/2` или charging) | :2684 | бегство врага с ОВ > половины (в начале хода — всегда) |
| 12 | `ambushOdds = 12` | :2686 | засада |
| 20 | `combatOdds = 20` | :2687 | бой |
| 15 / 30 | `patrolOdds = _visibleEnemies ? 15 : 30` | :2689 | патруль |
| 0 | `patrolOdds = 0` при наблюдателях | :2694 | патруль запрещён под наблюдением |
| ×1.3 | `combatOdds *= 1.3` (нет засады и `_melee`) | :2709 | бой ближнего боя |
| ×1.2 | `combatOdds *= 1.2` при `_knownEnemies == 1` | :2718 | бой против одиночки (враг) |
| 0 / 0 | `combatOdds = 0; escapeOdds = 0` HOSTILE без известных | :2737-2738 | |
| 0 | `escapeOdds = 0` при `_knownEnemies` и нет известного не-гражданского | :2731 | |
| ×1.1 | шанс текущего режима | :2745, :2748, :2751, :2754 | инерция |
| `< base/3` | escape ×1.7, combat ×0.6, ambush ×0.75 | :2759-2764 | тяжёлое ранение |
| `< 2*(base/3)` | escape ×1.4, combat ×0.8, ambush ×0.8 | :2765-2770 | среднее |
| `< base` | escape ×1.1 | :2771-2774 | лёгкое |
| aggr 0 | escape ×1.4, combat ×0.7 | :2779-2782 | |
| aggr 1 | ambush ×1.1 | :2783-2785 | |
| aggr 2 | combat ×1.4, escape ×0.7 | :2786-2789 | |
| aggr ≥3 | combat ×`Clamp(1.2 + a/10, 0.1, 2.0)`, escape ×`Clamp(0.9 - a/10, 0.1, 2.0)` | :2791-2792 | a=3: ×1.5/×0.6; a=8: ×2.0/×0.1 |
| ×1.5 | `ambushOdds *= 1.5` при COMBAT | :2798 | |
| `10·e·(n+10)/100` | бегство при n наблюдателях | :2804 | |
| `5·c·(n+20)/100` | бой при n наблюдателях | :2805 | |
| /2 | `escapeOdds /= 2` без наблюдателей | :2809 | |
| `10·c·(v+10)/100` | бой при v видимых | :2815 | |
| 5 | `_closestDist < 5 → ambushOdds = 0` | :2816-2819 | засада запрещена, если цель ближе 5 |
| ×1.7 / 0 | засада при `_ambushTUs` / без | :2824, :2828 | |
| ×0.75 / ×0.6 | escape / ambush при `STR_BASE_DEFENSE` | :2834-2835 | |
| 0 / 0 | combat / ambush без оружия, гранаты и `psiSkill` | :2841-2842 | |
| `generate(1, max(1, Σ))` | бросок режима | :2845 | порядок интервалов E, A, C, P |
| 10 % | `RNG::percent(10)` | :682 | переоценка в PATROL без контакта |
| > 2 | `_spottingEnemies > 2` | :700 | вынужденная переоценка |
| `< 2*health/3` | вынужденная переоценка | :701 | (иное округление, чем :2765) |
| 20 | `dist > 20 → continue` | :2211 | дальность «наблюдателя» (2D) |
| −2 | `originVoxel.z -= 2` | :2213 | точка глаз наблюдателя |
| 100 | `_closestDist = 100` нет цели | :2243 | |
| 255 | `minDist = 255` | :2339 | ближайший известный |
| `generate(0,20) − dist` | выбор случайной цели | :2368 | |
| 0 | `AIW_IGNORED` | AIModule.h:42 | порог «известен» при `includeCivs` |
| 50 | `ai.targetWeightThreatThreshold` (`Mod::getAITargetWeightThreatThreshold`) | src/Mod/Mod.h:247, Mod.cpp:3918 | порог «враг-угроза»; в Пиратках не задан (grep `targetweight` по *.rul пуст) |
| 100 / 50 / −200 / −100 | `targetWeightAsHostile` / `AsHostileCivilians` / `AsFriendly` / `AsNeutral` (мод; броня может переопределить `getValueOr`) | Mod.h:248-251; BattleUnit.cpp:3443-3446 | вес цели |
| `intelligence` | `_intelligence < turnsSinceSpotted → не знаю` | AIModule.cpp:4217 | память стороны; `units.intelligence` (Пиратки: 0–10, чаще 4); боец-игрок — константа 2 (BattleUnit.cpp:85) |
| `aggression` | `units.aggression` (`Unit::_aggression` по умолчанию 0, Unit.cpp:37) | BattleUnit.cpp:495 | Пиратки (415 из 446 юнитов задают): 1 — 134, 2 — 102, 0 — 72, 3 — 42, 8 — 31, 4 — 19, 5–7 — 15; боец-игрок 1 (BattleUnit.cpp:86) |
| 20 | `alienDeployments.cheatTurn` по умолчанию | AlienDeployment.cpp:42 | ход «читов»; в Пиратках задан только у `STR_MARS_THE_FINAL_ASSAULT_2` = 5 |
| `_cheatTurn/2`, ≤ 2 | `_turn > _cheatTurn/2 && liveAliens <= 2` | SavedBattleGame.cpp:1542 | ранние читы |
| `half`: `base.tu/2` | | AIModule.cpp:2682 | |
| 2 | `maxActions` | AiProbe.cpp:125, :3831 | действий за выбор юнита |

Все умножения `int *= double` усекаются к нулю после **каждого** шага (неявное преобразование при присваивании);
деления в :2804, :2805, :2815 — целочисленные. Порядок шагов поэтому важен. Поточечно, где двоичное представление
множителя (1.1, 1.4, 0.7…) может «потерять» единицу, не проверялось.

### Рассчитанные примеры (по формулам выше, с усечением на каждом шаге)

| случай | patrol | ambush | escape | combat | Σ | доли E / A / C / P |
|---|---|---|---|---|---|---|
| A. враг, огнестрел, aggr 1, здоров, ОВ полные, PATROL, не наблюдают, 1 видимый (1 известный), засады нет | 16 | 0 | 2 | 26 | 44 | 4.5 % / 0 / 59.1 % / 36.4 % |
| B. как A, но наблюдает 1 | 0 | 0 | 5 | 27 | 32 | 15.6 % / 0 / 84.4 % / 0 |
| C. как B, режим COMBAT (только при `setupAttack` = RETHINK) | 0 | 0 | 5 | 29 | 34 | 14.7 % / 0 / 85.3 % / 0 |
| D. враг, ОВ ≤ половины, здоровье < 2/3, aggr 0, COMBAT, наблюдают 2, видимых 2 | 0 | 0 | 34 | 14 | 48 | 70.8 % / 0 / 29.2 % / 0 |
| E. враг, засада готова, PATROL, не наблюдают, никого не видит, 1 известный, aggr 1 | 33 | 22 | 2 | 24 | 81 | 2.5 % / 27.2 % / 29.6 % / 40.7 % |
| F. враг никого не знает, не наблюдают, PATROL (переоценка лишь при `percent(10)`) | 33 | 0 | 0 | 0 | 33 | PATROL 100 % (бросок всё равно `generate(1,33)`) |
| G. бот, огнестрел, aggr 1, здоров, PATROL, не наблюдают, 1 видимый | 16 | 0 | 7 | 22 | 45 | 15.6 % / 0 / 48.9 % / 35.6 % |
| H. бот, как G, но наблюдает 1, режим COMBAT (атаки нет) | 0 | 0 | 16 | 25 | 41 | 39.0 % / 0 / 61.0 % / 0 (+ `tacticalMode`) |
| I. бот, никого не видит, не наблюдают, PATROL (переоценка при `percent(10)`) | 33 | 0 | 7 | 20 | 60 | 11.7 % / 0 / 33.3 % / 55.0 %; COMBAT → нет цели → PATROL; ESCAPE → устаревший `_escapeAction` (7.3) |

---

## 10. Таблица «RNG» (в порядке выполнения одного `think`, область карточки и вызываемое)

| # | файл:строка | вызов | что решает | когда вызывается |
|---|---|---|---|---|
| 0 | AIModule.cpp:370, :394, :404 | `RNG::percent` в `medikit_think` | аптечка/стимулятор (до `think`, `BattleUnit.cpp:3388-3400`) | раз за ход, при условиях аптечки — см. 15 |
| 1 | AIModule.cpp:1960 | `RNG::shuffle` | порядок клеток бегства | при вызове `setupEscape` на :640 (наблюдают и (`!_escapeTUs` или бот)) |
| 2 | :1995-1996, :2016-2018 | `RNG::generate` | сдвиг клетки бегства | внутри перебора `setupEscape`, по условиям — 14 |
| 3 | — | — | `setupAmbush` (:1630-1810) — в теле `RNG::` нет | при `_knownEnemies && !_melee && !_ambushTUs` |
| 4 | :4081, :4092, :4168 | `percent`, `percent`, `generate(35,155)` | пси-атака | в `setupAttack` при `_knownEnemies` (только враг) — 13 |
| 5 | :1839 | `RNG::percent(getSniperPercentage())` | снайперский выстрел | `_knownEnemies`, нет пси, не бластер, есть `getUnitRules()` |
| 6 | :2548 | `RNG::generate` | цель снайпера | внутри `sniperAction` |
| 7 | :4338 | `RNG::percent(meleeOdds)` | ближний или дальний | видим цель, есть и то и другое |
| 8 | :3884 | `RNG::generate` | режим огня (`extendedFireModeChoice`) | при включённом расширенном выборе — 12 |
| 9 | :1904 | `RNG::generate(0, 3)` | идти ли за огневой точкой | `_attackAction.type == BA_RETHINK` и **не** наблюдают |
| 10 | :3017 | `RNG::shuffle` | порядок клеток огневой точки | при вызове `findFirePoint` (после :1904) и найденном ближайшем известном |
| 11 | SavedBattleGame.cpp:2325, :2328, :2378 | `RNG::generate` | узел патруля (`getPatrolNode`) | в `setupPatrol` при поиске нового узла — 10 |
| 12 | AIModule.cpp:682 | `RNG::percent(10)` | переоценка режима | режим PATROL и `_spottingEnemies == _visibleEnemies == _knownEnemies == 0` |
| 13 | :1960 (+:1995…) | `setupEscape` | бегство | в `evaluateAIMode` :2698: наблюдают и `_escapeTUs == 0` |
| 14 | :1960 (+:1995…) | `setupEscape` | бегство | `evaluateAIMode` :2726: враг, `_knownEnemies`, `_escapeTUs == 0`, есть известный не-гражданский |
| 15 | :2845 | `RNG::generate(1, max(1, Σ))` | **режим** | всегда при вызове `evaluateAIMode`, кроме возврата на :2674 |
| 16 | :2368 | `RNG::generate(0,20)` × N годных целей | «случайная цель» (итог не используется, см. 4) | COMBAT, тайл старой цели без юнита и не граната |
| 17 | :3017 | `RNG::shuffle` | огневая точка | COMBAT-проверка (:2890 или :2901) |
| — | `tacticalMode` | нет | | |
| 18 | весь ряд снова | | | второй think на `BA_RETHINK` (`BattlescapeGame.cpp:449-453`), третий после подбора оружия (:478-483) |

Что легко сдвигает поток RNG (в пределах этой карточки):
- любой сдвиг в том, нашёл ли `setupAttack` действие, меняет, будет ли бросок режима вообще (COMBAT :688) и будет ли
  бросок :1904;
- найдено ли укрытие на :640 решает, будут ли ещё один-два полных `setupEscape` (каждый — `shuffle` всей сетки) внутри
  `evaluateAIMode`;
- `percent(10)` :682 срабатывает только при нулевых счётчиках — изменение, кто считается известным/видимым/наблюдающим,
  добавляет или убирает этот бросок;
- число бросков :2368 = число годных целей (включая гражданских) и зависит от того, кто стоит на тайле **старой**
  цели атаки;
- ESCAPE без укрытия даёт `BA_RETHINK` → второй полный think.

---

## 11. Таблица «Знание»

| вход решения | откуда | метка |
|---|---|---|
| кто «известен» (`validTarget`→`getTargetAttackWeight`) | `turnsSinceSpottedByFaction ≤ intelligence`, снайперский таймер споттеров | СТОРОНА; `isOut`, `getDangerous` — ИСТИНА; веса — РУЛСЕТ |
| `_knownEnemies` | число известных (только у врага) | СТОРОНА |
| `_visibleEnemies` | известные + `TileEngine::visible` из текущих позиций (без сектора обзора) + линия огня / путь до цели | СТОРОНА + ИСТИНА (геометрия по настоящим позициям) |
| `_spottingEnemies` | известные в 20 клетках + `canTargetUnit` из **текущих** глаз врага в тайл | СТОРОНА + ИСТИНА |
| `_closestDist` | последний `selectNearestTarget` | ИСТИНА (текущая позиция цели) |
| `selectClosestKnownEnemy` | ближайший известный по текущей позиции | СТОРОНА + ИСТИНА |
| `_escapeTUs`, `_ambushTUs` | итог `setupEscape`/`setupAmbush` этого хода | ПАМЯТЬ (в пределах хода, до сдвига) |
| `_AIMode` | прошлое решение/ход, сейв | ПАМЯТЬ |
| здоровье, ОВ, флаги оружия | своё состояние и инвентарь | ИСТИНА (своё); `_rifle/_melee` на :533 — ПАМЯТЬ (прошлый think) |
| базовые здоровье/ОВ, `psiSkill` | статы | РУЛСЕТ |
| `aggression`, `intelligence` | `units.aggression`, `units.intelligence`; боец-игрок 1/2 в коде | РУЛСЕТ |
| `getMissionType()` | тип миссии | РУЛСЕТ/состояние боя |
| `isCheating()` | номер хода и **число живых пришельцев** | ИСТИНА; `cheatTurn` — РУЛСЕТ |
| charging | `meleeAction` | ПАМЯТЬ |
| `_attackAction.type/target` | `setupAttack` этого think; target может быть старым | этот think / ПАМЯТЬ |
| `xtile->getUnit()` (годность COMBAT) | кто стоит на тайле | ИСТИНА |
| `_toNode`, `_patrolAction` | `setupPatrol` | ПАМЯТЬ / этот think |
| `_escapeAction` (ESCAPE, `tacticalMode`) | последний `setupEscape` — возможно прошлого хода | ПАМЯТЬ |
| `getFatalWounds()` (бот) | своё | ИСТИНА (своё) |

---

## 12. Слепые пятна (доказанные кодом)

1. **Угроза ближнего боя врага не входит в выбор режима.** В шансах (:2677-2843) и во всех входах (`countKnownTargets`
   :2179-2194, `getSpottingUnits` :2201-2233, `selectNearestTarget` :2240-2287, `selectClosestKnownEnemy` :2336-2352,
   `validTarget`/`getTargetAttackWeight` :4207-4280) нет чтения оружия, ОВ, энергии или пути врага. Враг ближнего боя
   рядом, но без линии огня в тайл, наблюдателем не считается.
2. **Энергия, оглушение, мораль не читаются** ни в `think` (:506-922), ни в `evaluateAIMode`, ни в `tacticalMode` (grep
   `getEnergy|getStun|getMorale` пуст; `getFatalWounds` — только :2962, бот).
3. **«Наблюдает» = линия огня, не зрение**: `getSpottingUnits` не смотрит направление взгляда, свет и дым, только
   трассу `canTargetUnit` и отсечку 20 клеток по горизонтали (без высоты). Неизвестный стороне враг, который реально
   видит юнита, не считается вовсе.
4. **`_visibleEnemies` у юнита без атаки = 0**: функция возвращает 0, если ни по одной видимой цели нет линии огня/пути
   (:2281-2286) — для шансов такой юнит «никого не видит» (патруль 30, бой без множителя видимых).
5. **`_visibleEnemies` на :533 по оружию прошлого think** (флаги и `_reachable` обновляются позже, :535-636, :550).
6. **Бот не знает врагов движком**: `_knownEnemies == 0` → нет засады, пси/снайпера/бластера в `setupAttack`, нет
   обнуления боя и бегства «никого не знаю», нет ×1.2, переоценка в ESCAPE каждый think.
7. **ESCAPE не проверяется на годность** (:2925-2933) и шанс бегства не обнуляется, если укрытия нет (:2723-2732): ESCAPE
   с `BA_RETHINK` → второй полный think; у бота без наблюдателей — исполнение устаревшего `_escapeAction`.
8. **Годность COMBAT проверяется по наличию юнита на тайле цели**, а не по типу действия: ходьба к огневой точке
   (пустой тайл) пересчитывается или теряется (:2883-2908); при `RETHINK` ветка выбирается по тайлу старой цели.
9. **`selectRandomTarget` в проверке COMBAT — мёртвый выбор**: `findFirePoint` переписывает `_aggroTarget` (:3005).
10. **Побочная запись `_attackAction.target`**: `setupEscape` внутри `evaluateAIMode` вызывает `selectNearestTarget`
    (:1940), которая у юнита только с ближним боем пишет `_attackAction.target` (:2430) уже после `setupAttack`.
11. **Шансы не знают, есть ли у патруля путь**: `patrolOdds` от `_toNode` не зависит; проверка — только после броска
    (:2913).
12. **Гражданские**: входят в `_knownEnemies`/`_visibleEnemies` врага (вес 50 > 0), но не в наблюдатели и не в
    ближайшего известного (порог 50) — один известный гражданский даёт бою ×1.2 и обнуляет бегство.
13. **Порог агрессии в `setupAttack` :1904**: при `aggression >= 3` первая попытка огневой точки без наблюдателей не
    делается никогда (`a < generate(0,3)` ложно), хотя шанс боя у таких юнитов выше.

---

## 13. Не прослежено

- Внутренности `setupEscape`, `setupAmbush`, `setupAttack` (кроме мест, где они меняют входы режима), `setupPatrol`,
  `findFirePoint` — карточки 10–14. В частности: что `findFirePoint` возвращает юниту без огнестрела, вызванный из
  проверки COMBAT (:2890, :2901).
- Что делает `handleAI`, если и второй think вернул `BA_RETHINK` (действие не ставится; как именно растёт
  `_AIActionCounter` до выхода к следующему юниту) — `01_pipeline.md`.
- `AiProbe::beforeThink` (`BattlescapeGame.cpp:446`) — не читал; если он меняет состояние юнита/RNG, это влияет на всё выше.
- Какие миссии Пираток имеют тип `STR_BASE_DEFENSE` (`getMissionType`) — не сверено с рулсетами.
- Ветка `UnitWalkBState::postPathProcedures` для бота при `!getPanicHandled()` (:524-528) — `30_execution.md`.
- Поточечная проверка усечения `int *= double` на двоичных представлениях множителей.
- Сколько раз за ход реально срабатывают ловушки 7.3 (устаревшее бегство бота) и 4 (пересчёт огневой точки) — нужен
  замер протоколом (`AiProbe::modeOdds` пишет шансы и бросок).
