# Прогон tools/test_*.py (05.10.2026, py -3.13, PYTHONIOENCODING=utf-8, таймаут 180 с, последовательно)

Всего файлов 92: PASS 87, FAIL 2, TIMEOUT 0, SKIPPED 3, ОТКЛОНЁН ХУКОМ 0 для самих тестов (тесты хуков запускались и прошли).
Красные: test_battle_view.py, test_gpu_scripts.py. Висящих нет (самый долгий test_gpuq.py, 161 с, при лимите 180 - запас небольшой).
Игра, сборка, видеокарта, выпуск не запускались; tools/editq.py вызывал только test_editq.py (временный репозиторий в TMP, EDITQ_REPO/EDITQ_HOME подменены).
Сырые логи: tests_logs/<тест>.log. 

## Таблица
| Тест | Итог | Время, с | Первая строка ошибки |
|---|---|---|---|
| test_acceptance_freeze.py | PASS | 0.1 |  |
| test_acceptance_run.py | PASS | 0.2 |  |
| test_ai_arena_commit.py | PASS | 1.0 |  |
| test_ai_arena_contract.py | PASS | 0.3 |  |
| test_aligned_recolor_v1.py | PASS | 0.2 |  |
| test_aligned_recolor_v2.py | PASS | 0.2 |  |
| test_ar_boundary_validation.py | PASS | 0.2 |  |
| test_arbiter.py | PASS | 0.2 |  |
| test_arbiter_v2.py | PASS | 0.2 |  |
| test_assembly_discovery_v1.py | PASS | 0.2 |  |
| test_assembly_group_v1.py | PASS | 0.2 |  |
| test_assembly_repeated_v1.py | PASS | 0.1 |  |
| test_asset_fidelity.py | PASS | 0.2 |  |
| test_backslash_guard.py | PASS | 17.5 |  |
| test_base_pack.py | PASS | 0.3 |  |
| test_battle_view.py | FAIL | 0.4 | см. разбор |
| test_blocked_pair.py | PASS | 0.1 |  |
| test_build_hd_pack.py | PASS | 0.2 |  |
| test_derive_recolor_acceptance_v2.py | PASS | 10.1 |  |
| test_detail_class.py | PASS | 0.3 |  |
| test_editq.py | PASS | 4.8 |  |
| test_families_recolor_diff.py | PASS | 0.2 |  |
| test_family_relation_v2.py | PASS | 0.2 |  |
| test_game_guard.py | PASS | 6.0 |  |
| test_gentle_scope.py | PASS | 0.2 |  |
| test_gpu_guard.py | PASS | 8.7 |  |
| test_gpu_scripts.py | FAIL | 11.4 | см. разбор |
| test_gpuq.py | PASS | 161.4 |  |
| test_hd_e2e_v1.py | PASS | 0.3 |  |
| test_hd_e2e_v1_r2.py | PASS | 0.3 |  |
| test_hd_e2e_v1_r3.py | PASS | 0.2 |  |
| test_hd_e2e_v1_r31.py | PASS | 0.2 |  |
| test_hd_manifest.py | PASS | 0.1 |  |
| test_identity_card.py | PASS | 0.3 |  |
| test_identity_holdout.py | PASS | 0.4 |  |
| test_identity_propose.py | PASS | 0.1 |  |
| test_identity_routing.py | PASS | 0.2 |  |
| test_item_asset_check.py | PASS | 0.4 |  |
| test_map_paint_tiled.py | PASS | 9.9 |  |
| test_map_scenes.py | PASS | 0.2 |  |
| test_map_update.py | PASS | 76.9 |  |
| test_mcd_state.py | PASS | 0.1 |  |
| test_model_lock.py | PASS | 0.8 |  |
| test_obj_families.py | PASS | 0.2 |  |
| test_obj_generation.py | PASS | 0.2 |  |
| test_obj_struct.py | PASS | 0.2 |  |
| test_option_defaults.py | PASS | 0.1 |  |
| test_pack_guard.py | PASS | 5.6 |  |
| test_photo_accept.py | PASS | 0.6 |  |
| test_photo_base.py | PASS | 0.4 |  |
| test_photo_decomp.py | PASS | 0.3 |  |
| test_pilot_batch.py | PASS | 0.7 |  |
| test_post_review_safety.py | PASS | 0.2 |  |
| test_read_pck.py | PASS | 0.1 |  |
| test_relation_discovery_v2.py | PASS | 0.2 |  |
| test_relation_discovery_v3.py | PASS | 0.3 |  |
| test_relation_discovery_v4.py | PASS | 0.3 |  |
| test_relation_discovery_v5.py | PASS | 0.2 |  |
| test_relation_holdout_v4.py | PASS | 0.2 |  |
| test_relation_holdout_v4_ref.py | PASS | 0.2 |  |
| test_relation_holdout_v5.py | PASS | 0.3 |  |
| test_relation_holdout_v7.py | PASS | 0.2 |  |
| test_relation_probe.py | PASS | 0.2 |  |
| test_relation_safety_v7_prep.py | PASS | 0.2 |  |
| test_relation_taxonomy.py | PASS | 0.3 |  |
| test_render_chunks.py | PASS | 13.4 |  |
| test_routing_holdout.py | PASS | 0.1 |  |
| test_routing_holdout_diag.py | PASS | 0.1 |  |
| test_routing_holdout_diag2.py | PASS | 0.1 |  |
| test_routing_holdout_v5.py | PASS | 0.2 |  |
| test_routing_holdout_v7.py | PASS | 0.2 |  |
| test_routing_holdout_v8.py | PASS | 0.2 |  |
| test_routing_model_v8.py | PASS | 0.1 |  |
| test_routing_rules.py | PASS | 0.2 |  |
| test_routing_rules_v5.py | PASS | 0.2 |  |
| test_routing_rules_v6.py | PASS | 0.1 |  |
| test_routing_rules_v7.py | PASS | 0.1 |  |
| test_rul_map.py | PASS | 4.5 |  |
| test_struct_guide.py | PASS | 0.4 |  |
| test_struct_report.py | PASS | 0.2 |  |
| test_two_component_v1.py | PASS | 0.2 |  |
| test_unit_census.py | PASS | 0.3 |  |
| test_v5_ar2_recount.py | PASS | 0.2 |  |
| test_v5_component_validation.py | PASS | 0.2 |  |
| test_v5_freeze_readiness.py | PASS | 0.2 |  |
| test_voice_deps.py | PASS | 0.2 |  |
| test_weapon_fit.py | PASS | 0.2 |  |
| test_weapon_part_fit.py | PASS | 0.3 |  |
| test_weapon_parts.py | PASS | 3.1 |  |
| test_gentle_determinism.py | SKIPPED | - | запускает игру |
| test_map_paint_input.py | SKIPPED | - | запускает скрипт видеокарты map_paint.py |
| test_voice_duplex.py | SKIPPED | - | компилирует C через gcc MSYS2 |

## Падения с разбором

### test_battle_view.py - FAIL (31 нарушение), находка по охвату, не поломка кода
Строки вида `FAIL audit: gen_hd.py - MISSING (ракурс своими словами)` и `FAIL audit: obj_series.py - no-words (ракурса в тексте нет)`.
Тест проверяет, что каждый генератор из tools/gpu_scripts.txt берёт блок ракурса из battle_view.py (правило CLAUDE.md «Ракурс боя - один на все генераторы», `battle_view.py audit`). Проверка охвата была и в HEAD, но в рабочем дереве оба файла, tools/hdart/battle_view.py (+248 строк) и tools/test_battle_view.py (+32), правятся другой сессией и не закоммичены; добавлены статусы NOT_BATTLE / NO_PROMPT / PROTECTED. Остальные проверки теста (фразы, направления, света) прошли - красный только раздел охвата.
MISSING: gen_hd, gen_cursor, gen_fire, map_paint, make_ref, probe_object, probe_floor, floor_group, obj_photo, ground_relief, gen_fire_real, unit_pilot, unit_refit, unit_direct, restore_probe_v1, prod_two_pass_v1, weapons_synth. no-words: obj_series, long_object, acceptance_run, repro_smoke, photo_render, struct_probe, photo_struct_render, hd_e2e_v1_run, restore_probe_v1b, restore_probe_v1c, restore_batch_v1, strict_ctl_v1, prod_two_pass_v2, weapons_redraw.
Класс: долг охвата / незавершённая работа соседней сессии, не устаревший тест. Часть имён (ground_relief, floor_group, acceptance_run, repro_smoke и др.) похожа на то, что их надо перевести в NOT_BATTLE / NO_PROMPT / PROTECTED, а не править промпты - решать автору. prod_two_pass_v2.py идёт на видеокарте прямо сейчас и числится в нарушителях.

### test_gpu_scripts.py - FAIL (5 ошибок)
```
ОШИБКА в списке, но это CPU_SCRIPT: strict_ctl_v1.py, unit_parts.py, weapons_synth.py, weapons_redraw.py, agent_full.py (модель не грузит)
классы: GPU_MODEL_SCRIPT 66, CPU_SCRIPT 278, UTILITY 125, LEGACY 13; в списке 79
```
Первая строка лога - `SyntaxWarning: invalid escape sequence` (<unknown>:6): предупреждение компиляции какого-то просканированного файла, не самого теста.
tools/gpu_scripts.txt и tools/test_gpu_scripts.py тоже изменены в рабочем дереве (+36 и +294 строк), тест переписан на граф вызовов. Расхождение: пять скриптов стоят в списке, а анализатор считает, что запуск файла до загрузки модели не доходит. Грепом: weapons_synth и weapons_redraw импортируют item_photo, obj_photo и render_chunks, unit_parts - item_photo и photo_ui, то есть грузят модель косвенно (дочерний процесс render_chunks или внутри main); strict_ctl_v1 и agent_full импортов с моделью не содержат. Класс: либо список избыточен для двух последних, либо анализатор не видит косвенную загрузку для первых трёх (недоделка WIP-теста). Окружение ни при чём. Риск: если список «почистят» по этому тесту, гард gpu-guard на weapons_synth, weapons_redraw, unit_parts может исчезнуть при том, что они реально грузят модель.

## Тесты, мусорящие в дереве
git status --porcelain: до прогона 262 строки (18:33), после 265 (18:45). Появилось ровно три:
- ` M docs/SETUP.md`, ` M docs/STATUS.md` (mtime 18:42:08-09)
- `?? Выпуск/weekly/` (создана 18:38, внутри 2026-10-05_dioxine: 8 png и summary.md, mtime до 18:43)
Ни один тест не ссылается на эти пути (grep SETUP.md, STATUS.md, weekly по tools/test_*.py: только test_map_update.py, он пишет MAP_STATUS.md во временную папку). Скорее всего это работа другой сессии (недельный дайджест: кадры боя, инвентаря). Причастность прогона не доказана и не опровергнута, но признаков нет. Ничего не удалялось. Сравнение: status_before.txt / status_after.txt в этой папке.
Остальные тесты, создающие данные (test_editq, test_gpuq, test_ai_arena_*, test_render_chunks, test_rul_map, test_map_update), пишут во временные каталоги, следов в дереве не оставили.

## Пропущенные
- test_gentle_determinism.py - запускает невидимую игру ботом (ai_probe) на сборке стенда; запрещено заданием.
- test_map_paint_input.py - запускает tools/hdart/map_paint.py (он в tools/gpu_scripts.txt); при поломке проверки «--pre отказывается до загрузки модели» тест загрузит модель на карту. Запрещено заданием.
- test_voice_duplex.py - собирает gcc из MSYS2 C-тест (сборка), запрещено заданием; нужен ещё gcc и miniaudio.h.

## Прочее
- test_gpuq.py: 161,4 с из 180 - близко к потолку при занятой машине (поднимает свой диспетчер в GPUQ_HOME во временной папке, карта фиктивная; реальную очередь и процессы prod_two_pass_v2 / weapon_judge не затронул - shutdown шёл с подменённым GPUQ_HOME). При более нагруженной машине возможен ложный TIMEOUT.
- Отклонения хуками: (1) backslash-guard отклонил мою команду sed с обратной косой (R-035, верно); (2) game-guard отклонил команду записи отчёта только из-за того, что в тексте heredoc стояло имя исполняемого файла игры (ложное срабатывание хука на тексте, не на запуске) - я переформулировал текст, хук не обходил.
- Первый запуск раннера упал на записи results.json в cp1252 (кириллица в примечании, R-001) после test_gentle_scope; продолжил вторым раннером с test_gpu_guard. Запусков в итоге 25+64=89, потерь нет.
