"""23 набора с лицами: совпадает ли меняющаяся часть (маска отличий набора) с голой куклой той же внешности.
Голая кукла - слои брони NUDE расы (layersDefinition), классика индексами в палитре боя (doll_b2_render).
Мерки на маске отличий, лучший сдвиг +-4: точное совпадение цвета и корреляция светлоты (под стеклом/жидкостью
цвет другой, а рисунок тот же). Выход nude_match.json и строка на набор."""
import json
import os
import re
import sys
import numpy as np
from PIL import Image
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, r"E:\OpenXCom\tools\hdart")
import doll_b2_render as db

D = r"E:\tmp\doll_ingame\multi_all"
CROPS = json.load(open(os.path.join(D, "crops.json"), encoding="utf-8"))
RACE = {"MAN_520": "RACE:UBERGAL", "MAN_531": "RACE:UBERGAL", "MAN_540": "RACE:UBERGAL",
        "MAN_493": "RACE:UBERGAL", "MAN_494": "RACE:UBERGAL",
        "MAN_570": "RACE:FHUMAN", "MAN_581": "RACE:FHUMAN", "MAN_590": "RACE:FHUMAN",
        "MAN_620": "STR_HYBRID_NUDE_DREAMLAND_UC", "MAN_631": "STR_HYBRID_NUDE_DREAMLAND_UC", "MAN_640": "STR_HYBRID_NUDE_DREAMLAND_UC",
        "MAN_720": "STR_LAMIA_NUDE_DREAMLAND_UC", "MAN_870": "STR_OGRE_NUDE_DREAMLAND_UC",
        "MAN_920": "RACE:GNOME", "MAN_931": "RACE:GNOME",
        "MAN_820": "STR_LOKNAR_NUDE_DREAMLAND_UC", "MAN_802": "STR_LOKNAR_NUDE_DREAMLAND_UC", "MAN_803": "STR_LOKNAR_NUDE_DREAMLAND_UC",
        "MAN_808": "STR_LOKNAR_NUDE_DREAMLAND_UC", "MAN_810": "STR_LOKNAR_NUDE_DREAMLAND_UC", "MAN_811": "STR_LOKNAR_NUDE_DREAMLAND_UC",
        "MAN_830": "STR_LOKNAR_NUDE_DREAMLAND_UC"}
arms = db.armor_layers()
files = db.sprite_files()
pal = db.game_palette()


def pick(race):
    """префикс расы -> броня с самыми короткими слоями (голая); имя брони -> как есть"""
    if race in arms or race.startswith("RACE:"):
        return race
    cand = [a for a, d in arms.items() if all(n.startswith(race + "__") for v in d.values() for n in v)]
    return min(cand, key=lambda a: max(len(v) for v in arms[a].values()))


cache = {}


def layer(n):
    if n not in cache:
        cache[n] = db.to_rgba(db.load_indices(files[n]), pal) if n in files and os.path.exists(files[n]) else None
    return cache[n]


def nude(arm, key):
    if arm.startswith("RACE:"):                 # голая из слоёв расы: тело 2, голова 10, волосы 13 (что есть)
        r = arm[5:]
        names = [n for n in ("%s__2__%s_NUDE" % (r, key), "%s__10__HEAD_%s" % (r, key), "%s__13__HAIR_%s" % (r, key))
                 if n in files]
        if not names:
            return None, []
    else:
        names = arms[arm].get(key)
    if names is None:
        return None, []
    out = np.zeros((200, 320, 4), np.uint8)
    for n in names:
        im = layer(n)
        if im is None:
            continue
        m = im[..., 3] > 0
        out[m] = im[m]
    return out, names


def lum(x):
    return x[..., :3].astype(np.float32) @ np.array([0.299, 0.587, 0.114], np.float32)


res = {}
MAIN = __name__ == "__main__"
for s in (sys.argv[1:] or sorted(RACE)) if MAIN else []:
    arm = pick(RACE[s])
    diff = np.asarray(Image.open(os.path.join(D, "diff_%s.png" % s))) > 0
    names = sorted((n for n in CROPS if re.match(r"^%s[MF]\d+\.SPK$" % s, n)), key=lambda n: (n[len(s)] != "F", int(n[len(s) + 1:-4])))
    rows = []
    for n in names:
        key = n[len(s):-4]
        cl = np.asarray(Image.open(os.path.join(D, "classic_%s.png" % n)).convert("RGBA"))
        nu, ln = nude(arm, key)
        if nu is None:
            rows.append((key, None, None, None))
            continue
        ys, xs = np.nonzero(diff & (cl[..., 3] > 0))
        best = (-1, 0, (0, 0))
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                y2, x2 = ys + dy, xs + dx
                ok = (y2 >= 0) & (y2 < 200) & (x2 >= 0) & (x2 < 320)
                a, b = cl[ys[ok], xs[ok]], nu[y2[ok], x2[ok]]
                op = b[:, 3] > 0
                if op.sum() < 20:
                    continue
                exact = float((np.all(a[:, :3] == b[:, :3], 1) & op).sum()) / len(ys)
                la, lb = lum(a[op]), lum(b[op])
                cor = float(np.corrcoef(la, lb)[0, 1]) if la.std() > 1 and lb.std() > 1 else 0.0
                cover = float(op.sum()) / len(ys)
                sc = exact + cor * cover
                if sc > best[0]:
                    best = (sc, (exact, cor, cover), (dx, dy))
        if best[0] < 0:
            rows.append((key, None, None, None))
        else:
            rows.append((key, best[1], best[2], ln))
    ok = [r for r in rows if r[1]]
    ex = np.mean([r[1][0] for r in ok]) if ok else 0
    co = np.mean([r[1][1] for r in ok]) if ok else 0
    cv = np.mean([r[1][2] for r in ok]) if ok else 0
    shifts = sorted(set(r[2] for r in ok))
    res[s] = {"armor": arm, "looks": len(names), "with_nude": len(ok), "exact": ex, "corr": co, "cover": cv,
              "shifts": shifts[:5], "rows": [(r[0], r[1], r[2]) for r in rows]}
    print("%s %-30s внешн %3d с голой %3d  точно %.2f  корр %.2f  покрытие %.2f  сдвиги %s" %
          (s, arm, len(names), len(ok), ex, co, cv, shifts[:4]), flush=True)
if MAIN:
    json.dump(res, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "nude_match.json"), "w", encoding="utf-8"), ensure_ascii=False)
