# Which HD frames of the hd mod would X-Com Files draw over a DIFFERENT classic frame.
# HD frames are found by set name and frame number, with no check against the classic frame (MULTIMOD 5.4),
# so a set of the same name with other pictures gets Piratez art.
#   sprite sets  - the engine's own export (OXCE_HD_EXPORT=all) of both games, frame by frame;
#   terrain      - TERRAIN/<name>.PCK as the virtual FS resolves it (mod folder over UFO), read like the engine;
#   UI pictures  - hd/UI/<name>.png against the image file of that name in each game (estimate, see note).
import csv, os, re, sys, tempfile
from pathlib import Path
import numpy as np
from PIL import Image

ROOT = Path("E:/OpenXCom")
sys.path.insert(0, str(ROOT / "tools" / "hdart"))
from xcom_sprites import read_pck

HERE = Path(os.environ.get("XCF_WORK", Path(tempfile.gettempdir()) / "xcf_compat"))   # where xcf_probe.py left its exports
GAME = ROOT / "Пиратки" / "Dioxine_XPiratez"
HD = GAME / "user" / "mods" / "hd" / "hd"
PIR = GAME / "user" / "mods" / "Piratez"
XCF = HERE / "xcf42" / "XComFiles"
UFO = GAME / "UFO"


def sheet(folder, name):
    p = folder / (name + ".png")
    t = folder / (name + ".png.txt")
    if not p.exists() or not t.exists():
        return None
    info = dict(l.split() for l in t.read_text().splitlines() if l.strip())
    n, w, h, c = (int(info[k]) for k in ("frames", "width", "height", "cols"))
    a = np.array(Image.open(p))
    return [a[(i // c) * h:(i // c + 1) * h, (i % c) * w:(i % c + 1) * w] for i in range(n)]


def hd_frames(folder):
    """Frame numbers the HD set has: <n>.png files, or every frame when it is a pack.hdp."""
    nums = {int(m.group(1)) for f in folder.iterdir() if (m := re.fullmatch(r"(\d+)\.png", f.name))}
    return nums, (folder / "pack.hdp").exists()


def compare(a, b, nums, packed):
    same = diff = gone = 0
    idx = range(len(a)) if packed or not nums else sorted(nums)
    for i in idx:
        if i >= len(a) or a[i] is None:
            continue
        if not a[i].any():
            continue   # empty in Piratez: nothing drawn there
        if b is None or i >= len(b) or b[i] is None:
            gone += 1
        elif np.array_equal(a[i], b[i]):
            same += 1
        else:
            diff += 1
    return same, diff, gone


def find_ci(folder, rel):
    p = folder
    for part in rel.split("/"):
        if not p.is_dir():
            return None
        hit = [c for c in p.iterdir() if c.name.lower() == part.lower()]
        if not hit:
            return None
        p = hit[0]
    return p


def terrain(name, mod):
    pck = find_ci(mod, "TERRAIN/" + name + ".PCK") or find_ci(UFO, "TERRAIN/" + name + ".PCK")
    if not pck:
        return None, None
    tab = pck.with_suffix(".TAB")
    if not tab.exists():
        tab = pck.with_suffix(".tab")
    frames = read_pck(str(pck), str(tab))
    return [None if f is None else np.array(f, dtype=np.uint8) for f in frames], pck


def main():
    out = []
    ea, eb = HERE / "exp_piratez", HERE / "exp_xcf"
    xcf_rul = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in (XCF / "Ruleset").rglob("*.rul")).lower()
    for d in sorted(HD.iterdir()):
        if not d.is_dir() or d.name in ("TERRAIN", "UI", "UI_esrgan", "FX", "OUTLINE", "Pathfinding"):
            continue
        name = d.name
        nums, packed = hd_frames(d)
        a, b = sheet(ea, name), sheet(eb, name)
        if a is None:
            out.append(("set", name, "not in Piratez export", 0, 0, 0))
            continue
        if b is None:
            out.append(("set", name, "absent in XCF", 0, 0, 0))
            continue
        s, df, g = compare(a, b, nums, packed)
        out.append(("set", name, "same" if df == 0 and g == 0 else "DIFFERS", s, df, g))
    for d in sorted((HD / "TERRAIN").iterdir()):
        name = d.name[:-4] if d.name.upper().endswith(".PCK") else d.name
        nums, packed = hd_frames(d)
        a, pa = terrain(name, PIR)
        b, pb = terrain(name, XCF)
        used = re.search(r"\b" + re.escape(name.lower()) + r"\b", xcf_rul) is not None
        if a is None:
            out.append(("terrain", name, "no Piratez source", 0, 0, 0))
            continue
        if b is None or not used:
            out.append(("terrain", name, "not used by XCF", 0, 0, 0))
            continue
        s, df, g = compare(a, b, nums, packed)
        out.append(("terrain", name, ("same" if df == 0 and g == 0 else "DIFFERS") + (" (UFO file in both)" if pa == pb else ""), s, df, g))
    with open(HERE / "xcf_hd_compare.tsv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["kind", "set", "verdict", "frames_same", "frames_differ", "frames_missing"])
        w.writerows(out)
    for kind in ("set", "terrain"):
        rows = [r for r in out if r[0] == kind]
        by = {}
        for r in rows:
            v = r[2].split(" (")[0]
            by.setdefault(v, [0, 0, 0, 0])
            by[v][0] += 1
            by[v][1] += r[3]; by[v][2] += r[4]; by[v][3] += r[5]
        print(kind, len(rows), "HD sets")
        for v, (n, s, df, g) in sorted(by.items()):
            print(f"   {v:24s} sets {n:4d}   frames same {s:6d} differ {df:6d} missing {g:5d}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
