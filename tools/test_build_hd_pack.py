#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_hd_pack: папка пака - выход манифеста и хранилища (Pipeline v2, P1-A; семья R-087).

Во временной папке, без игры:
  * stage + save + install - цель совпадает с манифестом, прежний манифест лёг в history;
  * записанное мимо сборщика видно как CHANGED и EXTRA; install возвращает по манифесту, лишнее - в резерв;
  * install --only трогает только названные файлы;
  * adopt записывает происхождение («кто записал») и делает цель снова чистой;
  * сборка из хранилища в пустую папку - IDENTICAL с целью; блоб хранилища только для чтения;
  * контроль: сборка без одного блоба падает, а не собирает неполный пак.

    py -3.13 tools/test_build_hd_pack.py
"""
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "hdart"))

import build_hd_pack as bhp             # noqa: E402

FAIL = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        FAIL.append(name)


def clean(res):
    return not (res["MISSING"] or res["CHANGED"] or res["EXTRA"])


tmp = tempfile.mkdtemp(prefix="bhp_")
old_cwd = os.getcwd()
os.chdir(tmp)
try:
    os.makedirs("art/manifest")
    target = os.path.join(tmp, "game", "hd")
    bhp.TARGETS = {"t": target}
    with open(bhp.MANIFEST, "w", encoding="utf-8-sig") as f:
        json.dump({"files": {}}, f)
    man = bhp.load()
    bhp.stage(man, "TERRAIN/A.PCK/1.png", b"png-a1", generator="qwen21_photo", approved=True, approval="Vitali")
    bhp.stage(man, "UI/x.png", b"png-ui", generator="legacy")
    bhp.save(man, why="тест")
    check("stage не пишет в цель", not os.path.exists(target))
    bhp.install(man, "t")
    check("install: цель совпала с манифестом", clean(bhp.diff(man, target)))
    bhp.stage(man, "TERRAIN/A.PCK/2.png", b"png-a2")
    bhp.save(man)
    check("прежний манифест в history", len(os.listdir(bhp.HISTORY)) == 1)

    # мимо сборщика
    with open(os.path.join(target, "UI", "x.png"), "wb") as f:
        f.write(b"hand-made")
    with open(os.path.join(target, "UI", "extra.png"), "wb") as f:
        f.write(b"stray")
    res = bhp.diff(man, target)
    check("записанное мимо - CHANGED, EXTRA, MISSING",
          res["CHANGED"] == ["UI/x.png"] and res["EXTRA"] == ["UI/extra.png"] and res["MISSING"] == ["TERRAIN/A.PCK/2.png"])
    bhp.install(man, "t", only=["TERRAIN/A.PCK/2.png"])
    res = bhp.diff(man, target)
    check("install --only трогает только названное", not res["MISSING"] and res["CHANGED"] == ["UI/x.png"]
          and res["EXTRA"] == ["UI/extra.png"])
    bhp.install(man, "t", backup=os.path.join(tmp, "bk"))
    check("install вернул по манифесту", clean(bhp.diff(man, target)))
    check("лишнее - в резерв, не удалено", os.path.exists(os.path.join(tmp, "bk", "t", "UI", "extra.png")))
    with open(os.path.join(target, "UI", "x.png"), "rb") as f:
        check("изменённое переписано из хранилища", f.read() == b"png-ui")

    # adopt
    with open(os.path.join(target, "UI", "x.png"), "wb") as f:
        f.write(b"map-update")
    import contextlib
    import io
    buf = io.StringIO()
    argv = sys.argv
    with contextlib.redirect_stdout(buf):
        sys.argv = ["build_hd_pack.py", "status", "--target", "t"]
        code = bhp.main()
    check("status: запись мимо - «непринятые изменения», код 1",
          code == 1 and "unadopted modification" in buf.getvalue() and "map_update.py" in buf.getvalue())
    stdin = sys.stdin
    sys.stdin = io.StringIO("принимаю\n")         # не терминал: так идут скрипт и агент
    try:
        sys.argv = ["build_hd_pack.py", "adopt", "--changed", "--by", "map_update", "--target", "t"]
        bhp.main()
        refused = False
    except SystemExit as e:
        refused = "только человек" in str(e)
    finally:
        sys.stdin, sys.argv = stdin, argv
    check("adopt из скрипта (без терминала) - отказ, даже с ответом «принимаю»",
          refused and bhp.diff(man, target)["CHANGED"] == ["UI/x.png"])
    n = bhp.adopt(man, "t", bhp.diff(man, target)["CHANGED"], "map_update", "тест")
    e = man["files"]["UI/x.png"]
    check("adopt записал происхождение", n == 1 and e["generator"] == "map_update" and e["approval"] == "adopted"
          and e.get("replaced"))
    check("после adopt цель чистая", clean(bhp.diff(man, target)))

    # воспроизводимость
    out = os.path.join(tmp, "stage")
    bhp.materialize(man, out)
    check("сборка из хранилища - IDENTICAL с целью", clean(bhp.diff(man, out)) and bhp.hashes(out) == bhp.hashes(target))
    bhp.materialize(man, out)               # поверх прежней: ссылки только для чтения удаляются
    bhp.clean_out(out)
    check("повторная сборка и уборка: папки нет", not os.path.exists(out))
    blob = bhp.blob_path(man["files"]["UI/x.png"]["sha256"], "UI/x.png")
    try:
        with open(blob, "wb") as f:
            f.write(b"x")
        ro = False
    except PermissionError:
        ro = True
    check("блоб хранилища только для чтения", ro)
    os.chmod(blob, 0o666)
    os.remove(blob)
    try:
        bhp.materialize(man, os.path.join(tmp, "stage2"))
        check("контроль: без блоба сборка падает", False)
    except SystemExit:
        check("контроль: без блоба сборка падает", True)
finally:
    os.chdir(old_cwd)
    for d, _ds, fs in os.walk(tmp):
        for fn in fs:
            os.chmod(os.path.join(d, fn), 0o666)
    shutil.rmtree(tmp, ignore_errors=True)
print("итог: %s" % ("всё прошло" if not FAIL else "упало %d" % len(FAIL)))
sys.exit(1 if FAIL else 0)
