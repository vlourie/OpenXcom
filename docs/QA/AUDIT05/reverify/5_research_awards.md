# AUDIT-05, повторная проверка: исследования и награды (пункты D форума)

Дата: 2026-11-22. Только чтение кода и существующих материалов; ничего не запускалось и не правилось.
Состояния: upstream `f0134ef80`, тег `hd-2026.11.20` (`89a709657`), HEAD ветки `hd-render`.
Оба коммита входят в тег (`git merge-base --is-ancestor` — да). `git log --oneline 89a709657..HEAD -- src/Savegame/SavedGame.cpp src/Savegame/SoldierDiary.cpp src/Savegame/SoldierDiary.h` — пусто: с тега эти файлы не менялись, HEAD = тег.

---

## 1. Коммит 70d3cf602 — `SavedGame::getAvailableResearchProjects`

**Место (HEAD):** `src/Savegame/SavedGame.cpp:1895` (функция), правка — строки 1906–1908; upstream — `SavedGame.cpp:1752` (`sortReserchVector(unlocked);` внутри `for (research : _discovered)`).

**Причина.** Вспомогательный вектор `unlocked` (темы из списков «unlocks») пересортировывался после каждой изученной темы: O(D·U log U). Цена росла с возрастом кампании.

**Что сделано.** Одна строка `sortReserchVector(unlocked)` вынесена из цикла на его конец.

### Доказательство эквивалентности (чтение кода)
1. `unlocked` — локальный вектор. Внутри цикла по `_discovered` он только пополняется (`push_back`) и не читается. Читается единственный раз ниже — `haveReserchVector(unlocked, research)` (`SavedGame.cpp:1921` HEAD), двоичным поиском, после цикла. Промежуточные сортировки на итог не влияют; после цикла и в upstream, и в HEAD — отсортированный полный список.
2. Порядок и стабильность. Ключ `researchLess` = `std::less<const RuleResearch*>` — порядок по адресу; равные ключи — один и тот же указатель (неразличимые элементы), поэтому нестабильность `std::sort` не видна. Мультимножество одно и то же, `lower_bound` по нему даёт то же.
3. Крайний случай: `_discovered` пуст — в upstream сортировки не было, в HEAD сортируется пустой вектор — без эффекта.
4. Функция `const`; `_discovered` не меняется; RNG и состояния игры сортировка не касается.
5. Порядок результата `projects` задаётся не `unlocked`, а обходом `mod->getResearchMap()` (`projects.push_back(research)`), этот код не тронут. Потребители порядка: `NewResearchListState.cpp:306`, `GeoscapeState.cpp:2609/2703` (разность «до/после»: `getNewlyAvailableResearchProjects` сама сортирует `before`/`after`, `SavedGame.cpp:1869-1870` upstream), `SavedGame.cpp:1776/1781` (`addFinishedResearch`). Набор и порядок `projects` идентичны.

**Проверено как:** чтение кода (upstream, тег, HEAD). Исполненного сравнения набора/порядка результата нет: ни один прогон не выгружал `projects` до и после.

**Замеры:** `docs/QA/AUDIT05/evidence/E/month_timing.py` (команда `a05month`, таймеры `geo_timing.py`, диагностическая копия `ui_timing_patch.py`). Логи: `evidence/E/runs/month_base_20261119_141235/month.tsv` (до: NoCodexManZ — 9 вызовов, 79,10 мс = 8,8 мс/вызов; PeasGray 6 вызовов, 14,46 мс), `evidence/E/runs/a05month_fix1_20261119_141552/month.tsv` (после: 21,08 мс / 9 = 2,34 мс; PeasGray 6,35 мс; `geo.time1Day` 85,78 → 28,50 мс, в коммите «86 → 28 мс»). Числа 8,8 → 2,3 мс подтверждаются. Оговорки: по одному прогону на сборку, повторов и разброса нет; сборки — диагностические копии с таймерами; сейвы одни и те же файлы из `Пиратки/Dioxine_XPiratez/user/piratez`; вызовов мало (6–9). Совпадение сборок «до/после» по всему, кроме правки, документами не подтверждено (метки `base`/`fix1`).

**Классификация:** исправлено верно. **Статус проверки:** чтение кода + замер (исполнен, одиночный). **Тег/HEAD:** в теге, в HEAD без изменений. **Риски:** нет.
**Нужен ли тест:** желателен дешёвый — выгрузка `projects` (имена по порядку) до и после на 4 сейвах, с `_debug` и без; по построению разницы быть не может.

### Расхождение с форумом (D, п.1)
Форум: «sorts the result inside the loop (`SavedGame.cpp:1752`)». Номер строки верен (upstream 1752), но «the result» неверно: сортируется не результат (`projects`), а вспомогательный список `unlocked`. Исправленная формулировка:
> `SavedGame::getAvailableResearchProjects` re-sorts the helper vector `unlocked` after every discovered topic (`SavedGame.cpp:1752`, `sortReserchVector(unlocked)` inside the loop over `_discovered`), although it is only searched (`std::lower_bound`) after the loop. Sorting it once after the loop gives the same list and the same result: 8.8 ms -> 2.3 ms per call on our month-108 save. Commit `70d3cf602`.

---

## 2. Коммит bdb1cfaff — `SoldierDiary::manageCommendations` и 14 переборов

**Место (HEAD):** `src/Savegame/SoldierDiary.cpp`: помощник `eachOwnMission` — 418–456; `manageCommendations` — с 463 (кеш итогов 475–580, цикл по наградам 580+); upstream: `SoldierDiary.cpp:286` (форум верен), `getMissionTotalFiltered` upstream 858, `getWinTotal` 904. Заголовок `SoldierDiary.h`: +3 строки (шаблон-член).

**Причина.** Для каждой из ~110 применимых наград итоги карьеры считались заново, каждый — вложенным перебором «миссии кампании × миссии бойца»; на каждое убийство и условие строились 4 строки и дважды искался предмет в правилах.

### 2.1. Кеш итогов (`total(T_*)`, `missionTotal`, `nounTotal`)
- Итоги вычисляются лениво (`totalKnown`), ровно тогда, когда до них доходит короткое замыкание `||`, — порядок оценки критериев сохранён.
- Итоги зависят только от `_killList`, `_missionIdList`, `missionStatistics`, `mod`. Единственное, что меняет `manageCommendations`, — `_commendations` (`addDecoration`, `push_back`). Ни один `getXTotal` не читает `_commendations`; уровень следующей награды читается из `_commendations` заново на каждом шаге (`nextCommendationLevel`). Цикл по наградам не двигает `iter`, пока награда выдаётся (повторная оценка после выдачи) — с кешем она оценивается по тем же итогам, что и без него. Устаревания нет.
- `missionTotal` кешируется по `commRule`, а `getMissionTotalFiltered` зависит только от правила — верно.
- `nounTotal` возвращает константную ссылку вместо копии; тело цикла карту не меняет; `std::map` упорядочен по ключу — порядок `modularCommendations` тот же.
- Повтор `totalDaysWounded` в исходном условии сохранён.

### 2.2. Разбор убийств (`KillTerms`, `resolveKills`)
Upstream: при несовпадении с rank/race/weapon/weaponAmmo и 4 строками — `mod->getItem(weapon)`, сверка `battleTypeArray[battleType]`, затем тип урона патрона (`weaponAmmo->getDamageType()->ResistType`, при `__GUNBUTT` — `weapon->getMeleeType()->ResistType`), диапазоны `0 <= x < BATTLE_TYPES/DAMAGE_TYPES`.
HEAD: то же, один раз на убийство в `resolveKills` (`SoldierDiary.cpp:~540–580`); результат — указатели на элементы локальных массивов `battleTypeArray/damageTypeArray` того же вызова (время жизни достаточно); условие совпадения — единое `||`. Для булева ИЛИ порядок проверок не важен, диапазоны сохранены, −1 → нет совпадения.
Отличие: в HEAD поиск предмета и разыменования делаются заранее для всех убийств, в upstream — лишь для не совпавших ранее. `getItem(id, error=false)` не бросает (`Mod.h:869`, возвращает 0); `getDamageType()/getMeleeType()` — указатели на поля-значения `RuleItem` (`_damageType`, `_meleeType`, `RuleItem.cpp:427–454`), не нулевые, так что дополнительного падения нет. Кеш `killTerms` строится один раз за вызов (проверка `killTerms.size() != _killList.size()`); `_killList` в вызове не меняется. Обход убийств по индексу `killNo` — тот же порядок.

### 2.3. `eachOwnMission` и 14 заменённых переборов
Оригинал: `for ms: for missionId in _missionIdList: if missionId == ms->id: действие` — действие по разу на каждую пару (ms, запись списка) с равным id.
HEAD: «индексная» ветка, если для всех `i`: `missionStatistics[i]->id == i`; тогда для каждой записи `missionId` (`0 <= missionId < size`) вызывается действие для `missionStatistics[missionId]`.
- `ms->id == i` для всех i ⇒ id уникальны, каждому `missionId` соответствует не более одного `ms` — ровно `missionStatistics[missionId]`. Отрицательные и вне диапазона id в upstream не находят пары, в HEAD пропускаются. Повторы в `_missionIdList` дают по паре в upstream и по вызову в HEAD — те же кратности.
- Меняется только порядок вызовов; все 14 потребителей суммируют или считают в `std::map` — порядок не важен. Заменены: `getRegionTotal`, `getCountryTotal`, `getTypeTotal`, `getUFOTotal` (карты), `getWinTotal`, `getScoreTotal`, `getLootValueTotal` (суммы), `getTerrorMissionTotal`, `getNightMissionTotal`, `getNightTerrorMissionTotal`, `getBaseDefenseMissionTotal`, `getAlienBaseAssaultTotal`, `getImportantMissionTotal`, `getValiantCruxTotal` (счётчики) — 14. Условия в каждом совпадают с upstream (`success`, `!isBaseDefense()`, `!isUfoMission()`, `!isAlienBase()`, `isDarkness(mod)`, `type != "STR_UFO_CRASH_RECOVERY"`, `valiantCrux`, `score`, `lootValue`).
- «Другая нумерация»: сквозная проверка `ms->id == i` для всех `i` (O(N) на вызов). Если хоть одна миссия не на своём месте (удалённые миссии, пропуски в id, сшитые сейвы, дубли id), используется прежний двойной перебор целиком — результат как в upstream при любых данных. В обычной игре `id = size()` в момент `push_back` (`DebriefingState.cpp:603–604`), миссии нигде не удаляются (в других местах `getMissionStatistics()` только читается), поэтому индексная ветка — штатная.
- `getMissionTotalFiltered`: upstream считал миссии с `ms->success`, у которых `ms->id` есть в `_missionIdList` (по одному разу на миссию), и тип/маркер входит в список правила; приоритет — `missionTypeNames`, иначе `missionMarkerNames`, если оба пусты — размер `_missionIdList`. HEAD: те же условия, единичность миссии — через `sort` + `unique` по указателям. Эквивалентно и в индексной, и в неиндексной ветке.

### Исполненные доказательства (п.3)
- Описания: `docs/QA/AUDIT05/AUDIT05_ROOT_CAUSES.md:393–420` и `:430–440`. В `AUDIT05_MASTER.md`, `AUDIT05_FINAL_H.md`, `AUDIT05_LOAD_PERF.md` про награды и исследования ничего нет (grep пуст).
- **Отпечаток наград:** команда `a05medals` в диагностической копии — `evidence/E/ui_timing_patch.py:359–391`: два прохода «`addMonthlyService` + `manageCommendations`» по всем бойцам всех баз, затем FNV-1a хеш по (имя бойца; для каждой награды тип, существительное, `getDecorationLevelInt()`), плюс число бойцов, убийств, выдач, наград. Хеш строгий: тип, существительное, уровень, привязка к бойцу. Прогоны: `evidence/E/runs/a05medals_base_20261119_141831` (до), `a05medals_fix2_20261119_142114`, `a05medals_fix2b_20261119_142217`, `a05medals_fix3_20261119_142436` (после). **В этих папках только `.tsv` таймеров; строки ответа игры (`ok soldiers=… hash=…`) не сохранены, `grep medals=` / `hash=` в `docs/QA/AUDIT05` находит только исходник патча.** Значит, «отпечатки совпали на 919 бойцах, 29 297 наград, 413 выдачах» (ROOT_CAUSES:409–411) — словесное утверждение; по сохранённому логу числа не проверить. «869» в сообщении коммита — ошибка, отчёт её признаёт (919).
- **Путь месячного отчёта:** `evidence/E/medals_month_test.py NoCodexManZ.sav <сборка до bdb1cfaff> <build-asan> 2`; лог `evidence/E/runs/medals_month_20261119_150209.txt`: до прогона 18 126 наград, после месяца 0 — 18 209, месяца 1 — 18 220 в обеих сборках; «A и B построчно совпали»; отчётов ASan/UBSan нет; ИТОГ: ДА. Оговорки: сравниваются только строки `commendationName: …` из сейва (в скрипте регулярка `commendationName: [^\n}]*`), без привязки к бойцу, один сейв, сравниваются сборка «до bdb1cfaff» и сборка ASan, то есть разные конфигурации. Слабее отпечатка `a05medals`, но независимое подтверждение.
- **Время:** `a05medals_base_…/month.tsv`, `SoldierDiary.manageCommendations` на кампаниях PeasGray / RedCatZ / GoldGalZ / NoCodexManZ (вызовов 308 / 304 / 516 / 710): до 2771 / 8448 / 10 685 / 39 962 мс; `a05medals_fix2_…`: 135 / 390 / 532 / 2435 мс; `a05medals_fix3_…`: 121 / 326 / 435 / 1594 мс (отдельные таймеры `getMissionTotalFiltered` 33,8 мс, `getTrapKillTotal` 18,6 мс …). 710 вызовов = два прохода по 355 бойцам: 39,96 / 2 ≈ 20 с на проход → 1,59 / 2 ≈ 0,8 с. Совпадает с «20 с → 0,8 с». `fix2b` (`…142217`): 2409 мс против 2435 мс (fix2) на NoCodexManZ — единственный повтор, разброс ~1 %; других повторов, средних и разброса нет, база измерена один раз. Сборки — диагностическая копия с таймерами; сейвы те же. Замеры «итоги боя 70 бойцов 8,1 → 0,36 с» (`a05battle_base_20261119_141608`, `a05battle_fix3_20261119_143220`) здесь не открывались.
- **Не доказано исполнением:** сейв с неиндексной нумерацией миссий (удалённые/пропущенные id, дубли id, дубли в `_missionIdList`, отрицательные id). На реальных кампаниях нумерация индексная (иначе ускорения не было бы: в fix3 4205 вызовов `getMissionTotalFiltered` = 33,8 мс). Эквивалентность неиндексной ветки обоснована лишь построением: она буквально повторяет прежний перебор.

**Классификация:** исправлено верно (кеш и 14 переборов); поведение сохраняется при любой нумерации. «Неполная правка» неприменима: оставшийся перебор «награды с killCriteria × убийства» описан и сознательно не тронут (ROOT_CAUSES:417–419).
**Статус проверки:** исполнено (`evidence/E/medals_month_test.py`, `runs/medals_month_20261119_150209.txt`; `a05medals` — результат только в тексте, сырого лога нет) + чтение кода.
**Тег/HEAD:** в теге; HEAD совпадает с тегом.
**Риски:** (1) нет сохранённого сырого вывода `a05medals`; (2) в неиндексных сейвах выигрыша нет (прежний O(N·M)) и добавляется O(N) проверка на вызов — не регрессия по результату, но возможное лёгкое замедление на очень длинных кампаниях с дырами; (3) заранее выполняемый разбор убийств даёт лишние вычисления на наградах без совпадений — на корректность не влияет; (4) указатели `terms.battleType/damageType` на локальные массивы корректны лишь внутри вызова (так и есть).
**Тесты, которые стоит добавить:** (а) отпечаток наград (`a05medals`, с сохранением сырого `ok … hash=…` в файл) на сейве с удалёнными/переставленными миссиями (id с пропусками, неиндексная нумерация) на сборках upstream и HEAD; (б) то же на сейве с дублями номеров в `_missionIdList` и наградами с `missionTypeNames`/`missionMarkerNames` (проверка `getMissionTotalFiltered`); (в) награда с `killCriteria`, где `detail` равен `BT_FIREARM` / `DT_AP` / `DT_MELEE`, и оружие с `__GUNBUTT`; (г) юнит-тест `eachOwnMission` в `tests/` с несколькими нумерациями.

### Расхождение с форумом (D, п.2)
Форум: «`SoldierDiary::manageCommendations` (`SoldierDiary.cpp:286`) recounts the career totals for every commendation of every soldier. With the totals computed once per soldier the monthly report on a month-108 save went from about 20 s to 0.8 s … the awarded commendations were compared and are the same.»
- Номер строки верен (upstream 286).
- «once per soldier» неточно: итоги теперь считаются один раз за вызов `manageCommendations` (вызов — на одного бойца, но повторные вызовы по тому же бойцу, как в месячном отчёте или цикле выдачи, считают заново).
- 20 с / 0,8 с — время одного прохода по всем бойцам кампании NoCodexManZ (355 бойцов), измеренное таймерами диагностической копии; в логах 40,0 → 1,6 с за два прохода.
- «one machine and one save» — измерено на четырёх сейвах (на малых ускорение меньше: PeasGray 2,8 с → 0,12 с за два прохода); сравнение наград выполнено на четырёх кампаниях (отпечаток, только в тексте) и на одной (построчно по логу).
Предлагаемая формулировка:
> `SoldierDiary::manageCommendations` (`SoldierDiary.cpp:286`) recomputes the career totals (14 nested loops "all campaign missions x the soldier's missions", plus per-kill string building and item lookups) for every commendation it checks, so the cost grows as awards x missions x career. Computing each total at most once per call (and replacing the 14 loops by one helper that indexes the mission list when mission ids equal their list positions, falling back to the old nested loop otherwise) brought a full monthly pass over all soldiers of a month-108 save from about 20 s to 0.8 s (two diagnostic passes: 40.0 s -> 1.6 s; one machine, four saves, single runs). The awarded commendations (type, noun, level per soldier) were compared before and after and are identical.

---

## Сводная таблица

| Коммит / пункт | Место (HEAD) | Классификация | Проверка | Тег | HEAD | Тест нужен |
|---|---|---|---|---|---|---|
| 70d3cf602, сортировка `unlocked` один раз | `SavedGame.cpp:1895–1908` | исправлено верно (набор и порядок те же: список только ищется после цикла; ключ — адрес, равные ключи — один объект) | чтение кода + замер 8,8 → 2,3 мс (`runs/month_base_20261119_141235`, `a05month_fix1_20261119_141552`, по одному прогону) | в теге | без изменений | желателен: выгрузка `projects` до/после |
| форум D.1 (текст) | `forum-…:125` | ошибка описания: сортируется не «the result», а вспомогательный `unlocked` | сверка с upstream 1752 | — | — | поправить текст |
| bdb1cfaff, кеш итогов и разбор убийств | `SoldierDiary.cpp:475–580, 730–850` | исправлено верно | чтение кода + исполнено (`medals_month_test.py`: 18 126 → 18 220 наград, построчно; `a05medals` — только в тексте) | в теге | без изменений | да: отпечаток с сохранением сырого лога |
| bdb1cfaff, `eachOwnMission` + 14 переборов | `SoldierDiary.cpp:418–456` и функции `getXTotal` | исправлено верно; нестандартная нумерация — прежний перебор целиком | чтение кода; на неиндексных данных не исполнялось | в теге | без изменений | да: сейв с удалёнными миссиями / дублями id |
| `getMissionTotalFiltered` (тип/маркер) | `SoldierDiary.cpp:~1087` | исправлено верно (тот же приоритет типов над маркерами, та же единичность миссии) | чтение кода | в теге | без изменений | да: дубли в `_missionIdList`, награды с типами/маркерами |
| замеры 20 → 0,8 с | `evidence/E/runs/a05medals_*` | подтверждены (на проход: 39,96 / 2 → 1,59 / 2 с); повтор только fix2/fix2b (~1 %); общего разброса нет | исполнено, одиночные прогоны, диагностическая копия | — | — | повтор N≥5 с разбросом, если число идёт в публикацию |
| форум D.2 (текст) | `forum-…:126–128` | ошибка описания (мелкая): «once per soldier» → «once per call»; «one save» → четыре сейва; 20 с — на проход; в сообщении коммита 869 вместо 919 | сверка с upstream 286 | — | — | поправить текст |

Подлинных расхождений поведения (вход → другой результат) не найдено.
