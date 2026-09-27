#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""map_pick.py - выбор кадров карт: по 50 на странице, у каждого оригинал | в моде | новый.

Левая кнопка на картинке - увеличить (все три крупно и варианты пола), правая - выбрать её:
    новый     - кадр идёт в мод (обе копии мода hd, R-087), прежний - в art\_backup\map_updates
    в моде    - новое отклонено; в общую папку серии кладётся кадр мода, следующие карты строятся от него
    оригинал  - новое отклонено и рисуется заново: кадр убирается из серии, его карта встаёт в очередь
                видеокарты с новым seed и --fresh (без сборки из готового - вышел бы тот же кадр)
Решения копятся в art\maps\updates\pick_pending.json и уходят «на производство» каждые 50 штук
(или кнопкой). Только тогда меняются учёт updates.tsv, мод и серия; журнал - pick_log.tsv.
Страница живёт только на этой машине: http://127.0.0.1:8772

    tools\hdart\.venv\Scripts\python.exe tools\hdart\map_pick.py serve
    tools\hdart\.venv\Scripts\python.exe tools\hdart\map_pick.py summary
"""
import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
for p in (HERE, os.path.dirname(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

from PIL import Image                                   # noqa: E402
import common                                           # noqa: E402
import map_update as mu                                 # noqa: E402

ENC = "utf-8-sig"
PENDING = os.path.join(mu.OUT, "pick_pending.json")
LOG = os.path.join(mu.OUT, "pick_log.tsv")
MODS = [common.GAME_HD, os.path.join("user", "mods", "hd")]    # обе копии мода hd (R-087)
SERIES = os.path.join("art", "maps", "paint", "series")
SERIES_BK = os.path.join("art", "maps", "paint", "series_rejected")
MAPS = os.path.join("art", "maps", "paint", "series_maps.json")
RUN = "art/maps/paint/run_series3.sh"
SH = "C:/Program Files/Git/bin/sh.exe"
PER = 50
K = 4
CHOICES = {"new", "mod", "orig"}


def is_main(r):
    return os.path.basename(r["файл"]) == "%d.png" % int(r["кадр"])


def load_json(path, default):
    if os.path.exists(path):
        with io.open(path, encoding=ENC) as f:
            return json.load(f)
    return default


def save_json(path, data):
    tmp = path + ".tmp"
    with io.open(tmp, "w", encoding=ENC) as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def zip_of(n):
    for fn in os.listdir(mu.OUT):
        if fn.startswith("upd_%04d_" % int(n)) and fn.endswith(".zip"):
            return os.path.join(mu.OUT, fn)
    return None


def on_floor(im):
    bg = Image.new("RGBA", (32 * K, 40 * K), mu.DARK + (255,))
    if im is not None:
        im = im.convert("RGBA")
        bg.alpha_composite(im if im.size == bg.size else im.resize(bg.size, Image.NEAREST))
    out = io.BytesIO()
    bg.convert("RGB").save(out, "PNG")
    return out.getvalue()


class State:
    def __init__(self):
        import map_mockup as mm
        self.world = mm.World()
        self.lock = threading.RLock()
        self.cache = {}
        self.pending = load_json(PENDING, {})
        self.last = ""          # итог последней отправки - для строки на странице
        self.busy = False

    # ---------------------------------------------------------------- что показывать
    def items(self):
        led = mu.read_ledger()
        latest = {}
        for r in led:
            if is_main(r) and (r["файл"] not in latest or int(r["обновление"]) > int(latest[r["файл"]]["обновление"])):
                latest[r["файл"]] = r
        out = []
        for r in sorted(latest.values(), key=lambda r: (int(r["обновление"]), r["набор"], int(r["кадр"]))):
            if r["решение"] != "ждёт":
                continue
            key = "%s|%s" % (r["обновление"], r["файл"])
            nv = sum(1 for x in led if x["обновление"] == r["обновление"] and x["набор"] == r["набор"]
                     and x["кадр"] == r["кадр"] and not is_main(x))
            out.append({"key": key, "upd": int(r["обновление"]), "map": r["карта"], "terrain": r["террейн"],
                        "set": r["набор"], "frame": int(r["кадр"]), "what": r["что"], "mod": bool(r["в_моде"]),
                        "bad": r["годен"] == "0", "flags": r["флаги"], "variants": nv,
                        "pick": self.pending.get(key)})
        return out

    def row(self, key):
        """Строка учёта по ключу; учёт перечитывается, только когда файл изменился."""
        mt = os.path.getmtime(mu.LEDGER)
        with self.lock:
            if getattr(self, "_mt", None) != mt:
                self._rows = {"%s|%s" % (r["обновление"], r["файл"]): r for r in mu.read_ledger()}
                self._mt = mt
            return self._rows.get(key)

    # ---------------------------------------------------------------- картинки
    def image(self, kind, key, v=0):
        ck = (kind, key, v)
        if ck in self.cache:
            return self.cache[ck]
        r = self.row(key)
        if r is None:
            return None
        s, f = r["набор"], int(r["кадр"])
        im = None
        if kind == "orig":
            im = self.world.sprite(s, f, None)
        elif kind == "mod":
            p = os.path.join(mu.mod_dir(common.GAME_HD, s), "%d.png" % f)
            im = Image.open(p) if os.path.exists(p) else None
        elif kind == "new":
            name = r["файл"] if not v else r["файл"][:-4] + ".v%d.png" % v
            z = zip_of(r["обновление"])
            if z:
                with zipfile.ZipFile(z) as zf:
                    if name in zf.namelist():
                        im = Image.open(io.BytesIO(zf.read(name)))
                        im.load()
        if im is None and kind != "orig":
            return None
        data = on_floor(im)
        self.cache[ck] = data
        return data

    # ---------------------------------------------------------------- решения
    def pick(self, key, choice):
        """Решение записать; на PER-м - отправка. Отдаёт (выбор, пошла ли отправка)."""
        with self.lock:
            if choice is None:
                self.pending.pop(key, None)
            else:
                self.pending[key] = choice
            save_json(PENDING, self.pending)
            got = self.pending.get(key)
        go = len(self.pending) >= PER and self.start()
        return got, go

    def start(self):
        """Отправка в фоне; занятость ставится сразу, чтобы второй щелчок не пустил вторую."""
        with self.lock:
            if self.busy or not self.pending:
                return False
            self.busy = True
            todo = dict(self.pending)
        threading.Thread(target=self.produce, args=(todo,), daemon=True).start()
        return True

    def produce(self, todo):
        """На производство: учёт, мод, серия, очередь перерисовки."""
        try:
            self.last = self._produce(todo)
            with self.lock:
                for k in todo:
                    if self.pending.get(k) == todo[k]:
                        self.pending.pop(k)
                save_json(PENDING, self.pending)
        except Exception as e:                                          # noqa: BLE001
            self.last = "ОШИБКА отправки: %s - решения остались в %s" % (e, PENDING)
        finally:
            self.busy = False
            self.cache.clear()
        print(self.last, flush=True)

    def _produce(self, todo):
        led = mu.read_ledger()
        stamp = time.strftime("%Y%m%d_%H%M%S")
        n_mod = n_keep = 0
        redo = {}                        # (террейн, карта) -> {(набор, кадр)}
        log = []
        for key, choice in todo.items():
            n, f = key.split("|", 1)
            main = next((r for r in led if r["обновление"] == n and r["файл"] == f), None)
            if main is None or main["решение"] != "ждёт":
                continue
            s, fr = main["набор"], main["кадр"]
            same = [r for r in led if r["набор"] == s and r["кадр"] == fr and r["решение"] == "ждёт"]
            mine = [r for r in same if r["обновление"] == n]          # кадр и его варианты из этого обновления
            older = [r for r in same if r["обновление"] != n]         # прежние выдачи того же кадра - заменены
            if choice == "new":
                self._to_mod(mine, stamp)
                for r in mine:
                    r["решение"] = "в моде"
                n_mod += 1
            else:
                for r in mine:
                    r["решение"] = "отклонён"
                if choice == "mod":
                    self._series_from_mod(s, int(fr), stamp)
                    n_keep += 1
                else:
                    self._series_out(s, int(fr), stamp)
                    redo.setdefault((main["террейн"], main["карта"]), set()).add((s, int(fr)))
            for r in older:
                r["решение"] = "отклонён"
            log.append((time.strftime("%Y-%m-%d %H:%M:%S"), n, f, choice))
        # учёт перечитать перед записью: пока клались файлы, задание очереди могло дописать своё обновление
        dec = {(r["обновление"], r["файл"]): r["решение"] for r in led}
        fresh = mu.read_ledger()
        for r in fresh:
            got = dec.get((r["обновление"], r["файл"]))
            if got and r["решение"] == "ждёт":
                r["решение"] = got
        mu.write_ledger(fresh)
        mu.write_status(fresh)
        new_log = not os.path.exists(LOG)
        with io.open(LOG, "a", encoding=ENC if new_log else "utf-8") as fh:
            if new_log:
                fh.write("время\tобновление\tфайл\tвыбор\n")
            for ln in log:
                fh.write("\t".join(ln) + "\n")
        jobs = [self._queue_redo(t, b, fr) for (t, b), fr in sorted(redo.items())]
        return ("отправлено %s: в мод %d, оставлен прежний %d, на перерисовку %d кадров (%s)"
                % (time.strftime("%H:%M"), n_mod, n_keep, sum(len(v) for v in redo.values()),
                   "; ".join(jobs) or "очередь не нужна"))

    def _to_mod(self, rows, stamp):
        z = zip_of(rows[0]["обновление"])
        if z is None:
            raise RuntimeError("нет архива обновления %s" % rows[0]["обновление"])
        s, fr = rows[0]["набор"], int(rows[0]["кадр"])
        names = {os.path.basename(r["файл"]) for r in rows}
        bk_name = os.path.basename(z)[:-4]
        with zipfile.ZipFile(z) as zf:
            for mod in MODS:
                d = mu.mod_dir(mod, s)
                os.makedirs(d, exist_ok=True)
                bk = os.path.join(mu.BACKUP, bk_name, "game" if mod == common.GAME_HD else "repo", os.path.basename(d))
                # прежние варианты, которых в новом нет, уходят в резерв: иначе смешаются с новыми
                old = [fn for fn in os.listdir(d) if fn == "%d.png" % fr or fn.startswith("%d.v" % fr)]
                for fn in old:
                    os.makedirs(bk, exist_ok=True)
                    shutil.copy2(os.path.join(d, fn), os.path.join(bk, fn))
                    if fn not in names:
                        os.remove(os.path.join(d, fn))
                for r in rows:
                    dst = os.path.join(d, os.path.basename(r["файл"]))
                    with zf.open(r["файл"]) as src, open(dst, "wb") as out:
                        out.write(src.read())
                    if mu.sha(dst) != r["sha"]:
                        raise RuntimeError("не совпал после записи: %s" % dst)

    def _series_files(self, s, fr):
        d = os.path.join(SERIES, s + ".PCK")
        if not os.path.isdir(d):
            return d, []
        return d, [fn for fn in os.listdir(d) if fn == "%d.png" % fr or fn.startswith("%d.v" % fr)]

    def _series_out(self, s, fr, stamp):
        d, files = self._series_files(s, fr)
        bk = os.path.join(SERIES_BK, "pick_" + stamp, s + ".PCK")
        for fn in files:
            os.makedirs(bk, exist_ok=True)
            shutil.move(os.path.join(d, fn), os.path.join(bk, fn))

    def _series_from_mod(self, s, fr, stamp):
        self._series_out(s, fr, stamp)
        src = mu.mod_dir(common.GAME_HD, s)
        d = os.path.join(SERIES, s + ".PCK")
        os.makedirs(d, exist_ok=True)
        for fn in os.listdir(src) if os.path.isdir(src) else []:
            if fn == "%d.png" % fr or fn.startswith("%d.v" % fr):
                shutil.copy2(os.path.join(src, fn), os.path.join(d, fn))

    def _queue_redo(self, terrain, block, frames):
        cfg = load_json(MAPS, {}).get(block)
        fl = ",".join("%s:%d" % sf for sf in sorted(frames))
        if not cfg:
            return "%s: нет настроек в %s - кадры %s убраны из серии, перерисуются со следующим прогоном карты" \
                % (block, MAPS, fl)
        seed = int(time.time()) % 100000
        cmd = ["py", "-3.13", "tools/gpuq.py", "add", "--name", "map_redo_%s" % block, "--",
               SH, RUN, cfg.get("terrain", terrain), block, cfg["hints"], cfg["profile"], cfg.get("variants", ""),
               cfg.get("field_objects", ""), "--seed", str(seed), "--fresh", fl]
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", env=env)
        return "%s: %s" % (block, (p.stdout.strip().splitlines() or [p.stderr.strip()])[-1])


PAGE = r"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><title>Выбор кадров карт</title>
<style>
:root{--bg:#141418;--panel:#1f1f26;--line:#34343f;--text:#e8e6e0;--dim:#9a98a0;--acc:#f0c040;--new:#4caf6a;--mod:#4a90d9;--orig:#d98c3a}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:14px/1.4 system-ui,Segoe UI,sans-serif}
header{position:sticky;top:0;z-index:5;display:flex;flex-wrap:wrap;gap:10px;align-items:center;padding:8px 16px;background:#18181e;border-bottom:1px solid var(--line)}
header b{color:var(--acc)}
button{background:var(--panel);color:var(--text);border:1px solid var(--line);border-radius:6px;padding:5px 10px;font:inherit;cursor:pointer}
button:hover{border-color:var(--acc)}
#stats,#last{color:var(--dim)}#last{flex-basis:100%;font-size:13px}
.help{color:var(--dim);font-size:13px}
.help i{font-style:normal;padding:0 5px;border-radius:3px}
main{padding:12px 16px 40px;display:grid;grid-template-columns:repeat(auto-fill,minmax(410px,1fr));gap:10px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:6px}
.card.done{border-color:#555}
.cap{display:flex;justify-content:space-between;gap:6px;color:var(--dim);font-size:12px;margin-bottom:4px;white-space:nowrap;overflow:hidden}
.cap b{color:var(--text)}.cap .bad{color:#e0a060}
.three{display:grid;grid-template-columns:repeat(3,128px);gap:6px;justify-content:center}
.pic{position:relative;border:3px solid transparent;border-radius:4px;cursor:zoom-in;width:134px}
.pic img{display:block;width:128px;height:160px;image-rendering:pixelated}
.pic .lab{font-size:11px;color:var(--dim);text-align:center}
.pic.none{cursor:default;opacity:.35}
.pic.new.on{border-color:var(--new)}.pic.mod.on{border-color:var(--mod)}.pic.orig.on{border-color:var(--orig)}
.card.picked .pic:not(.on){opacity:.45}
#zoom{position:fixed;inset:0;background:rgba(0,0,0,.88);display:none;z-index:9;align-items:center;justify-content:center;flex-direction:column;gap:10px}
#zoom.show{display:flex}
#zoom .big{display:flex;gap:16px}
#zoom .big div{text-align:center;color:var(--dim)}
#zoom img{width:384px;height:480px;image-rendering:pixelated;border:3px solid transparent}
#zoom .vars img{width:192px;height:240px}
#zoom .vars{display:flex;gap:8px}
</style></head><body>
<header>
 <b>Карты: выбор</b>
 <button id="prev">◀</button><span id="pg"></span><button id="next">▶</button>
 <span id="stats"></span>
 <button id="send">Отправить на производство</button>
 <span class="help">левая кнопка - увеличить, правая - выбрать:
  <i style="background:#2d4d35">новый</i> в мод,
  <i style="background:#24384f">в моде</i> оставить прежний,
  <i style="background:#553a1c">оригинал</i> нарисовать заново</span>
 <span id="last"></span>
</header>
<main id="main"></main>
<div id="zoom"></div>
<script>
const PER=__PER__;
let items=[],page=0;
const $=s=>document.querySelector(s);
const KINDS=[['orig','оригинал'],['mod','в моде'],['new','новый']];
function esc(s){return String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
function src(kind,key,v){return `/img/${kind}/${v||0}/${encodeURIComponent(key)}`}
async function load(){
 const d=await (await fetch('/api/items')).json();
 items=d.items;$('#last').textContent=d.last||'';
 if(page*PER>=items.length)page=Math.max(0,Math.ceil(items.length/PER)-1);
 draw()}
function draw(){
 const pages=Math.max(1,Math.ceil(items.length/PER)),part=items.slice(page*PER,page*PER+PER);
 const picked=items.filter(i=>i.pick).length;
 $('#pg').textContent=`стр. ${page+1} из ${pages}`;
 $('#stats').textContent=`кадров без решения ${items.length} · выбрано к отправке ${picked} (сама уходит на ${PER})`;
 $('#main').innerHTML=part.map((it,i)=>{
  const h=`<div class="cap"><span><b>${esc(it.set)} ${it.frame}</b> · ${esc(it.map)} · обн. ${it.upd} · ${esc(it.what)}${it.variants?' · вариантов '+it.variants:''}</span>`+
   (it.bad?`<span class="bad" title="${esc(it.flags)}">брак по меркам</span>`:'')+'</div>';
  const p=KINDS.map(([k,l])=>{
   const has=k!=='mod'||it.mod;
   return `<div class="pic ${k} ${has?'':'none'} ${it.pick===k?'on':''}" data-i="${page*PER+i}" data-k="${k}">`+
    (has?`<img loading="lazy" src="${src(k,it.key)}">`:'<img>')+`<div class="lab">${l}${has?'':' - нет'}</div></div>`}).join('');
  return `<div class="card ${it.pick?'picked':''}">${h}<div class="three">${p}</div></div>`}).join('')||'<p class="help">Кадров без решения нет.</p>';
 document.querySelectorAll('.pic:not(.none)').forEach(el=>{
  el.onclick=()=>zoom(items[+el.dataset.i]);
  el.oncontextmenu=e=>{e.preventDefault();pick(items[+el.dataset.i],el.dataset.k)}});
 document.querySelectorAll('.pic.none').forEach(el=>el.oncontextmenu=e=>e.preventDefault())}
function zoom(it){
 let h='<div class="big">'+KINDS.map(([k,l])=>(k!=='mod'||it.mod)?`<div><img data-k="${k}" src="${src(k,it.key)}" style="border-color:${it.pick===k?'var(--'+k+')':'transparent'}"><br>${l}</div>`:'').join('')+'</div>';
 if(it.variants){h+='<div class="vars">';for(let v=1;v<=it.variants;v++)h+=`<div><img src="${src('new',it.key,v)}"><br><span style="color:#999">вариант ${v}</span></div>`;h+='</div>'}
 h+=`<div style="color:#aaa">${esc(it.set)} ${it.frame} · ${esc(it.map)} · обновление ${it.upd}${it.flags?' · '+esc(it.flags):''} - щелчок или Esc закрывает</div>`;
 h=h.replace('щелчок или Esc закрывает','правая кнопка на картинке - выбрать, левая или Esc - закрыть');
 $('#zoom').innerHTML=h;$('#zoom').classList.add('show');
 $('#zoom').oncontextmenu=e=>{e.preventDefault();const k=e.target.dataset&&e.target.dataset.k;
  if(k){$('#zoom').classList.remove('show');pick(it,k)}}}
$('#zoom').onclick=()=>$('#zoom').classList.remove('show');
async function pick(it,k){
 const choice=it.pick===k?null:k;
 const r=await fetch('/api/pick',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:it.key,choice})});
 if(!r.ok){alert('Не записалось: '+await r.text());return}
 const d=await r.json();it.pick=d.pick;draw();
 if(d.sending)setTimeout(poll,1500)}
async function poll(){
 const d=await (await fetch('/api/state')).json();
 $('#last').textContent=d.busy?'отправка идёт...':(d.last||'');
 if(d.busy)setTimeout(poll,1500);else load()}
$('#send').onclick=async()=>{
 if(!items.some(i=>i.pick)){alert('Нечего отправлять: ничего не выбрано');return}
 await fetch('/api/send',{method:'POST'});$('#last').textContent='отправка идёт...';setTimeout(poll,1000)};
$('#prev').onclick=()=>{if(page>0){page--;draw();scrollTo(0,0)}};
$('#next').onclick=()=>{if((page+1)*PER<items.length){page++;draw();scrollTo(0,0)}};
document.addEventListener('keydown',e=>{
 if(e.key==='Escape')$('#zoom').classList.remove('show');
 else if(e.key==='ArrowRight')$('#next').onclick();else if(e.key==='ArrowLeft')$('#prev').onclick()});
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

        def js(self, data):
            self.send(200, json.dumps(data, ensure_ascii=False), "application/json; charset=utf-8")

        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            parts = [urllib.parse.unquote(p) for p in u.path.split("/") if p]
            if not parts:
                return self.send(200, PAGE.replace("__PER__", str(PER)), "text/html; charset=utf-8")
            if parts == ["api", "items"]:
                return self.js({"items": state.items(), "last": state.last})
            if parts == ["api", "state"]:
                return self.js({"busy": state.busy, "last": state.last, "pending": len(state.pending)})
            if len(parts) == 4 and parts[0] == "img" and parts[1] in CHOICES:
                data = state.image(parts[1], parts[3], int(parts[2]))
                return self.send(200, data, "image/png") if data else self.send(404, "нет картинки")
            self.send(404, "нет такой страницы")

        def do_POST(self):
            if self.path == "/api/send":
                return self.js({"ok": state.start()})
            if self.path != "/api/pick":
                return self.send(404, "нет такой страницы")
            try:
                d = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))).decode("utf-8"))
                key, choice = d["key"], d.get("choice")
            except Exception as e:                                          # noqa: BLE001
                return self.send(400, "плохой запрос: %s" % e)
            if choice is not None and choice not in CHOICES:
                return self.send(400, "нет такого выбора")
            r = state.row(key)
            if r is None or r["решение"] != "ждёт":
                return self.send(400, "кадра нет или решение уже отправлено")
            if choice == "mod" and not r["в_моде"]:
                return self.send(400, "в моде этого кадра нет")
            got, go = state.pick(key, choice)
            self.js({"pick": got, "sending": go})
    return H


def summary():
    led = mu.read_ledger()
    from collections import Counter
    print("решения по кадрам (главные файлы):", dict(Counter(r["решение"] for r in led if is_main(r))))
    print("выбрано, не отправлено:", len(load_json(PENDING, {})))


def main():
    for st in (sys.stdout, sys.stderr):     # вывод в файл или окно запуска - cp1252 без этого (R-001)
        st.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve")
    s.add_argument("--port", type=int, default=8772)
    sub.add_parser("summary")
    a = ap.parse_args()
    if a.cmd == "summary":
        return summary()
    state = State()
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), make_handler(state))
    print("страница выбора карт: http://127.0.0.1:%d  (кадров без решения %d)" % (a.port, len(state.items())),
          flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    sys.exit(main())
