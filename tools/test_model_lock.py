"""R-145: замок модели, generator_rev по замку и коду, перенос утверждения только через проверенный smoke.

Без видеокарты и без сети: слепки, партии и ответы - синтетические во временной папке.
    py -3.13 tools/test_model_lock.py
"""
import json
import os
import shutil
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hdart")
sys.path.insert(0, HERE)

import model_lock as ml          # noqa: E402
import obj_gen_spec as ogs       # noqa: E402
import repro_smoke as rs         # noqa: E402

ENC = "utf-8-sig"
FAIL = []


def check(name, ok):
    print("%s %s" % ("ok  " if ok else "FAIL", name))
    if not ok:
        FAIL.append(name)


def write(path, data, mode="w"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, mode, **({} if "b" in mode else {"encoding": ENC})) as f:
        f.write(data)


def fake_lock(hub):
    """Слепок модели и LoRA на диске и замок к ним."""
    model_files = {"model_index.json": b"{}", "transformer/w.safetensors": b"W" * 100}
    lora_files = {"lora.safetensors": b"L" * 50, "scheduler/scheduler_config.json": b"{\"s\": 1}"}
    parts = {}
    for key, repo, commit, files in (("model", "Q/Model", "a" * 40, model_files), ("lora", "V/Lora", "b" * 40, lora_files)):
        snap = ml.snapshot(repo, commit, hub)
        got = {}
        for rel, data in files.items():
            p = os.path.join(snap, rel)
            write(p, data, "wb")
            got[rel] = {"size": len(data), "sha256": ml.sha256_file(p)}
        parts[key] = {"repo": repo, "commit": commit, "files": got}
    parts["lora"]["file"] = "lora.safetensors"
    return {"lock": "t", "format": 1, "model": parts["model"], "lora": parts["lora"], "runtime": dict(ml.RUNTIME),
            "libraries": ml.library_versions(), "created": "x", "code": {"rev": "c1"}, "hardware": {"gpu": "x"}}


def test_lock(tmp):
    hub = os.path.join(tmp, "hub")
    lock = fake_lock(hub)
    check("замок совпадает со слепком и библиотеками", ml.check_runtime(lock, hub=hub) == [])
    p = ml.pin(lock)
    check("pin: коммиты из замка и без сети", p["model_revision"] == "a" * 40 and p["lora_revision"] == "b" * 40
          and p["local_files_only"] is True)
    # большой файл быстрой проверкой - по размеру; подмена того же размера видна только --full
    big = os.path.join(ml.snapshot("Q/Model", "a" * 40, hub), "transformer", "w.safetensors")
    old = ml.SMALL
    ml.SMALL = 10
    write(big, b"X" * 100, "wb")
    check("быстрая проверка: большой файл того же размера не читается", ml.check_runtime(lock, hub=hub) == [])
    check("--full: подменённые веса того же размера пойманы", any("sha256" in b for b in ml.check_runtime(lock, True, hub)))
    write(big, b"X" * 99, "wb")
    check("размер весов не тот - пойман и быстрой проверкой", any("размер" in b for b in ml.check_runtime(lock, hub=hub)))
    write(big, b"W" * 100, "wb")
    # файл LoRA читается всегда, даже большой
    lp = os.path.join(ml.snapshot("V/Lora", "b" * 40, hub), "lora.safetensors")
    write(lp, b"M" * 50, "wb")
    check("файл LoRA сверяется по sha256 всегда", any("lora.safetensors sha256" in b for b in ml.check_runtime(lock, hub=hub)))
    write(lp, b"L" * 50, "wb")
    ml.SMALL = old
    lock2 = json.loads(json.dumps(lock))
    lock2["libraries"]["diffusers"] = "0.0.0"
    check("другая версия diffusers - расхождение", any("diffusers" in b for b in ml.check_runtime(lock2, hub=hub)))
    check("нет слепка ревизии - расхождение", ml.check_files(dict(lock["model"], commit="c" * 40), hub=hub) != [])
    # lock_rev: служебные поля не влияют, байты весов влияют
    lock3 = dict(lock, created="y", hardware={"gpu": "другая"}, code={"rev": "c2"}, notes="n")
    check("lock_rev не зависит от created/hardware/code/notes", ogs.lock_rev(lock3) == ogs.lock_rev(lock))
    lock4 = json.loads(json.dumps(lock))
    lock4["model"]["files"]["transformer/w.safetensors"]["sha256"] = "0" * 64
    check("lock_rev меняется с sha256 весов", ogs.lock_rev(lock4) != ogs.lock_rev(lock))
    lock5 = json.loads(json.dumps(lock))
    lock5["libraries"]["torch"] = "9.9"
    check("lock_rev меняется с версией torch", ogs.lock_rev(lock5) != ogs.lock_rev(lock))
    return lock


def test_code_rev(tmp):
    d = os.path.join(tmp, "code")
    os.makedirs(d)
    src = "A = 1\n\n\ndef f():\n    return 1\n\n\ndef g():\n    return 2\n"
    write(os.path.join(d, "m.py"), src)
    parts = (("m.py", ("A", "f")),)
    r1 = ogs.code_rev(parts, d)
    write(os.path.join(d, "m.py"), src.replace("return 2", "return 3"))
    check("code_rev: правка функции вне списка ревизию не меняет", ogs.code_rev(parts, d) == r1)
    write(os.path.join(d, "m.py"), src.replace("return 1", "return 5"))
    check("code_rev: правка функции из списка меняет ревизию", ogs.code_rev(parts, d) != r1)
    write(os.path.join(d, "m.py"), src.replace("A = 1", "A = 2"))
    check("code_rev: константа из списка меняет ревизию", ogs.code_rev(parts, d) != r1)
    try:
        ogs.code_rev((("m.py", ("нет_такой",)),), d)
        check("code_rev: пропавшее имя - стоп", False)
    except SystemExit:
        check("code_rev: пропавшее имя - стоп", True)
    check("CODE_PARTS живого генератора находятся", len(ogs.code_rev()) == 12)


def test_approval(lock):
    no_lock = ogs.spec(lock={}, code="c")
    check("без замка: pinned ложь и не утверждено", no_lock["pinned"] is False and not ogs.approved_for(no_lock, "acceptance"))
    s = ogs.spec(lock=lock, code="c1")
    check("с замком: policy_rev отдельно от generator_rev", s["generator_policy_rev"] == ogs.GENERATOR_POLICY["rev"]
          and s["generator_rev"] != s["generator_policy_rev"])
    check("смена политики generator_rev не меняет",
          ogs.spec(dict(ogs.GENERATOR, note="другая"), lock=lock, code="c1")["generator_rev"] == s["generator_rev"])
    check("смена кода меняет generator_rev", ogs.spec(lock=lock, code="c2")["generator_rev"] != s["generator_rev"])
    gen = dict(ogs.GENERATOR, equivalent_to=dict(ogs.GENERATOR["equivalent_to"], status="PENDING_SMOKE",
                                                  generator_rev=s["generator_rev"]))
    g = ogs.spec(gen, lock=lock, code="c1")
    check("эквивалентность до smoke - утверждение не переходит", not ogs.approved_for(g, "acceptance"))
    gen["equivalent_to"]["status"] = "VERIFIED"
    g = ogs.spec(gen, lock=lock, code="c1")
    check("smoke VERIFIED на эту generator_rev - годен для приёмки, не для производства",
          ogs.approved_for(g, "acceptance") and not ogs.approved_for(g, "production"))
    g2 = ogs.spec(gen, lock=lock, code="c2")
    check("VERIFIED, но код с тех пор изменился - не годен", not ogs.approved_for(g2, "acceptance"))


def smoke_fixture(tmp):
    root = os.path.join(tmp, "runs")
    src = os.path.join(root, "acc-x")
    jobs = [{"job_id": "j01", "name": "j01_A", "seed": 7, "batch_id": "acc-x", "input_hash": "h1", "prompt": "p"},
            {"job_id": "j02", "name": "j02_B", "seed": 8, "batch_id": "acc-x", "input_hash": "h2", "prompt": "p"},
            {"job_id": "j03", "name": "j03_C", "seed": 9, "batch_id": "acc-x", "reference": {"raw": "raw/j01_A.png"}}]
    write(os.path.join(src, "batch_jobs.json"), json.dumps(jobs))
    from PIL import Image
    outs = {}
    for j, col in (("j01_A", (10, 20, 30, 255)), ("j02_B", (40, 50, 60, 255)), ("j03_C", (1, 1, 1, 255))):
        raw = os.path.join(src, "photo", "raw", j + ".png")
        os.makedirs(os.path.dirname(raw), exist_ok=True)
        Image.new("RGBA", (8, 8), col).save(raw)
        cut = os.path.join(src, "photo", "S.PCK", j + ".png")
        os.makedirs(os.path.dirname(cut), exist_ok=True)
        Image.new("RGBA", (4, 4), col).save(cut)
        outs[j[:3]] = {"raw": "raw/%s.png" % j, "raw_sha256": ml.sha256_file(raw),
                       "files": {"S.PCK/%s.png" % j: ml.sha256_file(cut)}}
    write(os.path.join(src, "photo", "outputs.json"), json.dumps(outs))
    write(os.path.join(src, "execution.json"), json.dumps([{"dry_run": False, "returncode": 0, "started": "t",
                                                          "generator_rev": "old"}]))
    return root, src


def test_smoke(tmp):
    root, src = smoke_fixture(tmp)
    now = {"name": "n", "generator_rev": "new1", "prompt_rev": "p", "lock_rev": "l", "code_rev": "c",
           "lock_code_rev": "c", "pinned": True, "generator_policy_rev": "pol", "approved_rev": "old",
           "args": ["--engine", "turbo"], "script": "tools/hdart/obj_photo.py"}
    rs.gen_now = lambda: dict(now)
    try:
        rs.prepare("acc-x", ["j01", "j03"], root)
        check("smoke: задание с опорой <image2> не берётся", False)
    except SystemExit:
        check("smoke: задание с опорой <image2> не берётся", True)
    sid = rs.prepare("acc-x", ["j01", "j02"], root)
    d = os.path.join(root, sid)
    copy = json.load(open(os.path.join(d, "jobs.json"), encoding=ENC))
    check("smoke: задания без batch_id, зёрна прежние", all("batch_id" not in j for j in copy)
          and [j["seed"] for j in copy] == [7, 8])
    check("smoke: старая партия не тронута", sorted(os.listdir(src)) == ["batch_jobs.json", "execution.json", "photo"])
    calls = []
    rc = rs.run(sid, dry_run=True, spawn=lambda cmd, cwd: calls.append(cmd) or 0, root=root)
    check("smoke --dry-run: obj_photo с --dry-run, без --batch", rc == 0 and calls and "--dry-run" in calls[0]
          and "--batch" not in calls[0] and calls[0][1].endswith("obj_photo.py"))

    def paint_same(cmd, cwd):          # «видеокарта»: те же байты, что в партии
        for j in ("j01_A", "j02_B"):
            for rel in ("raw/%s.png" % j, "S.PCK/%s.png" % j):
                os.makedirs(os.path.dirname(os.path.join(d, "photo", rel)), exist_ok=True)
                shutil.copy(os.path.join(src, "photo", rel), os.path.join(d, "photo", rel))
        return 0
    check("smoke: те же байты - код 0", rs.run(sid, spawn=paint_same, root=root) == 0)
    res = json.load(open(os.path.join(d, "smoke_result.json"), encoding=ENC))
    check("smoke: REPRODUCED_BYTE_IDENTICAL и перенос можно", res["verdict"] == "REPRODUCED_BYTE_IDENTICAL"
          and res["approval_transfer"].startswith("можно"))
    try:
        rs.run(sid, spawn=paint_same, root=root)
        check("smoke: в папке уже есть ответы - второй run не идёт", False)
    except SystemExit:
        check("smoke: в папке уже есть ответы - второй run не идёт", True)
    from PIL import Image
    Image.new("RGBA", (8, 8), (10, 20, 31, 255)).save(os.path.join(d, "photo", "raw", "j01_A.png"))
    res = rs.compare(sid, root)
    r = res["jobs"]["j01"]
    check("smoke: raw на единицу в канале - RAW_DIFFERS, попиксельно max 1, перенос нельзя",
          r["verdict"] == "RAW_DIFFERS" and r["raw_pixels"]["max"] == 1 and res["verdict"] == "NOT_REPRODUCED"
          and res["approval_transfer"] == "нельзя автоматически")
    now["generator_rev"] = "new2"
    try:
        rs.run(sid, spawn=paint_same, root=root)
        check("smoke: generator_rev сменилась после prepare - стоп", False)
    except SystemExit:
        check("smoke: generator_rev сменилась после prepare - стоп", True)


def main():
    tmp = tempfile.mkdtemp(prefix="t_lock_")
    try:
        lock = test_lock(tmp)
        test_code_rev(tmp)
        test_approval(lock)
        test_smoke(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("итог: %s" % ("всё прошло" if not FAIL else "ПРОВАЛЕНО %d" % len(FAIL)))
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
