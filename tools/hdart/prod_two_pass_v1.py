#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""PROD_TWO_PASS_V1 - первая производственная проверка двухступенчатого конвейера (DECISIONS 2026-10-03, решение
специалиста 04.10, передал Vitali в чате): RESTORE - основной рендер, STRICT - rescue только для кадров, которые
человек забраковал после RESTORE. Мерить: RESTORE first-pass yield, STRICT rescue rate (только на RESTORE-FAIL),
итоговый yield после двух проходов, сколько кадров осталось человеку, GPU-время на готовый кадр.

Шаги:
    select   кандидаты без модели -> candidates.json и identity_list.json (карточки review_server, вид «десятка»)
             Пул - ворота производства pilot_batch.select (один кадр, класс object, рукотворное, без вопросов семейства
             и другого бока, без подозрения на кусок, без семейств с перекрасками, опознание - согласие двух моделей
             или человек), но без фильтра сложной геометрии по названию: производство рисует и стулья.
             Сверх ворот: обломки по названию (photo_accept.DEBRIS, R-153); всё, что было в опытах RESTORE и STRICT
             (по нему подбирался способ - иначе выход завышен); вероятная перекраска набора без найденной связи -
             тот же номер кадра в наборе, чьё имя продолжает имя уже взятого (FOREST / FOREST_SNOW, R-166).
             Порядок - по числу мест на картах, как пойдёт производство. В список идут все годные: первые TARGET,
             чьё опознание Vitali подтвердит (CONFIRM / EDIT), и составят партию; остальные - запас.
    build    партия без ручной проверки опознания (специалист 04.10, второе решение): согласие двух моделей
             принимается для этого пилота; исключаются кадры EXCLUDE (названы специалистом) и EXCLUDE_LIKE (такие
             же по описанию: обломок, кусок машины, существо); первые TARGET остальных по порядку производства, без
             добора. -> jobs.json, descriptions.tsv (status OK: подпись = описание модели без слов стиля), excluded.tsv,
             thin.tsv. Журнал человека identity_decisions.tsv не трогается - опознание партии живёт в её файлах.
    relations  замороженные V7 (restore_batch_v1.do_relations); блокер generation.tsv «identity» снят решением
             специалиста, остальные блокеры держат кадр. Не OK - в рендер не идёт.
    freeze   baseline.json (restore_batch_v1.baseline_body); сверка с baseline RESTORE_BATCH_V1: промпт, негатив,
             вариант, ворота, правило подложки и хэши кода обязаны совпасть
    prompts  промпты (без модели)
    render   только через очередь (gpu_scripts.txt):
        py -3.13 tools/gpuq.py add --name prod_two_pass_v1_restore --cwd E:/OpenXCom -- \
            E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/render_chunks.py \
            --out art/objects/generation/probes/prod-two-pass-v1 -- \
            E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/prod_two_pass_v1.py render
    report   без модели, ПОСЛЕ рендера всех 60: report.md, sheet.png и заготовка verdicts_vitali.tsv
             (заготовка пишется один раз - запуск на середине рендера оставил бы в ней не все кадры).
    strict   второй проход, только через очередь: FAIL из verdicts_vitali.tsv путём strict_ctl_v1.do_render,
             вывод <партия>/strict/series/<SET>.PCK/<n>.png; готовое пропускается.
    third    третий проход (специалист 04.10, второе решение), только через очередь: FAIL STRICT с route STRICT из
             third/descriptions.tsv (описание - заметка Vitali по-английски), тот же путь, промпт и зерно; процессы
             third-chunk по 4 рендера (R-215). Вывод <партия>/third/strict/series. route NEED_DESCRIPTION ждёт
             описания, EXCLUDE_STRUCTURAL (часть стены) не рисуется.
Дальше: лист RESTORE для PASS/FAIL (с типом FAIL), STRICT на FAIL, лист оставшихся, отчёт. Ограничения специалиста
04.10: связи - замороженные V7; baseline-промпты не меняются, третий проход меняет только текст предмета; по ходу
партии ничего не подгоняется - новый тип ошибки записывается, партия заканчивается на том же baseline.
"""
import argparse
import csv
import glob
import json
import os
import re
import sys
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

ENC = "utf-8-sig"
PROFILE = "PROD_TWO_PASS_V1"
PROBES = os.path.join("art", "objects", "generation", "probes")
OUT = os.path.join(PROBES, "prod-two-pass-v1")
TARGET = 100
IDENT = os.path.join("art", "objects", "discovery", "asset_identity.tsv")
ID_LOG = os.path.join("art", "objects", "discovery", "identity_decisions.tsv")
# опыты, по которым подбирались RESTORE и STRICT: их кадры в проверку выхода не берутся
TUNING = ("restore-v1", "restore-v1b", "restore-v1c", "restore-batch-v1", "shape-fail-control-v1", "strict-ctl-v1")
ASSET_RX = re.compile(r"\b([A-Z][A-Z0-9_]+:\d+)\b")
REJECTED = ("UNKNOWN", "SKIP", "NOT_OBJECT")
FAIL_TYPES = (("INTERNAL_GEOMETRY", "неверная внутренняя геометрия"), ("MISSING_DETAIL", "пропала деталь"),
              ("IDENTITY", "изменилось опознание"), ("MATERIAL", "неверный материал / цвет / свет"),
              ("MALFORMED_PART", "уродливая часть"), ("OTHER", "другое"))
OLD_BASE = os.path.join(PROBES, "restore-batch-v1", "baseline.json")
SAME_AS_OLD = ("prompt", "negative", "variant", "gates", "machine", "seed0", "thin_rule", "code_sha256", "exceptions")
EXCLUDE = {a: "специалист 04.10: исключить" for a in (
    "XARMY:6", "NUKE1:7", "MILINDUSTRIALGHOUL:16", "MILBARRGHOUL:59", "MI8:14", "C_EXT_WALL_BLACK:32", "SGR_INT03:76",
    "RITUALS:1", "MADDECOR_WASTE:60", "SEASUNK6:6")}
EXCLUDE_LIKE = {
    "METRO1:104": "обломок колонны (как MADDECOR_WASTE:60, обломки)",
    "FRNITURE_WASTE:9": "обломок бетонной колонны (обломки)",
    "STATIONBITS:10": "тонкая планка - связь станции, кусок большего (как MI8:14)",
    "TOILET:10": "человек в ванне и луч света - существо и эффект (как MILBARRGHOUL:59)",
    "PLANE2:43": "антенна на жёлтой крыше самолёта - кусок машины (PLANE2:38 R-153, как MI8:14)",
    "NKF_APC_PIR_BROWN:4": "антенна набора бронемашины - кусок машины (как MI8:14)"}
STYLE_RX = ((re.compile(r"(?i)\bisometric pixel art of\s+"), ""),
            (re.compile(r"(?i),?\s*(isometric\s+)?pixel art( style)?"), ""),
            (re.compile(r"(?i),\s*isometric view\b"), ""),
            (re.compile(r"(?i)\bisometric\s+"), ""))


def read_tsv(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding=ENC) as f:
        return list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))


def dump(obj, path):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding=ENC) as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def tuning_assets():
    """Все кадры, упомянутые в json и tsv опытов TUNING (задания, вердикты, связи) -> {кадр: опыт}."""
    out = {}
    for d in TUNING:
        files = glob.glob(os.path.join(PROBES, d, "*.json")) + glob.glob(os.path.join(PROBES, d, "*.tsv"))
        if not files:
            raise SystemExit("опыт %s: нет ни одного json/tsv - список TUNING устарел" % d)
        for p in files:
            with open(p, encoding=ENC, errors="replace") as f:
                for a in ASSET_RX.findall(f.read()):
                    out.setdefault(a, d)
    return out


def set_variant(aid, taken):
    """Взятый кадр того же номера в наборе, чьё имя - начало имени этого или наоборот (FOREST:52 / FOREST_SNOW:52)."""
    s, n = aid.split(":")
    for t in taken:
        ts, tn = t.split(":")
        if tn == n and ts != s and (s.startswith(ts + "_") or ts.startswith(s + "_")):
            return t
    return None


def do_select():
    import photo_accept as pa
    import pilot_batch as pbt
    keep = pbt.GEOMETRY
    pbt.GEOMETRY = re.compile(r"(?!x)x")            # сложная геометрия - тоже производство
    try:
        cands, drop = pbt.select()
    finally:
        pbt.GEOMETRY = keep
    used = tuning_assets()
    ident = {r["asset_id"]: r for r in read_tsv(IDENT)}
    dec = {r["asset_id"]: r for r in read_tsv(ID_LOG)}
    picked, taken = [], []
    for c in sorted(cands, key=lambda c: (-c["places"], c["asset_id"])):
        aid, fam = c["asset_id"].upper(), c["family"].upper()
        key = c["asset_id"] if c["asset_id"] in ident else c["family"]
        row = ident.get(key, {})
        d = dec.get(key, {}).get("decision", "")
        card = (dec[key]["identity"] if d == "EDIT" else row.get("identity") or row.get("proposed") or "").strip()
        why = None
        if aid in used or fam in used:
            why = "был в опытах RESTORE/STRICT"
        elif pa.DEBRIS.search(c["name"]) or pa.DEBRIS.search(c["other_name"]):
            why = "обломки или кусок по названию (R-153)"
        elif d in REJECTED or (not d and row.get("status") in REJECTED):
            why = "опознание отклонено человеком"
        elif not card or card.upper() == "UNKNOWN":
            why = "нет описания на карточке"
        elif set_variant(aid, taken):
            why = "вероятная перекраска набора (R-166)"
        if why:
            drop[why] += 1
            continue
        taken.append(aid)
        picked.append(dict(c, ident_key=key, card=card,
                           confirmed=d in ("CONFIRM", "EDIT") or row.get("status") in ("HUMAN_CONFIRMED",
                                                                                         "HUMAN_EDITED")))
    os.makedirs(OUT, exist_ok=True)
    dump(picked, os.path.join(OUT, "candidates.json"))
    dump([{"category": "prod %d" % (i + 1), "asset_id": c["ident_key"], "rank": c["rank"], "places": c["places"],
           "kind": "один", "identity_status": c["level"], "identity": c["card"], "for": c["asset_id"]}
          for i, c in enumerate(picked)], os.path.join(OUT, "identity_list.json"))
    dump({"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "profile": PROFILE, "target": TARGET,
          "tuning": list(TUNING), "pool": len(cands), "listed": len(picked), "dropped": dict(drop),
          "levels": dict(Counter(c["level"] for c in picked)),
          "sets": len({c["asset_id"].split(":")[0] for c in picked})}, os.path.join(OUT, "candidates_manifest.json"))
    print("ворота производства: %d; в списке %d (цель %d, остальное - запас)" % (len(cands), len(picked), TARGET))
    print("отсев: %s" % dict(drop))
    print("уровни опознания: %s; наборов %d; уже подтверждено человеком %d" % (
        dict(Counter(c["level"] for c in picked)), len({c["asset_id"].split(":")[0] for c in picked}),
        sum(c["confirmed"] for c in picked)))
    for i, c in enumerate(picked, 1):
        print("  %3d %-26s мест %-4d %-22s %s" % (i, c["asset_id"], c["places"], c["level"], c["card"][:70]))
    if len(picked) < TARGET:
        print("НЕДОБОР: годных %d меньше цели %d" % (len(picked), TARGET))
    print("-> %s" % os.path.join(OUT, "identity_list.json"))


def use_rb():
    """restore_batch_v1 (baseline RESTORE_BATCH_V1) на папке этой партии; модуль не правится."""
    import restore_batch_v1 as rb
    out = OUT.replace("\\", "/")
    rb.OUT, rb.PROFILE = out, PROFILE
    rb.rp.OUT, rb.rp.RUN1, rb.rp.PROBE, rb.rp.ONLY = out, out, PROFILE, None
    return rb


def strict_frames():
    """Второй проход: только FAIL визуальной приёмки RESTORE (verdicts_vitali.tsv), описание и зерно - из партии."""
    vp = os.path.join(OUT, "verdicts_vitali.tsv")
    with open(vp, encoding=ENC) as f:
        ver = list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))
    with open(os.path.join(OUT, "report.json"), encoding=ENC) as f:
        rep = {x["asset_id"]: x for x in json.load(f)["items"]}
    with open(os.path.join(OUT, "jobs.json"), encoding=ENC) as f:
        seeds = {j["asset_id"]: j["seed"] for j in json.load(f)}
    if len(ver) != len(rep) or not all(v["verdict"] in ("PASS", "FAIL") for v in ver):
        raise SystemExit("визуальная приёмка RESTORE не заполнена целиком - STRICT не начинаю")
    return [{"group": "fail", "asset_id": v["asset_id"], "what": rep[v["asset_id"]]["what"],
             "seed": seeds[v["asset_id"]], "restore": rep[v["asset_id"]]["piece"], "defect": v.get("types", "")}
            for v in ver if v["verdict"] == "FAIL"]


def do_strict():
    """STRICT 27.09 ровно путём strict_ctl_v1.do_render (модуль не правится): другой список и папка."""
    import strict_ctl_v1 as sc
    out = os.path.join(OUT, "strict").replace("\\", "/")
    fr = strict_frames()
    sc.OUT, sc.frames = out, (lambda: fr)
    t0 = time.time()
    sc.do_render()
    done = [f["asset_id"] for f in fr if os.path.exists(os.path.join(ROOT, sc.piece("strict", f["asset_id"])))]
    sc.wr_json(out + "/spec.json", {
        "what": "PROD_TWO_PASS_V1 второй проход: STRICT 27.09 на FAIL визуальной приёмки RESTORE (специалист 04.10)",
        "path": "strict_ctl_v1.do_render: STYLE strict, Qwen-Image-2.1 %d шагов, cfg %g, %g Мп"
                % (sc.STEPS, sc.CFG, sc.MP),
        "what_seed": "из партии RESTORE (report.json, jobs.json)", "frames": [f["asset_id"] for f in fr],
        "done": len(done), "this_process_minutes": round((time.time() - t0) / 60, 1)})


THIRD = os.path.join(OUT, "third")
THIRD_CHUNK = 4                                     # рендеров на процесс модели (R-215)


def third_frames():
    """Третий проход (специалист 04.10): FAIL STRICT с исправленным описанием Vitali (third/descriptions.tsv,
    route STRICT); зерно то же, промпт baseline STRICT, меняется только текст предмета."""
    ver = read_tsv(os.path.join(OUT, "strict", "verdicts_vitali.tsv"))
    desc = {r["asset_id"]: r for r in read_tsv(os.path.join(THIRD, "descriptions.tsv"))}
    with open(os.path.join(OUT, "jobs.json"), encoding=ENC) as f:
        seeds = {j["asset_id"]: j["seed"] for j in json.load(f)}
    fails = [v["asset_id"] for v in ver if v["verdict"] == "FAIL"]
    if not fails or set(fails) != set(desc):
        raise SystemExit("third/descriptions.tsv не совпадает с FAIL STRICT - третий проход не начинаю")
    return [{"group": "third", "asset_id": a, "what": desc[a]["what_en"], "seed": seeds[a], "restore": "",
             "defect": desc[a]["source_ru"]} for a in fails if desc[a]["route"] == "STRICT" and desc[a]["what_en"]]


def third_chunk():
    """Процесс модели: не больше THIRD_CHUNK ещё не нарисованных кадров путём strict_ctl_v1.do_render."""
    import strict_ctl_v1 as sc
    sc.OUT = os.path.join(THIRD, "strict").replace("\\", "/")
    todo = [f for f in third_frames() if not os.path.exists(os.path.join(ROOT, sc.piece("strict", f["asset_id"])))]
    sc.frames = lambda: todo[:THIRD_CHUNK]
    sc.do_render()


def do_third():
    """Без модели: процессы third-chunk, пока всё не готово; три падения подряд без нового кадра - стоп."""
    import subprocess
    import strict_ctl_v1 as sc
    out = os.path.join(THIRD, "strict").replace("\\", "/")
    sc.OUT = out
    fr = third_frames()
    left = lambda: [f for f in fr if not os.path.exists(os.path.join(ROOT, sc.piece("strict", f["asset_id"])))]
    t0, crashes, procs, before_min = time.time(), 0, [], 0.0
    if os.path.exists(out + "/spec.json"):              # повторный запуск (добавлены описания): минуты прежних
        with open(out + "/spec.json", encoding=ENC) as f:
            old = json.load(f)
        if "processes" in old:
            procs, before_min = old["processes"], old["minutes"]
    while left() and crashes < 3:
        before, ts = len(left()), time.time()
        code = subprocess.call([sys.executable, os.path.abspath(__file__), "third-chunk"])
        made = before - len(left())
        procs.append({"exit_code": code, "made": made, "minutes": round((time.time() - ts) / 60, 1)})
        print("процесс: код %d, нарисовано %d, осталось %d" % (code, made, len(left())), flush=True)
        crashes = 0 if made else crashes + 1
    sc.wr_json(out + "/spec.json", {
        "what": "PROD_TWO_PASS_V1 третий проход: STRICT 27.09 с исправленным описанием Vitali на FAIL STRICT "
                "(специалист 04.10)",
        "path": "strict_ctl_v1.do_render: STYLE strict, Qwen-Image-2.1 %d шагов, cfg %g, %g Мп; по %d рендера на процесс"
                % (sc.STEPS, sc.CFG, sc.MP, THIRD_CHUNK),
        "what_seed": "описание - third/descriptions.tsv, зерно - jobs.json партии", "frames": [f["asset_id"] for f in fr],
        "done": len(fr) - len(left()), "processes": procs,
        "minutes": round(before_min + (time.time() - t0) / 60, 1)})
    if left():
        raise SystemExit("не нарисовано: %s" % ", ".join(f["asset_id"] for f in left()))


def clean(card):
    """Описание модели -> подпись для промпта: без слов стиля (pixel art, isometric), формулировка restore_batch_v1."""
    import restore_batch_v1 as rb
    t = card
    for rx, new in STYLE_RX:
        t = rx.sub(new, t)
    t = re.sub(r"\s+,", ",", re.sub(r"\s+", " ", t)).strip(" ,.")
    return rb.describe(t)


def do_build():
    import map_mockup as mm
    import hd_e2e_v1_run as e2e
    rb = use_rb()
    cands = json.load(open(os.path.join(OUT, "candidates.json"), encoding=ENC))
    known = {c["asset_id"] for c in cands}
    lost = sorted(set(EXCLUDE) - known)
    if lost:
        raise SystemExit("исключения специалиста не в списке кандидатов: %s" % ", ".join(lost))
    jobs, desc, excl = [], [], []
    for c in cands:
        k = c["asset_id"]
        why = EXCLUDE.get(k) or EXCLUDE_LIKE.get(k)
        if why:
            excl.append({"asset_id": k, "places": c["places"], "card": c["card"], "why": why})
            continue
        if len(jobs) >= TARGET:
            excl.append({"asset_id": k, "places": c["places"], "card": c["card"], "why": "сверх цели %d" % TARGET})
            continue
        s, f = k.split(":")
        jobs.append({"name": "bat_%s_%s" % (s.lower(), f), "job_id": "p%03d" % (len(jobs) + 1), "map": "", "at": [],
                     "take": ["%s@0" % k], "what": c["card"], "asset_id": k, "src": k,
                     "seed": rb.SEED0 + len(jobs) + 1, "stratum": "prod_two_pass", "group": "prod_two_pass",
                     "identity_how": c["level"], "identity_source": "asset_identity.tsv (согласие моделей)",
                     "output": ""})
        desc.append({"asset_id": k, "rank": c["rank"], "places": c["places"], "identity_status": c["level"],
                     "identity": c["card"], "description": clean(c["card"]), "status": "OK",
                     "note": "специалист 04.10: согласие моделей без ручной проверки"})
    jp = os.path.join(OUT, "jobs.json")
    if os.path.exists(jp) and rb.rp.load(jp) != jobs:
        raise SystemExit("jobs.json уже есть и отличается - состав партии не переписывается")
    rb.rp.dump(jp, jobs)
    for name, rows in (("descriptions.tsv", desc), ("excluded.tsv", excl)):
        p = os.path.join(OUT, name)
        if name == "descriptions.tsv" and os.path.exists(p):
            print("descriptions.tsv уже есть - не трогаю")
            continue
        with open(p, "w", encoding=ENC, newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter="\t", quoting=csv.QUOTE_NONE,
                               lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
    rb.install_rule()
    world = mm.World()
    lines = ["asset_id\tset\tthin\tby_margin\tmargin\tpanel\tpanel_margin\trule"]
    for j in jobs:
        frame = e2e.sprite_frame(world, j["asset_id"])[4]
        ps0 = rb._panels_by_margin(frame)
        ps, hit, t = rb.panels_rule(frame)
        lines.append("%s\tbatch\t%.3f\t%s\t%.0f\t%s\t%.0f\t%s" % (j["asset_id"], t, ps0[0][0], ps0[0][2], ps[0][0],
                                                                 ps[0][2], "THIN_NEUTRAL" if hit else ""))
    with open(os.path.join(OUT, "thin.tsv"), "w", encoding=ENC, newline="") as f:
        f.write("\n".join(lines) + "\n")
    print("заданий %d; исключено %d (специалист %d, такие же %d, сверх цели %d)" % (
        len(jobs), len(excl), sum(x["asset_id"] in EXCLUDE for x in excl),
        sum(x["asset_id"] in EXCLUDE_LIKE for x in excl), sum(x["why"].startswith("сверх") for x in excl)))
    print("правило тонкого края: %s" % (", ".join(x.split("\t")[0] for x in lines[1:] if x.endswith("THIN_NEUTRAL"))
                                         or "ни у кого"))
    for d in desc:
        if d["description"].lower().rstrip(".") != rb.describe(d["identity"]).lower().rstrip("."):
            print("  подпись %-24s %s" % (d["asset_id"], d["description"]))


def do_relations():
    rb = use_rb()
    base = rb.classify

    def classify(a, claims, batch, comp, questions, gen_row):
        left = " ".join(b for b in gen_row["blockers"].split() if b != "identity")
        return base(a, claims, batch, comp, questions, dict(gen_row, blockers=left))

    rb.classify = classify
    rb.do_relations()


def do_freeze():
    rb = use_rb()
    rb.do_freeze()
    new = rb.rp.load(os.path.join(OUT, "baseline.json"))["body"]
    old = rb.rp.load(OLD_BASE)["body"]
    diff = [k for k in SAME_AS_OLD if new.get(k) != old.get(k)]
    if diff:
        bad = [p for p in new["code_sha256"] if new["code_sha256"][p] != old["code_sha256"].get(p)]
        raise SystemExit("baseline не тот, что у RESTORE_BATCH_V1: %s %s" % (", ".join(diff), ", ".join(bad)))
    print("baseline совпадает с RESTORE_BATCH_V1 по: %s; к рендеру %d, задержано %d" % (
        ", ".join(SAME_AS_OLD), len(new["batch"]["render"]), len(new["batch"]["held"])))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    os.chdir(ROOT)
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["select", "build", "relations", "freeze", "prompts", "render", "report", "strict",
                                        "third", "third-chunk"])
    ap.add_argument("--max-renders", type=int, default=4)
    a = ap.parse_args()
    if a.cmd == "select":
        do_select()
    elif a.cmd == "build":
        do_build()
    elif a.cmd == "relations":
        do_relations()
    elif a.cmd == "freeze":
        do_freeze()
    elif a.cmd == "prompts":
        rb = use_rb()
        rb.rp.ONLY = set(rb.render_set())
        rb.install_rule()
        rb.install_exceptions()
        rb.rp.do_prompts()
    elif a.cmd == "strict":                        # модель - только через очередь
        do_strict()
    elif a.cmd == "third":                         # модель - только через очередь, процессы по THIRD_CHUNK
        do_third()
    elif a.cmd == "third-chunk":
        third_chunk()
    elif a.cmd == "report":                        # без модели: машинный итог и лист orig x4 | pilot | RESTORE
        rb = use_rb()
        rb.rp.ONLY = set(rb.check_baseline()["body"]["batch"]["render"])
        rb.do_report()
    else:
        rb = use_rb()
        base = rb.check_baseline()
        rb.rp.ONLY = set(base["body"]["batch"]["render"])
        rb.install_rule()
        rb.install_exceptions()
        rb.rp.do_render(a.max_renders)


if __name__ == "__main__":
    main()
