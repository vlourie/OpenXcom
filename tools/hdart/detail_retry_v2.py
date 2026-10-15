#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""DETAIL_RETRY_V2 - перерисовка брака финального листа V2 (специалист 05.10, передал Vitali в чате).

Из 75 кадров финального листа (final_select.py) Vitali снял 14. Общего четвёртого прохода нет: каждый кадр
рисуется заново тем же путём, что THIRD (strict_ctl_v1.do_render, STRICT 27.09, зерно партии), но описание
предмета прямо перечисляет деталь, которую Vitali назвал утраченной («Must show: ...»). Группы специалиста:
DETAIL (MISSING_DETAIL), IDENTITY, STRUCTURE, MATERIAL - в retry/descriptions.tsv столбец group; текст - по
заметке Vitali без своих добавлений (source_ru). Кадр без заметки не рисуется, пока Vitali её не даст.

    check   без модели: описания против брака листа (final_select/verdicts_vitali.tsv), спецификация в UTF-8 со BOM
    render  модель - только через очередь, процессы по prod_two_pass_v1.THIRD_CHUNK (R-215):
        py -3.13 tools/gpuq.py add --name detail_retry_v2 --cwd E:/OpenXCom -- \
            E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/detail_retry_v2.py render
    sheet   без модели: лист оригинал x4 | кадр финального листа | перерисовка -> retry/sheet.png

Кадры: retry/strict/series/<набор>.PCK/<номер>.png.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import prod_two_pass_v2  # noqa: E402,F401  (настраивает prod_two_pass_v1 на папку V2)
import prod_two_pass_v1 as v1  # noqa: E402

RETRY = os.path.join(v1.OUT, "retry")
FINAL = os.path.join(v1.OUT, "final_select")
v1.THIRD = RETRY
v1.__file__ = os.path.abspath(__file__)          # do_third зовёт third-chunk этого файла
HEAD = ["asset_id", "group", "route", "what_en", "must", "source_ru"]


def failed():
    return [r["asset_id"] for r in v1.read_tsv(os.path.join(FINAL, "verdicts_vitali.tsv")) if r["verdict"] == "FAIL"]


def retry_frames():
    desc = {r["asset_id"]: r for r in v1.read_tsv(os.path.join(RETRY, "descriptions.tsv"))}
    bad = failed()
    extra = set(desc) - set(bad)
    if extra:
        raise SystemExit("в retry/descriptions.tsv кадры не из брака листа: %s" % ", ".join(sorted(extra)))
    with open(os.path.join(v1.OUT, "jobs.json"), encoding=v1.ENC) as f:
        seeds = {j["asset_id"]: j["seed"] for j in json.load(f)}
    out = []
    for a in bad:
        r = desc.get(a)
        if not r or r["route"] != "STRICT" or not r["what_en"] or "Must show:" not in r["what_en"]:
            continue
        out.append({"group": "retry", "asset_id": a, "what": r["what_en"], "seed": seeds[a], "restore": "",
                    "defect": "%s: %s" % (r["group"], r["source_ru"])})
    return out


v1.third_frames = retry_frames


def do_check():
    p = os.path.join(RETRY, "descriptions.tsv")
    rows = v1.read_tsv(p)
    if not rows or any(set(r) != set(HEAD) for r in rows):
        raise SystemExit("retry/descriptions.tsv: столбцы не %s" % HEAD)
    fr = {f["asset_id"] for f in retry_frames()}
    bad = failed()
    for a in bad:
        print("%-20s %s" % (a, "рисуется" if a in fr else "ЖДЁТ описания"))
    print("брака на листе %d, к перерисовке %d" % (len(bad), len(fr)))
    with open(p + ".tmp", "w", encoding=v1.ENC, newline="") as f:     # кириллица - со BOM (R-001)
        f.write("\t".join(HEAD) + "\n")
        for r in rows:
            f.write("\t".join(r[k] for k in HEAD) + "\n")
    if len(v1.read_tsv(p + ".tmp")) != len(rows):
        raise SystemExit("перезапись описаний потеряла строки (R-159)")
    os.replace(p + ".tmp", p)


def do_sheet():
    import numpy as np
    from PIL import Image, ImageDraw
    import strict_ctl_v1 as sc
    import visual_judge as vj
    sc.OUT = os.path.join(RETRY, "strict").replace("\\", "/")
    sel = {r["asset_id"]: r for r in v1.read_tsv(os.path.join(FINAL, "select.tsv"))}
    fr = [f for f in retry_frames() if os.path.exists(os.path.join(v1.ROOT, sc.piece("strict", f["asset_id"])))]
    W, H, T = 256, 320, 18
    sheet = Image.new("RGB", (3 * W, len(fr) * (H + T)), (38, 38, 42))
    d = ImageDraw.Draw(sheet)
    for i, f in enumerate(fr):
        a, y = f["asset_id"], i * (H + T)
        o = Image.fromarray(np.repeat(np.repeat(vj.sprite(a), 8, 0), 8, 1))
        for j, (img, lab) in enumerate(((o, "оригинал"), (Image.open(sel[a]["piece"]), "лист: " + sel[a]["stage"]),
                                       (Image.open(os.path.join(v1.ROOT, sc.piece("strict", a))), "перерисовка"))):
            img = img.convert("RGBA")
            img.thumbnail((W, H))
            sheet.paste(img, (j * W + (W - img.width) // 2, y + T + (H - img.height) // 2), img)
            d.text((j * W + 4, y + 3), "%s  %s" % (a, lab), fill=(230, 230, 230))
    p = os.path.join(RETRY, "sheet.png")
    sheet.save(p)
    print("лист %s: %d кадров" % (p, len(fr)))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    os.chdir(v1.ROOT)
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "check":
        do_check()
    elif cmd == "render":
        v1.do_third()
        sp = os.path.join(RETRY, "strict", "spec.json")
        with open(sp, encoding=v1.ENC) as f:
            spec = json.load(f)
        spec["what"] = ("DETAIL_RETRY_V2: STRICT 27.09 на брак финального листа V2 (final_select/verdicts_vitali.tsv), "
                        "описание с обязательной деталью по заметке Vitali (специалист 05.10)")
        spec["what_seed"] = "описание - retry/descriptions.tsv, зерно - jobs.json партии"
        with open(sp, "w", encoding=v1.ENC) as f:
            json.dump(spec, f, ensure_ascii=False, indent=1)
    elif cmd == "third-chunk":
        v1.third_chunk()
    elif cmd == "sheet":
        do_sheet()
    else:
        raise SystemExit("команда: check | render | sheet")


if __name__ == "__main__":
    main()
