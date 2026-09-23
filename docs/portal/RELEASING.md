# Выпуск релиза и обновления лаунчера

Кто делает: тот, у кого закрытый ключ релизов. Ключ в гит не идёт никогда (`*.key` в
`portal/.gitignore`), хранится только на машине релиза. Схема хранилища — `ARCHITECTURE.md`, раздел 4.
Первый раз — по `FIRST_RELEASE.md`: там то же самое пошагово, с командами для PowerShell.

## Один раз: ключ

```powershell
cd portal
dotnet run --project src\Xp.ReleaseBuilder -c Release -- keygen --out D:\keys\xp-prod
```

- `release.key` — закрытый; положить в сейф и в резервную копию, **потерять = выпустить новый лаунчер вручную**.
- Содержимое `release.pub` дописать строкой `prod <base64>` в `portal/keys/release-keys.txt` и закоммитить.
- Без строки `prod` релизная сборка лаунчера останавливается: такой лаунчер не доверял бы ничему.

Смена ключа: новый `prod` добавить в список, выпустить лаунчер с обоими ключами, и только
после того, как им обновились игроки, подписывать новым и убирать старый.

## Каждый релиз игры

1. Собрать игру как обычно — `tools\build\build.ps1` кладёт готовый каталог в `dist\_stage`.
2. Собрать релиз (черновик, игроки его ещё не видят):

   ```powershell
   $env:XP_RELEASE_KEY = 'D:\keys\xp-prod\release.key'
   xp-release build --repo D:\xp-repo --id 2026.10.1-hd --version 2026.10.1 --channel test `
       --stage ..\dist\_stage --changelog-ru notes.ru.txt --changelog-en notes.en.txt
   ```

   Файлы хранятся по содержимому: второй релиз заливает только новые блобы.
3. Проверить черновик: `xp-release verify --repo D:\xp-repo --channel test --pub <release.pub> --deep`.
4. Опубликовать в `test`: `xp-release publish --repo D:\xp-repo --channel test --id 2026.10.1-hd`.
5. Обновиться тестовым лаунчером, сыграть. Потом тот же `--id` публикуется в `stable` —
   пересобирать не нужно.
6. Выложить изменившиеся файлы хранилища на сервер (блобы — **до** указателей каналов, иначе
   игрок увидит релиз, файлов которого ещё нет): здесь `portal\deploy\pack-releases.ps1`, на
   станции `.\station.ps1 releases <архив>`. Хранилище лежит в `portal\deploy\releases` станции и
   раздаётся по `https://x-piratez.mywire.org:8443/releases/`. Пошагово — `FIRST_RELEASE.md`, раздел 10.

Плохой релиз: `xp-release revoke --repo D:\xp-repo --channel stable --id <id>` — канал
возвращается на предыдущий опубликованный релиз, номер канала растёт, лаунчеры откатываются.

## Обновление самого лаунчера

```powershell
cd portal
.\publish.ps1 -Out ..\dist\_launcher            # релиз; для локальной проверки -DevKeys
xp-release build --repo D:\xp-repo --id launcher-0.2.0 --version 0.2.0 --channel launcher-stable `
    --stage ..\dist\_launcher --launcher-kind
xp-release publish --repo D:\xp-repo --channel launcher-stable --id launcher-0.2.0
```

Версию поднять в `src\Xp.Launcher\Xp.Launcher.csproj` (`<Version>`): лаунчер сравнивает её
со своей. `publish.ps1` сам находит vswhere и MSVC — без них NativeAOT не линкуется (грабли R-002).

## Локальная проверка без сервера

```powershell
xp-release serve --repo D:\xp-repo --port 8787
XPiratezLauncher.exe --headless check  --game <игра> --repo http://localhost:8787/
XPiratezLauncher.exe --headless update --game <игра>
```

Команды `--headless`: `check` (ничего не меняет, код 3 — есть обновление), `update` (файлы,
изменённые игроком, оставляет), `repair` (возвращает всё как в релизе), `rollback`,
`self-update`. Коды выхода: 0 готово, 1 ошибка, 2 отказ (подпись, игра запущена).
