# How the hd mod splits into submods (docs/portal/HD_SUBMODS.md). A HD resource is right in a game only
# where it was drawn over the same classic resource (MULTIMOD 5.4), and equal sources prove that only
# for the game versions compared here (Piratez of the install, X-Com Files 4.2), never for every game:
#   hd_core    - a fixed list, not a finding: TTF fonts; cursors only after the independence check of
#                MULTIMOD 5.4 (ours are drawn from CURSOR.PCK frames, R-040), so they are hd_core?;
#                vanilla equality is only reported (frames_vanilla_equal), it proves nothing for every game;
#   hd_shared? - a candidate for hd_shared with targetGames [piratez, x-com-files]: the Piratez source equals
#                the X-Com Files one frame by frame; FX and outlines match by rule name only, so they
#                are candidates that need a check in that game (an outline also needs the craft sprite);
#   hd_piratez - everything else, including sets where only part of the frames is shared (one pack per set).
# Kinds: sprite sets (engine export OXCE_HD_EXPORT=all of each game), terrain (TERRAIN/<name>.PCK as the
# virtual FS resolves it), UI pictures (image file of that name), FX and craft outlines (rule type names).
#   EXPORTS=<dir with exp_*> py -3.13 hd_split.py   -> docs/research/data/hd_split.tsv and a summary
# Needs xcf_probe.py setup + run vanilla / piratez / xcf; exports are read from EXPORTS (default: the work dir).
import csv, os, re, sys, tempfile
from collections import defaultdict
from pathlib import Path
import numpy as np
from PIL import Image

ROOT = Path("E:/OpenXCom")
sys.path.insert(0, str(ROOT / "tools" / "hdart"))
from xcom_sprites import read_pck

HERE = Path(os.environ.get("XCF_WORK", Path(tempfile.gettempdir()) / "xcf_compat"))
EXPORTS = Path(os.environ.get("EXPORTS", HERE))
GAME = ROOT / "Пиратки" / "Dioxine_XPiratez"
HD = GAME / "user" / "mods" / "hd" / "hd"
UFO = GAME / "UFO"
PIR = GAME / "user" / "mods" / "Piratez"
XCF = HERE / "xcf42" / "XComFiles"
VAN_RUL = GAME / "standard" / "xcom1"
OUT = ROOT / "docs" / "research" / "data" / "hd_split.tsv"
SPECIAL = ("TERRAIN", "UI", "UI_esrgan", "FX", "OUTLINE")
CORE_SETS = {"CURSOR.PCK"}   # hd_core candidates besides the fonts, pending the independence check


def sheet(folder, name):
    p, t = folder / (name + ".png"), folder / (name + ".png.txt")
    if not p.exists() or not t.exists():
        return None
    info = dict(l.split() for l in t.read_text().splitlines() if l.strip())
    n, w, h, c = (int(info[k]) for k in ("frames", "width", "height", "cols"))
    a = np.array(Image.open(p))
    return [a[(i // c) * h:(i // c + 1) * h, (i % c) * w:(i % c + 1) * w] for i in range(n)]


def same(x, i, a):
    return x is not None and i < len(x) and x[i] is not None and np.array_equal(x[i], a)


def frames_of(folder, n):
    nums = {int(m.group(1)) for f in folder.iterdir() if (m := re.fullmatch(r"(\d+)\.png", f.name))}
    return range(n) if (folder / "pack.hdp").exists() or not nums else sorted(nums)


def classify(pir, van, xcf, idx):
    """Frame counts: shared with X-Com Files or Piratez only, plus vanilla-equal as information.
    Frames empty in Piratez are not drawn and not counted."""
    c = defaultdict(int)
    for i in idx:
        if i >= len(pir) or pir[i] is None or not pir[i].any():
            continue
        a = pir[i]
        c["shared" if same(xcf, i, a) else "piratez"] += 1
        c["vanilla"] += same(van, i, a)
    return c


def verdict(c):
    """The narrowest submod that holds the whole set (a pack is one file per set)."""
    if not (c["shared"] or c["piratez"]):
        return "empty"
    if c["piratez"]:
        return "hd_piratez" if not c["shared"] else "hd_piratez (mixed)"
    return "hd_shared?"


def row(kind, name, c, note=""):
    if kind == "set" and name in CORE_SETS:
        sub, note = "hd_core?", "drawn from CURSOR.PCK frames (R-040): hd_core after the independence check"
    else:
        sub = verdict(c)
    if sub == "empty":   # no HD frame number matched an exported one (BASEBITS: numbers past the master offset, R-082)
        sub, note = "hd_piratez", note or "no frame compared"
    return (kind, name, sub, c["shared"], c["piratez"], c["vanilla"], note)


def find_ci(folder, rel):
    p = folder
    for part in rel.split("/"):
        if not p.is_dir():
            return None
        hit = [q for q in p.iterdir() if q.name.lower() == part.lower()]
        if not hit:
            return None
        p = hit[0]
    return p


def terrain(name, *roots):
    for r in roots:
        pck = find_ci(r, "TERRAIN/" + name + ".PCK")
        if pck:
            tab = pck.with_suffix(".TAB") if pck.with_suffix(".TAB").exists() else pck.with_suffix(".tab")
            return [None if f is None else np.array(f, dtype=np.uint8) for f in read_pck(str(pck), str(tab))]
    return None


def image_index(*roots):
    out = {}
    for r in roots:   # later roots win, like a mod over UFO
        for p in r.rglob("*"):
            if p.is_file() and p.suffix.lower() in (".png", ".gif", ".bmp", ".scr", ".spk", ".bdy", ".lbm"):
                out[p.name.lower()] = p
                out[p.stem.lower() + "#stem"] = p
    return out


def image(idx, name):
    p = idx.get(name) or idx.get(name + "#stem")
    if p is None:
        return None
    if p.suffix.lower() in (".png", ".gif", ".bmp"):
        im = Image.open(p)
        return ("px", (np.array(im) if im.mode == "P" else np.array(im.convert("RGBA"))).tobytes(), im.size)
    return ("raw", p.read_bytes(), None)


def rule_types(*roots):
    names = set()
    for r in roots:
        for p in r.rglob("*.rul"):
            names.update(re.findall(r"(?m)^\s*-?\s*(?:type|name): *\"?([A-Za-z0-9_\-]+)", p.read_text(encoding="utf-8", errors="replace")))
    return names


def main():
    rows = []
    ep, ev, ex = EXPORTS / "exp_piratez", EXPORTS / "exp_vanilla", EXPORTS / "exp_xcf"
    for d in sorted(HD.iterdir()):
        if not d.is_dir() or d.name in SPECIAL:
            continue
        pir = sheet(ep, d.name)
        if pir is None:
            rows.append(("set", d.name, "hd_piratez", 0, 0, 0, "not exported by Piratez"))
            continue
        c = classify(pir, sheet(ev, d.name), sheet(ex, d.name), frames_of(d, len(pir)))
        rows.append(row("set", d.name, c))
    for d in sorted((HD / "TERRAIN").iterdir()):
        name = d.name[:-4] if d.name.upper().endswith(".PCK") else d.name
        pir = terrain(name, PIR, UFO)
        if pir is None:
            rows.append(("terrain", name, "hd_piratez", 0, 0, 0, "no source"))
            continue
        c = classify(pir, terrain(name, UFO), terrain(name, XCF, UFO), frames_of(d, len(pir)))
        rows.append(row("terrain", name, c))
    iv, ip, ix = image_index(UFO), image_index(UFO, PIR), image_index(UFO, XCF)
    for f in sorted(HD.joinpath("UI").glob("*.png")):
        name = f.name[:-4].lower()
        a = image(ip, name)
        if a is None:   # no Piratez image of that name: drawn for another mod's picture, see R-033
            rows.append(("ui", f.name[:-4], "hd_piratez", 0, 1, 0, "no Piratez image"))
            continue
        sh, va = a == image(ix, name), a == image(iv, name)
        rows.append(("ui", f.name[:-4], "hd_shared?" if sh else "hd_piratez", int(sh), int(not sh), int(va), ""))
    for f in sorted(HD.joinpath("UI").rglob("*.ttf")):
        rows.append(("font", f.relative_to(HD / "UI").as_posix(), "hd_core", 0, 0, 0, "independent of game data"))
    tv, tp, tx = rule_types(VAN_RUL), rule_types(VAN_RUL, PIR), rule_types(VAN_RUL, XCF)
    keyed = [("fx", l.split()[1]) for l in (HD / "FX" / "weapons.txt").read_text(encoding="utf-8").splitlines()
             if l.strip() and not l.startswith("#") and len(l.split()) > 1]
    keyed += [("outline", l.split()[0]) for l in (HD / "OUTLINE" / "index.txt").read_text(encoding="utf-8").splitlines()
              if l.strip() and not l.startswith("#")]
    for kind, key in sorted(set(keyed)):
        sh = key in tx and key in tp
        note = ("same rule name in X-Com Files: check in the game" + (", and the craft sprite" if kind == "outline" else "")) if sh else ""
        rows.append((kind, key, "hd_shared?" if sh else "hd_piratez", int(sh), int(not sh), int(key in tv), note))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["kind", "name", "submod", "frames_shared_xcf", "frames_piratez_only", "frames_vanilla_equal", "note"])
        w.writerows(rows)
    print("written", OUT)
    for kind in ("font", "set", "terrain", "ui", "fx", "outline"):
        by = defaultdict(lambda: [0, 0, 0, 0])
        for r in rows:
            if r[0] == kind:
                b = by[r[2]]
                b[0] += 1; b[1] += r[3]; b[2] += r[4]; b[3] += r[5]
        print(kind)
        for v, (n, a, b, c) in sorted(by.items()):
            print(f"   {v:20s} {n:5d}   shared with xcf {a:6d}  piratez only {b:6d}  (vanilla-equal {c:6d})")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
