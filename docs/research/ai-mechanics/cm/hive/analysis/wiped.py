"""HIVE COMMAND CORE V0: a commander change with no successor (new=-1): were there really no living members? And what became of the squad. Read only. Usage: wiped.py <dir>"""
import gzip
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
kv = re.compile(r"(\w+)=([^ ]*)")
lines = [ln.rstrip("\n").split("\t")[-1] for ln in gzip.open(Path(sys.argv[1]) / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace")]
members = {}
for s in lines:
    if s.startswith("[HIVESQUAD] id="):
        k = dict(kv.findall(s))
        members[k["id"]] = {re.sub(r"\D", "", m) for m in k["members"].split(",")}
falls = {}
for s in lines:
    if s.startswith("[AICASUALTY]"):
        k = dict(kv.findall(s))
        falls.setdefault(k["victim"], int(k["turn"]))
for s in lines:
    if s.startswith("[HIVECMD]") and " new=-1 " in s:
        k = dict(kv.findall(s))
        t = int(k["turn"])
        sq = k["squad"]
        alive = [m for m in members.get(sq, ()) if falls.get(m, 999) > t]
        print(s[:110], "| start members", sorted(members.get(sq, ())), "| not fallen yet", alive)
        for u in alive:
            for o in lines:
                if o.startswith("[HIVEORD]") and f" unit={u} " in o and f" turn={t} " in o and " state=CREATED" in o:
                    print("    still ordered:", o[:120])
                    break
