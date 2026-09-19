#!/usr/bin/env python3
r"""
Paints an extracted sprite sheet into HD with Stable Diffusion XL (img2img +
ControlNet tile & canny), then downsamples it to the pack scale.

    <venv>\Scripts\python.exe tools\hdart\gen_hd.py --sheets <sheets folder> --set CULTIVAT.PCK [--test]
        [--strength 0.8] [--refine 0.45] [--steps 30] [--cfg 6.5] [--seed 1234] [--tile 0.6] [--tile-blur 0.35]
        [--canny 0.2] [--init smooth|nearest] [--sweep 0.7,0.8,0.9 | tile=0.3,0.6] [--matrix] [--frame 9]
        [--base stabilityai/stable-diffusion-xl-base-1.0] [--gen-scale 16] [--prompt "..."] [--subject "..."] [--out painted_x4.png]
        [--variants 2 [--only variants] [--variant-looks "..."] [--variant-frames 0,3]]

Input:  <sheets>/<SET>/original.png + layout.json (from extract_pck.py).
Output: <sheets>/<SET>/painted_x<gen-scale>.png (what the model produced),
        <sheets>/<SET>/painted_x<pack scale>.png (the sheet for build_pack.py),
        <sheets>/<SET>/crops/  (every generated crop, for looking at).
        With --variants N also painted_x<scale>.v1.png ... .vN.png (other paintings of the floors) and
        variants.json (which floors, which looks); build_pack.py makes <index>.v<n>.png of them.

How it works: every frame gets its own cell. Ground tiles (floors, and walkable objects that fill
the floor diamond - crops, flowers; layout.json says which, from the terrain's MCD) are repeated over
the cell on the isometric grid, so the painter sees a continuous field and paints terrain, not a
diamond-shaped planter on a background. Objects sit alone on the cell with the transparent background
filled by extending their own colors outward (so edges are not painted against a foreign color). The
cell is scaled `gen-scale` times (16: every 32x40 tile is 512x640 pixels - big on the canvas, so the
model keeps its details) with a smooth filter - the painter must
start from soft shapes, a nearest upscale makes it reproduce the blocks faithfully - and the cells are
painted two at a time, ground with ground (a terrain prompt) and objects with objects; the cells have
margins, so no seam ever crosses a sprite. The tile ControlNet keeps the colors and shapes of the
original, the canny one its edges;
`strength` says how far the painter may go (0.6 = touch-up, 0.8 = repaint, 0.9 = reinvent). A second
pass (`refine`, 0.45) repaints the first pass's output with sharp controls: pass one gets the shapes
and colors right but comes out soft, pass two puts texture and detail on it.
`--sweep 0.7,0.8,0.9` paints the first crop at several strengths into crops/sweep.png to pick one.

Ground variants (`--variants N`): every floor is painted N more times, each time with other words
(short grass / tall grass, lighter / darker sand) and a slightly recoloured input. The engine lays the
paintings over the map as smooth patches with ragged, blended edges, so a field of one floor stops
looking tiled. Its scale has the base painting in the middle: v1, v3 ... one way from it, v2, v4 ... the
other way, so the looks come in two directions (GROUND_LOOKS). The kind of a floor (grass, soil, sand,
snow, rock, mud, forest floor) is read from its hint; floors of no known kind get no variants unless
`--variant-looks` gives the words. `--only variants` paints only the variants (the base painting stays).

Models (~12 GB) live in E:\models (--models <dir> or the HD_MODELS variable; setup_gen.ps1 downloads
them there, `gen_hd.py --download-only` does the same):
  RunDiffusion/Juggernaut-XL-v9 (SDXL fine-tune), madebyollin/sdxl-vae-fp16-fix,
  xinsir/controlnet-tile-sdxl-1.0, diffusers/controlnet-canny-sdxl-1.0
"""
import argparse
import json
import os
import sys
import time
import subjects_terrain

# where the models live: E:\models (or --models / the HD_MODELS variable); must be set before any
# Hugging Face import looks at the environment
DEFAULT_MODELS_DIR = os.environ.get("HD_MODELS", r"E:\models" if os.name == "nt" else os.path.expanduser("~/hd-models"))
if "--models" in sys.argv:
    DEFAULT_MODELS_DIR = sys.argv[sys.argv.index("--models") + 1]
os.environ["HF_HOME"] = DEFAULT_MODELS_DIR
os.environ["HF_HUB_CACHE"] = os.path.join(DEFAULT_MODELS_DIR, "hub")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")  # Windows without developer mode: plain files, works fine

import numpy as np
from PIL import Image, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xcom_sprites as xs  # noqa: E402

# CLIP reads at most 77 tokens (about 55 words), the rest is dropped: keep the style short, the
# subject texts are counted too
STYLE = ("isometric game tile of {subject}, pre-rendered 3D game asset, realistic matte materials, "
         "detailed natural textures, soft light from the upper left, muted earthy colors, sharp focus, "
         "highly detailed, Xenonauts style")
# ground tiles are painted as a continuous field (the frame repeated on the isometric grid), so the
# prompt asks for terrain, not for an object
STYLE_GROUND = ("seamless isometric terrain texture of {subject}, top-down view, pre-rendered 3D game asset, "
                "realistic matte materials, detailed natural textures, soft light from the upper left, "
                "muted earthy colors, sharp focus, highly detailed, Xenonauts style")
NEGATIVE = ("cartoon, black outlines, vector art, cel shading, glossy, cute, anime, pixel art, pixelated, "
            "blurry, soft, jpeg artifacts, text, watermark, frame, border, oversaturated, deformed, "
            # тайл - кусок земли, а не снимок товара: иначе подставка под кактусом
            # читается как горшок, а сам объект встаёт в центр кадра и уезжает из силуэта
            "potted plant, flower pot, planter, wooden stand, pedestal, tabletop, product photo")
# unit sets: the frames are parts of a character (legs, torso, arms, a weapon) in eight directions,
# painted one by one; the prompt asks for the character's material, the controls keep every part's
# exact shape (the parts must still fit together when the engine assembles them)
STYLE_UNIT = ("isometric game character sprite, {subject}, pre-rendered 3D game asset, realistic matte "
              "materials, detailed cloth and armor textures, soft light from the upper left, sharp focus, "
              "highly detailed, Xenonauts style")
UNIT_SETS = {"XCOM_0.PCK", "XCOM_1.PCK", "XCOM_2.PCK", "SECTOID.PCK", "FLOATER.PCK", "SNAKEMAN.PCK", "MUTON.PCK",
             "ETHEREAL.PCK", "CHRYS.PCK", "CELATID.PCK", "SILACOID.PCK", "ZOMBIE.PCK", "CYBER.PCK", "X_REAP.PCK",
             "X_ROB.PCK", "TANKS.PCK", "CIVM.PCK", "CIVF.PCK", "HANDOB.PCK", "FLOOROB.PCK"}

# Тема набора идёт в промпт ПЕРЕД постоянным стилевым хвостом, а CLIP обрезает всё
# после 77 токенов. Слишком длинная тема выбрасывает из промпта "Xenonauts style" -
# то есть ровно то, ради чего стиль и задавался. Держать в пределах ~10-12 слов:
# к теме ещё добавляется покадровая подсказка, и вместе они должны влезть.
SUBJECTS = {
    # Наборы X-Piratez сюда НЕ пишем: их тема берётся из subjects_terrain.py по
    # террейну из рулсетов. Я один раз написал их руками и оба раза угадал не то
    # (A_PODS - не гидропоника, а пол базы пришельцев). См. RAKES.md, R-013.
    # --- ванильный UFO ---
    "CULTIVAT.PCK": "farmland: crop fields, hedges, wooden fences, stone walls, fruit trees, dirt",
    "BARN.PCK": "farm barn: wooden walls, roof, doors, windows, hay",
    "ROADS.PCK": "country road, asphalt, gravel, road markings",
    "FRNITURE.PCK": "furniture: tables, chairs, beds, cupboards, wooden floor",
    "FOREST.PCK": "forest: pine trees, bushes, grass, rocks, logs",
    "JUNGLE.PCK": "jungle: tropical trees, palms, dense bushes, mud",
    "DESERT.PCK": "desert: sand dunes, rocks, dry bushes, cactus",
    "MOUNT.PCK": "mountains: rocks, cliffs, snow patches, scree",
    "POLAR.PCK": "polar: snow, ice, frozen ground, icy rocks",
    "URBAN.PCK": "city street: buildings, concrete walls, windows, doors, shop fronts",
    "URBITS.PCK": "city props: cars, benches, lamps, hydrants",
    "UFO1.PCK": "alien spacecraft interior and hull: metallic panels, glowing consoles",
    "U_EXT02.PCK": "alien spacecraft hull: dark grey metal plating, curved walls",
    "U_WALL02.PCK": "alien spacecraft walls: metal panels, doors, alien technology",
    "U_BITS.PCK": "alien spacecraft parts: power source, navigation console",
    "U_DISEC2.PCK": "alien examination room: tables, tanks, instruments",
    "U_OPER2.PCK": "alien operating theatre: tables, lamps, alien devices",
    "U_PODS.PCK": "alien pods and tanks: green glowing containers",
    "U_BASE.PCK": "alien base: dark metal corridors, glowing panels",
    "XBASE1.PCK": "military base interior: concrete, metal doors, computers, beds",
    "XBASE2.PCK": "military base interior: hangar, storage, machinery, elevator",
    "PLANE.PCK": "military transport aircraft interior and hull: metal, seats, ramp",
    "LIGHTNIN.PCK": "sleek military aircraft hull: dark metal, ramp",
    "AVENGER.PCK": "advanced military aircraft hull: alien alloy, ramp",
    "MARS.PCK": "martian surface: red rocks, sand, alien structures",
    "BRAIN.PCK": "alien brain organism: pink flesh, tubes, pulsing tissue",
    "XCOM_0.PCK": "a soldier in a grey-blue combat jumpsuit with a harness, body part of the sprite",
    "XCOM_1.PCK": "a soldier in white hard personal armor plates, body part of the sprite",
    "XCOM_2.PCK": "a soldier in a bulky flying power suit with a helmet, body part of the sprite",
    "SECTOID.PCK": "a small grey alien with a big head and large black eyes, body part of the sprite",
    "FLOATER.PCK": "a cyborg alien in a red cloak floating on a jet engine, body part of the sprite",
    "SNAKEMAN.PCK": "a snake-like alien with a scaly tail and yellow-green skin, body part of the sprite",
    "MUTON.PCK": "a muscular alien in green armor plates, body part of the sprite",
    "ETHEREAL.PCK": "an alien in a purple hooded robe, body part of the sprite",
    "CHRYS.PCK": "an insectoid alien with a purple chitin shell and claws",
    "CELATID.PCK": "a floating green blob alien with tentacles",
    "SILACOID.PCK": "a glowing molten rock creature",
    "ZOMBIE.PCK": "a shambling human zombie in torn clothes, body part of the sprite",
    "CYBER.PCK": "a metallic disc-shaped robot with a red eye",
    "X_REAP.PCK": "a large two-headed furry beast, body part of the sprite",
    "X_ROB.PCK": "an alien walking robot with metal legs and cannons, body part of the sprite",
    "TANKS.PCK": "an armored tracked or hovering tank, part of the vehicle",
    "CIVM.PCK": "a male civilian in casual clothes, body part of the sprite",
    "CIVF.PCK": "a female civilian in casual clothes, body part of the sprite",
    "HANDOB.PCK": "weapons held in hand: rifles, pistols, launchers",
    "FLOOROB.PCK": "items lying on the floor: weapons, ammo clips, grenades",
    "SMOKE.PCK": "smoke puffs and fire",
    "HIT.PCK": "bullet impact sparks",
    "X1.PCK": "explosion fireball",
}

# ground variants (--variants N): other paintings of every floor, laid over the map by the engine as
# patches. Its scale has the base painting in the middle, v1, v3 ... on one side and v2, v4 ... on the
# other, so a kind of ground has two directions of looks, each a list of steps (v1 = first step of the
# first direction, v2 = first step of the second, v3 = second step of the first ...). A look: the words
# put before the frame's subject, and the colour change of the painter's input (brightness,
# saturation, warmth) - build_pack.py matches the variant's colours to the original recoloured the same way
GROUND_LOOKS = {
    "grass": ([("short trimmed sparse grass", (1.07, 0.88, 0.03)), ("very short dry grass, bare soil showing through", (1.14, 0.76, 0.07))],
              [("taller denser grass", (0.92, 1.10, -0.02)), ("tall thick lush grass", (0.85, 1.18, -0.03))]),
    "soil": ([("drier lighter soil", (1.09, 0.88, 0.02)), ("dry cracked soil with small pebbles", (1.16, 0.80, 0.03))],
             [("darker moist soil", (0.90, 1.08, 0.0)), ("dark wet soil with small puddles", (0.82, 1.12, -0.01))]),
    "sand": ([("lighter sand with fine wind ripples", (1.09, 0.88, 0.0)), ("pale sand with long wind ripples", (1.16, 0.80, 0.0))],
             [("darker coarse sand with small pebbles", (0.90, 1.08, 0.03)), ("darker reddish coarse sand with pebbles", (0.82, 1.15, 0.05))]),
    "snow": ([("fresh smooth snow", (1.05, 0.85, -0.01)), ("fresh powder snow drifts", (1.09, 0.78, -0.02))],
             [("wind-packed snow with icy patches", (0.93, 1.08, -0.04)), ("old grey snow with blue ice", (0.86, 1.14, -0.06))]),
    "rock": ([("lighter dusty weathered rock", (1.08, 0.88, 0.02)), ("pale dusty rock with cracks", (1.15, 0.80, 0.03))],
             [("darker rock with loose gravel", (0.90, 1.06, 0.0)), ("dark rough rock with scree", (0.82, 1.10, -0.01))]),
    "mud": ([("drier mud with cracks", (1.09, 0.88, 0.02)), ("dried cracked mud", (1.16, 0.80, 0.03))],
            [("wet dark mud with puddles", (0.89, 1.08, -0.01)), ("deep wet mud with water puddles", (0.81, 1.12, -0.02))]),
    "forest": ([("forest floor with dry fallen leaves", (1.06, 0.92, 0.06)), ("forest floor covered with dry brown leaves and needles", (1.12, 0.85, 0.10))],
               [("forest floor with moss and small ferns", (0.91, 1.10, -0.03)), ("thick green moss and ferns", (0.84, 1.18, -0.05))]),
}
# which kind a floor is: the words of its hint (or of the set's subject, the part before the colon). The
# ground of "a boulder on grass" is what follows "on", of "sand with a skull" what comes before "with";
# of several kinds in that part the last word wins ("dry sandy soil" is soil). Made ground (a gravel
# road, an earth floor in a base) gets no variants: its tiles are laid out on purpose
KIND_WORDS = {
    "snow": ("snow", "snowy", "ice", "icy", "frozen", "frost", "polar"),
    "sand": ("sand", "sandy", "dune", "dunes", "desert"),
    "grass": ("grass", "grassy", "lawn", "meadow", "sprout", "sprouts", "turf"),
    "soil": ("soil", "dirt", "earth", "ploughed", "plowed", "tilled", "furrows", "farmland"),
    "mud": ("mud", "muddy", "swamp", "bog"),
    "forest": ("moss", "leaves", "needles", "ferns", "undergrowth", "forest", "jungle"),
    "rock": ("rock", "rocks", "rocky", "stone", "stones", "gravel", "scree", "boulder", "boulders", "cliff", "cliffs", "mountains"),
}
MADE_GROUND = ("road", "roads", "asphalt", "concrete", "pavement", "kerb", "tiled", "tile", "tiles", "plate", "metal",
               "floor", "carpet", "wooden", "planks", "brick", "bricks")


def ground_kind(text):
    """The kind of ground a hint or subject describes (a GROUND_LOOKS key), or None."""
    import re
    text = (text or "").lower()
    part = text
    if " on " in text:
        part = text.split(" on ")[-1]
    elif " with " in text:
        part = text.split(" with ")[0]
    if any(w in MADE_GROUND for w in re.findall(r"[a-z]+", part)):
        return None
    for chunk in (part, text):
        best = None
        for word in re.findall(r"[a-z]+", chunk):
            for kind, words in KIND_WORDS.items():
                if word in words:
                    best = kind
        if best:
            return best
    return None


def variant_looks(kind, count):
    """The looks of variants 1..count of a ground kind: [(words, (brightness, saturation, warmth))]."""
    low, high = GROUND_LOOKS[kind]
    out = []
    for n in range(1, count + 1):
        side = low if n % 2 else high
        step = (n - 1) // 2
        words, tone = side[min(step, len(side) - 1)]
        if step >= len(side):
            # beyond the listed steps: the last look, recoloured further
            extra = step - len(side) + 1
            tone = tuple(1.0 + (t - 1.0) * (1.0 + 0.5 * extra) for t in tone[:2]) + (tone[2] * (1.0 + 0.5 * extra),)
        out.append((words, tuple(tone)))
    return out


def parse_looks(text):
    """--variant-looks / looks.json: "words|words@1.05,0.9,0.02|..." in variant order (v1|v2|v3...);
    `@brightness,saturation,warmth` is optional."""
    out = []
    for item in (text.split("|") if isinstance(text, str) else text):
        item = item.strip()
        tone = (1.0, 1.0, 0.0)
        if "@" in item:
            item, t = item.rsplit("@", 1)
            vals = [float(v) for v in t.split(",")]
            tone = tuple((vals + [1.0, 1.0, 0.0][len(vals):])[:3])
        out.append((item.strip(), tone))
    return out


def tint(rgb, tone):
    """Recolours an RGB image: brightness and saturation factors, warmth (+ = redder, - = bluer)."""
    b, sat, warm = tone
    a = np.asarray(rgb.convert("RGB")).astype(np.float32)
    luma = (a * np.array([0.299, 0.587, 0.114], np.float32)).sum(axis=2, keepdims=True)
    a = luma + (a - luma) * sat
    a = a * b * np.array([1.0 + warm, 1.0, 1.0 - warm], np.float32)
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGB")


# what single frames show (hints.py: the painter turned the wheat tile into orange cobs and dropped the
# apples without them): the hint replaces the subject for that frame, with the set's context after it.
# A hints.json next to the set's sheets ({"4": "...", ...}) adds or overrides.
from hints import hints_for  # noqa: E402


def fill_background(rgba, radius=5, blur=6.0):
    """Extends the sprite colors into the transparent area (OpenCV inpainting) so that the painter never
    sees a hard edge against a foreign color; returns an RGB image."""
    import cv2
    arr = np.array(rgba)
    rgb = arr[:, :, :3].copy()
    mask = (arr[:, :, 3] == 0).astype(np.uint8) * 255
    if mask.all():
        return Image.fromarray(np.full_like(rgb, 128))
    filled = cv2.inpaint(rgb[:, :, ::-1].copy(), mask, radius, cv2.INPAINT_TELEA)[:, :, ::-1]
    # soften the extended area (inpainting leaves streaks) and put the sprite itself back crisp
    soft = Image.fromarray(np.ascontiguousarray(filled)).filter(ImageFilter.GaussianBlur(blur))
    soft.paste(rgba.convert("RGB"), (0, 0), rgba.split()[3])
    return soft


def smooth_upscale(rgb, g):
    """Upscales the 1x image without blocks (Lanczos + a mild unsharp mask): soft shapes the painter
    fills with detail. A nearest upscale makes the tile ControlNet reproduce the 8x8 blocks faithfully,
    which is exactly what the first test showed."""
    up = rgb.resize((rgb.width * g, rgb.height * g), Image.LANCZOS)
    return up.filter(ImageFilter.UnsharpMask(radius=g * 0.4, percent=60, threshold=0))


def canny_image(rgb, low=60, high=140):
    import cv2
    gray = cv2.cvtColor(np.array(rgb), cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, low, high)
    return Image.fromarray(np.stack([edges] * 3, axis=-1))


def side_by_side(images, gap=8):
    """The images next to each other on a magenta strip (for comparing crops)."""
    w = sum(im.width for im in images) + gap * (len(images) - 1)
    h = max(im.height for im in images)
    out = Image.new("RGB", (w, h), (255, 0, 255))
    x = 0
    for im in images:
        out.paste(im.convert("RGB"), (x, 0))
        x += im.width + gap
    return out


MODELS = {
    "base": "RunDiffusion/Juggernaut-XL-v9",  # SDXL fine-tune: realistic, textured; stabilityai/stable-diffusion-xl-base-1.0 paints clay
    "vae": "madebyollin/sdxl-vae-fp16-fix",
    "tile": "xinsir/controlnet-tile-sdxl-1.0",
    "canny": "diffusers/controlnet-canny-sdxl-1.0",
}


def download_models():
    """Fetches every model into the models folder (safetensors only, fp16 variant of the base)."""
    from huggingface_hub import snapshot_download
    print("models folder:", DEFAULT_MODELS_DIR)
    os.makedirs(DEFAULT_MODELS_DIR, exist_ok=True)
    snapshot_download(MODELS["base"], allow_patterns=["*.json", "*.txt", "*.safetensors", "tokenizer*/*", "scheduler/*"],
                      ignore_patterns=["*.bin", "*.onnx", "*.msgpack", "*openvino*"])
    for key in ("vae", "tile", "canny"):
        snapshot_download(MODELS[key], allow_patterns=["*.json", "*.safetensors"], ignore_patterns=["*.bin"])
    print("done")


_PIPE = {}   # base -> готовый pipeline: в одном процессе модель грузится ОДИН раз


def load_pipeline(base=None):
    """base: an SDXL checkpoint in diffusers layout - a Hugging Face repo id (downloaded into the models
    folder on first use) or a local folder; None = plain SDXL base. Fine-tunes such as
    RunDiffusion/Juggernaut-XL-v9 give a far more realistic, textured look than the base model."""
    import torch
    from diffusers import AutoencoderKL, ControlNetModel, StableDiffusionXLControlNetImg2ImgPipeline
    import diffusers
    # diffusers 0.36+ renamed torch_dtype= to dtype= (the old name only warns, but keeps the log clean)
    ver = tuple(int(p) for p in diffusers.__version__.split(".")[:2] if p.isdigit())
    kw = {"dtype": torch.float16} if ver >= (0, 36) else {"torch_dtype": torch.float16}
    base = base or MODELS["base"]
    if base in _PIPE:
        return _PIPE[base]
    print("loading models from", DEFAULT_MODELS_DIR, "(downloaded there when missing, ~12 GB)... base:", base)
    tile = ControlNetModel.from_pretrained(MODELS["tile"], **kw)
    canny = ControlNetModel.from_pretrained(MODELS["canny"], **kw)
    vae = AutoencoderKL.from_pretrained(MODELS["vae"], **kw)
    common = dict(controlnet=[tile, canny], vae=vae, use_safetensors=True, **kw)
    try:
        pipe = StableDiffusionXLControlNetImg2ImgPipeline.from_pretrained(base, variant="fp16", **common)
    except Exception as e:  # no fp16 variant in this checkpoint: take the full-precision weights
        print("  (no fp16 variant: %s; loading the default weights)" % str(e).splitlines()[0][:100])
        pipe = StableDiffusionXLControlNetImg2ImgPipeline.from_pretrained(base, **common)
    pipe.to("cuda")
    pipe.set_progress_bar_config(disable=True)
    _PIPE[base] = pipe
    return pipe


# the built-in experiment list of --matrix: one frame painted with every variation, side by side
MATRIX = [
    ("baseline", {}),
    ("tile 0.3", {"tile": 0.3}),
    ("tile 0.65", {"tile": 0.65}),
    ("tile-blur 0.2", {"tile_blur": 0.2}),
    ("no canny", {"canny": 0.0}),
    ("no refine", {"refine": 0.0}),
    ("refine 0.6", {"refine": 0.6}),
    ("cfg 5", {"cfg": 5.0}),
    ("cfg 8", {"cfg": 8.0}),
    ("strength 0.9", {"strength": 0.9}),
    ("nearest init, tile 0.3", {"init": "nearest", "tile": 0.3}),
]

# neighbouring tiles of the isometric grid, in frame pixels: east/south are (16, 8) and (-16, 8)
ISO_STEP = (16, 8)


def derim_ground(frame_rgba, inner=0.72, pull=0.55, threshold=26.0):
    """Removes the tile's own edge from a ground frame: classic floor tiles carry a lighter or darker
    rim along the diamond (the grid the classic game shows), and a field tiled from them shows that
    lattice to the painter, which then paints it as paths or walls between the tiles. The rim's width
    is measured per edge (NW, NE, SW, SE): the widest band along the edge whose mean colour departs
    from the tile's interior (the inner half of the diamond) by more than `threshold` is the rim, at
    least the outer `1 - inner` of the radius always. Every rim pixel takes the colour of the pixel
    `pull` of the way towards the diamond's centre (never a rim pixel itself)."""
    arr = np.asarray(frame_rgba).copy()
    h, w = arr.shape[:2]
    cx, cy = (w - 1) / 2.0, h - 8.5
    ys, xs = np.mgrid[0:h, 0:w]
    d = np.abs(xs - cx) / (w / 2.0) + np.abs(ys - cy) / 8.0
    zone = diamond_mask(w, h) & (arr[:, :, 3] > 0)
    rgb = arr[:, :, :3].astype(np.float32)
    interior = zone & (d < 0.5)
    if interior.sum() < 8:
        return Image.fromarray(arr, "RGBA")
    mean_in = rgb[interior].mean(axis=0)
    quadrants = [
        (xs < cx) & (ys < cy), (xs >= cx) & (ys < cy),
        (xs < cx) & (ys >= cy), (xs >= cx) & (ys >= cy),
    ]
    starts = []
    for q in quadrants:
        d0 = inner
        for cand in np.arange(0.95, 0.49, -0.05):
            band = zone & q & (d >= cand)
            if band.sum() < 3:
                continue
            if np.linalg.norm(rgb[band].mean(axis=0) - mean_in) > threshold:
                d0 = min(d0, float(cand))
            else:
                break
        starts.append(d0)
    for y in range(h - 16, h):
        for x in range(w):
            if arr[y, x, 3] == 0:
                continue
            dd = d[y, x]
            q = (0 if y < cy else 2) + (0 if x < cx else 1)
            if dd < starts[q]:
                continue
            p = min(pull, starts[q] - 0.05)
            sx = int(round(cx + (x - cx) * p))
            sy = int(round(cy + (y - cy) * p))
            sx = min(max(sx, 0), w - 1)
            sy = min(max(sy, 0), h - 1)
            if arr[sy, sx, 3] > 0:
                arr[y, x, :3] = arr[sy, sx, :3]
    return Image.fromarray(arr, "RGBA")


def diamond_mask(w, h):
    """Boolean (h, w): the classic floor diamond of a frame, pixel-exact (rows h-16.. with half-widths
    2, 4, ..., 16, ..., 4, 2 for a 32-wide frame; scaled with the width)."""
    mask = np.zeros((h, w), dtype=bool)
    for r in range(1, 16):
        hw = (2 * r if r <= 8 else 2 * (16 - r)) * w // 32
        mask[h - 16 + r, w // 2 - hw:w // 2 + hw] = True
    return mask


def split_diamond(frame_rgba):
    """A ground frame split into its floor diamond (the bottom 16 rows inside the diamond) and the
    rest (whatever rises above or hangs beside it: a bank, a step, a stump)."""
    arr = np.asarray(frame_rgba)
    h, w = arr.shape[:2]
    inside = diamond_mask(w, h)
    diamond = arr.copy()
    diamond[~inside] = 0
    rest = arr.copy()
    rest[inside] = 0
    return Image.fromarray(diamond, "RGBA"), Image.fromarray(rest, "RGBA")


def tile_ground(frame_rgba, cell_w, cell_h, margin, reach=4, flips=True):
    """A ground frame repeated over the cell on the isometric lattice (back to front), so that the
    painter sees a continuous field instead of a diamond-shaped object on a background. The frame's own
    copy sits at (margin, margin) as in the sheet; the other copies are mirrored at random (a field of
    identical tiles reads as a pattern, and the painter repeats the pattern tile by tile)."""
    out = Image.new("RGBA", (cell_w, cell_h), (0, 0, 0, 0))
    mirrored = frame_rgba.transpose(Image.FLIP_LEFT_RIGHT)
    sx, sy = ISO_STEP
    offsets = []
    for i in range(-reach, reach + 1):
        for j in range(-reach, reach + 1):
            offsets.append((margin + sx * (i - j), margin + sy * (i + j), (i * 7 + j * 13) % 3 == 0 and (i, j) != (0, 0)))
    for ox, oy, flip in sorted(offsets, key=lambda o: (o[1], o[0])):
        if ox + frame_rgba.width <= 0 or oy + frame_rgba.height <= 0 or ox >= cell_w or oy >= cell_h:
            continue
        out.alpha_composite(mirrored if (flip and flips) else frame_rgba, (ox, oy))
    return out


def seamless_ground(cell, g, margin, frame_w=32, frame_h=40, band=0.25, flatten=0.5):
    """Makes a painted ground cell tile without seams: inside the floor diamond, a band along each
    edge is cross-faded with the field the painter continued beyond the opposite edge (shifted by the
    grid step), so that a tile's NE edge equals its own SW edge and so on; before that, `flatten` of the
    cell's slow brightness drift (the painter lights every tile a little differently, and a ramp per
    tile draws the grid) is removed. `cell` is the painted cell at scale g (RGB), the frame sits at
    (margin, margin)."""
    if flatten > 0:
        low = np.asarray(cell.filter(ImageFilter.GaussianBlur(6 * g))).astype(np.float32)
        arr = np.asarray(cell).astype(np.float32)
        arr = arr - flatten * (low - low.mean(axis=(0, 1), keepdims=True))
        cell = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), cell.mode)
    arr = np.asarray(cell).astype(np.float32)
    h, w = arr.shape[:2]
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    # frame coordinates in source pixels
    fx = (xs - margin * g) / g
    fy = (ys - margin * g) / g
    cx, cy = (frame_w - 1) / 2.0, frame_h - 8.5
    hx, hy = frame_w / 2.0, 8.0
    zone = fy >= frame_h - 16 - 0.5
    out = arr.copy()
    # the two grid directions: e runs SW (-1) -> NE (+1), f runs NW (-1) -> SE (+1)
    for sign_y, dx, dy in ((-1.0, hx, -hy), (1.0, hx, hy)):
        e = (fx - cx) / hx + sign_y * (fy - cy) / hy
        inside = (np.abs(e) <= 1.0) & zone & (np.abs((fx - cx) / hx - sign_y * (fy - cy) / hy) <= 1.0)
        wgt = np.clip((np.abs(e) - (1.0 - band)) / band, 0.0, 1.0) * 0.5
        wgt = np.where(inside, wgt, 0.0)
        # partner: the point one grid step across the opposite edge (a sample of the continued field)
        sx = np.clip(xs - np.sign(e) * dx * g, 0, w - 1).astype(np.int32)
        sy = np.clip(ys - np.sign(e) * dy * g, 0, h - 1).astype(np.int32)
        partner = arr[sy, sx]
        out = out * (1.0 - wgt[..., None]) + partner * wgt[..., None]
        arr = out.copy()
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), cell.mode)


def human_time(sec):
    """Секунды в «2 ч 05 м» / «3 м 20 с» / «45 с»."""
    sec = int(max(0, sec))
    if sec >= 3600:
        return "%d ч %02d м" % (sec // 3600, (sec % 3600) // 60)
    if sec >= 60:
        return "%d м %02d с" % (sec // 60, sec % 60)
    return "%d с" % sec


def frame_texture(frame_rgba):
    """(сколько цветов, средний перепад яркости между соседями) в непрозрачной части кадра.

    Ровный пол, нарисованный в три-четыре цвета, даёт мало цветов и малый перепад; каменистый
    или травяной - много и того и другого. По этим двум числам решается, снижать ли силу:
    на пустом ромбе силе 0.8 не за что зацепиться, и она выдумывает геометрию (RAKES.md, R-017)."""
    a = np.asarray(frame_rgba.convert("RGBA"), dtype=np.float32)
    m = a[:, :, 3] > 0
    if int(m.sum()) < 20:
        return 0, 0.0
    rgb = a[:, :, :3]
    colors = len(np.unique(rgb[m].astype(np.uint8), axis=0))
    lum = 0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]
    diffs = []
    for dy, dx in ((0, 1), (1, 0)):
        b = np.roll(np.roll(lum, -dy, 0), -dx, 1)
        mb = m & np.roll(np.roll(m, -dy, 0), -dx, 1)
        if dy:
            mb[-1, :] = False
        if dx:
            mb[:, -1] = False
        if mb.any():
            diffs.append(np.abs(lum - b)[mb])
    detail = float(np.concatenate(diffs).mean()) if diffs else 0.0
    return colors, detail


class Job:
    """Everything derived from the arguments before painting: per frame (cell) the painter's input and
    the control images, plus the crops (groups of cells painted together)."""

    def __init__(self, args, set_dir, info):
        self.args = args
        self.info = info
        self.set_dir = set_dir
        g = self.g = args.gen_scale
        m = self.margin = info["margin"]
        self.sheet = xs.Sheet(info["frame_w"], info["frame_h"], info["count"], info["columns"], m)
        self.original = Image.open(os.path.join(set_dir, "original.png")).convert("RGBA")
        self.big = self.original.resize((self.original.width * g, self.original.height * g), Image.NEAREST)
        self.ground = info.get("ground") or [False] * info["count"]
        self.base = info.get("base") or [False] * info["count"]
        self.hints = hints_for(info["set"])
        hints_file = os.path.join(set_dir, "hints.json")
        if os.path.exists(hints_file):
            with open(hints_file) as f:
                self.hints.update({int(k): v for k, v in json.load(f).items()})
        if getattr(args, "no_hints", False):
            self.hints = {}
        self.cell_w1, self.cell_h1 = info["frame_w"] + 2 * m, info["frame_h"] + 2 * m
        self.cell_w, self.cell_h = self.cell_w1 * g, self.cell_h1 * g
        self.types = info.get("types") or [-1] * info["count"]
        # plain floors of the set, to put under objects that stand on a ground diamond
        self.floors = [(i, self.sheet.cut(self.original, i, 1)) for i in range(info["count"])
                       if self.types[i] == xs.MCD_FLOOR and self.sheet.cut(self.original, i, 1).getbbox() is not None]
        self.cells = {}   # frame index -> dict(init, tile, canny) at scale g, or missing for empty frames
        self.tall = {}    # ground frames that rise well above the floor diamond (standing crops)
        self.flat = {}    # ровные полы: им идёт пониженная сила
        fc = getattr(args, "flat_colors", 8)
        fd = getattr(args, "flat_detail", 20.0)
        for i in range(info["count"]):
            frame = self.sheet.cut(self.original, i, 1)
            box = frame.getbbox()
            if box is None:
                continue
            self.tall[i] = self.ground[i] and box[1] < info["frame_h"] - 16 - 6
            if self.ground[i] and not self.tall[i] and fc > 0:
                colors, detail = frame_texture(frame)
                self.flat[i] = colors <= fc and detail < fd
            self.cells[i] = self.make_cell(frame, self.ground[i], self.base[i])
        # crops: cells of one kind and one hint painted together, side by side
        per = max(1, args.max_crop // self.cell_w)
        self.crops = []
        groups = {}
        for i in sorted(self.cells):
            groups.setdefault((not self.ground[i], bool(self.tall.get(i)),
                               bool(self.flat.get(i)), self.hints.get(i, "")), []).append(i)
        for key in sorted(groups):
            group = groups[key]
            for k in range(0, len(group), per):
                self.crops.append(group[k:k + per])


    def floor_under(self, frame):
        """The set's floor the object stands on: the floor whose pixels the sprite repeats (X-COM
        objects on a ground diamond carry that floor's pixels; build_pack puts the same floor's painted
        tile back under the object), else the floor closest in colour to the rim of the object's ground
        diamond, or None."""
        if not self.floors:
            return None
        index, _ = xs.floor_match(frame, self.floors)
        if index is not None:
            return dict(self.floors)[index]
        arr = np.asarray(frame).astype(np.float32)
        h, w = arr.shape[:2]
        rim = []
        for y in range(h - 16, h):
            for x in range(w):
                d = abs(x - (w - 1) / 2) / (w / 2) + abs(y - (h - 8.5)) / 8
                if 0.75 <= d <= 1.0 and arr[y, x, 3] > 0:
                    rim.append(arr[y, x, :3])
        if len(rim) < 8:
            return None
        rim = np.mean(rim, axis=0)
        best, best_d = None, None
        for i, floor in self.floors:
            fa = np.asarray(floor).astype(np.float32)
            sel = fa[:, :, 3] > 0
            if sel.sum() == 0:
                continue
            d = np.linalg.norm(fa[:, :, :3][sel].mean(axis=0) - rim)
            if best_d is None or d < best_d:
                best, best_d = floor, d
        return best

    def make_cell(self, frame, ground, base=False):
        """The painter's input for one frame: the frame (or the ground field) on a cell, background
        filled, upscaled; the tile control (blurred) and the canny control."""
        args, g, m = self.args, self.g, self.margin
        cell = Image.new("RGBA", (self.cell_w1, self.cell_h1), (0, 0, 0, 0))
        box = frame.getbbox()
        tall = ground and box is not None and box[1] < frame.height - 16 - 6
        if ground and not tall:
            # the field is made of the floor diamond alone; what rises above it (a bank, a step)
            # is put on the field once, where the frame is, so that it is painted as one thing
            diamond, rest = split_diamond(frame)
            cell = tile_ground(derim_ground(diamond), self.cell_w1, self.cell_h1, m)
            cell.alpha_composite(rest, (m, m))
        elif ground:
            cell = tile_ground(derim_ground(frame), self.cell_w1, self.cell_h1, m)
        elif base and self.floor_under(frame) is not None:
            # a field of the matching floor under the object, the object on top
            cell = tile_ground(derim_ground(self.floor_under(frame)), self.cell_w1, self.cell_h1, m)
            cell.alpha_composite(frame, (m, m))
        else:
            cell.alpha_composite(frame, (m, m))
        # a field gets a blurrier tile control: the painter must not copy the tiles' fine structure
        tile_blur = args.tile_blur * (1.8 if ground else 1.0)
        if args.init == "smooth":
            filled = smooth_upscale(fill_background(cell, radius=3, blur=1.0), g)
            tile = filled.filter(ImageFilter.GaussianBlur(g * tile_blur)) if tile_blur > 0 else filled
            canny = canny_image(filled, 20, 60)
        else:
            f1 = fill_background(cell, radius=3, blur=1.0)
            filled = f1.resize((f1.width * g, f1.height * g), Image.NEAREST)
            tile = filled.filter(ImageFilter.GaussianBlur(g * 0.35))
            canny = canny_image(filled)
        return {"init": filled, "tile": tile, "canny": canny}

    def variant_frames(self):
        """The frames that get variants: flat floors (the engine varies only a cell's floor)."""
        return [i for i in sorted(self.cells)
                if self.ground[i] and self.types[i] == xs.MCD_FLOOR and not self.tall.get(i)]

    def looks_for(self, i, count, subject, custom=None, per_frame=None):
        """(kind, looks) of floor i: its own looks.json entry, --variant-looks, or its kind's looks."""
        if per_frame and i in per_frame:
            looks = parse_looks(per_frame[i])
            return "custom", (looks + looks[-1:] * count)[:count]
        if custom:
            return "custom", (custom + custom[-1:] * count)[:count]
        kind = ground_kind(self.hints.get(i, "")) or (ground_kind(subject.split(":")[0]) if ":" in subject else None)
        if kind is None:
            return None, []
        return kind, variant_looks(kind, count)

    def variant_cell(self, i, tone):
        """The painter's input of floor i recoloured for a variant."""
        c = self.cells[i]
        return {"init": tint(c["init"], tone), "tile": tint(c["tile"], tone), "canny": c["canny"]}

    def assemble(self, key):
        """A sheet-sized image of every cell's `key` image (for dry runs and the painted sheet)."""
        out = Image.new("RGB", self.sheet.size(self.g), (128, 128, 128))
        for i, c in self.cells.items():
            out.paste(c[key], self.cell_origin(i))
        return out

    def cell_origin(self, i):
        return ((i % self.sheet.columns) * self.cell_w, (i // self.sheet.columns) * self.cell_h)

    def reference(self, i):
        """The original frame (nearest-scaled) on grey, cell-sized."""
        x, y = self.cell_origin(i)
        grey = Image.new("RGBA", (self.cell_w, self.cell_h), (90, 90, 90, 255))
        grey.alpha_composite(self.big.crop((x, y, x + self.cell_w, y + self.cell_h)))
        return grey.convert("RGB")


class Painter:
    def __init__(self, pipe, prompts, negative, context):
        import torch
        self.torch = torch
        self.pipe = pipe
        self.prompts = prompts  # {"ground": ..., "object": ...} with {subject} still to fill in
        self.negative = negative
        # {"ground": (короткая форма, полная), "object": (то же)}: у полов и объектов тема может
        # отличаться. В наборе вроде GDXOPSFLOORS одни полы, а тема террейна называет кусты и
        # деревья - и модель рисует зелень на ровном полу (RAKES.md, R-016)
        self.context = context

    def prompt_for(self, job, frame, look=""):
        hint = job.hints.get(frame, "")
        kind0 = "ground" if job.ground[frame] and not job.tall.get(frame) else "object"
        ctx = self.context[kind0]
        subject = ("%s, %s" % (hint, ctx[0])) if hint else ctx[1]
        if look:
            subject = "%s, %s" % (look, subject)
        # flat ground gets the terrain (top-down) prompt; standing crops are a field of objects
        return self.prompts[kind0].replace("{subject}", subject)

    def run(self, args, prompt, init, controls, weights, strength, steps, seed):
        w, h = init.size
        # SDXL wants multiples of 8; pad if needed and cut the padding off afterwards
        pw, ph = (w + 7) // 8 * 8, (h + 7) // 8 * 8

        def padded(im):
            if (pw, ph) == (w, h):
                return im
            canvas = Image.new("RGB", (pw, ph), (128, 128, 128))
            canvas.paste(im, (0, 0))
            return canvas
        generator = self.torch.Generator("cuda").manual_seed(seed)
        result = self.pipe(
            prompt=prompt, negative_prompt=self.negative,
            image=padded(init), control_image=[padded(c) for c in controls],
            strength=strength, num_inference_steps=steps, guidance_scale=args.cfg,
            controlnet_conditioning_scale=weights,
            generator=generator, width=pw, height=ph).images[0]
        return result.crop((0, 0, w, h))

    def paint(self, job, frames, strength, steps, seed, cells=None, look=""):
        """Paints the cells of `frames` side by side. Two passes: the first invents the picture from
        the soft input (shape and colors held by the blurred tile control), the second repaints it at
        `refine` strength from its own output with sharp controls (texture and detail).
        `cells` replaces the frames' inputs (a variant's recoloured ones), `look` goes before the subject.
        Returns {frame: (final, first pass)}."""
        args = job.args
        n = len(frames)
        init = Image.new("RGB", (job.cell_w * n, job.cell_h), (128, 128, 128))
        tile, canny = init.copy(), init.copy()
        for k, i in enumerate(frames):
            c = (cells or job.cells)[i]
            init.paste(c["init"], (k * job.cell_w, 0))
            tile.paste(c["tile"], (k * job.cell_w, 0))
            canny.paste(c["canny"], (k * job.cell_w, 0))
        prompt = self.prompt_for(job, frames[0], look)
        # a field has no edges worth keeping (the tile lattice least of all): canny off for ground crops
        canny_w = 0.0 if job.ground[frames[0]] else args.canny
        first = self.run(args, prompt, init, [tile, canny], [args.tile, canny_w], strength, steps, seed)
        final = first
        if args.refine > 0:
            final = self.run(args, prompt, first, [first, canny_image(first)], [args.tile, canny_w],
                             args.refine, steps, seed + 1000)
        out = {}
        for k, i in enumerate(frames):
            box = (k * job.cell_w, 0, (k + 1) * job.cell_w, job.cell_h)
            out[i] = (final.crop(box), first.crop(box))
        return out


def label(im, text):
    from PIL import ImageDraw
    out = im.convert("RGB").copy()
    d = ImageDraw.Draw(out)
    d.rectangle((0, 0, 8 + 7 * len(text), 16), fill=(0, 0, 0))
    d.text((4, 2), text, fill=(255, 255, 0))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default=DEFAULT_MODELS_DIR, help="folder the models are kept in (default E:\\models)")
    ap.add_argument("--download-only", action="store_true", help="fetch the models into --models and stop")
    ap.add_argument("--sheets", default="")
    ap.add_argument("--set", default="")
    ap.add_argument("--base", default="", help="SDXL checkpoint (HF repo id or folder); default Juggernaut XL v9, "
                    "stabilityai/stable-diffusion-xl-base-1.0 is the plain model")
    ap.add_argument("--gen-scale", type=int, default=16, help="upscale the painter works at: 16 = a 32x40 tile is 512x640 px "
                    "(sprites big on the canvas, the model keeps their details); 8 = four times faster, less faithful")
    ap.add_argument("--strength", type=float, default=0.8)
    ap.add_argument("--flat-strength", type=float, default=0.6, dest="flat_strength",
                    help="сила для РОВНЫХ полов (мало цветов, нет фактуры). На пустом ромбе сила 0.8 "
                         "выдумывает решётки и линии, которых в оригинале нет")
    ap.add_argument("--flat-colors", type=int, default=8, dest="flat_colors",
                    help="пол считается ровным, если цветов в нём не больше этого (0 = выключить)")
    ap.add_argument("--flat-detail", type=float, default=20.0, dest="flat_detail",
                    help="и средний перепад яркости между соседними пикселями меньше этого")
    ap.add_argument("--steps", type=int, default=30)
    ap.add_argument("--cfg", type=float, default=6.5)
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--tile", type=float, default=0.6, help="tile ControlNet weight (keeps colors and shapes; "
                    "0.6+ copies the softness of the input, 0.3 lets the model reinvent)")
    ap.add_argument("--tile-blur", type=float, default=0.35, help="blur of the tile control image, in source pixels: "
                    "the painter keeps the shapes but must invent the texture itself")
    ap.add_argument("--canny", type=float, default=0.2, help="canny ControlNet weight (keeps edges)")
    ap.add_argument("--refine", type=float, default=0.45, help="strength of the second pass (repaints the first "
                    "pass's output with sharp controls: detail and texture); 0 = one pass only")
    ap.add_argument("--init", choices=["smooth", "nearest"], default="smooth",
                    help="what the painter starts from: a smooth upscale (default) or the raw blocks")
    ap.add_argument("--prompt", default="", help="full prompt for objects (default: the style prompt with the set's subject)")
    ap.add_argument("--prompt-ground", default="", help="full prompt for ground tiles (default: the ground style prompt)")
    ap.add_argument("--subject", default="", help="subject words for the style prompts")
    ap.add_argument("--set-terrains", default="", dest="set_terrains",
                    help="set_terrains.tsv (по умолчанию .index/mod/Piratez/set_terrains.tsv рядом с корнем)")
    ap.add_argument("--no-hints", action="store_true", help="ignore the per-frame hints (HINTS / hints.json)")
    ap.add_argument("--only", choices=["all", "ground", "objects", "variants"], default="all",
                    help="repaint only the ground (or only the objects) and keep the other cells from the set's existing painted "
                         "sheet; variants: paint only the ground variants (--variants), the base painting stays")
    ap.add_argument("--variants", type=int, default=0, help="paint every floor this many more times (other looks: short / tall "
                    "grass, lighter / darker sand); the engine lays the paintings over the map as patches (up to 15)")
    ap.add_argument("--variant-looks", default="", help="the words of the variants for every floor, in order: "
                    "\"v1 words|v2 words\" (v1, v3 ... one way from the base painting, v2, v4 ... the other; "
                    "\"words@1.05,0.9,0.02\" also recolours: brightness, saturation, warmth); default: by the floor's kind")
    ap.add_argument("--variant-frames", default="", help="paint the variants of only these floors, e.g. 0,3 (floors "
                    "varied before with the same --variants keep theirs)")
    ap.add_argument("--seamless", type=int, default=1, help="1: blend the edges of ground tiles with the continued "
                    "field across the grid step, so neighbours meet without a seam; 0: off")
    ap.add_argument("--negative", default=NEGATIVE)
    ap.add_argument("--max-crop", type=int, default=1280, help="largest crop width sent to the model (1280 = two cells at scale 16)")
    ap.add_argument("--test", action="store_true", help="only the first crop, fewer steps")
    ap.add_argument("--sweep", default="", help="values of one parameter, e.g. 0.7,0.8,0.9 (strength) or tile=0.3,0.6: "
                                               "paints one frame with each and writes crops/sweep.png for comparing")
    ap.add_argument("--matrix", action="store_true", help="paints one frame with the built-in list of variations "
                                                          "(MATRIX in the script) into crops/matrix.png")
    ap.add_argument("--frame", default="", help="the frame(s) --sweep / --matrix look at, e.g. 9 or 4,8,9 (default: the first)")
    ap.add_argument("--dry-run", action="store_true", help="write the control images and stop (no model)")
    ap.add_argument("--out", default="")
    args = ap.parse_args(argv)
    if args.download_only:
        download_models()
        return
    if not args.sheets or not args.set:
        ap.error("--sheets and --set are required (or --download-only)")
    if args.only == "variants" and args.variants < 1:
        ap.error("--only variants needs --variants N")
    if args.variants > 15:
        ap.error("--variants: the engine reads at most 15")

    set_name = args.set.upper()
    set_dir = os.path.join(args.sheets, set_name)
    with open(os.path.join(set_dir, "layout.json")) as f:
        info = json.load(f)
    if "ground" not in info:
        print("note: layout.json has no tile types (old extract_pck.py) - every frame is painted as an object; re-run extract_pck.py")
    pack_scale = info["scale"]
    job = Job(args, set_dir, info)
    # Тема набора: --subject -> SUBJECTS -> террейн мода -> имя набора -> заглушка.
    # Связь "набор -> террейн" берётся из .index/mod/Piratez/set_terrains.tsv, который
    # строит tools/index_mod.py по рулсетам. Руками её не пишем (RAKES.md, R-013).
    subject = args.subject
    if subject:
        pass
    elif set_name in SUBJECTS:
        subject = SUBJECTS[set_name]
    else:
        subject, src = subjects_terrain.subject_for_set(
            set_name, tsv_path=(args.set_terrains or None))
        if subject:
            print("тема набора взята по террейну %s" % src)
        else:
            subject, src = subjects_terrain.subject_by_name(set_name)
            if subject:
                print("тема набора угадана по имени (образец %s) - проверь, если результат странный" % src)
            else:
                subject = "terrain tiles and objects"
                print("ВНИМАНИЕ: для %s нет темы ни в SUBJECTS, ни по террейну, ни по имени - "
                      "рисуем с заглушкой 'terrain tiles and objects'. Модель не знает, "
                      "что это за место." % set_name, file=sys.stderr)
    # Грубая оценка длины: CLIP считает и слова, и знаки препинания. Точный счёт
    # доступен только после загрузки модели, а предупредить надо до неё.
    _tail = 53   # префикс + постоянный стилевой хвост; выверено по факту: длинная
                 # тема ACHURCH дала ровно 79 токенов, как и сказал CLIP
    _est = len(subject.replace(",", " , ").replace(":", " : ").split()) + _tail
    if _est > 77:
        print("ВНИМАНИЕ: тема набора длинная (~%d токенов с хвостом стиля, предел 77). "
              "CLIP обрежет конец промпта - потеряется 'Xenonauts style'. Сократи тему."
              % _est, file=sys.stderr)
    # Тема может быть написана в двух частях через « | »: слева поверхности (идут и в полы,
    # и в объекты), справа предметы (только в объекты). Без разделителя обе части совпадают.
    if "|" in subject:
        head, _, tail = subject.partition(":")
        if tail:
            g, _, o = tail.partition("|")
            subject_ground = "%s:%s" % (head, g.rstrip().rstrip(","))
            subject = "%s:%s,%s" % (head, g.rstrip().rstrip(","), o)
        else:
            g, _, o = subject.partition("|")
            subject_ground = g.strip().rstrip(",")
            subject = "%s, %s" % (subject_ground, o.strip())
    else:
        subject_ground = subject
    # short form after a hint, full form without one - отдельно для полов и для объектов
    context = {"ground": (subject_ground.split(":")[0], subject_ground),
               "object": (subject.split(":")[0], subject)}
    unit = set_name in UNIT_SETS
    prompts = {"object": args.prompt or (STYLE_UNIT if unit else STYLE), "ground": args.prompt_ground or STYLE_GROUND}
    if unit:
        # characters: keep the parts' shapes and colors (they are assembled by the engine), add material
        if args.strength == 0.8: args.strength = 0.6
        if args.tile == 0.6: args.tile = 0.75
        if args.canny == 0.2: args.canny = 0.4
        if args.refine == 0.45: args.refine = 0.35
        print("unit set: strength %.2f, tile %.2f, canny %.2f, refine %.2f" % (args.strength, args.tile, args.canny, args.refine))
    print("prompt (objects):", prompts["object"].replace("{subject}", subject))
    print("prompt (ground): ", prompts["ground"].replace("{subject}", subject_ground))
    print("%d frames in %d crops (%d ground, %d with hints)" % (
        len(job.cells), len(job.crops), sum(1 for i in job.cells if job.ground[i]), sum(1 for i in job.cells if i in job.hints)))
    variants = plan_variants(args, job, set_dir, subject) if args.variants > 0 and args.only != "objects" else None
    if args.dry_run:
        for key in ("init", "tile", "canny"):
            job.assemble(key).save(os.path.join(set_dir, "dry_%s_x%d.png" % (key, job.g)))
        if variants:
            for k in range(1, args.variants + 1):
                sheet = Image.new("RGB", job.sheet.size(job.g), (128, 128, 128))
                for i, (_, looks) in variants["plan"].items():
                    sheet.paste(job.variant_cell(i, looks[k - 1][1])["init"], job.cell_origin(i))
                sheet.save(os.path.join(set_dir, "dry_init_x%d.v%d.png" % (job.g, k)))
        print("dry run: wrote dry_*.png into", set_dir)
        return

    painter = Painter(load_pipeline(args.base), prompts, args.negative, context)
    steps = 20 if args.test else args.steps
    crop_dir = os.path.join(set_dir, "crops")
    os.makedirs(crop_dir, exist_ok=True)
    t0 = time.time()
    frames = [int(v) for v in args.frame.split(",") if v.strip()] if args.frame else [min(job.cells)]
    frames = [f for f in frames if f in job.cells] or [min(job.cells)]

    def stack(rows):
        """Rows of panels under each other."""
        strips = [side_by_side(r) for r in rows]
        out = Image.new("RGB", (max(s.width for s in strips), sum(s.height + 8 for s in strips) - 8), (255, 0, 255))
        y = 0
        for st in strips:
            out.paste(st, (0, y))
            y += st.height + 8
        return out

    if args.sweep:
        # the frames at every value of one parameter, next to the original: pick by eye
        name, values = "strength", args.sweep
        if "=" in args.sweep:
            name, values = args.sweep.split("=", 1)
        name = name.replace("-", "_")
        rows = [[label(job.reference(f), "original %d" % f), label(job.cells[f]["init"], "input")] for f in frames]
        for v in values.split(","):
            setattr(args, name, type(getattr(args, name))(v))
            if name == "base":
                painter.pipe = load_pipeline(v)
            j = Job(args, set_dir, info) if name in ("gen_scale", "init", "tile_blur", "max_crop", "no_hints") else job
            for r, f in enumerate(frames):
                result, first = painter.paint(j, [f], args.strength, steps, args.seed)[f]
                tag = "%d_%s_%s" % (f, name, v.replace(".", "").replace("/", "-"))
                result.save(os.path.join(crop_dir, "sweep_%s.png" % tag))
                rows[r].append(label(result, "%s %s" % (name, v.split("/")[-1])))
            print("  %s %s done, %.0fs" % (name, v, time.time() - t0))
        stack(rows).save(os.path.join(crop_dir, "sweep.png"))
        print("wrote", os.path.join(crop_dir, "sweep.png"), "(original | input | %s = %s)" % (name, values))
        return

    if args.matrix:
        # the frames under every variation of MATRIX
        rows = [[label(job.reference(f), "original %d" % f)] for f in frames]
        for title, over in MATRIX:
            a = argparse.Namespace(**vars(args))
            for k, v in over.items():
                setattr(a, k, v)
            j = Job(a, set_dir, info)
            for r, f in enumerate(frames):
                result, _ = painter.paint(j, [f], a.strength, steps, a.seed)[f]
                rows[r].append(label(result.resize((job.cell_w, job.cell_h), Image.LANCZOS), title))
            print("  %-24s done, %.0fs" % (title, time.time() - t0))
        stack(rows).save(os.path.join(crop_dir, "matrix.png"))
        print("wrote", os.path.join(crop_dir, "matrix.png"))
        return

    if args.only == "variants":
        paint_variants(args, job, painter, set_dir, info, variants, steps, t0)
        return
    crops = job.crops[:1] if args.test else job.crops
    painted = job.assemble("init")
    if args.only != "all":
        crops = [c for c in crops if job.ground[c[0]] == (args.only == "ground")]
        previous = os.path.join(set_dir, "painted_x%d.png" % job.g)
        if os.path.exists(previous):
            old_sheet = Image.open(previous).convert("RGB")
            if old_sheet.size == painted.size:
                painted = old_sheet
                print("repainting only %s (%d crops), the rest stays from %s" % (args.only, len(crops), previous))
    flat_crops = sum(1 for c in crops if job.flat.get(c[0]))
    if flat_crops:
        print("ровных полов: %d кадр(ов) в %d кроп(ах) - им сила %.2f вместо %.2f"
              % (sum(1 for c in crops for i in c if job.flat.get(i)), flat_crops,
                 args.flat_strength, args.strength))
    for n, frames in enumerate(crops):
        crop_strength = args.flat_strength if job.flat.get(frames[0]) else args.strength
        results = painter.paint(job, frames, crop_strength, steps, args.seed + n)
        for i, (final, _) in results.items():
            if job.ground[i] and args.seamless:
                final = seamless_ground(final, job.g, job.margin, info["frame_w"], info["frame_h"])
            painted.paste(final, job.cell_origin(i))
        panels = [results[i][0] for i in frames]
        side_by_side(panels, 0).save(os.path.join(crop_dir, "crop_%02d.png" % n))
        el = time.time() - t0
        left = el / (n + 1) * (len(crops) - n - 1)
        print("  [%3d%%] кроп %d/%d, кадры %s%s%s | %s, осталось ~%s" % (
            (n + 1) * 100 // len(crops), n + 1, len(crops), " ".join(str(i) for i in frames),
            " сила %.2f" % crop_strength if crop_strength != args.strength else "",
            ": " + job.hints[frames[0]] if frames[0] in job.hints else "",
            human_time(el), human_time(left)), flush=True)

    painted.save(os.path.join(set_dir, "painted_x%d.png" % job.g))
    small = painted.resize((job.original.width * pack_scale, job.original.height * pack_scale), Image.LANCZOS)
    out = args.out or os.path.join(set_dir, "painted_x%d.png" % pack_scale)
    small.save(out)
    if variants:
        paint_variants(args, job, painter, set_dir, info, variants, steps, t0)
    print("wrote", out, "- next: build_pack.py --sheets %s --set %s --hd %s --mod <mod> [--pack-path TERRAIN]" % (args.sheets, set_name, out))


def plan_variants(args, job, set_dir, subject):
    """Which floors get variants and their looks: {"plan": {frame: (kind, looks)}}; prints the plan."""
    custom = parse_looks(args.variant_looks) if args.variant_looks else None
    per_frame = {}
    looks_file = os.path.join(set_dir, "looks.json")
    if os.path.exists(looks_file):
        with open(looks_file, encoding="utf-8") as f:
            per_frame = {int(k): v for k, v in json.load(f).items()}
    only = {int(v) for v in args.variant_frames.split(",") if v.strip()}
    plan, skipped = {}, []
    for i in job.variant_frames():
        if only and i not in only:
            continue
        kind, looks = job.looks_for(i, args.variants, subject, custom, per_frame)
        if kind is None:
            skipped.append(i)
            continue
        plan[i] = (kind, looks)
    for i, (kind, looks) in sorted(plan.items()):
        print("  variants of %d (%s%s): %s" % (i, kind, ", " + job.hints[i] if i in job.hints else "",
                                               " | ".join("v%d %s" % (n + 1, w) for n, (w, _) in enumerate(looks))))
    if skipped:
        print("  no variants for floors %s: no known kind of ground in their hints (--variant-looks or looks.json gives words)"
              % " ".join(str(i) for i in skipped))
    if not plan:
        print("no floors to vary")
    return {"plan": plan}


def paint_variants(args, job, painter, set_dir, info, variants, steps, t0):
    """Paints variants 1..N of the planned floors into painted_x<g>.v<n>.png and painted_x<scale>.v<n>.png,
    and writes variants.json (read by build_pack.py)."""
    plan = variants["plan"]
    if not plan:
        return
    count = args.variants
    pack_scale = info["scale"]
    per = max(1, args.max_crop // job.cell_w)
    # crops: floors with the same hint and the same looks painted together
    groups = {}
    for i, (kind, looks) in sorted(plan.items()):
        groups.setdefault((job.hints.get(i, ""), tuple(w for w, _ in looks)), []).append(i)
    crops = []
    for key in sorted(groups):
        group = groups[key]
        for k in range(0, len(group), per):
            crops.append(group[k:k + per])
    if args.test:
        crops = crops[:1]
        plan = {i: plan[i] for i in crops[0]}
    crop_dir = os.path.join(set_dir, "crops")
    os.makedirs(crop_dir, exist_ok=True)
    out_base = os.path.splitext(args.out or os.path.join(set_dir, "painted_x%d.png" % pack_scale))[0]
    meta_file = os.path.join(set_dir, "variants.json")
    old = {}
    if os.path.exists(meta_file):
        with open(meta_file, encoding="utf-8") as f:
            old = json.load(f)
    # the floors varied before and not now keep their variants, if every old variant sheet is there to
    # keep their cells from (same count, same painting scale); otherwise only this run's floors count
    size = job.sheet.size(job.g)
    sheets = {}
    if old.get("count") == count:
        for n_var in range(1, count + 1):
            big_path = os.path.join(set_dir, "painted_x%d.v%d.png" % (job.g, n_var))
            if os.path.exists(big_path):
                prev = Image.open(big_path).convert("RGB")
                if prev.size == size:
                    sheets[n_var] = prev
    if len(sheets) == count:
        painted_now = len(plan)
        plan = dict(plan)
        for key, entry in old.get("frames", {}).items():
            if int(key) not in plan:
                plan[int(key)] = (entry["kind"], [(w, tuple(t)) for w, t in entry["looks"]])
        kept = len(plan) - painted_now
        if kept:
            print("  %d floor(s) keep the variants painted before" % kept)
    else:
        sheets = {n_var: Image.new("RGB", size, (128, 128, 128)) for n_var in range(1, count + 1)}
    for n_var in range(1, count + 1):
        big_path = os.path.join(set_dir, "painted_x%d.v%d.png" % (job.g, n_var))
        sheet = sheets[n_var]
        for n, frames in enumerate(crops):
            look_words, _ = plan[frames[0]][1][n_var - 1]
            cells = {i: job.variant_cell(i, plan[i][1][n_var - 1][1]) for i in frames}
            results = painter.paint(job, frames, args.strength, steps, args.seed + n + 7919 * n_var, cells=cells, look=look_words)
            for i, (final, _) in results.items():
                if args.seamless:
                    final = seamless_ground(final, job.g, job.margin, info["frame_w"], info["frame_h"])
                sheet.paste(final, job.cell_origin(i))
            side_by_side([results[i][0] for i in frames], 0).save(os.path.join(crop_dir, "variant%d_crop_%02d.png" % (n_var, n)))
            print("  variant %d/%d, crop %d/%d (floors %s: %s) done, %.0fs" % (
                n_var, count, n + 1, len(crops), " ".join(str(i) for i in frames), look_words, time.time() - t0))
        sheet.save(big_path)
        small = sheet.resize((job.original.width * pack_scale, job.original.height * pack_scale), Image.LANCZOS)
        small.save("%s.v%d.png" % (out_base, n_var))
    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump({"count": count, "frames": {str(i): {"kind": kind, "hint": job.hints.get(i, ""),
                                                        "looks": [[w, list(t)] for w, t in looks]}
                                              for i, (kind, looks) in sorted(plan.items())}}, f, indent=1, ensure_ascii=False)
    print("wrote %d variant sheet(s) %s.v1.png ... and %s (%d floors)" % (count, out_base, meta_file, len(plan)))


if __name__ == "__main__":
    main()
