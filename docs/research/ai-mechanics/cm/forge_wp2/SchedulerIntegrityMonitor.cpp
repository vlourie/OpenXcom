/*
 * AI FORGE WP1, WP2 (bench, never in play). See SchedulerIntegrityMonitor.h. The only calls into the generators read their states.
 * Left out of the fingerprint, by design (the report lists them): Pathfinding's caches, sounds and pictures, script values,
 * statistics, the player's interface state (_currentAction), AiProbe's logs and memos.
 */
#include "SchedulerIntegrityMonitor.h"
#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <typeinfo>
#include <vector>
#include <SDL.h>
#include "AIModule.h"
#include "AiProbe.h"
#include "BattlescapeGame.h"
#include "BattleState.h"
#include "../Engine/Logger.h"
#include "../Engine/RNG.h"
#include "../Engine/Timer.h"
#include "../Mod/RuleInventory.h"
#include "../Mod/Armor.h"
#include "../Mod/RuleItem.h"
#include "../Mod/RuleVoiceSet.h"
#include "../Mod/Unit.h"
#include "../Savegame/BattleItem.h"
#include "../Savegame/BattleUnit.h"
#include "../Savegame/Node.h"
#include "../Savegame/SavedBattleGame.h"
#include "../Savegame/Soldier.h"
#include "../Savegame/Tile.h"
#include "TileEngine.h"

namespace OpenXcom
{

namespace SchedulerIntegrityMonitor
{

namespace
{

/// Word by word: this runs over the whole map at every decision.
struct Mix
{
	uint64_t h = 0x9E3779B97F4A7C15ULL;
	void add(long long v)
	{
		h = (h ^ (uint64_t)v) * 0x100000001B3ULL;
		h ^= h >> 29;
	}
	void text(const std::string &s)
	{
		for (char c : s)
		{
			add(c);
		}
	}
	void pos(const Position &p)
	{
		add(p.x); add(p.y); add(p.z);
	}
};

SavedBattleGame *battle = nullptr;
long long eventNo = 0;
uint64_t chain = 0xCBF29CE484222325ULL;
int lastSide = -1;
int lastSelected = -2;
bool fingerprintDue = false;
bool stopping = false;
std::map<int, int> selectedThisSide;
std::set<std::string> boundaries;
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

long long stopAt()
{
	static const long long at = [] { const char *s = getenv("OXCE_AI_FORGE_STOP"); return s ? atoll(s) : 0LL; }();
	return at;
}

const std::set<long long> &dumpAt()
{
	static const std::set<long long> at = []
	{
		std::set<long long> out;
		if (const char *s = getenv("OXCE_AI_FORGE_DUMP"))
		{
			std::istringstream in(s);
			std::string one;
			while (std::getline(in, one, ','))
			{
				out.insert(atoll(one.c_str()));
			}
		}
		return out;
	}();
	return at;
}

std::string hex(uint64_t v)
{
	std::ostringstream s;
	s << std::hex << v;
	return s.str();
}

/// One unit: everything of it the next decision can read, by what the battle holds, not by address.
void unitHash(Mix &m, BattleUnit *bu)
{
	m.add(bu->getId());
	m.text(bu->getType());
	m.add((int)bu->getFaction()); m.add((int)bu->getOriginalFaction()); m.add((int)bu->getStatus());
	m.pos(bu->getPosition()); m.pos(bu->getLastPosition()); m.pos(bu->getDestination());
	m.pos(bu->getTile() ? bu->getTile()->getPosition() : Position(-1, -1, -1));
	m.add(bu->getDirection()); m.add(bu->getToDirection()); m.add(bu->getFaceDirection());
	m.add(bu->getTurretDirection()); m.add(bu->getTurretToDirection()); m.add(bu->getVerticalDirection());
	m.add(bu->getWalkingPhase()); m.add(bu->getFallingPhase()); m.add(bu->getReverseMove());
	m.add(bu->getTimeUnits()); m.add(bu->getEnergy()); m.add(bu->getHealth()); m.add(bu->getMana());
	m.add(bu->getMorale()); m.add(bu->getStunlevel()); m.add(bu->getOverKillDamage()); m.add(bu->getFire());
	m.add(bu->isKneeled()); m.add(bu->isFloating()); m.add(bu->isSurrendering()); m.add(bu->getVisible());
	m.add(bu->reselectAllowed()); m.add(bu->isHiding()); m.add(bu->getCharging() ? bu->getCharging()->getId() : -1);
	m.add(bu->isAiMedikitUsed()); m.add(bu->getRespawn()); m.add(bu->getAlreadyRespawned());
	m.add(bu->getMindControllerId()); m.add(bu->getMurdererId()); m.add(bu->getMotionPoints()); m.add(bu->getScannedTurn());
	m.add(bu->getTurnsSinceSpotted()); m.add(bu->getTurnsLeftSpottedForSnipers()); m.add(bu->getTurnsSinceStunned());
	m.add(bu->getSpotterDuration());
	for (int f = FACTION_PLAYER; f <= FACTION_NEUTRAL; ++f)
	{
		m.add(bu->getTurnsSinceSpottedByFaction((UnitFaction)f));
		m.add(bu->getTurnsLeftSpottedForSnipersByFaction((UnitFaction)f));
	}
	for (int s = 0; s < SIDE_MAX; ++s)
	{
		m.add(bu->getArmor((UnitSide)s));
	}
	for (int p = 0; p < BODYPART_MAX; ++p)
	{
		m.add(bu->getFatalWound((UnitBodyPart)p));
	}
	for (const auto *seen : *bu->getVisibleUnits())
	{
		m.add(seen->getId());
	}
	m.add(-1);
	for (const auto *seen : bu->getUnitsSpottedThisTurn())
	{
		m.add(seen->getId());
	}
}

/// One item by what it is and where, not by id or address (ids may differ between runs of one battle, R-025).
uint64_t itemHash(const BattleItem *it)
{
	Mix m;
	m.text(it->getRules()->getType());
	m.add(it->getOwner() ? it->getOwner()->getId() : -1);
	m.add(it->getPreviousOwner() ? it->getPreviousOwner()->getId() : -1);
	m.add(it->getUnit() ? it->getUnit()->getId() : -1);
	m.text(it->getSlot() ? it->getSlot()->getId() : std::string("-"));
	m.add(it->getSlotX()); m.add(it->getSlotY());
	m.pos(it->getTile() ? it->getTile()->getPosition() : Position(-1, -1, -1));
	m.add(it->getAmmoQuantity()); m.add(it->getFuseTimer()); m.add(it->isFuseEnabled());
	m.add(it->getHealQuantity()); m.add(it->getPainKillerQuantity()); m.add(it->getStimulantQuantity());
	m.add(it->getXCOMProperty());
	for (int slot = 0; slot < RuleItem::AmmoSlotMax; ++slot)
	{
		const BattleItem *ammo = it->getAmmoForSlot(slot);
		m.text(ammo && ammo != it ? ammo->getRules()->getType() : std::string("-"));
		m.add(ammo && ammo != it ? ammo->getAmmoQuantity() : -1);
	}
	return m.h;
}

/// The whole of the state, in sections: which section differs says at once what diverged.
std::string sections(SavedBattleGame *save, std::vector<std::string> *dump)
{
	Mix sched, units, ai, order, ids, map, nodes, bot, derived;
	uint64_t items = 0;
	const BattlescapeGame *game = save->getBattleGame();
	sched.add(save->getTurn()); sched.add((int)save->getSide());
	sched.add(save->getSelectedUnit() ? save->getSelectedUnit()->getId() : -1);
	sched.add((int)save->getTUReserved()); sched.add(save->getKneelReserved()); sched.add(save->getGlobalShade());
	sched.add(save->getBughuntMode()); sched.add(save->isCheating()); sched.add(save->getDebugMode()); sched.add(save->isAborted());
	if (game)
	{
		sched.add(game->getAIActionCounter()); sched.add(game->getPanicHandled());
		sched.add(game->forgeSecondMove()); sched.add(game->forgeAggroSound());
		for (const auto *state : game->getStates())
		{
			sched.text(state ? typeid(*state).name() : "0");
		}
		bot.add(game->forgeGuardedTurn());
		for (int id : game->forgeGuardedUnits())
		{
			bot.add(id);
		}
	}
	bot.add((long long)AiProbe::forgeHash());
	for (auto *bu : *save->getUnits())
	{
		Mix one;
		unitHash(one, bu);
		units.add((long long)one.h);
		const uint64_t oneAi = bu->getAIModule() ? bu->getAIModule()->probeHash() : 0;
		ai.add((long long)oneAi);
		Mix inv;
		for (const auto *it : *bu->getInventory())
		{
			inv.add((long long)itemHash(it));
		}
		order.add((long long)inv.h);
		// what the auxiliary generator gave the unit: the rank scripts can read, the recolour, the look, the voice
		derived.add(bu->forgeRankUnified());
		for (const auto &pair : bu->getRecolor())
		{
			derived.add(pair.first); derived.add(pair.second);
		}
		derived.add(bu->getGeoscapeSoldier() ? bu->getGeoscapeSoldier()->getLookVariant() : -1);
		derived.text(bu->getUnitVoiceSet() ? bu->getUnitVoiceSet()->getType() : std::string("-"));
		if (dump)
		{
			std::ostringstream d;
			const Position p = bu->getPosition();
			d << "u=" << bu->getId() << " type=" << bu->getType() << " fac=" << (int)bu->getFaction() << " st=" << (int)bu->getStatus()
				<< " pos=" << p.x << "," << p.y << "," << p.z << " dir=" << bu->getDirection() << " tu=" << bu->getTimeUnits()
				<< " en=" << bu->getEnergy() << " hp=" << bu->getHealth() << " stun=" << bu->getStunlevel() << " mor=" << bu->getMorale()
				<< " mana=" << bu->getMana() << " fire=" << bu->getFire() << " wounds=" << bu->getFatalWounds()
				<< " noresel=" << (bu->reselectAllowed() ? 0 : 1) << " hide=" << (bu->isHiding() ? 1 : 0)
				<< " charge=" << (bu->getCharging() ? bu->getCharging()->getId() : -1)
				<< " seen=" << bu->getVisibleUnits()->size() << " uh=" << hex(one.h) << " ai=" << hex(oneAi) << " inv=" << hex(inv.h);
			const BattleItem *right = bu->getRightHandWeapon();
			const BattleItem *loaded = right ? right->getAmmoForSlot(0) : nullptr;
			d << " right=" << (right ? right->getRules()->getType() : std::string("-")) << " ammo=" << (loaded ? loaded->getAmmoQuantity() : -1);
			dump->push_back(d.str());
		}
	}
	for (const auto *it : *save->getItems())
	{
		items += itemHash(it);
		ids.add(it->getId());
	}
	const int size = save->getMapSizeXYZ();
	const int perFloor = save->getMapSizeX() * save->getMapSizeY();
	Mix floorHash;
	for (int i = 0; i < size; ++i)
	{
		Tile *tile = save->getTile(i);
		for (int part = O_FLOOR; part < O_MAX; ++part)
		{
			int id = -1, set = -1;
			tile->getMapData(&id, &set, (TilePart)part);
			map.add(id * 256LL + set);
			map.add(tile->isUfoDoorOpen((TilePart)part));
			map.add(tile->isDiscovered((TilePart)part));
		}
		map.add(tile->getFire()); map.add(tile->getSmoke()); map.add(tile->getOverlaps());
		map.add(tile->getExplosive()); map.add(tile->getExplosiveType()); map.add(tile->getDangerous());
		derived.add(tile->getAnimationOffset());
		map.add(tile->getUnit() ? tile->getUnit()->getId() : -1);
		for (int layer = 0; layer < LL_MAX; ++layer)
		{
			map.add(tile->getLight((LightLayers)layer));
		}
		for (const auto *it : *tile->getInventory())
		{
			order.add((long long)itemHash(it));
		}
		if (dump && perFloor > 0 && (i + 1) % perFloor == 0)
		{
			floorHash = map;
			dump->push_back("floor=" + std::to_string(i / perFloor) + " map=" + hex(floorHash.h));
		}
	}
	for (const auto *node : *save->getNodes())
	{
		nodes.add(node->isAllocated());
	}
	std::ostringstream out;
	out << "S=" << hex(sched.h) << " U=" << hex(units.h) << " A=" << hex(ai.h) << " I=" << hex(items) << " O=" << hex(order.h)
		<< " M=" << hex(map.h) << " N=" << hex(nodes.h) << " B=" << hex(bot.h) << " J=" << hex(ids.h)
		<< " R=" << hex(RNG::getSeed()) << " C=" << clockNow() << " L=" << hex(RNG::getSeedlessState()) << " V=" << hex(derived.h);
	return out.str();
}

void write(const std::string &body);

void dumpNow(const char *why)
{
	if (!battle)
	{
		return;
	}
	const uint64_t before = RNG::getSeed();
	std::vector<std::string> lines;
	const std::string all = sections(battle, &lines);
	Log(LOG_INFO) << "[FORGEDUMP] at=" << eventNo << " why=" << why << " " << all;
	for (const auto &line : lines)
	{
		Log(LOG_INFO) << "[FORGEDUMP] at=" << eventNo << " " << line;
	}
	if (RNG::getSeed() != before)
	{
		write("ev=VIOLATION kind=rng_touched where=dump");
	}
}

/// A numbered line of the chain: every line says what the generator holds and hashes all the lines before it.
void write(const std::string &body)
{
	if (stopping)
	{
		return;
	}
	std::ostringstream head;
	head << "n=" << ++eventNo;
	std::ostringstream rest;
	rest << " rng=" << hex(RNG::getSeed()) << " t=" << (battle ? battle->getTurn() : -1)
		<< " s=" << (battle ? (int)battle->getSide() : -1) << " " << body;
	const std::string text = rest.str();
	for (char c : text)
	{
		chain = (chain ^ (unsigned char)c) * 1099511628211ULL;
	}
	Log(LOG_INFO) << "[FORGE] " << head.str() << " h=" << hex(chain) << text;
	if (dumpAt().count(eventNo))
	{
		dumpNow("asked");
	}
	if (stopAt() > 0 && eventNo == stopAt())
	{
		dumpNow("stop");
		stopping = true;
	}
}

/// Side and selection are read, not hooked: nothing has to be added to the engine's own paths of choosing.
void poll()
{
	if (!battle)
	{
		return;
	}
	const int side = (int)battle->getSide();
	if (side != lastSide)
	{
		std::ostringstream s;
		s << "ev=side from=" << lastSide << " to=" << side;
		lastSide = side;
		selectedThisSide.clear();
		fingerprintDue = true;
		write(s.str());
	}
	const BattleUnit *selected = battle->getSelectedUnit();
	const int id = selected ? selected->getId() : -1;
	if (id != lastSelected)
	{
		std::ostringstream s;
		s << "ev=sel unit=" << id << " from=" << lastSelected;
		if (selected)
		{
			s << " again=" << selectedThisSide[id]++ << " noresel=" << (selected->reselectAllowed() ? 0 : 1)
				<< " fac=" << (int)selected->getFaction() << " st=" << (int)selected->getStatus() << " tu=" << selected->getTimeUnits();
		}
		lastSelected = id;
		write(s.str());
	}
}

std::string who(const BattleUnit *unit)
{
	std::ostringstream s;
	s << "unit=" << unit->getId() << " fac=" << (int)unit->getFaction() << " st=" << (int)unit->getStatus()
		<< " tu=" << unit->getTimeUnits() << " noresel=" << (unit->reselectAllowed() ? 0 : 1) << " hide=" << (unit->isHiding() ? 1 : 0);
	return s.str();
}

void emit(const std::string &body)
{
	poll();
	write(body);
}

/// Time units that moved past every hook named so far: said once, at the next fingerprint.
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
	const std::string all = sections(battle, nullptr);
	emit(std::string("ev=fp at=") + at + " " + all);
	if (RNG::getSeed() != before)
	{
		write(std::string("ev=VIOLATION kind=rng_touched where=") + at);
	}
	fingerprintDue = false;
}

/// The first event of each kind on each side gets the full dump: the boundaries a repeat is checked at unit by unit.
void boundary(const std::string &kind)
{
	const std::string key = kind + "." + std::to_string(lastSide);
	if (boundaries.insert(key).second)
	{
		write("ev=boundary kind=" + key);
		dumpNow(key.c_str());
	}
}

}

bool on()
{
	static const bool value = [] { const char *s = getenv("OXCE_AI_FORGE"); return s && *s && *s != '0'; }();
	return value;
}

void frame(SavedBattleGame *save)
{
	if (!on())
	{
		return;
	}
	battle = save;
	poll();
	if (fingerprintDue)
	{
		fingerprint("side");
	}
}

bool stopRequested()
{
	return stopping;
}

void mark(const BattleUnit *unit, bool set, const char *by, int line)
{
	if (!on())
	{
		return;
	}
	std::ostringstream s;
	s << "ev=mark set=" << (set ? 1 : 0) << " was=" << (unit->reselectAllowed() ? 0 : 1) << " by=" << by << ":" << line << " " << who(unit);
	emit(s.str());
}

void hide(const BattleUnit *unit, bool hiding, const char *by, int line)
{
	if (!on())
	{
		return;
	}
	std::ostringstream s;
	s << "ev=hiding set=" << (hiding ? 1 : 0) << " by=" << by << ":" << line << " " << who(unit);
	emit(s.str());
}

void tu(const BattleUnit *unit, int before, int after, const char *kind)
{
	if (!on() || before == after)
	{
		return;
	}
	std::ostringstream s;
	s << "ev=tu kind=" << kind << " was=" << before << " now=" << after << " " << who(unit);
	knownTu[unit->getId()] = after;
	emit(s.str());
}

void tick(SavedBattleGame *save, BattleUnit *unit, int counter, bool second)
{
	if (!on())
	{
		return;
	}
	battle = save;
	const Position p = unit->getPosition();
	std::ostringstream s;
	s << "ev=tick " << who(unit) << " counter=" << counter << " second=" << (second ? 1 : 0)
		<< " pos=" << p.x << "," << p.y << "," << p.z << " hp=" << unit->getHealth() << " en=" << unit->getEnergy();
	emit(s.str());
	if (second)
	{
		boundary("second_pass");
	}
}

void gate(BattleUnit *unit, int counter, int maxActions)
{
	if (!on())
	{
		return;
	}
	std::ostringstream s;
	s << "ev=gate " << who(unit) << " counter=" << counter << " max=" << maxActions << " stunned=" << (unit->getTurnsSinceStunned() == 0 ? 1 : 0);
	emit(s.str());
}

void guard(BattleUnit *unit)
{
	if (!on())
	{
		return;
	}
	emit("ev=guard " + who(unit));
}

void decide(SavedBattleGame *save, BattleUnit *unit, int counter, bool second)
{
	if (!on())
	{
		return;
	}
	battle = save;
	std::ostringstream s;
	s << "ev=decide " << who(unit) << " number=" << counter << " second=" << (second ? 1 : 0) << " d=" << ++decisionNo;
	emit(s.str());
	if (!unit->reselectAllowed())
	{
		write("ev=VIOLATION kind=decide_after_mark " + who(unit));
	}
	fingerprint("decide");
	if (dumpAfterBranch && decisionNo > plan().at)
	{
		// what the planned decision left, unit by unit, whichever way it was taken
		dumpAfterBranch = false;
		dumpNow("after_branch");
	}
}

/// The planned action against the engine's own rules, as they stand now: empty if it may be done; what it knows of the target goes to fair.
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
	if (!on())
	{
		return;
	}
	battle = save;
	std::ostringstream s;
	s << "ev=act " << who(unit) << " type=" << (int)action.type << " to=" << action.target.x << "," << action.target.y << "," << action.target.z
		<< " weapon=" << (action.weapon ? action.weapon->getRules()->getType() : std::string("-"))
		<< " fa=" << (action.finalAction ? 1 : 0) << " run=" << (action.run ? 1 : 0) << " number=" << action.number
		<< " ai=" << hex(unit->getAIModule() ? unit->getAIModule()->probeHash() : 0);
	emit(s.str());
	switch (action.type)
	{
	case BA_WALK: boundary("walk"); break;
	case BA_HIT: boundary("melee"); break;
	case BA_AUTOSHOT: case BA_SNAPSHOT: case BA_AIMEDSHOT: boundary("shot"); break;
	case BA_THROW: boundary("throw"); break;
	case BA_LAUNCH: boundary("launch"); break;
	case BA_PANIC: case BA_MINDCONTROL: boundary("psi"); break;
	case BA_NONE: boundary("none"); break;
	default: boundary("other"); break;
	}
}

void walkEnd(BattleUnit *unit, const BattleAction &action, bool aiBranch)
{
	if (!on())
	{
		return;
	}
	std::ostringstream s;
	s << "ev=walk_end " << who(unit) << " fa=" << (action.finalAction ? 1 : 0) << " ai=" << (aiBranch ? 1 : 0)
		<< " charge=" << (unit->getCharging() ? unit->getCharging()->getId() : -1);
	emit(s.str());
}

void reaction(BattleUnit *reactor, BattleUnit *target)
{
	if (!on())
	{
		return;
	}
	emit("ev=react " + who(reactor) + " target=" + std::to_string(target->getId()));
	boundary("reaction");
}

void panic(BattleUnit *unit)
{
	if (!on())
	{
		return;
	}
	emit("ev=panic " + who(unit));
	boundary("panic");
}

void converted(BattleUnit *from, BattleUnit *to)
{
	if (!on())
	{
		return;
	}
	emit("ev=convert from=" + std::to_string(from->getId()) + " " + who(to) + " type=" + to->getType());
	boundary("convert");
}

void casualty(const BattleUnit *victim, bool dead)
{
	if (!on())
	{
		return;
	}
	emit(std::string("ev=casualty dead=") + (dead ? "1 " : "0 ") + who(victim));
	boundary(dead ? "death" : "stun");
}

void finish(SavedBattleGame *save, const char *how)
{
	if (!on())
	{
		return;
	}
	battle = save;
	fingerprint("end");
	write(std::string("ev=end how=") + how);
	Log(LOG_INFO) << "[FORGETIME] at=end real_ms=" << SDL_GetTicks() << " battle_real_ms=" << (SDL_GetTicks() - battleTicks) << " clock=" << clockNow() << " clock0=" << clockStart;
}

}

}
