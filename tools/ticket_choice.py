#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""ticket_choice.py - страница выбора по тикетам, которые ждут решения Vitali.

Вопросы - census/tickets/choices.json (пишет командир тикетов): тикет, заголовок, что просит игрок, разбор,
листы (пути от корня репозитория), варианты (id, подпись, пояснение), рекомендуемый вариант.
Выбор и заметка дописываются в census/tickets/choice_picks.tsv - только дописыванием, последняя строка по
вопросу главная. Командир читает файл и делает выбранное. Ничего не генерирует, в мод и на сайт не пишет.

    py -3.13 tools\ticket_choice.py                 (http://localhost:8790)
    .claude/launch.json: ticket-choice
"""
import argparse
import csv
import io
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENC = "utf-8-sig"
QUESTIONS = os.path.join(ROOT, "census", "tickets", "choices.json")
PICKS = os.path.join(ROOT, "census", "tickets", "choice_picks.tsv")
PICK_COLS = ("qid", "ticket", "pick", "note", "when")
IMG_DIRS = ("art/_review/", "census/tickets/")         # отдаём картинки только отсюда
TYPES = {".png": "image/png", ".gif": "image/gif", ".jpg": "image/jpeg", ".webp": "image/webp"}
LOCK = threading.Lock()


def load_questions():
    with open(QUESTIONS, encoding=ENC) as f:
        return json.load(f)


def load_picks():
    """{qid: последняя строка выбора}."""
    out = {}
    if not os.path.exists(PICKS):
        return out
    with open(PICKS, encoding=ENC, newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            out[row["qid"]] = row
    return out


def add_pick(row):
    with LOCK:
        new = not os.path.exists(PICKS)
        with open(PICKS, "a", encoding=ENC if new else "utf-8", newline="") as f:
            w = csv.DictWriter(f, PICK_COLS, delimiter="\t")
            if new:
                w.writeheader()
            w.writerow({k: " ".join(str(row.get(k, "")).split()) for k in PICK_COLS})


PAGE = r"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Тикеты: выбор</title>
<style>
:root{--bg:#16181c;--card:#20242a;--ink:#e6e6e6;--dim:#9aa3ad;--acc:#4fb3a9;--rec:#d9a441;--line:#333a42}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,Segoe UI,sans-serif}
main{max-width:1100px;margin:0 auto;padding:16px}
h1{font-size:20px;margin:4px 0 12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:14px 16px;margin:0 0 16px}
.card.done{opacity:.75;border-color:var(--acc)}
.head{display:flex;gap:10px;align-items:baseline;flex-wrap:wrap}
.tk{color:var(--acc);font-weight:600}.st{color:var(--dim);font-size:13px}
h2{font-size:17px;margin:0}
p{margin:6px 0}.dim{color:var(--dim)}
.imgs{display:flex;gap:8px;overflow-x:auto;margin:10px 0}
.imgs figure{margin:0;flex:0 0 auto}.imgs img{max-height:260px;max-width:100%;border:1px solid var(--line);cursor:zoom-in;background:#000}
.imgs figcaption{font-size:12px;color:var(--dim)}
label.opt{display:block;border:1px solid var(--line);border-radius:6px;padding:8px 10px;margin:6px 0;cursor:pointer}
label.opt:hover{border-color:var(--acc)}
label.opt input{margin-right:8px}
.rec{color:var(--rec);font-size:12px;margin-left:6px}
textarea{width:100%;box-sizing:border-box;min-height:44px;background:#14171b;color:var(--ink);border:1px solid var(--line);border-radius:6px;padding:6px}
button{background:var(--acc);color:#082;color:#06201d;border:0;border-radius:6px;padding:7px 16px;font-weight:600;cursor:pointer;margin-top:6px}
.saved{color:var(--acc);font-size:13px;margin-left:8px}
#zoom{position:fixed;inset:0;background:rgba(0,0,0,.9);display:none;align-items:center;justify-content:center;cursor:zoom-out;z-index:9}
#zoom img{max-width:98vw;max-height:98vh}
</style></head><body><main>
<h1>Тикеты: что решить</h1>
<p class="dim">Выбор пишется в census/tickets/choice_picks.tsv; поменять можно в любой момент - главная последняя запись.</p>
<div id="list"></div></main>
<div id="zoom" onclick="this.style.display='none'"><img></div>
<script>
const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
function zoom(src){const z=document.getElementById('zoom');z.querySelector('img').src=src;z.style.display='flex'}
async function load(){
  const d=await (await fetch('/api')).json();const L=document.getElementById('list');L.innerHTML='';
  for(const q of d.questions){
    const p=d.picks[q.id]||{};const c=document.createElement('div');c.className='card'+(p.pick?' done':'');
    let h=`<div class="head"><span class="tk">${esc(q.ticket)}</span><h2>${esc(q.title)}</h2><span class="st">${esc(q.kind||'')}</span></div>`;
    if(q.asks)h+=`<p><b>Игрок:</b> ${esc(q.asks)}</p>`;
    if(q.found)h+=`<p><b>Разбор:</b> ${esc(q.found)}</p>`;
    if(q.images&&q.images.length){h+='<div class="imgs">';for(const im of q.images){const s='/img/'+encodeURI(im.path);
      h+=`<figure><img src="${s}" onclick="zoom('${s}')" loading="lazy"><figcaption>${esc(im.caption||'')}</figcaption></figure>`}h+='</div>'}
    if(q.question)h+=`<p><b>${esc(q.question)}</b></p>`;
    for(const o of q.options){h+=`<label class="opt"><input type="radio" name="${esc(q.id)}" value="${esc(o.id)}"${p.pick===o.id?' checked':''}>
      <b>${esc(o.label)}</b>${q.recommend===o.id?'<span class="rec">рекомендую</span>':''}<div class="dim">${esc(o.desc||'')}</div></label>`}
    h+=`<textarea placeholder="заметка (необязательно)">${esc(p.note||'')}</textarea>
      <button>Сохранить</button><span class="saved">${p.pick?'выбрано: '+esc(p.pick)+' · '+esc(p.when):''}</span>`;
    c.innerHTML=h;
    c.querySelector('button').onclick=async()=>{const r=c.querySelector('input:checked');
      if(!r){c.querySelector('.saved').textContent='выберите вариант';return}
      const res=await fetch('/pick',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({qid:q.id,ticket:q.ticket,pick:r.value,note:c.querySelector('textarea').value})});
      c.querySelector('.saved').textContent=res.ok?'сохранено: '+r.value:'ошибка записи';if(res.ok)c.classList.add('done')};
    L.appendChild(c)}
}
load();
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype):
        b = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        path = unquote(urlparse(self.path).path)
        if path == "/":
            return self.send(200, PAGE, "text/html; charset=utf-8")
        if path == "/api":
            data = {"questions": load_questions(), "picks": load_picks()}
            return self.send(200, json.dumps(data, ensure_ascii=False), "application/json; charset=utf-8")
        if path.startswith("/img/"):
            rel = path[5:].replace("\\", "/")
            full = os.path.normpath(os.path.join(ROOT, rel))
            ext = os.path.splitext(full)[1].lower()
            if (".." in rel.split("/") or not any(rel.startswith(d) for d in IMG_DIRS) or ext not in TYPES
                    or not os.path.isfile(full)):
                return self.send(404, "нет", "text/plain; charset=utf-8")
            with open(full, "rb") as f:
                return self.send(200, f.read(), TYPES[ext])
        self.send(404, "нет", "text/plain; charset=utf-8")

    def do_POST(self):
        if urlparse(self.path).path != "/pick":
            return self.send(404, "нет", "text/plain; charset=utf-8")
        n = int(self.headers.get("Content-Length", "0"))
        d = json.loads(self.rfile.read(n).decode("utf-8"))
        ids = {q["id"]: q for q in load_questions()}
        q = ids.get(d.get("qid"))
        if not q or d.get("pick") not in {o["id"] for o in q["options"]}:
            return self.send(400, "нет такого вопроса или варианта", "text/plain; charset=utf-8")
        add_pick({"qid": q["id"], "ticket": q["ticket"], "pick": d["pick"], "note": d.get("note", ""),
                  "when": time.strftime("%Y-%m-%d %H:%M")})
        self.send(200, "ok", "text/plain; charset=utf-8")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8790)
    a = ap.parse_args()
    load_questions()
    print("http://localhost:%d" % a.port, flush=True)
    ThreadingHTTPServer(("127.0.0.1", a.port), H).serve_forever()


if __name__ == "__main__":
    main()
