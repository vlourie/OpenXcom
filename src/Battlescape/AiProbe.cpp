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
#include <sstream>
#include "AIModule.h"
#include "BattlescapeGame.h"
#include "BattlescapeState.h"
#include "../Engine/Game.h"
#include "../Engine/Logger.h"
#include "../Engine/Timer.h"
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
void logDecision(SavedBattleGame *, BattleUnit *, const BattleAction &) {}
void logState(SavedBattleGame *, const char *) {}
bool tactics(const BattleUnit *) { return false; }
bool careful(const BattleUnit *) { return false; }
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

void logDecision(SavedBattleGame *save, BattleUnit *unit, const BattleAction &action)
{
	if (!active())
	{
		return;
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
		<< " seen=" << (seen.tellp() > 0 ? seen.str() : std::string("-"));
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
			<< " reach=" << reachable;
	}
}

#endif

}

}
