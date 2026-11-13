"""MISSION-LEVEL TACTICS STAGE 2: the 8 battles side by side (read only): the result, the plans, who carried out the shared order, what it did to the modules and
to the base, who died where, and the kinds of what stopped a task. Usage: s2_all.py <out dir> <battle>..."""
import collections
import gzip
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
KV = re.compile(r"(\w+)=(\S+)")


def lines(d):
    with gzip.open(Path(d) / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        for ln in f:
            yield ln.rstrip("\n").split("\t")[-1]


def one(d):
    r = {"plans": [], "tasks": collections.Counter(), "shooters": collections.Counter(), "walkers": collections.Counter(), "hits": collections.Counter(), "broke": collections.Counter(),
         "protohits": 0, "protobroke": 0, "playerbroke": 0, "blast": 0, "done": [], "demolished": [], "base": {}, "release": collections.Counter(), "deaths": collections.Counter(), "res": {},
         "grid": "", "repos": 0, "fighters": set(), "planturn": [], "lefts": {}, "ownkill": 0, "ownhit": 0, "cells": collections.Counter()}
    task = None
    fighters = set()
    for s in lines(d):
        if s.startswith("[AIRESULT]"):
            r["res"] = dict(KV.findall(s))
        elif s.startswith("[AICASUALTY]"):
            k = dict(KV.findall(s))
            try:
                j = json.loads(s[s.index("{"):])
                k.update({a: str(b) for a, b in j.items()})
            except ValueError:
                pass
            if k.get("vfaction") in ("1", "HOSTILE", "hostile"):
                r["deaths"][int(k.get("turn", 0))] += 1
                if k.get("kfaction") == k.get("vfaction"):
                    r["ownkill"] += 1
        elif s.startswith("[AIMISSION]"):
            k = dict(KV.findall(s))
            w = k.get("what")
            if w == "plan":
                r["plans"].append((k["turn"], k["cell"], k["fighters"]))
                for f in k["fighters"].split(";"):
                    r["fighters"].add(f.split(">")[0])
                fighters = set(f.split(">")[0] for f in k["fighters"].split(";"))
            elif w == "objective":
                r["planturn"].append(f't{k["turn"]} {k["fac"][4:]} left={k["left"]} {k["why"]}')
            elif w == "task":
                r["tasks"][k["kind"]] += 1
                if k["kind"] == "shoot" and k.get("on") == "1":
                    r["shooters"][k["unit"]] += 1
                if k["kind"] == "walk" and k.get("on") == "1":
                    r["walkers"][k["unit"]] += 1
            elif w == "hit" and k.get("side") == "1" and k.get("module") == "1" and k.get("part") == "3":
                u = k["unit"]
                cell = tuple(int(x) // 10 for x in k["tile"].split(",")[:2])
                brk = int(k["tdmg"]) >= int(k["partarmor"])
                if u in fighters:
                    r["hits"][u] += 1
                    r["broke"][u] += brk
                    r["cells"][("order", cell)] += brk
                else:
                    r["protohits"] += 1
                    r["protobroke"] += brk
                    r["cells"][("proto", cell)] += brk
            elif w == "hit" and k.get("side") == "0" and k.get("module") == "1" and k.get("part") == "3":
                r["playerbroke"] += int(k["tdmg"]) >= int(k["partarmor"])
            elif w == "blast":
                r["blast"] += 1
            elif w == "done":
                r["done"].append(f't{k["turn"]} {k["fac"][4:]}')
            elif w == "demolished":
                r["demolished"].append(f'{k["type"][4:]}>{k["becomes"][4:]}')
            elif w == "base":
                r["base"][k["when"]] = {a: k[a] for a in ("facilities", "rubble", "labs", "workshops", "psilabs", "training", "stores", "quarters", "hangars")}
            elif w == "release":
                r["release"][k["why"]] += 1
            elif w == "repos":
                r["repos"] += 1
            elif w == "grid":
                r["grid"] = s
    return r


for name in sys.argv[2:]:
    r = one(Path(sys.argv[1]) / name)
    x = r["res"]
    print(f'== {name}: turn {x.get("turn")} livesoldiers {x.get("livesoldiers")} pdead {x.get("pdead")} pwounded {x.get("pwounded")} phplost {x.get("phplost")} hdead {x.get("hdead")}+{x.get("hout")} '
          f'hattacks {x.get("hattacks")} hmoves {x.get("hmoves")}')
    print("   objectives:", " | ".join(r["planturn"]) or "-")
    print("   tasks", dict(r["tasks"]), "fighters in plans", len(r["fighters"]), "repos", r["repos"], "release", dict(r["release"]))
    print("   shot orders by unit", dict(r["shooters"]), "| walk orders by unit", dict(r["walkers"]))
    print("   module hits by plan fighters", dict(r["hits"]), "broke", dict(r["broke"]), "| others hits", r["protohits"], "broke", r["protobroke"], "| player broke", r["playerbroke"], "| blasts", r["blast"])
    print("   broken by source and cell:", {f"{a[0]} {a[1][0]},{a[1][1]}": b for a, b in sorted(r["cells"].items()) if b})
    print("   done", r["done"], "demolished", r["demolished"])
    print("   base before", r["base"].get("before"))
    if r["base"].get("after") != r["base"].get("before"):
        print("   base after ", r["base"].get("after"))
    print("   hostile deaths by turn", dict(sorted(r["deaths"].items())))
