"""AI FORGE WP2.1: the isolated tree forge21/tree = forge2/tree (the frozen WP2 tree) with one change of method: think() always runs, the mode of the shot may change after it.
The WP2 tree and exe stay as they are. CRLF kept. Every hook does nothing unless its OXCE_AI_FORGE* variable is set. args: none, or --files for the monitor's files only"""
import shutil
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "forge2"
TREE = HERE / "tree"
FILES_ONLY = "--files" in sys.argv
if not FILES_ONLY:
    if TREE.exists():
        shutil.rmtree(TREE)
    shutil.copytree(SRC / "tree", TREE)
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


# 1. handleAI: think() as in the engine, the arena's point after everything that decides and before anything that carries out
G = "Battlescape/BattlescapeGame.cpp"
sub(G, """	// AI FORGE WP2 (offline arena only, OXCE_AI_FORGE_BRANCH_*): one planned, checked action in place of this one think(). Unset: false at once.
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
""", """	unit->think(&action);

	if (action.type == BA_RETHINK)
	{
		_parentState->debug("Rethink");
		unit->think(&action);
	}

	_AIActionCounter = action.number;
""")
sub(G, """	AiProbe::logDecision(_save, unit, action);
	AiProbe::blockedStepDecide(_save, unit);
""", """	// AI FORGE WP2.1 (offline arena only, OXCE_AI_FORGE_BRANCH_*): think() has run in full and nothing is carried out yet; at the planned decision the state is compared and the mode of the shot may change. Unset: returns at once.
	SchedulerIntegrityMonitor::intervene(_save, unit, &action);
	AiProbe::logDecision(_save, unit, action);
	AiProbe::blockedStepDecide(_save, unit);
""")

# 2. the monitor: from WP2's files
hdr = (SRC / "mon" / "SchedulerIntegrityMonitor.h").read_text(encoding="utf-8").replace("\r\n", "\n")
cpp = (SRC / "mon" / "SchedulerIntegrityMonitor.cpp").read_text(encoding="utf-8").replace("\r\n", "\n")
hdr = subs(hdr, """ * AI FORGE WP2, the offline arena: OXCE_AI_FORGE_BRANCH_AT=<decision> with OXCE_AI_FORGE_BRANCH_MODE:
 *   observe - the dump at that decision, think() as ever; stop - the dump, then the run ends;
 *   act - one action in place of that decision's think(): OXCE_AI_FORGE_BRANCH_UNIT, _TYPE, _TO=x.y.z, _WEAPON, _CHAIN=<the chain's value it must find>,
 *   checked by the engine's own rules and refused (think() as ever, a VIOLATION line) if anything does not hold. Never in the living AI.
 */
""", """ * AI FORGE WP2.1, the offline arena: OXCE_AI_FORGE_BRANCH_AT=<decision> with OXCE_AI_FORGE_BRANCH_MODE:
 *   think() always runs in full; after it, before anything is carried out:
 *   observe - the state and the action are written, nothing else; act - also the mode of the shot becomes OXCE_AI_FORGE_BRANCH_TYPE, if think() chose
 *   OXCE_AI_FORGE_BRANCH_FROM at _TO=x.y.z with _WEAPON by _UNIT, the state is the expected one (_CHAIN, _STATE, when given) and the engine's own rules allow it;
 *   otherwise a VIOLATION line and the action stays. These lines stay out of the chain, so a run that changes nothing keeps its chain. Never in the living AI.
 */
""", "h")
hdr = subs(hdr, """/// The arena's point, just before think(): true if the planned action now stands in *action and think() is not to run.
bool branch(SavedBattleGame *save, BattleUnit *unit, BattleAction *action);
""", """/// The arena's point, after think() and before the action is carried out: see above.
void intervene(SavedBattleGame *save, BattleUnit *unit, BattleAction *action);
""", "h")
cpp = subs(cpp, """ * AI FORGE WP1, WP2 (bench, never in play). See SchedulerIntegrityMonitor.h.""", """ * AI FORGE WP1, WP2, WP2.1 (bench, never in play). See SchedulerIntegrityMonitor.h.""", "cpp")
cpp = subs(cpp, """#include "AIModule.h"
""", """#include "AIModule.h"
#include "ForgeLegal.h"
""", "cpp")
cpp = subs(cpp, """	std::string mode, weapon, chain;
	int unit = -1, type = 0;
""", """	std::string mode, weapon, chain, state;
	int unit = -1, type = 0, from = 0;
""", "cpp")
cpp = subs(cpp, """		p.chain = text("OXCE_AI_FORGE_BRANCH_CHAIN");
""", """		p.chain = text("OXCE_AI_FORGE_BRANCH_CHAIN");
		p.state = text("OXCE_AI_FORGE_BRANCH_STATE");
		p.from = atoi(text("OXCE_AI_FORGE_BRANCH_FROM").c_str());
""", "cpp")
# what the state hashes hold becomes readable where the first effects of a shot are looked for
cpp = subs(cpp, """			d << " right=" << (right ? right->getRules()->getType() : std::string("-")) << " ammo=" << (loaded ? loaded->getAmmoQuantity() : -1);
""", """			d << " right=" << (right ? right->getRules()->getType() : std::string("-")) << " ammo=" << (loaded ? loaded->getAmmoQuantity() : -1);
			d << " kneel=" << (bu->isKneeled() ? 1 : 0) << " armor=" << bu->getArmor(SIDE_FRONT) << "," << bu->getArmor(SIDE_LEFT) << "," << bu->getArmor(SIDE_RIGHT) << "," << bu->getArmor(SIDE_REAR) << "," << bu->getArmor(SIDE_UNDER);
			d << " overkill=" << bu->getOverKillDamage() << " motion=" << bu->getMotionPoints() << " tss=" << bu->getTurnsSinceSpotted() << " tsu=" << bu->getTurnsSinceStunned();
			d << " vis=";
			for (const auto *seen : *bu->getVisibleUnits())
			{
				d << seen->getId() << ",";
			}
			d << "- spot=";
			for (const auto *seen : bu->getUnitsSpottedThisTurn())
			{
				d << seen->getId() << ",";
			}
			d << "-";
""", "cpp")
cpp = subs(cpp, """		dumpAfterBranch = false;
		dumpNow("after_branch");
""", """		dumpAfterBranch = false;
		dumpNow("after_branch");
		tilesSince();
""", "cpp")
# the tiles: before decide(), which calls tilesSince
cpp = subs(cpp, """/// A numbered line of the chain:""", """/// One tile as plain values, what the map hash holds of it.
std::string tileText(Tile *tile)
{
	std::ostringstream s;
	s << "p:";
	for (int part = O_FLOOR; part < O_MAX; ++part)
	{
		int id = -1, set = -1;
		tile->getMapData(&id, &set, (TilePart)part);
		s << id << "." << set << "." << (tile->isUfoDoorOpen((TilePart)part) ? 1 : 0) << "." << (tile->isDiscovered((TilePart)part) ? 1 : 0) << "/";
	}
	s << ",f:" << tile->getFire() << ",s:" << tile->getSmoke() << ",o:" << tile->getOverlaps() << ",e:" << tile->getExplosive() << "." << tile->getExplosiveType()
		<< ",g:" << tile->getDangerous() << ",u:" << (tile->getUnit() ? tile->getUnit()->getId() : -1) << ",l:";
	for (int layer = 0; layer < LL_MAX; ++layer)
	{
		s << tile->getLight((LightLayers)layer) << "/";
	}
	return s.str();
}

std::vector<std::string> tilesAtIntervention;

void rememberTiles()
{
	tilesAtIntervention.clear();
	for (int i = 0; i < battle->getMapSizeXYZ(); ++i)
	{
		tilesAtIntervention.push_back(tileText(battle->getTile(i)));
	}
}

/// What changed on the map since the intervention, tile by tile: the map hash only says that something did.
void tilesSince()
{
	int changed = 0;
	for (int i = 0; i < (int)tilesAtIntervention.size(); ++i)
	{
		const std::string now = tileText(battle->getTile(i));
		if (now != tilesAtIntervention[i] && ++changed <= 300)
		{
			const Position p = battle->getTile(i)->getPosition();
			Log(LOG_INFO) << "[FORGEDUMP] at=" << eventNo << " tile=" << p.x << "," << p.y << "," << p.z << " was=" << tilesAtIntervention[i] << " now=" << now;
		}
	}
	Log(LOG_INFO) << "[FORGEDUMP] at=" << eventNo << " tiles_changed=" << changed;
}

/// A numbered line of the chain:""", "cpp")
start = cpp.index("/// The planned action against the engine's own rules")
end = cpp.index("void act(SavedBattleGame *save, BattleUnit *unit, const BattleAction &action)")
cpp = cpp[:start] + """/// The action as think() left it, field by field: all of it enters the state that must match.
static std::string actionText(const BattleAction &a)
{
	std::ostringstream s;
	s << "actor=" << (a.actor ? a.actor->getId() : -1) << " type=" << (int)a.type << " to=" << a.target.x << "," << a.target.y << "," << a.target.z
		<< " weapon=" << (a.weapon ? a.weapon->getRules()->getType() : std::string("-")) << " time=" << a.Time << " energy=" << a.Energy << " morale=" << a.Morale
		<< " health=" << a.Health << " stun=" << a.Stun << " mana=" << a.Mana << " number=" << a.number << " kneel=" << (a.kneel ? 1 : 0) << " run=" << (a.run ? 1 : 0)
		<< " strafe=" << (a.strafe ? 1 : 0) << " sneak=" << (a.sneak ? 1 : 0) << " ignoreSpotted=" << (a.ignoreSpottedEnemies ? 1 : 0) << " desperate=" << (a.desperate ? 1 : 0)
		<< " facing=" << a.finalFacing << " final=" << (a.finalAction ? 1 : 0) << " value=" << a.value << " diff=" << a.diff << " autoShot=" << a.autoShotCounter
		<< " spray=" << (a.sprayTargeting ? 1 : 0) << " waypoints=" << a.waypoints.size() << " targeting=" << (a.targeting ? 1 : 0)
		<< " origin=" << (int)a.relativeOrigin << " meleePart=" << a.terrainMeleeTilePart << " result=" << (a.result.empty() ? "-" : a.result);
	return s.str();
}

/// think()'s own rule for the kneel of an attack (AIModule::think, AI_COMBAT).
static bool kneelOf(const BattleUnit *unit, int type)
{
	const bool kneelDefault = AiProbe::careful(unit) && unit->getType() == "SOLDIER";
	return (type == BA_AIMEDSHOT || type == BA_AUTOSHOT) && unit->getArmor()->allowsKneeling(kneelDefault);
}

/// Reads the facts of ForgeLegal through the engine's own rules. The rest stays false if an earlier fact leaves nothing to read.
static ForgeLegal::Facts factsOf(SavedBattleGame *save, BattleUnit *unit, const BattleAction &action, int type, const Position &to)
{
	ForgeLegal::Facts f;
	const BranchPlan &p = plan();
	f.sameUnit = unit->getId() == p.unit && action.actor == unit;
	f.planned = action.type == p.from;
	f.sameTarget = action.target == p.to;
	f.sameWeapon = action.weapon && action.weapon->getRules()->getType() == p.weapon;
	f.unitFree = save->getSide() == unit->getFaction() && !unit->isOut() && !unit->isOutThresholdExceed() && unit->reselectAllowed();
	f.isShot = type == BA_AUTOSHOT || type == BA_SNAPSHOT || type == BA_AIMEDSHOT;
	f.kneelByRule = action.kneel == kneelOf(unit, action.type);
	BattleItem *weapon = action.weapon;
	if (!weapon || !f.isShot)
	{
		return f;
	}
	f.weaponHeld = weapon == unit->getRightHandWeapon() || weapon == unit->getLeftHandWeapon() || weapon == unit->getSpecialWeapon(BT_FIREARM);
	const BattleActionType mode = (BattleActionType)type;
	BattleActionCost cost(mode, unit, weapon);
	f.costTime = cost.Time;
	f.needsAmmo = weapon->needsAmmoForAction(mode);
	f.hasAmmo = static_cast<const BattleItem*>(weapon)->getAmmoForAction(mode) != nullptr;
	f.haveTU = cost.haveTU();
	Tile *tile = save->getTile(to);
	BattleUnit *target = tile ? tile->getUnit() : nullptr;
	f.enemyThere = target && !target->isOut() && target->getFaction() != unit->getFaction();
	if (!f.enemyThere)
	{
		return f;
	}
	// what it may know: seen by itself, or by its side no longer ago than its intelligence (as AIModule counts them)
	const auto &seen = *unit->getVisibleUnits();
	f.seen = std::find(seen.begin(), seen.end(), target) != seen.end();
	f.spotted = target->getTurnsSinceSpottedByFaction(unit->getFaction()) <= unit->getIntelligence();
	f.inRange = !weapon->getRules()->isOutOfRange(unit->distance3dToPositionSq(to));
	BattleAction aim;
	aim.type = mode;
	aim.actor = unit;
	aim.weapon = weapon;
	aim.target = to;
	Position origin = save->getTileEngine()->getOriginVoxel(aim, nullptr);
	Position scan;
	f.lineOfFire = save->getTileEngine()->canTargetUnit(&origin, tile, &scan, unit, false);
	return f;
}

/// The rules on real objects, cases that are never carried out: other modes and other targets at this very decision. A hidden unit is looked up for this line only.
static void legalProbes(SavedBattleGame *save, BattleUnit *unit, const BattleAction &action)
{
	const auto one = [&](const char *name, int type, const Position &to)
	{
		ForgeLegal::Facts f = factsOf(save, unit, action, type, to);
		f.stateSame = f.sameUnit = f.planned = f.sameTarget = f.sameWeapon = true;
		const char *fair = "";
		const char *why = ForgeLegal::refusal(f, fair);
		Log(LOG_INFO) << "[FORGELEGAL] case=" << name << " type=" << type << " to=" << to.x << "," << to.y << "," << to.z << " why=" << (why[0] ? why : "legal") << " fair=" << (fair[0] ? fair : "-") << " time=" << f.costTime;
	};
	const Position at = plan().to;
	one("auto", BA_AUTOSHOT, at);
	one("snap", BA_SNAPSHOT, at);
	one("aimed", BA_AIMEDSHOT, at);
	one("melee", BA_HIT, at);
	one("throw", BA_THROW, at);
	one("walk", BA_WALK, at);
	one("psi", BA_PANIC, at);
	one("own_tile", BA_SNAPSHOT, unit->getPosition());
	for (int i = 0; i < save->getMapSizeXYZ(); ++i)
	{
		if (!save->getTile(i)->getUnit())
		{
			one("empty_tile", BA_SNAPSHOT, save->getTile(i)->getPosition());
			break;
		}
	}
	const auto &seen = *unit->getVisibleUnits();
	const BattleUnit *hidden = nullptr;
	for (const auto *bu : *save->getUnits())
	{
		if (!bu->isOut() && bu->getTile() && bu->getFaction() != unit->getFaction() && std::find(seen.begin(), seen.end(), bu) == seen.end()
			&& bu->getTurnsSinceSpottedByFaction(unit->getFaction()) > unit->getIntelligence())
		{
			hidden = bu;
			break;
		}
	}
	if (hidden)
	{
		one("hidden_enemy", BA_SNAPSHOT, hidden->getPosition());
	}
	else
	{
		Log(LOG_INFO) << "[FORGELEGAL] case=hidden_enemy why=none_on_this_map";
	}
}

void intervene(SavedBattleGame *save, BattleUnit *unit, BattleAction *action)
{
	if (!on() || plan().at == 0 || decisionNo != plan().at || dumpAfterBranch)
	{
		return;
	}
	const BranchPlan &p = plan();
	battle = save;
	clockNow();
	const uint64_t before = RNG::getSeed();
	const std::string text = actionText(*action);
	Mix whole;
	whole.text(sections(save, nullptr));
	whole.text(text);
	Log(LOG_INFO) << "[FORGETIME] at=intervene d=" << decisionNo << " real_ms=" << SDL_GetTicks() << " battle_real_ms=" << (SDL_GetTicks() - battleTicks) << " clock0=" << clockStart;
	Log(LOG_INFO) << "[FORGEBRANCH] d=" << decisionNo << " phase=pre mode=" << p.mode << " chain=" << hex(chain) << " state=" << hex(whole.h) << " rng=" << hex(before) << " " << text;
	dumpNow("intervene");
	rememberTiles();
	dumpAfterBranch = true;
	if (p.mode != "act")
	{
		return;
	}
	ForgeLegal::Facts facts = factsOf(save, unit, *action, p.type, p.to);
	facts.stateSame = (p.chain.empty() || p.chain == hex(chain)) && (p.state.empty() || p.state == hex(whole.h));
	const char *fair = "";
	const std::string why = ForgeLegal::refusal(facts, fair);
	legalProbes(save, unit, *action);
	if (!why.empty())
	{
		write("ev=VIOLATION kind=branch_refused why=" + why + " " + who(unit));
		return;
	}
	const int timeBefore = action->Time;
	const int kneelBefore = action->kneel ? 1 : 0;
	const int fromType = (int)action->type;
	action->type = (BattleActionType)p.type;
	action->kneel = kneelOf(unit, p.type);
	action->updateTU();
	Log(LOG_INFO) << "[FORGEBRANCH] d=" << decisionNo << " phase=post from=" << fromType << " to=" << p.type << " fair=" << fair << " time_before=" << timeBefore << " time_after=" << action->Time
		<< " kneel_before=" << kneelBefore << " kneel_after=" << (action->kneel ? 1 : 0) << " rng=" << hex(RNG::getSeed()) << " " << actionText(*action);
	if (RNG::getSeed() != before)
	{
		write("ev=VIOLATION kind=rng_touched where=intervene");
	}
}

""" + cpp[end:]
(HERE / "mon" / "SchedulerIntegrityMonitor.h").write_text(hdr, encoding="utf-8")
(HERE / "mon" / "SchedulerIntegrityMonitor.cpp").write_text(cpp, encoding="utf-8")
for f, t in (("SchedulerIntegrityMonitor.h", hdr), ("SchedulerIntegrityMonitor.cpp", cpp)):
    (root / "Battlescape" / f).write_bytes(t.replace("\n", "\r\n").encode("utf-8"))
shutil.copy2(HERE / "ForgeLegal.h", root / "Battlescape" / "ForgeLegal.h")
print("tree ready", TREE)
