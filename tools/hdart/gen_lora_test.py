#!/usr/bin/env python3
"""gen_lora_test.py - что LoRA изменила: одни и те же клетки до и после.

Рисует таблицу: вход | без LoRA | с LoRA | эталон. Один прогон, одна загрузка модели,
одно зерно - разница между вторым и третьим столбцом и есть весь эффект обучения.

ВАЖНО про то, какие кадры брать. Кадры из датасета модель видела, и на них будет красиво
просто по памяти. Настоящий ответ дают кадры, которых в обучении НЕ было: ключ --set берёт
их прямо из листа набора, мимо датасета.

    E:\\train\\.venv-train\\Scripts\\python.exe tools\\hdart\\gen_lora_test.py ^
        --lora E:\\train\\lora\\oxcehd\\step-2540.safetensors --frames 0,1,4,96
    ... --set CULTIVAT.PCK --frames 0,1,2,3          (набор, которого в обучении не было)
"""

import argparse
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import torch                                          # noqa: E402
from PIL import Image, ImageDraw, ImageFont           # noqa: E402

PANEL = (90, 90, 96)
ZOOM = 24
CAPTION = "{trigger}X-COM isometric {kind} tile, {hint}"


def font(size=15):
    for p in (r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\arial.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


def from_dataset(data, frames):
    """Пары из собранного датасета: control, эталон и та самая подпись, на которой учили."""
    rows = []
    with open(os.path.join(data, "metadata.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            name = os.path.splitext(os.path.basename(r["image"]))[0]
            num = int(name.rsplit("_", 1)[-1])
            if frames and num not in frames:
                continue
            rows.append({
                "name": name,
                "control": os.path.join(data, r["edit_image"].replace("/", os.sep)),
                "ref": os.path.join(data, r["image"].replace("/", os.sep)),
                "prompt": r["prompt"],
                "seen": True,
            })
    return rows


def from_sheet(sheets, set_name, frames, trigger):
    """Кадры прямо из листа набора - эталона нет, зато модель их не видела."""
    import tile_forge as tf
    import build_dataset as bd

    sh = tf.Sheet(sheets, set_name)
    hints = {}
    hp = os.path.join(sheets, set_name, "hints.json")
    if os.path.exists(hp):
        with open(hp, encoding="utf-8-sig") as f:
            hints = {int(k): v for k, v in json.load(f).items()}
    rows = []
    for i in (frames or list(sh.frames())[:6]):
        if i >= sh.lay["count"]:
            print("  кадр %d: в наборе такого нет" % i, file=sys.stderr)
            continue
        if tf.alpha_box(sh.frame(i)) is None:
            continue
        control = bd.make_control(sh, i, ZOOM, PANEL)
        tmp = os.path.join(os.environ.get("TEMP", "."), "_ctl_%s_%d.png"
                           % (bd.slug(set_name), i))
        control.save(tmp)
        rows.append({
            "name": "%s_%03d" % (bd.slug(set_name), i),
            "control": tmp,
            "ref": None,
            "prompt": CAPTION.format(trigger=trigger, kind=bd.prompt_kind(sh, i),
                                     hint=hints.get(i) or "terrain tile"),
            "seen": False,
        })
    return rows


def find_processor(groups):
    """Папка processor рядом с весами: пути вида .../snapshots/<sha>/transformer/файл."""
    for g in groups:
        first = g[0] if isinstance(g, (list, tuple)) else g
        snap = os.path.dirname(os.path.dirname(first))
        cand = os.path.join(snap, "processor")
        if os.path.isdir(cand):
            return cand
    return ""


def build_pipe(models_json, processor, vram_limit=None, offload=True):
    from diffsynth.pipelines.qwen_image_21 import QwenImage21Pipeline, ModelConfig
    with open(models_json, encoding="utf-8") as f:
        groups = json.load(f)
    # Куда снимать слой, когда он не считается. По умолчанию offload_device = None, и
    # снятие кладёт слой обратно НА КАРТУ: бюджет vram_limit при этом честно проверяется,
    # слой честно "снимается", а память не освобождается ни на байт. Нужен явный "cpu" -
    # тогда веса лежат в ОЗУ и приезжают на карту по одному слою.
    if offload:
        configs = [ModelConfig(g, offload_device="cpu", offload_dtype=torch.bfloat16,
                               onload_device="cuda", onload_dtype=torch.bfloat16)
                   for g in groups]
    else:
        configs = [ModelConfig(g) for g in groups]

    # processor_config обязателен ВСЕГДА. Без него конвейер не кодирует промпт, и падает уже
    # в модели: "model_fn_qwen_image_21() missing 3 required positional arguments:
    # prompt_embeds, prompt_embeds_mask, edit_image_pad_mask". Ошибка выглядит как про
    # картинки, а на самом деле про текст.
    if not processor:
        processor = find_processor(groups)
    if processor and os.path.isdir(processor):
        print("processor: %s" % processor)
        proc = ModelConfig(processor)
    else:
        print("processor: местного нет, беру с хаба")
        proc = ModelConfig(model_id="Qwen/Qwen-Image-2.1", origin_file_pattern="processor/")
    # Бюджет памяти карты. Без него DiffSynth кладёт на карту всё подряд, и когда 32 ГБ
    # кончаются, распределением занимается уже Windows: сливает веса в shared memory через
    # PCIe. Снаружи это выглядит как "глючит" - 16 с на шаг вместо секунд. С бюджетом слои
    # снимаются в ОЗУ осознанно, по одному, и провала нет.
    pipe = QwenImage21Pipeline.from_pretrained(
        torch_dtype=torch.bfloat16, device="cuda", model_configs=configs,
        processor_config=proc, vram_limit=vram_limit)
    print("управление памятью включено: %s" % pipe.vram_management_enabled)
    return pipe


def draw(rows, out, width, height, title):
    W, H = width, height
    cols = 4 if any(r["ref"] for r in rows) else 3
    head, foot = 26, 22
    im = Image.new("RGB", (10 + cols * (W + 6), head + len(rows) * (H + foot) + 10), (26, 26, 30))
    d = ImageDraw.Draw(im)
    d.text((10, 6), title, fill=(255, 220, 0), font=font())
    names = ["вход", "без LoRA", "с LoRA", "эталон"]
    for k, r in enumerate(rows):
        y = head + k * (H + foot)
        pics = [r["control_im"], r["off_im"], r["on_im"]] + ([r["ref_im"]] if cols == 4 else [])
        for j, p in enumerate(pics):
            if p is not None:
                im.paste(p.convert("RGB").resize((W, H), Image.LANCZOS), (10 + j * (W + 6), y))
            d.text((14 + j * (W + 6), y + 2), names[j], fill=(255, 220, 0), font=font(13))
        mark = "видел при обучении" if r["seen"] else "НЕ видел"
        d.text((12, y + H + 4), "%s  (%s)  %s" % (r["name"], mark, r["prompt"][:70]),
               fill=(150, 255, 150) if not r["seen"] else (170, 170, 170), font=font(13))
    im.save(out)


def main():
    ap = argparse.ArgumentParser(description="сравнить генерацию с LoRA и без")
    ap.add_argument("--lora", required=True, help="файл .safetensors с обученной LoRA")
    ap.add_argument("--data", default="dataset", help="папка датасета")
    ap.add_argument("--sheets", default="art/TERRAIN")
    ap.add_argument("--set", dest="set_name", default="", help="брать кадры из листа набора")
    ap.add_argument("--frames", default="", help="номера через запятую")
    ap.add_argument("--trigger", default="oxcehd, ")
    ap.add_argument("--models", default=r"E:\train\model_paths.json")
    ap.add_argument("--processor", default="")
    ap.add_argument("--width", type=int, default=384, help="как при обучении")
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--steps", type=int, default=40)
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--vram-limit", dest="vram_limit", type=float, default=26.0,
                    help="бюджет памяти карты в ГБ; 0 - без бюджета, как было")
    ap.add_argument("--no-offload", dest="no_offload", action="store_true",
                    help="держать все веса на карте (как было до бюджета)")
    ap.add_argument("--out", default="lora_test")
    args = ap.parse_args()

    frames = [int(x) for x in args.frames.replace(" ", "").split(",") if x] if args.frames else []
    rows = (from_sheet(args.sheets, args.set_name, frames, args.trigger) if args.set_name
            else from_dataset(args.data, frames))
    if not rows:
        sys.exit("нечего рисовать - проверь --frames")
    os.makedirs(args.out, exist_ok=True)
    print("кадров: %d, размер %dx%d, зерно %d" % (len(rows), args.width, args.height, args.seed))

    if args.vram_limit:
        print("бюджет памяти карты: %.0f ГБ из 32" % args.vram_limit)
    pipe = build_pipe(args.models, args.processor, args.vram_limit or None,
                      offload=not args.no_offload)

    def run(tag):
        for r in rows:
            ctl = Image.open(r["control"]).convert("RGB").resize(
                (args.width, args.height), Image.NEAREST)
            kw = dict(edit_image=[ctl], seed=args.seed,
                      height=args.height, width=args.width)
            try:
                img = pipe(r["prompt"], num_inference_steps=args.steps, **kw)
            except TypeError as e:
                if "num_inference_steps" not in str(e):
                    raise
                img = pipe(r["prompt"], **kw)   # у этого конвейера ключ зовётся иначе
            if isinstance(img, (list, tuple)):
                img = img[0]
            r[tag] = img
            img.save(os.path.join(args.out, "%s_%s.png" % (r["name"], tag)))
            print("  %-22s %s" % (r["name"], tag))

    print("\nбез LoRA:")
    run("off_im")
    print("\nгружу LoRA: %s" % args.lora)
    pipe.load_lora(pipe.dit, args.lora)
    print("с LoRA:")
    run("on_im")

    for r in rows:
        r["control_im"] = Image.open(r["control"]).convert("RGB")
        r["ref_im"] = Image.open(r["ref"]).convert("RGB") if r["ref"] else None

    sheet = os.path.join(args.out, "compare.png")
    draw(rows, sheet, 260, 325, "LoRA %s  |  зерно %d  |  %dx%d"
         % (os.path.basename(args.lora), args.seed, args.width, args.height))
    print("\nлист: %s" % sheet)
    print("Смотреть в первую очередь строки «НЕ видел» - на виденных будет красиво по памяти.")


if __name__ == "__main__":
    main()
