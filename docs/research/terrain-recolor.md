# Перекраска блоков террейна в оригинале

Дата: 2026-09-28 | Уверенность: средняя (данные проверены кодом и перепиской PCK; часть выводов
о влиянии на HD-слой — по чтению кода, без прогона игры, см. «Чего НЕ выяснил»)

## Краткий ответ

Игра не перекрашивает тайлы террейна на лету. Каждый «цветной вариант» набора (CAVEAQUA рядом с
CAVEBROWN, C_EXT_ROOF_PRPL рядом с C_EXT_ROOF) — это **отдельный PCK/TAB/MCD**, нарисованный
художником мода заранее и подключённый в `terrains.mapDataSets` конкретного террейна. Движок
умеет перекрашивать «на лету» только юнитов и предметы (`BattleUnit::_recolor`,
`RecolorItemParser`) через замену группы 0xF0 индекса при сохранении оттенка 0x0F; для тайлов та
же машинерия (`newBaseColor`) используется только под один сценарий на всю карту — прибор ночного
видения (`Map::_nvColor`). Часть наборов-«перекрасок» и правда получена сдвигом индекса на целую
рампу (кратно 16, как у юнитов) — таких кадров подтверждено немного и по выборочной проверке; но
многие пары («CAVEBROWN → CAVEAQUA/CAVEMARS/CAVEDOOM/CAVEMEAT», `SGR_WALLS` → `_P/_B/_GOLD`) —
это произвольная, несводимая к одному сдвигу замена индекс-в-индекс, то есть фактически новая
покраска. Боевая палитра САМА не одна на весь мод: 23 `enviroEffects.paletteTransformations` и 3
уровня `depth` подменяют RGB `PAL_BATTLESCAPE` целиком на другой `.pal`-файл на время миссии;
HD-паки к этому не привязаны и её не учитывают.

## Детали

### 1. Перекраски на уровне данных: `census/frames.tsv`

Строит `tools/pck_census.py` (`py -3 tools\pck_census.py --install "Пиратки\Dioxine_XPiratez" --out census`).
Для каждого кадра TERRAIN/UNITS/UFOGRAPH/GEOGRAPH считаются четыре отпечатка (`fingerprints()`,
`tools/pck_census.py:218-237`):

| колонка `census/frames.tsv` | что это | как считается |
|---|---|---|
| `точный` | побайтовый рисунок | sha1 плоского массива индексов кадра |
| `силуэт` | маска непрозрачности | sha1 массива 0/1 по ненулевым индексам |
| `раскраска` | кандидат «то же самое в другом цвете» | индексы кадра заменены номером ПОРЯДКА первого появления (значение не важно, важен порядок); две картинки с одинаковой формой, но разными исходными индексами дают одинаковый хэш |
| `зеркало` | кандидат «то же самое отражённое по горизонтали» | sha1 кадра, отражённого построчно |

Важная оговорка из самого кода (`tools/pck_census.py:219-223`): «recolor — это КАНДИДАТ в
перекраску, а не доказательство — решает глаз на листе сравнения». Совпадение хэша `раскраска`
гарантирует одинаковую форму и одинаковый ПОРЯДОК появления цветов, но не гарантирует, что связь
между исходным и целевым индексом — это единый сдвиг, и не гарантирует, что материал (не только
цвет) остался тем же.

`census/roadmap.md` / `roadmap.tsv` строит `tools/pck_roadmap.py`: наборы сортируются по числу
клеток на картах (`sets.tsv`), и для каждого набора считается, сколько его кадров — это НОВЫЙ
рисунок (`новых`), сколько из них придётся рисовать (`рисовать`), а сколько можно получить
пересчётом палитры уже нарисованного (`перекраской` = кадр, чей хэш `раскраска` уже встречался
раньше в порядке обхода наборов, `tools/pck_roadmap.py:77-86`). Это чисто плановая метрика «что
экономим», а не подтверждение реального механизма перекраски.

### 1.1. Числа по `census/frames.tsv` (36 536 строк, 33 380 из них TERRAIN)

Подсчитано скриптом (см. `tools/hdart`-стиль, файл лежал в
`C:\Users\user\AppData\Local\Temp\claude\...\scratchpad\recolor_stats.py`, читает TSV как
`csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE)`, `encoding="utf-8-sig"`):

- Групп `раскраска` с больше чем одним кадром среди TERRAIN: **6280**, суммарно **23 942** кадра.
- Из них групп, где участвуют РАЗНЫЕ наборы (не просто повтор внутри одного PCK): **6041** групп,
  **23 316** кадров.
- Из НИХ групп, где кадры реально различаются побайтово (`точный` не совпадает — то есть это не
  случай «оба набора хранят один и тот же кадр без изменений», см. R-049/дедупликация): **2076**
  групп, **11 572** кадра (TERRAIN); по всем разделам вместе — **2078** групп, **11 604** кадра.
- Крупнейшие пары наборов по числу общих групп «раскраска» (TERRAIN, кадры реально разные):

| пара наборов | общих групп |
|---|---|
| PLANE2 / PLANE2R | 111 |
| IDT_HUMAN / SIBERIABASE, IDT_HUMAN / XBASE1, IDT_HUMAN / XBASE1_NTR, SIBERIABASE / XBASE1, SIBERIABASE / XBASE1_NTR, XBASE1 / XBASE1_NTR | 79 |
| IDT_HUMAN / XBASE1_AMB, SIBERIABASE / XBASE1_AMB, XBASE1 / XBASE1_AMB, XBASE1_AMB / XBASE1_NTR | 78 |
| A_FRN / U_FRN | 73 |
| XOPSTRANSPORT2 / XOPSTRANSPORT2_RED | 61 |
| U_WALL02 / U_WALL_P | 59 |
| U_WALL_G / U_WALL_G_X, U_WALL02GOLD / U_WALL_B | 58 |
| AVENGER_BL2 / AVENGER_R | 58 |
| U_WALL02GOLD / U_WALL_P | 57 |
| U_FRN / U_FRNCHURCH | 56 |
| URBAN / URBAN_GOODS, FREIGHTER_COMMAND / FREIGHTER_TECHNICAL, U_WALL_B / U_WALL_P | 55 |
| URBAN40K / URBAN40KN1, IDT_HUMAN / STATION, SIBERIABASE / STATION, STATION / XBASE1(_AMB,_NTR) | 53 |
| C_INT / C_INT_SMALL / C_INT_XCOM / C_INT_XCOM_GOLD (попарно) | 52 |
| XOPSUFOITEMS2 / XOPSUFOITEMS2SM | 52 |

Внимание: часть этих пар (например `IDT_HUMAN`/`SIBERIABASE`/`XBASE1*`) при выборочной проверке
раскладки индексов (см. 1.2) оказалась **побайтовыми повторами (сдвиг 0)** на всех проверенных
кадрах — то есть это переиспользование одного и того же готового рисунка между несколькими
террейнами баз, а не перекраска. «Раскраска»-хэш находит и такие случаи тоже, потому что при
сдвиге 0 отпечаток `раскраска` совпадает с отпечатком `точный`. Для «крупнейших пар» в таблице
выше это НЕ проверено поштучно — таблица показывает совпадение кандидатов, не подтверждённый факт
перекраски для каждой пары.

### 1.2. Как устроена перекраска на уровне индексов: два разных механизма

Проверено чтением сырых PCK через `tools/hdart/xcom_sprites.read_pck` (тот же код, что и у
переписи) на установке Пираток `Пиратки/Dioxine_XPiratez/user/mods/Piratez/TERRAIN`, по 6–20
первым кадрам каждой пары (скрипты `check_shift.py`, `check_shift2.py`, `check_shift3.py` в
scratchpad этой сессии). Для каждой пары (набор A, набор B) бралось отображение индекс(A) →
индекс(B) по всем ненулевым пикселям кадра и проверялось: (а) согласовано ли отображение (один и
тот же исходный индекс всегда даёт один и тот же целевой на всех проверенных кадрах) и (б)
сводится ли оно к ОДНОМУ константному сдвигу.

**Тип 1 — чистый сдвиг рампы, кратный 16** (согласовано, единственный ненулевой сдвиг, всегда
кратен 16):

| пара | сдвиг (B − A) |
|---|---|
| C_EXT_ROOF → C_EXT_ROOF_PRPL | +144 (= 9×16) |
| C_EXT_ROOF → C_EXT_ROOF_BLACK | +192 (= 12×16) |
| C_EXT_ROOF → C_EXT_ROOF_GOLD | +96 (= 6×16) |
| CULTIVAT → CULTIVAT_PP | набор сдвигов {−128, −96, 0, 16, 32, 80, 128} — все кратны 16 |
| CAVEBROWN → CAVEBONE | набор сдвигов {−160, −144, −112, −80, −64, −16, 0, 16, 32, 64} — все кратны 16 |
| U_WALL02 → U_WALL02GOLD | {−208, 0} |
| U_WALL02 → U_WALL_B | {−16, 0} |
| U_WALL02 → U_WALL_P | {−48, 0} |
| U_WALL02 → U_WALL_G | {0, +16} |
| IDT_HUMAN → SIBERIABASE, IDT_HUMAN → XBASE1 | {0} — на проверенных 20 кадрах это побайтовый повтор, не перекраска |

Множественность сдвигов внутри одной пары (не один сдвиг на весь набор, а несколько, каждый
кратен 16) означает, что РАЗНЫЕ рампы кадра (разные материалы: например кровля и оклад) сдвинуты
на РАЗНУЮ величину, но каждая — ровно на целое число рамп. Это в точности конвенция палитры
UFO/OXC: 16 рамп по 16 оттенков (см. раздел 2 ниже), та же, что использует движок для перекраски
юнитов.

**Тип 2 — произвольная, но согласованная замена индекс-в-индекс** (согласовано на проверенных
кадрах, но НЕ сводится к одному или нескольким кратным-16 сдвигам; часть сдвигов дробная —
например −111, −81, −50, −31, −17, +27, +34, +45):

| пара | пример |
|---|---|
| CAVEBROWN → CAVEAQUA | 25 разных значений сдвига на 6 кадрах, большинство не кратно 16 |
| CAVEBROWN → CAVEMARS | согласовано НЕ на всех кадрах (`consistent=False`) — на части кадров один и тот же исходный индекс уходит в разные целевые в разных кадрах, то есть форма/рисунок тоже отличается, не только цвет |
| CAVEBROWN → CAVEDOOM, → CAVEMEAT | то же: `consistent=False`, много разных сдвигов |
| SGR_WALLS → SGR_WALLS_P / _B / _GOLD | `consistent=False`, сдвиги не кратны 16 |
| CULTIVAT → CULTIVAT_UBER / _VR | `consistent=False`, сдвиги не кратны 16 |

Для таких пар «раскраска» в переписи — это ДРУГОЙ рисунок с тем же силуэтом, а не пересчёт
палитры одного и того же. Присваивать им единый сдвиг было бы неверно.

**Важная оговорка про выборку.** Проверено 6–20 первых кадров набора (не все кадры целиком) —
этого достаточно, чтобы отличить «чистый сдвиг» от «произвольная замена» (для чистого сдвига
несовместимого индекса не нашлось ни разу), но НЕ достаточно, чтобы гарантировать, что ВЕСЬ набор
(включая последние кадры, часто это редкие детали/углы) держит тот же сдвиг без исключений.

### 2. Перекраска на лету в движке — для юнитов и предметов есть, для тайлов террейна нет

Классический (не-HD) механизм замены группы палитры — `newBaseColor`, идёт от
`Surface::blitNShade` (`src/Engine/Surface.cpp:1010`) через `helper::ColorReplace::func`
(`src/Engine/ShaderDraw.h:133-198`). Константы конвенции:

```
src/Engine/ShaderDraw.h:127   const Uint8 ColorGroup = 0xF0;
src/Engine/ShaderDraw.h:128   const Uint8 ColorShade = 0x0F;
```

То есть у палитры 16 «рамп» (групп) по 16 оттенков; `ColorReplace` берёт у исходного пикселя
оттенок (младший ниббл), прибавляет `shade`, и подставляет группу `newColor` — ровно тот же
принцип, что я обнаружил в данных «Типа 1» выше (сдвиг кратен 16).

Для юнитов эта же идея реализована через скрипты рулсета: `RecolorUnitParser`
(`src/Mod/ModScript.h:94`), `BattleUnit::setRecolor` / `getRecolor`
(`src/Savegame/BattleUnit.cpp:931`, `:1457`), и обработчик `getRecolorScript`
(`src/Savegame/BattleUnit.cpp:6153-6169`), который для каждого пикселя ищет в векторе пар
(группа-источник → группа-цель) совпадение по `pixel & helper::ColorGroup` и подставляет
`shade + p.second`. Источник пар — поля рулсета брони: `armors.spriteFaceColor` (407 записей),
`armors.spriteHairColor` (353), `armors.spriteUtileColor` (45) — числа взяты из
`.index/mod/Piratez/rul/fields.tsv`. Для предметов — параллельный `RecolorItemParser`
(`src/Mod/ModScript.h:185`).

**Для тайлов (MapData/Tile) такого рулсет-поля и такого скрипта НЕТ.** В `src/Mod/ModScript.h`
грепом на `Tile`/`MapData` находится только один посторонний хук —
`VisibilityUnitParser` (`:112`), про видимость юнита, не про цвет. Терраин рисуется в
`Map::drawTerrain` (`src/Battlescape/Map.cpp:1275`), и все вызовы `surface->blit(...)` для пола,
стен и объекта передают `newBaseColor = _nvColor` (например `Map.cpp:1495, 1497, 1558, 1560, 1568,
1570, 1579, 1581`). `_nvColor` — член `Map` (`Map.h:82`), инициализируется нулём при старте
(`Map.cpp:230`) и это **один скаляр на всю видимую карту** — прибор ночного видения красит ВСЮ
сцену в одну группу, а не выбирает цвет по конкретному набору/MCD-записи.

Вывод: перекраска разных «цветных» наборов террейна в X-Piratez — это выбор ДРУГОГО заранее
нарисованного PCK через `terrains.mapDataSets`, а не параметр, который движок считает на лету.
Подтверждение из переписи рулсетов: поле `terrains.mapDataSets` (249 записей,
`.index/mod/Piratez/rul/fields.tsv`) — пример `MARS`: `["BLANKS","MARS","U_WALL02"]`, то есть
террейн MARS явно ссылается на базовый `U_WALL02`, а не на `U_WALL02GOLD` — выбор цвета целиком в
руках автора рулсета.

### 3. Палитры: не одна на весь мод

Базовая («по умолчанию») боевая палитра — `PAL_BATTLESCAPE`, и в X-Piratez она переопределена
кастомной палитрой `PAL_DGOOD_NORMAL` (target `PAL_BATTLESCAPE`, файл
`Resources/Pals/delicious_regular.pal`) — это подтверждает и запись в `docs/DECISIONS.md`
(2026-09-18): «X-Piratez заменяет боевую палитру целиком (PAL_DGOOD_NORMAL → PAL_BATTLESCAPE,
delicious_regular.pal)».

Но эта базовая палитра — не единственная, которую видит игрок в бою. Два независимых механизма
подменяют RGB `PAL_BATTLESCAPE` целиком на время миссии:

**(а) Глубина.** `alienDeployments.depth` — 15 записей в рулсете Пираток (все со значением
`[1,1]`, `.index/mod/Piratez/rul/values.tsv`), например `STR_SEA_SUNKEN_TOWN`,
`STR_TLETH_BASE_ASSAULT*`. `SavedBattleGame::setPaletteByDepth` (`src/Savegame/SavedBattleGame.cpp:3059-3071`):
при `_depth == 0` — `PAL_BATTLESCAPE`, иначе — `"PAL_BATTLESCAPE_" + depth`. В рулсете это
разрешается через `customPalettes`: `PAL_BATTLESCAPE_1/_2/_3` — все три указывают на один файл
`Resources/Pals/dgoodpal_water.pal` (`.index/mod/Piratez/rul/values.tsv`).

**(б) Окружение миссии.** `enviroEffects.paletteTransformations` — 23 записи в рулсете, каждая
вида `{"PAL_BATTLESCAPE":"<кастомная>"}`:

| enviroEffect | целевая палитра | файл |
|---|---|---|
| STR_ENVIRO_ACID_RAIN, STR_ENVIRO_POISON_GAS | PAL_DGOOD_ACID | dgoodpal_grinder.pal |
| STR_ENVIRO_COLD, STR_ENVIRO_COLD_INTENSE | PAL_COLD | delicious_cold.pal |
| STR_ENVIRO_CYDONIA, STR_ENVIRO_CYDONIA_SURFACE, STR_ENVIRO_DUST_STORM, STR_ENVIRO_LABYRINTHUS_NOCTIS, STR_ENVIRO_MARS | PAL_MARS | pal_Mars.pal |
| STR_ENVIRO_GNOMES_SHADOWTRAP, STR_ENVIRO_MOON, STR_ENVIRO_PSYCHEDELIC, STR_ENVIRO_SHADOWLANDS_2, STR_ENVIRO_SHADOWLANDS_ARMORSTRIPPER, STR_ENVIRO_SPACE, STR_ENVIRO_SPACE_FREIGHTER | PAL_DGOOD_SPACE | dgoodpal_space.pal |
| STR_ENVIRO_HEAT, STR_ENVIRO_HEAT_2 | PAL_HOT | delicious_hotasfuck.pal |
| STR_ENVIRO_IRRADIATED, STR_ENVIRO_NUKEZONE | PAL_OLDEDAYS | NEW_XCF_PALLET.pal |
| STR_ENVIRO_MAGMA | PAL_MAGMA | pal_hotpursuit.pal |
| STR_ENVIRO_SEA | PAL_DGOOD_SEA | dgoodpal_water.pal |
| STR_ENVIRO_SHADOWLANDS_1 | PAL_PURPLED | dgoodpal_normal_diopurple.pal |

Террейн привязывается к такому эффекту полем `terrains.enviroEffects` (74 записи), например
`CAVES_AQUA_A → STR_ENVIRO_SEA`.

Применяется это в `BattlescapeState::BattlescapeState`
(`src/Battlescape/BattlescapeState.cpp:267-281`): для каждой пары `(change.first, change.second)`
берутся объекты `Palette` мода по именам и **`origPal->copyFrom(newPal)`** — то есть RGB-таблица
самого объекта `PAL_BATTLESCAPE` (все 256 записей) целиком заменяется на RGB из кастомного файла,
`_paletteResetNeeded = true`, дальше применяется стандартный путь `_save->setPaletteByDepth(this)`
(`:284`). Индексы у всех кадров (террейна, юнитов, предметов) остаются те же самые числа — просто
теперь они означают другой цвет.

**Что это значит для HD-кадра, нарисованного под одну палитру.** Классический 8-битный слой
следует за подменой автоматически (индекс есть индекс, цвет ищется в живом объекте `Palette`).
HD-слой держит собственные таблицы (`_lut`, `_shadeLut`, `_recolorLut`, `_toneFactor`) и
перестраивает их при каждой смене палитры: `Map::setPalette` (`src/Battlescape/Map.cpp:914-925`)
рассылает `setPalette(colors, firstcolor, ncolors)` и классической поверхности, и
`_canvas->setPalette(...)` (HD-канвас), и наборам данных карты. `Canvas32::setPalette`
(`src/Engine/HdCanvas.cpp:380-396`) на каждый вызов делает `flush()` (сброс кэша затенённых
кадров) и `rebuildTables()`, которая пересчитывает тоновые кривые по ЖИВОЙ палитре
(`Canvas32::rebuildToneTables`, `src/Engine/HdCanvas.cpp:258-378`, комментарий на `:255-256`:
«past the end of the ramp the pixel is black exactly where the palette is»).

Но САМИ пиксели HD-пака (`hd/TERRAIN/<name>.PCK/<n>.png`) — это фиксированный RGBA, записанный на
диск заранее под КОНКРЕТНУЮ палитру (судя по `docs/DECISIONS.md` — `delicious_regular.pal`, она
же дефолтная `PAL_DGOOD_NORMAL`). `doBlitHd` (`src/Engine/HdCanvas.cpp:2112-2173`) применяет к
этим пикселям только тоновую кривую яркости по тени (`_toneFactor`, комментарий на `:2107-2110`:
«the shade applied as the palette-calibrated tone curve») и, если передан `newBaseColor`,
постеризацию в ближайшую палитровую запись группы (та же логика ночного видения). Ни то, ни
другое не меняет ОТТЕНОК HD-пикселя на оттенок новой палитры (`PAL_MARS`, `PAL_DGOOD_SPACE` и
т.п.) — это только про яркость (тень 0..16) и про группу 0xF0 для одного конкретного сценария.
У картинок интерфейса (`hd/UI`) для аналогичной задачи есть механизм `<имя>.pal.txt`
(«палитра, под которую сделана картинка, для перекраски под ту, под которой она показана» —
`src/Engine/HdUiArt.h:30-35`); для `hd/TERRAIN` такого файла или механизма не нашлось — просмотр
папки `hd/TERRAIN/C_EXT_ROOF.PCK/` в установке Пираток не содержит `.pal.txt`.

### 4. Как наш HD-слой сегодня обращается с перекраской

- `newBaseColor`/`Canvas32::_recolorLut` (`src/Engine/HdCanvas.h:207,249`,
  `src/Engine/HdCanvas.cpp:1198-1231` `classicTable`) — HD-реализация ТОЙ ЖЕ группы-0xF0-замены,
  что и классика, но для террейна вызывается только с `_nvColor` (см. раздел 2/3), то есть на
  сегодня перекраска наборов через неё не идёт.
- `.pal.txt` — используется только для `hd/UI` (интерфейсные картинки, `HdUiArt.h:30-35`,
  инструменты `tools/hdart/upscale_ui.py:187`, `photo_ui.py:142,996`, `restore_pedia.py`,
  `pedia_push.py`). Для `hd/TERRAIN` ничего подобного нет.
- R-030 (`docs/RAKES.md`) — это правило ГЕНЕРАЦИИ арта юнитов, не runtime-механизм: при переносе
  классической перекраски (замена группы палитры у юнита) в HD-картинку нельзя умножать
  поканально `p * (cb+2)/(ca+2)`, потому что HD-пиксель лишь БЛИЗОК к палитровой записи `ca` (в
  среднем на 16/255 у 578 из 691 листов Пираток), и ошибка в тёмном канале даёт паразитный цвет.
  Верно — скалярный множитель по ЯРКОСТИ: `cb * (яркость_HD + 2) / (яркость_ca + 2)`. Правило
  сформулировано для `src/Engine/HdCanvas.cpp` и `tools/hdart/upscale_units.py`, то есть для
  юнитов; для наборов террейна такого инструмента я не нашёл (см. ниже).
- `tools/hdart/dupe_plan.py` группирует кадры по ХЭШУ ПИКСЕЛЕЙ уже готовой (нарисованной) HD-
  картинки (`frame_hash`, кэш `census/frame_hash.tsv`, `tools/hdart/dupe_plan.py:44-64`), то есть
  ищет побайтовые повторы среди УЖЕ НАРИСОВАННОГО, чтобы разложить один результат на несколько
  мест (R-049). Про `раскраска`/`recolor`-хэш переписи или про перекраску по индексу в этом файле
  нет ни строки (проверено грепом — совпадений нет).
- `tools/hdart/mirror_frames.py` — то же самое, но для отражения по силуэту, с восстановлением
  «своего» света поворотом и переносом яркости (R-054, `docs/RAKES.md`). Тоже не про перекраску
  наборов.
- Chroma lock (`docs/DECISIONS.md`, 2026-09-18, «цвет мода задаёт оригинал, яркость — художник») —
  функция `chroma_lock` в `tools/hdart/build_pack.py:97-142` (используется на `:418-435`).
  Работает в CIELAB: цветность (a/b) берётся от РАЗМЫТОГО ОРИГИНАЛА (низкочастотная), яркость — от
  того, что нарисовала модель/художник. Это инструмент генерации ОДНОГО кадра против ЕГО
  СОБСТВЕННОГО классического источника — он не переносит цвет между наборами и не знает о
  «раскраска»-группах переписи.

Итог раздела: сегодня в тулинге НЕТ пути «нарисовать один набор и получить остальные наборы той
же цветовой семьи пересчётом» — ни на уровне движка (только `_nvColor` для тайлов), ни на уровне
скриптов генерации арта (`dupe_plan`/`mirror_frames` ищут точные и зеркальные повторы, не
перекраски; `chroma_lock` работает внутри одного кадра).

## Проверено в коде

- `tools/pck_census.py:218-237` — четыре отпечатка кадра (`exact`/`shape`/`recolor`/`mirror`) и
  прямая оговорка, что `раскраска` — кандидат, не доказательство.
- `tools/pck_census.py:1-20` — назначение переписи (три вопроса: сколько разного, что чаще видно,
  что рисовать первым).
- `tools/pck_roadmap.py:56-101` — как считается колонка `перекраской` (кадр, чей хэш `раскраска`
  уже встречался раньше в порядке обхода наборов по охвату клеток).
- `census/frames.tsv` (36 536 строк) и `census/roadmap.tsv`/`roadmap.md` — исходные числа.
- `src/Engine/ShaderDraw.h:127-198` — `ColorGroup = 0xF0`, `ColorShade = 0x0F`,
  `helper::ColorReplace::func` — классический механизм замены группы палитры.
- `src/Mod/ModScript.h:94,185` — `RecolorUnitParser`, `RecolorItemParser` (юниты и предметы,
  тайлов нет).
- `src/Savegame/BattleUnit.cpp:931,1457,6153-6169` — `setRecolor`/`getRecolor`/`getRecolorScript`.
- `.index/mod/Piratez/rul/fields.tsv` — `armors.spriteFaceColor` (407), `spriteHairColor` (353),
  `spriteUtileColor` (45), `terrains.mapDataSets` (249, пример MARS),
  `terrains.enviroEffects` (74, пример CAVES_AQUA_A → STR_ENVIRO_SEA).
- `src/Battlescape/Map.cpp:230,1275,1495-1901` — `_nvColor` как единственный `newBaseColor` для
  рисования тайлов, инициализация нулём, использование во всех вызовах `blit` внутри
  `drawTerrain`.
- `src/Battlescape/Map.h:82` — объявление `_nvColor`.
- `src/Savegame/SavedBattleGame.cpp:3059-3071` — `setPaletteByDepth`.
- `.index/mod/Piratez/rul/values.tsv` — `alienDeployments.depth` (15 записей, все `[1,1]`),
  `enviroEffects.paletteTransformations` (23 записи, таблица целей выше),
  `customPalettes.target`/`customPalettes.file` (16 записей, включая `PAL_BATTLESCAPE_1/_2/_3` →
  `dgoodpal_water.pal`, `PAL_DGOOD_NORMAL` → `PAL_BATTLESCAPE`/`delicious_regular.pal`).
- `src/Battlescape/BattlescapeState.cpp:267-284` — применение `paletteTransformations`
  (`origPal->copyFrom(newPal)`) и вызов `setPaletteByDepth`.
- `src/Battlescape/Map.cpp:914-929` — `Map::setPalette` рассылает смену палитры канвасу и наборам
  данных карты.
- `src/Engine/HdCanvas.cpp:380-396` — `Canvas32::setPalette` (`flush()` + `rebuildTables()`).
- `src/Engine/HdCanvas.cpp:258-378` — `Canvas32::rebuildToneTables` (тоновая кривая по живой
  палитре, только яркость).
- `src/Engine/HdCanvas.cpp:1198-1231` — `Canvas32::classicTable` (`_shadeLut`/`_recolorLut` по
  `newBaseColor`).
- `src/Engine/HdCanvas.cpp:2107-2173` — `Canvas32::doBlitHd` (тон + посеризация группы, без
  смены оттенка под другую палитру).
- `src/Engine/HdCanvas.h:207,242-253` — члены `Cmd::newBaseColor`, `_recolorLut`, `_toneFactor`,
  `_level`.
- `src/Engine/HdUiArt.h:30-35` — `.pal.txt` документирован только для `hd/UI`.
- `src/Engine/HdSprites.h:29-74` — реестр HD-кадров для террейна/юнитов: путь `hd/<набор>/<кадр>.png`
  или `hd/<набор>/pack.hdp`, про `.pal.txt` не упомянуто.
- Пробный просмотр каталога `Пиратки/Dioxine_XPiratez/user/mods/hd/hd/TERRAIN/C_EXT_ROOF.PCK/` —
  только `<N>.png`, ни одного `.pal.txt`.
- `tools/hdart/dupe_plan.py` — грепом по «раскраск»/«recolor» пусто; группировка идёт по
  `frame_hash` пикселей готового HD-кадра (`:44-64`).
- `docs/DECISIONS.md`, запись 2026-09-18 «цвет мода задаёт оригинал, яркость — художник» —
  контекст про `PAL_DGOOD_NORMAL → PAL_BATTLESCAPE, delicious_regular.pal` и `chroma_lock`.
- `tools/hdart/build_pack.py:71-142,418-435` — реализация `chroma_lock` (CIELAB, цветность от
  размытого оригинала, вызывается на кадр против его собственного классического источника).
- `docs/RAKES.md`, R-030 — правило переноса перекраски по яркости для HD-кадров юнитов, с точными
  числами ошибки (в среднем 16/255 у 578 из 691 листов).
- Прямая проверка сдвига индексов чтением сырых PCK (`tools/hdart/xcom_sprites.read_pck`) на
  `Пиратки/Dioxine_XPiratez/user/mods/Piratez/TERRAIN` — см. таблицы раздела 1.2 (скрипты
  `check_shift.py`, `check_shift2.py`, `check_shift3.py`, временные файлы этой сессии).

## Источники

Внешних источников не использовано — весь материал получен грепом и чтением исходников движка,
рулсетов X-Piratez и переписи `census/`, как и требовала задача. Веб не открывался.

## Чего НЕ выяснил

- Не проверил сдвиг индексов на ВСЕХ кадрах каждого набора (только первые 6–20) — для «чистых»
  пар (тип 1) не встретил ни одного нарушения на выборке, но не исключаю редкий кадр-исключение
  дальше по списку (например, последние, «угловые» кадры набора часто самые нетиповые).
- Не проверил глазами, отличается ли МАТЕРИАЛ между наборами тип-1 (например
  `C_EXT_ROOF`/`_GOLD`/`_SILVER`/`_BLACK` — это один и тот же рисунок кровли, перекрашенный, или
  разные материалы, которые случайно дают чистый сдвиг индекса просто потому, что палитра мода
  так устроена). Перепись и проверка сдвига видят только индексы 32×40, не сюжет рисунка.
- Не подтвердил дампом игры (Ctrl+F8) эффект `paletteTransformations` на HD-слой: вывод «HD-пак
  останется в исходном оттенке, пока классика перекрасится» сделан по чтению
  `doBlitHd`/`rebuildToneTables`/`HdUiArt.h`, а не по сравнению живых кадров под, например,
  `STR_ENVIRO_MARS`. Задача прямо запрещала запускать игру — это стоит проверить отдельно, когда
  можно.
- Не нашёл счётчика, сколько именно РЕАЛЬНЫХ (карт, а не деплойментов) миссий в кампании Пираток
  фактически используют каждый `enviroEffect` — только то, что 74 записи `terrains.enviroEffects`
  ссылаются на один из 23 `paletteTransformations`.
- Не проверял, существует ли в апстримном OXCE (вне нашего HD-слоя) какой-то скрытый механизм
  перекраски MapData через ModScript, который мог не попасть под мои grep-паттерны (`Tile`,
  `MapData`, `recolor`, `newBaseColor`) — судя по `src/Mod/ModScript.h`, единственный
  тайл-связанный скрипт (`VisibilityUnitParser`) про цвет не говорит, но полного списка всех
  `*Parser` структур файла я не вывел построчно.
- Не оценивал производительность или память возможной схемы «рисовать один, красить остальные» —
  вопрос был про факты формата, не про архитектуру.
