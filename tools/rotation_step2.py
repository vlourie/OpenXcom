# -*- coding: utf-8 -*-
"""Поворот карты на 4 стороны, шаг 2: разбор без видеокарты.

Тот же проход по картам, что у rotation_census2.py (классы картинок совпадают с его числами - скрипт
сверяет это сам), но с подробностями по каждой записи:

  1. стены: запись -> её обратная грань (та же грань / кадр пары / новая)
       census/rotation/wall_backface.tsv
  2. лист спорных стен (без пары и с декором): лицевая HD-грань | её зеркало (так рисует вариант 0) |
     лучший кандидат-пара из набора. Отметки Vitali - art/rotation/wall_marks.tsv
       art/rotation/walls_<игра>.html, art/rotation/walls/<игра>/<id>.png
  3. составные предметы: соседние записи объектов, которые на картах стоят только вместе и чьи кадры
     сходятся в одну картинку
       census/rotation/composite.tsv, лист art/rotation/composite_<игра>_NN.png
  4. симметрия прочих предметов (6 880 у Пираток): зеркало грани со сдвигом по изометрии + форма по LOFT
       census/rotation/object_symmetry.tsv, листы art/rotation/objects/<игра>_<отметка>_NN.png,
       поправки Vitali - art/rotation/object_marks.tsv
  итог  census/rotation/step2_counts.json

    py -3.13 tools\\rotation_step2.py              # всё
    py -3.13 tools\\rotation_step2.py --no-sheets  # только таблицы и числа (с учётом отметок)
Справка: docs/research/map-rotation-2026-10-20.md, раздел «Шаг 2».
"""
import argparse
import html
import json
import os
import random
import sys
from collections import defaultdict, Counter

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = r"E:\OpenXCom"
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "hdart"))
import pck_census as pc          # noqa: E402
import rotation_census as rc     # noqa: E402
import rotation_census2 as rc2   # noqa: E402
import xcom_sprites as xs        # noqa: E402

ENC = "utf-8-sig"
PZ = os.path.join(ROOT, "Пиратки", "Dioxine_XPiratez")
CENSUS = os.path.join(ROOT, "census", "rotation")
ART = os.path.join(ROOT, "art", "rotation")
RANK = {"пол": 0, "стена_одна": 1, "стена_пара": 2, "стена_без_пары": 3, "стена_декор": 3,
                   "объект_симм": 4, "объект_у_стены": 5, "объект": 6}

GAMES = {
    "piratez": dict(
        roots=[os.path.join(PZ, "user", "mods", "Piratez"), os.path.join(PZ, "standard", "xcom1"),
               os.path.join(PZ, "UFO")],
        rul=os.path.join(PZ, "user", "mods", "Piratez", "Ruleset"),
        hd=os.path.join(PZ, "user", "mods", "hd", "hd", "TERRAIN")),
    "ufo": dict(
        roots=[os.path.join(ROOT, "bin", "standard", "xcom1"), os.path.join(ROOT, "bin", "UFO")],
        rul=os.path.join(ROOT, "bin", "standard", "xcom1"),
        hd=os.path.join(ROOT, "user", "mods", "hd", "hd", "TERRAIN")),
}


# ------------------------------------------------------------------ проход по картам

def load_trees():
    trees = set()
    for i, line in enumerate(open(os.path.join(ROOT, "census", "trees", "trees.tsv"), encoding=ENC)):
        if i:
            c = line.split("\t")
            trees.add((c[0], int(c[1])))
    return trees


def scan(game, trees):
    """Повтор rotation_census2.run с подробностями. Возвращает словарь со всем нужным шагам 1-4."""
    g = GAMES[game]
    files = pc.Files(g["roots"])
    terrains = rc.collect(g["rul"])
    cache, sizes = {}, {}
    used = defaultdict(Counter)
    role = defaultdict(Counter)
    places = Counter()                     # (s, rec, part) -> мест на картах
    obj_blocks = []                        # [(блок, {(x, y, z): (s, rec)})] - объекты для составных
    seen_blocks = set()
    for tname, t in terrains.items():
        sets = list(t["mapDataSets"])
        for s in sets:
            sizes.setdefault(s, len(rc.mcd_full(files, s, cache)))
        for b in t["mapBlocks"]:
            bn = b.get("name") if isinstance(b, dict) else None
            mp = files.find(os.path.join("MAPS", bn + ".MAP")) if bn else None
            if not mp:
                continue
            m = rc2.read_map3(mp)
            if not m:
                continue
            sx, sy, sz, cells = m
            covered = {}
            for (x, y, z) in cells:
                covered[(x, y, z)] = any(cells.get((x, y, zz), b"\0")[0] for zz in range(z + 1, sz))
            # блок, который стоит в нескольких террейнах с теми же наборами, для составных считается раз
            bkey = (bn.upper(), tuple(sets))
            objs = {} if bkey not in seen_blocks else None
            seen_blocks.add(bkey)
            for (x, y, z), c in cells.items():
                for part in range(4):
                    v = c[part]
                    if not v:
                        continue
                    s, rec = pc.resolve(v, sets, sizes)
                    if s is None:
                        continue
                    used[(s, rec)][part] += 1
                    places[(s, rec, part)] += 1
                    if part == 3 and objs is not None:
                        objs[(x, y, z)] = (s, rec)
                    if part in (1, 2):
                        back = (x - 1, y, z) if part == 1 else (x, y - 1, z)
                        if back not in cells:
                            continue
                        f, bk = covered[(x, y, z)], covered[back]
                        r = "одна" if f == bk else ("изнутри" if f else "снаружи")
                        role[(s, rec, part)][r] += 1
            if objs:
                obj_blocks.append(("%s/%s" % (tname, bn), objs))
    reach = {k: set(v) for k, v in used.items()}
    rroles = {k: Counter(v) for k, v in role.items()}
    via = {}                               # (s, rec) -> из какой записи достигнута по die/alt
    stack = list(reach)
    while stack:
        s, rec = stack.pop()
        recs = cache.get(s) or []
        if rec >= len(recs):
            continue
        for nxt in (recs[rec]["die"], recs[rec]["alt"]):
            if nxt and nxt < len(recs):
                k = (s, nxt)
                before = set(reach.get(k, set()))
                reach.setdefault(k, set()).update(reach[(s, rec)])
                if k not in used:
                    via.setdefault(k, set()).add("die" if nxt == recs[rec]["die"] else "alt")
                for part in (1, 2):
                    if (s, rec, part) in rroles and (s, nxt, part) not in rroles:
                        rroles[(s, nxt, part)] = Counter(rroles[(s, rec, part)])
                if reach[k] != before:
                    stack.append(k)
    classes = rc2.load_classes()
    frames_of = {}
    for s in sorted({k[0] for k in reach}):
        fr, size = pc.read_set(files, os.path.join("TERRAIN", s + ".PCK"))
        if fr is not None:
            frames_of[s] = (fr, size)
    arr_cache = {}

    def arr(s, f):
        """Кадр индексами (numpy) или None для пустого/отсутствующего."""
        k = (s, f)
        if k not in arr_cache:
            fr, _sz = frames_of[s]
            a = None
            if f < len(fr) and fr[f] is not None:
                a = np.array(fr[f], np.uint8)
                if not a.any():
                    a = None
            arr_cache[k] = a
        return arr_cache[k]

    fp_cache = {}

    def exact(s, f):
        if (s, f) not in fp_cache:
            fp_cache[(s, f)] = pc.fingerprints(frames_of[s][0][f])["exact"]
        return fp_cache[(s, f)]

    wall_rec_dom = {}
    for (s, rec), parts in reach.items():
        if s not in frames_of:
            continue
        for part in (1, 2):
            if part in parts:
                rr = rroles.get((s, rec, part), Counter())
                wall_rec_dom[(s, rec, part)] = rr.most_common(1)[0][0] if rr else "одна"
    sil = defaultdict(list)                # (s, part, роль) -> [(rec, mask)]
    for (s, rec, part), dom in wall_rec_dom.items():
        a = arr(s, cache[s][rec]["frames"][0])
        if a is not None:
            sil[(s, part, dom)].append((rec, a > 0))
    by_part = defaultdict(list)
    for (s, part, _dom), lst in sil.items():
        by_part[(s, part)].extend(lst)

    def iou(a, b):
        if a.shape != b.shape:
            return 0.0
        u = np.logical_or(a, b).sum()
        return float(np.logical_and(a, b).sum()) / u if u else 0.0

    twin_rec = {}
    twin_of = {}
    for (s, part, _dom), lst in sil.items():
        other = by_part.get((s, 3 - part), [])
        for rec, m in lst:
            mm = m[:, ::-1]
            best = max(((iou(mm, o), orec) for (orec, o) in other), default=(0.0, None))
            twin_rec[(s, rec, part)] = best[0] >= 0.9
            twin_of[(s, rec, part)] = best[1] if best[0] >= 0.9 else None
    # ---- записи стен: обратная грань
    wall_rows = {}                         # (s, rec, part) -> сведения
    for (s, rec, part), dom in wall_rec_dom.items():
        r = cache[s][rec]
        cls = classes.get("%s:%d" % (s, rec), ("", ""))   # как rotation_census2: классы переписи и у ванили
        a0 = arr(s, r["frames"][0])
        best = (0.0, None)
        if dom != "одна" and a0 is not None:
            want = "снаружи" if dom == "изнутри" else "изнутри"
            m0 = a0 > 0
            best = max(((iou(m0, m), rr) for (rr, m) in sil.get((s, part, want), [])), default=(0.0, None))
        if "декор" in cls[1]:
            kind = "стена_декор"
        elif dom == "одна":
            kind = "стена_одна"
        else:
            kind = "стена_пара" if best[0] >= 0.9 else "стена_без_пары"
        wall_rows[(s, rec, part)] = dict(kind=kind, dom=dom, roles=rroles.get((s, rec, part), Counter()),
                                         cand=best[1], cand_iou=best[0], twin=twin_of.get((s, rec, part)),
                                         cls=cls[1])
    # ---- картинки (как rotation_census2): exact -> вид, подвид, кто дал вид
    need = {}
    twins = {}
    members = defaultdict(list)            # exact -> [(s, f, rec, part)]
    for (s, rec), parts in reach.items():
        if s not in frames_of:
            continue
        r = cache[s][rec]
        cls = classes.get("%s:%d" % (s, rec), ("", ""))
        for part in sorted(parts):
            if part == 0:
                kind = "пол"
            elif part in (1, 2):
                kind = wall_rows[(s, rec, part)]["kind"]
            else:
                kind = None
            for f in set(r["frames"]):
                a = arr(s, f)
                if a is None:
                    continue
                frame = frames_of[s][0][f]
                h = len(frame)
                k = kind
                if k is None:
                    ms, ps = rc2.mirror_sym(frame)
                    solid = r["big_wall"] == 1 and not (cls[0] == "BW1" and
                                                         cls[1] in ("предмет_кандидат", "многоклеточная_кандидат"))
                    if (s, f) in trees or solid:
                        k = "объект_симм"
                    elif cls[0] == "NEAR_WALL_ITEM":
                        k = "объект_у_стены"
                    elif ms >= 0.9 and ps >= 0.6:
                        k = "объект_симм"
                    else:
                        k = "объект"
                ex = exact(s, f)
                sub = ""
                if k == "пол":
                    fh = rc2.floor_height(frame, h)
                    sub = "плоский" if fh <= 2 and r["tlevel"] == 0 else ("низкий" if fh <= 6 else "высокий")
                if k == "объект_симм":
                    sub = "растение" if (s, f) in trees else ("куб" if r["big_wall"] == 1 else "зеркальный")
                if kind and kind.startswith("стена"):
                    twins[ex] = twins.get(ex, False) or twin_rec.get((s, rec, part), False)
                members[ex].append((s, f, rec, part))
                prev = need.get(ex)
                if prev is None or RANK[k] > RANK[prev[0]]:
                    need[ex] = (k, sub, (s, f, rec, part))
    return dict(game=game, files=files, cache=cache, frames_of=frames_of, arr=arr, exact=exact,
                reach=reach, places=places, wall_rows=wall_rows, need=need, twins=twins, members=members,
                obj_blocks=obj_blocks, via=via, wall_rec_dom=wall_rec_dom)


def check_against_census2(d, game):
    """Числа обязаны совпасть с rotation_counts2.json - иначе разбор идёт не по тем данным."""
    ref = json.load(open(os.path.join(CENSUS, "rotation_counts2.json"), encoding=ENC))[game]
    got = Counter(v[0] for v in d["need"].values())
    bad = {k: (got.get(k, 0), v) for k, v in ref["по_виду"].items() if got.get(k, 0) != v}
    if len(d["need"]) != ref["картинок"] or bad:
        raise SystemExit("%s: расходится с rotation_counts2.json: всего %d против %d, %s" %
                         (game, len(d["need"]), ref["картинок"], bad))
    return dict(got)


# ------------------------------------------------------------------ картинки

class Pics:
    """Классический кадр (палитрой игры) и HD-кадр пака, оба приведены к 128x160."""

    def __init__(self, d, game):
        self.d = d
        self.hd_dir = GAMES[game]["hd"]
        if game == "piratez":
            pal = Image.open(os.path.join(ROOT, "art", "TERRAIN", "ACHURCH.PCK", "original.png")).getpalette()
            self.pal = np.array(pal[:768], np.uint8).reshape(256, 3)
        else:
            self.pal = np.array(xs.load_palette(os.path.join(ROOT, "bin", "UFO", "GEODATA", "PALETTES.DAT")),
                                np.uint8)

    def classic(self, s, f, scale=4):
        a = self.d["arr"](s, f)
        if a is None:
            return None
        rgba = np.zeros(a.shape + (4,), np.uint8)
        rgba[..., :3] = self.pal[a]
        rgba[..., 3] = np.where(a > 0, 255, 0)
        im = Image.fromarray(rgba, "RGBA")
        return im.resize((im.width * scale, im.height * scale), Image.NEAREST)

    def hd(self, s, f):
        for name in (s.upper(), s):
            p = os.path.join(self.hd_dir, name + ".PCK", "%d.png" % f)
            if os.path.exists(p):
                im = Image.open(p).convert("RGBA")
                a = self.d["arr"](s, f)
                if a is not None and im.size != (a.shape[1] * 4, a.shape[0] * 4):
                    im = im.resize((a.shape[1] * 4, a.shape[0] * 4), Image.LANCZOS)
                return im
        return None

    def best(self, s, f):
        im = self.hd(s, f)
        return (im, "HD") if im is not None else (self.classic(s, f), "классика")


def font(n):
    for f in ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/segoeui.ttf"):
        if os.path.exists(f):
            return ImageFont.truetype(f, n)
    return ImageFont.load_default()


BG = (34, 34, 40, 255)


def on_bg(im, w, h):
    out = Image.new("RGBA", (w, h), BG)
    if im is not None:
        out.alpha_composite(im, ((w - im.width) // 2, h - im.height))
    return out


# ------------------------------------------------------------------ 1. стены -> обратная грань

def wall_table(d, game):
    rows = []
    for (s, rec, part), w in sorted(d["wall_rows"].items()):
        r = d["cache"][s][rec]
        f0 = r["frames"][0]
        a = d["arr"](s, f0)
        ex = d["exact"](s, f0) if a is not None else ""
        if w["kind"] == "стена_одна":
            back, ref = "та_же_грань", ""
        elif w["kind"] == "стена_пара":
            back, ref = "кадр_пары", "%s:%d" % (s, w["cand"])
        elif w["kind"] == "стена_декор":
            back, ref = "новая_без_декора", ""
        else:
            back, ref = "новая", ""
        pic_kind = d["need"][ex][0] if ex in d["need"] else ""
        roles = w["roles"]
        rows.append([game, s, rec, "west" if part == 1 else "north", f0, ex,
                     d["places"].get((s, rec, part), 0), "да" if (s, rec) in d["via"] else "",
                     roles.get("одна", 0), roles.get("изнутри", 0), roles.get("снаружи", 0), w["dom"],
                     w["kind"], back, ref,
                     "%s:%d" % (s, w["cand"]) if w["cand"] is not None else "", "%.2f" % w["cand_iou"],
                     "%s:%d" % (s, w["twin"]) if w["twin"] is not None else "", pic_kind])
    return rows


WALL_HEAD = ["игра", "набор", "запись", "часть", "кадр", "картинка", "мест", "только_die_alt",
             "мест_одна", "мест_изнутри", "мест_снаружи", "роль", "вид_записи", "обратная_грань",
             "обратная_запись", "лучший_кандидат", "IoU_кандидата", "близнец", "вид_картинки"]


def write_tsv(path, head, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding=ENC, newline="") as f:
        f.write("\t".join(head) + "\n")
        for r in rows:
            f.write("\t".join(str(v) for v in r) + "\n")


# ------------------------------------------------------------------ 2. лист спорных стен

def disputed_walls(d):
    """Картинки, которые требуют новой обратной грани (стена_без_пары, стена_декор), с представителем."""
    out = []
    for ex, (k, _sub, who) in d["need"].items():
        if k not in ("стена_без_пары", "стена_декор"):
            continue
        s, f, rec, part = who
        w = d["wall_rows"][(s, rec, part)]
        recs = sorted({"%s:%d" % (m[0], m[2]) for m in d["members"][ex]})
        pl = sum(d["places"].get((m[0], m[2], m[3]), 0) for m in d["members"][ex] if m[3] in (1, 2))
        out.append(dict(ex=ex, kind=k, s=s, f=f, rec=rec, part=part, dom=w["dom"], cand=w["cand"],
                        cand_iou=w["cand_iou"], recs=recs, places=pl, cls=w["cls"]))
    out.sort(key=lambda x: (x["s"], x["f"]))
    for i, x in enumerate(out):
        x["id"] = "W%04d" % (i + 1)
    return out


def wall_sheet(d, game, pics, items):
    outd = os.path.join(ART, "walls", game)
    os.makedirs(outd, exist_ok=True)
    fn = font(13)
    W, H = 128, 160
    for x in items:
        face, src = pics.best(x["s"], x["f"])
        mirror = face.transpose(Image.FLIP_LEFT_RIGHT) if face is not None else None
        cand = None
        if x["cand"] is not None and x["cand_iou"] >= 0.5:
            cf = d["cache"][x["s"]][x["cand"]]["frames"][0]
            cand, csrc = pics.best(x["s"], cf)
        card = Image.new("RGBA", (3 * (W + 8) + 8, H + 44), BG)
        for i, im in enumerate((face, mirror, cand)):
            card.alpha_composite(on_bg(im, W, H), (8 + i * (W + 8), 8))
        dr = ImageDraw.Draw(card)
        dr.text((8, H + 12), "%s  %s:%d %s  %s  мест %d" % (x["id"], x["s"], x["rec"],
                                                             "W" if x["part"] == 1 else "N", x["dom"], x["places"]),
                fill=(230, 230, 230), font=fn)
        dr.text((8, H + 27), "лицо (%s) | зеркало = вариант 0 | %s" %
                (src, ("пара? %s:%d IoU %.2f" % (x["s"], x["cand"], x["cand_iou"])) if cand is not None
                 else "кандидата нет"), fill=(170, 170, 180), font=fn)
        card.convert("RGB").save(os.path.join(outd, x["id"] + ".png"))


def wall_html(game, items):
    cards = []
    for x in items:
        cands = x["cand"] is not None and x["cand_iou"] >= 0.5
        cards.append(
            '<div class="c" data-id="%s" data-set="%s"><img loading="lazy" src="walls/%s/%s.png">'
            '<div class="b"><button data-m="S">одинаковы</button>%s<button data-m="N">новая</button>'
            '<span class="k">%s%s</span></div></div>' %
            (x["id"], x["s"], game, x["id"],
             '<button data-m="P">пара верна</button>' if cands else "",
             html.escape(x["kind"].replace("стена_", "")),
             (" · " + html.escape(x["cls"])) if x["cls"] else ""))
    sets = sorted({x["s"] for x in items})
    page = """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Обратные грани стен</title>
<style>
:root{--bg:#1d1d22;--fg:#e6e6e6;--mut:#9a9aa6;--card:#26262d;--s:#2f7d4a;--p:#2f5f9d;--n:#8d3b3b}
body{background:var(--bg);color:var(--fg);font:14px system-ui,sans-serif;margin:0;padding:12px 16px}
header{position:sticky;top:0;background:var(--bg);padding:8px 0;z-index:2;border-bottom:1px solid #333}
.g{display:flex;flex-wrap:wrap;gap:10px;margin-top:10px}
.c{background:var(--card);padding:4px;border:3px solid transparent;max-width:100%%}
.c img{display:block;max-width:100%%}
.c[data-mark=S]{border-color:var(--s)}.c[data-mark=P]{border-color:var(--p)}.c[data-mark=N]{border-color:var(--n)}
.b{display:flex;gap:6px;align-items:center;padding-top:4px;flex-wrap:wrap}
button{background:#3a3a44;color:var(--fg);border:0;padding:4px 8px;cursor:pointer}
.k{color:var(--mut);font-size:12px}
select,input{background:#2c2c34;color:var(--fg);border:1px solid #444;padding:3px}
</style></head><body>
<header><b>Обратные грани стен — %s</b> · %d картинок ·
<span id="cnt"></span><br>
Лицо | его зеркало (так показывает вариант 0) | кандидат-пара из набора.
<b>одинаковы</b> — обратная сторона такая же, как лицо (рисовать не надо);
<b>пара верна</b> — правый кадр и есть обратная сторона; <b>новая</b> — рисовать.
Без отметки — считается «новая».
<br>Набор: <select id="flt"><option value="">все</option>%s</select>
<button id="dl">Скачать отметки (wall_marks_%s.tsv)</button>
Файл положить в art/rotation/, скрипт читает его сам.</header>
<div class="g" id="g">%s</div>
<script>
const KEY="wall_marks_%s";let marks={};
try{marks=JSON.parse(localStorage.getItem(KEY)||"{}")}catch(e){}
function save(){try{localStorage.setItem(KEY,JSON.stringify(marks))}catch(e){}cnt()}
function cnt(){const c={S:0,P:0,N:0};for(const k in marks)c[marks[k]]++;
document.getElementById("cnt").textContent="отмечено: одинаковы "+c.S+", пара "+c.P+", новая "+c.N}
document.querySelectorAll(".c").forEach(el=>{const id=el.dataset.id;if(marks[id])el.dataset.mark=marks[id];
el.querySelectorAll("button").forEach(b=>b.onclick=()=>{const m=b.dataset.m;
if(marks[id]===m){delete marks[id];delete el.dataset.mark}else{marks[id]=m;el.dataset.mark=m}save()})});
document.getElementById("flt").onchange=e=>{const v=e.target.value;
document.querySelectorAll(".c").forEach(el=>el.style.display=(!v||el.dataset.set===v)?"":"none")};
document.getElementById("dl").onclick=()=>{let t="id\\tотметка\\n";for(const k of Object.keys(marks).sort())t+=k+"\\t"+marks[k]+"\\n";
const a=document.createElement("a");a.href=URL.createObjectURL(new Blob(["\\ufeff"+t],{type:"text/tab-separated-values"}));
a.download="wall_marks_%s.tsv";a.click()};cnt();
</script></body></html>""" % (game, len(items), "".join('<option>%s</option>' % s for s in sets), game,
                               "\n".join(cards), game, game)
    with open(os.path.join(ART, "walls_%s.html" % game), "w", encoding="utf-8") as f:
        f.write(page)


def read_marks(path, allowed):
    out = {}
    if os.path.exists(path):
        for i, line in enumerate(open(path, encoding=ENC)):
            c = line.rstrip("\r\n").split("\t")
            if i == 0 or len(c) < 2 or not c[1].strip():
                continue
            m = c[1].strip().upper()[:1]
            m = {"О": "S", "П": "P", "Н": "N", "Д": "Y"}.get(m, m)
            if m in allowed:
                out[c[0].strip()] = m
    return out


# ------------------------------------------------------------------ 3. составные предметы

def composites(d, game):
    """Связь двух записей-объектов: соседние клетки, стоят вместе в 80 %+ мест каждой, кадры касаются."""
    cache, arr = d["cache"], d["arr"]
    n = Counter()
    co = Counter()
    where = defaultdict(list)
    for bname, objs in d["obj_blocks"]:
        for pos, a in objs.items():
            n[a] += 1
            x, y, z = pos
            for dz in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        if not (dx or dy or dz):
                            continue
                        b = objs.get((x + dx, y + dy, z + dz))
                        if b is None or b == a:
                            continue
                        co[(a, (dx, dy, dz), b)] += 1
                        if len(where[(a, (dx, dy, dz), b)]) < 3:
                            where[(a, (dx, dy, dz), b)].append("%s@%d,%d,%d" % (bname, x, y, z))

    def mask(rec):
        s, r = rec
        a = arr(s, cache[s][r]["frames"][0])
        return None if a is None else (a > 0)

    def screen(rec, off):
        dx, dy, dz = off
        s, r = rec
        return 16 * (dx - dy), 8 * (dx + dy) - 24 * dz - cache[s][r]["plevel"]

    def contact(a, b, off):
        ma, mb = mask(a), mask(b)
        if ma is None or mb is None:
            return 0
        oxa, oya = screen(a, (0, 0, 0))
        oxb, oyb = screen(b, off)
        h = max(ma.shape[0], mb.shape[0]) + 80
        w = max(ma.shape[1], mb.shape[1]) + 80
        ca = np.zeros((h, w), bool)
        cb = np.zeros((h, w), bool)
        ca[40 + oya:40 + oya + ma.shape[0], 40 + oxa:40 + oxa + ma.shape[1]] = ma
        y0, x0 = 40 + oyb, 40 + oxb
        if y0 < 0 or x0 < 0 or y0 + mb.shape[0] > h or x0 + mb.shape[1] > w:
            return 0
        cb[y0:y0 + mb.shape[0], x0:x0 + mb.shape[1]] = mb
        dil = ca.copy()
        dil[1:] |= ca[:-1]; dil[:-1] |= ca[1:]; dil[:, 1:] |= ca[:, :-1]; dil[:, :-1] |= ca[:, 1:]
        return int((dil & cb & ~ca).sum() + (ca & cb).sum())

    links = []
    for (a, off, b), c in co.items():
        if a > b:                          # пару смотрим один раз
            continue
        if c / n[a] < 0.8 or c / n[b] < 0.8:
            continue
        ct = contact(a, b, off)
        once = n[a] == 1 and n[b] == 1
        if ct < (6 if once else 3):
            continue
        links.append((a, off, b, c, ct, once))
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for a, off, b, c, ct, once in links:
        parent[find(a)] = find(b)
    groups = defaultdict(list)
    for x in list(parent):
        groups[find(x)].append(x)
    # смещение членов от корня группы по связям (обход в ширину)
    adj = defaultdict(list)
    for a, off, b, c, ct, once in links:
        adj[a].append((b, off))
        adj[b].append((a, (-off[0], -off[1], -off[2])))
    out = []
    for root, mem in groups.items():
        start = min(mem)
        pos = {start: (0, 0, 0)}
        q = [start]
        while q:
            u = q.pop()
            for v, off in adj[u]:
                if v not in pos:
                    pu = pos[u]
                    pos[v] = (pu[0] + off[0], pu[1] + off[1], pu[2] + off[2])
                    q.append(v)
        mn = [min(p[i] for p in pos.values()) for i in range(3)]
        pos = {k: (p[0] - mn[0], p[1] - mn[1], p[2] - mn[2]) for k, p in pos.items()}
        ext = [max(p[i] for p in pos.values()) + 1 for i in range(3)]
        pics = set()
        kinds = Counter()
        for (s, r) in mem:
            for f in set(cache[s][r]["frames"]):
                if arr(s, f) is not None:
                    ex = d["exact"](s, f)
                    if ex not in pics:
                        pics.add(ex)
                        kinds[d["need"][ex][0] if ex in d["need"] else "?"] += 1
        # целое, собранное по клеткам как на карте (индексы, k=1): насколько оно совпадает со своим зеркалом
        canvas = np.zeros((120 + 24 * ext[2] + 8 * (ext[0] + ext[1]), 64 + 16 * (ext[0] + ext[1])), np.uint8)
        for m in sorted(pos, key=lambda m: (pos[m][2], pos[m][1], pos[m][0])):
            s, r = m
            a = arr(s, cache[s][r]["frames"][0])
            if a is None:
                continue
            x, y, z = pos[m]
            sx = 16 * (x - y) + 16 * ext[1]
            sy = 8 * (x + y) - 24 * z + 24 * ext[2] - cache[s][r]["plevel"] + 20
            if sy < 0 or sy + a.shape[0] > canvas.shape[0] or sx + a.shape[1] > canvas.shape[1]:
                continue
            sub = canvas[sy:sy + a.shape[0], sx:sx + a.shape[1]]
            sub[a > 0] = a[a > 0]
        whole = self_mirror(canvas) if canvas.any() else 0.0
        glinks = [l for l in links if l[0] in pos]
        once = all(l[5] for l in glinks)
        ex_where = []
        for l in glinks[:2]:
            ex_where += where[(l[0], l[1], l[2])][:1]
        out.append(dict(mem=sorted(mem), pos=pos, ext=ext, pics=pics, kinds=kinds,
                        sure="один_раз" if once else "надёжно", places=min(n[m] for m in mem), whole=whole,
                        where=ex_where))
    out.sort(key=lambda g: (g["sure"] != "надёжно", -len(g["mem"]), g["mem"]))
    for i, g in enumerate(out):
        g["id"] = "C%04d" % (i + 1)
        main = g["kinds"].most_common(1)[0][0] if g["kinds"] else "?"
        g["kind"] = ("растение" if any(k == "объект_симм" for k in g["kinds"]) and
                     all(d["need"].get(e, ("", "", None))[1] == "растение" for e in g["pics"])
                     else main)
        # растение и целое, симметричное само себе (купол, кольцо, бак): повёрнутый вид целого = тот же,
        # нужно лишь отдать клетке тот кусок, что теперь стоит на её месте на экране - это код
        g["fix"] = "перестановка_кусков" if g["kind"] == "растение" or g["whole"] >= 0.92 else "вид_целиком"
    return out


def composite_rows(game, groups):
    rows = []
    for g in groups:
        rows.append([g["id"], game, g["sure"], len(g["mem"]), len(g["pics"]), g["places"],
                     "%dx%dx%d" % tuple(g["ext"]), g["kind"], "%.2f" % g["whole"], g["fix"],
                     ",".join("%s=%d" % kv for kv in sorted(g["kinds"].items())),
                     " ".join("%s:%d@%d,%d,%d" % (s, r, *g["pos"][(s, r)]) for (s, r) in g["mem"]),
                     " ".join(g["where"])])
    return rows


COMP_HEAD = ["группа", "игра", "уверенность", "записей", "картинок", "мест", "размер_XxYxZ", "вид", "целое_сам_зеркало", "поворот",
             "картинки_по_видам", "состав_набор:запись@x,y,z", "пример_блок@клетка"]


def composite_sheet(d, game, pics, groups, per_page=30):
    fn = font(12)
    cw, ch = 220, 230
    for fn_ in os.listdir(ART):                    # страницы прошлого прогона
        if fn_.startswith("composite_%s_" % game) and fn_.endswith(".png"):
            os.remove(os.path.join(ART, fn_))
    sure = [g for g in groups if g["sure"] == "надёжно"] + [g for g in groups if g["sure"] != "надёжно"]
    for page in range(0, len(sure), per_page):
        chunk = sure[page:page + per_page]
        cols = 6
        rows = (len(chunk) + cols - 1) // cols
        sheet = Image.new("RGBA", (cols * cw, rows * ch), BG)
        dr = ImageDraw.Draw(sheet)
        for i, g in enumerate(chunk):
            canvas = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
            order = sorted(g["mem"], key=lambda m: (g["pos"][m][2], g["pos"][m][1], g["pos"][m][0]))
            for m in order:
                s, r = m
                im = pics.classic(s, d["cache"][s][r]["frames"][0], scale=2)
                if im is None:
                    continue
                x, y, z = g["pos"][m]
                sx = 200 + 32 * (x - y) - 32
                sy = 200 + 16 * (x + y) - 48 * z - 2 * d["cache"][s][r]["plevel"] - 80
                canvas.alpha_composite(im, (max(0, sx), max(0, sy)))
            bb = canvas.getbbox()
            if bb:
                canvas = canvas.crop(bb)
                canvas.thumbnail((cw - 10, ch - 40))
            cx, cy = (i % cols) * cw, (i // cols) * ch
            sheet.alpha_composite(on_bg(canvas, cw - 10, ch - 40), (cx + 5, cy + 5))
            dr.text((cx + 5, ch - 33 + cy), "%s %s %s" % (g["id"], g["sure"], g["kind"]), fill=(230, 230, 230),
                    font=fn)
            dr.text((cx + 5, ch - 18 + cy), "%d карт. %s мест %d · %s %.2f" %
                    (len(g["pics"]), "x".join(map(str, g["ext"])), g["places"],
                     "перестановка" if g["fix"] != "вид_целиком" else "целиком", g["whole"]),
                    fill=(150, 200, 150) if g["fix"] != "вид_целиком" else (170, 170, 180), font=fn)
        sheet.convert("RGB").save(os.path.join(ART, "composite_%s_%02d.png" % (game, page // per_page + 1)))


# ------------------------------------------------------------------ 4. симметрия прочих предметов

class Loft:
    def __init__(self, files):
        p = files.find(os.path.join("TERRAIN", "LOFTEMPS.DAT")) or files.find(os.path.join("GEODATA",
                                                                                           "LOFTEMPS.DAT"))
        data = np.frombuffer(open(p, "rb").read(), "<u2")
        self.loft = ((data[:, None] >> np.arange(16)) & 1).astype(bool).reshape(-1, 16, 16)
        self.raw = {}
        self.files = files

    def vox(self, s, rec):
        if s not in self.raw:
            p = self.files.find(os.path.join("TERRAIN", s + ".MCD"))
            dd = open(p, "rb").read() if p else b""
            self.raw[s] = [dd[i:i + 62] for i in range(0, len(dd) - 61, 62)]
        r = self.raw[s][rec]
        ids = [min(int(v), len(self.loft) - 1) for v in r[8:20]]
        return np.stack([self.loft[i] if i else np.zeros((16, 16), bool) for i in ids])


def vox_sym(v):
    """(форма тривиальна, лучшая осевая симметрия). Отражение - относительно своей оси предмета (середина
    рамки вокселей), а не середины клетки: предметы Пираток часто стоят у края клетки. Тривиальная - пусто
    или прямоугольный брус: не меняется ни при каком отражении, о симметрии предмета по ней сказать нечего."""
    if not v.any():
        return True, 1.0
    zz, yy, xx = np.nonzero(v)
    v = v[:, yy.min():yy.max() + 1, xx.min():xx.max() + 1]

    def viou(a, b):
        u = np.logical_or(a, b).sum()
        return float(np.logical_and(a, b).sum()) / u if u else 1.0
    fx = viou(v, v[:, :, ::-1])
    fy = viou(v, v[:, ::-1, :])
    trivial = min(fx, fy) >= 0.98 and v[zz.min():zz.max() + 1].all()
    return trivial, max(fx, fy)


def self_mirror(a):
    """Силуэт кадра против своего зеркала относительно своей оси (середина рамки): круглое, квадратное в
    плане, столб - близко к 1."""
    m = a > 0
    ys, xs_ = np.nonzero(m)
    m = m[:, xs_.min():xs_.max() + 1]
    u = np.logical_or(m, m[:, ::-1]).sum()
    return float(np.logical_and(m, m[:, ::-1]).sum()) / u if u else 0.0


def face_mirror(a):
    """Зеркало видимой грани со сдвигом изометрии. Предмет, симметричный слева направо, при взгляде
    на лицевую грань (левая половина кадра, грань юга) переходит в себя преобразованием
    (x, y) -> (2m - x, y + m - x); грань востока (правая половина) - (x, y) -> (2m - x, y - m + x).
    Возвращает (рисунок, силуэт, сторона): доли пикселей половины, у которых образ совпал по цвету
    (тот же индекс или сосед по рампе) и просто непрозрачен - лучшее по m."""
    h, w = a.shape
    ys, xs_ = np.nonzero(a)
    best = (0.0, 0.0, "")
    cx = w / 2.0
    for side, sign, sel in (("лицо", 1, xs_ < cx), ("бок", -1, xs_ >= cx)):
        py, px = ys[sel], xs_[sel]
        if len(px) < 12:
            continue
        v = a[py, px].astype(int)
        lo, hi = int(px.min()), int(px.max())
        for s2 in range(2 * lo, 2 * hi + 1):          # 2m
            nx = s2 - px
            for rnd in (0, 1):
                ny = py + sign * ((s2 - 2 * px + rnd) // 2)
                ok = (nx >= 0) & (nx < w) & (ny >= 0) & (ny < h)
                tv = np.zeros_like(v)
                tv[ok] = a[ny[ok], nx[ok]]
                shape = float((tv > 0).sum()) / len(v)
                if shape < best[1] * 0.5:
                    continue
                same = (tv > 0) & ((tv == v) | ((np.abs(tv - v) <= 2) & (tv // 16 == v // 16)))
                draw = float(same.sum()) / len(v)
                if draw > best[0]:
                    best = (draw, shape, side)
    return best


MARKS = ("да", "нет", "не_ясно", "низкий")
# поправки Vitali в art/rotation/object_marks_<игра>.tsv (id, отметка): Д - симметричен, Н - нет, ? - не ясно,
# L - низкий (как пол)
MARK_CODE = {"Y": "да", "N": "нет", "?": "не_ясно", "L": "низкий"}
SYM_T_YES = 0.80
SYM_T_NO = 0.55
SYM_LOFT_NO = 0.75


def symmetry(d, game):
    lf = Loft(d["files"])
    out = []
    for ex, (k, _sub, who) in d["need"].items():
        if k != "объект":
            continue
        s, f, rec, part = who
        a = d["arr"](s, f)
        draw, shape, side = face_mirror(a)
        trivial, lsym = vox_sym(lf.vox(s, rec))
        selfm = self_mirror(a)
        low = rc2.floor_height(d["frames_of"][s][0][f], a.shape[0])
        # только через die (разрушенный вид). Классом не стал: на выборке половина таких - целые на вид вещи
        debris = all(d["via"].get((m[0], m[2])) == {"die"} for m in d["members"][ex])
        loft_ok = trivial or lsym >= 0.9
        if low <= 3:
            mark = "низкий"            # лежит на ромбе пола: поворачивается как пол, кодом (при 6 px на
                                       # выборке попадали ящики и горшки - у них бока перекосит)
        elif loft_ok and (draw >= SYM_T_YES or selfm >= 0.92):
            mark = "да"
        elif (draw < SYM_T_NO and selfm < 0.8) or (not trivial and lsym < SYM_LOFT_NO):
            mark = "нет"
        else:
            mark = "не_ясно"
        out.append(dict(ex=ex, s=s, f=f, rec=rec, draw=draw, shape=shape, side=side, trivial=trivial,
                        lsym=lsym, selfm=selfm, low=low, debris=debris, mark=mark, n=len(d["members"][ex])))
    out.sort(key=lambda x: (x["s"], x["f"]))
    for i, x in enumerate(out):
        x["id"] = "O%04d" % (i + 1)
    return out


SYM_HEAD = ["id", "игра", "набор", "кадр", "запись", "картинка", "отметка_авто", "рисунок_грани",
            "силуэт_грани", "грань", "LOFT_тривиальна", "LOFT_осевая", "силуэт_сам_зеркало", "высота_над_ромбом", "только_die", "записей_с_картинкой", "отметка_Vitali",
            "итог"]


def symmetry_sheets(d, game, pics, items, per_page=80):
    outd = os.path.join(ART, "objects")
    os.makedirs(outd, exist_ok=True)
    for fn_ in os.listdir(outd):                   # страницы прошлого прогона: их число могло быть другим
        if fn_.startswith(game + "_") and fn_.endswith(".png"):
            os.remove(os.path.join(outd, fn_))
    fn = font(11)
    cw, ch = 104, 150
    cols = 10
    for mark in MARKS:
        lst = [x for x in items if x["mark"] == mark]
        for page in range(0, len(lst), per_page):
            chunk = lst[page:page + per_page]
            rows = (len(chunk) + cols - 1) // cols
            sheet = Image.new("RGBA", (cols * cw, rows * ch), BG)
            dr = ImageDraw.Draw(sheet)
            for i, x in enumerate(chunk):
                im, _src = pics.best(x["s"], x["f"])
                if im is not None:
                    im = im.copy()
                    im.thumbnail((cw - 8, ch - 30))
                cx, cy = (i % cols) * cw, (i // cols) * ch
                sheet.alpha_composite(on_bg(im, cw - 8, ch - 30), (cx + 4, cy + 4))
                dr.text((cx + 4, cy + ch - 25), "%s %.2f" % (x["id"], x["draw"]), fill=(230, 230, 230), font=fn)
                dr.text((cx + 4, cy + ch - 13), "%s:%d" % (x["s"][:10], x["f"]), fill=(160, 160, 170), font=fn)
            sheet.convert("RGB").save(os.path.join(outd, "%s_%s_%02d.png" % (game, mark, page // per_page + 1)))


def sample_sheet(d, game, pics, items, n=40, seed=20):
    """Выборка на глаз: по n случайных из каждой отметки, лицо и его простое зеркало рядом."""
    rnd = random.Random(seed)
    fn = font(11)
    cw, ch = 200, 150
    cols = 5
    for mark in MARKS:
        lst = [x for x in items if x["mark"] == mark]
        chunk = rnd.sample(lst, min(n, len(lst)))
        rows = (len(chunk) + cols - 1) // cols
        sheet = Image.new("RGBA", (cols * cw, rows * ch), BG)
        dr = ImageDraw.Draw(sheet)
        for i, x in enumerate(chunk):
            im, _src = pics.best(x["s"], x["f"])
            cx, cy = (i % cols) * cw, (i // cols) * ch
            if im is not None:
                im = im.copy()
                im.thumbnail((92, 120))
                sheet.alpha_composite(on_bg(im, 92, 120), (cx + 4, cy + 4))
                sheet.alpha_composite(on_bg(im.transpose(Image.FLIP_LEFT_RIGHT), 92, 120), (cx + 100, cy + 4))
            dr.text((cx + 4, cy + ch - 24), "%s %s:%d" % (x["id"], x["s"][:12], x["f"]), fill=(230, 230, 230),
                    font=fn)
            dr.text((cx + 4, cy + ch - 12), "рис %.2f сил %.2f LOFT %s %.2f" % (x["draw"], x["selfm"], "т" if x["trivial"] else "ф",
                                                                    x["lsym"]), fill=(160, 160, 170), font=fn)
        sheet.convert("RGB").save(os.path.join(ART, "sample_%s_%s.png" % (game, mark)))
        with open(os.path.join(ART, "sample_%s_%s.txt" % (game, mark)), "w", encoding=ENC) as f:
            f.write("\n".join(x["id"] for x in chunk) + "\n")


# ------------------------------------------------------------------ сборка

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-sheets", action="store_true", help="только таблицы и числа")
    ap.add_argument("--games", default="piratez,ufo")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    os.makedirs(ART, exist_ok=True)
    trees = load_trees()
    wall_rows_all, comp_rows_all, sym_rows_all = [], [], []
    summary = {}
    for game in args.games.split(","):
        print("== %s: проход по картам" % game, flush=True)
        d = scan(game, trees if game == "piratez" else set())
        kinds = check_against_census2(d, game)
        print("   сверка с rotation_counts2.json: совпало (%d картинок)" % len(d["need"]), flush=True)
        pics = Pics(d, game)
        # 1
        wall_rows_all += wall_table(d, game)
        # 2
        walls = disputed_walls(d)
        wm = read_marks(os.path.join(ART, "wall_marks_%s.tsv" % game), {"S", "P", "N"})
        if not args.no_sheets:
            print("   лист стен: %d" % len(walls), flush=True)
            wall_sheet(d, game, pics, walls)
            wall_html(game, walls)
        wcnt = Counter(wm.get(x["id"], "N") for x in walls)
        # 3
        groups = composites(d, game)
        comp_rows_all += composite_rows(game, groups)
        if not args.no_sheets:
            composite_sheet(d, game, pics, groups)
        # 4
        print("   симметрия предметов", flush=True)
        syms = symmetry(d, game)
        om = read_marks(os.path.join(ART, "object_marks_%s.tsv" % game), set(MARK_CODE))
        for x in syms:
            v = om.get(x["id"])
            x["final"] = MARK_CODE.get(v, x["mark"])
            sym_rows_all.append([x["id"], game, x["s"], x["f"], x["rec"], x["ex"], x["mark"], "%.3f" % x["draw"],
                                 "%.3f" % x["shape"], x["side"], "да" if x["trivial"] else "",
                                 "%.2f" % x["lsym"], "%.2f" % x["selfm"], x["low"], "да" if x["debris"] else "", x["n"], v or "", x["final"]])
        if not args.no_sheets:
            symmetry_sheets(d, game, pics, syms)
            sample_sheet(d, game, pics, syms)
        # итог
        scnt = Counter(x["final"] for x in syms)
        fix_of = {}
        for g in groups:
            for e in g["pics"]:
                if fix_of.get(e) != "вид_целиком":     # картинка в двух группах - берётся строгая
                    fix_of[e] = g["fix"]
        bucket = Counter()
        for x in syms:
            fx = fix_of.get(x["ex"])
            if fx == "перестановка_кусков":
                bucket["составной_перестановка"] += 1
            elif x["final"] == "низкий":
                bucket["низкий"] += 1
            elif fx == "вид_целиком":
                bucket["составной_целиком"] += 1
            else:
                bucket[x["final"]] += 1
        walls_new = len(walls) - wcnt["S"] - wcnt["P"]
        near = kinds.get("объект_у_стены", 0)
        high = json.load(open(os.path.join(CENSUS, "rotation_counts2.json"), encoding=ENC))[game][
            "подробно"].get("пол/высокий", 0)
        backs = bucket["да"] + bucket["нет"] + bucket["не_ясно"] + bucket["составной_целиком"]
        plan = dict(
            стены=walls_new, виды_сзади=backs,
            A=walls_new + backs,
            A_плюс_бока_несимметричным_мин=walls_new + backs + 2 * bucket["нет"],
            A_плюс_бока_несимметричным_макс=walls_new + backs + 2 * (bucket["нет"] + bucket["не_ясно"] +
                                                                     bucket["составной_целиком"]),
            B=walls_new + near + 3 * backs + 3 * high)     # высокий пол - три вида, как в первом подсчёте
        comp_obj = defaultdict(set)
        for g in groups:
            comp_obj[g["sure"]] |= {e for e in g["pics"] if d["need"].get(e, ("",))[0] == "объект"}
        stats = dict(
            картинок=len(d["need"]), по_виду=kinds,
            стены=dict(спорных=len(walls), без_пары=sum(1 for x in walls if x["kind"] == "стена_без_пары"),
                       декор=sum(1 for x in walls if x["kind"] == "стена_декор"),
                       с_кандидатом_IoU05=sum(1 for x in walls if x["cand"] is not None and x["cand_iou"] >= 0.5),
                       отмечено=len(wm), одинаковы=wcnt["S"], пара_верна=wcnt["P"], новая=wcnt["N"]),
            составные=dict(групп=len(groups),
                           надёжно=sum(1 for g in groups if g["sure"] == "надёжно"),
                           один_раз=sum(1 for g in groups if g["sure"] != "надёжно"),
                           записей=sum(len(g["mem"]) for g in groups),
                           картинок=len(set().union(*[g["pics"] for g in groups])) if groups else 0,
                           картинок_надёжно=len(set().union(*[g["pics"] for g in groups
                                                             if g["sure"] == "надёжно"])) if groups else 0,
                           по_виду=dict(Counter(g["kind"] for g in groups)),
                           по_повороту=dict(Counter(g["fix"] for g in groups)),
                           картинок_по_повороту={f_: len(set().union(*[g["pics"] for g in groups if g["fix"] == f_]))
                                                 for f_ in {g["fix"] for g in groups}},
                           из_прочих_предметов=len(comp_obj["надёжно"] | comp_obj["один_раз"]),
                           из_прочих_надёжно=len(comp_obj["надёжно"])),
            симметрия=dict(всего=len(syms), авто=dict(Counter(x["mark"] for x in syms)), итог=dict(scnt),
                           отмечено=len(om), только_die=sum(1 for x in syms if x["debris"])),
            прочие_предметы_по_корзинам=dict(bucket),
            рисовать=plan)
        summary[game] = stats
        print(json.dumps(stats, ensure_ascii=False, indent=1), flush=True)
    if set(summary) != set(GAMES):
        print("таблицы census/rotation общие для обеих игр - при --games %s не перезаписаны" % args.games)
        return
    write_tsv(os.path.join(CENSUS, "wall_backface.tsv"), WALL_HEAD, wall_rows_all)
    write_tsv(os.path.join(CENSUS, "composite.tsv"), COMP_HEAD, comp_rows_all)
    write_tsv(os.path.join(CENSUS, "object_symmetry.tsv"), SYM_HEAD, sym_rows_all)
    with open(os.path.join(CENSUS, "step2_counts.json"), "w", encoding=ENC) as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
