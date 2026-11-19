# Исправление А2: лаунчер (ветка worktree-agent-ae07ec2318a3a6efa)

Сделано (сборка Portal.slnx Release: 0 предупреждений, 0 ошибок; Core.Tests 545 зелёных, Ui.Tests 41 зелёный):
- #4 самообновление: хэш и копия в `LauncherRelease.FetchAsync` идут в `Task.Run`, вызов в `MainWindow.SelfUpdateAsync` тоже; тест на поток вызывающего. Коммит 594a51d0e.
- #3 push-to-talk: хуки и сторож (WM_TIMER) живут на отдельном потоке с `GetMessage`, в UI только `Post`; устаревшие фронты отбрасываются. Руками в игре не проверено. Тот же коммит 594a51d0e.
- #15 `KnowsModCheck` читает exe блоками по 1 МБ с нахлёстом (`LuaSubmit.ContainsAsync`), тесты на границе блока; #16 `Split` в LuaMods только для `user/mods/`. Коммит d7746dfb0.
- #14 удалены Review.cs, Pck.cs, Png.cs и тесты ReviewTests, PckTests (0 ссылок вне них); `ReviewException` и `ReviewTaskStore.DefaultRoot` перенесены в ReviewTasks.cs. Коммит d018f3914 (удаления попали в 594a51d0e).

Не сделано (по слову координатора, токены): кэш манифеста по хэшу указателя; проба `IlcOptimizationPreference=Size` (база: exe 36 847 616 Б при 0.5.4); версия 0.5.5; строки CHANGELOG и next.en.txt; экран «я здесь» (в аудите это решение для Vitali, плюс он питает уведомления).
Для сборки в worktree скопирован portal/third_party (в git не идёт); NativeAOT из Git Bash требует vswhere в PATH.
