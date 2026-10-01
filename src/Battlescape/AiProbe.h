#pragma once
#include <string>
#include <utility>
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
class BattlescapeGame;
class SavedBattleGame;
class BattleUnit;
class Position;
class TileEngine;
struct BattleAction;
struct BattleActionCost;

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
/// The probe skips everything nobody watches (OXCE_AI_FAST): no frame is drawn, no tile but UFO doors is animated,
/// every unit walks the short off-screen cycle, no final-blow scene, no audio, one log handle for the run, and the process
/// leaves right after the result line. The decisions, the record and the outcome stay the same as without it.
bool fast();
/// The bench skips the lighting recalculation on a step of a unit that sheds no light (OXCE_AI_LIGHTSKIP, docs/research/
/// ai-sim-speed-audit-2026-09-30.md, п. 6): its walk changes no light source, so the map's light stays what it is. Every other
/// light event (a shot, a glowing item dropped or picked up, a death, a fall, a teleport, a toggle of the personal light,
/// a hit, terrain changed) recalculates on its own. True - skip; counts the recalculations done and skipped for [AILIGHT].
bool lightSkip(const TileEngine *terrain, const BattleUnit *unit);
/// The pathfinding profile (OXCE_AI_PATHPROF, docs/research/ai-path-audit-2026-10-01.md): what the AI asks of the pathfinder
/// while it decides, each ask keyed by what it asks (kind, unit, place, target, move type, missile target, TU cap, TU and
/// energy) and timed, so that the same ask repeated within one decision - or in the next decision with the battle unchanged -
/// is counted apart and its answer's fingerprint is checked against the first. Reads only; [AIPF] lines per decision and at
/// the end of the battle. Off (the default): pathAsk is never called.
bool pathProf();
/// One answered ask: kind 1 calculate (algo 1 bresenham, 2 A*, 3 no path, 0 no end position), 2 findReachable; site - the
/// caller's return address, turned into a name offline by tools/ai_speed/path_prof.py; answer - the fingerprint of what came
/// back, len and cost - its size (path steps, reachable tiles) and TU (path cost, TU budget) for the mismatch lines.
void pathAsk(int kind, int algo, const BattleUnit *unit, const Position &from, const Position &to, int bam,
	const BattleUnit *missileTarget, int maxTU, int tu, int energy, unsigned long long answer, int len, int cost, long long ns, const void *site);
/// The decision record takes the reach the game computes when the unit thinks instead of asking the pathfinder itself before
/// the think (OXCE_AI_RECORD_REUSE, default on; 0 - the record asks as before). The path profile (docs/research/
/// ai-path-audit-2026-10-01.md, 2.3) found the record's ask repeated the think's own to the byte - 439 asks, 5,2 s of the
/// station battle. True for the first findReachable of the thinking unit with no action cost, at the time units and energy it
/// started to think with: the same ask the record would make. When the think may spend first (a reload, the once-a-turn
/// medikit, the freeze workaround - BattleUnit::think before AIModule::think) the record asks itself before the think as it
/// always did; a decision the think never asked for gets the record's own ask after it ([AIREUSE]: taken, own, fallback).
bool reachWanted(const BattleUnit *unit, const BattleActionCost &cost);
/// That answer: the tiles in the pathfinder's order with the time units to each (findReachable, reachedTU).
void reachTaken(SavedBattleGame *save, std::vector<std::pair<int, int>> &&reach);
/// The ambush profile (OXCE_AI_AMBUSHPROF): what AIModule::setupAmbush does with the map's nodes - how many it looks at, how
/// many pass each cheap check, how many enemy searches (A*, no TU cap) it runs, which of them succeed, what each costs in
/// expanded nodes and time, and which node it takes. Reads only: [AIAMB] per call, [AIAMBN] per enemy search, totals at the
/// end of the battle. Off (the default): nothing is counted.
bool ambushProf();
/// setupAmbush starts for unit against enemy, the closest known.
void ambushBegin(SavedBattleGame *save, const BattleUnit *unit, const BattleUnit *enemy);
/// A node passed a stage: 0 looked at, 1 near, same level, safe and in reach with the attack, 2 hidden from the enemy, 3 the unit's own path got there.
void ambushNode(int stage);
/// A search is about to start (its time is measured from here).
void ambushMark();
/// The unit's own path to the node was searched: ok - it got there, tu - its cost, expanded - the A* nodes.
void ambushOwn(bool ok, int tu, int expanded);
/// The enemy's path to the node was searched: ok - it got there, cost and len - its TU and steps, expanded - the A* nodes;
/// own - the unit's own cost, score - the node's score before cover, best - the best score so far.
void ambushEnemy(const Position &pos, bool ok, int cost, int len, int expanded, int own, int score, int best);
/// The node was scored after the enemy's search got there: cover - behind a window, taken - it became the best.
void ambushScored(int score, bool cover, bool taken);
/// setupAmbush ends: chosen - it set a walk, best - its score, target - the node, tus - the cost it kept, fast - it stopped early.
void ambushEnd(bool chosen, int best, const Position &target, int tus, bool fast);
/// AMBUSH_NEGATIVE_MEMO_V1 (OXCE_AI_AMBUSH_MEMO): inside one setupAmbush, once the enemy's A* to a node ran out of open nodes,
/// a node outside the tiles it closed has no path from the enemy (Pathfinding::closedTiles) and its search is skipped. The
/// memo lives in that call only. 0 - off (the default), 1 - skip, 2 - verify: search anyway and count answers that disagree
/// (none expected; the control of the statement). In the release build 0.
int ambushMemo();
/// A node the memo answered: skipped - its search was not run (mode 1); ok - what the search still run gave (mode 2);
/// own, score, best as ambushEnemy. [AIAMBN] with memo=1 for a skipped node; counts in [AIAMB] and the memo total line.
void ambushMemoNode(const Position &pos, bool skipped, bool ok, int own, int score, int best);
/// The escape audit (OXCE_AI_ESCAPEPROF, docs/research/ai-path-audit-2026-10-01.md, п. 11): how many candidate tiles
/// AIModule::setupEscape looks at, how many of them it drops as unreachable after getSpottingUnits has already traced the
/// enemies' lines of fire to them, how many canTargetUnit traces and how much time that took. Reads only: [AIESC] per side
/// at the end of the battle. Off (the default): nothing is counted.
bool escapeProf();
/// setupEscape starts for the unit.
void escapeBegin(const BattleUnit *unit);
/// One canTargetUnit trace of AIModule::getSpottingUnits (any caller).
void escapeTarget();
/// A candidate tile's getSpottingUnits is about to run (its traces and time are counted from here).
void escapeMark();
/// The candidate was classified: kind 0 - unreachable, dropped after the traces; 1 - reachable, scored; 2 - no tile (no traces).
void escapeProbe(const BattleUnit *unit, int kind);
/// ESCAPE_REACH_FIRST_V1 (OXCE_AI_ESCAPE_REACH_FIRST, stand only): setupEscape drops an unreachable candidate before the
/// enemies' lines of fire to it are traced. The traces are const and touch no RNG, so every reachable candidate gets the same
/// score and the same tile is chosen (audit п. 12-13: two thirds of the enemy's candidates are unreachable, 20 % of the city
/// battle went into their traces). Off (the default of the engine): the traces come first, as in OXCE.
bool escapeReachFirst();
/// A candidate dropped before its traces by the flag (counted always, [AIESCRF] in the battle's result).
void escapeSkipped();
/// The FOV-on-step audit (OXCE_AI_WALKFOVPROF, docs/research/ai-path-audit-2026-10-01.md, п. 14): what the
/// updateSoldierInfo call after every finished step of UnitWalkBState changes in the selected unit's sight, what of it the
/// step's own calculateFOV keeps, and how long the call takes. Reads only, snapshots before and after; [AIWALKFOV] at the end
/// of the battle. 1 - snapshots and time, 2 - time only (the snapshots cool the caches, mode 2 times the bare call);
/// off (the default): nothing is counted.
bool walkFovProf();
/// The step is finished, updateSoldierInfo is about to run for the walker: the snapshot before it.
void walkFovBefore(BattlescapeGame *game, const BattleUnit *walker);
/// updateSoldierInfo returned: the snapshot after it, compared with the one before.
void walkFovAfter(BattlescapeGame *game, const BattleUnit *walker);
/// The step's own calculateFOV ran: does the selected unit still see what updateSoldierInfo added.
void walkFovConfirm(BattlescapeGame *game, const BattleUnit *walker);
/// BOT_WALKFOV_UI_SKIP_V1 (OXCE_AI_WALKFOV_SKIP, stand only; the second opinion of 01.10 on audit п. 14). The
/// updateSoldierInfo call after a finished step of UnitWalkBState recalculates the selected unit's whole field of view for
/// the TU display; for the stand's bot nobody reads the display, and the step's own calculateFOV a few lines later recomputes
/// the units' part from scratch (visible units, spotted this turn, the seen flag, turnsSinceSpotted) - that one always stays.
/// 1 - skip the call's FOV (updateSoldierInfo(false): the display only) when the bot plays the player's side, the selected
/// unit is the walker and sneakyAI is off (the only reader of tile visibility between the steps); a human's turn, the AI's
/// side, another selected unit, sneakyAI - the call runs as in the engine. 2 - shadow: nothing is skipped; what the call
/// changed in the units and the step's FOV then did not keep is counted (prelight_*, postlight_* of [AIWALKFOVSKIP]) - the
/// gate: all of them 0 on the cohort before 1 goes in by default. Off (the default of the engine): the call as in OXCE; not
/// combined with OXCE_AI_WALKFOVPROF (the audit would count a skipped call as ran). Release builds: 0 always.
int walkFovSkip();
/// The step is finished: run the call's FOV? False only under walkFovSkip() 1 for the allowed case (counted).
bool walkFovKeep(BattlescapeGame *game, const BattleUnit *walker);
/// Does the AI play the player's side right now (OXCE_AI_BOT)?
bool botTurn(const SavedBattleGame *save);
/// The seed of a generated battle (OXCE_AI_SEED), or -1.
long long battleSeed();
/// Drives the probe from the battlescape's think: ends the player's turn, quits after the AI's.
void think(BattlescapeState *state, SavedBattleGame *save);
/// The battle is over (BattlescapeState::finishBattle): the result line, and the bot quits.
void battleOver(BattlescapeState *state, SavedBattleGame *save, bool abort);
/// Remembers the random generator and the unit's AI state just before it thinks (logDecision prints them next to the after),
/// and with OXCE_AI_RECORD the actions it could take (AiCandidates) for the decision record.
void beforeThink(SavedBattleGame *save, BattleUnit *unit);
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
/// The careful bot's cover out of turret fire (OXCE_AI_TURRET): living enemies that cannot move, whose place its side knows,
/// with a line of fire to pos at any distance; 0 when off.
int turretsSeeing(SavedBattleGame *save, BattleUnit *unit, const Position &pos);
/// The careful bot's soldier who cannot fight - empty hands, health under half or stun at half the health - runs from the enemies
/// its side sees (OXCE_AI_FLEE): a walk to the reachable tile fewest of them have a line of fire to, then farthest from them.
/// True when it set a walk.
bool flee(SavedBattleGame *save, BattleUnit *unit, BattleAction *action, const std::vector<int> &reachable);
/// How many AI actions a unit takes in a row before the next unit: the engine's 2, or OXCE_AI_ACTIONS for the careful bot.
int maxActions(const BattleUnit *unit);
/// A tuning number from the environment (OXCE_AI_EVAL_RISK and the like), or def; always def in a release build.
double param(const char *name, double def);
/// Counts one use of a tactical rule for the result line ([AIRESULT] tac=); also a step of the decision's reason trail.
void tally(const BattleUnit *unit, const char *rule);
/// A step of the decision's reason trail that is not counted in the result line (docs/AI_DECISION_RECORD.md).
void note(const BattleUnit *unit, const char *what);
/// A rule of the AI module filled one of its action slots (p patrol, a ambush, e escape, x attack, s psi): which rule, with
/// what score (INT_MIN - the rule has none), what action. For the decision record only (OXCE_AI_RECORD).
void propose(const BattleUnit *unit, char slot, const char *source, int score, const BattleAction &action);
/// The slot the decision was taken from (p a e x s as in propose, l Leeroy, b the bench's revive or flee).
void chosen(const BattleUnit *unit, char slot);
/// The dice of evaluateAIMode: the odds of each mode, the roll and the mode it gave.
void modeOdds(const BattleUnit *unit, int patrol, int ambush, int combat, int escape, int roll, int mode);
/// A tile a rule scored (firepoint, ambush, escape): logged only for the decisions of OXCE_AI_TRACE_DECISION.
void traceTile(const BattleUnit *unit, const char *what, const Position &pos, int score);
/// The walk the decision asked for got a path (handleAI pushes it) or not (it is dropped). With OXCE_AI_RECORD_PATH a
/// patrol walk also writes [AIPATROL]: 1 - its path and what stops its first step; 2 - also the reachable tile that gets
/// closest to the node (forensic: up to 17 full A* per stopped walk, a quarter of the station battle).
/// item: the walk goes to an item (findItem / findBotWeapon), not where the decision chose - "item":1 in both lines.
void walkPlanned(SavedBattleGame *save, BattleUnit *unit, bool pushed, bool item);
/// A walk stops without the unit moving (UnitWalkBState): a step of the action's trail in [AIEXEC],
/// "walk.stop.<reason> from>to d<dir> bam<move> mt<movement> sz<size> tu<tu>/<step> en<energy>/<step> rs<reserve> bu<blocker>".
/// Record only; -1 where a value is unknown.
void walkStop(const BattleUnit *unit, const char *reason, const Position &to, int dir, int bam, int stepTu, int stepEnergy, int blocker);
/// ENERGY_PATROL_END_V2 (OXCE_AI_ENERGY_PATROL_END, bench only): the patrol walk handleAI just planned is stopped by energy,
/// and the unit has less energy than the cheapest step to any neighbouring tile, other units aside - it has no step left
/// this turn. Checked after walkPlanned, on the same path.
bool patrolOutOfEnergy(SavedBattleGame *save, BattleUnit *unit, const BattleAction &action, bool pushed);
/// FIREPOINT_ENERGY_PATH_V1 (OXCE_AI_FIREPOINT_ENERGY_PATH, bench only): the path the battle's Pathfinding holds - the one
/// findFirePoint just asked for, and handleAI asks for the same before the walk - against what findReachable left for the
/// walk when it let the tile into _reachableWithAttack. Bit 1: the path needs more energy (the walk would stop on energy,
/// UnitWalkBState, and findFirePoint drops the tile); bit 2: more TU (counted only). 0 without the flag.
int firepointPathOver(SavedBattleGame *save, const BattleUnit *unit, int tuMax, int energyMax);
/// FIREPOINT_ENERGY_PATH_V1: the tiles one findFirePoint dropped by energy and found over by TU, one step of the trail
/// "firepoint.energy n<dropped> t<over by TU> mt<movement> en<energy>" and a tally when it dropped any.
void firepointDropped(const BattleUnit *unit, int droppedByEnergy, int overByTu);
/// FIREPOINT_BLOCKED_UNIT_STALL (OXCE_AI_FIREPOINT_BLOCKED, bench only): a walk stopped at a unit on the step in dir
/// (UnitWalkBState); the AI module records it if findFirePoint chose the walk. No-op without the flag.
void firepointBlocked(BattleUnit *unit, const BattleAction &action, int dir);
/// FIREPOINT_BLOCKED_UNIT_STALL: what the unit's side may know of the battle that a path depends on - pathRevision's hash
/// (where units stand, their status, the map's parts, doors, fire, smoke), but of the units only its own side and those
/// its side spotted this turn: a unit it does not see neither keeps nor drops a record. 0 in a release build.
unsigned long long knownRevision(SavedBattleGame *save, const BattleUnit *unit);
/// OXCE_AI_FIREPOINT_BLOCKED_SALT (bench test of the invalidation, not a game fixture): the first check of a record in
/// each unit-turn sees the revision changed. False in a release build.
bool firepointBlockedSalt();
/// A side's turn ends (BattlescapeGame::endTurn): the last decision's action is over.
void sideEnds(SavedBattleGame *save);
/// One line per unit killed or knocked out ([AICASUALTY]): by whom, with what, from how far, on whose turn.
void logCasualty(SavedBattleGame *save, const BattleUnit *victim, const BattleUnit *killer, const std::string &weapon,
	bool dead, int hitSide, bool terrain);

}

}
