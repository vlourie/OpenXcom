#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Одна проба Qwen-Image-2.1 на HANDOB Томпсона 1642 - те же входы, что у пробы Codex (handob_tommy.py).

Разрешение Vitali 07.10: одна проба через очередь видеокарты, только кадр 1642; входы - два чистых изображения
tommy1642/inputs и target_zones_rev2.json, цели размера, дула и хвата не меняются. Остальные кадры не рисуются.

Отличия от пробы Codex - только то, без чего Qwen не работает:
  - картинки в промпте названы тегами <image1>, <image2> (иначе вторая картинка без имени, R-045 struct_probe);
  - список Avoid из промпта отдан ещё и негативом (cfg 4 - негатив действует, R-040);
  - оба входа уменьшены одним масштабом 1024x1536 -> 832x1248 (1.04 Мп, рецепт RENDER_V1 - 1 Мп; две картинки
    по 1.57 Мп - это токенов больше, чем у трёх картинок по 1 Мп, R-205). Кадр 32x40 x32 становится x26 ровно,
    поэтому HANDOB уменьшен NEAREST (блоки остаются блоками), картина конструкции - LANCZOS.
Модель, шаги, cfg, разгрузка - по замку и RENDER_V1 (struct_probe.Render), одно зерно, одна попытка.
Ответ модели сохраняется как есть (raw/*.png, 832x1248) и копией, увеличенной одним масштабом до 1024x1536
(*_x1024.png) - её читает handob_tommy.check (холст 1024x1536 = база x32 с полями 128). Без растяжки,
без подгонки по силуэту, зоны не двигаются.

Только через очередь (gpu_scripts.txt):
    py -3.13 tools/gpuq.py add --name tommy1642_q21 --prio 1 --cwd E:/OpenXCom -- \
        E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/handob_tommy_q21.py
Без модели: --dry-run (входы 832x1248 и промпт в tommy1642/q21/inputs).
"""
import argparse
import datetime
import hashlib
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)

from PIL import Image                   # noqa: E402

ENC = "utf-8-sig"
PILOT = "art/items/weapons100-v1/grip_pilot"
SRC = os.path.join(PILOT, "tommy1642")
OUT = os.path.join(SRC, "q21")
REV2 = os.path.join(PILOT, "target_zones_rev2.json")
KEY = "STR_TOMMYGUN.1642"
W, H = 832, 1248                        # 1024x1536 x 13/16: база x26, поля 104
SEED = 7400


def sha(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def prepare():
    """Входы Codex -> входы Qwen; сверка хэшей с plan.json пробы Codex."""
    with open(os.path.join(SRC, "plan.json"), encoding=ENC) as f:
        plan = json.load(f)
    files = {"in1": os.path.join(SRC, "inputs", "in1_handob.png"),
             "in2": os.path.join(SRC, "inputs", "in2_construction.png"),
             "prompt": os.path.join(SRC, "inputs", "prompt.txt")}
    bad = [n for n, p in files.items() if sha(p) != plan["inputs_sha256"].get(n)]
    if bad:
        raise SystemExit("входы пробы Codex изменены: %s" % bad)
    if sha(REV2) != plan.get("zones_rev2_sha256"):
        raise SystemExit("редакция 2 зон изменена")
    with open(files["prompt"], encoding=ENC) as f:
        text = f.read().strip()
    for a, b in (("Image 1", "<image1>"), ("image 1", "<image1>"), ("Image 2", "<image2>"), ("image 2", "<image2>"),
                 ("1024x1536", "%dx%d" % (W, H))):
        text = text.replace(a, b)
    avoid = [s for s in text.splitlines() if s.startswith("Avoid:")]
    if len(avoid) != 1:
        raise SystemExit("в промпте нет одной строки Avoid")
    negative = avoid[0][len("Avoid:"):].strip().rstrip(".")
    in1 = Image.open(files["in1"]).convert("RGB")
    in2 = Image.open(files["in2"]).convert("RGB")
    if in1.size != (1024, 1536) or in2.size != (1024, 1536):
        raise SystemExit("входы не 1024x1536: %s %s" % (in1.size, in2.size))
    q1 = in1.resize((W, H), Image.NEAREST)
    q2 = in2.resize((W, H), Image.LANCZOS)
    d = os.path.join(OUT, "inputs")
    os.makedirs(d, exist_ok=True)
    q1.save(os.path.join(d, "in1_handob_832.png"))
    q2.save(os.path.join(d, "in2_construction_832.png"))
    with open(os.path.join(d, "prompt.txt"), "w", encoding=ENC) as f:
        f.write(text + "\n")
    with open(os.path.join(d, "negative.txt"), "w", encoding=ENC) as f:
        f.write(negative + "\n")
    return plan, files, text, negative, [q1, q2]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", dest="dry_run")
    a = ap.parse_args()
    os.chdir(ROOT)
    plan, files, text, negative, ims = prepare()
    print("промпт %d знаков, негатив %d знаков, входы %dx%d" % (len(text), len(negative), W, H), flush=True)
    if a.dry_run:
        print("dry-run: входы и промпт в", os.path.join(OUT, "inputs"))
        return
    raw_dir = os.path.join(OUT, "raw")
    raw = os.path.join(raw_dir, "%s.q21.s%d.png" % (KEY, SEED))
    if os.path.exists(raw):
        raise SystemExit("ответ уже есть - проба одна: %s" % raw)
    os.makedirs(raw_dir, exist_ok=True)
    import struct_probe as sp
    import gen_fire
    import gen_hd
    R = sp.Render(OUT)
    R.check_lock()
    gen_fire.NEGATIVE = negative
    R.run.mp = 0                        # размер входа уже 832x1248, кратен 32
    t0 = time.time()
    painter = gen_hd.Qwen21Painter(R.ns, {"ground": ("", "")})
    t1 = time.time()
    print("модель загружена за %.0f с, рисую: %d шагов, cfg %.1f, зерно %d" % (t1 - t0, R.run.steps, R.run.cfg, SEED),
          flush=True)
    hd = sp.run_multi(painter, R.run, text, ims, SEED)
    gen_hd.save_png(hd, raw)
    if not os.path.exists(raw):
        raise SystemExit("ответ не лёг на диск: %s" % raw)
    t2 = time.time()
    im = Image.open(raw)
    print("ответ %s, %dx%d %s, %.0f с" % (raw, im.width, im.height, im.mode, t2 - t1), flush=True)
    big = im.convert("RGB").resize((1024, 1536), Image.LANCZOS)   # один масштаб 16/13 по обеим осям
    big_path = raw[:-4] + "_x1024.png"
    big.save(big_path)
    run = {"at": datetime.datetime.now().isoformat(timespec="seconds"),
           "approved": "Vitali 07.10: одна проба Qwen-Image-2.1 через очередь, только HANDOB 1642",
           "engine": "qwen21", "generator_rev": R.grev, "model_lock": R.lock_rev, "seed": SEED,
           "steps": R.run.steps, "cfg": R.run.cfg, "size": [W, H], "inputs_sha256": plan["inputs_sha256"],
           "zones_rev2_sha256": plan["zones_rev2_sha256"], "prompt_sha256": sha(os.path.join(OUT, "inputs", "prompt.txt")),
           "script_sha256": sha(os.path.abspath(__file__)), "raw": raw.replace("\\", "/"),
           "raw_sha256": sha(raw), "raw_x1024": big_path.replace("\\", "/"),
           "load_s": round(t1 - t0), "render_s": round(t2 - t1), "gpuq_job": os.environ.get("GPUQ_JOB_ID", "")}
    with open(os.path.join(OUT, "run.json"), "w", encoding=ENC) as f:
        json.dump(run, f, ensure_ascii=False, indent=1)
    print("готово:", os.path.join(OUT, "run.json"), flush=True)


if __name__ == "__main__":
    main()
