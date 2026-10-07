#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""HD_PIPELINE_E2E_V1: исполнитель плана R3.3 - от manifest до готовых PNG (специалист 03.10, передал Vitali в
чате: «Если все E2E hard gates = 0 и присутствуют DIRECT_RENDER + EXACT_COPY + DERIVE_RECOLOR_SAFE, GPU E2E
разрешён»; R3.3 - DRY_RUN_PASS_GPU_E2E_ALLOWED).

Исполняет r33/manifest.json как есть, ничего не выбирает:
  DIRECT_RENDER       - рендер PHOTO_STRUCT_V1 тем же кодом, что photo_struct_render.py (struct_probe.Render,
                        вариант C, RENDER_V1, вырезка photo_base, проверки photo_accept). Кадр на карте - вход с карты
                        (photo_base.job_frame), кадр вне карт (BATHBITZ:14) - вход из самого спрайта, одним куском;
                        для кадров на карте prep сверяет, что оба входа равны до пикселя.
  EXACT_COPY          - копия готового кадра основы, сверка пикселей.
  DERIVE_RECOLOR_SAFE - frozen SAFE_V1 / BASE_V1 из существующего HD основы, хэш пикселей обязан совпасть с
                        expected_pixels_sha256 из manifest (он же - картинка карточки PASS).
Всё пишется в hd-e2e-v1/output/TERRAIN/<SET>.PCK/<n>.png; пак игры и мод не трогаются.

    prep      -> hd-e2e-v1/run1/jobs.json, guide/ (без модели)
    render    модель - только через очередь и render_chunks (не больше 4 рендеров на процесс):
              py -3.13 tools/gpuq.py add --name hd_e2e_v1_run1 --cwd E:/OpenXCom -- \
                  E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/render_chunks.py \
                  --out art/objects/generation/probes/hd-e2e-v1/run1 --max-renders 4 -- \
                  E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/hd_e2e_v1_run.py render
    assemble  -> output/, run1/result.json, result.md, sheet.png (без модели)

    py -3.13 tools/hdart/hd_e2e_v1_run.py <команда>
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.dirname(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
ROOT = os.path.dirname(os.path.dirname(HERE))
ENC = "utf-8-sig"
E2E = "art/objects/generation/probes/hd-e2e-v1"
R33 = E2E + "/r33"
RUN = E2E + "/run1"
OUTPUT = E2E + "/output"
VARIANT = "C"


def fsha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def load(path):
    with open(path, encoding=ENC) as f:
        return json.load(f)


def dump(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding=ENC, newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def manifest():
    """manifest R3.3 - только при DRY_RUN_PASS и целом хэше."""
    plan = load(os.path.join(R33, "plan.json"))
    if plan["verdict"] != "DRY_RUN_PASS_GPU_E2E_ALLOWED":
        raise SystemExit("R3.3 не разрешает GPU E2E: %s" % plan["verdict"])
    mp = os.path.join(R33, "manifest.json")
    if fsha(mp) != plan["manifest_sha256"]:
        raise SystemExit("manifest R3.3 изменён после сухого прогона")
    return plan, load(mp)


def sprite_frame(world, key):
    """Вход кадра вне карт: сам спрайт одним куском (как pieces_at для одного места)."""
    import obj_series as osr
    import photo_base as pb
    from PIL import Image  # noqa: F401
    s, f = key.split(":")
    spr = world.sprite(s.lower(), int(f), None)
    if spr is None:
        raise SystemExit("нет кадра %s" % key)
    k = (s.upper(), int(f), 0)
    comp = {"members": [(k, (0, 0, 0))], "spr": {k: spr.convert("RGBA")}, "pl": {k: 0}}
    whole, at = osr.compose(comp)
    bb = whole.split()[3].getbbox()
    p = pb.RENDER["pad"]
    box = (max(0, bb[0] - p), max(0, bb[1] - p), min(whole.width, bb[2] + p), min(whole.height, bb[3] + p))
    return comp, whole, at, box, whole.crop(box)


def job_input(world, j):
    import photo_base as pb
    if j["map"]:
        return pb.job_frame(world, j)
    return sprite_frame(world, j["asset_id"])


# ---------------------------------------------------------------- prep

def do_prep():
    import numpy as np
    import map_mockup as mm
    import photo_render as pr
    import struct_guide as sg
    plan, man = manifest()
    world = mm.World()
    jobs, checks = [], []
    for a in man["actions"]:
        if a["action"] != "DIRECT_RENDER":
            continue
        k = a["target"]
        s, f = k.split(":")
        src = load(os.path.join(E2E, "r32", "plan.json"))
        jj = [x for x in src["jobs"] if x["job_id"] == a["id"]][0]
        j = {"name": "e2e_%s_%s" % (s.lower(), f), "job_id": a["id"], "map": jj["map"], "at": jj["at"],
             "take": jj["take"], "what": a["identity"], "asset_id": k, "src": k, "seed": a["seed"],
             "stratum": "e2e", "group": "e2e", "identity_how": "AXIS_A_FINAL_IDENTITY",
             "identity_source": a["identity_source"], "output": a["outputs"][0]}
        jobs.append(j)
        comp, whole, at, box, frame = job_input(world, j)
        if j["map"]:                                   # вход с карты и из спрайта обязаны совпасть
            _c2, _w2, _a2, _b2, fr2 = sprite_frame(world, k)
            same = frame.size == fr2.size and np.array_equal(np.asarray(frame), np.asarray(fr2))
            checks.append({"asset": k, "map_vs_sprite_equal": bool(same)})
            if not same:
                raise SystemExit("%s: вход с карты и из спрайта различаются - вход вне карт не тот" % k)
        panels = pr.panels_by_margin(frame)
        g, rep = sg.build(frame, pr.RENDER_V1["zoom"], panels[0][1])
        os.makedirs(os.path.join(RUN, "guide"), exist_ok=True)
        g.save(os.path.join(RUN, "guide", j["name"] + ".png"))
        print("%-26s %-6s seed %d карта %s подложка %s" % (k, a["id"], j["seed"], j["map"] or "-", panels[0][0]))
    if os.path.exists(os.path.join(RUN, "jobs.json")) and load(os.path.join(RUN, "jobs.json")) != jobs:
        raise SystemExit("run1/jobs.json уже есть и отличается")
    dump(os.path.join(RUN, "jobs.json"), jobs)
    dump(os.path.join(RUN, "prep.json"), {"r33_spec_sha256": plan["spec_sha256"],
                                          "manifest_sha256": plan["manifest_sha256"], "input_checks": checks,
                                          "jobs": len(jobs), "at": time.strftime("%Y-%m-%dT%H:%M:%S")})
    print("заданий рендера %d; вход с карты = вход из спрайта у %d из %d кадров на картах" % (
        len(jobs), sum(c["map_vs_sprite_equal"] for c in checks), len(checks)))


# ---------------------------------------------------------------- render (видеокарта)

def do_render(max_renders):
    import map_mockup as mm
    import photo_base as pb
    import photo_render as pr
    import struct_probe as sp
    manifest()
    jobs = load(os.path.join(RUN, "jobs.json"))
    R = sp.Render(RUN, None, max_renders, False)
    print("hd_e2e_v1_run: generator_rev %s, guide_rev %s, cut_rev %s, заданий %d" % (
        R.grev, R.guide_rev, R.cut_rev, len(jobs)), flush=True)
    world = mm.World()
    raw_dir, meta_dir = os.path.join(RUN, "render", "raw"), os.path.join(RUN, "render", "meta")
    os.makedirs(raw_dir, exist_ok=True)
    os.makedirs(meta_dir, exist_ok=True)
    t0, cells = time.time(), []
    try:
        for n, j in enumerate(jobs, 1):
            comp, whole, at, box, frame = job_input(world, j)
            panels = pr.panels_by_margin(frame)
            final, attempts = R.job(VARIANT, j, frame, panels, raw_dir)
            meta, cell = R.finish(VARIANT, j, comp, whole, at, box, final, attempts,
                                  os.path.join(RUN, "render"), meta_dir,
                                  extra={"identity_how": j["identity_how"], "job_id": j["job_id"]})
            cells.append(cell)
            print("%-26s %-20s попыток %d | готово %d из %d, прошло %.0f мин" % (
                j["asset_id"], meta["outcome"], len(attempts), n, len(jobs), (time.time() - t0) / 60), flush=True)
    except sp.Budget:
        print("лимит процесса: новых рендеров %d из %d - выхожу" % (R.renders, R.max), flush=True)
        sys.exit(sp.EXIT_MORE)
    if cells:
        pb.sheet(world, cells, os.path.join(RUN, "render", "machine_sheet.png"))
    dump(os.path.join(RUN, "execution.json"), {"generator_rev": R.grev, "guide_rev": R.guide_rev,
                                                "cut_rev": R.cut_rev, "params": pr.RENDER_V1, "variant": VARIANT,
                                                "items": len(jobs), "gpuq_job": os.environ.get("GPUQ_JOB_ID", ""),
                                                "finished": time.strftime("%Y-%m-%dT%H:%M:%S")})
    print("готово: заданий %d, новых рендеров в процессе %d" % (len(cells), R.renders), flush=True)


# ---------------------------------------------------------------- assemble

def do_assemble():
    import numpy as np
    from PIL import Image, ImageDraw
    import derive_recolor_acceptance_v3 as A3v
    import derive_recolor_safe_acceptance_v1 as S
    import hd_e2e_v1_r33 as R33m
    import map_mockup as mm
    plan, man = manifest()
    jobs = {j["job_id"]: j for j in load(os.path.join(RUN, "jobs.json"))}
    out_root = os.path.abspath(OUTPUT)
    res, fails = [], []

    def put(src_img_path, dst):
        if not os.path.abspath(dst).startswith(out_root + os.sep):
            raise SystemExit("выход вне output: %s" % dst)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src_img_path, dst)

    rendered = {}
    for a in man["actions"]:
        dst = a["outputs"][0]
        r = {"action": a["action"], "id": a["id"], "target": a["target"], "output": dst}
        if a["action"] == "DIRECT_RENDER":
            j = jobs[a["id"]]
            mp = os.path.join(RUN, "render", "meta", j["name"] + ".json")
            if not os.path.exists(mp):
                fails.append("%s: нет ответа рендера" % a["id"])
                r["status"] = "MISSING"
                res.append(r)
                continue
            meta = load(mp)
            if fsha(meta["piece"]) != meta["piece_sha256"]:
                fails.append("%s: кусок изменён после рендера" % a["id"])
            put(meta["piece"], dst)
            rendered[a["target"].upper()] = dst
            r.update(status="DONE", machine=meta["machine"], outcome=meta["outcome"],
                     attempts=len(meta["attempts"]), what=meta["what"])
        elif a["action"] in ("EXACT_COPY", "MIRROR_FLIP"):
            src = rendered.get(a["from"].upper())
            if src is None:
                fails.append("%s: основы %s нет среди готовых" % (a["id"], a["from"]))
                r["status"] = "MISSING"
                res.append(r)
                continue
            if a["action"] == "EXACT_COPY":
                put(src, dst)
            else:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                Image.open(src).transpose(Image.FLIP_LEFT_RIGHT).save(dst)
            x, y = A3v.read_png(src), A3v.read_png(dst)
            same = np.array_equal(x[:, ::-1] if a["action"] == "MIRROR_FLIP" else x, y)
            if not same:
                fails.append("%s: вывод не равен основе" % a["id"])
            r.update(status="DONE" if same else "MISMATCH", source=a["from"])
        elif a["action"] == "DERIVE_RECOLOR_SAFE":
            pv = a["source_provenance"]
            if fsha(pv["path"]) != pv["sha256"]:
                fails.append("%s: HD основы изменился после сухого прогона" % a["id"])
            ev = S.eval_real({"base": a["from"], "member": a["target"], "rank": 0}, True)
            der = ev["_img"][0] if "_img" in ev else None
            if der is None or ev["eligibility"] != "SAFE_ELIGIBLE" or ev["geometry"] != a["transform_chain"][
                    "geometry_transform"]:
                fails.append("%s: вывод не получен или не SAFE_ELIGIBLE" % a["id"])
                r["status"] = "MISSING"
                res.append(r)
                continue
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            Image.fromarray(der, "RGBA").save(dst)
            got = R33m.asha(A3v.read_png(dst))
            ok = got == a["expected_pixels_sha256"]
            if not ok:
                fails.append("%s: хэш пикселей %s, ждали %s" % (a["id"], got[:12], a["expected_pixels_sha256"][:12]))
            r.update(status="DONE" if ok else "MISMATCH", source=a["from"], pixels_sha256=got,
                     type=a.get("type"), purpose=a.get("purpose"))
        r["sha256"] = fsha(dst) if os.path.exists(dst) else None
        res.append(r)

    missing = [r["id"] for r in res if not r.get("sha256")]
    by = {}
    for r in res:
        by[r["action"]] = by.get(r["action"], 0) + (1 if r.get("status") == "DONE" else 0)
    verdict = "E2E_FILES_COMPLETE" if not fails and not missing else "E2E_INCOMPLETE"
    result = {"profile": "HD_PIPELINE_E2E_V1_RUN1", "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
              "r33_spec_sha256": plan["spec_sha256"], "manifest_sha256": plan["manifest_sha256"],
              "verdict": verdict, "done_by_action": by, "failures": fails, "missing": missing, "actions": res,
              "note": "файлы готовы и сверены; качество рисунка решает человек по sheet.png, а не этот итог"}
    dump(os.path.join(RUN, "result.json"), result)

    # лист: оригинал x4 | готовый кадр на тёмном полу, по действию
    import obj_series as osr
    world = mm.World()
    cw, ch = 128, 160
    rows = [r for r in res if r.get("sha256")]
    im = Image.new("RGB", (2 * (cw + 4) + 360, len(rows) * (ch + 6)), (32, 32, 36))
    dr = ImageDraw.Draw(im)
    for i, r in enumerate(rows):
        s, f = r["target"].split(":")
        y = i * (ch + 6)
        o = world.sprite(s.lower(), int(f), None)
        if o is not None:
            im.paste(osr.on_floor(o.convert("RGBA").resize((cw, ch), Image.NEAREST), (cw, ch)), (0, y))
        im.paste(osr.on_floor(Image.open(r["output"]).convert("RGBA"), (cw, ch)), (cw + 4, y))
        txt = "%s\n%s\n%s" % (r["target"], r["action"] + (" " + r["outcome"] if r.get("outcome") else ""),
                              ("из " + r["source"]) if r.get("source") else (r.get("what", "") or "")[:48])
        dr.text((2 * (cw + 4) + 6, y + 8), txt, fill=(230, 230, 230))
    im.save(os.path.join(RUN, "sheet.png"))
    L = ["# HD_PIPELINE_E2E_V1 run1 - %s" % verdict, "",
         "Сделано %s по manifest R3.3 `%s`." % (result["at"], plan["manifest_sha256"][:12]), "",
         "Готово по действиям: %s." % by, "",
         "Сбои: %s." % ("; ".join(fails) or "нет"), "",
         "Лист для глаз: `sheet.png` (оригинал x4 | готовый кадр на тёмном полу). Качество рисунка решает человек.", "",
         "| действие | цель | итог | машина | выход |", "|---|---|---|---|---|"]
    L += ["| %s | %s | %s | %s | %s |" % (r["action"], r["target"], r.get("status"), r.get("outcome", "-"),
                                          r["output"]) for r in res]
    with open(os.path.join(RUN, "result.md"), "w", encoding=ENC, newline="\n") as f:
        f.write("\n".join(L) + "\n")
    print("%s; готово %s; сбоев %d; лист %s" % (verdict, by, len(fails), os.path.join(RUN, "sheet.png")))
    for x in fails:
        print("  СБОЙ", x)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("prep", "render", "assemble"))
    ap.add_argument("--max-renders", type=int, default=0, dest="max_renders")
    a = ap.parse_args()
    os.chdir(ROOT)
    if a.cmd == "prep":
        do_prep()
    elif a.cmd == "render":
        do_render(a.max_renders)
    else:
        do_assemble()


if __name__ == "__main__":
    main()
