#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Повторяющиеся кадры набора: убрать лишнее до рисования, размножить после.

В паках X-Piratez один и тот же рисунок часто лежит под несколькими номерами кадра.
У FORESTSWAMP.PCK из 132 полов РАЗНЫХ картинок только 98 - 34 кадра побайтовые копии.

Почему это важно, а не просто экономия. Движку нужен свой PNG на каждый индекс, но
картинка в них может быть одна. Если нарисовать копии порознь, вернутся РАЗНЫЕ рисунки
на клетки, которые в игре по замыслу одинаковы и стоят рядом, - на карте это видно
заплатками. Поэтому: рисуем только оригинал группы, потом копируем файл на её номера.

    ===== clean: убрать из папки с рисунками файлы-повторы =====

    py -3 tools\hdart\dupe_frames.py clean --set FORESTSWAMP.PCK --in "gpt_swamp\Результат"

    Если оригинал группы не нарисован, а его копия - да, файл не удаляется, а
    ПЕРЕИМЕНОВЫВАЕТСЯ в номер оригинала: работа не пропадает.
    --dry-run - только показать. --keep - не удалять, а сложить в подпапку _повторы.

    ===== spread: размножить готовые клетки пака на номера копий =====

    py -3 tools\hdart\dupe_frames.py spread --set FORESTSWAMP.PCK ^
        --mod "Пиратки\Dioxine_XPiratez\user\mods\hd"

    Запускать ПОСЛЕ tile_forge.py fit. Берёт <mod>\hd\<pack-path>\<набор>\<оригинал>.png
    и копирует под номерами копий.

Порядок работы целиком:
    1) clean   - выкинуть повторы из папки с рисунками
    2) tile_forge.py fit --in <та же папка> --mod <мод>
    3) spread  - размножить
    4) optimize_hd.py --only TERRAIN\<набор> --mode lossless
"""
import argparse
import hashlib
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import numpy as np                                  # noqa: E402
import tile_forge                                   # noqa: E402  (Sheet и разбор номера кадра)


def groups_of(sheet):
    """{оригинал: [все номера кадров с этой картинкой]} - по побайтовому сравнению."""
    first, groups = {}, {}
    for i in range(sheet.lay["count"]):
        key = hashlib.md5(np.asarray(sheet.frame(i)).tobytes()).hexdigest()
        head = first.setdefault(key, i)
        groups.setdefault(head, []).append(i)
    return groups


def canon_of(groups):
    return {i: head for head, members in groups.items() for i in members}


def drawn_files(in_dir):
    """{номер кадра: [файлы]} - номер разбирается ровно так же, как это сделает кузница."""
    out = {}
    for f in sorted(os.listdir(in_dir)):
        if not f.lower().endswith((".png", ".webp")):
            continue
        i = tile_forge.frame_number(f)
        if i is None:
            print("  пропуск (в имени нет явного номера): %s" % f)
            continue
        out.setdefault(i, []).append(f)
    return out


def cmd_clean(args):
    sheet = tile_forge.Sheet(args.sheets, args.set_name)
    groups = groups_of(sheet)
    canon = canon_of(groups)
    files = drawn_files(args.in_dir)
    bin_dir = os.path.join(args.in_dir, "_повторы")
    renamed = removed = kept = 0
    for i in sorted(files):
        head = canon.get(i, i)
        if head == i:
            kept += 1
            continue
        if head not in files:
            # оригинал не нарисован, а копия есть - не выбрасываем, а переименовываем
            src = files[i][0]
            ext = os.path.splitext(src)[1]
            dst = "%d%s" % (head, ext)
            print("  %s -> %s (оригинал группы не нарисован)" % (src, dst))
            if not args.dry_run:
                os.rename(os.path.join(args.in_dir, src), os.path.join(args.in_dir, dst))
            files[head] = [dst]
            renamed += 1
            continue
        for f in files[i]:
            print("  повтор кадра %d (тот же рисунок, что %d): %s" % (i, head, f))
            if args.dry_run:
                continue
            if args.keep:
                os.makedirs(bin_dir, exist_ok=True)
                shutil.move(os.path.join(args.in_dir, f), os.path.join(bin_dir, f))
            else:
                os.remove(os.path.join(args.in_dir, f))
            removed += 1
    where = "перенесено в _повторы" if args.keep else "удалено"
    print("оставлено %d, %s %d, переименовано %d%s"
          % (kept, where, removed, renamed, " (ничего не писал: --dry-run)" if args.dry_run else ""))
    return 0


def cmd_spread(args):
    sheet = tile_forge.Sheet(args.sheets, args.set_name)
    groups = groups_of(sheet)
    pack = os.path.join(args.mod, "hd", args.pack_path, args.set_name) if args.pack_path \
        else os.path.join(args.mod, "hd", args.set_name)
    if not os.path.isdir(pack):
        raise SystemExit("нет папки пака: %s" % pack)
    made = missing = 0
    for head, members in sorted(groups.items()):
        copies = [i for i in members if i != head]
        if not copies:
            continue
        src = os.path.join(pack, "%d.png" % head)
        if not os.path.exists(src):
            print("  кадр %d ещё не нарисован, его копии %s пропускаю"
                  % (head, ", ".join(str(i) for i in copies)))
            missing += len(copies)
            continue
        for i in copies:
            dst = os.path.join(pack, "%d.png" % i)
            print("  %d.png -> %d.png" % (head, i))
            if not args.dry_run:
                shutil.copyfile(src, dst)
            made += 1
    print("размножено %d, пропущено %d%s"
          % (made, missing, " (ничего не писал: --dry-run)" if args.dry_run else ""))
    return 0


def main():
    ap = argparse.ArgumentParser(description="повторяющиеся кадры набора: убрать и размножить")
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("clean", help="убрать из папки с рисунками файлы-повторы")
    c.add_argument("--sheets", default="art/TERRAIN")
    c.add_argument("--set", dest="set_name", required=True)
    c.add_argument("--in", dest="in_dir", required=True, help="папка с нарисованными плитками")
    c.add_argument("--keep", action="store_true", help="не удалять, а сложить в подпапку _повторы")
    c.add_argument("--dry-run", action="store_true", dest="dry_run")
    c.set_defaults(func=cmd_clean)

    s = sub.add_parser("spread", help="размножить готовые клетки пака на номера копий")
    s.add_argument("--sheets", default="art/TERRAIN")
    s.add_argument("--set", dest="set_name", required=True)
    s.add_argument("--mod", required=True, help="папка мода (та, где metadata.yml)")
    s.add_argument("--pack-path", default="TERRAIN", dest="pack_path",
                   help="подпапка пака; для не-террейна пусто")
    s.add_argument("--dry-run", action="store_true", dest="dry_run")
    s.set_defaults(func=cmd_spread)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
