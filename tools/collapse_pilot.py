"""Пилот модели обрушения (этап 0f): одна версия модели M0f, правило «неподдерживаемый расчёт», отбор зданий
пилота, сценарии и проверка на отложенных картах. Только анализ - движок не трогает.

py -3.13 tools/collapse_pilot.py candidates      - целые блоки группы 1, годные в пилот, с числами по 90 картам
                                                    (stage0f/pilot_candidates.tsv)
py -3.13 tools/collapse_pilot.py geom            - этажи зданий пилота буквами и части, которые держит только
                                                    правило-кандидат Q/I/M/S/N, - для слепого рецензента
                                                    (stage0f/pilot_geom.txt)
py -3.13 tools/collapse_pilot.py lock            - замок версии M0f: флаги, параметры, хэши кода, данных, списка
                                                    пилота и ожиданий (stage0f/rules.lock.txt)
py -3.13 tools/collapse_pilot.py scen FILE       - сценарии: PASS / FAIL / UNSUPPORTED (stage0f/scen_<имя>.json)
py -3.13 tools/collapse_pilot.py holdout [FILE]  - отложенные карты: висящее до боя по категориям, блоки, известные
                                                    по 90 картам, отдельно от новых; здания пилота на этих картах и
                                                    сценарии FILE на их местах (stage0f/holdout_*.json)

Модель M0f - collapse_v3.evaluate3 с флагами MODEL. В неё не входят: E (направленная консоль - ложные потери,
этап 0e), J (всё судно жёсткое - приклеивает груз), L (отдельный предел мостков - целая геометрия его не
подтвердила: CHEMTOWN51 держит настил от фермы до фермы с чистым пролётом 10, этап 0f). Числа C=2, L=12,
LINTEL, L_TARP, L_ROOF - экспериментальные; S, N, Q, I, M, B - правила-кандидаты.

Неподдерживаемый расчёт: если обрушение (упавшее, снятое и всё в одной клетке от них) затрагивает часть с
неизвестной ролью, висевшее до боя, лёгкий настил на балке, край блока, судно или (на карте) непроверенную
клетку и край карты - весь результат UNSUPPORTED, частичный не применяется."""
import collections
import hashlib
import json
import os
import pickle
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import collapse_census as cc      # noqa: E402
import collapse_v2 as V           # noqa: E402
import collapse_v3 as T           # noqa: E402
import collapse_summary as S      # noqa: E402

ENC = "utf-8-sig"
OUT = "census/collapse/stage0f"
LOCK = OUT + "/rules.lock.txt"
MODEL = "RUADHSNQIMGOWB"
CANDIDATE_RULES = "SNQIMB"                        # правила-кандидаты: что держится только ими - отчитывается
CONTEXT_RECORDS = {("IDT_FARM", i) for i in range(27, 38)}   # роль ROOF записи, а в WESTOWN_BAF_01 - стойка
UNSUP_ROLES = {"HULL", "HULL_NB", "CROWN", "TRUNK"}           # суда и деревья - вне пилота зданий
MIN_UP = 30
CODE = ["tools/collapse_census.py", "tools/collapse_v2.py", "tools/collapse_v3.py", "tools/collapse_summary.py",
        "tools/collapse_pilot.py", "tools/collapse_holdout.py"]
DATA = S.DATA + ["census/collapse/stage0f/holdout.lock.txt"]
PILOT = OUT + "/pilot_blocks.tsv"
HOLD = "census/collapse/holdout"


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


# ------------------------------------------------------------------ неизвестное и неподдерживаемое

def unknown(p, kind, disp):
    """Причина, по которой роль части не установлена, или None."""
    s, i = p["set"].upper(), p["idx"]
    if (s, i, kind) in disp:
        return "спорная роль %s:%d" % (s, i)
    if (s, i) in CONTEXT_RECORDS:
        return "роль по месту %s:%d" % (s, i)
    if p.get("role") in UNSUP_ROLES:
        return "роль %s" % p["role"]
    return None


def light_beam(blk, sup0, info):
    """Лёгкий настил (полоса уже 3 клеток), который держится балкой, а не прямо и не консолью."""
    out = set()
    for z in range(1, blk.sz):
        floors = blk.lv[z]["f"]
        for xy in V.light_floors(set(floors)):
            key = floors[xy]
            dr, cd, bl = info.get(key, (None, None, None))
            if key in sup0 and not dr and (cd is None or cd > 2):
                out.add(key)
    return out


def near(cells):
    out = set()
    for x, y, z in cells:
        out.update(((x, y, z), (x + 1, y, z), (x - 1, y, z), (x, y + 1, z), (x, y - 1, z), (x, y, z + 1),
                    (x, y, z - 1)))
    return out


class Base:
    """Исходное состояние блока или карты для серии сценариев: опоры, лёгкий настил на балке, части по клеткам."""

    def __init__(self, blk, disp, vessel=False, ver=None):
        self.blk, self.disp, self.vessel, self.ver = blk, disp, vessel, ver
        self.sup0, info = T.evaluate3(blk, frozenset(), MODEL)
        self.light = light_beam(blk, self.sup0, info)
        self.by_cell = collections.defaultdict(list)
        for key in blk.parts:
            for c in T.part_cells(key):
                self.by_cell[c].append(key)
        self.alt0 = {e: T.evaluate3(blk, frozenset(), MODEL.replace(e, ""))[0] for e in CANDIDATE_RULES}

    def judge(self, removed):
        blk = self.blk
        removed = frozenset(removed)
        sup, _ = T.evaluate3(blk, removed, MODEL)
        fallen = {k for k in self.sup0 if k not in sup and k not in removed and k[3] > 0}
        ev_cells = {c for k in fallen | removed for c in T.part_cells(k)}
        zone = {k for c in near(ev_cells) for k in self.by_cell.get(c, ())}
        why = collections.Counter()
        if self.vessel:
            why["судно"] += 1
        for key in zone:
            u = unknown(blk.parts[key], key[0], self.disp)
            if u:
                why[u] += 1
            if key[3] > 0 and key not in self.sup0:
                why["рядом висело до боя"] += 1
            if key in self.light:
                why["лёгкий настил на балке"] += 1
        for key in fallen:
            for x, y, z in T.part_cells(key):
                if x <= 0 or y <= 0 or x >= blk.sx - 1 or y >= blk.sy - 1:
                    why["край" if self.ver is None else "край карты"] += 1
                if self.ver is not None and (x, y, z) not in self.ver:
                    why["непроверенная клетка"] += 1
        deps = []
        for e in CANDIDATE_RULES:
            s_e, _ = T.evaluate3(blk, removed, MODEL.replace(e, ""))
            f_e = {k for k in self.alt0[e] if k not in s_e and k not in removed and k[3] > 0}
            if f_e != fallen:
                deps.append(e)
        return {"status": "UNSUPPORTED" if why else "OK", "fallen": fallen, "why": dict(why), "depends_on": deps,
                "sup": sup}


# ------------------------------------------------------------------ отбор

def map_stats(roles, g, disp):
    """По 90 картам: для каждого (террейн, блок) - мест, частей выше земли и висящих в его проверенных клетках."""
    import collapse_battles as cb
    d = cb.Data(V.game_args())
    st = collections.defaultdict(collections.Counter)
    names = sorted(n[:-4] + ".sav" for n in os.listdir(V.OUT + "/source") if n.endswith(".pkl"))
    for name in names:
        m, src = V.load_map(d, name, roles)
        ver = V.verified_cells(d, name, m, src)
        sup, _ = T.evaluate3(m, frozenset(), MODEL)
        seen = set()
        for c, tb in ver.items():
            if tb not in seen:
                seen.add(tb)
                st[(tb[0].upper(), tb[1].upper())]["maps"] += 1
        for key in m.parts:
            if key[3] == 0:
                continue
            c = (key[1], key[2], key[3])
            if c in ver:
                tb = (ver[c][0].upper(), ver[c][1].upper())
                st[tb]["up"] += 1
                if key not in sup:
                    st[tb]["hung"] += 1
        print("  карта", name, flush=True)
    return st


def cmd_candidates():
    roles = V.load_roles()
    g, low = S.groups()
    disp = S.disputed_records()
    vs = T.vessels()
    st = map_stats(roles, g, disp)
    rows = []
    n = 0
    t0 = time.time()
    for tname, kind, t, bname, blk, err, cache in cc.all_blocks(V.game_args()):
        if blk is None or blk.sz < 2 or g.get(tname.upper()) != "1" or tname.upper() in low:
            continue
        if (tname.upper(), bname.upper()) in vs:
            continue
        V.apply_roles(blk, roles)
        n += 1
        up = [k for k in blk.parts if k[3] > 0]
        if len(up) < MIN_UP:
            continue
        unk = collections.Counter(u for k, p in blk.parts.items() for u in [unknown(p, k[0], disp)] if u)
        sup0, info = T.evaluate3(blk, frozenset(), MODEL)
        hung = [k for k in up if k not in sup0]
        if hung or unk:
            continue
        light = light_beam(blk, sup0, info)
        only = {}
        for e in CANDIDATE_RULES:
            s2, _ = T.evaluate3(blk, frozenset(), MODEL.replace(e, ""))
            only[e] = sum(1 for k in up if k in sup0 and k not in s2)
        ms = st.get((tname.upper(), bname.upper()), collections.Counter())
        rows.append([tname, bname, blk.sx, blk.sy, blk.sz, len(up), len(light), ms["maps"], ms["up"], ms["hung"]] +
                    [only[e] for e in CANDIDATE_RULES])
        if n % 200 == 0:
            print("  блоков %d, %.0f с" % (n, time.time() - t0), flush=True)
    os.makedirs(OUT, exist_ok=True)
    cc.write_tsv(OUT + "/pilot_candidates.tsv",
                 ["terrain", "block", "sx", "sy", "sz", "parts_up", "light_beam", "maps", "maps_up", "maps_hung"] +
                 ["only_" + e for e in CANDIDATE_RULES], rows)
    print("групп 1 блоков", n, "кандидатов (без висящего и неизвестных ролей, верх >= %d)" % MIN_UP, len(rows))
    print("из них на 90 картах с висящим 0 и без лёгкого настила на балке:",
          sum(1 for r in rows if r[7] and not r[9] and not r[6]))


# ------------------------------------------------------------------ здания пилота

def read_tsv(path):
    with open(path, encoding=ENC) as f:
        lines = f.read().splitlines()
    head = lines[0].split("\t")
    return [dict(zip(head, ln.split("\t"))) for ln in lines[1:] if ln.strip() and not ln.startswith("#")]


def pilot_blocks(roles):
    rows = read_tsv(PILOT)
    blocks = V.load_blocks(rows, roles)
    return rows, blocks


def cmd_geom():
    roles = V.load_roles()
    rows, blocks = pilot_blocks(roles)
    out = []
    for r in rows:
        blk = blocks[(r["terrain"].upper(), r["block"].upper())]
        sup0, _ = T.evaluate3(blk, frozenset(), MODEL)
        out.append(V.geom_text(blk))
        for e in "QIMSN":
            s2, _ = T.evaluate3(blk, frozenset(), MODEL.replace(e, ""))
            only = sorted(k for k in blk.parts if k[3] > 0 and k in sup0 and k not in s2)
            if only:
                out.append("ПРОВЕРИТЬ %s: части, которые держит только правило %s: %s" % (
                    r["block"], e, T.compress(only)))
        out.append("")
    with open(OUT + "/pilot_geom.txt", "w", encoding=ENC) as f:
        f.write("\n".join(out) + "\n")
    print("записано", OUT + "/pilot_geom.txt", len(rows), "зданий")


# ------------------------------------------------------------------ замок

def expect_files():
    return sorted(OUT + "/" + n for n in os.listdir(OUT) if n.startswith("expect_") and n.endswith(".tsv"))


def cmd_lock():
    lines = ["версия модели M0f обрушения, записано %s - до прогона сценариев и отложенных карт" %
             time.strftime("%Y-%m-%d %H:%M:%S"),
             "флаги %s (collapse_v3.evaluate3); E, J, L не входят" % MODEL,
             "параметры (экспериментальные): C=2 L=12 order=2 cp=1 LINTEL=%d L_TARP=%d L_ROOF=%d C_CANOPY=%d" % (
                 V.LINTEL, V.L_TARP, T.L_ROOF, T.C_CANOPY),
             "правила-кандидаты: %s; неизвестные роли: спорные и непросмотренные column/truss, IDT_FARM 27-37 (по месту), "
             "%s" % (CANDIDATE_RULES, ", ".join(sorted(UNSUP_ROLES)))]
    for p in CODE + DATA + [PILOT] + expect_files():
        lines.append("%s sha256 %s" % (p, sha(p)))
    with open(LOCK, "w", encoding=ENC) as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


def check_lock(extra=()):
    if not os.path.exists(LOCK):
        raise SystemExit("нет замка %s - сначала lock" % LOCK)
    txt = open(LOCK, encoding=ENC).read()
    bad = [p for p in CODE + DATA + [PILOT] + list(extra) if sha(p) not in txt]
    if bad:
        raise SystemExit("замок НЕ СОВПАДАЕТ: " + ", ".join(bad))
    print("замок M0f совпадает")


# ------------------------------------------------------------------ сценарии

def verdict(e, blk, base, res):
    rm = cc.select(blk, e["remove"])
    mf = cc.select(blk, e.get("must_fall", "")) - rm
    ms = cc.select(blk, e.get("must_stand", "")) - rm
    stood = sorted(k for k in mf if k in res["sup"] and k in base.sup0)
    fell = sorted(k for k in ms if k not in res["sup"] and k in base.sup0)
    v = "PASS" if not stood and not fell else "FAIL"
    if not mf and not ms:
        v = "EMPTY"
    return v, stood, fell, mf, ms


def cmd_scen(path):
    check_lock([path])
    roles = V.load_roles()
    disp = S.disputed_records()
    expect = read_tsv(path)
    blocks = V.load_blocks(expect, roles)
    bases = {}
    out = {}
    cnt = collections.Counter()
    for e in expect:
        key = (e["terrain"].upper(), e["block"].upper())
        blk = blocks[key]
        if key not in bases:
            bases[key] = Base(blk, disp)
        base = bases[key]
        rm = cc.select(blk, e["remove"])
        res = base.judge(rm)
        v, stood, fell, mf, ms = verdict(e, blk, base, res)
        shown = "UNSUPPORTED" if res["status"] == "UNSUPPORTED" else v
        cnt[(shown, v)] += 1
        out[e["id"]] = {"shown": shown, "model_verdict": v, "why": res["why"], "depends_on": res["depends_on"],
                        "fallen": T.compress(sorted(res["fallen"])), "n_fallen": len(res["fallen"]),
                        "stood": T.compress(stood), "fell": T.compress(fell), "must_fall": len(mf),
                        "must_stand": len(ms)}
        print("%-10s %-11s (модель %s) упало %d | устояло из должных упасть %d/%d, упало из должных стоять %d/%d %s %s" % (
            e["id"], shown, v, len(res["fallen"]), len(stood), len(mf), len(fell), len(ms),
            "зависит от " + "".join(res["depends_on"]) if res["depends_on"] else "",
            json.dumps(res["why"], ensure_ascii=False) if res["why"] else ""), flush=True)
    tag = os.path.splitext(os.path.basename(path))[0]
    with open(OUT + "/scen_%s.json" % tag, "w", encoding=ENC) as f:
        json.dump({"file": path, "sha256": sha(path), "model": MODEL,
                   "count": {"%s|%s" % k: v for k, v in cnt.items()}, "result": out}, f, ensure_ascii=False, indent=1)
    print("итог (показано|модель):", {"%s|%s" % k: v for k, v in sorted(cnt.items())})


# ------------------------------------------------------------------ отложенные карты

def tuning_blocks():
    """Имена блоков MAP, найденных на 90 картах настройки."""
    out = set()
    for n in os.listdir(V.OUT + "/source"):
        if n.endswith(".pkl"):
            with open(V.OUT + "/source/" + n, "rb") as f:
                src = pickle.load(f)
            out.update(b[1].upper() for b in src.get("blocks", ()))
    return out


def shift_select(blk_map, toks, ox, oy, oz, ref):
    """Части карты, соответствующие частям блока по выражению toks (сдвиг места)."""
    keys = cc.select(ref, toks)
    return {(k, x + ox, y + oy, z + oz) for k, x, y, z in keys if (k, x + ox, y + oy, z + oz) in blk_map.parts}


def cmd_holdout(path=None):
    check_lock([path] if path else [])
    import collapse_battles as cb
    import collapse_holdout as H
    roles = V.load_roles()
    g, low = S.groups()
    disp = S.disputed_records()
    known = tuning_blocks()
    pilot = {(r["terrain"].upper(), r["block"].upper()) for r in read_tsv(PILOT)}
    expect = read_tsv(path) if path else []
    ref_blocks = V.load_blocks(expect, roles) if expect else {}
    d = cb.Data(H.game_args())
    cat = {"известный": collections.Counter(), "новый": collections.Counter()}
    pil = collections.Counter()
    scen = collections.Counter()
    rows, srows = [], []
    for name in H.names():
        m, src = H.load_map(d, name, roles, V.apply_roles)
        ver = H.verified_cells(d, name, m, src)
        base = Base(m, disp, ver=ver)
        sup = base.sup0
        for key in m.parts:
            if key[3] == 0:
                continue
            c = (key[1], key[2], key[3])
            if c not in ver:
                cat["новый"]["верх непроверенный"] += 1
                if key not in sup:
                    cat["новый"]["висит в непроверенной клетке"] += 1
                continue
            bt, bn = ver[c][0].upper(), ver[c][1].upper()
            kk = "известный" if bn in known else "новый"
            cat[kk]["верх"] += 1
            if (bt, bn) in pilot:
                pil["верх"] += 1
            if key in sup:
                continue
            vessel = g.get(bt) in ("2", "3")
            cl, wh = S.classify(m, key, sup, vessel, bt in low, disp, m.sx, m.sy)
            cl = {"край": "край карты"}.get(cl, cl)
            cat[kk][cl] += 1
            if (bt, bn) in pilot:
                pil["висит " + cl] += 1
                rows.append([name, bt, bn, cl, wh, "%s:%d:%d:%d" % key])
        for e in expect:
            ek = (e["terrain"].upper(), e["block"].upper())
            ref = ref_blocks[ek]
            for bt, bn, ox, oy, oz in src["blocks"]:
                if (bt.upper(), bn.upper()) != ek:
                    continue
                rm = shift_select(m, e["remove"], ox, oy, oz, ref)
                if not rm:
                    continue
                res = base.judge(rm)
                mf = shift_select(m, e.get("must_fall", ""), ox, oy, oz, ref) - rm
                ms = shift_select(m, e.get("must_stand", ""), ox, oy, oz, ref) - rm
                stood = [k for k in mf if k in res["sup"] and k in sup]
                fell = [k for k in ms if k not in res["sup"] and k in sup]
                v = "PASS" if not stood and not fell else "FAIL"
                shown = "UNSUPPORTED" if res["status"] == "UNSUPPORTED" else v
                scen[(shown, v)] += 1
                srows.append([name, e["id"], ox, oy, oz, shown, v, len(res["fallen"]), len(stood), len(mf),
                              len(fell), len(ms), json.dumps(res["why"], ensure_ascii=False),
                              "".join(res["depends_on"])])
        print(name, src["terrain"], {k: sum(v.values()) for k, v in cat.items()}, flush=True)
    cc.write_tsv(OUT + "/holdout_pilot_hung.tsv", ["save", "terrain", "block", "category", "why", "part"], rows)
    if expect:
        cc.write_tsv(OUT + "/holdout_scen.tsv", ["save", "id", "ox", "oy", "oz", "shown", "model", "fallen", "stood",
                                                 "must_fall", "fell", "must_stand", "why", "depends_on"], srows)
    res = {"model": MODEL, "maps": len(H.names()), "by_block_kind": {k: dict(v) for k, v in cat.items()},
           "pilot_blocks": dict(pil), "scenarios": {"%s|%s" % k: v for k, v in sorted(scen.items())}}
    with open(OUT + "/holdout_M0f.json", "w", encoding=ENC) as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    cmd = sys.argv[1]
    if cmd == "candidates":
        cmd_candidates()
    elif cmd == "geom":
        cmd_geom()
    elif cmd == "lock":
        cmd_lock()
    elif cmd == "scen":
        cmd_scen(sys.argv[2])
    elif cmd == "holdout":
        cmd_holdout(sys.argv[2] if len(sys.argv) > 2 else None)


if __name__ == "__main__":
    main()
