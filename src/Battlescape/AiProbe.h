#pragma once
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
struct BattleAction;

/**
 * The AI turn probe (OXCE_AI_PROBE=1, docs/AI_ROADMAP.md, stage 2.1): a loaded battle save
 * ends the player's turn by itself, the AI plays its turn on the virtual clock, the log gets
 * the state of the battle before and after ([AISTATE]) and every AI decision ([AIDECIDE]),
 * then the game quits. Asleep and silent in normal play.
 */
namespace AiProbe
{

/// Is the probe on (the OXCE_AI_PROBE environment variable)?
bool active();
/// Drives the probe from the battlescape's think: ends the player's turn, quits after the AI's.
void think(BattlescapeState *state, SavedBattleGame *save);
/// One line per AI decision (after the unit has thought, before the action runs).
void logDecision(SavedBattleGame *save, BattleUnit *unit, const BattleAction &action);
/// One line per unit on the field: position, TU, health, who it sees and who has spotted it.
void logState(SavedBattleGame *save, const char *when);

}

}
