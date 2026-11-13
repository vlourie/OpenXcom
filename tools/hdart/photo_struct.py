#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""PHOTO_STRUCT_ACCEPTANCE_V1 (специалист 01.10): рабочий путь STRUCT_GUIDE_V1_C на невиданных предметах.

    source -> STRUCT_GUIDE_V1 -> PHOTO C -> managed alpha -> technical QA -> human visual QA

STRUCT_GUIDE_V1 пройден на 10 предметах (DECISIONS 01.10), они теперь набор регрессии; struct_guide.py не
подгоняется. Здесь - переносится ли это на новые: ~20 предметов, которых не видели ни в одной пробе.

Отбор: ворота photo_accept.pool (один кадр, класс object - не structural и не structural_modular, семейство без
открытых вопросов, не другой бок, без перекрасок, не кусок большего, не природа, не DETAIL_CRITICAL, не у края
кадра), но опознание любого уровня, лишь бы на карточке было описание (у MODEL_HARD модели разошлись - его нет,
такие отсеяны): WRONG_IDENTITY в PHOTO acceptance v1 приходил сверху, от
описания, поэтому описание каждого предмета подтверждает Vitali ДО рендера на карточке опознания
(review_server, вид «десятка», список identity_list.json). В рендер идёт только подтверждённый текст - он и есть
промпт. Страты - как у v1 (photo_accept.STRATA), со своим зерном.

Ступени:
    py -3.13 tools/hdart/photo_struct.py candidates     список на проверку опознания (~1.5 x квоты)
        -> review_server --port 8779 --accept <OUT>/identity_list.json (.claude/launch.json: struct-accept-review)
    py -3.13 tools/hdart/photo_struct.py select         задания из подтверждённых, печатает команду очереди
    рендер - photo_struct_render.py под render_chunks.py (не больше 4 рендеров на процесс), только через gpuq
    py -3.13 tools/hdart/photo_struct.py machine        technical QA: machine.tsv
    py -3.13 tools/hdart/photo_struct.py page           слепая страница (вердикта машины нет)
    py -3.13 tools/hdart/photo_struct.py report --verdicts <tsv>

Человек: PASS / PARTIAL / FAIL и классы PIXEL_STEP_TRACING, DETAIL_LOSS, MAJOR_GEOMETRY, INVENTED_DETAIL,
BAD_MATERIAL, BAD_ALPHA, WRONG_IDENTITY (с отметкой, был ли промпт верен). INVENTED_DETAIL -> HARD_FAIL:
предмет с этим классом считается FAIL при любой отметке (путь не умеет сам доказывать внутреннюю структуру).
Ворота GATE утверждены специалистом 01.10 до рендера и заморожены в selection.json; машинный false-accept
только показываем (WATCH), приёмка от него не зависит. WRONG_IDENTITY при неверном промпте -
UPSTREAM_IDENTITY_FAIL: в общей доле FAIL, но отдельно renderer_evaluable_human_pass. В пак ничего. Всё - в art/objects/generation/probes/photo-struct-accept-v1/.
"""
import argparse
import csv
import hashlib
import json
import math
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

from PIL import Image                   # noqa: E402

import photo_accept as pa               # noqa: E402

ENC = "utf-8-sig"
OUT = os.path.join("art", "objects", "generation", "probes", "photo-struct-accept-v1")
SEED = "photo-struct-accept-v1"
SEED0 = 3713                            # зерно рендера: SEED0 + rank (у v1 - 2713)
STRATA = pa.STRATA                      # те же квоты, что у v1: 20 предметов
RESERVE = 1.5                           # на проверку опознания - с запасом под отказы
ID_LOG = os.path.join("art", "objects", "discovery", "identity_decisions.tsv")
IDENT = os.path.join("art", "objects", "discovery", "asset_identity.tsv")
PROBES = [("art/objects/generation/probes/photo-accept-v1/jobs.json", "photo-accept-v1"),
          ("art/objects/generation/probes/struct-guide-v1/jobs.json", "struct-guide-v1")]
# порядок, в котором берём уровни опознания внутри страта: чем твёрже, тем раньше
LEVEL_ORDER = ["HUMAN_CONFIRMED", "MODEL_AGREEMENT", "MODEL_AGREEMENT_NAME", "MODEL_HARD", "OLD_AGENT"]
WIDE_LEVELS = {"HARD": "MODEL_HARD", "OLD_AGENT": "OLD_AGENT"}
CLASSES = ["PIXEL_STEP_TRACING", "DETAIL_LOSS", "MAJOR_GEOMETRY", "INVENTED_DETAIL", "BAD_MATERIAL", "BAD_ALPHA",
           "WRONG_IDENTITY"]
OUTCOMES = ["PASS", "PARTIAL", "FAIL"]
CYR = re.compile("[а-яА-ЯёЁ]")
HARD_FAIL = {"INVENTED_DETAIL"}        # специалист 01.10: HUMAN_REVIEW / HARD_FAIL
# Ворота утверждены специалистом 01.10 до рендера, n = 20, в штуках. Приёмка пройдена, только если ВСЕ:
GATE = {"n": 20,
        "human_pass_min": 16,           # PARTIAL - не PASS
        "pixel_step_max": 2,
        "major_geometry_max": 2,
        "invented_detail_max": 2,       # и каждый INVENTED_DETAIL - FAIL (HARD_FAIL)
        "wrong_identity_prompt_ok_max": 0,  # WRONG_IDENTITY при верном промпте; не отмеченный промпт - как верный
        "detail_loss_fail_max": 2,      # DETAIL_LOSS у предмета с итогом FAIL
        "systemic_defect_max": 2}       # новый одинаковый дефект (тег на странице) - не больше чем у 2 предметов
# Смотрим, но приёмка от этого не зависит
WATCH = {"detail_loss_any_max": 4,      # DETAIL_LOSS у PASS/PARTIAL/FAIL вместе
         "technical_false_accept": "machine PASS + human FAIL",
         "technical_false_reject": "machine не PASS + human PASS"}


def load(path, default=None):
    return pa.load(path, default)


def dump(obj, path):
    pa.dump(obj, path)


def read_tsv(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding=ENC, newline="") as f:
        return list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))


def seen():
    """photo_accept.seen и всё, что видели после: photo-accept-v1 и struct-guide-v1 (ассет и кадр-источник)."""
    out = _seen0()
    for p, tag in PROBES:
        for j in load(p, []) or []:
            out.setdefault(j["asset_id"].upper(), tag)
            out.setdefault(j["src"].upper(), tag)
    return out


_seen0 = pa.seen


def decisions():
    """Последнее решение опознания по ассету из журнала review_server."""
    return {r["asset_id"]: r for r in read_tsv(ID_LOG)}


# ---------------------------------------------------------------- список на проверку опознания

def candidates():
    import pilot_batch as pbt
    keep_seen, keep_lv = pa.seen, pbt.LEVELS
    pa.seen = seen
    pbt.LEVELS = dict(pbt.LEVELS, **WIDE_LEVELS)
    try:
        cands, drop = pa.pool()
    finally:
        pa.seen, pbt.LEVELS = keep_seen, keep_lv
    ident = {r["asset_id"]: r for r in read_tsv(IDENT)}
    dec = decisions()
    fams = {}
    out = []
    for c in cands:
        key = c["asset_id"] if c["asset_id"] in ident else c["family"]
        if key not in ident:
            drop["нет карточки опознания"] += 1
            continue
        d = dec.get(key, {}).get("decision") or ""
        st = ident[key]["status"]
        if d in ("UNKNOWN", "SKIP", "NOT_OBJECT") or (not d and st in ("UNKNOWN", "SKIP", "NOT_OBJECT")):
            drop["опознание отклонено человеком"] += 1
            continue
        row = ident[key]
        card = (dec[key]["identity"] if d == "EDIT" else row["identity"] or row["proposed"]).strip()
        if not card or card.upper() == "UNKNOWN":       # модели разошлись, описания нет - нечего подтверждать
            drop["нет описания на карточке (модели разошлись)"] += 1
            continue
        if key in fams:
            drop["та же карточка, что у %s" % fams[key]] += 1
            continue
        fams[key] = c["asset_id"]
        if d in ("CONFIRM", "EDIT") or st in ("HUMAN_CONFIRMED", "HUMAN_EDITED"):
            c["level"] = "HUMAN_CONFIRMED"
        out.append(dict(c, ident_key=key, card=card, name="ps_%s" % c["asset_id"].replace(":", "_").lower()))
    rnd = random.Random(int(hashlib.sha256((SEED + "-candidates").encode()).hexdigest()[:12], 16))
    chosen, used_sets, picked, short = set(), set(), [], []
    for name, n in STRATA:
        want = math.ceil(n * RESERVE)
        ok = sorted((c for c in out if c["asset_id"] not in chosen and pa.stratum_ok(name, c)),
                    key=lambda c: c["asset_id"])
        rnd.shuffle(ok)
        ok.sort(key=lambda c: LEVEL_ORDER.index(c["level"]))     # устойчивая: внутри уровня - перемешано
        got = 0
        for strict in (True, False):
            for c in ok:
                if got >= want:
                    break
                st = {c["src"].split(":")[0], c["asset_id"].split(":")[0]}
                if c["asset_id"] in chosen or (strict and st & used_sets):
                    continue
                used_sets |= st
                chosen.add(c["asset_id"])
                picked.append(dict(c, stratum=name))
                got += 1
        if got < want:
            short.append("%s: %d из %d (годных %d)" % (name, got, want, len(ok)))
    os.makedirs(OUT, exist_ok=True)
    dump(picked, os.path.join(OUT, "candidates.json"))
    # вид «десятка» review_server: порядок списка, категория - страт
    dump([{"category": c["stratum"], "asset_id": c["ident_key"], "rank": c["rank"], "places": c["places"],
           "kind": "один", "identity_status": c["level"], "identity": c["card"], "for": c["asset_id"]}
          for c in picked], os.path.join(OUT, "identity_list.json"))
    dump({"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "seed": SEED, "reserve": RESERVE,
          "strata": dict(STRATA), "pool": len(out), "dropped": dict(drop), "short": short,
          "levels_in_pool": dict(Counter(c["level"] for c in out)),
          "listed": [c["asset_id"] for c in picked]}, os.path.join(OUT, "candidates_manifest.json"))
    print("годных: %d (по уровню опознания %s); отсев: %s" % (
        len(out), dict(Counter(c["level"] for c in out)), dict(drop)))
    for c in picked:
        print("  %-10s %-26s %-22s px %-4d open %-3d thin %.2f lum %5.1f  %s" % (
            c["stratum"], c["asset_id"], c["level"], c["px"], c["open_px"], c["thin_share"], c["lum"], c["card"][:60]))
    for s in short:
        print("  НЕДОБОР", s)
    print("на проверку опознания: %d -> %s" % (len(picked), os.path.join(OUT, "identity_list.json")))
    print("карточки: py -3.13 tools/hdart/review_server.py --port 8779 --accept %s  (вид «десятка»)"
          % os.path.join(OUT, "identity_list.json").replace("\\", "/"))
    return picked


# ---------------------------------------------------------------- задания из подтверждённого

def confirmed_text(c, ident, dec):
    """Текст для промпта: свой текст Vitali (EDIT) или то, что стояло на карточке при «Верно» (CONFIRM)."""
    d = dec.get(c["ident_key"])
    row = ident.get(c["ident_key"], {})
    if d and d["decision"] == "EDIT":
        return d["identity"], "EDIT", d["when"]
    if d and d["decision"] == "CONFIRM":
        return row.get("identity") or row.get("proposed") or "", "CONFIRM", d["when"]
    if not d and row.get("status") in ("HUMAN_CONFIRMED", "HUMAN_EDITED"):
        return row.get("identity", ""), row["status"], row.get("when", "")
    return "", (d or {}).get("decision", ""), ""


def select():
    picked = load(os.path.join(OUT, "candidates.json"))
    if not picked:
        raise SystemExit("нет candidates.json - сначала candidates")
    ident = {r["asset_id"]: r for r in read_tsv(IDENT)}
    dec = decisions()
    ok, state = [], Counter()
    for c in picked:
        text, how, when = confirmed_text(c, ident, dec)
        state[how or "без ответа"] += 1
        if text.strip():
            ok.append(dict(c, what=text.strip(), identity_how=how, identity_when=when))
    print("ответы на карточках: %s" % dict(state))
    mixed = [c["asset_id"] for c in ok if CYR.search(c["what"])]    # комментарий человека в тексте промпта
    if mixed:
        raise SystemExit("в описании кириллица (комментарий вместо промпта) - поправить на карточке: %s" % mixed)
    jobs, short = [], []
    for name, n in STRATA:
        got = [c for c in ok if c["stratum"] == name][:n]
        jobs += got
        if len(got) < n:
            short.append("%s: %d из %d" % (name, len(got), n))
    need = sum(n for _s, n in STRATA) - len(jobs)
    extra = [c for c in ok if c not in jobs][:max(0, need)]          # недобор страта - из запаса других
    for c in extra:
        c["stratum_fill"] = True
    jobs += extra
    if len(jobs) < sum(n for _s, n in STRATA):
        for s in short:
            print("  НЕДОБОР", s)
        raise SystemExit("подтверждённых описаний %d, нужно %d - задания не пишу; ответить на карточках или добрать "
                         "кандидатов" % (len(jobs), sum(n for _s, n in STRATA)))
    for c in jobs:
        c["seed"] = SEED0 + c["rank"]
        c["group"] = c["stratum"]
    frozen = {f: pa.sha256_file(os.path.join(HERE, f)) for f in
              ("struct_guide.py", "struct_probe.py", "photo_base.py", "photo_render.py", "photo_accept.py")}
    dump(jobs, os.path.join(OUT, "jobs.json"))
    dump({"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "seed": SEED, "seed0": SEED0, "answers": dict(state),
          "short": short, "filled_from_other_strata": [c["asset_id"] for c in extra], "frozen_code": frozen,
          "variant": "C", "classes": CLASSES, "hard_fail": sorted(HARD_FAIL),
          "gate_frozen": GATE, "gate_approved": "специалист 01.10, до рендера", "watch": WATCH,
          "max_renders_per_process": 4,
          "assets": [c["asset_id"] for c in jobs]}, os.path.join(OUT, "selection.json"))
    for c in jobs:
        print("  %-10s %-26s seed %-5d %-9s %s%s" % (c["stratum"], c["asset_id"], c["seed"], c["identity_how"],
                                                   c["what"][:60], "  (из запаса)" if c.get("stratum_fill") else ""))
    for s in short:
        print("  НЕДОБОР", s)
    print("заданий %d -> %s" % (len(jobs), os.path.join(OUT, "jobs.json")))
    py = "E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe"
    print("\nрендер - через очередь видеокарты:")
    print("py -3.13 tools/gpuq.py add --name photo_struct_accept_v1 --cwd E:/OpenXCom -- %s "
          "tools/hdart/render_chunks.py --out %s --max-renders 4 -- %s tools/hdart/photo_struct_render.py"
          % (py, OUT.replace("\\", "/"), py))
    return jobs


# ---------------------------------------------------------------- technical QA

def metas():
    jobs = load(os.path.join(OUT, "jobs.json")) or []
    return jobs, {j["asset_id"]: load(os.path.join(OUT, "render", "meta", j["name"] + ".json")) for j in jobs}


def machine():
    jobs, ms = metas()
    rows = [ms[j["asset_id"]] for j in jobs if ms[j["asset_id"]]]
    cols = ["asset_id", "stratum", "outcome", "machine", "attempts"] + pa.MACHINE_CHECKS
    with open(os.path.join(OUT, "machine.tsv"), "w", encoding=ENC) as f:
        f.write("\t".join(cols + ["why"]) + "\n")
        for r in rows:
            c = r["checks"]
            f.write("\t".join([r["asset_id"], r["group"], r["outcome"], r["machine"], str(len(r["attempts"]))]
                              + [c[k][0] for k in pa.MACHINE_CHECKS]
                              + ["; ".join("%s: %s" % (k, c[k][1]) for k in pa.MACHINE_CHECKS
                                           if c[k][0] not in ("PASS", "N/A"))]) + "\n")
    n = Counter(r["outcome"] for r in rows)
    print("машина: %d из %d; %s" % (len(rows), len(jobs), ", ".join("%s %d" % kv for kv in sorted(n.items()))))
    return rows


# ---------------------------------------------------------------- страница вслепую

PAGE = """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>PHOTO STRUCT вслепую</title>
<style>
:root{--bg:#1b1b1f;--card:#26262c;--fg:#e8e8ea;--mut:#9a9aa3;--acc:#f2c14e;--ok:#3f8f5a;--mid:#8a7a2e;--bad:#a3423a}
body{background:var(--bg);color:var(--fg);font:14px/1.4 system-ui,sans-serif;margin:0;padding:16px}
h1{font-size:18px;margin:0 0 4px}.mut{color:var(--mut)}
.row{background:var(--card);border-radius:8px;padding:12px;margin:14px 0}
.cols{display:flex;gap:10px;flex-wrap:wrap;align-items:flex-start}
.col{display:flex;flex-direction:column;gap:4px;max-width:100%}
.col img{max-width:100%;border-radius:4px}.col img.px{image-rendering:pixelated}
.t{font-weight:600;color:var(--acc);font-size:12px}
.what{background:#1f1f24;border-radius:4px;padding:4px 8px;margin:6px 0;font-size:13px}
button{background:#33333b;color:var(--fg);border:1px solid #44444d;border-radius:4px;padding:2px 8px;cursor:pointer;font-size:12px}
button.on[data-v=PASS]{background:var(--ok)}button.on[data-v=PARTIAL]{background:var(--mid)}
button.on[data-v=FAIL]{background:var(--bad)}button.on.cls{background:#7a5ab8}
button.on[data-p=yes]{background:var(--ok)}button.on[data-p=no]{background:var(--bad)}
.btns{display:flex;gap:4px;flex-wrap:wrap;margin-top:6px}
input[type=text]{width:100%;box-sizing:border-box;background:#1f1f24;color:var(--fg);border:1px solid #44444d;border-radius:4px;padding:3px;margin-top:6px}
textarea{width:100%;height:180px;background:#1f1f24;color:var(--fg);box-sizing:border-box}
a{color:var(--acc)}
</style></head><body>
<h1>PHOTO STRUCT acceptance v1 - новые предметы, вслепую</h1>
<div class="mut">__N__ предметов, которых не было ни в одной пробе. Путь один: структурный эскиз -> PHOTO C ->
альфа. Вердикта машины здесь нет, порядок случайный. По каждому: PASS / PARTIAL / FAIL и классы брака (можно
несколько). Описание под номером - то, что вы подтвердили на карточке, оно и было промптом; при WRONG_IDENTITY
отметьте, верен ли был промпт. INVENTED_DETAIL считается FAIL при любой отметке. Если дефект не из списка и
повторяется на разных предметах одинаково (например, тонкие ножки пропадают одним способом) - впишите в поле
«тег дефекта» одно и то же короткое слово у каждого такого предмета. TSV внизу - прислать целиком.</div>
<div id="rows"></div>
<h2>TSV</h2><textarea id="tsv" readonly></textarea>
<script>
const DATA = __DATA__;
const CLS = __CLS__;
const OUTC = __OUTC__;
const KEY = "photo-struct-accept-v1";
let st = {}; try { st = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) {}
function save(){ try { localStorage.setItem(KEY, JSON.stringify(st)); } catch (e) {} tsv(); }
function tsv(){
  const L = [["asset_id", "outcome", "classes", "prompt_ok", "defect", "note"].join("\\t")];
  for (const r of DATA) { const s = st[r.asset] || {};
    L.push([r.asset, s.o || "", Object.keys(s.k || {}).filter(k => s.k[k]).join(","), s.p || "",
            (s.d || "").replace(/[\\t\\n]/g, " "), (s.n || "").replace(/[\\t\\n]/g, " ")].join("\\t")); }
  document.getElementById("tsv").value = L.join("\\n");
}
const root = document.getElementById("rows");
DATA.forEach((r, i) => {
  const s = st[r.asset] = st[r.asset] || {}; s.k = s.k || {};
  const row = document.createElement("div"); row.className = "row";
  row.innerHTML = `<div><b>${i + 1}. ${r.asset}</b></div><div class="what">${r.what}</div>`;
  const cols = document.createElement("div"); cols.className = "cols"; row.appendChild(cols);
  for (const [f, t, px] of r.img) cols.insertAdjacentHTML("beforeend",
    `<div class="col"><div class="t">${t}</div><img class="${px ? "px" : ""}" src="${f}" width="${r.w}" height="${r.h}" loading="lazy"></div>`);
  cols.insertAdjacentHTML("beforeend", `<div class="col"><div class="t">сырой ответ</div><a href="${r.raw}" target="_blank">открыть</a></div>`);
  const ob = document.createElement("div"); ob.className = "btns";
  for (const v of OUTC) { const e = document.createElement("button"); e.textContent = v; e.dataset.v = v;
    if (s.o === v) e.classList.add("on");
    e.onclick = () => { s.o = s.o === v ? "" : v; ob.querySelectorAll("button").forEach(x => x.classList.toggle("on", x.dataset.v === s.o)); save(); };
    ob.appendChild(e); }
  row.insertAdjacentHTML("beforeend", `<div class="t" style="margin-top:8px">итог</div>`); row.appendChild(ob);
  const kb = document.createElement("div"); kb.className = "btns";
  for (const v of CLS) { const e = document.createElement("button"); e.textContent = v; e.className = "cls";
    if (s.k[v]) e.classList.add("on");
    e.onclick = () => { s.k[v] = !s.k[v]; e.classList.toggle("on", s.k[v]); save(); }; kb.appendChild(e); }
  row.insertAdjacentHTML("beforeend", `<div class="t" style="margin-top:8px">классы брака</div>`); row.appendChild(kb);
  const pb = document.createElement("div"); pb.className = "btns";
  for (const [v, t] of [["yes", "промпт был верен"], ["no", "промпт был неверен"]]) {
    const e = document.createElement("button"); e.textContent = t; e.dataset.p = v; if (s.p === v) e.classList.add("on");
    e.onclick = () => { s.p = s.p === v ? "" : v; pb.querySelectorAll("button").forEach(x => x.classList.toggle("on", x.dataset.p === s.p)); save(); };
    pb.appendChild(e); }
  row.insertAdjacentHTML("beforeend", `<div class="t" style="margin-top:8px">при WRONG_IDENTITY</div>`); row.appendChild(pb);
  const d = document.createElement("input"); d.type = "text"; d.placeholder = "тег дефекта (новый, повторяющийся)";
  d.value = s.d || ""; d.oninput = () => { s.d = d.value; save(); }; row.appendChild(d);
  const n = document.createElement("input"); n.type = "text"; n.placeholder = "заметка"; n.value = s.n || "";
  n.oninput = () => { s.n = n.value; save(); }; row.appendChild(n);
  root.appendChild(row);
});
tsv();
</script></body></html>"""


def page():
    import map_mockup as mm
    import obj_series as osr
    import shutil
    world = mm.World()
    jobs, ms = metas()
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
        meta = ms[j["asset_id"]]
        if meta is None:
            print("  %-26s нет рендера" % j["asset_id"])
            continue
        piece = Image.open(meta["piece"]).convert("RGBA")
        s, f = j["src"].split(":")
        orig = world.sprite(s.lower(), int(f), None).convert("RGBA")
        tag = "%02d" % n
        imgs = [(osr.on_floor(orig.resize(piece.size, Image.NEAREST), piece.size), "оригинал x4", True),
                (osr.on_floor(piece, piece.size), "новый на полу", False),
                (pa.on_bg(piece, (255, 0, 255)), "новый на пурпурном", False),
                (pa.on_bg(piece, (235, 235, 235)), "новый на светлом", False)]
        img = []
        for k, (im, t, px) in enumerate(imgs):
            fn = "%s_%d.png" % (tag, k)
            im.resize((cw, ch), Image.NEAREST if px else Image.LANCZOS).save(os.path.join(d, fn))
            img.append((fn, t, px))
        raw = "%s_raw.png" % tag
        shutil.copyfile(meta["attempts"][-1]["raw"], os.path.join(d, raw))
        data.append({"asset": j["asset_id"], "what": j["what"], "img": img, "raw": raw, "w": cw, "h": ch})
    html = PAGE.replace("__DATA__", json.dumps(data, ensure_ascii=False)).replace(
        "__CLS__", json.dumps(CLASSES)).replace("__OUTC__", json.dumps(OUTCOMES)).replace("__N__", str(len(data)))
    with open(os.path.join(d, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    url = os.path.relpath(d, os.path.join("art", "objects", "generation")).replace(os.sep, "/")
    print("страница: http://localhost:8778/%s/index.html (%d предметов из %d заданий)" % (url, len(data), len(jobs)))


# ---------------------------------------------------------------- отчёт

def read_verdicts(path):
    out = {}
    with open(path, encoding=ENC) as f:
        head = f.readline().rstrip("\r\n").split("\t")
        for line in f:
            if line.strip():
                r = dict(zip(head, line.rstrip("\r\n").split("\t")))
                r["classes"] = {c for c in r.get("classes", "").split(",") if c}
                out[r["asset_id"]] = r
    return out


def effective(r):
    """Итог с правилом HARD_FAIL: INVENTED_DETAIL - FAIL при любой отметке."""
    if r["classes"] & HARD_FAIL:
        return "FAIL"
    return r.get("outcome", "")


def upstream(r):
    """UPSTREAM_IDENTITY_FAIL: модель нарисовала то, что ей сказали, а сказали неверно - не поражение рендера."""
    return "WRONG_IDENTITY" in r["classes"] and r.get("prompt_ok") == "no"


def summarize(rows, n_jobs=None):
    """rows: [{asset_id, machine, outcome (человек), classes, prompt_ok, defect}] -> (метрики, ворота, смотрим).
    Ворота в штуках из GATE; оценены не все задания - ворота не решены (None)."""
    n = len(rows)
    eff = Counter(effective(r) for r in rows)
    count = {c: [r["asset_id"] for r in rows if c in r["classes"]] for c in CLASSES}
    wi = [r for r in rows if "WRONG_IDENTITY" in r["classes"]]
    wi_ok = [r["asset_id"] for r in wi if r.get("prompt_ok") == "yes"]
    wi_unk = [r["asset_id"] for r in wi if r.get("prompt_ok") not in ("yes", "no")]
    up = [r["asset_id"] for r in rows if upstream(r)]
    ev = [r for r in rows if not upstream(r)]
    ev_pass = sum(effective(r) == "PASS" for r in ev)
    dl_fail = [r["asset_id"] for r in rows if "DETAIL_LOSS" in r["classes"] and effective(r) == "FAIL"]
    tags = {}
    for r in rows:
        t = (r.get("defect") or "").strip().lower()
        if t:
            tags.setdefault(t, []).append(r["asset_id"])
    tfa = [r["asset_id"] for r in rows if r["machine"] == "PASS" and effective(r) == "FAIL"]
    tfr = [r["asset_id"] for r in rows if r["machine"] != "PASS" and effective(r) == "PASS"]
    hard = [r["asset_id"] for r in rows if r["classes"] & HARD_FAIL and r.get("outcome") != "FAIL"]
    m = {"n": n, "human_pass": eff["PASS"], "human_partial": eff["PARTIAL"], "human_fail": eff["FAIL"],
         "overall_human_pass": "%d/%d" % (eff["PASS"], n),
         "renderer_evaluable_human_pass": "%d/%d" % (ev_pass, len(ev)),
         "upstream_identity_fail": up,
         "class_count": {c: len(v) for c, v in count.items()}, "class_assets": count,
         "wrong_identity_prompt_ok": wi_ok, "wrong_identity_prompt_unmarked": wi_unk,
         "detail_loss_fail": dl_fail, "defect_tags": tags,
         "hard_fail_overrides": hard,
         "technical_false_accept": tfa, "technical_false_reject": tfr,
         "machine_pass": sum(r["machine"] == "PASS" for r in rows)}
    G = GATE
    checks = {
        "human PASS >= %d/%d (PARTIAL не PASS)" % (G["human_pass_min"], G["n"]): eff["PASS"] >= G["human_pass_min"],
        "PIXEL_STEP_TRACING <= %d" % G["pixel_step_max"]: len(count["PIXEL_STEP_TRACING"]) <= G["pixel_step_max"],
        "MAJOR_GEOMETRY <= %d" % G["major_geometry_max"]: len(count["MAJOR_GEOMETRY"]) <= G["major_geometry_max"],
        "INVENTED_DETAIL <= %d, каждый - FAIL" % G["invented_detail_max"]:
            len(count["INVENTED_DETAIL"]) <= G["invented_detail_max"],
        "WRONG_IDENTITY при верном промпте <= %d" % G["wrong_identity_prompt_ok_max"]:
            len(wi_ok) + len(wi_unk) <= G["wrong_identity_prompt_ok_max"],
        "DETAIL_LOSS с итогом FAIL <= %d" % G["detail_loss_fail_max"]: len(dl_fail) <= G["detail_loss_fail_max"],
        "новый повторяющийся дефект < %d предметов" % (G["systemic_defect_max"] + 1):
            all(len(v) <= G["systemic_defect_max"] for v in tags.values())}
    complete = n_jobs is None or n == n_jobs == G["n"]
    gate = {"checks": checks, "complete": complete, "passed": all(checks.values()) if complete else None}
    watch = {"DETAIL_LOSS всего <= %d" % WATCH["detail_loss_any_max"]:
                 len(count["DETAIL_LOSS"]) <= WATCH["detail_loss_any_max"],
             "TECHNICAL_FALSE_ACCEPT": "%d из %d machine PASS" % (len(tfa), m["machine_pass"]),
             "TECHNICAL_FALSE_REJECT": "%d из %d human PASS" % (len(tfr), eff["PASS"])}
    return m, gate, watch


_PROC = None


def proc_index(meta):
    """Которым по счёту после загрузки модели нарисован итоговый ответ предмета (renders.jsonl), или None."""
    global _PROC
    if _PROC is None:
        _PROC = {}
        p = os.path.join(OUT, "renders.jsonl")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                for s in f:
                    if s.strip():
                        r = json.loads(s)
                        if r.get("process_render"):
                            _PROC[r["raw"]] = "%s#%d" % (r.get("pid", "?"), r["process_render"])
    return _PROC.get(meta["attempts"][-1]["raw"]) if meta.get("attempts") else None


def report(path):
    jobs, ms = metas()
    human = read_verdicts(path)
    rows, unrated = [], []
    for j in jobs:
        meta, h = ms[j["asset_id"]], human.get(j["asset_id"])
        if meta is None:
            continue
        if not h or h.get("outcome") not in OUTCOMES:
            unrated.append(j["asset_id"])
            continue
        rows.append({"asset_id": j["asset_id"], "stratum": j["stratum"], "machine": meta["machine"],
                     "outcome": h["outcome"], "classes": h["classes"], "prompt_ok": h.get("prompt_ok", ""),
                     "defect": h.get("defect", ""), "note": h.get("note", ""), "how": j.get("identity_how", ""),
                     "process_render": proc_index(meta)})
    if not rows:
        raise SystemExit("ни одного предмета с вердиктом и рендером")
    m, gate, watch = summarize(rows, len(jobs))
    res = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "verdicts": path, "metrics": m, "unrated": unrated,
           "gate_frozen": GATE, "gate": gate, "watch": watch,
           "rows": [dict(r, classes=sorted(r["classes"]), effective=effective(r)) for r in rows]}
    dump(res, os.path.join(OUT, "report.json"))
    verdict = {True: "**ПРОЙДЕНА**", False: "**НЕ ПРОЙДЕНА**", None: "**не решена** (оценены не все %d)" % GATE["n"]}
    L = ["# PHOTO_STRUCT_ACCEPTANCE_V1 - итог", "",
         "Приёмка: %s." % verdict[gate["passed"]], "",
         "Вердикты: `%s`; с вердиктом и рендером %d, без оценки %d%s." % (
             path, len(rows), len(unrated), (" (" + ", ".join(unrated) + ")") if unrated else ""), "",
         "Итог человека с правилом HARD_FAIL (INVENTED_DETAIL - FAIL): PASS %d, PARTIAL %d, FAIL %d." % (
             m["human_pass"], m["human_partial"], m["human_fail"]),
         "overall_human_pass %s; renderer_evaluable_human_pass %s (без UPSTREAM_IDENTITY_FAIL: %s)." % (
             m["overall_human_pass"], m["renderer_evaluable_human_pass"],
             ", ".join(m["upstream_identity_fail"]) or "нет"), "",
         "| ворота (утверждены специалистом 01.10 до рендера) | |", "|---|---|"]
    L += ["| %s | %s |" % (k, "да" if v else "**нет**") for k, v in gate["checks"].items()]
    L += ["", "| класс | предметов |", "|---|---|"]
    L += ["| %s | %d |" % (c, v) for c, v in m["class_count"].items()]
    L += ["", "WRONG_IDENTITY: промпт верен %s; не отмечено (считается верным) %s." % (
        m["wrong_identity_prompt_ok"] or "-", m["wrong_identity_prompt_unmarked"] or "-"),
          "Теги дефектов: %s." % ("; ".join("%s - %s" % (t, ", ".join(a)) for t, a in m["defect_tags"].items())
                                  or "нет"),
          "", "Смотрим, приёмка не зависит: " + "; ".join("%s - %s" % (k, ("да" if v else "нет") if v in (True, False)
                                                                     else v) for k, v in watch.items()),
          "TECHNICAL_FALSE_ACCEPT: %s. TECHNICAL_FALSE_REJECT: %s." % (
              ", ".join(m["technical_false_accept"]) or "-", ", ".join(m["technical_false_reject"]) or "-"), "",
          "| предмет | страт | опознание | рендер в процессе | машина | человек | итог | классы | тег | заметка |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    L += ["| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
        r["asset_id"], r["stratum"], r["how"], r["process_render"] or "-", r["machine"], r["outcome"], effective(r),
        ",".join(sorted(r["classes"])), r["defect"], r["note"]) for r in rows]
    with open(os.path.join(OUT, "report.md"), "w", encoding=ENC) as f:
        f.write("\n".join(L) + "\n")
    print("\n".join(L))
    return res


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["candidates", "select", "machine", "page", "report"])
    ap.add_argument("--verdicts", default=os.path.join(OUT, "verdicts_vitali.tsv"))
    a = ap.parse_args()
    os.chdir(ROOT)
    {"candidates": candidates, "select": select, "machine": machine, "page": page,
     "report": lambda: report(a.verdicts)}[a.cmd]()


if __name__ == "__main__":
    main()
