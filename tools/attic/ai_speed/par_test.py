#!/usr/bin/env python3
"""N одинаковых скрытых боёв одновременно: сколько боёв в минуту даёт машина.

  py -3.13 tools/ai_speed/par_test.py --n 6 --tag p6base --build build-ai36
  py -3.13 tools/ai_speed/par_test.py --n 20 --tag p20p --build <опытная сборка> --unthrottle 1 --env OXCE_AI_FASTLOG=1

Итог - runs/par_<tag>.json и строка "боёв/мин". Ставить только когда видеокарта и стенд свободны."""
import argparse, json, subprocess, sys, time

from _common import HERE, OUT, ENC_R, ENC_W


def main():
    sys.stdout.reconfigure(encoding="utf-8")  # R-001
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--build", default="build-ai36")
    ap.add_argument("--mission", default="STR_VESSEL_BOMBER_SECTOID_ELITE")
    ap.add_argument("--seed", type=int, default=201)
    ap.add_argument("--unthrottle", type=int, default=0)
    ap.add_argument("--rec", type=int, default=1)
    ap.add_argument("--path", type=int, default=1)
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--env", action="append", default=[])
    ap.add_argument("--opt", action="append", default=[])
    ap.add_argument("--penv", action="append", default=[])
    a = ap.parse_args()

    procs, t0 = [], time.time()
    for i in range(a.n):
        cmd = [sys.executable, str(HERE / "run_one.py"), "--mission", a.mission, "--seed", str(a.seed),
               "--name", f"{a.tag}_{i:02d}", "--build", a.build, "--unthrottle", str(a.unthrottle),
               "--rec", str(a.rec), "--path", str(a.path), "--timeout", str(a.timeout)]
        for e in a.env:
            cmd += ["--env", e]
        for e in a.opt:
            cmd += ["--opt", e]
        for e in a.penv:
            cmd += ["--penv", e]
        procs.append(subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    for p in procs:
        p.wait()
    wall = time.time() - t0
    rows = []
    for i in range(a.n):
        f = OUT / f"{a.tag}_{i:02d}.json"
        if f.is_file():
            rows.append(json.loads(f.read_text(encoding=ENC_R)))
    ok = [r for r in rows if r["finished"] and r["ms"]]
    if not ok:
        sys.exit(f"{a.tag}: ни один бой не дошёл до конца")
    mean = lambda k: sum(r[k] for r in ok) / len(ok)
    out = {"tag": a.tag, "n": a.n, "ok": len(ok), "wall": round(wall, 1), "battle_s": round(mean("ms") / 1000, 1),
           "cpu_s": round(mean("cpu"), 1), "run_wall_s": round(mean("wall"), 1), "ecore": round(mean("ecore_share"), 2),
           "peak_mb": round(mean("peak_mb")), "per_min": round(len(ok) / wall * 60, 1)}
    (OUT / f"par_{a.tag}.json").write_text(json.dumps(out, ensure_ascii=False), encoding=ENC_W)
    print(f"{a.tag}: {len(ok)} из {a.n} боёв за {wall:.1f} с = {out['per_min']} боя/мин; бой {out['battle_s']} с, "
          f"процесс целиком {out['run_wall_s']} с, ЦП {out['cpu_s']} с, E-ядра {out['ecore']:.0%}, память {out['peak_mb']} МБ")


if __name__ == "__main__":
    main()
