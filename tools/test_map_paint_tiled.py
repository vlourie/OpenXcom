# -*- coding: utf-8 -*-
"""Проверка map_paint.paint_tiled без видеокарты (R-005): частый кадр обязан стыковаться сам с собой.

1. Стык. Вместо модели - гладкий случайный рисунок, заведомо НЕ периодичный. Из него paint_tiled
   собирает клетку; копии клетки раскладываются по сетке, как в игре, и перепад на стыке копий
   сравнивается с перепадом внутри клетки. Простой вырез центральной копии (как делал режим участков,
   прогон 11: шов по стене склада) обязан тест провалить - иначе тест ничего не ловит.
2. Порядок. Поле копий, которое видит модель, обязано совпасть с тем, как эту же стену рисует карта:
   порядок по высоте на экране открывал тёмный торец кадра на каждом стыке (прогон 12).

Нужны данные X-Piratez (только чтение). Запуск: python tools/test_map_paint_tiled.py
"""
import os
import sys
from types import SimpleNamespace

import numpy as np
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "hdart"), HERE]
os.chdir(os.path.dirname(HERE))
import map_mockup as mm  # noqa: E402
import map_paint as mp  # noqa: E402

T, B = "CULTA_UBER", "CULTASOLHUGE01"
CASES = [("BARN", 11), ("CULTIVAT_UBER", 0)]    # стена в два этажа и трава
K = 4


class Fake:
    """Вместо модели: гладкий шум xg, от входа не зависит. Первый вход запоминается."""
    def __init__(self):
        self.inputs = []

    def paint(self, rgba, g, prompt, seed, under=None, opts=None):
        self.inputs.append(rgba.copy())
        rng = np.random.default_rng(seed)
        small = rng.integers(0, 256, (rgba.height // 2 + 2, rgba.width // 2 + 2, 3)).astype(np.uint8)
        im = Image.fromarray(small).resize((rgba.width * g, rgba.height * g), Image.BICUBIC)
        return im.filter(ImageFilter.GaussianBlur(g * 0.6))


def wall_of(cell, spr, lattice):
    """Копии клетки x4 по сетке в игровом порядке; владелец каждого пикселя."""
    two = len(lattice) > 1
    offs = [(n, m) for n in range(-2, 3) for m in (range(-1, 2) if two else [0])]
    pts = [(n * lattice[0][0] + (m * lattice[1][0] if two else 0),
            n * lattice[0][1] + (m * lattice[1][1] if two else 0)) for n, m in offs]
    x_lo, y_lo = min(p[0] for p in pts), min(p[1] for p in pts)
    w = (max(p[0] for p in pts) + 32 - x_lo) * K
    h = (max(p[1] for p in pts) + 40 - y_lo) * K

    def z(i):
        n, m = offs[i]
        if lattice[0] == (0, -24):
            return n
        return m if two and lattice[1] == (0, -24) else 0
    order = sorted(range(len(pts)), key=lambda i: (z(i), pts[i][1], pts[i][0]))
    img = np.zeros((h, w, 3), np.float32)
    own = np.full((h, w), -1, np.int32)
    c = np.asarray(cell.convert("RGB")).astype(np.float32)
    a = np.kron(np.asarray(spr)[..., 3] > 0, np.ones((K, K), bool))
    for i in order:
        x, y = (pts[i][0] - x_lo) * K, (pts[i][1] - y_lo) * K
        img[y:y + 40 * K, x:x + 32 * K][a] = c[a]
        own[y:y + 40 * K, x:x + 32 * K][a] = i
    return img, own


def seam_ratio(img, own):
    """Средний перепад между соседями разных копий / между соседями одной копии."""
    seam, inner = [], []
    for dy, dx in ((0, 1), (1, 0)):
        a_own, b_own = own[:own.shape[0] - dy, :own.shape[1] - dx], own[dy:, dx:]
        d = np.abs(img[:img.shape[0] - dy, :img.shape[1] - dx] - img[dy:, dx:]).mean(-1)
        both = (a_own >= 0) & (b_own >= 0)
        seam.append(d[both & (a_own != b_own)])
        inner.append(d[both & (a_own == b_own)])
    s, i = np.concatenate(seam), np.concatenate(inner)
    return float(s.mean() / max(1e-6, i.mean())), len(s)


def naive_cell(fake_input, painted, g):
    """Простой вырез центральной копии из того же рисунка - как в режиме участков."""
    return painted


# кадр, его тип, основы, которые обязаны найтись (census/over_base.tsv, two_base в gen3-audit.md)
REUSE = [
    ("окно в стене", ("BARN", 13), 1, [("BARN", 11)]),
    ("стена с плющом из чужого набора", ("GOTHIC", 13), 1, [("ACHURCH2", 4)]),
    ("дерево на полу", ("NEOJUNGLE", 58), 3, [("NEOJUNGLE", 0)]),
    ("стена из двух основ, одна чужая", ("CULTBITS", 3), 1, [("CULTAN", 6), ("CULTBITS", 5)]),
    ("перекрёсток дороги из двух", ("ROADS", 2), 0, [("ROADS", 6), ("ROADS", 7)]),
]


def check_reuse(w, name, key, part, bases):
    """3. Кадр поверх готового (окно BARN 13 = стена BARN 11 плюс окошко; дерево поверх пола; перекрёсток
    из двух дорог): совпавшее с готовыми обязано прийти из них до байта, отличия - из своего рисунка.
    Иначе снова заплатка (прогон 14)."""
    import tempfile
    root = tempfile.mkdtemp()
    spr = w.sprite(*key, None)
    rng = np.random.default_rng(1)
    made = {}
    for bk in bases:
        made[bk] = Image.fromarray(rng.integers(0, 256, (160, 128, 3)).astype(np.uint8))
        os.makedirs(os.path.join(root, bk[0] + ".PCK"), exist_ok=True)
        made[bk].save(os.path.join(root, bk[0] + ".PCK", "%d.png" % bk[1]))
    own = np.full((160, 128, 3), 128, np.uint8)
    got = mp.reuse_base(w, root, key[0], key[1], own, spr, set(bases), {}, part=part)
    if got is None or sorted(got[1]) != sorted(bases):
        print("BAD  %s %s %d: основы %s, ждали %s" % (name, key[0], key[1], got and got[1], bases))
        return 1
    cell = np.asarray(got[0]).astype(int)
    a = np.asarray(spr)
    # чья клетка должна стоять в пикселе - как в same_base: жадно, первая основа забирает своё
    who = np.full(a.shape[:2], -1)
    for j, bk in enumerate(got[1]):
        b = np.asarray(w.sprite(*bk, None))
        same = (a[..., 3] > 0) & (b[..., 3] > 0) & (np.abs(a[..., :3].astype(int) - b[..., :3].astype(int)).sum(-1) == 0)
        who[same & (who < 0)] = j
    same = who >= 0
    diff4 = np.kron((a[..., 3] > 0) & ~same, np.ones((K, K), bool))
    # дальше 4 пикселей x4 от отличий - ровно основа; в глубине отличий - свой рисунок
    near = np.asarray(Image.fromarray((diff4 * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(9))) > 0
    want = np.zeros_like(cell)
    for j, bk in enumerate(got[1]):
        m4 = np.kron(who == j, np.ones((K, K), bool))
        want[m4] = np.asarray(made[bk]).astype(int)[m4]
    far_same = np.kron(same, np.ones((K, K), bool)) & ~near
    core = np.asarray(Image.fromarray((diff4 * 255).astype(np.uint8)).filter(ImageFilter.MinFilter(5))) > 0
    d_same = int((np.abs(cell - want).sum(-1)[far_same] > 0).sum())
    toned = np.asarray(mp.match_tone(Image.fromarray(own), spr, mp.TONE)).astype(int)
    d_core = int((np.abs(cell - toned).sum(-1)[core] > 3).sum())
    # отличия бывают в пиксель шириной (плющ, разметка дороги) - тогда глубины у них нет, проверять нечего
    ok = d_same == 0 and d_core == 0 and far_same.sum() > 500
    print("%s  %s %s %d из %s (%.0f%%): мимо основы %d из %d, не своё в отличиях %d из %d"
          % ("ok " if ok else "BAD", name, key[0], key[1], " + ".join("%s %d" % b for b in got[1]),
             100 * got[2], d_same, int(far_same.sum()), d_core, int(core.sum())))
    return 0 if ok else 1


def check_scenes():
    """R-016: поля полов и стен не получают предметов темы; у каждой темы пилота есть « | »."""
    bad = 0
    full, surf = mp.scene_prompts("grey floor | red barrels")
    if "red barrels" in surf or "red barrels" not in full or "grey floor" not in surf:
        print("BAD  тема: поле получило предметы или участок их потерял")
        bad += 1
    for name, sc in mp.SCENES.items():
        if " | " not in sc and name in ("UBASE_00", "URBAN06", "CATACOMBS_33"):
            print("BAD  тема %s без деления на поверхности и предметы" % name)
            bad += 1
    print("%s  тема делится на поверхности и предметы" % ("ok " if not bad else "BAD"))
    return bad


def main():
    w = mm.World()
    _im, _ow, inst = mp.layout(w, T, B)
    bad = check_scenes()
    for key in CASES:
        d = next(q for q in inst if (q["set"], q["frame"]) == key)
        lattice = mp.tile_lattice(inst, key)
        fake = Fake()
        args = SimpleNamespace(g_context=K)
        cell, _rep = mp.paint_tiled(w, fake, args, "", 7, d["spr"], d["part"], lattice)
        r_tiled, n = seam_ratio(*wall_of(cell, d["spr"], lattice))

        # тот же рисунок, клетка - просто вырез центра (без сборки)
        mos = fake.inputs[0]
        painted = Fake().paint(mos, K, "", 7)
        pad = 8
        xs = [q for q in inst if (q["set"], q["frame"]) == key]
        # центр поля - там, где paint_tiled его ставит: считаем так же
        two = len(lattice) > 1
        reach = 1 if two else 2
        pts = [(n_ * lattice[0][0] + (m * lattice[1][0] if two else 0),
                n_ * lattice[0][1] + (m * lattice[1][1] if two else 0))
               for n_ in range(-reach, reach + 1) for m in (range(-reach, reach + 1) if two else [0])]
        cx, cy = pad - min(p[0] for p in pts), pad - min(p[1] for p in pts)
        cut = painted.crop((cx * K, cy * K, (cx + 32) * K, (cy + 40) * K))
        r_cut, _n = seam_ratio(*wall_of(cut, d["spr"], lattice))
        ok1 = r_tiled <= 1.5
        sens = r_cut >= 2.0
        print("%s  %s %d: стык/внутри - сборка %.2f, простой вырез %.2f (пар на стыке %d)"
              % ("ok " if ok1 and sens else "BAD", key[0], key[1], r_tiled, r_cut, n))
        bad += not (ok1 and sens)

        # порядок: поле копий против карты - в клетке, у которой все соседи по сетке тот же кадр
        pos = {(q["x"], q["y"]) for q in xs}
        # закрыть клетку могут соседи вдоль сетки и этаж ВЫШЕ; этаж ниже рисуется раньше и ничего не закрывает
        need = [(sx * a, sy * a) for sx, sy in lattice for a in (-1, 1) if (sx, sy) != (0, -24) or a == 1]
        mid = next((q for q in xs if all((q["x"] + nx, q["y"] + ny) in pos for nx, ny in need)), None)
        if mid is None:
            print("--   %s %d: нет клетки, окружённой своими копиями - порядок не проверен" % key)
            continue
        # карта до этажа над соседом сверху: крыша и прочее выше клетку не касаются этой проверки
        up = 1 if (0, -24) in lattice else 0
        im_map, owner_map, inst_z = mp.layout(w, T, B, maxz=mid["z"] + up)
        mine = {i for i, q in enumerate(inst_z) if (q["set"], q["frame"]) == key}
        ref = np.asarray(im_map)[mid["y"]:mid["y"] + 40, mid["x"]:mid["x"] + 32]
        own = owner_map[mid["y"]:mid["y"] + 40, mid["x"]:mid["x"] + 32]
        ours = np.isin(own, list(mine))
        got = np.asarray(mos)[cy:cy + 40, cx:cx + 32]
        diff = int((np.abs(ref[..., :3].astype(int) - got[..., :3].astype(int)).sum(-1)[ours] > 0).sum())
        ok2 = diff == 0 and ours.sum() > 100
        print("%s  %s %d: поле копий против карты - несовпавших пикселей %d из %d"
              % ("ok " if ok2 else "BAD", key[0], key[1], diff, int(ours.sum())))
        bad += not ok2
    for case in REUSE:
        bad += check_reuse(w, *case)
    print("итог:", "всё верно" if not bad else "ОШИБОК %d" % bad)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
