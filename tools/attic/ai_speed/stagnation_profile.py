#!/usr/bin/env python3
"""STAGNATION_PROFILE - почему бой стенда живёт до предела ходов: пассивно, по архивам серий (второе мнение 01.10, п. 5).

Ничего в движке не меняется и не измеряется заново: всё, что второе мнение просит «собирать на каждом ходу», стенд
уже пишет в архивы серии (ai_arena): решения и их исполнение (<метка>.rec.gz: [AIREC] / [AIEXEC]), снимки юнитов на
границах ходов (<метка>.tiles.gz: [AISTATE] before / aistart / pstart / end), потери (<метка>.casualties.txt) и итог боя
(<метка>.tsv: how = over / timeout, turn, outcome). Скрипт складывает их по бою и ходу и печатает распределения;
правила «пат» он не вводит и исход не меняет - только показывает, разделяются ли два класса длинных боёв:
долгий бой, где в хвосте ещё есть атаки и движение, и пат, где последние 20-30 ходов почти только blocked / idle.

По ходу T и стороне (0 бот, 1 враг - по id юнита, >= 1000000 враг; поле faction врёт для захваченных психом): решений;
атак (base.k == 'a'); решений с уроном (dmg / stunned / fdmg / hp_lost); убитых и оглушённых ([AICASUALTY] turn=T, turn=0 -
до боя, не считается); удачных ходов (walk == 1 и клетка после != клетки начала); сорванных ходов по причине (walk == 1,
клетка та же: первый walk.stop.* следа; без следа и без траты ОВ - nowalk: UnitWalkBState снял себя до первого шага, у
юнита, которому броня ходить не даёт - Armor::allowsMoving, турели PILLBOX, - это каждое решение «патруль»); юнитов, решавших
и юнитов с продвижением (ход, атака, урон); юнитов с повторной остановкой первого шага (walk.stop.unit A>B с A == начало,
>= 2 раза за ход на той же паре A>B - REPEATED_BLOCKED_STEP); новых замеченных врагов (рост множества sees= стороны по
[AISTATE] плюс walk.stop.spotted); контакта (хоть у кого-то sees= не пуст в снимках хода); живых по стороне ([AISTATE]
pstart T, для хода 1 - before; статус не 6/7, hp > 0, stun < hp). Живые в конце боя - из таблицы серии (livesoldiers / hleft).

По бою: последний ход с атакой / уроном / потерей / удачным ходом / новым замеченным / контактом (и по сторонам); played -
последний сыгранный ход ([AIREC]); since_any = played - max(последних), since_combat - то же по атаке / урону / потере;
хвост N ходов (20 и 30): ходов с атакой, с уроном, с удачным ходом бота / врага, с контактом, с любым продвижением, «только
blocked / idle» (решения были, продвижения нет), доля сорванных и пустых (k == 'e') решений, ходов с повторной остановкой,
типы юнитов nowalk.

Числа - на той механике, которой сняты серии (когорта b46fp* - build-ai46 до REPEATED_BLOCKED_STEP_V1); после правки
ветки блокировок прогнать заново на новой когорте - скрипт от сборки не зависит.

  py -3.13 tools/ai_speed/stagnation_profile.py --arena E:/OXCE_AIWorker/results/arena b46fp23 b46fp24 b46fp29 b46fp30 b46fp32 b46fp35
  построчно по боям - tools/ai_speed/runs/stagnation_profile.tsv (--out)"""
import argparse
import collections
import csv
import gzip
import json
import re
import statistics
import sys
from pathlib import Path

from _common import ENC_W, OUT, probe_work

HOSTILE = 1000000  # id врага у стенда; меньше - бот (сторона 0)
RX_STATE = re.compile(r"\[AISTATE\] (\w+) turn=(\d+) unit=(\d+) type=\S+ faction=(\d+) status=(\d+) pos=\(\d+,\d+,\d+\) "
                      r"dir=-?\d+ tu=-?\d+ hp=(-?\d+)/(-?\d+) stun=(-?\d+) .*? sees=(\S+) ")
RX_CAS = re.compile(r"\[AICASUALTY\] turn=(\d+) side=(\d+) victim=(\d+) vfaction=(\d+) .* how=(\w+) ")
RX_BLOCK = re.compile(r"walk\.stop\.unit (\d+,\d+,\d+)>(\d+,\d+,\d+) ")
SIDES = (0, 1)
TAILS = (20, 30)
BINS = ((0, 0), (1, 5), (6, 10), (11, 20), (21, 40), (41, 10 ** 6))
# три карты, которые второе мнение назвало отдельно, остальное - «обычные»
NAMED = {"STR_LOC_CITY_OF_THE_DEAD_SCOUTING": "город мёртвых", "STR_NINJA_RAID_SITE": "ниндзя",
         "STR_LOC_RITUAL_CAVE": "ритуальная пещера"}


def cell(p):
    return ",".join(str(x) for x in p)


def new_turn():
    z = lambda: {s: 0 for s in SIDES}  # noqa: E731
    return {"dec": z(), "att": z(), "dmg": z(), "kill": z(), "mv_ok": z(), "mv_blk": z(), "idle": z(), "spot": z(),
            "contact": z(), "blk_why": collections.Counter(), "nowalk_units": set(),
            "units": {s: set() for s in SIDES}, "prog": {s: set() for s in SIDES},
            "rb": {s: set() for s in SIDES}, "first": collections.defaultdict(collections.Counter),
            "living": {}}  # living[kind] = {сторона: живых}


def new_battle():
    return {"turns": collections.defaultdict(new_turn), "seen": {s: set() for s in SIDES}, "pending": {},
            "types": {}, "how": "", "turn_tsv": 0, "outcome": "", "hleft": "", "livesoldiers": ""}


def side_of(unit):
    return 1 if unit >= HOSTILE else 0


def load_rec(path, B):
    """[AIREC] / [AIEXEC] серии -> счётчики хода; решение склеивается с исполнением по rec внутри боя"""
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            if "{" not in line:
                continue
            head = line[:line.index("{")]
            key = head.split(" [", 1)[0]
            if "[AIREC]" in head:
                r = json.loads(line[line.index("{"):])
                b = B[key]
                base = r.get("base") or {}
                b["pending"][r["rec"]] = (r["turn"], side_of(r["unit"]), r["unit"], cell(r["state"]["pos"]), base.get("k"))
                t = b["turns"][r["turn"]]
                s = side_of(r["unit"])
                t["dec"][s] += 1
                t["units"][s].add(r["unit"])
                if base.get("k") == "a":
                    t["att"][s] += 1
                    t["prog"][s].add(r["unit"])
                elif base.get("k") == "e":
                    t["idle"][s] += 1
            elif "[AIEXEC]" in head:
                r = json.loads(line[line.index("{"):])
                b = B[key]
                p = b["pending"].pop(r["rec"], None)
                if not p:
                    continue
                turn, s, unit, start, kind = p
                t = b["turns"][turn]
                end = cell(r["pos"]) if r.get("pos") else start
                trail = r.get("trail") or []
                if (r.get("dmg") or 0) + (r.get("stunned") or 0) + (r.get("fdmg") or 0) + (r.get("hp_lost") or 0) > 0:
                    t["dmg"][s] += 1
                    if (r.get("dmg") or 0) + (r.get("stunned") or 0) > 0:
                        t["prog"][s].add(unit)
                if r.get("walk") == 1:
                    if end != start:
                        t["mv_ok"][s] += 1
                        t["prog"][s].add(unit)
                    else:
                        t["mv_blk"][s] += 1
                        why = next((x.split(" ", 1)[0][10:] for x in trail if x.startswith("walk.stop.")), "nowalk")
                        t["blk_why"][why] += 1
                        if why == "nowalk":
                            t["nowalk_units"].add(unit)
                for x in trail:
                    if x.startswith("walk.stop.spotted"):
                        t["spot"][s] += 1
                    m = RX_BLOCK.search(x)
                    if m and m.group(1) == start:
                        c = t["first"][unit]
                        c[(m.group(1), m.group(2))] += 1
                        if c[(m.group(1), m.group(2))] >= 2:
                            t["rb"][s].add(unit)


def load_tiles(path, B):
    """[AISTATE] -> живые по стороне на границах хода, контакт и рост множества замеченных; тип юнита"""
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            m = RX_STATE.search(line)
            if not m:
                continue
            key = line.split(" [", 1)[0]
            kind, turn, unit, fac, st, hp, _hpmax, stun, sees = m.groups()
            if int(fac) not in SIDES:  # нейтралы (2) - не сторона боя; захваченный психом враг - по id, не по faction
                continue
            s = side_of(int(unit))
            b = B[key]
            b["types"].setdefault(int(unit), line[line.index("type=") + 5:].split(" ", 1)[0])
            t = b["turns"][int(turn)]
            liv = t["living"].setdefault(kind, {x: 0 for x in SIDES})
            if int(st) not in (6, 7) and int(hp) > 0 and int(stun) < int(hp):
                liv[s] += 1
            if sees != "-":
                t["contact"][s] += 1
                for sid in sees.split(","):
                    if sid and sid not in b["seen"][s]:
                        b["seen"][s].add(sid)
                        t["spot"][s] += 1


def load_casualties(path, B):
    if not path.is_file():
        return
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            m = RX_CAS.search(line)
            if not m:
                continue
            turn, _side, _victim, vfac, _how = m.groups()
            if int(turn) <= 0 or int(vfac) not in SIDES:
                continue
            key = line.split(" [", 1)[0]
            # потеря - продвижение той стороны, которая её нанесла: противоположной жертве
            B[key]["turns"][int(turn)]["kill"][1 - int(vfac)] += 1


def load_tsv(path, B):
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        for row in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
            key = f"seed={row['seed']} want={row['want']}"
            b = B[key]
            b["how"], b["outcome"] = row["how"], row.get("outcome", "")
            b["turn_tsv"] = int(row["turn"] or 0)
            b["hleft"], b["livesoldiers"] = row.get("hleft", ""), row.get("livesoldiers", "")


def living_at(b, turn):
    """живых по стороне в начале хода: pstart (ход 1 - before), иначе aistart, иначе end"""
    liv = b["turns"][turn]["living"] if turn in b["turns"] else {}
    for kind in ("pstart", "before", "aistart", "end"):
        if kind in liv:
            return liv[kind]
    return None


def summarize(label, key, b):
    """итог боя: последние ходы событий, хвосты, живые"""
    turns = sorted(t for t in b["turns"] if b["turns"][t]["dec"][0] + b["turns"][t]["dec"][1] > 0)
    if not turns:
        return None
    played = turns[-1]
    seed, want = key.split(" ")[0][5:], key.split(" ")[1][5:]
    r = {"label": label, "seed": seed, "mission": want, "how": b["how"], "outcome": b["outcome"],
         "turn_tsv": b["turn_tsv"], "played": played, "hleft": b["hleft"], "livesoldiers": b["livesoldiers"]}

    def last(f):
        return max((t for t in turns if f(b["turns"][t])), default=0)
    r["last_attack"] = last(lambda t: t["att"][0] + t["att"][1] > 0)
    r["last_attack_bot"] = last(lambda t: t["att"][0] > 0)
    r["last_attack_enemy"] = last(lambda t: t["att"][1] > 0)
    r["last_damage"] = last(lambda t: t["dmg"][0] + t["dmg"][1] > 0)
    r["last_kill"] = last(lambda t: t["kill"][0] + t["kill"][1] > 0)
    r["last_move_ok"] = last(lambda t: t["mv_ok"][0] + t["mv_ok"][1] > 0)
    r["last_move_bot"] = last(lambda t: t["mv_ok"][0] > 0)
    r["last_move_enemy"] = last(lambda t: t["mv_ok"][1] > 0)
    r["last_spot"] = last(lambda t: t["spot"][0] + t["spot"][1] > 0)
    r["last_contact"] = last(lambda t: t["contact"][0] + t["contact"][1] > 0)
    r["since_any"] = played - max(r["last_attack"], r["last_damage"], r["last_kill"], r["last_move_ok"], r["last_spot"])
    r["since_combat"] = played - max(r["last_attack"], r["last_damage"], r["last_kill"])
    r["since_move"] = played - r["last_move_ok"]
    r["since_contact"] = played - r["last_contact"]
    liv = living_at(b, played) or {0: -1, 1: -1}  # начало последнего сыгранного хода по снимкам
    r["pstart_bot"], r["pstart_enemy"] = liv[0], liv[1]
    r["living_bot"] = int(b["livesoldiers"] or -1)  # конец боя - счёт движка из таблицы серии
    r["living_enemy"] = int(b["hleft"] or -1)
    for n in TAILS:
        tail = [b["turns"][t] for t in turns if t > played - n]
        dec = sum(t["dec"][0] + t["dec"][1] for t in tail)
        pref = f"t{n}_"
        r[pref + "turns"] = len(tail)
        r[pref + "att"] = sum(t["att"][0] + t["att"][1] > 0 for t in tail)
        r[pref + "dmg"] = sum(t["dmg"][0] + t["dmg"][1] > 0 for t in tail)
        r[pref + "kill"] = sum(t["kill"][0] + t["kill"][1] > 0 for t in tail)
        r[pref + "mv_bot"] = sum(t["mv_ok"][0] > 0 for t in tail)
        r[pref + "mv_enemy"] = sum(t["mv_ok"][1] > 0 for t in tail)
        r[pref + "spot"] = sum(t["spot"][0] + t["spot"][1] > 0 for t in tail)
        r[pref + "contact"] = sum(t["contact"][0] + t["contact"][1] > 0 for t in tail)
        prog = [t["att"][0] + t["att"][1] + t["dmg"][0] + t["dmg"][1] + t["kill"][0] + t["kill"][1]
                + t["mv_ok"][0] + t["mv_ok"][1] + t["spot"][0] + t["spot"][1] > 0 for t in tail]
        r[pref + "prog"] = sum(prog)
        r[pref + "blocked_idle"] = sum(not p for p in prog)
        r[pref + "rb"] = sum(len(t["rb"][0]) + len(t["rb"][1]) > 0 for t in tail)
        r[pref + "share_blk_idle"] = round(sum(t["mv_blk"][0] + t["mv_blk"][1] + t["idle"][0] + t["idle"][1]
                                               for t in tail) / dec, 3) if dec else 0.0
        units = sum(len(t["units"][0]) + len(t["units"][1]) for t in tail)
        r[pref + "share_units_prog"] = round(sum(len(t["prog"][0]) + len(t["prog"][1]) for t in tail) / units, 3) if units else 0.0
        why = collections.Counter()
        nw = collections.Counter()
        for t in tail:
            why.update(t["blk_why"])
            nw.update(b["types"].get(u, "?") for u in t["nowalk_units"])
        r[pref + "blk_why"] = " ".join(f"{k}:{v}" for k, v in why.most_common(4))
        r[pref + "nowalk_types"] = " ".join(f"{k}:{v}" for k, v in nw.most_common(3))
    return r


def binned(values):
    c = collections.Counter()
    for v in values:
        for lo, hi in BINS:
            if lo <= v <= hi:
                c[(lo, hi)] += 1
                break
    return " ".join(f"{lo}" + (f"-{hi}" if hi != lo and hi < 10 ** 6 else "+" if hi >= 10 ** 6 else "") + f":{c[(lo, hi)]}"
                    for lo, hi in BINS)


def med(vals, q=0.5):
    if not vals:
        return "-"
    v = sorted(vals)
    return v[min(len(v) - 1, int(q * len(v)))] if q != 0.5 else statistics.median(v)


def group_of(mission):
    return NAMED.get(mission, "обычные")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("labels", nargs="+")
    ap.add_argument("--arena", default="", help="папка серий (пусто - рабочая папка стенда)")
    ap.add_argument("--out", default=str(OUT / "stagnation_profile.tsv"), help="построчно по боям")
    a = ap.parse_args()
    arena = Path(a.arena) if a.arena else probe_work() / "arena"
    sys.stdout.reconfigure(encoding="utf-8")
    rows = []
    for lab in a.labels:
        B = collections.defaultdict(new_battle)
        load_tsv(arena / f"{lab}.tsv", B)
        load_rec(arena / f"{lab}.rec.gz", B)
        load_tiles(arena / f"{lab}.tiles.gz", B)
        load_casualties(arena / f"{lab}.casualties.txt", B)
        n = 0
        for key, b in B.items():
            r = summarize(lab, key, b)
            if r:
                rows.append(r)
                n += 1
        print(f"{lab}: боёв {n}, timeout {sum(1 for r in rows if r['label'] == lab and r['how'] == 'timeout')}", flush=True)
    if not rows:
        return 1
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, "w", encoding=ENC_W, newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), delimiter="\t", quoting=csv.QUOTE_NONE, escapechar="\\")
        w.writeheader()
        w.writerows(rows)
    print(f"\nпострочно: {a.out}")

    # 1. по карте и исходу: сколько боёв, сыграно ходов, давность продвижения, хвост 20 и 30, живые
    print("\n== По карте и исходу (медиана; p90 в скобках у since_combat). t20/t30 - ходов хвоста с событием из N; "
          "blk+idle - ходов хвоста без продвижения; доля blk/idle - сорванных и пустых решений среди решений хвоста")
    print("карта | исход | боёв | сыграно | since_any | since_combat (p90) | since_contact | t20 атака / урон / ход бота / "
          "ход врага / замечен / контакт | t20 blk+idle | t30 blk+idle | доля blk/idle t20 | повтор. остановки t20 | живых бот / враг")
    by = collections.defaultdict(list)
    for r in rows:
        by[(group_of(r["mission"]) != "обычные", r["mission"], r["how"])].append(r)
    for (_named, mission, how), rs in sorted(by.items(), key=lambda kv: (not kv[0][0], kv[0][1], kv[0][2])):
        g = lambda k: [r[k] for r in rs]  # noqa: E731
        print(f"{mission} ({group_of(mission)}) | {how} | {len(rs)} | {med(g('played'))} | {med(g('since_any'))} | "
              f"{med(g('since_combat'))} ({med(g('since_combat'), 0.9)}) | {med(g('since_contact'))} | "
              f"{med(g('t20_att'))} / {med(g('t20_dmg'))} / {med(g('t20_mv_bot'))} / {med(g('t20_mv_enemy'))} / "
              f"{med(g('t20_spot'))} / {med(g('t20_contact'))} | "
              f"{med(g('t20_blocked_idle'))} | {med(g('t30_blocked_idle'))} | {med(g('t20_share_blk_idle'))} | "
              f"{med(g('t20_rb'))} | {med(g('living_bot'))} / {med(g('living_enemy'))}")

    # 2. распределения по исходу
    for how in ("timeout", "over"):
        rs = [r for r in rows if r["how"] == how]
        if not rs:
            continue
        print(f"\n== {how}: боёв {len(rs)}")
        for k, name in (("since_combat", "ходов с последней атаки / урона / потери до конца"),
                        ("since_contact", "ходов с последнего контакта (кто-то кого-то видел)"),
                        ("since_any", "ходов с последнего продвижения любого вида"),
                        ("since_move", "ходов с последнего удачного хода"),
                        ("t20_blocked_idle", "ходов хвоста 20 без продвижения"),
                        ("t30_blocked_idle", "ходов хвоста 30 без продвижения"),
                        ("t20_att", "ходов хвоста 20 с атакой"),
                        ("t20_rb", "ходов хвоста 20 с повторной остановкой первого шага")):
            print(f"  {name}: {binned([r[k] for r in rs])}")

    # 3. классы на timeout по хвосту 20 - таблица, не правило: атаки x ходы врага, атаки x контакт
    rs = [r for r in rows if r["how"] == "timeout"]
    if rs:
        ab = ((0, 0), (1, 2), (3, 5), (6, 10), (11, 20))
        for col, title in (("t20_mv_enemy", "ходов хвоста 20 с удачным ходом ВРАГА (столбцы)"),
                           ("t20_mv_bot", "ходов хвоста 20 с удачным ходом БОТА (столбцы)"),
                           ("t20_contact", "ходов хвоста 20 с контактом (столбцы)")):
            print(f"\n== timeout: ходов хвоста 20 с атакой (строки) x {title}")
            print("атак\\ | " + " | ".join(f"{lo}-{hi}" if lo != hi else f"{lo}" for lo, hi in ab))
            for alo, ahi in ab:
                cells = [sum(1 for r in rs if alo <= r["t20_att"] <= ahi and mlo <= r[col] <= mhi) for mlo, mhi in ab]
                print(f"{alo}-{ahi}" if alo != ahi else f"{alo}", "|", " | ".join(str(c) for c in cells))

        def klass(r):
            if r["t20_att"] >= 6:
                return "A бой идёт (атаки >= 6 ходов из 20)"
            if r["t20_att"] == 0 and r["t20_contact"] == 0:
                return "C нет контакта (0 атак, никто никого не видит)"
            if r["t20_att"] == 0:
                return "B контакт без атак"
            return "D редкие атаки (1-5 ходов из 20)"
        print("\n== timeout: классы хвоста 20 (данные, не правило)")
        kc = collections.Counter(klass(r) for r in rs)
        for k, v in sorted(kc.items()):
            sub = [r for r in rs if klass(r) == k]
            print(f"  {k}: {v} | враг без единого хода в хвосте: {sum(1 for r in sub if r['t20_mv_enemy'] == 0)} | "
                  f"since_combat медиана {med([r['since_combat'] for r in sub])} | since_contact {med([r['since_contact'] for r in sub])} | "
                  f"повторные остановки в хвосте: {sum(1 for r in sub if r['t20_rb'] > 0)} боёв")
        print("\n== timeout: по картам - боёв, классы A / B / C / D, враг неподвижен в хвосте, nowalk-типы; медиана since_combat, живых бот/враг")
        bym = collections.defaultdict(list)
        for r in rs:
            bym[r["mission"]].append(r)
        for mission, ms in sorted(bym.items(), key=lambda kv: -len(kv[1])):
            kc = collections.Counter(klass(r)[0] for r in ms)
            nw = collections.Counter()
            for r in ms:
                for x in r["t20_nowalk_types"].split():
                    nw[x.rsplit(":", 1)[0]] += int(x.rsplit(":", 1)[1])
            print(f"  {mission} ({group_of(mission)}): {len(ms)} | A {kc['A']} B {kc['B']} C {kc['C']} D {kc['D']} | "
                  f"враг без ходов {sum(1 for r in ms if r['t20_mv_enemy'] == 0)} | "
                  f"nowalk {' '.join(f'{k}:{v}' for k, v in nw.most_common(2)) or '-'} | "
                  f"since_combat {med([r['since_combat'] for r in ms])} | "
                  f"живых {med([r['living_bot'] for r in ms])}/{med([r['living_enemy'] for r in ms])}")

        print("\n== timeout: каждый бой (серия seed карта | класс | сыграно | посл. атака бот/враг | посл. урон | посл. потеря | "
              "посл. ход бот/враг | посл. контакт | since_combat | t20 атака/урон/ход бота/ход врага/контакт/blk+idle/повтор | "
              "доля blk/idle | причины срыва t20 | nowalk-типы | живых бот/враг)")
        for r in sorted(rs, key=lambda r: (group_of(r["mission"]) == "обычные", r["mission"], -r["since_combat"])):
            print(f"  {r['label']} {r['seed']} {r['mission']} | {klass(r)[0]} | {r['played']} | "
                  f"{r['last_attack_bot']}/{r['last_attack_enemy']} | {r['last_damage']} | {r['last_kill']} | "
                  f"{r['last_move_bot']}/{r['last_move_enemy']} | {r['last_contact']} | {r['since_combat']} | "
                  f"{r['t20_att']}/{r['t20_dmg']}/{r['t20_mv_bot']}/{r['t20_mv_enemy']}/{r['t20_contact']}/"
                  f"{r['t20_blocked_idle']}/{r['t20_rb']} | {r['t20_share_blk_idle']} | {r['t20_blk_why']} | "
                  f"{r['t20_nowalk_types'] or '-'} | {r['living_bot']}/{r['living_enemy']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
