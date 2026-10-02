# Step 1 of the HD split (docs/portal/HD_SUBMODS.md §5): lays the hd mod out as two mods by
# docs/research/data/hd_split.tsv, next to the install and without touching it:
#   hd_core - the rows of submod "hd_core" (TTF fonts, paths under hd/UI) with their licence texts:
#             <family>-OFL.txt beside each font, FONTS-LICENSE.txt (DejaVu) of the mod root;
#   hd      - everything else, "hd_core?" and "hd_shared?" candidates included; keeps the id hd (step 1:
#             the engine checked that id in MainMenuState, AdultChoiceState, OptionsHdState; step 2 replaced
#             the checks), gets master: piratez as the plan says. The rulesets whose strings moved to
#             bin/common/Language/OXCE (step 2) are left out: their extraStrings would override the
#             engine's strings in every other language (R-131).
# The layout is <out>/mods: junctions to every other mod of the install, hd_core and hd as real folders
# of hard links (no copy of gigabytes) and junctions to untouched subtrees. The install stays as it is,
# so no release takes the split before its acceptance (fonts HD_FONTS §2, launcher migration).
# Remove the layout only with rmdir for junctions (R-047): --clean does it.
#   py -3.13 tools/compat/hd_layout.py --out E:/tmp/hd_layout [--clean]
import argparse, csv, os, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODS = ROOT / "Пиратки" / "Dioxine_XPiratez" / "user" / "mods"
TABLE = ROOT / "docs" / "research" / "data" / "hd_split.tsv"
FILE_ATTRIBUTE_REPARSE_POINT = 0x400
# strings now in the engine (docs/portal/HD_SUBMODS.md §5 step 2); the pack no longer ships them
ENGINE_OWNED = {"Ruleset/reports.rul", "Ruleset/adult.rul", "Ruleset/fire.rul", "Ruleset/reticle.rul"}

CORE_META = """name: "HD core: fonts"
version: 0.2
description: "TTF fonts of the HD interface: Roboto, DejaVu Sans and the OFL families. Independent of game data."
author: OXCE-HD
id: hd_core
master: "*"
"""


def reparse(p):
    return bool(os.lstat(p).st_file_attributes & FILE_ATTRIBUTE_REPARSE_POINT)


def junction(link, target):
    subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], check=True, capture_output=True)


def clean(path):
    """Junctions go with rmdir (the link only), hard links with unlink; the targets stay."""
    if not path.exists():
        return
    for dirpath, dirs, files in os.walk(path, topdown=True):
        for d in list(dirs):
            p = Path(dirpath) / d
            if reparse(p):
                os.rmdir(p)
                dirs.remove(d)
        for f in files:
            os.unlink(Path(dirpath) / f)
    for dirpath, dirs, _ in sorted(os.walk(path), key=lambda t: -len(t[0])):
        os.rmdir(dirpath)


def core_files():
    """hd_core files relative to the mod root, from the table plus the licence texts that go with them."""
    with open(TABLE, encoding="utf-8-sig", newline="") as f:
        rows = [r for r in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE) if r["submod"] == "hd_core"]
    files = set()
    for r in rows:
        if r["kind"] != "font":
            sys.exit(f"hd_core row of kind {r['kind']} ({r['name']}): this layout only knows fonts")
        rel = "hd/UI/" + r["name"]
        files.add(rel)
        if r["name"].startswith("fonts/"):
            files.add("hd/UI/fonts/" + r["name"][6:].rsplit("-", 1)[0] + "-OFL.txt")
    files.add("FONTS-LICENSE.txt")
    return sorted(files), len(rows)


def place(src_root, dst_root, rel_dir, taken):
    """Mirror src_root/rel_dir into dst_root: a subtree with nothing taken is one junction,
    otherwise a real folder of hard links that leaves the taken files out."""
    src, dst = src_root / rel_dir, dst_root / rel_dir
    if not any(t == rel_dir or t.startswith(rel_dir + "/") for t in taken if rel_dir) and rel_dir:
        junction(dst, src)
        return
    dst.mkdir(parents=True, exist_ok=True)
    for e in sorted(src.iterdir()):
        rel = f"{rel_dir}/{e.name}" if rel_dir else e.name
        if e.is_dir():
            place(src_root, dst_root, rel, taken)
        elif rel not in taken and rel != "metadata.yml":
            os.link(e, dst / e.name)


def listing(root):
    """Files under root by relative path, following junctions (the layout is junctions and links)."""
    out = set()
    for dirpath, _, files in os.walk(root, followlinks=True):
        for f in files:
            out.add((Path(dirpath) / f).relative_to(root).as_posix())
    return out


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--out", required=True, help="folder of the layout; its mods/ is what -user/mods points to")
    a.add_argument("--clean", action="store_true", help="only remove the layout")
    o = a.parse_args()
    out = Path(o.out)
    clean(out / "mods")
    if o.clean:
        print("removed", out / "mods")
        return
    hd = MODS / "hd"
    files, fonts = core_files()
    missing = [f for f in files if not (hd / f).is_file()]
    if missing:
        sys.exit("not in the install's hd: " + ", ".join(missing))
    mods = out / "mods"
    mods.mkdir(parents=True)
    for m in sorted(MODS.iterdir()):
        if m.is_dir() and m.name != "hd":
            junction(mods / m.name, m)

    core = mods / "hd_core"
    for f in files:
        (core / f).parent.mkdir(parents=True, exist_ok=True)
        os.link(hd / f, core / f)
    (core / "metadata.yml").write_text(CORE_META, encoding="utf-8", newline="\n")

    pack = mods / "hd"
    place(hd, pack, "", set(files) | ENGINE_OWNED)
    # the install's file has a BOM; the game reads it either way, the layout writes it without (R-001)
    meta = (hd / "metadata.yml").read_text(encoding="utf-8-sig")
    if "master:" not in meta or "id: hd" not in meta:
        sys.exit("hd/metadata.yml: no master or id line, the layout would guess")
    if not meta.startswith("name:"):
        sys.exit("hd/metadata.yml does not start with name:, the layout would leave the old name")
    lines = []
    for line in meta.splitlines():
        if line.startswith("master:"):
            line = "master: piratez"
        elif line.startswith("name:"):
            line = 'name: "HD graphics: X-Piratez"'
        lines.append(line)
    (pack / "metadata.yml").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    # every file of the old hd is in exactly one of the two, metadata.yml in both by design,
    # the engine-owned rulesets in neither
    old = listing(hd) - {"metadata.yml"}
    owned = old & ENGINE_OWNED
    old -= owned
    a_core, a_pack = listing(core) - {"metadata.yml"}, listing(pack) - {"metadata.yml"}
    both, lost, extra = a_core & a_pack, old - a_core - a_pack, (a_core | a_pack) - old
    print(f"hd_core: {len(a_core)} file(s) ({fonts} font(s) of the table and their licences)")
    print(f"hd:      {len(a_pack)} file(s), master piratez, id hd")
    print(f"engine:  {len(owned)} ruleset(s) of strings left out: {', '.join(sorted(owned))}")
    print(f"old hd:  {len(old)} file(s) besides; in both {len(both)}, lost {len(lost)}, new {len(extra)}")
    if both or lost or extra:
        for f in sorted(both | lost | extra)[:20]:
            print("  !!", f)
        sys.exit(1)
    print("layout", mods)


if __name__ == "__main__":
    main()
