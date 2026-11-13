# X-Piratez v.o2: что изменилось и как перейти, не потеряв своё

Сверка 14.10.2026: новая версия `E:\Dioxine_XPiratez_o2\Dioxine_XPiratez` (v.o2) против нашей установки
`Пиратки\Dioxine_XPiratez` (v.o1.1.1). Всё сверено файлами и прогоном игры, установка и репозиторий не тронуты.
Скрипты и таблицы сверки — в блокноте сессии (`scratchpad/o2`), здесь только выводы и цифры.

## Коротко

| Что | Вывод |
|---|---|
| Движок | o2 требует OXCE 8.7 (`requiredExtendedVersion: "8.7"`) — наш 8.7.1, слияние движка не нужно |
| `common`, `standard` | у o2 отличаются только концами строк и своими языками Android; **оставляем наши** |
| Моды Dioxine | `Piratez`, `Piratez Cities Lore`, `Cyrillic Names`, `Czech Names`, `OAK patch for RU Piratez` — берём из o2 целиком |
| Наши моды | `hd`, `hd_core`, `XPZ RU-patch`, `Apple_Processing`, `XPZ_Kisya_Brysya_Sisters`, `intro_voice`, `piratez_tank_turret` — не трогаем; ни одно их поле o2 не задел (кроме RU-патча, см. ниже) |
| Наш файл в папке Piratez | один: `Ruleset/zz_award_pages_en.rul` — после замены пересоздать `tools/award_pages_en.py` |
| **Ошибка самого o2** | рулсет зовёт `Resources/Pedia/ChaosSyn_CPAL.png`, файл называется `ChaoSyn_CPAL.png` — при `lazyLoadResources false` игра встаёт на старте с FATAL, при ленивой загрузке — на статье педии. Заплатка — копия файла под ошибочным именем в нашем моде (проверено) |
| HD интерфейса и педии | 2173 картинки совпали; 81 нашу HD-картинку o2 переименовал (имя `_CPAL`) — без переименования они пропадут; 134 новые картинки без HD |
| HD террейна | 14 удалённых наборов никто не зовёт (наши паки на них — мёртвый груз); у JUNGLEROCKS перерисованы кадры 0–10 — наши 11 HD-кадров устарели |
| RU-патч | писан под o1.1.1: 6 полей перебивает o2, 54 новые строки o2 будут по-английски, 105 исправлений Dioxine в ru.yml скроет патч |
| Сейвы | сейв o1.1.1 грузится в o2 (см. «Прогон игры») |

## 1. Моды Dioxine

Заменяются папкой из o2: `Piratez`, `Piratez Cities Lore`, `Piratez Cyrillic Names`, `Piratez Czech Names`,
`OAK patch for RU Piratez`. Ни один файл Dioxine у нас не правлен: последние даты изменённых — его июньский выпуск.

**Единственный наш файл внутри `Piratez`** — `Ruleset/zz_award_pages_en.rul` (28.09). В o2 его нет, после замены
папки он пропадёт. Пересоздать: `py -3.13 tools/award_pages_en.py` (пишет и `extraStrings en-US`, и `ru` — R-131).

### Ошибка o2: ChaosSyn

`Piratez_Resources.rul:14459`:

```
  - typeSingle: CHAOS_SYNS_UFOPEDIA_PICTURE_CPAL
    fileSingle: Resources/Pedia/ChaosSyn_CPAL.png
```

В `Resources/Pedia` лежит `ChaoSyn_CPAL.png`. Прогон с `lazyLoadResources false`:
`[FATAL] FileRecord::at(Resources/Pedia/ChaosSyn_CPAL.png): requested file not found` — игра стоит на StartState.
У игрока с ленивой загрузкой ошибка выскочит при открытии статьи о Хаос-Синах.

Заплатка **рулсетом не лечится**: мод после Piratez с той же `typeSingle` и верным именем файла добавляет
свою запись, а запись Piratez всё равно грузится — прогон встал на том же FATAL.

Лечится **файлом**: в нашем моде, грузящемся после Piratez, положить копию картинки под ошибочным именем —
`Resources/Pedia/ChaosSyn_CPAL.png` (это `ChaoSyn_CPAL.png` из o2). Файлы модов движок кладёт в одно общее
дерево путей, и строка Piratez находит наш файл. Проверено прогоном (мод-проба `zz_o2fix`: только `metadata.yml`
и этот файл) — игра загрузилась полностью, см. раздел 7. Куда положить постоянно — решить: `hd_core` (он у всех
игроков) или маленький отдельный мод. Сообщить Dioxine — у него поправка в одну букву.

### Ссылка `getOneFree: STR_ALIEN_TERROR` — не битая

`research STR_SPARTAN_TRIUMVIR getOneFree: STR_ALIEN_TERROR` верна: исследование `STR_ALIEN_TERROR` есть в
мастер-моде (`standard/xcom1/research.rul:820`, `points: 50`, `needItem: true`), Пиратки его не переопределяют.
Прежняя запись здесь («такого исследования нет») была ошибкой: поиск шёл только по рулсетам Piratez, без
мастера. Индекс `.index/mod/Piratez/rul` мастер включает (`rul_map.py`, DEF_MASTER) — проверять по нему.

## 2. common и standard

186 файлов `common` и 289 `standard` отличаются, но только концами строк (размер меньше на число строк) и
языками Android. Наши `bin/common`, `bin/standard` и копии в установке **оставляем** — в них наши строки опций
(`Language/OXCE`) и шрифты; брать o2 значит их потерять. Святое правило не задето: правок нет.

## 3. Наши моды против o2

Сверка `tools/rul_map.py` каждого мода с мастером o1 и с мастером o2, по каждому полю мода — поменял ли его o2:

| Мод | Полей | Задетых o2 | Новых битых ссылок |
|---|---|---|---|
| Apple_Processing | 86 | 0 | 0 |
| XPZ_Kisya_Brysya_Sisters | 78 | 0 | 0 |
| piratez_tank_turret | 12 | 0 | 0 |
| intro_voice | 1 | 0 | 0 |
| XPZ RU-patch | 1064 | 6 (ниже) | 0 |

`hd` и `hd_core` рулсетов не имеют — их касаются только имена картинок (раздел 5).

## 4. RU-патч (Extremator 12.3.2, 19.09.2026, под o1.1.1)

Патч грузится после Piratez и перебивает его и строками, и рулсетами.

### Поля, которые o2 поменял, а патч ставит своё

| Поле | Патч | o1 | o2 | Что значит |
|---|---|---|---|---|
| armors `STR_SANDHAWK_ARMOR_UC` corpseGeo | `STR_ACADEMY_CORPSE` | — | `STR_CHEMICALS` | o2 сам задал труп, патч его заменит |
| soldierBonuses `STR_MEDAL_ASSAULTER_9` | reactions 10, firing 9 | 9 / 8 | 10 / 10 | патч режет стрельбу на 1 против o2 |
| soldierBonuses `STR_MEDAL_ARCHER_10` | stamina 18 | 16 | 18 | совпадает с o2, вреда нет |
| ufopaedia `STR_DURATHREAD_WORKING` text_width | 136 | 156 | 128 | вёрстка статьи |
| ufopaedia `STR_GUILD_AUTOPSY` text_width | 133 | 128 | 156 | вёрстка статьи |
| interfaces mainMenu `text color2` | 89 | — | — | косметика, вреда нет |

Механику меняют первые две — решает автор патча (или Vitali: оставить как в патче или как в o2).

### Строки

- en-US o2: **56 новых ключей**, перевод есть у 2. **54 будут по-английски**: Spartan Triumvir, Lamia Man,
  GUNTANK, Glaurung Machinegun, Seashell Monokini, Giftmaster's Lair (`STR_LOC_CATACOMBS_THEBAN`),
  `*_DISASSEMBLY` (Energy Focus, Ethyr Drive, Integrity Field, Omnisensor, Spatial Displacer),
  `STR_PINUP_164/165`, `STR_GDX_190` и др.
- **136 английских строк o2 изменены** (числа, описания) — патч перебивает все 136. Для 105 из них Dioxine
  обновил и ru.yml o2, но под патчем эти правки пропадут. Пример: `STR_GIANTSPIDER_QUEEN_CORPSE_EXTRACTION`
  в o2 «(3/22/4)», у патча старое «(3/24/4)» — игрок увидит неверные числа.
- ru.yml o2 против o1: 74 изменены, 3 новых; все 74 скрыты патчем.

Варианты (решает Vitali):
1. Ждать патч Extremator под o2 — правильный путь, переводы его.
2. До выхода патча — наш маленький языковой мод после патча: русский o2 для 105 изменённых ключей
   (текст Dioxine, не наш перевод). 54 новых ключа — по-английски или машинный перевод, только с одобрения.

## 5. HD интерфейса и педии

HD-слой ищет картинку по имени файла или типу в нижнем регистре (`Mod::loadHdUiArt`, R-033).
Сверка по `extraSprites` o1 и o2 всех наших `hd/UI` (`hd`, `hd_core`, `hd_18+`):

| Состояние | Картинок |
|---|---|
| то же имя, картинка та же | 2173 |
| то же имя, картинка изменена | 7 (Green_Armor_CPAL — 13 пикселей, остальные — см. «изменённые ресурсы») |
| **наша HD, имени в o2 больше нет** (переименовано в `_CPAL` или убрано) | 94, у 81 найден наследник |
| картинка o2 без HD | 207: 73 — наследники из строки выше, **134 новые** |
| не из Piratez (чужие моды) | 110 |

### 81 наследник: что делать с каждой HD (предварительно, по числам; решать листом)

| Класс | Число | Действие |
|---|---|---|
| A — та же картинка, другое имя | 15 | переименовать HD (7V7KILL, Big_Cat, DBLKILL, GUNNER, Hotkeys, Peasants_New, Temple_Door, X77/X97_Ped …) |
| C — та же, сдвинута на 1–6 пикселей | 10 | подогнать сдвиг (ALPHA, Bath, DRESSUP, GLOBETROTTER, Gnome_28, Mechapilot, Runtsy_5, Smugglers_3, UNDERFIRE, X67_Ped) |
| B — силуэт тот же, рисунок другой | 20 | смотреть листом: перекраска или вовсе не тот наследник (Exotic_Places → Marza_SSMD1 и т.п. — не он) |
| D — нарисовано заново | 35 | почти все — награды (`Resources/Awards/*_CPAL`); новая награда занимает половину кадра, HD прежней не годится — перерисовка |
| нет файла | 1 | ChaosSyn — ошибка o2 (раздел 1) |

Без переименования эти 81 картинку игра нарисует классикой (через xBRZ) — не катастрофа, но потеря.
Наоборот, оставленная HD под старым именем на другой рисунок — подмена (R-033): строки `is far from` в логе.

### 134 новые картинки без HD

120 — `Armors/Gals/Bikini_Bottom` (листы брони), 9 педия (Courtesan, GDX_190, Giftmasters, Guntank,
Pinup 164/165, Ghost Gal, Spartan Triumvir), 2 `Body_X` (Lamia_Man, Spartan_Triumvir), 2 Barbarian
(Shell_Shield, Lei), 1 награда HUNTRESS. Работа для арта — по одобрению Vitali.

## 6. HD террейна и прочие ресурсы

- **14 удалённых наборов** (CAVEPINK, CAVERED, C_EXT_NOSE_BUMPLESS_PRPL, C_EXT_ROOFBITS_SILVER, DUSKURBAN,
  MILURBAN, U_BASEGOLD, U_BITSN, U_DISEC3GOLD, U_EXT, U_EXT_ROOF, U_PODSGOLD, U_WALL, U_WALL02GOLD):
  ни рулсеты o2, ни наши моды их не зовут. Наши HD-паки на них (U_EXT 101 кадр, U_EXT_ROOF 101, DUSKURBAN 116,
  MILURBAN 116, U_WALL 87, CAVEPINK 41, CAVERED 41 …) безвредны; убрать можно, но не обязательно.
- **Изменённые MCD** (C_INT*, CATACDECOR*, containers, DUNGEON*, INDUSLUM, MUCONCRETE, MUICE, MUJUNGLE*,
  OSIRON_FINNIK, PLANE2/PLANE2R, UAC_*, JUNGLEROCKS): поменяны только свойства, ScanG и LOFT, **номера
  кадров не тронуты** — наши HD-кадры остаются верными.
- **JUNGLEROCKS.PCK: кадры 0–10 перерисованы** (каменные блоки стали другой формы, у полов выросла трава,
  у кадра 5 силуэт другой — IoU 0.46). Наши HD-кадры 0–10 в установке устарели — на карте будет старый камень.
  До перерисовки — убрать эти 11 файлов (игра покажет классику через xBRZ).
- VILFRNITURE: 111 кадров, ни один не изменён (другой только TAB).
- Новый набор CATACDECOR_VILLA — без HD.
- `PIR_44.png`: изменён один кадр 266 — у нас есть HD-пак `PIR_44.PCK`, кадр 266 устарел.
- BIGOBS 487, 488, 1115 (Spartan_MG, его патроны, SW_Shotgun — другая палитра), FLOOROB 739 (FloorFurs),
  GUI_Soldiers, Heavy_Suit (1 пиксель), фон Aurora_Dancing_FG_334_BCK — у нас HD на них нет, делать нечего.
- Карты LAREGBUNKER_00, URBANDIOHUGE00, маршруты CRASHEDPLANE* — HD не касаются.

## 7. Прогон игры

Наш exe (`build-release/bin/openxcom.exe`, 13.10), невидимо (`tools/game_hidden.py`), полная загрузка ресурсов
(`lazyLoadResources false`, R-182), сейв `logs/NoCodexCatZ.sav` (o1.1.1, 2606 г., месяц 2). Раскладка модов —
ссылки в блокноте: моды Dioxine из o2, наши из установки.

| Прогон | Моды | Итог |
|---|---|---|
| контроль: установка как есть (o1.1.1) | piratez o1.1.1, RU-патч 12.3.2, RusNames, Cities Lore, tank_turret, intro_voice, hd_core, hd | сейв загружен, геоскейп, окно «завершено производство», дамп снят |
| o2 без заплатки | те же, piratez v.o2 | `[FATAL] FileRecord::at(Resources/Pedia/ChaosSyn_CPAL.png)`, игра стоит на StartState |
| o2, заплатка рулсетом | + zz_o2fix (extraSprites) | тот же FATAL |
| **o2, заплатка файлом** | + zz_o2fix (файл ChaosSyn_CPAL.png) | **сейв o1.1.1 загружен**, тот же геоскейп и то же окно, дамп совпадает с контролем на глаз |

Ошибки лога o2 (с заплаткой) против контроля:

- одинаковые в обоих: `Failed to load item STR_APPLE_JAM / STR_APPLE_PUREE`, `research STR_PUMA_SISTERS_PREQ` —
  в сейве есть вещи модов Apple_Processing и Kisya, а в `options.cfg` установки эти моды **не включены**
  (вне o2, так было и на o1);
- в контроле, но не в o2: 89 строк `ufopaedia item misses type_id attribute` — Dioxine это починил;
- новых ошибок нет; строк `is far from`, `matches no image`, `already mapped in`, `not found in` нет ни там, ни там.

Не проверено в игре: бой на o2, педия с переименованными картинками, моды Apple_Processing и Kisya
(выключены в установке — только сверка рулсетов, раздел 3).

## 8. Порядок перехода (после «да» Vitali)

Все шаги правки игры — через `tools/editq.py`; выпуск — только `editq.py release now` (R-322).

1. Резервная копия: `Пиратки\Dioxine_XPiratez\user\mods\Piratez` и четыре мода Dioxine — в резерв.
2. Скопировать из o2 моды Dioxine (раздел 1). `common`, `standard`, наши моды, `options.cfg` — не трогать.
3. Заплатка ChaosSyn — файл `Resources/Pedia/ChaosSyn_CPAL.png` в выбранный мод (раздел 1).
4. Пересоздать `zz_award_pages_en.rul` (`tools/award_pages_en.py`).
5. HD: переименовать 15 (A); 10 (C) подогнать; 20 (B) и 35 (D) — листом Vitali; убрать JUNGLEROCKS 0–10 и
   кадр 266 PIR_44 до перерисовки. В обе копии мода hd (R-087) — сверить списки.
6. Строки — по решению про RU-патч (раздел 4).
7. Проверка: прогон на чистом и рабочем профиле, в логе ни `[FATAL]`, ни `not found`, ни `is far from`,
   ни `already mapped in`; экраны педии с переименованными картинками — дампом.
8. Выпуск с строкой в CHANGELOG («поддержка X-Piratez v.o2»).

## 9. Сделано 14.10 (по слову Vitali «исправить, пока не выйдет официальный; заплатку — поменять имя файла»)

Всё прежнее — в `E:\_backup\piratez_o1_2026-10-14` (моды Dioxine, RU-патч, `hd_ui`, `hd_pack`, `rupatch_rul`, `options.cfg`).

| Шаг | Что сделано |
|---|---|
| Моды Dioxine | пять папок заменены на o2; `common`, `standard`, наши моды, `options.cfg` не тронуты |
| ChaosSyn | файл в самом `Piratez/Resources/Pedia` переименован `ChaoSyn_CPAL.png` → `ChaosSyn_CPAL.png` (имя, которое зовёт рулсет); отдельного мода нет. Выйдет o2 с исправлением — заменится сам |
| `zz_award_pages_en.rul` | пересоздан `tools/award_pages_en.py` под o2 |
| RU-патч, рулсеты | сняты комментарием (`# o2: снято`) три поля: Sandhawk `corpseGeo`, `STR_MEDAL_ASSAULTER_9`, `STR_GUILD_AUTOPSY text_width` — значение берётся из o2. ARCHER_10, DURATHREAD и `color2` оставлены (вреда нет) |
| RU-патч, ru.yml | 66 строк — трёхстороннее слияние и выравнивание чисел с en o2 (проверены друг другом), 40 ручных правок, 30 строк патча оставлены как были, 54 новых ключа o2 переведены в терминах патча. Пример: `STR_GIANTSPIDER_QUEEN_CORPSE_EXTRACTION` теперь «(3/22/4)». Версия в `metadata.yml`: «12.3.2 / 19-SEP-2026 + o2 HD 14-OCT-2026». Выйдет патч Extremator под o2 — ставится поверх, наши правки не нужны |
| HD интерфейса | класс A (14 картинок) переименован; класс C (9) сдвинут на (dx·k, dy·k), край — повтором крайних пикселей; во всех копиях, где картинка была: `hd/UI`, `hd/UI_esrgan`, `hd_18+/UI` установки и репозитория — 77 файлов |
| `.pal.txt` | у 23 картинок записаны заново по палитре PNG o2: o2 пересобрал индексы и палитру (расходится 233–238 цветов из 256), прежний `pal.txt` перекрасил бы HD чужими цветами (HdUiArt::prepare). Прежние палитры равны палитре o1 у всех |
| C_017_CPAL | o2 отдал это имя бывшей `BlackDragonSmile_FG_541_CPAL` (корреляция с o1 1.0). Прежняя `C_017_CPAL` o1 была сиротой — её не зовёт ни один рулсет, и наша HD под этим именем рисовала её (корреляция с новой 0.41). Сирота — в резерв, на её место — HD чёрного дракона |
| Runtsy_5, Prize_Martial_Arts | из классов C и A перенесены в B: сдвиг не объясняет различие, решать листом |
| JUNGLEROCKS | HD-кадры 0–10 (o2 их перерисовал) убраны в резерв `hd_pack` и сняты с манифеста пака; 11, 12, 14, 17, 19 остались. В репозиторной копии мода набора нет |
| PIR_44 кадр 266 | в o2 изменён один пиксель; HD-кадр оставлен как есть |
| Манифест пака | `art/manifest/build_manifest.json` (цель game): 78 путей переименованы с происхождением `o2_rename` (`derived_from` — прежний sha, одобрение — как у прежнего), JUNGLEROCKS 0–10 сняты. `status`: изменённых 0; 24 «нет» — шрифты, ушедшие в `hd_core` раньше (R-202), к o2 не относятся |
| Индекс рулсетов | `.index/mod/Piratez/rul` пересобран на o2 вместе с мастером: 22976 записей, 3 битые ссылки (`weapon` педии `STR_JAWS` ×2 и `STR_WHITERABBIT_CLOCK`) — были и в o1 |

Остаётся Vitali (ничего не подключено): класс B (22 картинки), класс D (35, почти все награды), 134 новые
картинки без HD, HD для нового набора CATACDECOR_VILLA и перерисовка JUNGLEROCKS 0–10.
