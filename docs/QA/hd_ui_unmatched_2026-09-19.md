# HD-картинки интерфейса без пары

Замер: сессия 19-09-2026 00:24, X-Piratez + мод `hd`, строки `HD interface: ... matches no image of the mods`.

Всего таких картинок — **95** из 1659 загруженных. Файл-источник нашёлся у всех, значит имена верные;
не сходится не имя, а способ, которым игра грузит эти картинки.

## Почему не грузятся

`Mod::loadHdUiArt()` ищет пару по ИМЕНИ среди `_surfaces` и `_extraSprites` — то есть среди картинок,
которые мод объявил как спрайты. Ролики объявлены иначе: у них в рулсете `imagePath: Resources/Cutscenes/<файл>.png`,
и `SlideshowState` грузит файл напрямую в свою поверхность. Такой картинки нет ни в одном списке имён,
поэтому HD-пара к ней не привязывается никогда — сколько её ни перерисовывай.

## Ролики (`Resources/Cutscenes/`) — грузятся по пути, а не по имени

Штук: 90

- `alien_shore.png` → `Piratez/Resources/Cutscenes/Alien_Shore.png`
- `aurorahouri_fg_346_cpal.png` → `Piratez/Resources/Cutscenes/AuroraHouri_FG_346_CPAL.png`
- `bfm_cpal.png` → `Piratez/Resources/Cutscenes/BFM_CPAL.png`
- `blackdragon_fg_359_cpal.png` → `Piratez/Resources/Cutscenes/BlackDragon_FG_359_CPAL.png`
- `bloomlady_introa_fg_356_cpal.png` → `Piratez/Resources/Cutscenes/BloomLady_IntroA_FG_356_CPAL.png`
- `canny_queen.png` → `Piratez/Resources/Cutscenes/Canny_Queen.png`
- `canny_ritual.png` → `Piratez/Resources/Cutscenes/Canny_Ritual.png`
- `cleo_cosmic.png` → `Piratez/Resources/Cutscenes/Cleo_Cosmic.png`
- `comet.png` → `OAK patch for RU Piratez/Resources/Cutscenes/Comet.png`
- `councilappears.png` → `Piratez/Resources/Cutscenes/CouncilAppears.png`
- `cthulhu_sacrifice_3_cpal.png` → `Piratez/Resources/Cutscenes/Cthulhu_Sacrifice_3_CPAL.png`
- `cyber_towers_cpal.png` → `Piratez/Resources/Cutscenes/Cyber_Towers_CPAL.png`
- `deathscene_1_cpal.png` → `Piratez/Resources/Cutscenes/DEATHSCENE_1_CPAL.png`
- `defenders_of_humanity.png` → `Piratez/Resources/Cutscenes/Defenders_Of_Humanity.png`
- `desertintro_fg_375_cpal.png` → `Piratez/Resources/Cutscenes/DesertIntro_FG_375_CPAL.png`
- `dream10.png` → `Piratez/Resources/Cutscenes/Dream10.png`
- `dream16b_cpal.png` → `Piratez/Resources/Cutscenes/Dream16B_CPAL.png`
- `dreamwave_cpal.png` → `Piratez/Resources/Cutscenes/Dreamwave_CPAL.png`
- `dungeon_sword.png` → `Piratez/Resources/Cutscenes/Dungeon_Sword.png`
- `elevatorshaft_fg_340_cpal.png` → `Piratez/Resources/Cutscenes/ElevatorShaft_FG_340_CPAL.png`
- `escape_from_hell_2_cpal.png` → `Piratez/Resources/Cutscenes/Escape_From_Hell_2_CPAL.png`
- `glowing_pyramid.png` → `Piratez/Resources/Cutscenes/Glowing_Pyramid.png`
- `greatbase.png` → `Piratez/Resources/Cutscenes/GreatBase.png`
- `gudrun_seductive_cpal.png` → `Piratez/Resources/Cutscenes/Gudrun_Seductive_CPAL.png`
- `gudrunduel1fg_cpal.png` → `Piratez/Resources/Cutscenes/GudrunDuel1FG_CPAL.png`
- `gudrunduel2fg_cpal.png` → `Piratez/Resources/Cutscenes/GudrunDuel2FG_CPAL.png`
- `gudrunduel3fg_cpal.png` → `Piratez/Resources/Cutscenes/GudrunDuel3FG_CPAL.png`
- `gudrunduel4fg_cpal.png` → `Piratez/Resources/Cutscenes/GudrunDuel4FG_CPAL.png`
- `gudrunduel5fg_cpal.png` → `Piratez/Resources/Cutscenes/GudrunDuel5FG_CPAL.png`
- `inferno.png` → `OAK patch for RU Piratez/Resources/Cutscenes/Inferno.png`
- `intro1_fg_orky_cpal.png` → `Piratez/Resources/Cutscenes/Intro1_FG_Orky_CPAL.png`
- `intro2_fg_1_cpal.png` → `Piratez/Resources/Cutscenes/Intro2_FG_1_CPAL.png`
- `intro_00.png` → `OAK patch for RU Piratez/Resources/Cutscenes/Intro_00.png`
- `intro_00b_cpal.png` → `Piratez/Resources/Cutscenes/Intro_00b_CPAL.png`
- `intro_00splash.png` → `OAK patch for RU Piratez/Resources/Cutscenes/Intro_00Splash.png`
- `intro_06_cpal.png` → `Piratez/Resources/Cutscenes/Intro_06_CPAL.png`
- `intro_10.png` → `Piratez/Resources/Cutscenes/Intro_10.png`
- `intro_escape_fg_347_cpal.png` → `Piratez/Resources/Cutscenes/Intro_Escape_FG_347_CPAL.png`
- `intro_gudrunlessons_cpal.png` → `Piratez/Resources/Cutscenes/Intro_GudrunLessons_CPAL.png`
- `introbasefound_fg_843_cpal.png` → `Piratez/Resources/Cutscenes/IntroBaseFound_FG_843_CPAL.png`
- `intropeasants_fg_564_cpal.png` → `Piratez/Resources/Cutscenes/IntroPeasants_FG_564_CPAL.png`
- `knights_of_cydonia_oldearth.png` → `Piratez/Resources/Cutscenes/Knights_Of_Cydonia_OldEarth.png`
- `lawnch_cpal.png` → `Piratez/Resources/Cutscenes/Lawnch_CPAL.png`
- `mars_canyons.png` → `Piratez/Resources/Cutscenes/Mars_Canyons.png`
- `metropolis_cpal.png` → `Piratez/Resources/Cutscenes/Metropolis_CPAL.png`
- `mibgirl.png` → `Piratez/Resources/Cutscenes/MiBGirl.png`
- `miscresearch.png` → `Piratez/Resources/Cutscenes/MiscResearch.gif`
- `munintro_fg_373_cpal.png` → `Piratez/Resources/Cutscenes/MunIntro_FG_373_CPAL.png`
- `mutant_resistance.png` → `Piratez/Resources/Cutscenes/Mutant_Resistance.png`
- `mydra.png` → `Piratez/Resources/Cutscenes/Mydra.png`
- `noctis_1.png` → `Piratez/Resources/Cutscenes/Noctis_1.png`
- `noctis_2.png` → `Piratez/Resources/Cutscenes/Noctis_2.png`
- `noctis_3.png` → `Piratez/Resources/Cutscenes/Noctis_3.png`
- `orbital_cannon.png` → `Piratez/Resources/Cutscenes/Orbital_Cannon.png`
- `outronucc12_cpal.png` → `Piratez/Resources/Cutscenes/OutroNucc12_CPAL.png`
- `planet_66.png` → `Piratez/Resources/Cutscenes/Planet_66.png`
- `pods_cs1_cpal.png` → `Piratez/Resources/Cutscenes/Pods_CS1_CPAL.png`
- `priss_x1.png` → `Piratez/Resources/Cutscenes/PRISS_x1.png`
- `raider_camp.png` → `Piratez/Resources/Cutscenes/Raider_Camp.png`
- `red_death.png` → `Piratez/Resources/Cutscenes/Red_Death.png`
- `red_sun_dreams_cpal.png` → `Piratez/Resources/Cutscenes/Red_Sun_Dreams_CPAL.png`
- `robot_army_rising_cpal.png` → `Piratez/Resources/Cutscenes/Robot_Army_Rising_CPAL.png`
- `sakurazilla.png` → `OAK patch for RU Piratez/Resources/Cutscenes/SakuraZilla.png`
- `seeders.png` → `OAK patch for RU Piratez/Resources/Cutscenes/Seeders.png`
- `sgr_01_cpal.png` → `Piratez/Resources/Cutscenes/sgr_01_CPAL.png`
- `sgr_02_cpal.png` → `Piratez/Resources/Cutscenes/sgr_02_CPAL.png`
- `sgr_03_cpal.png` → `Piratez/Resources/Cutscenes/sgr_03_CPAL.png`
- `sgr_04_cpal.png` → `Piratez/Resources/Cutscenes/sgr_04_CPAL.png`
- `sgr_05_cpal.png` → `Piratez/Resources/Cutscenes/sgr_05_CPAL.png`
- `sgr_06_cpal.png` → `Piratez/Resources/Cutscenes/sgr_06_CPAL.png`
- `sgr_07_cpal.png` → `Piratez/Resources/Cutscenes/sgr_07_CPAL.png`
- `shadow_gate_m_cpal.png` → `Piratez/Resources/Cutscenes/Shadow_Gate_M_CPAL.png`
- `shadowplanet.png` → `Piratez/Resources/Cutscenes/ShadowPlanet.png`
- `snow_white_cpal.png` → `Piratez/Resources/Cutscenes/Snow_White_CPAL.png`
- `spaceassault.png` → `OAK patch for RU Piratez/Resources/Cutscenes/SpaceAssault.png`
- `spacebar4_cpal.png` → `Piratez/Resources/Cutscenes/Spacebar4_CPAL.png`
- `spacegal_cpal.png` → `Piratez/Resources/Cutscenes/SpaceGal_CPAL.png`
- `spaceyaht.png` → `OAK patch for RU Piratez/Resources/Cutscenes/SpaceYaht.png`
- `styx.png` → `OAK patch for RU Piratez/Resources/Cutscenes/Styx.png`
- `supercore.png` → `OAK patch for RU Piratez/Resources/Cutscenes/Supercore.png`
- `syn_apoc.png` → `Piratez/Resources/Cutscenes/Syn_Apoc.png`
- `technocracy.png` → `Piratez/Resources/Cutscenes/Technocracy.png`
- `thebes2.png` → `Piratez/Resources/Cutscenes/Thebes2.png`
- `tunnel_c1.png` → `Piratez/Resources/Cutscenes/Tunnel_C1.png`
- `visions.png` → `Piratez/Resources/Cutscenes/Visions.gif`
- `walkingtheplank_fg_167_cpal.png` → `Piratez/Resources/Cutscenes/WalkingThePlank_FG_167_CPAL.png`
- `xc_184.png` → `Piratez/Resources/Cutscenes/XC_184.png`
- `zanderfulluped.png` → `Piratez/Resources/Cutscenes/ZanderFullUPED.png`
- `zandersmalldark.png` → `Piratez/Resources/Cutscenes/ZanderSmallDark.png`
- `zandersmalldark2.png` → `Piratez/Resources/Cutscenes/ZanderSmallDark2.png`

## ХабароПедия (`Resources/Pedia/`) — файл есть, но ни один рулсет на него не ссылается

Штук: 5

- `c_017_cpal.png` → `Piratez/Resources/Pedia/C_017_CPAL.png`
- `golden_prince_ai1_cpal.png` → `Piratez/Resources/Pedia/Golden_Prince_AI1_CPAL.png`
- `milking.png` → `Piratez/Resources/Pedia/Milking.png`
- `piraterest.png` → `Piratez/Resources/Pedia/PirateRest.png`
- `witches2.png` → `Piratez/Resources/Pedia/Witches2.png`

## Что с этим делать

- Ролики: чтобы HD-кадр подхватывался, движок должен знать картинку ролика по имени файла —
  либо регистрировать слайды при загрузке рулсетов, либо привязывать пару в `SlideshowState` по содержимому.
  Решение не принято, см. `docs/DECISIONS.md`.
- Пять картинок ХабароПедии из списка ниже игра не показывает вообще: на них нет ссылки ни в одном рулсете.
  Рисовать их HD-версии смысла нет.
