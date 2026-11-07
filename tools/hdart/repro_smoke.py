#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Проверка воспроизводимости генератора (R-145): несколько заданий старой партии теми же зёрнами и
промптами, но новой generator_rev (замок модели), и сверка ответов с записанными побайтно.

Зачем: 8b9025eb1447 утверждена по приёмке acc-5e9f63c421c0, а считалась без замка модели. Ревизия с
замком наследует утверждение, только если те же задания дают те же байты (специалист 30.09). Не
побайтно - сверка raw попиксельно, и утверждение само не переходит. Старая партия не трогается: smoke -
отдельный id smk-<хэш> и своя папка art/objects/generation/runs/<id>/.

    py -3.13 tools\hdart\repro_smoke.py prepare --from acc-5e9f63c421c0 --jobs j03,j06,j09
    py -3.13 tools\hdart\repro_smoke.py run <smk-id> [--dry-run]     (видеокарта - только через gpuq)
    py -3.13 tools\hdart\repro_smoke.py compare <smk-id>             (без видеокарты: сверка готового)

Кладёт: smoke.json (что с чем сверяем, ревизии), jobs.json (задания старой партии без batch_id),
photo/ (ответы obj_photo), smoke_result.json и .md (вердикт по заданию: raw и куски, побайтно и попиксельно).
"""
import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import acceptance_run as arun              # noqa: E402
import asset_rev as ar                     # noqa: E402
import obj_gen_spec as ogs                 # noqa: E402

ENC = "utf-8-sig"
RUNS = arun.RUNS
# что smoke вправе запустить (то же, что acceptance_run; test_gpu_scripts видит по этой строке запуск модели)
MODEL_SCRIPTS = ("tools/hdart/obj_photo.py",)
assert MODEL_SCRIPTS == arun.MODEL_SCRIPTS


def load(path):
    with open(path, encoding=ENC) as f:
        return json.load(f)


def dump(obj, path):
    with open(path, "w", encoding=ENC) as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def gen_now():
    s = ogs.spec()
    return {k: s[k] for k in ("name", "generator_rev", "prompt_rev", "lock_rev", "code_rev", "lock_code_rev",
                              "pinned", "generator_policy_rev", "approved_rev")} | {"args": s["args"],
                                                                                    "script": s["script"]}


def prepare(source, job_ids, root=RUNS):
    src = os.path.join(root, source)
    jobs = {j["job_id"]: j for j in load(os.path.join(src, "batch_jobs.json"))}
    outs = load(os.path.join(src, "photo", "outputs.json"))
    miss = [j for j in job_ids if j not in jobs or j not in outs]
    if miss:
        raise SystemExit("в %s нет заданий или ответов %s" % (source, miss))
    if any(jobs[j].get("reference") for j in job_ids):
        raise SystemExit("задание с опорой <image2> в smoke не берётся: опора - ответ другого задания")
    g = gen_now()
    if not g["pinned"]:
        raise SystemExit("нет замка модели - smoke без замка ничего не проверяет (R-145)")
    if g["lock_code_rev"] != g["code_rev"]:
        raise SystemExit("код генератора изменился после замка (%s против %s) - снять замок заново"
                         % (g["lock_code_rev"], g["code_rev"]))
    sid = "smk-" + ar.h12([source, sorted(job_ids), g["generator_rev"], g["prompt_rev"]])
    d = os.path.join(root, sid)
    os.makedirs(d, exist_ok=True)
    # задание - как было в партии, до байта, только без batch_id: obj_photo идёт без --batch и снимка
    copy = [{k: v for k, v in jobs[j].items() if k != "batch_id"} for j in job_ids]
    dump(copy, os.path.join(d, "jobs.json"))
    execs = load(os.path.join(src, "execution.json"))
    done = [e for e in execs if not e.get("dry_run") and e.get("returncode") == 0]
    smoke = {"smoke_id": sid, "source_batch": source,
             "source_execution": done[-1].get("started") if done else None,
             "source_generator_rev": done[-1].get("generator_rev") if done else None,
             "jobs": job_ids, "seeds": {j: jobs[j]["seed"] for j in job_ids},
             "input_hash": {j: jobs[j].get("input_hash") for j in job_ids},
             "expected": {j: {"raw": outs[j]["raw"], "raw_sha256": outs[j]["raw_sha256"], "files": outs[j]["files"]}
                          for j in job_ids},
             "generator": g, "jobs_sha256": arun.sha256_file(os.path.join(d, "jobs.json")),
             "created": time.strftime("%Y-%m-%dT%H:%M:%S")}
    dump(smoke, os.path.join(d, "smoke.json"))
    print("%s: %d заданий из %s, generator_rev %s (было %s), lock_rev %s, code_rev %s"
          % (sid, len(job_ids), source, g["generator_rev"], smoke["source_generator_rev"], g["lock_rev"], g["code_rev"]))
    for j in job_ids:
        print("  %s %-24s seed %d  raw %s" % (j, jobs[j]["name"], jobs[j]["seed"], outs[j]["raw_sha256"][:12]))
    return sid


def command(smoke, d):
    g = smoke["generator"]
    if g["script"] not in MODEL_SCRIPTS:
        raise SystemExit("генератор %s не из MODEL_SCRIPTS" % g["script"])
    return [arun.PY_MODEL, os.path.join(ROOT, g["script"]), "--jobs", os.path.join(d, "jobs.json"),
            "--out", os.path.join(d, "photo")] + g["args"]


def pixels(a_path, b_path):
    """Попиксельная разница двух PNG: размер, доля отличающихся пикселей, наибольшее и среднее |d| по каналам."""
    import numpy as np
    from PIL import Image
    a, b = Image.open(a_path), Image.open(b_path)
    out = {"size_a": list(a.size), "size_b": list(b.size), "mode_a": a.mode, "mode_b": b.mode}
    if a.size != b.size:
        return out
    x = np.asarray(a.convert("RGBA"), np.int16)
    y = np.asarray(b.convert("RGBA"), np.int16)
    dd = np.abs(x - y)
    m = dd.max(-1) > 0
    ys, xs = np.nonzero(m)
    out.update(pixels=int(m.size), differ_pixels=int(m.sum()), differ=round(float(m.mean()), 6), max=int(dd.max()),
               mean=round(float(dd.mean()), 4), mean_in_diff=round(float(dd[m].mean()), 4) if m.any() else 0.0,
               max_rgba=[int(v) for v in dd.reshape(-1, 4).max(0)], alpha_max=int(dd[..., 3].max()),
               bbox=[int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1] if m.any() else None)
    return out


def compare(sid, root=RUNS):
    d = os.path.join(root, sid)
    smoke = load(os.path.join(d, "smoke.json"))
    src = os.path.join(root, smoke["source_batch"], "photo")
    got = os.path.join(d, "photo")
    res, all_same = {}, True
    for j in smoke["jobs"]:
        exp = smoke["expected"][j]
        r = {"raw": exp["raw"]}
        p = os.path.join(got, exp["raw"])
        if not os.path.exists(p):
            r["verdict"] = "NO_OUTPUT"
            all_same = False
            res[j] = r
            continue
        r["raw_sha256"] = arun.sha256_file(p)
        r["raw_same"] = r["raw_sha256"] == exp["raw_sha256"]
        if not r["raw_same"]:
            r["raw_pixels"] = pixels(os.path.join(src, exp["raw"]), p)
        r["files"] = {}
        for f, h in exp["files"].items():
            q = os.path.join(got, f)
            fh = arun.sha256_file(q) if os.path.exists(q) else None
            e = {"sha256": fh, "same": fh == h}
            if fh and fh != h:
                e["pixels"] = pixels(os.path.join(src, f), q)
            r["files"][f] = e
        same = r["raw_same"] and all(e["same"] for e in r["files"].values())
        r["verdict"] = "BYTE_IDENTICAL" if same else ("RAW_SAME_CUT_DIFFERS" if r["raw_same"] else "RAW_DIFFERS")
        all_same &= same
        res[j] = r
    g = gen_now()
    out = {"smoke_id": sid, "source_batch": smoke["source_batch"], "generator_rev_prepared": smoke["generator"]["generator_rev"],
           "generator_rev_now": g["generator_rev"], "source_generator_rev": smoke["source_generator_rev"],
           "verdict": "REPRODUCED_BYTE_IDENTICAL" if all_same else "NOT_REPRODUCED",
           "approval_transfer": ("можно: equivalent_to %s -> %s со status VERIFIED" % (smoke["source_generator_rev"], smoke["generator"]["generator_rev"]))
           if all_same and g["generator_rev"] == smoke["generator"]["generator_rev"] else "нельзя автоматически",
           "jobs": res, "compared": time.strftime("%Y-%m-%dT%H:%M:%S")}
    dump(out, os.path.join(d, "smoke_result.json"))
    lines = ["# Smoke воспроизводимости %s" % sid, "",
             "Источник: партия `%s` (generator_rev `%s`), задания %s, зёрна %s." % (
                 smoke["source_batch"], smoke["source_generator_rev"], ", ".join(smoke["jobs"]),
                 ", ".join("%s=%d" % kv for kv in smoke["seeds"].items())),
             "Новая generator_rev `%s` (замок `%s`, код `%s`)." % (smoke["generator"]["generator_rev"],
                                                                 smoke["generator"]["lock_rev"], smoke["generator"]["code_rev"]),
             "", "**Итог: %s** - перенос утверждения: %s." % (out["verdict"], out["approval_transfer"]), "",
             "| задание | raw | куски | вердикт |", "|---|---|---|---|"]
    for j, r in res.items():
        if r["verdict"] == "NO_OUTPUT":
            lines.append("| %s | нет ответа | - | NO_OUTPUT |" % j)
            continue
        raw = "совпал" if r["raw_same"] else "differs %s" % r.get("raw_pixels")
        fl = ", ".join("%s %s" % (f, "=" if e["same"] else "≠") for f, e in r["files"].items())
        lines.append("| %s | %s | %s | %s |" % (j, raw, fl, r["verdict"]))
    with open(os.path.join(d, "smoke_result.md"), "w", encoding=ENC) as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    return out


def run(sid, dry_run=False, spawn=subprocess.call, root=RUNS):
    d = os.path.join(root, sid)
    smoke = load(os.path.join(d, "smoke.json"))
    g = gen_now()
    if g["generator_rev"] != smoke["generator"]["generator_rev"]:
        raise SystemExit("generator_rev сейчас %s, а smoke готовили под %s - prepare заново"
                         % (g["generator_rev"], smoke["generator"]["generator_rev"]))
    if arun.sha256_file(os.path.join(d, "jobs.json")) != smoke["jobs_sha256"]:
        raise SystemExit("jobs.json изменился после prepare - не запускаю")
    raw = [os.path.join(d, "photo", smoke["expected"][j]["raw"]) for j in smoke["jobs"]]
    if any(os.path.exists(p) for p in raw):
        # obj_photo взял бы готовый ответ вместо нового - и smoke сверил бы файл сам с собой
        raise SystemExit("в %s уже лежат ответы - smoke только в чистой папке, prepare заново" % d)
    cmd = command(smoke, d)
    print("команда: %s" % " ".join(cmd))
    if dry_run:
        rc = spawn(cmd + ["--dry-run"], cwd=ROOT)
        print("--dry-run: план и замок проверены, модель не запускалась (код %s)" % rc)
        return rc
    rc = spawn(cmd, cwd=ROOT)
    smoke.setdefault("runs", []).append({"returncode": rc, "finished": time.strftime("%Y-%m-%dT%H:%M:%S")})
    dump(smoke, os.path.join(d, "smoke.json"))
    if rc != 0:
        print("obj_photo код %s" % rc)
        return rc
    return 0 if compare(sid, root)["verdict"] == "REPRODUCED_BYTE_IDENTICAL" else 1


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("cmd", choices=["prepare", "run", "compare"])
    p.add_argument("id", nargs="?")
    p.add_argument("--from", dest="source", default="")
    p.add_argument("--jobs", default="")
    p.add_argument("--dry-run", action="store_true", dest="dry_run")
    a = p.parse_args()
    if a.cmd == "prepare":
        prepare(a.source, [j for j in a.jobs.split(",") if j])
    elif a.cmd == "run":
        sys.exit(run(a.id, a.dry_run))
    else:
        compare(a.id)


if __name__ == "__main__":
    main()
