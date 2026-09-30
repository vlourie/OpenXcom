#!/usr/bin/env python3
"""Сколько раз из N процесс стенда не вышел сам: завис на старте (боя нет) или на выходе (итог есть, процесс жив).

  py -3.13 tools/ai_speed/hang_count.py --tag a --build build-ai36 --tries 10 --timeout 60
  py -3.13 tools/ai_speed/hang_count.py --tag j --build <опытная сборка> --tries 10 --timeout 60 --env OXCE_AI_JOINLOAD=1

Контрольный опыт к R-150 (гонка SDL_KillThread в ~StartState): без починки зависает 1 из 10 и чаще,
с починкой - 0 из 10. Короткий бой (бомбардировщик) - чтобы попыток было много."""
import argparse, os, sys, time

from _common import ROOT


def main():
    sys.stdout.reconfigure(encoding="utf-8")  # R-001
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--mission", default="STR_VESSEL_BOMBER_SECTOID_ELITE")
    ap.add_argument("--seed", type=int, default=201)
    ap.add_argument("--build", required=True)
    ap.add_argument("--tries", type=int, default=8)
    ap.add_argument("--timeout", type=int, default=45)
    ap.add_argument("--env", action="append", default=[])
    a = ap.parse_args()
    os.environ["OXCE_AI_BUILD"] = a.build
    os.environ["OXCE_AI_RECORD"] = "1"
    os.environ["OXCE_AI_RECORD_PATH"] = "1"
    for kv in a.env:
        k, v = kv.split("=", 1)
        os.environ[k] = v
    sys.path.insert(0, str(ROOT / "tools"))
    import ai_probe

    count = {"вышел сам": 0, "завис на выходе": 0, "завис на старте": 0}
    for n in range(a.tries):
        t0 = time.time()
        res = ai_probe.run(None, 60, name="var_hc_" + a.tag, timeout=a.timeout, bot=True, seed=a.seed,
                           campaign="NoCodexCatZ.sav", mission=a.mission, careful=True, squad=8)
        wall = time.time() - t0
        what = "вышел сам" if wall < a.timeout - 1 else ("завис на выходе" if res.finished else "завис на старте")
        count[what] += 1
        print(f"{a.tag} попытка {n + 1}: {wall:.1f} с, {what}", flush=True)
    print(f"{a.tag}: " + ", ".join(f"{k} {v}" for k, v in count.items()) + f" из {a.tries}")


if __name__ == "__main__":
    main()
