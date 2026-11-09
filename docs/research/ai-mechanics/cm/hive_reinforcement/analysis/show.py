"""All records of one unit in given turns: show.py run unit turn [turn ...]"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
run, unit, turns = sys.argv[1], sys.argv[2], set(sys.argv[3:])
for s in read(run):
    if s.startswith("[AIREC]"):
        try:
            j = json.loads(s[8:])
        except ValueError:
            continue
        if str(j["unit"]) == unit and str(j["turn"]) in turns:
            print("REC t", j["turn"], "n", j["n"], "rec", j["rec"], "tu", j["state"]["tu"], "pos", j["state"]["pos"], json.dumps(j.get("base"))[:420])
    elif s.startswith("[AIEXEC]"):
        try:
            j = json.loads(s[9:])
        except ValueError:
            continue
        if str(j.get("unit")) == unit and str(j.get("turn")) in turns:
            print("EXEC", s[:230])
    elif s.startswith(("[AIDECIDE]", "[HIVECC] event=ORDER", "[HIVECC] event=EXEC", "[AISTATE] aistart", "[HIVEORD]", "[AICASUALTY]")):
        k = kv(s)
        if (k.get("unit") == unit or k.get("victim") == unit) and k.get("turn") in turns:
            print(s[:330])
