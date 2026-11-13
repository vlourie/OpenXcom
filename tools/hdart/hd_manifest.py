#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Инвентарь ассетов и манифест происхождения HD-пака (docs/HD_PIPELINE_V2.md, разделы 7-10, тесты T7, T8).

Отвечает на вопрос «откуда в игре этот файл» (семья граблей R-087: смотрим один файл, игра грузит другой).

  inventory - art/manifest/assets.json и assets.tsv: строка на кадр переписи (census/frames.tsv):
              логический ассет, семейство и связь (obj_families), тип по MCD (0 пол, 1-2 стена,
              3 предмет - MapData.h TilePart), составной, плитка, анимация, статус Pipeline v2 и что
              сейчас стоит в игре (путь, sha256, генератор по манифесту);
  build     - art/manifest/build_manifest.json: запись на КАЖДЫЙ файл мода hd, который читает игра
              (common.GAME_HD), с происхождением: журнал установки obj_push (push.tsv), учёт обновлений
              карт (map_update, updates.tsv), вывод obj_derive (derived.json), папки выходов генераторов
              и снимки поколений в art/_backup - по совпадению sha256. Не найдено нигде - generator
              unknown: честное «не знаем», а не догадка;
  verify    - ЦЕЛОСТНОСТЬ манифеста и мода игры: INTEGRITY PASS/FAIL. FAIL (код 1) - только поломка:
              MISSING (в манифесте есть, в игре нет), HASH_MISMATCH (файл изменён), UNKNOWN_FILE (в игре лишний),
              BAD_PATH (путь выхода не внутри мода), NO_BLOB (в хранилище нет блоба), MISSING_SOURCE (источник
              не найден), BROKEN_DEPENDENCY (derived_from указывает в пустоту). Устаревшее сюда не входит:
              одной строкой FRESHNESS CURRENT или STALE N (WARN). --release - ещё и stale 0 (выпуск игрокам);
  freshness - СВЕЖЕСТЬ: STALE_REVISION (ревизия семейства в манифесте старше текущей в families.json) и
              ORPHANED (семейства, по которому собран файл, больше нет - не «изменилось», а потеряло
              основание). Всегда код 0: это предупреждение. --release требует stale 0 и orphaned 0;
  status    - общая картина: Integrity, Current, Stale, Orphaned, Missing, Modified, Unknown и можно ли
              выпускать. Свежесть зависимостей приёмочной десятки проверяет acceptance_plan.py (входы asset_rev);
  show      - всё про один файл или кадр: py -3.13 tools/hdart/hd_manifest.py show FRNITURE:8

Статус (раздел 10) - состояние в Pipeline v2, а не то, что лежит в игре: identified (есть в переписи),
review_required (кандидат семейства на проверке), family_confirmed (канонический или прямой член).
Прежний пак v2 не утверждал, поэтому generated/derived/approved/installed появятся с первыми v2-ассетами.

    py -3.13 tools/hdart/hd_manifest.py build
    py -3.13 tools/hdart/hd_manifest.py inventory
    py -3.13 tools/hdart/hd_manifest.py verify
    py -3.13 tools/hdart/hd_manifest.py freshness
    py -3.13 tools/hdart/hd_manifest.py status
"""
import argparse
import csv
import hashlib
import json
import os
import sys
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.dirname(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

ENC = "utf-8-sig"
OUT = os.path.join("art", "manifest")
# папки с выходами генераторов: (глоб относительно корня, generator, generator_version). Порядок -
# старшинство при совпадении хэша: самое позднее и самое точное - раньше
SOURCES = [
    ("art/objects/series", "qwen21_strict", "obj_series"),
    ("art/objects/long", "long_object", "long_object"),
    ("art/objects/*photo*", "qwen21_photo", "obj_photo"),
    ("art/objects/*turbo*", "qwen21_turbo", "obj_photo --engine turbo"),
    ("art/objects/derive*", "derive", "obj_derive"),
    ("art/objects/recut*", "qwen21_strict", "obj_series --recut"),
    ("art/objects/probe5*", "probe", "probe_object"),
    ("art/maps/paint/series", "map_paint", "map_paint"),
    ("art/_backup/TERRAIN_lora_20260924_1353", "lora_oxcehd_v1", "gen_lora_batch 2026-09-24"),
    ("art/_backup/hd_TERRAIN_2026-09-22", "snapshot_g0922", "поколение 22.09 (merge_gens g0922), генератор не записан"),
    ("art/_backup/TERRAIN_before_lora_20260924_1057", "sdxl_legacy", "прежний пак до 2026-09-21 (gen_hd / build_pack)"),
    ("art/_backup/map_updates", "map_paint", "снимок обновлений карт"),
    ("art/_backup/TERRAIN_mod_20260925_0805", "unknown_pre0925",
     "был в игре на 2026-09-25 08:05 (снимок перед merge_gens), генератор не записан"),
]
PUSH = "art/_review/ours_vs_pack/push.tsv"
LEDGER = "art/maps/updates/updates.tsv"


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def walk(root):
    """{путь относительно root через /: полный путь} по всем файлам."""
    out = {}
    for d, _dirs, files in os.walk(root):
        for f in files:
            p = os.path.join(d, f)
            out[os.path.relpath(p, root).replace(os.sep, "/")] = p
    return out


def frame_of(rel):
    """'TERRAIN/FRNITURE.PCK/8.png' -> ('FRNITURE', 8); не кадр набора -> None."""
    parts = rel.split("/")
    if len(parts) >= 2 and parts[-2].upper().endswith(".PCK") and parts[-1].lower().endswith(".png"):
        stem = parts[-1][:-4]
        if stem.isdigit():
            return parts[-2][:-4].upper(), int(stem)
    return None


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


def load_families(path):
    fams = []
    if os.path.exists(path):
        with open(path, encoding=ENC) as f:
            fams = json.load(f)
    return fams


def family_index(fams):
    """{первый ключ строки очереди: (семейство, ревизия, связь, решение, член)}."""
    out = {}
    for fm in fams:
        for m in fm["members"]:
            out[m["keys"][0].upper()] = (fm, m, "member")
        for m in fm["review"]:
            out.setdefault(m["keys"][0].upper(), (fm, m, "review"))
    return out


# ------------------------------------------------------------------ build

def build(game, fams_path, out_dir, sources=None, push=PUSH, ledger=LEDGER, derived=()):
    """Манифест на каждый файл game. Возвращает dict и пишет build_manifest.json в out_dir."""
    sources = SOURCES if sources is None else sources
    files = walk(game)
    t0 = time.time()
    game_sha = {rel: sha256(p) for rel, p in files.items()}
    print("файлов в моде игры: %d, хэши за %.0f с" % (len(files), time.time() - t0), flush=True)
    by_sha = {}                             # sha -> (generator, version, source path, approved, extra)

    def claim(sha, rec):
        by_sha.setdefault(sha, rec)

    # 1. журнал установки предметов: принято Vitali в review.tsv (столбец «берём»). Папки-источники
    # потом переписывались (перевырезка obj_series --recut), поэтому по хэшу источника находится
    # мало - запись держится и по ПУТИ в игре: файл, который больше никто не опознал, - от установки
    push_by_path = {}
    if push and os.path.exists(push):
        with open(push, encoding=ENC, newline="") as f:
            for r in csv.DictReader(f, delimiter="\t"):
                src = r["источник"].replace("\\", "/")
                gen = next((g for pat, g, _v in sources if _match(src, pat)), "unknown")
                extra = {"push": r.get("почему", "")}
                if r.get("перевёрнут"):
                    extra["derived_from"] = src + " (перевёрнут)"
                push_by_path[("TERRAIN/%s.PCK/%s.png" % (r["набор"], r["кадр"])).upper()] =(gen, "obj_push", src, True, extra)
                if os.path.exists(src) and not r.get("перевёрнут"):
                    claim(sha256(src), (gen, "obj_push", src, True, extra))
    # 2. учёт обновлений карт: sha каждого файла, решение Vitali
    if ledger and os.path.exists(ledger):
        with open(ledger, encoding=ENC, newline="") as f:
            for r in csv.DictReader(f, delimiter="\t"):
                if r.get("sha"):
                    claim(r["sha"], ("map_paint", "map_update upd_%04d" % int(r["обновление"]), r["файл"],
                                     r.get("решение") == "принят", {"map": r.get("карта", ""),
                                                                    "decision": r.get("решение", "")}))
    # 3. вывод obj_derive: из чего, семейство, ревизия
    for dj in derived:
        if os.path.exists(dj):
            with open(dj, encoding=ENC) as f:
                for rel, r in json.load(f).items():
                    claim(r["sha256"], (r["generator"], "obj_derive", os.path.join(os.path.dirname(dj), rel), False,
                                        {"derived_from": r["derived_from"], "family": r["family"],
                                         "revision": r["revision"]}))
    # 4. папки выходов и снимки поколений
    import glob
    for pat, gen, ver in sources:
        for root in sorted(glob.glob(pat)):
            if not os.path.isdir(root):
                continue
            n = 0
            for rel, p in walk(root).items():
                if p.lower().endswith(".png"):
                    claim(sha256(p), (gen, ver, p.replace(os.sep, "/"), False, {}))
                    n += 1
            print("  источник %s: %d png" % (root, n), flush=True)

    fams = load_families(fams_path)
    fidx = family_index(fams)
    key_item = {}
    for fm in fams:
        for m in fm["members"] + fm["review"]:
            for k in m["keys"] + m["src"]:
                key_item.setdefault(k.upper(), m["keys"][0].upper())
    man = {}
    for rel, sha in sorted(game_sha.items()):
        fr = frame_of(rel)
        gen, ver, src, approved, extra = by_sha.get(sha, ("unknown", "", None, False, {}))
        pr = push_by_path.get(rel.upper())
        if pr and gen in ("unknown", "unknown_pre0925"):
            # поверх установки позже никто не писал (иначе хэш опознан бы), а источник с тех пор другой
            gen, ver, src, approved, extra = pr[0], pr[1], pr[2], pr[3], dict(pr[4], source_changed=True)
        e = {"sha256": sha, "kind": kind_of_path(rel), "generator": gen, "generator_version": ver,
             "source_path": src, "approved": approved,
             "approval": "Vitali" if approved else ("legacy" if gen != "unknown" else "unknown"),
             "created": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(os.path.getmtime(files[rel]))),
             "derived_from": extra.get("derived_from"), "source_frame": None, "asset_id": None,
             "family": None, "revision": None}
        if fr:
            key = "%s:%d" % fr
            e["source_frame"] = key
            item = key_item.get(key)
            if item and item in fidx:
                fm, _m, part = fidx[item]
                e["asset_id"] = fm["family_id"] if part == "member" else item
                e["family"] = fm["family_id"] if part == "member" else None
                e["revision"] = fm["revision"] if part == "member" else None
            else:
                e["asset_id"] = key
        if extra.get("family"):
            e["family"], e["revision"] = extra["family"], extra["revision"]
        for k in ("push", "map", "decision", "source_changed"):
            if extra.get(k):
                e[k] = extra[k]
        man[rel] = e
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "build_manifest.json"), "w", encoding=ENC) as f:
        json.dump({"game": os.path.abspath(game).replace(os.sep, "/"), "built": time.strftime("%Y-%m-%dT%H:%M:%S"),
                   "files": man}, f, ensure_ascii=False, indent=0, sort_keys=True)
    return man


def _match(path, pat):
    import fnmatch
    p = path.replace("\\", "/")
    return fnmatch.fnmatch(p, pat + "/*") or fnmatch.fnmatch(p, pat.rstrip("*") + "*")


# ------------------------------------------------------------------ verify

# Целостность - поломка установки или манифеста: вердикт FAIL, код 1. Свежесть - файл цел, но собран из
# входов старше текущих: WARN, verify не роняет (выпуск игрокам требует ещё и stale = 0, ключ --release)
INTEGRITY = ("MISSING", "HASH_MISMATCH", "UNKNOWN_FILE", "BAD_PATH", "NO_BLOB", "MISSING_SOURCE",
             "BROKEN_DEPENDENCY")
FRESHNESS = ("STALE_REVISION", "ORPHANED")
STORE = os.path.join("art", "store", "blobs")


def _exists_src(path, game):
    """source_path пишется от корня репозитория, а у журнала карт (map_update) - от корня мода."""
    return os.path.exists(path) or os.path.exists(os.path.join(os.path.dirname(os.path.normpath(game)), path))


def verify(game, manifest_path, fams_path, store=STORE):
    """(n_current, [(состояние, путь, пояснение)]). Состояния - INTEGRITY и FRESHNESS; целый и свежий файл не
    перечисляется, только счётчик. Хранилище блобов проверяется, если оно ведётся (store существует)."""
    with open(manifest_path, encoding=ENC) as f:
        man = json.load(f)["files"]
    cur = {fm["family_id"]: fm["revision"] for fm in load_families(fams_path)}
    files = walk(game)
    use_store = bool(store) and os.path.isdir(store)
    out, n_ok = [], 0
    for rel, e in sorted(man.items()):
        if os.path.isabs(rel) or ".." in rel.split("/") or "\\" in rel or ":" in rel:
            out.append(("BAD_PATH", rel, "путь выхода не относительный путь внутри мода"))
            continue
        if rel not in files:
            out.append(("MISSING", rel, "в манифесте есть, в игре нет"))
            continue
        sha = sha256(files[rel])
        if sha != e["sha256"]:
            out.append(("HASH_MISMATCH", rel, "в игре %s, в манифесте %s" % (sha[:12], e["sha256"][:12])))
            continue
        broken = False
        if use_store and not os.path.exists(os.path.join(store, sha[:2], sha + os.path.splitext(rel)[1])):
            out.append(("NO_BLOB", rel, "в хранилище нет блоба %s - сборщику не из чего собрать" % sha[:12]))
            broken = True
        if e.get("source_path") and not _exists_src(e["source_path"], game):
            out.append(("MISSING_SOURCE", rel, "источник %s не найден" % e["source_path"]))
            broken = True
        dep = (e.get("derived_from") or "").split(" (")[0]
        if dep and not os.path.exists(dep) and dep not in man:
            out.append(("BROKEN_DEPENDENCY", rel, "выведен из %s, а его нет" % dep))
            broken = True
        if broken:
            continue
        if e.get("family") and e["family"] not in cur:
            # не STALE: входы не «изменились», а основания больше нет - файл мог потерять смысл целиком
            out.append(("ORPHANED", rel, "семейства %s больше нет (переразбито) - файл собран по связи, "
                        "которой нет" % e["family"]))
        elif e.get("family") and e.get("revision") and cur[e["family"]] > e["revision"]:
            out.append(("STALE_REVISION", rel, "%s ревизия %d, текущая %d" % (e["family"], e["revision"],
                                                                              cur[e["family"]])))
        else:
            n_ok += 1
    for rel in sorted(set(files) - set(man)):
        out.append(("UNKNOWN_FILE", rel, "в игре есть, в манифесте нет"))
    return n_ok, out


def summary(n_ok, bad):
    """Сводка для status: целостность, свежих, устаревших и каждое состояние поломки."""
    c = Counter(s for s, _r, _w in bad)
    integ = sum(c[s] for s in INTEGRITY)
    return {"integrity": "PASS" if not integ else "FAIL", "current": n_ok,
            "stale": c["STALE_REVISION"], "orphaned": c["ORPHANED"],
            "missing": c["MISSING"], "modified": c["HASH_MISMATCH"], "unknown": c["UNKNOWN_FILE"],
            "other_integrity": {s: c[s] for s in INTEGRITY if s not in ("MISSING", "HASH_MISMATCH", "UNKNOWN_FILE")
                                and c[s]}}


# ------------------------------------------------------------------ inventory

def inventory(census, ground, items_path, fams_path, manifest_path, out_dir):
    fams = load_families(fams_path)
    fidx = family_index(fams)
    with open(items_path, encoding=ENC) as f:
        items = json.load(f)
    # кадр -> (первый ключ строки очереди, роль в строке, номер куска)
    role = {}
    for it in items:
        rep = it["keys"][0].upper()
        if it["kind"] == "составной":
            for i, k in enumerate(it["src"]):
                role.setdefault(k.upper(), (rep, "composite_part", i))
        else:
            for i, k in enumerate(it["keys"]):
                role.setdefault(k.upper(), (rep, "self" if i == 0 else "exact_duplicate", 0))
            if it["kind"] == "анимация":
                for k in it["frames"][1:]:
                    role.setdefault(k.upper(), (rep, "animation_frame", 0))
    mtype = {}
    if os.path.exists(ground):
        with open(ground, encoding=ENC, newline="") as f:
            for r in csv.DictReader(f, delimiter="\t"):
                mtype[(r["набор"][:-4].upper() if r["набор"].upper().endswith(".PCK") else r["набор"].upper(),
                       int(r["кадр"]))] = int(r["тип"])
    man = {}
    if os.path.exists(manifest_path):
        with open(manifest_path, encoding=ENC) as f:
            for rel, e in json.load(f)["files"].items():
                fr = frame_of(rel)
                if fr:
                    man[fr] = (rel, e)
    first_of_hash = {}
    rows = []
    with open(census, encoding=ENC, newline="") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            sec, s, fr = r["раздел"], r["набор"].upper(), int(r["кадр"])
            key = "%s:%d" % (s, fr)
            empty = r["пикселей"] == "0"
            dup_of = first_of_hash.setdefault((sec, r["точный"]), key)
            t = mtype.get((s, fr), -1)
            atype = {"TERRAIN": {0: "floor_material", 1: "wall", 2: "wall", 3: "object"}.get(t, "unknown"),
                     "UNITS": "unit"}.get(sec, "ui")
            rep, how, part = role.get(key, (None, "", 0))
            fam = fidx.get(rep) if rep else None
            relation, family_id, canonical, revision, status, review = "unknown", "", "", "", "identified", ""
            asset_id = dup_of
            if fam:
                fm, m, where = fam
                if where == "member":
                    family_id, canonical, revision = fm["family_id"], fm["canonical"], fm["revision"]
                    relation, asset_id, status, review = m["relation"], fm["family_id"], "family_confirmed", m["decision"]
                else:
                    relation, status, review = m["relation"], "review_required", m.get("reason", "")
                    asset_id = rep
            elif rep:
                asset_id = rep
            if how == "exact_duplicate" or (dup_of != key and how != "composite_part"):
                relation = "exact_duplicate"
            elif how == "animation_frame":
                relation = "animation_frame"
            rel, e = man.get((s, fr), (None, {}))
            rows.append({
                "frame_id": key, "section": sec, "set": s, "frame": fr, "asset_id": asset_id,
                "family_id": family_id, "canonical": canonical, "relation": relation, "asset_type": atype,
                "material": "", "view": "", "variant": relation if relation in ("recolor", "mirror") else "",
                "composite": ("part %d" % part) if how == "composite_part" else "",
                "tileable": (m.get("tile", "") if fam else ""), "animation": r.get("анимация", "") or (
                    "yes" if how == "animation_frame" else ""),
                "generator": e.get("generator", ""), "generator_version": e.get("generator_version", ""),
                "source_revision": revision, "status": "empty" if empty else status, "review_status": review,
                "output_path": rel or "", "output_hash": e.get("sha256", "")})
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "assets.json"), "w", encoding=ENC) as f:
        json.dump(rows, f, ensure_ascii=False, indent=0)
    cols = list(rows[0])
    with open(os.path.join(out_dir, "assets.tsv"), "w", encoding=ENC, newline="") as f:
        f.write("\t".join(cols) + "\n")
        for r in rows:
            f.write("\t".join(str(r[c]) for c in cols) + "\n")
    return rows


# ------------------------------------------------------------------ main

def main():
    import common
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("build", "verify", "freshness", "status", "inventory", "show"))
    ap.add_argument("--release", action="store_true",
                    help="verify/status: выпуск игрокам - кроме целостности требовать stale 0 и orphaned 0")
    ap.add_argument("what", nargs="?", default="", help="show: НАБОР:кадр или путь в моде")
    ap.add_argument("--game", default=os.path.join(common.GAME_HD, "hd"))
    ap.add_argument("--families", default="art/objects/families/families.json")
    ap.add_argument("--items", default="art/objects/discovery/items.json")
    ap.add_argument("--census", default="census/frames.tsv")
    ap.add_argument("--ground", default="census/ground.tsv")
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--bootstrap", action="store_true",
                    help="build: пересобрать манифест сканом игры, хотя хранилище уже ведётся")
    a = ap.parse_args()
    mpath = os.path.join(a.out, "build_manifest.json")
    if a.cmd == "build" and os.path.isdir(os.path.join("art", "store", "blobs")) and not a.bootstrap \
            and os.path.abspath(a.out) == os.path.abspath(OUT):
        # с появлением хранилища манифест - желаемое состояние, а игра - выход (build_hd_pack.py). Скан игры
        # переписал бы его тем, что сейчас лежит в папке, включая записанное мимо сборщика
        raise SystemExit("манифест ведёт build_hd_pack.py: скан игры его не переписывает. Записанное мимо - "
                         "build_hd_pack.py adopt --changed --by <инструмент>; пересканировать всё - --bootstrap")
    if a.cmd == "build":
        import glob
        man = build(a.game, a.families, a.out, derived=glob.glob("art/objects/*/derived.json"))
        g = Counter((e["kind"], e["generator"]) for e in man.values())
        for (k, gen), n in sorted(g.items(), key=lambda kv: (kv[0][0], -kv[1])):
            print("%-8s %-16s %6d" % (k, gen, n))
        print("записей: %d -> %s" % (len(man), mpath))
    elif a.cmd in ("verify", "freshness", "status"):
        n_ok, bad = verify(a.game, mpath, a.families)
        s = summary(n_ok, bad)
        integ = [b for b in bad if b[0] in INTEGRITY]
        fresh = [b for b in bad if b[0] in FRESHNESS]
        n_old = s["stale"] + s["orphaned"]
        if a.cmd == "verify":
            for st, rel, why in integ[:40]:
                print("%-17s %s  %s" % (st, rel, why))
            print("INTEGRITY: %s  (%s)" % (s["integrity"], ", ".join(
                "%s %d" % kv for kv in Counter(b[0] for b in integ).most_common()) or "поломок нет"))
            print("FRESHNESS: %s" % ("CURRENT" if not n_old else
                                     "WARN - stale %d, orphaned %d (не ошибка целостности; подробно: freshness)"
                                     % (s["stale"], s["orphaned"])))
        elif a.cmd == "freshness":
            for st, rel, why in fresh[:40]:
                print("%-15s %s  %s" % (st, rel, why))
            fams = Counter(b[2].split(" ")[0] for b in fresh if b[0] == "STALE_REVISION")
            print("семейств с устаревшими файлами: %d; больше всего: %s" % (
                len(fams), ", ".join("%s %d" % kv for kv in fams.most_common(8))))
            print("FRESHNESS: %s  (STALE %d - входы изменились; ORPHANED %d - семейства, из которого собран файл, "
                  "больше нет)" % ("CURRENT" if not n_old else "WARN", s["stale"], s["orphaned"]))
            sys.exit(0)                     # свежесть - предупреждение, а не поломка
        else:
            print("Integrity   %s" % s["integrity"])
            for k, label in (("current", "Current"), ("stale", "Stale"), ("orphaned", "Orphaned"),
                             ("missing", "Missing"), ("modified", "Modified"), ("unknown", "Unknown")):
                print("%-11s %d" % (label, s[k]))
            for k, v in s["other_integrity"].items():
                print("%-11s %d" % (k, v))
            print("выпуск игрокам: %s" % ("можно" if s["integrity"] == "PASS" and not n_old else
                                         "нельзя - нужны integrity PASS, stale 0 и orphaned 0"))
        fail = s["integrity"] != "PASS" or (a.release and n_old)
        sys.exit(1 if fail else 0)
    elif a.cmd == "inventory":
        rows = inventory(a.census, a.ground, a.items, a.families, mpath, a.out)
        for col in ("asset_type", "status", "relation", "generator"):
            print("%s: %s" % (col, ", ".join("%s %d" % kv for kv in Counter(r[col] for r in rows).most_common(8))))
        print("кадров: %d, логических ассетов: %d -> %s" % (len(rows), len({r["asset_id"] for r in rows}),
                                                            os.path.join(a.out, "assets.tsv")))
    else:
        with open(mpath, encoding=ENC) as f:
            man = json.load(f)["files"]
        key = a.what.upper()
        hits = {rel: e for rel, e in man.items() if rel.upper() == key or e.get("source_frame") == key}
        ipath = os.path.join(a.out, "assets.json")
        inv = []
        if os.path.exists(ipath):
            with open(ipath, encoding=ENC) as f:
                inv = [r for r in json.load(f) if r["frame_id"] == key or r["output_path"].upper() == key]
        for rel, e in hits.items():
            print("файл игры: %s" % rel)
            for k in ("asset_id", "family", "revision", "generator", "generator_version", "source_path",
                      "derived_from", "approved", "approval", "created", "sha256"):
                print("  %-18s %s" % (k, e.get(k)))
        for r in inv:
            print("инвентарь: %s" % json.dumps(r, ensure_ascii=False))
        if not hits and not inv:
            print("нет ни в манифесте, ни в инвентаре: %s" % a.what)
            sys.exit(1)


if __name__ == "__main__":
    main()
