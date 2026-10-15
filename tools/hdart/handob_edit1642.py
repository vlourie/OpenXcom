#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""HANDOB 1642: проба «ракурс и материалы» - одна правка Edit-2511 по готовому рисунку (задание edit_plan/TASK.md).

Вход - полноразмерный очищенный ответ Codex (cg0), поставленный ТЕМ ЖЕ подобием cand_sim (fit4.json, масштаб
0.5009, поворот +6.2°, перенос 11.54, 8.58 базы) на холст 64 пикселя на пиксель базы. 64 = 32/0.5009 - это 1:1
к пикселям ответа, поэтому детали не теряются; 128x160 обратно не увеличивается (специалист 07.10). Холст кадра
2048x2560, во вход идёт вырез CROP базы - 1216x960, около 1.2 Мп; поле до рамки кандидата 2 базы слева, справа и снизу, 3 сверху. Подложка - фон самого ответа (3,194,2):
очищенный край кладётся на тот же фон, вход - это ответ Codex без его поля; блики стали серые и на зелёном не
съедаются матированием (R-089). Цвет назван в промпте и сверяется в ответе (R-157). Меток на входе нет (R-204).

Ответ возвращается в кадр 128x160 обратным целым преобразованием: вырез на своё место холста x64, матирование по
фону ответа (handob_cand1642.matte), премультиплицированное среднее 16x16. Нового подобия нет.

prep и fit модель не грузят (torch импортируется только в render), поэтому идут с GPUQ_BYPASS=1 (R-127):
    GPUQ_BYPASS=1 py -3.13 tools/hdart/handob_edit1642.py prep   вход, промпт, контроль обратного пути
    py -3.13 tools/gpuq.py add --name handob_edit1642 --prio 1 --cwd E:/OpenXCom -- \
        E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/handob_edit1642.py render
    GPUQ_BYPASS=1 py -3.13 tools/hdart/handob_edit1642.py fit    кадр 128x160, меры и лист
render - ТОЛЬКО по разрешению Vitali: одна попытка, один сид, Edit-2511 без LoRA и без Lightning, 40 шагов, cfg 4,
память в две фазы weapons_probe5.two_phase (R-213), модель по папке снимка (R-207).
Выход art/items/weapons100-v1/grip_pilot/tommy1642/edit_plan/: input.png, prompt.json, prep.json, control_1642.png,
raw.png, 1642.png, fit.json, sheet_*.png."""
import os

os.environ["HF_HUB_OFFLINE"] = "1"      # до импорта diffusers (R-145, R-207)

import argparse                         # noqa: E402
import hashlib                          # noqa: E402
import json                             # noqa: E402
import math                             # noqa: E402
import sys                              # noqa: E402
import time                             # noqa: E402

import numpy as np                      # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import battle_view as bv                # noqa: E402
import handob_cand1642 as hcd           # noqa: E402

ENC = "utf-8-sig"
OUT = os.path.join(hcd.SRC, "edit_plan")
K = 64                                  # пикселей на пиксель базы = 1:1 к ответу Codex
CROP = (9, 11, 28, 26)                # вырез входа в базе: x0, y0, x1, y1 (рамка кандидата x 11..25.75, y 14.25..24)
SEED = 1642
FULL = {"steps": 40, "cfg": 4.0, "lora": None, "lightning": False}
CAND_SHA = "0552b7f2a76ab33d75cac5a18c18b73ee2978b821e43fde3595b5624f696c07c"
ZONE_MIN_PX = 6                         # пикселей x4 детали в зоне рукояти: есть / нет
TOL_PANEL = 25.0                       # уход подложки ответа от поданной, сумма |dRGB| (R-157)
UNIT_M = 14                            # поле холста бойца, базы: сдвиг прицела выводит предмет за 32x40

PROMPT = (
    "Edit <image1>. It shows one weapon, a Thompson submachine gun, held in the hand in a battle game, on a flat "
    "pure green background RGB(3,194,2). Keep this exact weapon: the same outline, length, size and position on the "
    "picture, the muzzle at the same place on the right, the butt at the same place on the left, and the same parts "
    "in the same order and of the same size: the barrel with a small front sight and cooling fins, the receiver, a "
    "vertical wooden front grip under the barrel, a straight box magazine in front of the trigger guard, the trigger "
    "guard, a wooden pistol grip and a wooden stock. The magazine is a straight box. The front grip stays. Nothing "
    "is added and nothing is removed. "
    "Change only two things. First, the view and the volume: draw it as seen from the battle camera: {view}. Give the "
    "barrel, the receiver, the magazine and the stock solid volume consistent with that camera, with the light "
    "falling from above and from the left; do not widen or extend any surface and do not change the outline. "
    "Second, the materials: the steel is dark gunmetal grey, almost black, with fine highlights along the edges and "
    "a subtle machined texture; the wooden parts are dark brown walnut with readable wood grain, not red and not "
    "orange. "
    "Keep the same flat pure green background RGB(3,194,2) everywhere around the weapon, no shadow, no floor, no "
    "hands, no text.")
NEGATIVE = ("red wood, orange wood, bright wood, light grey steel, silver steel, chrome, drum magazine, round "
            "magazine, second magazine, missing front grip, extra parts, scope, bayonet, sling, hands, fingers, arm, "
            "soldier, text, watermark, frame, border, background gradient, white background, grey background, "
            "shadow on the ground, floor, blurry, pixel art, pixelated, jagged edges, " +
            bv.prompt_block("hand_item")["negative"])


def sha(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def load_fit():
    with open(os.path.join(hcd.SRC, "fit4", "fit4.json"), encoding=ENC) as f:
        fit = json.load(f)
    sim = fit["Codex"]["similarity"]
    a = sim["scale"] * complex(math.cos(math.radians(sim["rotation_deg"])), math.sin(math.radians(sim["rotation_deg"])))
    return fit["Codex"]["raw"], sim, a, complex(*sim["shift_base"])


def targets():
    with open(os.path.join(hcd.SRC, "plan.json"), encoding=ENC) as f:
        plan = json.load(f)
    with open(os.path.join(hcd.PILOT, "target_zones_rev2.json"), encoding=ENC) as f:
        rev = json.load(f)["frames"]["STR_TOMMYGUN.1642"]
    t = dict(plan["targets_x4"])
    t["front"] = rev["support"][0]
    return t, {"grip": t["grip"], "front": t["front"]}, plan["butt_base"]


def crop_px():
    x0, y0, x1, y1 = CROP
    return x0 * K, y0 * K, x1 * K, y1 * K


def box_reduce(rgb, alpha, f):
    """Премультиплицированное среднее блоками f x f -> RGBA float 0..255."""
    H, W = alpha.shape
    pm = rgb * alpha[..., None]
    A = alpha.reshape(H // f, f, W // f, f).mean((1, 3))
    P = pm.reshape(H // f, f, W // f, f, 3).mean((1, 3))
    out = np.where(A[..., None] > 1e-4, P / np.maximum(A[..., None], 1e-4), 0)
    return np.dstack([np.clip(out, 0, 255), np.clip(A * 255, 0, 255)])


def back_to_frame(crop_rgb):
    """Вырез x64 (RGB float) -> кадр 128x160 RGBA: на своё место холста 2048x2560 с фоном выреза, матирование,
    среднее 16x16. Возвращает (кадр, альфа выреза, отчёт матирования, фон выреза)."""
    bg = hcd.background(crop_rgb)
    full = np.zeros((40 * K, 32 * K, 3)) + bg
    X0, Y0, X1, Y1 = crop_px()
    full[Y0:Y1, X0:X1] = crop_rgb
    clean, alpha, mrep = hcd.matte(full, bg)
    frame = box_reduce(clean, alpha, K // 4)
    return frame, alpha[Y0:Y1, X0:X1], mrep, bg


def cut_check(alpha_crop):
    """Ничего не обрезано: непрозрачное у края выреза (полоса 4 пикселя)."""
    b = 4
    edge = np.zeros(alpha_crop.shape, bool)
    edge[:b] = edge[-b:] = True
    edge[:, :b] = edge[:, -b:] = True
    return int(((alpha_crop > 0.5) & edge).sum())


def iou(a, b):
    a, b = a[..., 3] > 127, b[..., 3] > 127
    return round(float((a & b).sum()) / max(1, int((a | b).sum())), 3)


def zone_fill(img, z):
    return round(float((img[z[1]:z[3] + 1, z[0]:z[2] + 1, 3] > 127).mean()), 3)


def wood_dark(img):
    """Дерево любого тона от красного до тёмного орехового: тёплое против серой стали."""
    r, g, b = img[..., 0], img[..., 1], img[..., 2]
    return (img[..., 3] > 127) & (r > g + 10) & (r > b + 8)


def frame_measures(img, t, zones, butt, cand):
    rep = hcd.measures(img, t, butt, zones)
    rep["iou_with_cand_sim_diag"] = iou(img, cand)
    w = wood_dark(img)
    for name, z in zones.items():
        rep["%s_zone_fill_opaque" % name] = zone_fill(img, z)
        rep["%s_zone_opaque_px" % name] = int((img[z[1]:z[3] + 1, z[0]:z[2] + 1, 3] > 127).sum())
        rep["%s_zone_fill_cand_sim" % name] = zone_fill(cand, z)
        rep["%s_zone_wood_px" % name] = int(w[z[1]:z[3] + 1, z[0]:z[2] + 1].sum())
    rep["wood_share_dark_rule"] = round(float(w.sum()) / max(1, int((img[..., 3] > 127).sum())), 3)
    L = hcd.lum(img[..., :3])
    op = img[..., 3] > 127
    rep["mean_luma_diag"] = round(float(L[op].mean()), 1)
    rep["dark_share_diag"] = round(float((L[op] < 40).mean()), 3)
    return rep


def verdict(m, cut_px, panel_drift):
    """Числа - отсев явного брака и замечания; принимает Vitali по сборке с бойцом в игровом масштабе (sheet_unit).
    Размер вне ±3 % - замечание (специалист 07.10: незаметная погрешность размера допустима). Дуло дальше 2 пикс x4 -
    REVIEW: видимый промах вспышки или хвата решается по сборке, а не автоматически."""
    fails, review, notes = [], [], []
    if not m["size_ok"]:
        notes.append("размер %s %% против оригинала (ориентир ±3)" % m["size_pct"])
    if not m["muzzle_ok"]:
        review.append("дуло %.2f пикс x4 от места оригинала (допуск 2) - смотреть вспышку на прицеле d0"
                      % m["muzzle_err_x4"])
    if cut_px:
        fails.append("обрезано: %d непрозрачных пикселей у края выреза" % cut_px)
    # рукоять в зоне - деталь присутствует (непрозрачное и дерево в зоне), а не заполнение как у cand_sim:
    # заполнение против непринятого кандидата - та же мера подобия контуру, что IoU (классика x4 даёт 0.11 против 0.35)
    for name in ("grip", "front"):
        if m["%s_zone_opaque_px" % name] < ZONE_MIN_PX:
            fails.append("%s: в зоне %d непрозрачных пикселей x4, нужно от %d" % (name, m["%s_zone_opaque_px" % name],
                                                                              ZONE_MIN_PX))
        elif m["%s_zone_wood_px" % name] < ZONE_MIN_PX:
            review.append("%s: дерева в зоне не найдено - смотреть лист" % name)
    if panel_drift > TOL_PANEL:
        review.append("подложка ответа ушла на %.0f от поданной (R-157)" % panel_drift)
    return ("FAIL" if fails else "REVIEW" if review else "PASS"), fails, review, notes


def unit_x4(item, case, d):
    """Кадр бойца x4 (игровой масштаб HD k=4) на холсте с полями: тело GOV_1 классикой x4, предмет 128x160 со
    сдвигом OFF прицела без обрезки и переноса (R-239), порядок слоёв routine 0. Плюс точка вспышки по рисунку
    предмета, как HdFx::noteTip (R-214): пиксели, дальние по взгляду d, в полосе классического пикселя."""
    import grip_matrix as gm
    la, ra, rot, side, _ = gm.CASES[case]
    if hs_frame(case, d) != 1642:
        raise SystemExit("%s d%d рисует кадр %d, а не 1642" % (case, d, hs_frame(case, d)))
    M = UNIT_M * 4
    H, W = 160 + 2 * M, 128 + 2 * M
    rgb, alpha = np.zeros((H, W, 3)), np.zeros((H, W))
    ox, oy = gm.OFF[case][0][d] * 4, gm.OFF[case][1][d] * 4

    def put(lay, x, y):
        a = lay[..., 3] / 255.0
        sl = (slice(y, y + lay.shape[0]), slice(x, x + lay.shape[1]))
        rgb[sl] = lay[..., :3] * a[..., None] + rgb[sl] * (1 - a[..., None])
        alpha[sl] = np.maximum(alpha[sl], a)
    L = {"la": la + d, "ra": ra + d, "lg": 16 + d, "to": 32 + d}
    for n in gm.order(d, case.endswith("AIM"), case in gm.TWO_H):
        if n in L:
            put(hcd.up_idx(gm.gov(L[n]), gm.gpal), M, M)
        elif n == ("iR" if side == "R" else "iL"):
            put(item, M + ox, M + oy)
    dx, dy = (0, 1, 1, 1, 0, -1, -1, -1)[d], (-1, -1, 0, 1, 1, 1, 0, -1)[d]
    sx, sy = dx - dy, (dx + dy) * 0.5
    ys, xs = np.nonzero(item[..., 3] > 127)
    p = xs * sx + ys * sy
    sel = p >= p.max() - 3.0
    tip = (float(xs[sel].mean()) + 0.5 + M + ox, float(ys[sel].mean()) + 0.5 + M + oy)
    return np.dstack([rgb, alpha * 255]), tip


def hs_frame(case, d):
    import grip_matrix as gm
    return 1640 + (d + gm.CASES[case][2]) % 8


def unit_cell(item, case, d, scale, font, title, tip_mark):
    u, tip = unit_x4(item, case, d)
    im = hcd.on_floor(u, scale)
    if tip_mark:
        dr = ImageDraw.Draw(im)
        x, y = tip[0] * scale, tip[1] * scale
        r = 4 * scale
        dr.ellipse([x - r, y - r, x + r, y + r], outline=(255, 60, 255), width=max(1, scale))
    return hcd.titled(im, title, font)


def floor_tile(img, scale):
    return hcd.on_floor(img, scale)


def do_prep():
    raw_path, sim, a, b = load_fit()
    if sha(os.path.join(hcd.OUT, "1642.png")) != CAND_SHA:
        raise SystemExit("cand_sim/1642.png изменён - контроль заморожен")
    t, zones, butt = targets()
    raw = np.asarray(Image.open(raw_path).convert("RGB")).astype(np.float64)
    bg = hcd.background(raw)
    clean, alpha, mrep = hcd.matte(raw, bg)
    big = hcd.place(clean, alpha, a, b, hcd.S_ANS, hcd.PAD_ANS, out_k=K)       # 2048x2560 RGBA, 1:1 к ответу
    X0, Y0, X1, Y1 = crop_px()
    al = big[..., 3] / 255.0
    outside = float(al.sum() - al[Y0:Y1, X0:X1].sum())
    if outside > 1.0:
        raise SystemExit("предмет выходит за вырез CROP: %.1f пикселей альфы снаружи" % outside)
    comp = big[..., :3] * al[..., None] + bg * (1 - al[..., None])
    inp = np.clip(np.round(comp[Y0:Y1, X0:X1]), 0, 255).astype(np.uint8)
    os.makedirs(OUT, exist_ok=True)
    inp_path = os.path.join(OUT, "input.png")
    Image.fromarray(inp).save(inp_path)
    # контроль обратного пути: сам вход -> кадр 128x160 обязан дать cand_sim
    cand = hcd.load_rgba(os.path.join(hcd.OUT, "1642.png"))
    back, al_c, mrep_b, bg_b = back_to_frame(inp.astype(np.float64))
    back8 = np.clip(np.round(back), 0, 255).astype(np.uint8)
    Image.fromarray(back8, "RGBA").save(os.path.join(OUT, "control_1642.png"))
    m = frame_measures(back8.astype(np.float64), t, zones, butt, cand)
    da = np.abs(back8[..., 3].astype(int) - cand[..., 3])
    both = (back8[..., 3] > 127) & (cand[..., 3] > 127)
    drgb = np.abs(back8[..., :3].astype(int) - cand[..., :3]).sum(2)[both]
    ctl = {"size_pct": m["size_pct"], "muzzle_err_x4": m["muzzle_err_x4"], "iou_with_cand_sim": m["iou_with_cand_sim_diag"],
           "alpha_absdiff_max": int(da.max()), "alpha_absdiff_mean": round(float(da.mean()), 3),
           "rgb_sumabs_mean_opaque": round(float(drgb.mean()), 2), "rgb_sumabs_p99_opaque": float(np.percentile(drgb, 99)),
           "cut_px": cut_check(al_c), "background_back": [round(float(v), 1) for v in bg_b]}
    prompt = PROMPT.format(view=bv.prompt_block("hand_item")["positive"])
    with open(os.path.join(OUT, "prompt.json"), "w", encoding=ENC) as f:
        json.dump({"prompt": prompt, "negative": NEGATIVE, "seed": SEED, "full": FULL, "width": int(inp.shape[1]),
                   "height": int(inp.shape[0])}, f, ensure_ascii=False, indent=1)
    rep = {"raw": raw_path, "similarity": sim, "k": K, "crop_base": CROP, "input": inp_path.replace("\\", "/"),
           "input_sha256": sha(inp_path), "input_size": [int(inp.shape[1]), int(inp.shape[0])],
           "input_mp": round(inp.shape[0] * inp.shape[1] / 1e6, 2), "background": [round(float(v), 1) for v in bg],
           "matte_answer": mrep, "alpha_outside_crop": round(outside, 2), "control_back_to_frame": ctl,
           "cand_sim_sha256": CAND_SHA}
    with open(os.path.join(OUT, "prep.json"), "w", encoding=ENC) as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)
    # лист: вход целиком | вход вблизи 1:1 | cand_sim x8 | контроль x8
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 15)
    iv = Image.fromarray(inp)
    zoom = iv.crop((560, 220, 1100, 760))
    s = hcd.row([hcd.titled(iv.resize((576, 480), Image.LANCZOS), "вход Edit-2511 %dx%d (уменьшен вдвое)" % iv.size, font),
                 hcd.titled(zoom, "вход 1:1, участок 540x540", font),
                 hcd.titled(floor_tile(cand.astype(np.float64), 4), "cand_sim 128x160 x4", font),
                 hcd.titled(floor_tile(back8.astype(np.float64), 4), "вход -> кадр: дуло %.1f, размер %s" %
                            (ctl["muzzle_err_x4"], ctl["size_pct"]), font)])
    s.save(os.path.join(OUT, "sheet_input.png"))
    print(json.dumps(rep, ensure_ascii=False, indent=1))


def do_render(a):
    import gen_hd
    import item_photo as ip
    import photo_ui as pu
    import torch
    import weapons_probe5 as p5
    with open(os.path.join(OUT, "prep.json"), encoding=ENC) as f:
        prep = json.load(f)
    inp_path = os.path.join(OUT, "input.png")
    if sha(inp_path) != prep["input_sha256"]:
        raise SystemExit("input.png изменён после prep")
    with open(os.path.join(OUT, "prompt.json"), encoding=ENC) as f:
        pr = json.load(f)
    raw_path = os.path.join(OUT, "raw.png")
    if os.path.exists(raw_path) and not a.force:
        raise SystemExit("raw.png уже есть - одна попытка; повтор только с --force по слову Vitali")
    models = a.models or gen_hd.DEFAULT_MODELS_DIR
    ip.edit_model_check(models)
    pu.MODEL = os.path.join(models, "hub", "models--Qwen--Qwen-Image-Edit-2511", "snapshots", ip.EDIT_MODEL_REV)
    img = Image.open(inp_path).convert("RGB")
    t0 = time.time()
    pipe, embeds = p5.two_phase(models, [(img, pr["prompt"], pr["negative"])])
    loaded = pipe.get_list_adapters() if hasattr(pipe, "get_list_adapters") else "?"
    print("LoRA в модели: %s" % (loaded or "нет"), flush=True)
    if loaded:
        raise SystemExit("LoRA загружена - не тот генератор (ни Lightning, ни другой)")
    dev = torch.device("cuda")
    pe, pm, npe, npm = (x.to(dev) for x in embeds[0])
    g = torch.Generator("cuda").manual_seed(pr["seed"])
    with torch.no_grad():
        out = pipe(image=[img], prompt=None, prompt_embeds=pe, prompt_embeds_mask=pm,
                   negative_prompt_embeds=npe, negative_prompt_embeds_mask=npm, true_cfg_scale=FULL["cfg"],
                   num_inference_steps=FULL["steps"], height=img.height, width=img.width,
                   generator=g).images[0].convert("RGB")
    if p5.gpu_mem("кадр") > 0.5:
        raise SystemExit("ушло в shared - стоп, ответ не сохранён")
    out.save(raw_path)
    meta = {"seed": pr["seed"], "full": FULL, "model_rev": ip.EDIT_MODEL_REV, "input_sha256": prep["input_sha256"],
            "seconds": round(time.time() - t0), "created": time.strftime("%Y-%m-%dT%H:%M:%S")}
    with open(os.path.join(OUT, "render_meta.json"), "w", encoding=ENC) as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    print("готово: %s, %d с" % (raw_path, meta["seconds"]), flush=True)


def do_fit():
    import grip_matrix as gm
    raw_path = os.path.join(OUT, "raw.png")
    if not os.path.exists(raw_path):
        raise SystemExit("нет raw.png - проба не запускалась")
    t, zones, butt = targets()
    cand = hcd.load_rgba(os.path.join(hcd.OUT, "1642.png"))
    raw = np.asarray(Image.open(raw_path).convert("RGB")).astype(np.float64)
    X0, Y0, X1, Y1 = crop_px()
    if raw.shape[:2] != (Y1 - Y0, X1 - X0):
        raise SystemExit("размер ответа %s, ждал %dx%d" % (raw.shape[:2], X1 - X0, Y1 - Y0))
    frame, al_c, mrep, bg = back_to_frame(raw)
    f8 = np.clip(np.round(frame), 0, 255).astype(np.uint8)
    Image.fromarray(f8, "RGBA").save(os.path.join(OUT, "1642.png"))
    img = f8.astype(np.float64)
    m = frame_measures(img, t, zones, butt, cand)
    drift = float(np.abs(bg - np.array([3.0, 194.0, 2.0])).sum())
    cut = cut_check(al_c)
    v, fails, review, notes = verdict(m, cut, drift)
    rep = {"verdict": v, "fails": fails, "review": review, "notes": notes, "measures": m, "cut_px": cut,
           "panel_answer": [round(float(x), 1) for x in bg], "panel_drift": round(drift, 1), "matte": mrep,
           "hands": {"cand_sim": hcd.hands_visible(cand, gm, zones), "probe": hcd.hands_visible(img, gm, zones)},
           "note": "принимает Vitali по sheet_unit (боец в игровом масштабе): узнаваемость, ствол, конструкция; "
                   "хват, сквозь тело, вспышка; ракурс, материалы, читаемость. Размер и дуло - замечания, "
                   "IoU с cand_sim, яркость и доля тёмного - диагностика"}
    with open(os.path.join(OUT, "fit.json"), "w", encoding=ENC) as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 15)
    cls = hcd.up_idx(gm.hob(1642), gm.hpal)
    nb = [hcd.titled(floor_tile(hcd.up_idx(gm.hob(f), gm.hpal), 2), "классика %d x8" % f, font) for f in (1643, 1644)]
    s1 = hcd.row([hcd.titled(floor_tile(cls, 2), "классика 1642 x8", font),
                  hcd.titled(floor_tile(cand, 2), "cand_sim x8", font),
                  hcd.titled(floor_tile(img, 2), "проба x8: %s" % v, font)] + nb)
    s1.save(os.path.join(OUT, "sheet_view.png"))
    rv = Image.fromarray(raw.astype(np.uint8))
    s2 = hcd.row([hcd.titled(Image.open(os.path.join(OUT, "input.png")).resize((576, 480), Image.LANCZOS), "вход", font),
                  hcd.titled(rv.resize((576, 480), Image.LANCZOS), "ответ Edit-2511", font)])
    s2.save(os.path.join(OUT, "sheet_raw.png"))
    s3 = hcd.row([hcd.titled(floor_tile(img, 1), "1:1", font), hcd.titled(floor_tile(img, 2), "x2", font),
                  hcd.titled(floor_tile(hcd.compose_unit(img, gm), 2), "TWO_STAND d2 x2", font),
                  hcd.titled(floor_tile(hcd.compose_unit(cand, gm), 2), "cand_sim TWO_STAND d2 x2", font)])
    s3.save(os.path.join(OUT, "sheet_floor.png"))
    # главный лист: боец со стволом, стоя (TWO_STAND d2) и в прицеле (TWO_AIM d0, тот же кадр 1642, сдвиг 8,-6),
    # 1:1 - игровой масштаб k=4, x2 - разбор; пурпурный круг - точка вспышки по рисунку (noteTip)
    rows = []
    for item, name in ((cls, "классика"), (cand, "cand_sim"), (img, "проба")):
        rows.append(hcd.row([unit_cell(item, "TWO_STAND", 2, 1, font, "%s стоя d2 1:1" % name, False),
                             unit_cell(item, "TWO_AIM", 0, 1, font, "%s прицел d0 1:1" % name, False),
                             unit_cell(item, "TWO_STAND", 2, 2, font, "стоя d2 x2", False),
                             unit_cell(item, "TWO_AIM", 0, 2, font, "прицел d0 x2, вспышка", True)]))
    hcd.col(rows).save(os.path.join(OUT, "sheet_unit.png"))
    print(json.dumps(rep, ensure_ascii=False, indent=1))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    os.chdir(hcd.ROOT)
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["prep", "render", "fit"])
    ap.add_argument("--models")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    {"prep": lambda: do_prep(), "render": lambda: do_render(a), "fit": lambda: do_fit()}[a.cmd]()


if __name__ == "__main__":
    main()
