#!/usr/bin/env python3
"""build_dataset.py - пары control->target для дообучения (LoRA) на нашей графике.

Зачем. Возвраты из чата нарисованы красиво, но кадрированы как попало: у одной клетки
1774x887, у другой 2048x2048. Учить edit-модель на несовмещённых парах нельзя - она выучит
не «перерисуй ровно эту клетку», а «перерисуй и сдвинь». Поэтому target тут не то, что
вернул чат, а ВЫХОД КУЗНИЦЫ (tile_forge), положенный на ту же подложку и в тот же габарит,
что и control. После этого пара совмещена по построению.

Что делает:
  1. обходит папки gpt_* (или любые --src), собирает входы и возвраты по номеру кадра;
  2. набор берёт из первой строки _ОПИСАНИЯ.txt, а не из имени папки;
  3. гонит каждый возврат через tile_forge (пол - best_fit, предмет - fit_object);
  4. строит control (оригинал x zoom, nearest, на подложке) и target (клетка в тот же габарит);
  5. меряет: совпадение следа, тёмный край, перерисовку ровного, уход тона;
  6. пишет манифест musubi-tuner, отчёт и листы для глаз - по ним отмечать брак.

Приёмка руками: открыть dataset/sheets/*.png, номера брака вписать в dataset/reject.txt
(по строке «НАБОР кадр» или просто «кадр»), прогнать скрипт ещё раз - они выпадут.

    py -3 tools\\hdart\\build_dataset.py --root . --out dataset
    py -3 tools\\hdart\\build_dataset.py --root . --out dataset --only-kind floor
"""

import argparse
import csv
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np                                  # noqa: E402
from PIL import Image, ImageDraw, ImageFont         # noqa: E402

import tile_forge as tf                             # noqa: E402

ENC = "utf-8-sig"
PANEL = (90, 90, 96)
ZOOM = 24
IMG_EXT = (".png", ".webp", ".jpg", ".jpeg")
SET_RE = re.compile(r"([A-Za-z0-9_]+\.PCK)")


# ------------------------------------------------------------------ сбор материала

def read_set_name(d):
    """Имя набора из _ОПИСАНИЯ.txt. Имя папки (gpt_swamp7) набор не называет."""
    for n in os.listdir(d):
        if n.lower().startswith("_опис") or n.lower().startswith("_descr"):
            try:
                with open(os.path.join(d, n), encoding=ENC, errors="replace") as f:
                    head = f.read(400)
            except OSError:
                continue
            m = SET_RE.search(head)
            if m:
                return m.group(1).upper()
    return None


CYR = re.compile(r"[\u0400-\u04FF]")
DESC_ROW = re.compile(r"^(\d+)\s+(\S+\.(?:png|webp))\s+(.+)$")


def read_hints(d):
    """Английские подсказки из таблицы в _ОПИСАНИЯ.txt: «0  swamp_frame_00.png  dark green ...
    тёмная моховая трава». Русский столбец отрезаем по первой кириллической букве - разделитель
    там не всегда пробел. Нужно потому, что hints.json есть не у каждого набора, а без подсказки
    все подписи выходят одинаковыми, и LoRA учится отвечать на промпт одним и тем же."""
    out = {}
    for n in os.listdir(d):
        if not (n.lower().startswith("_опис") or n.lower().startswith("_descr")):
            continue
        try:
            with open(os.path.join(d, n), encoding=ENC, errors="replace") as f:
                lines = f.read().splitlines()
        except OSError:
            continue
        for line in lines:
            m = DESC_ROW.match(line.strip())
            if not m:
                continue
            tail = m.group(3)
            c = CYR.search(tail)
            eng = (tail[:c.start()] if c else tail).strip(" -\t")
            if eng:
                out[int(m.group(1))] = eng
    return out


def images_in(d):
    out = []
    try:
        names = os.listdir(d)
    except OSError:
        return out
    for n in sorted(names):
        p = os.path.join(d, n)
        if os.path.isfile(p) and n.lower().endswith(IMG_EXT):
            out.append(p)
    return out


def collect(root, patterns, set_override):
    """({набор: {кадр: {"control": путь|None, "targets": [пути]}}}, {набор: {кадр: подсказка}})"""
    got, hints = {}, {}
    dirs = []
    for n in sorted(os.listdir(root)):
        p = os.path.join(root, n)
        if os.path.isdir(p) and any(re.match(pat, n, re.IGNORECASE) for pat in patterns):
            dirs.append(p)
    if not dirs:
        raise SystemExit("в %s нет папок по образцу %s" % (root, ", ".join(patterns)))

    for d in dirs:
        s = set_override or read_set_name(d)
        if not s:
            print("  %s: набор не назван в _ОПИСАНИЯ.txt, папка пропущена"
                  % os.path.basename(d), file=sys.stderr)
            continue
        bucket = got.setdefault(s, {})
        hints.setdefault(s, {}).update(read_hints(d))
        # верхний уровень - входы
        for p in images_in(d):
            i = tf.frame_number(os.path.basename(p))
            if i is not None:
                bucket.setdefault(i, {"control": None, "targets": []})["control"] = p
        # подпапки - возвраты (return, Результат, как угодно)
        for n in sorted(os.listdir(d)):
            sub = os.path.join(d, n)
            if not os.path.isdir(sub):
                continue
            for p in images_in(sub):
                i = tf.frame_number(os.path.basename(p))
                if i is None:
                    print("  пропуск: в имени «%s» нет явного номера кадра"
                          % os.path.basename(p), file=sys.stderr)
                    continue
                bucket.setdefault(i, {"control": None, "targets": []})["targets"].append(p)
    return got, hints


def read_rejects(path):
    """Строки «НАБОР кадр» или «кадр». Всё после # - примечание."""
    out = set()
    if not os.path.exists(path):
        return out
    with open(path, encoding=ENC, errors="replace") as f:
        for line in f:
            line = line.split("#")[0].strip()
            if not line:
                continue
            parts = line.replace(",", " ").split()
            s = None
            for part in parts:
                if SET_RE.fullmatch(part):
                    s = part.upper()
                elif part.isdigit():
                    out.add((s, int(part)))
    return out


# ------------------------------------------------------------------ картинки пары

def on_panel(im, size, panel):
    bg = Image.new("RGB", size, panel)
    im = im.convert("RGBA")
    if im.size != size:
        im = im.resize(size, Image.LANCZOS)
    bg.paste(im, (0, 0), im)
    return bg


def make_control(sh, i, zoom, panel):
    frame = sh.frame(i)
    big = frame.resize((frame.width * zoom, frame.height * zoom), Image.NEAREST)
    return on_panel(big, big.size, panel)


MCD_WEST_WALL, MCD_NORTH_WALL = 1, 2


def prompt_kind(sh, i):
    """Вид клетки ДЛЯ ПОДПИСИ - по той же разбивке, что и промпты gen_tile.py: floor / wall /
    object. Это не то же, что вид для кузницы (там только floor и object): подпись обязана
    совпасть с тем, чем потом будем генерить, а режется клетка по своим правилам."""
    types = sh.lay.get("types") or []
    t = types[i] if i < len(types) else None
    if t in (MCD_WEST_WALL, MCD_NORTH_WALL):
        return "wall"
    return "floor" if t == 0 else "object"


def kind_of(sh, i, how):
    """Пол или предмет. По умолчанию как в кузнице - по типу MCD. Но у болота 6 кадров
    (6, 8, 11, 12, 13, 14) имеют тип 3 и при этом ground=true: партии на отрисовку набирались
    по ground (132 кадра), а режутся они по типу (126). --floor-by ground выравнивает."""
    if how == "ground":
        g = sh.lay.get("ground")
        if g and i < len(g):
            return "floor" if g[i] else "object"
    return "floor" if tf.is_floor(sh, i) else "object"


def forge_cell(sh, i, drawn, scale, args):
    """Клетка пака из нарисованного - тем же кодом, что и боевая кузница."""
    frame = sh.frame(i)
    if tf.alpha_box(frame) is None:
        return None, "в оригинале пусто", {}
    kind = kind_of(sh, i, args.floor_by)
    mask = frame.split()[3].resize((frame.width * scale, frame.height * scale), Image.NEAREST)
    rim, inner = tf.rim_masks(mask)
    orig_big = frame.resize((frame.width * scale, frame.height * scale), Image.NEAREST)
    own = tf.rim_delta(orig_big, rim, inner)
    if kind == "object":
        cell = tf.fit_object(drawn, frame, scale, args.alpha, args.grow)
        info = {"kind": kind, "inset": 0.0, "rim_own": own, "rim_after": own, "how": "предмет"}
    else:
        target = min(2.0, own)
        cell, ins, _before, after, how = tf.best_fit(drawn, frame, scale, target,
                                                     args.max_inset, 0.01, "auto")
        info = {"kind": kind, "inset": ins, "rim_own": own, "rim_after": after, "how": how}
    if cell is None:
        return None, "картинка пустая", info
    return cell, "", info


# ------------------------------------------------------------------ мерки

def lum(arr):
    return arr[..., 0] * 0.299 + arr[..., 1] * 0.587 + arr[..., 2] * 0.114


def band(im, frame, div):
    """Средний тон и разброс клетки, приведённой к 1/div размера кадра, по плотной части ромба.
    div=1 - вся фактура вместе с дизерингом оригинала; div=4 - только КРУПНЫЙ рисунок: у ровного
    песка там почти ноль, а у «волн», которые дают решётку по стыкам, - заметная величина.
    Полупрозрачную кайму берём вне зачёта: после сведения она темнее тела и врёт в разброс."""
    w, h = max(2, frame.width // div), max(2, frame.height // div)
    m = np.asarray(frame.resize((w, h), Image.BOX))[..., 3] > 250
    if m.sum() < 4:
        return None, None
    a = np.asarray(im.convert("RGB").resize((w, h), Image.BOX), np.float64)[m]
    return a.mean(0), float(lum(a).std())


def measure(sh, i, cell, scale):
    frame = sh.frame(i)
    fw, fh = frame.width, frame.height
    cell_a = np.asarray(cell)[..., 3] > 128
    keep = np.asarray(frame.split()[3].resize((fw * scale, fh * scale), Image.NEAREST)) > 128
    union = float((cell_a | keep).sum())
    iou = float((cell_a & keep).sum()) / union if union else 0.0

    orig = frame.convert("RGB")
    flat = Image.alpha_composite(Image.new("RGBA", cell.size, PANEL + (255,)), cell)
    o_mean, o_det = band(orig, frame, 1)
    c_mean, c_det = band(flat, frame, 1)
    _, o_low = band(orig, frame, 4)
    _, c_low = band(flat, frame, 4)
    if o_mean is None or c_mean is None:
        return {"iou": iou, "det": 1.0, "low_orig": 0.0, "low_cell": 0.0,
                "low_ratio": 1.0, "tone": 0.0}
    if o_low is None or c_low is None:
        o_low, c_low = o_det, c_det
    return {
        "iou": iou,
        "det": c_det / o_det if o_det > 0.5 else 1.0,
        "low_orig": o_low,
        "low_cell": c_low,
        "low_ratio": c_low / o_low if o_low > 0.5 else (99.0 if c_low > 3 else 1.0),
        "tone": float(np.abs(c_mean - o_mean).max()),
    }


def verdict(mt, info, args):
    flags = []
    # у предмета кузница берёт ЕГО СОБСТВЕННУЮ прозрачность (иначе от веток кактуса останутся
    # обрубки), так что след и не обязан совпасть с оригиналом - порог там свой
    lim = args.min_iou if info["kind"] == "floor" else args.min_iou_object
    if mt["iou"] < lim:
        flags.append("след не совпал %.2f" % mt["iou"])
    if info["kind"] == "floor" and mt["low_orig"] < args.flat_low and mt["low_cell"] > args.wave:
        flags.append("перерисовал ровное %.1f" % mt["low_cell"])
    if mt["low_orig"] >= args.flat_low and mt["low_ratio"] < args.min_low_ratio:
        flags.append("замылил рисунок x%.2f" % mt["low_ratio"])
    if mt["tone"] > args.max_tone:
        flags.append("тон ушёл на %.0f" % mt["tone"])
    if info["kind"] == "floor" and info["rim_after"] < min(0.0, info["rim_own"]) - 0.5:
        flags.append("край темнее середины %.1f" % info["rim_after"])
    return flags


# ------------------------------------------------------------------ листы для глаз

FONT_TRIES = (r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\arial.ttf",
              r"C:\Windows\Fonts\tahoma.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
_font = None


def font():
    """Встроенный шрифт PIL кириллицу рисует квадратами - берём системный TTF."""
    global _font
    if _font is None:
        for p in FONT_TRIES:
            try:
                _font = ImageFont.truetype(p, 15)
                break
            except OSError:
                continue
        else:
            _font = ImageFont.load_default()
    return _font


def sheet_rows(rows, path, title):
    W, H = 216, 270
    FW, FH = 430, 290
    top = 26
    out = Image.new("RGB", (10 + 3 * W + FW + 40, top + len(rows) * (H + 24) + 10), (26, 26, 30))
    d = ImageDraw.Draw(out)
    d.text((10, 6), title, fill=(255, 220, 0), font=font())
    for k, r in enumerate(rows):
        y = top + k * (H + 24)
        for j, im in enumerate((r["control_im"], r["raw_im"], r["target_im"])):
            out.paste(im.convert("RGB").resize((W, H), Image.LANCZOS), (10 + j * (W + 6), y))
        if r["field_im"] is not None:
            out.paste(r["field_im"].convert("RGB").resize((FW, FH), Image.LANCZOS),
                      (10 + 3 * (W + 6) + 10, y))
        mark = "ок" if not r["flags"] else "; ".join(r["flags"])
        col = (150, 255, 150) if not r["flags"] else (255, 140, 140)
        d.text((12, y + H + 4), "#%d %s  %s  |  %s"
               % (r["frame"], r["kind"], r["hint"][:46], mark), fill=col, font=font())
    out.save(path)


# ------------------------------------------------------------------ главное

def slug(set_name):
    return re.sub(r"[^a-z0-9]+", "_", set_name.lower()).strip("_")


def run(args):
    root = os.path.abspath(args.root)
    got, desc_hints = collect(root, args.src, args.set_name)
    rejects = read_rejects(os.path.join(args.out, "reject.txt"))
    if rejects:
        print("в reject.txt отмечено брака: %d" % len(rejects))

    img_dir = os.path.join(args.out, "images")
    ctl_dir = os.path.join(args.out, "control")
    shs_dir = os.path.join(args.out, "sheets")
    for p in (img_dir, ctl_dir, shs_dir):
        os.makedirs(p, exist_ok=True)
    if not args.no_clean:
        # иначе отмеченный в reject.txt кадр останется лежать с прошлого прогона и уедет в обучение
        for p in (img_dir, ctl_dir, shs_dir):
            for n in os.listdir(p):
                f = os.path.join(p, n)
                if os.path.isfile(f):
                    os.remove(f)

    report, counts = [], {}
    for set_name in sorted(got):
        try:
            sh = tf.Sheet(args.sheets, set_name)
        except OSError:
            print("  %s: нет листа в %s, набор пропущен" % (set_name, args.sheets),
                  file=sys.stderr)
            continue
        scale = args.scale or sh.scale
        sg = slug(set_name)
        pending, kept, nohint = [], 0, []
        frames = sorted(k for k in got[set_name] if got[set_name][k]["targets"])
        print("\n%s: кадров с возвратом %d" % (set_name, len(frames)))
        print("%-5s %-7s %-6s %-7s %-7s %-6s %-6s %s"
              % ("кадр", "вид", "след", "фактура", "крупное", "тон", "край", "итог"))

        for i in frames:
            if i >= sh.lay["count"]:
                print("  кадр %d: в наборе такого нет" % i, file=sys.stderr)
                continue
            if (set_name, i) in rejects or (None, i) in rejects:
                counts["брак руками"] = counts.get("брак руками", 0) + 1
                continue
            paths = sorted(got[set_name][i]["targets"], key=os.path.getmtime, reverse=True)
            src = paths[0]
            drawn = Image.open(src).convert("RGBA")
            cell, err, info = forge_cell(sh, i, drawn, scale, args)
            if cell is None:
                print("  кадр %d: %s" % (i, err), file=sys.stderr)
                counts[err] = counts.get(err, 0) + 1
                continue
            if args.only_kind and info["kind"] != args.only_kind:
                continue

            pkind = prompt_kind(sh, i)
            mt = measure(sh, i, cell, scale)
            flags = verdict(mt, info, args)
            control = make_control(sh, i, args.zoom, PANEL)
            target = on_panel(cell, control.size, PANEL)
            # hints.json набора, иначе таблица из _ОПИСАНИЯ.txt - ею рисовали, ей и подписывать
            hint = sh.hints.get(i) or desc_hints.get(set_name, {}).get(i, "")

            if not hint:
                nohint.append(i)
                if args.require_hint:
                    counts["без подсказки"] = counts.get("без подсказки", 0) + 1
                    continue
            name = "%s_%03d" % (sg, i)
            cap = args.caption.format(hint=hint or "terrain tile", kind=pkind,
                                      trigger=args.trigger, set=set_name).strip()
            if not flags or args.keep_bad:
                control.save(os.path.join(ctl_dir, name + ".png"))
                target.save(os.path.join(img_dir, name + ".png"))
                # подпись читает тренер: спецификация попала бы в начало промпта (исключение R-001)
                with open(os.path.join(img_dir, name + ".txt"), "w", encoding="utf-8") as f:
                    f.write(cap + "\n")
                kept += 1
            counts["принято" if not flags else "с замечаниями"] = \
                counts.get("принято" if not flags else "с замечаниями", 0) + 1

            print("%-5d %-7s %-6.2f %-7.2f %-7.2f %-6.0f %-6.1f %s"
                  % (i, info["kind"], mt["iou"], mt["det"], mt["low_ratio"], mt["tone"],
                     info["rim_after"], "ок" if not flags else "; ".join(flags)))
            report.append({"set": set_name, "frame": i, "name": name, "src": src,
                           "kind": info["kind"], "pkind": pkind, "hint": hint,
                           "how": info["how"], "caption": cap,
                           "flags": flags, **mt})
            if len(pending) < args.preview_max:
                field = None
                if info["kind"] == "floor":
                    field = tf.middle(tf.field_of(cell, sh.fw, sh.fh, scale), 560, 380)
                    field = Image.alpha_composite(
                        Image.new("RGBA", field.size, (38, 38, 42, 255)), field)
                pending.append({"frame": i, "kind": info["kind"], "hint": hint, "flags": flags,
                                "control_im": control, "raw_im": tf.checker(drawn),
                                "target_im": target, "field_im": field})

        pending.sort(key=lambda r: (not r["flags"], r["frame"]))
        g = sh.lay.get("ground")
        if g:
            odd = [i for i in frames if i < len(g) and i < len(sh.lay.get("types", []))
                   and g[i] and sh.lay["types"][i] != 0]
            if odd:
                print("%s: кадров с ground=true, но типом предмета: %d (%s%s) - сейчас режутся "
                      "как предметы, --floor-by ground сделает их полами"
                      % (set_name, len(odd), " ".join(str(x) for x in odd[:12]),
                         " ..." if len(odd) > 12 else ""))
        pending.sort(key=lambda r: (not r["flags"], r["frame"]))
        for k in range(0, len(pending), args.per_sheet):
            part = pending[k:k + args.per_sheet]
            p = os.path.join(shs_dir, "%s_%02d.png" % (sg, k // args.per_sheet + 1))
            sheet_rows(part, p, "%s  вход | возврат | пара для обучения | поле"
                       % set_name)
        if nohint:
            print("%s: без подсказки %d кадров (%s%s) - подпись у них одинаковая, а картинки "
                  "разные; заполнить hints.json или взять --require-hint"
                  % (set_name, len(nohint), " ".join(str(x) for x in nohint[:15]),
                     " ..." if len(nohint) > 15 else ""))
        print("%s: в датасет ушло %d" % (set_name, kept))

    write_report(args, report, counts)
    return report


def write_report(args, report, counts):
    path = os.path.join(args.out, "report.tsv")
    with open(path, "w", encoding=ENC, newline="") as f:
        f.write("набор\tкадр\tимя\tвид\tвид в подписи\tслед\tфактура\tкрупное оригинал\tкрупное клетка\t"
                "крупное отн\tтон\tзамечания\tкузница\tподсказка\tисходник\n")
        for r in report:
            f.write("%s\t%d\t%s\t%s\t%s\t%.3f\t%.2f\t%.1f\t%.1f\t%.2f\t%.0f\t%s\t%s\t%s\t%s\n"
                    % (r["set"], r["frame"], r["name"], r["kind"], r["pkind"],
                       r["iou"], r["det"],
                       r["low_orig"], r["low_cell"], r["low_ratio"], r["tone"],
                       "; ".join(r["flags"]), r["how"], r["hint"], r["src"]))

    ok = [r for r in report if not r["flags"]]
    by_kind = {}
    for r in ok:
        by_kind[(r["set"], r["kind"])] = by_kind.get((r["set"], r["kind"]), 0) + 1

    lines = ["# Датасет для дообучения", "",
             "Пар всего: %d, без замечаний: %d." % (len(report), len(ok)), ""]
    lines.append("| набор | вид | принято |")
    lines.append("|---|---|---|")
    for (s, k), n in sorted(by_kind.items()):
        lines.append("| %s | %s | %d |" % (s, k, n))
    lines += ["", "## Почему отсеялось", ""]
    for k, v in sorted(counts.items(), key=lambda kv: -kv[1]):
        lines.append("- %s: %d" % (k, v))
    lines += ["", "## Дальше", "",
              "1. Посмотреть листы в `sheets\\` - там вход, возврат, пара и поле укладки.",
              "2. Номера брака вписать в `reject.txt` и прогнать скрипт ещё раз.",
              "3. Подпись обязана совпадать с тем промптом, которым потом будем генерить.",
              "", "Обучение (DiffSynth-Studio, Qwen-Image-2.1):", "",
              "```",
              "accelerate launch examples/qwen_image_21/model_training/train.py \\",
              "  --dataset_base_path <эта папка> \\",
              "  --dataset_metadata_path <эта папка>/metadata.csv \\",
              "  --data_file_keys \"image,edit_image\" --extra_inputs \"edit_image\" \\",
              "  --max_pixels 1048576 --lora_base_model dit --lora_rank 32",
              "```", ""]
    with open(os.path.join(args.out, "report.md"), "w", encoding=ENC) as f:
        f.write("\n".join(lines))

    # главный манифест - DiffSynth-Studio: train.py читает metadata.csv по
    # --dataset_metadata_path, пути в нём относительно --dataset_base_path.
    # image - что должно получиться, edit_image - что подаётся на вход.
    # Спецификации нет: файл читает тренер (грабли R-001, исключение)
    with open(os.path.join(args.out, "metadata.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["image", "edit_image", "prompt"])
        for r in report:
            if r["flags"] and not args.keep_bad:
                continue
            w.writerow(["images/%s.png" % r["name"], "control/%s.png" % r["name"], r["caption"]])

    # запасной манифест: его читает tomllib, спецификация там тоже лишняя
    toml = ["# датасет для musubi-tuner, собран build_dataset.py",
            "[general]",
            "resolution = [%d, %d]" % (args.train_res, args.train_res),
            "caption_extension = \".txt\"",
            "batch_size = 1",
            "enable_bucket = true",
            "bucket_no_upscale = false",
            "",
            "[[datasets]]",
            "image_directory = \"%s\"" % os.path.abspath(
                os.path.join(args.out, "images")).replace("\\", "/"),
            "control_directory = \"%s\"" % os.path.abspath(
                os.path.join(args.out, "control")).replace("\\", "/"),
            "num_repeats = %d" % args.repeats,
            ""]
    with open(os.path.join(args.out, "dataset.toml"), "w", encoding="utf-8") as f:
        f.write("\n".join(toml))

    print("\nпар всего: %d, без замечаний: %d" % (len(report), len(ok)))
    for (s, k), n in sorted(by_kind.items()):
        print("  %-18s %-7s %d" % (s, k, n))
    print("манифест: %s (image, edit_image, prompt)"
          % os.path.join(args.out, "metadata.csv"))
    print("отчёт: %s (report.tsv, report.md), листы: %s"
          % (args.out, os.path.join(args.out, "sheets")))


# Коротко и одинаково. Длинные простыни PROMPT_HD/PROMPT_FLAT из gen_tile.py - это костыль
# для НЕобученной модели: ими мы уговариваем её не портить геометрию. Смысл LoRA в том, что
# после обучения уговаривать не надо, и промптом становится вот эта строка. Она же обязана
# стоять в gen_tile.py, когда включим LoRA, иначе обучение не сработает.
DEFAULT_CAPTION = "{trigger}X-COM isometric {kind} tile, {hint}"


def build_parser():
    ap = argparse.ArgumentParser(
        description="пары control->target для дообучения на нашей графике")
    ap.add_argument("--root", default=".", help="корень проекта, где лежат папки gpt_*")
    ap.add_argument("--src", nargs="*", default=[r"gpt_.*"],
                    help="образцы имён папок с материалом")
    ap.add_argument("--sheets", default="art/TERRAIN", help="папка листов")
    ap.add_argument("--out", default="dataset", help="куда писать датасет")
    ap.add_argument("--set", dest="set_name", default="",
                    help="набор силой, если в _ОПИСАНИЯ.txt его нет")
    ap.add_argument("--only-kind", choices=["floor", "object"], default="",
                    dest="only_kind", help="взять только полы или только предметы")
    ap.add_argument("--scale", type=int, default=0, help="масштаб пака (0 - как в layout.json)")
    ap.add_argument("--zoom", type=int, default=ZOOM, help="во сколько раз увеличен вход")
    ap.add_argument("--train-res", type=int, default=1024, dest="train_res",
                    help="разрешение обучения в манифесте")
    ap.add_argument("--repeats", type=int, default=1, help="num_repeats в манифесте")
    ap.add_argument("--trigger", default="", help="слово-ключ в начало подписи, например oxcehd")
    ap.add_argument("--caption", default=DEFAULT_CAPTION,
                    help="шаблон подписи: {hint} {kind} {trigger} {set}")
    ap.add_argument("--alpha", choices=["drawn", "original", "both"], default="drawn",
                    help="чья прозрачность у предмета")
    ap.add_argument("--grow", type=int, default=1)
    ap.add_argument("--max-inset", type=float, default=0.20, dest="max_inset")
    ap.add_argument("--min-iou", type=float, default=0.90, dest="min_iou",
                    help="ниже - след пола не совпал с оригиналом")
    ap.add_argument("--min-iou-object", type=float, default=0.70, dest="min_iou_object",
                    help="то же для предмета: у него своя прозрачность, совпадения и не ждём")
    ap.add_argument("--floor-by", choices=["type", "ground"], default="type", dest="floor_by",
                    help="чем считать пол: типом MCD (как кузница) или признаком ground")
    ap.add_argument("--flat-low", type=float, default=2.0, dest="flat_low",
                    help="крупный разброс, ниже которого кадр считается ровным")
    ap.add_argument("--wave", type=float, default=3.5,
                    help="крупный разброс у ровного кадра, выше которого это уже волны")
    ap.add_argument("--min-low-ratio", type=float, default=0.45, dest="min_low_ratio",
                    help="ниже - крупный рисунок оригинала замылен")
    ap.add_argument("--max-tone", type=float, default=45.0, dest="max_tone",
                    help="допустимый уход среднего тона")
    ap.add_argument("--require-hint", action="store_true", dest="require_hint",
                    help="не брать кадры, для которых нет английской подсказки")
    ap.add_argument("--no-clean", action="store_true", dest="no_clean",
                    help="не чистить images/control перед сборкой")
    ap.add_argument("--keep-bad", action="store_true", dest="keep_bad",
                    help="класть в датасет и пары с замечаниями")
    ap.add_argument("--preview-max", type=int, default=60, dest="preview_max")
    ap.add_argument("--per-sheet", type=int, default=6, dest="per_sheet")
    return ap


def main():
    args = build_parser().parse_args()
    if args.trigger and not args.trigger.endswith(" "):
        args.trigger += ", "
    os.makedirs(args.out, exist_ok=True)
    rp = os.path.join(args.out, "reject.txt")
    if not os.path.exists(rp):
        with open(rp, "w", encoding=ENC) as f:
            f.write("# номера бракованных кадров, по строке: «НАБОР кадр» или просто «кадр»\n"
                    "# например: DESERT.PCK 0\n")
    run(args)


if __name__ == "__main__":
    main()
