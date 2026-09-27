# Рулсет X-Piratez: разбор по содержимому

Дата: 2026-09-26. Мод: X-Piratez v.o1.1.1 из установки `Пиратки/Dioxine_XPiratez` (только чтение,
в данных мода ничего не менялось). Инструмент: `tools/rul_map.py`, тест `tools/test_rul_map.py`.

## Что сделано и где лежит

`tools/rul_map.py` грузит все 49 рулсетов (32 файла мастер-мода `standard/xcom1` и 17 файлов
мода) в порядке движка и сливает записи так же, как `Mod::loadRule`. Результат - в
`.index/mod/Piratez/rul/` (в гит не идёт, пересобирается за 11 секунд):

| Файл | Что в нём | Строк |
|---|---|---|
| `RUL.md` | сводка: порядок загрузки, разделы, находки, дерево исследований, схема ссылок | - |
| `values.tsv` | каждое поле каждой записи ПОСЛЕ слияния всех файлов, значение в JSON | 187 439 |
| `entries.tsv` | запись, где заведена, где и сколько раз дописывалась | 32 511 |
| `fields.tsv` | раздел, поле, в скольких записях, читает ли его движок, пример | 783 |
| `refs.tsv` | ссылка: запись, поле, раздел-цель, id цели | 203 782 |
| `ref_schema.tsv` | какое поле какого раздела на какой раздел указывает | 167 |
| `dangling.tsv` | ссылка в поле-ссылке, а записи с таким id нет | 14 |
| `unknown_keys.tsv` | ключ, который движок у этого раздела не читает | 19 |
| `dup_keys.tsv` | повтор ключа в одной записи: что взял движок и что потерялось | 18 |
| `overrides.tsv` | поле задано одним файлом и перезаписано другим | 1 170 |
| `research_cycles.tsv` | циклы в `dependencies` и чем в них входят | 7 |
| `globals.tsv` | ключи верхнего уровня, не списки записей | 113 |

Старый индекс `.index/mod/Piratez/entries.tsv` (`tools/index_mod.py`) отвечает только «где объявлено»;
новый отвечает «что получилось в игре» - с учётом того, что одну запись пишут до трёх файлов.

```
py -3 tools\rul_map.py
py -3 tools\test_rul_map.py
```

Примеры запросов - в конце `RUL.md`. Главное: `values.tsv` грепается по `^раздел\tid\t`.

## Как движок читает рулсеты Пираток (сверено с кодом)

1. **Порядок файлов.** `Mod::loadMod` сортирует рулсеты по полному пути **по убыванию**
   (`a.fullpath > b.fullpath`). Мастер-мод xcom1 грузится раньше мода. Внутри Пираток порядок
   такой: `zz_award_pages_en`, `Yankes_Scripts`, `Shotguns_Rebalance`, `Recolr`,
   `Piratez_Wardrobe`, ..., `Piratez_Armors`, **`Piratez.rul`**, `HitFX-basic`. Символ `_` (0x5F)
   больше `.` (0x2E), поэтому все `Piratez_*.rul` идут РАНЬШЕ `Piratez.rul`, и в любом поле, которое
   задают оба, прав `Piratez.rul`. После него грузится только `HitFX-basic.rul`.
2. **Повтор ключа в записи - побеждает первый.** `YamlNodeReader::useIndex` строит индекс через
   `emplace`, который не перезаписывает; поиск без индекса (`findChildNode`) идёт с начала. PyYAML
   оставляет ПОСЛЕДНИЙ ключ, поэтому любой скрипт на `yaml.load` видит в таких записях не то, что
   игра. `rul_map.py` строит значения из дерева узлов сам и берёт первый ключ (тест проверяет).
3. **Повторная запись с тем же `type`/`name`** дописывает поля в существующую; `delete` удаляет;
   `new`/`override`/`update` - как в `Mod::loadRule`. `refNode` читается раньше собственных полей.
4. **`resourceConfig: Ruleset/Piratez_Globals.rul`** в `metadata.yml`: этот файл движок читает
   дважды - сперва как настройки ресурсов (`Mod::loadResourceConfigFile`), потом как обычный рулсет.
5. **Ключ, которого движок не знает, пропадает молча.** Проверки имён полей в OXCE нет вовсе.

## Устройство Piratez.rul

6,1 МБ, 242 066 строк, 12 разделов. 461 комментарий, 138 якорей (`&имя`), 3 229 ссылок на якоря
(`*имя`), 28 `refNode`.

| Раздел | Строки | Заведено записей | Дописано в чужие |
|---|---|---|---|
| facilities | 1-2 960 | 99 | 16 (все из xcom1) |
| items | 2 961-74 850 | 2 710 | 261 |
| crafts | 74 851-79 560 | 91 | 5 |
| craftWeapons | 79 561-81 786 | 149 | 6 |
| terrains | 81 787-82 563 | 0 | 1 |
| armors | 82 564-126 778 | 106 | **461** |
| soldiers (+4 константы званий) | 126 779-129 116 | 26 | 3 |
| units | 129 117-129 771 | 30 | 0 |
| research | 129 772-172 315 | 4 534 | 78 |
| manufacture | 172 316-205 401 | 2 139 | 19 |
| startingBase | 205 402-205 517 | - | - |
| ufopaedia | 205 518-242 067 | 4 740 | 181 |

**Где на самом деле живёт запись.** «Первое объявление» из старого индекса обманывает, потому
что одну броню или предмет пишут до трёх файлов, и каждый - свою часть:

- `Yankes_Scripts.rul` (грузится вторым, после `zz_award_pages_en`) - 320 броней и 94 предмета,
  у КАЖДОЙ записи ровно одно поле `tags` для скриптов. Для 213 броней это первое упоминание,
  поэтому старый индекс показывает их «объявленными» в файле скриптов.
- `Shotguns_Rebalance.rul` - 121 предмет, по 1-3 поля `shotgunSpread/Choke/Behavior`.
- `Piratez_Armors.rul` - 756 записей: 366 из них - только кукла из слоёв
  (`layersDefinition` + `layersDefaultPrefix`, больше нигде этих полей нет), около 387 броней
  описаны здесь целиком.
- `Piratez.rul` (грузится после всех `Piratez_*`) - 567 записей брони: 106 своих и 461 дописанная,
  у 566 есть `spriteSheet`, `corpseBattle`, `frontArmor` ... `damageModifier`. То есть статы и спрайты брони с
  куклой из `Piratez_Armors.rul` лежат в `Piratez.rul`.

Правило: смотреть запись в `values.tsv` (итог), а откуда какое поле - в `overrides.tsv` и
`entries.tsv` (столбец `updated_at`), а не в первом объявлении.

**Шаблоны на якорях.** Мод объявляет шаблон как настоящую запись с якорем и тут же её
переопределяет: `STR_SPAWN_MUTON_ULTRA` заведён три раза подряд (`&FRIENDLY_SPAWNER_NORMAL`,
`&ENEMY_...`, `&NEUTRAL_...`, `Piratez.rul:74645-74680`), последний (фракция 2) и остаётся в игре,
а первые два живут как якоря для `refNode` других спаунеров. Это приём, не ошибка.

## Цифры

- **Предметы, 4 023.** battleType (enum BattleType, RuleItem.h:34): 0 BT_NONE 1 460,
  11 BT_CORPSE 711, 1 BT_FIREARM 648, 2 BT_AMMO 540, 3 BT_MELEE 209, 10 BT_FLARE 161,
  4 BT_GRENADE 158, 6 BT_MEDIKIT 66, 5 BT_PROXIMITYGRENADE 30, 9 BT_PSIAMP 30.
  45 категорий, крупнейшая STR_BAT_CAT_EXO (1 029). 802 предмета `recover: false`.
  Спрайты: `bigSprite` у 2 813 предметов (2 368 разных), `floorSprite` у 2 755 (1 360 разных),
  `handSprite` у 722 (382 разных), `bulletSprite` у 644 (всего 54 разных), `hitAnimation` 41 разная.
  Скрипты у 57, теги у 98.
- **Броня, 969.** `drawingRoutine`: 0 у 725, дальше 4 (75), 5 (48), 6 (27). `layersDefinition`
  (кукла из слоёв) у 366, `spriteInv` у 592, большие (size 2) - 97.
- **Исследования, 4 628.** Медиана стоимости 4 (!), максимум 1 000 (STR_SCHOOLING_3); 2 022 темы с
  нулевой стоимостью - это флаги и события, а не исследования. `needItem` у 2 041, `destroyItem`
  у 821, `requiresBaseFunc` у 398, `disables` у 163, `lookup` у 203, `getOneFree` у 396, `unlocks`
  у 769. Поле `requires` у исследований не использует НИ ОДНА тема. Доступны без всяких условий
  только 4: STR_INSPECT_MACHINERY, STR_JACKSTOWN_SCOUTING, STR_RECRUIT_PEASANTS, STR_WAT_DO.
- **Производство, 2 158.** Категории: патроны 321, броня 216, грабёж 147, добыча 133, разборка 120,
  утиль 99, трофеи 92, вербовка 68. `randomProducedItems` у 115, `spawnedPersonType` у 53.
  Время (инженеро-часы): медиана 300, максимум 100 000.
- **ХабароПедия, 4 928 статей.** type_id (ArticleDefinition.h:33): 7 TEXTIMAGE 1 877,
  4 ITEM 1 608, 5 ARMOR 893, 8 TEXT 148, 2 CRAFT_WEAPON 112, 6 BASE_FACILITY 112.
  `image_id` у 2 083 статей, 2 039 разных картинок - столько работы у перерисовки педии.

## Дерево исследований

Самая длинная цепочка `dependencies` - 61 тема: от AUX_XEC_WEAPON_TWIN_XPLASMA через
STR_XEC_ARMAGEDDON_ARMOR, рельсотроны, EMP-гранату и разборку роботов вниз до STR_RECRUITMENT и
STR_LOOT_DISTRIBUTION. Полностью - в `RUL.md`.

Циклов в `dependencies` 7. `SavedGame::getAvailableResearchProjects` берёт тему из чьего-то
`unlocks` без проверки `dependencies` - так Пиратки и запирают темы «только через открытие».
Самый большой цикл - 74 темы вокруг контактов и дипломатии (STR_ALIEN_ORIGINS, STR_CONTACT_*,
STR_DIPLOMACY ...), в него 47 входов. **У всех семи циклов вход есть** - через `unlocks`,
`getOneFree`, события (`researchList`), скрипты событий и миссий (`researchTriggers`). Мёртвых
циклов нет.

## Схема ссылок

Выведена из данных, а не написана руками: поле считается ссылкой, если 60 и больше процентов его
строк - id одного раздела. 167 таких полей. Самые нагруженные:

| Поле | Куда | Ссылок |
|---|---|---|
| alienDeployments `data[].itemSets[][]` | items | 39 503 |
| terrains `mapBlocks[].randomizedItems[].itemList[]` | items | 30 637 |
| items `supportedInventorySections[]` | invs | 20 367 |
| research `getOneFree[]` | research | 11 977 |
| research `dependencies[]` | research | 9 068 |
| manufacture `requiredItems{}` | items и crafts | 4 405 |
| ufopaedia `requires[]` | research | 4 357 |
| armors `builtInWeapons[]` | items | 3 385 |
| eventScripts `eventWeights{}` | events | 2 094 |
| armors `units[]` | soldiers | 2 000 |

Значения, которые движок понимает сам, ссылками не считаются: `STR_NONE`; `dummy` в
`waves[].ufo` (волна без НЛО - `AlienMission::think`, «Some missions may not spawn a UFO»);
`globeTerrain` (`BattlescapeGenerator`); `STR_SCIENTIST`/`STR_ENGINEER`; палитры `PAL_*`.
Поля-подписи (`name`, `title`, `briefing.*`, `*Name`) - ключи перевода, а не ссылки.

## Находки: ошибки мода, которые движок проглатывает молча

Всё ниже проверено по коду движка и по тексту рулсета. Данные мода не трогали (правило 6 и
«ничего не меняем в механике») - это список для Dioxine, а не заплатка.

### Поле потеряно из-за повтора ключа (движок берёт первый)

| Где | Что | Взято | Потеряно |
|---|---|---|---|
| `Piratez_Factions.rul:9633` AUX_XARQUID_GRAPPLE | `damageAlter:` дважды подряд, первый пустой | пусто | RandomType 2, ToHealth 0.4 ... - вся настройка урона крюка |
| `Piratez.rul:58493` STR_STAFF_OF_BURNING_SOULS | `power` | 16 | 18 |
| `Piratez.rul:1288` STR_EYE_OF_HORUS | `placeSound` | 309 | 305 |
| `Piratez_Resources.rul:13277` BIG_CAPTAIN_YESGRAY_NOGOLD | `fileSingle` | Captain_GrayNoGold.png | UPed_Unavailable.gif |

Ещё 14 повторов с одинаковым значением (кукла STR_PEASANT_GLITTERARMOR_UC, `personalLight` у
четырёх броней, `needItem` у SECTOPOD_ARMOR) безвредны. Скрипт на PyYAML взял бы в первых трёх
строках ПОСЛЕДНЕЕ значение и разошёлся бы с игрой - ещё одна сторона граблей R-046.

### Ключ записан не в тот раздел

| Раздел | Ключ | Записей | Почему не работает |
|---|---|---|---|
| alienDeployments | `despawnEvenIfTargeted: true` | 16 (Piratez_Factions.rul, 59863-85841) | читает только `RuleAlienMission` (RuleAlienMission.cpp:81), `AlienDeployment` - нет |
| eventScripts | `interruptResearch` | 2 (STR_NINJAS_AT_BAY, STR_NINJAS_ESCALATION) | читают `RuleEvent` и `RuleAlienMission`, `RuleEventScript` - нет |
| crafts | `revealedFloors: [3]` | 1 (STR_CAVES_DROP_ENTRY, Piratez.rul:79547) | ключ блока карты (`MapBlock.cpp:71`), на уровне корабля не читается |

Ключей, которых движок не знает НИГДЕ, в записях нет ни одного. На верхнем уровне
`Piratez_Globals.rul` четыре таких: `theMostUselessOptionEver`, `theBiggestRipOffEver`, `downloads` -
шутки и заготовки, и `minReactionAccuracy: 5` - а вот это похоже на настройку, которой в OXCE 8.7 нет.

### Битые ссылки - 14

- **Три уже известны** и закрыты заплаткой движка (DECISIONS, 2026-09-20): `crafts` STR_RED_BARON
  `requires` STR_RED_BARON; статьи STR_LIVING_QUARTERS_ADVANCED_LARGE_DAMAGED и
  STR_OFFERING_TO_PURPLE_BLOOM требуют несуществующих тем. Инструмент нашёл их сам - это и есть
  проверка, что разбор ссылок верный.
- `startingConditions.allowedArmors` (Piratez_Globals.rul): STR_NEKO_WITCH_OUTFIT в пяти условиях -
  это ПРЕДМЕТ, брони с таким именем нет; STR_GNOME_TAC_GRAV_ARMOR - тоже предмет; STR_SOLDIER_DOLL -
  тип солдата. Броня, которую автор хотел разрешить, на этих миссиях не разрешена.
- `startingConditions` STR_STARCON_GAL_PARTY: `allowedCraft` STR_DELIVERATOR - такого корабля нет.
- статьи STR_MUTANT_REAPER и STR_TAMED_REAPER: `weapon: STR_JAWS`, STR_WHITERABBIT:
  `weapon: STR_WHITERABBIT_CLOCK` - таких предметов нет, блок оружия в статье пустой.

## Что это даёт проекту

- **HD-арт.** Точные списки того, что рисовать и что рисуется реально: 2 368 разных `bigSprite`,
  1 360 `floorSprite`, 382 `handSprite`, 2 039 картинок педии, 968 броней со `spriteSheet`
  и 366 кукол из слоёв. Всё из итоговых значений, а не из первого объявления - то есть без
  предметов, чей спрайт `Piratez.rul` потом переписал.
- **Бенчмарк ИИ и баланс.** `values.tsv` даёт итоговые числа оружия и брони без запуска игры,
  `refs.tsv` - кто кого выставляет (`alienRaces.members`, `alienDeployments.data[].itemSets`).
- **Проверка следующей версии Пираток.** Прогнать `rul_map.py` до и после обновления мода:
  `dangling.tsv`, `unknown_keys.tsv`, `dup_keys.tsv` покажут новые дыры до запуска игры.

## Чего НЕ выяснил

- **Слияние полей повторной записи - поверхностное.** Поле верхнего уровня заменяется целиком.
  Движок почти везде делает так же, но словари, которые он ДОПИСЫВАЕТ (`tags` и подобные), здесь
  могут выглядеть иначе, чем в игре. 1 170 перезаписей в `overrides.tsv` - по этой модели.
- **Проверка ключей - по строковым литералам кода**, а не по разбору `Rule*::load`. Ключ, имя
  которого собрано на ходу, распознан только для приставок `tu`/`cost`/`flat`/`conf` (RuleItem).
  Если класс читает ключ через помощника из другого файла, которого нет в списке `HELPERS`,
  будет ложное «не в классе» - так было с `ufos` (RuleCraftStats) и `mapScripts` (Mod.cpp),
  оба добавлены. Вложенные ключи (внутри `damageAlter`, `battlescapeTerrainData`) не проверяются.
- **Достижимость исследований** посчитана только для циклов. Какие темы недостижимы вообще
  (нужен предмет, который нигде не выпадает и не производится) - не считал: для этого надо
  моделировать трофеи миссий, производство и события вместе.
- **Скрипты** (`Yankes_Scripts.rul`, поле `scripts`) не разбираются - это отдельный язык, см.
  `yankes-scripts-review.md`.
- **Моды поверх Пираток** (RU-patch и прочие из `user/mods`) не загружаются - только мастер и сам мод.
