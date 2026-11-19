# hd/UI/<name>.png is the HD picture of the image <name> of ANY mod (R-033). Which of them X-Com Files has,
# and whether its image is the same picture as the one in Piratez the HD art was made from.
# Estimate by files: an image file whose name (with or without extension) is <name>, in the mod over UFO.
import os, sys, tempfile
from pathlib import Path
import numpy as np
from PIL import Image

ROOT = Path("E:/OpenXCom")
HERE = Path(os.environ.get("XCF_WORK", Path(tempfile.gettempdir()) / "xcf_compat"))   # the unpacked X-Com Files (xcf_probe.py setup)
GAME = ROOT / "Пиратки" / "Dioxine_XPiratez"
UI = GAME / "user" / "mods" / "hd" / "hd" / "UI"
EXT = {".png", ".gif", ".bmp", ".scr", ".spk", ".bdy", ".lbm", ".pck", ".dat"}


def index(*roots):
    out = {}
    for r in roots:   # later roots win, like a mod over UFO
        for p in r.rglob("*"):
            if p.is_file() and p.suffix.lower() in EXT:
                out[p.name.lower()] = p
                out.setdefault(p.stem.lower(), p) if False else None
                out[p.stem.lower() + "#stem"] = p
    return out


def find(idx, name):
    return idx.get(name) or idx.get(name + "#stem")


def pixels(p):
    if p.suffix.lower() not in (".png", ".gif", ".bmp"):
        return p.read_bytes()   # SCR/SPK and the like: compare the bytes
    im = Image.open(p)
    return np.array(im) if im.mode == "P" else np.array(im.convert("RGBA"))


def main():
    ufo = GAME / "UFO"
    pir = index(ufo, GAME / "user" / "mods" / "Piratez")
    xcf = index(ufo, HERE / "xcf42" / "XComFiles", HERE / "xcf42" / "DarkGeoscape")
    rows = []
    for f in sorted(UI.glob("*.png")):
        name = f.name[:-4].lower()
        b = find(xcf, name)
        if b is None:
            continue
        a = find(pir, name)
        if a is None:
            verdict = "XCF only (HD made for another image)"
        elif a == b:
            verdict = "same file (UFO)"
        else:
            pa, pb = pixels(a), pixels(b)
            if isinstance(pa, np.ndarray) and isinstance(pb, np.ndarray):
                same = pa.shape == pb.shape and np.array_equal(pa, pb)
            elif isinstance(pa, bytes) and isinstance(pb, bytes):
                same = pa == pb
            else:
                same = False   # one is a PNG, the other an SCR: other picture data
            verdict = "same picture" if same else "DIFFERENT picture"
        rows.append((name, verdict, str(b.relative_to(b.parents[2]) if len(b.parents) > 2 else b)))
    for r in rows:
        print("\t".join(r))
    from collections import Counter
    print(Counter(v for _, v, _ in rows))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
