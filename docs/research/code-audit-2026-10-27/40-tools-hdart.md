# Аудит tools/hdart (27.10.2026)

Зона: `tools/hdart`, 456 файлов .py, 159 519 строк. Только чтение. Полный список с классами — `40-tools-hdart.tsv` рядом
(путь, строк, класс, mtime, последняя очередь, флаг lock-хэша, доказательство). Скрипты проверки — блокнот сессии
`scratchpad\audit_hdart\` (final.py, helpers.py, dup.py, chains.py, simblocks.py, emit.py).

Как считалась жизнь файла: сильные корни — хуки, `.claude/launch.json`, агенты, скиллы, C# портала (Review.cs, Pck.cs,
PckTests.cs, SetupPage.cs), не-attic ps1/cmd/sh, живые `tools/*.py` с import или exec, документы-инструкции
(docs/handbook, docs/ART_STATUS.md, tools/hdart/README.md); затем замыкание по импортам; затем история реальных
запусков по заголовкам 875 логов `.gpuq/logs`. Слабые доказательства: строка в gpu_scripts.txt (тест требует перечислять
все модельные скрипты), settings.local.json, упоминание в test_*, словарь в battle_view.py, docstring.
mtime надёжнее даты коммита (массовый коммит 15.10).

## Итог

| Класс | Файлов | Строк | Доля | Действие |
|---|---:|---:|---:|---|
| Живые входы | 50 | 22 341 | 14,0 % | оставить |
| Живые библиотеки | 24 | 7 411 | 4,6 % | оставить |
| Рабочие серии (очередь с 13.10 или правка с 20.10) | 38 | 11 011 | 6,9 % | оставить |
| Библиотеки рабочих серий | 12 | 7 535 | 4,7 % | оставить, потом свести |
| **Итого живое** | **124** | **48 298** | **30,3 %** | |
| Старое поколение, держащее живое (импорт) | 17 | 8 466 | 5,3 % | свести (находки 5, 6) |
| Уже в attic | 12 | 3 151 | 2,0 % | |
| **В attic сейчас** | **160** | **48 066** | **30,1 %** | находка 1 |
| Свежие разовые пробы | 63 | 11 492 | 7,2 % | позже, находка 3 |
| Под lock-хэшем V3 | 79 | 39 896 | 25,0 % | находка 2 |
| v3_baseline.py (страж lock) | 1 | 150 | 0,1 % | оставить |
| Всего | 456 | 159 519 | 100 % | |

Свести: ~1 100–1 300 строк в живом коде и ~3 400 строк в 16 цепочках `_vN` (по сходству строк difflib; цепочки почти
целиком в изолированной части и снимаются переносом).

Топ-5: (1) attic — 160 файлов / 48 066 строк; (2) решение по цепочке V3 — 39 896 строк; (3) починка gpu_scripts.txt;
(4) общий загрузчик Qwen и общая палитра (~240 строк); (5) автоуборка свежих проб.

## Находки

### 1. Изолированное старое поколение и завершённые серии: 160 файлов рядом с живым кодом
- Тип: мёртвый код
- Серьёзность: средняя
- Где: tools/hdart/ (классы в TSV: СТАРОЕ-ПОКОЛЕНИЕ-изолировано без lock, РАЗОВЫЙ-завершённая серия, старые РАЗОВЫЙ-тикет/проба)
- Доказательство: из 105 изолированных без lock ни один не достигается замыканием от 124 живых; последний запуск в очереди
  среди 34 запускавшихся — 07.10. Крупнейшие: weapon_parts 1369, weapon_fit 1300, prod_two_pass_v4 1232, floor_batch 1148,
  weapon_judge 1003, grip_matrix 853, arbiter 846, sidewalk_probe 818, crossing_build 768, crossing_check 701, map_truth 700,
  agent_pose 687. Завершённые серии: 41 файл, 8 553 строки. Старые пробы: 15 файлов, 2 606 строк.
- Что сделать: перенести в tools/hdart/attic/ по TSV, не по маске. У 65 изолированных есть tools/test_*.py (36 603 строки под
  тестами) — переносить с тестами; убрать записи из gpu_scripts.txt; v3_baseline.py оставить; recipe_guard.py импортируют
  floor_batch и floor_series — вместе.
- Выигрыш: 48 066 из 159 519 строк (30,1 %), 160 из 456 файлов.
- Риск: сборка (тесты, gpu_scripts.txt)

### 2. Замороженная цепочка V3 держится на хэшах по путям
- Тип: размер
- Серьёзность: низкая
- Где: art/objects/generation/v3_baseline.lock.json (120 файлов hdart), tools/hdart/v3_baseline.py,
  art/objects/generation/probes/relation-holdout-v4/v5/v7/reference.lock.json, art/models/qwen21_turbo_rgba.lock.json
- Доказательство: lock фиксирует sha256 120 файлов (57 430 строк); 79 из них (39 896 строк) — изолированное старое поколение:
  hd_e2e_v1*, relation_*, routing_*, derive_recolor_*, prod_two_pass_v1..v4, arbiter*, identity_*. Проверка путевая.
- Что сделать: решение Vitali — оставить или перенести пакетом в attic/v3_frozen/ с пересозданием lock одной командой.
- Выигрыш: 39 896 строк (25,0 %), 79 файлов.
- Риск: сборка (проверка lock, test_model_lock.py)

### 3. Свежие разовые пробы копятся без уборки
- Тип: размер
- Серьёзность: низкая
- Где: tools/hdart/t###_*.py, ticket_*.py, *_sheet.py, probes/
- Доказательство: 63 файла, 11 492 строки с правкой за 7 дней или запуском в очереди с 13.10; по образцу прошлых серий станут мёртвыми.
- Что сделать: автоуборка — пробы без правки и без очереди 14 дней и без живых импортёров уходят в attic.
- Выигрыш: до 11 492 строк за цикл
- Риск: нет

### 4. Цепочки версий _vN: 16 семейств, ~3 400 общих строк
- Тип: дублирование
- Серьёзность: низкая
- Где: relation_holdout* (5 файлов, 3 338 строк кода, общих 810), routing_holdout* (6; 3 303; 745), hd_e2e* (9; 3 959; 615),
  derive_recolor_acceptance* (5; 2 580; 275), relation_discovery* (4; 2 768; 181), routing_rules* (4; 2 131; 179),
  derive_recolor_base_acceptance* (144), tree_render + tree_render_v2 (107, живая пара), arbiter + arbiter_v2 (79),
  prod_two_pass* (74), gen_reticle + gen_reticle_v2 (14)
- Доказательство: chains.py — 3 387 совпавших строк из 28 084 в 16 семействах. Точные AST-дубли функций: 61 кластер, 677 строк.
- Что сделать: в изолированной и замороженной части не сводить — снимается переносом (находки 1, 2). Из живых — только
  tree_render/tree_render_v2 при правке. gen_reticle_v2 (367) никто не импортирует — в находку 1.
- Выигрыш: до 3 400 строк, почти всё через находки 1–2; чистое слияние в живом ~200.
- Риск: сборка (lock); для tree_render* — механика/кадр, сверять побайтно

### 5. Палитра: 12 встроенных вариантов getpalette() вместо одной функции
- Тип: дублирование
- Серьёзность: низкая
- Где: центральная версия xcom_sprites.py:38,50. Копии в живых: gen_base.py:89, gen_base_bubbles.py:47, gen_craft_lights.py:139,
  gen_fx.py:427, glass_alpha.py:107, photo_ui.py:128, tank_turret.py:88, upscale_ui.py:39, upscale_units.py:85,150,602,
  gen_ufo_pedia.py:415, item_b2_render.py:124, doll_b2_render.py:95; ещё unit_pilot.py:70, anim_flicker.py:355, gen_path.py:250,
  restore_pedia.py:26, pilot2_job_sheet.py:49, water_build.py:75.
- Доказательство: 15 функций палитры в 13 файлах, 178 строк, 15 разных тел; ~33 вызова getpalette(); четыре разных способа
  дополнения до 768.
- Что сделать: всё через xcom_sprites.load_palette с одним правилом дополнения; рядом palette_array(im).
- Выигрыш: ~90 из 118 строк в живом.
- Риск: механика/кадр (результат не должен меняться — hdtest_compare.py и Ctrl+F8)

### 6. Двухфазная загрузка Qwen-Image-Edit повторена в четырёх файлах
- Тип: дублирование
- Серьёзность: низкая
- Где: weapons_probe5.py:73, unit_turnaround.py:390, doll_face_pilot.py:109, doll_photo_pilot.py:209; оригинал photo_ui.py:713
- Доказательство: блоки 58–66 строк совпадают на 44–66 %. Прочие загрузчики: gen_promo.py:246, gen_screens.py:300,
  gen_ufo_pedia.py:203, gen_lora_test.py:107, gen_hd.py:467, wall_restore_c.py:64. Всего 31 функция загрузки модели в 23 файлах, 415 строк.
- Что сделать: одна load_qwen_edit(two_phase=...) и одна load_qwen21() в общем модуле; проверить одной пробой через gpuq.
- Выигрыш: ~150 + ~60 строк.
- Риск: механика/кадр (порядок выгрузки моделей влияет на VRAM и, возможно, на воспроизводимость сидов)

### 7. Подложка и альфа: десятки одноимённых функций
- Тип: дублирование
- Серьёзность: низкая
- Где: on_floor ×12, on_bg ×5, over ×8, matte ×3 (agent_full.py:173, handob_cand1642.py:115, weapon_fit.py:207)
- Доказательство: 89 функций в 71 файле, 1 168 строк, 85 разных тел (живых 31, 308 строк) — переписанные заново варианты.
- Что сделать: общий underlay.py на 2–3 функции; начать с живых 19 файлов (R-089).
- Выигрыш: ~100 из 308 строк в живом.
- Риск: механика/кадр (альфа и край)

### 8. Малые утилиты: шрифт, tsv/json, хэш, PNG
- Тип: дублирование
- Серьёзность: низкая
- Где: шрифт ×26 в 20 файлах, read_tsv ×31 в 16, load PNG ×38, load_json/save_json, sha256_file ×10, sheet ×49
- Доказательство: JSON/TSV 132 функции, 657 строк; хэш 31 / 175; шрифт 29 / 184; PNG 78 / 441 (живых 24, 227).
- Что сделать: hdutil.py на 5 функций (font, read_tsv/write_tsv с utf-8-sig, sha256_file, load_rgba/save_png). Листы не сводить.
- Выигрыш: ~450 из ~630 строк в живом.
- Риск: нет (save_png — сверить на PNG-паках)

### 9. tools/gpu_scripts.txt разошёлся с диском; четыре GPU-скрипта проходят мимо сторожа
- Тип: ошибка
- Серьёзность: **высокая**
- Где: tools/gpu_scripts.txt:111-114; .claude/hooks/gpu-guard.ps1:55-56; tools/test_gpu_scripts.py
- Доказательство: test_gpu_scripts.py — 27 ошибок. Сторож берёт последнюю часть пути из команды и проверяет `$scripts -contains $leaf`;
  строки 111–114 записаны путями `tools/hdart/doll_*.py` (заголовок файла требует имя без пути) и не совпадут никогда —
  doll_paint_pilot, doll_ctl_pilot, doll_face_pilot, doll_face_ctl запускаются мимо очереди. Не в списке: detail_retry_v2,
  prod_two_pass_v3, prod_two_pass_v3sf, t300a_gen, t300r_gen. Зря в списке (CPU): strict_ctl_v1, unit_parts, weapons_synth,
  weapons_redraw, agent_full, voice_emotion_pilot, game_voice_probe, craft_launch_video, t249_box_gen, t300_gen.
  Нет на диске: obj3d_gen, obj3d_paint, gen_video, qwen_chat.
  Сверено в основной сессии: строки 111–114 — незакоммиченная правка (`git diff --stat` +5 строк), то есть чужая работа в процессе.
- Что сделать: имена без пути, добавить пять пропущенных, убрать CPU и отсутствующие; прогнать test_gpu_scripts.py и test_gpu_guard.py.
  Заодно сторожу — сравнивать по имени файла и в записях с путём.
- Выигрыш: сторож снова закрывает все GPU-скрипты.
- Риск: нет

### 10. Блок ракурса боя: 27 файлов «своими словами», 15 живых/рабочих
- Тип: ошибка
- Серьёзность: средняя
- Где: battle_view.py audit: MISSING у gen_hd, gen_cursor, gen_fire, map_paint, hud_panel_pilot, make_ref, probe_object, obj_photo,
  gen_ufo_pedia, gen_base_paint, wreck_object, base_hangar_edit, base_pool_repair, base_turret_split, craft_launch_frames;
  остальные 12 — изолированные/разовые
- Доказательство: audit — MISSING 27, USES 25, NOT_BATTLE 14, NO_PROMPT 6, PROTECTED 2. Часть MISSING может быть ложной
  (gen_hd описывает много наборов, map_paint рисует карту); по каждому файлу вручную не проверено.
- Что сделать: подключить battle_view в 15 живых (правило CLAUDE.md); небоевые пометить NOT_BATTLE.
- Выигрыш: единый ракурс; размер не уменьшится.
- Риск: механика/кадр (меняются запросы — арт будет другим; по одному набору и с показом Vitali)

### 11. Кириллица в JSON/HTML без спецификации
- Тип: ошибка
- Серьёзность: низкая
- Где: pedia_text.py:239, gen_hd.py:1589 и :1899, review_floors.py:693
- Доказательство: записи без utf-8-sig с кириллицей или ensure_ascii=False (R-001).
- Что сделать: utf-8-sig в четырёх местах и читатели на utf-8-sig.
- Риск: нет

### 12. reshape(256,3) без дополнения палитры
- Тип: ошибка
- Серьёзность: низкая
- Где: живые gen_fx.py:427, item_b2_render.py:124, gen_ufo_pedia.py:415; нежилые tracer_preview.py:126, grip_matrix.py:77
- Доказательство: Pillow 12.3.0 — getpalette() у PNG на 16 цветов даёт 48 значений, у RGB/RGBA — None; reshape(256,3) падает.
  Для PNG из OXCE_HD_EXPORT (256 цветов) не срабатывает.
- Что сделать: решается находкой 5.
- Риск: нет

### 13. Не найдено
- ComfyUI в зоне нет: конвейер вызывает DiffSynth и diffusers напрямую.
- Гонок при параллельной записи и потери альфы в живых файлах не найдено; проверка неисчерпывающая.

Живые входы (строк): gen_hd 1907, gen_combat_fx 1366, gen_fx 1364, map_paint 1286, photo_ui 1050, gen_base_anim 870,
upscale_units 846, tank_turret 786, review_floors 707, build_dataset 620, build_pack 592, gen_icons 547, map_pick 502,
fetch_fonts 494, tile_forge 490, pedia_batch 488, gen_path 466, build_hd_pack 425, gen_promo 411, score_batch 379,
review_server 369, battle_view 358, gen_craft_lights 355, gen_cursor 355, map_mockup 351, optimize_hd 322, xcom_sprites 316,
probe_object 315, sprite_scale 313, subjects_terrain 310, gen_reticle 306, hints 293, gen_fire 273, pedia_ab 259, pedia_text 252,
gen_base_bubbles 210, upscale_ui 201, server 199, make_ref 192, merge_gens 191, pedia_review 162, gen_cursor_box 158,
extract_pck 157, ticket_family 145, check_lora 91, ground_dump 75, unpanel_batch 74, cut_gloves 60, placeholder_sheet 49, __init__ 34.
Остальные классы — в TSV.
