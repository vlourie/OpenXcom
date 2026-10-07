#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""STRICT 27.09 на контрольном наборе (специалист 03.10, передал Vitali): 11 FAIL shape-fail-control-v1 плюс
16 regression_pass, итого 27 кадров. Больших партий нет, новых ворот нет, машинные метрики решения не принимают.

STRICT рисуется ровно путём obj_series.paint (серия 27.09): STYLE["strict"] и NEGATIVE из probe_object,
подложка pick_background, bicubic x16, Qwen-Image-2.1 40 шагов, cfg 4, 1 Мп, cut_out grow 2 / soft 40,
match_tone 0.7, pad 3. Описание и зерно - из партии RESTORE (как у PHOTO в oldauto-ab-v1), чтобы различался
только способ. Код obj_series не меняется: его main рисует по картам и подсказкам карт, кадр по списку не берёт.

    <venv-qwen21>/python.exe tools/hdart/strict_ctl_v1.py render   только через очередь gpuq (модель)
    py -3.13 tools/hdart/strict_ctl_v1.py sheet    слепые листы: 11 FAIL - три варианта X/Y/Z, 16 PASS - L/R
    py -3.13 tools/hdart/strict_ctl_v1.py report   раскрыть ключ по заполненным бланкам
"""
import argparse
import csv
import io
import json
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for _p in (HERE, os.path.join(HERE, "..")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from PIL import Image, ImageDraw, ImageFont         # noqa: E402

ENC = "utf-8-sig"
SRC = "art/objects/generation/probes/restore-batch-v1"
AB = "art/objects/generation/probes/oldauto-ab-v1"
CTL = "art/objects/generation/probes/shape-fail-control-v1"
OUT = "art/objects/generation/probes/strict-ctl-v1"
SHEET_SEED = 31004
# как obj_series.main по умолчанию
STEPS, CFG, MP, ZOOM, GROW, SOFT, PAD, TONE = 40, 4.0, 1.0, 16, 2, 40, 3, 0.7
CH_FAIL = ("X", "Y", "Z", "=", "ALL_FAIL")
CH_PASS = ("L", "R", "=", "BOTH_FAIL")


def rd_json(p):
    with open(os.path.join(ROOT, p), encoding=ENC) as f:
        return json.load(f)


def wr_json(p, obj):
    with open(os.path.join(ROOT, p), "w", encoding=ENC) as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def rd_tsv(p):
    with open(os.path.join(ROOT, p), encoding=ENC) as f:
        return list(csv.DictReader(io.StringIO(f.read()), delimiter="\t", quoting=csv.QUOTE_NONE))


def wr_tsv(p, head, rows):
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=head, delimiter="\t", quoting=csv.QUOTE_NONE, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    with open(os.path.join(ROOT, p), "w", encoding=ENC, newline="") as f:
        f.write(out.getvalue())


def frames():
    """27 кадров: (группа, asset_id, what, seed, кусок RESTORE, дефект)."""
    rep = {x["asset_id"]: x for x in rd_json(SRC + "/report.json")["items"]}
    seeds = {j["asset_id"]: j["seed"] for j in rd_json(SRC + "/jobs.json")}
    res = []
    for r in rd_tsv(CTL + "/control.tsv"):
        res.append({"group": "fail", "asset_id": r["asset_id"], "what": rep[r["asset_id"]]["what"],
                    "seed": seeds[r["asset_id"]], "restore": rep[r["asset_id"]]["piece"], "defect": r["defect"]})
    for r in rd_tsv(CTL + "/regression_pass.tsv"):
        res.append({"group": "pass", "asset_id": r["asset_id"], "what": rep[r["asset_id"]]["what"],
                    "seed": seeds[r["asset_id"]], "restore": rep[r["asset_id"]]["piece"], "defect": ""})
    if [f["group"] for f in res].count("fail") != 11 or len(res) != 27:
        raise SystemExit("контрольный набор не 11 + 16: %d" % len(res))
    return res


def piece(kind, asset):
    s, n = asset.split(":")
    return {"strict": "%s/series/%s.PCK/%s.png" % (OUT, s, n),
            "photo": "%s/A/%s.PCK/%s.png" % (AB, s, n)}[kind]


# ---------------------------------------------------------------- рендер (модель, только через gpuq)

def do_render():
    import map_mockup as mm
    import probe_object as po
    w = mm.World()
    fr = frames()
    os.makedirs(os.path.join(ROOT, OUT, "raw"), exist_ok=True)
    todo = [f for f in fr if not os.path.exists(os.path.join(ROOT, piece("strict", f["asset_id"])))]
    print("STRICT: кадров %d, готово %d, рисовать %d" % (len(fr), len(fr) - len(todo), len(todo)), flush=True)
    if not todo:
        return
    ns = argparse.Namespace(models=po.gen_hd.DEFAULT_MODELS_DIR, qwen21_model="", qwen21_steps=STEPS,
                            qwen21_cfg=CFG, qwen21_mp=MP, qwen21_strength=0.0, qwen21_offload="model",
                            qwen21_thrifty=False, qwen21_ref="", qwen21_ref_mp=1.0, qwen21_prompt="strict",
                            qwen21_hint="off", qwen21_ref_order="ref-first")
    painter = po.gen_hd.Qwen21Painter(ns, {"ground": ("", "")})
    po.gen_fire.NEGATIVE = po.NEGATIVE
    args = argparse.Namespace(steps=STEPS, cfg=CFG, mp=MP)
    t0 = time.time()
    for n, f in enumerate(todo, 1):
        s, k = f["asset_id"].split(":")
        full = w.sprite(s.lower(), int(k), None).convert("RGBA")
        bb = full.split()[3].getbbox()
        box = (max(0, bb[0] - PAD), max(0, bb[1] - PAD), min(full.width, bb[2] + PAD), min(full.height, bb[3] + PAD))
        frame = full.crop(box)
        panel = po.pick_background(frame)
        src = frame.resize((frame.width * ZOOM, frame.height * ZOOM), Image.BICUBIC)
        flat = Image.new("RGBA", src.size, tuple(panel) + (255,))
        flat.alpha_composite(src)
        prompt = po.STYLE["strict"].replace("{what}", f["what"])
        hd = po.gen_fire.run_pass(painter, args, prompt, flat.convert("RGB"), f["seed"])
        po.gen_hd.save_png(hd, os.path.join(ROOT, OUT, "raw", "%s_%s.png" % (s, k)))
        part = po.match_tone(po.cut_out(hd, frame, GROW, SOFT), frame, TONE)
        cut = Image.new("RGBA", (full.width * 4, full.height * 4), (0, 0, 0, 0))
        cut.paste(part, (box[0] * 4, box[1] * 4))
        os.makedirs(os.path.join(ROOT, OUT, "series", s + ".PCK"), exist_ok=True)
        po.gen_hd.save_png(cut, os.path.join(ROOT, piece("strict", f["asset_id"])))
        el = time.time() - t0
        print("[%d/%d] %s (%s) готово, %.0f с, осталось ~%.0f мин"
              % (n, len(todo), f["asset_id"], f["group"], el / n, el / n * (len(todo) - n) / 60), flush=True)
    wr_json(OUT + "/spec.json", {
        "what": "STRICT 27.09 на контрольном наборе 11 FAIL + 16 PASS (специалист 03.10)",
        "path": "obj_series.paint: STYLE strict, NEGATIVE probe_object, pick_background, bicubic x%d, "
                "Qwen-Image-2.1 %d шагов, cfg %g, %g Мп, cut_out grow %d soft %d, match_tone %g, pad %d"
                % (ZOOM, STEPS, CFG, MP, GROW, SOFT, TONE, PAD),
        "what_seed": "из партии RESTORE (report.json, jobs.json)", "sheet_seed": SHEET_SEED})
    print("ГОТОВО за %.1f мин" % ((time.time() - t0) / 60), flush=True)


# ---------------------------------------------------------------- слепые листы

def on_floor(im, size):
    bg = Image.new("RGBA", size, (38, 38, 42, 255))
    im = im.convert("RGBA").resize(size, Image.LANCZOS if im.width > size[0] else Image.NEAREST)
    bg.alpha_composite(im)
    return bg


def draw_parts(cells, caps, name, font, cw=256, ch=320, per=5):
    os.makedirs(os.path.join(ROOT, OUT, "sheet"), exist_ok=True)
    paths = []
    for part in range(0, len(cells), per):
        chunk = cells[part:part + per]
        cols = len(caps)
        sh = Image.new("RGBA", (cols * (cw + 8) + 8, len(chunk) * (ch + 30)), (18, 18, 18, 255))
        d = ImageDraw.Draw(sh)
        for r, (title, ims) in enumerate(chunk):
            y = r * (ch + 30)
            d.text((8, y + 4), title, fill=(240, 240, 240), font=font)
            for c, (im, cap) in enumerate(zip(ims, caps)):
                sh.paste(on_floor(im, (cw, ch)), (8 + c * (cw + 8), y + 28))
                d.text((8 + c * (cw + 8) + 6, y + 32), cap, fill=(255, 220, 0), font=font)
        p = os.path.join(OUT, "sheet", "%s_%02d.png" % (name, part // per))
        sh.convert("RGB").save(os.path.join(ROOT, p))
        paths.append(p)
    return paths


def filled(p, cols):
    return os.path.exists(os.path.join(ROOT, p)) and any(any(r[c].strip() for c in cols) for r in rd_tsv(p))


def do_sheet():
    import map_mockup as mm
    fr = frames()
    miss = [f["asset_id"] for f in fr if not os.path.exists(os.path.join(ROOT, piece("strict", f["asset_id"])))]
    miss += [f["asset_id"] + " (photo)" for f in fr if f["group"] == "fail"
             and not os.path.exists(os.path.join(ROOT, piece("photo", f["asset_id"])))]
    if miss:
        raise SystemExit("нет кусков: %s" % " ".join(miss))
    w = mm.World()
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 18)
    rng = random.Random(SHEET_SEED)
    key = {"fail": {}, "pass": {}}
    fail_cells, pass_cells, fail_rows, pass_rows = [], [], [], []

    def orig(a):
        s, n = a.split(":")
        return w.sprite(s.lower(), int(n), None).convert("RGBA").resize((128, 160), Image.NEAREST)

    def im(p):
        return Image.open(os.path.join(ROOT, p))

    for f in [f for f in fr if f["group"] == "fail"]:
        i = len(fail_rows) + 1
        order = ["restore", "strict", "photo"]
        rng.shuffle(order)
        key["fail"][f["asset_id"]] = {"row": i, "X": order[0], "Y": order[1], "Z": order[2]}
        srcs = {"restore": f["restore"], "strict": piece("strict", f["asset_id"]),
                "photo": piece("photo", f["asset_id"])}
        fail_cells.append(("%d  %s  дефект: %s" % (i, f["asset_id"], f["defect"]),
                           [orig(f["asset_id"])] + [im(srcs[k]) for k in order]))
        fail_rows.append({"row": i, "asset_id": f["asset_id"], "defect": f["defect"], "best": "",
                          "X": "", "Y": "", "Z": "", "X_fixed": "", "Y_fixed": "", "Z_fixed": "", "note": ""})
    for f in [f for f in fr if f["group"] == "pass"]:
        i = len(pass_rows) + 1
        s_left = rng.random() < 0.5
        key["pass"][f["asset_id"]] = {"row": i, "L": "strict" if s_left else "restore",
                                      "R": "restore" if s_left else "strict"}
        a, b = im(piece("strict", f["asset_id"])), im(f["restore"])
        pass_cells.append(("%d  %s" % (i, f["asset_id"]), [orig(f["asset_id"])] + ([a, b] if s_left else [b, a])))
        pass_rows.append({"row": i, "asset_id": f["asset_id"], "better": "", "note": ""})
    pf = draw_parts(fail_cells, ["оригинал", "X", "Y", "Z"], "fail", font)
    pp = draw_parts(pass_cells, ["оригинал", "L", "R"], "pass", font)
    wr_json(OUT + "/key.json", key)
    for p, head, rows, cols in ((OUT + "/verdicts_fail.tsv", list(fail_rows[0]), fail_rows, ("best", "X", "Y", "Z")),
                                (OUT + "/verdicts_pass.tsv", list(pass_rows[0]), pass_rows, ("better",))):
        if filled(p, cols):
            print("бланк %s уже заполнен - не перезаписываю" % p)
        else:
            wr_tsv(p, head, rows)
    print("листы FAIL: %s" % " ".join(pf))
    print("листы PASS: %s" % " ".join(pp))


# ---------------------------------------------------------------- раскрытие

def yes(v):
    return v.strip().lower() in ("да", "yes", "y", "1", "+")


def do_report():
    key = rd_json(OUT + "/key.json")
    vf, vp = rd_tsv(OUT + "/verdicts_fail.tsv"), rd_tsv(OUT + "/verdicts_pass.tsv")
    bad = [v["asset_id"] for v in vf if v["best"] not in CH_FAIL] + \
          [v["asset_id"] for v in vp if v["better"] not in CH_PASS]
    if bad:
        raise SystemExit("не заполнено или не из списка: %s" % " ".join(bad))
    names = ("restore", "strict", "photo")
    best = {k: 0 for k in names + ("=", "ALL_FAIL")}
    pas = {k: 0 for k in names}
    fixed = {k: 0 for k in names}
    rows_f = []
    for v in vf:
        k = key["fail"][v["asset_id"]]
        b = k[v["best"]] if v["best"] in ("X", "Y", "Z") else v["best"]
        best[b] += 1
        per = {k[c]: (v[c].strip().upper(), v[c + "_fixed"].strip()) for c in ("X", "Y", "Z")}
        for n in names:
            pas[n] += per[n][0] == "PASS"
            fixed[n] += yes(per[n][1])
        rows_f.append("| %s | %s | %s | %s | %s | %s | %s |" % (
            v["row"], v["asset_id"], b, " / ".join("%s %s" % (per[n][0] or "-", per[n][1] or "-") for n in names),
            per["strict"][1] or "-", v["defect"], v["note"]))
    win = {"strict": 0, "restore": 0, "=": 0, "BOTH_FAIL": 0}
    rows_p = []
    for v in vp:
        k = key["pass"][v["asset_id"]]
        b = k[v["better"]] if v["better"] in ("L", "R") else v["better"]
        win[b] += 1
        rows_p.append("| %s | %s | %s | %s |" % (v["row"], v["asset_id"], b, v["note"]))
    pref = best["strict"] + win["strict"]
    lines = ["# STRICT 27.09 на контрольном наборе: итог слепой проверки", "",
             "Порог специалиста 03.10: исправлено >= 6 из 11, явных регрессий на 16 не больше 1-2, в общем "
             "сравнении STRICT не хуже RESTORE.", "",
             "| исправлено STRICT (из 11) | на 16 PASS: лучше RESTORE / оба плохие | STRICT предпочли (из 27) | "
             "RESTORE предпочли (из 27) |",
             "|---|---|---|---|",
             "| %d | %d / %d | %d | %d |" % (fixed["strict"], win["restore"], win["BOTH_FAIL"], pref,
                                          best["restore"] + win["restore"]), "",
             "Явные регрессии на 16 бланк не отмечает: «лучше RESTORE» - предпочтение, не обязательно брак STRICT.",
             "Контроль: на 11 FAIL вариант RESTORE - это сам забракованный рендер (тот же файл, что видел Vitali). "
             "Оценщик назвал его исправленным в %d из 11 и PASS в %d из 11." % (fixed["restore"], pas["restore"]), "",
             "## 11 FAIL: RESTORE | STRICT | PHOTO", "",
             "| | RESTORE | STRICT | PHOTO | одинаково | все брак |", "|---|---|---|---|---|---|",
             "| лучший | %d | %d | %d | %d | %d |" % (best["restore"], best["strict"], best["photo"], best["="],
                                                    best["ALL_FAIL"]),
             "| PASS | %d | %d | %d | | |" % (pas["restore"], pas["strict"], pas["photo"]),
             "| дефект исправлен | %d | %d | %d | | |" % (fixed["restore"], fixed["strict"], fixed["photo"]), "",
             "| # | кадр | лучший | restore / strict / photo (PASS, исправлен) | STRICT исправил | дефект | заметка |",
             "|---|---|---|---|---|---|---|"] + rows_f + [
             "", "## 16 PASS: RESTORE против STRICT", "",
             "| лучше STRICT | лучше RESTORE | равно | оба плохие |", "|---|---|---|---|",
             "| %d | %d | %d | %d |" % (win["strict"], win["restore"], win["="], win["BOTH_FAIL"]), "",
             "| # | кадр | лучше | заметка |", "|---|---|---|---|"] + rows_p
    with open(os.path.join(ROOT, OUT, "report.md"), "w", encoding=ENC) as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines[4:7] + lines[10:15] + lines[-len(rows_p) - 6:-len(rows_p) - 2]))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["render", "sheet", "report"])
    a = ap.parse_args()
    os.chdir(ROOT)
    os.makedirs(OUT, exist_ok=True)
    {"render": do_render, "sheet": do_sheet, "report": do_report}[a.cmd]()


if __name__ == "__main__":
    main()
