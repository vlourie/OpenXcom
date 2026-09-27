# Разбор Piratez_Events.rul (X-Piratez)

Файл: `Пиратки/Dioxine_XPiratez/user/mods/Piratez/Ruleset/Piratez_Events.rul`, 13 211 строк.
Файл прочитан скриптом, а не глазами. Рулсеты Пираток слиты так же, как их сливает движок (`tools/rul_map.py`, итог в `.index/mod/Piratez/rul/`). Текст каждого события сверен с данными по `Language/en-US.yml` Пираток и по `ru.yml` русского патча.
Проверки повторяют то, что делает движок:
- `RuleEvent::load` (`src/Mod/RuleEvent.cpp`);
- `RuleEventScript::load` (`src/Mod/RuleEventScript.cpp`);
- ежемесячный запуск скриптов в `GeoscapeState.cpp`, около 4055-4225;
- `SavedGame::spawnEvent`, `addGeneratedEvent` и `wasEventGenerated` (`src/Savegame/SavedGame.cpp`, 2822-2840 и 3213);
- `SavedGame::addFinishedResearch` с начислением очков (1534);
- снятие события при показе (`GeoscapeState.cpp:2057`);
- `GeoscapeEventState::eventLogic` (`src/Geoscape/GeoscapeEventState.cpp`, 137-518).

**Файл не правился**: установка Пираток только читается. Все исправления ниже — предложения автору.

## Что в файле

- Две секции:
  - `events`: **792 события**, строки 1-6560;
  - `eventScripts`: **643 скрипта**, строки 6561-13211.
- Другие моды события не трогают: ни русский патч, ни прочие моды из установки.

Как движок это применяет. Без этого часть находок не понять.
- Скрипты перебираются раз в месяц, в первый день.
  - Сначала условия: `firstMonth`/`lastMonth`, очки, деньги, сложность. Затем `researchTriggers`, `itemTriggers`, `facilityTriggers` и триггеры баз, потом `executionOdds`.
  - Прошедший скрипт порождает события **из всех трёх списков сразу**: `oneTimeSequentialEvents`, `oneTimeRandomEvents` и одно событие по весам `eventWeights`.
- `wasEventGenerated` охраняет только разовые списки. Отметка ставится в момент порождения, а не показа. Повторяемое событие из `eventWeights` ничем не охраняется: оно выпадет, пока проходят условия скрипта.
- Событие ждёт показа `timer + RNG(0, timerRandom)` минут, округлённо до 30, но не меньше 60. У 63 событий это `60 + 43400`, то есть до 30,2 суток.
- При показе событие снимается, если исследование из его `interruptResearch` уже сделано. **Больше `interruptResearch` нигде не читается**, у `RuleEventScript` такого ключа нет.
- `eventLogic` при показе:
  - `points` идут в активность региона, если задан `regionList`, иначе в общий счёт;
  - из `researchList` берётся одна ещё не открытая тема. Она открывается с начислением **своих** `points` исследования поверх очков события.

## Что проверено и чисто

| Проверка | Итог |
|---|---|
| Повторы имён событий и скриптов, повторы ключей внутри записи | нет |
| Ключи, которых движок не читает | только два `interruptResearch` на скриптах, см. косяк 1 |
| Битые ссылки: исследования, предметы, регионы, солдаты, крафты, постройки, события | нет (`.index/mod/Piratez/rul/dangling.tsv`) |
| Заголовок и описание есть в en-US Пираток и в `ru.yml` русского патча | у всех 792 |
| Каждое событие достижимо хоть из одного скрипта | да |
| Скрипт, у которого все веса нулевые | нет |
| Месяцы в `eventWeights` по возрастанию; наименьший ключ ≤ `firstMonth`, иначе поиск по весам уходит за начало | да, у всех |
| `min*` > `max*` (очки, деньги, сложность), `executionOdds` вне 0-100 | нет |
| Фоны `background`: 321 разный, 315 из `extraSprites` мода, файлы на диске есть | все на месте |
| Музыка `music` | вся описана в `musics` |
| `city: true` у региона без городов, `{0}` в тексте без `regionList` | нет |
| `interruptResearch` события, которое требует сам скрипт (событие гасло бы всегда) | нет |

## Косяки

### 1. `interruptResearch` поставлен на скрипт — движок его выбрасывает

Скрипты ниндзя-эскалации:
- `STR_NINJAS_ESCALATION` (строка 11474, ключ на 11482): `interruptResearch: STR_NINJA_ESCALATION_4`;
- `STR_NINJAS_AT_BAY` (строка 11484, ключ на 11491): `interruptResearch: STR_NINJA_ESCALATION_6`.

`RuleEventScript::load` этот ключ не читает, так что оба молча пропадают (`unknown_keys.tsv`). Сами события его не имеют:
- `STR_NINJAS_ESCALATION` (4616): +500 очков и `STR_NINJA_ESCALATION_4`, скрипт 33 % в месяц;
- `STR_NINJAS_AT_BAY` (4623): +100 каждый месяц, пока нет `STR_NINJA_ESCALATION_6`. Текст говорит, что равновесие кончится, «как только мы отобьём такую атаку».

Те же исследования даёт и победа в бою: развёртывания `STR_NINJA_APC_RAID_SITE` (`Piratez_Factions.rul:83546`, ESC_4) и `STR_NINJA_CRAWLER_RAID_GOVT` (`:83644`, ESC_6). Значит, событие, порождённое в начале месяца, может прийти **после** победы. Игрок отбил налёт, а ему ещё раз «+100, равновесие держится» или «+500, эскалация».

Судя по всему, Dioxine хотел именно `interruptResearch`, но положил его не туда.

**Исправление (предложение):** перенести ключ со скриптов на события.
```yaml
  - name: STR_NINJAS_ESCALATION          # 4616
    interruptResearch: STR_NINJA_ESCALATION_4
  - name: STR_NINJAS_AT_BAY              # 4623
    interruptResearch: STR_NINJA_ESCALATION_6
```
Со скриптов (11482, 11491) ключ убрать.

### 2. `STR_BOUNTY_HUNTS_LATE` в первый месяц приходит дважды

Скрипт `STR_BOUNTY_HUNTS_LATE` (6582) держит одно и то же событие в двух списках:
```yaml
    oneTimeRandomEvents:
      STR_BOUNTY_HUNTS_LATE: 100
    eventWeights:
      0:
        STR_BOUNTY_HUNTS_LATE: 100
```
Движок порождает из обоих списков в одном прогоне. В первый месяц после `STR_CAPTAINS_RANK_02` игрок получает два окна «A Most Brilliant Idea» и −25 дважды. Дальше разовая копия уже отмечена, и работает только повторяемая.

`interruptResearch: STR_BOUNTY_HUNTING` у события (25) есть, поэтому после открытия охоты за головами обе копии гаснут как надо. Беда только в двойном первом месяце.

**Исправление (предложение):** оставить один список. Если ежемесячное напоминание задумано, убрать `oneTimeRandomEvents`. Если нет, убрать `eventWeights`.

### 3. Колдунья из пустошей и «Aurora's New Toy» могут прийти вдвоём

Событие `STR_WASTELAND_SORCERESS` (4481) порождают два скрипта. Оба гасят себя одним и тем же исследованием, которое даёт событие:

| Скрипт | Строка | С месяца | Шанс |
|---|---|---|---|
| `STR_WASTELAND_SORCERESS` | 11109 | 5 | 23 % |
| `STR_WASTELAND_SORCERESS_ACCEL` | 11119 | 10 | 33 % |

Условия у скриптов одинаковые (`STR_WEIRDNESS: true`, `STR_WASTELAND_SORCERESS: false`), друг друга они не исключают. С десятого месяца оба срабатывают в один месяц с вероятностью 0,23 × 0,33 ≈ 7,6 %. Это примерно **16 %** от всех месяцев, когда она вообще приходит. `interruptResearch` у события нет, поэтому показываются обе копии. Игрок видит два окна и получает **два комплекта**: посох, кошель, эзотерику, медальон, мантию и бельё.

Соседнее `STR_BLESSINGS` (4490) устроено так же, но у него `interruptResearch: STR_WASTELAND_PRIESTESS` есть, и дубль гаснет. У `STR_PSI_INITIATION_EVENT` то же самое. Похоже, у колдуньи ключ просто забыт.

То же у `STR_TEC_EVENT_I_HAVE_DR_X` (4437): скрипты `STR_TEC_EVENT_I_HAVE_DR_X` (8560, 33 %) и `_DUEL` (8571, 23 %), общее условие `STR_GDX_053: false`. Здесь дубль — это только второе окно, без предметов.

**Исправление (предложение):**
```yaml
  - name: STR_WASTELAND_SORCERESS        # 4481
    interruptResearch: STR_WASTELAND_SORCERESS
  - name: STR_TEC_EVENT_I_HAVE_DR_X      # 4437
    interruptResearch: STR_GDX_053
```

### 4. Повторяемое событие, закрытое своим исследованием, может выпасть второй раз в следующем месяце

Это общий случай, частный которого — косяк 3.
- 110 повторяемых событий открывают исследование, и скрипт выключается этим же исследованием (`researchTriggers: X: false`). Задумано «одно событие, пока X не открыто».
- `interruptResearch` стоит только у 8 из них: CAPTAIN_PERSONALITY_AUTOCHOICE_*, GDX_EVENT_ORDERS_1/2, TEC_EVENT_WARNING, MUTANT_COMPLAINT_REMINDER, BLESSINGS, PSI_INITIATION_EVENT.

Исследование открывается только в момент **показа**. При таймере `60 + 43400` окно может прийти через 30,2 суток, то есть позже начала следующего месяца. Тогда в первый день следующего месяца X ещё не открыто, скрипт снова проходит и порождает вторую копию. Без `interruptResearch` она потом честно показывается.

Вероятность на одно порождение:
- в среднем около 0,8 %;
- если событие порождено 1 февраля, **7,2 %**: в феврале 28 дней, а таймер дотягивает до 30.

Под риском **57** пар «скрипт — событие». Редко, но дубль повторяет всё: очки, деньги, предметы. Самые дорогие:

| Событие | Строка | Что повторится |
|---|---|---|
| `STR_CBT_TOURNAMENT_CHALLENGER_NINJA_DEFEAT` | 2859 | +2500, +$500 000, предметы |
| `STR_CBT_TOURNAMENT_CHALLENGER_OGRESS_WIN` | 2913 | +3000, +$500 000, предметы |
| `STR_CBT_TOURNAMENT_WIN` | 2812 | +1000, +$250 000, предметы (пять скриптов: _00, _01, _2, _10, _11) |
| `STR_CLEO_CHALLENGE` | 4904 | +$250 000 |
| `STR_CODEX_RED/GRAY/GREEN_AWAKENS` | 4766 / 4776 / 4785 | предметы кодекса |
| `STR_GDX_150` | 4198 | +500 |
| `STR_NINJAS_ESCALATION` | 4616 | +500 (см. косяк 1) |
| `STR_INTERSTELLAR_ASTROROCK_EVENT_SILENCE` | 3556 | −1000, −$100 000 |
| `STR_ALERT_COMMS_DISRUPTION` | 4338 | −500 |
| `STR_TEC_EVENT_PRINCESS_IS_IN_ANOTHER_CASTLE` | 4407 | −300 |

Полный список — в конце файла.

**Исправление (предложение):** тот же приём, что уже стоит у BLESSINGS и PSI_INITIATION. Каждому такому событию добавить `interruptResearch: <его же тема из researchList>`. Вторая копия тогда гаснет при показе. Поведение первой копии не меняется: при показе тема ещё не открыта.

### 5. Число в тексте не совпадает с данными

Текст события прямо называет очки или деньги, а данные дают другое. «Данные» — это `points`/`funds` события. Если событие открывает исследование со своими `points`, они указаны отдельно: текст Dioxine обычно называет только очки события.

| Событие | Строка | Текст | Данные | Вероятно |
|---|---|---|---|---|
| `STR_SOREDUMB_PIRATEZ` | 1553 | +$70k | `funds: 75000` | одно из двух |
| `STR_NORED_STOIC` | 2028 | −$75k | `funds` нет, `points: 75` | деньги забыты или стоят очками |
| `STR_CBT_TOURNAMENT_LOSE_BAD` | 2790 | +1000 Infamy | `points: 100` | лишний ноль в тексте (у `_LOSE`, 2801, текст и данные — 300) |
| `STR_CBT_TOURNAMENT_WIN` | 2812 | +700 Infamy | `points: 1000`, исследование +500 | текст устарел |
| `STR_RAGS_FOR_FREAKS` | 3040 | +5 Infamy | `points: -5` | знак |
| `STR_REVOLUTIONARY_MISSING_FUNDS_C` | 3175 | −$650k | `funds: -65000` | потерян ноль в данных: у B −300k, у D −1,5M |
| `STR_MRSHAN_WARRIOR_EVENT` | 3370 | +250 Infamy | `points: 200` | одно из двух |
| `STR_MRSHAN_FIGHTER_EVENT` | 3432 | +300 Infamy | `points: 200` | одно из двух |
| `STR_EARTHQUAKE_SOREASS` | 3674 | $50,000 | `funds: -65000` | одно из двух |
| `STR_GDX_EVENT_VAMPIRE_KISS` | 4134 | −250 Infamy | `points: -300` | одно из двух |

**Исправление (предложение):** выровнять текст или данные. Где «вероятно» указывает сторону, начать с неё. Самое заметное — `REVOLUTIONARY_MISSING_FUNDS_C`: в десять раз дешевле, чем обещано.

## Похоже на задумку, но стоит спросить

- **`STR_WIZ_128` «Red Mage's Gift» (4291).** Три скрипта: `STR_WIZ_128_35` (8373), `_45` (8383) и `_ASC30` (8393), каждый 50 %.
  - Каждый требует, чтобы в базе лежал свой вариант Красного Мага (`itemTriggers`).
  - Ни один не гасится исследованием `STR_WIZ_128` из `researchList` события.
  - Итог: пока Маг сидит в базе, подарок (предмет `STR_WIZ_128`) приходит каждый второй месяц.
  - Если в базе два варианта, пройти могут два скрипта сразу — два подарка в месяц.
  - Если подарок задуман один раз, нужно `STR_WIZ_128: false` в `researchTriggers` всех трёх скриптов или `interruptResearch: STR_WIZ_128` на событии.
- **Повторяемые события без закрытия** выглядят задуманными: `TEC_EVENT_BERSERKER_*` (8601-8630, −5000…−30000 каждый месяц до `STR_TEC_BASE_DONE`, `interruptResearch` стоит), напоминания, налоги. Они перечислены в выводе проверки, но в косяки не вынесены.
- **Пять событий `STR_CAPTAIN_PERSONALITY_AUTOCHOICE_*` и ещё два** (`STR_PERSONAL_LABS_LATE`, `STR_WIZ_EVENT_WHERE_FOUNTAIN`) закрываются `interruptResearch`, которого их скрипт не проверяет. Скрипт продолжает порождать событие каждый месяц, а движок каждый раз снимает его при показе. Лишняя работа, но игрок ничего не видит — не баг.

## Итог

Файл в хорошем состоянии: ни одной битой ссылки, пропавшей строки, фона или мелодии на 792 события и 643 скрипта. Все находки — про то, **сколько раз** событие приходит:
- косяк 1 (ниндзя) — явная ошибка: ключ положен не туда;
- косяки 2 и 3 — дубли, которые игрок увидит;
- косяк 4 — редкий дубль, который закрывается одной строкой на событие;
- таблица из косяка 5 — десять расхождений текста и данных.

## Чего НЕ выяснил

- В игре ничего не проверялось, выводы только из рулсета и кода движка.
- Вероятности дублей посчитаны по формуле таймера, а не по прогону.
- Числа в текстах `ru.yml` русского патча с данными не сверялись. Проверено только, что строки есть. Если в переводе стоят другие числа, чем в en-US, таблица косяка 5 для русского игрока будет другой.
- Не выяснял, задуман ли повторный подарок `STR_WIZ_128`.

## Список: 57 пар «скрипт → событие» с риском дубля в следующем месяце

Вероятность — на одно порождение с учётом `executionOdds` скрипта: средняя и для порождения 1 февраля.

| Скрипт | Событие | Строка события | Среднее | Февраль |
|---|---|---|---|---|
| STR_ZANDER_CYDONIA_READY_EVENT | STR_ZANDER_CYDONIA_READY_EVENT | 789 | 0,80 % | 7,2 % |
| STR_WIZ_EVENT_CONTACT | STR_WIZ_EVENT_CONTACT | 4232 | 0,80 % | 7,2 % |
| STR_WIZ_020 | STR_WIZ_020 | 4277 | 0,80 % | 7,2 % |
| STR_TEC_EVENT_STRANGE_LIGHTS | STR_TEC_EVENT_STRANGE_LIGHTS | 4360 | 0,80 % | 7,2 % |
| STR_TEC_EVENT_STRANGER | STR_TEC_EVENT_STRANGER | 4352 | 0,80 % | 7,2 % |
| STR_TEC_EVENT_PRINCESS_IS_IN_ANOTHER_CASTLE | то же | 4407 | 0,80 % | 7,2 % |
| STR_TEC_180 | STR_TEC_180 | 4422 | 0,80 % | 7,2 % |
| STR_TEC_176 | STR_TEC_176 | 4415 | 0,80 % | 7,2 % |
| STR_NEKOMIMI_CAT_PATH_SECRET_DEAL | то же | 3485 | 0,80 % | 7,2 % |
| STR_LOC_DEMON_BAIT | STR_LOC_DEMON_BAIT | 6390 | 0,80 % | 7,2 % |
| STR_GDX_150 | STR_GDX_150 | 4198 | 0,80 % | 7,2 % |
| STR_GDX_114 | STR_GDX_114 | 4184 | 0,80 % | 7,2 % |
| STR_GDX_113 | STR_GDX_113 | 4177 | 0,80 % | 7,2 % |
| STR_GDX_112 | STR_GDX_112 | 4171 | 0,80 % | 7,2 % |
| STR_CODEX_RED_AWAKENS | STR_CODEX_RED_AWAKENS | 4766 | 0,80 % | 7,2 % |
| STR_CODEX_GREEN_AWAKENS | STR_CODEX_GREEN_AWAKENS | 4785 | 0,80 % | 7,2 % |
| STR_CODEX_GRAY_AWAKENS | STR_CODEX_GRAY_AWAKENS | 4776 | 0,80 % | 7,2 % |
| STR_CBT_TOURNAMENT_CHALLENGER_NINJA_DEFEAT | то же | 2859 | 0,80 % | 7,2 % |
| STR_CAPTAINS_11 | STR_CAPTAINS_11 | 806 | 0,80 % | 7,2 % |
| STR_DES_001 | STR_DES_001 | 4749 | 0,72 % | 6,5 % |
| STR_SIVALINGA_RESURRECTION_EVENT | то же (таймер 20000+23000) | 4508 | 0,67 % | 8,0 % |
| STR_WIZ_101 | STR_WIZ_101 | 4240 | 0,64 % | 5,8 % |
| STR_CBT_TOURNAMENT | STR_CBT_TOURNAMENT | 2783 | 0,64 % | 5,8 % |
| STR_BLESSINGS_2B | STR_WASTELAND_PRIESTESS_2 | 4500 | 0,62 % | 5,6 % |
| STR_SP_AMBER_EVENT | STR_SP_AMBER_EVENT | 4547 | 0,60 % | 5,4 % |
| STR_JACKS_DUNGEON_EVENT | STR_JACKS_DUNGEON_EVENT | 4934 | 0,60 % | 5,4 % |
| STR_DEEP_TUNNELS_EVENT | STR_DEEP_TUNNELS_EVENT | 696 | 0,60 % | 5,4 % |
| STR_CLEO_CHALLENGE | STR_CLEO_CHALLENGE | 4904 | 0,60 % | 5,4 % |
| STR_WIZ_009 | STR_WIZ_009 | 4270 | 0,56 % | 5,1 % |
| STR_LFS_001 | STR_LFS_001 | 4696 | 0,53 % | 4,8 % |
| STR_ALERT_COMMS_DISRUPTION | STR_ALERT_COMMS_DISRUPTION | 4338 | 0,48 % | 4,3 % |
| STR_TEC_EVENT_ULTIMATUM | то же (таймер 2500+40000) | 4368 | 0,45 % | 5,5 % |
| STR_LFS_002 | STR_LFS_002 | 4704 | 0,43 % | 3,9 % |
| STR_CLEO_CATGIRLS | STR_CLEO_CATGIRLS | 4925 | 0,42 % | 3,8 % |
| STR_TEC_EVENT_GROWING_UP | STR_TEC_EVENT_GROWING_UP | 4429 | 0,40 % | 3,6 % |
| STR_CBT_TOURNAMENT_CHALLENGER_OGRESS_CHANCE | STR_CBT_TOURNAMENT_CHALLENGER_OGRESS_WIN | 2913 | 0,40 % | 3,6 % |
| STR_CBT_TOURNAMENT_CHALLENGER_OGRESS | то же | 2884 | 0,40 % | 3,6 % |
| STR_CBT_TOURNAMENT_CHALLENGER_NINJA | то же | 2851 | 0,40 % | 3,6 % |
| STR_CBT_TOURNAMENT_CHALLENGER_BLACK_DRAGON_FIGHT | STR_CBT_TOURNAMENT_CHALLENGER_BLACK_DRAGON_WIN | 2949 | 0,40 % | 3,6 % |
| STR_CBT_TOURNAMENT_CHALLENGER_BLACK_DRAGON | то же | 2931 | 0,40 % | 3,6 % |
| STR_BLK_001 | STR_BLK_001 | 4735 | 0,40 % | 3,6 % |
| STR_LFS_003 | STR_LFS_003 | 4712 | 0,34 % | 3,0 % |
| STR_BLESSINGS_2 | STR_WASTELAND_PRIESTESS_2 | 4500 | 0,34 % | 3,0 % |
| STR_WASTELAND_SORCERESS_ACCEL | STR_WASTELAND_SORCERESS | 4481 | 0,27 % | 2,4 % |
| STR_TEC_EVENT_I_HAVE_DR_X | STR_TEC_EVENT_I_HAVE_DR_X | 4437 | 0,27 % | 2,4 % |
| STR_NINJAS_ESCALATION | STR_NINJAS_ESCALATION | 4616 | 0,27 % | 2,4 % |
| STR_NEC_001 | STR_NEC_001 | 4720 | 0,27 % | 2,4 % |
| STR_CBT_TOURNAMENT_00, _01, _2, _10, _11 | STR_CBT_TOURNAMENT_WIN | 2812 | 0,27 % | 2,4 % |
| STR_DUMBASS_MINOTAUR | STR_DUMBASS_MINOTAUR | 797 | 0,19 % | 1,7 % |
| STR_WASTELAND_SORCERESS | STR_WASTELAND_SORCERESS | 4481 | 0,18 % | 1,7 % |
| STR_TEC_EVENT_I_HAVE_DR_X_DUEL | STR_TEC_EVENT_I_HAVE_DR_X | 4437 | 0,18 % | 1,7 % |
| STR_NEWS_FROM_CANADA | STR_NEWS_FROM_CANADA | 4392 | 0,18 % | 1,7 % |
| STR_INTERSTELLAR_ASTROROCK | STR_INTERSTELLAR_ASTROROCK_EVENT_SILENCE | 3556 | 0,18 % | 1,7 % |

Строка `STR_CBT_TOURNAMENT_00, _01, _2, _10, _11` — это пять пар, отсюда 57. Проверки лежат в блокноте сессии (`ev_check*.py`) и в проект не вынесены.
