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
#include <chrono>
#include <climits>
#include <iterator>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <map>
#include <unordered_map>
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
#include "../Engine/Options.h"
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
bool pathProf() { return false; }
void pathAsk(int, int, const BattleUnit *, const Position &, const Position &, int, const BattleUnit *, int, int, int, unsigned long long, int, int, long long, const void *) {}
bool reachWanted(const BattleUnit *, const BattleActionCost &) { return false; }
void reachTaken(SavedBattleGame *, std::vector<std::pair<int, int>> &&) {}
bool ambushProf() { return false; }
void ambushBegin(SavedBattleGame *, const BattleUnit *, const BattleUnit *) {}
void ambushNode(int) {}
void ambushMark() {}
void ambushOwn(bool, int, int) {}
void ambushEnemy(const Position &, bool, int, int, int, int, int, int) {}
void ambushScored(int, bool, bool) {}
void ambushEnd(bool, int, const Position &, int, bool) {}
int ambushMemo() { return 0; }
void ambushMemoNode(const Position &, bool, bool, int, int, int) {}
bool escapeProf() { return false; }
void escapeBegin(const BattleUnit *) {}
void escapeTarget() {}
void escapeMark() {}
void escapeProbe(const BattleUnit *, int) {}
bool escapeReachFirst() { return false; }
void escapeSkipped() {}
bool walkFovProf() { return false; }
void walkFovBefore(BattlescapeGame *, const BattleUnit *) {}
void walkFovAfter(BattlescapeGame *, const BattleUnit *) {}
void walkFovConfirm(BattlescapeGame *, const BattleUnit *) {}
int walkFovSkip() { return 0; }
bool walkFovKeep(BattlescapeGame *, const BattleUnit *) { return true; }
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
void walkStop(const BattleUnit *, const char *, const Position &, int, int, int, int, int, SavedBattleGame *) {}
bool patrolOutOfEnergy(SavedBattleGame *, BattleUnit *, const BattleAction &, bool) { return false; }
int firepointPathOver(SavedBattleGame *, const BattleUnit *, int, int) { return 0; }
void firepointDropped(const BattleUnit *, int, int) {}
void firepointBlocked(BattleUnit *, const BattleAction &, int) {}
unsigned long long knownRevision(SavedBattleGame *, const BattleUnit *) { return 0; }
bool firepointBlockedSalt() { return false; }
void blockedStepStop(SavedBattleGame *, BattleUnit *, int) {}
void blockedStepDecide(SavedBattleGame *, BattleUnit *) {}
void blockedStepPlan(SavedBattleGame *, BattleUnit *, const BattleAction &) {}
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
/// REPEATED_BLOCKED_STEP (passive): each unit's last stop at a unit - turn, the tile it stood on (and still must stand
/// on), knownRevision then; its next decisions there this turn record kr.dec and walk.first
struct StopMem { int turn = -1; Position from; unsigned long long kr = 0; };
std::map<int, StopMem> stopMem;
/// REPEATED_BLOCKED_STEP_V1 (OXCE_AI_BLOCKED_STEP): per unit, the steps that stopped at a unit from one tile in one unit-turn
/// at one knownRevision; the counts of the battle per side, and the steps suppressed per unit-turn
struct BlockedSteps { int turn = -1; Position from; unsigned long long kr = 0; std::vector<int> dirs; };
std::map<int, BlockedSteps> blockedSteps;
struct BlockedStepCount { int recorded = 0, suppressed = 0, rerouted = 0, noPath = 0, invRevision = 0, invTurn = 0; std::map<std::string, int> bySource; };
BlockedStepCount blockedCount[3];
std::map<std::pair<int, int>, std::vector<int>> blockedPerTurn;
/// the source of each unit's last decision as the record took it ("?" without the record)
std::map<int, std::string> decisionSource;
/// the decision record's reason trail (defined with the record below)
void addTrail(const BattleUnit *unit, const char *what);
/// is the decision record on (defined with the record below)
bool record();
/// did the faction last see an enemy on this tile (defined with the sightings below)
bool lastSeenAt(int faction, const Position &pos);
/// the decision record at a new side's turn and at the end of the battle (defined with the record below)
void recordTurn(SavedBattleGame *save);
void recordEnd(SavedBattleGame *save);
/// the pathfinding profile's totals and call sites at the end of the battle (defined with the profile below)
void pathReport();
/// the record's reuse of the think's reach and the ambush profile, their totals at the end of the battle (defined below)
void reachReport();
void ambushReport();
/// the escape audit's totals at the end of the battle (defined with the ambush profile below)
void escapeReport();
/// the FOV-on-step audit's totals at the end of the battle (defined with the escape audit below)
void walkFovReport();
void walkFovSkipReport();
/// REPEATED_BLOCKED_STEP_V1's totals at the end of the battle (defined with the rule below)
void blockedStepReport();

void logStart(SavedBattleGame *save)
{
	started = true;
	stopMem.clear();
	blockedSteps.clear();
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
	pathReport();
	reachReport();
	ambushReport();
	escapeReport();
	walkFovReport();
	walkFovSkipReport();
	blockedStepReport();
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

void walkStop(const BattleUnit *unit, const char *reason, const Position &to, int dir, int bam, int stepTu, int stepEnergy, int blocker,
	SavedBattleGame *save)
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
	if (save)
	{
		const unsigned long long kr = knownRevision(save, unit);
		s << " kr" << std::hex << kr << std::dec;
		stopMem[unit->getId()] = { save->getTurn(), from, kr };
	}
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
	/// the set has no moves yet: they come from the think's own findReachable (reachWanted / reachTaken), or after the think
	bool wantReach = false;
	int energy = 0;
	std::map<int, Snapshot> units;
	std::vector<Proposal> proposals;
	std::vector<std::string> trail;
	std::vector<std::string> odds;
	char slot = 0;
	bool trace = false;
	std::map<std::string, std::vector<std::string>> traced;
	/// REPEATED_BLOCKED_STEP: the unit stands where it was stopped this turn - knownRevision as it starts to think
	bool krWatch = false;
	unsigned long long krDec = 0;
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
	/// REPEATED_BLOCKED_STEP: record the walk's first step (walk.first)
	bool krWatch = false;
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

/// The record takes the think's reach (OXCE_AI_RECORD_REUSE, on unless set to 0).
bool reachReuse()
{
	static const bool on = []
	{
		const char *s = getenv("OXCE_AI_RECORD_REUSE");
		return !(s && *s == '0');
	}();
	return on;
}
/// Decisions whose moves came from the think (taken), whose the record asked for itself before the think because the think
/// might spend first (own), whose came from the record's own ask after the think (fallback), and how many asks of the thinking
/// unit came at other time units or energy than it started with (tudiff); the fallback asks' time.
int reachTakenN = 0, reachOwnN = 0, reachFallbackN = 0, reachTuDiffN = 0;
/// Why the record asked itself before the think: the freeze workaround, a reload, the medikit check (spendsBeforeThink).
int reachOwnAbortN = 0, reachOwnReloadN = 0, reachOwnMedikitN = 0;
long long reachFallbackNs = 0;

void reachReport()
{
	if (!record())
	{
		return;
	}
	Log(LOG_INFO) << "[AIREUSE] reuse=" << (reachReuse() ? 1 : 0) << " taken=" << reachTakenN << " own=" << reachOwnN << " abort=" << reachOwnAbortN
		<< " reload=" << reachOwnReloadN << " medikit=" << reachOwnMedikitN << " fallback=" << reachFallbackN
		<< " tudiff=" << reachTuDiffN << " fallback_us=" << reachFallbackNs / 1000;
}

/// May BattleUnit::think spend time units before the AI asks for its reach? AIModule::think clears the time units after 200
/// aborted walks (1); BattleUnit::think reloads a hand weapon short of ammo when the inventory holds a clip for its empty slot
/// (BattleUnit::reloadAmmo, 2) and once a turn runs the medikit check, whose gates before the dice are the unit's wounds, stun
/// and energy and a medikit it may use on itself now (AIModule::medikit_think steps 2 and 3; 3). The record asked for its
/// reach before all that, so on such a decision it keeps asking itself: the think's reach would be another one. Mirrors the
/// gates, never the dice: says yes whenever it cannot rule the spend out, and only the saving is lost then. 0 - no spend.
int spendsBeforeThink(const SavedBattleGame *save, const BattleUnit *unit)
{
	if (unit->getAIModule() && unit->getAIModule()->getWalkAbortCounter() > 200)
	{
		return 1;
	}
	for (const BattleItem *w : { unit->getRightHandWeapon(), unit->getLeftHandWeapon() })
	{
		if (!w || !w->isWeaponWithAmmo() || w->haveAllAmmo())
		{
			continue;
		}
		for (const auto *bi : *unit->getInventory())
		{
			const int slot = w->getRules()->getSlotForAmmo(bi->getRules());
			if (slot != -1 && !w->getAmmoForSlot(slot))
			{
				return 2;
			}
		}
	}
	if (!unit->isAiMedikitUsed())
	{
		const int stamina = unit->getBaseStats()->stamina;
		const bool heal = unit->getFatalWounds() > 0;
		const bool stim = unit->getStunlevel() > 0 || stamina <= 0 || unit->getEnergy() * 100 / stamina < 40;
		for (const auto *bi : *unit->getInventory())
		{
			const RuleItem *r = bi->getRules();
			if (r->getBattleType() != BT_MEDIKIT || !r->getAllowTargetSelf() || save->getTurn() < r->getAIUseDelay(save->getMod()))
			{
				continue;
			}
			const BattleMediKitType t = r->getMediKitType();
			if ((heal && (t == BMT_HEAL || t == BMT_NORMAL)) || (stim && (t == BMT_STIMULANT || t == BMT_NORMAL)))
			{
				return 3;
			}
		}
	}
	return 0;
}

/// The decision's moves are still wanted after the think: the record asks itself, as it did before the think without reuse.
void reachFallback(SavedBattleGame *save, const BattleUnit *unit)
{
	if (!pending.wantReach || pending.unit != unit->getId())
	{
		return;
	}
	const auto t0 = std::chrono::steady_clock::now();
	AiCandidates::addMoves(save, pending.set, AiCandidates::reach(save, unit));
	pending.wantReach = false;
	++reachFallbackN;
	reachFallbackNs += std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now() - t0).count();
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

namespace
{

/// The pathfinding profile (pathProf): the asks of the decision being made, keyed by what they ask. An ask asked again
/// within the decision is a repeat; asked in the next decision with the battle unchanged (pathRevision) - a cross repeat.
struct PathAskStat { int n = 0; uint64_t answer = 0; int algo = 0, len = 0, cost = 0; long long ns = 0; const void *site = nullptr; };
struct PathSiteStat { int kind = 0; long long n = 0, rep = 0, ns = 0, repNs = 0; };
struct PathCounts
{
	long long calls = 0, rep = 0, ns = 0, repNs = 0, cross = 0, crossNs = 0, mismatch = 0, crossMismatch = 0;
	long long calc = 0, reach = 0, bres = 0, astar = 0, nopath = 0;
	void add(const PathCounts &o)
	{
		calls += o.calls; rep += o.rep; ns += o.ns; repNs += o.repNs; cross += o.cross; crossNs += o.crossNs;
		mismatch += o.mismatch; crossMismatch += o.crossMismatch;
		calc += o.calc; reach += o.reach; bres += o.bres; astar += o.astar; nopath += o.nopath;
	}
};
struct PathDecision : PathCounts
{
	bool open = false;
	int unit = 0;
	bool sameRev = false;
	uint64_t rev = 0;
	std::chrono::steady_clock::time_point t0;
	std::unordered_map<uint64_t, PathAskStat> asks;
};
PathDecision pathNow, pathLast;
/// the battle's totals; pathOutside - asks made between decisions (the walk itself, the game's own checks)
PathCounts pathAll, pathOutside;
long long pathDecisions = 0, pathSameRev = 0, pathThinkNs = 0, pathUniq = 0, pathMisLogged = 0;
std::map<const void *, PathSiteStat> pathSites;

/// A repeat that came back different: the first 40 per battle in full, to see what the same ask can answer differently
void pathMismatch(const char *how, int kind, const BattleUnit *unit, const Position &from, const Position &to, int bam, int maxTU,
	int tu, int energy, const PathAskStat &was, int algo, int len, int cost, long long ns, const void *site)
{
	if (pathMisLogged++ >= 40)
	{
		return;
	}
	Log(LOG_INFO) << "[AIPF] " << how << " kind=" << (kind == 1 ? "calc" : "reach") << " unit=" << unit->getId() << " from=" << from << " to=" << to
		<< " bam=" << bam << " max=" << maxTU << " tu=" << tu << " en=" << energy
		<< " was=" << was.algo << "/" << was.len << "/" << was.cost << " now=" << algo << "/" << len << "/" << cost
		<< " us=" << was.ns / 1000 << "/" << ns / 1000 << " nth=" << was.n + 1
		<< " site0=0x" << std::hex << reinterpret_cast<std::uintptr_t>(was.site) << " site=0x" << reinterpret_cast<std::uintptr_t>(site) << std::dec;
}

/// What the pathfinder's answers depend on besides the ask: where every unit stands (a unit blocks a tile) and whether it is
/// out, the map's parts, doors, fire and smoke. Not the TU: the asking unit's budget is in the key, the others' do not matter.
uint64_t pathRevision(SavedBattleGame *save)
{
	StateHash h;
	for (const auto *bu : *save->getUnits())
	{
		h.add(bu->getId());
		h.add(bu->getPosition().x); h.add(bu->getPosition().y); h.add(bu->getPosition().z);
		h.add((int)bu->getStatus()); h.add(bu->isOut() ? 1 : 0);
	}
	for (int i = 0; i < save->getMapSizeXYZ(); ++i)
	{
		Tile *tile = save->getTile(i);
		for (int part = O_FLOOR; part < O_MAX; ++part)
		{
			int id = -1, set = -1;
			tile->getMapData(&id, &set, (TilePart)part);
			h.add(id * 256 + set);
			h.add(tile->isUfoDoorOpen((TilePart)part) ? 1 : 0);
		}
		h.add(tile->getFire()); h.add(tile->getSmoke());
	}
	return h.h;
}

void pathOpen(SavedBattleGame *save, const BattleUnit *unit)
{
	if (!pathProf())
	{
		return;
	}
	pathLast = std::move(pathNow);
	pathNow = PathDecision();
	pathNow.open = true;
	pathNow.unit = unit->getId();
	pathNow.rev = pathRevision(save);
	pathNow.sameRev = pathLast.unit != 0 && pathLast.rev == pathNow.rev;
	pathNow.t0 = std::chrono::steady_clock::now();
}

/// One line per decision: what it asked, how much of it again, what it cost (microseconds), against the time of the whole think.
void pathClose(const BattleUnit *unit)
{
	if (!pathProf() || !pathNow.open)
	{
		return;
	}
	const long long thinkNs = std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now() - pathNow.t0).count();
	Log(LOG_INFO) << "[AIPF] unit=" << unit->getId() << " same=" << (pathNow.sameRev ? 1 : 0) << " tt=" << thinkNs / 1000
		<< " n=" << pathNow.calls << " u=" << pathNow.asks.size() << " r=" << pathNow.rep << " t=" << pathNow.ns / 1000 << " tr=" << pathNow.repNs / 1000
		<< " x=" << pathNow.cross << " tx=" << pathNow.crossNs / 1000 << " mis=" << pathNow.mismatch << " xmis=" << pathNow.crossMismatch
		<< " calc=" << pathNow.calc << " reach=" << pathNow.reach << " bres=" << pathNow.bres << " astar=" << pathNow.astar << " nopath=" << pathNow.nopath;
	pathAll.add(pathNow);
	++pathDecisions;
	pathSameRev += pathNow.sameRev ? 1 : 0;
	pathThinkNs += thinkNs;
	pathUniq += (long long)pathNow.asks.size();
	pathNow.open = false;
}

void pathReport()
{
	if (!pathProf())
	{
		return;
	}
	// the anchor is a function of this build: path_prof.py takes its address in the exe (nm) to turn every site into a name
	Log(LOG_INFO) << "[AIPF] total decisions=" << pathDecisions << " same=" << pathSameRev << " tt=" << pathThinkNs / 1000
		<< " n=" << pathAll.calls << " u=" << pathUniq << " r=" << pathAll.rep << " t=" << pathAll.ns / 1000 << " tr=" << pathAll.repNs / 1000
		<< " x=" << pathAll.cross << " tx=" << pathAll.crossNs / 1000 << " mis=" << pathAll.mismatch << " xmis=" << pathAll.crossMismatch
		<< " calc=" << pathAll.calc << " reach=" << pathAll.reach << " bres=" << pathAll.bres << " astar=" << pathAll.astar << " nopath=" << pathAll.nopath
		<< " outside_n=" << pathOutside.calls << " outside_t=" << pathOutside.ns / 1000
		<< " outside_calc=" << pathOutside.calc << " outside_reach=" << pathOutside.reach
		<< " anchor=0x" << std::hex << reinterpret_cast<std::uintptr_t>(&active) << std::dec;
	std::vector<std::pair<const void *, PathSiteStat>> sites(pathSites.begin(), pathSites.end());
	std::sort(sites.begin(), sites.end(), [](const auto &a, const auto &b) { return a.second.ns > b.second.ns; });
	for (const auto &s : sites)
	{
		Log(LOG_INFO) << "[AIPF] site=0x" << std::hex << reinterpret_cast<std::uintptr_t>(s.first) << std::dec
			<< " kind=" << (s.second.kind == 1 ? "calc" : "reach") << " n=" << s.second.n << " r=" << s.second.rep
			<< " t=" << s.second.ns / 1000 << " tr=" << s.second.repNs / 1000;
	}
}

}

bool pathProf()
{
	static const bool on = active() && envOn("OXCE_AI_PATHPROF");
	return on;
}

void pathAsk(int kind, int algo, const BattleUnit *unit, const Position &from, const Position &to, int bam,
	const BattleUnit *missileTarget, int maxTU, int tu, int energy, unsigned long long answer, int len, int cost, long long ns, const void *site)
{
	if (!pathProf())
	{
		return;
	}
	PathSiteStat &s = pathSites[site];
	s.kind = kind;
	++s.n;
	s.ns += ns;
	if (!pathNow.open)
	{
		++pathOutside.calls;
		pathOutside.ns += ns;
		++(kind == 1 ? pathOutside.calc : pathOutside.reach);
		return;
	}
	StateHash k;
	k.add(kind); k.add(unit->getId());
	k.add(from.x); k.add(from.y); k.add(from.z); k.add(to.x); k.add(to.y); k.add(to.z);
	k.add(bam); k.add(missileTarget ? missileTarget->getId() : -1); k.add(maxTU); k.add(tu); k.add(energy);
	PathAskStat &a = pathNow.asks[k.h];
	if (a.n > 0)
	{
		++pathNow.rep;
		pathNow.repNs += ns;
		++s.rep;
		s.repNs += ns;
		if (a.answer != answer)
		{
			++pathNow.mismatch;
			pathMismatch("mis", kind, unit, from, to, bam, maxTU, tu, energy, a, algo, len, cost, ns, site);
		}
	}
	else
	{
		a.answer = answer;
		a.algo = algo; a.len = len; a.cost = cost; a.ns = ns; a.site = site;
		if (pathNow.sameRev)
		{
			auto p = pathLast.asks.find(k.h);
			if (p != pathLast.asks.end())
			{
				++pathNow.cross;
				pathNow.crossNs += ns;
				if (p->second.answer != answer)
				{
					++pathNow.crossMismatch;
					pathMismatch("xmis", kind, unit, from, to, bam, maxTU, tu, energy, p->second, algo, len, cost, ns, site);
				}
			}
		}
	}
	++a.n;
	++pathNow.calls;
	pathNow.ns += ns;
	++(kind == 1 ? pathNow.calc : pathNow.reach);
	if (algo == 1) ++pathNow.bres;
	else if (algo == 2) ++pathNow.astar;
	else if (algo == 3) ++pathNow.nopath;
}

void beforeThink(SavedBattleGame *save, BattleUnit *unit)
{
	if (!active())
	{
		return;
	}
	rngBefore = RNG::getSeed();
	aiBefore = unit->getAIModule() ? unit->getAIModule()->probeHash() : 0;
	pathOpen(save, unit);
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
		pending.energy = unit->getEnergy();
		const auto mem = stopMem.find(unit->getId());
		if (mem != stopMem.end() && mem->second.turn == save->getTurn() && mem->second.from == unit->getPosition())
		{
			pending.krWatch = true;
			pending.krDec = knownRevision(save, unit);
		}
		const int spends = reachReuse() ? spendsBeforeThink(save, unit) : 0;
		if (reachReuse() && !spends)
		{
			// the moves come from the think's own findReachable (reachTaken), the same ask this would make
			pending.set = AiCandidates::generate(save, unit, false);
			pending.wantReach = true;
		}
		else
		{
			pending.set = AiCandidates::generate(save, unit);
			if (spends)
			{
				++reachOwnN;
				++(spends == 1 ? reachOwnAbortN : spends == 2 ? reachOwnReloadN : reachOwnMedikitN);
			}
		}
		// the list must not change the battle: it may not draw a random number
		pending.rngTouched = RNG::getSeed() != rngBefore;
	}
}

bool reachWanted(const BattleUnit *unit, const BattleActionCost &cost)
{
	if (!record() || !pending.wantReach || pending.unit != unit->getId() || cost.Time != 0 || cost.Energy != 0)
	{
		return false;
	}
	if (unit->getTimeUnits() != pending.tu || unit->getEnergy() != pending.energy)
	{
		// the think spent before it asked (the AI freeze workaround clears the time units): not the record's ask
		++reachTuDiffN;
		return false;
	}
	return true;
}

void reachTaken(SavedBattleGame *save, std::vector<std::pair<int, int>> &&reach)
{
	AiCandidates::addMoves(save, pending.set, reach);
	pending.wantReach = false;
	++reachTakenN;
}

namespace
{

/// One setupAmbush call under the ambush profile.
struct AmbushCall
{
	bool open = false;
	int unit = -1, enemy = -1, enemyTu = 0;
	Position unitPos, enemyPos;
	std::chrono::steady_clock::time_point t0, mark;
	/// nodes per stage: looked at, near and in reach, hidden, own path ok
	int stage[4] = {};
	/// own searches: count, got there, expanded nodes, time
	int ownN = 0, ownOk = 0, ownExp = 0;
	long long ownNs = 0;
	/// enemy searches: got there or not, their expanded nodes and time apart, best changes
	int eok = 0, efail = 0, expOk = 0, expFail = 0, taken = 0;
	long long nsOk = 0, nsFail = 0;
	/// the negative memo: searches skipped, searches run to verify it and how many of those disagreed
	int memoSkip = 0, memoVerify = 0, memoBad = 0;
	/// the enemy search waiting for its score line
	bool nodeOpen = false;
	std::ostringstream node;
};
AmbushCall amb;
/// totals over the battle: calls, calls that chose a node, calls that stopped early, and the sums of the fields above
int ambCalls = 0, ambChosen = 0, ambFast = 0;
long long ambStage[4] = {}, ambOwnN = 0, ambOwnOk = 0, ambOwnExp = 0, ambOwnNs = 0;
long long ambEok = 0, ambEfail = 0, ambExpOk = 0, ambExpFail = 0, ambNsOk = 0, ambNsFail = 0, ambTaken = 0, ambNs = 0;
/// the negative memo over the battle, counted with or without the profile (the gate reads this line)
long long memoSkipN = 0, memoVerifyN = 0, memoBadN = 0;

void ambushReport()
{
	if (ambushMemo())
	{
		Log(LOG_INFO) << "[AIAMBMEMO] mode=" << ambushMemo() << " skip=" << memoSkipN << " verify=" << memoVerifyN << " bad=" << memoBadN;
	}
	if (!ambushProf())
	{
		return;
	}
	Log(LOG_INFO) << "[AIAMB] total calls=" << ambCalls << " chosen=" << ambChosen << " fast=" << ambFast
		<< " nodes=" << ambStage[0] << " near=" << ambStage[1] << " hidden=" << ambStage[2] << " own=" << ambStage[3]
		<< " ownn=" << ambOwnN << " ownok=" << ambOwnOk << " ownexp=" << ambOwnExp << " ownus=" << ambOwnNs / 1000
		<< " eok=" << ambEok << " efail=" << ambEfail << " expok=" << ambExpOk << " expfail=" << ambExpFail
		<< " tok=" << ambNsOk / 1000 << " tfail=" << ambNsFail / 1000 << " taken=" << ambTaken
		<< " memo=" << memoSkipN << " mver=" << memoVerifyN << " mbad=" << memoBadN << " us=" << ambNs / 1000;
}

/// The escape audit (OXCE_AI_ESCAPEPROF): per faction, setupEscape calls and its candidate tiles - with no tile, reachable,
/// unreachable - with the canTargetUnit traces getSpottingUnits ran for each kind and the time they took.
struct EscapeCount { long long calls = 0, notile = 0, reach = 0, unreach = 0, traceReach = 0, traceUnreach = 0, nsReach = 0, nsUnreach = 0; };
EscapeCount esc[3];
/// canTargetUnit traces of getSpottingUnits so far (any caller), and where the candidate's count and clock started
long long escTraces = 0, escTraceMark = 0;
std::chrono::steady_clock::time_point escMark;
/// candidates dropped before their traces by ESCAPE_REACH_FIRST_V1 (counted without the profile)
long long escSkipN = 0;

void escapeReport()
{
	if (active())
	{
		// the flag's own line, written without the profile: the proof of which artefact played (R-087, R-105)
		Log(LOG_INFO) << "[AIESCRF] mode=" << (escapeReachFirst() ? 1 : 0) << " skipped=" << escSkipN;
	}
	if (!escapeProf())
	{
		return;
	}
	static const char *const sides[3] = { "player", "hostile", "neutral" };
	auto put = [](const char *side, const EscapeCount &e)
	{
		Log(LOG_INFO) << "[AIESC] side=" << side << " escape_calls=" << e.calls
			<< " escape_candidates_total=" << e.notile + e.reach + e.unreach << " escape_candidates_reachable=" << e.reach
			<< " escape_candidates_unreachable=" << e.unreach << " escape_candidates_notile=" << e.notile
			<< " canTargetUnit_calls_on_reachable=" << e.traceReach << " canTargetUnit_calls_on_unreachable=" << e.traceUnreach
			<< " time_on_reachable_us=" << e.nsReach / 1000 << " time_wasted_on_unreachable_us=" << e.nsUnreach / 1000;
	};
	EscapeCount all;
	for (int f = 0; f < 3; ++f)
	{
		const EscapeCount &e = esc[f];
		if (!e.calls) continue;
		put(sides[f], e);
		all.calls += e.calls; all.notile += e.notile; all.reach += e.reach; all.unreach += e.unreach;
		all.traceReach += e.traceReach; all.traceUnreach += e.traceUnreach; all.nsReach += e.nsReach; all.nsUnreach += e.nsUnreach;
	}
	put("all", all);
}

}

bool ambushProf()
{
	static const bool on = active() && envOn("OXCE_AI_AMBUSHPROF");
	return on;
}

int ambushMemo()
{
	static const int mode = active() ? (int)param("OXCE_AI_AMBUSH_MEMO", 0) : 0;
	return mode;
}

void ambushMemoNode(const Position &pos, bool skipped, bool ok, int own, int score, int best)
{
	if (skipped) { ++memoSkipN; } else { ++memoVerifyN; memoBadN += ok ? 1 : 0; }
	if (!amb.open)
	{
		return;
	}
	if (!skipped)
	{
		++amb.memoVerify;
		amb.memoBad += ok ? 1 : 0;
		return; // the search ran: ambushEnemy writes its line as usual
	}
	++amb.memoSkip;
	Log(LOG_INFO) << "[AIAMBN] u=" << amb.unit << " e=" << amb.enemy << " pos=" << pos.x << "," << pos.y << "," << pos.z
		<< " d=" << Position::distance2d(pos, amb.unitPos) << " de=" << Position::distance2d(pos, amb.enemyPos) << " dze=" << pos.z - amb.enemyPos.z
		<< " own=" << own << " ok=0 cost=0 len=0 exp=0 us=0 s0=" << score << " best=" << best << " cover=-1 s=" << score << " take=0 memo=1";
}

void ambushBegin(SavedBattleGame *save, const BattleUnit *unit, const BattleUnit *enemy)
{
	if (!ambushProf())
	{
		return;
	}
	(void)save;
	amb = AmbushCall();
	amb.open = true;
	amb.unit = unit->getId();
	amb.enemy = enemy->getId();
	amb.enemyTu = enemy->getTimeUnits();
	amb.unitPos = unit->getPosition();
	amb.enemyPos = enemy->getPosition();
	amb.t0 = std::chrono::steady_clock::now();
}

void ambushNode(int stage)
{
	if (amb.open && stage >= 0 && stage < 4)
	{
		++amb.stage[stage];
	}
}

void ambushMark()
{
	if (amb.open)
	{
		amb.mark = std::chrono::steady_clock::now();
	}
}

void ambushOwn(bool ok, int tu, int expanded)
{
	if (!amb.open)
	{
		return;
	}
	(void)tu;
	++amb.ownN;
	amb.ownOk += ok ? 1 : 0;
	amb.ownExp += expanded;
	amb.ownNs += std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now() - amb.mark).count();
}

void ambushEnemy(const Position &pos, bool ok, int cost, int len, int expanded, int own, int score, int best)
{
	if (!amb.open)
	{
		return;
	}
	const long long ns = std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now() - amb.mark).count();
	if (ok) { ++amb.eok; amb.expOk += expanded; amb.nsOk += ns; }
	else { ++amb.efail; amb.expFail += expanded; amb.nsFail += ns; }
	// one line per enemy search: where, how far from both, what the unit's own path cost, what the enemy's search gave and cost,
	// the score before cover against the best so far; the cover and the outcome follow from ambushScored when the enemy got there
	amb.node.str("");
	amb.node << "[AIAMBN] u=" << amb.unit << " e=" << amb.enemy << " pos=" << pos.x << "," << pos.y << "," << pos.z
		<< " d=" << Position::distance2d(pos, amb.unitPos) << " de=" << Position::distance2d(pos, amb.enemyPos) << " dze=" << pos.z - amb.enemyPos.z
		<< " own=" << own << " ok=" << (ok ? 1 : 0) << " cost=" << cost << " len=" << len << " exp=" << expanded << " us=" << ns / 1000
		<< " s0=" << score << " best=" << best;
	if (ok)
	{
		amb.nodeOpen = true;
	}
	else
	{
		Log(LOG_INFO) << amb.node.str() << " cover=-1 s=" << score << " take=0";
	}
}

void ambushScored(int score, bool cover, bool taken)
{
	if (!amb.open || !amb.nodeOpen)
	{
		return;
	}
	amb.nodeOpen = false;
	amb.taken += taken ? 1 : 0;
	Log(LOG_INFO) << amb.node.str() << " cover=" << (cover ? 1 : 0) << " s=" << score << " take=" << (taken ? 1 : 0);
}

void ambushEnd(bool chosen, int best, const Position &target, int tus, bool fast)
{
	if (!amb.open)
	{
		return;
	}
	amb.open = false;
	const long long ns = std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now() - amb.t0).count();
	Log(LOG_INFO) << "[AIAMB] u=" << amb.unit << " e=" << amb.enemy << " etu=" << amb.enemyTu
		<< " upos=" << amb.unitPos.x << "," << amb.unitPos.y << "," << amb.unitPos.z << " epos=" << amb.enemyPos.x << "," << amb.enemyPos.y << "," << amb.enemyPos.z
		<< " nodes=" << amb.stage[0] << " near=" << amb.stage[1] << " hidden=" << amb.stage[2] << " own=" << amb.stage[3]
		<< " ownn=" << amb.ownN << " ownok=" << amb.ownOk << " ownexp=" << amb.ownExp << " ownus=" << amb.ownNs / 1000
		<< " eok=" << amb.eok << " efail=" << amb.efail << " expok=" << amb.expOk << " expfail=" << amb.expFail
		<< " tok=" << amb.nsOk / 1000 << " tfail=" << amb.nsFail / 1000 << " taken=" << amb.taken
		<< " memo=" << amb.memoSkip << " mver=" << amb.memoVerify << " mbad=" << amb.memoBad
		<< " chosen=" << (chosen ? 1 : 0) << " best=" << best << " target=" << target.x << "," << target.y << "," << target.z << " tus=" << tus
		<< " fast=" << (fast ? 1 : 0) << " us=" << ns / 1000;
	++ambCalls;
	ambChosen += chosen ? 1 : 0;
	ambFast += fast ? 1 : 0;
	for (int i = 0; i < 4; ++i) ambStage[i] += amb.stage[i];
	ambOwnN += amb.ownN; ambOwnOk += amb.ownOk; ambOwnExp += amb.ownExp; ambOwnNs += amb.ownNs;
	ambEok += amb.eok; ambEfail += amb.efail; ambExpOk += amb.expOk; ambExpFail += amb.expFail;
	ambNsOk += amb.nsOk; ambNsFail += amb.nsFail; ambTaken += amb.taken; ambNs += ns;
}

bool escapeProf()
{
	static const bool on = active() && envOn("OXCE_AI_ESCAPEPROF");
	return on;
}

void escapeBegin(const BattleUnit *unit)
{
	if (escapeProf()) ++esc[(int)unit->getFaction()].calls;
}

void escapeTarget()
{
	if (escapeProf()) ++escTraces;
}

void escapeMark()
{
	if (!escapeProf())
	{
		return;
	}
	escTraceMark = escTraces;
	escMark = std::chrono::steady_clock::now();
}

void escapeProbe(const BattleUnit *unit, int kind)
{
	if (!escapeProf())
	{
		return;
	}
	EscapeCount &e = esc[(int)unit->getFaction()];
	if (kind == 2)
	{
		++e.notile;
		return;
	}
	const long long ns = std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now() - escMark).count();
	const long long traces = escTraces - escTraceMark;
	if (kind == 1) { ++e.reach; e.traceReach += traces; e.nsReach += ns; }
	else { ++e.unreach; e.traceUnreach += traces; e.nsUnreach += ns; }
}

bool escapeReachFirst()
{
	static const bool on = active() && envOn("OXCE_AI_ESCAPE_REACH_FIRST");
	return on;
}

void escapeSkipped()
{
	++escSkipN;
}

namespace
{

/// The FOV-on-step audit (OXCE_AI_WALKFOVPROF, docs/research/ai-path-audit-2026-10-01.md, п. 14). UnitWalkBState::think calls
/// BattlescapeState::updateSoldierInfo after every finished step "to update the TU display"; on the player's side that call
/// recalculates the selected unit's whole field of view - its visible tiles and units - and the step's own event FOV around
/// the walker follows a few lines later. The audit reads only: a snapshot of the selected unit's sight before the call, one
/// after it, one more after the step's FOV - what the call changed, what of that the step's FOV kept, how long the call took.
struct WalkFovSnap
{
	std::vector<const BattleUnit *> units;   // the selected unit's visible units, sorted
	std::vector<const BattleUnit *> spotted; // its units spotted this turn, sorted
	std::vector<const Tile *> tiles;         // its visible tiles, sorted
	std::vector<char> seen;                  // BattleUnit::getVisible of every unit of the battle
	std::vector<int> since, snipers;         // turnsSinceSpotted / turnsLeftSpottedForSnipers by the selected unit's faction, every unit
	long long discovered = 0;                // discovered floors and walls of the whole map
};
struct WalkFovCount
{
	long long calls = 0, ran = 0, selWalker = 0, selOther = 0, walker[4] = {}; // walker: 0 player's side by a human, 1 by the bot, 2 the AI's side, 3 other
	long long nsRan = 0, nsNoop = 0, nsProbe = 0;
	long long tilesCalls = 0, tilesAdded = 0, tilesRemoved = 0, discCalls = 0, discTiles = 0;
	long long unitsCalls = 0, unitsAdded = 0, unitsRemoved = 0, spottedCalls = 0, spottedAdded = 0;
	long long seenHostile = 0, seenOther = 0, sinceReset = 0, snipersSet = 0;
	long long confirmed = 0, notConfirmed = 0, spottedNotConfirmed = 0, removedBack = 0, stepChanged = 0, noConfirm = 0;
};
WalkFovCount wfc;
WalkFovSnap wfS0, wfS1;
std::vector<const BattleUnit *> wfAdded, wfRemoved, wfSpotted; // what the call added to, removed from, spotted for the selected unit
const BattleUnit *wfSel = 0;
bool wfRan = false, wfPendingAfter = false, wfPendingConfirm = false;
std::chrono::steady_clock::time_point wfMark;

void walkFovTake(WalkFovSnap &s, SavedBattleGame *save, BattleUnit *sel, bool tiles = true)
{
	s.units.assign(sel->getVisibleUnits()->begin(), sel->getVisibleUnits()->end());
	std::sort(s.units.begin(), s.units.end());
	s.spotted.assign(sel->getUnitsSpottedThisTurn().begin(), sel->getUnitsSpottedThisTurn().end());
	std::sort(s.spotted.begin(), s.spotted.end());
	s.tiles.clear();
	if (tiles)
	{
		s.tiles.assign(sel->getVisibleTiles()->begin(), sel->getVisibleTiles()->end());
		std::sort(s.tiles.begin(), s.tiles.end());
	}
	const UnitFaction f = sel->getFaction();
	s.seen.clear();
	s.since.clear();
	s.snipers.clear();
	for (const auto *bu : *save->getUnits())
	{
		s.seen.push_back(bu->getVisible());
		s.since.push_back(bu->getTurnsSinceSpottedByFaction(f));
		s.snipers.push_back(bu->getTurnsLeftSpottedForSnipersByFaction(f));
	}
	s.discovered = 0;
	for (int i = 0, n = tiles ? save->getMapSizeXYZ() : 0; i < n; ++i)
	{
		const Tile *t = save->getTile(i);
		s.discovered += t->isDiscovered(O_FLOOR) + t->isDiscovered(O_WESTWALL) + t->isDiscovered(O_NORTHWALL);
	}
}

template <class T>
void walkFovDiff(const std::vector<T> &before, const std::vector<T> &after, std::vector<T> &added, std::vector<T> &removed)
{
	added.clear();
	removed.clear();
	std::set_difference(after.begin(), after.end(), before.begin(), before.end(), std::back_inserter(added));
	std::set_difference(before.begin(), before.end(), after.begin(), after.end(), std::back_inserter(removed));
}

long long walkFovNs(const std::chrono::steady_clock::time_point &from)
{
	return std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now() - from).count();
}

/// 0 off, 1 snapshots and time, 2 time only: the snapshots walk the whole map before the call and cool the caches, so the
/// call's time under mode 1 is an upper bound; mode 2 counts and times the same calls with nothing else in between.
int walkFovMode()
{
	static const int mode = active() ? (int)param("OXCE_AI_WALKFOVPROF", 0) : 0;
	return mode;
}

void walkFovReport()
{
	if (!walkFovProf())
	{
		return;
	}
	Log(LOG_INFO) << "[AIWALKFOV] mode=" << walkFovMode() << " walk_fov_calls=" << wfc.calls << " walk_fov_ran=" << wfc.ran
		<< " walk_fov_selected_player=" << wfc.walker[0] << " walk_fov_bot=" << wfc.walker[1] << " walk_fov_ai=" << wfc.walker[2] << " walk_fov_other=" << wfc.walker[3]
		<< " walk_fov_selected_is_walker=" << wfc.selWalker << " walk_fov_selected_other=" << wfc.selOther
		<< " walk_fov_time_us=" << wfc.nsRan / 1000 << " walk_fov_noop_time_us=" << wfc.nsNoop / 1000 << " probe_overhead_us=" << wfc.nsProbe / 1000
		<< " walk_fov_changed_visible_tiles=" << wfc.tilesCalls << " tiles_added=" << wfc.tilesAdded << " tiles_removed=" << wfc.tilesRemoved
		<< " walk_fov_new_discovered=" << wfc.discCalls << " discovered_parts=" << wfc.discTiles
		<< " walk_fov_changed_visible_units=" << wfc.unitsCalls << " units_added=" << wfc.unitsAdded << " units_removed=" << wfc.unitsRemoved
		<< " walk_fov_changed_spotted_units=" << wfc.spottedCalls << " spotted_added=" << wfc.spottedAdded
		<< " units_set_visible_hostile=" << wfc.seenHostile << " units_set_visible_other=" << wfc.seenOther
		<< " turns_since_spotted_reset=" << wfc.sinceReset << " snipers_set=" << wfc.snipersSet
		<< " added_kept_by_step_fov=" << wfc.confirmed << " added_not_kept_by_step_fov=" << wfc.notConfirmed
		<< " spotted_not_kept_by_step_fov=" << wfc.spottedNotConfirmed << " removed_back_by_step_fov=" << wfc.removedBack
		<< " step_changed_visible_units=" << wfc.stepChanged << " no_step_fov=" << wfc.noConfirm
		<< " sneakyAI=" << (Options::sneakyAI ? 1 : 0);
}

/// BOT_WALKFOV_UI_SKIP_V1 (OXCE_AI_WALKFOV_SKIP: 0 off, 1 skip, 2 shadow). The counters of both modes, and the shadow's
/// snapshots of the selected unit's sight before the call (S0) and after it (S1), compared by walkFovConfirm with the sight
/// after the step's own FOV: what the call set under the old light that the step's FOV did not set again is what mode 1 would
/// lose - spotted this turn, the seen flag (Pathfinding::isBlocked and voxelCheck read it for the player's side), turnsSinceSpotted
/// and the snipers' timer (set by whoever of the side sees the unit), a visible unit of the selected unit. A hostile the side
/// sees is in someone's visibleUnits; a neutral never is (TileEngine::calculateUnitsInFOV adds hostiles only, but sets the seen
/// flag and the timers on any faction), so for a unit nobody of the side lists the shadow asks the engine itself whether the
/// selected unit sees it now (walkFovStepSees): set again by the step's FOV is not a loss (setAgain), not seen now is.
struct WalkFovSkipCount
{
	long long calls = 0, skipped = 0, keptNotBot = 0, keptNotPlayable = 0, keptSelectedOther = 0, keptSneaky = 0;
	long long shadowCalls = 0, spottedOnly = 0, visibleOnly = 0, sinceOnly = 0, snipersOnly = 0, missing = 0, noStep = 0;
	long long setAgain = 0, setAgainNeutral = 0;
};
WalkFovSkipCount wsc;
WalkFovSnap wsS0, wsS1;
const BattleUnit *wsSel = 0;
bool wsPendingAfter = false, wsPendingConfirm = false;

int walkFovSkipMode()
{
	static const int mode = active() ? (int)param("OXCE_AI_WALKFOV_SKIP", 0) : 0;
	return mode;
}

/// The case the flag may skip: the bot plays the player's side, the call would run its FOV (playableUnitSelected), the
/// selected unit is the walker, sneakyAI is off. Anything else keeps the call and counts why.
bool walkFovSkipCase(BattlescapeGame *game, const BattleUnit *walker)
{
	SavedBattleGame *save = game->getSave();
	if (!botTurn(save))
	{
		++wsc.keptNotBot;
		return false;
	}
	if (!game->playableUnitSelected())
	{
		++wsc.keptNotPlayable;
		return false;
	}
	if (save->getSelectedUnit() != walker)
	{
		++wsc.keptSelectedOther;
		return false;
	}
	if (Options::sneakyAI)
	{
		++wsc.keptSneaky;
		return false;
	}
	return true;
}

void walkFovShadowBefore(BattlescapeGame *game, const BattleUnit *walker)
{
	if (wsPendingConfirm)
	{
		++wsc.noStep; // the previous step left think before its own FOV (it burned through the floor): mode 1 would have skipped without a replacement
		wsPendingConfirm = false;
	}
	++wsc.calls;
	wsPendingAfter = walkFovSkipCase(game, walker);
	if (!wsPendingAfter)
	{
		return;
	}
	++wsc.shadowCalls;
	wsSel = game->getSave()->getSelectedUnit();
	walkFovTake(wsS0, game->getSave(), game->getSave()->getSelectedUnit(), false);
}

void walkFovShadowAfter(BattlescapeGame *game)
{
	if (!wsPendingAfter)
	{
		return;
	}
	wsPendingAfter = false;
	walkFovTake(wsS1, game->getSave(), game->getSave()->getSelectedUnit(), false);
	wsPendingConfirm = true;
}

/// Does the selected unit see bu now, under the light after the step, the way the step's FOV decides it (TileEngine::
/// calculateUnitsInFOV with the event on its own tile: every unit, the view sector, then TileEngine::visible)? Reads only:
/// visible() works on locals and the visibility script takes const units.
bool walkFovStepSees(SavedBattleGame *save, BattleUnit *sel, BattleUnit *bu)
{
	if (bu->isOut() || bu->getId() == sel->getId())
	{
		return false;
	}
	const bool turret = Options::strafe && sel->getTurretType() > -1;
	const int size = bu->getArmor()->getSize();
	for (int x = 0; x < size; ++x)
	{
		for (int y = 0; y < size; ++y)
		{
			const Position p = bu->getPosition() + Position(x, y, 0);
			if (sel->checkViewSector(p, turret) && save->getTileEngine()->visible(sel, save->getTile(p)))
			{
				return true;
			}
		}
	}
	return false;
}

void walkFovShadowConfirm(BattlescapeGame *game)
{
	if (!wsPendingConfirm)
	{
		return;
	}
	wsPendingConfirm = false;
	SavedBattleGame *save = game->getSave();
	BattleUnit *sel = save->getSelectedUnit();
	if (sel != wsSel)
	{
		++wsc.noStep;
		return;
	}
	// the selected unit's sight after the step's FOV, and everything its side sees now: the seen flag, turnsSinceSpotted and
	// the snipers' timer are set by whoever of the side sees the unit, so only a unit nobody of the side sees is lost
	std::vector<const BattleUnit *> now(sel->getVisibleUnits()->begin(), sel->getVisibleUnits()->end());
	std::sort(now.begin(), now.end());
	std::vector<const BattleUnit *> side;
	for (auto *bu : *save->getUnits())
	{
		if (bu->getFaction() == sel->getFaction() && !bu->isOut())
		{
			side.insert(side.end(), bu->getVisibleUnits()->begin(), bu->getVisibleUnits()->end());
		}
	}
	std::sort(side.begin(), side.end());
	std::vector<const BattleUnit *> added, gone;
	walkFovDiff(wsS0.units, wsS1.units, added, gone);
	for (const auto *u : added)
	{
		wsc.missing += !std::binary_search(now.begin(), now.end(), u);
	}
	walkFovDiff(wsS0.spotted, wsS1.spotted, added, gone);
	for (const auto *u : added)
	{
		wsc.spottedOnly += !std::binary_search(now.begin(), now.end(), u);
	}
	const auto &units = *save->getUnits();
	for (size_t i = 0; i < units.size() && i < wsS0.seen.size() && i < wsS1.seen.size(); ++i)
	{
		if (std::binary_search(side.begin(), side.end(), units[i]))
		{
			continue;
		}
		const bool seenSet = !wsS0.seen[i] && wsS1.seen[i];
		const bool sinceSet = wsS0.since[i] != wsS1.since[i];
		const bool snipersSet = wsS0.snipers[i] != wsS1.snipers[i];
		if (!(seenSet || sinceSet || snipersSet))
		{
			continue;
		}
		if (walkFovStepSees(save, sel, units[i]))
		{
			++wsc.setAgain; // the step's FOV set the same under the new light (a neutral, or a hostile seen but listed by nobody)
			wsc.setAgainNeutral += units[i]->getFaction() == FACTION_NEUTRAL;
			continue;
		}
		wsc.visibleOnly += seenSet;
		wsc.sinceOnly += sinceSet;
		wsc.snipersOnly += snipersSet;
	}
}

void walkFovSkipReport()
{
	if (walkFovSkipMode() == 0)
	{
		return;
	}
	Log(LOG_INFO) << "[AIWALKFOVSKIP] mode=" << walkFovSkipMode() << " calls=" << wsc.calls << " skipped=" << wsc.skipped
		<< " kept_not_bot=" << wsc.keptNotBot << " kept_not_playable=" << wsc.keptNotPlayable << " kept_selected_other=" << wsc.keptSelectedOther << " kept_sneaky=" << wsc.keptSneaky
		<< " shadow_calls=" << wsc.shadowCalls << " prelight_spotted_only=" << wsc.spottedOnly << " prelight_visible_only=" << wsc.visibleOnly
		<< " prelight_turnsSinceSpotted_only=" << wsc.sinceOnly << " prelight_snipers_only=" << wsc.snipersOnly
		<< " postlight_missing_prelight_unit=" << wsc.missing << " shadow_no_step_fov=" << wsc.noStep
		<< " prelight_set_again_by_step=" << wsc.setAgain << " prelight_set_again_neutral=" << wsc.setAgainNeutral
		<< " sneakyAI=" << (Options::sneakyAI ? 1 : 0);
}

}

bool walkFovProf()
{
	return walkFovMode() > 0;
}

void walkFovBefore(BattlescapeGame *game, const BattleUnit *walker)
{
	if (walkFovSkipMode() == 2)
	{
		walkFovShadowBefore(game, walker);
	}
	if (!walkFovProf())
	{
		return;
	}
	SavedBattleGame *save = game->getSave();
	if (wfPendingConfirm)
	{
		++wfc.noConfirm; // the previous step left think before its own FOV (it burned through the floor)
		wfPendingConfirm = false;
	}
	++wfc.calls;
	const bool playerSide = save->getSide() == FACTION_PLAYER;
	++wfc.walker[walker->getFaction() == FACTION_PLAYER ? (playerSide ? (bot() ? 1 : 0) : 3) : (playerSide ? 3 : 2)];
	wfSel = save->getSelectedUnit();
	wfRan = game->playableUnitSelected(); // otherwise updateSoldierInfo leaves before its calculateFOV
	if (wfRan)
	{
		++(wfSel == walker ? wfc.selWalker : wfc.selOther);
		if (walkFovMode() == 1)
		{
			const auto t0 = std::chrono::steady_clock::now();
			walkFovTake(wfS0, save, save->getSelectedUnit());
			wfc.nsProbe += walkFovNs(t0);
		}
	}
	wfPendingAfter = true;
	wfMark = std::chrono::steady_clock::now();
}

void walkFovAfter(BattlescapeGame *game, const BattleUnit *)
{
	const long long ns = wfPendingAfter ? walkFovNs(wfMark) : 0; // the call's time, before the shadow's snapshot
	if (walkFovSkipMode() == 2)
	{
		walkFovShadowAfter(game);
	}
	if (!walkFovProf() || !wfPendingAfter)
	{
		return;
	}
	wfPendingAfter = false;
	if (!wfRan)
	{
		wfc.nsNoop += ns;
		return;
	}
	++wfc.ran;
	wfc.nsRan += ns;
	if (walkFovMode() != 1)
	{
		return;
	}
	SavedBattleGame *save = game->getSave();
	const auto t0 = std::chrono::steady_clock::now();
	walkFovTake(wfS1, save, save->getSelectedUnit());
	std::vector<const Tile *> tAdded, tRemoved;
	walkFovDiff(wfS0.tiles, wfS1.tiles, tAdded, tRemoved);
	if (!tAdded.empty() || !tRemoved.empty())
	{
		++wfc.tilesCalls;
		wfc.tilesAdded += tAdded.size();
		wfc.tilesRemoved += tRemoved.size();
	}
	if (wfS1.discovered > wfS0.discovered)
	{
		++wfc.discCalls;
		wfc.discTiles += wfS1.discovered - wfS0.discovered;
	}
	walkFovDiff(wfS0.units, wfS1.units, wfAdded, wfRemoved);
	if (!wfAdded.empty() || !wfRemoved.empty())
	{
		++wfc.unitsCalls;
		wfc.unitsAdded += wfAdded.size();
		wfc.unitsRemoved += wfRemoved.size();
	}
	std::vector<const BattleUnit *> gone;
	walkFovDiff(wfS0.spotted, wfS1.spotted, wfSpotted, gone);
	if (!wfSpotted.empty())
	{
		++wfc.spottedCalls;
		wfc.spottedAdded += wfSpotted.size();
	}
	const auto &units = *save->getUnits();
	for (size_t i = 0; i < wfS0.seen.size() && i < wfS1.seen.size() && i < units.size(); ++i)
	{
		if (!wfS0.seen[i] && wfS1.seen[i])
		{
			++(units[i]->getFaction() == FACTION_HOSTILE ? wfc.seenHostile : wfc.seenOther);
		}
		wfc.sinceReset += wfS0.since[i] != wfS1.since[i];
		wfc.snipersSet += wfS0.snipers[i] != wfS1.snipers[i];
	}
	wfc.nsProbe += walkFovNs(t0);
	wfPendingConfirm = true;
}

void walkFovConfirm(BattlescapeGame *game, const BattleUnit *)
{
	if (walkFovSkipMode() == 2)
	{
		walkFovShadowConfirm(game);
	}
	if (!walkFovProf() || !wfPendingConfirm)
	{
		return;
	}
	wfPendingConfirm = false;
	BattleUnit *sel = game->getSave()->getSelectedUnit();
	if (sel != wfSel)
	{
		++wfc.noConfirm;
		return;
	}
	const auto t0 = std::chrono::steady_clock::now();
	std::vector<const BattleUnit *> now(sel->getVisibleUnits()->begin(), sel->getVisibleUnits()->end());
	std::sort(now.begin(), now.end());
	for (const auto *u : wfAdded)
	{
		++(std::binary_search(now.begin(), now.end(), u) ? wfc.confirmed : wfc.notConfirmed);
	}
	for (const auto *u : wfSpotted)
	{
		wfc.spottedNotConfirmed += !std::binary_search(now.begin(), now.end(), u);
	}
	for (const auto *u : wfRemoved)
	{
		wfc.removedBack += std::binary_search(now.begin(), now.end(), u);
	}
	wfc.stepChanged += now != wfS0.units;
	wfc.nsProbe += walkFovNs(t0);
}

int walkFovSkip()
{
	return walkFovSkipMode();
}

bool walkFovKeep(BattlescapeGame *game, const BattleUnit *walker)
{
	if (walkFovSkipMode() != 1)
	{
		return true;
	}
	++wsc.calls;
	if (!walkFovSkipCase(game, walker))
	{
		return true;
	}
	++wsc.skipped;
	return false;
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
		if (exec.krWatch && pushed)
		{
			exec.trail.push_back("walk.first d" + std::to_string(save->getPathfinding()->getStartDirection()));
		}
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

/// [AIPATROL] (plan V2, L0-B): a patrol walk to its node - the path the game found, what stops its first step, and with
/// OXCE_AI_RECORD_PATH=2, when it is stopped, the tiles in reach that get closest to the node. The costs come from a
/// Pathfinding of the probe's own: the battle's one holds the path the walk is about to take.
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
	// the forensic fields (OXCE_AI_RECORD_PATH=2 only): up to 17 full A* of the probe's own Pathfinding per stopped walk, a
	// quarter of the station battle (docs/research/ai-path-audit-2026-10-01.md, п. 11); mode 1 ends the line here
	if (stop != "none" && param("OXCE_AI_RECORD_PATH", 0) >= 2)
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
			"OXCE_AI_FAST", "OXCE_AI_LIGHTSKIP", "OXCE_AI_PATHPROF", "OXCE_AI_AMBUSHPROF", "OXCE_AI_ESCAPEPROF", "OXCE_AI_RECORD_REUSE",
			"OXCE_AI_AMBUSH_MEMO", "OXCE_AI_ESCAPE_REACH_FIRST", "OXCE_AI_WALKFOVPROF", "OXCE_AI_WALKFOV_SKIP" }; // the fast mode, the light skip, the profiles, the record's reuse, the ambush memo, the escape order and the display's FOV skip change what is computed, not how the bench plays
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
	decisionSource[unit->getId()] = src ? src->src : std::string("?");
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
	if (pending.krWatch)
	{
		exec.krWatch = true;
		std::ostringstream kr;
		kr << "kr.dec " << std::hex << pending.krDec;
		exec.trail.push_back(kr.str());
	}
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
		reachFallback(save, unit);
		writeRecord(save, unit, action, hashUnits, hashItems, hashOrder, hashMap, hashRng);
	}
	pathClose(unit);
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

void firepointBlocked(BattleUnit *unit, const BattleAction &action, int dir)
{
	static const bool on = active() && envOn("OXCE_AI_FIREPOINT_BLOCKED");
	if (on && unit->getAIModule())
	{
		unit->getAIModule()->firepointWalkBlocked(action, dir);
	}
}

unsigned long long knownRevision(SavedBattleGame *save, const BattleUnit *unit)
{
	StateHash h;
	for (const auto *bu : *save->getUnits())
	{
		// a unit the side does not see is not in it: neither where it stands nor whether it is out
		if (bu->getFaction() != unit->getFaction() && bu->getTurnsSinceSpottedByFaction(unit->getFaction()) != 0)
		{
			continue;
		}
		h.add(bu->getId());
		h.add(bu->getPosition().x); h.add(bu->getPosition().y); h.add(bu->getPosition().z);
		h.add((int)bu->getStatus()); h.add(bu->isOut() ? 1 : 0);
	}
	for (int i = 0; i < save->getMapSizeXYZ(); ++i)
	{
		Tile *tile = save->getTile(i);
		for (int part = O_FLOOR; part < O_MAX; ++part)
		{
			int id = -1, set = -1;
			tile->getMapData(&id, &set, (TilePart)part);
			h.add(id * 256 + set);
			h.add(tile->isUfoDoorOpen((TilePart)part) ? 1 : 0);
		}
		h.add(tile->getFire()); h.add(tile->getSmoke());
	}
	return h.h;
}

bool firepointBlockedSalt()
{
	static const bool on = active() && envOn("OXCE_AI_FIREPOINT_BLOCKED_SALT");
	return on;
}

namespace
{

bool blockedStepOn()
{
	static const bool on = active() && envOn("OXCE_AI_BLOCKED_STEP");
	return on;
}

int unitTurnOf(const SavedBattleGame *save)
{
	return save->getTurn() * 8 + (int)save->getSide();
}

BlockedStepCount &blockedCountOf(const BattleUnit *unit)
{
	const int f = (int)unit->getFaction();
	return blockedCount[f >= 0 && f < 3 ? f : 2];
}

/// one count to the battle's [AIBLOCKSTEP] line and to the tac column of [AIRESULT] (p./h.blockstep.<name>): the second
/// is what the stations' ai_probe.py keeps; no trail entry, the callers note the detail themselves
void blockedBump(const BattleUnit *unit, int BlockedStepCount::*field, const std::string &name)
{
	++(blockedCountOf(unit).*field);
	++tallies[std::string(unit->getFaction() == FACTION_PLAYER ? "p." : "h.") + "blockstep." + name];
}

std::string dirList(const std::vector<int> &dirs)
{
	std::string s;
	for (int d : dirs) s += (s.empty() ? "d" : ",d") + std::to_string(d);
	return s;
}

void blockedStepReport()
{
	if (!active())
	{
		return;
	}
	// the flag's own line, also off: the proof of which artefact played (R-087)
	std::ostringstream s;
	s << "[AIBLOCKSTEP] mode=" << (blockedStepOn() ? 1 : 0);
	static const char *const sides[3] = { "player", "hostile", "neutral" };
	for (int i = 0; i < 3; ++i)
	{
		const BlockedStepCount &c = blockedCount[i];
		s << " " << sides[i] << ".recorded=" << c.recorded << " " << sides[i] << ".suppressed=" << c.suppressed
			<< " " << sides[i] << ".rerouted=" << c.rerouted << " " << sides[i] << ".no_path=" << c.noPath
			<< " " << sides[i] << ".invalidated_revision=" << c.invRevision << " " << sides[i] << ".invalidated_turn=" << c.invTurn;
		std::string by;
		for (const auto &b : c.bySource) by += (by.empty() ? "" : ",") + b.first + ":" + std::to_string(b.second);
		s << " " << sides[i] << ".by_source=" << (by.empty() ? "-" : by);
	}
	// the unit-turns that had steps suppressed, by how many different steps
	int distinct[4] = {};
	for (const auto &t : blockedPerTurn) ++distinct[std::min<size_t>(t.second.size(), 3)];
	s << " distinct_per_unit_turn=1:" << distinct[1] << ",2:" << distinct[2] << ",3+:" << distinct[3];
	Log(LOG_INFO) << s.str();
}

}

void blockedStepStop(SavedBattleGame *save, BattleUnit *unit, int dir)
{
	if (!blockedStepOn() || !unit->getAIModule())
	{
		return;
	}
	const int turn = unitTurnOf(save);
	const unsigned long long kr = knownRevision(save, unit);
	BlockedSteps &m = blockedSteps[unit->getId()];
	if (m.turn == turn && m.from == unit->getPosition() && m.kr == kr)
	{
		if (std::find(m.dirs.begin(), m.dirs.end(), dir) == m.dirs.end()) m.dirs.push_back(dir);
	}
	else
	{
		if (m.turn != -1 && m.turn != turn) blockedBump(unit, &BlockedStepCount::invTurn, "inv.turn");
		else if (m.turn != -1) blockedBump(unit, &BlockedStepCount::invRevision, "inv.rev");
		m.turn = turn;
		m.from = unit->getPosition();
		m.kr = kr;
		m.dirs.assign(1, dir);
	}
	blockedBump(unit, &BlockedStepCount::recorded, "recorded");
	note(unit, ("blockstep.recorded" + dirList(m.dirs)).c_str());
}

void blockedStepDecide(SavedBattleGame *save, BattleUnit *unit)
{
	if (!blockedStepOn())
	{
		return;
	}
	const auto it = blockedSteps.find(unit->getId());
	if (it == blockedSteps.end())
	{
		return;
	}
	const BlockedSteps &m = it->second;
	const char *why = nullptr;
	if (m.turn != unitTurnOf(save))
	{
		why = "turn";
		blockedBump(unit, &BlockedStepCount::invTurn, "inv.turn");
	}
	else if (m.from != unit->getPosition() || knownRevision(save, unit) != m.kr)
	{
		// the unit's own position is in the revision: moving off the tile changes it
		why = "revision";
		blockedBump(unit, &BlockedStepCount::invRevision, "inv.rev");
	}
	if (why)
	{
		note(unit, (std::string("blockstep.invalidated.") + why + " " + dirList(m.dirs)).c_str());
		blockedSteps.erase(it);
	}
}

void blockedStepPlan(SavedBattleGame *save, BattleUnit *unit, const BattleAction &action)
{
	if (!blockedStepOn())
	{
		return;
	}
	const auto it = blockedSteps.find(unit->getId());
	if (it == blockedSteps.end())
	{
		return;
	}
	// blockedStepDecide checked this decision's turn, tile and revision; nothing moved since
	Pathfinding *pf = save->getPathfinding();
	const int first = pf->getStartDirection();
	const std::vector<int> &dirs = it->second.dirs;
	if (first == -1 || std::find(dirs.begin(), dirs.end(), first) == dirs.end())
	{
		return;
	}
	blockedBump(unit, &BlockedStepCount::suppressed, "suppressed");
	const auto src = decisionSource.find(unit->getId());
	std::string source = src != decisionSource.end() && !src->second.empty() ? src->second : std::string("?");
	// both lists are name:count,name:count
	for (char &ch : source) if (ch == ' ' || ch == ',' || ch == ':' || ch == '=') ch = '_';
	++blockedCountOf(unit).bySource[source];
	++tallies[std::string(unit->getFaction() == FACTION_PLAYER ? "p." : "h.") + "blockstep.src." + source];
	std::vector<int> &perTurn = blockedPerTurn[{ unit->getId(), it->second.turn }];
	if (std::find(perTurn.begin(), perTurn.end(), first) == perTurn.end()) perTurn.push_back(first);
	pf->setBannedFirst(dirs);
	pf->calculate(action.actor, action.target, BAM_NORMAL);
	pf->setBannedFirst({});
	const int now = pf->getStartDirection();
	if (now == -1) blockedBump(unit, &BlockedStepCount::noPath, "no_path");
	else blockedBump(unit, &BlockedStepCount::rerouted, "rerouted");
	note(unit, ("blockstep.suppressed d" + std::to_string(first) + " -> " + (now == -1 ? std::string("none") : "d" + std::to_string(now))).c_str());
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
