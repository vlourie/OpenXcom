# -*- coding: utf-8 -*-
r"""Картинки лаунчера и сайта: Qwen-Image-2.1 рисует с нуля, без LoRA и без входной картинки.

Два шага, потому что арт утверждает человек:

1. draw - по каждой цели несколько вариантов (разные зёрна) в art/promo/<цель>/ и лист
   выбора art/promo/<цель>_sheet.jpg:
       tools\hdart\.venv-qwen21\Scripts\python.exe tools\hdart\gen_promo.py draw
       ... draw --slot launcher_hero --seeds 6
2. finish - выбранный вариант доводится под место в проекте (обрезка по сторонам, размер,
   дуотон для лаунчера, JPEG в пределах бюджета) и кладётся туда, откуда его берёт сборка:
       ... gen_promo.py finish launcher_hero=3 site_hero=1 mod_piratez=2 mod_hd=4 emblem=1

Негатив действует только при cfg > 1 (R-040), поэтому по умолчанию cfg 4.
Запускать с PYTHONIOENCODING=utf-8 (R-001), если вывод перенаправлен.
"""
import argparse
import io
import os
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "art", "promo")
sys.path.insert(0, os.path.dirname(__file__))

STYLE = ("Painted illustration in the style of a 1990s PC strategy game box cover, gritty retro "
         "science fiction, confident brushwork, dramatic rim lighting, deep indigo and violet night "
         "palette with acid lime green accents. ")
NEGATIVE = ("text, letters, words, caption, title, logo, watermark, signature, frame, border, "
            "blurry, low resolution, jpeg artifacts, deformed hands, extra fingers, extra limbs, "
            "duplicated faces, identical faces, clones, nudity, cleavage, bare midriff, bare belly, "
            "lingerie, pin-up, glamour pose, gore, photograph, plastic 3d render")

SETUP_LEFT = ("Composition: the left two fifths of the picture are calm, empty, very dark shadow "
              "with no objects and no detail. ")


def SETUP_OUT(step):
    """Фон шага мастера: в лаунчер, 1920x1200 под окно любого размера, тот же дуотон, что у карточки."""
    return ("portal/src/Xp.Launcher/Assets/setup_%s.jpg" % step, 1920, 1200, 350, "duotone")


# цель: (промпт, ширина, высота модели, что получается в конце)
# итог: (путь от корня репозитория, ширина, высота, бюджет КБ, обработка)
SLOTS = {
    "launcher_hero": (
        STYLE + "A ragtag crew of four mutant space-pirate women in patched practical armor and "
        "scavenged alien gear stand on the open cargo ramp of a battered airship at night, looking "
        "out over a ruined futuristic city ruled by aliens. One shoulders a heavy improvised rifle, "
        "another holds a glowing lime-green energy blade. Alien saucers with lime running lights "
        "hang in the violet sky. The figures stand in the right half; the lower left of the "
        "picture is dark, calm shadow with no detail.",
        1792, 1120,
        ("portal/src/Xp.Launcher/Assets/hero.jpg", 1280, 800, 400, "duotone")),
    "site_hero": (
        STYLE + "Wide panoramic view of a pirate hideout carved into a desert canyon at dusk in "
        "the year 2601. A patched-together gunship airship is docked on a rock ledge, a crew of "
        "mutant pirate women in mismatched armor loads crates of loot, lanterns and smoke, "
        "and a huge alien mothership looms on the horizon under a violet sky.",
        1792, 1120,
        ("portal/src/Xp.Portal/wwwroot/img/hero.jpg", 1280, 800, 300, "color")),
    "mod_piratez": (
        STYLE + "Wide banner: a gang of five battle-hardened mutant pirate women shoulder to "
        "shoulder, waist-up, faces in the middle of the picture. Every face is different: one "
        "with pale green mutant skin, one with a cybernetic eye, one older with a scarred cheek, "
        "one with small tusks, one with a shaved head and tattoos. They wear heavy full-coverage "
        "gear: long patched coats buttoned up, high collars, padded jackets, bulky scrap-metal "
        "armor plates over the chest and belly, bandanas and goggles. They hold improvised guns "
        "and a cutlass and look tough and dangerous, not glamorous. A battered airship and a "
        "violet sky with alien saucers behind them.",
        1920, 1088,
        ("portal/src/Xp.Portal/wwwroot/img/mods/piratez.jpg", 960, 540, 200, "color")),
    "mod_hd": (
        STYLE + "Wide isometric view from above of a tactical battlefield at night, crisp and "
        "richly detailed: farmland with a wooden barn and a wheat field, a crashed flying saucer "
        "glowing lime green, a squad of armored soldiers taking cover behind a stone wall, "
        "every tile sharp and clean like high resolution pixel-perfect game art.",
        1920, 1088,
        ("portal/src/Xp.Portal/wwwroot/img/mods/hd.jpg", 960, 540, 200, "color")),
    # фоны мастера установки: карточка шага стоит слева, поэтому сюжет - в правой половине,
    # а левые две пятых - ровная тёмная тень, на которой ничего не спорит с текстом
    "setup_where": (
        STYLE + SETUP_LEFT + "In the right half: the cramped navigation cabin of a pirate airship "
        "at night. A grizzled mutant pirate woman navigator in a long patched coat and goggles on "
        "her forehead leans over a chart table covered with old paper maps, a brass compass and a "
        "flickering lime-green holographic globe of Earth. Through a round porthole behind her, "
        "alien saucers drift over a ruined city.",
        1792, 1120, SETUP_OUT("where")),
    "setup_ufo": (
        STYLE + SETUP_LEFT + "In the right half: two pirate women in patched armor with flashlights "
        "break open a dusty military crate in a long-abandoned underground 20th-century defense "
        "base. Behind them in the hangar gloom stands a rusty old interceptor jet and faded "
        "soldiers' armor on racks; their flashlight beams cut through the dust.",
        1792, 1120, SETUP_OUT("ufo")),
    "setup_parts": (
        STYLE + SETUP_LEFT + "In the right half: the cargo hold of a pirate airship stacked with loot "
        "- crates, barrels, racks of improvised rifles and alien gadgets glowing lime green. A "
        "stocky pirate quartermaster woman with a bandana and a scarred face checks items off a "
        "long list on a clipboard, a pencil behind her ear.",
        1792, 1120, SETUP_OUT("parts")),
    "setup_install": (
        STYLE + SETUP_LEFT + "In the right half: the engine room of a pirate airship being made ready "
        "for flight. A pirate mechanic woman in overalls and welding goggles works on a huge "
        "patched-together engine, sparks flying, pipes and cables everywhere, a gauge needle "
        "climbing, warm orange sparks against the violet gloom.",
        1792, 1120, SETUP_OUT("install")),
    "setup_done": (
        STYLE + SETUP_LEFT + "In the right half: a battered pirate airship lifts off from a canyon "
        "hideout at dawn, engines glowing lime green, crew of pirate women waving from the open "
        "deck rail, heading toward a sky with distant alien saucers. Hopeful, adventurous mood.",
        1792, 1120, SETUP_OUT("done")),
    "emblem": (
        "Flat vector emblem, centered, bold simple silhouette readable at 32 pixels: a grinning "
        "pirate skull with a bandana over crossed improvised rifle and energy blade, acid lime "
        "green and pale mint on a dark violet circle, plain dark violet background.",
        1024, 1024,
        ("art/promo/emblem.png", 512, 512, 0, "png")),
}

# С героинями (Vitali 22.10: «замени все фотки на фотки с нашими 6 героинями, разнообразь»): шесть беглянок
# M1-M6 с опорами лиц, как gen_screens.py --cast - лор, опоры и тело оттуда же (CAST_HEAD). Карточка лаунчера
# теперь не одна: hero_<n>.jpg, лаунчер берёт случайную при каждом запуске. Кадр 1280x800 - три опоры и больше
# не помещаются в карту (R-213). Север - капитан, Искра - драчунья, Шпилька - механик и замки, Базальт - сила,
# Рысь - пилот, Тихая - точность.
HERO_RIGHT = ("Composition: the figures stand in the right half, the lower left of the picture is dark calm "
              "shadow with no detail. ")


def HERO_OUT(n):
    return ("portal/src/Xp.Launcher/Assets/hero_%d.jpg" % n, 1280, 800, 400, "tint")


CAST_SLOTS = {
    "cast_hero_1": ([1, 2, 4], HERO_RIGHT + "The three women stand on the open cargo ramp of a battered pirate "
                    "airship at night, looking out over a ruined futuristic city ruled by aliens: Sever, the woman "
                    "from Picture 1, the captain, in a long dark coat with a cutlass at her hip; Iskra, the woman "
                    "from Picture 2, shoulders a heavy improvised rifle with a fierce grin; Bazalt, the woman from "
                    "Picture 3, the tallest and strongest, holds a glowing lime-green energy blade. Alien saucers "
                    "with lime running lights hang in the violet sky.", HERO_OUT(1)),
    "cast_hero_2": ([3, 5, 6], HERO_RIGHT + "A huge dark hangar carved into rock before a night raid: a battered "
                    "patched-together pirate gunship on the pad, work lights cone down through haze. Shpilka, the "
                    "woman from Picture 1, the mechanic, tightens a bolt on a landing strut, a wrench in her hand; "
                    "Rys, the woman from Picture 2, the pilot, in a leather flight jacket with goggles around her "
                    "neck, climbs the ladder to the cockpit; Tikhaya, the woman from Picture 3, checks a long rifle, "
                    "her black braid over one shoulder.", HERO_OUT(2)),
    "cast_hero_3": ([5], HERO_RIGHT + "Night sky seen through the riveted brass frame of a pirate gunship "
                    "cockpit in a steep dive: a glowing alien saucer flees into the storm clouds, lime tracer fire "
                    "between them. Rys, the woman from Picture 1, the pilot, grips the controls at the right in "
                    "three-quarter view, a headset over her copper curls, her face lit by the dim gauges, a "
                    "fearless smile.", HERO_OUT(3)),
    "cast_hero_4": ([6, 2], HERO_RIGHT + "A rooftop of a ruined skyscraper at dawn over a burning city: Tikhaya, "
                    "the woman from Picture 1, lies prone behind a long sniper rifle at the right, calm and precise, "
                    "her black braid on her shoulder; Iskra, the woman from Picture 2, kneels beside her with "
                    "binoculars, pointing at a distant alien saucer landing among the towers.", HERO_OUT(4)),
    "cast_hero_5": ([4, 2, 3], HERO_RIGHT + "Boarding action inside a crashed alien saucer: smooth ribbed walls, "
                    "lime light panels, smoke. Bazalt, the woman from Picture 1, the tallest and strongest, forces a "
                    "sliding alien door open with her bare hands; Iskra, the woman from Picture 2, covers her with "
                    "a pistol and a knife; Shpilka, the woman from Picture 3, crouches at the door panel picking "
                    "its lock with a glowing tool.", HERO_OUT(5)),
    "cast_hero_6": ([1, 3], HERO_RIGHT + "The bridge of a pirate airship in a thunderstorm at night: rain lashes "
                    "the big riveted windows, lightning lights up an alien mothership in the clouds. Sever, the "
                    "woman from Picture 1, the captain, holds the brass steering wheel at the right, her silver bob "
                    "wet, her long dark coat; Shpilka, the woman from Picture 2, pulls a big lever beside her.",
                    HERO_OUT(6)),
    # фоны мастера установки: карточка шага слева, сюжет справа (SETUP_LEFT)
    "cast_setup_where": ([1], SETUP_LEFT + "In the right half: the cramped navigation cabin of a pirate airship at "
                         "night. Sever, the woman from Picture 1, the captain, in a long dark coat, leans over a chart "
                         "table covered with old paper maps, a brass compass and a flickering lime-green holographic "
                         "globe of Earth, her silver bob lit by it. Through a round porthole behind her, alien saucers "
                         "drift over a ruined city.", SETUP_OUT("where")),
    "cast_setup_ufo": ([4, 2], SETUP_LEFT + "In the right half: a long-abandoned underground 20th-century defense "
                       "base. Bazalt, the woman from Picture 1, the tallest and strongest, pries open a dusty military "
                       "crate with a crowbar; Iskra, the woman from Picture 2, holds a flashlight over it. Behind them "
                       "in the hangar gloom stands a rusty old interceptor jet, flashlight beams cut through the dust.",
                       SETUP_OUT("ufo")),
    "cast_setup_parts": ([6], SETUP_LEFT + "In the right half: the cargo hold of a pirate airship stacked with loot - "
                         "crates, barrels, racks of improvised rifles and alien gadgets glowing lime green. Tikhaya, "
                         "the woman from Picture 1, precise and calm, checks items off a long list on a clipboard, a "
                         "pencil behind her ear, her black braid over one shoulder.", SETUP_OUT("parts")),
    "cast_setup_install": ([3], SETUP_LEFT + "In the right half: the engine room of a pirate airship being made "
                           "ready for flight. Shpilka, the woman from Picture 1, the mechanic, in overalls with rolled "
                           "sleeves and welding goggles pushed up, her chestnut hair held by a metal bobby pin, works "
                           "on a huge patched-together engine, sparks flying, pipes and cables everywhere.",
                           SETUP_OUT("install")),
    "cast_setup_done": ([5, 1, 2], SETUP_LEFT + "In the right half: a battered pirate airship lifts off from a "
                        "canyon hideout at dawn, engines glowing lime green. On the open deck rail Rys, the woman from "
                        "Picture 1, waves, Sever, the woman from Picture 2, the captain, looks ahead, Iskra, the woman "
                        "from Picture 3, raises a fist. Hopeful, adventurous mood.", SETUP_OUT("done")),
    "cast_site_hero": ([1, 4, 6], "Wide panoramic view of a pirate hideout carved into a desert canyon at dusk in "
                       "the year 2601. A patched-together gunship airship is docked on a rock ledge; Sever, the woman "
                       "from Picture 1, the captain, directs the loading; Bazalt, the woman from Picture 2, carries a "
                       "heavy crate of loot on her shoulder; Tikhaya, the woman from Picture 3, keeps watch with a "
                       "rifle; lanterns and smoke, a huge alien mothership looms on the horizon under a violet sky.",
                       ("portal/src/Xp.Portal/wwwroot/img/hero.jpg", 1280, 800, 300, "color")),
}
for _n, (_ids, _scene, _out) in CAST_SLOTS.items():
    SLOTS[_n] = (STYLE + _scene, 1280, 800, _out)

# дуотон карточки игры: тени, середина, свет (LAUNCHER_UI.md, «арт карточки»); свет чуть поднят,
# иначе на 1280x800 рисунок тонет в двух почти одинаковых синих
DUOTONE = [(0.0, (0x18, 0x08, 0x10)), (0.45, (0x18, 0x18, 0x68)), (0.8, (0x18, 0x58, 0x88)),
           (1.0, (0x70, 0xA8, 0xC8))]


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


def draw(args):
    from PIL import Image
    # --slot setup_where,setup_ufo или по приставке: --slot setup_*
    names = [s for part in args.slot.split(",") if part
             for s in ([k for k in SLOTS if k.startswith(part[:-1])] if part.endswith("*") else [part])] or list(SLOTS)
    for n in names:
        if n not in SLOTS:
            raise SystemExit("нет такой цели: %s (есть %s)" % (n, ", ".join(SLOTS)))
    pipe, torch = load_pipe(args.offload)
    total = len(names) * args.seeds
    done, t0 = 0, time.time()
    for n in names:
        prompt, w, h, _ = SLOTS[n]
        extra, neg = {}, NEGATIVE
        if n in CAST_SLOTS:
            # опоры - только лица героинь; тело и одежду задаёт текст (gen_screens.CAST_HEAD)
            import gen_screens
            ids, scene, _ = CAST_SLOTS[n]
            refs = [Image.open(os.path.join(gen_screens.CAST_DIR, "M%d_face.png" % m)).convert("RGB") for m in ids]
            extra = dict(image=refs, output_resolution=gen_screens.CAST_RES)
            neg = NEGATIVE + gen_screens.CAST_NEG
            prompt = STYLE + gen_screens.CAST_HEAD + scene
        os.makedirs(os.path.join(OUT, n), exist_ok=True)
        for i in range(1, args.seeds + 1):
            path = os.path.join(OUT, n, "%s_%d.png" % (n, i))
            if os.path.exists(path) and not args.force:
                print("%s вариант %d уже есть - пропускаю" % (n, i), flush=True)
                done += 1
                continue
            seed = args.seed + i * 7919
            t1 = time.time()
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


def sheet(n):
    """Лист выбора: варианты с номерами, каждый уменьшен до 480 по ширине."""
    from PIL import Image, ImageDraw
    d = os.path.join(OUT, n)
    files = sorted((f for f in os.listdir(d) if f.endswith(".png")),
                   key=lambda f: int(f.rsplit("_", 1)[1].split(".")[0]))
    if not files:
        return
    tiles = []
    for f in files:
        im = Image.open(os.path.join(d, f)).convert("RGB")
        im = im.resize((480, round(480 * im.height / im.width)), Image.LANCZOS)
        dr = ImageDraw.Draw(im)
        dr.rectangle((0, 0, 34, 22), fill=(0, 0, 0))
        dr.text((8, 5), f.rsplit("_", 1)[1].split(".")[0], fill=(128, 208, 0))
        tiles.append(im)
    cols = 3
    rows = (len(tiles) + cols - 1) // cols
    th = tiles[0].height
    board = Image.new("RGB", (cols * 484 + 4, rows * (th + 4) + 4), (16, 0, 16))
    for k, t in enumerate(tiles):
        board.paste(t, (4 + (k % cols) * 484, 4 + (k // cols) * (th + 4)))
    board.save(os.path.join(OUT, "%s_sheet.jpg" % n), quality=88)


def cover(im, w, h):
    """Обрезка по центру под нужные стороны, затем уменьшение."""
    from PIL import Image
    k = max(w / im.width, h / im.height)
    im = im.resize((max(w, round(im.width * k)), max(h, round(im.height * k))), Image.LANCZOS)
    x, y = (im.width - w) // 2, (im.height - h) // 2
    return im.crop((x, y, x + w, y + h))


def duotone(im):
    from PIL import Image
    lut = []
    for c in range(3):
        for v in range(256):
            t = v / 255.0
            for (a, ca), (b, cb) in zip(DUOTONE, DUOTONE[1:]):
                if t <= b:
                    f = (t - a) / (b - a)
                    lut.append(round(ca[c] + (cb[c] - ca[c]) * f))
                    break
    return Image.merge("RGB", [im.convert("L")] * 3).point(lut)


def jpeg_under(im, path, kb):
    """Самое высокое качество JPEG, которое укладывается в бюджет."""
    for q in range(92, 49, -3):
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=q, optimize=True, progressive=True)
        if buf.tell() <= kb * 1024:
            break
    with open(path, "wb") as f:
        f.write(buf.getvalue())
    return q, buf.tell()


def finish(args):
    from PIL import Image
    for pick in args.picks:
        n, _, i = pick.partition("=")
        if n not in SLOTS or not i.isdigit():
            raise SystemExit("ожидаю цель=номер, например launcher_hero=3: %s" % pick)
        src = os.path.join(OUT, n, "%s_%s.png" % (n, i))
        if not os.path.exists(src):
            raise SystemExit("нет варианта: %s" % src)
        rel, w, h, kb, mode = SLOTS[n][3]
        dst = os.path.join(ROOT, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        im = cover(Image.open(src).convert("RGB"), w, h)
        if mode == "duotone":
            im = duotone(im)
        elif mode == "tint":
            # героини в чистом дуотоне теряют лица и цвет кожи: дуотон наполовину, рисунок виден
            im = Image.blend(im, duotone(im), 0.5)
        if mode == "png":
            im.save(dst, optimize=True)
            print("%s <- вариант %s: %s, %dx%d, %d КБ" % (n, i, rel, w, h, os.path.getsize(dst) // 1024))
        else:
            q, size = jpeg_under(im, dst, kb)
            print("%s <- вариант %s: %s, %dx%d, качество %d, %d КБ (бюджет %d)"
                  % (n, i, rel, w, h, q, size // 1024, kb))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("draw")
    d.add_argument("--slot", default="", help="цели через запятую, setup_* - по приставке; пусто - все")
    d.add_argument("--seeds", type=int, default=4, help="вариантов на цель")
    d.add_argument("--seed", type=int, default=2601)
    d.add_argument("--steps", type=int, default=40)
    d.add_argument("--cfg", type=float, default=4.0)
    d.add_argument("--offload", default="model", choices=["model", "none"])
    d.add_argument("--force", action="store_true", help="перерисовать уже готовые варианты")
    f = sub.add_parser("finish")
    f.add_argument("picks", nargs="+", help="цель=номер варианта")
    args = ap.parse_args()
    draw(args) if args.cmd == "draw" else finish(args)


if __name__ == "__main__":
    main()
