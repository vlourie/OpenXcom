# П-4. Оборона базы на стенде ИИ: статическая проверка

Только чтение кода и рулсетов. Игра и бои не запускались, `src/` и Git не тронуты, Codex не вызывался.
Все пути от `E:\OpenXCom\`. Раздел 5.6 документа: `docs/research/ai-mechanics/AUDIT-STAGE-1-BENCHMARK-DESIGN.md`, строки 191-202.

Сборка стенда: `OXCE_AI_DEV` (в `AiProbe.cpp` ветка `#else` со строки 424 до `#endif` на 6371). Знание «честное» включается переменной
`OXCE_AI_FAIR_KNOWLEDGE=1` (в `harness` читается из окружения, `AiProbe.cpp:796-800`, `5945-5949`).

## 1. Сводная таблица

| № | Пункт | Вердикт | Где в коде | Цитата |
|---|---|---|---|---|
| 1.1 | В бой идут бойцы базы из сейва, `_craft` обнуляется | верно | `src/Menu/NewBattleState.cpp:968-973` | `base = _craft->getBase(); bgen.setBase(base); _craft = 0;` |
| 1.2 | «Все бойцы базы» | **неверно как сформулировано** (идут не все) | `src/Battlescape/BattlescapeGenerator.cpp:1123-1124`, `1184-1185` | `(_craft == 0 && (soldier->hasFullHealth() \|\| soldier->canDefendBase()) && (soldier->getCraft() == 0 \|\| soldier->getCraft()->getStatus() != "STR_OUT"))` |
| 1.3 | Раненые отсекаются порогом `oxceWoundedDefendBaseIf` | верно по коду; значение на стенде не доказано | `src/Savegame/Soldier.cpp:1124-1127`; `src/Engine/Options.cpp:514` (умолчание 100); Piratez даёт 60 только как рекомендацию: `Пиратки/Dioxine_XPiratez/user/mods/Piratez/Ruleset/Piratez_Globals.rul:9150-9168` (`recommendedUserOptions`) | `return currentHealthPercentage >= Options::oxceWoundedDefendBaseIf;` |
| 1.4 | Бойцы кораблей со статусом `STR_OUT` не идут | верно (но на стенде статус берётся из сейва) | `BattlescapeGenerator.cpp:1124`, `1185` | `getCraft()->getStatus() != "STR_OUT"` |
| 1.5 | Только одна база (та, к которой приписан выбранный корабль) | верно | `NewBattleState.cpp:970`; выбор корабля сидом `NewBattleState.cpp:764-770`; перебор `deployXCOM` по `_base->getSoldiers()` (`BattlescapeGenerator.cpp:1117`, `1178`) | `_craft = crews[pick(crews.size())];` |
| 1.6 | `OXCE_AI_SQUAD` на состав обороны не влияет | **верно по результату, механизм иной** | `NewBattleState.cpp:773-813` | `crew[i]->setCraft(nullptr);` (лишних снимают с корабля, но `craft == 0` проходит фильтр 1.2, т.е. они всё равно идут) |
| 1.7 | `OXCE_AI_SQUAD` всё же влияет на выбор базы | не отражено в документе | `NewBattleState.cpp:791-807` | `if (strength(craft) > strength(_craft)) { _craft = craft; }` (выбирается корабль с самыми опытными бойцами, а значит и база) |
| 1.8 | Ограничения по числу нет в генераторе; предел - свободные точки появления `NR_XCOM` | верно | `BattlescapeGenerator.cpp:1491-1503`, `1504` (для обороны базы нет запасного `placeUnitNearFriend`), `1620` (`delete unit; return 0;`); `src/Savegame/SavedBattleGame.cpp:2341-2358` (`getSpawnNode`) | `else if (_save->getMissionType() != "STR_BASE_DEFENSE")` |
| 1.9 | Техника (HWP) на стенде | **документ молчит; по коду на стенде не идёт** | `BattlescapeGenerator.cpp:1049-1073`; `src/Savegame/Base.cpp:1612-1642` (`setupDefenses` наполняет `_vehicles`); единственный вызов `src/Geoscape/GeoscapeState.cpp:1115`; в `Base.cpp` нет загрузки `_vehicles` из сейва | `base->setupDefenses(mission);` (только в геоскейпе); ветка кораблей `if (... getMonthsPassed() == -1)` только для быстрого боя (`1061`) |
| 1.10 | Предметы склада базы на карте | верно, с фильтром | `BattlescapeGenerator.cpp:1261-1291` | `rule->canBeEquippedBeforeBaseDefense() && rule->isInventoryItem() && (rule->isUsefulBattlescapeItem() \|\| rule->canBeEquippedToCraftInventory()) && isResearched(...)` |
| 1.11 | Режим без `OXCE_AI_CAMPAIGN` (быстрый бой, `monthsPassed == -1`) - другой набор | не отражено | `NewBattleState.cpp:719-761` (сейв только при `OXCE_AI_CAMPAIGN`); `BattlescapeGenerator.cpp:1061`, `1264` | `if (_game->getSavedGame()->getMonthsPassed() == -1)` |
| 2.1 | Карта строится из модулей базы сейва | верно | `BattlescapeGenerator.cpp:2987-3014` (вызов), `3517-3520` | `for (const auto* fac : *_base->getFacilities()) { if (fac->isBuiltOrHadPreviousFacility())` |
| 2.2 | Блок модуля берётся по `mapName` постройки и порядковому номеру | верно | `BattlescapeGenerator.cpp:3583-3599` | `auto* block = _terrain->getMapBlock(newname.str()); ... addBlock(x, y, block, _terrain);` |
| 2.3 | Террейн базы в Пиратках: `XBASE`, 60x60x5, затенение 6 | верно | `Пиратки/Dioxine_XPiratez/user/mods/Piratez/Ruleset/Piratez_Factions.rul:113136-113146` (переопределяет ваниль `.../standard/xcom1/alienDeployments.rul:1017`) | `- type: STR_BASE_DEFENSE ... terrains: - XBASE ... shade: 6` |
| 2.4 | Карта не зависит от места базы на глобусе в Пиратках | верно | `BattlescapeGenerator.cpp:2989-3013`; ключ `baseDefenseMapFromLocation` читается `src/Mod/Mod.cpp:4053`, в рулсетах Пираток и `standard/xcom1` не найден (искал по `Piratez/` и `standard/xcom1`) | `if (_mod->getBaseDefenseMapFromLocation() == 1) {...} else { generateBaseMap(); }` |
| 2.5 | Склад: клетки хранения `_save->getStorageSpace()` из модулей-складов | верно | `BattlescapeGenerator.cpp:3603-3636` (шахматка), `3641-3683` (явные `storageTiles`) | `_save->getStorageSpace().push_back(Position(k, l, groundLevel));` |
| 2.6 | Карта модулей (здоровье модулей для ИИ) | верно, ванильно | `BattlescapeGenerator.cpp:3696` -> `src/Savegame/SavedBattleGame.cpp:3095-3114` (`calculateModuleMap`) | `if (... getMapData(O_OBJECT)->isBaseModule())` |
| 2.7 | Узлы маршрутов берутся из файлов маршрутов блоков модулей | верно | `BattlescapeGenerator.cpp:3430` (`loadNodes()`), `4108-4133`, `2507-2562` (`loadRMP`), связи `3505`/`4138` (`attachNodeLinks`) | `std::string filename = "ROUTES/" + mapblock->getName() +".RMP";` |
| 2.8 | Узел-цель для разрушения модулей: флаг `reserved == 5` | верно | `src/Savegame/Node.cpp:186-189` | `return _reserved == 5;` |
| 2.9 | Тайлы базы помечены «видимыми» (для игрока) | верно, ИИ не затрагивает | `BattlescapeGenerator.cpp:4624`, `2317`, ещё `3201`, `3287`, `4038`, `4073` | `bool visible = (_save->getMissionType() == "STR_BASE_DEFENSE"); // yes, i'm hard coding these` (в `AIModule.cpp` нет ни `isDiscovered`, ни `getDiscovered`) |
| 3.1 | Особые ветки ИИ для `STR_BASE_DEFENSE` | найдены три (ванильные) | `src/Battlescape/AIModule.cpp:2023`, `2039-2107`, `3845-3849` | `escapeOdds *= 0.75; ambushOdds *= 0.6;` |
| 3.2 | Враг на обороне базы знает расположение модулей (идёт к целевым узлам живых модулей) | верно, ванильно, не добавлено стендом | `AIModule.cpp:2096-2103`; `Mod.cpp:3947` (`destroyBaseFacilities`); Пиратки включают: `Piratez_Globals.rul:9176` | `if (node->isTarget() && !node->isAllocated() && _save->getModuleMap()[...].second > 0)` |
| 3.3 | Враг знает позиции бойцов с самого начала | **не найдено** | стартовые значения: `src/Savegame/BattleUnit.h:136` (`_turnsSinceSpotted[FACTION_MAX] = { 255, 255, 255 }`), `141` (`_aiSeen ... = { -1, -1, -1, -1 }`); сброс `BattleUnit.cpp:4992-5010`; `grep` по `setTurnsSinceSpotted` даёт только `SavedBattleGame.cpp:1629`, `TileEngine.cpp:1526`, `2682`, `5527`, `BattlescapeGame.cpp:1106`, `BattleUnit.cpp:2093` | `Uint8 _turnsSinceSpotted[FACTION_MAX] = { 255, 255, 255 };` |
| 3.4 | Знание боевых позиций бойцов берётся из линии видимости | верно, одинаково для всех миссий | `src/Battlescape/TileEngine.cpp:1524-1531` | `bu->setTurnsSinceSpottedByFaction(unit->getFaction(), 0);` (ветки по типу миссии нет) |
| 3.5 | «Читерство» (`_cheating`) на обороне базы - то же, что в других боях | верно | `src/Savegame/SavedBattleGame.cpp:1611-1630`; `AIModule.cpp:1170`, `3884-3887` | `if ((_turn > _cheatTurn / 2 && tally.liveAliens <= 2) \|\| _turn > _cheatTurn) { _cheating = true; }` затем `bu->setTurnsSinceSpotted(0)` для всех живых бойцов игрока |
| 3.6 | Ветка `scout` в `AIModule.cpp:2023-2036` (читерство делает всех разведчиками) на обороне базы **не работает** | верно, ванильно | `AIModule.cpp:2023-2036` | `if (_save->getMissionType() != "STR_BASE_DEFENSE") { ... if (_save->isCheating() \|\| ...) scout = true; ...}` |
| 3.7 | Что стенд меняет: честная память (`FAIR_KNOWLEDGE`) | верно, но не специфично для обороны | `AiProbe.cpp:5945-5949`, `5990-6024` (`fairPlace`), `AIModule.cpp:3544-3556`, `BattleUnit.cpp:5136-5181`, `TileEngine.cpp:1531` | `if (side == FACTION_HOSTILE && save->isCheating() && target->getFaction() == FACTION_PLAYER) { ... return 0; }` (читерство исключено из честной памяти) |
| 3.8 | Серия стенда запускается с `OXCE_AI_FAIR_KNOWLEDGE=1` | верно по одному снимку | `E:\OXCE_AIWorker\stand2\int\work\oxce_ai_probe\arena\iB1_STR_VESSEL_SOTL_SECTOID_ELITE_1155.prov.txt` (строки 10-12) | `OXCE_AI_FAIR_KNOWLEDGE=1`; боёв обороны базы в этом каталоге не нашёл (`ls | grep BASE_DEF` пусто) |
| 3.9 | Кэш покрытий `AiCoverMap` отключён на обороне базы | верно | `src/Battlescape/AiCoverMap.cpp:496` | `if (mode() == 0 \|\| save->getMissionType() == "STR_BASE_DEFENSE") return;` (ускоряющий кэш; влияет ли на решения - не доказано) |
| 3.10 | Релизная сборка и стенд расходятся по `FAIR_KNOWLEDGE` | верно, и это не про оборону | `AiProbe.cpp:409` (релиз всегда `0`), `434` (`AI3_PROFILE` включает `1`); подробно в `docs/research/ai-mechanics/AUDIT-DEV-RELEASE-DIFF-2026-10-23.md`, D04 | `int fairKnowledge() { return 0; }` |
| 4.1 | `cheatTurn` у `STR_BASE_DEFENSE` в Пиратках | **не задан -> умолчание 20** | умолчание `src/Mod/AlienDeployment.cpp:42`, чтение `:170`; рулсет `Piratez_Factions.rul:113136-113146` и ваниль `standard/xcom1/alienDeployments.rul:1017` ключа не содержат | `_turnLimit(0), _cheatTurn(20), ...` |
| 4.2 | `cheatTurn` у `STR_GOVT_BASE_DEFENSE` | **не задан -> 20** | `Piratez_Factions.rul:112930-113135` (в диапазоне нет `cheatTurn`) | то же умолчание |
| 4.3 | `cheatTurn` у `STR_VESSEL_NIN_APC` | **не задан -> 20** | `Piratez_Factions.rul:107120-107191` (в диапазоне нет `cheatTurn`); корабль `ufos` в `:49589` | то же умолчание |
| 4.4 | Единственное развёртывание Пираток с `cheatTurn` | `STR_MARS_THE_FINAL_ASSAULT_2` = 5 | `Piratez_Factions.rul:114614`, `:114631`; `.index/mod/Piratez/rul/values.tsv:3709` | `cheatTurn: 5` |
| 4.5 | Развёртывание берётся по типу миссии | верно | `BattlescapeGenerator.cpp:781`, `785` | `getDeployment(_ufo?_ufo->getRules()->getType():_save->getMissionType(), true)` ... `_save->setCheatTurn(ruleDeploy->getCheatTurn());` |
| 4.6 | Особые ветки `== "STR_BASE_DEFENSE"` не срабатывают у `STR_GOVT_BASE_DEFENSE` | верно (сравнение по точной строке) | `NewBattleState.cpp:1006-1016` (обычный сайт миссии), `AIModule.cpp:2023`, `3845` | `_save->getMissionType() == "STR_BASE_DEFENSE"` |

## 2. Расхождения с разделом 5.6 документа

1. «В бой идут **все** бойцы базы» - неточно. Идут бойцы одной базы (той, к которой приписан выбранный сидом корабль), у которых
   `hasFullHealth()` или `canDefendBase()`, и не те, чей корабль имеет статус `STR_OUT`. Раненый боец отсекается порогом
   `oxceWoundedDefendBaseIf` (умолчание 100; Пиратки лишь рекомендуют 60). Реальное значение на стенде зависит от `options.cfg`
   стенда - не доказано, надо смотреть на станции. Предел по числу - свободные точки появления `NR_XCOM` на карте базы.
2. «`OXCE_AI_SQUAD` на это не влияет» - по составу боя верно, но стоит дописать два факта. Переменная всё же выбирает корабль
   с самыми опытными бойцами, а значит и базу (`NewBattleState.cpp:791-807`). Лишних бойцов она снимает с корабля, но не из
   боя (`setCraft(nullptr)`, дальше они проходят `craft == 0`).
3. Техника (HWP) документом не упомянута. По коду на стенде в обороне её нет: `Base::_vehicles` наполняет только
   `Base::setupDefenses` (вызов лишь в `GeoscapeState.cpp:1115`), а при загрузке сейва `_vehicles` не восстанавливается.
   Вывод по коду, на реальном бою не проверен.
4. Предметы со склада базы идут не все, а по фильтру (`BattlescapeGenerator.cpp:1270-1279`) и только если исследовано.
5. Документ описывает только режим с `OXCE_AI_CAMPAIGN`. Без него (быстрый бой с рекрутами, `monthsPassed == -1`) состав и
   предметы другие (`BattlescapeGenerator.cpp:1061`, `1264`).
6. «Правило "враг знает карту, кроме баз игрока"» - формулировка документа сама по себе расплывчата. По коду картина такая:
   в штатной игре на обороне базы враг не знает позиций бойцов заранее (в начале `turnsSinceSpotted = 255`, `aiSeen = -1`),
   но **знает расположение живых модулей базы** и идёт к целевым узлам (`AIModule.cpp:2096`, включено Пираткой через
   `destroyBaseFacilities: true`). Это ванильная механика, стенд её не меняет. Нужно решение Vitali: считать ли её
   нарушением правила или штатным знанием. Предложение документа «нужна проверка» этим закрыто по коду, но не по бою.
7. Документ не упоминает, что `AiCoverMap` на обороне базы выключен (`AiCoverMap.cpp:496`). Это кэш для скорости, и
   на решения он, скорее всего, не влияет, но это не доказано.

## 3. Итог по вопросу «знает ли ИИ больше, чем в штатной игре»

- Заранее позиции бойцов: нет. Начальные значения `255` и `-1`, особых записей для обороны базы нет (`grep` по `isCheating`, `setTurnsSinceSpotted`, `STR_BASE_DEFENSE` в `src/Battlescape` и `src/Savegame`).
- Карта и модули: да, как и в штатной игре (ИИ видит всё поле целиком, а на обороне базы идёт к целевым узлам живых модулей).
- «Читерство» после хода `cheatTurn` (20 или после 10-го хода при двух и менее живых врагах): одинаково с другими боями, `cheatTurn` у обороны базы не переопределён. С включённой честной памятью читерство оставлено как в штатной игре (`AiProbe.cpp:6004-6011`).
- Что стенд меняет в любую сторону: честная память `FAIR_KNOWLEDGE` (делает врага *менее* осведомлённым, чем в штатной игре, пока не наступило читерство); одинаково во всех миссиях, для обороны ничего особого.

## 4. Что можно проверить на стенде без правок (ничего не запускалось)

Журнал игры (`[AITRACE]`, только при `OXCE_AI_FAIR_KNOWLEDGE=1`):

- `{"ai2h":1,"rec":..,"cons":"cheat","kind":3,...}` - строка `fairNote` (`AiProbe.cpp:6026-6046`): враг использует читерское знание вместо памяти; поле `since` - `turnsSinceSpotted`. Первая такая строка показывает ход, с которого читерство действует.
- `{"ai2h":1,"aim":..,"kind":1|2,...,"oracle":0|1,"seenNow":..}` (`:6064`) - прицеливание в текущее место цели, которого враг по памяти не знает. `kind=2` - цель не видели ни разу. Для обороны базы интересно число `oracle=1` на ходах до читерства.
- `{"ai2h":1,"vis":..,"n":..,"off":[..]}` (`:6091`) - видимые враги, чья запомненная позиция отличается от реальной.
- Запись памяти (`BattleUnit.cpp:5187-5197`, `AiProbe.cpp:6338-6366`): причины `OBSERVATION_FOV`, `OBSERVATION_REACTION`, `DIRECT_SHOT_REVEAL`, `HIT_REVEAL`, `KILL_REVEAL`, `LOAD`, `FORGET_PROBE`. Если у бойцов игрока появляется запись памяти врага до первого `OBSERVATION_*` - это и есть заранее известное знание.
- Отказы записи (`fairDeny`, `:6316-6335`) и `vgeo` (`:6101`) - факты о том, где честная память не обновилась.
- `[AIPROBE] start: turn .., mission STR_BASE_DEFENSE` (`AiProbe.cpp:593`) и `logState(save, "before")` (`:595`) - число и состав сторон в начале боя; сверяется с пунктами 1.2-1.9.
- `[AIPROBE] loadout soldier=.. -> ..` (`NewBattleState.cpp:703`) - перевооружение при `OXCE_AI_LOADOUT_FIX=1`, показывает, кто из бойцов базы шёл в бой по фильтру (тот же фильтр, что в `deployXCOM`).
- `OXCE_AI_FAIR_SAVECHECK=1` - `{"ai2h":1,"savecheck":1,...}` и `savediff` (`AiProbe.cpp:6141-6183`): сверка записи памяти с сохранением.

Поля сейва боя:

- у каждого юнита: `turnsSinceSpotted`, `turnsSinceSpottedByXcom`, `turnsSinceSpottedByCivilian` (`BattleUnit.cpp:837-841`), `turnsLeftSpottedForSnipers*` (`:838-842`), `aiSeen` (`:937-945`, пишется только с включённым флагом);
- глобально: `cheatTurn` (`SavedBattleGame.cpp:672`), `turn`, `moduleMap` для обороны базы (`:642`), узлы `nodes` (с признаком цели, `reserved`).
- Проверка: на ходу 1 у всех бойцов игрока `turnsSinceSpotted = 255` и `aiSeen` отсутствует, пока их никто не видел; значение `cheatTurn` в сейве обороны базы = 20.
- Состав: число юнитов фракции игрока в сейве против числа здоровых бойцов базы (пункт 1.2) и признак наличия HWP (пункт 1.9).

Не проверено и требует боя: реальное значение `oxceWoundedDefendBaseIf` на стенде, наличие HWP в бою, влияние отключённого `AiCoverMap` на решения, число доступных точек появления `NR_XCOM` на карте базы Vitali.
