# -*- coding: utf-8 -*-
r"""Тикет XP-000098: фон экрана инвентаря бойца под сетками слотов - три темы (оружейная, оружейная на корабле,
походный брезент), по нескольку зёрен каждая. Кандидаты по выбору Vitali 31.10; в мод НИЧЕГО НЕ СТАВИТ.

Qwen-Image-2.1 (как gen_screens.py), 1792x1120 (16:10, как экран 320x200), затем LANCZOS в 1280x800 - размер
HD-картинок экранов мода (k = 4). Сырые кадры - art/tickets/t098/gen/<тема>_<зерно>.png, кандидаты 1280x800 -
art/tickets/t098/cand/<тема>_<зерно>.png (их и листы делает t098_sheet.py, без модели). Картинка идёт ПОД сетки
слотов, значки предметов, подписи и цифры: плоский фронтальный фон, тёмный, спокойный, без фокуса; приметных
цветных предметов и надписей в промпте нет (R-016, R-570), людей нет.

Круг 1 (31.10): armory, ship, tarp. У tarp брезент лежал на земле целиком - края и петли в кадре; круг 2: tarpc -
крупным планом на весь кадр, края не видны.

    py -3 tools\gpuq.py add --name t098-bg --prio 1 -- tools\hdart\.venv-qwen21\Scripts\python.exe tools\hdart\t098_gen.py render
"""
import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

OUTD = os.path.join(ROOT, "art", "tickets", "t098")
GEN = os.path.join(OUTD, "gen")

STYLE = ("Painted texture illustration in the style of a 1990s PC strategy game, gritty retro science fiction, "
         "confident brushwork. A flat frontal wall-like backdrop that fills the whole picture edge to edge, "
         "evenly dark and calm: low contrast, muted dark brown, soot and dull bronze tones, only mid-dark and dark "
         "values, soft even faint warm glow with a gentle vignette, no focal point, no bright spots, no sharp "
         "highlights, the surface is a quiet background for small items laid on top of it. ")

THEMES = {
    "armory": ("The wall of a pirate hideout armory seen straight on: dark riveted iron wall panels, perforated "
               "metal boards with rows of empty iron hooks and brackets, heavy dark timber shelving beams, "
               "worn flaking paint, scratches and oil grime, everything in deep shadow."),
    "ship": ("The inner bulkhead of a pirate dropship's cargo bay seen straight on: dark riveted steel plates with "
             "rows of rivets, vertical ribs, welded seams and bolted frames, a loose rope cargo net hanging "
             "slack over part of the wall, worn paint, scuffs and oil grime, everything in deep shadow."),
    "tarp": ("A worn canvas field tarpaulin spread flat on the ground seen from directly above: heavy dark olive "
             "brown cloth with soft folds and creases, stitched patches and seams, dark leather straps and rope "
             "loops lying across it, grains of dirt and dust, everything in deep shadow."),
}
# круг 2: брезент крупным планом на весь кадр (в круге 1 он лежал на земле целиком, края и петли были в кадре)
THEMES_R2 = {
    "tarpc": ("A close-up of a worn heavy canvas field tarpaulin seen from directly above that fills the whole "
              "picture edge to edge, no ground, no edges and no corners visible: dark olive brown cloth with soft "
              "folds and creases, a few stitched square patches and long seams, two wide dark leather straps "
              "stitched flat across the cloth, grains of dirt and dust, everything in very deep shadow, low "
              "contrast, dark."),
}
NEG_EXTRA = (", people, person, woman, man, face, hands, skull, weapons, guns, rifles, swords, bottles, lamps, "
             "light fixtures, windows, glowing screens, flames, bright lights, white, blue, green, red, "
             "perspective, vanishing point, scene, room interior, 3d render, depth of field, high contrast")
SEEDS = [9801, 9802, 9803, 9804]
W, H = 1792, 1120


def render(args):
    import gen_screens as gs
    pipe, torch = gs.load_pipe(args.offload)
    os.makedirs(GEN, exist_ok=True)
    themes = dict(THEMES)
    themes.update(THEMES_R2)
    total = len(themes) * len(SEEDS)
    done, t0 = 0, time.time()
    for name, text in themes.items():
        prompt = STYLE + text
        for seed in SEEDS:
            path = os.path.join(GEN, "%s_%d.png" % (name, seed))
            if os.path.exists(path) and not args.force:
                done += 1
                continue
            t1 = time.time()
            img = pipe(prompt=prompt, negative_prompt=gs.NEGATIVE + NEG_EXTRA, true_cfg_scale=args.cfg,
                       width=W, height=H, num_inference_steps=args.steps,
                       generator=torch.Generator("cuda").manual_seed(seed)).images[0]
            img.convert("RGB").save(path)
            done += 1
            print("%s %d за %.0f с, всего %d/%d, осталось ~%.0f мин"
                  % (name, seed, time.time() - t1, done, total,
                     (time.time() - t0) / max(1, done) * (total - done) / 60), flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["render"])
    ap.add_argument("--offload", default="model")
    ap.add_argument("--cfg", type=float, default=4.0)
    ap.add_argument("--steps", type=int, default=40)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    render(a)
