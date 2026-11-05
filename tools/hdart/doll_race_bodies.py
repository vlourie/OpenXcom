"""Одно тело на группу торса: по кадру на группу (тот же рисовальщик, что у doll_pipe_pilot), без голов и вещей.

Группы и основы - по мерке doll_body_census.py и глазами (docs/research/doll-pipeline-2026-11-03.md, 10.15).
Vitali 04.11: «следующие начинай с проверки: если тело одинаковое - делаем его, а на него уже все побрякушки и
татуировки накладываем». Слои других рас и layers/ не трогает: выход art/doll/pipe_pilot/<раса>/.

  py -3 tools/gpuq.py add --name doll_fhuman_bodies -- E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe \
      E:/OpenXCom/tools/hdart/doll_race_bodies.py
  --dry-run - без модели: входы кадров (рисунок = вход) и листы.
"""
import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import doll_pipe_pilot as P                         # до numpy: пилот ставит окружение модели
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import build_pack as bp
import doll_b2_render as db
import doll_ctl_pilot as cp
import doll_photo_pilot as dp
import vx_control as vc
import wall_section as ws

RACE = "FHUMAN"
OUT = os.path.join(db.ROOT, "art", "doll", "pipe_pilot", RACE.lower())
HAIR = 13                                           # у FHUMAN волосы отдельным слоем
# основа группы -> слова про торс: форму держит контроль, слова не дают модели спорить с ним
STRONG = "Strong build, broad shoulders, muscular arms and thighs. "
TORSO = {"M2": STRONG + "Clearly defined six-pack abdominal muscles, exactly as in the input.",
         "F14": "Strong build, broad shoulders. A smooth soft rounded belly with a navel.",
         "M19": "Strong lean build, broad shoulders. A lean flat stomach with a shallow muscle groove above the navel.",
         "F10": "Strong build, broad shoulders. A soft smooth belly with a navel.",
         "F1": STRONG + "A clear vertical centre line on the abdomen and defined lower abdominal muscles, exactly as in the input."}
# живот без кубиков: слова «no six-pack» в промпте модель понимала наоборот (M19, серия #1115)
NEG_ABS = {"F14", "M19", "F10"}
ABS = ", six-pack, abs, ripped abdominal muscles, segmented belly"
BUST = ", huge breasts, breast implants"
# #1115: раздутая грудь, кубики вместо полоски. #1116: «centre line», «inflated chest» и «coin» - плитка на груди, наклейки-монеты
# #1118: s4 у F14 - плита на груди, у M19 - нет наклейки. F1: s0 - сиреневая полоса на груди, s1 и s2 (#1127, #1128) - плита на груди
RESEED = {"F14": 3, "M19": 3, "F10": 2, "F1": 3}
# #1117: по коже F14 и M19 модель пишет руны и столбики знаков - одного tattoo в негативе мало
GLYPHS = ", text, letters, writing, glyphs, runes, symbols, circuit pattern, printed pattern on the skin"
VARIANTS = {}                                       # ещё сиды на выбор; основой становится сид из RESEED
GREY_CHROMA, GREY_L = 8, 38                         # подложка и ореол в сыром кадре
SHEET_BOX = (50, 44, 110, 148)                      # рамка тел FHUMAN с полем, на листах
SHEET_TORSO = (54, 66, 106, 112)


def setup():
    dp.RACE = RACE
    P.FILES, P.PAL = db.sprite_files(), db.game_palette()
    cp.FILES, cp.PAL = P.FILES, P.PAL
    # места на теле FHUMAN: замер по строкам 05.11 (пах - строка 100, середина 80; кисти - строки 94..108)
    P.FACE_BOX = (77, 56, 84, 66)
    P.THONG = [(69, 90), (80.5, 95), (92, 90), (92, 91.5), (82.5, 97.5), (81, 100.5), (79.5, 100.5), (78, 97.5), (69, 91.5)]
    P.HAND_ROWS, P.HAND_X = (94, 108), (63, 98)
    P.STRAP_ROWS = (86, 99)
    P.CHEST_LINES = ()                                  # черта на груди - беда кадров UBERGAL; появится - снять замер
    P.FEET_ROW = 136
    P.classic_marks = lambda look: np.zeros((db.H, db.W), bool)     # основы выбраны без вещей
    P.FILL_EDGES = False                                # щель режет figure_alpha: заливка давала плоские пятна и ступни-лопаты
    P.BODY = P.BODY.replace("A woman's figure with a full bust - never a man.",
                            "A woman's figure with a natural bust of the same size and shape as in the input - never a man.")
    assert "natural bust" in P.BODY


def names_of(look):
    return ["%s__2__%s_NUDE" % (RACE, look), "%s__10__HEAD_%s" % (RACE, look), "%s__%d__HAIR_%s" % (RACE, HAIR, look)]


def job(i, look, s=None):
    main = s is None
    s = RESEED.get(look, 0) if main else s
    names = [n for n in names_of(look) if n in P.FILES]
    body = db.load_indices(P.FILES[names[0]])
    skin = P.mode_colour(P.PAL[body][body != 0].astype(np.float32))
    pz = {"skin": P.skin_name(skin), "face": "a calm look", "neck": "", "hair": "", "head": ""}
    sil = np.zeros((db.H, db.W), bool)
    for n in names:
        sil |= dp.layer_mask(P.FILES, n)
    cl = dp.classic(P.FILES, P.PAL, names)
    return {"look": look, "tag": "body_%s_s%d" % (look, s), "main": main, "names": names, "sil": sil, "classic": cl,
            "prompt": P.body_text(pz) + " " + TORSO[look],
            "negative": P.negative_for(pz) + BUST + GLYPHS + (ABS if look in NEG_ABS else ""),
            "seed": P.RUN["seed"] + 1000 * s + i,
            "init": P.thong_on(P.to8(cp.b2_canvas(names))), "mask": P.mask8(sil),
            "control": vc.control_map(cl.crop(dp.CROP), dp.Z, "gray")}


def figure_alpha(rgb8, sil):
    """Альфа k=4: силуэт классики минус подложка, которую модель оставила внутри него (фигура у неё чуть уже).
    Режется только серое, связанное с внешней стороной силуэта: блик внутри тела не дыра. Края считаются на кадре x8."""
    x0, y0, x1, y1 = (v * dp.K for v in dp.CROP)
    lab = bp._rgb_to_lab(rgb8.astype(np.float32) / 255.0)
    grey = (np.hypot(lab[..., 1], lab[..., 2]) < GREY_CHROMA) & (lab[..., 0] > GREY_L)
    h, w = grey.shape
    outside = np.asarray(Image.fromarray(((ws.sil4(sil)[y0:y1, x0:x1] > 0.5) * 255).astype(np.uint8)).resize((w, h), Image.NEAREST)) == 0
    n, lab_c = cv2.connectedComponents((grey | outside).astype(np.uint8), connectivity=4)
    touch = np.unique(lab_c[outside])
    cut = np.isin(lab_c, touch[touch > 0]) & ~outside
    # тонкий ореол вне тела тёплый и в серое не попал: тоньше 3 точек k=4 - не тело, пальцы толще
    keep = cv2.morphologyEx((~cut & ~outside).astype(np.uint8), cv2.MORPH_OPEN,
                            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
    fig = cv2.GaussianBlur(keep.astype(np.float32), (0, 0), 1.5)    # край без лесенки (R-121)
    fig = cv2.resize(fig, (x1 - x0, y1 - y0), interpolation=cv2.INTER_AREA)
    a = ws.sil4(sil).astype(np.float32)
    a[y0:y1, x0:x1] *= np.clip((fig - 0.35) / 0.3, 0, 1)
    return a


def layer_cut(rgb4, alpha, edge=3.0):
    """Как P.layer_from, но альфа своя: полоса у края берёт цвет изнутри (светлая кайма модели, R-089)."""
    d = cv2.distanceTransform((alpha > 0.5).astype(np.uint8), cv2.DIST_L2, 5)
    fill, c = P._blur_in(rgb4, d > edge, edge)
    t = (np.clip(1 - (d - 1) / edge, 0, 1) * (c > 0.05) * (alpha > 0))[..., None]
    rgb = rgb4 * (1 - t) + fill * t
    out = np.dstack([rgb, alpha * 255])
    return Image.fromarray(np.clip(out + 0.5, 0, 255).astype(np.uint8), "RGBA")


def worker(jobs):
    painter = None
    for j in jobs:
        done = os.path.join(OUT, "raw", j["tag"] + "_out.png")
        if os.path.exists(done):
            continue
        if painter is None:
            painter = P.Painter([x["prompt"] for x in jobs] + [x["negative"] for x in jobs])
            print("модель загружена за %d с" % painter.load_s, flush=True)
        t = time.time()
        try:
            rgb, s0 = painter.paint(j["init"], j["mask"], j["control"], j["prompt"], j["seed"], P.RUN["body"]["strength"],
                                    P.RUN["body"]["control"], j["negative"])
        except Exception as e:                          # память карты: новый процесс продолжит
            print("кадр %s упал: %s" % (j["tag"], str(e)[:300]), flush=True)
            sys.exit(75)
        Image.fromarray(rgb).save(done)
        with open(os.path.join(OUT, "raw", j["tag"] + "_render.json"), "w", encoding=db.ENC) as f:
            json.dump({"seconds": round(time.time() - t), "sigma0": s0, "seed": j["seed"], "prompt": j["prompt"]}, f,
                      ensure_ascii=False)
        print("  %s: %.0f с" % (j["tag"], time.time() - t), flush=True)


def finish(jobs, dry):
    FONT = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 22)
    k = dp.K
    box = tuple(v * k for v in SHEET_BOX)
    torso = tuple(v * k for v in SHEET_TORSO)
    shifts = {}
    tiles, tors = [], []
    for j in jobs:
        look = j["look"]
        done = os.path.join(OUT, "raw", j["tag"] + "_out.png")
        rgb = np.asarray(j["init"].convert("RGB")) if dry else np.asarray(Image.open(done).convert("RGB"))
        f4, sd = P.skin_match(P.full4(rgb), look, j["sil"])
        shifts[look] = sd
        f4 = P.clean_body(f4, look)
        layer = layer_cut(f4, figure_alpha(rgb, j["sil"])) if not dry else P.layer_from(f4, j["sil"])
        if not dry and j["main"]:
            layer.save(os.path.join(OUT, "bases", look.lower() + ".png"))
        cl4 = j["classic"].resize((db.W * k, db.H * k), Image.NEAREST)
        name = j["tag"][len("body_"):]
        tiles.append((name, P.tile(cl4, box), P.tile(layer, box)))
        tors.append((name, P.tile(cl4, torso), P.tile(layer, torso)))
    for name, rows, per in (("bodies", tiles, 4), ("torsos", tors, 3)):
        w, h = rows[0][1].size
        n = (len(rows) + per - 1) // per
        sheet = Image.new("RGB", (per * (2 * w + 8), n * (h + 30)), (15, 15, 18))
        d = ImageDraw.Draw(sheet)
        for i, (look, a, b) in enumerate(rows):
            x, y = (i % per) * (2 * w + 8), (i // per) * (h + 30)
            d.text((x + 3, y + 2), "%s: классика | новое%s" % (look, " (вход)" if dry else ""), fill=(255, 230, 0), font=FONT)
            sheet.paste(a, (x, y + 30))
            sheet.paste(b, (x + w, y + 30))
        fn = os.path.join(OUT, name + ("_dry" if dry else "") + ".png")
        sheet.save(fn)
        print(fn, sheet.size, flush=True)
    print("сдвиг кожи:", json.dumps(shifts), flush=True)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--worker", action="store_true", help="(служебное) рисовать недостающие кадры подряд")
    ns = ap.parse_args()
    for d in ("raw", "bases"):
        os.makedirs(os.path.join(OUT, d), exist_ok=True)
    setup()
    jobs = [job(i, look) for i, look in enumerate(TORSO)]
    jobs += [job(i, look, s) for i, look in enumerate(TORSO) for s in VARIANTS.get(look, []) if s != RESEED.get(look, 0)]
    if ns.worker:
        worker(jobs)
        return
    if not ns.dry_run:
        for attempt in range(3):
            if all(os.path.exists(os.path.join(OUT, "raw", j["tag"] + "_out.png")) for j in jobs):
                break
            r = subprocess.run([sys.executable, os.path.abspath(__file__), "--worker"])
            print("рабочий процесс вышел с кодом %s (попытка %d)" % (r.returncode, attempt + 1), flush=True)
        missing = [j["tag"] for j in jobs if not os.path.exists(os.path.join(OUT, "raw", j["tag"] + "_out.png"))]
        if missing:
            raise SystemExit("не нарисованы: %s" % missing)
    finish(jobs, ns.dry_run)


if __name__ == "__main__":
    main()
