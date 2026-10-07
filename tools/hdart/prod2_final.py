#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Итог PROD_TWO_PASS_V2: что приняли судьи и что осталось человеку (специалист 05.10 - человеку только хвост).

Без модели. Читает приговоры связки судей трёх проходов (judge/<проход>/verdicts_auto.tsv, visual_judge.py
prod-verdict) и маршрут пересмотра (third/descriptions.tsv) и пишет в папку партии:
    final.tsv            asset_id, status, stage, piece, note - на каждый кадр партии
    final.md             сводка и хвост
    final_accepted.png   принятые судьями: оригинал x4 | принятый HD (тёмный пол) - глазам Vitali одним листом
    final_tail.png       хвост: оригинал x4 | RESTORE | STRICT | THIRD

Принятое судьями - не приёмка: на калибровке TEST судьи пропустили 1 плохой из 6 AUTO_ACCEPT (DECISIONS 05.10),
поэтому лист принятых тоже идёт Vitali, но смотреть его - одно решение на кадр, а не три прохода.

    GPUQ_BYPASS=1 py -3.13 tools/hdart/prod2_final.py
"""
import csv
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import visual_judge as vj        # noqa: E402

ENC = "utf-8-sig"
V2 = vj.V2
STAGES = ["RESTORE", "STRICT", "THIRD"]
DARK = vj.DARK


def read_tsv(p):
    if not os.path.exists(p):
        return []
    with open(p, encoding=ENC) as f:
        return list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))


def piece(stage, a):
    s, f = a.split(":")
    return os.path.join(V2, vj.PROD_SUB[stage], "%s.PCK" % s, "%s.png" % f)


def cell(img, w=128, h=160):
    """Картинка в клетку w x h на тёмном полу, по центру, без масштаба вверх больше x1."""
    from PIL import Image
    bg = Image.new("RGBA", (w, h), DARK)
    if img is None:
        return bg
    k = min(w / img.width, h / img.height, 1.0)
    im = img.resize((max(1, int(img.width * k)), max(1, int(img.height * k))), Image.LANCZOS) if k < 1 else img
    bg.alpha_composite(im, ((w - im.width) // 2, (h - im.height) // 2))
    return bg


def orig_img(a):
    import numpy as np
    from PIL import Image
    o = vj.sprite(a)
    return Image.fromarray(np.repeat(np.repeat(o, 4, 0), 4, 1))


def hd_img(stage, a):
    from PIL import Image
    p = piece(stage, a)
    return Image.open(p).convert("RGBA") if os.path.exists(p) else None


def sheet(rows, cols_per_row, path, head):
    """rows: [(подпись, [картинки])]; по cols_per_row записей в ряд."""
    from PIL import Image, ImageDraw
    if not rows:
        return
    n = len(rows[0][1])
    cw, ch, lab = 128, 160, 14
    rw = n * cw + 8
    nr = (len(rows) + cols_per_row - 1) // cols_per_row
    W, H = cols_per_row * rw + 8, 24 + nr * (ch + lab + 8)
    out = Image.new("RGBA", (W, H), (12, 12, 12, 255))
    d = ImageDraw.Draw(out)
    from PIL import ImageFont
    try:                                    # шрифт PIL по умолчанию кириллицы не знает - шапка выходит квадратами
        font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 14)
    except OSError:
        font = None
    d.text((8, 4), head, fill=(230, 230, 230, 255), font=font)
    for i, (label, imgs) in enumerate(rows):
        x0, y0 = 8 + (i % cols_per_row) * rw, 24 + (i // cols_per_row) * (ch + lab + 8)
        d.text((x0, y0), label, fill=(240, 220, 120, 255))
        for j, im in enumerate(imgs):
            out.alpha_composite(cell(im), (x0 + j * cw, y0 + lab))
    out.convert("RGB").save(path)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    os.chdir(vj.ROOT)
    with open(os.path.join(V2, "jobs.json"), encoding=ENC) as f:
        jobs = [j["asset_id"] for j in json.load(f)]
    with open(os.path.join(V2, "report.json"), encoding=ENC) as f:      # рисовались: V7 часть заданий придержал
        assets = [x["asset_id"] for x in json.load(f)["items"]]
    held = [a for a in jobs if a not in set(assets)]
    ver = {st: {r["asset_id"]: r for r in read_tsv(os.path.join(vj.prod_dir(st), "verdicts_auto.tsv"))}
           for st in STAGES}
    third = {r["asset_id"]: r for r in read_tsv(os.path.join(V2, "third", "descriptions.tsv"))}
    rows = []
    for a in assets:
        st, status, note = "", "TAIL", ""
        for s in STAGES:
            v = ver[s].get(a)
            if v and v["verdict"] == "PASS":
                st, status, note = s, "ACCEPTED_BY_JUDGES", v["note"]
                break
        if status == "TAIL":
            if a not in ver["RESTORE"]:
                raise SystemExit("нет приговора RESTORE: %s" % a)
            last = next((s for s in reversed(STAGES) if a in ver[s]), "RESTORE")
            if a in third and third[a]["route"] != "STRICT":
                note = "THIRD не рисовался: %s; " % third[a]["route"]
            elif a in third and a not in ver["THIRD"]:
                raise SystemExit("THIRD нарисован, а приговора нет: %s" % a)
            st, note = last, note + ver[last][a]["route"] + ": " + ver[last][a]["note"]
        rows.append({"asset_id": a, "status": status, "stage": st, "piece": piece(st, a).replace("\\", "/"),
                     "note": note.replace("\t", " ")})
    p = os.path.join(V2, "final.tsv")
    head = ["asset_id", "status", "stage", "piece", "note"]
    with open(p + ".tmp", "w", encoding=ENC, newline="") as f:
        w = csv.DictWriter(f, fieldnames=head, delimiter="\t", quoting=csv.QUOTE_NONE, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    os.replace(p + ".tmp", p)

    acc = [r for r in rows if r["status"] == "ACCEPTED_BY_JUDGES"]
    tail = [r for r in rows if r["status"] == "TAIL"]
    sheet([("%s  %s" % (r["asset_id"], r["stage"]), [orig_img(r["asset_id"]), hd_img(r["stage"], r["asset_id"])])
           for r in acc], 5, os.path.join(V2, "final_accepted.png"),
          "PROD_TWO_PASS_V2: приняты судьями %d - оригинал x4 | HD" % len(acc))
    sheet([(r["asset_id"], [orig_img(r["asset_id"])] + [hd_img(s, r["asset_id"]) for s in STAGES]) for r in tail],
          2, os.path.join(V2, "final_tail.png"),
          "PROD_TWO_PASS_V2: хвост %d - оригинал x4 | RESTORE | STRICT | THIRD" % len(tail))

    ident = read_tsv(os.path.join(V2, "identity", "auto", "identity.tsv"))
    human = [r["asset_id"] for r in ident if r["route"] == "HUMAN"]
    by_stage = Counter(r["stage"] for r in acc)
    md = ["# PROD_TWO_PASS_V2 - итог", "",
          "Кадров в партии: %d. Приняты связкой судей (Codex + Claude, оба PASS sure): %d - RESTORE %d, STRICT %d, "
          "THIRD %d. Хвост: %d." % (len(rows), len(acc), by_stage["RESTORE"], by_stage["STRICT"], by_stage["THIRD"],
                                   len(tail)), "",
          "Опознание не решено (арбитр не уверен, не рисовались): %d - %s." % (len(human), ", ".join(human)), "",
          "Не рисовались по связям V7 (выводятся из другого кадра или ждут его): %d." % len(held), "",
          "Лист принятых - final_accepted.png, хвост - final_tail.png, по кадру - final.tsv.", "",
          "## Хвост", "", "| кадр | последний проход | судьи |", "|---|---|---|"]
    md += ["| %s | %s | %s |" % (r["asset_id"], r["stage"], r["note"].replace("|", "/")[:220]) for r in tail]
    with open(os.path.join(V2, "final.md"), "w", encoding=ENC, newline="\n") as f:
        f.write("\n".join(md) + "\n")
    print("принято судьями %d (%s), хвост %d, опознание человеку %d"
          % (len(acc), dict(by_stage), len(tail), len(human)))


if __name__ == "__main__":
    main()
