# Приёмка: интро в упакованном выпуске 2026.10.17-3

Дата: 2026-10-17. Коммиты: `5ccb5eeb8`, `8a03d16f3`; автоматический коммит выпуска `b1e35c400`.

## Вердикт

ГОДЕН. Сверка происхождения исполняемого файла R-087 пройдена от упаковщика до манифеста и blob в архиве станции; запуск именно упакованного stage exe подтвердил интро.

## Проверено

| Что | Шаги | Ожидалось | Получилось | Итог |
|---|---|---|---|---|
| Один packed exe во всех копиях | Get-FileHash SHA256 для `dist/_stage/openxcom_hd.exe`, `dist/_work/openxcom_boxed.exe`, `Пиратки/Dioxine_XPiratez/openxcom_hd.exe` | Одинаковый SHA | Все три: `BFE4F025E5FFA692A128E9AEC08FDB346AC4F34C270B7C2EA30E563BE6C75398` | PASS |
| Manifest указывает проверенный exe | Прочитать `D:/xp-repo/releases/2026.10.17-3/manifest.json`, найти `files.path=openxcom_hd.exe` | SHA и размер соответствуют stage | SHA выше, size=39231867, component=engine | PASS |
| Указатель stable | Сверить release.json, channels/stable.json и SHA256 manifest | Published, нужная версия/manifest | Published `2026.10.17-3`, sequence=87; manifest SHA `6dfdc26a3244bb37e96c92aae6261c86448617e5c4eda90e5a0ce32c66cd1665` | PASS |
| Архив содержит именно этот exe | Прочитать ZIP blob `blobs/sha256/bf/bfe4f025e5ffa692a128e9aec08fdb346ac4f34c270b7c2ea30e563be6c75398`, вычислить SHA256 | Совпадает со stage | 39231867 байт; SHA совпал | PASS |
| Manifest/channel в архиве | Прочитать ZIP manifest и stable.json; сравнить с хранилищем, ZipFile.testzip | Совпадают, CRC без ошибок | Manifest побайтно совпал; stable releaseId/sequence совпали; testzip=None | PASS |
| Runtime packed exe | `py -3 tools/game_hidden.py --out E:/OpenXCom/scratchpad/intro-fix-2026-10-17/packed-cold.png --save '' --master piratez --set 'playIntro=true;oxceGentleAsk=false;oxceAdultAsk=false' --user E:/OpenXCom/scratchpad/intro-fix-2026-10-17/packed-user --exe E:/OpenXCom/dist/_stage/openxcom_hd.exe --after 60` | Intro SlideshowState с voiceintro | `OpenXcom started successfully`, SlideshowState, voiceintro_01/02/03; packed-cold.png записан, процесс PID 4376 завершён с кодом 0 | PASS |

Архив: `dist/xp-releases_2026-10-17_214416.zip`, SHA256 `73092F6C17B2F3EE08992CD0905F361FD07AAFB48A09B9817172A22045FED623`. Это delta для существующего хранилища станции; всего 17 ZIP entries, 4 новых blob. Для остальных файлов выпуска нужны ранее доставленные blob. Это не самостоятельный установочный комплект.

`dist/release_2026-10-17_214251.log`: обе штатные проверки хранилища дают OK; финальная строка подтверждает выпуск `2026.10.17-3` в stable. Первая попытка выпуска ранее остановилась на Get-FileHash из-за окружения PSModulePath; успешный повтор выполнили со стандартным PSModulePath, исходный фикс интро не менялся. Эта причина передана директором, отдельного воспроизведения первой попытки QA не делал.

## Дефекты

Новых дефектов упакованного исправления не найдено. Лог packed-прогона содержит тот же фон установленных модов, что baseline: 89 `ufopaedia item misses type_id attribute`, два предупреждения о версии модов, 152 HD-картинки без соответствующего имени. `not found in`, `is far from` и FATAL отсутствуют. Это не новые диагностики выпуска; подробнее — `intro-startup-2026-10-17.md`.

## Не проверено и почему

- Доставка архива на удалённую станцию и фактическое предложение обновления лаунчером: в этой локальной проверке доступа к станции не использовалось.
- Слышимый звук, весь ролик и интерактивный чистый профиль: запуск намеренно Hidden/dummy, музыка=0, вопросы выключены только в отдельном cfg. Правка громкость не меняет.
- Подписи отдельно не проверялись этим прогоном: записаны результаты двух штатных verify OK из release log.
- Дополнительные проверки механики/рендера не повторялись; это узкая сверка упаковки и cold startup после основной приёмки.
