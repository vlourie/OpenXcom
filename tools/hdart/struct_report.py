#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""STRUCT_GUIDE_V1 - мерка лесенки, слепая страница A/B/C и ворота. Без модели.

stair_follow - доля «зубцов» лесенки, по которым пошла альфа итогового кадра: зона - пиксели x4, где
силуэт оригинала nearest и спрямлённый struct_guide расходятся; в ней альфа > 0.5 совпала с nearest -
ступень, со спрямлённым - линия. 1.0 - край обводит пиксели, 0.0 - край ровный. Только там, где guide
нашёл лесенку: прямые стены и настоящие уступы в зону не входят.

    py -3.13 tools/hdart/struct_report.py stair [--v1]   # мерка по A, B, C (--v1: все 20 предметов v1)
    py -3.13 tools/hdart/struct_report.py page            # слепая страница: на предмет три кадра X/Y/Z
    py -3.13 tools/hdart/struct_report.py report <tsv>    # раскрыть и посчитать ворота
"""
import json
import os
import random
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.dirname(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
ROOT = os.path.dirname(os.path.dirname(HERE))

import numpy as np                      # noqa: E402
from PIL import Image                   # noqa: E402

import struct_guide as sg               # noqa: E402

ENC = "utf-8-sig"
V1 = "art/objects/generation/probes/photo-accept-v1"
OUT = "art/objects/generation/probes/struct-guide-v1"
SEED = "struct-guide-v1"
OUTCOMES = ["PASS", "PARTIAL", "FAIL"]
CLASSES = ["PIXEL_STEP_TRACING", "MAJOR_GEOMETRY", "WRONG_IDENTITY", "DETAIL_LOSS", "BAD_MATERIAL",
           "INVENTED_DETAIL", "BAD_ALPHA"]
GATE = {"primary_fixed_min": 5, "new_geometry_max": 0, "new_identity_max": 0}


def load(p):
    if not os.path.exists(p):
        return None
    with open(p, encoding=ENC) as f:
        return json.load(f)


def dump(obj, p):
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    with open(p, "w", encoding=ENC) as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def piece_path(variant, src):
    """Кусок по src задания (кадр, который рисовался), а не по asset_id семейства."""
    s, f = src.split(":")
    base = os.path.join(V1, "render") if variant == "A" else os.path.join(OUT, variant)
    return os.path.join(base, "%s.PCK" % s.upper(), "%s.png" % f)


def stair_zone(sprite):
    """Зона лесенки x4 для кадра (весь спрайт): (nearest, спрямлённый, зона) - bool HxW x4."""
    import photo_base as pb
    m = pb.guide(sprite)["m"]
    h, w = m.shape
    near = np.repeat(np.repeat(m, 4, 0), 4, 1)
    smooth = sg.coverage([sg.smooth_loop(L) for L in sg.loops(m)], w, h, 4) > 0.5
    return near, smooth, near != smooth


def stair_follow(sprite, piece):
    near, smooth, zone = stair_zone(sprite)
    a = np.asarray(piece.convert("RGBA"))[..., 3] > 127
    if a.shape != zone.shape:
        raise SystemExit("кусок %s, а кадр x4 %s" % (a.shape, zone.shape))
    z = int(zone.sum())
    if not z:
        return None, 0
    step = int((a == near)[zone].sum())
    return round(step / z, 3), z


def stair(all_v1=False):
    import map_mockup as mm
    world = mm.World()
    jobs = load(os.path.join(V1 if all_v1 else OUT, "jobs.json"))
    rows = []
    for j in jobs:
        s, f = j["src"].split(":")
        sprite = world.sprite(s.lower(), int(f), None).convert("RGBA")
        r = {"asset_id": j["asset_id"], "group": j.get("group", j.get("stratum", ""))}
        for v in (("A",) if all_v1 else ("A", "B", "C")):
            p = piece_path(v, j["src"])
            if os.path.exists(p):
                r[v], r["zone"] = stair_follow(sprite, Image.open(p))
        rows.append(r)
        print("%-24s %-10s зона %4s  %s" % (r["asset_id"], r["group"], r.get("zone", "-"),
                                          "  ".join("%s %s" % (v, r.get(v, "-")) for v in "ABC")), flush=True)
    if not all_v1:
        dump(rows, os.path.join(OUT, "stair.json"))
    return rows


PAGE = r"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>STRUCT_GUIDE_V1 вслепую</title>
<style>
:root{--bg:#18181c;--fg:#e8e8ee;--mut:#9a9aa6;--acc:#8ab4ff;--ok:#2e7d4f;--part:#8a6d1e;--bad:#8e2f2f}
body{background:var(--bg);color:var(--fg);font:14px system-ui,sans-serif;margin:16px}
.mut{color:var(--mut)}.row{border-top:1px solid #333;padding:12px 0}
.cols{display:flex;gap:10px;flex-wrap:wrap;align-items:flex-start}.col{max-width:100%}
.t{font-size:12px;color:var(--mut)}img{max-width:100%;height:auto;background:#000}img.px{image-rendering:pixelated}
.cand{border:1px solid #333;border-radius:6px;padding:6px;margin-top:8px}
.pair{display:flex;gap:6px;flex-wrap:wrap}
button{background:#33333b;color:var(--fg);border:1px solid #44444d;border-radius:4px;padding:2px 8px;cursor:pointer;font-size:12px}
button.on[data-v=PASS]{background:var(--ok)}button.on[data-v=PARTIAL]{background:var(--part)}button.on[data-v=FAIL]{background:var(--bad)}
button.on.cls{background:#7a5ab8}.btns{display:flex;gap:4px;flex-wrap:wrap;margin-top:6px}
input[type=text]{width:100%;box-sizing:border-box;background:#1f1f24;color:var(--fg);border:1px solid #44444d;border-radius:4px;padding:3px;margin-top:6px}
textarea{width:100%;height:200px;background:#1f1f24;color:var(--fg);box-sizing:border-box}
</style></head><body>
<h1>STRUCT_GUIDE_V1 - три кадра одного предмета, вслепую</h1>
<div class="mut">__N__ предметов. У каждого слева оригинал x4, дальше три кадра X, Y, Z в случайном порядке
(на полу боя и на светлом). Какой из них откуда - не сказано. По каждому кадру: PASS / PARTIAL / FAIL и,
если не PASS, классы брака. PIXEL_STEP_TRACING - края кубиками по пикселям оригинала. Если края ровные,
но предмет стал другим (другая форма, другая вещь) - это FAIL с MAJOR_GEOMETRY или WRONG_IDENTITY.
Ответ копится в браузере, TSV внизу - прислать целиком.</div>
<div id="rows"></div>
<h2>TSV</h2><textarea id="tsv" readonly></textarea>
<script>
const DATA = __DATA__;
const CLS = __CLS__;
const OUTC = __OUTC__;
const KEY = "struct-guide-v1";
let st = {}; try { st = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) {}
function save(){ try { localStorage.setItem(KEY, JSON.stringify(st)); } catch (e) {} tsv(); }
function tsv(){
  const L = [["asset_id", "slot", "outcome", "classes", "note"].join("\t")];
  for (const r of DATA) for (const c of r.cand) { const s = (st[r.asset] || {})[c.slot] || {};
    L.push([r.asset, c.slot, s.o || "", Object.keys(s.k || {}).filter(k => s.k[k]).join(","),
            (s.n || "").replace(/[\t\n]/g, " ")].join("\t")); }
  document.getElementById("tsv").value = L.join("\n");
}
const root = document.getElementById("rows");
DATA.forEach((r, i) => {
  st[r.asset] = st[r.asset] || {};
  const row = document.createElement("div"); row.className = "row";
  row.innerHTML = `<div><b>${i + 1}. ${r.asset}</b> <span class="mut">${r.what}</span></div>
    <div class="cols"><div class="col"><div class="t">оригинал x4</div><img class="px" src="${r.orig}" width="${r.w}" height="${r.h}"></div></div>`;
  for (const c of r.cand) {
    const s = st[r.asset][c.slot] = st[r.asset][c.slot] || {}; s.k = s.k || {};
    const box = document.createElement("div"); box.className = "cand";
    box.innerHTML = `<b>${c.slot}</b><div class="pair">` + c.img.map(([f, t]) =>
      `<div class="col"><div class="t">${t}</div><img src="${f}" width="${r.w}" height="${r.h}" loading="lazy"></div>`).join("") + `</div>`;
    const ob = document.createElement("div"); ob.className = "btns";
    for (const v of OUTC) { const e = document.createElement("button"); e.textContent = v; e.dataset.v = v;
      if (s.o === v) e.classList.add("on");
      e.onclick = () => { s.o = s.o === v ? "" : v; ob.querySelectorAll("button").forEach(x => x.classList.toggle("on", x.dataset.v === s.o)); save(); };
      ob.appendChild(e); }
    box.appendChild(ob);
    const kb = document.createElement("div"); kb.className = "btns";
    for (const v of CLS) { const e = document.createElement("button"); e.textContent = v; e.className = "cls";
      if (s.k[v]) e.classList.add("on");
      e.onclick = () => { s.k[v] = !s.k[v]; e.classList.toggle("on", s.k[v]); save(); }; kb.appendChild(e); }
    box.appendChild(kb);
    const n = document.createElement("input"); n.type = "text"; n.placeholder = "заметка"; n.value = s.n || "";
    n.oninput = () => { s.n = n.value; save(); }; box.appendChild(n);
    row.appendChild(box);
  }
  root.appendChild(row);
});
tsv();
</script></body></html>"""


def on_bg(piece, rgb):
    im = Image.new("RGBA", piece.size, tuple(rgb) + (255,))
    im.alpha_composite(piece)
    return im.convert("RGB")


def page():
    """Слепая страница: оригинал x4 и три кадра под случайными буквами; ключ - в key.json рядом."""
    import map_mockup as mm
    import obj_series as osr
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
    data, key = [], {}
    for n, j in enumerate(order, 1):
        paths = {v: piece_path(v, j["src"]) for v in "ABC"}
        if not all(os.path.exists(p) for p in paths.values()):
            print("%s: нет всех трёх кадров - пропуск" % j["asset_id"])
            continue
        s, f = j["src"].split(":")
        orig = world.sprite(s.lower(), int(f), None).convert("RGBA")
        tag = "%02d" % n
        on = osr.on_floor(orig.resize((cw // 2, ch // 2), Image.NEAREST), (cw // 2, ch // 2))
        on.resize((cw, ch), Image.NEAREST).save(os.path.join(d, tag + "_o.png"))
        vs = list("ABC")
        rnd.shuffle(vs)
        cand = []
        for slot, v in zip("XYZ", vs):
            piece = Image.open(paths[v]).convert("RGBA")
            img = []
            for k, (im, t) in enumerate([(osr.on_floor(piece, piece.size), "на полу"),
                                         (on_bg(piece, (235, 235, 235)), "на светлом")]):
                fn = "%s_%s%d.png" % (tag, slot, k)
                im.resize((cw, ch), Image.LANCZOS).save(os.path.join(d, fn))
                img.append((fn, t))
            cand.append({"slot": slot, "img": img})
            key.setdefault(j["asset_id"], {})[slot] = v
        data.append({"asset": j["asset_id"], "what": j["what"], "orig": tag + "_o.png", "cand": cand,
                     "w": cw, "h": ch})
    html = PAGE.replace("__DATA__", json.dumps(data, ensure_ascii=False)).replace(
        "__CLS__", json.dumps(CLASSES)).replace("__OUTC__", json.dumps(OUTCOMES)).replace("__N__", str(len(data)))
    with open(os.path.join(d, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    dump(key, os.path.join(OUT, "key.json"))                # не в page/ - страница его не видит
    url = os.path.relpath(d, os.path.join("art", "objects", "generation")).replace(os.sep, "/")
    print("страница: http://localhost:8778/%s/index.html (%d предметов)" % (url, len(data)))


def read_tsv(path):
    with open(path, encoding=ENC) as f:
        head = f.readline().rstrip("\r\n").split("\t")
        rows = [dict(zip(head, line.rstrip("\r\n").split("\t"))) for line in f if line.strip()]
    for r in rows:
        if r.get("outcome") and r["outcome"] not in OUTCOMES:
            raise SystemExit("%s %s: исход %r вне %s" % (r["asset_id"], r["slot"], r["outcome"], OUTCOMES))
        for c in filter(None, r.get("classes", "").split(",")):
            if c not in CLASSES:
                raise SystemExit("%s %s: класс %r вне набора" % (r["asset_id"], r["slot"], c))
    return rows


def gate(verdicts, groups):
    """verdicts: {asset: {вариант: (исход, set классов)}}; groups: {asset: primary|secondary}.
    Починено (по варианту V) - первичный PIXEL-предмет, у которого V PASS или PARTIAL без PIXEL_STEP_TRACING.
    Новый класс - у V есть, у A того же предмета нет (A судится вслепую рядом, а не по v1)."""
    out = {}
    for v in ("B", "C"):
        fixed, new_geo, new_id, still = [], [], [], []
        for a, vv in verdicts.items():
            if v not in vv or "A" not in vv:
                continue
            o, k = vv[v]
            _oa, ka = vv["A"]
            if groups.get(a) == "primary":
                if o in ("PASS", "PARTIAL") and "PIXEL_STEP_TRACING" not in k:
                    fixed.append(a)
                elif "PIXEL_STEP_TRACING" in k:
                    still.append(a)
            if "MAJOR_GEOMETRY" in k and "MAJOR_GEOMETRY" not in ka:
                new_geo.append(a)
            if "WRONG_IDENTITY" in k and "WRONG_IDENTITY" not in ka:
                new_id.append(a)
        n_prim = sum(1 for a in verdicts if groups.get(a) == "primary" and v in verdicts[a])
        ok = (len(fixed) >= GATE["primary_fixed_min"] and len(new_geo) <= GATE["new_geometry_max"]
              and len(new_id) <= GATE["new_identity_max"])
        out[v] = {"primary_fixed": len(fixed), "primary_n": n_prim, "fixed": sorted(fixed),
                  "still_pixel": sorted(still), "new_major_geometry": sorted(new_geo),
                  "new_wrong_identity": sorted(new_id), "gate": "PASS" if ok else "FAIL"}
    return out


def report(tsv_path):
    key = load(os.path.join(OUT, "key.json"))
    jobs = {j["asset_id"]: j for j in load(os.path.join(OUT, "jobs.json"))}
    groups = {a: j["group"] for a, j in jobs.items()}
    verdicts = {}
    for r in read_tsv(tsv_path):
        if not r.get("outcome"):
            continue
        v = key[r["asset_id"]][r["slot"]]
        verdicts.setdefault(r["asset_id"], {})[v] = (r["outcome"], set(filter(None, r.get("classes", "").split(","))))
    g = gate(verdicts, groups)
    stairs = {r["asset_id"]: r for r in (load(os.path.join(OUT, "stair.json")) or [])}
    lines = ["# STRUCT_GUIDE_V1 - итог пробы", "",
             "Ворота: из 7 первичных PIXEL_STEP_TRACING не меньше %d в PASS/PARTIAL без лесенки; новых "
             "MAJOR_GEOMETRY 0; новых WRONG_IDENTITY 0 (новый - у варианта есть, у A того же предмета нет)."
             % GATE["primary_fixed_min"], ""]
    for v in ("B", "C"):
        x = g[v]
        lines += ["## %s: %s" % (v, x["gate"]), "",
                  "- починено первичных: %d из %d (%s)" % (x["primary_fixed"], x["primary_n"], ", ".join(x["fixed"]) or "-"),
                  "- лесенка осталась: %s" % (", ".join(x["still_pixel"]) or "-"),
                  "- новых MAJOR_GEOMETRY: %s" % (", ".join(x["new_major_geometry"]) or "0"),
                  "- новых WRONG_IDENTITY: %s" % (", ".join(x["new_wrong_identity"]) or "0"), ""]
    lines += ["## По предметам", "", "| предмет | группа | A | B | C | stair A / B / C |", "|---|---|---|---|---|---|"]
    for a in jobs:
        vv = verdicts.get(a, {})
        cell = {v: ("%s %s" % (vv[v][0], ",".join(sorted(vv[v][1])))).strip() if v in vv else "-" for v in "ABC"}
        s = stairs.get(a, {})
        lines.append("| %s | %s | %s | %s | %s | %s / %s / %s |" % (a, groups[a], cell["A"], cell["B"], cell["C"],
                                                                     s.get("A", "-"), s.get("B", "-"), s.get("C", "-")))
    lines.append("")
    with open(os.path.join(OUT, "report.md"), "w", encoding=ENC) as f:
        f.write("\n".join(lines))
    dump({"gate": g, "verdicts": {a: {v: [o, sorted(k)] for v, (o, k) in vv.items()} for a, vv in verdicts.items()}},
         os.path.join(OUT, "report.json"))
    print("\n".join(lines))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    os.chdir(ROOT)
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "stair":
        stair("--v1" in sys.argv)
    elif cmd == "page":
        page()
    elif cmd == "report" and len(sys.argv) > 2:
        report(sys.argv[2])
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
