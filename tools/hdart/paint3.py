#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""paint3.py - третий генератор TERRAIN: промпт из фактов, гладкий вход, выбор лучшего.

Почему третий. Разбор LoRA-батча (docs/research/gen3-audit.md) нашёл семь причин брака, и
все они в конвейере, а не в «модель не умеет»:

  1. промпт без содержания: у 85% кадров «terrain tile», у предметов почти у всех;
  2. LoRA выучена на 127 парах пустыни и болота - всё рисует бурым камнем;
  3. прозрачность снималась хромакеем по серой подложке, а у 45% кадров больше четверти тела
     лежит в его допуске: серый металл выгрызался дырами («недорисован» 27-29%);
  4. на вход шло nearest-увеличение: ступеньки пикселей перерисовывались как рельеф (R-004);
  5. 384x480 - 0.18 МП при родных для Qwen-Image примерно 1 МП;
  6. cfg 1: негатив не действует вовсе (R-040);
  7. один ответ на кадр, никакого выбора; укладка кроп+растяжка по «содержимому» сбивала след.

Что делает этот:

  промпт   prompt_writer.Writer: тип по MCD, цвета по пикселям, тема террейна, проверенное
           описание; негатив против перекоса (серому - «rust, stone, wood grain»);
  вход     гладкое увеличение (Lanczos с премультипликацией + лёгкая резкость) на нейтральном
           фоне, КОНТРАСТНОМ к кадру; полу - поле из его копий на изосетке (R-005);
  размер   холст подбирается под --mp мегапикселей (0.45 по умолчанию, вдвое больше прежнего);
  модель   Qwen-Image-2.1 edit, по умолчанию БЕЗ LoRA, cfg 4 с негативом; --lora - если надо;
  укладка  кадр вырезается по ИЗВЕСТНЫМ координатам холста, без поиска «содержимого», плюс
           поиск сдвига в пределах пикселя оригинала;
  альфа    из силуэта оригинала (x4, как у прежних паков), а не из подложки;
  цвет     --lock: крупный план цвета берётся у оригинала, мелкая деталь - у модели. Серое не
           может стать бурым, пятно не может стать дырой, при этом фактура остаётся моделью;
  выбор    --cands ответов с разными зёрнами, каждый оценивается score_batch.score_frame (теми
           же мерками, что батч), в пак идёт лучший.

В мод НИЧЕГО не пишет (арт подключается после выбора Vitali). Клетки кладёт туда же, куда
любой другой ответ: art\TERRAIN\<НАБОР>.PCK\returned\gen3\<N>.png - уже готовые клетки x4,
кузница им не нужна. Копии в другие паки: dupe_plan.py --spread --sub gen3.
Листы «оригинал | прежний пак | LoRA | gen3» на тёмном полу: art\gen3\review\<НАБОР>.png.

    E:\train\.venv-train\Scripts\python.exe tools\hdart\paint3.py --sets C_INT,MARSEC_EXT_2 --plan-only
    E:\train\.venv-train\Scripts\python.exe tools\hdart\paint3.py --sets C_INT --frames 68,16 --cands 3
    E:\train\.venv-train\Scripts\python.exe tools\hdart\paint3.py --hours 4       по очереди census\roadmap.tsv
"""
import argparse
import csv
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import numpy as np                                      # noqa: E402
from PIL import Image, ImageDraw, ImageFilter           # noqa: E402

import build_dataset as bd                              # noqa: E402
import dupe_plan as dup                                 # noqa: E402
import prompt_writer as pw                              # noqa: E402
import score_batch as sb                                # noqa: E402
import tile_forge as tf                                 # noqa: E402

ENC = "utf-8-sig"
SUB = "gen3"
OUT = os.path.join("art", "gen3")
OLD = os.path.join("art", "_backup", "TERRAIN_before_lora_20260924_1057")
FLOOR_BG = (38, 38, 42)                                 # пол боя: на нём и смотрим (R-041)
BACKGROUNDS = [(38, 38, 42), (96, 96, 102), (176, 176, 182)]
SCALE = 4                                               # масштаб пака


# ------------------------------------------------------------------ картинки

def resize_f(arr, size, flt=Image.LANCZOS):
    """Плавающий массив HxW через PIL в режиме F - без потери точности на 8 битах."""
    return np.asarray(Image.fromarray(arr.astype(np.float32), "F").resize(size, flt), np.float64)


def smooth_up(rgba, g, sharpen=True):
    """Гладкое увеличение RGBA: премультипликация, чтобы прозрачное не тянуло край в чёрное.
    Nearest нельзя нигде (R-004): модель рисует ступеньки как рельеф."""
    a = np.asarray(rgba.convert("RGBA"), np.float64)
    al = a[..., 3] / 255.0
    size = (rgba.width * g, rgba.height * g)
    up_a = np.clip(resize_f(al, size), 0.0, 1.0)
    rgb = np.zeros((size[1], size[0], 3))
    for c in range(3):
        rgb[..., c] = resize_f(a[..., c] * al, size)
    rgb = np.where(up_a[..., None] > 0.02, rgb / np.maximum(up_a[..., None], 1e-3), 0.0)
    im = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), "RGB")
    if sharpen:
        im = im.filter(ImageFilter.UnsharpMask(radius=g * 0.4, percent=60, threshold=0))
    return np.asarray(im, np.float64), up_a


def pick_background(frame):
    """Нейтральный фон, самый далёкий от тела кадра: серый металл на серой подложке модель не
    отделяет от фона, а хромакей потом выгрызает его вместе с подложкой."""
    a = np.asarray(frame.convert("RGBA"), np.float64)
    px = a[..., :3][a[..., 3] > 128]
    if len(px) == 0:
        return BACKGROUNDS[0]
    best, best_d = BACKGROUNDS[0], -1.0
    for bg in BACKGROUNDS:
        d = np.abs(px - np.array(bg)).max(-1)
        q = float(np.percentile(d, 10))
        if q > best_d:
            best, best_d = bg, q
    return best


def gauss1d(sigma):
    r = max(1, int(math.ceil(sigma * 3)))
    x = np.arange(-r, r + 1, dtype=np.float64)
    k = np.exp(-0.5 * (x / sigma) ** 2)
    return k / k.sum()


def blur(arr, sigma):
    """Гаусс по двум осям (scipy в окружении обучения нет)."""
    k = gauss1d(sigma)
    r = len(k) // 2
    p = np.pad(arr, ((r, r), (r, r)), mode="edge")
    tmp = np.apply_along_axis(lambda v: np.convolve(v, k, mode="valid"), 1, p)
    return np.apply_along_axis(lambda v: np.convolve(v, k, mode="valid"), 0, tmp)


def masked_low(rgb, m, sigma):
    """Крупный план цвета внутри маски: размытие, нормированное на размытую маску."""
    mb = blur(m, sigma)
    out = np.zeros_like(rgb)
    for c in range(3):
        out[..., c] = blur(rgb[..., c] * m, sigma) / np.maximum(mb, 1e-3)
    return out


# ------------------------------------------------------------------ холст и укладка

class Canvas:
    """Что показываем модели и где на этом холсте лежит кадр (в пикселях оригинала)."""

    def __init__(self, sh, i, kind, mp, margin):
        fr = sh.frame(i).convert("RGBA")
        self.frame = fr
        fw, fh = fr.width, fr.height
        fb = tf.alpha_box(fr)
        if kind == "floor":
            # пол - поле из его копий на изосетке: модель видит землю, а не ромб на фоне (R-005)
            # n=2: при n=1 поле - ромб 3x3 с пустыми углами, и над клеткой видна подложка
            field = tf.field_of(fr, fw, fh, 1, n=2)
            cx, cy = 32, 16                             # где в поле центральная копия (n=2)
            # вырез обязан накрывать ВЕСЬ кадр, а не только ромб: make_cell режет по кадру
            # целиком, и при вырезе по габариту ромба сдвиг уходил в минус (пол 32x40, ромб внизу)
            x0 = max(0, min(cx, cx + fb[0] - 8))
            y0 = max(0, min(cy, cy + fb[1] - 8))
            x1 = min(field.width, max(cx + fw, cx + fb[2] + 8))
            y1 = min(field.height, max(cy + fh, cy + fb[3] + 8))
            base = field.crop((x0, y0, x1, y1))
            self.ox, self.oy = cx - x0, cy - y0
        else:
            base = Image.new("RGBA", (fw + 2 * margin, fh + 2 * margin), (0, 0, 0, 0))
            base.alpha_composite(fr, (margin, margin))
            self.ox, self.oy = margin, margin
        self.base = base
        self.g = max(6, int(math.sqrt(mp * 1e6 / (base.width * base.height))))
        self.W = int(math.ceil(base.width * self.g / 16.0)) * 16
        self.H = int(math.ceil(base.height * self.g / 16.0)) * 16
        self.bg = pick_background(fr)

    def control(self, rgba=False):
        rgb, al = smooth_up(self.base, self.g)
        if rgba:
            # Qwen-Image-2.1 читает все четыре канала VAE: прозрачный фон вместо подложки
            out = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
            arr = np.dstack([np.clip(rgb, 0, 255), np.clip(al, 0, 1) * 255.0]).astype(np.uint8)
            out.paste(Image.fromarray(arr, "RGBA"), (0, 0))
            return out
        bg = np.array(self.bg, np.float64)
        comp = rgb * al[..., None] + bg * (1.0 - al[..., None])
        out = Image.new("RGB", (self.W, self.H), self.bg)
        out.paste(Image.fromarray(np.clip(comp, 0, 255).astype(np.uint8), "RGB"), (0, 0))
        return out

    def at_scale(self, img, s):
        """Ответ модели в масштабе s оригинала (весь холст без добивки до кратного 16)."""
        if img.size != (self.W, self.H):
            img = img.resize((self.W, self.H), Image.LANCZOS)
        img = img.convert("RGB").crop((0, 0, self.base.width * self.g, self.base.height * self.g))
        return img.resize((self.base.width * s, self.base.height * s), Image.LANCZOS)


def find_shift(big, cv, ref_rgb, mask, radius):
    """Сдвиг (dx, dy) в пикселях x4, при котором ответ лучше ложится на оригинал. Qwen-edit
    иногда сдвигает картинку на полпикселя-пиксель; искать «содержимое» по фону нельзя (серое на
    сером), поэтому сравниваем яркость внутри расширенного силуэта."""
    arr = np.asarray(big, np.float64)
    L = arr @ np.array([0.299, 0.587, 0.114])
    R = ref_rgb @ np.array([0.299, 0.587, 0.114])
    R = R - R[mask].mean()
    h, w = mask.shape
    x0, y0 = cv.ox * SCALE, cv.oy * SCALE
    best, best_d, zero_d = (0, 0), None, None
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            ys, xs = y0 + dy, x0 + dx
            if ys < 0 or xs < 0 or ys + h > L.shape[0] or xs + w > L.shape[1]:
                continue
            c = L[ys:ys + h, xs:xs + w]
            c = c - c[mask].mean()
            d = float(np.abs(c - R)[mask].mean())
            if dx == 0 and dy == 0:
                zero_d = d
            if best_d is None or d < best_d:
                best, best_d = (dx, dy), d
    # сдвиг берём, только если он заметно лучше нуля: иначе это шум фактуры
    if zero_d is not None and best_d is not None and best_d > zero_d * 0.95:
        return (0, 0)
    return best


def make_cell(sh, i, cv, answer, kind, lock, alpha_mode, shift_radius):
    fr = cv.frame
    cw, ch = fr.width * SCALE, fr.height * SCALE
    mask_exact = np.asarray(fr.split()[3].resize((cw, ch), Image.NEAREST), np.float64) > 128
    ref_rgb, ref_a = smooth_up(fr, SCALE, sharpen=False)
    big = cv.at_scale(answer, SCALE)
    look = np.asarray(Image.fromarray(mask_exact.astype(np.uint8) * 255).filter(
        ImageFilter.MaxFilter(5)), np.float64) > 0
    dx, dy = find_shift(big, cv, ref_rgb, look, shift_radius)
    x0, y0 = cv.ox * SCALE + dx, cv.oy * SCALE + dy
    rgb = np.asarray(big, np.float64)[y0:y0 + ch, x0:x0 + cw]
    if alpha_mode == "smooth" and kind not in ("floor", "wall", "diagonal wall", "solid block"):
        alpha = np.clip((ref_a - 0.35) / 0.3, 0.0, 1.0)
    else:
        alpha = mask_exact.astype(np.float64)
    if lock > 0:
        # крупный план - у оригинала, мелкая деталь - у модели. Сигма в пикселях оригинала:
        # 1.2 - это пятна от трёх пикселей и крупнее; дизеринг оригинала в них уже усреднён
        m = (alpha > 0.5).astype(np.float64)
        if m.sum() >= 16:
            s = lock * SCALE
            rgb = rgb + masked_low(ref_rgb, m, s) - masked_low(rgb, m, s)
    rgb = np.clip(rgb, 0, 255)
    rgb[alpha <= 0] = 0
    out = np.dstack([rgb, alpha * 255.0]).astype(np.uint8)
    return Image.fromarray(out, "RGBA"), (dx, dy)


# ------------------------------------------------------------------ модель

def load_pipe(args):
    import torch
    import gen_lora_test as glt
    free, total = torch.cuda.mem_get_info()
    print("карта: свободно %.1f из %.1f ГБ" % (free / 2 ** 30, total / 2 ** 30), flush=True)
    if free < 16 * 2 ** 30:
        print("  МАЛО ПАМЯТИ: кто-то держит карту (Ollama держит модель описаний ~20 ГБ: "
              "ollama stop <модель>). Генерация пойдёт, но медленно.", flush=True)
    pipe = glt.build_pipe(args.models, args.processor, args.vram_limit or None, offload=True)
    if args.lora:
        pipe.load_lora(pipe.dit, args.lora)
        print("LoRA: %s" % os.path.basename(args.lora), flush=True)
    return pipe


def generate(pipe, prompt, negative, ctl, seed, args, refs=()):
    kw = dict(edit_image=[ctl] + list(refs), seed=seed, height=ctl.height, width=ctl.width,
              num_inference_steps=args.steps, cfg_scale=args.cfg)
    if args.cfg > 1.0:
        kw["negative_prompt"] = negative
    img = pipe(prompt, **kw)
    if isinstance(img, (list, tuple)):
        img = img[0]
    if img.mode == "RGBA":
        # ответ RGBA: альфу берём у оригинала, а прозрачное модели кладём на тот же фон,
        # что и на входе, - иначе under-alpha RGB бывает любым
        bg = Image.new("RGBA", img.size, FLOOR_BG + (255,))
        img = Image.alpha_composite(bg, img).convert("RGB")
    return img


# ------------------------------------------------------------------ лист для глаз

def review_sheet(sh, frames, gen_dir, path):
    """gen_dir - папка клеток этого набора (returned/gen3), остальные столбцы - по имени набора."""
    cols = [("оригинал", None), ("прежний пак", os.path.join(OLD, sh.name)),
            ("мод сейчас", os.path.join(sb.MOD, sh.name)), ("gen3", gen_dir)]
    cw, ch = sh.fw * SCALE, sh.fh * SCALE
    head = 20
    im = Image.new("RGB", (len(cols) * (cw + 6) + 6, head + len(frames) * (ch + 18) + 6), (20, 20, 24))
    d = ImageDraw.Draw(im)
    for k, (t, _) in enumerate(cols):
        d.text((8 + k * (cw + 6), 4), t, fill=(255, 220, 0))
    for r, (i, note) in enumerate(frames):
        y = head + r * (ch + 18)
        for k, (_t, src) in enumerate(cols):
            if src is None:
                cell = sh.frame(i).convert("RGBA").resize((cw, ch), Image.NEAREST)
            else:
                p = os.path.join(src, "%d.png" % i)
                if not os.path.exists(p):
                    continue
                cell = Image.open(p).convert("RGBA")
                if cell.size != (cw, ch):
                    cell = cell.resize((cw, ch), Image.LANCZOS)
            tile = Image.new("RGBA", (cw, ch), FLOOR_BG + (255,))
            tile.alpha_composite(cell)
            im.paste(tile.convert("RGB"), (6 + k * (cw + 6), y))
        d.text((8, y + ch + 2), "%d  %s" % (i, note)[:110], fill=(170, 170, 170))
    im.save(path)


# ------------------------------------------------------------------ прогон

def score_args():
    a = bd.build_parser().parse_args([])
    for k, v in dict(max_spill=0.03, max_miss=0.05, min_corr=0.70, det_lo=0.0, det_hi=1.60,
                     max_sat=0.10).items():
        setattr(a, k, v)
    return a


def hms(sec):
    sec = int(max(0, sec))
    return "%d ч %02d м" % (sec // 3600, (sec % 3600) // 60)


REPORT = ["набор", "кадр", "вид", "зерно", "годен", "балл", "флаги", "сдвиг", "фон", "холст",
          "с", "откуда", "промпт"]


def main():
    import gen_lora_batch as glb
    ap = argparse.ArgumentParser(description="третий генератор TERRAIN")
    ap.add_argument("--sheets", default=os.path.join("art", "TERRAIN"))
    ap.add_argument("--sets", default="", help="наборы через запятую; без - очередь roadmap")
    ap.add_argument("--roadmap", default=os.path.join("census", "roadmap.tsv"))
    ap.add_argument("--frames", default="", help="номера кадров через запятую")
    ap.add_argument("--list", default="", help="файл строк 'НАБОР кадр' - ровно эти кадры")
    ap.add_argument("--redo", action="store_true", help="перерисовать уже нарисованное")
    ap.add_argument("--hours", type=float, default=0.0, help="бюджет времени, 0 - без предела")
    ap.add_argument("--max-plan", type=int, default=4000, dest="max_plan")
    ap.add_argument("--plan-only", action="store_true", dest="plan_only",
                    help="план и промпты, модель не грузить")
    ap.add_argument("--mp", type=float, default=0.45, help="мегапикселей на холст")
    ap.add_argument("--margin", type=int, default=4, help="поле вокруг предмета, пикс. оригинала")
    ap.add_argument("--steps", type=int, default=24)
    ap.add_argument("--cfg", type=float, default=4.0, help="1.0 - без негатива (R-040)")
    ap.add_argument("--cands", type=int, default=2, help="ответов на кадр, берём лучший")
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--lock", type=float, default=1.2,
                    help="крупный план цвета - у оригинала; сигма в пикс. оригинала, 0 - выкл.")
    ap.add_argument("--alpha", choices=["exact", "smooth"], default="exact",
                    help="exact - силуэт оригинала x4; smooth - сглаженный у предметов")
    ap.add_argument("--shift", type=int, default=3, help="поиск сдвига, пикселей x4")
    ap.add_argument("--lora", default="", help="LoRA .safetensors; без - базовая модель")
    ap.add_argument("--lora-caption", action="store_true", dest="lora_caption",
                    help="подпись в формате обучения oxcehd вместо указания")
    ap.add_argument("--models", default=r"E:\train\model_paths.json")
    ap.add_argument("--processor", default="")
    ap.add_argument("--vram-limit", dest="vram_limit", type=float, default=26.0)
    ap.add_argument("--keep-raw", action="store_true", dest="keep_raw",
                    help="сохранять вход и все ответы в art/gen3/raw")
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--sub", default=SUB, help="папка клеток returned/<sub> - своя на вариант опыта")
    ap.add_argument("--prompt", choices=["plain", "struct", "lora"], default="plain",
                    help="plain - указание фразами; struct - разделами с материалом и hex")
    ap.add_argument("--refs", choices=["none", "sheet"], default="none",
                    help="sheet - вторым изображением весь лист набора с обведённым кадром")
    ap.add_argument("--input", choices=["bg", "rgba"], default="bg",
                    help="bg - на контрастном фоне; rgba - прозрачный фон, 2.1 читает альфу")
    args = ap.parse_args()
    if args.lora_caption:
        args.prompt = "lora"

    os.makedirs(args.out, exist_ok=True)
    deadline = time.time() + args.hours * 3600.0 if args.hours else None
    frames_only = {int(x) for x in args.frames.split(",") if x.strip()} if args.frames else None
    only = None
    if args.list:
        only = {}
        with open(args.list, encoding=ENC) as f:
            for line in f:
                p = line.split()
                if len(p) >= 2 and not line.startswith("#"):
                    only.setdefault(p[0].upper().replace(".PCK", ""), set()).add(int(p[1]))
        order = list(only)
    elif args.sets:
        order = [s.strip().upper().replace(".PCK", "") for s in args.sets.split(",") if s.strip()]
    else:
        order = [n for n, _t, _d in glb.read_order(args.roadmap)]

    # план до модели (R-018): повторы между паками, зеркала и кадры без записи MCD не рисуем
    by_frame, _ = dup.load(args.sheets)
    claimed = set()
    plans, total = [], 0
    for name in order:
        if args.redo:
            sh = tf.Sheet(args.sheets, name + ".PCK")
            todo = [i for i in sh.frames() if tf.alpha_box(sh.frame(i)) is not None]
            out = os.path.join(args.sheets, name + ".PCK", "returned", args.sub)
        else:
            sh, plan, err = glb.plan_set(args.sheets, name, args.sheets, by_frame, claimed, sub=args.sub)
            if err:
                print("  %s: %s" % (name, err))
                continue
            todo, _h, out, _d, _t = plan
        if frames_only is not None:
            todo = [i for i in todo if i in frames_only]
        if only is not None:
            todo = [i for i in todo if i in only[name]]
        if todo:
            plans.append((sh, todo, out))
            total += len(todo)
        if total > args.max_plan:
            break
    print("наборов: %d, кадров: %d, ответов на кадр: %d" % (len(plans), total, args.cands), flush=True)
    if not plans:
        sys.exit("нечего рисовать")

    writer = pw.Writer(args.sheets, args.out, vlm=False)
    prompts = {}
    for sh, todo, _o in plans:
        for i in todo:
            prompts[(sh.name, i)] = writer.row(sh, i)
    src = {}
    for r in prompts.values():
        if r:
            k = r["откуда"].split(" ")[0]
            src[k] = src.get(k, 0) + 1
    print("описание кадра: " + ", ".join("%s %d" % kv for kv in sorted(src.items())), flush=True)
    if args.plan_only:
        for (name, i), r in list(prompts.items())[:12]:
            cv = Canvas(tf.Sheet(args.sheets, name), i, r["вид"], args.mp, args.margin)
            print("\n%s %d [%s] холст %dx%d (x%d), фон %s\n  %s\n  негатив: %s"
                  % (name, i, r["вид"], cv.W, cv.H, cv.g, cv.bg, r["промпт"], r["негатив"]))
        return 0

    pipe = load_pipe(args)
    sargs = score_args()
    rep_path = os.path.join(args.out, "report.tsv")
    new_rep = not os.path.exists(rep_path)
    rep = open(rep_path, "a", encoding=ENC, newline="")
    w = csv.DictWriter(rep, REPORT, delimiter="\t", lineterminator="\n")
    if new_rep:
        w.writeheader()
    raw_dir = os.path.join(args.out, "raw")
    rev_dir = os.path.join(args.out, "review")
    os.makedirs(rev_dir, exist_ok=True)

    done, good, t0 = 0, 0, time.time()
    for sh, todo, out in plans:
        os.makedirs(out, exist_ok=True)
        notes = []
        print("=== %s: %d кадров" % (sh.name, len(todo)), flush=True)
        for i in todo:
            if deadline and time.time() > deadline:
                print("бюджет времени вышел, останов на целом кадре", flush=True)
                break
            r = prompts[(sh.name, i)]
            if r is None:
                continue
            t1 = time.time()
            cv = Canvas(sh, i, r["вид"], args.mp, args.margin)
            ctl = cv.control(rgba=args.input == "rgba")
            refs = [pw.sheet_hint(sh, i)] if args.refs == "sheet" else []
            if args.prompt == "lora":
                prompt = pw.lora_caption(r["вид"], r["_stats"], r["описание"])
            elif args.prompt == "struct":
                prompt = pw.compose_structured(r["вид"], r["_stats"], r["_theme"], r["описание"],
                                               r["_material"], r["_hex"], r["_glow"], len(refs))
            else:
                prompt = r["промпт"]
            best = None
            for k in range(args.cands):
                seed = args.seed + 7919 * k
                ans = generate(pipe, prompt, r["негатив"], ctl, seed, args, refs)
                # судим ДО возврата цвета: он по построению подтягивает тон, насыщенность и
                # корреляцию - ровно то, что меряют мерки, и они слепнут. Проверка на 1500
                # ответах LoRA: мерки дали 92% годных, а глазами каменная фактура на металле
                # осталась как была. Выбор - по честной клетке, в пак - с возвратом цвета
                raw_cell, shift = make_cell(sh, i, cv, ans, r["вид"], 0, args.alpha, args.shift)
                sc = sb.score_frame(sh, i, raw_cell, SCALE, sargs)
                cell = (make_cell(sh, i, cv, ans, r["вид"], args.lock, args.alpha, args.shift)[0]
                        if args.lock > 0 else raw_cell)
                key = (sc["годен"], sc["балл"]) if sc else (0, -9.0)
                if args.keep_raw:
                    d = os.path.join(raw_dir, sh.name)
                    os.makedirs(d, exist_ok=True)
                    if k == 0:
                        ctl.save(os.path.join(d, "%d_ctl.png" % i))
                    ans.save(os.path.join(d, "%d_s%d.png" % (i, seed)))
                if best is None or key > best[0]:
                    best = (key, cell, sc, seed, shift)
            key, cell, sc, seed, shift = best
            cell.save(os.path.join(out, "%d.png" % i))
            done += 1
            good += int(key[0])
            flags = (sc or {}).get("flags", "оценка не посчиталась")
            notes.append((i, "%s  балл %.2f  %s" % ("годен" if key[0] else "брак", key[1], flags)))
            w.writerow({"набор": sh.name, "кадр": i, "вид": r["вид"], "зерно": seed,
                        "годен": key[0], "балл": "%.3f" % key[1], "флаги": flags,
                        "сдвиг": "%d,%d" % shift, "фон": "%d,%d,%d" % cv.bg,
                        "холст": "%dx%d" % (cv.W, cv.H), "с": "%.1f" % (time.time() - t1),
                        "откуда": r["откуда"], "промпт": prompt})
            rep.flush()
            spent = time.time() - t0
            print("  %-16s %3d  %-5s балл %5.2f  %5.1f%%  годных %d/%d  ~%.0f с/кадр  осталось ~%s  %s"
                  % (sh.name, i, "годен" if key[0] else "брак", key[1], 100.0 * done / total, good,
                     done, spent / done, hms((total - done) * spent / done), flags), flush=True)
        if notes:
            review_sheet(sh, notes, out, os.path.join(rev_dir, sh.name + ".png"))
        if deadline and time.time() > deadline:
            break
    rep.close()
    print("\nнарисовано %d, годных по меркам %d (%.0f%%) за %s" %
          (done, good, 100.0 * good / max(1, done), hms(time.time() - t0)), flush=True)
    print("листы: %s   отчёт: %s" % (rev_dir, rep_path), flush=True)
    print("копии в другие паки: dupe_plan.py --spread --sub %s" % args.sub, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
