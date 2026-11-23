# X-Piratez: откровенные варианты внешности юнитов в бою (перепись)

Решение Vitali 03.10: прежде чем делать HD-юнитов 18+, переписать, какие откровенные варианты внешности УЖЕ есть в данных игры. Только перепись: ничего не генерировалось, игра не запускалась, установка Пираток только читалась.

| Что | Где |
|---|---|
| таблица | `census/units/explicit_variants.tsv` (строка на броню и вид: inv, battle, corpse) |
| обзор подтверждённых и неясных | `art/_review/units-18plus/explicit_overview.png` |
| обзор отвергнутых | `art/_review/units-18plus/rejected_overview.png` |
| листы просмотра | `art/_review/units-18plus/review/` - dolls_*, battle_*, corpses_* с индексами .tsv |
| скрипт | `tools/unit_explicit.py` (`--review` листы кукол, `--battle-review` листы боя) |

## Метод

1. Брони Пираток - из рулсетов после слияния модов (загрузчик tools/unit_census, терпит повторный якорь, R-046); у каждого поля записан файл и строка, откуда оно пришло (столбец source_mod).
2. **Кукла инвентаря** собирается так же, как InventoryState: `layersDefinition` (версия F0/M0, поверхности `<префикс>__<слой>__<предмет>` в порядке списка) или цепочка `spriteInv` (`<inv>F0.SPK`, `<inv>M0.SPK`, `<inv>.SPK`). SPK раскодируются из RLE, картинки - индексами, индекс 0 прозрачен (R-043), палитра боя delicious_regular.
3. Сигналы до просмотра: слои `*_NUDE` (тело) и `BIKINI_*`, доля видимого тела и зоны груди и паха, доля телесных цветов, слова в именах и строках en-US/ru и в педии (nude, naked, topless, голая, топлес, бельё). Сигналы только сортируют лист, решение принято глазами.
4. Одинаковые куклы (хэш составной картинки) сведены в группы: 181 броня с решением, решение по представителю действует на всю группу (`VERDICTS` в скрипте).
5. **Бой**: для каждой откровенной брони собран стоящий юнит из `spriteSheet` (drawingRoutine 0: ноги 16+d, руки 0+d / 8+d, торс 267+d у женской версии или 32+d, d=3) и кадр смерти 266; решение по листу (`BATTLE`).
6. **Труп**: `corpseBattle` -> картинка в BIGOBS по census/units/corpses.tsv; 573 разных картинки трупов отсортированы по доле телесного, просмотрены первые 250 (`CORPSE`).
7. **Пара**: (а) soldiers: `armorForAvatar` = откровенная, `armor` = обычная; (б) тот же базовый слой тела, обычная - броня по умолчанию типа бойца; (в) то же семейство листов (census/units/families.tsv) и общее начало ID не короче 6 знаков. Иначе - «нет пары».

## Итог

| Вид | подтверждено | неясно | отвергнуто |
|---|---|---|---|
| куклы инвентаря, броней | 96 | 11 | 74 |
| листы боя откровенных броней, разных листов | 47 | 12 | 4 |
| трупы откровенных броней, разных предметов | 41 | 12 | 9 |
| трупы ОБЫЧНЫХ броней с открытой картинкой, предметов (броней) | 25 (38) | 22 (23) | - |

Откровенных броней (кукла подтверждена или неясна): **107**, из них без одетой пары 35. Источник: piratez 107.

Главное для HD:

- Откровенное - это не редкие «секретные» брони, а **базовое состояние бойца**. Броня по умолчанию у типов бойцов: STR_SOLDIER_R - STR_PIR_NUDE_UC, STR_SOLDIER_W - STR_PIR_TOPLESS_UC, STR_SOLDIER_SYNTH - STR_SYNTH_NUDE_UC, STR_SOLDIER_NEKOMIMI_H - STR_NEKO_NUDE_UC; `armorForAvatar` почти у всех типов - *_NUDE (PIR, SLAVE, PEASANT, HYBRID, LAMIA, LOKNAR, GNOME, OGRE, NEKO). Голая пиратка ходит по общему листу PIR_500 у 8 броней.
- Одетая пара есть далеко не всегда: у враждебных и гражданских (ламия, призрак, паучиха, Аврора, голограмма, суккуб, жертва у столба) другого облика в данных нет вовсе.
- Трупы: картинка трупа часто откровенная **и у обычной брони** - оборванка (броня по умолчанию STR_SOLDIER), крестьянские платья, вечернее платье, джунгли, контрабандистка и др. Для цензурной версии трупы - отдельная работа, не следствие броней.

## Откровенные брони

Кукла / бой / труп: да - подтверждено, ? - неясно, нет - отвергнуто (одетое или общий лист с обычной), «-» - нет листа или трупа.

| Броня | Мод | Кукла | Лист боя | Бой | Труп | Обычная пара |
|---|---|---|---|---|---|---|
| ARMOR_AWAKENED_CORPSE | piratez | да | BFARM_DEF.PCK | да | STR_CORPSE_PIR_NUDE да | нет пары |
| AUR_ARMOR_2 | piratez | да | AUR_02.PCK | да | STR_AURORA_2_CORPSE_BATTLE да | нет пары |
| CIV_ARMOR_MUT_4 | piratez | да | MUT_4.PCK | да | CIV_MUT_4_CORPSE да | нет пары |
| CIV_ARMOR_SLAVE_GLADIATRIX | piratez | да | PIR_563.PCK | да | STR_CORPSE_PEASANT_GLADIATRIX да | нет пары |
| DAMSEL_SACRIFICE_ARMOR | piratez | да | SACRIFICE1.PCK | да | STR_DAMSEL_SACRIFICE_CORPSE да | нет пары |
| GHOST_0_ARMOR | piratez | да | GHOST_GAL.PCK | да | STR_GHOST_0_CORPSE_BATTLE ? | нет пары |
| GOLDEN_SAINT_2_ARMOR | piratez | да | AVT_2.PCK | да | STR_GOLDEN_SAINT_CORPSE_BATTLE нет | нет пары |
| HOLOGAL_ARMOR | piratez | да | HOLOGAL.PCK | ? | STR_HOLOGAL_CORPSE ? | нет пары |
| RETICULAN_ARMOR_P2 | piratez | да | RET_2.PCK | да | STR_RETICULAN_2_CORPSE_BATTLE да | нет пары |
| SPIDERGIRL_ARMOR | piratez | да | SPIDERGIRL.PCK | да | STR_SPIDERGIRL_CORPSE_BATTLE да | нет пары |
| STR_AMAZON_ARMOR_SEA_UC | piratez | да | PIR_500.PCK | да | STR_CORPSE_AMAZON ? | STR_PIR_CASTAWAY_ARMOR_UC |
| STR_ARMOR_DOCTOR_X_GNOME | piratez | да | PIR_901.PCK | да | STR_CORPSE_DOCTOR_X_KNIGHT_GEO да | нет пары |
| STR_ARMOR_SAINT_FAKE_UC | piratez | да | PIR_360.PCK | да | STR_CORPSE_PIR_NUDE да | STR_PIR_CASTAWAY_ARMOR_UC |
| STR_ARMOR_SAINT_UC | piratez | да | PIR_360.PCK | да | STR_CORPSE_PIR_NUDE да | STR_PIR_CASTAWAY_ARMOR_UC |
| STR_BERSERKER_ARMOR_UC | piratez | да | PIR_378.PCK | да | STR_CORPSE_PIR_NUDE да | нет пары |
| STR_BRAINER_OUTFIT_SEA_UC | piratez | да | PIR_281.PCK | да | STR_CORPSE_BRAINER_SEA да | STR_PIR_CASTAWAY_ARMOR_UC |
| STR_CAMO_PAINT_UC | piratez | да | PIR_111.PCK | да | STR_CORPSE_TOPLESS да | нет пары |
| STR_CHORT_ARMOR_UC | piratez | да | CHORT.PCK | ? | STR_CORPSE_CHORT ? | нет пары |
| STR_DAMSEL_VICTIM_ARMOR | piratez | да | PIR_490.PCK | да | STR_DAMSEL_VICTIM_CORPSE да | STR_DAMSEL_ARMOR_FURS_UC |
| STR_GNOME_NUDE_DREAMLAND_UC | piratez | да | PIR_901.PCK | да | STR_CORPSE_GNOME_NUDE да | STR_GNOME_DRESS_UC |
| STR_GNOME_NUDE_UC | piratez | да | PIR_901.PCK | да | STR_CORPSE_GNOME_NUDE да | STR_GNOME_DRESS_UC |
| STR_HERMIT_UC | piratez | да | PIR_484.PCK | ? | STR_CORPSE_HERMIT да | STR_PIR_CASTAWAY_ARMOR_UC |
| STR_HYBRID_NUDE_DREAMLAND_UC | piratez | да | PIR_601.PCK | да | STR_CORPSE_HYBRID_NUDE ? | STR_HYBRID_ADVISOR_UC |
| STR_HYBRID_NUDE_SEA_UC | piratez | да | PIR_601.PCK | да | STR_CORPSE_HYBRID_NUDE ? | STR_HYBRID_ADVISOR_UC |
| STR_HYBRID_NUDE_UC | piratez | да | PIR_601.PCK | да | STR_CORPSE_HYBRID_NUDE ? | STR_HYBRID_ADVISOR_UC |
| STR_HYBRID_PSICRYSTAL_DREAMLAND_UC | piratez | да | PIR_637.PCK | да | STR_CORPSE_HYBRID_PSICRYSTAL_NUDE ? | STR_HYBRID_ADVISOR_UC |
| STR_HYBRID_THONG_SEA_UC | piratez | да | PIR_602.PCK | да | STR_CORPSE_HYBRID_THONG ? | STR_HYBRID_ADVISOR_UC |
| STR_HYBRID_THONG_UC | piratez | да | PIR_602.PCK | да | STR_CORPSE_HYBRID_THONG ? | STR_HYBRID_ADVISOR_UC |
| STR_HYENA_RIDER_ARMOR_UC | piratez | да | HYENA_RIDER.PCK | ? | HYENA_RIDER_CORPSE_1 нет | STR_PIR_CASTAWAY_ARMOR_UC |
| STR_LAMIA_NUDE_DREAMLAND_UC | piratez | да | PIR_701.PCK | да | STR_CORPSE_LAMIA_NUDE да | STR_LAMIA_STRAPS_UC |
| STR_LAMIA_NUDE_SEA_UC | piratez | да | PIR_701.PCK | да | STR_CORPSE_LAMIA_NUDE да | STR_LAMIA_STRAPS_UC |
| STR_LAMIA_NUDE_S_UC | piratez | да | PIR_701.PCK | да | STR_CORPSE_LAMIA_NUDE да | STR_LAMIA_STRAPS_UC |
| STR_LAMIA_NUDE_UC | piratez | да | PIR_701.PCK | да | STR_CORPSE_LAMIA_NUDE да | STR_LAMIA_STRAPS_UC |
| STR_LINGERIE_BRA_UC | piratez | да | PIR_452.PCK | да | STR_CORPSE_PANTLESS да | STR_PIR_CASTAWAY_ARMOR_UC |
| STR_LINGERIE_SET_X_UC | piratez | да | PIR_450.PCK | да | STR_CORPSE_WENCH да | STR_PIR_CASTAWAY_ARMOR_UC |
| STR_LOKNAR_NUDE_DREAMLAND_UC | piratez | да | PIR_801.PCK | ? | STR_CORPSE_LOKNAR_NUDE нет | STR_LOKNAR_NIGHTFLYER_UC |
| STR_LOKNAR_NUDE_SEA_UC | piratez | да | PIR_801.PCK | ? | STR_CORPSE_LOKNAR_NUDE нет | STR_LOKNAR_NIGHTFLYER_UC |
| STR_LOKNAR_NUDE_UC | piratez | да | PIR_801.PCK | ? | STR_CORPSE_LOKNAR_NUDE нет | STR_LOKNAR_COAT_UC |
| STR_LOST_SOUL_F_ARMOR | piratez | да | PIR_551.PCK | да | STR_CORPSE_PEASANT_NUDE да | нет пары |
| STR_LOST_SOUL_M_ARMOR | piratez | да | PIR_501.PCK | да | STR_CORPSE_SLAVE_NUDE да | нет пары |
| STR_NEKO_BELLE_UC | piratez | да | XNEKO_009.PCK | да | STR_CORPSE_NEKO_BELLE да | STR_NEKO_BLITZ_ARMOR_UC |
| STR_NEKO_CAMO_PAINT_UC | piratez | да | XNEKO_050.PCK | да | STR_CORPSE_NEKO_CAMO_PAINT да | STR_NEKO_WITCH_OUTFIT_UC |
| STR_NEKO_GRAV_ARMOR_UC | piratez | да | XNEKO_100.PCK | да | STR_CORPSE_NEKO_GRAV_ARMOR да | STR_NEKO_STS_UC |
| STR_NEKO_NUDE_DREAMLAND_UC | piratez | да | XNEKO_301.PCK | да | STR_CORPSE_NEKO_NUDE_DREAMLAND да | STR_NEKO_WITCH_OUTFIT_UC |
| STR_NEKO_NUDE_UC | piratez | да | XNEKO_008.PCK | да | STR_CORPSE_NEKO_NUDE да | STR_NEKO_STS_UC |
| STR_NEKO_PATIENT_OUTFIT_UC | piratez | да | XNEKO_025.PCK | да | STR_CORPSE_NEKO_PATIENT да | STR_NEKO_STS_UC |
| STR_NEKO_SPACE_POD_UC | piratez | да | PIR_112.PCK | нет | STR_CORPSE_SPACE_POD нет | нет пары |
| STR_OGRE_NUDE_DREAMLAND_UC | piratez | да | PIR_851.PCK | да | STR_CORPSE_OGRE_NUDE ? | STR_OGRE_BREECHES_UC |
| STR_OGRE_NUDE_UC | piratez | да | PIR_851.PCK | да | STR_CORPSE_OGRE_NUDE ? | STR_OGRE_BREECHES_UC |
| STR_PATIENT_OUTFIT_UC | piratez | да | PIR_391.PCK | да | STR_CORPSE_PATIENT да | STR_PIR_CASTAWAY_ARMOR_UC |
| STR_PEASANT_ARMOR_HUNTER_UC | piratez | да | PIR_556.PCK | да | STR_CORPSE_PEASANT_HUNTER да | STR_PEASANT_ARMOR_DRESS_UC |
| STR_PEASANT_ARMOR_SAINT_UC | piratez | да | PIR_360.PCK | да | STR_CORPSE_PIR_NUDE да | STR_PEASANT_ARMOR_DRESS_UC |
| STR_PEASANT_BONDAGE_GEAR_UC | piratez | да | PIR_490.PCK | да | STR_CORPSE_PEASANT_NUDE да | STR_PEASANT_ARMOR_DRESS_UC |
| STR_PEASANT_MUD_UC | piratez | да | PIR_551.PCK | да | STR_CORPSE_PEASANT_NUDE да | нет пары |
| STR_PEASANT_NUDE_DREAMLAND_UC | piratez | да | PIR_551.PCK | да | STR_CORPSE_PEASANT_NUDE да | STR_PEASANT_ARMOR_DRESS_UC |
| STR_PEASANT_NUDE_SEA_UC | piratez | да | PIR_551.PCK | да | STR_CORPSE_PEASANT_NUDE да | STR_PEASANT_ARMOR_DRESS_UC |
| STR_PEASANT_NUDE_UC | piratez | да | PIR_551.PCK | да | STR_CORPSE_PEASANT_NUDE да | STR_PEASANT_ARMOR_DRESS_UC |
| STR_PIR_CHAINS_UC | piratez | да | PIR_500.PCK | да | STR_CORPSE_PIR_NUDE да | STR_PIR_CASTAWAY_ARMOR_UC |
| STR_PIR_GREMRIN_DREAMLAND_UC | piratez | да | PIR_313.PCK | да | STR_CORPSE_PIR_GREMRIN да | STR_PIR_CASTAWAY_ARMOR_UC |
| STR_PIR_GREMRIN_UC | piratez | да | PIR_313.PCK | да | STR_CORPSE_PIR_GREMRIN да | STR_PIR_CASTAWAY_ARMOR_UC |
| STR_PIR_MINX_UC | piratez | да | PIR_151.PCK | да | STR_CORPSE_TOPLESS да | STR_PIR_CASTAWAY_ARMOR_UC |
| STR_PIR_NUDE_DREAMLAND_UC | piratez | да | PIR_500.PCK | да | STR_CORPSE_PIR_NUDE_DREAMLAND да | STR_PIR_CASTAWAY_ARMOR_UC |
| STR_PIR_NUDE_SEA_UC | piratez | да | PIR_500.PCK | да | STR_CORPSE_PIR_NUDE да | STR_PIR_CASTAWAY_ARMOR_UC |
| STR_PIR_NUDE_UC | piratez | да | PIR_500.PCK | да | STR_CORPSE_PIR_NUDE да | STR_PIR_CASTAWAY_ARMOR_UC |
| STR_PIR_SLAVE_ARMOR_FAKE_UC | piratez | да | PIR_490.PCK | да | STR_CORPSE_PIR_NUDE да | STR_PIR_CASTAWAY_ARMOR_UC |
| STR_PIR_SLAVE_ARMOR_UC | piratez | да | PIR_490.PCK | да | STR_CORPSE_PIR_NUDE да | STR_PIR_CASTAWAY_ARMOR_UC |
| STR_PIR_TOPLESS_UC | piratez | да | PIR_111.PCK | да | STR_CORPSE_TOPLESS да | STR_PIR_CASTAWAY_ARMOR_UC |
| STR_RAGS_UC | piratez | да | PIR_481.PCK | да | STR_CORPSE_RAGS да | STR_PIR_CASTAWAY_ARMOR_UC |
| STR_SAVAGE_ARMOR_UC | piratez | да | PIR_373.PCK | да | STR_CORPSE_SAVAGE да | STR_PIR_CASTAWAY_ARMOR_UC |
| STR_SLAVE_ARMOR_SAINT_UC | piratez | да | PIR_530.PCK | да | STR_CORPSE_SLAVE_SAINT да | STR_SLAVE_PUNK_UC |
| STR_SLAVE_NUDE_DREAMLAND_UC | piratez | да | PIR_501.PCK | да | STR_CORPSE_SLAVE_NUDE да | STR_SLAVE_PUNK_UC |
| STR_SLAVE_NUDE_SEA_UC | piratez | да | PIR_501.PCK | да | STR_CORPSE_SLAVE_NUDE да | STR_SLAVE_PUNK_UC |
| STR_SLAVE_NUDE_UC | piratez | да | PIR_501.PCK | да | STR_CORPSE_SLAVE_NUDE да | STR_SLAVE_PUNK_UC |
| STR_SLIMEGAL_BODY_SEA_UC | piratez | да | PIR_500.PCK | да | STR_CORPSE_SLIMEGAL да | нет пары |
| STR_SLIMEGAL_BODY_UC | piratez | да | PIR_500.PCK | да | STR_CORPSE_SLIMEGAL да | нет пары |
| STR_SPACE_POD_GNOME_UC | piratez | да | PIR_112.PCK | нет | STR_CORPSE_SPACE_POD нет | нет пары |
| STR_SPACE_POD_HYBRID_UC | piratez | да | PIR_112.PCK | нет | STR_CORPSE_SPACE_POD нет | нет пары |
| STR_SPACE_POD_LAMIA_UC | piratez | да | PIR_112.PCK | нет | STR_CORPSE_SPACE_POD нет | нет пары |
| STR_SPACE_POD_PEASANT_UC | piratez | да | PIR_112.PCK | нет | STR_CORPSE_SPACE_POD нет | нет пары |
| STR_SPACE_POD_UC | piratez | да | PIR_112.PCK | нет | STR_CORPSE_SPACE_POD нет | нет пары |
| STR_STEALTH_ARMOR_SEA_UC | piratez | да | PIR_46.PCK | ? | STR_CORPSE_STEALTH да | нет пары |
| STR_STEALTH_ARMOR_UC | piratez | да | PIR_46.PCK | ? | STR_CORPSE_STEALTH да | нет пары |
| STR_SWIFTSUIT_SEA_UC | piratez | да | PIR_180.PCK | да | STR_CORPSE_GRAV_ARMOR нет | STR_PIR_CASTAWAY_ARMOR_UC |
| STR_SWIFTSUIT_UC | piratez | да | PIR_180.PCK | да | STR_CORPSE_GRAV_ARMOR нет | STR_PIR_CASTAWAY_ARMOR_UC |
| STR_SYNTH_NUDE_A_SPACE_UC | piratez | да | PIR_663.PCK | да | STR_CORPSE_SYNTH_NUDE_SPACE нет | STR_SYNTH_REFRACTOR_A_UC |
| STR_SYNTH_NUDE_A_UC | piratez | да | PIR_668.PCK | да | STR_CORPSE_SYNTH_NUDE_A нет | STR_SYNTH_REFRACTOR_A_UC |
| STR_SYNTH_NUDE_SEA_UC | piratez | да | PIR_666.PCK | да | STR_CORPSE_SYNTH_NUDE нет | STR_SYNTH_REFRACTOR_A_UC |
| STR_SYNTH_NUDE_UC | piratez | да | PIR_666.PCK | да | STR_CORPSE_SYNTH_NUDE нет | STR_SYNTH_REFRACTOR_A_UC |
| STR_THEBAN_DRESS_SEA_UC | piratez | да | PIR_500.PCK | да | STR_CORPSE_THEBAN_DRESS да | STR_PIR_CASTAWAY_ARMOR_UC |
| STR_THEBAN_DRESS_UC | piratez | да | PIR_451.PCK | да | STR_CORPSE_THEBAN_DRESS да | STR_PIR_CASTAWAY_ARMOR_UC |
| STR_TOPLESS_SEA_UC | piratez | да | PIR_111.PCK | да | STR_CORPSE_TOPLESS да | STR_PIR_CASTAWAY_ARMOR_UC |
| STR_WRAITH_FEM_ARMOR | piratez | да | WRAITH.PCK | ? | STR_WRAITH_CORPSE ? | STR_WRAITH_GUARD_FEM_ARMOR |
| STYGIAN_GUARD_ARMOR | piratez | да | STYGIAN_GUARD.PCK | да | STR_STYGIAN_GUARD_CORPSE ? | нет пары |
| SUCCUBUS_ARMOR | piratez | да | SUCCUBUS.PCK | да | STR_SUCCUBUS_CORPSE да | нет пары |
| UBER_BELTER_ARMOR | piratez | да | UBR_BLT.PCK | да | STR_UBER_BELTER_CORPSE_BATTLE да | нет пары |
| ZOMBIE_CARRIE_ARMOR | piratez | да | ZOMBIE_CARRIE.PCK | да | STR_ZOMBIE_CARRIE_CORPSE да | нет пары |
| CHURCH_ARMOR_P4 | piratez | ? | COS_3.PCK | нет | STR_CHURCH_3_CORPSE_BATTLE нет | нет пары |
| RETICULAN_ARMOR_P1 | piratez | ? | RET_1.PCK | ? | STR_RETICULAN_1_CORPSE_BATTLE ? | нет пары |
| STR_CIV_ARMOR_CASTAWAY_GAL | piratez | ? | PIR_489.PCK | нет | STR_CORPSE_CASTAWAY да | нет пары |
| STR_GNOME_EXPERIMENT_UC | piratez | ? | PIR_903.PCK | ? | STR_CORPSE_GNOME_EXPERIMENT да | STR_GNOME_DRESS_UC |
| STR_HOLOSUIT_UC | piratez | ? | PIR_460.PCK | ? | STR_CORPSE_HOLOSUIT да | STR_PIR_CASTAWAY_ARMOR_UC |
| STR_NEKO_HOLOSUIT_UC | piratez | ? | XNEKO_105.PCK | ? | STR_CORPSE_NEKO_HOLOSUIT ? | STR_NEKO_STS_UC |
| STR_NIGHTGOWN_DREAMLAND_UC | piratez | ? | PIR_455.PCK | нет | STR_CORPSE_GOWN да | STR_PIR_CASTAWAY_ARMOR_UC |
| STR_NIGHTGOWN_UC | piratez | ? | PIR_455.PCK | нет | STR_CORPSE_GOWN да | STR_PIR_CASTAWAY_ARMOR_UC |
| STR_SPACE_POD_LOKNAR_UC | piratez | ? | PIR_112.PCK | нет | STR_CORPSE_SPACE_POD нет | нет пары |
| STR_SYNTH_REFRACTOR_UC | piratez | ? | PIR_667.PCK | ? | STR_CORPSE_SYNTH_NUDE нет | STR_SYNTH_REFRACTOR_A_UC |
| STR_WRAITH_ARMOR | piratez | ? | WRAITH.PCK | ? | STR_WRAITH_CORPSE ? | STR_WRAITH_GUARD_FEM_ARMOR |

Как найдена пара - столбец link_evidence таблицы; доказательство каждой строки (файл рулсета и строка) - столбцы source_mod и evidence.

## Трупы обычных броней с открытой картинкой

| Предмет трупа | Решение | Брони |
|---|---|---|
| CIVF_CORPSE | да | CIVF_ARMOR, CIV_ARMOR_F1, STR_UNARMORED_HUMAN |
| CIVF_CORPSE_TRAITOR | да | CIV_ARMOR_F1_TRAITOR |
| STR_AURORA_2_CORPSE_BATTLE | да | AUR_ARMOR_1 |
| STR_CORPSE | да | STR_NONE_UC |
| STR_CORPSE_CASTAWAY | да | STR_PIR_CASTAWAY_ARMOR_UC |
| STR_CORPSE_DOCTOR_X_KNIGHT_GEO | да | STR_ARMOR_DOCTOR_X_KNIGHT_NUDE |
| STR_CORPSE_DOCTOR_X_VAMPIRE | да | STR_ARMOR_DOCTOR_X_VAMPIRE |
| STR_CORPSE_DOLL | да | STR_AURORA_DOLL_ARMOR_UC |
| STR_CORPSE_GNOME_EXPLORER_SEA | да | STR_GNOME_EXPLORER_SEA_UC |
| STR_CORPSE_GNOME_GLITTER | да | STR_GNOME_GLITTERARMOR_DREAMLAND_UC, STR_GNOME_GLITTERARMOR_UC |
| STR_CORPSE_GOWN | да | STR_HOBO_DRESS_UC |
| STR_CORPSE_PARTY_DRESS | да | STR_PARTY_DRESS_UC |
| STR_CORPSE_PEASANT_CAMO | да | ARMOR_HALF_UBER_GIRL, STR_PEASANT_CAMO_UC |
| STR_CORPSE_PEASANT_DRESS | да | STR_PEASANT_ARMOR_DRESS_UC, STR_PIR_SPECTRE_DREAMLAND_UC, STR_WHITE_DRESS_UC |
| STR_CORPSE_PEASANT_FUSILIER | да | STR_PEASANT_FUSILIER_UC |
| STR_CORPSE_PEASANT_GLADIATRIX | да | STR_PEASANT_ARMOR_GLADIATRIX_UC |
| STR_CORPSE_PEASANT_GLITTER | да | STR_PEASANT_GLITTERARMOR_DREAMLAND_UC, STR_PEASANT_GLITTERARMOR_UC |
| STR_CORPSE_PIR_CLOTHING | да | STR_CLOTHING_UC |
| STR_CORPSE_PIR_MAGICAL_OUTFIT | да | STR_MAGICAL_GIRL_OUTFIT_SEA_UC, STR_MAGICAL_GIRL_OUTFIT_UC |
| STR_CORPSE_SAVAGE | да | STR_BARBARIAN_ARMOR_S_UC, STR_BARBARIAN_ARMOR_UC |
| STR_CORPSE_SLAVE_NUDE | да | STR_SLAVE_ARMOR_LOINCLOTH_SEA_UC, STR_SLAVE_ARMOR_LOINCLOTH_UC, STR_SLAVE_ARMOR_TUNIC_A_UC, STR_SLAVE_ARMOR_TUNIC_UC |
| STR_CORPSE_TOPLESS | да | STR_LINGERIE_TEDDY_UC, STR_MAGE_ROBE_UC |
| STR_JUNGLE_GAL_CORPSE_BATTLE | да | JUNGLE_GAL_ARMOR |
| STR_SMUGGLER_5_CORPSE_BATTLE | да | SMUGGLER_ARMOR_P5 |
| STR_ZOMBIE_SADAKO_CORPSE | да | ZOMBIE_SADAKO_ARMOR |
| STR_CORPSE_AMAZON | ? | STR_AMAZON_ARMOR_UC, STR_BARBARIAN_RAGS_UC |
| STR_CORPSE_BRAINER | ? | STR_BRAINER_OUTFIT_UC |
| STR_CORPSE_CHORT | ? | STR_CHORT_ARMOR_INFILTRATION_UC |
| STR_CORPSE_DOCTOR_X_SORCERESS | ? | STR_ARMOR_DOCTOR_X_SORCERESS |
| STR_CORPSE_GNOME_CAMO_PAINT | ? | STR_GNOME_CAMO_PAINT_UC |
| STR_CORPSE_GNOME_EXPLORER | ? | STR_GNOME_EXPLORER_UC |
| STR_CORPSE_NEKO_BIKINI | ? | STR_NEKO_BIKINI_UC |
| STR_CORPSE_NEKO_HERBALIST | ? | STR_NEKO_HERBALIST_OUTFIT_UC |
| STR_CORPSE_NEKO_PARTY_DRESS | ? | STR_NEKO_PARTY_DRESS_UC |
| STR_CORPSE_NURSE_ADV | ? | STR_NURSE_OUTFIT_ADV_UC |
| STR_CORPSE_PEASANT_MEIDO | ? | STR_PEASANT_MEIDO_UC |
| STR_CORPSE_PEASANT_MILITIA | ? | STR_PEASANT_ARMOR_MILITIA_UC |
| STR_CORPSE_PEASANT_SAILOR | ? | STR_PEASANT_ARMOR_SAILOR_UC |
| STR_CORPSE_PEASANT_SCAVENGER | ? | STR_SCAVENGER_OUTFIT_UC |
| STR_CORPSE_REDMAGE_I | ? | STR_ARMOR_RED_MAGE_DRESS |
| STR_CORPSE_RUNT | ? | STR_RUNT_OUTFIT_UC |
| STR_CORPSE_SMOKEY | ? | STR_SMOKEY_ARMOR_UC |
| STR_CORPSE_SP_AMBER | ? | STR_SP_AMBER_UC |
| STR_HUMAN_1_CORPSE_BATTLE | ? | HUMAN_ARMOR_STEWARDESS |
| STR_HUMAN_5_CORPSE_BATTLE | ? | HUMAN_ARMOR_M5 |
| STR_HUMAN_8_CORPSE_BATTLE | ? | HUMAN_ARMOR_F8 |
| STR_RETBANDIT_1_CORPSE_BATTLE | ? | RETBANDIT_ARMOR_P1 |

## Отвергнутые кандидаты

Кукла подозрительна по сигналам (слово в имени или педии, слой тела, много телесного), но одета. Лист - rejected_overview.png.

| Броня | Почему |
|---|---|
| ARMOR_KOBOLD_HUNTRESS | сетчатая броня |
| BANDIT_ARMOR_P13 | мужчина в плавках |
| CIV_ARMOR_BUSY_CATGIRL | одета |
| CIV_ARMOR_TRIBAL | мужчина в набедренной повязке |
| DANCER_ARMOR | стриптизерша в бикини |
| GOLDEN_SAINT_1_ARMOR | фигура в пламени, тела не видно |
| HOE_ARMOR_P1 | лифчик и юбка |
| HUMAN_ARMOR_F8 | комбинезон |
| NINJA_ARMOR_1 | одета, вырез |
| RAIDER_ARMOR_P1 | бикини |
| RAIDER_ARMOR_P3 | бикини |
| RETICULAN_ARMOR_P0 | пришелец без половых признаков |
| RETICULAN_ARMOR_P7 | пришелец без половых признаков |
| SECTOID_ARMOR_P12 | купальник |
| SMUGGLER_ARMOR_P2 | одета |
| STR_AMAZON_ARMOR_UC | бикини |
| STR_ARMOR_DOCTOR_X_KNIGHT | только педия: без брони была бы голой; кукла в броне |
| STR_ARMOR_RED_MAGE_BIKINI_SEA | бикини |
| STR_ARMOR_RED_MAGE_DRESS | платье |
| STR_AURORA_DOLL_ARMOR_UC | бикини |
| STR_BARBARIAN_ARMOR_S_UC | лифчик и юбка |
| STR_BARBARIAN_ARMOR_UC | лифчик и юбка |
| STR_BARBARIAN_RAGS_UC | купальник |
| STR_BIKINI_SEA_UC | бикини |
| STR_BIKINI_UC | бикини |
| STR_BLITZ_ARMOR_SEA_UC | одета |
| STR_BLITZ_ARMOR_UC | одета |
| STR_CHILLER_SEA_UC | купальник |
| STR_CHILLER_UC | купальник |
| STR_CHORT_ARMOR_INFILTRATION_UC | чёрный облегающий силуэт без деталей |
| STR_CLOTHING_UC | вырез рубашки |
| STR_FORCE_ARMOR_SEA_UC | лифчик |
| STR_FORCE_ARMOR_UC | лифчик |
| STR_GNOME_BIKINI_SEA_UC | бикини |
| STR_GNOME_EXPLORER_SEA_UC | только педия: про ныряние голышом; кукла одета |
| STR_GNOME_FIRESTARTER_UC | ремни-купальник |
| STR_GNOME_GLITTERARMOR_DREAMLAND_UC | купальник |
| STR_GNOME_GLITTERARMOR_UC | купальник |
| STR_GRAV_ARMOR_UC | сбруя закрывает грудь |
| STR_LAMIA_SCALE_MAIL_UC | чешуйчатая броня |
| STR_LAMIA_STRAPS_UC | грудь закрыта сбруей |
| STR_LINGERIE_SET_UC | платье |
| STR_LINGERIE_TEDDY_UC | боди |
| STR_MAGICAL_GIRL_OUTFIT_SEA_UC | бельё, грудь закрыта |
| STR_MAGICAL_GIRL_OUTFIT_UC | бельё, грудь закрыта |
| STR_MEIDO_OUTFIT_UC | платье горничной |
| STR_NEKO_BIKINI_UC | бикини |
| STR_NEKO_UNIPUMA_UC | одета |
| STR_NURSE_OUTFIT_ADV_UC | грудь закрыта |
| STR_NURSE_OUTFIT_UC | платье медсестры |
| STR_OGRE_SWIM_SEA_UC | мужчина в плавках |
| STR_OGRE_SWIM_UC | мужчина в плавках |
| STR_PARTY_DRESS_UC | платье |
| STR_PEASANT_ARMOR_GLADIATRIX_UC | ремни поверх груди |
| STR_PEASANT_ARMOR_MILITIA_UC | грудь закрыта |
| STR_PEASANT_GLITTERARMOR_DREAMLAND_UC | купальник |
| STR_PEASANT_GLITTERARMOR_UC | купальник |
| STR_PIR_CASTAWAY_ARMOR_UC | вырез рубашки |
| STR_PIR_ROGUE_UC | одета |
| STR_PIR_SWASHBUCKLER_UC | одета |
| STR_RED_MAGE_RITUAL_ARMOR | бикини |
| STR_RUNT_OUTFIT_UC | одета |
| STR_SCOUT_OUTFIT_UC | лифчик |
| STR_SLAVE_ARMOR_LOINCLOTH_SEA_UC | мужчина в набедренной повязке |
| STR_SLAVE_ARMOR_LOINCLOTH_UC | мужчина в набедренной повязке |
| STR_SLAVE_ARMOR_TUNIC_A_UC | мужской торс, туника |
| STR_SPACE_POD_SLAVE_UC | мужской торс в капсуле |
| STR_SWIMSUIT_PEASANT_SEA_UC | купальник |
| STR_SWIMSUIT_PEASANT_UC | купальник |
| STR_SWIMSUIT_SEA_UC | купальник |
| STR_SWIMSUIT_UC | купальник |
| STR_SYNTH_CATSUIT_UC | комбинезон |
| STR_VOODOO_ARMOR_UC | корсет, грудь закрыта |
| ZOMBIE_SADAKO_ARMOR | голый торс без половых признаков |

Отвергнуто и внутри откровенных броней: лист боя капсулы PIR_112 (6 броней SPACE_POD: голая в инвентаре, в бою закрытая капсула), CHURCH_ARMOR_P4 (в названии «голая», и кукла и бой - купальник), ночные рубашки PIR_455, гражданская оборванка с общим листом PIR_489.

## Неясное

- Куклы смотрены в одной версии (F0, у мужских M0); вторые версии и слои предметов поверх тела - нет.
- Бой и трупы - 32x40 и 32x48: поза, вырез и полупрозрачность часто не читаются. Неясными оставлены голограммы и сетки (HOLOGAL, XNEKO_105, PIR_903, PIR_460, PIR_46), перекрашенные скриптом тела (PIR_801 локнар, PIR_667 синт), тёмные (WRAITH, CHORT, RET_1), PIR_484 под плащом. HYENA_RIDER (большой юнит) не собран вовсе.
- Цвет кожи у части броней даёт скрипт мода (recolor), а не лист: на собранном без скрипта кадре тело серое, решение по такому кадру - неясно.
- Трупы с 251 по 573 по доле телесного не просмотрены: там в основном звери, машины и чудовища, но единичные пропуски возможны.
- Пара «по семейству листов» - вывод по сходству, а не связь в данных; в отчёте помечена отдельно.
- Две брони названы голыми только в педии (STR_ARMOR_DOCTOR_X_KNIGHT, STR_GNOME_EXPLORER_SEA_UC): кукла одета, отвергнуты.

## Что это значит для HD-конвейера

По HD_UNITS раздел 12: цензурная версия - в мод hd, откровенная - отдельным файлом в hd_18+; одетое не раздевать; варианты только из существующих данных.

- Брони и листы со статусом «да» - это и есть список того, что ложится в hd_18+ как есть (HD-перерисовка того же содержимого). В hd для них нужна цензурная версия того же листа: прикрыть, не меняя силуэт и анимацию.
- У «нет пары» цензурную версию взять неоткуда, кроме прикрытия того же листа: одетого листа в игре нет, придумывать новую одежду - это новый вариант, а не существующий.
- Общие листы (PIR_500 у 8 броней, PIR_551 у 5) рисуются один раз: решение по листу, а не по броне.
- «Неясно» - сначала глазами Vitali на обзоре, потом в работу.
- Трупы обычных броней - отдельный список: цензурная версия нужна и там, где сама броня одета.
- Отвергнутые в hd_18+ не идут: откровенной версии в данных у них нет, раздевать одетое нельзя.
