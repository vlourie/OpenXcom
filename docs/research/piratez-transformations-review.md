# Разбор Piratez_Transformations.rul (X-Piratez)

Файл: `Пиратки/Dioxine_XPiratez/user/mods/Piratez/Ruleset/Piratez_Transformations.rul`, 3 016 строк.
Файл прочитан скриптом, а не глазами. Рулсеты слиты так же, как их сливает движок (`tools/rul_map.py`, итог в `.index/mod/Piratez/rul/`).
Каждая трансформация сверена с текстом педии в `Language/en-US.yml`: с её собственной статьёй, со статьёй исследования из `requires` и со статьёй её бонуса.
Проверки повторяют то, что делает движок:
- `RuleSoldierTransformation::load` (`src/Mod/RuleSoldierTransformation.cpp`);
- `Soldier::isEligibleForTransformation`, `Soldier::transform`, `Soldier::calculateStatChanges` (`src/Savegame/Soldier.cpp:1675-2080`);
- `UnitStats::softLimit` (`src/Mod/Unit.h:145`);
- `SavedGame::getAvailableTransformations` (`src/Savegame/SavedGame.cpp:1955`).

**Файл не правился**: установка Пираток только читается. Все исправления ниже — предложения автору.

## Что в файле

- Одна секция `soldierTransformation`, **83 записи** и одна закомментированная (`STR_EAT_CAKE`, строка 185).
- 3 записи закрыты `requires: STR_UNAVAILABLE`: `STR_CAREER_SOLDIER`, `STR_LONE_WOLF`, `STR_THEBAN_ASSAULT_CLONE`. Их не делают в базе, их имена ставятся рекрутам через `spawnedSoldier.previousTransformations`.
- 73 записи дают бонус (`soldierBonusType`), 7 меняют тип солдата, 12 выдают свою броню, 8 требуют медалей.
- Другие файлы мода и русский патч эту секцию не трогают.

Как движок это применяет. Без этого часть находок не понять.
- Трансформация даёт **один** бонус (`soldierBonusType`). Второго поля нет.
- История пишется по **имени трансформации**. `forbiddenPreviousTransformations` и `requiredPreviousTransformations` смотрят имена, а не бонусы. Если один и тот же бонус выдают две трансформации, запрет, написанный на одну, вторую не видит.
- Потолок изменения статов (`calculateStatChanges`):
  - `upperBoundAtMaxStats` берёт **стартовый максимум** нового типа, `upperBoundAtStatCaps` — потолок тренировки. Если заданы оба, побеждает `maxStats`.
  - `upperBoundType: 0` (по умолчанию) — «динамический» режим. Тип солдата не меняется — **мягкий** потолок: рост упирается в потолок, стат выше потолка остаётся как был. Тип меняется — **жёсткий**: `min(изменение, потолок − текущее)`. Значит, **любой** стат выше потолка срезается до потолка, даже если трансформация его не трогала.
  - `upperBoundType: 1` — всегда мягкий, `2` — всегда жёсткий.
- `keepSoldierArmor` по умолчанию `false`. Без него броня уходит на склад, солдат получает броню своего типа по умолчанию.
- Изменение храбрости округляется к десяткам.

## Что проверено и чисто

| Проверка | Итог |
|---|---|
| Повторы имён, повторы ключей в записи, ключи, которых движок не читает | нет (`dup_keys.tsv`, `unknown_keys.tsv`) |
| Ссылки: исследования в `requires`, предметы, типы солдат, бонусы, медали, броня, другие трансформации | все находятся (`dangling.tsv` пуст по этой секции) |
| Каждая функция из `requiresBaseFunc` (14 штук: CULT, DOJO, BDSWAP, PSION…) даётся хотя бы одним зданием | да |
| Изменения храбрости кратны 10 | да |
| Уровни в `requiredCommendations` не выходят за длину медали | да; нумерация черепов в педии везде одна: «1st Iron Skull» = 1, «1st Silver Skull» = 4 (FUSION, DESTRUCTOR, ABYSSAL, SWIFTPAW, JUDICIAL, RED_KNIGHT) |
| Числа в педии против `flatOverallStatChange` и бонуса | совпадают у всех, кроме перечисленных ниже |
| Смена типа при `keepSoldierArmor: true` (Herbalist: Nekomimi → Nekomimi_H) | вся броня, которую носит Nekomimi, разрешена и Nekomimi_H |
| Повторяемые трансформации (нет запрета на саму себя) | 14; задуманы: Dreamlink («any number of times»), Tiger Tours, Body Swap, воскрешения. Weirdgal, Repentance, Shade Embodiment после себя меняют тип и сами себя не пускают. Исключение — Nepotism, ниже |
| Односторонние запреты (A запрещает B, B не запрещает A) | 16 пар. Реально обходимая одна — Magicienne/Workout, ниже; остальные либо задуманы (Brides требует Nepotism), либо недостижимы по типу солдата |

## Косяки

Порядок — по тому, насколько они видны игроку.

### 1. Uberization даёт только Half-Uber, а черта Null теряется

- Трансформация `STR_UBERIZATION`, строка 759: `soldierBonusType: STR_HALF_UBER`.
- Педия (`STR_UBERIZATION_UFOPEDIA`, en-US.yml:12976): «The recipients gain Half-Uber **and Null** traits which together give them: +5 Armor, +1 NV, +15 STR, +10 HP, +5 TU & MEL, −25 FRS, −5 VPWR & VSKL».
- Бонус `STR_NULL_TRAIT` (Piratez_Bonuses.rul:191) лежит без дела — прошлый разбор бонусов нашёл его как «никем не используемый». Сумма двух бонусов даёт **ровно** обещанное педией:

| | HALF_UBER (Bonuses:63) | NULL_TRAIT (Bonuses:191) | сумма | педия |
|---|---|---|---|---|
| реакция | +10 | −10 | 0 | не упомянута |
| сила воли VPWR | −10 | +5 | −5 | −5 |
| VSKL | — | −5 | −5 | −5 |
| восст. морали | −2 | +2 | 0 | не упомянуто |
| прочее (броня, NV, STR, HP, TU, MEL, FRS) | как в педии | — | как в педии | совпадает |

- Движок даёт одной трансформации один бонус, поэтому Null не выдаётся никогда. Игрок получает +10 реакции, −10 VPWR, 0 VSKL и −2 к морали за ход вместо обещанного.
- Трогать сам `STR_HALF_UBER` нельзя: его же носят рекруты Half-Uber Girl, и их педия (en-US.yml:6781) описывает его верно.

**Исправление (предложение):** завести отдельный бонус на сумму (например `STR_UBERIZED`: броня 5, NV 1, tu 5, health 10, strength 15, psiStrength −5, psiSkill −5, melee 5, mana −25, без реакции и без восстановления морали) и поставить его в `soldierBonusType`. Строки к новому бонусу — те же, что у Half-Uber.

### 2. Weirdgal Transformation срезает VSKL до 30

- Строка 216. Тип меняется на `STR_SOLDIER_W`, стоит `upperBoundAtMaxStats: true` (строка 259). `upperBoundType` не задан, значит, потолок **жёсткий**.
- `maxStats.psiSkill` у W — 30, а потолок тренировки у Gal (STR_SOLDIER, _S, _M, _V, _X) — 40. У W самой потолок тренировки 60.
- Итог: Gal, натренировавшая VSKL 31-40, после трансформации получает ровно 30. Педия и сама трансформация (`psiSkill: 3`) обещают **+3**.
- Остальные статы W не режутся: её `maxStats` не ниже потолков Gal.

**Исправление (предложение):** дописать `upperBoundType: 1`. Мягкий потолок оставит всё как было задумано, только перестанет отнимать то, что выше стартового максимума.

### 3. Repentance срезает VSKL до 10, педия говорит «cap 20»

- `STR_ANG_102`, строка 262. Тип меняется на `STR_SOLDIER_R`, потолок `upperBoundAtMaxStats: true` (строка 301), жёсткий.
- У R `maxStats.psiSkill` = 10, `statCaps.psiSkill` = 20. Педия (`STR_ANG_102_UFOPEDIA`): «Set V.SKL cap at 20».
- Остальные пункты педии совпадают с `statCaps` R **до единицы**: ACC 100, THR 80, REA 90, HP 110, BRA 100. По `maxStats` у R HP 125 и STR 100 — это стартовые, а не потолок.
- То есть педия описывает `statCaps`, а данные режут по `maxStats`. Расходится только VSKL: 10 вместо 20.

**Исправление (предложение):** `upperBoundAtMaxStats: false`, `upperBoundAtStatCaps: true`. Проверил по всем пяти исходным типам: новых срезов это не добавит, а ровно воспроизведёт педию. Если 10 задумано — поправить педию.

### 4. Cenobite Initiation требует 90 свежести, педия — 90 храбрости

- `STR_CENOBITE_TRAINING`, строка 1293: `requiredMinStats: {psiStrength: 45, mana: 90}` (mana — строка 1316).
- Педия (`STR_CENOBITE_UFOPEDIA`, en-US.yml:12972): «Requires 45 VPWR and **90 BRA**».
- Там же: «Repentias, Lokk'Naars and Damsels only». В данных есть ещё `STR_SOLDIER_LAMIA`.

**Исправление (предложение):** `bravery: 90` вместо `mana: 90` — или педию под данные. Ламий дописать в педию либо убрать из списка.

### 5. Brides to the Queen: восстановление энергии вместо морали

- Бонус `STR_BRIDE` (Piratez_Bonuses.rul:599): `recovery: energy +1, stun +1`.
- Педия (`STR_BRIDE_UFOPEDIA`, en-US.yml:2880): «+1 **Morale** and Stun regen». Там же: «increases their fanaticism» — это скорее про мораль.

**Исправление (предложение):** `recovery: morale: flatOne: 1` вместо `energy`. Или «Energy» в педии.

### 6. Wholesome Training: тренировка и бонус не те, что в педии

- `STR_BREAD_AND_FISHES_TRAINING`, строка 1432. Педия (`STR_BREAD_AND_FISHES_UFOPEDIA`, en-US.yml:12970).

| | данные | педия |
|---|---|---|
| тренировка (`flatOverallStatChange`, строка 1471) | HP +15, **STA +25**, THR +5, **STR +10** | HP +15, **STA +20**, **TU +10**, THR +5 |
| восст. морали (бонус `STR_BREAD_AND_FISHES_BONUS`, Bonuses:540) | **+1** | **+2** |

- Остальное в бонусе совпадает: HP +8, STA и FRS +6, STR +4, броня +1, энергия −2.

**Исправление (предложение):** решить, что верно, и свести. Если верна педия: `stamina: 20`, `tu: 10` вместо `strength: 10`, морали `flatOne: 2`.

### 7. Magicienne и Workout for Catgirls исключают друг друга только в одну сторону

- `STR_MAGICIENNE_TRAINING` (строка 1171) запрещает `STR_NEKO_BODYBUILDER_TRAINING`. А Workout (строка 2931) запрещает только Swiftpaws и себя.
- Итог: Нэко, прошедшая Workout, Magicienne получить не может. Нэко, прошедшая Magicienne, — на Workout идёт спокойно. Типы для обхода: Nekomimi, Nekomimi_O, Nekomimi_W.
- Рядом Gladiatorial Training и Magicienne запрещают друг друга с обеих сторон, так что задумка — взаимное исключение.

**Исправление (предложение):** дописать `STR_MAGICIENNE_TRAINING` в `forbiddenPreviousTransformations` у Workout.

### 8. Shade Embodiment выдаёт Zombie Gal под другим именем, и запреты его не видят

- `STR_SHADE_EMBODIMENT`, строка 2632: тень становится Gal (`STR_SOLDIER`) с бонусом `STR_ZOMBIGAL`. Так и в педии (en-US.yml:14342): «a Lunatic with the Zombie Gal augmentation».
- Но в истории у неё записано `STR_SHADE_EMBODIMENT`, а не `STR_ZOMBIFICATION`. Прежние записи истории стёр `reset: true` при вызове тени.
- Семь трансформаций запрещают `STR_ZOMBIFICATION`, но не `STR_SHADE_EMBODIMENT`: Weirdgal, Repentance, Lifeforce Focusing (Gals), Wholesome, Sun Martial Rituals, Sivalinga Resurrection и закрытый Theban Clone. Воплощённая тень проходит их все. Так получаются, например, зомби-Weirdgal и зомби с Sun Rituals. А Сивалинга поднимает её, хотя педия Сивалинги говорит «zombified can't be raised».
- С другой стороны, `STR_ZOMBI_REVIVAL` и `STR_BODY_SWAP` **требуют** `STR_ZOMBIFICATION`. Воплощённой тени они недоступны, хотя по бонусу она Zombie Gal.

**Исправление (предложение):**
- дописать `STR_SHADE_EMBODIMENT` рядом с `STR_ZOMBIFICATION` во все семь списков запретов;
- для Zombie Revival и Body Swap: `requiredPreviousTransformations` в движке — это «И», а не «ИЛИ». Нужны копии этих двух записей с требованием `STR_SHADE_EMBODIMENT`. Или сказать в педии, что воплощённым это недоступно.

## Похоже на задумку, но стоит уточнить

- **Капсула стазиса остаётся после воскрешения.**
  - `STR_ASSIGN_STASIS_POD` (строка 2388) даёт бонус `STR_STASIS_POD_ASSIGNED` (Bonuses:352): −5 REA, −3 HP, +3 FRS и **−5 TU восстановления за ход**. Строки педии у бонуса нет, штраф нигде не описан.
  - Оба воскрешения (строки 2428 и 2468) требуют эту трансформацию в истории, но не убирают её. После воскрешения штраф −5 TU за ход остаётся навсегда, а при следующей смерти девушку можно воскресить снова **без новой капсулы**.
  - Если капсула должна расходоваться, в движке (OXCE 8.6) для этого есть `removeTransformations: [STR_ASSIGN_STASIS_POD]`: снимает и запись истории, и её бонус.
- **Chort Binding режет REA до 80 и VSKL до 10.**
  - Строка 2760. Тип меняется на Chort, `upperBoundAtMaxStats: true`, жёстко.
  - Лок'нар с REA 140 или Нэко со 125 получают 80. Любой VSKL выше 10 становится 10, хотя потолок тренировки у Chort — 20.
  - REA 80 совпадает с потолком Chort, это может быть задумано. VSKL — та же история, что в находке 3.
- **Repentia в списке Chort Binding не пройдёт никогда.** `minRank: 1` (строка 2788), а у `STR_SOLDIER_R` `allowPromotion: false`: Repentance сбрасывает звание, повысить нельзя. Либо убрать R из списка, либо снять `minRank` для неё отдельной записью.
- **Nepotism повторяется и каждый раз даёт +1 FRS навсегда.**
  - Строка 2. Запрета на саму себя нет, `flatOverallStatChange: mana 1`.
  - Педия (en-US.yml:2878): «they will not get any extra benefit from repeated Neppings». Бонус +15 и правда не складывается, а +1 копится до потолка — по $100k за единицу.
  - Если +1 — только чтобы экран трансформации не был пустым, стоит убрать повтор (`forbiddenPreviousTransformations: [STR_NEPOTISM]`) или единицу.
- **Три тренировки снимают броню.** У `STR_DREAMLINK_TRAINING` (709), `STR_REVOLUTIONARY_TRAINING` (789) и `STR_SADIST_TRAINING` (1356) нет `keepSoldierArmor`. У остальных 76 он стоит. Броня уходит на склад, солдат выходит в броне по умолчанию. Для Ritual of Rebirth это может быть образом («born again»), для двух других похоже на пропуск.
- **Syn Acceptance отнимает 75 % набранной свежести.** Строка 1661, `percentGainedStatChange: mana −75`. В педии только «for better or worse». Экран трансформации это покажет, но стоит строки в педии.

## Мелочи

- **Zombiefication:** `STR_SOLDIER_V` в `allowedSoldierTypes` дважды (строки 2519-2520). Похоже, вместо второго имелся в виду другой тип.
- **Воскрешения одевают собак в BOXX_ARMOR.** Sleeping Beauty Revival (обе) и Sivalinga Resurrection пускают `STR_SOLDIER_DOGE` и `STR_SOLDIER_BLOODOGE` и выдают `BOXX_ARMOR`. В `units` у этой брони собак нет.
- **Педия не перечисляет всех, кто допущен:**
  - Judicial Education: «Gnomes, Ogres and Heroes», в данных ещё Lamia;
  - Damsel Magicienne: «Damsels… Lokk'Naars are also allowed», в данных ещё Gnome и четыре типа Nekomimi.
- **Personal Attention:** педия перечисляет только «+1 Freshness». Тренировка +3 к девяти статам (строка 49) не упомянута. Она видна на экране трансформации, но в педии её нет.

## Итог

- Файл аккуратный: 83 записи без повторов, без битых ссылок и незнакомых ключей. Все требования к медалям и зданиям выполнимы. Педия у пяти десятков трансформаций совпадает с данными до единицы.
- Главный баг — **Uberization без черты Null** (находка 1): педия прямо называет две черты и их сумму, а вторая черта лежит в бонусах без дела.
- Два случая, где смена типа с жёстким потолком **отнимает** VSKL, хотя педия обещает рост или другой потолок: Weirdgal и Repentance (2, 3).
- Три расхождения педии и чисел: Cenobite, Brides, Wholesome (4-6).
- Две дыры в запретах: Magicienne/Workout и Shade Embodiment (7, 8).

Сообщение автору на английском — [piratez-transformations-dm.en.txt](piratez-transformations-dm.en.txt).

## Чего НЕ выяснил

- Ничего не проверено в игре, всё — по рулсету и коду движка. Срезы в находках 2 и 3 выведены из `calculateStatChanges`. Самая дешёвая проверка — экран трансформации: он показывает min/max изменения тем же кодом (`SoldierTransformationState.cpp:248`). Взять Gal с VSKL 35 и открыть Weirdgal.
- Достижимость `requiredMinStats` сверх потолка типа не оценивал. Условия считаются с бонусами (`includeBonusesForMinStats: true`), а бонусы у каждого солдата свои. Например, Hero Ascension требует STR 80 при потолке Hero 60 — это возможно только бонусами, и педия так и говорит («who can boast»).
- Не проверено, получаются ли предметы из `requiredItems` (Captain's 11 Token, Harem Collar и другие). Проверено только, что такие предметы есть.
- Рекрутов с готовой историей (`spawnedSoldier.previousTransformations`) разбирал прошлый отчёт по бонусам: там 42 пары, все закрыты. Здесь заново не проверял.
