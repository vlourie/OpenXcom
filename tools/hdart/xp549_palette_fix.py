#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""XP-000549: HD-паки юнитов собраны по палитре, зашитой в PNG листа, а игра красит классику боевой
delicious_regular.pal (R-030) - тёмное в HD светлее классики. Вариант C (выбор Vitali 10.11): весь рисунок
пака по цвету классики - к каждому HD-пикселю прибавляется (цвет боевой палитры - цвет палитры листа) для
классического индекса под ним, плавным полем (билинейный апсэмпл), чтобы детали HD сохранились.

Меняется только цвет: альфа каждого кадра байт в байт та же (assert по декодированным кадрам), края не тронуты.
Кадр, у которого размер не k x классика, и кадр, которого нет в классике, остаются как были (те же байты).
Пак с отметкой palette_fix=xp549 в settings.txt пропускается (второй раз не применяется).

    py -3.13 tools/hdart/xp549_palette_fix.py --list census/tickets/XP-000549/dark_lift.tsv --min-diff 15 --out art/_review/xp549_stage
        - сборка паков в --out/<НАБОР>/pack.hdp (+settings.txt) и метрики; в игру ничего не пишет
    ... --install --yes --approval "..."   - положить собранное в мод hd (манифест build_hd_pack, установка Пираток);
        прежний pack.hdp и settings.txt - в art/_backup/xp549/<НАБОР>/ (ничего не удаляется). Под очередью правок.
Запускать интерпретатором tools/hdart/.venv (там imagequant и oxipng для упаковки кадров, как в optimize_hd).
"""
import argparse
import csv
import io
import os
import shutil
import struct
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from types import SimpleNamespace

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.dirname(os.path.dirname(HERE))
os.chdir(ROOT)

import upscale_units as U                            # noqa: E402
import optimize_hd as OH                             # noqa: E402
import build_hd_pack as bp                           # noqa: E402

ENC = "utf-8-sig"
MARK = "palette_fix=xp549"
PIR = os.path.join(ROOT, "Пиратки", "Dioxine_XPiratez", "user", "mods", "Piratez")
PACK_MAGIC = b"OXHDPCK1"
DARK = 40
LUM_W = np.array([0.299, 0.587, 0.114], np.float32)
PNG_ARGS = SimpleNamespace(mode="palette", min_psnr=34.0, level=3)
BACKUP = os.path.join("art", "_backup", "xp549")


def battle_pal():
    lines = open(os.path.join(PIR, "Resources", "Pals", "delicious_regular.pal"), encoding="utf-8", errors="replace").read().split("\n")
    return np.array([tuple(int(x) for x in l.split()) for l in lines[3:3 + 256]], np.uint8)


def read_pack(data):
    scale, bw, bh, n = struct.unpack_from("<4I", data, 8)
    entries = [struct.unpack_from("<3I", data, 24 + i * 12) for i in range(n)]
    return scale, bw, bh, [(a, data[o:o + s]) for a, o, s in entries]


def write_pack(scale, bw, bh, blobs):
    """blobs: [(index, png bytes)]; одинаковые байты хранятся один раз, как в optimize_hd."""
    seen, order = {}, []
    for _, b in blobs:
        if b not in seen:
            seen[b] = None
            order.append(b)
    pos = 24 + 12 * len(blobs)
    for b in order:
        seen[b] = pos
        pos += len(b)
    out = bytearray(PACK_MAGIC + struct.pack("<IIII", scale, bw, bh, len(blobs)))
    for i, b in blobs:
        out += struct.pack("<III", i, seen[b], len(b))
    for b in order:
        out += b
    return bytes(out)


def lum(a):
    return a @ LUM_W


def up(arr, k):
    if arr.ndim == 2:
        return np.asarray(Image.fromarray(arr.astype(np.float32), "F").resize((arr.shape[1] * k, arr.shape[0] * k), Image.BILINEAR))
    return np.stack([up(arr[..., i], k) for i in range(arr.shape[2])], -1)


def recolor(c, hd, k, pal, spal):
    """Вариант C: HD + (боевая - листовая) по индексу классики под пикселем; альфа не меняется."""
    valid = (c != 0).astype(np.float32)
    cb = pal[c].astype(np.float32) * valid[..., None]
    cs = spal[c].astype(np.float32) * valid[..., None]
    v4 = up(valid, k)
    ok = v4 > 0.02
    inv = 1.0 / np.maximum(v4, 1e-3)
    corr = (up(cb, k) * inv[..., None] - up(cs, k) * inv[..., None]) * ok[..., None]
    out = hd.copy()
    out[..., :3] = np.rint(np.clip(hd[..., :3].astype(np.float32) + corr, 0, 255)).astype(np.uint8)
    return out


def downscale(rgba, k):
    h, w = rgba.shape[:2]
    a = rgba[..., 3:4].astype(np.float32) / 255
    rgb = rgba[..., :3].astype(np.float32) * a
    h1, w1 = h // k, w // k
    rgb = rgb[:h1 * k, :w1 * k].reshape(h1, k, w1, k, 3).sum((1, 3))
    a = a[:h1 * k, :w1 * k].reshape(h1, k, w1, k, 1).sum((1, 3))
    return rgb / np.maximum(a, 1e-6), (a / (k * k))[..., 0]


def dark_median(items, pal, k):
    """items: [(classic indices, hd rgba)] -> (медиана яркости классики, медиана HD) по тёмным местам, как в dark_lift.py."""
    cv, hv = [], []
    for c, hd in items:
        crgb = pal[c].astype(np.float32)
        drgb, da = downscale(hd, k)
        m = (c != 0) & (lum(crgb) < DARK) & (da > 0.9)
        if m.sum() < 3:
            continue
        cv.append(lum(crgb)[m])
        hv.append(lum(drgb)[m])
    if not cv:
        return None, None
    return float(np.median(np.concatenate(cv))), float(np.median(np.concatenate(hv)))


def decode(blob):
    return np.asarray(Image.open(io.BytesIO(blob)).convert("RGBA"))


def pack_png(rgba):
    """PNG кадра с ТОЧНОЙ альфой. Палитровый (как в паках после optimize_hd), если альфа - несколько уровней и PSNR
    не хуже 34 дБ: непрозрачные пиксели - одна палитра с дизерингом, каждый уровень неполной альфы - свои 8 цветов
    (палитра PNG держит альфу на запись). Иначе - RGBA без потерь."""
    import imagequant
    im = Image.fromarray(rgba, "RGBA")
    a = rgba[..., 3]
    levels = [int(v) for v in np.unique(a) if 0 < v < 255]

    def lossless():
        return OH.squeeze(OH.to_png(im), PNG_ARGS.level)

    if len(levels) > 8 or not (a == 255).any():
        return lossless()
    k_part = 8
    n_op = 256 - 1 - k_part * len(levels)
    rgb = rgba[..., :3].copy()
    rgb[a == 0] = rgb[a == 255].mean(0).astype(np.uint8)          # прозрачное не тянет палитру
    q = imagequant.quantize_pil_image(Image.fromarray(rgb, "RGB").convert("RGBA"), dithering_level=1.0, max_colors=n_op)
    idx = np.asarray(q).astype(np.int32)
    n_used = int(idx.max()) + 1
    pal = np.array(q.getpalette()[:3 * n_used], np.uint8).reshape(-1, 3)
    if n_used > n_op:
        return lossless()
    entries = [tuple(int(v) for v in c) + (255,) for c in pal]
    out = np.zeros(a.shape, np.int32)
    out[a == 255] = idx[a == 255]
    entries.append((0, 0, 0, 0))
    out[a == 0] = len(entries) - 1
    for lv in levels:
        m = a == lv
        cols = rgba[..., :3][m]
        sq = Image.fromarray(cols.reshape(1, -1, 3), "RGB").quantize(colors=k_part, method=Image.MEDIANCUT, dither=Image.NONE)
        sp = np.array(sq.getpalette()[:3 * k_part], np.uint8).reshape(-1, 3)
        base = len(entries)
        for c in sp:
            entries.append(tuple(int(v) for v in c) + (lv,))
        out[m] = base + np.asarray(sq).reshape(-1).astype(np.int32)
    if len(entries) > 256:
        return lossless()
    P = Image.fromarray(out.astype(np.uint8), "P")
    P.putpalette([v for e in entries for v in e[:3]])
    buf = io.BytesIO()
    P.save(buf, format="PNG", transparency=bytes(e[3] for e in entries), optimize=True)
    png = OH.squeeze(buf.getvalue(), PNG_ARGS.level)
    back = decode(png)
    if not (back[..., 3] == a).all() or OH.visible_psnr(im, Image.fromarray(back, "RGBA")) < PNG_ARGS.min_psnr:
        return lossless()
    return png


def fix_pack(job):
    name, src_root, out_root = job
    pal = battle_pal()
    ents = {e["name"]: e for e in U.read_ruleset_sheets(os.path.join(PIR, "Ruleset", "Piratez_Resources.rul"))}
    src = os.path.join(src_root, name)
    sp = os.path.join(src, "settings.txt")
    settings = open(sp, encoding="utf-8", errors="replace").read().strip() if os.path.isfile(sp) else ""
    if MARK in settings.split():
        return name, "уже отмечен", None
    frames, spal, w, h, notes = U.frames_of_ruleset_set(ents[name], PIR)
    cl = dict(frames)
    spal = np.asarray(spal, np.uint8)[:256]
    data = open(os.path.join(src, "pack.hdp"), "rb").read()
    k, bw, bh, blobs = read_pack(data)
    out_blobs, before, after = [], [], []
    cache = {}
    changed = kept = 0
    for idx, blob in blobs:
        c = cl.get(idx)
        hd = None
        if c is not None:
            hd = decode(blob)
            if hd.shape[:2] != (c.shape[0] * k, c.shape[1] * k):
                hd = None
        if hd is None:
            out_blobs.append((idx, blob))
            kept += 1
            continue
        key = (blob, c.tobytes())
        if key not in cache:
            new = recolor(c, hd, k, pal, spal)
            assert (new[..., 3] == hd[..., 3]).all(), "альфа изменилась"
            png = pack_png(new)
            back = decode(png)
            assert (back[..., 3] == hd[..., 3]).all(), "альфа изменилась после упаковки"
            cache[key] = (png, back)
        png, back = cache[key]
        before.append((c, hd))
        after.append((c, back))
        out_blobs.append((idx, png))
        changed += 1
    cm0, hm0 = dark_median(before, pal, k)
    cm1, hm1 = dark_median(after, pal, k)
    dst = os.path.join(out_root, name)
    os.makedirs(dst, exist_ok=True)
    pk = write_pack(k, bw, bh, out_blobs)
    with open(os.path.join(dst, "pack.hdp"), "wb") as f:
        f.write(pk)
    with open(os.path.join(dst, "settings.txt"), "w", encoding="utf-8", newline="") as f:
        f.write((settings + " " + MARK).strip())
    st = dict(frames=len(blobs), changed=changed, kept=kept, classic=cm0, before=hm0, after=hm1,
              old_size=len(data), new_size=len(pk))
    return name, "ok", st


def pick_packs(path, min_diff):
    rows = list(csv.reader(open(path, encoding=ENC), delimiter="\t"))
    return [r[0] for r in rows[1:] if float(r[5]) > min_diff]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", required=True)
    ap.add_argument("--min-diff", type=float, default=15.0)
    ap.add_argument("--out", default=os.path.join("art", "_review", "xp549_stage"))
    ap.add_argument("--only", default="", help="через запятую; для пробы")
    ap.add_argument("--names-file", default="", help="список наборов (по одному в строке) вместо порога --min-diff")
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--approval", default="")
    ap.add_argument("--report", default="")
    a = ap.parse_args()
    names = pick_packs(a.list, a.min_diff)
    if a.names_file:
        names = [l.strip() for l in open(a.names_file, encoding=ENC).read().split("\n") if l.strip() and not l.startswith("#")]
    if a.only:
        names = [n for n in names if n in set(a.only.split(","))]
    src_root = os.path.join(bp.TARGETS["game"])
    t0 = time.time()
    results = []
    if not a.install:
        os.makedirs(a.out, exist_ok=True)
        with ProcessPoolExecutor(a.jobs) as ex:
            for r in ex.map(fix_pack, [(n, src_root, a.out) for n in names]):
                results.append(r)
                print(r[0], r[1], r[2] and "%d/%d кадров, тёмная медиана: классика %.1f, было %.1f, стало %.1f, %d -> %d Б" % (
                    r[2]["changed"], r[2]["frames"], r[2]["classic"] or -1, r[2]["before"] or -1, r[2]["after"] or -1,
                    r[2]["old_size"], r[2]["new_size"]), flush=True)
        if a.report:
            with open(a.report, "w", encoding=ENC, newline="") as f:
                f.write("pack\tкадров\tизменено\tне тронуто\tclassic_med\tбыло\tстало\tразница_стало\tразмер_был\tразмер_стал\n")
                for n, s, st in results:
                    if st:
                        d = (st["after"] - st["classic"]) if st["after"] is not None else float("nan")
                        f.write("%s\t%d\t%d\t%d\t%.1f\t%.1f\t%.1f\t%.1f\t%d\t%d\n" % (
                            n, st["frames"], st["changed"], st["kept"], st["classic"] or -1, st["before"] or -1, st["after"] or -1, d,
                            st["old_size"], st["new_size"]))
        print("готово за %.0f с, паков %d" % (time.time() - t0, len(results)))
        return
    # ---- установка: собранное в --out -> манифест -> установка Пираток
    if not a.yes or not a.approval:
        raise SystemExit("нужны --yes и --approval (чьё слово и когда); под очередью правок")
    man = bp.load()
    rels, bk = [], os.path.join(BACKUP, time.strftime("%Y%m%d_%H%M%S"))
    for n in names:
        sdir = os.path.join(a.out, n)
        if not os.path.isfile(os.path.join(sdir, "pack.hdp")):
            raise SystemExit("нет собранного пака %s в %s" % (n, a.out))
        gdir = os.path.join(src_root, n)
        os.makedirs(os.path.join(bk, n), exist_ok=True)
        for fn in ("pack.hdp", "settings.txt"):
            gp = os.path.join(gdir, fn)
            if os.path.isfile(gp):
                shutil.copyfile(gp, os.path.join(bk, n, fn))
        for fn in ("pack.hdp", "settings.txt"):
            rel = "%s/%s" % (n, fn)
            old = man["files"].get(rel, {})
            new = bp.sha256_file(os.path.join(sdir, fn))
            if old.get("sha256") == new:
                continue
            bp.stage(man, rel, os.path.join(sdir, fn), generator="xp549_palette_fix.py", generator_version="XP-000549 вариант C",
                     source_path=os.path.join(sdir, fn).replace(os.sep, "/"), approved=True, approval=a.approval)
            rels.append(rel)
    bp.save(man, why="XP-000549: %d паков в боевую палитру" % len(names))
    print("game:", bp.install(man, "game", only=rels), "файлов; прежние - в", bk)
    import hashlib
    for rel in rels:
        with open(os.path.join(src_root, rel), "rb") as fh:
            if hashlib.sha256(fh.read()).hexdigest() != man["files"][rel]["sha256"]:
                raise SystemExit("РАСХОДИТСЯ %s" % rel)
    print("сверено: файлов %d" % len(rels))


if __name__ == "__main__":
    main()
