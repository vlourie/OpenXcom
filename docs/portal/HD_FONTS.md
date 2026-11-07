# Шрифты пакета `hd_core`: происхождение и условия распространения (02.10.2026, исправлено 03.10.2026)

17 файлов TTF из `user/mods/hd/hd/UI` — всё содержимое будущего `hd_core` (HD_SUBMODS §2).
Все файлы, тексты лицензий и запись источников пишет `tools/hdart/fetch_fonts.py`; источник каждого
файла закреплён коммитом или выпуском и SHA-256, сборка воспроизводима байт в байт (метка времени `head`
берётся у исходника). Юридическая оценка не делалась: ниже — что написано в самих файлах и лицензиях.

## 1. Таблица

| Файл | Гарнитура, версия | Откуда | Лицензия | Изменён нами | SHA-256 |
|---|---|---|---|---|---|
| `FontBig.ttf` | Roboto Medium 2.138, © 2011 Google | `googlefonts/roboto-2`, выпуск v2.138, `roboto-android.zip` → `Roboto-Medium.ttf` | Apache 2.0, `ROBOTO-LICENSE.txt` | нет, совпадает с файлом выпуска | `7984aafeaf43` |
| `FontSmall.ttf` | Roboto 2.138 | тот же архив → `Roboto-Regular.ttf` | Apache 2.0 | нет | `797e35f7f5d6` |
| `FontFallback.ttf` | DejaVu Sans 2.37 | `dejavu-fonts/dejavu-fonts`, выпуск `version_2_37`, `dejavu-fonts-ttf-2.37.tar.bz2` → `ttf/DejaVuSans.ttf` | Bitstream Vera + изменения DejaVu в общественном достоянии, `FONTS-LICENSE.txt` | нет | `7da195a74c55` |
| `fonts/Curvy-Small.ttf`, `-Big.ttf` | **Curvy** — из Comfortaa 3.105 | `google/fonts@db64f6b`, `ofl/comfortaa/Comfortaa[wght].ttf` | OFL 1.1, `Curvy-OFL.txt` | да: вес 400/700, подрезка, **переименован** | `bc5ab7185690` / `3001458f1d92` |
| `fonts/Exo2-*.ttf` | Exo 2 2.010 | `google/fonts@1796e34`, `ofl/exo2/Exo2[wght].ttf` | OFL 1.1, `Exo2-OFL.txt` | да: вес, подрезка | `8c5866b9202b` / `88518e746d9e` |
| `fonts/Jura-*.ttf` | Jura 5.106 | `google/fonts@6e4b84c`, `ofl/jura/Jura[wght].ttf` | OFL 1.1, `Jura-OFL.txt` | да: вес, подрезка | `a3eed7402823` / `7223982605a0` |
| `fonts/MPlusRounded-*.ttf` | Rounded Mplus 1c 1.059 | `google/fonts@84efd8a`, `ofl/mplusrounded1c/MPLUSRounded1c-Regular/Bold.ttf` | OFL 1.1, `MPlusRounded-OFL.txt` | да: подрезка | `b5a1ec695cfb` / `52a663e67b7a` |
| `fonts/Pulse-*.ttf` | **Pulse** — из Play 2.101 | `google/fonts@51c6a42`, `ofl/play/Play-Regular/Bold.ttf` | OFL 1.1, `Pulse-OFL.txt` | да: подрезка, **переименован** | `8026ae7a90c8` / `58260ee7500d` |
| `fonts/Rubik-*.ttf` | Rubik 2.300 | `google/fonts@8b0a1d0`, `ofl/rubik/Rubik[wght].ttf` | OFL 1.1, `Rubik-OFL.txt` | да: вес, подрезка | `1a76c58351c2` / `feb2909259ba` |
| `fonts/Unbounded-*.ttf` | Unbounded 1.701 | `google/fonts@8b0a1d0`, `ofl/unbounded/Unbounded[wght].ttf` | OFL 1.1, `Unbounded-OFL.txt` | да: вес, подрезка | `ec69170d440c` / `938e8e5d3449` |

Полные коммиты, SHA-256 исходников и итоговых файлов — в `FONTS-SOURCES.txt` в корне мода (идёт в
`hd_core`). Таблицы шрифтов, кроме переименованных `name`, совпадают с прежними файлами мода байт в байт
(проверено fontTools по каждой таблице) — переименование и закрепление источников рисунок не изменили.

## 2. Расхождения с условиями — закрыты 03.10.2026

1. **Тексты OFL у шести семейств были чужие** (все начинались строкой Comfortaa: кэш `fetch` по голому
   имени `OFL.txt`). Теперь у каждого семейства свой `<набор>-OFL.txt` с того же коммита, что и шрифт;
   первая строка — авторы своей гарнитуры. У Rounded M+ в `google/fonts` нет `OFL.txt`: строка авторов
   взята из его `METADATA.pb`, текст лицензии — стандартный OFL 1.1 (это записано в `FONTS-SOURCES.txt`).
2. **Текст Apache 2.0 для Roboto** — `ROBOTO-LICENSE.txt` в корне мода, рядом с `FONTS-LICENSE.txt` (DejaVu).
3. **Зарезервированные имена.** По FAQ OFL 2.6 подрезка и инстанс веса — изменение, и п. 3 запрещает
   изменённой версии зарезервированное имя. Comfortaa переименован в **Curvy**, Play (RFN «Play»,
   «Playtype», «Playtype Sans») — в **Pulse**: таблица `name` (семейство, полное и PostScript-имя,
   уникальный ID) и имена файлов. `fetch_fonts.py` останавливается, если зарезервированное имя осталось
   в любой записи `name`. Строки авторских прав и сам текст OFL с RFN сохранены, как требует п. 2.
   У остальных пяти семейств RFN нет. Порядок наборов в опции `oxceHdUiFont` (по имени файла) у Curvy
   и Pulse тот же, что был у Comfortaa и Play: выбор игрока не сдвигается.
4. **Источник Roboto и DejaVu** записан в `FONTS-SOURCES.txt`: файлы мода совпадают байт в байт с
   файлами официальных выпусков (SHA-256 архива и файла), то есть «не изменены» — факт, а не догадка.

## 3. Что значит для раздела

`hd_core` с `targetGames: "*"` распространяется со всеми играми; условия §2 этим закрыты. В `hd_core`
идут шрифты, `*-OFL.txt` рядом с ними, `FONTS-LICENSE.txt`, `ROBOTO-LICENSE.txt` и `FONTS-SOURCES.txt`
(`tools/compat/hd_layout.py`, `docs/research/data/hd_split.tsv`).
