"""Крупные варианты картинок сайта для экранов 2К и 4К.

В wwwroot лежат картинки ровно того размера, в каком их показывает разметка на обычном экране
(1280x800 у первого экрана, 960x540 у обложек). На экране с масштабом браузер просит вдвое
больше пикселей, не находит их и растягивает — картинка «плывёт». Скрипт кладёт рядом файл
<имя>@2x.jpg из исходника art/promo (1792x1120), а разметка отдаёт оба через srcset: браузер
берёт тот, который подходит его экрану.

Вариант исходника скрипт ищет сам — сравнивает каждый с тем, что уже лежит в wwwroot, и берёт
ближайший: какой номер выбрал Vitali, в репозитории не записано.

    python tools/site_art_2x.py            собрать
    python tools/site_art_2x.py --dry-run  только показать, что нашлось
"""
import argparse
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMO = os.path.join(ROOT, "art", "promo")
WWW = os.path.join(ROOT, "portal", "src", "Xp.Portal", "wwwroot", "img")

# цель -> (папка вариантов, ширина и высота обычной картинки, бюджет крупной в КБ)
TARGETS = {
    os.path.join(WWW, "hero.jpg"): ("site_hero", 1280, 800, 700),
    os.path.join(WWW, "mods", "piratez.jpg"): ("mod_piratez", 960, 540, 600),
    os.path.join(WWW, "mods", "hd.jpg"): ("mod_hd", 960, 540, 600),
}


def cover(im, w, h):
    """Обрезка по центру под нужные стороны, затем масштаб — как в gen_promo.cover."""
    from PIL import Image
    k = max(w / im.width, h / im.height)
    im = im.resize((max(w, round(im.width * k)), max(h, round(im.height * k))), Image.LANCZOS)
    x, y = (im.width - w) // 2, (im.height - h) // 2
    return im.crop((x, y, x + w, y + h))


def jpeg_under(im, path, kb):
    """Самое высокое качество JPEG, которое укладывается в бюджет."""
    for q in range(92, 49, -3):
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=q, optimize=True, progressive=True)
        if buf.tell() <= kb * 1024:
            break
    with open(path, "wb") as f:
        f.write(buf.getvalue())
    return q, buf.tell()


def closest(variants, target, w, h):
    """Вариант, из которого собрана лежащая в wwwroot картинка: по средней разнице пикселей."""
    from PIL import Image, ImageChops, ImageStat
    with Image.open(target) as t:
        have = t.convert("RGB")
        best, score = None, None
        for path in variants:
            with Image.open(path) as v:
                made = cover(v.convert("RGB"), w, h)
            diff = ImageStat.Stat(ImageChops.difference(have, made)).mean
            mean = sum(diff) / len(diff)
            if score is None or mean < score:
                best, score = path, mean
    return best, score


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    from PIL import Image

    for target, (slot, w, h, kb) in TARGETS.items():
        folder = os.path.join(PROMO, slot)
        if not os.path.isdir(folder):
            print("нет папки вариантов: %s" % folder)
            continue
        variants = [os.path.join(folder, f) for f in sorted(os.listdir(folder)) if f.endswith(".png")]
        if not variants:
            print("нет вариантов в %s" % folder)
            continue
        if not os.path.exists(target):
            print("нет картинки %s" % target)
            continue
        src, score = closest(variants, target, w, h)
        with Image.open(src) as im:
            sw, sh = im.size
        # крупная картинка ровно такая, какую даёт исходник: выдумывать пиксели незачем
        k = min(sw / w, sh / h, 2.0)
        bw, bh = round(w * k), round(h * k)
        out = os.path.splitext(target)[0] + "@2x.jpg"
        print("%s <- %s (расхождение %.1f из 255), %dx%d -> %dx%d"
              % (os.path.relpath(out, ROOT), os.path.basename(src), score, sw, sh, bw, bh))
        if args.dry_run:
            continue
        with Image.open(src) as im:
            big = cover(im.convert("RGB"), bw, bh)
        q, size = jpeg_under(big, out, kb)
        print("    качество %d, %d КБ (бюджет %d)" % (q, size // 1024, kb))


if __name__ == "__main__":
    sys.exit(main())
