#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Держать пакетный прогон живым до конца очереди или до общего срока.

gen_lora_batch сам по себе останавливается по бюджету времени и продолжает с места. Здесь
надстройка над ним: если процесс кончился раньше срока - неважно почему, - подождать и
поднять заново с ОСТАТКОМ общего бюджета, а не с полным. Нужно потому, что долгий прогон
гасят не только ошибки: обвязка снимает фоновые задачи при нехватке памяти в системе, и
в логе при этом нет ни сбоя, ни последней строки - просто обрыв на целом кадре.

    py -3 tools/hdart/keep_batch.py --lora E:\train\lora\oxcehd\step-2540.safetensors ^
        --hours 12

Останавливается сам в трёх случаях: вышел общий срок; очередь кончилась (gen_lora_batch
сказал "нечего рисовать"); три попытки подряд не дали НИ ОДНОГО кадра - значит поднимать
дальше бессмысленно, сломано что-то общее, и надо читать лог, а не жечь карту.

Дочерний процесс запускается списком аргументов и со своим окружением: PYTHONIOENCODING
обязателен, иначе python с перенаправленным выводом кодирует stdout в cp1252 и падает на
первой же строке с кириллицей (грабли R-001), а прогон на 12 часов умирает за секунду.
"""
import argparse
import io
import os
import subprocess
import sys
import time

ENC = "utf-8-sig"
DEAD = "нечего рисовать"


def drawn_in(log, start):
    """Сколько кадров дописалось в лог с позиции start - мера того, была ли работа."""
    try:
        with io.open(log, encoding="utf-8", errors="replace") as f:
            f.seek(start)
            return sum(1 for line in f if "с/кадр" in line)
    except OSError:
        return 0


def size_of(p):
    try:
        return os.path.getsize(p)
    except OSError:
        return 0


def stamp():
    return time.strftime("%H:%M:%S")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lora", required=True)
    ap.add_argument("--hours", type=float, default=12.0, help="общий срок на все попытки")
    ap.add_argument("--gap", type=float, default=60.0, help="пауза перед подъёмом, секунд")
    ap.add_argument("--log", default="gen_batch2.log")
    ap.add_argument("--python", default=r"E:\train\.venv-train\Scripts\python.exe")
    ap.add_argument("--script", default=os.path.join("tools", "hdart", "gen_lora_batch.py"))
    ap.add_argument("--extra", default="", help="ещё ключи дочернему, через пробел")
    args = ap.parse_args()

    deadline = time.time() + args.hours * 3600.0
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    tries = 0
    empty = 0
    total = 0
    while True:
        left = deadline - time.time()
        if left < 120:
            print("[%s] общий срок вышел, поднимать не буду" % stamp(), flush=True)
            break
        tries += 1
        before = size_of(args.log)
        cmd = [args.python, args.script, "--lora", args.lora,
               "--hours", "%.3f" % (left / 3600.0)]
        if args.extra:
            cmd += args.extra.split()
        print("[%s] попытка %d, остаток срока %.1f ч" % (stamp(), tries, left / 3600.0),
              flush=True)
        with io.open(args.log, "a", encoding="utf-8") as f:
            rc = subprocess.call(cmd, stdout=f, stderr=subprocess.STDOUT, env=env)
        made = drawn_in(args.log, before)
        total += made
        print("[%s] попытка %d кончилась: код %s, кадров за неё %d, всего %d"
              % (stamp(), tries, rc, made, total), flush=True)

        try:
            with io.open(args.log, encoding="utf-8", errors="replace") as f:
                f.seek(before)
                tail = f.read()
        except OSError:
            tail = ""
        if DEAD in tail:
            print("[%s] очередь кончилась - рисовать больше нечего" % stamp(), flush=True)
            break

        empty = empty + 1 if made == 0 else 0
        if empty >= 3:
            print("[%s] три попытки подряд без единого кадра - останавливаюсь, читай лог"
                  % stamp(), flush=True)
            break
        if time.time() + args.gap >= deadline:
            print("[%s] до срока меньше паузы, заканчиваю" % stamp(), flush=True)
            break
        time.sleep(args.gap)

    print("[%s] итого нарисовано за все попытки: %d кадров" % (stamp(), total), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
