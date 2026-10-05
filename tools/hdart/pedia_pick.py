#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""pedia_pick.py - выбор картинок педии: оригинал и три наши версии рядом, текст статьи по-русски.

По каждой картинке Vitali выбирает лучшую из трёх версий (обычная, наша в манере художника, 18+)
или отвергает все. Решения копятся в art\pedia_regen\pick.tsv (последняя строка по картинке главная),
в мод ничего не пишется. Страница живёт только на этой машине: http://127.0.0.1:8770

    py -3.13 tools\hdart\pedia_pick.py serve              # поднять страницу
    py -3.13 tools\hdart\pedia_pick.py summary            # сколько выбрано, чего и сколько отвергнуто

Клавиши на странице: 1 2 3 - выбрать версию, 0 или X - отвергнуть все, стрелки - соседняя картинка,
Z - картинки во весь экран. Версия берётся самая свежая: переделка (hd_redo v3, v2) важнее серии (v1).
"""
import argparse
import glob
import io
import json
import os
import re
import sys
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import common

ENC = "utf-8-sig"
ROOT = os.path.join("art", "pedia_regen")
ORIG = os.path.join(common.MODS, "Piratez", "Resources", "Pedia")
PICKS = os.path.join(ROOT, "pick.tsv")
VARIANTS = [("hd", "Обычная"), ("style", "Наша (манера художника)"), ("18", "18+")]
CHOICES = {"hd", "style", "18", "none"}
TYPES = {".png": "image/png", ".gif": "image/gif", ".jpg": "image/jpeg"}


def load(path, default):
    if os.path.exists(path):
        with io.open(path, encoding=ENC) as f:
            return json.load(f)
    return default


def ru(d):
    d = d or {}
    return d.get("ru") or d.get("en-US") or ""


def outputs():
    """{(вариант, имя без расширения в нижнем регистре): путь} - самая свежая версия каждой картинки."""
    best = {}
    for var, _ in VARIANTS:
        for path in glob.glob(os.path.join(ROOT, var + "_*", "*__%s__v*.png" % var)):
            m = re.match(r"(.+)__%s__v(\d+)\.png$" % re.escape(var), os.path.basename(path))
            if not m:
                continue
            # переделка важнее серии, внутри - старший номер версии
            rank = (os.path.basename(os.path.dirname(path)).endswith("_redo"), int(m.group(2)))
            key = (var, m.group(1).lower())
            if key not in best or rank > best[key][0]:
                best[key] = (rank, path)
    return {k: v[1] for k, v in best.items()}


def read_picks():
    picks = {}
    if os.path.exists(PICKS):
        with io.open(PICKS, encoding=ENC) as f:
            for line in f:
                p = line.rstrip("\r\n").split("\t")
                if len(p) >= 3 and p[1] in CHOICES:
                    picks[p[0]] = {"choice": p[1], "time": p[2], "note": p[3] if len(p) > 3 else "",
                                   "file": p[4] if len(p) > 4 else ""}
    return picks


def write_pick(key, choice, note, path):
    new = not os.path.exists(PICKS)
    with io.open(PICKS, "a", encoding=ENC if new else "utf-8") as f:
        f.write("%s\t%s\t%s\t%s\t%s\n" % (key, choice, time.strftime("%Y-%m-%d %H:%M:%S"),
                                          note.replace("\t", " ").replace("\n", " "), path))


class State:
    def __init__(self):
        self.plan = load(os.path.join(ROOT, "plan.json"), None)
        if not self.plan:
            sys.exit("нет %s: сначала pedia_batch.py plan" % os.path.join(ROOT, "plan.json"))
        self.text = load(os.path.join(ROOT, "pedia_text.json"), {})
        self.refresh()

    def refresh(self):
        self.out = outputs()

    def items(self):
        picks = read_picks()
        res = []
        for i, k in enumerate(self.plan["order"]):
            it = self.plan["info"][k]
            stem = os.path.splitext(it["file"])[0].lower()
            arts = (self.text.get(k) or {}).get("articles") or []
            res.append({
                "key": k, "n": i + 1, "file": it["file"], "batch": i // self.plan["size"] + 1,
                "kind": it["kind"],
                "articles": [{"title": ru(a.get("title")), "text": ru(a.get("text"))} for a in arts],
                "have": [v for v, _ in VARIANTS if (v, stem) in self.out],
                "pick": picks.get(k),
            })
        return res

    def gen_path(self, var, key):
        it = self.plan["info"].get(key)
        if not it:
            return None
        return self.out.get((var, os.path.splitext(it["file"])[0].lower()))


PAGE = r"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><title>Выбор картинок педии</title>
<style>
:root{--bg:#141418;--panel:#1f1f26;--line:#34343f;--text:#e8e6e0;--dim:#9a98a0;--acc:#f0c040;--ok:#4caf6a;--bad:#d9534f}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:15px/1.45 system-ui,Segoe UI,sans-serif}
header{position:sticky;top:0;z-index:5;display:flex;flex-wrap:wrap;gap:10px;align-items:center;padding:10px 16px;background:#18181e;border-bottom:1px solid var(--line)}
header b{color:var(--acc)}
select,button,input{background:var(--panel);color:var(--text);border:1px solid var(--line);border-radius:6px;padding:6px 10px;font:inherit}
button{cursor:pointer}button:hover{border-color:var(--acc)}
#stats{color:var(--dim);margin-left:auto}
main{padding:14px 16px 40px;max-width:1900px;margin:0 auto}
.row{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}
.cell{background:var(--panel);border:2px solid var(--line);border-radius:8px;padding:6px;display:flex;flex-direction:column;min-height:120px}
.cell.pickable{cursor:pointer}.cell.pickable:hover{border-color:#777}
.cell.chosen{border-color:var(--ok);box-shadow:0 0 0 2px var(--ok) inset}
.cell .cap{display:flex;justify-content:space-between;color:var(--dim);font-size:13px;margin-bottom:4px}
.cell .cap kbd{background:#2c2c36;border-radius:4px;padding:0 6px;color:var(--text)}
.cell .img{flex:1;display:flex;align-items:center;justify-content:center;background:#0b0b0e;border-radius:4px;min-height:200px}
.cell img{max-width:100%;max-height:62vh;display:block}
.cell img.orig{image-rendering:pixelated;width:100%;height:auto}
.none{color:var(--dim);font-size:13px;padding:20px;text-align:center}
.bar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:12px 0}
.bar .rej{border-color:var(--bad)}.bar .rej.on{background:var(--bad);color:#fff}
.verdict{font-weight:600}.verdict.ok{color:var(--ok)}.verdict.bad{color:var(--bad)}
#note{flex:1;min-width:220px}
article{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:12px 16px;margin-top:8px;white-space:pre-wrap}
article h3{margin:0 0 6px;color:var(--acc);font-size:16px}
.meta{color:var(--dim);font-size:13px}
body.zoom .row{grid-template-columns:repeat(2,minmax(0,1fr))}
body.zoom .cell img{max-height:80vh}
@media (max-width:900px){.row{grid-template-columns:repeat(2,minmax(0,1fr))}}
</style></head><body>
<header>
 <b>Педия: выбор</b>
 <button id="prev" title="стрелка влево">◀</button>
 <input id="jump" size="5" title="номер картинки">
 <button id="next" title="стрелка вправо">▶</button>
 <select id="filter">
  <option value="todo">без решения</option>
  <option value="all">все</option>
  <option value="picked">выбранные</option>
  <option value="none">отвергнутые</option>
 </select>
 <select id="need">
  <option value="1">есть хотя бы одна версия</option>
  <option value="3">есть все три версии</option>
  <option value="0">любые, даже без версий</option>
 </select>
 <span id="stats"></span>
</header>
<main id="main"></main>
<script>
const VARS=__VARS__;
let items=[],view=[],pos=0;
const $=s=>document.querySelector(s);
function esc(s){return String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
async function load(){items=await (await fetch('/api/items')).json();applyFilter(true)}
function applyFilter(keep){
 const f=$('#filter').value,need=+$('#need').value,cur=view[pos]&&view[pos].key;
 view=items.filter(it=>{
  if(it.have.length<need)return false;
  const c=it.pick&&it.pick.choice;
  if(f==='todo')return !c; if(f==='picked')return c&&c!=='none'; if(f==='none')return c==='none'; return true});
 pos=0; if(keep&&cur){const i=view.findIndex(v=>v.key===cur); if(i>=0)pos=i}
 draw()}
function stats(){
 const done=items.filter(i=>i.pick).length,rej=items.filter(i=>i.pick&&i.pick.choice==='none').length;
 const by={};VARS.forEach(v=>by[v[0]]=items.filter(i=>i.pick&&i.pick.choice===v[0]).length);
 $('#stats').textContent=`в списке ${view.length?pos+1:0} из ${view.length} · решено ${done} из ${items.length}: `+
  VARS.map(v=>v[1].split(' ')[0].toLowerCase()+' '+by[v[0]]).join(', ')+`, отвергнуто ${rej}`}
function draw(){
 stats();
 const it=view[pos];
 if(!it){$('#main').innerHTML='<p class="none">В этом списке картинок нет. Смените фильтр вверху.</p>';return}
 const c=it.pick&&it.pick.choice;
 let h=`<div class="meta">№ ${it.n} · серия ${it.batch} · ${esc(it.file)}${it.kind==='ship'?' · корабль':''}</div><div class="row">`;
 h+=`<div class="cell"><div class="cap"><span>Оригинал</span></div><div class="img"><img class="orig" src="/img/orig/${encodeURIComponent(it.key)}"></div></div>`;
 VARS.forEach((v,i)=>{
  const has=it.have.includes(v[0]);
  h+=`<div class="cell ${has?'pickable':''} ${c===v[0]?'chosen':''}" data-v="${v[0]}"><div class="cap"><span>${esc(v[1])}</span><kbd>${i+1}</kbd></div><div class="img">`+
   (has?`<img src="/img/${v[0]}/${encodeURIComponent(it.key)}?t=${Date.now()}">`:'<div class="none">ещё не нарисована</div>')+`</div></div>`});
 h+='</div><div class="bar">';
 h+=`<button class="rej ${c==='none'?'on':''}" id="rej">Отвергнуть все <kbd>0</kbd></button>`;
 h+=`<input id="note" placeholder="заметка: что не так или что поправить" value="${esc(it.pick&&it.pick.note||'')}">`;
 h+=c?`<span class="verdict ${c==='none'?'bad':'ok'}">${c==='none'?'отвергнуты все':'выбрана: '+esc(VARS.find(v=>v[0]===c)[1])} · ${esc(it.pick.time)}</span>`:'<span class="meta">решения нет</span>';
 h+='</div>';
 (it.articles.length?it.articles:[{title:'',text:'(текста статьи нет)'}]).forEach(a=>{
  h+=`<article>${a.title?`<h3>${esc(a.title)}</h3>`:''}${esc(a.text)}</article>`});
 $('#main').innerHTML=h;
 document.querySelectorAll('.cell.pickable').forEach(el=>el.onclick=()=>pick(el.dataset.v));
 $('#rej').onclick=()=>pick('none');
 $('#jump').value=it.n}
async function pick(choice){
 const it=view[pos]; if(!it)return;
 if(choice!=='none'&&!it.have.includes(choice))return;
 const note=($('#note')||{}).value||'';
 const r=await fetch('/api/pick',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:it.key,choice,note})});
 if(!r.ok){alert('Не записалось: '+await r.text());return}
 it.pick=await r.json();
 const f=$('#filter').value;
 if(f==='todo'){view.splice(pos,1); if(pos>=view.length)pos=Math.max(0,view.length-1)} else if(pos<view.length-1)pos++;
 draw()}
function go(d){if(!view.length)return;pos=Math.min(view.length-1,Math.max(0,pos+d));draw();scrollTo(0,0)}
$('#prev').onclick=()=>go(-1);$('#next').onclick=()=>go(1);
$('#filter').onchange=()=>applyFilter(true);$('#need').onchange=()=>applyFilter(true);
$('#jump').onchange=e=>{const n=+e.target.value;let i=view.findIndex(v=>v.n===n);
 if(i<0){$('#filter').value='all';$('#need').value='0';applyFilter(false);i=view.findIndex(v=>v.n===n)}
 if(i>=0){pos=i;draw()}};
document.addEventListener('keydown',e=>{
 if(e.target.tagName==='INPUT'){if(e.key==='Enter')e.target.blur();return}
 if(e.key==='ArrowRight')go(1);else if(e.key==='ArrowLeft')go(-1);
 else if('123'.includes(e.key)&&e.key.length===1)pick(VARS[+e.key-1][0]);
 else if(e.key==='0'||e.key==='x'||e.key==='X'||e.key==='ч'||e.key==='Ч')pick('none');
 else if(e.key==='z'||e.key==='Z'||e.key==='я'||e.key==='Я')document.body.classList.toggle('zoom')});
load();
</script></body></html>"""


def make_handler(state):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send(self, code, body, ctype="text/plain; charset=utf-8"):
            if isinstance(body, str):
                body = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def file(self, path):
            if not path or not os.path.exists(path):
                return self.send(404, "нет файла")
            with open(path, "rb") as f:
                self.send(200, f.read(), TYPES.get(os.path.splitext(path)[1].lower(), "application/octet-stream"))

        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            parts = [urllib.parse.unquote(p) for p in u.path.split("/") if p]
            if not parts:
                return self.send(200, PAGE.replace("__VARS__", json.dumps(VARIANTS, ensure_ascii=False)),
                                 "text/html; charset=utf-8")
            if parts == ["api", "items"]:
                state.refresh()
                return self.send(200, json.dumps(state.items(), ensure_ascii=False), "application/json; charset=utf-8")
            if len(parts) == 3 and parts[0] == "img":
                if parts[1] == "orig":
                    it = state.plan["info"].get(parts[2])
                    return self.file(os.path.join(ORIG, it["file"]) if it else None)
                return self.file(state.gen_path(parts[1], parts[2]))
            self.send(404, "нет такой страницы")

        def do_POST(self):
            if self.path != "/api/pick":
                return self.send(404, "нет такой страницы")
            try:
                d = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))).decode("utf-8"))
                key, choice, note = d["key"], d["choice"], str(d.get("note", ""))
            except Exception as e:                                         # noqa: BLE001
                return self.send(400, "плохой запрос: %s" % e)
            if key not in state.plan["info"] or choice not in CHOICES:
                return self.send(400, "нет такой картинки или выбора")
            path = "" if choice == "none" else (state.gen_path(choice, key) or "")
            if choice != "none" and not path:
                return self.send(400, "этой версии ещё нет")
            write_pick(key, choice, note, path)
            self.send(200, json.dumps(read_picks()[key], ensure_ascii=False), "application/json; charset=utf-8")
    return H


def summary():
    state = State()
    items = state.items()
    from collections import Counter
    c = Counter(it["pick"]["choice"] for it in items if it["pick"])
    have = Counter(len(it["have"]) for it in items)
    print("картинок %d, решено %d" % (len(items), sum(c.values())))
    for v, name in VARIANTS + [("none", "отвергнуты все")]:
        print("  %-26s %d" % (name, c.get(v, 0)))
    print("готово версий: " + ", ".join("%d - у %d" % kv for kv in sorted(have.items())))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve")
    s.add_argument("--port", type=int, default=8770)
    sub.add_parser("summary")
    a = ap.parse_args()
    if a.cmd == "summary":
        return summary()
    state = State()
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), make_handler(state))
    print("страница выбора: http://127.0.0.1:%d  (картинок %d)" % (a.port, len(state.plan["order"])), flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    sys.exit(main())
