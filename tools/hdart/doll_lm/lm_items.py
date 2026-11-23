"""LAMIA (09.11): вещи правкой FLUX.3 Klein. Вход 1 - готовая HD-кукла F0 (layers/full_F0.png), вход 2 - классика брони
init_arm_<броня>.png. Аргументы: брони через запятую (ключи ARM), сиды. Выход images/arm_<ключ>_<сид>.png.
Щиты - отдельными правками (броня с щитом закрывает доспех под щитом; доспех берём из правки без щита)."""
import json
import os
import sys

OUT = r"E:\tmp\doll_ingame\lm"
BASE = os.path.join(OUT, "layers", "full_F0.png")
KEEP = ("Keep the lamia of image 1 exactly as it is wherever the armour does not cover her: the same pose, outline, size "
        "and place, the same face, skin colour, muscles, pale belly plates and snake tail, the same grey panel and light. "
        "Detailed realistic painting, crisp and sharp, no text.")
PUT = "Edit image 1: put on her the armour shown in image 2, in the same place and of the same shape as in image 2: "
SHIELD = "Edit image 1: give her the shield shown in image 2, in the same place and of the same size as in image 2: "
ARM = {
    "BOSS": PUT + ("a black spiked plate armour of dark gunmetal steel: a cuirass with a high collar on her chest and "
                   "shoulders, short sharp spikes on the shoulders and a small red star on the chest, black armoured sleeves "
                   "on the arms down to the wrists, and a long tapering column of black segmented plates down the front of "
                   "the snake tail to the bottom. Her hands stay bare. Small black goggles with grey lenses over her eyes. "),
    "BRONZE": PUT + ("a golden bronze cuirass of plates with dark bronze shoulder guards, a brown leather strap across the "
                     "chest, a bronze belt with a round buckle and a hanging crimson loincloth with golden trim at the front "
                     "of the tail; a bronze helmet with a nose guard covering her whole head and hair, a dark red cloth over "
                     "the lower face; short golden bronze bracers on both forearms; a long dark crimson cape hanging behind "
                     "her back, its edges visible at the sides. "),
    "NUDE_S": SHIELD + ("a round blue wooden shield with a bronze rim, small red rivets and a round golden boss in the "
                        "middle, held in front of her. "),
    "CHAIN_MAIL": PUT + ("a long dark grey steel chain-mail hauberk covering her shoulders, chest, belly and the front of "
                         "the snake tail down to the bottom and along the tail, grey steel shoulder plates, dark purple-black "
                         "leather sleeves and gloves on the arms, a belt with small silver skull studs; a dark steel helmet "
                         "with a grim skull-shaped face mask covering her whole head and hair, a small red crest on top. "),
    "CHAIN_MAIL_A": SHIELD + ("a big black kite shield shaped like a horned demon face with two small glowing red eyes, "
                              "held in front of her body. She also wears the dark chain mail and skull helmet of image 2. "),
    "SCALE_MAIL": PUT + ("a short-sleeved shirt of dark brown iron scale mail with small rounded overlapping scales, covering "
                         "her shoulders, chest and belly down to the hips, with a high scale collar that covers her neck and "
                         "her face from the nose down; her eyes, forehead and curly hair stay visible, her arms stay bare. "),
    "SCALE_MAIL_A": SHIELD + ("a small round shield of pale bone-white chitin with a dark rim, held low on the RIGHT side "
                              "of the picture, over her left hand and the top of the snake tail, exactly where the pale "
                              "round shield is in image 2; nothing on the left side of the picture. She also wears the dark "
                              "scale mail of image 2. "),
    "HOPLITE": PUT + ("an ancient Greek hoplite outfit: a bronze Corinthian helmet with a silver face guard and cheek pieces "
                      "covering her whole head and hair, a black crest on top; a dark red cape hanging behind her back and "
                      "fastened over her shoulders at the front of the neck with a round silver brooch; a bronze guard on "
                      "her belly; a brown leather skirt of hanging strips at the hips; a big round white shield with red "
                      "rays, a red rim and a round red boss, held in front of her. Her chest stays bare with the two small "
                      "black pasties. "),
    "STRAPS": PUT + ("wide brown leather harness straps crossing her chest diagonally from her left shoulder, fastened "
                     "with a round steel ring in the middle, and a brown leather backpack on her back, its edges visible "
                     "beside her waist. "),
    "TAC_SUIT": PUT + ("a dark green armoured tactical suit: big rounded green shoulder armour, green armour plates on the "
                       "chest and belly, the same green segmented armour covering the whole snake tail down to its tip with "
                       "dark brown joints, green armoured sleeves; a green helmet with a face mask covering her whole head, "
                       "only her eyes visible. "),
}
SRC = {"NUDE_S": "STR_LAMIA_NUDE_S_UC"}
names = sys.argv[1].split(",") if len(sys.argv) > 1 and sys.argv[1] != "all" else list(ARM)
seeds = [int(s) for s in sys.argv[2].split(",")] if len(sys.argv) > 2 else [1, 2]
from PIL import Image
w, h = Image.open(BASE).size
jobs = {}
for n in names:
    ref = os.path.join(OUT, "init_arm_%s.png" % SRC.get(n, "STR_LAMIA_%s_UC" % n))
    for seed in seeds:
        item = "arm_%s_%d" % (n, seed)
        if not os.path.exists(os.path.join(OUT, "images", item + ".png")):
            jobs[item] = {"task": "lm", "prompt": ARM[n] + KEEP, "caption": item, "seed": seed, "width": w, "height": h,
                          "image": [BASE, ref]}
spec = {"id": "lm", "model": "flux3", "preset": "bf16", "mode": "both", "variant": "bf16",
        "captions": os.path.join(OUT, "captions.json"), "jobs": jobs, "offload_mode": "auto"}
with open(os.path.join(OUT, "spec_items.json"), "w", encoding="utf-8") as f:
    json.dump(spec, f, ensure_ascii=False, indent=1)
print("заданий", len(jobs), flush=True)
if jobs:
    os.environ["MB_SPEC"] = os.path.join(OUT, "spec_items.json")
    os.environ["MB_OUT"] = OUT
    sys.path.insert(0, r"F:\AIStudio\models\benchmarks\2026-11-06\tools\workers")
    import flux3_worker
    flux3_worker.main()
print("готово", len(jobs), flush=True)
