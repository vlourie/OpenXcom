# -*- coding: utf-8 -*-
r"""Разносит подсказки из таблицы по наборам: floors.tsv -> <набор>\hints.json.

    tools\hdart\.venv\Scripts\python.exe tools\hdart\hints_apply.py --table floors_ru\floors.tsv --sheets art/TERRAIN

Берётся колонка «подсказка (eng)» - её читает gen_hd и кладёт в промпт кадра. Русская колонка
нужна людям: её правят, потом английскую переписывают под правку. Если русское описание есть, а
английского нет, строка попадает в `floors_todo.tsv` рядом с таблицей - её надо перевести.

`--dry-run` - только посчитать. `--clear` - стереть hints.json у наборов из таблицы (откат).
"""
import argparse
import csv
import json
import os
import sys

ENC = "utf-8-sig"


def main(argv=None):
    ap = argparse.ArgumentParser(description="подсказки из таблицы в hints.json")
    ap.add_argument("--table", required=True)
    ap.add_argument("--sheets", required=True)
    ap.add_argument("--dry-run", action="store_true", dest="dry_run")
    ap.add_argument("--clear", action="store_true", help="убрать hints.json у наборов из таблицы")
    args = ap.parse_args(argv)

    by_set, todo, empty = {}, [], 0
    with open(args.table, encoding=ENC, newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        cols = {c.strip(): c for c in (reader.fieldnames or [])}
        col_set = cols.get("набор") or cols.get("set")
        col_frame = cols.get("кадр") or cols.get("frame")
        col_ru = cols.get("что вижу (рус)") or cols.get("ru")
        col_en = cols.get("подсказка (eng)") or cols.get("en")
        if not (col_set and col_frame and col_en):
            raise SystemExit("в таблице нет колонок «набор», «кадр», «подсказка (eng)»")
        for row in reader:
            name = (row[col_set] or "").strip()
            if not name:
                continue
            en = (row[col_en] or "").strip()
            ru = (row[col_ru] or "").strip() if col_ru else ""
            if not en:
                empty += 1
                if ru:
                    todo.append((name, row[col_frame], ru))
                continue
            by_set.setdefault(name, {})[str(int(row[col_frame]))] = en

    print("наборов в таблице: %d, подсказок: %d, пустых: %d"
          % (len(by_set), sum(len(v) for v in by_set.values()), empty))
    if todo:
        out = os.path.join(os.path.dirname(os.path.abspath(args.table)), "floors_todo.tsv")
        with open(out, "w", encoding=ENC, newline="") as f:
            f.write("набор\tкадр\tчто вижу (рус)\n")
            for name, frame, ru in todo:
                f.write("%s\t%s\t%s\n" % (name, frame, ru))
        print("без английской подсказки, но с русской: %d -> %s" % (len(todo), out))
    if args.dry_run:
        return 0

    written = 0
    for name, frames in sorted(by_set.items()):
        set_dir = os.path.join(args.sheets, name)
        if not os.path.isdir(set_dir):
            print("  нет папки листа: %s" % set_dir)
            continue
        path = os.path.join(set_dir, "hints.json")
        if args.clear:
            if os.path.exists(path):
                os.remove(path)
                written += 1
            continue
        old = {}
        if os.path.exists(path):
            with open(path, encoding=ENC) as f:
                old = json.load(f)
        old.update(frames)
        # hints.json читает gen_hd обычным open(): спецификация в начале файла ломает json.load
        # (грабли R-036). Человек его не читает - пишем чистый UTF-8.
        with open(path, "w", encoding="utf-8") as f:
            json.dump(old, f, ensure_ascii=False, indent=1, sort_keys=True)
        written += 1
    print(("стёрто hints.json: %d" if args.clear else "записано hints.json: %d") % written)
    return 0


if __name__ == "__main__":
    sys.exit(main())
