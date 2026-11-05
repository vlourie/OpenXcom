# -*- coding: utf-8 -*-
r"""Перевырезка куста JUNGLEBITS:3 из сохранённых ответов модели (art/tickets/hb509/gen/raw/bush3_<зерно>.png) без видеокарты:
силуэт - по классике (grow пикселей классики шире), края спрямлены xBRZ (cut_out), кайма подложки снята.
    py -3.13 p509_bush3_cut.py <grow> <зерно>...   -> art/tickets/hb509/bush3/g<grow>/<зерно>/JUNGLEBITS_3.png"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"E:\OpenXCom\tools\hdart")
os.chdir(r"E:\OpenXCom")
import numpy as np
from PIL import Image
import map_mockup as mm
import probe_object as po
import p509_defringe as df

PAD, SOFT, TONE = 3, 40, 0.7


def cut(seed, grow):
    w = mm.World()
    full = w.sprite("junglebits", 3, None).convert("RGBA")
    bb = full.split()[3].getbbox()
    box = (max(0, bb[0] - PAD), max(0, bb[1] - PAD), min(full.width, bb[2] + PAD), min(full.height, bb[3] + PAD))
    frame = full.crop(box)
    hd = Image.open(os.path.join("art", "tickets", "hb509", "gen", "raw", "bush3_%d.png" % seed)).convert("RGB")
    part = po.match_tone(po.cut_out(hd, frame, grow, SOFT), frame, TONE)
    out = Image.new("RGBA", (full.width * 4, full.height * 4), (0, 0, 0, 0))
    out.paste(part, (box[0] * 4, box[1] * 4))
    return df.defringe(out)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    grow = int(sys.argv[1])
    for s in sys.argv[2:]:
        d = os.path.join("art", "tickets", "hb509", "bush3", "g%d" % grow, s)
        os.makedirs(d, exist_ok=True)
        cut(int(s), grow).save(os.path.join(d, "JUNGLEBITS_3.png"))
        print(d)
