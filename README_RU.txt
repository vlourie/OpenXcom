OXCE Global Transfers AutoBuild
================================

Это пакет, который добавляет в rackrossum/OpenXcom community_build:

  OXCE -> Глобальный вид -> ОБЗОР ВСЕХ ДОСТАВОК

и собирает Windows openxcom.exe через GitHub Actions.

Почему через GitHub Actions:
- готовый openxcom.exe должен собираться под Windows через Visual Studio/MSBuild;
- оригинальный репозиторий уже использует Windows workflow с msbuild OpenXcom.2010.sln;
- локальная среда ChatGPT не имеет Windows/MSBuild/Visual Studio XP toolset.

Как использовать:

1. Открой https://github.com/rackrossum/OpenXcom
2. Нажми Fork.
3. В своём fork выбери ветку community_build.
4. Распакуй содержимое этого архива в корень fork-репозитория.
   Должны появиться:

   tools/apply_global_transfers_patch.py
   tools/global_transfers/GlobalTransfersState.cpp
   tools/global_transfers/GlobalTransfersState.h
   .github/workflows/build-global-transfers.yml

5. Сделай commit и push.
6. Открой вкладку Actions.
7. Выбери workflow:

   Build Global Transfers patched OXCE

8. Нажми Run workflow.
9. Когда сборка закончится, скачай artifact:

   oxce_global_transfers_windows

10. Внутри будет ZIP с новым OpenXcom.exe.
    Сделай бэкап старого openxcom.exe и замени новым.

Клавиша:
- По умолчанию новая горячая клавиша не назначена: SDLK_UNKNOWN.
- Зайди в настройки игры:

  OXCE -> Глобальный вид -> ОБЗОР ВСЕХ ДОСТАВОК

  и назначь любую удобную кнопку.

Что делает окно:
- показывает доставки сразу по всем базам;
- колонки: БАЗА / ДОСТАВКА / КОЛ-ВО / ЧАСОВ;
- клик по строке открывает обычное окно доставок выбранной базы.

