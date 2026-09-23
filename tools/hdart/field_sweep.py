# -*- coding: utf-8 -*-
r"""Перебор настроек поля на ОДНОМ полу: что художник вообще понимает.

    tools\hdart\.venv\Scripts\python.exe tools\hdart\field_sweep.py --sheets hdart_sheets_pz_field --set CULTIVAT.PCK --frame 0 --mod-b "Пиратки\Dioxine_XPiratez\user\mods\hd"

Рисует один и тот же пол несколькими способами подряд (модель грузится один раз) и складывает
результаты на один лист: оригинал, старый пак (если дан --mod-b) и каждая настройка - полем 3x3,
как его кладёт движок. Настройки:

    cell x16      как рисовалось раньше: одна клетка, масштаб 16 (тайл 512x640)
    3x3 x16       поле 3x3, тот же масштаб на клетку - контекст есть, размер детали прежний
    3x3 tight     то же, но управляющая картинка резче и сила ниже: держится оригинала
    5x5 x10       то, что прогонялось ночью (клетка рисуется 320x400)
    5x5 x16       поле 5x5 в полном масштабе, ~5 Мпикс - только с --heavy

Свои наборы: --configs "3x3 x16,3x3 tight". Минут пять на прогон, зато дальше не гадать.
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from PIL import Image, ImageDraw     # noqa: E402
import xcom_sprites as xs            # noqa: E402
import build_pack                    # noqa: E402
import gen_hd                        # noqa: E402
import subjects_terrain              # noqa: E402

# Перебор стиля (--styles): размер поля почти не влияет, а слова влияют сильно. Пробуем разные
# способы объяснить модели, что это кусок земли, а не рендер предмета.
STYLES = [
    ("photo", "{subject}, seen straight from above, flat even daylight, matte surface, fine grain, "
              "muted natural colors"),
    ("satellite", "aerial survey photo of {subject}, straight down, overcast flat light, no shadows, "
                  "fine grain"),
    ("painted", "hand-painted terrain art of {subject}, top-down, gouache and dry brush, visible "
                "brush texture, matte, flat light"),
    ("xeno", "hand-painted strategy game terrain, {subject}, top-down, matte poster paint, muted "
             "earthy palette, no gloss"),
    ("macro", "close-up ground photo of {subject}, camera straight down, diffuse light, sharp fine "
              "detail, no highlights"),
]

# Перебор режимов Qwen (--qwen): он держит композицию, вопрос только в том, сколько шагов и какой
# CFG нужны, чтобы он действительно перерисовал материал, а не сгладил исходные пиксели.
# При cfg 1.0 негатив не работает вовсе (нечего взвешивать), поэтому и пробуем с ним и без.
QWEN_TRIALS = [
    ("qwen 8 fast", 8, 1.0),
    ("qwen 20 cfg3", 20, 3.0),
    ("qwen 40 cfg4", 40, 4.0),
]

# Перебор силы у SDXL (--strengths): 0.8 - «нарисуй заново» (отсюда раздутые предметы),
# 0.3 - «оставь как есть, добавь фактуру». Ни разу не пробовали, а стоит копейки.
STRENGTH_TRIALS = [0.25, 0.35, 0.45, 0.6]

CONFIGS = [
    ("cell x16", {"ground_field": 0}),
    ("3x3 x16", {"ground_field": 3, "field_scale": 16}),
    ("3x3 tight", {"ground_field": 3, "field_scale": 16, "field_blur": 1.0, "tile": 0.85, "strength": 0.65}),
    ("5x5 x10", {"ground_field": 5, "field_scale": 10}),
    ("5x5 x16", {"ground_field": 5, "field_scale": 16, "heavy": True}),
]


def pack_like(cell, job, info, frame, scale=4):
    """Клетка после сшивки -> кадр, как его положил бы build_pack (цвет подтянут, альфа оригинала)."""
    fw, fh, m = info["frame_w"], info["frame_h"], job.margin
    small = cell.convert("RGB").resize(((fw + 2 * m) * scale, (fh + 2 * m) * scale), Image.LANCZOS)
    small = small.crop((m * scale, m * scale, (m + fw) * scale, (m + fh) * scale)).convert("RGBA")
    orig = job.sheet.cut(job.original, frame, 1).resize((fw * scale, fh * scale), Image.NEAREST)
    alpha = orig.split()[3]
    mask = alpha.point(lambda v: 255 if v > 128 else 0)
    out = build_pack.color_match(small, orig, mask, 0.8)
    out = build_pack.chroma_lock(out, orig, mask, 1.0)
    out.putalpha(alpha)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="перебор настроек поля на одном полу")
    ap.add_argument("--sheets", required=True)
    ap.add_argument("--set", required=True, dest="set_name")
    ap.add_argument("--frame", type=int, default=-1, help="номер пола; -1 - самый большой ровный пол")
    ap.add_argument("--mod-b", default="", dest="mod_b", help="мод со старым паком, для колонки «было»")
    ap.add_argument("--pack-path", default="TERRAIN", dest="pack_path")
    ap.add_argument("--out", default="art/_experiments/field_sweep")
    ap.add_argument("--cells", type=int, default=3, help="поле из скольких клеток показывать")
    ap.add_argument("--configs", default="", help="через запятую, имена из списка в описании")
    ap.add_argument("--heavy", action="store_true", help="включить и тяжёлые настройки (5x5 x16)")
    ap.add_argument("--strengths", default=None,
                    help="перебрать силу SDXL при поле 3x3: список через запятую или пусто = 0.25,0.35,0.45,0.6")
    ap.add_argument("--qwen", action="store_true",
                    help="перебирать режимы Qwen-Image-Edit (шаги и CFG) при поле 3x3")
    ap.add_argument("--styles", action="store_true",
                    help="перебирать не размеры поля, а слова стиля (список STYLES) при 3x3 x16")
    ap.add_argument("--steps", type=int, default=0, help="шагов модели (0 - как у gen_hd)")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)

    set_name = args.set_name if args.set_name.upper().endswith(".PCK") else args.set_name + ".PCK"
    set_dir = os.path.join(args.sheets, set_name)
    with open(os.path.join(set_dir, "layout.json"), encoding="utf-8-sig") as f:
        info = json.load(f)
    info.setdefault("set", set_name)
    fw, fh = info["frame_w"], info["frame_h"]

    base = gen_hd.build_parser().parse_args(["--sheets", args.sheets, "--set", set_name])
    if args.steps:
        base.steps = args.steps
    if args.seed:
        base.seed = args.seed
    job = gen_hd.Job(base, set_dir, info)

    frame = args.frame
    if frame < 0:
        floors = [(job.sheet.cut(job.original, i, 1).split()[3].getbbox(), i) for i in job.cells
                  if job.ground[i] and not job.tall.get(i) and job.types[i] == xs.MCD_FLOOR]
        floors = [(b, i) for b, i in floors if b]
        if not floors:
            raise SystemExit("в наборе нет ровных полов")
        frame = max(floors, key=lambda t: (t[0][2] - t[0][0]) * (t[0][3] - t[0][1]))[1]
    print("пол %d, набор %s%s" % (frame, set_name, (", подсказка: " + job.hints[frame]) if frame in job.hints else ""))

    names = [c.strip() for c in args.configs.split(",") if c.strip()]
    if args.strengths is not None:
        vals = [float(v) for v in args.strengths.split(",") if v.strip()] or STRENGTH_TRIALS
        configs = [("сила %.2f" % v, {"ground_field": 3, "field_scale": 16,
                                      "strength": v, "flat_strength": v}) for v in vals]
    elif args.qwen:
        configs = [(n, {"ground_field": 3, "field_scale": 16, "painter": "qwen",
                        "qwen_steps": st, "qwen_cfg": cfg})
                   for n, st, cfg in QWEN_TRIALS if not names or n in names]
    elif args.styles:
        configs = [(n, {"ground_field": 3, "field_scale": 16, "style": st})
                   for n, st in STYLES if not names or n in names]
    else:
        configs = [(n, o) for n, o in CONFIGS if (not names or n in names) and (args.heavy or not o.get("heavy"))]
    if not configs:
        raise SystemExit("нечего перебирать: проверь --configs")

    subject, src = (gen_hd.SUBJECTS.get(set_name), "SUBJECTS")
    if not subject:
        subject, s2 = subjects_terrain.subject_for_set(set_name)
        src = "террейн %s" % s2
    if not subject:
        subject, s2 = subjects_terrain.subject_by_name(set_name)
        src = "имя %s" % s2
    subject = subject or "terrain tiles and objects"
    context = {"ground": (subject.split(":")[0], subject), "object": (subject.split(":")[0], subject)}
    prompts = {"object": gen_hd.STYLE, "ground": gen_hd.STYLE_GROUND}
    print("тема (%s): %s" % (src, subject))

    os.makedirs(args.out, exist_ok=True)
    os.makedirs(os.path.join(set_dir, "crops"), exist_ok=True)
    painter = None
    if any(o.get("painter") != "qwen" for _, o in configs):
        painter = gen_hd.Painter(gen_hd.load_pipeline(base.base), prompts, gen_hd.NEGATIVE, context)

    panels = []
    orig_cell = job.sheet.cut(job.original, frame, 1).resize((fw * 4, fh * 4), Image.NEAREST)
    panels.append((build_pack.ground_field([orig_cell], args.cells, 4).convert("RGB"), "original"))
    if args.mod_b:
        p = os.path.join(args.mod_b, "hd", args.pack_path, set_name, "%d.png" % frame) if args.pack_path \
            else os.path.join(args.mod_b, "hd", set_name, "%d.png" % frame)
        if os.path.exists(p):
            panels.append((build_pack.ground_field([Image.open(p).convert("RGBA")], args.cells, 4).convert("RGB"),
                           "old pack"))
        else:
            print("старого пака нет: %s" % p)

    t0 = time.time()
    for name, over in configs:
        a = argparse.Namespace(**vars(base))
        for k, v in over.items():
            if k not in ("heavy", "style"):
                setattr(a, k, v)
        keep_style = gen_hd.STYLE_FIELD
        if over.get("style"):
            gen_hd.STYLE_FIELD = over["style"]
        t = time.time()
        use = painter
        if over.get("painter") == "qwen":
            use = gen_hd.QwenPainter(a, context)
        if a.ground_field >= 3:
            cells, gs, places = gen_hd.paint_ground_field(a, job, use, set_dir, info, frame, a.steps,
                                                          a.seed, 1)
            cell = cells[0]
        else:
            j = gen_hd.Job(a, set_dir, info)
            cell = use.paint(j, [frame], a.strength, a.steps, a.seed)[frame][0]
        if over.get("painter") == "qwen":
            del use                      # освобождаем 20 ГБ перед следующим режимом
            try:
                import torch
                torch.cuda.empty_cache()
            except Exception:
                pass
        if a.seamless:
            cell = gen_hd.seamless_ground(cell, job.g, job.margin, fw, fh)
        packed = pack_like(cell, job, info, frame)
        packed.save(os.path.join(args.out, "cell_%s.png" % name.replace(" ", "_")))
        gen_hd.STYLE_FIELD = keep_style
        panels.append((build_pack.ground_field([packed], args.cells, 4).convert("RGB"),
                       "%s  %.0fs" % (name, time.time() - t)))
        print("  %-12s готово за %s" % (name, gen_hd.human_time(time.time() - t)), flush=True)

    top = 18
    w = sum(p[0].width for p in panels) + 8 * (len(panels) - 1)
    h = max(p[0].height for p in panels)
    sheet = Image.new("RGB", (w, h + top), (28, 28, 30))
    d = ImageDraw.Draw(sheet)
    x = 0
    for im, text in panels:
        sheet.paste(im, (x, top))
        d.text((x + 4, 4), text, fill=(255, 232, 120))
        x += im.width + 8
    out = os.path.join(args.out, "%s_%d.png" % (set_name[:-4], frame))
    sheet.save(out)
    print("лист: %s (всего %s)" % (out, gen_hd.human_time(time.time() - t0)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
