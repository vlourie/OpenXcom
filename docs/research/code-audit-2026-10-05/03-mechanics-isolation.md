# Проверка изоляции HD-слоя от механики (HEAD e6af0d5ed) — только чтение

Агент Explore, 05.10.2026. Сравнение против настоящего апстрима 441cae1b0 (Meridian, «OXCE 8.7.1»); тег `v8.7.1` в этом репозитории указывает на локальный коммит 03421b28a.

## Короткий ответ

Само HD-рисование изолировано чисто. В src/Engine/Hd* нет ни одного вызова RNG, и к объектам игры этот код обращается только через `const`-указатели. Все HD-вставки в боевые состояния либо только читают, либо меняют темп (интервал тика, камеру).

По букве правила 2 CLAUDE.md есть два нарушения, оба помечены в коде как «HD:»: правка арок в GeoscapeState и подмена исследования «пустышкой» в Rule*Script. Есть и одна правка механики в выпускной сборке, не связанная с HD: порядок предметов в BattlescapeGenerator.

## Файлы вне src/Engine/Hd*, где упоминается HD

### (а) Отрисовка и интерфейс

| Группа | Файлы и число упоминаний |
|---|---|
| Interface | Window.cpp 15/.h 2; Text.cpp 12/.h 2; TextButton.cpp 11/.h 2; Bar.cpp 10/.h 1; ProgressBar.cpp 10/.h 1; TextList.cpp 9(10)/.h 2; TextEdit.cpp 9/.h 1; Cursor.cpp 9/.h 1; Frame.cpp 9/.h 1; ArrowButton.cpp 8/.h 1; NumberText.cpp 7/.h 1; ScrollBar.cpp 6(8)/.h 1; ToggleTextButton.cpp 5/.h 1; BattlescapeButton.cpp 3(6)/.h (2); ComboBox.cpp 3(4); Slider.cpp 3(5) |
| Menu | OptionsHdState.cpp 53(74)/.h 1(5); MainMenuState.cpp 11(12); OptionsAdvancedState.cpp 9; OptionsBattlescapeState.cpp 3/.h 1; AdultChoiceState.cpp 2/.h 1; GentleChoiceState.h 1; OptionsBaseState.cpp (2) |
| Battlescape | Map.cpp 43(87)/.h 11(16); BattlescapeState.cpp 36(64); Inventory.cpp 18(21)/.h 3(5); ActionMenuItem.cpp 11/.h 1; UnitSprite.cpp 7(14)/.h 3; InventoryState.cpp 7; AlienInventory.cpp 7; WarningMessage.cpp 7/.h 1; BattlescapeMessage.cpp 5/.h 1; Camera.cpp 3; ItemSprite.cpp 2(3)/.h 3 |
| Geoscape | Globe.cpp 33(52)/.h 5(16); DogfightState.cpp 8/.h 1; GeoscapeCraftState.cpp (2) |
| Basescape | BaseView.cpp 27(48)/.h (4); CraftInfoState.cpp 1(5) |
| Engine | Game.cpp 42(48); Options.cpp 36(40); Options.inc.h 32(36); Feedback.cpp 19; Screen.cpp 17/.h 3; Surface.cpp 15/.h 2(5); SurfaceSet.cpp 4; Zoom.cpp 2 |
| Mod | Mod.cpp 54(79)/.h 3(13); MapDataSet.cpp 5 |
| Прочее | Ufopaedia/ArticleStateItem.cpp 3 |

### (б) Механика

| Файл | Число упоминаний |
|---|---|
| Battlescape/ExplosionBState.cpp | 8 (14 с локальными hd*) |
| Battlescape/ProjectileFlyBState.cpp / .h | 7 (18) / (1) |
| Battlescape/UnitDieBState.cpp / .h | 2 (14) / (2) |
| Battlescape/UnitWalkBState.cpp, UnitTurnBState.cpp, UnitFallBState.cpp | по 3 |
| Battlescape/Projectile.cpp | 2 |
| Battlescape/Explosion.h | 3 (4) |
| Battlescape/BattlescapeGenerator.cpp | 0 (5) |
| Geoscape/GeoscapeState.cpp | 0 (2, плюс 3 комментария «HD:») |
| Savegame/SavedBattleGame.cpp / .h | 0 (2) / (1) |
| Savegame/Tile.cpp / .h | 0 (1) / (1) |
| Savegame/Ufo.cpp / .h | 0 (6) / (2) |
| Mod/RuleArcScript.cpp, RuleEventScript.cpp, RuleMissionScript.cpp | комментарии «HD:» — 2, 1, 1 |
| Battlescape/TileEngine.cpp | HD-функция `explosionArea` |
| AIModule, Pathfinding, BattlescapeGame, BattleUnit | только вызовы AiProbe |
| Engine/RNG, остальные Mod/Rule* | 0 |

## Подозрительные места

**П1 — нарушение по букве правила, механика.** GeoscapeState.cpp:3794–3816 (`determineAlienMissions`, комментарии «HD:»), RuleArcScript.cpp:96,102; RuleEventScript.cpp:111; RuleMissionScript.cpp:138; Mod.h:646; Mod.cpp:5286 `getResearchOrPlaceholder`.
- Ссылка на необъявленное исследование больше не роняет загрузку, вместо неё создаётся «пустышка», которую нельзя открыть.
- Случайная арка-пустышка убирается из `disabledRngArcs`: меняется набор вариантов для `choose()`, то есть результат броска.
- Последовательность арок на пустышке останавливается, а не открывает её.
- Для корректных данных мода изменений нет; затронуты только моды с битыми ссылками.
- Осознанная правка (коммиты bde0ba3c3 и 03421b28a), но это механика вне HD-слоя под меткой «HD».

**П2 — механика в выпускной сборке, не HD.** BattlescapeGenerator.cpp:1236, 1258, 1288 и ItemContainer.cpp:240 `getContentsInListOrder`.
- Предметы с корабля и базы создаются в порядке списка мода, а не по адресам `RuleItem*` (у апстрима порядок разный от запуска к запуску).
- Меняются id предметов, порядок на клетке корабля, авто-экипировка и разбор ничьих в `surveyItems`.
- Флагом не закрыто. Коммит c4eb8720a («одна механика везде»).

**П3 — отклонение от апстрима, только камера.** ProjectileFlyBState.cpp:404: `HdGentle::traceProjectiles() >= 2`, в апстриме `> 2`. При `qolDontTraceProjectiles=2` камера не следует ни за одним выстрелом независимо от «нежного» режима. `followProjectile` читает только камера. Коммит 699a5d520.

**П4 — HD-путь пишет в Savegame, на практике безвредно.** Map.cpp:990–1003 (`hdTestFreeze`), Tile.cpp:727 (`hdTestResetAnimation`), SavedBattleGame.h:422 (`setAnimFrame`), Map.cpp:3015. Срабатывает по Ctrl+F8: обнуляет `_animFrame` (пишется в сейв, виден скриптам), кадры анимации тайлов, `_animationOffset` огня и дыма, пропускает один `Map::animate`. В апстриме `animFrame` и так растёт по настенным часам; формально нарушение изоляции, можно закрыть флагом или запретить вне тестов.

**П5 — ранний return под HD-условием.** UnitDieBState.cpp:275–278: `if (_killCam && HdKillCam::hold()) return;` — откладывает `setUnitDying(false)`, `calculateLighting`, `calculateFOV`, перевод тела в труп. Сцена ограничена 15 с, порядок действий не меняется, ввод заблокирован. `finalBlow()` только читает. Вердикт: только темп.

**П6 — HD-поле в сейве.** Ufo.cpp:124–125, 276–277, 841: `_hdDecoded`, ключ `hdDecoded`. Читает только Globe.cpp:1819. Безвредно, формат сейва расширен.

**Проверено и не найдено:** вызовов RNG в src/Engine/Hd* нет; новых вызовов, двигающих зерно RNG, в Map, BattlescapeState, Camera, UnitSprite, Globe, BaseView, Game, Screen, Surface, Inventory нет (счётчики совпадают с апстримом); изменяющих вызовов из Map.cpp к `_save`, юнитам или тайлам нет, кроме П4; в Hd* к игровым объектам только `const`-указатели.

## Безобидные места группы (б)

- ExplosionBState.cpp:238–239, 247 — `HdFx::boomClip`/`setHdFx`: после `explode()`, перед циклом RNG, без RNG.
- ExplosionBState.cpp:281–283, 370–378 — чтение здоровья и оглушения до и после `hit()` для выбора эффекта, через `const`.
- ExplosionBState.cpp:269, 389 и BattlescapeGame.cpp:408, 611, 833, 1443 — `centerOnPosition` → `focusOn`; без «нежного» режима это ровно `centerOnPosition`.
- ProjectileFlyBState.cpp:433–448, 553, 596 — `hdMuzzle`, без RNG.
- ProjectileFlyBState.cpp:855–862 — эффект попадания дроби, только чтение.
- Projectile.cpp:52 — `HdGentle::fireSpeed()` 3 вместо 6 пикселей за кадр. Траектория считается заранее; `addVaporCloud` тратит RNG один раз на точку траектории, число бросков не зависит от скорости.
- UnitWalkBState.cpp:553–555, UnitTurnBState.cpp:64–66, UnitFallBState.cpp:59–61 — только миллисекунды между тиками.
- Explosion.h:37, 59–61 — поле `_hdFx`, флаг `onUnit`, геттеры.
- BattlescapeGenerator.cpp:773, 2457, 2804, 3279, 3305 и SavedBattleGame.cpp:452, 455 — `refreshHdScale` и `loadData(..., hdScale)`: масштабируются только спрайты, MCD и LOFT не трогаются.
- GeoscapeState.cpp:896, 1894 — `setHdRadarSlow`/`hdRadarCycle`, только картинка глобуса.
- TileEngine.cpp:3564 `explosionArea` — копия лучей `explode()` без RNG, вызывается только из Map.cpp:1517.
- TileEngine.cpp `unitLightPower` — точное выделение функции для AiProbe.
- UnitWalkBState.cpp:202–205 — `updateSoldierInfo(AiProbe::walkFovKeep())`; заглушка возвращает `true`.
- DogfightState.cpp:827, 2293, 2357 — показ шанса попадания по той же формуле (только чтение) и контур НЛО; вызовов RNG по-прежнему 19.
- BattlescapeState.cpp: `Timer::hdFrameSkip` только поднимает `maxFrameSkip`; `mapClick` во время скольжения камеры игнорируется — это ввод.
- Все вызовы `AiProbe::*` в выпуске — пустые заглушки.

## OXCE_AI_DEV / AiProbe

- CMakeLists.txt:25: `option(OXCE_AI_DEV ... OFF)`. AiProbe.cpp всегда компилируется; при `#ifndef OXCE_AI_DEV` (строки 72–176) это заглушки: `active`/`fast`/`careful`/`botTurn` дают `false`, `maxActions` — 2, `walkFovKeep` — `true`.
- InfoboxOKState.cpp:100 и ConfirmEndMissionState.cpp:125 закрыты `#ifdef OXCE_AI_DEV`. BriefingState::think проверяет `AiProbe::active()` — в выпуске всегда `false`.
- NewBattleState.cpp:608–706 и 718–919 закрыты; дополнительные броски RNG там только в сборке стенда. Даже в стенде зонд спит без `OXCE_AI_PROBE`.
- Выпускная сборка: build-release/CMakeCache.txt — `OXCE_AI_DEV:BOOL=OFF`; build.ps1:571 упаковывает build-release. Все build-ai* — ON.
- **Риск:** build.ps1 не проверяет `OXCE_AI_DEV=OFF` в кэше и не вызывает cmake с явным `-D`. Стоит добавить проверку.
- Выборочная проверка AIModule: изменённые строки при заглушках эквивалентны апстриму (`kneelDefault=false`, `calculateKnownOccupantV2` с `null` — обычный `calculate`, `reachableWithAttack` — тот же `findReachable`). Полная эквивалентность ИИ за рамками проверки.

## HdGentle (нежный режим)

Опция `oxceGentle`, определение в src/Engine/HdGentle.h; настройки игрока не перезаписывает, подменяет при чтении.
- **Темп**: ходьба, поворот, падение — 60 мс за тик; снаряд 3 пикселя за кадр.
- **Камера**: `traceProjectiles=4`; `smoothCamera`; `focusOn` не перецентрирует видимую точку (Camera.cpp:465); скольжение `beginShown`/`endShown` подменяет `_mapOffset` только на время рисования; клики во время скольжения игнорируются; kill cam выключен.
- **Интерфейс**: стрелка и цвет номера стрелявшего реакцией (`noteGentleShot`/`noteGentleTrail`, Map.cpp:3399+) пишут только в поля Map. Клавиша быстрого режима заблокирована.

Расчёт не меняется. Число тиков и бросков RNG не зависит от интервалов.

## Выводы

1. Рисующий HD-слой механику не трогает. Одно формальное нарушение — П4 (Ctrl+F8 пишет `animFrame` и анимацию тайлов); П6 только расширяет формат сейва.
2. Реальные правки механики — П1 (арки и исследования-«пустышки», метка «HD:») и П2 (порядок предметов, стенд ИИ). Обе осознанные, но нарушают правило из CLAUDE.md. Либо явно занести их как исключения, либо вынести из-под метки «HD».
3. П3 стоит упомянуть в журнале изменений: значение 2 опции qolDontTraceProjectiles работает не как в апстриме, но только для камеры.
4. Тестовые хуки по переменным окружения (`OXCE_HD_CLICK`/`SET`/`MOUSE`/`TYPE`/`START`/`DUMP*`) и Ctrl+F8 вкомпилированы в выпуск. Без переменных на механику не влияют.
5. Вне HD: переключение света отдельного бойца (клавиша P) и телепорт в предпросмотре расстановки — из oxce-plus, не HD-слой.

Проверено только чтением: grep, git diff/log и чтение файлов, ничего не менялось.
