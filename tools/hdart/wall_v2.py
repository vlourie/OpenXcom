"""WALL_RENDER_V2: участок стен, где модель меняет ТОЛЬКО маску целевой стены (решение специалиста 08.10).

V1 (wall_section.py) перерисовывал весь вход и потом вырезал стену: модель читала двери и соседей частью
стены (протёк цвета двери B01/B03), сдвигала весь ответ, дорисовывала двери и окна. V2 даёт тот же вход
как контекст, но латенты вне маски целевой стены на каждом шаге заменяются зашумлённым известным холстом:

  * известный холст - подложка участка и контекст (двери, чужие стены) кадрами пака игры x4;
  * свободно - клетки латентов, где есть пиксель целевой стены (верхний владелец - стена плана), плюс одна
    клетка поля наружу, но не на контекст и не в проём (VOID);
  * VOID (проёмы целевых кадров) и контекст закреплены: модель их не рисует, на последнем шаге шум 0,
    и там ровно известный холст;
  * вход-условие - тот же холст, где целевые стены поверх - классика xBRZ x4.

Дальше всё как V1 (вырезка по силуэту, сборка кадров, швы, ворота) - код wall_section.py без изменений.
Сквозной участок (--thru): прозрачность и форма проёма - маска геометрии оригинала (вариант M,
wall_thru.sil4_frame_open / assemble_open); пурпурный ключ (вариант K) не используется.

  wall_v2.py <ключи wall_section.py> [--thru] [--mask-only]

--mask-only: листы маски и холстов в <out>/s<сид>/ без модели (GPUQ_BYPASS=1 допустим, модель не грузится).
Модель - только через очередь видеокарты (tools/gpu_scripts.txt).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import numpy as np                                  # noqa: E402
from PIL import Image, ImageDraw                    # noqa: E402
import cv2                                          # noqa: E402
import wall_section as ws                           # noqa: E402

po = ws.po
MASK_ONLY = "mask-only"


def pad_crop(im, box, k):
    """Кроп по габариту box (k=1) из картинки k, за краем - прозрачное (как Image.crop)."""
    return im.crop((box[0] * k, box[1] * k, box[2] * k, box[3] * k))


def regions(frame, c):
    """Маски k=1 по входу: own - целевая стена сверху, ctx - контекст сверху, void - проёмы целевых."""
    lab, box, paint = c["lab"], c["box"], c["paint"]
    h, w = frame.height, frame.width
    full = np.full((h, w), -1, np.int32)
    ox, oy = max(0, -box[0]), max(0, -box[1])
    sub = lab[max(0, box[1]):box[3], max(0, box[0]):box[2]]
    full[oy:oy + sub.shape[0], ox:ox + sub.shape[1]] = sub
    own = np.isin(full, paint)
    ctx = (full >= 0) & ~own
    void = ws.openings(own) & ~ctx
    return own, ctx, void


def canvases(frame, c, W, H):
    """Известный холст (подложка + контекст паком) и вход-условие (тот же + целевые классикой xBRZ), W x H."""
    mem, at, size, ctx_img = c["mem"], c["at"], c["size"], c["ctx_img"]
    panel = tuple(int(v) for v in po.pick_background(frame)) + (255,)
    known_imgs = [ctx_img[i] if m["role"] == "ctx" else None for i, m in enumerate(mem)]
    cond_imgs = [ctx_img[i] if m["role"] == "ctx" else ws.xbrz(m["full"]) for i, m in enumerate(mem)]
    out = []
    for imgs in (known_imgs, cond_imgs):
        lay = pad_crop(ws.compose(mem, at, size, imgs, 4), c["box"], 4)
        flat = Image.new("RGBA", lay.size, panel)
        flat.alpha_composite(lay)
        out.append(flat.convert("RGB").resize((W, H), Image.LANCZOS))
    return out[0], out[1], panel


def latent_mask(own, ctx, void, hl, wl):
    """Свободные клетки латентов (1) - целевая стена и поле в одну клетку наружу (не контекст, не проём)."""
    def frac(m):
        return cv2.resize(m.astype(np.float32), (wl, hl), interpolation=cv2.INTER_AREA)
    f_own, f_ctx, f_void = frac(own), frac(ctx), frac(void)
    free0 = f_own > 0
    grow = cv2.dilate(free0.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    free = free0 | (grow & (f_ctx == 0) & (f_void == 0))
    return free, dict(own=round(float(free0.mean()), 3), free=round(float(free.mean()), 3),
                      ctx_in_free=int((free & (f_ctx > 0)).sum()), cells=int(hl * wl))


def mask_sheet(known, cond, free, d):
    """Лист: вход-условие | известный холст | свободное (красным поверх условия)."""
    W, H = known.size
    big = cv2.resize(free.astype(np.uint8), (W, H), interpolation=cv2.INTER_NEAREST) > 0
    over = np.asarray(cond, np.float32).copy()
    over[big] = over[big] * 0.45 + np.array([255, 0, 0], np.float32) * 0.55
    k = min(1.0, 900.0 / W)
    ims = [(cond, "condition: context = game pack, target = classic xBRZ"), (known, "known (locked) canvas"),
           (Image.fromarray(over.astype(np.uint8)), "red = model may change")]
    w2, h2 = int(W * k), int(H * k)
    sheet = Image.new("RGB", (w2 * 3 + 16, h2 + 20), (30, 30, 34))
    dr = ImageDraw.Draw(sheet)
    for j, (im, t) in enumerate(ims):
        sheet.paste(im.resize((w2, h2), Image.LANCZOS), (j * (w2 + 8), 18))
        dr.text((j * (w2 + 8) + 4, 2), t, fill=(255, 255, 0))
    sheet.save(os.path.join(d, "v2_mask.png"))


def render(painter, args, prompt, frame, seed, d, c):
    W, H = po.gen_hd.qwen21_size(frame.width * args.zoom, frame.height * args.zoom, args.mp)
    hl, wl = 2 * (H // 32), 2 * (W // 32)
    own, ctx, void = regions(frame, c)
    known, cond, _panel = canvases(frame, c, W, H)
    free, st = latent_mask(own, ctx, void, hl, wl)
    known.save(os.path.join(d, "v2_known.png"))
    cond.save(os.path.join(d, "v2_cond.png"))
    mask_sheet(known, cond, free, d)
    print("  V2: латенты %dx%d, целевая %.3f, свободно %.3f, клеток контекста в свободном %d, проёма %d пикс k=1"
          % (wl, hl, st["own"], st["free"], st["ctx_in_free"], int(void.sum())), flush=True)
    if painter == MASK_ONLY:
        raise SystemExit("--mask-only: листы в %s, модель не грузилась" % d)

    import weapons_probe5 as w5
    torch = painter.torch
    pipe = painter.pipe
    dev = pipe._execution_device
    with torch.no_grad():
        # VAE 2.1 четырёхканальный (RGBA), как и в самом конвейере: холст непрозрачный, альфа 255
        t = pipe.image_processor.preprocess(known.convert("RGBA"), H, W).unsqueeze(2).to(dev, pipe.vae.dtype)
        lat = pipe._encode_vae_image(t, generator=None)
        init = pipe._pack_latents(lat, 1, lat.shape[1], lat.shape[3], lat.shape[4]).to(torch.bfloat16)
    if init.shape[1] != hl * wl:
        raise SystemExit("латентов %d, маска %d (%dx%d)" % (init.shape[1], hl * wl, wl, hl))
    g = torch.Generator("cuda").manual_seed(seed + 1)
    noise = torch.randn(init.shape, generator=g, device=dev, dtype=torch.float32).to(init.dtype)
    m = torch.from_numpy(free.reshape(1, -1, 1).astype(np.float32)).to(dev, init.dtype)

    def cb(pp, i, _t, kw):
        x = kw["latents"]
        sg = float(pp.scheduler.sigmas[i + 1])
        noised = sg * noise + (1.0 - sg) * init
        return {"latents": (m * x.to(init.dtype) + (1.0 - m) * noised).to(x.dtype)}

    kw = {"prompt": prompt, "num_inference_steps": args.steps, "image": cond,
          "generator": torch.Generator("cuda").manual_seed(seed),
          "negative_prompt": po.gen_fire.NEGATIVE, "true_cfg_scale": args.cfg, "width": W, "height": H,
          "callback_on_step_end": cb, "callback_on_step_end_tensor_inputs": ["latents"]}
    miss = [k for k in ("image", "negative_prompt", "true_cfg_scale", "callback_on_step_end") if k not in painter.accepts]
    if miss:
        raise SystemExit("конвейер не принимает %s" % miss)
    with torch.no_grad():
        hd = pipe(**kw).images[0].convert("RGB")
    shared = w5.gpu_mem("V2 сид %d" % seed)
    if shared > 0.5:
        raise SystemExit("ушло в shared (%.1f ГБ) - стоп" % shared)
    return hd


def main():
    argv = sys.argv[1:]
    if "--thru" in argv:
        argv.remove("--thru")
        import wall_thru as wt
        ws.sil4_frame = wt.sil4_frame_open
        ws.assemble = wt.assemble_open
    if "--mask-only" in argv:
        argv.remove("--mask-only")
        po.gen_hd.Qwen21Painter = lambda *a, **k: MASK_ONLY
    if "--recut" in argv:
        raise SystemExit("--recut здесь не нужен: перевырезка готового ответа - wall_section.py --recut")
    ws.RENDER = render
    sys.argv = [sys.argv[0]] + argv
    ws.main()


if __name__ == "__main__":
    main()
