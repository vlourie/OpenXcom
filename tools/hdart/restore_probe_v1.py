#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""RESTORE_V1 - путь A (DECISIONS 2026-10-03): те же 7 прямых рендеров run1, промпт под реставрацию ассета.

Что меняется против run1 и только это:
  - промпт: вместо «фотореалистичная вещь, естественный износ и грязь» - верная реставрация спрайта: цвет,
    насыщенность и яркость как в спрайте, тёмные части тёмные, размер каждой части прежний, без новых деталей,
    без ржавчины и грязи (RESTORE);
  - подпись предмета: жёсткое описание из restore-v1/descriptions.tsv вместо подписи оси A с «or»;
    рендер только при status = OK у всех строк (описания подтверждает Vitali, R-125);
  - негатив: obj_photo.NEGATIVE без «flat colours» (спорит с ровным сигнальным цветом) плюс выцветание,
    ржавчина, грязь, лишние и пропавшие части (NEG_ADD).
Всё прочее как run1: задания и зёрна run1/jobs.json, вход варианта C (эскиз struct_guide + оригинал),
модель по замку, 40 шагов, cfg 4, 1 Мп, подложка, вырезка photo_base.cut, проверки photo_accept, до трёх
попыток. Рендерный цикл - struct_probe.Render без правки; prompt_for подменяется в этом процессе.
Поверх - ворота верности asset_fidelity (COLOR, DARK, PARTS).

Модель - только через очередь (gpu_scripts.txt):
    py -3.13 tools/gpuq.py add --name restore_v1 --cwd E:/OpenXCom -- \
        E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/render_chunks.py \
        --out art/objects/generation/probes/restore-v1 -- \
        E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/restore_probe_v1.py render
Без модели (GPUQ_BYPASS=1): prompts - промпты в restore-v1/prompts.md; report - ворота и лист
run1 против restore-v1.
"""
import argparse
import csv
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.dirname(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
ROOT = os.path.dirname(os.path.dirname(HERE))
os.chdir(ROOT)

ENC = "utf-8-sig"
PROBES = "art/objects/generation/probes"
RUN1 = PROBES + "/hd-e2e-v1/run1"
OUT = PROBES + "/restore-v1"
VARIANT = "C"
RESTORE = (
    "<image1> is the low-resolution original game sprite of {what}, shown on a flat grey preview panel. "
    "The panel is background, not part of the object. "
    "Restore this exact sprite as a sharp high-resolution realistic picture of the same object for the same "
    "game. This is a faithful restoration, not a reinterpretation: keep the position, the size, the silhouette "
    "and the proportions of every part exactly as in the sprite, seen from above at 30 degrees in isometric "
    "view exactly like the sprite. Keep the colours of the sprite: the same hue, the same brightness and the "
    "same saturation for every part. Bright accent colours stay bright and saturated, dark parts stay dark, "
    "almost black, light parts stay light. Do not add parts, do not remove parts, do not make any part smaller "
    "or larger. Clean surfaces: no wear, no rust, no dirt, no stains. Real material surface detail, even soft "
    "light from the upper left, sharp focus. "
    "Output one isolated object on the same flat panel. No ground, no floor, no other objects, "
    "no frame, no text.")
NEG_DROP = "flat colours, "
NEG_ADD = (", desaturated, faded colours, washed out, dull colours, colour shift, rust, dirt, grime, stains, "
           "weathered, worn, extra parts, missing parts, smaller parts, antenna")
# переопределяют наследники (restore_probe_v1b.py): какие кадры, с чем сравнивать в отчёте, имя пробы
ONLY = None                     # None - все задания run1; иначе множество asset_id
PREV, PREV_PREFIX, PREV_LABEL = RUN1, "e2e_", "run1"
PROBE = "RESTORE_V1"


def load(p):
    with open(p, encoding=ENC) as f:
        return json.load(f)


def dump(p, obj):
    with open(p, "w", encoding=ENC) as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def descriptions():
    with open(os.path.join(OUT, "descriptions.tsv"), encoding=ENC) as f:
        return {r["asset_id"]: r for r in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE)}


def jobs(require_ok):
    """Задания run1 с жёстким описанием вместо подписи оси A."""
    d = descriptions()
    out = []
    for j in load(os.path.join(RUN1, "jobs.json")):
        if ONLY is not None and j["asset_id"] not in ONLY:
            continue
        r = d.get(j["asset_id"])
        if r is None:
            raise SystemExit("нет описания %s в descriptions.tsv" % j["asset_id"])
        if require_ok and r["status"] != "OK":
            raise SystemExit("описание %s не подтверждено (status %s) - рендер не начинаю (R-125)" % (
                j["asset_id"], r["status"]))
        out.append(dict(j, what=r["description"], what_axis_a=j["what"], name="restore_" + j["name"][4:],
                        output=""))
    return out


def prompt_for(what, name, rgb):
    """photo_render.prompt_for с текстом RESTORE: та же замена фразы подложки и тот же хвост про фон."""
    import photo_render as pr
    r, g, b = [int(v) for v in rgb]
    if pr.GREY_PHRASE not in RESTORE:
        raise SystemExit("в RESTORE нет фразы подложки")
    base = RESTORE.replace("{what}", what).replace(
        pr.GREY_PHRASE, "shown on a flat preview panel of colour RGB(%d, %d, %d)" % (r, g, b))
    kind = "neutral " if name.startswith("grey") else ""
    return base + " " + pr.PANEL_TEXT.format(kind=kind, r=r, g=g, b=b)


def negative():
    import obj_photo as op
    if NEG_DROP not in op.NEGATIVE:
        raise SystemExit("в obj_photo.NEGATIVE нет %r - негатив изменился" % NEG_DROP)
    return op.NEGATIVE.replace(NEG_DROP, "") + NEG_ADD


def do_prompts():
    import map_mockup as mm
    import photo_render as pr
    import struct_probe as sp
    import hd_e2e_v1_run as e2e
    world = mm.World()
    lines = ["# %s: промпты (без модели)" % PROBE, "", "Негатив: `%s`" % negative(), ""]
    for j in jobs(False):
        comp, whole, at, box, frame = e2e.job_input(world, j)
        name, rgb, margin = pr.panels_by_margin(frame)[0]
        _ims, extra, _rep = sp.inputs(VARIANT, frame, rgb)
        lines += ["## %s (seed %d, подложка %s)" % (j["asset_id"], j["seed"], name), "",
                  "Ось A: %s" % j["what_axis_a"], "", prompt_for(j["what"], name, rgb) + extra, ""]
    with open(os.path.join(OUT, "prompts.md"), "w", encoding=ENC) as f:
        f.write("\n".join(lines))
    print("промпты: %s/prompts.md" % OUT)


def do_render(max_renders):
    import gen_fire
    import map_mockup as mm
    import photo_base as pb
    import photo_render as pr
    import struct_probe as sp
    import hd_e2e_v1_run as e2e
    js = jobs(True)
    R = sp.Render(OUT, None, max_renders, False)
    pr.prompt_for = prompt_for                  # только в этом процессе; photo_render.py не правится
    gen_fire.NEGATIVE = negative()              # Render.__init__ поставил obj_photo.NEGATIVE - заменить после
    print("%s: generator_rev %s, guide_rev %s, cut_rev %s, заданий %d" % (
        PROBE.lower(), R.grev, R.guide_rev, R.cut_rev, len(js)), flush=True)
    world = mm.World()
    raw_dir, meta_dir = os.path.join(OUT, "render", "raw"), os.path.join(OUT, "render", "meta")
    os.makedirs(raw_dir, exist_ok=True)
    os.makedirs(meta_dir, exist_ok=True)
    t0, cells = time.time(), []
    try:
        for n, j in enumerate(js, 1):
            comp, whole, at, box, frame = e2e.job_input(world, j)
            panels = pr.panels_by_margin(frame)
            final, attempts = R.job(VARIANT, j, frame, panels, raw_dir)
            meta, cell = R.finish(VARIANT, j, comp, whole, at, box, final, attempts,
                                  os.path.join(OUT, "render"), meta_dir,
                                  extra={"what_axis_a": j["what_axis_a"], "job_id": j["job_id"],
                                         "negative": gen_fire.NEGATIVE, "probe": PROBE})
            cells.append(cell)
            print("%-26s %-20s попыток %d | готово %d из %d, прошло %.0f мин" % (
                j["asset_id"], meta["outcome"], len(attempts), n, len(js), (time.time() - t0) / 60), flush=True)
    except sp.Budget:
        print("лимит процесса: новых рендеров %d из %d - выхожу" % (R.renders, R.max), flush=True)
        sys.exit(sp.EXIT_MORE)
    if cells:
        pb.sheet(world, cells, os.path.join(OUT, "render", "machine_sheet.png"))
    dump(os.path.join(OUT, "execution.json"), {"generator_rev": R.grev, "guide_rev": R.guide_rev,
                                               "cut_rev": R.cut_rev, "params": pr.RENDER_V1, "variant": VARIANT,
                                               "prompt": RESTORE, "negative": gen_fire.NEGATIVE,
                                               "items": len(js), "gpuq_job": os.environ.get("GPUQ_JOB_ID", ""),
                                               "finished": time.strftime("%Y-%m-%dT%H:%M:%S")})
    print("готово: заданий %d, новых рендеров в процессе %d" % (len(cells), R.renders), flush=True)


def do_report():
    """Ворота верности PREV против OUT и лист: оригинал x4 | PREV | OUT."""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont
    import asset_fidelity as AF
    import map_mockup as mm
    world = mm.World()
    try:                                        # шрифт PIL по умолчанию без кириллицы - на листе квадратики
        font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 13)
    except OSError:
        font = ImageFont.load_default()
    cur = os.path.basename(OUT)
    rows, md = [], ["# %s против %s" % (PROBE, PREV_LABEL), "",
                    "Ворота asset_fidelity (%s) и машина photo_accept. Лист: `sheet.png`." % ", ".join(AF.CHECKS), "",
                    "| кадр | %s машина | %s верность | %s машина | %s | %s верность |" % (
                        PREV_LABEL, PREV_LABEL, cur, " | ".join("%s %s" % (cur, c) for c in AF.CHECKS), cur),
                    "|---|---|---|---|%s---|" % ("---|" * len(AF.CHECKS))]
    res = []
    for j in jobs(False):
        m1 = load(os.path.join(PREV, "render", "meta", j["name"].replace("restore_", PREV_PREFIX, 1) + ".json"))
        mp = os.path.join(OUT, "render", "meta", j["name"] + ".json")
        m2 = load(mp) if os.path.exists(mp) else None
        s = os.path.basename(os.path.dirname(m1["piece"]))[:-4]
        n = int(os.path.splitext(os.path.basename(m1["piece"]))[0])
        o = np.asarray(world.sprite(s.lower(), n, None))
        r1 = AF.measure(o, Image.open(m1["piece"]))
        r2 = AF.measure(o, Image.open(m2["piece"])) if m2 else None
        res.append({"asset_id": j["asset_id"], PREV_LABEL: {"machine": m1["machine"], "verdict": AF.verdict(r1),
                                                            "fidelity": {c: r1[c] for c in AF.CHECKS}},
                    "restore": None if m2 is None else {"machine": m2["machine"], "verdict": AF.verdict(r2),
                                                        "fidelity": {c: r2[c] for c in AF.CHECKS}}})
        md.append("| %s | %s | %s | %s | %s | %s |" % (
            j["asset_id"], m1["machine"], AF.verdict(r1), m2["machine"] if m2 else "—",
            " | ".join(("%s (%s)" % tuple(r2[c]) for c in AF.CHECKS) if r2 else ("—",) * len(AF.CHECKS)),
            AF.verdict(r2) if r2 else "—"))
        tiles = [np.repeat(np.repeat(o, 4, 0), 4, 1), np.asarray(Image.open(m1["piece"]).convert("RGBA"))]
        if m2:
            tiles.append(np.asarray(Image.open(m2["piece"]).convert("RGBA")))
        H, W = tiles[0].shape[:2]
        row = Image.new("RGBA", (3 * (W * 2 + 10) + 420, H * 2), (18, 18, 18, 255))
        for i, t in enumerate(tiles):
            bg = Image.new("RGBA", (W, H), (28, 26, 24, 255))
            bg.alpha_composite(Image.fromarray(t))
            row.paste(bg.resize((W * 2, H * 2), Image.LANCZOS), (i * (W * 2 + 10), 0))
        d = ImageDraw.Draw(row)
        x = 3 * (W * 2 + 10)
        d.text((x, 8), j["asset_id"], fill=(235, 235, 235), font=font)
        d.text((x, 30), "orig x4 | %s | %s" % (PREV_LABEL, cur), fill=(150, 150, 150), font=font)
        d.text((x, 56), "%s: %s / %s" % (PREV_LABEL, m1["machine"], AF.verdict(r1)), fill=(200, 200, 200), font=font)
        if r2:
            d.text((x, 78), "%s: %s / %s" % (cur, m2["machine"], AF.verdict(r2)), fill=(200, 200, 200), font=font)
            for i, c in enumerate(AF.CHECKS):
                d.text((x, 100 + 18 * i), "%s %s %s" % (c, r2[c][0], r2[c][1][:44]), fill=(170, 170, 170),
                       font=font)
        rows.append(row)
    sheet = Image.new("RGBA", (max(r.width for r in rows), sum(r.height for r in rows)), (18, 18, 18, 255))
    y = 0
    for r in rows:
        sheet.paste(r, (0, y))
        y += r.height
    sheet.save(os.path.join(OUT, "sheet.png"))
    with open(os.path.join(OUT, "report.md"), "w", encoding=ENC) as f:
        f.write("\n".join(md) + "\n")
    dump(os.path.join(OUT, "report.json"), res)
    print("\n".join(md[4:]))
    print("лист %s/sheet.png" % OUT)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["prompts", "render", "report"])
    ap.add_argument("--max-renders", type=int, default=4)
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if a.cmd == "prompts":
        do_prompts()
    elif a.cmd == "render":
        do_render(a.max_renders)
    else:
        do_report()


if __name__ == "__main__":
    main()
