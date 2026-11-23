#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка tools/hdart/anim_flicker.py: мигание петель, где классика меняется на малой площади.

    py -3.13 tools/test_anim_flicker.py
"""
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "hdart"))
import anim_flicker as af                                           # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
FAIL = []
K = 4


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        FAIL.append(name)


def classic(light):
    """Стена 40x32: тело индекса 10, огонёк 2x2 индекса light."""
    a = np.zeros((40, 32), np.uint8)
    a[4:36, 6:26] = 10
    a[12:14, 14:16] = light
    return a


def hd(seed, light_rgb=None):
    """HD стены 160x128: фактура по зерну (разные зёрна - разные рисунки), огонёк по месту классики."""
    rng = np.random.default_rng(seed)
    a = np.zeros((160, 128, 4), np.float32)
    a[16:144, 24:104, :3] = 90 + rng.integers(0, 60, (128, 80, 3))
    a[16:144, 24:104, 3] = 255
    if light_rgb is not None:
        a[48:56, 56:64, :3] = light_rgb
    return a


PAL = np.zeros((256, 3), np.float32)
PAL[10] = (110, 110, 110)
PAL[20] = (40, 40, 40)
PAL[30] = (250, 230, 60)

cb, cf = classic(20), classic(30)

# 1. группы петли: основа - кадр, который показывается чаще; двери пропускаются
recs = af.records(bytes([1, 2, 2, 2, 2, 2, 2, 2] + [0] * 54) + bytes([5, 6, 5, 6, 5, 6, 5, 6] + [0] * 22 + [1] + [0] * 31))
check("дверь НЛО не петля, запись без двери - петля", [r for r, _ in recs] == [0])
g = af.groups(recs, 8, {1: 1, 2: 7})
check("основа группы - кадр, который на экране чаще (2)", g == [(2, [1], [0])])

# 2. контроль: HD кадров петли нарисован порознь - мигание ловится
ha, hf = hd(1, (40, 40, 40)), hd(2, (250, 230, 60))
before = af.measure(cb, cf, ha, hf, 2)
check("контроль: разные рисунки HD вне изменений классики - мигание (вне > %.0f)" % af.OUT_DIFF,
      before["out_diff"] > af.OUT_DIFF)
check("доля изменений классики малая (мягкий класс)", 0 < before["frac"] <= af.SOFT_FRAC)
same = af.measure(cb, cf, ha, hd(1, (250, 230, 60)), 2)
check("один рисунок со своим огоньком - не мигание", same["out_diff"] < 0.5)

# 3. кольцо: один рисунок - мало, разные - много (auto выбирает own или delta)
check("кольцо одного рисунка до RING_SAME", af.ring_diff(cb, cf, ha, hd(1, (250, 230, 60)), 2) <= af.RING_SAME)
check("кольцо разных рисунков больше RING_SAME", af.ring_diff(cb, cf, ha, hf, 2) > af.RING_SAME)

# 4. правка через папку пака: вне маски - основа, варианты - как у основы
with tempfile.TemporaryDirectory() as d:
    pack = Path(d)
    Image.fromarray(ha.astype(np.uint8), "RGBA").save(pack / "1.png")
    Image.fromarray(hd(3, (40, 40, 40)).astype(np.uint8), "RGBA").save(pack / "1.v1.png")
    Image.fromarray(hf.astype(np.uint8), "RGBA").save(pack / "2.png")
    Image.fromarray(hd(4, (250, 230, 60)).astype(np.uint8), "RGBA").save(pack / "2.v2.png")
    for mode in ("own", "delta"):
        new = af.build_fix(pack, "T", 1, 2, cb, cf, 2, mode, PAL)
        check("%s: набор вариантов кадра - как у основы" % mode, sorted(new) == [".png", ".v1.png"])
        after = af.measure(cb, cf, ha, new[".png"].astype(np.float32), 2)
        check("%s: HD вне маски после правки - основа (вне %.2f)" % (mode, after["out_diff"]),
              after["out_diff"] < 1.0)
        far = np.ones((160, 128), bool)
        far[16:96, 32:88] = False                      # далеко от огонька: ровно основа до байта
        check("%s: вдали от маски - побайтно основа" % mode,
              np.array_equal(new[".png"][far], ha.astype(np.uint8)[far]))
        allowed = af.up(af.dilate(cb != cf, 2), K)
        check("%s: вне разрешённой маски - побайтно основа, с альфой и RGB под прозрачным" % mode,
              all(np.array_equal(v[~allowed], (ha if r == ".png" else hd(3, (40, 40, 40))).astype(np.uint8)[~allowed])
                  for r, v in new.items()))
        w = af.weight(cb, cf, K, 2)[..., 0]
        check("%s: перо только внутрь маски, без ступени на её краю (край %.2f)" % (mode, w[allowed].min()),
              (w[~allowed] == 0).all() and 0 < w[allowed].min() <= 0.15)
        lit = new[".png"][50:54, 58:62, :3].astype(float).mean((0, 1))
        check("%s: огонёк в середине маски загорелся (R %.0f, B %.0f)" % (mode, lit[0], lit[2]),
              lit[0] > 180 and lit[2] < 120)
    # контроль на сам контроль: правка с нулевой маской (кадр = основа) не меняет основу
    new0 = af.build_fix(pack, "T", 1, 2, cb, cb, 2, "delta", PAL)
    check("кадр с той же классикой после delta - основа побайтно",
          np.array_equal(new0[".png"], ha.astype(np.uint8)))

# 5. delta: тёмная деталь на яркой основе не обрезается по каналам (оттенок не съезжает),
#    кайма размытия на пустом месте основы не становится непрозрачной
bright = hd(5, (250, 230, 60))
bright[16:144, 24:104, :3] = (250, 230, 60)
cbr, cdk = classic(30), classic(20)
cdk[36:38, 14:16] = 20                              # деталь у нижнего края силуэта: размытие выходит наружу
cdk[38:40, 14:16] = 20
wd = af.weight(cbr, cdk, K, 2)
nd = af.compose_delta(bright, cbr, cdk, PAL, wd).astype(np.float32)
pm = nd[..., :3] * nd[..., 3:] / 255.0
check("delta: предумноженный цвет в [0, a]", bool((pm >= -0.5).all() and (pm <= nd[..., 3:] + 0.5).all()))
dark = nd[50:54, 58:62, :3].mean((0, 1))
check("delta: огонёк погас без сдвига оттенка (R %.0f, G %.0f, B %.0f, отношение R/G как у основы)"
      % tuple(dark), dark[0] < 200 and abs(dark[0] / max(dark[1], 1) - 250 / 230) < 0.15)
empty = (bright[..., 3] == 0) & ~af.up(cdk > 0, K)
check("delta: на пустом месте основы и классики кадра альфа 0 (кайма %d пикс)" % int((nd[..., 3][empty] > 0).sum()),
      not (nd[..., 3][empty] > 0).any())

# 6. delta: мелкий огонёк (один пиксель базы) не гаснет размытием разницы (R-351).
#    Прежняя classic_up (bilinear плюс гаусс k*0.4) давала около 0.4 точной разницы - контроль ниже обязан это видеть.
def classic_up_old(fr, pal, k):
    from PIL import Image as _I
    a = np.zeros(fr.shape + (4,), np.float32)
    m = fr > 0
    a[m, :3] = pal[fr[m]]
    a[m, 3] = 255.0
    a[..., :3] *= a[..., 3:] / 255.0
    a = np.stack([np.asarray(_I.fromarray(a[..., c], "F").resize((fr.shape[1] * k, fr.shape[0] * k), _I.BILINEAR))
                  for c in range(4)], 2)
    return np.stack([af.gauss(a[..., c], k * 0.4) for c in range(4)], 2)


PAL[25] = (120, 120, 120)
c1, c2 = classic(20), classic(20)
c2[12, 14] = 25                                     # огонёк в один пиксель базы, разница 80 без обрезки
base1 = hd(6, (40, 40, 40))
core = af.up(c1 != c2, K)
exact = 80.0


def lit_of(fn):
    keep = af.classic_up
    af.classic_up = fn
    try:
        n = af.compose_delta(base1, c1, c2, PAL, af.weight(c1, c2, K, 2)).astype(np.float32)
    finally:
        af.classic_up = keep
    return af.hd_diff(n, base1)[core].mean() / exact


lit_new, lit_old = lit_of(af.classic_up), lit_of(classic_up_old)
check("delta: огонёк в пиксель базы не ниже 0.6 точной разницы (%.2f)" % lit_new, lit_new >= 0.6)
check("контроль: прежнее двойное размытие этот огонёк гасит (%.2f)" % lit_old, lit_old < 0.6)

# 8. установка по плану (--only install.tsv): ставятся ровно кадры плана и ровно его байты
import hashlib                                                      # noqa: E402
import io                                                           # noqa: E402
with tempfile.TemporaryDirectory() as d:
    pack = Path(d)
    Image.fromarray(ha.astype(np.uint8), "RGBA").save(pack / "1.png")
    Image.fromarray(hf.astype(np.uint8), "RGBA").save(pack / "2.png")
    new = af.build_fix(pack, "T", 1, 2, cb, cf, 2, "delta", PAL)
    shas = []
    for rest, arr in new.items():
        buf = io.BytesIO()
        Image.fromarray(arr, "RGBA").save(buf, "PNG")
        shas.append("%s=%s" % (rest, hashlib.sha256(buf.getvalue()).hexdigest()[:12]))
    tsv = pack / "install.tsv"
    tsv.write_text("набор\tкадр\tосновa\tрежим\tsha\nT\t2\t1\tdelta\t%s\n" % " ".join(shas), encoding="utf-8-sig")
    plan = af.read_plan(tsv)
    check("план прочитан: кадр, режим, sha", plan == {("T", 2): {"mode": "delta", "sha": dict(s.split("=") for s in shas)}})
    rows8 = [{"set": "T", "frame": 2}, {"set": "T", "frame": 3}]
    check("по плану берутся только его кадры", af.plan_rows(rows8, plan) == rows8[:1])
    try:
        af.plan_rows(rows8[1:], plan)
        check("кадр плана, который не мигает, - отказ", False)
    except SystemExit:
        check("кадр плана, который не мигает, - отказ", True)
    item = {"row": {"set": "T", "frame": 2}, "files": new}
    check("байты правки равны sha плана", af.plan_check([item], plan) == [])
    bent = dict(new)
    bent[".png"] = new[".png"].copy()
    bent[".png"][0, 0, 0] ^= 1
    check("контроль: байт правки ушёл от плана - расхождение", af.plan_check([{"row": item["row"], "files": bent}], plan) == ["T 2"])

# 9. копия user/mods/hd: набор целиком, если папки нет, она неполная или прочие файлы не равны манифесту
import build_hd_pack as bp                                          # noqa: E402
with tempfile.TemporaryDirectory() as d:
    repo = Path(d)
    sd = "TERRAIN/S.PCK/"
    (repo / sd).mkdir(parents=True)
    body = {"0.png": b"base", "1.png": b"frame", "2.png": b"other"}
    for fn, data in body.items():
        (repo / sd / fn).write_bytes(data)
    man9 = {"files": {sd + fn: {"sha256": hashlib.sha256(data).hexdigest()} for fn, data in body.items()}}
    man9["files"][sd + "1.png"] = {"sha256": "0" * 64}                 # кадр 1 уже переписан в манифесте
    staged9 = {sd + "1.png"}
    check("набор в копии равен манифесту - только правленый кадр", af.repo_whole(bp, man9, repo, sd, staged9) is None)
    (repo / sd / "2.png").write_bytes(b"old")
    check("прочий файл набора не равен манифесту - набор целиком",
          sorted(af.repo_whole(bp, man9, repo, sd, staged9) or []) == sorted(man9["files"]))
    (repo / sd / "2.png").unlink()
    check("набор неполный - целиком (R-257)", sorted(af.repo_whole(bp, man9, repo, sd, staged9) or []) == sorted(man9["files"]))
    check("папки нет - целиком",
          af.repo_whole(bp, {"files": {"TERRAIN/NONE.PCK/0.png": {"sha256": "x"}}}, repo, "TERRAIN/NONE.PCK/", set())
          == ["TERRAIN/NONE.PCK/0.png"])

# 7. контроли живой анимации (пилот 15.10): LAM_FLOOR и WHITEBITS не правятся, хотя доля изменений
#    у части кадров ниже LIVE_FRAC. Настоящие данные установки. Контроль: ANIM_FLICKER_NO_LIVE_SETS=1 - падает.
import os                                                           # noqa: E402
import loop_twins as lt                                             # noqa: E402
if os.environ.get("ANIM_FLICKER_NO_LIVE_SETS") == "1":
    af.LIVE_SETS = set()
ctl = {"LAM_FLOOR", "WHITEBITS"}
rows = af.scan(lt.COPIES["установка"], "установка", ctl, lt.game_files(), 2)
got = {r["set"] for r in rows}
check("контроли найдены в установке (%s)" % ", ".join(sorted(got)), got == ctl)
bad = ["%s %d<-%d %s" % (r["set"], r["frame"], r["base"], r["class"]) for r in rows if r["class"].startswith("мигает")]
check("контроли не попадают в правку (мигает: %d%s)" % (len(bad), "; " + ", ".join(bad[:4]) if bad else ""), not bad)

print("ИТОГ:", "FAIL " + ", ".join(FAIL) if FAIL else "все проверки прошли")
sys.exit(1 if FAIL else 0)
