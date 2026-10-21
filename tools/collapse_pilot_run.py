#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Пилот обрушения в движке (этап 1): невидимые бои на сборке стенда с опцией oxceCollapse.

Сценарии - census/collapse/stage0m/pilot_scen.tsv (только чтение, под замком 0m). Отладочный стенд
CollapsePilot.cpp ставит бойцов на клетки участка (OXCE_COLLAPSE_UNIT, _STUN - без сознания, _DROP - предмет
с земли) на первом обходе settle и снимает части сценария (OXCE_COLLAPSE_REMOVE, номера частей блока) на
обходе OXCE_COLLAPSE_AT. Обходы - конец хода игрока (и цепочки взрывов местности). Итог сверяется с моделью
M0j4 (collapse_v7c.evaluate7c после collapse_v7d.install() - то же, что вывезено в CollapsePilotData.h): число упавших частей здания,
а бойцы, тело и предмет - по сохранению после хода ИИ.

    py -3.13 tools\collapse_pilot_run.py find  <сейв>...         в каком сейве стоит здание пилота (лог found)
    py -3.13 tools\collapse_pilot_run.py scen  --block barn --save <сейв> [--cells 79] [--only ALL:1] [--off]
    py -3.13 tools\collapse_pilot_run.py raw   --save <сейв> --env K=V ... [--off] [--turns N]

Сборка - build-ai-collapse (OXCE_AI_DEV=ON, R-203); каталог можно сменить OXCE_AI_BUILD до запуска.
Итоги - census/collapse/pilot1/runs/<имя>/ (лог, сохранение, summary.json).
"""
import argparse
import json
import os
import re
import shutil
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
os.environ.setdefault("OXCE_AI_BUILD", "build-ai-collapse")  # до импорта ai_probe: EXE считается при импорте
import ai_probe  # noqa: E402

ROOT = HERE.parent
ENC = "utf-8-sig"
# OXCE_COLLAPSE_HEADER - заголовок, с которым собран стенд, когда в src его ещё нет (бои вне очереди правок)
HEADER = Path(os.environ.get("OXCE_COLLAPSE_HEADER") or ROOT / "src/Battlescape/CollapsePilotData.h")
SCEN = ROOT / "census/collapse/stage0m/pilot_scen.tsv"
SCEN3 = ROOT / "census/collapse/pilot3/pilot_scen.tsv"   # третья партия зданий (collapse_pilot3_scen)
SCEN4 = ROOT / "census/collapse/pilot4/pilot_scen.tsv"   # четвёртая партия (collapse_pilot4_scen)
SCEN5 = ROOT / "census/collapse/pilot5/pilot_scen.tsv"   # пятая партия (collapse_pilot5_scen)
SCEN6 = ROOT / "census/collapse/pilot6/pilot_scen.tsv"   # шестая партия (collapse_pilot6_scen)
SCEN7 = ROOT / "census/collapse/pilot7/pilot_scen.tsv"   # седьмая партия (collapse_pilot7_scen)
SCEN8 = ROOT / "census/collapse/pilot8/pilot_scen.tsv"   # восьмая партия (collapse_pilot8_scen)
SCEN9 = ROOT / "census/collapse/pilot9/pilot_scen.tsv"   # девятая партия - лес и столбы (collapse_pilot9_scen)
SCEN10 = ROOT / "census/collapse/pilot10/pilot_scen.tsv"  # десятая партия - охват после ветки D
SCEN11 = ROOT / "census/collapse/pilot11/pilot_scen.tsv"  # одиннадцатая - разобранные виды предметов
SCEN12 = ROOT / "census/collapse/pilot12/pilot_scen.tsv"  # двенадцатая - второй лист видов
SCEN13 = ROOT / "census/collapse/pilot13/pilot_scen.tsv"  # тринадцатая - третий лист видов
OUT = ROOT / "census/collapse/pilot1/runs"
KIND = {"f": 0, "w": 1, "n": 2, "o": 3}
LABEL_RU = {"barn": "амбар", "bunker": "бункер",
            "banditbarn1": "амбар бандитов 1", "banditbarn2": "амбар бандитов 2", "riceshed": "сарай"}
import collapse_pilot4_scen as P4  # noqa: E402
LABEL_RU.update({en: ru for tn, bn, ru, en in P4.BUILDINGS})
import collapse_pilot5_scen as P5  # noqa: E402
LABEL_RU.update({en: ru for tn, bn, ru, en in P5.BUILDINGS})
import collapse_pilot6_scen as P6  # noqa: E402
LABEL_RU.update({en: ru for tn, bn, ru, en in P6.BUILDINGS})
import collapse_pilot7_scen as P7  # noqa: E402
LABEL_RU.update({en: ru for tn, bn, ru, en in P7.BUILDINGS})
import collapse_pilot8_scen as P8  # noqa: E402
LABEL_RU.update({en: ru for tn, bn, ru, en in P8.BUILDINGS})
import collapse_pilot9_scen as P9  # noqa: E402
LABEL_RU.update({en: ru for tn, bn, ru, en in P9.BUILDINGS})
import collapse_pilot10_scen as P10  # noqa: E402
LABEL_RU.update({en: ru for tn, bn, ru, en in P10.BUILDINGS})
import collapse_pilot11_scen as P11  # noqa: E402
LABEL_RU.update({en: ru for tn, bn, ru, en in P11.BUILDINGS})
import collapse_pilot12_scen as P12  # noqa: E402
LABEL_RU.update({en: ru for tn, bn, ru, en in P12.BUILDINGS})
import collapse_pilot13_scen as P13  # noqa: E402
LABEL_RU.update({en: ru for tn, bn, ru, en in P13.BUILDINGS})
CPF_INBOX = 128
_collapse_on = threading.local()


def _prepare_user(work, _orig=ai_probe.prepare_user):
    """options.cfg прогона установки плюс oxceCollapse (опции в конфиге установки нет - дописываем)."""
    _orig(work)
    on = getattr(_collapse_on, "value", True)
    p = work / "options.cfg"
    cfg = p.read_bytes().decode("utf-8")
    cfg, n = re.subn(r"(?m)^(\s*)oxceCollapse: .*$", r"\g<1>oxceCollapse: " + ("true" if on else "false"), cfg)
    if not n:
        cfg = re.sub(r"(?m)^options:\s*$", "options:\n  oxceCollapse: " + ("true" if on else "false"), cfg, count=1)
    p.write_bytes(cfg.encode("utf-8"))  # yaml-cpp, без спецификации (R-001, исключение)


ai_probe.prepare_user = _prepare_user


def _bench_defaults(env, _orig=ai_probe.bench_defaults):
    """Окружение прогона собирается в run() того же потока: сюда кладём OXCE_COLLAPSE_* этого прогона."""
    for k in [k for k in env if k.startswith("OXCE_COLLAPSE_")]:
        del env[k]
    env.update(getattr(_collapse_on, "env", {}))
    return _orig(env)


ai_probe.bench_defaults = _bench_defaults


# ------------------------------------------------------------------ данные блока из заголовка

def header_blocks():
    """{метка: {'parts': [(kind,x,y,z,flags)], 'index': {(kind,x,y,z): i}}} - номера частей как у движка."""
    text = HEADER.read_text(encoding="utf-8")
    blocks = {}
    for m in re.finditer(r'\{ "(\w+)", "[^"]*", \d+, \d+, \d+, \d+, \d+, \d+, \d+, sets\d+, \d+, (parts\d+), (\d+),', text):
        label, arr, n = m.group(1), m.group(2), int(m.group(3))
        body = re.search(r"static const CollapsePart %s\[\] = \{(.*?)\n\};" % arr, text, re.S).group(1)
        parts = []
        for row in re.findall(r"\{([^{}]*)\}", body):
            v = [int(s) for s in row.split(",")]
            parts.append((v[0], v[1], v[2], v[3], v[6]))
        if len(parts) != n:
            raise SystemExit("заголовок: у %s %d частей, ожидалось %d" % (label, len(parts), n))
        blocks[label] = {"parts": parts, "index": {p[:4]: i for i, p in enumerate(parts)}}
    return blocks


def kparse(s):
    kind, xyz = s.split(":")
    x, y, z = map(int, xyz.split(","))
    return kind, x, y, z


def partial_rows(label_en, only=None):
    """Сценарии частичного обрушения (collapse_partial_scen): PFALL с ожиданиями must_fall и must_stand."""
    import collapse_partial_scen as PF
    if any(b[3] == label_en for b in P7.BUILDINGS):   # седьмая партия - свои сценарии и замок (partial7)
        import collapse_partial7_scen as PF7
        PF7.use()
    if any(b[3] == label_en for b in P8.BUILDINGS):   # восьмая партия - так же (partial8)
        import collapse_partial8_scen as PF8
        PF8.use()
    if any(b[3] == label_en for b in P9.BUILDINGS):   # девятая партия - сценарии деревьев (partial9)
        import collapse_partial9_scen as PF9
        PF9.use()
    if any(b[3] == label_en for b in P10.BUILDINGS):  # десятая партия - те же сценарии деревьев (partial10)
        import collapse_partial10_scen as PF10
        PF10.use()
    if any(b[3] == label_en for b in P11.BUILDINGS):  # одиннадцатая - так же (partial11)
        import collapse_partial11_scen as PF11
        PF11.use()
    if any(b[3] == label_en for b in P12.BUILDINGS):  # двенадцатая - так же (partial12)
        import collapse_partial12_scen as PF12
        PF12.use()
    if any(b[3] == label_en for b in P13.BUILDINGS):  # тринадцатая - так же (partial13)
        import collapse_partial13_scen as PF13
        PF13.use()
    PF.check_lock()
    out = []
    for i, r in enumerate(PF.rows()):
        if r["label"] != LABEL_RU[label_en]:
            continue
        r["scenario"] = "PFALL%s" % r["side"]
        if only and "%s:%s" % (r["scenario"], r["z"]) not in only:
            continue
        out.append(r)
    return out


def partial_verdict(label, r, blocks, lines):
    """Вердикт PFALL по игре: упавшее - объединение fell= строк debug model на обходах, где снято всё, что снял
    стенд; must_fall берётся только из частей, которые модель держит в целом здании (как в collapse_partial_scen)."""
    import collapse_partial_scen as PF
    parts = blocks[label]["parts"]
    idx = blocks[label]["index"]
    num = lambda k: idx[(KIND[k[0]],) + tuple(k[1:])]
    key = lambda i: ("fwno"[parts[i][0]],) + tuple(parts[i][1:4])
    want = {num(kparse(s)) for s in r["removed"].split()}
    # только обход стенда и следующие без нового снятого: обход, где снято новое, - уже разрушения боя (R-301)
    fell, seen, at, state = set(), 0, None, None
    for l in lines:
        m = re.match(r"\[COLLAPSE\] debug: model %s at (\d+,\d+,\d+) removed=([\d,]*) fell=([\d,]*)" % label, l)
        if not m:
            continue
        rm = {int(s) for s in m.group(2).split(",") if s}
        fl = {int(s) for s in m.group(3).split(",") if s}
        if at is None:
            if not want <= rm:
                continue
            at, state = m.group(1), rm
        elif m.group(1) != at:
            continue
        elif rm - state:
            break
        seen += 1
        fell |= fl
        state = state | fl
    C, blk, box, inside = _model[label]
    base = {k for k in C.evaluate7c(blk, frozenset())[0] if inside(k, box)}
    v, miss, extra = PF.verdict(r, {key(i) for i in fell}, base)
    return {"verdict": v if seen else "NO_EVENT", "settles_seen": seen, "game_fell": len(fell),
            "must_fall": len({kparse(s) for s in r["must_fall"].split()} & base), "missed": sorted(map(PF.kstr, miss)),
            "must_stand_fallen": sorted(map(PF.kstr, extra))}


def scen_rows(label_en, cells=None, only=None):
    lines = SCEN.read_text(encoding=ENC).splitlines()
    head = lines[0].split("\t")
    lines += SCEN3.read_text(encoding=ENC).splitlines()[1:]
    lines += SCEN4.read_text(encoding=ENC).splitlines()[1:]
    lines += SCEN5.read_text(encoding=ENC).splitlines()[1:]
    lines += SCEN6.read_text(encoding=ENC).splitlines()[1:]
    lines += SCEN7.read_text(encoding=ENC).splitlines()[1:]
    lines += SCEN8.read_text(encoding=ENC).splitlines()[1:]
    lines += SCEN9.read_text(encoding=ENC).splitlines()[1:]
    lines += SCEN10.read_text(encoding=ENC).splitlines()[1:]
    lines += SCEN11.read_text(encoding=ENC).splitlines()[1:]
    lines += SCEN12.read_text(encoding=ENC).splitlines()[1:]
    lines += SCEN13.read_text(encoding=ENC).splitlines()[1:]
    out = []
    for ln in lines[1:]:
        r = dict(zip(head, ln.split("\t")))
        if r["label"] != LABEL_RU[label_en] or r["scenario"] == "ONE":
            continue
        if cells and int(r["unit_cells"]) != cells:
            continue
        if only and "%s:%s" % (r["scenario"], r["z"]) not in only:
            continue
        out.append(r)
    return out


# ------------------------------------------------------------------ модель

_model = {}
_model_lock = threading.Lock()


def model_fell(label_en, removed_keys):
    """Части здания (внутри участка пилота), которые модель M0j4 (как в игре) роняет при снятом removed_keys."""
    with _model_lock:          # прогоны идут потоками: соседний не должен увидеть словарь заполненным наполовину
        if label_en not in _model:
            _load_model(label_en)
    C, blk, box, inside = _model[label_en]
    rm = frozenset(k for k in removed_keys if inside(k, box))
    held = C.evaluate7c(blk, rm)[0]
    return sorted(k for k in blk.parts if inside(k, box) and k not in held and k not in rm)


def _load_model(label_en):
    # здание четвёртой-шестой партии грузится одно: загрузка всех целых блоков карт идёт минутами (cc.all_blocks
    # на каждое здание), а прогону нужен один
    for M in (P4, P5, P6, P7, P8, P9, P10, P11, P12, P13):
        one = [b for b in M.BUILDINGS if b[3] == label_en]
        if one:
            import collapse_pilot_export as EX
            import collapse_v7d as D
            D.install()
            keep = M.PILOT
            M.PILOT = [(tn, bn, ru) for tn, bn, ru, en in one]
            try:
                C, CT, blds = M.load()
            finally:
                M.PILOT = keep
            EX.BOX.update(M.BOX)
            EX.LABEL_EN.update(M.LABEL_EN)
            for tn, bn, label, blk in blds:
                _model[EX.LABEL_EN[label]] = (C, blk, EX.BOX[label], EX.inside)
            return
    if True:                                      # здания 0m и третьей партии - прежняя загрузка всего списка
        import collapse_pilot_scen as PS
        import collapse_pilot_export as EX
        import collapse_pilot3_scen as P3
        import collapse_v7d as D
        D.install()                               # evaluate7c считает M0j4, как заголовок игры
        C, CT, blds = PS.load()
        first = PS.PILOT
        PS.PILOT = P3.PILOT
        blds += PS.load()[2]
        PS.PILOT = first
        EX.BOX.update(P3.BOX)
        EX.LABEL_EN.update(P3.LABEL_EN)
        blds += P4.load()[2]
        EX.BOX.update(P4.BOX)
        EX.LABEL_EN.update(P4.LABEL_EN)
        blds += P5.load()[2]
        EX.BOX.update(P5.BOX)
        EX.LABEL_EN.update(P5.LABEL_EN)
        blds += P6.load()[2]
        EX.BOX.update(P6.BOX)
        EX.LABEL_EN.update(P6.LABEL_EN)
        blds += P7.load()[2]
        EX.BOX.update(P7.BOX)
        EX.LABEL_EN.update(P7.LABEL_EN)
        blds += P8.load()[2]
        EX.BOX.update(P8.BOX)
        EX.LABEL_EN.update(P8.LABEL_EN)
        blds += P9.load()[2]
        EX.BOX.update(P9.BOX)
        EX.LABEL_EN.update(P9.LABEL_EN)
        for tn, bn, label, blk in blds:
            _model[EX.LABEL_EN[label]] = (C, blk, EX.BOX[label], EX.inside)


# ------------------------------------------------------------------ сохранение

def sav_entities(path):
    """Юниты и предметы сохранения боя: {id: {...}} по разделам units/items (разбор строк, без yaml)."""
    units, items = {}, {}
    sect, cur = None, None
    for ln in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"^  (\w+):", ln)
        if m:
            sect = m.group(1)
            cur = None
            continue
        if sect not in ("units", "items"):
            continue
        m = re.match(r"^    - id: (-?\d+)", ln)
        if m:
            cur = {"id": int(m.group(1))}
            (units if sect == "units" else items)[cur["id"]] = cur
            continue
        m = re.match(r"^      (\w+): (.*)$", ln)
        if m and cur is not None and m.group(1) in ("position", "status", "faction", "type", "owner", "unit",
                                                     "previousOwner", "inventoryslot", "health", "stunlevel", "genUnitType"):
            cur[m.group(1)] = m.group(2).strip()
    return units, items


def pos(s):
    return tuple(int(v) for v in s.strip("[]").split(",")) if s else None


# ------------------------------------------------------------------ прогон

def collapse_lines(log):
    out = []
    if log and Path(log).exists():
        for raw in Path(log).read_text(encoding=ENC, errors="replace").splitlines():
            body = raw.split("\t")[-1]
            if body.startswith("[COLLAPSE]") or body.startswith("[AIPROBE] done") or body.startswith("[AIPROBE] stuck"):
                out.append(body)
    return out


def probe(name, save, env, on=True, turns=1):
    """Один невидимый бой; env - переменные стенда (OXCE_COLLAPSE_*), только этому прогону (свой поток)."""
    _collapse_on.value = on
    _collapse_on.env = env
    r = ai_probe.run(save, turns=turns, save_as="after.asav", name="collapse_" + name, timeout=900)
    dest = OUT / name
    dest.mkdir(parents=True, exist_ok=True)
    if r.log and Path(r.log).exists():
        shutil.copyfile(r.log, dest / "openxcom.log")
    saved = None
    if r.saved:
        saved = dest / "after.asav"
        shutil.copyfile(r.saved, saved)
    return r, dest, saved


def cmd_find(a):
    def one(save):
        name = "find_" + Path(save).stem
        r, dest, _ = probe(name, save, {}, True, 1)
        return save, [l for l in collapse_lines(dest / "openxcom.log") if " found " in l or "scan:" in l], r.seconds
    with ThreadPoolExecutor(max_workers=a.jobs) as ex:
        for save, lines, sec in ex.map(one, a.saves):
            print("%s  %.0f с" % (save, sec))
            for l in lines:
                print("   ", l)


def cells_pick(cells, n, avoid):
    """n клеток участка ближе к середине, не из avoid."""
    cx = sorted(c[0] for c in cells)[len(cells) // 2]
    cy = sorted(c[1] for c in cells)[len(cells) // 2]
    free = sorted((c for c in cells if c not in avoid), key=lambda c: (abs(c[0] - cx) + abs(c[1] - cy), c))
    return free[:n]


def run_scen(a, r, blocks, label):
    rm_keys = [kparse(s) for s in r["removed"].split()]
    idx = blocks[label]["index"]
    nums = []
    for k in rm_keys:
        i = idx.get((KIND[k[0]], k[1], k[2], k[3]))
        if i is None:
            raise SystemExit("часть %s:%d,%d,%d не найдена в заголовке" % k)
        nums.append(i)
    z = int(r["z"])
    cells = [tuple(map(int, c.split(","))) for c in r["parts"].split()]
    hole = {(k[1], k[2]) for k in rm_keys if k[0] == "f" and k[3] == z}
    # двое стоят, один без сознания (тело), один предмет с земли - на участке, не на дыре
    pick = cells_pick(cells, 4, hole)
    units, stun, drop = pick[:2], pick[2:3], pick[3:4]
    if a.hole_unit and hole:
        units = units[:1] + [sorted(hole)[0]]  # ещё один - прямо над снятым полом
    env = {
        "OXCE_COLLAPSE_UNIT": "%s:%s" % (label, ";".join("%d,%d,%d" % (x, y, z) for x, y in units)),
        "OXCE_COLLAPSE_STUN": "%s:%s" % (label, ";".join("%d,%d,%d" % (x, y, z) for x, y in stun)),
        "OXCE_COLLAPSE_DROP": "%s:%s" % (label, ";".join("%d,%d,%d" % (x, y, z) for x, y in drop)),
        "OXCE_COLLAPSE_REMOVE": "%s:%s" % (label, ",".join(map(str, nums))),
        "OXCE_COLLAPSE_AT": str(a.at),
    }
    name = "%s_%s_z%d_c%s%s%s%s" % (label, r["scenario"], z, r["unit_cells"], r.get("dup", ""),
                                    "_hu" if a.hole_unit and hole else "", "_off" if a.off else "")
    exp = model_fell(label, rm_keys)
    res, dest, saved = probe(name, a.save, env, not a.off, a.turns)
    lines = collapse_lines(dest / "openxcom.log")
    summ = {"name": name, "scenario": r["scenario"], "z": z, "cells": int(r["unit_cells"]), "expect": r["expect"],
            "removed_parts": len(nums), "model_fell": len(exp), "seconds": round(res.seconds, 1),
            "finished": res.finished, "lines": lines}
    off = None
    for l in lines:
        # сейв с ключом collapsePilot: здание не ищется заново, а берётся из записи - строка kept
        m = re.match(r"\[COLLAPSE\] (?:found|kept) %s .* at (\d+),(\d+),(\d+)" % label, l)
        if m and off is None:  # отладка движка ставит юнитов в первый экземпляр блока
            off = tuple(map(int, m.groups()))
        m = re.match(r"\[COLLAPSE\] (.+) %s at .*: removed (\d+), fell (\d+) \(f (\d+) w (\d+) n (\d+) o (\d+)\).*falling units (\d+);"
                     r" scan ([\d.e+-]+) ms, eval ([\d.e+-]+) ms, apply ([\d.e+-]+) ms, light\+fov ([\d.e+-]+) ms" % label, l)
        if m:
            g = m.groups()
            summ.setdefault("settles", []).append({"why": g[0], "removed": int(g[1]), "fell": int(g[2]),
                                                   "fell_kind": list(map(int, g[3:7])), "falling_units": int(g[7]),
                                                   "ms": {"scan": float(g[8]), "eval": float(g[9]), "apply": float(g[10]),
                                                          "light_fov": float(g[11])}})
        m = re.match(r"\[AIPROBE\] done: (\d+) AI turn\(s\), (\d+) ms real", l)
        if m:
            summ["probe_ms"] = int(m.group(2))
        # вход и выход модели движка на каждом обходе - против эталона M0j4 на том же входе
        m = re.match(r"\[COLLAPSE\] debug: model %s at (\d+),(\d+),(\d+) removed=([\d,]*) fell=([\d,]*)" % label, l)
        if m:
            parts = blocks[label]["parts"]
            rm_i = [int(s) for s in m.group(4).split(",") if s]
            fl_i = sorted(int(s) for s in m.group(5).split(",") if s)
            key = lambda i: ("fwno"[parts[i][0]],) + tuple(parts[i][1:4])
            ref = sorted(blocks[label]["index"][(KIND[k[0]],) + k[1:]] for k in model_fell(label, [key(i) for i in rm_i]))
            summ.setdefault("model_check", []).append({"at": tuple(map(int, m.group(1, 2, 3))), "removed": len(rm_i),
                                                       "engine_fell": len(fl_i), "ref_fell": len(ref), "same": fl_i == ref})
    summ["offset"] = off
    # бойцы, тело, предмет - по сохранению
    placed = []
    for l in lines:
        m = re.match(r"\[COLLAPSE\] debug: unit (\d+)( knocked out)? at %s (\d+),(\d+),(\d+)( - place refused)?" % label, l)
        if m:
            placed.append({"id": int(m.group(1)), "stun": bool(m.group(2)), "at": tuple(map(int, m.group(3, 4, 5))),
                           "refused": bool(m.group(6))})
        m = re.match(r"\[COLLAPSE\] debug: item (-?\d+) to %s (\d+),(\d+),(\d+)" % label, l)
        if m:
            placed.append({"item": int(m.group(1)), "at": tuple(map(int, m.group(2, 3, 4)))})
    if saved and off:
        us, its = sav_entities(saved)
        for p in placed:
            if "id" in p:
                u = us.get(p["id"], {})
                p["after"] = pos(u.get("position"))
                p["status"] = u.get("status")
                body = [i for i in its.values() if i.get("unit") == str(p["id"])]
                if body:
                    p["body_item"] = body[0]["id"]
                    p["body_after"] = pos(body[0].get("position"))
            elif p["item"] >= 0:
                it = its.get(p["item"], {})
                p["after"] = pos(it.get("position"))
                p["owner"] = it.get("owner")
            for key in ("after", "body_after"):
                if p.get(key):
                    q = p[key]
                    p[key + "_block"] = (q[0] - off[0], q[1] - off[1], q[2] - off[2])
    summ["placed"] = placed
    if "must_fall" in r:
        summ["partial"] = partial_verdict(label, r, blocks, lines)
    (dest / "summary.json").write_text(json.dumps(summ, ensure_ascii=False, indent=1), encoding=ENC)
    return summ


def cmd_scen(a):
    blocks = header_blocks()
    only = set(a.only.split(",")) if a.only else None
    rows = partial_rows(a.block, only) if a.partial else scen_rows(a.block, a.cells, only)
    if not rows:
        raise SystemExit("сценариев нет")
    # два сценария на том же этаже и участке (разные детали) - одно имя, общая рабочая папка параллельных прогонов
    seen = {}
    for r in rows:
        k = (r["scenario"], r["z"], r["unit_cells"])
        seen[k] = seen.get(k, 0) + 1
        if seen[k] > 1:
            r["dup"] = "_%d" % seen[k]
    with ThreadPoolExecutor(max_workers=a.jobs) as ex:
        res = list(ex.map(lambda r: run_scen(a, r, blocks, a.block), rows))
    for s in res:
        st = s.get("settles", [])
        fell = [x["fell"] for x in st]
        print("%-28s ждём %-8s модель %3d  игра %-10s %s  %.0f с%s" % (
            s["name"], s["expect"], s["model_fell"], fell, "" if s["finished"] else "НЕ ДОИГРАН", s["seconds"],
            "" if s["offset"] else "  ЗДАНИЕ НЕ НАЙДЕНО"))
        mc = s.get("model_check", [])
        # R-301: бой снёс части блока ещё до стенда - первый обход со снятым видит больше заданного, итог не о сценарии
        first = next((c["removed"] for c in mc if c["removed"]), 0)
        if first > s["removed_parts"]:
            print("       БОЙ ДО СТЕНДА: на первом обходе снято %d, задано %d - прогон не о сценарии (R-301)" % (
                first, s["removed_parts"]))
        print("       сверка с эталоном: %d обходов, совпало %d; %s" % (
            len(mc), sum(c["same"] for c in mc),
            " ".join("%d->%d/%d" % (c["removed"], c["engine_fell"], c["ref_fell"]) for c in mc if c["removed"])))
        if "partial" in s:
            pv = s["partial"]
            print("       частичное: %s  упало в игре %d, должно упасть %d, не упало %d, лишнего %d %s" % (
                pv["verdict"], pv["game_fell"], pv["must_fall"], len(pv["missed"]), len(pv["must_stand_fallen"]),
                " ".join(pv["missed"][:4] + pv["must_stand_fallen"][:4])))
        for p in s["placed"]:
            print("      ", {k: v for k, v in p.items() if k not in ("after",)})


def cmd_raw(a):
    env = dict(kv.split("=", 1) for kv in a.env)
    r, dest, saved = probe(a.name, a.save, env, not a.off, a.turns)
    for l in collapse_lines(dest / "openxcom.log"):
        print(l)
    print("сохранение:", saved, " %.0f с" % r.seconds)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("find")
    f.add_argument("saves", nargs="+")
    f.add_argument("--jobs", type=int, default=4)
    s = sub.add_parser("scen")
    s.add_argument("--block", required=True, choices=sorted(LABEL_RU))
    s.add_argument("--save", required=True)
    s.add_argument("--cells", type=int)
    s.add_argument("--only", help="ALL:1,HOLE:2 ...")
    s.add_argument("--off", action="store_true", help="опция выключена (контроль)")
    s.add_argument("--at", type=int, default=2, help="обход settle, на котором снять части (1 - конец первого хода)")
    s.add_argument("--turns", type=int, default=2)
    s.add_argument("--hole-unit", action="store_true", help="второго бойца - над снятым полом")
    s.add_argument("--partial", action="store_true", help="сценарии частичного обрушения (collapse_partial_scen)")
    s.add_argument("--jobs", type=int, default=3)
    w = sub.add_parser("raw")
    w.add_argument("--save", required=True)
    w.add_argument("--name", default="raw")
    w.add_argument("--env", nargs="*", default=[])
    w.add_argument("--off", action="store_true")
    w.add_argument("--turns", type=int, default=1)
    a = ap.parse_args()
    {"find": cmd_find, "scen": cmd_scen, "raw": cmd_raw}[a.cmd](a)


if __name__ == "__main__":
    main()
