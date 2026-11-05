## How we make the art

- **The mechanics stay the same.** Only the picture changes: tiles, walkability, cover, numbers and saves are those of the original. At the smallest scale the game must draw a frame byte for byte as the classic does — this is checked before every change to the drawing.
- **Drawn on our own graphics card.** New frames come from local models: repainting after the original, upscaling that keeps the drawing, photo bases. A finished frame is fitted to the exact silhouette of the original, so there are no jagged edges, halos or shifted details.
- **Every batch is checked against the original.** Before a release: sheets of "original next to new", a shape check and a choice between several variants. If the new one is worse, the old one stays.
- **You point, we fix.** Found a blurry or shifted picture? Open a ticket on the site or send a report with F8 straight from the game. Fixes for your tickets come out in the updates and are marked in "What's new".
- **Updates come regularly, in small portions.** Each has its "What's new", and the whole history is in the launcher's "Updates" tab and on the site.

## Done

- **Walls and solid blocks** — every wall has a clean edge exactly along the original silhouette: brick, boards, stone, concrete, rock, ice, base sections, UFO and ship walls, broken walls and doors. Hills, dunes and slopes fit together without seams or a grid, and hill slopes are covered with the same grass as the flat ground. Lights on consoles and monitors blink on their own, not with the whole wall; house windows are nearly transparent.
- **Ships, UFOs and vehicles** — hulls (about 1200 frames) and the Mi-24 helicopter repainted along the original silhouette.
- **Floors and ground** — streets, sea, swamps, snow, sand, forests, base and ship plating and decks: sharper and without a dark grid at the tile joins. Flat floors have a clean tile edge without jaggies, both on top and at the bottom. Snow maps, jungle and tropics, asphalt and the sand around a crashed plane were redrawn.
- **Map objects** — about 250 new pictures of furniture, devices and small things, plus their copies in other sets. Rails, cash machines, stairs, doors, litter, the fuel pump, cabbage beds and much more were redrawn after your tickets.
- **Plants** — trees, bushes, vines, stumps and grass are drawn whole and cut into tiles, without seams.
- **Inventory** — about 2100 items in high resolution: weapons, ammunition, medicine, grenades, armour, documents, parts, treasures, psi items, prisoners and bodies. A clean outline without jaggies, with the shape and colours of the original. Weapons in soldiers' hands and items on the floor are smooth now too.
- **Interface** — battle panels to choose from (including "Ship's brass" and four more drawn themes), globe radars, a cursor in the colour of the damage with a flight arc, the area of effect, path numbers in a crisp font, high-resolution fonts (a separate mod "HD core: fonts"). Your own colour and look for window buttons, button text, and a separate theme for each game screen. Screen backgrounds now feature our crew, the six heroines. A soldier's face on the battle bar is drawn in high resolution.
- **Battle effects** — optional in the HD settings: billowing smoke, tongues of fire, flash light, shadows under soldiers and items, corner shading, bloody footprints, blood colour by creature kind, terrain beyond the map edge, the battlefield border.
- **Living base** — buildings are redrawn and come alive: water, radars, turrets, hangar lights, conveyor belts with parts and engineers, day and night by local time. When a craft leaves or lands, the camera drops to its hangar and a short scene plays.
- **UFOpaedia** — about 1500 high-resolution illustrations; buildings show the same picture that stands on your base. Some pictures were redrawn after review remarks.
- **Environment colours** — missions with their own tint (Styx, heat, magma) tint HD the same way as the classic art; inventory items take the weather tint too.
- **Output through the graphics card** — optional in the HD settings: the card draws the globe, the base and the battle map.

## Under way

- **Inventory, second layer** — more detailed weapon pictures, starting with the most common; the first layer is already with you.
- **Finishing maps after player tickets** — frames you complained about are redrawn and fitted to the original.
- **Floors and plants** — the next batches, by the maps met most often: caves, cities, the port, shopping quarters, roads.
- **Living base** — the remaining buildings come alive one by one.

## Next in the art

1. **Ground in groups:** water and shores → earth and sand → forest and jungle → indoor floors, roofs and ceilings. Windows and doors with a strict check of the openings.
2. **Roads:** kerbs and stone texture.
3. **Items in hand and on the floor** — properly drawn, not just upscaled; a stage of its own.
4. **Units.** Soldiers and enemies are only upscaled from the original so far. The soldier doll can already be built from HD layers (body, head, each item) — the layer pictures themselves come in a separate release. Drawn units start with a pilot set; if the pilot passes the check, the most common enemies follow.
5. **Small things:** creature flashes and effects, the remaining jungle rock blocks, posters.
6. **Vanilla X-COM (UFO Defense)** — after Piratez: its sets are different and get a check of their own.

## Besides the art

- **Tactical AI (BetterAI, experimental)** — a screen of its own in the HD settings, off by default: then the enemy behaves as in plain OXCE. When on, it fixes AI errors: a fleeing enemy no longer picks a tile closer to a soldier, does not hold a path to an unreachable point, searches the whole module when a base is attacked and remembers who shot at it. A separate "AI3" mode stops it wasting shots that have no chance to hurt.
- **Building collapse** — optional in the HD settings. Works on hundreds of map sections already: houses, trees, posts. What falls leaves rubble: heaps of debris in the colour of the terrain, felled trunks, brushwood, dust; rubble gives cover but can hurt a soldier. The aim shows tiles where something may fall. New sections are added in batches, each checked.
- **Sound** — soldier voices: every kind of soldier has its own voice; all 157 voices have about a hundred lines for selecting a soldier and ordering a move, so they hardly repeat during a battle; voices have their own volume slider. Footsteps sound by footwear and by floor material. You can put your own music into the "music" folder.
- **Russian names** — a separate mod "Russian names for Piratez": up to 2500 first and last names for every people and race, each in its own spirit. It switches on by itself with the Russian language.
- **Comfort in battle and on the base** — map zoom with Ctrl + wheel, base-switching arrows on screens (also with the soldier-switch keys), confirmation of large buys and sales, transfer cost between bases, highlighting of matching ammunition, forwarding loot to other bases, a research time estimate and a multi-point ship route (optional in the settings).
- **Launcher and site** — the history of every update and this roadmap; the launcher announces new versions and new mods by itself, updates in smaller archives and goes to the tray while you play. It has a "Community" section with voice and a "Messages" tab for private text chat. "New build" lets you pick other games from mod.io too. The game shows an "Update available" banner, which can be turned off in the HD settings. The site states which version we play (X-Piratez on the OXCE-HD engine) and describes the mods; the site's main page shows anonymous statistics, which can be switched off with a checkbox in the launcher settings.
- **Planned** (no dates) — voice and messages will become IRC-like: text channels next to voice and a list of participants; an in-game notification about new messages; a refreshed look of the launcher.

## What will not happen

- Rules, balance and the save format do not change. The AI and building collapse only behind a switch.
- The classic drawing stays: any HD layer can be turned off.
- Art that is worse than before is not released just because it is newer.
