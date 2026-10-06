r"""Проба материала тротуара ROADS для sidewalk_job1: один ответ Qwen-Image-2.1 - вид сверху на покрытие.

ГРУЗИТ МОДЕЛЬ НА ВИДЕОКАРТУ: запуск только через очередь и только по слову Vitali.

    py -3 tools\gpuq.py add --name sidewalk-probe -- E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/sidewalk_render.py

Вход - ровный средний цвет классики ROADS:0 со слабым непериодическим шумом, без пятен оригинала (R-118): форму
и узор модели не подсказываем, только тон. Материал словами - «ровное крапчатое серое покрытие тротуара»
(уточнение Vitali 07.10); плитки, кирпичи, швы и борозды названы только в негативе (R-016). Ракурс и свет -
battle_view.prompt_block("floor_unrolled"). Модель - Qwen-Image-2.1 по замку art/models/qwen21_turbo_rgba.lock.json
без LoRA, 40 шагов, cfg 4 (негатив действует только при cfg больше 1, R-040).

Кладёт в census/maps/pilot2/probe_sidewalk/: sketch.png, raw_s<сид>.png, prompt_s<сид>.json. Кадры из ответа
собирает sidewalk_probe.py build --raw ... (без модели), лист - sidewalk_probe.py sheet.
Готовый ответ не перерисовывается: повтор задания после падения ничего не делает.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import battle_view          # noqa: E402
import model_lock           # noqa: E402
import sidewalk_probe as sp  # noqa: E402

ENC = "utf-8-sig"
OUT = sp.OUT

PROMPT = ("Flat speckled grey sidewalk pavement surface: a smooth even poured walkway with fine, evenly scattered, "
          "non-directional grit and tiny pale and dark specks, the same small grain size everywhere, a few very faint "
          "worn spots. Keep the overall grey colour and brightness of image1 exactly. {view}. "
          "Photorealistic material detail, sharp fine grain, uniform over the whole square.")
NEG_MATERIAL = ("paving slabs, tiles, flagstones, bricks, cobblestones, pavers, herringbone, grid, joints, seams, "
                "cracks, grooves, furrows, ploughed soil, stripes, lines, directional strokes, brush strokes, ripples, "
                "bumps, domes, raised cells, pebbles, gravel stones, puddles, leaves, litter, road markings, text, "
                "pixel art, pixelated, blocky, dithering, blurry, smudged, noise pattern repetition")


def sketch(seed, mean_rgb):
    """1024 x 1024: средний цвет классики плюс слабый мелкий шум (разброс 3 единицы) - без узора оригинала."""
    rng = np.random.default_rng(seed)
    n = sp.blur_wrap(rng.normal(0, 1, (sp.SIDE, sp.SIDE)), 1.0)
    n *= 3.0 / n.std()
    img = mean_rgb[None, None, :] + n[..., None]
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=7101)
    ap.add_argument("--steps", type=int, default=40)
    ap.add_argument("--cfg", type=float, default=4.0)
    ap.add_argument("--mp", type=float, default=1.0)
    ap.add_argument("--offload", default="model", choices=["model", "seq", "none"])
    ap.add_argument("--lock", default=model_lock.LOCK)
    ap.add_argument("--dry-run", action="store_true", help="вход, промпт и сверка замка - без модели")
    a = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    raw = OUT / ("raw_s%d.png" % a.seed)
    if raw.exists():
        print("ответ уже есть: %s - не рисую" % raw)
        return
    mean_rgb, _ = sp.classic_mean()
    sk = sketch(a.seed, mean_rgb)
    sk.save(OUT / "sketch.png")
    vb = battle_view.prompt_block("floor_unrolled")
    prompt = PROMPT.format(view=vb["positive"][0].upper() + vb["positive"][1:])
    negative = vb["negative"] + ", " + NEG_MATERIAL

    lock = model_lock.load(a.lock)
    if lock is None:
        raise SystemExit("нет замка модели %s" % a.lock)
    pinned = model_lock.pin(lock)
    bad = model_lock.check_runtime(lock)
    for b in bad:
        print("   замок:", b, flush=True)
    if bad:
        raise SystemExit("расхождений с замком %d - не рисую" % len(bad))
    print("замок модели: %s@%s - совпадает (без LoRA)" % (pinned["model_repo"], pinned["model_revision"][:8]), flush=True)
    meta = dict(seed=a.seed, steps=a.steps, cfg=a.cfg, mp=a.mp, model=pinned["model_repo"],
                revision=pinned["model_revision"], prompt=prompt, negative=negative,
                sketch="средний цвет классики ROADS:0 %s + шум 3" % [round(float(x), 1) for x in mean_rgb])
    print("промпт:", prompt, "\nнегатив:", negative, flush=True)
    if a.dry_run:
        return

    import gen_fire
    import gen_hd
    ns = argparse.Namespace(models=gen_hd.DEFAULT_MODELS_DIR, qwen21_model="", qwen21_steps=a.steps,
                            qwen21_cfg=a.cfg, qwen21_mp=a.mp, qwen21_strength=0.0, qwen21_offload=a.offload,
                            qwen21_thrifty=False, qwen21_ref="", qwen21_ref_mp=1.0, qwen21_prompt="strict",
                            qwen21_hint="off", qwen21_ref_order="ref-first",
                            qwen21_revision=pinned["model_revision"],
                            qwen21_local_only=bool(pinned["local_files_only"]))
    painter = gen_hd.Qwen21Painter(ns, {"ground": ("", "")})
    gen_fire.NEGATIVE = negative                     # run_pass берёт негатив из модуля gen_fire
    hd = gen_fire.run_pass(painter, a, prompt, sk, a.seed)
    gen_hd.save_png(hd.convert("RGB"), str(raw))
    (OUT / ("prompt_s%d.json" % a.seed)).write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding=ENC)
    print("ответ: %s %s" % (raw, hd.size), flush=True)
    print("дальше без модели: py -3.13 tools/hdart/sidewalk_probe.py build --raw %s && "
          "py -3.13 tools/hdart/sidewalk_probe.py sheet --tag s%d" % (raw.relative_to(sp.ROOT).as_posix(), a.seed))


if __name__ == "__main__":
    main()
