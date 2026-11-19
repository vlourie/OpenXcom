#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Отчёт пилота PILOT_PRODUCTION_V1: лист просмотра результатов и свод для решения о расширении. Модель не грузит.

Идёт после acceptance_run.py run <id> и acceptance_report.py <id> (листы оригинал x4 | HD, вырез карты, числа
cover / spill / semi / shadow). В пак ничего не принимается.

  sheet   - runs/<id>/pilot_review/index.html: карточка на ассет, по умолчанию PASS, человек отмечает только
            брак (GEOMETRY_FAIL, SEMANTIC_FAIL, ALPHA_FAIL, FOOTPRINT_FAIL, три класса детали - гейт 30.09:
            BLURRED_UPSCALE_FAIL, DETAIL_RECONSTRUCTION_FAIL, RECONSTRUCTED_BUT_INVENTED) или MANUAL_REVIEW. Машинные флаги
            отчёта - подсказка, куда смотреть, вердикт не ставят. Выход - TSV исключений.
  summary - свод по TSV: generated / missing / crash, счёт вердиктов, critical_fail_rate (semantic + geometry)
            и hard_fail_rate (всё объективно непригодное, включая не нарисованное) против порогов
            специалиста, повторяющиеся классы ошибок. Системность решает человек: свод показывает повторы.

    py -3.13 tools/hdart/pilot_report.py sheet   pilot-v2-xxxxxxxxxxxx
    py -3.13 tools/hdart/pilot_report.py summary pilot-v2-xxxxxxxxxxxx --verdicts <tsv>
"""
import argparse
import csv
import html
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import acceptance_run as arun             # noqa: E402
import pilot_batch as pb                  # noqa: E402

ENC = "utf-8-sig"
# гейт детали (специалист 30.09, проба probes/detail-v1, набор regression/detail_critical_v1.json):
#   BLURRED_UPSCALE_FAIL        hard; не critical - смысл и геометрия сохранены
#   DETAIL_RECONSTRUCTION_FAIL  hard; critical, только если человек отметил, что потеря детали меняет конструкцию
#                               или назначение (у стула пропали рейки, у терминала экран, у шкафа полки) -
#                               столбец changes_function; мелкая декоративная черта - не critical
#   RECONSTRUCTED_BUT_INVENTED  hard и critical
DETAIL = ("BLURRED_UPSCALE_FAIL", "DETAIL_RECONSTRUCTION_FAIL", "RECONSTRUCTED_BUT_INVENTED")
VERDICTS = ("PASS", "GEOMETRY_FAIL", "SEMANTIC_FAIL", "ALPHA_FAIL", "FOOTPRINT_FAIL") + DETAIL + ("MANUAL_REVIEW",)
HARD = ("GEOMETRY_FAIL", "SEMANTIC_FAIL", "ALPHA_FAIL", "FOOTPRINT_FAIL") + DETAIL
CRITICAL = ("GEOMETRY_FAIL", "SEMANTIC_FAIL", "RECONSTRUCTED_BUT_INVENTED")
FUNCTION_LOSS = "DETAIL_RECONSTRUCTION_FAIL"      # critical при changes_function = 1
GATE = {"critical": 0.05, "hard": 0.10}          # специалист 30.09: critical <= 5%, hard <= 10%
SYSTEMIC_MIN = 3                                  # один и тот же класс ошибки 3 раза и больше - показать как повтор


def load(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding=ENC) as f:
        return json.load(f)


def state(batch_id):
    """(снимок, строки отчёта по ассетам, ассеты вне политики на сегодня). Без отчёта - стоп."""
    snap = arun.load_snapshot(batch_id)
    rd = os.path.join(arun.run_dir(batch_id), "report")
    doc = load(os.path.join(rd, "report.json"))
    if not doc or doc.get("batch_id") != batch_id:
        raise SystemExit("нет report.json партии %s - сначала acceptance_report.py %s" % (batch_id, batch_id))
    with open(pb.FAMS, encoding=ENC) as f:
        questions = pb.open_questions(json.load(f))
    off = {a for a in snap["asset_ids"] if a.upper() in questions}
    return snap, rd, doc, off


def auto_flags(row):
    """Подсказки из чисел отчёта: что машина видит по ассету (не вердикт)."""
    out = []
    if row["ai_jobs"] == "FAIL":
        out.append("MISSING: " + (row.get("ai_why") or "нет ответа"))
    for key, m in row["numbers"].items():
        if "relation" in m:
            continue
        over = max(m["overflow_px"].values()) if m.get("overflow_px") else 0
        if m["cover"] < 0.85 or m["spill"] > 0.05 or over > 1.0:
            out.append("footprint? cover %.2f spill %.2f over %.1f" % (m["cover"], m["spill"], over))
        if m["semi"] > 0.02 or m["shadow"] > 0.02:
            out.append("alpha? semi %.3f shadow %.3f" % (m["semi"], m["shadow"]))
    if row.get("derive") == "FAIL":
        out.append("derive FAIL: " + ", ".join(row.get("derive_bad", [])))
    return out


def sheet(batch_id):
    snap, rd, doc, off = state(batch_id)
    levels = {a["asset_id"]: a["identity"].get("source", "") for a in snap["assets"]}

    def img(p, cls=""):
        if not p:
            return '<div class="none">нет листа</div>'
        p = p if os.path.isabs(p) else os.path.join(rd, p)
        if not os.path.exists(p):
            p = os.path.join(rd, os.path.basename(p))
        if not os.path.exists(p):
            return '<div class="none">нет листа</div>'
        # ссылкой на лист отчёта, не внутри страницы: 126 ассетов - это ~18 МБ base64; страница отдаётся
        # сервером из runs/<id> (launch.json pilot-review), путь относительный
        return '<img loading="lazy" class="%s" src="../report/%s" alt="">' % (cls, html.escape(os.path.basename(p)))

    cards = []
    for n, row in enumerate(doc["assets"], 1):
        aid = row["asset_id"]
        sh = row.get("sheets", {})
        maps = [v for k, v in sh.items() if k.startswith("map_")]
        flags = auto_flags(row)
        tags = []
        if aid in off:
            tags.append('<span class="off">вне политики: открытый вопрос семейства</span>')
        if row.get("derive") not in (None, "N/A"):
            tags.append('<span class="tag">+ зеркало</span>')
        btns = "".join('<button data-v="%s">%s</button>' % (v, v.replace("_FAIL", "").replace("_", " "))
                       for v in VERDICTS)
        cards.append(
            '<div class="card" data-id="%s"><div class="pics">%s%s%s</div><div class="meta">'
            '<div class="num">#%d <code>%s</code> <span class="lvl">%s</span> %s</div>'
            '<div class="name">%s</div><div class="flags">%s</div><div class="btns">%s</div>'
            '<input class="note" placeholder="что не так (одинаковые слова - один класс ошибки)" hidden>'
            '<label class="fn" hidden><input type="checkbox" class="fnc"> потеря детали меняет конструкцию или '
            'назначение (critical)</label></div></div>' % (
                html.escape(aid), img(sh.get("identity"), "id"), "".join(img(m) for m in maps[:1]),
                img(sh.get("family")) if sh.get("family") else "", n, html.escape(aid),
                html.escape(levels.get(aid, "")), " ".join(tags), html.escape(row["identity"] or ""),
                "<br>".join(html.escape(f) for f in flags) or "машина: чисто", btns))
    out = os.path.join(arun.run_dir(batch_id), "pilot_review")
    os.makedirs(out, exist_ok=True)
    page = PAGE.replace("{{ID}}", batch_id).replace("{{N}}", str(len(cards))).replace("{{CARDS}}", "\n".join(cards))
    with open(os.path.join(out, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)
    print("лист -> %s (%d ассетов, вне политики %d, с машинными флагами %d)" % (
        os.path.join(out, "index.html"), len(cards), len(off), sum(1 for r in doc["assets"] if auto_flags(r))))


def read_verdicts(path, ids):
    ex, fns = {}, set()
    with open(path, encoding=ENC, newline="") as f:
        for r in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
            v = r.get("verdict", "").strip().upper()
            if v not in VERDICTS:
                raise SystemExit("%s: вердикт %r не из %s" % (r.get("asset_id"), v, VERDICTS))
            if r["asset_id"] not in ids:
                raise SystemExit("%s: не из партии" % r["asset_id"])
            fn = (r.get("changes_function") or "").strip().lower() in ("1", "yes", "true")
            if fn and v != FUNCTION_LOSS:
                raise SystemExit("%s: changes_function только при %s, а вердикт %s" % (r["asset_id"], FUNCTION_LOSS, v))
            if fn:
                fns.add(r["asset_id"])
            if v != "PASS":
                ex[r["asset_id"]] = (v, (r.get("note") or "").strip())
    return ex, fns


def tally(rows, ex, fns=frozenset()):
    """Счёт по списку строк отчёта: MISSING - объективно, остальное - вердикт человека (по умолчанию PASS).
    fns - ассеты, где DETAIL_RECONSTRUCTION_FAIL отмечен как меняющий конструкцию: они critical (FUNCTION_LOSS)."""
    c = Counter()
    for row in rows:
        if row["ai_jobs"] == "FAIL":
            c["MISSING"] += 1
            continue
        v = ex.get(row["asset_id"], ("PASS", ""))[0]
        c[v] += 1
        if v == FUNCTION_LOSS and row["asset_id"] in fns:
            c["FUNCTION_LOSS"] += 1
    n = len(rows)
    crit = sum(c[v] for v in CRITICAL) + c["FUNCTION_LOSS"]
    hard = sum(c[v] for v in HARD) + c["MISSING"]
    return c, n, crit, hard


def summary(batch_id, verdicts):
    snap, rd, doc, off = state(batch_id)
    ids = {r["asset_id"] for r in doc["assets"]}
    ex, fns = read_verdicts(verdicts, ids)
    L = ["# Пилот %s - свод" % batch_id, "",
         "Политика %s, генератор %s, в пак ничего не принято." % (snap.get("policy"), snap["generator"]["generator_rev"]),
         "Код прогона: %s, не хватает ответов: %d." % (doc.get("returncode"), len(doc.get("missing_outputs") or [])), ""]
    verdict_lines = {}
    for title, rows in (("все %d" % len(doc["assets"]), doc["assets"]),
                        ("в политике %d (без %d вне политики)" % (len(doc["assets"]) - len(off), len(off)),
                         [r for r in doc["assets"] if r["asset_id"] not in off])):
        c, n, crit, hard = tally(rows, ex, fns)
        cr, hr = crit / n if n else 0, hard / n if n else 0
        ok = cr <= GATE["critical"] and hr <= GATE["hard"]
        verdict_lines[title] = ok
        L += ["## %s" % title, "", "| что | сколько | доля |", "|---|---|---|",
              "| generated | %d | |" % (n - c["MISSING"]), "| missing / crash | %d | |" % c["MISSING"]]
        L += ["| %s | %d | %.1f%% |" % (v, c[v], 100.0 * c[v] / n) for v in VERDICTS]
        L += ["| HARD_FAIL_TOTAL | %d | %.1f%% |" % (hard, 100 * hr), "",
              "- critical_fail_rate (semantic + geometry + invented + деталь с потерей назначения, из них %d): "
              "**%.1f%%** (порог %d%%)" % (c["FUNCTION_LOSS"], 100 * cr, 100 * GATE["critical"]),
              "- hard_fail_rate (geometry, semantic, alpha, footprint, деталь, не нарисовано): **%.1f%%** (порог %d%%)" % (
                  100 * hr, 100 * GATE["hard"]),
              "- по числам: %s" % ("в пороге" if ok else "ВНЕ ПОРОГА"), ""]
    pat = Counter((v, note.lower()) for v, note in ex.values() if v != "PASS" and note)
    L += ["## Повторяющиеся классы ошибок", "",
          "Одинаковая заметка человека - один класс. %d и больше раз - кандидат в системную ошибку: расширение "
          "по правилу специалиста не идёт, пока класс не разобран." % SYSTEMIC_MIN, ""]
    top = pat.most_common(12)
    L += ["- %s x%d: %s%s" % (v, k, note, "  **<- повтор**" if k >= SYSTEMIC_MIN else "") for (v, note), k in top] or ["- нет"]
    auto = Counter(f.split(" ", 1)[0] for r in doc["assets"] for f in auto_flags(r))
    L += ["", "Машинные флаги (подсказка, не вердикт): %s" % (", ".join("%s %d" % kv for kv in auto.most_common()) or "нет"),
          "", "## Исключения", "", "| ассет | вердикт | заметка | вне политики |", "|---|---|---|---|"]
    L += ["| %s | %s | %s | %s |" % (a, v, note, "да" if a in off else "") for a, (v, note) in sorted(ex.items())]
    systemic = [p for p, k in pat.items() if k >= SYSTEMIC_MIN]
    L += ["", "**Итог по правилу расширения:** %s" % (
        "повтор класса ошибки - не расширять, пока не разобран" if systemic else
        ("числа в пороге, повторов %d+ нет - решение за специалистом" % SYSTEMIC_MIN
         if all(verdict_lines.values()) else "числа вне порога - не расширять"))]
    path = os.path.join(rd, "pilot_summary.md")
    with open(path, "w", encoding=ENC) as f:
        f.write("\n".join(L) + "\n")
    print("\n".join(L))
    print("-> %s" % path)


PAGE = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Пилот: просмотр результатов</title>
<style>
:root{--bg:#141418;--card:#1e1e24;--line:#34343c;--text:#e8e8ea;--mute:#9a9aa4;--ok:#2f7d4f;--bad:#b23a3a;
--geo:#b0782a;--al:#2a7fb0;--fp:#8a4fb0;--man:#6a6a74;--acc:#e6b422}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.35 system-ui,sans-serif}
header{position:sticky;top:0;z-index:5;background:#101014ee;border-bottom:1px solid var(--line);padding:10px 16px;
display:flex;gap:16px;flex-wrap:wrap;align-items:center}header b{color:var(--acc)}label{color:var(--mute)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(520px,1fr));gap:10px;padding:12px 16px 220px}
@media(max-width:560px){.grid{grid-template-columns:1fr}}
.card{background:var(--card);border:2px solid var(--line);border-radius:8px;padding:8px}
.card.x-GEOMETRY_FAIL{border-color:var(--geo)}.card.x-SEMANTIC_FAIL{border-color:var(--bad)}
.card.x-ALPHA_FAIL{border-color:var(--al)}.card.x-FOOTPRINT_FAIL{border-color:var(--fp)}
.card.x-MANUAL_REVIEW{border-color:var(--man)}
.card.x-BLURRED_UPSCALE_FAIL,.card.x-DETAIL_RECONSTRUCTION_FAIL,.card.x-RECONSTRUCTED_BUT_INVENTED{border-color:var(--bad)}
.pics{display:flex;gap:6px;flex-wrap:wrap}.pics img{max-width:100%;max-height:340px;background:#0c0c0f;border-radius:4px}
.pics img.id{width:min(100%,528px);max-height:none}
.none{color:var(--mute);padding:20px}
.num{color:var(--mute);margin-top:6px}code{color:var(--text)}.lvl{font-size:11px;background:#2a2a33;padding:1px 6px;border-radius:3px}
.off{color:#ff8a65;font-size:12px}.tag{color:var(--acc);font-size:12px}
.name{font-size:16px;font-weight:600;margin:2px 0}.flags{color:var(--mute);font-size:12px}
.btns{display:flex;gap:4px;flex-wrap:wrap;margin-top:6px}
.btns button{flex:1;min-width:70px;padding:5px 4px;border:1px solid var(--line);border-radius:4px;background:#26262e;
color:var(--text);cursor:pointer;font-size:12px}
.btns button.on[data-v=PASS]{background:var(--ok)}.btns button.on[data-v=GEOMETRY_FAIL]{background:var(--geo)}
.btns button.on[data-v=SEMANTIC_FAIL]{background:var(--bad)}.btns button.on[data-v=ALPHA_FAIL]{background:var(--al)}
.btns button.on[data-v=FOOTPRINT_FAIL]{background:var(--fp)}.btns button.on[data-v=MANUAL_REVIEW]{background:var(--man)}
.btns button.on[data-v=BLURRED_UPSCALE_FAIL],.btns button.on[data-v=DETAIL_RECONSTRUCTION_FAIL],
.btns button.on[data-v=RECONSTRUCTED_BUT_INVENTED]{background:var(--bad)}
.note{width:100%;margin-top:6px;padding:5px;background:#101014;color:var(--text);border:1px solid var(--line);border-radius:4px}
footer{position:fixed;bottom:0;left:0;right:0;background:#101014f2;border-top:1px solid var(--line);padding:8px 16px}
textarea{width:100%;height:110px;background:#0c0c0f;color:var(--text);border:1px solid var(--line);font:12px monospace}
footer button{padding:6px 14px;background:var(--acc);border:0;border-radius:4px;font-weight:600;cursor:pointer}
</style></head><body>
<header><div><b>{{ID}}</b>: {{N}} ассетов. По умолчанию PASS - отметь только брак.</div>
<div id="cnt"></div><label><input type="checkbox" id="only"> только отмеченные</label></header>
<div class="grid">
{{CARDS}}
</div>
<footer><div style="display:flex;gap:10px;align-items:center;margin-bottom:6px"><span>Вердикты (скопируй в чат):</span>
<button id="copy">Скопировать</button><span id="copied" style="color:var(--mute)"></span></div>
<textarea id="out" readonly></textarea></footer>
<script>
const KEY="pilot_review_{{ID}}";let st={};
try{st=JSON.parse(localStorage.getItem(KEY)||"{}")}catch(e){st={}}
function save(){try{localStorage.setItem(KEY,JSON.stringify(st))}catch(e){}}
function paint(card){const s=st[card.dataset.id]||{v:"PASS",note:""};
card.className="card"+(s.v!=="PASS"?" x-"+s.v:"");
card.querySelectorAll(".btns button").forEach(b=>b.classList.toggle("on",b.dataset.v===s.v));
const n=card.querySelector(".note");n.hidden=s.v==="PASS";n.value=s.note||"";
card.querySelector(".fn").hidden=s.v!=="DETAIL_RECONSTRUCTION_FAIL";card.querySelector(".fnc").checked=!!s.fn;
card.style.display=(document.getElementById("only").checked&&s.v==="PASS")?"none":""}
function out(){const rows=[],c={};
document.querySelectorAll(".card").forEach(card=>{const s=st[card.dataset.id]||{v:"PASS"};c[s.v]=(c[s.v]||0)+1;
if(s.v!=="PASS")rows.push(card.dataset.id+"\\t"+s.v+"\\t"+(s.note||"").replace(/[\\t\\n]/g," ")+"\\t"+
(s.v==="DETAIL_RECONSTRUCTION_FAIL"&&s.fn?"1":""))});
document.getElementById("out").value="asset_id\\tverdict\\tnote\\tchanges_function\\n"+rows.join("\\n");
document.getElementById("cnt").textContent=Object.entries(c).map(([k,v])=>k.replace("_FAIL","")+" "+v).join(" · ")}
document.querySelectorAll(".card").forEach(card=>{paint(card);
card.querySelectorAll(".btns button").forEach(b=>b.onclick=()=>{const id=card.dataset.id;
st[id]={v:b.dataset.v,note:(st[id]||{}).note||""};if(b.dataset.v==="PASS")delete st[id];save();paint(card);out()});
card.querySelector(".note").oninput=e=>{const id=card.dataset.id;if(st[id]){st[id].note=e.target.value;save();out()}};
card.querySelector(".fnc").onchange=e=>{const id=card.dataset.id;if(st[id]){st[id].fn=e.target.checked;save();out()}}});
document.getElementById("only").onchange=()=>document.querySelectorAll(".card").forEach(paint);
document.getElementById("copy").onclick=()=>{const t=document.getElementById("out");t.select();
try{navigator.clipboard.writeText(t.value)}catch(e){document.execCommand("copy")}
document.getElementById("copied").textContent="скопировано"};
out();
</script></body></html>
"""


def main():
    for s in (sys.stdout, sys.stderr):
        s.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["sheet", "summary"])
    ap.add_argument("batch_id")
    ap.add_argument("--verdicts")
    a = ap.parse_args()
    if a.cmd == "sheet":
        sheet(a.batch_id)
    else:
        if not a.verdicts:
            raise SystemExit("summary: --verdicts <tsv> (исключения с листа; пустой TSV с заголовком - всё PASS)")
        summary(a.batch_id, a.verdicts)


if __name__ == "__main__":
    main()
