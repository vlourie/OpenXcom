"""AI FORGE WP4: the isolated tree forge4/tree = forge3/tree (the frozen WP3 tree) plus: the arena may carry out another attack in place of the shot think() chose (another target, a blow, a psi attack),
through the engine's own list of candidates and its own rules; a horizon at the side's next turn, where the run ends. Only the monitor's files and one setter in AIModule.h.
WP3's tree and exe stay as they are. CRLF kept in the tree. Everything here does nothing unless OXCE_AI_FORGE_BRANCH_* is set."""
import shutil
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "forge3"
TREE = HERE / "tree"
if TREE.exists():
    shutil.rmtree(TREE)
shutil.copytree(SRC / "tree", TREE)
root = TREE / "src"
(HERE / "mon").mkdir(exist_ok=True)


def subs(text, old, new):
    assert text.count(old) == 1, (old[:70], text.count(old))
    return text.replace(old, new)


hdr = (SRC / "mon" / "SchedulerIntegrityMonitor.h").read_text(encoding="utf-8").replace("\r\n", "\n")
cpp = (SRC / "mon" / "SchedulerIntegrityMonitor.cpp").read_text(encoding="utf-8").replace("\r\n", "\n")

hdr = subs(hdr, """ *   Dumps with the tiles counted by kind: after_branch (the next decision), round0 and round1 (the first decision of turns t+1 and t+2), end.
 */
""", """ *   Dumps with the tiles counted by kind: after_branch (the next decision), round0 and round1 (the first decision of turns t+1 and t+2), end.
 * AI FORGE WP4, the same arena: _NEWTO=x.y.z, _NEWWEAPON, _NEWUNIT: the action becomes _TYPE by that weapon at that unit's tile, if the engine's own list of candidates holds exactly it and the rules allow it.
 *   _STOPSIDE=1: a dump at the first decision of the same side on a later turn (next_side), and the run ends there, or once a further turn has begun without one.
 */
""")
cpp = subs(cpp, " * AI FORGE WP1, WP2, WP2.1, WP3 (bench, never in play).", " * AI FORGE WP1, WP2, WP2.1, WP3, WP4 (bench, never in play).")
cpp = subs(cpp, '#include "AIModule.h"\n', '#include "AIModule.h"\n#include "AiCandidates.h"\n')
cpp = subs(cpp, """bool roundDone[2] = { false, false };
""", """bool roundDone[2] = { false, false };
int branchSide = -1;
bool nextSideDone = false;
""")
cpp = subs(cpp, """	std::string mode, weapon, chain, state;
	int unit = -1, type = 0, from = 0;
	Position to = Position(-1, -1, -1);
};
""", """	std::string mode, weapon, chain, state, newWeapon;
	int unit = -1, type = 0, from = 0, newUnit = -1;
	Position to = Position(-1, -1, -1), newTo = Position(-1, -1, -1);
	bool stopSide = false;
};
""")
cpp = subs(cpp, """		p.to = Position(x, y, z);
		return p;
""", """		p.to = Position(x, y, z);
		x = y = z = -1;
		sscanf(text("OXCE_AI_FORGE_BRANCH_NEWTO").c_str(), "%d.%d.%d", &x, &y, &z);
		p.newTo = Position(x, y, z);
		p.newWeapon = text("OXCE_AI_FORGE_BRANCH_NEWWEAPON");
		p.newUnit = atoi(text("OXCE_AI_FORGE_BRANCH_NEWUNIT").c_str());
		p.stopSide = text("OXCE_AI_FORGE_BRANCH_STOPSIDE") == "1";
		return p;
""")
# the next turn of the side: what the action left when the side comes to act again; a line of the chain, then nothing more is written
cpp = subs(cpp, """				roundDone[k] = true;
				horizon(names[k]);
			}
		}
	}
}
""", """				roundDone[k] = true;
				horizon(names[k]);
			}
		}
		if (plan().stopSide && !nextSideDone)
		{
			const bool sideAgain = (int)save->getSide() == branchSide && save->getTurn() > branchTurn;
			if (sideAgain || save->getTurn() > branchTurn + 1)
			{
				nextSideDone = true;
				if (sideAgain)
				{
					horizon("next_side");
				}
				write(std::string("ev=stop why=") + (sideAgain ? "next_side" : "no_decision_of_the_side"));
				stopping = true;
			}
		}
	}
}
""")
# the facts: of an attack by any weapon the plan names
start = cpp.index("/// Reads the facts of ForgeLegal through the engine's own rules.")
end = cpp.index("void act(SavedBattleGame *save, BattleUnit *unit, const BattleAction &action)")
cpp = cpp[:start] + """/// The weapon of that name, looked for where AiCandidates looks for an attack's weapon.
static BattleItem *weaponNamed(BattleUnit *unit, const std::string &name)
{
	BattleItem *held[5] = { unit->getRightHandWeapon(), unit->getLeftHandWeapon(), unit->getSpecialWeapon(BT_FIREARM), unit->getSpecialWeapon(BT_MELEE), unit->getSpecialWeapon(BT_PSIAMP) };
	for (BattleItem *item : held)
	{
		if (item && item->getRules()->getType() == name)
		{
			return item;
		}
	}
	return nullptr;
}

/// Does the engine's own list hold exactly this action, with a line of fire or a reach? Without the moves: nothing is asked of the pathfinder between a decision and its action.
static bool inEngineList(SavedBattleGame *save, BattleUnit *unit, int type, const Position &to, int targetId, const std::string &weapon, int cost)
{
	const AiCandidates::Set set = AiCandidates::generate(save, unit, false);
	for (const AiCandidates::Candidate &c : set.acts)
	{
		if (c.kind == AiCandidates::ATTACK && c.type == type && c.tile == to && c.target == targetId && c.weapon == weapon)
		{
			return c.lof == 1 && c.tu == cost;
		}
	}
	return false;
}

/// Reads the facts of ForgeLegal through the engine's own rules. The rest stays false if an earlier fact leaves nothing to read.
static ForgeLegal::Facts factsOf(SavedBattleGame *save, BattleUnit *unit, const BattleAction &action, int type, const Position &to, BattleItem *weapon)
{
	ForgeLegal::Facts f;
	const BranchPlan &p = plan();
	f.sameUnit = unit->getId() == p.unit && action.actor == unit;
	f.planned = action.type == p.from;
	f.sameTarget = action.target == p.to;
	f.sameWeapon = action.weapon && action.weapon->getRules()->getType() == p.weapon;
	f.unitFree = save->getSide() == unit->getFaction() && !unit->isOut() && !unit->isOutThresholdExceed() && unit->reselectAllowed();
	const bool isShot = type == BA_AUTOSHOT || type == BA_SNAPSHOT || type == BA_AIMEDSHOT;
	const bool isPsi = type == BA_PANIC || type == BA_MINDCONTROL;
	f.isAttack = isShot || type == BA_HIT || isPsi;
	f.kneelByRule = action.kneel == kneelOf(unit, action.type);
	if (!weapon || !f.isAttack)
	{
		return f;
	}
	f.weaponHeld = weaponNamed(unit, weapon->getRules()->getType()) == weapon;
	const BattleActionType mode = (BattleActionType)type;
	BattleActionCost cost(mode, unit, weapon);
	f.costTime = cost.Time;
	f.needsAmmo = weapon->needsAmmoForAction(mode);
	f.hasAmmo = static_cast<const BattleItem*>(weapon)->getAmmoForAction(mode) != nullptr;
	f.haveTU = cost.haveTU();
	f.useDelayOver = save->getTurn() >= weapon->getRules()->getAIUseDelay(save->getMod());
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
	TileEngine *te = save->getTileEngine();
	if (type == BA_HIT)
	{
		f.inRange = true;
		f.lineOfFire = te->validMeleeRange(unit, target, te->getDirectionTo(unit->getPosition(), target->getPosition()));
	}
	else if (isPsi)
	{
		// as the psi of a player goes through primaryAction and the AI's through psiAction; psiAttackCalculate is left out: it draws from the game's generator
		f.inRange = !weapon->getRules()->isOutOfRange(unit->distance3dToUnitSq(target));
		f.lineOfFire = !weapon->getRules()->isLOSRequired() || AiProbe::upstreamSees(unit, target, 0);
		f.targetAllowed = unit->getAIModule() && unit->getAIModule()->validTarget(target, true, false)
			&& weapon->getRules()->isTargetAllowed(target->getFaction(), unit->getFaction())
			&& unit->getOriginalFaction() == unit->getFaction() && target->getOriginalFaction() != unit->getFaction() && target->getArmor()->getSize() == 1
			&& !(type == BA_PANIC && target->getUnitRules() && !target->getUnitRules()->canPanic())
			&& !(type == BA_MINDCONTROL && target->getUnitRules() && !target->getUnitRules()->canBeMindControlled());
	}
	else
	{
		f.inRange = !weapon->getRules()->isOutOfRange(unit->distance3dToPositionSq(to));
		BattleAction aim;
		aim.type = mode;
		aim.actor = unit;
		aim.weapon = weapon;
		aim.target = to;
		Position origin = te->getOriginVoxel(aim, nullptr);
		Position scan;
		f.lineOfFire = te->canTargetUnit(&origin, tile, &scan, unit, false);
	}
	f.inList = inEngineList(save, unit, type, to, target->getId(), weapon->getRules()->getType(), f.costTime);
	return f;
}

/// The rules on real objects, cases that are never carried out: other actions and other targets at this very decision. A hidden unit is looked up for this line only.
static void legalProbes(SavedBattleGame *save, BattleUnit *unit, const BattleAction &action)
{
	const auto one = [&](const char *name, int type, const Position &to, BattleItem *weapon)
	{
		ForgeLegal::Facts f = factsOf(save, unit, action, type, to, weapon);
		f.sameUnit = f.planned = f.sameTarget = f.sameWeapon = true;
		const char *fair = "";
		const char *why = ForgeLegal::refusal(f, fair);
		Log(LOG_INFO) << "[FORGELEGAL] case=" << name << " type=" << type << " to=" << to.x << "," << to.y << "," << to.z << " weapon=" << (weapon ? weapon->getRules()->getType() : std::string("-")) << " why=" << (why[0] ? why : "legal") << " fair=" << (fair[0] ? fair : "-") << " time=" << f.costTime;
	};
	const Position at = plan().to;
	BattleItem *gun = action.weapon;
	BattleItem *melee = unit->getSpecialWeapon(BT_MELEE);
	BattleItem *psi = unit->getSpecialWeapon(BT_PSIAMP);
	one("auto", BA_AUTOSHOT, at, gun);
	one("snap", BA_SNAPSHOT, at, gun);
	one("aimed", BA_AIMEDSHOT, at, gun);
	one("butt", BA_HIT, at, gun);
	one("melee", BA_HIT, at, melee);
	one("panic", BA_PANIC, at, psi);
	one("mindcontrol", BA_MINDCONTROL, at, psi);
	one("throw", BA_THROW, at, gun);
	one("walk", BA_WALK, at, gun);
	one("own_tile", BA_SNAPSHOT, unit->getPosition(), gun);
	for (int i = 0; i < save->getMapSizeXYZ(); ++i)
	{
		if (!save->getTile(i)->getUnit())
		{
			one("empty_tile", BA_SNAPSHOT, save->getTile(i)->getPosition(), gun);
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
		one("hidden_enemy", BA_SNAPSHOT, hidden->getPosition(), gun);
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
	Log(LOG_INFO) << "[FORGETIME] at=intervene d=" << decisionNo << " turn=" << save->getTurn() << " real_ms=" << SDL_GetTicks() << " battle_real_ms=" << (SDL_GetTicks() - battleTicks) << " clock0=" << clockStart;
	Log(LOG_INFO) << "[FORGEBRANCH] d=" << decisionNo << " phase=pre mode=" << p.mode << " chain=" << hex(chain) << " state=" << hex(whole.h) << " rng=" << hex(before) << " " << text;
	dumpNow("intervene");
	rememberTiles();
	dumpAfterBranch = true;
	branchTurn = save->getTurn();
	branchSide = (int)save->getSide();
	if (p.mode != "act")
	{
		return;
	}
	BattleItem *weapon = weaponNamed(unit, p.newWeapon);
	const ForgeLegal::Facts facts = factsOf(save, unit, *action, p.type, p.newTo, weapon);
	const char *fair = "";
	const std::string why = ForgeLegal::refusal(facts, fair);
	Tile *newTile = save->getTile(p.newTo);
	const BattleUnit *newTarget = newTile ? newTile->getUnit() : nullptr;
	legalProbes(save, unit, *action);
	if (why.empty() && (!newTarget || newTarget->getId() != p.newUnit))
	{
		write("ev=VIOLATION kind=branch_refused why=another_unit_on_the_tile " + who(unit));
		return;
	}
	if (!why.empty())
	{
		write("ev=VIOLATION kind=branch_refused why=" + why + " " + who(unit));
		return;
	}
	const int timeBefore = action->Time;
	const int kneelBefore = action->kneel ? 1 : 0;
	const int fromType = (int)action->type;
	action->type = (BattleActionType)p.type;
	action->target = p.newTo;
	action->weapon = weapon;
	action->kneel = kneelOf(unit, p.type);
	// think()'s own side effect of a psi attack: it does not try another at its next decision. Its number -= 1 is left out: the shot this stands in for was counted, so no action is added.
	if ((p.type == BA_PANIC || p.type == BA_MINDCONTROL) && unit->getAIModule())
	{
		unit->getAIModule()->forgeDidPsi();
	}
	action->updateTU();
	Log(LOG_INFO) << "[FORGEBRANCH] d=" << decisionNo << " phase=post from=" << fromType << " to=" << p.type << " fair=" << fair << " time_before=" << timeBefore << " time_after=" << action->Time
		<< " kneel_before=" << kneelBefore << " kneel_after=" << (action->kneel ? 1 : 0) << " rng=" << hex(RNG::getSeed()) << " " << actionText(*action);
	if (RNG::getSeed() != before)
	{
		write("ev=VIOLATION kind=rng_touched where=intervene");
		return;
	}
	// WP3: the new state of the game RNG, the same in both branches of a pair; nothing above read it
	if (const char *reseed = getenv("OXCE_AI_FORGE_RESEED"))
	{
		const uint64_t seed = strtoull(reseed, nullptr, 10);
		if (seed == 0)
		{
			write("ev=VIOLATION kind=reseed_zero " + who(unit));
			return;
		}
		RNG::setSeed(seed);
		Log(LOG_INFO) << "[FORGEBRANCH] d=" << decisionNo << " phase=reseed seed=" << seed << " was=" << hex(before) << " now=" << hex(RNG::getSeed());
	}
}

""" + cpp[end:]
(HERE / "mon" / "SchedulerIntegrityMonitor.h").write_text(hdr, encoding="utf-8")
(HERE / "mon" / "SchedulerIntegrityMonitor.cpp").write_text(cpp, encoding="utf-8")
for f, t in (("SchedulerIntegrityMonitor.h", hdr), ("SchedulerIntegrityMonitor.cpp", cpp)):
    (root / "Battlescape" / f).write_bytes(t.replace("\n", "\r\n").encode("utf-8"))
(root / "Battlescape" / "ForgeLegal.h").write_bytes((HERE / "ForgeLegal.h").read_text(encoding="utf-8").replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8"))
aih = (root / "Battlescape" / "AIModule.h").read_bytes().decode("utf-8")
line = "\tbool validTarget(BattleUnit* target, bool assessDanger, bool includeCivs) const;"
assert aih.count(line) == 1
aih = aih.replace(line, line + "\r\n\t/// AI FORGE WP4 (offline arena only): the mark think() leaves after a psi attack.\r\n\tvoid forgeDidPsi() { _didPsi = true; }")
(root / "Battlescape" / "AIModule.h").write_bytes(aih.encode("utf-8"))
print("tree ready", TREE)
