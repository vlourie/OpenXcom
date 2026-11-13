# fix-A: четыре правки безопасности (сайт и лаунчер), 09.11.2026

Не закоммичено. Диф: `git diff -- portal`, плюс новый файл `portal/tests/Xp.Portal.Tests/LuaModArchiveTests.cs`.

## 1. Zip-бомба в ReadMetadata
- `portal/src/Xp.Manifest/LuaModArchive.cs` (`ReadMetadata`): поток записи читается кусками в буфер 64 КиБ + 1; если пришло больше 64 КиБ - `null`.
  Прежняя проверка `entry.Length` осталась.
- Поведение .NET 10: поток записи сам обрезается на заявленной длине (без исключения). Заявлено 100 байт при 5 МиБ реальных -
  читается ровно 100 байт, `InvalidDataException` нет. То есть с ZipArchive лживый заголовок «вниз» бомбой не был; ограниченное
  чтение - защита в глубину (на случай смены поведения библиотеки).
- Тесты: `portal/tests/Xp.Portal.Tests/LuaModArchiveTests.cs` (3): честный малый файл читается; честный >64 КиБ отвергается;
  заголовок с занижением (правятся локальный заголовок и центральный каталог) - читается ровно заявленное, не мегабайты.
  Они без БД, 3 из 3 зелёные.

## 2. Ключ бота review
- `portal/deploy/station.ps1`: параметр `-Networks` (строка, CIDR/адреса через запятую); `bot-review` передаёт `--networks`,
  если задан, иначе печатает жёлтое предупреждение «сеть не задана» и создаёт ключ как раньше. Справка в шапке дополнена.
  `BotApi.Allowed` не тронут. BOM на месте (EF BB BF), разбор PowerShell - 0 ошибок. Реальную команду не запускал (Docker).

## 3. libsodium в установщике
- `portal/src/Xp.Bootstrapper/Installer.cs` `LoadSodium`: ветка «libsodium.dll рядом с exe» убрана целиком; всегда пишется
  встроенный ресурс во временную папку. `LoadSodium` вызывается только из режима установки (запуск без аргументов, `Installer.Run`);
  режим самообновления (`--pid/--source/...`) его не зовёт, а xp-bootstrap запускается лаунчером из временной копии, так что
  сценария, где нужен libsodium рядом, нет. Ресурс встроен всегда (`Xp.Bootstrapper.csproj`). Обоснование - в комментарии.

## 4. Токен устройства в лаунчере
- `ReviewTasks.cs` `ReviewFileAsync`: проверка теперь хост + схема + порт.
- `Reports.cs`: `PortalClient.NewHttpClient(timeout)` - клиент с `SocketsHttpHandler { AllowAutoRedirect = false }`; в `ThrowIfFailedAsync`
  любой 3xx - `PortalException` с кодом `redirect_refused` и понятным текстом. Все заголовки `X-Device-Token`/`X-Ticket-Token`
  уходят через `PortalClient`, поэтому достаточно клиентов, которые ему отдают.
- Клиенты, которые отдают `PortalClient`, заменены на `NewHttpClient`: AccountPanel, Dialogues, ModdingPanel, ReportWindow,
  ReviewPage, VoicePage, ReviewSmoke (по одной строке). SupportPage не тронут: публичный список без токена.
- Тесты `portal/tests/Xp.Launcher.Core.Tests/ReviewTaskTests.cs` (+3): (а) другой порт и другая схема отвергаются, запрос не уходит;
  (б) ответ 302 на запрос с токеном - `redirect_refused`; (в) настоящий редирект через два `HttpListener`: клиент лаунчера
  не идёт на «чужой» порт, а обычный `HttpClient` (контроль) идёт и несёт токен - то есть тест видит утечку.

## Проверка
- `dotnet build portal/Portal.slnx -c Release`: 0 предупреждений, 0 ошибок.
- `Xp.Launcher.Core.Tests`: 550 passed, 0 failed.
- `Xp.Portal.Tests`: 16 passed, 256 failed - все падения из-за отсутствия Postgres на localhost:5433 (Npgsql, PortalFactory),
  не из-за правок. Одноразовый кластер (R-651) поднять не удалось: запуск initdb/pg_ctl запрещён правами сессии. БД-тесты
  (в т.ч. `LuaModApiTests`, использующие `ReadMetadata`) не прогнаны. Нужно прогнать там, где Postgres есть.
- `Xp.Launcher.Ui.Tests` не запускал (UI-клиенты менялись лишь заменой строки инициализации; сборка зелёная).
- Версию лаунчера не поднимал.

## Приёмка (ведущая сессия, 09.11)
- Диф прочитан целиком; `dotnet test` с фильтрами повторён: ReviewTaskTests 45 из 45, LuaModArchiveTests 3 из 3.
- Правка 2 (`-Networks`) оставлена как флаг на будущее, **перевыпуск ключа не нужен и не поможет**: Caddy портала в Docker Desktop
  видит каждого внешнего клиента как шлюз `172.30.10.1` (и `remote_ip`, и `X-Forwarded-For` в журнале `xp-portal-caddy-1`), так что
  `BotApi.Allowed` с любой реальной сетью либо пропустит всех, либо никого. Записано граблями (docs/rakes/portal.md).
- Коммиты: по одному на правку (архив, station.ps1, установщик, токен лаунчера).

## Дополнение (09.11 14:35)
- Тесты сайта с базой прогнаны ведущей сессией на одноразовом Postgres (R-651): Xp.Portal.Tests 272 из 272, в том числе LuaModApiTests с ReadMetadata. Пункт «не прогнаны» снят.
