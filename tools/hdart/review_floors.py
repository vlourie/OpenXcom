# -*- coding: utf-8 -*-
r"""Приёмка полов глазами: слева оригинал, справа HD - и вердикт по каждому полу.

    tools\hdart\.venv\Scripts\python.exe tools\hdart\review_floors.py --mod "Пиратки\Dioxine_XPiratez\user\mods\hd" --sheets art/TERRAIN
    (открыть review\index.html, разметить, нажать «скачать вердикты»)
    tools\hdart\.venv\Scripts\python.exe tools\hdart\review_floors.py --report review\verdicts.csv

Для каждого пола рисуется пара: одно и то же поле клеток, слева выложенное ОРИГИНАЛЬНЫМ кадром
(увеличенным без сглаживания - как игра показывала бы его без пака), справа - кадром из пака.
Поле, а не одиночный тайл: половина брака видна только в укладке (швы, решётка, повтор детали).

`--mode variants` вместо этого сравнивает пак с вариантами и без них (нужны `<i>.v1.png` в паке) -
тем же способом проверяется, помогли ли варианты.

Страница `review\index.html` открывается прямо с диска: стрелки листают, 1 - оставить,
2 - забраковать, 3 - сомнительно, 0 - снять отметку. Вердикты кладутся в `verdicts.csv`
(кнопкой «скачать»), его же можно загрузить обратно и продолжить с того места.

`--report verdicts.csv` печатает итог и пишет рядом `verdicts_bad_sets.txt` - список наборов
через запятую, готовый для `--sets` перекраски.

`--from-game` - приёмка по УСТАНОВЛЕННОЙ игре, без нашего дерева `art/`: оригиналы читаются прямо
из PCK/TAB/MCD данных мода, а HD-кадры - из пака, который читает игра (папка мода или его zip).
Это тот же путь, которым потом пойдёт проверялка в лаунчере у игроков (docs/portal/PACK_REVIEW.md),
и по нему же судим мы сами: судить надо по конечному файлу, а не по листу из середины конвейера
(грабли R-019).

    tools\hdart\.venv\Scripts\python.exe tools\hdart\review_floors.py --from-game ^
        --sets CAVEBROWN,CAVEAQUA --mod "Пиратки\Dioxine_XPiratez\user\mods\hd"

Кадры идут все, а не только полы: полы показываются полем клеток, остальное - кадром на тёмном
полу боя (грабли R-041). Кадры, на которые не ссылается ни одна запись MCD, пропускаются: игра
их не рисует (грабли R-052). Вердикты выгружаются в `verdicts.json` - в том виде, в каком их
будет слать лаунчер.
"""
import argparse
import hashlib
import io
import json
import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
TOOLS = os.path.dirname(HERE)
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import numpy as np                   # noqa: E402
from PIL import Image, ImageDraw, ImageFont     # noqa: E402
import xcom_sprites as xs            # noqa: E402
import build_pack                    # noqa: E402
import extract_pck                   # noqa: E402
import gen_hd                        # noqa: E402
import subjects_terrain              # noqa: E402
import pck_census                    # noqa: E402

ENC = "utf-8-sig"
FLOOR = (38, 34, 30)                 # тёмный пол боя: на нём виден остаток подложки (грабли R-041)
PZ = os.path.join("Пиратки", "Dioxine_XPiratez", "user", "mods")

# Причина брака задаёт, каким скриптом чинить, поэтому список закрытый: по свободному тексту
# статистику на двадцати тысячах кадров не построишь (docs/portal/PACK_REVIEW.md §3).
REASONS = [
    ("color", u"цвет уехал", "q"),
    ("shape", u"силуэт не тот", "w"),
    ("panel", u"фон-подложка", "e"),
    ("seams", u"швы и решётка", "r"),
    ("invented", u"содержание выдумано", "t"),
    ("blurry", u"слишком мутно", "y"),
]


def subject_of(set_name):
    if set_name in gen_hd.SUBJECTS:
        return gen_hd.SUBJECTS[set_name], "SUBJECTS"
    subject, src = subjects_terrain.subject_for_set(set_name)
    if subject:
        return subject, "террейн %s" % src
    subject, src = subjects_terrain.subject_by_name(set_name)
    if subject:
        return subject, "имя (%s)" % src
    return "", "ЗАГЛУШКА"


def font(size=13):
    """Шрифт с кириллицей: встроенный в Pillow её не умеет и рисует подписи квадратами."""
    for p in (r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\arial.ttf"):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


def panels_image(panels, caption):
    """Несколько полей в ряд, у каждого своя подпись, общая подпись сверху."""
    gap, top = 12, 20
    head = font(14)
    w = sum(p[0].width for p in panels) + gap * (len(panels) - 1)
    h = max(p[0].height for p in panels)
    # у одиночных кадров колонка уже подписи, и подпись обрезалась на полуслове
    w = max(w, int(head.getlength(caption)) + 8)
    im = Image.new("RGB", (w, top + h), (28, 28, 30))
    d = ImageDraw.Draw(im)
    d.text((4, 3), caption, fill=(255, 232, 120), font=head)
    x = 0
    for img, text in panels:
        im.paste(img, (x, top))
        d.text((x + 6, top + 2), text, fill=(190, 190, 190), font=font(13))
        x += img.width + gap
    return im


def fit_panel(im, args):
    """Подогнать колонку под ширину страницы или показать её крупнее ключом --zoom."""
    if args.zoom and args.zoom != 1.0:
        return im.resize((max(1, int(im.width * args.zoom)), max(1, int(im.height * args.zoom))),
                         Image.NEAREST if args.zoom > 1 else Image.LANCZOS)
    if args.width <= 0 or im.width <= args.width:
        return im
    return im.resize((args.width, max(1, im.height * args.width // im.width)), Image.LANCZOS)


def on_floor(im, pad=10):
    """Кадр на тёмном полу боя. На шахматке остаток подложки не читается вовсе (грабли R-041)."""
    bg = Image.new("RGB", (im.width + 2 * pad, im.height + 2 * pad), FLOOR)
    bg.paste(im, (pad, pad), im)
    return bg


class Pack:
    """Кадры HD-пака ровно там, где их берёт игра: <мод>/hd/<раздел>/<НАБОР>/<N>.png.

    Мод может быть папкой или zip - игроку пак приезжает и так, и так, а судить надо по тому
    файлу, который читает игра (грабли R-019).
    """

    def __init__(self, mod, pack_path, set_name):
        self.set_name = set_name
        rel = "/".join(x for x in ("hd", pack_path, set_name) if x)
        self.where = "%s!%s" % (mod, rel) if mod.lower().endswith(".zip") else os.path.join(mod, *rel.split("/"))
        self.zip, self.names, self.dir = None, {}, ""
        if mod.lower().endswith(".zip"):
            self.zip = zipfile.ZipFile(mod)
            tail = rel.lower() + "/"
            for n in self.zip.namelist():
                low = n.replace("\\", "/").lower()
                if low.endswith("/") or not (low == tail or low.startswith(tail) or ("/" + tail) in low):
                    continue
                self.names[low.rsplit("/", 1)[1]] = n
        else:
            self.dir = self.where

    def data(self, file_name):
        if self.zip is not None:
            n = self.names.get(file_name.lower())
            return self.zip.read(n) if n else None
        p = os.path.join(self.dir, file_name)
        if not os.path.exists(p):
            return None
        with open(p, "rb") as f:
            return f.read()

    def frame(self, i):
        """(кадр RGBA, sha256 файла) - подпись та же, что в манифесте релиза: это ключ версии."""
        raw = self.data("%d.png" % i)
        if raw is None:
            return None, ""
        im = Image.open(io.BytesIO(raw)).convert("RGBA")
        return im, hashlib.sha256(raw).hexdigest()

    def variants(self, i):
        """Варианты кадра <N>.v1.png, <N>.v2.png... - игра раскладывает их узором."""
        out, n = [], 1
        while True:
            raw = self.data("%d.v%d.png" % (i, n))
            if raw is None:
                return out
            out.append(Image.open(io.BytesIO(raw)).convert("RGBA"))
            n += 1


def mod_version(mod):
    """Строка версии мода из его metadata.yml: попадает в вердикт, чтобы было видно, что судили."""
    raw = None
    if mod.lower().endswith(".zip"):
        with zipfile.ZipFile(mod) as z:
            for n in z.namelist():
                if n.replace("\\", "/").lower().endswith("metadata.yml"):
                    raw = z.read(n)
                    break
    else:
        p = os.path.join(mod, "metadata.yml")
        if os.path.exists(p):
            with open(p, "rb") as f:
                raw = f.read()
    if raw is None:
        return ""
    text = raw.decode("utf-8-sig", "replace")
    got = {}
    for line in text.splitlines():
        k, _, v = line.partition(":")
        if k.strip() in ("id", "version"):
            got[k.strip()] = v.strip().strip('"')
    return " ".join(x for x in (got.get("id", ""), got.get("version", "")) if x)


def game_set(data, section, set_name):
    """Набор как его читает игра: кадры из PCK/TAB и разметка по MCD. None - набора нет."""
    folder = os.path.join(data, section)
    pck = extract_pck.find_ci(folder, set_name)
    if not pck:
        return None
    stem = os.path.splitext(os.path.basename(pck))[0]
    tab = extract_pck.find_ci(folder, stem + ".TAB")
    fw, fh = xs.frame_size_for(os.path.basename(pck))
    frames = xs.read_pck(pck, tab or None, fw, fh)
    types, walkable, raised = [-1] * len(frames), [True] * len(frames), [False] * len(frames)
    mcd = extract_pck.find_ci(folder, stem + ".MCD")
    if mcd:
        types, walkable, raised = xs.frame_types(xs.read_mcd(mcd), len(frames))
    ground, _ = extract_pck.ground_flags(frames, types, walkable, raised, fw, fh)
    return {"frames": frames, "types": types, "ground": ground, "fw": fw, "fh": fh, "mcd": bool(mcd)}


def game_names(args):
    """Какие наборы проверять: названные ключом --sets или все, на которые в моде есть пак."""
    only = {s.strip().upper() for s in args.sets.split(",") if s.strip()}
    have = []
    if args.mod.lower().endswith(".zip"):
        with zipfile.ZipFile(args.mod) as z:
            head = "/".join(x for x in ("hd", args.pack_path) if x).lower() + "/"
            for n in z.namelist():
                low = n.replace("\\", "/").lower()
                pos = low.find(head)
                if pos < 0:
                    continue
                rest = low[pos + len(head):].split("/")
                if len(rest) > 1 and rest[0].endswith(".pck"):
                    have.append(rest[0].upper())
    else:
        root = os.path.join(args.mod, "hd", args.pack_path) if args.pack_path else os.path.join(args.mod, "hd")
        if os.path.isdir(root):
            have = [d.upper() for d in os.listdir(root)
                    if d.upper().endswith(".PCK") and os.path.isdir(os.path.join(root, d))]
    have = sorted(set(have))
    if only:
        have = [n for n in have if n in only or n[:-4] in only]
        missing = only - {n for n in have} - {n[:-4] for n in have}
        for m in sorted(missing):
            print("в моде нет пака: %s" % m)
    return have


def build_pairs_game(args):
    """Пары «оригинал - пак» по установленной игре: ни листов из art/, ни layout.json."""
    if args.palette:
        palette = xs.load_palette_file(args.palette)
    else:
        # у модов вроде X-Piratez своей PALETTES.DAT нет: боевая палитра подменяется customPalettes
        pal = extract_pck.find_ci(os.path.join(args.data, "GEODATA"), "PALETTES.DAT")
        if not pal:
            raise SystemExit(u"нет %s\\GEODATA\\PALETTES.DAT - укажи палитру мода ключом --palette"
                             % args.data)
        palette = xs.load_palette(pal)
    pairs_dir = os.path.join(args.out, "pairs")
    os.makedirs(pairs_dir, exist_ok=True)
    items, skipped, orphans = [], [], 0
    for set_name in game_names(args):
        g = game_set(args.data, args.section, set_name)
        if g is None:
            skipped.append("%s: набора нет в данных игры (%s)" % (set_name, args.section))
            continue
        pack = Pack(args.mod, args.pack_path, set_name)
        stem = set_name[:-4] if set_name.upper().endswith(".PCK") else set_name
        # тему набора знают только террейны: она берётся из рулсетов по террейну (грабли R-013)
        src = subject_of(set_name)[1] if args.section.upper() == "TERRAIN" else ""
        for i, frame in enumerate(g["frames"]):
            if frame is None or not any(any(row) for row in frame):
                continue
            if g["mcd"] and g["types"][i] < 0:
                orphans += 1                      # на кадр не ссылается ни одна запись MCD: игра его не рисует
                continue
            hd, sha = pack.frame(i)
            if hd is None:
                skipped.append("%s #%d: нет кадра в паке" % (stem, i))
                continue
            orig = xs.frame_to_image(frame, palette)
            k = max(1, hd.width // g["fw"])
            big = orig.resize((g["fw"] * k, g["fh"] * k), Image.NEAREST)
            if hd.size != big.size:
                hd = hd.resize(big.size, Image.LANCZOS)
            mask = big.split()[3].point(lambda v: 255 if v > 128 else 0)
            err = build_pack.chroma_error(hd, big, mask)
            if g["ground"][i]:
                kind = u"пол"
                left = build_pack.ground_field([big], args.cells, k).convert("RGB")
                right = build_pack.ground_field([hd] + pack.variants(i), args.cells, k).convert("RGB")
            else:
                kind = {xs.MCD_WEST_WALL: u"стена", xs.MCD_NORTH_WALL: u"стена",
                        xs.MCD_FLOOR: u"пол"}.get(g["types"][i], u"объект")
                left, right = on_floor(big), on_floor(hd)
            panels = [(fit_panel(left, args), u"оригинал (игра без пака)"), (fit_panel(right, args), u"HD-пак")]
            note = u"%s · %s" % (kind, src) if src else kind
            pair = panels_image(panels, "%s  #%d   dE %.1f   %s" % (stem, i, err, note))
            fn = "%s_%d.png" % (stem, i)
            pair.save(os.path.join(pairs_dir, fn))
            items.append({"set": set_name, "stem": stem, "frame": i, "err": round(err, 1),
                          "src": note, "file": "pairs/" + fn,
                          "orig": pck_census.fingerprints(frame)["exact"], "hd": sha})
            if args.max and len(items) >= args.max:
                break
        if args.max and len(items) >= args.max:
            break
    if orphans:
        print(u"кадров-сирот пропущено: %d (на них не ссылается ни одна запись MCD)" % orphans)
    items.sort(key=lambda r: -r["err"])
    return items, skipped


def build_pairs(args):
    pairs_dir = os.path.join(args.out, "pairs")
    os.makedirs(pairs_dir, exist_ok=True)
    only = {s.strip().upper() for s in args.sets.split(",") if s.strip()}
    names = sorted(n for n in os.listdir(args.sheets)
                   if n.upper().endswith(".PCK") and os.path.isdir(os.path.join(args.sheets, n)))
    if only:
        names = [n for n in names if n.upper() in only or n.upper()[:-4] in only]

    items, skipped = [], []
    for name in names:
        set_dir = os.path.join(args.sheets, name)
        layout = os.path.join(set_dir, "layout.json")
        pack_dir = os.path.join(args.mod, "hd", args.pack_path, name) if args.pack_path \
            else os.path.join(args.mod, "hd", name)
        if not os.path.exists(layout) or not os.path.isdir(pack_dir):
            continue
        with open(layout, encoding=ENC) as f:
            info = json.load(f)
        info.setdefault("set", name)
        count, fw, fh = info["count"], info["frame_w"], info["frame_h"]
        types = info.get("types") or [-1] * count
        ground = info.get("ground") or [False] * count
        sheet = xs.Sheet(fw, fh, count, info["columns"], info["margin"])
        original = Image.open(os.path.join(set_dir, "original.png")).convert("RGBA")
        subject, src = subject_of(info["set"])

        floors = []
        for i in range(count):
            if types[i] != xs.MCD_FLOOR or not ground[i]:
                continue
            frame = sheet.cut(original, i, 1)
            box = frame.getbbox()
            if box is None or box[1] < fh - 16 - 6:
                continue
            area = float(np.asarray(frame.split()[3], np.float64).sum()) / 255.0
            floors.append((area, i, frame))
        floors.sort(key=lambda t: -t[0])

        for _, i, orig in floors[:max(1, args.per_set)]:
            png = os.path.join(pack_dir, "%d.png" % i)
            if not os.path.exists(png):
                skipped.append("%s #%d: нет кадра в паке" % (name, i))
                continue
            hd = Image.open(png).convert("RGBA")
            k = max(1, hd.width // fw)
            big = orig.resize((fw * k, fh * k), Image.NEAREST)
            if hd.size != big.size:
                hd = hd.resize(big.size, Image.LANCZOS)
            mask = big.split()[3].point(lambda v: 255 if v > 128 else 0)
            err = build_pack.chroma_error(hd, big, mask)

            def field_of(frames):
                return build_pack.ground_field(frames, args.cells, k).convert("RGB")

            def pack_b_frame():
                other = os.path.join(args.mod_b, "hd", args.pack_path, name) if args.pack_path \
                    else os.path.join(args.mod_b, "hd", name)
                png_b = os.path.join(other, "%d.png" % i)
                if not os.path.exists(png_b):
                    return None
                im = Image.open(png_b).convert("RGBA")
                return im.resize(hd.size, Image.LANCZOS) if im.size != hd.size else im

            if args.mode in ("packs", "three"):
                hd_b = pack_b_frame()
                if hd_b is None:
                    skipped.append("%s #%d: нет кадра во втором паке" % (name, i))
                    continue
                panels = [(field_of([hd_b]), "old pack"), (field_of([hd]), "new pack")]
                if args.mode == "three":
                    panels.insert(0, (field_of([big]), "original"))
            elif args.mode == "variants":
                variants = []
                n = 1
                while os.path.exists(os.path.join(pack_dir, "%d.v%d.png" % (i, n))):
                    variants.append(Image.open(os.path.join(pack_dir, "%d.v%d.png" % (i, n))).convert("RGBA"))
                    n += 1
                if not variants:
                    skipped.append("%s #%d: вариантов нет" % (name, i))
                    continue
                panels = [(field_of([hd]), "no variants"),
                          (field_of([hd] + variants), "with variants (%d)" % len(variants))]
            else:
                panels = [(field_of([big]), "original (game without the pack)"), (field_of([hd]), "HD pack")]

            panels = [(fit_panel(im, args), text) for im, text in panels]

            stem = (name[:-4] if name.upper().endswith(".PCK") else name)
            tag = "SUBJ" if src.startswith("SUBJECTS") else ("TERR" if src.startswith("террейн")
                                                             else ("NAME" if src.startswith("имя") else "NONE"))
            caption = "%s  #%d   dE %.1f   theme: %s" % (stem, i, err, tag)
            pair = panels_image(panels, caption)
            fn = "%s_%d.png" % (stem, i)
            pair.save(os.path.join(pairs_dir, fn))
            with open(png, "rb") as f:
                sha = hashlib.sha256(f.read()).hexdigest()
            items.append({"set": name, "stem": stem, "frame": i, "err": round(err, 1),
                          "src": u"тема: " + src, "file": "pairs/" + fn, "orig": "", "hd": sha})
        if args.max and len(items) >= args.max:
            break

    items.sort(key=lambda r: -r["err"])
    return items, skipped


PAGE = u"""<!doctype html>
<meta charset="utf-8">
<title>Приёмка полов</title>
<style>
 body{margin:0;background:#1c1c1e;color:#ddd;font:14px/1.4 system-ui,Segoe UI,sans-serif}
 header{position:sticky;top:0;background:#141416;padding:8px 12px;display:flex;gap:12px;align-items:center;
        border-bottom:1px solid #333;flex-wrap:wrap}
 button{background:#2c2c30;color:#eee;border:1px solid #444;border-radius:6px;padding:6px 10px;cursor:pointer}
 button:hover{background:#3a3a40}
 .ok{border-color:#3c8c4a} .bad{border-color:#a04040} .maybe{border-color:#9a8030}
 #wrap{display:flex;gap:12px;padding:12px;align-items:flex-start}
 #list{width:250px;max-height:82vh;overflow:auto;border:1px solid #333;border-radius:6px}
 #list div{padding:4px 8px;cursor:pointer;border-bottom:1px solid #262628;white-space:nowrap;overflow:hidden}
 #list div.cur{background:#2e2e34}
 #view{flex:1}
 #view img{max-width:100%;image-rendering:auto;border:1px solid #333;border-radius:6px}
 #view.zoom img{max-width:none;image-rendering:pixelated}
 #view.zoom{overflow:auto;max-height:82vh}
 .tag{font-weight:600} .t1{color:#6fcf7f} .t2{color:#e06b6b} .t3{color:#d8bd5a}
 #meta{margin:6px 0 6px}
 #why{margin:0 0 10px;display:flex;gap:8px;flex-wrap:wrap}
 #why span{border:1px solid #444;border-radius:6px;padding:3px 8px;cursor:pointer;color:#aaa}
 #why span.on{border-color:#a04040;color:#e9c0c0;background:#3a2a2a}
 #why.off{opacity:.35;pointer-events:none}
 small{color:#999}
</style>
<header>
  <b id="title">Приёмка</b>
  <span id="pos"></span>
  <button onclick="mark(1)" class="ok">1 — оставить</button>
  <button onclick="mark(2)" class="bad">2 — забраковать</button>
  <button onclick="mark(3)" class="maybe">3 — сомнительно</button>
  <button onclick="mark(0)">0 — снять</button>
  <button onclick="zoom()">Z — крупнее</button>
  <button onclick="saveJson()">передать (скачать json)</button>
  <button onclick="save()">csv</button>
  <label style="cursor:pointer">загрузить<input type="file" onchange="load(this)" style="display:none"></label>
  <span id="stat"></span>
  <small>стрелки — листать, F — только неразмеченные</small>
</header>
<div id="wrap">
  <div id="list"></div>
  <div id="view">
    <div id="meta"></div>
    <div id="why"></div>
    <img id="img">
  </div>
</div>
<script>
const items = /*ITEMS*/, meta = /*META*/, reasons = /*REASONS*/;
let verdict = {}, cur = 0, onlyNew = false;
const key = it => it.set + "#" + it.frame;
const vOf = k => (verdict[k] || {}).v || 0;
// прежние разметки хранили одно число: поднимаем их до {вердикт, причины}
function normalise(o){ const out = {}; for(const k in o) out[k] = typeof o[k] == "number" ? {v:o[k], r:[]} : o[k]; return out; }
try { const s = localStorage.getItem(meta.store); if (s) verdict = normalise(JSON.parse(s)); } catch (e) {}
function keep(){ try { localStorage.setItem(meta.store, JSON.stringify(verdict)); } catch (e) {} }
function tag(v){ return v==1?"<span class='tag t1'>оставить</span>":v==2?"<span class='tag t2'>брак</span>":v==3?"<span class='tag t3'>сомнительно</span>":""; }
function draw(){
  const it = items[cur]; if(!it) return;
  document.getElementById("title").textContent = meta.title;
  document.getElementById("pos").textContent = (cur+1) + " / " + items.length;
  document.getElementById("img").src = it.file;
  const rec = verdict[key(it)] || {v:0, r:[]};
  document.getElementById("meta").innerHTML = "<b>" + it.stem + "</b> #" + it.frame +
    " &nbsp; отличие по цвету " + it.err + " &nbsp; " + it.src + " &nbsp; " + tag(rec.v);
  const why = document.getElementById("why");
  why.className = rec.v == 2 ? "" : "off";
  why.innerHTML = reasons.map(r => "<span class='" + ((rec.r||[]).includes(r[0])?"on":"") +
      "' onclick='reason(\\"" + r[0] + "\\")'>" + r[2].toUpperCase() + " — " + r[1] + "</span>").join("");
  const l = document.getElementById("list");
  l.innerHTML = items.map((x,n)=>"<div class='"+(n==cur?"cur":"")+"' onclick='go("+n+")'>"+
      (vOf(key(x))==1?"✓ ":vOf(key(x))==2?"✗ ":vOf(key(x))==3?"? ":"· ")+x.stem+" #"+x.frame+"</div>").join("");
  const c = l.querySelector(".cur"); if(c) c.scrollIntoView({block:"nearest"});
  const vs = Object.values(verdict).map(x=>x.v);
  document.getElementById("stat").textContent = "оставить " + vs.filter(v=>v==1).length +
      " · брак " + vs.filter(v=>v==2).length + " · сомнительно " + vs.filter(v=>v==3).length;
}
function go(n){ cur = Math.max(0, Math.min(items.length-1, n)); draw(); }
function zoom(){ document.getElementById("view").classList.toggle("zoom"); }
function step(d){
  let n = cur;
  for(let i=0;i<items.length;i++){ n = (n + d + items.length) % items.length; if(!onlyNew || !vOf(key(items[n]))) break; }
  go(n);
}
function mark(v){
  const it = items[cur]; if(!it) return;
  if(v===0) delete verdict[key(it)]; else verdict[key(it)] = {v:v, r:(verdict[key(it)]||{}).r || []};
  keep();
  // брак оставляем на экране: сейчас будут отмечать причину
  if(v===1 || v===3) step(1); else draw();
}
function reason(code){
  const it = items[cur]; if(!it) return;
  const rec = verdict[key(it)] || (verdict[key(it)] = {v:2, r:[]});
  rec.v = 2;
  rec.r = rec.r || [];
  const at = rec.r.indexOf(code);
  if(at < 0) rec.r.push(code); else rec.r.splice(at, 1);
  keep(); draw();
}
function download(name, text, type){
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], {type:type}));
  a.download = name; a.click();
}
function save(){
  let out = "set,frame,verdict\\n";
  for(const it of items){ const v = vOf(key(it)); if(v) out += it.set + "," + it.frame + "," + (v==1?"ok":v==2?"bad":"maybe") + "\\n"; }
  download("verdicts.csv", out, "text/csv");
}
// тот же вид, в котором вердикты уходят на портал: один блок на пак
function saveJson(){
  const packs = {};
  for(const it of items){
    const rec = verdict[key(it)]; if(!rec || !rec.v) continue;
    const p = packs[it.set] || (packs[it.set] = {section: meta.section, set: it.set,
        modVersion: meta.modVersion, frames: []});
    p.frames.push({frame: it.frame, orig: it.orig, hd: it.hd,
        verdict: rec.v==1?"ok":rec.v==2?"bad":"doubt", reasons: rec.v==2 ? (rec.r||[]) : []});
  }
  const list = Object.values(packs);
  if(!list.length){ alert("нечего передавать: ни одного вердикта"); return; }
  download("verdicts.json", JSON.stringify({tool: meta.tool, checkedAt: new Date().toISOString(),
      packs: list}, null, 1), "application/json");
}
function load(inp){
  const f = inp.files[0]; if(!f) return;
  const r = new FileReader();
  r.onload = () => {
    verdict = {};
    const text = r.result.trim();
    if(text.startsWith("{")){
      for(const p of (JSON.parse(text).packs || []))
        for(const fr of (p.frames || []))
          verdict[p.set + "#" + fr.frame] = {v: fr.verdict=="ok"?1:fr.verdict=="bad"?2:3, r: fr.reasons || []};
    } else {
      for(const line of text.split(/\\r?\\n/).slice(1)){
        const p = line.split(","); if(p.length < 3) continue;
        verdict[p[0] + "#" + p[1]] = {v: p[2].trim()=="ok"?1:p[2].trim()=="bad"?2:3, r: []};
      }
    }
    keep(); draw();
  };
  r.readAsText(f);
}
document.onkeydown = e => {
  const r = reasons.find(x => x[2] == e.key.toLowerCase());
  if(e.key=="ArrowRight"||e.key==" ") { step(1); e.preventDefault(); }
  else if(e.key=="ArrowLeft") step(-1);
  else if("0123".includes(e.key)) mark(+e.key);
  else if(r) reason(r[0]);
  else if(e.key.toLowerCase()=="z") zoom();
  else if(e.key.toLowerCase()=="f") { onlyNew = !onlyNew; document.getElementById("stat").textContent += onlyNew?" · только неразмеченные":""; }
};
draw();
</script>
"""


def read_verdicts(path):
    """Вердикты из verdicts.json (как их шлёт лаунчер) или из старого verdicts.csv."""
    rows = []
    with open(path, encoding=ENC, newline="") as f:
        text = f.read()
    if text.lstrip().startswith("{"):
        for pack in json.loads(text).get("packs", []):
            for fr in pack.get("frames", []):
                rows.append((pack["set"], int(fr["frame"]), fr.get("verdict", ""), fr.get("reasons") or []))
        return rows
    import csv
    for row in csv.DictReader(io.StringIO(text)):
        v = (row.get("verdict") or "").strip()
        rows.append((row["set"], int(row["frame"]), "doubt" if v == "maybe" else v, []))
    return rows


def report(path):
    """Итог по вердиктам: сколько чего, из-за чего брак и список наборов для перекраски."""
    bad, ok, maybe = [], [], []
    why = {}
    for set_name, frame, v, reasons in read_verdicts(path):
        item = (set_name, frame)
        (bad if v == "bad" else ok if v == "ok" else maybe).append(item)
        if v == "bad":
            for r in reasons:
                why[r] = why.get(r, 0) + 1
    print("оставить: %d, брак: %d, сомнительно: %d" % (len(ok), len(bad), len(maybe)))
    if why:
        names = dict((code, text) for code, text, _ in REASONS)
        print("причины брака: " + ", ".join("%s %d" % (names.get(c, c), n)
                                            for c, n in sorted(why.items(), key=lambda kv: -kv[1])))
    sets = sorted({s for s, _ in bad})
    out = os.path.join(os.path.dirname(os.path.abspath(path)), "verdicts_bad_sets.txt")
    line = ",".join(s[:-4] if s.upper().endswith(".PCK") else s for s in sets)
    with open(out, "w", encoding=ENC) as f:
        f.write(line + "\n")
    print("наборов с браком: %d -> %s" % (len(sets), out))
    if bad:
        print("кадры: " + "; ".join("%s #%d" % (s, i) for s, i in bad[:40]) + ("..." if len(bad) > 40 else ""))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="пары «оригинал - HD» полем и страница приёмки")
    ap.add_argument("--report", default="", help="посчитать итог по готовому verdicts.json или .csv и выйти")
    ap.add_argument("--mod", default="", help="мод с паками: папка или zip")
    ap.add_argument("--sheets", default="art/TERRAIN")
    ap.add_argument("--out", default="art/_review/review")
    ap.add_argument("--pack-path", default=None, dest="pack_path",
                    help="папка паков внутри hd/ (по умолчанию TERRAIN; для UNITS - пустая строка)")
    ap.add_argument("--from-game", action="store_true", dest="from_game",
                    help="читать оригиналы прямо из данных игры, без листов из art/: так же будет "
                         "работать проверялка в лаунчере")
    ap.add_argument("--data", default=os.path.join(PZ, "Piratez"),
                    help="--from-game: папка мода-источника с TERRAIN/*.PCK")
    ap.add_argument("--palette", default=os.path.join(PZ, "Piratez", "Resources", "Pals", "delicious_regular.pal"),
                    help="--from-game: палитра мода (пусто - GEODATA/PALETTES.DAT данных)")
    ap.add_argument("--section", default="TERRAIN", help="--from-game: раздел данных игры")
    ap.add_argument("--sets", default="", help="только эти наборы, через запятую")
    ap.add_argument("--per-set", type=int, default=1, dest="per_set")
    ap.add_argument("--cells", type=int, default=4)
    ap.add_argument("--width", type=int, default=420, help="ширина каждой колонки (0 - как есть)")
    ap.add_argument("--zoom", type=float, default=0.0,
                    help="во сколько раз показать поле вместо подгонки по ширине: 1 - как есть "
                         "(пиксель в пиксель), 2 - вдвое крупнее. Отменяет --width")
    ap.add_argument("--max", type=int, default=0, help="хватит после стольких полов (проба)")
    ap.add_argument("--mode", choices=["orig", "variants", "packs", "three"], default="orig",
                    help="orig: оригинал против HD; variants: пак без вариантов против пака с ними; "
                         "packs: старый пак (--mod-b) против нового (--mod); "
                         "three: три колонки - оригинал, старый пак, новый")
    ap.add_argument("--mod-b", default="", dest="mod_b", help="второй мод для --mode packs (старый пак)")
    args = ap.parse_args(argv)

    if args.report:
        return report(args.report)
    if not args.mod:
        ap.error("нужен --mod (или --report)")
    if args.mode in ("packs", "three") and not args.mod_b:
        ap.error("--mode %s: нужен --mod-b со старым паком" % args.mode)
    if args.pack_path is None:
        # у UNITS паки лежат прямо в hd/<НАБОР>.PCK, у террейна - в hd/TERRAIN/<НАБОР>.PCK
        args.pack_path = "TERRAIN" if not args.from_game or args.section.upper() == "TERRAIN" else ""
    if args.from_game and not args.sets and not args.max:
        ap.error("--from-game без --sets соберёт все паки мода (это десятки тысяч кадров). "
                 "Назови наборы через --sets или ограничь пробу ключом --max")

    os.makedirs(args.out, exist_ok=True)
    if args.from_game:
        print("оригиналы: %s\\%s   пак: %s   палитра: %s"
              % (args.data, args.section, args.mod, args.palette or "PALETTES.DAT данных"))
        items, skipped = build_pairs_game(args)
        meta = {"title": u"Приёмка пака", "store": "packVerdicts", "section": args.section,
                "modVersion": mod_version(args.mod), "tool": "review_floors.py --from-game"}
    else:
        items, skipped = build_pairs(args)
        meta = {"title": u"Приёмка полов", "store": "floorVerdicts", "section": args.pack_path,
                "modVersion": mod_version(args.mod), "tool": "review_floors.py"}
    # метки-комментарии, а не голые слова: в json наборов попадаются и METAL, и другие совпадения
    page = (PAGE.replace("/*ITEMS*/", json.dumps(items, ensure_ascii=False))
                .replace("/*META*/", json.dumps(meta, ensure_ascii=False))
                .replace("/*REASONS*/", json.dumps(REASONS, ensure_ascii=False)))
    with open(os.path.join(args.out, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)
    with open(os.path.join(args.out, "pairs.json"), "w", encoding=ENC) as f:
        json.dump(items, f, ensure_ascii=False, indent=1)
    print("пар собрано: %d (наборов %d)" % (len(items), len({i["set"] for i in items})))
    if skipped:
        print("пропущено: %d (%s%s)" % (len(skipped), "; ".join(skipped[:5]), "..." if len(skipped) > 5 else ""))
    print("открой: %s" % os.path.join(os.path.abspath(args.out), "index.html"))
    print("разметил - «передать (скачать json)», потом: review_floors.py --report %s"
          % os.path.join(args.out, "verdicts.json"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
