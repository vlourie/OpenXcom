#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""STRUCT_GUIDE_V1 - проба подавления лесенки (R-160): три входа одного PHOTO-рендера.

  A - как photo_render_v1: кадр bicubic x16 на подложке. Не рисуется заново: берётся готовый итог v1
      (тот же кусок, те же попытки) из photo-accept-v1/render.
  B - вместо bicubic чистый структурный guide (struct_guide.build) на той же подложке.
  C - guide первой картинкой (геометрия; 2.1 держится за первую сильнее, R-044) и bicubic оригинала второй:
      цвет, опознание, детали. Промпт тот же плюс одна фраза про <image2> (C_TEXT) - без неё вторая
      картинка без имени, а называть картинки Qwen велит тегами (R-045).
Всё прочее - как photo_render_v1, без правки его кода: модель по замку, 40 шагов, cfg 4, 1 Мп, зерно задания,
подложка panels_by_margin, промпт prompt_for, негатив obj_photo.NEGATIVE, вырезка photo_base.cut, проверки
photo_accept.checks, до трёх попыток с теми же правилами перерисовки.

Итог 01.10: ворота пройдены, рабочий вариант - C (DECISIONS). Цикл рендера (Render.job, Render.finish) берёт
и приёмка photo_struct.py: один путь, не копия.

Процесс модели рисует не больше --max-renders новых картинок и выходит с кодом EXIT_MORE (OOM после 5 и 14
рендеров, DECISIONS 01.10); новый процесс продолжает с того же места - готовые ответы не перерисовываются.
Каждый ответ - запись в renders.jsonl (sha256), сверяет её render_chunks.py.

Модель - только через очередь (gpu_scripts.txt):
    py -3.13 tools/gpuq.py add --name struct_guide_v1 --cwd E:/OpenXCom -- \
        E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/render_chunks.py -- \
        E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/struct_probe.py
Без модели: --dry-run (план, guide, промпты), --recut (готовые raw; нет ответа - стоп до загрузки модели).
"""
import argparse
import hashlib
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.dirname(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
ROOT = os.path.dirname(os.path.dirname(HERE))

import numpy as np                      # noqa: E402
from PIL import Image                   # noqa: E402

import photo_accept as pa               # noqa: E402
import photo_base as pb                 # noqa: E402
import photo_render as pr               # noqa: E402
import struct_guide as sg               # noqa: E402

ENC = "utf-8-sig"
V1 = "art/objects/generation/probes/photo-accept-v1"
OUT = "art/objects/generation/probes/struct-guide-v1"
PRIMARY = ["CATACDECOR_CONC:18", "CULTDECOR:40", "SPACESTATION_EXTRA:8", "CORP:107", "METROBITS:10",
           "FREIGHTER_PASSENGER:57", "C_INT:25"]
SECONDARY = ["C_INT_XCOM:57", "DAWNURBAN:96", "CATACDECOR:18"]
VARIANTS = ("B", "C")
C_TEXT = ("<image2> is the same original sprite: use it only for colours, identity and small details. "
          "Take the outline, proportions and edges from <image1>; its edges are smooth lines, keep them smooth.")
MANIFEST = "renders.jsonl"
EXIT_MORE = 75                          # лимит рендеров процесса исчерпан, работа осталась (render_chunks.py)


def sha12(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:12]


def sha256_file(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def run_multi(painter, run, prompt, images, seed):
    """gen_fire.run_pass для нескольких картинок: всё то же, image - список одного размера."""
    import gen_fire
    import gen_hd
    torch = painter.torch
    W, H = gen_hd.qwen21_size(images[0].width, images[0].height, run.mp)
    src = [im.convert("RGB").resize((W, H), Image.LANCZOS) for im in images]
    kw = {"prompt": prompt, "num_inference_steps": run.steps,
          "generator": torch.Generator("cuda").manual_seed(seed)}
    if "image" in painter.accepts:
        kw["image"] = src if len(src) > 1 else src[0]
    elif "images" in painter.accepts:
        kw["images"] = src
    else:
        raise SystemExit("конвейер не принимает картинку")
    if "negative_prompt" in painter.accepts:
        kw["negative_prompt"] = gen_fire.NEGATIVE
    if "true_cfg_scale" in painter.accepts:
        kw["true_cfg_scale"] = run.cfg
    elif "guidance_scale" in painter.accepts:
        kw["guidance_scale"] = run.cfg
    if "width" in painter.accepts:
        kw["width"], kw["height"] = W, H
    return painter.pipe(**kw).images[0]


def inputs(variant, frame, rgb):
    """Картинки входа и добавка к промпту для варианта."""
    zoom = pr.RENDER_V1["zoom"]
    guide, rep = sg.build(frame, zoom, rgb)
    if variant == "B":
        return [guide], "", rep
    return [guide, pr.flat_input(frame, rgb, zoom)], " " + C_TEXT, rep


class Budget(Exception):
    """Новый рендер нужен, а лимит процесса исчерпан: выйти с EXIT_MORE, продолжит новый процесс."""


class Render:
    """Рендер по рецепту RENDER_V1 с входом варианта B/C. Модель грузится при первом нужном рендере."""

    def __init__(self, out, models=None, max_renders=0, recut=False):
        import model_lock
        import obj_photo as op
        import probe_object as po
        self.po, self.out, self.max, self.recut = po, out, max_renders, recut
        self.lock = model_lock.load()
        if self.lock is None:
            raise SystemExit("нет замка модели %s" % model_lock.LOCK)
        pinned = model_lock.pin(self.lock)
        self.grev = pr.generator_rev(self.lock)
        import obj_gen_spec as ogs
        self.lock_rev = ogs.lock_rev(self.lock)
        self.guide_rev = sha12(os.path.join(HERE, "struct_guide.py"))
        self.cut_rev = sha12(os.path.join(HERE, "photo_base.py"))
        self.ns = argparse.Namespace(
            models=models or po.gen_hd.DEFAULT_MODELS_DIR, qwen21_model="", qwen21_steps=pr.RENDER_V1["steps"],
            qwen21_cfg=pr.RENDER_V1["cfg"], qwen21_mp=pr.RENDER_V1["mp"], qwen21_strength=0.0,
            qwen21_offload=pr.RENDER_V1["offload"], qwen21_thrifty=False, qwen21_ref="", qwen21_ref_mp=1.0,
            qwen21_prompt="strict", qwen21_hint="off", qwen21_ref_order="ref-first",
            qwen21_revision=pinned["model_revision"], qwen21_local_only=pinned["local_files_only"])
        self.run = argparse.Namespace(mp=pr.RENDER_V1["mp"], steps=pr.RENDER_V1["steps"], cfg=pr.RENDER_V1["cfg"])
        po.gen_fire.NEGATIVE = op.NEGATIVE
        self.painter, self.renders, self.checked = None, 0, False
        self.known = set()                  # ответы, уже записанные в журнал
        mp = os.path.join(out, MANIFEST)
        if os.path.exists(mp):
            with open(mp, encoding="utf-8") as f:
                self.known = {json.loads(s)["raw"] for s in f if s.strip()}

    def check_lock(self):
        import model_lock
        if not self.checked:
            bad = model_lock.check_runtime(self.lock)
            if bad:
                raise SystemExit("расхождений с замком %d - не рисую: %s" % (len(bad), bad[:3]))
            self.checked = True

    def record(self, raw, j, v, k, found=False):
        """Строка журнала ответа: файл лёг, читается, хэш - на сверку между процессами. found - ответ был на
        диске без записи (процесс упал между сохранением и журналом, или ответ старше журнала)."""
        Image.open(raw).verify()
        key = raw.replace("\\", "/")
        rec = {"raw": key, "sha256": sha256_file(raw), "bytes": os.path.getsize(raw),
               "asset_id": j["asset_id"], "variant": v, "attempt": k, "pid": os.getpid(),
               "generator_rev": self.grev, "model_lock": self.lock_rev,
               "gpuq_job": os.environ.get("GPUQ_JOB_ID", ""), "when": time.strftime("%Y-%m-%dT%H:%M:%S")}
        if found:
            rec["found"] = True
        else:                               # который это рендер после загрузки модели: 1..max (специалист 01.10)
            rec["process_render"] = self.renders + 1
        with open(os.path.join(self.out, MANIFEST), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self.known.add(key)

    def job(self, v, j, frame, panels, raw_dir, extra_text=None):
        """Попытки одного задания -> (final, attempts); final None - ответа нет (--recut)."""
        attempts, tried, pi, final = [], set(), 0, None
        for k in range(pr.MAX_ATTEMPTS):
            name, rgb, margin = panels[pi]
            tried.add(name)
            seed = j["seed"] + pr.RENDER_V1["reseed"] * k
            ims, extra, grep_ = inputs(v, frame, rgb)
            text = pr.prompt_for(j["what"], name, rgb) + extra + (extra_text or "")
            raw = os.path.join(raw_dir, "%s.a%d.png" % (j["name"], k))
            if not os.path.exists(raw):
                if self.recut:
                    break
                if self.max and self.renders >= self.max:
                    raise Budget()
                self.check_lock()
                if self.painter is None:
                    import gen_hd           # прямой вызов, не через self.po: его видит test_gpu_scripts
                    self.painter = gen_hd.Qwen21Painter(self.ns, {"ground": ("", "")})
                ts = time.time()
                hd = run_multi(self.painter, self.run, text, ims, seed)
                self.po.gen_hd.save_png(hd, raw)
                if not os.path.exists(raw):
                    raise SystemExit("ответ не лёг на диск: %s" % raw)
                self.record(raw, j, v, k)
                self.renders += 1
                print("   %s %s попытка %d: %.0f с" % (v, j["asset_id"], k + 1, time.time() - ts), flush=True)
            elif raw.replace("\\", "/") not in self.known:
                self.record(raw, j, v, k, found=True)
            hd = Image.open(raw)
            hd = hd.convert("RGBA" if hd.mode in ("RGBA", "LA", "P") else "RGB")
            det = pr.detect_panel(hd)
            delta = round(float(np.abs(det - np.asarray(rgb, np.float32)).max()), 1)
            left = k + 1 < pr.MAX_ATTEMPTS
            rec = {"attempt": k, "seed": seed, "panel": name, "panel_rgb": list(rgb), "panel_margin": margin,
                   "prompt": text, "inputs": len(ims), "guide": grep_, "raw": raw.replace("\\", "/"),
                   "raw_sha256": sha256_file(raw),
                   "detected_rgb": [round(float(x), 1) for x in det], "panel_delta": delta}
            if delta > pa.MACHINE["panel_delta"] and left:
                rec["status"] = "PANEL_MISMATCH"
                attempts.append(rec)
                print("   %s %s: PANEL_MISMATCH (delta %.0f) - перерисовка" % (v, j["asset_id"], delta), flush=True)
                continue
            im, rep, g, m_u = pb.cut(frame, hd, asked=rgb)
            c = pa.checks(rep, delta, left, pa.footprint(g, m_u))
            verdict = pa.machine_verdict(c)
            rec["status"] = verdict
            attempts.append(rec)
            final = (im, rep, g, m_u, c, verdict)
            if verdict == "RERENDER" and left:
                if c["SILHOUETTE"][0] == "RERENDER":
                    nxt = [i for i, p in enumerate(panels) if p[0] not in tried]
                    pi = nxt[0] if nxt else pi
                print("   %s %s: RERENDER - следующая попытка на %s" % (v, j["asset_id"], panels[pi][0]), flush=True)
                continue
            break
        return final, attempts

    def finish(self, v, j, comp, whole, at, box, final, attempts, piece_dir, meta_dir, extra=None):
        """Кусок в <piece_dir>/<SET>.PCK/<n>.png и meta -> (meta, cell для листа)."""
        import obj_series as osr
        im, rep, g, m_u, c, verdict = final
        canvas = Image.new("RGBA", (whole.width * 4, whole.height * 4), (0, 0, 0, 0))
        canvas.paste(im, (box[0] * 4, box[1] * 4))
        key = comp["members"][0][0]
        piece = osr.split(canvas, comp, at, pb.GROW)[key]
        d = os.path.join(piece_dir, key[0] + ".PCK")
        os.makedirs(d, exist_ok=True)
        pp = os.path.join(d, "%d.png" % key[1])
        piece.save(pp)
        meta = {"asset_id": j["asset_id"], "variant": v, "group": j.get("group", ""), "what": j["what"],
                "generator_rev": self.grev, "guide_rev": self.guide_rev, "cut_rev": self.cut_rev,
                "attempts": attempts, "report": rep, "checks": {x: list(c[x]) for x in pa.MACHINE_CHECKS},
                "machine": verdict, "outcome": pa.outcome(verdict, len(attempts)),
                "piece": pp.replace("\\", "/"), "piece_sha256": sha256_file(pp),
                "created": time.strftime("%Y-%m-%dT%H:%M:%S")}
        meta.update(extra or {})
        with open(os.path.join(meta_dir, j["name"] + ".json"), "w", encoding=ENC) as f:
            json.dump(meta, f, ensure_ascii=False, indent=1)
        return meta, (dict(j, rel="-"), piece, g, m_u, rep, "%s %s" % (v, meta["outcome"]))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--variants", default=",".join(VARIANTS))
    ap.add_argument("--only", default="")
    ap.add_argument("--dry-run", action="store_true", dest="dry_run")
    ap.add_argument("--recut", action="store_true")
    ap.add_argument("--models", default=None)
    ap.add_argument("--max-renders", type=int, default=0, dest="max_renders",
                    help="новых рендеров на процесс, 0 - без лимита (render_chunks.py ставит 4)")
    args = ap.parse_args()
    os.chdir(ROOT)
    import map_mockup as mm

    with open(os.path.join(V1, "jobs.json"), encoding=ENC) as f:
        allj = {j["asset_id"]: j for j in json.load(f)}
    order = PRIMARY + SECONDARY
    if args.only:
        order = [a for a in order if a in args.only.split(",")]
    jobs = [dict(allj[a], group="primary" if a in PRIMARY else "secondary") for a in order]
    variants = [v for v in args.variants.split(",") if v]
    R = Render(args.out, args.models, args.max_renders, args.recut)
    print("struct_guide_v1: generator_rev %s, guide_rev %s, cut_rev %s, заданий %d x %s" % (
        R.grev, R.guide_rev, R.cut_rev, len(jobs), variants), flush=True)
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "jobs.json"), "w", encoding=ENC) as f:
        json.dump(jobs, f, ensure_ascii=False, indent=1)

    world = mm.World()
    plan = []
    for j in jobs:
        comp, whole, at, box, frame = pb.job_frame(world, j)
        panels = pr.panels_by_margin(frame)
        plan.append((j, comp, whole, at, box, frame, panels))
        gd = os.path.join(args.out, "guide")
        os.makedirs(gd, exist_ok=True)
        g, rep = sg.build(frame, pr.RENDER_V1["zoom"], panels[0][1])
        g.save(os.path.join(gd, j["name"] + ".png"))
        print("%-24s %-9s seed %d подложка %s guide %s" % (j["asset_id"], j["group"], j["seed"], panels[0][0], rep),
              flush=True)
    if args.dry_run:
        j, *_r, panels = plan[0]
        print("промпт C:", pr.prompt_for(j["what"], panels[0][0], panels[0][1]) + " " + C_TEXT)
        return
    missing = [(v, j["asset_id"]) for v in variants for j, *_r in plan
               if not os.path.exists(os.path.join(args.out, v, "raw", j["name"] + ".a0.png"))]
    if args.recut and missing:                      # R-127
        raise SystemExit("--recut, а ответа нет у %d: %s" % (len(missing), missing[:5]))
    if missing:
        R.check_lock()

    t0, total, n = time.time(), len(plan) * len(variants), 0
    try:
        for v in variants:
            raw_dir, meta_dir = os.path.join(args.out, v, "raw"), os.path.join(args.out, v, "meta")
            os.makedirs(raw_dir, exist_ok=True)
            os.makedirs(meta_dir, exist_ok=True)
            cells = []
            for j, comp, whole, at, box, frame, panels in plan:
                n += 1
                final, attempts = R.job(v, j, frame, panels, raw_dir)
                if final is None:
                    print("%s %-24s нет ответа (--recut)" % (v, j["asset_id"]), flush=True)
                    continue
                meta, cell = R.finish(v, j, comp, whole, at, box, final, attempts,
                                      os.path.join(args.out, v), meta_dir)
                cells.append(cell)
                el = time.time() - t0
                print("%s %-24s %-20s попыток %d | готово %d из %d, прошло %.0f мин" % (
                    v, j["asset_id"], meta["outcome"], len(attempts), n, total, el / 60), flush=True)
            if cells:
                pb.sheet(world, cells, os.path.join(args.out, v, "machine_sheet.png"))
    except Budget:
        print("лимит процесса: новых рендеров %d из %d - выхожу, продолжит новый процесс" % (R.renders, R.max),
              flush=True)
        sys.exit(EXIT_MORE)
    ex = {"generator_rev": R.grev, "guide_rev": R.guide_rev, "guide": sg.GUIDE_V1, "cut_rev": R.cut_rev,
          "params": pr.RENDER_V1, "c_text": C_TEXT, "variants": variants, "items": len(plan), "renders": R.renders,
          "minutes": round((time.time() - t0) / 60, 1), "gpuq_job": os.environ.get("GPUQ_JOB_ID", ""),
          "finished": time.strftime("%Y-%m-%dT%H:%M:%S")}
    if not args.recut:
        with open(os.path.join(args.out, "execution.json"), "w", encoding=ENC) as f:
            json.dump(ex, f, ensure_ascii=False, indent=1)
    print("готово: новых рендеров %d, %.0f мин" % (R.renders, ex["minutes"]), flush=True)


if __name__ == "__main__":
    main()
