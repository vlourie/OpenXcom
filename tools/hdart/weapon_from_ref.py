#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Готовый эталон оружия -> кадр пака k=4 обычной обработкой, без генерации и без деформации (указание 05.10).

Эталон (картинка Vitali) снимается с фона (weapon_fit.matte плюс заливка ложных дыр в тёмном теле), чистится от
цвета фона на кромке (photo_base.decontaminate), равномерно масштабируется к габариту оригинала (среднее
геометрическое отношений ширины и высоты - пропорции эталона сохраняются, TPS и подгонки нет) и ставится центром
на центр габарита оригинала в кадре 128x192. Альфа - эталона, а не силуэта оригинала; цвет - эталона, тон не
подгоняется. Итог срезается только по клеткам предмета (grid_rect), срезанное пишется в отчёт.

Для проверки weapon_fit.py --synth пишет meta/<тип>.json: raw - эталон на холсте кропа x16 на ровной подложке
(тот же вход, что видела бы модель), file - кадр пака.
Запуск: py -3.13 tools/hdart/weapon_from_ref.py --only W-019
--scale-mul 1.0086 - ещё равномерное увеличение вокруг точки дула (столбец muzzle опознания), дуло не сдвигается.
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)

import numpy as np                      # noqa: E402
from PIL import Image                   # noqa: E402

import item_photo as ip                 # noqa: E402
import weapon_fit as wf                 # noqa: E402

ENC = "utf-8-sig"
OUT = "art/items/weapons-fromref-v1"
K, ZOOM = 4, 16
PANEL = (176, 176, 182)


def ref_matte(path):
    """Матт эталона: weapon_fit.matte, ложные дыры в тёмном теле (тёмный фон эталона) залиты, цвет кромки без фона."""
    rgb, a, bg = wf.matte(path)
    if bg is None:
        # альфа самого файла (ответ с прозрачностью): цвет уже без подложки, дыры в ней настоящие
        return rgb.astype(np.float32), a, None
    a = np.maximum(a, wf.holes_of(a > 0.5).astype(np.float32))
    rgb = ip.pb.decontaminate(rgb.astype(np.float32), a, bg)
    return rgb, a, bg


def scaled(rgb, a, tw, th):
    """Равномерный масштаб к габариту tw x th; ресайз с умножением на альфу, чтобы фон не втекал в кромку."""
    h, w = a.shape
    s = float(np.sqrt(tw / float(w) * th / float(h)))
    nw, nh = max(1, int(round(w * s))), max(1, int(round(h * s)))
    pre = np.dstack([rgb * a[..., None], a * 255.0])
    ims = [Image.fromarray(pre[..., i].astype(np.float32), "F").resize((nw, nh), Image.LANCZOS) for i in range(4)]
    arr = np.dstack([np.asarray(im) for im in ims])
    al = np.clip(arr[..., 3] / 255.0, 0, 1)
    col = arr[..., :3] / np.maximum(al, 1e-3)[..., None]
    col = np.where(al[..., None] > 1e-3, col, 0)
    return np.clip(col, 0, 255), al, s


def paste(dst_rgb, dst_a, rgb, a, x, y):
    H, W = dst_a.shape
    h, w = a.shape
    xs0, ys0, xs1, ys1 = max(0, x), max(0, y), min(W, x + w), min(H, y + h)
    lost = float(a.sum() - a[ys0 - y:ys1 - y, xs0 - x:xs1 - x].sum())
    dst_rgb[ys0:ys1, xs0:xs1] = rgb[ys0 - y:ys1 - y, xs0 - x:xs1 - x]
    dst_a[ys0:ys1, xs0:xs1] = a[ys0 - y:ys1 - y, xs0 - x:xs1 - x]
    return lost


def place(rgb, a, box, zoom, W, H, mul=1.0, muzzle="-"):
    """Эталон на холст W x H: габарит оригинала box (в пикселях базы) x zoom, центр к центру.
    mul != 1 - ещё равномерное увеличение в mul раз вокруг точки дула (она остаётся там, где была при mul 1)."""
    tw, th = (box[2] - box[0]) * zoom, (box[3] - box[1]) * zoom
    h0, w0 = a.shape
    s1 = float(np.sqrt(tw / float(w0) * th / float(h0)))
    c, al, s = scaled(rgb, a, tw * mul, th * mul)
    nh, nw = al.shape
    cx, cy = (box[0] + box[2]) * zoom / 2.0, (box[1] + box[3]) * zoom / 2.0
    x0, y0 = cx - w0 * s1 / 2.0, cy - h0 * s1 / 2.0
    anchor = None
    if mul != 1.0 and muzzle in wf.DIRS:
        dx, dy = wf.DIRS[muzzle]
        pm = wf.muzzle_point(a, dx, dy, zoom / s1)
        anchor = [round(x0 + pm[0] * s1, 2), round(y0 + pm[1] * s1, 2)]
        x, y = int(round(anchor[0] - pm[0] * s)), int(round(anchor[1] - pm[1] * s))
    else:
        x, y = int(round(cx - nw / 2.0)), int(round(cy - nh / 2.0))
    out_rgb = np.zeros((H, W, 3), np.float32)
    out_a = np.zeros((H, W), np.float32)
    lost = paste(out_rgb, out_a, c, al, x, y)
    rep = {"scale": round(s, 4), "placed_px": [nw, nh], "at": [x, y],
           "placed_dw_pct": round(100 * (nw / float(tw) - 1), 1), "placed_dh_pct": round(100 * (nh / float(th) - 1), 1),
           "lost_off_canvas_alpha": round(lost, 1)}
    if mul != 1.0:
        rep.update(scale_mul=mul, anchor=anchor or "центр габарита")
    return out_rgb, out_a, rep


def job(row, lrow, out, ref="", wide=False, mul=1.0):
    t = row["type"]
    ref = ref or (row.get("ref") or "").strip()
    if not ref or not os.path.exists(ref):
        raise SystemExit("%s: эталона нет (%s)" % (row["master"], ref))
    frame = int(lrow["frame"])
    ip.CARDS = "art/items/weapons100-v1/cards"
    full, src = ip.load_frame(t, frame)
    crop, cbox = ip.crop_job(full)
    rgb, a, bg = ref_matte(ref)
    h, w = a.shape
    m_full = np.asarray(full)[..., 3] > 0
    box = wf.bbox(m_full)
    tw, th = box[2] - box[0], box[3] - box[1]
    rep = {"ref": ref, "ref_bg": None if bg is None else [float(v) for v in bg], "ref_px": [w, h],
           "aspect_ref_vs_orig_pct": round(100 * ((w / float(h)) / (tw / float(th)) - 1), 1)}
    # сырой для проверки: эталон на холсте кропа x16 на ровной подложке
    m_crop = np.asarray(crop)[..., 3] > 0
    mz = (row.get("muzzle") or "-").strip()
    c16, a16, rep["raw_place"] = place(rgb, a, wf.bbox(m_crop), ZOOM, crop.width * ZOOM, crop.height * ZOOM, mul, mz)
    raw = c16 * a16[..., None] + np.asarray(PANEL, np.float32) * (1 - a16[..., None])
    raw_p = os.path.join(out, "raw", t + ".ref16.png")
    Image.fromarray(np.clip(raw, 0, 255).astype(np.uint8), "RGB").save(raw_p)
    raw_a = ""
    if bg is None:
        # у ответа своя альфа: проверка сырого берёт её, а не матт по подложке (светлая сталь цвета подложки, R-089)
        raw_a = os.path.join(out, "raw", t + ".ref16a.png")
        Image.fromarray(np.dstack([c16, a16 * 255.0]).clip(0, 255).astype(np.uint8), "RGBA").save(raw_a)
    # итог: кадр k=4 128x192, срез по клеткам предмета
    c4, a4, rep["place"] = place(rgb, a, box, K, full.width * K, full.height * K, mul, mz)
    cw, ch = [int(v) for v in lrow["cells"].split("x")]
    # --wide: допуск метки .wide (свой кадр плюс рамка руки после сдвига, Р-13) - метка поштучно, по решению Vitali
    gx0, gy0, gx1, gy1 = (ip.iac.wide_rect(cw, ch, full.size) if wide else ip.iac.grid_rect(cw, ch))
    keep = np.zeros_like(a4)
    keep[gy0 * K:gy1 * K, gx0 * K:gx1 * K] = 1
    rep["place"]["cut_by_cells_alpha"] = round(float((a4 * (1 - keep)).sum()), 1)
    rep["place"]["clip"] = "wide" if wide else "grid"
    a4 = a4 * keep
    rgba = np.dstack([c4, a4 * 255.0]).clip(0, 255).astype(np.uint8)
    pp = os.path.join(out, "pack", "BIGOBS.PCK", "%d.%s%s.png" % (frame, t, ".wide" if wide else ""))
    Image.fromarray(rgba, "RGBA").save(pp)
    meta = {"asset_id": t, "master": row["master"], "frame": frame, "cells": [cw, ch], "ref": ref, "src": src,
            "method": "FROM_REF: матт, равномерный масштаб, без генерации и деформации",
            "report": rep, "raw": raw_p.replace("\\", "/"), "file": pp.replace("\\", "/"),
            "raw_alpha": raw_a.replace("\\", "/"),
            "created": time.strftime("%Y-%m-%dT%H:%M:%S")}
    with open(os.path.join(out, "meta", t + ".json"), "w", encoding=ENC) as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    print("%s %s масштаб %.4f, пропорции эталона против оригинала %+.1f%%, ширина %+.1f%%, высота %+.1f%%, "
          "срезано клетками %.0f" % (row["master"], t, rep["place"]["scale"], rep["aspect_ref_vs_orig_pct"],
                                     rep["place"]["placed_dw_pct"], rep["place"]["placed_dh_pct"],
                                     rep["place"]["cut_by_cells_alpha"]), flush=True)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", required=True, help="мастера через запятую, W-019")
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--ref", default="", help="другой эталон вместо столбца ref (один предмет), например ответ генератора")
    ap.add_argument("--wide", action="store_true", help="срез по допуску .wide, файл <кадр>.<тип>.wide.png")
    ap.add_argument("--scale-mul", type=float, default=1.0,
                    help="ещё равномерное увеличение вокруг точки дула (1.008 - на 0,8%%), без растяжения по оси")
    a = ap.parse_args()
    os.chdir(ROOT)
    want = set(a.only.split(","))
    lrows = wf.list_rows()
    rows = [r for k in range(1, 6) for r in wf.batch_rows(k) if r["master"] in want]
    if not rows:
        raise SystemExit("нет строк опознания для %s" % a.only)
    for sub in ("raw", "meta", "pack/BIGOBS.PCK"):
        os.makedirs(os.path.join(a.out, sub), exist_ok=True)
    for r in rows:
        job(r, lrows[r["master"]], a.out, a.ref, a.wide, a.scale_mul)


if __name__ == "__main__":
    main()
