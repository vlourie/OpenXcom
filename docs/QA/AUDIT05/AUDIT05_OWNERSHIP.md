# AUDIT-05 — владение объектами и время жизни

Этап B, 18.11.2026, SHA исходников `ffbec78ec25f737ff0827786b603a89558709ab1`.
Источник — чтение кода (файл и строка указаны), не запуск. Где утверждение проверено запуском — сказано отдельно.
Обозначения: **владеет** — удаляет в своём деструкторе; **ссылка** — сырой указатель без владения;
**может быть 0** — указатель бывает нулевым в штатной работе.

## 1. Верхний уровень: `Game`

| Что | Кто владеет | Когда создаётся | Когда уничтожается | Где |
|---|---|---|---|---|
| `Game` | `main` (стек) | запуск | выход из `main` | `src/main.cpp` |
| `_states` — стек экранов (`std::list<State*>`) | `Game` | `pushState` / `setState` | `popState` переносит в `_deleted`; удаление — в начале следующего круга `Game::run` | `Game.cpp:939-978`, `run` |
| `_deleted` — экраны, ждущие удаления | `Game` | `popState` | начало круга `run`; **в `~Game` не освобождается** | `Game.cpp:144-169` |
| `_save` — текущая игра (`SavedGame*`), **может быть 0** | `Game` | `setSavedGame(new …)` | `setSavedGame` удаляет прежний **сразу**; `~Game` | `Game.cpp setSavedGame` |
| `_mod` | `Game` | `loadMods` | `~Game`, после `_save` | `Game.cpp:158-159` |
| `_screen`, `_cursor`, `_lang`, `_fpsCounter`, плашки | `Game` | конструктор | `~Game` | `Game.cpp:156-164` |

Порядок в `~Game`: экраны стека → курсор → язык → **сейв** → мод → экран. Сейв ссылается на правила мода и умирает
раньше мода — порядок правильный. Экраны умирают раньше сейва — деструктор экрана вправе читать сейв **только на
этом пути**.

### Главная особенность: сейв удаляется сразу, экраны — потом

`Game::setSavedGame(x)` выполняет `delete _save` немедленно. Экраны, снятые `setState` / `popState`, живут до
начала следующего круга. Значит между `setSavedGame` и началом следующего круга существуют экраны со ссылками в уже
освобождённый сейв. Их деструкторы и любой код, который успеет к ним обратиться, читают освобождённую память.

Все места смены сейва (grep `setSavedGame`, 18 вызовов):

| Место | Порядок | Экраны со ссылками на старый сейв в момент удаления |
|---|---|---|
| `LoadGameState.cpp:170` | `popState` (себя) → `load` → `setSavedGame(s)` → `setState(new GeoscapeState)` | весь прежний стек ещё в `_states` (Geoscape / Battlescape и окна над ними) |
| `LoadGameState.cpp:240` (`error`) | после неудачи: `setSavedGame(0)` | уже поставленный новый `GeoscapeState` — **остаётся в стеке без сейва** (AUD05-008, подтверждено) |
| `LoadGameState.cpp:242` (`error`) | неудача до смены: `delete save` | прежняя игра остаётся, но деструктор недогруженного сейва выгружает общие наборы карты (AUD05-013, подтверждено) |
| `AbandonGameState.cpp:122-123` | `setState(new MainMenuState)` → `setSavedGame(0)` | прежний стек в `_deleted` |
| `SaveGameState.cpp:221-222` | то же | прежний стек в `_deleted` |
| `StatisticsState.cpp:350`, `CutsceneState.cpp:75` | `setSavedGame(0)` → `setState(…)` | прежний стек ещё в `_states` |
| `NewBattleState.cpp:461/604/727/1062`, `NewGameState.cpp:173/212`, `ListLoadOriginalState.cpp:196`, `MainMenuState.cpp:358/397` | из меню | экранов игры в стеке нет |
| `HdControl.cpp:689` (стенд) | `dropStates` → `setSavedGame` | экраны удалены заранее (исправление R-508 / R-535) |

Что защищает игрока сейчас: деструкторы экранов в сейв почти не заглядывают. Проверено скриптом
`tools/state_dtors.py` по всем 213 классам экранов и боя (186 с деструктором в `.cpp`): в сейв или его объекты
обращаются два.

| Деструктор | Что делает | Достижимо ли при удалённом сейве |
|---|---|---|
| `InventoryState::~InventoryState` (`InventoryState.cpp:634`) | `_battleGame->getTileEngine()->applyGravity / calculateLighting / recalculateFOV` | у игрока — не нашёл пути: загрузка и выход из боя закрыты, пока открыт инвентарь. На стенде до R-535 — да. **Потенциальная** |
| `GraphsState::~GraphsState` (`GraphsState.cpp:313`) | `_game->getSavedGame()->setGraph…Toggles` | то же; при `getSavedGame() == 0` — нулевой указатель. **Потенциальная** |

Скрипт видит только тело деструктора. Косвенные обращения (деструктор поля, обработчик таймера) он не ловит;
деструкторы `GeoscapeState`, `BattlescapeState`, `BattlescapeGame`, `Map` прочитаны глазами — в сейв не заглядывают.

Порядок удаления: `Game::run` удаляет `_deleted.back()` первым, `dropStates` — `front()`. При `setState` в `_deleted`
экраны попадают сверху вниз, значит `run` удаляет **нижний экран раньше окон над ним**, а стенд — наоборот.
Окно, которое в деструкторе обращается к экрану-родителю, на пути игрока получит уже удалённого родителя
(`_parent` в деструкторах скриптом не найден — на сегодня чисто, но правило нигде не записано).

## 2. `SavedGame` (геоскейп)

`SavedGame::~SavedGame` — `SavedGame.cpp:204-270`.

| Поле | Владение | Замечание |
|---|---|---|
| `_time`, `_alienStrategy`, `_previewBase` | владеет | |
| `_countries`, `_regions`, `_bases`, `_ufos`, `_waypoints`, `_missionSites`, `_alienBases`, `_activeMissions`, `_geoscapeEvents` | владеет (векторы указателей) | порядок записи в сейв значим: базы пришельцев → миссии → НЛО (`SavedGame.cpp:917-922`) |
| `_deadSoldiers`, `_missionStatistics`, `_researchDiary` | владеет | |
| `_globalEquipmentLayout[j]` | владеет, цикл до `Options::oxceMaxEquipmentLayoutTemplates` | если опция уменьшена после загрузки — хвост не освобождается (утечка, не порча); массив фиксированного размера |
| `_globalCraftLoadout[j]` | владеет | |
| `_battleGame` (`SavedBattleGame*`), **может быть 0** | владеет | `setBattleGame(0)` после боя: `DebriefingState.cpp:802`, `BattlescapeState.cpp:4082`, `CraftEquipmentState.cpp:265`, `SoldiersState.cpp:305` |
| `_discovered`, `_poppedResearch`, `_autosales` и т. п. | ссылки на правила `Mod` | действительны, пока жив мод |
| живые бойцы | **не здесь**: ими владеет `Base::_soldiers` | `SavedGame::getSoldier(id)` ищет по базам, **может вернуть 0** |

`Base::~Base` (`Base.cpp:72-100`): владеет `_facilities`, `_soldiers`, `_crafts`, `_transfers`, `_productions`,
`_items`, `_research`, `_vehiclesFromBase`.
`Craft::~Craft` (`Craft.cpp:99-113`): владеет `_weapons`, `_items`, `_tempSoldierItems`, `_tempExtraItems`,
`_vehicles`; бойцы корабля — **ссылки**: принадлежность записана в `Soldier::_craft`, не в корабле.
Свой код: `HdCraftRoute::forget(this)` в деструкторе — глобальная таблица по указателю корабля чистится вовремя.
`Soldier::~Soldier` (`Soldier.cpp:131-140`): владеет раскладками, `_death`, `_diary`.

Перекрёстные ссылки геоскейпа (`Craft::_dest`, `Ufo::_mission`, `Soldier::_craft`, цели перехватов) на этапе B
**не разобраны** — они относятся к логике геоскейпа, этап E.

## 3. `SavedBattleGame` (бой)

`SavedBattleGame::~SavedBattleGame` — `SavedBattleGame.cpp:96-133`.

| Поле | Владение | Замечание |
|---|---|---|
| `_tiles` | владеет (один массив `Tile`, не указатели) | `getTile(pos)` вне карты → **0** |
| `_nodes`, `_units` | владеет | |
| `_items`, `_recoverGuaranteed`, `_recoverConditional` | владеет | |
| `_deleted` (предметы) | владеет | см. ниже |
| `_pathfinding`, `_tileEngine`, `_baseItems`, `_hitLog` | владеет | |
| `_mapDataSets` | **ссылки** на наборы мода; в деструкторе `unloadData()` | наборы общие для всех `SavedBattleGame`, а выгружает их деструктор любого из них — без счётчика. Второй `SavedBattleGame` (недогруженный сейв) при удалении выгружает наборы идущего боя: **AUD05-013, подтверждено ASan** |
| `_battleState` (`BattlescapeState*`), **может быть 0** | ссылка назад на экран | 0 до `setBattleState` и в инвентаре базы; разыменовывается без проверки в `canUseWeapon` (`:1224`, `:1234`), `:1631`, `:1805`, `:1814` |
| `_selectedUnit`, `_undoUnit`, `_lastSelectedUnit` | ссылки в `_units` | |
| `_rule` (`Mod*`) | ссылка | |

**Удаление предмета в бою** (`removeItem`, `SavedBattleGame.cpp:1943-1985`): предмет убирается из `_items` и с
клетки или владельца и переносится в `_deleted`; память освобождается только в конце боя. Это намеренная защита:
указатели на предмет в действиях, снарядах и скриптах не становятся висячими. Цена — `_deleted` растёт весь бой.
Встроенное оружие (`isSpecialWeapon`) не удаляется вовсе. Вместе с оружием удаляются и его заряженные обоймы.
В `removeUnconsciousBodyItem` (`:2784-2800`) автор OXCE сам оставил TODO: цикл выйдет за конец списка, если
`removeItem` уберёт больше одного предмета — возможно только для предмета с заряженной обоймой, у тела её нет.
**Потенциальная**, низкий приоритет.

`BattleUnit::~BattleUnit` (`BattleUnit.cpp:645-653`): владеет `_statistics` (и убийствами в ней), `_currentAIState`.
Всё остальное — ссылки: `_tile`, `_geoscapeSoldier` (в `Base::_soldiers`), `_armor` / `_unitRules` (в `Mod`),
`_inventory` (в `SavedBattleGame::_items`), `_charging` (другой юнит).
`BattleUnit::_geoscapeSoldier` при загрузке берётся из `savedGame->getSoldier(id)` без проверки на 0 (AUD05-006).

`BattleItem`: владельца (`_owner`, `_previousOwner`), тело (`_unit`), клетку (`_tile`) и обоймы (`_ammoItem[]`)
держит ссылками; сам принадлежит `SavedBattleGame`. В сейве связи записаны номерами (`owner`, `unit`,
`ammoItemSlots`) и восстанавливаются вторым проходом через `unitIndex` / `itemIndex` (`SavedBattleGame.cpp:255-395`).

`Tile`: владеет только своими данными; `_unit`, `_inventory`, `_mapData->…` — ссылки. Объекты карты хранятся номерами
(`ID`, `SetID`) и превращаются в указатели в `loadMapResources` (`:505-545`).

## 4. Экраны (`State`) и поверхности

`State::~State` (`State.cpp:67-74`) удаляет `_surfacesOwned` в обратном порядке добавления. Экран владеет своими
поверхностями; поверхности мода (`Mod::getSurface`, наборы спрайтов) экрану не принадлежат.
`Surface`, `SurfaceSet`, владение внутри `Mod` (правила, наборы, звуки, шрифты) на этапе B **не читались** — они
идут в этап F (загрузка модов) и G; в `review_status.tsv` эти файлы остаются `NOT_REVIEWED`.

## 5. Загрузка сейва: что с чем связывается и где нет проверки

Порядок `SavedGame::load` (`SavedGame.cpp:449-783`): заголовок → **`RNG::setSeed`** (`:475-476`, до того как известно,
удастся ли загрузка — AUD05-009) → страны, регионы → базы пришельцев → миссии → НЛО → базы → … → бой
(`SavedBattleGame::load`, `:775`).

| Связь | Как восстанавливается | Что при битой ссылке |
|---|---|---|
| клетка ← двоичные данные | номер клетки из `binTiles` | вне массива: `assert` выключен в выпуске → запись за массив (AUD05-002); данных меньше, чем `totalTiles` → чтение за буфером (AUD05-001, **подтверждено ASan**) |
| клетка → объект карты | `_mapDataSets[SetID]->getObject(ID)` | `ID` проверяется (`MapDataSet::getObject` бросает исключение), `SetID` — нет (AUD05-003) |
| юнит → боец базы | `savedGame->getSoldier(id)` | 0 передаётся в конструктор `BattleUnit` (AUD05-006) |
| юнит → тип и броня | `mod->getUnit / getArmor` | проверяется, юнит пропускается с записью в лог — образец правильной обработки |
| предмет → клетка | `getTile(pos)->addItem` | клетка вне карты → 0 (AUD05-005) |
| предмет → владелец, тело | `findUnitById` | проверяется (`count` перед `at`) |
| предмет → обойма, новый ключ `ammoItemSlots` | `itemIndex.count` перед `at` | проверяется |
| предмет → обойма, старый ключ `ammoItem` | `itemIndex.at` без проверки | `std::out_of_range`, которое никто не ловит (AUD05-007) |
| размеры карты | `width`, `length`, `height` как есть | не проверяются (AUD05-004) |

`LoadGameState::think` ловит только `OpenXcom::Exception` и `YAML::Exception`. Любое стандартное исключение
(`std::out_of_range`, `std::length_error`, `std::bad_alloc`) уходит в общий обработчик `main` — игра закрывается с
отчётом о падении вместо окна «не удалось загрузить».

## 6. Запись сейва

`SaveGameState::think` (`SaveGameState.cpp:205-214`): запись в `<имя>.bak` → `CrossPlatform::moveFile(bak, имя)`.
На Windows это `MoveFileExW(…, MOVEFILE_REPLACE_EXISTING)` — замена одним действием: прежний сейв цел, пока новый не
записан. Слабые места (AUD05-012): `CrossPlatform::writeFile` не проверяет результат `SDL_RWclose` и не сбрасывает
файл на диск — при отключении питания сразу после записи новый файл может оказаться пустым, а старый уже заменён;
вне Windows `moveFile` — копирование и удаление, не одно действие.
`SavedGame::save` (`SavedGame.cpp:831-1012`) ничего в состоянии игры не меняет (метод `const`), кроме статического
флага `SoldierDiary::setCompactWrite`, который снимается охранником и при исключении.
