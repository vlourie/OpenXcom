#!/usr/bin/env python3
"""Разбор классов B и C профиля пата (`stagnation_profile.py`) по архивам серий `ai_arena` - пассивно,
движок не трогает, игра не запускается. Порядок второго мнения 01.10, п. 3 и 4.

Класс C (timeout, хвост 20: 0 атак, 0 контакта) - что стороны делают по карте: ближайшая пара живых
по снимкам AISTATE за бой и за хвост, общие посещённые клетки, этажи, смещение за ход, знание врага
о бойцах (после `cheatTurn` 20 движок каждый ход ставит бойцам игрока spotted 0 - враг знает всех),
источники решений (AIREC base.src), дошли ли ходы (AIEXEC). Вопрос: разделены ли стороны физически
или просто долго ищут друг друга.

Класс B (timeout, хвост 20: контакт есть, атак нет) - почему никто не атакует: кто кого видит и жив ли
увиденный, главное оружие у живых, решения против списков кандидатов атаки AICAND acts (цели нет /
линии огня нет / ОД не хватает / линия и ОД есть, а выбрано другое), решения вплотную к живому
противнику на том же этаже (рукопашный кандидат и его lof, диагональ или прямо), что в руках в конце.

Списки acts лежат в cand.gz (около 1 ГБ на серию, в основном списки ходов): нужные строки один раз
выжимаются в runs/stagnation_acts_<label>.txt и дальше берутся оттуда.

Запуск (та же когорта, что у профиля; профиль должен быть уже посчитан в runs/stagnation_profile.tsv):
  py -3.13 tools/ai_speed/stagnation_classes.py --arena E:/OXCE_AIWorker/results/arena c
  py -3.13 tools/ai_speed/stagnation_classes.py --arena E:/OXCE_AIWorker/results/arena b
Сводки - runs/stagnation_c.tsv и runs/stagnation_b.tsv.
"""
import argparse
import csv
import gzip
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import ENC_W, OUT  # noqa: E402

HOSTILE = 1000000
RX_POS = re.compile(r"\((-?\d+),(-?\d+),(-?\d+)\)")
T_HIT = 10  # BA_HIT (src/Mod/RuleItem.h: 7 авто, 8 снэп, 9 прицельный, 10 рукопашная, 14 паника)
ARENA = Path("E:/OXCE_AIWorker/results/arena")


def side_of(unit):
    return 1 if unit >= HOSTILE else 0


def fmt(x):
    return "-" if x is None else (f"{x:.1f}" if isinstance(x, float) else str(x))


def dist2(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


# ---------------------------------------------------------------- чтение архивов

def classes(prof):
    """Бои timeout по классам хвоста 20 из таблицы профиля: C - 0 атак и 0 контакта, B - 0 атак при контакте."""
    with open(prof, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))
    out = {"B": [], "C": []}
    for r in rows:
        if r["how"] != "timeout":
            continue
        att, con = int(r["t20_att"]), int(r["t20_contact"])
        if att == 0 and con == 0:
            out["C"].append(r)
        elif att == 0:
            out["B"].append(r)
    return out


def key_of(r):
    return f"seed={r['seed']} want={r['mission']}"


def arena_rows(arena, label):
    with open(arena / f"{label}.tsv", encoding="utf-8-sig", newline="") as f:
        return {f"seed={r['seed']} want={r['want']}": r for r in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE)}


def read_gz(arena, label, kind, keys):
    """Строки архива label.kind.gz по ключам боёв: {key: [rest, ...]}, rest начинается с '[TAG] '."""
    want = set(keys)
    out = defaultdict(list)
    with gzip.open(arena / f"{label}.{kind}.gz", "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            head, sep, rest = line.partition(" [")
            if not sep or head not in want:
                continue
            out[head].append("[" + rest.rstrip("\n"))
    return out


def acts_lines(arena, label, keys):
    """Строки [AICAND] acts= нужных боёв: из кэша runs/stagnation_acts_<label>.txt, иначе одним проходом по cand.gz."""
    cache = OUT / f"stagnation_acts_{label}.txt"
    want = {k.encode("utf-8") for k in keys}
    have = set()
    lines = []
    if cache.is_file():
        with cache.open("rb") as f:
            for raw in f:
                head = raw.split(b" [", 1)[0]
                have.add(head)
                if head in want:
                    lines.append(raw)
    missing = want - have
    if missing:
        print(f"  {label}: выжимка acts для {len(missing)} боёв из cand.gz (долго, один раз)", flush=True)
        OUT.mkdir(parents=True, exist_ok=True)
        new = []
        with gzip.open(arena / f"{label}.cand.gz", "rb") as f:
            for raw in f:
                if b"[AICAND] acts=" not in raw:
                    continue
                head = raw.split(b" [", 1)[0]
                if head in missing:
                    new.append(raw)
        with cache.open("ab") as f:
            f.writelines(new)
        lines.extend(new)
    out = defaultdict(list)
    for raw in lines:
        head, sep, rest = raw.decode("utf-8", errors="replace").partition(" [")
        out[head].append("[" + rest.rstrip("\n"))
    return out


# ---------------------------------------------------------------- разбор строк

def parse_state(rest):
    """'[AISTATE] when turn=.. unit=.. ... rh=..' -> словарь: when, числа, pos=(x,y,z), sees=[id,...], side."""
    toks = rest.split(" ")
    d = {"when": toks[1]}
    for t in toks[2:]:
        if "=" in t:
            k, v = t.split("=", 1)
            d[k] = v
    for k in ("turn", "unit", "faction", "status", "stun", "morale", "seenby", "known", "near", "shade", "reach", "tu", "tumax"):
        if k in d:
            d[k] = int(d[k])
    hp = d.get("hp", "0/0").split("/")
    d["hp"], d["hpmax"] = int(hp[0]), int(hp[1])
    m = RX_POS.match(d.get("pos", ""))
    d["pos"] = tuple(int(x) for x in m.groups()) if m else None
    d["sees"] = [int(x) for x in d["sees"].split(",")] if d.get("sees", "-") != "-" else []
    d["side"] = side_of(d["unit"])
    return d


def living(s):
    return s["status"] not in (6, 7) and s["hp"] > 0 and s["stun"] < s["hp"]


def states_of(lines):
    """{(when, turn): {unit: state}} и {unit: type}."""
    snaps = defaultdict(dict)
    types = {}
    for rest in lines:
        if rest.startswith("[AISTATE] "):
            s = parse_state(rest)
            snaps[(s["when"], s["turn"])][s["unit"]] = s
            types[s["unit"]] = s.get("type", "?")
    return snaps, types


def recs_of(lines):
    """[AIREC] по порядку и [AIEXEC] по номеру записи."""
    recs, execs = [], {}
    for rest in lines:
        if rest.startswith("[AIREC] "):
            recs.append(json.loads(rest[8:]))
        elif rest.startswith("[AIEXEC] "):
            e = json.loads(rest[9:])
            execs[e["rec"]] = e
    return recs, execs


def acts_of(lines):
    """{hash: [act, ...]} из [AICAND] acts=<hash> unit=<id> list=[...]."""
    out = {}
    for rest in lines:
        if rest.startswith("[AICAND] acts="):
            h = rest[14:].split(" ", 1)[0]
            out[h] = json.loads(rest[rest.index(" list=") + 6:])
    return out


# ---------------------------------------------------------------- класс C: по карте

def analyse_c(label, r, arow, tiles, reclines, tail):
    snaps, types = states_of(tiles)
    recs, execs = recs_of(reclines)
    played = int(r["played"])
    tail0 = played - tail + 1
    turns = sorted({t for (w, t) in snaps if w == "pstart"})
    near = []  # ближайшая пара живых по каждому снимку
    for t in turns:
        for when in ("pstart", "aistart"):
            st = snaps.get((when, t))
            if not st:
                continue
            bots = [s for s in st.values() if s["side"] == 0 and living(s) and s["pos"]]
            ens = [s for s in st.values() if s["side"] == 1 and living(s) and s["pos"]]
            if not bots or not ens:
                continue
            best = None
            for b in bots:
                for e in ens:
                    d, dz = dist2(b["pos"], e["pos"]), abs(b["pos"][2] - e["pos"][2])
                    if best is None or (d, dz) < (best[0], best[1]):
                        best = (d, dz, b["pos"], e["pos"], b["unit"], e["unit"])
            near.append((t, when) + best + (len(bots), len(ens)))
    visited = {0: set(), 1: set()}
    visited_tail = {0: set(), 1: set()}
    zlev = {0: Counter(), 1: Counter()}
    for (w, t), st in snaps.items():
        for s in st.values():
            if not s["pos"] or not living(s):
                continue
            visited[s["side"]].add(s["pos"])
            if t >= tail0:
                visited_tail[s["side"]].add(s["pos"])
                zlev[s["side"]][s["pos"][2]] += 1
    moves = {0: [], 1: []}  # смещение юнита за свой ход в хвосте: бот pstart->aistart, враг aistart->pstart следующего
    for t in turns:
        if t < tail0:
            continue
        p0, a0, p1 = snaps.get(("pstart", t)), snaps.get(("aistart", t)), snaps.get(("pstart", t + 1))
        if p0 and a0:
            for u, s in p0.items():
                if s["side"] == 0 and living(s) and u in a0 and s["pos"] and a0[u]["pos"]:
                    moves[0].append(dist2(s["pos"], a0[u]["pos"]))
        if a0 and p1:
            for u, s in a0.items():
                if s["side"] == 1 and living(s) and u in p1 and s["pos"] and p1[u]["pos"]:
                    moves[1].append(dist2(s["pos"], p1[u]["pos"]))
    en_near, en_known = [], []
    for t in turns:
        if t < tail0:
            continue
        for s in snaps.get(("pstart", t), {}).values():
            if s["side"] == 1 and living(s):
                en_known.append(s["known"])
                if s["near"] >= 0:
                    en_near.append(s["near"])
    src = {0: Counter(), 1: Counter()}
    kinds = {0: Counter(), 1: Counter()}
    walk = {0: [0, 0], 1: [0, 0]}
    for rec in recs:
        if rec["turn"] < tail0:
            continue
        sd = rec["side"]
        b = rec.get("base") or {}
        src[sd][str(b.get("src"))] += 1
        kinds[sd][str(b.get("k"))] += 1
        e = execs.get(rec["rec"])
        if e and e.get("walk"):
            walk[sd][0 if e["pos"] != rec["state"]["pos"] else 1] += 1
    tail_near = [n for n in near if n[0] >= tail0]
    return {
        "label": label, "key": key_of(r), "mission": r["mission"], "terrain": arow.get("terrain"), "shade": arow.get("shade"),
        "units": arow.get("units"), "hostile": arow.get("hostile"), "living": f"{r['living_bot']}/{r['living_enemy']}",
        "played": played, "last_contact": r["last_contact"], "since_contact": r["since_contact"],
        "en_types": Counter(types[u] for u in types if u >= HOSTILE),
        "all_min": min(near, key=lambda n: (n[2], n[3])) if near else None,
        "tail_min": min(tail_near, key=lambda n: (n[2], n[3])) if tail_near else None,
        "tail_med": median([n[2] for n in tail_near]) if tail_near else None,
        "tail_max": max(n[2] for n in tail_near) if tail_near else None,
        "visited": (len(visited[0]), len(visited[1]), len(visited[0] & visited[1])),
        "visited_tail": (len(visited_tail[0]), len(visited_tail[1]), len(visited_tail[0] & visited_tail[1])),
        "z": (dict(zlev[0]), dict(zlev[1])),
        "move": (median(moves[0]) if moves[0] else None, median(moves[1]) if moves[1] else None,
                 sum(1 for m in moves[0] if m == 0), len(moves[0]), sum(1 for m in moves[1] if m == 0), len(moves[1])),
        "en_near": (min(en_near) if en_near else None, median(en_near) if en_near else None),
        "en_known": median(en_known) if en_known else None,
        "src": src, "kinds": kinds, "walk": walk,
    }


def verdict_c(o):
    tm = o["tail_min"][2] if o["tail_min"] else None
    parts = ["одно пространство (клетки общие)" if o["visited"][2] >= 3 else "общих клеток нет"]
    if tm is not None and tm <= 6:
        parts.append(f"в хвосте сходились до {tm:.0f}")
    elif tm is not None:
        parts.append(f"в хвосте ближе {tm:.0f} не было")
    if o["move"][1] is not None and o["move"][1] == 0:
        parts.append("враг стоит")
    if o["move"][0] is not None and o["move"][0] == 0:
        parts.append("бот стоит")
    return "; ".join(parts)


def report_c(results, tail, out_tsv):
    for o in results:
        print()
        print(f"=== {o['label']} {o['key']}  terrain={o['terrain']} shade={o['shade']} units={o['units']} hostile={o['hostile']} "
              f"живых {o['living']} сыграно {o['played']} последний контакт ход {o['last_contact']} (since {o['since_contact']})")
        print("  враг:", ", ".join(f"{t} x{n}" for t, n in o["en_types"].most_common()))
        am, tm = o["all_min"], o["tail_min"]
        if am:
            print(f"  ближе всего за бой: {am[2]:.1f} (dz {am[3]}) ход {am[0]} {am[1]} бот {am[6]}@{am[4]} враг {am[7]}@{am[5]}")
        if tm:
            print(f"  хвост {tail}: ближе всего {tm[2]:.1f} (dz {tm[3]}) ход {tm[0]} {tm[1]} бот {tm[6]}@{tm[4]} враг {tm[7]}@{tm[5]}; "
                  f"медиана {fmt(o['tail_med'])}, максимум {fmt(o['tail_max'])}")
        v, vt = o["visited"], o["visited_tail"]
        print(f"  клетки за бой: бот {v[0]}, враг {v[1]}, общих {v[2]}; за хвост: бот {vt[0]}, враг {vt[1]}, общих {vt[2]}")
        print(f"  этажи в хвосте: бот {o['z'][0]} враг {o['z'][1]}")
        m = o["move"]
        print(f"  смещение за ход в хвосте (медиана): бот {fmt(m[0])} (стоял {m[2]} из {m[3]}), враг {fmt(m[1])} (стоял {m[4]} из {m[5]})")
        print(f"  враг знает бойцов (cheat после хода 20): known медиана {fmt(o['en_known'])}, near min {fmt(o['en_near'][0])} "
              f"медиана {fmt(o['en_near'][1])}")
        for sd, name in ((0, "бот"), (1, "враг")):
            print(f"  решения {name} в хвосте: виды {dict(o['kinds'][sd])}; источники {dict(o['src'][sd].most_common(6))}; "
                  f"ходы дошли/сорвались {o['walk'][sd][0]}/{o['walk'][sd][1]}")
        print("  вывод:", verdict_c(o))
    cols = ("label", "seed", "mission", "terrain", "shade", "live", "last_contact", "min_all", "dz_all", "min_tail", "dz_tail", "med_tail",
            "common", "common_tail", "bot_move", "en_move", "bot_stood", "en_stood", "en_near_min", "bot_src", "en_src", "verdict")
    rows = []
    for o in results:
        am, tm = o["all_min"], o["tail_min"]
        rows.append((o["label"], o["key"].split(" ")[0][5:], o["mission"], o["terrain"], o["shade"], o["living"], o["last_contact"],
                     fmt(am[2]) if am else "-", am[3] if am else "-", fmt(tm[2]) if tm else "-", tm[3] if tm else "-", fmt(o["tail_med"]),
                     o["visited"][2], o["visited_tail"][2], fmt(o["move"][0]), fmt(o["move"][1]), f"{o['move'][2]}/{o['move'][3]}",
                     f"{o['move'][4]}/{o['move'][5]}", fmt(o["en_near"][0]), dict(o["src"][0].most_common(3)), dict(o["src"][1].most_common(3)),
                     verdict_c(o)))
    print()
    print("=== сводка")
    print("\t".join(cols))
    for row in rows:
        print("\t".join(str(x) for x in row))
    with open(out_tsv, "w", encoding=ENC_W, newline="") as f:
        w = csv.writer(f, delimiter="\t", quoting=csv.QUOTE_NONE, escapechar="|")
        w.writerow(cols)
        w.writerows(rows)
    print("записано", out_tsv)


# ---------------------------------------------------------------- класс B: почему нет атаки

def analyse_b(label, r, arow, tiles, reclines, acts, tail):
    snaps, types = states_of(tiles)
    recs, execs = recs_of(reclines)
    played = int(r["played"])
    tail0 = played - tail + 1

    def nearest_opp(sd, turn, pos):
        # противник бота в ход бота не двигается: его позиции - снимок pstart того же хода; для врага - aistart
        st = snaps.get(("pstart" if sd == 0 else "aistart", turn)) or {}
        best = None
        for s in st.values():
            if s["side"] != sd and living(s) and s["pos"] and pos:
                d, dz = dist2(pos, s["pos"]), abs(pos[2] - s["pos"][2])
                if best is None or (d, dz) < (best[0], best[1]):
                    best = (d, dz, s)
        return best

    contact = Counter()
    pairs = Counter()
    armed = {0: Counter(), 1: Counter()}
    for (w, t), st in snaps.items():
        if t < tail0:
            continue
        for s in st.values():
            if not living(s):
                continue
            armed[s["side"]]["есть" if s.get("weapon", "-") != "-" else "нет"] += 1
            for v in s["sees"]:
                seen = st.get(v)
                alive = seen is not None and living(seen)
                d = dist2(s["pos"], seen["pos"]) if seen and seen["pos"] and s["pos"] else -1
                dz = abs(s["pos"][2] - seen["pos"][2]) if seen and seen["pos"] and s["pos"] else -1
                contact[(s["side"], "живого" if alive else "лежачего")] += 1
                pairs[(s["side"], s["unit"], v, alive, round(d), dz)] += 1
    dec = {0: Counter(), 1: Counter()}
    declined_src = {0: Counter(), 1: Counter()}
    nolof_src = {0: Counter(), 1: Counter()}
    examples = {0: [], 1: []}
    weapons_lof = {0: Counter(), 1: Counter()}
    adj = {0: Counter(), 1: Counter()}
    adj_ex = {0: [], 1: []}
    walk = {0: [0, 0], 1: [0, 0]}
    for rec in recs:
        if rec["turn"] < tail0:
            continue
        sd = rec["side"]
        b = rec.get("base") or {}
        tu = rec["state"]["tu"]
        pos = tuple(rec["state"]["pos"])
        e = execs.get(rec["rec"])
        if e and e.get("walk"):
            walk[sd][0 if tuple(e["pos"]) != pos else 1] += 1
        lst = acts.get(rec["cand"]["acts"]) if acts else None
        if lst is None:
            dec[sd]["без списка"] += 1
            continue
        att = [a for a in lst if a["k"] == "a"]
        lof = [a for a in att if a.get("lof") == 1]
        lof_tu = [a for a in lof if a["tu"] <= tu]
        if not att:
            dec[sd]["цели нет"] += 1
        elif not lof:
            dec[sd]["цель есть, линии огня нет"] += 1
            nolof_src[sd][str(b.get("src"))] += 1
            if len(examples[sd]) < 3 and dec[sd]["цель есть, линии огня нет"] == 1:
                best = max(att, key=lambda a: a["p"])
                examples[sd].append(f"ход {rec['turn']} юнит {rec['unit']} ОД {tu}: без линии огня — {best['w']} t{best['t']} p{best['p']} d{best['d']} "
                                    f"по {best['u']} ({types.get(best['u'], '?')}); выбрано {b.get('k')} {b.get('src')} -> {b.get('to')}")
        elif not lof_tu:
            dec[sd]["линия есть, ОД не хватает"] += 1
        elif b.get("k") == "a":
            dec[sd]["атака выбрана"] += 1
        else:
            dec[sd]["линия и ОД есть, не атакует"] += 1
            declined_src[sd][str(b.get("src"))] += 1
            best = max(lof_tu, key=lambda a: a["p"])
            weapons_lof[sd][f"{best['w']} t{best['t']}"] += 1
            if len(examples[sd]) < 3:
                props = (b.get("reason") or {}).get("props") or []
                examples[sd].append(f"ход {rec['turn']} юнит {rec['unit']} ОД {tu}: лучшая атака {best['w']} t{best['t']} p{best['p']} d{best['d']} tu{best['tu']} "
                                    f"по {best['u']} ({types.get(best['u'], '?')}); выбрано {b.get('k')} {b.get('src')} -> {b.get('to')} "
                                    f"score {b.get('score')} props {[(p.get('src'), p.get('sc')) for p in props]}")
        nb = nearest_opp(sd, rec["turn"], pos)
        if nb and nb[0] <= 1.5 and nb[1] == 0:
            melee = [a for a in att if a["t"] == T_HIT]
            dx, dy = nb[2]["pos"][0] - pos[0], nb[2]["pos"][1] - pos[1]
            how = "диагональ" if dx and dy else "прямо"
            what = ("рукопашная с линией" if any(a.get("lof") == 1 for a in melee)
                    else ("рукопашная без линии" if melee else "рукопашного кандидата нет"))
            adj[sd][(what, how)] += 1
            if len(adj_ex[sd]) < 2:
                adj_ex[sd].append(f"ход {rec['turn']} юнит {rec['unit']} {pos} рядом {nb[2]['unit']} {types.get(nb[2]['unit'], '?')} {nb[2]['pos']} "
                                  f"({how}): {what}; кандидаты {[(a['w'], a['p'], a['lof'], a['tu']) for a in melee][:2]}; выбрано {b.get('k')} {b.get('src')}")
    last = max(t for (w, t) in snaps)
    st = snaps.get(("pstart", last)) or snaps.get(("aistart", last)) or {}
    bot_arms, en_arms = [], Counter()
    for s in st.values():
        if s["side"] == 0:
            bot_arms.append(f"{s['unit']} {'жив' if living(s) else 'лежит'} hp{s['hp']}/{s['hpmax']} stun{s['stun']} главное={s.get('weapon')} "
                            f"rh={s.get('rh')} lh={s.get('lh')} ammo={s.get('ammo')} spare={s.get('spare')}")
        elif living(s):
            en_arms[f"{s.get('type')} {s.get('weapon')} rh={s.get('rh')} lh={s.get('lh')}"] += 1
    return {
        "label": label, "key": key_of(r), "mission": r["mission"], "terrain": arow.get("terrain"), "shade": arow.get("shade"),
        "living": f"{r['living_bot']}/{r['living_enemy']}", "played": played, "last_attack": r["last_attack"], "since_combat": r["since_combat"],
        "contact": contact, "pairs": pairs, "dec": dec, "declined_src": declined_src, "nolof_src": nolof_src, "examples": examples,
        "weapons_lof": weapons_lof, "bot_arms": bot_arms, "en_arms": en_arms, "armed": armed, "adj": adj, "adj_ex": adj_ex, "walk": walk,
    }


def report_b(results, out_tsv):
    for o in results:
        print()
        print(f"=== {o['label']} {o['key']}  terrain={o['terrain']} shade={o['shade']} живых {o['living']} сыграно {o['played']} "
              f"последняя атака ход {o['last_attack']} (since_combat {o['since_combat']})")
        c = o["contact"]
        print(f"  контакты в хвосте (снимок x юнит x цель): бот видит живого {c[(0, 'живого')]}, лежачего {c[(0, 'лежачего')]}; "
              f"враг видит живого {c[(1, 'живого')]}, лежачего {c[(1, 'лежачего')]}")
        for (sd, u, v, alive, d, dz), n in sorted(o["pairs"].items(), key=lambda kv: -kv[1])[:5]:
            print(f"    {'бот' if sd == 0 else 'враг'} {u} видит {v} ({'жив' if alive else 'лежит'}) дист {d} dz {dz}: {n} снимков")
        a = o["armed"]
        print(f"  главное оружие у живых по снимкам хвоста: бот есть {a[0]['есть']} / нет {a[0]['нет']}; враг есть {a[1]['есть']} / нет {a[1]['нет']}")
        for sd, name in ((0, "бот"), (1, "враг")):
            print(f"  решения {name}: {dict(o['dec'][sd])}; ходы дошли/сорвались {o['walk'][sd][0]}/{o['walk'][sd][1]}")
            if o["nolof_src"][sd]:
                print(f"    без линии огня выбирал: {dict(o['nolof_src'][sd].most_common(5))}")
            if o["declined_src"][sd]:
                print(f"    отказ при линии и ОД, источники: {dict(o['declined_src'][sd].most_common(5))}; оружие {dict(o['weapons_lof'][sd])}")
            if o["adj"][sd]:
                print(f"    вплотную к живому противнику (тот же этаж): {dict(o['adj'][sd])}")
                for ex in o["adj_ex"][sd]:
                    print("      ", ex)
            for ex in o["examples"][sd]:
                print("    ", ex)
        print("  бот в конце:")
        for s in o["bot_arms"]:
            print("    ", s)
        print("  враг живой в конце:", dict(o["en_arms"]))
    cols = ("label", "seed", "mission", "terrain", "shade", "live", "last_attack", "bot_sees_alive", "bot_sees_down", "en_sees_alive", "en_sees_down",
            "bot_armed", "bot_unarmed", "en_armed", "en_unarmed", "bot_dec", "en_dec", "bot_adjacent", "en_adjacent", "bot_walk", "en_walk")
    rows = []
    for o in results:
        c, a = o["contact"], o["armed"]
        rows.append((o["label"], o["key"].split(" ")[0][5:], o["mission"], o["terrain"], o["shade"], o["living"], o["last_attack"],
                     c[(0, "живого")], c[(0, "лежачего")], c[(1, "живого")], c[(1, "лежачего")], a[0]["есть"], a[0]["нет"], a[1]["есть"], a[1]["нет"],
                     dict(o["dec"][0]), dict(o["dec"][1]), dict(o["adj"][0]), dict(o["adj"][1]),
                     f"{o['walk'][0][0]}/{o['walk'][0][1]}", f"{o['walk'][1][0]}/{o['walk'][1][1]}"))
    print()
    print("=== сводка")
    print("\t".join(cols))
    for row in rows:
        print("\t".join(str(x) for x in row))
    with open(out_tsv, "w", encoding=ENC_W, newline="") as f:
        w = csv.writer(f, delimiter="\t", quoting=csv.QUOTE_NONE, escapechar="|")
        w.writerow(cols)
        w.writerows(rows)
    print("записано", out_tsv)


# ---------------------------------------------------------------- запуск

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("klass", choices=("c", "b"), help="c - класс C по карте, b - класс B почему нет атаки")
    ap.add_argument("--arena", default=str(ARENA), help="папка архивов серий ai_arena")
    ap.add_argument("--profile", default=str(OUT / "stagnation_profile.tsv"), help="таблица stagnation_profile.py")
    ap.add_argument("--tail", type=int, default=20, help="хвост в ходах, как у профиля")
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    arena = Path(a.arena)
    cls = classes(a.profile)[a.klass.upper()]
    by_label = defaultdict(list)
    for r in cls:
        by_label[r["label"]].append(r)
    print(f"класс {a.klass.upper()}: {len(cls)} боёв в {len(by_label)} сериях (профиль {a.profile})")
    results = []
    for label in sorted(by_label):
        rows = by_label[label]
        keys = [key_of(r) for r in rows]
        arow = arena_rows(arena, label)
        tiles = read_gz(arena, label, "tiles", keys)
        recl = read_gz(arena, label, "rec", keys)
        acts = {k: acts_of(v) for k, v in acts_lines(arena, label, keys).items()} if a.klass == "b" else {}
        for r in rows:
            k = key_of(r)
            if k not in tiles:
                print("нет AISTATE:", label, k)
                continue
            if a.klass == "c":
                results.append(analyse_c(label, r, arow.get(k, {}), tiles[k], recl.get(k, []), a.tail))
            else:
                results.append(analyse_b(label, r, arow.get(k, {}), tiles[k], recl.get(k, []), acts.get(k, {}), a.tail))
    OUT.mkdir(parents=True, exist_ok=True)
    if a.klass == "c":
        report_c(results, a.tail, OUT / "stagnation_c.tsv")
    else:
        report_b(results, OUT / "stagnation_b.tsv")


if __name__ == "__main__":
    main()
