# Ракурс боя (view-keeper), 05.10

battle_view.py audit (только чтение текстов): из 57 скриптов с моделью: USES 4 (unit_parts, unit_turnaround, weapons_restore, agent_full; agent_pose тоже импортирует, но его нет в gpu_scripts.txt), MISSING 17, no-words 14, NOT_BATTLE 14, NO_PROMPT 6, PROTECTED 2.

Дефекты самого audit (battle_view.py ЗАНЯТ): регулярка OWN_WORDS не ловит dimetric / upper left / 30 degrees / light from; no-words не значит «не про бой» — промпт может приходить из другого модуля; prod_two_pass_v1 попал в MISSING ложно (он вырезает слова стиля из подписей).

Собственные слова о ракурсе (не импортируют battle_view): gen_hd.py:73-79,174; map_paint.py:257; probe_object.py:51-62; obj_photo.py:56-90 (ближе всех к модулю, самый активный); floor_group.py:62-86; probe_floor.py:64,75 (смесь top-down + isometric); ground_relief.py:41-72 (ПРОТИВОРЕЧИЕ: тень вправо-вниз против UNROLLED_LIGHT «без направленного света»); make_ref.py:38 (нигде не упомянут — старый); gen_cursor.py (геометрия рамки, не переводить, R-040); gen_fire.py:54, gen_fire_real.py:30; unit_pilot.py:282, unit_direct.py:45-73, unit_refit.py:61 (остановлен R-208 — мёртвый); restore_probe_v1.py:50; weapons_synth.py:56 (вид не определён).

Сверка prompt_block с docs/research/battle-render.md: противоречий нет (геометрия 45/30/26.6, свет, FACING 0..7 совпадают). Замечание: генераторы развёрток должны брать prompt_block("floor_unrolled"), а не "floor".

Направления (R-084): DIRV в gen_combat_fx.py:713 и DIR_VEC в tank_turret.py:65 совпадают с движком, источник в комментарии есть. gen_path.py:118 DIRS не проверен.

Безопасно: ничего без слова Vitali — одобренные промпты на модуль переводятся только с его слова (R-112). Кандидаты без одобрения: unit_direct/unit_pilot (пилот), ground_relief (противоречие по тени), probe_floor (смесь видов). Нужно решение по obj_photo/probe_object (одобренная серия), gen_hd/map_paint (старые серии, bv.short), weapons_synth (вид).
