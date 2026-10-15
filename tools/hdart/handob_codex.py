#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Пилот хвата: шесть пробных HD-кадров HANDOB через Codex image_gen (06.10).

Указание Vitali 06.10: Codex ровно на шесть картинок - STR_OLD_SNIPER_RIFLE, STR_SAW, STR_TOMMYGUN, у каждого
кадры handSprite+2 и +4 (стойка и прицел взгляда d2). Массовой генерации, судей и правок движка нет.

Видеокарту не трогает: картинку рисует сервис OpenAI (weapons_chatgpt.call, задание через stdin - R-222).

prep  - входы и промпты, затем заморозка целевых зон (target_zones.json): зоны кистей по классике и кисти
        согласованной позы в двух видах d2, хэши входов. Зоны после генерации не двигаются.
run   - codex exec по замороженным входам; ответ - codex/raw/<тип>.<кадр>.cgN.png. Хэши входов сверяются
        с заморозкой, расхождение - отказ.

Входы на кадр:
  1 - кадр HANDOB 32x40 x32 nearest: ракурс, раскладка, длина, дуло (единственный источник геометрии);
  2 - BIGOBS ствола 32x48 x32 nearest: конструкция, материалы, цвета (ориентация НЕ отсюда);
  3 - образец манеры (эталон Vitali, тот же, что у weapons_chatgpt --v2): только качество рисунка.

    py -3.13 tools/hdart/handob_codex.py prep
    py -3.13 tools/hdart/handob_codex.py run --only STR_SAW.1786
"""
import argparse
import datetime
import hashlib
import json
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)

import battle_view as bv                # noqa: E402
import grip_matrix as gm                # noqa: E402
import item_photo as ip                 # noqa: E402

ENC = "utf-8-sig"
PILOT = "art/items/weapons100-v1/grip_pilot"
OUT = os.path.join(PILOT, "codex")
FREEZE = os.path.join(PILOT, "target_zones.json")
STYLE_REF = "art/items/refs/vitali/street_sweeper.webp"
BG = (16, 18, 26, 255)
# вид, по которому кадр проверяется в пилоте d2: hs+2 - стойка d2, hs+4 - прицел d2
PILOT_USE = {2: ("TWO_STAND", 2), 4: ("TWO_AIM", 2)}

# Конструкция без ориентации (ориентация - только с картинки 1); по describe/what_v2.tsv и карточкам боеприпаса
WHAT = {
    "STR_OLD_SNIPER_RIFLE": (
        "an old bolt-action marksman rifle: a thin dark steel barrel with a small front sight at the muzzle, a long "
        "orange-brown wooden full stock with darker bands running almost to the muzzle, a short dark grey telescopic "
        "sight at the receiver with the bolt handle beside it, a small magazine bulge with a trigger guard under the "
        "receiver, a curved orange-brown wooden butt widening at its end; no detachable magazine",
        ""),
    "STR_SAW": (
        "an autogun squad machine gun: a long barrel with a grey perforated cooling shroud along it and a small light "
        "bar across the shroud, a big dark grey steel receiver, a short part sticking out of the shroud side, a row of "
        "yellow-orange brass cartridges of the ammo belt in the middle of the receiver with a dark feed box beside "
        "it, a pistol grip, a grey stock",
        "- the short part sticking out of the shroud side: keep it exactly in the size and place drawn in image 1 "
        "and image 2, as a plain steel part; do not turn it into a recognizable grip, bipod, handle or sight;\n"),
    "STR_TOMMYGUN": (
        "a Thompson submachine gun: a dark steel barrel with a small front sight and light grey cooling fins, a "
        "brown wooden vertical front grip under the barrel, a straight dark grey box magazine in front of the "
        "trigger, a brown wooden pistol grip, a brown wooden stock; reddish-brown wood and dark steel",
        "- the front grip and the magazine only where image 1 draws them and of the size drawn there; the magazine "
        "is a straight box, not a drum;\n"),
}

PROMPT = """Image 1 is the original low-resolution battle sprite of a weapon held by a soldier (32x40 pixels, enlarged \
with hard pixels; the soldier and the hands are not part of it). It is the ONLY source of the view, the angle, the \
placement in the frame, the length and the muzzle position. Image 2 is the inventory picture of the same weapon in \
another view (32x48 pixels): take from it only the construction, the parts, their materials and colors, not its \
orientation. Image 3 is a style example only: a different weapon that shows the wanted rendering quality. Do not copy \
any part, shape or color of image 3.

Redraw the weapon of image 1 as a high-quality detailed game sprite in the rendering style of image 3: crisp painted \
game art, clean continuous edges, convincing materials, readable small details.

What the weapon is: {what}.

View: {view}. The weapon is seen exactly as in image 1.

Keep exactly from image 1:
- the same angle and direction of the barrel and the same placement in the frame;
- the muzzle and the butt end at the same places, overall width and height of the weapon within 3 percent;
- every part where image 1 draws it and of its size; parts that image 1 does not show are not added;
{special}- the colors of each region as in image 1 and image 2 (only cleaner);
- no hands, no arms, no soldier, no shadow, no ground, no text, no labels.

Avoid: {neg}.

The canvas has the 4:5 proportions of image 1 (32x40). Fill it exactly like image 1 fills its frame. Transparent \
background."""


def sha(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def load_tasks():
    with open(os.path.join(PILOT, "tasks.json"), encoding=ENC) as f:
        return json.load(f)


def key(t):
    return "%s.%d" % (t["type"], t["frame"])


def handob_rgba(frame):
    idx = gm.hob(frame)                 # индексы, 0 прозрачный (R-043)
    rgb = gm.hpal[idx]
    return np.dstack([rgb, np.where(idx == 0, 0, 255)]).astype(np.uint8)


def files_of(k):
    base = os.path.join(OUT, "inputs", k)
    return {"in1": base + ".in1_handob.png", "in2": base + ".in2_bigobs.png", "in3": base + ".in3_style.png",
            "prompt": base + ".prompt.txt"}


def prep(tasks, refreeze):
    if os.path.exists(FREEZE) and not refreeze:
        raise SystemExit("зоны уже заморожены (%s); перезаморозка - только --refreeze и только до генерации" % FREEZE)
    if os.path.isdir(os.path.join(OUT, "raw")) and any(f.endswith(".png") for f in os.listdir(os.path.join(OUT, "raw"))):
        raise SystemExit("в codex/raw уже есть ответы: зоны после генерации не перезамораживаются")
    os.makedirs(os.path.join(OUT, "inputs"), exist_ok=True)
    ip.CARDS = "art/items/weapons100-v1/cards"
    pb = bv.prompt_block("hand_item")
    style = Image.open(STYLE_REF).convert("RGB")
    with open(os.path.join(PILOT, "zones.json"), encoding=ENC) as f:
        zones = json.load(f)
    frozen = {"_note": "Целевые зоны пилота хвата, заморожены ДО генерации (указание Vitali 06.10). zones - зоны "
                       "кистей по классике (x4, до offX/offY, формат zones.json); pose_hands - кожа кистей "
                       "согласованной позы GOV_1 в виде пилота d2, в координатах кадра предмета (база) и x4. После "
                       "генерации фактические места хвата размечаются на HD-кадре и сравниваются с этими; зоны "
                       "вслед за ошибками рисунка не двигаются.",
              "frozen_at": datetime.datetime.now().isoformat(timespec="seconds"),
              "zones_json_sha256": sha(os.path.join(PILOT, "zones.json")),
              "tasks_json_sha256": sha(os.path.join(PILOT, "tasks.json")), "frames": {}}
    for t in tasks:
        k = key(t)
        fs = files_of(k)
        a = handob_rgba(t["frame"])
        im = Image.new("RGBA", (a.shape[1], a.shape[0]), BG)
        im.alpha_composite(Image.fromarray(a, "RGBA"))
        im.convert("RGB").resize((a.shape[1] * 32, a.shape[0] * 32), Image.NEAREST).save(fs["in1"])
        big, _src = ip.load_frame(t["type"], t["bigobs"])
        bg = Image.new("RGBA", big.size, BG)
        bg.alpha_composite(big)
        bg.convert("RGB").resize((big.width * 32, big.height * 32), Image.NEAREST).save(fs["in2"])
        style.save(fs["in3"])
        what, special = WHAT[t["type"]]
        text = PROMPT.format(what=what, view=pb["positive"], special=special, neg=pb["negative"])
        with open(fs["prompt"], "w", encoding=ENC) as f:
            f.write(text)
        case, d = PILOT_USE[t["k"]]
        use = [u for u in t["uses"] if u["case"] == case and u["dir"] == d]
        if len(use) != 1:
            raise SystemExit("%s: вид %s d%d в tasks.json не найден" % (k, case, d))
        hands = {}
        for role, h in use[0]["hands"].items():
            px = h["skin_in_item_frame"]
            xs, ys = [p[0] for p in px], [p[1] for p in px]
            hands[role] = {"arm_frame": h["arm_frame"], "skin": px,
                           "bbox": [min(xs), min(ys), max(xs), max(ys)],
                           "bbox_x4": [min(xs) * 4, min(ys) * 4, max(xs) * 4 + 3, max(ys) * 4 + 3],
                           "dist_geom_classic": h.get("dist_geom"), "dist_visible_classic": h.get("dist_visible")}
        frozen["frames"][k] = {"master": t["master"], "type": t["type"], "frame": t["frame"], "k": t["k"],
                               "pilot_use": {"case": case, "dir": d, "offX": use[0]["offX"], "offY": use[0]["offY"],
                                             "layers": use[0]["layers"]},
                               "bbox_x4": t["bbox_x4"], "size_x4": t["size_x4"],
                               "size_tolerance_px_x4": t["size_tolerance_px_x4"], "muzzle_x4": t["muzzle_x4"],
                               "muzzle_tolerance_px_x4": t["muzzle_tolerance_px_x4"],
                               "zones": zones[t["type"]][str(t["frame"])], "pose_hands": hands,
                               "inputs_sha256": {n: sha(p) for n, p in fs.items()}}
        print(k, "входы готовы:", ", ".join(os.path.basename(p) for p in fs.values()))
    with open(FREEZE, "w", encoding=ENC) as f:
        json.dump(frozen, f, ensure_ascii=False, indent=1)
    print("заморожено:", FREEZE, "кадров", len(frozen["frames"]))


def run(tasks, only):
    import weapons_chatgpt as wc
    with open(FREEZE, encoding=ENC) as f:
        frozen = json.load(f)
    want = set(only.split(","))
    todo = [t for t in tasks if key(t) in want]
    if len(todo) != len(want):
        raise SystemExit("нет заданий: %s" % sorted(want - {key(t) for t in todo}))
    if sha(os.path.join(PILOT, "zones.json")) != frozen["zones_json_sha256"]:
        raise SystemExit("zones.json изменён после заморозки - зоны не двигаются")
    wc.OUT = OUT
    os.makedirs(os.path.join(OUT, "raw"), exist_ok=True)
    for t in todo:
        k = key(t)
        fs = files_of(k)
        bad = [n for n, p in fs.items() if sha(p) != frozen["frames"][k]["inputs_sha256"][n]]
        if bad:
            raise SystemExit("%s: входы изменены после заморозки: %s" % (k, bad))
        with open(fs["prompt"], encoding=ENC) as f:
            prompt = f.read()
        wc.call({"type": k, "master": t["master"]}, [fs["in1"], fs["in2"], fs["in3"]], prompt)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["prep", "run"])
    ap.add_argument("--only", default="", help="run: ключи <тип>.<кадр> через запятую")
    ap.add_argument("--refreeze", action="store_true", help="prep: заморозить заново (только пока нет ответов)")
    a = ap.parse_args()
    os.chdir(ROOT)
    tasks = load_tasks()
    if a.cmd == "prep":
        prep(tasks, a.refreeze)
    else:
        if not a.only:
            raise SystemExit("run: нужен --only")
        run(tasks, a.only)


if __name__ == "__main__":
    main()
