/*
 * Copyright 2010-2026 OpenXcom Developers.
 *
 * This file is part of OpenXcom.
 *
 * OpenXcom is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * OpenXcom is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with OpenXcom.  If not, see <http://www.gnu.org/licenses/>.
 */
#include "AiProbe.h"
#include <algorithm>
#include <climits>
#include <cmath>
#include <cstdlib>
#include <map>
#include <memory>
#include <set>
#include <sstream>
#include <typeinfo>
#include "AiCandidates.h"
#include "AIModule.h"
#include "BattleState.h"
#include "BattlescapeGame.h"
#include "BattlescapeState.h"
#include "Pathfinding.h"
#include "../Engine/Game.h"
#include "../Engine/Logger.h"
#include "../Engine/RNG.h"
#include "../Engine/Timer.h"
#include "../Mod/Armor.h"
#include "../Mod/RuleInventory.h"
#include "../Mod/RuleItem.h"
#include "../Savegame/BattleItem.h"
#include "../Savegame/BattleUnit.h"
#include "../Savegame/SavedBattleGame.h"
#include "../Savegame/SavedGame.h"
#include "../Savegame/Tile.h"
#include "TileEngine.h"

#ifdef _WIN32
#define PROBE_ENVIRON _environ
#else
extern char **environ;
#define PROBE_ENVIRON environ
#endif

namespace OpenXcom
{

namespace AiProbe
{

#ifndef OXCE_AI_DEV

// a release build: the bench is not compiled in, every entry point does nothing
bool active() { return false; }
bool fast() { return false; }
bool lightSkip(const TileEngine *, const BattleUnit *) { return false; }
bool botTurn(const SavedBattleGame *) { return false; }
long long battleSeed() { return -1; }
void think(BattlescapeState *, SavedBattleGame *) {}
void battleOver(BattlescapeState *, SavedBattleGame *, bool) {}
void beforeThink(SavedBattleGame *, BattleUnit *) {}
void logDecision(SavedBattleGame *, BattleUnit *, const BattleAction &) {}
void logState(SavedBattleGame *, const char *) {}
bool tactics(const BattleUnit *) { return false; }
bool careful(const BattleUnit *) { return false; }
bool evalFire(const BattleUnit *) { return false; }
bool pickUp(const BattleUnit *) { return false; }
bool watchPoint(SavedBattleGame *, const BattleUnit *, Position &) { return false; }
bool halfWalk(SavedBattleGame *, const BattleUnit *) { return false; }
int closeEnemies(SavedBattleGame *, const BattleUnit *, const Position &) { return 0; }
bool revive(SavedBattleGame *, BattleUnit *, BattleAction *, const std::vector<int> &) { return false; }
int turretsSeeing(SavedBattleGame *, BattleUnit *, const Position &) { return 0; }
bool flee(SavedBattleGame *, BattleUnit *, BattleAction *, const std::vector<int> &) { return false; }
int maxActions(const BattleUnit *) { return 2; }
double param(const char *, double def) { return def; }
void tally(const BattleUnit *, const char *) {}
void note(const BattleUnit *, const char *) {}
void propose(const BattleUnit *, char, const char *, int, const BattleAction &) {}
void chosen(const BattleUnit *, char) {}
void modeOdds(const BattleUnit *, int, int, int, int, int, int) {}
void traceTile(const BattleUnit *, const char *, const Position &, int) {}
void walkPlanned(SavedBattleGame *, BattleUnit *, bool, bool) {}
void walkStop(const BattleUnit *, const char *, const Position &, int, int, int, int, int) {}
bool patrolOutOfEnergy(SavedBattleGame *, BattleUnit *, const BattleAction &, bool) { return false; }
int firepointPathOver(SavedBattleGame *, const BattleUnit *, int, int) { return 0; }
void firepointDropped(const BattleUnit *, int, int) {}
void sideEnds(SavedBattleGame *) {}
void logCasualty(SavedBattleGame *, const BattleUnit *, const BattleUnit *, const std::string &, bool, int, bool) {}

#else

namespace
{

bool envOn(const char *name)
{
	const char *s = getenv(name);
	return s && *s && *s != '0';
}

/// Lighting recalculations on a unit's step - done and skipped (lightSkip), for the [AILIGHT] line of the result.
int lightRecalc = 0, lightSkipped = 0;

/// Does the AI play the player's side too (OXCE_AI_BOT)?
bool bot()
{
	static const bool on = active() && envOn("OXCE_AI_BOT");
	return on;
}

/// AI turns to play before quitting (OXCE_AI_PROBE_TURNS, default 1; for the bot the turn cap, default 60).
int turnsWanted()
{
	const char *s = getenv("OXCE_AI_PROBE_TURNS");
	const int n = s ? atoi(s) : 0;
	return n > 0 ? n : (bot() ? 60 : 1);
}

enum Phase { WAIT_PLAYER, AI_PLAYING, FINISHED };
Phase phase = WAIT_PLAYER;
int turnsPlayed = 0;
int turnAtEnd = 0;
int aiStartLogged = -1;
int playerStartLogged = -1;
Uint32 startTicks = 0, startVirtual = 0;
bool started = false;
/// health of every unit when the probe started: the battle may begin with soldiers already hurt
std::map<int, int> startHealth;
/// decisions per side: [side][0] moves, [side][1] attacks (shots, throws, melee)
int decided[3][2] = {};
/// uses of the tactical rules: "h.cover", "p.pullback"...
std::map<std::string, int> tallies;
/// the decision record's reason trail (defined with the record below)
void addTrail(const BattleUnit *unit, const char *what);
/// is the decision record on (defined with the record below)
bool record();
/// did the faction last see an enemy on this tile (defined with the sightings below)
bool lastSeenAt(int faction, const Position &pos);
/// the decision record at a new side's turn and at the end of the battle (defined with the record below)
void recordTurn(SavedBattleGame *save);
void recordEnd(SavedBattleGame *save);

void logStart(SavedBattleGame *save)
{
	started = true;
	startTicks = SDL_GetTicks();
	startVirtual = Timer::probeTicks;
	for (const auto *bu : *save->getUnits())
	{
		startHealth[bu->getId()] = bu->getHealth();
	}
	Log(LOG_INFO) << "[AIPROBE] start: turn " << save->getTurn() << ", mission " << save->getMissionType()
		<< (bot() ? ", bot plays the player, turn cap " : ", AI turns to play ") << turnsWanted();
	logState(save, "before");
}

/// The line the statistics are made of: who is left on each side, what it cost the player.
void logResult(SavedBattleGame *save, const char *how)
{
	int pUnits = 0, pDead = 0, pOut = 0, pWounded = 0, pHpLost = 0;
	int hUnits = 0, hDead = 0, hOut = 0;
	for (const auto *bu : *save->getUnits())
	{
		// the battle ends before the last casualty falls: health 0 is dead, stun over health is out
		const bool dead = bu->getStatus() == STATUS_DEAD || bu->getHealth() <= 0;
		const bool out = !dead && (bu->getStatus() == STATUS_UNCONSCIOUS || bu->getStunlevel() >= bu->getHealth());
		if (bu->getOriginalFaction() == FACTION_PLAYER)
		{
			++pUnits;
			auto was = startHealth.find(bu->getId());
			const int lost = (was != startHealth.end() ? was->second : bu->getBaseStats()->health) - std::max(0, bu->getHealth());
			pDead += dead;
			pOut += out;
			pWounded += lost > 0 || bu->getFatalWounds() > 0;
			pHpLost += lost > 0 ? lost : 0;
		}
		else if (bu->getOriginalFaction() == FACTION_HOSTILE)
		{
			++hUnits;
			hDead += dead;
			hOut += out;
		}
	}
	// the engine's own count decides who won: it skips surrendered, psi-captured and over-threshold units
	const BattlescapeTally tally = save->getBattleGame()->tallyUnits();
	std::ostringstream tac;
	for (const auto &t : tallies)
	{
		tac << (tac.tellp() > 0 ? "," : "") << t.first << ":" << t.second;
	}
	Log(LOG_INFO) << "[AIRESULT] how=" << how
		<< " tac=" << (tac.tellp() > 0 ? tac.str() : std::string("-"))
		<< " seed=" << battleSeed()
		<< " livesoldiers=" << tally.liveSoldiers << " livealiens=" << tally.liveAliens << " aborted=" << save->isAborted()
		<< " mission=" << save->getMissionType()
		<< " turn=" << save->getTurn()
		<< " player=" << pUnits << " pdead=" << pDead << " pout=" << pOut << " pwounded=" << pWounded << " phplost=" << pHpLost
		<< " hostile=" << hUnits << " hdead=" << hDead << " hout=" << hOut << " hleft=" << (hUnits - hDead - hOut)
		<< " pmoves=" << decided[FACTION_PLAYER][0] << " pattacks=" << decided[FACTION_PLAYER][1]
		<< " hmoves=" << decided[FACTION_HOSTILE][0] << " hattacks=" << decided[FACTION_HOSTILE][1]
		<< " ms=" << (SDL_GetTicks() - startTicks) << " vms=" << (Timer::probeTicks - startVirtual);
	// the light of the run (OXCE_AI_LIGHTSKIP): did the walks go through the skip, was anybody lit, how dark was the map
	int litHostile = 0, litNow = 0;
	for (const auto *bu : *save->getUnits())
	{
		litHostile += bu->getOriginalFaction() == FACTION_HOSTILE && bu->getArmor()->getPersonalLightHostile() > 0;
		litNow += save->getTileEngine()->unitLightPower(bu) > 0;
	}
	const char *ls = getenv("OXCE_AI_LIGHTSKIP");
	Log(LOG_INFO) << "[AILIGHT] lightskip=" << (ls ? ls : "-")
		<< " lighting_recalc_count=" << lightRecalc << " lighting_skipped_count=" << lightSkipped
		<< " units_with_personalLightHostile=" << litHostile << " units_lit_now=" << litNow
		<< " shade=" << save->getGlobalShade();
}

}

bool active()
{
	static const bool on = envOn("OXCE_AI_PROBE");
	return on;
}

bool fast()
{
	static const bool on = active() && envOn("OXCE_AI_FAST");
	return on;
}

bool lightSkip(const TileEngine *terrain, const BattleUnit *unit)
{
	static const bool on = active() && envOn("OXCE_AI_LIGHTSKIP");
	if (on && terrain->unitLightPower(unit) == 0)
	{
		++lightSkipped;
		return true;
	}
	++lightRecalc;
	return false;
}

bool botTurn(const SavedBattleGame *save)
{
	return bot() && save->getSide() == FACTION_PLAYER;
}

bool tactics(const BattleUnit *unit)
{
	static const bool on = active() && envOn("OXCE_AI_TACTICS");
	return on && unit->getFaction() == FACTION_HOSTILE;
}

bool careful(const BattleUnit *unit)
{
	static const bool on = bot() && envOn("OXCE_AI_CAREFUL");
	return on && unit->getFaction() == FACTION_PLAYER;
}

bool evalFire(const BattleUnit *unit)
{
	static const bool on = envOn("OXCE_AI_EVAL");
	return on && careful(unit);
}

bool pickUp(const BattleUnit *unit)
{
	static const bool on = envOn("OXCE_AI_ARMS");
	return on && careful(unit);
}

double param(const char *name, double def)
{
	const char *s = getenv(name);
	return s && *s ? atof(s) : def;
}

void tally(const BattleUnit *unit, const char *rule)
{
	++tallies[std::string(unit->getFaction() == FACTION_PLAYER ? "p." : "h.") + rule];
	addTrail(unit, rule);
}

void note(const BattleUnit *unit, const char *what)
{
	addTrail(unit, what);
}

void walkStop(const BattleUnit *unit, const char *reason, const Position &to, int dir, int bam, int stepTu, int stepEnergy, int blocker)
{
	if (!record())
		return;
	const Position from = unit->getPosition();
	const AIModule *ai = unit->getAIModule();
	std::ostringstream s;
	s << "walk.stop." << reason << " " << from.x << "," << from.y << "," << from.z << ">" << to.x << "," << to.y << "," << to.z
		<< " d" << dir << " bam" << bam << " mt" << (int)unit->getMovementType() << " sz" << unit->getArmor()->getSize()
		<< " tu" << unit->getTimeUnits() << "/" << stepTu << " en" << unit->getEnergy() << "/" << stepEnergy
		<< " rs" << (ai ? (int)const_cast<AIModule *>(ai)->getReserveMode() : -1) << " bu" << blocker;
	addTrail(unit, s.str().c_str());
}

long long battleSeed()
{
	static const long long seed = [] { const char *s = getenv("OXCE_AI_SEED"); return active() && s && *s ? atoll(s) : -1LL; }();
	return seed;
}

void battleOver(BattlescapeState *state, SavedBattleGame *save, bool abort)
{
	if (!active() || phase == FINISHED)
	{
		return;
	}
	if (!started)
	{
		logStart(save);
	}
	recordEnd(save);
	logState(save, "end");
	logResult(save, abort ? "abort" : "over");
	phase = FINISHED;
	state->getGame()->quit();
}

void think(BattlescapeState *state, SavedBattleGame *save)
{
	if (!active() || phase == FINISHED)
	{
		return;
	}
	recordTurn(save);
	if (bot())
	{
		// both sides are the AI's: watch, log the start of each hostile turn, stop at the turn cap
		if (!started)
		{
			logStart(save);
		}
		if (save->getSide() == FACTION_HOSTILE && aiStartLogged != save->getTurn())
		{
			aiStartLogged = save->getTurn();
			logState(save, "aistart");
		}
		// and of each player turn: a tile's outcome is the next snapshot after the other side has moved
		if (save->getSide() == FACTION_PLAYER && playerStartLogged != save->getTurn() && save->getTurn() > 1)
		{
			playerStartLogged = save->getTurn();
			logState(save, "pstart");
		}
		if (save->getTurn() > turnsWanted())
		{
			recordEnd(save);
			logState(save, "end");
			logResult(save, "timeout");
			phase = FINISHED;
			state->getGame()->quit();
		}
		return;
	}
	BattlescapeGame *bg = state->getBattleGame();
	// the player's turn, nothing moving: either the first one after loading or the one the AI handed back
	const bool playerReady = save->getSide() == FACTION_PLAYER && !bg->isBusy() && state->allowButtons();
	if (phase == WAIT_PLAYER && playerReady)
	{
		if (!started)
		{
			logStart(save);
		}
		turnAtEnd = save->getTurn();
		phase = AI_PLAYING;
		bg->requestEndTurn(false);
	}
	else if (phase == AI_PLAYING && save->getSide() == FACTION_HOSTILE && aiStartLogged != save->getTurn())
	{
		// who the AI side really sees as its turn begins: the blindness test needs the moved units unseen in both runs
		aiStartLogged = save->getTurn();
		logState(save, "aistart");
	}
	else if (phase == AI_PLAYING && playerReady && save->getTurn() > turnAtEnd)
	{
		++turnsPlayed;
		if (turnsPlayed < turnsWanted())
		{
			phase = WAIT_PLAYER;
			return;
		}
		logState(save, "after");
		// OXCE_AI_PROBE_SAVE=<file>: the battle as the AI left it, on the player's turn - a fixture for the next probes
		const char *saveAs = getenv("OXCE_AI_PROBE_SAVE");
		if (saveAs && *saveAs)
		{
			state->getGame()->getSavedGame()->save(saveAs, state->getGame()->getMod());
			Log(LOG_INFO) << "[AIPROBE] saved: " << saveAs;
		}
		Log(LOG_INFO) << "[AIPROBE] done: " << turnsPlayed << " AI turn(s), " << (SDL_GetTicks() - startTicks)
			<< " ms real, " << (Timer::probeTicks - startVirtual) << " ms virtual";
		phase = FINISHED;
		state->getGame()->quit();
	}
}

/// FNV-1a over whole numbers: the fingerprint of the battle state before a decision (docs/research/ai-arena-v2-plan.md, 3.1).
struct StateHash
{
	uint64_t h = 1469598103934665603ULL;
	void add(long long v)
	{
		for (int i = 0; i < 8; ++i)
		{
			h = (h ^ (uint64_t)((v >> (i * 8)) & 0xff)) * 1099511628211ULL;
		}
	}
	void text(const std::string &s)
	{
		for (char c : s)
		{
			add(c);
		}
	}
};

/// One item by what it is, not by getId(): item ids differ between runs of one battle (the items are made in the order of
/// a map keyed by rule pointers, R-025) while every decision stays the same (det23a/det23b, 22 of 22).
static uint64_t itemHash(const BattleItem *it, long long where)
{
	StateHash h;
	h.add(where);
	h.text(it->getRules()->getType());
	h.text(it->getSlot() ? it->getSlot()->getId() : std::string("-"));
	h.add(it->getAmmoQuantity());
	h.add(it->getFuseTimer());
	const BattleItem *ammo = it->getAmmoForSlot(0);
	h.text(ammo && ammo != it ? ammo->getRules()->getType() : std::string("-"));
	h.add(ammo && ammo != it ? ammo->getAmmoQuantity() : 0);
	return h.h;
}

/// Two runs of one battle diverge at the first decision whose fingerprints differ: units (place, facing, TU, health, stun,
/// morale, energy, fire, status, faction, who they see; the engine's state queue), items (what lies where, in any order),
/// the order of items in each inventory, map (tile parts, doors, fire, smoke) and the random generator's state - five parts,
/// to see at once which one it was. Items and their order apart: the order of one inventory can differ between runs.
static void stateHash(SavedBattleGame *save, uint64_t &units, uint64_t &items, uint64_t &order, uint64_t &map, uint64_t &rng)
{
	StateHash u, o, m;
	uint64_t itemSum = 0;
	for (auto *bu : *save->getUnits())
	{
		u.add(bu->getId());
		u.add(bu->getPosition().x); u.add(bu->getPosition().y); u.add(bu->getPosition().z);
		u.add(bu->getDirection()); u.add(bu->getTimeUnits()); u.add(bu->getHealth()); u.add(bu->getStunlevel());
		u.add(bu->getMorale()); u.add(bu->getEnergy()); u.add(bu->getFire()); u.add((int)bu->getStatus()); u.add((int)bu->getFaction());
		for (const auto *seen : *bu->getVisibleUnits())
		{
			u.add(seen->getId());
		}
		for (const auto *it : *bu->getInventory())
		{
			const uint64_t h = itemHash(it, bu->getId());
			itemSum += h;
			o.add((long long)h);
		}
	}
	for (int i = 0; i < save->getMapSizeXYZ(); ++i)
	{
		Tile *tile = save->getTile(i);
		for (int part = O_FLOOR; part < O_MAX; ++part)
		{
			int id = -1, set = -1;
			tile->getMapData(&id, &set, (TilePart)part);
			m.add(id * 256 + set);
			m.add(tile->isUfoDoorOpen((TilePart)part) ? 1 : 0);
		}
		m.add(tile->getFire()); m.add(tile->getSmoke());
		for (const auto *it : *tile->getInventory())
		{
			const uint64_t h = itemHash(it, -1 - i);
			itemSum += h;
			o.add((long long)h);
		}
	}
	// the engine's own state goes with the units: the same world with another queue of battle states moves on differently
	if (const BattlescapeGame *game = save->getBattleGame())
	{
		u.add(game->getAIActionCounter());
		for (const auto *state : game->getStates())
		{
			for (const char *c = typeid(*state).name(); *c; ++c)
			{
				u.add(*c);
			}
		}
	}
	u.add((int)save->getSide());
	units = u.h;
	items = itemSum;
	order = o.h;
	map = m.h;
	rng = RNG::getSeed();
}

uint64_t rngBefore = 0, aiBefore = 0;

namespace
{

/// Which bench behaviour made the record (docs/AI_DECISION_RECORD.md): a dataset never mixes generations. base_v2 is
/// build-ai28 and later - the battle's items in the mod's order (docs/research/ai-arena-v2-plan.md, "Поколения базы").
/// Change it with any change of how the bench plays; the OXCE_AI_* switches of a run go into "cfg" apart.
const char *const ENGINE_GEN = "base_v2";

/// A rule of the AI module that filled a slot: the slot is taken from later, maybe by a later decision.
struct Proposal
{
	char slot = 0;
	std::string src;
	int score = INT_MIN;
	int type = 0;
	Position to;
	std::string weapon;
	int rec = -1;
};

/// hp, stun, whether down, faction: every unit as a decision begins, to see what its action did
struct Snapshot { int hp, stun; bool down; int faction; };

bool isDown(const BattleUnit *bu)
{
	return bu->getStatus() == STATUS_DEAD || bu->getHealth() <= 0 || bu->getStatus() == STATUS_UNCONSCIOUS
		|| bu->getStunlevel() >= bu->getHealth();
}

/// The decision record (OXCE_AI_RECORD, plan V2 step 2): the candidates of the unit about to think, and what it thought.
struct Pending
{
	int unit = -1;
	AiCandidates::Set set;
	bool rngTouched = false;
	/// the unit as it starts to think (thinking may spend: a grenade is primed in think)
	Position pos;
	int dir = 0, tu = 0, hp = 0, stun = 0, morale = 0;
	bool kneel = false;
	std::map<int, Snapshot> units;
	std::vector<Proposal> proposals;
	std::vector<std::string> trail;
	std::vector<std::string> odds;
	char slot = 0;
	bool trace = false;
	std::map<std::string, std::vector<std::string>> traced;
};
Pending pending;

/// The action of the last decision until it is over: the next decision, the end of the side's turn or of the battle.
struct Exec
{
	int rec = -1, unit = -1, side = -1, turn = 0;
	int tu = 0;
	int walk = -1;
	/// the walk goes to an item (findItem / findBotWeapon replaced the decision's action): "item":1 in [AIEXEC] and [AIPATROL]
	bool item = false;
	std::map<int, Snapshot> units;
	std::vector<std::string> trail;
	/// a patrol walk to its node, followed by [AIPATROL] (OXCE_AI_RECORD_PATH): the node, the move type, the tiles in reach
	bool patrol = false;
	Position target;
	int bam = 0;
	std::vector<std::pair<Position, int>> reach;
	/// enemies it knows of (AiCandidates' rule), sees itself, has a shot at with a line of fire (any / within its TU)
	int known = 0, seen = 0, lof = 0, lofTu = 0;
};
Exec exec;

/// Each unit that decided in its side's turn: first and last record, and how it was when its last action was over;
/// written when the side's next turn begins - what the enemy's turn did to it.
struct After { int first = -1, last = -1, n = 0, turn = 0, hp = 0, stun = 0; };
std::map<int, After> afterOf[3];
int seenSide = -1, seenTurn = -1;

/// per unit, per slot: the last rule that filled it
std::map<int, std::map<char, Proposal>> slotOf;
/// move and action lists already written in this battle: a list is stored once, the records refer to it by its hash
std::set<uint64_t> movesWritten, actsWritten;
/// the decision's number in the battle, and the order in which units first decide within one side's turn
int recordNo = 0;
int orderTurn = -1, orderSide = -1;
std::map<int, int> orderOf;
bool headWritten = false;

bool record()
{
	static const bool on = active() && envOn("OXCE_AI_RECORD");
	// the battle is over (turn cap): a decision taken later in the same frame has no execution to follow
	return on && phase != FINISHED;
}

/// OXCE_AI_TRACE_DECISION=12,40: the record numbers whose every scored tile goes to the log ([AITRACE])
bool traced(int rec)
{
	static const std::set<int> wanted = []
	{
		std::set<int> out;
		const char *s = getenv("OXCE_AI_TRACE_DECISION");
		std::istringstream in(s ? s : "");
		std::string item;
		while (std::getline(in, item, ','))
		{
			if (!item.empty())
				out.insert(atoi(item.c_str()));
		}
		return out;
	}();
	return wanted.count(rec) > 0;
}

void addTrail(const BattleUnit *unit, const char *what)
{
	if (!record())
		return;
	if (pending.unit == unit->getId())
		pending.trail.push_back(what);
	else if (exec.unit == unit->getId())
		exec.trail.push_back(what);
}

}

namespace
{

std::string jpos(Position p)
{
	std::ostringstream s;
	s << "[" << p.x << "," << p.y << "," << p.z << "]";
	return s.str();
}

BattleUnit *unitById(SavedBattleGame *save, int id)
{
	for (auto *bu : *save->getUnits())
	{
		if (bu->getId() == id)
			return bu;
	}
	return nullptr;
}

/// Living units of other factions with the unit in their sight now.
int spottedBy(SavedBattleGame *save, const BattleUnit *unit)
{
	int n = 0;
	for (auto *bu : *save->getUnits())
	{
		if (bu->getFaction() != unit->getFaction() && !bu->isOut())
		{
			const auto *vis = bu->getVisibleUnits();
			n += std::find(vis->begin(), vis->end(), unit) != vis->end() ? 1 : 0;
		}
	}
	return n;
}

/// The last decision's action is over: what it did ([AIEXEC], joined to [AIREC] by rec).
void flushExec(SavedBattleGame *save)
{
	if (exec.rec < 0)
	{
		return;
	}
	BattleUnit *self = unitById(save, exec.unit);
	int dmg = 0, stunned = 0, downed = 0, fdmg = 0, fdowned = 0, born = 0;
	for (const auto *bu : *save->getUnits())
	{
		auto b = exec.units.find(bu->getId());
		if (b == exec.units.end())
		{
			++born; // spawned by the action (a zombie, a split unit)
			continue;
		}
		if (bu->getId() == exec.unit)
			continue;
		const int lost = std::max(0, b->second.hp - bu->getHealth());
		const int stun = std::max(0, bu->getStunlevel() - b->second.stun);
		const int down = !b->second.down && isDown(bu) ? 1 : 0;
		if (b->second.faction != exec.side)
		{
			dmg += lost; stunned += stun; downed += down;
		}
		else
		{
			fdmg += lost; fdowned += down;
		}
	}
	std::ostringstream trail;
	for (const auto &t : exec.trail)
	{
		trail << (trail.tellp() > 0 ? "," : "") << "\"" << t << "\"";
	}
	std::ostringstream line;
	line << "[AIEXEC] {\"v\":1,\"rec\":" << exec.rec << ",\"unit\":" << exec.unit << ",\"walk\":";
	if (exec.walk < 0) line << "null"; else line << exec.walk;
	if (exec.item) line << ",\"item\":1";
	if (self)
	{
		const auto &b = exec.units[exec.unit];
		int seen = 0;
		for (const auto *v : *self->getVisibleUnits())
		{
			seen += v->getFaction() != self->getFaction() && !v->isOut() ? 1 : 0;
		}
		line << ",\"pos\":" << jpos(self->getPosition()) << ",\"dir\":" << self->getDirection() << ",\"tu\":" << self->getTimeUnits()
			<< ",\"spent\":" << (exec.tu - self->getTimeUnits()) << ",\"kneel\":" << (self->isKneeled() ? 1 : 0)
			<< ",\"hp\":" << self->getHealth() << ",\"hp_lost\":" << std::max(0, b.hp - self->getHealth())
			<< ",\"stun\":" << self->getStunlevel() << ",\"down\":" << (isDown(self) ? 1 : 0)
			<< ",\"seen\":" << seen << ",\"spotted\":" << spottedBy(save, self);
		if (exec.side >= 0 && exec.side < 3)
		{
			After &a = afterOf[exec.side][exec.unit];
			if (a.n++ == 0)
				a.first = exec.rec;
			a.last = exec.rec;
			a.turn = exec.turn;
			a.hp = self->getHealth();
			a.stun = self->getStunlevel();
		}
	}
	line << ",\"dmg\":" << dmg << ",\"stunned\":" << stunned << ",\"downed\":" << downed << ",\"fdmg\":" << fdmg << ",\"fdowned\":" << fdowned
		<< ",\"born\":" << born << ",\"trail\":[" << trail.str() << "]}";
	Log(LOG_INFO) << line.str();
	exec = Exec();
}

/// The side begins its next turn (or the battle is over): what the enemy's turn did to each unit that decided in the side's
/// last turn ([AIAFTER], joined to the records first..last).
void flushAfter(SavedBattleGame *save, int side, bool end)
{
	for (const auto &e : afterOf[side])
	{
		const BattleUnit *u = unitById(save, e.first);
		const After &a = e.second;
		std::ostringstream line;
		line << "[AIAFTER] {\"v\":1,\"side\":" << side << ",\"turn\":" << a.turn << ",\"now\":" << save->getTurn() << ",\"unit\":" << e.first
			<< ",\"first\":" << a.first << ",\"last\":" << a.last << ",\"n\":" << a.n << ",\"end\":" << (end ? 1 : 0);
		if (u)
		{
			const bool dead = u->getStatus() == STATUS_DEAD || u->getHealth() <= 0;
			line << ",\"dead\":" << (dead ? 1 : 0) << ",\"down\":" << (isDown(u) ? 1 : 0)
				<< ",\"hp\":" << u->getHealth() << ",\"hp_lost\":" << std::max(0, a.hp - u->getHealth())
				<< ",\"stun\":" << u->getStunlevel() << ",\"stun_gain\":" << std::max(0, u->getStunlevel() - a.stun)
				<< ",\"wounds\":" << u->getFatalWounds() << ",\"pos\":" << jpos(u->getPosition()) << ",\"spotted\":" << (dead ? 0 : spottedBy(save, u));
		}
		line << "}";
		Log(LOG_INFO) << line.str();
	}
	afterOf[side].clear();
}

void recordTurn(SavedBattleGame *save)
{
	const int side = save->getSide();
	if (!record() || (side == seenSide && save->getTurn() == seenTurn))
	{
		return;
	}
	seenSide = side;
	seenTurn = save->getTurn();
	if (side >= 0 && side < 3)
	{
		flushExec(save); // the other side's last action, if its turn end was not seen
		flushAfter(save, side, false);
	}
}

void recordEnd(SavedBattleGame *save)
{
	if (!record())
	{
		return;
	}
	flushExec(save);
	for (int side = 0; side < 3; ++side)
	{
		flushAfter(save, side, true);
	}
}

}

void beforeThink(SavedBattleGame *save, BattleUnit *unit)
{
	if (!active())
	{
		return;
	}
	rngBefore = RNG::getSeed();
	aiBefore = unit->getAIModule() ? unit->getAIModule()->probeHash() : 0;
	if (record())
	{
		flushExec(save);
		pending = Pending();
		pending.unit = unit->getId();
		pending.pos = unit->getPosition();
		pending.dir = unit->getDirection();
		pending.tu = unit->getTimeUnits();
		pending.hp = unit->getHealth();
		pending.stun = unit->getStunlevel();
		pending.morale = unit->getMorale();
		pending.kneel = unit->isKneeled();
		pending.trace = traced(recordNo);
		for (const auto *bu : *save->getUnits())
		{
			pending.units[bu->getId()] = { bu->getHealth(), bu->getStunlevel(), isDown(bu), (int)bu->getFaction() };
		}
		pending.set = AiCandidates::generate(save, unit);
		// the list must not change the battle: it may not draw a random number
		pending.rngTouched = RNG::getSeed() != rngBefore;
	}
}

void propose(const BattleUnit *unit, char slot, const char *source, int score, const BattleAction &action)
{
	if (!record() || pending.unit != unit->getId())
	{
		return;
	}
	Proposal p;
	p.slot = slot;
	p.src = source;
	p.score = score;
	p.type = action.type;
	p.to = action.target;
	p.weapon = action.weapon ? action.weapon->getRules()->getType() : std::string();
	p.rec = recordNo;
	pending.proposals.push_back(p);
	slotOf[unit->getId()][slot] = p;
}

void chosen(const BattleUnit *unit, char slot)
{
	if (record() && pending.unit == unit->getId())
	{
		pending.slot = slot;
	}
}

void modeOdds(const BattleUnit *unit, int patrol, int ambush, int combat, int escape, int roll, int mode)
{
	if (!record() || pending.unit != unit->getId())
	{
		return;
	}
	std::ostringstream s;
	s << "{\"p\":" << patrol << ",\"a\":" << ambush << ",\"c\":" << combat << ",\"e\":" << escape << ",\"roll\":" << roll << ",\"mode\":" << mode << "}";
	pending.odds.push_back(s.str());
}

void traceTile(const BattleUnit *unit, const char *what, const Position &pos, int score)
{
	if (pending.trace && pending.unit == unit->getId())
	{
		std::ostringstream s;
		s << "[" << pos.x << "," << pos.y << "," << pos.z << "," << score << "]";
		pending.traced[what].push_back(s.str());
	}
}

namespace { void logPatrolPath(SavedBattleGame *save, BattleUnit *unit, bool pushed); }

void walkPlanned(SavedBattleGame *save, BattleUnit *unit, bool pushed, bool item)
{
	if (record() && exec.unit == unit->getId())
	{
		exec.walk = pushed ? 1 : 0;
		exec.item = item;
		if (exec.patrol)
		{
			exec.patrol = false;
			logPatrolPath(save, unit, pushed);
		}
	}
}

void sideEnds(SavedBattleGame *save)
{
	if (record())
	{
		flushExec(save);
	}
}

namespace
{

std::string hex(uint64_t v)
{
	std::ostringstream s;
	s << std::hex << v;
	return s.str();
}

std::string pos(Position p)
{
	std::ostringstream s;
	s << "[" << p.x << "," << p.y << "," << p.z << "]";
	return s.str();
}

/// Item types are plain STR_ names, but the record is JSON: keep it so whatever a mod calls its items.
std::string quoted(const std::string &text)
{
	std::string out = "\"";
	for (char c : text)
	{
		if (c == '"' || c == '\\')
			out += '\\';
		if ((unsigned char)c >= 0x20)
			out += c;
	}
	return out + "\"";
}

/// Would the walk's reserve check let a step of tu, energy go (BattlescapeGame::checkReservedTU as UnitWalkBState calls it)?
/// Asked with justChecking, which has no side effects; for the player's side that skips one shortcut of the real call -
/// a reserve the unit cannot pay at all reserves nothing - so it is put back here.
bool reserveLets(SavedBattleGame *save, BattleUnit *unit, int tu, int energy)
{
	BattlescapeGame *game = save->getBattleGame();
	if (save->getSide() == FACTION_HOSTILE) return game->checkReservedTU(unit, tu, energy, true);
	return !game->checkReservedTU(unit, 0, 0, true) || game->checkReservedTU(unit, tu, energy, true);
}

/// A Pathfinding of the probe's own: the battle's one holds the path the walk is about to take.
Pathfinding *probePathfinding(SavedBattleGame *save)
{
	static std::unique_ptr<Pathfinding> probe;
	static const SavedBattleGame *probeSave = nullptr;
	static Position probeSize;
	const Position mapSize(save->getMapSizeX(), save->getMapSizeY(), save->getMapSizeZ());
	if (!probe || probeSave != save || probeSize != mapSize) // a new battle may get the old one's address
	{
		probe.reset(new Pathfinding(save));
		probeSave = save;
		probeSize = mapSize;
	}
	return probe.get();
}

/// The walk's path as the battle's Pathfinding holds it: its cost, its first step, and what stops that step.
struct FirstStep
{
	int cost = -1, dir = -1, tu = -1, en = -1, stand = 0;
	Position to;
	std::string stop = "none";
};

/// What stops the first step of the walk the battle's Pathfinding holds - UnitWalkBState's checks in its order.
FirstStep firstStep(SavedBattleGame *save, BattleUnit *unit, BattleActionMove bam, bool pushed)
{
	Pathfinding *pf = save->getPathfinding();
	const std::vector<int> &path = pf->getPath();
	FirstStep s;
	s.to = unit->getPosition();
	if (pushed)
	{
		s.cost = 0;
		Position p = unit->getPosition();
		for (auto it = path.rbegin(); it != path.rend(); ++it) // paths are stored in reverse order
		{
			PathfindingStep r = pf->getTUCost(p, *it, unit, nullptr, bam);
			if (it == path.rbegin())
			{
				s.dir = *it;
				s.tu = r.cost.time;
				s.en = r.cost.energy;
				s.to = r.pos;
			}
			s.cost += r.cost.time;
			p = r.pos;
		}
	}

	// a kneeling unit stands up first, and that TU is gone before the step
	const int tu = unit->getTimeUnits(), energy = unit->getEnergy();
	const bool kneel = unit->isKneeled();
	s.stand = kneel ? unit->getKneelUpCost() : 0;
	if (!pushed)
		s.stop = "nopath";
	else if (kneel && !(unit->getArmor()->allowsKneeling(unit->getType() == "SOLDIER") && !unit->isFloating() && reserveLets(save, unit, s.stand, 0)))
		s.stop = "kneel";
	else if (s.tu == Pathfinding::INVALID_MOVE_COST)
		s.stop = "invalid";
	else if (s.tu > tu - s.stand)
		s.stop = "tu";
	else if (s.en > energy)
		s.stop = "energy";
	else if (!reserveLets(save, unit, s.tu + s.stand, s.en))
		s.stop = "reserve";
	else
	{
		const int size = unit->getArmor()->getSize() - 1;
		for (int x = size; x >= 0 && s.stop == "none"; --x)
		{
			for (int y = size; y >= 0 && s.stop == "none"; --y)
			{
				const Tile *t = save->getTile(s.to + Position(x, y, 0));
				const BattleUnit *other = t ? t->getOverlappingUnit(save, TUO_IGNORE_SMALL) : nullptr;
				if (other && other != unit) s.stop = "occupied";
			}
		}
	}
	return s;
}

/// The cheapest step to a neighbouring tile by energy, other units aside (ENERGY_PATROL_END_V2): the game's step cost in
/// all 10 directions with the walk's move type, with the other units lifted off the tiles around for the count and put
/// straight back - they are a passing obstacle, the terrain, the stairs and the unit's size are not.
/// (getTUCost and all it calls are const, and it runs on the probe's own Pathfinding; the only thing touched is the
/// lifted units, and LiftUnits puts them back on any way out of the block.) snEn -1 - no such step, snN - how many.
void staticStep(SavedBattleGame *save, BattleUnit *unit, BattleActionMove bam, int &snEn, int &snN)
{
	Pathfinding *probe = probePathfinding(save);
	const Position from = unit->getPosition();
	snEn = -1;
	snN = 0;
	struct LiftUnits
	{
		std::vector<std::pair<Tile*, BattleUnit*>> lifted;
		~LiftUnits() { for (const auto &l : lifted) l.first->setUnit(l.second); }
	} lift;
	const int big = unit->getArmor()->getSize() - 1; // the box covers the footprint of a large unit and its neighbours
	for (int z = from.z - 2; z <= from.z + 1; ++z)
		for (int x = from.x - 1; x <= from.x + big + 1; ++x)
			for (int y = from.y - 1; y <= from.y + big + 1; ++y)
			{
				Tile *t = save->getTile(Position(x, y, z));
				if (t && t->getUnit() && t->getUnit() != unit)
				{
					lift.lifted.push_back({ t, t->getUnit() });
					t->setUnit(nullptr);
				}
			}
	for (int dir = 0; dir <= Pathfinding::DIR_DOWN; ++dir)
	{
		const PathfindingStep r = probe->getTUCost(from, dir, unit, nullptr, bam);
		if (r.cost.time >= Pathfinding::INVALID_MOVE_COST || r.pos == from) continue;
		++snN;
		if (snEn < 0 || r.cost.energy < snEn) snEn = r.cost.energy;
	}
}

/// [AIPATROL] (plan V2, L0-B): a patrol walk to its node - the path the game found, what stops its first step, and when it
/// is stopped, the tiles in reach that get closest to the node. The costs come from a Pathfinding of the probe's own: the
/// battle's one holds the path the walk is about to take.
void logPatrolPath(SavedBattleGame *save, BattleUnit *unit, bool pushed)
{
	Pathfinding *probe = probePathfinding(save);
	const BattleActionMove bam = (BattleActionMove)exec.bam;
	const Position from = unit->getPosition();
	const std::vector<int> &path = save->getPathfinding()->getPath();

	const FirstStep step = firstStep(save, unit, bam, pushed);
	const int cost = step.cost, firstDir = step.dir, firstTu = step.tu, firstEn = step.en, stand = step.stand;
	const Position firstTo = step.to;
	const std::string &stop = step.stop;
	const int tu = unit->getTimeUnits(), energy = unit->getEnergy();
	const bool kneel = unit->isKneeled();

	std::ostringstream line;
	line << "[AIPATROL] {\"v\":3,\"rec\":" << exec.rec << ",\"unit\":" << unit->getId() << ",\"pos\":" << pos(from) << ",\"to\":" << pos(exec.target)
		<< ",\"bam\":" << exec.bam << (exec.item ? ",\"item\":1" : "") << ",\"pushed\":" << (pushed ? 1 : 0) << ",\"len\":" << (pushed ? (int)path.size() : 0) << ",\"cost\":" << cost
		<< ",\"first\":";
	if (pushed)
		line << "{\"dir\":" << firstDir << ",\"tu\":" << firstTu << ",\"en\":" << firstEn << ",\"to\":" << pos(firstTo) << "}";
	else
		line << "null";
	// how many TU the reserve leaves for a move: the largest step it lets go (the check only gets harder with more TU)
	int lo = -1, hi = tu;
	while (lo < hi)
	{
		const int mid = (lo + hi + 1) / 2;
		if (reserveLets(save, unit, mid, 0)) lo = mid; else hi = mid - 1;
	}
	// the TU a reaction shot costs: a snap shot with the weapon TileEngine::determineReactionType takes
	int snap = -1;
	if (BattleItem *w = unit->getMainHandWeapon(unit->getFaction() != FACTION_PLAYER, true))
	{
		if (w->getRules()->getBattleType() == BT_FIREARM)
		{
			const BattleActionCost c(BA_SNAPSHOT, unit, w);
			if (c.Time > 0) snap = c.Time;
		}
	}
	int snEn, snN;
	staticStep(save, unit, bam, snEn, snN);
	AIModule *ai = unit->getAIModule();
	line << ",\"sn_en\":" << snEn << ",\"sn_n\":" << snN;
	line << ",\"tu\":" << tu << ",\"energy\":" << energy << ",\"kneel\":" << (kneel ? 1 : 0)
		<< ",\"reserve\":" << (pushed && firstTu != Pathfinding::INVALID_MOVE_COST ? (reserveLets(save, unit, firstTu + stand, firstEn) ? 1 : 0) : -1)
		<< ",\"free\":" << lo << ",\"reserved\":" << (lo < 0 ? tu : tu - lo)
		<< ",\"rmode\":" << (ai && save->getSide() == FACTION_HOSTILE ? (int)ai->getReserveMode() : (int)save->getTUReserved())
		<< ",\"after\":" << (pushed && firstTu != Pathfinding::INVALID_MOVE_COST ? tu - stand - firstTu : -1) << ",\"snap\":" << snap
		<< ",\"known\":" << exec.known << ",\"seen\":" << exec.seen << ",\"lof\":" << exec.lof << ",\"lof_tu\":" << exec.lofTu
		<< ",\"stop\":\"" << stop << "\",\"nreach\":" << exec.reach.size();
	if (stop != "none")
	{
		// the tiles in reach nearest to the node, and how far each still is from it by path
		const int before = probe->pathCost(unit, from, exec.target, bam);
		std::vector<std::pair<int, size_t>> near;
		for (size_t i = 0; i < exec.reach.size(); ++i)
		{
			const Position d = exec.reach[i].first - exec.target;
			near.push_back({ d.x * d.x + d.y * d.y + 4 * d.z * d.z, i });
		}
		std::sort(near.begin(), near.end());
		if (near.size() > 16) near.resize(16);
		struct Best { int i = -1, after = -1, reach = 0; bool ok = false; };
		Best best, bestOk;
		for (const auto &n : near)
		{
			const auto &r = exec.reach[n.second];
			const int after = probe->pathCost(unit, r.first, exec.target, bam);
			if (after < 0) continue;
			const bool ok = reserveLets(save, unit, r.second, 0);
			auto better = [&](const Best &b) { return b.i < 0 || after < b.after || (after == b.after && r.second < b.reach); };
			if (better(best)) best = { (int)n.second, after, r.second, ok };
			if (ok && better(bestOk)) bestOk = { (int)n.second, after, r.second, ok };
		}
		auto put = [&](const Best &b) {
			if (b.i < 0) { line << "null"; return; }
			line << "{\"to\":" << pos(exec.reach[b.i].first) << ",\"reach\":" << b.reach << ",\"after\":" << b.after << ",\"reserve\":" << (b.ok ? 1 : 0) << "}";
		};
		line << ",\"before\":" << before << ",\"best\":";
		put(best);
		line << ",\"best_ok\":";
		put(bestOk);
	}
	line << "}";
	Log(LOG_INFO) << line.str();
}

bool attackType(int type)
{
	return type == BA_AUTOSHOT || type == BA_SNAPSHOT || type == BA_AIMEDSHOT || type == BA_HIT || type == BA_THROW
		|| type == BA_LAUNCH || type == BA_MINDCONTROL || type == BA_PANIC || type == BA_USE;
}

/// What an attack aims at (docs/AI_DECISION_RECORD.md): an enemy the unit knows of or one it does not, a friend, a body,
/// the tile its side last saw an enemy on, a door, a wall or object, or a bare tile. A launch aims at its last waypoint.
std::string targetKind(SavedBattleGame *save, BattleUnit *unit, const BattleAction &action)
{
	const Position at = action.type == BA_LAUNCH && !action.waypoints.empty() ? action.waypoints.back() : action.target;
	Tile *tile = save->getTile(at);
	if (!tile)
		return "none";
	if (const BattleUnit *bu = tile->getUnit())
	{
		if (bu == unit)
			return "self";
		if (bu->isOut())
			return "down";
		if (bu->getFaction() == unit->getFaction())
			return "friend";
		const auto &seen = *unit->getVisibleUnits();
		const bool known = std::find(seen.begin(), seen.end(), bu) != seen.end()
			|| bu->getTurnsSinceSpottedByFaction(unit->getFaction()) <= unit->getIntelligence();
		return known ? "enemy" : "enemy_unknown";
	}
	if (lastSeenAt((int)unit->getFaction(), at))
		return "last_seen";
	bool door = false, solid = false;
	for (TilePart part : { O_WESTWALL, O_NORTHWALL, O_OBJECT })
	{
		if (const MapData *md = tile->getMapData(part))
		{
			door = door || md->isDoor() || md->isUFODoor();
			solid = true;
		}
	}
	return door ? "door" : solid ? "terrain" : "tile";
}

/// The OXCE_AI_* switches of the run, sorted, but the battle's own (seed, mission, campaign), the recording's and the machine's
/// paths: the bench's configuration.
const std::string &cfgText()
{
	static const std::string text = []
	{
		static const std::set<std::string> skip = { "OXCE_AI_SEED", "OXCE_AI_RECORD", "OXCE_AI_TRACE_DECISION", "OXCE_AI_PROBE_SAVE",
			"OXCE_AI_BUILD", "OXCE_AI_KEEP_DECIDE", "OXCE_AI_MISSION", "OXCE_AI_CAMPAIGN", "OXCE_AI_EXE", "OXCE_AI_GAME", "OXCE_AI_WORK", "OXCE_AI_RECORD_PATH",
			"OXCE_AI_FAST", "OXCE_AI_LIGHTSKIP" }; // the fast mode and the light skip change what is computed, not how the bench plays
		std::vector<std::string> vars;
		for (char **e = PROBE_ENVIRON; e && *e; ++e)
		{
			const std::string v = *e;
			if (v.compare(0, 8, "OXCE_AI_") == 0 && !skip.count(v.substr(0, v.find('='))))
				vars.push_back(v);
		}
		std::sort(vars.begin(), vars.end());
		std::string out;
		for (const auto &v : vars)
		{
			const size_t eq = v.find('=');
			out += (out.empty() ? "" : ",") + quoted(v.substr(0, eq)) + ":" + quoted(eq == std::string::npos ? std::string() : v.substr(eq + 1));
		}
		return out;
	}();
	return text;
}

uint64_t cfgHash()
{
	static const uint64_t h = [] { StateHash s; s.text(cfgText()); return s.h; }();
	return h;
}

std::string jlist(const std::vector<std::string> &items, bool quote)
{
	std::string out;
	for (const auto &i : items)
	{
		out += (out.empty() ? "" : ",") + (quote ? quoted(i) : i);
	}
	return "[" + out + "]";
}

void writeRecord(SavedBattleGame *save, BattleUnit *unit, const BattleAction &action, uint64_t hashUnits, uint64_t hashItems,
	uint64_t hashOrder, uint64_t hashMap, uint64_t hashRng)
{
	if (pending.unit != unit->getId())
	{
		Log(LOG_INFO) << "[AIPROBE] record: no candidates for unit " << unit->getId();
		return;
	}
	if (!headWritten)
	{
		headWritten = true;
		Log(LOG_INFO) << "[AIRECHEAD] {\"v\":1,\"gen\":\"" << ENGINE_GEN << "\",\"cfg\":\"" << hex(cfgHash()) << "\",\"seed\":" << battleSeed()
			<< ",\"env\":{" << cfgText() << "}}";
	}
	const AiCandidates::Set &set = pending.set;
	if (movesWritten.insert(set.movesHash).second)
	{
		std::ostringstream moves;
		for (const auto &m : set.moves)
		{
			moves << (moves.tellp() > 0 ? ";" : "") << m.tile.x << "." << m.tile.y << "." << m.tile.z << ":" << m.tu;
		}
		Log(LOG_INFO) << "[AICAND] moves=" << hex(set.movesHash) << " unit=" << unit->getId() << " list=" << moves.str();
	}
	// the other actions with their chances: stored once per battle too, under the hash of the text
	std::ostringstream acts;
	for (const auto &c : set.acts)
	{
		acts << (acts.tellp() > 0 ? "," : "") << "{\"id\":\"" << hex(c.id) << "\",\"k\":\"" << (char)c.kind << "\",\"t\":" << c.type
			<< ",\"to\":" << pos(c.tile) << ",\"tu\":" << c.tu;
		if (c.kind == AiCandidates::ATTACK)
		{
			acts << ",\"u\":" << c.target << ",\"w\":" << quoted(c.weapon) << ",\"p\":" << c.chance << ",\"lof\":" << c.lof << ",\"d\":" << c.dist;
		}
		acts << "}";
	}
	StateHash actsHash;
	actsHash.text(acts.str());
	if (actsWritten.insert(actsHash.h).second)
	{
		Log(LOG_INFO) << "[AICAND] acts=" << hex(actsHash.h) << " unit=" << unit->getId() << " list=[" << acts.str() << "]";
	}
	if (save->getTurn() != orderTurn || save->getSide() != orderSide)
	{
		orderTurn = save->getTurn();
		orderSide = save->getSide();
		orderOf.clear();
	}
	const int order = orderOf.emplace(unit->getId(), (int)orderOf.size()).first->second;

	AiCandidates::Kind kind;
	const uint64_t chosen = AiCandidates::chosenId(save, unit, action, &kind);
	bool in = false;
	for (const auto *list : { &set.acts, &set.moves })
	{
		for (const auto &c : *list)
		{
			in = in || c.id == chosen;
		}
	}
	// a choice out of the list still has to have a known kind: a walk to a tile the AI picked beyond this turn's reach,
	// a step onto a neighbour's tile, an attack whose target the record names
	std::string exp = in ? "cand" : "none";
	const std::string tk = attackType(action.type) ? targetKind(save, unit, action) : std::string();
	if (!in && kind == AiCandidates::MOVE)
	{
		const Position p = unit->getPosition(), to = action.target;
		const Tile *t = save->getTile(to);
		if (std::max(std::abs(to.x - p.x), std::abs(to.y - p.y)) <= 1 && std::abs(to.z - p.z) <= 1 && t && t->getUnit() && t->getUnit() != unit)
		{
			exp = "occupied";
		}
		else
		{
			kind = AiCandidates::MOVE_TO_AI_POINT;
			exp = "ai_point";
		}
	}
	else if (!in && kind == AiCandidates::ATTACK)
	{
		exp = "target";
	}

	// the slot the action came from and the rule that filled it (maybe in an earlier decision: a slot is kept)
	const AIModule *ai = unit->getAIModule();
	const int mode = ai ? ai->getAIMode() : -1;
	char slot = pending.slot;
	if (!slot && mode >= AI_PATROL && mode <= AI_ESCAPE)
	{
		slot = "paxe"[mode];
	}
	const char look = slot == 'l' ? 'x' : slot;
	const Proposal *src = nullptr;
	auto of = slotOf.find(unit->getId());
	if (of != slotOf.end() && of->second.count(look))
	{
		src = &of->second[look];
		// a rule of an earlier decision whose action is not the one taken: the slot was emptied since; but a walk to the unit's
		// own tile became BA_NONE on the way (walk.self) and still is that rule's
		const bool self = action.type == BA_NONE && src->type == BA_WALK
			&& std::find(pending.trail.begin(), pending.trail.end(), std::string("walk.self")) != pending.trail.end();
		if (src->rec < recordNo && src->type != action.type && !self && !(attackType(src->type) && attackType(action.type)))
			src = nullptr;
	}
	std::vector<std::string> props;
	for (const auto &p : pending.proposals)
	{
		std::ostringstream s;
		s << "{\"s\":\"" << p.slot << "\",\"src\":" << quoted(p.src) << ",\"sc\":";
		if (p.score == INT_MIN) s << "null"; else s << p.score;
		s << ",\"t\":" << p.type << ",\"to\":" << pos(p.to) << ",\"w\":" << quoted(p.weapon) << "}";
		props.push_back(s.str());
	}
	const std::string trail = jlist(pending.trail, true);
	tally(unit, in ? "rec.in" : (std::string("rec.out.") + (char)kind + std::to_string((int)action.type)).c_str());

	const int rec = recordNo++;
	std::ostringstream line;
	line << "[AIREC] {\"v\":1,\"gen\":\"" << ENGINE_GEN << "\",\"cfg\":\"" << hex(cfgHash()) << "\",\"seed\":" << battleSeed() << ",\"rec\":" << rec
		<< ",\"turn\":" << save->getTurn() << ",\"side\":" << (int)save->getSide() << ",\"unit\":" << unit->getId() << ",\"order\":" << order
		<< ",\"n\":" << action.number
		<< ",\"state\":{\"pos\":" << pos(pending.pos) << ",\"dir\":" << pending.dir << ",\"tu\":" << pending.tu
		<< ",\"hp\":" << pending.hp << ",\"stun\":" << pending.stun << ",\"morale\":" << pending.morale << ",\"kneel\":" << (pending.kneel ? 1 : 0)
		<< ",\"h\":{\"u\":\"" << hex(hashUnits) << "\",\"i\":\"" << hex(hashItems) << "\",\"o\":\"" << hex(hashOrder) << "\",\"m\":\"" << hex(hashMap)
		<< "\",\"r0\":\"" << hex(rngBefore) << "\",\"r\":\"" << hex(hashRng) << "\",\"a0\":\"" << hex(aiBefore) << "\"}"
		<< ",\"state_id\":\"" << hex(hashUnits ^ hashMap) << "\"}"
		<< ",\"cand\":{\"n\":" << set.count() << ",\"set\":\"" << hex(set.setHash) << "\",\"order\":\"" << hex(set.orderHash)
		<< "\",\"moves\":\"" << hex(set.movesHash) << "\",\"nmoves\":" << set.moves.size() << ",\"acts\":\"" << hex(actsHash.h)
		<< "\",\"nacts\":" << set.acts.size() << ",\"rng\":" << (pending.rngTouched ? 1 : 0) << "}"
		<< ",\"base\":{\"id\":\"" << hex(chosen) << "\",\"k\":\"" << (char)kind << "\",\"in\":" << (in ? 1 : 0) << ",\"exp\":\"" << exp << "\""
		<< ",\"tk\":" << (tk.empty() ? std::string("null") : quoted(tk)) << ",\"t\":" << (int)action.type
		<< ",\"to\":" << pos(action.target) << ",\"w\":" << quoted(action.weapon ? action.weapon->getRules()->getType() : std::string())
		<< ",\"run\":" << (action.run ? 1 : 0) << ",\"mode\":" << mode << ",\"slot\":";
	if (slot) line << "\"" << slot << "\""; else line << "null";
	// RETHINK is the AI's own meta-action (think again next frame), no rule proposes it
	line << ",\"src\":" << (src ? quoted(src->src) : action.type == BA_RETHINK ? std::string("\"rethink\"") : std::string("null"))
		<< ",\"src_rec\":" << (src ? std::to_string(src->rec) : std::string("null"))
		<< ",\"score\":" << (src && src->score != INT_MIN ? std::to_string(src->score) : std::string("null"))
		<< ",\"reason\":{\"trail\":" << trail << ",\"odds\":" << jlist(pending.odds, false) << ",\"props\":" << jlist(props, false) << "}}"
		<< ",\"rule\":null}";
	Log(LOG_INFO) << line.str();
	if (pending.trace)
	{
		std::ostringstream tiles;
		for (const auto &t : pending.traced)
		{
			tiles << (tiles.tellp() > 0 ? "," : "") << quoted(t.first) << ":" << jlist(t.second, false);
		}
		Log(LOG_INFO) << "[AITRACE] {\"v\":1,\"rec\":" << rec << ",\"unit\":" << unit->getId() << ",\"tiles\":{" << tiles.str() << "}}";
	}
	// the action runs now: follow it to its end
	exec = Exec();
	exec.rec = rec;
	exec.unit = unit->getId();
	exec.side = (int)save->getSide();
	exec.turn = save->getTurn();
	exec.tu = pending.tu;
	exec.units = std::move(pending.units);
	if (slot == 'p' && src && src->src == "patrol.node" && action.type == BA_WALK && param("OXCE_AI_RECORD_PATH", 0) > 0)
	{
		exec.patrol = true;
		exec.target = action.target;
		exec.bam = (int)action.getMoveType();
		for (const auto &m : set.moves)
		{
			if (m.tu >= 0 && m.tu <= pending.tu && m.tile != pending.pos) exec.reach.push_back({ m.tile, m.tu });
		}
		const auto &visible = *unit->getVisibleUnits();
		for (const auto *bu : *save->getUnits())
		{
			if (bu->isOut() || bu->getFaction() == unit->getFaction()) continue;
			const bool sees = std::find(visible.begin(), visible.end(), bu) != visible.end();
			exec.seen += sees ? 1 : 0;
			exec.known += sees || bu->getTurnsSinceSpottedByFaction(unit->getFaction()) <= unit->getIntelligence() ? 1 : 0;
		}
		std::set<int> lof, lofTu;
		for (const auto &c : set.acts)
		{
			if (c.kind != AiCandidates::ATTACK || c.lof != 1 || (c.type != BA_SNAPSHOT && c.type != BA_AUTOSHOT && c.type != BA_AIMEDSHOT)) continue;
			lof.insert(c.target);
			if (c.tu <= pending.tu) lofTu.insert(c.target);
		}
		exec.lof = (int)lof.size();
		exec.lofTu = (int)lofTu.size();
	}
	pending.unit = -1;
}

}

void logDecision(SavedBattleGame *save, BattleUnit *unit, const BattleAction &action)
{
	if (!active())
	{
		return;
	}
	uint64_t hashUnits, hashItems, hashOrder, hashMap, hashRng;
	stateHash(save, hashUnits, hashItems, hashOrder, hashMap, hashRng);
	// the order of the deciding unit's own inventory: the AI takes the first fitting item it finds
	StateHash own;
	for (const auto *it : *unit->getInventory())
	{
		own.add((long long)itemHash(it, unit->getId()));
	}
	const int side = save->getSide();
	if (side >= 0 && side < 3 && action.type != BA_NONE)
	{
		const bool attack = action.type == BA_AUTOSHOT || action.type == BA_SNAPSHOT || action.type == BA_AIMEDSHOT
			|| action.type == BA_HIT || action.type == BA_THROW || action.type == BA_LAUNCH
			|| action.type == BA_MINDCONTROL || action.type == BA_PANIC;
		++decided[side][attack ? 1 : 0];
	}
	const AIModule *ai = unit->getAIModule();
	BattleUnit *target = unit->getAIModule() ? unit->getAIModule()->getTarget() : nullptr;
	// the other side's units this side has laid eyes on during this turn: a decision may differ legitimately after that
	std::ostringstream seen;
	for (const auto *bu : *save->getUnits())
	{
		if (bu->getFaction() != unit->getFaction() && !bu->isOut() && bu->getTurnsSinceSpottedByFaction(unit->getFaction()) == 0)
		{
			seen << (seen.tellp() > 0 ? "," : "") << bu->getId();
		}
	}
	Log(LOG_INFO) << "[AIDECIDE] turn=" << save->getTurn()
		<< " side=" << (int)save->getSide()
		<< " unit=" << unit->getId()
		<< " n=" << action.number
		<< " from=" << unit->getPosition()
		<< " tu=" << unit->getTimeUnits()
		<< " mode=" << (ai ? ai->getAIMode() : -1)
		<< " act=" << (int)action.type
		<< " to=" << action.target
		<< " run=" << (action.run ? 1 : 0)
		<< " kneel=" << (action.kneel ? 1 : 0)
		<< " aim=" << (target ? target->getId() : -1)
		<< " weapon=" << (action.weapon ? action.weapon->getRules()->getType() : std::string("-"))
		<< " seen=" << (seen.tellp() > 0 ? seen.str() : std::string("-"))
		<< " hu=" << std::hex << hashUnits << " hi=" << hashItems << " ho=" << hashOrder << " hou=" << own.h << " hm=" << hashMap << " hr=" << hashRng
		<< " hr0=" << rngBefore << " ha0=" << aiBefore << " ha=" << (ai ? ai->probeHash() : 0) << std::dec;
	if (record())
	{
		writeRecord(save, unit, action, hashUnits, hashItems, hashOrder, hashMap, hashRng);
	}
}

void logCasualty(SavedBattleGame *save, const BattleUnit *victim, const BattleUnit *killer, const std::string &weapon,
	bool dead, int hitSide, bool terrain)
{
	if (!active())
	{
		return;
	}
	// how many of the other side had eyes on the victim, and how far the killer stood: in the open, flanked, sniped
	const UnitFaction other = victim->getOriginalFaction() == FACTION_HOSTILE ? FACTION_PLAYER : FACTION_HOSTILE;
	int seenBy = 0;
	for (auto *bu : *save->getUnits())
	{
		if (bu->getFaction() == other && !bu->isOut())
		{
			const auto *vis = bu->getVisibleUnits();
			seenBy += std::find(vis->begin(), vis->end(), victim) != vis->end() ? 1 : 0;
		}
	}
	int dist = -1;
	if (killer)
	{
		const Position d = killer->getPosition() - victim->getPosition();
		dist = (int)(std::sqrt((double)(d.x * d.x + d.y * d.y)) + 0.5);
	}
	static const char *sides[] = { "front", "left", "right", "rear", "under" };
	Log(LOG_INFO) << "[AICASUALTY] turn=" << save->getTurn()
		<< " side=" << (int)save->getSide()
		<< " victim=" << victim->getId()
		<< " vfaction=" << (int)victim->getOriginalFaction()
		<< " type=" << victim->getType()
		<< " how=" << (dead ? "dead" : "stun")
		<< " pos=" << victim->getPosition()
		<< " tu=" << victim->getTimeUnits()
		<< " kneel=" << (victim->isKneeled() ? 1 : 0)
		<< " seenby=" << seenBy
		<< " killer=" << (killer ? killer->getId() : -1)
		<< " kfaction=" << (killer ? (int)killer->getFaction() : -1)
		<< " ktype=" << (killer ? killer->getType() : std::string("-"))
		<< " dist=" << dist
		<< " weapon=" << weapon
		<< " hit=" << (hitSide >= 0 && hitSide < 5 ? sides[hitSide] : "-")
		<< " terrain=" << (terrain ? 1 : 0);
}

namespace
{

/// Where each side last laid eyes on each enemy, and how far that enemy has been seen to go in a turn (docs/AI_TRAINING.md):
/// the fair threat map knows the map, the sighting and an estimate of speed - never the enemy's position now or its TUs.
struct Sighting { Position pos; int turn; };
std::map<int, Sighting> lastSeen[3];
std::map<int, double> seenReach;
const double REACH_PRIOR = 8.0; // tiles a turn before anything is observed: an average walker

bool lastSeenAt(int faction, const Position &pos)
{
	for (const auto &s : lastSeen[faction])
	{
		if (s.second.pos == pos)
			return true;
	}
	return false;
}

void updateSightings(SavedBattleGame *save)
{
	for (const auto *e : *save->getUnits())
	{
		if (e->isOut())
		{
			continue;
		}
		for (int f = 0; f < 3; ++f)
		{
			if (f == (int)e->getFaction() || e->getTurnsSinceSpottedByFaction((UnitFaction)f) != 0)
			{
				continue;
			}
			auto it = lastSeen[f].find(e->getId());
			if (it != lastSeen[f].end() && save->getTurn() > it->second.turn)
			{
				const Position d = e->getPosition() - it->second.pos;
				const double moved = std::sqrt((double)(d.x * d.x + d.y * d.y)) / (save->getTurn() - it->second.turn);
				double &reach = seenReach[e->getId()];
				reach = std::max(reach, moved); // the estimate only grows
			}
			lastSeen[f][e->getId()] = { e->getPosition(), save->getTurn() };
		}
	}
}

/// Expected number of enemies the unit's side knows of that could have a line of fire on it after their next move:
/// each is somewhere within reach x (turns since seen + 1) of its sighting; 16 fixed points of that disc (no RNG - the battle
/// must not change), the engine's own line of fire from eye height to the unit. Also how many could be within 3 tiles (melee).
void threatOf(SavedBattleGame *save, BattleUnit *unit, double &threat, int &reachable)
{
	threat = 0;
	reachable = 0;
	Tile *tile = unit->getTile();
	if (!tile)
	{
		return;
	}
	static const double ring[16][2] = { {0, 0},
		{0.5, 0}, {-0.25, 0.43}, {-0.25, -0.43}, {0.25, 0.43}, {0.25, -0.43},
		{1, 0}, {0.81, 0.59}, {0.31, 0.95}, {-0.31, 0.95}, {-0.81, 0.59}, {-1, 0}, {-0.81, -0.59}, {-0.31, -0.95}, {0.31, -0.95}, {0.81, -0.59} };
	const Position at = unit->getPosition();
	std::map<int, const BattleUnit *> byId;
	for (const auto *u : *save->getUnits())
	{
		byId[u->getId()] = u;
	}
	for (const auto &s : lastSeen[(int)unit->getFaction()])
	{
		auto e = byId.find(s.first);
		if (e == byId.end() || e->second->isOut())
		{
			continue;
		}
		auto r = seenReach.find(s.first);
		const double radius = std::max(REACH_PRIOR, r != seenReach.end() ? r->second : 0.0) * (save->getTurn() - s.second.turn + 1);
		const Position d = at - s.second.pos;
		const double dist = std::sqrt((double)(d.x * d.x + d.y * d.y));
		reachable += dist <= radius + 3 ? 1 : 0;
		if (dist > radius + 30)
		{
			continue; // too far to shoot from anywhere it can be
		}
		int hits = 0, tried = 0;
		for (const auto &p : ring)
		{
			const Position q(s.second.pos.x + (int)std::lround(p[0] * radius), s.second.pos.y + (int)std::lround(p[1] * radius), s.second.pos.z);
			if (!save->getTile(q))
			{
				continue;
			}
			++tried;
			Position origin = q.toVoxel() + Position(8, 8, 20), scan;
			hits += save->getTileEngine()->canTargetUnit(&origin, tile, &scan, nullptr, false) ? 1 : 0;
		}
		threat += tried ? (double)hits / tried : 0.0;
	}
}

/// What the unit holds and carries: each hand as type:1 (loaded or needs no ammo) / type:0 (empty),
/// weapons with ammo outside the hands (it could draw them), ammo that fits a hand weapon (it could reload).
std::string handsOf(const BattleUnit *unit)
{
	std::ostringstream out;
	const BattleItem *hands[2] = { unit->getRightHandWeapon(), unit->getLeftHandWeapon() };
	const char *names[2] = { "rh", "lh" };
	for (int i = 0; i < 2; ++i)
	{
		out << " " << names[i] << "=";
		if (hands[i])
		{
			out << hands[i]->getRules()->getType() << ":" << (hands[i]->haveAnyAmmo() ? 1 : 0);
		}
		else
		{
			out << "-";
		}
	}
	int spare = 0, ammo = 0;
	for (const auto *bi : *unit->getInventory())
	{
		if (bi == hands[0] || bi == hands[1])
		{
			continue;
		}
		const RuleItem *rule = bi->getRules();
		if ((rule->getBattleType() == BT_FIREARM || rule->getBattleType() == BT_MELEE) && bi->haveAnyAmmo())
		{
			++spare;
		}
		for (const auto *h : hands)
		{
			if (h && h->isWeaponWithAmmo() && h->getRules()->getSlotForAmmo(rule) != -1)
			{
				++ammo;
				break;
			}
		}
	}
	out << " spare=" << spare << " ammo=" << ammo;
	return out.str();
}

}

bool watchPoint(SavedBattleGame *save, const BattleUnit *unit, Position &out)
{
	static const bool on = envOn("OXCE_AI_WATCH");
	if (!on || !careful(unit))
	{
		return false;
	}
	updateSightings(save); // what the side sees now joins what it saw before; nothing it has not seen
	std::map<int, const BattleUnit *> byId;
	for (const auto *u : *save->getUnits())
	{
		byId[u->getId()] = u;
	}
	// the enemy nearest to reaching the unit: its distance from its sighting less how far it can have gone since
	double best = 1e9;
	bool found = false;
	for (const auto &s : lastSeen[(int)unit->getFaction()])
	{
		auto e = byId.find(s.first);
		if (e == byId.end() || e->second->isOut() || s.second.pos == unit->getPosition())
		{
			continue;
		}
		auto r = seenReach.find(s.first);
		const double radius = std::max(REACH_PRIOR, r != seenReach.end() ? r->second : 0.0) * (save->getTurn() - s.second.turn + 1);
		const Position d = unit->getPosition() - s.second.pos;
		const double margin = std::sqrt((double)(d.x * d.x + d.y * d.y)) - radius;
		if (margin < best)
		{
			best = margin;
			out = s.second.pos;
			found = true;
		}
	}
	return found;
}

bool halfWalk(SavedBattleGame *save, const BattleUnit *unit)
{
	static const bool on = envOn("OXCE_AI_HALF");
	if (!on || !careful(unit))
	{
		return false;
	}
	// "in contact" is the side's own memory of a living enemy: the engine's known-enemies count is kept for the alien side only
	updateSightings(save);
	std::map<int, const BattleUnit *> byId;
	for (const auto *u : *save->getUnits())
	{
		byId[u->getId()] = u;
	}
	for (const auto &s : lastSeen[(int)unit->getFaction()])
	{
		auto e = byId.find(s.first);
		if (e != byId.end() && !e->second->isOut())
		{
			return true;
		}
	}
	return false;
}

int closeEnemies(SavedBattleGame *save, const BattleUnit *unit, const Position &pos)
{
	static const bool on = envOn("OXCE_AI_GAP");
	if (!on || !careful(unit))
	{
		return 0;
	}
	// only what the side sees now: 28 % of the bot's turns ended within 2 tiles of a visible enemy, half its melee losses
	const UnitFaction own = unit->getFaction();
	int close = 0;
	for (const auto *e : *save->getUnits())
	{
		if (e->isOut() || e->getFaction() == own || e->getFaction() == FACTION_NEUTRAL
			|| e->getTurnsSinceSpottedByFaction(own) != 0 || e->getPosition().z != pos.z)
		{
			continue;
		}
		close += Position::distance2d(pos, e->getPosition()) <= 2 ? 1 : 0;
	}
	return close;
}

bool revive(SavedBattleGame *save, BattleUnit *unit, BattleAction *action, const std::vector<int> &reachable)
{
	static const bool on = envOn("OXCE_AI_REVIVE");
	if (!on || !careful(unit))
	{
		return false;
	}
	// 18.6 % of the bot's dead were lying unconscious and got finished off, and half of them one stimulant would have raised
	BattleItem *kit = nullptr;
	for (auto *item : *unit->getInventory())
	{
		const RuleItem *rule = item->getRules();
		if (rule->getBattleType() == BT_MEDIKIT && (rule->getMediKitType() == BMT_STIMULANT || rule->getMediKitType() == BMT_NORMAL)
			&& rule->getStunRecovery() > 0 && item->getStimulantQuantity() > 0
			&& rule->getAllowTargetGround() && rule->getAllowTargetFriendGround())
		{
			kit = item;
			break;
		}
	}
	if (!kit)
	{
		return false;
	}
	BattleActionCost use(BA_USE, unit, kit);
	const int useTU = use.Time + 4; // the AI's hardcoded 4 TUs for picking the kit up, as its own self-use pays
	// the same bodies the player's medikit takes: small, woundable, lying where they fell (ActionMenuState)
	auto downed = [&](BattleUnit *bu)
	{
		if (bu->getStatus() != STATUS_UNCONSCIOUS || bu->getOriginalFaction() != unit->getOriginalFaction() || bu->isBigUnit()
			|| bu->getHealth() <= 0 || (!bu->isWoundable() && !kit->getRules()->getAllowTargetImmune()))
		{
			return false;
		}
		const Tile *tile = save->getTile(bu->getPosition());
		if (!tile)
		{
			return false;
		}
		for (const auto *bi : *const_cast<Tile *>(tile)->getInventory())
		{
			if (bi->getUnit() == bu)
			{
				return true;
			}
		}
		return false;
	};
	for (auto *bu : *save->getUnits())
	{
		if (bu->getPosition() != unit->getPosition() || bu == unit || !downed(bu))
		{
			continue;
		}
		// OXCE_AI_REVIVE=2: dose on until the stun is below half the health - raised with stun just under it and no time units,
		// the comrade fell again and was killed standing (0.033 -> 0.059 a battle on r17s5..s7)
		static const bool dose = getenv("OXCE_AI_REVIVE") && atoi(getenv("OXCE_AI_REVIVE")) >= 2;
		while (kit->getStimulantQuantity() > 0 && (bu->getStatus() == STATUS_UNCONSCIOUS
			|| (dose && !bu->isOut() && bu->getStunlevel() * 2 >= bu->getHealth())))
		{
			const bool wasDown = bu->getStatus() == STATUS_UNCONSCIOUS;
			BattleAction stim;
			stim.weapon = kit;
			stim.type = BA_USE;
			stim.actor = unit;
			stim.updateTU();
			stim.Time += 4;
			if (!stim.spendTU())
			{
				tally(unit, "revive.short");
				break;
			}
			save->getTileEngine()->medikitUse(&stim, bu, BMA_STIMULANT, BODYPART_TORSO);
			tally(unit, !wasDown ? "revive.dose" : bu->getStatus() == STATUS_UNCONSCIOUS ? "revive.use" : "revive.up");
			save->getTileEngine()->medikitRemoveIfEmpty(&stim);
		}
		return false;
	}
	// no body here: walk onto the nearest one this turn's time units reach with one use to spare
	Position best;
	int bestTU = -1;
	for (auto *bu : *save->getUnits())
	{
		if (bu == unit || !downed(bu) || std::find(reachable.begin(), reachable.end(), save->getTileIndex(bu->getPosition())) == reachable.end())
		{
			continue;
		}
		const int walk = save->getPathfinding()->reachedTU(bu->getPosition());
		if (walk < 0 || walk + useTU > unit->getTimeUnits() || (bestTU >= 0 && walk >= bestTU))
		{
			continue;
		}
		bestTU = walk;
		best = bu->getPosition();
	}
	if (bestTU < 0)
	{
		return false;
	}
	tally(unit, "revive.walk");
	action->type = BA_WALK;
	action->target = best;
	action->run = false;
	return true;
}

int turretsSeeing(SavedBattleGame *save, BattleUnit *unit, const Position &pos)
{
	static const bool on = envOn("OXCE_AI_TURRET");
	if (!on || !careful(unit))
	{
		return 0;
	}
	// 12 % of the base's dead: the NINJA_RAID_SITE chaingun turret, median 15 tiles away - the engine's spotter count stops at 20
	Tile *tile = save->getTile(pos);
	if (!tile)
	{
		return 0;
	}
	updateSightings(save);
	const UnitFaction own = unit->getFaction();
	int seeing = 0;
	for (auto *e : *save->getUnits())
	{
		if (e->isOut() || e->getFaction() == own || e->getFaction() == FACTION_NEUTRAL || e->getArmor()->allowsMoving())
		{
			continue;
		}
		if (!e->getArmor()->isAlwaysVisible() && lastSeen[(int)own].find(e->getId()) == lastSeen[(int)own].end())
		{
			continue; // the side has never seen it
		}
		Position origin = save->getTileEngine()->getSightOriginVoxel(e);
		origin.z -= 2;
		Position scan;
		if (save->getTileEngine()->canTargetUnit(&origin, tile, &scan, e, false, pos != unit->getPosition() ? unit : nullptr))
		{
			++seeing;
		}
	}
	return seeing;
}

bool flee(SavedBattleGame *save, BattleUnit *unit, BattleAction *action, const std::vector<int> &reachable)
{
	static const bool on = envOn("OXCE_AI_FLEE");
	if (!on || !careful(unit))
	{
		return false;
	}
	// 5 % of the base's turns: the soldier sees an enemy, stays put and spends under a quarter of its time units - killed
	// in the enemy's turn 2.7 % (empty hands 6.6 %, health under half 36 %), 15 % of the losses in the enemy's turn;
	// the cover rules need a tile fewer see than now, and next to the enemy there is none
	// no weapon the unit can use - empty hands are not enough: armour's empty-hand weapon (STR_GAUNTLET_CLAW) is the bot's
	// top killer, 11 % of its kills, and fleeing with it cost 9.5 % of the kills and 4.9 % of the wins (f20s5, f20s9)
	const bool unarmed = !unit->getMainHandWeapon() && !unit->getUtilityWeapon(BT_MELEE);
	const bool hurt = unit->getHealth() * 2 < unit->getBaseStats()->health || unit->getStunlevel() * 2 >= unit->getHealth();
	if ((!unarmed && !hurt) || unit->getTimeUnits() * 4 < unit->getBaseStats()->tu)
	{
		return false;
	}
	const UnitFaction own = unit->getFaction();
	std::vector<BattleUnit *> seen;
	for (auto *e : *save->getUnits())
	{
		if (!e->isOut() && e->getFaction() != own && e->getFaction() != FACTION_NEUTRAL && e->getTurnsSinceSpottedByFaction(own) == 0
			&& Position::distance2d(e->getPosition(), unit->getPosition()) <= 25)
		{
			seen.push_back(e);
		}
	}
	if (seen.empty())
	{
		return false;
	}
	TileEngine *te = save->getTileEngine();
	// fewer lines of fire first, then distance to the nearest (up to 20 tiles), then the time units the walk takes
	auto score = [&](const Position &pos, int walk, int &lines)
	{
		Tile *tile = save->getTile(pos);
		int nearest = 20;
		lines = 0;
		for (auto *e : seen)
		{
			nearest = std::min(nearest, Position::distance2d(pos, e->getPosition()));
			Position origin = te->getSightOriginVoxel(e);
			origin.z -= 2;
			Position scan;
			if (te->canTargetUnit(&origin, tile, &scan, e, false, pos != unit->getPosition() ? unit : nullptr))
			{
				++lines;
			}
		}
		return -1000 * lines + 10 * nearest - walk / 10;
	};
	int hereLines = 0, bestLines = 0, lines = 0;
	int best = score(unit->getPosition(), 0, hereLines);
	bestLines = hereLines;
	Position bestPos = unit->getPosition();
	for (int index : reachable)
	{
		Position pos = save->getTileCoords(index);
		const int walk = save->getPathfinding()->reachedTU(pos);
		if (walk <= 0 || pos == unit->getPosition())
		{
			continue;
		}
		const int s = score(pos, walk, lines);
		if (s > best)
		{
			best = s;
			bestPos = pos;
			bestLines = lines;
		}
	}
	if (bestPos == unit->getPosition())
	{
		tally(unit, unarmed ? "flee.stay.unarmed" : "flee.stay.hurt");
		return false;
	}
	// out: to a tile fewer of them can shoot at; back: the same lines of fire, only farther
	tally(unit, bestLines < hereLines ? (unarmed ? "flee.out.unarmed" : "flee.out.hurt") : (unarmed ? "flee.back.unarmed" : "flee.back.hurt"));
	action->type = BA_WALK;
	action->target = bestPos;
	action->run = false; // the reachable tiles and their time units are the walking ones
	return true;
}

int maxActions(const BattleUnit *unit)
{
	// the engine moves to the next unit after 2 actions: a clawed soldier next to the enemy hits twice for 9 TU each and stands
	// with 260 of 282 left (d9probe, 127 such hits on 22 battles) - a player hits on until the enemy falls
	static const int n = getenv("OXCE_AI_ACTIONS") ? atoi(getenv("OXCE_AI_ACTIONS")) : 0;
	return n > 2 && careful(unit) ? n : 2;
}

bool patrolOutOfEnergy(SavedBattleGame *save, BattleUnit *unit, const BattleAction &action, bool pushed)
{
	static const bool on = active() && envOn("OXCE_AI_ENERGY_PATROL_END");
	if (!on || !pushed)
	{
		return false;
	}
	// the same count as [AIPATROL] v3: stop energy, a static neighbour step exists, and it costs more energy than is left
	const BattleActionMove bam = action.getMoveType();
	if (firstStep(save, unit, bam, true).stop != "energy")
	{
		return false;
	}
	int snEn, snN;
	staticStep(save, unit, bam, snEn, snN);
	return snN > 0 && unit->getEnergy() < snEn;
}

int firepointPathOver(SavedBattleGame *save, const BattleUnit *unit, int tuMax, int energyMax)
{
	static const bool on = active() && envOn("OXCE_AI_FIREPOINT_ENERGY_PATH");
	if (!on)
	{
		return 0;
	}
	// the path is the one calculate(unit, pos, BAM_NORMAL) found - often bresenhamPath, which does not look at energy at all;
	// its steps are costed the way findReachable costs them (penalty in the TU, none in the energy)
	Pathfinding *pf = save->getPathfinding();
	const std::vector<int> &path = pf->getPath();
	int tu = 0, energy = 0;
	Position p = unit->getPosition();
	for (auto it = path.rbegin(); it != path.rend(); ++it) // paths are stored in reverse order
	{
		PathfindingStep r = pf->getTUCost(p, *it, unit, nullptr, BAM_NORMAL);
		tu += r.cost.time + r.penalty.time;
		energy += r.cost.energy;
		p = r.pos;
	}
	return (energy > energyMax ? 1 : 0) | (tu > tuMax ? 2 : 0);
}

void firepointDropped(const BattleUnit *unit, int droppedByEnergy, int overByTu)
{
	if (droppedByEnergy)
	{
		++tallies[std::string(unit->getFaction() == FACTION_PLAYER ? "p." : "h.") + "firepoint.energy"];
	}
	std::ostringstream s;
	s << "firepoint.energy n" << droppedByEnergy << " t" << overByTu << " mt" << (int)unit->getMovementType() << " en" << unit->getEnergy();
	addTrail(unit, s.str().c_str());
}

void logState(SavedBattleGame *save, const char *when)
{
	if (!active())
	{
		return;
	}
	updateSightings(save);
	for (auto *bu : *save->getUnits())
	{
		if (bu->getStatus() == STATUS_DEAD || bu->getStatus() == STATUS_IGNORE_ME)
		{
			continue;
		}
		std::ostringstream sees;
		for (const auto *v : *bu->getVisibleUnits())
		{
			sees << (sees.tellp() > 0 ? "," : "") << v->getId();
		}
		// what the tile is worth (docs/AI_TRAINING.md, [AITILE] data): how many of the other side have eyes on the unit
		// right now (truth), how many of them its own side knows this turn and the nearest known one, how dark it stands
		const UnitFaction own = bu->getFaction();
		int seenBy = 0, known = 0, near = -1;
		for (auto *e : *save->getUnits())
		{
			if (e->isOut() || e->getFaction() == own || e->getFaction() == FACTION_NEUTRAL)
			{
				continue;
			}
			const auto *vis = e->getVisibleUnits();
			seenBy += std::find(vis->begin(), vis->end(), bu) != vis->end() ? 1 : 0;
			if (e->getTurnsSinceSpottedByFaction(own) == 0)
			{
				++known;
				const Position d = e->getPosition() - bu->getPosition();
				const int dist = (int)(std::sqrt((double)(d.x * d.x + d.y * d.y)) + 0.5);
				near = near < 0 ? dist : std::min(near, dist);
			}
		}
		const Tile *tile = bu->getTile();
		// the threat map only for the side whose turn just ended: its outcome comes with the next snapshot
		const bool ended = (std::string(when) == "aistart" && own == FACTION_PLAYER)
			|| ((std::string(when) == "pstart" || std::string(when) == "before") && own == FACTION_HOSTILE);
		double threat = -1;
		int reachable = -1;
		if (ended && !bu->isOut())
		{
			threatOf(save, bu, threat, reachable);
		}
		Log(LOG_INFO) << "[AISTATE] " << when
			<< " turn=" << save->getTurn()
			<< " unit=" << bu->getId()
			<< " type=" << bu->getType()
			<< " faction=" << (int)bu->getFaction()
			<< " status=" << (int)bu->getStatus()
			<< " pos=" << bu->getPosition()
			<< " dir=" << bu->getDirection()
			<< " tu=" << bu->getTimeUnits()
			<< " hp=" << bu->getHealth() << "/" << bu->getBaseStats()->health
			<< " stun=" << bu->getStunlevel()
			<< " morale=" << bu->getMorale()
			<< " kneel=" << (bu->isKneeled() ? 1 : 0)
			<< " weapon=" << (bu->getMainHandWeapon() ? bu->getMainHandWeapon()->getRules()->getType() : std::string("-"))
			<< " spotted=" << bu->getTurnsSinceSpottedByFaction(FACTION_HOSTILE)
			<< " sniped=" << bu->getTurnsLeftSpottedForSnipersByFaction(FACTION_HOSTILE)
			<< " sees=" << (sees.tellp() > 0 ? sees.str() : std::string("-"))
			<< " seenby=" << seenBy
			<< " known=" << known
			<< " near=" << near
			<< " shade=" << (tile ? tile->getShade() : -1)
			<< " tumax=" << bu->getBaseStats()->tu
			<< " wounds=" << bu->getFatalWounds()
			<< " threat=" << threat
			<< " reach=" << reachable
			<< handsOf(bu);
	}
}

#endif

}

}
