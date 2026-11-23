# Аудит tools/hdart — 2026-10-05 (только чтение)

Скрипты аудита: `scratchpad/audit/hdart_audit.py` (сбор), `make_report.py` (отчёт); данные — `hdart_audit.json`, полная таблица — `hdart_classes.tsv` (utf-8-sig).
Что считалось ссылкой: импорт в `tools/**/*.py` (по basename, с учётом `import X as y`, `from X import`, `importlib`); упоминание `X.py` в `docs/**/*.md`, `CLAUDE.md`, `AGENTS.md`, `.claude/**`; `tools/gpu_scripts.txt`; `X.py` в `art/**` (.sh/.cmd/.ps1/.json/.md, глубина 4, без `_backup`/`raw`, просмотрено 2670 файлов); история очереди видеокарты — заголовки `===== <время> запуск: [...]` в `.gpuq/logs/<id>.log` (367 логов; `queue.json` хранит только 30 последних, KEEP_DONE).
Занятость — по `protected_status.txt` (git status --porcelain): в `tools/hdart` **151 файл в гите, 148 не закоммичены (`??`), 14 изменены (`M`)** — то есть почти весь код v2 (relation/routing/derive/hd_e2e/weapons/unit_*) живёт только на диске.

## Сводка числами

| Класс | Модулей | Пояснение |
|---|---|---|
| ACTIVE (ядро) | 67 | в конвейере по HD_PIPELINE_V2 §31 / PHOTO_BASE / DECISIONS 03–05.10, либо ставился в очередь за 7 дней |
| ACTIVE-LIB | 93 | не ядро, но импортируется ACTIVE (из них **68 с «замороженными» именами** holdout/relation/routing/derive/probe: **61 тянет цепочка `prod_two_pass_v2 → prod_two_pass_v1 → restore_batch_v1 / hd_e2e_v1_run → hd_e2e_v1`**, остальные 7 — библиотеки проб у item_photo, obj_photo, pilot_batch, unit_parts, weapons_restore) |
| FROZEN | 30 | одноразовые приёмки/пробы/holdout с вердиктом в DECISIONS или остановленные |
| LEGACY | 51 | есть ссылки в доках/граблях или импорт, но не в текущем конвейере и не ставился 7 дней (класс сверх ТЗ: иначе это были бы ORPHAN с живыми ссылками) |
| SUPERSEDED | 2 | есть vN+1, никто кроме неё не импортирует |
| ORPHAN | 9 | ни ссылок, ни запусков |
| ATTIC | 12 | уже в attic/ |
| **Всего .py** | **264** | 249 в корне + 12 attic + 3 triage |

Прочих файлов в tools/hdart (ps1/sh/cmd/txt/json/md/yml/csv/html): 21. Сейчас в очереди: #408 `prod_two_pass_v2.py strict` (идёт), #409 `agent_pose.py render` (ждёт); `weapon_judge.py` по докстрингу видеокарту не трогает (Codex exec), в `gpu_scripts.txt` его нет.

## 1–2. Классификация (кратко; полная таблица — hdart_classes.tsv)

### ACTIVE (ядро)

| файл | класс | изменён | строк | занят | ссылки | почему |
|---|---|---|---|---|---|---|
| agent_full.py | ACTIVE | 2026-10-05 | 682 | ЗАНЯТ | imp:agent_pose; doc:1; gpuq:1/2026-10-05 | в текущем конвейере (HD_PIPELINE_V2 §31 / PHOTO_BASE / DECISIONS 10.03-10.04) |
| agent_pose.py | ACTIVE | 2026-10-05 | 569 | ЗАНЯТ | gpuq:1/2026-10-05 | ставился в очередь 2026-10-05 |
| asset_fidelity.py | ACTIVE | 2026-10-03 | 262 | ЗАНЯТ | imp:restore_batch_v1,restore_probe_v1,test_asset_fidelity; R:157,210; doc:3; art:4 | в текущем конвейере (HD_PIPELINE_V2 §31 / PHOTO_BASE / DECISIONS 10.03-10.04) |
| battle_view.py | ACTIVE | 2026-10-04 | 359 | ЗАНЯТ | imp:agent_full,agent_pose,test_battle_view…; doc:16 | в текущем конвейере (HD_PIPELINE_V2 §31 / PHOTO_BASE / DECISIONS 10.03-10.04) |
| build_hd_pack.py | ACTIVE | 2026-09-29 | 426 | ЗАНЯТ | imp:obj_push,test_build_hd_pack; R:141; doc:12 | в текущем конвейере (HD_PIPELINE_V2 §31 / PHOTO_BASE / DECISIONS 10.03-10.04) |
| cover_check.py | ACTIVE | 2026-09-27 | 101 |  | imp:tile_qa; R:089,116; doc:7 | в текущем конвейере (HD_PIPELINE_V2 §31 / PHOTO_BASE / DECISIONS 10.03-10.04) |
| craft_outline.py | ACTIVE | 2026-10-05 | 706 |  | R:209; doc:3 | очертания посудин для глобуса (R-209, 05.10, art/outline) |
| extract_pck.py | ACTIVE | 2026-09-24 | 158 |  | imp:ground_dump,review_floors,run_batch; R:052,075; doc:10; art:1 | в текущем конвейере (HD_PIPELINE_V2 §31 / PHOTO_BASE / DECISIONS 10.03-10.04) |
| fire_real_pack.py | ACTIVE | 2026-09-28 | 215 |  | doc:1 | в текущем конвейере (HD_PIPELINE_V2 §31 / PHOTO_BASE / DECISIONS 10.03-10.04) |
| floor_group.py | ACTIVE | 2026-09-28 | 365 |  | imp:ground_relief; R:112,117,118; doc:6; art:2; gpuq:4/2026-09-28 | лаборатория §32 HD_PIPELINE_V2; последний запуск 28.09 |
| gen_craft_lights.py | ACTIVE | 2026-09-28 | 356 |  | imp:check_craft_lights,craft_outline,facility_sheet…; R:043,082,087; doc:5 | в текущем конвейере (HD_PIPELINE_V2 §31 / PHOTO_BASE / DECISIONS 10.03-10.04) |
| gen_fire_real.py | ACTIVE | 2026-09-28 | 92 |  | doc:1; gpuq:1/2026-09-28 | в текущем конвейере (HD_PIPELINE_V2 §31 / PHOTO_BASE / DECISIONS 10.03-10.04) |
| gen_reticle.py | ACTIVE | 2026-09-25 | 307 |  | imp:gen_reticle_v2; R:042; doc:4 | в текущем конвейере (HD_PIPELINE_V2 §31 / PHOTO_BASE / DECISIONS 10.03-10.04) |
| gen_reticle_v2.py | ACTIVE | 2026-10-03 | 368 |  | - | прицелы v2 (03.10), ключи = Mod::HD_RETICLES; импортирует gen_reticle |
| ground_relief.py | ACTIVE | 2026-09-28 | 298 |  | R:118,127; doc:3; gpuq:5/2026-09-28 | лаборатория §32; последний запуск 28.09 (R-118) |
| hd_manifest.py | ACTIVE | 2026-09-30 | 498 | ЗАНЯТ | imp:test_hd_manifest; doc:3 | в текущем конвейере (HD_PIPELINE_V2 §31 / PHOTO_BASE / DECISIONS 10.03-10.04) |
| identity_auto.py | ACTIVE | 2026-10-05 | 487 | ЗАНЯТ | art:108 | автоопознание PROD_TWO_PASS_V2 (специалист 05.10), 108 ссылок в art/ |
| identity_propose.py | ACTIVE | 2026-09-30 | 940 | ЗАНЯТ | imp:arbiter,identity_card,test_identity_propose; R:143; doc:4; gpuq:6/2026-09-29 | ставился в очередь 2026-09-29 |
| item_photo.py | ACTIVE | 2026-10-03 | 1099 |  | imp:unit_direct,unit_parts,unit_pilot…; R:204,205,207,211; doc:7; art:1; gpuq:10/2026-10-03 | ставился в очередь 2026-10-03 |
| long_object.py | ACTIVE | 2026-09-28 | 574 |  | R:122; doc:5; gpuq:2/2026-09-28 | лаборатория §32; последний запуск 28.09 (R-122) |
| map_mockup.py | ACTIVE | 2026-09-26 | 352 |  | imp:acceptance_report,acceptance_run,cover_check…; R:071,117; doc:6; art:8 | в текущем конвейере (HD_PIPELINE_V2 §31 / PHOTO_BASE / DECISIONS 10.03-10.04) |
| model_lock.py | ACTIVE | 2026-09-30 | 249 | ЗАНЯТ | imp:obj_photo,photo_render,struct_probe…; R:145; doc:6; art:2 | в текущем конвейере (HD_PIPELINE_V2 §31 / PHOTO_BASE / DECISIONS 10.03-10.04) |
| obj_batch.py | ACTIVE | 2026-09-30 | 95 | ЗАНЯТ | R:125,132,136; doc:4 | в текущем конвейере (HD_PIPELINE_V2 §31 / PHOTO_BASE / DECISIONS 10.03-10.04) |
| obj_derive.py | ACTIVE | 2026-09-29 | 216 | ЗАНЯТ | imp:acceptance_run,derive_recolor_acceptance_v2; R:136,166,194,195; doc:13; art:2 | в текущем конвейере (HD_PIPELINE_V2 §31 / PHOTO_BASE / DECISIONS 10.03-10.04) |
| obj_families.py | ACTIVE | 2026-09-29 | 559 | ЗАНЯТ | imp:relation_probe,test_obj_families,test_relation_probe; R:136,140,166,194; doc:15; art:10 | в текущем конвейере (HD_PIPELINE_V2 §31 / PHOTO_BASE / DECISIONS 10.03-10.04) |
| obj_gen_spec.py | ACTIVE | 2026-10-01 | 267 | ЗАНЯТ | imp:acceptance_plan,item_photo,model_lock…; R:145; doc:2 | в текущем конвейере (HD_PIPELINE_V2 §31 / PHOTO_BASE / DECISIONS 10.03-10.04) |
| obj_generation.py | ACTIVE | 2026-10-01 | 513 | ЗАНЯТ | imp:test_obj_generation; R:140,148,153,163; doc:5 | в текущем конвейере (HD_PIPELINE_V2 §31 / PHOTO_BASE / DECISIONS 10.03-10.04) |
| obj_photo.py | ACTIVE | 2026-09-30 | 527 | ЗАНЯТ | imp:item_photo,photo_base,photo_render…; R:117,121,125,127; doc:21; art:23; gpuq:30/2026-10-03 | в текущем конвейере (HD_PIPELINE_V2 §31 / PHOTO_BASE / DECISIONS 10.03-10.04) |
| obj_push.py | ACTIVE | 2026-09-30 | 148 | ЗАНЯТ | - | установка принятых предметов в мод (v2 §38 - только через манифест); правится другой сесси |
| obj_queue.py | ACTIVE | 2026-09-30 | 286 | ЗАНЯТ | R:125,132,136,153; doc:9 | в текущем конвейере (HD_PIPELINE_V2 §31 / PHOTO_BASE / DECISIONS 10.03-10.04) |
| obj_review.py | ACTIVE | 2026-09-30 | 192 | ЗАНЯТ | imp:identity_card,review_server; doc:1 | в текущем конвейере (HD_PIPELINE_V2 §31 / PHOTO_BASE / DECISIONS 10.03-10.04) |
| obj_series.py | ACTIVE | 2026-09-28 | 511 |  | imp:cover_check,hd_e2e_v1_run,long_object…; R:089,112,116,119; doc:10; art:1; gpuq:17/2026-09-28 | лаборатория §32; предметы strict (DECISIONS 27.09); импортируют obj_photo, cover_check, lo |
| obj_struct.py | ACTIVE | 2026-09-29 | 298 | ЗАНЯТ | imp:craft_outline,identity_propose,obj_families…; R:140,177; doc:3; art:10 | в текущем конвейере (HD_PIPELINE_V2 §31 / PHOTO_BASE / DECISIONS 10.03-10.04) |
| optimize_hd.py | ACTIVE | 2026-09-30 | 329 | ЗАНЯТ | doc:10 | в текущем конвейере (HD_PIPELINE_V2 §31 / PHOTO_BASE / DECISIONS 10.03-10.04) |
| pedia_ab.py | ACTIVE | 2026-10-01 | 260 | ЗАНЯТ | R:101; doc:2; gpuq:14/2026-09-26 | в текущем конвейере (HD_PIPELINE_V2 §31 / PHOTO_BASE / DECISIONS 10.03-10.04) |
| pedia_batch.py | ACTIVE | 2026-10-01 | 489 | ЗАНЯТ | imp:pedia_nudecheck; R:101; doc:2; gpuq:50/2026-10-01 | в текущем конвейере (HD_PIPELINE_V2 §31 / PHOTO_BASE / DECISIONS 10.03-10.04) |
| pedia_nudecheck.py | ACTIVE | 2026-09-26 | 115 |  | gpuq:1/2026-09-26 | в текущем конвейере (HD_PIPELINE_V2 §31 / PHOTO_BASE / DECISIONS 10.03-10.04) |
| photo_accept.py | ACTIVE | 2026-10-01 | 626 | ЗАНЯТ | imp:photo_decomp,photo_render,photo_struct…; R:210; doc:3; art:5 | в текущем конвейере (HD_PIPELINE_V2 §31 / PHOTO_BASE / DECISIONS 10.03-10.04) |
| photo_base.py | ACTIVE | 2026-10-01 | 672 | ЗАНЯТ | imp:hd_e2e_v1_run,item_photo,photo_accept…; R:156,157,160,210; doc:10; art:6 | в текущем конвейере (HD_PIPELINE_V2 §31 / PHOTO_BASE / DECISIONS 10.03-10.04) |
| photo_render.py | ACTIVE | 2026-10-01 | 275 | ЗАНЯТ | imp:hd_e2e_v1_run,item_photo,photo_struct_render…; R:160,204; doc:4; art:4; gpuq:2/2026-10-01 | в текущем конвейере (HD_PIPELINE_V2 §31 / PHOTO_BASE / DECISIONS 10.03-10.04) |
| photo_struct_render.py | ACTIVE | 2026-10-01 | 122 | ЗАНЯТ | doc:3; art:1; gpuq:2/2026-10-01 | ставился в очередь 2026-10-01 |
| pilot_batch.py | ACTIVE | 2026-09-30 | 480 | ЗАНЯТ | imp:detail_class,photo_accept,photo_struct…; R:148,153; doc:2 | в текущем конвейере (HD_PIPELINE_V2 §31 / PHOTO_BASE / DECISIONS 10.03-10.04) |
| probe_floor.py | ACTIVE | 2026-09-27 | 457 |  | imp:floor_group,ground_relief; R:118; doc:2; gpuq:3/2026-09-27 | лаборатория §32; импортируется floor_group/ground_relief |
| prod_two_pass_v2.py | ACTIVE | 2026-10-05 | 240 | ЗАНЯТ | doc:1; gpuq:2/2026-10-05 | в текущем конвейере (HD_PIPELINE_V2 §31 / PHOTO_BASE / DECISIONS 10.03-10.04) |
| qwen_literal.py | ACTIVE | 2026-10-03 | 94 | ЗАНЯТ | gpuq:1/2026-10-03 | ставился в очередь 2026-10-03 |
| render_chunks.py | ACTIVE | 2026-10-01 | 161 | ЗАНЯТ | R:215; doc:3; art:1; gpuq:29/2026-10-05 | в текущем конвейере (HD_PIPELINE_V2 §31 / PHOTO_BASE / DECISIONS 10.03-10.04) |
| struct_guide.py | ACTIVE | 2026-10-01 | 360 | ЗАНЯТ | imp:hd_e2e_v1_run,item_photo,photo_struct_render…; R:160,220; doc:9; art:4 | в текущем конвейере (HD_PIPELINE_V2 §31 / PHOTO_BASE / DECISIONS 10.03-10.04) |
| unit_direct.py | ACTIVE | 2026-10-03 | 209 | ЗАНЯТ | R:208,211; doc:2; gpuq:3/2026-10-03 | в текущем конвейере (HD_PIPELINE_V2 §31 / PHOTO_BASE / DECISIONS 10.03-10.04) |
| unit_parts.py | ACTIVE | 2026-10-05 | 707 | ЗАНЯТ | imp:agent_full,agent_pose; R:212,219; doc:2; gpuq:11/2026-10-05 | в текущем конвейере (HD_PIPELINE_V2 §31 / PHOTO_BASE / DECISIONS 10.03-10.04) |
| unit_pilot.py | ACTIVE | 2026-10-03 | 644 | ЗАНЯТ | imp:unit_direct,unit_parts,unit_ref…; R:205,208,211,212; doc:7; gpuq:2/2026-10-03 | ставился в очередь 2026-10-03 |
| unit_turnaround.py | ACTIVE | 2026-10-04 | 1151 | ЗАНЯТ | imp:unit_parts; R:217,218,219; doc:3; art:1; gpuq:24/2026-10-04 | в текущем конвейере (HD_PIPELINE_V2 §31 / PHOTO_BASE / DECISIONS 10.03-10.04) |
| upscale_units.py | ACTIVE | 2026-10-02 | 847 |  | imp:weapons_sr; R:030,175; doc:21; gpuq:2/2026-10-02 | в текущем конвейере (HD_PIPELINE_V2 §31 / PHOTO_BASE / DECISIONS 10.03-10.04) |
| visual_judge.py | ACTIVE | 2026-10-05 | 550 | ЗАНЯТ | imp:identity_auto; doc:1 | визуальный судья PROD_TWO_PASS_V2 (специалист 05.10) |
| weapon_ammo_cards.py | ACTIVE | 2026-10-05 | 335 | ЗАНЯТ | imp:weapon_handob_cards; art:2 | новый 05.10: карточки оружие+боеприпас (серия weapons100) |
| weapon_describe_merge.py | ACTIVE | 2026-10-05 | 72 | ЗАНЯТ | art:1 | новый 05.10: свод описаний сотни weapons100 |
| weapon_fit.py | ACTIVE | 2026-10-05 | 1301 | ЗАНЯТ | imp:test_weapon_fit,test_weapon_parts,weapon_accept…; R:089,220,226,229; doc:4; art:2 | в текущем конвейере (HD_PIPELINE_V2 §31 / PHOTO_BASE / DECISIONS 10.03-10.04) |
| weapon_handob_cards.py | ACTIVE | 2026-10-05 | 298 | ЗАНЯТ | doc:1; art:1 | новый 05.10: карточки HANDOB (серия weapons100), импортирует weapon_ammo_cards |
| weapon_judge.py | ACTIVE | 2026-10-05 | 608 | ЗАНЯТ | R:231; doc:1; art:2 | в текущем конвейере (HD_PIPELINE_V2 §31 / PHOTO_BASE / DECISIONS 10.03-10.04) |
| weapon_part_fit.py | ACTIVE | 2026-10-05 | 441 | ЗАНЯТ | imp:test_weapon_part_fit; art:1 | новый 05.10: доводка частей оружия без генерации (серия weapons100) |
| weapon_parts.py | ACTIVE | 2026-10-05 | 1300 | ЗАНЯТ | imp:test_weapon_parts,weapon_accept,weapon_judge; R:227,229; doc:2; art:4 | в текущем конвейере (HD_PIPELINE_V2 §31 / PHOTO_BASE / DECISIONS 10.03-10.04) |
| weapons_batch.py | ACTIVE | 2026-10-03 | 130 | ЗАНЯТ | art:1; gpuq:4/2026-10-03 | ставился в очередь 2026-10-03 |
| weapons_chatgpt.py | ACTIVE | 2026-10-05 | 356 | ЗАНЯТ | R:222,226; doc:2; art:6 | в текущем конвейере (HD_PIPELINE_V2 §31 / PHOTO_BASE / DECISIONS 10.03-10.04) |
| weapons_edit.py | ACTIVE | 2026-10-04 | 332 | ЗАНЯТ | imp:weapons_probe3,weapons_probe4,weapons_probe5…; gpuq:2/2026-10-04 | ставился в очередь 2026-10-04 |
| weapons_redraw.py | ACTIVE | 2026-10-05 | 266 | ЗАНЯТ | R:221; doc:1; art:1; gpuq:1/2026-10-05 | ставился в очередь 2026-10-05 |
| weapons_restore.py | ACTIVE | 2026-10-04 | 162 | ЗАНЯТ | art:1; gpuq:1/2026-10-04 | ставился в очередь 2026-10-04 |
| weapons_sr.py | ACTIVE | 2026-10-03 | 105 | ЗАНЯТ | gpuq:2/2026-10-03 | ставился в очередь 2026-10-03 |
| weapons_synth.py | ACTIVE | 2026-10-04 | 223 | ЗАНЯТ | imp:weapons_redraw; R:220,221; doc:2; gpuq:2/2026-10-04 | ставился в очередь 2026-10-04 |

### ACTIVE-LIB (библиотеки, которых держит импорт)

| файл | класс | изменён | строк | занят | ссылки | цепочка до ядра |
|---|---|---|---|---|---|---|
| acceptance_plan.py | ACTIVE-LIB (заморож. имя) | 2026-09-30 | 564 | ЗАНЯТ | imp:acceptance_report,acceptance_run,pilot_batch… | pilot_batch |
| acceptance_run.py | ACTIVE-LIB (заморож. имя) | 2026-09-30 | 367 | ЗАНЯТ | imp:acceptance_report,obj_photo,pilot_report… | obj_photo |
| aligned_recolor_v1.py | ACTIVE-LIB (заморож. имя) | 2026-10-02 | 182 | ЗАНЯТ | imp:aligned_recolor_v2,ar_boundary_validation,relation_discovery_v5… | v5_ar2_recount <- relation_holdout_v7 <- hd_e2e_v1 <- restore_batch_v1 <- prod_two_pass_v1 <- prod_two_pass_v2 |
| aligned_recolor_v2.py | ACTIVE-LIB (заморож. имя) | 2026-10-02 | 105 | ЗАНЯТ | imp:hd_e2e_v1,relation_holdout_v5,relation_holdout_v7… | hd_e2e_v1 <- restore_batch_v1 <- prod_two_pass_v1 <- prod_two_pass_v2 |
| ar_boundary_validation.py | ACTIVE-LIB (заморож. имя) | 2026-10-02 | 422 | ЗАНЯТ | imp:aligned_recolor_v2,relation_safety_v7_prep,test_ar_boundary_validation… | relation_safety_v7_prep <- hd_e2e_v1 <- restore_batch_v1 <- prod_two_pass_v1 <- prod_two_pass_v2 |
| assembly_discovery_v1.py | ACTIVE-LIB (заморож. имя) | 2026-10-02 | 242 | ЗАНЯТ | imp:assembly_group_v1,assembly_repeated_v1,hd_e2e_v1… | hd_e2e_v1 <- restore_batch_v1 <- prod_two_pass_v1 <- prod_two_pass_v2 |
| assembly_evidence_v2_prep.py | ACTIVE-LIB (заморож. имя) | 2026-10-02 | 547 | ЗАНЯТ | imp:relation_safety_v7_prep | relation_safety_v7_prep <- hd_e2e_v1 <- restore_batch_v1 <- prod_two_pass_v1 <- prod_two_pass_v2 |
| assembly_group_v1.py | ACTIVE-LIB (заморож. имя) | 2026-10-02 | 225 | ЗАНЯТ | imp:assembly_evidence_v2_prep,hd_e2e_v1,relation_holdout_v7… | hd_e2e_v1 <- restore_batch_v1 <- prod_two_pass_v1 <- prod_two_pass_v2 |
| assembly_repeated_v1.py | ACTIVE-LIB (заморож. имя) | 2026-10-02 | 202 | ЗАНЯТ | imp:assembly_evidence_v2_prep,hd_e2e_v1,relation_holdout_v7… | hd_e2e_v1 <- restore_batch_v1 <- prod_two_pass_v1 <- prod_two_pass_v2 |
| axis_a_clean_v5.py | ACTIVE-LIB (заморож. имя) | 2026-10-02 | 142 | ЗАНЯТ | imp:relation_holdout_v7 | relation_holdout_v7 <- hd_e2e_v1 <- restore_batch_v1 <- prod_two_pass_v1 <- prod_two_pass_v2 |
| derive_recolor_acceptance_v2.py | ACTIVE-LIB (заморож. имя) | 2026-10-03 | 777 | ЗАНЯТ | imp:derive_recolor_acceptance_v2_report_fix,derive_recolor_acceptance_v3,derive_recolor_acceptance_v31… | derive_recolor_acceptance_v3 <- hd_e2e_v1_run <- prod_two_pass_v1 <- prod_two_pass_v2 |
| derive_recolor_acceptance_v3.py | ACTIVE-LIB (заморож. имя) | 2026-10-03 | 766 | ЗАНЯТ | imp:derive_recolor_acceptance_v31,derive_recolor_acceptance_v32,derive_recolor_base_acceptance_v1… | hd_e2e_v1_run <- prod_two_pass_v1 <- prod_two_pass_v2 |
| derive_recolor_acceptance_v31.py | ACTIVE-LIB (заморож. имя) | 2026-10-03 | 540 | ЗАНЯТ | imp:derive_recolor_acceptance_v32,derive_recolor_base_acceptance_v1,derive_recolor_v33_dev | derive_recolor_base_acceptance_v1 <- derive_recolor_safe_acceptance_v1 <- hd_e2e_v1_run <- prod_two_pass_v1 <- prod_two_ |
| derive_recolor_acceptance_v32.py | ACTIVE-LIB (заморож. имя) | 2026-10-03 | 857 | ЗАНЯТ | imp:derive_recolor_base_acceptance_v1,derive_recolor_v33_dev | derive_recolor_base_acceptance_v1 <- derive_recolor_safe_acceptance_v1 <- hd_e2e_v1_run <- prod_two_pass_v1 <- prod_two_ |
| derive_recolor_base_acceptance_v1.py | ACTIVE-LIB (заморож. имя) | 2026-10-03 | 851 | ЗАНЯТ | imp:derive_recolor_base_acceptance_v11,derive_recolor_safe_acceptance_v1 | derive_recolor_safe_acceptance_v1 <- hd_e2e_v1_run <- prod_two_pass_v1 <- prod_two_pass_v2 |
| derive_recolor_base_v1.py | ACTIVE-LIB (заморож. имя) | 2026-10-03 | 99 | ЗАНЯТ | imp:derive_recolor_base_acceptance_v1 | derive_recolor_base_acceptance_v1 <- derive_recolor_safe_acceptance_v1 <- hd_e2e_v1_run <- prod_two_pass_v1 <- prod_two_ |
| derive_recolor_safe_acceptance_v1.py | ACTIVE-LIB (заморож. имя) | 2026-10-03 | 534 | ЗАНЯТ | imp:hd_e2e_v1_r33,hd_e2e_v1_run | hd_e2e_v1_run <- prod_two_pass_v1 <- prod_two_pass_v2 |
| derive_recolor_v3.py | ACTIVE-LIB (заморож. имя) | 2026-10-03 | 266 | ЗАНЯТ | imp:derive_recolor_acceptance_v3,derive_recolor_acceptance_v31,derive_recolor_acceptance_v32… | derive_recolor_acceptance_v3 <- hd_e2e_v1_run <- prod_two_pass_v1 <- prod_two_pass_v2 |
| derive_recolor_v31.py | ACTIVE-LIB (заморож. имя) | 2026-10-03 | 264 | ЗАНЯТ | imp:derive_recolor_acceptance_v31,derive_recolor_acceptance_v32,derive_recolor_base_acceptance_v1… | derive_recolor_base_acceptance_v1 <- derive_recolor_safe_acceptance_v1 <- hd_e2e_v1_run <- prod_two_pass_v1 <- prod_two_ |
| derive_recolor_v32.py | ACTIVE-LIB (заморож. имя) | 2026-10-03 | 169 | ЗАНЯТ | imp:derive_recolor_acceptance_v32 | derive_recolor_acceptance_v32 <- derive_recolor_base_acceptance_v1 <- derive_recolor_safe_acceptance_v1 <- hd_e2e_v1_run |
| derive_recolor_v33_dev.py | ACTIVE-LIB (заморож. имя) | 2026-10-03 | 540 | ЗАНЯТ | imp:derive_recolor_base_acceptance_v1,derive_recolor_v33_rdiag | derive_recolor_base_acceptance_v1 <- derive_recolor_safe_acceptance_v1 <- hd_e2e_v1_run <- prod_two_pass_v1 <- prod_two_ |
| families_recolor_diff.py | ACTIVE-LIB (заморож. имя) | 2026-10-01 | 235 | ЗАНЯТ | imp:family_relation_v2,test_families_recolor_diff | family_relation_v2 <- relation_holdout_v4 <- hd_e2e_v1 <- restore_batch_v1 <- prod_two_pass_v1 <- prod_two_pass_v2 |
| family_relation_v2.py | ACTIVE-LIB (заморож. имя) | 2026-10-01 | 194 | ЗАНЯТ | imp:relation_holdout_v4,relation_holdout_v5,relation_holdout_v7… | relation_holdout_v4 <- hd_e2e_v1 <- restore_batch_v1 <- prod_two_pass_v1 <- prod_two_pass_v2 |
| hd_e2e_v1.py | ACTIVE-LIB (заморож. имя) | 2026-10-03 | 914 | ЗАНЯТ | imp:hd_e2e_v1_identity,hd_e2e_v1_r2,hd_e2e_v1_r3… | restore_batch_v1 <- prod_two_pass_v1 <- prod_two_pass_v2 |
| hd_e2e_v1_r33.py | ACTIVE-LIB (заморож. имя) | 2026-10-03 | 390 | ЗАНЯТ | imp:hd_e2e_v1_run | hd_e2e_v1_run <- prod_two_pass_v1 <- prod_two_pass_v2 |
| hd_e2e_v1_run.py | ACTIVE-LIB (заморож. имя) | 2026-10-03 | 324 | ЗАНЯТ | imp:prod_two_pass_v1,restore_batch_v1,restore_probe_v1 | prod_two_pass_v1 <- prod_two_pass_v2 |
| identity_card.py | ACTIVE-LIB (заморож. имя) | 2026-10-01 | 769 | ЗАНЯТ | imp:hd_e2e_v1_identity,identity_holdout,routing_holdout… | routing_holdout <- relation_holdout_v4 <- hd_e2e_v1 <- restore_batch_v1 <- prod_two_pass_v1 <- prod_two_pass_v2 |
| identity_routing.py | ACTIVE-LIB (заморож. имя) | 2026-10-01 | 515 | ЗАНЯТ | imp:aligned_recolor_v2,ar_boundary_validation,assembly_evidence_v2_prep… | hd_e2e_v1 <- restore_batch_v1 <- prod_two_pass_v1 <- prod_two_pass_v2 |
| mcd_state.py | ACTIVE-LIB (заморож. имя) | 2026-10-01 | 227 | ЗАНЯТ | imp:relation_discovery_v2,relation_holdout_v4,relation_holdout_v5… | relation_holdout_v4 <- hd_e2e_v1 <- restore_batch_v1 <- prod_two_pass_v1 <- prod_two_pass_v2 |
| post_review_safety.py | ACTIVE-LIB (заморож. имя) | 2026-10-02 | 71 | ЗАНЯТ | imp:assembly_evidence_v2_prep,relation_holdout_v5,relation_holdout_v7… | relation_holdout_v7 <- hd_e2e_v1 <- restore_batch_v1 <- prod_two_pass_v1 <- prod_two_pass_v2 |
| probe_object.py | ACTIVE-LIB (заморож. имя) | 2026-09-28 | 316 |  | imp:item_photo,long_object,obj_photo… | item_photo |
| prod_two_pass_v1.py | ACTIVE-LIB (заморож. имя) | 2026-10-04 | 431 | ЗАНЯТ | imp:prod_two_pass_v2 | prod_two_pass_v2 |
| relation_discovery_v2.py | ACTIVE-LIB (заморож. имя) | 2026-10-02 | 930 | ЗАНЯТ | imp:aligned_recolor_v1,aligned_recolor_v2,ar_boundary_validation… | relation_discovery_v3 <- hd_e2e_v1 <- restore_batch_v1 <- prod_two_pass_v1 <- prod_two_pass_v2 |
| relation_discovery_v3.py | ACTIVE-LIB (заморож. имя) | 2026-10-02 | 855 | ЗАНЯТ | imp:ar_boundary_validation,assembly_discovery_v1,assembly_evidence_v2_prep… | hd_e2e_v1 <- restore_batch_v1 <- prod_two_pass_v1 <- prod_two_pass_v2 |
| relation_discovery_v4.py | ACTIVE-LIB (заморож. имя) | 2026-10-02 | 819 | ЗАНЯТ | imp:aligned_recolor_v1,aligned_recolor_v2,ar_boundary_validation… | restore_batch_v1 <- prod_two_pass_v1 <- prod_two_pass_v2 |
| relation_discovery_v5.py | ACTIVE-LIB (заморож. имя) | 2026-10-02 | 608 | ЗАНЯТ | imp:relation_holdout_v5,relation_holdout_v7,relation_safety_v7_prep… | relation_holdout_v7 <- hd_e2e_v1 <- restore_batch_v1 <- prod_two_pass_v1 <- prod_two_pass_v2 |
| relation_holdout_v4.py | ACTIVE-LIB (заморож. имя) | 2026-10-02 | 1103 | ЗАНЯТ | imp:ar_boundary_validation,assembly_evidence_v2_prep,hd_e2e_v1… | hd_e2e_v1 <- restore_batch_v1 <- prod_two_pass_v1 <- prod_two_pass_v2 |
| relation_holdout_v4_axis_zip.py | ACTIVE-LIB (заморож. имя) | 2026-10-02 | 129 | ЗАНЯТ | imp:axis_a_clean_v5,relation_holdout_v7 | relation_holdout_v7 <- hd_e2e_v1 <- restore_batch_v1 <- prod_two_pass_v1 <- prod_two_pass_v2 |
| relation_holdout_v4_ref.py | ACTIVE-LIB (заморож. имя) | 2026-10-02 | 344 | ЗАНЯТ | imp:relation_discovery_v5,relation_holdout_v5,relation_holdout_v7… | relation_holdout_v7 <- hd_e2e_v1 <- restore_batch_v1 <- prod_two_pass_v1 <- prod_two_pass_v2 |
| relation_holdout_v5.py | ACTIVE-LIB (заморож. имя) | 2026-10-02 | 1121 | ЗАНЯТ | imp:assembly_evidence_v2_prep,relation_holdout_v7,relation_safety_v7_prep… | relation_holdout_v7 <- hd_e2e_v1 <- restore_batch_v1 <- prod_two_pass_v1 <- prod_two_pass_v2 |
| relation_holdout_v7.py | ACTIVE-LIB (заморож. имя) | 2026-10-03 | 1105 | ЗАНЯТ | imp:hd_e2e_v1,hd_e2e_v1_identity,test_relation_holdout_v7 | hd_e2e_v1 <- restore_batch_v1 <- prod_two_pass_v1 <- prod_two_pass_v2 |
| relation_probe.py | ACTIVE-LIB (заморож. имя) | 2026-10-01 | 702 | ЗАНЯТ | imp:aligned_recolor_v1,families_recolor_diff,family_relation_v2… | hd_e2e_v1 <- restore_batch_v1 <- prod_two_pass_v1 <- prod_two_pass_v2 |
| relation_safety_v7_prep.py | ACTIVE-LIB (заморож. имя) | 2026-10-02 | 612 | ЗАНЯТ | imp:hd_e2e_v1,hd_e2e_v1_r2,hd_e2e_v1_r3… | hd_e2e_v1 <- restore_batch_v1 <- prod_two_pass_v1 <- prod_two_pass_v2 |
| relation_taxonomy.py | ACTIVE-LIB (заморож. имя) | 2026-10-02 | 1044 | ЗАНЯТ | imp:ar_boundary_validation,hd_e2e_v1,hd_e2e_v1_r2… | hd_e2e_v1 <- restore_batch_v1 <- prod_two_pass_v1 <- prod_two_pass_v2 |
| relation_truth_v2.py | ACTIVE-LIB (заморож. имя) | 2026-10-02 | 576 | ЗАНЯТ | imp:ar_boundary_validation,hd_e2e_v1_review,relation_discovery_v4… | relation_discovery_v4 <- restore_batch_v1 <- prod_two_pass_v1 <- prod_two_pass_v2 |
| relation_v6_prep.py | ACTIVE-LIB (заморож. имя) | 2026-10-02 | 499 | ЗАНЯТ | imp:assembly_evidence_v2_prep,relation_safety_v7_prep | relation_safety_v7_prep <- hd_e2e_v1 <- restore_batch_v1 <- prod_two_pass_v1 <- prod_two_pass_v2 |
| restore_batch_v1.py | ACTIVE-LIB (заморож. имя) | 2026-10-03 | 619 | ЗАНЯТ | imp:prod_two_pass_v1 | prod_two_pass_v1 <- prod_two_pass_v2 |
| restore_probe_v1.py | ACTIVE-LIB (заморож. имя) | 2026-10-03 | 264 | ЗАНЯТ | imp:restore_batch_v1,restore_probe_v1b,restore_probe_v1c… | weapons_restore |
| restore_probe_v1b.py | ACTIVE-LIB (заморож. имя) | 2026-10-03 | 48 | ЗАНЯТ | imp:restore_batch_v1,restore_probe_v1c | restore_batch_v1 <- prod_two_pass_v1 <- prod_two_pass_v2 |
| routing_holdout.py | ACTIVE-LIB (заморож. имя) | 2026-10-01 | 1011 | ЗАНЯТ | imp:hd_e2e_v1_identity,relation_holdout_v4,relation_holdout_v5… | relation_holdout_v4 <- hd_e2e_v1 <- restore_batch_v1 <- prod_two_pass_v1 <- prod_two_pass_v2 |
| routing_holdout_diag.py | ACTIVE-LIB (заморож. имя) | 2026-10-01 | 238 | ЗАНЯТ | imp:routing_holdout_diag2,routing_rules_v5,test_routing_holdout_diag | routing_rules_v5 <- routing_holdout_v5 <- relation_holdout_v4 <- hd_e2e_v1 <- restore_batch_v1 <- prod_two_pass_v1 <- pr |
| routing_holdout_diag2.py | ACTIVE-LIB (заморож. имя) | 2026-10-01 | 322 | ЗАНЯТ | imp:routing_rules_v5,test_routing_holdout_diag2 | routing_rules_v5 <- routing_holdout_v5 <- relation_holdout_v4 <- hd_e2e_v1 <- restore_batch_v1 <- prod_two_pass_v1 <- pr |
| routing_holdout_v5.py | ACTIVE-LIB (заморож. имя) | 2026-10-01 | 759 | ЗАНЯТ | imp:relation_holdout_v4,routing_holdout_v7,routing_holdout_v8… | relation_holdout_v4 <- hd_e2e_v1 <- restore_batch_v1 <- prod_two_pass_v1 <- prod_two_pass_v2 |
| routing_holdout_v7.py | ACTIVE-LIB (заморож. имя) | 2026-10-02 | 684 | ЗАНЯТ | imp:relation_holdout_v4,relation_holdout_v5,relation_holdout_v7… | relation_holdout_v4 <- hd_e2e_v1 <- restore_batch_v1 <- prod_two_pass_v1 <- prod_two_pass_v2 |
| routing_holdout_v8.py | ACTIVE-LIB (заморож. имя) | 2026-10-02 | 779 | ЗАНЯТ | imp:hd_e2e_v1_identity,relation_holdout_v4,relation_holdout_v5… | relation_holdout_v4 <- hd_e2e_v1 <- restore_batch_v1 <- prod_two_pass_v1 <- prod_two_pass_v2 |
| routing_model_v8.py | ACTIVE-LIB (заморож. имя) | 2026-10-02 | 1058 | ЗАНЯТ | imp:ar_boundary_validation,hd_e2e_v1,hd_e2e_v1_identity… | hd_e2e_v1 <- restore_batch_v1 <- prod_two_pass_v1 <- prod_two_pass_v2 |
| routing_rules.py | ACTIVE-LIB (заморож. имя) | 2026-10-01 | 326 | ЗАНЯТ | imp:relation_holdout_v4,routing_holdout,routing_holdout_v5… | relation_holdout_v4 <- hd_e2e_v1 <- restore_batch_v1 <- prod_two_pass_v1 <- prod_two_pass_v2 |
| routing_rules_v5.py | ACTIVE-LIB (заморож. имя) | 2026-10-01 | 540 | ЗАНЯТ | imp:routing_holdout_v5,routing_holdout_v7,routing_model_v8… | routing_holdout_v5 <- relation_holdout_v4 <- hd_e2e_v1 <- restore_batch_v1 <- prod_two_pass_v1 <- prod_two_pass_v2 |
| routing_rules_v6.py | ACTIVE-LIB (заморож. имя) | 2026-10-02 | 843 | ЗАНЯТ | imp:routing_holdout_v7,routing_model_v8,routing_rules_v7… | routing_holdout_v7 <- relation_holdout_v4 <- hd_e2e_v1 <- restore_batch_v1 <- prod_two_pass_v1 <- prod_two_pass_v2 |
| routing_rules_v7.py | ACTIVE-LIB (заморож. имя) | 2026-10-02 | 705 | ЗАНЯТ | imp:hd_e2e_v1,relation_holdout_v4,relation_holdout_v5… | hd_e2e_v1 <- restore_batch_v1 <- prod_two_pass_v1 <- prod_two_pass_v2 |
| strict_ctl_v1.py | ACTIVE-LIB (заморож. имя) | 2026-10-03 | 303 | ЗАНЯТ | imp:prod_two_pass_v1,prod_two_pass_v2 | prod_two_pass_v2 |
| struct_probe.py | ACTIVE-LIB (заморож. имя) | 2026-10-01 | 339 | ЗАНЯТ | imp:hd_e2e_v1_run,item_photo,photo_struct_render… | item_photo |
| two_component_v1.py | ACTIVE-LIB (заморож. имя) | 2026-10-02 | 179 | ЗАНЯТ | imp:assembly_evidence_v2_prep,hd_e2e_v1,relation_holdout_v7… | hd_e2e_v1 <- restore_batch_v1 <- prod_two_pass_v1 <- prod_two_pass_v2 |
| v5_ar2_recount.py | ACTIVE-LIB (заморож. имя) | 2026-10-02 | 598 | ЗАНЯТ | imp:assembly_evidence_v2_prep,relation_holdout_v5,relation_holdout_v7… | relation_holdout_v7 <- hd_e2e_v1 <- restore_batch_v1 <- prod_two_pass_v1 <- prod_two_pass_v2 |
| v5_component_validation.py | ACTIVE-LIB (заморож. имя) | 2026-10-02 | 630 | ЗАНЯТ | imp:ar_boundary_validation,relation_holdout_v5,test_v5_component_validation… | v5_freeze_readiness <- relation_safety_v7_prep <- hd_e2e_v1 <- restore_batch_v1 <- prod_two_pass_v1 <- prod_two_pass_v2 |
| v5_freeze_readiness.py | ACTIVE-LIB (заморож. имя) | 2026-10-02 | 405 | ЗАНЯТ | imp:relation_safety_v7_prep,test_v5_freeze_readiness,v5_ar2_recount | relation_safety_v7_prep <- hd_e2e_v1 <- restore_batch_v1 <- prod_two_pass_v1 <- prod_two_pass_v2 |
| weapons_probe3.py | ACTIVE-LIB (заморож. имя) | 2026-10-04 | 201 | ЗАНЯТ | imp:weapons_probe4,weapons_probe5,weapons_restore | weapons_probe5 <- unit_parts |
| weapons_probe5.py | ACTIVE-LIB (заморож. имя) | 2026-10-04 | 205 | ЗАНЯТ | imp:unit_parts,unit_turnaround,weapons_restore | unit_parts |
| asset_rev.py | ACTIVE-LIB | 2026-09-29 | 114 | ЗАНЯТ | imp:acceptance_plan,acceptance_run,item_photo… | item_photo |
| build_dataset.py | ACTIVE-LIB | 2026-09-22 | 621 |  | imp:build,dupe_sets,gen_lora_batch… | score_batch <- map_mockup |
| common.py | ACTIVE-LIB | 2026-09-26 | 14 |  | imp:build,build_hd_pack,carpet_check… | build_hd_pack |
| detail_class.py | ACTIVE-LIB | 2026-09-30 | 318 | ЗАНЯТ | imp:photo_accept,photo_probe,simple_probe… | photo_accept |
| dupe_plan.py | ACTIVE-LIB | 2026-09-22 | 150 |  | imp:gen_lora_batch,merge_best,merge_gens… | score_batch <- map_mockup |
| floor_context.py | ACTIVE-LIB | 2026-09-27 | 225 |  | imp:floor_group | floor_group |
| gen_base.py | ACTIVE-LIB | 2026-09-17 | 200 |  | imp:check_craft_lights,craft_outline,facility_sheet… | gen_craft_lights |
| gen_fire.py | ACTIVE-LIB | 2026-09-22 | 274 |  | imp:floor_group,gen_cursor,gen_fire_real… | floor_group |
| gen_hd.py | ACTIVE-LIB | 2026-09-30 | 1908 | ЗАНЯТ | imp:ab_sdxl,check_floors,field_sweep… | floor_group |
| gen_lora_test.py | ACTIVE-LIB | 2026-09-22 | 238 |  | imp:gen_lora_batch,paint3,pedia_ab… | pedia_ab |
| hints.py | ACTIVE-LIB | 2026-09-15 | 294 |  | imp:floor_sheets,gen_hd,list_ground_sets… | gen_hd <- floor_group |
| item_asset_check.py | ACTIVE-LIB | 2026-10-03 | 158 |  | imp:item_geometry,item_photo,test_item_asset_check… | item_photo |
| map_paint.py | ACTIVE-LIB | 2026-09-27 | 1287 |  | imp:floor_context,map_update,obj_photo… | obj_photo |
| pedia_push.py | ACTIVE-LIB | 2026-09-26 | 110 |  | imp:pedia_nudecheck | pedia_nudecheck |
| photo_ui.py | ACTIVE-LIB | 2026-09-22 | 1017 |  | imp:gen_hd,ground_relief,item_photo… | gen_hd <- floor_group |
| review_server.py | ACTIVE-LIB | 2026-10-01 | 370 | ЗАНЯТ | imp:arbiter,identity_card,identity_propose… | arbiter |
| score_batch.py | ACTIVE-LIB | 2026-09-26 | 380 |  | imp:ab_sdxl,ab_sheet,build… | map_mockup |
| sprite_scale.py | ACTIVE-LIB | 2026-09-16 | 314 |  | imp:long_object,photo_base,probe_object… | long_object |
| subjects_terrain.py | ACTIVE-LIB | 2026-09-19 | 311 |  | imp:check_floors,field_sweep,gen_hd… | gen_hd <- floor_group |
| tile_forge.py | ACTIVE-LIB | 2026-09-22 | 491 |  | imp:ab_sdxl,ab_sheet,build… | map_mockup |
| tile_qa.py | ACTIVE-LIB | 2026-09-30 | 457 | ЗАНЯТ | imp:acceptance_report,acceptance_run,detail_probe | acceptance_run <- obj_photo |
| vx_control.py | ACTIVE-LIB | 2026-09-28 | 176 |  | imp:obj_photo | obj_photo |
| weapon_accept.py | ACTIVE-LIB | 2026-10-05 | 434 | ЗАНЯТ | imp:weapon_judge | weapon_judge |
| weapon_from_ref.py | ACTIVE-LIB | 2026-10-05 | 180 | ЗАНЯТ | imp:weapon_accept,weapon_judge,weapon_parts | weapon_judge |
| xcom_sprites.py | ACTIVE-LIB | 2026-09-25 | 317 |  | imp:build_pack,check_floors,extract_pck… | extract_pck |

**Замечание по цепочке.** `restore_batch_v1.py` (производственная партия RESTORE) импортирует `hd_e2e_v1_run as e2e` (строка 206, ради `e2e.sprite_frame`, строка 245) и `hd_e2e_v1 as E` (строка 329: «замороженные детекторы V7, только чтение» — `E.Discovery`, `E.build`); `prod_two_pass_v1.py` — тот же `hd_e2e_v1_run` (строка 302), а `hd_e2e_v1_run` на шаге derive импортирует `derive_recolor_acceptance_v3`, `derive_recolor_safe_acceptance_v1`, `hd_e2e_v1_r33` (строки 189–191) — то есть и весь derive_recolor-стек. Все эти импорты **внутри функций** (ленивые): перенос в другую папку сломает не запуск, а конкретный шаг (select/build/derive) в момент вызова — ошибки до прогона не будет. Дальше `hd_e2e_v1` тянет `relation_holdout_v7`, `relation_holdout_v4`, `relation_discovery_v3/v4`, `relation_taxonomy`, `relation_safety_v7_prep`, `identity_routing`, и дальше по цепочке — весь стек holdout'ов (≈68 модулей, 34550 строк). Любой перенос этих файлов в `frozen/` без правки `sys.path` сломает сегодняшний `prod_two_pass_v2 strict`.

### FROZEN

| файл | класс | изменён | строк | занят | ссылки | почему |
|---|---|---|---|---|---|---|
| acceptance_batch.py | FROZEN | 2026-09-29 | 125 | ЗАНЯТ | doc:1 | одноразовая приёмка/проба/holdout по имени и докстрингу |
| acceptance_report.py | FROZEN | 2026-09-30 | 359 | ЗАНЯТ | doc:1 | одноразовая приёмка/проба/holdout по имени и докстрингу |
| arbiter.py | FROZEN | 2026-09-30 | 847 | ЗАНЯТ | imp:arbiter_v2,test_arbiter,test_arbiter_v2…; doc:3; gpuq:1/2026-09-30 | P1-C арбитр: DECISIONS 30.09 - массово не применять до FALSE_CONFIDENT; библиотека для rev |
| arbiter_v2.py | FROZEN | 2026-09-30 | 478 | ЗАНЯТ | imp:test_arbiter_v2 | одноразовая приёмка/проба/holdout по имени и докстрингу |
| derive_recolor_base_acceptance_v11.py | FROZEN | 2026-10-03 | 661 | ЗАНЯТ | doc:1; art:1 | одноразовая приёмка/проба/holdout по имени и докстрингу; вердикт: ## 2026-10-03 — DERIVE_R |
| derive_recolor_v33_rdiag.py | FROZEN | 2026-10-03 | 191 | ЗАНЯТ | doc:1 | одноразовая приёмка/проба/holdout по имени и докстрингу; вердикт: ## 2026-10-03 — UNIVERSA |
| detail_probe.py | FROZEN | 2026-09-30 | 402 | ЗАНЯТ | imp:photo_probe,simple_probe; doc:1 | одноразовая приёмка/проба/holdout по имени и докстрингу |
| hd_e2e_v1_identity.py | FROZEN | 2026-10-03 | 160 | ЗАНЯТ | - | одноразовая приёмка/проба/holdout по имени и докстрингу |
| hd_e2e_v1_r2.py | FROZEN | 2026-10-03 | 790 | ЗАНЯТ | imp:hd_e2e_v1_r3,test_hd_e2e_v1_r2 | одноразовая приёмка/проба/holdout по имени и докстрингу |
| hd_e2e_v1_r3.py | FROZEN | 2026-10-03 | 1141 | ЗАНЯТ | imp:hd_e2e_v1_r31,hd_e2e_v1_r32,test_hd_e2e_v1_r3… | одноразовая приёмка/проба/holdout по имени и докстрингу |
| hd_e2e_v1_r31.py | FROZEN | 2026-10-03 | 135 | ЗАНЯТ | imp:hd_e2e_v1_r32,test_hd_e2e_v1_r31 | одноразовая приёмка/проба/holdout по имени и докстрингу |
| hd_e2e_v1_r32.py | FROZEN | 2026-10-03 | 312 | ЗАНЯТ | doc:1 | одноразовая приёмка/проба/holdout по имени и докстрингу; вердикт: ## 2026-10-03 — DERIVE_R |
| hd_e2e_v1_review.py | FROZEN | 2026-10-03 | 310 | ЗАНЯТ | imp:hd_e2e_v1_r32 | одноразовая приёмка/проба/holdout по имени и докстрингу |
| identity_holdout.py | FROZEN | 2026-10-01 | 390 | ЗАНЯТ | imp:test_identity_holdout; doc:2 | одноразовая приёмка/проба/holdout по имени и докстрингу |
| oldauto_ab_v1.py | FROZEN | 2026-10-03 | 408 | ЗАНЯТ | doc:1 | одноразовая приёмка/проба/holdout по имени и докстрингу; вердикт: ## 2026-10-03 — RESTORE: |
| photo_decomp.py | FROZEN | 2026-10-01 | 322 | ЗАНЯТ | imp:test_photo_decomp; R:160; doc:1 | одноразовая приёмка/проба/holdout по имени и докстрингу |
| photo_probe.py | FROZEN | 2026-09-30 | 213 | ЗАНЯТ | R:153; doc:2 | одноразовая приёмка/проба/holdout по имени и докстрингу |
| photo_struct.py | FROZEN | 2026-10-01 | 593 | ЗАНЯТ | doc:3 | PHOTO_STRUCT_ACCEPTANCE_V1 (01.10) |
| repro_smoke.py | FROZEN | 2026-09-30 | 233 | ЗАНЯТ | imp:test_model_lock; R:145; doc:4; gpuq:2/2026-10-01 | одноразовая приёмка/проба/holdout по имени и докстрингу |
| restore_probe_v1c.py | FROZEN | 2026-10-03 | 54 | ЗАНЯТ | doc:1; gpuq:1/2026-10-03 | одноразовая приёмка/проба/holdout по имени и докстрингу; вердикт: ## 2026-10-03 — RESTORE_ |
| routing_holdout_table.py | FROZEN | 2026-10-01 | 100 | ЗАНЯТ | imp:test_routing_holdout_diag2; art:1 | одноразовая приёмка/проба/holdout по имени и докстрингу |
| simple_probe.py | FROZEN | 2026-09-30 | 338 | ЗАНЯТ | imp:photo_probe; R:153; doc:3 | одноразовая приёмка/проба/holdout по имени и докстрингу |
| slot_control.py | FROZEN | 2026-10-01 | 123 | ЗАНЯТ | doc:1 | одноразовая приёмка/проба/holdout по имени и докстрингу |
| struct_report.py | FROZEN | 2026-10-01 | 326 | ЗАНЯТ | imp:test_struct_report; R:160; doc:3 | одноразовая приёмка/проба/holdout по имени и докстрингу |
| truth_codex.py | FROZEN | 2026-09-30 | 187 | ЗАНЯТ | doc:1 | одноразовая приёмка/проба/holdout по имени и докстрингу |
| truth_recheck.py | FROZEN | 2026-09-30 | 224 | ЗАНЯТ | - | одноразовая приёмка/проба/holdout по имени и докстрингу |
| truth_sheet.py | FROZEN | 2026-09-30 | 270 | ЗАНЯТ | imp:truth_codex,truth_recheck | одноразовая приёмка/проба/holdout по имени и докстрингу |
| unit_ref.py | FROZEN | 2026-10-03 | 308 | ЗАНЯТ | R:208; doc:1 | ОСТАНОВЛЕН 03.10 решением специалиста (докстринг, R-208) |
| unit_refit.py | FROZEN | 2026-10-03 | 683 | ЗАНЯТ | R:208; doc:1; gpuq:4/2026-10-03 | остановлен 03.10 (R-208: TPS-растяжка отклонена), хотя ставился в очередь 03.10 |
| w015_mag_fit.py | FROZEN | 2026-10-05 | 197 | ЗАНЯТ | art:2 | одноразовая приёмка/проба/holdout по имени и докстрингу |

### LEGACY

| файл | класс | изменён | строк | занят | ссылки | почему |
|---|---|---|---|---|---|---|
| base_pack.py | LEGACY | 2026-09-27 | 102 |  | imp:gen_base_anim,gen_base_bubbles,test_base_pack; R:104; doc:1 | есть ссылки (доки/импорт/очередь), но не в текущем конвейере и не ставился 7 дней |
| build_pack.py | LEGACY | 2026-09-20 | 593 |  | imp:ab_sdxl,check_floors,field_sweep…; R:005,006,019,039; doc:19 | есть ссылки (доки/импорт/очередь), но не в текущем конвейере и не ставился 7 дней |
| carpet_check.py | LEGACY | 2026-09-26 | 86 |  | R:039; doc:2 | есть ссылки (доки/импорт/очередь), но не в текущем конвейере и не ставился 7 дней |
| check_craft_lights.py | LEGACY | 2026-09-26 | 179 |  | R:043; doc:1 | есть ссылки (доки/импорт/очередь), но не в текущем конвейере и не ставился 7 дней |
| check_lora.py | LEGACY | 2026-09-22 | 92 |  | doc:2 | есть ссылки (доки/импорт/очередь), но не в текущем конвейере и не ставился 7 дней |
| check_triton.py | LEGACY | 2026-09-22 | 95 |  | - | есть ссылки (доки/импорт/очередь), но не в текущем конвейере и не ставился 7 дней |
| cut_gloves.py | LEGACY | 2026-09-17 | 61 |  | doc:1 | есть ссылки (доки/импорт/очередь), но не в текущем конвейере и не ставился 7 дней |
| dupe_frames.py | LEGACY | 2026-09-22 | 172 |  | R:049; doc:1 | есть ссылки (доки/импорт/очередь), но не в текущем конвейере и не ставился 7 дней |
| dupe_sets.py | LEGACY | 2026-09-22 | 149 |  | doc:1 | есть ссылки (доки/импорт/очередь), но не в текущем конвейере и не ставился 7 дней |
| facility_sheet.py | LEGACY | 2026-09-26 | 255 |  | imp:gen_base_anim | есть ссылки (доки/импорт/очередь), но не в текущем конвейере и не ставился 7 дней |
| family_review.py | LEGACY | 2026-09-29 | 209 | ЗАНЯТ | R:148; doc:1 | листы семейств v2 §6; упомянут в HD_PIPELINE_V2 без .py, никем не импортируется |
| fetch_fonts.py | LEGACY | 2026-10-03 | 495 |  | doc:8 | есть ссылки (доки/импорт/очередь), но не в текущем конвейере и не ставился 7 дней |
| fit_sheet.py | LEGACY | 2026-09-22 | 89 |  | R:050,089; doc:3 | лист приёмки G1-G3 (R-019, R-041) |
| footstep_census.py | LEGACY | 2026-09-26 | 22 |  | doc:1 | есть ссылки (доки/импорт/очередь), но не в текущем конвейере и не ставился 7 дней |
| fx_census.py | LEGACY | 2026-09-26 | 112 |  | doc:2 | есть ссылки (доки/импорт/очередь), но не в текущем конвейере и не ставился 7 дней |
| fx_map.py | LEGACY | 2026-09-27 | 113 |  | doc:1 | есть ссылки (доки/импорт/очередь), но не в текущем конвейере и не ставился 7 дней |
| gen_base_anim.py | LEGACY | 2026-09-27 | 871 |  | doc:4 | есть ссылки (доки/импорт/очередь), но не в текущем конвейере и не ставился 7 дней |
| gen_base_bubbles.py | LEGACY | 2026-09-27 | 211 |  | doc:4 | есть ссылки (доки/импорт/очередь), но не в текущем конвейере и не ставился 7 дней |
| gen_combat_fx.py | LEGACY | 2026-09-27 | 1082 |  | R:083,084; doc:9 | есть ссылки (доки/импорт/очередь), но не в текущем конвейере и не ставился 7 дней |
| gen_cursor.py | LEGACY | 2026-09-22 | 356 |  | imp:unpanel_batch; R:040,041,050,089; doc:5 | есть ссылки (доки/импорт/очередь), но не в текущем конвейере и не ставился 7 дней |
| gen_cursor_box.py | LEGACY | 2026-09-25 | 159 |  | doc:2 | есть ссылки (доки/импорт/очередь), но не в текущем конвейере и не ставился 7 дней |
| gen_fx.py | LEGACY | 2026-09-27 | 1365 |  | R:083; doc:10 | есть ссылки (доки/импорт/очередь), но не в текущем конвейере и не ставился 7 дней |
| gen_icons.py | LEGACY | 2026-10-01 | 548 |  | doc:2 | есть ссылки (доки/импорт/очередь), но не в текущем конвейере и не ставился 7 дней |
| gen_lora_batch.py | LEGACY | 2026-09-26 | 229 |  | imp:build,paint3; R:049,050,051,052; doc:14 | HD_PIPELINE_V2 §33: кандидат в attic; из него берёт MCD_DIRS triage/build.py |
| gen_path.py | LEGACY | 2026-09-26 | 467 |  | R:042; doc:4 | есть ссылки (доки/импорт/очередь), но не в текущем конвейере и не ставился 7 дней |
| gen_promo.py | LEGACY | 2026-09-25 | 276 |  | doc:2 | есть ссылки (доки/импорт/очередь), но не в текущем конвейере и не ставился 7 дней |
| ground_dump.py | LEGACY | 2026-09-26 | 76 |  | R:015; doc:2 | эталон разбора наборов для лаунчера (R-015) |
| hints_apply.py | LEGACY | 2026-09-22 | 92 |  | - | есть ссылки (доки/импорт/очередь), но не в текущем конвейере и не ставился 7 дней |
| link_frames.py | LEGACY | 2026-09-22 | 225 |  | imp:build,gen_lora_batch,prompt_writer; R:052; doc:1 | есть ссылки (доки/импорт/очередь), но не в текущем конвейере и не ставился 7 дней |
| make_ref.py | LEGACY | 2026-09-22 | 193 |  | doc:1 | есть ссылки (доки/импорт/очередь), но не в текущем конвейере и не ставился 7 дней |
| map_pick.py | LEGACY | 2026-09-30 | 503 | ЗАНЯТ | R:106,107; doc:4 | есть ссылки (доки/импорт/очередь), но не в текущем конвейере и не ставился 7 дней |
| map_queue.py | LEGACY | 2026-09-26 | 111 |  | doc:1 | есть ссылки (доки/импорт/очередь), но не в текущем конвейере и не ставился 7 дней |
| map_update.py | LEGACY | 2026-09-30 | 437 | ЗАНЯТ | imp:map_pick,sweep_sheet,test_map_update; doc:2; art:4 | LEGACY_DIRECT_WRITER (докстринг, P1-B): пишет мимо манифеста |
| merge_gens.py | LEGACY | 2026-09-30 | 192 | ЗАНЯТ | R:076,088; doc:9 | есть ссылки (доки/импорт/очередь), но не в текущем конвейере и не ставился 7 дней |
| mirror_frames.py | LEGACY | 2026-09-23 | 224 |  | imp:gen_lora_batch,mirror_sheet; R:051,054; doc:7 | есть ссылки (доки/импорт/очередь), но не в текущем конвейере и не ставился 7 дней |
| mirror_sheet.py | LEGACY | 2026-09-23 | 115 |  | R:054; doc:2 | лист зеркальных пар (R-054) |
| pedia_flatbg.py | LEGACY | 2026-09-26 | 107 |  | doc:4 | есть ссылки (доки/импорт/очередь), но не в текущем конвейере и не ставился 7 дней |
| pedia_review.py | LEGACY | 2026-09-26 | 163 |  | doc:8 | есть ссылки (доки/импорт/очередь), но не в текущем конвейере и не ставился 7 дней |
| pedia_text.py | LEGACY | 2026-09-26 | 253 |  | doc:5 | есть ссылки (доки/импорт/очередь), но не в текущем конвейере и не ставился 7 дней |
| pilot_report.py | LEGACY | 2026-09-30 | 311 | ЗАНЯТ | imp:test_detail_class; doc:1 | есть ссылки (доки/импорт/очередь), но не в текущем конвейере и не ставился 7 дней |
| placeholder_sheet.py | LEGACY | 2026-09-15 | 50 |  | doc:1 | есть ссылки (доки/импорт/очередь), но не в текущем конвейере и не ставился 7 дней |
| restore_pedia.py | LEGACY | 2026-09-16 | 113 |  | doc:1 | восстановление 8-бит педии из HD (сентябрь) |
| review_floors.py | LEGACY | 2026-09-26 | 708 |  | doc:11 | приёмка полов для портала (docs/portal/PACK_REVIEW.md), импортирует build_pack |
| tank_turret.py | LEGACY | 2026-10-02 | 787 |  | R:175; doc:4 | есть ссылки (доки/импорт/очередь), но не в текущем конвейере и не ставился 7 дней |
| tracer_preview.py | LEGACY | 2026-09-27 | 246 |  | R:043; doc:1 | есть ссылки (доки/импорт/очередь), но не в текущем конвейере и не ставился 7 дней |
| triage/build.py | LEGACY | 2026-09-26 | 247 |  | - | сборка страницы триажа (attic/README: импортирует gen_lora_batch) |
| triage/caption.py | LEGACY | 2026-09-24 | 114 |  | R:064; doc:1 | есть ссылки (доки/импорт/очередь), но не в текущем конвейере и не ставился 7 дней |
| triage/server.py | LEGACY | 2026-09-24 | 200 |  | - | страница триажа, запускается triage/start.cmd |
| unpanel_batch.py | LEGACY | 2026-09-22 | 75 |  | R:050,062,089; doc:6 | есть ссылки (доки/импорт/очередь), но не в текущем конвейере и не ставился 7 дней |
| upscale_ui.py | LEGACY | 2026-09-16 | 202 |  | doc:5 | есть ссылки (доки/импорт/очередь), но не в текущем конвейере и не ставился 7 дней |
| weapon_classes.py | LEGACY | 2026-09-26 | 318 |  | imp:fx_map | есть ссылки (доки/импорт/очередь), но не в текущем конвейере и не ставился 7 дней |

### SUPERSEDED / ORPHAN / ATTIC

| файл | класс | изменён | строк | занят | ссылки | почему |
|---|---|---|---|---|---|---|
| attic/ab_sdxl.py | ATTIC | 2026-09-26 | 163 |  | doc:4 | в attic/ |
| attic/ab_sheet.py | ATTIC | 2026-09-26 | 133 |  | R:066,088; doc:7; art:1 | в attic/ |
| attic/check_floors.py | ATTIC | 2026-09-26 | 183 |  | doc:1 | в attic/ |
| attic/field_sweep.py | ATTIC | 2026-09-26 | 233 |  | doc:1 | в attic/ |
| attic/gen_tile.py | ATTIC | 2026-09-26 | 604 |  | R:049,050,051; doc:8 | в attic/ |
| attic/keep_batch.py | ATTIC | 2026-09-26 | 119 |  | doc:1 | в attic/ |
| attic/merge_best.py | ATTIC | 2026-09-26 | 153 |  | R:061,076,088; doc:6 | в attic/ |
| attic/paint3.py | ATTIC | 2026-09-26 | 526 |  | imp:ab_sdxl; R:062,063,066,067; doc:14; art:1 | в attic/ |
| attic/pick_old_grey.py | ATTIC | 2026-09-26 | 137 |  | doc:3 | в attic/ |
| attic/prompt_writer.py | ATTIC | 2026-09-26 | 640 |  | imp:ab_sdxl,paint3; doc:7 | в attic/ |
| attic/repack_all.py | ATTIC | 2026-09-26 | 75 |  | doc:2 | в attic/ |
| attic/run_batch.py | ATTIC | 2026-09-26 | 197 |  | R:018,049,051; doc:5 | в attic/ |
| dupe_view.py | ORPHAN | 2026-09-22 | 109 |  | - | ни ссылок, ни запусков |
| floor_sheets.py | ORPHAN | 2026-09-22 | 133 |  | - | ни ссылок, ни запусков |
| item_geometry.py | ORPHAN | 2026-10-03 | 400 |  | doc:1; art:1 | новый (03.10) замер геометрии HD-BIGOBS по контракту v4; никем не импортируется, не ставил |
| list_ground_sets.py | ORPHAN | 2026-09-26 | 168 |  | - | ни ссылок, ни запусков |
| map_hint_sheet.py | ORPHAN | 2026-09-26 | 162 |  | - | ни ссылок, ни запусков |
| orig_sheet.py | ORPHAN | 2026-09-23 | 87 |  | - | ни ссылок, ни запусков |
| pedia_compare.py | ORPHAN | 2026-09-26 | 395 |  | - | ни ссылок, ни запусков |
| pedia_pick.py | ORPHAN | 2026-09-26 | 321 |  | - | ни ссылок, ни запусков |
| sweep_sheet.py | ORPHAN | 2026-09-26 | 77 |  | - | ни ссылок, ни запусков |
| derive_recolor_acceptance_v2_report_fix.py | SUPERSEDED | 2026-10-03 | 76 | ЗАНЯТ | doc:1 | есть derive_recolor_acceptance_v31, derive_recolor_acceptance_v32; никем не импортируется |
| weapons_probe4.py | SUPERSEDED | 2026-10-04 | 123 | ЗАНЯТ | gpuq:1/2026-10-04 | есть weapons_probe5; никем не импортируется |

### Прочие файлы tools/hdart

| файл | заметка |
|---|---|
| attic/README.md | ATTIC |
| attic/run_detached.cmd | ATTIC: запуск run_batch отдельно |
| triage/index.html | LEGACY: страница триажа |
| triage/start.cmd | LEGACY: запускает triage/server.py |
| README.md | документация |
| README_photo.md | документация PHOTO |
| README_tank.md | документация башни танка |
| base_anims.yml | данные gen_base_anim |
| gen_all.ps1 | ACTIVE-ish: в gpu_scripts.txt, защита R-015 (Select-ModSource); обёртка над extract_pck/gen_hd/build_pack (G1) |
| intro_files.txt | список файлов вступления |
| pedia_mismatch.csv | отчёт pedia_compare |
| pedia_mismatch.md | отчёт pedia_compare |
| pedia_names.txt | данные педии |
| rejected_files.txt | список отклонённых |
| review_page.html | страница review_server (не в гите) |
| setup_gen.ps1 | окружение .venv (SDXL) |
| setup_photo.ps1 | окружение photo |
| setup_qwen21.ps1 | окружение .venv-qwen21 (текущее) |
| setup_train.ps1 | окружение обучения (E:/train) |
| tank_masks.json | данные tank_turret (R-175) |
| train_lora.ps1 | LEGACY: обучение LoRA (HD_PIPELINE_V2 §34 - заморожено), в gpu_scripts.txt |

## 3. Дыра gpu-guard

Как матчит хук (`.claude/hooks/gpu-guard.ps1`): список — `tools/gpu_scripts.txt` (basename); запуск = первый `.py/.ps1/.sh` после интерпретатора (python/py/accelerate/powershell/pwsh/sh/bash) **или** скрипт из списка первым словом команды; команда делится по `&&`/`||`/`;`/`|` вне кавычек; пропуск при `gpuq.py`, `GPUQ_BYPASS=1`, `--help/-h/--dry-run/-DryRun`. Путь не важен, только basename.

Прямой импорт torch/diffusers/diffsynth/transformers/safetensors/ollama или вызов `from_pretrained`/`load_lora_weights`/Ollama 11434 без записи в списке:

| файл | что | дыра? |
|---|---|---|
| tools/hdart/check_lora.py | safetensors  | слабая: только читает safetensors LoRA на CPU, модель не грузит |
| tools/hdart/vx_control.py | diffusers, safetensors, torch, transformers from_pretrained( | нет: библиотека без __main__, исключение оговорено в шапке gpu_scripts.txt (вызывает obj_photo) |

**Настоящая дыра — запускатели без модели, которые поднимают модельный скрипт сами:**

| файл | что делает | следствие |
|---|---|---|
| tools/hdart/render_chunks.py | `subprocess.Popen(cmd + ['--max-renders', N])` — крутит кусками любой рендер (строка 131); в очередь ставился 29 раз, последний 05.10 | `py tools/hdart/render_chunks.py -- python photo_render.py ...` напрямую хук **пропустит**: первый скрипт после интерпретатора — render_chunks.py, его в списке нет (правило «первый скрипт» из шапки хука). Дописать `render_chunks.py` в gpu_scripts.txt |
| tools/hdart/agent_pose.py | `subprocess.run([sys.executable, agent_full.py, 'build', ...])` (строка 440); сам в очереди (#407 done, #409 queued) под .venv-qwen21 | в gpu_scripts.txt нет; `agent_full.py` есть. Прямой `py agent_pose.py render` хук пропустит, а render грузит Edit-2511 через unit_parts.Inpainter. Дописать |
| tools/hdart/weapon_judge.py, visual_judge.py, identity_auto.py, weapons_chatgpt.py | `codex exec` (облако), по докстрингу «без видеокарты» | не дыра, но в очередь их ставят ради сериализации — решить, нужен ли им список (тогда gpuq будет ждать их как «мимо очереди») |

В списке есть, а в `tools/**` файла нет: run2.py, sweep.sh, run_pilot.sh, run18.sh, run_ab_refine.sh, train.py, run_series.sh, run_series2.sh, run_series3.sh — это sh-скрипты прогонов в `art/maps/paint/` (R-080) и `E:/train/train.py`; не ошибка, но `tools/test_gpu_scripts.py` их не проверит.

## 4. R-001 (кириллица без спецификации)

Проверка по AST: `open(..., 'w'/'a')` и `write_text` с `encoding='utf-8'` или без encoding, в модулях, где есть строковые литералы с кириллицей. Исключены: `ENC`/`ir.ENC`/`rp.ENC` (= 'utf-8-sig' в identity_routing/restore_probe_v1, проверено), `ENC if new else 'utf-8'` (дописывание в существующий файл — верно), `.pal.txt`/`settings.txt`/`.key`/`layout.json` (читает игра или конвейер, без кириллицы, спецификация вредна).

Модулей с нарушением: **44**, из них с рискованным расширением (md/tsv/txt/csv/log — то, что читают PowerShell и `type`): **12**. HTML/JSON/JSONL для браузера и своих читалок — ниже риск, но формально тоже R-001.

| файл | строки (encoding → что пишет) |
|---|---|
| identity_auto.py | 142: utf-8 → .md; 290: utf-8 → .md; 413: utf-8 → .md; 153: utf-8 → .md; 215: utf-8 → .log |
| visual_judge.py | 209: utf-8 → .md; 334: utf-8 → .log; 478: utf-8 → .md; 220: utf-8 → .md |
| tank_turret.py | 732: utf-8 → .txt |
| build_dataset.py | 514: utf-8 → .csv; 419: utf-8 → .txt |
| weapon_judge.py | 176: utf-8 → .txt |
| agent_full.py | 584: utf-8 → .txt; 586: utf-8 → .txt |
| agent_pose.py | 493: utf-8 → .txt; 495: utf-8 → .txt |
| attic/keep_batch.py | 86: utf-8 → .log |
| base_pack.py | 93: utf-8 → .txt |
| fx_map.py | 104: utf-8 → .txt |
| gen_fx.py | 1197: utf-8 → .txt |
| score_batch.py | 245: utf-8 → .csv |

Остальные (html/json/jsonl/прочее): gen_hd.py, relation_holdout_v7.py, axis_a_clean_v5.py, derive_recolor_v33_rdiag.py, detail_class.py, detail_probe.py, gen_combat_fx.py, hd_e2e_v1_identity.py, hd_e2e_v1_review.py, hints_apply.py, identity_card.py, identity_routing.py, link_frames.py, photo_accept.py, photo_decomp.py, photo_struct.py, pilot_batch.py, pilot_report.py, relation_holdout_v4.py, relation_holdout_v4_axis_zip.py, relation_holdout_v5.py, render_chunks.py, review_floors.py, routing_holdout.py, routing_holdout_v5.py, routing_holdout_v7.py, routing_holdout_v8.py, simple_probe.py, struct_probe.py, struct_report.py, truth_codex.py, weapons_chatgpt.py.

## 5. Дубли функций (одно имя в 3+ модулях, верхний уровень)

Всего имён: **196**. Побайтно одинаковое тело во всех копиях: 4 (at x3, osha x3, rate x6, code_changed x4). Шаблон приёмки, размноженный копированием файла (разные тела, одна роль): p, do_check, do_lockref, do_report, write_md, freeze, spec_body, do_spec, load_spec, do_cards, do_relations, do_select — по 10–34 копии каждая в acceptance/holdout/derive_recolor/hd_e2e.

| функция | модулей | разных тел | где |
|---|---|---|---|
| write_md | 34 | 32 | ar_boundary_validation, assembly_evidence_v2_prep, derive_recolor_base_acceptance_v1, derive_recolor_base_acceptance_v11, derive_recolor_saf… |
| do_report | 30 | 30 | ar_boundary_validation, assembly_evidence_v2_prep, derive_recolor_acceptance_v2, derive_recolor_acceptance_v3, derive_recolor_acceptance_v31… |
| load | 27 | 15 | acceptance_plan, build_hd_pack, derive_recolor_acceptance_v32, derive_recolor_base_acceptance_v1, derive_recolor_base_acceptance_v11, derive… |
| do_check | 27 | 25 | ar_boundary_validation, assembly_evidence_v2_prep, derive_recolor_acceptance_v2, derive_recolor_acceptance_v3, derive_recolor_acceptance_v31… |
| sheet | 25 | 25 | agent_pose, craft_outline, detail_class, detail_probe, fetch_fonts, gen_icons, gen_promo, item_geometry, item_photo, map_paint, map_update, … |
| p | 25 | 4 | ar_boundary_validation, assembly_evidence_v2_prep, hd_e2e_v1, hd_e2e_v1_identity, hd_e2e_v1_r2, hd_e2e_v1_r3, hd_e2e_v1_r32, hd_e2e_v1_r33, … |
| read_tsv | 18 | 10 | carpet_check, identity_auto, identity_card, identity_holdout, identity_routing, item_asset_check, map_queue, obj_generation, photo_struct, p… |
| do_spec | 17 | 17 | assembly_evidence_v2_prep, derive_recolor_acceptance_v2, derive_recolor_acceptance_v3, derive_recolor_acceptance_v31, derive_recolor_accepta… |
| load_spec | 17 | 17 | assembly_evidence_v2_prep, derive_recolor_acceptance_v2, derive_recolor_acceptance_v3, derive_recolor_acceptance_v31, derive_recolor_accepta… |
| build | 16 | 16 | axis_a_clean_v5, family_relation_v2, gen_fx, hd_e2e_v1, hd_manifest, link_frames, mcd_state, relation_holdout_v4_axis_zip, relation_holdout_… |
| spec_body | 15 | 15 | assembly_evidence_v2_prep, derive_recolor_acceptance_v2, derive_recolor_acceptance_v3, derive_recolor_acceptance_v31, derive_recolor_accepta… |
| dump | 15 | 10 | derive_recolor_acceptance_v32, derive_recolor_base_acceptance_v1, derive_recolor_base_acceptance_v11, derive_recolor_safe_acceptance_v1, det… |
| order | 14 | 9 | ar_boundary_validation, assembly_discovery_v1, derive_recolor_safe_acceptance_v1, hd_e2e_v1_review, identity_holdout, relation_holdout_v4, r… |
| do_cards | 14 | 14 | derive_recolor_acceptance_v2, derive_recolor_acceptance_v3, derive_recolor_acceptance_v31, derive_recolor_base_acceptance_v1, derive_recolor… |
| select | 13 | 12 | derive_recolor_safe_acceptance_v1, gen_base_anim, identity_holdout, photo_accept, photo_struct, pilot_batch, relation_holdout_v4, relation_h… |
| report | 12 | 12 | acceptance_report, arbiter, arbiter_v2, build_hd_pack, identity_card, identity_routing, photo_accept, photo_decomp, photo_struct, review_flo… |
| font | 12 | 11 | build_dataset, dupe_view, family_review, fit_sheet, gen_lora_test, mirror_sheet, orig_sheet, review_floors, tank_turret, unit_pilot, weapon_… |
| run | 11 | 11 | acceptance_run, arbiter, arbiter_v2, build_dataset, derive_recolor_v33_rdiag, detail_class, families_recolor_diff, pedia_batch, repro_smoke,… |
| freeze | 11 | 11 | arbiter, identity_holdout, pilot_batch, relation_holdout_v4, relation_holdout_v5, relation_holdout_v7, routing_holdout, routing_holdout_v5, … |
| do_select | 11 | 11 | prod_two_pass_v1, prod_two_pass_v2, relation_holdout_v4, relation_holdout_v5, relation_holdout_v7, relation_taxonomy, restore_batch_v1, rout… |
| sha256_file | 10 | 6 | acceptance_run, arbiter, build_hd_pack, item_photo, model_lock, photo_accept, photo_render, pilot_batch, render_chunks, struct_probe |
| discover | 10 | 9 | aligned_recolor_v1, aligned_recolor_v2, assembly_discovery_v1, assembly_group_v1, assembly_repeated_v1, relation_discovery_v2, relation_disc… |
| do_lockref | 10 | 6 | ar_boundary_validation, relation_holdout_v4, relation_holdout_v4_ref, relation_holdout_v5, relation_holdout_v7, routing_holdout, routing_hol… |
| compose | 10 | 10 | derive_recolor_v33_dev, gen_reticle, gen_reticle_v2, obj_review, obj_series, photo_ui, prompt_writer, tank_turret, unit_pilot, visual_judge |
| do_relations | 10 | 9 | hd_e2e_v1, prod_two_pass_v1, relation_holdout_v4, relation_holdout_v5, relation_holdout_v7, restore_batch_v1, routing_holdout, routing_holdo… |
| rel | 9 | 3 | acceptance_report, derive_recolor_acceptance_v2, derive_recolor_acceptance_v3, derive_recolor_acceptance_v31, derive_recolor_acceptance_v32,… |
| render | 9 | 9 | craft_outline, derive_recolor_acceptance_v2, gen_base_anim, gen_base_bubbles, gen_cursor_box, gen_icons, gen_path, gen_reticle, map_mockup |
| fsha | 9 | 3 | derive_recolor_acceptance_v2, derive_recolor_acceptance_v32, derive_recolor_base_acceptance_v1, derive_recolor_base_acceptance_v11, derive_r… |
| on_floor | 9 | 8 | gen_reticle, long_object, map_pick, mirror_sheet, obj_series, oldauto_ab_v1, probe_object, review_floors, strict_ctl_v1 |
| load_json | 8 | 6 | acceptance_report, arbiter, derive_recolor_acceptance_v2, derive_recolor_acceptance_v3, identity_routing, map_pick, prompt_writer, server |
| do_pack | 8 | 7 | ar_boundary_validation, hd_e2e_v1_review, identity_auto, relation_holdout_v4, relation_holdout_v5, relation_holdout_v7, relation_taxonomy, v… |
| label | 8 | 8 | arbiter, gen_base_anim, gen_hd, map_mockup, photo_base, probe_floor, tile_forge, tile_qa |
| classify | 8 | 8 | detail_class, family_relation_v2, gen_base_anim, pedia_batch, relation_holdout_v5, relation_holdout_v7, restore_batch_v1, weapon_classes |
| page | 8 | 8 | detail_class, detail_probe, photo_accept, photo_decomp, photo_struct, pilot_batch, simple_probe, struct_report |
| blur | 8 | 8 | gen_base_anim, gen_fx, oldauto_ab_v1, paint3, sprite_scale, unit_parts, unit_ref, weapon_fit |
| summary | 8 | 8 | hd_e2e_v1_r32, hd_manifest, map_pick, pedia_compare, pedia_pick, pilot_report, simple_probe, v5_freeze_readiness |
| do_freeze | 7 | 6 | ar_boundary_validation, hd_e2e_v1_r32, prod_two_pass_v1, relation_discovery_v5, restore_batch_v1, v5_ar2_recount, v5_component_validation |
| f3 | 7 | 3 | ar_boundary_validation, relation_discovery_v4, relation_discovery_v5, relation_holdout_v4, v5_ar2_recount, v5_component_validation, v5_freez… |
| fit | 7 | 7 | arbiter, identity_card, item_geometry, photo_base, truth_sheet, w015_mag_fit, weapon_ammo_cards |
| sample | 7 | 7 | assembly_group_v1, assembly_repeated_v1, fire_real_pack, two_component_v1, unit_refit, weapon_fit, weapon_part_fit |

По именам из ТЗ: `read_pck`/`load_palette`/`to_rgba`/`luma`/`cut_out`/`matte` в 3+ модулях не определены (живут в `xcom_sprites`, `tile_forge`, `photo_base`, `obj_photo` и импортируются) — дублирование идёт не по графике, а по **каркасу приёмок** (`do_spec/load_spec/spec_body/do_check/do_report/write_md/do_cards/freeze/do_lockref`): каждая новая приёмка — копия предыдущего файла.

## 6. Размер

Самые большие модули (строк): gen_hd.py 1908, gen_fx.py 1365, weapon_fit.py 1301, weapon_parts.py 1300, map_paint.py 1287, unit_turnaround.py 1151, hd_e2e_v1_r3.py 1141, relation_holdout_v5.py 1121, relation_holdout_v7.py 1105, relation_holdout_v4.py 1103.

Самые длинные функции (строк): gen_hd.py:main 301, map_paint.py:run_regions 297, obj_families.py:main 273, build_pack.py:main 270, obj_photo.py:main 267, obj_series.py:main 227, hd_e2e_v1.py:do_plan 225, floor_group.py:main 214, photo_ui.py:main 198, craft_outline.py:main 196.

## 7. Семейства версий

Семейств по шаблону `_vN`/`N`/`_prep`/`_fix`/`_report`: **15**, файлов в них: **57**.

| семейство | файлов | члены | последняя версия |
|---|---|---|---|
| acceptance | 2 | acceptance_report, acceptance_run | acceptance_run |
| aligned_recolor | 2 | aligned_recolor_v1, aligned_recolor_v2 | aligned_recolor_v2 |
| arbiter | 2 | arbiter, arbiter_v2 | arbiter_v2 |
| derive_recolor | 5 | derive_recolor_v3, derive_recolor_v31, derive_recolor_v32, derive_recolor_v33_dev, derive_recolor_v33_rdiag | derive_recolor_v33_rdiag |
| derive_recolor_acceptance | 5 | derive_recolor_acceptance_v2, derive_recolor_acceptance_v2_report_fix, derive_recolor_acceptance_v3, derive_recolor_acceptance_v31, derive_recolor_acceptance_v32 | derive_recolor_acceptance_v32 |
| derive_recolor_base_acceptance | 2 | derive_recolor_base_acceptance_v1, derive_recolor_base_acceptance_v11 | derive_recolor_base_acceptance_v11 |
| gen_reticle | 2 | gen_reticle, gen_reticle_v2 | gen_reticle_v2 |
| hd_e2e | 9 | hd_e2e_v1, hd_e2e_v1_identity, hd_e2e_v1_r2, hd_e2e_v1_r3, hd_e2e_v1_r31, hd_e2e_v1_r32, hd_e2e_v1_r33, hd_e2e_v1_review, hd_e2e_v1_run | hd_e2e_v1_run |
| prod_two_pass | 2 | prod_two_pass_v1, prod_two_pass_v2 | prod_two_pass_v2 |
| relation_discovery | 4 | relation_discovery_v2, relation_discovery_v3, relation_discovery_v4, relation_discovery_v5 | relation_discovery_v5 |
| relation_holdout | 5 | relation_holdout_v4, relation_holdout_v4_axis_zip, relation_holdout_v4_ref, relation_holdout_v5, relation_holdout_v7 | relation_holdout_v7 |
| restore_probe | 3 | restore_probe_v1, restore_probe_v1b, restore_probe_v1c | restore_probe_v1c |
| routing_holdout | 7 | routing_holdout, routing_holdout_diag, routing_holdout_diag2, routing_holdout_table, routing_holdout_v5, routing_holdout_v7, routing_holdout_v8 | routing_holdout_v8 |
| routing_rules | 4 | routing_rules, routing_rules_v5, routing_rules_v6, routing_rules_v7 | routing_rules_v7 |
| weapons_probe | 3 | weapons_probe3, weapons_probe4, weapons_probe5 | weapons_probe5 |

Не по шаблону, но по смыслу семейства: restore: restore_probe_v1, restore_probe_v1b, restore_probe_v1c, restore_batch_v1; gen_fire: gen_fire, gen_fire_real; gen_cursor: gen_cursor, gen_cursor_box; photo_render: photo_render, photo_struct_render; weapons_probe: weapons_probe3, weapons_probe4, weapons_probe5; unit_pilot: unit_pilot, unit_direct, unit_parts, unit_ref, unit_refit, unit_turnaround.

Где `vN` не superseded формально, но по DECISIONS закрыт: derive_recolor_acceptance_v2 (FAIL 03.10) → v3 (FAIL) → v31 (FAIL по H5) → v32 (FAIL) → v33_dev (FAIL_NO_CANDIDATE); derive_recolor_base_acceptance_v1 (FAIL навсегда) → v11 (NOT YET VERIFIED); routing_rules_v5 → v6 → v7 (заморожен) → routing_model_v8; relation_discovery_v2 → v5; relation_holdout_v4 → v5 → v7 (VERIFIED 03.10, цикл закрыт). Формально SUPERSEDED только 2, потому что каждая vN+1 импортирует vN (а hd_e2e_v1 импортирует почти всех).

## Предложение структуры

Физически ничего не переносить до слова Vitali — HD_PIPELINE_V2 §30 прямо требует сначала `tools/hdart/SCRIPT_STATUS.json` (CURRENT/EXPERIMENTAL/LEGACY/SPECIALIZED), а каталоги двигать «только после того как v2 запускается end-to-end». Файла SCRIPT_STATUS.json на диске нет — `hdart_classes.tsv` этого аудита может стать его черновиком.

1. **`tools/hdart/attic/`** (по образцу уже сделанного 26.09) — LEGACY G1–G3 без импортёров вне attic и не специализированные: carpet_check, check_lora, check_triton, cut_gloves, dupe_frames, dupe_sets, fit_sheet, footstep_census, ground_dump, hints_apply, make_ref, map_queue, mirror_sheet, placeholder_sheet, restore_pedia, review_floors, unpanel_batch; папка `triage/` (build, caption, server + index.html, start.cmd) — целиком как `attic/triage/`. Плюс по HD_PIPELINE_V2 §33 — gen_lora_batch, gen_lora_test, merge_gens (и gen_hd, но его импортируют floor_group/map_paint/…: 19 импортёров — нельзя без правки sys.path).
   Специализированные генераторы (SPECIALIZED по §31: base_pack, check_craft_lights, fetch_fonts, fx_census, fx_map, gen_base_anim, gen_base_bubbles, gen_combat_fx, gen_cursor, gen_cursor_box, gen_fx, gen_icons, gen_path, gen_promo, pedia_flatbg, pedia_review, pedia_text, tank_turret, tracer_preview, upscale_ui) формально LEGACY — не запускались неделю, — но их зовут при смене арта (огонь, прицелы, база, иконки, курсор, педия, башня танка); оставить на месте.
2. **`tools/hdart/frozen/<серия>/`** (новая папка, скрипты одноразовых приёмок с записанным вердиктом): derive_recolor_* (14 файлов), hd_e2e_v1_* (9), relation_*/routing_*/assembly_*/aligned_recolor_*/v5_*/ar_boundary_validation/two_component_v1/post_review_safety/axis_a_clean_v5 (≈35), acceptance_*/pilot_*/photo_probe/simple_probe/detail_probe/slot_control/photo_struct/oldauto_ab_v1/truth_*, restore_probe_v1*/weapons_probe3-5/unit_ref/unit_refit, w015_mag_fit. **Но**: 61 из них ACTIVE-LIB через `prod_two_pass_v1 → restore_batch_v1 / hd_e2e_v1_run → hd_e2e_v1` и через `identity_routing` (46 импортёров) — переносить можно только вместе с `sys.path.insert` в hd_e2e_v1/hd_e2e_v1_run/restore_batch_v1 или после того, как `sprite_frame` и чтение замороженных детекторов V7 переедут в общую библиотеку.
3. **Оставить на месте**: ядро v2 (obj_*, photo_*, struct_guide, asset_fidelity, model_lock, build_hd_pack, hd_manifest, render_chunks, weapon_*, unit_parts/unit_turnaround/unit_direct, agent_*), специализированные генераторы (gen_fire_real, fire_real_pack, gen_craft_lights, gen_reticle*, gen_base_*, gen_icons, gen_path, gen_cursor*, gen_combat_fx, gen_fx, craft_outline, tank_turret, pedia_*, upscale_*), библиотеки (xcom_sprites, tile_forge, score_batch, build_dataset, dupe_plan, hints, common, sprite_scale, extract_pck, map_mockup, battle_view).

**Перенос ломает ссылки** (записи, где путь `tools/hdart/X.py` стоит в `Файлы:` или тексте):

- RAKES: R-005 → build_pack; R-006 → build_pack; R-015 → ground_dump; R-019 → build_pack; R-039 → build_pack, carpet_check; R-040 → gen_cursor; R-041 → gen_cursor; R-042 → gen_path; R-043 → check_craft_lights, tracer_preview; R-049 → dupe_frames, gen_lora_batch; R-050 → fit_sheet, gen_cursor, gen_lora_batch, unpanel_batch; R-051 → gen_lora_batch, mirror_frames; R-052 → gen_lora_batch, link_frames; R-054 → gen_lora_batch, mirror_frames, mirror_sheet; R-061 → gen_lora_batch; R-062 → gen_lora_batch, unpanel_batch; R-064 → caption; R-076 → merge_gens; R-083 → gen_combat_fx, gen_fx; R-084 → gen_combat_fx; R-087 → build_pack; R-088 → gen_lora_batch, merge_gens; R-089 → fit_sheet, gen_cursor, gen_lora_batch, unpanel_batch; R-104 → base_pack; R-106 → map_pick; R-107 → map_pick; R-145 → repro_smoke; R-148 → family_review; R-153 → photo_probe, simple_probe; R-160 → photo_decomp, struct_report; R-175 → tank_turret; R-208 → unit_ref, unit_refit.
- DECISIONS (дата записи → модули): 2026-09-18 → build_pack; 2026-09-21 → build_pack, fetch_fonts; 2026-09-29 → map_pick, map_update, merge_gens; 2026-09-30 → arbiter, detail_probe, photo_probe, pilot_report, repro_smoke, simple_probe; 2026-10-01 → family_review, identity_holdout, photo_decomp, photo_struct, slot_control, struct_report; 2026-10-03 → derive_recolor_acceptance_v2_report_fix, derive_recolor_base_acceptance_v11, derive_recolor_v33_rdiag, hd_e2e_v1_r32, oldauto_ab_v1, restore_probe_v1c.
- GENERATORS.md описывает по разделам: gen_hd, attic/gen_tile, gen_fire, tile_forge, build_pack, optimize_hd, map_paint, gen_combat_fx, gen_fx, gen_cursor, gen_cursor_box, gen_path, gen_reticle, gen_craft_lights, gen_base_anim, gen_base_bubbles, gen_icons, gen_promo, pedia_batch, pedia_ab, merge_gens — при переносе править пути в заголовках разделов; attic/README.md перечисляет, что осталось в корне и почему.
- art/**: derive_recolor_base_acceptance_v11 (1), map_update (4), routing_holdout_table (1), w015_mag_fit (2) — сводки и spec.json приёмок называют скрипт по пути.

## Безопасно применить сейчас

Только файлы, которых нет в protected_status.txt, без импортёров, без упоминаний `.py` в доках/граблях/art, никогда не ставились в очередь и не в gpu_scripts.txt (перенос в attic/ — после `git mv`, с проверкой `--help`):

- `tools/hdart/dupe_view.py` — ORPHAN, 109 строк, изменён 2026-09-22, в гите; ни ссылок, ни запусков
- `tools/hdart/floor_sheets.py` — ORPHAN, 133 строк, изменён 2026-09-22, в гите; ни ссылок, ни запусков
- `tools/hdart/list_ground_sets.py` — ORPHAN, 168 строк, изменён 2026-09-26, в гите; ни ссылок, ни запусков
- `tools/hdart/map_hint_sheet.py` — ORPHAN, 162 строк, изменён 2026-09-26, в гите; ни ссылок, ни запусков
- `tools/hdart/orig_sheet.py` — ORPHAN, 87 строк, изменён 2026-09-23, в гите; ни ссылок, ни запусков
- `tools/hdart/pedia_compare.py` — ORPHAN, 395 строк, изменён 2026-09-26, в гите; ни ссылок, ни запусков
- `tools/hdart/pedia_pick.py` — ORPHAN, 321 строк, изменён 2026-09-26, в гите; ни ссылок, ни запусков
- `tools/hdart/sweep_sheet.py` — ORPHAN, 77 строк, изменён 2026-09-26, в гите; ни ссылок, ни запусков
- `tools/hdart/hints_apply.py` — LEGACY, 92 строк, изменён 2026-09-22, в гите; есть ссылки (доки/импорт/очередь), но не в текущем конвейере и не ставился 7 дне

Те же условия, но есть упоминание в доках/граблях (перенос — с правкой ссылки): carpet_check (R:039), check_craft_lights (R:043), check_lora (doc:2), cut_gloves (doc:1), dupe_frames (R:049), dupe_sets (doc:1), fit_sheet (R:050,089), footstep_census (doc:1), fx_census (doc:2), fx_map (doc:1), gen_base_anim (doc:4), gen_base_bubbles (doc:4), gen_combat_fx (R:083,084), gen_cursor_box (doc:2), gen_fx (R:083), gen_path (R:042), ground_dump (R:015), map_queue (doc:1), mirror_sheet (R:054), pedia_flatbg (doc:4), pedia_review (doc:8), pedia_text (doc:5), placeholder_sheet (doc:1), restore_pedia (doc:1), review_floors (doc:11), tracer_preview (R:043), unpanel_batch (R:050,062,089).

Без переноса, сразу: дописать `render_chunks.py` и `agent_pose.py` в `tools/gpu_scripts.txt` (файл занят другой сессией — `M tools/gpu_scripts.txt`, значит через неё).

## Требует решения Vitali

1. **148 файлов tools/hdart не в гите** (`??`), в том числе весь relation/routing/derive_recolor/hd_e2e стек, photo_base/photo_accept/photo_render, weapon_*, unit_*, prod_two_pass_v1/v2, restore_batch_v1 — то, на чём сегодня идёт производство. Коммитить, как есть, или сначала раскладывать по папкам (тогда переносить дешевле всего именно сейчас, пока ссылок в гите нет).
2. **`prod_two_pass_v1 → restore_batch_v1 / hd_e2e_v1_run → hd_e2e_v1 → весь стек holdout'ов и derive_recolor`** ради `sprite_frame` (hd_e2e_v1_run), чтения замороженных детекторов V7 (`E.Discovery`, `E.build` в restore_batch_v1:329) и шага derive (hd_e2e_v1_run:189–191). Вынести `sprite_frame` в общую библиотеку (map_mockup/xcom_sprites) и завернуть чтение V7 в один тонкий модуль — тогда 61 «замороженных» модулей перестанут быть ACTIVE-LIB и их можно морозить физически.
3. **Папка `frozen/`** — заводить ли (HD_PIPELINE_V2 §30 говорит о SCRIPT_STATUS.json, а не о папке) и считать ли `hdart_classes.tsv` её черновиком.
4. **gen_hd.py (1908 строк, 19 импортёров, 103 упоминания в доках)** — HD_PIPELINE_V2 §33 называет его LEGACY-кандидатом в attic, но floor_group/map_paint/ground_relief импортируют его напрямую; перенос — только с shim-модулем.
5. **Каркас приёмок копируется файлом** (do_spec/load_spec/spec_body/do_check/do_report/write_md — по 15–34 копии). Выделить `acceptance_kit.py` до следующей приёмки или оставить «одна приёмка — один самодостаточный файл» как принцип (это удобно для заморозки sha256, см. selection.json в PHOTO_BASE).
6. **R-001 в 44 модулях**, из них 12 пишут md/tsv/txt/csv/log с `utf-8` без спецификации: identity_auto.py (7, ЗАНЯТ), visual_judge.py (4, ЗАНЯТ), tank_turret.py (1), build_dataset.py (2), weapon_judge.py (1, ЗАНЯТ), agent_full.py (2, ЗАНЯТ), agent_pose.py (2, ЗАНЯТ), attic/keep_batch.py (1), base_pack.py (1), fx_map.py (1), gen_fx.py (1), score_batch.py (1). Чинить точечно (занятые — через их сессии) или одним проходом после коммита.
7. **unit_refit.py / unit_ref.py** остановлены специалистом 03.10 (R-208), но unit_refit в gpu_scripts.txt и ставился в очередь — оставить как FROZEN или убрать из списка запускаемых.
8. **weapon_judge / visual_judge / identity_auto / weapons_chatgpt** (Codex exec) — нужна ли им очередь видеокарты как сериализация (тогда в gpu_scripts.txt) или они идут мимо неё по замыслу.
9. **ORPHAN с 05.10** (`weapon_describe_merge`, `weapon_handob_cards` — я переклассифицировал в ACTIVE как новые из серии weapons100; `item_geometry` 03.10 — ORPHAN) — подтвердить, что они в работе, иначе через неделю станут сиротами по-настоящему.
