# Правка B: нагрузка сайта (находки 3, 4, 7 аудита 09.11)

Не закоммичено. Codex не вызывался.

## Что изменено (portal/src/Xp.Portal)
1. `Review/TaskApi.cs` `BotAnswerAsync`: вместо `ToListAsync` по всем ответам - `FirstOrDefaultAsync` по `OrderByDescending(Id)` (одна строка) и отдельный `CountAsync`. Поле `answers` в ответе (`BotAnswerView`) то же, формат не менялся.
2. `Review/TaskService.cs` `PutFileAsync`: список всех файлов заменён на `CountAsync` (только когда файла ещё нет) и `SumAsync(Size)` по остальным файлам - считает база. Порядок проверок и коды ошибок прежние.
3. Потолок ответов: лимита не было. Добавлен `ReviewTaskLimits.AnswersPerTask = 50` (`Data/ReviewTasks.cs`); в `AnswerAsync` после проверки идемпотентности и статуса: `too_many_answers`, HTTP 409 (как соседние `too_many_files`, `task_taken`). Повтор того же Idempotency-Key по-прежнему возвращает "уже принято" и после потолка.
4. `Program.cs` лимит `packs`: оставлен 200 за 10 минут, добавлен комментарий. Причина: лаунчер (`Xp.Launcher.Core/LazyPacks.cs`) спрашивает POST-ом, пока сборка идёт, каждые 5 с до MaxWait (около 3 минут), то есть одно обновление - до ~37 POST. Счётчик считает только не-GET, то есть каждый опрос. За Caddy в Docker все клиенты - один адрес (R-870), лимит общий. 20 за 10 минут сломал бы даже одно обновление, 30 - два одновременных. Реальных чисел из логов станции у меня нет (кода, который их считает, нет), поэтому снижать нечем. Если нужно - сначала снять число POST /api/v1/packs в журнале Caddy за неделю.

## Как проверено
- `dotnet build portal/Portal.slnx -c Release`: 0 предупреждений, 0 ошибок.
- Тесты без БД (LuaApiDocTests, LuaModArchiveTests, ModArtTests, VoiceLobbyTests): 8 из 8.
- Postgres на localhost:5433 не запущен, initdb/pg_ctl не трогал.

## Не проверено (нужна база)
- `dotnet test portal/tests/Xp.Portal.Tests -c Release --filter "FullyQualifiedName~ReviewTaskTests"` (PutFile, Answer, BotAnswer, too_many_files), и `ReviewTests`, `KestrelReviewLimitTests`.
- Нового теста на потолок 50 ответов и на `BotAnswerAsync` со многими ответами нет (в отчёте аудита отмечено как непокрытое); не писал, т.к. запустить его без базы нельзя. SQL `COUNT`/`SUM` по пустому набору: `SumAsync` по `long` даёт 0, но на Postgres не прогонял.

## Приёмка (ведущая сессия, 09.11 14:35)
- Диф прочитан целиком, принят как есть; лимит packs 200 оставлен по доводу исполнителя (одно обновление лаунчера — до ~37 POST, все клиенты за Docker — один адрес, R-870).
- Тесты с базой прогнаны на одноразовом Postgres 18 из MSYS2 (R-651: initdb ICU en-US, порт 5433, роль xp/xpdev, кластер удалён):
  ReviewTaskTests + ReviewTests + KestrelReviewLimitTests + LuaModApiTests — 46 из 46; весь Xp.Portal.Tests — 272 из 272 за 22 с.
- Теста на потолок 50 ответов нет (написать при следующем заходе по сайту).
