#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Файл обновления на одну карту: что нарисовано для неё и ещё никуда не выдавалось.

Рисуем по картам (map_paint.py), выдаём тоже по картам: карта готова - файл обновления. Кадр
набора стоит на многих картах, а папка прогона (--root) у всех карт общая, поэтому в обновление
карты идут только кадры, которых не было ни в одном прошлом обновлении или которые с тех пор
перерисованы. Первое обновление карты - «карта», следующие - «исправление».

В мод ничего не пишется, пока Vitali не выбрал (accept/reject), и только командой apply.
Рядом с каждым кадром - прежний кадр мода и мерки брака обоих (score_batch.score_frame, R-061):
новое не кладётся поверх старого вслепую. Мерки - только отсев явного брака; решает лист (R-066).

    py tools\hdart\map_update.py pack --terrain CULTA_UBER --block CULTAFARM01 --root art\maps\paint\CULTA_UBER_t17
    py tools\hdart\map_update.py accept 3                  всё обновление 3
    py tools\hdart\map_update.py reject 3 --frames BARN:7,BARN:8
    py tools\hdart\map_update.py apply 3 --mod <мод hd>    принятое - в мод, заменённое - в art\_backup
    py tools\hdart\map_update.py status                    пересчитать docs\MAP_STATUS.md

Учёт - art\maps\updates\updates.tsv, строка на файл. Дорожная карта карт - docs\MAP_STATUS.md,
она каждый раз считается из учёта заново, руками не правится.
"""
import argparse
import datetime
import hashlib
import json
import os
import shutil
import sys
import zipfile
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
for p in (HERE, os.path.dirname(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np                                      # noqa: E402
from PIL import Image, ImageDraw                        # noqa: E402

ENC = "utf-8-sig"
OUT = os.path.join("art", "maps", "updates")
LEDGER = os.path.join(OUT, "updates.tsv")
STATUS = os.path.join("docs", "MAP_STATUS.md")
MOD = os.path.join("Пиратки", "Dioxine_XPiratez", "user", "mods", "hd")
BACKUP = os.path.join("art", "_backup", "map_updates")
FIELDS = ["обновление", "вид", "дата", "террейн", "карта", "набор", "кадр", "файл", "sha", "был_sha",
          "что", "в_моде", "годен", "флаги", "годен_мод", "флаги_мод", "решение"]
# пороги мерок - умолчания build_dataset.py и score_batch.py, чтобы приёмка карты шла теми же мерками
SCORE_ARGS = SimpleNamespace(max_spill=0.03, max_miss=0.05, min_corr=0.70, max_sat=0.10, det_lo=0.0, det_hi=1.60,
                             min_iou=0.90, min_iou_object=0.70, flat_low=2.0, wave=3.5, min_low_ratio=0.45,
                             max_tone=45.0)
DARK = (28, 26, 24)     # тёмный пол боя: остаток подложки на шахматке не виден (R-041)


# ------------------------------------------------------------------ учёт

def read_ledger():
    if not os.path.exists(LEDGER):
        return []
    with open(LEDGER, encoding=ENC) as f:
        head = f.readline().rstrip("\n").split("\t")
        return [dict(zip(head, ln.rstrip("\n").split("\t"))) for ln in f if ln.strip()]


def write_ledger(rows):
    os.makedirs(OUT, exist_ok=True)
    tmp = LEDGER + ".tmp"
    with open(tmp, "w", encoding=ENC) as f:
        f.write("\t".join(FIELDS) + "\n")
        for r in rows:
            f.write("\t".join(str(r.get(k, "")).replace("\t", " ") for k in FIELDS) + "\n")
    os.replace(tmp, LEDGER)


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def upd_name(n, terrain, block):
    return "upd_%04d_%s_%s" % (n, terrain, block)


# ------------------------------------------------------------------ кадры карты

def map_frames(world, terrain, block):
    """{набор: {кадр}} - всё, что карта может показать: кадры записей со всеми фазами анимации,
    обломки и открытые двери по цепочке (die/alt), как их рисует map_paint (R-071)."""
    import map_paint as mp
    name = {x.upper(): x for x in world.sets_of(terrain)}
    _im, _o, inst = mp.layout(world, terrain, block)
    out = {}
    seen = set()
    for d in inst:
        s = d["set"]
        chain = [d["rec"]]
        recs = world.records(name.get(s, s))
        while chain:
            r = chain.pop()
            if (s, r) in seen or r >= len(recs):
                continue
            seen.add((s, r))
            out.setdefault(s, set()).update(recs[r]["frames"])
            for nxt in (recs[r]["die"], recs[r]["alt"]):
                if nxt:
                    chain.append(nxt)
    return out


def files_of(root, s, f):
    """Клетка кадра и её варианты пола <кадр>.v<n>.png - как их ищет движок, без пропусков."""
    d = os.path.join(root, s + ".PCK")
    main = os.path.join(d, "%d.png" % f)
    if not os.path.exists(main):
        return []
    out = [main]
    v = 1
    while os.path.exists(os.path.join(d, "%d.v%d.png" % (f, v))):
        out.append(os.path.join(d, "%d.v%d.png" % (f, v)))
        v += 1
    return out


def mod_dir(mod, s):
    """Папка набора в моде - с тем регистром, что уже лежит там (Nuke3, а не NUKE3)."""
    base = os.path.join(mod, "hd", "TERRAIN")
    if os.path.isdir(base):
        for dn in os.listdir(base):
            if dn.upper() == s.upper() + ".PCK":
                return os.path.join(base, dn)
    return os.path.join(base, s + ".PCK")


def score(world, s, f, path):
    """(годен 1/0, флаги) по меркам score_batch; пустые строки, если оценить нельзя."""
    import score_batch as sb
    sh = world.sheet(s)
    if sh is None or path is None or not os.path.exists(path):
        return "", ""
    try:
        cell = Image.open(path).convert("RGBA")
        got = sb.score_frame(sh, f, cell, cell.width // sh.frame(f).width, SCORE_ARGS)
    except Exception as e:                                          # noqa: BLE001
        return "", "не оценён: %s" % e
    if got is None:
        return "", "не оценён: размер"
    return str(got["годен"]), got["flags"]


# ------------------------------------------------------------------ лист для выбора

def fit_text(dr, txt, font, width):
    """Строка по ширине своей колонки: подписи соседних кадров не должны налезать друг на друга."""
    if dr.textlength(txt, font=font) <= width:
        return txt
    while txt and dr.textlength(txt + "...", font=font) > width:
        txt = txt[:-1]
    return txt + "..."


def sheet(world, rows, mod, out_png, per=24):
    """Оригинал x4 | прежний кадр мода | новый - на тёмном полу, в полный рост (R-066)."""
    import build_dataset as bd
    files = []
    k = 4
    cw, ch, lh = 32 * k, 40 * k, 52
    for page in range(0, len(rows), per):
        part = rows[page:page + per]
        cols = 3
        rows_n = (len(part) + cols - 1) // cols
        W = cols * (3 * cw + 16)
        im = Image.new("RGB", (W, rows_n * (ch + lh) + 4), (16, 16, 18))
        dr = ImageDraw.Draw(im)
        for i, r in enumerate(part):
            x0 = (i % cols) * (3 * cw + 16)
            y0 = (i // cols) * (ch + lh)
            s, f = r["набор"], int(r["кадр"])
            orig = world.sprite(s, f, None)
            old = os.path.join(mod_dir(mod, s), "%d.png" % f)
            cells = [orig.resize((cw, ch), Image.NEAREST) if orig is not None else None,
                     Image.open(old).convert("RGBA") if os.path.exists(old) else None,
                     Image.open(r["_src"]).convert("RGBA")]
            for j, c in enumerate(cells):
                bg = Image.new("RGBA", (cw, ch), DARK + (255,))
                if c is not None:
                    bg.alpha_composite(c.resize((cw, ch)) if c.size != (cw, ch) else c)
                im.paste(bg.convert("RGB"), (x0 + j * cw, y0 + lh))
            fnt = bd.font()
            bad = r["годен"] == "0"
            fit = lambda txt: fit_text(dr, txt, fnt, 3 * cw - 4)
            dr.text((x0 + 2, y0 + 1), fit("%s %s  %s" % (s, r["файл"].split("/")[-1], r["что"])),
                    fill=(230, 200, 120) if bad else (220, 220, 220), font=fnt)
            if bad:
                dr.text((x0 + 2, y0 + 17), fit("брак: " + r["флаги"]), fill=(230, 150, 110), font=fnt)
            dr.text((x0 + 2, y0 + 33), "оригинал | в моде%s | новый" % ("" if r["в_моде"] else " (нет)"),
                    fill=(150, 150, 150), font=fnt)
        name = out_png % (page // per + 1)
        im.save(name)
        files.append(name)
    return files


# ------------------------------------------------------------------ команды

def cmd_pack(args):
    import map_mockup as mm
    world = mm.World()
    ledger = read_ledger()
    # последний выданный вариант файла; отклонённый тоже: он вернётся, только когда его перерисуют
    shipped = {r["файл"]: r["sha"] for r in ledger}
    n = max([int(r["обновление"]) for r in ledger] or [0]) + 1
    kind = "исправление" if any(r["террейн"] == args.terrain and r["карта"] == args.block for r in ledger) \
        else "карта"
    frames = map_frames(world, args.terrain, args.block)
    date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    rows, same, missing = [], 0, 0
    for s in sorted(frames):
        for f in sorted(frames[s]):
            got = files_of(args.root, s, f)
            if not got:
                missing += 1
                continue
            for src in got:
                rel = "hd/TERRAIN/%s/%s" % (os.path.basename(mod_dir(args.mod, s)), os.path.basename(src))
                h = sha(src)
                if shipped.get(rel) == h:
                    same += 1
                    continue
                old = os.path.join(mod_dir(args.mod, s), os.path.basename(src))
                is_main = "." not in os.path.basename(src)[:-4]
                ok, fl = score(world, s, f, src) if is_main else ("", "")
                ok_m, fl_m = score(world, s, f, old) if is_main and os.path.exists(old) else ("", "")
                rows.append({"обновление": n, "вид": kind, "дата": date, "террейн": args.terrain,
                             "карта": args.block, "набор": s, "кадр": f, "файл": rel, "sha": h,
                             "был_sha": shipped.get(rel, ""), "что": "исправлен" if rel in shipped else "новый",
                             "в_моде": "да" if os.path.exists(old) else "", "годен": ok, "флаги": fl,
                             "годен_мод": ok_m, "флаги_мод": fl_m, "решение": "ждёт", "_src": src})
    total = sum(len(v) for v in frames.values())
    print("карта %s %s: кадров на карте %d, нарисовано нет %d, уже выданы %d, в обновление %d файлов"
          % (args.terrain, args.block, total, missing, same, len(rows)))
    if not rows:
        print("выдавать нечего - обновление не создано")
        return 0
    name = upd_name(n, args.terrain, args.block)
    d = os.path.join(OUT, name)
    os.makedirs(d, exist_ok=True)
    zpath = os.path.join(OUT, name + ".zip")
    main_rows = [r for r in rows if r["файл"].endswith("/%d.png" % int(r["кадр"]))]
    sheets = sheet(world, main_rows, args.mod, os.path.join(d, "лист_%02d.png"))
    manifest = {"обновление": n, "вид": kind, "дата": date, "террейн": args.terrain, "карта": args.block,
                "папка_прогона": args.root.replace("\\", "/"), "файлов": len(rows),
                "брак_по_меркам": sum(r["годен"] == "0" for r in rows),
                "кадров_на_карте": total, "не_нарисовано": missing, "уже_выдано": same,
                "файлы": [{k: r[k] for k in ("файл", "sha", "что", "в_моде", "годен", "флаги",
                                             "годен_мод", "флаги_мод")} for r in rows]}
    with open(os.path.join(d, "manifest.json"), "w", encoding=ENC) as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for r in rows:
            z.write(r["_src"], r["файл"])
        z.write(os.path.join(d, "manifest.json"), "manifest.json")
        for p in sheets:
            z.write(p, os.path.basename(p))
    # в учёт - только после того, как архив собран целиком
    write_ledger(ledger + rows)
    bad = manifest["брак_по_меркам"]
    print("обновление %d (%s): %s, %d файлов, брак по меркам %d, лист: %s"
          % (n, kind, zpath, len(rows), bad, ", ".join(sheets)))
    write_status(read_ledger())
    return 0


def pick(ledger, n, frames):
    want = None
    if frames:
        want = set()
        for x in frames.split(","):
            s, f = x.strip().split(":")
            want.add((s.upper(), f))
    return [r for r in ledger if int(r["обновление"]) == int(n)
            and (want is None or (r["набор"].upper(), r["кадр"]) in want)]


def cmd_decide(args, verdict):
    ledger = read_ledger()
    got = pick(ledger, args.n, args.frames)
    if not got:
        print("в обновлении %s нет таких файлов" % args.n)
        return 1
    for r in got:
        if r["решение"] == "в моде":
            print("уже в моде, не меняю: %s" % r["файл"])
            continue
        r["решение"] = verdict
    write_ledger(ledger)
    print("обновление %s: %s - %d файлов" % (args.n, verdict, len(got)))
    write_status(ledger)
    return 0


def cmd_apply(args):
    """Принятое - в мод. Заменённый файл мода уходит в art\\_backup\\map_updates\\<обновление>."""
    ledger = read_ledger()
    got = [r for r in pick(ledger, args.n, None) if r["решение"] == "принят"]
    wait = [r for r in pick(ledger, args.n, None) if r["решение"] == "ждёт"]
    if wait:
        print("в обновлении %s %d файлов без решения - сначала accept или reject" % (args.n, len(wait)))
        return 1
    if not got:
        print("в обновлении %s нечего класть в мод" % args.n)
        return 1
    zpath = next((os.path.join(OUT, fn) for fn in os.listdir(OUT)
                  if fn.startswith("upd_%04d_" % int(args.n)) and fn.endswith(".zip")), None)
    if zpath is None:
        print("нет архива обновления %s в %s" % (args.n, OUT))
        return 1
    bk = os.path.join(BACKUP, os.path.basename(zpath)[:-4])
    with zipfile.ZipFile(zpath) as z:
        for r in got:
            dst = os.path.join(args.mod, *r["файл"].split("/"))
            if os.path.exists(dst):
                b = os.path.join(bk, *r["файл"].split("/"))
                os.makedirs(os.path.dirname(b), exist_ok=True)
                shutil.copy2(dst, b)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with z.open(r["файл"]) as src, open(dst, "wb") as out:
                out.write(src.read())
            if sha(dst) != r["sha"]:
                print("НЕ СОВПАЛ после записи: %s" % dst)
                return 1
            r["решение"] = "в моде"
    write_ledger(ledger)
    print("обновление %s: в мод %s положено %d файлов, прежние - в %s" % (args.n, args.mod, len(got), bk))
    write_status(ledger)
    return 0


def write_status(ledger):
    """Дорожная карта по картам: считается из учёта целиком, руками не правится."""
    import map_mockup as mm
    world = mm.World()
    maps_total = sum(len(world.blocks_of(t)) for t in world.terrains)
    by_upd = {}
    for r in ledger:
        by_upd.setdefault(int(r["обновление"]), []).append(r)
    by_map = {}
    for n in sorted(by_upd):
        rs = by_upd[n]
        by_map.setdefault((rs[0]["террейн"], rs[0]["карта"]), []).append((n, rs))

    def state(rs):
        dec = {r["решение"] for r in rs}
        if dec == {"в моде"}:
            return "в моде"
        if "ждёт" in dec:
            return "ждёт решения"
        if dec == {"отклонён"}:
            return "отклонено"
        if "принят" in dec:
            return "принято, не в моде"
        return "в моде частично"

    lines = ["# Дорожная карта HD по картам", "",
             "Считается `tools/hdart/map_update.py` из учёта `art/maps/updates/updates.tsv`. Руками не править.",
             "", "Обновлено: %s" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), ""]
    done_maps = sum(1 for v in by_map.values() if all(state(rs) == "в моде" for _n, rs in v))
    lines += ["| карт в игре | с обновлением | целиком в моде | обновлений | файлов |",
              "|---|---|---|---|---|",
              "| %d | %d | %d | %d | %d |" % (maps_total, len(by_map), done_maps, len(by_upd), len(ledger)), ""]
    lines += ["## По картам", "", "| террейн | карта | обновление | вид | файлов | новых | исправлено | "
              "брак по меркам | состояние |", "|---|---|---|---|---|---|---|---|---|"]
    for (t, b), ups in sorted(by_map.items()):
        for n, rs in ups:
            lines.append("| %s | %s | %04d | %s | %d | %d | %d | %d | %s |" % (
                t, b, n, rs[0]["вид"], len(rs), sum(r["что"] == "новый" for r in rs),
                sum(r["что"] == "исправлен" for r in rs), sum(r["годен"] == "0" for r in rs), state(rs)))
    # исправления по файлам: файл, выданный больше одного раза
    per_file = {}
    for r in ledger:
        per_file.setdefault(r["файл"], []).append(r)
    fixed = {k: v for k, v in per_file.items() if len(v) > 1}
    lines += ["", "## Исправления по файлам", ""]
    if not fixed:
        lines.append("Пока ни один файл не выдавался дважды.")
    else:
        lines += ["| файл | обновления | последнее решение |", "|---|---|---|"]
        for k, v in sorted(fixed.items()):
            lines.append("| %s | %s | %s |" % (k, ", ".join("%04d (%s)" % (int(r["обновление"]), r["карта"])
                                                          for r in v), v[-1]["решение"]))
    with open(STATUS, "w", encoding=ENC) as f:
        f.write("\n".join(lines) + "\n")
    print("дорожная карта: %s" % STATUS)


def main(argv=None):
    global OUT, LEDGER, STATUS
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pack", help="собрать обновление карты")
    p.add_argument("--terrain", required=True)
    p.add_argument("--block", required=True)
    p.add_argument("--root", required=True, help="папка прогона map_paint (--root)")
    p.add_argument("--mod", default=MOD, help="мод hd, с которым сравнивать (только чтение)")
    for name in ("accept", "reject"):
        q = sub.add_parser(name, help="принять или отклонить обновление или его кадры")
        q.add_argument("n")
        q.add_argument("--frames", default="", help="НАБОР:кадр через запятую; без него - всё обновление")
    q = sub.add_parser("apply", help="принятое - в мод, прежнее - в резерв")
    q.add_argument("n")
    q.add_argument("--mod", required=True, help="мод hd, КУДА класть - задаётся явно (R-015)")
    sub.add_parser("status", help="пересчитать docs/MAP_STATUS.md")
    ap.add_argument("--updates", default=OUT, help="папка обновлений и учёта (для теста - своя)")
    ap.add_argument("--status", default=STATUS, help="куда писать дорожную карту")
    args = ap.parse_args(argv)
    OUT, STATUS = args.updates, args.status
    LEDGER = os.path.join(OUT, "updates.tsv")
    if args.cmd == "pack":
        return cmd_pack(args)
    if args.cmd == "accept":
        return cmd_decide(args, "принят")
    if args.cmd == "reject":
        return cmd_decide(args, "отклонён")
    if args.cmd == "apply":
        return cmd_apply(args)
    write_status(read_ledger())
    return 0


if __name__ == "__main__":
    sys.exit(main())
