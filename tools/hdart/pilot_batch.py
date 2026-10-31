#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Пилот продакшна PILOT_PRODUCTION_V1: отбор простых рукотворных предметов, лист быстрой проверки, заморозка партии.

Решение специалиста 30.09: не ждать решения для всех классов, а пустить узкий класс, который приёмка подтвердила
(acc-5e9f63c421c0: простые одиночные предметы), на 100-200 реальных ассетах. Vitali не подтверждает каждый, а
только выкидывает явный мусор; по умолчанию кандидат остаётся.

Отбор (select) из плана генерации, без модели:
  взято:   GENERATE, один кадр, класс object, рукотворное, опознание HUMAN_CONFIRMED / HUMAN_EDITED или согласие
           двух моделей (AUTO_REVIEW_EASY - одно имя или синоним; HUMAN_REVIEW_LIGHT - имя одно, категория разная);
           зеркала семейства разрешены (вывод зеркала прошёл приёмку).
  отсеяно: природа и рельеф, семейства с перекрасками (DERIVE_RECOLOR FAIL), сложная геометрия по названию
           (стулья, лестницы, решётки, рамы, перила - VILFRNITURE:2 потерял рейки), открытый разбор семейства,
           другой бок (ALT_VIEW FAIL), составные, анимации, стены и полы, спорное и старое непроверенное опознание.

    py -3.13 tools/hdart/pilot_batch.py select                  (сколько и почему, без картинок)
    py -3.13 tools/hdart/pilot_batch.py sheet                   (лист art/objects/generation/pilot_v1/index.html)
    py -3.13 tools/hdart/pilot_batch.py freeze --exclusions <tsv> | --no-exclusions
                                                                  (партия batches/pilot-v1-<id>.json, только чтение)
    py -3.13 tools/hdart/pilot_batch.py check    <id>          (BATCH_CURRENT / BATCH_STALE)
    py -3.13 tools/hdart/pilot_batch.py refreeze pilot-v1-<id> (тот же список -> pilot-v2-<id> с заданиями модели)

Партия замораживается снимком: генерация берёт её, а не живой generation.tsv. Снимок списка (pilot-v1) не
запускается: политика генератора в нём не записана. refreeze делает из того же списка партию в формате приёмки
(generator_policy_rev, задания, jobs_hash, use=pilot) - её запускает acceptance_run.py run, как приёмку.
"""
import argparse
import csv
import hashlib
import html
import io
import json
import os
import re
import sys
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.dirname(os.path.dirname(HERE))
ENC = "utf-8-sig"
GEN = os.path.join(ROOT, "art", "objects", "generation")
DISC = os.path.join(ROOT, "art", "objects", "discovery")
PLAN = os.path.join(GEN, "generation.tsv")
IDENT = os.path.join(DISC, "asset_identity.tsv")
PROPS = os.path.join(DISC, "proposals.json")
FAMS = os.path.join(ROOT, "art", "objects", "families", "families.json")
OUT = os.path.join(GEN, "pilot_v1")
BATCHES = os.path.join(GEN, "batches")
POLICY = "PILOT_PRODUCTION_V1"
GENERATOR_REV = "438d6841d129"
APPROVED_FOR = "PRODUCTION_PILOT_SIMPLE_OBJECTS"
VERDICTS = ("OK", "WRONG_IDENTITY", "COMPLEX_GEOMETRY", "OTHER")
LEVELS = {"HUMAN": "HUMAN_CONFIRMED", "EASY": "MODEL_AGREEMENT", "LIGHT": "MODEL_AGREEMENT_NAME"}
NATURE_CATS = {"plant or nature", "rock or terrain relief", "wall or building part"}
NATURE = re.compile(r"rock|cliff|tree|bush|shrub|grass|plant|stone|boulder|\blog|stump|flower|fern|palm|weed|cactus|"
                    r"vine|moss|dirt|mud|sand|snow|\bice\b|crystal|coral|mushroom|root|branch|lea(f|ves)|hedge|reed|"
                    r"wall|ruin|rubble|crater|gravel|soil|hill|mound|dune", re.I)
GEOMETRY = re.compile(r"chair|stool|bench|fence|rail|grat|grid|lattice|ladder|stair|step|shelf|shelv|rack|frame|"
                      r"truss|scaffold|cage|bars|mesh|\bnet\b|antenna|pylon|tower|window|blind|slat|comb|spoke|wheel",
                      re.I)


def h12(obj):
    return hashlib.sha1(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]


def sha256_file(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def read_tsv(p):
    with open(p, encoding=ENC, newline="") as f:
        return list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))


def level_of(x):
    if x.get("status") in ("HUMAN_CONFIRMED", "HUMAN_EDITED"):
        return "HUMAN"
    return {"AUTO_REVIEW_EASY": "EASY", "HUMAN_REVIEW_LIGHT": "LIGHT", "HUMAN_REVIEW_HARD": "HARD",
            "UNKNOWN": "UNKNOWN"}.get(x.get("review_level", ""), "OLD_AGENT")


def names_of(aid, x, props):
    """(название для генерации, второе название модели или '', категории)."""
    if x.get("status") in ("HUMAN_CONFIRMED", "HUMAN_EDITED"):
        return x.get("identity", ""), "", {x.get("proposed_category", "")}
    p = props.get(aid)
    if isinstance(p, dict) and p.get("first"):
        a, b = p["first"], p.get("second") or {}
        name = p.get("proposed_name") or a.get("proposed_name", "")
        other = b.get("proposed_name", "")
        return name, ("" if other.strip().lower() == name.strip().lower() else other), \
            {a.get("proposed_category", ""), b.get("proposed_category", "")}
    return x.get("proposed_name") or x.get("proposed", ""), "", {x.get("proposed_category", "")}


def open_questions(fams):
    """Ассеты с незакрытым вопросом семейства - ЛЮБЫМ, включая необязательные для плана (alternate_view_weak):
    канонический кадр семейства с кандидатами на проверке и сами кандидаты. obj_generation такие вопросы
    необязательного вида заказом не держит, а заморозка (acceptance_plan.plan_one) держит - отбор обязан
    отсекать не мягче заморозки (TAVERN:15, 30.09)."""
    out = set()
    for fm in fams:
        if fm.get("review"):
            out.add(fm["family_id"].upper())
            out |= {m["keys"][0].upper() for m in fm["review"]}
    return out


def select():
    """-> (кандидаты, счёт отсева по причинам). Причина - первая сработавшая, в порядке списка."""
    rows = read_tsv(PLAN)
    with open(FAMS, encoding=ENC) as f:
        questions = open_questions(json.load(f))
    ids = {r["asset_id"]: r for r in read_tsv(IDENT)}
    with open(PROPS, encoding=ENC) as f:
        props = json.load(f)
    with_alt = {r["family"] for r in rows if r["action"] == "GENERATE_WITH"}
    recolors = Counter(r["family"] for r in rows if r["action"] == "DERIVE" and r["relation"] == "recolor")
    mirrors = {}
    for r in rows:
        if r["action"] == "DERIVE" and r["relation"] == "mirror":
            mirrors.setdefault(r["family"], []).append(r["asset_id"])
    out, drop = [], Counter()
    for r in rows:
        if r["action"] != "GENERATE":
            continue
        aid, fam = r["asset_id"], r["family"] or r["asset_id"]
        x = ids.get(aid) or ids.get(r["family"]) or {}
        lv = level_of(x)
        name, other, cats = names_of(aid, x, props)
        text = " ".join((name, other))
        cats -= {""}
        why = next((w for w, bad in (
            ("не один кадр (составной, анимация)", r["kind"] != "один"),
            ("не класс object (стена, пол, рельеф под вопросом)", r["asset_class"] != "object"),
            ("разбор семейства или другой бок", "in_review" in r["blockers"] or "family_review" in r["blockers"]
             or r["family"] in with_alt or aid.upper() in questions or fam.upper() in questions),
            ("похож на кусок большего (R-153)", "part_fragment_suspect" in r["blockers"]),
            ("опознание спорное, старое или нет (%s)" % lv, lv not in LEVELS),
            ("природа или рельеф", (cats and cats <= NATURE_CATS) or (not cats and NATURE.search(text))),
            ("семейство с перекрасками", recolors[fam] > 0),
            ("сложная геометрия по названию", bool(GEOMETRY.search(text))),
        ) if bad), None)
        if why:
            drop[why] += 1
            continue
        out.append({"asset_id": aid, "family": fam, "rank": int(x["rank"]), "name": name, "other_name": other,
                    "categories": sorted(cats), "level": LEVELS[lv], "mirrors": mirrors.get(fam, []),
                    "places": int(r["places"] or 0), "input_hash": r["input_hash"],
                    "identity_rev": x.get("identity_rev", "")})
    out.sort(key=lambda c: (-c["places"], c["asset_id"]))
    return out, drop


def report_select(cands, drop):
    n_gen = sum(drop.values()) + len(cands)
    print("GENERATE в плане: %d" % n_gen)
    for w, v in drop.items():
        print("  - %-48s %5d" % (w, v))
    print("кандидатов %s: %d, кадров с зеркалами %d, мест на картах %d" % (
        POLICY, len(cands), sum(1 + len(c["mirrors"]) for c in cands), sum(c["places"] for c in cands)))
    print("  по уровню: %s" % ", ".join("%s %d" % kv for kv in Counter(c["level"] for c in cands).most_common()))


# ------------------------------------------------------------------ лист

def sheet():
    import review_server as rs
    from PIL import Image
    cands, drop = select()
    report_select(cands, drop)
    with open(rs.ITEMS, encoding=ENC) as f:
        items = {it["rank"]: it for it in json.load(f)}

    class Holder:
        pass
    holder = Holder()
    holder.items = items
    rs.CACHE = os.path.join(OUT, "_render_cache")          # свой кэш: ранги страницы проверки могли сдвинуться
    rend = rs.Renders(holder)
    img = os.path.join(OUT, "img")
    os.makedirs(img, exist_ok=True)
    cards = []
    for n, c in enumerate(cands, 1):
        stem = c["asset_id"].replace(":", "_")
        raw = rend.asset(c["rank"])
        if raw is None:
            raise SystemExit("%s: нет кадра" % c["asset_id"])
        Image.open(io.BytesIO(raw)).save(os.path.join(img, stem + "_sprite.png"))
        ctx = rend.context(c["rank"])
        has_map = ctx is not None
        if has_map:
            m = Image.open(io.BytesIO(ctx)).convert("RGB")
            m.thumbnail((360, 360))
            m.save(os.path.join(img, stem + "_map.jpg"), quality=85)
        cards.append(dict(c, n=n, stem=stem, has_map=has_map))
        if n % 20 == 0:
            print("  картинок %d/%d" % (n, len(cands)), flush=True)
    with open(os.path.join(OUT, "candidates.json"), "w", encoding=ENC) as f:
        json.dump({"policy": POLICY, "made": time.strftime("%Y-%m-%dT%H:%M:%S"), "drop": drop,
                   "sources": {"plan": sha256_file(PLAN), "identity": sha256_file(IDENT), "proposals": sha256_file(PROPS)},
                   "candidates": cands}, f, ensure_ascii=False, indent=1)
    with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as f:
        f.write(page(cards))
    print("лист -> %s" % os.path.join(OUT, "index.html"))


def page(cards):
    import base64
    img = os.path.join(OUT, "img")

    def data(fn, mime):                                  # картинки внутри страницы: лист открывается где угодно
        with open(os.path.join(img, fn), "rb") as f:
            return "data:%s;base64,%s" % (mime, base64.b64encode(f.read()).decode())

    def card(c):
        other = (' <span class="alt">/ %s</span>' % html.escape(c["other_name"])) if c["other_name"] else ""
        mir = (' <span class="tag">+%d зеркало</span>' % len(c["mirrors"])) if c["mirrors"] else ""
        mp = ('<img class="map" src="%s" alt="">' % data(c["stem"] + "_map.jpg", "image/jpeg")) if c["has_map"] \
            else '<div class="map none">нет карты</div>'
        btns = "".join('<button data-v="%s">%s</button>' % (v, v.replace("_", " ")) for v in VERDICTS)
        return ('<div class="card" data-id="%s"><div class="pics"><img class="spr" src="%s" alt="">%s'
                '</div><div class="meta"><div class="num">#%d <code>%s</code></div><div class="name">%s%s</div>'
                '<div class="lvl %s">%s</div><div class="small">мест на картах %d%s</div>'
                '<div class="btns">%s</div><input class="note" placeholder="что не так" hidden></div></div>') % (
            html.escape(c["asset_id"]), data(c["stem"] + "_sprite.png", "image/png"), mp, c["n"], html.escape(c["asset_id"]), html.escape(c["name"]),
            other, c["level"].lower(), c["level"], c["places"], mir, btns)
    body = "\n".join(card(c) for c in cards)
    return PAGE.replace("{{N}}", str(len(cards))).replace("{{CARDS}}", body).replace("{{POLICY}}", POLICY)


PAGE = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Пилот: быстрый просмотр</title>
<style>
:root{--bg:#141418;--card:#1e1e24;--line:#34343c;--text:#e8e8ea;--mute:#9a9aa4;--ok:#2f7d4f;--bad:#b23a3a;
--geo:#b0782a;--oth:#5a5ab8;--acc:#e6b422}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.35 system-ui,sans-serif}
header{position:sticky;top:0;z-index:5;background:#101014ee;border-bottom:1px solid var(--line);padding:10px 16px;
display:flex;gap:16px;flex-wrap:wrap;align-items:center}
header b{color:var(--acc)}label{color:var(--mute)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:10px;padding:12px 16px 220px}
.card{background:var(--card);border:2px solid var(--line);border-radius:8px;padding:8px}
.card.x-WRONG_IDENTITY{border-color:var(--bad)}.card.x-COMPLEX_GEOMETRY{border-color:var(--geo)}
.card.x-OTHER{border-color:var(--oth)}
.pics{display:flex;gap:6px;align-items:flex-start}
.spr{width:128px;height:160px;object-fit:contain;image-rendering:pixelated;background:#0c0c0f;border-radius:4px}
.map{width:calc(100% - 134px);max-height:160px;object-fit:contain;background:#0c0c0f;border-radius:4px}
.map.none{display:flex;align-items:center;justify-content:center;color:var(--mute);height:160px}
.num{color:var(--mute);margin-top:6px}code{color:var(--text)}
.name{font-size:16px;font-weight:600;margin:2px 0}.alt{color:var(--mute);font-weight:400}
.lvl{display:inline-block;font-size:11px;padding:1px 6px;border-radius:3px;background:#2a2a33}
.lvl.human_confirmed{background:#23452f}.small{color:var(--mute);font-size:12px;margin-top:2px}
.tag{color:var(--acc)}
.btns{display:flex;gap:4px;flex-wrap:wrap;margin-top:6px}
.btns button{flex:1;min-width:60px;padding:5px 4px;border:1px solid var(--line);border-radius:4px;background:#26262e;
color:var(--text);cursor:pointer;font-size:12px}
.btns button.on[data-v=OK]{background:var(--ok)}.btns button.on[data-v=WRONG_IDENTITY]{background:var(--bad)}
.btns button.on[data-v=COMPLEX_GEOMETRY]{background:var(--geo)}.btns button.on[data-v=OTHER]{background:var(--oth)}
.note{width:100%;margin-top:6px;padding:5px;background:#101014;color:var(--text);border:1px solid var(--line);
border-radius:4px}
footer{position:fixed;bottom:0;left:0;right:0;background:#101014f2;border-top:1px solid var(--line);padding:8px 16px}
textarea{width:100%;height:110px;background:#0c0c0f;color:var(--text);border:1px solid var(--line);font:12px monospace}
footer button{padding:6px 14px;background:var(--acc);border:0;border-radius:4px;font-weight:600;cursor:pointer}
</style></head><body>
<header><div><b>{{POLICY}}</b>: {{N}} кандидатов. По умолчанию всё OK - отметь только явный мусор.</div>
<div id="cnt"></div><label><input type="checkbox" id="only"> только исключения</label></header>
<div class="grid">
{{CARDS}}
</div>
<footer><div style="display:flex;gap:10px;align-items:center;margin-bottom:6px"><span>Исключения (скопируй в чат):</span>
<button id="copy">Скопировать</button><span id="copied" style="color:var(--mute)"></span></div>
<textarea id="out" readonly></textarea></footer>
<script>
const KEY="pilot_v1_verdicts";let st={};
try{st=JSON.parse(localStorage.getItem(KEY)||"{}")}catch(e){st={}}
function save(){try{localStorage.setItem(KEY,JSON.stringify(st))}catch(e){}}
function paint(card){const id=card.dataset.id,s=st[id]||{v:"OK",note:""};
card.className="card"+(s.v!=="OK"?" x-"+s.v:"");
card.querySelectorAll(".btns button").forEach(b=>b.classList.toggle("on",b.dataset.v===s.v));
const n=card.querySelector(".note");n.hidden=s.v==="OK";n.value=s.note||"";
card.style.display=(document.getElementById("only").checked&&s.v==="OK")?"none":""}
function out(){const rows=[],c={OK:0,WRONG_IDENTITY:0,COMPLEX_GEOMETRY:0,OTHER:0};
document.querySelectorAll(".card").forEach(card=>{const s=st[card.dataset.id]||{v:"OK"};c[s.v]++;
if(s.v!=="OK")rows.push(card.dataset.id+"\\t"+s.v+"\\t"+(s.note||"").replace(/[\\t\\n]/g," "))});
document.getElementById("out").value="asset_id\\tverdict\\tnote\\n"+rows.join("\\n");
document.getElementById("cnt").textContent="OK "+c.OK+" · не то "+c.WRONG_IDENTITY+" · геометрия "+
c.COMPLEX_GEOMETRY+" · другое "+c.OTHER}
document.querySelectorAll(".card").forEach(card=>{paint(card);
card.querySelectorAll(".btns button").forEach(b=>b.onclick=()=>{const id=card.dataset.id;
st[id]={v:b.dataset.v,note:(st[id]||{}).note||""};if(b.dataset.v==="OK")delete st[id];save();paint(card);out()});
card.querySelector(".note").oninput=e=>{const id=card.dataset.id;if(st[id]){st[id].note=e.target.value;save();out()}}});
document.getElementById("only").onchange=()=>document.querySelectorAll(".card").forEach(paint);
document.getElementById("copy").onclick=()=>{const t=document.getElementById("out");t.select();
try{navigator.clipboard.writeText(t.value)}catch(e){document.execCommand("copy")}
document.getElementById("copied").textContent="скопировано"};
out();
</script></body></html>
"""


# ------------------------------------------------------------------ заморозка партии

def freeze(exclusions):
    with open(os.path.join(OUT, "candidates.json"), encoding=ENC) as f:
        shown = json.load(f)
    cands, _drop = select()
    if [c["asset_id"] for c in cands] != [c["asset_id"] for c in shown["candidates"]]:
        raise SystemExit("план или опознание изменились после листа - пересобрать sheet и показать заново")
    ex = {}
    if exclusions:
        for r in read_tsv(exclusions):
            v = r.get("verdict", "").strip().upper()
            if v not in VERDICTS:
                raise SystemExit("%s: вердикт %r не из %s" % (r.get("asset_id"), v, VERDICTS))
            if r["asset_id"] not in {c["asset_id"] for c in cands}:
                raise SystemExit("%s: не из листа" % r["asset_id"])
            if v != "OK":
                ex[r["asset_id"]] = {"verdict": v, "note": r.get("note", "")}
    items = [c for c in cands if c["asset_id"] not in ex]
    body = {"policy": POLICY, "generator_rev": GENERATOR_REV, "approved_for": APPROVED_FOR, "items": items,
            "excluded": ex, "sources": shown["sources"]}
    bid = "pilot-v1-" + h12(body)
    snap = dict(body, batch_id=bid, created=time.strftime("%Y-%m-%dT%H:%M:%S"), items_hash=h12(items),
                reviewed_by="vitali", counts={"shown": len(cands), "excluded": len(ex), "items": len(items),
                                              "frames_with_mirrors": sum(1 + len(c["mirrors"]) for c in items)})
    os.makedirs(BATCHES, exist_ok=True)
    p = os.path.join(BATCHES, bid + ".json")
    with open(p, "w", encoding=ENC) as f:
        json.dump(snap, f, ensure_ascii=False, indent=1)
    os.chmod(p, 0o444)
    print("партия %s: %d из %d (исключено %d: %s) -> %s" % (
        bid, len(items), len(cands), len(ex), ", ".join("%s %d" % kv for kv in Counter(
            e["verdict"] for e in ex.values()).most_common()) or "-", p))
    return p


# ------------------------------------------------------------------ сверка и перезаморозка под политику

def load_batch(bid):
    p = os.path.join(BATCHES, bid + ".json")
    if not os.path.exists(p):
        raise SystemExit("партии %s нет" % bid)
    with open(p, encoding=ENC) as f:
        return json.load(f)


def check(bid):
    """BATCH_CURRENT (0) / BATCH_STALE (2). Партия с заданиями (refreeze) сверяется тем же acceptance_plan,
    что и приёмка, с утверждением для пилота; первый снимок (freeze, только список) - по источникам и политике."""
    import acceptance_plan as ap
    import obj_gen_spec as ogs
    snap = load_batch(bid)
    if "acceptance_batch_id" in snap:
        _snap, bad = ap.check_batch(bid)
    else:
        gen = ogs.spec()
        bad = []
        if snap.get("generator_policy_rev") != gen["generator_policy_rev"]:
            bad.append(("*", "STALE", ["generator_policy_rev: в снимке %s, сейчас %s" % (
                snap.get("generator_policy_rev") or "не записана", gen["generator_policy_rev"])]))
        if ogs.effective_rev(gen) != ogs.effective_rev(dict(gen, generator_rev=snap["generator_rev"])):
            bad.append(("*", "STALE", ["generator_rev: в снимке %s, сейчас %s" % (snap["generator_rev"],
                                                                                   gen["generator_rev"])]))
        if not ogs.approved_for(gen, "pilot"):
            bad.append(("*", "STALE", ["generator_not_approved: %s" % gen["status"]]))
        now = {"plan": sha256_file(PLAN), "identity": sha256_file(IDENT), "proposals": sha256_file(PROPS)}
        bad += [("*", "STALE", ["%s изменился после листа" % k]) for k in now if now[k] != snap["sources"].get(k)]
        bad.append(("*", "STALE", ["нет заданий модели - снимок списка, запуск только после refreeze"]))
    for k, st, what in bad:
        print("  %-9s %-22s %s" % (st, k, ",".join(what)))
    print("%s %s" % ("BATCH_STALE" if bad else "BATCH_CURRENT", bid))
    return 2 if bad else 0


def refreeze(old_id, dry_run=False, drop=()):
    """Тот же список (items снимка old_id, исключения Vitali не пересматриваются) - в новую неизменяемую партию
    с заданиями модели в формате приёмки: acceptance_run.py check/run/derive/qa работают с ней как есть.
    Название для промпта - то, что Vitali видел на листе; опознание вне листа не меняется."""
    import acceptance_plan as ap
    import asset_rev as ar
    import obj_gen_spec as ogs
    old = load_batch(old_id)
    if "items" not in old:
        raise SystemExit("%s - не снимок списка пилота" % old_id)
    gen, dver, fh = ogs.spec(), ogs.derive_version(), ar.frame_hashes()
    if not ogs.approved_for(gen, "pilot"):
        msg = "генератор %s (%s, generator_rev %s) не утверждён для пилота (obj_gen_spec)" % (
            gen["name"], gen["status"], gen["generator_rev"])
        if not dry_run:
            raise SystemExit(msg + " - не замораживаю")
        print("!! " + msg)
    rows, fam, items_by_rank, idrows = ap.load_state()
    # снятые при перезаморозке - только названные явно, с причиной; остальной список не пересматривается
    dropped = dict(d.split("=", 1) if "=" in d else (d, "") for d in drop)
    unknown = set(dropped) - {c["asset_id"] for c in old["items"]}
    if unknown or not all(dropped.values()):
        raise SystemExit("--drop <asset_id>=<причина>, только из партии %s: %s" % (old_id, sorted(unknown) or "нет причины"))
    old = dict(old, items=[c for c in old["items"] if c["asset_id"] not in dropped])
    names = {c["asset_id"]: c["name"] for c in old["items"]}
    rows = [dict(r, identity=names[r["asset_id"]]) if r["asset_id"] in names and r["key"] == r["asset_id"]
            and not r.get("identity") else r for r in rows]
    with open(FAMS, encoding=ENC) as f:
        questions = open_questions(json.load(f))
    plans, why = [], []
    for c in old["items"]:
        p = ap.plan_one({"asset_id": c["asset_id"], "category": "pilot_simple"}, rows, fam, items_by_rank, gen,
                        idrows, fh)
        # опознание не HUMAN_* - это и есть допуск пилота: согласие моделей плюс лист, просмотренный Vitali
        p["blockers"] = [b for b in p["blockers"] if not b.startswith("опознание ")]
        # plan_one видит вопросы только своего семейства; кандидат «другой бок?» чужого - тоже вопрос
        if c["asset_id"].upper() in questions and not p["blockers"]:
            p["blockers"].append("открытый вопрос семейства (кандидат другого бока или перекраски в чужом семействе)")
        if p["generation_strategy"] not in ("single", "mirror_canonical") or len(p["jobs"]) != 1:
            p["blockers"].append("вне границ пилота: %s, заданий %d" % (p["generation_strategy"], len(p["jobs"])))
        p["deps_stale"] = ap.deps_stale(c["asset_id"], rows, fam, items_by_rank, idrows, gen, dver, fh)
        p["blockers"] += ["зависимости %s у %s: %s" % (st, k, ",".join(d)) for k, (st, d) in p["deps_stale"].items()]
        if p["blockers"]:
            why.append("%s: %s" % (c["asset_id"], "; ".join(p["blockers"])))
        p["identity"]["source"] = c["level"]
        plans.append(p)
    if why:
        raise SystemExit("не замораживаю:\n  " + "\n  ".join(why))
    ap.number_jobs(plans, ogs.SEED0)
    snap = ap.snapshot(plans, rows, gen, dver)
    del snap["acceptance_batch_id"]
    for a, c in zip(snap["assets"], old["items"]):
        a["identity"]["source"] = c["level"]
    snap.update(use="pilot", policy=POLICY, approved_for=APPROVED_FOR,
                generator_policy=gen["policy"]["production_pilot"], pilot_of=old_id,
                pilot_items_hash=old["items_hash"], excluded=old["excluded"], reviewed_by=old["reviewed_by"],
                dropped_at_refreeze=dropped)
    bid = "pilot-v2-" + ar.h12(snap)
    snap.update(acceptance_batch_id=bid, batch_id=bid)    # acceptance_run ищет партию по acceptance_batch_id
    path = "(--dry-run: не записано)" if dry_run else ap.write_frozen(snap, BATCHES)
    c = snap["counts"]
    print("партия %s из %s: ассетов %d, заданий модели %d, зеркал выводом %d, кадров игры %d + %d -> %s" % (
        bid, old_id, c["assets"], c["ai_jobs"], c["derive_jobs"], c["direct_game_frames"],
        c["derived_game_frames"], path))
    print("generator_rev %s, prompt_rev %s, generator_policy_rev %s, jobs_hash %s" % (
        gen["generator_rev"], gen["prompt_rev"], gen["generator_policy_rev"], snap["jobs_hash"]))
    return bid


def main():
    for s in (sys.stdout, sys.stderr):
        s.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["select", "sheet", "freeze", "check", "refreeze"])
    ap.add_argument("batch_id", nargs="?")
    ap.add_argument("--exclusions")
    ap.add_argument("--no-exclusions", action="store_true", dest="no_exclusions")
    ap.add_argument("--dry-run", action="store_true", dest="dry_run", help="refreeze: собрать и проверить, не записывая")
    ap.add_argument("--drop", action="append", default=[], metavar="ID=причина",
                    help="refreeze: снять ассет из списка (записывается в снимок)")
    a = ap.parse_args()
    if a.cmd in ("check", "refreeze") and not a.batch_id:
        raise SystemExit("%s: нужен id партии" % a.cmd)
    if a.cmd == "select":
        report_select(*select())
    elif a.cmd == "sheet":
        sheet()
    elif a.cmd == "check":
        sys.exit(check(a.batch_id))
    elif a.cmd == "refreeze":
        refreeze(a.batch_id, a.dry_run, a.drop)
    else:
        if not a.exclusions and not a.no_exclusions:
            raise SystemExit("freeze: --exclusions <tsv> или --no-exclusions")
        freeze(a.exclusions)


if __name__ == "__main__":
    main()
