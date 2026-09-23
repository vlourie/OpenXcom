# -*- coding: utf-8 -*-
r"""Какие наборы террейна имеет смысл красить вариантами земли (`gen_hd.py --variants`).

    tools\hdart\.venv\Scripts\python.exe tools\hdart\list_ground_sets.py --sheets art/TERRAIN

Варианты земли получают только РОВНЫЕ ПОЛЫ, у которых по подсказке кадра (или по теме набора)
понятен вид грунта: трава, почва, песок, снег, камень, грязь, лесная подстилка. Сделанная земля
(дорога, бетон, плитка, пол базы) вариантов не получает - её клетки выложены осознанно.

Скрипт повторяет ровно тот же отбор, что делает gen_hd.plan_variants, но без модели и без рисования:
читает листы из `--sheets` (layout.json + original.png), подсказки из hints.py/hints.json и тему
набора (SUBJECTS -> террейн мода -> имя). Нужен, чтобы не гонять батч по всем 625 наборам Пираток:
у большинства (корабли, базы, подземелья, мебель) варьировать нечего, а перепаковка набора стоит
секунд и переписывает уже ужатые картинки.

Пишет рядом с листами:
  ground_sets.txt       - таблица: набор, сколько полов, какие виды грунта
  ground_sets_list.txt  - одной строкой через запятую, готово для --sets / -Sets

Дальше (видеокарта, после того как батч террейна закончится):
  $sets = (Get-Content art/TERRAIN\ground_sets_list.txt -Encoding UTF8 -Raw).Trim()
  tools\hdart\.venv\Scripts\python.exe tools\hdart\run_batch.py --sets $sets --force --clean-big `
      --data "Пиратки\Dioxine_XPiratez\user\mods\Piratez" `
      --palette "Пиратки\Dioxine_XPiratez\user\mods\Piratez\Resources\Pals\delicious_regular.pal" `
      --mod "Пиратки\Dioxine_XPiratez\user\mods\hd" --sheets art/TERRAIN `
      --gen-args "--variants 2 --only variants"
(--force здесь значит "не пропускай набор, у которого уже есть пак"; --only variants оставляет
базовую покраску и объекты как есть и рисует только варианты полов.)
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from PIL import Image          # noqa: E402
import xcom_sprites as xs      # noqa: E402
import gen_hd                  # noqa: E402
import subjects_terrain        # noqa: E402
from hints import hints_for    # noqa: E402

ENC = "utf-8-sig"


def subject_of(set_name, tsv_path):
    """Тема набора - как её берёт gen_hd: SUBJECTS -> террейн мода -> имя набора."""
    if set_name in gen_hd.SUBJECTS:
        return gen_hd.SUBJECTS[set_name], "SUBJECTS"
    subject, src = subjects_terrain.subject_for_set(set_name, tsv_path=(tsv_path or None))
    if subject:
        return subject, "террейн %s" % src
    subject, src = subjects_terrain.subject_by_name(set_name)
    if subject:
        return subject, "имя (образец %s)" % src
    return "", "нет темы"


def floors_with_kind(set_dir, info, subject):
    """[(кадр, вид грунта)] ровных полов, у которых вид грунта известен."""
    count = info["count"]
    frame_h = info["frame_h"]
    types = info.get("types") or [-1] * count
    ground = info.get("ground") or [False] * count
    hints = hints_for(info["set"])
    hints_file = os.path.join(set_dir, "hints.json")
    if os.path.exists(hints_file):
        with open(hints_file, encoding=ENC) as f:
            hints.update({int(k): v for k, v in json.load(f).items()})
    sheet = xs.Sheet(info["frame_w"], frame_h, count, info["columns"], info["margin"])
    original = Image.open(os.path.join(set_dir, "original.png")).convert("RGBA")
    by_subject = gen_hd.ground_kind(subject.split(":")[0]) if ":" in subject else None
    from_tail = False
    if by_subject is None and hasattr(gen_hd, "ground_kind_tail"):
        by_subject = gen_hd.ground_kind_tail(subject)
        from_tail = by_subject is not None
    out = []
    for i in range(count):
        if not ground[i] or types[i] != xs.MCD_FLOOR:
            continue
        box = sheet.cut(original, i, 1).getbbox()
        if box is None:                      # пустой кадр
            continue
        if box[1] < frame_h - 16 - 6:        # высокий: это не ровный пол
            continue
        kind = gen_hd.ground_kind(hints.get(i, "")) or by_subject
        if kind:
            out.append((i, kind))
    return out, from_tail


def main(argv=None):
    ap = argparse.ArgumentParser(description="наборы, у которых есть природные полы для вариантов")
    ap.add_argument("--sheets", default="art/TERRAIN", help="папка листов (та же, что у батча)")
    ap.add_argument("--set-terrains", default="", dest="set_terrains",
                    help="путь к set_terrains.tsv, если он не на месте по умолчанию")
    ap.add_argument("--min-floors", type=int, default=1, dest="min_floors",
                    help="брать набор, если таких полов хотя бы столько (по умолчанию 1)")
    args = ap.parse_args(argv)

    if not os.path.isdir(args.sheets):
        raise SystemExit("нет папки листов: %s" % args.sheets)

    rows, skipped, broken = [], [], []
    names = sorted(n for n in os.listdir(args.sheets)
                   if n.upper().endswith(".PCK") and os.path.isdir(os.path.join(args.sheets, n)))
    for name in names:
        set_dir = os.path.join(args.sheets, name)
        layout = os.path.join(set_dir, "layout.json")
        if not os.path.exists(layout) or not os.path.exists(os.path.join(set_dir, "original.png")):
            broken.append((name, "нет layout.json или original.png"))
            continue
        try:
            with open(layout, encoding=ENC) as f:
                info = json.load(f)
            info.setdefault("set", name)
            subject, src = subject_of(info["set"], args.set_terrains)
            floors, from_tail = floors_with_kind(set_dir, info, subject)
        except Exception as e:
            broken.append((name, "%s: %s" % (type(e).__name__, e)))
            continue
        kinds = sorted({k for _, k in floors})
        if len(floors) >= args.min_floors:
            rows.append((name, len(floors), kinds, src, from_tail))
        else:
            skipped.append(name)

    rows.sort(key=lambda r: (-r[1], r[0]))
    width = max([len(r[0]) for r in rows] + [10])
    tailed = [r for r in rows if r[4]]
    lines = ["# Наборы с природными полами: им есть что варьировать (%d из %d)" % (len(rows), len(names)),
             "# звёздочка - вид грунта взят из ХВОСТА темы (в голове его нет): %d наборов, их стоит"
             % len(tailed),
             "# просмотреть глазами - у корабля или помоста пол может не быть землёй", "",
             "# %-*s  %5s  %-28s  %s" % (width, "набор", "полов", "виды грунта", "откуда тема"), ""]
    for name, n, kinds, src, from_tail in rows:
        lines.append("%s%-*s  %5d  %-28s  %s" % ("*" if from_tail else " ", width - 1 if width > 1 else width,
                                                 name, n, " ".join(kinds), src))
    if broken:
        lines += ["", "# не удалось прочитать:"]
        lines += ["%-*s  %s" % (width, n, why) for n, why in broken]
    lines += ["", "# без природных полов (%d): %s" % (len(skipped), " ".join(skipped))]
    text = "\n".join(lines) + "\n"

    table = os.path.join(args.sheets, "ground_sets.txt")
    with open(table, "w", encoding=ENC) as f:
        f.write(text)
    listed = ",".join(r[0][:-4] if r[0].upper().endswith(".PCK") else r[0] for r in rows)
    list_path = os.path.join(args.sheets, "ground_sets_list.txt")
    with open(list_path, "w", encoding=ENC) as f:
        f.write(listed + "\n")

    print(text)
    print("таблица: %s" % table)
    print("список для --sets: %s" % list_path)
    print("наборов к покраске вариантов: %d из %d, полов всего: %d"
          % (len(rows), len(names), sum(r[1] for r in rows)))
    if tailed:
        print("из них вид грунта взят из хвоста темы (в таблице со звёздочкой): %d - %s"
              % (len(tailed), " ".join(r[0][:-4] for r in tailed)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
