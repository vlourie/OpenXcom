"""Маски MCD/LOFT против классической графики (план пилота 2, раздел 4.1).

Окна и двери фасада с привязками (alt, die - по цепочке) и всеми кадрами петли. Видимый проём классики
= объём стены (envelope) минус силуэт кадра. Сравнение с механическим open: IoU проёмов, сдвиг центров
(пикс x4), доля open, закрашенная классикой, доля solid без рисунка, доля силуэта вне объёма.
Выход: census/maps/pilot2/masks/mask_vs_classic.png и .json.

    py -3.13 tools/hdart/mask_vs_classic.py
"""
import sys, json
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
import geom_mask as gm
sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[2]
SAVE = ROOT / "census" / "maps" / "pilot2" / "refs" / "facade" / "site.sav"
g = gm.Geom(SAVE)
start = [("URBAN", r) for r in (67, 68, 62, 27, 28, 65, 66)]
seen, todo = [], list(start)
while todo:
    s, r = todo.pop(0)
    if (s, r) in seen:
        continue
    seen.append((s, r))
    rec = g.record(s, r)
    for k in ("alt", "die"):
        v = rec.get(k)
        if v and v > 0 and (s, v) not in seen:
            todo.append((s, v))


def centre(m):
    ys, xs = np.nonzero(m)
    return (xs.mean(), ys.mean()) if len(xs) else None


rows, tiles = [], []
for s, r in seen:
    mk = gm.masks_for(g, s, r)
    rec = mk["rec"]
    env, op, sol = mk["envelope"], mk["open"], mk["solid"]
    wall = rec["type"] in (1, 2)
    for f, fr in mk["frames"].items():
        sil = fr["sil"]
        hole = env & ~sil if wall else np.zeros_like(sil)
        # дверь НЛО: кадры петли дальше 0 механически пропускаются целиком - проём = вся её сплошная часть
        mech = op.copy()
        if rec["ufo_door"] and f != rec["frames"][0]:
            mech = env.copy()
        c1, c2 = centre(hole), centre(mech)
        d = (np.hypot(c1[0] - c2[0], c1[1] - c2[1]) if c1 and c2 else None)
        # разложение сдвига центров точно: hole = mech - A + B, A - закрашено классикой в механическом проёме
        # (косяки, переплёт, перемычка), B - прозрачное классики вне него; d = (|B|(cB-cM) - |A|(cA-cM)) / |hole|
        A, B = mech & sil, hole & ~mech
        split = None
        if c1 and c2 and hole.any():
            cm = np.array(c2)
            fa = -(A.sum() * (np.array(centre(A)) - cm)) / hole.sum() if A.any() else np.zeros(2)
            fb = (B.sum() * (np.array(centre(B)) - cm)) / hole.sum() if B.any() else np.zeros(2)
            split = dict(shift_xy=[round(float(c1[0] - c2[0]), 2), round(float(c1[1] - c2[1]), 2)],
                         from_painted_in_open=[round(float(v), 2) for v in fa],
                         from_clear_outside_open=[round(float(v), 2) for v in fb],
                         painted_left_right=[int((A[:, :int(cm[0])]).sum()), int((A[:, int(cm[0]):]).sum())],
                         painted_up_down=[int((A[:int(cm[1])]).sum()), int((A[int(cm[1]):]).sum())],
                         clear_outside_px=int(B.sum()))
        # слои LOFT без единого сплошного вокселя: механический проём на всю ширину стены (косяков в LOFT нет)
        empty_z = [z for z in range(24) if not g.voxels(rec)[z].any()]
        row = dict(rec="%s#%d" % (s, r), frame=f, type=rec["type"], door=rec["door"], ufo=rec["ufo_door"],
                   alt=rec["alt"], die=rec["die"], stop_los=rec["stop_los"],
                   hole_px=int(hole.sum()), mech_open_px=int(mech.sum()),
                   iou_open=round(gm.iou(hole, mech), 3) if (hole.any() or mech.any()) else None,
                   centre_shift_x4=None if d is None else round(float(d), 1),
                   open_painted=round(float((mech & sil).sum() / max(1, mech.sum())), 3),
                   solid_unpainted=round(float((sol & ~sil).sum() / max(1, sol.sum())), 3),
                   sil_outside_env=round(float((sil & ~env).sum() / max(1, sil.sum())), 3) if wall else None,
                   shift_split=split, loft_empty_z=("%d..%d" % (empty_z[0], empty_z[-1]) if empty_z else None))
        rows.append(row)
        # лист: классика, зелёное - механический проём, синее - видимый проём классики, белое - их общее
        idx, pal = fr["idx"], fr["pal"]
        img = np.where(gm.up(idx > 0)[..., None], gm.up_rgb(pal[idx].astype(float)), np.full((160, 128, 3), 58.0))
        img = img * 0.5
        img[mech & ~hole] = (40, 230, 90)
        img[hole & ~mech] = (60, 120, 255)
        img[hole & mech] = (240, 240, 240)
        ring = sol & ~np.roll(sol, 1, 0) | sol & ~np.roll(sol, -1, 0) | sol & ~np.roll(sol, 1, 1) | sol & ~np.roll(sol, -1, 1)
        img[ring] = (255, 60, 60)
        im = Image.fromarray(img.clip(0, 255).astype(np.uint8)).resize((256, 320), Image.NEAREST)
        ImageDraw.Draw(im).text((3, 3), "%s#%d f%d" % (s, r, f), fill=(255, 255, 0))
        ImageDraw.Draw(im).text((3, 16), "IoU %s  d %s" % (row["iou_open"], row["centre_shift_x4"]), fill=(255, 255, 0))
        tiles.append(im)
for r in rows:
    print(r)
cols = 6
sheet = Image.new("RGB", (cols * 260, ((len(tiles) + cols - 1) // cols) * 324), (20, 20, 24))
for i, t in enumerate(tiles):
    sheet.paste(t, ((i % cols) * 260, (i // cols) * 324))
out = ROOT / "census" / "maps" / "pilot2" / "masks"
sheet.save(out / "mask_vs_classic.png")
(out / "mask_vs_classic.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8-sig")
print("лист", out / "mask_vs_classic.png", sheet.size)
