"""TACTICAL STAGE 2: one unit's AI mode across turns - every [AIREC]: turn, decision n, position, TU, mode, slot, source, odds.

Shows whether the mode was rolled this decision (odds present) or carried over from an earlier one.

  py -3.13 -I fl_mode.py <log> <unit> [max turn]"""
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
U = int(sys.argv[2])
TMAX = int(sys.argv[3]) if len(sys.argv) > 3 else 99
for l in open(sys.argv[1], encoding="utf-8", errors="replace"):
    if not l.startswith("[AIREC] "):
        continue
    r = json.loads(l[8:])
    if r["unit"] != U or r["turn"] > TMAX:
        continue
    b, s = r["base"], r["state"]
    print(f"rec {r['rec']} turn {r['turn']} n={r['n']} pos={s['pos']} tu={s['tu']} morale={s.get('morale')} mode={b['mode']} "
          f"slot={b['slot']} src={b['src']} t={b['t']} to={b['to']} odds={b['reason'].get('odds')}")
