"""SIDE-FIRST COMBAT: did units marked dontReselect act again? Existing logs only. The one place the mark is logged is [AIPOSTWALK]: resel0 = the mark was free when the walk began, noresel = it is set when the walk ended. The line exists only for a walk with a final action, a turn, a charge or hiding, and the second pass's marks are not logged at all: the counts are a lower bound.
Log order: [AISCD] act, [AIEXEC] of the previous record, [AIDECIDE] of this action, the walk's [AIPOSTWALK], [AIEXEC] of this record. So a record counts as later only when its [AIDECIDE] comes after the mark; the D0 arm has no director and is the control of this reading. Marks clear at the next turn. args: zip:prefix:arm:missions ..."""
import gzip
import io
import json
import re
import sys
import zipfile
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
KV = re.compile(r"(\w+)=([^ ]*)")


def battle(z, label, c, ex):
    ls = [s.split("\t")[-1] for s in gzip.open(io.BytesIO(z.read(f"out/{label}/openxcom.log.gz")), "rt", encoding="utf-8", errors="replace").read().splitlines()]
    marked = {}
    pend = None
    later = None
    actors = set()
    for s in ls:
        if s.startswith("[AIPOSTWALK] "):
            d = dict(KV.findall(s))
            if d.get("side") != "1":
                continue
            c["postwalk"] += 1
            if d.get("resel0") == "0":
                c["walk_began_marked"] += 1
                ex.append((label, "шаг начат при метке", s[:170]))
            if d.get("noresel") == "1":
                c["marks_seen"] += 1
                marked.setdefault((d["turn"], d["unit"]), s[:90])
        elif s.startswith("[AISCD] "):
            j = json.loads(s[8:])
            e = j.get("ev")
            if e == "act":
                pend = None
                k = (str(j["turn"]), str(j["actor"]))
                if k in marked:
                    c["scd_act_after_mark"] += 1
                    c["scd_act_" + j["kind"]] += 1
                    actors.add(k)
                    pend = j
                    if sum(1 for x in ex if x[0] == label) < 2:
                        ex.append((label, "метка: " + marked[k], "затем: " + s[8:120]))
            elif e == "result" and pend is not None:
                if (j.get("spent") or 0) > 0:
                    c["scd_spent_after_mark"] += 1
                    c["scd_spent_tu"] += j.get("spent") or 0
                pend = None
        elif s.startswith("[AIDECIDE] "):
            later = None
            d = dict(KV.findall(s.split(" hu=")[0]))
            if d.get("side") == "1" and (d.get("turn"), d.get("unit")) in marked:
                later = d
        elif s.startswith("[AIEXEC] ") and later:
            x = json.loads(s[9:])
            d, later = later, None
            if str(x.get("unit")) == d["unit"]:
                c["records_after_mark"] += 1
                if (x.get("spent") or 0) > 0:
                    c["records_spent_after_mark"] += 1
    c["unit_turns_after_mark"] += len(actors)


for a in sys.argv[1:]:
    zp, prefix, arm, missions = a.rsplit(":", 3)
    z = zipfile.ZipFile(zp)
    for m in missions.split(","):
        c = Counter()
        ex = []
        for s_ in (1, 2, 3, 4):
            battle(z, f"{prefix}_{arm}_{m}_s{s_}", c, ex)
        print(f"{prefix} {arm} {m}:", dict(sorted(c.items())))
        for e in ex[:3]:
            print("   ", e)
