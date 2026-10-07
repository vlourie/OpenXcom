"""SIMPLE_SHAPE против DETAIL_CRITICAL (30.09, решение по пробе детали probes/detail-v1).

Проба показала: Qwen-путь (turbo, полный, полный с промптом восстановления) не восстанавливает внутреннюю
мелкую деталь - 0 PASS из 30. DETAIL_CRITICAL - предметы, где качество определяет внутренняя деталь в
несколько пикселей исходника: плакаты, картины, вывески, надписи; мониторы, клавиатуры, пульты; полки,
стеллажи, витрины; решётки, прорези; всё, где смысл зависит от числа внутренних деталей.

Предложение автоматическое (source AUTO), не правда: два признака.
  слова    - опознание (identity) называет тип из списка DETAIL_CRITICAL;
  контуры - доля резких перепадов яркости (>= 48) между соседями внутри силуэта оригинала: внутренняя
             структура, которую глаз читает как рисунок. Сама по себе DETAIL_CRITICAL не ставит - только
             ведёт предмет без слова в UNSURE (на глаз).
  Доля крошечных одноцветных пятен (tiny_per100) - только столбец: на пилоте она меряет дизеринг фактуры,
  у регрессионных 9.7-74.5, у ящиков и столов то же самое (30.09), классы не делит.
Классы: DETAIL_CRITICAL (слово), SIMPLE_SHAPE (нет слова, контуров ниже порога), UNSURE (нет слова, контуров
выше порога). Контроль: все 10 предметов регрессионного набора обязаны выйти не SIMPLE_SHAPE.

    py -3.13 tools/hdart/detail_class.py pilot-v2-18e401ad31e8     # tsv, лист по классам, сводка
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import numpy as np                                  # noqa: E402
from PIL import Image, ImageDraw                    # noqa: E402

ENC = "utf-8-sig"
GEN = os.path.join("art", "objects", "generation")
REGRESSION = os.path.join(GEN, "regression", "detail_critical_v1.json")
OUT = os.path.join(GEN, "detail_class")
# решения человека поверх AUTO: asset_id, class, source, note (source - кто решил; агент сюда не пишет от себя)
OVERRIDES = os.path.join(OUT, "overrides.tsv")
CLASSES = ("SIMPLE_SHAPE", "DETAIL_CRITICAL", "STRUCTURAL", "UNSURE")
# типы DETAIL_CRITICAL по вердикту специалиста 30.09; слово целиком, мн. число - тем же корнем
WORDS = {
    "picture": r"poster|painting|picture|portrait|canvas|sign|signpost|signboard|label|text|letter|lettering|"
               r"banner|placard|notice|billboard|map|chart|plaque",
    "screen": r"monitor|screen|display|keyboard|keypad|console|terminal|computer|dashboard|control panel|"
              r"instrument|gauge|dial|clock|radio|television|tv",
    "rack": r"shelf|shelves|rack|bookcase|bookshelf|cabinet|drawers?|locker|showcase",
    "grille": r"grille|grill|vent|vents|lattice|grate|grating|mesh|louvre|louver|slats?",
}
TINY = 3            # пятно не больше 3 пикселей - «деталь в несколько пикселей»
EDGE_DL = 48        # перепад яркости соседей, который глаз читает как контур
PIX_EDGE = 0.20     # доля резких соседств внутри силуэта - выше порога без слова ведёт в UNSURE


def load(path):
    with open(path, encoding=ENC) as f:
        return json.load(f)


def words(text):
    t = (text or "").lower()
    hit = []
    for kind, rx in WORDS.items():
        m = re.search(r"\b(%s)(e?s)?\b" % rx, t)
        if m:
            hit.append("%s:%s" % (kind, m.group(1)))
    return hit


def pixel_numbers(frames):
    """frames - RGBA кадры k=1. Нутро = силуэт без одного пикселя края."""
    tiny = inner = edges = pairs = 0
    for im in frames:
        a = np.asarray(im.convert("RGBA"))
        m = a[..., 3] > 0
        core = m.copy()
        core[1:] &= m[:-1]; core[:-1] &= m[1:]; core[:, 1:] &= m[:, :-1]; core[:, :-1] &= m[:, 1:]
        inner += int(core.sum())
        lum = a[..., :3].astype(np.int32) @ np.array([299, 587, 114]) // 1000
        for d in ((0, 1), (1, 0)):
            both = core[: core.shape[0] - d[0], : core.shape[1] - d[1]] & core[d[0]:, d[1]:]
            dl = np.abs(lum[: lum.shape[0] - d[0], : lum.shape[1] - d[1]] - lum[d[0]:, d[1]:])
            pairs += int(both.sum())
            edges += int((both & (dl >= EDGE_DL)).sum())
        # одноцветные 4-связные пятна, целиком в нутре
        col = (a[..., 0].astype(np.int64) << 16) | (a[..., 1].astype(np.int64) << 8) | a[..., 2]
        seen = np.zeros_like(m)
        H, W = m.shape
        for y in range(H):
            for x in range(W):
                if not m[y, x] or seen[y, x]:
                    continue
                c, stack, comp, inside = col[y, x], [(y, x)], 0, True
                seen[y, x] = True
                while stack:
                    cy, cx = stack.pop()
                    comp += 1
                    inside &= bool(core[cy, cx])
                    for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                        if 0 <= ny < H and 0 <= nx < W and m[ny, nx] and not seen[ny, nx] and col[ny, nx] == c:
                            seen[ny, nx] = True
                            stack.append((ny, nx))
                if comp <= TINY and inside:
                    tiny += 1
    return {"inner_px": inner, "tiny_per100": round(100.0 * tiny / max(1, inner), 2),
            "edge_share": round(edges / max(1, pairs), 3)}


def classify(hit, px):
    busy = px["edge_share"] >= PIX_EDGE
    if hit:
        return "DETAIL_CRITICAL", "слово " + ",".join(hit) + ("; пиксели тоже" if busy else "")
    if busy:
        return "UNSURE", "слова нет, резких контуров внутри %.2f" % px["edge_share"]
    return "SIMPLE_SHAPE", "слова нет, резких контуров внутри %.2f" % px["edge_share"]


def read_overrides(path=OVERRIDES):
    out = {}
    if not os.path.exists(path):
        return out
    import csv
    with open(path, encoding=ENC, newline="") as f:
        for r in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
            if r["class"] not in CLASSES:
                raise SystemExit("%s: класс %r не из %s" % (r["asset_id"], r["class"], CLASSES))
            if not (r.get("source") or "").strip():
                raise SystemExit("%s: решение без source" % r["asset_id"])
            out[r["asset_id"]] = r
    return out


def collect(batch_id):
    """Строки классификации партии: AUTO по признакам, поверх - решения человека из overrides.tsv."""
    import map_mockup as mm
    import pilot_batch as pb
    snap = load(os.path.join(GEN, "batches", batch_id + ".json"))
    reg = {r["asset_id"] for r in load(REGRESSION)["assets"]} if os.path.exists(REGRESSION) else set()
    questions = pb.open_questions(load(pb.FAMS))
    over = read_overrides()
    world = mm.World()
    rows = []
    for a in snap["assets"]:
        aid = a["asset_id"]
        text = a["identity"]["text"]
        frames = []
        for key in a["canonical"]["pieces"]:
            s, f = key.rsplit(":", 1)
            frames.append(world.sprite(s.lower(), int(f), None))
        px = pixel_numbers(frames)
        auto, why = classify(words(text), px)
        cls, src = auto, "AUTO"
        if aid in over:
            cls, src, why = over[aid]["class"], over[aid]["source"], "%s (AUTO: %s)" % (over[aid]["note"], why)
        fam = (a.get("family") or {}).get("id") or ""
        rows.append({"asset_id": aid, "class": cls, "auto_class": auto, "source": src, "why": why, "identity": text,
                     "in_policy": not (aid.upper() in questions or fam.upper() in questions),
                     "regression": aid in reg, **px, "frames": frames, "pieces": a["canonical"]["pieces"]})
    stray = sorted(set(over) - {r["asset_id"] for r in rows})
    if stray:
        print("решения не из этой партии (пропущены): %s" % ", ".join(stray))
    return rows, reg


def run(batch_id):
    rows, reg = collect(batch_id)
    bad = [r["asset_id"] for r in rows if r["regression"] and r["class"] == "SIMPLE_SHAPE"]
    os.makedirs(OUT, exist_ok=True)
    cols = ["asset_id", "class", "auto_class", "source", "in_policy", "regression", "tiny_per100", "edge_share",
            "inner_px", "identity", "why"]
    with open(os.path.join(OUT, batch_id + ".tsv"), "w", encoding=ENC, newline="") as f:
        f.write("\t".join(cols) + "\n")
        for r in sorted(rows, key=lambda r: (r["class"], r["asset_id"])):
            f.write("\t".join(str(r[c]) for c in cols) + "\n")
    sheet(rows, os.path.join(OUT, batch_id + "_sheet.png"))
    human = sum(r["source"] != "AUTO" for r in rows)
    L = ["# SIMPLE_SHAPE / DETAIL_CRITICAL: %s" % batch_id, "",
         "AUTO: DETAIL_CRITICAL - по слову опознания; без слова UNSURE при доле резких контуров внутри >= %.2f. "
         "Поверх - решения человека из overrides.tsv: %d." % (PIX_EDGE, human), "",
         "| класс | все | в политике |", "|---|---|---|"]
    for c in CLASSES:
        n = sum(r["class"] == c for r in rows)
        if n or c != "STRUCTURAL":
            L.append("| %s | %d | %d |" % (c, n, sum(r["class"] == c and r["in_policy"] for r in rows)))
    L += ["", "Регрессионный набор (%d): SIMPLE_SHAPE у %s" % (len(reg), bad or "ни одного - контроль пройден")]
    with open(os.path.join(OUT, batch_id + ".md"), "w", encoding=ENC) as f:
        f.write("\n".join(L) + "\n")
    print("\n".join(L))
    if bad:
        raise SystemExit("регрессионный набор ушёл в SIMPLE_SHAPE: %s - классификатор не годится" % bad)


PAGE = """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Класс предмета</title>
<style>
:root{--bg:#1b1b1f;--card:#26262c;--fg:#e8e8ea;--mut:#9a9aa3;--acc:#f2c14e;--s:#3fa55b;--d:#c94a4a;--st:#4a7fc9;--u:#77777f}
body{background:var(--bg);color:var(--fg);font:14px/1.4 system-ui,sans-serif;margin:0;padding:16px}
h1{font-size:18px;margin:0 0 4px}.mut{color:var(--mut)}
.row{background:var(--card);border-radius:8px;padding:12px;margin:14px 0}
.pics{display:flex;gap:10px;flex-wrap:wrap;align-items:flex-start;margin:8px 0}
.pics img{max-width:100%;image-rendering:pixelated;background:#202024;border-radius:4px}
.pics img.ctx{image-rendering:auto;max-height:360px}
.btns{display:flex;gap:4px;flex-wrap:wrap}
button{background:#33333b;color:var(--fg);border:1px solid #44444d;border-radius:4px;padding:4px 9px;cursor:pointer}
button.on[data-v=SIMPLE_SHAPE]{background:var(--s)}button.on[data-v=DETAIL_CRITICAL]{background:var(--d)}
button.on[data-v=STRUCTURAL]{background:var(--st)}button.on[data-v=UNSURE]{background:var(--u)}
input[type=text]{width:100%;box-sizing:border-box;background:#1f1f24;color:var(--fg);border:1px solid #44444d;border-radius:4px;padding:4px;margin-top:6px}
textarea{width:100%;height:160px;background:#1f1f24;color:var(--fg);box-sizing:border-box}
</style></head><body>
<h1>Класс предмета: SIMPLE_SHAPE или DETAIL_CRITICAL</h1>
<div class="mut">DETAIL_CRITICAL - качество решает внутренняя деталь в несколько пикселей: постер, надпись, экран,
клавиатура, пульт, полки, стеллаж, витрина, решётка, прорези, смысл в числе деталей. SIMPLE_SHAPE - форма и
материал без такой детали. STRUCTURAL - модульная геометрия (рейки, каркас), UNSURE - не понимаю, что это.
Слева оригинал x6, дальше лист опознания и вырез карты пилота (там HD - только для контекста).</div>
<div id="rows"></div>
<h2>TSV (в overrides.tsv)</h2><textarea id="tsv" readonly></textarea>
<script>
const DATA = __DATA__;
const KEY = "__KEY__";
const V = ["SIMPLE_SHAPE","DETAIL_CRITICAL","STRUCTURAL","UNSURE"];
let st = {}; try { st = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) {}
function save(){ try { localStorage.setItem(KEY, JSON.stringify(st)); } catch (e) {} tsv(); }
function tsv(){
  const L = ["asset_id\\tclass\\tsource\\tnote"];
  for (const r of DATA) { const s = st[r.asset] || {}; if (s.v)
    L.push([r.asset, s.v, "HUMAN Vitali " + new Date().toISOString().slice(0,10), (s.n || "").replace(/[\\t\\n]/g, " ")].join("\\t")); }
  document.getElementById("tsv").value = L.join("\\n");
}
const root = document.getElementById("rows");
for (const r of DATA) {
  const s = st[r.asset] = st[r.asset] || {};
  const row = document.createElement("div"); row.className = "row";
  row.innerHTML = `<div><b>${r.asset}</b> - <span>${r.identity}</span> <span class="mut">(${r.why})</span></div>`;
  const pics = document.createElement("div"); pics.className = "pics";
  for (const p of r.orig) pics.insertAdjacentHTML("beforeend", `<img src="${p}" loading="lazy">`);
  for (const p of r.ctx) pics.insertAdjacentHTML("beforeend", `<img class="ctx" src="${p}" loading="lazy">`);
  row.appendChild(pics);
  const b = document.createElement("div"); b.className = "btns";
  for (const v of V) { const e = document.createElement("button"); e.textContent = v; e.dataset.v = v;
    if (s.v === v) e.classList.add("on");
    e.onclick = () => { s.v = s.v === v ? "" : v; b.querySelectorAll("button").forEach(x => x.classList.toggle("on", x.dataset.v === s.v)); save(); };
    b.appendChild(e); }
  row.appendChild(b);
  const n = document.createElement("input"); n.type = "text"; n.placeholder = "что это (если понятно)"; n.value = s.n || "";
  n.oninput = () => { s.n = n.value; save(); }; row.appendChild(n);
  root.appendChild(row);
}
tsv();
</script></body></html>"""


def page(batch_id, cls="UNSURE"):
    """Лист решений для класса (по умолчанию UNSURE): detail_class/<cls>/index.html, отдаётся http.server из
    art/objects/generation (launch.json: detail-probe, порт 8778). Выход - TSV в формате overrides.tsv."""
    rows, _reg = collect(batch_id)
    rep = {a["asset_id"]: a for a in load(os.path.join(GEN, "runs", batch_id, "report", "report.json"))["assets"]}
    d = os.path.join(OUT, cls.lower())
    os.makedirs(d, exist_ok=True)
    data = []
    for r in sorted((r for r in rows if r["class"] == cls), key=lambda r: r["asset_id"]):
        orig = []
        for key, fr in zip(r["pieces"], r["frames"]):
            f = "%s_x6.png" % key.replace(":", "_")
            fr.resize((fr.width * 6, fr.height * 6), Image.NEAREST).save(os.path.join(d, f))
            orig.append(f)
        sh = rep.get(r["asset_id"], {}).get("sheets", {})
        ctx = [os.path.relpath(p, d).replace(os.sep, "/") for k, p in sorted(sh.items())
               if (k == "identity" or k.startswith("map_")) and os.path.exists(p)]
        data.append({"asset": r["asset_id"], "identity": r["identity"], "why": r["why"], "orig": orig, "ctx": ctx})
    html = PAGE.replace("__DATA__", json.dumps(data, ensure_ascii=False)).replace(
        "__KEY__", "detail_class_%s_%s" % (batch_id, cls))
    with open(os.path.join(d, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    print("%s: %d предметов -> http://localhost:8778/detail_class/%s/index.html" % (cls, len(data), cls.lower()))


def sheet(rows, path):
    """Лист по классам: оригинал x3 NEAREST, подпись, у регрессионных - рамка."""
    cw, ch = 32 * 3 + 8, 40 * 3 + 30
    order = [c for c in ("DETAIL_CRITICAL", "STRUCTURAL", "UNSURE", "SIMPLE_SHAPE")
             if c != "STRUCTURAL" or any(r["class"] == c for r in rows)]
    per = 12
    blocks = []
    for c in order:
        rs = sorted([r for r in rows if r["class"] == c], key=lambda r: r["asset_id"])
        n = max(1, -(-len(rs) // per))
        im = Image.new("RGB", (per * cw, 24 + n * ch), (30, 30, 34))
        d = ImageDraw.Draw(im)
        d.text((6, 6), "%s: %d" % (c, len(rs)), fill=(255, 220, 90))
        for i, r in enumerate(rs):
            x, y = (i % per) * cw, 24 + (i // per) * ch
            fr = r["frames"][0].convert("RGBA").resize((96, 120), Image.NEAREST)
            im.paste(fr, (x + 4, y + 2), fr)
            if r["regression"]:
                d.rectangle((x + 2, y, x + cw - 4, y + 124), outline=(240, 80, 80))
            d.text((x + 4, y + 124), r["asset_id"][:17], fill=(200, 200, 200) if r["in_policy"] else (150, 120, 120))
        blocks.append(im)
    out = Image.new("RGB", (per * cw, sum(b.height for b in blocks)), (30, 30, 34))
    y = 0
    for b in blocks:
        out.paste(b, (0, y))
        y += b.height
    out.save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("batch_id")
    ap.add_argument("--page", metavar="CLASS", help="лист решений для класса (UNSURE) вместо классификации")
    a = ap.parse_args()
    if a.page:
        page(a.batch_id, a.page)
    else:
        run(a.batch_id)


if __name__ == "__main__":
    main()
