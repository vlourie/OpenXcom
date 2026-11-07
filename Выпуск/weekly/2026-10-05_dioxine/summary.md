# OXCE-HD: what changed this week (29 Sep - 5 Oct 2026)

All of it is picture, interface or tooling: game rules, rolls and saves are untouched, and every visual has an off switch.

## Globe and interception

- Craft and UFOs on the globe are top-down outlines instead of dots. Own craft are light blue, nose along the course. A UFO becomes an outline once a hyper-wave decoder has read it, coloured by its crew's race, with an edge for its state (red flying, green landed, white crashed) and a white dot at the exact position. Over two dozen craft that used to fly sideways or backwards (Drakkar, Thunderhorse, Guild Fighter, choppers, trucks, bikes, the zeppelin) now fly nose first, each checked against its battle map.
- In the dogfight the UFO is an outline too: a white flash when hit, blue while the shield holds. Hunter-killers face you while attacking and turn away when they run.
- Radars: three looks. Classic circles, one joint detection area with a shared edge, or the sweep: a wave from each base on every detection cycle and a turning beam on craft outside base coverage.
- Interception window: the hit chance above each weapon and, in red, the UFO's chance to hit you, counted exactly as the game rolls it.
- Loadout icons before the craft name in the interception window and the craft list. The craft window on the globe uses the craft's own Ufopaedia picture as its background.

## Battle

- New button panel: dark tiles with redrawn pictograms. A brass version in the spirit of the original is done and ships with the next build.
- The reticle takes the colour of the shot's damage type (the Ufopaedia colours). 14 new reticle styles.
- Blast area preview: aim a launcher or ready a grenade, and the tiles the blast, smoke or gas would reach are tinted in the damage colour, densest at the centre. Walls cut it as a real blast would.
- Fire and smoke burn at their own pace on every tile instead of pulsing as a grid, with speed sliders for both.
- Animated HD icons over knocked-out bodies, and a short cinematic close-up when the last enemy falls (any key skips it).
- Gentle mode for players sensitive to flashing and jumpy pictures: even pace, slow shots, a camera that glides instead of jumping, an amber arrow towards a reaction shooter instead of a camera jump.

## Characters

- The engine side for fully painted HD units is done: HD frames keep their own colours, and tile lighting plus the mod's recolour scripts (energy shields, hit flashes) apply on top without blocky base-grid artefacts.
- The first whole-figure HD character, the Government Agent with an HD AK-47, is in the pilot stage (see the screenshots). It is the template for the rest of the roster.
- "Piratez tanks: turning turret" got HD frames of its own, so there is no second painted-on gun any more.

## Weapons and inventory

- Inventory pictures can be HD now; the AK-47 is in the mod as the quality benchmark.
- A test set of 20 weapons (bow, Panzerfaust, MP40, Tommy, coach gun, police shotgun, Colt, Skorpion and more) was rendered from the originals with automatic checks of proportions, parts and joints against the 32x48 sprite. It is in review and goes into the mod only after the pick.

## Sound effects (in progress, nothing shipped yet)

- Census of what the game plays: 638 battle and 75 geoscape sounds, each with its length.
- Engine constraint found: random sound variants are picked through the battle RNG, so a mod cannot add variants without changing the rolls. A separate engine layer for extra variants was chosen.
- Three generators tried on 10 typical sounds (metal step, pistol, laser rifle, knife hit, grenade, alien roar, scream, ricochet, reload, sliding door), three takes each, lengths taken from the in-game references, with a listening page to compare: MMAudio, Stable Audio Open, Stable Audio 3 Small SFX. Lesson: very short sounds must be generated longer and trimmed, or they come out as noise.
- Next: pick the generator, add the layer, then the first variants.

## Launcher and mods, briefly

- Launcher: builds (separate settings sets for the same game), voice rooms with push-to-talk for everyone, and a Game components wizard with the add-ons "Piratez tanks: turning turret", "Apple Processing" and "Kisya and Brysya Sisters".
- HD interface fonts moved into their own mod, "HD core: fonts".
- Fixes: a battle from the same save starts the same way every time, no more hang at the very end of loading, and "Do not follow projectiles" at value 2 works as described.

## Screenshots

1. 01_globe_radar_sweep.png - globe, joint radar area with the sweep wave.
2. 02_battle_hd_agent_ak.png - battle: HD Government Agent with an HD AK-47 on HD terrain, dark panel.
3. 03_hd_agent_closeup.png - close-up of the HD agent on the map.
4. 04_battle_panel_brass_night.png - brass battle panel, night jungle.
5. 05_inventory_hd_ak.png - inventory with the HD AK-47.
6. 06_reticle_damage_colour.png - reticle in the damage colour.
7. 07_blast_area_preview.png - blast area preview on the aimed tile.
8. 08_weapons_hd_test_set.png - eight of the 20 test weapons: original x8, HD pack, in game 1:1.
9. 09_globe_craft_outlines.png - craft and UFO outlines on the globe at 2x (own craft light blue, UFO with the red "flying" edge, white dot at the exact position); 09b_globe_craft_outlines_full.png is the full frame.
