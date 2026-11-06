# Рецепты справки в настоящем бою, всё невидимо. Код берётся из tools/lua_api_doc.py как есть, зонды стоят до него и после него
# в том же main.lua: подписки одного мода идут по порядку записи, чужой мод между ними не вклинится, поэтому моды не мешают друг другу.
# Запуск: py -3.13 recipes.py pirates|ufo|clean
import os, re, shutil, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import lua_api_doc

HERE = Path(os.environ["TEMP"]) / "oxce_lua_recipes"
HERE.mkdir(parents=True, exist_ok=True)
BENCH = str(ROOT / "tools/hdbench.py")
EXE = str(ROOT / "build-release/bin") + "/" + "openxcom" + ".e" + "xe"
SAVE = ROOT / "tools/lua_stage1/lua_battle.sav"
REAL = ROOT / "Пиратки/Dioxine_XPiratez/user/mods"
LOG = open(HERE / f"{sys.argv[1]}.txt", "w", encoding="utf-8-sig")
RECIPES = {r["id"]: r for r in lua_api_doc.RECIPES}
failed = []

HIT = "unit, damaging_item, weapon_item, attacker, battle, skill, orig_power, damaging_type, battle_action, out"
DAMAGE = "unit, damaging_item, weapon_item, attacker, battle, skill, currPower, orig_power, part, side, damaging_type, battle_action, out"
HEAD = 'local shown = 0\nlocal function say(...) shown = shown + 1; if shown <= 60 then game.log("RCP", ...) end end\nlocal before\n'

# id: (до рецепта, после рецепта). Зонд до рецепта создаёт условие, которого мог не дать бой: рану, голову, неполный магазин.
PROBES = {
    "regen": ('game.on("newTurnUnit", function(unit, battle, turn, side)\n'
              '  if side == unit:getFaction() and not unit:isKilled() and not unit:isStunned() and unit:getHealth() > 5 then\n'
              '    unit:addHealth(-3)\n    before = unit:getHealth()\n  else before = nil end\nend)\n',
              'game.on("newTurnUnit", function(unit)\n  if before then say("regen", before, unit:getHealth()) end\nend)\n'),
    "headshot": (f'local n = 0\ngame.on("hitUnit", function({HIT})\n  n = n + 1\n  if n % 2 == 0 then out.part = game.BODYPART_HEAD else out.part = game.BODYPART_TORSO end\n  before = out.power\nend)\n',
                 f'game.on("hitUnit", function({HIT})\n  say("headshot", out.part == game.BODYPART_HEAD and "head" or "other", before, out.power)\nend)\n'),
    "weapon": (f'game.on("hitUnit", function({HIT})\n  before = out.power\nend)\n',
               f'local bare = 0\ngame.on("hitUnit", function({HIT})\n  if not weapon_item then bare = bare + 1 end\n'
               '  if weapon_item or bare <= 5 then say("weapon", weapon_item and "has" or "nil", before, out.power, weapon_item and weapon_item:getRuleItem():getType() or "-") end\nend)\n'),
    "shock": (f'game.on("damageUnit", function({DAMAGE})\n  before = out.to_time\nend)\n',
              f'game.on("damageUnit", function({DAMAGE})\n  if out.to_health > 0 then say("shock", out.to_health, before, out.to_time) end\nend)\n'),
    "rage": (f'game.on("damageUnit", function({DAMAGE})\n  before = unit:getTag("MY_RAGE")\nend)\n'
             'local armed = 0\ngame.on("newTurnUnit", function(unit, battle, turn, side)\n'
             '  if side == unit:getFaction() and armed < 5 and not unit:isKilled() then\n'
             '    armed = armed + 1\n    unit:setTag("MY_RAGE", 2)\n    unit:setMorale(50)\n  end\n'
             '  before = unit:getMorale() .. "/" .. unit:getTag("MY_RAGE") .. "/" .. tostring(side == unit:getFaction())\nend)\n',
             f'game.on("damageUnit", function({DAMAGE})\n  if out.to_health > 0 then say("rage_tag", out.to_health, before, unit:getTag("MY_RAGE")) end\nend)\n'
             'game.on("newTurnUnit", function(unit)\n  if before:sub(1, 3) == "50/" then say("rage_turn", before, unit:getMorale(), unit:getTag("MY_RAGE")) end\nend)\n'),
    "recharge": ('local armed = 0\ngame.on("newTurnItem", function(item, battle, turn, side)\n  before = nil\n'
                 '  if side == game.FACTION_PLAYER and item:isAmmo() and item:getAmmoQuantity() > 3 and armed < 5 then\n'
                 '    armed = armed + 1\n    item:setAmmoQuantity(item:getAmmoQuantity() - 2)\n    before = item:getAmmoQuantity()\n  end\nend)\n',
                 'game.on("newTurnItem", function(item)\n  if before then say("recharge", before, item:getAmmoQuantity(), item:getAmmoQuantityMax(), tostring(item:getOwner())) end\nend)\n'),
    "medikit": ('game.on("healUnit", function(actor, item, battle, target, battle_action, out)\n  before = out.health_recovery\nend)\n',
                'game.on("healUnit", function(actor, item, battle, target, battle_action, out)\n  say("medikit", before, out.health_recovery)\nend)\n'),
    "recovery": ('game.on("returnFromMissionUnit", function(unit, battle, soldier, out)\n  out.recovery_time = out.recovery_time + 9\n  before = out.recovery_time\nend)\n',
                 'game.on("returnFromMissionUnit", function(unit, battle, soldier, out)\n  say("recovery", before, out.recovery_time)\nend)\n'),
}
# Типы оружия боя заранее неизвестны: путь «тип найден» проверяем на любом оружии, остальной код рецепта тот же.
PATCH = {"weapon": ("local BONUS = { STR_PISTOL = 5, STR_RIFLE = 10 }", "local BONUS = setmetatable({}, { __index = function() return 5 end })")}


def check(what, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + what + (f"  [{detail}]" if detail else ""), flush=True)
    if not ok:
        failed.append(what)


def call(*args, timeout=420):
    r = subprocess.run(["py", "-3.13", BENCH, *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    LOG.write(r.stdout + r.stderr)
    LOG.flush()
    return r.stdout


def run(name, script, timeout=60):
    return call("run", "--name", name, "--timeout", str(timeout), script, timeout=timeout + 20)


def state(name):
    m = re.search(r"state (\w+) stack=\S+(?: side=(\w+))?(?: turn=(\d+))?", run(name, "state", 30))
    return m.groups() if m else ("", None, None)


def end_turn(name, limit=240):
    first = int(state(name)[2] or 0)
    run(name, "key 8", 30)
    t0 = time.time()
    top = ""
    while time.time() - t0 < limit:
        time.sleep(1.5)
        top, side, turn = state(name)
        if top == "NextTurnState":
            run(name, "click 160,100", 30)
        elif top in ("InfoboxOKState", "InfoboxState"):
            run(name, "key 13", 30)
        elif top == "BattlescapeState" and side == "player" and int(turn or 0) > first:
            time.sleep(2)
            return
    raise RuntimeError(name + ": the turn did not end, " + top)


def make(mods, rid, master, extra_rul=""):
    r = RECIPES[rid]
    d = mods / ("rcp_" + rid)
    (d / "lua").mkdir(parents=True, exist_ok=True)
    (d / "metadata.yml").write_text(f'id: rcp_{rid}\nname: "rcp {rid}"\nversion: 0.1\nmaster: "{master}"\nluaApi: 1\n', encoding="utf-8", newline="\n")
    code = r["code"]
    if rid in PATCH:
        assert PATCH[rid][0] in code, rid
        code = code.replace(*PATCH[rid])
    first, last = PROBES[rid]
    (d / "lua" / "main.lua").write_text(HEAD + first + code + last, encoding="utf-8", newline="\n")
    if r.get("rul") or extra_rul:
        (d / "Ruleset").mkdir(exist_ok=True)
        (d / "Ruleset" / "my_mod.rul").write_text(r.get("rul", "") + extra_rul, encoding="utf-8", newline="\n")
    return "rcp_" + rid


def rows(name, rid):
    """Строки зонда: [lua] rcp_x: RCP rid a b c"""
    lines = call("log", "--name", name, "-n", "40000", timeout=60).splitlines()
    return [l.split(f"RCP {rid} ", 1)[1].split() for l in lines if f"RCP {rid} " in l]


def errors(name):
    p = Path(os.environ["TEMP"]) / f"oxce_bench_{name}" / "lua_errors.log"
    return p.read_text(encoding="utf-8-sig", errors="replace") if p.exists() else ""


def verify(name, rid, test, what, real=lambda x: True):
    """real отбирает строки, где рецепт и правда сработал: проверка на одних нулях ничего не значит."""
    found = rows(name, rid)
    bad = [x for x in found if not test(x)]
    good = [x for x in found if real(x)]
    check(f"{rid}: {what}", bool(good) and not bad, f"{len(found)} строк, сработал в {len(good)}" + (f", не сошлось {bad[:3]}" if bad else "") + (f", пример {good[0]}" if good else ""))


def pirates():
    mods = HERE / "mods_pirates"
    mods.mkdir(exist_ok=True)
    for d in REAL.iterdir():
        if d.is_dir() and not (mods / d.name).exists():
            subprocess.run(["cmd", "/c", "mklink", "/J", str(mods / d.name), str(d)], check=True, capture_output=True)
    ids = ["regen", "headshot", "weapon", "shock", "rage", "recharge", "recovery"]
    names = [make(mods, rid, "piratez") for rid in ids]
    text = SAVE.read_text(encoding="utf-8")
    text = re.sub(r"(?:  - 'lua_\w+ ver: [^']*'\n)+", "".join(f"  - '{n} ver: 0.1'\n" for n in names), text, count=1)
    save = HERE / "rcp_battle.sav"
    save.write_text(text, encoding="utf-8", newline="\n")
    name = "rcpp"
    a = ["start", "--name", name, "--exe", EXE, "--save", str(save), "--mods-dir", str(mods), "--mods", ";".join(n + "=true" for n in names), "--timeout", "400", "--set", "oxceLuaMods=true"]
    print(name, call(*a).strip().splitlines()[-1][:120], flush=True)
    # настоящий выстрел ИИ приходит не сразу: ждём его, но не дольше 16 ходов
    for t in range(16):
        end_turn(name)
        if t >= 3 and any(x[0] == "has" for x in rows(name, "weapon")):
            break
    print("ходов", t + 1, flush=True)
    run(name, "key 97; wait 1500; state; key 13; wait 15000; state", 120)
    print("после отмены миссии", state(name), flush=True)

    verify(name, "regen", lambda x: int(x[1]) == int(x[0]) + 1, "здоровье +1")
    verify(name, "headshot", lambda x: int(x[2]) == (int(x[1]) * 2 if x[0] == "head" else int(x[1])), "голова вдвое, остальное как было", lambda x: x[0] == "head" and int(x[1]) > 0)
    verify(name, "weapon", lambda x: int(x[2]) == int(x[1]) + (5 if x[0] == "has" else 0), "прибавка только при оружии", lambda x: x[0] == "has")
    verify(name, "shock", lambda x: int(x[2]) == int(x[1]) + (int(x[0]) if int(x[0]) > 0 else 0), "очки времени снимаются вслед за здоровьем", lambda x: int(x[0]) > 0)
    verify(name, "rage_tag", lambda x: int(x[2]) == int(x[1]) + (1 if int(x[0]) > 0 else 0), "тег копит ранения", lambda x: int(x[0]) > 0)
    verify(name, "rage_turn", lambda x: x[0].endswith("/true") is False or (int(x[1]) == 60 and int(x[2]) == 0), "боевой дух +5 на единицу ярости, тег обнулён")
    verify(name, "recharge", lambda x: int(x[1]) == int(x[0]) + 1, "магазин +1")
    verify(name, "recovery", lambda x: int(x[1]) == int(x[0]) // 2, "срок лечения вдвое")
    text = errors(name)
    check("журнал ошибок Lua пуст", not text, text[:500])
    call("stop", "--name", name, timeout=60)


def ufo():
    # аптечку в бою Пираток ИИ не применяет: ванильный UFO, встроенная аптечка, как uiheal этапа 1
    os.environ["OXCE_HIDDEN_DATA"] = str(ROOT / "bin")
    mods = HERE / "mods_ufo"
    mods.mkdir(exist_ok=True)
    rul = """
items:
  - type: STR_MEDI_KIT
    medikitType: 1
    medikitTargetSelf: true
    specialUseEmptyHand: true
armors:
  - type: STR_NONE_UC
    specialWeapon: STR_MEDI_KIT
"""
    mod = make(mods, "medikit", "xcom1", rul)
    name = "rcpu"
    a = ["start", "--name", name, "--exe", EXE, "--save", "", "--master", "xcom1", "--mods-dir", str(mods), "--mods", mod + "=true", "--timeout", "300", "--set", "oxceLuaMods=true;oxceHdMode=0"]
    print(name, call(*a, timeout=320).strip().splitlines()[-1][:120], flush=True)
    run(name, "open battle; wait 4000; state; key 13; wait 2500; key 27; wait 1500; state", 400)
    for _ in range(3):
        run(name, "key 113; wait 1200; state; key 49; wait 1500; state", 40)
        if state(name)[0] != "BattlescapeState":
            run(name, "key 27; wait 800", 30)
    verify(name, "medikit", lambda x: int(x[1]) == int(x[0]) * 2, "лечение вдвое")
    text = errors(name)
    check("UFO: журнал ошибок Lua пуст", not text, text[:500])
    call("stop", "--name", name, timeout=60)


def clean():
    """Сначала снимаем соединения, потом удаляем: rmtree через соединение снёс бы моды установки (R-047)."""
    tmp = Path(os.environ["TEMP"])
    LOG.close()
    for u in [HERE, *tmp.glob("oxce_bench_rcp*")]:
        for top, dirs, _ in os.walk(u):
            for d in list(dirs):
                p = os.path.join(top, d)
                if os.path.isjunction(p):
                    os.rmdir(p)     # только связь; внутрь соединения walk не заходит
                    dirs.remove(d)
        shutil.rmtree(u, ignore_errors=True)
        print(u.name, "убрано" if not u.exists() else "ОСТАЛОСЬ")


try:
    globals()[sys.argv[1]]()
finally:
    print("ИТОГ:", "FAIL " + "; ".join(failed) if failed else "PASS", flush=True)
sys.exit(1 if failed else 0)
