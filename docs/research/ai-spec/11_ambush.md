# AMBUSH: засада у узла, невидимого ближайшему известному врагу

Код: `src/Battlescape/AIModule.cpp` (`setupAmbush` :1630-1803, ветка `AI_AMBUSH` в `think`, `evaluateAIMode`,
`tacticalMode`), `src/Battlescape/Pathfinding.cpp` (`calculate`, `finalPositionFor`, `closedTiles`),
`src/Battlescape/TileEngine.cpp` (`canTargetUnit`, `faceWindow`), `src/Battlescape/AiProbe.cpp` (`ambushMemo` и зонды).
Флаги V4, меняющие ветку: `AMBUSH_MEMO` (пропуск поиска пути врага), `KNOWN_OCCUPANT_PATH_V2` (свой путь к узлу).
Бот засады не делает вовсе — см. §2 «почему у бота нет засады».

## 1. Дерево вызовов

```
AIModule::think                                                  AIModule.cpp:506
  _knownEnemies = countKnownTargets()  (0 у не-HOSTILE)            :532 -> :2179-2194
  reachableWithAttack(snap | aimed | hit) -> _reachableWithAttack  :611-630 -> :939-945
  if (_knownEnemies && !_melee && !_ambushTUs) setupAmbush()       :647-652
    _ambushAction.type = BA_RETHINK; bestScore = 0; _ambushTUs = 0  :1632-1634
    selectClosestKnownEnemy() -> _aggroTarget                      :1639 -> :2336-2351
    knownOccupantV2 (KO2, HOSTILE)                                 :1643-1650 -> :1088-1101
    origin = getSightOriginVoxel(_aggroTarget)                     :1654
    memo = AiProbe::ambushMemo()                                   :1663
    for node in getNodes()  (порядок файла карты)                  :1667
      отказы: dummy; tile==0; distance2d>10; другой z; getDangerous; нет в _reachableWithAttack   :1669-1678
      скрытность: !canTargetUnit(origin -> узел, гипотет. юнит) && !getSpottingUnits(pos)          :1690
      свой путь: calculateKnownOccupantV2(pos) -> ownPath, ambushTUs                              :1694-1697
      score = 100 - ambushTUs                                                                     :1702-1703
      [AMBUSH_MEMO] finalPositionFor + enemyReach -> пропуск поиска                               :1709-1719
      путь врага: calculate(_aggroTarget, pos, BAM_NORMAL)                                         :1721-1723
      [AMBUSH_MEMO] enemyReach = closedTiles() после первого «нет пути»                            :1730-1733
      enemyPath: +25 за faceWindow; score > bestScore -> лучший; > 80 -> выход                     :1734-1757
    bestScore > 0: BA_WALK к узлу, прогон врага по его пути -> finalFacing                       :1762-1795
  setupAttack, setupPatrol
  evaluate (AI_AMBUSH: !_rifle || !_ambushTUs || _visibleEnemies)  :684-686
  evaluateAIMode: ambushOdds 12 ... ; 0 без _rifle или без _ambushTUs                              :2686, 2704-2711, 2822-2827
  tacticalMode (бот) — у бота до AMBUSH не доходит (см. §2)        :2964-2969
  case AI_AMBUSH: action <- _ambushAction, finalFacing, finalAction=true, kneel                   :823-831
  BA_WALK на другую клетку -> _escapeTUs = _ambushTUs = 0          :866-873
UnitWalkBState::postPathProcedures: finalAction -> dontReselect; поворот на finalFacing (только не PLAYER)   UnitWalkBState.cpp:478-516
```

## 2. Развилки

### think : вызов засады (AIModule.cpp:647-652)
УСЛОВИЕ:   `if (_knownEnemies && !_melee && !_ambushTUs)`
ДАННЫЕ:    `_knownEnemies` (СТОРОНА: `validTarget(bu, true, true)` по всем юнитам, только если `_unit->getFaction() == FACTION_HOSTILE`, AIModule.cpp:2183-2192); `_melee` — есть утилита ближнего боя (:535) или оружие в руке `BT_MELEE` (:624-627); `_ambushTUs` (ПАМЯТЬ: с прошлого вызова в этом ходу; сбрасывается `reset()` в начале хода игрока, :162-170, SavedBattleGame.cpp:1564, и ходьбой на другую клетку, :872)
RNG:       нет
РЕЗУЛЬТАТ: `setupAmbush()`
ВОЗВРАТ:   `setupAttack`
СТОРОНЫ:   только HOSTILE. **Почему у бота нет засады:** `countKnownTargets()` возвращает 0 для любой не-HOSTILE фракции (AIModule.cpp:2183), значит у бота (PLAYER) и нейтралов `_knownEnemies == 0` и условие :647 ложно всегда; `_ambushTUs` остаётся 0 (`reset`, конструктор), поэтому в `evaluateAIMode` `ambushOdds = 0` (:2704-2706, :2822-2827) и запасная ветка AMBUSH сразу уходит в ESCAPE (:2925-2931). Режим AI_AMBUSH у бота может появиться только из запасной цепочки и тут же заменяется на ESCAPE. Флаг `OXCE_AI_TACTICS` (вне V4) этого не меняет — он для HOSTILE

### setupAmbush : цель засады (AIModule.cpp:1639, 2336-2351)
УСЛОВИЕ:   `selectClosestKnownEnemy()`: по всем юнитам `validTarget(bu, true, false)` (не выбыл; клетка не `getDangerous`; вес `getTargetAttackWeight > getAITargetWeightThreatThreshold()`; вес 0 = `AIW_IGNORED`, если `_intelligence < getTurnsSinceSpottedByFaction(faction)` и не снайпер со споттером, :4217-4224)
ДАННЫЕ:    знание стороны о цели (СТОРОНА: `turnsSinceSpotted` против `intelligence` юнита); расстояние `distance2d` до ИСТИННОЙ позиции цели (ИСТИНА), не до места, где её видели
RNG:       нет
РЕЗУЛЬТАТ: `_aggroTarget` — ближайшая известная цель (при равенстве — первая по списку юнитов, `dist < minDist`, начальное 255); иначе — провал засады (ниже `ambushEnd(false)`)
СТОРОНЫ:   HOSTILE (бот сюда не попадает)

### setupAmbush : KNOWN_OCCUPANT_PATH_V2 (AIModule.cpp:1643-1650, 1088-1101, 1106-1118)
УСЛОВИЕ:   `knownOccupantV2(old)`: флаг, `FACTION_HOSTILE`, `_aggroTarget`; цель возвращается, если `getTurnsSinceSpottedByFaction(HOSTILE) == 0` (замечена стороной в этом ходу), иначе `old = true`, 0
ДАННЫЕ:    СТОРОНА (замечена в этом ходу)
RNG:       нет
РЕЗУЛЬТАТ: в своих поисках пути к узлам клетка цели считается занятой (`setKnownOccupant`), поиск пути ВРАГА к узлу не трогается
СТОРОНЫ:   HOSTILE, V4

### setupAmbush : отбор узла (AIModule.cpp:1667-1678)
УСЛОВИЕ:   `node->isDummy()` -> пропуск; затем `tile == 0 || Position::distance2d(pos, _unit->getPosition()) > 10 || pos.z != _unit->getPosition().z || tile->getDangerous() || std::find(_reachableWithAttack..., getTileIndex(pos)) == end` -> пропуск
ДАННЫЕ:    узлы (ИСТИНА карты; кандидаты — ТОЛЬКО узлы, не клетки); метка `getDangerous`; `_reachableWithAttack` — клетки, достижимые с запасом ОВ на атаку (findReachable с бюджетом `TU - cost`, AIModule.cpp:941-944; стартовая клетка в него входит)
RNG:       нет
РЕЗУЛЬТАТ: узел идёт на проверку скрытности
ПРЕРЫВАНИЕ: `_reachableWithAttack` обновляется только в `reachableWithAttack()` (:939) — в think только при годном оружии в руке (:611-630). Без оружия (или если `canUseWeapon` ложно) список остаётся от прошлого think, возможно с другой позиции
СТОРОНЫ:   HOSTILE. `distance2d` = `ceil(sqrt(dx*dx+dy*dy))` (Position.h:118-121); флаги узла (тип SMALL/FLYING, ранг, аллокация) НЕ проверяются

### setupAmbush : скрытность узла (AIModule.cpp:1690)
УСЛОВИЕ:   `!canTargetUnit(&origin, tile, &target, _aggroTarget, false, _unit) && !getSpottingUnits(pos)`
ДАННЫЕ:    `origin = getSightOriginVoxel(_aggroTarget)` (глаза цели, ИСТИННАЯ позиция); `canTargetUnit` — линия огня по вокселям к гипотетическому `_unit` на узле, без дальности, света, дыма и направления взгляда (TileEngine.cpp:2196+); юниты на линии блокируют по ИСТИНЕ. `getSpottingUnits(pos)` — все цели `validTarget(bu, false, false)` (СТОРОНА отбора) в `distance2d <= 20`, линия из глаз минус 2 вокселя к гипотетическому юниту (AIModule.cpp:2201-2233)
RNG:       нет
РЕЗУЛЬТАТ: узел, который не видит ни ближайшая цель, ни любая известная цель в 20 клетках
СТОРОНЫ:   HOSTILE

### setupAmbush : свой путь (AIModule.cpp:1694-1703)
УСЛОВИЕ:   `ownPath = getStartDirection() != -1` после `calculateKnownOccupantV2(pos, ko2, ...)` (= `calculate(_unit, pos, BAM_NORMAL)`, при KO2 с клеткой цели как занятой)
ДАННЫЕ:    свой поиск пути (блокировка юнитами по правилу HOSTILE — 31_pathfinding.md); лимит 1000 ОВ
RNG:       нет
РЕЗУЛЬТАТ: `score = BASE_SYSTEMATIC_SUCCESS - ambushTUs = 100 - getTotalTUCost()`
ПРЕРЫВАНИЕ: узел под самим юнитом путь не проходит никогда: при `start == end` путь пуст, `getStartDirection()` возвращает -1 (Pathfinding.cpp:939-943)
СТОРОНЫ:   HOSTILE

### setupAmbush : память «нет пути» AMBUSH_MEMO (AIModule.cpp:1709-1719, 1728-1733)
УСЛОВИЕ:   `memo = AiProbe::ambushMemo()` = параметр `OXCE_AI_AMBUSH_MEMO` (AiProbe.cpp:1713-1717; V4: 1 — пропуск; 2 — сверка; 0 — выкл.). Если `enemyReach` не пуст: `end = finalPositionFor(_aggroTarget, pos, BAM_NORMAL)`; `memoNoPath = !end || !enemyReach[index(*end)]`. `memoNoPath && memo == 1` -> `continue`
ДАННЫЕ:    `enemyReach` — `closedTiles()` первого в этом вызове поиска пути врага, который исчерпал открытый список без ответа (Pathfinding.cpp:303; пуст, если поиск упёрся в лимит или отказал заранее); живёт только в этом вызове
RNG:       нет
РЕЗУЛЬТАТ: поиск пути врага к узлу пропускается, узел не берётся — тот же итог, что дал бы поиск без пути. Заполнение: `else if (memo && !enemyPath && enemyReach.empty()) enemyReach = closedTiles();` (:1730-1733)
СТОРОНЫ:   HOSTILE, V4. `ambushMemoNode`, `ambushMark`, `ambushNode`, `ambushBegin`, `ambushEnd`, `ambushEnemy`, `ambushOwn`, `ambushScored` — зонды записи (AiProbe.cpp:1719-1846), RNG не трогают, состояние ИИ не меняют

### setupAmbush : путь врага к узлу (AIModule.cpp:1721-1723)
УСЛОВИЕ:   `calculate(_aggroTarget, pos, BAM_NORMAL)`; `enemyPath = getStartDirection() != -1`
ДАННЫЕ:    поиск ОТ ЛИЦА цели: её тип движения и её правило блокировки юнитами (цель — PLAYER: блокируют видимые юниты, `u->getVisible()`, Pathfinding.cpp:1203-1226); лимит 1000 ОВ, ОВ цели не учитываются
RNG:       нет
РЕЗУЛЬТАТ: узел годен, только если цель может до него дойти
СТОРОНЫ:   HOSTILE

### setupAmbush : оценка и выбор (AIModule.cpp:1734-1757)
УСЛОВИЕ:   `enemyPath`
ДАННЫЕ:    `faceWindow(pos)` (ИСТИНА карты: на одной из 4 сторон клетки есть стена, не закрывающая обзор, TileEngine.cpp:5673-5688)
RNG:       нет
РЕЗУЛЬТАТ: `cover` -> `score += 25`; `taken = score > bestScore` -> `path = copyPath()` (путь ВРАГА к узлу), `bestScore = score`, `_ambushTUs = (pos == позиция юнита) ? 1 : ambushTUs`, `_ambushAction.target = pos`; `bestScore > 80` -> `fastPass = true; break`
ВОЗВРАТ:   следующий узел или выход из цикла
СТОРОНЫ:   HOSTILE. Ветка `_ambushTUs = 1` для своей клетки недостижима (своя клетка не проходит `ownPath`)

### setupAmbush : итог и направление взгляда (AIModule.cpp:1762-1803)
УСЛОВИЕ:   `bestScore > 0`
ДАННЫЕ:    `path` — путь цели к узлу; `getTUCost(currentPos, path.back(), _aggroTarget, 0, BAM_NORMAL)` — шаги цели от её позиции; `canTargetUnit(&origin, tile, &target, _unit, false, _aggroTarget)` — линия из точки засады (`target.toVoxel() + (8, 8, height + floatHeight - terrainLevel - 4)`, :1769-1771) к гипотетической цели на шаге
RNG:       нет
РЕЗУЛЬТАТ: `_ambushAction.type = BA_WALK`; `finalFacing = getDirectionTo(узел, первая клетка пути цели, откуда засада её достанет)`; если такой клетки нет — `finalFacing` НЕ присваивается и остаётся от прошлого вызова (поле не сбрасывается в `setupAmbush`; начальное — из `BattleAction()` конструктора, AIModule.cpp:62). Иначе (`bestScore <= 0`) — `_ambushAction.type = BA_RETHINK` (:1632), `ambushEnd(false)`
ПРЕРЫВАНИЕ: `setUnit(_aggroTarget)` (:1773) оставляет в Pathfinding юнитом цель — следующий `calculate` переставит (не прослежено, есть ли чтение между)
ВОЗВРАТ:   think
СТОРОНЫ:   HOSTILE

### think : пересмотр режима из засады (AIModule.cpp:684-686)
УСЛОВИЕ:   `case AI_AMBUSH: evaluate = (!_rifle || !_ambushTUs || _visibleEnemies);`
ДАННЫЕ:    `_rifle` (оружие `BT_FIREARM` без путевых точек, :613-619), `_ambushTUs` (ПАМЯТЬ), `_visibleEnemies` (ЮНИТ)
RNG:       нет
РЕЗУЛЬТАТ: засада держится без пересмотра, пока у юнита винтовка, засада найдена и он никого не видит
СТОРОНЫ:   HOSTILE

### evaluateAIMode : шанс засады (AIModule.cpp:2686, 2704-2711, 2748, 2763-2784, 2796-2799, 2814-2843)
УСЛОВИЕ:   база `ambushOdds = 12`; `!_rifle || _ambushTUs == 0` -> 0; ×1.1 в AI_AMBUSH; ×0.75 (здоровье < 1/3), ×0.8 (< 2/3); агрессия 1 -> ×1.1; ×1.5 в AI_COMBAT; `_visibleEnemies && _closestDist < 5` -> 0; `_ambushTUs` -> ×1.7, иначе 0; базовая оборона ×0.6; нет ни оружия, ни гранаты, ни пси -> 0
RNG:       RNG HERE: `RNG::generate(1, max(1, sum))` AIModule.cpp:2845 — общий бросок режима (03_modes.md); вызывается всегда, когда `evaluate`
РЕЗУЛЬТАТ: AI_AMBUSH; запасная ветка: AMBUSH остаётся при `_ambushTUs != 0`, иначе ESCAPE (:2925-2931); PATROL без узла уходит в AMBUSH (:2911-2923)
СТОРОНЫ:   оба по коду; у бота `ambushOdds` всегда 0

### tacticalMode : засада под наблюдением (AIModule.cpp:2955-2969)
УСЛОВИЕ:   `_spottingEnemies`, есть укрытие (`_escapeAction.type == BA_WALK`, цель не своя клетка, `getSpottingUnits(цель) < _spottingEnemies`), `_AIMode == AI_AMBUSH && !wounded` -> засада остаётся
СТОРОНЫ:   вызывается при `tactics || careful` (:639, :744-746); у врага V4 `tactics` выключен, у бота засады нет — ветка в V4 не исполняется

### think : действие засады (AIModule.cpp:823-831)
УСЛОВИЕ:   `_AIMode == AI_AMBUSH`
РЕЗУЛЬТАТ: `setCharging(0)`; `action->type/target = _ambushAction`; `finalFacing = _ambushAction.finalFacing`; `finalAction = true`; `kneel = allowsKneeling(kneelDefault)` (`kneelDefault` — только бот-солдат, :750)
ВОЗВРАТ:   `BA_WALK` на другую клетку -> `_escapeTUs = _ambushTUs = 0` (:869-873); на свою -> `BA_NONE` (:874-877)
СТОРОНЫ:   HOSTILE. Резерв ОВ: `_reserve = BA_NONE` (:748), ходьба засады резерва не держит. `desperate` не ставится — ходьба засады останавливается на новом замеченном враге (UnitWalkBState.cpp:235)

### UnitWalkBState::postPathProcedures : конец пути засады (UnitWalkBState.cpp:478-516)
УСЛОВИЕ:   `_unit->getFaction() != FACTION_PLAYER`
РЕЗУЛЬТАТ: `finalAction` -> `dontReselect()` (ход юнита закончен); поворот на `finalFacing`, если `!= -1`, с `calculateFOV` после каждого шага поворота
СТОРОНЫ:   HOSTILE. Прерывание через `cancelCurentMove` (замечен враг после шага :241-244, огонь на реакцию :248-254, ОВ/энергия/резерв :314-341) — это `abortPath()` + `popState()` (UnitWalkBState.cpp:129-139) БЕЗ `postPathProcedures`: `finalAction` не срабатывает (юнит может действовать снова), поворота на `finalFacing` нет. Ветка «стоит и заметил» (:276-281) `postPathProcedures` вызывает. Подробно — 30_execution.md

## 3. Числа

| что | значение | выражение | файл:строка | на что влияет |
|---|---|---|---|---|
| база очков узла | 100 | `BASE_SYSTEMATIC_SUCCESS` | AIModule.cpp:1651, 1702 | |
| цена пути | −ОВ пути | `score -= ambushTUs` | AIModule.cpp:1703 | узел с путём >= 100 ОВ без окна — `score <= 0`, не берётся; с окном — при >= 125 ОВ |
| бонус окна | +25 | `COVER_BONUS` | AIModule.cpp:1652, 1740 | любое окно/забор на краю клетки, направление не важно |
| досрочный выход | > 80 | `FAST_PASS_THRESHOLD` | AIModule.cpp:1653, 1751 | первый узел с `score > 80` (путь < 20 ОВ, или < 45 ОВ с окном) |
| порог принятия | > 0 | `bestScore > 0` (старт 0) | AIModule.cpp:1633, 1743, 1762 | |
| радиус поиска | `distance2d <= 10` | `> 10` -> отказ | AIModule.cpp:1676 | только узлы в круге ~10 клеток, на своём z |
| радиус видящих | `distance2d <= 20` | `dist > 20` -> не считать | AIModule.cpp:2211 | |
| глаза видящего | −2 вокселя | `originVoxel.z -= 2` | AIModule.cpp:2213 | у цели засады (`origin`, :1654) поправки нет |
| точка засады для взгляда | (8, 8, рост + float − terrain − 4) | | AIModule.cpp:1769-1771 | клетка цели на пути врага |
| `_ambushTUs` | ОВ пути (или 1 для своей клетки — недостижимо) | | AIModule.cpp:1749 | шанс засады, повторный вызов |
| шанс в `evaluateAIMode` | 12 и множители | | AIModule.cpp:2686 и далее | см. 03_modes.md |
| порог цели | 50 (по умолчанию) | `getAITargetWeightThreatThreshold()` | AIModule.cpp:4278 | кто «известный враг»; в Пиратках `ai:` без весов — умолчания (Piratez_Globals.rul:9151, 40_ruleset.md) |

## 4. RNG (в порядке выполнения)

| # | вызов | файл:строка | что решает | когда |
|---|---|---|---|---|
| — | в `setupAmbush` RNG нет | AIModule.cpp:1630-1803 | — | — |
| 1 | `RNG::generate(1, sum)` | AIModule.cpp:2845 | выбор режима (в т. ч. засады) | при `evaluate`; засада влияет на `sum` через `ambushOdds` |

Хрупкость: сама засада бросков не тратит, но её результат `_ambushTUs` входит в `sum` броска режима (×1.7 или 0) — правка,
меняющая, найдена ли засада (память `AMBUSH_MEMO` при сверке, KO2, `_reachableWithAttack`), меняет границы отрезков
броска и выбранный режим при том же числе. `AMBUSH_MEMO=1` по построению не меняет итог (пропускается только поиск,
доказанно дающий «нет пути»), поэтому поток RNG не сдвигает.

## 5. Знание

| что | метка | где |
|---|---|---|
| есть ли известные враги | СТОРОНА (`turnsSinceSpotted` против `intelligence`) | AIModule.cpp:2183-2192, 4217-4224 |
| цель засады и её позиция | СТОРОНА отбора, ИСТИНА позиции | AIModule.cpp:2341-2346 |
| откуда смотрит цель | ИСТИНА (`getSightOriginVoxel` по настоящей позиции) | AIModule.cpp:1654 |
| видят ли узел другие цели | СТОРОНА отбора, ИСТИНА позиций и линий | AIModule.cpp:2201-2233 |
| линия огня | ИСТИНА геометрии, юниты на линии — ИСТИНА; свет, дым, дальность — не учитываются | TileEngine.cpp:2196+ |
| дойдёт ли цель до узла | поиск от лица цели (её блокировка юнитами — по правилу PLAYER) | AIModule.cpp:1721, Pathfinding.cpp:1203-1226 |
| свой путь | поиск HOSTILE (+ KO2) | AIModule.cpp:1694 |
| окно | ИСТИНА карты | TileEngine.cpp:5673 |
| узлы | ИСТИНА карты | AIModule.cpp:1667 |
| `_reachableWithAttack` | ИСТИНА о себе, возможно с прошлого think | AIModule.cpp:939-945 |
| `_ambushTUs`, `_ambushAction` | ПАМЯТЬ (в пределах хода) | AIModule.cpp:162-170, 1634 |

## 6. Карточка режима AMBUSH

| пункт | ответ по коду |
|---|---|
| цель | встать на узел, которого не видит ни ближайшая известная цель, ни известные цели в 20 клетках, и куда цель может прийти; смотреть туда, откуда она появится |
| кандидаты | только узлы сети (не клетки), не dummy, в `distance2d <= 10`, на своём z, достижимые с запасом ОВ на атаку |
| жёсткие отказы | `tile == 0`; далеко; другой z; `getDangerous`; не в `_reachableWithAttack`; узел виден цели или любому известному видящему; нет своего пути; нет пути цели (или память «нет пути»); своя клетка (путь пуст) |
| оценка | `100 − ОВ пути` + 25 за окно |
| штрафы | только цена пути; опасность, огонь, раны, число врагов — нет |
| видимость | линия огня (не зрение): от цели и от известных целей в 20 клетках к гипотетическому юниту; свет, дым, дальность зрения, направление взгляда — нет |
| RNG | нет |
| первая или лучшая | лучшая по порядку узлов с досрочным выходом на первом `score > 80`; при равенстве — раньше в списке узлов |
| ОВ | узел достижим с оставшимися ОВ на снап/прицельный/удар; цена пути — штраф; после ходьбы `finalAction` — ход окончен, остаток ОВ на огонь на реакцию; резерва при ходьбе нет |
| энергия | только через достижимость (`findReachable` учитывает энергию); в оценке нет |
| угроза ближнего боя врага | не учитывается: засада у прохода, к которому идёт цель с клинком, оценивается так же |
| другие враги | влияют только как «видящие» (отказ узла); их пути к узлу не проверяются |
| пропал путь | путь цели к узлу проверяется при выборе; к моменту хода — нет; свой путь пересчитывается в `handleAI` (BattlescapeGame.cpp:521), нет — ходьбы нет, действие потрачено |
| запасные ветки | `bestScore <= 0` -> `BA_RETHINK`; в `evaluateAIMode` AMBUSH без `_ambushTUs` -> ESCAPE |

## 7. Слепые пятна (доказано кодом)

1. Бот засады не строит: `countKnownTargets()` у не-HOSTILE — 0 (AIModule.cpp:2183), условие вызова :647 ложно.
2. Юнит, уже стоящий на лучшем узле, не может «остаться в засаде»: путь к своей клетке пуст, `ownPath` ложно
   (AIModule.cpp:1697, Pathfinding.cpp:939-943); ветка `_ambushTUs = 1` (:1749) мёртвая.
3. Кандидаты — только узлы сети: клетка в укрытии без узла не рассматривается (AIModule.cpp:1667).
4. Скрытность проверяется линией огня, а не зрением: темнота, дым и дальность зрения цели не учитываются, а невидимые
   глазу узлы, до которых долетает выстрел, отвергаются (`canTargetUnit` без света и дальности).
5. Позиции целей — ИСТИННЫЕ: «известная» цель берётся по знанию стороны, но расстояние, глаза и пути считаются от её
   настоящего места, даже если сторона видела её несколько ходов назад (AIModule.cpp:1654, 2343, 1721).
6. Бонус окна не связан с направлением на врага: подходит любое окно на любом из 4 краёв (TileEngine.cpp:5673-5688).
7. Угроза ближнего боя, огонь, раны, число врагов, их ОВ и время до прихода цели в оценке отсутствуют.
8. `finalFacing` не сбрасывается: если ни один шаг пути цели не просматривается из засады, юнит повернётся по
   направлению прошлой засады (AIModule.cpp:1776-1791).
9. `_reachableWithAttack` без годного оружия в руке не обновляется в этом think (AIModule.cpp:611-630) — достижимость
   узлов берётся с прошлого think.
10. Проверяется путь одной цели (ближайшей); другие известные враги могут пройти к узлу и с другой стороны.
11. Путь цели ищется без лимита её ОВ (1000): узел «доступен цели», даже если ей нужно несколько ходов.
12. Прерванная ходьба к засаде не завершает ход: `cancelCurentMove` (замечен враг после шага, огонь на реакцию,
    нехватка ОВ/энергии; UnitWalkBState.cpp:129-139) не зовёт `postPathProcedures`, поэтому ни `dontReselect`, ни
    поворота на `finalFacing` нет — юнит остаётся там, где его остановили, и может быть выбран снова.

## 8. Не прослежено

- Когда именно исполняется ветка «стоит и заметил» (UnitWalkBState.cpp:276-281) против отмены после шага (:241-244) —
  какой из путей встречается при остановке засады на деле (30_execution.md).
- Чтение Pathfinding после `setUnit(_aggroTarget)` (:1773) до следующего `calculate`.
- Как часто на картах fair22 у HOSTILE `_knownEnemies > 0` без видимых врагов (зависит от `intelligence` юнитов
  Пираток и `turnsSinceSpotted`) — нужна выборка рулсета, 40_ruleset.md.
- Равенство памяти `AMBUSH_MEMO` и полного поиска — доказано на стенде режимом 2 (комментарий :1656-1662), не в коде.
