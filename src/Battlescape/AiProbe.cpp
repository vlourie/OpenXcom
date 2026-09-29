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
#include <cmath>
#include <cstdlib>
#include <map>
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
#include "../Mod/RuleInventory.h"
#include "../Mod/RuleItem.h"
#include "../Savegame/BattleItem.h"
#include "../Savegame/BattleUnit.h"
#include "../Savegame/SavedBattleGame.h"
#include "../Savegame/SavedGame.h"
#include "../Savegame/Tile.h"
#include "TileEngine.h"

namespace OpenXcom
{

namespace AiProbe
{

#ifndef OXCE_AI_DEV

// a release build: the bench is not compiled in, every entry point does nothing
bool active() { return false; }
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
void logCasualty(SavedBattleGame *, const BattleUnit *, const BattleUnit *, const std::string &, bool, int, bool) {}

#else

namespace
{

bool envOn(const char *name)
{
	const char *s = getenv(name);
	return s && *s && *s != '0';
}

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
}

}

bool active()
{
	static const bool on = envOn("OXCE_AI_PROBE");
	return on;
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

/// The decision record (OXCE_AI_RECORD, plan V2 step 2): the candidates of the unit about to think.
struct Pending
{
	int unit = -1;
	AiCandidates::Set set;
	bool rngTouched = false;
};
Pending pending;
/// move lists already written in this battle: a list is stored once, the records refer to it by its hash
std::set<uint64_t> movesWritten;
/// the decision's number in the battle, and the order in which units first decide within one side's turn
int recordNo = 0;
int orderTurn = -1, orderSide = -1;
std::map<int, int> orderOf;

bool record()
{
	static const bool on = active() && envOn("OXCE_AI_RECORD");
	return on;
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
		pending.unit = unit->getId();
		pending.set = AiCandidates::generate(save, unit);
		// the list must not change the battle: it may not draw a random number
		pending.rngTouched = RNG::getSeed() != rngBefore;
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

void writeRecord(SavedBattleGame *save, BattleUnit *unit, const BattleAction &action, uint64_t hashUnits, uint64_t hashItems,
	uint64_t hashOrder, uint64_t hashMap, uint64_t hashRng)
{
	if (pending.unit != unit->getId())
	{
		Log(LOG_INFO) << "[AIPROBE] record: no candidates for unit " << unit->getId();
		return;
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
	tally(unit, in ? "rec.in" : (std::string("rec.out.") + (char)kind + std::to_string((int)action.type)).c_str());

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
	const AIModule *ai = unit->getAIModule();
	Log(LOG_INFO) << "[AIREC] {\"v\":1,\"seed\":" << battleSeed() << ",\"rec\":" << recordNo++
		<< ",\"turn\":" << save->getTurn() << ",\"side\":" << (int)save->getSide() << ",\"unit\":" << unit->getId() << ",\"order\":" << order
		<< ",\"n\":" << action.number
		<< ",\"state\":{\"pos\":" << pos(unit->getPosition()) << ",\"dir\":" << unit->getDirection() << ",\"tu\":" << unit->getTimeUnits()
		<< ",\"hp\":" << unit->getHealth() << ",\"stun\":" << unit->getStunlevel() << ",\"morale\":" << unit->getMorale()
		<< ",\"kneel\":" << (unit->isKneeled() ? 1 : 0)
		<< ",\"h\":{\"u\":\"" << hex(hashUnits) << "\",\"i\":\"" << hex(hashItems) << "\",\"o\":\"" << hex(hashOrder) << "\",\"m\":\"" << hex(hashMap)
		<< "\",\"r0\":\"" << hex(rngBefore) << "\",\"r\":\"" << hex(hashRng) << "\",\"a0\":\"" << hex(aiBefore) << "\"}"
		<< ",\"state_id\":\"" << hex(hashUnits ^ hashMap) << "\"}"
		<< ",\"cand\":{\"n\":" << set.count() << ",\"set\":\"" << hex(set.setHash) << "\",\"order\":\"" << hex(set.orderHash)
		<< "\",\"moves\":\"" << hex(set.movesHash) << "\",\"nmoves\":" << set.moves.size() << ",\"rng\":" << (pending.rngTouched ? 1 : 0)
		<< ",\"acts\":[" << acts.str() << "]}"
		<< ",\"base\":{\"id\":\"" << hex(chosen) << "\",\"k\":\"" << (char)kind << "\",\"in\":" << (in ? 1 : 0) << ",\"t\":" << (int)action.type
		<< ",\"to\":" << pos(action.target) << ",\"w\":" << quoted(action.weapon ? action.weapon->getRules()->getType() : std::string())
		<< ",\"run\":" << (action.run ? 1 : 0) << ",\"mode\":" << (ai ? ai->getAIMode() : -1) << ",\"score\":null,\"reason\":null}"
		<< ",\"rule\":null,\"exec\":null,\"after\":null,\"after_enemy\":null}";
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
