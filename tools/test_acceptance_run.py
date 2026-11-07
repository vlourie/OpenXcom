#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""acceptance_run: видеокарта получает ровно задания замороженного снимка (P1-B, замечания 30.09, R-087).

Без модели и без видеокарты, на синтетическом снимке во временной папке:
  * компиляция читает только снимок - живое состояние (load_state) при ней не трогается;
  * batch_jobs.json правили руками - повторная компиляция отказывается;
  * снимок правили в обход --freeze (задания против jobs_hash) - BATCH_STALE;
  * verify_for_gpu: свежий снимок и те же задания - да; задание изменено - стоп; снимок устарел - стоп;
  * run: BATCH_STALE - код 2 и obj_photo не запускается; --dry-run - не запускается, но запись в execution.json;
    obj_photo упал - вывод и проверка не делаются; команда несёт --batch и абсолютный интерпретатор;
  * опора B (замечания 30.09): raw, который партия не записывала (старый FRNITURE 19), не берётся; B до ответа
    A этой партии и после подмены файла A - не запускается; в execution.json у B reference_job и
    reference_output_sha256 = sha256 ответа A; obj_photo кончил с кодом 0, а ответа нет - код 1, без вывода.

    py -3.13 tools/test_acceptance_run.py
"""
import json
import os
import shutil
import stat
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "hdart"))
sys.stdout.reconfigure(encoding="utf-8")

import acceptance_plan as ap            # noqa: E402
import acceptance_run as arun           # noqa: E402
import asset_rev as ar                  # noqa: E402

FAIL = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        FAIL.append(name)


def expect_exit(fn, *a, **kw):
    try:
        fn(*a, **kw)
    except SystemExit as e:
        return str(e)
    return None


JOBS = [{"job_id": "j01", "name": "j01_SET_0", "asset_id": "SET:0", "identity": "refrigerator", "seed": 2714,
         "take": ["SET:0@0"], "prompt": "p A", "view": "A", "multiview_group": "mv-SET_0",
         "expected_outputs": ["SET.PCK/0.png"], "derive": []},
        {"job_id": "j02", "name": "j02_SET_1", "asset_id": "SET:0", "identity": "refrigerator", "seed": 2715,
         "take": ["SET:1@0"], "prompt": "p B <image2>", "view": "B", "multiview_group": "mv-SET_0",
         "reference": {"view": "A", "job_id": "j01", "job_name": "j01_SET_0", "raw": "raw/j01_SET_0.png"},
         "expected_outputs": ["SET.PCK/1.png"], "derive": []}]
GEN = {"name": "g", "script": "tools/hdart/obj_photo.py", "args": ["--engine", "turbo", "--rgba"],
       "generator_rev": "gen1", "prompt_rev": "pr1", "status": "APPROVED_FOR_ACCEPTANCE", "approved_rev": "gen1"}


def make_snap(jobs=JOBS):
    snap = {"generator": GEN, "assets": [], "jobs": jobs, "jobs_hash": ar.h12(jobs)}
    snap["acceptance_batch_id"] = "acc-" + ar.h12(snap)
    return snap


def fresh(batch_id):
    return ap.load(os.path.join(tmp, batch_id + ".json")), []


def stale(_batch_id):
    return {}, [("SET:0", "STALE", ["family_rev"])]


tmp = tempfile.mkdtemp(prefix="accrun_")
runs = os.path.join(tmp, "runs")
try:
    snap = make_snap()
    bid = snap["acceptance_batch_id"]
    ap.write_frozen(snap, tmp)

    real_state = ap.load_state

    def no_live():
        raise AssertionError("компиляция читает живое состояние")
    ap.load_state = no_live
    try:
        s, jobs, path = arun.compile_batch(bid, tmp, runs)
        ok = True
    except AssertionError:
        ok = False
    finally:
        ap.load_state = real_state
    check("компиляция - только из снимка, живое состояние не читается", ok)
    check("batch_jobs: задания снимка как есть, плюс batch_id и what",
          [arun.strip(j) for j in jobs] == JOBS and all(j["batch_id"] == bid and j["what"] == "refrigerator" for j in jobs))
    check("повторная компиляция того же снимка проходит", expect_exit(arun.compile_batch, bid, tmp, runs) is None)

    with open(path, "w", encoding=arun.ENC) as f:
        f.write(json.dumps(jobs[:1]))
    check("batch_jobs правили руками - отказ", "не совпадает" in (expect_exit(arun.compile_batch, bid, tmp, runs) or ""))
    os.remove(path)

    bad = make_snap()
    bad["jobs"] = [dict(JOBS[0], seed=1)] + JOBS[1:]
    bad["acceptance_batch_id"] = bad_id = "acc-tampered0000"
    with open(os.path.join(tmp, bad_id + ".json"), "w", encoding=arun.ENC) as f:
        json.dump(bad, f)
    check("задания снимка против jobs_hash - BATCH_STALE",
          "BATCH_STALE" in (expect_exit(arun.load_snapshot, bad_id, tmp) or ""))
    check("снимка нет - BATCH_STALE", "BATCH_STALE" in (expect_exit(arun.load_snapshot, "acc-none", tmp) or ""))

    compiled = arun.compiled_jobs(snap)
    check("verify_for_gpu: свежий снимок, те же задания - да",
          expect_exit(arun.verify_for_gpu, bid, compiled, tmp, fresh) is None)
    changed = [dict(compiled[0], prompt="other")] + compiled[1:]
    check("verify_for_gpu: задание изменено - стоп", expect_exit(arun.verify_for_gpu, bid, changed, tmp, fresh) is not None)
    check("verify_for_gpu: одно задание выкинуто - стоп",
          expect_exit(arun.verify_for_gpu, bid, compiled[:1], tmp, fresh) is not None)
    check("verify_for_gpu: снимок устарел - стоп",
          "BATCH_STALE" in (expect_exit(arun.verify_for_gpu, bid, compiled, tmp, stale) or ""))

    calls = []

    def spawn(cmd, cwd=None):
        calls.append(cmd)
        return 3

    check("run: BATCH_STALE - код 2, obj_photo не запускался",
          arun.run(bid, check=stale, spawn=spawn, folder=tmp, root=runs) == 2 and not calls
          and not os.path.exists(os.path.join(runs, bid, "execution.json")))
    rc = arun.run(bid, dry_run=True, check=fresh, spawn=spawn, folder=tmp, root=runs)
    rec_path = os.path.join(runs, bid, "execution.json")
    rec = ap.load(rec_path) if os.path.exists(rec_path) else []
    check("run --dry-run: код 0, obj_photo не запускался, запись с хэшами",
          rc == 0 and not calls and len(rec) == 1 and rec[0]["dry_run"] and rec[0]["jobs_hash"] == snap["jobs_hash"]
          and len(rec[0]["batch_jobs_sha256"]) == 64 and rec[0]["returncode"] is None)
    cmd = rec[0]["command"] if rec else []
    check("команда: абсолютный интерпретатор, --jobs batch_jobs, --batch <id>, аргументы генератора",
          os.path.isabs(cmd[0]) and cmd[cmd.index("--batch") + 1] == bid and "--rgba" in cmd
          and cmd[cmd.index("--jobs") + 1].endswith("batch_jobs.json"))

    if os.path.exists(arun.PY_MODEL):
        done = []
        real_derive, real_qa = arun.derive, arun.qa
        arun.derive = lambda *a, **k: done.append("derive")
        arun.qa = lambda *a, **k: done.append("qa")
        try:
            rc = arun.run(bid, check=fresh, spawn=spawn, folder=tmp, root=runs)
        finally:
            arun.derive, arun.qa = real_derive, real_qa
        rec = ap.load(rec_path)
        check("obj_photo упал - код его, вывод и проверка не делались, код в записи",
              rc == 3 and len(calls) == 1 and not done and rec[-1]["returncode"] == 3)
    else:
        print("skip obj_photo упал: нет интерпретатора модели %s" % arun.PY_MODEL)

    # опора B - ответ A именно этой партии (sha256), чужой raw не берётся
    photo = os.path.join(runs, bid, "photo")
    os.makedirs(os.path.join(photo, "raw"), exist_ok=True)
    os.makedirs(os.path.join(photo, "SET.PCK"), exist_ok=True)

    def fake_paint(job, content):
        raw = os.path.join(photo, "raw", job["name"] + ".png")
        with open(raw, "wb") as f:
            f.write(content)
        files = []
        for rel in job["expected_outputs"]:
            p = os.path.join(photo, rel)
            with open(p, "wb") as f:
                f.write(content + rel.encode())
            files.append(p)
        return raw, files

    ja, jb = compiled
    stale_raw = os.path.join(photo, "raw", ja["name"] + ".png")
    with open(stale_raw, "wb") as f:
        f.write(b"old FRNITURE 19")
    check("raw лежит, а партия его не записывала - не беру",
          "не записывала" in (expect_exit(arun.check_raw, photo, ja, stale_raw) or ""))
    check("B до ответа A этой партии - не запускается",
          "не выполнялось" in (expect_exit(arun.check_reference, photo, jb) or ""))
    os.remove(stale_raw)
    raw_a, files_a = fake_paint(ja, b"A1")
    rec_a = arun.record_output(photo, ja, raw_a, files_a)
    check("свой записанный raw берётся повторно", expect_exit(arun.check_raw, photo, ja, raw_a) is None)
    ref = arun.check_reference(photo, jb)
    check("опора B: reference_job j01 и sha256 ответа A", ref == {"reference_job": "j01",
                                                                   "reference_output_sha256": rec_a["raw_sha256"]})
    with open(raw_a, "wb") as f:
        f.write(b"A2 from elsewhere")
    check("ответ A подменили после записи - B не запускается",
          "не совпадает" in (expect_exit(arun.check_reference, photo, jb) or ""))
    check("и сам A его не возьмёт", expect_exit(arun.check_raw, photo, ja, raw_a) is not None)
    changed_job = dict(ja, prompt="other")
    raw_a, files_a = fake_paint(ja, b"A1")
    check("raw записан для другого задания (промпт) - не беру",
          expect_exit(arun.check_raw, photo, changed_job, raw_a) is not None)
    _recs, miss = arun.outputs_of(snap, photo)
    check("ответа B нет - outputs_of называет его", any(m.startswith("j02") for m in miss) and
          not any(m.startswith("j01") for m in miss))

    if os.path.exists(arun.PY_MODEL):
        def spawn_ok(cmd, cwd=None):
            ra, fa = fake_paint(ja, b"A3")
            arun.record_output(photo, ja, ra, fa)
            r = arun.check_reference(photo, jb)
            rb, fb = fake_paint(jb, b"B3")
            arun.record_output(photo, jb, rb, fb, r)
            return 0

        done = []
        real_derive, real_qa = arun.derive, arun.qa
        arun.derive = lambda *a, **k: done.append("derive")
        arun.qa = lambda *a, **k: done.append("qa")
        try:
            rc = arun.run(bid, check=fresh, spawn=spawn_ok, folder=tmp, root=runs)
            last = ap.load(rec_path)[-1]
            o = last.get("outputs", {})
            check("execution.json: у B reference_job j01 и sha256 ответа A этого запуска, вывод и проверка сделаны",
                  rc == 0 and done == ["derive", "qa"] and o.get("j02", {}).get("reference_job") == "j01"
                  and o["j02"]["reference_output_sha256"] == o["j01"]["raw_sha256"] and not last["missing_outputs"])

            def spawn_half(cmd, cwd=None):
                os.remove(os.path.join(photo, "SET.PCK", "1.png"))
                return 0
            done.clear()
            rc = arun.run(bid, check=fresh, spawn=spawn_half, folder=tmp, root=runs)
            check("код 0, а ответа нет - код 1, вывод и проверка не делались",
                  rc == 1 and not done and ap.load(rec_path)[-1]["missing_outputs"])
        finally:
            arun.derive, arun.qa = real_derive, real_qa
finally:
    for dp, _dn, fn in os.walk(tmp):
        for p in fn:
            os.chmod(os.path.join(dp, p), stat.S_IWRITE)
    shutil.rmtree(tmp, ignore_errors=True)

print("итог: " + ("всё прошло" if not FAIL else "%d не прошло" % len(FAIL)))
sys.exit(1 if FAIL else 0)
