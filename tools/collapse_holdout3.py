"""Третий независимый набор карт для проверки модели обрушения (этап 0i, census/collapse/stage0i/holdout3.lock.txt).

Те же шаги, что у отложенных карт 0f (tools/collapse_holdout.py), в своём каталоге census/collapse/holdout3:
  py -3.13 tools/collapse_holdout3.py gen --seeds 22-25 [--jobs 2]   - бои стенда ИИ (невидимо, ai_probe.Hidden)
  py -3.13 tools/collapse_holdout3.py source                         - исходные карты"""
import sys
import types

import collapse_holdout as H

H.HOLD = "census/collapse/holdout3"


def main():
    cmd = sys.argv[1]
    if cmd == "gen":
        seeds, jobs = "22-25", 2
        args = sys.argv[2:]
        for i, t in enumerate(args):
            if t == "--seeds":
                seeds = args[i + 1]
            if t == "--jobs":
                jobs = int(args[i + 1])
        H.cmd_gen(types.SimpleNamespace(missions=H.MISSIONS, seeds=seeds, jobs=jobs, timeout=600))
    elif cmd == "source":
        H.cmd_source(types.SimpleNamespace())


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
