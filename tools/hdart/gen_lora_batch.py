#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Пакетный прогон обученной LoRA по очереди наборов из переписи.

Тот же конвейер, что в gen_lora_test.py (DiffSynth + Qwen-Image-2.1 + наша LoRA), но не
ради сравнения, а ради работы: наборы берутся в порядке очереди docs\ART_STATUS.md, кадры
считаются по кадрам, а не по наборам, и прогон сам останавливается по бюджету времени.

Три вещи, ради которых это отдельный файл, а не ключ к gen_lora_test:

ОДИН ПРОЦЕСС на весь батч, модель грузится один раз (грабли R-018: подъём процесса на
каждый набор стоил шести часов из сорока).

ПРОДОЛЖЕНИЕ с места: уже нарисованные кадры пропускаются. Прогон можно оборвать в любой
момент и запустить снова - он доберёт остаток.

БЮДЖЕТ ВРЕМЕНИ: --hours. Проверяется перед каждым кадром, поэтому останов всегда на целом
кадре, а не посреди него.

    E:\train\.venv-train\Scripts\python.exe tools\hdart\gen_lora_batch.py ^
        --lora E:\train\lora\oxcehd\step-2540.safetensors --hours 4.5

Кладёт в art\TERRAIN\<НАБОР>.PCK\returned\lora\<кадр>.png - туда же, куда кладётся ответ
модели из любого другого источника, поэтому дальше набор собирается обычным tile_forge fit.
В пак и в мод НИЧЕГО не пишет: сборку делаем глазами, не вслепую.
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import gen_lora_test as glt                            # noqa: E402
import tile_forge as tf                                # noqa: E402
import build_dataset as bd                             # noqa: E402
import mirror_frames as mfr                            # noqa: E402
import link_frames as lfr                              # noqa: E402
import dupe_plan as dup                                # noqa: E402
from PIL import Image                                  # noqa: E402

ENC = "utf-8-sig"
MCD_DIRS = [os.path.join("Пиратки", "Dioxine_XPiratez", "user", "mods", "Piratez", "TERRAIN"),
            os.path.join("user", "mods", "XComFiles", "TERRAIN"),
            os.path.join("bin", "UFO", "TERRAIN")]
ZOOM = glt.ZOOM
PANEL = glt.PANEL
CAPTION = glt.CAPTION


def read_order(roadmap):
    """Порядок наборов из очереди. Место 1 - то, что видно на большинстве карт."""
    import csv
    with open(roadmap, encoding=ENC, newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    return [(r["набор"], int(r["клеток"]), int(r["рисовать"])) for r in rows]


def plan_set(sheets, name, out_root, by_frame=None, claimed=None):
    """Что рисовать в наборе: кадры с содержимым, которых ещё нет в ответе.

    claimed - множество хэшей картинок, уже заказанных или уже нарисованных ГДЕ УГОДНО.
    Одна картинка лежит в десятках паков, и заказывать её на каждый пак значит жечь
    время впустую и получать разные рисунки на клетки, одинаковые в оригинале (R-049).
    Копии разложит dupe_plan.spread после прогона."""
    try:
        sh = tf.Sheet(sheets, name + ".PCK")
    except Exception as e:                              # noqa: BLE001
        return None, None, "лист не читается: %s" % e
    hints = {}
    hp = os.path.join(sheets, name + ".PCK", "hints.json")
    if os.path.exists(hp):
        try:
            with open(hp, encoding=ENC) as f:
                hints = {int(k): v for k, v in json.load(f).items()}
        except Exception:                               # noqa: BLE001
            hints = {}
    out = os.path.join(out_root, name + ".PCK", "returned", "lora")
    # Зеркала не рисуем. Их два сорта, и первая версия фильтра видела только первый:
    # побайтовое отражение. Второй сорт - художник отразил ФОРМУ, а свет оставил с той же
    # стороны, и хэш такую пару не ловит вовсе (R-054). В ICEKING_RUINS таких 24 из 25 пар,
    # то есть почти весь повтор проходил мимо. Близнеца делает mirror_frames.py: поворот
    # плюс возврат своего света по яркости.
    mirrored = {j for _i, j, _e in mfr.silhouette_pairs(sh)}
    # Кадр, на который не ссылается ни одна запись MCD, игра не рисует никогда: террейн
    # берётся только через записи. Таких по всем наборам 2479 из 33046 (7.5%). Фильтр
    # включается, ТОЛЬКО если MCD найден - иначе отсеяли бы весь набор.
    live = None
    mcd = lfr.find_mcd(MCD_DIRS, name + ".PCK")
    if mcd:
        try:
            live = set()
            for r in lfr.read_records(mcd):
                live.update(r["frames"])
        except Exception:                               # noqa: BLE001
            live = None
    todo = []
    dupes = twins = 0
    for i in range(sh.lay["count"]):
        if tf.alpha_box(sh.frame(i)) is None:           # пустой кадр - рисовать нечего
            continue
        if i in mirrored:
            twins += 1
            continue
        if live is not None and i not in live:
            continue
        h = by_frame.get((name, i)) if by_frame else None
        if os.path.exists(os.path.join(out, "%d.png" % i)):
            if h is not None and claimed is not None:
                claimed.add(h)                          # нарисовано - значит уже занято
            continue
        if h is not None and claimed is not None:
            if h in claimed:
                dupes += 1
                continue
            claimed.add(h)
        todo.append(i)
    return sh, (todo, hints, out, dupes, twins), ""


def hms(sec):
    sec = int(max(0, sec))
    return "%d ч %02d м" % (sec // 3600, (sec % 3600) // 60)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lora", required=True)
    ap.add_argument("--sheets", default=os.path.join("art", "TERRAIN"))
    ap.add_argument("--roadmap", default=os.path.join("census", "roadmap.tsv"))
    ap.add_argument("--sets", default="", help="свой список через запятую вместо очереди")
    ap.add_argument("--hours", type=float, default=4.5, help="бюджет времени")
    ap.add_argument("--steps", type=int, default=20)
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--width", type=int, default=384)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--trigger", default="oxcehd, ")
    ap.add_argument("--models", default=r"E:\train\model_paths.json")
    ap.add_argument("--processor", default="")
    ap.add_argument("--vram-limit", dest="vram_limit", type=float, default=26.0)
    ap.add_argument("--rescan", action="store_true", help="пересчитать хэши листов")
    ap.add_argument("--plan-only", dest="plan_only", action="store_true",
                    help="показать план и выйти, модель не грузить")
    ap.add_argument("--max-plan", dest="max_plan", type=int, default=4000,
                    help="сколько кадров планировать вперёд; без срока - вся очередь")
    ap.add_argument("--out", default=os.path.join("art", "TERRAIN"))
    args = ap.parse_args()

    deadline = time.time() + args.hours * 3600.0

    if args.sets:
        order = [(s.strip().replace(".PCK", ""), 0, 0) for s in args.sets.split(",") if s.strip()]
    else:
        order = read_order(args.roadmap)

    # План строим ДО загрузки модели: сколько кадров всего, известно с первой минуты, и
    # оценка остатка есть сразу, а не после первого набора (грабли R-018).
    by_frame, _by_hash = dup.load(args.sheets, rescan=args.rescan)
    claimed = set()
    plans, total, saved, mirrors = [], 0, 0, 0
    for name, tiles, _draw in order:
        sh, plan, err = plan_set(args.sheets, name, args.out, by_frame, claimed)
        if err:
            continue
        todo, hints, out, dupes, twins = plan
        saved += dupes
        mirrors += twins
        if not todo:
            continue
        plans.append((name, sh, todo, hints, out, tiles))
        total += len(todo)
        if total > args.max_plan:                       # дальше считать смысла нет
            break

    print("наборов в работе: %d, кадров нарисовать: %d, бюджет %.1f ч"
          % (len(plans), total, args.hours), flush=True)
    print("не заказано повторно (та же картинка в другом паке): %d кадров" % saved, flush=True)
    print("не заказано зеркал (получим поворотом со своим светом): %d кадров" % mirrors,
          flush=True)
    for name, _sh, todo, _h, _o, tiles in plans[:8]:
        print("   %-16s %3d кадров, %7d клеток" % (name, len(todo), tiles), flush=True)
    if not plans:
        sys.exit("нечего рисовать - всё уже нарисовано или листы не читаются")

    if args.plan_only:
        return 0

    print("\nбюджет памяти карты: %.0f ГБ" % args.vram_limit, flush=True)
    pipe = glt.build_pipe(args.models, args.processor, args.vram_limit or None, offload=True)
    pipe.load_lora(pipe.dit, args.lora)
    print("LoRA загружена: %s\n" % os.path.basename(args.lora), flush=True)

    done = 0
    t0 = time.time()
    for name, sh, todo, hints, out, _tiles in plans:
        os.makedirs(out, exist_ok=True)
        print("=== %s: %d кадров -> %s" % (name, len(todo), out), flush=True)
        for i in todo:
            if time.time() > deadline:
                print("\nбюджет времени вышел, останавливаюсь на целом кадре", flush=True)
                print("нарисовано за прогон: %d кадров" % done, flush=True)
                return 0
            prompt = CAPTION.format(trigger=args.trigger, kind=bd.prompt_kind(sh, i),
                                    hint=hints.get(i) or "terrain tile")
            ctl = bd.make_control(sh, i, ZOOM, PANEL).resize(
                (args.width, args.height), Image.NEAREST)
            img = pipe(prompt, edit_image=[ctl], seed=args.seed, height=args.height,
                       width=args.width, num_inference_steps=args.steps)
            if isinstance(img, (list, tuple)):
                img = img[0]
            img.save(os.path.join(out, "%d.png" % i))
            done += 1
            spent = time.time() - t0
            left = (total - done) * (spent / done)
            print("  %-16s кадр %3d   %5.1f%%  осталось ~%s  (%.1f с/кадр)"
                  % (name, i, 100.0 * done / total, hms(min(left, deadline - time.time())),
                     spent / done), flush=True)
    print("\nвсё запланированное нарисовано: %d кадров за %s" % (done, hms(time.time() - t0)),
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
