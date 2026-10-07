# Целевые игры для лаунчера: пять модов с mod.io (этап 0 MULTIMOD)
Дата: 2026-10-02 | Уверенность: высокая по metadata.yml, размерам, датам, прямой ссылке на скачивание и по составу архивов; по правам авторов - ни один из шести релизов не имеет проверенного разрешения на раздачу (раздел «Права и лицензии», сверка 02.10.2026); низкая по условиям API для нашего случая (ключа нет, вызовов с ключом не делали)

## Краткий ответ

- `metadata.yml` всех пяти игр (и 40k) прочитан из **самих релизных архивов mod.io**: через HTTP Range взят только конец zip (центральный каталог) и один маленький файл, архивы целиком не скачивались (всего около 6-7 МБ чтения на всё). У X-Com Files архив лежит локально (`E:\Additional mods\openxcom_xfiles_42.zip`, размер байт в байт равен размеру на mod.io).
- Мастеры движка получились **разные**: X-Com Files, X-Chronicles и Mars-com — мастеры поверх `xcom1` (UFO); World of (Terrifying) Silence — **не мастер**, обычный мод на мастере `xcom2` (TFTD); RoSigma — подмод мастера `40k` (`isMaster: false`, `master: 40k`), а сам `40k` — мастер поверх `xcom1`. Гипотеза из MULTIMOD §2 подтверждена: у RoSigma **обязательна зависимость от 40k**, мастер движка = `40k`.
- Все пять требуют OXCE не выше 8.7 (`requiredExtendedVersion`); наш движок собирается как `8.7.1.0` (`src/version.h:26`), проверка идёт по `isHigherThanCurrentVersion` — все проходят.
- **Скачать с mod.io без ключа и без входа можно**: ссылка `https://g-51.modapi.io/v1/games/51/mods/<mod>/files/<file>/download` отвечает `302` на `binary.modcdn.io/...?verify=...`, там работает Range (проверено curl-ом, 206). А вот **список файлов и последняя версия** через API требуют ключ: без него `401, error_ref 11000`.
- Права на раздачу своей копии: **проверенного разрешения нет ни у одного из шести релизов** (сверка 02.10.2026, раздел «Права и лицензии»). У X-Com Files 4.2 в readme внутри архива есть заявление «CC-BY-NC» (версия 4.0 только по ссылке), но с оговоркой про чужое содержимое и с 41 треком музыки, в том числе из коммерческих игр: UNVERIFIED для архива целиком. У X-Chronicles 1.8 и Mars-com 1.5 лицензия «CC-NC-BY-SA» названа только на странице mod.io и в теме форума, внутри архивов её нет (у X-Chronicles есть ссылка на BY-NC-SA 4.0, у Mars-com нет версии): UNVERIFIED. У World of Silence, 40k и ROSIGMA лицензии не найдено: UNVERIFIED. VERIFIED-FORBIDS нет ни у кого. Условия mod.io прав на раздачу не дают.

## Детали

### Таблица по играм

Значения `id / isMaster / master / requiredExtendedVersion` — дословно из `metadata.yml` релизного архива mod.io (файл указан в колонке «источник»).

| | X-Com Files | World of (Terrifying) Silence | 40k ROSIGMA | X-Chronicles | Mars-com |
|---|---|---|---|---|---|
| Страница | `/m/the-x-com-files` | `/m/the-world-of-terrifying-silence` | `/m/rosigma` | `/m/x-chronicles` | `/m/mars-com` |
| id мода mod.io | 158 | 378 | 896102 | 1463316 | 6046584 |
| Автор(ы) | Solarius Scorch | Nord (оригинал и поддержка на mod.io; форк Murkhach — отдельная ветка, не эта) | Leflair, Buscher, Xom126 и др. | Nord | Nord |
| `id` в metadata | `x-com-files` | `TWoTS` | `40k_ROSIGMA_edits` | `Xchr` | `Mars-com` |
| `isMaster` | true | **false** | false | true | true |
| `master` | `xcom1` | **`xcom2`** | **`40k`** | `xcom1` | `xcom1` |
| Зависимость mod.io | 1 (заглушка OXCE, id 205) | не указана | 1: мод **40k** (id 297) | не указана | не указана |
| `requiredExtendedVersion` | 8.6 | 8.7 | 8.5 | 8.7 | 8.7 |
| Версия | 4.2 | 2.8 | 3.2 (в metadata: `RELEASE - 3.2 ROSIGMA - 40k039 and CHAOS Edition`; на странице «3.2- with 40k039 & OXCE 8.5») | 1.8 | 1.5 |
| Файл на mod.io | `openxcom_xfiles_42.zip`, file id 8236968 | `twots_2_8-4e1i.zip`, 8249581 | `rosigma.zip`, 7762287 | `xchr_1_8-fghl.zip`, 8249632 | `mars-com_1_5-clmp.zip`, 8249614 |
| Размер архива | 248 338 351 Б (236,83 МиБ) | 25 782 195 Б (24,59 МиБ) | 418 063 586 Б (398,7 МиБ) | 22 963 354 Б (21,9 МиБ) | 5 238 619 Б (5,0 МиБ) |
| Дата загрузки файла (Last-Modified на CDN) | 2026-09-21 08:58 GMT | 2026-09-25 19:29 GMT | 2026-05-22 10:01 GMT | 2026-09-25 19:48 GMT | 2026-09-25 19:44 GMT |
| Ванильные данные | UFO (`xcom1`) | **TFTD** (`xcom2`) | UFO (через 40k, `xcom1`) | UFO (`xcom1`) | UFO (`xcom1`; в metadata ещё `loadResources: [UFO]`) |
| Подмоды в архиве | `DarkGeoscape` (id `dark-geoscape`, master `x-com-files`), `XCF Cyrillic Names` (id `XCF-CyrNames`, master `x-com-files`) | нет (одна папка `TWoTS`) | нет (одна папка `rosigma`) | `XCHR Cyrillic Names` (id `XCHR-CyrNames`, master `Xchr`) | нет (одна папка `Mars-com`) |
| Языки в `Language/` архива | cs, da, de, el, en-GB, en-US, es-419, es-ES, et, fr, hu, it, ja, ko, lt, pl, pt-BR, pt-PT, ro, **ru**, sk, uk, vi, zh-CN, zh-TW, zh | en-US, ko, **ru** | en-US, **ru** | en-US, **ru** | en-US, **ru** |
| Лицензия (заявление автора; вердикт - в разделе «Права и лицензии») | «CC-BY-NC» в readme архива, deed 4.0 по ссылке; UNVERIFIED (чужое содержимое, музыка) | в архиве лицензии на мод нет (есть CC BY-SA 4.0 на одну картинку, которой в архиве нет); UNVERIFIED | не найдено; в архиве «non-profit mod», не лицензия; UNVERIFIED | «CC-NC-BY-SA» на странице mod.io и форуме, ссылка на BY-NC-SA 4.0 только на mod.io, в архиве нет; UNVERIFIED | «CC-NC-BY-SA» на странице и форуме, без версии и ссылки, в архиве нет; UNVERIFIED |
| Источник metadata | архив mod.io = локальный zip (размеры совпали); то же в репозитории (ветка master там уже 4.3-dev) | диапазонное чтение архива mod.io | диапазонное чтение архива mod.io; то же в теге `3.2` репозитория Codeberg | диапазонное чтение архива mod.io | диапазонное чтение архива mod.io |

Полный `metadata.yml` (текущий релиз каждой игры), без изменений:

```yaml
# X-Com Files 4.2 (XComFiles/metadata.yml)
name: "X-Com Files"
version: "4.2"
requiredExtendedVersion: "8.6"
author: "Solarius Scorch"
id: x-com-files
isMaster: true
master: xcom1
reservedSpace: 3
resourceConfig: Ruleset/transparencyLUTs.rul

# TWoTS 2.8 (TWoTS/metadata.yml)
name: "The world of (terrifying) silence"
version: 2.8
description: "Expansion of TFTD. OXCE not included."
author: Nord
id: TWoTS
requiredExtendedVersion: "8.7"
reservedSpace: 3
isMaster: false
master: xcom2

# ROSIGMA 3.2 (rosigma/metadata.yml)
name: "40k ROSIGMA Submod"
version: "RELEASE - 3.2 ROSIGMA - 40k039 and CHAOS Edition"
id: 40k_ROSIGMA_edits
master: 40k
isMaster: false
resourceConfig: Ruleset/vars_ROSIGMA.rul
reservedSpace: 5
requiredExtendedVersion: "8.5"

# 40k 039 (40k/metadata.yml, файл 038cutscenes.zip на mod.io)
name: "40k"
version: "039"
id: 40k
master: xcom1
isMaster: true
resourceConfig: Ruleset/vars40k.rul
reservedSpace: 2
requiredExtendedVersion: "7.5.3"

# X-Chronicles 1.8 (XCHR/metadata.yml)
name: "X-Chronicles"
version: "1.8"
id: Xchr
isMaster: true
master: xcom1
reservedSpace: 4
resourceConfig: transparency.rul
requiredExtendedVersion: "8.7"

# Mars-com 1.5 (Mars-com/metadata.yml)
name: "Mars-com"
version: "1.5"
id: Mars-com
reservedSpace: 7
requiredExtendedVersion: "8.7"
resourceConfig: transparency.rul
master: xcom1
isMaster: true
loadResources:
  - UFO
```

### Что из этого следует для модели «игра = мастер движка + требования» (MULTIMOD §4.1)

| Игра | `engineMaster` (ключ `-master`) | Что должно быть включено |
|---|---|---|
| X-Com Files | `x-com-files` (его `master` — `xcom1`) | `x-com-files` |
| World of Silence | `xcom2` | `TWoTS` (сам по себе не мастер: в меню «Базовая игра» его нет, это мод поверх TFTD) |
| RoSigma | `40k` (его `master` — `xcom1`) | `40k` **и** `40k_ROSIGMA_edits` |
| X-Chronicles | `Xchr` | `Xchr` |
| Mars-com | `Mars-com` | `Mars-com` |

Факты о движке, на которые это опирается (проверено в коде):
- `ModInfo::canActivate`: мод активируется, если он мастер, или без мастера, или его `master` равен текущему мастеру (`src/Engine/ModInfo.cpp:299-302`) — поэтому RoSigma видна только при выбранном `40k`, а TWoTS — только при выбранном `xcom2`.
- Если `isMaster: true`, то по умолчанию `master` пуст, но может быть задан явно (`ModInfo.cpp:233-245`); у всех трёх мастеров из таблицы он задан (`xcom1`).
- `loadResources` читается только у мастера с пустым `master` (`ModInfo.cpp:247-251`), поэтому `loadResources: [UFO]` у Mars-com при `master: xcom1` движок не использует.
- `requiredExtendedVersion` разбирается как версия «Extended» (`ModInfo.cpp:218-222`); `8.7` не выше `8.7.1.0`, значит все пять проходят.
- id с дефисом (`x-com-files`, `Mars-com`) допустимы для движка, но в скриптах мода дефис в id обрезается: из треда Mars-com (форум, тема 13072, ответ Nord на лог ошибок пользователя) «mod Id's that contain dashes (-) in them won't work as they seem to get truncated in the scripts» — это к лаунчеру отношения не имеет, но объясняет, почему авторы меняют id.

### Подмоды и связанные файлы на mod.io

- **X-Com Files**: в самом архиве лежат `DarkGeoscape` (Solarius Scorch) и `XCF Cyrillic Names` (OAK C.G. и Kammerer, база по состоянию на 2022-07-20 по README внутри); отдельных файлов не нужно. На mod.io у XCF есть и отдельные подмоды (например «The X-Com Files - Bonus Music Pack», `/m/the-x-com-files-bonus-music-pack`), их id и версии не собирали.
- **RoSigma**: подмоды вне архива, на страницах mod.io: Army Painter (`/m/xcom-army-painter-oxce`), три саундтрека (`igost-rosigma-40k`, `sobost-rosigma-40k`, `chaosost-rosigma-40k`), Raven Guard reskin (`/m/raven-guard-rosigma-reskin`), коллекция минимодов. Мод **40k** на mod.io (1 110 284 118 Б, 1,03 ГБ, версия 039, файл `038cutscenes.zip`, загружен 2025-01-08) содержит внутри три мини-подмода смены ордена: `Blood Angels`, `Imperial Fists`, `Salamanders` (у первых двух `master: "40k"` прочитано; у Salamanders вывод обрезан, но по аналогии то же).
- **X-Chronicles**: `XCHR Cyrillic Names` (OAK C.G. и Kammerer, Kato, Nord) в том же архиве.

### Особенности версий

- X-Com Files: на mod.io и в теге 4.2 репозитория — 4.2, а в `master` репозитория `SolariusScorch/XComFiles` уже `version: "4.3"` (разработка). Брать по mod.io, а не по ветке.
- RoSigma: в репозитории Codeberg (`LeflairKunstler/ROSIGMA`) ветка `main` — `DEV - 3.2A`, `requiredExtendedVersion: "8.7"`; тег `3.2` (2026-04-18) — релиз, `8.5`. Архив mod.io (загружен 2026-05-22) совпадает с тегом `3.2` по `metadata.yml`. **Локальный файл `E:\Additional mods\rosigma3.2.4.zip` отличается от mod.io**: 418 070 246 Б против 418 063 586 и 16201 запись против 16203, при том же тексте `metadata.yml`. Откуда он, не выяснено. Вывод: версия в `metadata.yml` не идентифицирует архив — нужен хэш.
- 40k: `requiredExtendedVersion: "7.5.3"`, версия 039 — самая новая в репозитории (`BeatAroundTheBuscher/OXCE_40k`, релиз 039 от 2025-01-08, «OXCE 8.0 Compatibility»); RoSigma 3.2 требует именно 40k 039.
- Три мода Nord (TWoTS, X-Chronicles, Mars-com) обновлены в один день, 2026-09-25, под OXCE 8.7 («mod updated to work with OXCE 8.7» в журналах изменений на форуме); значит, закреплённая версия в каталоге устаревает быстро.

### Права и лицензии (пересмотрено 02.10.2026)

Прежний вывод («у X-Com Files, X-Chronicles и Mars-com есть свободная лицензия, раздавать можно») **снят**: он опирался на слова с веб-страниц и не учитывал содержимое архивов, версию лицензии и исключения. Ниже каждый релиз разобран по семи пунктам. Прямая ссылка на скачивание с mod.io сама по себе права на раздачу не даёт (см. подраздел про условия mod.io).

**Как проверялось.** Для каждого релиза по ссылке `https://g-51.modapi.io/v1/games/51/mods/<mod>/files/<file>/download` (302 на `binary.modcdn.io`) через HTTP Range прочитан только центральный каталог zip и маленькие текстовые файлы; архивы целиком не скачивались. Для X-Com Files центральный каталог (13 474 имени и CRC32) сверён с локальным `E:\Additional mods\openxcom_xfiles_42.zip` — совпал целиком, размер совпал байт в байт. По каждому каталогу искали по имени файла `readme / licen[cs]e / copying / credit / notice / terms / legal / author / thanks / about`, плюс все `.txt .md .rtf .html .pdf .url` на глубине до одной папки; у Nord-модов, RoSigma и 40k дополнительно прочитаны `metadata.yml` и (у Mars-com, X-Chronicles, TWoTS, RoSigma) `Language/*.yml` на слова licen/CC BY/copyright/permission. Страницы mod.io и форума прочитаны 02.10.2026 через `r.jina.ai` (рендер без JS), даты правок текста этих страниц **не известны**: цитата «как на 02.10.2026».

**Шкала вердиктов.** VERIFIED-PERMITS — в первичном источнике (архив релиза) есть явная лицензия с версией, нет оговорок, ставящих под сомнение права на весь архив. VERIFIED-FORBIDS — явный запрет. UNVERIFIED — всё остальное, в том числе «лицензия названа без версии», «лицензия только на странице, не в архиве», «есть оговорка про чужое содержимое». **На 02.10.2026 ни один из шести релизов не получает VERIFIED-PERMITS, запретов тоже не найдено.**

#### Сводка

| Релиз | mod / file id | Лицензия внутри архива | Лицензия снаружи | Точное определение | Вердикт |
|---|---|---|---|---|---|
| X-Com Files 4.2 | 158 / 8236968 | да: `XComFiles/X-Com_Files_readme.txt`, «CC-BY-NC» + ссылка на deed 4.0 | тот же текст в README репозитория, не противоречит | CC BY-NC 4.0 по ссылке (в тексте версии нет) | **UNVERIFIED** для всего архива: оговорка про чужое и 41 трек музыки, часть из коммерческих игр |
| X-Chronicles 1.8 | 1463316 / 8249632 | **нет** ни одного файла с лицензией | mod.io и форум: «CC-NC-BY-SA»; ссылка на BY-NC-SA 4.0 только на mod.io | вероятно CC BY-NC-SA 4.0, но название нестандартное | **UNVERIFIED** |
| Mars-com 1.5 | 6046584 / 8249614 | **нет** | mod.io и форум: «CC-NC-BY-SA», без версии и ссылки | неоднозначно: версии нет | **UNVERIFIED** |
| TWoTS 2.8 | 378 / 8249581 | на мод — **нет**; лежит лицензия одной картинки (CC BY-SA 4.0), самой картинки в архиве нет | нигде | лицензии на мод не найдено | **UNVERIFIED** (права не переданы; запрета тоже нет) |
| 40k 039 | 297 / 5956800 | **нет** | нигде (GitHub: поле license пусто, файла LICENSE нет) | не найдено | **UNVERIFIED** |
| 40k ROSIGMA 3.2 | 896102 / 7762287 | **нет**; есть «non-profit mod … All art credit goes to the respective artist» | README ветки `main` (не тега 3.2): «A free submod»; лицензии нет | не найдено | **UNVERIFIED** |

#### 1. X-Com Files 4.2 (mod 158)

1. **Релиз.** mod 158, file 8236968, `openxcom_xfiles_42.zip`, 248 338 351 Б (236,83 МиБ), 13 474 записи; Last-Modified CDN 2026-09-21 08:58:56 GMT; ETag `"cbc45e2146e1997c7027c5e050ca6a3a-5"` (составной, **не MD5**). MD5 из API не получен: список файлов требует ключ. Версия внутри — 4.2 (верхняя строка журнала изменений в readme).
2. **Внутри архива, проверено.** `XComFiles/X-Com_Files_readme.txt` (149 810 Б, прочитан целиком), `XCF Cyrillic Names/README.txt` (796 Б); `XComFiles/metadata.yml` прочитан при прежней сверке (полный текст приведён выше, слов о лицензии в нём нет). Файла LICENSE нет; в `DarkGeoscape` текстовых файлов нет. Пять png с «License» в имени — предметы игры, не лицензии. Цитаты (путь `XComFiles/X-Com_Files_readme.txt`):
   - строка 42: «This mod is non-commercial and falls under the CC-BY-NC license. This means that you are free to share it (copy and redistribute the material in any medium or format)»;
   - строка 43: «Details here: https://creativecommons.org/licenses/by-nc/4.0/deed.en»;
   - строка 208: «All content belong to their respective creators, as indicated in the credits.»
   В `XCF Cyrillic Names/README.txt` лицензии нет: только история сборок («Основано на гитхаб-версии XComFiles по состоянию на 20.07.2022»).
3. **Снаружи.** https://raw.githubusercontent.com/SolariusScorch/XComFiles/master/README.md, строки 35-36 — тот же текст дословно (`master` — уже 4.3-dev; в README тега 4.2 строка «CC-BY-NC» тоже есть). Релиз GitHub 4.2 (2026-09-21T09:04:36Z) без приложенных файлов; файла LICENSE в корне репозитория нет, поле license GitHub пусто. На странице mod.io (https://mod.io/g/openxcom/m/the-x-com-files) строк о лицензии нет. Противоречий нет.
4. **Определение.** CC BY-NC 4.0 — только по ссылке на deed (https://creativecommons.org/licenses/by-nc/4.0/); в самой фразе «CC-BY-NC» номер версии не назван. Небольшая оговорка, вероятно несущественная.
5. **Чужое.** (а) строка 208 прямо говорит, что содержимое принадлежит «their respective creators»; лицензия автора мода на чужие вклады этим не подтверждена. (б) Список благодарностей — около сотни участников (Meridian, Dioxine, Finnik, Otto Hartenstein, Brain_322 и др.); сведений, что они дали права на тех же условиях, нет. (в) Раздел «MUSIC:» (строка 331): 41 трек, из них 15 «Suno AI», остальные — с указанием источника: Robert Prince (DOOMGATE, DOOMHUNT, DOOMSHAWN), Fallout, Warcraft 3, Soldier of Fortune, System Shock 2, Shadow Warrior, Space Rangers 2, Alien Shooter 2, Mark Snow, The Avalanches, Kult: Heretic Kingdoms, «Vanilla AGA version of UFO: Enemy Unknown», The Thing и др. В архиве 43 файла `XComFiles/SOUND/*.ogg` (146,6 МБ в распакованном виде); двух из них (`TFTD_AQUA.ogg`, `ZIZZ_STUDIO_SPOOKY_SCAPE.ogg`) в списке нет. Это записи, права на которые у Solarius Scorch вряд ли есть: **выдать их под CC BY-NC автор не мог**. (г) Строки «http://www.freesfx.co.uk: Some sounds» и «The Internet: pictures» — источники без лицензии. Для всего архива это значит: фраза «лицензия мода» не покрывает музыку и часть картинок; раздача архива целиком включает материалы, на которые разрешения нет.
6. **Условия для нас.** (CC BY-NC 4.0, legalcode.en) Неизменная копия: п. 3(a)(1) — сохранить указание авторов, уведомление об авторском праве, ссылку на лицензию и на отказ от гарантий (при неизменной копии это всё лежит в readme внутри архива; ссылку на лицензию надо дать рядом); п. 1(9) «NonCommercial means not primarily intended for or directed towards commercial advantage or monetary compensation» — раздача лаунчером не должна быть платной или привязанной к оплате; п. 2(a)(5)(B) — нельзя ставить дополнительные условия или технические меры, ограничивающие получателя. HD-слой поверх: слой, полученный из кадров мода, — Adapted Material; ShareAlike в BY-NC **нет**, но остаются NC и обязанность указать, что материал изменён (п. 3(a)(1)(B)), и указание прежних авторов. Нужные слова атрибуции: «The X-Com Files by Solarius Scorch and contributors (credits in X-Com_Files_readme.txt), CC BY-NC 4.0, https://creativecommons.org/licenses/by-nc/4.0/; HD layer: modified». Вопрос «коммерческий ли лаунчер» (реклама, донаты, платные функции) здесь не решён — это решение владельца проекта.
7. **Вердикт: UNVERIFIED для неизменной копии всего архива.** Для того, что автор вправе лицензировать (его собственный вклад), заявление явное и лежит в самом архиве; для остального — нет. Чего не хватает: письменный ответ Solarius Scorch — (1) подтверждение версии 4.0; (2) охватывает ли заявление весь архив 4.2 за исключением перечисленных треков и чужих файлов; (3) можно ли раздавать архив без `SOUND/*.ogg` и какие ещё файлы исключить; (4) условия для подмода `XCF Cyrillic Names` (авторы Kato, OAK C.G., Kammerer).

#### 2. X-Chronicles 1.8 (mod 1463316)

1. **Релиз.** mod 1463316, file 8249632, `xchr_1_8-fghl.zip`, 22 963 354 Б (21,9 МиБ), 5 599 записей; Last-Modified 2026-09-25 19:48:45 GMT; ETag `"252f4b4a6132ca37129ba94d2769df0f-5"` (составной, не MD5); MD5 не получен. Автор Nord.
2. **Внутри архива.** Проверены: все 5 599 имён на readme/license/credit и т.п. — **ни одного файла**; `XCHR/metadata.yml` (236 Б, без лицензии и без `description`), `XCHR Cyrillic Names/metadata.yml`, `XCHR/Language/en-US.yml` и `ru.yml` (в них слова licen/CC/copyright не встречаются; единственное «permission» — игровой текст про разрешение на закупку оружия). Лицензии внутри архива **нет**.
3. **Снаружи.** (а) https://mod.io/g/openxcom/m/x-chronicles, раздел «Credits» (страница создана 2021-11-03, текст на 02.10.2026): «All X-Com resources belongs to X-Com franchise owners (Take-Two Interactive, i think)» и «All other is under CC-NC-BY-SA, as mr.Hobbes insisted.» — с гиперссылкой на https://creativecommons.org/licenses/by-nc-sa/4.0/deed.en. (б) https://openxcom.org/forum/index.php?topic=10233.0 (заголовок «X-Chronicles Release, v.1.8»): та же фраза, без ссылки. Версии, к которой относятся заявления, на страницах нет: это текст на странице мода, не привязанный к файлу 1.8.
4. **Определение.** Название «CC-NC-BY-SA» нестандартное (порядок элементов; официально «BY-NC-SA»). Ссылка в описании mod.io ведёт на BY-NC-SA 4.0 — по ней лицензия определяется как **CC BY-NC-SA 4.0**, но только по ссылке на странице, не в архиве. Расплывчато.
5. **Чужое.** Прямо исключены ресурсы X-Com («belongs to X-Com franchise owners»). Мод на мастере UFO (`master: xcom1`) и по заявлению автора заимствует у других («to the other modders from whom I borrowed something» — без имён и файлов). Пример в треде: вопрос про «goblin assets» и их автора (тема 10233, страница `.40`) — права на них отдельные. Подмод `XCHR Cyrillic Names` — другие авторы (OAK C.G., Kammerer, Kato, Nord по данным ранней сверки), своей лицензии нет.
6. **Условия для нас (если лицензия подтвердится как BY-NC-SA 4.0).** Неизменная копия: BY-NC 3(a) (то же, что выше) плюс NC; но в архиве нет ни лицензии, ни авторства — ссылку на лицензию и авторов надо дать самим. HD-слой, производный от кадров мода, — Adapted Material: BY-NC-SA 4.0, п. 3(b)(1) — «Adapter's License» обязана быть CC-лицензией с теми же элементами (BY-NC-SA, эта версия или более поздняя, либо совместимая), п. 3(b)(2) — дать текст или ссылку на неё, п. 3(b)(3) — без дополнительных условий и технических мер. Атрибуция: «X-Chronicles by Nord, CC BY-NC-SA 4.0, https://creativecommons.org/licenses/by-nc-sa/4.0/; HD layer: modified, same licence».
7. **Вердикт: UNVERIFIED.** Не хватает: подтверждения Nord в первичном источнике (файл в архиве или письменный ответ) — версия 4.0, что значит «all other», перечень заимствованного и его лицензии, условия для Cyrillic Names.

#### 3. Mars-com 1.5 (mod 6046584)

1. **Релиз.** mod 6046584, file 8249614, `mars-com_1_5-clmp.zip`, 5 238 619 Б (5,0 МиБ), 1 860 записей; Last-Modified 2026-09-25 19:44:41 GMT; ETag `"38f6901ea2d3bb867056246fcf2208ed"` (без суффикса `-N`: возможно, MD5 содержимого, **не проверено** — файл целиком не качали). Автор Nord; страница создана 2026-05-09.
2. **Внутри архива.** Имена всех 1 860 записей — файлов readme/license/credit нет; верхний уровень: `Mars-com/metadata.yml` (247 Б), `Mars-com/transparency.rul`; `Language/en-US.yml`, `ru.yml` — слов о лицензии нет. Лицензии внутри **нет**.
3. **Снаружи.** https://mod.io/g/openxcom/m/mars-com, «Credits» (02.10.2026): «All X-Com resources belongs to X-Com franchise owners (Take-Two Interactive, i think)» и «All other is under CC-NC-BY-SA.»; та же фраза в https://openxcom.org/forum/index.php?topic=13072.0 («[Overhaul] Mars-com v.1.5»). Ссылки на текст лицензии нет, версии нет.
4. **Определение. Неоднозначно:** нет версии (у CC-лицензий 3.0 и 4.0 различаются условия, совместимость и ShareAlike), нет ссылки, нестандартное название.
5. **Чужое.** Исключены ресурсы X-Com; «to the other modders from whom I borrowed something» (без списка); «most sprites reimagined» из описания — производные от спрайтов X-Com, на которые лицензия автора не распространяется.
6. **Условия для нас.** Если подтвердится BY-NC-SA 4.0 — те же, что у X-Chronicles; при версии 3.0 условия другие (юридический текст 3.0 не разбирали). Атрибуция: «Mars-com by Nord, CC BY-NC-SA (version to be confirmed)» — окончательный текст нельзя написать, пока версия не названа.
7. **Вердикт: UNVERIFIED.** Не хватает: ответа Nord — версия, ссылка на текст, перечень заимствований; лучше — файл LICENSE в самом архиве.

#### 4. The World of (Terrifying) Silence 2.8 (mod 378)

1. **Релиз.** mod 378, file 8249581, `twots_2_8-4e1i.zip`, 25 782 195 Б (24,59 МиБ), 3 001 запись; Last-Modified 2026-09-25 19:29:27 GMT; ETag `"2335aedd6a3dafa1cef5f57241c9467c-5"` (составной, не MD5); MD5 не получен. Автор Nord. Мод поверх TFTD, не мастер.
2. **Внутри архива.** Поиск по 3 001 имени: единственный текстовый файл — `TWoTS/Resources/Weapons/TerroristWeaponsLicense.txt` (275 Б). Цитата: «Terror.png / Artwork (c) Riccardo Gasperi / This artwork is licensed under a Creative Commons Attribution-ShareAlike 4.0 International License.» Это лицензия **одной картинки**; файла `Terror.png` в архиве нет (по имени не найден). `TWoTS/metadata.yml` (237 Б): `description: "Expansion of TFTD. OXCE not included."`; `Language/*.yml` слов о лицензии не содержат. Лицензии на сам мод **нет**.
3. **Снаружи.** https://mod.io/g/openxcom/m/the-world-of-terrifying-silence (02.10.2026): перечень «Included mods from other authors: "Extended facilities" by Blank. "Moray" by tyran_nick. "Carharodons" by Xops», «Included new_civilian's TFTD patch»; про лицензию — ничего. https://openxcom.org/forum/index.php?topic=5566.0 (v.2.8): то же плюс «"More USO" by Blank. TFTD Alt Drills by pWWWa»; лицензии нет. Отдельная тема https://openxcom.org/forum/index.php?topic=13220.0 (форк Murkhach «TWoTSM», «based on 2.63», на OneDrive): «Feel free to comment adjust or use any part of this mod» — относится к его форку, не к файлу mod.io 2.8 и не к работам Nord.
4. **Определение.** Для мода — **не найдено**. Для `Terror.png` — CC BY-SA 4.0 (по тексту файла).
5. **Чужое.** Включены работы Blank, tyran_nick, Xops, new_civilian, pWWWa; их лицензий нет ни в архиве, ни на странице. Права на данные TFTD — у франшизы.
6. **Условия для нас.** Права на раздачу копии и на адаптацию автор не передавал в найденных источниках; в отсутствие явной лицензии получатель по общему принципу авторского права этих прав не имеет (общий принцип, юрисдикция не изучалась). Для `Terror.png` (если бы он был) — атрибуция и ShareAlike по CC BY-SA 4.0.
7. **Вердикт: UNVERIFIED.** Не хватает: разрешения Nord на раздачу архива и на HD-слой поверх; подтверждения авторов вошедших модов.

#### 5. 40k 039 (mod 297)

1. **Релиз.** mod 297, file 5956800, `038cutscenes.zip`, 1 110 284 118 Б (1,03 ГиБ), 12 171 запись; на странице mod.io дата 2025-01-07 23:57, Last-Modified CDN 2025-01-08 00:31:38 GMT; ETag `"1e3bd53d93899040dc1536fcd5c6f91a-6"` (составной, не MD5). Версия в `metadata.yml` — 039. Авторы на mod.io: ohartenstein23, Bulletdesigner.
2. **Внутри архива.** Центральный каталог (12 171 имя) и маленькие файлы: `40k/README.md` (355 Б), `40k/linker.yml`, `40k/metadata.yml` (поле `author`: «bulletdesigner, Ryskeliini, ohartenstein23 with help from all OXC forum, special thks to all who help»), `metadata.yml` трёх мини-подмодов (Blood Angels, Imperial Fists, Salamanders). README — только ссылки на подмоды и вики Codex. Лицензии **нет**.
3. **Снаружи.** https://mod.io/g/openxcom/m/40k — лицензии нет. https://openxcom.org/forum/index.php?topic=5026.0 (первое сообщение, «Credits»): «Big props to Ryskeliini for the space marine stuff», «Used a lot of maps from Terrainpack so special thks to Hobbes», «i used lot of stuff from other mods for reference and change it to 40k universe», «Background images from various internet sources». https://github.com/BeatAroundTheBuscher/OXCE_40k — поле license пусто, файла LICENSE в корне нет (последний push 2025-01-08 = релиз 039).
4. **Определение.** Не найдено.
5. **Чужое.** Прямо названы карты из Terrainpack (Hobbes), материалы Ryskeliini, «stuff from other mods», картинки «from various internet sources»; сеттинг Warhammer 40k — чужая франшиза (разрешения правообладателя среди найденных источников нет).
6. **Условия для нас.** Права на раздачу и адаптацию в найденных источниках не переданы (общий принцип, см. п. 6 TWoTS).
7. **Вердикт: UNVERIFIED.** Не хватает: ответа ohartenstein23 / bulletdesigner (они указаны авторами на mod.io); отдельно — Hobbes (карты) и Ryskeliini (основа).

#### 6. 40k ROSIGMA 3.2 (mod 896102)

1. **Релиз.** mod 896102, file 7762287, `rosigma.zip`, 418 063 586 Б (398,7 МиБ), 16 203 записи; Last-Modified CDN 2026-05-22 10:01 GMT; ETag `"78542d4d524f4a78bb6bf9e59142d607-8"` (составной, не MD5). `metadata.yml`: версия «RELEASE - 3.2 ROSIGMA - 40k039 and CHAOS Edition», `master: 40k`. Локальный `E:\Additional mods\rosigma3.2.4.zip` — другой файл (418 070 246 Б, 16 201 запись), к этому релизу не относится.
2. **Внутри архива.** Прочитаны: `rosigma/README.md` (31 Б: «# ROSIGMA / A submod for 40k OXCE»), `rosigma/Install instructions.txt`, `rosigma/ROSIGMA text notes.txt` (лицензионных слов нет), `rosigma/Resources/FOESPEDIAADEPTAS/Art Credit.txt` (1 198 Б), `metadata.yml`, а также `Language/en-US.yml` и `ru.yml` (раздел «Credits» — списки участников, лицензии нет). Цитаты из `Art Credit.txt`: «This is a non-profit mod for a opensource game. All art credit goes to the respective artist.» и, про одну иллюстрацию, «Games Workshop probably owns the rights.» Это уведомление о нежелании извлекать прибыль и о чужом авторстве, **не лицензия**. Лицензии нет.
3. **Снаружи.** https://codeberg.org/LeflairKunstler/ROSIGMA, README ветки `main` (DEV 3.2A): «A free submod for 40k OXCE (OpenXcom Extended) made by many contributors over the yeas»; в README тега `3.2` этой фразы **нет** (только две строки заголовка), поле лицензии репозитория пусто. https://mod.io/g/openxcom/m/rosigma, «Credits» (02.10.2026): «Dioxine for some assets we nabbed from XPZ» и перечень вкладов Cabal/CABSHEP, Lord Flashheart, StarSquid и др. Тема https://openxcom.org/forum/index.php?topic=9687.0: «If you want to contribute anything at all … feel free to contact us» (про вклад в мод, не про использование).
4. **Определение.** Не найдено. Слово «free» без текста лицензии — не лицензия.
5. **Чужое.** Активы Dioxine из X-Piratez; Cabal/CABSHEP, Lord Flashheart, TheodorTemplar, ErraticDeviant (озвучка), StarSquid; иллюстрации по Art Credit (Paul Dainton, Thanh Tuấn и др., часть из них — материалы Games Workshop); подмод зависит от 40k (см. п. 5 для 40k). Для сведения: в README X-Piratez из локальной установки (`Пиратки\Dioxine_XPiratez\XPiratez readme\XPiratez_readme.txt`, строка 98; версия установки не сверялась с заимствованным в RoSigma) сказано «The contents are public domain, credit would be nice, just don't distribute the full mod under your name. Non-commercial.» — это другой мод, к самому релизу RoSigma оно не подтверждено.
6. **Условия для нас.** Права на раздачу и адаптацию в найденных источниках не переданы.
7. **Вердикт: UNVERIFIED.** Не хватает: ответа Leflair / Buscher / Xom126 (авторы по описанию), согласия Dioxine на включённые активы XPZ, перечня иллюстраций и их лицензий.

#### Условия mod.io (отдельно: они не дают прав на раздачу)

Источники: Terms of Use https://mod.io/terms, API Access Terms https://mod.io/apiterms, Game Terms https://mod.io/gameterms; прочитаны 02.10.2026, даты редакций на страницах не указаны. Нумерация подпунктов внутри п. 6.2 — по порядку списка в тексте страницы.

- **ToU п. 6.2(1):** автор даёт «mod.io and the Relevant Game Admin» лицензию (переуступаемую, сублицензируемую, бессрочную) «for the sole purpose of providing the Services». Получатель лицензии — mod.io и администратор игры; мы ни тем, ни другим не являемся.
- **ToU п. 6.2(2):** «Enhanced License Rights» (продажа, публикация на других носителях «for users of our Services and other third parties») автор даёт mod.io и администратору игры отдельно через панель UGC и может отозвать. Включены ли они у какого-либо из шести модов — со стороны не видно.
- **ToU п. 6.2(5):** «User Generated Content is publicly available information which is shared with other users, other third parties, and is made available through the mod.io API» — это сказано про доступность, не про права на использование.
- **ToU п. 6.2(7):** автор сохраняет все права на содержимое («you retain all rights to the User Generated Content»); п. 6.3(1): автор заявляет, что содержимое его или он вправе его лицензировать.
- **ToU п. 9.1-9.3:** то, что показано на сервисе, принадлежит mod.io или лицензировано ему; копировать и распространять это без разрешения нельзя (п. 9.3). Это относится к материалам сервиса; к вопросу о правах на моды не отвечает, но к показу обложек и скриншотов страниц надо относиться осторожно.
- **API Access Terms п. 2.1:** лицензия на доступ, внедрение и распространение «mod.io API data to End Users for their use via your platform» — непередаваемая и несублицензируемая; **про права на сами файлы модов здесь ничего нет**. П. 3.3 — брендинг mod.io обязателен; п. 3.5 — нельзя использовать API «for spamming or scraping data»; п. 5.1 — интеллектуальная собственность в API остаётся за mod.io.
- **Game Terms п. 9.2 и 12.5:** «the mod.io API is open to third parties» и «Third parties are authorized to use the mod.io API (Tool Providers) to create and share apps, plugins, features, functionality and services»; п. 12.5(4): mod.io «is not a party to any license between you, any End Users and Tool Providers». Эти условия адресованы администратору игры, а не нам.
- **Вывод.** Условия mod.io определяют отношения автора с mod.io и сторонних программ с API. Они не дают лаунчеру прав на раздачу файла, не заменяют лицензию автора и ничего не говорят о скачивании без ключа по прямой ссылке. Права на каждый релиз определяются только заявлением автора (разделы выше).

### mod.io API: что известно

**Идентификаторы** (видны на страницах без ключа; сам API не вызывали):
- Игра OpenXcom на mod.io: `name_id` = `openxcom`, **game id 51** (в адресах `https://g-51.modapi.io/v1/games/51/...`; в пути обложки игры `thumb.modcdn.io/games/2838/51/...`). Игра на mod.io называется «OpenXcom», страница `https://mod.io/g/openxcom`.
- id модов — в таблице выше (поле «ID» на страницах); дополнительно OXCE-заглушка (543 Б, id 205) и 40k (id 297).
- id текущих файлов — в таблице выше (взяты из ссылок «Download file»).

**Что API не отдаёт без ключа.** Любой запрос к `api.mod.io/v1/...` и `g-51.modapi.io/v1/...` без `api_key` даёт `401`, `error_ref 11000` («malformed/missing api_key»); с недействительным ключом — `401`, `error_ref 11001`. Проверено curl-ом на `/games`, `/games/51`, `/games/51/mods/158`, `/games/51/mods/158/files/8236968`. Идентификаторы выше получены рендером страниц, не API.

**Ключи.** Документация REST API (https://docs.mod.io/restapiref/):
- Ключ даёт только чтение (GET), передаётся в строке запроса `api_key=<32 символа>`; запись и подписки — только через OAuth 2 с bearer-токеном. Для списка файлов и скачивания OAuth не нужен: «Browsing and downloading content» отмечены как назначение ключа.
- Два вида ключей: привязанный к игре — без ограничения запросов; привязанный к пользователю — **60 запросов в минуту**. Токен OAuth — 120/мин, по IP — 1000/мин. Превышение — `429` с `retry-after`; при упорстве учётные данные могут отозвать.
- Ключ пользователя запрашивают на `https://mod.io/me/access`: по условиям «You will get access to the mod.io API if mod.io accepts your request» (API Access Terms п. 1.1) — то есть одобрение ручное, срок и вероятность отказа неизвестны. Ключ игры выдаёт панель администратора игры; кто администратор страницы openxcom, не выяснено.
- Как получал ключ сам OpenXcom для встроенного браузера модов — не найдено. В нашем коде интеграции нет: единственный след — комментарий `//Options::refreshMods(); // TODO: uncomment ... after mod.io integration is merged` (`src/Menu/ModListState.cpp:91`). SupSuper в треде 6556 описывал тестовую сборку: данные пользователя в `%LOCALAPPDATA%\Mod.io\openxcom_modio`, общие моды в `%PROGRAMDATA%\Mod.io\<game id>`; ключ и id игры в посте не раскрыты.

**Настройка игры «API access» (`api_access_options`).** Поле объекта Game: бит 1 — «Allow 3rd parties to access this games API endpoints»; бит 2 — «Allow mods to be downloaded directly (if disabled all download URLs will contain a frequently changing verification hash to stop unauthorized use)»; бит 4 и 8 — требовать токен пользователя при скачивании. Значение у openxcom мы без ключа **прочитать не можем**. Косвенно:
- ссылка скачивания на странице не содержит хэша проверки и работает анонимно (проверено) — значит, бит 2 включён, биты 4 и 8 выключены;
- бит 1 (разрешён ли доступ сторонним программам) косвенно не проверить, нужен пробный вызов с ключом.

**Файл и хэш.** Объект файла (Modfile Object): `id`, `filesize`, `filename`, `version`, `changelog`, `filehash.md5`, `download.binary_url`, `download.date_expires`. **SHA-256 не отдаётся**, только MD5. Если у игры включён бит 2, ссылка стабильная и без хэша проверки; иначе в ссылку добавляется короткоживущий хэш, и сохранять `binary_url` нельзя. Список файлов мода — `GET /games/{game}/mods/{mod}/files`, зависимости — `GET /games/{game}/mods/{mod}/dependencies` (оба из справочника, GET с ключом).

**Прямая ссылка без входа — проверено.**
```
GET https://g-51.modapi.io/v1/games/51/mods/6046584/files/8249614/download
 -> 302 Location: https://binary.modcdn.io/mods/36cd/6046584/mars-com_1_5-clmp.zip?verify=<время>-<подпись>
GET <это> с Range: bytes=...  -> 206, заголовки ETag, Last-Modified, Content-Range
```
Так же для остальных пяти файлов. Подпись `verify` выдаётся при каждом обращении; срок жизни не выяснен (в пределах прогона не истекала). ETag у крупных файлов вида `"…-5"` (составная загрузка), то есть **не MD5 содержимого**; у Mars-com (5 МБ) ETag без суффикса, совпадение с MD5 не проверяли.

Как узнать id нового файла без ключа: ссылка зависит от id файла, а он есть в разметке страницы только после выполнения JS (мы брали через рендер-прокси `r.jina.ai`, это сторонний сервис, на машине игрока не вариант). Прямого стабильного адреса «последний файл мода» не найдено.

**Условия API Access Terms** (https://mod.io/apiterms, прочитано полностью):
- п. 1.1: ключ запрашивается через аккаунт на `mod.io/me/access`; принятие запроса за mod.io.
- п. 2.1: лицензия «access, implement, and distribute the mod.io API data to End Users for their use via your platform»; непередаваемая и несублицензируемая.
- п. 3.1: использовать только для сайтов, игр, приложений, инструментов и сервисов, полезных игрокам.
- п. 3.2: использовать только ключ, привязанный к собственному аккаунту.
- п. 3.3: **брендинг mod.io обязателен «at all times» при использовании API**; лицензия на логотип дана, материалы — https://mod.io/about.
- п. 3.4: лимиты из https://docs.mod.io/restapi/rate-limiting; многократное превышение может закончиться закрытием аккаунта и ключа.
- п. 3.5: нельзя использовать API, чтобы «bypass or create a competing or replacement product for mod.io», для бенчмарков, «for spamming or scraping data».
- п. 8.3, 10.1, D: mod.io может в любой момент и без уведомления изменить, остановить или заблокировать доступ; API «as is».
- п. 3.7-3.9: соблюдать ToU и закон; п. 11: возмещение убытков mod.io при нарушении.
- Не найдено в документе: норма о сторонних программах, скачивающих файлы по прямой ссылке без ключа; про кэширование ответов API; про показ чужих обложек.

Игровые условия (Game Terms) — для администратора игры openxcom, не для нас; текст не открывали.

### Обложки и картинки

На страницах: логотип (`og:image`, кроп 1280x720) и галерея; миниатюры отдаются публично с `thumb.modcdn.io/mods/<hash>/<mod id>/crop_<размер>/<файл>` без ключа.

| Игра | Логотип (имя файла) | Файлов-картинок на странице (оценка, с учётом дублей «.1») |
|---|---|---|
| X-Com Files | `planet.jpg` | 27 |
| World of Silence | `terror_from_the_deep_by_kilzig-d.jpg` | 8 |
| RoSigma | `rosigma_logo.png` | 39 |
| X-Chronicles | `philiphofmanner.jpeg` | 11 |
| Mars-com | `title.2.png` | 12 |

Условия показа в чужом приложении:
- mod.io: права на загруженное принадлежат автору; ToU даёт лицензию mod.io и администратору игры. Отдельного разрешения «сторонним приложениям показывать обложки» в ToU **не найдено**. API Access Terms п. 2.1 разрешает распространять «mod.io API data» (в ней есть адреса медиа) игрокам через свою платформу; при получении адресов страницей/рендером, а не API, этой лицензии у нас нет. Обязателен брендинг mod.io (п. 3.3).
- Автор: права на показ обложек и скриншотов страниц **не проверены ни у одного релиза**: заявления авторов о лицензии (раздел «Права и лицензии») относятся к моду, а не к картинкам на странице, у TWoTS, 40k и RoSigma лицензии нет вовсе.
- Вероятно сторонние работы в логотипах (по имени файла, не проверено): TWoTS — `terror_from_the_deep_by_kilzig` (имя в духе DeviantArt), X-Chronicles — `philiphofmanner`. Авторство и право показа не выяснены.

## Проверено в коде
- `src/version.h:23-26` — `OPENXCOM_VERSION_ENGINE "Extended"`, `OPENXCOM_VERSION_NUMBER 8,7,1,0` (в задании было 8.7.0; фактически рабочее дерево 8.7.1).
- `src/Engine/ModInfo.cpp:203-264` — какие поля metadata читает наш движок (`id`, `isMaster`, `master`, `requiredExtendedVersion`, `requiredExtendedEngine`, `resourceConfig`, `loadResources`, `requiredMasterModVersion`, `reservedSpace`).
- `src/Engine/ModInfo.cpp:182-199` — поддерживаемые движки: `Extended`, `OXCE-HD` (наш), пустое имя.
- `src/Engine/ModInfo.cpp:299-302` — `canActivate`.
- `src/Engine/CrossPlatform.cpp:1853` — `isHigherThanCurrentVersion` сравнивает покомпонентно по четырём числам; `8.7` не выше `8.7.1.0`.
- `src/Menu/ModListState.cpp:91` — комментарий про недовлитую интеграцию mod.io; другого кода mod.io в `src/` нет (grep по `mod.io|modio` — один файл).

## Источники
- Страницы модов (рендер через r.jina.ai, потому что сами страницы без JS пусты): https://mod.io/g/openxcom/m/the-x-com-files , https://mod.io/g/openxcom/m/the-world-of-terrifying-silence , https://mod.io/g/openxcom/m/rosigma , https://mod.io/g/openxcom/m/x-chronicles , https://mod.io/g/openxcom/m/mars-com , https://mod.io/g/openxcom/m/40k — id, версия, размер, ссылки скачивания, описания, лицензионные строки Nord, число зависимостей, список изображений.
- Архивы mod.io (только конец файла и `metadata.yml` через Range): ссылки вида `https://g-51.modapi.io/v1/games/51/mods/<mod>/files/<file>/download` из таблицы — `metadata.yml`, список языков, состав папок, размер и Last-Modified.
- https://docs.mod.io/restapiref/ — аутентификация, лимиты, объекты Modfile/Download/Game, `api_access_options`.
- https://mod.io/apiterms — API Access Terms (прочитано полностью).
- https://mod.io/terms — Terms of Use; первая сверка читала резюме https://mod.io/legal/terms, разделы 3, 4, 6, 9 перечитаны 02.10.2026 по полному тексту.
- https://openxcom.org/forum/index.php?topic=6556.0 и `.30` — анонс mod.io-портала (2018; Scott из mod.io: «The API can also be consumed in a read-only anonymous manner»; ToU: автор сохраняет права; рекомендации авторам); SupSuper о встроенном браузере (2019, 2021). Это цитата 2018 года, **про текущее поведение ключей не говорит**.
- https://openxcom.org/forum/index.php?topic=10233.0 (X-Chronicles), `13072` (Mars-com), `5566` (TWoTS+, автор Nord), `13220` (форк Murkhach), `9687` (ROSIGMA), `5026` (40k).
- https://raw.githubusercontent.com/SolariusScorch/XComFiles/master/README.md , `.../X-Com_Files_readme.txt` , `.../metadata.yml` , https://api.github.com/repos/SolariusScorch/XComFiles/releases — лицензия CC BY-NC, языки, журнал 4.2 (2026-09-21), ветка master = 4.3-dev.
- https://codeberg.org/LeflairKunstler/ROSIGMA (`raw/tag/3.2/metadata.yml`, `api/v1/repos/.../releases`, `Language/`) — metadata релиза 3.2, README.
- https://github.com/BeatAroundTheBuscher/OXCE_40k и `.../ROSIGMA` (архив старых релизов 2.x с zip-ассетами на GitHub, 2023) — metadata 40k, языки.
- Локально: `E:\Additional mods\openxcom_xfiles_42.zip` (248 338 351 Б), `E:\Additional mods\rosigma3.2.4.zip` (418 070 246 Б) — только чтение `metadata.yml` и списка файлов.
- Сверка прав 02.10.2026: архивы mod.io по ссылкам из таблицы (только центральный каталог и малые файлы: readme, README.md, `Art Credit.txt`, `TerroristWeaponsLicense.txt`, `metadata.yml`, `Language/*.yml`); локальный `E:\Additional mods\openxcom_xfiles_42.zip` (сверен по каталогу с файлом mod.io 8236968); страницы mod.io, рендер `r.jina.ai`; https://mod.io/terms , https://mod.io/apiterms , https://mod.io/gameterms; https://creativecommons.org/licenses/by-nc/4.0/legalcode.en , https://creativecommons.org/licenses/by-nc-sa/4.0/legalcode.en (номера пунктов 1(9), 2(a)(5)(B), 3(a), 3(b)); https://openxcom.org/forum/index.php?topic=10233.0 , `13072`, `5566`, `13220`, `5026`, `9687`, `4595`; https://raw.githubusercontent.com/SolariusScorch/XComFiles/master/README.md и тег 4.2; https://codeberg.org/LeflairKunstler/ROSIGMA (`main` и тег `3.2`, README); https://github.com/BeatAroundTheBuscher/OXCE_40k (содержимое корня, поле license); `Пиратки\Dioxine_XPiratez\XPiratez readme\XPiratez_readme.txt` (только чтение).

## Чего НЕ выяснил
- **Значение `api_access_options` у игры openxcom** (разрешён ли доступ сторонним программам к API игры) и кто её администратор: нужен пробный вызов с ключом `GET /games/51`.
- **Выдаст ли mod.io пользовательский ключ** на `me/access` под лаунчер и в какие сроки; делится ли лимит 60/мин между всеми игроками одного ключа или считается по клиенту (документация говорит «per key», без разбора случая «ключ внутри приложения у многих игроков»).
- Как mod.io относится к прямой ссылке `…/download` без ключа в стороннем приложении: API Access Terms про это молчат, а адрес находится на домене API (`modapi.io`). Ответ нужен от mod.io (legal@mod.io) или от администратора игры.
- Срок жизни подписи `verify=` на CDN; совпадает ли `filehash.md5` в API с ETag (для файлов без `-N`).
- Лицензии (права на раздачу и адаптацию) - **что осталось не выяснено по каждому релизу**: X-Com Files - письменное подтверждение версии 4.0, охвата архива и списка исключений (музыка `SOUND/*.ogg`, чужие файлы), условия подмода `XCF Cyrillic Names`; X-Chronicles и Mars-com - версия лицензии и перечень заимствованного у других авторов (Mars-com - ещё ссылка на текст лицензии), условия `XCHR Cyrillic Names`; World of Silence - разрешение Nord и авторов включённых модов (Blank, tyran_nick, Xops, new_civilian, pWWWa); 40k - ohartenstein23, bulletdesigner, Ryskeliini, Hobbes (карты Terrainpack); ROSIGMA - Leflair, Buscher, Xom126, Dioxine (активы XPZ), авторы иллюстраций. Авторам не писали.
- MD5 релизных файлов: API без ключа недоступен; ETag на CDN у пяти из шести - составной (`-N`), не MD5. У Mars-com ETag без суффикса (`38f6901ea2d3bb867056246fcf2208ed`) - возможно MD5, не проверено (файл целиком не качали).
- Редакции ToU, API Access Terms и Game Terms: даты на страницах не указаны, текст прочитан 02.10.2026; support-статью mod.io «Terms of Use & policies update - 2024» не читали. Включены ли у авторов «Enhanced License Rights» (ToU п. 6.2(2)) - со стороны не видно.
- Юридическая оценка (считается ли HD-слой, полученный из кадров мода, «Adapted Material»; считается ли лаунчер «NonCommercial» при рекламе или донатах) - не выяснялась; это вопрос к владельцу проекта и юристу, не к разведке.
- Происхождение локального `rosigma3.2.4.zip` и чем он отличается от `rosigma.zip` на mod.io (размер, две записи).
- Есть ли на mod.io отдельные версии 40k без катсцен (1,03 ГБ): «View 42 other versions» не открывали.
- Права на показ обложек и логотипов (оригинальных работ в логотипах TWoTS и X-Chronicles).
- id и размеры вспомогательных модов mod.io (музыка XCF, Army Painter, саундтреки RoSigma, минимоды).
- Результат запуска пяти игр в нашем форке: проверяли только `metadata.yml`, но не загрузку рулсетов.

## Что это значит для лаунчера

- **Скачивать с mod.io без ключа технически можно**: прямая ссылка по `mod id / file id` отдаёт файл анонимно, Range работает, размеры и даты в таблице. Нельзя без ключа **узнать, что вышла новая версия**: для этого нужен API с ключом (или ручное обновление каталога).
- Для каталога схемы 2 (`upstream: url, sha256, size`) подходит закрепление на конкретный `file id`: файл на CDN не меняется, а `sha256` посчитаем сами (API даёт только MD5). Версия в `metadata.yml` архив не идентифицирует (пример RoSigma 3.2: два разных zip с одним текстом metadata).
- Какие релизы можно выкладывать своей копией: **ни один не имеет проверенного разрешения** (вердикты UNVERIFIED, подробности и что нужно для проверки - в разделе «Права и лицензии»). Ближе всего X-Com Files 4.2 (явное заявление автора в самом архиве), но с оговоркой про чужое содержимое и с музыкой из коммерческих игр; у X-Chronicles и Mars-com заявление только на странице, у остальных трёх лицензии нет. Для World of Silence, 40k и ROSIGMA - только `upstream` или «укажите скачанный архив».
- Две независимые неопределённости. Техническая: допускают ли условия mod.io скачивание файлов сторонней программой по прямой ссылке без ключа (API Access Terms про это молчат). Правовая: условия mod.io прав на раздачу **не дают** (ToU п. 6.2(1), (7); API Access Terms п. 2.1 - про «API data», не про файлы), право на раздачу определяется только лицензией автора, а её проверенной нет. Закреплённые id решают первое, но не второе. Если API нужен - либо одобренный ключ (брендинг mod.io обязателен, ключ привязан к нашему аккаунту, лимит 60/мин у пользовательского ключа), либо письмо в mod.io / администратору игры.
- Структура игр для каталога: три мастера поверх UFO, одна игра на TFTD, одна игра в два уровня (`40k` -> `40k_ROSIGMA_edits`). `engineMaster` у RoSigma = `40k`, у TWoTS = `xcom2` — это подтверждено `metadata.yml`, догадок не осталось.
- Данные ванильной игры нужны двух видов (UFO и TFTD): сборка TWoTS без TFTD работать не будет, а остальные четыре — без UFO.
- Все пять требуют OXCE 8.5-8.7; наш `8.7.1.0` их принимает, но Nord выпустил три мода под 8.7 в один день — каталог будет устаревать.
- Обложки: публичные, но условий показа в стороннем приложении нет, а лицензий авторов на картинки страниц нет ни у одного релиза; безопаснее брать через API (п. 2.1) с брендингом mod.io; право на показ у автора не подтверждено нигде.
