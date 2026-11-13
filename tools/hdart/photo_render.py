#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""photo_render_v1 - рендер PHOTO-базы для PHOTO acceptance v1 (01.10), отдельно от obj_photo.py.

Рецепт A (made01 #259, PHOTO v2 6:2): полный Qwen-Image-2.1, 40 шагов, cfg 4, 1 Мп, кадр bicubic x16 на
подложке, промпт obj_photo.PHOTO. Отличия - только подложка (R-157: made01 подавал свою, а модель
возвращала светло-серую 165-191 почти всегда):
  * подложка - photo_base.panel_for (серая, если отделяет тело; иначе цветная), и в картинке, и в тексте:
    "Render the object on a uniform neutral background: RGB(r, g, b). ..." (формулировка специалиста);
  * в ответе подложка меряется (медиана полосы 8 пикселей по краю) - panel_delta, худший канал; больше
    MACHINE.panel_delta - PANEL_MISMATCH: не вырезать из чужого фона, а перерисовать с другим зерном;
  * форма не проверяется (тело цвета подложки ответа, photo_base UNVERIFIABLE) - перерисовать на следующей
    по запасу подложке. Попыток не больше MAX_ATTEMPTS; не закрылось - итог REVIEW, решает человек.
Модель - строго по замку art/models/qwen21_turbo_rgba.lock.json (коммит, без сети, R-145), без LoRA.
generator_rev - свой: параметры, замок и текст кода рендера (obj_gen_spec.code_parts). Вырезка -
photo_base.cut как есть; её sha256 пишется отдельно (cut_rev). obj_photo.py не правится (он в CODE_PARTS turbo).

Модель на видеокарте - только через очередь (gpu_scripts.txt):
    py -3.13 tools/gpuq.py add --name photo_accept_v1 --cwd E:/OpenXCom -- \
        E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/photo_render.py \
        --jobs art/objects/generation/probes/photo-accept-v1/jobs.json --out art/objects/generation/probes/photo-accept-v1/render
Без модели: --dry-run (план, подложки, промпты, generator_rev), --recut (перевырезка готовых raw; нет
ответа - стоп до загрузки модели, R-127).
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

import photo_base as pb                 # noqa: E402
import photo_accept as pa               # noqa: E402

ENC = "utf-8-sig"
MAX_ATTEMPTS = 3
RENDER_V1 = {"name": "photo_render_v1", "engine": "qwen21", "steps": 40, "cfg": 4.0, "mp": 1.0, "zoom": 16,
             "pad": 3, "offload": "model", "prompt": "obj_photo.PHOTO + PANEL_TEXT", "negative": "obj_photo.NEGATIVE",
             "input": "кадр bicubic x16 на подложке panel_for", "panel_delta_max": pa.MACHINE["panel_delta"],
             "max_attempts": MAX_ATTEMPTS, "reseed": 1000}
PANEL_TEXT = ("Render the object on a uniform {kind}background: RGB({r}, {g}, {b}). "
              "The background must remain completely flat and unchanged.")
GREY_PHRASE = "shown on a flat grey preview panel"
CODE = (
    ("obj_photo.py", ("PHOTO", "NEGATIVE")),
    ("gen_hd.py", ("QWEN21_REPO", "Qwen21Painter", "qwen21_size", "save_png")),
    ("gen_fire.py", ("run_pass",)),
    ("model_lock.py", ("pin", "check_runtime")),
    ("photo_render.py", ("RENDER_V1", "PANEL_TEXT", "GREY_PHRASE", "prompt_for", "flat_input", "detect_panel")),
)


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def prompt_for(what, name, rgb):
    """PHOTO с подложкой, названной цветом: серая фраза заменена цветом, в конце - фраза специалиста."""
    import obj_photo as op
    r, g, b = [int(v) for v in rgb]
    base = op.PHOTO.replace("{what}", what)
    if GREY_PHRASE not in base:
        raise SystemExit("в obj_photo.PHOTO нет фразы %r - промпт изменился" % GREY_PHRASE)
    base = base.replace(GREY_PHRASE, "shown on a flat preview panel of colour RGB(%d, %d, %d)" % (r, g, b))
    kind = "neutral " if name.startswith("grey") else ""
    return base + " " + PANEL_TEXT.format(kind=kind, r=r, g=g, b=b)


def flat_input(frame, rgb, zoom):
    """Как obj_photo.paint: кадр bicubic x zoom поверх ровной подложки."""
    src = frame.resize((frame.width * zoom, frame.height * zoom), Image.BICUBIC)
    flat = Image.new("RGBA", src.size, tuple(int(v) for v in rgb) + (255,))
    flat.alpha_composite(src.convert("RGBA"))
    return flat.convert("RGB")


def detect_panel(hd, band=8):
    """Подложка ответа: медиана полосы band пикселей по краю картинки."""
    rgb = np.asarray(hd.convert("RGB"), np.float32)
    edge = np.concatenate([rgb[:band].reshape(-1, 3), rgb[-band:].reshape(-1, 3),
                           rgb[:, :band].reshape(-1, 3), rgb[:, -band:].reshape(-1, 3)])
    return np.median(edge, 0)


def panels_by_margin(frame):
    """Все подложки по убыванию запаса тела до них (как photo_base.panel_for): серые, потом цветные."""
    a = np.asarray(frame.convert("RGBA"), np.float64)
    px = a[..., :3][a[..., 3] > 128]
    out = []
    for name, rgb in pb.PANELS + pb.CHROMA:
        m = float(np.percentile(np.abs(px - np.array(rgb)).max(-1), 10)) if len(px) else 0.0
        out.append((name, rgb, round(m, 1)))
    first = pb.panel_for(frame)
    return [first] + sorted((p for p in out if p[0] != first[0]), key=lambda p: -p[2])


def generator_rev(lock):
    import asset_rev as ar
    import obj_gen_spec as ogs
    return ar.h12({"params": RENDER_V1, "lock_rev": ogs.lock_rev(lock), "code": ogs.code_parts(CODE)})


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--jobs", default=os.path.join(pa.OUT, "jobs.json"))
    ap.add_argument("--out", default=os.path.join(pa.OUT, "render"))
    ap.add_argument("--only", default="", help="asset_id или имена заданий через запятую")
    ap.add_argument("--dry-run", action="store_true", dest="dry_run")
    ap.add_argument("--recut", action="store_true",
                    help="без модели: только готовые raw; нет ответа - стоп (GPUQ_BYPASS=1 - только с ним)")
    ap.add_argument("--models", default=None)
    args = ap.parse_args()
    os.chdir(ROOT)
    import map_mockup as mm
    import model_lock
    import obj_photo as op
    import obj_series as osr
    import probe_object as po

    with open(args.jobs, encoding=ENC) as f:
        jobs = json.load(f)
    if args.only:
        names = set(args.only.split(","))
        jobs = [j for j in jobs if j["name"] in names or j["asset_id"] in names]
    lock = model_lock.load()
    if lock is None:
        raise SystemExit("нет замка модели %s" % model_lock.LOCK)
    pinned = model_lock.pin(lock)
    grev = generator_rev(lock)
    cut_rev = sha256_file(os.path.join(HERE, "photo_base.py"))[:12]
    print("photo_render_v1: generator_rev %s, cut_rev %s, модель %s@%s, заданий %d" % (
        grev, cut_rev, pinned["model_repo"], pinned["model_revision"][:8], len(jobs)), flush=True)

    world = mm.World()
    plan = []
    for j in jobs:
        comp, whole, at, box, frame = pb.job_frame(world, j)
        if len(comp["members"]) != 1:
            raise SystemExit("%s: составной из %d - acceptance v1 только в один кусок" % (j["asset_id"], len(comp["members"])))
        panels = panels_by_margin(frame)
        plan.append((j, comp, whole, at, box, frame, panels))
        print("%-24s %-10s seed %d подложка %s %s запас %.0f" % (j["asset_id"], j["stratum"], j["seed"],
                                                               panels[0][0], panels[0][1], panels[0][2]), flush=True)
    if args.dry_run:
        j, *_r, panels = plan[0]
        print("промпт первого:", prompt_for(j["what"], panels[0][0], panels[0][1]))
        return
    raw_dir = os.path.join(args.out, "raw")
    meta_dir = os.path.join(args.out, "meta")
    os.makedirs(raw_dir, exist_ok=True)
    os.makedirs(meta_dir, exist_ok=True)
    missing = [j["asset_id"] for j, *_r in plan if not os.path.exists(os.path.join(raw_dir, j["name"] + ".a0.png"))]
    if args.recut and missing:                   # R-127: без готового ответа - стоп до загрузки модели
        raise SystemExit("--recut, а ответа нет у %d: %s" % (len(missing), ", ".join(missing[:5])))
    if missing:
        bad = model_lock.check_runtime(lock)
        for b in bad:
            print("   замок:", b, flush=True)
        if bad:
            raise SystemExit("расхождений с замком %d - не рисую" % len(bad))

    painter = None
    ns = argparse.Namespace(models=args.models or po.gen_hd.DEFAULT_MODELS_DIR, qwen21_model="",
                            qwen21_steps=RENDER_V1["steps"], qwen21_cfg=RENDER_V1["cfg"], qwen21_mp=RENDER_V1["mp"],
                            qwen21_strength=0.0, qwen21_offload=RENDER_V1["offload"], qwen21_thrifty=False,
                            qwen21_ref="", qwen21_ref_mp=1.0, qwen21_prompt="strict",
                            qwen21_hint="off", qwen21_ref_order="ref-first",
                            qwen21_revision=pinned["model_revision"], qwen21_local_only=pinned["local_files_only"])
    run = argparse.Namespace(mp=RENDER_V1["mp"], steps=RENDER_V1["steps"], cfg=RENDER_V1["cfg"])
    po.gen_fire.NEGATIVE = op.NEGATIVE           # как obj_photo: негатив PHOTO, не огня

    t0, done, cells, renders = time.time(), 0, [], 0
    for n, (j, comp, whole, at, box, frame, panels) in enumerate(plan, 1):
        attempts, tried, pi = [], set(), 0
        final = None
        for k in range(MAX_ATTEMPTS):
            name, rgb, margin = panels[pi]
            tried.add(name)
            seed = j["seed"] + RENDER_V1["reseed"] * k
            text = prompt_for(j["what"], name, rgb)
            raw = os.path.join(raw_dir, "%s.a%d.png" % (j["name"], k))
            if not os.path.exists(raw):
                if args.recut:
                    break
                if painter is None:
                    painter = po.gen_hd.Qwen21Painter(ns, {"ground": ("", "")})
                ts = time.time()
                hd = po.gen_fire.run_pass(painter, run, text, flat_input(frame, rgb, RENDER_V1["zoom"]), seed)
                po.gen_hd.save_png(hd, raw)
                renders += 1
                print("   %s попытка %d: %.0f с" % (j["asset_id"], k + 1, time.time() - ts), flush=True)
            hd = Image.open(raw)
            hd = hd.convert("RGBA" if hd.mode in ("RGBA", "LA", "P") else "RGB")
            det = detect_panel(hd)
            delta = round(float(np.abs(det - np.asarray(rgb, np.float32)).max()), 1)
            left = k + 1 < MAX_ATTEMPTS
            rec = {"attempt": k, "seed": seed, "panel": name, "panel_rgb": list(rgb), "panel_margin": margin,
                   "prompt": text, "raw": raw.replace("\\", "/"), "raw_sha256": sha256_file(raw),
                   "detected_rgb": [round(float(v), 1) for v in det], "panel_delta": delta}
            if delta > pa.MACHINE["panel_delta"] and left:
                rec["status"] = "PANEL_MISMATCH"         # не вырезать из чужого фона - перерисовать
                attempts.append(rec)
                print("   %s: PANEL_MISMATCH, подана %s, вернулась %s (delta %.0f) - перерисовка" % (
                    j["asset_id"], list(rgb), rec["detected_rgb"], delta), flush=True)
                continue
            im, rep, g, m_u = pb.cut(frame, hd, asked=rgb)
            c = pa.checks(rep, delta, left, pa.footprint(g, m_u))
            v = pa.machine_verdict(c)
            rec["status"] = v
            attempts.append(rec)
            final = (k, im, rep, g, m_u, c, v)
            if v == "RERENDER" and left:
                if c["SILHOUETTE"][0] == "RERENDER":    # тело цвета подложки ответа - следующая по запасу
                    nxt = [i for i, p in enumerate(panels) if p[0] not in tried]
                    pi = nxt[0] if nxt else pi
                print("   %s: RERENDER (%s) - следующая попытка на %s" % (
                    j["asset_id"], "; ".join("%s %s" % (x, c[x][1]) for x in c if c[x][0] == "RERENDER"),
                    panels[pi][0]), flush=True)
                continue
            break
        if final is None:
            print("%-24s нет ответа (--recut)" % j["asset_id"], flush=True)
            continue
        k, im, rep, g, m_u, c, v = final
        canvas = Image.new("RGBA", (whole.width * 4, whole.height * 4), (0, 0, 0, 0))
        canvas.paste(im, (box[0] * 4, box[1] * 4))
        key = comp["members"][0][0]
        piece = osr.split(canvas, comp, at, pb.GROW)[key]
        d = os.path.join(args.out, key[0] + ".PCK")
        os.makedirs(d, exist_ok=True)
        pp = os.path.join(d, "%d.png" % key[1])
        piece.save(pp)
        out = pa.outcome(v, len(attempts))
        meta = {"asset_id": j["asset_id"], "src": j["src"], "stratum": j["stratum"], "what": j["what"],
                "generator": RENDER_V1["name"], "generator_rev": grev, "cut_rev": cut_rev,
                "model": {"repo": pinned["model_repo"], "revision": pinned["model_revision"]},
                "attempts": attempts, "final_attempt": len(attempts) - 1, "report": rep,
                "checks": {x: list(c[x]) for x in pa.MACHINE_CHECKS}, "machine": v, "outcome": out,
                "piece": pp.replace("\\", "/"), "piece_sha256": sha256_file(pp),
                "created": time.strftime("%Y-%m-%dT%H:%M:%S")}
        with open(os.path.join(meta_dir, j["name"] + ".json"), "w", encoding=ENC) as f:
            json.dump(meta, f, ensure_ascii=False, indent=1)
        done += 1
        cells.append((dict(j, rel="-"), piece, g, m_u, rep, "%s %s" % (j["stratum"], out)))
        el = time.time() - t0
        print("%-24s %-10s %-20s попыток %d | готово %d из %d, прошло %.0f мин, осталось ~%.0f мин" % (
            j["asset_id"], j["stratum"], out, len(attempts), n, len(plan), el / 60,
            el / n * (len(plan) - n) / 60), flush=True)
    if cells:
        pb.sheet(world, cells, os.path.join(args.out, "machine_sheet.png"))
    ex = {"generator": RENDER_V1["name"], "generator_rev": grev, "cut_rev": cut_rev, "params": RENDER_V1,
          "model_lock_sha256": sha256_file(model_lock.LOCK), "jobs": args.jobs.replace("\\", "/"),
          "items": done, "renders": renders, "minutes": round((time.time() - t0) / 60, 1),
          "gpuq_job": os.environ.get("GPUQ_JOB_ID", ""), "finished": time.strftime("%Y-%m-%dT%H:%M:%S")}
    with open(os.path.join(args.out, "execution.json"), "w", encoding=ENC) as f:
        json.dump(ex, f, ensure_ascii=False, indent=1)
    print("готово: %d предметов, новых рендеров %d, %.0f мин" % (done, renders, ex["minutes"]), flush=True)


if __name__ == "__main__":
    main()
