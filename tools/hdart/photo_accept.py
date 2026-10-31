#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""PHOTO acceptance v1 (утверждено специалистом 01.10): проверка PHOTO-базы на НОВЫХ предметах.

Правила photo_base подбирались на 20 предметах made01 - это обучающий набор. Здесь - отложенная проверка:
~20 предметов, которых не было ни в photo-v2, ни в 20 настройки, ни в регрессии детали, ни в made01 вообще,
по случаям: 4 простых, 4 тонких (ножки, прутья), 4 с прорезями, 3 очень тёмных, 3 очень светлых, 2 с
трудным краем (тело близко ко всем серым подложкам - идёт цветная). Рендер - photo_render.py (свой
generator_rev, подложка названа цветом в промпте, PANEL_MISMATCH -> перерисовка), вырезка - photo_base.cut
как есть (полоса альфы 1.5 пикселя не меняется: менять её сейчас - подгонка под обучающий набор).

Разделение проверок:
  машина   PANEL, ALPHA, SILHOUETTE, FOOTPRINT, MISSING_MAJOR_PART, EDGE_SPILL, OPENING_PRESERVATION
           -> PASS / REVIEW / RERENDER / FAIL
  Vitali   OBJECT_IDENTITY, MATERIAL_QUALITY, MAJOR_GEOMETRY, INTERNAL_STRUCTURE, PHOTOREALISM,
           INVENTED_DETAIL -> PASS / FAIL и класс брака ALPHA / GEOMETRY / IDENTITY / MATERIAL / DETAIL /
           INVENTION; вслепую - вердикта машины на странице нет, порядок перемешан.
Ворота PHOTO_ACCEPTANCE_V1: human PASS >= 80 %, machine false-accept (машина PASS, человек FAIL) <= 10 %,
alpha hard fail <= 5 %, нет повторяющегося системного брака геометрии и вырезки подложки. RERENDER - не
hard fail: итог PASS / PASS_AFTER_RERENDER / REVIEW / FAIL. В пак ничего не идёт.

    py -3.13 tools\hdart\photo_accept.py select        отбор и задания (без видеокарты)
    <venv-qwen21> tools\hdart\photo_render.py ...      рендер - только через gpuq (команду печатает select)
    py -3.13 tools\hdart\photo_accept.py machine       машинный отчёт по готовым рендерам
    py -3.13 tools\hdart\photo_accept.py page          слепая страница для Vitali
    py -3.13 tools\hdart\photo_accept.py report --verdicts <tsv со страницы>   матрица, метрики, ворота
Всё кладётся в art/objects/generation/probes/photo-accept-v1/.
"""
import argparse
import hashlib
import json
import os
import random
import re
import sys
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.dirname(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
ROOT = os.path.dirname(os.path.dirname(HERE))

import numpy as np                      # noqa: E402
from PIL import Image, ImageDraw        # noqa: E402

import photo_base as pb                 # noqa: E402

ENC = "utf-8-sig"
OUT = os.path.join("art", "objects", "generation", "probes", "photo-accept-v1")
SEED = "photo-accept-v1"
SEED0 = 2713                            # зерно рендера: SEED0 + rank предмета (как у made01 - от списка)
ITEMS = os.path.join("art", "objects", "discovery", "items.json")
DETAIL_REG = os.path.join("art", "objects", "generation", "regression", "detail_critical_v1.json")
MIN_PX = 150
# (страт, сколько) - порядок = порядок отбора: редкие раньше, предмет идёт в первый подходящий
STRATA = [("hard_edge", 2), ("light", 3), ("openings", 4), ("thin", 4), ("dark", 3), ("simple", 4)]
# обломки и куски корпуса - не вещь целиком, а кусок большего (R-153) или рельеф; слова куска - из
# obj_generation.FRAGMENT_WORDS без машин целиком (fuel tank - отдельная вещь)
DEBRIS = re.compile(r"\b(debris|rubble|wreck|wreckage|scrap|hull|fuselage|wing|tail fin|nose cone|cockpit|"
                    r"section|segment|fragment|part of|piece of|panel of)s?\b", re.I)
STRATUM_RULE = {
    "hard_edge": "лучшая серая подложка ближе MIN_MARGIN (%.0f) к телу - рендер идёт на цветной" % pb.MIN_MARGIN,
    "openings": "прорези оригинала >= 6 пикселей k=1",
    "thin": "тонкое (не переживает открытие 3x3) >= 12 % силуэта",
    "dark": "средняя яркость тела < 70",
    "light": "средняя яркость тела >= 155 (в пуле выше 165 только три, два из них - прорези)",
    "simple": "одним куском, без прорезей, тонкого < 5 %, яркость 70-165, серая подложка отделяет",
}
HUMAN_CRITERIA = ["OBJECT_IDENTITY", "MATERIAL_QUALITY", "MAJOR_GEOMETRY", "INTERNAL_STRUCTURE", "PHOTOREALISM",
                  "INVENTED_DETAIL"]
FAIL_CLASSES = ["ALPHA", "GEOMETRY", "IDENTITY", "MATERIAL", "DETAIL", "INVENTION"]
MACHINE_CHECKS = ["PANEL", "ALPHA", "SILHOUETTE", "FOOTPRINT", "MISSING_MAJOR_PART", "EDGE_SPILL",
                  "OPENING_PRESERVATION"]
# пороги машины сверх photo_base.GEOM (черновые, как и те): итоговая альфа и опора на пол
# ALPHA FAIL - только явная поломка (тело не нарисовано, подложка по половине кромки); полупрозрачное -
# REVIEW: у тонких полоса 1.5 пикселя занимает большую часть тела, это известное, а не брак (made01: semi до 0.20)
MACHINE = {"panel_delta": 24.0,          # подложка ответа дальше от поданной (худший канал) - PANEL_MISMATCH
           "alpha_fail_core": 0.10, "alpha_fail_rim": 0.50, "alpha_review_semi": 0.08,
           "foot_fail": 0.70, "foot_review": 0.90, "foot_band": 0.20,
           "spill_fail": 0.25, "holes_review": 0.70}
GATE = {"human_pass_min": 0.80, "false_accept_max": 0.10, "alpha_hard_fail_max": 0.05, "systemic_min": 3}
RANK = {"PASS": 0, "N/A": 0, "REVIEW": 1, "RERENDER": 2, "FAIL": 3}


def load(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding=ENC) as f:
        return json.load(f)


def dump(obj, path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding=ENC) as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


# ---------------------------------------------------------------- отбор

def seen():
    """Всё, что уже видели глазами или по чему подбирались правила: {asset_id: откуда}."""
    out = {}
    for j in load(os.path.join(pb.PHOTO_V2, "batch_jobs.json"), []):
        out[j["asset_id"].upper()] = "photo-v2"
    for r in (load(os.path.join(pb.OUT, "regression.json"), {}) or {}).get("items", []):
        out.setdefault(r["asset_id"].upper(), "regression-20")
    for a in (load(DETAIL_REG, {}) or {}).get("assets", []):
        out.setdefault(a["asset_id"].upper(), "detail-regression")
        for fr in a.get("frames", []):          # копии того же кадра в других наборах
            m = re.match(r"TERRAIN/(.+)\.PCK/(\d+)\.png", fr.replace("\\", "/"))
            if m:
                out.setdefault(("%s:%s" % m.groups()).upper(), "detail-regression")
    for j in load(pb.MADE01_JOBS, []):
        for t in j.get("take", []):
            out.setdefault(t.split("@")[0].upper(), "made01")
    return out


def features(world, job):
    _c, _w, _a, _b, frame = pb.job_frame(world, job)
    g = pb.guide(frame)
    a = np.asarray(frame.convert("RGBA"), np.float64)
    body = a[..., :3][a[..., 3] > 128]
    grey = max(float(np.percentile(np.abs(body - np.array(rgb)).max(-1), 10)) for _n, rgb in pb.PANELS) \
        if len(body) else 0.0
    return {"px": g["px"], "open_px": g["open_px"], "thin_share": round(g["thin_px"] / max(1, g["px"]), 3),
            "lum": round(g["lum"], 1), "comps": g["comps"], "grey_margin": round(grey, 1)}


def stratum_ok(name, f):
    if name == "hard_edge":
        return f["grey_margin"] < pb.MIN_MARGIN
    if name == "openings":
        return f["open_px"] >= 6
    if name == "thin":
        return f["thin_share"] >= 0.12
    if name == "dark":
        return f["lum"] < 70
    if name == "light":
        return f["lum"] >= 155
    return (f["thin_share"] < 0.05 and not f["open_px"] and f["comps"] == 1 and 70 <= f["lum"] <= 165
            and f["grey_margin"] >= pb.MIN_MARGIN)


def pool():
    """Кандидаты: ворота pilot_batch (один кадр, класс object, без вопросов семейства и другого бока, без
    подозрения на кусок, опознание HUMAN/EASY/LIGHT, не природа, без перекрасок), но БЕЗ фильтра сложной
    геометрии по названию - тонкие и с прорезями и есть предмет проверки. -> (кандидаты, отсев)."""
    import detail_class as dc
    import map_mockup as mm
    import pilot_batch as pbt
    keep = pbt.GEOMETRY
    pbt.GEOMETRY = re.compile(r"(?!x)x")
    try:
        cands, drop = pbt.select()
    finally:
        pbt.GEOMETRY = keep
    items = load(ITEMS)
    by_key = {}
    for it in items:
        for k in it.get("keys", []):
            by_key.setdefault(k.upper(), it)
    old = seen()
    world = mm.World()
    out = []
    for c in cands:
        aid = c["asset_id"].upper()
        it = by_key.get(aid)
        why = None
        if aid in old or c["family"].upper() in old:
            why = "уже видели: %s" % (old.get(aid) or old.get(c["family"].upper()))
        elif it is None or len(it.get("src", [])) != 1 or len(it.get("at", [])) != 1:
            why = "нет задания в один кусок в items.json"
        elif any(k.upper() in old for k in it.get("keys", [])):
            why = "копия уже виденного кадра"
        elif dc.words(c["name"]) or dc.words(c["other_name"]):
            why = "DETAIL_CRITICAL (регрессия детали)"
        elif DEBRIS.search(c["name"]) or DEBRIS.search(c["other_name"]):
            why = "обломки (R-153)"
        if why is None:
            s, f = it["src"][0].split(":")
            a = np.asarray(world.sprite(s.lower(), int(f), None).convert("RGBA"))[..., 3] > 0
            if int(a[:, 0].sum() + a[:, -1].sum() + a[0].sum()):
                why = "касается края кадра (R-153)"
            elif a.sum() < MIN_PX:
                why = "мелкий (< %d пикселей)" % MIN_PX
        if why:
            drop[why] += 1
            continue
        job = {"name": "pa_%s" % aid.replace(":", "_").lower(), "map": it["map"], "at": it["at"][:1],
               "take": ["%s@0" % it["src"][0]], "what": c["name"], "asset_id": c["asset_id"], "src": it["src"][0],
               "rank": c["rank"], "family": c["family"], "level": c["level"], "places": c["places"]}
        job.update(features(world, job))
        out.append(job)
    return out, drop


def select():
    cands, drop = pool()
    rnd = random.Random(int(hashlib.sha256(SEED.encode()).hexdigest()[:12], 16))
    chosen, used_sets, jobs = set(), set(), []
    short = []
    for name, n in STRATA:
        ok = sorted((c for c in cands if c["asset_id"] not in chosen and stratum_ok(name, c)),
                    key=lambda c: c["asset_id"])
        rnd.shuffle(ok)
        got = 0
        # разные наборы: не два кадра одного PCK (ни ассета, ни источника); не хватило - второй проход без этого
        for strict in (True, False):
            for c in ok:
                if got >= n:
                    break
                st = {c["src"].split(":")[0], c["asset_id"].split(":")[0]}
                if c["asset_id"] in chosen or (strict and st & used_sets):
                    continue
                used_sets |= st
                chosen.add(c["asset_id"])
                jobs.append(dict(c, stratum=name, seed=SEED0 + c["rank"]))
                got += 1
        if got < n:
            short.append("%s: %d из %d (годных %d)" % (name, got, n, len(ok)))
    frozen = {"photo_base.py": sha256_file(os.path.join(HERE, "photo_base.py")),
              "photo_accept.py": sha256_file(os.path.join(HERE, "photo_accept.py"))}
    manifest = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "seed": SEED, "strata": dict(STRATA),
                "stratum_rule": STRATUM_RULE, "pool": len(cands), "dropped": dict(drop), "short": short,
                "frozen_code": frozen, "machine": MACHINE, "geom": pb.GEOM, "gate": GATE,
                "assets": [j["asset_id"] for j in jobs]}
    dump(jobs, os.path.join(OUT, "jobs.json"))
    dump(manifest, os.path.join(OUT, "selection.json"))
    cols = ["asset_id", "stratum", "src", "rank", "seed", "px", "open_px", "thin_share", "lum", "comps",
            "grey_margin", "level", "places", "what"]
    with open(os.path.join(OUT, "candidates.tsv"), "w", encoding=ENC) as f:
        f.write("\t".join(cols + ["picked"]) + "\n")
        pick = {j["asset_id"]: j for j in jobs}
        for c in cands:
            r = pick.get(c["asset_id"], c)
            f.write("\t".join(str(r.get(k, "")).replace("\t", " ") for k in cols) + "\t%d\n" % (c["asset_id"] in pick))
    print("годных после ворот и исключений: %d; отсев: %s" % (len(cands), dict(drop)))
    for j in jobs:
        print("  %-10s %-24s seed %-5d px %-4d open %-3d thin %.2f lum %5.1f grey %5.1f  %s" % (
            j["stratum"], j["asset_id"], j["seed"], j["px"], j["open_px"], j["thin_share"], j["lum"],
            j["grey_margin"], j["what"][:50]))
    for s in short:
        print("  НЕДОБОР", s)
    print("заданий %d -> %s" % (len(jobs), os.path.join(OUT, "jobs.json")))
    return jobs


# ---------------------------------------------------------------- машина

def footprint(g, m_u):
    """Опора: доля нижней полосы силуэта (FOOTPRINT band) x4, закрытая ответом в пропорциях модели."""
    s = g["sil4"] > 0.5
    ys = np.nonzero(s.any(1))[0]
    if not len(ys):
        return None
    y0 = ys[-1] - max(2, int(round((ys[-1] - ys[0] + 1) * MACHINE["foot_band"]))) + 1
    band = s.copy()
    band[:y0] = False
    return round(float((band & pb.grow(m_u > 0.5, 2)).sum()) / max(1, int(band.sum())), 4)


def checks(rep, panel_delta, panel_rerender_left, foot):
    """Отчёт photo_base.cut + подложка -> {проверка: (статус, почему)}. panel_rerender_left - можно ли ещё
    перерисовать (нет - несовпадение подложки уходит человеку, REVIEW)."""
    M, G = MACHINE, pb.GEOM
    c = {}
    if panel_delta > M["panel_delta"]:
        c["PANEL"] = ("RERENDER" if panel_rerender_left else "REVIEW", "panel delta %.0f" % panel_delta)
    else:
        c["PANEL"] = ("PASS", "panel delta %.0f" % panel_delta)
    if rep["geometry"] == "UNVERIFIABLE":       # тело цвета подложки: форма неизвестна - на другой подложке
        c["SILHOUETTE"] = ("RERENDER", rep["geometry_why"])
    elif rep["cover"] < G["cover_fail"] or (rep.get("aspect_raw") or 0) > G["aspect_fail"]:
        c["SILHOUETTE"] = ("FAIL", "cover %.2f aspect %s" % (rep["cover"], rep.get("aspect_raw")))
    elif rep["cover"] < G["cover_review"] or (rep.get("aspect_raw") or 0) > G["aspect_review"]:
        c["SILHOUETTE"] = ("REVIEW", "cover %.2f aspect %s" % (rep["cover"], rep.get("aspect_raw")))
    else:
        c["SILHOUETTE"] = ("PASS", "cover %.2f iou %.2f" % (rep["cover"], rep["iou"]))
    if foot is None:
        c["FOOTPRINT"] = ("N/A", "")
    else:
        c["FOOTPRINT"] = ("FAIL" if foot < M["foot_fail"] else "REVIEW" if foot < M["foot_review"] else "PASS",
                          "bottom band %.2f" % foot)
    tc = rep.get("thin_cover")
    part = []
    st = "PASS"
    if tc is not None and tc < G["thin_fail"]:
        st = "FAIL"
        part.append("thin %.2f" % tc)
    if rep["comps_render"] < rep["comps_orig"]:
        st = max(st, "REVIEW", key=RANK.get)
        part.append("comps %d/%d" % (rep["comps_render"], rep["comps_orig"]))
    c["MISSING_MAJOR_PART"] = (st, "; ".join(part) or ("thin %.2f" % tc if tc is not None else "no thin parts"))
    sp = rep["spill"]
    c["EDGE_SPILL"] = ("FAIL" if sp > M["spill_fail"] else "REVIEW" if sp > G["spill_review"] else "PASS",
                       "spill %.3f" % sp)
    hk = rep.get("holes_kept")
    if hk is None:
        c["OPENING_PRESERVATION"] = ("N/A", "no openings")
    else:
        c["OPENING_PRESERVATION"] = ("FAIL" if hk < G["holes_fail"] else "REVIEW" if hk < M["holes_review"]
                                     else "PASS", "holes kept %.2f" % hk)
    why = []
    if rep["core_panel"] > M["alpha_fail_core"]:
        why.append("core panel %.2f" % rep["core_panel"])
    if rep["rim_panel"] > M["alpha_fail_rim"]:
        why.append("rim panel %.2f" % rep["rim_panel"])
    if why:
        c["ALPHA"] = ("FAIL", "; ".join(why))
    elif rep["alpha"] == "REVIEW" or rep["semi"] > M["alpha_review_semi"]:
        c["ALPHA"] = ("REVIEW", rep["alpha_why"] or "semi %.2f" % rep["semi"])
    else:
        c["ALPHA"] = ("PASS", "semi %.3f" % rep["semi"])
    # тело цвета подложки ответа: матт не отделил тело, и всё, что меряется по матту, - не брак формы, а
    # неизвестность (NUKE3 21 made01: опора 0.64 при охвате 0.27) - перерисовать, а не браковать
    if rep["geometry"] == "UNVERIFIABLE":
        for k in ("FOOTPRINT", "MISSING_MAJOR_PART", "EDGE_SPILL", "OPENING_PRESERVATION", "ALPHA"):
            if c[k][0] == "FAIL":               # ALPHA: подложка в ядре - то же тело цвета подложки
                c[k] = ("RERENDER", c[k][1] + " (unverifiable)")
    # аспект 1.3-1.6 photo_base переводит FAIL деталей в REVIEW (детали в чужих пропорциях съезжают) - так же
    a = rep.get("aspect_raw") or 0
    if G["aspect_review"] < a <= G["aspect_fail"]:
        for k in ("MISSING_MAJOR_PART", "OPENING_PRESERVATION"):
            if c[k][0] == "FAIL":
                c[k] = ("REVIEW", c[k][1] + " (aspect %.2f)" % a)
    return c


def machine_verdict(c):
    return max((s for s, _w in c.values()), key=RANK.get)


def outcome(verdict, attempts):
    """Итог предмета по машине: RERENDER, который не удалось закрыть перерисовкой, - REVIEW."""
    if verdict == "PASS":
        return "PASS_AFTER_RERENDER" if attempts > 1 else "PASS"
    if verdict == "RERENDER":
        return "REVIEW"
    return verdict


def machine():
    """Сводка результатов photo_render: machine.tsv и лист machine_sheet.png (с вердиктами - не для слепой
    оценки)."""
    jobs = load(os.path.join(OUT, "jobs.json"))
    rows = []
    for j in jobs:
        r = load(os.path.join(OUT, "render", "meta", j["name"] + ".json"))
        if r is None:
            print("  %-24s нет рендера" % j["asset_id"])
            continue
        rows.append(r)
    cols = ["asset_id", "stratum", "outcome", "machine", "attempts"] + MACHINE_CHECKS
    with open(os.path.join(OUT, "machine.tsv"), "w", encoding=ENC) as f:
        f.write("\t".join(cols + ["why"]) + "\n")
        for r in rows:
            c = r["checks"]
            f.write("\t".join([r["asset_id"], r["stratum"], r["outcome"], r["machine"], str(len(r["attempts"]))]
                              + [c[k][0] for k in MACHINE_CHECKS]
                              + ["; ".join("%s: %s" % (k, c[k][1]) for k in MACHINE_CHECKS if c[k][0] not in
                                           ("PASS", "N/A"))]) + "\n")
    n = Counter(r["outcome"] for r in rows)
    print("машина: %d из %d; %s" % (len(rows), len(jobs), ", ".join("%s %d" % kv for kv in sorted(n.items()))))
    for r in rows:
        bad = [k for k in MACHINE_CHECKS if r["checks"][k][0] not in ("PASS", "N/A")]
        print("  %-24s %-10s %-20s %s" % (r["asset_id"], r["stratum"], r["outcome"],
                                          ", ".join("%s=%s" % (k, r["checks"][k][0]) for k in bad)))
    return rows


# ---------------------------------------------------------------- страница для Vitali (вслепую)

PAGE = """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>PHOTO acceptance v1</title>
<style>
:root{--bg:#1b1b1f;--card:#26262c;--fg:#e8e8ea;--mut:#9a9aa3;--acc:#f2c14e;--ok:#3f8f5a;--bad:#a3423a}
body{background:var(--bg);color:var(--fg);font:14px/1.4 system-ui,sans-serif;margin:0;padding:16px}
h1{font-size:18px;margin:0 0 4px}.mut{color:var(--mut)}
.row{background:var(--card);border-radius:8px;padding:12px;margin:14px 0}
.cols{display:flex;gap:10px;flex-wrap:wrap;align-items:flex-start}
.col{display:flex;flex-direction:column;gap:4px;max-width:100%}
.col img{max-width:100%;image-rendering:auto;border-radius:4px}
.col img.px{image-rendering:pixelated}
.t{font-weight:600;color:var(--acc);font-size:12px}
table{border-collapse:collapse;margin-top:8px}td{padding:2px 6px}
button{background:#33333b;color:var(--fg);border:1px solid #44444d;border-radius:4px;padding:2px 8px;cursor:pointer;font-size:12px}
button.on[data-v=PASS]{background:var(--ok)}button.on[data-v=FAIL]{background:var(--bad)}
button.on.cls{background:#7a5ab8}
.btns{display:flex;gap:4px;flex-wrap:wrap;margin-top:6px}
input[type=text]{width:100%;box-sizing:border-box;background:#1f1f24;color:var(--fg);border:1px solid #44444d;border-radius:4px;padding:3px;margin-top:6px}
textarea{width:100%;height:180px;background:#1f1f24;color:var(--fg);box-sizing:border-box}
a{color:var(--acc)}
</style></head><body>
<h1>PHOTO acceptance v1 - новые предметы, вслепую</h1>
<div class="mut">__N__ предметов, которых не было ни в одной прежней пробе. Вердикта машины здесь нет, порядок
случайный. По каждому: итог PASS / FAIL, при FAIL - класс брака (можно несколько), по критериям - PASS / FAIL.
PASS - годится как HD-кадр этой вещи; альфу видно на пурпурном и на полу. Ответ копится в браузере, TSV внизу -
прислать целиком.</div>
<div id="rows"></div>
<h2>TSV</h2><textarea id="tsv" readonly></textarea>
<script>
const DATA = __DATA__;
const CRIT = __CRIT__;
const CLS = __CLS__;
const KEY = "photo-accept-v1";
let st = {}; try { st = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) {}
function save(){ try { localStorage.setItem(KEY, JSON.stringify(st)); } catch (e) {} tsv(); }
function tsv(){
  const L = [["asset_id", "human", "fail_class"].concat(CRIT, ["note"]).join("\\t")];
  for (const r of DATA) { const s = st[r.asset] || {};
    L.push([r.asset, s.o || "", Object.keys(s.k || {}).filter(k => s.k[k]).join(",")]
      .concat(CRIT.map(c => (s.c || {})[c] || ""), [(s.n || "").replace(/[\\t\\n]/g, " ")]).join("\\t")); }
  document.getElementById("tsv").value = L.join("\\n");
}
function toggle(box, s, field, v){ s[field] = s[field] === v ? "" : v;
  box.querySelectorAll("button").forEach(x => x.classList.toggle("on", x.dataset.v === s[field])); save(); }
const root = document.getElementById("rows");
DATA.forEach((r, i) => {
  const s = st[r.asset] = st[r.asset] || {}; s.c = s.c || {}; s.k = s.k || {};
  const row = document.createElement("div"); row.className = "row";
  row.innerHTML = `<div><b>${i + 1}. ${r.asset}</b> <span class="mut">${r.what}</span></div>`;
  const cols = document.createElement("div"); cols.className = "cols"; row.appendChild(cols);
  for (const [f, t, px] of r.img) cols.insertAdjacentHTML("beforeend",
    `<div class="col"><div class="t">${t}</div><img class="${px ? "px" : ""}" src="${f}" width="${r.w}" height="${r.h}" loading="lazy"></div>`);
  cols.insertAdjacentHTML("beforeend", `<div class="col"><div class="t">сырой ответ</div><a href="${r.raw}" target="_blank">открыть</a></div>`);
  const ob = document.createElement("div"); ob.className = "btns";
  for (const v of ["PASS", "FAIL"]) { const e = document.createElement("button"); e.textContent = v; e.dataset.v = v;
    if (s.o === v) e.classList.add("on"); e.onclick = () => toggle(ob, s, "o", v); ob.appendChild(e); }
  row.insertAdjacentHTML("beforeend", `<div class="t" style="margin-top:8px">итог</div>`); row.appendChild(ob);
  const kb = document.createElement("div"); kb.className = "btns";
  for (const v of CLS) { const e = document.createElement("button"); e.textContent = v; e.className = "cls";
    if (s.k[v]) e.classList.add("on");
    e.onclick = () => { s.k[v] = !s.k[v]; e.classList.toggle("on", s.k[v]); save(); }; kb.appendChild(e); }
  row.insertAdjacentHTML("beforeend", `<div class="t" style="margin-top:8px">класс брака (при FAIL)</div>`); row.appendChild(kb);
  const tb = document.createElement("table");
  for (const cr of CRIT) { const tr = document.createElement("tr"); tr.innerHTML = `<td>${cr}</td>`;
    const td = document.createElement("td"); td.className = "btns";
    for (const v of ["PASS", "FAIL"]) { const e = document.createElement("button"); e.textContent = v; e.dataset.v = v;
      if (s.c[cr] === v) e.classList.add("on");
      e.onclick = () => { s.c[cr] = s.c[cr] === v ? "" : v;
        td.querySelectorAll("button").forEach(x => x.classList.toggle("on", x.dataset.v === s.c[cr])); save(); };
      td.appendChild(e); }
    tr.appendChild(td); tb.appendChild(tr); }
  row.appendChild(tb);
  const n = document.createElement("input"); n.type = "text"; n.placeholder = "заметка"; n.value = s.n || "";
  n.oninput = () => { s.n = n.value; save(); }; row.appendChild(n);
  root.appendChild(row);
});
tsv();
</script></body></html>"""


def on_bg(piece, rgb):
    im = Image.new("RGBA", piece.size, tuple(rgb) + (255,))
    im.alpha_composite(piece)
    return im.convert("RGB")


def page():
    """Слепая страница: оригинал x4, новый кадр на полу боя, на пурпурном, на светлом - без вердикта
    машины, страта и числа попыток; порядок перемешан своим зерном."""
    import map_mockup as mm
    import obj_series as osr
    import shutil
    world = mm.World()
    jobs = load(os.path.join(OUT, "jobs.json"))
    d = os.path.join(OUT, "page")
    os.makedirs(d, exist_ok=True)
    for f in os.listdir(d):
        if f.endswith(".png"):
            os.remove(os.path.join(d, f))
    rnd = random.Random(SEED + "-page")
    order = list(jobs)
    rnd.shuffle(order)
    cw, ch = 256, 320
    data = []
    for n, j in enumerate(order, 1):
        meta = load(os.path.join(OUT, "render", "meta", j["name"] + ".json"))
        if meta is None:
            continue
        s, f = j["src"].split(":")
        piece = Image.open(os.path.join(OUT, "render", "%s.PCK" % s.upper(), "%s.png" % f)).convert("RGBA")
        orig = world.sprite(s.lower(), int(f), None).convert("RGBA")
        tag = "%02d" % n                        # имя файла не выдаёт ни страт, ни вердикт
        imgs = [(osr.on_floor(orig.resize(piece.size, Image.NEAREST), piece.size), "оригинал x4", True),
                (osr.on_floor(piece, piece.size), "новый на полу", False),
                (on_bg(piece, (255, 0, 255)), "новый на пурпурном", False),
                (on_bg(piece, (235, 235, 235)), "новый на светлом", False)]
        img = []
        for k, (im, t, px) in enumerate(imgs):
            fn = "%s_%d.png" % (tag, k)
            im.resize((cw, ch), Image.NEAREST if px else Image.LANCZOS).save(os.path.join(d, fn))
            img.append((fn, t, px))
        raw = "%s_raw.png" % tag
        shutil.copyfile(meta["attempts"][meta["final_attempt"]]["raw"], os.path.join(d, raw))
        data.append({"asset": j["asset_id"], "what": j["what"], "img": img, "raw": raw, "w": cw, "h": ch})
    html = PAGE.replace("__DATA__", json.dumps(data, ensure_ascii=False)).replace(
        "__CRIT__", json.dumps(HUMAN_CRITERIA)).replace("__CLS__", json.dumps(FAIL_CLASSES)).replace(
        "__N__", str(len(data)))
    with open(os.path.join(d, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    url = os.path.relpath(d, os.path.join("art", "objects", "generation")).replace(os.sep, "/")
    print("страница: http://localhost:8778/%s/index.html (%d предметов из %d заданий)" % (url, len(data), len(jobs)))


# ---------------------------------------------------------------- матрица и ворота

def read_verdicts(path):
    with open(path, encoding=ENC) as f:
        head = f.readline().rstrip("\r\n").split("\t")
        return {r["asset_id"]: r for r in (dict(zip(head, line.rstrip("\r\n").split("\t"))) for line in f if line.strip())}


def report(verdicts_path):
    """Сверка машины с вердиктом Vitali: матрица, шесть метрик, ворота PHOTO_ACCEPTANCE_V1."""
    jobs = {j["asset_id"]: j for j in load(os.path.join(OUT, "jobs.json"))}
    human = read_verdicts(verdicts_path)
    rows = []
    for aid, j in jobs.items():
        meta = load(os.path.join(OUT, "render", "meta", j["name"] + ".json"))
        h = human.get(aid, {})
        if meta is None or h.get("human") not in ("PASS", "FAIL"):
            continue
        rows.append({"asset_id": aid, "stratum": j["stratum"], "machine": meta["machine"],
                     "outcome": meta["outcome"], "attempts": len(meta["attempts"]), "human": h["human"],
                     "fail_class": h.get("fail_class", ""), "checks": meta["checks"],
                     "note": h.get("note", "")})
    n = len(rows)
    if not n:
        raise SystemExit("ни одного предмета с вердиктом и рендером")
    hp = [r for r in rows if r["human"] == "PASS"]
    hf = [r for r in rows if r["human"] == "FAIL"]
    mpass = [r for r in rows if r["machine"] == "PASS"]     # PASS и PASS_AFTER_RERENDER
    mfail = [r for r in rows if r["machine"] == "FAIL"]
    fa = [r for r in mpass if r["human"] == "FAIL"]
    fr = [r for r in mfail if r["human"] == "PASS"]
    cls = Counter(c for r in hf for c in r["fail_class"].split(",") if c)
    alpha_hard = [r for r in rows if r["checks"]["ALPHA"][0] == "FAIL" or
                  (r["human"] == "FAIL" and "ALPHA" in r["fail_class"].split(","))]
    geo = [r for r in hf if "GEOMETRY" in r["fail_class"].split(",")]
    panel = [r for r in rows if r["checks"]["PANEL"][0] != "PASS"]
    m = {"n": n,
         "human_accept_rate": round(len(hp) / n, 3),
         # доля брака среди принятых машиной: столько плохих прошло бы без человека (самый опасный класс)
         "machine_false_accept_rate": round(len(fa) / len(mpass), 3) if mpass else 0.0,
         "machine_false_accept": "%d of %d machine PASS" % (len(fa), len(mpass)),
         # доля годных по человеку, которые машина отбраковала
         "machine_false_reject_rate": round(len(fr) / len(hp), 3) if hp else 0.0,
         "machine_false_reject": "%d of %d human PASS" % (len(fr), len(hp)),
         "rerender_rate": round(sum(r["attempts"] > 1 for r in rows) / n, 3),
         "alpha_fail_rate": round(len(alpha_hard) / n, 3),
         "geometry_fail_rate": round(len(geo) / n, 3)}
    # системный брак: один и тот же класс или одна и та же машинная проверка у >= systemic_min предметов
    geo_sys = Counter(r["stratum"] for r in geo)
    gate = {"human PASS >= %.0f %%" % (GATE["human_pass_min"] * 100): m["human_accept_rate"] >= GATE["human_pass_min"],
            "machine false-accept <= %.0f %%" % (GATE["false_accept_max"] * 100):
                m["machine_false_accept_rate"] <= GATE["false_accept_max"],
            "alpha hard fail <= %.0f %%" % (GATE["alpha_hard_fail_max"] * 100):
                m["alpha_fail_rate"] <= GATE["alpha_hard_fail_max"],
            "no repeated systemic geometry defect (< %d GEOMETRY FAIL)" % GATE["systemic_min"]:
                len(geo) < GATE["systemic_min"],
            "no repeated panel extraction defect (< %d unresolved PANEL)" % GATE["systemic_min"]:
                sum(r["checks"]["PANEL"][0] not in ("PASS",) for r in rows) < GATE["systemic_min"]}
    matrix = Counter((r["machine"], r["human"]) for r in rows)
    res = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "verdicts": verdicts_path, "metrics": m,
           "matrix": {"%s|%s" % k: v for k, v in sorted(matrix.items())}, "fail_classes": dict(cls),
           "geometry_fail_by_stratum": dict(geo_sys), "panel_not_pass": [r["asset_id"] for r in panel],
           "gate": gate, "gate_passed": all(gate.values()),
           "false_accepts": [{"asset_id": r["asset_id"], "fail_class": r["fail_class"], "note": r["note"]}
                             for r in fa],
           "rows": [{k: r[k] for k in ("asset_id", "stratum", "machine", "outcome", "attempts", "human", "fail_class")}
                    for r in rows]}
    dump(res, os.path.join(OUT, "report.json"))
    L = ["# PHOTO acceptance v1 - итог", "",
         "Вердикты: `%s`, предметов с вердиктом и рендером: %d." % (verdicts_path, n), "",
         "| машина \\ человек | PASS | FAIL |", "|---|---|---|"]
    for mv in ("PASS", "REVIEW", "RERENDER", "FAIL"):
        L.append("| %s | %d | %d |" % (mv, matrix[(mv, "PASS")], matrix[(mv, "FAIL")]))
    L += ["", "| метрика | значение |", "|---|---|"] + ["| %s | %s |" % kv for kv in m.items()]
    L += ["", "| ворота PHOTO_ACCEPTANCE_V1 | |", "|---|---|"] + \
         ["| %s | %s |" % (k, "да" if v else "**нет**") for k, v in gate.items()]
    L += ["", "Итог ворот: **%s**." % ("пройдены" if res["gate_passed"] else "не пройдены"),
          "", "Классы брака у человека: %s." % (dict(cls) or "нет"),
          "", "| предмет | страт | машина | итог машины | попыток | человек | класс |", "|---|---|---|---|---|---|---|"]
    L += ["| %(asset_id)s | %(stratum)s | %(machine)s | %(outcome)s | %(attempts)d | %(human)s | %(fail_class)s |" % r
          for r in rows]
    with open(os.path.join(OUT, "report.md"), "w", encoding=ENC) as f:
        f.write("\n".join(L) + "\n")
    print("\n".join(L))
    return res


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["select", "machine", "page", "report"])
    ap.add_argument("--verdicts", default=os.path.join(OUT, "verdicts_vitali.tsv"))
    a = ap.parse_args()
    os.chdir(ROOT)
    if a.cmd == "select":
        select()
        print("\nрендер - через очередь видеокарты:")
        print("py -3.13 tools/gpuq.py add --name photo_accept_v1 --cwd E:/OpenXCom -- "
              "E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/photo_render.py "
              "--jobs %s --out %s" % ((OUT + "/jobs.json").replace("\\", "/"), (OUT + "/render").replace("\\", "/")))
    elif a.cmd == "machine":
        machine()
    elif a.cmd == "page":
        page()
    else:
        report(a.verdicts)


if __name__ == "__main__":
    main()
