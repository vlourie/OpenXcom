# Первый выпуск: пошагово в PowerShell

Для того, кто делает это впервые. Короткая справка для тех, кто уже умеет, — `RELEASING.md`.
Все команды проверены прогоном 2026-09-23 на одноразовом ключе.

Что получится в итоге: на диске `D:\xp-repo` — подписанное хранилище релизов. Лаунчер
скачивает обновления оттуда. Пока хранилище лежит только у тебя на диске, игроки его не видят.
Как выложить его на сервер — последний раздел, «Выложить на сервер».

**Всё то же самое делает один запуск `Выпуск\OXCE_Release.cmd`** — шаги 2, 5–8 и упаковку для
станции из раздела 10 (см. `Выпуск\README.md`). Этот документ — чтобы понимать, что он делает, и
делать руками, если что-то пошло не так.

## 0. Открыть PowerShell

Пуск → набрать `powershell` → Windows PowerShell. Команды вставлять по одной (правый клик
вставляет), после каждой — Enter. Строки с обратной кавычкой `` ` `` в конце — это одна
команда, вставлять их вместе.

```powershell
cd E:\OpenXCom
```

## 1. Один раз: копия ключа и программа подписи

1. Скопировать `D:\keys\xp-prod\release.key` на флешку или в менеджер паролей. Без этого
   файла выпускать обновления нельзя, и восстановить его нечем.
2. Собрать программу подписи `xp-release`:

   ```powershell
   dotnet publish portal\src\Xp.ReleaseBuilder -c Release -o dist\_xp-release
   ```

   Повторять только если менялся код в `portal\src\Xp.ReleaseBuilder`.

## 2. Собрать игру

`Выпуск\OXCE_Build.cmd` → кнопка **«Обе»** (или в PowerShell: `.\Выпуск\OXCE_Build.cmd both`).
Нужна именно «Обе»: только в ней в `dist\_stage` лежат и exe, и моды. Релиз берёт файлы
оттуда.

## 3. Задать имена на этот выпуск

Вставить в то же окно PowerShell. `$id` меняется на каждый выпуск: одно имя дважды
использовать нельзя.

```powershell
$xpr  = 'E:\OpenXCom\dist\_xp-release\xp-release.exe'
$key  = 'D:\keys\xp-prod\release.key'
$pub  = 'D:\keys\xp-prod\release.pub'
$repo = 'D:\xp-repo'
$id   = '2026.09.24-test1'
```

Если закрыл окно, эти пять строк нужно вставить заново: окно их не помнит.

## 4. Текст «Что нового» (по желанию)

Лаунчер показывает его справа на главной. Нет файла — панели нет.

```powershell
New-Item -ItemType Directory -Force D:\xp-notes
notepad "D:\xp-notes\$id.ru.txt"
```

Блокнот спросит, создать ли новый файл, — «Да». Написать, сохранить, закрыть.

## 5. Собрать и подписать релиз

```powershell
& $xpr build --repo $repo --id $id --version 2026.9.24 --channel stable `
    --stage E:\OpenXCom\dist\_stage --launch openxcom_hd.exe `
    --changelog-ru "D:\xp-notes\$id.ru.txt" --key $key
```

Если файла «Что нового» нет — та же команда без него:

```powershell
& $xpr build --repo $repo --id $id --version 2026.9.24 --channel stable `
    --stage E:\OpenXCom\dist\_stage --launch openxcom_hd.exe --key $key
```

Идёт несколько минут: считается хэш почти 40 тысяч файлов. В конце должно быть так:

```
not released from the stage: XPiratezLauncher.exe, libHarfBuzzSharp.dll, ...
  art.hd       art     38140 files  1794.0 MiB
  engine       engine    859 files    43.6 MiB
  mod.intro_voice ...
release 2026.09.24-test1: 39019 files, ... status draft
```

Строка `not released from the stage` — это нормально: лаунчер выпускается отдельно, в шаге 7.
`draft` — черновик, его ещё никто не видит.

## 6. Опубликовать и проверить

```powershell
& $xpr publish --repo $repo --channel stable --id $id --key $key
& $xpr verify --repo $repo --channel stable --pub $pub --deep
```

`verify` должен сказать `OK`. Любые строки `PROBLEM:` — остановиться и разбираться.

## 7. Лаунчер — отдельным релизом

Нужен в первый раз и каждый раз, когда поднималась версия в
`portal\src\Xp.Launcher\Xp.Launcher.csproj` (`<Version>`). Номер в `--id` и `--version` — эта
же версия.

```powershell
& $xpr build --repo $repo --id launcher-0.1.1 --version 0.1.1 --channel launcher-stable `
    --stage E:\OpenXCom\dist\_launcher_rel --launcher-kind --key $key
& $xpr publish --repo $repo --channel launcher-stable --id launcher-0.1.1 --key $key
```

Сейчас версия 0.1.1: в ней лаунчер уже смотрит на сервер, а не на `localhost`. Собирать сам
лаунчер отдельно не надо: сборка «Обе» из шага 2 кладёт свежий в `dist\_launcher_rel`.

Должно быть `5 files`: сам лаунчер, `xp-bootstrap.exe` и три DLL.

## 8. Посмотреть, что получилось

```powershell
& $xpr list --repo $repo
```

## 9. Проверить лаунчером у себя

Во **втором** окне PowerShell запустить раздачу (окно не закрывать, пока проверяешь):

```powershell
& 'E:\OpenXCom\dist\_xp-release\xp-release.exe' serve --repo D:\xp-repo --port 8787
```

В первом окне:

```powershell
$game = 'E:\OpenXCom\Пиратки\Dioxine_XPiratez'
$p = Start-Process "$game\XPiratezLauncher.exe" -ArgumentList '--headless','check','--game',"`"$game`"",'--repo','http://localhost:8787/' -Wait -PassThru -NoNewWindow
$p.ExitCode
```

Число в ответе: `0` — всё уже как в релизе, `3` — есть обновление, `2` — подпись не принята
(значит, подписано не тем ключом), `1` — другая ошибка, текст выше. `--repo` действует только на
эту проверку и в настройки лаунчера не записывается.

Раздачу во втором окне остановить — Ctrl+C.

## Если ошибся

- `release '...' already exists` — это имя уже занято. Поменять `$id` (например `-test2`) и
  повторить с шага 5.
- Опубликовал не то — вернуть канал на предыдущий релиз:
  `& $xpr revoke --repo $repo --channel stable --id $id --key $key`
- `error: ...` с путём к ключу — проверить, что `D:\keys\xp-prod\release.key` на месте.

## 10. Выложить на сервер

Куда: на станцию, в папку `portal\deploy\releases` рядом с `station.ps1`. Её раздаёт тот же
Caddy, что и сайт, по адресу `https://x-piratez.mywire.org:8443/releases/`. Оттуда берут
обновления лаунчеры, и оттуда же сайт показывает текущую версию.

Что: все файлы `D:\xp-repo` — `blobs`, `releases`, `channels`. Порядок важен, и его соблюдает
команда станции: сначала файлы, указатели каналов последними. Иначе лаунчер увидит релиз,
файлов которого на сервере ещё нет.

**Первый раз** — сначала обновить сам сайт: в его новой версии Caddy умеет раздавать
`/releases/`.

1. Здесь, в PowerShell:

   ```powershell
   cd E:\OpenXCom
   powershell -ExecutionPolicy Bypass -File portal\deploy\pack.ps1
   ```

   Получится `dist\xp-portal_<дата>_<коммит>.zip`. На станции распаковать его поверх папки
   сайта и из `portal\deploy` запустить `powershell -ExecutionPolicy Bypass -File .\station.ps1`.

**Каждый раз** (и первый тоже — после обновления сайта):

1. Здесь упаковать хранилище. Упаковывается только то, что изменилось с прошлого раза; первый
   архив — всё хранилище, около 1,8 ГБ:

   ```powershell
   powershell -ExecutionPolicy Bypass -File portal\deploy\pack-releases.ps1
   ```

   Получится `dist\xp-releases_<дата_время>.zip`.
2. Перенести архив на станцию — как обычно переносишь архив сайта.
3. На станции, в PowerShell из `portal\deploy`:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\station.ps1 releases C:\путь\xp-releases_....zip
   ```

   Команда разложит файлы в правильном порядке, в первый раз сама впишет открытый ключ в
   `portal.env` и перезапустит сайт с Caddy. В конце покажет каналы:

   ```
   launcher-stable      -> launcher-0.1.1
   stable               -> 2026.09.24-test1
   ```

   Красная строка `НЕ отвечает` — Caddy не раздаёт папку: запустить `.\station.ps1` (up) и
   повторить.
4. Проверить снаружи — с телефона на мобильном интернете открыть
   `https://x-piratez.mywire.org:8443/releases/channels/stable.json`. Должна показаться строка с
   `"releaseId"`.

Если архив потерялся по дороге и на станцию не попал, следующий упаковывать с `-Full`: скрипт
считает отправленным всё, что однажды упаковал.

После этого лаунчер 0.1.1 у любого игрока сам находит обновления на сервере. Лаунчер 0.1.0,
который уже лежит в Пиратках, смотрит на `localhost` — его один раз заменить руками на 0.1.1
из сборки «Обе».
