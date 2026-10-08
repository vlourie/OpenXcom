"""TREE_RENDER_V1: составное дерево FOREST 42-57 (и FOREST_WASTE) одним рисунком плюс срезы этажей
(решение специалиста 08.10, TREE METHOD CHECK принят). Независимый рендер кадров запрещён.

Рендеры на сид (все Qwen-Image-2.1 strict, одобренный путь obj_series, R-112):
  * MAIN       - дерево T1 целиком (вход - классика всего дерева, как составной obj_series);
  * CUT_Z0     - вид, где скрыты этажи 1-2: латенты MAIN вне ствола закреплены (как wall_v2), модель
                 меняет только место, которое в полном виде закрыто верхом, - срез ствола 57;
  * CUT_Z1     - вид без этажа 2: закреплены MAIN и уже готовый вид Z0, модель рисует верх яруса 1
                 со срезами 48, 50, 51;
  * пни FOREST:58 и BLACKFOREST:58 - по кадру, тот же путь, что одиночный предмет obj_series.

Сборка (без модели): у каждого куска цвет - вид своего этажа (V_z), маска - свой силуэт и кайма среди кусков
не выше своего этажа. Полный вид равен MAIN, вид без верха - срезу. Каждый номер кадра получает ОДНУ
картинку (53/54/55 стоят на двух этажах - берётся положение, ближе всего к остальным, отклонение в отчёте).
Из тех же 16 кадров собираются T1, T1b, T2, T3 (и куртина FOREST) во всех видах этажей.

  tree_render.py --mask-only            листы масок срезов по классике, модель не грузится
  tree_render.py [--max-renders 4]      рендер того, чего нет (возобновляемо; только через gpuq)
  tree_render.py --assemble             кадры, сборки, листы и числа из готовых ответов, без модели

Модель - только через очередь видеокарты (tools/gpu_scripts.txt).
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
for p in (HERE, os.path.dirname(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np                                  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter       # noqa: E402
import cv2                                          # noqa: E402
import probe_object as po                           # noqa: E402
import sprite_scale as ss                           # noqa: E402
import map_mockup as mm                             # noqa: E402

ENC = "utf-8-sig"
OUT = "census/trees/forest42/render_v1"
CLUSTERS = "census/trees/forest42/clusters.json"
OLD = "Пиратки/Dioxine_XPiratez/user/mods/hd/hd/TERRAIN"
HINTS = "art/objects/composite_hints.json"
FLOOR = (52, 58, 46)
TOP = 2                       # верхний этаж T1
SETS = ("FOREST", "FOREST_WASTE")
# срезы - только то, что есть на классике вида (R-016, R-040); «не новая ёлка» - решение специалиста
CUT_WHAT = {
    ("FOREST", 1): "the lower tiers of one large dense conifer tree whose top tier has been removed: "
                   "a flat top of dark green needle branches with a few small brown cut ends of the trunk "
                   "and branches showing on top",
    ("FOREST", 0): "the lower part of one tall conifer trunk whose crown has been removed: one straight dark "
                   "brown trunk as tall as the brown column in the image, rising directly out of the roots "
                   "that are already drawn at the bottom, with a flat light brown sawn top and a few short "
                   "green branch stubs on its sides; the trunk reaches down to those roots without a gap, "
                   "one single trunk only",
    ("FOREST_WASTE", 1): "the lower tiers of one large dead charred tree whose top tier has been removed: "
                         "blackish grey withered branches with a few pale pinkish ring-shaped cut ends on top",
    ("FOREST_WASTE", 0): "the lower part of one tall dead charred trunk whose crown has been removed: one "
                         "straight grey-black trunk as tall as the dark column in the image, rising directly "
                         "out of the roots that are already drawn at the bottom, with a pale sawn top and a "
                         "few bare twig stubs on its sides; the trunk reaches down to those roots without a "
                         "gap, one single trunk only",
}
STUMPS = {
    ("FOREST", 58): "a sawn-off stump of a dark brown conifer trunk with spreading roots and small green moss "
                    "tufts at the base",
    ("BLACKFOREST", 58): "a broken dark violet-black tree stump with a jagged broken top and spreading roots",
}
LAYOUTS = {"FOREST": (("T1", 0), ("T1b", 2), ("T2", 1), ("T3", 6), ("clump", 4)),
           "FOREST_WASTE": (("T1", 0), ("T1b", 2), ("T2", 1), ("T3", 7))}
CUT_SEED = {0: 101, 1: 202}


# ---------------------------------------------------------------- раскладка и маски (k=1)

class Tree:
    """Раскладка T1 набора: куски, холст k=1, маски этажей."""

    def __init__(self, world, S, sig, grow):
        self.S = S
        pcs = []
        for f, p, x, y, z in sig:
            pcs.append(dict(f=f, z=z, key=(z, y, x, p), sx=(x - y) * 16,
                            sy=(x + y) * 8 - z * 24 - plevel(world, S, f)))
        pcs.sort(key=lambda q: q["key"])                     # порядок рисования игры
        x0 = min(q["sx"] for q in pcs)
        y0 = min(q["sy"] for q in pcs)
        self.W = max(q["sx"] for q in pcs) - x0 + 32
        self.H = max(q["sy"] for q in pcs) - y0 + 40
        for q in pcs:
            q["at"] = (q["sx"] - x0, q["sy"] - y0)
            q["spr"] = sprite(world, S, q["f"])
            m = np.zeros((self.H, self.W), bool)
            x, y = q["at"]
            m[y:y + 40, x:x + 32] = np.asarray(q["spr"])[..., 3] > 0
            q["sil"] = m
        self.pcs = pcs
        self.top = max(q["z"] for q in pcs)
        self.lab, self.anys = {}, {}
        for z in range(self.top + 1):
            self.lab[z], self.anys[z] = partition(pcs, [i for i, q in enumerate(pcs) if q["z"] <= z],
                                                  self.H, self.W, grow)
        # что рисует кусок: свой силуэт целиком и кайма среди кусков не выше своего этажа
        for i, q in enumerate(pcs):
            z = q["z"]
            q["draw"] = q["sil"] | ((self.lab[z] == i) & ~self.anys[z])
        self.lv = np.array([q["z"] for q in pcs])

    def upper(self, z):
        """U_z: всё, что рисуют куски выше этажа z (в полном виде закрывает нижние)."""
        u = np.zeros((self.H, self.W), bool)
        for q in self.pcs:
            if q["z"] > z:
                u |= q["draw"]
        return u

    def owner_level(self, z):
        """Этаж куска, который в виде z владеет пикселем (-1 - никто)."""
        lab = self.lab[z]
        return np.where(lab >= 0, self.lv[np.maximum(lab, 0)], -1)

    def compose(self, zmax=99, k=1):
        im = Image.new("RGBA", (self.W * k, self.H * k), (0, 0, 0, 0))
        for q in self.pcs:
            if q["z"] <= zmax:
                s = q["spr"] if k == 1 else q["spr"].resize((32 * k, 40 * k), Image.NEAREST)
                im.alpha_composite(s, (q["at"][0] * k, q["at"][1] * k))
        return im


def partition(pcs, sel, H, W, grow):
    """Как obj_series.split: силуэты (верхний по порядку рисования - первым) и кайма grow+2 шагов, спорный
    пиксель - тому, кто дотянулся первым."""
    lab = np.full((H, W), -1, np.int32)
    for i in reversed(sel):
        m = pcs[i]["sil"]
        lab[m & (lab < 0)] = i
    anys = lab >= 0
    for _ in range(grow + 2):
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            src = np.roll(lab, (dy, dx), (0, 1))
            take = (lab < 0) & (src >= 0)
            lab[take] = src[take]
    return lab, anys


_PL = {}


def plevel(world, S, f):
    if (S, f) not in _PL:
        _PL[(S, f)] = next((r["p_level"] for r in world.records(S) if r["frame"] == f), 0)
    return _PL[(S, f)]


_SPR = {}


def sprite(world, S, f):
    if (S, f) not in _SPR:
        _SPR[(S, f)] = world.sprite(S, f, None).convert("RGBA")
    return _SPR[(S, f)]


def rep4(m):
    return np.repeat(np.repeat(m, 4, 0), 4, 1)


def xbrz(img, k=4):
    up = ss.xbrz_scale(np.asarray(img.convert("RGBA"), np.float32)[None], k)[0]
    return Image.fromarray(np.clip(up, 0, 255).astype(np.uint8), "RGBA")


def crop_box(img, pad):
    bb = img.split()[3].getbbox()
    return (max(0, bb[0] - pad), max(0, bb[1] - pad), min(img.width, bb[2] + pad), min(img.height, bb[3] + pad))


# ---------------------------------------------------------------- геометрия вырезки (как po.cut_out)

def cut_geom(hd, frame, soft, floor=0.30, max_aspect=1.3):
    """Те же шаги, что po.cut_out, но с запомненным переносом ответ -> кадр x4: срезы рисуются на холсте
    MAIN (закреплённые латенты) и обязаны лечь в те же пиксели."""
    a = np.asarray(hd.convert("RGB"), np.float32)
    edge = np.concatenate([a[:8].reshape(-1, 3), a[-8:].reshape(-1, 3),
                           a[:, :8].reshape(-1, 3), a[:, -8:].reshape(-1, 3)])
    bg = tuple(float(v) for v in np.median(edge, axis=0))
    al = keyed_alpha(hd, bg, soft, floor)
    cw, ch = frame.width * 4, frame.height * 4
    ob = frame.split()[3].getbbox()
    ab = Image.fromarray((al > 0.5).astype(np.uint8) * 255, "L").filter(ImageFilter.MinFilter(5)).getbbox()
    ab = (max(0, ab[0] - 2), max(0, ab[1] - 2), min(hd.width, ab[2] + 2), min(hd.height, ab[3] + 2))
    ox0, oy0, ox1, oy1 = [v * 4 for v in ob]
    sw, sh = (ox1 - ox0) / (ab[2] - ab[0]), (oy1 - oy0) / (ab[3] - ab[1])
    s = (sw * sh) ** 0.5
    sw = min(max(sw, s / max_aspect), s * max_aspect)
    sh = min(max(sh, s / max_aspect), s * max_aspect)
    pw, ph = max(1, round((ab[2] - ab[0]) * sw)), max(1, round((ab[3] - ab[1]) * sh))
    return dict(bg=bg, ab=ab, pw=pw, ph=ph, px=round((ox0 + ox1 - pw) / 2), py=oy1 - ph, cw=cw, ch=ch,
                soft=soft, floor=floor, raw=hd.size)


def keyed_alpha(hd, bg, soft, floor):
    rgba = po.gen_fire.unpanel(hd, bg, soft)
    al = np.asarray(rgba.split()[3], np.float32) / 255.0
    return np.clip((al - floor) / (1.0 - floor), 0.0, 1.0)


def to_body(hd, g):
    """Ответ (холст рендера) -> кадр x4 габарита crop: подложка снята, перенос как у MAIN."""
    rgba = po.gen_fire.unpanel(hd, g["bg"], g["soft"])
    al = keyed_alpha(hd, g["bg"], g["soft"], g["floor"])
    rgba.putalpha(Image.fromarray((al * 255).astype(np.uint8), "L"))
    piece = rgba.crop(g["ab"]).resize((g["pw"], g["ph"]), Image.LANCZOS)
    M = max(piece.width, piece.height)
    big = Image.new("RGBA", (g["cw"] + 2 * M, g["ch"] + 2 * M), (0, 0, 0, 0))
    big.alpha_composite(piece, (M + g["px"], M + g["py"]))
    return big.crop((M, M, M + g["cw"], M + g["ch"]))


def body_to_raw(img, g, resample):
    """Обратный перенос: картинка/маска x4 габарита crop -> холст рендера (вне ab - пусто)."""
    M = max(g["pw"], g["ph"])
    mode = img.mode
    big = Image.new(mode, (g["cw"] + 2 * M, g["ch"] + 2 * M), 0)
    big.paste(img, (M, M))
    part = big.crop((M + g["px"], M + g["py"], M + g["px"] + g["pw"], M + g["py"] + g["ph"]))
    ab = g["ab"]
    part = part.resize((ab[2] - ab[0], ab[3] - ab[1]), resample)
    raw = Image.new(mode, g["raw"], 0)
    raw.paste(part, (ab[0], ab[1]))
    return raw


def mask_raw(m4body, g):
    im = Image.fromarray(m4body.astype(np.uint8) * 255, "L")
    return np.asarray(body_to_raw(im, g, Image.NEAREST)) > 127


def sil_limit(frame, grow):
    sil = frame.split()[3].point(lambda v: 255 if v > 0 else 0)
    if grow > 0:
        sil = sil.filter(ImageFilter.MaxFilter(2 * grow + 1))
    return np.asarray(po.smooth_silhouette(sil, 4), np.float32) / 255.0


def limit_alpha(body, frame, grow):
    m = np.asarray(body.split()[3], np.float32) * sil_limit(frame, grow)
    out = body.copy()
    out.putalpha(Image.fromarray(m.astype(np.uint8), "L"))
    return out


def tone_params(cut, frame):
    """Параметры po.match_tone (сдвиг среднего и разброса к оригиналу) - один раз по MAIN, дальше они же
    для срезов: иначе срез и полный вид разойдутся тоном на стыке."""
    o = np.asarray(frame.convert("RGBA"), np.float32)
    o = o[..., :3][o[..., 3] > 128]
    c = np.asarray(cut, np.float32)
    src = c[..., :3][c[..., 3] > 128]
    ms, ss_ = src.mean(0), src.std(0) + 1e-3
    mo, so = o.mean(0), o.std(0) + 1e-3
    return ms, np.minimum(so / ss_, 1.0), mo


def apply_tone(cut, p, amount):
    ms, gain, mo = p
    c = np.asarray(cut, np.float32).copy()
    rgb = c[..., :3]
    toned = (rgb - ms) * gain + mo
    c[..., :3] = np.clip(rgb + (toned - rgb) * amount, 0, 255)
    return Image.fromarray(c.astype(np.uint8), "RGBA")


# ---------------------------------------------------------------- модель

def painter_new(args):
    ns = argparse.Namespace(models=po.gen_hd.DEFAULT_MODELS_DIR, qwen21_model="", qwen21_steps=args.steps,
                            qwen21_cfg=args.cfg, qwen21_mp=args.mp, qwen21_strength=0.0,
                            qwen21_offload="model", qwen21_thrifty=False, qwen21_ref="", qwen21_ref_mp=1.0,
                            qwen21_prompt="strict", qwen21_hint="off", qwen21_ref_order="ref-first")
    po.gen_fire.NEGATIVE = po.NEGATIVE
    return po.gen_hd.Qwen21Painter(ns, {"ground": ("", "")})


def check_shared(tag):
    import weapons_probe5 as w5
    shared = w5.gpu_mem(tag)
    if shared > 0.5:
        raise SystemExit("ушло в shared (%.1f ГБ) - стоп" % shared)


def paint_strict(painter, args, frame, what, seed):
    """Одобренный путь obj_series.paint: классика bicubic x16 на подложке, strict."""
    panel = po.pick_background(frame)
    src = frame.resize((frame.width * args.zoom, frame.height * args.zoom), Image.BICUBIC)
    flat = Image.new("RGBA", src.size, tuple(panel) + (255,))
    flat.alpha_composite(src)
    prompt = po.STYLE["strict"].replace("{what}", what)
    return po.gen_fire.run_pass(painter, args, prompt, flat.convert("RGB"), seed).convert("RGB")


def paint_locked(painter, args, known, cond, free, what, seed):
    """Как wall_v2.render: латенты вне free на каждом шаге - зашумлённый известный холст."""
    torch = painter.torch
    pipe = painter.pipe
    dev = pipe._execution_device
    W, H = known.size
    hl, wl = H // 16, W // 16
    with torch.no_grad():
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

    kw = {"prompt": po.STYLE["strict"].replace("{what}", what), "num_inference_steps": args.steps,
          "image": cond, "generator": torch.Generator("cuda").manual_seed(seed),
          "negative_prompt": po.gen_fire.NEGATIVE, "true_cfg_scale": args.cfg, "width": W, "height": H,
          "callback_on_step_end": cb, "callback_on_step_end_tensor_inputs": ["latents"]}
    miss = [k for k in ("image", "negative_prompt", "true_cfg_scale", "callback_on_step_end")
            if k not in painter.accepts]
    if miss:
        raise SystemExit("конвейер не принимает %s" % miss)
    with torch.no_grad():
        return pipe(**kw).images[0].convert("RGB")


# ---------------------------------------------------------------- одно дерево: холсты срезов

class Job:
    """Дерево набора S на сиде seed: пути, MAIN, срезы, виды этажей."""

    def __init__(self, world, CL, hints, S, seed, args):
        self.S, self.seed, self.args = S, seed, args
        self.tree = Tree(world, S, CL[S]["sigs"][0]["sig"], args.grow)
        self.whole = self.tree.compose()
        self.box = crop_box(self.whole, args.pad)
        self.frame = self.whole.crop(self.box)
        self.what = hints[S + ":57"]
        self.d = os.path.join(args.out, "s%d" % seed, S)
        os.makedirs(self.d, exist_ok=True)
        self.raw_main = os.path.join(self.d, "raw_main.png")

    def raw_cut(self, z):
        return os.path.join(self.d, "raw_cut_z%d.png" % z)

    def body4(self, m):
        """Маска k=1 холста -> x4 габарита crop."""
        b = self.box
        return rep4(m[b[1]:b[3], b[0]:b[2]])

    def frame_z(self, z):
        return self.tree.compose(z).crop(self.box)

    def masks(self, z):
        """U_z, владелец-этаж в виде z и свободное (k=1 холста)."""
        t = self.tree
        U = t.upper(z)
        own = t.owner_level(z)
        sil_le = np.zeros_like(U)
        for q in t.pcs:
            if q["z"] <= z:
                sil_le |= q["sil"]
        near = cv2.dilate(sil_le.astype(np.uint8), np.ones((7, 7), np.uint8)) > 0
        F = U & (own == z) & near
        return U, own, F

    def main_cut(self):
        """MAIN: ответ -> кадр x4 (сверка с po.cut_out/match_tone до пикселя), параметры переноса и тона."""
        hd = Image.open(self.raw_main).convert("RGB")
        g = cut_geom(hd, self.frame, self.args.soft)
        body = limit_alpha(to_body(hd, g), self.frame, self.args.grow)
        tp = tone_params(body, self.frame)
        main = apply_tone(body, tp, self.args.tone)
        ref = po.match_tone(po.cut_out(hd, self.frame, self.args.grow, self.args.soft), self.frame, self.args.tone)
        dev = np.abs(np.asarray(ref, np.int16) - np.asarray(main, np.int16)).max()
        if dev > 1:
            raise SystemExit("%s: вырезка MAIN разошлась с po.cut_out на %d - перенос неверен" % (self.S, dev))
        return hd, g, tp, main

    def canvases(self, z, hd, g, vraw):
        """Известный холст, условие и свободные клетки для CUT_z (холст ответа MAIN)."""
        U, own, F = self.masks(z)
        U_r = mask_raw(self.body4(U), g)
        F_r = mask_raw(self.body4(F), g)
        known = np.asarray(hd, np.uint8).copy()
        known[U_r] = np.array(g["bg"], np.float32).round().astype(np.uint8)
        for zz in range(z):                      # где в виде z владеет кусок ниже - его готовый вид
            m = mask_raw(self.body4(U & (own == zz)), g)
            known[m] = np.asarray(vraw[zz], np.uint8)[m]
        known = Image.fromarray(known)
        cls = xbrz(self.frame_z(z))
        flat = Image.new("RGBA", cls.size, tuple(int(round(v)) for v in g["bg"]) + (255,))
        flat.alpha_composite(cls)
        cls_r = np.asarray(body_to_raw(flat, g, Image.LANCZOS).convert("RGB"))
        cond = np.asarray(known).copy()
        cond[F_r] = cls_r[F_r]
        W, H = hd.size
        hl, wl = H // 16, W // 16
        f = cv2.resize(F_r.astype(np.float32), (wl, hl), interpolation=cv2.INTER_AREA) > 0
        free = cv2.dilate(f.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
        return known, Image.fromarray(cond), free, U_r

    def vraw(self, z, hd, raw_cut, U_r, vprev):
        """Вид z на холсте ответа: MAIN, на U_z - срез (там, где владеет кусок этажа z) или вид ниже."""
        _U, own, _F = self.masks(z)
        g = self._g
        v = np.asarray(hd, np.uint8).copy()
        v[U_r] = np.asarray(raw_cut, np.uint8)[U_r]
        for zz in range(z):
            m = mask_raw(self.body4(_U & (own == zz)), g)
            v[m] = np.asarray(vprev[zz], np.uint8)[m]
        return Image.fromarray(v)


def mask_sheet(path, cond, known, free, title):
    W, H = known.size
    big = cv2.resize(free.astype(np.uint8), (W, H), interpolation=cv2.INTER_NEAREST) > 0
    over = np.asarray(cond, np.float32).copy()
    over[big] = over[big] * 0.45 + np.array([255, 0, 0], np.float32) * 0.55
    k = min(1.0, 700.0 / W)
    ims = [(cond, "condition"), (known, "locked canvas"), (Image.fromarray(over.astype(np.uint8)), "red = free")]
    w2, h2 = int(W * k), int(H * k)
    sheet = Image.new("RGB", (w2 * 3 + 16, h2 + 34), (30, 30, 34))
    dr = ImageDraw.Draw(sheet)
    dr.text((4, 2), title, fill=(255, 255, 255))
    for j, (im, t) in enumerate(ims):
        sheet.paste(im.resize((w2, h2), Image.LANCZOS), (j * (w2 + 8), 32))
        dr.text((j * (w2 + 8) + 4, 18), t, fill=(255, 255, 0))
    sheet.save(path)


def classic_mask_sheet(job, path):
    """--mask-only: по классике - вид всё / без верха / ствол, U_z (красным) и свободное (жёлтым) x4."""
    t = job.tree
    cells = []
    for z in range(t.top + 1):
        img = np.asarray(xbrz(t.compose(z)), np.float32)
        bg = np.zeros_like(img)
        bg[..., :3] = FLOOR
        bg[..., 3] = 255
        a = img[..., 3:4] / 255.0
        rgb = img[..., :3] * a + bg[..., :3] * (1 - a)
        if z < t.top:
            U, _own, F = job.masks(z)
            u4, f4 = rep4(U), rep4(F)
            rgb[u4] = rgb[u4] * 0.6 + np.array([255, 0, 0]) * 0.4
            rgb[f4] = rgb[f4] * 0.5 + np.array([255, 255, 0]) * 0.5
        cells.append(Image.fromarray(rgb.astype(np.uint8)))
    w, h = cells[0].size
    sheet = Image.new("RGB", (len(cells) * (w + 8), h + 20), (30, 30, 34))
    dr = ImageDraw.Draw(sheet)
    for j, c in enumerate(reversed(cells)):
        z = t.top - j
        sheet.paste(c, (j * (w + 8), 20))
        dr.text((j * (w + 8) + 4, 4), "z<=%d%s" % (z, "" if z == t.top else "  red=U (covered by upper), "
                                                   "yellow=free"), fill=(255, 255, 0))
    sheet.save(path)


# ---------------------------------------------------------------- рендер (возобновляемо)

def do_render(args, world, CL, hints):
    painter = None
    done = 0
    t0 = time.time()

    def need():
        nonlocal painter
        if args.max_renders and done >= args.max_renders:
            print("предел рендеров на процесс %d - выход (R-215)" % args.max_renders, flush=True)
            raise SystemExit(0)
        if painter is None:
            painter = painter_new(args)

    for seed in args.seeds:
        for S in SETS:
            job = Job(world, CL, hints, S, seed, args)
            if not os.path.exists(job.raw_main):
                need()
                hd = paint_strict(painter, args, job.frame, job.what, seed)
                po.gen_hd.save_png(hd, job.raw_main)
                done += 1
                check_shared("%s MAIN s%d" % (S, seed))
                print("  %s MAIN s%d готов (%d за %.0f с)" % (S, seed, done, time.time() - t0), flush=True)
            hd, g, _tp, _main = job.main_cut()
            job._g = g
            vraw = {}
            for z in range(job.tree.top):
                known, cond, free, U_r = job.canvases(z, hd, g, vraw)
                p = job.raw_cut(z)
                if not os.path.exists(p):
                    need()
                    known.save(os.path.join(job.d, "known_z%d.png" % z))
                    cond.save(os.path.join(job.d, "cond_z%d.png" % z))
                    mask_sheet(os.path.join(job.d, "mask_z%d.png" % z), cond, known, free,
                               "%s CUT_Z%d s%d: free %.3f" % (S, z, seed, free.mean()))
                    cut = paint_locked(painter, args, known, cond, free, CUT_WHAT[(S, z)], seed + CUT_SEED[z])
                    po.gen_hd.save_png(cut, p)
                    done += 1
                    check_shared("%s CUT_Z%d s%d" % (S, z, seed))
                    print("  %s CUT_Z%d s%d готов, свободно %.3f (%d за %.0f с)"
                          % (S, z, seed, free.mean(), done, time.time() - t0), flush=True)
                vraw[z] = job.vraw(z, hd, Image.open(p).convert("RGB"), U_r, vraw)
        for (S, f), what in STUMPS.items():
            p = os.path.join(args.out, "s%d" % seed, "stump_%s_%d.png" % (S, f))
            if os.path.exists(p):
                continue
            need()
            spr = sprite(world, S, f)
            hd = paint_strict(painter, args, spr.crop(crop_box(spr, args.pad)), what, seed)
            po.gen_hd.save_png(hd, p)
            done += 1
            check_shared("пень %s:%d s%d" % (S, f, seed))
            print("  пень %s:%d s%d готов (%d за %.0f с)" % (S, f, seed, done, time.time() - t0), flush=True)
    print("рендер: всё на месте, новых %d" % done, flush=True)


# ---------------------------------------------------------------- сборка (без модели)

def on_floor(rgba):
    bg = Image.new("RGBA", rgba.size, FLOOR + (255,))
    bg.alpha_composite(rgba)
    return bg.convert("RGB")


def views(job):
    """Виды этажей x4 холста: V[top] = MAIN, V[z] - срез; плюс числа шва и дрейфа VAE."""
    hd, g, tp, main = job.main_cut()
    job._g = g
    t, b = job.tree, job.box
    canvas = lambda body: paste4(body, b, t)       # noqa: E731
    V = {t.top: canvas(main)}
    vraw, stats = {}, {}
    for z in range(t.top):
        known, _cond, free, U_r = job.canvases(z, hd, g, vraw)
        raw = Image.open(job.raw_cut(z)).convert("RGB")
        vraw[z] = job.vraw(z, hd, raw, U_r, vraw)
        fz = job.frame_z(z)
        cut = apply_tone(limit_alpha(to_body(raw, g), fz, job.args.grow), tp, job.args.tone)
        cut4 = np.asarray(canvas(cut), np.uint8)
        U, own, _F = job.masks(z)
        U4, own4 = rep4(U), rep4(own)
        v = np.asarray(V[t.top], np.uint8).copy()
        v[U4 & (own4 == z)] = cut4[U4 & (own4 == z)]
        for zz in range(z):
            m = U4 & (own4 == zz)
            v[m] = np.asarray(V[zz], np.uint8)[m]
        v[U4 & (own4 < 0)] = 0
        V[z] = Image.fromarray(v)
        # шов: пиксели MAIN рядом с U_z - насколько срез у границы похож на MAIN; дрейф VAE закреплённого
        ring = (cv2.dilate(U4.astype(np.uint8), np.ones((13, 13), np.uint8)) > 0) & ~U4
        m4 = np.asarray(V[t.top], np.uint8)
        ring &= m4[..., 3] > 200
        seam = float(np.abs(cut4[..., :3].astype(np.int16) - m4[..., :3])[ring].mean()) if ring.any() else -1
        W, H = hd.size
        lock = ~(cv2.resize(cv2.dilate(free.astype(np.uint8), np.ones((5, 5), np.uint8)), (W, H),
                            interpolation=cv2.INTER_NEAREST) > 0)
        drift = float(np.abs(np.asarray(raw, np.int16) - np.asarray(known, np.int16))[lock].mean())
        stats["z%d" % z] = dict(seam_mean_abs=round(seam, 2), locked_vae_drift=round(drift, 2),
                                free_cells=round(float(free.mean()), 3))
    return V, stats


def paste4(body, box, t):
    c = Image.new("RGBA", (t.W * 4, t.H * 4), (0, 0, 0, 0))
    c.paste(body, (box[0] * 4, box[1] * 4))
    return c


def pieces(job, V):
    """Кусок = вид своего этажа под своей маской; номер кадра - одна картинка. Кадр на двух местах (53/54/55
    стоят на этажах 1 и 2): часть кадра на одном месте закрыта соседом, а на другом видна, поэтому пиксель
    кадра берётся с того места, где он виден в виде своего этажа; виден на обоих - с верхнего (полный вид).
    Пиксели, видные на обоих местах, - настоящий конфликт: на нижнем месте они разойдутся с задуманным."""
    t = job.tree
    pos = {}
    for i, q in enumerate(t.pcs):
        v = np.asarray(V[q["z"]], np.uint8).copy()
        v[..., 3] = (v[..., 3] * rep4(q["draw"])).astype(np.uint8)
        cover = np.zeros_like(q["draw"])                 # в виде своего этажа: позже и не выше
        cover_all = np.zeros_like(q["draw"])             # в полном виде: всё, что рисуется позже
        for k in range(i + 1, len(t.pcs)):
            cover_all |= t.pcs[k]["sil"]
            if t.pcs[k]["z"] <= q["z"]:
                cover |= t.pcs[k]["sil"]
        x, y = q["at"]
        box = (x * 4, y * 4, x * 4 + 128, y * 4 + 160)
        vis = rep4(q["draw"] & ~cover)[box[1]:box[3], box[0]:box[2]]
        vis_full = rep4(q["draw"] & ~cover_all)[box[1]:box[3], box[0]:box[2]]
        pos.setdefault(q["f"], []).append((q, np.asarray(Image.fromarray(v).crop(box)), vis, vis_full))
    frames, report = {}, {}
    for f, lst in pos.items():
        if len(lst) == 1:
            frames[f] = Image.fromarray(lst[0][1])
            continue
        lst.sort(key=lambda e: -e[0]["z"])              # верхнее место - первым
        out = np.zeros_like(lst[0][1])
        done = np.zeros(out.shape[:2], bool)
        for layer in (3, 2):                             # виден в полном виде, потом в виде своего этажа
            for e in lst:
                take = e[layer] & ~done
                out[take] = e[1][take]
                done |= take
        for e in lst:                                    # закрыт везде - откуда есть
            take = (e[1][..., 3] > 0) & ~done
            out[take] = e[1][take]
            done |= take
        both = lst[0][3].copy()
        for e in lst[1:]:
            both &= e[3]
        conf = 0.0
        if both.any():
            d = [np.abs(lst[0][1][..., :3].astype(np.int16) - e[1][..., :3])[both].max(-1) for e in lst[1:]]
            conf = float(np.concatenate(d).mean())
        frames[f] = Image.fromarray(out)
        report[f] = dict(positions=["z%d" % e[0]["z"] for e in lst],
                         visible_full_px=[int(e[3].sum()) for e in lst], visible_full_in_all=int(both.sum()),
                         conflict_mean_abs=round(conf, 1))
    return frames, report


def assemble(world, S, sig, frames, zmax, k=4, src=None):
    """Раскладка sig -> картинка x4: кадры frames (128x160) или классика (src=None, frames=None)."""
    rows = []
    for f, p, x, y, z in sig:
        rows.append(((z, y, x, p), f, (x - y) * 16, (x + y) * 8 - z * 24 - plevel(world, S, f)))
    rows.sort()
    x0 = min(r[2] for r in rows)
    y0 = min(r[3] for r in rows)
    W = max(r[2] for r in rows) - x0 + 32
    H = max(r[3] for r in rows) - y0 + 40
    im = Image.new("RGBA", (W * k, H * k), (0, 0, 0, 0))
    for key, f, sx, sy in rows:
        if key[0] > zmax:
            continue
        if frames is None:
            s = sprite(world, S, f).resize((32 * k, 40 * k), Image.NEAREST)
        else:
            s = frames.get(f)
            if s is None:
                continue
        im.alpha_composite(s, ((sx - x0) * k, (sy - y0) * k))
    return im


def old_frames(S):
    out = {}
    for f in range(42, 59):
        p = os.path.join(OLD, S + ".PCK", "%d.png" % f)
        if os.path.exists(p):
            out[f] = Image.open(p).convert("RGBA")
    return out


def diff(a, b):
    x = np.asarray(on_floor(a), np.int16)
    y = np.asarray(on_floor(b), np.int16)
    m = (np.asarray(a)[..., 3] > 0) | (np.asarray(b)[..., 3] > 0)
    d = np.abs(x - y).max(-1)[m]
    return dict(mean=round(float(d.mean()), 2), p99=int(np.percentile(d, 99)), over24=round(float((d > 24).mean()), 4))


def grid(rows, path, title, scale=1.0):
    """rows: [(подпись ряда, [(подпись, картинка RGBA), ...]), ...] на полу."""
    cells = [[(t, on_floor(im)) for t, im in r] for _n, r in rows]
    if scale != 1.0:
        cells = [[(t, im.resize((int(im.width * scale), int(im.height * scale)), Image.LANCZOS)) for t, im in r]
                 for r in cells]
    cw = max(im.width for r in cells for _t, im in r)
    ch = [max(im.height for _t, im in r) for r in cells]
    ncol = max(len(r) for r in cells)
    W = 120 + ncol * (cw + 8)
    H = 24 + sum(h + 22 for h in ch)
    sheet = Image.new("RGB", (W, H), (28, 28, 32))
    dr = ImageDraw.Draw(sheet)
    dr.text((6, 4), title, fill=(255, 255, 255))
    y = 24
    for (name, _r), r, h in zip(rows, cells, ch):
        dr.text((6, y + h // 2), name, fill=(255, 255, 0))
        for j, (t, im) in enumerate(r):
            x = 120 + j * (cw + 8)
            sheet.paste(im, (x, y + 16))
            dr.text((x + 2, y + 2), t, fill=(200, 200, 200))
        y += h + 22
    sheet.save(path)


def do_assemble(args, world, CL, hints):
    summary = {}
    for seed in args.seeds:
        sd = os.path.join(args.out, "s%d" % seed)
        for S in SETS:
            job = Job(world, CL, hints, S, seed, args)
            if not (os.path.exists(job.raw_main) and all(os.path.exists(job.raw_cut(z)) for z in range(job.tree.top))):
                print("  %s s%d: ответов нет - пропуск" % (S, seed))
                continue
            V, stats = views(job)
            frames, multi = pieces(job, V)
            fd = os.path.join(job.d, "frames", S + ".PCK")
            os.makedirs(fd, exist_ok=True)
            for f, im in frames.items():
                po.gen_hd.save_png(im, os.path.join(fd, "%d.png" % f))
            olds = old_frames(S)
            t = job.tree
            # T1 собран из кадров против задуманных видов
            sig0 = CL[S]["sigs"][0]["sig"]
            checks = {}
            for z in range(t.top, -1, -1):
                a = assemble(world, S, sig0, frames, z)
                checks["T1_z<=%d" % z] = diff(a, crop_like(V[z], a))
            stats["T1_assembled_vs_intended"] = checks
            stats["multi_position_frames"] = multi
            summary["%s s%d" % (S, seed)] = stats
            # лист 1: целиком
            grid([("whole", [("classic x4", job.whole.resize((t.W * 4, t.H * 4), Image.NEAREST)),
                             ("old HD (T1)", assemble(world, S, sig0, olds, 99)),
                             ("MAIN (render)", V[t.top]),
                             ("T1 from frames", assemble(world, S, sig0, frames, 99))])],
                 os.path.join(sd, "%s_whole.png" % S), "%s s%d: whole tree" % (S, seed))
            # лист 2: раскладки во всех видах этажей
            rows = []
            for name, i in LAYOUTS[S]:
                sig = CL[S]["sigs"][i]["sig"]
                ztop = max(e[4] for e in sig)
                for kind, fr in (("classic", None), ("old", olds), ("new", frames)):
                    rows.append(("%s %s" % (name, kind),
                                 [("z<=%d" % z, assemble(world, S, sig, fr, z)) for z in range(ztop, -1, -1)]))
            grid(rows, os.path.join(sd, "%s_layouts.png" % S),
                 "%s s%d: T1/T1b/T2/T3 from the SAME frames; columns = all floors, upper hidden, ..." % (S, seed),
                 scale=0.5)
            # лист 3: кадры 42-58
            frow = []
            for f in range(42, 58):
                frow.append(("%d" % f, [("classic", sprite(world, S, f).resize((128, 160), Image.NEAREST)),
                                        ("old", olds.get(f, Image.new("RGBA", (128, 160)))),
                                        ("new", frames[f])]))
            half = (len(frow) + 1) // 2
            grid([(a[0] + " | " + b[0], a[1] + b[1]) for a, b in zip(frow[:half], frow[half:])],
                 os.path.join(sd, "%s_frames.png" % S), "%s s%d: frames 42-57 classic | old | new" % (S, seed))
            print("  %s s%d: собрано, %s" % (S, seed, json.dumps(stats, ensure_ascii=False)), flush=True)
        # пни
        prow = []
        for (S, f), _what in STUMPS.items():
            p = os.path.join(sd, "stump_%s_%d.png" % (S, f))
            if not os.path.exists(p):
                continue
            spr = sprite(world, S, f)
            box = crop_box(spr, args.pad)
            fr = spr.crop(box)
            hd = Image.open(p).convert("RGB")
            part = po.match_tone(po.cut_out(hd, fr, args.grow, args.soft), fr, args.tone)
            cut = Image.new("RGBA", (128, 160), (0, 0, 0, 0))
            cut.paste(part, (box[0] * 4, box[1] * 4))
            od = os.path.join(sd, "stumps", S + ".PCK")
            os.makedirs(od, exist_ok=True)
            po.gen_hd.save_png(cut, os.path.join(od, "%d.png" % f))
            old = os.path.join(OLD, S + ".PCK", "%d.png" % f)
            prow.append(("%s:%d" % (S, f), [("classic", spr.resize((128, 160), Image.NEAREST)),
                                            ("old", Image.open(old).convert("RGBA") if os.path.exists(old)
                                             else Image.new("RGBA", (128, 160))),
                                            ("new", cut)]))
        if prow:
            grid(prow, os.path.join(sd, "stumps.png"), "stumps s%d: classic | old | new" % seed)
    with open(os.path.join(args.out, "summary.json"), "w", encoding=ENC) as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=1)
    print("сборка: %s" % os.path.join(args.out, "summary.json"))


def crop_like(v, a):
    """Задуманный вид (холст дерева T1 x4) и сборка T1 из кадров - один и тот же холст по построению."""
    if v.size != a.size:
        raise SystemExit("холст вида %s и сборки %s разные" % (v.size, a.size))
    return v


def do_masks(args, world, CL, hints):
    for S in SETS:
        job = Job(world, CL, hints, S, args.seeds[0], args)
        t = job.tree
        for z in range(t.top):
            U, own, F = job.masks(z)
            print("  %s срез z%d: U %d пикс k=1, свободно %d, владельцы этажей %s"
                  % (S, z, int(U.sum()), int(F.sum()), sorted(set(own[U].tolist()))))
        p = os.path.join(args.out, "mask_%s.png" % S)
        classic_mask_sheet(job, p)
        print("  лист", p)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--seeds", default="2711,2712")
    ap.add_argument("--steps", type=int, default=40)
    ap.add_argument("--cfg", type=float, default=4.0)
    ap.add_argument("--mp", type=float, default=1.0)
    ap.add_argument("--zoom", type=int, default=16)
    ap.add_argument("--grow", type=int, default=2)
    ap.add_argument("--soft", type=int, default=40)
    ap.add_argument("--pad", type=int, default=3)
    ap.add_argument("--tone", type=float, default=0.7)
    ap.add_argument("--max-renders", type=int, default=4, dest="max_renders")
    ap.add_argument("--mask-only", action="store_true", dest="mask_only", help="листы масок, без модели")
    ap.add_argument("--assemble", action="store_true", help="кадры, сборки, листы из готовых ответов, без модели")
    args = ap.parse_args()
    args.seeds = [int(s) for s in args.seeds.split(",")]
    sys.stdout.reconfigure(encoding="utf-8")
    os.makedirs(args.out, exist_ok=True)
    world = mm.World()
    CL = json.load(open(CLUSTERS, encoding=ENC))
    hints = json.load(open(HINTS, encoding=ENC))
    if args.mask_only:
        do_masks(args, world, CL, hints)
    elif args.assemble:
        do_assemble(args, world, CL, hints)
    else:
        do_render(args, world, CL, hints)


if __name__ == "__main__":
    main()
