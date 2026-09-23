# Выпуск

| Файл | Что делает |
|---|---|
| `OXCE_Build.cmd` | только сборка: окно с кнопками EXE / Мод / Обе (скрипты — `tools\build`) |
| `OXCE_Release.cmd` | **выпуск целиком**: сборка «Обе» → подпись → публикация → проверка → архив для станции |
| `release_config.json` | пути к ключу, хранилищу и прочему для `OXCE_Release.cmd` |
| `notes\next.ru.txt` | «Что нового» для следующего выпуска (по желанию; есть и `next.en.txt`) |

## Как выпустить

1. Если хочешь текст «Что нового» — написать его в `notes\next.ru.txt`.
2. Двойной клик по `OXCE_Release.cmd`. Ждать «ГОТОВО» зелёным. Сборка идёт десятки минут,
   подпись и проверка — минуту-две.
3. Архив `dist\xp-releases_<дата_время>.zip` отнести на станцию и там, в PowerShell из
   `C:\xp-portal\portal\deploy`:

   ```powershell
   $z = (Get-ChildItem C:\XPiratezModHD\xp-releases_*.zip | Sort-Object LastWriteTime | Select-Object -Last 1).FullName
   powershell -ExecutionPolicy Bypass -File .\station.ps1 releases $z
   ```

Если в `release_config.json` указать `StationDrop` — общую папку станции (например
`\\STATION\XPiratezModHD`; в JSON обратные косые удваиваются: `"\\\\STATION\\XPiratezModHD"`),
архив туда скопируется сам, и останется только шаг на станции.

## Что он решает сам

- **Имя выпуска** — по дате: `2026.09.24`, второй за день `2026.09.24-2`. В канале `test` —
  `2026.09.24-test`, `2026.09.24-test2`. Версия — `2026.9.24` (`2026.9.24.2`).
- **Лаунчер** выпускается, только когда поднята его версия (`<Version>` в
  `portal\src\Xp.Launcher\Xp.Launcher.csproj`). Из папки лаунчера берутся ровно его 5 файлов,
  посторонние (архивы, `.pdb`) пропускаются.
- **xp-release** пересобирается сам, если менялся его код.
- **«Что нового»** после выпуска переименовывается в `notes\<имя выпуска>.ru.txt` — следующий
  выпуск старый текст не покажет.
- **Упаковка для станции** — только то, что изменилось с прошлого раза.

## Варианты запуска

Из PowerShell в `E:\OpenXCom`:

```powershell
.\Выпуск\OXCE_Release.cmd                 # канал stable, со сборкой
.\Выпуск\OXCE_Release.cmd nobuild         # без сборки: подписать то, что уже лежит в dist\_stage
.\Выпуск\OXCE_Release.cmd test            # в канал test (свой лаунчер-канал launcher-test)
```

Журнал каждого запуска — `dist\release_<дата_время>.log`.

## Если что-то не так

- `нет приватного ключа` — не подключён диск `D:` с `D:\keys\xp-prod\release.key`.
- Ошибка на сборке — смотреть вывод сборки выше, ничего ещё не подписано.
- Опубликовал не то — откатить канал на прошлый выпуск:

  ```powershell
  & E:\OpenXCom\dist\_xp-release\xp-release.exe revoke --repo D:\xp-repo --channel stable --id <имя> --key D:\keys\xp-prod\release.key
  ```

  Потом упаковать и отнести на станцию как обычно (`OXCE_Release.cmd` тут не нужен:
  `powershell -ExecutionPolicy Bypass -File portal\deploy\pack-releases.ps1`).

Пошагово руками, с объяснением каждого шага — `docs\portal\FIRST_RELEASE.md`.
