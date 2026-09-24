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
    "emblem": (
        "Flat vector emblem, centered, bold simple silhouette readable at 32 pixels: a grinning "
        "pirate skull with a bandana over crossed improvised rifle and energy blade, acid lime "
        "green and pale mint on a dark violet circle, plain dark violet background.",
        1024, 1024,
        ("art/promo/emblem.png", 512, 512, 0, "png")),
}

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
    names = [args.slot] if args.slot else list(SLOTS)
    for n in names:
        if n not in SLOTS:
            raise SystemExit("нет такой цели: %s (есть %s)" % (n, ", ".join(SLOTS)))
    pipe, torch = load_pipe(args.offload)
    total = len(names) * args.seeds
    done, t0 = 0, time.time()
    for n in names:
        prompt, w, h, _ = SLOTS[n]
        os.makedirs(os.path.join(OUT, n), exist_ok=True)
        for i in range(1, args.seeds + 1):
            path = os.path.join(OUT, n, "%s_%d.png" % (n, i))
            if os.path.exists(path) and not args.force:
                print("%s вариант %d уже есть - пропускаю" % (n, i), flush=True)
                done += 1
                continue
            seed = args.seed + i * 7919
            t1 = time.time()
            img = pipe(prompt=prompt, negative_prompt=NEGATIVE, true_cfg_scale=args.cfg,
                       width=w, height=h, num_inference_steps=args.steps,
                       generator=torch.Generator("cuda").manual_seed(seed)).images[0]
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
    d.add_argument("--slot", default="", help="одна цель; пусто - все")
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
