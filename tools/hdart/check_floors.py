# -*- coding: utf-8 -*-
r"""Проверка, как испеклись ПОЛЫ: поле из одной клетки, как его кладёт движок, плюс отличие по цвету.

    tools\hdart\.venv\Scripts\python.exe tools\hdart\check_floors.py --mod "Пиратки\Dioxine_XPiratez\user\mods\hd" --sheets art/TERRAIN

Для каждого набора берётся его главный ровный пол (самый большой по площади; `--per-set 2` - два),
из пака мода читается готовый HD-кадр и раскладывается полем `--cells` x `--cells` ровно тем узором,
которым его кладёт движок (`build_pack.ground_field`). На таком поле сразу видно то, ради чего
проверка и делается: швы по краю ромба, решётка одинаковых клеток, пятна другого цвета.

Рядом считается отличие по цвету от оригинала (та же мера, что печатает build_pack: разница a/b в
CIELAB под маской оригинала, яркость не в счёт - её художник вправе менять). Наборы в листах идут
сначала худшие, чтобы глазами смотреть не все 625, а первые страницы.

Пишет в `--out` (по умолчанию `floors_check`):
  floors_check.txt      - таблица: набор, кадр, отличие, откуда взялась тема набора
  fields\<набор>_<кадр>.png - поле каждого пола в полном размере (смотреть подозрительные)
  sheet_01.png ...      - листы по 12 полей, худшие первыми

Видеокарта не нужна; на 625 наборах - минуты.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import numpy as np                   # noqa: E402
from PIL import Image, ImageDraw     # noqa: E402
import xcom_sprites as xs            # noqa: E402
import build_pack                    # noqa: E402
import gen_hd                        # noqa: E402
import subjects_terrain              # noqa: E402

ENC = "utf-8-sig"


def subject_of(set_name):
    """Тема набора и откуда она взялась - как это делает gen_hd."""
    if set_name in gen_hd.SUBJECTS:
        return gen_hd.SUBJECTS[set_name], "SUBJECTS"
    subject, src = subjects_terrain.subject_for_set(set_name)
    if subject:
        return subject, "террейн %s" % src
    subject, src = subjects_terrain.subject_by_name(set_name)
    if subject:
        return subject, "имя (%s)" % src
    return "", "ЗАГЛУШКА"


def main(argv=None):
    ap = argparse.ArgumentParser(description="поля полов из готового пака: швы, решётка, цвет")
    ap.add_argument("--mod", required=True, help="мод с паками, например Пиратки\\...\\user\\mods\\hd")
    ap.add_argument("--sheets", default="art/TERRAIN", help="папка листов (там layout.json и оригиналы)")
    ap.add_argument("--out", default="art/_review/floors_check")
    ap.add_argument("--pack-path", default="TERRAIN", dest="pack_path")
    ap.add_argument("--sets", default="", help="только эти наборы, через запятую (иначе все)")
    ap.add_argument("--per-set", type=int, default=1, dest="per_set", help="сколько полов брать с набора")
    ap.add_argument("--cells", type=int, default=4, help="поле cells x cells клеток")
    ap.add_argument("--tile-width", type=int, default=340, dest="tile_width", help="ширина поля на листе")
    ap.add_argument("--limit", type=int, default=120, help="сколько худших положить на листы")
    ap.add_argument("--per-page", type=int, default=12, dest="per_page")
    args = ap.parse_args(argv)

    fields_dir = os.path.join(args.out, "fields")
    os.makedirs(fields_dir, exist_ok=True)
    only = {s.strip().upper() for s in args.sets.split(",") if s.strip()}
    names = sorted(n for n in os.listdir(args.sheets)
                   if n.upper().endswith(".PCK") and os.path.isdir(os.path.join(args.sheets, n)))
    if only:
        names = [n for n in names if n.upper() in only or n.upper()[:-4] in only]

    rows, missing = [], []
    for name in names:
        set_dir = os.path.join(args.sheets, name)
        layout = os.path.join(set_dir, "layout.json")
        pack_dir = os.path.join(args.mod, "hd", args.pack_path, name) if args.pack_path \
            else os.path.join(args.mod, "hd", name)
        if not os.path.exists(layout) or not os.path.isdir(pack_dir):
            missing.append((name, "нет листа или пака"))
            continue
        with open(layout, encoding=ENC) as f:
            info = json.load(f)
        info.setdefault("set", name)
        count, fw, fh = info["count"], info["frame_w"], info["frame_h"]
        types = info.get("types") or [-1] * count
        ground = info.get("ground") or [False] * count
        sheet = xs.Sheet(fw, fh, count, info["columns"], info["margin"])
        original = Image.open(os.path.join(set_dir, "original.png")).convert("RGBA")
        subject, src = subject_of(info["set"])

        floors = []
        for i in range(count):
            if types[i] != xs.MCD_FLOOR or not ground[i]:
                continue
            frame = sheet.cut(original, i, 1)
            box = frame.getbbox()
            if box is None or box[1] < fh - 16 - 6:      # пустой или высокий: это не ровный пол
                continue
            area = float(np.asarray(frame.split()[3], np.float64).sum()) / 255.0
            floors.append((area, i, frame))
        if not floors:
            continue
        floors.sort(key=lambda t: -t[0])

        for _, i, orig in floors[:max(1, args.per_set)]:
            png = os.path.join(pack_dir, "%d.png" % i)
            if not os.path.exists(png):
                missing.append((name, "нет кадра %d в паке" % i))
                continue
            hd = Image.open(png).convert("RGBA")
            k = max(1, hd.width // fw)
            big = orig.resize((fw * k, fh * k), Image.NEAREST)
            if hd.size != big.size:
                hd = hd.resize(big.size, Image.LANCZOS)
            mask = big.split()[3].point(lambda v: 255 if v > 128 else 0)
            err = build_pack.chroma_error(hd, big, mask)
            field = build_pack.ground_field([hd], args.cells, k).convert("RGB")
            path = os.path.join(fields_dir, "%s_%d.png" % (name[:-4] if name.upper().endswith(".PCK") else name, i))
            field.save(path)
            rows.append({"set": name, "frame": i, "err": err, "src": src, "field": path})

    rows.sort(key=lambda r: -r["err"])

    lines = ["# Поля полов из готового пака: отличие по цвету от оригинала (a/b в CIELAB), худшие сверху",
             "# больше 15 - цвет ушёл заметно; смотри поле в %s" % fields_dir, "",
             "%-34s %6s %8s  %s" % ("набор", "кадр", "отличие", "откуда тема")]
    for r in rows:
        lines.append("%-34s %6d %8.1f  %s" % (r["set"], r["frame"], r["err"], r["src"]))
    if missing:
        lines += ["", "# пропущено:"] + ["%-34s %s" % (n, why) for n, why in missing]
    table = os.path.join(args.out, "floors_check.txt")
    with open(table, "w", encoding=ENC) as f:
        f.write("\n".join(lines) + "\n")

    # листы: худшие первыми, подписи латиницей (в картинке нет кириллического шрифта)
    pages, picked = 0, rows[:args.limit] if args.limit > 0 else rows
    cols = 4
    label_h = 16
    for start in range(0, len(picked), args.per_page):
        chunk = picked[start:start + args.per_page]
        thumbs = []
        for r in chunk:
            im = Image.open(r["field"])
            w = args.tile_width
            im = im.resize((w, max(1, im.height * w // im.width)), Image.LANCZOS)
            tile = Image.new("RGB", (w, im.height + label_h), (32, 32, 32))
            tile.paste(im, (0, label_h))
            d = ImageDraw.Draw(tile)
            src = r["src"]
            tag = "SUBJ" if src.startswith("SUBJECTS") else ("TERR" if src.startswith("террейн") else
                                                             ("NAME" if src.startswith("имя") else "NONE"))
            d.text((4, 3), "%s #%d  dE %.1f  %s" % (r["set"][:-4], r["frame"], r["err"], tag), fill=(255, 235, 120))
            thumbs.append(tile)
        rows_n = (len(thumbs) + cols - 1) // cols
        tw = max(t.width for t in thumbs)
        th = max(t.height for t in thumbs)
        page = Image.new("RGB", (cols * (tw + 8) + 8, rows_n * (th + 8) + 8), (32, 32, 32))
        for n, t in enumerate(thumbs):
            page.paste(t, (8 + (n % cols) * (tw + 8), 8 + (n // cols) * (th + 8)))
        pages += 1
        page.save(os.path.join(args.out, "sheet_%02d.png" % pages))

    print("полов проверено: %d в %d наборах" % (len(rows), len({r["set"] for r in rows})))
    if rows:
        print("отличие: худшее %.1f (%s), среднее %.1f; больше 15 у %d полов"
              % (rows[0]["err"], rows[0]["set"], sum(r["err"] for r in rows) / len(rows),
                 sum(1 for r in rows if r["err"] > 15)))
    print("таблица: %s" % table)
    print("листы: %s\\sheet_01.png ... (%d)" % (args.out, pages))
    if missing:
        print("пропущено наборов/кадров: %d - смотри конец таблицы" % len(missing))
    return 0


if __name__ == "__main__":
    sys.exit(main())
