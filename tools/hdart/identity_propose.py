#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Предлагатель опознания: что это за предмет, для ассетов без описания (Pipeline v2, P1-A, P1-B).

У 1987 ассетов-предметов нет ни описания из прежних партий, ни подсказки карты (NO_PROPOSAL в
asset_identity.tsv). Локальная модель со зрением (Ollama, та же, что в triage/caption.py) ПРЕДЛАГАЕТ
опознание; подтверждает только человек на странице review_server.

Модель не угадывает по одной картинке 32x40 - ей дано всё, что известно о ассете (P1-B, п.2):
  картинки: сам ассет nearest x4 (без художественной обработки), место на карте с рамкой,
            полоса членов семейства и кандидатов «другой бок» с подписями;
  факты:    набор PCK и номер кадра, террейны рулсетов с этим набором, карты и сколько раз стоит,
            клеток и раскладка (составной), физика MCD (тип записи, проходимость, броня, горит ли,
            взрывается ли, свет, закрывает ли обзор, есть ли кадр разрушения и второе состояние,
            анимация), объём по вокселям LOFT, соседи по клетке на карте (с их опознанием, если есть),
            класс по MCD (object_or_relief - «предмет или рельеф?»).

Ответ (P1-B, п.3) - запись в art/objects/discovery/proposals.json:
  asset_id, proposed_name, proposed_category, proposed_material, short_description (фраза для промпта),
  ru, confidence, evidence (на что опиралась: picture, map_context, neighbours, tileset_name,
  terrain_name, mcd, footprint, family), ambiguity, status = PROPOSED, model, when, facts, facts_hash.
UNKNOWN лучше неверного ответа (п.4): модель прямо просят ответить proposed_name = UNKNOWN и написать
ambiguity, если данных мало; у «предмет или рельеф?» порог уверенности выше.

Каждый ассет спрашивается ДВАЖДЫ (температура 0.2 и 0.8), оба ответа хранятся (first, second), и
сведение reconcile() ставит статус (замечания 29.09):
  PROPOSED           - тот же предмет теми же словами; категория разная - не выше 0.6;
  PROPOSED_AMBIGUOUS - тот же смысл только через словарь SYNONYMS (pillar / column) - не выше 0.5;
  REVIEW_REQUIRED    - назвали разные предметы (barrel / pillar) или разошлись в «предмет или рельеф»:
                       имени нет, обе догадки - в candidates, страница прячет их (не якорить человека);
  UNKNOWN            - модель не опознала.
Правило сведения меняется без модели: --reconcile пересчитывает все пары за секунды (ask_rev от него не
зависит). Сводка --stats: четыре числа сведения и матрица «на что опирался ответ -> чем кончилось».

Предложение никогда не становится подтверждённым: obj_generation ставит ему AGENT_PROPOSED (у PROPOSED_AMBIGUOUS
тоже, с пометкой), REVIEW_REQUIRED - своим статусом без текста, UNKNOWN остаётся NO_PROPOSAL, и к генерации не
пускает ни одно из них без решения человека. confidence только сортирует карточки. Одинаковое описание у
разных семейств допустимо - семейства от этого не сливаются (п.5).

Ответы копятся по одному; прерванный прогон продолжается с места. Ошибки - proposals_errors.json.

Модель на видеокарте - только через очередь (tools/gpu_scripts.txt):
    py -3 tools/gpuq.py add --name identity-propose -- C:/Python313/python.exe E:/OpenXCom/tools/hdart/identity_propose.py
    py -3.13 tools/hdart/identity_propose.py --dry-run --limit 5    # факты и картинки, без модели
    py -3.13 tools/hdart/identity_propose.py --stats                # сводка по готовым ответам
    py -3.13 tools/hdart/identity_propose.py --reconcile            # пересвести пары, модель не звать
После прогона - py -3.13 tools/hdart/obj_generation.py (или «Пересобрать» на странице проверки).
"""
import argparse
import base64
import csv
import hashlib
import io
import json
import os
import re
import sys
import time
import urllib.request
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.dirname(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

ENC = "utf-8-sig"
DISC = os.path.join("art", "objects", "discovery")
FAMS = os.path.join("art", "objects", "families", "families.json")
OUT = os.path.join(DISC, "proposals.json")
SET_TERRAINS = os.path.join(".index", "mod", "Piratez", "set_terrains.tsv")
MODEL = "orcarouter/Qwen3.8-27B-Uncensored:q5_K_M"     # как в triage/caption.py
CTX_SIDE = 768                                          # место на карте: не больше, иначе не влезет в num_ctx
STRIP_MAX = 6                                           # членов семейства на полосе
CATEGORIES = ("furniture", "container", "machine or electronics", "vehicle or vehicle part", "light",
              "sign or decoration", "goods or small items", "debris or junk", "plant or nature",
              "rock or terrain relief", "wall or building part", "other", "UNKNOWN")
EVIDENCE = ("picture", "map_context", "neighbours", "tileset_name", "terrain_name", "mcd", "footprint", "family")
MAP_EV = ("map_context", "neighbours")
DATA_EV = ("tileset_name", "terrain_name", "mcd", "footprint")
HIGH, MEDIUM = 0.75, 0.45                               # сводка: high >= 0.75, medium >= 0.45, иначе low
RELIEF_MIN = 0.6                                        # «предмет или рельеф?» ниже этого - неоднозначно
TILE_TYPE = {0: "floor record", 1: "west wall record", 2: "north wall record", 3: "object record"}
PART = {0: "floor", 1: "west wall", 2: "north wall", 3: "object"}

ASK = """You identify ONE object from the 1994 isometric game X-COM (mod X-Piratez) for a remake.
Picture 1: the object itself - the original pixel art enlarged 4x with nearest neighbour (no changes);
the dark grey around it is empty background.
Picture 2 (if given): the object in its place on a real game map, marked with a red frame; other things
there are NOT the answer, they are context.
Picture 3 (if given): other members of the same family (recolours, mirrors) and possible other sides of it,
each labelled.
Game data about the object:
{facts}
The sprite is tiny (32x40 pixels): most of them could be several things. First look at Picture 1 ALONE,
ignoring all names, and say what you see; then use the map and the data.
Answer strictly as JSON with keys:
"picture_alone": what Picture 1 alone shows, 1-6 English words, without using any names or data;
"alternatives": a list of 1-3 other things it could plausibly be (always give at least one);
"proposed_name": a short English name of the object (1-4 words), or "UNKNOWN";
"proposed_category": one of {categories};
"proposed_material": main material, 1-3 English words, or "";
"short_description": an English noun phrase for an image prompt, max 16 words: what it is, shape, materials,
colours, no style words; "" if UNKNOWN;
"ru": the same in Russian, 1 sentence;
"confidence": how sure you are WHAT the object is, by this scale:
  0.9 - Picture 1 alone clearly shows exactly this object, the alternatives are unlikely, the data agree;
  0.7 - the picture fits, but the alternatives are also possible; the map or the data decided it;
  0.5 - the picture is unclear; the answer comes mostly from the tileset or terrain name;
  0.3 or less - a guess: answer UNKNOWN instead;
  if "picture_alone" names a different thing than "proposed_name", confidence is at most 0.5;
"evidence": a list of the clues you really used, from {evidence};
"ambiguity": "" if clear, otherwise what else it could be and what is missing.
UNKNOWN is better than a wrong answer: if the picture, the map and the data together do not tell what
it is, answer "proposed_name": "UNKNOWN" and explain in "ambiguity". Do not pick an object just to answer.{relief}"""
RELIEF = """
This one may be terrain relief (a hill, mound, slope, ramp) rather than an object: game data cannot tell.
Add the key "relief_decision": "object" (a separate thing standing on the ground), "relief" (the ground
itself shaped as a hill or slope) or "unsure". Answer "object" or "relief" only if the pictures clearly
show it; otherwise "unsure", "proposed_name": "UNKNOWN", and write in "ambiguity" what it could be."""


# ------------------------------------------------------------------ контекст

class Context:
    """Всё, что известно об ассете, кроме картинок: читается один раз на прогон."""

    def __init__(self, items, fams, ident):
        import map_mockup as mm
        import obj_struct as os_
        self.mm = mm
        self.items = items                                      # rank -> item
        self.by_key = {it["keys"][0].upper(): it for it in items.values()}
        self.fams = fams
        self.ident = ident
        self.world = mm.World()
        self.struct = os_.Struct(self.world)
        self.usage = mm.usage(self.world)
        self.set_terrains = {}
        if os.path.exists(SET_TERRAINS):
            with open(SET_TERRAINS, encoding=ENC, newline="") as f:
                for r in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
                    self.set_terrains[r["set"].upper()] = [t.strip() for t in r["terrains"].split(",") if t.strip()]
        self.blocks = {}

    def label(self, key):
        """Как назвать соседа: опознание или подсказка, если есть."""
        r = self.ident.get(key, {})
        text = r.get("identity") or r.get("proposed") or self.by_key.get(key, {}).get("hint", "")
        return text.replace("[фото] ", "")[:60]

    def neighbours(self, key, where):
        """Что стоит в той же клетке и в 8 соседних на том же этаже, в первом месте на карте."""
        if not where or "/" not in where:
            return []
        terrain, block = where.split("/", 1)
        s0, f0 = key.split(":")
        f0 = int(f0)
        try:
            if block not in self.blocks:
                sets = self.world.sets_of(terrain)
                sizes = {s: len(self.world.records(s)) for s in sets}
                self.blocks[block] = (sets, sizes, self.mm.read_block(self.world, block))
            sets, sizes, (_sx, _sy, _sz, cells) = self.blocks[block]
        except (SystemExit, Exception):                          # noqa: BLE001
            return []

        def parts(cell):
            for part, v in enumerate(cell or ()):
                if v:
                    s, rec = self.mm.pc.resolve(v, sets, sizes)
                    if s is not None:
                        yield part, "%s:%d" % (s.upper(), self.world.records(s)[rec]["frame"])
        at = next((xyz for xyz, cell in sorted(cells.items())
                   if any(k == "%s:%d" % (s0.upper(), f0) for _p, k in parts(cell))), None)
        if at is None:
            return []
        x, y, z = at
        out = Counter()
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for part, k in parts(cells.get((x + dx, y + dy, z))):
                    if k == key:
                        continue
                    out[(PART[part], k, "same cell" if dx == dy == 0 else "next cell")] += 1
        return [{"part": p, "key": k, "where": w, "what": self.label(k)} for (p, k, w), _n in out.most_common(12)]

    def mcd(self, key):
        s, f = key.split(":")
        rec = self.struct.record(s, int(f))
        if rec is None:
            return None
        info = self.struct.info(s, int(f))
        p = info.get("phys", {})
        vox = info.get("vox")
        fill = [int(v) for v in vox.reshape(12, -1).sum(1)] if vox is not None else []
        layers = sum(1 for v in fill if v)
        return {"tile_type": TILE_TYPE.get(rec[53], "type %d" % rec[53]),
                "walkable": p.get("tu_walk", 255) < 255, "tu_walk": p.get("tu_walk", 255),
                "armor": p.get("armor", 0), "burns": p.get("flammable", 255) < 255,
                "explodes": p.get("he_strength", 0) > 0, "light_source": p.get("light_source", 0),
                "blocks_sight": bool(p.get("stop_los")), "big_wall": p.get("big_wall", 0),
                "destroyed_version": rec[44] > 0, "second_state": rec[46] > 0,
                "animated": len(set(rec[0:8])) > 1,
                "height_layers": layers, "bottom_fill": round(fill[0] / 256, 2) if fill else 0,
                "sprite_h": info.get("h", 0), "sprite_w": info.get("w", 0)}

    def facts(self, row, it):
        key = it["keys"][0].upper()
        fm = self.fams.get(row["asset_id"])
        sets = sorted({k.split(":")[0].upper() for k in it["keys"][:1] + it["src"]})
        use = self.usage.get(key, [])
        terr = Counter()
        for t, _b, n in use:
            terr[t] += n
        members, views = [], []
        if fm:
            for m in fm["members"][1:]:
                (views if m.get("relation") == "alternate_view" else members).append(
                    {"key": m["keys"][0], "relation": m.get("relation", ""), "decision": m.get("decision", "")})
            for m in fm.get("review", []):
                if m.get("reason", "").startswith("alternate_view"):
                    views.append({"key": m["keys"][0], "relation": "possible other side", "decision": "REVIEW"})
        return {"asset_id": row["asset_id"], "frames": it["src"], "tilesets": sets,
                "terrains_of_tileset": sorted({t for s in sets for t in self.set_terrains.get(s, [])})[:8],
                "map_example": it.get("map", ""), "placed": it.get("places", 0), "blocks": it.get("blocks", 0),
                "terrains_used": [t for t, _n in terr.most_common(6)],
                "cells": len(it["src"]), "kind": it.get("kind", ""), "layout": it.get("at", []),
                "asset_class": row.get("asset_class", ""),
                "mcd": self.mcd(it["src"][0]),
                "family": members, "other_sides": views,
                "neighbours": self.neighbours(it["src"][0].upper(), it.get("map", ""))}


def facts_text(fx):
    """Факты словами для модели; пустое не пишется."""
    L = ["- tileset (PCK) %s, frame %s" % (", ".join(fx["tilesets"]), ", ".join(fx["frames"]))]
    if fx["terrains_of_tileset"]:
        L.append("- ruleset terrains using this tileset: %s" % ", ".join(fx["terrains_of_tileset"]))
    if fx["map_example"]:
        L.append("- placed %s times on %s map blocks; terrains: %s; example map %s" % (
            fx["placed"], fx["blocks"], ", ".join(fx["terrains_used"]) or "?", fx["map_example"]))
    if fx["cells"] > 1:
        L.append("- one object of %d map cells (composite), cell offsets %s" % (fx["cells"], fx["layout"]))
    m = fx["mcd"]
    if m:
        bits = [m["tile_type"],
                "walkable" if m["walkable"] else "blocks movement",
                "armor %d" % m["armor"], "burns" if m["burns"] else "does not burn"]
        bits += [b for b, on in (("explodes when destroyed", m["explodes"]), ("emits light", m["light_source"]),
                                 ("blocks line of sight", m["blocks_sight"]),
                                 ("has a destroyed version", m["destroyed_version"]),
                                 ("has a second state (opens, switches)", m["second_state"]),
                                 ("animated", m["animated"])) if on]
        L.append("- MCD: " + ", ".join(bits))
        L.append("- volume: %d of 12 height layers, bottom layer fills %d%% of the cell; sprite %dx%d px" % (
            m["height_layers"], m["bottom_fill"] * 100, m["sprite_w"], m["sprite_h"]))
    if fx["family"]:
        L.append("- same object in other tilesets/colours: %s" % ", ".join(
            "%s (%s)" % (x["key"], x["relation"]) for x in fx["family"][:8]))
    if fx["other_sides"]:
        L.append("- possible other sides of it: %s" % ", ".join(x["key"] for x in fx["other_sides"][:6]))
    if fx["neighbours"]:
        L.append("- on the map next to: %s" % "; ".join(
            "%s %s %s%s" % (n["where"], n["part"], n["key"], (" (%s)" % n["what"]) if n["what"] else "")
            for n in fx["neighbours"]))
    if fx["asset_class"] == "object_or_relief":
        L.append("- game data cannot tell if this is an object or terrain relief")
    return "\n".join(L)


# ------------------------------------------------------------------ картинки

def b64(im):
    b = io.BytesIO()
    im.convert("RGB").save(b, "PNG")
    return base64.b64encode(b.getvalue()).decode()


def strip(rend, fx, items_by_key):
    """Полоса членов семейства и возможных других боков, по кадру x4 с подписью."""
    from PIL import Image, ImageDraw
    cells = []
    for x in (fx["family"] + fx["other_sides"])[:STRIP_MAX]:
        it = items_by_key.get(x["key"].upper())
        raw = rend.asset(it["rank"]) if it else None
        if raw is None:
            continue
        im = Image.open(io.BytesIO(raw)).convert("RGB")
        lab = Image.new("RGB", (max(im.width, 150), im.height + 18), (20, 20, 24))
        lab.paste(im, (0, 18))
        ImageDraw.Draw(lab).text((3, 3), "%s %s" % (x["key"], x["relation"]), fill=(255, 220, 0))
        cells.append(lab)
    if not cells:
        return None
    out = Image.new("RGB", (sum(c.width for c in cells) + 6 * (len(cells) - 1), max(c.height for c in cells)),
                    (20, 20, 24))
    x = 0
    for c in cells:
        out.paste(c, (x, 0))
        x += c.width + 6
    return out


def pictures(rend, rank, fx, items_by_key):
    """[ассет x4, место на карте, полоса семейства] -> base64; первого нет - пусто."""
    from PIL import Image
    out = []
    raw = rend.asset(rank)
    if raw is None:
        return out
    out.append(b64(Image.open(io.BytesIO(raw))))
    raw = rend.context(rank)
    if raw is not None:
        im = Image.open(io.BytesIO(raw)).convert("RGB")
        k = CTX_SIDE / max(im.size)
        if k < 1:
            im = im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))), Image.LANCZOS)
        out.append(b64(im))
    st = strip(rend, fx, items_by_key)
    if st is not None:
        k = CTX_SIDE / st.width
        if k < 1:
            st = st.resize((CTX_SIDE, max(1, int(st.height * k))), Image.LANCZOS)
        out.append(b64(st))
    return out


# ------------------------------------------------------------------ ответ

def normalize(d, fx):
    """Ответ модели -> запись предложения; всё сомнительное - к UNKNOWN, а не к догадке."""
    name = str(d.get("proposed_name", "")).strip()
    try:
        conf = min(1.0, max(0.0, float(d.get("confidence", 0.0))))
    except (TypeError, ValueError):
        conf = 0.0
    cat = d.get("proposed_category") if d.get("proposed_category") in CATEGORIES else "other"
    ev = d.get("evidence") if isinstance(d.get("evidence"), list) else []
    ev = [e for e in ev if e in EVIDENCE] or ["picture"]
    amb = str(d.get("ambiguity", "")).strip()
    desc = str(d.get("short_description", "")).strip()
    alt = [str(x).strip() for x in d.get("alternatives", []) if str(x).strip()] \
        if isinstance(d.get("alternatives"), list) else []
    alone = str(d.get("picture_alone", "")).strip()
    # прогон 29.09 (150 ответов): все 0.90-0.95, ни одного UNKNOWN - число модели не различает ответы.
    # Потолки по тому, на что ответ опирается, ставит код, а не модель:
    if "picture" not in ev:
        conf = min(conf, 0.6)             # картинку не использовала - ответ из имён и данных
    if not alt:
        conf = min(conf, 0.7)             # не назвала ни одной альтернативы - не думала о них
    relief = str(d.get("relief_decision", "")).strip().lower() if fx["asset_class"] == "object_or_relief" else ""
    if not name or name.upper() == "UNKNOWN" or cat == "UNKNOWN":
        name, cat, desc = "UNKNOWN", "UNKNOWN", ""
        amb = amb or "модель не назвала предмет"
    elif fx["asset_class"] == "object_or_relief" and relief not in ("object", "relief"):
        # «предмет или рельеф?» без явного решения - к человеку, а не догадкой (P1-B, п.4)
        amb = amb or "предмет или рельеф - модель не решила (%s): %s" % (relief or "нет ответа", name)
        name, cat, desc = "UNKNOWN", "UNKNOWN", ""
    elif conf <= 0.3:                     # по шкале запроса это догадка: UNKNOWN лучше неверного
        amb = amb or "догадка (уверенность %.2f): %s" % (conf, name)
        name, cat, desc = "UNKNOWN", "UNKNOWN", ""
    return {"asset_id": fx["asset_id"], "proposed_name": name, "proposed_category": cat,
            "picture_alone": alone, "alternatives": alt, "relief_decision": relief,
            "proposed_material": str(d.get("proposed_material", "")).strip() if name != "UNKNOWN" else "",
            "short_description": desc or ("" if name == "UNKNOWN" else name),
            "ru": str(d.get("ru", "")).strip(), "confidence": round(conf, 2), "evidence": ev,
            "ambiguity": amb, "status": "PROPOSED", "asset_class": fx["asset_class"]}


def ask_rev():
    """Версия ЗАПРОСА к модели: правка текста запроса делает прежние ответы устаревшими - прогон спросит
    заново. Правило сведения двух ответов сюда не входит: оба ответа хранятся (first, second), и сведение
    пересчитывается без модели (--reconcile). Хвост "two-answers:2:0.4:0.6" - литерал, с которым шёл
    прогон #274 (запрос о двух ответах); менять его - значит спросить 1987 ассетов заново, ~4 часа."""
    return hashlib.sha1((ASK + RELIEF + REQUEST_SALT).encode("utf-8")).hexdigest()[:12]


REQUEST_SALT = "two-answers:2:0.4:0.6"
STOP = {"a", "an", "the", "of", "with", "and", "on", "in", "small", "large", "big", "old", "piece", "part",
         "segment", "section"}
# общие слова, которые не называют предмет: главным словом берётся слово перед ними (storage unit -> storage)
GENERIC = {"unit", "object", "structure", "item", "thing", "fragment", "set", "assembly", "element", "piece",
           "part", "section", "segment", "portion"}
# ОДИН смысл разными словами (разбор 29.09): первый в группе - каноническое слово. Совпадение только через
# словарь - PROPOSED_AMBIGUOUS (близко, но решает человек). Словарь, не модель: правится здесь и пересчитывается
# --reconcile за секунды
SYNONYMS = (("column", "pillar", "pilaster"), ("crate", "box"), ("sofa", "couch", "settee"),
            ("lamp", "light", "lantern"), ("wreckage", "debris", "rubble", "junk", "scrap"),
            ("barrel", "keg", "cask"), ("cabinet", "cupboard"), ("rock", "stone", "boulder"),
            ("bush", "shrub"), ("bed", "cot", "bunk"), ("console", "terminal"), ("seat", "chair"),
            ("machine", "machinery", "device", "apparatus"), ("pipe", "tube", "pipeline"),
            ("sign", "signboard", "signpost"), ("car", "automobile"), ("rug", "carpet", "mat"),
            ("stair", "staircase", "step"), ("wreckage", "wreck"), ("mound", "hill", "hillock", "knoll"),
            ("vegetation", "foliage", "greenery"), ("shelf", "shelving", "rack"), ("bin", "can", "dustbin"))
CANON = {}
for _g in SYNONYMS:
    for _w in _g:
        CANON.setdefault(_w, CANON.get(_g[0], _g[0]))       # wreck -> wreckage, а wreckage уже в группе debris
ADJ = {"rocky": "rock", "grassy": "grass", "mossy": "moss", "sandy": "sand", "icy": "ice", "stony": "stone",
       "wooden": "wood", "metallic": "metal"}
RECONCILE_RULE = 5                  # правка verdict/reconcile - поднять; ответы не переспрашиваются (4 - приставки,
                                    # 5 - review_level)
AGREE_CAP = 0.4                     # прежнее правило (rule 2): разошлись - не выше; для ответов до rule 3
NAME_CAP = 0.6                      # имя то же, категория нет - PROPOSED не выше этого
SYN_CAP = 0.5                       # тот же смысл другим словом - PROPOSED_AMBIGUOUS не выше этого
ANSWER_KEYS = ("proposed_name", "proposed_category", "relief_decision", "confidence", "short_description",
               "proposed_material")
# статус ответа модели (P1-B, замечания 29.09): совпали - PROPOSED; тот же смысл через синонимы -
# PROPOSED_AMBIGUOUS; назвали РАЗНЫЕ предметы - REVIEW_REQUIRED (имени нет, догадки скрыты от первого взгляда,
# чтобы не якорить человека); не опознала - UNKNOWN
MODEL_STATUSES = ("PROPOSED", "PROPOSED_AMBIGUOUS", "REVIEW_REQUIRED", "UNKNOWN")


def stem(w):
    """Грубое единственное число: boxes -> box, shelves -> shelf, mounds -> mound (не glass, cactus, debris)."""
    if len(w) > 4 and w.endswith("ves"):
        return w[:-3] + "f"
    if len(w) > 4 and w.endswith("ies"):                    # berries -> berry, batteries -> battery
        return w[:-3] + "y"
    if len(w) > 4 and w.endswith(("xes", "ches", "shes", "sses")):
        return w[:-2]
    if len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is")):
        return w[:-1]
    return w


def tokens(name, syn=True):
    """Значимые слова по порядку, в единственном числе (rocky -> rock), синонимы - к каноническому слову."""
    out = []
    for w in re.findall(r"[a-z]+", name.lower()):
        if w in STOP or len(w) <= 2:
            continue
        w = ADJ.get(w, stem(w))
        out.append(CANON.get(w, w) if syn else w)
    return out


def words(name, syn=True):
    return set(tokens(name, syn))


# приставка к предмету (замечания 29.09): table with computer / table with lamp - разные вещи при одном главном
# слове. Не после дефиса: wall-mounted lamp - это lamp, а не wall
ATTACH = re.compile(r"(?<![-\w])(with|containing|holding|carrying|mounted|attached|filled|loaded|full of)\b")


def split_name(name):
    """(предмет, приставка): «rack with bottles» -> («rack», «bottles»). Без маркера или с маркером в начале
    (mounted lamp) приставки нет."""
    low = name.lower()
    m = ATTACH.search(low)
    if not m or not tokens(low[:m.start()], False):
        return low, ""
    return low[:m.start()], low[m.end():]


def head(name, syn=True):
    """Главное слово - последнее значимое до приставки (small bush with berries -> bush, rack containing
    bottles -> rack), общие слова пропускаются (wooden barrel -> barrel, storage unit -> storage)."""
    ws = tokens(split_name(name)[0], syn)
    named = [w for w in ws if w not in GENERIC]
    return (named or ws or [""])[-1]


def attachment(name, syn=True):
    """Значимые слова приставки: table with computer monitor -> {computer, monitor}."""
    return {w for w in tokens(split_name(name)[1], syn) if w not in GENERIC}


def attach_state(a, b, syn=True):
    """same - приставки совместимы (обе пусты, общее слово, или приставка одного названа в словах другого:
    bush with berries / berry bush); one_sided - у одного есть приставка, другой о ней молчит (table with
    computer / table); conflict - обе есть и разные (table with computer / table with lamp)."""
    xa, xb = attachment(a, syn), attachment(b, syn)
    if not xa and not xb:
        return "same"
    if xa and xb:
        return "same" if any(_word_match(p, q) for p in xa for q in xb) else "conflict"
    one, other = (xa, words(b, syn)) if xa else (xb, words(a, syn))
    return "same" if any(_word_match(p, q) for p in one for q in other) else "one_sided"


def _word_match(x, y):
    """Слово то же, или одно - конец другого не короче 4 букв (armchair / chair; pod / tripod - нет)."""
    return x == y or any(len(p) >= 4 and len(q) > len(p) and q.endswith(p) for p, q in ((x, y), (y, x)))


def same_thing(a, b, syn=True):
    """Названы ли одним предметом: главные слова совпали, или главное слово одного есть среди слов другого
    (hay bale / bale of hay). Общее прилагательное не в счёт: Crypt Barrel / Crypt Pillar, wooden crate /
    wooden table - разные предметы."""
    ha, hb = head(a, syn), head(b, syn)
    if not ha or not hb:
        return False
    if _word_match(ha, hb):
        return True
    wa, wb = words(a, syn), words(b, syn)
    return any(_word_match(ha, w) for w in wb) and any(_word_match(hb, w) for w in wa)


def verdict(a, b):
    """Сведение двух независимых ответов: agree | synonym | category | conflict | unknown.
      agree    - тот же предмет теми же словами, та же категория и то же решение предмет/рельеф;
      category - тот же предмет, категория разная (crashed plane fuselage: vehicle / debris - спор о рубрике);
      synonym  - тот же смысл только через словарь SYNONYMS (structural pillar / support column);
      conflict - разные предметы (Hay Bale / wood pile, barrel / pillar) или разное решение предмет/рельеф;
      unknown  - хотя бы один ответ UNKNOWN (второй, если назван, - только скрытая догадка).
    Альтернативы в счёт не идут: «бочка» против «колонны, или бочки» - это и есть сомнение.
    Согласие = главное слово то же И приставки совместимы (attach_state): table with computer / table with lamp -
    conflict; приставка у одного, другой о ней молчит (table with computer / table) - synonym, решает человек."""
    if a["proposed_name"] == "UNKNOWN" or b["proposed_name"] == "UNKNOWN":
        return "unknown"
    if a.get("relief_decision", "") != b.get("relief_decision", ""):
        return "conflict"
    na, nb = a["proposed_name"], b["proposed_name"]
    if same_thing(na, nb, syn=False):
        att = attach_state(na, nb, syn=False)
        if att == "same":
            return "agree" if a["proposed_category"] == b["proposed_category"] else "category"
        att = attach_state(na, nb, syn=True)
        return "conflict" if att == "conflict" else "synonym"
    if same_thing(na, nb, syn=True):
        return "conflict" if attach_state(na, nb, syn=True) == "conflict" else "synonym"
    return "conflict"


def agree(a, b):
    """Прежний вид для вызывающих: "full" | "name" | "" (synonym и category - "name")."""
    v = verdict(a, b)
    if v == "unknown":
        return "full" if a["proposed_name"] == b["proposed_name"] else ""
    return {"agree": "full", "category": "name", "synonym": "name"}.get(v, "")


# сколько работы человеку (замечания 30.09) - по сведению двух ответов, а не по числу уверенности модели
REVIEW_LEVELS = ("AUTO_REVIEW_EASY", "HUMAN_REVIEW_LIGHT", "HUMAN_REVIEW_HARD", "UNKNOWN")


def review_level(v, a_name="", b_name=""):
    """EASY - совпали или один смысл через словарь; LIGHT - один предмет, спор о категории или приставка
    у одного из двух; HARD - разные предметы; UNKNOWN - полезной догадки нет."""
    if v == "agree":
        return "AUTO_REVIEW_EASY"
    if v == "synonym":
        return "HUMAN_REVIEW_LIGHT" if attach_state(a_name, b_name, True) == "one_sided" else "AUTO_REVIEW_EASY"
    if v == "category":
        return "HUMAN_REVIEW_LIGHT"
    if v == "conflict":
        return "HUMAN_REVIEW_HARD"
    return "UNKNOWN"


def _cand(x):
    return {k: x.get(k, "") for k in ("proposed_name", "proposed_category", "relief_decision",
                                      "short_description", "proposed_material", "confidence", "ambiguity")}


def reconcile(p):
    """Запись предложения с first/second -> статус, имя и уверенность по правилу RECONCILE_RULE. Модель не
    зовётся: пересчёт всех ответов - секунды. first - ответ a (он же на верхнем уровне: evidence, alternatives,
    picture_alone), second - ответ b."""
    a = dict(p, **p["first"])
    b = dict(p["second"])
    b.setdefault("relief_decision", "")
    v = verdict(a, b)
    out = dict(p, verdict=v, reconcile_rule=RECONCILE_RULE, consistent=v in ("agree", "category", "synonym"),
               candidates=[], model_notes="",
               review_level=review_level(v, a.get("proposed_name", ""), b.get("proposed_name", "")))
    for k in ("proposed_name", "proposed_category", "short_description", "confidence", "ambiguity"):
        out[k] = a.get(k, "")
    out["proposed_material"] = a.get("proposed_material") or p.get("proposed_material", "")
    if v in ("agree", "category", "synonym"):
        out["confidence"] = round(min(float(a["confidence"]), float(b["confidence"])), 2)
        out["status"] = "PROPOSED"
        if v == "category":
            out["confidence"] = min(out["confidence"], NAME_CAP)
            out["ambiguity"] = "; ".join(x for x in ("категория разошлась: %s / %s" % (
                a["proposed_category"], b["proposed_category"]), a.get("ambiguity", "")) if x)
        elif v == "synonym":
            out["confidence"] = min(out["confidence"], SYN_CAP)
            out["status"] = "PROPOSED_AMBIGUOUS"
            out["ambiguity"] = "; ".join(x for x in ("два ответа назвали одно разными словами: %s / %s" % (
                a["proposed_name"], b["proposed_name"]), a.get("ambiguity", "")) if x)
        return out
    # разные предметы или не опознала: имени на карточке нет, догадки - в скрытых candidates (не якорить)
    out["candidates"] = [_cand(x) for x in (a, b) if x.get("proposed_name", "UNKNOWN") != "UNKNOWN"]
    out["model_notes"] = "; ".join(x.get("ambiguity", "") for x in (a, b) if x.get("ambiguity"))
    out.update(proposed_name="UNKNOWN", proposed_category="UNKNOWN", proposed_material="", short_description="",
               confidence=0.0)
    if v == "conflict":
        out["status"] = "REVIEW_REQUIRED"
        out["ambiguity"] = ("два ответа модели - разные предметы (предмет или рельеф - тоже разошлись)"
                            if a.get("relief_decision", "") != b.get("relief_decision", "")
                            else "два ответа модели - разные предметы")
    else:
        out["status"] = "UNKNOWN"
        out["ambiguity"] = "модель не опознала" + (" (один из двух ответов)" if out["candidates"] else "")
    return out


def combine(a, b):
    """Два ответа -> одно предложение. Число уверенности модели не калибровано (прогон 29.09: 0.9 почти
    всему), честный сигнал сомнения - расхождение двух независимых ответов (VILBAN 35: тюк сена /
    поленница, SIETCHDOOM 53: бочка / колонна). Оба ответа хранятся целиком (first, second) - правило
    сведения пересчитывается без модели (reconcile, --reconcile)."""
    out = dict(a, first={k: a.get(k, "") for k in ANSWER_KEYS + ("ambiguity",)},
               second={k: b.get(k, "") for k in ANSWER_KEYS + ("ambiguity",)})
    return reconcile(out)


def ask(imgs, fx, host, model):
    """Два независимых ответа (температура 0.2 и 0.8) и их сведение combine()."""
    a = ask_once(imgs, fx, host, model, 0.2, 1)
    b = ask_once(imgs, fx, host, model, 0.8, 2)
    return combine(a, b)


def ask_once(imgs, fx, host, model, temperature, seed):
    body = {"model": model, "stream": False, "think": False, "format": "json",
            # num_ctx как у caption.py: без него Ollama берёт родной контекст и выносит слои на процессор
            # (R-064), а разный num_ctx у двух клиентов - перезагрузка модели на каждом переключении
            "options": {"temperature": temperature, "seed": seed, "num_predict": 500, "num_ctx": 4096},
            "prompt": ASK.format(facts=facts_text(fx), categories=", ".join(CATEGORIES),
                                 evidence=", ".join(EVIDENCE),
                                 relief=RELIEF if fx["asset_class"] == "object_or_relief" else ""),
            "images": imgs}
    req = urllib.request.Request(host + "/api/generate", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return normalize(json.loads(json.loads(r.read().decode())["response"]), fx)


def ambiguous_relief(p):
    return p.get("asset_class") == "object_or_relief" and (
        p["proposed_name"] == "UNKNOWN" or p["confidence"] < RELIEF_MIN or bool(p["ambiguity"]))


def stats(props, errors):
    """Сводка P1-B, п.6. Источники пересекаются (карта и данные вместе); «только визуально» - ни того, ни другого."""
    ps = [p for p in props.values() if isinstance(p, dict)]
    known = [p for p in ps if p["proposed_name"] != "UNKNOWN"]
    ev = [set(p.get("evidence", [])) for p in known]
    out = {"total processed": len(ps) + len(errors),
           "high confidence": sum(1 for p in known if p["confidence"] >= HIGH),
           "medium confidence": sum(1 for p in known if MEDIUM <= p["confidence"] < HIGH),
           "low confidence": sum(1 for p in known if p["confidence"] < MEDIUM),
           "UNKNOWN": len(ps) - len(known),
           "object/terrain ambiguous": sum(1 for p in ps if ambiguous_relief(p)),
           "errors": len(errors),
           "with map context": sum(1 for e in ev if e & set(MAP_EV)),
           "with MCD/ruleset": sum(1 for e in ev if e & set(DATA_EV)),
           "visual only": sum(1 for e in ev if not e & (set(MAP_EV) | set(DATA_EV))),
           "two answers agree": sum(1 for p in ps if p.get("consistent") is True),
           "two answers disagree": sum(1 for p in ps if p.get("consistent") is False),
           "same name in several assets":sum(n for n in Counter(p["proposed_name"].lower() for p in known).values()
                                              if n > 1)}
    v = Counter(p.get("verdict", "") for p in ps)
    # четыре числа замечаний 29.09 (по сведению двух ответов, правило RECONCILE_RULE)
    out.update({"exact/near agreement": v["agree"] + v["synonym"],
                "  exact (same words)": v["agree"],
                "  near (synonyms, PROPOSED_AMBIGUOUS)": v["synonym"],
                "category-only disagreement": v["category"],
                "true semantic disagreement (REVIEW_REQUIRED)": v["conflict"],
                "UNKNOWN (model did not identify)": v["unknown"],
                "not reconciled (old answers)": v[""]})
    lv = Counter(p.get("review_level", "") for p in ps)
    out.update({"review " + k: lv[k] for k in REVIEW_LEVELS})
    return out


def evidence_group(p):
    """Строка матрицы по тому, на что ответ (a) сказал, что опирался: только картинка, данные (MCD, рулсеты,
    имена наборов), карта (место, соседи) или несколько источников сразу."""
    ev = set(p.get("evidence", []))
    m, d = bool(ev & set(MAP_EV)), bool(ev & set(DATA_EV))
    return "multiple (map + MCD/ruleset)" if m and d else "map-context supported" if m else \
        "MCD/ruleset supported" if d else "visual only"


def matrix(props):
    """Матрица «откуда опора -> чем кончилось сведение»: какой контекст реально помогает модели. Второй срез -
    по тому, что было ДАНО (стоит ли на картах, опознаны ли соседи), а не по тому, что модель назвала."""
    ps = [p for p in props.values() if isinstance(p, dict) and p.get("verdict")]
    cols = ("agree", "synonym", "category", "conflict", "unknown")
    rows = {}
    for p in ps:
        rows.setdefault(evidence_group(p), Counter())[p["verdict"]] += 1
        fx = p.get("facts") or {}
        placed = "given: placed on maps" if fx.get("placed") else "given: not on any map"
        rows.setdefault(placed, Counter())[p["verdict"]] += 1
        nb = "given: named neighbours" if any(n.get("what") for n in fx.get("neighbours", [])) \
            else "given: no named neighbours"
        rows.setdefault(nb, Counter())[p["verdict"]] += 1
    order = ("visual only", "MCD/ruleset supported", "map-context supported", "multiple (map + MCD/ruleset)",
             "given: placed on maps", "given: not on any map", "given: named neighbours", "given: no named neighbours")
    L = ["%-30s %5s %6s %6s %8s %8s %7s %6s" % (("evidence",) + cols + ("total", "agree%"))]
    for r in order:
        c = rows.get(r)
        if not c:
            continue
        n = sum(c.values())
        L.append("%-30s %5d %6d %6d %8d %8d %7d %5.0f%%" % ((r,) + tuple(c[k] for k in cols) + (
            n, 100.0 * (c["agree"] + c["synonym"] + c["category"]) / n)))
    return L


# MCD говорит о предмете сверх «стоит / проходим / броня»: горит, взрывается, светит, открывается, анимирован
MCD_TELLING = ("burns", "explodes", "light_source", "second_state", "animated")


def cohorts(p):
    """Когорты по тому, что было В ЗАПРОСЕ (facts_text), а не по словам модели (замечания 29.09)."""
    fx = p.get("facts") or {}
    m = fx.get("mcd") or {}
    return ["MCD informative" if any(m.get(k) for k in MCD_TELLING) else "MCD generic" if m else "no MCD",
            "map context available" if fx.get("map_example") else "map context unavailable",
            "family context available" if fx.get("family") or fx.get("other_sides")
            else "family context unavailable",
            "named neighbours" if any(n.get("what") for n in fx.get("neighbours", [])) else "no named neighbours"]


def cohort_table(props):
    ps = [p for p in props.values() if isinstance(p, dict) and p.get("verdict")]
    rows = {}
    for p in ps:
        for c in cohorts(p):
            rows.setdefault(c, Counter())[p["verdict"]] += 1
    order = ("MCD informative", "MCD generic", "no MCD", "map context available", "map context unavailable",
             "family context available", "family context unavailable", "named neighbours", "no named neighbours")
    L = ["%-28s %6s %8s %9s %9s %8s" % ("given in prompt", "total", "agree%", "category%", "semantic%", "UNKNOWN%")]
    for r in order:
        c = rows.get(r)
        if not c:
            continue
        n = sum(c.values())
        L.append("%-28s %6d %7.0f%% %8.0f%% %8.0f%% %7.0f%%" % (
            r, n, 100.0 * (c["agree"] + c["synonym"]) / n, 100.0 * c["category"] / n,
            100.0 * c["conflict"] / n, 100.0 * c["unknown"] / n))
    return L


CONFLICT_TYPES = ("object / relief split", "attachment differs", "shared words, same category",
                  "shared words, other category", "no shared words, same category", "no shared words, other category")


def conflict_type(p):
    """Грубый тип расхождения HARD по одним строкам - только для отчёта, сведение от него не зависит.
    «Общие слова» - кандидат в род/вид или вариант одной конструкции (Freighter Wall Corner / wall corner post);
    настоящую смысловую связь (SAME / BROADER_NARROWER / RELATED / DIFFERENT) решал бы отдельный арбитр."""
    a, b = p["first"], p["second"]
    if a.get("relief_decision", "") != b.get("relief_decision", ""):
        return CONFLICT_TYPES[0]
    na, nb = a["proposed_name"], b["proposed_name"]
    if same_thing(na, nb, True):
        return CONFLICT_TYPES[1]
    shared = {w for w in words(na) if w not in GENERIC} & {w for w in words(nb) if w not in GENERIC}
    same_cat = a.get("proposed_category") == b.get("proposed_category")
    return CONFLICT_TYPES[(2 if shared else 4) + (0 if same_cat else 1)]


def conflict_table(props):
    c = Counter(conflict_type(p) for p in props.values()
                if isinstance(p, dict) and p.get("verdict") == "conflict" and p.get("first") and p.get("second"))
    n = sum(c.values())
    if not n:
        return []
    return ["", "HARD by conflict type (strings only): %d" % n] + \
        ["  %-34s %5d  %3.0f%%" % (t, c[t], 100.0 * c[t] / n) for t in CONFLICT_TYPES]


def disagreement_pairs(props, top=30):
    """Частые пары главных слов у расхождений и у синонимов: покрывают ли 20-30 групп большую часть -
    или нужен слой смысловой нормализации, а не словарь (замечания 29.09)."""
    L = []
    for v, title in (("conflict", "semantic disagreement"), ("synonym", "near (synonyms / one-sided attachment)")):
        pairs = Counter()
        for p in props.values():
            if isinstance(p, dict) and p.get("verdict") == v and p.get("first") and p.get("second"):
                pairs[tuple(sorted((head(p["first"]["proposed_name"], False),
                                    head(p["second"]["proposed_name"], False))))] += 1
        n = sum(pairs.values())
        if not n:
            continue
        best = pairs.most_common(top)
        L += ["", "%s: %d, pairs %d; top 20 cover %.0f%%, top %d cover %.0f%%" % (
            title, n, len(pairs), 100.0 * sum(c for _p, c in pairs.most_common(20)) / n, top,
            100.0 * sum(c for _p, c in best) / n)]
        L += ["  %3d  %s / %s" % (c, x, y) for (x, y), c in best]
    return L


def save(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding=ENC) as f:
        json.dump(data, f, ensure_ascii=False, indent=0)
    os.replace(tmp, path)


def load(path):
    if os.path.exists(path):
        with open(path, encoding=ENC) as f:
            return json.load(f)
    return {}


def running_proposer():
    """pid другого процесса identity_propose с моделью (не --stats и не --reconcile), или None."""
    try:
        import psutil
    except ImportError:
        raise SystemExit("нужен psutil (py -3.13): без него не проверить, идёт ли прогон")
    me = os.getpid()
    for pr in psutil.process_iter(["pid", "cmdline"]):
        cmd = " ".join(pr.info.get("cmdline") or [])
        if pr.info["pid"] != me and "identity_propose" in cmd and "--reconcile" not in cmd \
                and "--stats" not in cmd and "python" in cmd.lower():
            return pr.info["pid"]
    return None


def print_stats(props, errors, path):
    s = stats(props, errors)
    lines = ["%-46s %d" % (k, v) for k, v in s.items()] + [""] + matrix(props) + [""] + cohort_table(props) + \
        conflict_table(props) + disagreement_pairs(props)
    print("\n".join(lines))
    with open(path, "w", encoding=ENC) as f:
        f.write("identity_propose %s\n" % time.strftime("%Y-%m-%d %H:%M"))
        f.write("\n".join(lines) + "\n")
    print("-> %s" % path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--host", default="http://127.0.0.1:11434")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--status", default="NO_PROPOSAL", help="чьё опознание спрашивать (через запятую)")
    ap.add_argument("--keys", default="", help="только эти ассеты (через запятую)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true", help="напечатать факты и картинки, модель не звать")
    ap.add_argument("--stats", action="store_true", help="только сводка по готовым ответам")
    ap.add_argument("--reconcile", action="store_true",
                    help="пересвести готовые пары ответов по текущему правилу (verdict/reconcile), модель не звать")
    a = ap.parse_args()
    for s in (sys.stdout, sys.stderr):
        s.reconfigure(encoding="utf-8", errors="replace")
    err_path = os.path.splitext(a.out)[0] + "_errors.json"
    stats_path = os.path.splitext(a.out)[0] + "_stats.txt"
    props, errors = load(a.out), load(err_path)
    if a.reconcile:
        other = running_proposer()
        if other:
            # идущий прогон держит свои ответы в памяти и перепишет файл - пересчёт потерялся бы
            raise SystemExit("идёт прогон identity_propose (pid %s): пересчёт после его конца" % other)
        before = Counter(p.get("verdict", "") for p in props.values() if isinstance(p, dict))
        n = 0
        for k, p in list(props.items()):
            if isinstance(p, dict) and isinstance(p.get("first"), dict) and isinstance(p.get("second"), dict):
                props[k] = reconcile(p)
                n += 1
        save(a.out, props)
        after = Counter(p.get("verdict", "") for p in props.values() if isinstance(p, dict))
        print("пересведено %d пар ответов (правило %d); без пары (старые ответы): %d" % (
            n, RECONCILE_RULE, len(props) - n))
        print("было: %s\nстало: %s" % (dict(before), dict(after)))
        return print_stats(props, errors, stats_path)
    if a.stats:
        return print_stats(props, errors, stats_path)
    import review_server as rs
    with open(rs.ITEMS, encoding=ENC) as f:
        items = {it["rank"]: it for it in json.load(f)}
    with open(rs.IDENTITY, encoding=ENC, newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))
    with open(FAMS, encoding=ENC) as f:
        fams = {fm["family_id"]: fm for fm in json.load(f)}
    want = set(a.status.split(","))
    keys = {k.strip().upper() for k in a.keys.split(",") if k.strip()}
    # ответ модели сам делает строку AGENT_PROPOSED - по статусу она из отбора выпала бы и осталась с
    # ответом прежнего запроса; предложение модели без решения человека остаётся в отборе
    mine = lambda r: r["asset_id"] in props and (
        r["status"] == "REVIEW_REQUIRED" or
        r["status"] == "AGENT_PROPOSED" and r.get("proposed_source", "").startswith("agent_model"))
    todo = [r for r in sorted(rows, key=lambda r: int(r["rank"]))
            if (r["asset_id"] in keys if keys else r["status"] in want or mine(r))
            and props.get(r["asset_id"], {}).get("ask_rev") != ask_rev()]     # ответ прежнего запроса - заново
    if a.limit:
        todo = todo[:a.limit]
    print("спросить: %d (%s), уже есть ответов %d" % (len(todo), a.keys or "статус " + a.status, len(props)),
          flush=True)
    ctx = Context(items, fams, {r["asset_id"]: r for r in rows})

    class Holder:
        pass
    holder = Holder()
    holder.items = items
    rend = rs.Renders(holder)
    t0, done = time.time(), 0
    for n, r in enumerate(todo, 1):
        it = items[int(r["rank"])]
        try:
            fx = ctx.facts(r, it)
            imgs = pictures(rend, int(r["rank"]), fx, ctx.by_key)
            if not imgs:
                raise ValueError("нет картинки ассета")
            if a.dry_run:
                print("== %s: картинок %d\n%s" % (r["asset_id"], len(imgs), facts_text(fx)), flush=True)
                continue
            ans = ask(imgs, fx, a.host, a.model)
        except Exception as e:                                           # noqa: BLE001
            errors[r["asset_id"]] = {"error": str(e)[:300], "when": time.strftime("%Y-%m-%dT%H:%M:%S")}
            print("  %s: ОШИБКА %s" % (r["asset_id"], e), flush=True)
            if not a.dry_run:
                save(err_path, errors)
            continue
        text = facts_text(fx)
        ans.update(model=a.model, ask_rev=ask_rev(), when=time.strftime("%Y-%m-%dT%H:%M:%S"), facts=fx,
                   facts_hash=hashlib.sha256(text.encode()).hexdigest()[:12])
        props[r["asset_id"]] = ans
        errors.pop(r["asset_id"], None)
        done += 1
        if done % 5 == 0:
            save(a.out, props)
            save(err_path, errors)
        el = time.time() - t0
        print("  %d/%d %-18s %.2f %-24s %-28s %s  | %.1f с/шт, осталось ~%d мин" % (
            n, len(todo), r["asset_id"], ans["confidence"], ans["proposed_category"][:24], ans["proposed_name"][:28],
            ",".join(ans["evidence"]), el / n, (len(todo) - n) * el / n / 60), flush=True)
    if a.dry_run:
        return None
    save(a.out, props)
    save(err_path, errors)
    print("готово: новых ответов %d, всего %d" % (done, len(props)))
    print_stats(props, errors, stats_path)
    return None


if __name__ == "__main__":
    main()
