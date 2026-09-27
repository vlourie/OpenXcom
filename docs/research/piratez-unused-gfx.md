# X-Piratez: unused graphics files

Built 2026-09-26 by `tools/gfx_unused.py` against the installed game (`Пиратки/Dioxine_XPiratez`, mods active in `user/options.cfg`: xcom1 master, piratez, XPZ_EX_RU-patch, piratezRusNames, piratezCitiesLore, piratez_tank_turret, intro_voice, hd). Machine-readable list: `census/gfx_unused.tsv`.

Regenerate:

```
tools/hdart/.venv/Scripts/python.exe tools/gfx_unused.py
```

## What counts as used

Rulesets are YAML-parsed (comments ignored) the way the engine resolves them:

- a path string in any field (`extraSprites` `files` / `fileSingle`, cutscene images, ...), case-insensitive like FileMap;
- a path ending in `/` loads every image directly in that folder (`ExtraSprites::loadSurfaceSet`);
- a name in any `mapDataSets` means `TERRAIN/<name>.PCK` + `.TAB`;
- fonts: only `Language/<fontName>` is read, from the mod that loads last; its `images[].file` entries are used.

Scanned: 15,684 graphics files in Piratez (9,505 png, 4,929 gif, 625 pck + 625 tab), 55 rulesets, 193,717 extraSprites frame writes, 610 terrain sets named in mapDataSets. Every file marked **unused** was also raw-grepped across all install texts (comments included): the only hits are commented-out font lines.

## Summary

| Status | Files | Size, KB | Meaning |
|---|---|---|---|
| unused | 76 | 945.5 | nothing loads the file, in any configuration of this install |
| overwritten | 2 | 22.3 | loaded into a sprite frame that a later entry writes again |
| shadowed | 65 | 380.0 | a later mod supplies the same path; the Piratez copy is used only without that mod |

## 1. Unused (76 files)

### Fonts: 7

| File | KB | Note |
|---|---|---|
| `Language/AmigaFontBig.png` | 7.0 | only in commented-out `file:` lines, or in no font .dat at all |
| `Language/AmigaFontBigBloax.gif` | 9.9 | only in commented-out `file:` lines, or in no font .dat at all |
| `Language/AmigaFontSmallDio.png` | 6.8 | only in commented-out `file:` lines, or in no font .dat at all |
| `Language/FontGeoSmall_ko.png` | 23.1 | only in commented-out `file:` lines, or in no font .dat at all |
| `Language/FontSmallBloax.gif` | 4.5 | only in commented-out `file:` lines, or in no font .dat at all |
| `Language/FontSmallOAK.png` | 4.7 | only in commented-out `file:` lines, or in no font .dat at all |
| `Language/XPFontGeoSmall_Ko.png` | 0.4 | only in commented-out `file:` lines, or in no font .dat at all |

### Resources: 38

| File | KB | Note |
|---|---|---|
| `Resources/Armors/Gals/Admiral/Admiral_Main.gif` | 2.7 | no reference in any ruleset |
| `Resources/Armors/Gals/Misc/Armbands_Low.gif` | 1.2 | no reference in any ruleset |
| `Resources/Armors/Gals/Pirate/Pirate_Pants.gif` | 1.7 | no reference in any ruleset |
| `Resources/Armors/Gals/Smokey/Mesh_Mask_Held.gif` | 1.4 | no reference in any ruleset |
| `Resources/Armors/Gals/Smokey/Smokey_Mask_Held.gif` | 1.3 | no reference in any ruleset |
| `Resources/Armors/Nekomimi/Dreamwalker/Ankha_body (1).png` | 6.1 | no reference in any ruleset |
| `Resources/Armors/Nekomimi/Spaceguardian/SG_Body.png` | 5.7 | no reference in any ruleset |
| `Resources/Armors/Nekomimi/Spaceguardian/SG_Helm.png` | 4.4 | no reference in any ruleset |
| `Resources/Armors/Nekomimi/Spaceguardian/SG_Tail.png` | 4.5 | no reference in any ruleset |
| `Resources/Armors/Nekomimi/Spacetrooper/ST_Body.png` | 5.6 | no reference in any ruleset |
| `Resources/Armors/Nekomimi/Spacetrooper/ST_Helm.png` | 4.4 | no reference in any ruleset |
| `Resources/Armors/Nekomimi/Spacetrooper/ST_Tail.png` | 4.5 | no reference in any ruleset |
| `Resources/Backgrounds/EQP_Black.gif` | 1.2 | no reference in any ruleset |
| `Resources/Backgrounds/Medusa_BCK.png` | 18.2 | no reference in any ruleset |
| `Resources/Backgrounds/PLUNDER.gif` | 18.2 | no reference in any ruleset |
| `Resources/Blanks/Wolv_LH_Empty.png` | 3.9 | no reference in any ruleset |
| `Resources/Body_X/Doomguy_Inv.png` | 6.1 | no reference in any ruleset |
| `Resources/Cheese_Bag.png` | 4.1 | no reference in any ruleset |
| `Resources/CraftWpnPed/MedGunAAPed.gif` | 2.6 | no reference in any ruleset |
| `Resources/Cutscenes/Intro_00Splash.png` | 15.2 | no reference in any ruleset; same path also in XPZ_EX_RU-patch; the RU patch copy differs |
| `Resources/FLOOROB/FloorFurs.gif` | 0.9 | no reference in any ruleset |
| `Resources/FLOOROB/FloorStaffMind.png` | 3.6 | no reference in any ruleset |
| `Resources/Globe/HD7Close.png` | 4.1 | no reference in any ruleset |
| `Resources/Globe/HD7Far.png` | 4.0 | no reference in any ruleset |
| `Resources/Globe/HD7Med.png` | 4.2 | no reference in any ruleset |
| `Resources/Globe/JungleFar.png` | 3.8 | no reference in any ruleset |
| `Resources/Pedia/C_017_CPAL.png` | 49.2 | no reference in any ruleset |
| `Resources/Pedia/Golden_Prince_AI1_CPAL.png` | 49.5 | no reference in any ruleset |
| `Resources/Pedia/Milking.png` | 36.0 | no reference in any ruleset |
| `Resources/Pedia/PirateRest.png` | 38.4 | no reference in any ruleset |
| `Resources/Pedia/UPed_Ghost_Gal.gif` | 2.3 | no reference in any ruleset |
| `Resources/Pedia/Witches2.png` | 41.5 | no reference in any ruleset |
| `Resources/Planes/DrakkarDogfight.gif` | 1.0 | no reference in any ruleset |
| `Resources/Planes/DrakkarMinimised.gif` | 1.0 | no reference in any ruleset |
| `Resources/Porn_1.png` | 4.5 | no reference in any ruleset |
| `Resources/Rocket_Launcher_Old2.gif` | 1.5 | no reference in any ruleset |
| `Resources/Sprites/MRC_7BAK.png` | 20.1 | no reference in any ruleset |
| `Resources/UnitUI/Shock.png` | 3.6 | no reference in any ruleset |

### Terrain sets (PCK + TAB): 15 sets, 30 files

Name absent from every `mapDataSets`. The matching `.MCD` (and any `MAPS/`) are dead too, but they are not graphics.

| Set | PCK+TAB, KB |
|---|---|
| `TERRAIN/C_EXT_NOSE_BUMPLESS_PRPL` | 22.7 |
| `TERRAIN/C_EXT_ROOFBITS_SILVER` | 14.9 |
| `TERRAIN/CAVEPINK` | 23.5 |
| `TERRAIN/CAVERED` | 23.5 |
| `TERRAIN/DUSKURBAN` | 53.0 |
| `TERRAIN/MILURBAN` | 49.5 |
| `TERRAIN/MUICE` | 44.6 |
| `TERRAIN/U_BASEGOLD` | 39.0 |
| `TERRAIN/U_BITSN` | 3.1 |
| `TERRAIN/U_DISEC3GOLD` | 19.8 |
| `TERRAIN/U_EXT` | 54.7 |
| `TERRAIN/U_EXT_ROOF` | 54.7 |
| `TERRAIN/U_PODSGOLD` | 14.9 |
| `TERRAIN/U_WALL` | 47.0 |
| `TERRAIN/U_WALL02GOLD` | 27.1 |

### Mod root: 1

| File | KB | Note |
|---|---|---|
| `splash.png` | 15.2 | engine never loads it (no `splash` in src/); byte-identical to `Resources/Cutscenes/Intro_00Splash.png`. May be read by an external launcher |

## 2. Overwritten (2 files)

| File | KB | Why |
|---|---|---|
| `Resources/Backgrounds/EQP_TONED.gif` | 20.8 | `BACK08.SCR` frame 0 is rewritten later by `resources/backgrounds/eqp_brown2x4.gif` (XPZ_EX_RU-patch:Ruleset/EX_extraSprites.rul:6) |
| `Resources/Flags/National/31_XF_FLAG.png` | 1.5 | `Flag731` frame 0 is rewritten later by `resources/flags/national/12_kcn_flag.png` (piratezRusNames:Ruleset/Piratez_Resources.rul:25) |

## 3. Shadowed in this install (65 files)

Not dead: an English install without the RU patch uses them. Deleting any of these breaks that configuration.

| File | KB | By |
|---|---|---|
| `Language/AmigaFontBigBloaxEX.gif` | 10.3 | font sheet of Piratez's own `AmigaFont.dat`; the game reads `XPZ_EX_RU-patch`'s copy instead |
| `Language/FontGeoBig_ko.png` | 21.6 | font sheet of Piratez's own `AmigaFont.dat`; the game reads `XPZ_EX_RU-patch`'s copy instead |
| `Language/FontSmallBloaxEX.gif` | 4.7 | font sheet of Piratez's own `AmigaFont.dat`; the game reads `XPZ_EX_RU-patch`'s copy instead |
| `Language/XPZFontGeoSmall_ko.png` | 0.4 | font sheet of Piratez's own `AmigaFont.dat`; the game reads `XPZ_EX_RU-patch`'s copy instead |
| `Resources/14mmRound.png` | 3.6 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/Backgrounds/Back_08b.gif` | 9.3 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/Backgrounds/BackOutfit.gif` | 11.3 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/Backgrounds/Nazi_Bck.png` | 16.4 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/Body_X/BlackKnight_Inv.png` | 6.0 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/Body_X/HANABU_Inv.png` | 7.1 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/Body_X/Humanist_Leader.gif` | 2.6 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/Body_X/Humanist_Stormtrooper.gif` | 2.5 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/Body_X/MercenaryUltramarine_Armor.png` | 7.3 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/Camo_Cloth.png` | 3.7 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/Corpses/MONGORN_b.png` | 4.3 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/Corpses/NAZ_9_b.png` | 4.2 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/Cutscenes/Intro_00.png` | 15.5 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/Fist_Big.png` | 3.8 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/Fist_Saint.png` | 3.9 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/FLOOROB/floor_hbolter.gif` | 1.0 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/FLOOROB/floor_hbolter_case.gif` | 0.9 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/FLOOROB/floor_Megavolt.png` | 3.6 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/FLOOROB/FloorBand.gif` | 0.9 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/FLOOROB/FloorBriefcase.gif` | 0.9 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/FLOOROB/FloorHammer.gif` | 0.9 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/FLOOROB/FloorLootSmall.gif` | 0.9 | overridden by the same path in `piratezCitiesLore` (loads later) |
| `Resources/FLOOROB/FloorMedipack.gif` | 0.9 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/FLOOROB/FloorMinigun2.gif` | 1.0 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/FLOOROB/FloorSHvyRifle.gif` | 0.9 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/Fuel_Capsule.gif` | 1.5 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/HANDOB/Bozar.png` | 4.0 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/HANDOB/Hammer.png` | 1.3 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/HANDOB/hbolter_h.png` | 2.2 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/HANDOB/Medipack.png` | 1.1 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/HANDOB/Megavolt.png` | 4.2 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/HANDOB/STOP_SIGN_H.gif` | 1.5 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/HANDOB/ThrowingAxesH.png` | 3.7 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/hbolter_case.gif` | 1.1 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/HEAVYBOLTER.gif` | 1.7 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/HellPistol.gif` | 1.0 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/HSMG_Clip.gif` | 0.9 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/Iron_Rod.gif` | 1.0 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/Megavolt.png` | 3.9 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/Mrrshan_Cell.png` | 1.3 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/Mrrshan_Cell2.png` | 3.7 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/Pedia/Moon_Nazi_Base.png` | 21.0 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/Pedia/MoonNazis.png` | 29.1 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/Pedia/Ultramarine.png` | 9.0 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/Pedia/UPed_Black_Knight.png` | 6.4 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/Pedia/UPed_Hanabu.png` | 7.4 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/Pedia/UPed_Humanist_Leader.gif` | 2.5 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/Pedia/UPed_Humanist_Stormtrooper.gif` | 2.6 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/Pedia/WastelandPriestess_FG_176.png` | 46.0 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/Pedia/X04_Ped.gif` | 16.6 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/Pistol_Clip.gif` | 0.9 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/Pistol_Clip_Adv.gif` | 0.9 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/Pistol_Clip_Sly.gif` | 0.9 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/SHvy_Rifle.gif` | 1.1 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/SHvy_Rifle_Ammo.gif` | 1.0 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/Slugthrower_Shells_Chem.png` | 3.6 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/SmallFile.png` | 3.6 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/Sprites/HANABU.png` | 10.5 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/Sprites/NAZ_9.png` | 20.3 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/Sprites/TIGER_TURRET.png` | 8.5 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |
| `Resources/UnitUI/Burn.png` | 3.6 | overridden by the same path in `XPZ_EX_RU-patch` (loads later) |

## Not covered

- **Unused frames inside used sets.** A file loaded into `BIGOBS.PCK` frame N counts as used even if no item's `bigSprite` points at N. That needs a pass over item and armor sprite indices with mod offsets (`Mod::getOffset`).
- **Terrain sets named only by deleted or unreachable terrains.** A set listed in the `mapDataSets` of a terrain that no deployment or globe texture uses still counts as used here.
- **Frame overwrites across mods.** Only checked within one mod and for single images: other mods' sprite indices are shifted by their own offset.
- **HD pack** (`user/mods/hd`): not in scope; the engine already logs a summary of `hd/UI` pictures with no match.
