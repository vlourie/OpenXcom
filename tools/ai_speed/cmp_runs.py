#!/usr/bin/env python3
"""Таблица вариантов: время боя и совпадение потоков записи с базой.

  py -3.13 tools/ai_speed/cmp_runs.py base var1 var2 ...

Потоки считаются заново по логам прогонов run_one.py; отпечаток настроек (cfg, env в [AIRECHEAD]) и реальное
время (ms, vms) из сравнения убраны - они различаются по определению. "=поток" - побайтно тот же, "!поток" - другой.
Флаг стенда пассивен, только если ВСЕ потоки "=" на станции и на городе (R-149), потом на 22 боях (R-113)."""
import hashlib, json, re, sys

from _common import OUT, ENC_R, probe_work

STREAMS = {
    "result": ("[AIRESULT]",),
    "decide": ("[AIDECIDE]",),
    "rec": ("[AIRECHEAD]", "[AIREC]", "[AIEXEC]", "[AIAFTER]", "[AITRACE]"),
    "cand": ("[AICAND]",),
    "state": ("[AISTATE]",),
    "path": ("[AIPATROL]",),
    "casualty": ("[AICASUALTY]",),
}
NORM = [(re.compile(r'"cfg":"[0-9a-f]+"'), '"cfg":""'), (re.compile(r'"env":\{[^}]*\}'), '"env":{}'),
        (re.compile(r" (ms|vms)=\d+"), ""), (re.compile(r"\bcfg=[0-9a-f]+"), "cfg=")]


def hashes(work, name):
    h = {k: [hashlib.sha256(), 0] for k in STREAMS}
    with open(work / ("var_" + name) / "openxcom.log", encoding=ENC_R, errors="replace") as f:
        for raw in f:
            body = raw.rstrip("\n").split("\t", 2)[-1]
            if not body.startswith("[AI"):
                continue
            for k, tags in STREAMS.items():
                if body.startswith(tags):
                    for rx, to in NORM:
                        body = rx.sub(to, body)
                    h[k][0].update(body.encode("utf-8", "replace") + b"\n")
                    h[k][1] += 1
    return {k: (v[0].hexdigest()[:12], v[1]) for k, v in h.items()}


def main():
    sys.stdout.reconfigure(encoding="utf-8")  # R-001
    names = sys.argv[1:]
    if len(names) < 2:
        sys.exit(__doc__)
    work = probe_work()
    base = hashes(work, names[0])
    bd = json.loads((OUT / (names[0] + ".json")).read_text(encoding=ENC_R))
    print(f"{'вариант':26} {'всего':>6} {'бой,с':>6} {'x':>5} {'ЦП,с':>6} {'вирт,с':>6} {'лог МБ':>6} {'строк':>6}"
          f"  потоки против {names[0]}")
    for n in names:
        d = json.loads((OUT / (n + ".json")).read_text(encoding=ENC_R))
        h = hashes(work, n)
        same = []
        for k in STREAMS:
            if not h[k][1] and not base[k][1]:
                continue
            same.append(("=" if h[k] == base[k] else "!") + k)
        x = bd["ms"] / d["ms"] if d["ms"] else 0
        print(f"{n:26} {d['wall']:6.1f} {d['ms'] / 1000:6.1f} {x:5.2f} {d.get('cpu', 0):6.1f} {d['vms'] / 1000:6.0f} "
              f"{d['log_mb']:6.1f} {d['log_lines']:6d}  {' '.join(same)}  {' '.join(d['env'])}"
              f"{'' if d['rec'] else ' rec=0'}{'' if d['path'] else ' path=0'}")


if __name__ == "__main__":
    main()
