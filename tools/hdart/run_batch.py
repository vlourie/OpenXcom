# -*- coding: utf-8 -*-
r"""Весь батч в ОДНОМ процессе: модель грузится один раз, прогресс в процентах с оценкой времени.

    python tools\hdart\run_batch.py --all-sets ^
        --data    "Пиратки\Dioxine_XPiratez\user\mods\Piratez" ^
        --palette "Пиратки\Dioxine_XPiratez\user\mods\Piratez\Resources\Pals\delicious_regular.pal" ^
        --mod     "Пиратки\Dioxine_XPiratez\user\mods\hd" ^
        --sheets  art/TERRAIN --clean-big

Запускать венвовым питоном (tools\hdart\.venv\Scripts\python.exe): в нём torch и diffusers.

Зачем отдельно от gen_all.ps1: тот на каждый набор поднимал новый процесс python, и SDXL
грузился заново - дважды на набор (полы и объекты), примерно по 17 секунд. На 625 наборах
это около шести часов чистой загрузки моделей. Здесь процесс один, модель в памяти,
загрузка происходит ровно один раз за весь батч (gen_hd._PIPE).

Прогресс считается по КАДРАМ, а не по наборам: наборы от 1 до 155 кадров, и «набор 40 из 625»
ничего не говорит о времени. Число кадров в наборе известно заранее из .TAB, поэтому оценка
времени есть с самого начала и уточняется после каждого набора.

Прерывать можно в любой момент: набор, у которого уже есть пак, пропускается (если не --force).
"""

import argparse
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import xcom_sprites as xs          # noqa: E402
import extract_pck                 # noqa: E402
import gen_hd                      # noqa: E402
import build_pack                  # noqa: E402

ENC = "utf-8-sig"


def log_line(path, msg):
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = "%s  %s" % (stamp, msg)
    print(line, flush=True)
    try:
        with open(path, "a", encoding=ENC) as f:
            f.write(line + "\n")
    except OSError:
        pass


def frames_in(data, folder, name):
    """Сколько кадров в наборе — по .TAB, без распаковки. Нужно для оценки времени заранее."""
    for ext in (".TAB", ".tab"):
        p = os.path.join(data, folder, name + ext)
        if os.path.exists(p):
            try:
                return max(1, len(xs.read_tab(p)))
            except Exception:
                return 1
    return 1


def set_names(data, folder, wanted, all_sets):
    if wanted:
        return [w.upper() for w in wanted]
    if not all_sets:
        raise SystemExit("нужен --sets или --all-sets")
    d = os.path.join(data, folder)
    if not os.path.isdir(d):
        raise SystemExit("нет папки наборов: %s (проверь --data)" % d)
    # Регистр расширения в Windows не различается: один проход и уникальные имена,
    # иначе каждый набор попадёт в список дважды.
    seen = {}
    for f in os.listdir(d):
        stem, ext = os.path.splitext(f)
        if ext.lower() == ".pck":
            seen[stem.upper()] = True
    return sorted(seen)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--palette", default="")
    ap.add_argument("--mod", required=True)
    ap.add_argument("--sheets", default="hdart_sheets")
    ap.add_argument("--sets", default="", help="через запятую; иначе --all-sets")
    ap.add_argument("--all-sets", action="store_true", dest="all_sets")
    ap.add_argument("--units", action="store_true", help="UNITS вместо TERRAIN")
    ap.add_argument("--force", action="store_true", help="перекрасить набор, даже если пак уже есть")
    ap.add_argument("--clean-big", action="store_true", dest="clean_big",
                    help="после упаковки удалять painted_x16.png (30-50 МБ на набор)")
    ap.add_argument("--object-strength", type=float, default=0.55, dest="object_strength",
                    help="сила для объектов (второй проход); 0 = один проход")
    ap.add_argument("--gen-args", default="", dest="gen_args", help="лишние ключи для gen_hd.py")
    ap.add_argument("--pack-args", default="", dest="pack_args", help="лишние ключи для build_pack.py")
    ap.add_argument("--limit", type=int, default=0, help="взять только первые N наборов (проба)")
    args = ap.parse_args(argv)

    # Та же защита, что в gen_all.ps1 (RAKES.md, R-015): если --data указывает на мод, а --sheets
    # оставлен ванильным, листы мода затрут ванильные листы наборов с теми же именами.
    dn = args.data.replace("/", "\\").rstrip("\\").lower()
    if dn not in ("bin\\ufo", "bin\\tftd") and args.sheets == "hdart_sheets":
        raise SystemExit("--data указывает на мод (%s), значит нужен и свой --sheets: иначе листы "
                         "мода затрут ванильные (наборы DESERT, FOREST, ROADS и другие называются "
                         "одинаково). Для X-Piratez: --sheets art/TERRAIN" % args.data)

    folder = "UNITS" if args.units else "TERRAIN"
    pack_path = "" if args.units else "TERRAIN"
    names = set_names(args.data, folder, [s.strip() for s in args.sets.split(",") if s.strip()], args.all_sets)
    if args.limit:
        names = names[:args.limit]

    os.makedirs(args.sheets, exist_ok=True)
    log = os.path.join(args.sheets, "run_batch.log")

    # План: что красим, что пропускаем, сколько всего кадров
    plan, skipped, total = [], 0, 0
    for n in names:
        pack = os.path.join(args.mod, "hd", pack_path, n + ".PCK") if pack_path \
            else os.path.join(args.mod, "hd", n + ".PCK")
        if os.path.isdir(pack) and not args.force:
            skipped += 1
            continue
        c = frames_in(args.data, folder, n)
        plan.append((n, c))
        total += c
    log_line(log, "наборов %d, к покраске %d (%d уже готовы), кадров примерно %d"
             % (len(names), len(plan), skipped, total))
    if not plan:
        return 0

    gen_extra = args.gen_args.split() if args.gen_args else []
    pack_extra = args.pack_args.split() if args.pack_args else []
    started = time.time()
    done_frames = 0
    done_sets = 0
    failed = []

    for name, count in plan:
        set_pck = name + ".PCK"
        set_dir = os.path.join(args.sheets, set_pck)
        pct = done_frames * 100 // max(total, 1)
        eta = (time.time() - started) / done_frames * (total - done_frames) if done_frames else 0
        log_line(log, "[%3d%%] набор %d/%d  %s (%d кадров)%s"
                 % (pct, done_sets + 1, len(plan), set_pck, count,
                    "  осталось ~%s" % gen_hd.human_time(eta) if done_frames else ""))
        t_set = time.time()
        try:
            ex = ["--data", args.data, "--out", args.sheets, "--sets", "%s/%s" % (folder, set_pck)]
            if args.palette:
                ex += ["--palette", args.palette]
            extract_pck.main(ex)

            base = ["--sheets", args.sheets, "--set", set_pck] + gen_extra
            if args.object_strength > 0 and not args.units \
                    and "--only" not in gen_extra and "--strength" not in gen_extra:
                gen_hd.main(base + ["--only", "ground"])
                gen_hd.main(base + ["--only", "objects", "--strength", "%g" % args.object_strength])
            else:
                gen_hd.main(base)

            painted = os.path.join(set_dir, "painted_x4.png")
            pk = ["--sheets", args.sheets, "--set", set_pck, "--hd", painted, "--mod", args.mod]
            if pack_path:
                pk += ["--pack-path", pack_path]
            build_pack.main(pk + pack_extra)

            if args.clean_big:
                big = os.path.join(set_dir, "painted_x16.png")
                if os.path.exists(big):
                    mb = os.path.getsize(big) / (1024.0 * 1024.0)
                    os.remove(big)
                    log_line(log, "  убран painted_x16 (%.1f МБ)" % mb)
        except KeyboardInterrupt:
            log_line(log, "прервано пользователем на %s" % set_pck)
            break
        except Exception:
            failed.append(set_pck)
            log_line(log, "  ОШИБКА на %s:\n%s" % (set_pck, traceback.format_exc()))
        done_frames += count
        done_sets += 1
        log_line(log, "  %s готов за %s" % (set_pck, gen_hd.human_time(time.time() - t_set)))

    log_line(log, "готово: %d набор(ов) за %s%s"
             % (done_sets, gen_hd.human_time(time.time() - started),
                ("; с ошибками: " + ", ".join(failed)) if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
