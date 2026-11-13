"""Target selection cases in the D0 logs: every hostile attack decision with the aimed unit and the other units it saw.

  py -3.13 cases.py <out dir> <prefix> <tsv out>
For each hostile attack (act 6-14 with aim at a unit): the aimed unit and every other seen non-hostile unit with its 2D distance
from the shooter, hp/hpmax at the turn start, vehicle (weapon AUX_ACAR_*), kneel. Then a summary: how often a seen alternative
was at most 3 tiles farther and softer (not a vehicle while the aim is one) or more wounded (lower hp share)."""
import gzip
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
OUT, PREFIX, TSV = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
ATT = {6, 7, 8, 9, 10, 12, 13, 14}
KV = re.compile(r"(\w+)=(\([^)]*\)|\S+)")


def kv(body):
    return {k: v for k, v in KV.findall(body)}


def pos(s):
    return tuple(int(x) for x in s.strip("()").split(","))


rows = []
for d in sorted(OUT.iterdir()):
    if not d.name.startswith(PREFIX + "_"):
        continue
    st = {}
    dead = set()
    with gzip.open(d / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        for raw in f:
            body = raw.rstrip("\n").split("\t", 2)[-1]
            if body.startswith("[AISTATE] "):
                k = kv(body)
                if "unit" in k and "hp" in k:
                    hp, hm = k["hp"].split("/")
                    st[k["unit"]] = dict(f=int(k["faction"]), pos=pos(k["pos"]), hp=int(hp), hm=int(hm),
                                         veh=k.get("weapon", "").startswith("AUX_ACAR") or k.get("rh", "").startswith("INV_STEERING"),
                                         kneel=k.get("kneel", "0"), status=int(k["status"]), type=k.get("type", ""))
            elif body.startswith("[AICASUALTY] "):
                dead.add(kv(body).get("victim"))
            elif body.startswith("[AIDECIDE] "):
                k = kv(body)
                if k.get("side") != "1" or int(k["unit"]) < 1000000 or int(k["act"]) not in ATT:
                    continue
                aim = k.get("aim", "-1")
                if aim not in st or st[aim]["f"] == 1:
                    continue
                fr = pos(k["from"])
                seen = [u for u in k.get("seen", "-").split(",") if u in st and st[u]["f"] != 1 and u not in dead
                        and st[u]["status"] == 0]

                def dist(u):
                    p = st[u]["pos"]
                    return max(abs(p[0] - fr[0]), abs(p[1] - fr[1])) if False else round(((p[0] - fr[0]) ** 2 + (p[1] - fr[1]) ** 2) ** 0.5)
                a = st[aim]
                alts = [u for u in seen if u != aim]
                rows.append(dict(battle=d.name, turn=k["turn"], unit=k["unit"], act=k["act"], weapon=k.get("weapon", ""), aim=aim,
                                 adist=dist(aim), aveh=int(a["veh"]), ahp=a["hp"], ahm=a["hm"], af=a["f"],
                                 alts=";".join(f"{u}:{dist(u)}:{int(st[u]['veh'])}:{st[u]['hp']}/{st[u]['hm']}:f{st[u]['f']}" for u in alts),
                                 softer=int(a["veh"] and any(not st[u]["veh"] and st[u]["f"] == 0 and dist(u) <= dist(aim) + 3 for u in alts)),
                                 wounded=int(any(st[u]["f"] == 0 and st[u]["hp"] * a["hm"] < 0.6 * a["hp"] * st[u]["hm"]
                                                 and dist(u) <= dist(aim) + 3 for u in alts)),
                                 civ=int(a["f"] == 2 and any(st[u]["f"] == 0 and dist(u) <= dist(aim) + 3 for u in alts))))
cols = list(rows[0]) if rows else []
TSV.write_text("\t".join(cols) + "\n" + "".join("\t".join(str(r[c]) for c in cols) + "\n" for r in rows), encoding="utf-8-sig")
n = len(rows)
multi = sum(1 for r in rows if r["alts"])
print(f"hostile attacks at a unit: {n}, with another seen unit: {multi}")
print(f"aim is a vehicle: {sum(r['aveh'] for r in rows)}; of them a soft player unit seen at most 3 tiles farther: {sum(r['softer'] for r in rows)}")
print(f"a seen player unit with hp share < 0.6 of the aim's, at most 3 tiles farther: {sum(r['wounded'] for r in rows)}")
print(f"aim is a civilian while a player unit is at most 3 tiles farther: {sum(r['civ'] for r in rows)}")
print(f"aim faction: player {sum(1 for r in rows if r['af'] == 0)}, civilian {sum(1 for r in rows if r['af'] == 2)}")
bat = {}
for r in rows:
    bat.setdefault(r["battle"].split("_")[1], [0, 0, 0])
    b = bat[r["battle"].split("_")[1]]
    b[0] += 1
    b[1] += r["softer"]
    b[2] += r["civ"]
print("per scenario (attacks, softer, civ):", " ".join(f"{s}:{v[0]}/{v[1]}/{v[2]}" for s, v in sorted(bat.items())))
