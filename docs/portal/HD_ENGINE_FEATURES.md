# Правки движка OXCE-HD: что работает в любой игре, что требует данных, что — арта (02.10.2026)

Перечень к HD_SUBMODS §4. Снят по коду ветки `hd-render`, только чтение; строки в пометке
«вывод» — прочитано из кода, но не проверено запуском. Класс A значит «по коду не зависит от
игры», а не «проверено во всех играх»: совместимость с конкретной игрой доказывают только проверки
ТЗ (MULTIMOD §5.5) на её сборке.

**База.** Upstream — OXCE 8.7.1 (`441cae1b0`, слит `89614f12b`). После неё 590 коммитов наши
(587 vlourie + 3 под учёткой машины, тоже vlourie: Global Transfers) и 64 — rackrossum, унаследованный
QOL-форк сообщества: не наши, но едут в нашем движке. `187df8dd3` — сжатый коммит HD-работы до 8.7.

## 1. Классы

| Класс | Значит | Что нужно в чужой игре |
|---|---|---|
| **A** | работает в любой игре OXCE | ничего; строки — в `bin/common/Language/OXCE` или `QOL` |
| **B** | нужны данные рулсета или мода | данные этой игры (спрайты, теги, статьи) или правка движка |
| **C** | нужен HD-арт в папке с именем | пакет арта, нарисованный под эту игру |

Источники строк: **OXCE** — `bin/common/Language/OXCE/*.yml`; **QOL** — `bin/common/Language/QOL`;
**LANG** — `bin/common/Language/*.yml`; **HDMOD** — `user/mods/hd/Ruleset/*.rul` (только при
включённом `hd`).

## 2. Слой HD включён всегда

`Screen.cpp` переходит на 32 бит (слоистый путь), если верно хоть одно: `use32bitScaler`, OpenGL,
`oxceHdScale > 1`, `oxceHdPictures`, `oxceHdUi > 0`. `oxceHdPictures` по умолчанию `true` — значит
Canvas32 работает в любой игре. Арт ищется по имени набора и номеру кадра, картинки интерфейса — по
имени файла, без сверки содержимого: папка `hd/` любого активного мода ложится на любую игру. Замер
на X-Com Files: ~893 кадра в 10 наборах, 314 кадров террейна в 27 наборах и не меньше 4 картинок
педии рисуются артом Пираток (`docs/research/xcf-hd-compat-2026-10.md`). Без HD-арта слой только
увеличивает классические кадры (вывод по логике поиска, не замер).

## 3. Перечень

### A — любая игра

| # | Что | Где (`src/`) | Строки | Опция (умолчание) | Механика |
|---|---|---|---|---|---|
| 1 | Ядро HD: Canvas8/32, HdSprites, HdBlit, HdWorkers, xBRZ, загрузка паков | `Engine/HdCanvas.*`, `HdSprites.cpp:76-125`, `Mod/Mod.cpp:955-1031`, `MapDataSet.cpp:253`, `Map.cpp:281-295` | — | `oxceHdPictures` (true), `oxceHdScale` (1), `oxceHdMode` (2), `oxceHdThreads` (0), `oxceHdFrameSkip` (4) | нет (только рисование); сам арт — класс C |
| 2 | Перекраска скриптом в HD-слое | `HdCanvas.cpp:599-804` `blitScripted` | — | за режимом HD | нет; исполняет скрипты самой брони |
| 3 | HD-свет | `Map.cpp:483` | OXCE | `oxceHdLight` (true) | нет; правила видимости не задеты |
| 5 | Покачивание парящих | `Map.cpp:2758` | OXCE | `oxceHdHoverBob` (true) | нет |
| 11 | Камера гибели | `Engine/HdKillCam`, `UnitDieBState.cpp:74,153` | OXCE | `oxceHdKillCam` (true), нежный режим выключает | нет (картинка и темп) |
| 12 | Номера врагов | `BattlescapeState.cpp:2528-2534` | OXCE | `oxceHdEnemyNumber` (1) | нет; только уже видимые (вывод) |
| 13 | Башня танка (drawingRoutine 5) | `UnitSprite.cpp` ~1058 | — | при `oxceHdMode != 0` | нет; спрайты самой брони |
| 17 | HD-интерфейс: скины, TTF, подписи и масштаб глобуса | `HdUi.cpp:64`, `HdUiArt`, `HdUiDraw`, `HdFont`, `Mod.cpp:2953` | OXCE | `oxceHdUi` (0), `oxceHdUiSkin` (2), `oxceHdUiFont` (0), `oxceHdGlobeScale` (0), `oxceHdUiSmooth` (true) | нет; картинки `hd/UI/*.png` и шрифты — класс C |
| 18 | Вкладка опций HD | `Menu/OptionsHdState.cpp`, `OptionsBaseState.cpp:120` | OXCE, **кроме строк огня и прицела — HDMOD** | — | нет. **Сырые ключи**, §4 |
| 21 | Нежный режим | `Engine/HdGentle.h:33-93`, `Map.cpp`, `Camera.cpp:467,498`, `Projectile.cpp:52` | OXCE | `oxceGentle` (false), `oxceGentleAsk` (true) | нет по замыслу; `tools/test_gentle_scope.py`, `test_gentle_determinism.py`. `REACTION_COLOR` 18 — индекс палитры (стандартная и Пираток) |
| 22 | Выбор языка при первом запуске | `Menu/LanguageChoiceState` | — | `oxceLanguageChosen` (false) | нет |
| 24 | Отчёт игрока F8 | `Engine/Feedback.cpp:183-202`, `Game.cpp:352-373` | — | `keyFeedback` (F8) | нет; имя лаунчера зашито — §5 |
| 25 | Дамп кадра и автоматизация (Ctrl+F8, `OXCE_HD_*`) | `BattlescapeState.cpp:3242`, `Game.cpp:429-508` | — | `keyBattleHdTestDump`; переменные среды | нет без переменных среды; в сборке игроков не вырезано |
| 26 | Смена режима HD | `BattlescapeState.cpp:3247` | — | `keyBattleHdModeToggle` (F9) | нет. **Конфликт клавиш**, §6 |
| 29 | Оружие корабля вкл/выкл в окне корабля | `Geoscape/GeoscapeCraftState` | OXCE | — | то же, что upstream даёт в других окнах |
| 31 | Цвет «нового» в педии, фильтр по алфавиту | `UfopaediaSelectState.cpp:57`, `NewBattleState` | OXCE | — | нет |
| 34 | Сводка перевозок | `Geoscape/GlobalTransfersState` | OXCE | `keyGeoGlobalTransfers` (не назначена) | нет |
| 35 | Ссылки инвентаря: достижения, бонусы | `ExtendedInventoryLinksState.cpp:155` | LANG (en-US, ru) | — | нет |
| 36 | Масштаб полос характеристик | `Basescape/SoldierInfoState` | — | — | нет |
| 37 | Экран изменения характеристик после боя | `SoldierStatChangeState`, `DebriefingState.cpp:915` | стандартные | — | нет |
| 38 | Столбец максимума в UnitInfoState | `Battlescape/UnitInfoState` | — | — | нет |
| 39 | «Продолжать работу» после производства | `ProductionCompleteState.cpp` | OXCE | — | то, что игрок может сделать руками |
| 40 | Перестановка очереди производства | список производства | OXCE | `oxceBaseManufactureReorder` (false, скрыта) | нет |
| 41 | Битая ссылка на исследование не роняет загрузку | `Mod.cpp:5248` `getResearchOrPlaceholder` | — | — | терпимость загрузки (три опечатки Пираток), как в 8.7.0 |
| 42 | Детерминированный порядок предметов при высадке | `ItemContainer::getContentsInListOrder`, `BattlescapeGenerator` deployXCOM | — | всегда | **да, малая**: порядок создания и id предметов (CHANGELOG 2026.09.29-2) |
| 43 | ИИ: kneelDefault, отход, `_bannedFirst`, AiProbe, стенд | `AiProbe.cpp:69-84`, `AIModule`, `Pathfinding`, `CMakeLists.txt:25-27` | — | сборочный флаг `OXCE_AI_DEV` (OFF) + `OXCE_AI_*` | **в сборке игроков нет**: всё через заглушки AiProbe |
| 44 | Катсцена `<id>_<lang>`, длительность слайдов (R-029), `SDL_WaitThread` (R-150), падение ModListState | `Menu/CutsceneState`, `SlideshowState`, `StartState`, `ModListState` | — | — | нет |
| 45 | Имя движка `OXCE-HD`, версия «(vlourie + MuRuCoN)» | `ModInfo`, `version.h` | — | — | моды, требующие движок `OXCE-HD`, привяжутся к нам (вывод) |
| 46 | QOL rackrossum (не наш): подсказки количества, мало маны, сортировки, фон хода врага, `dontTraceProjectiles` (режимы 3-4 наши, R-170), свет отдельного юнита, превью телепорта, рефакторинг Pathfinding, параллельное сохранение базы, прокрутка инвентаря | `TileEngine.cpp:4682`, `SoldierSortUtil.h`, миксины | QOL | `qol*` (8 опций) | свет юнита меняет освещение, а с ним ночную видимость — как общий переключатель upstream (вывод). **Рефакторинг Pathfinding на равенство не проверен** |

### B — нужны данные рулсета или мода

| # | Что | Где | Чего требует | Строки | Опция | В XCF |
|---|---|---|---|---|---|---|
| 23 | Кнопки «Мои отчёты» / «Лаунчер» в главном меню | `MainMenuState.cpp:84-101`, 148, 445 | мод `hd` включён; «Лаунчер» — ещё `Feedback::hasLauncher()` | HDMOD `reports.rul` | — | без `hd` кнопок нет (с `67b334ef2`, R-036); `tr()` всё равно зовётся — предупреждения в логе (вывод) |
| 27 | Группы в списках бойцов и значок расы (8 экранов) | `SortSoldiersMixin.h:98-167`, `SoldierSortUtil.cpp:171-190` | extraSprites `Flag<N>` и `flagOffset` бойца | OXCE | `oxceSoldierListGroupBy` (1), `oxceSoldierListRaceBadge` (true) | есть оба; в ванили столбец пуст, место занято |
| 28 | Значки оружия корабля | `CraftInfoState.cpp:64-119`, `CraftsState:136`, `InterceptState:197` | спрайт оружия в BASEBITS.PCK | OXCE | `oxceCraftWeaponIcons` (true) | данные ванили есть |
| 30 | Ссылки на педию из «НЛО обнаружен», средний щелчок по подписи на глобусе | `UfoDetectedState`, `GeoscapeState` | статьи педии | — / OXCE | — | без статьи молча ничего (вывод) |
| 32 | Строка щита в инвентаре | `InventoryState.cpp:665-680, 746-771`; `BattleUnit.cpp` ~3048-3080 | теги `Tag.UNIT_ENERGY_SHIELD_HP`, `Tag.ARMOR_ENERGY_SHIELD_CAPACITY` (скрипт щита Yankes) | OXCE | — | **теги есть**: XCF определяет их в `scripts_XCOMFILES.rul` |
| 33 | Заряд щита в слоте руки | `BattlescapeState.cpp:2055-2064` | список предметов Пираток, зашитый в код | — | — | **ни одного предмета нет** — §5 |
| 6′ | Вид удара по оружию | `hd/FX/weapons.txt` | имена предметов игры | — | — | свой список на игру |

### C — нужен HD-арт с именем

| # | Что | Папка арта | Строки | Опция (умолчание) |
|---|---|---|---|---|
| 1′ | Паки наборов и террейна | `hd/<НАБОР>/`, `pack.hdp`, `hd/TERRAIN/<имя>.PCK/` | — | `oxceHdPictures` |
| 4 | Варианты земли | `hd/TERRAIN/…/<i>.v<n>.png` | OXCE | `oxceHdGroundVariants` (true) |
| 6 | Эффекты: попадания, трассеры, материал террейна | `hd/FX/<клип>/`; `HdFx.cpp:129-163` (вид урона → семейство), 211-216 (подстроки материала) | OXCE | `oxceHdFx` (true) |
| 7 | Огонь и дым | `hd/SMOKE.PCK` | **HDMOD `fire.rul`** | `oxceHdFire` (2) |
| 8 | Стили прицела | `hd/CURSOR.PCK/reticle_<стиль>/` (`Mod.cpp:1072` `HD_RETICLES`) | **HDMOD `reticle.rul`** | `oxceHdReticle` (0) |
| 9 | Стрелки пути | `hd/Pathfinding` | — | режим HD |
| 10 | Анимированные указатели на полу | `hd/UI/anim/<имя>/` (имена upstream) | — | режим HD |
| 14 | Контуры кораблей на глобусе и в перехвате | `hd/OUTLINE/index.txt`, `<тип>.png`; цвет расы — хэш имени расы (`HdOutline.cpp:282`) | — | `oxceHdCraftOutlines` (true); в сейв пишется лишний ключ `hdDecoded` (только контур) |
| 15 | Анимация базы | `hd/BASEBITS.PCK/<i>.v<n>.png`, `.anim.txt` | — | `oxceHdBaseAnim` (true) |
| 16 | Огни кораблей в ангаре | `hd/BASEBITS.PCK/<i>.lights.txt` | стандартные | `oxceHdCraftLights` (true) |
| 17′ | Картинки интерфейса и шрифты | `hd/UI/*.png` (по имени в нижнем регистре), `hd/UI/Font*.ttf`, `hd/UI/fonts` | — | `oxceHdUi` |
| 20 | Экран выбора версии 18+ | проверяет `hd_18+/{UI,TERRAIN,GLOBE,BASEBITS.PCK}`; только при включённом `hd` | HDMOD `adult.rul` | `oxceAdultArt` (false), `oxceAdultAsk` (true) |

**Картинки глобуса (день/ночь)** — в коде нет загрузчика ни сейчас, ни в истории. Ключи
`oxceHdGlobe*`, `oxceAdultContent` в options.cfg установки остались от незакоммиченной сборки (вывод).

## 4. Сырые ключи `STR_` в игре без `hd`

1. **Вкладка опций HD, строки «Огонь» и «Прицел»** (`OptionsHdState.cpp:219-231`): `tr("STR_HD_FIRE_<n>")`,
   `tr("STR_HD_RETICLE_*")`, а строки лежат только в `hd/Ruleset/fire.rul` и `reticle.rul`. Вкладка
   показывается всегда (без `hd` — с пометкой `STR_HD_MOD_OFF`, но со всеми строками). Единственный
   видимый случай.
2. **`STR_MY_REPORTS`, `STR_LAUNCHER`**: кнопок без `hd` нет, но строки запрашиваются — только лог (вывод).
3. Нежный режим и выбор языка показываются в любой игре, строки у них в OXCE или их нет — безопасно.

**Требования — два, и одно другое не заменяет.**

1. **Видимость опций уже задана ТЗ** (MULTIMOD §0 п. 4, §6.1–6.2): строка вкладки HD видна, только
   если её возможность подтверждена ресурсом активной сборки (`hdFire` — варианты `SMOKE`,
   `reticleStyles` — стили прицела и т. д.). Скрытая опция не сбрасывается: значение остаётся в
   конфиге сборки и вернётся с артом. Значит, без арта строк «Огонь» и «Прицел» нет вовсе — сейчас
   код этого не делает, вкладка показывает все строки.
2. **Строки — в движке** (отзыв: «общие строки движка доступны без HD-пакета»): `STR_HD_FIRE_*`,
   `STR_HD_RETICLE_*`, строки `reports.rul` и `adult.rul` переносятся в `bin/common/Language/OXCE`
   (исключение «Святого правила»: без предупреждения, но с переносом в установку Пираток). Это
   убирает сырые ключи там, где опция видна, но не решает, видна ли она.

## 5. Литералы Пираток в коде

| Где | Что | В другой игре |
|---|---|---|
| `BattlescapeState.cpp:2055-2064` | `shieldItemTypes`: `STR_ENERGY_SHIELD_SMALL`, `STR_REFRACTOR_SHIELD_SMALL`, `STR_ARCANE_SHIELD_SMALL`, `STR_ENERGY_MATRIX_SMALL`, `AUX_ENERGY_SHIELD_FAKK`, `AUX_GORGON_SHIELD`, `STR_HELLFIST` | не срабатывает: в XCF ни одного. Связь чисто Пираток; если нужна в другой игре — признак из рулсета (например, тег), а не список |
| `InventoryState.cpp:673-674` | `Tag.UNIT_ENERGY_SHIELD_HP`, `Tag.ARMOR_ENERGY_SHIELD_CAPACITY` | работает там, где стоит скрипт щита Yankes: Пиратки и XCF |
| `Feedback.cpp:202` | `XPiratezLauncher.exe` — запасное имя после `XP_LAUNCHER` и `launcher/launcher-path.txt` | имя лаунчера сменится при ребрендинге |
| `HdFx.cpp:129-163` | виды урона 11-15 → семейства эффектов по смыслу Пираток | номера в другой игре значат то, что скажет её рулсет; эффект будет другим по виду, механика не задета |
| `HdFx.cpp:211-216` | подстроки материала террейна (`CULT`, `SHACK`…) | эвристика: нет совпадения — общий материал |
| `Mod.cpp:1072` | `HD_RETICLES` `ring45/plasma/techno/predator` | имена папок пакета, не данные игры |
| `MainMenuState.cpp:87`, `AdultChoiceState.cpp:36,65`, `OptionsHdState.cpp:40,95` | id мода `hd`: кнопки меню, экран 18+, пометка «HD-мод выключен» | наш, не Пираток, но это проверка по имени мода — ТЗ её запрещает (MULTIMOD §0 п. 4). Раздел на пакеты сохраняет id `hd` у пакета Пираток, пока проверки не заменены проверками ресурса (HD_SUBMODS §5, шаги 1–2) |

Упоминания Пираток в комментариях (без поведения): `CraftSoldiersState:291`, `SoldiersState:378`,
`Bar.cpp:189`, `UnitSprite.cpp:1058`, `HdUiArt.cpp:288,327`, `HdUi.cpp:625`, `HdSprites.cpp:1041`,
`HdFont.cpp:39`, `BattlescapeGame.cpp:3063`, `HdCanvas.cpp:663`, `UfopaediaSelectState.cpp:57`,
`Mod.cpp:5242`, `HdGentle.h:45`, `SortSoldiersMixin.h:147`.

## 6. Механика — итог

- Ни одна функция показа правил не трогает.
- **Исключение в сборке игроков:** детерминированный порядок предметов при высадке (#42) — меняет id
  и порядок создания предметов, а с ними разбор равных вариантов у ИИ.
- Правки ИИ (#43) вырезаны сборкой (`OXCE_AI_DEV` OFF) и вдобавок требуют переменных `OXCE_AI_*`.
- Нежный режим закрыт тестом области (`test_gentle_scope.py`).
- От rackrossum, не наше: свет отдельного юнита влияет на ночную видимость, как общий переключатель
  (вывод); рефакторинг Pathfinding на равенство с upstream не проверен.
- **F9 — две команды сразу** (проверено по коду, `BattlescapeState.cpp:3229-3250`): `keyQuickLoad`
  (upstream, F9) и `keyBattleHdModeToggle` (наш, F9) обрабатываются в одном проходе; вне ironman
  нажатие F9 и загружает быстрое сохранение, и меняет режим HD. Правил не меняет, но это ошибка
  управления — нужна другая клавиша по умолчанию для смены режима.

## 7. Главный риск для чужой игры

У `hd` `master: "*"`, а арт сопоставляется по имени набора и номеру кадра. Включённый `hd` рисует
арт Пираток поверх кадров другой игры (замер на XCF, §2). Раздел на пакеты (HD_SUBMODS) снимает это
для того, что уходит в `hd_piratez`; подписи исходного ресурса (этап 6) — для общих кандидатов.
