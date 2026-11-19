"""Read only: why [AICASUALTY] of the AI side outnumbers the units on M3: repeats by victim, type and how, per run; and who the guards are against their anchors, from ra_eval's output. Usage: casualty_look.py <run>..."""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
for run in sys.argv[1:]:
    c = Counter()
    types = Counter()
    how = Counter()
    for s in read(run):
        if s.startswith("[AICASUALTY]"):
            k = kv(s)
            if k.get("vfaction") == "1" and int(k["turn"]) <= 8:
                c[k["victim"]] += 1
                types[k["type"]] += 1
                how[k["how"]] += 1
    print(run, "lines", sum(c.values()), "victims", len(c), "top", c.most_common(4), "how", dict(how), "types", types.most_common(5))
