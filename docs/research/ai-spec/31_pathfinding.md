# Путь ИИ: Pathfinding (calculate, A*, Bresenham, findReachable, getTUCost)

Область: `src/Battlescape/Pathfinding.cpp/.h`, `PathfindingNode.*`, `PathfindingOpenSet.*`, исполнение пути в
`UnitWalkBState.cpp` (только проверки ОВ и энергии на шаге) и места вызова в `AIModule.cpp` и `BattlescapeGame.cpp::handleAI`.
Выбор целей режимов (патруль, засада, эскейп, точка огня, ближний бой) описан в своих карточках; здесь — только то, как
им отвечает поиск пути и что в этом ответе на самом деле лежит.

Флаги стенда читаются через AiProbe. В сборке без `OXCE_AI_DEV` все функции AiProbe — заглушки, возвращающие false или 0
(`src/Battlescape/AiProbe.cpp:73-168`, блок `#ifndef OXCE_AI_DEV`). Поэтому у игрока в выпуске работает ровно та ветка,
которая в этой карточке помечена «враг без флагов».

---

## 1. Схема

```
AIModule::think()
  ├── [вне V4] KNOWN_OCCUPANT_PATH V1: setKnownOccupant(_unit, knownOccupant) (AIModule.cpp:538-549)
  ├── _reachable = findReachable(_unit, BattleActionCost())                (AIModule.cpp:550)
  │     └── Дейкстра по getTUCost(BAM_NORMAL), бюджет {TU, energy}, сортировка MinNodeCosts (Pathfinding.cpp:1845-1927)
  ├── reachableWithAttack(cost) -> _reachableWithAttack                     (AIModule.cpp:615/620/626/4342 -> :939-945)
  │     └── findReachable(_unit, cost оружия)
  ├── патруль: calculate(_unit, _toNode, BAM_NORMAL)                       (AIModule.cpp:1592)
  │     └── [STALE_EXACT] witnessReach(...) / settleWitness / полный calculate (AIModule.cpp:1436-1488)
  ├── засада: calculateKnownOccupantV2(pos) -> calculate(_unit,pos)        (AIModule.cpp:1694, :1106-1118)
  │     ├── ambushTUs = getTotalTUCost()                                    (AIModule.cpp:1695)
  │     └── calculate(_aggroTarget, pos, BAM_NORMAL)  путь врага           (AIModule.cpp:1721)
  ├── эскейп: calculate(_unit, target, _escapeAction.getMoveType())        (AIModule.cpp:2107)
  │     └── _escapeTUs = getTotalTUCost()                                   (AIModule.cpp:2113)
  ├── точка огня: calculateKnownOccupantV2(pos)                             (AIModule.cpp:3070)
  │     └── score += TU - getTotalTUCost()                                  (AIModule.cpp:3095)
  ├── ближний бой: calculate(_unit, checkPath, BAM_NORMAL, 0, maxTUs)      (AIModule.cpp:2419)
  │     └── Leeroy: calculate(..., canRun?BAM_RUN:BAM_NORMAL, 0, 100000)    (AIModule.cpp:2475)
  └── evalFire [вне V4]: findReachable(cheapestCost) + reachedTU           (AIModule.cpp:3677-3682)

BattlescapeGame::handleAI(), action.type == BA_WALK                         (BattlescapeGame.cpp:507-553)
  ├── [KNOWN_OCCUPANT_PATH_V2] setKnownOccupant(actor, ko2)                 (:514-520)
  ├── calculate(action.actor, action.target, BAM_NORMAL)                    (:521)
  ├── [BLOCKED_STEP] AiProbe::blockedStepPlan -> setBannedFirst + calculate (:523; AiProbe.cpp:4403-4440)
  ├── [PATROL_STUN_PREFIX, careful] patrolStunReserve -> keepPathPrefix / abortPath (:536-540)
  ├── [вне V4] patrolOutOfEnergy -> spendPatrol                              (:541-544)
  ├── путь есть -> UnitWalkBState                                           (:545-548)
  └── путь пуст и walkToItem -> targetTile->setDangerous(true)             (:549-552)

Pathfinding::calculate(unit, end, bam, missileTarget=0, maxTUCost=1000)    (Pathfinding.cpp:172-290; .h:243)
  ├── зонды Trace / pathAsk                                                  (:175-220)
  ├── tryCalculateFinalPosition -> нет -> return (путь пуст)               (:227-229; :88-144)
  ├── strafe                                                                 (:235-252)
  ├── sneak = Options::sneakyAI && FACTION_HOSTILE                           (:254)
  ├── bresenhamPath(start,end,bam,missileTarget,sneak)  — БЕЗ maxTUCost     (:258)
  │     └── удача и первый шаг не запрещён -> return                         (:258-266)
  ├── снаряд и maxTUCost == -1 -> 10000                                      (:272-275)
  └── aStarPath(..., sneak, maxTUCost) -> неудача -> abortPath              (:277-285)

UnitWalkBState::think() (на каждом шаге)                                   (UnitWalkBState.cpp:305-397)
  ├── getTUCost(pos, dir, unit, 0, action.getMoveType())
  ├── INVALID -> стоп "invalid"; tu > TU -> стоп "tu"; energy > Energy -> стоп "energy"
  ├── чужой юнит в клетке -> increaseAIWalkAbortCounter, стоп "unit"
  └── spendTimeUnits(tu), spendEnergy(energy)
```

---

## 2. Развилки

### 2.1. calculate: вход и конечная клетка

```
УСЛОВИЕ:   !tryCalculateFinalPosition(...) (endPosition вне карты, isBlocked(_unit, dest, O_FLOOR/O_OBJECT),
           верхний этаж при подъёме по лестнице/полу)
ДАННЫЕ:    клетки карты, юниты в клетке назначения — ИСТИНА о местоположении, отфильтрованная isBlocked по фракции (см. 2.6)
RNG:       нет
РЕЗУЛЬТАТ: путь пуст, getStartDirection() == -1
ВОЗВРАТ:   return из calculate
СТОРОНЫ:   оба
```
Ссылки: `Pathfinding.cpp:227-229`, `:96-99` (вне карты), `:107-109` (блок назначения), `:113-122` (лестница и пол на
уровне -24 поднимают z на 1), `:126-129` (выше верхнего этажа — отказ). Если юнит не летает и это не снаряд, назначение
опускается вниз, пока выполняется `canFallDown(size)`; исключение — лестница у юнита размера 1 (`:130-138`). После спуска
блокировка проверяется ещё раз (`:140-141`). `finalPositionFor` (`:156-163`) — та же функция для чужого юнита: временно
подставляет его в `_unit`. Её зовёт засада для памяти досягаемости врага (`AIModule.cpp:1712`).

Следствие: если ИИ просит путь к клетке в воздухе, путь строится к земле под ней, а не к самой клетке.

### 2.2. calculate: прямой путь (Bresenham)

```
УСЛОВИЕ:   bresenhamPath(startPosition, endPosition, bam, missileTarget, sneak)
           && (_bannedFirst.empty() || _path.empty() || !bannedFirst(_path.front()))
ДАННЫЕ:    getTUCost каждого шага (ИСТИНА о карте; юниты — по 2.6); sneak -> Tile::getVisible() (ИСТИНА о зрении игрока, см. 2.5)
RNG:       нет
РЕЗУЛЬТАТ: _path — прямая; _totalTUCost = сумма cost + penalty (кроме снаряда)
ВОЗВРАТ:   return (A* не запускается)
СТОРОНЫ:   оба
```
Ссылки: `Pathfinding.cpp:258-266`, вызов без `maxTUCost` (`:258`). В `bresenhamPath` параметр `maxTUCost` в теле не
используется ни разу (`:1704-1836`). Прямая принимается, только если цена шага та же, что у предыдущего (или
диагональный эквивалент, или это первый шаг) и направление не заблокировано, иначе false (`:1800-1808`). Если включён
sneak и любая клетка прямой видна игроку, прямая отвергается (`:1794`). `_totalTUCost` обнуляется (`:1719`) и копится
(`:1809-1813`).

Если первый шаг прямой стоит в `_bannedFirst` (BLOCKED_STEP), сделанный путь сбрасывается (`abortPath`, `:269`), и
дальше идёт A*.

**Обход лимита:** если прямая удалась, ограничение ОВ (`maxTUCost`) не проверялось. Поэтому путь может стоить больше
бюджета, который передал вызывающий (ближний бой с `chargeReserve`, `AIModule.cpp:3312` -> `:2419`).

### 2.3. aStarPath

```
УСЛОВИЕ:   прямая не удалась
ДАННЫЕ:    getTUCost(…, bam) по 10 направлениям (ИСТИНА карты; юниты — 2.6); sneak -> Tile::getVisible()
RNG:       нет
РЕЗУЛЬТАТ: _path к цели или пусто; _totalTUCost = цена ПОСЛЕДНЕЙ ослабленной соседней клетки (не пути)
ПРЕРЫВАНИЕ: открытый список исчерпан (всё, что дешевле maxTUCost, просмотрено)
ВОЗВРАТ:   true (путь) / false -> abortPath в calculate (:278-285)
СТОРОНЫ:   оба
```
Ссылки:
- `Pathfinding.cpp:358-416`: сброс всех узлов `:361-364`, старт `:368`, извлечение и `setChecked` `:375-378`;
- цель найдена -> восстановление пути `:379-389`;
- направления 0..9, пропуск запрещённого первого шага `:392-395`; INVALID — пропуск `:396-398`;
- `if (sneak && _save->getTile(nextPos)->getVisible()) r.cost.time *= 2;` `:401`;
- `_totalTUCost = currentNode->getTUCost(missile) + r.cost + r.penalty;` `:405`;
- соседняя клетка ослабляется, если её ещё нет в открытом списке или новая цена по времени лучше, и при этом
  `_totalTUCost.time <= maxTUCost` (`:407-411`). Энергия здесь не ограничена.

Порядок открытого списка: `_cost = time*4 + guess` (`PathfindingOpenSet.cpp:75`), `guess = 4 * Position::distance(target, pos)`
(`PathfindingNode.cpp:101`) — то есть g в ОВ плюс евклидово расстояние в клетках (3D, `Position.h:93-96`).
`std::priority_queue`, устаревшие записи отбрасываются по `_openentry` (`PathfindingOpenSet.cpp:37-61`).

Эвристика слабая: 1 на клетку при цене шага около 4 ОВ. Переоценить она может только там, где шаг стоит меньше 1 на
клетку расстояния. Так бывает на падении (цена 0, `Pathfinding.cpp:828-831`) и при очень малых процентах брони. Поэтому
в редких случаях A* вернёт не самый дешёвый путь.

Комментарий в коде прямо признаёт: «after A* _totalTUCost is the last node tried, not the path» (`Pathfinding.cpp:2004`).
`getTotalTUCost()` возвращает `_totalTUCost.time` (`Pathfinding.h:318`).

### 2.4. calculate: лимит ОВ

| Вызов | maxTUCost | Файл:строка |
|---|---|---|
| по умолчанию | 1000 | `Pathfinding.h:243` |
| снаряд с maxTUCost == -1 и BAM_MISSILE | 10000 | `Pathfinding.cpp:272-275` |
| ближний бой selectPointNearTarget | maxTUs (TU юнита или chargeReserve) | `AIModule.cpp:2419` (`:2267`, `:3312`) |
| Leeroy | 100000 | `AIModule.cpp:2475` |
| все остальные места ИИ (патруль, засада, эскейп, точка огня, ходьба handleAI) | 1000 | `AIModule.cpp:1592`, `:1112-1116`, `:2107`; `BattlescapeGame.cpp:521` |

То есть у патруля, засады, эскейпа и точки огня сам поиск пути текущими ОВ юнита не ограничен. Досягаемость отсекает
вызывающий — фильтром `_reachable` или `_reachableWithAttack` (см. карточки режимов). Где фильтра нет, путь
может быть длиннее хода (патруль к узлу, `AIModule.cpp:1592`): юнит идёт, пока хватает ОВ, и останавливается на «tu»
(2.10).

### 2.5. sneakyAI

```
УСЛОВИЕ:   Options::sneakyAI && unit->getFaction() == FACTION_HOSTILE
ДАННЫЕ:    Tile::getVisible() — сколько юнитов ИГРОКА сейчас видят клетку (ИСТИНА о зрении противника)
RNG:       нет
РЕЗУЛЬТАТ: A*: цена шага в видимую клетку x2; Bresenham: прямая через видимую клетку отвергается
СТОРОНЫ:   только враг; бот (FACTION_PLAYER) — никогда
```
Ссылки: `Pathfinding.cpp:254`, `:401`, `:1794`, `witnessReach` `:1022`, `:1059`. `Tile::_visible` увеличивают только
юниты-игроки (`TileEngine.cpp:1572` — return, если не FACTION_PLAYER; `:1661` setVisible(+1)). Умолчание опции —
false (`src/Engine/Options.cpp:256`). В options.cfg установки Пираток `sneakyAI: false` (строка 412). Удвоение
действует только в поиске: в `findReachable` sneak нет (`Pathfinding.cpp:1874`), при ходьбе цена берётся без удвоения
(`UnitWalkBState.cpp:306`), а `_totalTUCost` после A* уже включает удвоенную цену соседней клетки.

### 2.6. Юниты как препятствия: isBlocked, часть O_FLOOR

```
УСЛОВИЕ:   tile->getUnit() && !(_probeIgnore & IGNORE_ALL_UNITS)                     (:1206)
           u == unit || u == missileTarget || u->isOut() -> НЕ блок                  (:1209-1210)
           unit->getFaction() == FACTION_PLAYER && u->getVisible() -> блок            (:1213-1214)
           unit->getFaction() == u->getFaction() -> блок                              (:1215-1216)
           FACTION_HOSTILE && u ∈ unit->getUnitsSpottedThisTurn() -> блок             (:1217-1219)
           u == _knownOccupant && unit == _knownOccupantFor && bam != BAM_MISSILE
             -> ++_knownOccupantHits, блок                                            (:1221-1225)
           иначе — проходимо
ДАННЫЕ:    положение u — ИСТИНА (настоящая текущая клетка); u->getVisible() — СТОРОНА (видим игроку);
           getUnitsSpottedThisTurn — ЮНИТ/ПАМЯТЬ (кого видел сам этот юнит в этот ход)
RNG:       нет
РЕЗУЛЬТАТ: клетка недоступна в getTUCost (:567-570) -> INVALID
СТОРОНЫ:   см. таблицу
```

| Кто ищет | Кого считает препятствием | Метка |
|---|---|---|
| бот (FACTION_PLAYER) | своих; чужих, видимых игроку сейчас (`u->getVisible()`) | СТОРОНА |
| враг (FACTION_HOSTILE) | своих; тех, кого видел САМ в этот ход (`getUnitsSpottedThisTurn`), по их НАСТОЯЩЕЙ текущей клетке | ЮНИТ/ПАМЯТЬ + ИСТИНА позиции |
| нейтрал (FACTION_NEUTRAL) | только своих | — |

Список `getUnitsSpottedThisTurn` пополняется в `addToVisibleUnits` (`BattleUnit.cpp:2408-2422`) и очищается в
`prepareNewTurn` (`:2866`). Враг, которого видела только сторона, а сам юнит нет, для поиска проходим. Тот, кого юнит
видел и потерял из виду, блокирует клетку, где стоит СЕЙЧАС: позиция берётся из `tile->getUnit()`, а не из памяти.

Непредусмотренное препятствие обнаруживается при ходьбе: `UnitWalkBState.cpp:368-384` — `increaseAIWalkAbortCounter`,
стоп «unit». Кроме того, если на ходу юнит заметит врага, следующая проверка `getTUCost` на шаге (`UnitWalkBState.cpp:306`)
может вернуть INVALID — стоп «invalid» (`:311-315`).

Большие стены, падение больших юнитов, двери для снарядов: `Pathfinding.cpp:1166-1202`, `:1228-1256`, `:1259-1268`.
Если `Tile::getTUCost(part, movementType) == 255` — блок (`:1269`).

### 2.7. KNOWN_OCCUPANT_PATH_V2 (V4)

```
УСЛОВИЕ:   AiProbe::knownOccupantPathV2() && _unit->getFaction() == FACTION_HOSTILE && _aggroTarget
           && _aggroTarget->getTurnsSinceSpottedByFaction(faction) == 0                 (AIModule.cpp:1089-1100)
ДАННЫЕ:    getTurnsSinceSpottedByFaction — СТОРОНА (сторона видела цель в этот ход)
RNG:       нет
РЕЗУЛЬТАТ: на время ОДНОГО calculate клетка _aggroTarget считается занятой (setKnownOccupant/…/setKnownOccupant(0,0))
СТОРОНЫ:   только враг и только при V2 (у бота knownOccupantV2 возвращает 0 — FACTION_HOSTILE)
```
Где действует:
- точка огня — `calculateKnownOccupantV2`, `AIModule.cpp:3070`;
- засада — `:1694`;
- ходьба к точке, которую выбрали эти две ветки: `knownOccupantV2Walk` (`AIModule.cpp:1138-1148`), применяется в
  `BattlescapeGame.cpp:514-528`. Условия — действие BA_WALK, цель совпадает с `_ko2WalkTo`, цель не isOut, сторона
  видела её в этот ход (`getTurnsSinceSpottedByFaction == 0`).

Флаг включён, только если `active && env V2 && !V1` (`AiProbe.cpp:4111-4114`).

Что меняется по сравнению с прежним поведением: сам юнит цель в этот ход не видел, а сторона видела — без V2 клетка
цели проходима (2.6), с V2 нет. Если юнит видел цель сам, она уже в `getUnitsSpottedThisTurn`, срабатывает ветка
`:1217-1219` раньше, и счётчик `_knownOccupantHits` не растёт. `findReachable` под V2 этот блок не получает: `_reachable`
и `_reachableWithAttack` считаются без него. Другие враги, видимые только стороной, остаются проходимыми.

V1 (`OXCE_AI_KNOWN_OCCUPANT_PATH`, вне V4) ставит занимающего ПЕРЕД `findReachable` и оставляет на весь think
(`AIModule.cpp:538-549`).

### 2.8. findReachable (кандидаты клеток)

```
УСЛОВИЕ:   всегда, при каждом think (AIModule.cpp:550); при оружии — ещё раз с ценой атаки (:939-945)
ДАННЫЕ:    unit->getTimeUnits(), unit->getEnergy() — ЮНИТ; getTUCost(BAM_NORMAL) — ИСТИНА карты, юниты по 2.6
RNG:       нет
РЕЗУЛЬТАТ: вектор индексов клеток, отсортированный MinNodeCosts; узлы держат цену до клетки (reachedTU)
СТОРОНЫ:   оба
```
Ссылки: `Pathfinding.cpp:1845-1927`.
- Бюджет: `tuMax = unit->getTimeUnits() - cost.Time`, `energyMax = unit->getEnergy() - cost.Energy` (`:1852-1855`).
- Цена шага: всегда `BAM_NORMAL`, без sneak, без missileTarget (`:1874`). Штраф огня входит в бюджет ОВ:
  `currentNode->getTUCost(false) + r.cost + r.penalty` (`:1877`).
- Отсечение: `if (!(totalTuCost <= costMax)) continue;` (`:1878`), где `<=` — это time<= и energy<=
  (`PathfindingNode.h`, operator<=).
- Ослабление только по времени: `nextNode->getTUCost(false).time > totalTuCost.time` (`:1884`).
- В результат идёт каждый извлечённый узел, включая стартовую клетку (`:1891`).
- `std::sort(reachable.begin(), reachable.end(), MinNodeCosts());` (`:1893`). Сравнение —
  `a->getTUCost(false) < b->getTUCost(false)`, а `<` означает time< И energy< (`PathfindingNode.h:136-149` и operator<).
  Это не строгий слабый порядок (несравнимые пары нетранзитивны), поэтому порядок «по возрастанию цены» не гарантирован,
  а по стандарту поведение std::sort с таким компаратором не определено.

`reachedTU(pos)` (`:1934-1938`) читает цену из узлов: `isChecked() ? time : -1`. Любой следующий `calculate` сбрасывает
все узлы (`:361-364`), поэтому `reachedTU` годен только до первого `calculate` после `findReachable`.

Зонд: `reachWanted` -> `reachTaken` (`:1914-1925`) — передача ответа в запись решения; на результат не влияет.

### 2.9. getTUCost (цена шага)

```
УСЛОВИЕ:   (startPosition, direction, unit, missileTarget, bam)
ДАННЫЕ:    клетки, стены, полы, объекты, огонь, дым — ИСТИНА; armor moveCost — РУЛСЕТ; юниты — 2.6
RNG:       нет
РЕЗУЛЬТАТ: PathfindingStep { cost{time,energy}, penalty{firePenalty,0}, pos }
СТОРОНЫ:   оба; штраф огня — не для FACTION_PLAYER
```
По порядку (`Pathfinding.cpp:430-933`):
1. Части юнита size 1 или 2 (`:438-439`). Нет клетки -> INVALID (`:468-471`).
2. `isBlockedDirection` и перепад terrainLevel больше 8 -> INVALID (`:486-493`). Маски подъёма, спуска, падения, полёта,
   лазания (`:480-539`). Лазание только при `size == 1` и не летуне (`:484`).
3. Полёт: перекрывающий юнит (TUO_IGNORE_SMALL) -> INVALID (`:504-512`). Ходьба по воздуху -> INVALID (`:547-553`).
4. Назначение заблокировано (`isBlocked` O_FLOOR/O_OBJECT, 2.6) -> INVALID (`:567-570`).
5. Юнит 2x2: дверь на северной или западной стене в `destinationTile[3]` -> INVALID (`:574-582`).
6. Огонь: `if (unit->getFaction() != FACTION_PLAYER && unit->avoidsFire())` и в любой клетке назначения `getFire() > 0`
   -> `firePenaltyCost = FIRE_PREVIEW_MOVE_COST` (32). Это штраф (penalty), а не цена (`:585-596`).
7. Вверх или вниз через `validateUpDown`: по лестнице — минимум из ОВ лестницы, но не меньше 8; полёт или гравилифт — 8;
   иначе INVALID (`:615-651`).
8. Стены на пути шага: средняя цена, ≥255 -> INVALID (`:666-718`). Нет пола -> 4 (`:721-724`). Пол плюс объект (кроме
   лестниц), 0 -> 4, подъём на этаж +1 (`:727-744`).
9. Диагональ: `cost = (int)((double)cost * 1.5)` (`:747-750`).
10. Подводный бой: `_save->getDepth() > 0 && (getFire() > 0 || getSmoke() > 0)` -> +2 (`:755-758`). На суше дым цену
    не меняет.
11. Снаряд с целью: дружественный юнит в клетке -> INVALID; чужой не-цель, если
    `unit->getUnitRules() && getTurnsSinceSpottedByFaction(...) <= getIntelligence()` -> INVALID (`:760-774`).
12. Strafe +1, если направление не совпадает (`:778-784`). Потолок шага `MAX_MOVE_COST` 100 (`:787`).
13. Юнит 2x2: `totalCost /= numberOfParts` и проверки по X (`:803-820`).
14. Снаряд -> цена 0 (`:823-826`). Падение (`DIR_DOWN && fallingDown`) -> цена 0, только штраф (`:828-831`).
15. Множители брони в процентах: `costDiv = 100*100*100` (`:833`); база юнита (`:836`); база лазания, полёта или
    обычная (`:838-849`); по направлению и bam: climb up/down, fly up/down, gravlift, walk/flyWalk, run/flyRun,
    strafe/flyStrafe, sneak (`:851-922`).
16. Округление по `Mod::EXTENDED_MOVEMENT_COST_ROUNDING`: 0 — вниз, 1 — к ближнему, 2 — к ближнему с половиной вниз
    (`:924-930`). Возврат `Clamp(time, 1, 254)`, `Clamp(energy, 0, 255)` (`:932`).

`getMovementType` (`:1134-1151`): снаряд -> FLY; `BAM_SNEAK` -> WALK.

### 2.10. Исполнение пути: нехватка посреди пути

```
УСЛОВИЕ:   на каждом шаге UnitWalkBState пересчитывает getTUCost(pos, dir, unit, 0, action.getMoveType())
ДАННЫЕ:    TU, Energy юнита — ЮНИТ; клетки и юниты — ИСТИНА / 2.6
RNG:       нет
РЕЗУЛЬТАТ: стоп с остатком пути: "invalid" / "tu" / "energy" / "reserve" / "unit"
ПРЕРЫВАНИЕ: cancelCurentMove
СТОРОНЫ:   оба; "reserve" только при getPanicHandled()
```
Ссылки: `UnitWalkBState.cpp:305-309` (цена шага без штрафа огня, без удвоения sneak), `:311-315` (invalid),
`:317-325` (tu), `:328-335` (energy), `:338-342` (reserve, `checkReservedTU`, только `_parent->getPanicHandled()`),
`:368-384` (юнит в клетке), `:394-397` (списание `spendTimeUnits`, `spendEnergy`). Перед ходьбой юнит встаёт с колен
(`UnitWalkBState.cpp:103-117`); вставание тратит ОВ (`BattlescapeGame.cpp:618-641`), и ни `findReachable`, ни
`calculate` это не учитывают (вычет `KneelUpCost` есть только в превью `refreshPath`, `Pathfinding.cpp:1570-1576`).

Энергия не ограничивает `calculate` и A* (`Pathfinding.cpp:407-411` сравнивает только time). Если путь длиннее запаса
энергии, юнит дойдёт до шага, на который энергии нет, и встанет посреди пути (стоп «energy»). Восстановление энергии
между ходами — в `BattleUnit::prepareNewTurn`, в этой карточке не прослежено. Связь с оглушением на патруле —
см. PATROL_STUN_PREFIX (2.13).

### 2.11. Ход ИИ: путь в handleAI (BA_WALK)

```
УСЛОВИЕ:   action.type == BA_WALK                                           (BattlescapeGame.cpp:507)
ДАННЫЕ:    action.target, action.actor; ko2 (V2)
RNG:       нет
РЕЗУЛЬТАТ: calculate(action.actor, action.target, BAM_NORMAL)               (:521)
ВОЗВРАТ:   getStartDirection() != -1 -> UnitWalkBState (:545-548); иначе при walkToItem -> setDangerous(true) (:549-552)
СТОРОНЫ:   оба
```
Путь здесь ВСЕГДА считается с `BAM_NORMAL`, а идёт юнит с `action.getMoveType()` (`UnitWalkBState.cpp:306`).
`getMoveType` даёт `BAM_RUN` при `action.run` (`BattlescapeGame.h:98-100`). У эскейпа на нечётных попытках `run` = true
(`AIModule.cpp:1966`), у Leeroy `run = canRun` (`:3362`). Значит, эскейп оценивал клетку по пути и цене бега
(`AIModule.cpp:2107`, `:2113`), а путь для ходьбы перестроен с ценой шага — маршрут может отличаться, ОВ и энергия
списываются по цене бега.

### 2.12. BLOCKED_STEP (V4)

```
УСЛОВИЕ:   blockedStepOn() && у юнита записан запрещённый первый шаг && первый шаг нового пути ∈ dirs   (AiProbe.cpp:4403-4419)
ДАННЫЕ:    blockedSteps (ПАМЯТЬ стенда: шаги, на которых ходьба уже упиралась в этот ход)
RNG:       нет
РЕЗУЛЬТАТ: setBannedFirst(dirs); calculate(BAM_NORMAL); setBannedFirst({})                          (:4433-4435)
ПРЕРЫВАНИЕ: нового пути нет -> unit->increaseAIWalkAbortCounter() (:4440); путь пуст -> ходьбы нет
СТОРОНЫ:   оба при флаге (env OXCE_AI_BLOCKED_STEP, AiProbe.cpp:4285)
```
Запрет первого шага уважают и Bresenham (`Pathfinding.cpp:258`), и A* (`:392-395`), и `witnessReach` (`:1054`).
Отслеживание запрета — зонды (`blockedBump`, `tallies`).

### 2.13. PATROL_STUN_PREFIX (V4, только careful)

Только ссылкой: `AiProbe::patrolStunReserve` (`AiProbe.cpp:3888-3968`) у бота с CAREFUL обрезает путь патруля до
безопасного начала (`Pathfinding::keepPathPrefix`, `Pathfinding.cpp:1992-2000`, под `#ifdef OXCE_AI_DEV`) или, если
безопасного шага нет, путь сбрасывается (`BattlescapeGame.cpp:536-540`). У врага ветка не работает (careful = bot &&
OXCE_AI_CAREFUL && FACTION_PLAYER, `AiProbe.cpp:367-371`). Подробности — в карточке патруля.

### 2.14. STALE_EXACT / STALE_PATROL_NODE (V4): witnessReach

```
УСЛОВИЕ:   staleExact (param OXCE_AI_STALE_EXACT 0..3, AiProbe.cpp:4242-4246) и нет известного занимающего (AIModule.cpp:1436-1488)
ДАННЫЕ:    те же getTUCost (sneak — тот же, :1022, :1059), запрет первого шага (:1054)
RNG:       нет
РЕЗУЛЬТАТ: -1 отказ; 3 уже на цели; 1 путь найден в пределах cap; 2 cap что-то отбросил; 0 пути нет  (Pathfinding.cpp:1006-1099)
ВОЗВРАТ:   ans == 2 -> полный calculate (AIModule.cpp:1465); иначе settleWitness (:1481); нет пути -> freePatrolTarget
СТОРОНЫ:   оба при флаге
```
`witnessReach` держит собственные массивы, cap = 1000 (`Pathfinding.cpp:1023`), эвристика `weight*4*dist` (`:1030`),
вызывается с weight 4. Результат 1 — только если `4*cost + unpaid <= 4*cap`, иначе 2 (`:1078-1090`).
`settleWitness` переносит найденный путь в `_path` (`:1108-1116`). Сама функция не стоит под `#ifdef`, но вызывается
только при флаге стенда.

### 2.15. Пустой путь или недостижимая цель

| Где | Что происходит | Файл:строка |
|---|---|---|
| `calculate` | `_path` пуст, `getStartDirection() == -1` | `Pathfinding.cpp:939-943` |
| патруль, новый узел | `_toNode = 0`, до 5 попыток выбрать узел (`triesLeft`) | `AIModule.cpp:1429`, `:1496`, `:1592-1595` |
| STALE-патруль | `freePatrolTarget` | `AIModule.cpp:1436-1488` |
| засада | узел пропускается (`ownPath == false`); нет пути врага — узел без очков засады | `AIModule.cpp:1697-1699`, `:1723` |
| эскейп | клетка не принимается (кроме своей клетки, там `_escapeTUs = 1`) | `AIModule.cpp:2108-2117` |
| точка огня | клетка не принимается | `AIModule.cpp:3070-3095` (карточка огня) |
| ближний бой | клетка не принимается | `AIModule.cpp:2419-2425`, `:2476` |
| handleAI ходьба | ходьбы нет; walkToItem -> клетка `setDangerous(true)` до конца хода | `BattlescapeGame.cpp:545-552` |
| BLOCKED_STEP без пути | `increaseAIWalkAbortCounter` | `AiProbe.cpp:4440` |
| ходьба упёрлась в юнита | `increaseAIWalkAbortCounter`, стоп | `UnitWalkBState.cpp:368-384` |

`closedTiles()` (`Pathfinding.cpp:303-324`) отдаёт закрытое множество последнего A*, если путь не найден. Пусто, если
`_expanded == 0` или путь найден. Очищается, если у любой закрытой клетки `time*2 > _searchCap`. Это использует
память засады `enemyReach` (`AIModule.cpp:1732`).

---

## 3. Числа

| Имя | Значение | Выражение | Файл:строка | На что влияет |
|---|---|---|---|---|
| DEFAULT_MOVE_COST | 4 | — | `Pathfinding.h:120-128` | цена клетки без пола или с нулевой ценой |
| DEFAULT_MOVE_FLY_COST | 8 | — | `Pathfinding.h:120-128` | полёт вверх и вниз, гравилифт |
| MAX_MOVE_COST | 100 | `std::min(cost, +MAX_MOVE_COST)` | `Pathfinding.cpp:787` | потолок шага до процентов брони |
| INVALID_MOVE_COST | 255 | — | `Pathfinding.h:120-128` | непроходимо; Clamp time до 254 |
| FIRE_PREVIEW_MOVE_COST | 32 | penalty | `Pathfinding.cpp:585-596` | штраф огня (не бот) |
| лестница/полёт вверх-вниз | ≥8 | min(ladder TU, …), не меньше 8 | `Pathfinding.cpp:615-651` | шаги DIR_UP/DIR_DOWN |
| диагональ | ×1.5 | `(int)((double)cost * 1.5)` | `Pathfinding.cpp:749` | цена диагонали (усечение) |
| подъём объектом на этаж | +1 | — | `Pathfinding.cpp:727-744` | ступени |
| подводный огонь/дым | +2 | `getDepth()>0 && (fire||smoke)` | `Pathfinding.cpp:755-758` | только TFTD |
| strafe | +1 | направление ≠ взгляд | `Pathfinding.cpp:778-784` | BAM_STRAFE |
| sneak | ×2 time | `tile->getVisible()` | `Pathfinding.cpp:401` | A* врага при sneakyAI |
| size 2 | /4 | `totalCost /= numberOfParts` | `Pathfinding.cpp:805` | цена 2x2 |
| падение | 0 | — | `Pathfinding.cpp:828-831` | спуск без опоры |
| costDiv | 1 000 000 | `100*100*100` | `Pathfinding.cpp:833` | три процента подряд |
| округление | 0/1/2 | `EXTENDED_MOVEMENT_COST_ROUNDING` | `Pathfinding.cpp:924-930` | у Пираток 2 (`Piratez_Globals.rul:9173`, `extendedMovementCostRounding`) |
| Clamp | time 1..254, energy 0..255 | — | `Pathfinding.cpp:932` | минимум 1 ОВ на шаг |
| приоритет A* | `time*4 + 4*dist` | Sint16 | `PathfindingOpenSet.cpp:75`, `PathfindingNode.cpp:101` | порядок раскрытия |
| maxTUCost по умолчанию | 1000 | — | `Pathfinding.h:243` | потолок поиска |
| maxTUCost снаряда | 10000 | при -1 | `Pathfinding.cpp:272-275` | бластер |
| Leeroy | 100000 | — | `AIModule.cpp:2475` | поиск без лимита |
| witnessReach cap | 1000 | — | `Pathfinding.cpp:1023` | STALE_EXACT |
| witnessReach weight | 4 | аргумент | `AIModule.cpp:1436-1488` | эвристика `weight*4*dist` |
| closedTiles сброс | `time*2 > _searchCap` | — | `Pathfinding.cpp:303-324` | память enemyReach |
| попытки патруля | 5 | `int triesLeft = 5` | `AIModule.cpp:1429` | выбор узла при пустом пути |
| превью red/yellow/green | 3/10/4 | — | `Pathfinding.cpp:45-47` | только цвета маркеров |

Проценты брони по умолчанию (поле рулсета `moveCost.*Percent`, `Armor.cpp:134-156`; умолчания `Armor.h:140-156`, пары
ОВ/энергия):

| Поле | ОВ % | Энергия % |
|---|---|---|
| base, baseFly, baseClimb, baseNormal | 100 | 100 |
| walk, strafe, sneak | 100 | 50 |
| run | 75 | 75 |
| flyWalk, flyStrafe | 100 | 50 |
| flyRun | 75 | 75 |
| flyUp, flyDown | 100 | 0 |
| climbUp, climbDown | 100 | 50 |
| gravLift | 100 | 0 |

База юнита копируется из брони (`BattleUnit.cpp:160-163`). Скрипт может задать её через `MoveCost.set*`
(`BattleUnit.cpp:6906-6913`), но в скриптах Пираток таких вызовов не найдено. У Пираток `moveCost` есть в 49 бронях,
в основном `flyDownPercent [0,0]`; есть `baseFlyPercent` и `fly*`, у LOKNAR `runPercent [50,125]`.

---

## 4. RNG

В `Pathfinding.cpp`, `PathfindingNode.cpp`, `PathfindingOpenSet.cpp` вызовов `RNG::` нет (grep `RNG` по трём файлам
пуст). Равные варианты решают порядок направлений 0..9 (`Pathfinding.cpp:392`, `:1872`) и куча `std::priority_queue`
(`PathfindingOpenSet.cpp:37-61`) — детерминированно при одинаковой карте и одинаковом порядке вызовов.

Поиск пути не тратит броски, поэтому лишний или пропущенный `calculate` или `findReachable` последовательность RNG не
сдвигает. Он влияет только через результат: другой ответ -> другая ветка вызывающего -> другое число бросков дальше.

Броски у вызывающих, которые решают, куда искать путь (вне этой области, для сверки):

| Файл:строка | Вызов | Что решает | Когда |
|---|---|---|---|
| `AIModule.cpp:1960` | `RNG::shuffle(randomTileSearch)` | порядок клеток эскейпа | при поиске эскейпа |
| `AIModule.cpp:2368` | `RNG::generate(0,20)` | выбор ближайшей цели (дальше путь к ней) | selectNearestTarget |
| `AIModule.cpp:3017` | `RNG::shuffle(randomTileSearch)` | порядок клеток findFirePoint | при поиске точки огня |
| `BattlescapeGame.cpp:1733` | `RNG::generate(-5,5)` ×2, до 20 попыток | клетка бегства в панике, затем `calculate` (`:1745`) | паника |

Неопределённое поведение `std::sort` с `MinNodeCosts` (2.8) — не RNG, но порядок `_reachable` может зависеть от
реализации стандартной библиотеки. Для одной сборки он воспроизводим.

---

## 5. Знание

| Вход | Где читается | Метка | Комментарий |
|---|---|---|---|
| стены, полы, объекты, двери, terrainLevel | `getTUCost`, `isBlocked`, `isBlockedDirection` | ИСТИНА | вся карта, без учёта разведанности |
| огонь в клетке | `Pathfinding.cpp:585-596`, `:755` | ИСТИНА | без проверки, видел ли юнит огонь |
| дым | `Pathfinding.cpp:755` | ИСТИНА | только при `getDepth() > 0` |
| свои юниты | `isBlocked :1215` | ИСТИНА | всегда блок |
| чужие юниты для бота | `isBlocked :1213` (`u->getVisible()`) | СТОРОНА | видимые игроку сейчас |
| чужие юниты для врага | `isBlocked :1217-1219` | ЮНИТ/ПАМЯТЬ + ИСТИНА позиции | замеченные САМИМ юнитом в этот ход, по настоящей клетке |
| цель V2 | `isBlocked :1221-1225` | СТОРОНА | `getTurnsSinceSpottedByFaction == 0` |
| юниты для снаряда | `getTUCost :760-774` | СТОРОНА + РУЛСЕТ | `getTurnsSinceSpottedByFaction <= getIntelligence()`; без `getUnitRules()` (солдаты) ветки нет |
| видимость клетки (sneak) | `Pathfinding.cpp:401`, `:1794` | ИСТИНА (зрение игрока) | только враг, только при sneakyAI |
| ОВ, энергия | `findReachable :1852-1853`; `UnitWalkBState :317-335` | ЮНИТ | — |
| проценты брони | `getTUCost :836-922` | РУЛСЕТ | `moveCost.*Percent`, база юнита |
| avoidsFire | `getTUCost :586` | РУЛСЕТ | `BattleUnit.cpp:5912-5919`: поле юнита, иначе `specab < BURNFLOOR`; у Пираток поле не задано |
| sneakyAI | `calculate :254` | опция | `Options.cpp:256`, false |
| EXTENDED_MOVEMENT_COST_ROUNDING | `getTUCost :924-930` | РУЛСЕТ | Пиратки 2 |
| запрещённый первый шаг | `_bannedFirst` | ПАМЯТЬ стенда | BLOCKED_STEP |
| память досягаемости врага | `closedTiles`, `finalPositionFor` | ПАМЯТЬ (в пределах think) | AMBUSH_MEMO |

---

## 6. Карточка: поиск пути как сервис режимов

| Вопрос | Ответ |
|---|---|
| цель | задаёт вызывающий; конечная клетка уточняется `tryCalculateFinalPosition` (спуск на землю, лестница) |
| кандидаты | `findReachable` — все клетки в пределах {TU, energy} при цене ходьбы (BAM_NORMAL), включая свою |
| жёсткие отказы | INVALID в `getTUCost`; блок юнитом по 2.6; 2x2 у двери; ходьба по воздуху; запрещённый первый шаг |
| оценка | минимум ОВ (A*) или прямая с равной ценой шагов (Bresenham); энергия в выборе пути не участвует |
| штрафы | огонь +32 (не бот); sneak ×2 за видимую игроку клетку (враг при опции) |
| штраф за видимость | только sneakyAI (выключен в установке) |
| RNG | нет |
| первая подходящая или лучшая | Bresenham — первая подходящая (прямая); A* — по приоритету g+dist, обычно лучшая |
| ОВ | `calculate`: лимит 1000, Bresenham лимит не смотрит; `findReachable`: точный бюджет |
| энергия | только `findReachable` (бюджет); `calculate` — нет; при ходьбе стоп «energy» |
| угроза ближнего боя врага | не учитывается (в Pathfinding нет чтения оружия или досягаемости врага) |
| другие враги | препятствие только по 2.6; угрозу от них Pathfinding не читает |
| путь пропал | 2.15 |
| запасные ветки | BLOCKED_STEP — повтор без запрещённого шага; STALE_EXACT — полный calculate при ans 2 |

---

## 7. Флаги и зонды

| Флаг / имя | В V4 | Меняет поведение? | Где |
|---|---|---|---|
| KNOWN_OCCUPANT_PATH_V2 | да | да: блок цели в FP, засаде и ходьбе к их точке | 2.7 |
| BLOCKED_STEP | да | да: перестроение без шага, abort при отсутствии пути | 2.12 |
| PATROL_STUN_PREFIX | да | да (только бот careful): обрезка пути | 2.13 |
| STALE_EXACT / STALE_PATROL_NODE | да | да: другой поиск пути к узлу патруля (witnessReach) | 2.14 |
| ESCAPE_REACH_FIRST | да | по списку AiProbe — «меняет вычисление, не игру»: фильтр клеток эскейпа по `_reachable` до calculate (`AIModule.cpp:2052-2061`, флаг `:2053`) | `AiProbe.cpp:1891`, `:2755-2756` |
| AMBUSH_MEMO | да | заявлено как «вычисление, не игра»: память `closedTiles` врага | `AIModule.cpp:1704-1733` |
| FAST, LIGHTSKIP, WALKFOV_SKIP | да | заявлено как «вычисление, не игра» | `AiProbe.cpp:2755-2756` |
| KNOWN_OCCUPANT_PATH (V1) | вне V4 | да | `AIModule.cpp:538-549` |
| OXCE_AI_HALF | вне V4 | да: findReachable с keep = база TU/2 | `AIModule.cpp:846-863` |
| OXCE_AI_ENERGY_PATROL_END | вне V4 | да: spendPatrol | `BattlescapeGame.cpp:541-544` |
| OXCE_AI_FIREPOINT_ENERGY_PATH | вне V4 | да | `AIModule.cpp:3075` |
| OXCE_AI_EVAL (evalFire) | вне V4 | да | `AIModule.cpp:3677` |
| reachWanted / reachTaken (OXCE_AI_RECORD_REUSE) | — | нет: ответ `findReachable` передаётся записи решения | `Pathfinding.cpp:1914-1925`; `AiProbe.cpp:765-773`, `:1591-1611` |
| pathAsk / pathProf (OXCE_AI_PATHPROF) | — | нет: хэш ответа, время, адрес вызова; RNG нет | `Pathfinding.cpp:196-220`, `:1848-1913`; `AiProbe.cpp:1452`, `:1458` |
| Trace (OXCE_AI_TRACE_PATH) | — | нет: лог | `Pathfinding.cpp:175-194` |
| probeReach (PATROL_NO_PATH_CAUSE) | вне V4 | зонд, но зовёт `calculate` и `abortPath`: портит `_path`, флаги узлов, `_expanded`, `_totalTUCost` | `Pathfinding.cpp:967-982`; `AIModule.cpp:1270-1277` |
| patrolReuseProbe | — | зонд, зовёт `calculate` (тот же побочный эффект) | `AIModule.cpp:1203` |
| AiCandidates::reach | — | зонд, зовёт `findReachable` до think (узлы перезаписываются, затем think зовёт его снова) | `AiCandidates.cpp:286-293` |
| pathCost (OXCE_AI_RECORD_PATH ≥ 2) | — | на своём объекте probe, состояние игры не трогает | `Pathfinding.cpp:2007-2029`; `AiProbe.cpp:2672` |
| OXCE_AI_DEV | — | без него `pathCost`, `keepPathPrefix` не компилируются, AiProbe — заглушки | `Pathfinding.h:344-351`; `Pathfinding.cpp:1985-2030` |

---

## 8. Слепые пятна (доказано кодом)

1. **`getTotalTUCost()` после A* — не цена пути.** В `aStarPath` `_totalTUCost` перезаписывается при каждой попытке
   ослабить соседнюю клетку (`Pathfinding.cpp:405`) и при найденной цели не восстанавливается (`:379-389`). Комментарий
   `:2004` это подтверждает. Верно оно только после Bresenham (`:1809-1813`). Это число используют:
   - засада: `ambushTUs`, `score -= ambushTUs` (`AIModule.cpp:1695`, `:1703`);
   - эскейп: `_escapeTUs` (`AIModule.cpp:2113`);
   - точка огня: `score += TU - getTotalTUCost()` (`AIModule.cpp:3095`).
   Для клетки, к которой нет прямой, оценка ОВ случайна относительно настоящей цены пути. Кроме того, под sneak она
   содержит удвоение (`:401`).
2. **Энергия не ограничивает `calculate`.** A* сравнивает только `_totalTUCost.time <= maxTUCost` (`Pathfinding.cpp:409`),
   Bresenham лимитов не смотрит. Нехватка энергии выясняется только при ходьбе (`UnitWalkBState.cpp:328-335`).
3. **Bresenham обходит `maxTUCost`.** Параметр в `bresenhamPath` не используется (`Pathfinding.cpp:1704-1836`). Ближний
   бой с `maxTUs = chargeReserve` (`AIModule.cpp:3312` -> `:2419`) может получить прямой путь дороже резерва.
4. **`findReachable` ослабляет только по времени** (`Pathfinding.cpp:1884`), а отсекает по времени И энергии (`:1878`).
   Клетка, до которой самый дешёвый по ОВ путь не проходит по энергии, а более дорогой по ОВ прошёл бы, не попадёт
   в `_reachable`.
5. **`findReachable` всегда BAM_NORMAL, без sneak** (`Pathfinding.cpp:1874`): бег эскейпа и Leeroy, двойная цена
   видимых клеток, вставание с колен в бюджете не учтены.
6. **Сортировка `_reachable` не гарантирована.** `MinNodeCosts` использует `operator<` (time< И energy<,
   `PathfindingNode.h:136-149`), это не строгий слабый порядок. Порядок «самые дешёвые первыми» используют 250 клеток
   evalFire (`AIModule.cpp:3677`, вне V4).
7. **Ходьба в handleAI всегда строит путь с BAM_NORMAL** (`BattlescapeGame.cpp:521`), а идёт с `action.getMoveType()`
   (`UnitWalkBState.cpp:306`). Маршрут и цена, по которым эскейп оценил клетку при беге (`AIModule.cpp:2107`), могут
   разойтись с реальными.
8. **Враг видит препятствием только тех чужих, кого заметил сам в этот ход** (`Pathfinding.cpp:1217-1219`), но по их
   НАСТОЯЩЕЙ клетке (ИСТИНА). Враг, известный только стороне, проходим (кроме `_aggroTarget` при V2 в трёх местах).
   Нейтрал игнорирует всех чужих.
9. **Бот не получает штраф огня** (`Pathfinding.cpp:586`: `unit->getFaction() != FACTION_PLAYER`) и прокладывает путь
   сквозь горящие клетки по обычной цене. Дым на суше цену не меняет ни для кого (`:755`).
10. **`getDangerous()` Pathfinding не читает** (в `Pathfinding.cpp` нет вызова). Опасные клетки (гранаты) отсекают только
    вызывающие (например `AIModule.cpp:2417`, `:2083`). Путь может пройти через опасную клетку к безопасной.
11. **Нет угрозы по пути.** Ни `getTUCost`, ни A* не читают реакционный огонь, зону ближнего боя врага или то, видит ли
    клетку враг (кроме sneakyAI — только враг, по зрению игрока).
12. **`reachedTU` годен только до следующего `calculate`.** `aStarPath` сбрасывает все узлы (`Pathfinding.cpp:361-364`).
    Зонды `probeReach` и `patrolReuseProbe`, зовущие `calculate` (`AIModule.cpp:1203`, `:1270-1277`), тоже перезаписывают
    узлы и `_path`.
13. **Снаряды бота не видят «известных» юнитов**: ветка `unit->getUnitRules() && … <= getIntelligence()`
    (`Pathfinding.cpp:769`) не срабатывает без правил юнита (солдаты). Блокируют только дружественные.
14. **Приоритет открытого списка — Sint16** (`time*4 + guess`, `PathfindingOpenSet.cpp:75`). При g больше ~8191 ОВ он
    переполнится. Достижимо только с лимитом 100000 (Leeroy, `AIModule.cpp:2475`) на очень длинном пути — теоретически.

---

## 9. Не прослежено

- Восстановление энергии и ОВ между ходами (`BattleUnit::prepareNewTurn`) и для какой стороны и в какой момент оно
  вызывается — вне этой области.
- Резерв ОВ ИИ (`checkReservedTU` при `getPanicHandled`, `UnitWalkBState.cpp:338-342`) против бюджета `findReachable`:
  резерв в `findReachable` не вычитается, а при ходьбе действует только в одной ветке — как это меняет решения, не
  прослежено.
- Поворот перед первым шагом при ходьбе (`UnitWalkBState`, «turning during walking costs no tu», `UnitWalkBState.cpp:345`, `:421`) и его стоимость в
  других местах — не проверено.
- Обновляется ли `_reachableWithAttack` в think, где у юнита нет оружия: заполняется только в `AIModule.cpp:615-626` и
  `:4342`, в начале think не очищается — возможна устаревшая выборка. Где очищается, не найдено (не прослежено до конца).
- Какое значение `sneakyAI` пишут конфиги прогонов стенда (fair22 и др.); `AiProbe.cpp:2006` выводит его в лог.
- `AiProbe::revive` и `AiProbe::flee` (`AIModule.cpp:551-552`) используют `_reachable` — функции стенда, не разбирались.
- `increaseAIWalkAbortCounter`: где читается счётчик и что делает при пороге (комментарий в `AiProbe.cpp` называет
  «abort cap (AIModule::think, 200)») — не прослежено.
- Телепорт: `calculateTeleportDestination` (`Pathfinding.cpp:332-342`) — не разбирался.
- `isBlockedDirection`, `isOnStairs`, `validateUpDown`, `canFallDown` (`Pathfinding.cpp:1282-1515`) прочитаны только
  на уровне «что возвращают»; построчная геометрия больших стен не проверялась.
- Как вызывающие используют `_escapeTUs` после присвоения — карточка эскейпа.
