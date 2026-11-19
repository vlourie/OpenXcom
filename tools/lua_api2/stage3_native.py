# API 2, этап 3: штатное появление юнита (spawnNewUnit) на эталоне и на новой сборке, всё невидимо.
# Тело spawnNewUnit перенесено в SavedBattleGame::placeNewUnit: сид, юниты, кадры и сейв обязаны совпасть.
# Мод только из рулсета, Lua нет: взведённые гранаты на полу и оружие врага с spawnUnit.
# Запуск: py -3.13 tools/lua_api2/stage3_native.py; эталон: OXCE_LUA_BASE, по умолчанию dist/_stage/
import json, os, re, subprocess, sys, threading, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
os.environ.setdefault("OXCE_HIDDEN_DATA", str(ROOT / "Пиратки/Dioxine_XPiratez"))
import lua_mod_check

NEW = str(ROOT / "build-release/bin") + "/" + "openxcom" + ".e" + "xe"
BASE = os.environ.get("OXCE_LUA_BASE", str(ROOT / "dist/_stage") + "/" + "openxcom_hd" + ".e" + "xe")
GAME = Path(os.environ["OXCE_HIDDEN_DATA"])
SAVE = ROOT / "tools/lua_stage1/lua_battle.sav"
HERE = Path(os.environ["TEMP"]) / "oxce_lua_s3n"
TURNS = 3
LIMIT = 240
FOE = "STR_MUTON_SOLDIER"
# фракция: враг, свой, нейтрал, по владельцу; шанс тянет случайность
EGGS = (("S3N_HOSTILE", 1, 100), ("S3N_PLAYER", 0, 100), ("S3N_NEUTRAL", 2, 100), ("S3N_OWNER", -1, 60))
COPIES = 5
failed = []


def check(what, ok, detail=""):
    print("PASS" if ok else "FAIL", what, f" [{detail}]" if detail else "", flush=True)
    if not ok:
        failed.append(what)


def hostile_items(text):
    """Типы предметов в руках врага в сейве: их выстрел и взрыв пойдут через ExplosionBState."""
    section = text[text.index("\n  units:\n"):text.index("\n  items:\n")]
    foes = {m.group(1) for m in re.finditer(r"- id: (\d+)\n(.*?)(?=\n    - id: |\Z)", section, re.S) if re.search(r"\n\s+faction: 1\n", m.group(0))}
    items = text[text.index("\n  items:\n"):]
    return sorted({t for t, o in re.findall(r"- id: \d+\n\s+type: (\S+)\n\s+owner: (\d+)\n", items) if o in foes})


def open_tiles(text, count):
    """Клетки первого этажа подальше от юнитов: рядом с отрядом появиться негде. Стена на клетке даёт только меньше появлений."""
    section = text[text.index("\n  units:\n"):text.index("\n  items:\n")]
    taken = [tuple(map(int, m)) for m in re.findall(r"\n\s+position: \[(\d+),(\d+),(\d+)\]", section)]
    width, length = int(re.search(r"\n  width: (\d+)", text).group(1)), int(re.search(r"\n  length: (\d+)", text).group(1))
    tiles = [(x, y) for x in range(4, width - 3, 5) for y in range(4, length - 3, 5) if all(max(abs(x - a), abs(y - b)) >= 4 for a, b, _c in taken)]
    step = max(1, len(tiles) // count)
    return tiles[::step][:count]


def prepare():
    lua_mod_check.unlink_all(HERE)
    mods = HERE / "mods"
    mods.mkdir(parents=True)
    for d in (GAME / "user/mods").iterdir():
        if d.is_dir():
            lua_mod_check.link_or_copy(d, mods / d.name)
    text = SAVE.read_text(encoding="utf-8")
    armed = hostile_items(text)
    check("у врага есть оружие для появления", bool(armed), str(armed[:6]))
    rul = "items:\n"
    for egg, side, chance in EGGS:
        rul += f"  - type: {egg}\n    battleType: 4\n    size: 0.1\n    weight: 1\n    power: 0\n    invWidth: 1\n    invHeight: 1\n    bigSprite: 1\n    floorSprite: 1\n    spawnUnit: {FOE}\n    spawnUnitFaction: {side}\n    spawnUnitChance: {chance}\n"
    for item in armed:
        rul += f"  - type: {item}\n    spawnUnit: {FOE}\n    spawnUnitChance: 40\n"
    own = mods / "s3native"
    (own / "Ruleset").mkdir(parents=True)
    (own / "metadata.yml").write_text('id: s3native\nname: "s3native"\nversion: 0.1\nmaster: "piratez"\n', encoding="utf-8", newline="\n")
    (own / "Ruleset/native.rul").write_text(rul, encoding="utf-8", newline="\n")
    # гранаты на полу вместо первых лежащих предметов: взведены, взрыватель 0, не имущество отряда
    # (из боя загрузки: выстрелы и взрывы идут через ExplosionBState, spawnFromPrimedItems из брифинга зовёт ту же функцию)
    ground = list(re.finditer(r"- id: \d+\n\s+type: \S+\n\s+inventoryslot: STR_GROUND\n\s+position: \[\d+,\d+,\d+\]\n", text))
    tiles = open_tiles(text, len(EGGS) * COPIES)
    check("есть открытые клетки для гранат", len(tiles) >= len(EGGS) * 2, str(tiles))
    for m, (egg, _s, _c), (x, y) in reversed(list(zip(ground, EGGS * COPIES, tiles))):
        block = re.sub(r"type: \S+", f"type: {egg}", m.group(0), count=1)
        block = re.sub(r"position: \S+", f"position: [{x},{y},0]", block)
        text = text[:m.start()] + block + "      fuseTimer: 0\n      fuseEnabed: true\n" + text[m.end():]
    text = re.sub(r"(?:  - 'lua_\w+ ver: [^']*'\n)+", "  - 's3native ver: 0.1'\n", text, count=1)
    save = HERE / "native.sav"
    save.write_text(text, encoding="utf-8", newline="\n")
    return mods, save


def play(bench, mods, save, name, exe, sets, out):
    """Кадр в начале и после каждого хода, сейв в конце. Стенд гасится при любом исходе."""
    rec = out.setdefault(name, {"seeds": []})
    try:
        lua_mod_check.unlink_all(bench.folder(name))
        a = ["start", "--name", name, "--exe", exe, "--save", str(save), "--mods-dir", str(mods), "--mods", "s3native=true", "--timeout", "120"]
        if sets:
            a += ["--set", sets]
        print(name, (bench.call(*a, timeout=140).strip().splitlines() or ["?"])[-1][:100], flush=True)
        bench.run(name, "wait 2500; key ctrl+289; wait 2500", 40)
        for _ in range(TURNS):
            bench.end_turn(name, 90)
            bench.run(name, "key ctrl+289; wait 2500", 40)
            rec["seeds"].append(re.search(r"seed=(\d+)", bench.run(name, "state", 30)).group(1))
        bench.run(name, "key 286; wait 5000; state", 40)
    except Exception as e:
        rec["error"] = repr(e)[:300]
    finally:
        bench.call("stop", "--name", name, timeout=60)


def battle_part(path):
    text = path.read_text(encoding="utf-8", errors="replace")
    return text[text.index("\nbattleGame:\n"):].splitlines()


def spawned(lines):
    """Появившиеся: те же имена типов, что у яиц; считаем по фракциям в записях юнитов."""
    text = "\n".join(lines)
    units = text[text.index("\n  units:\n"):text.index("\n  items:\n")]
    found = {}
    for m in re.finditer(r"- id: \d+\n(.*?)(?=\n    - id: |\Z)", units, re.S):
        kind = re.search(r"genUnitType: (\S+)", m.group(1))
        side = re.search(r"\n\s+faction: (-?\d+)", m.group(1))
        if kind and kind.group(1) == FOE and side:
            found[side.group(1)] = found.get(side.group(1), 0) + 1
    return found


def compare(a, b, out, k):
    x, y = out[a], out[b]
    check(f"{a}: стенд прошёл", "error" not in x, x.get("error", ""))
    check(f"{b}: стенд прошёл", "error" not in y, y.get("error", ""))
    if "error" in x or "error" in y:
        return
    check(f"{a}: сиды те же", x["seeds"] == y["seeds"], f"{x['seeds']} / {y['seeds']}")
    bench = lua_mod_check.Bench(NEW, HERE)
    pa, pb = bench.folder(a) / "piratez", bench.folder(b) / "piratez"
    dumps = sorted(p.stem for p in pa.glob("hdtest*.json"))
    check(f"{a}: кадров снято", len(dumps) == TURNS + 1, str(dumps))
    for stem in dumps:
        r = subprocess.run(["py", "-3.13", str(ROOT / "tools/hdtest_compare.py"), str(pa / stem), str(pb / stem)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
        d = json.loads((pa / f"{stem}.json").read_text(encoding="utf-8-sig"))
        rows = [l.strip()[:100] for l in r.stdout.splitlines() if re.search(r"\[map\]|\[frame\]|RESULT", l)]
        print(a, stem, "mode", d.get("hdMode"), "k", d.get("k"), rows, flush=True)
        check(f"{a} {stem}: снято при k = {k}", d.get("k") == k, str(d.get("k")))
        check(f"{a} {stem}: кадр совпал", not [l for l in r.stdout.splitlines() if re.search(r"\[(map|frame)\].*DIFF", l)], "; ".join(rows)[:200])
    la, lb = battle_part(pa / "_quick_.asav"), battle_part(pb / "_quick_.asav")
    import difflib
    diff = [l for l in difflib.unified_diff(la, lb, lineterm="", n=0) if l[:1] in "+-" and l[:3] not in ("+++", "---")]
    # такт анимации и звание нейтрала из RNG::seedless не от сборки: контроль этапа 3
    diff = [l for l in diff if not re.search(r"animFrame|_FRAME|rankIntUnified", l)]
    found = spawned(la)
    print(a, "появилось по фракциям:", found, "строк различий:", len(diff), diff[:6], flush=True)
    check(f"{a}: появление всех сторон", all(found.get(s) for s in ("0", "1", "2")), str(found))
    check(f"{a}: те же юниты по фракциям", found == spawned(lb), f"{found} / {spawned(lb)}")
    check(f"{a}: сейв совпал", not diff, str(diff)[:300])


def main():
    started = time.time()
    mods, save = prepare()
    bench = lua_mod_check.Bench(NEW, HERE)
    out = {}
    # настройка масштаба при запуске: стендовое set k=1 в бою масштаб карты не меняет, дамп остаётся k = 4
    cases = (("", "", 4), ("0", "oxceHdMode=0", 4), ("1", "oxceHdMode=0;oxceHdScale=1", 1))
    jobs = [(f"s3n{w}{c}", e, s) for c, s, _k in cases for w, e in (("base", BASE), ("new", NEW))]
    threads = [threading.Thread(target=play, args=(bench, mods, save, n, e, s, out)) for n, e, s in jobs]
    for t in threads:
        t.start()
    for t in threads:
        t.join(LIMIT)
    check("уложились в потолок", not any(t.is_alive() for t in threads) and time.time() - started < LIMIT, f"{time.time() - started:.0f} с")
    for c, _s, k in cases:
        compare(f"s3nbase{c}", f"s3nnew{c}", out, k)
    print(f"итог: {'FAIL ' + str(len(failed)) if failed else 'PASS'}, {time.time() - started:.0f} с", flush=True)
    for f in failed:
        print("  FAIL:", f[:140])
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
