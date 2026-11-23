"""Без карты: сколько реально разных тел у каждой расы paper doll. Ниже шеи, по классике.
Тела одной формы: силуэт почти совпал и светотень та же (та же фигура, другая кожа).
Контроль: UBERGAL должен дать одну основную форму. Лист: представитель каждой формы."""
import json
import os
import re
import sys
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import build_pack as bp
import doll_b2_render as db

F = db.sprite_files()
PAL = db.game_palette()
SIL_FRAC = 0.03     # силуэт: не больше 3% тела
AGREE = 0.85        # корреляция светлоты по общим пикселям
LUM = np.asarray(PAL, np.float32)[:, :3] @ np.array([0.299, 0.587, 0.114], np.float32)
LAB = bp._rgb_to_lab(np.asarray(PAL, np.float32)[:, :3][None] / 255.0)[0]
TORSO_FRAC = 0.05   # торс: своего не больше 5% его пикселей
OUT = sys.argv[1] if len(sys.argv) > 1 else "census"
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "art", "doll", "pipe_pilot")


def agree(a, b):
    """Светотень одна и та же: корреляция светлоты по общим пикселям. Не зависит от цвета кожи.
    Таблица индексов не годится: у F5 и M42 UBERGAL она объясняет только 81%, хотя тело одно."""
    both = (a > 0) & (b > 0)
    if both.sum() < 10:
        return 0.0
    la, lb = LUM[a[both]], LUM[b[both]]
    if la.std() == 0 or lb.std() == 0:
        return 0.0
    return float(np.corrcoef(la, lb)[0, 1])


races = defaultdict(lambda: defaultdict(dict))
for k in F:
    m = re.match(r"^(\w+?)__(\d+)__(.+)$", k)
    if m:
        races[m.group(1)][int(m.group(2))][m.group(3)] = k

def own_torso(a, b):
    """Пикселей торса, которых не объясняет кожа: таблица a -> самый частый b, расстояние по Lab."""
    both = (a > 0) & (b > 0)
    u, c = np.unique(a[both].astype(np.int64) * 256 + b[both], return_counts=True)
    t, best = np.arange(256), np.zeros(256, np.int64)
    for x, n in zip(u.tolist(), c.tolist()):
        if n > best[x // 256]:
            best[x // 256], t[x // 256] = n, x % 256
    return int(((np.linalg.norm(LAB[t[a]] - LAB[b], axis=-1) > 14) & both).sum())


def torso_groups(imgs, names):
    """Форма по силуэту и корреляции не отличает кубики от гладкого живота (FHUMAN: 124 тела, 5 торсов).
    Делим форму по самому торсу: 36 строк под шеей, лучшая из двух сторон таблицы."""
    names = [n for n in names if "CAMO" not in n]
    if len(names) < 2:
        return [(n, [n]) for n in names]
    tor = [imgs[n][3:39] for n in names]
    limit = TORSO_FRAC * int((tor[0] > 0).sum())
    s = np.zeros((len(names), len(names)), np.int32)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            s[i, j] = s[j, i] = min(own_torso(tor[i], tor[j]), own_torso(tor[j], tor[i]))
    left, out = set(range(len(names))), []
    while left:
        c = max(left, key=lambda i: sum(s[i, j] <= limit for j in left))
        m = [j for j in left if s[c, j] <= limit]
        out.append((names[c], sorted(names[j] for j in m)))
        left -= set(m)
    return sorted(out, key=lambda g: -len(g[1]))


result = {}
tiles = []
for race in sorted(races):
    layers = races[race]
    nude = {}
    for l in layers:
        for n, key in layers[l].items():
            if "NUDE" in n:
                nude[n] = key
    if len(nude) < 4:
        continue
    bottoms = []
    for l in layers:
        for n, key in layers[l].items():
            if n.startswith("HEAD"):
                try:
                    ys = np.nonzero(db.load_indices(F[key]))[0]
                except Exception:
                    continue
                if len(ys):
                    bottoms.append(int(ys.max()))
    row = int(np.median(bottoms)) + 3 if bottoms else 63
    imgs = {}
    for n, key in nude.items():
        try:
            imgs[n] = db.load_indices(F[key])[row:]
        except Exception as e:
            print("  пропущен", race, n, str(e)[:80])
    groups = {}
    for n, im in imgs.items():
        groups.setdefault(im.tobytes(), []).append(n)
    uniq = sorted(groups.values(), key=lambda v: -len(v))
    shapes = []     # {"rep": имя, "members": [...], "skins": {байты: [...]}, "diff": {...}}
    for names in uniq:
        im = imgs[names[0]]
        area = max(int((im > 0).sum()), 1)
        for s in shapes:
            rp = imgs[s["rep"]]
            if int(((im > 0) != (rp > 0)).sum()) <= SIL_FRAC * area:
                ag = agree(im, rp)
                if ag >= AGREE:
                    s["members"] += names
                    for n in names:
                        s["agree"][n] = ag
                        s["sil"][n] = int(((im > 0) != (rp > 0)).sum())
                    break
        else:
            shapes.append({"rep": names[0], "members": list(names), "agree": {n: 1.0 for n in names},
                           "sil": {n: 0 for n in names}, "copies": len(names)})
    shapes.sort(key=lambda s: -len(s["members"]))
    result[race] = {"тел": len(imgs), "строка шеи": row, "точно разных ниже шеи": len(uniq),
                    "форм": len(shapes), "точных копий самой частой": len(uniq[0]) if uniq else 0,
                    "формы": [{"пример": s["rep"], "тел": len(s["members"]), "имена": sorted(s["members"]),
                               "минимум совпадения": round(min(s["agree"].values()), 3)} for s in shapes]}
    print("%-10s тел %3d  шея %3d  точно разных %3d  форм %3d  размер форм: %s" % (
        race, len(imgs), row, len(uniq), len(shapes), [len(s["members"]) for s in shapes][:14]), flush=True)
    for s in shapes[:6]:
        print("    %-14s x%-3d NUDECAMO %d  мин. корреляция %.2f" % (
            s["rep"], len(s["members"]), sum("CAMO" in n for n in s["members"]), min(s["agree"].values())), flush=True)
    torsos = [g for s in shapes for g in torso_groups(imgs, s["members"])]
    torsos.sort(key=lambda g: -len(g[1]))
    result[race]["торсов"] = len(torsos)
    result[race]["торсы"] = [{"основа": r, "тел": len(m), "имена": m} for r, m in torsos]
    print("    торсов %d: %s" % (len(torsos), [(r.replace("_NUDE", ""), len(m)) for r, m in torsos][:14]), flush=True)
    for r, m in torsos[:12]:
        tiles.append((race, r, len(m), db.load_indices(F[nude[r]])))

json.dump(result, open(os.path.join(ROOT, OUT + ".json"), "w", encoding="utf-8-sig"), ensure_ascii=False, indent=1)
W, H = 100, 165
Z = 2
FONT = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 13)
PER = 12
rows = (len(tiles) + PER - 1) // PER
sheet = Image.new("RGB", (PER * (W * Z + 4), rows * (H * Z + 22)), (15, 15, 18))
d = ImageDraw.Draw(sheet)
for i, (race, n, c, idx) in enumerate(tiles):
    rgba = db.to_rgba(idx, PAL)
    im = Image.new("RGBA", (idx.shape[1], idx.shape[0]), (112, 112, 118, 255))
    im.alpha_composite(Image.fromarray(rgba, "RGBA"))
    ys, xs = np.nonzero(idx)
    cx = (int(xs.min()) + int(xs.max())) // 2
    x0 = max(cx - W // 2, 0)
    crop = im.crop((x0, 0, x0 + W, H)).convert("RGB").resize((W * Z, H * Z), Image.NEAREST)
    x, y = (i % PER) * (W * Z + 4), (i // PER) * (H * Z + 22)
    d.text((x + 2, y + 2), "%s %s x%d" % (race, n.replace("_NUDE", ""), c), fill=(255, 230, 0), font=FONT)
    sheet.paste(crop, (x, y + 22))
fn = os.path.join(ROOT, OUT + ".png")
sheet.save(fn)
print(fn, sheet.size)
