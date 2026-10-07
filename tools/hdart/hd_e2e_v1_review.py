#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""HD_PIPELINE_E2E_V1: страница обычного ревью тикетов связей и приём решений в review/e2e-v1/decisions.tsv.

Специалист 03.10, передал Vitali в чате: тикеты R00616, R00660, R00661, R00807-R00812 - на обычный ревью, «без
указания желаемого результата и без подсказки, сколько действий освободит NONE»; исход - подтверждено, отвергнуто
или OPEN, «не нужно стремиться получить NONE».

Что видит человек: пару кадров A и B (relation_truth_v2.pair_image: крупно, силуэты, соседи в PCK), место на карте
(relation_taxonomy.map_image), факты игры (relation_taxonomy.facts: MCD, LOFT, где стоят вместе) и само утверждение
детектора: тип и что он кандидат. Чего не видит: какие кадры и единицы рисования тикет держит, сколько действий
освободит любой ответ, что даст пересборка плана (affected_*, downstream_blocked, released_despite, batch_assets) -
это остаётся в review.jsonl. Порядок тикетов перемешан солью, ни один ответ не выбран заранее.

    pack                    -> review/e2e-v1/pages/batch-01/index.html, items.json, img/, pack.lock.json
    import <файл.tsv>       проверить ответы страницы и дописать их в decisions.tsv (ничего не переписывает)

    py -3.13 tools/hdart/hd_e2e_v1_review.py <команда>
"""
import argparse
import csv
import hashlib
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import identity_routing as ir                     # noqa: E402

ENC = ir.ENC
REVIEW_DIR = os.path.join("art", "objects", "generation", "review", "e2e-v1")
TICKETS = os.path.join(REVIEW_DIR, "review.jsonl")
DECISIONS = os.path.join(REVIEW_DIR, "decisions.tsv")
OUT = os.path.join(REVIEW_DIR, "pages", "batch-01")
SALT = "hd-e2e-v1-review-batch-01"
# тикет -> ticket_key в R3.1 (перенумерация тикета не должна тихо подменить пару)
BATCH = {"R00616": "73e85b498209", "R00660": "f7d837d58658", "R00661": "67cdf06c226a",
         "R00807": "c6d639920383", "R00808": "fcfa88054fd4", "R00809": "8302a0ae6443",
         "R00810": "295d90d697d7", "R00811": "6b36b8b5a5b7", "R00812": "a112b3d4b17e"}
HEAD = ["review_id", "ticket_key", "decision", "type", "partner", "note", "who", "when"]
DECISIONS_ALLOWED = ("CONFIRM_TYPE", "OTHER_TYPE", "NO_RELATION", "OPEN")
# типы связей V7 (тикеты review.jsonl) и ярлыки relation_taxonomy, без NONE и UNSURE - для них свои ответы;
# OTHER_SIDE - тот же предмет другим боком: в схеме V7 его нет (R-177), ответ записывается как есть
TYPES = ("COMPOSITE_PART", "REPEATED_ASSEMBLY_RELATION", "ATTACHMENT_CANDIDATE", "MODULAR_SECTION",
         "STRUCTURAL_COUNTERPART", "STATE_VARIANT", "DESTROYED_VARIANT_OF", "ANIMATION_FAMILY", "EXACT_COPY",
         "RECOLOR_PEER", "RECOLOR_OF", "ALIGNED_RECOLOR", "MIRRORED_VARIANT_PEER", "LOCAL_EDIT_VARIANT",
         "SET_CORRESPONDENCE", "OTHER_SIDE")
TYPE_RU = {
    "COMPOSITE_PART": "A и B - части одного поставленного многоклеточного предмета (две половины кровати)",
    "REPEATED_ASSEMBLY_RELATION": "A и B входят в одну и ту же сборку из нескольких кадров, и эта сборка "
                                  "повторяется на разных картах",
    "ATTACHMENT_CANDIDATE": "один регулярно ставится к другому (стул к столу, вывеска на стену), но это две вещи",
    "MODULAR_SECTION": "оба - отдельные секции конструкции, каждая в своей клетке, комбинируются по-разному",
    "STRUCTURAL_COUNTERPART": "та же конструкция в парной роли (левый и правый угол, начало и конец)",
    "STATE_VARIANT": "другое состояние того же предмета (открыто/закрыто, вкл/выкл)",
    "DESTROYED_VARIANT_OF": "разрушенный вид того же предмета",
    "ANIMATION_FAMILY": "кадры одной петли анимации",
    "EXACT_COPY": "пиксели совпадают",
    "RECOLOR_PEER": "тот же рисунок в других цветах, та же сторона",
    "RECOLOR_OF": "B - перекраска A (направленно)",
    "ALIGNED_RECOLOR": "перекраска со сдвигом рисунка в клетке",
    "MIRRORED_VARIANT_PEER": "тот же рисунок, отражённый слева направо",
    "LOCAL_EDIT_VARIANT": "B - A с правкой части (что-то добавлено или убрано)",
    "SET_CORRESPONDENCE": "кадр с тем же номером в наборе-двойнике",
    "OTHER_SIDE": "тот же предмет другим боком (поворот, не зеркало)",
}
CLAIM_RU = {"RELATED_CANDIDATE": "кандидат: существование связи не доказано", "TYPE_OPEN": "тип открыт"}


def p(*a):
    return os.path.join(OUT, *a)


def order(s):
    return hashlib.sha256((SALT + "|" + s).encode("utf-8")).hexdigest()


def load_tickets():
    out = {}
    with open(TICKETS, encoding="utf-8-sig") as f:
        for ln in f:
            r = json.loads(ln)
            if r["review_id"] in BATCH:
                out[r["review_id"]] = r
    for rid, key in BATCH.items():
        r = out.get(rid)
        if r is None:
            raise SystemExit("тикета %s нет в %s" % (rid, TICKETS))
        if r["ticket_key"] != key:
            raise SystemExit("%s: ticket_key %s, ожидался %s - тикеты перенумерованы" % (rid, r["ticket_key"], key))
        if not r.get("claim") or len(r["claim"].get("pair", [])) != 2:
            raise SystemExit("%s: нет пары в утверждении" % rid)
    return out


def blind_item(r):
    """Только то, что нужно для решения о самой связи: id, ключ, пара, тип и уровень утверждения, детектор."""
    c = r["claim"]
    return {"review_id": r["review_id"], "ticket_key": r["ticket_key"], "a": c["pair"][0], "b": c["pair"][1],
            "type": c["type"], "type_ru": TYPE_RU.get(c["type"], ""), "detectors": list(c.get("detectors", [])),
            "level": [CLAIM_RU.get(c.get("existence"), c.get("existence", "")),
                      CLAIM_RU.get(c.get("type_level"), c.get("type_level", ""))]}


# слова, которых на странице быть не должно: последствия ответа для плана
FORBIDDEN = ("affected_render_units", "affected_frames", "downstream_blocked", "released_despite", "batch_assets",
             "group_ids", "освобод", "release", "unblock", "действий", "actions_v7", "possible_actions")


def do_pack():
    import relation_discovery_v2 as v2
    import relation_discovery_v3 as v3
    import relation_taxonomy as tx
    import relation_truth_v2 as rt
    import routing_model_v8 as v8
    if os.path.exists(p("answers.tsv")):
        raise SystemExit("ответы уже есть - страница не перестраивается: %s" % p("answers.tsv"))
    tickets = load_tickets()
    os.makedirs(p("img"), exist_ok=True)
    ctx = v3.Ctx(index=v2.load_index(v2.OUT))
    mcd = v8.Mcd(ctx.world)
    items = []
    t0 = time.time()
    for rid in sorted(BATCH, key=order):
        it = blind_item(tickets[rid])
        a, b = it["a"], it["b"]
        L, (pa, pb, cnt, blocks) = tx.facts(ctx, mcd, a, b)
        rt.pair_image(ctx, a, b).save(p("img", rid + "_pair.png"))
        files = [rid + "_pair.png"]
        mi = tx.map_image(ctx, a, b, pa, pb, cnt, blocks)
        if mi is not None:
            mi.save(p("img", rid + "_map.png"))
            files.append(rid + "_map.png")
        it["facts"], it["files"] = L, files
        items.append(it)
        print("%s %s ~ %s  %.0f с" % (rid, a, b, time.time() - t0), flush=True)
    key = "hd-e2e-v1-review-" + order("|".join(sorted(BATCH)))[:8]
    page = (PAGE.replace("__DATA__", json.dumps(items, ensure_ascii=False))
            .replace("__TYPES__", json.dumps([[t, TYPE_RU[t]] for t in TYPES], ensure_ascii=False))
            .replace("__HEAD__", json.dumps(HEAD)).replace("__KEY__", key))
    low = page.lower()
    hit = [w for w in FORBIDDEN if w.lower() in low]
    if hit:
        raise SystemExit("на странице запрещённое: %s" % hit)
    with open(p("index.html"), "w", encoding="utf-8") as f:
        f.write(page)
    ir.dump_json(p("items.json"), {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "salt": SALT,
                                   "decision": "специалист 03.10, передал Vitali в чате: 9 тикетов на обычный ревью",
                                   "items": items, "storage_key": key, "answer_columns": HEAD,
                                   "decisions_allowed": list(DECISIONS_ALLOWED), "types": list(TYPES)})
    imgs = {f: ir.file_sha(p("img", f)) if hasattr(ir, "file_sha") else hashlib.sha256(
        open(p("img", f), "rb").read()).hexdigest() for f in sorted(os.listdir(p("img")))}
    ir.dump_json(p("pack.lock.json"), {"img_sha256": imgs, "page_sha256": hashlib.sha256(
        page.encode("utf-8")).hexdigest(), "tickets": BATCH})
    rel = os.path.relpath(OUT, os.path.join("art", "objects", "generation")).replace(os.sep, "/")
    print("тикетов %d; страница: http://localhost:8778/%s/index.html" % (len(items), rel))


def read_rows(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE))
    rows = [r for r in rows if any(x.strip() for x in r)]
    if not rows or rows[0] != HEAD:
        raise SystemExit("%s: шапка не %s" % (path, HEAD))
    return rows[1:]


def do_import(path):
    """Ответы страницы -> decisions.tsv. Читает decisions.tsv целиком, проверяет новые строки, пишет всё сразу
    (R-159) и сверяет число строк после записи. Повтор тикета, уже решённого в decisions.tsv, - отказ. После заморозки
    ответов (hd_e2e_v1_r32.py freeze -> answers.lock.json) решения не принимаются: R3.2 считан по замороженным."""
    if os.path.exists(os.path.join(REVIEW_DIR, "answers.lock.json")):
        raise SystemExit("ответы заморожены (answers.lock.json) - новые решения только новым пакетом и новым пересчётом")
    new = read_rows(path)
    old = read_rows(DECISIONS)
    done = {r[0] for r in old}
    errs, seen = [], set()
    for r in new:
        if len(r) != len(HEAD):
            errs.append("строка %s: %d столбцов" % (r[:1], len(r)))
            continue
        d = dict(zip(HEAD, r))
        rid = d["review_id"]
        if BATCH.get(rid) != d["ticket_key"]:
            errs.append("%s: тикет не из этой страницы или ключ %s не тот" % (rid, d["ticket_key"]))
        if d["decision"] not in DECISIONS_ALLOWED:
            errs.append("%s: решение %r" % (rid, d["decision"]))
        if (d["decision"] == "OTHER_TYPE") != bool(d["type"]):
            errs.append("%s: тип указывается только при OTHER_TYPE и тогда обязателен" % rid)
        if d["type"] and d["type"] not in TYPES:
            errs.append("%s: тип %r не из списка" % (rid, d["type"]))
        if not d["who"].strip() or not d["when"].strip():
            errs.append("%s: нет who или when" % rid)
        if rid in done or rid in seen:
            errs.append("%s: уже решён" % rid)
        seen.add(rid)
    if errs:
        raise SystemExit("ответы не приняты:\n  " + "\n  ".join(errs))
    rows = [HEAD] + old + new
    with open(DECISIONS, "w", encoding=ENC, newline="") as f:
        w = csv.writer(f, delimiter="\t", quoting=csv.QUOTE_NONE, escapechar=None, lineterminator="\n")
        w.writerows(rows)
    back = read_rows(DECISIONS)
    if len(back) != len(old) + len(new):
        raise SystemExit("после записи в decisions.tsv %d строк, ожидалось %d" % (len(back), len(old) + len(new)))
    print("принято %d решений; в decisions.tsv теперь %d" % (len(new), len(back)))
    for r in new:
        print("  " + "  ".join(r[:4]))


PAGE = r"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Ревью связей E2E</title>
<style>
:root{--bg:#f6f5f2;--fg:#1d1d1f;--mut:#666;--card:#fff;--line:#ddd;--acc:#2a62c9}
@media (prefers-color-scheme:dark){:root{--bg:#18181b;--fg:#e8e8ea;--mut:#9a9aa2;--card:#222226;--line:#3a3a40;--acc:#7aa6ff}}
body{background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,sans-serif;margin:0;padding:16px}
main{max-width:1100px;margin:0 auto}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:14px;margin:18px 0}
.card h2{margin:0 0 6px;font-size:18px}
.claim{margin:6px 0 10px}.claim b{font-family:ui-monospace,monospace}
.mut{color:var(--mut)}
img{max-width:100%;height:auto;display:block;margin:8px 0;image-rendering:pixelated;background:#141418}
ul{margin:6px 0 10px;padding-left:20px}
.ans label{display:block;margin:3px 0;cursor:pointer}
select,input[type=text],textarea{font:inherit;background:var(--bg);color:var(--fg);border:1px solid var(--line);
  border-radius:4px;padding:4px 6px;max-width:100%}
textarea{width:100%;min-height:44px;box-sizing:border-box}
.row{margin:6px 0}
details{margin:8px 0}
pre{white-space:pre-wrap;word-break:break-all;background:var(--bg);border:1px solid var(--line);padding:8px}
button{font:inherit;padding:6px 12px;border-radius:5px;border:1px solid var(--line);background:var(--card);color:var(--fg);cursor:pointer}
</style></head><body><main>
<h1>Ревью связей E2E V1: 9 тикетов</h1>
<p>Для каждой пары детектор утверждает связь определённого типа. Решите, есть ли она:
<b>CONFIRM_TYPE</b> - связь есть, и тип верен; <b>OTHER_TYPE</b> - связь есть, но другого типа (выбрать тип);
<b>NO_RELATION</b> - связи нет; <b>OPEN</b> - по показанному не решить (в заметке - чего не хватило).
Ответы сохраняются в браузере; TSV внизу - прислать целиком.</p>
<p class="mut">Кто отвечает: <input type="text" id="who" placeholder="имя"></p>
<details><summary>Определения типов</summary><ul id="defs"></ul></details>
<div id="items"></div>
<h2>TSV</h2><button id="copy">Скопировать</button><pre id="tsv"></pre>
</main>
<script>
const DATA=__DATA__, TYPES=__TYPES__, HEAD=__HEAD__, KEY="__KEY__";
const DEC=[["CONFIRM_TYPE","связь есть, тип верен"],["OTHER_TYPE","связь есть, тип другой"],
  ["NO_RELATION","связи нет"],["OPEN","не решить по показанному"]];
let S={who:"",ans:{}};
try{const v=JSON.parse(localStorage.getItem(KEY)||"null");if(v&&v.ans)S=v}catch(e){}
function save(){try{localStorage.setItem(KEY,JSON.stringify(S))}catch(e){}render()}
function esc(s){return String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]))}
document.getElementById("defs").innerHTML=TYPES.map(t=>"<li><b>"+t[0]+"</b> - "+esc(t[1])+"</li>").join("");
const who=document.getElementById("who");who.value=S.who||"";who.oninput=()=>{S.who=who.value;save()};
const box=document.getElementById("items");
DATA.forEach((it,i)=>{
  const a=S.ans[it.review_id]||(S.ans[it.review_id]={decision:"",type:"",partner:"",note:"",when:""});
  const d=document.createElement("div");d.className="card";
  d.innerHTML="<h2>"+(i+1)+". "+it.review_id+": A "+esc(it.a)+" ~ B "+esc(it.b)+"</h2>"+
    "<div class='claim'>Утверждение: <b>"+esc(it.type)+"</b> - "+esc(it.type_ru)+
    "<div class='mut'>"+esc(it.level.join("; "))+"; детектор "+esc(it.detectors.join(", "))+"</div></div>"+
    it.files.map(f=>"<img loading='lazy' src='img/"+f+"' alt='"+f+"'>").join("")+
    "<ul>"+it.facts.map(x=>"<li>"+esc(x)+"</li>").join("")+"</ul>"+
    "<div class='ans'>"+DEC.map(o=>"<label><input type='radio' name='d"+i+"' value='"+o[0]+"'> <b>"+o[0]+
      "</b> - "+o[1]+"</label>").join("")+"</div>"+
    "<div class='row'>тип при OTHER_TYPE: <select><option value=''>-</option>"+
      TYPES.map(t=>"<option>"+t[0]+"</option>").join("")+"</select></div>"+
    "<div class='row'>с каким кадром связь, если не с A или B (необязательно): <input type='text' class='partner'></div>"+
    "<div class='row'><textarea placeholder='заметка: почему, чего не хватило'></textarea></div>";
  box.appendChild(d);
  d.querySelectorAll("input[type=radio]").forEach(r=>{r.checked=r.value===a.decision;
    r.onchange=()=>{a.decision=r.value;if(r.value!=="OTHER_TYPE")a.type="";a.when=new Date().toISOString().slice(0,19);save()}});
  const sel=d.querySelector("select");sel.value=a.type;sel.onchange=()=>{a.type=sel.value;save()};
  const pt=d.querySelector(".partner");pt.value=a.partner;pt.oninput=()=>{a.partner=pt.value;save()};
  const ta=d.querySelector("textarea");ta.value=a.note;ta.oninput=()=>{a.note=ta.value;save()};
  it._sel=sel;
});
function clean(s){return String(s||"").replace(/[\t\r\n]+/g," ").trim()}
function render(){
  DATA.forEach(it=>{const a=S.ans[it.review_id];it._sel.disabled=a.decision!=="OTHER_TYPE"});
  const rows=[HEAD.join("\t")];
  DATA.forEach(it=>{const a=S.ans[it.review_id];if(!a.decision)return;
    rows.push([it.review_id,it.ticket_key,a.decision,a.decision==="OTHER_TYPE"?a.type:"",clean(a.partner),
      clean(a.note),clean(S.who),a.when].join("\t"))});
  document.getElementById("tsv").textContent=rows.join("\n");
}
document.getElementById("copy").onclick=()=>{navigator.clipboard&&navigator.clipboard.writeText(document.getElementById("tsv").textContent)};
render();
</script></body></html>
"""


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("pack", "import"))
    ap.add_argument("file", nargs="?")
    a = ap.parse_args()
    if a.cmd == "pack":
        do_pack()
    else:
        if not a.file:
            raise SystemExit("import <файл.tsv>")
        do_import(a.file)


if __name__ == "__main__":
    main()
