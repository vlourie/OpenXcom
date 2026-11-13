"""DEMONESS и DOGE (09.11): входы FLUX.3 Klein - классика в своей рамке, xBRZ x4 и LANCZOS до x8, на подложке куклы.
Выход E:/tmp/doll_ingame/dd/init_<имя>.png и classic_<имя>.png (крупно без сглаживания, для листов)."""
import os
import sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, r"E:\OpenXCom\tools\hdart")
from PIL import Image
import doll_b2_render as db
import doll_photo_pilot as dp
import wall_section as ws

OUT = r"E:\tmp\doll_ingame\dd"
os.makedirs(OUT, exist_ok=True)
Z = 8
# рамка на холсте 320x200: DEMONESS x 46..109 y 18..168, DOGE x 54..95 y 58..142 (с полем; стороны кратны 2 - x8 кратно 16)
JOBS = {
    "dem_light": ((36, 10, 120, 176), ["DEMONESS__2__LIGHT_NUDE"]),
    "dem_dark": ((36, 10, 120, 176), ["DEMONESS__2__DARK_NUDE"]),
    "dog": ((44, 50, 108, 150), ["DOGE__2__DOG_M0"]),
    "dog_shield": ((44, 50, 108, 150), ["DOGE__2__DOG_M0", "DOGE__3__DOGESHIELD_RED"]),
    "dog_tac": ((44, 50, 108, 150), ["DOGE__2__DOG_M0", "DOGE__3__DOGETAC"]),
}
F, PAL = db.sprite_files(), db.game_palette()
for name, (crop, layers) in JOBS.items():
    img = dp.classic(F, PAL, layers)
    part = img.crop(crop)
    up = ws.xbrz(part, 4).resize((part.width * Z, part.height * Z), Image.LANCZOS)
    bg = Image.new("RGBA", up.size, dp.PANEL + (255,))
    bg.alpha_composite(up)
    bg.convert("RGB").save(os.path.join(OUT, "init_%s.png" % name))
    cl = Image.new("RGBA", part.size, dp.PANEL + (255,))
    cl.alpha_composite(part)
    cl.resize(up.size, Image.NEAREST).convert("RGB").save(os.path.join(OUT, "classic_%s.png" % name))
    print(name, crop, up.size)
print("подложка", dp.PANEL)
