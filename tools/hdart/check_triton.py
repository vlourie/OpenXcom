#!/usr/bin/env python3
"""check_triton.py - можно ли на этой машине считать flex attention.

Зачем. Qwen-Image-2.1 в DiffSynth считает внимание через torch flex attention, а он собирает
ядра компилятором Triton. Официальный Triton под Windows не выпускают, и обучение падает не
сразу, а на первом же шаге - после того как в память загрузилось 30 ГБ весов. Этот скрипт
делает ровно ту операцию, что падала, только на крошечных тензорах: полминуты вместо десяти.

    E:\\train\\.venv-train\\Scripts\\python.exe tools\\hdart\\check_triton.py

Если Triton не встал:
    E:\\train\\.venv-train\\Scripts\\python.exe -m pip install -U triton-windows
"""

import sys
import time


def main():
    import torch
    print("torch      %s" % torch.__version__)
    print("cuda       %s" % torch.version.cuda)
    if not torch.cuda.is_available():
        sys.exit("CUDA не видна - дальше смотреть нечего")
    cap = torch.cuda.get_device_capability(0)
    print("видеокарта %s, sm_%d%d" % (torch.cuda.get_device_name(0), cap[0], cap[1]))

    try:
        import triton
        print("triton     %s" % getattr(triton, "__version__", "версия не назвалась"))
    except ImportError:
        print("triton     НЕТ")
        sys.exit("\nTriton не установлен - flex attention работать не будет.\n"
                 "Ставить так:  python -m pip install -U triton-windows\n"
                 "Потом прогнать эту проверку ещё раз.")

    try:
        from torch.nn.attention.flex_attention import flex_attention, create_block_mask
    except ImportError:
        sys.exit("в этом torch нет flex_attention - нужен посвежее")

    print("\nпроба 1: flex attention без компиляции (это НЕ трогает Triton)...")
    dev = "cuda"
    b, h, s, d = 1, 4, 512, 64
    q = torch.randn(b, h, s, d, device=dev, dtype=torch.bfloat16)
    k = torch.randn(b, h, s, d, device=dev, dtype=torch.bfloat16)
    v = torch.randn(b, h, s, d, device=dev, dtype=torch.bfloat16)

    def mask_mod(_b, _h, qi, ki):
        return qi >= ki

    t0 = time.time()
    try:
        mask = create_block_mask(mask_mod, b, h, s, s, device=dev)
        out = flex_attention(q, k, v, block_mask=mask)
        torch.cuda.synchronize()
    except Exception as e:                                   # noqa: BLE001
        print("  НЕ РАБОТАЕТ: %s: %s" % (type(e).__name__, e))
        sys.exit("\nЭто даже не путь Triton - сломано что-то более основательное.")
    print("  ок за %.1f с, выход %s %s" % (time.time() - t0, tuple(out.shape), out.dtype))

    # Вот это и есть настоящая проверка. Обучение зовёт flex attention ЧЕРЕЗ torch.compile:
    # в трассировке падения было torch._inductor -> triton_hash_with_backend -> нет triton.
    # Без компиляции torch считает внимание запасной неслитой реализацией и Triton не трогает
    # вовсе - такая проба проходит даже там, где обучение падает.
    print("\nпроба 2: через torch.compile - ровно то, что делает обучение...")
    t0 = time.time()
    try:
        compiled = torch.compile(flex_attention)
        out = compiled(q, k, v, block_mask=mask)
        torch.cuda.synchronize()
    except Exception as e:                                   # noqa: BLE001
        print("  НЕ РАБОТАЕТ: %s: %s" % (type(e).__name__, e))
        sys.exit("\nОбучение упадёт на первом шаге так же. Варианты:\n"
                 "  1) подобрать triton-windows под версию torch выше;\n"
                 "  2) если жалуется на компилятор C++ - поставить Build Tools for Visual Studio\n"
                 "     (инструктору на Windows нужен cl.exe);\n"
                 "  3) считать без flex - тогда внимание считается другой веткой кода,\n"
                 "     и это НЕ то же самое, что при генерации.")

    print("  ок за %.1f с (сборка ядра)" % (time.time() - t0))
    if not torch.isfinite(out).all():
        sys.exit("в выходе NaN или бесконечности - ядро собралось, но считает мусор")

    t0 = time.time()
    for _ in range(5):
        out = compiled(q, k, v, block_mask=mask)
    torch.cuda.synchronize()
    print("  повторный вызов: %.1f мс" % ((time.time() - t0) * 200))
    print("\nflex attention собирается Triton'ом и считает. Обучение можно запускать.")


if __name__ == "__main__":
    main()
