#!/usr/bin/env python3
"""check_lora.py - не пустая ли обученная LoRA.

Зачем отдельная проверка. Лосс может всю ночь выглядеть нормальным, а на диск лечь файл из
нулей: в ai-toolkit это открытая бага #1054 (gradient checkpointing вместе с выгрузкой слоёв
даёт NaN в градиентах, и половина весов остаётся начальной). У LoRA матрица B нарочно
начинается с нулей, и если она нулём и осталась - никакого влияния на картинку не будет,
сколько ни зови её в генерации. Проверять надо ДО того, как радоваться.

    py -3 tools\\hdart\\check_lora.py E:\\train\\lora\\oxcehd
    py -3 tools\\hdart\\check_lora.py E:\\train\\lora\\oxcehd\\epoch-4.safetensors
"""

import os
import sys

try:
    from safetensors.torch import load_file
except ImportError:
    sys.exit("нет safetensors - запускать питоном из .venv-train")


def newest(path):
    if os.path.isfile(path):
        return path
    found = []
    for root, _dirs, names in os.walk(path):
        for n in names:
            if n.endswith(".safetensors"):
                found.append(os.path.join(root, n))
    if not found:
        sys.exit("в %s нет ни одного .safetensors" % path)
    found.sort(key=os.path.getmtime)
    return found[-1]


def side(key):
    k = key.lower()
    if "lora_b" in k or "lora_up" in k:
        return "B"
    if "lora_a" in k or "lora_down" in k:
        return "A"
    return None


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    path = newest(sys.argv[1])
    print("смотрю %s" % path)
    print("размер %.1f МБ" % (os.path.getsize(path) / 2 ** 20))
    sd = load_file(path)
    print("тензоров всего: %d" % len(sd))

    stat = {"A": [0, 0], "B": [0, 0]}      # [всего, из них нулевых]
    worst = []
    for k, v in sd.items():
        s = side(k)
        if s is None:
            continue
        n = float(v.float().abs().max())
        stat[s][0] += 1
        if n == 0.0:
            stat[s][1] += 1
        worst.append((n, s, k))

    if not worst:
        sys.exit("в файле нет ни одного слоя LoRA - это вообще не та модель?")

    for s in ("A", "B"):
        total, zero = stat[s]
        print("  %s: слоёв %d, нулевых %d" % (s, total, zero))

    worst.sort()
    print("самые маленькие по модулю:")
    for n, s, k in worst[:5]:
        print("  %-1s %-60s max|w| = %.3e" % (s, k[-60:], n))

    if stat["B"][0] and stat["B"][1] == stat["B"][0]:
        sys.exit("\nВСЕ матрицы B нулевые - обучение прошло впустую, LoRA ничего не изменит.\n"
                 "Это та самая бага с gradient checkpointing и выгрузкой слоёв. Пробовать без\n"
                 "--use_gradient_checkpointing_offload, а если не влезает - уменьшить -Rank.")
    if stat["B"][1]:
        print("\nчасть матриц B нулевая (%d из %d) - подозрительно, посмотреть csv с потерями"
              % (stat["B"][1], stat["B"][0]))
    else:
        print("\nLoRA живая: нулевых матриц B нет.")


if __name__ == "__main__":
    main()
