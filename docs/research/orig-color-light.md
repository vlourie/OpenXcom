# Оригинальный (классический, 8-битный) цвет и свет боя

Дата: 2026-09-28 | Уверенность: высокая (код), средняя — там, где помечено отдельно

## Краткий ответ

Классический движок красит спрайт боя ОДНИМ целым числом shade 0..16 на клетку (иногда с
поправкой для двери), применяя его ко всей клетке (пол, обе стены, объект, юнита, предмет)
разом — направленного света и падающих теней от объектов нет. Shade = 15 минус максимум яркости
по 4 слоям света (солнце/окружение, огонь+лампы, светящиеся предметы, юниты), яркость от
источника гаснет линейно с расстоянием по вокселям, блокируется стенами/полом/крышей. Индекс
цвета темнеет внутри своей 16-цветной группы палитры (`idx & 0xF0` группа, `idx & 0x0F` shade);
при переполнении группы результат — жёстко индекс 15 (чёрный). Неразведанная клетка красится
shade=16, что всегда даёт чёрный. Палитра боя (`PAL_BATTLESCAPE`, 256 цветов, «UFO 6-бит → 8-бит
×4») может быть ПОДМЕНЕНА ЦЕЛИКОМ модом на миссию/среду (enviroEffects.paletteTransformations —
например, Пиратки на Марсе/во льду/в кислоте), а не просто «сдвинута». Настоящая полупрозрачность
(alpha-блендинг) есть только в отдельном OXCE-механизме vapor/transparencyLUT (не для обычных
спрайтов пола/стен/юнитов), дым и огонь — это ОБЫЧНЫЕ непрозрачные спрайты SMOKE.PCK разной
«густоты», а не альфа-канал. Наш HD-слой добавляет то, чего в оригинале НЕТ: интерполяцию shade
и цветовую температуру света между соседними клетками (`HdLight`, 9 узлов) и «плавный» тон HD-арта
по кривой яркости палитры (`tonedFor`) — при k=1/nearest этот путь должен точно воспроизводить
классику побайтно (`_shadeLut`, построен по той же формуле).

## Детали

### 1. Палитра боя

- Формат хранения на диске: X-Com 6-битный VGA RGB (0-63 на канал), 3 байта на цвет подряд.
  Загрузка — `Palette::loadDat` (`src/Engine/Palette.cpp:52-75`): каждый канал `× 4` даёт 0-255,
  индекс 0 помечен прозрачным (`unused=0`), 256 цветов.
- `PAL_BATTLESCAPE` — это палитра №4 (с нуля) из `GEODATA/PALETTES.DAT`, смещение
  `Palette::palOffset(4)` (`src/Mod/Mod.cpp:6059-6064`, `Palette::palOffset` = `palette*(768+6)`,
  `src/Engine/Palette.h:67`). После загрузки движок ПРИНУДИТЕЛЬНО переписывает последние 16
  цветов (индексы 240-255, `Palette::backPos`=224, `+16`) серым градиентом от (140,152,148) до
  (3,3,6) — «Correct Battlescape palette» (`src/Mod/Mod.cpp:6066-6087`). Это отдельная группа
  0xF0 (15-я), не связана с формулой затемнения shade (см. ниже).
- Для подводных миссий (TFTD depth 1-3) есть отдельные целые палитры `PAL_BATTLESCAPE_1/2/3`,
  выбор по `_depth` в `SavedBattleGame::setPaletteByDepth` (`src/Savegame/SavedBattleGame.cpp:3059-3071`).
- **Подмена палитры по миссии/среде**: `RuleEnviroEffects.paletteTransformations` — карта
  `{"PAL_BATTLESCAPE": "PAL_ДРУГАЯ"}` из рулсета. Применяется при входе в
  `BattlescapeState`: `origPal->copyFrom(newPal)` (`src/Battlescape/BattlescapeState.cpp:267-281`) —
  то есть содержимое `PAL_BATTLESCAPE` физически перезаписывается другой палитрой ЦЕЛИКОМ (не
  плавный переход, не тонирование одного канала). Индексы 0-255 остаются теми же номерами,
  меняются лишь их RGB. У X-Piratez это активно используется (перепись
  `.index/mod/Piratez/rul/values.tsv`, раздел `enviroEffects.*.paletteTransformations`):
  `PAL_MARS`, `PAL_HOT`, `PAL_COLD`, `PAL_MAGMA`, `PAL_DGOOD_ACID`, `PAL_DGOOD_SEA`,
  `PAL_DGOOD_SPACE`, `PAL_OLDEDAYS`, `PAL_PURPLED` — по конкретному enviroEffect (кислотный
  дождь, холод, Сидония, ядовитый газ, космос, радиация и т.д.).
- Глобальная тёмность/светлость миссии (`globalShade`, 0-15) в палитру не входит вообще — это
  отдельное число на `SavedBattleGame`, см. п.3.

### 2. Формула затемнения (shade) индекса цвета

Индекс палитры — байт: старший полубайт `0xF0` — номер цветовой группы (0-15, «рампа»), младший
`0x0F` — позиция внутри группы (0 = самый светлый цвет рампы, 15 = самый тёмный). Формула в
`helper::StandardShade::func` (`src/Engine/ShaderDraw.h:176-213`, используется
`Surface::blitNShade`, `src/Engine/Surface.cpp:1010-1031` — это и есть путь рисования тайлов боя):

```
newShade = src + shade                       // байт целиком, group+index вместе
if ((newShade ^ src) & 0xF0)                 // изменился ли старший полубайт (группа)
    dest = 0x0F                              // "так темно, что цвет бы сменил группу — сделать чёрным"
else
    dest = newShade
```

Практически: `shade` — целое число 0..16 (иногда до 16 включительно, см. п.3), прибавляется к
байту индекса; если прибавление переносит бит в группу (`0xF0`), результат жёстко фиксируется в
`0x0F` — абсолютный индекс палитры 15 (внутри группы 0), который в классических палитрах X-Com
традиционно чёрный. Это НЕ обязательно «группа 15» палитры (0xF0-0xFF, тот самый переписанный
серый градиент из п.1) — это именно индекс 15 в НУЛЕВОЙ группе. Символьная константа `ColorGroup
= 0xF0`, `ColorShade = 0x0F` (`src/Engine/ShaderDraw.h:127-128`).

Второй вариант, `helper::ColorReplace::func` (`src/Engine/ShaderDraw.h:130-171`) делает то же
самое, но ещё подменяет саму группу цвета (`newBaseColor`) — используется, когда нужно
перекрасить юнита в другую группу (напр. броня разных цветов), см. `Surface::blitNShade` с
параметром `newBaseColor` (там же строки 987-996).

Диапазон shade в вызовах рисования — 0..16: 16 передаётся явно для неразведанных клеток
(`Map.cpp:1477-1478`, см. ниже) и гарантированно уводит в чёрный, потому что `idx + 16` переносит
бит группы для ЛЮБОГО `idx` кроме уже нулевого индекса (0 всё равно прозрачен и не рисуется:
проверка `if (src)` перед формулой).

### 3. Откуда берётся shade клетки

**Итог на клетке** — `Tile::getShade()` (`src/Savegame/Tile.cpp:514-525`):

```
shade = max(0, 15 - max(_light[LL_AMBIENT], _light[LL_FIRE], _light[LL_ITEMS], _light[LL_UNITS]))
```

Четыре слоя света, `enum LightLayers { LL_AMBIENT, LL_FIRE, LL_ITEMS, LL_UNITS, LL_MAX }`
(`src/Savegame/Tile.h:38`, свет хранится `Uint8 _light[LL_MAX]`, строка 122). Слой = самый яркий
источник побеждает («add light только если новое больше», `Tile::addLight`,
`src/Savegame/Tile.cpp:479-483`), яркость 0-15 (0 темнота, 15 максимум), поэтому shade = 15 -
яркость: 0 = полностью светло, 15 = темно (в пределах палитровой группы), 16 = зарезервировано
как «полностью чёрное» (неразведанное).

Расчёт слоёв — `TileEngine::calculateLighting` (`src/Battlescape/TileEngine.cpp:1129-1237`),
вызывается на изменение террейна/событие (взрыв, начало хода и т.п.):

| Слой | Функция | Источники | Макс. дальность |
|---|---|---|---|
| `LL_AMBIENT` | `calculateSunShading` (`TileEngine.cpp:937-967`) | `15 - globalShade` минус 2, если клетка под крышей/выше есть непроходимый пол/объект СВЕРХУ, и только когда `globalShade ≤ 4` (днём/в сумерках; ночью солнце и так не светит, вычитать нечего) | вся карта |
| `LL_FIRE` | `calculateTerrainBackground` (`TileEngine.cpp:981-1021`) | статичные источники: MCD-поле `Light_Source` пола/стен/объекта (лампы и т.п., `MapDataSet.cpp:158`), плюс огонь на клетке (сила 15, `fireLightPower`/`unitFireLightPower`) | `getMaxStaticLightDistance()`, по умолчанию 16 (`Mod.cpp:435`), ruleset ключ `globals.lighting.maxStatic` (`Mod.cpp:4146`) |
| `LL_ITEMS` | `calculateTerrainItems` (`TileEngine.cpp:1026-…`) | предметы на земле со свечением (`RuleItem` `glow`/`glowRange`) | `getMaxDynamicLightDistance()`, по умолчанию 24 (`Mod.cpp:435`), ключ `globals.lighting.maxDynamic` |
| `LL_UNITS` | `calculateUnitLighting` (`TileEngine.cpp:1062-1127`) | личный свет юнита (`Armor.personalLight`/`personalLightHostile`/`personalLightNeutral`, дефолты в коде 15/0/0, `Armor.h:170-172`; у игрока ещё зависит от переключателя `L` — `keyBattlePersonalLighting`, `Options.cpp:338`), свечение оружия в руках (`glow`/`glowRange`), горящий юнит (15, оглушённый горящий — 10) | `getMaxDynamicLightDistance()` |

Распространение света — `TileEngine::addLight` (`TileEngine.cpp:1245-…`): яркость убывает линейно
с воксельным расстоянием от источника (`power - distance`, округление по `Position::distance`),
дальше либо «классический» режим (свет просто ставится по прямой видимости клеток, без учёта
поэтажной геометрии — `clasicLighting` истинно, когда в ruleset `globals.lighting.enhanced` не
включает соответствующий бит), либо «улучшенный» режим OXCE (`enhanced` бит 1/2/4 для fire/items/
units) с трассировкой по вокселям через `_blockVisibility` (блокировка стенами/полом/дымом,
дым съедает 1 свет за шаг, разница высоты блокирует). `getEnhancedLighting()` — ruleset-флаг,
у Пираток в `values.tsv` по разделу `globals`/`lighting` не встречен явно в нашей выборке —
см. «Чего не выяснил».

**День/ночь и глубина миссии** — `globalShade` (0..15) на `SavedBattleGame`
(`SavedBattleGame.h:97`, `getGlobalShade`/`setGlobalShade`, `SavedBattleGame.cpp:791-802`).
Источник — `BattlescapeGenerator::_worldShade`:
- по умолчанию берётся из реального положения солнца на глобусе в точке высадки:
  `Globe::getPolygonTextureAndShade` (`src/Geoscape/Globe.cpp:2171-2182`) считает тень через
  `CreateShadow::getShadowValue` и таблицей `worldshades[32]` переводит геоскейпные 0-31 уровня
  тени в боевые 0-15 (`{0,0,0,0,1,1,2,2,3,3,4,4,5,5,6,6,7,7,8,8,9,9,10,11,11,12,12,13,13,14,15,15}`);
  вызывается в `GeoscapeState.cpp` при посадке/тревоге (строки 1373-1435, 3522-3580) и передаётся
  в генератор через `BattlescapeGenerator::setWorldShade` (`BattlescapeGenerator.cpp:165-170`,
  клампится 0..15);
- либо жёстко задаётся депло­йментом миссии: `AlienDeployment` поля `shade`/`minShade`/`maxShade`
  (`AlienDeployment.cpp:344`, `getShade`), применяются в `BattlescapeGenerator.cpp:546` (базовый
  сценарий) и `:817-828` (обычная миссия — если `shade != -1`, использовать её, иначе клампить
  между `minShade`/`maxShade`). Перепись `values.tsv` показывает у X-Piratez десятки записей
  `alienDeployments.*.shade` (1..15) и `minShade`/`maxShade` (напр. подводные миссии
  `minShade=12` — всегда тёмные).
- Не связано с глубиной палитры (`_depth`, TFTD) напрямую — глубина влияет только на выбор
  `PAL_BATTLESCAPE_N`, а не на `globalShade`.

**Влияние этажа (z) и крыши**: см. таблицу `LL_AMBIENT` выше — единственная явная поправка на
крышу: -2 к солнечному свету, если СУММА блокировки пола/объекта НАД клеткой по всем уровням
выше больше 0, и только пока `globalShade ≤ 4`. Это булево «есть крыша/нет», а не постепенное
затухание с числом этажей сверху.

**Неразведанные клетки** — если `!tile->isDiscovered(O_FLOOR)`, движок не вызывает `getShade()`
вовсе, а жёстко ставит `tileShade = obstacleShade = 16` (`src/Battlescape/Map.cpp:1475-1483`);
как показано в п.2, shade=16 всегда даёт чёрный индекс 15 — отсюда «чёрные» неразведанные клетки
на экране. Стены неразведанной клетки — та же логика в `Map::getWallShade`
(`src/Battlescape/Map.cpp:947-973`: `shade=16`, если `!tileFrot->isDiscovered(O_FLOOR)`).

**Дым**: занижает свет при распространении (только в «улучшенном» режиме — `light -= 1` за шаг
через задымлённую клетку, `TileEngine.cpp:1347-1350`), но САМ дым как спрайт рисуется обычным
непрозрачным блитом `SMOKE.PCK` с тем же `tileShade`, что и остальная клетка (кроме огня — тому
даётся `shade=0`, горит «своим светом» независимо от темноты клетки, `Map.cpp:1830`). Выбор
кадра дыма по плотности (`tile->getSmoke()`) — `Map.cpp:1804-1841`, разные кадры анимации ИМИТИРУЮТ
разную густоту (больше непрозрачных пикселей в кадре), это не альфа-канал.

**Огонь**: рисуется с `shade=0` (не темнеет от тёмной клетки) и одновременно ЯВЛЯЕТСЯ источником
света (`LL_FIRE`=15, `unitFireLightPower`=15 для горящего юнита, `TileEngine.cpp:970-976`).

### 4. Направленный свет и падающие тени от объектов

Не найдено. Единственная «направленность» в классическом рендере — вертикальная (не
горизонтальная): shade юнита интерполируется между освещённостью его тайла и тайла НАД/ПОД ним
в зависимости от вертикального смещения внутри клетки (`terrainLevel`, шаг ходьбы) —
`Map::drawUnit`, лямбды `getTileShade`/`getMixedTileShade` (`src/Battlescape/Map.cpp:1220-1262`);
во время шага юнит ещё интерполирует shade между стартовой и целевой клеткой по фазе анимации
(`Interpolate(startShade, endShade, offsets.NormalizedMovePhase, 16)`, там же строка 1253).
Падающих теней от стен/предметов на пол/соседей нет — вся клетка (пол, обе стены, объект,
предмет, юнит) красится ОДНИМ shade этой клетки (см. п.5 — единственное исключение это двери).
Между соседними клетками нет никакого сглаживания/интерполяции в классике — соседние клетки с
разным shade стыкуются резкой ступенькой (это и есть визуальный эффект классического X-Com).

### 5. Одна ли тень на клетку — все части

Да, в норме одна: `tileShade = reShade(tile)` считается один раз на клетку
(`Map.cpp:1461`) и используется для пола, объекта-на-заднем-плане, предмета на земле, дыма.
**Единственное исключение** — стены: `Map::getWallShade` (`Map.cpp:947-973`) для СЕВЕРНОЙ/ЗАПАДНОЙ
стены, которая одновременно является дверью (`isDoor`/`isUfoDoor`) и уже разведана, БЕРЁТ ТЕНЬ У
СОСЕДНЕЙ клетки ЗА дверью: `shade = min(reShade(thisTile), getShade(neighbourBehindDoor) + 5)` —
то есть открытая/закрывающаяся дверь может показать что дальняя сторона темнее (свет из освещённой
комнаты «протекает» через дверной проём на 5 shade хуже, если по ту сторону темнее). Обычные
(не дверные) стены равны shade своей клетки.

Второй частный случай — «obstacle»-подсветка (опция показа препятствий `showObstacles`):
`obstacleShade = getShadePulseForFrame(tileShade, _animFrame)` — пульсирующая (по кадрам анимации)
модификация ТОЙ ЖЕ базовой тени клетки для клеток-препятствий, не имеет отношения к направленности
света (`Map.cpp:1007`, `1461-1469`).

Параметр `half` в `blitNShade`/`Surface::blit` (`Surface.cpp:980-996`) — НЕ полупрозрачность, а
геометрическое обрезание: рисуется только правая половина исходного спрайта (`g.beg_x =
g.end_x/2`). Используется при рисовании северной стены поверх уже нарисованной западной, чтобы не
задваивать общий угловой столбец пикселей (`Map.cpp:1568,1570`: `half = bool(tile->getSprite(O_WESTWALL))`).

### 6. Полупрозрачность и OXCE-опции освещения

- Настоящая полупрозрачность (альфа-блендинг по значению, не по группе палитры) в классическом
  8-битном рендере ОТСУТСТВУЕТ для обычных спрайтов — палитра принципиально индексная, смешение
  цветов невозможно без явной таблицы соответствия.
- OXCE добавляет механизм «прозрачностей» (`RuleInterface`/глобальный `transparencies` ruleset —
  не найден точный YAML-ключ в этой сессии, см. «Чего не выяснил»): `_transparencies` в `Mod`
  (`src/Mod/Mod.h:345`, заполняется `Mod.cpp:3166-3224`) — набор «тинт + непрозрачность» пар,
  из которых строится ПРЕДВАРИТЕЛЬНО ПОСЧИТАННАЯ таблица «ближайший цвет палитры»
  (`Mod::createTransparencyLUT`, `Mod.cpp:7043-7087`: для каждого тона и уровня непрозрачности
  ищется индекс палитры с минимальной евклидовой разницей RGB — честный alpha-blend невозможен,
  поэтому результат аппроксimируется существующим цветом палитры). Используется ТОЛЬКО системой
  «vapor»-частиц (пар/газ от оружия и эффектов) — `Map::addVaporParticle`/`drawVaporParticles`
  (`Map.cpp:848-888`, `3061-…`), не применяется к обычным спрайтам пола/стен/юнитов.
- Опции игрока, влияющие на освещение экрана боя: `keyBattlePersonalLighting` (клавиша `L`,
  вкл/выкл личный свет игрока, `Options.cpp:338`), `oxceTogglePersonalLightType` (per-battle/
  per-campaign, `Options.cpp:420`), `oxceAutoNightVisionThreshold` (авто-включение «ночного
  видения» интерфейса при `globalShade` выше порога, `BattlescapeState.cpp:629`), режим отладки
  видимости (`_debugVisionMode`, тестовые пресеты «Reaver» — shade/2, и «Meridian» — всегда 0,
  `Map.cpp:2580-2592`), «гибридное ночное видение» (`_nvColor`, светлее в радиусе от игрока или
  глобально до `NIGHT_VISION_MAX_SHADE`=8, порог включения `NIGHT_VISION_SHADE`=4, `Map.h:70-71`,
  `Map.cpp:2594-2620`).
- Ruleset-опции освещения (не игровые, модные): `globals.lighting.maxStatic`/`maxDynamic`/
  `enhanced` (`Mod.cpp:4146-4148`, дефолты 16/24/0, `Mod.cpp:435`).

## Проверено в коде

- `src/Engine/Palette.cpp:52-75` — `Palette::loadDat`, 6-бит → 8-бит `×4`, индекс 0 прозрачный
- `src/Engine/Palette.h:67,77` — `palOffset`, `backPos=224`
- `src/Mod/Mod.cpp:6044-6089` — загрузка палитр боя, переписывание последних 16 цветов
  `PAL_BATTLESCAPE` серым градиентом
- `src/Mod/Mod.cpp:6403-6423,6778-6792` — `PAL_BATTLESCAPE_1/2/3` (глубина), сборка LUT
  прозрачностей для каждой из них
- `src/Battlescape/BattlescapeState.cpp:267-284` — подмена `PAL_BATTLESCAPE` через
  `enviroEffects.paletteTransformations`, `origPal->copyFrom(newPal)`
- `src/Mod/RuleEnviroEffects.h:50,69` — `_paletteTransformations`, `getPaletteTransformations`
- `.index/mod/Piratez/rul/values.tsv` (раздел `enviroEffects`) — 18 записей
  `paletteTransformations` у Пираток (Mars/Hot/Cold/Magma/Acid/Sea/Space/OldEdays/Purpled)
- `src/Engine/ShaderDraw.h:127-128,176-213` — `ColorGroup=0xF0`, `ColorShade=0x0F`,
  `helper::StandardShade::func`
- `src/Engine/Surface.cpp:980-1031` — `Surface::blitNShade` (обе перегрузки), `half`
- `src/Savegame/Tile.cpp:457-525` — `addLight`/`resetLight`/`resetLightMulti`/`getShade`
- `src/Savegame/Tile.h:38,122` — `LightLayers`, `_light[LL_MAX]`
- `src/Battlescape/TileEngine.cpp:900-901,937-1237,1245-…` — конструктор с дефолтами,
  `calculateSunShading`, `calculateTerrainBackground`, `calculateTerrainItems`,
  `calculateUnitLighting`, `calculateLighting`, `addLight`
- `src/Mod/Mod.cpp:435,4146-4148` — дефолты и ruleset-ключи `maxStatic`/`maxDynamic`/`enhanced`
- `src/Mod/MapDataSet.cpp:158` — MCD-поле `Light_Source`
- `src/Mod/Armor.h:170-172`, `src/Mod/Armor.cpp:177-179` — `personalLight*`, дефолты 15/0/0
- `src/Geoscape/Globe.cpp:2171-2182` — `getPolygonTextureAndShade`, таблица `worldshades[32]`
- `src/Geoscape/GeoscapeState.cpp:1373-1435,3522-3580` — вызовы при посадке/базе, передача в
  `ConfirmLandingState`/`BattlescapeGenerator`
- `src/Battlescape/BattlescapeGenerator.cpp:165-170,546,761,805-828,952` — `setWorldShade`,
  дефолт из депло­ймента, клампы `minShade`/`maxShade`
- `src/Mod/AlienDeployment.cpp:344` — `getShade`
- `.index/mod/Piratez/rul/values.tsv` (раздел `alienDeployments`) — конкретные `shade`/
  `minShade`/`maxShade` по миссиям Пираток
- `src/Savegame/SavedBattleGame.h:97,217,219`, `.cpp:791-802` — `_globalShade`,
  `setGlobalShade`/`getGlobalShade`
- `src/Savegame/SavedBattleGame.cpp:3059-3071` — `setPaletteByDepth`
- `src/Battlescape/Map.cpp:947-973` — `Map::getWallShade` (двери, «протечка» света)
- `src/Battlescape/Map.cpp:1440-1901` — основной цикл рисования клетки: пол/стены/объекты/
  предметы/дым, `tileShade`/`obstacleShade`/`wallShade`
- `src/Battlescape/Map.cpp:1007` — `getShadePulseForFrame`
- `src/Battlescape/Map.cpp:1027-1267` — `Map::drawUnit`, интерполяция тени по вертикали и по
  фазе ходьбы
- `src/Battlescape/Map.cpp:2580-2620` — `Map::reShade`, `_debugVisionMode`, гибридное ночное
  видение, `NIGHT_VISION_SHADE=4`/`NIGHT_VISION_MAX_SHADE=8` (`Map.h:70-71`)
- `src/Engine/Options.cpp:338,420` — `keyBattlePersonalLighting`, `oxceTogglePersonalLightType`
- `src/Battlescape/BattlescapeState.cpp:629` — `oxceAutoNightVisionThreshold`
- `src/Mod/Mod.h:345`, `src/Mod/Mod.cpp:3166-3224,7043-7087` — `_transparencies`,
  `createTransparencyLUT` (ближайший цвет палитры, не честный alpha-blend)
- `src/Battlescape/Map.cpp:848-888,3061-3079` — система vapor-частиц, единственный
  потребитель `_transparencies`/LUT
- `src/Battlescape/Map.cpp:1804-1841` — выбор кадра `SMOKE.PCK` по плотности дыма, `shade=0`
  для огня
- `src/Engine/HdCanvas.h:42-56,58-110` — `HdLight` (9 узлов, `shade[]`, `tint[]`, `flat`),
  интерфейс `HdCanvas`
- `src/Battlescape/Map.cpp:582-598,600-641,650-735` — `hdShadeOf`, `hdTintOf` (цвет по слоям
  света: тёплый огонь, холодная ночь), `updateHdLight` (усреднение по 9 узлам диамонда клетки)
- `src/Engine/HdCanvas.cpp:207-230` — `Canvas32::rebuildTables`, `_shadeLut[shade][idx]`
  строится ПО ТОЙ ЖЕ формуле, что `StandardShade::func` (побайтная идентичность при k=1/nearest)
- `src/Engine/HdCanvas.cpp:1160-1231` — `doBlit`/`classicTable`, применение `_shadeLut`
- `src/Engine/HdCanvas.cpp:1779-1854` — `Canvas32::tonedFor`: тонирование HD-кадра по кривой
  яркости палитры (`_toneFactor`) плюс умножение на цвет света (`tintKey`, 5 бит на канал),
  кэш с LRU и учётом байтов
- `src/Engine/HdCanvas.cpp:330-374` — построение `_toneFactor` из фактических рамп палитры мода

## Источники
Веб не привлекался — все факты из исходников репозитория и рулсетов установки Пираток.

## Чего НЕ выяснил

- Точный ruleset YAML-ключ, которым мод объявляет `_transparencies` (Mod.cpp:3166-3224 читает
  их из какого-то `reader`, но какая именно секция YAML и как называется тинт/уровень —
  не прочитано, нужен отдельный проход по `Mod::loadFile`/`ModScript` в районе строки 3100-3230).
- Есть ли у X-Piratez явный `globals.lighting.enhanced`/`maxStatic`/`maxDynamic` в рулсетах —
  не встретилось в выборке `values.tsv` по ключевым словам «lighting/Static/Dynamic»; либо не
  задаётся (тогда действуют дефолты 16/24/0 из кода), либо лежит под другим полем-именем,
  которое не искалось прицельно (например `startingConditions` может переопределять свет — не
  проверено).
- Реальные RGB-значения самих ramp/групп `PAL_BATTLESCAPE` (и подменяющих `PAL_MARS`, `PAL_HOT`
  и т.д.) не читались — известна только структура (256 цветов, группы по 16), не какая группа
  «земля», какая «металл»: это должно смотреться по конкретным `.rmp`/`.dat` файлам ресурсов,
  вне области этого исследования по коду.
- Точная формула `getShadowValue` (класс `CreateShadow`, откуда берётся тень 0..31 на глобусе) —
  не открывалась; только то, что в неё идёт `Cord` и `getSunDirection(lon,lat)`.
- Не проверено, применяется ли `paletteTransformations` СРАЗУ при заходе в `BattlescapeState`
  для КАЖДОГО боя или только один раз/лениво повторно между разными сохранёнными играми
  (потенциальный риск «старая палитра осталась в памяти» — не исследовалось, вне задачи).
- Не смотрел, где именно `Interpolate(...,16)` определена (какая нормализация по умолчанию у
  этого хелпера) — использована как чёрный ящик, судя по вызову шкала до 16 соответствует
  диапазону shade.
