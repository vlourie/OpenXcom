# Приёмка этапа 1 лаунчера - сборки (docs/portal/MULTIMOD.md §11) - на живой игре, НЕВИДИМО (R-124).
# Временная установка в --work: common, standard и user/mods - соединения на установку Пираток (только чтение,
# снимаются rmdir, R-047), exe, xp-profiles.json, состояние лаунчера, options.cfg и сейв - копии. Установку не трогает.
# Четыре пункта специалиста: миграция сохраняет конфиг; две сборки независимы; сейвы грузятся;
# под идущей игрой отказ записи профиля, управления сборками и обновления. Плюс аудит записи игры (§3.2).
#   py -3.13 tools/builds_accept.py --work E:/tmp/builds_accept --out E:/tmp/builds_accept/result.json
import argparse, hashlib, json, os, re, shutil, stat, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ai_probe

ROOT = Path(__file__).resolve().parents[1]
GAME = ROOT / "Пиратки" / "Dioxine_XPiratez"
LAUNCHER = ROOT / "portal" / "src" / "Xp.Launcher" / "bin" / "Debug" / "net10.0" / "XPiratezLauncher.exe"
FIXED = {"battleEdgeScroll": "0", "oxceAdultAsk": "false", "playIntro": "false", "oxceGentleAsk": "false"}

a = argparse.ArgumentParser()
a.add_argument("--work", required=True)
a.add_argument("--out", required=True)
a.add_argument("--save", default="NoCodexCatZ.sav")
a.add_argument("--after", type=int, default=110, help="секунд до дампа кадра и выхода игры")
a.add_argument("--launcher", default=str(LAUNCHER))
o = a.parse_args()
sys.stdout.reconfigure(encoding="utf-8")
work = Path(o.work).resolve()
inst = work / "inst"
results = []


def check(point, what, ok, detail=""):
    results.append({"point": point, "check": what, "ok": bool(ok), "detail": str(detail)})
    print(("OK  " if ok else "FAIL") + f" [{point}] {what}" + (f": {detail}" if detail else ""), flush=True)


def reparse(p):
    return bool(os.lstat(p).st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def remove_tree(p):
    # соединения снимать rmdir, не заходя внутрь (R-047)
    for e in os.scandir(p):
        if reparse(e.path):
            os.rmdir(e.path)
        elif e.is_dir(follow_symlinks=False):
            remove_tree(e.path)
        else:
            os.chmod(e.path, stat.S_IWRITE)
            os.unlink(e.path)
    os.rmdir(p)


def junction(link, target):
    subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], check=True, capture_output=True)


def sha(p):
    p = Path(p)
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16] if p.exists() else None


def snapshot(root, skip=()):
    out = {}
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if not reparse(os.path.join(dp, d))]
        for f in fns:
            full = os.path.join(dp, f)
            rel = os.path.relpath(full, root).replace("\\", "/")
            if not any(re.match(s, rel) for s in skip):
                out[rel] = sha(full)
    return out


def diff(before, after):
    return {"added": sorted(set(after) - set(before)), "removed": sorted(set(before) - set(after)),
            "changed": sorted(k for k in set(before) & set(after) if before[k] != after[k])}


def cfg_keys(p):
    keys = {}
    for line in Path(p).read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"^  (\w+): (.*)$", line)
        if m:
            keys[m.group(1)] = m.group(2)
    return keys


def launcher(*args):
    r = subprocess.run([o.launcher, "--headless", *args, "--game", str(inst)], capture_output=True,
                       encoding="utf-8", errors="replace", timeout=120)
    return r.returncode, (r.stdout + r.stderr).strip()


def builds():
    return json.loads((inst / "launcher" / "builds.json").read_text(encoding="utf-8-sig"))


def run_game(args, tag, extra):
    dump = work / f"{tag}.png"
    if dump.exists():
        dump.unlink()
    env = {k.upper(): v for k, v in os.environ.items()}
    env["PATH"] = "C:\\msys64\\mingw64\\bin;" + env.get("PATH", "")
    env.update(SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy", OXCE_HD_DUMP=str(dump), OXCE_HD_DUMP_AFTER=str(o.after))
    exe = inst / "openxcom_hd.exe"
    # как Play в лаунчере: рабочий каталог - установка, аргументы - builds args; плюс сейв и ключи прогона
    p = ai_probe.Hidden([str(exe), *args, *extra], str(inst), env)
    print(f"{tag}: pid {p.pid} (скрытый рабочий стол)", flush=True)
    return p, dump


def wait_game(p, t0):
    """(код выхода, принудительно): принудительно - таймаут и taskkill; код тогда от taskkill, а не от игры."""
    forced = False
    while p.poll() is None:
        ai_probe.hide_windows(p.pid)
        if time.time() - t0 > o.after + 90:
            subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True)
            print("таймаут: игра снята taskkill")
            forced = True
            p.wait()
            break
        time.sleep(0.2)
    return p.returncode, forced


def game_log():
    log = inst / "user" / "openxcom.log"
    return log.read_text(encoding="utf-8", errors="replace").splitlines() if log.exists() else []


def loaded_geoscape(lines):
    return [l for l in lines if "HD frame" in l and "Geoscape" in l]


def exited_cleanly(tag, rc, forced, dump, geo):
    """Штатный выход: игра сама дошла до дампа и закрылась. Четыре условия отдельно - одно не заменяет другое."""
    check(3, f"игра на {tag} вышла сама: без таймаута и taskkill", not forced, "снята taskkill" if forced else "")
    check(3, f"игра на {tag}: код выхода 0", rc == 0, f"код {rc}")
    check(3, f"игра на {tag}: кадр-дамп есть", dump.exists(), dump.name)
    check(3, f"игра на {tag}: сейв загружен, геоскейп в логе", bool(geo), geo[-1] if geo else "в логе нет кадров геоскейпа")


# ------------------------------------------------------------------ установка
if work.exists():
    remove_tree(work)
(inst / "user" / "piratez").mkdir(parents=True)
(inst / "launcher").mkdir()
for d in ("common", "standard", "UFO", "TFTD"):   # без UFO мастер Пираток не грузится: 'No X-COM installations found'
    if (GAME / d).exists():
        junction(inst / d, GAME / d)
junction(inst / "user" / "mods", GAME / "user" / "mods")
shutil.copy2(GAME / "openxcom_hd.exe", inst)
shutil.copy2(GAME / "xp-profiles.json", inst)
for f in ("profiles.json", "profile-mods.json"):
    if (GAME / "launcher" / f).exists():
        shutil.copy2(GAME / "launcher" / f, inst / "launcher")
raw = (GAME / "user" / "options.cfg").read_bytes().decode("utf-8")
for n, v in FIXED.items():   # то, что спрашивает игрока при запуске (R-095) и крутит камеру мышью (R-093)
    raw, k = re.subn(rf"(?m)^(\s*){n}: .*$", lambda m: f"{m.group(1)}{n}: {v}", raw)
    if not k:
        raw = re.sub(r"(?m)^options:\s*$", f"options:\n  {n}: {v}", raw, count=1)
(inst / "user" / "options.cfg").write_bytes(raw.encode("utf-8"))
shutil.copy2(GAME / "user" / "piratez" / o.save, inst / "user" / "piratez" / o.save)
SAVE = inst / "user" / "piratez" / o.save
LEGACY = inst / "user" / "options.cfg"
STATE = [r"^launcher/logs/", r"^user/openxcom\.log", r"^openxcom_hd\.exe$"]
mods_t0 = time.time()

# ------------------------------------------------------------------ 1. миграция
h_cfg0, h_save0 = sha(LEGACY), sha(SAVE)
s0 = snapshot(inst, [r"^openxcom_hd\.exe$"])
rc, out = launcher("builds", "list")
print(out)
check(1, "первый запуск со сборками: код 0", rc == 0, rc)
bs = builds()
A = bs["last"]
cfgA = inst / "user" / "builds" / A / "options.cfg"
check(1, "в builds.json только записанные поля, без вычисляемого current", "current" not in bs, sorted(bs))
check(1, "сборка создана из активного мастера",A == "piratez" and [b["id"] for b in bs["builds"]] == ["piratez"], [b["id"] for b in bs["builds"]])
check(1, "конфиг сборки - побайтная копия прежнего user/options.cfg", sha(cfgA) == h_cfg0, f"{sha(cfgA)} против {h_cfg0}")
check(1, "прежний user/options.cfg на месте и не изменён", sha(LEGACY) == h_cfg0)
check(1, "сейв не тронут", sha(SAVE) == h_save0)
d = diff(s0, snapshot(inst, [r"^openxcom_hd\.exe$"]))
check(1, "миграция только добавила файлы, ничего не изменила и не удалила", not d["changed"] and not d["removed"], d)
h_json = sha(inst / "launcher" / "builds.json")
rc, _ = launcher("builds", "list")
check(1, "второй запуск миграцию не повторяет", rc == 0 and sha(inst / "launcher" / "builds.json") == h_json and sha(cfgA) == h_cfg0)

# ------------------------------------------------------------------ 2. вторая сборка
rc, out = launcher("builds", "copy", "--id", A, "--title", "Копия Пираток")
B = out.split("created ")[-1].split()[0] if "created " in out else None
check(2, "копия сборки: код 0", rc == 0 and B, out.splitlines()[-1] if out else rc)
cfgB = inst / "user" / "builds" / B / "options.cfg"
check(2, "копия - побайтно тот же конфиг", sha(cfgB) == sha(cfgA))
rc, out = launcher("builds", "new", "--title", "Новая", "--template", "piratez")
C = out.split("created ")[-1].split()[0] if "created " in out else None
check(2, "новая сборка из профиля: код 0", rc == 0 and C, out.splitlines()[-1] if out else rc)
cfgC = inst / "user" / "builds" / C / "options.cfg"
check(2, "у новой сборки свой конфиг", cfgC.exists() and C not in (A, B))

# Play на A: профиль в конфиг A, затем игра с аргументами A
rc, _ = launcher("builds", "select", "--id", A)
rc2, out = launcher("profile")
check(2, "профиль пишется в конфиг текущей сборки", rc == 0 and rc2 == 0 and f"user/builds/{A}/options.cfg" in out, out.splitlines()[0] if out else rc2)
rc, out = launcher("builds", "args", "--id", A)
argsA = out.splitlines()
check(2, "аргументы запуска сборки A", rc == 0 and "-cfg" in argsA and argsA[argsA.index("-cfg") + 1].endswith(f"/user/builds/{A}/"), argsA)
keysA0 = cfg_keys(cfgA)
hB1, hC1, hL1 = sha(cfgB), sha(cfgC), sha(LEGACY)
check(2, "контроль: значение, которое меняет игра, в A ещё не 13", keysA0.get("battleScrollSpeed") != "13", keysA0.get("battleScrollSpeed"))
s_game0 = snapshot(inst, [r"^openxcom_hd\.exe$"])

# ------------------------------------------------------------------ игра на A; 4. отказ под игрой
t0 = time.time()
p, dumpA = run_game(argsA, "gameA", ["-battleScrollSpeed", "13", "-load", o.save])
time.sleep(8)
watch = [r"^launcher/(builds|profiles|profile-mods|state)\.json$", r"^user/builds/", r"^user/options\.cfg$"]
def guarded():
    return {k: v for k, v in snapshot(inst, [r"^openxcom_hd\.exe$"]).items() if any(re.match(w, k) for w in watch)}
g0 = guarded()
for op in (["builds", "new", "--title", "Под игрой"], ["builds", "copy", "--id", A, "--title", "Под игрой"],
           ["builds", "rename", "--id", B, "--title", "Под игрой"], ["builds", "delete", "--id", C],
           ["builds", "select", "--id", B], ["profile"], ["rollback"]):
    rc, out = launcher(*op)
    check(4, f"под игрой '{' '.join(op[:2])}' - отказ (код 2)", rc == 2 and "REFUSED" in out, out.splitlines()[-1] if out else rc)
check(4, "игра всё это время шла (иначе проверка пустая)", p.poll() is None)
check(4, "под игрой ни один файл сборок, профиля и конфига не изменился", guarded() == g0, diff(g0, guarded()))
rc, forced = wait_game(p, t0)
logA = game_log()
geo = loaded_geoscape(logA)
exited_cleanly("сборке A (сейв из user/piratez)", rc, forced, dumpA, geo)
errs = [l for l in logA if re.search(r"\[ERROR\]|\[FATAL\]", l)]
print("ошибки в логе игры A:", *errs[-10:], sep="\n  ")
keysA1 = cfg_keys(cfgA)
check(2, "игра записала изменённую настройку в конфиг A", keysA1.get("battleScrollSpeed") == "13", keysA1.get("battleScrollSpeed"))
changedA = {k: (keysA0.get(k), keysA1.get(k)) for k in set(keysA0) | set(keysA1) if keysA0.get(k) != keysA1.get(k)}
print("ключи A, изменённые игрой:", changedA)
check(2, "конфиг B побайтно прежний", sha(cfgB) == hB1)
check(2, "конфиг новой сборки побайтно прежний", sha(cfgC) == hC1)
check(2, "прежний user/options.cfg побайтно прежний", sha(LEGACY) == hL1)
check(3, "сейв после загрузки цел (игра его не переписала)", sha(SAVE) == h_save0)
auditA = diff(s_game0, snapshot(inst, [r"^openxcom_hd\.exe$"]))
print("аудит: что игра на сборке A записала в установку:", json.dumps(auditA, ensure_ascii=False, indent=1))

# ------------------------------------------------------------------ игра на B
rc, _ = launcher("builds", "select", "--id", B)
rc2, out = launcher("profile")
check(2, "выбор B и профиль в конфиг B", rc == 0 and rc2 == 0 and f"user/builds/{B}/options.cfg" in out, out.splitlines()[0] if out else rc2)
rc, out = launcher("builds", "args", "--id", B)
argsB = out.splitlines()
hA2, keysB0 = sha(cfgA), cfg_keys(cfgB)
s_game1 = snapshot(inst, [r"^openxcom_hd\.exe$"])
t0 = time.time()
p, dumpB = run_game(argsB, "gameB", ["-load", o.save])
rc, forced = wait_game(p, t0)
logB = game_log()
geo = loaded_geoscape(logB)
exited_cleanly("сборке B (тот же сейв)", rc, forced, dumpB, geo)
check(2, "после игры на B конфиг A побайтно прежний", sha(cfgA) == hA2)
check(2, "в B осталась своя настройка, а не 13 из A", cfg_keys(cfgB).get("battleScrollSpeed") == keysB0.get("battleScrollSpeed") != "13",
      cfg_keys(cfgB).get("battleScrollSpeed"))
auditB = diff(s_game1, snapshot(inst, [r"^openxcom_hd\.exe$"]))
print("аудит: что игра на сборке B записала:", json.dumps(auditB, ensure_ascii=False, indent=1))
touched = [str(Path(dp, f)) for dp, _, fns in os.walk(GAME / "user" / "mods") for f in fns
           if os.path.getmtime(Path(dp, f)) > mods_t0]
check("3.2", "игра ничего не записала в моды (через соединение - в установку)", not touched, touched[:10])

# ------------------------------------------------------------------ без игры управление работает (контроль к пункту 4)
rc, out = launcher("rollback")
check(4, "контроль: без игры rollback не отказ по игре", rc != 2, out.splitlines()[-1] if out else rc)
rc, _ = launcher("builds", "rename", "--id", B, "--title", "Копия, переименована")
check(4, "контроль: без игры переименование работает", rc == 0 and next(b for b in builds()["builds"] if b["id"] == B)["title"] == "Копия, переименована")
rc, out = launcher("builds", "delete", "--id", C)
kept = out.split("settings kept in ")[-1].splitlines()[0].strip() if "settings kept in " in out else ""
kp = Path(kept) if Path(kept).is_absolute() else inst / kept
check(4, "контроль: без игры удаление работает, настройки перенесены в резерв",
      rc == 0 and kept and C not in [b["id"] for b in builds()["builds"]] and not cfgC.parent.exists() and (kp / "options.cfg").exists(), kept)

json.dump({"results": results, "auditA": auditA, "auditB": auditB, "changedA": changedA,
           "argsA": argsA, "argsB": argsB, "errorsA": errs[-20:]},
          open(o.out, "w", encoding="utf-8-sig"), ensure_ascii=False, indent=1)
bad = [r for r in results if not r["ok"]]
print(f"\nитого: {len(results) - len(bad)} из {len(results)} OK")
sys.exit(1 if bad else 0)
