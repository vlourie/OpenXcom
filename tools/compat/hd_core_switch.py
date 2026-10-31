# The one switch of the HD split (docs/portal/HD_SUBMODS.md §5): the fonts leave the hd mod for hd_core and the
# packaging, the profile and the launcher follow in the same run, so no release can carry one without the others:
#   mods      - in BOTH copies of hd (repository user/mods and the install, R-087) the fonts and their licence
#               texts move to user/mods/hd_core with its metadata.yml (hd_layout.core_files, CORE_META); the
#               rulesets whose strings live in the engine (ENGINE_OWNED) go to art/_backup/hd_core_switch;
#               hd/metadata.yml gets master piratez and its own name (hd_layout.pack_meta)
#   packaging - tools/build/build_config.json: hd_core in Mods right before hd; ModRequire of hd_core = the fonts and
#               licences, of hd = the art without fonts and Ruleset. ReleaseBuilder puts hd_core whole into art.hd
#               (Components.cs HdCoreModId): a player with HD gets it by the update, nothing new to tick
#   profile   - portal/profiles/xp-profiles.json: { "id": "hd_core" } right before { "id": "hd" }, the font option
#               needs hd_core
#   launcher  - Выпуск/release_config.json MinLauncher 0.3.7 and Xp.Launcher.csproj <Version>0.3.7: only that
#               launcher has HdCoreMigration, which switches hd_core on in the player's settings; release.ps1
#               refuses a stage with hd_core under a lower MinLauncher
# Modes:
#   (none)          checks every precondition and prints what would change; writes nothing
#   --apply         does it - the release step; take the edit queue first (tools/editq.py), the files it moves
#                   are not seen by its hook (R-108): commit with --add
#   --scratch DIR   the same transforms on a test copy, nothing of the repository or the install is written:
#                   DIR/game/user/mods = the split by tools/compat/hd_layout.py (junctions and hard links),
#                   DIR/game/common, standard = junctions to the install; DIR/build_config.json,
#                   DIR/xp-profiles.json, DIR/release_config.json for build.ps1 -Config and a release by hand
#   py -3.13 tools/compat/hd_core_switch.py [--apply | --scratch E:/tmp/hd_final/new --key <test key>]
import argparse, json, os, re, shutil, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hd_layout  # noqa: E402

ROOT = hd_layout.ROOT
INSTALL = hd_layout.MODS.parent.parent
COPIES = [ROOT / "user" / "mods", hd_layout.MODS]
BUILD_CFG = ROOT / "tools" / "build" / "build_config.json"
PROFILES = ROOT / "portal" / "profiles" / "xp-profiles.json"
RELEASE_CFG = ROOT / "Выпуск" / "release_config.json"
CSPROJ = ROOT / "portal" / "src" / "Xp.Launcher" / "Xp.Launcher.csproj"
BACKUP = ROOT / "art" / "_backup" / "hd_core_switch"
MIN_LAUNCHER = "0.3.7"
OLD_LAUNCHER = "0.3.6"
CORE_REQUIRE = ["metadata.yml", "hd/UI/FontBig.ttf", "hd/UI/FontSmall.ttf", "hd/UI/FontFallback.ttf", "hd/UI/fonts",
                "FONTS-LICENSE.txt", "ROBOTO-LICENSE.txt", "FONTS-SOURCES.txt"]
PACK_REQUIRE = ["metadata.yml", "hd/UI", "hd/TERRAIN"]
BOM = b"\xef\xbb\xbf"


def once(text, old, new, what):
    n = text.count(old)
    if n != 1:
        sys.exit(f"{what}: '{old}' found {n} time(s), expected once - the file is not what the switch knows")
    return text.replace(old, new)


def read(p):
    """Text as it is on disk: BOM and line ends kept for the write back."""
    raw = p.read_bytes()
    text = raw[len(BOM):].decode("utf-8") if raw.startswith(BOM) else raw.decode("utf-8")
    return text, raw.startswith(BOM), "\r\n" if "\r\n" in text else "\n"


def write(p, text, bom):
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_bytes((BOM if bom else b"") + text.encode("utf-8"))
    os.replace(tmp, p)


def strip_comments(text):
    return "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("//"))


def build_cfg(text, nl):
    text = once(text, '"Mods": ["hd", ', '"Mods": ["hd_core", "hd", ', BUILD_CFG.name)
    old = ('"hd": ["metadata.yml", "hd/UI/FontBig.ttf", "hd/UI/FontSmall.ttf", "hd/UI/FontFallback.ttf", '
           '"hd/UI/fonts", "Ruleset"],')
    line = re.search(r"^([ \t]*)" + re.escape(old), text, re.M)
    if not line:
        sys.exit(f"{BUILD_CFG.name}: no ModRequire line of hd with the fonts")
    new = (f'"hd_core": {json.dumps(CORE_REQUIRE, ensure_ascii=False)},{nl}{line.group(1)}'
           f'"hd": {json.dumps(PACK_REQUIRE, ensure_ascii=False)},')
    text = once(text, old, new, BUILD_CFG.name)
    cfg = json.loads(text)
    assert cfg["Mods"].index("hd_core") + 1 == cfg["Mods"].index("hd")
    assert cfg["ModRequire"]["hd_core"] == CORE_REQUIRE and cfg["ModRequire"]["hd"] == PACK_REQUIRE
    return text


def profiles(text, nl):
    line = re.findall(r'^([ \t]*)\{ "id": "hd" \},?[ \t]*\r?$', text, re.M)
    if len(line) != 1:
        sys.exit(f'{PROFILES.name}: {len(line)} line(s) {{ "id": "hd" }}, expected one')
    text = once(text, '{ "id": "hd" }', '{ "id": "hd_core" },' + nl + line[0] + '{ "id": "hd" }', PROFILES.name)
    text = once(text, '{ "key": "oxceHdUiFont", "value": "1", "needsMod": "hd" }',
                '{ "key": "oxceHdUiFont", "value": "1", "needsMod": "hd_core" }', PROFILES.name)
    p = json.loads(strip_comments(text))["profiles"][0]
    ids = [m["id"] for m in p["mods"]]
    assert ids.index("hd_core") + 1 == ids.index("hd")
    return text


def release_cfg(text, nl):
    if '"MinLauncher"' in text:
        sys.exit(f"{RELEASE_CFG.name}: MinLauncher is set already")
    line = re.search(r'^([ \t]*)"Launch": "[^"]*",', text, re.M)
    if not line:
        sys.exit(f"{RELEASE_CFG.name}: no Launch line")
    text = text.replace(line.group(0), f'{line.group(0)}{nl}{line.group(1)}"MinLauncher": "{MIN_LAUNCHER}",', 1)
    assert json.loads(text)["MinLauncher"] == MIN_LAUNCHER
    return text


def csproj(text, nl):
    return once(text, f"<Version>{OLD_LAUNCHER}</Version>", f"<Version>{MIN_LAUNCHER}</Version>", CSPROJ.name)


EDITS = [(BUILD_CFG, build_cfg), (PROFILES, profiles), (RELEASE_CFG, release_cfg), (CSPROJ, csproj)]


def plan_split(mods_root):
    """What moves where in one copy; refuses a copy that is split already or lacks a font."""
    hd, core = mods_root / "hd", mods_root / "hd_core"
    if core.exists():
        sys.exit(f"{core} exists: this copy is split already")
    files, _ = hd_layout.core_files()
    missing = [f for f in files if not (hd / f).is_file()]
    if missing:
        sys.exit(f"not in {hd}: " + ", ".join(missing))
    owned = sorted(f for f in hd_layout.ENGINE_OWNED if (hd / f).is_file())
    hd_layout.pack_meta((hd / "metadata.yml").read_text(encoding="utf-8-sig"))   # refuses an unknown file
    for need in PACK_REQUIRE[1:]:
        if not (hd / need).is_dir():
            sys.exit(f"{hd / need}: the pack would not pass its ModRequire")
    return files, owned


def split(mods_root, files, owned, backup):
    hd, core = mods_root / "hd", mods_root / "hd_core"
    before = hd_layout.listing(hd)
    for f in files:
        (core / f).parent.mkdir(parents=True, exist_ok=True)
        os.replace(hd / f, core / f)
    (core / "metadata.yml").write_text(hd_layout.CORE_META, encoding="utf-8", newline="\n")
    for f in owned:
        (backup / f).parent.mkdir(parents=True, exist_ok=True)
        os.replace(hd / f, backup / f)
    # a new name, not a write into the old file: it may be a hard link shared with the other copy
    tmp = hd / "metadata.yml.tmp"
    tmp.write_text(hd_layout.pack_meta((hd / "metadata.yml").read_text(encoding="utf-8-sig")), encoding="utf-8",
                   newline="\n")
    os.replace(tmp, hd / "metadata.yml")
    for d in (hd / "hd" / "UI" / "fonts", hd / "Ruleset"):
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()
    a_core, a_pack = hd_layout.listing(core), hd_layout.listing(hd)
    lost = before - a_core - a_pack - set(owned)
    if lost or (a_core & a_pack) - {"metadata.yml"}:
        sys.exit(f"{mods_root}: lost {sorted(lost)[:10]}, in both {sorted((a_core & a_pack) - {'metadata.yml'})[:10]}")
    print(f"{mods_root}: hd_core {len(a_core)} file(s), hd {len(a_pack)}, rulesets to {backup}: {', '.join(owned) or '-'}")


def scratch(out, key):
    """The switched packaging on a test copy: the split layout as the game folder and the three configs."""
    game = out / "game"
    if game.exists():
        sys.exit(f"{game} exists: remove it first (hd_layout.py --out {game / 'user'} --clean, then the junctions "
                 "common and standard with rmdir, R-047)")
    (game / "user").mkdir(parents=True)
    subprocess.run([sys.executable, str(Path(__file__).with_name("hd_layout.py")), "--out", str(game / "user")],
                   check=True)
    for d in ("common", "standard"):
        hd_layout.junction(game / d, INSTALL / d)

    text, _, nl = read(BUILD_CFG)
    cfg = json.loads(build_cfg(text, nl))
    cfg.update(GameDir=str(game), DistDir=str(out / "dist"), LauncherOut=str(out / "launcher"),
               LauncherDevKeys=True, SyncDataToGame=False, CopyExeTo="", OpenExplorer=False,
               ProfilesFile=str(out / "xp-profiles.json"), ModSource={m: "game" for m in cfg["Mods"]})
    (out / "build_config.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

    text, bom, nl = read(PROFILES)
    write(out / "xp-profiles.json", profiles(text, nl), bom)

    text, _, nl = read(RELEASE_CFG)
    rc = json.loads(release_cfg(text, nl))
    pub = Path(key).with_suffix(".pub")
    rc.update(Key=str(key), Pub=str(pub), Repo=str(out.parent / "repo"), Stage=str(out / "dist" / "_stage"),
              LauncherDir=str(out / "launcher"), XpRelease=str(ROOT / rc["XpRelease"]), StationDrop="",
              OpenExplorer=False)
    (out / "release_config.json").write_text(json.dumps(rc, ensure_ascii=False, indent=2), encoding="utf-8")
    print("scratch", out, "- build: tools/build/build.ps1 -Target Both -StageOnly -NoNinja -Config",
          out / "build_config.json")


def main():
    a = argparse.ArgumentParser()
    g = a.add_mutually_exclusive_group()
    g.add_argument("--apply", action="store_true", help="split both copies and edit the four files")
    g.add_argument("--scratch", help="a test copy in this folder instead")
    a.add_argument("--key", help="--scratch: the throwaway signing key of the test repository (never the prod key)")
    o = a.parse_args()
    if o.scratch:
        if not o.key or "xp-prod" in o.key.replace("\\", "/"):
            sys.exit("--scratch needs --key of a throwaway key, not the production one")
        scratch(Path(o.scratch), o.key)
        return

    new = []
    for p, f in EDITS:
        text, bom, nl = read(p)
        new.append((p, f(text, nl), bom))
    splits = [(m, *plan_split(m)) for m in COPIES]
    for m, files, owned in splits:
        print(f"{m}: {len(files)} file(s) to hd_core, rulesets out: {', '.join(owned) or '-'}")
    for p, _, _ in new:
        print("edit", p.relative_to(ROOT))
    if not o.apply:
        print("dry run: nothing written; --apply does it")
        return
    stamp = time.strftime("%Y%m%d_%H%M%S")
    for i, (m, files, owned) in enumerate(splits):
        split(m, files, owned, BACKUP / stamp / ("repo" if i == 0 else "install"))
    for p, text, bom in new:
        write(p, text, bom)
        print("written", p.relative_to(ROOT))
    print(f"switched: hd_core packaged, profiled, launcher {MIN_LAUNCHER} required")


if __name__ == "__main__":
    main()
