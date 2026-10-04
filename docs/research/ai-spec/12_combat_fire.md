# COMBAT: стрельба — выбор цели, findFirePoint, режим огня, снайпер (AIModule)

Область: `src/Battlescape/AIModule.cpp`, коммит `7cd80e284`. Только чтение кода; номера строк сверены по текущему файлу.
Соседние области, на которые здесь только ссылки: 03 (выбор режима в `evaluateAIMode`), 13 (пси, бластер, граната,
`explosiveEfficacy`), 30/31 (исполнение ходьбы и путь, `setKnownOccupant`, BLOCKED_STEP), 40 (рулсеты).

Метки знания: **ИСТИНА** — истинное состояние мира (позиция, направление, клетка), **СТОРОНА** — что знает фракция
(`turnsSinceSpotted…ByFaction`), **ЮНИТ** — характеристики самого юнита, **ПАМЯТЬ** — поля AIModule, живущие между вызовами,
**РУЛСЕТ** — значения мода.

Флаги: V4 = AMBUSH_MEMO, BLOCKED_STEP, ESCAPE_REACH_FIRST, FAST, KNOWN_OCCUPANT_PATH_V2, LIGHTSKIP, LOADOUT_FIX,
PATROL_STUN_PREFIX, STALE_EXACT, STALE_PATROL_NODE, WALKFOV_SKIP; у бота CAREFUL=1; TACTICS выключен.
В этой области из V4 действует только **KNOWN_OCCUPANT_PATH_V2** (у врага). Остальные флаги, которые встречаются в коде
стрельбы, — **вне V4**: OXCE_AI_EVAL, OXCE_AI_FIREPOINT_BLOCKED (+ _V1_INTEROP, _SALT), OXCE_AI_FIREPOINT_TARGET_CELL,
OXCE_AI_FIREPOINT_ENERGY_PATH, OXCE_AI_KNOWN_OCCUPANT_PATH (V1), OXCE_AI_TACTICS.
В сборке без стенда (выпуск игрокам) все функции AiProbe — заглушки `false`/`0` (`src/Battlescape/AiProbe.cpp:115-147`),
то есть работает только ванильная ветка.

---

## 0. Ответ на главный вопрос — три формулы

### 0.1. Оценка точки огня (findFirePoint)

```
score(pos) = 100                                   // BASE_SYSTEMATIC_SUCCESS, AIModule.cpp:3019, 3094
           − 10 × N_видящих(pos)                   // getSpottingUnits(pos), :3094
           + (ОВ_сейчас − ОВ_пути_до_pos)          // :3095
           + 10, если pos ВНЕ конуса 90° цели      // !_aggroTarget->checkViewSector(pos), :3096-3099

если (у юнита нет waitIfOutsideWeaponRange) и (extendedFireModeChoice мода) и (оружие есть)
     и (цель СЕЙЧАС вне дальности оружия):         // :3102-3104
   score = score × ceil(dist3d_сейчас) / max(dist2d(pos, цель), 1)   // целочисленно, :3105-3109
```

- Принять точку: `bestScore > 70` (:3138). Клетка с оценкой ≤ 0 не выбирается никогда (стартовое `bestScore = 0`, :3023, сравнение `>` :3115).
- Порядок клеток — случайный (`RNG::shuffle`, :3017). Первая клетка с оценкой **> 125** обрывает поиск (:3121-3123):
  берётся не лучшая, а первая «очень хорошая» в случайном порядке.
- Случайного слагаемого в самой оценке нет. Случайность — только в порядке перебора.

Пример: ОВ 60, путь 12 ОВ, на клетку смотрит один враг, клетка за спиной цели:
`100 − 10·1 + (60 − 12) + 10 = 148` → больше 125, поиск остановлен на ней.
Пример отказа: ОВ 30, путь 24, видят трое, клетка в конусе цели: `100 − 30 + 6 + 0 = 76` → принята (> 70).
ОВ 30, путь 28, видят трое: `100 − 30 + 2 = 72` → принята; видят четверо: `62` → не принята.

Оружие вне дальности (Пиратки, extended включён): сейчас до цели 15 (3D), лимит оружия 10, клетка в 8 по плоскости:
`148 × 15 / 8 = 277`. Клетка дальше цели (dist2d 20): `148 × 15 / 20 = 111`.

### 0.2. Выбор цели

| Где | Кто годен | Как выбирается | Случайность |
|---|---|---|---|
| прямой выстрел (`selectNearestTarget`, :2240) | вес > 0 (вместе с гражданскими), клетка не «опасная», `TileEngine::visible` (без конуса обзора), есть линия огня из точки вылета оружия | минимальная `distance2d`, строго `<` (ничья → раньший в списке юнитов) | нет |
| точка огня (`selectClosestKnownEnemy`, :2336) | вес > 50 (только целевая фракция, без гражданских), клетка не «опасная» | минимальная `distance2d` по ИСТИННОЙ позиции, без видимости и линии огня | нет |
| запасной путь COMBAT (`selectRandomTarget`, :2359) | вес > 0 (с гражданскими), клетка не «опасная» | максимум `RNG::generate(0,20) − distance2d` | бросок на каждую годную цель |
| снайпер (`selectSpottedUnitForSniper`, :2495) | вес > 0, цель подсвечена споттерами фракции, у цели есть режим с оценкой > 0 | `RNG::generate(0, n−1)` — равновероятно | 1 бросок + броски в каждом `extendedFireModeChoice` |

«Вес» цели (`getTargetAttackWeight`, :4207-4251): своя фракция −200, враг целевой фракции 100, гражданский для врага 50,
нейтральная сторона −100; 0, если `_intelligence < turnsSinceSpottedByFaction` (цель «забыта»), кроме снайпера при
подсвеченной цели. Затем вес может переписать скрипт `AiCalculateTargetWeight` (:4243-4247).

### 0.3. Режим огня (extendedFireModeChoice, у Пираток)

```
кандидаты (по порядку): AIMED, AUTO, SNAP, THROW — только те, на которые хватает ОВ и энергии сейчас (haveTU, :3840-3855)
база(режим) = точность × выстрелов × базовыеОВ_юнита / ОВ_режима            // scoreFiringMode, :2663
   точность = getFiringAccuracy − dropoff × (выход за лимит дальности)       // :2582-2597
   вне maxRange → точность 0                                                // :2600-2606
   нет линии огня (только при checkLOF) → 0                                 // :2641-2658
оценка = база × (100 + RNG::generate(−I, +I)) / 100,  I = 5 × max(10 − интеллект, 0)    // :3883-3884
для AUTO: оценка × (100 + (агрессия − 1) × 5) / 100                         // :3888-3890
выбор: строго больший; старт 0 → при всех ≤ 0 тип RETHINK                   // :3893-3897
```

Пример (интеллект 3 → I = 35; агрессия 2): винтовка, точность aimed 110 / snap 60 / auto 35×3 выстрела,
ОВ юнита 60, стоимости 30/15/20:
AIMED `110·1·60/30 = 220`, AUTO `35·3·60/20 = 315`, SNAP `60·1·60/15 = 240`.
Броски, например, −20 %, +10 %, +30 %: AIMED 176, AUTO `346 × 105/100 = 363`, SNAP 312 → **AUTO**.
Урон, броня цели, шанс убийства и ОВ на отход в формуле **не участвуют**.

---

## 1. Дерево вызовов

```
AIModule::think (:506)
├─ :529  _attackAction.weapon = action->weapon            (оружие основной руки)
├─ :532  _knownEnemies   = countKnownTargets()            (только у FACTION_HOSTILE; у бота 0)
├─ :533  _visibleEnemies = selectNearestTarget()          (на _rifle/_melee ПРОШЛОГО вызова)
├─ :534  _spottingEnemies = getSpottingUnits(свою позицию)
├─ :550  _reachable = findReachable(ОВ, энергия целиком)
├─ :605-631 оружие → _blaster | _rifle | _melee + reachableWithAttack(AIMED | SNAPSHOT | HIT)
├─ :636  _grenade
├─ :654  setupAttack (:1811)
│   ├─ :1820 if _knownEnemies
│   │   ├─ :1823 psiAction                               → область 13
│   │   ├─ :1830 _blaster → wayPointAction               → область 13
│   │   └─ :1836 есть unitRules → :1839 RNG::percent(sniper) → :1842 sniperAction (:3472)
│   │                                                           └─ selectSpottedUnitForSniper (:2495)
│   │                                                               └─ extendedFireModeChoice(checkLOF=true) на каждую цель
│   ├─ :1849 evalFireAction (вне V4)
│   ├─ :1862 selectNearestTarget (:2240) — прямой выстрел
│   │   ├─ :1867 selectMeleeOrRanged (:4295)  при _melee && _rifle
│   │   ├─ :1872 grenadeAction                 при _grenade      → область 13
│   │   ├─ :1878 meleeAction                   при _melee        → область 13
│   │   └─ :1884 projectileAction (:3493)      при _rifle
│   │       └─ :3536 extendedFireModeChoice(checkLOF=false)  (Пиратки) | ванильная таблица :3553-3600
│   ├─ :1889 тип != RETHINK → return
│   └─ :1904 _spottingEnemies || агрессия < RNG::generate(0,3)
│       └─ :1908 findFirePoint (:3003)
│           ├─ :3005 selectClosestKnownEnemy (:2336)
│           ├─ :3017 RNG::shuffle(121 смещение)
│           └─ на каждую клетку: canTargetUnit → calculateKnownOccupantV2 → Pathfinding::calculate
│                                 → getSpottingUnits(pos) → checkViewSector
├─ :714 evaluateAIMode (:2669) → ветка COMBAT (:2879-2908)
│   ├─ :2883 на клетке цели юнит/бросок гранаты: тип != RETHINK → оставить; иначе :2890 findFirePoint
│   └─ :2897 иначе: selectRandomTarget (:2359, вызов :2899) + :2901 findFirePoint (повторно); неудача → AI_PATROL (:2908)
├─ :743 tacticalMode (:2941) — только при CAREFUL (бот) или TACTICS (вне V4)
├─ :748 _reserve = BA_NONE; :769-783 резерв по агрессии только в PATROL
└─ :790-821 AI_COMBAT → action (тип, цель, оружие, finalFacing, kneel, счётчик хода к точке огня)
```

`getReserveMode` (:4286) и `getTarget` (:4403) — геттеры, читаются вне модуля (см. D-24, D-25).

---

## 2. Развилки

### D-01. Устаревшие флаги оружия в selectNearestTarget из think
- УСЛОВИЕ: вызов `selectNearestTarget()` в `think` на :533 стоит раньше `_rifle = false` (:536), раньше `_melee = …` (:535) и раньше пересчёта `_reachable` (:550).
- ДАННЫЕ: ПАМЯТЬ — `_rifle`, `_melee`, `_reachable` от прошлого вызова `think` этого юнита.
- RNG: нет.
- РЕЗУЛЬТАТ: `_visibleEnemies` и `_aggroTarget` первого вызова считаются по ветке прошлого вызова (:2256 `if (_rifle || !_melee)`); в ветке ближнего боя `selectPointNearTarget` ищет клетку в старом `_reachable` (:2403).
- ПРЕРЫВАНИЕ / ВОЗВРАТ: нет; `setupAttack` вызывает `selectNearestTarget` второй раз уже со свежими флагами (:1862).
- СТОРОНЫ: враг и бот одинаково.

### D-02. Оружие основной руки
- УСЛОВИЕ: `if (action->weapon)` (:605) → `if (_save->canUseWeapon(action->weapon, _unit, false, BA_NONE))` (:608); `BT_FIREARM` (:610): `getCurrentWaypoints() != 0` → `_blaster` (:612-615), иначе `_rifle` (:618-620); `BT_MELEE` → `_melee` (:623-626). Иначе `action->weapon = 0` (:631).
- ДАННЫЕ: ЮНИТ (предмет в руке), РУЛСЕТ (тип оружия). Боеприпас здесь не проверяется (комментарий :608).
- RNG: нет.
- РЕЗУЛЬТАТ: `_reachableWithAttack = findReachable(cost)` с бюджетом «ОВ − стоимость SNAPSHOT (AIMED у бластера, HIT у ближнего)» и «энергия − её стоимость» (`reachableWithAttack`, :939-945).
- Важно: если годного оружия нет, `_reachableWithAttack` **не обновляется** и остаётся от прошлого вызова (ПАМЯТЬ). `_attackAction.weapon` уже присвоен на :529 и при непригодном оружии не обнуляется (обнуляется только `action->weapon`, :631).
- СТОРОНЫ: обе.

### D-03. Порядок попыток в setupAttack
- УСЛОВИЕ: сброс `_attackAction.type = BA_RETHINK; _psiAction.type = BA_NONE; _evalChosen = false` (:1813-1815).
- `if (_knownEnemies)` (:1820) → пси (:1823; при успехе `return`, :1825-1829) → `if (_blaster)` wayPointAction (:1830-1835) → `else if (_unit->getUnitRules())` (:1836) → снайпер (D-04).
- `if (!sniperAttack && _rifle && AiProbe::evalFire(_unit))` (:1849) → evalFireAction (вне V4).
- `if (!sniperAttack && selectNearestTarget())` (:1862) → выбор оружия и атака (D-08…D-11).
- `if (_attackAction.type != BA_RETHINK) return;` (:1889-1903).
- `else if (_spottingEnemies || _unit->getAggression() < RNG::generate(0, 3))` (:1904) → findFirePoint (:1908).
- ДАННЫЕ: ПАМЯТЬ (`_knownEnemies`, `_rifle`, `_melee`, `_grenade`, `_blaster`, `_spottingEnemies`), ЮНИТ (агрессия).
- СТОРОНЫ: у бота `_knownEnemies = 0` всегда (D-26), поэтому пси/бластер/снайпер у бота не вызываются.

### D-04. Бросок снайпера
- УСЛОВИЕ: `if (RNG::percent(_unit->getUnitRules()->getSniperPercentage()))` (:1839).
- ДАННЫЕ: РУЛСЕТ — `sniper` юнита (у Пираток задан у 169 из 446 юнитов: 25/33/50/75 и т. д., у остальных 0).
- RNG HERE: `RNG::percent` AIModule.cpp:1839 — **всегда**, когда `_knownEnemies > 0`, пси не сработала, нет бластера и у юнита есть unitRules; бросок тратится и при `sniper = 0` (`percent` = `generate(0,99) < v`, `src/Engine/RNG.h:52-55`).
- РЕЗУЛЬТАТ: успех → `sniperAttack = sniperAction()` (:1842).
- СТОРОНЫ: только враг (у солдат под контролем разума нет unitRules — комментарий :1836).

### D-05. sniperAction / selectSpottedUnitForSniper
- УСЛОВИЕ (:2522): `validTarget(bu, true, true) && bu->getTurnsLeftSpottedForSnipersByFaction(_unit->getFaction())`.
- ДАННЫЕ: СТОРОНА (подсветка споттерами), ИСТИНА (`_attackAction.target = bu->getPosition()`, :2525-2527), ЮНИТ (ОВ).
- Стоимости: AUTO/SNAP/AIMED (:2503-2505), бросок гранаты только при `_grenade`: бросок + 4 + взвод (:2509-2517).
- На каждую годную цель: `extendedFireModeChoice(…, true)` (:2528) — **независимо** от флага мода `extendedFireModeChoice`, с проверкой линии огня. Цель с итоговым типом не RETHINK попадает в список (:2530-2539).
- RNG HERE: в каждом `extendedFireModeChoice` — по броску на каждый доступный режим (D-13); затем `RNG::generate(0, numberOfTargets - 1)` AIModule.cpp:2548 — только при непустом списке.
- РЕЗУЛЬТАТ: выбранная цель → `_aggroTarget`, `_attackAction` (:2549-2552). Пустой список → `_aggroTarget = 0`, тип RETHINK, оружие — основная рука (:2554-2559).
- ВОЗВРАТ: sniperAction при успехе ставит `_visibleEnemies = max(_visibleEnemies, 1)` (:3478) и возвращает true (:3472-3486).
- СТОРОНЫ: только враг.

### D-06. Прямой выстрел: кто годен (selectNearestTarget)
- УСЛОВИЕ: `validTarget(bu, true, true) && _save->getTileEngine()->visible(_unit, bu->getTile())` (:2248-2249); `dist < _closestDist` (:2253), стартовое `_closestDist = 100` (:2243).
- Линия огня: `if (_rifle || !_melee)` (:2256) — `canTargetUnit` из `getOriginVoxel(action, 0)` с `action.weapon = _attackAction.weapon` (:2258-2263). Иначе (только ближний бой) — `selectPointNearTarget(bu, ОВ)` и `validMeleeRange` (:2267-2271).
- ДАННЫЕ: ИСТИНА (позиции, `visible`), СТОРОНА (через вес — «не забыта»), ЮНИТ.
- `TileEngine::visible` учитывает дальность, свет/дым/огонь и линию взгляда, но не конус обзора (`TileEngine.cpp:1864`).
- RNG: нет.
- ВОЗВРАТ: число видимых годных целей (`tally`, :2251) — **только если** хотя бы одна прошла линию огня (:2282-2286), иначе 0. `_aggroTarget` — ближайшая с линией огня.
- Побочный эффект: ветка ближнего боя пишет `_attackAction.target` (через `selectPointNearTarget`, :2428).
- СТОРОНЫ: обе.

### D-07. selectPointNearTarget (клетка для удара, вызывается из D-06)
- УСЛОВИЕ: перебор z −1..1, x и y от `−size` до `sizeTarget` вокруг цели (:2394-2399); клетка в `_reachable` (:2403); `validMeleeRange` (:2406); клетка не опасная (:2417); путь `calculate(…, BAM_NORMAL, 0, maxTUs)` (:2419) с `start != −1` (:2428).
- Оценка: `distanceCurrent = path.size() − dodgeChanceDiff × getArcDirection(dir − 4, dirTarget)` (:2422), где `dodgeChanceDiff = meleeDodge × backPenalty × diff / 160` (:2391). Меньше — лучше.
- ДАННЫЕ: ИСТИНА (позиция и направление цели), ЮНИТ, ПАМЯТЬ (`_reachable`).
- RNG: нет (на :2410 — зонд трассировки).
- СТОРОНЫ: обе.

### D-08. selectMeleeOrRanged (только при `_melee && _rifle`) — часть дальнего боя
- УСЛОВИЕ: нет ближнего оружия или заряда → `_melee = false` (:4300-4304); нет дальнего или боеприпаса → `_rifle = false` (:4306-4309).
- Шанс ближнего: `meleeOdds = 10` (:4314); урон ближнего > 50 → `+ (урон − 50) / 2` (:4316-4320); `− 20 × (_visibleEnemies − 1)` (:4322-4324).
- `if (meleeOdds > 0 && HP ≥ 2/3 HP)` (:4327): агрессия 0 → −20, агрессия > 1 → +10 × агрессия (:4329-4335); `RNG::percent(meleeOdds)` (:4338).
- RNG HERE: `RNG::percent` AIModule.cpp:4338 — **только** при `meleeOdds > 0` и здоровье ≥ 2/3 после всех поправок до агрессии.
- РЕЗУЛЬТАТ: успех → ближний (`_rifle = false`, `reachableWithAttack(HIT)`, :4340-4343). Иначе → `_melee = false` (:4346), дальний бой.
- СТОРОНЫ: обе.

### D-09. Граната раньше выстрела
- УСЛОВИЕ: `if (_grenade) grenadeAction();` (:1869-1874) стоит до `if (_rifle) projectileAction();` (:1881-1886).
- РЕЗУЛЬТАТ: при решении бросить `grenadeAction` ставит `_rifle = _melee = false` (:3970-3971) — выстрел не рассматривается. Детали броска — область 13.

### D-10. projectileAction: годность режима
- УСЛОВИЕ: цель = `_aggroTarget->getPosition()` (:3495, ИСТИНА); тип сбрасывается в RETHINK (:3517).
- testEffect (:3496-3514): у режима, на который хватает ОВ, нет боеприпаса → `clearTU`; у взрывчатки `explosiveEfficacy(...) == 0` → `clearTU` (:3507-3511). `clearTU` делает `haveTU` ложным, режим выпадает.
- RNG: в testEffect нет (explosiveEfficacy без RNG — область 13).
- СТОРОНЫ: обе.

### D-11. projectileAction: extended или ваниль
- УСЛОВИЕ: `waitIfOutsideWeaponRange = getGeoscapeSoldier() ? false : getUnitRules()->waitIfOutsideWeaponRange()` (:3528); `if (!waitIfOutsideWeaponRange && extendedFireModeChoiceEnabled)` (:3532) → `extendedFireModeChoice(costAuto, costSnap, costAimed, costThrow /*пустой*/, false)` (:3536), `return`.
- ДАННЫЕ: РУЛСЕТ — `ai.extendedFireModeChoice` (у Пираток `true`, `Piratez_Globals.rul:9155`), `waitIfOutsideWeaponRange` (у Пираток не задан ни у одного юнита).
- Пустой `costThrow` даёт `haveTU() == false` (`BattlescapeGame.cpp:104-107`) — бросок в прямом выстреле не рассматривается.
- Ваниль (когда extended выключен): `respectMaxRange` и цель вне дальности → `return` с RETHINK (:3541-3549); `dist2d < 4`: AUTO, иначе при отсутствии SNAP — AIMED, иначе SNAP (:3553-3570); `> 12`: AIMED, иначе SNAP при `< 20` (:3573-3585); затем SNAP, AIMED, AUTO (:3587-3600).
- RNG: в ванильной таблице нет; в extended — D-13.
- СТОРОНЫ: обе (у бота `getGeoscapeSoldier() != 0` → wait = false).

### D-12. scoreFiringMode
- УСЛОВИЕ: нет типа или оружия → 0 (:2575-2578).
- Точность: `getFiringAccuracy(GetBeforeShoot(action))` (:2582); дистанция `ceil(sqrt(distance3dToUnitSq(target)))` (:2583-2584) — **от текущей позиции юнита**.
- Лимиты: `calculateLimits(upper, lower, depth, type)` (:2588): `upper` — aimRange, а при `battleUFOExtenderAccuracy` для SNAP/AUTO — snapRange/autoRange; `lower` — minRange; возвращает dropoff (`RuleItem.cpp:2386-2410`). `distance > upper` → `accuracy −= (distance − upper) × dropoff`; `distance < lower` → `accuracy −= (lower − distance) × dropoff` (:2590-2597). Точность может уйти в минус.
- Вне дальности (`isOutOfThrowRange` для броска, иначе `isOutOfRange(distSq)`, `RuleItem.cpp:2290`) → `accuracy = 0` (:2600-2607).
- Выстрелов: из конфигурации AIMED/SNAP/AUTO, иначе 1 (:2609-2621).
- `tuCost = getActionTUs(type, weapon).Time` (:2623); бросок гранаты: + 4 + взвод (:2625-2632); `tuTotal = getBaseStats()->tu` (:2633); `!tuCost` → 0 (:2636-2639).
- `if (checkLOF)` (:2641): навесной или бросок → `validateThrow` (:2646-2652); иначе `canTargetUnit(origin, target tile, …, _unit, false, target)` (:2654-2657); провал → 0.
- ВОЗВРАТ: `accuracy * numberOfShots * tuTotal / tuCost` (:2663).
- ДАННЫЕ: ИСТИНА (дистанция до цели), ЮНИТ, РУЛСЕТ.
- RNG: нет.

### D-13. extendedFireModeChoice
- Кандидаты в порядке: AIMED (`costAimed.haveTU()`, :3840), AUTO (:3844), SNAP (:3848), THROW (:3852). THROW без `_grenade` → `continue` до броска (:3862-3871).
- `newScore = scoreFiringMode(&testAction, _aggroTarget, checkLOF)` (:3878).
- RNG HERE: `RNG::generate(-intelligenceModifier, intelligenceModifier)` AIModule.cpp:3884 — **на каждый** кандидат, прошедший `haveTU` (и THROW с гранатой), даже при `intelligenceModifier = 0` (`generate` всегда вызывает `next()`, `RNG.cpp:90-93`).
- `intelligenceModifier = getAIFireChoiceIntelCoeff() * max(10 − getIntelligence(), 0)` (:3883): коэффициент 5 по умолчанию (`Mod.cpp:442`), Пиратки не меняют.
- AUTO: `× (100 + (getAggression() − 1) × getAIFireChoiceAggroCoeff()) / 100` (:3888-3891), коэффициент 5.
- `if (newScore > score)` (:3893), старт `score = 0`, `chosenAction = BA_RETHINK`.
- ВОЗВРАТ: `_probeScore = score; _attackAction.type = chosenAction` (:3905-3906). Все оценки ≤ 0 → RETHINK.
- ДАННЫЕ: ЮНИТ (интеллект, агрессия, ОВ), РУЛСЕТ, ИСТИНА (через scoreFiringMode).
- СТОРОНЫ: обе. Бот: интеллект 2, агрессия 1 (`BattleUnit.cpp:85-86`) → I = 40 (±40 %), множитель AUTO = 1.

### D-14. Ветка поиска точки огня
- УСЛОВИЕ: `else if (_spottingEnemies || _unit->getAggression() < RNG::generate(0, 3))` (:1904).
- RNG HERE: `RNG::generate(0, 3)` AIModule.cpp:1904 — **только** при `_spottingEnemies == 0` (короткое замыкание `||`) и только если до этого тип остался RETHINK.
- Вероятность прохода без видящих: агрессия 0 → 75 %, 1 → 50 %, 2 → 25 %, ≥ 3 → 0 % (у Пираток агрессия ≥ 3 у 107 из 446 юнитов: такие без «видящих» точку огня здесь не ищут никогда). Чем агрессивнее, тем реже — так в коде.
- СТОРОНЫ: бот (агрессия 1) — 50 %.

### D-15. findFirePoint: цель
- УСЛОВИЕ: `if (!selectClosestKnownEnemy()) return false;` (:3005-3006) — **до** перемешивания, бросков нет.
- `selectClosestKnownEnemy` (:2336-2353): `validTarget(bu, true, false)` — вес > 50 (без гражданских), минимальная `distance2d(bu->getPosition(), …)`, старт 255, строго `<`.
- ДАННЫЕ: СТОРОНА (допуск через «не забыта»), ИСТИНА (позиция).
- Цель findFirePoint может не совпадать с целью прямого выстрела (D-06): здесь нужна не видимость, а только память стороны.

### D-16. findFirePoint: KNOWN_OCCUPANT_PATH_V2 (V4, враг)
- УСЛОВИЕ: `knownOccupantV2(ko2Old)` (:3009) → цель, если `knownOccupantPathV2()` и юнит HOSTILE и `_aggroTarget->getTurnsSinceSpottedByFaction(faction) == 0` (:1091-1098); иначе 0.
- РЕЗУЛЬТАТ: в каждом расчёте пути клетка цели заблокирована (`calculateKnownOccupantV2`, :1106-1118). Без цели — обычный `calculate(_unit, pos, BAM_NORMAL)`.
- ДАННЫЕ: СТОРОНА (замечена в этот ход).
- СТОРОНЫ: враг при V4 — да; бот — нет (не HOSTILE); без стенда — нет.

### D-17. findFirePoint: перемешивание
- `randomTileSearch = _save->getTileSearch()` — 121 смещение x, y ∈ [−5..5], z = 0 (`SavedBattleGame.cpp:79-84`).
- RNG HERE: `RNG::shuffle` AIModule.cpp:3017 — **всегда**, если цель найдена: 120 вызовов `generate(0, i)` (`RNG.h:83-89`).

### D-18. findFirePoint: подавление заблокированной точки (вне V4)
- `suppress = _fpBlocked && firepointBlockedHolds()` (:3027). `_fpBlocked` ставит только `recordFirepointBlockedAttempt` (:982), которую зовут `firepointWalkBlocked` (из `AiProbe::firepointBlocked`, нужен `OXCE_AI_FIREPOINT_BLOCKED`, `AiProbe.cpp:4004-4010`) и `firepointStepSuppressed` (нужны `OXCE_AI_FIREPOINT_BLOCKED` и `_V1_INTEROP`, `AiProbe.cpp:4446-4450`).
- `recordFirepointBlockedAttempt` (:971-993): записывает, только если `_firepointChosen && action.type == BA_WALK && action.target == _firepointChosenAt`; запоминает точку, шаг, позицию, ОВ, ход, цель, позицию цели, ревизию знания.
- `firepointBlockedHolds` (:999-1035): запись держится, если совпадают ход, позиция, ОВ, цель, её позиция и ревизия знания; иначе запись сбрасывается.
- При suppress клетка, путь к которой начинается тем же шагом `_fpBlockedDir`, пропускается (:3082-3093).
- В V4 `_fpBlocked` не ставится → `suppress = false`. Работает при V4 вместо этого BLOCKED_STEP — вне findFirePoint (область 30/31).

### D-19. findFirePoint: сброс типа
- `_attackAction.type = BA_RETHINK;` (:3035) — до цикла, при любом исходе. Неудача findFirePoint оставляет RETHINK, а `_attackAction.target` — лучшую оценённую клетку (или прежнюю цель, если ни одна не оценена).

### D-20. findFirePoint: фильтр клетки
- `pos = позиция юнита + смещение` (:3038); `tile == 0` или клетки нет в `_reachableWithAttack` → пропуск (:3040-3042).
- `skipTargetCell` (`OXCE_AI_FIREPOINT_TARGET_CELL`, вне V4): клетки, где стоит цель, пропускаются (:3043-3060).
- Точка вылета: `pos.toVoxel() + (8, 8, height + floatHeight − terrainLevel − 4)` (:3064-3066); размер юнита не учитывается.
- `canTargetUnit(&origin, _aggroTarget->getTile(), &target, _unit, false)` (:3068) — линия огня до ИСТИННОЙ клетки цели.
- `calculateKnownOccupantV2(pos, ko2, …)` (:3070) → `Pathfinding::calculate(_unit, pos, BAM_NORMAL)` — maxTUCost по умолчанию 1000 (`Pathfinding.h:243`).
- `getStartDirection() != −1` (:3072); пустой путь (своя клетка) → −1 (`Pathfinding.cpp:939-943`).
- `firepointPathOver` (`OXCE_AI_FIREPOINT_ENERGY_PATH`, вне V4; без него 0): путь по энергии сверх бюджета → пропуск (:3075-3081).
- RNG: нет. ДАННЫЕ: ИСТИНА (клетка цели, проходимость), ПАМЯТЬ (`_reachableWithAttack`).

### D-21. findFirePoint: оценка и выбор
- `score = 100 − getSpottingUnits(pos) * 10` (:3094); `+= ОВ − getTotalTUCost()` (:3095); `+10`, если `!_aggroTarget->checkViewSector(pos)` (:3096-3099).
- Поправка дальности (:3102-3110) — см. 0.1. Условие `isOutOfRange` считается от **текущего** расстояния юнита до цели, а не от `pos`.
- `if (score > bestScore)` (:3115) → цель, `finalFacing = getDirectionTo(pos, позиция цели)` (:3117-3120); `if (score > FAST_PASS_THRESHOLD)` (125) → `break` (:3121-3123).
- `if (bestScore > 70)` (:3138) → `type = BA_WALK`, `_firepointChosen = true`, `_firepointChosenAt`, `_ko2FpChosenTarget` (:3140-3144), `return true` (:3153). Иначе `false` (:3160).
- ДАННЫЕ: ИСТИНА (направление цели в `checkViewSector`, `BattleUnit.cpp:5198`; позиции видящих), СТОРОНА (кто считается видящим — через вес), ЮНИТ (ОВ).

### D-22. getSpottingUnits (штраф за видимость)
- `checking = pos != позиция юнита` (:2204).
- На каждого юнита: `validTarget(bu, false, false)` (:2208) — вес > 50 (без гражданских), опасная клетка не проверяется.
- `distance2d > 20` → пропуск (:2210-2211). Точка глаз бойца — z − 2 (:2213).
- `canTargetUnit(origin, tile(pos), …, bu, false, _unit)` (:2218 при `checking`, иначе :2225) — только линия огня. Конуса обзора, света, дыма, ночного зрения нет (`canTargetUnit`, `TileEngine.cpp:2196`).
- ДАННЫЕ: СТОРОНА (кто «помнится»), ИСТИНА (позиции видящих).
- RNG: нет. (:2215 — зонд.)

### D-23. evaluateAIMode — повторный вызов findFirePoint (область 03, здесь только последствия)
- `xtile = tile(_attackAction.target)`; `if (xtile && (xtile->getUnit() || бросок гранаты))` (:2883): `type != RETHINK` → `return` (:2885-2888); иначе `findFirePoint()` (:2890).
- Иначе (клетка цели без юнита — это уже выбранная точка огня, клетка рывка ближнего боя или пустая клетка) → `selectRandomTarget()` (:2899), затем `picked && findFirePoint()` (:2901).
- Неудача → `_AIMode = AI_PATROL` (:2908).
- RNG HERE: в selectRandomTarget — по броску на каждую годную цель (:2368); в findFirePoint — 120 бросков (:3017). **Точка огня, выбранная в setupAttack, перевыбирается заново** с новым перемешиванием; выбор `selectRandomTarget` тут же перезаписывается `selectClosestKnownEnemy` внутри findFirePoint (:3005) и влияет только на «есть ли хоть одна цель» (с гражданскими) и на число бросков.

### D-24. getReserveMode
- `return _reserve;` (:4286-4289). `_reserve = BA_NONE` на каждом think (:748); не NONE только в `AI_PATROL` с огнестрелом: агрессия 0 → AIMED, 1 → AUTO, 2 → SNAP (:769-783).
- Читатель: `checkReservedTU` (`BattlescapeGame.cpp:1524`, ветка HOSTILE :1536-1552): к стоимости добавляется SNAP + ОВ/3, AUTO + 2·ОВ/5, AIMED + ОВ/2 от базовых ОВ.
- В COMBAT резерв не держится: ходьба к точке огня и выстрел резервом не ограничены.
- СТОРОНЫ: только сторона HOSTILE.

### D-25. getTarget
- `return _aggroTarget;` (:4403-4406). Читают `MeleeAttackBState.cpp:129-134` (не игрок) и AiProbe.

### D-26. Бот: целевая фракция и знание
- Бот при careful получает `setTargetFaction(FACTION_HOSTILE)` (`BattlescapeGame.cpp:425-430`). Веса: враг 100, нейтральные −100 (не цели).
- `countKnownTargets` считает только для FACTION_HOSTILE (:2179-2192) → у бота `_knownEnemies = 0`: пси, бластер, снайпер и засада не работают.
- Остальное (selectNearestTarget, findFirePoint, getSpottingUnits) у бота работает так же, как у врага.

### D-27. Исполнение COMBAT в think
- `action->type/target/weapon = _attackAction…` (:791-794); бросок гранаты — списание взвода и 4 ОВ (:795-799); `finalFacing` (:801).
- Ходьба к точке огня не тратит счётчик действий, если `type == BA_WALK && _rifle && allowsMoving() && BattleActionCost(BA_SNAPSHOT, …).haveTU()` (:804-809). Проверка SNAP — по ОВ **до** ходьбы.
- AIMED/AUTO → `kneel = allowsKneeling(kneelDefault)` (:814-817); `_evalChosen` → своё приседание (:818-821, вне V4).

### D-28. tacticalMode (бот при V4; TACTICS вне V4)
- Вызов при `tactical` (:743-746): `AiProbe::tactics(_unit) || AiProbe::careful(_unit)` (:639).
- Нет видящих → выход (:2944-2947). Укрытие должно быть WALK, не своя клетка и видимо меньшим числом (:2955-2960).
- Атака не RETHINK/NONE и юнит не ранен (:2969-2970): AIMED/AUTO, после выстрела меньше `_escapeTUs`, а SNAP оставляет `≥ _escapeTUs` → тип SNAP (:2972-2980). При careful, не WALK и `ОВ − стоимость < _escapeTUs` → `AI_ESCAPE` («scoot», :2983-2988).
- Иначе (включая атаку RETHINK) → `AI_ESCAPE` (:2994-2995).
- RNG: нет.

### D-29. evalFireAction (вне V4)
- Включается `AiProbe::evalFire` = `OXCE_AI_EVAL` && careful (`AiProbe.cpp:373-377`); OXCE_AI_EVAL нет в V4.
- Кратко: цели — замеченные в этот ход (:3625); режимы AIMED/SNAP/AUTO (:3641); до 250 клеток (:3678); RISK 0.15, COVER 0.5, COVERTU 0.25, WALK 0.1 (:3690-3693); fragility = 2 − HP/maxHP (:3694); под наблюдением не ходит (:3709); exposure = risk × fragility × число врагов с линией огня (:3735); gain: при уроне ≥ HP `1 − (1 − hit)^shots`, иначе `0.7 × min(1, hit × shots × perHit / hp)` (:3786); risk = exposure × (0.5, если хватает ОВ на укрытие, иначе 1) (:3789); `score = gain − risk − walk + 0.0005 × left` (:3790). RNG нет.

---

## 3. Числа

| Число | Смысл | Где | Источник |
|---|---|---|---|
| 100 | база оценки точки огня | :3019, :3094 | код |
| 125 | порог быстрого выхода из поиска | :3020, :3121 | код |
| 70 | минимальная лучшая оценка, чтобы идти | :3138 | код |
| 10 | штраф за каждого видящего | :3094 | код |
| 10 | бонус за клетку вне конуса цели | :3098 | код |
| 1 ОВ = 1 очко | остаток ОВ после пути | :3095 | код |
| 11×11, z = 0 | область поиска точки огня (121 смещение) | `SavedBattleGame.cpp:79-84` | код |
| 1000 | maxTUCost пути до точки огня | `Pathfinding.h:243` | код |
| 20 | дальность «видящего» по плоскости | :2210 | код |
| −2 / −4 | высота глаз видящего / ствола юнита | :2213, :3066 | код |
| 100 | стартовый `_closestDist` прямого выстрела | :2243 | код |
| 255 | стартовая дистанция selectClosestKnownEnemy | :2339 | код |
| 0..20 | случайная добавка selectRandomTarget | :2368 | код |
| −100 | стартовый максимум selectRandomTarget | :2361 | код |
| 0..3 | бросок «поищу точку огня» | :1904 | код |
| sniper % | шанс снайперского действия | :1839 | РУЛСЕТ |
| 5 | fireChoiceIntelCoeff | `Mod.cpp:442` | РУЛСЕТ (умолч.) |
| 5 | fireChoiceAggroCoeff | `Mod.cpp:442` | РУЛСЕТ (умолч.) |
| 10 | интеллект, при котором разброс режима 0 | :3883 | код |
| true | extendedFireModeChoice у Пираток | `Piratez_Globals.rul:9155` | РУЛСЕТ |
| true | respectMaxRange у Пираток (не действует при extended) | `Piratez_Globals.rul:9156` | РУЛСЕТ |
| true | battleUFOExtenderAccuracy у Пираток | `Piratez_Globals.rul:9106` | РУЛСЕТ |
| 4 | ОВ на «достать гранату» | :2516, :2630 | код |
| 4 / 12 / 20 | границы дистанций ванильной таблицы | :3553, :3573, :3580 | код |
| 50 | порог веса цели (ThreatThreshold) | `Mod.h:247-251` | РУЛСЕТ (умолч.) |
| 100 / 50 / −200 / −100 / 0 | веса: враг, гражданский, свой, нейтральный, забытый | `Mod.h:247-251`, `AIModule.h:42` | РУЛСЕТ (умолч.) |
| 10, +(урон−50)/2, −20·(видимых−1), −20 / +10·aggr | шанс ближнего боя | :4314-4335 | код |
| 2/3 HP | порог здоровья для броска ближнего | :4327 | код |
| ОВ/3, 2·ОВ/5, ОВ/2 | резерв SNAP/AUTO/AIMED (только PATROL) | `BattlescapeGame.cpp:1546-1548` | код |
| 160 | делитель dodgeChanceDiff | :2391 | код |
| 2 / 1 | интеллект / агрессия бота | `BattleUnit.cpp:85-86` | код |

Распределение у Пираток (из `.index/mod/Piratez/rul/values.tsv`, 446 юнитов): интеллект 0–10, чаще 3–6, `10` у 9 юнитов, не задан у 29;
агрессия 0 — 72, 1 — 134, 2 — 102, 3 — 42, 4 — 19, 5 — 7, 6 — 5, 7 — 3, 8 — 31, не задана у 31.

---

## 4. RNG — в порядке выполнения за один вызов think (стрельба)

| # | Вызов | Файл:строка | Когда | Сколько бросков |
|---|---|---|---|---|
| 1 | `RNG::percent(sniper)` | AIModule.cpp:1839 | `_knownEnemies > 0`, пси не сработала, нет бластера, есть unitRules (только враг) | 1, даже при sniper = 0 |
| 2 | `RNG::generate(-I, I)` в extendedFireModeChoice | :3884 | внутри sniperAction, на каждую подсвеченную цель | по 1 на каждый доступный режим (AIMED/AUTO/SNAP, THROW только с гранатой) |
| 3 | `RNG::generate(0, n−1)` | :2548 | снайпер, список не пуст | 1 |
| 4 | `RNG::percent(meleeOdds)` | :4338 | `_melee && _rifle`, есть видимая цель, odds > 0, HP ≥ 2/3 | 1 |
| 5 | броски grenadeAction / meleeAction | — | область 13 | в grenadeAction и meleeAction RNG не найдено |
| 6 | `RNG::generate(-I, I)` | :3884 | projectileAction при extended (Пиратки) | по 1 на каждый доступный режим |
| 7 | `RNG::generate(0, 3)` | :1904 | тип остался RETHINK и `_spottingEnemies == 0` | 1 |
| 8 | `RNG::shuffle` | :3017 | findFirePoint, цель найдена | 120 |
| 9 | `RNG::generate(0, 20)` | :2368 | evaluateAIMode COMBAT, клетка цели без юнита | по 1 на каждую годную цель (с гражданскими) |
| 10 | `RNG::shuffle` | :3017 | повторный findFirePoint из evaluateAIMode (:2890 или :2901) | 120 |

Перед №1 может бросать psiAction (`RNG::percent` :4081, :4092, `RNG::generate(35, 155)` :4168) — область 13.
Между №7 и №9 бросают `RNG::percent(10)` :682 (думать ли о режиме) и `RNG::generate(1, …)` :2845 (выбор режима) — область 03.

Что легко сдвигает последовательность:
- №1 тратится у **каждого** врага с известной целью, даже без снайперского поля — добавление/удаление условия перед ним сдвинет всё.
- №2 и №6: число бросков = число режимов, на которые хватает ОВ **сейчас**, и зависит от боеприпаса (testEffect обнуляет режим) и от гранаты на поясе (THROW только в снайпере).
- №7 зависит от `_spottingEnemies` (короткое замыкание): любое изменение `getSpottingUnits` меняет, будет ли бросок.
- №8/№10: 120 бросков на вызов; повторный вызов в evaluateAIMode удваивает их.
- №9: число бросков = число годных целей, включая гражданских.

---

## 5. Знание

| Что читается | Метка | Где | Комментарий |
|---|---|---|---|
| допуск цели: `turnsSinceSpottedByFaction ≤ _intelligence` | СТОРОНА + ЮНИТ | :4217 | «знает ли сторона о цели» |
| подсветка споттерами | СТОРОНА | :4217-4218 (вес), :2522 | для снайпера |
| позиция цели (`getPosition`, `getTile`) | **ИСТИНА** | :2252, :2263, :2341, :2526, :3068, :3495 | не последняя известная позиция, а настоящая |
| направление цели (`checkViewSector` по `_direction`) | **ИСТИНА** | :3096, `BattleUnit.cpp:5198-5208` | бонус +10 за «за спиной» |
| видимость для прямого выстрела (`TileEngine::visible`) | ИСТИНА | :2249 | без конуса обзора |
| линия огня (`canTargetUnit`) | ИСТИНА | :2263, :3068, :2218/:2225, :2654 | |
| видящие точку (`getSpottingUnits`) | СТОРОНА (кто) + ИСТИНА (где) | :2208-2225 | без конуса, света, дыма |
| проходимость и цена пути | ИСТИНА (+ СТОРОНА при KO2 V2) | :3070, :1106-1118 | |
| клетка «опасная» (граната брошена) | ИСТИНА клетки | :4266 | |
| ОВ, энергия, интеллект, агрессия, точность | ЮНИТ | :3095, :3883, :3889, :2582 | |
| `_reachable`, `_reachableWithAttack`, `_rifle`, `_melee` | ПАМЯТЬ | :533, :3041 | могут быть устаревшими (D-01, D-02) |
| `_fpBlocked…` | ПАМЯТЬ | :971-1035 | вне V4 |
| sniper, waitIfOutsideWeaponRange, extendedFireModeChoice, коэффициенты, веса | РУЛСЕТ | :1839, :3021, :3022, :3883, :3889 | |

---

## 6. Карточки режима

### 6.1. FIREPOINT (findFirePoint)

| Пункт | Как в коде |
|---|---|
| Цель | ближайшая по плоскости известная цель с весом > 50 (`selectClosestKnownEnemy`, :3005, :2336-2353); гражданские не цель |
| Кандидаты | 121 клетка 11×11 на своём этаже (z = 0) вокруг юнита, в случайном порядке (:3016-3017, :3038) |
| Жёсткие отказы | нет клетки; не в `_reachableWithAttack` (:3040-3042); нет линии огня из клетки до клетки цели (:3068); нет пути (`start == −1`, в т. ч. своя клетка, :3072); вне V4: клетка цели (:3043-3060), путь по энергии (:3075-3081), заблокированный шаг (:3082-3093) |
| Оценка | `100 − 10·видящих + (ОВ − ОВ_пути) + 10·[вне конуса цели]` (:3094-3099) |
| Поправка дальности | при extended и оружии вне дальности сейчас: `× ceil(dist3d_сейчас) / max(dist2d(pos, цель), 1)` (:3102-3110) |
| Штраф за видимость | −10 за каждого «видящего» (вес > 50, ≤ 20 клеток по плоскости, есть линия огня до клетки) (:2201-2233) |
| RNG | только порядок перебора: shuffle, 120 бросков (:3017); в оценке случайности нет |
| Первая или лучшая | лучшая из просмотренных, но **первая > 125** обрывает перебор (:3121-3123); ничья → раньшая в случайном порядке (`>`) |
| Порог | `bestScore > 70` (:3138) |
| ОВ | путь не ограничен ОВ напрямую (maxTU 1000), ограничен фильтром `_reachableWithAttack` — бюджет «ОВ − стоимость SNAP» (:618-620, :939-943); в оценке — остаток ОВ после пути (:3095). Сам выстрел после ходьбы не планируется: в think только проверка `SNAPSHOT.haveTU()` по ОВ до ходьбы для счётчика (:804-809) |
| Энергия | только через фильтр `_reachableWithAttack` (бюджет энергии в findReachable); путь `calculate` по энергии не проверяется без флага вне V4 |
| Угроза ближнего боя | не учитывается (вес, линия огня — только у видящих; дальность 20; ни оружие видящего, ни ход до клетки не читаются) |
| Другие враги | только через «видящих» (−10 каждый); их ближний бой, огонь на реакцию, оружие, ОВ не читаются |
| Если путь пропал | при выборе — клетка отпадает (:3072). После выбора путь пересчитывается в handleAI (`BattlescapeGame.cpp:521`); `start == −1` → ходьба не начинается (:545). Повтор think при RETHINK (`BattlescapeGame.cpp:449-453`). При V4 первый шаг, упёршийся в юнита, запрещает BLOCKED_STEP (область 30/31) |
| Запасные ветки | неудача → тип RETHINK (:3035); evaluateAIMode повторяет findFirePoint (:2890) или selectRandomTarget + findFirePoint (:2899-2901), затем → AI_PATROL (:2908); у бота tacticalMode отправляет RETHINK в AI_ESCAPE (:2994-2995) |
| Направление после | `finalFacing = getDirectionTo(pos, позиция цели)` (:3120) |

### 6.2. Прямой выстрел (selectNearestTarget + projectileAction)

| Пункт | Как в коде |
|---|---|
| Цель | ближайшая по плоскости видимая (`visible`, без конуса) годная цель (вес > 0, с гражданскими) с линией огня из точки вылета оружия (:2240-2287) |
| Кандидаты режимов | AIMED, AUTO, SNAP, на которые хватает ОВ/энергии и есть боеприпас и эффект (:3496-3525, :3840-3851) |
| Жёсткие отказы | вне maxRange → точность 0 (:2600-2606); нет стоимости режима → 0 (:2636-2639); взрывчатка без эффекта (:3508-3511); все ≤ 0 → RETHINK (:3893) |
| Оценка | `точность × выстрелов × базовыеОВ / ОВ_режима` (:2663), × случайный множитель интеллекта (:3884), AUTO × агрессию (:3888-3891) |
| Штраф за видимость | нет |
| RNG | по броску на каждый доступный режим (:3884) |
| Первая или лучшая | лучшая, строго `>`; ничья → раньший по порядку AIMED, AUTO, SNAP |
| ОВ | только «хватает ли на режим сейчас»; остаток после выстрела не учитывается (у бота — tacticalMode, D-28) |
| Энергия | через `haveTU` стоимости режима |
| Угроза ближнего боя / другие враги | не учитываются (кроме `−20·(видимых − 1)` в выборе ближнего/дальнего, D-08) |
| Если цели нет | `selectNearestTarget` возвращает 0 → ветка точки огня (:1904) |
| Запасные ветки | RETHINK → findFirePoint (D-14), затем evaluateAIMode (D-23) |
| Ваниль без extended | таблица по дистанции (:3553-3600) без оценки и RNG |

### 6.3. SNIPER (sniperAction)

| Пункт | Как в коде |
|---|---|
| Включение | враг, `_knownEnemies > 0`, нет пси и бластера, `RNG::percent(sniper)` (:1820-1844) |
| Кандидаты | годные цели (вес > 0), подсвеченные споттерами стороны (:2522); вес не зануляется для забытых, если подсвечены (:4217-4218) |
| Оценка цели | `extendedFireModeChoice(checkLOF = true)` на каждую цель; цель годна, если хоть один режим > 0 (:2528-2539) |
| Выбор | равновероятно среди годных: `RNG::generate(0, n − 1)` (:2548) — оценки целей между собой **не сравниваются** |
| Бросок гранаты | THROW в кандидатах, если есть граната и ОВ на бросок + 4 + взвод (:2509-2517) |
| Результат | `_visibleEnemies ≥ 1` (:3478), атака без findFirePoint (`!sniperAttack` в :1849, :1862) |

---

## 7. Слепые пятна (доказанные кодом)

1. **Видящие без конуса обзора, света и дыма.** `getSpottingUnits` проверяет только `canTargetUnit` (:2218, :2225; `TileEngine.cpp:2196`). Враг, стоящий спиной, в темноте или за дымом, считается «видящим» так же, как смотрящий в упор.
2. **Позиция и направление цели — истинные.** findFirePoint целится в настоящую клетку цели (:3068) и даёт +10 за клетку за её настоящей спиной (:3096), хотя сторона знает лишь, что цель «замечена не позже `_intelligence` ходов назад» (:4217).
3. **Угроза ближнего боя и огонь на реакцию не читаются** ни в оценке точки огня, ни в выборе режима: только число линий огня (:3094) и ОВ (:3095).
4. **Только свой этаж.** Смещения поиска с z = 0 (`SavedBattleGame.cpp:79-84`): точка огня на другом уровне не рассматривается.
5. **Путь не ограничен ОВ.** `calculate` с maxTU 1000 (:3070, `Pathfinding.h:243`); ограничение только фильтром `_reachableWithAttack`, построенным другим поиском (`findReachable`). Путь по энергии без флага вне V4 не проверяется (:3075-3081).
6. **Выстрел после ходьбы не гарантирован.** Оценка — остаток ОВ после пути (:3095), но ни стоимость режима, ни линия огня **с учётом** дальности/точности оружия не проверяются. findFirePoint не смотрит тип оружия и боеприпас: работает и без `_rifle` (ветка :1904 не требует оружия), а `_reachableWithAttack` тогда устаревший (D-02).
7. **Дальность поправляется по текущей позиции.** Условие «вне дальности» (:3104) считается от текущего расстояния, а не от `pos`; если сейчас цель в дальности, клетка за пределом дальности не штрафуется.
8. **Ни урона, ни брони, ни шанса убийства** в выборе режима (:2663); точность может быть отрицательной (:2590-2597) — такой режим просто отпадает.
9. **Выбор цели прямого выстрела — только дистанция** (:2253): раненая, опасная, с оружием цель не предпочитается; снайпер выбирает цель равновероятно (:2548).
10. **Резерв ОВ в COMBAT не держится** (:748, :769-783); `_escapeTUs` в projectileAction не учитывается (у бота частично спасает tacticalMode, D-28).
11. **Точка огня перевыбирается.** После setupAttack evaluateAIMode заново зовёт findFirePoint с новым перемешиванием (:2899-2901) — выбор первого вызова не сохраняется; рывок ближнего боя на пустую клетку тоже может быть заменён точкой огня.
12. **Неудача findFirePoint стирает тип атаки** (:3035) — но в setupAttack (:1904) и в evaluateAIMode (:2890) её зовут только при RETHINK; на ветке :2901 тип перед вызовом может быть не RETHINK (клетка цели пустая — например, рывок ближнего боя), и тогда выбранная атака заменяется точкой огня или пропадает.
13. **Первая «очень хорошая» клетка** (> 125) выигрывает у лучшей (:3121-3123): при большом запасе ОВ почти любая клетка с короткой дорогой даёт > 125, и выбор фактически случаен.
14. **Чем агрессивнее, тем реже ищет точку огня, когда его не видят** (:1904): агрессия ≥ 3 — никогда (107 юнитов Пираток).
15. **Устаревшие данные в первом selectNearestTarget** (:533): `_rifle`, `_melee`, `_reachable` прошлого вызова (D-01).
16. **Точка вылета 8,8** (:3064-3066) — центр одной клетки, размер юнита 2×2 не учитывается.
17. **У бота нет снайпера, пси, бластера** — `_knownEnemies = 0` (D-26).

---

## 8. Не прослежено

- `BattleUnit::getFiringAccuracy` в деталях (модификаторы приседания, ранений, сложности) — только факт вызова (:2582).
- `RuleItem::calculateLimits` и `isOutOfRange` — по сводке строк `RuleItem.cpp:2290`, `:2386-2410`, частные случаи maxRange 1/2 не разбирались.
- `Pathfinding::calculate` (прямой путь Брезенхема против A*), `setKnownOccupant`, `isBlocked`, `takeKnownOccupantHits` — область 31. Может ли цена пути `calculate` отличаться от цены `findReachable` для той же клетки — не прослежено.
- `TileEngine::canTargetUnit`, `visible`, `validateThrow`, `getOriginVoxel` — только перечислено, что они читают.
- `psiAction`, `wayPointAction`, `grenadeAction`, `meleeAction`, `explosiveEfficacy` — область 13.
- Выбор режима `evaluateAIMode` (вероятности COMBAT/PATROL/AMBUSH/ESCAPE) — область 03.
- Исполнение ходьбы и выстрела (`handleAI`, `UnitWalkBState`, `ProjectileFlyBState`), BLOCKED_STEP — области 30/31.
- Скрипт `AiCalculateTargetWeight` у Пираток (:4243-4247) — переписывает ли он веса целей — область 40.
- `countKnownTargets` (:2179-2192) и `getTurnsSinceSpottedByFaction` — что у никогда не замеченной цели — область знания.
- Зонды (`AiProbe::tally`, `note`, `traceTile`, `probeMark`/`probeSlot`, `_probeScore`, `firepointDropped`, `knownOccupantV2Decided`) — только запись, на решения не влияют.
