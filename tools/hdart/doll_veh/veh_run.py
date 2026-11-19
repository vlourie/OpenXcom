"""Техника: запуск FLUX.3 Klein по промптам veh_flux.WHAT. Аргументы: имена через запятую (all), сиды.
Выход E:/tmp/doll_ingame/veh/images/<имя>_<сид>.png. Запуск через gpuq окружением diffusers."""
import json
import os
import sys
from PIL import Image
from veh_flux import OUT, REPAINT, WHAT

names = list(WHAT) if sys.argv[1] == "all" else sys.argv[1].split(",")
seeds = [int(s) for s in sys.argv[2].split(",")] if len(sys.argv) > 2 else [1, 2]
jobs = {}
for name in names:
    src = os.path.join(OUT, "init_%s.png" % name)
    w, h = Image.open(src).size
    for seed in seeds:
        item = "%s_%d" % (name, seed)
        if not os.path.exists(os.path.join(OUT, "images", item + ".png")):
            jobs[item] = {"task": "veh", "prompt": REPAINT + WHAT[name], "caption": item, "seed": seed, "width": w,
                          "height": h, "image": [src]}
spec = {"id": "veh", "model": "flux3", "preset": "bf16", "mode": "both", "variant": "bf16",
        "captions": os.path.join(OUT, "captions.json"), "jobs": jobs, "offload_mode": "auto"}
with open(os.path.join(OUT, "spec.json"), "w", encoding="utf-8") as f:
    json.dump(spec, f, ensure_ascii=False, indent=1)
print("заданий", len(jobs), flush=True)
if jobs:
    os.environ["MB_SPEC"] = os.path.join(OUT, "spec.json")
    os.environ["MB_OUT"] = OUT
    sys.path.insert(0, r"F:\AIStudio\models\benchmarks\2026-11-06\tools\workers")
    import flux3_worker
    flux3_worker.main()
print("готово", len(jobs), flush=True)
