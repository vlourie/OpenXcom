#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""OLD AUTO против RESTORE на тех же 30 кадрах партии restore-batch-v1 (специалист 03.10, передал Vitali).

A - старый простой генератор Vitali: obj_photo --engine qwen21 без --rgba (Qwen-Image-2.1 полная, 40 шагов,
cfg 4, 1 Мп, промпт PHOTO «фотография настоящей вещи», подложка pick_background, вырезка edge). Выбрал Vitali
03.10 в чате; первый прогон (турбо qwen21_turbo_rgba, gpuq #339) - не тот генератор, лежит в A_turbo, его лист
и ключ (sheet_turbo, key_turbo.json) недействительны.
Описание и зерно - те же, что у RESTORE (report.json и jobs.json партии), чтобы различался только способ.
B - готовые куски RESTORE (render/<НАБОР>.PCK/<кадр>.png), ничего не перерисовывается.

Модель этот скрипт не грузит: A рисует obj_photo через очередь (команда печатается в jobs).

    py -3.13 tools/hdart/oldauto_ab_v1.py jobs      задания A (art/.../oldauto-ab-v1/jobs_a.json) и команда gpuq
    py -3.13 tools/hdart/oldauto_ab_v1.py metrics   простые метрики формы RESTORE против разметки (без генерации)
    py -3.13 tools/hdart/oldauto_ab_v1.py sheet     слепой лист: оригинал | L | R, порядок по зерну, ключ в key.json
    py -3.13 tools/hdart/oldauto_ab_v1.py report    раскрыть ключ по заполненному verdicts_ab.tsv
"""
import argparse
import csv
import hashlib
import io
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for _p in (HERE, os.path.join(HERE, "..")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np                                  # noqa: E402
from PIL import Image, ImageDraw, ImageFont         # noqa: E402

ENC = "utf-8-sig"
SRC = "art/objects/generation/probes/restore-batch-v1"
OUT = "art/objects/generation/probes/oldauto-ab-v1"
PY_QWEN = "E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe"
A_GEN = {"name": "obj_photo --engine qwen21 (Qwen-Image-2.1 полная, 40 шагов, cfg 4, 1 Мп, промпт PHOTO)",
         "args": ["--engine", "qwen21"], "status": "старый генератор фото, выбран Vitali 03.10 для A/B"}
SHEET_SEED = 31003                                # порядок L/R на листе; ключ - key.json, Vitali его не видит
CHOICES = ("L", "R", "=", "BOTH_FAIL")


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


def items():
    """30 кадров партии RESTORE: asset_id, what, seed, путь куска B."""
    rep = rd_json(SRC + "/report.json")
    seeds = {j["asset_id"]: j["seed"] for j in rd_json(SRC + "/jobs.json")}
    res = []
    for x in rep["items"]:
        if "piece" not in x:
            continue
        res.append({"asset_id": x["asset_id"], "what": x["what"], "seed": seeds[x["asset_id"]],
                    "b": x["piece"], "machine": x["machine_final"]})
    if len(res) != 30:
        raise SystemExit("в партии RESTORE %d нарисованных кадров, ждал 30" % len(res))
    return res


def a_piece(asset):
    s, n = asset.split(":")
    return "%s/A/%s.PCK/%s.png" % (OUT, s, n)


# ---------------------------------------------------------------- задания A

def do_jobs():
    jobs = []
    for i, it in enumerate(items(), 1):
        s, n = it["asset_id"].split(":")
        jobs.append({"name": "a%02d_%s_%s" % (i, s.lower(), n), "anim": "%s:%s" % (s, n), "what": it["what"],
                     "seed": it["seed"], "asset_id": it["asset_id"]})
    os.makedirs(os.path.join(ROOT, OUT, "A"), exist_ok=True)
    wr_json(OUT + "/jobs_a.json", jobs)
    gen = A_GEN
    wr_json(OUT + "/spec.json", {
        "what": "OLD AUTO (A) против RESTORE (B), те же 30 кадров, те же описания и зёрна",
        "a_generator": gen["name"], "a_args": gen["args"], "a_status": gen["status"],
        "a_prompt": "PHOTO из obj_photo.py, {what} - описание партии RESTORE",
        "a_turbo_void": "A_turbo, jobs_a_turbo.json, spec_turbo.json, sheet_turbo, key_turbo.json - турбо, не тот генератор",
        "b": SRC + "/render (готовые куски, baseline " + rd_json(SRC + "/report.json")["baseline_sha256"][:12] + ")",
        "jobs_sha256": hashlib.sha256(open(os.path.join(ROOT, OUT, "jobs_a.json"), "rb").read()).hexdigest(),
        "sheet_seed": SHEET_SEED})
    cmd = [PY_QWEN, "tools/hdart/obj_photo.py", "--jobs", OUT + "/jobs_a.json", "--out", OUT + "/A"] + gen["args"]
    print("заданий A: %d -> %s/jobs_a.json" % (len(jobs), OUT))
    print("py -3 tools/gpuq.py add --name oldauto_ab_photo --prio 1 -- " + " ".join(cmd))


# ---------------------------------------------------------------- метрики формы

def world():
    import map_mockup as mm
    return mm.World()


def orig(w, asset):
    s, n = asset.split(":")
    return np.asarray(w.sprite(s.lower(), int(n), None).convert("RGBA"), np.float32)


def down(piece, shape):
    """Кусок x4 -> сетка оригинала: усреднение 4x4 с учётом альфы (премультипликация)."""
    a = np.asarray(Image.open(os.path.join(ROOT, piece)).convert("RGBA"), np.float32)
    h, w = shape
    a = a[:h * 4, :w * 4].reshape(h, 4, w, 4, 4)
    al = a[..., 3:4] / 255.0
    rgb = (a[..., :3] * al).sum((1, 3)) / np.maximum(al.sum((1, 3)), 1e-6)
    return np.concatenate([rgb, al.mean((1, 3)) * 255.0], -1)


def lum(a):
    return a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114


def sobel(y):
    p = np.pad(y, 1, mode="edge")
    gx = (p[:-2, 2:] + 2 * p[1:-1, 2:] + p[2:, 2:]) - (p[:-2, :-2] + 2 * p[1:-1, :-2] + p[2:, :-2])
    gy = (p[2:, :-2] + 2 * p[2:, 1:-1] + p[2:, 2:]) - (p[:-2, :-2] + 2 * p[:-2, 1:-1] + p[:-2, 2:])
    return gx, gy


def dilate(m):
    p = np.pad(m, 1)
    r = np.zeros_like(m)
    for dy in (0, 1, 2):
        for dx in (0, 1, 2):
            r |= p[dy:dy + m.shape[0], dx:dx + m.shape[1]]
    return r


def blur(x):
    k = np.array([1, 4, 6, 4, 1], np.float32) / 16
    p = np.pad(x, ((0, 0), (2, 2)), mode="edge")
    x = sum(k[i] * p[:, i:i + x.shape[1]] for i in range(5))
    p = np.pad(x, ((2, 2), (0, 0)), mode="edge")
    return sum(k[i] * p[i:i + x.shape[0]] for i in range(5))


def shape_metrics(o, r):
    """o, r - RGBA на сетке оригинала. Всё - внутри силуэта оригинала, без края (край навязан вырезкой)."""
    m = o[..., 3] > 127
    inner = m & ~dilate(~m)                         # без пикселя края: контур совпадает по построению
    yo, yr = lum(o), lum(r)
    res = {"pixels": int(m.sum()), "inner": int(inner.sum())}
    z = lambda y, k: (y - y[k].mean()) / (y[k].std() + 1e-6)
    res["lum_mae"] = float(np.abs(yo - yr)[m].mean())
    res["lum_shift"] = float(yr[m].mean() - yo[m].mean())
    res["contrast_ratio"] = float((yr[m].std() + 1) / (yo[m].std() + 1))
    res["lum_corr"] = float((z(yo, m) * z(yr, m))[m].mean())
    gox, goy = sobel(yo)
    grx, gry = sobel(yr)
    go, gr = np.hypot(gox, goy), np.hypot(grx, gry)
    k = inner if inner.sum() >= 20 else m
    res["grad_corr"] = float((z(go, k) * z(gr, k))[k].mean())
    cos = (gox * grx + goy * gry) / (go * gr + 1e-6)
    wgt = go * gr
    res["orient_agree"] = float((cos * wgt)[k].sum() / (wgt[k].sum() + 1e-6))
    # кромки: верхняя четверть градиента внутри силуэта; совпадение с допуском в пиксель (Dice)
    eo = (go >= np.quantile(go[k], 0.75)) & k
    er = (gr >= np.quantile(gr[k], 0.75)) & k
    hit_o = (eo & dilate(er)).sum() / max(eo.sum(), 1)
    hit_r = (er & dilate(eo)).sum() / max(er.sum(), 1)
    res["edge_dice"] = float(2 * hit_o * hit_r / max(hit_o + hit_r, 1e-6))
    res["edge_recall"] = float(hit_o)
    # SSIM по яркости, гаусс 5x5, среднее внутри силуэта
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    mo, mr = blur(yo), blur(yr)
    vo, vr = blur(yo * yo) - mo * mo, blur(yr * yr) - mr * mr
    cov = blur(yo * yr) - mo * mr
    ss = ((2 * mo * mr + c1) * (2 * cov + c2)) / ((mo * mo + mr * mr + c1) * (vo + vr + c2))
    res["ssim"] = float(ss[m].mean())
    return res


# чем больше, тем лучше (True) или тем хуже (False)
HIGHER_BETTER = {"lum_corr": True, "grad_corr": True, "orient_agree": True, "edge_dice": True,
                 "edge_recall": True, "ssim": True, "lum_mae": False, "abs_lum_shift": False,
                 "abs_log_contrast": False}


def auc(fail, ok, higher_better):
    """Доля пар (FAIL, PASS), где PASS лучше FAIL; ничья - половина. 0.5 - мера ничего не различает."""
    s = 0.0
    for f in fail:
        for p in ok:
            if p == f:
                s += 0.5
            elif (p > f) == higher_better:
                s += 1
    return s / (len(fail) * len(ok))


def best_cut(fail, ok, higher_better):
    """Лучший порог на этих же данных (оптимистично: подобран на тех же 29 кадрах)."""
    vals = sorted(set(fail + ok))
    best = None
    for t in vals:
        if higher_better:
            tp, fp = sum(v <= t for v in fail), sum(v <= t for v in ok)
        else:
            tp, fp = sum(v >= t for v in fail), sum(v >= t for v in ok)
        acc = (tp + len(ok) - fp) / (len(fail) + len(ok))
        if best is None or acc > best[0]:
            best = (acc, t, tp, fp)
    return best


def loo_acc(fail, ok, higher_better):
    """Порог, подобранный без проверяемого кадра (leave-one-out): честнее, чем best_cut."""
    data = [(v, 1) for v in fail] + [(v, 0) for v in ok]
    right = 0
    for i, (v, y) in enumerate(data):
        rest = data[:i] + data[i + 1:]
        _a, t, _tp, _fp = best_cut([x for x, c in rest if c], [x for x, c in rest if not c], higher_better)
        pred = (v <= t) if higher_better else (v >= t)
        right += int(pred == bool(y))
    return right / len(data)


def do_metrics():
    lab = {r["asset_id"]: r for r in rd_tsv(OUT + "/labels.tsv")}
    w = world()
    rows = []
    rng = np.random.default_rng(1)
    shuf = {k: [] for k in HIGHER_BETTER if k in ("ssim", "edge_dice", "grad_corr", "lum_corr", "orient_agree")}
    for it in items():
        o = orig(w, it["asset_id"])
        r = down(it["b"], o.shape[:2])
        m = shape_metrics(o, r)
        ctl = shape_metrics(o, o)                   # контроль меры: оригинал против себя - идеал
        # второй контроль: внутренность рендера перемешана - структура убита, цвета те же
        idx = np.argwhere(o[..., 3] > 127)
        perm = idx[rng.permutation(len(idx))]
        sh = r.copy()
        sh[idx[:, 0], idx[:, 1], :3] = r[perm[:, 0], perm[:, 1], :3]
        ms = shape_metrics(o, sh)
        for k in shuf:
            shuf[k].append((m[k], ms[k]))
        m["abs_lum_shift"] = abs(m["lum_shift"])
        m["abs_log_contrast"] = abs(float(np.log(m["contrast_ratio"])))
        rows.append(dict(asset_id=it["asset_id"], label=lab[it["asset_id"]]["label"], machine=it["machine"],
                         **{k: round(v, 4) if isinstance(v, float) else v for k, v in m.items()},
                         ctl_ssim=round(ctl["ssim"], 4), ctl_edge_dice=round(ctl["edge_dice"], 4)))
    head = list(rows[0].keys())
    wr_tsv(OUT + "/metrics_restore.tsv", head, rows)
    fail = [r for r in rows if r["label"] == "FAIL"]
    ok = [r for r in rows if r["label"] == "PASS"]
    lines = ["# Метрики формы RESTORE против разметки (без генерации)", "",
             "Разметка: labels.tsv (специалист 03.10, передал Vitali): FAIL %d, PASS %d, REVIEW %d - REVIEW в "
             "разделение не входит." % (len(fail), len(ok), sum(r["label"] == "REVIEW" for r in rows)),
             "Сетка - оригинал 32x40: кусок x4 усреднён 4x4 с альфой. Всё внутри силуэта оригинала; градиент и "
             "кромки - без пикселя края (контур навязан вырезкой, R-210).",
             "Контроль меры: оригинал против себя - ssim %.3f, edge_dice %.3f у всех 30." % (
                 min(r["ctl_ssim"] for r in rows), min(r["ctl_edge_dice"] for r in rows)),
             "Контроль чувствительности (медиана по 30): рендер как есть / внутренность перемешана - " + ", ".join(
                 "%s %.2f / %.2f" % (k, np.median([a for a, _b in v]), np.median([b for _a, b in v]))
                 for k, v in shuf.items()) + ". Мера структуру видит, если второе число заметно ниже.", "",
             "AUC - доля пар (FAIL, PASS), где PASS лучше: 0.5 не различает, 1.0 разделяет полностью. "
             "Порог на этих же 29 - оптимистичная точность; LOO - порог подобран без проверяемого кадра.", "",
             "| мера | лучше | FAIL медиана | PASS медиана | AUC | точность порога | LOO |",
             "|---|---|---|---|---|---|---|"]
    summary = {}
    for k, hb in HIGHER_BETTER.items():
        fv, pv = [r[k] for r in fail], [r[k] for r in ok]
        a = auc(fv, pv, hb)
        acc, t, tp, fp = best_cut(fv, pv, hb)
        loo = loo_acc(fv, pv, hb)
        summary[k] = {"auc": a, "best_acc": acc, "threshold": t, "fail_caught": tp, "pass_flagged": fp, "loo": loo}
        lines.append("| %s | %s | %.3f | %.3f | %.2f | %.2f (порог %.3f: FAIL %d/%d, PASS в брак %d/%d) | %.2f |" % (
            k, "выше" if hb else "ниже", float(np.median(fv)), float(np.median(pv)), a, acc, t, tp, len(fv), fp,
            len(pv), loo))
    lines += ["", "## По кадрам", "", "| кадр | разметка | машина | ssim | edge_dice | grad_corr | lum_corr | lum_mae |",
              "|---|---|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: (r["label"], r["ssim"])):
        lines.append("| %s | %s | %s | %.3f | %.3f | %.3f | %.3f | %.1f |" % (
            r["asset_id"], r["label"], r["machine"], r["ssim"], r["edge_dice"], r["grad_corr"], r["lum_corr"],
            r["lum_mae"]))
    with open(os.path.join(ROOT, OUT, "metrics.md"), "w", encoding=ENC) as f:
        f.write("\n".join(lines) + "\n")
    wr_json(OUT + "/metrics_summary.json", summary)
    for k, v in sorted(summary.items(), key=lambda kv: -abs(kv[1]["auc"] - 0.5)):
        print("%-17s AUC %.2f  порог %.2f  LOO %.2f" % (k, v["auc"], v["best_acc"], v["loo"]))
    print("-> %s/metrics.md" % OUT)


# ---------------------------------------------------------------- слепой лист

def on_floor(im, size):
    bg = Image.new("RGBA", size, (38, 38, 42, 255))
    im = im.convert("RGBA").resize(size, Image.LANCZOS if im.width > size[0] else Image.NEAREST)
    bg.alpha_composite(im)
    return bg


def do_sheet():
    its = items()
    miss = [it["asset_id"] for it in its if not os.path.exists(os.path.join(ROOT, a_piece(it["asset_id"])))]
    if miss:
        raise SystemExit("нет кусков A у %d: %s" % (len(miss), " ".join(miss)))
    rng = random.Random(SHEET_SEED)
    key, rows = {}, []
    w = world()
    cw, ch = 256, 320
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 18)
    cells = []
    for i, it in enumerate(its, 1):
        a_left = rng.random() < 0.5
        key[it["asset_id"]] = {"row": i, "L": "A" if a_left else "B", "R": "B" if a_left else "A"}
        s, n = it["asset_id"].split(":")
        o = w.sprite(s.lower(), int(n), None).convert("RGBA").resize((128, 160), Image.NEAREST)
        a, b = Image.open(os.path.join(ROOT, a_piece(it["asset_id"]))), Image.open(os.path.join(ROOT, it["b"]))
        cells.append((i, it["asset_id"], o, a if a_left else b, b if a_left else a))
        rows.append({"row": i, "asset_id": it["asset_id"], "better": "", "L": "", "R": "", "note": ""})
    os.makedirs(os.path.join(ROOT, OUT, "sheet"), exist_ok=True)
    for part in range(0, len(cells), 5):
        chunk = cells[part:part + 5]
        sh = Image.new("RGBA", (3 * (cw + 8) + 8, len(chunk) * (ch + 30)), (18, 18, 18, 255))
        d = ImageDraw.Draw(sh)
        for r, (i, aid, o, left, right) in enumerate(chunk):
            y = r * (ch + 30)
            d.text((8, y + 4), "%d  %s" % (i, aid), fill=(240, 240, 240), font=font)
            for c, (im, cap) in enumerate(((o, "оригинал"), (left, "L"), (right, "R"))):
                sh.paste(on_floor(im, (cw, ch)), (8 + c * (cw + 8), y + 28))
                d.text((8 + c * (cw + 8) + 6, y + 32), cap, fill=(255, 220, 0), font=font)
        sh.convert("RGB").save(os.path.join(ROOT, OUT, "sheet", "part_%02d.png" % (part // 5)))
    wr_json(OUT + "/key.json", key)
    p = OUT + "/verdicts_ab.tsv"
    if os.path.exists(os.path.join(ROOT, p)) and any(r["better"] or r["L"] or r["R"] for r in rd_tsv(p)):
        print("бланк %s уже заполнен - не перезаписываю" % p)
    else:
        wr_tsv(p, ["row", "asset_id", "better", "L", "R", "note"], rows)
    print("лист: %s/sheet/part_00..%02d.png, бланк %s" % (OUT, (len(cells) - 1) // 5, p))


# ---------------------------------------------------------------- раскрытие

def do_report():
    key = rd_json(OUT + "/key.json")
    vs = rd_tsv(OUT + "/verdicts_ab.tsv")
    bad = [v["asset_id"] for v in vs if v["better"] not in CHOICES]
    if bad:
        raise SystemExit("в бланке не заполнено или не из %s 'лучше': %s" % (CHOICES, " ".join(bad)))
    win = {"A": 0, "B": 0, "=": 0, "BOTH_FAIL": 0}
    passes = {"A": 0, "B": 0}
    rows = []
    for v in vs:
        k = key[v["asset_id"]]
        w = k[v["better"]] if v["better"] in ("L", "R") else v["better"]
        win[w] += 1
        pa = v[k["L"] == "A" and "L" or "R"].strip().upper()
        pb = v[k["L"] == "B" and "L" or "R"].strip().upper()
        passes["A"] += pa == "PASS"
        passes["B"] += pb == "PASS"
        rows.append("| %s | %s | %s | %s | %s | %s |" % (v["row"], v["asset_id"], w, pa or "-", pb or "-", v["note"]))
    n = len(vs)
    marked = any(v["L"].strip() or v["R"].strip() for v in vs)
    pa_s = "%d/%d" % (passes["A"], n) if marked else "не ставили"
    pb_s = "%d/%d" % (passes["B"], n) if marked else "не ставили"
    lines = ["# OLD AUTO (A) против RESTORE (B): итог слепого сравнения", "",
             "A - %s; B - RESTORE baseline партии. Ключ L/R - key.json (зерно листа %d)." % (
                 rd_json(OUT + "/spec.json")["a_generator"], SHEET_SEED), "",
             "| лучше A | лучше B | одинаково | оба брак | PASS A | PASS B |", "|---|---|---|---|---|---|",
             "| %d | %d | %d | %d | %s | %s |" % (win["A"], win["B"], win["="], win["BOTH_FAIL"], pa_s, pb_s), "",
             "| # | кадр | лучше | A | B | заметка |", "|---|---|---|---|---|---|"] + rows
    with open(os.path.join(ROOT, OUT, "report.md"), "w", encoding=ENC) as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines[4:7]))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["jobs", "metrics", "sheet", "report"])
    a = ap.parse_args()
    os.chdir(ROOT)
    os.makedirs(OUT, exist_ok=True)
    {"jobs": do_jobs, "metrics": do_metrics, "sheet": do_sheet, "report": do_report}[a.cmd]()


if __name__ == "__main__":
    main()
