"""Пилот 2 обрушения: невидимые проверки плана docs/research/building-collapse-pilot2-plan-2026-10-08.md.

Здания пилота ищутся при генерации карты, список - ключ сейва collapsePilot; загрузка берёт его,
а не ищет заново. Каждая проверка - с контролем (R-086): прогон, где проверяемое не работает,
обязан дать другой исход.

  py -3.13 tools/collapse_pilot2_run.py hit      первое попадание не отключает обвал (контроль - сборка пилота 1)
  py -3.13 tools/collapse_pilot2_run.py reload   частичный обвал, сейв, загрузка, второй обвал - как без загрузки
  py -3.13 tools/collapse_pilot2_run.py badkey   неверный ключ: rejected, бой доигран
  py -3.13 tools/collapse_pilot2_run.py oldsave  сейв без ключа: целое здание найдено, частичное нет
  py -3.13 tools/collapse_pilot2_run.py units    юнит 2x2 и летающий над снятым полом (контроль - боец 1x1)
  py -3.13 tools/collapse_pilot2_run.py occupied нижний боец окружён, на него падает верхний
  py -3.13 tools/collapse_pilot2_run.py fire     опору снимает огонь (контроль - без огня)
  py -3.13 tools/collapse_pilot2_run.py chain    взрыв взрывчатой части (контроль - взрыв рядом)
  py -3.13 tools/collapse_pilot2_run.py ai       время ходов ИИ с обвалом, вкл против выкл, повторы чередуясь
  py -3.13 tools/collapse_pilot2_run.py shift    ключ сдвинут: на чужие блоки - rejected; на пустое место и второй бункер - проходит (предел)
  py -3.13 tools/collapse_pilot2_run.py ruin     разбито больше половины: сейв, загрузка, второй обвал - как без загрузки (контроль - порог половины)
  py -3.13 tools/collapse_pilot2_run.py chain2   тот же взрыв при выключенной опции: карта до модели совпадает
  py -3.13 tools/collapse_pilot2_run.py fall     занятая клетка: сейв сразу после падения (контроль - опция выкл)
  py -3.13 tools/collapse_pilot2_run.py ident    режим 0, k=1 и k=4: сборка пилота 2 против сборки пилота 1

Сборка - build-ai-collapse (OXCE_AI_DEV=ON); контроль - сборка пилота 1 (--p1-build - каталог сборки, или OXCE_COLLAPSE_P1_BUILD).
Итог каждого прогона - census/collapse/pilot2/runs/<имя>/summary.json, сводка проверки - <проверка>.json рядом.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import collapse_pilot_run as CP  # noqa: E402  (ставит OXCE_AI_BUILD и обёртки ai_probe)

ai_probe = CP.ai_probe
ROOT = CP.ROOT
ENC = CP.ENC
OUT = ROOT / "census/collapse/pilot2/runs"
NEW_EXE = Path(ai_probe.EXE)
FARM = "STR_LOC_DOOMED_FARM"  # амбар на зерне 24 (поиск при генерации, 08.10)
BASE = "STR_GOVT_BASE_DEFENSE"   # бункер на зерне 6 (два целых)
SCEN_CELLS = {"barn": 79, "bunker": 49}
OLD_FARM = ROOT /"census/collapse/holdout3/battles/collapse_STR_LOC_DOOMED_FARM_24.sav"


class _Exe:
    """ai_probe.EXE на поток: контрольная сборка идёт рядом с новой."""
    tl = threading.local()

    def cur(self):
        return Path(getattr(self.tl, "exe", NEW_EXE))

    def is_file(self):
        return self.cur().is_file()

    @property
    def parent(self):
        return self.cur().parent

    def __str__(self):
        return str(self.cur())

    __fspath__ = __str__


EXE = _Exe()
ai_probe.EXE = EXE
P1_EXE = None
P2H_EXE = None  # сборка 993474e93: загрузка с порогом половины частей - контроль ruin


# ------------------------------------------------------------------ прогон и разбор

def run(name, save=None, seed=None, mission=None, env=None, on=True, turns=1, build="new"):
    EXE.tl.exe = {"new": NEW_EXE, "p1": P1_EXE, "p2h": P2H_EXE}[build]
    CP._collapse_on.value = on
    CP._collapse_on.env = dict(env or {})
    # сейв сразу после падения (OXCE_COLLAPSE_FALL_SAVE) пишется в папку пользователя прогона: прежний убрать (R-246)
    fall = Path(ai_probe.WORK) / ("p2_" + name) / "piratez" / "fall.asav"
    if fall.exists():
        fall.unlink()
    r = ai_probe.run(save, turns=turns, save_as="after.asav", name="p2_" + name, timeout=900, seed=seed,
                     mission=mission)
    dest = OUT / name
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    if r.log and Path(r.log).exists():
        shutil.copyfile(r.log, dest / "openxcom.log")
    saved = None
    if r.saved:
        saved = dest / "after.asav"
        shutil.copyfile(r.saved, saved)
    fall_saved = None
    if fall.exists():
        fall_saved = dest / "fall.asav"
        shutil.copyfile(fall, fall_saved)
    s = parse(dest / "openxcom.log")
    s.update({"name": name, "build": build, "on": on, "turns": turns, "seed": seed, "mission": mission,
              "save_in": str(save) if save else None, "env": env or {}, "seconds": round(r.seconds, 1),
              "finished": r.finished, "saved": str(saved) if saved else None,
              "fall_saved": str(fall_saved) if fall_saved else None,
              "key_after": key_of(saved) if saved else None})
    (dest / "summary.json").write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding=ENC)
    return s


NUM = r"([\d.e+-]+)"


def parse(log):
    lines = CP.collapse_lines(log)
    text = Path(log).read_text(encoding=ENC, errors="replace") if Path(log).exists() else ""
    s = {"lines": lines, "found": [], "kept": [], "rejected": [], "not_whole": [], "settles": [], "model": [],
         "units": [], "terrain": [], "fall": [], "errors":[l.split("\t")[-1] for l in text.splitlines()
                                 if ("\t[ERROR]" in l or "[FATAL]" in l) and "misses type_id" not in l][:20],
         "stalls": [l.split("\t")[-1] for l in text.splitlines() if "HD stall" in l][:50]}
    for l in lines:
        m = re.match(r"\[COLLAPSE\] (found|kept) (\w+) \((.+)\) at (\d+),(\d+),(\d+): (\d+) of (\d+)", l)
        if m:
            f = re.search(r"parts in place, (\d+) foreign", l)
            s[m.group(1)].append({"label": m.group(2), "name": m.group(3), "at": list(map(int, m.group(4, 5, 6))),
                                  "n": int(m.group(7)), "all": int(m.group(8)),
                                  "foreign": int(f.group(1)) if f else None})
        m = re.match(r"\[COLLAPSE\] debug: before model settle (\d+) \((.+)\): terrain (\w+)", l)
        if m:
            s["terrain"].append({"settle": int(m.group(1)), "why": m.group(2), "hash": m.group(3)})
        if l.startswith(("[COLLAPSE] debug: fall over", "[COLLAPSE] debug: fall settled")):
            s["fall"].append(l)
        m = re.match(r"\[COLLAPSE\] rejected (.*) at (-?\d+),(-?\d+),(-?\d+) \(format (-?\d+)\): (.+)", l)
        if m:
            s["rejected"].append({"name": m.group(1), "at": list(map(int, m.group(2, 3, 4))),
                                  "format": int(m.group(5)), "why": m.group(6)})
        if l.startswith("[COLLAPSE] not whole"):
            s["not_whole"].append(l)
        m = re.match(r"\[COLLAPSE\] (.+) (\w+) at (\d+),(\d+),(\d+): removed (\d+), fell (\d+) \(f (\d+) w (\d+) n (\d+) o (\d+)\)"
                     r".*falling units (\d+); scan %s ms, eval %s ms, apply %s ms, light\+fov %s ms" % (NUM, NUM, NUM, NUM), l)
        if m:
            g = m.groups()
            s["settles"].append({"why": g[0], "label": g[1], "at": list(map(int, g[2:5])), "removed": int(g[5]),
                                 "fell": int(g[6]), "falling_units": int(g[11]),
                                 "ms": {"scan": float(g[12]), "eval": float(g[13]), "apply": float(g[14]),
                                        "light_fov": float(g[15])}})
        m = re.match(r"\[COLLAPSE\] debug: model (\w+) at (\d+),(\d+),(\d+) removed=([\d,]*) fell=([\d,]*)", l)
        if m:
            s["model"].append({"label": m.group(1), "at": list(map(int, m.group(2, 3, 4))),
                               "removed": [int(v) for v in m.group(5).split(",") if v],
                               "fell": [int(v) for v in m.group(6).split(",") if v]})
        if l.startswith("[COLLAPSE] debug:") and (" unit " in l or "item" in l or "fire" in l or "blast" in l
                                                  or "large" in l or "flying" in l or "hit " in l):
            s["units"].append(l)
        m = re.match(r"\[AIPROBE\] done: (\d+) AI turn\(s\), (\d+) ms real, (\d+) ms virtual", l)
        if m:
            s["ai"] = {"turns": int(m.group(1)), "ms_real": int(m.group(2)), "ms_virtual": int(m.group(3))}
        if l.startswith("[AIPROBE] stuck"):
            s["stuck"] = l
    return s


def key_of(save):
    """Ключ collapsePilot сейва как текст (None - ключа нет)."""
    t = Path(save).read_text(encoding="utf-8", errors="replace")
    m = re.search(r"(?m)^  collapsePilot:\n((?:    .*\n)*)", t)
    return m.group(0) if m else None


def edit_key(src, dst, fn):
    """Копия сейва с правленым ключом: fn(текст ключа) -> новый текст ('' - убрать)."""
    t = Path(src).read_text(encoding="utf-8")
    m = re.search(r"(?m)^  collapsePilot:\n((?:    .*\n)*)", t)
    if not m:
        raise SystemExit("в сейве нет ключа collapsePilot: %s" % src)
    new = t[:m.start()] + fn(m.group(0)) + t[m.end():]
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    Path(dst).write_bytes(new.encode("utf-8"))  # сейв читает yaml-cpp: без спецификации
    return dst


def parts_of(label, scenario, z, cells=None):
    """Номера частей сценария pilot_scen.tsv (как у движка) и сами ключи.
    Строки сценария разные по участку (unit_cells): берём участок пилота 1 (амбар c79, бункер c49)."""
    rows = CP.scen_rows(label, cells or SCEN_CELLS[label], {"%s:%d" % (scenario, z)})
    if not rows:
        raise SystemExit("нет сценария %s %s z%d" % (label, scenario, z))
    keys = [CP.kparse(s) for s in rows[0]["removed"].split()]
    idx = BLOCKS[label]["index"]
    return [idx[(CP.KIND[k[0]], k[1], k[2], k[3])] for k in keys], keys


def env_parts(var, label, nums):
    return {var: "%s:%s" % (label, ",".join(map(str, nums)))}


def env_tiles(var, label, tiles):
    return {var: "%s:%s" % (label, ";".join("%d,%d,%d" % t for t in tiles))}


def check_model(s):
    """Каждый обход движка против эталона M0j3 на том же входе."""
    out = []
    for m in s["model"]:
        parts = BLOCKS[m["label"]]["parts"]
        key = lambda i: ("fwno"[parts[i][0]],) + tuple(parts[i][1:4])
        ref = sorted(BLOCKS[m["label"]]["index"][(CP.KIND[k[0]],) + k[1:]]
                     for k in CP.model_fell(m["label"], [key(i) for i in m["removed"]]))
        out.append({"at": m["at"], "removed": len(m["removed"]), "fell": len(m["fell"]), "ref": len(ref),
                    "same": sorted(m["fell"]) == ref})
    return out


def final_gone(s, label):
    """Части здания, которых нет к последнему обходу с отладкой модели: снятые плюс упавшие."""
    ms = [m for m in s["model"] if m["label"] == label]
    if not ms:
        return None
    return sorted(set(ms[-1]["removed"]) | set(ms[-1]["fell"]))


def collapse_pass(s, label, stand):
    """Обход обвала: первый обход модели, на входе которого все снятые стендом части.
    Возвращает (вход модели, упавшее) - номера частей по порядку."""
    for m in s["model"]:
        if m["label"] == label and set(stand) <= set(m["removed"]):
            return sorted(m["removed"]), sorted(m["fell"])
    return None


def short(s):
    return {"name": s["name"], "build": s["build"], "on": s["on"], "finished": s["finished"],
            "found": [(f["label"], f["at"], f["n"], f["all"], f["foreign"]) for f in s["found"]],
            "kept": [(f["label"], f["at"], f["n"], f["all"]) for f in s["kept"]],
            "rejected": [(r["name"], r["at"], r["why"]) for r in s["rejected"]],
            "not_whole": len(s["not_whole"]),
            "settles": [(x["why"], x["label"], x["removed"], x["fell"], x["falling_units"]) for x in s["settles"]],
            "model_check": check_model(s), "errors": s["errors"], "stuck": s.get("stuck"), "ai": s.get("ai"),
            "key_after": bool(s["key_after"]), "seconds": s["seconds"]}


def report(check, res):
    p = OUT / (check + ".json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding=ENC)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    print("->", p)


def par(fns, jobs=4):
    with ThreadPoolExecutor(max_workers=jobs) as ex:
        return list(ex.map(lambda f: f(), fns))


# ------------------------------------------------------------------ проверки

def c_hit(a):
    """Попадание, после которого здание стоит, - и потом снятие опоры: обвал есть (пилот 1 его терял)."""
    hit, _ = parts_of("barn", "CORNER", 2)
    all1, all1k = parts_of("barn", "ALL", 1)
    s0 = run("hit_save", seed=24, mission=FARM, env={**env_parts("OXCE_COLLAPSE_HIT", "barn", hit),
                                                     "OXCE_COLLAPSE_MODEL": "1"})
    if not s0["saved"]:
        raise SystemExit("нет сейва после попадания")
    rm = {**env_parts("OXCE_COLLAPSE_REMOVE", "barn", all1), "OXCE_COLLAPSE_AT": "1"}
    res = par([lambda: run("hit_load_new", save=s0["saved"], env=rm),
               lambda: run("hit_load_p1", save=s0["saved"], env=rm, build="p1"),
               lambda: run("hit_cont_new", seed=24, mission=FARM,
                           env={**env_parts("OXCE_COLLAPSE_HIT", "barn", hit), **rm})])
    exp = CP.model_fell("barn", all1k + [k for k in parts_of("barn", "CORNER", 2)[1]])
    report("hit", {"hit_parts": len(hit), "remove_parts": len(all1), "model_fell_ref": len(exp),
                   "runs": [short(s0)] + [short(s) for s in res]})


def c_reload(a):
    """Частичный обвал, сейв, загрузка, снятие опоры - против того же без загрузки."""
    hit, hitk = parts_of("barn", "CORNER", 1)
    all1, _ = parts_of("barn", "ALL", 1)
    henv = env_parts("OXCE_COLLAPSE_HIT", "barn", hit)
    rm = env_parts("OXCE_COLLAPSE_REMOVE", "barn", all1)
    mod = {"OXCE_COLLAPSE_MODEL": "1"}
    s1, cont = par([lambda: run("reload_s1", seed=24, mission=FARM, env={**henv, **mod}),
                    lambda: run("reload_cont", seed=24, mission=FARM,
                                env={**henv, **rm, **mod, "OXCE_COLLAPSE_AT": "2"}, turns=2)])
    if not s1["saved"]:
        raise SystemExit("нет сейва S1")
    s2 = run("reload_s2", save=s1["saved"], env={**rm, **mod, "OXCE_COLLAPSE_AT": "1"})
    p_cont, p_s2 = collapse_pass(cont, "barn", all1), collapse_pass(s2, "barn", all1)
    res = {"partial_ref": len(CP.model_fell("barn", hitk)), "runs": [short(s1), short(cont), short(s2)]}
    if p_cont and p_s2:
        res.update({"input_cont": len(p_cont[0]), "input_reload": len(p_s2[0]),
                    "same_input": p_cont[0] == p_s2[0],
                    "fell_cont": len(p_cont[1]), "fell_reload": len(p_s2[1]),
                    "same_fell": p_cont[1] == p_s2[1],
                    "input_only_cont": sorted(set(p_cont[0]) - set(p_s2[0])),
                    "input_only_reload": sorted(set(p_s2[0]) - set(p_cont[0])),
                    "fell_only_cont": sorted(set(p_cont[1]) - set(p_s2[1])),
                    "fell_only_reload": sorted(set(p_s2[1]) - set(p_cont[1]))})
    else:
        res["error"] = "нет обхода обвала: cont %s, reload %s" % (bool(p_cont), bool(p_s2))
    report("reload", res)


def c_badkey(a):
    src = fmt2("fmt2_farm", 24, FARM, a.refresh)
    d = OUT / "_saves"
    cases = {
        "badkey_name": lambda k: k.replace("STR_LOC_DOOMED_FARM_24@", "STR_NO_SUCH_BUILDING@"),
        "badkey_out": lambda k: re.sub(r"at: \[\d+,\s*\d+,\s*\d+\]", "at: [200, 200, 0]", k),
        "badkey_ver": lambda k: re.sub(r"version: \d+", "version: 99", k),
        "badkey_garbage": lambda k: "  collapsePilot:\n    version: 1\n    buildings:\n      - model: 7\n        at: [1]\n",
        "badkey_scalar": lambda k: "  collapsePilot: junk\n",
        "badkey_vertext": lambda k: re.sub(r"version: \d+", "version: abc", k),
    }
    saves = {n: edit_key(src, d / (n + ".asav"), f) for n, f in cases.items()}
    res = par([lambda n=n: run(n, save=saves[n], env={"OXCE_COLLAPSE_MODEL": "1"}) for n in cases])
    report("badkey", {"runs": [short(s) for s in res]})


def c_oldsave(a):
    src = OUT / "reload_s1/after.asav"
    if not src.exists():
        raise SystemExit("сначала reload (нужен сейв с частичным обвалом)")
    nokey = edit_key(src, OUT / "_saves/oldsave_partial.asav", lambda k: "")
    res = par([lambda: run("oldsave_whole", save=OLD_FARM, env={"OXCE_COLLAPSE_MODEL": "1"}),
               lambda: run("oldsave_partial", save=nokey, env={"OXCE_COLLAPSE_MODEL": "1"}),
               lambda: run("oldsave_partial_key", save=src, env={"OXCE_COLLAPSE_MODEL": "1"})])
    report("oldsave", {"runs": [short(s) for s in res]})


def c_units(a):
    all1, _ = parts_of("barn", "ALL", 1)
    rm = {**env_parts("OXCE_COLLAPSE_REMOVE", "barn", all1), "OXCE_COLLAPSE_AT": "1"}
    seeds = [int(v) for v in a.seeds.split(",")]
    big, fly = [(5, 5, 1)], [(6, 6, 1)]
    fns = []
    for sd in seeds:
        fns.append(lambda sd=sd: run("units_big_fly_%d" % sd, seed=sd, mission=FARM,
                                     env={**rm, **env_tiles("OXCE_COLLAPSE_BIG", "barn", big),
                                          **env_tiles("OXCE_COLLAPSE_FLY", "barn", fly)}, turns=1))
        fns.append(lambda sd=sd: run("units_ctl_%d" % sd, seed=sd, mission=FARM,
                                     env={**rm, **env_tiles("OXCE_COLLAPSE_UNIT", "barn", big + fly)}, turns=1))
    res = par(fns)
    report("units", {"runs": [dict(short(s), stand=s["units"]) for s in res]})


def c_big(a):
    """2x2 на бункере (зерно 6 - бронемашина STR_GOVT_ARMORED_CAR): угол машины на 5,5,1, квадрат 5..6 x 5..6;
    под квадратом на z0 только пол, модель от снятия пола z1 этого квадрата ничего не роняет (p2_big_pick)."""
    idx = BLOCKS["bunker"]["index"]
    sq = [(5, 5), (6, 5), (5, 6), (6, 6)]
    fl = lambda cells: env_parts("OXCE_COLLAPSE_REMOVE", "bunker", [idx[(CP.KIND["f"], x, y, 1)] for x, y in cells])
    car = {**env_tiles("OXCE_COLLAPSE_BIG", "bunker", [(5, 5, 1)]), "OXCE_COLLAPSE_AT": "1"}
    res = par([lambda: run("big_all", seed=6, mission=BASE, env={**car, **fl(sq)}),
               lambda: run("big_half", seed=6, mission=BASE, env={**car, **fl(sq[:2])}),
               lambda: run("big_none", seed=6, mission=BASE, env={**car, "OXCE_COLLAPSE_MODEL": "1"})])
    report("big", {"runs": [dict(short(s), stand=s["units"]) for s in res]})


def c_occupied(a):
    all1, _ = parts_of("barn", "ALL", 1)
    low = (5, 6, 0)
    ring = [(low[0] + dx, low[1] + dy, 0) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy]
    rm = {**env_parts("OXCE_COLLAPSE_REMOVE", "barn", all1), "OXCE_COLLAPSE_AT": "1"}
    res = par([lambda: run("occupied_ring", seed=24, mission=FARM,
                           env={**rm, **env_tiles("OXCE_COLLAPSE_UNIT", "barn", [(5, 6, 1), low] + ring)}),
               lambda: run("occupied_open", seed=24, mission=FARM,
                           env={**rm, **env_tiles("OXCE_COLLAPSE_UNIT", "barn", [(5, 6, 1), low])})])
    out = []
    for s in res:
        d = dict(short(s), stand=s["units"])
        if s["saved"]:
            us, _ = CP.sav_entities(s["saved"])
            d["units_after"] = {i: (u.get("position"), u.get("status")) for i, u in us.items()
                                if u.get("faction") == "0"}
        out.append(d)
    report("occupied", {"runs": out})


def c_fire(a):
    win = [(x, y, 1) for x in (3, 4, 5) for y in (5, 6, 7)]
    fenv = {**env_tiles("OXCE_COLLAPSE_FIRE", "barn", win), "OXCE_COLLAPSE_AT": "1"}
    res = par([lambda: run("fire_on", seed=24, mission=FARM, env=fenv, turns=2),
               lambda: run("fire_ctl", seed=24, mission=FARM, env={"OXCE_COLLAPSE_MODEL": "1"}, turns=2)])
    report("fire", {"runs": [dict(short(s), stand=s["units"]) for s in res]})


def c_chain(a):
    benv = {"OXCE_COLLAPSE_AT": "1", "OXCE_COLLAPSE_BLAST_POWER": str(a.power), "OXCE_COLLAPSE_MODEL": "1"}
    if a.chain_at == "barn":
        # бункер модель не роняет ни при каком радиусе (p2_chain_pick); амбар - клетка 4,4,0 r2 роняет 11;
        # контроль R-086 - тот же взрыв при выключенной опции
        blast = env_tiles("OXCE_COLLAPSE_BLAST", "barn", [(4, 4, 0)])
        res = par([lambda: run("chain_barn_boom", seed=24, mission=FARM, env={**benv, **blast}),
                   lambda: run("chain_barn_off", seed=24, mission=FARM, env={**benv, **blast}, on=False)])
    else:
        res = par([lambda: run("chain_boom", seed=6, mission=BASE,
                               env={**benv, **env_tiles("OXCE_COLLAPSE_BLAST", "bunker", [(1, 7, 0)])}),
                   lambda: run("chain_ctl", seed=6, mission=BASE,
                               env={**benv, **env_tiles("OXCE_COLLAPSE_BLAST", "bunker", [(a.ctl_x, a.ctl_y, 0)])})])
    report("chain_" + a.chain_at, {"power": a.power, "runs": [dict(short(s), stand=s["units"]) for s in res]})


def c_ai(a):
    all1, _ = parts_of("barn", "ALL", 1)
    rm = {**env_parts("OXCE_COLLAPSE_REMOVE", "barn", all1), "OXCE_COLLAPSE_AT": "1"}
    out = []
    for rep in range(a.reps):
        order = [True, False] if rep % 2 == 0 else [False, True]
        for on in order:  # по одному: замер времени, рядом не идёт ничего своего
            s = run("ai_%s_%d" % ("on" if on else "off", rep), seed=24, mission=FARM, env=rm, on=on, turns=3)
            d = short(s)
            d["rep"] = rep
            d["light_fov_ms"] = [x["ms"] for x in s["settles"]]
            d["stalls"] = s["stalls"]
            out.append(d)
            print(d["name"], d["ai"], d["settles"], d["seconds"])
    report("ai", {"runs": out})


def c_ident(a):
    """Режим 0: сборка пилота 2 (опция выкл и вкл) против сборки пилота 1, k=1 и k=4; контроль - сейв с обвалом."""
    # обе сборки с OXCE_AI_DEV=ON: различаются только правкой пилота 2
    exes = {"p1": P1_EXE, "p1b": P1_EXE, "new": NEW_EXE, "newon": NEW_EXE}
    saves = {"farm": OUT / "hit_save/after.asav", "coll": OUT / "hit_load_new/after.asav"}
    d = OUT / "_ident"

    def one(b, sv, k):
        u = d / ("%s_%s_k%d" % (b, sv, k))
        if u.exists():
            shutil.rmtree(u)
        u.mkdir(parents=True)
        cmd = ["py", "-3.13", str(ROOT / "tools/game_hidden.py"), "--out", str(u / "shot.png"), "--save",
               str(saves[sv]), "--after", "110", "--key", "ctrl+289", "--exe", str(exes[b]), "--user", str(u),
               "--set", "oxceHdMode=0;oxceHdScale=%d;oxceCollapse=%s" % (k, "true" if b == "newon" else "false")]
        subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        return u / "piratez/hdtest000"

    def cmp(x, y):
        p = subprocess.run(["py", "-3.13", str(ROOT / "tools/hdtest_compare.py"), str(x), str(y)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        m = re.search(r"RESULT: (\w+)", p.stdout)
        return m.group(1) if m else "?", p.stdout[-1500:]

    jobs = [(b, sv, k) for k in (1, 4) for sv in ("farm", "coll") for b in ("p1", "p1b", "new", "newon")]
    dumps = dict(zip(jobs, par([lambda j=j: one(*j) for j in jobs], jobs=a.jobs)))
    res = []
    for k in (1, 4):
        for sv in ("farm", "coll"):
            for b in ("p1b", "new", "newon"):
                v, txt = cmp(dumps[("p1", sv, k)], dumps[(b, sv, k)])
                res.append({"k": k, "save": sv, "pair": "p1 vs " + b, "result": v, "tail": txt})
        v, txt = cmp(dumps[("p1", "farm", k)], dumps[("p1", "coll", k)])
        res.append({"k": k, "save": "farm vs coll", "pair": "p1 control", "result": v, "tail": txt})
    report("ident", {"pairs": res})


# ------------------------------------------------------------------ проверки загрузки без порога (09.10)

KEY_AT = r"at: \[\s*%d,\s*%d,\s*%d\s*\]"


def fmt2(name, seed, mission, refresh=False):
    """Сейв новой сборки с ключом формата 2 (отпечаток sig): бой без повреждений стенда, один ход."""
    p = OUT / name / "after.asav"
    if refresh or not p.exists():
        s = run(name, seed=seed, mission=mission, env={"OXCE_COLLAPSE_MODEL": "1"})
        if not s["saved"]:
            raise SystemExit("нет сейва %s" % name)
    k = key_of(p) or ""
    if "version: 2" not in k or "sig:" not in k:
        raise SystemExit("в сейве %s нет ключа формата 2:\n%s" % (p, k))
    return p


def move_at(old, new, count=1):
    return lambda k: re.sub(KEY_AT % old, "at: [%d,%d,%d]" % new, k, count=count)


def drop_entry(k, at):
    """Убрать из ключа запись здания с данным at (запись - строки от '- model:' до следующей)."""
    out, cur = [], []
    for l in k.splitlines(True):
        if l.lstrip().startswith("- "):
            if cur:
                out.append(cur)
            cur = [l]
        elif cur:
            cur.append(l)
        else:
            out.append([l])
    if cur:
        out.append(cur)
    keep = [e for e in out if not re.search(KEY_AT % at, "".join(e))]
    if len(keep) != len(out) - 1:
        raise SystemExit("в ключе нет ровно одной записи at %s:\n%s" % (at, k))
    return "".join("".join(e) for e in keep)


def to_format1(k):
    """Ключ формата 2 -> формат 1 сборки 993474e93 (без отпечатка)."""
    k = re.sub(r"version: \d+", "version: 1", k)
    return "".join(l for l in k.splitlines(True) if not l.lstrip().startswith("sig:"))


def c_shift(a):
    """Предел проверки ключа: на чужие блоки - отклонить; на пустое место и на другой экземпляр - проходит."""
    farm = fmt2("fmt2_farm", 24, FARM, a.refresh)
    base = fmt2("fmt2_base", 6, BASE, a.refresh)
    d = OUT / "_saves"
    barn = (28, 18, 0)
    cases = {
        # амбар 14x24 на карте 60x60: чужие блоки фермы
        "shift_foreign": (farm, move_at(barn, (0, 0, 0)), "rejected: foreign parts"),
        "shift_ground_a": (farm, move_at(barn, (0, 36, 0)), "?"),
        "shift_ground_b": (farm, move_at(barn, (46, 0, 0)), "?"),
        # бункер 10x10x4 на карте 80x60x9: над бункером пусто - пустое место, модель ничего не снимает
        "shift_air": (base, move_at((40, 50, 0), (40, 50, 5)), "kept 0 parts, model removes nothing"),
        "shift_foreign_b": (base, move_at((40, 50, 0), (10, 10, 0)), "rejected: foreign parts"),
        # ключ бункера 40,50 сдвинут на второй бункер 70,50: проходит - предел проверки
        "shift_copy": (base, lambda k: move_at((40, 50, 0), (70, 50, 0))(drop_entry(k, (70, 50, 0))),
                       "kept at 70,50 - passes"),
        "shift_dup": (base, move_at((40, 50, 0), (70, 50, 0)), "one kept, one rejected: duplicate entry"),
        "sig_changed": (farm, lambda k: re.sub(r"sig: '?[0-9a-f]+'?", "sig: 0123456789abcdef", k),
                        "rejected: model data changed"),
    }
    saves = {n: edit_key(src, d / (n + ".asav"), f) for n, (src, f, _) in cases.items()}
    for n in saves:
        print(n, (key_of(saves[n]) or "").replace("\n", " | "))
    res = par([lambda n=n: run(n, save=saves[n], env={"OXCE_COLLAPSE_MODEL": "1"}) for n in cases], jobs=a.jobs)
    report("shift", {"runs": [dict(short(s), expect=cases[s["name"]][2], key=key_of(saves[s["name"]]),
                                   model=[(m["label"], m["at"], len(m["removed"]), len(m["fell"])) for m in s["model"]])
                              for s in res]})


def ruin_parts():
    """Разбито больше половины частей здания (флаг 128, 385 у амбара): все части z0 и z2, кроме опор
    сценария ALL z1 (198 частей, модель роняет ещё 1, на месте 186). Этаж z1 цел - снятие ALL z1 потом
    роняет его (модель: 129 частей)."""
    parts = BLOCKS["barn"]["parts"]
    all1 = set(parts_of("barn", "ALL", 1)[0])
    inbox = [i for i, p in enumerate(parts) if p[4] & 128]
    nums = [i for i in inbox if i not in all1 and parts[i][3] != 1]
    if len(nums) * 2 <= len(inbox):
        raise SystemExit("разбито не больше половины: %d из %d" % (len(nums), len(inbox)))
    return nums


def c_ruin(a):
    """Сильно разбитое здание: сейв, загрузка, второй обвал - как без загрузки; контроль - сборка с порогом половины."""
    if not (P2H_EXE and P2H_EXE.is_file()):
        raise SystemExit("нужна сборка 993474e93 (порог половины): --p2h-build")
    hit = ruin_parts()
    all1, _ = parts_of("barn", "ALL", 1)
    henv = env_parts("OXCE_COLLAPSE_HIT", "barn", hit)
    rm = env_parts("OXCE_COLLAPSE_REMOVE", "barn", all1)
    mod = {"OXCE_COLLAPSE_MODEL": "1"}
    s1, cont = par([lambda: run("ruin_s1", seed=24, mission=FARM, env={**henv, **mod}),
                    lambda: run("ruin_cont", seed=24, mission=FARM,
                                env={**henv, **rm, **mod, "OXCE_COLLAPSE_AT": "2"}, turns=2)])
    if not s1["saved"]:
        raise SystemExit("нет сейва ruin_s1")
    f1 = edit_key(s1["saved"], OUT / "_saves/ruin_s1_format1.asav", to_format1)
    s2, s2v1, old = par([lambda: run("ruin_s2", save=s1["saved"], env={**rm, **mod, "OXCE_COLLAPSE_AT": "1"}),
                         lambda: run("ruin_s2_format1", save=f1, env={**rm, **mod, "OXCE_COLLAPSE_AT": "1"}),
                         lambda: run("ruin_old", save=f1, env={**rm, **mod, "OXCE_COLLAPSE_AT": "1"}, build="p2h")])
    res = {"hit_parts": len(hit), "all_parts": len(BLOCKS["barn"]["parts"]),
           "runs": [short(s) for s in (s1, cont, s2, s2v1, old)]}
    for nm, s in (("reload", s2), ("reload_format1", s2v1)):
        pc, ps = collapse_pass(cont, "barn", all1), collapse_pass(s, "barn", all1)
        if pc and ps:
            res[nm] = {"input_cont": len(pc[0]), "input_reload": len(ps[0]), "same_input": pc[0] == ps[0],
                       "fell_cont": len(pc[1]), "fell_reload": len(ps[1]), "same_fell": pc[1] == ps[1],
                       "input_only_cont": sorted(set(pc[0]) - set(ps[0])),
                       "input_only_reload": sorted(set(ps[0]) - set(pc[0])),
                       "fell_only_cont": sorted(set(pc[1]) - set(ps[1])),
                       "fell_only_reload": sorted(set(ps[1]) - set(pc[1]))}
        else:
            res[nm] = {"error": "нет обхода обвала: cont %s, reload %s" % (bool(pc), bool(ps))}
    report("ruin", res)


def c_chain2(a):
    """Стенд ставит тот же взрыв и при выключенной опции: прямое разрушение до модели совпадает
    (хэш карты перед моделью), итог различается - опция отвечает только за обвал."""
    benv = {"OXCE_COLLAPSE_AT": "1", "OXCE_COLLAPSE_BLAST_POWER": str(a.power), "OXCE_COLLAPSE_MODEL": "1",
            **env_tiles("OXCE_COLLAPSE_BLAST", "barn", [(4, 4, 0)])}
    on, off = par([lambda: run("chain2_on", seed=24, mission=FARM, env=benv),
                   lambda: run("chain2_off", seed=24, mission=FARM, env=benv, on=False)])
    h_on = {t["settle"]: t for t in on["terrain"]}
    h_off = {t["settle"]: t for t in off["terrain"]}
    rows = [{"settle": n, "why_on": h_on.get(n, {}).get("why"), "why_off": h_off.get(n, {}).get("why"),
             "hash_on": h_on.get(n, {}).get("hash"), "hash_off": h_off.get(n, {}).get("hash"),
             "same": h_on.get(n, {}).get("hash") == h_off.get(n, {}).get("hash")}
            for n in sorted(set(h_on) | set(h_off))]
    report("chain2", {"power": a.power, "terrain_before_model": rows,
                      "blast_on": [l for l in on["units"] if "blast" in l],
                      "blast_off": [l for l in off["units"] if "blast" in l],
                      "runs": [short(on), short(off)]})


def c_fall(a):
    """Занятая клетка: сейв сразу после падения (до хода врага); контроль - то же без обвала (опция выкл:
    стенд снимает те же опоры, модель не роняет)."""
    all1, _ = parts_of("barn", "ALL", 1)
    low = (5, 6, 0)
    ring = [(low[0] + dx, low[1] + dy, 0) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy]
    env = {**env_parts("OXCE_COLLAPSE_REMOVE", "barn", all1), "OXCE_COLLAPSE_AT": "1",
           **env_tiles("OXCE_COLLAPSE_UNIT", "barn", [(5, 6, 1), low] + ring), "OXCE_COLLAPSE_FALL_SAVE": "fall.asav"}
    res = par([lambda: run("fall_on", seed=24, mission=FARM, env=env),
               lambda: run("fall_off", seed=24, mission=FARM, env=env, on=False)])
    out = []
    for s in res:
        d = dict(short(s), fall=s["fall"], stand=s["units"])
        for nm in ("fall_saved", "saved"):
            if s[nm]:
                us, its = CP.sav_entities(s[nm])
                ours = {i for i, u in us.items() if u.get("faction") == "0"}
                d["units_" + nm] = {i: {k: u.get(k) for k in ("position", "status", "health", "stunlevel")}
                                    for i, u in us.items() if i in ours}
                # previousOwner: вещи, которые боец без сознания уронил на землю
                d["items_" + nm] = {i: {k: it.get(k) for k in ("type", "owner", "previousOwner", "unit",
                                                               "inventoryslot", "position")}
                                    for i, it in its.items()
                                    if {it.get("owner"), it.get("previousOwner"), it.get("unit")} & {str(u) for u in ours}}
        out.append(d)
    report("fall", {"runs": out})


CHECKS = {"hit": c_hit, "reload": c_reload, "badkey": c_badkey, "oldsave": c_oldsave, "units": c_units, "big": c_big,
          "occupied": c_occupied, "fire": c_fire, "chain": c_chain, "ai": c_ai, "ident": c_ident,
          "shift": c_shift, "ruin": c_ruin, "chain2": c_chain2, "fall": c_fall}


def main():
    global P1_EXE, P2H_EXE, BLOCKS
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("check", choices=sorted(CHECKS))
    ap.add_argument("--p1-build", default=os.environ.get("OXCE_COLLAPSE_P1_BUILD", ""),
                    help="каталог сборки пилота 1 (OXCE_AI_DEV=ON) - контроль")
    ap.add_argument("--p2h-build", default=os.environ.get("OXCE_COLLAPSE_P2H_BUILD", ""),
                    help="ruin: каталог сборки 993474e93 (порог половины частей) - контроль")
    ap.add_argument("--refresh", action="store_true", help="shift, badkey: снять сейвы формата 2 заново")
    ap.add_argument("--seeds", default="24", help="units: зёрна фермы")
    ap.add_argument("--power", type=int, default=60, help="chain: сила взрыва стенда")
    ap.add_argument("--chain-at", choices=("barn", "bunker"), default="barn", help="chain: здание взрыва")
    ap.add_argument("--ctl-x", type=int, default=2, help="chain: клетка контроля")
    ap.add_argument("--ctl-y", type=int, default=7)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--jobs", type=int, default=4)
    a = ap.parse_args()
    P1_EXE = Path(a.p1_build) / "bin" / ("openxcom" + ".exe") if a.p1_build else None
    if a.check in ("hit", "ident") and not (P1_EXE and P1_EXE.is_file()):
        raise SystemExit("нужна сборка пилота 1: --p1-build")
    P2H_EXE = Path(a.p2h_build) / "bin" / "openxcom.exe" if a.p2h_build else None
    BLOCKS = CP.header_blocks()
    CHECKS[a.check](a)


BLOCKS = None

if __name__ == "__main__":
    main()
