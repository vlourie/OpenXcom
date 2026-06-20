OXCE Global Transfers AutoBuild v145
===================================

Этот пакет добавляет в OXCE/QOL новый экран:

  Глобальный вид -> ОБЗОР ВСЕХ ДОСТАВОК

Исправление v145:
  - обработчик GeoscapeState::btnGlobalTransfersClick теперь вынесен в отдельный файл
    src/Geoscape/GeoscapeGlobalTransfers.cpp;
  - это исправляет ошибку линковки LNK2001 unresolved external symbol btnGlobalTransfersClick.

Как использовать:
1. Распакуй архив.
2. Загрузи содержимое архива в корень fork-репозитория rackrossum/OpenXcom поверх старых файлов:
   .github
   tools
   README_RU.txt
3. Commit directly to community_build.
4. Actions -> Build Global Transfers patched OXCE -> Run workflow.

После успешной сборки скачай artifact oxce_global_transfers_windows.

Кнопка/горячая клавиша появится в настройках:
  OXCE -> Глобальный вид -> ОБЗОР ВСЕХ ДОСТАВОК

По умолчанию клавиша не назначена, чтобы не конфликтовать с твоими текущими настройками.
