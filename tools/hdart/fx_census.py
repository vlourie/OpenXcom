"""Перепись боевых эффектов X-Piratez: пули, попадания, взрывы, удары.

Что носит урон на дистанции и в ближнем бою, какими кадрами SMOKE/X1/HIT.PCK и
спрайтами Projectiles это рисуется. Разбор - docs/research/combat-fx.md.
Запуск: PYTHONIOENCODING=utf-8 py -3 tools/hdart/fx_census.py -> census/fx_census2.json
"""
import sys, os, glob, collections, json
sys.path.insert(0, r"E:\OpenXCom\tools")
from pck_census import load_yaml

ROOT = r"E:\OpenXCom\Пиратки\Dioxine_XPiratez\user\mods\Piratez"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "census")
items = {}
for p in sorted(glob.glob(os.path.join(ROOT, "Ruleset", "*.rul"))):
    d = load_yaml(p) or {}
    for it in d.get("items", []) or []:
        if not isinstance(it, dict):
            continue
        if "delete" in it:
            items.pop(it["delete"], None); continue
        items.setdefault(it["type"], {}).update(it)

DT = {0: "CHARM", 1: "PIERCING", 2: "BURN", 3: "CONCUSSIVE", 4: "LASER", 5: "PLASMA", 6: "DAZE",
      7: "CUTTING", 8: "CHEM", 9: "CHOKING", 10: "ANTI-E511", 11: "BIO", 12: "ELECTRIC", 13: "EMP",
      14: "WARP", 15: "MIND", 16: "STABBING", 17: "HEAT", 18: "COLD", 19: "DT19"}

def dtype(v):
    if isinstance(v, dict):
        v = v.get("type", v.get("ResistType", 0))
    return int(v or 0)

C = collections.Counter
# ---------- ranged: every item that carries a projectile's damage
ranged = []
for t, it in items.items():
    bt = it.get("battleType", 0)
    if bt not in (1, 2, 4, 5):  # firearm, ammo, grenade, proximity
        continue
    if bt == 1 and it.get("compatibleAmmo") and not it.get("power"):
        continue
    if not it.get("power") and bt != 4:
        continue
    dt = dtype(it.get("damageType", 0))
    alter = it.get("damageAlter") or {}
    radius = alter.get("FixRadius", it.get("blastRadius", -1))
    aoe = (radius or 0) > 0 or (radius == -1 and dt in (2, 3, 9) and bt != 1)
    ranged.append(dict(type=t, bt=bt, dt=dt, bullet=it.get("bulletSprite", -1),
                       hit=it.get("hitAnimation", 0), aoe=bool(aoe) or bt in (4, 5),
                       pellets=it.get("shotgunPellets", 0), arc=bool(it.get("arcingShot"))))

# ---------- melee: battleType 3 with power, plus any item with a second melee mode (meleeType)
# Имя сверяется ПО СЛОВАМ (части между '_'), начало слова: SPIKED_MACE не копьё, BATTLE_AX не дубина.
KIND = [
 ("хлыст/цепь", ["WHIP", "LASH", "FLAIL", "KUSARIGAMA", "NOOSE", "CHAIN", "GRAPPLE", "TENTACLE", "TENTACLES"]),
 ("когти/лапы", ["CLAW", "CLAWS", "TALON", "PAWS", "REAPER", "CHRYSSALID", "RATT", "HYENA", "DOGG", "WEREDOGE", "CHUPACABRA", "SPIDER", "GIANTSPIDER", "MEGASCORPION", "KRAB", "BEETLE", "MAGGOT", "VAMPIRE", "CAT", "TASOTH", "BOOMOSAURUS", "ZOMBIGAL", "WOLVERINE"]),
 ("укус/клюв", ["BITE", "JAW", "FANG", "BEAK", "MAW", "FISH", "SHARK", "ZOMBIE", "VAMPBAT", "DOGE"]),
 ("кулак/пинок/борьба", ["FIST", "FISTO", "FISTY", "SHOCKAFIST", "PUNCH", "KNUCKLES", "GAUNTLET", "KUNG", "PALM", "KICK", "BRAWL", "SLAP", "UNARMED", "WRESTLING", "BAD", "GENTLE", "PEG", "CESTUS", "HANDLE", "GLOVE"]),
 ("жало/игла", ["STING", "NEEDLE", "BEES", "INFECTOR", "SYRINGE", "DRILL"]),
 ("колющее древко", ["SPEAR", "PIKE", "TRIDENT", "LANCE", "IMPALER", "PITCHFORK", "BOATHOOK", "HALBERD", "GLAIVE", "BAYONET", "RAPIER"]),
 ("клинок/топор", ["SWORD", "KNOIF", "KNIFE", "BLADE", "SABER", "SABRE", "CUTLASS", "MACHETE", "KATANA", "WAKIZASHI", "GLADIUS", "DAGGER", "AX", "SCYTHE", "CLEAVER", "CHAINSAW", "SICKLE", "SLICER", "RAZOR", "BILLHOOK", "GARLAND", "SHIV", "MANHACK", "HATCHET"]),
 ("дубина/молот/щит", ["CLUB", "BAT", "BATTO", "MACE", "HAMMER", "BATON", "CROWBAR", "PIPE", "STAFF", "QUARTERSTAFF", "CANE", "MAUL", "STICK", "WRENCH", "ROD", "TONFA", "MORNING", "SLEDGE", "PAN", "SHOVEL", "SCEPTER", "THUNDERSTRIKER", "DISCIPLINER", "ANCHOR", "SIGN", "IV", "ROCK", "PILLOW", "GUITAR", "FLAG", "SHIELD", "PADD", "TORCH", "MAG", "FIRE", "FAN", "SHAWL", "PROD"]),
]
def kind(t, bt):
    words = t.upper().split("_")
    for k, ws in KIND:
        if any(w == x or (len(x) >= 4 and w.startswith(x)) for w in words for x in ws):
            return k
    return "приклад/штык ружья" if bt == 1 else "прочее"

melee = []
for t, it in items.items():
    bt = it.get("battleType", 0)
    if t.startswith("AURA_"):
        continue
    if bt == 3 and it.get("power"):
        dt = dtype(it.get("damageType", 0))
    elif "meleeType" in it or it.get("meleePower"):
        dt = dtype(it.get("meleeType", 0))
    else:
        continue
    melee.append(dict(type=t, dt=dt, anim=it.get("meleeAnimation", 0), kind=kind(t, bt), bt=bt,
                      creature=t.startswith("AUX_") or t.startswith("SPC_")))

res = {
 "items_total": len(items),
 "ranged_n": len(ranged),
 "ranged_aoe_n": sum(r["aoe"] for r in ranged),
 "ranged_direct_n": sum(not r["aoe"] for r in ranged),
 "ranged_dt": {DT[k]: v for k, v in C(r["dt"] for r in ranged).most_common()},
 "direct_hitAnim": dict(C(r["hit"] for r in ranged if not r["aoe"]).most_common()),
 "aoe_hitAnim_X1": dict(C(r["hit"] for r in ranged if r["aoe"]).most_common()),
 "bullet_distinct": len(set(r["bullet"] for r in ranged if r["bullet"] != -1)),
 "beam_or_invisible": sum(1 for r in ranged if r["bullet"] == -1),
 "pellets": sum(1 for r in ranged if (r["pellets"] or 0) > 1),
 "arc": sum(1 for r in ranged if r["arc"]),
 "direct_dt_x_hit": len(set((r["dt"], r["hit"]) for r in ranged if not r["aoe"])),
 "melee_n": len(melee),
 "melee_kind": dict(C(m["kind"] for m in melee).most_common()),
 "melee_dt": {DT[k]: v for k, v in C(m["dt"] for m in melee).most_common()},
 "melee_anim": dict(C(m["anim"] for m in melee).most_common()),
 "melee_creature_n": sum(m["creature"] for m in melee),
 "melee_kind_x_dt": len(set((m["kind"], m["dt"]) for m in melee)),
 "melee_kind_x_anim": {k: dict(C(m["anim"] for m in melee if m["kind"] == k)) for k in set(m["kind"] for m in melee)},
 "other": [m["type"] for m in melee if m["kind"] == "прочее"],
 "dt_by_hit": {str(h): {DT[k]: v for k, v in C(r["dt"] for r in ranged if not r["aoe"] and r["hit"] == h).most_common(4)} for h in sorted(set(r["hit"] for r in ranged if not r["aoe"]))},
 "dt_by_meleeanim": {str(a): {DT[k]: v for k, v in C(m["dt"] for m in melee if m["anim"] == a).most_common(4)} for a in sorted(set(m["anim"] for m in melee))},
}
with open(os.path.join(OUT, "fx_census2.json"), "w", encoding="utf-8-sig") as f:
    json.dump(dict(res, ranged=ranged, melee=melee), f, ensure_ascii=False, indent=1)
for k, v in res.items():
    print(k, ":", v)
