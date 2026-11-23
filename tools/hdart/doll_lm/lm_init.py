"""LAMIA (09.11): входы FLUX.3 Klein - классика в рамке, xBRZ x4 и LANCZOS до x8, на подложке куклы.
16 голых внешностей (тело с головой в одном слое) - init_<внешность>.png и classic_<внешность>.png (крупно без сглаживания)."""
import os
import sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, r"E:\OpenXCom\tools\hdart")
from PIL import Image
import doll_b2_render as db
import doll_photo_pilot as dp
import wall_section as ws

OUT = r"E:\tmp\doll_ingame\lm"
os.makedirs(OUT, exist_ok=True)
Z = 8
CROP = (42, 40, 134, 146)                       # все слои LAMIA x 44..132 y 44..143; стороны чётные - x8 кратно 16
LOOKS = ["F%d" % i for i in range(8)] + ["M%d" % i for i in range(8)]
F, PAL = db.sprite_files(), db.game_palette()
for look in LOOKS:
    img = dp.classic(F, PAL, ["LAMIA__2__%s_NUDE" % look])
    part = img.crop(CROP)
    up = ws.xbrz(part, 4).resize((part.width * Z, part.height * Z), Image.LANCZOS)
    bg = Image.new("RGBA", up.size, dp.PANEL + (255,))
    bg.alpha_composite(up)
    bg.convert("RGB").save(os.path.join(OUT, "init_%s.png" % look))
    cl = Image.new("RGBA", part.size, dp.PANEL + (255,))
    cl.alpha_composite(part)
    cl.resize(up.size, Image.NEAREST).convert("RGB").save(os.path.join(OUT, "classic_%s.png" % look))
print("внешностей", len(LOOKS), "размер", up.size)
