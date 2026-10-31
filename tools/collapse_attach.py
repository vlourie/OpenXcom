#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Этап 0l обрушения зданий: разметка кандидатов крепления (рецензия 0k).

Кандидаты - записи слота o, которые правило a M0j2 (collapse_v7b) роняет на целых блоках
(census/collapse/stage0k/v2/attach_candidates.tsv). Автоматическая роль - не основание для обрушения: каждую
запись размечает исполнитель по картинке и геометрии, с причиной и уверенностью; спорное - на решение Vitali.

Разметка (census/collapse/stage0l/attach_marks.tsv), свойство записи, а не исход:
    SURFACE    стоит на поверхности: to = floor (пол своей клетки) или below (предмет этажом ниже)
    ATTACHED   прикреплено: to = к чему - сторона клетки w (своя западная стена), n (своя северная),
               e (западная стена соседа x+1), s (северная стена соседа y+1), up (пол этажом выше - подвес),
               ow, on, oe, os (предмет слота o соседней клетки с этой стороны: стена-предмет, балка крана, труба);
               несколько через '+' - держится, пока цела ХОТЯ БЫ одна
    STRUCTURE  несущая конструкция: to = роль (ROOF, WALL, MASS, HULL, COLUMN, TRUSS)
    UNKNOWN    не решено: to пусто
Метки «падает» нет: падение - результат расчёта, а не свойство.

Геометрия - по LOFT как в игре: TileEngine::voxelCheck берёт бит 15 - x (collapse_v7.footprint отражён по x;
для правила b, которое сравнивает части одной клетки, это безразлично, для касания соседей - нет).

    py -3.13 tools\collapse_attach.py geom     касания по LOFT во всех местах записи на целых блоках
    py -3.13 tools\collapse_attach.py sheet    листы: кадр, вид сверху LOFT со сторонами, окружение, разметка
    py -3.13 tools\collapse_attach.py check    разметка полна и согласна с геометрией
    py -3.13 tools\collapse_attach.py lock     замок разметки (до прогона модели с ней)
"""
import collections
import hashlib
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import collapse_census as cc                      # noqa: E402
import collapse_v2 as V                           # noqa: E402
import collapse_v7 as J                           # noqa: E402
import collapse_v7b as K                          # noqa: E402

ENC = "utf-8-sig"
OUT = "census/collapse/stage0l"
CAND = K.OUT + "/attach_candidates.tsv"
GEOM = OUT + "/attach_geom.json"
MARKS = OUT + "/attach_marks.tsv"
LOCK = OUT + "/attach_marks.lock.txt"
MARK_HEAD = ["set", "idx", "mark", "to", "confidence", "reason", "dispute"]
KINDS = {"SURFACE": {"floor", "below"}, "ATTACHED": {"w", "n", "e", "s", "up", "ow", "on", "oe", "os"},
         "STRUCTURE": {"ROOF", "WALL", "MASS", "HULL", "COLUMN", "TRUSS"}, "UNKNOWN": {""}}
NEIGH = {"ow": (-1, 0), "oe": (1, 0), "on": (0, -1), "os": (0, 1)}
CONF = {"high", "medium", "low"}
SIDE = {"w": ("w", 0, 0), "n": ("n", 0, 0), "e": ("w", 1, 0), "s": ("n", 0, 1)}


def candidates():
    rows = [r.split("\t") for r in open(CAND, encoding=ENC).read().splitlines()[1:]]
    out = collections.OrderedDict()
    for r in rows:
        k = (r[0].upper(), int(r[1]))
        d = out.setdefault(k, {"set": r[0], "idx": int(r[1]), "role": r[2], "src": r[3], "cls": r[4],
                               "drop": 0, "floor": [], "example": r[7]})
        d["drop"] += int(r[6])
        d["floor"].append("%s %s" % (r[5], r[6]))
    return out


def foot(t):
    """Воксели слоя LOFT t в координатах клетки: x к востоку, y к югу (бит 15 - x, как voxelCheck)."""
    return {(15 - x, y) for x, y in J.footprint(t)}


def layers(blk, key):
    p = blk.parts[key]
    if p["set"] == "SYNTH":
        return {}
    ids = J.loft_ids(p["set"], p["idx"])
    if not ids:
        return {}
    return {li: foot(ids[li]) for li in range(12) if p["rec"]["layers"][li]}


def touch(a, b, dx, dy):
    """Число вокселей a, совпадающих или соседних по стороне с вокселями b (b сдвинут на dx, dy) в том же слое."""
    n = 0
    for li, fa in a.items():
        fb = b.get(li)
        if not fb:
            continue
        sb = {(x + dx, y + dy) for x, y in fb}
        n += sum(1 for x, y in fa if {(x, y), (x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)} & sb)
    return n


def part_at(blk, z, side, x, y):
    k, dx, dy = SIDE[side]
    return blk.lv[z][k].get((x + dx, y + dy))


def cmd_geom():
    """По каждой записи-кандидату все места на целых блоках: есть ли пол и держится ли он (M0i2+b и M0j2), с чем
    объект соприкасается по LOFT (стены четырёх сторон, предмет ниже, пол выше, предметы соседей)."""
    cand = candidates()
    os.makedirs(OUT, exist_ok=True)
    st = collections.defaultdict(collections.Counter)
    info, t0, nb = {}, time.time(), 0
    roles = V.load_roles()
    for tname, kind, t, bname, blk, err, cache in cc.all_blocks(V.game_args()):
        if blk is None:
            continue
        nb += 1
        hit = [k for k, p in blk.parts.items() if k[0] == "o" and (p["set"].upper(), p["idx"]) in cand]
        if not hit:
            continue
        V.apply_roles(blk, roles)
        held_b = K.evaluate7b(blk, frozenset(), K.M0I2 + "b")[0]
        held_j = K.evaluate7b(blk, frozenset(), K.MODEL)[0]
        for k in hit:
            p = blk.parts[k]
            rid = (p["set"].upper(), p["idx"])
            _, x, y, z = k
            c = st[rid]
            c["places"] += 1
            me = layers(blk, k)
            if rid not in info:
                allv = set().union(*me.values()) if me else set()
                info[rid] = {"nl": len(me), "lo": min(me) if me else -1, "hi": max(me) if me else -1,
                             "area_bottom": len(me[min(me)]) if me else 0, "area_all": len(allv),
                             "edge": {s: sum(1 for a, b in allv if f(a, b)) for s, f in
                                      (("w", lambda a, b: a <= 2), ("n", lambda a, b: b <= 2),
                                       ("e", lambda a, b: a >= 13), ("s", lambda a, b: b >= 13))},
                             "top": sorted(allv), "big_wall": p["rec"]["big_wall"], "armor": p["rec"]["armor"],
                             "stop_los": p["rec"]["stop_los"], "cls": p["cls"], "role": p.get("role"),
                             "rev": bool(p.get("rev"))}
            fl = blk.lv[z]["f"].get((x, y))
            if k in held_b and k not in held_j:
                c["dropped_by_a"] += 1
            if fl is not None:
                c["floor"] += 1
                c["floor_held_b" if fl in held_b else "floor_not_held_b"] += 1
                continue
            c["nofloor"] += 1
            if z == 0:
                c["nofloor_z0"] += 1
            tw = []
            for s in SIDE:
                wk = part_at(blk, z, s, x, y)
                if wk is None:
                    continue
                c["has_" + s] += 1
                k2, dx, dy = SIDE[s]
                if touch(me, layers(blk, wk), dx * 16, dy * 16):
                    c["touch_" + s] += 1
                    tw.append(s)
            c["combo_" + ("none" if not tw else "+".join(tw))] += 1
            if z + 1 < len(blk.lv) and blk.lv[z + 1]["f"].get((x, y)) is not None:
                c["floor_above"] += 1
            if z > 0:
                ob = blk.lv[z - 1]["o"].get((x, y))
                if ob is not None:
                    c["obj_below"] += 1
                    bl = layers(blk, ob)
                    if me and 11 in bl and bl[11] & me[min(me)]:
                        c["sits_on_below"] += 1
            for s, (dx, dy) in (("w", (-1, 0)), ("e", (1, 0)), ("n", (0, -1)), ("s", (0, 1))):
                ok = blk.lv[z]["o"].get((x + dx, y + dy))
                if ok is not None and touch(me, layers(blk, ok), dx * 16, dy * 16):
                    c["touch_o_" + s] += 1
        if nb % 500 == 0:
            print("  блоков %d, %.0f с" % (nb, time.time() - t0), flush=True)
    out = {}
    for rid, d in cand.items():
        out["%s:%d" % rid] = {"cand": {kk: d[kk] for kk in ("set", "idx", "role", "src", "cls", "drop", "floor",
                                                              "example")},
                              "geom": info.get(rid), "count": dict(st[rid])}
    with open(GEOM, "w", encoding=ENC) as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    miss = [k for k, v in out.items() if v["geom"] is None]
    print("блоков %d, записей %d, без мест %d %s -> %s" % (nb, len(out), len(miss), miss, GEOM))


# ------------------------------------------------------------------ разметка

def read_marks():
    if not os.path.exists(MARKS):
        return {}
    lines = open(MARKS, encoding=ENC).read().splitlines()
    head = lines[0].split("\t")
    if head != MARK_HEAD:
        raise SystemExit("%s: шапка %s, ожидалась %s" % (MARKS, head, MARK_HEAD))
    out = {}
    for n, ln in enumerate(lines[1:], 2):
        if not ln.strip():
            continue
        r = dict(zip(head, ln.split("\t")))
        k = (r["set"].upper(), int(r["idx"]))
        if k in out:
            raise SystemExit("%s:%d: запись %s:%d повторена" % (MARKS, n, *k))
        r["line"] = n
        out[k] = r
    return out


def cmd_check():
    """Разметка: каждая запись-кандидат размечена, поля допустимы, крепление к стороне, у которой в местах без
    пола есть часть; расхождение с касанием по LOFT печатается (не ошибка: у плюща и ламп LOFT пустой)."""
    geo = json.load(open(GEOM, encoding=ENC))
    marks = read_marks()
    bad, warn = [], []
    for key, g in geo.items():
        s, i = key.rsplit(":", 1)
        m = marks.get((s, int(i)))
        if m is None:
            bad.append("%s: нет разметки" % key)
            continue
        if m["mark"] not in KINDS:
            bad.append("%s: метка %r" % (key, m["mark"]))
            continue
        tos = [t for t in m["to"].split("+")] if m["to"] else [""]
        if any(t not in KINDS[m["mark"]] for t in tos):
            bad.append("%s: %s к %r" % (key, m["mark"], m["to"]))
        if m["confidence"] not in CONF:
            bad.append("%s: уверенность %r" % (key, m["confidence"]))
        if not m["reason"].strip():
            bad.append("%s: нет причины" % key)
        if m["mark"] == "UNKNOWN" and not m["dispute"].strip():
            bad.append("%s: UNKNOWN без вопроса" % key)
        c = g["count"]
        if m["mark"] == "ATTACHED":
            for t in tos:
                if t in SIDE and not c.get("has_" + t) and c.get("nofloor"):
                    warn.append("%s: прикреплено к %s, а в местах без пола там нет стены ни разу" % (key, t))
                if t in SIDE and c.get("has_" + t) and not c.get("touch_" + t) and g["geom"]["nl"]:
                    warn.append("%s: прикреплено к %s, а LOFT её не касается" % (key, t))
                if t in NEIGH and g["geom"]["nl"] and not c.get("touch_o_" + t[1]):
                    warn.append("%s: прикреплено к предмету соседа %s, а LOFT его не касается ни разу" % (key, t))
    extra = set(marks) - {(k.rsplit(":", 1)[0], int(k.rsplit(":", 1)[1])) for k in geo}
    bad += ["%s:%d: размечено, но не кандидат" % k for k in sorted(extra)]
    for w in warn:
        print("  ?", w)
    for b in bad:
        print("  !", b)
    agg = collections.Counter((m["mark"], m["confidence"]) for m in marks.values())
    print("размечено %d из %d; %s; спорных %d" % (len(marks), len(geo), dict(sorted(agg.items())),
                                                 sum(1 for m in marks.values() if m["dispute"].strip())))
    return 1 if bad else 0


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def cmd_lock():
    if cmd_check():
        raise SystemExit("разметка с ошибками - замок не ставлю")
    if os.path.exists(LOCK):
        raise SystemExit("%s уже есть - разметку после замка меняют только новой версией" % LOCK)
    with open(LOCK, "w", encoding=ENC) as f:
        f.write("# замок разметки крепления, этап 0l (до прогона модели с ней)\n")
        f.write("time\t%s\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
        for p in (MARKS, GEOM, "tools/collapse_attach.py"):
            f.write("%s\t%s\n" % (p, sha(p)))
    print("->", LOCK)


def check_lock():
    if not os.path.exists(LOCK):
        raise SystemExit("нет замка разметки %s" % LOCK)
    for ln in open(LOCK, encoding=ENC).read().splitlines():
        if ln.startswith("#") or ln.startswith("time"):
            continue
        p, h = ln.split("\t")
        if sha(p) != h:
            raise SystemExit("замок разметки нарушен: %s" % p)


# ------------------------------------------------------------------ листы

def cmd_sheet():
    from PIL import Image, ImageDraw, ImageFont
    geo = json.load(open(GEOM, encoding=ENC))
    marks = read_marks()
    fnt = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 12)
    files = J._loft_data()["files"]

    def frame(st, idx):
        try:
            with open(files.find(os.path.join("TERRAIN", st + ".MCD")), "rb") as f:
                r = f.read()[idx * cc.REC:(idx + 1) * cc.REC]
            L = json.load(open("art/TERRAIN/%s.PCK/layout.json" % st, encoding=ENC))
            im = Image.open("art/TERRAIN/%s.PCK/original.png" % st).convert("RGBA")
        except (KeyError, OSError, ValueError):
            return None
        pw, ph = im.size[0] // L["columns"], im.size[1] // L["rows"]
        f = r[0]
        c, rr = f % L["columns"], f // L["columns"]
        cell = im.crop((c * pw, rr * ph, c * pw + pw, rr * ph + ph)).resize((32, 40), Image.NEAREST)
        bg = Image.new("RGBA", (32, 40), (40, 40, 48, 255))
        bg.alpha_composite(cell)
        return bg.convert("RGB").resize((96, 120), Image.NEAREST)

    def top(g):
        """Вид сверху: клетка 16x16 вокселей по 5 пикселей, север вверху, запад слева."""
        im = Image.new("RGB", (80, 80), (235, 235, 230))
        d = ImageDraw.Draw(im)
        for x, y in (g or {}).get("top", []):
            d.rectangle((x * 5, y * 5, x * 5 + 4, y * 5 + 4), fill=(60, 60, 160))
        d.rectangle((0, 0, 79, 79), outline=(0, 0, 0))
        d.text((2, 66), "W", fill=(200, 0, 0), font=fnt)
        d.text((36, 0), "N", fill=(200, 0, 0), font=fnt)
        return im

    keys = list(geo)
    per, W, CW, CH = 20, 2, 780, 150
    for page in range(0, len(keys), per):
        part = keys[page:page + per]
        img = Image.new("RGB", (W * CW, ((len(part) + W - 1) // W) * CH + 30), (250, 250, 247))
        d = ImageDraw.Draw(img)
        d.text((6, 6), "Этап 0l: разметка крепления (кадр, LOFT сверху - север вверху, касания в местах без пола). "
                       "Стр. %d" % (page // per + 1), fill=(0, 0, 0), font=fnt)
        for i, key in enumerate(part):
            g = geo[key]
            x0, y0 = (i % W) * CW + 6, (i // W) * CH + 30
            s, idx = key.rsplit(":", 1)
            fr = frame(s, int(idx))
            if fr:
                img.paste(fr, (x0, y0))
            img.paste(top(g["geom"]), (x0 + 100, y0))
            c, gm, cd = g["count"], g["geom"] or {}, g["cand"]
            m = marks.get((s, int(idx)))
            lines = ["%s  %s (%s), класс %s, броня %s, слоёв LOFT %s (%s-%s)" % (
                         key, cd["role"], cd["src"], cd["cls"], gm.get("armor"), gm.get("nl"), gm.get("lo"),
                         gm.get("hi")),
                     "роняет a: %s частей (%s); мест %s, без пола %s" % (cd["drop"], ", ".join(cd["floor"]),
                                                                      c.get("places"), c.get("nofloor", 0)),
                     "касание без пола: " + ", ".join("%s %d" % (k[6:], v) for k, v in sorted(c.items())
                                                       if k.startswith("combo_")),
                     "стены есть: " + ", ".join("%s %d" % (k[4:], v) for k, v in sorted(c.items())
                                                if k.startswith("has_")) +
                     "; соседи o: " + ", ".join("%s %d" % (k[8:], v) for k, v in sorted(c.items())
                                                if k.startswith("touch_o_")),
                     "ниже предмет %d (стоит на нём %d), пол выше %d; пол есть %d (держится %d)" % (
                         c.get("obj_below", 0), c.get("sits_on_below", 0), c.get("floor_above", 0),
                         c.get("floor", 0), c.get("floor_held_b", 0)),
                     "пример " + cd["example"]]
            if m:
                lines.append("РАЗМЕТКА: %s %s [%s] %s" % (m["mark"], m["to"], m["confidence"], m["reason"]))
                if m["dispute"].strip():
                    lines.append("ВОПРОС: " + m["dispute"])
            for j, ln in enumerate(lines):
                d.text((x0 + 186, y0 + j * 17), ln[:100], fill=(150, 0, 0) if ln.startswith(("РАЗМ", "ВОПР"))
                       else (0, 0, 0), font=fnt)
        p = OUT + "/attach_marks_%d.png" % (page // per + 1)
        img.save(p)
        print("->", p)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    os.chdir(os.path.dirname(HERE))
    fn = {"geom": cmd_geom, "sheet": cmd_sheet, "check": cmd_check, "lock": cmd_lock}.get(
        sys.argv[1] if len(sys.argv) > 1 else "")
    if fn is None:
        print(__doc__)
        sys.exit(0)
    sys.exit(fn() or 0)
