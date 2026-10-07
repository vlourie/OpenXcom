# Что ИИ знает: истина, знание стороны, видимость юнита, память

Код: коммит `7cd80e284`. Все ссылки `файл:строка` сверены по текущему дереву. Флаги V4 — как в `00_README.md`
(все `=1`; `AMBUSH_MEMO=1`, `WALKFOV_SKIP=1`, `STALE_EXACT=1`). Бот = `AiProbe::careful(unit)`
(`src/Battlescape/AiProbe.cpp:367-371`: `bot() && OXCE_AI_CAREFUL && faction == FACTION_PLAYER`).

## 0. Коротко

1. **Позиция врага всегда настоящая.** Ни одна система родного ИИ не хранит «последнюю известную позицию». Знание
   стороны — это только фильтр «можно ли думать об этом юните» (`turnsSinceSpotted <= intelligence`), а дальше
   читается `bu->getPosition()` / `bu->getTile()` в момент решения. Запомненные позиции есть только у зондов бота вне V4
   (`lastSeen`, `AiProbe.cpp:3168`).
2. **Окно знания считается в раундах, а не в ходах стороны.** `updateTurnsSince` увеличивает счётчик один раз за раунд —
   в начале хода игрока (`SavedBattleGame.cpp:1549-1558`). Врагу с `intelligence >= 1` игрок, замеченный в прошлом раунде,
   «известен» весь следующий ход врага — уже на той клетке, куда он ушёл.
3. **У бота `countKnownTargets()` всегда 0** (`AIModule.cpp:2179-2194`, только `FACTION_HOSTILE`). Поэтому у бота нет
   засады (`think`, `:647`), нет пси/вейпойнта/снайпера (`setupAttack`, `:1819`), нет ветки «знаю врагов» в выборе
   режима (`:2714`), а в режиме ESCAPE оценка повторяется на каждом `think` (`:691`).
4. **Но знание стороны у бота работает через `validTarget`**: солдат имеет `intelligence = 2`
   (`BattleUnit.cpp:85`). `getSpottingUnits`, `selectClosestKnownEnemy` → `findFirePoint`, `selectRandomTarget`
   считают врага, которого сторона бота видела до 2 раундов назад, — по его настоящей текущей позиции.
5. **«Видимый враг» в `selectNearestTarget` — это знание стороны + `TileEngine::visible()`**, а `visible()` не проверяет
   сектор обзора (`TileEngine.cpp:1864-1930`): враг за спиной считается видимым, если сторона его знает.
6. **«Кто меня видит» (`getSpottingUnits`) — геометрия от настоящих глаз врага, без сектора обзора, без света и дыма,
   радиус 20 клеток константой** (`AIModule.cpp:2201-2231`). В Пиратках `maxViewDistance: 40`
   (`Piratez_Globals.rul:8872`) — враги на 21–40 клетках в счёт не входят.
7. **Блокеры пути зависят от фракции** (`Pathfinding.cpp:1206-1225`): игрок/бот — по флагу «виден стороне сейчас»;
   враг — только то, что этот юнит сам заметил с начала хода своей стороны; нейтрал — только свои. Невидимые юниты
   для пути — пустые клетки.
8. **Утечки истины** (доказанные): занятость клеток (`setUnitPosition(test)` в `getPatrolNode` и
   `selectPointNearTarget`, `tile->getUnit()` в `evaluateAIMode`/`setupPatrol`/`explosiveEfficacy`); подбор предметов
   по всей карте без видимости (`surveyItems`, в Пиратках `pickUpWeaponsMoreActively: true`); пси-зрение сквозь стены;
   хэш «что изменилось» `knownRevision` (BLOCKED_STEP) включает всю карту.
9. **LIGHTSKIP и WALKFOV_SKIP — не побайтно по построению**, равенство подтверждено только приёмкой (тени и fair22).

## 1. Схема: где знание рождается и где читается

```
Источник                                   Что пишет                                   Кто читает в ИИ
TileEngine::calculateLighting (:1141)      свет слоя юнитов (тень клетки)               visible() → дальность в темноте
TileEngine::calculateUnitsInFOV (:1467)    bu->setVisible (только наблюдатель-игрок)   isBlocked (игрок), carefulGuard
                                           unit->_visibleUnits, _unitsSpottedThisTurn  isBlocked (враг), UnitWalk stop, psi LOS
                                           bu->_turnsSinceSpotted[obsFaction] = 0      validTarget → почти всё
                                           bu->_turnsLeftSpottedForSnipers[...]        снайпер
TileEngine::calculateTilesInFOV (:1559)    tile->setVisible/discovered (только игрок)  sneakyAI (вне умолчания)
TileEngine::getSpottingUnits(BU*) (:2565)  bu->addToVisibleUnits (реакция, без фильтра) реакция
BattleUnit::damage (:1955-2052)            ai->_wasHitBy, turnsSince атакующего = 0     реакция (gotHit), validTarget
BattlescapeGame::checkForCasualties (:1039) murderer turnsSince[HOSTILE] = 0           validTarget врага
SavedBattleGame::endTurn (:1542-1567)      _cheating, updateTurnsSince, cheat → 0,      evaluateAIMode, think, patrol
                                           AIModule::reset
AIModule (поля)                            _toNode/_fromNode, _AIMode, _escapeTUs,     setupPatrol, think
                                           _ambushTUs, _wasHitBy
AiProbe (V4)                               KO_V2 цель, блокированные шаги, STALE         Pathfinding, handleAI, setupPatrol
```

Порядок в ходе юнита ИИ (`BattlescapeGame::handleAI`):
```
handleAI
  ├── unit->setVisible(false)                                 BattlescapeGame.cpp:411
  ├── calculateFOV(unit->getPosition(), 1, false)             :413   — пересчёт видимости вокруг юнита (без клеток)
  ├── careful(unit) → ai->setTargetFaction(FACTION_HOSTILE)   :425-430
  ├── AIModule::think                                         :447
  │     ├── _knownEnemies   = countKnownTargets()             AIModule.cpp:532  СТОРОНА (только враг)
  │     ├── _visibleEnemies = selectNearestTarget()           :533              СТОРОНА ∧ visible() 360°
  │     ├── _spottingEnemies= getSpottingUnits(pos)           :534              СТОРОНА + ИСТИНА-геометрия
  │     ├── KO_V1 (вне V4) :540-549; findReachable :550
  │     ├── _wasHitBy.clear()                                 :561   — память попаданий стёрта
  │     ├── setupEscape / setupAmbush / setupAttack / setupPatrol  :640-657
  │     └── evaluateAIMode / режимы                           :709+
  ├── findItem (не игрок) / findBotWeapon (бот, вне V4)       :466-474
  ├── blockedStepDecide (BLOCKED_STEP)                        :494
  └── KO_V2 / blockedStepPlan → Pathfinding::calculate        :509-528
```

## 2. Источники знания

### 2.1 Свет

```
### TileEngine::unitLightPower (TileEngine.cpp:1065-1110)
УСЛОВИЕ:   личный свет фракции (personalLightFriend / Hostile / Neutral) + светящийся предмет в руках + горящий юнит
ДАННЫЕ:    РУЛСЕТ (броня, предмет), состояние юнита (ИСТИНА)
RNG:       нет
РЕЗУЛЬТАТ: сила света юнита
ВОЗВРАТ:   calculateUnitLighting (:1114-1139) → gsDynamic; calculateLighting(layer<=LL_UNITS) (:1141-1250)
СТОРОНЫ:   оба
```

Свет влияет на зрение через `getVisibleDistanceMaxHelper` (`TileEngine.cpp:1739-1789`): если
`tile->getShade() > getMaxDarknessToSeeUnits()` (по умолчанию 9, `Mod.cpp:437`), дальность — тёмная
(`getMaxViewDistanceAtDark`), иначе дневная; горящая цель снимает камуфляж и темноту. Зрение ИИ — то же, что у
игрока: отдельного «ночного» правила для ИИ в коде не найдено.

### 2.2 Видимость: calculateUnitsInFOV

```
### TileEngine::calculateUnitsInFOV (TileEngine.cpp:1467-1550)
УСЛОВИЕ:   setupEventVisibilitySector(posSelf, eventPos, eventRadius) истинно (полная проверка; eventRadius==0 или
           eventPos==(-1,-1,-1) или наблюдатель внутри события, :1412-1417) → unit->clearVisibleUnits() (:1480-1483)
ДАННЫЕ:    позиции всех юнитов (ИСТИНА), сектор обзора наблюдателя checkViewSector (:1500), visible() (:1505)
RNG:       нет
РЕЗУЛЬТАТ: для юнита в секторе события:
           - вне сектора обзора → removeFromVisibleUnits (:1500-1504)
           - visible(): наблюдатель PLAYER → bu->setVisible(true) (:1508-1511);
             (цель HOSTILE ∧ наблюдатель PLAYER) ∨ (цель не HOSTILE ∧ наблюдатель HOSTILE) ∧ !hasVisibleUnit →
             addToVisibleUnits + addToVisibleTiles (:1512-1518);
             фракции разные → bu->setTurnsSinceSpottedByFaction(obsFaction, 0),
             снайперский таймер = max(getSpotterDuration(), текущий) (:1520-1527)
           - в секторе обзора, но не видно → removeFromVisibleUnits (~:1531)
ВОЗВРАТ:   true, если _unitsSpottedThisTurn вырос и visibleUnits не пуст (:1543-1547)
СТОРОНЫ:   оба. Наблюдатель-нейтрал не заполняет visibleUnits никогда; игрок не вносит в них нейтралов,
           но turnsSinceSpotted ставит при любой разнице фракций
```

`visible()` (`TileEngine.cpp:1864-1930`): своя фракция — всегда; дальше `distance2dSq > getMaxViewDistanceSq()` → нет;
пси-зрение (`getPsiVision`, с `psiCamouflage`, не у `fearImmune`) — **да без проверки препятствий** (:1882-1899);
иначе `canTargetUnit` от глаз, дым/огонь, скрипт `VisibilityUnit`. **Сектор обзора `visible()` не проверяет** —
его проверяют только вызывающие (`calculateUnitsInFOV` :1500, реакция :2619).

`addToVisibleUnits` (`BattleUnit.cpp:2408-2432`) кладёт юнит и в `_visibleUnits`, и (если ещё нет) в
`_unitsSpottedThisTurn`. `_unitsSpottedThisTurn` чистит только `prepareNewTurn` (`BattleUnit.cpp:2866`) — в начале хода
своей стороны (`SavedBattleGame.cpp:1604-1606`); затем `BattlescapeGame::endTurn` делает `recalculateFOV()`
(`BattlescapeGame.cpp:786`, после `_save->endTurn()` :759) — полную проверку всех юнитов, и список стороны, начинающей ход,
заполняется тем, что видно на старте.

`calculateTilesInFOV` (`TileEngine.cpp:1559-1680`) работает только для `FACTION_PLAYER` (:1572): видимость клеток
есть только у стороны игрока. У врага видимых клеток нет вообще.

### 2.3 Когда пересчитывается видимость

| где | что | файл:строка |
|---|---|---|
| начало хода стороны | `recalculateFOV()` — полный пересчёт всех | `BattlescapeGame.cpp:786`, `TileEngine.cpp:5783-5792` |
| перед каждым решением ИИ | `calculateFOV(pos, 1, false)` | `BattlescapeGame.cpp:413` |
| конец каждого шага | `calculateFOV(pos, 2, false)` (после света) | `UnitWalkBState.cpp:232` |
| конец шага, выбранный юнит игрока | `updateSoldierInfo(walkFovKeep)` → полный `calculateFOV(selectedUnit)` | `UnitWalkBState.cpp:204`, `BattlescapeState.cpp:2344` |
| поворот / остановка | `calculateFOV(_unit)` | `UnitWalkBState.cpp:441`, `:520`, `:535` |
| двери, смена местности, взрыв | `calculateFOV(pos, …)` | `TileEngine.cpp:3324/3329`, `:3546/3550`, `:4235` |
| смерть, предметы со светом | `calculateFOV` | `TileEngine.cpp:4846`, `:5221`; `BattlescapeGame.cpp:1189/1204`, `:2553`, `:2776`, `:3158` |
| спавн юнита | `calculateFOV(newUnit->getPosition())` | `BattlescapeGame.cpp:2486` |

Между этими точками `_visibleUnits` не обновляется: это кэш, а не опрос.

### 2.4 LIGHTSKIP и WALKFOV_SKIP — побайтно ли

```
### UnitWalkBState::think : свет шага (UnitWalkBState.cpp:227-231)
УСЛОВИЕ:   change = checkForProximityGrenades(_unit); if (change || !AiProbe::lightSkip(_terrain, _unit)) calculateLighting(...)
ДАННЫЕ:    unitLightPower(unit) == 0 (AiProbe.cpp:344-353) — ИСТИНА о собственном свете
RNG:       нет
РЕЗУЛЬТАТ: при LIGHTSKIP и нулевом свете ходока пересчёт слоя юнитов пропущен
СТОРОНЫ:   оба (флаг V4), только при active()
```

Вывод: «побайтно» держится на допущении, что ходок без света не меняет освещение (свет других юнитов от его позиции не
зависит). В коде это не доказано проверкой; утверждение и приёмка — `AiProbe.h:59-63`, `tools/ai_probe.py:98-137`
(ночь с фонарями, потоки =, fair22 IDENTICAL).

```
### UnitWalkBState::think : updateSoldierInfo на шаге (UnitWalkBState.cpp:204)
УСЛОВИЕ:   updateSoldierInfo(AiProbe::walkFovKeep(_parent, _unit)); walkFovKeep == false, если WALKFOV_SKIP==1 и
           walkFovSkipCase: botTurn ∧ playableUnitSelected ∧ selectedUnit == walker ∧ !sneakyAI (AiProbe.cpp:2036-2060, 2345-2356)
ДАННЫЕ:    —
RNG:       нет
РЕЗУЛЬТАТ: пропущен полный calculateFOV(selectedUnit) (BattlescapeState.cpp:2344) ДО света шага
СТОРОНЫ:   только бот, ход игрока
```

Не побайтно по построению: пропущенный вызов шёл при старом свете и мог поставить `_unitsSpottedThisTurn`,
`setVisible`, `turnsSinceSpotted = 0`, снайперский таймер и видимость клеток ходока, которые FOV шага (`:232`, с
`updateTiles=false`) не ставит снова. Перечень возможных потерь — сам комментарий `AiProbe.cpp:2009-2016`; равенство
установлено режимом тени (`=2`, все счётчики потерь 0) и fair22 IDENTICAL (`tools/ai_probe.py`). Видимость клеток
игрока на шаге бота (нужна только для sneakyAI) при пропуске не пересчитывается.

### 2.5 Знание стороны: turnsSinceSpotted

Хранится у ЦЕЛИ: `bu->_turnsSinceSpotted[faction]`, `bu->_turnsLeftSpottedForSnipers[faction]`
(`BattleUnit.cpp:4993-5056`). Кто именно видел — не хранится. Сеттер без фракции пишет слот HOSTILE.

| кто ставит | значение | условие | файл:строка |
|---|---|---|---|
| `calculateUnitsInFOV` | слот наблюдателя = 0, снайпер = max(spotter наблюдателя, текущий) | видит, фракции разные | `TileEngine.cpp:1520-1527` |
| попадание (`BattleUnit::damage`) | атакующему в слоте жертвы = 0; снайпер = max(текущий, spotter ЖЕРТВЫ) | AIMED/SNAP/AUTO, есть damage_item, прямое попадание или радиус 0; снайпер — по `EXTENDED_SPOT_ON_HIT_FOR_SNIPING` (Пиратки: 1 — только если жертва не выбыла) | `BattleUnit.cpp:1964-1987`, `:2047-2052` |
| скрипт `DamageSpecialUnit` | любое | скрипт мода меняет `args` до записи | `BattleUnit.cpp:1993-2000`, `:2050-2051` |
| смерть врага | убийце слот HOSTILE = 0 | жертва HOSTILE, есть убийца | `BattlescapeGame.cpp:1039` |
| cheating | всем живым игрокам слот HOSTILE = 0 | `_cheating` в начале хода игрока | `SavedBattleGame.cpp:1559-1561` |
| `tryConcealUnit` | слот HOSTILE = 255, снайпер 0 | — | `TileEngine.cpp:5117-5130` |
| `updateTurnsSince` | +1 до 255, снайпер −1 | раз в раунд, начало хода игрока | `BattleUnit.cpp:4946`, `SavedBattleGame.cpp:1557` |

Реакция (`TileEngine::getSpottingUnits(BU*)`) `turnsSinceSpotted` НЕ ставит (`TileEngine.cpp:2619-2630`): только
`addToVisibleUnits` реагирующему.

Cheating (`SavedBattleGame.cpp:1542-1545`): `(_turn > _cheatTurn/2 && liveAliens <= 2) || _turn > _cheatTurn`;
`cheatTurn` по умолчанию 20 (`AlienDeployment.cpp:42`, поле `cheatTurn`). В Пиратках `cheatTurn` задан у одного
развёртывания (5), у остальных 20 (values.tsv). Сбрасывает `resetTurnCounter` (`SavedBattleGame.cpp:2924`).

`intelligence`: солдат 2 (`BattleUnit.cpp:85`), юнит рулсета — `Unit::intelligence` (`BattleUnit.cpp:494`, по
умолчанию 0). В Пиратках по 417 юнитам: 0×10, 1×36, 2×52, 3×64, 4×97, 5×52, 6×54, 7×19, 8×18, 9×6, 10×9.
`spotter` (−1 = intelligence, `Unit.cpp:372`): −1×18, 0×3, 1×81, 2×72, 3×20, 4×8, 5×2; у солдат `getSpotterDuration`
= 0 (`BattleUnit.cpp:5798-5806`).

### 2.6 Видимость юнита (ЮНИТ)

| поле | что | наполняется | читается |
|---|---|---|---|
| `_visibleUnits` | видит сейчас (кэш) | `calculateUnitsInFOV`, реакция | `hasVisibleUnit`, psi LOS (`AIModule.cpp:4032`), `worthTaking`/`handleAI` (`BattlescapeGame.cpp:466, 471, 2876`), sneak-up |
| `_unitsSpottedThisTurn` | видел с начала хода своей стороны | `addToVisibleUnits` | `isBlocked` врага (`Pathfinding.cpp:1218`), остановка шага (`UnitWalkBState.cpp:235, 442`) |
| `bu->_visible` | виден стороне игрока сейчас | `setVisible(true)` от наблюдателя-игрока; `false` у не-игроков в начале хода и перед решением/шагом | `isBlocked` игрока (`:1213`), `carefulGuard` (`BattlescapeGame.cpp:328`) |

`getVisible()` у игрока и `isAlwaysVisible` — всегда true (`BattleUnit.cpp:3487`).

### 2.7 Память

| память | где | живёт | читается |
|---|---|---|---|
| `_wasHitBy` (id атакующих) | `AIModule.cpp:1354-1375` | от попадания до `_wasHitBy.clear()` в следующем `think` жертвы (`:561`); сохраняется в сейв (`:198`) | только реакция: `gotHit` (`TileEngine.cpp:2611`). В решениях `AIModule` не читается |
| `_toNode`, `_fromNode`, `_AIMode` | AIModule | между решениями и ходами, в сейве (`:194-196`) | `setupPatrol`, `evaluateAIMode` |
| `_escapeTUs`, `_ambushTUs` | AIModule | до `reset()` в начале хода игрока (`:162-170`, `SavedBattleGame.cpp:1564`) | `think` `:640, :647`, `evaluateAIMode` |
| STALE_PATROL_NODE | `setupPatrol` `:1436-1494` | проверка сохранённого `_toNode` своим поиском (witnessReach при STALE_EXACT=1, иначе `calculate`) | нет пути → узел сброшен |
| KO_V2 | `AIModule.cpp:1088-1148` | цель `_aggroTarget` с `turnsSince == 0` блокирует свою клетку в поиске (враг) | `findFirePoint` `:3007-3015`, `setupAmbush` `:1641-1650`, ход `BattlescapeGame.cpp:509-528` |
| AMBUSH_MEMO | `setupAmbush` `:1655-1729` | один вызов: закрытые клетки первого полного A* врага без пути | пропуск узлов без пути у врага |
| BLOCKED_STEP | `AiProbe.cpp:4346-4440` | до конца хода юнита, пока `knownRevision` тот же (`AiProbe.h:346-355`) | запрет первого шага в `blockedStepPlan` |
| `_fpBlocked` (FIREPOINT_BLOCKED, вне V4) | `AIModule.cpp:971-1030` | ход юнита, пока не сменились позиция/ОВ/цель/`knownRevision` | `findFirePoint` `:3027` |
| `lastSeen` (вне V4) | `AiProbe.cpp:3168-3206` | весь бой, позиция и ход последнего замечания | зонды бота: HALF, WATCH, TURRET и др. |

`knownRevision` (`AiProbe.cpp:4013-4038`) хэширует свои и замеченные в этот раунд юниты (`turnsSince == 0`) с их
настоящими позициями **и всю карту целиком** (MapData каждой клетки, двери, огонь, дым) — в том числе неразведанное.

### 2.8 Утечки (ИСТИНА за фильтром знания)

| утечка | файл:строка | у кого |
|---|---|---|
| занятость клеток при выборе узла: `setUnitPosition(unit, pos, true)` → `t->getUnit()` | `SavedBattleGame.cpp:2346`, `:2632-2670` | оба |
| занятость клеток у цели ближнего боя: `setUnitPosition(test)` | `AIModule.cpp:2385-2445` | оба |
| `xtile->getUnit()` на клетке цели атаки | `AIModule.cpp:2883` | оба |
| `nodeunit = tile->getUnit()` на узле (оборона базы) | `AIModule.cpp:1562` | оба |
| `explosiveEfficacy`: юнит на клетке цели считается `++enemiesAffected` до проверки знания | `AIModule.cpp:3207-3212` | оба |
| `getSpottingUnits`, засада, `findFirePoint`: линия от настоящих глаз врага | `AIModule.cpp:2212-2227`, `:1654`, `:1690`, `:3068` | оба |
| `setupAmbush`: путь врага до узла его собственными блокерами и ОВ не ограничен | `AIModule.cpp:1721` | враг |
| `surveyItems`: все предметы на земле карты с `attraction`, без видимости | `BattlescapeGame.cpp:2806-2856` | враг, нейтрал |
| пси-зрение без препятствий | `TileEngine.cpp:1882-1899` | у кого `psiVision` |
| psi: `psiAttackCalculate` по настоящим статам жертвы | `AIModule.cpp:4047` | враг |
| missile-путь: блокирует юнит, если `turnsSince <= intelligence` (настоящая клетка) | `Pathfinding.cpp:762-772` | враг с рулсетом |
| `knownRevision` включает всю карту | `AiProbe.cpp:4027-4036` | оба (BLOCKED_STEP) |
| sneakyAI: видимость клеток игрока | `Pathfinding.cpp:254, 401, 1022, 1059` | враг; `sneakyAI: false` в установке (`options.cfg:412`), стенд выключает |

## 3. ГЛАВНАЯ ТАБЛИЦА: система решения × источник знания

Обозначения: ✔ — читает; — — не читает. «СТОРОНА» = `validTarget`/`getTargetAttackWeight`:
`turnsSince[свой] <= intelligence` или снайпер с таймером (`AIModule.cpp:4216-4223`).

| система | ИСТИНА | СТОРОНА | ЮНИТ | ПАМЯТЬ | примечание (файл:строка) |
|---|---|---|---|---|---|
| `countKnownTargets` | — | ✔ `validTarget(bu,true,true)` | — | — | только `FACTION_HOSTILE`, иначе 0 — `AIModule.cpp:2179-2194` |
| `getSpottingUnits(pos)` | ✔ позиция и глаза врага, `canTargetUnit` 360°, ≤20 клеток | ✔ `validTarget(bu,false,false)` (вес > порога 50) | — | — | нет сектора, света, дыма; `assessDanger=false` — `:2201-2231` |
| `selectNearestTarget` | ✔ позиция цели, LOF/`selectPointNearTarget` | ✔ `validTarget(bu,true,true)` | ✔ `visible(_unit, tile)` пересчётом, без сектора | — | ставит `_aggroTarget`, `_closestDist` — `:2240-2287` |
| `selectNearestTargetLeeroy` | ✔ | ✔ | ✔ `visible()` | — | `:2295-2330` |
| `selectClosestKnownEnemy` | ✔ настоящая позиция, расстояние | ✔ `validTarget(bu,true,false)` | — | — | без видимости и без LOF — `:2336-2353` |
| `selectRandomTarget` | ✔ позиция | ✔ `validTarget(bu,true,true)` | — | — | RNG на каждую цель — `:2359-2376` |
| `selectPointNearTarget` | ✔ клетки вокруг `target->getPosition()`, `setUnitPosition(test)` | — (цель уже выбрана) | — | — | `_reachable`, `getDangerous` — `:2385-2445` |
| `selectSpottedUnitForSniper` | ✔ позиция, LOF в `scoreFiringMode` | ✔ `validTarget` ∧ снайперский таймер | — | — | `:2520-2550` |
| `validTarget` | ✔ `isOut`, `getDangerous` | ✔ вес цели | — | — | `:4259-4280` |
| `evaluateAIMode`: входы | ✔ `xtile->getUnit()` (:2883), ОВ, здоровье | ✔ `_knownEnemies` (:2714), `isCheating` (:2871) | ✔ `_visibleEnemies`, `_closestDist` (:2813-2818) | ✔ `_AIMode` (инерция :2742), `_ambushTUs` (:2704, :2822), `_escapeTUs` (:2695, :2721) | `_spottingEnemies` (:2692, :2802) — смешанный, см. выше |
| `setupPatrol` | ✔ занятость узлов (`getPatrolNode`), `nodeunit` (:1562) | ✔ `isCheating` → scout (:1505) | — | ✔ `_toNode`, `_fromNode`; STALE (:1436-1494) | путь — своими блокерами |
| `setupAmbush` | ✔ глаза цели `getSightOriginVoxel(_aggroTarget)` (:1654), путь цели (:1721) | ✔ `selectClosestKnownEnemy` (:1639) | — | ✔ AMBUSH_MEMO (один вызов), KO_V2 | только враг (у бота `_knownEnemies=0`) |
| `setupAttack` | ✔ через вызываемые | ✔ `_knownEnemies` (:1819) | ✔ `selectNearestTarget` (:1862) | — | `_spottingEnemies` (:1904) |
| `setupEscape` | ✔ позиция `_aggroTarget`, `getSpottingUnits(target)` | ✔ через `selectNearestTarget`/`getSpottingUnits` | ✔ `selectNearestTarget` (:1938) | ✔ `lastCover` (переменная функции) | RNG `:1960, :1995-1996, :2016-2018` |
| `findFirePoint` | ✔ `canTargetUnit` к `_aggroTarget->getTile()`, `checkViewSector` цели (:3096) | ✔ `selectClosestKnownEnemy` (:3005) | — | ✔ KO_V2; `_fpBlocked` (вне V4) | `getSpottingUnits(pos)` (:3094) |
| `getSpottingUnits` в escape/ambush | ✔ | ✔ | — | — | `:2063`, `:2133`, `:1690` |
| `projectileAction` + `scoreFiringMode` | ✔ расстояние до `_aggroTarget`, LOF (при `checkLOF`) | — | — | — | `explosiveEfficacy` для взрывных (:3508) — `:3497-3610`, `:2572-2664` |
| `extendedFireModeChoice` | ✔ через `scoreFiringMode` | — | — | — | RNG по intelligence (:3884) |
| `grenadeAction` + `explosiveEfficacy` | ✔ юниты в радиусе по настоящим позициям, юнит на клетке цели | ✔ вес > 0 для остальных (:3236-3242) | — | — | `getNodeOfBestEfficacy`: узлы, глаза юнитов — `:4354-4398` |
| `psiAction` | ✔ статы жертвы (`psiAttackCalculate`), дальность | ✔ `validTarget(bu,true,false)` | ✔ `getVisibleUnits` если `isLOSRequired` (:4032) | ✔ `_didPsi` | RNG `:4081, :4092, :4168` |
| `meleeAction` | ✔ позиция, ≤20 клеток, `selectPointNearTarget` | ✔ `validTarget(bu,true,true)` | — | — | без видимости — `:3284-3330`, ≤20 клеток `:3306` |
| `wayPointAction` | ✔ путь BAM_MISSILE к настоящей позиции | ✔ `validTarget(bu,true,true)` | — | — | `:3385-3465` |
| медкит (`medikit_think`) | ✔ своё здоровье, оглушение, энергия | — | — | — | о врагах не знает — `:290-420` |
| `surveyItems`/`findItem` | ✔ все предметы карты | — | ✔ `getVisibleUnits()->empty()` (`handleAI` :466, `worthTaking` :2876) | ✔ `getTurnFlag` (брошен на ходу не-игрока) | `BattlescapeGame.cpp:2751-2880` |
| `findBotWeapon` (вне V4) | ✔ предметы ≤8 клеток, тот же z | — | ✔ `getVisibleUnits()->empty()` (:471) | — | `BattlescapeGame.cpp:3104-3165` |
| блокеры пути (`isBlocked`) | ✔ кто на клетке | ✔ игрок: `u->getVisible()` | ✔ враг: `_unitsSpottedThisTurn` | ✔ KO_V1 (вне V4) | `Pathfinding.cpp:1206-1225` |
| missile-путь | ✔ | ✔ `turnsSince <= intelligence` | — | — | `Pathfinding.cpp:762-772` |
| остановка шага при новом враге | — | — | ✔ `_unitsSpottedThisTurn.size() != _numUnitsSpotted` | ✔ `_numUnitsSpotted` с начала шага-действия (:66) | `UnitWalkBState.cpp:235, 243-247` |
| остановка о юнит на клетке | ✔ `getOverlappingUnit` | — | — | — | `UnitWalkBState.cpp:374-384` |
| огонь на реакцию | ✔ позиция ходока | — | ✔ сектор обзора, `visible(bu,tile)` | ✔ `_wasHitBy` (`gotHit`) | `TileEngine.cpp:2565-2680` |
| `carefulGuard` (бот) | ✔ позиция | — | ✔ `bu->getVisible()` (видит сторона сейчас) | ✔ WATCH (вне V4) | `BattlescapeGame.cpp:307-345` |

## 4. Позиция врага: настоящая или запомненная

**Настоящая текущая.** Все системы из таблицы берут `bu->getPosition()`, `bu->getTile()` или
`getSightOriginVoxel(bu)` в момент решения:

| система | что читается | файл:строка |
|---|---|---|
| `getSpottingUnits` | `bu->getPosition()`, `getSightOriginVoxel(bu)` | `AIModule.cpp:2210-2212` |
| `selectNearestTarget` | `bu->getPosition()`, `bu->getTile()` | `:2249-2268` |
| `selectClosestKnownEnemy` | `bu->getPosition()` | `:2344` |
| `setupAmbush` | `getSightOriginVoxel(_aggroTarget)`; путь `calculate(_aggroTarget, pos)` | `:1654`, `:1721` |
| `findFirePoint` | `_aggroTarget->getTile()`, `_aggroTarget->getPosition()` | `:3068`, `:3108`, `:3120` |
| снайпер | `bu->getPosition()` | `:2527`, `:2550` |
| psi | `_aggroTarget->getPosition()` | `:4180` |

Следствие: с `intelligence = N` ИИ знает настоящую позицию врага в течение N раундов после последнего замечания, где
бы тот ни был, — сквозь стены, после ухода за угол. Это главное несоответствие «знанию игрока». Другое следствие:
`_aggroTarget` между решениями не хранится как точка — он переизбирается (`selectNearestTarget` и др. обнуляют
`_aggroTarget = 0`, `:2244`, `:2338`, `:2362`).

Исключения (запомненная точка): `lastSeen` зондов бота (вне V4, `AiProbe.cpp:3168-3206`), `lastCover` внутри одного
вызова `setupEscape`. В родном ИИ запомненной позиции врага не найдено.

## 5. Бот против врага

| что | враг (`HOSTILE`) | бот (`PLAYER`, careful) | файл:строка |
|---|---|---|---|
| `_targetFaction` | `PLAYER` | `HOSTILE` (выставляется перед каждым решением) | `AIModule.cpp:52-70`, `BattlescapeGame.cpp:425-430` |
| `intelligence` | из рулсета (0–10 у Пираток) | 2 | `BattleUnit.cpp:494`, `:85` |
| `countKnownTargets` | считает | всегда 0 | `AIModule.cpp:2183` |
| засада | есть при `_knownEnemies` | никогда | `:647` |
| psi/вейпойнт/снайпер | при `_knownEnemies` | никогда | `:1819-1841` |
| ESCAPE: повтор оценки | `!_spottingEnemies \|\| !_knownEnemies` | всегда истинно (`_knownEnemies=0`) | `:690-692` |
| выбор режима без known | `combatOdds = escapeOdds = 0` | не обнуляется | `:2735-2739` |
| cheating | знает всех игроков (слот HOSTILE = 0), режим COMBAT принудительно | не действует на бота (слот PLAYER не трогается); `evaluate=true` при cheating действует на всех | `SavedBattleGame.cpp:1559-1561`, `AIModule.cpp:2871`, `:707` |
| вес нейтрала | `AsHostileCivilians` 50 (цель, но не угроза: ≤ порога 50) | `AsNeutral` −100 (не цель, свой в радиусе гранаты) | `:4224-4241`, `Mod.h:247-251` |
| блокеры пути | замеченные самим юнитом с начала хода | видимые стороне сейчас (`getVisible`) | `Pathfinding.cpp:1213-1219` |
| `getNodeOfBestEfficacy` | враги +1 (если знает), свои −2 | каждый юнит −2 → гранатный узел не выбирается никогда (`bestScore > 2`) | `AIModule.cpp:4378-4389` |
| `gotHit` в реакции | `_wasHitBy` (AI есть) | `_wasHitBy` бота (у бота тоже AIModule), а не `getHitState` | `TileEngine.cpp:2611` |
| реакция врага взрывным | `explosiveEfficacy == 0` → не стреляет | правило только для `ai` юнита в `tryReaction` | `TileEngine.cpp:2862-2867` |
| подбор оружия | `surveyItems` вся карта (Пиратки: `pickUpWeaponsMoreActively`) | `findBotWeapon` ≤8 клеток (вне V4, ARMS) | `BattlescapeGame.cpp:466-474` |
| поворот к угрозе в конце | — | `carefulGuard`: ближайший видимый стороне враг | `BattlescapeGame.cpp:307-345, 582` |
| WALKFOV_SKIP | не касается | пропуск FOV выбранного юнита на шаге | `AiProbe.cpp:2036-2060` |
| tacticalMode | нет (TACTICS выключен) | да | `AIModule.cpp:745`, `:2941-3000` |

## 6. Развилки ключевых функций

```
### AIModule::getTargetAttackWeight : фильтр знания (AIModule.cpp:4216-4223)
УСЛОВИЕ:   target->getFaction() != _unit->getFaction() &&
           _intelligence < target->getTurnsSinceSpottedByFaction(_unit->getFaction()) &&
           (!_unit->isSniper() || !target->getTurnsLeftSpottedForSnipersByFaction(_unit->getFaction()))
ДАННЫЕ:    turnsSince, снайперский таймер (СТОРОНА); _intelligence (РУЛСЕТ)
RNG:       нет
РЕЗУЛЬТАТ: AIW_IGNORED (0); иначе AsHostile (цель == _targetFaction) / AsHostileCivilians / AsNeutral; свои — AsFriendly
           без фильтра знания (:4211-4215); затем скрипт AiCalculateTargetWeight (:4243)
ВОЗВРАТ:   validTarget: includeCivs → вес > 0, иначе вес > getAITargetWeightThreatThreshold (50)
СТОРОНЫ:   оба
```

```
### AIModule::validTarget (AIModule.cpp:4259-4280)
УСЛОВИЕ:   target->isOut() || (assessDanger && target->getTile()->getDangerous()) ||
           (target->getFaction() != FACTION_PLAYER && target->isIgnoredByAI()) → false
ДАННЫЕ:    isOut, getDangerous (ИСТИНА); вес (СТОРОНА)
RNG:       нет
ВОЗВРАТ:   bool
СТОРОНЫ:   оба
```

```
### AIModule::getSpottingUnits (AIModule.cpp:2201-2231)
УСЛОВИЕ:   validTarget(bu, false, false) && distance2d(pos, bu->getPosition()) <= 20 &&
           canTargetUnit(глаза bu (z-2), tile(pos), …, bu, false[, _unit если pos не своя клетка])
ДАННЫЕ:    знание (СТОРОНА); позиция и глаза bu, геометрия (ИСТИНА)
RNG:       нет (зонд escapeTarget — счёт)
РЕЗУЛЬТАТ: число «кто может видеть клетку»
СТОРОНЫ:   оба; у врага в счёт идут только игроки (вес 100 > 50), нейтралы (50) — нет
```

```
### AIModule::selectNearestTarget (AIModule.cpp:2240-2287)
УСЛОВИЕ:   validTarget(bu, true, true) && visible(_unit, bu->getTile())
ДАННЫЕ:    знание (СТОРОНА); visible() — пересчёт зрения без сектора (ЮНИТ 360°); LOF / selectPointNearTarget (ИСТИНА)
RNG:       нет
РЕЗУЛЬТАТ: tally всех таких; _aggroTarget — ближайший, до которого есть LOF (стрелок) или точка удара (рукопашник)
ВОЗВРАТ:   tally, если найден _aggroTarget, иначе 0 (видимые без LOF не считаются вовсе, :2280-2285)
СТОРОНЫ:   оба
```

```
### Pathfinding::isBlocked : юнит на клетке пола (Pathfinding.cpp:1206-1225)
УСЛОВИЕ:   u == unit || u == missileTarget || u->isOut() → не блок;
           unit PLAYER && u->getVisible() → блок; своя фракция → блок;
           unit HOSTILE && u ∈ unit->getUnitsSpottedThisTurn() → блок;
           u == _knownOccupant && unit == _knownOccupantFor && bam != BAM_MISSILE → блок (KO)
ДАННЫЕ:    tile->getUnit() (ИСТИНА); getVisible (СТОРОНА игрока сейчас); _unitsSpottedThisTurn (ЮНИТ)
RNG:       нет
РЕЗУЛЬТАТ: иначе — клетка проходима, путь идёт сквозь невидимого юнита; нейтрал-ходок проходит сквозь всех чужих
ПРЕРЫВАНИЕ: на ходу UnitWalkBState останавливается о такой юнит (:374-384) или у занятой клетки назначения (:156-158)
СТОРОНЫ:   оба; KO_V2 ставит _knownOccupant только врагу (AIModule.cpp:1091)
```

```
### UnitWalkBState::think : остановка «spotted» (UnitWalkBState.cpp:235, 243-247)
УСЛОВИЕ:   !_action.ignoreSpottedEnemies && !_falling && !_action.desperate && getPanicHandled() &&
           _numUnitsSpotted != _unit->getUnitsSpottedThisTurn().size()
ДАННЫЕ:    собственный список замеченных ходока (ЮНИТ), снят в начале действия (:66)
RNG:       нет
РЕЗУЛЬТАТ: cancelCurentMove — новое решение ИИ
ПРЕРЫВАНИЕ: побег ставит desperate = true (AIModule.cpp:761) — новые враги его не останавливают
ВОЗВРАТ:   handleAI → think
СТОРОНЫ:   оба. Новый враг — любой, кого FOV шага добавил в список (у врага и нейтралы), не обязательно опасный
```

```
### TileEngine::getSpottingUnits(BattleUnit*) : кто реагирует (TileEngine.cpp:2565-2680)
УСЛОВИЕ:   (bu->checkViewSector(unit->getPosition()) || gotHit) && canTargetUnit(...) && visible(bu, tile);
           gotHit = ai ? ai->getWasHitBy(unit->getId()) : bu->getHitState() (:2611);
           EXTENDED_MELEE_REACTIONS == 2 (Пиратки: 2) → || wasMeleeAttackedBy (:2613-2617)
ДАННЫЕ:    глаза реагирующего, сектор (ЮНИТ); _wasHitBy (ПАМЯТЬ)
RNG:       RNG HERE: RNG::percent(arg.getFirst()) TileEngine.cpp:2892 — выстрел реакции; только если кандидат прошёл
РЕЗУЛЬТАТ: bu->addToVisibleUnits(unit) без фильтра фракций (:2629); игрок → unit->setVisible(true)
СТОРОНЫ:   оба; на ходу нейтралов реакции нет
```

## 7. Числа

| число | значение | выражение / поле | файл:строка | на что влияет |
|---|---|---|---|---|
| радиус «кто видит» | 20 | `if (dist > 20) continue` | `AIModule.cpp:2211` | `getSpottingUnits` |
| дальность зрения | 20 (Пиратки 40) | `maxViewDistance` | `Mod.cpp:437, 3870`; `Piratez_Globals.rul:8872` | `visible()` |
| порог темноты | 9 | `maxDarknessToSeeUnits` | `Mod.cpp:437, 3871` | дальность в темноте |
| порог угрозы | 50 | `ai.targetWeightThreatThreshold` | `Mod.h:247`, `Mod.cpp:3918` | `validTarget(...,false)` |
| вес врага | 100 | `targetWeightAsHostile` | `Mod.h:248` | цели, граната |
| вес мирного (для врага) | 50 | `targetWeightAsHostileCivilians` | `Mod.h:249` | цель, но не «угроза» |
| вес своего | −200 | `targetWeightAsFriendly` | `Mod.h:250` | граната |
| вес нейтрала (для бота) | −100 | `targetWeightAsNeutral` | `Mod.h:251` | граната бота |
| intelligence солдата | 2 | константа | `BattleUnit.cpp:85` | окно знания бота |
| cheatTurn | 20 | `cheatTurn` | `AlienDeployment.cpp:42, 170` | cheating: turn > 10 и ≤2 живых, или turn > 20 |
| turnsSince потолок | 255 | `updateTurnsSince` | `BattleUnit.cpp:4946` | «никогда не видел» |
| intelCoeff огня | 5 | `ai.fireChoiceIntelCoeff`; разброс ±5·max(10−int,0) % | `Mod.cpp:442`, `AIModule.cpp:3883-3884` | выбор режима огня |
| радиус ближнего боя | 20 | `newDistance > 20` | `AIModule.cpp:3307` | `meleeAction` |
| узлы гранаты | ≤20, > радиуса | `dist <= 20 && dist > radius` | `AIModule.cpp:4366` | `getNodeOfBestEfficacy` |
| засада: узлы | ≤10, тот же z | | `AIModule.cpp:1675` | `setupAmbush` |
| предметы бота | <9 клеток, тот же z | `bestDist = 9` | `BattlescapeGame.cpp:3121, 3130` | `findBotWeapon` (вне V4) |
| sneak-up | 0 | `closeQuartersSneakUpGlobal` | `Mod.cpp:449, 3940` | подкрадывание в ближнем бою |
| sneaky стоимость | ×2 | клетка видна игроку | `Pathfinding.cpp:401, 1059` | sneakyAI (выключен) |

## 8. RNG

В источниках знания (FOV, свет, turnsSince, `validTarget`, `getSpottingUnits`, `selectNearestTarget`,
`selectClosestKnownEnemy`, `isBlocked`, остановка шага) RNG нет. Броски там, где знание уже применено:

| файл:строка | что решает | когда вызывается |
|---|---|---|
| `AIModule.cpp:682` | PATROL: `evaluate` при отсутствии врагов (10 %) | режим PATROL и `_spottingEnemies`, `_visibleEnemies`, `_knownEnemies` все 0 (короткое замыкание `\|\|`) |
| `AIModule.cpp:1839` | снайпер: `getSniperPercentage` | `_knownEnemies` ∧ не `_blaster` ∧ есть `unitRules` (только враг) |
| `AIModule.cpp:1904` | `findFirePoint` без замечающих | `_attackAction.type == BA_RETHINK` ∧ `!_spottingEnemies` |
| `AIModule.cpp:1960` | `RNG::shuffle` клеток побега | всегда в `setupEscape` |
| `AIModule.cpp:1995-1996` | ±20 к цели побега | в ветке с замечающими |
| `AIModule.cpp:2016-2018` | ±10, ±10, ±1 отчаянного побега | ветка отчаяния |
| `AIModule.cpp:2368` | `selectRandomTarget`: по броску на каждую известную цель | число бросков = число целей, проходящих `validTarget` |
| `AIModule.cpp:2548` | снайпер: выбор цели | есть хотя бы одна цель |
| `AIModule.cpp:3884` (в `extendedFireModeChoice`) | разброс оценки режима | на каждый доступный режим; у снайпера — на каждую цель с таймером |
| `AIModule.cpp:2845` | выбор режима | всегда в `evaluateAIMode` после входа |
| `AIModule.cpp:3017` | `RNG::shuffle` клеток огня | `findFirePoint`, если `selectClosestKnownEnemy` нашёл цель |
| `AIModule.cpp:4081`, `:4092`, `:4168` | psi: контроль, USE, итог | на каждую известную цель и тип атаки |
| `AIModule.cpp:4338` | рукопашная или стрельба | `_melee && _rifle` |
| `SavedBattleGame.cpp:2325/2328`, `:2378` | узел патруля | `getPatrolNode` |
| `TileEngine.cpp:2892` | выстрел реакции | кандидат реакции найден |
| `ProjectileFlyBState.cpp:207` | sneak-up | ближний бой с `closeQuarters` |

Сдвиг знания меняет число бросков: `selectRandomTarget` (:2368), снайпер (:3884 на цель), psi (:4081/:4092 на цель)
бросают **на каждую известную цель**. Одна лишняя «известная» цель (например, другое значение `turnsSince` или
`intelligence`) сдвигает всю последовательность RNG боя.

## 9. Знание (входы решений → метка)

| вход | метка | файл:строка |
|---|---|---|
| `_knownEnemies` | СТОРОНА | `AIModule.cpp:532` |
| `_visibleEnemies` | СТОРОНА ∧ ЮНИТ(360°, пересчёт) | `:533` |
| `_spottingEnemies` | СТОРОНА ∧ ИСТИНА(геометрия) | `:534` |
| `_closestDist`, `_aggroTarget` | ИСТИНА позиция после фильтра | `:2263-2276` |
| `isCheating()` | ИСТИНА (число живых пришельцев, номер хода) | `SavedBattleGame.cpp:1542-1545` |
| занятость клетки цели/узла | ИСТИНА | `AIModule.cpp:2883`, `:1562`; `SavedBattleGame.cpp:2346` |
| блокеры пути | ЮНИТ (враг) / СТОРОНА сейчас (игрок) | `Pathfinding.cpp:1213-1219` |
| остановка шага | ЮНИТ | `UnitWalkBState.cpp:235` |
| реакция | ЮНИТ + ПАМЯТЬ | `TileEngine.cpp:2611-2623` |
| предметы | ИСТИНА + ЮНИТ (пусто ли видимых) | `BattlescapeGame.cpp:466, 2806-2856` |
| `_toNode`, `_AIMode`, `_wasHitBy` | ПАМЯТЬ | `AIModule.cpp:194-198` |
| `intelligence`, spotter, sniper %, веса | РУЛСЕТ | `BattleUnit.cpp:494`, `Unit.cpp:37, 97, 372`, `Mod.cpp:3918-3922` |

## 10. Слепые пятна (доказано кодом)

1. **Нет последней известной позиции.** В `AIModule` нет поля позиции врага; все системы читают `getPosition()`
   (раздел 4). ИИ не умеет «идти туда, где видел»: либо знает настоящую позицию, либо не знает ничего.
2. **`getSpottingUnits` не смотрит сектор обзора врага, свет, дым, камуфляж** — в функции только `validTarget`,
   расстояние и `canTargetUnit` (`AIModule.cpp:2206-2227`). Клетка «под прицелом» — по чистой геометрии.
3. **`getSpottingUnits` ограничен 20 клетками константой** (`:2211`), при `maxViewDistance: 40` в Пиратках враги на
   21–40 клетках, которые реально видят клетку, не считаются — ни в побеге, ни в засаде, ни в `findFirePoint`.
4. **`getSpottingUnits` у врага не считает нейтралов** (вес 50 не > порога 50, `:2208`), у бота — не считает нейтралов
   (вес −100). Вооружённый нейтрал не «угроза».
5. **`selectNearestTarget` не проверяет сектор обзора** (`visible()` его не читает, `TileEngine.cpp:1864-1930`): юнит
   «видит» известного стороне врага за спиной.
6. **Враги без LOF не входят в `_visibleEnemies`** (`AIModule.cpp:2280-2285`: без `_aggroTarget` возвращается 0) —
   видимый, но недосягаемый враг для выбора режима не существует.
7. **У бота нет засады, пси и снайпера** — `countKnownTargets` возвращает 0 для не-врагов (`:2183`).
8. **Путь врага проходит сквозь не замеченных им самим юнитов**, даже если их видит его сторона (`Pathfinding.cpp:1217-1219`
   читает только список этого юнита). Отсюда остановки «unit» на ходу (`UnitWalkBState.cpp:374-384`).
9. **Нейтралы не видят никого как препятствие, кроме своих** (`Pathfinding.cpp:1206-1225`: ветки PLAYER и HOSTILE не
   срабатывают) и не заполняют `_visibleUnits` (`TileEngine.cpp:1512-1518`).
10. **Попадание в ближнем бою и броском не раскрывает атакующего**: `setWasHitBy` и `turnsSince = 0` только для
    AIMED/SNAP/AUTO (`BattleUnit.cpp:1966-1968`).
11. **`_wasHitBy` в решениях не используется** — только для реакции (`TileEngine.cpp:2611`); стирается в начале
    `think` (`AIModule.cpp:561`).
12. **Свои в `getNodeOfBestEfficacy` штрафуются без проверки знания**, а у бота штрафуются все юниты
    (`AIModule.cpp:4378-4389`, `:4400`).
13. **`explosiveEfficacy` считает юнит на клетке цели «задетым врагом» без проверки знания** (`:3207-3212`); остальные —
    только с весом ≠ 0.
14. **У стороны врага нет видимых клеток** (`calculateTilesInFOV` только для игрока, `TileEngine.cpp:1572`): ИИ не знает,
    какие клетки он осмотрел.
15. **`surveyItems` не проверяет видимость предмета и наличие врагов около него** (`BattlescapeGame.cpp:2806-2856`);
    в Пиратках `pickUpWeaponsMoreActively: true` (`Piratez_Globals.rul:9158-9159`) снимает и условие «брошен на
    ходу ИИ» (`:2820`), и условие «никого не вижу» (`handleAI` :466, `worthTaking` :2876).
16. **`knownRevision` (BLOCKED_STEP) меняется от событий на неразведанной части карты** (`AiProbe.cpp:4027-4036`) —
    запрет шага снимается от того, чего сторона не видела. Ошибка в сторону лишнего пересмотра, не утечки цели.

## 11. Не прослежено

- Может ли `_visibleUnits` держать устаревшую запись, когда наблюдатель и цель вне секторов событий (кэш чистится только
  в секторе события и при полной проверке, `TileEngine.cpp:1480-1531`). Кто читает его в решении — psi (`:4032`),
  предметы — поэтому важно; доказательства устаревания в коде не искал.
- `setupEventVisibilitySector`/`inEventVisibilitySector` (`TileEngine.cpp:1412+`) — точная геометрия сектора события.
- Скрипты Пираток, меняющие снайперский таймер (`Yankes_Scripts.rul:3438-3443` и далее читают/обнуляют
  `TurnsLeftSpottedForSnipers`), и `AiCalculateTargetWeight`, `VisibilityUnit`, `DamageSpecialUnit` — не разобраны.
- `TileEngine::canTargetUnit` — внутренности (какие воксели, учёт других юнитов), читалось как «геометрия LOF».
- `getPatrolNode` целиком (`SavedBattleGame.cpp:2317-2390`) — только место утечки занятости и RNG; подробно в `10_patrol.md`.
- `AiProbe::pickUp`, `watchPoint`, `closeEnemies`, `turretsSeeing`, `flee`, `halfWalk` — зонды и правила бота вне V4,
  знание по ним указано по комментариям и первым строкам, не по полному коду.
- `isSniper()` — определение не открывал (предположительно процент снайпера > 0).
- Порядок `updateTurnsSince` относительно смены фракции под контролем разума (`SavedBattleGame.cpp:1580-1600`) — не
  разбирал.
