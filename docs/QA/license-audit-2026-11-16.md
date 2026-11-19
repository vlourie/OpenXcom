# Лицензия, название и mod.io: проверка 2026-11-16

Повод: пересказ неофициальных мнений команды OpenXcom (нарушение GPL закрытым лаунчером, исходники
«не рядом», название похоже на официальный форк, возможные препятствия на mod.io).
Это разбор по тексту GPL v3 и FAQ FSF, а не заключение юриста. Ничего не менялось: только чтение
репозитория, установки, сайта и страницы mod.io.

## 1. Что проверено и что нашлось

| Что | Состояние |
|---|---|
| Лицензия движка | GPL v3, `LICENSE.txt` в корне, репозиторий `github.com/vlourie/OpenXcom` открыт |
| Исходник каждого выпуска | метка `hd-<выпуск>` ставится и отправляется из `release.ps1`; `hd-2026.11.16-2` на GitHub есть |
| Лаунчер, сайт, установщик | частный репозиторий `vlourie/xp-portal` (решение 09.11), лицензии нет никакой |
| Код GPL внутри лаунчера | поиском шапок GPL в `portal/src/*.cs` не найден |
| Связь игры и лаунчера | только запуск процесса (`Feedback.cpp:237`, CreateProcess) и файлы; закрытых DLL движок не грузит |
| `LICENSE.txt` в выпуске | **в `dist/_stage` его нет** (в установке он есть только из пакета Пираток) |
| Указание на исходник рядом с бинарником | сайт: ссылка на корень репозитория в шапке и подвале; mod.io: **нет**; лаунчер: **нет**; папка игры: **нет** |
| Описание репозитория на GitHub | **«Open-source clone of the original X-Com», сайт openxcom.org**; ветка по умолчанию `oxce-plus` с README OpenXcom |
| Заголовок окна и главное меню | «OpenXcom Extended 8.7.1 (vlourie + MuRuCoN)» (`main.cpp:127`, `MainMenuState.cpp:280`) |
| Сообщение о сбое | **«please report it on the OpenXcom forum (OXCE board)»** (`CrossPlatform.cpp:1559`) |
| Шапки новых файлов `Hd*` | «Copyright 2010-2026 OpenXcom Developers. This file is part of OpenXcom» |
| Сайт | заголовок «X-Piratez — X-Piratez», «ENGINE: OpenXcom Extended 8.7.1 + HD»; слова «неофициальный» нет |
| mod.io | «OXCE HD», оценка 50 % (12 голосов), 157 скачиваний; файл — zip с установщиком 3 МБ; зависимости: X-Piratez и **OXCE Meridian**; метка **Terror From The Deep**; есть фраза «not an official release»; ссылки на исходник и слова GPL нет; про ИИ-графику не сказано, в обсуждении 3 из 5 отзывов — «AI slop» |
| README в папке игры | стоковый «OpenXcom 1.0»; `HD_README.txt` от 17.10 |

## 2. Разбор обвинений

### «Свой закрытый лаунчер нарушает GPL» — нет, но слабые места есть

GPL распространяется на программу и производные от неё. Отдельная программа, которая скачивает
и запускает GPL-программу как процесс, производной не становится: это «aggregate»
(GPL v3 §5, последний абзац; FAQ FSF `#MereAggregation`, `#GPLInProprietarySystem`).
У нас ровно так: лаунчер написан с нуля на .NET, с движком общается запуском и файлами.

Что всё же надо закрыть:

- у лаунчера нет ни лицензии, ни списка чужих компонентов (Avalonia, SkiaSharp, HarfBuzz, libsodium,
  LiveKit FFI, NVorbis, Markdig, miniaudio) — их лицензии требуют упоминания;
- движок сейчас нельзя получить без лаунчера. GPL этого не запрещает, но именно это и читается как
  «exclusive launcher». Снимается выкладкой сборки движка обычным архивом (см. 3.2);
- вопрос «зачем закрытый» останется. Самый сильный ход — открыть исходник лаунчера (без ключей и
  серверной части). Это решение Vitali; юридически оно не обязательно.

### «Исходники должны идти ВМЕСТЕ с бинарником, ссылки на GitHub мало» — неверно, но у нас не доделано

GPL v3 §6(d): при раздаче с сервера исходник может лежать на другом сервере, если **рядом с
бинарником есть ясное указание, где он**, и он доступен так же свободно (FAQ `#SourceAndBinaryOnDifferentSites`).
Метки на каждый выпуск у нас есть. Не хватает «ясного указания рядом»:

- на mod.io, в лаунчере и в папке игры его нет вовсе;
- на сайте ссылка ведёт в корень репозитория, где ветка по умолчанию — чужая `oxce-plus`;
- в выпуске нет `LICENSE.txt` — копию лицензии обязаны получать вместе с программой (§4, §6). Это
  единственное прямое нарушение буквы, чинится одним файлом;
- никто не проверял, что метка собирается с чистого клона в тот же exe (нужен один прогон).

### «Название OXCE-HD выдаёт себя за официальный форк» — закон не требует менять, но поводы мы даём сами

GPL имён не касается; о зарегистрированном знаке «OXCE» мне неизвестно (не проверял). Brutal-OXCE и
«OXCE 8.7.1-hires» cybragon живут с таким же именем. Но в продукте есть места, где мы буквально
представляемся OpenXcom/OXCE:

- главное меню и заголовок окна: «OpenXcom Extended 8.7.1»;
- сбой отправляет игрока **на форум OpenXcom** — ровно то, чего они боятся («crap lands at OpenXCOM's doorstep»);
- описание и сайт репозитория на GitHub — от OpenXcom;
- шапки наших новых файлов приписывают код «OpenXcom Developers»;
- сейвы пишут `engine: Extended` — сейв нашей сборки неотличим от сейва OXCE. Менять нельзя без
  проверки загрузки (это уже совместимость сейвов), но в отчёт об ошибке стоит дописывать, что сборка наша.

Отдельно: сайт называется просто «X-Piratez» (заголовок, домен, `XPiratezLauncher.exe`). Это похоже на
официальный сайт Пираток сильнее, чем OXCE-HD — на официальный OXCE. Dioxine уже отзывался о проекте резко.

Мой вывод: **название не менять, но везде добавить «unofficial fork» и убрать перечисленное.** Спокойнее
всего — прямо спросить Meridian, устраивает ли имя.

### mod.io

По условиям mod.io администратор игры (команда OpenXcom) может ограничить любой мод без объяснений.
Правом тут не защититься — только безупречной страницей и отношениями. Что на странице может раздражать:

- вместо мода выложен exe-загрузчик, который тянет всё с нашего сервера мимо проверки mod.io;
- в зависимостях OXCE Meridian, хотя его сборка не нужна и не используется;
- метка TFTD (если TFTD не проверен — убрать);
- нет исходника, лицензии, слова об ИИ-графике, адреса для ошибок;
- «Official Website» рядом со словами OXCE и X-Piratez.

## 3. Что сделать

### 3.1 Сразу, без спорных решений

1. **Выпуск:** класть в папку игры `LICENSE.txt` и `OXCE-HD-README.txt` (текст ниже) с точной ссылкой на метку.
2. **Игра:** сообщение о сбое — на наш сайт; главное меню и заголовок — «OXCE-HD <выпуск> — unofficial fork
   of OpenXcom Extended 8.7.1». Картинка k=1 не затрагивается, механика тоже; правка через очередь.
3. **GitHub:** описание «OXCE-HD — unofficial fork of OpenXcom Extended (HD rendering layer). Not affiliated
   with OpenXcom/OXCE», сайт — наш; ветка по умолчанию `hd-render`; README с английским началом и блоком
   «Fork notice»; убрать из README ссылки на закрытые `portal/` и `docs/portal/`.
4. **Сайт:** подвал и страница загрузки — текст ниже; ссылка на исходник ведёт на метку текущего выпуска;
   заголовок «X-Piratez HD (unofficial)»; строка движка «OXCE-HD (unofficial fork of OXCE 8.7.1)».
5. **Лаунчер:** окно «О программе»: неофициальность, лицензия движка, ссылка на метку установленной сборки,
   лицензии чужих компонентов (`THIRD-PARTY-NOTICES.txt` рядом с exe), куда слать ошибки.
6. **mod.io:** новый верх описания (текст ниже), убрать зависимость OXCE, проверить метку TFTD,
   «Official Website» → «Project website».
7. **Новые файлы кода** впредь: «Copyright 2026 OXCE-HD contributors» + та же шапка GPL. Старые массово не трогать.

### 3.2 Решения Vitali

- **A. Сборка без лаунчера.** На каждый выпуск — GitHub Release на метке: zip с `openxcom_hd.exe`, dll,
  `common`, `standard`, `LICENSE.txt`. Исходник GitHub прикладывает сам, «в том же месте» — претензия
  по §6 и слово «exclusive» снимаются полностью. Рекомендую.
- **B. Открыть исходник лаунчера** (без ключей, серверной части и токенов). Юридически не нужно,
  но закрывает главный раздражитель. Если нет — одна честная фраза, почему закрыт.
- **C. Название.** Оставить OXCE-HD с «unofficial» или уйти от «OXCE». Рекомендую оставить и спросить Meridian.
- **D. Тема на форуме OpenXcom** (черновик от 29.10, `forum-gpl-source-2026-10-29.md`): если не создана — создать,
  дополнив пунктами этого отчёта; ответить и администраторам mod.io до того, как они начнут действовать.
- **E. Пожертвования «HD developers… for the new graphics».** GPL не мешает, но графика сделана по чужим
  работам (Dioxine и авторы из Credits Пираток, Microprose). Формулировку лучше свести к «launcher, site, servers».

### 3.3 Как обновлять mod.io дальше

- в «Что нового» каждого файла — строка `Engine source for this build: <ссылка на метку>`;
- версия файла = версия лаунчера, в описании — номер выпуска игры;
- описание правится только из `docs/portal/MODIO-PAGE.en.md`, верхний блок не убирать;
- при появлении варианта A — давать на странице и прямую ссылку на архив без лаунчера.

## 4. Готовые тексты (английский)

**Верх страницы mod.io и страница загрузки сайта**

> **OXCE-HD is an unofficial fork of OpenXcom Extended 8.7.1.** It is not made, endorsed or supported by the
> OpenXcom or OXCE developers, nor by Dioxine. Please report problems to us (link), not to the OpenXcom forum.
>
> - Engine: GPL v3. Source of every released build: https://github.com/vlourie/OpenXcom (tag `hd-<release>`).
> - What you download here: a small installer. It installs our launcher, which downloads the engine build and
>   HD packs from our server, and X-Piratez from its author's page. The launcher is a separate program
>   and is not part of the engine.
> - The HD artwork and voices are made with AI tools from the original game art. Everything HD can be switched
>   off; with HD off the picture is byte-identical to OXCE.
> - X-Piratez is by Dioxine and its contributors. OpenXcom by SupSuper and contributors, OXCE by Meridian and Yankes.
> - You need your own copy of UFO: Enemy Unknown / X-COM: UFO Defense.

**`OXCE-HD-README.txt` в папке игры**

> OXCE-HD <release> — unofficial fork of OpenXcom Extended 8.7.1 (https://github.com/MeridianOXC/OpenXcom).
> Modified by the OXCE-HD team since September 2026: 32-bit HD rendering layer, HD interface, effects, Lua mods.
> Licensed under the GNU GPL v3, see LICENSE.txt. No warranty.
> Source code of this exact build: https://github.com/vlourie/OpenXcom/tree/hd-<release>
> Not affiliated with or endorsed by the OpenXcom / OXCE developers. Report bugs at <site>/tickets/new.
> XPiratezLauncher.exe and its libraries are a separate program and are not covered by the GPL.

**Сообщение о сбое**

> This is OXCE-HD, an unofficial build. Please report this error at <site>/tickets/new (F8 in game),
> not on the OpenXcom forum.

**Подвал сайта**

> X-Piratez HD is an unofficial fan project. Engine: OXCE-HD, an unofficial fork of OpenXcom Extended (GPL v3,
> source on GitHub). Based on X-Piratez by Dioxine. Not affiliated with OpenXcom, OXCE or Dioxine.

**Ответ приславшему**

> Thanks for the heads-up, this is useful. Short version of where we stand: the engine is GPL v3 and the source
> of every released build is tagged on GitHub; the launcher is a separate program that only downloads and starts
> the game, it contains no OpenXcom code. We agree the notices were not good enough: we are adding the licence
> and the exact source link to the game folder, the launcher, the site and mod.io, marking the build as an
> unofficial fork everywhere, and pointing crash reports to us instead of the OpenXcom forum. If the OXC/OXCE
> team wants anything else changed, including the name, we would rather hear it directly.
