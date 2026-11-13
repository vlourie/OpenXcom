"""OPERATIONAL INTELLIGENCE: shared reading of one battle log. Attacks of the AI side with the target found by tile, facing of the target, the side of armour the rule gives. Read only."""
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mc"))
from lib import kv, read, tup  # noqa: E402

ATT = set(range(4, 21))
SIDE = {0: "front", 1: "front/right", 2: "right", 3: "rear/right", 4: "rear", 5: "rear/left", 6: "left", 7: "front/left"}


def rel_dir(dx, dy):
    """BattleUnit::damage: direction code of the hit from the voxels relative to the victim. dx, dy: shooter minus target, in tiles."""
    ax, ay = abs(dx), abs(dy)
    if ay > ax * 2:
        return 8 + 4 * (dy > 0)
    if ax > ay * 2:
        return 10 + 4 * (dx < 0)
    if dx < 0:
        return 13 if dy > 0 else 15
    return 11 if dy > 0 else 9


def side_code(shooter, target, facing):
    """0 front ... 4 rear, as the switch in BattleUnit::damage. None when straight above or below."""
    dx, dy = shooter[0] - target[0], shooter[1] - target[1]
    if dx == 0 and dy == 0:
        return None
    return (rel_dir(dx, dy) - facing) % 8


class Battle:
    """Log of one battle: per decision of the AI side, the state of the player's units as of the start of that AI turn."""

    def __init__(self, run):
        self.run = run
        self.L = read(run)
        self.units = {}  # id -> first state fields
        self.state = defaultdict(dict)  # turn -> unit -> kv of [AISTATE] aistart
        self.attacks = []
        self.casualties = []
        self.decisions = []
        self.seed = None
        self.mission = None
        self.result = None
        self.parse()

    def parse(self):
        dec = None
        recs = {}
        tally = defaultdict(lambda: defaultdict(int))
        acts = None
        moves = None
        pending = None
        for i, s in enumerate(self.L):
            if s.startswith("[AISTATE]"):
                k = kv(s)
                kind = s.split(" ", 2)[1]
                u = k.get("unit")
                if u and u not in self.units:
                    self.units[u] = k
                if kind == "aistart":
                    self.state[int(k["turn"])][u] = k
            elif s.startswith("[AIDECIDE]"):
                k = kv(s)
                k["line"] = i
                pending = k
                acts = moves = None
            elif s.startswith("[AICAND] moves=") and pending is not None:
                moves = s
            elif s.startswith("[AICAND] acts=") and pending is not None:
                acts = s
            elif s.startswith("[AIREC]") and pending is not None:
                try:
                    j = json.loads(s[8:])
                except ValueError:
                    pending = None
                    continue
                pending["rec"] = j["rec"]
                pending["src"] = (j.get("base") or {}).get("src")
                pending["dir"] = j["state"]["dir"]
                pending["hp"] = j["state"]["hp"]
                pending["morale"] = j["state"]["morale"]
                pending["moves_s"] = moves
                pending["acts_s"] = acts
                recs[j["rec"]] = pending
                if pending["side"] == "1":
                    self.decisions.append(pending)
                    if int(pending["act"]) in ATT and pending["aim"] != "-1":
                        tally[(pending["turn"], pending["to"])][pending["aim"]] += 1
                pending = None
            elif s.startswith("[AIEXEC]"):
                try:
                    j = json.loads(s[9:])
                except ValueError:
                    continue
                d = recs.get(j["rec"])
                if d is not None:
                    d["exec"] = j
            elif s.startswith("[AICASUALTY]"):
                self.casualties.append(kv(s))
            elif s.startswith("[AIRESULT]"):
                self.result = kv(s)
            elif s.startswith("[AIRECHEAD]") and self.seed is None:
                self.seed = json.loads(s[12:])["seed"]
        for d in self.decisions:
            if int(d["act"]) in ATT:
                t = tally.get((d["turn"], d["to"]))
                d["target"] = max(t, key=t.get) if t else d["aim"]
                self.attacks.append(d)


def acts_of(d):
    if not d.get("acts_s"):
        return []
    try:
        return json.loads(d["acts_s"].split(" list=", 1)[1])
    except (IndexError, ValueError):
        return []


def moves_of(d):
    if not d.get("moves_s"):
        return {}
    out = {}
    for c in d["moves_s"].split(" list=", 1)[1].split(";"):
        try:
            p, tu = c.split(":")
            x, y, z = p.split(".")
            out[(int(x), int(y), int(z))] = int(tu)
        except ValueError:
            pass
    return out


def pos(p):
    return tup(p)
