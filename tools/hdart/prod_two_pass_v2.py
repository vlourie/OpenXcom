#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""PROD_TWO_PASS_V2 - вторая производственная партия предметов (специалист 05.10, передал Vitali в чате).

Тот же конвейер, что PROD_TWO_PASS_V1 (prod_two_pass_v1.py, модуль не правится - здесь только другие папка, цель
и отбор): 150 кандидатов -> карточки опознания (быстро подтвердить или поправить, без исследования) -> итоговые
описания показать Vitali -> замороженные V7 -> RESTORE -> FAIL в STRICT -> остаток с неверным описанием в THIRD ->
остаток после THIRD в особые очереди, четвёртого общего прохода нет.

Отличия от V1:
    * кадры первой партии не берутся: все её задания (jobs.json, 50 приняты и закрыты) и исключённые специалистом
      (excluded.tsv, кроме «сверх цели» - запас V1 годится сюда);
    * опознание автоматическое (специалист 05.10 отменил ручной identity-review): прежние описания - только
      гипотезы; два судьи разных семейств по карточке контекста, при споре - арбитр (identity_auto.py). Человеку -
      только то, в чём арбитр не уверен.

Шаги (как в V1):
    select     -> candidates.json (все годные), identity_list.json (первые TARGET)
    опознание  identity_card.py (карточки) -> identity_auto.py pack / codex / merge / arbiter-pack / final
    build      по identity/auto/identity.tsv: RENDER в партию, остальное в excluded.tsv -> jobs.json, descriptions.tsv
    relations, freeze, prompts, render, report, strict, third - как в V1; модель только через очередь:
        py -3.13 tools/gpuq.py add --name prod_two_pass_v2_restore --cwd E:/OpenXCom -- \
            E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/render_chunks.py \
            --out art/objects/generation/probes/prod-two-pass-v2 -- \
            E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/prod_two_pass_v2.py render
"""
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import prod_two_pass_v1 as v1      # noqa: E402

PREV = os.path.join(v1.PROBES, "prod-two-pass-v1")
v1.PROFILE = "PROD_TWO_PASS_V2"
v1.OUT = os.path.join(v1.PROBES, "prod-two-pass-v2")
v1.THIRD = os.path.join(v1.OUT, "third")
v1.TARGET = 150
v1.EXCLUDE, v1.EXCLUDE_LIKE = {}, {}       # исключения V1 уже вне отбора (prev_batch)
v1.__file__ = os.path.abspath(__file__)    # do_third зовёт third-chunk этого файла, а не V1
_tuning = v1.tuning_assets


def prev_batch():
    """Кадры первой партии: все задания и исключённые специалистом; запас «сверх цели» не входит."""
    out = {}
    with open(os.path.join(PREV, "jobs.json"), encoding=v1.ENC) as f:
        for j in json.load(f):
            out[j["asset_id"].upper()] = "партия PROD_TWO_PASS_V1"
    for r in v1.read_tsv(os.path.join(PREV, "excluded.tsv")):
        if not r["why"].startswith("сверх цели"):
            out[r["asset_id"].upper()] = "исключён в PROD_TWO_PASS_V1"
    if len(out) < 100:
        raise SystemExit("первая партия прочиталась не целиком: %d кадров" % len(out))
    return out


def tuning_assets():
    out = _tuning()
    for a, why in prev_batch().items():
        out.setdefault(a, why)
    return out


v1.tuning_assets = tuning_assets


def do_select():
    lp = os.path.join(v1.OUT, "identity_list.json")
    if os.path.exists(lp):
        raise SystemExit("identity_list.json уже есть - карточки показаны, список не переписываю")
    import pilot_batch as pbt
    # Опознание старого агента (OLD_AGENT, без сверки второй моделью) в V1 не бралось: там опознание принималось
    # согласием моделей без человека. Здесь каждое подтверждает Vitali на карточке, поэтому оно годится как
    # черновик карточки. Без этого после V1 годных 2 (05.10). HARD (модели разошлись) не берётся: описания нет.
    keep = pbt.LEVELS
    pbt.LEVELS = dict(keep, OLD_AGENT="OLD_AGENT_CARD")
    try:
        v1.do_select()
    finally:
        pbt.LEVELS = keep
    with open(lp, encoding=v1.ENC) as f:
        full = json.load(f)
    v1.dump(full[:v1.TARGET], lp)
    os.replace(os.path.join(v1.OUT, "candidates.json"), ALL)
    print("на карточки: %d из %d годных" % (min(len(full), v1.TARGET), len(full)))


ALL = os.path.join(v1.OUT, "candidates_all.json")      # все годные отбора; candidates.json - только к build


IDENTITY = os.path.join(v1.OUT, "identity", "auto", "identity.tsv")
ID_NOTE = {"STRUCTURAL_PART": "опознание: часть конструкции, одиночным предметом не рисуется",
           "NOT_OBJECT": "опознание: не предмет (рельеф, пол, эффект)",
           "HUMAN": "опознание: арбитр не уверен - человеку"}


def do_build():
    """Описание и маршрут каждого кандидата - из автоматического опознания (identity_auto.py final -> identity.tsv;
    специалист 05.10: ручной identity-review отменён). RENDER - в партию с описанием опознания; STRUCTURAL_PART,
    NOT_OBJECT и HUMAN - в excluded.tsv со своей причиной (класс в class_decisions не пишется - это решает человек)."""
    rb = v1.use_rb()
    jp = os.path.join(v1.OUT, "jobs.json")
    if os.path.exists(jp):
        raise SystemExit("jobs.json уже есть - состав партии собран и не переписывается")
    with open(os.path.join(v1.OUT, "identity_list.json"), encoding=v1.ENC) as f:
        shown = [x["for"] for x in json.load(f)]
    with open(ALL, encoding=v1.ENC) as f:
        cands = {c["asset_id"]: c for c in json.load(f)}
    ident = {r["asset_id"]: r for r in v1.read_tsv(IDENTITY)}
    wait = [a for a in shown if ident.get(a, {}).get("route", "WAIT") == "WAIT"]
    if wait:
        raise SystemExit("опознание не закончено (WAIT): %s" % ", ".join(wait))
    use, src = [], {}
    for a in shown:
        r = ident[a]
        if r["route"] == "RENDER":
            use.append(dict(cands[a], card=r["description"].strip(), name=r["name"]))
        else:
            use.append(cands[a])
            v1.EXCLUDE[a] = ID_NOTE[r["route"]]
        src[a] = r["source"]
    print("опознание: в рендер %d, вне партии %d" % (len(use) - len(v1.EXCLUDE), len(v1.EXCLUDE)))
    v1.dump(use, os.path.join(v1.OUT, "candidates.json"))      # build V1 берёт только их
    v1.do_build()
    jobs = rb.rp.load(jp)
    for j in jobs:
        j["identity_source"] = "identity_auto.py (два судья + арбитр): " + src[j["asset_id"]]
    rb.rp.dump(jp, jobs)
    dp = os.path.join(v1.OUT, "descriptions.tsv")
    rows = v1.read_tsv(dp)
    assert len(rows) == len(jobs), (len(rows), len(jobs))
    for r in rows:
        r["note"] = "автоматическое опознание (специалист 05.10): " + src[r["asset_id"]]
    with open(dp + ".tmp", "w", encoding=v1.ENC, newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter="\t", quoting=csv.QUOTE_NONE, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    os.replace(dp + ".tmp", dp)


JUDGE = os.path.join(v1.OUT, "judge")


def auto_verdicts(stage, n):
    """Приговоры связки судей (visual_judge.py prod-verdict): FAIL - всё, кроме AUTO_ACCEPT; WAIT - не начинать."""
    ver = v1.read_tsv(os.path.join(JUDGE, stage, "verdicts_auto.tsv"))
    if len(ver) != n or any(v["route"] == "WAIT" for v in ver):
        raise SystemExit("приговоры судей %s не готовы (%d из %d) - проход не начинаю" % (stage, len(ver), n))
    return ver


def strict_frames():
    """Второй проход V2: FAIL судей RESTORE (judge/restore/verdicts_auto.tsv; специалист 05.10 - без ручной
    приёмки каждого кадра), описание и зерно - из партии, как в V1."""
    with open(os.path.join(v1.OUT, "report.json"), encoding=v1.ENC) as f:
        rep = {x["asset_id"]: x for x in json.load(f)["items"]}
    with open(os.path.join(v1.OUT, "jobs.json"), encoding=v1.ENC) as f:
        seeds = {j["asset_id"]: j["seed"] for j in json.load(f)}
    ver = auto_verdicts("restore", len(rep))
    return [{"group": "fail", "asset_id": v["asset_id"], "what": rep[v["asset_id"]]["what"],
             "seed": seeds[v["asset_id"]], "restore": rep[v["asset_id"]]["piece"], "defect": v["types"]}
            for v in ver if v["verdict"] == "FAIL"]


def third_frames():
    """Третий проход V2: FAIL судей STRICT с новым описанием автоматического пересмотра (identity_auto.py
    third-desc -> third/descriptions.tsv, route STRICT); зерно то же, меняется только текст предмета."""
    with open(os.path.join(v1.OUT, "strict", "spec.json"), encoding=v1.ENC) as f:
        n = len(json.load(f)["frames"])
    ver = auto_verdicts("strict", n)
    desc = {r["asset_id"]: r for r in v1.read_tsv(os.path.join(v1.THIRD, "descriptions.tsv"))}
    with open(os.path.join(v1.OUT, "jobs.json"), encoding=v1.ENC) as f:
        seeds = {j["asset_id"]: j["seed"] for j in json.load(f)}
    fails = [v["asset_id"] for v in ver if v["verdict"] == "FAIL"]
    if not fails or set(fails) != set(desc):
        raise SystemExit("third/descriptions.tsv не совпадает с FAIL STRICT - третий проход не начинаю")
    return [{"group": "third", "asset_id": a, "what": desc[a]["what_en"], "seed": seeds[a], "restore": "",
             "defect": desc[a]["source_ru"]} for a in fails if desc[a]["route"] == "STRICT" and desc[a]["what_en"]]


v1.strict_frames, v1.third_frames = strict_frames, third_frames


def strict_chunk():
    """Процесс модели второго прохода: не больше THIRD_CHUNK ещё не нарисованных кадров (R-215)."""
    import strict_ctl_v1 as sc
    sc.OUT = os.path.join(v1.OUT, "strict").replace("\\", "/")
    todo = [f for f in strict_frames() if not os.path.exists(os.path.join(v1.ROOT, sc.piece("strict", f["asset_id"])))]
    sc.frames = lambda: todo[:v1.THIRD_CHUNK]
    sc.do_render()


def do_strict():
    """Без модели: процессы strict-chunk, пока всё не готово; три падения подряд без нового кадра - стоп.
    В V1 STRICT рисовал одним процессом и упал по OOM на 26-м кадре (R-215) - здесь как do_third V1."""
    import subprocess
    import time
    import strict_ctl_v1 as sc
    out = os.path.join(v1.OUT, "strict").replace("\\", "/")
    sc.OUT = out
    fr = strict_frames()
    left = lambda: [f for f in fr if not os.path.exists(os.path.join(v1.ROOT, sc.piece("strict", f["asset_id"])))]
    t0, crashes, procs = time.time(), 0, []
    while left() and crashes < 3:
        before, ts = len(left()), time.time()
        code = subprocess.call([sys.executable, os.path.abspath(__file__), "strict-chunk"])
        made = before - len(left())
        procs.append({"exit_code": code, "made": made, "minutes": round((time.time() - ts) / 60, 1)})
        print("процесс: код %d, нарисовано %d, осталось %d" % (code, made, len(left())), flush=True)
        crashes = 0 if made else crashes + 1
    sc.wr_json(out + "/spec.json", {
        "what": "PROD_TWO_PASS_V2 второй проход: STRICT 27.09 на FAIL судей RESTORE (judge/restore/verdicts_auto.tsv)",
        "path": "strict_ctl_v1.do_render: STYLE strict, Qwen-Image-2.1 %d шагов, cfg %g, %g Мп; по %d рендера на процесс"
                % (sc.STEPS, sc.CFG, sc.MP, v1.THIRD_CHUNK),
        "what_seed": "из партии RESTORE (report.json, jobs.json)", "frames": [f["asset_id"] for f in fr],
        "done": len(fr) - len(left()), "processes": procs, "minutes": round((time.time() - t0) / 60, 1)})
    if left():
        raise SystemExit("не нарисовано: %s" % ", ".join(f["asset_id"] for f in left()))


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ("strict", "strict-chunk"):
        sys.stdout.reconfigure(encoding="utf-8")
        os.chdir(v1.ROOT)
        (do_strict if sys.argv[1] == "strict" else strict_chunk)()
    elif len(sys.argv) > 1 and sys.argv[1] in ("select", "build"):
        sys.stdout.reconfigure(encoding="utf-8")
        os.chdir(v1.ROOT)
        (do_select if sys.argv[1] == "select" else do_build)()
    else:
        v1.main()


if __name__ == "__main__":
    main()
