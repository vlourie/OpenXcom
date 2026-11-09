"""AI FORGE WP2: the isolated tree forge2/tree = forge/tree (the frozen WP1 tree) + the arena. The WP1 tree and exe stay as they are. CRLF kept.
Every hook does nothing unless its OXCE_AI_FORGE* variable is set. args: none"""
import shutil
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "forge" / "tree"
TREE = HERE / "tree"
FILES_ONLY = "--files" in sys.argv  # the monitor's two files only: nothing else is touched, the build stays incremental
if not FILES_ONLY:
    if TREE.exists():
        shutil.rmtree(TREE)
    shutil.copytree(SRC, TREE)
root = TREE / "src"
(HERE / "mon").mkdir(exist_ok=True)


def subs(text, old, new, name):
    crlf = "\r\n" in text
    if crlf:
        old = old.replace("\n", "\r\n")
        new = new.replace("\n", "\r\n")
    assert text.count(old) == 1, (name, old[:70], text.count(old))
    return text.replace(old, new)


def sub(path, old, new):
    if FILES_ONLY:
        return
    p = root / path
    b = p.read_bytes().decode("utf-8", errors="surrogateescape")
    p.write_bytes(subs(b, old, new, path).encode("utf-8", errors="surrogateescape"))


# 1. the auxiliary generator: a fixed start under the arena's variable, its state readable. Unset: by time and address, as ever
sub("Engine/RNG.h", "	int seedless(int min, int max);\n", "	int seedless(int min, int max);\n	/// AI FORGE WP2 (bench): what the auxiliary generator holds, for the fingerprint.\n	uint64_t getSeedlessState();\n")
sub("Engine/RNG.cpp", """RandomState x_seedless;
""", """RandomState x_seedless;

/**
 * AI FORGE WP2 (offline arena only): OXCE_AI_FORGE_SEEDLESS=<number> fixes where the auxiliary generator starts. Unset: nothing changes.
 */
const bool x_seedlessForge = []
{
	const char *s = getenv("OXCE_AI_FORGE_SEEDLESS");
	if (s && *s)
	{
		x_seedless = RandomState(strtoull(s, nullptr, 10));
	}
	return true;
}();
""")
sub("Engine/RNG.cpp", """int seedless(int min, int max)
""", """uint64_t getSeedlessState()
{
	return x_seedless.getSeed();
}

int seedless(int min, int max)
""")
rng = (root / "Engine/RNG.cpp").read_bytes().decode("utf-8", errors="surrogateescape")
if "<cstdlib>" not in rng and not FILES_ONLY:
    first = rng.index("#include")
    (root / "Engine/RNG.cpp").write_bytes((rng[:first] + "#include <cstdlib>\r\n" + rng[first:]).encode("utf-8", errors="surrogateescape"))

# 2. the causes of the unit's time units
U = "Savegame/BattleUnit.cpp"
sub(U, """		setValueMax(_tu, - std::get<toTime>(args.data), 0, _stats.tu);
""", """		const int tuBeforeDamage = _tu;
		setValueMax(_tu, - std::get<toTime>(args.data), 0, _stats.tu);
		SchedulerIntegrityMonitor::tu(this, tuBeforeDamage, _tu, "damage");
""")
sub(U, """		// Add to previous turn TU, if regen is less than normal unit need couple of turns to regen full bar
		setValueMax(_tu, tu, 0, getBaseStats()->tu);
""", """		const int tuBeforeRecovery = _tu;
		// Add to previous turn TU, if regen is less than normal unit need couple of turns to regen full bar
		setValueMax(_tu, tu, 0, getBaseStats()->tu);
""")
sub(U, """		_tu -= (_tu * ((_fatalWounds[BODYPART_LEFTLEG]+_fatalWounds[BODYPART_RIGHTLEG]) * 10))/100;

		setValueMax(_tu, 0, 0, getBaseStats()->tu);
""", """		_tu -= (_tu * ((_fatalWounds[BODYPART_LEFTLEG]+_fatalWounds[BODYPART_RIGHTLEG]) * 10))/100;

		setValueMax(_tu, 0, 0, getBaseStats()->tu);
		SchedulerIntegrityMonitor::tu(this, tuBeforeRecovery, _tu, "recover");
""")
sub(U, """void BattleUnit::resetTimeUnitsAndEnergy()
{
	_tu = _stats.tu;
""", """void BattleUnit::resetTimeUnitsAndEnergy()
{
	SchedulerIntegrityMonitor::tu(this, _tu, _stats.tu, "reset");
	_tu = _stats.tu;
""")
sub(U, """void setBaseStatScript(BattleUnit *bu, int val)
{
	if (bu)
	{
		(bu->*StatCurr) = Clamp(val, - NegativeLimitMult * (bu->getBaseStats()->*StatMax), +(bu->getBaseStats()->*StatMax));
	}
""", """void setBaseStatScript(BattleUnit *bu, int val)
{
	if (bu)
	{
		const int before = bu->*StatCurr;
		(bu->*StatCurr) = Clamp(val, - NegativeLimitMult * (bu->getBaseStats()->*StatMax), +(bu->getBaseStats()->*StatMax));
		if constexpr (StatCurr == BattleUnit::forgeTimeUnits())
		{
			SchedulerIntegrityMonitor::tu(bu, before, bu->*StatCurr, "script");
		}
	}
""")
H = "Savegame/BattleUnit.h"
sub(H, "	const RuleVoiceSet* getUnitVoiceSet() const { return _unitVoiceSet; }\n", """	const RuleVoiceSet* getUnitVoiceSet() const { return _unitVoiceSet; }
	/// AI FORGE WP2: which member the scripts' time units setter writes; the auxiliary generator's rank for the scripts.
	static constexpr int BattleUnit::* forgeTimeUnits() { return &BattleUnit::_tu; }
	int forgeRankUnified() const { return _rankIntUnified; }
""")

# 3. the arena's point in handleAI: the decision is taken instead of think() only when the plan says so
G = "Battlescape/BattlescapeGame.cpp"
sub(G, """	unit->think(&action);

	if (action.type == BA_RETHINK)
	{
		_parentState->debug("Rethink");
		unit->think(&action);
	}

	_AIActionCounter = action.number;
""", """	// AI FORGE WP2 (offline arena only, OXCE_AI_FORGE_BRANCH_*): one planned, checked action in place of this one think(). Unset: false at once.
	if (!SchedulerIntegrityMonitor::branch(_save, unit, &action))
	{
		unit->think(&action);

		if (action.type == BA_RETHINK)
		{
			_parentState->debug("Rethink");
			unit->think(&action);
		}
	}

	_AIActionCounter = action.number;
""")
sub("Battlescape/AiProbe.cpp", """			if (v.compare(0, 8, "OXCE_AI_") == 0 && !skip.count(name) && (harness() || !play() || ai3Env(name.c_str())))
""", """			if (v.compare(0, 8, "OXCE_AI_") == 0 && v.compare(0, 13, "OXCE_AI_FORGE") != 0 && !skip.count(name) && (harness() || !play() || ai3Env(name.c_str())))
""")

# 4. the monitor: from WP1's files
hdr = (HERE.parent / "forge" / "mon" / "SchedulerIntegrityMonitor.h").read_text(encoding="utf-8").replace("\r\n", "\n")
cpp = (HERE.parent / "forge" / "mon" / "SchedulerIntegrityMonitor.cpp").read_text(encoding="utf-8").replace("\r\n", "\n")
hdr = subs(hdr, """ * OXCE_AI_FORGE_DUMP=n,n,..: the full dump at these events. OXCE_AI_FORGE_STOP=n: the fingerprint and dump at event n, the run ends.
 */
""", """ * OXCE_AI_FORGE_DUMP=n,n,..: the full dump at these events. OXCE_AI_FORGE_STOP=n: the fingerprint and dump at event n, the run ends.
 * AI FORGE WP2, the offline arena: OXCE_AI_FORGE_BRANCH_AT=<decision> with OXCE_AI_FORGE_BRANCH_MODE:
 *   observe - the dump at that decision, think() as ever; stop - the dump, then the run ends;
 *   act - one action in place of that decision's think(): OXCE_AI_FORGE_BRANCH_UNIT, _TYPE, _TO=x.y.z, _WEAPON, _CHAIN=<the chain's value it must find>,
 *   checked by the engine's own rules and refused (think() as ever, a VIOLATION line) if anything does not hold. Never in the living AI.
 */
""", "h")
hdr = subs(hdr, """/// What think() and the steps after it decided, before it is carried out.
""", """/// The arena's point, just before think(): true if the planned action now stands in *action and think() is not to run.
bool branch(SavedBattleGame *save, BattleUnit *unit, BattleAction *action);
/// What think() and the steps after it decided, before it is carried out.
""", "h")
cpp = subs(cpp, """ * AI FORGE WP1 (bench, never in play). See SchedulerIntegrityMonitor.h. Read only: the only call into the generator is RNG::getSeed.
 * Left out of the fingerprint, by design (the report lists them): Pathfinding's caches, the auxiliary generator RNG::seedless,
 * sounds and pictures, script values, statistics, the player's interface state (_currentAction), AiProbe's logs and memos.
""", """ * AI FORGE WP1, WP2 (bench, never in play). See SchedulerIntegrityMonitor.h. The only calls into the generators read their states.
 * Left out of the fingerprint, by design (the report lists them): Pathfinding's caches, sounds and pictures, script values,
 * statistics, the player's interface state (_currentAction), AiProbe's logs and memos.
""", "cpp")
cpp = subs(cpp, '''#include <vector>
#include "AIModule.h"
''', '''#include <vector>
#include <SDL.h>
#include "AIModule.h"
''', "cpp")
cpp = subs(cpp, '''#include "../Mod/RuleItem.h"
''', '''#include "../Mod/Armor.h"
#include "../Mod/RuleItem.h"
#include "../Mod/RuleVoiceSet.h"
''', "cpp")
cpp = subs(cpp, '''#include "../Savegame/SavedBattleGame.h"
''', '''#include "../Savegame/SavedBattleGame.h"
#include "../Savegame/Soldier.h"
''', "cpp")
cpp = subs(cpp, '''#include "../Savegame/Tile.h"
''', '''#include "../Savegame/Tile.h"
#include "TileEngine.h"
''', "cpp")
cpp = subs(cpp, """std::set<std::string> boundaries;
""", """std::set<std::string> boundaries;
long long decisionNo = 0;
bool dumpAfterBranch = false;
long long clockStart = -1;
Uint32 battleTicks = 0;
std::map<int, int> knownTu;

/// The virtual clock from its first reading: where it starts depends on the real time spent before the battle and stays out of the chain ([FORGETIME]).
long long clockNow()
{
	if (clockStart < 0)
	{
		clockStart = Timer::probeTicks;
		battleTicks = SDL_GetTicks();
		Log(LOG_INFO) << "[FORGETIME] at=first clock0=" << clockStart << " real_ms=" << battleTicks;
	}
	return (long long)Timer::probeTicks - clockStart;
}

struct BranchPlan
{
	long long at = 0;
	std::string mode, weapon, chain;
	int unit = -1, type = 0;
	Position to = Position(-1, -1, -1);
};

const BranchPlan &plan()
{
	static const BranchPlan value = []
	{
		BranchPlan p;
		const auto text = [](const char *name) { const char *s = getenv(name); return std::string(s ? s : ""); };
		p.at = atoll(text("OXCE_AI_FORGE_BRANCH_AT").c_str());
		p.mode = text("OXCE_AI_FORGE_BRANCH_MODE");
		p.unit = atoi(text("OXCE_AI_FORGE_BRANCH_UNIT").c_str());
		p.type = atoi(text("OXCE_AI_FORGE_BRANCH_TYPE").c_str());
		p.weapon = text("OXCE_AI_FORGE_BRANCH_WEAPON");
		p.chain = text("OXCE_AI_FORGE_BRANCH_CHAIN");
		int x = -1, y = -1, z = -1;
		sscanf(text("OXCE_AI_FORGE_BRANCH_TO").c_str(), "%d.%d.%d", &x, &y, &z);
		p.to = Position(x, y, z);
		return p;
	}();
	return value;
}
""", "cpp")
cpp = subs(cpp, """				<< " seen=" << bu->getVisibleUnits()->size() << " uh=" << hex(one.h) << " ai=" << hex(oneAi) << " inv=" << hex(inv.h);
""", """				<< " seen=" << bu->getVisibleUnits()->size() << " uh=" << hex(one.h) << " ai=" << hex(oneAi) << " inv=" << hex(inv.h);
			const BattleItem *right = bu->getRightHandWeapon();
			const BattleItem *loaded = right ? right->getAmmoForSlot(0) : nullptr;
			d << " right=" << (right ? right->getRules()->getType() : std::string("-")) << " ammo=" << (loaded ? loaded->getAmmoQuantity() : -1);
""", "cpp")
cpp = subs(cpp, """	Mix sched, units, ai, order, ids, map, nodes, bot;
""", """	Mix sched, units, ai, order, ids, map, nodes, bot, derived;
""", "cpp")
cpp = subs(cpp, """		order.add((long long)inv.h);
		if (dump)
""", """		order.add((long long)inv.h);
		// what the auxiliary generator gave the unit: the rank scripts can read, the recolour, the look, the voice
		derived.add(bu->forgeRankUnified());
		for (const auto &pair : bu->getRecolor())
		{
			derived.add(pair.first); derived.add(pair.second);
		}
		derived.add(bu->getGeoscapeSoldier() ? bu->getGeoscapeSoldier()->getLookVariant() : -1);
		derived.text(bu->getUnitVoiceSet() ? bu->getUnitVoiceSet()->getType() : std::string("-"));
		if (dump)
""", "cpp")
cpp = subs(cpp, """		map.add(tile->getExplosive()); map.add(tile->getExplosiveType()); map.add(tile->getDangerous());
""", """		map.add(tile->getExplosive()); map.add(tile->getExplosiveType()); map.add(tile->getDangerous());
		derived.add(tile->getAnimationOffset());
""", "cpp")
cpp = subs(cpp, """		<< " R=" << hex(RNG::getSeed()) << " C=" << Timer::probeTicks;
""", """		<< " R=" << hex(RNG::getSeed()) << " C=" << clockNow() << " L=" << hex(RNG::getSeedlessState()) << " V=" << hex(derived.h);
""", "cpp")
cpp = subs(cpp, """void fingerprint(const char *at)
{
	if (!battle)
	{
		return;
	}
	const uint64_t before = RNG::getSeed();
""", """/// Time units that moved past every hook named so far: said once, at the next fingerprint.
void scanTu()
{
	for (const auto *bu : *battle->getUnits())
	{
		const int now = bu->getTimeUnits();
		const auto it = knownTu.find(bu->getId());
		if (it == knownTu.end())
		{
			knownTu[bu->getId()] = now;
		}
		else if (it->second != now)
		{
			std::ostringstream s;
			s << "ev=tu kind=untraced was=" << it->second << " now=" << now << " " << who(bu);
			it->second = now;
			emit(s.str());
		}
	}
}

void fingerprint(const char *at)
{
	if (!battle)
	{
		return;
	}
	scanTu();
	const uint64_t before = RNG::getSeed();
""", "cpp")
# who() must be known to scanTu
who_block = """std::string who(const BattleUnit *unit)
{
	std::ostringstream s;
	s << "unit=" << unit->getId() << " fac=" << (int)unit->getFaction() << " st=" << (int)unit->getStatus()
		<< " tu=" << unit->getTimeUnits() << " noresel=" << (unit->reselectAllowed() ? 0 : 1) << " hide=" << (unit->isHiding() ? 1 : 0);
	return s.str();
}

"""
cpp = subs(cpp, who_block, "", "cpp")
cpp = subs(cpp, """void emit(const std::string &body)
{
""", who_block + """void emit(const std::string &body)
{
""", "cpp")
cpp = subs(cpp, """	s << "ev=tu kind=" << kind << " was=" << before << " now=" << after << " " << who(unit);
	emit(s.str());
""", """	s << "ev=tu kind=" << kind << " was=" << before << " now=" << after << " " << who(unit);
	knownTu[unit->getId()] = after;
	emit(s.str());
""", "cpp")
cpp = subs(cpp, """	s << "ev=decide " << who(unit) << " number=" << counter << " second=" << (second ? 1 : 0);
""", """	s << "ev=decide " << who(unit) << " number=" << counter << " second=" << (second ? 1 : 0) << " d=" << ++decisionNo;
""", "cpp")
cpp = subs(cpp, """	fingerprint("decide");
}
""", """	fingerprint("decide");
	if (dumpAfterBranch && decisionNo > plan().at)
	{
		// what the planned decision left, unit by unit, whichever way it was taken
		dumpAfterBranch = false;
		dumpNow("after_branch");
	}
}
""", "cpp")
cpp = subs(cpp, """void act(SavedBattleGame *save, BattleUnit *unit, const BattleAction &action)
{
""", """/// The planned action against the engine's own rules, as they stand now: empty if it may be done; what it knows of the target goes to fair.
static std::string refusal(SavedBattleGame *save, BattleUnit *unit, const BranchPlan &p, BattleItem *&weapon, std::string &fair)
{
	if (unit->getId() != p.unit) return "another_unit";
	if (save->getSide() != unit->getFaction() || unit->isOut() || unit->isOutThresholdExceed() || !unit->reselectAllowed()) return "unit_cannot_act";
	if (p.type != BA_AUTOSHOT && p.type != BA_SNAPSHOT && p.type != BA_AIMEDSHOT) return "not_a_shot";
	const BattleActionType type = (BattleActionType)p.type;
	for (BattleItem *held : { unit->getRightHandWeapon(), unit->getLeftHandWeapon(), unit->getSpecialWeapon(BT_FIREARM) })
	{
		if (held && held->getRules()->getType() == p.weapon)
		{
			weapon = held;
			break;
		}
	}
	if (!weapon) return "weapon_not_held";
	BattleActionCost cost(type, unit, weapon);
	if (cost.Time <= 0) return "no_such_mode";
	if (weapon->needsAmmoForAction(type) && !static_cast<const BattleItem*>(weapon)->getAmmoForAction(type)) return "no_ammo";
	if (!cost.haveTU()) return "no_time_units";
	Tile *tile = save->getTile(p.to);
	BattleUnit *target = tile ? tile->getUnit() : nullptr;
	if (!target || target->isOut() || target->getFaction() == unit->getFaction()) return "no_enemy_there";
	// what it may know: seen by itself, or by its side no longer ago than its intelligence (as AIModule counts them)
	const auto &seen = *unit->getVisibleUnits();
	if (std::find(seen.begin(), seen.end(), target) != seen.end()) fair = "seen";
	else if (target->getTurnsSinceSpottedByFaction(unit->getFaction()) <= unit->getIntelligence()) fair = "spotted";
	else return "target_not_known";
	if (weapon->getRules()->isOutOfRange(unit->distance3dToPositionSq(p.to))) return "out_of_range";
	BattleAction aim;
	aim.type = type;
	aim.actor = unit;
	aim.weapon = weapon;
	aim.target = p.to;
	Position origin = save->getTileEngine()->getOriginVoxel(aim, nullptr);
	Position scan;
	if (!save->getTileEngine()->canTargetUnit(&origin, tile, &scan, unit, false)) return "no_line_of_fire";
	return "";
}

bool branch(SavedBattleGame *save, BattleUnit *unit, BattleAction *action)
{
	if (!on() || plan().at == 0 || decisionNo != plan().at)
	{
		return false;
	}
	const BranchPlan &p = plan();
	battle = save;
	clockNow();
	Log(LOG_INFO) << "[FORGETIME] at=branch d=" << decisionNo << " real_ms=" << SDL_GetTicks() << " battle_real_ms=" << (SDL_GetTicks() - battleTicks) << " clock0=" << clockStart;
	Log(LOG_INFO) << "[FORGEBRANCH] d=" << decisionNo << " mode=" << p.mode << " chain=" << hex(chain) << " unit=" << unit->getId();
	dumpNow("branch");
	dumpAfterBranch = true;
	if (p.mode == "stop")
	{
		stopping = true;
		return false;
	}
	if (p.mode != "act")
	{
		return false;
	}
	const uint64_t before = RNG::getSeed();
	std::string why, fair;
	BattleItem *weapon = nullptr;
	if (!p.chain.empty() && p.chain != hex(chain))
	{
		why = "state_differs";
	}
	else
	{
		why = refusal(save, unit, p, weapon, fair);
	}
	if (RNG::getSeed() != before)
	{
		write("ev=VIOLATION kind=rng_touched where=branch");
		why = "rng_touched";
	}
	if (!why.empty())
	{
		write("ev=VIOLATION kind=branch_refused why=" + why + " " + who(unit));
		return false;
	}
	action->type = (BattleActionType)p.type;
	action->actor = unit;
	action->weapon = weapon;
	action->target = p.to;
	// as think() fills an attack in
	const bool kneelDefault = AiProbe::careful(unit) && unit->getType() == "SOLDIER";
	action->kneel = (p.type == BA_AIMEDSHOT || p.type == BA_AUTOSHOT) && unit->getArmor()->allowsKneeling(kneelDefault);
	action->updateTU();
	std::ostringstream s;
	s << "ev=branch " << who(unit) << " type=" << p.type << " to=" << p.to.x << "," << p.to.y << "," << p.to.z << " weapon=" << p.weapon
		<< " target=" << save->getTile(p.to)->getUnit()->getId() << " fair=" << fair << " time=" << action->Time << " kneel=" << (action->kneel ? 1 : 0);
	emit(s.str());
	return true;
}

void act(SavedBattleGame *save, BattleUnit *unit, const BattleAction &action)
{
""", "cpp")
cpp = subs(cpp, """	battle = save;
	fingerprint("end");
	write(std::string("ev=end how=") + how);
""", """	battle = save;
	fingerprint("end");
	write(std::string("ev=end how=") + how);
	Log(LOG_INFO) << "[FORGETIME] at=end real_ms=" << SDL_GetTicks() << " battle_real_ms=" << (SDL_GetTicks() - battleTicks) << " clock=" << clockNow() << " clock0=" << clockStart;
""", "cpp")
cpp = subs(cpp, """#include <cstdint>
""", """#include <algorithm>
#include <cstdint>
#include <cstdio>
""", "cpp")
(HERE / "mon" / "SchedulerIntegrityMonitor.h").write_text(hdr, encoding="utf-8")
(HERE / "mon" / "SchedulerIntegrityMonitor.cpp").write_text(cpp, encoding="utf-8")
for f, t in (("SchedulerIntegrityMonitor.h", hdr), ("SchedulerIntegrityMonitor.cpp", cpp)):
    (root / "Battlescape" / f).write_bytes(t.replace("\n", "\r\n").encode("utf-8"))
print("tree ready", TREE)
