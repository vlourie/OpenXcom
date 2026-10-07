# X-Com Files на нашей сборке: что работает, что нет (02.10.2026)

Опыт к MULTIMOD §5.4 и этапу 0 (`docs/portal/MULTIMOD.md`). Сборка `build-release/bin/openxcom.exe`
(OXCE-HD 8.7.1), X-Com Files **4.2** из `E:\Additional mods\openxcom_xfiles_42.zip` (там же Dark Geoscape и
XCF Cyrillic Names). Все прогоны невидимые (`ai_probe.Hidden` + SDL dummy), каждый в своей папке `-user/-cfg`,
моды по соединению; установка Пираток не тронута.

Как повторить: `tools/compat/xcf_probe.py setup`, затем `run xcf`, `run piratez`, `run xcf_hd`
(экспорт всех наборов `OXCE_HD_EXPORT=all`, **`lazyLoadResources false`** — иначе выгружаются только
загруженные наборы, R-182), потом `xcf_compare.py` и `xcf_ui.py`. Рабочая папка — `%TEMP%\xcf_compat`
(`XCF_WORK`). Таблицы: `docs/research/data/xcf_hd_compare.tsv`, `xcf_hd_ui.tsv`.

## 1. Сама игра

| Что | Итог |
|---|---|
| metadata | `id: x-com-files`, `isMaster: true`, `master: xcom1`, `requiredExtendedVersion: "8.6"`, версия 4.2 |
| Загрузка на нашем движке | без единой ошибки; 489 наборов, 103 126 кадров, 23 с с полной загрузкой ресурсов |
| Данные | ванильный UFO (`xcom1`), TFTD не нужен |
| Подмоды в архиве | Dark Geoscape (`master: x-com-files`), XCF Cyrillic Names (`master: x-com-files`) |
| Русский | `Language/ru.yml` в самом моде |
| Наши строки движка | `STR_MY_REPORTS`, `STR_LAUNCHER` — «not found in ru»: на чужой игре пункты меню отчётов и лаунчера будут сырыми ключами. Строки лежат не там, где их видит любая игра (сверить с `bin/common/Language/OXCE`) |

## 2. Наши моды в X-Com Files

| Мод | `master` | Итог |
|---|---|---|
| Танк с башней (`piratez_tank_turret`) | `piratez` | **не включится**: движок отказывает, `missing master mod piratez`. Танк — броня и наборы Пираток, в XCF их нет |
| Кися и Брыся (`kisya_brysya_sisters`) | `piratez` | **не включится**: события, ранги и бойцы Пираток |
| Apple Processing | `piratez` | **не включится** |
| RU-патч, Cities Lore, Cyrillic/Czech Names, OAK | `piratez` | не включатся; у XCF свой русский и свои Cyrillic Names |
| `intro_voice` | `"*"` | включится, но это голос вступления Пираток — в XCF ему не место |
| `hd` | `"*"` | **включится и частично нарисует чужое** — ниже |

Значит, «танк, Кися и т.д.» для X-Com Files надо делать отдельными модами под `master: x-com-files`
(своя броня, свои события), переносом не обойтись.

## 3. HD-пак (`hd`) поверх X-Com Files — замер по кадрам

HD-кадр ищется по имени набора и номеру кадра, сверки с классическим кадром нет (MULTIMOD §5.4).
Сравнены итоговые классические кадры обеих игр там, где у `hd` есть пак:

| Вид | Наборов с HD | XCF их не использует | Совпадают кадр в кадр | **Отличаются** |
|---|---|---|---|---|
| Спрайты (юниты, эффекты) | 703 | 676 | 17 наборов, 1 723 кадра | **10 наборов, 893 кадра** |
| Террейн | 626 | 388 | 211 наборов, 10 371 кадр | **27 наборов, 314 кадров (+8 отсутствуют)** |
| Картинки интерфейса | — | 1 945 имён не найдено | — | движок сопоставил **33** имени; по файлам подтверждено разных не меньше 4 (статьи педии `DragonCalling`, `Hybrid_Agent_CPAL`, `Maid`, `VAMPIRE_KNIGHT`) |

Где HD нарисует Пиратки поверх другой картинки XCF (больше всего кадров): `ZOMBIE_TROOPER_1` 275,
`ZOMBIE_TROOPER_2` 203, `TOMB_GUARD` 169, `DOGE` 75, `WASPITE` 51, `SHAMBLER` 41, `SMOKE` 31,
`GIANT_BEETLE` 28, `ABOMINATION` 12, `X1` 8; террейн `XB2BR` 62, `U_WALL02` 44, `MILEXT` 29,
`DUNGEON_VILLA` 25, `U_WALL02GOLD` 24, `SHOGG_VILLAGE_PODS` 24, `WHITEBASES01` 20.

Что совпадает и годится как есть: 12 094 кадра — общие ванильные и «сборниковые» наборы (зомби,
скелеты, `CURSOR`, `HIT`, `CAMERA`, базы X-COM, ванильные НЛО). Это первый реальный кандидат в `hd_core`
и `hd_xcf` без перерисовки.

**Вывод.** Включать `hd` в X-Com Files как есть нельзя: ~1 200 кадров и часть статей педии покажут
картинки Пираток. Нужен этап 3 (раздел `hd_core` / `hd_piratez`) или этап 6 (подпись исходного кадра,
несовпало — классика). Подпись закрывает и эти 1 200 кадров, и все будущие игры разом.

## 4. Попутно в установке Пираток

`scanModDir: Can't scan` у `XPZ_Kisya_Brysya_Sisters`, `Piratez Czech Names`, `OAK patch for RU Piratez`:
в `Пиратки\Dioxine_XPiratez\user\mods` эти папки — пустые каталоги без `metadata.yml` (полная Кися лежит в
`dist/_stage`). Похоже на след снятой галочки компонента — проверить, что лаунчер при удалении компонента
убирает и пустые папки.
