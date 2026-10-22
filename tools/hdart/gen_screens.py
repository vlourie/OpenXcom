# -*- coding: utf-8 -*-
r"""Фоны экранов интерфейса по темам: Qwen-Image-2.1 рисует с нуля, как арт лаунчера (gen_promo.py).

Одна тема - одна сцена на группу экранов (исследования, производство, бойцы, рынок...); какой
экран к какой теме - SCREENS ниже, имена экранов - разделы interfaces рулсетов. Картинка стоит под
плотным текстом окна, поэтому промпт просит крупные спокойные формы, глубокую тень и никакой мелкой
пестроты, а свет и металл - как у нарисованной панели боя (латунь, клёпаные листы, тёплый свет ламп).

Два шага, потому что арт утверждает Vitali (art-approval-first):

1. draw - по каждой теме несколько вариантов в art/ui_screens/<тема>/ и лист выбора <тема>_sheet.jpg:
       tools\hdart\.venv-qwen21\Scripts\python.exe tools\hdart\gen_screens.py draw --theme research,crew --seeds 3
2. install - выбранные варианты в обе копии мода hd (hd/UI/screens/<тема>.png + screens.txt):
       tools\hdart\.venv\Scripts\python.exe tools\hdart\gen_screens.py install --pick research=1,crew=2
   приглушение, стекло под текстом и рамку из металла панели боя делает движок (HdScreens), не файл.

Только через очередь видеокарты (tools/gpuq.py). Запускать с PYTHONIOENCODING=utf-8 (R-001).
"""
import argparse
import os
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "art", "ui_screens")
sys.path.insert(0, os.path.dirname(__file__))

# свет и материал - как у панели боя: латунь, клёпаное железо, тёплые лампы в темноте
STYLE = ("Painted illustration in the style of a 1990s PC strategy game box cover, gritty retro science "
         "fiction, confident brushwork. The interior of a battered space-pirate airship and hideout built from "
         "heavy riveted brass and dark iron plates, warm amber lamp light and deep shadows, a touch of acid lime "
         "green from alien tech. ")
# под картинкой - списки и цифры во всё окно: она должна быть настроением, а не сюжетом
CALM = ("Composition for a background behind dense text: big simple shapes, low contrast, most of the picture "
        "is soft deep shadow, no small busy detail, no bright spots in the middle, the subject is large and "
        "placed toward one side, slightly out of focus like a cinematic backdrop. ")
NEGATIVE = ("text, letters, words, numbers, caption, title, logo, watermark, signature, frame, border, "
            "screens with writing, blurry mess, low resolution, jpeg artifacts, deformed hands, extra fingers, "
            "extra limbs, duplicated faces, clones, nudity, cleavage, bare midriff, lingerie, pin-up, glamour "
            "pose, gore, photograph, plastic 3d render, high contrast, busy pattern, bright white areas")

THEMES = {
    "research": "A dim laboratory in the hold of a pirate ship: a half-dismantled alien device glowing faint lime "
                "green on a brass workbench, glass jars and tubes, a magnifying lamp on an arm. A pirate woman "
                "scientist in a patched lab coat and goggles studies it from the right side, her face lit from below.",
    # первые три варианта поставили работника в центр - с четвёртого станок и человек прижаты к правому краю
    "manufacture": "A cramped pirate workshop seen from the side: the left two thirds of the picture are dark empty "
                   "iron walls with hanging chains and tool racks fading into shadow; at the far right edge a heavy "
                   "lathe and an anvil, a pirate mechanic woman in a leather apron and welding mask works there in "
                   "profile, a small soft shower of orange sparks, smoke drifting in the lamp light.",
    "crew": "The crew quarters of a pirate airship: bunks of riveted iron, hammocks, lockers with stickers, a long "
            "table with mugs and cards. Several mutant pirate women in practical patched clothing rest and talk in "
            "the background shadows on the left and right, faces half in shadow, relaxed and tough.",
    "market": "A smugglers' black market in a rock cavern: stalls of crates and barrels, hanging lanterns, alien "
              "gadgets and improvised guns on racks, a hooded trader with a scarred face behind a counter on the "
              "right side, coins and a ledger on the counter.",
    "hangar": "A huge dark hangar carved into rock: a battered patched-together pirate gunship stands on the pad, "
              "fuel hoses and gantries, work lights cone down through haze, a pirate woman pilot in a flight jacket "
              "with goggles leans on a landing strut at the right.",
    "bridge": "The bridge of a pirate airship at night: a brass steering wheel and levers, a round radar screen "
              "glowing faint lime green, wide windows showing a dark sky with a distant alien saucer and its "
              "running lights, the pilot's chair in silhouette.",
    "training": "A pirate training hall in the ship's hold: a punching bag of patched leather hanging on a chain, "
                "a sparring ring of ropes and iron posts, rusty weights and a target dummy riddled with holes, a tough "
                "pirate woman in a sleeveless shirt and cargo trousers wraps her fists at the right side.",
    "memorial": "A quiet memorial niche in the hideout: a riveted brass plate wall with rows of engraved names too "
                "small to read, dog tags and a battered pirate hat hanging on hooks, candles and one dim amber lamp, "
                "a bottle and an empty glass on a ledge, deep shadow all around.",
    "armory": "A pirate armory: racks of improvised rifles and blades on dark iron walls, ammunition crates, a "
              "suit of patched combat armour on a stand at the right, a workbench with a disassembled gun, an alien "
              "weapon glowing faint lime green in a locked cage.",
    "stores": "A cavernous cargo hold of a pirate hideout: stacks of crates, barrels and sacks strapped with nets "
              "receding into darkness, a chain hoist and a hook, a few crates marked with alien glyphs glowing faint "
              "lime, lamp light falling on the stacks at the right side.",
    "pursuit": "Night sky seen through the riveted brass frame of a pirate gunship cockpit: a glowing alien saucer "
               "flying away into the clouds on the right, faint lime engine trails, the cockpit gunsight and "
               "gauges dark in the foreground, moonlight on the clouds below.",
    "defense": "The blast door of a pirate hideout under attack: a massive riveted iron door half open, red "
               "alarm lamps and smoke, sandbags and a mounted heavy gun at the right side, sparks and the glow of "
               "something alien beyond the door, deep shadow on the left.",
    "debriefing": "After the battle at dawn: a battered pirate dropship on a scorched field, smoke rising, crates "
                  "of salvaged alien loot glowing faint lime being carried aboard, tired pirate women in patched "
                  "combat gear in silhouette on the right side against the warm low sun.",
    "facilities": "Construction inside a rock hideout: scaffolding of iron beams, a half-built brass corridor "
                  "module hanging from a crane hook, welding light on the right side, cables and lamps strung "
                  "across the cavern, plans pinned to a crate.",
    "menus": "The captain's cabin of a pirate airship: a heavy desk with a chart, a brass sextant and a bottle of "
             "rum, a round porthole showing a dark sky, a captain's coat and hat on a hook at the right, an oil "
             "lamp giving warm light, deep shadow.",
    # второй заход 22.10: экраны, мимо которых шли темы (главное меню, окна геоскейпа и педии, окна боя)
    "mainmenu": "The deck of a battered pirate airship at dusk high above burning clouds: on the left a tough "
                "mutant pirate woman captain in a long coat with a cutlass, on the right two pirate women in "
                "patched combat gear with improvised rifles, a glowing alien saucer far away in the stormy sky "
                "between them, brass railings, ropes and a fluttering black flag.",
    "geoscape": "A pirate navigator's chart room: a big brass-ringed globe of the Earth glowing faintly with lime "
                "markers stands on a round chart table, old maps pinned to riveted iron walls, dividers and an "
                "oil lamp, a navigator woman in a long coat leans over the globe at the right side in shadow.",
    "pedia": "The archive of a pirate hideout: tall iron shelves of battered books, folders and data cassettes "
             "receding into darkness, specimen jars with alien parts glowing faint lime, a reading lamp over a "
             "desk with a thick open illustrated codex at the right side.",
    "battle": "A field command post inside a ruined building at night during a raid: a field radio with glowing "
              "dials, a tactical map spread on an ammunition crate held down by a pistol and a canteen, rifles "
              "leaning on a broken wall, distant fire glow through a shattered window on the right.",
    "briefing": "The cargo hold of a pirate dropship in flight before landing: rows of fold-down seats along "
                "riveted iron walls, harnesses and racked weapons, a red jump lamp glowing over the closed ramp at "
                "the right, pirate women in patched combat gear sitting in shadow checking their guns.",
    "hidden": "A dark ruined street at night in drifting fog: the silhouette of an alien creeping between broken "
              "walls far away on the right, a faint lime glow of its eyes, moonlight on wet rubble, everything "
              "still and tense, almost the whole picture in deep shadow.",
    "alert": "A human town burning at night seen from a hill: columns of smoke lit orange from below, an alien "
             "saucer hovering low over the roofs on the right with faint lime beams, tiny fleeing silhouettes, "
             "the searchlight of a distant pirate airship crossing the sky.",
}

# главное меню - обложка игры: под ним только кнопки, сюжет может быть ярче и крупнее, середина - небо под кнопки
BOLD = {"mainmenu"}
COVER = ("Box cover composition: the characters stand on the left and right thirds, the centre of the picture is "
         "open darker sky where the menu buttons will sit, dramatic warm rim light, no small busy detail. ")

# экраны тем (разделы interfaces); пилот - первые шесть тем, остальные темы - после выбора стиля
SCREENS = {
    "research": "allocateResearch geoResearch geoResearchComplete geoResearchRequired globalResearchDiary "
                "globalResearchMenu researchMenu selectNewResearch techTreeSelect techTreeViewer tests "
                "manageContainment globalContainmentMenu statsForNerds",
    "manufacture": "allocateManufacture geoManufacture geoManufactureComplete globalManufactureMenu "
                   "manufactureInfo manufactureMenu selectNewManufacture",
    "crew": "soldierList craftSoldiers craftPilots craftPilotsSelect soldierDiary soldierDiaryPerformance "
            "soldierDiaryMission soldierDiaryLight soldierRank promotions commendations commendationsLate "
            "sackSoldier soldierAvatar soldierVoice soldierBonus",
    "market": "buyMenu sellMenu costsInfo fundingWindow monthlyReport",
    "hangar": "craftInfo craftSelect craftWeapons craftArmor geoNewCraft",
    # craftError - сообщения геоскейпа о судах (НЛО начал охоту, нет топлива, нет экипажа)
    "bridge": "intercept geoCraft craftPatrol confirmDestination confirmCydonia lowFuel ufoTracker targetInfo "
              "craftPilotError craftError",
    "training": "martialTraining allocateMartial psiTraining allocatePsi trainingFinished soldierTransformation "
                "transformationList soldierTransform",
    "memorial": "soldierMemorial endGameStatistics",
    "armory": "craftEquipment craftEquipmentLoad craftEquipmentSave soldierArmor cannotReequip",
    "stores": "storesInfo itemLocations itemsArriving transferBaseSelect transferConfirm transferInfo transferMenu "
              "geoNewItem dependencyTree",
    "pursuit": "UFOInfo UFOLost multipleTargets dogfightInfo dogfightExperience confirmLanding alienBase",
    "defense": "baseDefense baseDefense_geo baseDestroyed",
    "debriefing": "debriefing",
    "facilities": "selectFacility placeFacility dismantleFacility geoNewFacility baseNaming",
    "menus": "optionsMenu modsMenu newBattleMenu newGameMenu noteMenu oxceLinks pauseMenu saveMenus "
             "selectMusicTrack",
    "mainmenu": "mainMenu",
    # окна над глобусом: бросить игру, новая база, курс
    "geoscape": "geoscape",
    # меню педии (списки разделов и статей); сами статьи - своя графика, не тема
    "pedia": "ufopaedia",
    # окна боя на TAC00.SCR (выход с карты, итоги опыта, комплекты снаряжения, дневник хода): имя даёт движок
    "battle": "battlescape",
    "briefing": "briefing",
    # «скрытое движение»: заставка хода и сообщение на карте
    "hidden": "nextTurn hiddenMovement",
    # тревога о миссии (погром, абордаж)
    "alert": "terrorSite",
}

# Героини - шесть беглянок M1-M6 (лор и внешность: F:\AIStudio\EscapeScene\CHARACTERS_AND_SCENE.md, лица -
# art/cast/M<N>_face.png из cast_faces.py). Без них модель рисовала на всех картинках одно и то же лицо.
# Роль по характеру: Север - лидер (капитан, курс, брифинг), Искра - дерзкая драчунья, Шпилька - вскрывает
# замки (механик), Базальт - самая сильная, Рысь - быстрая, замечает опасность (пилот), Тихая - точная (учёная).
# Тема -> героини по порядку опор (Picture 1, 2, 3) и сцена, где они названы по именам.
CAST = {
    "research": ([6], "A dim laboratory in the hold of a pirate ship: a half-dismantled alien device glowing faint "
                      "lime green on a brass workbench, glass jars and tubes, a magnifying lamp on an arm. Tikhaya, "
                      "the woman from Picture 1, works at the right side in a patched lab coat over dark work "
                      "clothes, goggles pushed up on her forehead, her black braid over one shoulder, her face lit "
                      "from below by the device, calm and focused."),
    "manufacture": ([3], "A cramped pirate workshop seen from the side: the left two thirds of the picture are dark "
                         "empty iron walls with hanging chains and tool racks fading into shadow; at the far right "
                         "edge a heavy lathe and an anvil. Shpilka, the woman from Picture 1, a mechanic in a leather "
                         "apron over a work shirt with rolled sleeves, a welding mask pushed up on her head, her "
                         "chestnut hair held by a plain metal bobby pin, works there in three-quarter view, a small "
                         "soft shower of orange sparks, smoke drifting in the lamp light."),
    "crew": ([2, 4, 5], "The crew quarters of a pirate airship: bunks of riveted iron, hammocks, lockers with "
                        "stickers, a long table with mugs and cards. Three pirate women rest there in practical "
                        "patched clothing: on the left Iskra, the woman from Picture 1, sits on the table edge "
                        "laughing; in the back Bazalt, the woman from Picture 2, the tallest and strongest, leans on "
                        "a bunk with crossed arms; on the right Rys, the woman from Picture 3, sits in a hammock "
                        "cleaning a pistol. Faces half in shadow, relaxed and tough."),
    "hangar": ([5], "A huge dark hangar carved into rock: a battered patched-together pirate gunship stands on the "
                    "pad, fuel hoses and gantries, work lights cone down through haze. Rys, the woman from Picture 1, "
                    "the pilot, in a worn leather flight jacket with goggles around her neck, leans on a landing "
                    "strut at the right side."),
    "training": ([2], "A pirate training hall in the ship's hold: a punching bag of patched leather hanging on a "
                      "chain, a sparring ring of ropes and iron posts, rusty weights and a target dummy riddled with "
                      "holes. Iskra, the woman from Picture 1, in a sleeveless shirt and cargo trousers, wraps her "
                      "fists with tape at the right side, a fierce grin."),
    "pursuit": ([5], "Night sky seen through the riveted brass frame of a pirate gunship cockpit: a glowing alien "
                     "saucer flying away into the clouds on the right, faint lime engine trails, moonlight on the "
                     "clouds below. Rys, the woman from Picture 1, the pilot, sits at the controls in the left "
                     "foreground in three-quarter view, a headset over her copper curls, her face lit by the dim "
                     "gauges, eyes fixed on the target."),
    "mainmenu": ([1, 2, 4], "The deck of a battered pirate airship at dusk high above burning clouds: on the left "
                            "Sever, the woman from Picture 1, the captain, in a long dark coat with a cutlass; on the "
                            "right Iskra, the woman from Picture 2, and Bazalt, the woman from Picture 3, in patched "
                            "combat gear with improvised rifles; a glowing alien saucer far away in the stormy sky "
                            "between them, brass railings, ropes and a fluttering black flag."),
    "geoscape": ([1], "A pirate navigator's chart room: a big brass-ringed globe of the Earth glowing faintly with "
                      "lime markers stands on a round chart table, old maps pinned to riveted iron walls, an oil "
                      "lamp. Sever, the woman from Picture 1, in a long dark coat, leans over the globe at the right "
                      "side plotting a course with brass dividers, her silver bob lit by the lamp."),
    "briefing": ([1, 3, 6], "The cargo hold of a pirate dropship in flight before landing: rows of fold-down seats "
                            "along riveted iron walls, harnesses and racked weapons, a red jump lamp glowing over the "
                            "closed ramp at the right. Sever, the woman from Picture 1, stands by the ramp giving "
                            "orders; Shpilka, the woman from Picture 2, and Tikhaya, the woman from Picture 3, sit on "
                            "the seats in patched combat gear checking their guns."),
}
CAST.update({
    # без опор модель сама поставила сюда мужчин и безликие шлемы - экипаж Пираток женский
    "hidden": ([6], "A dark ruined street at night in drifting fog seen from a broken doorway: the silhouette of an "
                    "alien creeping between broken walls far away on the right, a faint lime glow of its eyes, "
                    "moonlight on wet rubble. Tikhaya, the woman from Picture 1, keeps watch at the left edge in "
                    "the shadow of the doorway, in patched combat gear with a rifle, her face half lit by the "
                    "moon, still and tense; almost the whole picture is deep shadow."),
    "alert": ([5], "A human town burning at night seen from the open hatch of a pirate airship: columns of smoke lit "
                   "orange from below, an alien saucer hovering low over the roofs on the right with faint lime "
                   "beams, tiny fleeing silhouettes. Rys, the woman from Picture 1, stands at the left by the "
                   "hatch in a leather flight jacket, gripping a brass handrail, her face lit by the fires, eyes "
                   "narrowed at the saucer."),
})
# Экран хода врага - ещё дюжина сцен (тикет XP-000234, Vitali 22.10: «много разных картинок по теме»): кто-то из
# героинь затаился, враг только намёком - силуэт, тень, глаза, следы, не человек. Ставятся в одну строку с hidden
# (install), движок берёт другую картинку каждый ход (HdScreens::nextVariant).
HIDDEN = {
    "hidden_jungle": ([5], "A night jungle of giant leaves and hanging vines in drifting mist, fireflies. Rys, the "
                           "woman from Picture 1, crouches behind a fallen mossy trunk at the left edge in patched "
                           "combat gear, holding her breath, a pistol close to her chest. Far away on the right "
                           "between the trees a big reptilian shape is half hidden in the dark, only two faint lime "
                           "eyes glowing."),
    "hidden_sewer": ([3], "A flooded sewer tunnel of old brick arches, black water to the knees, a single dim lamp "
                          "far down the tunnel. Shpilka, the woman from Picture 1, presses her back to the wet wall at "
                          "the left, a pistol raised beside her face. On the curved wall far away on the right falls "
                          "the long shadow of a clawed creature, slow ripples spreading on the water toward her."),
    "hidden_desert": ([4], "Desert ruins at night under a sky full of stars, cold blue moonlight on sand dunes and "
                           "broken stone columns. Bazalt, the woman from Picture 1, the tallest and strongest, lies "
                           "behind a low broken wall at the left with a heavy machine gun, watching. On a far dune "
                           "crest on the right walk the thin silhouettes of three tall aliens, faint lime glow of "
                           "their eyes."),
    "hidden_snow": ([1], "A snowy pine forest at night in a blizzard. Sever, the woman from Picture 1, the captain, "
                         "crouches behind a thick pine at the left in a long dark coat dusted with snow, binoculars "
                         "lowered, her silver bob under a hood. Huge deep footprints of something large lead away into "
                         "the dark on the right, a faint lime glow between the far trees."),
    "hidden_ufo": ([6], "The curved corridor inside a crashed alien saucer: smooth ribbed walls, dim lime light "
                        "panels, steam from a broken pipe. Tikhaya, the woman from Picture 1, kneels at the left edge "
                        "aiming a long rifle down the corridor, her black braid over one shoulder. At the far end a "
                        "sliding door stands half open, the tall thin shadow of an alien behind frosted glass."),
    "hidden_rooftop": ([2], "Rain-soaked city rooftops at night: water tanks, chimneys, wet tar paper shining in the "
                            "dark. Iskra, the woman from Picture 1, crouches behind a brick chimney at the left with "
                            "a knife and a pistol, rain on her face, a tense fierce grin. Above a far roof on the "
                            "right hangs a small alien drone, its narrow searchlight sweeping through the rain."),
    "hidden_warehouse": ([3], "A dark warehouse of stacked wooden crates and steel shelves, one lamp swinging on a "
                              "chain, its light swaying across the floor. Shpilka, the woman from Picture 1, hides "
                              "between the crates at the left in a leather jacket, a wrench in one hand and a pistol "
                              "in the other. Behind the dirty high windows on the right passes the hulking silhouette "
                              "of a mechanical sentry with one red eye."),
    "hidden_swamp": ([6], "A misty swamp at night: dead twisted trees, reeds, black still water under a pale moon. "
                          "Tikhaya, the woman from Picture 1, stands waist deep in the reeds at the left, rifle "
                          "raised, motionless. From the right a trail of faint lime bubbles moves slowly toward her "
                          "across the water, something big beneath the surface."),
    "hidden_cathedral": ([1], "A ruined gothic church at night, moonlight falling through tall broken windows in "
                              "long pale shafts across the stone floor and toppled pews. Sever, the woman from "
                              "Picture 1, the captain, stands behind a stone pillar at the left in a long dark coat, "
                              "a cutlass in her hand. Across the floor from the right stretches the long shadow of a "
                              "winged alien perched somewhere high."),
    "hidden_mine": ([4], "An old mine shaft: timber supports, a rail track with a rusty cart, a dropped lantern on "
                         "its side throwing warm light on the ground. Bazalt, the woman from Picture 1, the tallest "
                         "and strongest, stands at the left with a pump shotgun, looking into a side tunnel on the "
                         "right, where dozens of tiny lime eyes glitter in the blackness."),
    "hidden_docks": ([2], "A harbour at night in thick fog: cranes, stacked cargo containers, wet planks, black "
                          "water. Iskra, the woman from Picture 1, crouches behind an iron bollard at the left, a "
                          "pistol ready. On the right a long tentacle with a faint lime glow slides out of the black "
                          "water onto the pier."),
    "hidden_radar": ([5], "The dark cockpit of a pirate dropship landed at night: brass frames, levers, rain on "
                          "the windscreen. Rys, the woman from Picture 1, the pilot, leans close to a round green "
                          "motion scanner at the left, faint blips on it, her face and copper curls lit lime from "
                          "below. Outside the windscreen on the right only darkness and rain, and the vague shape "
                          "of something tall standing very still."),
}
CAST.update(HIDDEN)
# у них свои места боя, не корабль: с общим STYLE модель ставила слева в каждую сцену одну и ту же латунную стенку
# с фонарём и зелёным экраном - в пустыню, снег и болото тоже (варианты c1-c2, 22.10)
STYLE_OUT = ("Painted illustration in the style of a 1990s PC strategy game box cover, gritty retro science "
             "fiction, confident brushwork. A night scene on a battlefield, no ship interior, no brass walls, no "
             "lamps or screens unless the scene names them; cold moonlight and deep shadows, a touch of acid lime "
             "green from alien eyes and tech. ")
CAST_DIR = os.path.join(ROOT, "art", "cast")
# опоры - только лица; тело и одежду задаёт текст (героини - солдатки 18-21, спортивные, не культуристки)
CAST_HEAD = ("The pictures are face references of the characters, not the scene: keep each named woman's face, "
             "skin tone, eye colour and hairstyle exactly as in her picture, and give every woman a different face. "
             "All of them are adult women of 19 to 21 with athletic, toned, feminine builds, not bodybuilders, "
             "fully clothed in practical gear. The scene: ")
CAST_NEG = ", identical faces, same face on every woman, bodybuilder, huge muscles, masculine arms, man, beard"
CAST_RES = 640                                      # сторона опоры-лица: три опоры и кадр 1280x800 без shared


def load_pipe(offload):
    import gen_hd                                   # ставит HF_HOME на E:\models
    import torch
    import diffusers
    pipe = diffusers.QwenImage21Pipeline.from_pretrained(gen_hd.QWEN21_REPO, torch_dtype=torch.bfloat16)
    if offload == "none":
        pipe.to("cuda")
    else:
        pipe.enable_model_cpu_offload()
    return pipe, torch


def sheet(n):
    """Лист выбора: варианты с номерами, каждый уменьшен до 480 по ширине."""
    from PIL import Image, ImageDraw
    d = os.path.join(OUT, n)
    # варианты 1, 2, 3... и с героинями c1, c2... (после обычных)
    files = sorted((f for f in os.listdir(d) if f.endswith(".png")),
                   key=lambda f: (f.rsplit("_", 1)[1][0] == "c", int(f.rsplit("_", 1)[1].split(".")[0].lstrip("c"))))
    if not files:
        return
    tiles = []
    for f in files:
        im = Image.open(os.path.join(d, f)).convert("RGB")
        im = im.resize((480, round(480 * im.height / im.width)), Image.LANCZOS)
        dr = ImageDraw.Draw(im)
        dr.rectangle((0, 0, 34, 22), fill=(0, 0, 0))
        dr.text((8, 5), f.rsplit("_", 1)[1].split(".")[0], fill=(255, 200, 112))
        tiles.append(im)
    cols = 3
    rows = (len(tiles) + cols - 1) // cols
    th = tiles[0].height
    board = Image.new("RGB", (cols * 484 + 4, rows * (th + 4) + 4), (16, 10, 6))
    for k, t in enumerate(tiles):
        board.paste(t, (4 + (k % cols) * 484, 4 + (k // cols) * (th + 4)))
    board.save(os.path.join(OUT, "%s_sheet.jpg" % n), quality=88)


def draw(args):
    names = [t for t in args.theme.split(",") if t] or list(CAST if args.cast else THEMES)
    for n in names:
        if n not in (CAST if args.cast else THEMES):
            raise SystemExit("нет такой темы%s: %s" % (" с героинями" if args.cast else "", n))
    pipe, torch = load_pipe(args.offload)
    total = len(names) * args.seeds
    done, t0 = 0, time.time()
    for n in names:
        refs, extra, neg = None, {}, NEGATIVE
        if args.cast:
            from PIL import Image
            ids, scene = CAST[n]
            refs = [Image.open(os.path.join(CAST_DIR, "M%d_face.png" % m)).convert("RGB") for m in ids]
            extra = dict(image=refs, output_resolution=CAST_RES)
            neg = NEGATIVE + CAST_NEG
            prompt = (STYLE_OUT if n in HIDDEN else STYLE) + (COVER if n in BOLD else CALM) + CAST_HEAD + scene
        else:
            prompt = STYLE + (COVER if n in BOLD else CALM) + THEMES[n]
        os.makedirs(os.path.join(OUT, n), exist_ok=True)
        for i in range(1, args.seeds + 1):
            path = os.path.join(OUT, n, ("%s_c%d.png" if args.cast else "%s_%d.png") % (n, i))
            if os.path.exists(path) and not args.force:
                print("%s вариант %d уже есть - пропускаю" % (n, i), flush=True)
                done += 1
                continue
            seed = args.seed + i * 7919
            t1 = time.time()
            # 16:10 - как экран 320x200, которому картинка служит фоном; с опорами - сразу 1280x800 (больше
            # install всё равно не ставит), иначе три опоры и кадр 1792 не помещаются в карту (R-213)
            w, h = (1280, 800) if args.cast else (1792, 1120)
            img = pipe(prompt=prompt, negative_prompt=neg, true_cfg_scale=args.cfg,
                       width=w, height=h, num_inference_steps=args.steps,
                       generator=torch.Generator("cuda").manual_seed(seed), **extra).images[0]
            img.convert("RGB").save(path)
            done += 1
            el = time.time() - t0
            print("%s вариант %d/%d (зерно %d) за %.0f с, всего %d/%d, осталось ~%.0f мин"
                  % (n, i, args.seeds, seed, time.time() - t1, done, total,
                     el / done * (total - done) / 60), flush=True)
        sheet(n)


def install(args):
    """Выбранные варианты - в hd/UI/screens/<тема>.png обеих копий мода hd, таблица тем - screens.txt рядом
    (её читает движок, HdScreens::load): строка «картинка = экраны». Модель не грузит."""
    import shutil
    from PIL import Image
    picks = dict(p.split("=") for p in args.pick.split(",") if p)
    for n in picks:
        if n not in THEMES and n not in HIDDEN:
            raise SystemExit("нет такой темы: %s" % n)
    dests = [os.path.join(ROOT, d, "hd", "UI", "screens") for d in args.mods.split(";") if d]
    for n, v in picks.items():
        src = os.path.join(OUT, n, "%s_%s.png" % (n, v))
        if not os.path.exists(src):
            raise SystemExit("нет варианта %s" % src)
    # темы, уже стоящие в моде (картинка есть), остаются в таблице: --pick ставит или меняет только названные
    themes = [n for n in THEMES if n in picks or os.path.exists(os.path.join(dests[0], "%s.png" % n))]
    lines = ["# Фоны экранов по темам (HdScreens): картинка = экраны (id из interfaces рулсетов).",
             "# Пишет tools/hdart/gen_screens.py install - руками не править."]
    # сцены хода врага - картинки той же строки, что hidden: экран берёт одну из них на ход
    more = [n for n in HIDDEN if n in picks or os.path.exists(os.path.join(dests[0], "%s.png" % n))]
    lines += ["%s = %s" % (" ".join("%s.png" % f for f in [n] + (more if n == "hidden" else [])),
                           " ".join(SCREENS[n].split())) for n in themes]
    for d in dests:
        os.makedirs(d, exist_ok=True)
        for n, v in picks.items():
            src = os.path.join(OUT, n, "%s_%s.png" % (n, v))
            dst = os.path.join(d, "%s.png" % n)
            # RGBA, как остальные картинки HD-слоя; не больше экрана при k = 4 (1280x800, 16:10): движок вписывает
            # в окно сам, а лишние пиксели - только время чтения PNG при открытии экрана (1792x1120 - ~60 мс)
            im = Image.open(src).convert("RGBA")
            if im.width > 1280:
                im = im.resize((1280, round(im.height * 1280 / im.width)), Image.LANCZOS)
            im.save(dst, optimize=True)
        with open(os.path.join(d, "screens.txt"), "w", encoding="utf-8-sig", newline="\n") as f:
            f.write("\n".join(lines) + "\n")
        print("%s: %d картинок и screens.txt" % (d, len(picks)))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("install", help="поставить выбранные варианты в мод (без видеокарты)")
    i.add_argument("--pick", required=True, help="тема=номер через запятую: research=1,crew=2")
    i.add_argument("--mods", default="user/mods/hd;Пиратки/Dioxine_XPiratez/user/mods/hd",
                   help="копии мода hd через ;, от корня репозитория")
    d = sub.add_parser("draw")
    d.add_argument("--theme", default="", help="темы через запятую; пусто - все")
    d.add_argument("--seeds", type=int, default=3, help="вариантов на тему")
    d.add_argument("--seed", type=int, default=2601)
    d.add_argument("--steps", type=int, default=40)
    d.add_argument("--cfg", type=float, default=4.0)
    d.add_argument("--offload", default="model", choices=["model", "none"])
    d.add_argument("--force", action="store_true", help="перерисовать уже готовые варианты")
    d.add_argument("--cast", action="store_true",
                   help="темы с героинями M1-M6 (CAST): лица опорами, варианты <тема>_c<N>.png")
    args = ap.parse_args()
    if args.cmd == "draw":
        draw(args)
    elif args.cmd == "install":
        install(args)


if __name__ == "__main__":
    main()
