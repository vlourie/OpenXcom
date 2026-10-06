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
        row = dict(rec="%s#%d" % (s, r), frame=f, type=rec["type"], door=rec["door"], ufo=rec["ufo_door"],
                   alt=rec["alt"], die=rec["die"], stop_los=rec["stop_los"],
                   hole_px=int(hole.sum()), mech_open_px=int(mech.sum()),
                   iou_open=round(gm.iou(hole, mech), 3) if (hole.any() or mech.any()) else None,
                   centre_shift_x4=None if d is None else round(float(d), 1),
                   open_painted=round(float((mech & sil).sum() / max(1, mech.sum())), 3),
                   solid_unpainted=round(float((sol & ~sil).sum() / max(1, sol.sum())), 3),
                   sil_outside_env=round(float((sil & ~env).sum() / max(1, sil.sum())), 3) if wall else None)
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
