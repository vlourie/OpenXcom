"""WALL_RESTORE_C: проба AI-фактуры поверх детерминированной основы стен (указание специалиста 08.10).

A/B2 (wall_restore.py) держат геометрию, но фактурные стены выглядят увеличенным спрайтом. Здесь модель
малой силой перерисовывает B2, а из её ответа берётся ТОЛЬКО мелкая фактура яркости:

  * вход модели - B2 x4, увеличенный до x16 (512x640, гладкий вход, R-004), края продолжены наружу силуэта;
    SDXL Juggernaut-XL-v9 img2img + ControlNet tile (вход же, вес 0.6) + canny (вес 0.3); подсказка - только
    материал кадра (census/walls/restore/c_materials.json, R-016) и короткий блок ракурса battle_view.short;
  * ответ уменьшается до 128x160, из него берётся полоса мельче половины пикселя базы (sprite_scale.add_detail:
    y - blur(y, 2 пикс x4)) и кладётся множителем яркости (сила 1.0, предел +-35 %) на A - только внутри альфы A;
  * альфа, силуэт, контур, проёмы, цвет и всё строение крупнее половины пикселя базы - из A без изменений.
    Модель не решает ни прозрачность, ни края, ни число деталей.

Две силы перерисовки (--strengths 0.30 0.45) - колонки c30, c45. Веса - папки снимков кэша (R-207), без сети.

  wall_restore_c.py --cases census/walls/restore/cases.json --out census/walls/restore

Читает <out>/<случай>/xbrz и esrgan (готовые A и B2), пишет <out>/<случай>/c<NN>/series/<НАБОР>.PCK/<кадр>.png,
сырой ответ модели <out>/<случай>/c<NN>/raw/<НАБОР>_<кадр>.png и report_c.json. В мод ничего не кладётся.
Модель на видеокарте - только через очередь (tools/gpuq.py).
"""
import argparse
import glob
import json
import os
import sys
import time

os.environ.setdefault("HF_HUB_OFFLINE", "1")
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import numpy as np                                  # noqa: E402
import cv2                                          # noqa: E402
from PIL import Image                               # noqa: E402
import battle_view as bv                            # noqa: E402
import map_mockup as mm                             # noqa: E402
import sprite_scale as ss                           # noqa: E402
import wall_restore as wr                           # noqa: E402

ENC = "utf-8-sig"
ROOT = os.path.dirname(os.path.dirname(HERE))
HUB = "E:/models/hub"
REPOS = {"base": "RunDiffusion--Juggernaut-XL-v9", "tile": "xinsir--controlnet-tile-sdxl-1.0",
         "canny": "diffusers--controlnet-canny-sdxl-1.0", "vae": "madebyollin--sdxl-vae-fp16-fix"}
UP = 4                     # B2 (x4) -> вход модели x16
STEPS, CFG, SEED = 30, 5.0, 2711
CTRL = (0.6, 0.3)          # вес tile, canny
DETAIL = (1.0, 0.35)       # сила, предел поправки яркости из ответа
NEG_EXTRA = ("window, door, opening, frame, new panel, sign, text, logo, cracks, pixel art, jagged pixels, "
             "blurry, smooth plastic")
LINE_T = 16.0              # |поправка яркости| для меры новых линий
LINE_LEN = 13              # длина штриха, пикселей x4 (три с лишним пикселя базы)


def snapshot(key):
    """Папка снимка кэша по refs/main (R-207): локальная папка грузится без сети и с закреплённой ревизией."""
    d = os.path.join(HUB, "models--" + REPOS[key])
    rev = open(os.path.join(d, "refs", "main"), encoding="utf-8").read().strip()
    return os.path.join(d, "snapshots", rev), rev


def load_pipe():
    import torch
    from diffusers import AutoencoderKL, ControlNetModel, StableDiffusionXLControlNetImg2ImgPipeline
    kw = {"torch_dtype": torch.float16}
    paths = {k: snapshot(k) for k in REPOS}
    for k, (p, rev) in paths.items():
        print("  %s: %s @ %s" % (k, REPOS[k], rev[:12]), flush=True)
    tile = ControlNetModel.from_pretrained(paths["tile"][0], **kw)
    canny = ControlNetModel.from_pretrained(paths["canny"][0], **kw)
    vae = AutoencoderKL.from_pretrained(paths["vae"][0], **kw)
    common = dict(controlnet=[tile, canny], vae=vae, use_safetensors=True, local_files_only=True, **kw)
    try:
        pipe = StableDiffusionXLControlNetImg2ImgPipeline.from_pretrained(paths["base"][0], variant="fp16", **common)
    except Exception as e:  # noqa: BLE001 - без варианта fp16 берутся полные веса
        print("  (нет варианта fp16: %s)" % str(e).splitlines()[0][:100], flush=True)
        pipe = StableDiffusionXLControlNetImg2ImgPipeline.from_pretrained(paths["base"][0], **common)
    pipe.to("cuda")
    pipe.set_progress_bar_config(disable=True)
    return pipe, {k: v[1] for k, v in paths.items()}


def lum(rgb):
    return 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]


def model_input(b2):
    """RGB B2, продолженный наружу силуэта и в проёмы, x16 гладко (LANCZOS)."""
    a = np.asarray(b2, np.float32)
    rgb = ss.fill_outside(a[None, ..., :3], (a[None, ..., 3] > 0))[0]
    im = Image.fromarray(np.clip(rgb + 0.5, 0, 255).astype(np.uint8))
    return im.resize((im.width * UP, im.height * UP), Image.LANCZOS)


def canny_of(im):
    g = cv2.Canny(np.asarray(im.convert("L")), 100, 200)
    return Image.fromarray(np.dstack([g] * 3))


def line_kernels(n):
    ks = [np.ones((1, n), np.uint8), np.ones((n, 1), np.uint8)]
    h = n // 2 + 1
    for sgn in (1, -1):                      # изо-диагонали 2:1 в обе стороны
        k = np.zeros((h, n), np.uint8)
        for x in range(n):
            y = x // 2
            k[y if sgn > 0 else h - 1 - y, x] = 1
        ks.append(k)
    return ks


KERNELS = line_kernels(LINE_LEN)


def new_lines(img, base):
    """Пикселей x4: длинные штрихи поправки яркости (img против base), которые не лежат вдоль граней base.
    Это мера «новых линий, швов, крестов» - то, чего фактура приносить не должна."""
    a = np.asarray(img, np.float32)
    b = np.asarray(base, np.float32)
    inside = a[..., 3] > 128
    d = lum(a[..., :3]) - lum(b[..., :3])
    hot = ((np.abs(d) > LINE_T) & inside).astype(np.uint8)
    lines = np.zeros_like(hot)
    for k in KERNELS:
        lines |= cv2.morphologyEx(hot, cv2.MORPH_OPEN, k)
    lb = lum(b[..., :3]).astype(np.float32)
    g = np.hypot(cv2.Sobel(lb, cv2.CV_32F, 1, 0), cv2.Sobel(lb, cv2.CV_32F, 0, 1))
    edges = cv2.dilate((g > 60).astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    return int((lines.astype(bool) & ~edges).sum())


def vs_base(img, base):
    """Против основы A: средняя |поправка яркости| внутри альфы (сколько фактуры добавлено), корреляция
    яркости в масштабе пикселя базы (blur 4 пикс x4: строение) и наибольшее расхождение альфы."""
    a = np.asarray(img, np.float32)
    b = np.asarray(base, np.float32)
    inside = b[..., 3] > 128
    la, lb = lum(a[..., :3]), lum(b[..., :3])
    ba, bb = cv2.GaussianBlur(la, (0, 0), 4), cv2.GaussianBlur(lb, (0, 0), 4)
    c = float(np.corrcoef(ba[inside], bb[inside])[0, 1]) if inside.sum() > 16 else None
    return dict(texture=round(float(np.abs(la - lb)[inside].mean()), 2),
                struct_corr=None if c is None else round(c, 4),
                alpha_diff=int(np.abs(a[..., 3] - b[..., 3]).max()),
                new_lines=new_lines(img, base))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", required=True)
    ap.add_argument("--out", default="census/walls/restore")
    ap.add_argument("--materials", default="census/walls/restore/c_materials.json")
    ap.add_argument("--strengths", type=float, nargs="+", default=[0.30, 0.45])
    ap.add_argument("--dry", action="store_true", help="без модели: ответ = сам вход (проверка пути и мер)")
    a = ap.parse_args()
    os.chdir(ROOT)
    import torch
    cases = json.load(open(a.cases, encoding=ENC))
    mats = json.load(open(a.materials, encoding=ENC))
    short = bv.short("wall")
    t0 = time.time()
    pipe, revs = (None, {}) if a.dry else load_pipe()
    print("модель загружена за %.0f с" % (time.time() - t0), flush=True)
    world = mm.World()
    n_total = sum(len(c["targets"]) for c in cases) * len(a.strengths)
    done = 0
    for case in cases:
        d = os.path.join(a.out, case["id"])
        rep = {"id": case["id"], "strengths": a.strengths, "steps": STEPS, "cfg": CFG, "seed": SEED,
               "controlnet": CTRL, "detail": DETAIL, "revisions": revs, "frames": {}}
        for s, n in case["targets"]:
            key = "%s:%d" % (s.upper(), n)
            frame = world.sprite(s, n, None)
            mask = np.asarray(frame)[..., 3] > 0
            name = os.path.join("series", s.upper() + ".PCK", "%d.png" % n)
            A = Image.open(os.path.join(d, "xbrz", name)).convert("RGBA")
            B2 = Image.open(os.path.join(d, "esrgan", name)).convert("RGBA")
            m = mats[key]
            prompt = "%s, %s, %s, detailed realistic material texture, sharp focus" % (
                m["material"], short["positive"], "game wall tile")
            neg = short["negative"] + ", " + NEG_EXTRA
            inp = model_input(B2)
            can = canny_of(inp)
            fr = {"class": m["class"], "material": m["material"], "prompt": prompt,
                  "A": dict(vs_base(A, A), **wr.metrics(A, frame, mask)),
                  "B2": dict(vs_base(B2, A), **wr.metrics(B2, frame, mask))}
            a_arr = np.asarray(A, np.float32)
            for st in a.strengths:
                tag = "c%02d" % round(st * 100)
                if a.dry:
                    out = inp
                else:
                    gen = torch.Generator("cuda").manual_seed(SEED)
                    out = pipe(prompt=prompt, negative_prompt=neg, image=inp, control_image=[inp, can],
                               strength=st, num_inference_steps=STEPS, guidance_scale=CFG,
                               controlnet_conditioning_scale=list(CTRL), generator=gen,
                               width=inp.width, height=inp.height).images[0]
                rawp = os.path.join(d, tag, "raw", "%s_%d.png" % (s.upper(), n))
                os.makedirs(os.path.dirname(rawp), exist_ok=True)
                out.save(rawp)
                small = np.asarray(out.resize(A.size, Image.LANCZOS), np.float32)
                rgb = wr.detail(a_arr[..., :3], small, DETAIL[0], DETAIL[1], a_arr[..., 3])
                C = Image.fromarray(np.clip(np.dstack([rgb, a_arr[..., 3]]) + 0.5, 0, 255).astype(np.uint8), "RGBA")
                p = os.path.join(d, tag, name)
                os.makedirs(os.path.dirname(p), exist_ok=True)
                C.save(p)
                fr[tag] = dict(vs_base(C, A), **wr.metrics(C, frame, mask))
                done += 1
            rep["frames"][key] = fr
            print("%s %s: %s" % (case["id"], key, "  ".join(
                "%s фактура %.1f линий %d" % (t, fr[t]["texture"], fr[t]["new_lines"])
                for t in ["B2"] + ["c%02d" % round(x * 100) for x in a.strengths])), flush=True)
        with open(os.path.join(d, "report_c.json"), "w", encoding=ENC) as f:
            json.dump(rep, f, ensure_ascii=False, indent=1)
        print("== %s готов: %d из %d рендеров, %.0f с; видеопамять пик %.1f ГБ" % (
            case["id"], done, n_total, time.time() - t0, (0 if a.dry else torch.cuda.max_memory_allocated()) / 2 ** 30), flush=True)


if __name__ == "__main__":
    main()
