"""R-236: модель стенда обрушения грузится один раз на весь пул потоков.

collapse_pilot_run.model_fell зовут из ThreadPoolExecutor (scen --jobs 4). Без блокировки второй поток видел
словарь _model заполненным наполовину и падал KeyError 'barn' / 'bunker' (14.10). Тест зовёт model_fell
одновременно из нескольких потоков для каждого здания; контроль COLLAPSE_RUN_NOLOCK=1 подменяет блокировку
пустой - тест обязан упасть (гонка воспроизводится не всегда, поэтому контроль повторяется).

Запуск: py -3.13 tools/test_collapse_pilot_run.py
"""
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collapse_pilot_run as R  # noqa: E402

LABELS = ["barn", "bunker", "banditbarn1", "banditbarn2", "riceshed"]


class _NoLock:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def run_once():
    R._model.clear()
    with ThreadPoolExecutor(8) as ex:
        res = list(ex.map(lambda lb: R.model_fell(lb, []), LABELS * 4))
    return res


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if os.environ.get("COLLAPSE_RUN_NOLOCK") == "1":
        R._model_lock = _NoLock()
        # медленная загрузка расширяет окно гонки, как в настоящем прогоне
        orig = R._load_model

        def slow():
            if not R._model:
                threading.Event().wait(0.0)
            orig()
        R._load_model = slow
    bad = 0
    for _ in range(3):
        try:
            res = run_once()
        except KeyError as e:
            print("KeyError", e)
            bad += 1
            continue
        if any(r for r in res):
            print("ошибка: целое здание без снятых частей что-то роняет", res)
            bad += 1
    print("ok" if not bad else "FAIL %d из 3" % bad)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
