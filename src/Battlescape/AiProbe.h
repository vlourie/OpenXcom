#pragma once
#include <climits>
#include <functional>
#include <list>
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
class Pathfinding;
struct BattleAction;
struct BattleActionCost;
struct BattleActionAttack;
struct RuleDamageType;

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
/// The bench autopilot (OXCE_AI_PROBE): plays the player's turns, presses every OK, quits at the end. Off in the play mode.
bool harness();
/// The play mode (OXCE_AI3_PLAY, without OXCE_AI_PROBE): the AI flags work in an ordinary game, nobody presses for the player.
bool play();
/// Screens close by themselves: the bench, or the play mode with the bot on the player's side (headless checks).
bool autoClose();
/// The probe skips everything nobody watches (OXCE_AI_FAST): no frame is drawn, no tile but UFO doors is animated,
/// every unit walks the short off-screen cycle, no final-blow scene, no audio, one log handle for the run, and the process
/// leaves right after the result line. The decisions, the record and the outcome stay the same as without it.
bool fast();
/// May quick flight and loose hits (Options::oxceHdQuickFlight, oxceHdLooseHits) run? They shorten the time a burst
/// takes, and a UFO door's frame goes by that time (R-155): the bench keeps the stock pace unless OXCE_AI_HDPACE asks.
bool hdPace();
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
/// AMBUSH_NEGATIVE_MEMO_V2 (OXCE_AI_AMBUSH_MEMO): inside one setupAmbush, once the enemy's A* to a node ran out of open nodes,
/// a node whose search would end outside the tiles it closed (Pathfinding::closedTiles, finalPositionFor) has no path from
/// the enemy and its search is skipped. The
/// memo lives in that call only. 0 - off (the default), 1 - skip, 2 - verify: search anyway and count answers that disagree
/// (none expected; the control of the statement). In the release build 0.
int ambushMemo();
/// A node the memo answered: skipped - its search was not run (mode 1); ok - what the search still run gave (mode 2);
/// own, score, best as ambushEnemy. [AIAMBN] with memo=1 for a skipped node; counts in [AIAMB] and the memo total line.
void ambushMemoNode(const Position &pos, bool skipped, bool ok, int own, int score, int best);
/// BEST_CELL (bench, OXCE_AI_BEST_CELL=<bits>, docs/research/ai-mechanics/BEST-CELL-2026-10-22.md): the fire point, ambush
/// and escape searches take the best cell, not the first over their "good enough" threshold. 0 (the default, and always in the
/// release build) - the searches as in OXCE.
enum BestCellBits
{
	BC_FP_BEST = 1,    ///< findFirePoint: no early quit over 125, the best cell of the window
	BC_LEVELS = 2,     ///< findFirePoint and setupAmbush: the levels z-1 and z+1 too
	BC_REACHCOST = 4,  ///< the walk cost from findReachable's table; A* only for a cell that may become the best
	BC_AMB_BEST = 8,   ///< setupAmbush: every node of the window, equal scores by chance
	BC_ESC_BEST = 16,  ///< setupEscape: the whole window with no early quit over 100; the random run only if none passed
	BC_HOSTILE = 32,   ///< the bits above for the hostile side only; the player's and the neutral units search as in OXCE
};
int bestCell();
/// The best-cell audit (OXCE_AI_CELLPROF, docs/research/ai-mechanics/FIRST-GOOD-ENOUGH-2026-10-22.md): how long the fire
/// point, ambush and escape searches take, where they quit on their "good enough" threshold, and - by a shadow search on a
/// pathfinder of its own, with no random numbers - how good the chosen cell is against every cell of the same window, of
/// the other levels in the window, and of the reach outside it. Reads only: [AICELL] per search. Off (the default) and in
/// the release build: nothing is counted and no shadow search runs.
bool cellProf();
/// One search: the real loop's numbers, then the shadow's (INT_MIN - no cell scored in that group).
struct CellStat
{
	long long ns = 0;                   // the real search's loop
	int window = 0, scanned = 0, passed = 0, breakAt = -1, chosen = INT_MIN, threshold = 0;
	long long nsFull = 0;               // shadow: every candidate of the real window
	int full = 0, fullAbove = 0, best = INT_MIN, rank = -1, mismatch = 0;
	long long nsZ = 0;                  // shadow: the window's cells on the other levels
	int zCand = 0, zScored = 0, zBest = INT_MIN;
	long long nsFar = 0;                // shadow: the reach outside the window, any level
	int farCand = 0, farScored = 0, farBest = INT_MIN;
	// findFirePoint only: why there is no line - the target's distance (tiles, 3d) and level offset, whether this unit sees it,
	// and what the centre line from the unit's own cell to the target meets first (VoxelType: -1 nothing, 0 floor, 1/2 wall,
	// 3 object, 4 another unit, 5 off the map; 6 - the target itself), the armor of that part and its distance in tiles
	int dist = -1, dz = 0, seen = -1, blk = -2, blkArmor = -1, blkDist = -1;
};
/// A pathfinder of the audit's own for the shadow search: the game's one keeps the state the real search left in it.
/// Null when the audit is off.
Pathfinding *cellPathfinding(SavedBattleGame *save);
/// The search is done: one [AICELL] line.
void cellSearch(SavedBattleGame *save, const BattleUnit *unit, const char *ctx, const CellStat &s);
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
/// ESCAPE_ALT_PROBE (OXCE_AI_ESCAPE_ALT_PROBE with the record, the careful bot only, docs/research/ai-path-audit-2026-10-01.md
/// п. 17.29): was there a reachable tile that dominated the escape tile setupEscape chose? Reads only, no random numbers,
/// no pathfinding, the side's memory of the enemies is copied, never updated. Off (the default): false.
bool escapeAlt(const BattleUnit *unit);
/// One [AIESCALT] line per escape setupEscape chose: the unit's tile, the chosen one and every tile of reachable whose cost
/// (the think's own reach, the record's move list) is at most the chosen tile's plus OXCE_AI_ESCAPE_ALT_CAP (8) time units.
/// Per tile: cost; spot - what setupEscape itself counted (spotting, the engine's getSpottingUnits; it sees every enemy, the
/// oracle column); and from the side's knowledge only: enemies seen now with a line of fire, enemies remembered and not seen
/// now with a line of fire from where they were seen, the threat after their move and how many can come within 3 tiles
/// (threatOf's disc), the distance to the nearest remembered enemy; fire and danger on the tile.
void escapeAltWrite(SavedBattleGame *save, BattleUnit *unit, const std::vector<int> &reachable, const Position &chosen, int score,
	int escapeTUs, bool run, const std::function<int(const Position &)> &spotting);
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
/// PANIC_TURN_FIX (OXCE_AI_PANIC_TURN_FIX, bench only, needs OXCE_AI_BOT): on the bot's turn of the player's side its
/// panicking units are handled first, the way the player branch of BattlescapeGame::think does, and the panic-handled
/// state becomes true as for a human. Without it the state stays false from turn 2 on every side's turn (R-120): half the
/// accuracy, no reaction after a shot, walks not stopped by a newly spotted enemy, the bot's TU cleared after a walk.
bool panicTurnFix();
/// The panic-handled state BattlescapeGame::think sees: one [AIPANIC] line each time it changes (turn, side, value).
void panicState(SavedBattleGame *save, bool handled);
/// A projectile's accuracy divider (ProjectileFlyBState), counted by the shooter's faction, turn 1 or later and 100 or
/// not, for the [AIPANIC] line of the result.
void shotDivider(SavedBattleGame *save, const BattleUnit *shooter, double divider);
/// POSTWALK_FIX (OXCE_AI_POSTWALK_FIX, bench only, needs OXCE_AI_BOT): UnitWalkBState::postPathProcedures runs its AI
/// branch for the bot's player units too - the walk's AIModule decision is carried out as for an AI unit (final facing,
/// finalAction ends the unit's actions, a charge in melee range strikes, a hiding unit turns away). Without it the branch
/// is only for factions other than the player's, and the bot's post-walk decisions are dropped.
bool postWalkFix();
/// UPSTREAM_SPOT (OXCE_AI_UPSTREAM_SPOT, bench only): upstream 6ee48e7d1 "Fix freeze when civilian try move pass alien" -
/// Pathfinding::isBlocked blocks a tile whose unit the mover's SIDE spotted this turn (any faction, not only a hostile
/// mover's own spotted list); calculateUnitsInFOV puts hostile units in the visible list of every non-hostile viewer
/// (neutrals too); getSpottingUnits stamps the spotter side's spotted turn. KNOWN_OCCUPANT_PATH V1 and V2 are off under
/// it (it covers them), unless OXCE_AI_UPSTREAM_KO_KEEP is set to count what they would add. False in a release build.
bool upstreamSpot();
/// UPSTREAM_VIS (OXCE_AI_UPSTREAM_VIS, bench only): upstream 613ec4a28 "Simplify visible enemies code" - five checks of
/// the visible-units list use BattleUnit::hasVisibleUnit, which also says yes for a unit of the viewer's own faction.
bool upstreamVis();
/// UPSTREAM_VIS: does the viewer see the target (check site 0 psiAction, 1 and 2 primaryAction, 3 the visible-unit buttons,
/// 4 eyesOnTarget): hasVisibleUnit with the flag, the visible-units list without it.
bool upstreamSees(const BattleUnit *viewer, const BattleUnit *target, int site);
/// Does postPathProcedures take its AI branch for this player unit: the fix is on, the bot plays the player's side, and
/// the panic-handled state is true (a panicking unit's walk keeps the player branch, as for a human).
bool postWalkAi(const SavedBattleGame *save, const BattleUnit *unit, bool panicHandled);
/// What the walk's decision asks of postPathProcedures, as it begins (reads only), and what was done as it ends:
/// one [AIPOSTWALK] line per walk with a post-walk request, counts in the [AIPOSTWALK] result line.
void postWalkBegin(SavedBattleGame *save, BattleUnit *unit, const BattleAction &action, bool aiBranch);
void postWalkEnd(SavedBattleGame *save, const BattleUnit *unit, bool meleePushed);
/// A melee attack that has spent its TU (MeleeAttackBState): counted when it is the one postPathProcedures pushed.
void postWalkMelee(const BattleUnit *unit);
/// COUNTER_FIX (OXCE_AI_COUNTER_FIX, bench only): the AI action counter of BattlescapeGame is reset when handleAI gets a
/// unit other than the one whose decision last raised it (or the same one on another turn or side) - a new unit starts
/// at action 1. Without it a counter left by a unit that died, fell unconscious or lost the selection otherwise goes on.
bool counterFix();
/// handleAI got this unit with this counter, before its checks: true when the counter is another unit's (or another turn's)
/// and COUNTER_FIX resets it.
bool counterCheck(SavedBattleGame *save, const BattleUnit *unit, int counter);
/// handleAI raised the counter for this unit's decision.
void counterOwn(SavedBattleGame *save, const BattleUnit *unit, int counter);
/// P0-D SECOND_PASS (clean2: always in the bench): handleAI left `left` and selected `selected` - does the AI's second pass
/// begin? On the bot's turn when the selection came round to where the turn's traversal began (the new unit is not further
/// on from the start than the left one): the player's soldiers keep their campaign ids in the base's order, so the upstream
/// test by id ends their first pass at the first lower id, and the player's turn begins with the unit last selected, not at the
/// vector's start. Otherwise upstream's selected id <= left id (hostile and neutral ids are handed out in vector order and their
/// turns begin with nothing selected).
bool secondPassWrapped(SavedBattleGame *save, const BattleUnit *left, const BattleUnit *selected);
/// P0-D SECOND_PASS: handleAI got `unit` - the first one of a side's turn is where that turn's traversal began.
void passStartNote(SavedBattleGame *save, const BattleUnit *unit);
/// U1 A* TOTAL TU COST (OXCE_AI_ASTAR_COST_FIX, bench only): when A* takes the destination off its open list,
/// _totalTUCost becomes that terminal node's cost - the path's cumulative cost - instead of the last neighbour the search
/// tried. The path and the search order stay the same.
bool astarCostFix();
/// U2 SETUPESCAPE DISTANCE SIGN (OXCE_AI_ESCAPE_SIGN_FIX, bench only): the distance term of setupEscape is
/// (newDistance - oldDistance) * 10 - farther from the aggro target positive, closer negative, same 0 - instead of upstream's
/// |newDistance - oldDistance| * 10. Nothing else of setupEscape changes.
bool escapeSignFix();
/// U3 fix (OXCE_AI_STALE_ESCAPE_FIX, bench only): the AI_ESCAPE branch of think runs setupEscape when the escape plan's
/// contract (AIModule::escapePlanBroken) does not hold; a plan that holds is reused as it is, with no new RNG.
bool staleEscapeFix();
/// BetterAI fixes of the stock AI's errors O7-O14 (docs/research/ai-mechanics/BETTERAI-PLAN.md). The player's build: the
/// BetterAI switch and its fixes row (Options::oxceBetterAi, oxceBetterAiFixes); the bench (OXCE_AI_DEV): the play mode by
/// the same options, the harness by OXCE_AI_OXCE_FIXES. The fixes O1-O6 are the clean2 switches above, on by the same rule
/// in the player's build.
bool oxceFixes();
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
/// The number the next [AIREC] of this battle will carry (AI2-A trace lines refer to it); 0 in a release build.
int nextRec();
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
/// REPEATED_BLOCKED_STEP (passive, record only): with save, a stop at a unit ends with " kr<knownRevision>", and the
/// unit's next decisions this turn on the same tile start their [AIEXEC] trail with "kr.dec <knownRevision>" and, if they
/// walk, "walk.first d<first step>" - whether a suppression of that first step would have held. Nothing else reads it.
void walkStop(const BattleUnit *unit, const char *reason, const Position &to, int dir, int bam, int stepTu, int stepEnergy, int blocker,
	SavedBattleGame *save = nullptr);
/// ENERGY_PATROL_END_V2 (OXCE_AI_ENERGY_PATROL_END, bench only): the patrol walk handleAI just planned is stopped by energy,
/// and the unit has less energy than the cheapest step to any neighbouring tile, other units aside - it has no step left
/// this turn. Checked after walkPlanned, on the same path.
bool patrolOutOfEnergy(SavedBattleGame *save, BattleUnit *unit, const BattleAction &action, bool pushed);
/// PATROL_STUN_RESERVE_V1 (OXCE_AI_PATROL_STUN_RESERVE, bench only, the careful bot): the patrol walk handleAI just planned
/// would leave the unit's armor stun recovery at the start of its next turn at or below zero - the energy the path takes
/// (steps it can pay for in TU and energy), then the armor's energy recovery, then the armor's stun recovery at that energy,
/// soldier bonuses included. Only when the energy matters (the recovery at full energy is higher). One [AISTUNRES] line per
/// check. True: handleAI drops the walk; attack, escape and the bot's flee are not patrol walks and are never checked.
/// PATROL_STUN_RESERVE_V2 (OXCE_AI_PATROL_STUN_PREFIX, over V1 when both are set): instead of dropping the walk, keeps the
/// longest prefix of the same path after which the recovery stays above zero (the node and the path are not chosen again);
/// true only when not even one step is safe.
bool patrolStunReserve(SavedBattleGame *save, BattleUnit *unit, const BattleAction &action, bool pushed);
/// FIREPOINT_ENERGY_PATH_V1 (OXCE_AI_FIREPOINT_ENERGY_PATH, bench only): the path the battle's Pathfinding holds - the one
/// findFirePoint just asked for, and handleAI asks for the same before the walk - against what findReachable left for the
/// walk when it let the tile into _reachableWithAttack. Bit 1: the path needs more energy (the walk would stop on energy,
/// UnitWalkBState, and findFirePoint drops the tile); bit 2: more TU (counted only). 0 without the flag.
int firepointPathOver(SavedBattleGame *save, const BattleUnit *unit, int tuMax, int energyMax, Pathfinding *pf = nullptr);
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
/// FIREPOINT_TARGET_CELL_V1 (OXCE_AI_FIREPOINT_TARGET_CELL, bench only): findFirePoint does not take a tile where the unit
/// would stand on its own aggro target as a firepoint - the target is not in the way of that path only because the unit
/// did not spot it this turn (Pathfinding::isBlocked), and the walk stops on it. False in a release build.
bool firepointTargetCell();
/// FIREPOINT_TARGET_CELL_V1: one findFirePoint dropped the target's tile (cell) - found it another point or none; one step of
/// the trail "firepoint.target_cell <cell> -> <point>|none" and the tallies firepoint.target_cell_rejected and
/// firepoint.target_cell_rejected_then_found_other / _then_no_firepoint.
void firepointTargetCellRejected(const BattleUnit *unit, const Position &cell, bool found, const Position &point);
/// KNOWN_OCCUPANT_PATH_V1 (OXCE_AI_KNOWN_OCCUPANT_PATH, bench only): an enemy AI unit's paths take the tile of its closest
/// known target (the one selectClosestKnownEnemy gives findFirePoint) as blocked if its side spotted that target this turn -
/// the AI aims at it there, but Pathfinding::isBlocked sees only the units this unit spotted itself. No other or older
/// target, nothing the side has not spotted, not for missiles. False in a release build.
bool knownOccupantPath();
/// KNOWN_OCCUPANT_PATH_V1: an enemy's decision is made (after its thinks). Tallies knownocc.target_set (the closest known
/// target was spotted this turn) or knownocc.target_age_old (it was not - the rule held back); if the thinks' searches took the
/// target's tile as blocked (hits), knownocc.blocked, knownocc.blocked_<walk> (firepoint, patrol, walk_other, nowalk),
/// knownocc.target_is_aggro / _not_aggro (the decision's _aggroTarget) and the trail step "knownocc <id> <tile> b<hits>".
void knownOccupantDecided(const BattleUnit *unit, const BattleUnit *occupant, int age, int hits, const BattleUnit *aggro, const char *walk);
/// KNOWN_OCCUPANT_PATH_V1: the walk's own path is calculated; if its search took the tile as blocked, knownocc.path_replanned
/// (it found a path) or knownocc.no_path, and the trail step "knownocc.walk b<hits> <to> found|none".
void knownOccupantWalked(const BattleUnit *unit, const BattleUnit *occupant, int hits, const Position &to, bool found);
/// KNOWN_OCCUPANT_PATH_V2 (OXCE_AI_KNOWN_OCCUPANT_PATH_V2, bench only): the target T findFirePoint and setupAmbush chose
/// (_aggroTarget), if the enemy's side spotted it this turn, blocks its tile for those two branches' own path searches and for
/// the walk to the point they chose - nothing else: not findReachable, patrol, escape, melee, shots, psi, grenades, missiles.
/// Off while V1 is on. False in a release build.
bool knownOccupantPathV2();
/// KNOWN_OCCUPANT_PATH_V2: an enemy's decision is made. Per branch (fp, amb) that ran this think: knownocc2.<b>.target_set
/// (T supplied) or knownocc2.<b>.target_age_old (T not spotted this turn - held back); knownocc2.<b>.search_blocked if a search
/// took T's tile as blocked (trail "knownocc2 <b> <id> <tile> b<hits>"); knownocc2.<b>.chosen if the decision walks there.
void knownOccupantV2Decided(const BattleUnit *unit, const char *branch, const BattleUnit *target, bool old, int hits, bool chosen);
/// KNOWN_OCCUPANT_PATH_V2: the walk to the branch's point is calculated with T's tile blocked: knownocc2.walk_<b>; if it took
/// the tile (hits), knownocc2.walk_<b>.path_replanned or .no_path and the trail "knownocc2.walk <b> b<hits> <to> found|none".
void knownOccupantV2Walked(const BattleUnit *unit, const char *branch, int hits, const Position &to, bool found);
/// PATROL_REUSE_PROBE (OXCE_AI_PATROL_REUSE_PROBE, bench only, passive): setupPatrol keeps the node it stored in an earlier
/// think (_toNode, not reached) instead of choosing one - classify it as the decision is made. Play does not read any of it;
/// the occupant is the bench's oracle, not what the AI knows. False in a release build.
bool patrolReuseProbe();
/// PATROL_REUSE_PROBE: one decision whose last setupPatrol kept the stored node. Tallies patrol.reuse.<cls> (valid,
/// occupied_own, occupied_ally, occupied_enemy_seen_this_turn, occupied_enemy_known_old, occupied_enemy_never_seen,
/// unreachable), for a free node also patrol.reuse.route_<who> (the first unit on the path the unit's own search takes, the
/// same classes) or patrol.reuse.route_free; patrol.reuse.chosen.<cls> if the decision walks to the node. The trail step
/// "patrol.reuse <cls> node <xyz> age <turns> reach 0|1 first <xyz> occ <id>/<faction>/s<seen> route <id>/<faction>/s<seen>@<xyz>".
void patrolReuseDecided(const BattleUnit *unit, const char *cls, const char *route, bool chosen, const std::string &trail);
/// PATROL_NO_PATH_CAUSE (OXCE_AI_PATROL_NOPATH_PROBE with OXCE_AI_PATROL_REUSE_PROBE, bench only, passive): for a kept node
/// that is free and has no path, the same search again with units let through (Pathfinding::probeReach). False in a release build.
bool patrolNoPathProbe();
/// PATROL_NO_PATH_CAUSE: one such decision. Tallies patrol.nopath.<cause> and patrol.nopath.chosen.<cause> if it walks to the
/// node; the cause: own, seen, own_or_seen (either let through is enough), own_and_seen (only both), unit_rule (only every
/// unit: the big-unit and falling rules, whatever the side knows), geometry (no path without any unit), geometry_refused (the
/// destination refused even then). The reuse trail gets " nopath <cause> fin <xyz>|none r <own>/<seen>/<both>/<all>
/// exp <real>/<own>/<seen>/<both>/<all>" (1 path, 0 none, -1 refused; nodes the A* closed).
void patrolNoPathDecided(const BattleUnit *unit, const char *cause, bool chosen);
/// STALE_PATROL_NODE_V1 (OXCE_AI_STALE_PATROL_NODE, bench only): setupPatrol drops the node it kept from an earlier think
/// when this unit's own search finds no path to it, and chooses again as for a new node (which needs a path). False in a
/// release build.
bool stalePatrolNode();
/// STALE_PATROL_NODE_V1: one check of a kept node. Tallies patrol_stale.checked; when dropped also patrol_stale.no_path,
/// .cleared and .reselected or .reselect_failed, and the trail "patrol.stale old <xyz> age <turns> new <xyz>|-".
void stalePatrolChecked(const BattleUnit *unit, bool cleared, const Position &old, int age, const Position &now);
/// STALE_REACH_SHADOW (OXCE_AI_STALE_SHADOW with OXCE_AI_STALE_PATROL_NODE, bench only, passive): profile the STALE check's
/// search and ask the same question by Pathfinding::witnessReach at several weights. False in a release build.
bool staleShadow();
/// STALE_REACH_SHADOW: one STALE check - the real search's answer, the nodes its A* closed (0 after a straight path or a
/// refusal), its path cost and time; logs "[AIPF] stale ..." with the witness searches' answers, nodes, costs and times.
/// Leaves the pathfinder's path, nodes and counts as they were.
void staleShadowAsk(SavedBattleGame *save, BattleUnit *unit, const Position &node, bool noPath, int expanded, int cost, long long ns);
/// EXACT_STALE_REACH_V1 (OXCE_AI_STALE_EXACT with OXCE_AI_STALE_PATROL_NODE, bench only): how the STALE check is answered.
/// 0 the full search (calculate); 1 Pathfinding::witnessReach at weight 4 - a found path or a proven none decide, anything
/// else goes to the full search; 2 the same, and the full search runs every time to compare (the witness still decides);
/// 3 the broken control: a found path dearer than 300 TU is called none - the bench's play must change. 0 in a release build.
int staleExact();
/// EXACT_STALE_REACH_V1: one check. ans 1 path, 0 none, 2 unknown (the full search decided); expanded the witness's nodes;
/// full the full search's answer (1 path, 0 none) or -1 when it did not run. Tallies p./h.stale_witness_yes, _no, _unknown,
/// _fallback_full, _expanded, and with a decided ans and full run _verified, _mismatch (logs "[AIPF] stale_exact mismatch").
void staleExactAsked(const BattleUnit *unit, const Position &node, int ans, int expanded, int full);
/// REPEATED_BLOCKED_STEP_V1 (OXCE_AI_BLOCKED_STEP, bench only): a walk stopped at a unit on the step in dir from where the
/// unit stands (UnitWalkBState). Remembered for the rest of the unit-turn while knownRevision stays what it was then; another
/// stop there at the same revision adds its step. No-op without the flag.
void blockedStepStop(SavedBattleGame *save, BattleUnit *unit, int dir);
/// REPEATED_BLOCKED_STEP_V1: a decision of the unit (handleAI, any action) - drops the steps it remembers when the unit-turn or
/// knownRevision changed (the unit's own move changes the revision).
void blockedStepDecide(SavedBattleGame *save, BattleUnit *unit);
/// REPEATED_BLOCKED_STEP_V1: the walk handleAI just calculated starts with a remembered step - calculates the path again
/// with the remembered steps banned as first steps: a way round them, or none.
void blockedStepPlan(SavedBattleGame *save, BattleUnit *unit, const BattleAction &action);
/// A side's turn ends (BattlescapeGame::endTurn): the last decision's action is over.
void sideEnds(SavedBattleGame *save);
/// A stage of SavedBattleGame::endTurn (OXCE_AI_ATTRIB_PROBE): one [AITURNFX] line per unit whose health, stun or status
/// changed since the side's turn ended or since the previous stage. Reads only; no-op without the flag.
void turnStage(SavedBattleGame *save, const char *stage);
/// One line per unit killed or knocked out ([AICASUALTY]): by whom, with what, from how far, on whose turn.
void logCasualty(SavedBattleGame *save, const BattleUnit *victim, const BattleUnit *killer, const std::string &weapon,
	bool dead, int hitSide, bool terrain);
/// One line per event the gentle on/off check must cover ([AIEVENT]): a reaction shot, an area explosion; the camera's
/// floor is logged by think. Separate from [AIRESULT] tac=, so the AI series comparing builds do not see it.
void event(SavedBattleGame *save, const char *what, const BattleUnit *unit, const Position &pos);
/// WOUNDED_COMBAT_DECISION_V1 (OXCE_AI_MEDIPROBE with the record): BattleUnit::think runs AIModule::medikit_think once a turn,
/// before the AI picks its mode. medikitBefore snaps the unit before the loop of one kind (1 heal, 2 stimulant), medikitAfter
/// writes one [AIMEDI] line: the unit's state before and after, the medikits it carries, which of them it may use on itself
/// now, the chance medikit_think would roll, how many uses the loop made, and the first gate it stopped at. Mirrors the gates,
/// never the dice: reads only, no random numbers. Off (the default): nothing.
void medikitBefore(const BattleUnit *unit, int kind);
void medikitAfter(const BattleUnit *unit, int kind, int used);

/// AI2-B2 EXPLOSIVE UTILITY MEASUREMENT (OXCE_AI_BLAST_PROBE, with the record): what each explosion did to each unit it
/// hit ([AIBHIT]), the explosion itself and the decision behind it ([AIBLAST]), and the terms of explosiveEfficacy for the
/// decision's target ([AIEFF]). Plain reads and log lines: no random numbers, no game state is written.
bool blastProbe();
/// What BattleUnit::damage used for the hit being logged: filled only while armed (TileEngine::hitUnit inside an explosion).
struct DmgNote
{
	bool armed = false, reached = false;
	int side = -1, part = -1, resisted = 0, scripted = 0, armor = -1, afterArmor = 0;
};
extern DmgNote dmgNote;
/// The unit as the explosion is about to hit it.
struct BlastPre
{
	int hp = 0, stun = 0, fire = 0, tu = 0, morale = 0, status = 0;
	int armor[5] = {};
	bool down = false;
};
/// TileEngine::explode: the explosion begins, one ray reaches a new tile (its remaining power, distance, rolled damage), it ends.
void blastBegin(SavedBattleGame *save, const BattleActionAttack &attack, const Position &center, int power, int powerUsed,
	const RuleDamageType *type, int radius);
void blastTile(int power, double l, int damage);
void blastEnd(SavedBattleGame *save);
/// TileEngine::hitUnit: true (and the unit read) only inside an explosion with the probe on.
bool blastBefore(const BattleUnit *unit, BlastPre &pre);
void blastAfter(SavedBattleGame *save, const BattleUnit *unit, const Position &relative, int damage, const BlastPre &pre);
/// The terms of one explosiveEfficacy call; kept for the decision about to be recorded.
struct EffNote
{
	int unit = -1, x = 0, y = 0, z = 0, radius = 0;
	bool grenade = false;
	int diff = 0, desp = 0, targetFaction = -1;
	bool hurt = false, kamikaze = false, noDiff = false;
	/// id, faction, weight, verdict: 0 counted, 1 line blocked, 2 tile already dangerous, 3 weight 0 (unknown to the AI),
	/// 4 the target, 5 the target on a dangerous tile (not counted), 6 the attacker itself in range (never counted)
	std::vector<std::vector<int>> units;
	int enemies = 0, efficacy = 0, result = 0;
	const char *path = "";
};
void effDone(const EffNote &note);
/// AI2-B2 blaster: AIModule::wayPointAction picked its target (the unit, whose tile explosiveEfficacy was called for) and laid
/// the waypoints; the launch aims at the first waypoint, so the probe keeps the target, the first waypoint and the last apart.
void blastWaypoints(const BattleUnit *unit, const BattleUnit *target, const std::list<Position> &waypoints);
/// The decision is recorded: its aim (for [AIBLAST]), the thrown item (a delayed grenade), the efficacy terms ([AIEFF]).
void blastDecision(SavedBattleGame *save, const BattleUnit *unit, const BattleAction &action, int rec);

/// AI2-G HYPO_LOS (bench flag OXCE_AI_HYPO_LOS; 0 - D1, 1 - TileEngine::canTargetUnit sees a hypothetical unit when a line
/// reaches the place of its body unhit). Diagnostics only with 1: canTargetUnit reports each hypothetical call (hypoNote: the
/// verdict without the fix and with it, whether the unit stands on the tile, whether a line reached the place unhit); the AI's
/// callers open a context (hypoBegin/hypoEnd: escape, ambush, facing, firepoint, tactical) and the reports are summed per
/// candidate tile into one [AITRACE] ai2g line; the probe's own checks run under a tag (HypoTag). Plain reads and log lines:
/// no random numbers, no game state is written. 0 in a release build.
int hypoLos();
/// Inside HypoOld canTargetUnit answers as D1 and reports nothing (the old verdict of an ambush node, for the line only).
bool hypoForceOld();
void hypoNote(const BattleUnit *potential, const BattleUnit *exclude, const Position &pos, bool oldSeen, bool newSeen, bool onTile,
	bool lineFree);
void hypoBegin(const BattleUnit *unit, const char *ctx, int spotNow);
void hypoEnd(const BattleUnit *unit, const char *ctx, bool ok, const Position &at, int score);
/// setupAmbush: the node about to be checked and whether it passes the same two checks without the fix.
void hypoAmbushNode(const Position &pos, bool oldAccept);
/// findFirePoint: the score before the range scaling, and the scaling's two distances when it applies.
void hypoPre(const Position &pos, int score);
void hypoScale(const Position &pos, int distanceToTarget, int proposedDistance);
struct HypoTag
{
	const char *prev;
	explicit HypoTag(const char *tag);
	~HypoTag();
};
struct HypoOld
{
	bool prev;
	HypoOld();
	~HypoOld();
};

/// AI2-H FAIR KNOWLEDGE (bench flag OXCE_AI_FAIR_KNOWLEDGE, read once; 0 - as AI2_BASELINE_HYPO_LOS, 1 - the AI places a known
/// enemy it does not see now at the place its side last honestly saw it, BattleUnit::updateHonestKnownPosition; a known enemy its side never
/// saw has no place). The hostile side under the cheat keeps the current place of player units. 0 in a release build.
int fairKnowledge();
/// AI2-H5 MELEE FIREPOINT APPROACH (bench flag OXCE_AI_MELEE_FIREPOINT_APPROACH, read once; 0 - baseline, 1 - in findFirePoint a
/// unit whose only usable attack is a melee blow treats the target as out of attack range until the blow can be made). 0 in a release build.
bool meleeFirepointApproach();
/// The one rule of the known place (all AI consumers go through AIModule::knownPlace, which calls this): 0 - the current place
/// (flag off, own side, the cheat, or the remembered place is the current one), 1 - the remembered place and facing (known, dir),
/// 2 - no place (the side never saw the unit).
int fairPlace(const SavedBattleGame *save, const BattleUnit *decider, const BattleUnit *target, Position &known, int &dir);
/// One [AITRACE] {"ai2h":1,...} line per decision record, consumer and target: the place the AI used instead of the current one (kind 1), or
/// no place at all (kind 2). Plain log lines.
void fairNote(const BattleUnit *unit, const BattleUnit *target, const char *cons, int kind, const Position &known, const Position &now);
/// The decision record is written: the gates' checks (an aim at the current place of a displaced target, visible enemies whose
/// remembered place is not the current one). Plain reads and log lines.
void fairDecision(SavedBattleGame *save, const BattleUnit *unit, const BattleAction &action);
/// A melee probe: the unit stands in reach of the remembered place of the target and the target is not there (the player's
/// 'there is no one there'); one [AITRACE] {"ai2h":1,"probe":...} line, occupant -1 for an empty tile.
void fairProbe(const BattleUnit *unit, const BattleUnit *target, const Position &known, const BattleUnit *occupant);
/// OXCE_AI_FAIR_SAVECHECK=1: each side's start writes every unit to YAML and reads it back, and compares the remembered places.
void fairSaveCheck(SavedBattleGame *save);
/// h5 (gate 6 proof): the side's memory of target changed from old to now (BattleUnit::logAiSeenChange) - one passive
/// [AITRACE] {"ai2h":1,"mw":...} line with the reason, the observer and the state that allowed the write. Reads only.
/// h6: plus basis - the proof of the reveal (fov, reaction, shot_from_cell, seen_now; LOAD / RESET / FORGET_PROBE pass "").
void fairWrite(const SavedBattleGame *save, const BattleUnit *target, int side, const char *reason, const int *old, const int *now,
	const BattleUnit *observer, int a, int b, const char *basis = "");
/// h6: the honest-memory gate refused a reveal (no proof the side gets the place now) - one passive [AITRACE] {"ai2h":1,"deny":...}
/// line: reason, the memory kept, whether the write would have changed it, the state. Reads only.
void fairDeny(const SavedBattleGame *save, const BattleUnit *target, int side, const char *reason, const int *mem, bool change,
	const BattleUnit *observer, int a, int b);
/// h6: a live unit of the side has target on its visible list now (the engine's honest sighting state). false in a release build.
bool fairSideSeesNow(const SavedBattleGame *save, int side, const BattleUnit *target);
/// h7: a voxel test met a unit moved by AiKnownPlace. what: 0 trueHit - the true body stopped a line (the control
/// OXCE_AI_FAIR_TRUEBODY=1; TRUE_BODY_INTERCEPT_WHILE_VIRTUAL), 1 badPart - a 2x2 part outside the body (no hit instead of the
/// crash), 2 skipHit - the true body skipped where h6 would have hit it, 3 skipBadPart - skipped where h6 would have crashed,
/// 4 virtHit - the body at the known place stopped a line. Counted; the decision record writes one [AITRACE] {"ai2h":1,"vgeo":...}.
void fairGeo(int what, const BattleUnit *target);
/// h8 knowledge contract: what the deciding side knows about the target's place now. FAIR_LEGACY - flag off or own side (no rule);
/// FAIR_CURRENT - the side honestly observes it now (a live unit has it on its visible list, or has it in its view sector and
/// TileEngine::visible - the same proof that writes the honest memory, AI_REVEAL_FOV); FAIR_LAST_SEEN - only the remembered place
/// (mem, dir); FAIR_UNKNOWN - no place; FAIR_CHEAT - the hostile side under the cheat, as before. Reads only.
enum FairState { FAIR_LEGACY = 0, FAIR_CURRENT = 1, FAIR_LAST_SEEN = 2, FAIR_UNKNOWN = 3, FAIR_CHEAT = 4 };
int fairState(SavedBattleGame *save, const BattleUnit *decider, BattleUnit *target, Position &mem, int &dir);
/// h8: one [AITRACE] {"ai2h":1,"sel":...} line per record, selector and target: the state, whether the old 360 ray to the true tile
/// passed (oldPass, -1 not asked), whether the target passed now and which place the selector used ("now", "mem", "none").
/// used "now" with state LAST_SEEN/UNKNOWN is TRUE_HIDDEN_POSITION_READ_AFFECTING_AI ("hid":1).
void fairSel(const BattleUnit *unit, const BattleUnit *target, const char *cons, int state, int oldPass, int newPass,
	const char *used, const Position &mem);
/// h8: the selector's pick (one line per call that picked): target, state, place used, tally.
void fairPick(const BattleUnit *unit, const BattleUnit *target, const char *cons, int state, const char *used, int tally);

}

}
