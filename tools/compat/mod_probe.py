# Чужие игры mod.io + наши моды: невидимая проверка на живом стенде (hdbench, R-124), билет XP-000068.
# Каждая игра - своя папка модов из соединений (игра + все моды установки Пираток, снимать только rmdir, R-047)
# и свой -user. Два варианта: bare - только моды игры; ours - игра + наши общие моды (hd_core, intro_voice)
# + все наши моды Пираток включены галочкой (движок обязан их отклонить: master piratez); classic - как bare,
# но классический рисунок (oxceHdMode 0): отделяет падение HD-слоя от падения самой игры.
#   py -3.13 tools/compat/mod_probe.py run [игра ...] [--variant bare|ours|classic|all]
#   py -3.13 tools/compat/mod_probe.py report          сводка по логам -> stdout
# Архивы mod.io распакованы в E:\Additional mods\modio-2026-10-27\<игра>\x (MODIO_DIR).
import argparse, json, os, re, subprocess, sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import hidden_game

MODIO = Path(os.environ.get("MODIO_DIR", "E:/Additional mods/modio-2026-10-27"))
WORK = Path(os.environ.get("MODPROBE_WORK", Path(tempfile.gettempdir()) / "mod_probe"))
OUR_MODS = hidden_game.GAME / "user" / "mods"
SHARED = ["hd_core", "intro_voice"]   # master "*"
# TFTD (TWoTS): в установке Пираток папка TFTD только с README, движок берёт первую найденную - своя папка данных
TFTD = Path(os.environ.get("TFTD_DIR", "C:/Program Files (x86)/Steam/steamapps/common/X-COM Terror from the Deep/TFD"))
DATA_TFTD = {"twots"}

# игра -> мастер движка, [(папка в архиве, id мода)]; порядок = порядок загрузки
GAMES = {
    "xcf": ("x-com-files", [("xcf/x/XComFiles", "x-com-files"), ("xcf/x/DarkGeoscape", "dark-geoscape"),
                            ("xcf/x/XCF Cyrillic Names", "XCF-CyrNames")]),
    "40k": ("40k", [("40k/x/40k", "40k")]),
    "rosigma": ("40k", [("40k/x/40k", "40k"), ("rosigma/x/rosigma", "40k_ROSIGMA_edits")]),
    "xchr": ("Xchr", [("xchr/x/XCHR", "Xchr"), ("xchr/x/XCHR Cyrillic Names", "XCHR-CyrNames")]),
    "marscom": ("Mars-com", [("marscom/x/Mars-com", "Mars-com")]),
    "twots": ("xcom2", [("twots/x/TWoTS", "TWoTS")]),
}
# бой - отдельным стендом из главного меню: бой поверх уже открытой кампании (глобус -> база -> open battle) роняет
# игру и на Mars-com в режиме 0 - это сценарий, а не мод (прямой OXCE_HD_START=battle доходит до брифинга)
SCRIPTS = {
    "ui": "shot {d}/menu.png; open geoscape; wait 4000; shot {d}/geo.png; open base; wait 3000; shot {d}/base.png; state",
    "battle": "open battle; wait 5000; shot {d}/briefing.png; key 13; wait 12000; shot {d}/inventory.png; "
              # снаряжение закрывает Esc (keyCancel), под ним NextTurnState - Enter
              "key 27; wait 3000; key 13; wait 8000; shot {d}/battle.png; state",
}


def our_ids():
    """id всех наших модов из установки Пираток: папка -> id."""
    out = {}
    for d in sorted(OUR_MODS.iterdir()):
        m = d / "metadata.yml"
        if m.is_file():
            t = m.read_text(encoding="utf-8-sig", errors="replace")
            g = re.search(r'(?m)^id:\s*"?([^"\r\n]+?)"?\s*$', t)
            if g:
                out[d.name] = g.group(1)
    return out


def junction(link, target):
    if link.exists():
        return
    subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], check=True, capture_output=True)


def mods_dir(game):
    d = WORK / f"mods_{game}"
    d.mkdir(parents=True, exist_ok=True)
    for rel, _ in GAMES[game][1]:
        junction(d / Path(rel).name, MODIO / rel)
    for name in our_ids():
        junction(d / name, OUR_MODS / name)
    return d


def data_dir(game):
    """-data для игры: установка Пираток, а для TFTD - папка из соединений (common, standard, UFO из установки, TFTD из Steam)."""
    if game not in DATA_TFTD:
        return ""
    if not (TFTD / "GEODATA").is_dir():
        raise SystemExit(f"нет данных TFTD: {TFTD} (TFTD_DIR)")
    d = WORK / "data_tftd"
    d.mkdir(parents=True, exist_ok=True)
    for name in ("common", "standard", "UFO"):
        junction(d / name, hidden_game.GAME / name)
    junction(d / "TFTD", TFTD)
    return str(d)


def piratez_cfg_ids():
    cfg = (hidden_game.GAME / "user" / "options.cfg").read_text(encoding="utf-8")
    sec = re.search(r"(?ms)^mods:\n(.*?)^\S", cfg)
    return re.findall(r"(?m)^    id: (.+?)\r?$", sec.group(1)) if sec else []


def run_one(game, variant, phases=None):
    master, mods = GAMES[game]
    name = f"mp_{game}_{variant}"
    out = WORK / name
    out.mkdir(parents=True, exist_ok=True)
    for f in out.glob("*.png"):
        f.unlink()
    ours = our_ids()
    flags = {i: "false" for i in piratez_cfg_ids()}
    flags.update({i: "false" for i in ours.values()})
    for _, i in mods:
        flags[i] = "true"
    if variant in ("ours", "ours0"):
        for i in ours.values():
            flags[i] = "true"   # моды Пираток - движок должен отказать; общие - загрузиться
    flags[master] = "true"
    order = [i for i in flags if i not in {m for _, m in mods}] + [m for _, m in mods]
    mods_arg = ";".join(f"{i}={flags[i]}" for i in order)
    user = WORK / f"u_{name}"
    hb = [sys.executable, str(ROOT / "tools" / "hdbench.py")]
    res = {"game": game, "variant": variant, "master": master, "phases": {}}
    env = dict(os.environ, OXCE_HIDDEN_DATA=data_dir(game))
    text = ""
    for phase, script in SCRIPTS.items():
        if phases and phase not in phases:
            continue
        t0 = time.time()
        r = subprocess.run(hb + ["start", "--name", name, "--save", "", "--user", str(user), "--mods-dir", str(mods_dir(game)),
                                 "--mods", mods_arg, "--master", master, "--timeout", "1200",
                                 "--set", "oxceHdMode=0" if variant in ("classic", "ours0") else ""],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
        ph = {"start_rc": r.returncode, "start": (r.stdout + r.stderr)[-800:], "load_s": round(time.time() - t0, 1)}
        if r.returncode == 0:
            r2 = subprocess.run(hb + ["run", "--name", name, "--timeout", "300", script.format(d=out.as_posix())],
                                capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
            ph.update(run_rc=r2.returncode, run=(r2.stdout + r2.stderr)[-2000:])
        subprocess.run(hb + ["stop", "--name", name], capture_output=True)
        log = user / "openxcom.log"
        lt = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
        ph["fatal"] = "[FATAL]" in lt
        res["phases"][phase] = ph
        text += f"===== {phase}\n" + lt
    res["start_rc"] = max(p["start_rc"] for p in res["phases"].values())
    res["run_rc"] = max(p.get("run_rc", 9) for p in res["phases"].values())
    res["load_s"] = next(iter(res["phases"].values()))["load_s"]
    (out / "openxcom.log").write_text(text, encoding="utf-8-sig")
    res["errors"] = [l for l in text.splitlines() if re.search(r"\[(ERROR|FATAL)\]", l)][:200]
    res["warnings"] = sum(1 for l in text.splitlines() if "[WARN" in l)
    res["loaded"] = [l.split("]", 2)[-1].strip() for l in text.splitlines() if "Loading mod" in l or "loaded mod" in l.lower()][:60]
    res["refused"] = [l for l in text.splitlines() if re.search(r"missing master|can't activate|not activ|master mod", l, re.I)][:60]
    (out / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8-sig")
    print(f"{name}: start {res['start_rc']} run {res.get('run_rc')} "
          f"падение {[k for k, v in res['phases'].items() if v['fatal']]} ошибок {len(res['errors'])} "
          f"предупр. {res['warnings']} {res['load_s']} с", flush=True)
    return res


def report():
    for f in sorted(WORK.glob("mp_*/result.json")):
        r = json.loads(f.read_text(encoding="utf-8-sig"))
        print(f"== {f.parent.name}: start {r['start_rc']} run {r.get('run_rc')} ошибок {len(r['errors'])} "
              f"предупреждений {r['warnings']} загрузка {r['load_s']} с")
        for l in r["errors"][:12]:
            print("   ", l[:200])
        for l in r["refused"][:8]:
            print("   отказ:", l[:200])


def main():
    hidden_game.utf8_streams()
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "report"])
    ap.add_argument("games", nargs="*")
    ap.add_argument("--variant", default="all", choices=["bare", "ours", "classic", "ours0", "all"])
    ap.add_argument("--phase", default="", help="ui,battle (по умолчанию обе)")
    a = ap.parse_args()
    if a.cmd == "report":
        return report()
    for g in a.games or list(GAMES):
        for v in (["bare", "ours", "classic"] if a.variant == "all" else [a.variant]):
            run_one(g, v, a.phase.split(",") if a.phase else None)


if __name__ == "__main__":
    main()
