"""LAMIA (09.11): FLUX.3 Klein. Аргументы: задание (body | skin_<группа> | head_<внешность>), сиды через запятую.
body - перерисовка классики F0 (init_F0.png); skin_* и head_* - правка выбранной основы (LM_BASE), head_* с эталоном
classic init_<внешность>.png вторым входом. Головы сиды 1-4 - прежний промпт «smooth natural face» (брак R-869),
с сида 11 - промпт по педии (LAMIA, EYES). Запуск через gpuq окружением diffusers. Выход E:/tmp/doll_ingame/lm/images/<задание>_<сид>.png."""
import json
import os
import sys

OUT = r"E:\tmp\doll_ingame\lm"
BASE = os.environ.get("LM_BASE", "")
REPAINT = ("Repaint this blurry low-resolution game sprite as a sharp, detailed, realistic painting in the style of a dark "
           "fantasy strategy game. Keep the composition exactly: the figure in the same place, the same size, the same pose "
           "and the same outline, every limb where it is now. The plain flat grey panel around the figure stays exactly as it "
           "is: no floor, no shadow, no background objects. Soft light from the upper left. Crisp and sharp, no text. ")
WHO = ("She is a lamia, a snake-woman: an adult woman about 30 years old with a powerful muscular upper body, broad strong "
       "shoulders, big muscular arms hanging down at her sides with the hands in loose fists, a natural full bust and a ribbed "
       "abdomen with defined muscles, seen from the front. Below the hips her body becomes a thick snake tail: smooth orange "
       "skin with small fine scales on the sides and back, wide pale pinkish-cream belly plates in horizontal bands down the "
       "front, the tail curling to the right of the picture and ending in a long pointed tip. Smooth orange skin with warm "
       "darker shading. Short curly golden-blond hair and a broad strong face. She wears only two small flat round black "
       "pasties, one on each nipple, nothing else. ")
KEEP = ("Keep everything else exactly as it is: the same pose, outline, size and place, the same muscles, belly plates and "
        "tail, the same grey panel and light. Crisp and sharp, no text.")
# группы кожи по классике (lm_skin.py): оранжевая - сама основа; цель rgb классики в скобках
SKIN = {"green": "a bright yellowish grass green (like rgb 134,191,87) with darker green shading",           # F1 F5
        "pink": "a light rosy-peach human skin tone (like rgb 223,171,146) with soft rosy shading",          # F2 F4
        "beige": "a light warm beige human skin tone (like rgb 208,175,145) with soft tan shading",          # F3 M7
        "brown": "an olive golden-brown skin tone like tanned leather (like rgb 155,119,68) with darker brown shading"}  # F6 F7 M2 M3 M6

# головы по классике (лист ch_all.jpg, 09.11); глаза - EYES (лист eyes.png: в классике глаз сплошной цветной, без белка)
HEAD = {"F0": "short curly golden-blond hair, warm orange skin, full red lips.",
        "F1": "replace her golden curls completely: her hair is a round puffy cloud of short frizzy dull ash-brown hair, greyish "
              "light brown like dry straw in shadow, not golden and not yellow, wider than her head on both sides and ending "
              "at the jaw, not hanging down to the shoulders; her face and neck are the same bright grass green as her "
              "body, not grey; a thin red forked snake tongue sticking out of the corner of her mouth.",
        "F2": "a chin-length bob split in two colours: the left half of the hair silver-grey, the right half jet black, "
              "light rosy skin.",
        "F3": "long straight bright violet-pink hair with a fringe, hanging down on both sides to the shoulders, light beige "
              "skin, red lips.",
        "F4": "messy straggly silver-grey hair parted in the middle, hanging straight down past the cheeks to the shoulders "
              "on both sides, light rosy skin.",
        "F5": "long white hair with a lilac tint and a thin red headband across the forehead, green skin, red lips.",
        "F6": "black hair gathered in a tall knot on top of the head with blue beads, thin black braids with blue beads hanging "
              "by the cheeks, golden-brown skin, red lips.",
        "F7": "a wild spiky mane of hair, crimson red on the right side and dark blue on the left side, golden-brown skin, "
              "two small white fangs.",
        "M0": "short straight pale straw-blond hair, warm orange skin.",
        "M1": "short dark green hair swept to the right of the picture with a teal streak at the tip, warm orange skin.",
        "M2": "very short cropped brown hair, golden-brown skin.",
        "M3": "short black hair with spiky dark blue tips on top, golden-brown skin.",
        "M4": "dark crimson-magenta hair over the whole top of the head, falling down the right side of the picture to "
              "the jaw, no shaved part; warm orange skin.",
        "M5": "short swept dark grey-black hair, warm orange skin.",
        "M6": "replace her golden curls completely: short jet-black curly hair with a dark navy-blue sheen, not grey, not "
              "silver, close to the head; golden-brown skin, red lips.",
        "M7": "short black hair with a small top-knot bun, pale beige skin."}
EYES = {"F0": "bright lemon-yellow", "F1": "bright yellow-green", "F2": "bright pale blue", "F3": "glossy black",
        "F4": "yellow-green", "F5": "bright cyan-blue", "F6": "glossy black", "F7": "bright green", "M0": "bright green",
        "M1": "glowing magenta-pink", "M2": "bright blue", "M3": "dark reddish-brown", "M4": "bright green",
        "M5": "bright green", "M6": "bright green", "M7": "bright lemon-yellow"}
# педия (R-869): ламии - гибрид змеелюдей, тупые, сильные и злобные дикарки, укус, кислота; лица грубые, глаза змеиные
LAMIA = ("She is a lamia, a savage snake-woman mutant, a hybrid bred from the reptilian Snakemen: strong, stubborn and "
         "bad-tempered. She is unmistakably a woman, an adult female with a woman's face: full lips, a feminine chin and "
         "cheeks, no beard, no stubble; but the face is coarse and heavy, with wide cheekbones, a wide nose, a strong jaw and "
         "a thick short neck merging into the massive shoulder muscles. A sullen grim scowl and a hard cold stare, dark smoky "
         "shadows painted around the eyes like war paint. Her eyes are snake eyes: the whole eye is one solid %s colour with "
         "no white at all and a thin dark vertical slit pupil. Not a pretty fashion model, not a man. ")


def prompt(task):
    if task == "body":
        return REPAINT + WHO
    if task.startswith("skin_"):
        return ("Edit this picture: change only the colour of her skin on the face, neck, arms, chest, belly and on the scaled "
                "sides and back of the snake tail to %s. The pale belly plates down the front of the tail stay pale cream. %s"
                % (SKIN[task[5:]], KEEP))
    if task.startswith("head_"):
        lk = task[5:]
        return ("Edit image 1: give her the head, face and hair of the lamia in image 2: %s %sThe same hairstyle, hair "
                "colour and length, eye colour and skin colour of the face as in image 2, the head and hair in the same place "
                "and of the same size as in image 2. Detailed realistic painting of the face, not blocky, not pixelated. Keep "
                "the body of image 1 below the neck exactly as it is, the same size and place. Crisp and sharp, no text."
                % (HEAD[lk], LAMIA % EYES[lk]))
    raise SystemExit("нет задания " + task)


task = sys.argv[1]
seeds = [int(s) for s in sys.argv[2].split(",")] if len(sys.argv) > 2 else [1, 2, 3]
from PIL import Image
src = os.path.join(OUT, "init_F0.png") if task == "body" else BASE
w, h = Image.open(src).size
jobs = {}
for seed in seeds:
    item = "%s_%d" % (task, seed) if task == "body" else "%s_%s_%d" % (task, os.path.splitext(os.path.basename(BASE))[0], seed)
    if not os.path.exists(os.path.join(OUT, "images", item + ".png")):
        img = [src] + ([os.path.join(OUT, "init_%s.png" % task[5:])] if task.startswith("head_") else [])
        jobs[item] = {"task": "lm", "prompt": prompt(task), "caption": item, "seed": seed, "width": w, "height": h, "image": img}
spec = {"id": "lm", "model": "flux3", "preset": "bf16", "mode": "both", "variant": "bf16",
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
