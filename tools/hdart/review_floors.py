# -*- coding: utf-8 -*-
r"""Приёмка полов глазами: слева оригинал, справа HD - и вердикт по каждому полу.

    tools\hdart\.venv\Scripts\python.exe tools\hdart\review_floors.py --mod "Пиратки\Dioxine_XPiratez\user\mods\hd" --sheets art/TERRAIN
    (открыть review\index.html, разметить, нажать «скачать вердикты»)
    tools\hdart\.venv\Scripts\python.exe tools\hdart\review_floors.py --report review\verdicts.csv

Для каждого пола рисуется пара: одно и то же поле клеток, слева выложенное ОРИГИНАЛЬНЫМ кадром
(увеличенным без сглаживания - как игра показывала бы его без пака), справа - кадром из пака.
Поле, а не одиночный тайл: половина брака видна только в укладке (швы, решётка, повтор детали).

`--mode variants` вместо этого сравнивает пак с вариантами и без них (нужны `<i>.v1.png` в паке) -
тем же способом проверяется, помогли ли варианты.

Страница `review\index.html` открывается прямо с диска: стрелки листают, 1 - оставить,
2 - забраковать, 3 - сомнительно, 0 - снять отметку. Вердикты кладутся в `verdicts.csv`
(кнопкой «скачать»), его же можно загрузить обратно и продолжить с того места.

`--report verdicts.csv` печатает итог и пишет рядом `verdicts_bad_sets.txt` - список наборов
через запятую, готовый для `--sets` перекраски.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import numpy as np                   # noqa: E402
from PIL import Image, ImageDraw     # noqa: E402
import xcom_sprites as xs            # noqa: E402
import build_pack                    # noqa: E402
import gen_hd                        # noqa: E402
import subjects_terrain              # noqa: E402

ENC = "utf-8-sig"


def subject_of(set_name):
    if set_name in gen_hd.SUBJECTS:
        return gen_hd.SUBJECTS[set_name], "SUBJECTS"
    subject, src = subjects_terrain.subject_for_set(set_name)
    if subject:
        return subject, "террейн %s" % src
    subject, src = subjects_terrain.subject_by_name(set_name)
    if subject:
        return subject, "имя (%s)" % src
    return "", "ЗАГЛУШКА"


def panels_image(panels, caption):
    """Несколько полей в ряд, у каждого своя подпись, общая подпись сверху."""
    gap, top = 12, 18
    w = sum(p[0].width for p in panels) + gap * (len(panels) - 1)
    h = max(p[0].height for p in panels)
    im = Image.new("RGB", (w, top + h), (28, 28, 30))
    d = ImageDraw.Draw(im)
    d.text((4, 4), caption, fill=(255, 232, 120))
    x = 0
    for img, text in panels:
        im.paste(img, (x, top))
        d.text((x + 6, top + 2), text, fill=(190, 190, 190))
        x += img.width + gap
    return im


def build_pairs(args):
    pairs_dir = os.path.join(args.out, "pairs")
    os.makedirs(pairs_dir, exist_ok=True)
    only = {s.strip().upper() for s in args.sets.split(",") if s.strip()}
    names = sorted(n for n in os.listdir(args.sheets)
                   if n.upper().endswith(".PCK") and os.path.isdir(os.path.join(args.sheets, n)))
    if only:
        names = [n for n in names if n.upper() in only or n.upper()[:-4] in only]

    items, skipped = [], []
    for name in names:
        set_dir = os.path.join(args.sheets, name)
        layout = os.path.join(set_dir, "layout.json")
        pack_dir = os.path.join(args.mod, "hd", args.pack_path, name) if args.pack_path \
            else os.path.join(args.mod, "hd", name)
        if not os.path.exists(layout) or not os.path.isdir(pack_dir):
            continue
        with open(layout, encoding=ENC) as f:
            info = json.load(f)
        info.setdefault("set", name)
        count, fw, fh = info["count"], info["frame_w"], info["frame_h"]
        types = info.get("types") or [-1] * count
        ground = info.get("ground") or [False] * count
        sheet = xs.Sheet(fw, fh, count, info["columns"], info["margin"])
        original = Image.open(os.path.join(set_dir, "original.png")).convert("RGBA")
        subject, src = subject_of(info["set"])

        floors = []
        for i in range(count):
            if types[i] != xs.MCD_FLOOR or not ground[i]:
                continue
            frame = sheet.cut(original, i, 1)
            box = frame.getbbox()
            if box is None or box[1] < fh - 16 - 6:
                continue
            area = float(np.asarray(frame.split()[3], np.float64).sum()) / 255.0
            floors.append((area, i, frame))
        floors.sort(key=lambda t: -t[0])

        for _, i, orig in floors[:max(1, args.per_set)]:
            png = os.path.join(pack_dir, "%d.png" % i)
            if not os.path.exists(png):
                skipped.append("%s #%d: нет кадра в паке" % (name, i))
                continue
            hd = Image.open(png).convert("RGBA")
            k = max(1, hd.width // fw)
            big = orig.resize((fw * k, fh * k), Image.NEAREST)
            if hd.size != big.size:
                hd = hd.resize(big.size, Image.LANCZOS)
            mask = big.split()[3].point(lambda v: 255 if v > 128 else 0)
            err = build_pack.chroma_error(hd, big, mask)

            def field_of(frames):
                return build_pack.ground_field(frames, args.cells, k).convert("RGB")

            def pack_b_frame():
                other = os.path.join(args.mod_b, "hd", args.pack_path, name) if args.pack_path \
                    else os.path.join(args.mod_b, "hd", name)
                png_b = os.path.join(other, "%d.png" % i)
                if not os.path.exists(png_b):
                    return None
                im = Image.open(png_b).convert("RGBA")
                return im.resize(hd.size, Image.LANCZOS) if im.size != hd.size else im

            if args.mode in ("packs", "three"):
                hd_b = pack_b_frame()
                if hd_b is None:
                    skipped.append("%s #%d: нет кадра во втором паке" % (name, i))
                    continue
                panels = [(field_of([hd_b]), "old pack"), (field_of([hd]), "new pack")]
                if args.mode == "three":
                    panels.insert(0, (field_of([big]), "original"))
            elif args.mode == "variants":
                variants = []
                n = 1
                while os.path.exists(os.path.join(pack_dir, "%d.v%d.png" % (i, n))):
                    variants.append(Image.open(os.path.join(pack_dir, "%d.v%d.png" % (i, n))).convert("RGBA"))
                    n += 1
                if not variants:
                    skipped.append("%s #%d: вариантов нет" % (name, i))
                    continue
                panels = [(field_of([hd]), "no variants"),
                          (field_of([hd] + variants), "with variants (%d)" % len(variants))]
            else:
                panels = [(field_of([big]), "original (game without the pack)"), (field_of([hd]), "HD pack")]

            def fit(im):
                if args.zoom and args.zoom != 1.0:
                    return im.resize((max(1, int(im.width * args.zoom)), max(1, int(im.height * args.zoom))),
                                     Image.NEAREST if args.zoom > 1 else Image.LANCZOS)
                if args.width <= 0 or im.width <= args.width:
                    return im
                return im.resize((args.width, max(1, im.height * args.width // im.width)), Image.LANCZOS)
            panels = [(fit(im), text) for im, text in panels]

            stem = (name[:-4] if name.upper().endswith(".PCK") else name)
            tag = "SUBJ" if src.startswith("SUBJECTS") else ("TERR" if src.startswith("террейн")
                                                             else ("NAME" if src.startswith("имя") else "NONE"))
            caption = "%s  #%d   dE %.1f   theme: %s" % (stem, i, err, tag)
            pair = panels_image(panels, caption)
            fn = "%s_%d.png" % (stem, i)
            pair.save(os.path.join(pairs_dir, fn))
            items.append({"set": name, "stem": stem, "frame": i, "err": round(err, 1),
                          "src": src, "file": "pairs/" + fn})
        if args.max and len(items) >= args.max:
            break

    items.sort(key=lambda r: -r["err"])
    return items, skipped


PAGE = u"""<!doctype html>
<meta charset="utf-8">
<title>Приёмка полов</title>
<style>
 body{margin:0;background:#1c1c1e;color:#ddd;font:14px/1.4 system-ui,Segoe UI,sans-serif}
 header{position:sticky;top:0;background:#141416;padding:8px 12px;display:flex;gap:12px;align-items:center;
        border-bottom:1px solid #333;flex-wrap:wrap}
 button{background:#2c2c30;color:#eee;border:1px solid #444;border-radius:6px;padding:6px 10px;cursor:pointer}
 button:hover{background:#3a3a40}
 .ok{border-color:#3c8c4a} .bad{border-color:#a04040} .maybe{border-color:#9a8030}
 #wrap{display:flex;gap:12px;padding:12px;align-items:flex-start}
 #list{width:250px;max-height:82vh;overflow:auto;border:1px solid #333;border-radius:6px}
 #list div{padding:4px 8px;cursor:pointer;border-bottom:1px solid #262628;white-space:nowrap;overflow:hidden}
 #list div.cur{background:#2e2e34}
 #view{flex:1}
 #view img{max-width:100%;image-rendering:auto;border:1px solid #333;border-radius:6px}
 #view.zoom img{max-width:none;image-rendering:pixelated}
 #view.zoom{overflow:auto;max-height:82vh}
 .tag{font-weight:600} .t1{color:#6fcf7f} .t2{color:#e06b6b} .t3{color:#d8bd5a}
 #meta{margin:6px 0 10px}
 small{color:#999}
</style>
<header>
  <b>Приёмка полов</b>
  <span id="pos"></span>
  <button onclick="mark(1)" class="ok">1 — оставить</button>
  <button onclick="mark(2)" class="bad">2 — забраковать</button>
  <button onclick="mark(3)" class="maybe">3 — сомнительно</button>
  <button onclick="mark(0)">0 — снять</button>
  <button onclick="zoom()">Z — крупнее</button>
  <button onclick="save()">скачать вердикты</button>
  <label style="cursor:pointer">загрузить<input type="file" onchange="load(this)" style="display:none"></label>
  <span id="stat"></span>
  <small>стрелки — листать, F — только неразмеченные</small>
</header>
<div id="wrap">
  <div id="list"></div>
  <div id="view">
    <div id="meta"></div>
    <img id="img">
  </div>
</div>
<script>
const items = ITEMS;
let verdict = {}, cur = 0, onlyNew = false;
const key = it => it.set + "#" + it.frame;
try { const s = localStorage.getItem("floorVerdicts"); if (s) verdict = JSON.parse(s); } catch (e) {}
function tag(v){ return v==1?"<span class='tag t1'>оставить</span>":v==2?"<span class='tag t2'>брак</span>":v==3?"<span class='tag t3'>сомнительно</span>":""; }
function draw(){
  const it = items[cur]; if(!it) return;
  document.getElementById("pos").textContent = (cur+1) + " / " + items.length;
  document.getElementById("img").src = it.file;
  document.getElementById("meta").innerHTML = "<b>" + it.stem + "</b> #" + it.frame +
    " &nbsp; отличие по цвету " + it.err + " &nbsp; тема: " + it.src + " &nbsp; " + tag(verdict[key(it)]);
  const l = document.getElementById("list");
  l.innerHTML = items.map((x,n)=>"<div class='"+(n==cur?"cur":"")+"' onclick='go("+n+")'>"+
      (verdict[key(x)]==1?"✓ ":verdict[key(x)]==2?"✗ ":verdict[key(x)]==3?"? ":"· ")+x.stem+" #"+x.frame+"</div>").join("");
  const c = l.querySelector(".cur"); if(c) c.scrollIntoView({block:"nearest"});
  const n1=Object.values(verdict).filter(v=>v==1).length, n2=Object.values(verdict).filter(v=>v==2).length,
        n3=Object.values(verdict).filter(v=>v==3).length;
  document.getElementById("stat").textContent = "оставить " + n1 + " · брак " + n2 + " · сомнительно " + n3;
}
function go(n){ cur = Math.max(0, Math.min(items.length-1, n)); draw(); }
function zoom(){ document.getElementById("view").classList.toggle("zoom"); }
function step(d){
  let n = cur;
  for(let i=0;i<items.length;i++){ n = (n + d + items.length) % items.length; if(!onlyNew || !verdict[key(items[n])]) break; }
  go(n);
}
function mark(v){
  const it = items[cur]; if(!it) return;
  if(v===0) delete verdict[key(it)]; else verdict[key(it)] = v;
  try { localStorage.setItem("floorVerdicts", JSON.stringify(verdict)); } catch (e) {}
  if(v!==0) step(1); else draw();
}
function save(){
  let out = "set,frame,verdict\\n";
  for(const it of items){ const v = verdict[key(it)]; if(v) out += it.set + "," + it.frame + "," + (v==1?"ok":v==2?"bad":"maybe") + "\\n"; }
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([out], {type:"text/csv"}));
  a.download = "verdicts.csv"; a.click();
}
function load(inp){
  const f = inp.files[0]; if(!f) return;
  const r = new FileReader();
  r.onload = () => {
    verdict = {};
    for(const line of r.result.split(/\\r?\\n/).slice(1)){
      const p = line.split(","); if(p.length < 3) continue;
      verdict[p[0] + "#" + p[1]] = p[2].trim()=="ok"?1:p[2].trim()=="bad"?2:3;
    }
    try { localStorage.setItem("floorVerdicts", JSON.stringify(verdict)); } catch (e) {}
    draw();
  };
  r.readAsText(f);
}
document.onkeydown = e => {
  if(e.key=="ArrowRight"||e.key==" ") { step(1); e.preventDefault(); }
  else if(e.key=="ArrowLeft") step(-1);
  else if("0123".includes(e.key)) mark(+e.key);
  else if(e.key.toLowerCase()=="z") zoom();
  else if(e.key.toLowerCase()=="f") { onlyNew = !onlyNew; document.getElementById("stat").textContent += onlyNew?" · только неразмеченные":""; }
};
draw();
</script>
"""


def report(path):
    """Итог по вердиктам: сколько чего и список наборов с браком для перекраски."""
    import csv
    bad, ok, maybe = [], [], []
    with open(path, encoding=ENC, newline="") as f:
        for row in csv.DictReader(f):
            v = (row.get("verdict") or "").strip()
            item = (row["set"], int(row["frame"]))
            (bad if v == "bad" else ok if v == "ok" else maybe).append(item)
    print("оставить: %d, брак: %d, сомнительно: %d" % (len(ok), len(bad), len(maybe)))
    sets = sorted({s for s, _ in bad})
    out = os.path.join(os.path.dirname(os.path.abspath(path)), "verdicts_bad_sets.txt")
    line = ",".join(s[:-4] if s.upper().endswith(".PCK") else s for s in sets)
    with open(out, "w", encoding=ENC) as f:
        f.write(line + "\n")
    print("наборов с браком: %d -> %s" % (len(sets), out))
    if bad:
        print("кадры: " + "; ".join("%s #%d" % (s, i) for s, i in bad[:40]) + ("..." if len(bad) > 40 else ""))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="пары «оригинал - HD» полем и страница приёмки")
    ap.add_argument("--report", default="", help="посчитать итог по готовому verdicts.csv и выйти")
    ap.add_argument("--mod", default="", help="мод с паками")
    ap.add_argument("--sheets", default="art/TERRAIN")
    ap.add_argument("--out", default="art/_review/review")
    ap.add_argument("--pack-path", default="TERRAIN", dest="pack_path")
    ap.add_argument("--sets", default="", help="только эти наборы, через запятую")
    ap.add_argument("--per-set", type=int, default=1, dest="per_set")
    ap.add_argument("--cells", type=int, default=4)
    ap.add_argument("--width", type=int, default=420, help="ширина каждой колонки (0 - как есть)")
    ap.add_argument("--zoom", type=float, default=0.0,
                    help="во сколько раз показать поле вместо подгонки по ширине: 1 - как есть "
                         "(пиксель в пиксель), 2 - вдвое крупнее. Отменяет --width")
    ap.add_argument("--max", type=int, default=0, help="хватит после стольких полов (проба)")
    ap.add_argument("--mode", choices=["orig", "variants", "packs", "three"], default="orig",
                    help="orig: оригинал против HD; variants: пак без вариантов против пака с ними; "
                         "packs: старый пак (--mod-b) против нового (--mod); "
                         "three: три колонки - оригинал, старый пак, новый")
    ap.add_argument("--mod-b", default="", dest="mod_b", help="второй мод для --mode packs (старый пак)")
    args = ap.parse_args(argv)

    if args.report:
        return report(args.report)
    if not args.mod:
        ap.error("нужен --mod (или --report)")
    if args.mode in ("packs", "three") and not args.mod_b:
        ap.error("--mode %s: нужен --mod-b со старым паком" % args.mode)

    os.makedirs(args.out, exist_ok=True)
    items, skipped = build_pairs(args)
    with open(os.path.join(args.out, "index.html"), "w", encoding="utf-8") as f:
        f.write(PAGE.replace("ITEMS", json.dumps(items, ensure_ascii=False)))
    with open(os.path.join(args.out, "pairs.json"), "w", encoding=ENC) as f:
        json.dump(items, f, ensure_ascii=False, indent=1)
    print("пар собрано: %d (наборов %d)" % (len(items), len({i["set"] for i in items})))
    if skipped:
        print("пропущено: %d (%s%s)" % (len(skipped), "; ".join(skipped[:5]), "..." if len(skipped) > 5 else ""))
    print("открой: %s" % os.path.join(os.path.abspath(args.out), "index.html"))
    print("разметил - «скачать вердикты», потом: review_floors.py --report %s"
          % os.path.join(args.out, "verdicts.csv"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
