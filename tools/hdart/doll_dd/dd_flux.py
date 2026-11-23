"""DEMONESS и DOGE (09.11): FLUX.3 Klein перерисовывает классику (init_<имя>.png из dd_init.py), поза и место те же.
Аргументы: имена заданий через запятую (dem_light, dog, ...), сиды через запятую. Запуск через gpuq окружением diffusers.
Выход E:/tmp/doll_ingame/dd/images/<имя>_<сид>.png."""
import json
import os
import sys

OUT = r"E:\tmp\doll_ingame\dd"
SRC = os.environ.get("DD_SRC", "")                  # другой вход (правка готового HD), иначе init_<имя>.png
REPAINT = ("Repaint this blurry low-resolution game sprite as a sharp, detailed, realistic painting in the style of a dark "
           "fantasy strategy game. Keep the composition exactly: the figure in the same place, the same size, the same pose "
           "and the same outline, every limb where it is now. The plain flat grey panel around the figure stays exactly as it "
           "is: no floor, no shadow, no background objects. Soft light from the upper left, a thin red rim light on the right "
           "edges as in the input. Crisp and sharp, no text. ")
DEM = ("She is a chort, a shapeshifting female earth demon: an adult woman about 30 years old, tall and athletic, seen from the "
       "front, standing with both arms raised and bent behind her head, elbows up. Two short curved black horns on her head. "
       "Glowing violet eyes, a calm cruel face with high cheekbones. Smooth pale pinkish-tan skin with dark purple shading in "
       "the hollows, a toned ribbed abdomen with sharply defined muscles and dark vein-like cracks. A natural full bust. Below "
       "the hips she has the legs of a goat: thick brown fur on the thighs and shins, digitigrade legs with backward bent "
       "ankles and black cloven hooves, one leg crossed in front of the other as in the input. She wears only minimal black "
       "underwear: two small flat round black pasties, one on each nipple, and a narrow black thong. ")
DOG = ("A big muscular guard dog, a black and tan rottweiler-like hound with short glossy fur, standing upright on its hind "
       "legs like a person, seen from the front, its head turned to the left of the picture and tilted, the jaws wide open "
       "showing sharp white teeth, a red tongue and red mouth. The face and back are black, the chest, legs and paws are tan. "
       "Both front paws are raised in front of the chest with the toes and dark claws visible, the hind legs stand straight "
       "with the paws on the ground, one ear pointed up. ")
KEEP = ("Keep everything else exactly as it is: the same pose, outline, size and place, the same face, horns, muscles and "
        "details, the same brown goat fur on the legs and the black hooves, the same black thong, the same grey panel and light. "
        "Crisp and sharp, no text.")
DARK = ("Edit this picture: change only the colour of her bare skin to a very dark blue-black, deep indigo navy with a cold "
        "violet sheen on the highlights and black in the shadows, like polished obsidian, on the face, neck, arms, chest and "
        "belly. Her eyes glow bright green instead of violet. " + KEEP)
DKEEP = ("Keep the dog of image 1 exactly as it is: the same pose, outline, size and place, the same open jaws, fur colours "
         "and paws, the same grey panel and light. Detailed realistic painting, crisp and sharp, no text.")
SHIELD = ("Edit image 1: put on the dog the armour shown in image 2, in the same place as in image 2: a dark grey steel chest "
          "plate on its chest between the raised front paws, held by a grey strap around the neck, with a row of small glowing "
          "red light bars at the top and a round glowing red lens in the middle, orange trim on the right edge. " + DKEEP)
TAC = ("Edit image 1: put on the dog the armour shown in image 2, in the same place as in image 2: a green padded tactical "
       "vest of rough fabric covering its chest and belly between the raised front paws, and a green fabric hood of the same "
       "cloth over the top of its head and the back of its neck, the ear sticking out through the hood. "
       + ("The hood is large and clearly visible: it covers the whole top of the head from the forehead just above the eyes, "
          "and hangs down the left side of the head behind the jaw to the shoulder, exactly like the green area in image 2. "
          if os.environ.get("DD_HOOD") else "") + DKEEP)
P = {"dem_light": REPAINT + DEM, "dog": REPAINT + DOG, "dem_dark": DARK, "dog_shield": SHIELD, "dog_tac": TAC}
REF = {"dog_shield": os.path.join(OUT, "init_dog_shield.png"), "dog_tac": os.path.join(OUT, "init_dog_tac.png")}
names = sys.argv[1].split(",")
seeds = [int(s) for s in sys.argv[2].split(",")] if len(sys.argv) > 2 else [1, 2, 3]
from PIL import Image
jobs = {}
for name in names:
    src = SRC or os.path.join(OUT, "init_%s.png" % name)
    w, h = Image.open(src).size
    for seed in seeds:
        item = "%s_%d" % (name, seed) if not SRC else "%s_%s_%d" % (name, os.path.splitext(os.path.basename(SRC))[0], seed)
        if not os.path.exists(os.path.join(OUT, "images", item + ".png")):
            jobs[item] = {"task": "dd", "prompt": P[name], "caption": item, "seed": seed, "width": w, "height": h,
                          "image": [src] + ([REF[name]] if name in REF else [])}
spec = {"id": "dd", "model": "flux3", "preset": "bf16", "mode": "both", "variant": "bf16",
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
