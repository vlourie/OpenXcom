#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hd_manifest: происхождение файла игры и сверка установки (docs/HD_PIPELINE_V2.md, тесты T7 и T8).

Синтетический мод из четырёх кадров, без установки Пираток:
  * T7: файл, совпавший с папкой генератора, получает её generator, семейство и ревизию;
  * установленный из журнала push.tsv, у которого источник потом переписан, - всё равно от установки,
    с пометкой source_changed; не найденный нигде - unknown, а не догадка;
  * T8: подменённый файл - HASH_MISMATCH; лишний - UNKNOWN_FILE; удалённый - MISSING;
    семейство с новой ревизией - STALE_REVISION; нетронутая установка - всё MATCH;
  * целостность отдельно от свежести: только устаревшее - integrity PASS (STALE - WARN), переразбитое
    семейство - ORPHANED (не STALE); нет блоба в хранилище и пропавший источник - FAIL.

    py -3.13 tools/test_hd_manifest.py
"""
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "hdart"))

import hd_manifest as hm                # noqa: E402

FAIL = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        FAIL.append(name)


def put(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


tmp = tempfile.mkdtemp(prefix="hdman_")
try:
    game = os.path.join(tmp, "game")
    src = os.path.join(tmp, "gen_a")
    out = os.path.join(tmp, "manifest")
    put(os.path.join(game, "TERRAIN", "SET.PCK", "0.png"), b"frame zero")
    put(os.path.join(game, "TERRAIN", "SET.PCK", "1.png"), b"pushed then source recut")
    put(os.path.join(game, "TERRAIN", "SET.PCK", "2.png"), b"nobody knows")
    put(os.path.join(src, "SET.PCK", "0.png"), b"frame zero")
    put(os.path.join(src, "SET.PCK", "1.png"), b"recut later - other bytes")
    push = os.path.join(tmp, "push.tsv")
    with open(push, "w", encoding=hm.ENC) as f:
        f.write("набор\tкадр\tисточник\tперевёрнут\tпочему\n")
        f.write("SET\t1\t%s\t\tstrict #1\n" % os.path.join(src, "SET.PCK", "1.png").replace(os.sep, "/"))
    fams = os.path.join(tmp, "families.json")
    fam = [{"family_id": "SET:0", "revision": 1, "members": [
        {"keys": ["SET:0"], "src": ["SET:0"], "relation": "canonical", "decision": "AUTO"}], "review": []}]
    with open(fams, "w", encoding=hm.ENC) as f:
        json.dump(fam, f)
    sources = [(src.replace(os.sep, "/"), "gen_a", "v1")]
    man = hm.build(game, fams, out, sources=sources, push=push, ledger=None)
    e0, e1, e2 = (man["TERRAIN/SET.PCK/%d.png" % i] for i in range(3))
    check("T7: кадр из папки генератора опознан", e0["generator"] == "gen_a" and e0["source_path"].endswith("0.png"))
    check("T7: семейство и ревизия записаны", e0["family"] == "SET:0" and e0["revision"] == 1)
    check("T7: sha256 записан", e0["sha256"] == hm.sha256(os.path.join(game, "TERRAIN", "SET.PCK", "0.png")))
    check("журнал установки: источник переписан - всё равно от установки",
          e1["generator"] == "gen_a" and e1["approved"] and e1.get("source_changed") is True)
    check("не найден нигде - unknown", e2["generator"] == "unknown" and e2["approval"] == "unknown")

    mpath = os.path.join(out, "build_manifest.json")
    n_ok, bad = hm.verify(game, mpath, fams, store=None)
    check("нетронутая установка - всё MATCH", n_ok == 3 and not bad)

    # свежесть отдельно от целостности: новая ревизия семейства - STALE (WARN), integrity PASS
    fam[0]["revision"] = 2
    with open(fams, "w", encoding=hm.ENC) as f:
        json.dump(fam, f)
    n_ok, bad = hm.verify(game, mpath, fams, store=None)
    s = hm.summary(n_ok, bad)
    check("только устаревшее - integrity PASS, stale 1, current 2",
          s["integrity"] == "PASS" and s["stale"] == 1 and s["current"] == 2)
    with open(fams, "w", encoding=hm.ENC) as f:
        json.dump([], f)
    n_ok, bad = hm.verify(game, mpath, fams, store=None)
    s = hm.summary(n_ok, bad)
    check("семейство переразбито - ORPHANED отдельно от STALE, integrity PASS",
          s["integrity"] == "PASS" and s["orphaned"] == 1 and s["stale"] == 0)
    # хранилище ведётся, а блоба нет - поломка; источник пропал - поломка
    store = os.path.join(tmp, "store")
    os.makedirs(store)
    n_ok, bad = hm.verify(game, mpath, fams, store=store)
    check("нет блоба в хранилище - NO_BLOB, integrity FAIL",
          hm.summary(n_ok, bad)["integrity"] == "FAIL" and sum(1 for b in bad if b[0] == "NO_BLOB") == 3)
    os.remove(os.path.join(src, "SET.PCK", "0.png"))
    n_ok, bad = hm.verify(game, mpath, fams, store=None)
    check("источник пропал - MISSING_SOURCE", [b[0] for b in bad if b[1].endswith("0.png")] == ["MISSING_SOURCE"])
    put(os.path.join(src, "SET.PCK", "0.png"), b"frame zero")

    put(os.path.join(game, "TERRAIN", "SET.PCK", "1.png"), b"hand-swapped file")
    put(os.path.join(game, "TERRAIN", "SET.PCK", "3.png"), b"extra")
    os.remove(os.path.join(game, "TERRAIN", "SET.PCK", "2.png"))
    fam[0]["revision"] = 2
    with open(fams, "w", encoding=hm.ENC) as f:
        json.dump(fam, f)
    n_ok, bad = hm.verify(game, mpath, fams, store=None)
    got = {rel.split("/")[-1]: s for s, rel, _w in bad}
    check("T8: подменённый файл - HASH_MISMATCH", got.get("1.png") == "HASH_MISMATCH")
    check("лишний файл - UNKNOWN_FILE", got.get("3.png") == "UNKNOWN_FILE")
    check("удалённый файл - MISSING", got.get("2.png") == "MISSING")
    check("новая ревизия семейства - STALE_REVISION", got.get("0.png") == "STALE_REVISION")
    check("MATCH не осталось", n_ok == 0)
    check("поломки - integrity FAIL, устаревшее посчитано отдельно",
          hm.summary(n_ok, bad)["integrity"] == "FAIL" and hm.summary(n_ok, bad)["stale"] == 1)
finally:
    shutil.rmtree(tmp, ignore_errors=True)
print("итог: %s" % ("всё прошло" if not FAIL else "упало %d" % len(FAIL)))
sys.exit(1 if FAIL else 0)
