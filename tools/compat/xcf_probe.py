# X-Com Files + our mods: invisible runs of our build (ai_probe.Hidden + SDL dummy, R-124).
# Each run - own -user/-cfg in the scratchpad; mods by junction (remove with rmdir only, R-047).
#   py -3.13 xcf_probe.py setup        unzip XCF 4.2 and make the run folders
#   py -3.13 xcf_probe.py run <name>   export all sprite sets (OXCE_HD_EXPORT) and quit
import os, re, subprocess, sys, tempfile, time, zipfile
from pathlib import Path

ROOT = Path("E:/OpenXCom")
sys.path.insert(0, str(ROOT / "tools"))
import ai_probe

GAME = ROOT / "Пиратки" / "Dioxine_XPiratez"
MODS = GAME / "user" / "mods"
EXE = ROOT / "build-release" / "bin" / "openxcom.exe"
HERE = Path(os.environ.get("XCF_WORK", Path(tempfile.gettempdir()) / "xcf_compat"))   # runs and exports, outside the repo
HERE.mkdir(parents=True, exist_ok=True)
XCF_ZIP = Path("E:/Additional mods/openxcom_xfiles_42.zip")
XCF41 = ROOT / "new mod" / "X-Files 41b"
UNPACK = HERE / "xcf42"

PIRATEZ_ON = ["piratez", "XPZ_EX_RU-patch", "piratezCitiesLore", "piratezRusNames", "OAK patch for RU Piratez"]

# run name -> (master, [(folder in user/mods, source, active id or None)])
def runs():
    xcf = [("XComFiles", UNPACK / "XComFiles", "x-com-files"),
           ("DarkGeoscape", UNPACK / "DarkGeoscape", "dark-geoscape"),
           ("XCF Cyrillic Names", XCF41 / "XCF Cyrillic Names", "XCF-CyrNames")]
    # Piratez add-ons put in the folder too: the engine must refuse them under another master
    addons = [(n, MODS / n, i) for n, i in [("piratez_tank_turret", "piratez_tank_turret"),
              ("Apple_Processing", "apple_processing")]]
    # the install's copy is empty folders; the full mod is in the release stage
    addons.append(("XPZ_Kisya_Brysya_Sisters", ROOT / "dist" / "_stage" / "user" / "mods" / "XPZ_Kisya_Brysya_Sisters", "kisya_brysya_sisters"))
    hd = [("hd", MODS / "hd", "hd")]
    return {
        "piratez": ("piratez", None),
        "vanilla": ("xcom1", []),   # the base every game builds on: what of hd is drawn over an unchanged UFO frame
        "xcf": ("x-com-files", xcf),
        "xcf_hd": ("x-com-files", xcf + hd + [("intro_voice", MODS / "intro_voice", "intro_voice")] + addons),
    }

def junction(link, target):
    if link.exists():
        return
    subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], check=True, capture_output=True)

def setup():
    if not UNPACK.exists():
        with zipfile.ZipFile(XCF_ZIP) as z:
            z.extractall(UNPACK)
    for name, (master, mods) in runs().items():
        u = HERE / ("u_" + name)
        u.mkdir(exist_ok=True)
        cfg = (GAME / "user" / "options.cfg").read_text(encoding="utf-8")
        if mods is None:
            junction(u / "mods", MODS)   # the install's mods as they are
        else:
            (u / "mods").mkdir(exist_ok=True)
            for folder, src, _ in mods:
                junction(u / "mods" / folder, src)
            lines = ["mods:", f"  - active: true", f"    id: {master}"]
            for _, _, mid in mods:
                if mid == master:
                    continue
                lines += [f"  - active: true", f"    id: {mid}"]
            cfg = re.sub(r"(?m)^mods:\n(?:  .*\n)*", "\n".join(lines) + "\n", cfg, count=1)
        added = []
        for k, v in {"battleEdgeScroll": "0", "oxceAdultAsk": "false", "playIntro": "false", "oxceGentleAsk": "false", "language": "ru", "lazyLoadResources": "false"}.items():
            cfg, n = re.subn(rf"(?m)^(\s*){k}: .*$", lambda m: f"{m.group(1)}{k}: {v}", cfg)
            if not n:
                added.append(f"  {k}: {v}")
        if added:
            cfg = re.sub(r"(?m)^options:\s*$", "options:\n" + "\n".join(added), cfg, count=1)
        (u / "options.cfg").write_text(cfg, encoding="utf-8")
        print("ready", u)

def run(name, sets="all", extra_env=None, timeout=900):
    master, _ = runs()[name]
    u = HERE / ("u_" + name)
    out = HERE / ("exp_" + name)
    env = {k.upper(): v for k, v in os.environ.items()}
    env["PATH"] = "C:\\msys64\\mingw64\\bin;" + env.get("PATH", "")
    env.update(SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy")
    if sets:
        env.update(OXCE_HD_EXPORT=str(out), OXCE_HD_EXPORT_SETS=sets)
    env.update(extra_env or {})
    args = [str(EXE), "-data", str(GAME), "-user", str(u), "-cfg", str(u), "-master", master,
            "-fullscreen", "false", "-displayWidth", "1920", "-displayHeight", "1080",
            "-soundVolume", "0", "-musicVolume", "0"]
    logf = u / "openxcom.log"
    if logf.exists():
        logf.unlink()
    p = ai_probe.Hidden(args, str(EXE.parent), env)
    t0 = time.time()

    def game_running():
        r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq openxcom.exe"], capture_output=True, text=True)
        return "openxcom.exe" in r.stdout

    # the wrapper may exit before the game: done = export line in the log and no game process
    while True:
        ai_probe.hide_windows(p.pid)
        text = logf.read_text(encoding="utf-8", errors="replace") if logf.exists() else ""
        if ("HD export:" in text or "[FATAL]" in text) and not game_running():
            break
        if time.time() - t0 > timeout:
            subprocess.run(["taskkill", "/IM", "openxcom.exe", "/F"], capture_output=True)
            print("timeout")
            break
        time.sleep(1)
    print(name, "done in", int(time.time() - t0), "s")
    log = logf.read_text(encoding="utf-8", errors="replace").splitlines()
    for line in log:
        if re.search(r"\[(ERROR|FATAL|WARNING)\]|HD export|Loading mod|master", line):
            print("  ", line[:220])

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if sys.argv[1] == "setup":
        setup()
    else:
        run(sys.argv[2])
