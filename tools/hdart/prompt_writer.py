#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prompt_writer.py - промпт на КАЖДЫЙ кадр из фактов, а не «terrain tile».

Зачем. Разбор LoRA-батча (docs/research/gen3-audit.md) показал: у 85 процентов кадров
подсказки нет вовсе, у предметов - у 71 из 20 313. Модель получала «X-COM isometric object
tile, terrain tile» и рисовала то, чему её научили на пустыне и болоте: бурый камень. Белая
стена корабля C_INT 68 вышла каменной кладкой с выбитой надписью XCOM.

Промпт здесь собирается из того, что можно ПРОВЕРИТЬ, в таком порядке доверия:

  1. данные игры: тип части клетки по MCD (пол, западная/северная стена, объект, сплошной
     блок, дверь, обломки) - triage/build.py читает те же поля;
  2. пиксели кадра: основные цвета с долями, насыщенность, ровный или фактурный, упирается ли
     рисунок в край кадра (кусок большего объекта);
  3. тема террейна из рулсетов (subjects_terrain.subject_for_set, R-013) с правилом « | »
     (R-016): полам и стенам - левая часть, предметам - вся;
  4. описание моделью со зрением (Ollama) - ТОЛЬКО после проверки против 1-2: цветовые слова,
     которых нет в пикселях, выбрасываются; слова «pixel», «pixelated», «8-bit» и подобные
     тоже (иначе модель рисует ступеньки как содержание, R-004).

Материал в негатив: если кадр серый или белый - «rust, brown stone, wood grain», если это снег -
«sand». Ровно тот перекос, который показал разбор.

    py -3 tools/hdart/prompt_writer.py --sets C_INT,MARSEC_EXT_2 --show 10
    py -3 tools/hdart/prompt_writer.py --sets C_INT --vlm        описание моделью (Ollama)

Пишет art/gen3/prompts.tsv (дописывает и заменяет строки своих наборов) и кэш описаний
art/gen3/captions.json по хэшу картинки: одна картинка - одно описание на все паки.
"""
import argparse
import base64
import colorsys
import csv
import hashlib
import io
import json
import os
import re
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import numpy as np                                      # noqa: E402
from PIL import Image                                   # noqa: E402

import link_frames as lfr                               # noqa: E402
import subjects_terrain as st                           # noqa: E402
import tile_forge as tf                                 # noqa: E402

ENC = "utf-8-sig"
OUT = os.path.join("art", "gen3")
MCD_DIRS = [os.path.join("Пиратки", "Dioxine_XPiratez", "user", "mods", "Piratez", "TERRAIN"),
            os.path.join("user", "mods", "XComFiles", "TERRAIN"),
            os.path.join("bin", "UFO", "TERRAIN")]
TRIAGE = os.path.join("art", "_review", "triage", "captions.json")
VLM_MODEL = "orcarouter/Qwen3.8-27B-Uncensored:q5_K_M"

# поля записи MCD (62 байта) - по struct MCD в src/Mod/MapDataSet.cpp, как в triage/build.py
F = dict(ufo_door=30, big_wall=33, gravlift=34, door=35, tu_walk=39, die_mcd=44, type=53, light=58)

FIELDS = ["набор", "кадр", "хэш", "вид", "цвета", "тема", "описание", "откуда", "промпт", "негатив"]


# ------------------------------------------------------------------ данные игры

def mcd_records(set_name):
    path = lfr.find_mcd(MCD_DIRS, set_name)
    if not path:
        return None
    with open(path, "rb") as f:
        data = f.read()
    out = []
    for n in range(0, len(data) - lfr.RECORD + 1, lfr.RECORD):
        b = data[n:n + lfr.RECORD]
        r = {k: b[o] for k, o in F.items()}
        r["frames"] = list(b[0:8])
        r["i"] = len(out)
        out.append(r)
    return out


def kind_of(recs, sh, i):
    """Кем назвать клетку - по MCD. Без MCD - по типам из layout.json."""
    if recs:
        own = [r for r in recs if i in r["frames"]]
        if own:
            r = own[0]
            # обломки - только у предмета: разрушенная стена часто оставляет запись-пол, и слово
            # «rubble» у ровной палубы зовёт модель насыпать мусора
            if r["type"] == 3 and any(x["die_mcd"] and x["die_mcd"] in [o["i"] for o in own]
                                      for x in recs):
                return "rubble"
            if r["ufo_door"]:
                return "sliding door"
            if r["door"]:
                return "door"
            if r["gravlift"]:
                return "lift pad"
            if r["big_wall"] == 1:
                return "solid block"
            if r["big_wall"] in (2, 3):
                return "diagonal wall"
            return {0: "floor", 1: "wall", 2: "wall"}.get(r["type"], "object")
    types = sh.lay.get("types") or []
    t = types[i] if i < len(types) else None
    return {0: "floor", 1: "wall", 2: "wall"}.get(t, "object")


def glows(recs, i):
    return bool(recs) and any(r["light"] for r in recs if i in r["frames"])


# ------------------------------------------------------------------ пиксели

def colour_name(r, g, b):
    h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
    h *= 360.0
    if v < 0.16:
        return "black"
    if s < 0.16 or (v < 0.3 and s < 0.3):
        return ("dark grey" if v < 0.38 else "grey" if v < 0.62 else
                "light grey" if v < 0.84 else "white")
    if h < 14 or h >= 340:
        if v < 0.45:
            return "dark red"
        return "pink" if (s < 0.45 and v > 0.7) else "red"
    if h < 42:
        if v < 0.62 or (s < 0.5 and v < 0.75):
            return "brown"
        return "tan" if s < 0.5 else "orange"
    if h < 68:
        if v < 0.5:
            return "olive"
        return "beige" if s < 0.4 else "yellow"
    if h < 160:
        if s < 0.35:
            return "grey-green"
        return "dark green" if v < 0.42 else "green"
    if h < 200:
        return "teal" if v < 0.55 else "cyan"
    if h < 255:
        return "dark blue" if v < 0.42 else ("steel blue" if s < 0.4 else "blue")
    if h < 290:
        return "purple"
    return "magenta" if s > 0.5 else "pink"


# цветовые слова и их родня: описание модели проверяется по этим группам
COLOUR_WORDS = {
    "black": {"black", "dark grey"}, "white": {"white", "light grey"},
    "grey": {"grey", "dark grey", "light grey", "white", "black", "steel blue", "grey-green"},
    "gray": {"grey", "dark grey", "light grey", "white", "black", "steel blue", "grey-green"},
    "silver": {"grey", "light grey", "white"}, "red": {"red", "dark red", "pink"},
    "crimson": {"red", "dark red"}, "maroon": {"dark red", "brown"}, "orange": {"orange", "tan"},
    "brown": {"brown", "tan", "dark red", "olive", "orange"}, "tan": {"tan", "beige", "brown"},
    "beige": {"beige", "tan"}, "yellow": {"yellow", "beige", "olive", "orange"},
    "gold": {"yellow", "orange", "tan", "beige", "olive"}, "golden": {"yellow", "orange", "tan", "beige", "olive"},
    "olive": {"olive", "grey-green"}, "green": {"green", "dark green", "grey-green", "olive", "teal"},
    "teal": {"teal", "cyan", "green"}, "cyan": {"cyan", "teal"},
    "blue": {"blue", "dark blue", "steel blue", "cyan", "teal"}, "navy": {"dark blue"},
    "purple": {"purple", "magenta"}, "violet": {"purple"}, "pink": {"pink", "magenta", "red"},
    "magenta": {"magenta", "pink", "purple"},
}


def frame_stats(frame):
    """Цвета с долями, насыщенность, яркость, ровность и касание края - всё по пикселям."""
    a = np.asarray(frame.convert("RGBA"), np.float64)
    m = a[..., 3] > 128
    if m.sum() < 4:
        return None
    # дизеринг оригинала - шахматка двух цветов; называть надо то, что видит глаз, поэтому цвета
    # считаем на половинном размере, где шахматка усредняется
    half = frame.convert("RGBA").resize((max(1, frame.width // 2), max(1, frame.height // 2)), Image.BOX)
    h = np.asarray(half, np.float64)
    hm = h[..., 3] > 200
    px = h[..., :3][hm] if hm.sum() >= 3 else a[..., :3][m]
    counts = {}
    for r, g, b in px:
        n = colour_name(r, g, b)
        counts[n] = counts.get(n, 0) + 1
    tot = float(sum(counts.values()))
    colours = sorted(((n, c / tot) for n, c in counts.items()), key=lambda t: -t[1])
    rgb = a[..., :3][m]
    hsv = np.asarray(frame.convert("RGB").convert("HSV"), np.float64)[m]
    lum = rgb @ np.array([0.299, 0.587, 0.114])
    # ровность - та же мерка, что gen_hd.frame_texture: число цветов и перепад соседей
    L = (a[..., :3] @ np.array([0.299, 0.587, 0.114]))
    dx = np.abs(np.diff(L, axis=1))[m[:, 1:] & m[:, :-1]]
    dy = np.abs(np.diff(L, axis=0))[m[1:, :] & m[:-1, :]]
    detail = float(np.concatenate([dx, dy]).mean()) if dx.size + dy.size else 0.0
    ncol = len({tuple(c) for c in rgb.astype(int)})
    ys, xs = np.nonzero(m)
    edge = []
    if xs.min() == 0:
        edge.append("left")
    if xs.max() == frame.width - 1:
        edge.append("right")
    if ys.min() == 0:
        edge.append("top")
    return {"colours": colours, "sat": float(hsv[:, 1].mean() / 255.0), "lum": float(lum.mean()),
            "detail": detail, "ncol": ncol, "flat": ncol <= 8 and detail < 20, "edge": edge,
            "area": float(m.mean())}


def colour_phrase(colours, min_share=0.12, top=3):
    names = [n for n, s in colours if s >= min_share][:top]
    if not names:
        names = [colours[0][0]]
    return ", ".join(names)


# ------------------------------------------------------------------ описание моделью

BANNED = re.compile(r"\b(pixel(?:ated|ized|s)?|pixel[- ]art|8[- ]?bit|16[- ]?bit|retro|sprite|"
                    r"low[- ]?res(?:olution)?|blocky|jagged|isometric|grid|game|tile|icon|"
                    r"stylized|render(?:ing|ed)?|3d|art|image|picture|background)\b", re.I)


def clean_caption(text, stats):
    """Выкинуть запрещённые слова и цвета, которых в кадре нет. Вернуть (текст, что выкинули)."""
    if not text:
        return "", []
    dropped = []
    have = {n for n, s in stats["colours"] if s >= 0.05}
    words = re.findall(r"[A-Za-z-]+|[^A-Za-z-]+", text)
    out = []
    for w in words:
        lw = w.lower()
        if BANNED.fullmatch(lw):
            dropped.append(lw)
            continue
        base = lw[:-2] if lw.endswith("ish") else lw
        if base in COLOUR_WORDS and not (COLOUR_WORDS[base] & have):
            dropped.append(lw)
            continue
        out.append(w)
    t = "".join(out)
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"\s+([,.;])", r"\1", t)
    t = re.sub(r"(,\s*){2,}", ", ", t)
    t = re.sub(r"\b(and|with|of|a|an)\s*([,.]|$)", r"\2", t)
    return t.strip(" ,.;"), dropped


ASK = """You see one tile of the isometric tactical game X-COM (mod X-Piratez), enlarged 8x.
The dark area around it is empty background. Second picture: the whole tile set it belongs to, the tile is outlined in red.
Facts from the game data: it is a {kind}. Setting of the map: {theme}.
Colours measured from its pixels: {colours}.
Name what is drawn so a painter can redraw it. Answer strictly as JSON:
"subject": English noun phrase, 4-12 words: the thing, its material and its visible parts (for example "white metal wall panel with a dark vent slot", "stack of hay bales tied with rope", "cracked grey concrete floor");
"material": 1-3 words.
Rules: use only the measured colours; never mention pixels, resolution, style, game, tile or background; if you cannot tell what it is, describe the surface and material."""


def sheet_hint(sh, i):
    """Весь лист набора, кадр обведён: без соседей кусок стены не отличить от доски."""
    from PIL import ImageDraw
    cols = sh.cols
    n = sh.lay["count"]
    rows = (n + cols - 1) // cols
    W, H = cols * sh.fw, rows * sh.fh
    im = Image.new("RGB", (W, H), (38, 38, 42))
    for k in range(n):
        r, c = divmod(k, cols)
        fr = sh.frame(k)
        im.paste(fr, (c * sh.fw, r * sh.fh), fr)
    im = im.resize((W * 2, H * 2), Image.NEAREST)
    r, c = divmod(i, cols)
    ImageDraw.Draw(im).rectangle((c * sh.fw * 2, r * sh.fh * 2, (c + 1) * sh.fw * 2 - 1,
                                  (r + 1) * sh.fh * 2 - 1), outline=(255, 0, 0), width=2)
    return im


def b64png(im):
    b = io.BytesIO()
    im.convert("RGB").save(b, "PNG")
    return base64.b64encode(b.getvalue()).decode()


def ask_vlm(sh, i, kind, theme, colours, host, model):
    fr = sh.frame(i).convert("RGBA")
    big = fr.resize((fr.width * 8, fr.height * 8), Image.NEAREST)
    bg = Image.new("RGBA", big.size, (38, 38, 42, 255))
    img = Image.alpha_composite(bg, big)
    body = {"model": model, "stream": False, "think": False, "format": "json",
            "options": {"temperature": 0.1, "num_predict": 200},
            "prompt": ASK.format(kind=kind, theme=theme or "unknown", colours=colours),
            "images": [b64png(img), b64png(sheet_hint(sh, i))]}
    req = urllib.request.Request(host + "/api/generate", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        txt = json.loads(r.read().decode())["response"]
    d = json.loads(txt)
    return str(d.get("subject", "")).strip(), str(d.get("material", "")).strip()


def unload_vlm(host, model):
    """Отпустить память карты: Ollama держит модель 20 ГБ, и генератору не хватит места."""
    try:
        body = {"model": model, "keep_alive": 0, "prompt": ""}
        req = urllib.request.Request(host + "/api/generate", json.dumps(body).encode(),
                                     {"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=60).read()
    except Exception:                                   # noqa: BLE001
        pass


# ------------------------------------------------------------------ сам промпт

KIND_EN = {"floor": "a floor tile", "wall": "a wall section", "object": "a standing object",
           "solid block": "a solid block filling the whole cell", "diagonal wall": "a diagonal wall",
           "door": "a door", "sliding door": "a sliding door", "lift pad": "a lift platform",
           "rubble": "rubble and debris left after destruction"}

GREYS = {"black", "dark grey", "grey", "light grey", "white", "steel blue"}


def theme_for(set_name, kind, table):
    theme, _terr = st.subject_for_set(set_name, table)
    if not theme:
        theme, _pat = st.subject_by_name(set_name)
    if not theme:
        return ""
    left, _, right = theme.partition(" | ")
    # R-016: поверхности слева, предметы справа; полу и стене - только поверхности
    return left.strip() if kind in ("floor", "wall", "diagonal wall", "solid block") else \
        (left.strip() + (", " + right.strip() if right else ""))


def negative_for(stats, kind, text):
    neg = ["pixel art", "pixelated", "jagged stair-step edges", "blocky", "text", "letters",
           "logo", "watermark", "extra objects", "changed shape", "blurry", "frame", "border"]
    main = {n for n, s in stats["colours"] if s >= 0.25}
    low = text.lower()
    if main and main <= GREYS and "stone" not in low and "rock" not in low:
        neg += ["rust", "brown stone", "stone masonry", "wood grain", "dirt"]
    if "snow" in low or "ice" in low:
        neg += ["sand", "brown soil"]
    if stats["flat"]:
        neg += ["cracks", "bricks", "tiles pattern", "noise"]
    return ", ".join(neg)


# Слова конструкции и поверхности. Пол, стена и блок без единого из них в описании - это
# описание не того: triage назвал сплошной красный блок корпуса «red leather bra with thin straps»
STRUCT = re.compile(r"\b(floor|flooring|wall|walls|panel|panels|plate|plates|plating|deck|block|blocks|"
                    r"slab|slabs|ground|tiles?|tiled|bulkhead|hull|bricks?|stones?|concrete|metal|steel|"
                    r"iron|grating|grate|planks?|boards?|wood|wooden|carpet|sand|sandy|grass|grassy|snow|"
                    r"soil|dirt|mud|rock|rocks|rocky|water|ice|road|asphalt|pavement|roof|window|door|"
                    r"fence|hedge|column|pillar|pipes?|beam|girder|frame|glass|marble|plaster|surface|"
                    r"gravel|earth|cliff|dune|lava|flesh|membrane|organic|crystal|machinery|console|"
                    r"cave|mesh|vent|shutter|gate|arch|stairs?|steps|ramp|ledge|edge|corner|segment|"
                    r"section|plaster|tarmac|cobble|cobblestones?|straw|thatch|leaves|moss|bark)\b", re.I)
SURFACE_KINDS = ("floor", "wall", "diagonal wall", "solid block", "door", "sliding door", "lift pad")


def cut_edges(edge):
    """Где предмет обрезан рамкой. Оба бока сразу - это предмет во всю ширину клетки, не обрезка."""
    sides = [e for e in edge if e in ("left", "right")]
    return (["top"] if "top" in edge else []) + (sides if len(sides) == 1 else [])


def fits_kind(subject, kind):
    return kind not in SURFACE_KINDS or bool(STRUCT.search(subject))


def compose(set_name, i, kind, stats, theme, subject, glow=False):
    """Промпт для Qwen-Image-2.1 edit без LoRA: указание, а не список тегов."""
    colours = colour_phrase(stats["colours"])
    parts = ["Redraw this X-COM game tile as a clean high-resolution painted game asset."]
    if subject:
        parts.append("It is %s: %s." % (KIND_EN.get(kind, "an object"), subject))
    else:
        parts.append("It is %s." % KIND_EN.get(kind, "an object"))
    if theme:
        parts.append("Setting: %s." % theme)
    parts.append("Main colours: %s." % colours)
    if stats["flat"]:
        parts.append("The surface is smooth and even, keep it plain.")
    if glow:
        parts.append("It glows.")
    # ромб пола касается левого и правого края по построению, стена - часть длинной стены:
    # фраза про обрезанный край нужна только предмету, который правда обрезан рамкой кадра
    if kind in ("wall", "diagonal wall"):
        parts.append("It is one piece of a longer wall that continues into the neighbouring cells.")
    elif kind in ("object", "rubble") and cut_edges(stats["edge"]):
        parts.append("This is a cut-out part of a larger structure that continues past the %s "
                     "edge; do not close or round off the cut." % " and ".join(cut_edges(stats["edge"])))
    parts.append("Keep exactly the same outline, position, colours and light direction as the "
                 "source. Turn the pixel steps into smooth straight edges and add fine realistic "
                 "detail only inside the existing shapes. No text, no new objects.")
    return " ".join(parts)


def dominant_hex(frame, n=3, min_share=0.10):
    """Главные цвета кадра числом: на половинном размере (дизеринг усреднён), квантование PIL."""
    half = frame.convert("RGBA").resize((max(1, frame.width // 2), max(1, frame.height // 2)), Image.BOX)
    a = np.asarray(half, np.uint8)
    px = a[..., :3][a[..., 3] > 200]
    if len(px) < 3:
        a = np.asarray(frame.convert("RGBA"), np.uint8)
        px = a[..., :3][a[..., 3] > 128]
    if len(px) == 0:
        return []
    strip = Image.fromarray(px.reshape(1, -1, 3), "RGB").quantize(colors=n, method=Image.MEDIANCUT)
    pal = strip.getpalette()
    cnt = np.bincount(np.asarray(strip).ravel(), minlength=n)
    out = []
    for k in np.argsort(-cnt):
        if cnt[k] / float(cnt.sum()) >= min_share:
            out.append("#%02X%02X%02X" % tuple(pal[3 * k:3 * k + 3]))
    return out


STRUCT_KIND = {"floor": "floor surface (seen from above at an isometric angle)",
               "wall": "wall section", "diagonal wall": "diagonal wall section",
               "object": "standing object", "solid block": "solid block filling the whole cell",
               "door": "door", "sliding door": "sliding door", "lift pad": "lift platform",
               "rubble": "rubble and debris"}


def compose_structured(kind, stats, theme, subject, material, hexes, glow=False, refs=0):
    """Указание разделами: что за вещь, из чего, какого цвета, что нельзя менять. Материал
    называется ПРЯМО (R-063: каменная фактура на металле проходит мимо мерок цвета) - модель
    держит то, что названо, а не то, что запрещено в негативе."""
    sat = "low saturation, neutral" if stats["sat"] < 0.08 else (
        "moderate saturation" if stats["sat"] < 0.25 else "saturated")
    obj = subject or STRUCT_KIND.get(kind, "object")
    lines = ["TASK: high-resolution restoration of the supplied low-resolution game sprite "
             "(image 1). This is a restoration, not a reinterpretation."]
    if refs:
        lines.append("CONTEXT: image 2 is the whole tile set this sprite belongs to, the sprite is "
                     "outlined in red. Use it only to understand what the sprite is; edit image 1 only.")
    lines.append("OBJECT: %s; %s." % (STRUCT_KIND.get(kind, "object"), obj))
    if material:
        lines.append("MATERIAL: %s%s." % (material, ", smooth even surface" if stats["flat"] else ""))
    elif stats["flat"]:
        lines.append("MATERIAL: smooth even surface.")
    if theme:
        lines.append("SETTING: %s." % theme)
    col = colour_phrase(stats["colours"])
    lines.append("COLOUR: %s%s; %s." % (col, (" (" + ", ".join(hexes) + ")") if hexes else "", sat))
    if glow:
        lines.append("LIGHT: it glows.")
    if kind in ("wall", "diagonal wall"):
        lines.append("STRUCTURE: one piece of a longer wall that continues into the neighbouring cells.")
    elif kind in ("object", "rubble") and cut_edges(stats["edge"]):
        lines.append("STRUCTURE: cut-out part of a larger structure continuing past the %s edge; "
                     "do not close or round off the cut." % " and ".join(cut_edges(stats["edge"])))
    elif kind == "floor":
        lines.append("STRUCTURE: the ground repeats seamlessly in every direction; keep the "
                     "large-scale pattern and do not add new large objects.")
    lines.append("GEOMETRY: preserve the exact silhouette, proportions, openings, major edges, "
                 "component positions and light direction of the source.")
    lines.append("DETAIL: replace the pixel steps with clean straight edges and add fine realistic "
                 "detail of the named material inside the existing shapes. No text, no new objects.")
    return "\n".join(lines)


def lora_caption(kind, stats, subject, trigger="oxcehd, "):
    """Та же подпись, что при обучении LoRA oxcehd: '{trigger}X-COM isometric {kind} tile, {hint}'."""
    k = "floor" if kind == "floor" else ("wall" if "wall" in kind or kind == "solid block" else "object")
    hint = subject or colour_phrase(stats["colours"])
    return "%sX-COM isometric %s tile, %s" % (trigger, k, hint)


# ------------------------------------------------------------------ обход

def frame_hash(frame):
    return hashlib.md5(np.asarray(frame.convert("RGBA")).tobytes()).hexdigest()


def load_json(path):
    if os.path.exists(path):
        with open(path, encoding=ENC) as f:
            return json.load(f)
    return {}


def save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding=ENC) as f:
        json.dump(data, f, ensure_ascii=False, indent=0)
    os.replace(tmp, path)


def read_tsv(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding=ENC, newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def write_tsv(path, rows):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding=ENC, newline="") as f:
        w = csv.DictWriter(f, FIELDS, delimiter="\t", lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)


class Writer:
    """Промпты по кадрам. Используется и отдельно (CLI), и изнутри paint3.py."""

    def __init__(self, sheets, out=OUT, vlm=False, host="http://127.0.0.1:11434",
                 model=VLM_MODEL, use_triage=True):
        self.sheets, self.out = sheets, out
        self.vlm, self.host, self.model = vlm, host, model
        os.makedirs(out, exist_ok=True)
        self.cache_path = os.path.join(out, "captions.json")
        self.cache = load_json(self.cache_path)
        self.triage = load_json(TRIAGE) if use_triage else {}
        self.table = st.load_set_terrains(st.default_index_path())
        self.mcd = {}
        self.asked = 0

    def row(self, sh, i):
        name = sh.name
        fr = sh.frame(i)
        stats = frame_stats(fr)
        if stats is None:
            return None
        if name not in self.mcd:
            self.mcd[name] = mcd_records(name)
        recs = self.mcd[name]
        kind = kind_of(recs, sh, i)
        theme = theme_for(name, kind, self.table)
        h = frame_hash(fr)
        subject, src = "", "факты"
        c = self.cache.get(h)
        if c is None and self.vlm:
            try:
                s, mat = ask_vlm(sh, i, KIND_EN.get(kind, kind), theme,
                                 colour_phrase(stats["colours"]), self.host, self.model)
                c = {"subject": s, "material": mat, "from": "vlm"}
                self.cache[h] = c
                self.asked += 1
                if self.asked % 10 == 0:
                    save_json(self.cache_path, self.cache)
            except Exception as e:                      # noqa: BLE001
                print("  %s %d: описание не получено (%s)" % (name, i, e), file=sys.stderr)
        if c is None:
            t = self.triage.get("%s_%d" % (name.replace(".PCK", ""), i))
            if t and t.get("en"):
                c = {"subject": t["en"], "material": t.get("material", ""), "from": "triage"}
        hint = sh.hints.get(i, "")
        # подсказка руками надёжнее любой модели: сначала она
        if hint:
            subject, _ = clean_caption(hint, stats)
            src = "hints.json"
        elif c:
            subject, dropped = clean_caption(c["subject"], stats)
            src = c.get("from", "vlm") + (" (выкинуто: %s)" % ", ".join(sorted(set(dropped))) if dropped else "")
            if not fits_kind(subject, kind):
                src = "факты (%s «%s» не про %s)" % (c.get("from", "vlm"), subject, kind)
                subject = ""
        prompt = compose(name, i, kind, stats, theme, subject, glows(recs, i))
        material = (c or {}).get("material", "")
        material = clean_caption(material, stats)[0] if material else ""
        return {"набор": name, "кадр": i, "хэш": h, "вид": kind,
                "_material": material, "_glow": glows(recs, i), "_theme": theme,
                "_hex": dominant_hex(fr),
                "цвета": ", ".join("%s %d%%" % (n, round(s * 100)) for n, s in stats["colours"][:4]),
                "тема": theme, "описание": subject, "откуда": src, "промпт": prompt,
                "негатив": negative_for(stats, kind, subject + " " + theme),
                "_stats": stats}

    def flush(self):
        save_json(self.cache_path, self.cache)
        if self.vlm and self.asked:
            unload_vlm(self.host, self.model)


def main():
    ap = argparse.ArgumentParser(description="промпты на каждый кадр из фактов")
    ap.add_argument("--sheets", default=os.path.join("art", "TERRAIN"))
    ap.add_argument("--sets", default="", help="наборы через запятую")
    ap.add_argument("--list", default="", help="файл строк 'НАБОР кадр' - ровно эти кадры")
    ap.add_argument("--frames", default="", help="номера через запятую (по умолчанию все)")
    ap.add_argument("--vlm", action="store_true", help="описание моделью со зрением (Ollama)")
    ap.add_argument("--host", default="http://127.0.0.1:11434")
    ap.add_argument("--model", default=VLM_MODEL)
    ap.add_argument("--no-triage", dest="triage", action="store_false",
                    help="не брать описания из art/_review/triage/captions.json")
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--show", type=int, default=5, help="сколько промптов напечатать")
    args = ap.parse_args()

    wr = Writer(args.sheets, args.out, args.vlm, args.host, args.model, args.triage)
    frames = [int(x) for x in args.frames.split(",") if x.strip()] if args.frames else None
    sets = [s.strip().upper().replace(".PCK", "") + ".PCK" for s in args.sets.split(",") if s.strip()]
    only = {}
    if args.list:
        with open(args.list, encoding=ENC) as f:
            for line in f:
                p = line.split()
                if len(p) >= 2 and not line.startswith("#"):
                    only.setdefault(p[0].upper().replace(".PCK", "") + ".PCK", []).append(int(p[1]))
        sets = list(only)
    if not sets:
        sys.exit("нужен --sets или --list")
    tsv = os.path.join(args.out, "prompts.tsv")
    keep = [r for r in read_tsv(tsv) if r["набор"] not in sets]
    new = []
    for name in sets:
        sh = tf.Sheet(args.sheets, name)
        for i in (only[name] if name in only else frames if frames is not None else sh.frames()):
            if i >= sh.lay["count"] or tf.alpha_box(sh.frame(i)) is None:
                continue
            r = wr.row(sh, i)
            if r:
                new.append(r)
    wr.flush()
    write_tsv(tsv, keep + new)
    srcs = {}
    for r in new:
        k = r["откуда"].split(" ")[0]
        srcs[k] = srcs.get(k, 0) + 1
    print("кадров: %d -> %s" % (len(new), tsv))
    print("описание взято: " + ", ".join("%s %d" % kv for kv in sorted(srcs.items())))
    for r in new[:args.show]:
        print("\n%s %s  [%s]  %s" % (r["набор"], r["кадр"], r["вид"], r["цвета"]))
        print("  откуда:  " + r["откуда"])
        print("  промпт:  " + r["промпт"])
        print("  негатив: " + r["негатив"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
