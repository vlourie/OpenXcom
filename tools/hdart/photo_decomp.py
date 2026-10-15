#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PHOTO acceptance v1 - разложение брака: главный (и второй) класс у каждого FAIL человека, причины по стратам.

Специалист 01.10: ворота v1 не пройдены (человек PASS 8 из 20), класс указан у 3 FAIL из 12. Прежде чем строить
следующий опыт, у каждого FAIL - один главный класс брака из строгого набора; по доминирующему решается, какую
часть PHOTO чинить. Рендер, вырезка, пороги и вердикт v1 не меняются: photo_accept.py заморожен в selection.json,
здесь он только читается.

  page    - страница только с FAIL: оригинал, новый на полу / пурпурном / светлом, описание из промпта, прежние
            классы; главный класс - обязательно, второй - по желанию. TSV внизу.
  report  - decomp.md / decomp.json: главный класс по стратам, доминирующий класс и развилка специалиста.
            Где в decomp TSV строки нет, а в v1 был ровно один класс - берётся он (помечено "из v1").

Слой проверок (DECISIONS 01.10): TECHNICAL QA (подложка, альфа, силуэт, опора, прорези) - машина, её PASS -
TECHNICAL_GATE_PASS, то есть «годен к просмотру человеком», не приёмка; VISUAL QA (опознание, геометрия,
материал, детали, выдумка) - человек.

    py -3.13 tools/hdart/photo_decomp.py page
    py -3.13 tools/hdart/photo_decomp.py report [--decomp <tsv>]
"""
import argparse
import html
import json
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import photo_accept as pa               # noqa: E402

ENC = "utf-8-sig"
# PIXEL_STEP_TRACING - седьмой класс (специалист 01.10, R-160): рендер обводит лесенку силуэта 32x40 вместо
# гладкого контура; край итога на 99-100 % - край модели, вырезка ни при чём
CLASSES = ["WRONG_IDENTITY", "MAJOR_GEOMETRY", "DETAIL_LOSS", "BAD_MATERIAL", "INVENTED_DETAIL", "BAD_ALPHA",
           "PIXEL_STEP_TRACING"]
# структурная группа считается и вместе, сырые классы - отдельно
STRUCTURAL = ["MAJOR_GEOMETRY", "DETAIL_LOSS", "PIXEL_STEP_TRACING", "INVENTED_DETAIL"]
V1_TO = {"IDENTITY": "WRONG_IDENTITY", "GEOMETRY": "MAJOR_GEOMETRY", "DETAIL": "DETAIL_LOSS",
         "MATERIAL": "BAD_MATERIAL", "INVENTION": "INVENTED_DETAIL", "ALPHA": "BAD_ALPHA"}
# развилка специалиста 01.10: доминирующий главный класс -> что строить следующим
FORK = {"WRONG_IDENTITY": "рендер не виноват - чинить смысловой вход (опознание, описание предмета)",
        "MAJOR_GEOMETRY": "кадр 32x40 недостаточен как единственный образец формы - нужна структурная ступень",
        "DETAIL_LOSS": "кадр 32x40 недостаточен как единственный образец деталей - нужна структурная ступень",
        "BAD_MATERIAL": "PHOTO перспективна - лечить формулировку рендера и материал",
        "INVENTED_DETAIL": "модели слишком много свободы - нужен более жёсткий структурный guide",
        "BAD_ALPHA": "вернуться к photo_base (вырезка и альфа)",
        "PIXEL_STEP_TRACING": "кадр 32x40 нельзя подавать единственной правдой о геометрии - структурная ступень "
                              "(чистый guide контура) до PHOTO"}
STRATA = [s for s, _n in pa.STRATA]


def out(*p):
    return os.path.join(pa.OUT, *p)


def fails():
    """FAIL человека в порядке слепой страницы, с её картинками, описанием и прежними классами."""
    with open(out("page", "index.html"), encoding="utf-8") as f:
        m = re.search(r"const DATA = (\[.*?\]);\n", f.read(), re.S)
    data = json.loads(m.group(1))
    human = pa.read_verdicts(out("verdicts_vitali.tsv"))
    jobs = {j["asset_id"]: j for j in pa.load(out("jobs.json"))}
    res = []
    for r in data:
        h = human.get(r["asset"], {})
        if h.get("human") != "FAIL":
            continue
        v1 = [c for c in h.get("fail_class", "").split(",") if c]
        j = jobs[r["asset"]]
        meta = pa.load(out("render", "meta", j["name"] + ".json"))
        prompt = meta["attempts"][meta["final_attempt"]]["prompt"]
        res.append(dict(r, stratum=j["stratum"], v1=v1, v1_new=[V1_TO.get(c, c) for c in v1],
                        prompt=html.escape(prompt)))
    return res


PAGE = """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>PHOTO v1 брак</title>
<style>
:root{--bg:#1b1b1f;--card:#26262c;--fg:#e8e8ea;--mut:#9a9aa3;--acc:#f2c14e;--p:#a3423a;--s:#7a5ab8}
body{background:var(--bg);color:var(--fg);font:14px/1.4 system-ui,sans-serif;margin:0;padding:16px}
h1{font-size:18px;margin:0 0 4px}.mut{color:var(--mut)}
.row{background:var(--card);border-radius:8px;padding:12px;margin:14px 0}
.cols{display:flex;gap:10px;flex-wrap:wrap;align-items:flex-start}
.col{display:flex;flex-direction:column;gap:4px;max-width:100%}
.col img{max-width:100%;border-radius:4px}.col img.px{image-rendering:pixelated}
.t{font-weight:600;color:var(--acc);font-size:12px;margin-top:8px}
button{background:#33333b;color:var(--fg);border:1px solid #44444d;border-radius:4px;padding:3px 8px;cursor:pointer;font-size:12px}
.pri button.on{background:var(--p)}.sec button.on{background:var(--s)}
.btns{display:flex;gap:4px;flex-wrap:wrap;margin-top:4px}
input[type=text]{width:100%;box-sizing:border-box;background:#1f1f24;color:var(--fg);border:1px solid #44444d;border-radius:4px;padding:3px;margin-top:8px}
textarea{width:100%;height:160px;background:#1f1f24;color:var(--fg);box-sizing:border-box}
</style></head><body>
<h1>PHOTO acceptance v1 - почему брак</h1>
<div class="mut">Только ваши FAIL (__N__). Вердикт PASS/FAIL не меняется. <span id="left"></span></div>
<ul class="mut" style="margin:6px 0 0 18px;padding:0">
<li><b>Главный</b> - из-за чего картинку нельзя принять, даже если всё остальное исправить. <b>Второй</b> - сопутствующее, если есть.</li>
<li><b>WRONG_IDENTITY</b> - не тот предмет по смыслу, в том числе когда не тот предмет уже написан в описании промпта.</li>
<li><b>MAJOR_GEOMETRY</b> - неверна крупная конструкция: форма корпуса, число крупных частей, ножки, двери, пропорции, поворот.</li>
<li><b>DETAIL_LOSS</b> - крупная форма верна, но пропали значимые внутренние элементы: полки, кнопки, решётки, ступени, рисунок панели.</li>
<li><b>PIXEL_STEP_TRACING</b> - края кубиками: модель обвела пиксельную лесенку оригинала вместо ровного контура. Может быть главным, даже если опознание тоже не совсем точное, - если картинку нельзя принять именно из-за ступенек.</li>
<li>«Описание верное?» - про текст промпта (строка «описание»), не про картинку. «Промпт задавал детали?» - только для INVENTED_DETAIL: было ли в промпте прямо сказано, какие детали должны быть.</li>
</ul>
<div id="rows"></div>
<h2>TSV</h2><textarea id="tsv" readonly></textarea>
<script>
const DATA = __DATA__;
const CLS = __CLS__;
const KEY = "photo-accept-v1-decomp";
let st = {}; try { st = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) {}
function save(){ try { localStorage.setItem(KEY, JSON.stringify(st)); } catch (e) {} tsv(); }
function tsv(){
  const L = ["asset_id\\tprimary\\tsecondary\\tprompt_ok\\tdetail_constrained\\tnote"];
  let left = 0;
  for (const r of DATA) { const s = st[r.asset] || {};
    const inv = s.p === "INVENTED_DETAIL" || s.s === "INVENTED_DETAIL";
    if (!s.p || !s.q || (inv && !s.d)) left++;
    L.push([r.asset, s.p || "", s.s || "", s.q || "", inv ? (s.d || "") : "",
            (s.n || "").replace(/[\\t\\n]/g, " ")].join("\\t")); }
  document.getElementById("tsv").value = L.join("\\n");
  document.getElementById("left").textContent = left ? "Не дозаполнено: " + left + "." : "Всё размечено.";
}
function pick(box, s, field, v){ s[field] = s[field] === v ? "" : v;
  box.querySelectorAll("button").forEach(x => x.classList.toggle("on", x.dataset.v === s[field])); save(); }
const root = document.getElementById("rows");
DATA.forEach((r, i) => {
  const s = st[r.asset] = st[r.asset] || {};
  for (const k in r.saved) if (!s[k] && r.saved[k]) s[k] = r.saved[k];   // присланное в decomp_vitali.tsv
  const row = document.createElement("div"); row.className = "row";
  row.innerHTML = `<div><b>${i + 1}. ${r.asset}</b></div><div class="mut">описание: ${r.what}</div>` +
    (r.v1.length ? `<div class="mut">в v1 вы отметили: ${r.v1.join(", ")}</div>` : "");
  const cols = document.createElement("div"); cols.className = "cols"; row.appendChild(cols);
  for (const [f, t, px] of r.img) cols.insertAdjacentHTML("beforeend",
    `<div class="col"><div class="t">${t}</div><img class="${px ? "px" : ""}" src="../page/${f}" width="${r.w}" height="${r.h}" loading="lazy"></div>`);
  cols.insertAdjacentHTML("beforeend", `<div class="col"><div class="t">сырой ответ</div><a href="../page/${r.raw}" target="_blank" style="color:var(--acc)">открыть</a></div>`);
  row.insertAdjacentHTML("beforeend", `<details class="mut" style="margin-top:6px"><summary>весь промпт</summary>${r.prompt}</details>`);
  for (const [field, cls, title, opts] of [["p", "pri", "главный класс", CLS], ["s", "sec", "второй (если есть)", CLS],
      ["q", "pri", "описание в промпте верное?", ["YES", "NO"]],
      ["d", "sec", "промпт прямо задавал детали? (только при INVENTED_DETAIL)", ["YES", "NO"]]]) {
    row.insertAdjacentHTML("beforeend", `<div class="t">${title}</div>`);
    const b = document.createElement("div"); b.className = "btns " + cls;
    for (const v of opts) { const e = document.createElement("button"); e.textContent = v; e.dataset.v = v;
      if (s[field] === v) e.classList.add("on"); e.onclick = () => pick(b, s, field, v); b.appendChild(e); }
    row.appendChild(b); }
  const n = document.createElement("input"); n.type = "text"; n.placeholder = "заметка"; n.value = s.n || "";
  n.oninput = () => { s.n = n.value; save(); }; row.appendChild(n);
  root.appendChild(row);
});
tsv();
</script></body></html>"""


def page():
    rows = fails()
    dec = read_decomp(out("decomp_vitali.tsv"))
    for r in rows:
        v = dec.get(r["asset"], {})
        r["saved"] = {"p": v.get("primary", ""), "s": v.get("secondary", ""), "q": v.get("prompt_ok", ""),
                      "d": v.get("detail_constrained", ""), "n": v.get("note", "")}
    d = out("decomp")
    os.makedirs(d, exist_ok=True)
    doc = PAGE.replace("__DATA__", json.dumps(rows, ensure_ascii=False)).replace(
        "__CLS__", json.dumps(CLASSES)).replace("__N__", str(len(rows)))
    with open(os.path.join(d, "index.html"), "w", encoding="utf-8") as f:
        f.write(doc)
    url = os.path.relpath(d, os.path.join("art", "objects", "generation")).replace(os.sep, "/")
    print("страница: http://localhost:8778/%s/index.html (FAIL человека: %d)" % (url, len(rows)))


def read_decomp(path):
    if not os.path.exists(path):
        return {}
    with open(path, encoding=ENC) as f:
        head = f.readline().rstrip("\r\n").split("\t")
        return {r["asset_id"]: r for r in (dict(zip(head, ln.rstrip("\r\n").split("\t"))) for ln in f if ln.strip())}


def decompose(rows, dec):
    """Главный и второй класс каждого FAIL: из decomp TSV; нет строки - единственный класс v1; иначе пусто.
    prompt_ok (описание в промпте верное) и detail_constrained (промпт задавал детали, только при
    INVENTED_DETAIL) - YES / NO / пусто."""
    res = []
    for r in rows:
        d = dec.get(r["asset"], {})
        p, s, src = d.get("primary", ""), d.get("secondary", ""), "decomp"
        if not p and len(r["v1_new"]) == 1:
            p, src = r["v1_new"][0], "из v1"
        if p and p not in CLASSES or s and s not in CLASSES:
            raise SystemExit("%s: класс вне набора (%s / %s)" % (r["asset"], p, s))
        q, dc = d.get("prompt_ok", ""), d.get("detail_constrained", "")
        if q not in ("", "YES", "NO") or dc not in ("", "YES", "NO"):
            raise SystemExit("%s: prompt_ok / detail_constrained - YES или NO (%s / %s)" % (r["asset"], q, dc))
        res.append({"asset_id": r["asset"], "stratum": r["stratum"], "primary": p, "secondary": s,
                    "source": src if p else "", "prompt_ok": q, "detail_constrained": dc,
                    "v1": ",".join(r["v1"]), "note": d.get("note", "")})
    return res


# куда ведёт класс: связаны архитектурно те, что лечатся одной ступенью
STAGE = {"WRONG_IDENTITY": "identity", "MAJOR_GEOMETRY": "structure", "DETAIL_LOSS": "structure",
         "INVENTED_DETAIL": "structure", "PIXEL_STEP_TRACING": "structure", "BAD_MATERIAL": "render",
         "BAD_ALPHA": "photo_base"}


def decide(prim, n):
    """Правило специалиста 01.10: один класс >= 50 % FAIL - опыт против него; два вместе >= 70 % - общий этап,
    только если лечатся одной ступенью; иначе причины размазаны - PHOTO пока слишком нестабильна как база."""
    top = prim.most_common()
    if not top or not n:
        return "NONE", [], "размеченных FAIL нет"
    c1, k1 = top[0]
    if k1 / n >= 0.5 and (len(top) == 1 or top[1][1] < k1):
        return "SINGLE", [c1], "один класс - %d из %d: опыт против %s (%s)" % (k1, n, c1, FORK[c1])
    if len(top) >= 2 and (top[0][1] + top[1][1]) / n >= 0.7:
        c2 = top[1][0]
        if STAGE[c1] == STAGE[c2]:
            return "COMBINED", [c1, c2], "%s + %s - %d из %d, лечатся одной ступенью (%s): один общий этап" % (
                c1, c2, top[0][1] + top[1][1], n, STAGE[c1])
        return "TWO_UNRELATED", [c1, c2], ("%s + %s - %d из %d, но ступени разные (%s / %s): общий этап не "
                                           "делать, решение за специалистом" % (c1, c2, top[0][1] + top[1][1], n,
                                                                               STAGE[c1], STAGE[c2]))
    return "SCATTERED", [c for c, _k in top], ("причины размазаны (самый частый %s - %d из %d): проблема не "
                                               "локальная, PHOTO пока слишком нестабильна как база" % (c1, k1, n))


def cause(r):
    """Откуда брак (по главному классу), специалист 01.10: неверное описание в промпте - UPSTREAM (пришло во
    входе), кроме альфы; альфа - POSTPROCESS; остальное при верном описании - RENDERER (у геометрии, деталей и
    выдумки - рендер или структура); описание не отмечено - ?. Лесенка (PIXEL_STEP_TRACING) - RENDERER при любом
    описании: её даёт вход рендера, а не текст (R-160)."""
    p = r["primary"]
    if not p:
        return "?"
    if p == "BAD_ALPHA":
        return "POSTPROCESS"
    if p == "PIXEL_STEP_TRACING":
        return "RENDERER"
    if r["prompt_ok"] == "NO":
        return "UPSTREAM"
    return "RENDERER" if r["prompt_ok"] == "YES" else "?"


def split(res, cls, field):
    """Для класса (главного или второго): сколько с field YES / NO / не отмечено."""
    rs = [r for r in res if cls in (r["primary"], r["secondary"])]
    return {k: sum(r[field] == v for r in rs) for k, v in (("YES", "YES"), ("NO", "NO"), ("?", ""))}


def report(path):
    res = decompose(fails(), read_decomp(path))
    n = len(res)
    known = [r for r in res if r["primary"]]
    prim = Counter(r["primary"] for r in known)
    sec = Counter(r["secondary"] for r in known if r["secondary"])
    by = {s: Counter(r["primary"] or "?" for r in res if r["stratum"] == s) for s in STRATA}
    ident = split(res, "WRONG_IDENTITY", "prompt_ok")
    invent = split(res, "INVENTED_DETAIL", "detail_constrained")
    causes = Counter(cause(r) for r in res)
    top = prim.most_common()
    top1 = top[0][1] / n if top and n else 0.0
    top2 = sum(k for _c, k in top[:2]) / n if top and n else 0.0
    struct = sum(prim[c] for c in STRUCTURAL)
    complete = len(known) == n and all(r["prompt_ok"] for r in res) and not invent["?"]
    kind, target, why = decide(prim, n) if complete else ("INCOMPLETE", [], "разметка не закончена - решения нет")
    res_json = {"fails": n, "classified": len(known), "complete": complete, "primary": dict(prim),
                "secondary": dict(sec), "by_stratum": {s: dict(c) for s, c in by.items()},
                "wrong_identity_prompt_ok": ident, "invented_detail_constrained": invent,
                "top1_share": round(top1, 3), "top2_share": round(top2, 3), "cause": dict(causes),
                "structural_failure": {"classes": STRUCTURAL, "primary": struct,
                                       "share": round(struct / n, 3) if n else 0.0},
                "decision": {"kind": kind, "target": target, "why": why}, "rows": res}
    with open(out("decomp.json"), "w", encoding=ENC) as f:
        json.dump(res_json, f, ensure_ascii=False, indent=1)
    L = ["# PHOTO acceptance v1 - разложение брака", "",
         "FAIL человека: %d, с главным классом: %d%s." % (n, len(known), "" if complete else
                                                           " - **разметка не закончена**"), "",
         "| класс | главный | второй |", "|---|---|---|"]
    L += ["| %s | %d | %d |" % (c, prim[c], sec[c]) for c in CLASSES]
    L += ["", "| страт (главный) | " + " | ".join(CLASSES + ["?"]) + " |", "|---" * (len(CLASSES) + 2) + "|"]
    L += ["| %s | " % s + " | ".join(str(by[s][c]) for c in CLASSES + ["?"]) + " |" for s in STRATA]
    L += ["", "WRONG_IDENTITY (главный или второй): описание в промпте уже было неверным - %d (чинить опознание), "
              "верным - %d (рендер не послушался), не отмечено - %d." % (ident["NO"], ident["YES"], ident["?"]),
          "INVENTED_DETAIL (главный или второй): промпт задавал детали - %d (выдумка вопреки описанию - нужен "
          "структурный guide), не задавал - %d, не отмечено - %d." % (invent["YES"], invent["NO"], invent["?"]),
          "", "FAIL total = %d; Top1 = %.1f %%; Top2 combined = %.1f %% (порог 50 %% / 70 %%)." % (
              n, 100 * top1, 100 * top2),
          "STRUCTURAL_FAILURE (%s, по главному) = %d из %d, %.1f %%." % (
              " + ".join(STRUCTURAL), struct, n, 100 * struct / n if n else 0.0),
          "Откуда брак (по главному): RENDERER %d, UPSTREAM %d, POSTPROCESS %d, не определено %d." % (
              causes["RENDERER"], causes["UPSTREAM"], causes["POSTPROCESS"], causes["?"]),
          "", "Решение: **%s** - %s." % (kind, why)]
    L += ["", "| предмет | страт | главный | второй | описание верное | детали заданы | откуда | в v1 | заметка |",
          "|---|---|---|---|---|---|---|---|---|"]
    L += ["| %(asset_id)s | %(stratum)s | %(primary)s | %(secondary)s | %(prompt_ok)s | %(detail_constrained)s | "
          "%(source)s | %(v1)s | %(note)s |" % r for r in res]
    with open(out("decomp.md"), "w", encoding=ENC) as f:
        f.write("\n".join(L) + "\n")
    print("\n".join(L))
    return res_json


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("page")
    r = sub.add_parser("report")
    r.add_argument("--decomp", default=out("decomp_vitali.tsv"))
    a = ap.parse_args()
    if a.cmd == "page":
        page()
    else:
        report(a.decomp)


if __name__ == "__main__":
    main()
