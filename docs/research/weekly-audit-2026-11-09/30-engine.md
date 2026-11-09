# Недельный аудит 09.11.2026 — зона 30: движок C++ (src/)

Проверяющий: только чтение, ничего не правилось, не собиралось, игра не запускалась. База сравнения — коммит `dacd5060a` (27.10);
с тех пор 139 коммитов в `src`, 242 файла, +26 366 / −1 035 строк. Все времена — «оценка по числу операций, не замерено» (R-091).
Прошлые аудиты: `docs/research/code-audit-2026-10-27/10-cpp-hd.md`, `20-cpp-gameplay.md`.

## Итог

| Показатель | Значение |
|---|---|
| Lua-песочница: побег к файлам, процессам, байткоду, сети | **не нашёл**. Открыто 5 библиотек (base, table, string, math, utf8), из base оставлен белый список, `load/dofile/require/debug/os/io/package/string.dump/collectgarbage/coroutine` недоступны, байткод запрещён флагом `"t"` |
| Выход за границы / переполнение в Lua-функциях | в просмотренных пишущих функциях (карта, предметы, юниты, деньги, склад, экраны) **не нашёл**: везде `checkInt`, диапазоны, лимиты на вызов/ход |
| Нарушение правила 2 (механика) | **не нашёл**: все изменения вне HD либо под опцией (по умолчанию выкл.), либо дают тот же результат при выключенной опции, либо работают только при загруженных Lua-модах |
| Главный реальный риск | нет **общего лимита времени** на Lua: 2 000 000 инструкций на *каждый* вызов, число вызовов не ограничено (находка 1) |
| Из списка 27.10 закрыто | 8 из 13 (см. раздел «Что из 27.10 закрыто / не закрыто») |
| exe выпуска | 26,2 МБ (`build-release/bin/openxcom.exe`, 26 165 248 байт, 08.11). Таблица обрушения вынесена в `.bin`, символы срезаны (`-s`) |

## Находки

| # | Тяжесть | Что | Где | Чем грозит | Починка и цена в часах | Что выигрывает игрок |
|---|---|---|---|---|---|---|
| 1 | средняя | У Lua нет общего (на кадр / на ход / на бой) лимита времени. Лимит один: `instructions = 2000000` на один `fire()` (`main.lua` — в 10 раз больше). Число вызовов не ограничено: событие `visibilityUnit` (по паре юнитов), `reactionUnit*`, `aiCalculateTargetWeight`, `*BonusStats` вызываются из горячих циклов. Лимит срабатывает только как ошибка, а обработчик, который тратит 1,9 млн инструкций и не падает, не отключается никогда | `src/Engine/LuaSandbox.h:50` (`Limits`), `LuaSandbox.cpp:~413` (`lua_sethook`, счётчик обнуляется в `begin()`), `LuaHost.cpp:3846-3891` (`fireOutputs`: цикл по модам без общего счёта). Поиск `chrono\|SDL_GetTicks` в `LuaSandbox.cpp` и `LuaHost.cpp` — пусто | Мод (даже честный, но с тяжёлым обработчиком видимости) вешает бой. Оценка по числу операций, не замерено: 2 млн инструкций Lua ≈ 10–30 мс; 1000 вызовов за ход ≈ 10–30 с. Защита от злого мода — только то, что игрок сам поставил мод и включил `oxceLuaMods` (по умолчанию выкл.) | Накопительный счёт инструкций на ход/кадр в `LuaHost` (поле в `Entry`, сброс в `newTurn`/кадр); при превышении — `isDisabled()` для мода + строка в журнал. ~3–4 ч + тест в `tools/lua_sandbox_test.cpp` | Бой не виснет из-за одного плохого мода; мод отключается с понятным сообщением |
| 2 | низкая | `main.lua` читается в память целиком без ограничения размера до разбора | `LuaHost.cpp:3786-3787` (`CrossPlatform::readFile` + `istreambuf_iterator`) | Мод с `main.lua` в сотни МБ съест память до того, как сработает лимит Lua (32 МБ действует только на кучу Lua). Нужно, чтобы мод поставил сам игрок | Проверка `size > 1 МБ` до чтения, ~0,5 ч | Мелочь, защита от случайно битого файла |
| 3 | низкая | Остальные пути к файлам не нужны (мод читает только свой `lua/main.lua`), но путь строится как `info->getPath() + "/lua/main.lua"` без проверки на символьную ссылку | `LuaHost.cpp:3702` | Символьная ссылка `lua/main.lua` на чужой файл читается как код Lua (содержимое попадёт в сообщение об ошибке разбора, если не Lua). Утечка файла игрока в журнал; наружу ничего не уходит | Не нужно чинить: мод и так выполняется с правами игрока | — |
| 4 | низкая | `tostring(<таблица/userdata/функция>)` и `print` показывают адреса (`%p` Lua 5.4) | `LuaSandbox.cpp` (`gameLog`, `luaL_tolstring`), `luaopen_base` не урезает `tostring` | Утечка адресов кучи (обход ASLR). Без примитива записи/исполнения в песочнице использовать нечем | Не чинить | — |
| 5 | низкая | Защитные правки загрузки сейва боя меняют поведение загрузки (правило 2 «загрузка сейва»): предмет с владельцем, которого нет, теперь пропускается; второй проход по предметам пропускает id, которого нет в индексе. Раньше — обращение по `itemIndex.at()` (исключение) или повисший предмет | `src/Savegame/SavedBattleGame.cpp:326-330`, `:380` (diff `dacd5060a`) | Сохранённый бой с битой ссылкой раньше падал/терял предметы иначе, теперь тихо без предмета + строка `LOG_ERROR`. На целом сейве поведение то же | Оставить; но записать в DECISIONS, что это осознанное отклонение от апстрима | Битый сейв не роняет игру |
| 6 | низкая | `Pathfinding::canCrush`: `armor >= 255 \|\| armor > limit` берёт `CollapsePilot::trunkArmor(..., TRUNK_MELEE)`, а при `oxceCollapse=false` возвращает `md->getArmor()` — поведение апстрима. Проверено: при `crushTerrain == 0` (у всех ванильных и Пираток-броней) функция выходит на первой же проверке `limit <= 0` | `src/Battlescape/Pathfinding.cpp` (diff: `canCrush`, `crushes`, `partCost`, `_crushOn = armor->getCrushTerrain() > 0 && ...`) | Это **новая механика**, но под полем брони `crushTerrain` (по умолчанию 0) и только для хода игрока (`getFaction()==FACTION_PLAYER`, `!AiProbe::botTurn`). Правило 2 не нарушено, если ни одна ванильная броня не имеет поле. Проверить на рулсетах Пираток: `grep -rn crushTerrain` | Проверить рулсет (0,2 ч) | — |
| 7 | низкая | Тест-хуки остались в выпускном exe вне `#ifdef OXCE_AI_DEV`: `OXCE_HD_CONTROL` (`HdControl.cpp`: команды из файла — load/set/key/click), `OXCE_HD_DUMP`, `OXCE_HD_MOUSE`, `OXCE_HD_CLICK`, `OXCE_HD_TYPE`, `OXCE_HD_SET`, `OXCE_HD_KEY` (`Game.cpp:462-590`), `OXCE_HD_SAVES`, `OXCE_HD_ARTICLE` (`MainMenuState.cpp:326,352`), `OXCE_HD_LAUNCH_TEST`, `OXCE_HD_DUMP_LAUNCH`, `OXCE_HD_PALSHIFT_DUMP` (`HdPaletteShift.cpp:273`), `OXCE_HD_ADDRESS_RELOAD`, `OXCE_HD_FLASH_AT`, `OXCE_HD_BLAST_AT`, `OXCE_HD_BLAST_REVEAL`, `OXCE_HD_VIEW_ZOOM`, `AddressTrace` (`HdCanvas.cpp:536-558`) | перечисленные файлы | Нужен доступ к переменным окружения процесса (локальный пользователь) — угрозы нет. Цена: десятки КБ кода, вызовы `getenv` в горячих местах закрыты `static const` | Обернуть `HdControl::step`, авто-ввод в `Game.cpp`, `AddressTrace` и `PALSHIFT_DUMP` в `#ifdef OXCE_AI_DEV` (или новый `OXCE_HD_DEV`): ~3–4 ч + сверка Ctrl+F8 и `hdtest_compare.py` + проверка, что стенды hdbench собираются с флагом | −30…60 КБ exe (оценка, не замерено), меньше поверхности для сбоев |
| 8 | низкая | `HdControl.cpp:303` и `:475`: `g->getStates().back()` без проверки на пустой стек (остался из 27.10 №2); в `stateLine` и в 630-654 проверка есть | `src/Engine/HdControl.cpp:303,475` | Падение тестового канала при команде `load`/`reinit` в момент, когда стек пуст. Только при `OXCE_HD_CONTROL` | +4 строки, 0,2 ч | Стенд не падает |
| 9 | низкая | Исключение в задаче `HdWorkers` по-прежнему не ловится (остался из 27.10 №3): в `HdWorkers.cpp` нет ни `try`, ни `catch` | `src/Engine/HdWorkers.cpp:34` (`fn(i);`), `grep -n "try\|catch"` — пусто | `std::bad_alloc` в задаче (куклы: `composeFrame` выделяет `W*H*4` на слой, до 4 МБ × слои) = `std::terminate` без записи в журнал | `try/catch(...)` вокруг `fn(i)`, сохранить первое исключение, бросить из `run()` после барьера: ~1 ч | Вместо немого вылета — строка в журнале |
| 10 | низкая | `HdUiArt::frame()` отдаёт `const HdFrame&` на `art->frame`, а следующий вызов `frame(other)` при нехватке бюджета (768 МБ) обнуляет `frame` самого старого «чужого» `Art`. Если вызывающий держит ссылку на пиксели первой картинки и просит вторую (слои куклы друг за другом) — висячая ссылка возможна только если первая стала «самой старой» | `src/Engine/HdUiArt.cpp:581-600` (цикл вытеснения `oldest->frame = HdFrame()`) | Теоретически; `lru` первой только что обновлён `++clock`, поэтому вытеснится она последней. Вероятность низкая; доказательства падения нет | Либо документировать «ссылка живёт до следующего `frame()`», либо вытеснять после кадра: 1–2 ч, нужен случай воспроизведения | — |
| 11 | низкая | Память: бюджеты кэшей картинок интерфейса и кукол — 768 МБ (`HdUiArt.cpp:395`) + 256 МБ подготовленных (`:829`) + HdSprites 384 МБ (`HdSprites.cpp:238`): до ~1,4 ГБ только кэшей HD на слабом ПК | перечисленные строки | На 8 ГБ ПК с картой и модами Пираток — риск свопа. Это настройка, не ошибка; значения заданы константами без опции | Связать бюджет с физической памятью (`GlobalMemoryStatusEx`) или вынести в опцию: 1–2 ч | Слабый ПК не уходит в своп |
| 12 | низкая (скорость) | `Map::drawTerrain`: `std::vector<int> pixelMaskArray(4*_k*_k)` строится на каждую клетку с паром/дымом каждый кадр, деление `my/_k` и `mx/_k` на элемент (остался из 27.10 №4) | `src/Battlescape/Map.cpp:5800-5804` | k=4: 64 `int`, k=8: 256 `int` на клетку; оценка по числу операций, не замерено: до 0,3 мс на кадр при сотнях клеток с дымом | Таблица маски на `_k` в члене класса (строить при смене `_k`), ~1 ч + IDENTICAL k=1 | До 0,3 мс на кадр |
| 13 | низкая (скорость) | `Map::updateHdLight` вызывает `hdTintOf` для каждой из 9 клеток при каждой видимой клетке каждый кадр (для центральной — один раз, остальные 8 — заново; остался из 27.10 №9) | `src/Battlescape/Map.cpp:1760,1790` (вызовы), `:1712-1745` (тело: 4 слоя × 3 канала, один `max`) | Около 9 × 4 слоя × ~10 флопов на клетку; 2 000 клеток ≈ 0,7 млн флопов, оценка, не замерено ≈ 0,3–0,6 мс | Кэш `tint` в `Tile` (+3 `float`) с сбросом при `calculateLighting`: 2–3 ч + IDENTICAL | ~0,3–0,6 мс на кадр |
| 14 | низкая (скорость) | Новый `Map::hdFloorAo`: кэш по клетке есть, но на каждую клетку каждый кадр делается 27 вызовов `partOf` (`getTile`+`isDiscovered`+`isUfoDoorOpen`+`getMapData`) и `std::equal` по 27 указателям | `src/Battlescape/Map.cpp:3600-3630` | 2 000 клеток × 27 ≈ 54 тыс. дешёвых вызовов; оценка по числу операций 0,1–0,3 мс/кадр, не замерено | Хранить версию карты (счётчик изменений видимости/частей) и сравнивать её, а не 27 указателей: 2–3 ч + IDENTICAL | ~0,1–0,3 мс на кадр |
| 15 | информ. | `HdUi::drawImage` — CPU-путь по-прежнему один поток (float `blendPixel`), но с видеокартой идёт через `HdGpuWorld::image` и возвращается раньше (`HdUiDraw.cpp:850-856`). Без видеокарты остаётся как в 27.10 №5 | `src/Engine/HdUiDraw.cpp:844-870` | Только на машинах без GL-пути | Разрезать на `HdWorkers` по строкам, 1–2 ч | — |
| 16 | информ. | `upper(sets[s]->getName())` внутри тройного цикла (блок × набор × k): 956 блоков × ~30 наборов × k — десятки тысяч выделений строк за раз при старте боя (остался из 27.10) | `src/Battlescape/CollapsePilot.cpp:861`, `:345` | Раз на бой, не на кадр; оценка: единицы мс | Предвычислить `upper` по набору один раз: 0,5 ч | — |
| 17 | информ. | Карта наложений `SavedBattleGame::placeNewUnit` — вынесенная копия кода `BattlescapeGame::spawnNewUnit`: порядок вызовов `RNG` проверен — `RNG::generate(0,7)` для направления вызывается после проверки позиции (как раньше, внутри `if (positionValid)`), `RNG::generate(0,9)` для уровня предметов после него. Поведение при игре без Lua идентично апстриму | `src/Savegame/SavedBattleGame.cpp:2228-2278`, `src/Battlescape/BattlescapeGame.cpp` (diff) | Это не находка, а подтверждение; но стоит добавить в `docs/handbook/render.md`/тест, что здесь ловится дрейф RNG | — | — |

## Lua API: функция | проверка аргументов | риск

Всего в `LuaHost.cpp` около 515 строк-регистраций в ~40 таблицах `luaL_Reg`. Типы-«ручки» закрыты (`__metatable = false`, `__index` — таблица
методов, нет `__gc`, `setmetatable` с `__gc` запрещён); ручка игрового объекта живёт один `fire()` (`generation`), чужой вызов даёт ошибку
`... is valid only inside the handler that received it` (`LuaSandbox.cpp:691-699`). Все числа идут через `checkInt` (`LuaHost.cpp:249-254`: диапазон `int`),
индексы — через `luaL_argcheck` на диапазон. Поэтому «указатель из Lua» получить нельзя.

Колонка «разрешение» — что нужно в `luaCaps` (метаданные мода); без него функция даёт ошибку `needs '...' in luaCaps`.

| Функция(и) | Разрешение | Проверка аргументов | Риск |
|---|---|---|---|
| `game.on`, `game.log`, `print`, `pcall`, `xpcall`, `setmetatable`, `math.random` | — | `game.on`: только в `main.lua`, имя события из белого списка; `pcall`/`xpcall` пропускают лимит; `setmetatable` отвергает `__gc`; `math.random`: интервал в `int`, запрещён в `main.lua` и в «чистых» обработчиках (иначе сдвигается ГСЧ игры) | низкий |
| `game.screen`, `game.openScreen` | `screens` | имя, число экранов (`SCREENS_PER_MOD 64`, на вызов 1, на ход/день 8, одновременно `MAX_OPEN 4`); интерфейс должен быть в рулсете | низкий |
| `game.getBattle/getGeoscape/getBases` | — | только чтение, ручки | низкий |
| `ui:window/text/button/toggleButton/list/comboBox/edit/slider/image/onKey/onClose/close` | `screens` | строки `≤ 2000` и валидный UTF-8 (`checkUiText`), опечатки в полях таблицы отвергаются (`checkFields`), `MAX_WIDGETS 64`, `MAX_ROWS 2000`, `MAX_COLUMNS 8`, `MAX_OPTIONS 256`, картинка должна существовать (`hasSurface`, `LuaHost.cpp:1822,1955,2177`) | низкий |
| виджет: `setText/setImage/setRows/…` | `screens` | виджет и экран проверяются (`checkWidget`, `find(screen)`), вид виджета через маску | низкий |
| `battle:getTile(x,y,z)` | — | границы карты по каждой оси (`LuaHost.cpp:1265-1273`), иначе `nil` | низкий |
| `battle:getUnits/getItems/getSelectedUnit/getTurn/getSize/…` | — | только чтение, `faction` через `checkFaction` | низкий |
| `battle:randomRange/randomChance` | — | запрещены в «чистых» обработчиках (`checkRandomAllowed`) | низкий |
| `battle:setAlienItemLevel`, `setReinforcementsItemLevel` | — | шаблон `battleSetItemLevel`: диапазон по таблице уровней (не открывал) | низкий (механика, но через уровень предметов — как в апстриме) |
| `battle:flashMessage/flashLongMessage` | — | текст `MESSAGE_MAX 200`, `MESSAGE_TICKS` | низкий |
| `battle:tryConcealUnit` | — | `checkOtherUnit` | низкий |
| `battle:spawnItem(type,x,y,z[,done])` | `spawn` | тип в рулсете, 3 координаты внутри карты, `done` — функция; лимиты: 32 на вызов, 256 на ход; очередь выполняется в безопасный момент (`checkMayQueue`), не в превью | низкий |
| `battle:removeItem(item[,done])` | `spawn` | ручка предмета; при исполнении: предмет ещё в бою (`std::find`), не спец-оружие, не тело, снятие цели прицеливания (`takeOutOfBattle`, `LuaHost.cpp:3457-3495`); удалённые предметы хранятся в `_deleted` до конца боя — чтение `getGlow()` для уже удалённого безопасно | низкий |
| `battle:spawnUnit{type,x,y,z,faction,direction,done}` | `spawn` | только юниты рулсета (не солдат), `x/y/z` в границах (`fieldInt`), `faction` ∈ [PLAYER, NEUTRAL], `direction` ∈ [0,7]; 4 на вызов, 16 на ход; исполняет `placeNewUnit` (то же, что и спавн оружия) | низкий |
| `unit:giveItem(type[,done])` | `spawn` | тип в рулсете, юнит жив и в списке (`std::find` на исполнении) | низкий |
| `unit:set*/add*` (≈30: TU, здоровье, мана, энергия, оглушение, мораль, огонь, броня, раны, тип движения, `setSpawnUnit*`, `setTurnsSinceSpotted*`) | — (только в записываемом обработчике, `checkWritable`) | идут через `BattleUnit::LuaApi` — это те же функции, что у Y-скриптов OXCE, они клампят значения и индексы (`BattleUnit.cpp:6145-6159`: сторона `0 ≤ side < SIDE_MAX`, `Clamp(value, ±BaseStatLimit)`); каждую по отдельности не проверял | низкий–средний (изменение боя без метки в сейве, как у Y-скриптов) |
| `unit:disableIndicators`, `makeVisible`, `reduceBy*` | — | `checkWritable` | низкий |
| `item:setAmmoQuantity/setFuseTimer/setHealQuantity/setPainKillerQuantity/setStimulantQuantity/setFuseEnabled/setInventoryMoveCost` | — | шаблон `setInt`, `checkInt`; границы по количеству в самом `BattleItem` (не проверял) | низкий |
| `tile:getPart(part)` | — | `checkPart`: `O_FLOOR ≤ part < O_MAX` | низкий |
| `tile:setPart(part,set,id[,done])` | `map` | имя набора из `getMapDataSets`, `0 ≤ id < size`, объект набора должен быть того же `ObjectType`, что и слот | низкий |
| `tile:clearPart/destroyPart(part[,done])` | `map` | `checkPart`; при исполнении `changeTile` | низкий |
| `tile:setFire(turns)` | `map` | 0…255 | низкий |
| `tile:setSmoke(density)` | `map` | 0…15 | низкий |
| (ограничения карты) | `map` | 64 клетки на вызов, 512 на ход; в сейве ставится `luaTouched: map` | низкий |
| `battle:getMapSets()` | — | только чтение, `LIST_TICKS` | низкий |
| `geoscape:getFunds`, `geoscape:addFunds(n)` | `economy` | `n` ∈ [−10⁹, 10⁹]; работает только в `newHour/newDay/newMonth`, в клике экрана и в функции `hireSoldier`; не в бою; счёт в 64 бита; откат при ошибке (`noteEconomy`); метка `luaTouched: economy` | низкий (счёт 5000 вызовов × 10⁹ = 5·10¹² укладывается в `int64`) |
| `base:addItem/removeItem(type[,n])` | `economy` | `n` ∈ [1, 10⁹], переполнение `INT_MAX` проверено, снятие не больше имеющегося; откат | низкий (вместимость склада не проверяется — как в апстриме) |
| `base:add/removeScientists/Engineers(n)` | `economy` | `n` ∈ [1, 10⁹], переполнение, только свободные | низкий |
| `base:hireSoldier(type[,done])` | `economy` | тип солдата в рулсете; 16 на вызов, 64 в день; при исполнении проверяются база, места, месячный лимит | низкий |
| `soldier:setStat/addStat`, `setWoundRecovery/ManaMissing/HealthMissing` | — | `checkStat` (указатель на член из белой таблицы), `statValue`/`statAddend` — клампы; `setInt` без диапазона (сеттеры `Soldier` клампят сами — не проверял) | средний: меняет сейв без метки `luaTouched` |
| `setTag/getTag` (юнит, предмет, бой, геоскейп, солдат) | — | `checkTag` по имени из рулсета, `checkInt` | низкий |
| `rules:*`, `ruleItem:*`, `ruleArmor:*`, `ruleUnit:*`, `ruleSoldier:*`, `ruleCraft:*`, `ruleUfo:*`, `ruleCountry:*`, `ruleResearch:*`, `ruleInventory:*`, `ruleDamage:*` | — | только `get*`/`is*`/`has*`: пишущих методов нет (проверено по таблицам `RULE_*_METHODS`) | низкий |
| `statsForNerds:addStat/addTextRow/addIntRow/addTextFormatRow` | — | только в обработчике `statsForNerds*`, текст ограничен | низкий |
| `country/ufo/craft/base:get*` | — | только чтение | низкий |

## Что из 27.10 закрыто / не закрыто

| № 27.10 | Что | Статус | Доказательство |
|---|---|---|---|
| ✔ №2 (README) | Стенд обрушения `OXCE_COLLAPSE_*` в выпускном exe | **закрыто** | `CollapsePilot.cpp:795-825`, `1117-1392`, `1956-1971`, `2066-2129` под `#ifdef OXCE_AI_DEV` |
| ✔ №3 | Проверка «нет стенда ИИ» держится на метке | закрыто (метка `OXCE-AI-DEV-BUILD-MARK`) | как в README |
| ✔ №5 / 10-№1 | `_metrics` не сбрасывался | **закрыто** | `HdUi.cpp:1367`, `HdUiDraw.cpp:568` — `_metrics.clear()` |
| 10-№2 | `states.back()` без проверки в `HdControl` | **не закрыто** | `HdControl.cpp:303,475` (находка 8) |
| 10-№3 | исключение в задаче `HdWorkers` | **не закрыто** | `HdWorkers.cpp:34`, нет `try` (находка 9) |
| 10-№4 | `pixelMaskArray` на клетку | **не закрыто** | `Map.cpp:5800` (находка 12) |
| 10-№5 | `drawImage` — float в один поток | **частично**: GPU-путь, CPU-путь прежний | `HdUiDraw.cpp:850-870` |
| 10-№6 | 960 фигур HdBaseLife на основном потоке | **закрыто** | `HdBaseLife.cpp:278` — `HdWorkers::run` по фигурам |
| 10-№9 | `hdTintOf` 9 раз на клетку | **не закрыто** (центр переиспользован, 8 соседних считаются) | `Map.cpp:1760,1790` (находка 13) |
| 10-№12 | `paletteIndexOf` бинарным поиском на пиксель | **не закрыто** | `HdCanvas.cpp:2163-2166` (`std::lower_bound` на вызов) |
| 20 (README §2) | `--export-all-symbols`, таблица символов | **таблица символов срезана (`-s`)**, `--export-all-symbols` оставлен намеренно (комментарий: crashDump читает таблицу экспорта) | `src/CMakeLists.txt:713-718` |
| §2 README | `RGBtoYUV[16777216]` — 64 МБ статик | **не закрыто**, но стоит в `.bss` (в файл exe не входит) и заполняется только при `hqx` (`Zoom.cpp:766`); в размер exe не влияет, в ОЗУ 64 МБ только при включённом фильтре hqx | `Scalers/init.cpp:22-37` |
| README §1.8 | `AiProbe::note` заглушки (247 вызовов) | **почти закрыто**: в `src` сейчас 20 вызовов `AiProbe::note`; тело при выпуске — заглушка (в заголовке объявлена, реализация `AiProbe.cpp`) | `grep -rn "AiProbe::note" src` → 20 |
| 20-№ | `upper(getName())` в тройном цикле | **не закрыто** | `CollapsePilot.cpp:861` (находка 16) |
| 10-№14 | тестовые выгрузки PalShift и AddressTrace в exe | **не закрыто**, прибавились новые хуки | находка 7 |
| 20 | Таблица обрушения 376 062 строки в исходнике | **закрыто** | `CollapsePilotData.bin` 533 434 байт, `CollapsePilotData.player.bin` 445 042 байт |

## Что в порядке

- **Песочница Lua.** Белый список base (`LuaSandbox.cpp:60-63`); `string.dump` убран (`:365`), `math.randomseed` убран, метатаблица строк закрыта; загрузка только текстом (`luaL_loadbufferx(..., "t")`, `:513,538`); лимит инструкций через `lua_sethook(count)`, лимит C-циклов (`oxce_lua_c_tick` вписан в `lstrlib.c`, `ltablib.c`, `lvm.c`, `lutf8lib.c` и др.), лимит памяти 32 МБ в аллокаторе (`alloc`, `:80-110`), ошибки подряд → мод отключается (`maxErrors = 5`), `pcall` не глотает лимит (`safePcall`), `__gc` запрещён (иначе финализатор вне хука), `LUAI_MAXSTACK` уменьшен. Lua 5.4.9 (`libs/lua/README.txt`), собран как C++ (исключения, не `longjmp`) — безопасно для `std::string` в обработчиках.
- **Механика без Lua-модов.** Каждый вызов `lua->fire(...)` стоит за `getLuaHost()` (нуль, если ни одного мода с `lua/main.lua` и `oxceLuaMods` = false по умолчанию, `Options.cpp:383`); `LuaHost::create` возвращает нуль при `off`. Вызовы из рабочих потоков отсекаются (`fireOutputs`: `this_thread::get_id() != g_mainThread`).
- **Очередь изменений Lua** (`spawn`, `map`, `economy`): исполняется в известный момент (`runQueue`), сбрасывается при новом бое (`dropQueue`), ошибка обработчика откатывает очередь и счёт (`dropQueued`, `endEconomy`), изменение помечается в сейве (`luaTouch` — `economy`, `map`, `spawn`).
- **KnowledgeArmor** (`KnowledgeArmor.cpp:49-103`): при `oxceKnowledgeArmor = false` (по умолчанию, `Options.cpp:549`) возвращает `type->ArmorEffectiveness` без изменения; формула смещения детерминирована и не использует ГСЧ.
- **TransferItemsState**, рамка на глобусе (`GeoscapeState`, `Globe::takeBox/getTargetsInRect`): цвета строк — опция `oxceHdTransferSides`; рамка — `oxceHdGlobeBox`; только рисование/выбор самолётов, лимит 4 как у Intercept.
- **TileEngine/Pathfinding/UnitWalkBState.** Все ветки под `crushTerrain > 0` или `oxceCollapse`; `trunkArmor` при выключенных опциях возвращает `md->getArmor()`; замена `tile->damage(...)` на `tileFinalDamage >= armorToBreak && tile->damage(...)` равносильна, потому что `Tile::damage` и так проверяет `power >= armor`.
- **Новые Lua-экраны:** картинки проверяются перед `getSurface(image)` без `error=false`; выход экрана проверяется `find(screen)`.
- **HD-кэши:** куклы — кэш по хэшу пикселей композита (`HdUiArt.cpp:240-246`), PNG слоёв декодируются на `HdWorkers` (`:496-503`), сборка слоёв режется на `jobs` строк (`:530-560`), бюджет с вытеснением; затенение углов `hdFloorAo` — кэш на клетку и на уникальную форму (2048 кадров максимум, при переполнении рисует без тени и пишет предупреждение один раз); `mech.txt` читается один раз и кэшируется по типу брони (`HdFx.cpp:256-300`); `HdSmoke`/`HdFire`/`HdBaseLife` идут через `HdWorkers`.
- **Размер exe.** 26,2 МБ против 62 МБ (27.10): таблица обрушения в `.bin`, символы срезаны.

## Не проверено

- Каждый шаблон `unitSet`/`unitSet2`/`BattleUnit::LuaApi` по отдельности (проверил только `setArmor`/`addArmor` и общий принцип «те же функции, что у Y-скриптов»).
- `Soldier::setHealthMissing/setManaMissing/setWoundRecovery` — клампы внутри `Soldier`.
- Тело `changeTile` (`LuaHost.cpp`, исполнение `tile:setPart/destroyPart` в очереди) и `finishQueued`: порядок пересчёта света/видимости после правки карты.
- `LuaScreenState` — полный разбор состояния (закрытие экрана во время обработчика, повторный вход); смотрел только места, где разыменуются `getMod()->getSurface`, `getSavedGame()`.
- `HdSprites.cpp` (вытеснение и указатели `registry`/`views`): прочитал заголовки бюджета и `erase`, но цикл вытеснения (`:887-930`) целиком не разбирал.
- Куклы: рендер по слоям (`doll`, `composeLayers`), цвета и порядок; проверял только производительность и кэш.
- `ModCheck.cpp` (+144 строки), `HdScreenThemes.*`, `OptionsScreenThemesState.*`, `HdChatNotice.*`, `HdPilotVoice.*`, `HdKillCam.*`, `HdGpuWorld.*`, `HdGpuCanvas.*` (около 5 000 новых строк): не читал.
- `Map.cpp` (+2 985 строк): прочитал `hdFloorAo`, `updateHdLight`, `hdTintOf`, вставку частиц пара; остальное — по `grep` на аллокации в `drawTerrain`.
- Никакие числа времени не замерены (R-091); для находок 12–14 перед правкой нужна строка `HD perf` на hdbench.
- Сборка, тесты `tools/lua_sandbox_test.cpp` и Ctrl+F8 не запускались.
