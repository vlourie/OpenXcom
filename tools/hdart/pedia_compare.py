#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""pedia_compare.py - сравнение генераций педии одного вида: апскейл и до четырёх генераций рядом.

Три вида (Vitali 2026-09-26): своя (серии hd, photo, cine), 18+ (всё с «18» в метке),
комиксы (серия style, манера художника). Первая картинка - наш апскейл ESRGAN из мода hd
(нет его - оригинал), без номера; генерации пронумерованы 1-4, самые свежие. Под ними один раз
текст статьи педии и откуда каждая картинка (папка и файл).

Решения копятся в art\pedia_regen\compare.tsv: картинка, вид, выбор (1-4, none - всё брак,
later - подумаю ещё), время, заметка, путь выбранного файла (последняя строка по паре главная).
В мод ничего не пишется. Страница живёт только на этой машине: http://127.0.0.1:8771

    py -3.13 tools\hdart\pedia_compare.py serve     # поднять страницу
    py -3.13 tools\hdart\pedia_compare.py summary   # сколько генераций и решений по видам

Клавиши: 1-4 - выбрать, 0 или X - всё брак, пробел - подумаю ещё, стрелки - соседняя картинка,
клик по картинке - оригинальный размер (там стрелки листают картинки, Esc закрывает).
"""
import argparse
import io
import json
import os
import re
import sys
import time
import urllib.parse
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import common

ENC = "utf-8-sig"
ROOT = os.path.join("art", "pedia_regen")
ORIG = os.path.join(common.PIRATEZ, "Resources", "Pedia")
UPSCALE = os.path.join(common.GAME_HD, "hd", "UI_esrgan")
DECISIONS = os.path.join(ROOT, "compare.tsv")
# где лежат генерации: серии и пробы; файл <имя>__<метка>__<хвост>.png
SCAN = [ROOT, os.path.join("art", "_refs", "pedia_ab"), os.path.join("art", "_refs", "pedia_fix"),
        os.path.join("art", "_refs", "pedia_nude"), os.path.join("art", "_refs", "pedia_flatbg")]
KINDS = [("own", "Своя"), ("18", "18+"), ("comics", "Комиксы")]
SLOTS = 4
CHOICES = {"1", "2", "3", "4", "none", "later"}
TYPES = {".png": "image/png", ".gif": "image/gif", ".jpg": "image/jpeg"}
NAME = re.compile(r"(.+?)__([^_].*?)__(.+)\.png$", re.I)


def kind_of(tag):
    """Метка генерации -> вид. Порядок важен: photo_18 - это 18+, а не своя."""
    t = tag.lower()
    if "18" in t:
        return "18"
    if t == "style" or "comic" in t:
        return "comics"
    return "own"


def load(path, default):
    if os.path.exists(path):
        with io.open(path, encoding=ENC) as f:
            return json.load(f)
    return default


def ru(d):
    d = d or {}
    return d.get("ru") or d.get("en-US") or ""


def scan():
    """{(вид, имя в нижнем регистре): [генерация, ...]} - свежие первыми."""
    found = {}
    for top in SCAN:
        for dirpath, _, files in os.walk(top):
            for f in files:
                m = NAME.match(f)
                if not m:
                    continue
                path = os.path.join(dirpath, f)
                rel = os.path.relpath(path).replace(os.sep, "/")
                found.setdefault((kind_of(m.group(2)), m.group(1).lower()), []).append({
                    "path": rel, "dir": os.path.relpath(dirpath, "art").replace(os.sep, "/"),
                    "tag": m.group(2) + " " + m.group(3), "mtime": os.path.getmtime(path)})
    for gens in found.values():
        gens.sort(key=lambda g: -g["mtime"])
    return found


def read_decisions():
    res = {}
    if os.path.exists(DECISIONS):
        with io.open(DECISIONS, encoding=ENC) as f:
            for line in f:
                p = line.rstrip("\r\n").split("\t")
                if len(p) >= 4 and p[2] in CHOICES:
                    res[(p[0], p[1])] = {"choice": p[2], "time": p[3], "note": p[4] if len(p) > 4 else "",
                                         "path": p[5] if len(p) > 5 else ""}
    return res


def write_decision(key, kind, choice, note, path):
    new = not os.path.exists(DECISIONS)
    with io.open(DECISIONS, "a", encoding=ENC if new else "utf-8") as f:
        f.write("%s\t%s\t%s\t%s\t%s\t%s\n" % (key, kind, choice, time.strftime("%Y-%m-%d %H:%M:%S"),
                                              note.replace("\t", " ").replace("\n", " "), path))


class State:
    def __init__(self):
        self.plan = load(os.path.join(ROOT, "plan.json"), None)
        if not self.plan:
            sys.exit("нет %s: сначала pedia_batch.py plan" % os.path.join(ROOT, "plan.json"))
        self.text = load(os.path.join(ROOT, "pedia_text.json"), {})
        self.refresh()

    def refresh(self):
        self.gens = scan()
        self.known = {g["path"] for gens in self.gens.values() for g in gens}

    def stem(self, key):
        return os.path.splitext(self.plan["info"][key]["file"])[0]

    def upscale(self, key):
        p = os.path.join(UPSCALE, self.stem(key) + ".png")
        return p if os.path.exists(p) else None

    def slots(self, kind, key):
        return self.gens.get((kind, self.stem(key).lower()), [])[:SLOTS]

    def items(self):
        dec = read_decisions()
        res = []
        for i, k in enumerate(self.plan["order"]):
            it = self.plan["info"][k]
            arts = (self.text.get(k) or {}).get("articles") or []
            gens = {kd: [{"path": g["path"], "dir": g["dir"], "tag": g["tag"],
                          "date": time.strftime("%d.%m %H:%M", time.localtime(g["mtime"]))}
                         for g in self.slots(kd, k)] for kd, _ in KINDS}
            more = {kd: max(0, len(self.gens.get((kd, self.stem(k).lower()), [])) - SLOTS) for kd, _ in KINDS}
            res.append({
                "key": k, "n": i + 1, "file": it["file"], "kind": it["kind"],
                "up": bool(self.upscale(k)),
                "articles": [{"title": ru(a.get("title")), "text": ru(a.get("text"))} for a in arts],
                "gens": gens, "more": more,
                "dec": {kd: dec.get((k, kd)) for kd, _ in KINDS},
            })
        return res


PAGE = r"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><title>Сравнение генераций педии</title>
<style>
:root{--bg:#141418;--panel:#1f1f26;--line:#34343f;--text:#e8e6e0;--dim:#9a98a0;--acc:#f0c040;--ok:#4caf6a;--bad:#d9534f;--later:#5b8def}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:15px/1.45 system-ui,Segoe UI,sans-serif}
header{position:sticky;top:0;z-index:5;display:flex;flex-wrap:wrap;gap:10px;align-items:center;padding:10px 16px;background:#18181e;border-bottom:1px solid var(--line)}
header b{color:var(--acc)}
select,button,input{background:var(--panel);color:var(--text);border:1px solid var(--line);border-radius:6px;padding:6px 10px;font:inherit}
button{cursor:pointer}button:hover{border-color:var(--acc)}
.tabs button.on{background:var(--acc);color:#111;border-color:var(--acc);font-weight:600}
#stats{color:var(--dim);margin-left:auto}
main{padding:14px 16px 40px;max-width:2200px;margin:0 auto}
.row{display:grid;gap:10px}
.cell{background:var(--panel);border:2px solid var(--line);border-radius:8px;padding:6px;display:flex;flex-direction:column;min-width:0}
.cell.chosen{border-color:var(--ok);box-shadow:0 0 0 2px var(--ok) inset}
.cell .cap{display:flex;justify-content:space-between;gap:6px;color:var(--dim);font-size:13px;margin-bottom:4px}
.cell .cap b{color:var(--text);font-size:18px;line-height:1}
.cell .img{flex:1;display:flex;align-items:center;justify-content:center;background:#0b0b0e;border-radius:4px;min-height:160px}
.cell img{max-width:100%;max-height:60vh;display:block;cursor:zoom-in}
.cell img.px{image-rendering:pixelated;width:100%;height:auto}
.cell .src{color:var(--dim);font-size:12px;margin-top:4px;word-break:break-all}
.none{color:var(--dim);font-size:13px;padding:20px;text-align:center}
.bar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:12px 0}
.bar button{min-width:92px;font-weight:600}
.bar button.on{background:var(--ok);color:#111;border-color:var(--ok)}
.bar .rej{border-color:var(--bad)}.bar .rej.on{background:var(--bad);color:#fff;border-color:var(--bad)}
.bar .later{border-color:var(--later)}.bar .later.on{background:var(--later);color:#fff;border-color:var(--later)}
.bar button:disabled{opacity:.3;cursor:default}
.verdict{font-weight:600}.verdict.ok{color:var(--ok)}.verdict.bad{color:var(--bad)}.verdict.later{color:var(--later)}
#note{flex:1;min-width:220px}
article{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:12px 16px;margin-top:8px;white-space:pre-wrap}
article h3{margin:0 0 6px;color:var(--acc);font-size:16px}
.meta{color:var(--dim);font-size:13px;margin-bottom:6px}
kbd{background:#2c2c36;border-radius:4px;padding:0 5px;color:var(--text);font-size:12px;font-weight:400}
#zoom{position:fixed;inset:0;z-index:20;background:rgba(0,0,0,.93);display:none;overflow:auto;cursor:zoom-out}
#zoom.on{display:block}
#zoom .wrap{min-width:100%;min-height:100%;display:flex;align-items:center;justify-content:center;padding:30px}
#zoom img{display:block;max-width:none}
#zoom img.px{image-rendering:pixelated}
#zoom .zcap{position:fixed;top:0;left:0;right:0;padding:8px 16px;background:rgba(20,20,24,.9);color:var(--text);font-size:14px}
@media (max-width:1100px){.row{grid-template-columns:repeat(2,minmax(0,1fr))!important}}
</style></head><body>
<header>
 <b>Педия: генерации</b>
 <span class="tabs" id="tabs"></span>
 <button id="prev" title="стрелка влево">◀</button>
 <input id="jump" size="5" title="номер картинки">
 <button id="next" title="стрелка вправо">▶</button>
 <select id="filter">
  <option value="todo">без решения</option>
  <option value="later">подумаю ещё</option>
  <option value="picked">выбранные</option>
  <option value="none">брак</option>
  <option value="all">все</option>
 </select>
 <select id="need">
  <option value="2">генераций 2 и больше</option>
  <option value="1" selected>хотя бы одна генерация</option>
 </select>
 <span id="stats"></span>
</header>
<main id="main"></main>
<div id="zoom"><div class="zcap" id="zcap"></div><div class="wrap"><img id="zimg"></div></div>
<script>
const KINDS=__KINDS__, WORD=['первая','вторая','третья','четвёртая'];
let items=[],view=[],pos=0,kind=localStorage.getItem('pc_kind')||'own',zoomList=[],zoomAt=-1;
const $=s=>document.querySelector(s);
function esc(s){return String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
function tabs(){$('#tabs').innerHTML=KINDS.map(k=>`<button data-k="${k[0]}" class="${k[0]===kind?'on':''}">${esc(k[1])}</button>`).join(' ');
 document.querySelectorAll('#tabs button').forEach(b=>b.onclick=()=>{kind=b.dataset.k;try{localStorage.setItem('pc_kind',kind)}catch(e){};tabs();applyFilter(false)})}
async function load(){items=await (await fetch('/api/items')).json();tabs();applyFilter(true)}
function applyFilter(keep){
 const f=$('#filter').value,need=+$('#need').value,cur=view[pos]&&view[pos].key;
 view=items.filter(it=>{
  if(it.gens[kind].length<need)return false;
  const c=it.dec[kind]&&it.dec[kind].choice;
  if(f==='todo')return !c; if(f==='later')return c==='later'; if(f==='none')return c==='none';
  if(f==='picked')return c&&c!=='none'&&c!=='later'; return true});
 pos=0; if(keep&&cur){const i=view.findIndex(v=>v.key===cur); if(i>=0)pos=i}
 draw()}
function stats(){
 const mine=items.filter(i=>i.gens[kind].length),d=mine.map(i=>i.dec[kind]&&i.dec[kind].choice);
 const picked=d.filter(c=>c&&c!=='none'&&c!=='later').length,rej=d.filter(c=>c==='none').length,lat=d.filter(c=>c==='later').length;
 $('#stats').textContent=`в списке ${view.length?pos+1:0} из ${view.length} · с генерациями ${mine.length}: выбрано ${picked}, брак ${rej}, подумать ${lat}`}
function chosenSlot(it){const d=it.dec[kind];if(!d||!/^[1-4]$/.test(d.choice))return -1;
 const i=it.gens[kind].findIndex(g=>g.path===d.path);return i}
function draw(){
 stats();
 const it=view[pos];
 if(!it){$('#main').innerHTML='<p class="none">В этом списке картинок нет. Смените вид или фильтр вверху.</p>';return}
 const gens=it.gens[kind],d=it.dec[kind],c=d&&d.choice,ch=chosenSlot(it);
 zoomList=[{src:`/img/base/${encodeURIComponent(it.key)}`,px:!it.up,cap:it.up?'Апскейл ESRGAN (мод hd, UI_esrgan)':'Оригинал Пираток'}];
 let h=`<div class="meta">№ ${it.n} · ${esc(it.file)} · раздел ${esc(it.kind||'—')}${it.more[kind]?` · ещё ${it.more[kind]} старых генераций не показаны`:''}</div>`;
 h+=`<div class="row" style="grid-template-columns:repeat(${gens.length+1},minmax(0,1fr))">`;
 h+=`<div class="cell"><div class="cap"><span>${it.up?'Наш апскейл':'Оригинал'}</span>${it.up?`<a href="#" id="orig" style="color:var(--dim)">оригинал 320×200</a>`:''}</div>`+
    `<div class="img"><img data-z="0" class="${it.up?'':'px'}" src="${zoomList[0].src}"></div><div class="src">${it.up?'hd/UI_esrgan/':'Piratez/Resources/Pedia/'}${esc(it.file)}</div></div>`;
 gens.forEach((g,i)=>{
  const src=`/img/gen?p=${encodeURIComponent(g.path)}`;
  zoomList.push({src,px:false,cap:`${i+1} · ${g.dir} · ${g.tag} · ${g.date}`});
  h+=`<div class="cell ${i===ch?'chosen':''}"><div class="cap"><b>${i+1}</b><span>${esc(g.date)}</span></div>`+
     `<div class="img"><img data-z="${i+1}" src="${src}"></div><div class="src">${esc(g.dir)} · ${esc(g.tag)}</div></div>`});
 h+='</div><div class="bar">';
 WORD.forEach((w,i)=>{h+=`<button data-c="${i+1}" class="${i===ch?'on':''}" ${i<gens.length?'':'disabled'}>${w} <kbd>${i+1}</kbd></button>`});
 h+=`<button data-c="none" class="rej ${c==='none'?'on':''}">всё брак <kbd>0</kbd></button>`;
 h+=`<button data-c="later" class="later ${c==='later'?'on':''}">подумаю ещё <kbd>пробел</kbd></button>`;
 h+=`<input id="note" placeholder="заметка: что не так или что поправить" value="${esc(d&&d.note||'')}">`;
 h+='</div><div class="meta">';
 if(c){const cls=c==='none'?'bad':c==='later'?'later':'ok',t=c==='none'?'всё брак':c==='later'?'подумаю ещё':
   (ch>=0?`выбрана ${WORD[ch]}`:`выбран файл, которого сейчас нет среди четырёх: ${esc(d.path)}`);
  h+=`<span class="verdict ${cls}">${t}</span> · ${esc(d.time)}`} else h+='решения нет';
 h+='</div>';
 (it.articles.length?it.articles:[{title:'',text:'(текста статьи нет)'}]).forEach(a=>{
  h+=`<article>${a.title?`<h3>${esc(a.title)}</h3>`:''}${esc(a.text)}</article>`});
 $('#main').innerHTML=h;
 document.querySelectorAll('.bar button[data-c]').forEach(b=>b.onclick=()=>decide(b.dataset.c));
 document.querySelectorAll('.cell img').forEach(im=>im.onclick=()=>zoom(+im.dataset.z));
 const o=$('#orig'); if(o)o.onclick=e=>{e.preventDefault();zoomList.push({src:`/img/orig/${encodeURIComponent(it.key)}`,px:true,cap:'Оригинал Пираток (увеличен ×3)',scale:3});zoom(zoomList.length-1)};
 $('#jump').value=it.n}
function zoom(i){
 if(i<0||i>=zoomList.length)return; zoomAt=i; const z=zoomList[i],img=$('#zimg');
 img.className=z.px?'px':''; img.style.width=''; img.onload=()=>{if(z.scale)img.style.width=img.naturalWidth*z.scale+'px';
  $('#zcap').textContent=`${z.cap} · ${img.naturalWidth}×${img.naturalHeight} · ← → листать, Esc или клик - закрыть`};
 img.src=z.src; $('#zoom').classList.add('on'); $('#zoom').scrollTo(0,0)}
function unzoom(){$('#zoom').classList.remove('on');zoomAt=-1}
$('#zoom').onclick=unzoom;
async function decide(choice){
 const it=view[pos]; if(!it)return;
 const gens=it.gens[kind];
 if(/^[1-4]$/.test(choice)&&+choice>gens.length)return;
 const note=($('#note')||{}).value||'';
 const path=/^[1-4]$/.test(choice)?gens[+choice-1].path:'';
 const r=await fetch('/api/decide',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:it.key,kind,choice,note,path})});
 if(!r.ok){alert('Не записалось: '+await r.text());return}
 it.dec[kind]=await r.json();
 const f=$('#filter').value;
 if(f==='todo'){view.splice(pos,1); if(pos>=view.length)pos=Math.max(0,view.length-1)} else if(pos<view.length-1)pos++;
 draw(); scrollTo(0,0)}
function go(d){if(!view.length)return;pos=Math.min(view.length-1,Math.max(0,pos+d));draw();scrollTo(0,0)}
$('#prev').onclick=()=>go(-1);$('#next').onclick=()=>go(1);
$('#filter').onchange=()=>applyFilter(true);$('#need').onchange=()=>applyFilter(true);
$('#jump').onchange=e=>{const n=+e.target.value;let i=view.findIndex(v=>v.n===n);
 if(i<0){$('#filter').value='all';$('#need').value='1';applyFilter(false);i=view.findIndex(v=>v.n===n)}
 if(i>=0){pos=i;draw()}};
document.addEventListener('keydown',e=>{
 if(zoomAt>=0){if(e.key==='Escape')unzoom();else if(e.key==='ArrowRight')zoom(Math.min(zoomAt+1,zoomList.length-1));
  else if(e.key==='ArrowLeft')zoom(Math.max(zoomAt-1,0));e.preventDefault();return}
 if(e.target.tagName==='INPUT'){if(e.key==='Enter')e.target.blur();return}
 if(e.key==='ArrowRight')go(1);else if(e.key==='ArrowLeft')go(-1);
 else if(/^[1-4]$/.test(e.key))decide(e.key);
 else if(e.key==='0'||e.key==='x'||e.key==='X'||e.key==='ч'||e.key==='Ч')decide('none');
 else if(e.key===' '){e.preventDefault();decide('later')}});
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
                return self.send(200, PAGE.replace("__KINDS__", json.dumps(KINDS, ensure_ascii=False)),
                                 "text/html; charset=utf-8")
            if parts == ["api", "items"]:
                state.refresh()
                return self.send(200, json.dumps(state.items(), ensure_ascii=False), "application/json; charset=utf-8")
            if parts == ["img", "gen"]:
                p = urllib.parse.parse_qs(u.query).get("p", [""])[0]
                return self.file(p if p in state.known else None)      # только найденные генерации
            if len(parts) == 3 and parts[0] == "img" and parts[2] in state.plan["info"]:
                key = parts[2]
                if parts[1] == "orig":
                    return self.file(os.path.join(ORIG, state.plan["info"][key]["file"]))
                if parts[1] == "base":
                    return self.file(state.upscale(key) or os.path.join(ORIG, state.plan["info"][key]["file"]))
            self.send(404, "нет такой страницы")

        def do_POST(self):
            if self.path != "/api/decide":
                return self.send(404, "нет такой страницы")
            try:
                d = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))).decode("utf-8"))
                key, kind, choice = d["key"], d["kind"], d["choice"]
                note, path = str(d.get("note", "")), str(d.get("path", ""))
            except Exception as e:                                         # noqa: BLE001
                return self.send(400, "плохой запрос: %s" % e)
            if key not in state.plan["info"] or kind not in dict(KINDS) or choice not in CHOICES:
                return self.send(400, "нет такой картинки, вида или выбора")
            if choice.isdigit() and path not in {g["path"] for g in state.slots(kind, key)}:
                return self.send(400, "этой генерации нет - обновите страницу")
            write_decision(key, kind, choice, note, path if choice.isdigit() else "")
            self.send(200, json.dumps(read_decisions()[(key, kind)], ensure_ascii=False),
                      "application/json; charset=utf-8")
    return H


def summary():
    state = State()
    items = state.items()
    for kd, name in KINDS:
        mine = [it for it in items if it["gens"][kd]]
        c = Counter((it["dec"][kd] or {}).get("choice", "-") for it in mine)
        per = Counter(min(len(it["gens"][kd]) + it["more"][kd], 9) for it in mine)
        print("%-8s картинок с генерациями %d (%s); выбрано %d, брак %d, подумать %d, без решения %d" % (
            name, len(mine), ", ".join("%d шт. - у %d" % kv for kv in sorted(per.items())) or "нет",
            sum(v for k, v in c.items() if k.isdigit()), c["none"], c["later"], c["-"]))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve")
    s.add_argument("--port", type=int, default=8771)
    sub.add_parser("summary")
    a = ap.parse_args()
    if a.cmd == "summary":
        return summary()
    state = State()
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), make_handler(state))
    print("страница сравнения: http://127.0.0.1:%d  (картинок %d)" % (a.port, len(state.plan["order"])), flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    sys.exit(main())
