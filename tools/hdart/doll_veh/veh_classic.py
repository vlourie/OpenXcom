"""Техника (куклы одной картинкой): классика в RGBA палитрой игры, x1 и лист x4. Выход E:/tmp/doll_ingame/veh/classic_<имя>.png, sheet.jpg."""
import os
import sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, r"E:\OpenXCom\tools\hdart")
import numpy as np
from PIL import Image, ImageDraw
import doll_b2_render as db
MOD = r"E:\OpenXCom\Пиратки\Dioxine_XPiratez\user\mods\Piratez"
OUT = r"E:\tmp\doll_ingame\veh"
PICS = {"MAN_65.SPK": "Hovertank_Armor.gif", "MAN_75.SPK": "Armored_Car_Armor.png", "MAN_89.SPK": "Tank_P_ACannon.png",
        "MAN_90.SPK": "Tank_P_BCannon.png", "MAN_93.SPK": "Tank_P_LasCannon.png",
        "XTurretInventoryImage": "XTurret_01_Inv.png", "XTurretLaserInventoryImage": "XTurret_02_Inv.png",
        "XTurretGaussInventoryImage": "XTurret_03_Inv.gif", "XTurretPlasmaInventoryImage": "XTurret_05_Inv.png",
        "XTurretChaingunInventoryImage": "XTurret_06_Inv.gif", "XTurretPlasmaGatlingInventoryImage": "XTurret_07_Inv.gif",
        "TurretInventoryImage": "Turret_Armor.png", "TurretRedInventoryImage": "Turret_Armor_Red.png"}
PAL = db.game_palette()
tiles = []
for name, fn in (PICS.items() if __name__ == "__main__" else ()):
    im = Image.open(os.path.join(MOD, "Resources", "Body_X", fn))
    if getattr(im, "n_frames", 1) > 1:
        im.seek(0)
    print(name, fn, im.mode, im.size)
    idx = np.asarray(im.convert("P") if im.mode != "P" else im)
    rgba = db.to_rgba(idx, PAL)
    Image.fromarray(rgba).save(os.path.join(OUT, "classic_%s.png" % name))
    ys, xs = np.nonzero(rgba[..., 3])
    print("   рамка", xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)
    t = Image.new("RGB", (rgba.shape[1], rgba.shape[0]), (110, 110, 118))
    t.paste(Image.fromarray(rgba), (0, 0), Image.fromarray(rgba))
    t = t.crop((10, 40, 160, 155)).resize((600, 460), Image.NEAREST)
    ImageDraw.Draw(t).text((4, 4), name, fill=(255, 220, 90))
    tiles.append(t)
sheet = Image.new("RGB", (600 * 5, 460 * 3), (0, 0, 0))
for i, t in enumerate(tiles):
    sheet.paste(t, ((i % 5) * 600, (i // 5) * 460))
sheet.save(os.path.join(OUT, "sheet.jpg"), quality=88)
