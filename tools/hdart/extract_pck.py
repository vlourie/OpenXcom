#!/usr/bin/env python3
"""
Extracts X-COM sprite sets to PNG sheets for the HD art pipeline.

    py -3 extract_pck.py --data <UFO folder> --out <sheets folder> [--scale 4] [--columns 8] [--margin 4]
                         [--sets TERRAIN/CULTIVAT.PCK UNITS/XCOM_0.PCK ...] [--all]

For every set it writes into <out>/<SET NAME>/:
  original.png   - the frames on a grid, indexed PNG with the battlescape palette (index 0 = transparent)
  original_x<k>.png - the same, RGBA, nearest-scaled k times: the input of the painting step
  mask_x<k>.png  - the coverage of the original (white where a pixel is drawn), scaled k times
  layout.json    - the grid (frame size, count, columns, margin) build_pack.py cuts the HD sheet with

Sheets keep a margin around every frame so that a painted frame never bleeds into its neighbour.
"""
import argparse
import json
import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xcom_sprites as xs  # noqa: E402

def find_ci(folder, name):
    """Файл в папке без учёта регистра: у модов имена наборов пишутся и так, и так."""
    p = os.path.join(folder, name)
    if os.path.exists(p):
        return p
    if os.path.isdir(folder):
        for f in os.listdir(folder):
            if f.upper() == name.upper():
                return os.path.join(folder, f)
    return ""


def ground_flags(frames, types, walkable, raised, fw, fh):
    """Какие кадры набора — сплошное поле, а какие стоят на своём ромбе пола.

    Правило одно на весь конвейер: им пользуется и разбор наборов, и приёмка (review_floors),
    иначе поле у них разъедется и приёмка будет судить не о том, что собрано.
    """
    ground, base = [], []
    for i, frame in enumerate(frames):
        if frame is None or (fw, fh) != (32, 40):
            ground.append(False)
            base.append(False)
            continue
        cov = xs.diamond_coverage(frame, fw, fh)
        top = min((y for y in range(fh) if any(frame[y])), default=fh)
        # flat only: slopes, stairs and hay bales (terrain level != 0) are objects, not a field; so is
        # a "floor" with something tall drawn on it (a phone booth)
        ground.append(not raised[i] and ((types[i] == xs.MCD_FLOOR and top >= fh - 16 - 8) or
                                         (types[i] == xs.MCD_OBJECT and walkable[i] and cov >= 0.85)))
        # an object standing on its own full ground diamond (a tree on grass): the painter gets the
        # diamond repeated around it as a field, so that it does not read as a planter
        base.append(not ground[-1] and types[i] in (xs.MCD_FLOOR, xs.MCD_OBJECT) and cov >= 0.85)
    return ground, base


DEFAULT_SETS = [
    "TERRAIN/CULTIVAT.PCK", "TERRAIN/BARN.PCK", "TERRAIN/ROADS.PCK", "TERRAIN/FRNITURE.PCK",
    "TERRAIN/FOREST.PCK", "TERRAIN/JUNGLE.PCK", "TERRAIN/DESERT.PCK", "TERRAIN/MOUNT.PCK",
    "TERRAIN/POLAR.PCK", "TERRAIN/URBAN.PCK", "TERRAIN/URBITS.PCK", "TERRAIN/UFO1.PCK",
    "TERRAIN/U_EXT02.PCK", "TERRAIN/U_WALL02.PCK", "TERRAIN/U_BITS.PCK", "TERRAIN/U_DISEC2.PCK",
    "TERRAIN/U_OPER2.PCK", "TERRAIN/U_PODS.PCK", "TERRAIN/U_BASE.PCK", "TERRAIN/XBASE1.PCK",
    "TERRAIN/XBASE2.PCK", "TERRAIN/PLANE.PCK", "TERRAIN/LIGHTNIN.PCK", "TERRAIN/AVENGER.PCK",
    "TERRAIN/MARS.PCK", "TERRAIN/BRAIN.PCK",
    "UNITS/XCOM_0.PCK", "UNITS/XCOM_1.PCK", "UNITS/XCOM_2.PCK", "UNITS/SECTOID.PCK", "UNITS/FLOATER.PCK",
    "UNITS/SNAKEMAN.PCK", "UNITS/MUTON.PCK", "UNITS/ETHEREAL.PCK", "UNITS/CHRYS.PCK", "UNITS/CELATID.PCK",
    "UNITS/SILACOID.PCK", "UNITS/ZOMBIE.PCK", "UNITS/CYBER.PCK", "UNITS/X_REAP.PCK", "UNITS/X_ROB.PCK",
    "UNITS/TANKS.PCK", "UNITS/CIVM.PCK", "UNITS/CIVF.PCK", "UNITS/HANDOB.PCK", "UNITS/FLOOROB.PCK",
    "UFOGRAPH/SMOKE.PCK", "UFOGRAPH/HIT.PCK", "UFOGRAPH/X1.PCK", "UFOGRAPH/CURSOR.PCK",
]


def extract_set(data_dir, rel, out_dir, palette, scale, columns, margin):
    name = os.path.basename(rel).upper()
    folder = os.path.join(data_dir, os.path.dirname(rel))
    pck = find_ci(folder, name)
    if not pck:
        print("  missing:", rel)
        return None
    stem = os.path.splitext(os.path.basename(pck))[0]
    tab = find_ci(folder, stem + ".TAB") or os.path.splitext(pck)[0] + ".TAB"
    fw, fh = xs.frame_size_for(name)
    frames = xs.read_pck(pck, tab, fw, fh)
    sheet = xs.Sheet(fw, fh, len(frames), columns=columns, margin=margin)
    # tile types from the terrain's MCD (floor / walls / object) and which frames are ground cover:
    # floors, and walkable objects that fill the floor diamond (crops, flowers; a tree is impassable) -
    # those are painted as a continuous field, not as an object standing on a background
    types, walkable, raised = [-1] * len(frames), [True] * len(frames), [False] * len(frames)
    mcd = find_ci(folder, stem + ".MCD")
    if mcd:
        types, walkable, raised = xs.frame_types(xs.read_mcd(mcd), len(frames))
    ground, base = ground_flags(frames, types, walkable, raised, fw, fh)
    target = os.path.join(out_dir, name)
    os.makedirs(target, exist_ok=True)
    sheet.compose(frames, palette, 1, "P").save(os.path.join(target, "original.png"))
    big = sheet.compose(frames, palette, scale, "RGBA")
    big.save(os.path.join(target, "original_x%d.png" % scale))
    mask = big.split()[3].point(lambda a: 255 if a else 0)
    mask.save(os.path.join(target, "mask_x%d.png" % scale))
    info = sheet.describe()
    info.update({"set": name, "source": rel, "scale": scale, "sheet_w": big.width, "sheet_h": big.height,
                 "types": types, "ground": ground, "base": base})
    with open(os.path.join(target, "layout.json"), "w") as f:
        json.dump(info, f, indent=1)
    print("  %-14s %4d frames %dx%d -> %dx%d, %d ground, %d objects on a ground diamond" % (
        name, len(frames), fw, fh, big.width, big.height, sum(ground), sum(base)))
    return info


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="the UFO data folder (with GEODATA, TERRAIN, UNITS, UFOGRAPH)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--scale", type=int, default=4)
    ap.add_argument("--columns", type=int, default=8)
    ap.add_argument("--margin", type=int, default=4)
    ap.add_argument("--sets", nargs="*", default=[])
    ap.add_argument("--all", action="store_true", help="every battlescape set of vanilla UFO")
    ap.add_argument("--palette", default="",
                    help="палитра мода (.pal, JASC или GIMP) вместо GEODATA/PALETTES.DAT. "
                         "Нужна для модов, которые подменяют PAL_BATTLESCAPE через customPalettes")
    args = ap.parse_args(argv)
    if args.palette:
        palette = xs.load_palette_file(args.palette)
        print("палитра:", args.palette)
    else:
        pal_path = os.path.join(args.data, "GEODATA", "PALETTES.DAT")
        if not os.path.exists(pal_path):
            geo = os.path.join(args.data, "GEODATA")
            found = ""
            if os.path.isdir(geo):
                for f in os.listdir(geo):
                    if f.upper() == "PALETTES.DAT":
                        found = os.path.join(geo, f)
            if not found:
                raise SystemExit(
                    "нет %s.\n"
                    "У модов вроде X-Piratez своей PALETTES.DAT нет — они подменяют боевую палитру\n"
                    "через customPalettes. Укажи её явно: --palette <мод>/Resources/Pals/<файл>.pal"
                    % pal_path)
            pal_path = found
        palette = xs.load_palette(pal_path)
    sets = list(args.sets)
    if args.all or not sets:
        sets = DEFAULT_SETS if args.all else DEFAULT_SETS[:1]
    os.makedirs(args.out, exist_ok=True)
    for rel in sets:
        extract_set(args.data, rel, args.out, palette, args.scale, args.columns, args.margin)


if __name__ == "__main__":
    main()
