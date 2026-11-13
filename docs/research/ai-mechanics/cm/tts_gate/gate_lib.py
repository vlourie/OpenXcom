"""NATURAL GATE, read only: one battle log as decisions with the engine's own candidate lists, and where every unit stood at any line.
lof in the acts list is TileEngine::canTargetUnit from the unit's real origin (AiCandidates.cpp:126), the solver's lineNow without the visibility part."""
import bisect
import json
import re

KV = re.compile(r"(\w+)=([^ ]*)")
POS = re.compile(r"\((-?\d+),(-?\d+),(-?\d+)\)")
SHOT = {7, 8, 9}
ENEMY_BASE = 1000000


def kv(s):
    return dict(KV.findall(s))


def tup(p):
    m = POS.match(p)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def lane(p, a, b):
    """solver's nearLine: position k along a-b and the squared distance from it; flat, as the solver's is"""
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = dx * dx + dy * dy
    if n <= 0:
        return -1, 99.0
    k = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / n
    ex, ey = a[0] + k * dx - p[0], a[1] + k * dy - p[1]
    return k, ex * ex + ey * ey


def near_line(p, a, b):
    k, d2 = lane(p, a, b)
    return 0 < k < 1 and d2 <= 2.25


def cheb(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


class Battle:
    def __init__(self, lines):
        self.acts_raw, self.moves_raw, self.exec = {}, {}, {}
        self.dec = []
        self.hist = {}
        self.fac = {}
        self.tts = []
        self.acts_cache = {}
        for i, s in enumerate(lines):
            if s.startswith("[AICAND] acts="):
                h = s[14:s.index(" ", 14)]
                self.acts_raw.setdefault(h, s[s.index("list=") + 5:])
            elif s.startswith("[AICAND] moves="):
                h = s[15:s.index(" ", 15)]
                self.moves_raw.setdefault(h, s[s.index("list=") + 5:])
            elif s.startswith("[AIEXEC]"):
                j = json.loads(s[9:])
                self.exec[j["rec"]] = j
                if "pos" in j:
                    self.mark(int(j["unit"]), i, tuple(j["pos"]), j.get("tu"), None)
            elif s.startswith("[AIREC]"):
                j = json.loads(s[8:])
                st = j["state"]
                c = j.get("cand") or {}
                base = j.get("base") or {}
                d = {"i": i, "rec": j["rec"], "turn": j["turn"], "side": j["side"], "unit": j["unit"], "n": j["n"], "pos": tuple(st["pos"]), "tu": st["tu"], "kneel": st.get("kneel", 0),
                     "acts": c.get("acts"), "moves": c.get("moves"), "t": base.get("t"), "to": tuple(base["to"]) if base.get("to") else None, "w": base.get("w"), "id": base.get("id"), "src": base.get("src")}
                self.dec.append(d)
                if j["side"] == 1:
                    self.fac[j["unit"]] = 1
                self.mark(j["unit"], i, d["pos"], st["tu"], False)
            elif s.startswith("[AISTATE]"):
                k = kv(s)
                if "unit" in k and "pos" in k:
                    u = int(k["unit"])
                    self.fac[u] = int(k.get("faction", self.fac.get(u, 0)))
                    self.mark(u, i, tup(k["pos"]), int(k["tu"]) if "tu" in k else None, k.get("status", "0") != "0")
            elif s.startswith("[AICASUALTY]"):
                k = kv(s)
                self.mark(int(k["victim"]), i, tup(k["pos"]), None, True)
            elif s.startswith("[AITTS]"):
                self.tts.append((i, json.loads(s[8:])))
        self.by_unit = {}
        for d in self.dec:
            self.by_unit.setdefault(d["unit"], []).append(d)
        self.keys = {u: [h[0] for h in v] for u, v in self.hist.items()}

    def mark(self, u, i, pos, tu, out):
        h = self.hist.setdefault(u, [])
        p0, t0, o0 = (h[-1][1], h[-1][2], h[-1][3]) if h else (None, None, False)
        h.append((i, pos if pos else p0, t0 if tu is None else tu, o0 if out is None else out))

    def at(self, u, i):
        """(pos, tu, out) by the last line before i"""
        k = self.keys.get(u)
        if not k:
            return None
        j = bisect.bisect_left(k, i) - 1
        return self.hist[u][j][1:] if j >= 0 else None

    def acts(self, h):
        if h not in self.acts_cache:
            raw = self.acts_raw.get(h)
            self.acts_cache[h] = json.loads(raw) if raw else []
        return self.acts_cache[h]

    def moves(self, h):
        raw = self.moves_raw.get(h)
        out = {}
        if raw:
            for c in raw.split(";"):
                p, _, t = c.partition(":")
                x = p.split(".")
                if len(x) == 3 and t and int(t) >= 0:  # R-709: -1 is a cell out of reach
                    out[(int(x[0]), int(x[1]), int(x[2]))] = int(t)
        return out

    def comrades(self, i, b):
        """hostile units up at line i, without b"""
        out = {}
        for u, f in self.fac.items():
            if f != 1 or u == b:
                continue
            a = self.at(u, i)
            if a and not a[2] and a[0]:
                out[u] = a
        return out


def shots_by_target(acts):
    """target id -> {pos, lof, cheapest tu, chance, weapon, dist} over firearm modes, for the player's side"""
    out = {}
    for c in acts:
        if c.get("k") != "a" or c.get("t") not in SHOT or c.get("u", ENEMY_BASE) >= ENEMY_BASE or c.get("u", -1) < 0:
            continue
        o = out.setdefault(c["u"], {"to": tuple(c["to"]), "lof": 0, "tu": 10 ** 6, "p": 0, "w": c.get("w"), "d": c.get("d"), "mode": c["t"]})
        o["lof"] = max(o["lof"], c.get("lof", 0))
        if c["tu"] < o["tu"]:
            o.update(tu=c["tu"], p=c.get("p", 0), w=c.get("w"), mode=c["t"])
    return out


def attack_target(b, d):
    """the player's-side id an executed attack decision aimed at, by the action id in the unit's acts list"""
    for c in b.acts(d["acts"]) if d["acts"] else []:
        if c.get("id") == d["id"]:
            return c.get("u")
    return None
