#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""XP-000579: живые наёмники M.E.R.C. в HD светлее своего классического трупа - у наборов MRC_1, MRC_3 и PIR_862
(одна основа) HD-кадры светлее классики на 6 единиц L*. Вариант A (выбор Vitali 16.11): каждый HD-кадр затемнён
одним множителем в линейном свете так, чтобы средняя L* его непрозрачных пикселей стала как у классического кадра
(классика - в боевой палитре delicious_regular.pal). Рисунок, тон и альфа те же; кадр не k x классика и кадр,
которого нет в классике, остаются теми же байтами. Пак с отметкой gain=xp579 в settings.txt пропускается.

    tools\hdart\.venv\Scripts\python.exe tools\hdart\xp579_gain.py --out art\_review\xp579_stage
        - сборка паков в --out/<НАБОР>/ и метрики; в игру ничего не пишет
    ... --install --yes --approval "..."   - собранное в манифест build_hd_pack и в установку Пираток; прежнее -
        в art/_backup/xp579/<время>/ (ничего не удаляется). Под очередью правок.
"""
import argparse
import hashlib
import os
import shutil
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.dirname(os.path.dirname(HERE))
os.chdir(ROOT)

import upscale_units as U                            # noqa: E402
import build_hd_pack as bp                           # noqa: E402
import xp549_palette_fix as X                        # noqa: E402

NAMES = ["MRC_1.PCK", "MRC_3.PCK", "PIR_862.PCK"]
MARK = "gain=xp579"
BACKUP = os.path.join("art", "_backup", "xp579")


def lin(c):
    c = c / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055) * 255


def lstar_lin(li):
    y = li[..., 0] * 0.2126 + li[..., 1] * 0.7152 + li[..., 2] * 0.0722
    return np.where(y > 0.008856, 116 * np.cbrt(y) - 16, 903.3 * y)


def match(hd, target):
    """Множитель в линейном свете (бисекция), при котором средняя L* непрозрачного HD = target."""
    m = hd[..., 3] > 128
    li = lin(hd[..., :3].astype(np.float64))
    lm = li[m]
    lo, hi = 0.2, 1.5
    for _ in range(30):
        g = (lo + hi) / 2
        if lstar_lin(np.clip(lm * g, 0, 1)).mean() > target:
            hi = g
        else:
            lo = g
    out = hd.copy()
    out[..., :3] = srgb(li * g).round().astype(np.uint8)
    return out, g


def fix_pack(job):
    name, src_root, out_root = job
    pal = X.battle_pal()
    ents = {e["name"]: e for e in U.read_ruleset_sheets(os.path.join(X.PIR, "Ruleset", "Piratez_Resources.rul"))}
    src = os.path.join(src_root, name)
    sp = os.path.join(src, "settings.txt")
    settings = open(sp, encoding="utf-8", errors="replace").read().strip() if os.path.isfile(sp) else ""
    if MARK in settings.split():
        return name, "уже отмечен", None
    frames, _spal, _w, _h, _notes = U.frames_of_ruleset_set(ents[name], X.PIR)
    cl = dict(frames)
    data = open(os.path.join(src, "pack.hdp"), "rb").read()
    k, bw, bh, blobs = X.read_pack(data)
    out, cache, gains, ls_c, ls_b, ls_a = [], {}, [], [], [], []
    kept = 0
    for idx, blob in blobs:
        c = cl.get(idx)
        hd = None
        if c is not None:
            hd = X.decode(blob)
            if hd.shape[:2] != (c.shape[0] * k, c.shape[1] * k):
                hd = None
        mask = (c != 0) if c is not None else None
        if hd is None or mask.sum() < 30 or (hd[..., 3] > 128).sum() < 30:
            out.append((idx, blob))
            kept += 1
            continue
        key = (blob, c.tobytes())
        if key not in cache:
            target = float(lstar_lin(lin(pal[c[mask]].astype(np.float64))).mean())
            new, g = match(hd, target)
            assert (new[..., 3] == hd[..., 3]).all(), "альфа изменилась"
            png = X.pack_png(new)
            back = X.decode(png)
            assert (back[..., 3] == hd[..., 3]).all(), "альфа изменилась после упаковки"
            m = hd[..., 3] > 128
            cache[key] = (png, g, target, float(lstar_lin(lin(hd[..., :3][m].astype(np.float64))).mean()),
                          float(lstar_lin(lin(back[..., :3][m].astype(np.float64))).mean()))
        png, g, t, b, a = cache[key]
        gains.append(g); ls_c.append(t); ls_b.append(b); ls_a.append(a)
        out.append((idx, png))
    dst = os.path.join(out_root, name)
    os.makedirs(dst, exist_ok=True)
    pk = X.write_pack(k, bw, bh, out)
    with open(os.path.join(dst, "pack.hdp"), "wb") as f:
        f.write(pk)
    with open(os.path.join(dst, "settings.txt"), "w", encoding="utf-8", newline="") as f:
        f.write((settings + " " + MARK).strip())
    return name, "ok", dict(frames=len(blobs), changed=len(gains), kept=kept, classic=np.mean(ls_c), before=np.mean(ls_b),
                            after=np.mean(ls_a), gain=np.mean(gains), old_size=len(data), new_size=len(pk))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=os.path.join("art", "_review", "xp579_stage"))
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--approval", default="")
    a = ap.parse_args()
    src_root = bp.TARGETS["game"]
    if not a.install:
        os.makedirs(a.out, exist_ok=True)
        with ProcessPoolExecutor(len(NAMES)) as ex:
            for n, s, st in ex.map(fix_pack, [(n, src_root, a.out) for n in NAMES]):
                print(n, s, st and "%d/%d кадров, L*: классика %.1f, было %.1f, стало %.1f, множитель %.3f, %d -> %d Б" % (
                    st["changed"], st["frames"], st["classic"], st["before"], st["after"], st["gain"], st["old_size"], st["new_size"]), flush=True)
        return
    if not a.yes or not a.approval:
        raise SystemExit("нужны --yes и --approval (чьё слово и когда); под очередью правок")
    man = bp.load()
    rels, bk = [], os.path.join(BACKUP, time.strftime("%Y%m%d_%H%M%S"))
    for n in NAMES:
        sdir = os.path.join(a.out, n)
        if not os.path.isfile(os.path.join(sdir, "pack.hdp")):
            raise SystemExit("нет собранного пака %s в %s" % (n, a.out))
        os.makedirs(os.path.join(bk, n), exist_ok=True)
        for fn in ("pack.hdp", "settings.txt"):
            gp = os.path.join(src_root, n, fn)
            if os.path.isfile(gp):
                shutil.copyfile(gp, os.path.join(bk, n, fn))
        for fn in ("pack.hdp", "settings.txt"):
            rel = "%s/%s" % (n, fn)
            new = bp.sha256_file(os.path.join(sdir, fn))
            if man["files"].get(rel, {}).get("sha256") == new:
                continue
            bp.stage(man, rel, os.path.join(sdir, fn), generator="xp579_gain.py", generator_version="XP-000579 вариант A",
                     source_path=os.path.join(sdir, fn).replace(os.sep, "/"), approved=True, approval=a.approval)
            rels.append(rel)
    bp.save(man, why="XP-000579: MRC_1, MRC_3, PIR_862 по светлоте классики")
    print("game:", bp.install(man, "game", only=rels), "файлов; прежние - в", bk)
    for rel in rels:
        with open(os.path.join(src_root, rel), "rb") as fh:
            if hashlib.sha256(fh.read()).hexdigest() != man["files"][rel]["sha256"]:
                raise SystemExit("РАСХОДИТСЯ %s" % rel)
    print("сверено: файлов %d" % len(rels))


if __name__ == "__main__":
    main()
