"""Проба восстановления детали (30.09, вердикт по пилоту pilot-v2-18e401ad31e8: BLURRED_UPSCALE_FAIL).

Те же задания пилота (место на карте, what, зерно), три режима - смотреть глазами ТОЛЬКО на
DETAIL_RECONSTRUCTION: внутренние формы перерисованы, ступени пикселей не просто размазаны, мелкие
функциональные детали стали настоящими элементами, экран/постер/надпись - новый HD-элемент.

  A  turbo 6 шагов, cfg 1 - готовые ответы пилота, заново не рисуются
  B  полный Qwen-Image-2.1, 30 шагов, cfg 4 (негатив действует, R-040), промпт пилота как есть
  C  как B, промпт с просьбой восстановить внутреннюю деталь, а не увеличивать пиксели

B лучше A заметно - виноват turbo. B и C тоже мажут - виновата схема (оригинал главной опорой),
нужна структурная и смысловая подготовка.

    py -3.13 tools/hdart/detail_probe.py make        # задания B и C, probe.json (без видеокарты)
    py -3.13 tools/hdart/detail_probe.py sheet       # лист оригинал | A | B | C (без видеокарты)
Рисуют B и C два задания obj_photo.py через gpuq (команды печатает make).
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from PIL import Image                               # noqa: E402

ENC = "utf-8-sig"
BATCH = "pilot-v2-18e401ad31e8"
RUN = os.path.join("art", "objects", "generation", "runs", BATCH)
OUT = os.path.join("art", "objects", "generation", "probes", "detail-v1")
# 10 самых явных размытых из пилота: 6 панелей (постер, картина, вывеска) и 4 корпуса с мелкой деталью
ASSETS = ["TAVERN:18", "TAVERN:21", "MANSION_PAINTINGS:9", "CARGO1:70", "HANGAR2_SCI:51", "MADDECOR:78",
          "COMPUTERS:15", "FREIGHTER_COMMAND_2:59", "AVENGER_EDIT:30", "CATACDECOR:9"]
MODES = {
    "B": {"engine": "qwen21", "steps": 30, "cfg": 4.0, "prompt": "pilot"},
    "C": {"engine": "qwen21", "steps": 30, "cfg": 4.0, "prompt": "reconstruct"},
}
# промпт пилота: "Keep the position, the size and the silhouette of <image1>. Preserve the exact number..."
OLD_KEEP = "Keep the position, the size and the silhouette of <image1>."
NEW_KEEP = (
    "<image1> is a tiny low-resolution game sprite: use it only as a guide for the silhouette, position, "
    "size, main parts and colours. Do not upscale, trace or smooth its pixels. Reconstruct every internal "
    "detail as a new sharp high-resolution element: screens, displays, buttons, keys, vents, grilles, "
    "shelves, labels, letters, printed pictures and painted images must be redrawn as real crisp objects "
    "with clean edges and fine detail, never as blurred colour patches or soft blobs. "
    "Keep the position, the size and the silhouette of <image1>.")


def load(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding=ENC) as f:
        return json.load(f)


def dump(obj, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding=ENC) as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def make(py):
    jobs = load(os.path.join(RUN, "batch_jobs.json"))
    by = {j["asset_id"]: j for j in jobs}
    miss = [a for a in ASSETS if a not in by]
    if miss:
        raise SystemExit("нет в партии %s: %s" % (BATCH, miss))
    probe = {"batch_id": BATCH, "assets": ASSETS, "modes": {"A": {"engine": "turbo", "steps": 6, "cfg": 1.0,
                                                                  "prompt": "pilot", "out": os.path.join(RUN, "photo")}}}
    for m, cfg in MODES.items():
        out = []
        for a in ASSETS:
            j = {k: v for k, v in by[a].items() if k != "batch_id"}      # не партия: --batch только turbo
            if cfg["prompt"] == "reconstruct":
                if OLD_KEEP not in j["prompt"]:
                    raise SystemExit("%s: в промпте пилота нет фразы, которую меняет C" % a)
                j["prompt"] = j["prompt"].replace(OLD_KEEP, NEW_KEEP)
            out.append(j)
        d = os.path.join(OUT, m)
        dump(out, os.path.join(OUT, "jobs_%s.json" % m))
        probe["modes"][m] = dict(cfg, out=os.path.join(d, "photo"))
        print("%s: %d заданий, зёрна %s" % (m, len(out), ",".join(str(j["seed"]) for j in out)))
    probe["prompt_C_keep"] = NEW_KEEP
    dump(probe, os.path.join(OUT, "probe.json"))
    for m, cfg in MODES.items():
        print("\n# %s" % m)
        print("%s tools/hdart/obj_photo.py --jobs %s --out %s --engine %s --rgba --mp 2.0 --steps %d --cfg %.1f" % (
            py, os.path.join(OUT, "jobs_%s.json" % m).replace("\\", "/"),
            probe["modes"][m]["out"].replace("\\", "/"), cfg["engine"], cfg["steps"], cfg["cfg"]))


def sha(path, n=None):
    import hashlib
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        h = hashlib.sha256(f.read()).hexdigest()
    return h[:n] if n else h


def text_rev(s):
    import hashlib
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]


JOB_PREFIX = "detail_probe_"        # имя задания gpuq без режима; simple_probe.py ставит своё


def record(mode):
    """Запись прогона detail_probe_<mode>: задание очереди, замок, prompt_rev, зерно, хэши raw и итога.
    A - ответы пилота (запись прогона партии - runs/<id>/execution.json), здесь только их хэши."""
    probe = load(os.path.join(OUT, "probe.json"))
    m = probe["modes"][mode]
    if mode == "A":
        jobs = [j for j in load(os.path.join(RUN, "batch_jobs.json")) if j["asset_id"] in probe["assets"]]
        run = {"execution": os.path.join(RUN, "execution.json"), "batch_id": BATCH}
    else:
        jobs = load(os.path.join(OUT, "jobs_%s.json" % mode))
        q = load(os.path.join(".gpuq", "queue.json"))
        mine = [j for j in q["jobs"].values() if j["name"] == JOB_PREFIX + mode]
        if not mine:
            raise SystemExit("в очереди нет %s%s" % (JOB_PREFIX, mode))
        g = max(mine, key=lambda j: int(j["id"]))
        log = os.path.join(".gpuq", "logs", "%s.log" % g["id"])
        lock_line = ""
        if os.path.exists(log):
            with open(log, encoding="utf-8", errors="replace") as f:
                lock_line = next((l.strip() for l in f if l.startswith("замок модели")), "")
        run = {"gpuq_job": g["id"], "state": g.get("state"), "code": g.get("code"), "started": g.get("started"),
               "finished": g.get("finished"), "cmd": g["cmd"], "log": log, "lock_line_in_log": lock_line,
               "jobs_file_sha256": sha(os.path.join(OUT, "jobs_%s.json" % mode))}
    lock = os.path.join("art", "models", "qwen21_turbo_rgba.lock.json")
    rows = []
    for j in jobs:
        rel = j["expected_outputs"][0]
        rows.append({"name": j["name"], "asset_id": j["asset_id"], "seed": j["seed"],
                     "prompt_rev": text_rev(j["prompt"]),
                     "raw_sha256": sha(os.path.join(m["out"], "raw", j["name"] + ".png")),
                     "final_sha256": sha(os.path.join(m["out"], rel)), "final": rel})
    rec = dict(mode=mode, engine=m["engine"], steps=m["steps"], cfg=m["cfg"], mp=2.0, prompt=m["prompt"],
               out=m["out"], model_lock=lock, model_lock_sha256=sha(lock), run=run, jobs=rows)
    miss = [r["name"] for r in rows if not r["raw_sha256"] or not r["final_sha256"]]
    rec["missing"] = miss
    dump(rec, os.path.join(OUT, "execution_%s.json" % mode))
    print("%s: %d заданий, нет ответа %d, замок %s" % (mode, len(rows), len(miss), rec["model_lock_sha256"][:12]))
    # перекрёстная сверка: у разных режимов не может быть одинаковых ответов, у B и A/C - одного prompt_rev с C
    others = {}
    for o in ("A", "B", "C"):
        p = os.path.join(OUT, "execution_%s.json" % o)
        if o != mode and os.path.exists(p):
            others[o] = load(p)
    for o, r in others.items():
        theirs = {y["asset_id"]: y["raw_sha256"] for y in r["jobs"]}
        same = [x["name"] for x in rows if x["raw_sha256"] and x["raw_sha256"] == theirs.get(x["asset_id"])]
        if same:
            raise SystemExit("ОДИНАКОВЫЕ ответы %s и %s: %s - режимы перепутаны" % (mode, o, same))
    return 0


def crop_box(ims):
    box = None
    for im in ims:
        b = im.split()[3].getbbox()
        if b:
            box = b if box is None else (min(box[0], b[0]), min(box[1], b[1]), max(box[2], b[2]), max(box[3], b[3]))
    return box


MODES_ALL = ["A", "B", "C"]
TITLES = {"O": "ORIGINAL x4", "A": "A turbo 6", "B": "B full-Qwen 30", "C": "C full-Qwen reconstruct"}


def cells():
    """По каждому предмету: общая рамка по всем столбцам, крупные вырезы (NEAREST - без своего сглаживания,
    иначе лист сам размоет то, что оценивается) и сырые ответы моделей."""
    import map_mockup as mm
    import tile_qa as tq
    probe = load(os.path.join(OUT, "probe.json"))
    if probe is None:
        raise SystemExit("нет probe.json - сначала make")
    jobs = {j["asset_id"]: j for j in load(os.path.join(RUN, "batch_jobs.json"))}
    world = mm.World()
    for a in probe["assets"]:
        j = jobs[a]
        key = j["take"][0].split("@")[0]
        rel = j["expected_outputs"][0]
        col = {"O": tq.orig_x4(world, key)}
        raws = {}
        for m in MODES_ALL:
            base = probe["modes"][m]["out"]
            p = os.path.join(base, rel)
            col[m] = tq.load_hd(p) if os.path.exists(p) else None
            rp = os.path.join(base, "raw", j["name"] + ".png")
            raws[m] = rp if os.path.exists(rp) else None
        box = crop_box([c for c in col.values() if c is not None]) or (0, 0, 128, 160)
        box = (max(0, box[0] - 4), max(0, box[1] - 4), min(128, box[2] + 4), min(160, box[3] + 4))
        z = max(2, min(4, 420 // max(box[2] - box[0], box[3] - box[1])))
        size = ((box[2] - box[0]) * z, (box[3] - box[1]) * z)
        big = {k: (c.crop(box).resize(size, Image.NEAREST) if c is not None else None) for k, c in col.items()}
        yield a, j, big, raws, size


def sheet():
    import tile_qa as tq
    rows = []
    for a, _j, big, raws, size in cells():
        blank = Image.new("RGBA", size, (0, 0, 0, 0))
        rows.append(tq.side([tq.label(big[k] or blank, ("%s  %s" % (a, TITLES[k])) if k == "O" else
                                      TITLES[k] + ("" if big[k] is not None else "  - нет"))
                             for k in ["O"] + MODES_ALL]))
        h = size[1]
        rr = []
        for m in MODES_ALL:
            if raws[m]:
                r = Image.open(raws[m]).convert("RGBA")
                rr.append(tq.label(r.resize((max(1, round(r.width * h / r.height)), h), Image.LANCZOS),
                                   "%s сырой ответ" % m))
        if rr:
            rows.append(tq.side(rr))
    W = max(r.width for r in rows)
    out = Image.new("RGBA", (W, sum(r.height + 16 for r in rows)), tq.BG)
    y = 0
    for r in rows:
        out.alpha_composite(r, (0, y))
        y += r.height + 16
    p = tq.save(out, os.path.join(OUT, "detail_sheet.png"))
    print("лист:", p)


PAGE = """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Detail probe</title>
<style>
:root{--bg:#1b1b1f;--card:#26262c;--fg:#e8e8ea;--mut:#9a9aa3;--acc:#f2c14e;--ok:#3fa55b;--part:#c9962c;--bad:#c94a4a;--inv:#8a5cc9}
body{background:var(--bg);color:var(--fg);font:14px/1.4 system-ui,sans-serif;margin:0;padding:16px}
h1{font-size:18px;margin:0 0 4px}.mut{color:var(--mut)}
.row{background:var(--card);border-radius:8px;padding:12px;margin:14px 0}
.cols{display:flex;gap:10px;flex-wrap:wrap;align-items:flex-start}
.col{display:flex;flex-direction:column;gap:6px;max-width:100%}
.col img{max-width:100%;image-rendering:pixelated;background:#202024;border-radius:4px}
.t{font-weight:600;color:var(--acc)}
.btns{display:flex;gap:4px;flex-wrap:wrap}
button{background:#33333b;color:var(--fg);border:1px solid #44444d;border-radius:4px;padding:3px 7px;cursor:pointer;font-size:12px}
button.on[data-v=PASS]{background:var(--ok)}button.on[data-v=PARTIAL]{background:var(--part)}
button.on[data-v=FAIL]{background:var(--bad)}button.on[data-v=RECONSTRUCTED_BUT_INVENTED]{background:var(--inv)}
label{font-size:12px;color:var(--mut);display:block}
input[type=text]{width:100%;box-sizing:border-box;background:#1f1f24;color:var(--fg);border:1px solid #44444d;border-radius:4px;padding:3px}
textarea{width:100%;height:160px;background:#1f1f24;color:var(--fg);box-sizing:border-box}
a{color:var(--acc)}
</style></head><body>
<h1>Detail probe: DETAIL_RECONSTRUCTION</h1>
<div class="mut">Оценивается только восстановление внутренней детали, не «что красивее». Отметь, какие критерии НЕ выполнены:
1 internal structure, 2 semantic detail, 3 edge/detail sharpness, 4 fidelity (не изобретает новую конструкцию).
Новый, но не тот плакат/экран - RECONSTRUCTED_BUT_INVENTED.</div>
<div id="rows"></div>
<h2>TSV</h2><textarea id="tsv" readonly></textarea>
<script>
const DATA = __DATA__;
const KEY = "detail_probe_v1";
const CRIT = ["1 structure","2 semantic","3 sharpness","4 fidelity"];
const VERD = ["PASS","PARTIAL","FAIL","RECONSTRUCTED_BUT_INVENTED"];
let st = {}; try { st = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) {}
function save(){ try { localStorage.setItem(KEY, JSON.stringify(st)); } catch (e) {} tsv(); }
function tsv(){
  const L = ["asset_id\\tmode\\tverdict\\tfailed_criteria\\tnote"];
  for (const r of DATA) for (const m of ["A","B","C"]) {
    const s = st[r.asset + "|" + m] || {};
    L.push([r.asset, m, s.v || "", (s.c || []).join(","), (s.n || "").replace(/[\\t\\n]/g, " ")].join("\\t"));
  }
  document.getElementById("tsv").value = L.join("\\n");
}
const root = document.getElementById("rows");
for (const r of DATA) {
  const row = document.createElement("div"); row.className = "row";
  row.innerHTML = `<div><b>${r.asset}</b> <span class="mut">${r.what}</span></div>`;
  const cols = document.createElement("div"); cols.className = "cols"; row.appendChild(cols);
  for (const k of ["O","A","B","C"]) {
    const c = document.createElement("div"); c.className = "col";
    c.innerHTML = `<div class="t">${r.titles[k]}</div>` + (r.img[k] ? `<img src="${r.img[k]}" width="${r.w}" height="${r.h}" loading="lazy">` : `<div class="mut">нет ответа</div>`)
      + (r.raw[k] ? `<a href="${r.raw[k]}" target="_blank">сырой ответ</a>` : "");
    if (k !== "O") {
      const id = r.asset + "|" + k; const s = st[id] = st[id] || {};
      const b = document.createElement("div"); b.className = "btns";
      for (const v of VERD) { const e = document.createElement("button"); e.textContent = v; e.dataset.v = v;
        if (s.v === v) e.classList.add("on");
        e.onclick = () => { s.v = s.v === v ? "" : v; b.querySelectorAll("button").forEach(x => x.classList.toggle("on", x.dataset.v === s.v)); save(); };
        b.appendChild(e); }
      c.appendChild(b);
      for (const cr of CRIT) { const l = document.createElement("label"); const i = document.createElement("input"); i.type = "checkbox";
        i.checked = (s.c || []).includes(cr); i.onchange = () => { s.c = (s.c || []).filter(x => x !== cr); if (i.checked) s.c.push(cr); save(); };
        l.appendChild(i); l.append(" не выполнен: " + cr); c.appendChild(l); }
      const n = document.createElement("input"); n.type = "text"; n.placeholder = "заметка"; n.value = s.n || "";
      n.oninput = () => { s.n = n.value; save(); }; c.appendChild(n);
    }
    cols.appendChild(c);
  }
  root.appendChild(row);
}
tsv();
</script></body></html>"""


def page():
    """Страница вердиктов: probes/detail-v1/page/index.html, картинки рядом, сырые ответы ссылками.
    Отдаётся http.server из art/objects/generation (launch.json: detail-probe)."""
    d = os.path.join(OUT, "page")
    os.makedirs(d, exist_ok=True)
    root = os.path.join("art", "objects", "generation")
    data = []
    for a, j, big, raws, size in cells():
        img, raw = {}, {}
        for k, im in big.items():
            if im is not None:
                f = "%s_%s.png" % (a.replace(":", "_"), k)
                im.save(os.path.join(d, f))
                img[k] = f
        for m, p in raws.items():
            if p:
                raw[m] = os.path.relpath(p, d).replace(os.sep, "/")
        data.append({"asset": a, "what": j["what"], "img": img, "raw": raw, "w": size[0], "h": size[1],
                     "titles": TITLES})
    html = PAGE.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    with open(os.path.join(d, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    print("страница: http://localhost:8778/%s/page/index.html" % os.path.relpath(OUT, root).replace(os.sep, "/"))


REGRESSION = os.path.join("art", "objects", "generation", "regression", "detail_critical_v1.json")
# решение 30.09 (специалист): три класса брака детали - в словаре QA навсегда, набор пробы - постоянный
GATE = {
    "BLURRED_UPSCALE_FAIL": "внутренние формы - размытое увеличение пикселей оригинала, а не новый HD-рисунок",
    "DETAIL_RECONSTRUCTION_FAIL": "мелкая функциональная деталь (экран, надпись, полки, решётка) не стала "
                                  "настоящим элементом: пропала, слилась или число деталей не то",
    "RECONSTRUCTED_BUT_INVENTED": "деталь чёткая, но придумана заново: не тот рисунок, текст или число, "
                                  "что у оригинала",
}


def regression():
    """Постоянный регрессионный набор detail-critical: 10 предметов пробы с зерном, ревизиями входа,
    хэшами ответов A/B/C и вердиктами Vitali. Новый путь детали принимается, только если он на этом
    наборе даёт PASS там, где A/B/C дали FAIL, - и не хуже B ни на одном предмете."""
    snap = {a["asset_id"]: a for a in load(os.path.join("art", "objects", "generation", "batches",
                                                          BATCH + ".json"))["assets"]}
    ex = {m: load(os.path.join(OUT, "execution_%s.json" % m)) for m in MODES_ALL}
    verdicts = {}
    with open(os.path.join(OUT, "verdicts_vitali.tsv"), encoding=ENC) as f:
        for ln in f.read().splitlines()[1:]:
            p = (ln.split("\t") + ["", "", "", "", ""])[:5]
            if p[0]:
                verdicts[(p[0], p[1])] = {"verdict": p[2], "failed_criteria": p[3], "note": p[4]}
    assets = []
    for aid in ASSETS:
        a = snap[aid]
        row = next(r for r in a["rows"] if r["asset_id"] == aid and r["key"] == a["canonical"]["key"])
        modes = {}
        for m in MODES_ALL:
            j = next(j for j in ex[m]["jobs"] if j["asset_id"] == aid)
            modes[m] = {k: j[k] for k in ("seed", "prompt_rev", "raw_sha256", "final_sha256")}
            modes[m].update(verdicts.get((aid, m), {"verdict": ""}))
            modes[m]["verdict_source"] = "HUMAN (Vitali, 30.09)"
        assets.append({"asset_id": aid, "identity": a["identity"], "canonical": a["canonical"],
                       "canonical_source_rev": row["inputs"].get("canonical_source_rev", ""),
                       "frames": a["frames"], "modes": modes})
    doc = {"set": "detail_critical_v1", "created": "2026-09-30", "permanent": True,
           "why": "проба детали probes/detail-v1: ни один режим Qwen-пути не дал PASS по DETAIL_RECONSTRUCTION",
           "source_batch": BATCH, "gate": GATE,
           "criteria": ["internal structure", "semantic detail", "edge/detail sharpness", "fidelity"],
           "verdicts": ["PASS", "PARTIAL", "FAIL", "RECONSTRUCTED_BUT_INVENTED"],
           "accept_rule": "новый путь детали: PASS хотя бы там, где все три режима FAIL, и не хуже B ни на одном",
           "modes": {m: {k: ex[m][k] for k in ("engine", "steps", "cfg", "prompt", "model_lock_sha256")
                         if k in ex[m]} | {"execution": os.path.join(OUT, "execution_%s.json" % m)}
                     for m in MODES_ALL},
           "sheet": os.path.join(OUT, "detail_sheet.png"), "summary": os.path.join(OUT, "summary.md"),
           "assets": assets}
    dump(doc, REGRESSION)
    print("регрессионный набор:", REGRESSION, "-", len(assets), "предметов")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["make", "record", "sheet", "page", "regression"])
    ap.add_argument("mode", nargs="?", default="")
    ap.add_argument("--py", default="E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe")
    a = ap.parse_args()
    if a.cmd == "make":
        make(a.py)
    elif a.cmd == "record":
        for m in (a.mode.split(",") if a.mode else ["A", "B", "C"]):
            record(m)
    elif a.cmd == "sheet":
        sheet()
    elif a.cmd == "regression":
        regression()
    else:
        page()


if __name__ == "__main__":
    main()
