# Разбор Piratez_Globals.rul (X-Piratez)

Файл: `Пиратки/Dioxine_XPiratez/user/mods/Piratez/Ruleset/Piratez_Globals.rul`, 9 196 строк, 20 разделов.
Файл прочитан скриптами, а не глазами. Рулсеты Пираток слиты так же, как их сливает движок (`tools/rul_map.py`, итог в `.index/mod/Piratez/rul/`). Более поздние файлы мода записи Globals не переопределяют.
Разделы разбирались параллельно; каждая находка из раздела «Косяки» перепроверена по коду движка и по слитым данным.

**Файл не правился**: установка Пираток только читается. Все исправления ниже — предложения автору.

## Что в файле и против чего сверено

| Раздел | Строки | Записей | Код движка |
|---|---|---|---|
| `invs` | 1-243 | 13 | `RuleInventory.cpp`, `Inventory.cpp`, `Mod.cpp:2528-2548` |
| `cutscenes` | 244-1009 | 28 | `RuleVideo.cpp`, `SlideshowState.cpp`, `Font.cpp` |
| `commendations` | 1010-4109 | 110 | `RuleCommendations.cpp`, `SoldierDiary.cpp` |
| `missionRatings`, `monthlyRatings` | 4110-4146 | 13 + 22 | `DebriefingState.cpp:580-590`, `MonthlyReportState.cpp:171-182` |
| `itemCategories` | 4147-4289 | 71 | `RuleItemCategory.cpp`, фильтры `CraftEquipmentState`, `PurchaseState` |
| `startingConditions` | 4290-7236 | 45 | `RuleStartingCondition.cpp`, `BattlescapeGenerator.cpp` |
| `enviroEffects` | 7237-8065 | 34 | `RuleEnviroEffects.cpp`, `NextTurnState.cpp` |
| `interfaces` | 8066-8586 | 148 | `RuleInterface.cpp`, `State.cpp`, все `add(..., "id", "interface")` |
| `extraGlobeLabels` | 8587-8828 | 47 | `RuleGlobe` |
| глобальные ключи, опции, `ai`, `constants`, `mana`, `transparencyLUTs` | 8829-9196 | — | `Mod.cpp` (`loadFile`, 2700-2740, 3195-3300, 3740-3905, 4088-4105), `Options.cpp` |

## Как движок обращается с этими данными

Без этого часть находок не понять.

- **Неизвестное имя в списках `allowed…/forbidden…` стартового условия** молча ни с чем не совпадает: `std::find` по строкам (`RuleStartingCondition.cpp:52-71, 107-213, 217-301`). В логе ничего.
- **Запрещённая броня меняется** на `defaultArmor` для типа солдата. Цель не перепроверяется ни на allowed, ни на `armor.units`; фильтр только по размеру (`BattlescapeGenerator.cpp:1085-1095`). В большинстве условий Пираток запасная броня — `BOXX_ARMOR` («в ящике», `allowsMoving: false`).
- **HWP проверяется дважды** (`BattlescapeGenerator.cpp:1000-1026`): сначала сама машина (`isVehiclePermitted`), потом её патрон — первый боеприпас слота `vehicleFixedAmmoSlot`, по умолчанию 0 (`RuleItem.cpp:150, 1600-1607`), через `isItemPermitted`. Патрон не прошёл — машина с патронами молча остаётся на базе.
- **`allowedItems` и `allowedItemCategories`** работают как объединение (`RuleStartingCondition.cpp:229-298`).
- **Медали «убийства по критерию»**: каждый OR-блок `killCriteria` считается отдельно, одинаковые блоки дают двойной счёт (`SoldierDiary.cpp:456` — комментарий самого движка, `:590`).
- **Тип миссии в статистике солдата** — тип последнего сыгранного этапа (`BattlescapeState.cpp:3752`, `DebriefingState.cpp:1179`).
- **`fixedUserOptions` / `recommendedUserOptions`** применяются только к опциям, у которых есть категория в меню (`Mod.cpp:2708-2713, 2730-2735`); `maximizeInfoScreens` из рекомендованных движок стирает явно (`Mod.cpp:2705`).
- **Элемент интерфейса с id, который никто не спрашивает**, молча игнорируется (`State.cpp:201-203`).

## Что проверено и чисто

| Проверка | Итог |
|---|---|
| invs: клетки контейнеров не пересекаются, не выходят за 320×200, не закрывают куклу | чисто |
| invs: матрица `costs` полная (13×12); `getCost` делает `find()->second` без проверки, так что пропуск был бы неопределённым поведением | пропусков нет |
| invs: новый слот `STR_QD_SLOT` («Q.D.») — цены в обе стороны, 2248 предметов его разрешают, строка есть | заведён полностью |
| cutscenes: 28 записей — все картинки, строки (en и ru), `musicId`, ссылки из `gameOver`, alienDeployments и research | чисто |
| cutscenes: английские подписи влезают в рамку и в экран (оценка шрифтом FONT_SMALL мода, строка 8 px) | влезают все |
| commendations: ключи, имена критериев, формат `killCriteria`, больше 1150 имён в них (661 предмет, 22 расы, звания, типы урона, статусы, фракции) | все существуют |
| commendations: пары раса+звание и оружие+патрон выполнимы; `sprite` 0..6 при 7 кадрах; уровней не больше 10; `missionTypeFilter` — все типы существуют | чисто |
| startingConditions: 45 записей, все используются (129 ссылок из alienDeployments), 1045 целей `defaultArmor` существуют и все размера 1, allowed/forbidden одного вида не смешаны, все `allowedVehicles` — HWP | чисто, кроме находок ниже |
| enviroEffects: все ключи читаются; брони в `armorTransformations` существуют (иначе падение на загрузке); палитры объявлены; предметы аур `weaponOrAmmo` существуют (иначе падение на 2-м ходу); 33 ссылки из заданий и террейнов | чисто |
| interfaces: все id, кроме перечисленных ниже, движок спрашивает; цвета в 0..255 (−1 — ванильное соглашение) | чисто |
| глобальные ключи, `ai`, `constants`, `mana`, `lighting`, `difficultyCoefficientOverrides` | читаются все, кроме `minReactionAccuracy` |
| `startingTime`: 1.1.2601 — четверг, `weekday: 5` (1 = воскресенье) | верно |
| 167 `hiddenMovementBackgrounds` — все в extraSprites; `vaporColor` предметов 0..11 при 12 LUT | чисто |
| 47 меток глобуса: координаты, строки, повторы | чисто, кроме опечаток |

## Косяки

Порядок — по тому, насколько они видны игроку.

### 1. Три HWP разрешены условием, но молча не выезжают — их патрон условие не пропускает

- **Sentry Spike.** Патрон `STR_HWP_SPIKE_ROCKETS` имеет только категорию `STR_BAT_CAT_AUX`; у остальных патронов HWP есть `STR_BAT_CAT_TANK_AMMO`.
  - `STR_STARCON_SPACE` (машина — 6943, категории [0G, TANK_AMMO] — 6939);
  - `&allowedHWPExo` (7127) — EXO, MARS, MARS_CODES (категории [EXO, TANK_AMMO] — 7123, 7153, 7161).
  - Не выезжает на: SPACE_STATION_1-5, COMMS_DISRUPTION, MOON_NAZIS_1/2, LABYRINTHUS_NOCTIS, CYDONIA.
  - Исправление: `allowedItems: [STR_HWP_SPIKE_ROCKETS]` в эти условия (объединяется с категориями) или категория TANK_AMMO самим ракетам.
- **Red Mage ASC-30.** Патрон `STR_WIZ_SPELL_HADES` не проходит:
  - SPACE (6944) — нет категории 0G/TANK_AMMO;
  - GAL_PARTY (4926) — allowedItems 4911-4924 только безделушки;
  - SHADOWLANDS_NOSTUFF (6572) — в `&AllowedItemsShadowlandsNostuff` (6566-6571) вписаны заклинания Doctor X A70, а HADES нет. Механизм автору известен — это недосмотр.
  - Не выезжает на: SPACE_STATION_*, TAVERN, CATACOMBS_BUTCHER*. На EXO и MARS выезжает (у HADES есть категория EXO).
- **Doctor X A70 в GAL_PARTY** (4928): патрон `STR_WIZ_SPELL_HOLOGAL` не в allowedItems таверны (в NOSTUFF, 6568, он есть). Из трёх разрешённых в таверне HWP реально выезжает одна — Doctor X Vampire.
- Игрок видит машину в брифинге и экипировке, а в бою её нет, без сообщения.

### 2. Ведьмин наряд неко: последствия опечатки, о которой уже писали

`STR_NEKO_WITCH_OUTFIT` вместо `STR_NEKO_WITCH_OUTFIT_UC` (5740 → NOHELMET_INFILTRATION_MAX6 и через `*` на 5796 NOHELMET; 5925 CITY; 6068 CITY_STEALTH; 6211 EMANSION) и `STR_GNOME_TAC_GRAV_ARMOR` без `_UC` (6052) уже отправлены Dioxine в первом отчёте ([piratez-bugreport.en.txt](piratez-bugreport.en.txt), п. 6). Новое — какой эффект:
- неко-H в ведьмином наряде переодевается: NOHELMET*, CITY → `STR_NEKO_BELLE_UC`, EMANSION → наряд горничной;
- **CITY_STEALTH** (миссия POLIS_TERMINAL): `defaultArmor` для NEKOMIMI_H — `BOXX_ARMOR`, **неко весь бой сидит в ящике**;
- гном в тактической грав-броне на POLIS_TERMINAL → `STR_GNOME_DRESS_UC`.
- Два вопроса из того отчёта закрываются сами: `STR_SOLDIER_DOLL` (4681) — нужная `STR_AURORA_DOLL_ARMOR_UC` уже стоит на 4682; `STR_DELIVERATOR` (4975) — это английское название крафта `STR_FIRESTORM` (en-US.yml:7464), а он уже в списке на 4950. Обе строки просто удалить.

### 3. Две медали считают одно оружие дважды

Обе — `killsWithCriteriaCareer`, OR-блоки повторены дословно:
- **SHELLSHOCKED** (1768): `[1, ["STR_FLAMETHROWER", "FACTION_HOSTILE", "STATUS_DEAD"]]` на 1852 и 1860. Каждое убийство огнемётом идёт за два. Удалить 1859-1860.
- **HAMMERER** (2078): `STR_COOKER` на 2122 и 2128. Удалить 2127-2128.

### 4. `minReactionAccuracy` не действует нигде — и мы сказали автору неверно

- Ключ стоит на верхнем уровне (8878) и под `ai:` (9152). В первом отчёте (п. 8) мы написали, что под `ai:` он работает. **Это ошибка**: `ai:` в `Mod.cpp:3742-3765` его не читает, и во всём `src` такого ключа нет.
- Его убрал коммит OXCE `be1d81980` (Meridian, 2025-05-17, «Reaction fire thresholds»). Заменили:
  - для врагов и мирных — `ai.reactionFireThreshold` / `reactionFireThresholdCiv` (у Пираток уже 5);
  - для бойцов игрока — пользовательская опция `oxceReactionFireThreshold`, по умолчанию 0 (`Mod.cpp:5012`).
- Раньше порог 5 действовал на **всех**, включая бойцов игрока (при `battleUFOExtenderAccuracy`, у Пираток fixed true). Теперь порог 0 означает «проверки нет» (`TileEngine.cpp:2622-2623`): бойцы игрока открывают ответный огонь и при шансе 1-4 %.
- Исправление: удалить обе строки; если нужно прежнее поведение для игрока — `oxceReactionFireThreshold: 5` в `recommendedUserOptions` (категория STR_BATTLESCAPE есть, значит применится).

### 5. Магма оставляет Красную Колдунью в форме Горгоны

- `STR_ENVIRO_MAGMA` (7495, террейн CHEMTOWNHOTPURSUITS): `armorTransformations` написан вручную, 4 пары. У 12 других опасных сред (ACID_RAIN, DUST_STORM, POISON_GAS, NUKEZONE, CYDONIA×4, MARS, MOON, LABYRINTHUS_NOCTIS, COLDSPACE) — тот же набор плюс `STR_ARMOR_RED_MAGE_GORGON: STR_ARMOR_RED_MAGE_EXO` (якорь `&SECTION_ARMOR_TRANSFORM_EVA`, 7445).
- Исправление: `armorTransformations: *SECTION_ARMOR_TRANSFORM_EVA`.

### 6. Цвета окон подтверждения задаются не в том интерфейсе

- `mainMenu` (8089-8092): элементы `confirmDefaults` и `confirmVideo` (color 89). Движок берёт их из `optionsMenu` (`OptionsDefaultsState.cpp:50-53`, `OptionsConfirmState.cpp:56-60`, `OptionDetailState.cpp:54-57`, `ModConfirmExtendedState.cpp:51-54`); в `mainMenu` они лежали до коммита `bbb09780e` (2018).
  - Окна «сбросить настройки», «подтвердить видеорежим», «подтвердить смену модов» рисуются цветами мастера (138/239) вместо задуманного 89.
  - Исправление: перенести оба элемента в `optionsMenu`.
- `modsMenu` (8180-8181): `- id: button`. Движок спрашивает `button1` и `button2` (`ModListState.cpp:64-69`). Кнопки OK/Отмена остаются цвета 133 вместо 239. Переименовать в `button2`.

### 7. Коралловый остров засчитывается не в ту медаль

- UNDERSEA_MISSIONS (Diver), `missionTypeFilter` (1095): `STR_SEA_CORAL_EXIT` — первый этап, его `nextStage` — `STR_CORAL_ISLAND`. В статистику пишется последний этап, а успешно кончиться на первом нельзя — фильтр не срабатывает никогда.
- `STR_CORAL_ISLAND` стоит в INFILTRATION (Partygoer, 1088). Коралловая миссия идёт в Partygoer, не в Diver.
- Решать автору: перенести `STR_CORAL_ISLAND` в Diver или убрать мёртвый `STR_SEA_CORAL_EXIT`.

## Похоже на задумку, но стоит уточнить

- **HEAT** (7262, 7337): `STR_THIEF_ARMOR_SEA_UC → STR_PIR_TOPLESS_UC` и `STR_NEKO_THIEF_ARMOR_SEA_UC → STR_NEKO_NUDE_UC`, а SEA делает их из `STR_THIEF_ARMOR_UC` / `STR_NEKO_THIEF_ARMOR_UC`. Остальные ~90 пар симметричны. Сказывается только в многоэтапном задании «море, потом жара».
- **GROUND_OR_UNDETECTABLE** (4303): из 12 крафтов с `undetectable: true` нет `STR_CAPSULE` и `STR_SKYRANGER_SHADOW`.
- **LOCAL_CITIZENS, craftTransformations** (5047-5118): все посадочные крафты превращаются в экспедицию, кроме `STR_SKYRANGER_SHADOW`.
- **NEKO_CLASS_HERBALIST** (4092): `totalIronMan: [9999]`, не вручается ничем (`commendationName` только у OUTLAW, WARRIOR, ACE). Бонус даёт трансформация (Piratez_Transformations.rul:2886), но медали в дневнике травницы нет, у других классов есть.
- **Пороги `[1, …, 1]`** у GLOBETROTTER (3998), VALKYRIE (~4039), FALLEN (~4056): все 10 уровней сразу. Педия GLOBETROTTER пишет «Awarded once».
- **DOTS** засчитывает ещё ACADEMY_COUNSELLOR и ACADEMY_SCIENTIST, педия называет только Provost. **ROOMSERVICE** засчитывает и ванильного SNAKEMAN_ENGINEER.
- **CYDONIA_2 / CYDONIA_3** (7973, 7986) без палитры PAL_MARS, у CYDONIA и CYDONIA_SURFACE она есть. Подземная часть?
- **PLAINCLOTHES_INFILTRATION** (7573, 7578): RAGS→FURS и HUNTER→FURS, как в холодной среде.

## Мелочи

- `soldierDiaries` в `fixedUserOptions` не применяется (нет категории, `Options.cpp:201`); по умолчанию true, но если у игрока в options.cfg false, мод медали не включит. То же с `globeDetail/RadarLines/FlightPaths/AllRadarsOnBaseBuild` в рекомендованных (эффекта нет, по умолчанию true) и `maximizeInfoScreens` (движок стирает).
- `interfaces`: мёртвые элементы — `loadingText` (8201-8206, такого интерфейса в OXCE нет вовсе), `dogfight.button` и `dogfight.background` (8325, 8331), `battlescape.indicatorGreen` (8449). Эффекта нет.
- `STR_ENVIRO_COLDSPACE` (8041) не используется ни одним заданием или террейном.
- 26 `itemCategories` (MELEE, AUTO_MELEE, CARBINE, SNIPER, CANNON и 21 по типу урона — MAGIC…FOREVER) без строк и без единого предмета; в фильтрах не видны.
- `IMPORTANT_MISSIONS` (1011): заглушка — нет строки, description от ORIGINAL8, [9999].
- Дубли в SPACE allowedArmors (6910-6913): `STR_SYNTH_REFRACTOR_A_SPACE_UC`, `STR_SYNTH_CHILLER_ARMOR_A_SPACE_UC`.
- `missionRatings`: нижний порог −10000, ниже — пустой рейтинг. У месячного −999999.
- Опечатки в en-US: «Chihuaha», «Caucassus», «Cordiliera».
- `IDOL` (~3835): комментарий «per mission», критерий и педия — «in a single turn».

## Для Vitali (не для Dioxine)

- `XPZ RU-patch/Language/ru.yml:2948` (`STR_MEDAL_MAXDAKKA_UFOPEDIA`): управляющий символ 0x16 внутри текста. PyYAML файл не читает; yaml-cpp, видимо, терпит.
- Подписи слотов инвентаря в режиме цены ОВ (`":NN"` к подписи, `Inventory.cpp:282-289`) по замеру шрифтом пересекаются: «L. HAND:20» с «Q.D.:24», «HAT:30» с «WEAR:50». Глазами в игре не проверено.
- В `de.yml` мода нет `STR_BACK_PACK`, в uk/lt/hu/et/es-419 нет ни одного имени слота Пираток — видны длинные ванильные подписи.
- **Поправка к первому отчёту Dioxine**: п. 8 про `minReactionAccuracy` был неверен (см. находку 4). В новом сообщении это исправлено.

## Итог

- Самое заметное игроку: **три HWP молча остаются на базе** (находка 1) и **неко в ящике на POLIS_TERMINAL** (находка 2, опечатка уже отправлена).
- Двойной счёт в двух медалях, магма без Горгоны, цвета окон подтверждения, коралл не в той медали.
- Поправка к прошлому отчёту: `minReactionAccuracy` мёртв целиком, и бойцы игрока потеряли порог ответного огня.

Сообщение автору на английском — [piratez-globals-dm.en.txt](piratez-globals-dm.en.txt).

## Чего НЕ выяснил

- Ничего не проверено в бою. Всё — по рулсету и коду движка (наш форк OXCE 8.7.1; Пиратки требуют 8.6, поведение в проверенных местах то же).
- HWP (находка 1) — выведено из `BattlescapeGenerator.cpp`, не воспроизведено на сейве.
- Тексты педии больших медалей против их `killCriteria` не сверены: сверены только имена.
- Ограничения `armor.units` для запасной брони (MAGE_ROBE только для W и т.п.) — спрайты это или лор, не выяснял.
- Сообщения сред сверены только с en-US; `.pal` на читаемость текста не смотрел.
- Русские подписи катсцен не оценивал: русский патч переопределяет их рамки своим `EX_cutscenes.rul`.
