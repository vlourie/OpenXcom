#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Семантический арбитр опознания (Pipeline v2, P1-C): второй проход только по HUMAN_REVIEW_HARD.

Предлагатель (identity_propose, #274) дал каждому ассету два независимых ответа; у 1133 из 1987 они назвали
разные предметы (HARD). Арбитр НЕ придумывает третье имя: смотрит на кадр, место на карте, MCD и семейство и
выбирает между готовыми догадками A и B - A / B / NEITHER / CANNOT_TELL, плюс связь A с B: SAME /
BROADER_NARROWER / RELATED_BUT_DIFFERENT / DIFFERENT. Опознание он не подтверждает никогда: лучшее, что он может,
- перевести ассет из HARD в LIGHT (карточку, где человеку хватит одного взгляда), подтверждает Vitali.

Переход (специалист 30.09, не меняется):
    A/B + SAME или A/B + BROADER_NARROWER  -> HUMAN_REVIEW_LIGHT
    RELATED_BUT_DIFFERENT, A/B + DIFFERENT -> остаётся HUMAN_REVIEW_HARD
    NEITHER                                -> HUMAN_REVIEW_HARD
    CANNOT_TELL, ответ не по форме         -> HUMAN_REVIEW_HARD (арбитр не знает)

Приёмка - контрольные 100 HARD до любого массового прохода: по 25 на каждый из четырёх типов расхождения
(conflict_type: общие слова или нет x категория та же или нет), внутри четверти - разные наборы PCK, террейны и
пары категорий. Сотня ЗАМОРАЖИВАЕТСЯ до запуска арбитра (freeze): состав, догадки A/B, класс, байты всех
входных картинок и текста - в arbiter-control-100-<хэш>.json только для чтения, картинки - рядом; run сверяет
sha256 входа перед каждым вопросом, поменять тест после просмотра ответов незаметно нельзя. Главная мера -
FALSE_CONFIDENT: арбитр выбрал A или B, а верно другое, NEITHER или вообще другой предмет (правда - разметка
Vitali, truth.tsv). Пороги: до 5 процентов хорошо, 5-10 дорабатывать, больше 10 массово не применять; много
CANNOT_TELL - допустимо.

Что видит арбитр (и только это): кадр ассета x4 nearest, вырез карты с рамкой, полосу семейства и других боков
(подписи - только связь, без имён наборов), данные MCD (тип записи, проходимость, броня, горит, взрывается,
свет, обзор, разрушение, второе состояние, анимация, объём по вокселям, клетки составного) и две догадки.
Имён наборов, террейнов, карт и соседей нет: они подсказывают ответ словами, а не картинкой.

    py -3.13 tools/hdart/arbiter.py freeze                     (без модели: отбор, картинки, снимок)
    py -3.13 tools/hdart/arbiter.py freeze --holdout           (вторая закрытая сотня без ассетов контрольной)
    py -3.13 tools/hdart/arbiter.py run <снимок> --dry-run     (без модели: входы и запрос первого)
    py -3 tools/gpuq.py add --name arbiter-control -- C:/Python313/python.exe E:/OpenXCom/tools/hdart/arbiter.py run <снимок>
    py -3.13 tools/hdart/arbiter.py report <снимок>            (без модели: распределения, FALSE_CONFIDENT по truth.tsv)
    py -3.13 tools/hdart/arbiter.py label <снимок>             (страница разметки правды вслепую, 127.0.0.1:8775)
"""
import argparse
import csv
import hashlib
import io
import json
import os
import random
import sys
import time
import urllib.request
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import identity_propose as ip              # noqa: E402

ENC = "utf-8-sig"
ARB = os.path.join(ROOT, "art", "objects", "discovery", "arbiter")
CLASSES = ip.CONFLICT_TYPES[2:6]           # четыре типа HARD: общие слова да/нет x категория та же/другая
PER_CLASS = 25
SELECT_SALT = "arbiter-control-100:1"      # порядок отбора; менять - значит другая сотня
HOLDOUT_SALT = "arbiter-holdout-100:1"     # вторая, закрытая сотня (freeze --holdout)
DECISIONS = ("A", "B", "NEITHER", "CANNOT_TELL")
RELATIONS = ("SAME", "BROADER_NARROWER", "RELATED_BUT_DIFFERENT", "DIFFERENT")
EVIDENCE = ("sprite", "map_crop", "mcd", "family_views")
TRUTHS = ("A", "B", "BOTH", "NEITHER", "CANNOT_TELL")   # BOTH - A и B здесь одно и то же, годится любая
LIGHT, HARD = "HUMAN_REVIEW_LIGHT", "HUMAN_REVIEW_HARD"
MODEL = ip.MODEL
OPTIONS = {"temperature": 0.0, "seed": 1, "num_predict": 300, "num_ctx": 4096}   # num_ctx - R-064
THRESHOLDS = ((0.05, "хорошо"), (0.10, "дорабатывать"), (1.01, "массово не применять"))
MODEL_SOURCES = {"codex": "CODEX_BLIND", "claude": "CLAUDE_BLIND"}   # who -> truth_source; остальные - HUMAN_<WHO>

ASK = """You are a referee. Two earlier guesses disagree about what ONE object from the 1994 isometric game
X-COM (mod X-Piratez) is. Decide between them. Do not invent a new name.
Picture 1: the object itself - the original pixel art enlarged 4x with nearest neighbour (no changes);
the dark grey around it is empty background.
Picture 2 (if given): the object in its place on a real game map, marked with a red frame; other things there
are context, not the answer.
Picture 3 (if given): other members of its family (recolours, mirrors, possible other sides), each labelled
with its relation.
Game data (MCD) about the object:
{facts}
Candidate A: {a}
Candidate B: {b}
Answer strictly as JSON with exactly these keys:
"decision": "A" if candidate A is what the pictures show and B fits clearly worse; "B" likewise for B;
"NEITHER" if the pictures clearly show something that is neither A nor B; "CANNOT_TELL" if the pictures and
data do not settle it. Picking A or B while unsure is an error; CANNOT_TELL is an acceptable answer;
"relation": how A and B relate as names of this object: "SAME" (the same thing in other words),
"BROADER_NARROWER" (one is a more general or a more specific name of the other), "RELATED_BUT_DIFFERENT"
(related but different objects or parts, e.g. a wall and a pillar), "DIFFERENT" (unrelated objects);
"reason_short": at most 25 English words why; do not propose another name;
"evidence_used": a list of what you really used, from: sprite, map_crop, mcd, family_views."""


def h12(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:12]


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha256_file(p):
    with open(p, "rb") as f:
        return sha256_bytes(f.read())


def arb_rev(model=MODEL):
    """Версия арбитра: текст запроса, модель, параметры. Ответ другой версии в сводку не идёт."""
    return h12({"ask": ASK, "model": model, "options": OPTIONS, "decisions": DECISIONS, "relations": RELATIONS})


def save_json(path, data, readonly=False):
    if os.path.exists(path) and readonly:
        os.chmod(path, 0o644)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding=ENC) as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)
    if readonly:
        os.chmod(path, 0o444)


def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding=ENC) as f:
        return json.load(f)


# ------------------------------------------------------------------ вход арбитра

def arb_facts(fx):
    """Только MCD, объём, клетки составного и семейство - без имён наборов, террейнов, карт и соседей."""
    L = []
    if fx["cells"] > 1:
        L.append("- one object of %d map cells (composite), cell offsets %s" % (fx["cells"], fx["layout"]))
    m = fx["mcd"]
    if m:
        bits = [m["tile_type"], "walkable" if m["walkable"] else "blocks movement",
                "armor %d" % m["armor"], "burns" if m["burns"] else "does not burn"]
        bits += [b for b, on in (("explodes when destroyed", m["explodes"]), ("emits light", m["light_source"]),
                                 ("blocks line of sight", m["blocks_sight"]),
                                 ("has a destroyed version", m["destroyed_version"]),
                                 ("has a second state (opens, switches)", m["second_state"]),
                                 ("animated", m["animated"])) if on]
        L.append("- MCD: " + ", ".join(bits))
        L.append("- volume: %d of 12 height layers, bottom layer fills %d%% of the cell; sprite %dx%d px" % (
            m["height_layers"], m["bottom_fill"] * 100, m["sprite_w"], m["sprite_h"]))
    else:
        L.append("- MCD: no record found")
    rel = Counter(x["relation"] or "variant" for x in fx["family"]) + Counter("possible other side" for _ in fx["other_sides"])
    if rel:
        L.append("- family: %s" % ", ".join("%d %s" % (n, r) for r, n in sorted(rel.items())))
    if fx["asset_class"] == "object_or_relief":
        L.append("- game data cannot tell if this is an object or terrain relief")
    return "\n".join(L)


def family_strip(rend, fx, items_by_key):
    """Полоса семейства как у предлагателя, но подпись - только связь, без ключа набора."""
    from PIL import Image, ImageDraw
    cells = []
    for x in (fx["family"] + fx["other_sides"])[:ip.STRIP_MAX]:
        it = items_by_key.get(x["key"].upper())
        raw = rend.asset(it["rank"]) if it else None
        if raw is None:
            continue
        im = Image.open(io.BytesIO(raw)).convert("RGB")
        lab = Image.new("RGB", (max(im.width, 150), im.height + 18), (20, 20, 24))
        lab.paste(im, (0, 18))
        ImageDraw.Draw(lab).text((3, 3), x["relation"] or "variant", fill=(255, 220, 0))
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


def png(im):
    b = io.BytesIO()
    im.convert("RGB").save(b, "PNG")
    return b.getvalue()


def fit(im, side=ip.CTX_SIDE):
    from PIL import Image
    k = side / max(im.size)
    if k < 1:
        im = im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))), Image.LANCZOS)
    return im


def candidate(x):
    """Догадка словами для запроса: имя, категория, описание."""
    t = "%s (%s)" % (x["proposed_name"], x.get("proposed_category", ""))
    if x.get("short_description") and x["short_description"] != x["proposed_name"]:
        t += " - " + x["short_description"]
    return t


# ------------------------------------------------------------------ отбор и заморозка

def hard_pool(props, rows):
    """HARD без решения человека: оба ответа есть, названы разные предметы, строка всё ещё REVIEW_REQUIRED."""
    status = {r["asset_id"]: r for r in rows}
    out = {c: [] for c in CLASSES}
    for aid, p in props.items():
        if not isinstance(p, dict) or p.get("verdict") != "conflict" or not p.get("first") or not p.get("second"):
            continue
        if status.get(aid, {}).get("status") != "REVIEW_REQUIRED":
            continue
        a, b = p["first"], p["second"]
        if "UNKNOWN" in (a.get("proposed_name"), b.get("proposed_name")):
            continue
        if a["proposed_name"].strip().lower() == b["proposed_name"].strip().lower():
            continue
        c = ip.conflict_type(p)
        if c in out:
            out[c].append(aid)
    return out


def pick(pool, attrs, n=PER_CLASS, global_sets=None, set_cap=3, salt=SELECT_SALT):
    """n ассетов из пула в порядке соли, жадно на разнообразие: сначала новый набор PCK, новый террейн и новая
    пара категорий, потом ограничения ослабляются. global_sets - счёт наборов по всей сотне (не больше set_cap)."""
    order = sorted(pool, key=lambda a: hashlib.sha1((salt + a).encode()).hexdigest())
    got, sets, terr, cats = [], Counter(), set(), set()
    global_sets = global_sets if global_sets is not None else Counter()
    for set_lim, need_terr, need_cat in ((1, True, True), (1, True, False), (1, False, False),
                                         (2, False, False), (set_cap, False, False), (99, False, False)):
        for a in order:
            if len(got) >= n:
                break
            if a in got:
                continue
            s, t, c = attrs[a]
            if sets[s] >= set_lim or (set_lim < 99 and global_sets[s] >= set_cap):
                continue
            if need_terr and t in terr or need_cat and c in cats:
                continue
            got.append(a)
            sets[s] += 1
            global_sets[s] += 1
            terr.add(t)
            cats.add(c)
    return got


def freeze(out_root=ARB, salt=SELECT_SALT, prefix="arbiter-control-100", exclude=()):
    """Заморозить сотню. Вторая закрытая сотня (holdout, замечание Codex 30.09) - своя соль, свой префикс и
    exclude: снимки, чьи ассеты в неё не попадают; размечается до первого взгляда на ответы арбитра."""
    import review_server as rs
    taken = set()
    for p in exclude:
        taken |= {x["asset_id"] for x in check_snapshot(p)[0]["items"]}
    props = ip.load(ip.OUT)
    with open(rs.ITEMS, encoding=ENC) as f:
        items = {it["rank"]: it for it in json.load(f)}
    with open(rs.IDENTITY, encoding=ENC, newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))
    with open(ip.FAMS, encoding=ENC) as f:
        fams = {fm["family_id"]: fm for fm in json.load(f)}
    by_id = {r["asset_id"]: r for r in rows}
    pool = {c: [a for a in v if a not in taken] for c, v in hard_pool(props, rows).items()}
    print("HARD без решения человека%s: %s" % (" (без %d из прежних снимков)" % len(taken) if taken else "",
                                               ", ".join("%s %d" % (c, len(v)) for c, v in pool.items())), flush=True)

    def attrs_of(aid):
        it = items[int(by_id[aid]["rank"])]
        p = props[aid]
        return (it["src"][0].split(":")[0].upper(), (it.get("map") or "?/").split("/")[0].upper(),
                tuple(sorted((p["first"].get("proposed_category", ""), p["second"].get("proposed_category", "")))))
    attrs = {a: attrs_of(a) for v in pool.values() for a in v}
    gsets = Counter()
    chosen = {c: pick(pool[c], attrs, PER_CLASS, gsets, salt=salt) for c in CLASSES}
    short = [c for c in CLASSES if len(chosen[c]) < PER_CLASS]
    if short:
        raise SystemExit("в классах %s меньше %d HARD - сотню не собрать" % (short, PER_CLASS))

    ctx = ip.Context(items, fams, by_id)

    class Holder:
        pass
    holder = Holder()
    holder.items = items
    tmp_cache = os.path.join(out_root, "_render_cache")
    rs.CACHE = tmp_cache                      # свежий рендер, не кэш страницы проверки (ранги могли сдвинуться)
    rend = rs.Renders(holder)
    recs = []
    from PIL import Image
    for c in CLASSES:
        for aid in chosen[c]:
            r = by_id[aid]
            it = items[int(r["rank"])]
            p = props[aid]
            fx = ctx.facts(r, it)
            a, b = sorted((p["first"], p["second"]), key=lambda x: x["proposed_name"].strip().lower())
            pics = {}
            raw = rend.asset(int(r["rank"]))
            if raw is None:
                raise SystemExit("%s: нет кадра ассета" % aid)
            pics["sprite"] = png(Image.open(io.BytesIO(raw)))
            raw = rend.context(int(r["rank"]))
            if raw is not None:
                pics["map_crop"] = png(fit(Image.open(io.BytesIO(raw)).convert("RGB")))
            st = family_strip(rend, fx, ctx.by_key)
            if st is not None:
                pics["family_views"] = png(fit(st))
            facts = arb_facts(fx)
            recs.append({"asset_id": aid, "rank": int(r["rank"]), "class": c,
                         "A": {k: a.get(k, "") for k in ("proposed_name", "proposed_category", "short_description")},
                         "B": {k: b.get(k, "") for k in ("proposed_name", "proposed_category", "short_description")},
                         "a_is": "first" if a is p["first"] else "second",
                         "tileset": attrs[aid][0], "terrain": attrs[aid][1], "categories": list(attrs[aid][2]),
                         "facts": facts,
                         "inputs": dict({k: sha256_bytes(v) for k, v in pics.items()},
                                        facts=sha256_bytes(facts.encode("utf-8"))),
                         "_pics": pics,
                         "source": {"ask_rev": p.get("ask_rev"), "facts_hash": p.get("facts_hash"),
                                    "identity_rev": r.get("identity_rev", ""), "status": r["status"]}})
    body = [{k: v for k, v in x.items() if k != "_pics"} for x in recs]
    sid = h12({"salt": salt, "items": body})
    name = "%s-%s" % (prefix, sid)
    d = os.path.join(out_root, name)
    os.makedirs(os.path.join(d, "inputs"), exist_ok=True)
    for x in recs:
        for k, v in x["_pics"].items():
            p = os.path.join(d, "inputs", "%s_%s.png" % (x["asset_id"].replace(":", "_"), k))
            with open(p, "wb") as f:
                f.write(v)
            os.chmod(p, 0o444)
    snap = {"snapshot_id": name, "created": time.strftime("%Y-%m-%dT%H:%M:%S"), "select_salt": salt,
            "excluded": {os.path.basename(p): len(check_snapshot(p)[0]["items"]) for p in exclude},
            "per_class": PER_CLASS, "classes": list(CLASSES),
            "pool": {c: len(v) for c, v in pool.items()},
            "sources": {"proposals": sha256_file(ip.OUT), "identity": sha256_file(rs.IDENTITY),
                        "items": sha256_file(rs.ITEMS)},
            "diversity": {c: {"tilesets": len({attrs[a][0] for a in chosen[c]}),
                              "terrains": len({attrs[a][1] for a in chosen[c]}),
                              "category_pairs": len({attrs[a][2] for a in chosen[c]})} for c in CLASSES},
            "items": body}
    snap["items_hash"] = h12(body)
    path = os.path.join(out_root, name + ".json")
    save_json(path, snap, readonly=True)
    print("снимок %s: %d ассетов" % (path, len(body)))
    for c in CLASSES:
        dv = snap["diversity"][c]
        print("  %-32s пул %4d  наборов %2d  террейнов %2d  пар категорий %2d" % (
            c, len(pool[c]), dv["tilesets"], dv["terrains"], dv["category_pairs"]))
    return path


# ------------------------------------------------------------------ вопрос и ответ

def check_snapshot(path):
    snap = load_json(path)
    if snap is None:
        raise SystemExit("нет снимка %s" % path)
    if h12(snap["items"]) != snap["items_hash"]:
        raise SystemExit("снимок правили после заморозки (items_hash) - не запускаю")
    return snap, os.path.join(os.path.dirname(path), snap["snapshot_id"])


def inputs_of(x, d):
    """Картинки ассета из снимка, с проверкой sha256; порядок - sprite, map_crop, family_views."""
    out = []
    for k in EVIDENCE:
        if k == "mcd" or k not in x["inputs"]:
            continue
        p = os.path.join(d, "inputs", "%s_%s.png" % (x["asset_id"].replace(":", "_"), k))
        with open(p, "rb") as f:
            b = f.read()
        if sha256_bytes(b) != x["inputs"][k]:
            raise SystemExit("%s: %s не совпадает со снимком - не спрашиваю" % (x["asset_id"], k))
        out.append(b)
    if sha256_bytes(x["facts"].encode("utf-8")) != x["inputs"]["facts"]:
        raise SystemExit("%s: факты не совпадают со снимком" % x["asset_id"])
    return out


def prompt_of(x):
    return ASK.format(facts=x["facts"], a=candidate(x["A"]), b=candidate(x["B"]))


def normalize(d):
    """Ответ модели -> четыре поля строго по форме; не по форме - INVALID (идёт как не знаю)."""
    out = {"decision": str(d.get("decision", "")).strip().upper().replace(" ", "_"),
           "relation": str(d.get("relation", "")).strip().upper().replace(" ", "_").replace("/", "_"),
           "reason_short": str(d.get("reason_short", "")).strip()[:300],
           "evidence_used": [e for e in d.get("evidence_used", []) if e in EVIDENCE]
           if isinstance(d.get("evidence_used"), list) else []}
    bad = [k for k, ok in (("decision", out["decision"] in DECISIONS), ("relation", out["relation"] in RELATIONS)) if not ok]
    out["valid"] = not bad
    if bad:
        out["invalid"] = bad
    return out


def route(ans):
    """Куда ассет ушёл бы по ответу арбитра. CONFIRMED - никогда."""
    if ans.get("valid") and ans["decision"] in ("A", "B") and ans["relation"] in ("SAME", "BROADER_NARROWER"):
        return LIGHT
    return HARD


def ask(x, imgs, host, model):
    import base64
    body = {"model": model, "stream": False, "think": False, "format": "json", "options": OPTIONS,
            "prompt": prompt_of(x), "images": [base64.b64encode(b).decode() for b in imgs]}
    req = urllib.request.Request(host + "/api/generate", json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        raw = json.loads(r.read().decode())["response"]
    try:
        d = json.loads(raw)
    except ValueError:
        d = {}
    ans = normalize(d if isinstance(d, dict) else {})
    ans["raw"] = raw[:800]
    return ans


def run(path, host="http://127.0.0.1:11434", model=MODEL, limit=0, dry_run=False):
    snap, d = check_snapshot(path)
    rev = arb_rev(model)
    rd = os.path.join(d, "runs", rev)
    os.makedirs(rd, exist_ok=True)
    ans_path = os.path.join(rd, "answers.json")
    answers = load_json(ans_path, {})
    todo = [x for x in snap["items"] if x["asset_id"] not in answers]
    if limit:
        todo = todo[:limit]
    print("арбитр %s, модель %s: спросить %d, уже есть %d" % (rev, model, len(todo), len(answers)), flush=True)
    t0 = time.time()
    for n, x in enumerate(todo, 1):
        imgs = inputs_of(x, d)
        if dry_run:
            print("== %s [%s] картинок %d\n%s" % (x["asset_id"], x["class"], len(imgs), prompt_of(x)), flush=True)
            if n >= 1:
                break
            continue
        try:
            ans = ask(x, imgs, host, model)
        except Exception as e:                                          # noqa: BLE001
            print("  %s: ОШИБКА %s" % (x["asset_id"], str(e)[:200]), flush=True)
            continue
        ans.update(arb_rev=rev, model=model, when=time.strftime("%Y-%m-%dT%H:%M:%S"),
                   route=route(ans), inputs=x["inputs"])
        answers[x["asset_id"]] = ans
        save_json(ans_path, answers)
        el = time.time() - t0
        print("  %d/%d %-18s %-12s %-22s -> %s  | %.1f с/шт, осталось ~%d мин" % (
            n, len(todo), x["asset_id"], ans["decision"] or "?", ans["relation"] or "?", ans["route"], el / n,
            (len(todo) - n) * el / n / 60), flush=True)
    if not dry_run:
        meta = {"arb_rev": rev, "model": model, "options": OPTIONS, "ask_sha256": sha256_bytes(ASK.encode("utf-8")),
                "snapshot": snap["snapshot_id"], "items_hash": snap["items_hash"], "answers": len(answers)}
        save_json(os.path.join(rd, "run.json"), meta)
        report(path, rev)
    return 0


# ------------------------------------------------------------------ сводка

def truth_source(who):
    """Источник правды словом (специалист 30.09): разметка модели - не человека, и это видно в каждой сводке."""
    w = (who or "").strip()
    return MODEL_SOURCES.get(w.lower()) or "HUMAN_" + (w.upper() or "UNKNOWN")


def load_truth(d):
    """truth.tsv рядом со снимком: asset_id, truth (A/B/BOTH/NEITHER/CANNOT_TELL), who, truth_source, when, note.
    Строки без truth_source (записаны до 30.09) получают его по who."""
    p = os.path.join(d, "truth.tsv")
    if not os.path.exists(p):
        return {}
    with open(p, encoding=ENC, newline="") as f:
        out = {r["asset_id"]: r for r in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE)
               if r.get("truth", "").strip().upper() in TRUTHS}
    for r in out.values():
        r["truth_source"] = r.get("truth_source") or truth_source(r.get("who"))
    return out


def false_confident(ans, truth):
    """Ложно-уверенный выбор: арбитр выбрал A или B, а правда - другое, NEITHER или другой предмет.
    None - сверить нельзя (разметки нет или человек сам не знает)."""
    if not ans.get("valid") or ans["decision"] not in ("A", "B"):
        return False
    t = (truth or {}).get("truth", "").strip().upper()
    if t in ("", "CANNOT_TELL"):
        return None
    return t not in (ans["decision"], "BOTH")


def verdict_of(rate):
    return next(v for lim, v in THRESHOLDS if rate <= lim)


OUTCOMES = ("correct", "false_confident", "wrong_uncertain", "picked_human_unsure", "invalid", "unlabeled")


def outcome(ans, truth):
    """Исход ответа против правды (таблица специалиста 30.09):
    correct - выбор совпал (A/B при той же правде или BOTH; NEITHER при NEITHER; CANNOT_TELL при CANNOT_TELL);
    false_confident - выбрал A/B, а правда другая догадка или NEITHER;
    wrong_uncertain - отказался (NEITHER / CANNOT_TELL), а правда другая: ошибка, но безопасная - ассет остаётся HARD;
    picked_human_unsure - выбрал A/B, а человек сам сказал CANNOT_TELL (не сверяется);
    invalid - ответ не по форме; unlabeled - правды нет."""
    if not ans or not ans.get("valid"):
        return "invalid"
    t = (truth or {}).get("truth", "").strip().upper()
    if not t:
        return "unlabeled"
    dec = ans["decision"]
    if dec in ("A", "B"):
        if t == "CANNOT_TELL":
            return "picked_human_unsure"
        return "correct" if t in (dec, "BOTH") else "false_confident"
    return "correct" if dec == t else "wrong_uncertain"


def summary_text(per):
    """Сводка в форме, которую просил специалист: TOTAL и те же строки по четырём классам."""
    pct = lambda v: "-" if v is None else "%.1f %%" % (100 * v)
    L = []
    for c in ("ALL",) + CLASSES:
        k = per[c]
        L += ["TOTAL" if c == "ALL" else c.upper(),
              "labeled: %d/%d" % (k["truth"], k["n"]),
              "truth_source: " + (", ".join("%s %d" % kv for kv in sorted(k["truth_sources"].items())) or "-"),
              "",
              "truth:"] + ["%s %d" % (t, k["truth_" + t]) for t in TRUTHS] + [
              "",
              "arbiter:",
              "correct %d" % k["out_correct"],
              "FALSE_CONFIDENT %d" % k["out_false_confident"],
              "wrong_but_declined %d" % k["out_wrong_uncertain"],
              "picked_while_human_unknown %d" % k["out_picked_human_unsure"],
              "invalid %d" % k["out_invalid"],
              "",
              "choice_accuracy %s" % pct(k["choice_accuracy"]),
              "FALSE_CONFIDENT_total_pct %s" % pct(k["fc_total_pct"]),
              "FALSE_CONFIDENT_labeled_pct %s" % pct(k["fc_labeled_pct"]),
              "B_pick_rate %s" % pct(k["b_preference"]),
              "B_truth_rate %s" % pct(k["truth_b_share"]),
              "",
              "FALSE_CONFIDENT_BY_CHOICE:"] + [
              "%s %d of %d verified picks (%s)" % (c, v["false_confident"], v["verified_picks"], pct(v["rate"]))
              for c, v in k["false_confident_by_choice"].items()] + [
              "",
              "FALSE_CONFIDENT_BY_RELATION:"] + ["%s %d" % (r, k["fc_rel_" + r]) for r in RELATIONS] + [
              "",
              "FALSE_CONFIDENT_SHARED_WORDS %d" % k["fc_shared_words"],
              "FALSE_CONFIDENT_NO_SHARED_WORDS %d" % k["fc_no_shared_words"],
              "", ""]
    L.append("arbiter - только размеченные карточки, сумма строки = размечено. total_pct - FALSE_CONFIDENT от всех n "
             "класса, labeled_pct - от размеченных; при 100/100 совпадают. verified picks - выборы буквы, где у "
             "человека есть ответ (не CANNOT_TELL).")
    return "\n".join(L)


def report(path, rev=None):
    snap, d = check_snapshot(path)
    rev = rev or arb_rev()
    rd = os.path.join(d, "runs", rev)
    answers = load_json(os.path.join(rd, "answers.json"), {})
    truth = load_truth(d)
    items = snap["items"]
    rows, per = [], {c: Counter() for c in CLASSES + ("ALL",)}
    for x in items:
        a = answers.get(x["asset_id"])
        t = truth.get(x["asset_id"])
        fc = false_confident(a, t) if a else None
        for c in (x["class"], "ALL"):
            k = per[c]
            k["n"] += 1
            if a is None:
                k["no_answer"] += 1
                continue
            k["answered"] += 1
            k["dec_" + (a["decision"] if a.get("valid") else "INVALID")] += 1
            if a.get("valid"):
                k["rel_" + a["relation"]] += 1
            k[a["route"]] += 1
            if t:
                k["truth"] += 1
                k["truth_" + t["truth"].strip().upper()] += 1
                k["out_" + outcome(a, t)] += 1
                k["src_" + t["truth_source"]] += 1
            if fc is True:
                k["false_confident"] += 1
                k["fc_rel_" + a["relation"]] += 1          # аналитика: с какой связью арбитр ошибался уверенно
                k["fc_shared_words" if x["class"].startswith("shared") else "fc_no_shared_words"] += 1
                k["fc_choice_" + a["decision"]] += 1       # ошибки на букве: позиционный перекос или нет
            if a.get("valid") and a["decision"] in ("A", "B"):
                if fc is None:
                    k["picked_unverified"] += 1
                else:
                    k["verified_choice_" + a["decision"]] += 1  # выборы этой буквы, которые сверяются с правдой
        rows.append({"asset_id": x["asset_id"], "class": x["class"], "A": x["A"]["proposed_name"],
                     "B": x["B"]["proposed_name"], "decision": a and (a["decision"] if a.get("valid") else "INVALID"),
                     "relation": a and a.get("relation"), "route": a and a["route"],
                     "reason": a and a.get("reason_short"), "evidence": a and a.get("evidence_used"),
                     "truth": t and t["truth"], "false_confident": fc, "outcome": outcome(a, t) if a else None})
    for k in per.values():
        picks = k["dec_A"] + k["dec_B"]
        k["b_preference"] = round(k["dec_B"] / picks, 3) if picks else None
        tab = k["truth_A"] + k["truth_B"]
        k["truth_b_share"] = round(k["truth_B"] / tab, 3) if tab else None
    for c, k in per.items():                       # точность выбора: верные выборы A/B к сверяемым выборам A/B
        pc = sum(1 for r in rows if (c == "ALL" or r["class"] == c) and r["outcome"] == "correct"
                 and r["decision"] in ("A", "B"))
        k["picks_correct"] = pc
        k["choice_accuracy"] = round(pc / (pc + k["out_false_confident"]), 3) if pc + k["out_false_confident"] else None
    out = {"snapshot": snap["snapshot_id"], "arb_rev": rev, "answers": len(answers), "truth": len(truth),
           "per_class": {c: dict(v) for c, v in per.items()}, "rows": rows,
           "made": time.strftime("%Y-%m-%dT%H:%M:%S")}
    allk = per["ALL"]
    for k in per.values():                         # аналитические поля: только пересчёт готовых ответов, без модели
        k["truth_sources"] = {s[4:]: v for s, v in k.items() if s.startswith("src_")}
        k["false_confident_by_relation"] = {r: k["fc_rel_" + r] for r in RELATIONS}
        k["false_confident_with_shared_words"] = k["fc_shared_words"]
        k["false_confident_without_shared_words"] = k["fc_no_shared_words"]
        k["false_confident_by_choice"] = {
            c: {"false_confident": k["fc_choice_" + c], "verified_picks": k["verified_choice_" + c],
                "rate": round(k["fc_choice_" + c] / k["verified_choice_" + c], 3) if k["verified_choice_" + c] else None}
            for c in ("A", "B")}
        # два знаменателя: от всей выборки класса и от размеченного - пока разметка неполная, они расходятся
        k["fc_total_pct"] = round(k["out_false_confident"] / k["n"], 4) if k["truth"] else None
        k["fc_labeled_pct"] = round(k["out_false_confident"] / k["truth"], 4) if k["truth"] else None
    out["per_class"] = {c: dict(v) for c, v in per.items()}
    if allk["truth"]:
        rate = allk["false_confident"] / allk["n"]
        out["false_confident_rate"] = round(rate, 4)
        out["verdict"] = verdict_of(rate)
        out["false_confident_by_relation"] = allk["false_confident_by_relation"]
        out["false_confident_with_shared_words"] = allk["fc_shared_words"]
        out["false_confident_without_shared_words"] = allk["fc_no_shared_words"]
        out["false_confident_by_choice"] = allk["false_confident_by_choice"]
        out["false_confident_labeled_rate"] = allk["fc_labeled_pct"]
    os.makedirs(rd, exist_ok=True)
    save_json(os.path.join(rd, "report.json"), out)
    summary = summary_text(per)
    with open(os.path.join(rd, "summary.txt"), "w", encoding=ENC) as f:
        f.write(summary + "\n")
    L = ["# Арбитр P1-C: контрольные 100 HARD", "",
         "Снимок `%s`, арбитр `%s` (%s). Ответов %d из %d, разметка правды %d." % (
             snap["snapshot_id"], rev, MODEL, len(answers), len(items), len(truth)),
         "Источник правды: %s." % (", ".join("%s %d" % kv for kv in sorted(allk["truth_sources"].items())) or "нет"),
         ""]
    head = ["класс", "n", "A", "B", "NEITHER", "CANNOT_TELL", "не по форме", "SAME", "BR_NAR", "REL_DIFF",
            "DIFFERENT", "-> LIGHT", "-> HARD", "FALSE_CONF", "выбор без правды"]
    L += ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for c in CLASSES + ("ALL",):
        k = per[c]
        L.append("| %s |" % " | ".join(str(v) for v in (
            c, k["n"], k["dec_A"], k["dec_B"], k["dec_NEITHER"], k["dec_CANNOT_TELL"], k["dec_INVALID"],
            k["rel_SAME"], k["rel_BROADER_NARROWER"], k["rel_RELATED_BUT_DIFFERENT"], k["rel_DIFFERENT"],
            k[LIGHT], k[HARD], k["false_confident"] if k["truth"] else "-", k["picked_unverified"])))
    L.append("")
    pct = lambda v: "-" if v is None else "%.0f %%" % (100 * v)
    if allk["truth"]:
        head = ["класс", "размечено", "правда A", "B", "BOTH", "NEITHER", "CANNOT_TELL", "арбитр верно",
                "FALSE_CONF", "ошибся, но отказался", "выбрал, человек не знает", "не по форме",
                "точность выбора", "доля B у арбитра", "доля B в правде"]
        L += ["Правда против ответа (исходы - `outcome` в коде):", "",
              "| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
        for c in CLASSES + ("ALL",):
            k = per[c]
            L.append("| %s |" % " | ".join(str(v) for v in (
                c, k["truth"], k["truth_A"], k["truth_B"], k["truth_BOTH"], k["truth_NEITHER"], k["truth_CANNOT_TELL"],
                k["out_correct"], k["out_false_confident"], k["out_wrong_uncertain"], k["out_picked_human_unsure"],
                k["out_invalid"], pct(k["choice_accuracy"]), pct(k["b_preference"]), pct(k["truth_b_share"]))))
        L.append("")
    else:
        L.append("Доля B у арбитра: %s (A и B расставлены по алфавиту; правды для сравнения пока нет)." %
                 pct(allk["b_preference"]))
    L += ["", "Сводка (она же `summary.txt`):", "", "```", summary, "```", ""]
    if allk["truth"]:
        L.append("**FALSE_CONFIDENT %d из %d (%.1f %%) - %s.** От размеченных %d: %.1f %%. Выбор A/B без правды "
                 "(человек не знает или не размечено) %d - в процент не входят." % (
                     allk["false_confident"], allk["n"], 100.0 * out["false_confident_rate"], out["verdict"],
                     allk["truth"], 100.0 * allk["fc_labeled_pct"], allk["picked_unverified"]))
    else:
        L.append("**FALSE_CONFIDENT - нет разметки правды** (truth.tsv рядом со снимком). До неё известно только "
                 "распределение ответов.")
    ct = allk["dec_CANNOT_TELL"] + allk["dec_INVALID"]
    if allk["answered"]:
        L.append("CANNOT_TELL и не по форме: %d из %d (%.0f %%). Ушло бы в LIGHT: %d." % (
            ct, allk["answered"], 100.0 * ct / allk["answered"], allk[LIGHT]))
    summary_end = len(L)
    L += ["", "| ассет | класс | A | B | решение | связь | куда | правда | FC | почему |", "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            r["asset_id"], r["class"], r["A"], r["B"], r["decision"] or "-", r["relation"] or "-",
            (r["route"] or "-").replace("HUMAN_REVIEW_", ""), r["truth"] or "-",
            {True: "**да**", False: "", None: ""}[r["false_confident"]], (r["reason"] or "").replace("|", "/")))
    with open(os.path.join(rd, "report.md"), "w", encoding=ENC) as f:
        f.write("\n".join(L) + "\n")
    print("\n".join(L[:summary_end]))
    print("-> %s" % os.path.join(rd, "report.md"))
    return out


# ------------------------------------------------------------------ разметка правды (вслепую)

LABEL_PAGE = """<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>Разметка правды</title>
<meta name="viewport" content="width=device-width,initial-scale=1"><style>
:root{--bg:#16161a;--fg:#e8e6e3;--mut:#9a978f;--card:#212127;--acc:#e6b422;--on:#2f6f3e}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.4 system-ui,sans-serif}
header{position:sticky;top:0;background:#101013;padding:10px 16px;border-bottom:1px solid #333;z-index:2}
main{max-width:1200px;margin:auto;padding:12px 16px}
.card{background:var(--card);border-radius:8px;padding:12px;margin:0 0 14px}
.pics{display:flex;gap:10px;flex-wrap:wrap;align-items:flex-start}.pics img{max-width:100%;image-rendering:pixelated;border:1px solid #333}
.sprite{height:200px}.ctx{max-height:380px}.fam{max-height:150px}
.c{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:10px 0}.c div{background:#2a2a31;padding:8px;border-radius:6px}
.c b{color:var(--acc)}pre{white-space:pre-wrap;color:var(--mut);font-size:13px;margin:6px 0}
button{background:#33333b;color:var(--fg);border:1px solid #555;border-radius:6px;padding:7px 12px;margin:3px;cursor:pointer;font:inherit}
button.on{background:var(--on);border-color:#4caf50}input{background:#2a2a31;color:var(--fg);border:1px solid #555;border-radius:6px;padding:6px;width:60%}
</style></head><body><header>Разметка правды: <span id="n"></span> · кадр, место, данные MCD и две догадки. Ответы арбитра здесь не показаны.
<br><small>A / B - верна эта догадка, другая хуже · BOTH - обе верны, это одно и то же · NEITHER - ни одна · CANNOT_TELL - не могу сказать</small></header>
<main id="m"></main><script>
const T=["A","B","BOTH","NEITHER","CANNOT_TELL"];let items=[],truth={};
async function load(){const r=await fetch("api/items");const d=await r.json();items=d.items;truth=d.truth;draw()}
function esc(s){return String(s||"").replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]))}
function cand(x){return "<b>"+esc(x.proposed_name)+"</b> ("+esc(x.proposed_category)+")<br><small>"+esc(x.short_description)+"</small>"}
function draw(){document.getElementById("n").textContent=Object.keys(truth).length+" из "+items.length;
document.getElementById("m").innerHTML=items.map((x,i)=>{const t=(truth[x.asset_id]||{});
return `<div class="card" id="c${i}"><div class="pics">${x.pics.map(p=>`<img class="${p.cls}" src="${p.src}" alt="${p.cls}">`).join("")}</div>
<pre>${esc(x.facts)}</pre><div class="c"><div>A: ${cand(x.A)}</div><div>B: ${cand(x.B)}</div></div>
${T.map(v=>`<button class="${t.truth==v?"on":""}" onclick="put(${i},'${v}')">${v}</button>`).join("")}
<input placeholder="заметка (что это на самом деле, если NEITHER)" value="${esc(t.note)}" onchange="note(${i},this.value)"></div>`}).join("")}
async function send(i,v,n){const x=items[i];const r=await fetch("api/truth",{method:"POST",headers:{"Content-Type":"application/json"},
body:JSON.stringify({asset_id:x.asset_id,truth:v,note:n})});truth=(await r.json()).truth;draw();}
function put(i,v){send(i,v,(truth[items[i].asset_id]||{}).note||"")}
function note(i,n){const t=truth[items[i].asset_id];if(t)send(i,t.truth,n)}
load()</script></body></html>"""


def save_truth(d, truth):
    p = os.path.join(d, "truth.tsv")
    tmp = p + ".tmp"
    with open(tmp, "w", encoding=ENC, newline="") as f:
        w = csv.writer(f, delimiter="\t", quoting=csv.QUOTE_NONE, escapechar="\\", lineterminator="\n")
        w.writerow(("asset_id", "truth", "who", "truth_source", "when", "note"))
        for aid in sorted(truth):
            t = truth[aid]
            w.writerow((aid, t["truth"], t["who"], t.get("truth_source") or truth_source(t["who"]), t["when"],
                        t.get("note", "").replace("\t", " ").replace("\n", " ")))
    os.replace(tmp, p)


def label(path, port=8775, who="Vitali"):
    """Страница разметки правды: только вход арбитра (кадр, место, семейство, MCD, A, B), без его ответов.
    Порядок - по хэшу, не по классу; ответ сразу в truth.tsv рядом со снимком."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from urllib.parse import unquote, urlparse
    snap, d = check_snapshot(path)
    items = sorted(snap["items"], key=lambda x: hashlib.sha1(("truth:" + x["asset_id"]).encode()).hexdigest())
    cls = {"sprite": "sprite", "map_crop": "ctx", "family_views": "fam"}
    view = [{"asset_id": x["asset_id"], "A": x["A"], "B": x["B"], "facts": x["facts"],
             "pics": [{"cls": cls[k], "src": "img/%s_%s.png" % (x["asset_id"].replace(":", "_"), k)}
                      for k in ("sprite", "map_crop", "family_views") if k in x["inputs"]]} for x in items]
    known = {x["asset_id"] for x in items}
    truth = {k: dict(v) for k, v in load_truth(d).items()}
    lock = __import__("threading").Lock()

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def out(self, code, body, ctype):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            u = unquote(urlparse(self.path).path)
            if u in ("/", "/index.html"):
                return self.out(200, LABEL_PAGE.encode("utf-8"), "text/html; charset=utf-8")
            if u == "/api/items":
                return self.out(200, json.dumps({"items": view, "truth": truth}).encode(), "application/json")
            if u.startswith("/img/") and "/" not in u[5:] and ".." not in u:
                p = os.path.join(d, "inputs", u[5:])
                if os.path.exists(p):
                    with open(p, "rb") as f:
                        return self.out(200, f.read(), "image/png")
            self.out(404, b"no", "text/plain")

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            q = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
            if urlparse(self.path).path != "/api/truth" or q.get("asset_id") not in known or q.get("truth") not in TRUTHS:
                return self.out(400, b"bad", "text/plain")
            with lock:
                truth[q["asset_id"]] = {"asset_id": q["asset_id"], "truth": q["truth"], "who": who,
                                        "when": time.strftime("%Y-%m-%dT%H:%M:%S"), "note": str(q.get("note", ""))[:300]}
                save_truth(d, truth)
            self.out(200, json.dumps({"truth": truth}).encode(), "application/json")

    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    print("разметка правды: http://127.0.0.1:%d/  (%d ассетов, размечено %d) -> %s" % (
        port, len(items), len(truth), os.path.join(d, "truth.tsv")), flush=True)
    srv.serve_forever()


def main():
    for s in (sys.stdout, sys.stderr):
        s.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["freeze", "run", "report", "label"])
    ap.add_argument("--port", type=int, default=8775)
    ap.add_argument("snapshot", nargs="?")
    ap.add_argument("--host", default="http://127.0.0.1:11434")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true", dest="dry_run")
    ap.add_argument("--holdout", action="store_true", help="freeze: вторая закрытая сотня без ассетов контрольной")
    a = ap.parse_args()
    if a.cmd == "freeze" and a.holdout:
        import glob
        ctl = sorted(glob.glob(os.path.join(ARB, "arbiter-control-100-*.json")))
        if not ctl:
            raise SystemExit("нет контрольной сотни - нечего исключать")
        freeze(salt=HOLDOUT_SALT, prefix="arbiter-holdout-100", exclude=ctl)
    elif a.cmd == "freeze":
        freeze()
    elif a.cmd == "run":
        sys.exit(run(a.snapshot, a.host, a.model, a.limit, a.dry_run))
    elif a.cmd == "label":
        label(a.snapshot, a.port)
    else:
        report(a.snapshot)


if __name__ == "__main__":
    main()
