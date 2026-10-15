# HD Pipeline v2 — архитектура production-пайплайна X-Piratez HD

> ТЗ специалиста по архиву конвейера (29.09.2026), переслано Vitali без правок.
> Отзыв и сверка с кодом - docs/research/pipeline-review-2026-09-29.md; спецификация v1.0 - DECISIONS 2026-09-29.
> Ход работ по P0/P1/P2 отмечается в конце файла, раздел «Состояние».

## 0. Зафиксировать Visual Specification v1.0

Записать в `docs/DECISIONS.md`.

Production-графика оценивается только по этим требованиям:

1. **Semantic fidelity — EXACT**
   - предмет должен оставаться тем же предметом;
   - нельзя заменять назначение, количество частей или тип конструкции.

2. **Geometry fidelity — HIGH**
   - силуэт и занимаемая область максимально соответствуют оригиналу;
   - крупные элементы, отверстия, ножки, стойки, проёмы и т. п. сохраняются;
   - допустимы только мелкие изменения, необходимые для нормального HD anti-aliasing и микродеталей.

3. **Material appearance — PHOTOREALISTIC**
   - дерево выглядит как дерево;
   - металл как металл;
   - ткань как ткань;
   - камень как камень;
   - пиксельная фактура оригинала сохраняться не обязана.

4. **Camera / projection — EXACT**
   - исходная изометрия не меняется;
   - нельзя менять высоту камеры, перспективу, направление обзора.

5. **Family consistency — EXACT**
   - одинаковый объект другого цвета остаётся тем же объектом;
   - другой ракурс должен показывать тот же объект;
   - зеркальный вариант должен происходить из того же объекта;
   - части составного объекта должны выглядеть как одна конструкция.

6. **Tile continuity — EXACT**
   - повторяемые элементы не дают видимых швов;
   - поверхности должны продолжаться между клетками;
   - модульные предметы должны совпадать на стыках.

7. **Lighting consistency**
   - единое направление света для семейства;
   - recolor не должен менять физику света;
   - другой цвет не означает другую форму или новое положение источника света.

8. **No generative invention**
   AI может добавлять микродетали материала, но не имеет права:
   - добавлять/удалять ножки;
   - менять число полок;
   - менять отверстия;
   - превращать один предмет в другой;
   - изменять footprint;
   - менять конструкцию ради более красивой картинки.

---

# 1. Главный принцип Pipeline v2

Больше НЕ считать отдельный PNG основной единицей работы.

Основная единица:

`logical asset`

Связь:

`frame → asset → variant/relation`

Пример:

```text
FRNITURE:8
asset_id = chair_arm_01
relation = canonical
view = NW
color = blue

FRNITURE:9
asset_id = chair_arm_01
relation = recolor
view = NW
color = red
```

Генеративная модель должна рисовать `chair_arm_01`, а не независимо `FRNITURE:8` и `FRNITURE:9`.

---

# 2. До окончания этапов A–C GPU production queue остаётся STOPPED

Не запускать массовую генерацию.

Разрешены только маленькие диагностические probes после завершения архитектурной части.

---

# 3. Этап A — исправить систему семейств

Текущий `obj_families.py` использует граф связей и фактически допускает транзитивную склейку:

```text
A похож на B
B похож на C
→ A/B/C
```

Это запрещается.

## Новая модель семейства

У каждого семейства должен быть:

```json
{
  "family_id": "...",
  "canonical": "...",
  "members": [],
  "review": []
}
```

Каждый автоматический член обязан пройти сравнение **непосредственно с canonical**.

Не:

```text
member ↔ любой member
```

а:

```text
candidate ↔ canonical
```

## Алгоритм

### 3.1 Candidate graph можно сохранить

Текущие pairwise comparisons полезны для поиска кандидатов.

Но connectivity используется только для:

`candidate discovery`

и никогда для окончательной принадлежности.

### 3.2 Выбрать canonical

Предпочтительно:

1. наиболее часто используемый вариант;
2. наиболее полный/неповреждённый;
3. лучший representative по размеру/качеству;
4. при равенстве — стабильный deterministic выбор.

Canonical записывается явно.

### 3.3 Проверить каждого кандидата против canonical

Для:

- recolor;
- mirror;
- possible alternate view;
- composite variant.

Если candidate не проходит direct canonical test:

```text
status = REVIEW_REQUIRED
reason = indirect_chain
```

Он не входит автоматически в family.

### 3.4 Никаких автоматических bridge-members

Если:

```text
A↔B = PASS
B↔C = PASS
A↔C = FAIL
```

то:

```text
family = A+B
C = REVIEW_REQUIRED
```

а не A+B+C.

---

# 4. Добавить confidence и reason

Для каждой предполагаемой связи хранить:

```json
{
  "relation": "recolor",
  "confidence": 0.94,
  "evidence": {
    "iou": 0.98,
    "corr": 0.87,
    "edge_corr": 0.91
  },
  "decision": "AUTO"
}
```

Возможные decision:

```text
AUTO
HUMAN_APPROVED
HUMAN_REJECTED
REVIEW_REQUIRED
```

Никакие сомнительные связи не должны молча становиться production-family.

---

# 5. Отдельно различать типы связи

Не объединять понятие «похожий предмет».

Минимальный список:

```text
canonical
exact_duplicate
recolor
mirror
alternate_view
animation_frame
composite_variant
tile_repeat
modular_left
modular_middle
modular_right
damaged_variant
semantic_related
unknown
```

`semantic_related` НЕ означает, что изображения можно выводить друг из друга.

Например два разных деревянных стула могут быть semantic_related, но не одно family asset.

---

# 6. Пересобрать review sheets

После исправления `obj_families.py` создать новые листы.

Показывать семейство вокруг canonical:

```text
CANONICAL

AUTO MEMBERS

REVIEW REQUIRED
```

Для каждого кадра показывать коротко:

```text
set:frame
relation
IoU
corr
edge
direct/indirect
```

Особо вывести отдельный лист:

`indirect_chain_review`

для нынешних 238 кадров, которые попали в семью только через цепочки.

Это сейчас главный обязательный ручной review.

---

# 7. Этап B — единый Asset Inventory

Создать общий machine-readable файл:

`art/manifest/assets.json`

и удобный TSV:

`art/manifest/assets.tsv`

Одна строка на логический кадр.

Минимальные поля:

```text
frame_id
set
frame
asset_id
family_id
canonical
relation
asset_type
material
view
variant
composite
tileable
animation
generator
generator_version
source_revision
status
review_status
output_path
output_hash
```

## asset_type

Минимум:

```text
object
floor_material
wall
structural
fx
unit
ui
pedia
craft
unknown
```

---

# 8. Этап C — provenance manifest

Это обязательное исправление нынешнего смешанного HD-пака.

Нужно иметь возможность для любого файла в игре ответить:

> откуда он появился?

Создать:

`art/manifest/build_manifest.json`

Пример:

```json
{
  "FRNITURE.PCK/8.png": {
    "asset_id": "chair_arm_01",
    "generator": "qwen_photo",
    "generator_version": "v2",
    "derived_from": null,
    "source_frame": "FRNITURE:8",
    "family": "chair_arm_01",
    "revision": 3,
    "created": "...",
    "approved": true,
    "sha256": "..."
  },

  "FRNITURE.PCK/9.png": {
    "asset_id": "chair_arm_01",
    "generator": "derive_recolor",
    "derived_from": "FRNITURE.PCK/8.png",
    "revision": 3,
    "approved": true,
    "sha256": "..."
  }
}
```

Ни один production-файл не должен попадать в HD-пак без manifest entry.

---

# 9. Manifest должен проверять саму установленную игру

Добавить команду:

```text
manifest verify
```

Она сравнивает:

- production source;
- manifest hash;
- файл в игровом HD mod.

Результат:

```text
MATCH
MISSING
UNKNOWN_FILE
HASH_MISMATCH
STALE_REVISION
```

Это должно окончательно убить класс ошибок R-087:

> смотрим один файл, игра загружает другой.

---

# 10. Отказаться от `done_of()` как источника истины

Сейчас `obj_queue.py` пытается определить:

- strict;
- photo;
- «в игре»

через наличие файлов и MD5.

Это полезно для legacy-аудита, но для Pipeline v2 недостаточно.

Источник истины — manifest.

MD5/sha нужен только для проверки физического файла.

Статусы должны идти из БД/manifest:

```text
identified
family_confirmed
generated
derived
review_required
approved
installed
```

---

# 11. Убрать automatic parent decisions из ранней очереди

Сейчас `obj_queue.py` уже умеет назначать:

```text
mirror parent
recolor? parent
```

до полноценной стадии family validation.

В Pipeline v2 очередь не должна решать identity объекта.

`obj_queue.py` занимается только:

```text
discovery / usage / contexts / composites / animations
```

А отношения решает отдельный family stage.

То есть архитектурно:

```text
obj_queue
    ↓
raw assets
    ↓
obj_families
    ↓
validated families
    ↓
generation queue
```

а не обе системы, параллельно пытающиеся определить родителей.

---

# 12. Разделить очередь discovery и очередь генерации

Сделать:

```text
art/objects/discovery/
art/objects/families/
art/objects/generation/
```

## discovery

Что существует в игре.

## families

Что является одной логической вещью.

## generation

Что реально требуется рисовать.

Это разные сущности.

---

# 13. Production generation queue строить только после families

Для каждого family определить минимальный набор AI-задач.

Например:

```text
chair_arm_01

NW blue
NW red
```

не означает две AI-задачи.

Нужно:

```text
GENERATE:
chair_arm_01 / canonical / NW

DERIVE:
red recolor
```

---

# 14. Правило генерации alternate views

Если два кадра — реально две стороны одного объекта:

не генерировать их независимыми jobs.

Основной production режим:

```text
multi-view generation
```

На одном canvas модели показывается один объект:

```text
VIEW A | VIEW B
```

с явной инструкцией:

> This is exactly the same physical object shown from two isometric directions.

После генерации результат режется.

Обе картинки получают один:

```text
asset_revision
generation_id
seed
material_description
```

---

# 15. Recolor

Текущий подход `obj_derive.py` оставить.

Он уже правильно идёт в сторону:

```text
деталь/яркость от HD canonical
цветовая информация от target original
```

Это production-capable направление.

На v2 сейчас НЕ переписывать его полностью.

Добавить только:

1. manifest integration;
2. family revision tracking;
3. QA;
4. возможность позже заменить color transform без регенерации canonical.

---

# 16. Recolor v2.1 — потом

Позже можно выделить:

```text
detail
luminance
albedo/chroma
specular approximation
```

чтобы яркие металлические блики не окрашивались как обычная поверхность.

Это не blocker Pipeline v2.

---

# 17. Mirrors

Различать:

```text
geometric mirror
```

и

```text
same object opposite view
```

Это НЕ одно и то же.

Из-за фиксированного направления света X-Piratez простой flip может дать неправильное освещение.

Поэтому relation `mirror` должна отдельно хранить:

```text
geometry = mirrored
lighting = preserve_world_direction
```

При необходимости после flip делать relighting/reconstruction.

---

# 18. Floors больше не проходят object generation pipeline

Полы выделяются окончательно.

Production:

```text
floor frame
    ↓
material_id
    ↓
large seamless world material
    ↓
world-space sampling
    ↓
isometric projection/mask
```

Не:

```text
tile → diffusion → tile
```

`hd-glue` становится основой production floor architecture после завершения текущего D-stage.

---

# 19. Floor asset — это MATERIAL

Пример:

```json
{
  "material_id": "sand_desert_01",
  "kind": "floor_material",
  "texture": "...",
  "scale": "...",
  "variation": "...",
  "lighting": "...",
  "seed": "..."
}
```

Несколько старых PCK frames могут ссылаться на один material.

---

# 20. Walls / structural assets

Стены не должны обрабатываться как тысячи независимых картинок.

Разделить:

```text
geometry
+
material
```

Geometry:

```text
straight
corner
end
door
window
damaged
junction
```

Material:

```text
silver_metal_01
brick_red_01
concrete_01
wood_wall_01
...
```

Серебряная стена `C_EXT_WALL_SILVER` — отличный первый тест нового подхода, особенно потому что нынешняя family connectivity там дала сильную цепочку.

---

# 21. Tile-repeat / modular objects

Если один кадр физически повторяется рядом с собой и образует один большой объект:

не рисовать независимые клетки.

Для repeating surfaces:

генерировать контекст минимум 3×3 и брать центральную область.

Для линейных конструкций:

```text
LEFT
MIDDLE
RIGHT
```

Для углов:

```text
STRAIGHT
CORNER
END
```

Если части одного предмета различны — они хранят один `asset_id` и разные `part_id`.

---

# 22. Composite objects

Добавить:

```text
asset_id
part_id
part_offset
```

Например кровать:

```text
bed_01/head
bed_01/body
```

AI должен видеть весь composite одновременно.

Нельзя рисовать head и body как независимые вещи.

После одной генерации режем на игровые куски.

---

# 23. Semantic identification становится обязательной стадией

До AI generation у logical asset должен быть:

```text
identity_status = CONFIRMED
```

или:

```text
REVIEW_REQUIRED
```

Модель не запускается для `UNKNOWN`.

Контекст идентификации брать из:

- sprite;
- соседних кадров PCK;
- map crop;
- terrain name;
- MCD properties;
- usage contexts;
- composite membership;
- ruleset hints;
- существующих human hints.

---

# 24. Не давать генератору сырой 32×40 как единственное structural truth

Перед photo-generation создать:

`structural guide`.

Guide должен содержать:

```text
smooth silhouette
major internal edges
holes/openings
anchor/baseline
part boundaries
allowed envelope
```

Строить его из оригинала детерминированно.

Не простым `resize ×4`.

---

# 25. Новый geometry preprocessing

Исследовать:

```text
binary alpha
↓
contour extraction
↓
polygon/polyline
↓
simplification
↓
corner preservation
↓
HD rasterization
↓
anti-alias
```

Задача — убрать информацию:

> это был квадрат 1×1 пиксель

но сохранить информацию:

> здесь был угол / край / отверстие.

---

# 26. AI отвечает за appearance, не за geometry

Разделить ответственность.

Deterministic system отвечает за:

- footprint;
- anchor;
- silhouette constraints;
- part layout;
- tiling;
- family relation.

AI отвечает за:

- материал;
- микродетали;
- natural texture;
- реалистичное shading внутри разрешённой геометрии.

---

# 27. Native RGBA Qwen сохранить

Это хорошая часть текущего pipeline.

Но final alpha нельзя полностью доверять модели.

Использовать:

```text
AI alpha
+
geometry envelope
```

Если модель выходит далеко за допустимую область:

`QA FAIL`.

---

# 28. QA должен быть reject-system

Метрики не выбирают «самую красивую» картинку.

Они только отбраковывают нарушения.

Автоматические hard fails:

```text
wrong dimensions
invalid alpha
gross geometry drift
wrong anchor
family mismatch
composite mismatch
tile seam
unexpected spill
missing part
extra large part
manifest mismatch
```

Human review решает художественное качество среди прошедших QA.

---

# 29. Не использовать один общий numeric beauty score

Запрещается:

```text
score 87 > score 84
→ автоматически выбрать 87
```

Разрешается:

```text
geometry PASS
alpha PASS
family PASS
tile PASS
```

после чего человек выбирает визуально.

---

# 30. Script layout

Пока физически ничего не перемещать.

Сначала ввести логическую классификацию.

Создать файл:

`tools/hdart/SCRIPT_STATUS.json`

со статусами:

```text
CURRENT
EXPERIMENTAL
LEGACY
SPECIALIZED
```

Только после того как v2 запускается end-to-end — физически переносить каталоги.

Это уменьшит шанс сломать импорты.

---

# 31. Предварительная классификация основных скриптов

## CURRENT / основа v2

```text
obj_queue.py          — после упрощения до discovery
obj_families.py       — серьёзно переделать
obj_derive.py         — оставить и встроить в manifest
obj_review.py
obj_batch.py          — после перехода на validated families
extract_pck.py
map_mockup.py
optimize_hd.py
gpuq.py
```

Также production-specialized, если работают:

```text
gen_fire_real.py
fire_real_pack.py
gen_craft_lights.py
gen_reticle.py
pedia_*
upscale_units.py
```

Они решают другие типы ассетов и не должны ломаться из-за нового terrain pipeline.

---

# 32. EXPERIMENTAL

Пока оставить как лабораторию:

```text
probe_object.py
probe_floor.py
vx_control.py
floor_group.py
ground_relief.py
long_object.py
map_paint.py
obj_photo.py
obj_series.py
```

Не использовать их результат автоматически в production pack.

---

# 33. LEGACY / кандидат в attic

После завершения migration:

```text
gen_hd.py                — legacy terrain generator
gen_lora_batch.py
gen_lora_test.py
check_lora.py
merge_gens.py
```

А также старые инструменты, задача которых была выбрать лучший результат между прежними поколениями генераторов.

Не удалять.

Перенести в:

`tools/hdart/attic/`

только после проверки всех импортов.

---

# 34. LoRA

Текущая LoRA не является production source для v2.

Не удалять, но заморозить.

Причина:

training targets были сами сгенерированы другой моделью.

То есть она учит visual prior предыдущей генерации, а не физические материалы.

Возвращаться к LoRA только после стабилизации architecture v2.

---

# 35. Generation records

Каждый запуск AI должен создавать job record:

```json
{
  "generation_id": "...",
  "asset_id": "...",
  "family_revision": 4,
  "model": "...",
  "model_hash": "...",
  "prompt_version": "...",
  "seed": 123,
  "steps": 6,
  "cfg": 1,
  "control": "...",
  "inputs": [],
  "outputs": []
}
```

Никаких безымянных результатов.

---

# 36. Revision invalidation

Если family была изменена человеком:

```text
family revision 4 → 5
```

все генерации старой revision должны получить:

```text
STALE
```

Но физически не удаляться.

Это важно, чтобы исправление ошибки семейства автоматически инвалидировало неправильные derived assets.

---

# 37. Production pack должен собираться, а не редактироваться вручную

Новая команда:

```text
build_hd_pack
```

Берёт только:

```text
approved
current revision
manifest-valid
```

assets.

Папка игрового мода больше не является рабочей папкой художника.

Она является **build output**.

Это критически важно.

---

# 38. Никогда не копировать эксперимент прямо в game HD

Правильный путь:

```text
experiment
↓
candidate
↓
QA
↓
human approval
↓
manifest
↓
build
↓
game
```

Не:

```text
experiment → game folder
```

---

# 39. Сделать reproducible build

На одной и той же версии manifest:

```text
build twice
```

должен дать одинаковый набор файлов и одинаковые hashes.

AI generation к reproducible build уже не относится — build использует одобренные результаты.

---

# 40. Acceptance tests v2

До возобновления массовой GPU-очереди должны проходить следующие тесты.

### T1 Family chain

Искусственно:

```text
A-B PASS
B-C PASS
A-C FAIL
```

C не должен автоматически попадать в family.

### T2 Recolor

Синее/красное кресло:

- одна геометрия;
- один canonical;
- красный derived;
- одинаковый asset_id.

### T3 Alternate view

Два стула:

- один asset_id;
- разные view;
- не две независимые сущности.

### T4 Composite

Кровать:

- одна generation;
- несколько игровых частей;
- корректная сборка на карте.

### T5 Tile object

Повторяемый стол:

- соседние копии не расходятся;
- центральный модуль идентичен.

### T6 Floor

Минимум 10×10 клеток одного материала:

- нет видимой ромбической сетки;
- scroll test проходит;
- нет discontinuity.

### T7 Manifest

Берём случайный PNG из игры.

Система обязана показать:

```text
asset
source
generator
revision
family
approval
hash
```

### T8 Wrong game file

Подменить один PNG вручную.

`manifest verify` обязан поймать mismatch.

---

# 41. Что делать прямо сейчас, без GPU

Порядок строго такой:

## P0

1. Записать Visual Specification v1.0 в `DECISIONS.md`.
2. Исправить `obj_families.py`:
   - canonical;
   - direct comparison;
   - indirect → REVIEW_REQUIRED.
3. Пересобрать family data.
4. Сделать review sheet для 238 indirect-chain кадров.
5. Создать общий Asset Inventory.
6. Создать provenance/build manifest.
7. Перевести `obj_queue.py` в роль discovery, убрать из него роль окончательного family authority.

## P1

8. Связать `obj_derive.py` с family revision и manifest.
9. Сделать manifest verifier.
10. Сделать deterministic pack builder.
11. Ввести status machine для assets.

## P2

12. Подготовить structural-guide pipeline.
13. Сделать первые 10–20 canonical object tests.
14. Только после их принятия размораживать GPU queue.

---

# 42. GPU queue нельзя размораживать просто после исправления families

Условие возобновления production generation:

- family chain исправлен;
- manifest существует;
- игра собирается через builder;
- provenance конкретного PNG можно восстановить;
- canonical/derived разделены;
- минимум несколько representative objects проходят весь Pipeline v2 end-to-end.

После этого генерацию запускать маленькими партиями:

```text
10
→ review
→ 50
→ review
→ 100
→ review
```

И только затем большой batch.

---

# 43. Основной принцип проекта после v2

Задача больше не формулируется:

> перерисовать все кадры X-Piratez.

Она формулируется:

> восстановить логическую библиотеку ассетов X-Piratez, создать качественный canonical representation каждого ассета и детерминированно получить его игровые варианты.

Конечный граф:

```text
GAME DATA
   ↓
DISCOVERY
   ↓
IDENTIFICATION
   ↓
ASSET / FAMILY GRAPH
   ↓
┌────────────────────────────────┐
│ OBJECT                         │
│ canonical AI generation        │
│ → views → recolor → parts      │
├────────────────────────────────┤
│ FLOOR                          │
│ material → world projection    │
├────────────────────────────────┤
│ WALL / STRUCTURAL              │
│ geometry × material            │
├────────────────────────────────┤
│ FX / UI / UNIT / PEDIA         │
│ specialized pipelines          │
└────────────────────────────────┘
   ↓
AUTOMATIC QA
   ↓
HUMAN REVIEW
   ↓
APPROVED ASSET
   ↓
MANIFEST
   ↓
DETERMINISTIC BUILD
   ↓
GAME MOD
```

## Definition of Done

Pipeline v2 считается введённым, когда для любого видимого HD-кадра в игре можно однозначно ответить:

1. Что это за логический объект/материал?
2. К какому family он относится?
3. Какой кадр canonical?
4. Был ли он сгенерирован или выведен?
5. Если выведен — из чего?
6. Каким генератором и revision он создан?
7. Прошёл ли QA?
8. Кто/когда его утвердил?
9. Почему именно этот файл находится сейчас в игровом паке?
10. Можно ли полностью пересобрать этот же пак из manifest без ручного копирования файлов?

Если хотя бы на один пункт система не может ответить — asset pipeline ещё не контролирует этот кадр.

---

## Состояние

- 2026-09-29: P0.1 спецификация записана в DECISIONS.
- 2026-09-29: P0.2-P0.3 obj_families только от канонического: член - прямая связь с каноническим
  (AUTO), цепочка - REVIEW_REQUIRED indirect_chain с путём via, слабое зеркало - weak_mirror, другой
  бок - alternate_view_candidate; решения человека - art/objects/families/decisions.tsv; ревизия
  семейства растёт при смене content_hash. Итог: 1540 семейств (761 с членами), прямых членов 1325,
  на проверку: цепочек 407, слабых зеркал 96, другой бок 2141; плиток 409. Тест tools/test_obj_families.py.
- 2026-09-29: P0.4 листы проверки tools/hdart/family_review.py -> art/_review/families_v2
  (indirect_chain_review_NN - главный ручной разбор, weak, view) с tsv для решений.
- 2026-09-29: P0.5 инвентарь tools/hdart/hd_manifest.py inventory -> art/manifest/assets.json, .tsv:
  36536 кадров, 20668 логических ассетов.
- 2026-09-29: P0.6 манифест сборки hd_manifest.py build -> art/manifest/build_manifest.json: 50383
  файла мода игры с происхождением по sha256; verify - 50383 MATCH. Происхождение UI, FX, юнитов
  unknown: их конвейеры записей не пишут. Тест tools/test_hd_manifest.py (T7, T8).
- 2026-09-29: P0.7 obj_queue - только discovery (art/objects/discovery, parent/derive не назначает;
  номера мест прежние, 5045 из 5045). Очередь генерации tools/hdart/obj_generation.py ->
  art/objects/generation: GENERATE 3720, DERIVE 1325; READY 0 - опознание человеком не подтверждено
  ни у одного (identity.tsv: 129 прежних описаний агента перенесены как REVIEW_REQUIRED), view_pending
  1846, family_review 911. obj_batch берёт только READY. Тест tools/test_obj_generation.py.

### P1-A (2026-09-29)

Условия специалиста до первой десятки - все три выполнены, генерация не запускалась:

1. **Ложные «другой бок» сокращены.** Другой бок ищется по строению, а не по гистограмме цвета
   (tools/hdart/obj_struct.py: воксели LOFT из MCD, поворот на 90/180/270 и зеркало, физика MCD):
   ALT_VIEW_HIGH (AUTO, рисуется одним заказом с каноническим - GENERATE_WITH), POSSIBLE (на
   карточку), REJECT. Пар 4585: HIGH 57, POSSIBLE 957, отсеяно 3571. Обязательная проверка
   473 кандидата вместо 2141 (в 4.5 раза меньше); 79 слабых (0.62-0.70, alternate_view_weak) показаны,
   но заказ не держат. Перекраска и зеркало выводятся (DERIVE), другой бок не выводится никогда.
   Тест tools/test_obj_struct.py.
2. **Класс считается сам.** floor_like (пол по MCD, высота до 22 вокселей), structural (стена по
   Big_Wall 2/3 или 4-9 со Stop_LOS; рельеф, который не горит), object_or_relief (рельеф, который горит:
   кресло или скала - вопрос class_check на карточке), object. Из очереди предметов ушло 884:
   STRUCTURAL 606, FLOOR_LIKE 278.
3. **Опознание на уровне ассета.** art/objects/discovery/asset_identity.tsv - строка на семейство
   (член наследует от канонического): 3012 ассетов, AGENT_PROPOSED 1016, NO_PROPOSAL 1987, SKIP 9.
   Решения человека - identity_decisions.tsv (CONFIRM / EDIT / UNKNOWN / SKIP / NOT_OBJECT),
   старый identity.tsv по кадрам убран. Страница проверки tools/hdart/review_server.py
   (.claude/launch.json: asset-review, порт 8774): карточка - оригинал x4, кадр пака в игре, место на
   карте, члены семейства с кнопками перекраска / зеркало / другой бок / не то, предложение с кнопками
   Верно / Мой текст / Не знаю / Не рисовать / Не предмет; «Пересобрать» гонит obj_families и
   obj_generation. Проверено в песочнице (asset-review-test, --logs): решение доходит до плана, READY.
   Предлагатель tools/hdart/identity_propose.py (Ollama, только через gpuq) пишет proposals.json для
   NO_PROPOSAL - статус AGENT_PROPOSED, к генерации не пускает.
4. **Ревизии по частям.** tools/hdart/asset_rev.py: family_rev, identity_rev, canonical_source_rev,
   member_source_rev, generator_rev, derive_rev; строка плана и запись obj_derive несут inputs и
   input_hash, смена любой части (в т.ч. текста опознания) делает выход STALE.
5. **Пак собирается, а не правится.** tools/hdart/build_hd_pack.py: хранилище по содержимому
   art/store/blobs (5.0 ГБ, блобы только для чтения), желаемое состояние art/manifest/build_manifest.json
   (прежние - history), журнал pack_log.tsv. build собрал пак из манифеста (жёсткие ссылки, 45 с) -
   **IDENTICAL с установленным, 50383 из 50383** (манифест 97a39f319f89). Запись в mods/hd/hd мимо
   сборщика запрещают хуки pack-guard.ps1 (Bash) и guard-paths.ps1 (Write/Edit); obj_push переведён на
   stage + install. Прочие старые писатели (map_update, map_pick, merge_gens, optimize_hd) пока пишут
   напрямую - их запись видна в status как CHANGED/EXTRA и принимается adopt --by <инструмент>.
   Тесты tools/test_build_hd_pack.py, tools/test_pack_guard.py.
6. **Приёмочная десятка.** tools/hdart/acceptance_batch.py -> art/objects/generation/acceptance.json,
   вкладка «десятка» на странице проверки: перекраска - стол FRNITURE 0 (он же плитка, R-136),
   зеркала - кресло FRNITURE 9/8 и стул VILFRNITURE 2 / FRNITURE 3, другой бок - холодильник
   FRNITURE 19, составной - кровать NUKE3 30 (R-132), плитка - рама NUKE2 10, одиночные - коробки
   URBANLUX 76, торшер FRNITURE 10, ящик INDUSLUM 45, бутылки INDUSLUM 55. Только рукотворное (R-125).
   Следующий шаг - Vitali подтверждает опознание и состав семейств десятки; генерация - по его слову.

### P1-B (2026-09-29)

Графика на видеокарте не запускалась. Сделано:

1. **Предлагатель опознания** (tools/hdart/identity_propose.py, Ollama qwen3.8 27B, только через gpuq):
   по NO_PROPOSAL-ассетам спрашивает модель с полным контекстом - канонический кадр и он же x4 без
   художественной правки, члены семейства, набор и кадр, MCD, габарит, места на картах и соседи,
   составной, кандидаты другого бока, имена террейна и рулсета. Ответ: proposed_name / category /
   material, short_description, confidence, evidence, ambiguity, status = PROPOSED. Ответ модели
   **никогда** не становится CONFIRMED и не открывает ассет для генерации (obj_generation держит
   AGENT_PROPOSED в BLOCKED по identity; тест test_obj_generation: 0.99 остаётся AGENT_PROPOSED).
   - Число модели не калибровано (R-143): первый прогон дал 150 ответов из 150 на 0.85-0.95, правка
     шкалы в запросе не помогла. Уверенность теперь - согласие двух независимых ответов
     (temperature 0.2 и 0.8, разные seed): совпали имя (общее слово), категория и решение
     рельеф/предмет - берётся меньшая из двух; совпали имя (главное слово) и решение, а категория нет
     («crashed plane fuselage» дважды: vehicle / debris) - не выше 0.6, спор о категории в ambiguity;
     разошлись - не выше 0.4, оба ответа в ambiguity, у «предмет или рельеф?» - UNKNOWN. Плюс
     потолки кодом: без опоры на картинку <= 0.6, без альтернатив <= 0.7, 0.3 и ниже - UNKNOWN с
     догадкой в ambiguity. Оба ответа хранятся целиком (first, second). Версия запроса ask_rev
     (текст и правило сведения) - ответы прежней версии переспрашиваются, в том числе те, что уже
     стали AGENT_PROPOSED от модели.
   - Проба 30 ассетов (13 «предмет или рельеф?» + 17 предметов): согласие 19, расхождение 11;
     из 13 рельефов UNKNOWN 8, предложение 5. Полный прогон 1987 ассетов - gpuq #274 (~5.5 ч).
   - Одинаковое описание у разных семейств допустимо; семейства по описанию не сливаются.
   - Сводка по п.6 - identity_propose.py --stats -> art/objects/discovery/proposals_stats.txt.
   Тест tools/test_identity_propose.py.
2. **Страница проверки** показывает ответ модели (имя, категория, материал, уверенность, основания,
   сомнение); вкладки «предложено», «без описания», «предмет или рельеф?» отсортированы по уверенности -
   только порядок просмотра. Кнопка члена «не то» переименована в «другой предмет» (SPLIT FAMILY).
3. **Ревизии.** asset_rev: family_rev, identity_rev, canonical_source_rev, member_source_rev,
   generator_rev, prompt_rev, derive_rev; генератор и шаблон запроса - tools/hdart/obj_gen_spec.py
   (qwen21_turbo_rgba, approved = False). Тест: смена каждой части делает STALE ровно по ней;
   «refrigerator» -> «vending machine» без смены семейства - STALE по identity_rev.
4. **План сухого прогона десятки** - tools/hdart/acceptance_plan.py ->
   art/objects/generation/acceptance_plan.md (.json): по каждому ассету опознание, канонический кадр,
   ревизии, связи, что рисует модель, что выводится, какие кадры игры получатся, генератор, что держит.
5. **Старые писатели** map_update, map_pick, merge_gens, optimize_hd помечены LEGACY_DIRECT_WRITER
   (build_hd_pack.LEGACY_DIRECT_WRITERS и докстроки); их запись status показывает как unadopted
   modification с кодом 1. adopt - только человек в терминале: без TTY отказ, с TTY - список путей
   и ввод «принимаю». Тест tools/test_build_hd_pack.py.
6. **tools/test_gpu_scripts.py по смыслу**: разбор AST, граф вызовов с псевдонимами модулей,
   загрузка модели (from_pretrained, torch.load, torch.cuda, snapshot_download, запрос к Ollama с
   промптом...) доходит по графу до уровня модуля. Классы: GPU_MODEL_SCRIPT (обязан быть в
   gpu_scripts.txt), CPU_SCRIPT, UTILITY (библиотеки и тесты), LEGACY (attic). Исключений по имени
   файла нет. Сейчас GPU 39, CPU 131, UTILITY 36, LEGACY 13; контрольный список без трёх GPU-скриптов
   падает. vx_control.py (библиотека) из списка убран.

Условия первой GPU-десятки на 29.09:

| условие | состояние |
|---|---|
| опознание всех 10 CONFIRMED | **нет** - 0 из 10, ждёт Vitali (вкладка «десятка») |
| спорные связи решены | **нет** - FRNITURE 9: 3 кандидата (ABUNKER 11, GOVT 85, CITYFRNITURE 8); VILFRNITURE 2: 1 (FRNITURE 3) |
| сухой план проверен | план есть (acceptance_plan.md), ждёт просмотра |
| ревизии / stale | да, тесты проходят |
| сборщик пака чист | да для игры: IDENTICAL 50383; в репозиторной копии мода 1762 файла unadopted - только доклад |
| manifest verify = PASS | **нет** - MATCH 48142, STALE_REVISION 2241 (семейства получили новые ревизии после P1-A); ошибок целостности нет |

Вопрос к Vitali: STALE_REVISION должна ли валить verify, или это отдельная очередь работы, а PASS -
про целостность (MISSING / HASH_MISMATCH / UNKNOWN_FILE)? Сам порог не менялся.

#### P1-B, замечания специалиста (2026-09-29, поздно)

Ответ на вопрос выше - нет, не должна (DECISIONS 2026-09-29, «REVIEW_REQUIRED без имени; verify - только
целостность»).

1. **manifest: три команды** (tools/hdart/hd_manifest.py):
   - `verify` - только целостность: INTEGRITY PASS/FAIL. FAIL (код 1) - MISSING, HASH_MISMATCH,
     UNKNOWN_FILE, BAD_PATH (путь выхода не внутри мода), NO_BLOB (в хранилище нет блоба),
     MISSING_SOURCE (источник не найден; путь журнала карт - от корня мода), BROKEN_DEPENDENCY
     (derived_from в пустоту). Свежесть - одной строкой WARN. `--release` - ещё и stale 0, orphaned 0;
   - `freshness` - STALE_REVISION (входы изменились) и ORPHANED (семейства больше нет: 361 кадр ушёл
     из семейств после разбора строения, 1 переразбит), список и семейства, всегда код 0;
   - `status` - Integrity PASS, Current 47780, Stale 2241, Orphaned 362, Missing 0, Modified 0,
     Unknown 0; выпуск игрокам - нельзя, пока stale и orphaned не 0.
   Десятка: acceptance_plan.deps_stale пересчитывает входы asset_rev каждой строки плана (семейство,
   опознание, оригиналы, генератор, промпт, вывод) и сравнивает с записанными - «зависимости десятки:
   CURRENT»; контрольный опыт: смена content_hash, опознания или derive_rev даёт STALE ровно по ним.
   Тест tools/test_hd_manifest.py (+ целостность против свежести, NO_BLOB, MISSING_SOURCE, ORPHANED).
2. **Сведение двух ответов** - identity_propose.reconcile, RECONCILE_RULE 3, модель не нужна
   (`--reconcile` пересчитывает все пары; ask_rev от правила не зависит, прогон #274 не переспрашивается):
   | вердикт | статус | уверенность |
   |---|---|---|
   | тот же предмет теми же словами, та же категория | PROPOSED | меньшая из двух |
   | тот же предмет, категория разная | PROPOSED | ≤ 0.6 |
   | тот же смысл только через SYNONYMS (pillar/column, crate/box, sofa/couch, lamp/light, wreckage/debris...) | PROPOSED_AMBIGUOUS | ≤ 0.5 |
   | разные предметы или разное «предмет/рельеф» | UNKNOWN + REVIEW_REQUIRED, догадки в candidates | 0 |
   | хотя бы один UNKNOWN | UNKNOWN | 0 |
   Главное слово - последнее значимое до «with», общие слова (unit, structure...) пропускаются, мн. число
   к единственному; общее прилагательное не делает согласия. obj_generation: REVIEW_REQUIRED - свой
   статус строки без текста, подсказка карты не подставляется (описание прежней партии - старше);
   столбцы model_status, candidates. Страница: вкладка «модель не решила», догадки за «открыть»,
   «Верно» без текста неактивна, у PROPOSED_AMBIGUOUS пометка «близко, разными словами».
   Сводка `--stats`: четыре числа (согласие точное и через синонимы, спор только о категории,
   настоящее расхождение, UNKNOWN) и матрица «на что опирался ответ -> вердикт» плюс срез по тому,
   что было дано (стоит ли на картах, опознаны ли соседи).
3. Прогон #274 не перезапускался. Предварительно по первым 470 ответам: согласие 192 (точно 168,
   синонимы 24), только категория 44, разные предметы 226, UNKNOWN 8. Итог - после конца прогона.

#### P1-B, второй круг замечаний (2026-09-30)

1. **ORPHANED вместо FAMILY_GONE**, отдельно от STALE (см. п.1 выше). Десятка: acceptance_plan.deps_stale
   отдаёт по каждой строке CURRENT / STALE (что изменилось) / ORPHANED (семейства, по которому записан
   вход, больше нет).
2. **Заморозка десятки** - `acceptance_plan.py --freeze`: только если у всех десяти нет блокеров, журналы
   решений не новее плана и генератор утверждён. Неизменяемый (только для чтения) снимок
   `art/objects/generation/batches/<acceptance_batch_id>.json`: asset_ids; по ассету - семейство (id,
   revision, content_hash), опознание (статус, текст, identity_rev), канонический кадр и куски, промпт,
   кадры игры, строки GENERATE / GENERATE_WITH / DERIVE с входами и input_hash; генератор (generator_rev,
   prompt_rev), derive_rev. id = `acc-` + хэш содержимого: тот же состав и входы - тот же id.
   GPU-задание получает **acceptance_batch_id**, а не список ассетов, и перед стартом зовёт
   `acceptance_plan.py --check <id>`: BATCH_CURRENT (код 0) или BATCH_STALE (код 2, по каждой строке STALE /
   ORPHANED и что именно). Тест tools/test_acceptance_freeze.py (синтетика: тот же id, только чтение,
   STALE по семейству, опознанию, оригиналу члена, derive_rev, генератору, промпту; ORPHANED).
3. **Приставка в имени** (RECONCILE_RULE 4): split_name делит имя по with / containing / holding / carrying /
   mounted / attached / filled / loaded / full of (не после дефиса). Согласие = главное слово то же И
   приставки совместимы: обе пусты, есть общее слово, или приставка одного названа в словах другого (bush
   with berries / berry bush). Обе есть и разные (table with computer / table with lamp, rack with bottles /
   rack containing weapons) - REVIEW_REQUIRED; приставка у одного, другой молчит (table with computer / table) -
   PROPOSED_AMBIGUOUS.
4. **Когорты по тому, что было в запросе** (cohort_table в `--stats`): MCD говорящий (горит, взрывается,
   светит, второе состояние, анимирован) / обычный / нет MCD; контекст карты есть / нет; семейство или другие
   бока есть / нет; соседи с названием есть / нет. На каждую - согласие, спор о категории, смысловое
   расхождение, UNKNOWN в процентах. Плюс частые пары главных слов у расхождений и у «близко» с долей,
   которую покрывают 20 и 30 частых пар.
5. **Словарь синонимов не расширяется** до конца #274. Предварительно, 587 ответов по правилу 4: согласие
   237 (точно 203, близко 34), категория 46, расхождение 289, UNKNOWN 13. Расхождения - 239 разных пар,
   20 частых покрывают 20 процентов: длинный хвост и родо-видовые пары (bush / plant, formation / rock,
   container / crate, corner / wall) - словарём это не закрыть. Когорты: MCD говорящий 43 процента
   согласия против 37 у обычного (расхождение 46 против 55); семейство (40 против 41) и соседи (42 против 40)
   не помогают. Все 585 сведённых стоят на картах - когорты «без карты» в выборке нет. Решение - по полным
   1987.
6. **Уровни разбора** (RECONCILE_RULE 5, поле review_level; в `--stats` - счёт по уровням):
   AUTO_REVIEW_EASY - совпали или один смысл через словарь; HUMAN_REVIEW_LIGHT - один предмет, спор о
   категории или приставка у одного; HUMAN_REVIEW_HARD - разные предметы; UNKNOWN - полезной догадки нет.
   Меряет трудозатраты человека, а не уверенность модели. Карточка HARD: догадки A и B рядом, равноправно,
   по алфавиту (candidate_names), кнопки A / B / Другое / Не знаю. Выбор догадки - решение человека
   (EDIT с пометкой в журнале «выбрана догадка модели A из: ...»), «Другое» - к своему тексту.
   На 722 ответах (копия, пересведённая по правилу 5): EASY 274, LIGHT 64, HARD 368, UNKNOWN 14.
7. **Развилка P1-C** (решается по полным 1987, #274 не перезапускается): HARD + UNKNOWN меньше ~35 процентов -
   остаток дочищает человек; около 50 - второй проход только по HARD, **семантический арбитр**: получает
   канонический кадр, MCD, вырез карты, членов семейства и догадки A и B, отвечает только A / B / NEITHER /
   CANNOT_TELL (без свободного имени), и связь A с B: SAME / BROADER_NARROWER / RELATED_BUT_DIFFERENT /
   DIFFERENT - отдельным проходом, не словарём. Пока не сделан. Для отчёта - грубый тип HARD по строкам
   (conflict_table в `--stats`: разное предмет/рельеф, приставка, общие слова или нет, категория та же или нет).
   На 850 ответах: EASY 38 процентов, LIGHT 9, HARD 52, UNKNOWN 2 (HARD + UNKNOWN 53). HARD 438: общие слова
   при той же категории 30 процентов (Freighter Wall Corner / wall corner post, freighter wall segment / panel -
   род/вид или вариант), общие слова при другой 15 (UFO Pod / UFO), без общих слов при той же 25
   (counter / wooden table), при другой 30 (Doomed Crypt Pillar / Crate).
   Приёмка арбитра (если P1-C): до массового прохода - контрольная выборка 100 HARD, поровну по четырём типам,
   ответы сверяет Vitali. Главная мера - **ложно-уверенный выбор** (арбитр выбрал A или B, а верно другое или
   ни то ни другое), а не общая точность: при низком ложно-уверенном много CANNOT_TELL допустимо. Цель -
   безопасно перевести часть HARD в LIGHT, а не угадать всё.
8. **Итог #274** (2026-09-30, 1987 ассетов: 1982 ответа, 5 ошибок - ответ модели обрезан на 500 токенах, JSON
   не разобрался; `--reconcile` по правилу 5, модель не звалась): EASY 673 (34 процента), LIGHT 144 (7),
   HARD 1133 (57), UNKNOWN 32 (2); HARD + UNKNOWN 59 процентов - выше порога 35, по правилу развилки - P1-C
   (арбитр только по HARD, сначала контрольные 100). Четыре числа: согласие 686 (точно 596, близко 90),
   категория 131, расхождение 1133, UNKNOWN 32. HARD по типам: общие слова при той же категории 334 (29),
   при другой 134 (12), без общих слов при той же 301 (27), при другой 364 (32). Когорты: MCD говорящий 37
   процентов согласия против 32 у обычного (расхождение 53 против 62); соседи с названием 39 против 34;
   семейство 35 против 35 - не помогает; все 1982 стоят на картах. Расхождения - 887 разных пар на 1133,
   20 частых покрывают 11 процентов (corner / wall 19, pillar / wall 13, formation / rock 12) - словарь не
   путь; «близко» - 20 пар покрывают 100. Таблица опознания: AGENT_PROPOSED 1835, REVIEW_REQUIRED 1133,
   NO_PROPOSAL 35, SKIP 9. Десятка: 0 из 10 готовы (опознание не подтверждено), зависимости CURRENT;
   manifest: Integrity PASS, Current 47780, Stale 2241, Orphaned 362.
9. **Порядок после #274** (решение специалиста 30.09): предлагатель больше не улучшается (887 разных пар на
   1133 расхождения - неопределённость самой графики, а не словаря; 5 обрезанных JSON - потом повтором с
   большим лимитом ответа). Сначала доказать конец цепочки на одной десятке:
   (1) Vitali на вкладке «десятка» подтверждает опознание 10 и решает 4 спорные связи; (2) пересборка
   acceptance_plan, построчный разбор dry-run со специалистом; (3) `--freeze` -> acc-<хэш>; (4) команда
   специалиста на GPU - только эта десятка; (5) проверка в игре: геометрия, одинаковость семейства, другой
   бок, перекраска, составной, плитка, альфа, свет. (6) Прошла - P1-C на контрольных 100 HARD: по 25 на тип,
   внутри четверти разные PCK / террейны / категории (не двадцать стен подряд). Пороги FALSE_CONFIDENT
   (выбрал A или B, а верно другое или NEITHER): до 5 процентов хорошо, 5-10 дорабатывать, больше 10 массово не
   применять; CANNOT_TELL 30-40 процентов допустимо. (7) Массовый проход - только после оценки. Арбитр
   опознание не подтверждает: HARD -> A/B + SAME или BROADER_NARROWER -> LIGHT -> подтверждение Vitali.

#### P1-B, три разрыва до --freeze (2026-09-30)

Vitali подтвердил опознание десятки и спорные связи; dry-run построчно показал три места, где запустилось бы
не то, что проверяли. Закрыты (DECISIONS 2026-09-30, «qwen21_turbo_rgba утверждён для приёмочной десятки»).
Видеокарта не запускалась, --freeze не делался.

1. **Другой бок - два задания.** FRNITURE 19 (вид A) и MILBARR 19 (вид B) - одна multiview_group
   mv-FRNITURE_19. B получает ответ A второй картинкой (`reference.raw` = raw/j04_FRNITURE_19.png),
   same_asset / material / dimensions / construction = true, промпт «Same physical object, same materials,
   proportions, details and construction as <image2>, shown from the alternate isometric side». obj_photo:
   задание со ссылкой без готового raw и без задания-источника раньше в списке - отказ.
2. **Снимок -> задания -> obj_photo.** Снимок несёт задания и jobs_hash; `acceptance_run.py`
   check / compile / run [--dry-run] / derive / qa. Компиляция живых файлов не читает (тест подменяет
   load_state исключением). obj_photo `--batch <id>` сверяет снимок и задания до загрузки модели.
   Запись каждого запуска - runs/<id>/execution.json. Раннер в gpu_scripts.txt: проверка классов теперь видит
   запускатель, переданный параметром (`spawn=subprocess.call`); без записи в списке она падает.
3. **Плитка.** Фрагмент TILEABLE (текст специалиста) - только у категории tileable (NUKE2 10). `tile_qa.py`:
   лист 3x3 по изо-сетке (оригинал x4 | HD) и карта, где копии стоят вплотную (перебор карт по частоте, срез
   по этажу пары). На прежнем паке NUKE2 10: NUKE_CITY_NORAD_5 / NUKECITY03, этаж 1, 28 мест, 4 пары вплотную.
   TILE_FAIL допустим.

Промпт v2: prompt_rev d93485b9640a (первый вариант f32d3546e5cf дал «this same physical a pale household
refrigerator» - опознание с артиклем в середине фразы; второй бок переписан через «object»). Генератор
qwen21_turbo_rgba, generator_rev 8b9025eb1447, APPROVED_FOR_ACCEPTANCE.

Dry-run (пересчитан отдельно из acceptance_plan.json): ассетов 10, заданий модели 11, файлов ответа 12
(составной даёт два куска), прямых кадров игры 27, заданий вывода 13, выведенных файлов 33, выведенных кадров
игры 33; прямые и выведенные кадры не пересекаются, зёрна 2714-2724 все разные.

| ассет | generation_strategy | qa_strategy |
|---|---|---|
| FRNITURE 0 | recolor_canonical | geometry, alpha, ingame_lighting, adjacency_qa, recolor_derived |
| FRNITURE 9 | mirror_canonical | ... adjacency_qa, recolor_derived, mirror_derived |
| VILFRNITURE 2 | mirror_canonical | ... mirror_derived |
| FRNITURE 19 | linked_alt_views_2_jobs | ... identity_between_views, adjacency_qa, recolor_derived |
| NUKE3 30 | composite_2_parts | ... assembled_geometry, mirror_derived, composite_seam_qa |
| NUKE2 10 | tileable_single | ... tile_qa_3x3, tile_qa_map, recolor_derived |
| URBANLUX 76, FRNITURE 10, INDUSLUM 55 | single | geometry, alpha, ingame_lighting |
| INDUSLUM 45 | single | ... adjacency_qa |

Сухой прогон раннера на настоящей десятке (снимок во временной папке): BATCH_CURRENT, 11 заданий, команда
с `--batch`, снимок с чужим скриптом - отказ. Тесты: test_acceptance_freeze, test_acceptance_run (новый),
test_gpu_scripts, test_gpu_guard и остальные тесты P1 - проходят.

Второй круг (DECISIONS 2026-09-30, «структурная фраза, ADJACENCY_QA и COMPOSITE_SEAM_QA»): таблица выше уже
с новыми именами проверок. Промпт: «same number of steps, shelves, drawers and doors» заменена структурной
фразой, prompt_rev **e8a18c9f496a** (старой фразы 0 из 11 промптов, новой 11 из 11, фрагмент плитки только
у j07). ADJACENCY_QA (tile_qa.adjacency) - FRNITURE 0/9/19, INDUSLUM 45; TILE QA - только NUKE2 10.
COMPOSITE_SEAM_QA (tile_qa.composite_seam) - вывод BEDS 4+5 из NUKE3 30+29, места STYXTOWER/STYX_DARKTOWER
(496,392,7) и (512,400,7); провал только вывода - DERIVE_MIRROR_COMPOSITE_FAIL. Происхождение ответа:
photo/outputs.json (job_hash, raw_sha256, reference_job, reference_output_sha256), j05 отказывается при
чужом хэше ответа j04.

Проверка на прежнем паке (только чтение установки): FRNITURE 0 - D_HILHOTEL, 24 места, 26 пар вплотную,
cover 0.996, вниманий нет; BEDS из прежних NUKE3 - щель 0.002, двойное 0.005, mirror IoU 1.0, вниманий нет.
Контроль: половина BEDS 5 сдвинута на 12 пикселей - DERIVE_MIRROR_COMPOSITE_FAIL, 4 внимания; FRNITURE 0
увеличен на 20 процентов - 5 вниманий. Числа состава не изменились: 10 / 11 / 12 / 27 / 13 / 33.

Прогон `acc-5e9f63c421c0` (2026-09-30): попытка 1 (gpuq #276) снята на загрузке модели, ответов 0 (R-145:
модель без revision, апстрим сдвинул main; веса всех ревизий равны по sha256). Попытка 2 (gpuq #278) - код 0,
11 из 11 заданий, 33 выведенных файла, QA по стратегиям. Отчёт `tools/hdart/acceptance_report.py` ->
art/objects/generation/runs/acc-5e9f63c421c0/report/report.md (авто-строки и PENDING_HUMAN), наблюдения по
листам - notes.md там же. В пак ничего не шло; P1-C и массовая партия не запускались.

Итог приёмки (DECISIONS 2026-09-30, «итог приёмки acc-5e9f63c421c0»): ядро v2 принято; 5 PASS / 1 частичный / 4
FAIL; провалы разложены по слоям IDENTITY, GENERATOR_GEOMETRY, ALT_VIEW, DERIVE_RECOLOR, STRUCTURAL_TILEABLE,
ALPHA с опорным ассетом регрессии каждый - runs/acc-5e9f63c421c0/acceptance_result.json и .md. Генератор
qwen21_turbo_rgba - только простые одиночные предметы. URBANLUX 76 и FRNITURE 19 возвращены на опознание (REOPEN),
NUKE2 10 - structural_modular (class_decisions.tsv). Дальше - закрепление ревизий модели (R-145), затем P1-C.

R-145 (DECISIONS 2026-09-30, «замок модели»): модель, LoRA и библиотеки генератора закреплены замком
art/models/qwen21_turbo_rgba.lock.json (tools/hdart/model_lock.py), generator_rev считается по замку, коду
генератора и параметрам - 438d6841d129; границы применимости - generator_policy_rev qwen21-policy-2026-09-30.1.
Утверждение 8b9025eb1447 переходит на новую ревизию только после smoke smk-c3bfb42cef83 (tools/hdart/repro_smoke.py:
три задания приёмки теми же зёрнами, побайтно). Порядок дальше: smoke -> VERIFIED -> P1-C -> контрольные 100 HARD.

P1-C (DECISIONS 2026-09-30, «арбитр на контрольных 100 HARD»): tools/hdart/arbiter.py. freeze - снимок
arbiter-control-100-c7077054e919 (25 на тип, sha256 всех входов, только для чтения); run - только через gpuq, сверяет
входы со снимком перед каждым вопросом; report - распределение по четырём типам и FALSE_CONFIDENT по truth.tsv;
label - разметка правды вслепую. Первый прогон acf097a4c063: 0 CANNOT_TELL, 0 NEITHER, в LIGHT 71 - ждёт разметки
Vitali, asset_identity не тронута. Отчёт - runs/acf097a4c063/report.md рядом со снимком.
