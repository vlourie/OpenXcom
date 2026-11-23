"""WALL_FINAL_SELECT, шаг 1: варианты A и B2 для каждой используемой стены (решение специалиста 08.10).

Список стен - census/walls/wall_render_frames.tsv: одна строка - одна картинка классики (хэш), в ней все
кадры с этой картинкой. Для картинки считаются ровно те способы, что приняты в WALL_RESTORE_V1:
  A   xbrz    xBRZ x4 продолженного кадра (wall_restore.xbrz_rgb);
  B2  esrgan  A плюс мелкая фактура Real-ESRGAN x4plus поправкой яркости (wall_restore.detail, DETAIL).
Классика - индексами PCK в боевой палитре (класс Classic), как её рисует игра. Альфа - всегда маска оригинала: ws.sil4_frame, у кадра со сквозными проёмами (ws.openings) -
wt.sil4_frame_open. Ни увеличитель, ни модель прозрачность не решают. B3 (anime), B1 и C здесь нет:
для стен они запрещены или не нужны.

B2 грузит Real-ESRGAN на видеокарту - запуск только через очередь gpuq. --no-model даёт один A без модели.
Готовые картинки пропускаются, прогон можно повторять.

  wall_final_render.py [--out census/walls/final_select/render] [--no-model] [--limit N] [--frames <tsv>]

--frames - другой список картинок того же вида (так перерисован MI_24_HIND_A после R-075, 15.10).

Выход: <out>/xbrz/<хэш>.png, <out>/esrgan/<хэш>.png (128x160 RGBA) и <out>/render.tsv
(хэш, кадр-представитель, сквозная, кадров, расхождение классики между кадрами строки). В мод ничего не кладётся.
"""
import argparse
import csv
import hashlib
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import numpy as np                                  # noqa: E402
from PIL import Image                               # noqa: E402
import map_mockup as mm                             # noqa: E402
import wall_restore as wr                           # noqa: E402
import wall_section as ws                           # noqa: E402

ENC = "utf-8-sig"
ROOT = os.path.dirname(os.path.dirname(HERE))
FRAMES = "census/walls/wall_render_frames.tsv"


class Classic:
    """Кадр классики так, как его рисует игра: индексы PCK подряд (xs.read_pck, R-075), цвет - боевая палитра
    мастер-мода delicious_regular при тени 0, индекс 0 прозрачен (R-043). Палитра листа art/TERRAIN
    (map_mockup.World.sprite) с ней расходится (R-030): одна и та же картинка в разных наборах вышла бы разной."""

    def __init__(self, world):
        import xcom_sprites as xs
        self.xs, self.world, self.cache = xs, world, {}
        pal = world.files.find(os.path.join("Resources", "Pals", "delicious_regular.pal"))
        if not pal:
            raise SystemExit("нет Resources/Pals/delicious_regular.pal")
        self.pal = np.array(xs.load_palette_file(pal)[:256], np.uint8)

    def idx(self, s, n):
        k = s.upper()
        if k not in self.cache:
            p = self.world.files.find(os.path.join("TERRAIN", s + ".PCK"))
            t = self.world.files.find(os.path.join("TERRAIN", s + ".TAB"))
            self.cache[k] = self.xs.read_pck(p, t) if p else []
        fr = self.cache[k]
        if n >= len(fr) or fr[n] is None:
            return None
        return np.array(fr[n], np.uint8)

    def rgba(self, idx):
        out = np.zeros(idx.shape + (4,), np.uint8)
        out[..., :3] = self.pal[idx]
        out[..., 3] = np.where(idx > 0, 255, 0)
        return out


def rows(path=FRAMES):
    with open(path, encoding=ENC, newline="") as f:
        return list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))


def parse_frame(t):
    s, n = t.rsplit(":", 1)
    return s, int(n)


def to_img(rgb, alpha):
    return Image.fromarray(np.clip(np.dstack([rgb, alpha]) + 0.5, 0, 255).astype(np.uint8), "RGBA")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="census/walls/final_select/render")
    ap.add_argument("--no-model", action="store_true", help="только A, модель не грузится")
    ap.add_argument("--limit", type=int, default=0, help="только первые N картинок (проба)")
    ap.add_argument("--frames", default=FRAMES, help="список картинок (колонки картинка, кадры), по умолчанию стены")
    a = ap.parse_args()
    os.chdir(ROOT)
    sys.stdout.reconfigure(encoding="utf-8")
    methods = ("xbrz",) if a.no_model else ("xbrz", "esrgan")
    for m in methods:
        os.makedirs(os.path.join(a.out, m), exist_ok=True)
    up = None
    if not a.no_model:
        import upscale_units as uu
        up = uu.Upscaler(wr.MODELS["esrgan"])
    world = mm.World()
    cl = Classic(world)
    rs = rows(a.frames)
    if a.limit:
        rs = rs[:a.limit]
    out_rows, done, skipped, t0 = [], 0, 0, time.time()
    for i, r in enumerate(rs):
        h = r["картинка"]
        frames = [parse_frame(t) for t in r["кадры"].split()]
        rep, first = None, None
        differ = 0
        for s, n in frames:
            ix = cl.idx(s, n)
            if ix is None:
                continue
            if rep is None:
                rep, first = (s, n), ix
            elif ix.shape != first.shape or not np.array_equal(ix, first):
                differ += 1
        if rep is None:
            out_rows.append([h, "", "", str(len(frames)), "нет кадра"])
            continue
        mask = first > 0
        first = cl.rgba(first)
        thru = bool(ws.openings(mask).any())
        out_rows.append([h, "%s:%d" % rep, "1" if thru else "0", str(len(frames)), str(differ)])
        paths = {m: os.path.join(a.out, m, h + ".png") for m in methods}
        if all(os.path.exists(p) for p in paths.values()):
            skipped += 1
            continue
        src, _m = wr.filled(Image.fromarray(first, "RGBA"))
        alpha = wr.alpha_of(mask, thru)
        base = wr.xbrz_rgb(src)
        to_img(base, alpha).save(paths["xbrz"])
        if up is not None:
            b2 = wr.detail(base, wr.model_rgb(up, src), wr.DETAIL[0], wr.DETAIL[1], alpha)
            to_img(b2, alpha).save(paths["esrgan"])
        done += 1
        if (i + 1) % 200 == 0:
            el = time.time() - t0
            print("картинок %d из %d (новых %d, готовых раньше %d), %.0f с" % (i + 1, len(rs), done, skipped, el),
                  flush=True)
    with open(os.path.join(a.out, "render.tsv"), "w", encoding=ENC, newline="") as f:
        f.write("\t".join(["картинка", "представитель", "сквозная", "кадров", "классика_расходится"]) + "\n")
        for row in out_rows:
            f.write("\t".join(row) + "\n")
    bad = sum(1 for row in out_rows if row[4] not in ("0",))
    print("готово: картинок %d, новых %d, готовых раньше %d, сквозных %d, строк с расхождением классики %d, %.0f с"
          % (len(out_rows), done, skipped, sum(1 for row in out_rows if row[2] == "1"), bad, time.time() - t0),
          flush=True)


if __name__ == "__main__":
    main()
