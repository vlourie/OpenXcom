#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Запуск приёмочной партии ТОЛЬКО из замороженного снимка (P1-B, замечания 30.09).

Главный риск - заморозили одно, видеокарта получила другое (R-087). Поэтому путь один:

    неизменяемый снимок batches/<id>.json (acceptance_plan.py --freeze)
        -> --check: семейства, опознание, оригиналы, генератор, промпт, вывод - те же (иначе BATCH_STALE)
        -> компиляция: runs/<id>/batch_jobs.json - задания из снимка как есть, плюс batch_id; хэш сверяется
        -> obj_photo --batch <id>: сам ещё раз сверяет снимок и задания перед загрузкой модели
        -> вывод без модели (перекраска, зеркало) по заданиям вывода из снимка
        -> проверка: лист плитки 3x3 и карта с копиями вплотную (tile_qa.py)

Живые файлы (families.json, asset_identity.tsv, generation.json, очередь, текущий промпт) при компиляции
НЕ читаются: всё, что нужно заданию, лежит в снимке. Их читает только --check, чтобы сказать, что снимок
устарел. Изменилось хоть что-то - ничего не запускается, нужен новый --freeze (новый id).

    py -3.13 tools/hdart/acceptance_run.py check   acc-xxxxxxxxxxxx      (BATCH_CURRENT / BATCH_STALE)
    py -3.13 tools/hdart/acceptance_run.py compile acc-xxxxxxxxxxxx      (batch_jobs.json, без модели)
    py -3.13 tools/hdart/acceptance_run.py run     acc-xxxxxxxxxxxx --dry-run   (всё, кроме модели)
    py -3.13 tools/gpuq.py add --name acc-xxxxxxxxxxxx -- py -3.13 tools/hdart/acceptance_run.py run acc-xxxxxxxxxxxx
    py -3.13 tools/hdart/acceptance_run.py derive  acc-xxxxxxxxxxxx      (вывод, без модели)
    py -3.13 tools/hdart/acceptance_run.py qa      acc-xxxxxxxxxxxx      (листы проверки, без модели)

Всё кладётся в art/objects/generation/runs/<id>/: batch_jobs.json, execution.json (что, когда, каким
интерпретатором и с каким хэшем заданий запущено), photo/ (ответы obj_photo), derived/, qa/. В пак НЕ идёт.
"""
import hashlib
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import acceptance_plan as ap              # noqa: E402
import asset_rev as ar                    # noqa: E402

ENC = "utf-8-sig"
RUNS = os.path.join(ap.GEN, "runs")
# интерпретатор модели - абсолютным путём (R-097: gpuq ищет исполняемый файл от своей папки)
PY_MODEL = os.path.join(ROOT, "tools", "hdart", ".venv-qwen21", "Scripts", "python.exe")
# что runner вправе запустить: снимок не может подсунуть другой скрипт (и gpu_scripts видит, что это за запуск)
MODEL_SCRIPTS = ("tools/hdart/obj_photo.py",)


def load_snapshot(batch_id, folder=ap.BATCHES):
    path = os.path.join(folder, batch_id + ".json")
    if not os.path.exists(path):
        raise SystemExit("BATCH_STALE: снимка %s нет" % batch_id)
    snap = ap.load(path)
    if snap.get("acceptance_batch_id") != batch_id:
        raise SystemExit("BATCH_STALE: в файле %s снимок %s" % (path, snap.get("acceptance_batch_id")))
    if ar.h12(snap.get("jobs", [])) != snap.get("jobs_hash"):
        raise SystemExit("BATCH_STALE: задания снимка %s не сходятся с jobs_hash - снимок правили" % batch_id)
    return snap


def compiled_jobs(snap):
    """Задания для obj_photo: из снимка как есть, плюс batch_id. Ничего живого не читается."""
    return [dict(j, batch_id=snap["acceptance_batch_id"], what=j["identity"]) for j in snap["jobs"]]


def strip(job):
    """Задание без полей, которые добавляет компиляция, - для сверки со снимком."""
    return {k: v for k, v in job.items() if k not in ("batch_id", "what")}


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


OUTPUTS = "outputs.json"          # в photo/: что obj_photo нарисовал в ЭТОЙ партии, с хэшами


def job_hash(job):
    return ar.h12(strip(job))


def load_outputs(out):
    path = os.path.join(out, OUTPUTS)
    if not os.path.exists(path):
        return {}
    with open(path, encoding=ENC) as f:
        return json.load(f)


def check_raw(out, job, raw_path):
    """Готовый raw в папке партии берётся, только если его записала эта партия для этого же задания
    и файл с тех пор не менялся. Иначе - стоп: чужой или старый ответ (замечания 30.09)."""
    if not os.path.exists(raw_path):
        return
    rec = load_outputs(out).get(job["job_id"])
    if not rec or rec.get("job_hash") != job_hash(job) or rec.get("raw_sha256") != sha256_file(raw_path):
        raise SystemExit("%s: %s лежит, но партия его не записывала (или он изменился) - не беру; "
                         "удали файл, если это брошенный ответ этой партии" % (job["name"], raw_path))


def check_reference(out, job):
    """Задание B берёт ответ A только тот, что A записало в этой партии: sha256 файла = записанному."""
    ref = job["reference"]
    rec = load_outputs(out).get(ref["job_id"])
    path = os.path.join(out, ref["raw"])
    if not rec:
        raise SystemExit("%s: опорное задание %s в этой партии не выполнялось - не запускаю" % (
            job["name"], ref["job_id"]))
    if not os.path.exists(path) or sha256_file(path) != rec["raw_sha256"]:
        raise SystemExit("%s: опора %s не совпадает с ответом %s этой партии (sha256) - не запускаю" % (
            job["name"], path, ref["job_id"]))
    return {"reference_job": ref["job_id"], "reference_output_sha256": rec["raw_sha256"]}


def record_output(out, job, raw_path, files, ref=None):
    """Запись obj_photo после задания: хэш задания, sha256 raw и каждого куска, опора B."""
    recs = load_outputs(out)
    recs[job["job_id"]] = dict({"job_id": job["job_id"], "name": job["name"], "batch_id": job.get("batch_id"),
                                "job_hash": job_hash(job), "raw": os.path.relpath(raw_path, out).replace(os.sep, "/"),
                                "raw_sha256": sha256_file(raw_path),
                                "files": {os.path.relpath(p, out).replace(os.sep, "/"): sha256_file(p) for p in files},
                                "finished": time.strftime("%Y-%m-%dT%H:%M:%S")}, **(ref or {}))
    with open(os.path.join(out, OUTPUTS), "w", encoding=ENC) as f:
        json.dump(recs, f, ensure_ascii=False, indent=1, sort_keys=True)
    return recs[job["job_id"]]


def outputs_of(snap, out):
    """(записи заданий снимка, чего не хватает): каждый ожидаемый файл есть, и его sha256 = записанному."""
    recs, miss = load_outputs(out), []
    for j in snap["jobs"]:
        rec = recs.get(j["job_id"])
        if not rec or rec.get("job_hash") != ar.h12(j):
            miss.append("%s: нет записи" % j["job_id"])
            continue
        for rel in j["expected_outputs"]:
            p = os.path.join(out, rel)
            if not os.path.exists(p) or rec["files"].get(rel) != sha256_file(p):
                miss.append("%s: %s" % (j["job_id"], rel))
    return recs, miss


def run_dir(batch_id, root=RUNS):
    return os.path.join(root, batch_id)


def compile_batch(batch_id, folder=ap.BATCHES, root=RUNS):
    """runs/<id>/batch_jobs.json из снимка. Файл уже есть и отличается - стоп: его правили руками."""
    snap = load_snapshot(batch_id, folder)
    jobs = compiled_jobs(snap)
    d = run_dir(batch_id, root)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, "batch_jobs.json")
    text = json.dumps(jobs, ensure_ascii=False, indent=1)
    if os.path.exists(path):
        with open(path, encoding=ENC) as f:
            if f.read() != text:
                raise SystemExit("%s уже есть и не совпадает со снимком - не перезаписываю, разберись" % path)
    else:
        with open(path, "w", encoding=ENC) as f:
            f.write(text)
    return snap, jobs, path


def verify_for_gpu(batch_id, jobs, folder=ap.BATCHES, check=None):
    """Для obj_photo --batch перед загрузкой модели: снимок свежий и задания - ровно его задания."""
    snap, bad = (check or ap.check_batch)(batch_id)
    if bad:
        raise SystemExit("BATCH_STALE %s: %s - ничего не запускаю" % (
            batch_id, "; ".join("%s %s %s" % (st, k, ",".join(w)) for k, st, w in bad)))
    if ar.h12([strip(j) for j in jobs]) != snap["jobs_hash"]:
        raise SystemExit("задания не совпадают со снимком %s (jobs_hash %s) - ничего не запускаю" % (
            batch_id, snap["jobs_hash"]))
    return snap


def command(snap, jobs_path, out):
    g = snap["generator"]
    if g["script"] not in MODEL_SCRIPTS:
        raise SystemExit("генератор снимка %s не из MODEL_SCRIPTS %s - не запускаю" % (g["script"], MODEL_SCRIPTS))
    return [PY_MODEL, os.path.join(ROOT, g["script"]), "--jobs", jobs_path, "--out", out] + g["args"] + \
        ["--batch", snap["acceptance_batch_id"]]


def write_record(d, rec):
    path = os.path.join(d, "execution.json")
    hist = []
    if os.path.exists(path):
        with open(path, encoding=ENC) as f:
            hist = json.load(f)
    hist.append(rec)
    with open(path, "w", encoding=ENC) as f:
        json.dump(hist, f, ensure_ascii=False, indent=1)
    return path


def run(batch_id, dry_run=False, check=None, spawn=subprocess.call, folder=ap.BATCHES, root=RUNS):
    snap, bad = (check or ap.check_batch)(batch_id)
    for k, st, w in bad:
        print("  %-9s %-22s %s" % (st, k, ",".join(w)))
    if bad:
        print("BATCH_STALE %s - ничего не запускаю" % batch_id)
        return 2
    print("BATCH_CURRENT %s" % batch_id)
    snap, jobs, path = compile_batch(batch_id, folder, root)
    d = run_dir(batch_id, root)
    cmd = command(snap, path, os.path.join(d, "photo"))
    rec = {"batch_id": batch_id, "jobs_hash": snap["jobs_hash"], "batch_jobs": path,
           "batch_jobs_sha256": sha256_file(path), "jobs": len(jobs), "command": cmd,
           "generator_rev": snap["generator"]["generator_rev"], "prompt_rev": snap["generator"]["prompt_rev"],
           "dry_run": dry_run, "started": time.strftime("%Y-%m-%dT%H:%M:%S")}
    print("заданий %d, jobs_hash %s, batch_jobs sha256 %s" % (len(jobs), snap["jobs_hash"], rec["batch_jobs_sha256"][:12]))
    for j in jobs:
        print("  %s %-28s seed %d  %s%s" % (j["job_id"], j["name"], j["seed"], " ".join(j["take"]),
                                          ("  <image2> " + j["reference"]["raw"]) if j.get("reference") else ""))
    print("команда: %s" % " ".join(cmd))
    if dry_run:
        rec["returncode"] = None
        write_record(d, rec)
        print("--dry-run: модель не запускалась")
        return 0
    if not os.path.exists(PY_MODEL):
        raise SystemExit("нет интерпретатора модели %s" % PY_MODEL)
    rc = spawn(cmd, cwd=ROOT)
    rec.update(returncode=rc, finished=time.strftime("%Y-%m-%dT%H:%M:%S"))
    recs, miss = outputs_of(snap, os.path.join(d, "photo"))
    # по заданию: sha256 ответа и кусков; у B - reference_job и reference_output_sha256 (ответ A этой партии)
    rec["outputs"] = {k: {f: v[f] for f in ("raw_sha256", "files", "reference_job", "reference_output_sha256")
                          if f in v} for k, v in sorted(recs.items())}
    rec["missing_outputs"] = miss
    write_record(d, rec)
    if rc != 0:
        print("obj_photo код %s - вывод и проверка не делаются" % rc)
        return rc
    if miss:
        print("ответов не хватает или они изменились: %s - вывод и проверка не делаются" % "; ".join(miss[:6]))
        return 1
    derive(batch_id, folder, root)
    qa(batch_id, folder, root)
    return 0


def derive(batch_id, folder=ap.BATCHES, root=RUNS):
    """Вывод без модели по заданиям вывода из снимка: перекраска и зеркало из ответа задания основы."""
    from PIL import Image
    import map_mockup as mm
    import obj_derive as od
    snap = load_snapshot(batch_id, folder)
    d = run_dir(batch_id, root)
    world = mm.World()
    records, made, miss = {}, 0, []
    outs_rec = load_outputs(os.path.join(d, "photo"))
    for j in snap["jobs"]:
        for dv in j["derive"]:
            how = "зеркало" if dv["relation"] == "mirror" else "перекраска"
            outs = dv["outputs"]
            for i, (kb, kt) in enumerate(zip(dv["base_src"], dv["member_src"])):
                src = os.path.join(d, "photo", ap.out_path(kb))
                if not os.path.exists(src):
                    miss.append(src)
                    continue
                # основа - только ответ этой партии: sha256 файла = записанному obj_photo
                if outs_rec.get(j["job_id"], {}).get("files", {}).get(ap.out_path(kb)) != sha256_file(src):
                    raise SystemExit("%s: не тот ответ, что записала партия (sha256) - вывод не делаю" % src)
                sb, fb = kb.rsplit(":", 1)
                st, ft = kt.rsplit(":", 1)
                im = od.derive(Image.open(src), world.sprite(sb.lower(), int(fb), None),
                               world.sprite(st.lower(), int(ft), None), how)
                targets = outs if len(dv["member_src"]) == 1 else [outs[i]]
                for rel in targets:
                    out = os.path.join(d, "derived", rel)
                    os.makedirs(os.path.dirname(out), exist_ok=True)
                    im.save(out)
                    records[rel] = {"batch_id": batch_id, "job_id": j["job_id"], "relation": dv["relation"],
                                    "derived_from": ap.out_path(kb), "derived_from_sha256": sha256_file(src),
                                    "derive_rev": dv["derive_rev"], "input_hash": dv["input_hash"],
                                    "sha256": sha256_file(out)}
                    made += 1
    os.makedirs(os.path.join(d, "derived"), exist_ok=True)
    with open(os.path.join(d, "derived", "derived.json"), "w", encoding=ENC) as f:
        json.dump(records, f, ensure_ascii=False, indent=1, sort_keys=True)
    print("выведено файлов %d; нет ответа основы: %d%s" % (made, len(miss), (" - " + ", ".join(miss[:5])) if miss else ""))
    return made, miss


def qa(batch_id, folder=ap.BATCHES, root=RUNS):
    """Листы проверки по QA_strategy ассета (tile_qa): TILE_QA (плитка: 3x3 и карта), ADJACENCY_QA (рядом
    со своей копией, не плитка), COMPOSITE_SEAM_QA (составной, выведенный по кускам: шов после сборки)."""
    import tile_qa
    snap = load_snapshot(batch_id, folder)
    d = run_dir(batch_id, root)
    photo, derived, qd = os.path.join(d, "photo"), os.path.join(d, "derived"), os.path.join(d, "qa")
    need = {a["asset_id"]: a["qa_strategy"] for a in snap["assets"]}
    out = []
    for j in snap["jobs"]:
        qs = need.get(j["asset_id"], [])
        if j["relation"] != "canonical":
            continue
        if len(j["expected_outputs"]) == 1:
            key = j["take"][0].split("@")[0]
            src = os.path.join(photo, j["expected_outputs"][0])
            if os.path.exists(src):
                if "tile_qa_3x3" in qs:
                    out.append(tile_qa.repeat_sheet(src, key, os.path.join(qd, "%s_3x3.png" % j["name"])))
                if "tile_qa_map" in qs:
                    out.append(tile_qa.map_sheet(photo, key, j["map"], os.path.join(qd, "%s_map.png" % j["name"])))
                if "adjacency_qa" in qs:
                    out.append(tile_qa.adjacency(photo, key, j["map"],
                                                 os.path.join(qd, "%s_adjacency.png" % j["name"])))
        if "composite_seam_qa" in qs:
            keys = [t.split("@")[0] for t in j["take"]]
            for dv in j["derive"]:
                if len(dv["member_src"]) < 2 or "at" not in dv:
                    continue
                src_hd = {k: os.path.join(photo, ap.out_path(k)) for k in keys}
                der_hd = {k: os.path.join(derived, ap.out_path(k)) for k in dv["member_src"]}
                if not all(os.path.exists(p) for p in list(src_hd.values()) + list(der_hd.values())):
                    continue
                out.append(tile_qa.composite_seam(
                    src_hd, der_hd, [(k, tuple(a)) for k, a in zip(keys, j["at"])],
                    [(k, tuple(a)) for k, a in zip(dv["member_src"], dv["at"])], dv["map"], derived, qd,
                    "%s_%s" % (j["name"], dv["key"].replace(":", "_"))))
    os.makedirs(qd, exist_ok=True)
    with open(os.path.join(qd, "qa.json"), "w", encoding=ENC) as f:
        # вердикт (TILE_PASS / TILE_FAIL, ADJACENCY_*, COMPOSITE_SEAM_* или DERIVE_MIRROR_COMPOSITE_FAIL) ставит
        # человек по листу и в игре; числа и suspect - только куда смотреть
        json.dump([dict(o, verdict="PENDING_HUMAN") for o in out], f, ensure_ascii=False, indent=1)
    for o in out:
        print("QA %s -> %s%s" % (o["kind"], o["sheet"], ("  внимание: " + "; ".join(
            o.get("footprint", o.get("derived", {})).get("attention", []))) if o["kind"] != "tile_qa_3x3" else ""))
    return out


def main():
    import argparse
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("action", choices=["check", "compile", "run", "derive", "qa"])
    p.add_argument("batch_id")
    p.add_argument("--dry-run", action="store_true", dest="dry_run", help="run: всё, кроме модели")
    a = p.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if a.action == "check":
        snap, bad = ap.check_batch(a.batch_id)
        for k, st, w in bad:
            print("  %-9s %-22s %s" % (st, k, ",".join(w)))
        print("%s %s" % ("BATCH_STALE" if bad else "BATCH_CURRENT", a.batch_id))
        sys.exit(2 if bad else 0)
    if a.action == "compile":
        snap, jobs, path = compile_batch(a.batch_id)
        print("%s: заданий %d, jobs_hash %s, sha256 %s" % (path, len(jobs), snap["jobs_hash"], sha256_file(path)[:12]))
        return
    if a.action == "run":
        sys.exit(run(a.batch_id, a.dry_run))
    if a.action == "derive":
        derive(a.batch_id)
        return
    qa(a.batch_id)


if __name__ == "__main__":
    main()
