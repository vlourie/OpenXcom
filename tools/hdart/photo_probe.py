"""Проба PHOTO v2 (30.09, после провала SIMPLE A/B v1): может ли текущий режим хотя бы приблизиться к
вчерашнему фотореализму, не ломая геометрию? Если нет - SIMPLE закрывается и возврат к вчерашней ветке.

  A  вчерашний photo: партия made01 (gpuq #259, 29.09) - полный Qwen-Image-2.1, 40 шагов, cfg 4, 1 Мп,
     серая подложка, промпт obj_photo.PHOTO; готовые ответы, заново не рисуются
  B  текущий режим: полный Qwen-Image-2.1 по замку, --rgba, 2 Мп, 30 шагов, cfg 4, промпт спецификации
     (obj_gen_spec.build_prompt без модификаторов); то же задание made01, то же зерно 2713 + номер

Предметы - только целиком видимые: один кусок, силуэт оригинала не касается краёв кадра (у кусков
вертолёта, фургона, хвоста самолёта - касается), не DETAIL_CRITICAL по слову, не мельче 150 пикселей.
По 2 случайно (закреплённое зерно) из четырёх типов: бытовое одиночное, корпус, мебель, лампа.

    py -3.13 tools/hdart/photo_probe.py make       # выборка, задания B, команда очереди (без видеокарты)
    py -3.13 tools/hdart/photo_probe.py record A|B
    py -3.13 tools/hdart/photo_probe.py page
    py -3.13 tools/hdart/photo_probe.py summary [verdicts.tsv]
"""
import argparse
import hashlib
import json
import os
import random
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import numpy as np                                  # noqa: E402

import detail_class as dc                           # noqa: E402
import detail_probe as dp                           # noqa: E402
import obj_gen_spec as ogs                          # noqa: E402
import simple_probe as sp                           # noqa: E402

OUT = os.path.join("art", "objects", "generation", "probes", "photo-v2")
SEED = "photo-v2"
YDAY_JOBS = os.path.join("art", "objects", "queue", "jobs_made01.json")
YDAY_OUT = os.path.join("art", "objects", "made01_photo")
YDAY_GPUQ = "259"
PER = 2
MIN_PX = 150
# тип по описанию, первое совпадение; лампа последней - «тумба с лампой» это корпус
TYPES = [
    ("household", r"toilet|washbasin|bottle|trash can|box|crate|sack"),
    ("housing", r"cabinet|barrel|chest|stove"),
    ("furniture", r"chair|armchair|stool|table|wardrobe|nightstand"),
    ("lamp", r"lamp|lantern"),
]
TITLES = {"O": "ORIGINAL x4", "A": "A yesterday photo", "B": "B full-Qwen rgba 30"}
CFG = {"title": "PHOTO v2: вчерашний фотореализм против текущего режима",
       "intro": "Целиком видимые предметы вчерашней партии, по 2 из четырёх типов, выбраны случайно. "
                "Вопрос: может ли одна сторона хотя бы приблизиться к другой по фотореализму, не ломая "
                "геометрию.",
       "key": "photo_probe_v2", "seed": SEED, "summary": "PHOTO v2: вчера (A) против текущего (B)",
       "caveat": "A - готовые ответы made01 29.09, B - текущий режим на тех же заданиях и зёрнах. Альфа у A - "
                 "заливка по контуру на серой подложке, у B - прозрачность самой модели: край по пикселям "
                 "может расходиться и без разницы в геометрии.",
       "help": "Итог по предмету (специалист): одна сторона лучше, ничья или брак у обеих. Главное - выглядит ли "
               "предмет заново нарисованной настоящей вещью или обводкой пиксельной формы. По критериям: "
               "лучше = больше настоящего материала, чище край, точнее форма и смысл, правдоподобнее свет; "
               "для PLASTIC_LOOK и PIXEL_STEP_TRACING лучше тот, у кого их меньше.",
       "buttons": [["1", "1 лучше"], ["tie", "ничья"], ["2", "2 лучше"], ["fail", "оба брак"]],
       "out": {"A": "PHOTO_A_BETTER", "B": "RGBA_B_BETTER"},
       "fixed": {"tie": "TIE", "fail": "BOTH_FAIL"},
       "outcomes": ["PHOTO_A_BETTER", "RGBA_B_BETTER", "TIE", "BOTH_FAIL"],
       "wins": {"A": ["PHOTO_A_BETTER"], "B": ["RGBA_B_BETTER"]},
       "wins_note": "Gate (специалист): A стабильно выглядит заново нарисованной настоящей вещью, а B наследует "
                    "пиксельные ступеньки - текущий RGBA-путь SIMPLE закрывается независимо от скорости."}
CRITERIA = ["PHOTOREAL_MATERIAL", "EDGE_RECONSTRUCTION", "GEOMETRY_FIDELITY", "OBJECT_IDENTITY",
            "LIGHTING", "PLASTIC_LOOK", "PIXEL_STEP_TRACING"]


def setup():
    sp.OUT = OUT
    sp.CFG = CFG
    sp.CRITERIA = CRITERIA
    sp.setup = setup
    dp.OUT = OUT
    dp.RUN = OUT                    # dp.cells берёт задания из RUN/batch_jobs.json
    dp.MODES = {}
    dp.MODES_ALL = ["A", "B"]
    dp.TITLES = TITLES
    dp.JOB_PREFIX = "photo_probe_"


def kind(what):
    for name, rx in TYPES:
        if re.search(r"\b(%s)(e?s)?\b" % rx, what.lower()):
            return name
    return None


def candidates():
    import map_mockup as mm
    w = mm.World()
    out = []
    for i, j in enumerate(dp.load(YDAY_JOBS)):
        if len(j.get("take", [])) != 1:
            continue                                    # составные и анимации - не этот вопрос
        key = j["take"][0].split("@")[0]
        s, f = key.split(":")
        a = np.asarray(w.sprite(s.lower(), int(f), None).convert("RGBA"))[:, :, 3] > 0
        edge = int(a[:, 0].sum() + a[:, -1].sum() + a[0].sum())
        rel = "%s.PCK/%s.png" % (s, f)
        why = []
        if edge:
            why.append("касается края %d" % edge)
        if a.sum() < MIN_PX:
            why.append("мелкий %d" % a.sum())
        if dc.words(j["what"]):
            why.append("DETAIL_CRITICAL: %s" % ",".join(dc.words(j["what"])))
        if not (os.path.exists(os.path.join(YDAY_OUT, rel))
                and os.path.exists(os.path.join(YDAY_OUT, "raw", j["name"] + ".png"))):
            why.append("нет вчерашнего ответа")
        k = kind(j["what"])
        if k is None:
            why.append("тип не из списка")
        out.append(dict(j, index=i, asset_id=key, rel=rel, kind=k, why=why))
    return out


def make(py):
    setup()
    cand = candidates()
    ok = [c for c in cand if not c["why"]]
    by = {}
    for c in ok:
        by.setdefault(c["kind"], []).append(c)
    print("заданий made01 в один кусок: %d, годных: %d (%s)" % (
        len(cand), len(ok), ", ".join("%s %d" % (k, len(v)) for k, v in sorted(by.items()))))
    rnd = random.Random(int(hashlib.sha256(SEED.encode()).hexdigest()[:12], 16))
    pick = []
    for name, _rx in TYPES:
        pool = by.get(name, [])
        pick += rnd.sample(pool, min(PER, len(pool)))
    template = {"head": ogs.RGBA_HEAD, "tail": ogs.RGBA_TAIL, "parts": ogs.PROMPT_V2,
                "order": list(ogs.MODIFIER_ORDER)}
    jobs = []
    for c in pick:
        j = {k: c[k] for k in ("name", "map", "at", "take", "what", "asset_id")}
        j["seed"] = ogs.SEED0 + c["index"]              # как у made01: 2713 + номер в списке (#259)
        j["expected_outputs"] = [c["rel"]]
        jobs.append(j)
        print("  %-9s %-18s %s seed %d  %s" % (c["kind"], c["asset_id"], c["name"], j["seed"], c["what"][:60]))
    dp.dump(jobs, os.path.join(OUT, "batch_jobs.json"))
    jb = [dict(j, prompt=ogs.build_prompt(template, j["what"])) for j in jobs]
    dp.dump(jb, os.path.join(OUT, "jobs_B.json"))
    b_out = os.path.join(OUT, "B", "photo")
    probe = {"batch_id": "made01", "seed": SEED, "assets": [j["asset_id"] for j in jobs],
             "strata": {c["asset_id"]: c["kind"] for c in pick},
             "modes": {"A": {"engine": "qwen21", "steps": 40, "cfg": 4.0, "mp": 1.0, "rgba": False,
                             "prompt": "obj_photo.PHOTO (grey panel)", "out": YDAY_OUT, "gpuq_job": YDAY_GPUQ},
                       "B": {"engine": "qwen21", "steps": 30, "cfg": 4.0, "mp": 2.0, "rgba": True,
                             "prompt": "obj_gen_spec.build_prompt", "out": b_out}},
             "question": __doc__.split("\n")[0]}
    dp.dump(probe, os.path.join(OUT, "probe.json"))
    with open(os.path.join(OUT, "candidates.tsv"), "w", encoding=dc.ENC) as f:
        f.write("asset_id\tjob\tkind\tpicked\twhy\twhat\n")
        chosen = {c["name"] for c in pick}
        for c in cand:
            f.write("%s\t%s\t%s\t%d\t%s\t%s\n" % (c["asset_id"], c["name"], c["kind"] or "", c["name"] in chosen,
                                                  "; ".join(c["why"]), c["what"].replace("\t", " ")))
    print("\n# B")
    print("%s tools/hdart/obj_photo.py --jobs %s --out %s --engine qwen21 --rgba --mp 2.0 --steps 30 --cfg 4.0" % (
        py, os.path.join(OUT, "jobs_B.json").replace("\\", "/"), b_out.replace("\\", "/")))


def record_a():
    """A - ответы вчерашней партии made01 (gpuq #259): только хэши и откуда они."""
    setup()
    probe = dp.load(os.path.join(OUT, "probe.json"))
    rows = []
    for j in dp.load(os.path.join(OUT, "batch_jobs.json")):
        rows.append({"name": j["name"], "asset_id": j["asset_id"], "seed": j["seed"],
                     "raw_sha256": dp.sha(os.path.join(YDAY_OUT, "raw", j["name"] + ".png")),
                     "final_sha256": dp.sha(os.path.join(YDAY_OUT, j["expected_outputs"][0])),
                     "final": j["expected_outputs"][0]})
    rec = dict(mode="A", **{k: probe["modes"]["A"][k] for k in ("engine", "steps", "cfg", "mp", "rgba", "prompt", "out")},
               run={"gpuq_job": YDAY_GPUQ, "log": os.path.join(".gpuq", "logs", YDAY_GPUQ + ".log"),
                    "jobs_file": YDAY_JOBS, "jobs_file_sha256": dp.sha(YDAY_JOBS)}, jobs=rows,
               missing=[r["name"] for r in rows if not r["raw_sha256"] or not r["final_sha256"]])
    dp.dump(rec, os.path.join(OUT, "execution_A.json"))
    print("A: %d ответов вчерашней партии, нет %d" % (len(rows), len(rec["missing"])))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["make", "record", "page", "summary"])
    ap.add_argument("mode", nargs="?", default="")
    ap.add_argument("--py", default="E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe")
    a = ap.parse_args()
    setup()
    if a.cmd == "make":
        make(a.py)
    elif a.cmd == "record":
        if a.mode == "A":
            record_a()
        elif a.mode == "B":
            return dp.record("B")
        else:
            raise SystemExit("record A|B")
    elif a.cmd == "summary":
        sp.summary(a.mode or os.path.join(OUT, "verdicts_vitali.tsv"))
    else:
        sp.page()
    return 0


if __name__ == "__main__":
    sys.exit(main())
