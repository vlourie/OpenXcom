#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Детерминированная сборка HD-пака из манифеста (Pipeline v2, P1-A; семья граблей R-087).

Папка мода hd в игре - только ВЫХОД. Что в ней лежит, решает манифест art/manifest/build_manifest.json
(путь в моде -> sha256 и происхождение), а байты берутся из хранилища по хэшу art/store/blobs/<aa>/<sha>.
Руками и чужими скриптами в папку пака не пишут: .claude/hooks/pack-guard.ps1 не даёт скопировать туда
файл, guard-paths.ps1 - записать инструментом.

  import  - один раз: положить в хранилище байты всех файлов манифеста (из source_path, если хэш тот же,
            иначе из текущей игры). Файл, чей хэш не сходится ни там ни там, - MISSING, код 1;
  build   - собрать пак в --out (по умолчанию art/_staging_hd) из манифеста и хранилища и сравнить с игрой:
            IDENTICAL - сборка воспроизводит установленный пак байт в байт;
  status  - расхождение цели (--target game|repo) с манифестом: MISSING, CHANGED, EXTRA. Код 1, если есть;
  install - привести цель к манифесту: недостающее и изменённое переписать из хранилища, лишнее - в
            art/_backup/pack_extra_<время> (не удаляется). Нужен --yes; --only <путь>... - только эти;
  adopt   - принять в манифест то, что в цель записали мимо сборщика (прежние инструменты: map_update,
            map_pick, merge_gens...): --changed или пути, --by <инструмент> обязателен. Это запись
            происхождения, а не обход: «кто записал» остаётся в манифесте и в журнале. Только человек
            (P1-B): нужен терминал и ответ «принимаю», из скрипта и от агента - отказ.
Прежние прямые писатели (LEGACY_DIRECT_WRITERS) не переделаны: всё, что они пишут в пак, status
показывает как НЕПРИНЯТЫЕ ИЗМЕНЕНИЯ (unadopted modification), пока человек не сделает adopt.

Для скриптов: stage(man, rel, png_bytes_or_path, **происхождение) + save(man) + install(target, only=[...]).
Каждое сохранение манифеста кладёт прежний в art/manifest/history - откат = вернуть файл и install.

    py -3.13 tools/hdart/build_hd_pack.py import
    py -3.13 tools/hdart/build_hd_pack.py build
    py -3.13 tools/hdart/build_hd_pack.py status
    py -3.13 tools/hdart/build_hd_pack.py install --yes
"""
import argparse
import hashlib
import json
import os
import shutil
import stat
import sys
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.dirname(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import common                                        # noqa: E402

ENC = "utf-8-sig"
STORE = os.path.join("art", "store", "blobs")
MANIFEST = os.path.join("art", "manifest", "build_manifest.json")
HISTORY = os.path.join("art", "manifest", "history")
LOG = os.path.join("art", "manifest", "pack_log.tsv")
STAGING = os.path.join("art", "_staging_hd")
# пишут в папку пака напрямую, мимо манифеста; не переделаны (P1-B) - их след в status как непринятое
LEGACY_DIRECT_WRITERS = ("map_update.py", "map_pick.py", "merge_gens.py", "optimize_hd.py")
TARGETS = {"game": os.path.join(common.GAME_HD, "hd"), "repo": os.path.join("user", "mods", "hd", "hd")}


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def ext_of(rel):
    e = os.path.splitext(rel)[1].lower()
    return e if e and len(e) <= 6 else ".bin"


def blob_path(sha, rel):
    return os.path.join(STORE, sha[:2], sha + ext_of(rel))


def walk(root):
    out = {}
    for d, _dirs, files in os.walk(root):
        for f in files:
            p = os.path.join(d, f)
            out[os.path.relpath(p, root).replace(os.sep, "/")] = p
    return out


def kind_of_path(rel):
    top = rel.split("/")[0]
    if top == "TERRAIN":
        return "terrain"
    if top in ("UI", "UI_esrgan"):
        return "pedia" if "pedia" in rel.lower() else "ui"
    if top == "FX":
        return "fx"
    if top.upper().endswith(".PCK"):
        return "unit"
    return "unknown"


# ------------------------------------------------------------------ хранилище и манифест

def _put(src_path, data, sha, rel):
    """Блоб в хранилище: пишется во временный файл и переименовывается, потом только чтение."""
    dst = blob_path(sha, rel)
    if os.path.exists(dst):
        return dst
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    tmp = dst + ".tmp%d" % os.getpid()
    if data is not None:
        with open(tmp, "wb") as f:
            f.write(data)
    else:
        shutil.copyfile(src_path, tmp)
    if sha256_file(tmp) != sha:
        os.remove(tmp)
        raise SystemExit("хранилище: байты %s не сходятся с хэшем %s" % (src_path or rel, sha[:12]))
    os.replace(tmp, dst)
    os.chmod(dst, stat.S_IREAD)                       # блоб неизменен: запись поверх - ошибка, а не порча
    return dst


def put(obj, rel):
    """obj - путь к файлу или байты -> sha256; блоб в хранилище."""
    if isinstance(obj, (bytes, bytearray)):
        sha = hashlib.sha256(obj).hexdigest()
        _put(None, bytes(obj), sha, rel)
    else:
        sha = sha256_file(obj)
        _put(obj, None, sha, rel)
    return sha


def load(path=MANIFEST):
    with open(path, encoding=ENC) as f:
        return json.load(f)


def manifest_hash(man):
    h = hashlib.sha256()
    for rel in sorted(man["files"]):
        h.update(("%s\t%s\n" % (rel, man["files"][rel]["sha256"])).encode("utf-8"))
    return h.hexdigest()[:16]


def save(man, path=MANIFEST, why=""):
    """Прежний манифест - в history (откат), новый - атомарно."""
    if os.path.exists(path):
        os.makedirs(HISTORY, exist_ok=True)
        shutil.copyfile(path, os.path.join(HISTORY, "build_manifest_%s.json" % time.strftime("%Y%m%d_%H%M%S")))
    man["built"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    man["manifest_hash"] = manifest_hash(man)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding=ENC) as f:
        json.dump(man, f, ensure_ascii=False, indent=0, sort_keys=True)
    os.replace(tmp, path)
    log("save", "", man["manifest_hash"], why)


def stage(man, rel, obj, **prov):
    """Новый файл пака: байты (или путь) в хранилище, запись в манифест с происхождением. Не пишет в игру."""
    rel = rel.replace(os.sep, "/")
    sha = put(obj, rel)
    old = man["files"].get(rel, {})
    e = {"sha256": sha, "kind": kind_of_path(rel), "generator": "unknown", "generator_version": "",
         "source_path": None, "approved": False, "approval": "unknown", "derived_from": None,
         "source_frame": old.get("source_frame"), "asset_id": old.get("asset_id"), "family": old.get("family"),
         "revision": old.get("revision"), "created": time.strftime("%Y-%m-%dT%H:%M:%S")}
    e.update(prov)
    e["sha256"] = sha
    if old.get("sha256") and old["sha256"] != sha:
        e["replaced"] = old["sha256"]
    man["files"][rel] = e
    return sha


def log(action, rel, sha, note=""):
    new = not os.path.exists(LOG)
    with open(LOG, "a", encoding=ENC if new else "utf-8", newline="") as f:
        if new:
            f.write("когда\tдействие\tпуть\tsha\tзаметка\n")
        f.write("\t".join([time.strftime("%Y-%m-%d %H:%M:%S"), action, rel, sha[:16], note.replace("\t", " ")]) + "\n")


# ------------------------------------------------------------------ сравнение цели с манифестом

def hashes(root, cache_name=None):
    """{rel: sha} по всем файлам root; хэш пересчитывается, только если размер или время изменились."""
    cache, cpath = {}, None
    if cache_name:
        cpath = os.path.join("art", "manifest", "stat_%s.json" % cache_name)
        if os.path.exists(cpath):
            with open(cpath, encoding=ENC) as f:
                cache = json.load(f)
    out, fresh = {}, {}
    for rel, p in walk(root).items():
        st = os.stat(p)
        c = cache.get(rel)
        if c and c[0] == st.st_size and c[1] == st.st_mtime_ns:
            out[rel] = c[2]
        else:
            out[rel] = sha256_file(p)
        fresh[rel] = [st.st_size, st.st_mtime_ns, out[rel]]
    if cpath:
        with open(cpath, "w", encoding=ENC) as f:
            json.dump(fresh, f)
    return out


def diff(man, root, cache_name=None):
    have = hashes(root, cache_name) if os.path.isdir(root) else {}
    want = {rel: e["sha256"] for rel, e in man["files"].items()}
    res = {"MISSING": sorted(set(want) - set(have)), "EXTRA": sorted(set(have) - set(want)),
           "CHANGED": sorted(r for r in set(want) & set(have) if want[r] != have[r])}
    res["MATCH"] = len(set(want) & set(have)) - len(res["CHANGED"])
    return res


def report(res, label, show=8):
    bad = sum(len(res[k]) for k in ("MISSING", "CHANGED", "EXTRA"))
    print("%s: совпало %d; нет %d, изменено %d, лишних %d -> %s"
          % (label, res["MATCH"], len(res["MISSING"]), len(res["CHANGED"]), len(res["EXTRA"]),
             "IDENTICAL" if not bad else "DIFFERENT"))
    for k in ("MISSING", "CHANGED", "EXTRA"):
        for rel in res[k][:show]:
            print("  %-8s %s" % (k, rel))
        if len(res[k]) > show:
            print("  %-8s ... ещё %d" % (k, len(res[k]) - show))
    return bad


# ------------------------------------------------------------------ команды

def cmd_import(man, game):
    need = [(rel, e) for rel, e in sorted(man["files"].items()) if not os.path.exists(blob_path(e["sha256"], rel))]
    print("в манифесте %d файлов, в хранилище нет %d" % (len(man["files"]), len(need)), flush=True)
    miss, n, t0 = [], 0, time.time()
    for rel, e in need:
        got = False
        for src in (e.get("source_path"), os.path.join(game, rel)):
            if src and os.path.exists(src) and sha256_file(src) == e["sha256"]:
                _put(src, None, e["sha256"], rel)
                got = True
                break
        if not got:
            miss.append(rel)
        n += 1
        if n % 5000 == 0:
            print("  %d из %d, %.0f с" % (n, len(need), time.time() - t0), flush=True)
    for rel in miss[:20]:
        print("  MISSING  %s: байтов с хэшем манифеста нет ни в source_path, ни в игре" % rel)
    print("положено %d, не найдено %d" % (len(need) - len(miss), len(miss)))
    return 1 if miss else 0


def unlink_ro(p):
    """Удалить файл сборки. Жёсткая ссылка делит с блобом атрибут «только чтение», и Windows её не
    удаляет: атрибут снимается - и с блоба тоже, поэтому после серии удалений зовётся protect_store."""
    os.chmod(p, stat.S_IWRITE)
    os.remove(p)


def protect_store():
    """Вернуть «только чтение» всем блобам хранилища (после unlink_ro)."""
    for d, _ds, fs in os.walk(STORE):
        for fn in fs:
            os.chmod(os.path.join(d, fn), stat.S_IREAD)


def clean_out(out):
    """Убрать папку сборки; блобы остаются и снова только для чтения."""
    for p in walk(out).values():
        unlink_ro(p)
    shutil.rmtree(out)
    protect_store()


def materialize(man, out, link=True):
    """Пак из хранилища в out; link - жёсткие ссылки (быстро, для проверки), иначе копии."""
    have = walk(out) if os.path.isdir(out) else {}
    touched = False
    for rel in sorted(set(have) - set(man["files"])):
        unlink_ro(have[rel])
        touched = True
    for rel, e in sorted(man["files"].items()):
        src = blob_path(e["sha256"], rel)
        if not os.path.exists(src):
            if touched:
                protect_store()
            raise SystemExit("нет блоба %s для %s - сначала import" % (e["sha256"][:12], rel))
        dst = os.path.join(out, rel)
        if os.path.exists(dst):
            unlink_ro(dst)
            touched = True
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if link:
            try:
                os.link(src, dst)
                continue
            except OSError:
                pass
        shutil.copyfile(src, dst)
    if touched:
        protect_store()


def install(man, target, only=None, backup=None):
    """Цель к манифесту. only - только эти пути (лишнее тогда не трогается). -> число изменённых файлов."""
    root = TARGETS.get(target, target)
    res = diff(man, root, target if target in TARGETS else None)
    todo = res["MISSING"] + res["CHANGED"]
    extra = res["EXTRA"]
    if only is not None:
        only = {r.replace(os.sep, "/") for r in only}
        todo = [r for r in todo if r in only]
        extra = []
    backup = backup or os.path.join("art", "_backup", "pack_extra_" + time.strftime("%Y%m%d_%H%M%S"))
    for rel in todo:
        dst = os.path.join(root, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        tmp = dst + ".hdtmp"
        shutil.copyfile(blob_path(man["files"][rel]["sha256"], rel), tmp)   # копия, не ссылка: блоб неизменен
        os.replace(tmp, dst)
        log("install:" + target, rel, man["files"][rel]["sha256"])
    for rel in extra:
        b = os.path.join(backup, target, rel)
        os.makedirs(os.path.dirname(b), exist_ok=True)
        shutil.move(os.path.join(root, rel), b)
        log("extra->backup:" + target, rel, "", b)
    if todo or extra:
        with open(os.path.join("art", "manifest", "installed_%s.json" % target), "w", encoding=ENC) as f:
            json.dump({"target": os.path.abspath(root), "manifest_hash": manifest_hash(man),
                       "when": time.strftime("%Y-%m-%dT%H:%M:%S"), "written": len(todo), "moved_extra": len(extra),
                       "backup": backup if extra else None}, f, ensure_ascii=False, indent=1)
    return len(todo) + len(extra)


def adopt(man, target, paths, by, note):
    root = TARGETS.get(target, target)
    n = 0
    for rel in paths:
        p = os.path.join(root, rel)
        if not os.path.exists(p):
            print("  нет файла %s - пропущено" % rel)
            continue
        stage(man, rel, p, generator=by, generator_version="adopt", source_path=None, approved=False,
              approval="adopted", adopted=time.strftime("%Y-%m-%dT%H:%M:%S"), adopt_note=note)
        log("adopt:" + by, rel, man["files"][rel]["sha256"], note)
        n += 1
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("import", "build", "status", "install", "adopt"))
    ap.add_argument("paths", nargs="*", help="adopt: пути в моде (TERRAIN/X.PCK/1.png)")
    ap.add_argument("--target", default="game", help="game (установка Пираток) | repo (user/mods/hd) | папка")
    ap.add_argument("--out", default=STAGING)
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--changed", action="store_true", help="adopt: всё изменённое и лишнее в цели")
    ap.add_argument("--by", default="", help="adopt: каким инструментом записано")
    ap.add_argument("--note", default="")
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--keep", action="store_true", help="build: не убирать собранную папку")
    a = ap.parse_args()
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")
    man = load()
    if a.cmd == "import":
        return cmd_import(man, TARGETS["game"])
    if a.cmd == "build":
        t0 = time.time()
        materialize(man, a.out, link=True)
        bad = report(diff(man, a.out), "сборка %s против манифеста (%.0f с)" % (a.out, time.time() - t0))
        bad += report(diff(man, TARGETS["game"], "game"), "игра против манифеста")
        if not bad:
            print("IDENTICAL: сборка из манифеста воспроизводит установленный пак (%d файлов, манифест %s)"
                  % (len(man["files"]), manifest_hash(man)))
        if not a.keep:
            clean_out(a.out)              # папка сборки - жёсткие ссылки на блобы; сами блобы остаются
        return 1 if bad else 0
    if a.cmd == "status":
        res = diff(man, TARGETS.get(a.target, a.target), a.target)
        bad = report(res, "цель " + a.target)
        unadopted = len(res["CHANGED"]) + len(res["EXTRA"])
        if unadopted:
            print("НЕПРИНЯТЫЕ ИЗМЕНЕНИЯ (unadopted modification): %d файлов в цели записаны мимо сборщика - "
                  "прежние прямые писатели (LEGACY_DIRECT_WRITER: %s) или руками. В манифест их принимает только "
                  "человек: adopt --by <инструмент>; вернуть пак к манифесту - install --yes"
                  % (unadopted, ", ".join(LEGACY_DIRECT_WRITERS)))
        return 1 if bad else 0
    if a.cmd == "install":
        if not a.yes:
            report(diff(man, TARGETS.get(a.target, a.target), a.target), "будет приведено: " + a.target)
            print("проба: добавь --yes")
            return 0
        n = install(man, a.target, a.only)
        print("записано и убрано файлов: %d" % n)
        return 1 if report(diff(man, TARGETS.get(a.target, a.target), a.target), "после установки") and a.only is None else 0
    if a.cmd == "adopt":
        if not a.by:
            raise SystemExit("adopt: --by <инструмент> обязателен - происхождение не пишется пустым")
        paths = a.paths
        if a.changed:
            res = diff(man, TARGETS.get(a.target, a.target), a.target)
            paths = res["CHANGED"] + res["EXTRA"]
        # P1-B: adopt - только явная операция человека. Скрипт и агент идут без терминала - им отказ;
        # ключа, который снимает вопрос, нет нарочно
        if not sys.stdin.isatty():
            raise SystemExit("adopt: только человек в терминале - принять %d файлов от %s. Запусти сам в консоли"
                             % (len(paths), a.by))
        for rel in paths[:20]:
            print("  принять: %s" % rel)
        if input("принять в манифест %d файлов как записанные %s? впиши «принимаю»: "
                 % (len(paths), a.by)).strip() != "принимаю":
            print("не принято")
            return 1
        n = adopt(man, a.target, paths, a.by, a.note)
        if n:
            save(man, why="adopt %d от %s" % (n, a.by))
        print("принято в манифест: %d" % n)
        return 0


if __name__ == "__main__":
    sys.exit(main())
