#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Отчёт приёмочной партии по логическим ассетам (P1-B, после acceptance_run.py run). Модель не грузит.

Читает только то, что записал прогон: снимок batches/<id>.json, runs/<id>/execution.json, photo/outputs.json,
derived/derived.json, qa/qa.json - и строит листы для глаз. Строки отчёта двух родов:
  авто    - AI job (запись, хэши, файлы), geometry и alpha/footprint (числа cover_check / tile_qa.footprint по
            порогам ниже), derive (файлы и хэши вывода): PASS / WARN / FAIL машиной;
  человек - semantic identity, family consistency, игровой просмотр, вердикт специального QA: всегда
            PENDING_HUMAN со ссылкой на лист. Отчёт их не ставит (решение - за Vitali).
Каждое задание - seed, raw sha256, sha256 итоговых кадров, input_hash, prompt_rev, generator_rev, execution id.
Упавшее задание не перезапускается и не прячется: строка FAIL с причиной.

    py -3.13 tools/hdart/acceptance_report.py acc-xxxxxxxxxxxx
-> runs/<id>/report/report.md, report.json и листы рядом.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import numpy as np                        # noqa: E402
from PIL import Image                     # noqa: E402

import acceptance_plan as ap              # noqa: E402
import acceptance_run as arun             # noqa: E402
import map_mockup as mm                   # noqa: E402
import tile_qa as tq                      # noqa: E402

ENC = "utf-8-sig"
# пороги автоматики - подсказка, куда смотреть, а не приёмка
GEOM = {"cover_warn": 0.85, "cover_fail": 0.70, "spill_warn": 0.05, "spill_fail": 0.15,
        "over_warn": 1.0, "over_fail": 4.0}
ALPHA = {"semi_warn": 0.02, "semi_fail": 0.05, "shadow_warn": 0.02, "shadow_fail": 0.05}
PENDING = "PENDING_HUMAN"


def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding=ENC) as f:
        return json.load(f)


def key_of(rel):
    """'FRNITURE.PCK/9.png' -> 'FRNITURE:9'"""
    s, f = rel.split("/")[-2:]
    return "%s:%s" % (s[:-4], f[:-4])


def worst(*vals):
    order = ("PASS", "N/A", "WARN", "FAIL")
    vals = [v for v in vals if v]
    return max(vals, key=order.index) if vals else "N/A"


def geometry(m):
    over = max(m["overflow_px"].values())
    if m["cover"] < GEOM["cover_fail"] or m["spill"] > GEOM["spill_fail"] or over > GEOM["over_fail"]:
        return "FAIL"
    if m["cover"] < GEOM["cover_warn"] or m["spill"] > GEOM["spill_warn"] or over > GEOM["over_warn"]:
        return "WARN"
    return "PASS"


def alpha(m):
    if m["semi"] > ALPHA["semi_fail"] or m["shadow"] > ALPHA["shadow_fail"]:
        return "FAIL"
    if m["semi"] > ALPHA["semi_warn"] or m["shadow"] > ALPHA["shadow_warn"]:
        return "WARN"
    return "PASS"


def luma(im):
    a = np.asarray(im.convert("RGBA")).astype(np.float32)
    return 0.299 * a[:, :, 0] + 0.587 * a[:, :, 1] + 0.114 * a[:, :, 2], a[:, :, 3] > 128


def body_corr(a, b):
    """Корреляция яркости двух HD-кадров по общему телу - одинаково ли нарисована форма (подсказка)."""
    la, ma = luma(a)
    lb, mb = luma(b)
    m = ma & mb
    if m.sum() < 50:
        return None
    x, y = la[m] - la[m].mean(), lb[m] - lb[m].mean()
    d = float(np.sqrt((x * x).sum() * (y * y).sum()))
    return round(float((x * y).sum() / d), 3) if d else None


def body_rgb(im):
    a = np.asarray(im.convert("RGBA")).astype(np.float32)
    m = a[:, :, 3] > 128
    return [round(float(a[:, :, c][m].mean()), 1) for c in range(3)] if m.any() else None


def cell(im, text):
    return tq.label(im.convert("RGBA"), text)


def column(rows):
    w = max(r.width for r in rows)
    out = Image.new("RGBA", (w, sum(r.height + 8 for r in rows)), tq.BG)
    y = 0
    for r in rows:
        out.alpha_composite(r, (0, y))
        y += r.height + 8
    return out


def job_status(j, rec, outs, photo):
    """AI job: запись этой партии, хэш задания, raw и каждый кадр - те, что записаны."""
    if rec is None:
        return "FAIL", "прогона нет (только dry-run)"
    o = outs.get(j["job_id"])
    if not o:
        return "FAIL", "obj_photo не записал ответа (код прогона %s)" % rec.get("returncode")
    if o.get("job_hash") != arun.ar.h12(j):
        return "FAIL", "ответ записан для другого задания (job_hash)"
    raw = os.path.join(photo, o["raw"])
    if not os.path.exists(raw) or arun.sha256_file(raw) != o["raw_sha256"]:
        return "FAIL", "raw нет или изменился после записи"
    for rel in j["expected_outputs"]:
        p = os.path.join(photo, rel)
        if not os.path.exists(p) or o["files"].get(rel) != arun.sha256_file(p):
            return "FAIL", "кадр %s нет или не тот" % rel
    if j.get("reference"):
        ref = outs.get(j["reference"]["job_id"], {})
        if o.get("reference_job") != j["reference"]["job_id"] or \
                o.get("reference_output_sha256") != ref.get("raw_sha256"):
            return "FAIL", "опора не ответ %s этой партии" % j["reference"]["job_id"]
    return "PASS", ""


def report(batch_id, root=arun.RUNS):
    snap = arun.load_snapshot(batch_id)
    d = arun.run_dir(batch_id, root)
    photo, derived = os.path.join(d, "photo"), os.path.join(d, "derived")
    rd = os.path.join(d, "report")
    os.makedirs(rd, exist_ok=True)
    hist = load_json(os.path.join(d, "execution.json"), [])
    runs = [r for r in hist if not r.get("dry_run")]
    rec = runs[-1] if runs else None
    exec_id = "%s/run%d@%s" % (batch_id, len(runs), rec["started"]) if rec else None
    outs = arun.load_outputs(photo)
    ders = load_json(os.path.join(derived, "derived.json"), {})
    qas = load_json(os.path.join(d, "qa", "qa.json"), [])
    world = mm.World()
    gen = snap["generator"]

    jobs_out, assets_out = [], []
    by_asset = {}
    for j in snap["jobs"]:
        by_asset.setdefault(j["asset_id"], []).append(j)
        st, why = job_status(j, rec, outs, photo)
        o = outs.get(j["job_id"], {})
        jobs_out.append({"job_id": j["job_id"], "name": j["name"], "asset_id": j["asset_id"], "view": j["view"],
                         "status": st, "why": why, "seed": j["seed"], "input_hash": j["input_hash"],
                         "raw_sha256": o.get("raw_sha256"), "final_sha256": o.get("files", {}),
                         "reference_job": o.get("reference_job"),
                         "reference_output_sha256": o.get("reference_output_sha256"),
                         "prompt_rev": gen["prompt_rev"], "generator_rev": gen["generator_rev"],
                         "execution_id": exec_id})
    jst = {x["job_id"]: x for x in jobs_out}

    for a in snap["assets"]:
        aid = a["asset_id"]
        js = by_asset.get(aid, [])
        row = {"asset_id": aid, "identity": a["identity"]["text"], "strategy": a["generation_strategy"],
               "jobs": [j["job_id"] for j in js], "sheets": {}, "numbers": {}}
        row["ai_jobs"] = worst(*[jst[j["job_id"]]["status"] for j in js])
        row["ai_why"] = "; ".join("%s: %s" % (j["job_id"], jst[j["job_id"]]["why"]) for j in js
                                  if jst[j["job_id"]]["why"])
        geo, alp, cells = [], [], []
        for j in js:
            for t, rel in zip(j["take"], j["expected_outputs"]):
                key = t.split("@")[0]
                p = os.path.join(photo, rel)
                if not os.path.exists(p):
                    geo.append("FAIL")
                    alp.append("FAIL")
                    continue
                o4, hd = tq.orig_x4(world, key), tq.load_hd(p)
                m = tq.footprint(o4, hd)
                row["numbers"][key] = {k: m[k] for k in ("cover", "spill", "semi", "shadow", "overflow_px")}
                geo.append(geometry(m))
                alp.append(alpha(m))
                cells.append(tq.side([cell(o4, "%s original x4" % key),
                                      cell(hd, "%s HD (%s %s)" % (key, j["job_id"], j["view"] or ""))]))
        row["geometry"], row["alpha_footprint"] = worst(*geo), worst(*alp)
        if cells:
            row["sheets"]["identity"] = tq.save(column(cells), os.path.join(rd, "%s_identity.png" % aid.replace(":", "_")))
        row["semantic_identity"] = PENDING

        # вывод: файлы и хэши; лист семейства - основа и все выведенные рядом, с подсказкой одинаковости
        dvs = [(j, dv) for j in js for dv in j["derive"]]
        if dvs:
            bad, fam = [], []
            for j, dv in dvs:
                for rel in dv["outputs"]:
                    r = ders.get(rel)
                    p = os.path.join(derived, rel)
                    base_sha = outs.get(j["job_id"], {}).get("files", {}).get(r["derived_from"]) if r else None
                    if not r or not os.path.exists(p) or arun.sha256_file(p) != r["sha256"] \
                            or r["derived_from_sha256"] != base_sha:
                        bad.append(rel)
                        continue
                    if rel == dv["outputs"][0] or len(dv["member_src"]) > 1:
                        bk = key_of(r["derived_from"])
                        base = tq.load_hd(os.path.join(photo, r["derived_from"]))
                        hd = tq.load_hd(p)
                        ref = base.transpose(Image.FLIP_LEFT_RIGHT) if dv["relation"] == "mirror" else base
                        mk = key_of(rel)
                        m = tq.footprint(tq.orig_x4(world, mk), hd)
                        c = body_corr(ref, hd)
                        row["numbers"]["%s <- %s" % (mk, bk)] = {"relation": dv["relation"], "form_corr": c,
                                                                  "cover": m["cover"], "spill": m["spill"],
                                                                  "files": len(dv["outputs"])}
                        fam.append(tq.side([cell(tq.orig_x4(world, mk), "%s original x4" % mk),
                                            cell(hd, "%s %s of %s, corr %s" % (mk, dv["relation"], bk, c))]))
            row["derive"] = "FAIL" if bad else "PASS"
            row["derive_bad"] = bad[:8]
            if fam:
                row["sheets"]["family"] = tq.save(column(cells[:1] + fam),
                                                  os.path.join(rd, "%s_family.png" % aid.replace(":", "_")))
            row["family_consistency"] = PENDING
        else:
            row["derive"] = "N/A"
            row["family_consistency"] = PENDING if len(js) > 1 else "N/A"

        # специальный QA - из qa.json прогона, вердикт не ставится
        keys = {t.split("@")[0] for j in js for t in j["take"]}
        special = []
        for q in qas:
            if q.get("key") in keys or set(q.get("from", [])) & keys:
                attn = q.get("footprint", q.get("derived", {})).get("attention", []) if q["kind"] != "tile_qa_3x3" else []
                special.append({"kind": q["kind"], "attention": attn, "suspect": q.get("suspect"),
                                "source_attention": q.get("source", {}).get("attention"),
                                "sheet": q.get("sheet"), "map_sheet": q.get("map_sheet"), "verdict": PENDING})
        row["special_qa"] = special

        # игровой просмотр: вырез карты на месте задания (map_mockup, как render игры; без освещения боя)
        for j in js:
            if all(os.path.exists(os.path.join(photo, r)) for r in j["expected_outputs"]):
                placed = [(t.split("@")[0], tuple(at)) for t, at in zip(j["take"], j["at"])]
                row["sheets"]["map_%s" % j["job_id"]] = tq.place_sheet(
                    photo, j["map"], placed, os.path.join(rd, "%s_map.png" % j["name"]), "HD on map, %s" % j["map"])
        row["game_view"] = PENDING
        assets_out.append(row)

    views = alt_views(snap, photo, rd, world)
    doc = {"batch_id": batch_id, "execution_id": exec_id, "returncode": rec and rec.get("returncode"),
           "missing_outputs": rec and rec.get("missing_outputs"), "generator": gen,
           "thresholds": {"geometry": GEOM, "alpha": ALPHA}, "assets": assets_out, "jobs": jobs_out,
           "alt_views": views}
    with open(os.path.join(rd, "report.json"), "w", encoding=ENC) as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    with open(os.path.join(rd, "report.md"), "w", encoding=ENC) as f:
        f.write(markdown(doc, rd))
    return doc


def alt_views(snap, photo, rd, world):
    """Два бока одного предмета: A, A перевёрнутый, B - один ли это предмет (решает человек)."""
    out = []
    for jb in snap["jobs"]:
        if not jb.get("reference"):
            continue
        ja = next(j for j in snap["jobs"] if j["job_id"] == jb["reference"]["job_id"])
        pa, pb = (os.path.join(photo, j["expected_outputs"][0]) for j in (ja, jb))
        if not (os.path.exists(pa) and os.path.exists(pb)):
            out.append({"a": ja["job_id"], "b": jb["job_id"], "note": "ответа нет"})
            continue
        ka, kb = (j["take"][0].split("@")[0] for j in (ja, jb))
        ha, hb = tq.load_hd(pa), tq.load_hd(pb)
        oa, ob = tq.orig_x4(world, ka), tq.orig_x4(world, kb)
        sheet = tq.side([cell(oa, "%s original (A)" % ka), cell(ha, "%s HD (A)" % ka),
                         cell(ha.transpose(Image.FLIP_LEFT_RIGHT), "A flipped"),
                         cell(ob, "%s original (B)" % kb), cell(hb, "%s HD (B)" % kb)])
        out.append({"a": ja["job_id"], "b": jb["job_id"], "keys": [ka, kb],
                    "rgb": {"orig_a": body_rgb(oa), "orig_b": body_rgb(ob), "hd_a": body_rgb(ha), "hd_b": body_rgb(hb)},
                    "form_corr_hd_b_vs_flipped_a": body_corr(ha.transpose(Image.FLIP_LEFT_RIGHT), hb),
                    "form_corr_orig_b_vs_flipped_a": body_corr(oa.transpose(Image.FLIP_LEFT_RIGHT), ob),
                    "sheet": tq.save(sheet, os.path.join(rd, "views_%s_%s.png" % (ka.replace(":", "_"),
                                                                                    kb.replace(":", "_")))),
                    "verdict": PENDING})
    return out


def rel(p, rd):
    return os.path.relpath(p, rd).replace(os.sep, "/") if p else "-"


def markdown(doc, rd):
    L = ["# Приёмка %s" % doc["batch_id"], "",
         "execution id `%s`, код прогона %s, prompt_rev `%s`, generator_rev `%s` (%s)." % (
             doc["execution_id"], doc["returncode"], doc["generator"]["prompt_rev"],
             doc["generator"]["generator_rev"], doc["generator"]["status"]),
         "Недостающих ответов: %s." % (len(doc["missing_outputs"] or []) if doc["missing_outputs"] is not None else "-"),
         "",
         "Авто - машина по записям и числам (пороги в report.json). PENDING_HUMAN - решает Vitali по листу; "
         "отчёт этих строк не ставит. Игровой просмотр - вырез карты map_mockup (как рисует игра, без освещения "
         "боя).", ""]
    for a in doc["assets"]:
        L += ["## %s - %s" % (a["asset_id"], a["identity"]), "",
              "| Что | Результат |", "|---|---|",
              "| AI job(s) %s | %s (авто)%s |" % (", ".join(a["jobs"]), a["ai_jobs"],
                                                  (" - " + a["ai_why"]) if a["ai_why"] else ""),
              "| geometry | %s (авто) |" % a["geometry"],
              "| semantic identity | %s - [лист](%s) |" % (a["semantic_identity"], rel(a["sheets"].get("identity"), rd)),
              "| family consistency | %s%s |" % (a["family_consistency"],
                                                 (" - [лист](%s)" % rel(a["sheets"]["family"], rd))
                                                 if "family" in a["sheets"] else ""),
              "| alpha/footprint | %s (авто) |" % a["alpha_footprint"],
              "| derive | %s (авто)%s |" % (a["derive"], (" - " + ", ".join(a.get("derive_bad", [])))
                                            if a.get("derive_bad") else ""),
              "| специальный QA | %s |" % ("; ".join(
                  "%s: %s%s, [лист](%s)%s" % (
                      q["kind"], "внимание: " + " / ".join(q["attention"]) if q["attention"] else "вниманий нет",
                      (", suspect " + q["suspect"]) if q.get("suspect") else "", rel(q["sheet"], rd),
                      (", [карта](%s)" % rel(q["map_sheet"], rd)) if q.get("map_sheet") else "")
                  for q in a["special_qa"]) or "-"),
              "| игровой просмотр | %s - %s |" % (a["game_view"], ", ".join(
                  "[%s](%s)" % (k[4:], rel(v, rd)) for k, v in a["sheets"].items() if k.startswith("map_"))),
              "", "Числа: `%s`" % json.dumps(a["numbers"], ensure_ascii=False), ""]
    L += ["## Два бока", ""]
    for v in doc["alt_views"]:
        L += ["- %s -> %s: [лист](%s), корреляция формы B с перевёрнутым A: HD %s, оригинал %s; цвет тела %s; %s" % (
            v["a"], v["b"], rel(v.get("sheet"), rd), v.get("form_corr_hd_b_vs_flipped_a"),
            v.get("form_corr_orig_b_vs_flipped_a"), v.get("rgb"), v.get("verdict", v.get("note")))]
    L += ["", "## Задания", "",
          "| job | status | seed | input_hash | raw sha256 | итоговые кадры sha256 | ref |", "|---|---|---|---|---|---|---|"]
    for j in doc["jobs"]:
        L.append("| %s %s | %s%s | %d | %s | %s | %s | %s |" % (
            j["job_id"], j["name"], j["status"], (" " + j["why"]) if j["why"] else "", j["seed"], j["input_hash"],
            (j["raw_sha256"] or "-")[:16], ", ".join("%s %s" % (k, v[:16]) for k, v in j["final_sha256"].items()) or "-",
            ("%s %s" % (j["reference_job"], j["reference_output_sha256"][:16])) if j["reference_job"] else "-"))
    return "\n".join(L) + "\n"


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    doc = report(sys.argv[1])
    for a in doc["assets"]:
        print("%-14s ai %-4s geo %-4s alpha %-4s derive %-4s qa %s" % (
            a["asset_id"], a["ai_jobs"], a["geometry"], a["alpha_footprint"], a["derive"],
            ", ".join(q["kind"] + ("!" if q["attention"] or q.get("suspect") else "") for q in a["special_qa"]) or "-"))
    print("отчёт: %s" % os.path.join(arun.run_dir(sys.argv[1]), "report", "report.md"))


if __name__ == "__main__":
    main()
