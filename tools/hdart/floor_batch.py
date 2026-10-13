"""Конвейер HD-полов партиями: очередь -> план съёмки -> сборка -> игровые кадры -> общий лист -> установка.

Одна строка очереди - ГРУППА побайтных копий классики (census/frame_hash.tsv, R-296): рисуется один раз,
ставится на все копии. Состояние - art/ground/queue/queue.tsv (UTF-8 со спецификацией), правится только этим
скриптом и руками в столбце «заметка».

    py -3.13 tools/hdart/floor_batch.py index            # где на картах сейвов стоит каждый кадр пола (раз)
    py -3.13 tools/hdart/floor_batch.py queue            # пересобрать очередь (статусы сохраняются)
    py -3.13 tools/hdart/floor_batch.py plan  --batch b01 --n 24
    py -3.13 tools/hdart/floor_batch.py build --batch b01
    py -3.13 tools/hdart/floor_batch.py shoot --batch b01 [--jobs 3]
    py -3.13 tools/hdart/floor_batch.py sheet --batch b01
    py -3.13 tools/hdart/floor_batch.py judge --batch b01 --accept K1,K2 --reject K3=почему,...
    py -3.13 tools/hdart/floor_batch.py install --batch b01 [--yes]   # через editq: файлы мода
    py -3.13 tools/hdart/floor_batch.py stats

Статусы: queued, built, accepted, rejected (перерисовать другим методом), installed, keep_old (прежний пак
лучше или равен - закрыто), problem (отдельная очередь проблем, партии их не берут), no_save (нет на картах
сейвов - нечем проверить), need_view (собрана, на картах есть, но в игровой кадр партии не попала - нужен
другой ракурс; партии не берут, ждёт проверки), skip (не трогать: KEEP, PORTROADS, U_BASE_VR).

Игровые кадры - только невидимо (tools/game_hidden.py, R-124). Камера кадра подбирается по совпадению с
расчётным рисунком карты (map_screen_check.render), владелец пикселя даёт вырез каждой группы.
"""
import argparse
import collections
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

WORK = ROOT / "art" / "ground" / "queue"
SAVES = WORK / "saves"
QTSV = WORK / "queue.tsv"
INDEX = WORK / "save_index.json"
INST = ROOT / "Пиратки" / "Dioxine_XPiratez"
GAME_MODS = INST / "user" / "mods"
GAME = GAME_MODS / "hd" / "hd"
REPO = ROOT / "user" / "mods" / "hd" / "hd"
TAB = "\t"
ENC_R, ENC_W = "utf-8-sig", "utf-8-sig"
FRESH = time.mktime((2026, 10, 7, 0, 0, 0, 0, 0, -1))      # пак правлен после - набор уже закрыт
MIN_CELLS = 200
KEEP = {"UFOAA_INT:43", "UFOAA_INT:44", "AVENGER_EDIT:37", "STATIONDECOR:35"}
KEEP_PREFIX = ("PORTROADS:", "U_BASE_VR:")
PROBLEMS = {"ROADS_WASTE:0": "отдельная очередь проблем (рецензия 13.10)",
            "CARGO1:48": "R-320: подмена палитры боя - почти чёрные индексы становятся бирюзой",
            "C_INT:6": "в игре не виден - закрыт бортом поезда"}
COLS = ["группа", "копии", "клеток", "статус", "партия", "метод", "заметка"]
# окно игрового кадра 1920x1080 при k = 4: база 480x270, внизу панель боя
VIEW_DX, VIEW_UP, VIEW_DOWN = 13, 14, 8


def say(*a):
    print(*a, flush=True)


def rows(p):
    with open(p, encoding=ENC_R, newline="") as f:
        return list(csv.DictReader(f, delimiter=TAB, quoting=csv.QUOTE_NONE))


def key_of(s, f):
    return "%s:%d" % (s.replace(".PCK", "").upper(), int(f))


# ------------------------------------------------------------------ данные

def copies():
    """группа побайтных копий: ключ -> хэш, хэш -> ключи"""
    hof, by = {}, collections.defaultdict(list)
    with open(ROOT / "census" / "frame_hash.tsv", encoding=ENC_R) as f:
        for line in f:
            p = line.rstrip("\n").split(TAB)
            if len(p) < 3 or not p[1].isdigit():
                continue
            k = key_of(p[0], p[1])
            hof[k] = p[2]
            by[p[2]].append(k)
    return hof, by


def cells_on_maps():
    out = {}
    for r in rows(ROOT / "census" / "frames.tsv"):
        if r["раздел"] == "TERRAIN":
            out[key_of(r["набор"], r["кадр"])] = int(r["клеток"] or 0)
    return out


def floors():
    out = set()
    for r in rows(ROOT / "census" / "ground.tsv"):
        if r["раздел"] == "TERRAIN" and r["тип"] == "0" and r["пусто"] != "1":
            out.add(key_of(r["набор"], r["кадр"]))
    return out


def pack_png(k, root=GAME):
    s, f = k.split(":")
    return root / "TERRAIN" / ("%s.PCK" % s) / ("%s.png" % f)


def skip_reason(k):
    if k in KEEP or k.startswith(KEEP_PREFIX) or k.split(":")[0].endswith("_VR"):   # R-314
        return "не трогать"
    return None


def load_queue():
    if not QTSV.exists():
        return {}
    return {r["группа"]: r for r in rows(QTSV)}


def save_queue(q):
    WORK.mkdir(parents=True, exist_ok=True)
    order = sorted(q.values(), key=lambda r: -int(r["клеток"]))
    tmp = QTSV.with_suffix(".tmp")
    with open(tmp, "w", encoding=ENC_W, newline="") as f:
        f.write(TAB.join(COLS) + "\n")
        for r in order:
            f.write(TAB.join(str(r.get(c, "")).replace(TAB, " ").replace("\n", " ") for c in COLS) + "\n")
    if len(rows(tmp)) != len(order):          # R-159: проверка до замены
        raise SystemExit("запись очереди не сошлась")
    os.replace(tmp, QTSV)


# ------------------------------------------------------------------ index

def cmd_index(a):
    import map_truth as mt
    src = Path(a.saves) if a.saves else SAVES
    if a.saves:
        SAVES.mkdir(parents=True, exist_ok=True)
        for p in sorted(src.glob("*.asav")):
            if not (SAVES / p.name).exists():
                shutil.copy2(p, SAVES / p.name)
    idx = json.loads(INDEX.read_text(encoding=ENC_R)) if INDEX.exists() else {}
    for sv in sorted(SAVES.glob("*.asav")):
        if sv.name in idx and not a.force:
            continue
        t0 = time.time()
        bt = mt.Battle(str(sv))
        D = mt.Data(bt.mods)
        where = collections.defaultdict(list)
        for z in range(bt.Z):
            for y in range(bt.Y):
                for x in range(bt.X):
                    q = bt.part(z, y, x, 0)
                    if not q:
                        continue
                    recs = D.mcd(bt.sets[q[0]])
                    if q[1] >= len(recs):
                        continue
                    where[key_of(bt.sets[q[0]], recs[q[1]]["frames"][0])].append((x, y, z))
        idx[sv.name] = {"size": [bt.X, bt.Y, bt.Z], "frames": where}
        say("%-60s кадров пола %4d  %.0f с" % (sv.name, len(where), time.time() - t0))
        INDEX.write_text(json.dumps(idx, ensure_ascii=False), encoding=ENC_W)
    say("сейвов в индексе:", len(idx))


def load_index():
    if not INDEX.exists():
        raise SystemExit("нет %s - сначала index" % INDEX)
    return json.loads(INDEX.read_text(encoding=ENC_R))


# ------------------------------------------------------------------ queue

def cmd_queue(a):
    hof, by = copies()
    cells = cells_on_maps()
    fl = floors()
    idx = load_index()
    seen = set()
    for v in idx.values():
        seen.update(v["frames"])
    old = load_queue()
    q = {}
    done = set()
    for k in sorted(fl):
        if k in done:
            continue
        grp = sorted(set(by.get(hof.get(k), [])) | {k})
        done.update(grp)
        n = sum(cells.get(m, 0) for m in grp)
        if n < MIN_CELLS:
            continue
        rep = max(grp, key=lambda m: (cells.get(m, 0), m))
        prev = old.get(rep)
        st, note = (prev["статус"], prev["заметка"]) if prev else ("queued", "")
        live = [m for m in grp if not skip_reason(m)]
        fresh = [m for m in live if pack_png(m).exists() and os.path.getmtime(pack_png(m)) >= FRESH]
        if len(live) < len(grp):                # копия PORTROADS или VR-набора - не трогать всю группу
            live = []
        if not live:
            st, note = "skip", "не трогать: " + ",".join(grp)
        elif any(m in PROBLEMS for m in grp):
            m = [m for m in grp if m in PROBLEMS][0]
            st, note = "problem", PROBLEMS[m]
        elif st in ("queued", "no_save") and fresh:
            st, note = "installed", "правлен с 07.10: " + ",".join(fresh[:3])
        elif st in ("queued", "no_save") and not (st == "no_save" and note):   # с заметкой - решено планом
            st = "queued" if any(m in seen for m in grp) else "no_save"
        q[rep] = {"группа": rep, "копии": ",".join(m for m in grp if m != rep), "клеток": n, "статус": st,
                  "партия": prev["партия"] if prev else "", "метод": prev["метод"] if prev else "",
                  "заметка": note}
    save_queue(q)
    stats(q)


def stats(q):
    c = collections.Counter(r["статус"] for r in q.values())
    cc = collections.Counter()
    for r in q.values():
        cc[r["статус"]] += int(r["клеток"])
    say("групп %d:" % len(q))
    for st in ("queued", "built", "accepted", "rejected", "installed", "keep_old", "problem", "no_save", "need_view",
               "skip"):
        say("  %-10s %4d групп  %8d клеток" % (st, c[st], cc[st]))


def cmd_stats(a):
    stats(load_queue())


# ------------------------------------------------------------------ plan

def visible(dx, dy):
    return abs(dx - dy) <= VIEW_DX and -VIEW_UP <= dx + dy <= VIEW_DOWN


def cmd_plan(a):
    q = load_queue()
    idx = load_index()
    want = [r for r in sorted(q.values(), key=lambda r: -int(r["клеток"]))
            if r["статус"] in (("queued",) + (("rejected",) if a.redo else ()))][: a.n]
    if not want:
        raise SystemExit("в очереди пусто")
    members = {r["группа"]: [r["группа"]] + [m for m in r["копии"].split(",") if m] for r in want}
    # клетки групп по сейвам и этажам
    occ = collections.defaultdict(lambda: collections.defaultdict(list))   # (сейв, z) -> группа -> клетки
    for sv, v in idx.items():
        for g, ms in members.items():
            for m in ms:
                for x, y, z in v["frames"].get(m, []):
                    occ[(sv, z)][g].append((x, y))
    import map_screen_check as msc
    busy = {sv: {p for _u, p, _f in msc.units(str(SAVES / sv))[0]} for sv in idx}
    R = 14
    offs = [(dy, dx) for dy in range(-R, R + 1) for dx in range(-R, R + 1) if visible(dx, dy)]
    # число клеток группы в кадре при центре (cx, cy): свёртка карты клеток с окном кадра
    hits = {}
    for (sv, z), gs in occ.items():
        X, Y, _Z = idx[sv]["size"]
        free = np.zeros((Y, X), bool)
        for g, cs in gs.items():
            m = np.zeros((Y, X), np.float32)
            for x, y in cs:
                m[y, x] = 1
                free[y, x] = True
            pm = np.pad(m, R)
            acc = np.zeros((Y, X), np.float32)
            for dy, dx in offs:                 # acc[cy, cx] = клеток группы со сдвигом (dx, dy) от центра
                acc += pm[R + dy:R + dy + Y, R + dx:R + dx + X]
            hits[(sv, z, g)] = acc.astype(np.int32)
        for x, y, zz in busy[sv]:
            if zz == z and 0 <= y < Y and 0 <= x < X:
                free[y, x] = False
        occ[(sv, z)]["_free"] = free

    def at(sv, z, g, c):
        return int(hits[(sv, z, g)][c[1], c[0]])
    left = set(members)
    shots = []
    while left and len(shots) < a.max_shots:
        best = None
        for (sv, z), gs in occ.items():
            live = [g for g in gs if g in left]
            if not live:
                continue
            ok = [np.minimum(hits[(sv, z, g)], 12) * (hits[(sv, z, g)] >= a.min_cells) for g in live]
            n = sum((o > 0).astype(np.int32) for o in ok)
            # добор по всем клеткам групп: при насыщенном счёте центр уходит в гущу пола, а не в угол карты
            raw = sum(np.minimum(hits[(sv, z, g)], 999) for g in live)
            sc = n * 10 ** 7 + sum(ok).astype(np.int64) * 10 ** 4 + raw
            sc = np.where(gs["_free"], sc, -1)
            yy, xx = np.unravel_index(int(np.argmax(sc)), sc.shape)
            if sc[yy, xx] >= 10 ** 7 and (best is None or sc[yy, xx] > best[0]):
                best = (int(sc[yy, xx]), sv, (int(xx), int(yy), z), live)
        if best is None:
            break
        _sc, sv, c, live = best
        hit = {g: at(sv, c[2], g, c) for g in live}
        good = {g for g in live if hit[g] >= a.min_cells}
        shots.append({"save": sv, "center": c, "groups": sorted(good), "cells": {g: hit[g] for g in good}})
        left -= good
        say("кадр %2d: %-55s %-12s групп %d" % (len(shots), sv, "%d,%d,%d" % c, len(good)))
    plan = {"batch": a.batch, "made": time.strftime("%Y-%m-%d %H:%M"), "shots": shots,
            "groups": sorted(set(members) - left), "unplaced": sorted(left)}
    d = WORK / a.batch
    d.mkdir(parents=True, exist_ok=True)
    (d / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding=ENC_W)
    for r in q.values():
        if r["партия"] == a.batch and r["статус"] == "queued":
            r["партия"] = ""
    for g in plan["groups"]:
        q[g]["партия"] = a.batch
    def placeable(g):
        return any(int((np.where(gs["_free"], hits[(sv, z, g)], 0) >= a.min_cells).sum()) > 0
                   for (sv, z), gs in occ.items() if g in gs)
    nowhere = {g for g in left if not placeable(g)}
    say("не влезли в %d кадров: %d, места нет вовсе: %d" % (a.max_shots, len(left - nowhere), len(nowhere)))
    for g in left - nowhere:
        q[g]["партия"] = ""
    left = nowhere
    for g in left:                              # нечем проверить - из партий вон, пока не будет сейва
        q[g]["статус"] = "no_save"
        q[g]["заметка"] = "на картах сейвов нет места с %d клетками в кадре" % a.min_cells
    save_queue(q)
    say("партия %s: групп в плане %d, без места %d, игровых кадров %d" % (a.batch, len(plan["groups"]), len(left),
                                                                         len(shots)))


def load_plan(batch):
    p = WORK / batch / "plan.json"
    if not p.exists():
        raise SystemExit("нет плана " + str(p))
    return json.loads(p.read_text(encoding=ENC_R))


# ------------------------------------------------------------------ build

def cmd_build(a):
    plan = load_plan(a.batch)
    q = load_queue()
    out = WORK / a.batch / "TERRAIN"
    py = sys.executable
    for g in plan["groups"]:
        r = q[g]
        meth = r["метод"] or "pixel_lines"
        if meth.split()[0] != "pixel_lines":
            say("%-22s метод %s - не умею, пропуск" % (g, meth))
            continue
        extra = meth.split()[1:]
        cmd = [py, str(HERE / "pixel_lines.py"), "--out", str(out), "--frames", g] + extra
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        if p.returncode and "поле не закрывает кадр" in (p.stdout + p.stderr) and "--holes" not in extra:
            extra = extra + ["--holes"]
            cmd = cmd + ["--holes"]
            p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                               env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        if p.returncode:
            say("%-22s ОШИБКА %s" % (g, (p.stderr or p.stdout).strip().splitlines()[-1:]))
            r["заметка"] = "сборка упала"
            continue
        r["метод"] = " ".join(["pixel_lines"] + extra)
        r["статус"] = "built"
        say("%-22s %s" % (g, p.stdout.strip().splitlines()[-1]))
        s, f = g.split(":")
        src = out / ("%s.PCK" % s) / ("%s.png" % f)
        for m in [m for m in r["копии"].split(",") if m]:
            ms, mf = m.split(":")
            dst = out / ("%s.PCK" % ms) / ("%s.png" % mf)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
    save_queue(q)


# ------------------------------------------------------------------ shoot

def junction(link, target):
    subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], check=True, capture_output=True)


def game_save(sv, center):
    import map_screen_check as msc
    out = WORK / "_game" / ("%s_%d_%d_%d.sav" % ((Path(sv).stem,) + tuple(center)))
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        msc.prep(str(SAVES / sv), str(out), center=tuple(center), clear_smoke=True)
        txt = out.read_text(encoding="utf-8")
        import re
        txt2, k = re.subn(r"(?m)^  globalshade: \d+$", "  globalshade: 0", txt)
        if k != 1:
            raise SystemExit("globalshade: %d мест" % k)
        out.write_text(txt2, encoding="utf-8")
    return out


def layout(batch):
    """Папка модов партии: соединения на моды установки; в hd/hd/TERRAIN копии наборов партии с новыми кадрами.
    Варианты .vN заменённого кадра снимаются: иначе узор groundFrameFor показывает прежний рисунок (R-245)."""
    new = WORK / batch / "TERRAIN"
    root = WORK / "_mods" / batch
    sets = sorted(p.name for p in new.iterdir() if p.is_dir())
    terr = root / "hd" / "hd" / "TERRAIN"
    if not root.exists():
        root.mkdir(parents=True)
        for m in GAME_MODS.iterdir():
            if m.name != "hd":
                junction(root / m.name, m)
        src_hd = GAME_MODS / "hd"
        for sub_src, sub_dst, keep in ((src_hd, root / "hd", {"hd"}), (src_hd / "hd", root / "hd" / "hd", {"TERRAIN"}),
                                       (src_hd / "hd" / "TERRAIN", terr, set(sets))):
            sub_dst.mkdir(parents=True, exist_ok=True)
            for e in sub_src.iterdir():
                if e.name in keep:
                    continue
                if e.is_dir():
                    junction(sub_dst / e.name, e)
                else:
                    shutil.copy2(e, sub_dst / e.name)
    n = gone = 0
    src_t = GAME_MODS / "hd" / "hd" / "TERRAIN"
    for s in sets:
        if (terr / s).is_junction():            # набор добавлен после первой раскладки: связь снять (R-047)
            os.rmdir(terr / s)
        if not (terr / s).exists():
            if (src_t / s).exists():
                shutil.copytree(src_t / s, terr / s)
            else:
                (terr / s).mkdir(parents=True)
        for p in (new / s).glob("*.png"):
            f = p.name[:-4]
            if ".v" not in f:
                for v in (terr / s).glob(f + ".v*.png"):
                    v.unlink()
                    gone += 1
            shutil.copy2(p, terr / s / p.name)
            n += 1
    say("раскладка %s: наборов %d, кадров %d, снято вариантов %d" % (root, len(sets), n, gone))
    return root


def run_game(out, mods_dir, mode, user, save, after):
    if out.exists():
        return True
    sets = "oxceHdMode=%d;oxceHdScale=4;oxceHdGroundVariants=true" % mode
    cmd = [sys.executable, str(ROOT / "tools" / "game_hidden.py"), "--out", str(out), "--save", str(save),
           "--after", str(after), "--user", str(user), "--set", sets]
    if mods_dir:
        cmd += ["--mods-dir", str(mods_dir)]
    out.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    ok = out.exists()
    say("  %-50s %s" % (out.parent.name + "/" + out.name, "есть" if ok else "НЕТ, код %d" % r.returncode))
    return ok


def shot_paths(batch, sh):
    stem = Path(sh["save"]).stem
    c = tuple(sh["center"])
    ref = WORK / "_game" / ("ref_%s_%d_%d_%d" % ((stem,) + c))
    nm = "%d_%d_%d_r0.png" % c
    return ref / ("classic_" + nm), ref / ("hd_now_" + nm), WORK / batch / "game" / ("%s_new_%s" % (stem, nm))


def cmd_shoot(a):
    plan = load_plan(a.batch)
    mods = layout(a.batch)
    jobs = []
    for i, sh in enumerate(plan["shots"]):
        sav = game_save(sh["save"], sh["center"])
        cl, hn, nw = shot_paths(a.batch, sh)
        u = WORK / "_users"
        jobs += [(cl, None, 0, u / ("ref%d_c" % i + a.batch), sav), (hn, None, 1, u / ("ref%d_h" % i + a.batch), sav),
                 (nw, mods, 1, u / ("%s_%d_n" % (a.batch, i)), sav)]
    t0 = time.time()
    with ThreadPoolExecutor(a.jobs) as ex:
        res = list(ex.map(lambda j: run_game(j[0], j[1], j[2], j[3], j[4], a.after), jobs))
    say("игровых кадров: %d из %d, %.0f мин" % (sum(res), len(res), (time.time() - t0) / 60))


# ------------------------------------------------------------------ sheet

def camera_fit(bt, data, classic, center):
    """Камера кадра (смещение карты при k = 1) подбором: расчётный рисунок карты против классики по пикселям."""
    import map_screen_check as msc
    H0, W0 = classic.shape[:2]
    W, H = W0 // 4, H0 // 4
    small = classic[2::4, 2::4][:H, :W].astype(np.int64)
    col = (small[..., 0] << 16) | (small[..., 1] << 8) | small[..., 2]
    x, y, z = center
    sx, sy = x * 16 - y * 16, x * 8 + y * 8 - z * 24
    M = 48
    nom = (W // 2 - sx - 16, H // 2 - sy, z)
    img, owner = msc.render(bt, data, (nom[0] + M, nom[1] + M, z), W + 2 * M, H + 2 * M)
    best = None
    for st, rng in ((4, range(-M + 4, M - 3, 4)), (1, None)):
        cand = [(dx, dy) for dx in rng for dy in rng] if rng is not None else \
            [(best[1] + i, best[2] + j) for i in range(-4, 5) for j in range(-4, 5)]
        for dx, dy in cand:
            ix = img[M - dy:M - dy + H, M - dx:M - dx + W]
            m = ix > 0
            if m.sum() < 1000:
                continue
            k = (ix[m].astype(np.int64) << 24) | col[m]
            u, n = np.unique(k, return_counts=True)
            per = collections.defaultdict(int)
            for kk, nn in zip((u >> 24).tolist(), n.tolist()):
                per[kk] = max(per[kk], nn)
            sc = sum(per.values()) / m.sum()
            if best is None or sc > best[0]:
                best = (sc, dx, dy)
    sc, dx, dy = best
    own = owner[M - dy:M - dy + H, M - dx:M - dx + W]
    return sc, own


def font(sz):
    for f in ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/segoeui.ttf"):
        if os.path.exists(f):
            return ImageFont.truetype(f, sz)
    return ImageFont.load_default()


def cmd_sheet(a):
    import map_truth as mt
    plan = load_plan(a.batch)
    q = load_queue()
    d = WORK / a.batch
    tiles = []      # (группа, [три выреза], подпись)
    info = {}
    for sh in plan["shots"]:
        cl, hn, nw = shot_paths(a.batch, sh)
        if not (cl.exists() and hn.exists() and nw.exists()):
            say("нет игровых кадров для", sh["save"], sh["center"])
            continue
        bt = mt.Battle(str(SAVES / sh["save"]))
        data = mt.Data(bt.mods)
        A = [np.asarray(Image.open(p).convert("RGB")) for p in (cl, hn, nw)]
        sc, own = camera_fit(bt, data, A[0], sh["center"])
        say("%-55s камера: совпадение %.3f" % (sh["save"], sc))
        part = (own - 1) % 4
        cell = (own - 1) // 4
        fkey = {}
        for g in sh["groups"]:
            for m in [g] + [m for m in q[g]["копии"].split(",") if m]:
                fkey[m] = g
        H, W = own.shape
        names = np.full(own.shape, "", object)
        uniq = np.unique(cell[(own > 0) & (part == 0)])
        lookup = {}
        for c in uniq.tolist():
            z, rest = divmod(c, bt.Y * bt.X)
            y, x = divmod(rest, bt.X)
            p0 = bt.part(z, y, x, 0)
            if not p0:
                continue
            recs = data.mcd(bt.sets[p0[0]])
            if p0[1] < len(recs):
                lookup[c] = fkey.get(key_of(bt.sets[p0[0]], recs[p0[1]]["frames"][0]), "")
        for g in sh["groups"]:
            cs = [c for c, gg in lookup.items() if gg == g]
            mask = (own > 0) & (part == 0) & np.isin(cell, cs)
            npx = int(mask.sum())
            if npx < 40:
                continue
            # вырез: самое плотное окно 96x60 базы
            ii = np.cumsum(np.cumsum(np.pad(mask, ((1, 0), (1, 0))).astype(np.int32), 0), 1)
            bw, bh = min(120, W), min(68, H - 56)
            sums = ii[bh:, bw:] - ii[:-bh, bw:] - ii[bh:, :-bw] + ii[:-bh, :-bw]
            sums = sums[: max(1, H - 56 - bh + 1)]
            yy, xx = np.unravel_index(int(np.argmax(sums)), sums.shape)
            box = tuple(int(v) for v in (xx * 4, yy * 4, (xx + bw) * 4, (yy + bh) * 4))
            m4 = np.repeat(np.repeat(mask, 4, 0), 4, 1)
            dn = np.abs(A[2].astype(int) - A[1].astype(int)).sum(2)[m4[:A[1].shape[0], :A[1].shape[1]]]
            crops = [Image.fromarray(x).crop(box) for x in A]
            prev = info.get(g)
            if prev and prev["px"] >= npx:
                continue
            info[g] = {"px": npx, "changed": float((dn > 24).mean()) if dn.size else 0.0, "save": sh["save"],
                       "center": sh["center"], "box": box}
            tiles = [t for t in tiles if t[0] != g] + [(g, crops)]
    # лист: по строке на группу, три вырезa 0.5
    order = [g for g in plan["groups"] if g in info]
    miss = [g for g in plan["groups"] if g not in info]
    f1, f2 = font(22), font(18)
    tw, th = 360, 204                      # вырез 480x272 в 0.75: мелкий рисунок ещё читается
    rows_ = []
    for i, g in enumerate(order):
        crops = dict(tiles)[g]
        row = Image.new("RGB", (60 + 3 * (tw + 6), th + 30), (28, 28, 32))
        dr = ImageDraw.Draw(row)
        dr.text((6, th // 2), "%d" % (i + 1), fill=(255, 220, 90), font=f1)
        for j, c in enumerate(crops):
            row.paste(c.resize((tw, th), Image.LANCZOS), (60 + j * (tw + 6), 26))
        r = q[g]
        dr.text((60, 3), "%s  (+%d копий)  %s  изм. %.0f%%" % (g, len([m for m in r["копии"].split(",") if m]),
                                                                r["метод"], 100 * info[g]["changed"]),
                fill=(230, 230, 230), font=f2)
        rows_.append(row)
    per = a.per_page
    pages = []
    for pi in range(0, len(rows_), per):
        chunk = rows_[pi:pi + per]
        head = Image.new("RGB", (chunk[0].width, 34), (28, 28, 32))
        dh = ImageDraw.Draw(head)
        for j, t in enumerate(("классика", "пак сейчас", "новое")):
            dh.text((60 + j * (tw + 6) + 6, 6), t, fill=(160, 200, 255), font=f1)
        page = Image.new("RGB", (chunk[0].width, 34 + sum(r.height for r in chunk)), (28, 28, 32))
        page.paste(head, (0, 0))
        y = 34
        for r in chunk:
            page.paste(r, (0, y))
            y += r.height
        p = d / ("sheet_%d.png" % (pi // per + 1))
        page.save(p)
        pages.append(p)
    (d / "sheet.json").write_text(json.dumps({"order": order, "missing": miss, "info": info}, ensure_ascii=False,
                                             indent=1), encoding=ENC_W)
    say("лист: групп %d, без выреза %d %s" % (len(order), len(miss), miss))
    for p in pages:
        say(" ", p)


# ------------------------------------------------------------------ judge / install

def cmd_judge(a):
    q = load_queue()
    sh = json.loads((WORK / a.batch / "sheet.json").read_text(encoding=ENC_R))
    num = {str(i + 1): g for i, g in enumerate(sh["order"])}

    def g_of(t):
        return num.get(t, t.upper())
    for t in [t for t in (a.accept or "").split(",") if t]:
        g = g_of(t)
        q[g]["статус"] = "accepted"
    for t in [t for t in (a.reject or "").split(";") if t]:
        k, _, why = t.partition("=")
        g = g_of(k.strip())
        q[g]["статус"] = "rejected"
        q[g]["заметка"] = why.strip()
    for t in [t for t in (a.keep or "").split(";") if t]:
        k, _, why = t.partition("=")
        g = g_of(k.strip())
        q[g]["статус"] = "keep_old"
        q[g]["заметка"] = why.strip()
    save_queue(q)
    # вердикты партии - отдельным файлом: в очереди только последнее состояние группы, а группа, возвращённая на
    # пересборку, уходит в следующую партию, и счёт прежней партии из очереди уже не собрать
    vp = WORK / a.batch / "verdicts.tsv"
    old = {}
    if vp.exists():
        for row in csv.reader(vp.read_text(encoding=ENC_R).splitlines()[1:], delimiter="\t", quoting=csv.QUOTE_NONE):
            old[row[0]] = row
    for g in sh["order"]:
        if q[g]["статус"] in ("accepted", "rejected", "keep_old"):
            old[g] = [g, q[g]["статус"], q[g]["заметка"].replace("\t", " ")]
    vp.write_text("группа\tвердикт\tзаметка\n" + "".join("\t".join(r) + "\n" for r in old.values()), encoding=ENC_W)
    stats(q)


def cmd_install(a):
    import build_hd_pack as bp
    os.chdir(ROOT)
    q = load_queue()
    out = WORK / a.batch / "TERRAIN"
    take = [r for r in q.values() if r["партия"] == a.batch and r["статус"] == "accepted"]
    man = bp.load()
    plan, drop = [], []
    for r in take:
        g = r["группа"]
        for m in [g] + [m for m in r["копии"].split(",") if m]:
            if skip_reason(m):
                continue
            ms, mf = m.split(":")
            gd = GAME / "TERRAIN" / ("%s.PCK" % ms)
            if not (gd / ("%s.png" % mf)).exists():
                say("%-22s нет пака в установке - пропуск" % m)
                continue
            src = out / ("%s.PCK" % ms) / ("%s.png" % mf)
            plan.append(("TERRAIN/%s.PCK/%s.png" % (ms, mf), str(src), m, g,
                         "конвейер полов %s: игровой кадр лучше прежнего пака (%s)" % (a.batch, r["метод"])))
            for v in sorted(gd.glob(mf + ".v*.png")):
                drop.append("TERRAIN/%s.PCK/%s" % (ms, v.name))
    say("групп %d, файлов %d, снять вариантов %d" % (len(take), len(plan), len(drop)))
    if not a.yes:
        raise SystemExit("сухой прогон; --yes - записать")
    for rel, src, m, g, why in plan:
        old = man["files"].get(rel, {}).get("sha256")
        bp.stage(man, rel, src, generator="pixel_lines", generator_version="pixel_lines.py 13.10 floor_batch",
                 source_path=src, approved=True, approval=why, asset_id=m, source_frame=g, replaced=old)
    for rel in drop:
        man["files"].pop(rel, None)
    bp.save(man, why="floor_batch %s" % a.batch)
    bp.log("save", "", bp.manifest_hash(man)[:16], "floor_batch %s: %d файлов, снято вариантов %d"
           % (a.batch, len(plan), len(drop)))
    rels = sorted({p[0] for p in plan})
    say("game:", bp.install(man, "game", only=rels))
    repo = []
    for r in rels:
        sd = r.rsplit("/", 1)[0] + "/"
        whole = [k for k in man["files"] if k.startswith(sd)]
        if (REPO / sd).is_dir() and len(os.listdir(REPO / sd)) >= len(whole):
            repo.append(r)
        else:                                   # R-257: набора нет или он неполный - целиком
            repo += whole
    say("repo:", bp.install(man, "repo", only=sorted(set(repo))))
    for rel in drop:
        for root in (GAME, REPO):
            p = root / rel
            if p.exists():
                bp.unlink_ro(str(p)) if hasattr(bp, "unlink_ro") else p.unlink()
    bad = 0
    for r in rels:
        for root in (GAME, REPO):
            if hashlib.sha256((root / r).read_bytes()).hexdigest() != man["files"][r]["sha256"]:
                say("РАСХОДИТСЯ", root, r)
                bad += 1
    for sd in sorted({r.rsplit("/", 1)[0] + "/" for r in rels}):
        ng, nr = len(os.listdir(GAME / sd)), len(os.listdir(REPO / sd))
        nm = len([k for k in man["files"] if k.startswith(sd)])
        if not ng == nr == nm:
            say("ЧИСЛО ФАЙЛОВ", sd, "game", ng, "repo", nr, "манифест", nm)
            bad += 1
    say("сверка: расхождений", bad)
    if not bad:
        for r in take:
            r["статус"] = "installed"
        save_queue(q)
    stats(q)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("index")
    p.add_argument("--saves", default="")
    p.add_argument("--force", action="store_true")
    sp.add_parser("queue")
    sp.add_parser("stats")
    p = sp.add_parser("plan")
    p.add_argument("--batch", required=True)
    p.add_argument("--n", type=int, default=24)
    p.add_argument("--min-cells", type=int, default=3)
    p.add_argument("--max-shots", type=int, default=16)
    p.add_argument("--redo", action="store_true", help="брать и отклонённые (после смены метода)")
    for nm in ("build", "sheet", "shoot", "install", "judge"):
        p = sp.add_parser(nm)
        p.add_argument("--batch", required=True)
        if nm == "shoot":
            p.add_argument("--jobs", type=int, default=3)
            p.add_argument("--after", type=int, default=90)
        if nm == "sheet":
            p.add_argument("--per-page", type=int, default=8)
        if nm == "install":
            p.add_argument("--yes", action="store_true")
        if nm == "judge":
            p.add_argument("--accept", default="")
            p.add_argument("--reject", default="")
            p.add_argument("--keep", default="")
    a = ap.parse_args()
    {"index": cmd_index, "queue": cmd_queue, "stats": cmd_stats, "plan": cmd_plan, "build": cmd_build,
     "shoot": cmd_shoot, "sheet": cmd_sheet, "judge": cmd_judge, "install": cmd_install}[a.cmd](a)


if __name__ == "__main__":
    main()
