#pragma once
#include <string>
#include <vector>
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

namespace OpenXcom
{

class BattlescapeState;
class SavedBattleGame;
class BattleUnit;
class Position;
struct BattleAction;

/**
 * The AI turn probe (OXCE_AI_PROBE=1, docs/AI_ROADMAP.md, stage 2.1): a loaded battle save
 * ends the player's turn by itself, the AI plays its turn on the virtual clock, the log gets
 * the state of the battle before and after ([AISTATE]) and every AI decision ([AIDECIDE]),
 * then the game quits. Asleep and silent in normal play.
 *
 * OXCE_AI_BOT=1: the player's side is played by the AI too, to the end of the battle or
 * OXCE_AI_PROBE_TURNS turns; the result goes to the log ([AIRESULT]). OXCE_AI_SEED=<n> with
 * OXCE_HD_START=battle: a random quick battle of the mod (NewBattleState::probeRandomize).
 *
 * Compiled in only with the CMake option OXCE_AI_DEV (the local build-ai): in a release build
 * active() is always false.
 */
namespace AiProbe
{

/// Is the probe on (the OXCE_AI_PROBE environment variable, OXCE_AI_DEV builds only)?
bool active();
/// Does the AI play the player's side right now (OXCE_AI_BOT)?
bool botTurn(const SavedBattleGame *save);
/// The seed of a generated battle (OXCE_AI_SEED), or -1.
long long battleSeed();
/// Drives the probe from the battlescape's think: ends the player's turn, quits after the AI's.
void think(BattlescapeState *state, SavedBattleGame *save);
/// The battle is over (BattlescapeState::finishBattle): the result line, and the bot quits.
void battleOver(BattlescapeState *state, SavedBattleGame *save, bool abort);
/// One line per AI decision (after the unit has thought, before the action runs).
void logDecision(SavedBattleGame *save, BattleUnit *unit, const BattleAction &action);
/// One line per unit on the field: position, TU, health, who it sees and who has spotted it.
void logState(SavedBattleGame *save, const char *when);
/// The smarter enemy under test (OXCE_AI_TACTICS): true for hostile units only.
bool tactics(const BattleUnit *unit);
/// The careful bot (OXCE_AI_CAREFUL): true for the player's units while the bot plays them.
bool careful(const BattleUnit *unit);
/// The careful bot weighs every reachable tile, target and fire mode by expected damage against risk (OXCE_AI_EVAL).
bool evalFire(const BattleUnit *unit);
/// The careful bot, its hands empty or its gun dry, picks up a weapon from the ground while it sees no enemy (OXCE_AI_ARMS).
bool pickUp(const BattleUnit *unit);
/// The careful bot, seeing no enemy, ends its turn facing the sighting of the known enemy nearest to reaching it (OXCE_AI_WATCH).
bool watchPoint(SavedBattleGame *save, const BattleUnit *unit, Position &out);
/// The careful bot on patrol with enemies known walks half its time units at most, as a player does (OXCE_AI_HALF).
bool halfWalk(SavedBattleGame *save, const BattleUnit *unit);
/// The careful bot's cover keeps its distance (OXCE_AI_GAP): living enemies its side sees now within 2 tiles of pos; 0 when off.
int closeEnemies(SavedBattleGame *save, const BattleUnit *unit, const Position &pos);
/// The careful bot raises a downed comrade with a medikit's stimulant (OXCE_AI_REVIVE): standing on the body it spends uses
/// until the comrade gets up; otherwise it sets a walk onto the nearest body in reach (reachable - the last findReachable). True when it set a walk.
bool revive(SavedBattleGame *save, BattleUnit *unit, BattleAction *action, const std::vector<int> &reachable);
/// A tuning number from the environment (OXCE_AI_EVAL_RISK and the like), or def; always def in a release build.
double param(const char *name, double def);
/// Counts one use of a tactical rule for the result line ([AIRESULT] tac=).
void tally(const BattleUnit *unit, const char *rule);
/// One line per unit killed or knocked out ([AICASUALTY]): by whom, with what, from how far, on whose turn.
void logCasualty(SavedBattleGame *save, const BattleUnit *victim, const BattleUnit *killer, const std::string &weapon,
	bool dead, int hitSide, bool terrain);

}

}
