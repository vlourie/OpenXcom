# OXCE-HD <ВЫПУСК> — stable

Source of the binaries of this release: tag `hd-<ВЫПУСК>` (commit `<SHA>`), branch `hd-render`.
The engine is free software under the GNU GPL v3 (`LICENSE.txt`); the licences of the third-party libraries are in
`THIRD-PARTY-NOTICES.txt`, both files are next to the executable. OXCE-HD is an unofficial fork of OpenXcom
Extended 8.7.1 and is not made, endorsed or supported by the OpenXcom or OXCE developers, nor by Dioxine.

This release brings the results of an engine audit (AUDIT-05): 49 commits, no new features. Battle mechanics,
balance and random numbers are unchanged; old saves load. The numbers below were measured on one bench
(X-Piratez with the HD mods, 1920x1080, scale 4) and will differ on other machines. We do not claim that the
game is free of bugs or that every line of code is covered by tests.

## English

### Performance
- The game starts faster: 2.4 -> about 1.5-1.8 seconds to the main menu.
- A late campaign saves about two and a half times faster (0.6 -> 0.24 s).
- In long campaigns the research list and the after-battle awards screen open faster.

### Memory
- The main menu takes about 50-60 MB less.
- After a battle the game no longer keeps enlarged copies of every frame the battle opened - only of those
  actually drawn: at scale 4 after three battles about 810 MB instead of 1020, in battle about 1170 instead of
  1350. This path works on Windows only; other platforms keep the previous behaviour.
- Writing a save no longer takes an extra half a gigabyte of memory for a moment.

### Stability
- Loading a save either gives the loaded game or leaves the current one: a damaged or unfit save is refused with
  a message instead of closing the game or spoiling the battle in progress.
- Loading a battle saved at another HD scale no longer leaves the game half-way.
- If the generator cannot build a battle map, the game says so and returns to the globe instead of closing.
- Base defence: the attack goes by phases, the facilities fire at the UFO once; a failed battle generation is no
  longer counted as the enemy leaving.
- Stores: nothing is bought or transferred beyond the capacity, cargo on the way is counted; very large deal sums
  no longer overflow; a transfer with zero travel time is delivered once.
- Rare battle cases no longer close the game: a throw by a unit with zero strength, a unit without time units in
  the reaction score, a high-rank reinforcement, a map without route nodes.
- Video card mode: a single driver error recreates the resources; after several in a row the mode is switched off
  for the session instead of crashing.
- If the game does crash, `openxcom.log` keeps a record of the place, also for a crash outside the main thread
  (Windows x64).

### Security
- Damaged or wrongly built mod files (music, sounds, fonts, maps, videos, pictures) are refused with a message in
  the log instead of reading memory outside the file.
- Pictures are read by our own build of SDL_image (branch SDL-1.2 with the security fixes, `libs/SDL_image`).
- Mod scripts: an endless loop is stopped and named in the log; integer operations no longer close the game.

### Compatibility
- Mod rules are checked after loading (mission - wave - UFO - deployment, mission sites, stage rings); an error
  is named at once, with the name of the rule.
- The picture without enlargement matches the previous one byte for byte on the checked set of frames; saves
  written by the old and the new build from the same state are identical on the checked set.
- Reproducible tests for the fixed defects are in `tests/` (parsers, Adlib, crash trace, SDL_image).

## Русский

### Производительность
- Игра запускается быстрее: до главного меню 2,4 → около 1,5–1,8 секунды.
- Поздняя кампания сохраняется примерно в два с половиной раза быстрее (0,6 → 0,24 с).
- В длинных кампаниях быстрее открываются исследования и экран наград после боя.

### Память
- В главном меню игра занимает примерно на 50–60 МБ меньше.
- После боя игра больше не держит в памяти увеличенные копии всех кадров, которые бой открыл, — только те, что
  действительно рисовались: на масштабе 4 после трёх боёв около 810 МБ вместо 1020, в бою около 1170 вместо 1350.
  Этот путь работает только на Windows; на других платформах поведение прежнее.
- Запись сохранения больше не занимает на время лишние полгигабайта памяти.

### Стабильность
- Загрузка сохранения либо даёт загруженную игру, либо оставляет прежнюю: повреждённый или негодный сейв
  отклоняется окном с сообщением, а не закрывает игру и не портит идущий бой.
- Загрузка боя, сохранённого на другом масштабе HD, больше не оставляет игру в промежуточном состоянии.
- Если генератор не смог собрать карту боя, игра сообщает об этом и возвращает на глобус, а не закрывается.
- Оборона базы: нападение идёт по фазам, сооружения стреляют по НЛО один раз; сбой генерации боя больше не
  засчитывается как уход противника.
- Склад: за предел вместимости ничего не покупается и не отправляется, учитываются грузы в пути; очень большие
  суммы сделок считаются без переполнения; груз с нулевым временем перевозки доставляется один раз.
- Редкие случаи в бою больше не закрывают игру: бросок бойцом с нулевой силой, юнит без единиц времени при
  расчёте реакции, подкрепление высокого ранга, карта без узлов маршрута.
- Режим видеокарты: одиночная ошибка драйвера пересоздаёт ресурсы, после нескольких подряд режим отключается до
  конца сеанса вместо падения.
- Если игра всё же упала, в `openxcom.log` остаётся запись о месте падения, в том числе не в главном потоке
  (Windows x64).

### Безопасность
- Повреждённые или собранные с ошибкой файлы мода (музыка, звуки, шрифты, карты, ролики, картинки) отклоняются
  с сообщением в журнале, а не читают память за пределами файла.
- Картинки читает собственная сборка SDL_image (ветка SDL-1.2 с исправлениями безопасности, `libs/SDL_image`).
- Скрипты модов: бесконечный цикл останавливается и называется в журнале; целочисленные операции больше не
  закрывают игру.

### Совместимость
- Правила мода проверяются после загрузки (миссия — волна — НЛО — развёртывание, площадки миссий, кольца стадий);
  ошибка называется сразу, с именем правила.
- Картинка в режиме без увеличения совпадает с прежней побайтно на проверенном наборе кадров; сейвы, записанные
  старой и новой сборкой из одного состояния, на проверенном наборе совпадают.
- Воспроизводимые тесты исправленных дефектов лежат в `tests/` (разборщики данных, Adlib, запись о падении,
  SDL_image).

## Checksums

```
<SHA-256>  <файл архива>
<SHA-256>  openxcom_hd.exe
```
