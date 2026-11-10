"""Проверка теории Vitali: картинка капсулы = общая капсула + слой куклы (голова) без перерисовки.
По индексам палитры: оригинальный PNG капсулы из мода против слоёв голой куклы расы.
- общая часть: точки, одинаковые у всех внешностей набора;
- меняющиеся точки V: на каком слое куклы они лежат (тело 2 / голова 10 / волосы 13 / нигде);
- совпадение индекса точь-в-точь и через таблицу «индекс куклы -> индекс капсулы» (затемнение палитрой)."""
import os
import sys
import glob
import numpy as np
from collections import Counter, defaultdict
from PIL import Image
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, r"E:\OpenXCom\tools\hdart")
import doll_b2_render as db

ARM = r"E:\OpenXCom\Пиратки\Dioxine_XPiratez\user\mods\Piratez\Resources\Armors"
files = db.sprite_files()
SETS = {"570": ("FHUMAN", (1, 1)), "620": ("HYBRID", (1, 0)), "870": ("OGRE", (1, 2))}
CHECK = sys.argv[1:] or ["570:F0", "620:F0", "870:F0", "870:M3"]


def idx(p):
    im = Image.open(p)
    assert im.mode == "P", (p, im.mode)
    return np.asarray(im)


def layer(name):
    return idx(files[name]) if name in files and os.path.exists(files[name]) else None


for item in (CHECK if __name__ == "__main__" else []):
    s, key = item.split(":")
    race, (dx, dy) = SETS[s]
    allp = sorted(glob.glob(os.path.join(ARM, "Body_%s" % s, "body%s_*.*" % s)))
    stack = np.stack([idx(p) for p in allp])
    common = np.all(stack == stack[0], 0)
    pod = idx(glob.glob(os.path.join(ARM, "Body_%s" % s, "body%s_%s.*" % (s, key)))[0])
    # лист: капсула | кукла (слои) | меняющиеся точки (красные) поверх капсулы, x6
    pal0 = db.game_palette()
    box = np.argwhere(~common)
    (y0, x0), (y1, x1) = box.min(0) - 4, box.max(0) + 5
    y0, x0 = max(0, y0), max(0, x0)
    V = ~common
    L = {}
    for num, nm in (("2", "%s__2__%s_NUDE"), ("10", "%s__10__HEAD_%s"), ("13", "%s__13__HAIR_%s")):
        a = layer(nm % (race, key))
        if a is not None:
            # точка капсулы (x, y) = точка куклы (x+dx, y+dy)
            sh = np.zeros_like(a)
            ys, xs = np.nonzero(a)
            y2, x2 = ys - dy, xs - dx
            ok = (y2 >= 0) & (y2 < 200) & (x2 >= 0) & (x2 < 320)
            sh[y2[ok], x2[ok]] = a[ys[ok], xs[ok]]
            L[num] = sh
    doll = np.zeros_like(pod)
    where = np.full(pod.shape, "-", object)
    for num in ("2", "10", "13"):
        if num in L:
            m = L[num] > 0
            doll[m] = L[num][m]
            where[m] = num
    nv = int(V.sum())
    print("== MAN_%s%s: файлов внешностей %d, меняется точек %d из %d" % (s, key, len(allp), nv, 320 * 200))
    print("   меняющиеся точки по слою куклы:", dict(Counter(where[V].tolist())))
    on = V & (doll > 0)
    ex = (pod[on] == doll[on]).mean() if on.any() else 0
    tab = defaultdict(Counter)
    for a, b in zip(doll[on].tolist(), pod[on].tolist()):
        tab[a][b] += 1
    cons = sum(c.most_common(1)[0][1] for c in tab.values()) / max(1, on.sum())
    print("   на кукле: точь-в-точь %.2f, по таблице индекс->индекс %.2f (разных индексов куклы %d)" % (ex, cons, len(tab)))
    # примеры таблицы: индекс куклы -> индекс капсулы, цвет
    pal = db.game_palette()
    top = sorted(tab.items(), key=lambda kv: -sum(kv[1].values()))[:6]
    print("   примеры:", ["%d%s->%d%s %.0f%%" % (a, tuple(pal[a]), c.most_common(1)[0][0], tuple(pal[c.most_common(1)[0][0]]),
                                              100 * c.most_common(1)[0][1] / sum(c.values())) for a, c in top])
    off = V & (doll == 0)
    print("   меняется вне куклы: %d точек" % off.sum())
    a1 = pal0[pod].astype(np.uint8)
    a2 = pal0[doll].astype(np.uint8); a2[doll == 0] = (30, 30, 34)
    a3 = (a1 * 0.45).astype(np.uint8); a3[V] = (255, 60, 60)
    a4 = pal0[stack[0]].astype(np.uint8)
    tiles = [Image.fromarray(t[y0:y1, x0:x1]).resize(((x1 - x0) * 6, (y1 - y0) * 6), Image.NEAREST) for t in (a1, a2, a3, a4)]
    sheet = Image.new("RGB", (sum(t.width + 8 for t in tiles), tiles[0].height), (14, 15, 19))
    x = 0
    for t in tiles:
        sheet.paste(t, (x, 0)); x += t.width + 8
    sheet.save(os.path.join(os.path.dirname(os.path.abspath(__file__)), "pod_%s_%s.png" % (s, key)))
