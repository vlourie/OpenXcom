"""Проба SIMPLE A/B (30.09, специалист): стоит ли полный Qwen своей цены на ПРОСТЫХ предметах.

Не повод переводить SIMPLE на полный Qwen то, что B выиграл у A на пробе детали: там были
DETAIL_CRITICAL, а цена B - около 90 с на картинку против 20 с у turbo. Чистый вопрос, без C и без
правки промптов:

  A  turbo 6 шагов, cfg 1 - готовые ответы пилота, заново не рисуются
  B  полный Qwen-Image-2.1, 30 шагов, cfg 4, тот же промпт, зерно и вход, что у A

Выборка не руками: SIMPLE_SHAPE пилота в политике (detail_class.collect, с решениями overrides.tsv),
четыре слоя по 4, случайно с закреплённым зерном. Слой по слову опознания, «мелкое» - по площади
силуэта среди того, что не попало в слова; пятна на полу (кровь) не предметы. Что не попало никуда (статуи, колонны, обломки корпусов),
в пробу не идёт - это не вопрос пробы.

    py -3.13 tools/hdart/simple_probe.py make      # выборка, задания B, команда очереди (без видеокарты)
    py -3.13 tools/hdart/simple_probe.py record A|B
    py -3.13 tools/hdart/simple_probe.py page      # страница A против B по критериям
    py -3.13 tools/hdart/simple_probe.py summary [verdicts.tsv]   # свод по TSV страницы
Итог по предмету (специалист): WIN_A / WIN_B / TIE / B_BETTER_BUT_NOT_ENOUGH - на странице «B немного лучше».
Это SIMPLE A/B v1, n=16, exploratory: в мебели случайно 4 стола. Если B заметно лучше - перед сменой режима
v2 на недопредставленных типах (лампы, стулья, крупные гладкие корпуса, одиночные бытовые предметы).
Рисует B одно задание obj_photo.py через gpuq (команду печатает make).
"""
import argparse
import csv
import hashlib
import json
import os
import random
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import numpy as np                                  # noqa: E402

import detail_class as dc                           # noqa: E402
import detail_probe as dp                           # noqa: E402

ENC = "utf-8-sig"
OUT = os.path.join("art", "objects", "generation", "probes", "simple-v1")
SEED = "simple-v1"
PER = 4
# слой по слову опознания, первое совпадение; tank - корпус, а не тара
STRATA = [
    ("technical", r"tank|van|vehicle|fuselage|fin|tail|nose|aircraft|helicopter|engine|generator"),
    ("container", r"crate|box|boxe|barrel|bin|can|kit|tire|chest|sack|bag"),
    ("furniture", r"table|sofa|bed|wardrobe|lamp|toilet|mailbox|chair|bench|cabinet|desk|stool"),
]
SMALL_PX = 250          # площадь силуэта в базовых пикселях (все куски) - «мелкое»
DECAL = r"blood|splatter|stain|puddle"      # пятно на полу - не предмет, вне слоёв
TITLES = {"O": "ORIGINAL x4", "A": "A turbo 6", "B": "B full-Qwen 30"}
# подписи страницы и свода; photo_probe.py подменяет своими
CFG = {"title": "SIMPLE A/B v1 (n=16, exploratory): turbo против полного Qwen",
       "intro": "Простые предметы пилота, выбраны случайно по слоям.",
       "key": "simple_probe_v1", "seed": SEED, "summary": "SIMPLE A/B v1, exploratory",
       "caveat": "Не доказательство для всей категории: в мебели выпали 4 стола.",
       "help": "Итог по предмету - кто лучше и насколько: «немного» - разница есть, но небольшая. По критериям: "
               "лучше = точнее, чище; для размытия и выдумки лучше тот, у кого их меньше.",
       # кнопки итога: 1/2 - сторона, «+» - заметно; tie и прочие - постоянные итоги (fixed)
       "buttons": [["1+", "1 заметно лучше"], ["1", "1 немного лучше"], ["tie", "ничья"],
                   ["2", "2 немного лучше"], ["2+", "2 заметно лучше"]],
       "out": {"A": "WIN_A", "A+": "WIN_A", "B": "B_BETTER_BUT_NOT_ENOUGH", "B+": "WIN_B"},
       "fixed": {"tie": "TIE"},
       "outcomes": ["WIN_A", "WIN_B", "TIE", "B_BETTER_BUT_NOT_ENOUGH"],
       "wins": {"A": ["WIN_A"], "B": ["WIN_B", "B_BETTER_BUT_NOT_ENOUGH"]},
       "wins_note": "wins B = WIN_B + B_BETTER_BUT_NOT_ENOUGH (из них заметно - WIN_B)."}
CRITERIA = ["overall visual quality", "geometry fidelity", "semantic fidelity", "alpha",
            "material quality", "unwanted blur", "invented details"]


def setup():
    dp.OUT = OUT
    dp.MODES = {"B": {"engine": "qwen21", "steps": 30, "cfg": 4.0, "prompt": "pilot"}}
    dp.MODES_ALL = ["A", "B"]
    dp.TITLES = TITLES
    dp.JOB_PREFIX = "simple_probe_"


def stratum(row):
    text = row["identity"].lower()
    if re.search(r"\b(%s)" % DECAL, text):
        return None
    for name, rx in STRATA:
        if re.search(r"\b(%s)(e?s)?\b" % rx, text):
            return name
    area = sum(int((np.asarray(f.convert("RGBA"))[:, :, 3] > 0).sum()) for f in row["frames"])
    return "small" if area < SMALL_PX else None


def select():
    rows, _reg = dc.collect(dp.BATCH)
    pool = [r for r in rows if r["class"] == "SIMPLE_SHAPE" and r["in_policy"]]
    jobs = {j["asset_id"] for j in dp.load(os.path.join(dp.RUN, "batch_jobs.json"))}
    by = {}
    for r in sorted(pool, key=lambda r: r["asset_id"]):
        s = stratum(r)
        if s and r["asset_id"] in jobs:
            by.setdefault(s, []).append(r)
    rnd = random.Random(int(hashlib.sha256(SEED.encode()).hexdigest()[:12], 16))
    pick = []
    for name in ("container", "furniture", "small", "technical"):
        cand = by.get(name, [])
        for r in rnd.sample(cand, min(PER, len(cand))):
            pick.append((name, r, len(cand)))
    return pool, by, pick


def make(py):
    setup()
    pool, by, pick = select()
    print("SIMPLE_SHAPE в политике: %d; по слоям: %s; вне слоёв: %d" % (
        len(pool), ", ".join("%s %d" % (k, len(v)) for k, v in sorted(by.items())),
        len(pool) - sum(len(v) for v in by.values())))
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "selection.tsv"), "w", encoding=ENC, newline="") as f:
        w = csv.writer(f, delimiter="\t", quoting=csv.QUOTE_NONE, escapechar="\\")
        w.writerow(["asset_id", "stratum", "stratum_size", "identity"])
        for name, r, n in pick:
            w.writerow([r["asset_id"], name, n, r["identity"].replace("\t", " ")])
            print("  %-10s %-26s %s" % (name, r["asset_id"], r["identity"][:60]))
    dp.ASSETS = [r["asset_id"] for _n, r, _k in pick]
    dp.make(py)
    probe = dp.load(os.path.join(OUT, "probe.json"))
    probe.update(seed=SEED, strata={r["asset_id"]: n for n, r, _k in pick}, question=__doc__.split("\n")[0])
    dp.dump(probe, os.path.join(OUT, "probe.json"))


PAGE = """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Simple A/B</title>
<style>
:root{--bg:#1b1b1f;--card:#26262c;--fg:#e8e8ea;--mut:#9a9aa3;--acc:#f2c14e;--x:#4a7fc9;--y:#c9962c;--tie:#6a6a73}
body{background:var(--bg);color:var(--fg);font:14px/1.4 system-ui,sans-serif;margin:0;padding:16px}
h1{font-size:18px;margin:0 0 4px}.mut{color:var(--mut)}
.row{background:var(--card);border-radius:8px;padding:12px;margin:14px 0}
.cols{display:flex;gap:10px;flex-wrap:wrap;align-items:flex-start}
.col{display:flex;flex-direction:column;gap:6px;max-width:100%}
.col img{max-width:100%;image-rendering:pixelated;background:#202024;border-radius:4px}
.t{font-weight:600;color:var(--acc)}
table{border-collapse:collapse;margin-top:8px}td{padding:2px 6px}
button{background:#33333b;color:var(--fg);border:1px solid #44444d;border-radius:4px;padding:2px 8px;cursor:pointer;font-size:12px}
button.on[data-v="1"]{background:var(--x)}button.on[data-v="2"]{background:var(--y)}button.on[data-v=tie]{background:var(--tie)}
button.on[data-o^="1"]{background:var(--x)}button.on[data-o^="2"]{background:var(--y)}button.on[data-o=tie]{background:var(--tie)}
button.on[data-o=fail]{background:#a3423a}
.btns{display:flex;gap:4px;flex-wrap:wrap}label{font-size:12px;color:var(--mut);display:block}
input[type=text]{width:100%;box-sizing:border-box;background:#1f1f24;color:var(--fg);border:1px solid #44444d;border-radius:4px;padding:3px}
textarea{width:100%;height:160px;background:#1f1f24;color:var(--fg);box-sizing:border-box}
a{color:var(--acc)}
</style></head><body>
<h1>__TITLE__</h1>
<div class="mut">__INTRO__ Режимы спрятаны: 1 и 2 стоят в
случайном порядке, в TSV уходят настоящие A/B. Под каждой картинкой - hard fail (геометрия, смысл,
альфа, след не тот) и выдуманные детали. __HELP__</div>
<div id="rows"></div>
<h2>TSV</h2><textarea id="tsv" readonly></textarea>
<script>
const DATA = __DATA__;
const CRIT = __CRIT__;
const KEY = "__KEY__";
const CFG = __CFG__;
const OUTCOME = CFG.buttons;
let st = {}; try { st = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) {}
function save(){ try { localStorage.setItem(KEY, JSON.stringify(st)); } catch (e) {} tsv(); }
function real(r, v){ return v === "tie" ? "tie" : (v ? r.order[+v - 1] : ""); }
function outcome(r, v){
  if (!v) return ["", ""];
  if (v in CFG.fixed) return [CFG.fixed[v], ""];
  const m = r.order[+v[0] - 1], big = v.length > 1;
  return [CFG.out[m + (big ? "+" : "")], m + "+" in CFG.out ? (big ? "clear" : "slight") : ""];
}
function tsv(){
  const L = [["asset_id", "stratum", "outcome", "margin", "hard_fail_A", "hard_fail_B", "invented_A", "invented_B"]
             .concat(CRIT, ["note"]).join("\\t")];
  for (const r of DATA) { const s = st[r.asset] || {}; const f = s.f || {};
    L.push([r.asset, r.stratum].concat(outcome(r, s.o), [f["A|hard"] ? 1 : 0, f["B|hard"] ? 1 : 0,
            f["A|inv"] ? 1 : 0, f["B|inv"] ? 1 : 0], CRIT.map(c => real(r, (s.c || {})[c])),
            [(s.n || "").replace(/[\\t\\n]/g, " ")]).join("\\t")); }
  document.getElementById("tsv").value = L.join("\\n");
}
const root = document.getElementById("rows");
for (const r of DATA) {
  const s = st[r.asset] = st[r.asset] || {}; s.c = s.c || {}; s.f = s.f || {};
  const row = document.createElement("div"); row.className = "row";
  row.innerHTML = `<div><b>${r.asset}</b> <span class="mut">${r.stratum} - ${r.what}</span></div>`;
  const cols = document.createElement("div"); cols.className = "cols"; row.appendChild(cols);
  const show = [["O", "ORIGINAL x4"], [r.order[0], "1"], [r.order[1], "2"]];
  for (const [k, t] of show) {
    const c = document.createElement("div"); c.className = "col";
    c.innerHTML = `<div class="t">${t}</div>` + (r.img[k] ? `<img src="${r.img[k]}" width="${r.w}" height="${r.h}" loading="lazy">` : `<div class="mut">нет ответа</div>`)
      + (k !== "O" && r.raw[k] ? `<a href="${r.raw[k]}" target="_blank">сырой ответ</a>` : "");
    if (k !== "O") for (const [fk, ft] of [["hard", "hard fail"], ["inv", "выдуманные детали"]]) {
      const l = document.createElement("label"); const i = document.createElement("input"); i.type = "checkbox";
      const id = k + "|" + fk; i.checked = !!s.f[id]; i.onchange = () => { s.f[id] = i.checked; save(); };
      l.appendChild(i); l.append(" " + ft); c.appendChild(l); }
    cols.appendChild(c);
  }
  const ob = document.createElement("div"); ob.className = "btns";
  for (const [v, t] of OUTCOME) { const e = document.createElement("button"); e.textContent = t; e.dataset.o = v;
    if (s.o === v) e.classList.add("on");
    e.onclick = () => { s.o = s.o === v ? "" : v; ob.querySelectorAll("button").forEach(x => x.classList.toggle("on", x.dataset.o === s.o)); save(); };
    ob.appendChild(e); }
  row.insertAdjacentHTML("beforeend", `<div class="t" style="margin-top:8px">итог</div>`); row.appendChild(ob);
  const tb = document.createElement("table");
  for (const cr of CRIT) {
    const tr = document.createElement("tr"); tr.innerHTML = `<td>${cr}</td>`;
    const td = document.createElement("td");
    for (const [v, t] of [["1", "1 лучше"], ["tie", "ничья"], ["2", "2 лучше"]]) {
      const e = document.createElement("button"); e.textContent = t; e.dataset.v = v;
      if (s.c[cr] === v) e.classList.add("on");
      e.onclick = () => { s.c[cr] = s.c[cr] === v ? "" : v; td.querySelectorAll("button").forEach(x => x.classList.toggle("on", x.dataset.v === s.c[cr])); save(); };
      td.appendChild(e); }
    tr.appendChild(td); tb.appendChild(tr);
  }
  row.appendChild(tb);
  const n = document.createElement("input"); n.type = "text"; n.placeholder = "заметка"; n.value = s.n || "";
  n.oninput = () => { s.n = n.value; save(); }; row.appendChild(n);
  root.appendChild(row);
}
tsv();
</script></body></html>"""


def page():
    setup()
    probe = dp.load(os.path.join(OUT, "probe.json"))
    if probe is None:
        raise SystemExit("нет probe.json - сначала make")
    d = os.path.join(OUT, "page")
    os.makedirs(d, exist_ok=True)
    rnd = random.Random(CFG["seed"] + "-page")
    data = []
    import shutil
    for f in os.listdir(d):
        if f.endswith(".png"):
            os.remove(os.path.join(d, f))
    for a, j, big, raws, size in dp.cells():
        order = ["A", "B"]
        rnd.shuffle(order)
        # имена файлов - по стороне 1/2, сырой ответ копией рядом: ни имя, ни путь не выдают режим
        side = {"O": "O", order[0]: "1", order[1]: "2"}
        img, raw = {}, {}
        for k, im in big.items():
            if im is not None:
                f = "%s_%s.png" % (a.replace(":", "_"), side[k])
                im.save(os.path.join(d, f))
                img[k] = f
        for m, p in raws.items():
            if p:
                f = "%s_%s_raw.png" % (a.replace(":", "_"), side[m])
                shutil.copyfile(p, os.path.join(d, f))
                raw[m] = f
        data.append({"asset": a, "stratum": probe["strata"][a], "what": j["what"], "img": img, "raw": raw,
                     "w": size[0], "h": size[1], "order": order})
    html = PAGE.replace("__DATA__", json.dumps(data, ensure_ascii=False)).replace(
        "__CRIT__", json.dumps(CRITERIA)).replace("__TITLE__", CFG["title"]).replace(
        "__INTRO__", CFG["intro"]).replace("__KEY__", CFG["key"]).replace("__HELP__", CFG["help"]).replace(
        "__CFG__", json.dumps({k: CFG[k] for k in ("buttons", "out", "fixed")}, ensure_ascii=False))
    with open(os.path.join(d, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    url = os.path.relpath(d, os.path.join("art", "objects", "generation")).replace(os.sep, "/")
    print("страница: http://localhost:8778/%s/index.html (%d предметов, B есть у %d)" % (
        url, len(data), sum(1 for x in data if "B" in x["img"])))


EXTRA = ("BOTH_FAIL", "UNRATED")


def summary(path):
    """Свод по TSV страницы (вердикты человека): итоги по предметам, hard fail и выдумка по режимам,
    критерии и слои. Вывод - summary.md рядом; решение по режиму принимает человек, не скрипт."""
    with open(path, encoding=ENC, newline="") as f:
        rows = [{k: (v or "") for k, v in r.items()}          # хвостовые пустые поля в строке могут быть срезаны
                for r in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE)]
    outs = tuple(CFG["outcomes"]) + tuple(e for e in EXTRA if e not in CFG["outcomes"])
    for r in rows:              # без итога: брак обоих - BOTH_FAIL (сравнивать нечего), иначе не оценён
        if not r["outcome"]:
            r["outcome"] = "BOTH_FAIL" if r["hard_fail_A"] == r["hard_fail_B"] == "1" else "UNRATED"
    bad = [r["asset_id"] for r in rows if r["outcome"] not in outs]
    if bad:
        raise SystemExit("итог не из %s: %s" % (outs, bad))
    n = len(rows)

    def cnt(key, val="1"):
        return sum(1 for r in rows if r[key] == val)

    L = ["# %s (n=%d)" % (CFG["summary"], n), "", "Вердикты: %s. %s" % (path, CFG["caveat"]), "",
         "| итог | предметов |", "|---|---|"]
    L += ["| %s | %d |" % (o, cnt("outcome", o)) for o in outs]
    L += ["", "| | A | B |", "|---|---|---|",
          "| wins | %d | %d |" % tuple(sum(cnt("outcome", o) for o in CFG["wins"][m]) for m in "AB"),
          "| ties | %d | %d |" % (cnt("outcome", "TIE"), cnt("outcome", "TIE")),
          "| hard fails | %d | %d |" % (cnt("hard_fail_A"), cnt("hard_fail_B")),
          "| invented details | %d | %d |" % (cnt("invented_A"), cnt("invented_B")),
          "", CFG["wins_note"], "",
          "| критерий | A лучше | B лучше | ничья | не отмечено |", "|---|---|---|---|---|"]
    for c in CRITERIA:
        L.append("| %s | %d | %d | %d | %d |" % (c, cnt(c, "A"), cnt(c, "B"), cnt(c, "tie"), cnt(c, "")))
    L += ["", "| слой | %s |" % " | ".join(outs), "|---" * (len(outs) + 1) + "|"]
    for s in sorted({r["stratum"] for r in rows}):
        sub = [r for r in rows if r["stratum"] == s]
        L.append("| %s | %s |" % (s, " | ".join(str(sum(1 for r in sub if r["outcome"] == o))
                                                for o in outs)))
    L += ["", "| предмет | слой | итог | hard A/B | invented A/B | заметка |", "|---|---|---|---|---|---|"]
    for r in rows:
        L.append("| %s | %s | %s | %s/%s | %s/%s | %s |" % (r["asset_id"], r["stratum"], r["outcome"], r["hard_fail_A"],
                                                           r["hard_fail_B"], r["invented_A"], r["invented_B"], r["note"]))
    out = os.path.join(os.path.dirname(os.path.abspath(path)), "summary.md")      # рядом с вердиктами
    with open(out, "w", encoding=ENC) as f:
        f.write("\n".join(L) + "\n")
    print("\n".join(L))
    print("\nсвод:", out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["make", "record", "page", "summary"])
    ap.add_argument("mode", nargs="?", default="")
    ap.add_argument("--py", default="E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe")
    a = ap.parse_args()
    if a.cmd == "make":
        make(a.py)
    elif a.cmd == "record":
        setup()
        if a.mode not in ("A", "B"):
            raise SystemExit("record A|B")
        return dp.record(a.mode)
    elif a.cmd == "summary":
        summary(a.mode or os.path.join(OUT, "verdicts_vitali.tsv"))
    else:
        page()
    return 0


if __name__ == "__main__":
    sys.exit(main())
