# -*- coding: utf-8 -*-
r"""Картинки педии кораблей противника (тикет XP-000172): Qwen-Image-2.1 по макету с карты боя и примеру.

У кораблей игрока в педии - кинокадр корабля (pedia_batch.py, FREE), и он сделан с того же корабля,
что стоит на карте боя: макет блока AIRBUS2 и фото AIRVAN.png - один и тот же красный фургон с того же
ракурса. У кораблей противника картинки нет (статья UFO, type_id 9, показывает схему 160x52), а блок
карты боя есть. Отсюда рецепт (Vitali 21.10: «корабли брать из боя с карты, по примерам других кораблей
из педии»): модели даются три картинки -
  <image1> макет корабля игрока с карты боя, <image2> его фото из педии (пример: как из макета делается
  фото), <image3> макет вражеского корабля с карты боя - и просьба сделать с <image3> то же, что с <image1>.

Шаги, арт утверждает Vitali (art-approval-first):
1. mock - макеты блоков из HD-пака мода в art/pedia_ufo/_mock/ (без видеокарты, системный питон):
       py -3 tools\hdart\gen_ufo_pedia.py mock
2. draw - варианты в art/pedia_ufo/<корабль>/<пример>_v<N>.png и лист art/pedia_ufo/sheet.jpg,
   только через очередь видеокарты (tools/gpuq.py), с PYTHONIOENCODING=utf-8 (R-001):
       tools\hdart\.venv-qwen21\Scripts\python.exe tools\hdart\gen_ufo_pedia.py draw --seeds 1
3. подключение - после выбора, вместе с показом картинки в ArticleStateUfo (движок, отдельно).
"""
import argparse
import gc
import json
import os
import re
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "art", "pedia_ufo")
MOCK = os.path.join(OUT, "_mock")
MODDIR = os.path.join(ROOT, "Пиратки", "Dioxine_XPiratez", "user", "mods")
HDUI = os.path.join(MODDIR, "hd", "hd", "UI")
VALUES = os.path.join(ROOT, ".index", "mod", "Piratez", "rul", "values.tsv")
sys.path.insert(0, os.path.dirname(__file__))

# пример: корабль игрока -> его фото педии в hd/UI. Макет и фото сняты почти с одного ракурса
EXAMPLES = {
    "AIRVAN": ("STR_AIRVAN", "AIRVAN.png"),
    "SABRE": ("STR_SABRE", "SABRE.png"),
    "HUEY": ("STR_HUEY", "CA_HUEY.png"),
}

HEAD = ("<image1> is a render of a flying vessel taken from an isometric tactical battle map, seen from above "
        "at an angle. <image2> is the film still for the game's encyclopedia made from <image1>: the very same "
        "vessel with the same shape, parts, colours and markings, turned into a real cinematic photograph of a "
        "full-size craft actually built and filmed for a big-budget science fiction movie. <image3> is a render "
        "of another vessel from the same battle map. Make the film still of the vessel of <image3> in exactly the "
        "way <image2> was made from <image1>: keep the silhouette, the proportions, the arrangement of hull, "
        "decks, turrets, engines, windows and markings of <image3>, and every part keeps its own colour from "
        "<image3>; the realism, materials, light and camera come from <image2>. Nothing of the vessel of <image1> "
        "or <image2> appears in the result. The flat grey background of the renders and the open cut-away of the "
        "battle map are not part of the vessel: show it closed and whole. Dynamic three-quarter view from "
        "slightly above, the vessel large in the frame. ")
# пример второй и третьей картинкой: при примере первым (HEAD) модель рисовала сам пример - пилот 21.10,
# USO CRUISER с примером AIRVAN вышел красным фургоном с килями AIRVAN
HEAD_TARGET_FIRST = (
    "<image1> is a render of a flying vessel taken from an isometric tactical battle map, seen from above at an "
    "angle. Make a real cinematic film still of exactly this vessel of <image1>, as if it were actually built "
    "full-size and filmed for a big-budget science fiction movie: keep its silhouette, proportions, the "
    "arrangement of hull, decks, turrets, engines, windows and markings, and every part keeps its own colour from "
    "<image1>. <image2> and <image3> are only an example of the conversion, a different vessel: <image2> is its "
    "battle map render and <image3> the film still made from it. Take from that example only how a render becomes "
    "a photograph - the realism, materials, light and camera; never its shape, colours, fins, intakes or "
    "markings. The flat grey background of the render and the open cut-away of the battle map are not part of "
    "the vessel: show it closed and whole. Dynamic three-quarter view from slightly above, the vessel large in "
    "the frame. ")
# без примера картинкой: что пары «макет -> фото» показывают (AIRVAN, SABRE, HUEY), сказано словами
# стиль - как у остальных фото кораблей педии (pedia_batch.py FREE + NEG_CINE, Vitali 26.09): один корабль
# в середине кадра с воздухом вокруг, простой фон, ясные сильные цвета, контровой свет, лёгкий износ.
# S2/S3 21.10 (копоть, шторм, брызги, корабль во весь кадр) - «выбиваются», в отбросы (R-429)
HEAD_SOLO = (
    "<image1> is a render of a flying vessel taken from an isometric tactical battle map, seen from above at an "
    "angle. Make a real cinematic film still of this vessel, as if it were actually built full-size and filmed "
    "for a big-budget science fiction movie of the 1980s. From the render take the silhouette, the proportions "
    "and the main masses and their colours; the floor tiles, grid patterns, railings and small clutter of the "
    "battle map are only the game's floor, not the surface of the real hull, and the open cut-away is not part "
    "of the vessel: show it closed and whole. The vessel flies alone in the middle of the frame, medium size, "
    "with plenty of open air around it, seen in three-quarter view from slightly above. Clean simple "
    "background. The colours are clear and strong, cinematic dramatic light and contrast with a bright rim "
    "light along the hull, painted metal with fine panel lines and real materials, only light wear. The vessel "
    "carries only the weapons named below, small and in proportion to the hull, exactly as many as named; "
    "nothing else on it is a gun. ")
NEGATIVE = ("text, letters, numbers, caption, logo, watermark, grid, isometric game render, pixel art, voxel, "
            "cut-away, cross-section, flat grey background, cartoon, drawing, cel shading, plastic toy, low "
            "resolution, blurry, jpeg artifacts, desaturated, washed out, repainted, wrong colours, people in the "
            "foreground, nudity, muted colours, faded paint, dull, overcast, rust, mud, dirty, soot, storm, "
            "lightning, rain, spray, vessel filling the frame, cropped vessel, oversized weapon")

# корабль: сценарий до генерации (Vitali 21.10) - чей, какой расы, где кабина, как быстро летает, и оружие
# ТОЛЬКО из конфига: статья en-US (STR_..._UFOPEDIA), ufos (speedMax, power, raceBonus), предметы карты
# (battlescapeTerrainData.items - детали орудия), срезы этажей карты (где мостик и пульты)
SHIPS = {
    # бандиты/рейдеры; speedMax 180 - тихоход; в статье «14mm turrets», на карте две STR_SPAWN_14MM_LIGHT_TURRET;
    # рубка - надстройка с пультами на конце гондолы (левый конец макета)
    "STR_VESSEL_BANDIT_ZEPP": (
        "The battle map shows the long gondola hull of a bandit airship; in the film still a huge fat patched "
        "gas envelope rides above that gondola. A slow lumbering raider airship of wasteland bandits, the "
        "wheelhouse with its windows is the raised cabin at one end of the gondola, a pusher engine pod at the "
        "same end. It drifts over a ruined wasteland town under a clear golden sunset sky. Weapons: exactly two "
        "small light 14mm machine-gun turrets on the gondola deck, nothing more."),
    # Звёздные боги: экипаж - элита сектоидов, флоатеров, мутонов, эфириалов (raceBonus); speedMax 5000,
    # armor 10; на карте STR_GAUSS_CANNON_PARTS - одна пушка Гаусса; Elerium-115 на борту; срезы этажей:
    # низ с красными гравиплитами, широкая средняя палуба, сверху мостик с креслом (большая надстройка) и
    # малая надстройка. S3: пушка вышла огромной (Vitali 21.10 «пушка должна быть меньше»). Курс: в QB след
    # шёл из левого верха - летел вправо вниз; Vitali 21.10 «летит в сторону левого верха» - мостик (большая
    # надстройка, на макете слева вверху) - нос, след на холсте draw21 нарисован вправо вниз (TRAIL21, R-428)
    "STR_VESSEL_GUNSHIP": (
        "An alien warship of the Star Gods, crewed by elite grey aliens: a small, heavily armoured and very fast "
        "craft, three stacked rounded armour slabs, no wings, no fins, no jet intakes, no exhausts. The hull is "
        "alien alloy, dark charcoal with a lilac sheen, large precisely fitted curved plates with hair-thin "
        "seams, small square portholes in rounded frames along the sides, a few of them lit violet. It is "
        "driven by anti-gravity: a row of round red gravity-lift plates glows softly on its belly. The larger "
        "raised block on its back is the armoured command bridge with a narrow viewport slit glowing violet. "
        "Weapons: exactly one gauss cannon, a short slim twin-rail barrel with a few copper coils, small - no "
        "longer than the smaller raised block it sits on - nothing more. It flies high above a sea of white "
        "clouds in a clear evening sky, heading towards the upper left corner of the frame: the command bridge "
        "end is the front and leads, pointing to the upper left; a thin vapour trail streams out behind it "
        "towards the lower right corner of the frame."),
    # T'Leth (подводная цивилизация, Tasoth); speedMax 4400; «light and easily mass-produced»; на карте
    # STR_SONIC_OSCILLATOR_PARTS - звуковые осцилляторы, стволов нет; круглые чёрные люки на носах лопастей,
    # пары красных огней (окно перехвата USO_Cruiser.png). Vitali 21.10: «такой потолок как в оригинале не
    # надо, просто форму сохрани» - решётка крыши это пол карты, корпус гладкий
    "STR_VESSEL_USO_CRUISER": (
        "A gunboat of the T'Leth, an ancient alien civilisation living deep under the ocean: a light, "
        "mass-produced flying submarine. Keep only the outline of the render: a thick flat three-lobed flying "
        "wing with rounded ends. The lattice pattern on the render is just the floor of the game map: the real "
        "hull is smooth, sleek and streamlined, polished golden amber alloy with soft curved panels, a gentle "
        "dome in the middle where the crew sits, no glass canopy. Each lobe ends in a rounded nose with a big "
        "round black hatch, pairs of small red running lights along the rim, the underside a darker sea-green. "
        "Weapons: two sonic oscillators, smooth grey spheres set into the hull near the tips of the lobes; no gun "
        "barrels, no missiles, nothing more. It flies fast and level low over a calm deep-blue sea at dusk, sea "
        "water dripping from its hull, a long white wake on the water behind it."),
    # Black Talon по рулсету - штурмовик («crudely made of plastasteel plating and jet engines ... attack with
    # missile fire», Interwin_F117.gif), но блок карты VES_NECROFIGTHER (CRASHEDPLANE) - два цилиндра и плоские
    # листы. Vitali 21.10 после QB/QC: «ЭТО СПУТНИК СДЕЛАЙ СПУТНИК по типу станции МИР» - цилиндры = модули,
    # листы = солнечные батареи; ракеты оставлены малыми пусковыми трубами (атакует ракетами по описанию)
    "STR_VESSEL_BLACK_BOMBER": (
        "A crude armed space satellite built in the manner of the old Soviet Mir space station: the two big "
        "metal cylinders of the render are its pressurised modules joined by a docking node, the flat dark "
        "plates are its wide rectangular solar panel wings on lattice booms. Riveted cylindrical hull sections "
        "in off-white and grey thermal blankets with silver foil and dark plastasteel patches welded on, small "
        "round portholes, radiator fins, antenna dishes and whip antennas, docking ports with conical probes. "
        "Weapons: missiles only - a small rack of a few short missile launch tubes on one module, nothing more. "
        "It hangs in orbit high above the curved blue Earth with white clouds, black space with a few stars "
        "behind it, hard bright sunlight from one side."),
}
# сверх общего негатива - чего нет у этого корабля по конфигу
SHIP_NEG = {
    "STR_VESSEL_BANDIT_ZEPP": "many guns, cannon rows, missile pods, large guns",
    "STR_VESSEL_GUNSHIP": "wings, tail fins, jet engines, propellers, gun turrets, multiple guns, missiles, "
                          "long cannon, huge cannon, letters, glyph text, featureless box",
    "STR_VESSEL_USO_CRUISER": "gun barrels, cannons, turrets, missiles, wings with jet engines, raft, floating "
                              "platform, ship deck, boat, oil rig, lattice, grid, honeycomb, cage, mesh roof",
    "STR_VESSEL_BLACK_BOMBER": "aeroplane, jet fighter, stealth jet, wings with jet engines, tail fins, cockpit "
                               "canopy, jet exhaust flames, sky, clouds around it, desert, explosions, fireworks, "
                               "missiles in flight, guns, turrets, propellers, astronauts",
}
BG = (128, 128, 132)
# сторона опоры для модели: QwenImage21Pipeline растягивает КАЖДУЮ опору до output_resolution^2 и держит её
# ключи в KV-кэше на всех слоях. При 1024 три опоры + выход заняли 32.1 ГБ из 32.6 и ушли в shared 3.4 ГБ
# (сторож очереди снимает задание, R-213); 768 - около 0.6 Мпикс на опору
COND_RES = 768


def terrain_data(ids):
    """id корабля -> battlescapeTerrainData из карты рулсетов (.index, tools/rul_map.py)."""
    out = {}
    with open(VALUES, encoding="utf-8-sig") as f:
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) >= 4 and p[1] in ids and p[2] == "battlescapeTerrainData" and p[0] in ("crafts", "ufos"):
                out[p[1]] = json.loads(p[3])
    return out


def mock(args):
    """Блок корабля целиком из HD-пака мода, как его рисует игра (map_mockup.render), фон прозрачный."""
    import map_mockup as mm
    import score_batch as sb

    class Clear(tuple):                      # render заливает фон FLOOR_BG + (255,) - даём прозрачный
        def __add__(self, other):
            return (0, 0, 0, 0)
    mm.FLOOR_BG = Clear((0, 0, 0))
    ids = list(SHIPS) + [v[0] for v in EXAMPLES.values()]
    data = terrain_data(set(ids))
    world = mm.World()
    os.makedirs(MOCK, exist_ok=True)
    for sid in ids:
        t = data.get(sid)
        if not t:
            print("нет battlescapeTerrainData:", sid)
            continue
        world.terrains[t["name"]] = t
        block = t["mapBlocks"][0]["name"]
        im, _ = mm.render(world, t["name"], block, sb.MOD, 4)
        im = im.crop(im.getbbox())
        im.save(os.path.join(MOCK, sid + ".png"))
        print(sid, block, im.size)


def load_pipe(offload):
    import gen_hd                                   # ставит HF_HOME на E:\models
    import torch
    import diffusers
    pipe = diffusers.QwenImage21Pipeline.from_pretrained(gen_hd.QWEN21_REPO, torch_dtype=torch.bfloat16)
    if offload == "none":
        pipe.to("cuda")
    else:
        pipe.enable_model_cpu_offload()
    if hasattr(pipe, "enable_vae_tiling"):
        pipe.enable_vae_tiling()
    return pipe, torch


def fit(im, side=1024):
    """Макет кладётся на ровный серый с полями - как рамка кадра, не обрезанный край. Размер опоры для
    модели задаёт не он: конвейер сам растягивает каждую до output_resolution^2 (см. COND_RES)."""
    from PIL import Image
    if im.mode == "RGBA":
        pad = max(im.size) // 12
        bg = Image.new("RGBA", (im.width + 2 * pad, im.height + 2 * pad), BG + (255,))
        bg.alpha_composite(im, (pad, pad))
        im = bg
    im = im.convert("RGB")
    s = side / max(im.size)
    return im.resize((round(im.width * s) // 16 * 16, round(im.height * s) // 16 * 16), Image.LANCZOS)


def sheet(tag=None):
    """Лист выбора: строка на корабль - макет и варианты по 480 в ширину. tag - только серия, в sheet_<tag>.jpg."""
    from PIL import Image, ImageDraw
    rows = []
    for ship in SHIPS:
        d = os.path.join(OUT, ship)
        mp = os.path.join(MOCK, ship + ".png")
        if not os.path.isdir(d) or not os.path.exists(mp):
            continue
        files = sorted(f for f in os.listdir(d) if re.match(r"^[A-Z]+\d*_v\d+\.png$", f)
                       and (not tag or f.startswith(tag + "_v")))
        if not files:
            continue
        m = fit(Image.open(mp).convert("RGBA"), 480)
        tiles = [m]
        for f in files:
            im = Image.open(os.path.join(d, f)).convert("RGB")
            im = im.resize((480, round(480 * im.height / im.width)), Image.LANCZOS)
            ImageDraw.Draw(im).text((8, 5), f[:-4], fill=(255, 200, 112))
            tiles.append(im)
        rows.append((ship, tiles))
    if not rows:
        return
    th = 300
    cols = max(len(t) for _, t in rows)
    board = Image.new("RGB", (cols * 484 + 4, len(rows) * (th + 24) + 4), (16, 10, 6))
    dr = ImageDraw.Draw(board)
    for r, (ship, tiles) in enumerate(rows):
        y = 4 + r * (th + 24)
        dr.text((8, y + 4), ship, fill=(255, 220, 160))
        for c, t in enumerate(tiles):
            board.paste(t.crop((0, 0, t.width, min(t.height, th))), (4 + c * 484, y + 20))
    board.save(os.path.join(OUT, "sheet_%s.jpg" % tag if tag else "sheet.jpg"), quality=88)


def draw(args):
    from PIL import Image
    names = [s for s in args.ship.split(",") if s] or list(SHIPS)
    exs = [e for e in args.examples.split(",") if e]
    for n in names:
        if n not in SHIPS:
            raise SystemExit("нет такого корабля: %s (есть %s)" % (n, ", ".join(SHIPS)))
        if not os.path.exists(os.path.join(MOCK, n + ".png")):
            raise SystemExit("нет макета %s - сначала шаг mock" % n)
    for e in exs:
        if e not in EXAMPLES:
            raise SystemExit("нет такого примера: %s (есть %s)" % (e, ", ".join(EXAMPLES)))
    pipe, torch = load_pipe(args.offload)
    pairs = {e: (fit(Image.open(os.path.join(MOCK, EXAMPLES[e][0] + ".png")).convert("RGBA")),
                 fit(Image.open(os.path.join(HDUI, EXAMPLES[e][1])))) for e in exs}
    # вариант -> (файл, опоры, начало промпта). Режим в имени: AIRVAN_v1 - пример первым (HEAD),
    # TAIRVAN_v1 - макет врага первым, SOLO_v1 - без примера картинкой
    def variants(ref):
        if args.mode == "solo":
            return [("SOLO", [ref], HEAD_SOLO)]
        if args.mode == "target-first":
            return [("T" + e, [ref, pairs[e][0], pairs[e][1]], HEAD_TARGET_FIRST) for e in exs]
        return [(e, [pairs[e][0], pairs[e][1], ref], HEAD) for e in exs]
    total = len(names) * (1 if args.mode == "solo" else len(exs)) * args.seeds
    done, t0 = 0, time.time()
    for n in names:
        ref = fit(Image.open(os.path.join(MOCK, n + ".png")).convert("RGBA"))
        os.makedirs(os.path.join(OUT, n), exist_ok=True)
        for e, images, head in variants(ref):
            if args.tag:
                e = args.tag                    # серия под своим именем: S2_v1 ...
            elif args.cond_res != COND_RES:
                e += str(args.cond_res)         # SOLO1024_v1 - опоры в другом разрешении
            for i in range(1, args.seeds + 1):
                path = os.path.join(OUT, n, "%s_v%d.png" % (e, i))
                if os.path.exists(path) and not args.force:
                    done += 1
                    continue
                seed = args.seed + i * 7919
                t1 = time.time()
                # 16:10, как картинки педии кораблей игрока (1280x800); крупнее - уменьшается при подключении
                img = pipe(image=images, prompt=head + "The scene: " + SHIPS[n],
                           negative_prompt=NEGATIVE + (", " + SHIP_NEG[n] if n in SHIP_NEG else ""),
                           true_cfg_scale=args.cfg, width=args.width, height=args.height,
                           output_resolution=args.cond_res,
                           num_inference_steps=args.steps,
                           generator=torch.Generator("cuda").manual_seed(seed)).images[0]
                img.convert("RGB").save(path)
                done += 1
                el = time.time() - t0
                print("%s %s v%d (зерно %d) за %.0f с, всего %d/%d, осталось ~%.0f мин"
                      % (n, e, i, seed, time.time() - t1, done, total, el / done * (total - done) / 60), flush=True)
                del img                     # без этого шестая картинка падала по памяти карты (#789)
                gc.collect()
                torch.cuda.empty_cache()
        sheet(args.tag)


# draw21 - тем же путём, каким сделаны фото кораблей игрока в педии (pedia_batch -> pedia_ab --model new):
# Qwen-Image-2.1 на DiffSynth, img2img - старт с латентов картинки под шумом силы strength (у кораблей 0.95).
# Картинка - макет с карты боя посреди кадра 16:10 на небе своей сцены: раскладка, ракурс и курс берутся из
# неё, а не выбираются моделью (R-428). Vitali 21.10 после S4: «все не то / делай через квен 2.1»
HEAD21 = ("Make a real cinematic film still of this flying vessel, as if it were actually built full-size and "
          "filmed for a big-budget science fiction movie: keep its silhouette, proportions, camera angle and "
          "position in the frame. The vessel comes from an isometric game battle map: its floor tiles, grid "
          "patterns, railings and small clutter are only the game's floor, not the surface of the real hull, and "
          "the open cut-away is not part of the vessel: show it closed and whole. It flies alone with plenty "
          "of empty space around it, the simple background behind it as in the picture. Every part keeps its own colour from the "
          "picture, the colours as clear and strong as in the picture, not greyed. Cinematic dramatic light and "
          "contrast with a bright rim light along the hull, painted metal with fine panel lines and real "
          "materials; only light wear. The vessel carries only the weapons named below, small and in proportion "
          "to the hull, exactly as many as named; nothing else on it is a gun. ")
# небо сверху, небо у горизонта, низ (земля, облака, море) и его доля кадра - по сцене из SHIPS
SKY21 = {
    "STR_VESSEL_BANDIT_ZEPP": ((70, 92, 140), (250, 172, 84), (64, 48, 38), 0.22),
    "STR_VESSEL_GUNSHIP": ((40, 82, 160), (240, 192, 150), (236, 236, 242), 0.28),
    "STR_VESSEL_USO_CRUISER": ((42, 52, 104), (222, 132, 92), (22, 52, 92), 0.35),
    "STR_VESSEL_BLACK_BOMBER": ((2, 3, 10), (14, 26, 60), (46, 98, 176), 0.3),   # спутник: космос над Землёй
}
# след, заданный рисунком на холсте (на силе 0.95 раскладка держится, слова «влево-вправо» - нет, R-428):
# корабль -> угол кадра, куда уходит след (летит в противоположный)
TRAIL21 = {"STR_VESSEL_GUNSHIP": (1.0, 0.86)}


def canvas21(n, W, H):
    """Макет посреди кадра на небе сцены: корабль ~62% ширины, чуть выше центра, вокруг воздух."""
    import numpy as np
    from PIL import Image
    top, hor, low, share = SKY21[n]
    gy = int(H * (1 - share))
    t = np.linspace(0, 1, gy)[:, None]
    sky = np.array(top)[None, :] * (1 - t) + np.array(hor)[None, :] * t
    a = np.zeros((H, W, 3), np.float32)
    a[:gy] = sky[:, None, :]
    # ровная заливка низа на силе 0.9-0.95 так и остаётся плоской плашкой (Q95_v1 цеппелина, 21.10):
    # низ - от цвета горизонта к своему, с крупной зернистостью, чтобы модель читала его как местность
    u = np.linspace(0, 1, H - gy)[:, None, None] ** 0.6
    a[gy:] = np.array(hor)[None, None, :] * (1 - u) + np.array(low)[None, None, :] * u
    rng = np.random.default_rng(172)
    from PIL import ImageFilter
    blot = Image.fromarray((rng.random((H // 8, W // 8)) * 255).astype(np.uint8)).resize(
        (W, H), Image.BICUBIC).filter(ImageFilter.GaussianBlur(10))
    b = np.asarray(blot, np.float32)[gy:, :, None]
    a[gy:] += (b - b.mean()) / (b.std() + 1e-3) * 14 * u
    bg = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    if n in TRAIL21:                        # от середины корабля к углу, корабль ляжет поверх начала
        from PIL import ImageDraw
        tr = Image.new("L", (W, H), 0)
        ex, ey = TRAIL21[n]
        x0, y0, x1, y1 = W * 0.5, H * 0.45, W * ex, H * ey
        d = ImageDraw.Draw(tr)
        for s in range(40):                 # тоньше и прозрачнее к хвосту
            t0, t1 = s / 40.0, (s + 1) / 40.0
            d.line([(x0 + (x1 - x0) * t0, y0 + (y1 - y0) * t0), (x0 + (x1 - x0) * t1, y0 + (y1 - y0) * t1)],
                   fill=int(255 * (1 - t0 * 0.6)), width=max(6, int(36 * (1 - t0 * 0.5))))
        tr = tr.filter(ImageFilter.GaussianBlur(6))
        bg.alpha_composite(Image.merge("RGBA", (*[Image.new("L", (W, H), 245)] * 3, tr)))
    mp = os.path.join(MOCK, n + "_clean.png")
    m = Image.open(mp if os.path.exists(mp) else os.path.join(MOCK, n + ".png")).convert("RGBA")
    m = m.crop(m.getchannel("A").getbbox())
    s = min(W * 0.62 / m.width, H * 0.6 / m.height)
    m = m.resize((round(m.width * s), round(m.height * s)), Image.LANCZOS)
    bg.alpha_composite(m, ((W - m.width) // 2, int(H * 0.45 - m.height / 2)))
    return bg.convert("RGB")


# выбор Vitali 21.10 (art/pedia_ufo/ACCEPTED.txt) и рамки статьи UFO с картинкой (ArticleStateUfo, движок):
# характеристики слева вверху под заголовком, текст внизу под кораблём
ACCEPTED = {
    "STR_VESSEL_BANDIT_ZEPP": "QB97_v2.png",
    "STR_VESSEL_USO_CRUISER": "QB95_v3.png",
    "STR_VESSEL_GUNSHIP": "QD95_v2.png",
    "STR_VESSEL_BLACK_BOMBER": "QD95_v2.png",
}
RULESET = "hd_pedia_ufo.rul"
PAL_SRC = os.path.join(MODDIR, "Piratez", "Resources", "Pedia", "AIRVAN.png")   # PAL_UFOPAEDIA статей кораблей


def install(args):
    """Подключение выбранных: классика 320x200 в палитре статей кораблей (Resources/PediaUfo) и рулсет
    Ruleset/hd_pedia_ufo.rul - в обе копии мода hd; HD 1280x800 hd/UI/<то же имя>.png - сборщиком пака
    (манифест, обе копии). Без --yes - сухой прогон. Системный питон: py -3.13 ... install --yes"""
    import hashlib
    import io as _io
    from PIL import Image
    import build_hd_pack as bp
    pal_im = Image.open(PAL_SRC)
    pal = pal_im.getpalette()[:768]
    q = list(pal)
    q[0:3] = [255, 0, 255]                  # индекс 0 прозрачный - чёрный не должен в него попасть
    qimg = Image.new("P", (1, 1))
    qimg.putpalette(q)
    roots = [os.path.join(ROOT, "user", "mods", "hd"), os.path.join(MODDIR, "hd")]
    lines = ["# OXCE-HD: photos of the enemy vessels in the Ufopaedia (ticket XP-000172), made by",
             "# tools/hdart/gen_ufo_pedia.py; the engine shows image_id of a UFO article full-screen.",
             "extraSprites:"]
    arts, classic = [], []
    for sid, f in ACCEPTED.items():
        name = "PediaUfo_" + sid.replace("STR_", "")
        src = Image.open(os.path.join(OUT, sid, f)).convert("RGB")
        hd = src.resize((1280, 800), Image.LANCZOS)
        small = hd.resize((320, 200), Image.LANCZOS).quantize(palette=qimg, dither=Image.Dither.NONE)
        small.putpalette(pal)
        b = _io.BytesIO()
        small.save(b, "PNG", optimize=True)
        classic.append(("Resources/PediaUfo/%s.png" % name, b.getvalue()))
        b = _io.BytesIO()
        hd.save(b, "PNG", optimize=True)
        arts.append(("UI/%s.png" % name, b.getvalue(), sid, f))
        lines += ["  - typeSingle: %s" % name, "    fileSingle: Resources/PediaUfo/%s.png" % name]
    lines.append("ufopaedia:")
    for sid in ACCEPTED:
        lines += ["  - id: %s" % sid, "    image_id: PediaUfo_%s" % sid.replace("STR_", ""),
                  "    rect_stats: {x: 5, y: 52, width: 150, height: 40}",
                  "    rect_text: {x: 10, y: 146, width: 300, height: 50}"]
    rul = ("\n".join(lines) + "\n").encode("utf-8")
    print("картинок %d, рулсет %d строк; копии: %s" % (len(arts), len(lines), ", ".join(roots)))
    if not args.yes:
        raise SystemExit("сухой прогон; --yes - записать")
    for root in roots:
        for rel, data in classic + [("Ruleset/" + RULESET, rul)]:
            p = os.path.join(root, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "wb") as fh:
                fh.write(data)
    man = bp.load()
    rels = []
    for rel, data, sid, f in arts:
        entry = man["files"].get(rel)
        bp.stage(man, rel, data, generator="gen_ufo_pedia", generator_version="gen_ufo_pedia.py draw21 21.10",
                 source_path=None, approved=True, approval="Vitali 21.10 в чате (ACCEPTED.txt)",
                 derived_from=entry.get("sha256") if entry else None, source_frame=sid,
                 note="педия корабля противника: %s/%s" % (sid, f))
        rels.append(rel)
    bp.save(man, why="gen_ufo_pedia: %d фото педии кораблей противника" % len(rels))
    print("game:", bp.install(man, "game", only=rels))
    print("repo:", bp.install(man, "repo", only=rels))
    bad = 0
    for r in rels:
        for root in (bp.TARGETS["game"], bp.TARGETS["repo"]):
            p = os.path.join(root, r)
            if not os.path.exists(p) or hashlib.sha256(open(p, "rb").read()).hexdigest() != man["files"][r]["sha256"]:
                print("РАСХОДИТСЯ", root, r)
                bad += 1
    print("сверка копий:", "OK" if not bad else "РАСХОДИТСЯ %d" % bad)


def clean(args):
    """Макет без мелочи, лежащей отдельно от корпуса: на силе 0.95 она остаётся в кадре летящим мусором
    (Q95 бомбардировщика 21.10 - разложенные по карте обломки вокруг самолёта). Куски, которые после
    раздутия на grow пикселей не срослись с крупными (меньше share самого большого), стираются.
    Системный питон (scipy), не DiffSynth: py -3 tools\\hdart\\gen_ufo_pedia.py clean"""
    import numpy as np
    from PIL import Image
    from scipy import ndimage
    for n in [s for s in args.ship.split(",") if s] or list(SHIPS):
        im = Image.open(os.path.join(MOCK, n + ".png")).convert("RGBA")
        a = np.asarray(im).copy()
        solid = a[..., 3] > 0
        lab, k = ndimage.label(ndimage.binary_dilation(solid, iterations=args.grow))
        if k == 0:
            continue
        area = ndimage.sum(solid, lab, range(1, k + 1))
        keep = np.isin(lab, 1 + np.flatnonzero(area >= args.share * area.max()))
        a[~keep] = 0
        Image.fromarray(a, "RGBA").save(os.path.join(MOCK, n + "_clean.png"))
        print("%s: кусков %d, оставлено %d, стёрто пикселей %d" % (
            n, k, int((area >= args.share * area.max()).sum()), int((solid & ~keep).sum())))


def draw21(args):
    """Только из окружения DiffSynth: E:\\train\\.venv-train (как pedia_batch -> pedia_ab --model new)."""
    import numpy as np
    from PIL import Image
    import pedia_ab
    import pedia_batch as pb
    names = [s for s in args.ship.split(",") if s] or list(SHIPS)
    strengths = [float(s) for s in args.strengths.split(",")]
    todo = []
    for n in names:
        if n not in SHIPS:
            raise SystemExit("нет такого корабля: %s (есть %s)" % (n, ", ".join(SHIPS)))
        os.makedirs(os.path.join(OUT, n), exist_ok=True)
        inp = os.path.join(OUT, n, args.prefix + "_input.png")
        canvas21(n, args.width, args.height).save(inp)
        for st in strengths:
            for i in range(1, args.seeds + 1):
                path = os.path.join(OUT, n, "%s%d_v%d.png" % (args.prefix, round(st * 100), i))
                if args.force or not os.path.exists(path):
                    todo.append((n, inp, st, i, path))
    print("заданий %d" % len(todo), flush=True)
    if todo:
        ns = argparse.Namespace(models_json=args.models_json, vram_limit=args.vram_limit, steps=args.steps,
                                cfg=args.cfg)
        gen = pedia_ab.New(ns)
        neg = pb.NEG_PHOTO + ", low poly, plastic toy" + pb.NEG_CINE + pb.NEG_NOBODY + ", " + NEGATIVE
        t0 = time.time()
        for k, (n, inp, st, i, path) in enumerate(todo):
            t1 = time.time()
            seed = args.seed + i * 7919
            out = gen(Image.open(inp).convert("RGB"), HEAD21 + "The scene: " + SHIPS[n],
                      neg + (", " + SHIP_NEG[n] if n in SHIP_NEG else ""), seed, st)
            Image.fromarray(np.asarray(out)).convert("RGB").save(path)
            el = time.time() - t0
            print("%s сила %.2f v%d (зерно %d) за %.0f с, всего %d/%d, осталось ~%.0f мин" % (
                n, st, i, seed, time.time() - t1, k + 1, len(todo), el / (k + 1) * (len(todo) - k - 1) / 60),
                flush=True)
    for st in strengths:
        sheet("%s%d" % (args.prefix, round(st * 100)))


def main():
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = a.add_subparsers(dest="cmd", required=True)
    sub.add_parser("mock")
    d = sub.add_parser("draw")
    d.add_argument("--ship", default="", help="через запятую; пусто - все пилотные")
    d.add_argument("--examples", default="AIRVAN,SABRE", help="пары-примеры через запятую: " + ",".join(EXAMPLES))
    # solo по умолчанию: пары картинкой копируются в результат (R-426)
    d.add_argument("--mode", default="solo", choices=("example-first", "target-first", "solo"))
    d.add_argument("--seeds", type=int, default=1)
    d.add_argument("--seed", type=int, default=172)
    d.add_argument("--steps", type=int, default=40)
    d.add_argument("--cfg", type=float, default=4.0)
    d.add_argument("--offload", default="model", choices=("model", "none"))
    d.add_argument("--force", action="store_true")
    d.add_argument("--cond-res", type=int, default=COND_RES,
                   help="сторона опор; 1024 с тремя опорами уходит в shared ~3.4 ГБ, с одной (solo) - нет")
    d.add_argument("--width", type=int, default=1280)
    d.add_argument("--height", type=int, default=800)
    d.add_argument("--tag", help="имя серии в файлах вместо режима: S2 -> S2_v1.png")
    sub.add_parser("sheet").add_argument("--tag")
    q = sub.add_parser("draw21", help="Qwen-Image-2.1 DiffSynth img2img, как педия кораблей игрока")
    q.add_argument("--ship", default="")
    q.add_argument("--strengths", default="0.9,0.95", help="через запятую; файлы Q90_v1.png ...")
    q.add_argument("--prefix", default="Q", help="серия: QB -> QB95_v1.png, QB_input.png (только буквы)")
    q.add_argument("--seeds", type=int, default=4)
    q.add_argument("--seed", type=int, default=172)
    q.add_argument("--steps", type=int, default=30, help="как pedia_ab --model new")
    q.add_argument("--cfg", type=float, default=4.0)
    q.add_argument("--width", type=int, default=1280)
    q.add_argument("--height", type=int, default=800)
    q.add_argument("--force", action="store_true")
    q.add_argument("--models-json", dest="models_json", default=r"E:\train\model_paths.json")
    q.add_argument("--vram-limit", dest="vram_limit", type=float, default=26.0)
    c = sub.add_parser("clean", help="макет без отдельно лежащей мелочи -> _mock/<корабль>_clean.png")
    c.add_argument("--ship", default="STR_VESSEL_BLACK_BOMBER")
    c.add_argument("--grow", type=int, default=6)
    c.add_argument("--share", type=float, default=0.05)
    sub.add_parser("install", help="выбранные (ACCEPTED) - в обе копии мода hd").add_argument("--yes", action="store_true")
    args = a.parse_args()
    if args.cmd == "install":
        install(args)
    elif args.cmd == "clean":
        clean(args)
    elif args.cmd == "mock":
        mock(args)
    elif args.cmd == "draw":
        draw(args)
    elif args.cmd == "draw21":
        draw21(args)
    else:
        sheet(args.tag)


if __name__ == "__main__":
    main()
