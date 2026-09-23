#!/usr/bin/env python3
"""
Курсоры боя (UFOGRAPH/CURSOR.PCK) новой моделью Qwen-Image-2.1.

Почему отдельный скрипт, а не gen_hd.py: у CURSOR.PCK нет MCD, значит нет ни полов, ни ромба,
а --painter qwen21 в gen_hd.py умеет только --only ground. Курсор - это накладка поверх клетки,
движок рисует её без затенения (Map.cpp, shade = 0), ровно как огонь; отсюда родство с gen_fire.py,
у которого и берётся вся обвязка: подложка, снятие подложки, габарит, лист, петля.

Чем курсор отличается от огня:
  * геометрия важнее красоты. Половинки рамки (кадры 0..5) и прицел с ромбом (6..10) обязаны
    лечь на сетку клеток пиксель в пиксель - модели прямо запрещено двигать линии;
  * поэтому cfg по умолчанию 4.0, а не 1.0, как у огня: при 1.0 негатив не действует вовсе,
    и модель молча выбрасывает штрих, который промпт не назвал поимённо (грабли R-040);
  * каждый штрих чертежа перечислен в описании по счёту, а описание снято с дампа пикселей
    оригинала, а не написано по памяти;
  * кадры одной петли должны быть роднёй: зерно одно на группу, а не на кадр;
  * готовые кадры кладутся прямо в пак (--pack), потому что для CURSOR.PCK build_pack.py
    не нужен - ни ромба, ни маски оригинала, ни chroma lock здесь нет.

    tools\\hdart\\.venv-qwen21\\Scripts\\python.exe tools\\hdart\\gen_cursor.py --tries 1
    ... --frame 11,12,13,14,15,16          только картиночные курсоры
    ... --pack user\\mods\\hd\\hd\\CURSOR.PCK   разложить по паку (по умолчанию только в листы)

Смотреть в первую очередь cursor_sheet_t1.png: верхний ряд - оригинал, нижний - как вышло.
"""
import argparse
import os
import sys
import time
import zlib

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_hd  # noqa: E402
import gen_fire as gf  # noqa: E402

# Что на каком кадре - прочитано с самих кадров и сверено с src/Battlescape/Map.cpp:
# рамка 0/1 верх (красный/жёлтый), 2 верх синий пунктир, 3/4 низ, 5 низ синий,
# 6 прицел красный, 7..10 прицел жёлтый (4 фазы), 11/12 пси, 13/14 точка пути, 15/16 бросок.
# Описания сверены с пикселями оригинала (дамп кадров 1, 4 и 7), а не написаны по памяти:
# модель роняет ту линию, которую промпт не назвал поимённо, поэтому штрихи перечислены по счёту.
BOX_TOP = ("box", "верх рамки выбора",
           "the upper half of an isometric selection box, made of seven straight strokes: "
           "(1) and (2) a shallow inverted V whose apex is at the top centre of the frame and whose "
           "two arms run down and outward to the left and right edges; "
           "(3) and (4) a vertical bar down the far left edge and a vertical bar down the far right "
           "edge, both running from the ends of those arms to the bottom of the frame; "
           "(5) a THICK VERTICAL STEM down the exact middle, from the apex to about two thirds of "
           "the height - this stem is the most important stroke and must be there; "
           "(6) and (7) from the foot of that stem, two arms running down and outward to the bottom "
           "ends of the left and right vertical bars")
BOX_BOTTOM = ("box", "низ рамки выбора",
              "the lower half of an isometric selection box, made of five straight strokes: "
              "(1) and (2) two arms coming down and inward from the upper left and the upper right "
              "and meeting at the centre; "
              "(3) a THICK VERTICAL STEM running from that meeting point straight down almost to the "
              "bottom of the frame - this stem is the most important stroke and must be there; "
              "(4) and (5) at the very bottom, two more arms running down and inward from the left "
              "and right edges to meet directly under the foot of the stem")
AIM = ("aim", "прицел",
       "a targeting reticle: a circle outline; four solid wedge-shaped arrows, one from each side, "
       "wide where they touch the circle and tapering to a point at the centre; a small cross at the "
       "exact centre; and below the circle a flat isometric diamond outline marking the floor tile")
PSI = ("psi", "пси-усилитель",
       "a psi-amp cursor: a small grey alien head seen from the front, flanked left and right by "
       "vertical sound-wave bars")
WAYPOINT = ("waypoint", "точка пути",
            "a waypoint marker: a blue dart pointing left, with a yellow band and a black-and-white "
            "chequered tail")
THROW = ("throw", "бросок",
         "a throw cursor: a wide blue arrowhead pointing down with two small grey spheres above it")

FRAMES = {
    0:  (BOX_TOP,    "red",              "loop_box_red"),
    1:  (BOX_TOP,    "yellow",           "loop_box_yellow"),
    2:  (BOX_TOP,    "pale blue dotted", "loop_box_blue"),
    3:  (BOX_BOTTOM, "red",              "loop_box_red"),
    4:  (BOX_BOTTOM, "yellow",           "loop_box_yellow"),
    5:  (BOX_BOTTOM, "pale blue dotted", "loop_box_blue"),
    6:  (AIM,        "red",              "loop_aim_red"),
    7:  (AIM,        "yellow",           "loop_aim_yellow"),
    8:  (AIM,        "yellow",           "loop_aim_yellow"),
    9:  (AIM,        "yellow",           "loop_aim_yellow"),
    10: (AIM,        "yellow",           "loop_aim_yellow"),
    11: (PSI,        "grey and white",   "loop_psi"),
    12: (PSI,        "grey and white",   "loop_psi"),
    13: (WAYPOINT,   "blue and yellow",  "loop_waypoint"),
    14: (WAYPOINT,   "blue and yellow",  "loop_waypoint"),
    15: (THROW,      "blue and grey",    "loop_throw"),
    16: (THROW,      "blue and grey",    "loop_throw"),
}

# Кадры, где модели нельзя фантазировать вообще: они ложатся на сетку клеток.
STRICT = set(range(0, 11))
# Синие половинки рамки нарисованы ПУНКТИРОМ, и это не лесенка от низкого разрешения, а знак:
# так помечена клетка, до которой не дойти. Запрет на ступеньки для них выключается, иначе
# модель считает точки браком и сливает их в сплошную линию.
DOTTED = {2, 5}

PROMPT = (
    "<image1> is a low-resolution sprite from the 1994 game X-COM, shown enlarged on a flat grey "
    "panel. It is a battlescape mouse cursor drawn as {colour} lines: {what}. "
    "Redraw it as the same cursor at high resolution: crisp clean edges, smooth anti-aliasing, a "
    "faint glow along the lines, slightly richer {colour} shading where the original already has a "
    "bright-to-dark gradient. "
    "Where a stroke in <image1> fades from bright to dark, keep that fade in the same place and in "
    "the same direction; never fill a stroke with one flat tone. "
    "{strict}"
    "Keep the flat grey panel behind it exactly as it is, perfectly uniform, with nothing drawn on it: "
    "no tile, no ground, no terrain, no objects, no shadow, no frame, no text.")

STRICT_TEXT = (
    "This cursor has to line up with the game grid pixel for pixel, so keep the geometry exactly: "
    "every line stays straight and in the same place, same endpoints, same corners, same angles, "
    "same length, same thickness relative to the frame. Do not move, rotate, bend, stretch or "
    "re-space anything, and do not add a single new line. "
    "Count the strokes listed above and keep every single one of them - removing even one, "
    "especially the vertical stem in the middle, makes the cursor useless. "
    "{edges}")

SMOOTH_TEXT = (
    "The edges in <image1> look stair-stepped only because the original is 32 by 40 pixels: draw "
    "each stroke as one clean straight line through the same two endpoints, without the stair "
    "steps, and do not turn the stair steps into a pattern or a texture. ")

DOTTED_TEXT = (
    "Every stroke here is DOTTED on purpose: it is a row of separate small square dots with a clear "
    "gap after each one. The dots are not an artefact and not a broken line - they are what tells "
    "the player this tile cannot be reached. Keep exactly that dotted rhythm: the same number of "
    "dots along each stroke, the same gaps, the same dot size. Never join the dots into a solid "
    "continuous line. ")

LOOSE_TEXT = (
    "Keep the same silhouette, the same size and the same position inside the frame. ")

PHASE = " This is phase {n} of {m} of the cursor animation; all phases must look like one drawing."

NEGATIVE = ("missing line, missing stroke, missing vertical bar, missing stem, removed element, "
            "flat single-tone fill, lost gradient, "
            "{edges}"
            "changed shape, changed position, changed size, moved lines, "
            "bent lines, curved lines, extra lines, extra elements, different colors, palette shift, "
            "photorealism, 3D render, metal texture, drop shadow, cast shadow, ground, tile, terrain, "
            "objects, background pattern, gradient background, vignette, panel border, frame, outline "
            "box, text, watermark, blur, noise, jpeg artifacts")

NEG_SMOOTH = "stair-stepped edges, jagged pixel edges, pixel-art texture, "
NEG_DOTTED = "solid continuous line, joined dots, filled line, dashes merged together, "


def run_pass(painter, args, prompt, image, seed, negative):
    """То же, что gen_fire.run_pass, но негатив свой и зависит от кадра."""
    torch = painter.torch
    W, H = gen_hd.qwen21_size(image.width, image.height, args.mp)
    src = image.convert("RGB").resize((W, H), Image.LANCZOS)
    kw = {"prompt": prompt, "num_inference_steps": args.steps,
          "generator": torch.Generator("cuda").manual_seed(seed)}
    if "image" in painter.accepts:
        kw["image"] = src
    elif "images" in painter.accepts:
        kw["images"] = [src]
    if "negative_prompt" in painter.accepts:
        kw["negative_prompt"] = negative
    if "true_cfg_scale" in painter.accepts:
        kw["true_cfg_scale"] = args.cfg
    elif "guidance_scale" in painter.accepts:
        kw["guidance_scale"] = args.cfg
    if "width" in painter.accepts:
        kw["width"], kw["height"] = W, H
    return painter.pipe(**kw).images[0]


def alpha_floor(rgba, floor):
    """Убрать остаток подложки.

    unpanel снимает ровный фон арифметикой, но у модели фон не идеально ровный, и после него
    внутри габарита остаётся дымка с альфой около 20 из 255. to_footprint режет по
    ПРЯМОУГОЛЬНИКУ габарита, поэтому дымка получает резкий край и на тёмном полу читается как
    светлая рамка вокруг рисунка. На шахматке её не видно вовсе - смотреть надо на полу (R-019).
    Порог гасит всё ниже floor и растягивает остальное, чтобы края не потеряли плотность."""
    import numpy as np
    a = np.asarray(rgba, dtype=np.float32)
    al = a[..., 3] / 255.0
    al = np.clip((al - floor) / max(1e-3, 1.0 - floor), 0.0, 1.0)
    a[..., 3] = al * 255.0
    return Image.fromarray(a.astype(np.uint8), "RGBA")


def prompt_for(i, phase_n, phase_m):
    (_kind, _ru, what), colour, _loop = FRAMES[i]
    edges = DOTTED_TEXT if i in DOTTED else SMOOTH_TEXT
    strict = STRICT_TEXT.format(edges=edges) if i in STRICT else LOOSE_TEXT
    p = PROMPT.format(colour=colour, what=what, strict=strict)
    if phase_m > 1:
        p += PHASE.replace("{n}", str(phase_n)).replace("{m}", str(phase_m))
    return p


def negative_for(i):
    return NEGATIVE.format(edges=NEG_DOTTED if i in DOTTED else NEG_SMOOTH)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default=gen_hd.DEFAULT_MODELS_DIR)
    ap.add_argument("--sheets", default="art/TERRAIN")
    ap.add_argument("--set", dest="set_name", default="CURSOR.PCK")
    ap.add_argument("--frame", default="", help="кадры через запятую; пусто - все 17")
    ap.add_argument("--tries", type=int, default=1, help="сколько раз нарисовать весь набор")
    ap.add_argument("--try-base", type=int, default=0, dest="try_base",
                    help="с какого номера нумеровать попытки: повтор не должен затирать прошлый лист")
    ap.add_argument("--seed", type=int, default=4242)
    ap.add_argument("--steps", type=int, default=40)
    ap.add_argument("--cfg", type=float, default=4.0,
                    help="при 1.0 негатив не действует вовсе, и модель молча роняет штрихи (R-040); "
                         "кадр дороже примерно вдвое, но без этого чертёж не держится")
    ap.add_argument("--mp", type=float, default=2.0)
    ap.add_argument("--zoom", type=int, default=24, help="во сколько раз увеличить кадр на входе")
    ap.add_argument("--scale", type=int, default=4, help="масштаб пака для готового кадра")
    ap.add_argument("--grow", type=int, default=1,
                    help="на сколько исходных пикселей можно выйти за габарит оригинала")
    ap.add_argument("--soft", type=int, default=48, help="порог снятия подложки")
    ap.add_argument("--alpha-floor", type=float, default=0.30, dest="alpha_floor",
                    help="ниже этой альфы считаем остатком подложки и гасим; 0 - не трогать")
    ap.add_argument("--repack", default="",
                    help="не рисовать, а пересобрать готовые кадры из сохранённых *_hd.png: "
                         "список вида 0:2,1:2,2:3 - кадр и номер победившей попытки")
    ap.add_argument("--panel", default="90,90,96", help="цвет подложки")
    ap.add_argument("--pack", default="", help="каталог пака: сюда лягут <кадр>.png готовыми")
    ap.add_argument("--pack-try", type=int, default=1, dest="pack_try",
                    help="какую попытку раскладывать по паку")
    ap.add_argument("--gif-ms", type=int, default=125, dest="gif_ms")
    ap.add_argument("--model", default="")
    ap.add_argument("--offload", default="model", choices=["model", "seq", "none"])
    args = ap.parse_args()

    panel = tuple(int(v) for v in args.panel.split(","))
    set_dir, lay, hints, sheet = gf.load_set(args.sheets, args.set_name)
    frames = ([int(v) for v in args.frame.split(",") if v.strip()]
              if args.frame else sorted(FRAMES))
    bad = [i for i in frames if i not in FRAMES]
    if bad:
        raise SystemExit("нет описания для кадров %s - допиши их в FRAMES" % bad)
    out_dir = os.path.join(set_dir, "cursor")
    os.makedirs(out_dir, exist_ok=True)
    if args.pack:
        os.makedirs(args.pack, exist_ok=True)

    if args.repack:
        # Пересборка без модели: берём сохранённый вывод модели и заново снимаем подложку,
        # режем по габариту и гасим дымку. Какая попытка победила на каком кадре - в --repack,
        # чтобы выбор лежал в команде, а не в чьей-то памяти.
        if not args.pack:
            raise SystemExit("--repack без --pack бессмыслен: некуда класть")
        pick = {}
        for part in args.repack.split(","):
            k, v = part.split(":")
            pick[int(k)] = int(v)
        for i in sorted(pick):
            hd = os.path.join(out_dir, "cur_%02d_t%d_hd.png" % (i, pick[i]))
            if not os.path.exists(hd):
                raise SystemExit("нет кадра %s - этой попытки не было" % hd)
            frame = gf.frame_of(sheet, lay, i)
            rgba = gf.unpanel(Image.open(hd).convert("RGB"), panel, args.soft)
            cut = gf.to_footprint(rgba, frame, args.scale, args.grow)
            if args.alpha_floor > 0:
                cut = alpha_floor(cut, args.alpha_floor)
            gen_hd.save_png(cut, os.path.join(out_dir, "cur_%02d_t%d_cut.png" % (i, pick[i])))
            gen_hd.save_png(cut, os.path.join(args.pack, "%d.png" % i))
            print("кадр %2d <- попытка %d" % (i, pick[i]))
        print("пересобрано %d кадр(ов) -> %s" % (len(pick), args.pack))
        return

    # номер фазы внутри своей петли - чтобы модель знала, что кадры родня
    order = {}
    for i in sorted(FRAMES):
        loop = FRAMES[i][2]
        order.setdefault(loop, []).append(i)

    ns = argparse.Namespace(models=args.models, qwen21_model=args.model, qwen21_steps=args.steps,
                            qwen21_cfg=args.cfg, qwen21_mp=args.mp, qwen21_strength=0.0,
                            qwen21_offload=args.offload, qwen21_thrifty=False,
                            qwen21_ref="", qwen21_ref_mp=1.0, qwen21_prompt="strict",
                            qwen21_hint="off", qwen21_ref_order="ref-first")
    painter = gen_hd.Qwen21Painter(ns, {"ground": ("", "")})

    t0 = time.time()
    total = len(frames) * args.tries
    done = 0
    for t in range(args.tries):
        tn = args.try_base + t + 1
        cuts, tops, bottoms = {}, [], []
        for i in frames:
            loop = FRAMES[i][2]
            # зерно одно на всю петлю: фазы обязаны быть одним рисунком, а не пятью разными
            seed = args.seed + t * 7919 + (zlib.crc32(loop.encode()) % 100000)
            frame = gf.frame_of(sheet, lay, i)
            src = gf.on_panel(frame, args.zoom, panel)
            p = prompt_for(i, order[loop].index(i) + 1, len(order[loop]))
            print("попытка %d/%d, кадр %d (%s, %s) | вход %dx%d, зерно %d"
                  % (tn, args.try_base + args.tries, i, FRAMES[i][0][1], loop,
                     src.width, src.height, seed), flush=True)
            hd = run_pass(painter, args, p, src, seed, negative_for(i))
            gen_hd.save_png(hd, os.path.join(out_dir, "cur_%02d_t%d_hd.png" % (i, tn)))
            rgba = gf.unpanel(hd, panel, args.soft)
            cut = gf.to_footprint(rgba, frame, args.scale, args.grow)
            if args.alpha_floor > 0:
                cut = alpha_floor(cut, args.alpha_floor)
            gen_hd.save_png(cut, os.path.join(out_dir, "cur_%02d_t%d_cut.png" % (i, tn)))
            cuts[i] = cut
            tops.append(gen_hd.label(gf.checker(frame.resize(src.size, Image.NEAREST)),
                                     "оригинал %d" % i))
            bottoms.append(gen_hd.label(gf.checker(cut.resize(src.size, Image.NEAREST)),
                                        "кадр %d" % i))
            done += 1
            el = time.time() - t0
            print("  %s, осталось ~%s" % (gen_hd.human_time(el),
                                          gen_hd.human_time(el / done * (total - done))), flush=True)

        h = 300
        fit = lambda ps: [p.resize((max(1, round(h * p.width / p.height)), h), Image.LANCZOS)
                          for p in ps]
        rows = []
        step = 6
        for a in range(0, len(tops), step):
            rows.append(gen_hd.side_by_side(fit(tops[a:a + step])))
            rows.append(gen_hd.side_by_side(fit(bottoms[a:a + step])))
        board = Image.new("RGB", (max(r.width for r in rows), sum(r.height for r in rows) + 8 * len(rows)),
                          (32, 32, 36))
        y = 0
        for r in rows:
            board.paste(r, (0, y)); y += r.height + 8
        sheet_path = os.path.join(out_dir, "cursor_sheet_t%d.png" % tn)
        gen_hd.save_png(board, sheet_path)
        print("  лист: %s  <- смотреть в первую очередь" % sheet_path)

        for loop, ids in order.items():
            ids = [i for i in ids if i in cuts]
            if len(ids) > 1:
                gif = os.path.join(out_dir, "%s_t%d.gif" % (loop, tn))
                gf.save_loop([cuts[i] for i in ids], gif, max(1, 8 // args.scale * 2), args.gif_ms)
                print("  петля %s: %s" % (loop, gif))

        if args.pack and tn == args.pack_try:
            for i, cut in sorted(cuts.items()):
                gen_hd.save_png(cut, os.path.join(args.pack, "%d.png" % i))
            print("  в пак: %d кадр(ов) -> %s" % (len(cuts), args.pack))

    print("готово за %s" % gen_hd.human_time(time.time() - t0))


if __name__ == "__main__":
    main()
