# -*- coding: utf-8 -*-
r"""Пересобрать паки из уже нарисованных листов - без видеокарты и без перерисовки.

    tools\hdart\.venv\Scripts\python.exe tools\hdart\repack_all.py --sheets art/TERRAIN --mod "Пиратки\Dioxine_XPiratez\user\mods\hd"

Нужно, когда поменялся build_pack (правила сборки кадра, цвет, края), а покраска осталась прежней:
листы `painted_x4.png` лежат в папке листов, GPU не требуется. Варианты (`painted_x4.v*.png`)
подхватываются сами, как при обычном прогоне.

`--sets A,B` - только эти наборы, `--pack-args "--chroma-lock 0"` - ключи build_pack.py,
`--dry-run` - только перечислить, что будет пересобрано.
"""
import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import build_pack                  # noqa: E402
import gen_hd                      # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description="пересборка паков из готовых листов")
    ap.add_argument("--sheets", required=True)
    ap.add_argument("--mod", required=True)
    ap.add_argument("--pack-path", default="TERRAIN", dest="pack_path")
    ap.add_argument("--sets", default="")
    ap.add_argument("--pack-args", default="", dest="pack_args")
    ap.add_argument("--dry-run", action="store_true", dest="dry_run")
    args = ap.parse_args(argv)

    only = {s.strip().upper() for s in args.sets.split(",") if s.strip()}
    names = sorted(n for n in os.listdir(args.sheets)
                   if n.upper().endswith(".PCK") and os.path.isdir(os.path.join(args.sheets, n)))
    if only:
        names = [n for n in names if n.upper() in only or n.upper()[:-4] in only]
    todo = [n for n in names if os.path.exists(os.path.join(args.sheets, n, "painted_x4.png"))]
    missing = [n for n in names if n not in todo]
    print("наборов с листом: %d%s" % (len(todo), (", без листа: %d" % len(missing)) if missing else ""))
    if args.dry_run:
        print(" ".join(todo))
        return 0

    extra = args.pack_args.split() if args.pack_args else []
    started, failed = time.time(), []
    for n, name in enumerate(todo):
        hd = os.path.join(args.sheets, name, "painted_x4.png")
        argv_pack = ["--sheets", args.sheets, "--set", name, "--hd", hd, "--mod", args.mod]
        if args.pack_path:
            argv_pack += ["--pack-path", args.pack_path]
        try:
            build_pack.main(argv_pack + extra)
        except Exception as e:
            failed.append("%s: %s" % (name, e))
            print("  ОШИБКА на %s: %s" % (name, e))
        el = time.time() - started
        left = el / (n + 1) * (len(todo) - n - 1)
        print("[%3d%%] %d/%d %s | %s, осталось ~%s"
              % ((n + 1) * 100 // len(todo), n + 1, len(todo), name,
                 gen_hd.human_time(el), gen_hd.human_time(left)), flush=True)
    print("готово: %d набор(ов) за %s%s"
          % (len(todo) - len(failed), gen_hd.human_time(time.time() - started),
             ("; с ошибками: " + "; ".join(failed)) if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
