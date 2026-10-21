#pragma once
/*
 * Copyright 2010-2016 OpenXcom Developers.
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
#include "../Engine/Yaml.h"
#include "BattlescapeGame.h"
#include "Position.h"
#include "../Savegame/BattleUnit.h"
#include <climits>
#include <vector>


namespace OpenXcom
{

class SavedBattleGame;
class BattleUnit;
struct BattleAction;
class BattlescapeState;
class Node;
class Tile;

enum AIMode { AI_PATROL, AI_AMBUSH, AI_COMBAT, AI_ESCAPE };
enum AIAttackWeight : int
{
	/// Base scale of attack weights
	AIW_SCALE = 100,
	AIW_IGNORED = 0,
};

/**
 * AI2-H FAIR KNOWLEDGE: for its scope the unit stands, for the geometry the AI computes, at the place where the AI's side
 * last honestly saw it (its position, tile pointer and facing); the tiles' occupants and all else stay as they are, and all
 * is restored at the end. Inactive unless the known place is not the current one (AIModule::knownPlace kind 1).
 */
class AiKnownPlace
{
	BattleUnit *_unit;
	Position _pos;
	Tile *_tile;
	int _dir;
	bool _on;
public:
	AiKnownPlace(SavedBattleGame *save, BattleUnit *unit, int kind, const Position &pos, int dir);
	~AiKnownPlace();
	AiKnownPlace(const AiKnownPlace &) = delete;
	AiKnownPlace &operator=(const AiKnownPlace &) = delete;
	bool on() const { return _on; }

	/// h7 (variant B): the units moved now. For the AI's geometry a moved unit exists only at its known place: its body on
	/// the true tiles stops no line (TileEngine::voxelCheck), and its virtual body stands on the known tiles. Empty with the
	/// flag off, so the engine's paths are as before. OXCE_AI_FAIR_TRUEBODY=1 - the control: h6 geometry (the true body
	/// stays, no virtual one), only a part outside a 2x2 body is no hit instead of the crash.
	static bool any() { return !_moved.empty(); }
	static bool trueBody();
	static bool moved(const BattleUnit *unit);
	/// The tile is one the moved unit stands on at its known place (pokeUp: or the tile above, which its body reaches).
	static bool atKnown(const SavedBattleGame *save, const BattleUnit *unit, const Tile *tile, bool pokeUp);
	/// The moved unit standing at its known place on this tile (as Tile::getUnit), 0 if none.
	static BattleUnit *knownOn(const Tile *tile);
	/// As Tile::getOverlappingUnit, for the known places: a moved unit on the tile, or one below whose body reaches into it.
	static BattleUnit *knownOverlapping(const SavedBattleGame *save, const Tile *tile);
	/// The unit on the tile as the AI's geometry sees it (Tile::getUnit when nothing is moved or in the control).
	static BattleUnit *unitOn(const Tile *tile);
private:
	static std::vector<BattleUnit *> _moved;
};

/**
 * This class is used by the BattleUnit AI.
 */
class AIModule
{
private:
	SavedBattleGame *_save;
	BattleUnit *_unit;
	BattleUnit *_aggroTarget;
	int _knownEnemies, _visibleEnemies, _spottingEnemies;
	int _escapeTUs, _ambushTUs;
	int _walkAbortCounter;
	bool _weaponPickedUp;
	bool _rifle, _melee, _blaster, _grenade;
	bool _traceAI, _didPsi;
	int _AIMode, _intelligence, _closestDist;
	Node *_fromNode, *_toNode;
	bool _foundBaseModuleToDestroy;
	std::vector<int> _reachable, _reachableWithAttack, _wasHitBy;
	BattleActionType _reserve;
	UnitFaction _targetFaction;

	BattleAction _escapeAction, _ambushAction, _attackAction, _patrolAction, _psiAction;
	/// U3 escape plan contract (bench, clean1: always in the bench): what setupEscape computed _escapeAction for. The module is
	/// the unit's own, so the unit is the same by construction. Written always, read only by escapePlanBroken.
	struct EscapePlan
	{
		bool valid = false;           // setupEscape ran (a found tile or BA_RETHINK, both are a plan)
		int turn = -1, side = -1;     // the turn of the side it ran in
		Position origin;              // where the unit stood
		BattleUnit *aggro = nullptr;  // the target it measured from, nullptr none
	};
	EscapePlan _escapePlan;
	/// 0 the escape plan fits the unit now, else the first term it breaks: 1 never computed, 2 another turn of the side,
	/// 3 another origin, 4 no destination tile, 5 destination not reachable (a known unit on it included), 7 aggro out.
	/// (6, a unit on it, is not a term of its own: one the unit knows of makes it 5, one it does not is no reason.)
	int escapePlanBroken() const;
	/// The shot chosen by evalFireAction (OXCE_AI_EVAL): kneel for it, and whether it chose one this think.
	bool _evalKneel = false, _evalChosen = false;
	/// The bench's decision record (AiProbe::propose, docs/AI_DECISION_RECORD.md): the score the rule that ran last gave its
	/// action and, if it names itself more exactly than its caller, its name. Written, never read by play.
	int _probeScore = INT_MIN;
	const char *_probeSource = nullptr;
	/// AI3-FF (bench, OXCE_AI_FF_RISK): units of the target faction the last explosiveEfficacy counted (written always, read
	/// only with the flag); the throw grenadeAction found and left for ffThrowOrShot (bit 2); the decision ff.trade was noted in.
	mutable int _ffEnemies = 0;
	mutable int _ffNoteRec = -1, _ffSecRec = -1;
	bool _ffThrow = false, _ffThrowNode = false;
	int _ffThrowEnemies = 0;
	Position _ffThrowAt;
	BattleItem *_ffThrowItem = nullptr;
	/// ENERGY_PATROL_END_V2 (bench, AiProbe::patrolOutOfEnergy): the unit-turn (turn and side) its patrol walks are spent in.
	int _patrolSpent = -1;
	/// Where it stood and how much energy it had then: a unit moved or given energy (a stimulant) may walk again.
	Position _patrolSpentAt;
	int _patrolSpentEnergy = -1;
	/// This think's action is the patrol's walk to its node.
	bool _patrolWalk = false;
	/// The think after a spent patrol dropped: 1 asked for it (BA_RETHINK), 2 this think is it (no second ask).
	int _patrolRetry = 0;
	/// AI3-IMM (bench): the think after an immobile unit's walk dropped - 1 asked for it (BA_RETHINK), 2 this think is it.
	int _immRetry = 0;
	/// AI3-RETRY (bench, OXCE_AI_FAILED_RETRY): an action handleAI handed on (walk or attack) and the unit's state when it was
	/// decided; a ban is such an action after which the state did not change (it was not carried out), with why: p no path,
	/// s the walk stopped at once, a the attack did nothing. Kept for one unit-turn. The reserve and running the think chose
	/// belong to the action: a walk the patrol's reserve stopped is another walk without it.
	struct RetryKey { int type; Position target; int weapon; int reserve; bool run; char why; unsigned long long print; };
	std::vector<RetryKey> _retryBans;
	RetryKey _retryLast = { 0, Position(), -1, 0, false, 0, 0 };
	bool _retryHaveLast = false;
	int _retryTurn = -1;
	unsigned long long _retryNow = 0;
	/// The unit's own state and what it sees (FAIR: own state and visible units only).
	unsigned long long retryPrint() const;
	/// What findReachable left for the walk when it made _reachableWithAttack: the unit's TU and energy less the attack's
	/// (FIREPOINT_ENERGY_PATH_V1, bench, AiProbe::firepointPathOver).
	int _reachableTuMax = 0, _reachableEnergyMax = 0;
	/// FIREPOINT_BLOCKED_UNIT_STALL (bench, AiProbe::firepointBlocked): the point findFirePoint chose in this think - one
	/// function for firepoint, its fallback and random, so the source is not part of the key.
	bool _firepointChosen = false;
	Position _firepointChosenAt;
	/// The firepoint walk a unit stopped (walk.stop.unit) and the state it was asked in: while all of it holds, any point
	/// by the same first step from there meets the same unit, and findFirePoint skips it. Any change drops the record.
	bool _fpBlocked = false;
	Position _fpBlockedPoint, _fpBlockedFrom, _fpBlockedAggroPos;
	int _fpBlockedDir = -1, _fpBlockedTu = -1, _fpBlockedTurn = -1, _fpBlockedAggro = -1;
	unsigned long long _fpBlockedRev = 0;
	/// A record dropped by a change: the same step from the same place stopped again is a retry after invalidation.
	bool _fpInvalidated = false;
	Position _fpInvalidatedFrom;
	int _fpInvalidatedDir = -1;
	/// This think skipped a blocked point (the outcome tally); the unit-turn the test salt was used in.
	bool _fpSuppressedNow = false;
	int _fpSaltTurn = -1;
	/// Does the record still hold for this ask? If not, drops it and says why.
	bool firepointBlockedHolds();
	/// The record of one blocked firepoint walk: a real stop or V1's suppression (FIREPOINT_BLOCKED_V2_INTEROP).
	void recordFirepointBlockedAttempt(const BattleAction &action, int dir, bool v1Suppression);
	/// KNOWN_OCCUPANT_PATH_V1 (bench): the closest known target if the side spotted it this turn; how long ago the side
	/// spotted the closest known target as this think started (-1: none).
	const BattleUnit *knownOccupant(int &age) const;
	int _knownOccAge = -1;
	/// KNOWN_OCCUPANT_PATH_V2 (bench): the branch's target T (_aggroTarget) if the side spotted it this turn; old: there is a
	/// target but it was not spotted this turn. Null with the flag off or for a unit not of the enemy.
	const BattleUnit *knownOccupantV2(bool &old) const;
	/// KNOWN_OCCUPANT_PATH_V2: this unit's own path search to pos, T's tile blocked if T is given; adds what it blocked to hits.
	void calculateKnownOccupantV2(const Position &pos, const BattleUnit *target, int &hits);
	/// KNOWN_OCCUPANT_PATH_V2: per think, what findFirePoint / setupAmbush supplied and blocked; the T of the point they chose
	/// (setupAmbush keeps its point across thinks while _ambushTUs holds, so its T lives with _ambushAction).
	const BattleUnit *_ko2FpTarget = 0, *_ko2AmbTarget = 0, *_ko2FpChosenTarget = 0, *_ko2AmbChosenTarget = 0;
	bool _ko2FpOld = false, _ko2AmbOld = false, _ko2FpRan = false, _ko2AmbRan = false;
	int _ko2FpHits = 0, _ko2AmbHits = 0;
	/// KNOWN_OCCUPANT_PATH_V2: the walk this think decided on, if it goes to a point one of the two branches chose: its T and
	/// branch ("fp", "amb"); null otherwise.
	const BattleUnit *_ko2WalkTarget = 0;
	const char *_ko2WalkBranch = 0;
	Position _ko2WalkTo;
	/// PATROL_REUSE_PROBE (bench, passive): the turn setupPatrol chose _toNode in (-1: before this battle's play, as a save
	/// loads it); what the last setupPatrol of this decision found when it kept the stored node (empty class: it did not).
	/// Written, never read by play.
	int _toNodeTurn = -1;
	/// O14 (BetterAI): the turn whose first decision cleared _wasHitBy (-1: none since the module was made or loaded).
	int _wasHitByTurn = -1;
	std::string _prClass, _prRoute, _prTrail;
	Position _prNode;
	/// PATROL_NO_PATH_CAUSE (bench, passive): why the kept free node has no path (empty: not probed or not that case)
	std::string _prCause;
	/// PATROL_REUSE_PROBE: classifies the stored node setupPatrol is about to keep (its own search, then abortPath, as the
	/// choice of a node does); a unit's class as the unit's side sees it.
	void patrolReuseProbe();
	const char *patrolReuseWho(const BattleUnit *other) const;
	/// _reachableWithAttack for this attack, and what it left for the walk.
	void reachableWithAttack(const BattleActionCost &cost);
	int unitTurn() const;
	/// Marks the patrol's walk in action and drops it if the patrol is spent here (both think and dont_think end in it);
	/// with retry the first drop thinks once more, as the empty walk it replaces was followed by a think.
	void endPatrolIfSpent(BattleAction *action, bool retry);
	/// A slot's action before a rule runs: the record hears of the rule only if it changed the slot.
	struct ProbeMark { BattleActionType type; Position target; const BattleItem *weapon; };
	const BattleAction &probeAction(char slot) const;
	ProbeMark probeMark(char slot) const;
	void probeSlot(char slot, const char *source, const ProbeMark &before);

	bool selectPointNearTargetLeeroy(BattleUnit *target, bool canRun);
	int selectNearestTargetLeeroy(bool canRun);
	int meleeActionLeeroy(bool canRun);
	void dont_think(BattleAction *action);
public:
	bool medikit_think(BattleMediKitType healOrStim);
public:
	/// Creates a new AIModule linked to the game and a certain unit.
	AIModule(SavedBattleGame *save, BattleUnit *unit, Node *node);
	/// Cleans up the AIModule.
	~AIModule();
	/// The fingerprint of this module's own state (the AI turn probe logs it before and after each decision).
	unsigned long long probeHash() const;
	/// AI3-RETRY (bench): before a selection's think - the state now; the action handed on last left it unchanged: a ban.
	void retryBegin();
	/// AI3-RETRY: is this action banned in the state retryBegin saw? Returns the ban's why, 0 if not banned.
	char retryBanned(const BattleAction &action) const;
	/// AI3-RETRY: the action handleAI hands on (why as above for the case it fails); other types forget the last one.
	void retryRemember(const BattleAction &action, char why);
	/// Sets the target faction.
	void setTargetFaction(UnitFaction f);
	/// Resets the unsaved AI state.
	void reset();
	/// Loads the AI Module from YAML.
	void load(const YAML::YamlNodeReader& reader);
	/// Saves the AI Module to YAML.
	void save(YAML::YamlNodeWriter writer) const;
	/// Runs Module functionality every AI cycle.
	void think(BattleAction *action);
	/// Sets the "unit was hit" flag true.
	void setWasHitBy(BattleUnit *attacker);
	/// Increases the walk abort counter.
	void increaseWalkAbortCounter() { _walkAbortCounter++; }
	/// The walk abort counter: over 200, the next think clears the unit's time units first (the AI freeze workaround).
	int getWalkAbortCounter() const { return _walkAbortCounter; }
	/// Sets the "unit picked up a weapon" flag.
	void setWeaponPickedUp();
	/// Gets whether the unit was hit.
	bool getWasHitBy(int attacker) const;
	/// Set start node.
	void setStartNode(Node *node) { _fromNode = node; }
	/// setup a patrol objective.
	void setupPatrol();
	/// setup an ambush objective.
	void setupAmbush();
	/// setup a combat objective.
	void setupAttack();
	/// setup an escape objective.
	void setupEscape();
	/// count how many xcom/civilian units are known to this unit.
	int countKnownTargets() const;
	/// AI2-H FAIR KNOWLEDGE: where this AI may place the target - 0 its current place, 1 the place its side last honestly saw it
	/// (pos, dir), 2 nowhere (never seen). The one rule for every audited consumer (AiProbe::fairPlace); logs [AITRACE] ai2h once per
	/// decision, consumer and target. Always 0 with the bench flag off.
	int knownPlace(const BattleUnit *target, const char *cons, Position &pos, int &dir) const;
	/// Is the tile where this side knows the target to be marked dangerous (grenaded)? Never seen - no tile, not dangerous.
	bool knownDangerous(const BattleUnit *target) const;
	/// The target's position as this side knows it: kp for kind 1, its position for kind 0, (-1,-1,-1) for never seen.
	Position knownPos(const BattleUnit *target, const char *cons) const;
	/// Melee reach from a tile to the target where this side knows it to be: the engine's validMeleeRange for kind 0, a
	/// hypothetical body at kp for kind 1 (tile occupancy is not read), no reach for kind 2.
	bool knownMeleeRange(Position from, BattleUnit *target, int kind, const Position &kp, int kdir) const;
	/// knownMeleeRange from a tile with the target's known place looked up (consumer "melee").
	bool knownMeleeFrom(Position from, BattleUnit *target) const;
	/// knownMeleeFrom where this unit stands; a target remembered (kind 1) at a place it has left is probed and forgotten there.
	bool knownAdjacent(BattleUnit *target) const;
	/// The unit this side knows to stand on a tile (consumer "blast"), none if it knows nobody there.
	BattleUnit *fairOccupant(Position at) const;
	/// count how many known XCom units are able to see this unit.
	int getSpottingUnits(const Position& pos) const;
	/// Selects the nearest target we can see, and return the number of viable targets.
	/// AI2-H h8: escape - the pick for setupEscape (a target the side remembers is taken at its remembered place).
	int selectNearestTarget(bool escape = false);
	/// AI2-H h8 knowledge contract for the nearest-target selectors: 0 - skip, 1 - the old ray to the true tile, 2 - the ray at the
	/// remembered place (escape only); state, mem, dir - AiProbe::fairState; oldPass - the old ray (diagnostics, -1 not asked).
	int fairNearestMode(BattleUnit *bu, bool escape, const char *cons, int &state, Position &mem, int &dir, int &oldPass) const;
	/// Selects the closest known xcom unit for ambushing.
	bool selectClosestKnownEnemy();
	/// Selects a random known target.
	bool selectRandomTarget();
	/// Selects the nearest reachable point relative to a target.
	bool selectPointNearTarget(BattleUnit *target, int maxTUs);
	/// Selects a target from a list of units seen by spotter units for out-of-LOS actions
	bool selectSpottedUnitForSniper();
	/// Scores a firing mode action based on distance to target and accuracy.
	int scoreFiringMode(BattleAction *action, BattleUnit *target, bool checkLOF);
	/// AI3-E (bench, OXCE_AI_FIRE_MODE_EV): the expected damage of a direct firing mode this turn, -1 (with why) if not modelled.
	double fireModeEffect(BattleAction *action, BattleUnit *target, const char *&why);
	/// re-evaluate our situation, and make a decision from our available options.
	void evaluateAIMode();
	/// The bench's tactical rules (OXCE_AI_TACTICS / OXCE_AI_CAREFUL): attack or take cover, never loiter in view.
	void tacticalMode();
	/// Selects a suitable position from which to attack.
	bool findFirePoint();
	/// Decides if we should throw a grenade/launch a missile to this position.
	int explosiveEfficacy(Position targetPos, BattleUnit *attackingUnit, int radius, int diff, bool grenade = false) const;
	bool getNodeOfBestEfficacy(BattleAction *action, int radius);
	/// Attempts to take a melee attack/charge an enemy we can see.
	void meleeAction();
	/// Attempts to fire a waypoint projectile at an enemy we, or one of our teammates sees.
	void wayPointAction();
	/// Attempts to fire at an enemy spotted for us.
	bool sniperAction();
	/// Attempts to fire at an enemy we can see.
	void projectileAction();
	/// The bench's shot evaluator (OXCE_AI_EVAL): every reachable tile, seen enemy and fire mode by expected damage against risk.
	bool evalFireAction();
	/// Chooses a firing mode for the AI based on expected number of hits per turn
	void extendedFireModeChoice(BattleActionCost& costAuto, BattleActionCost& costSnap, BattleActionCost& costAimed, BattleActionCost& costThrow, bool checkLOF = false);
	/// Attempts to throw a grenade at an enemy (or group of enemies) we can see.
	void grenadeAction();
	/// AI3-FF (bench, OXCE_AI_FF_RISK bit 2): the deferred throw of grenadeAction against the shot projectileAction chose.
	void ffThrowOrShot();
	/// AI3-FF (bench): scoreFiringMode's accuracy * shots * TU ratio, the distance taken to a place (the side's known one).
	int ffFireScore(const BattleAction &action, Position at) const;
	/// AI3-FF (bench, OXCE_AI_FF_RISK bit 8): the power the action hits with, bonuses included, before resistances.
	int ffPower(const BattleAction &action) const;
	/// AI3-FF (bench, OXCE_AI_FF_RISK bit 4): a tile part with explosive the shooter sees near the line of fire to the target
	/// whose blast reaches our own side for no gain by the weights of explosiveEfficacy.
	bool ffLineRisk(Position target) const;
	/// Performs a psionic attack.
	bool psiAction();
	/// Performs a melee attack action.
	void meleeAttack();

	/// How much given unit is worth as target of attack.
	AIAttackWeight getTargetAttackWeight(BattleUnit* target) const;
	/// Checks to make sure a target is valid, given the parameters
	bool validTarget(BattleUnit* target, bool assessDanger, bool includeCivs) const;

	/// Checks the alien's TU reservation setting.
	BattleActionType getReserveMode();
	/// Assuming we have both a ranged and a melee weapon, we have to select one.
	void selectMeleeOrRanged();
	/// Gets the current targetted unit.
	BattleUnit* getTarget();
	/// Gets the current AI mode (AI_PATROL..AI_ESCAPE), for the AI probe's log.
	int getAIMode() const { return _AIMode; }
	/// Is this the walk of a patrol to its node (the probe's slot p, patrol.node)?
	bool isPatrolWalk(const BattleAction &action) const;
	/// No more patrol walks for the rest of this unit-turn: it has no step left by energy (bench, ENERGY_PATROL_END_V2).
	void spendPatrol();
	/// The walk being done stopped at a unit on the step in dir: recorded if findFirePoint chose it (bench,
	/// FIREPOINT_BLOCKED_UNIT_STALL; called by AiProbe::firepointBlocked only).
	void firepointWalkBlocked(const BattleAction &action, int dir);
	/// V1 suppressed the first step in dir of that walk and found no way round (bench, FIREPOINT_BLOCKED_V2_INTEROP; called
	/// by AiProbe::blockedStepPlan only): recorded as a stop on that step.
	void firepointStepSuppressed(const BattleAction &action, int dir);
	/// KNOWN_OCCUPANT_PATH_V1 (bench, BattlescapeGame::handleAI): the decision is made - what the thinks' searches blocked.
	void knownOccupantDecided(const BattleAction &action);
	/// KNOWN_OCCUPANT_PATH_V1: the walk's own path is calculated (found: it has a first step) - what that search blocked.
	void knownOccupantWalked(const BattleAction &action, bool found);
	/// KNOWN_OCCUPANT_PATH_V2 (bench, BattlescapeGame::handleAI): the decision is made - what findFirePoint / setupAmbush blocked.
	void knownOccupantV2Decided(const BattleAction &action);
	/// KNOWN_OCCUPANT_PATH_V2: the T whose tile the walk's own path search must take as blocked - only for the walk to the point
	/// findFirePoint or setupAmbush chose this think; null for any other walk.
	const BattleUnit *knownOccupantV2Walk(const BattleAction &action) const;
	/// KNOWN_OCCUPANT_PATH_V2: the walk's own path is calculated with that T (found: it has a first step; hits: what it blocked).
	void knownOccupantV2Walked(const BattleAction &action, bool found, int hits);
	/// PATROL_REUSE_PROBE (bench): the decision is made - tallies what its last setupPatrol found keeping the stored node.
	void patrolReuseDecided(const BattleAction &action);
	/// Frees up the destination node for another Unit to select
	void freePatrolTarget();
	/// AI2-A DAMAGE FEASIBILITY (bench flag OXCE_AI_ZERO_EFFECT): 0 off, 1 shadow (judge and log only), 2 a direct shot or blow
	/// the real damage pipeline proves useless is not taken, 3 = 2 plus no fire-point search for a target only such shots reach.
	static int zeroEffectMode();
	enum { AIZ_POTENTIAL = 0, AIZ_ZERO = 1, AIZ_UNKNOWN = 2 };
	/// Can this direct attack change the target at all, by BattleUnit::damage as it stands now (no RNG, no state change):
	/// AIZ_ZERO only when the largest damage roll ends with nothing changed on the target; anything not proven is AIZ_UNKNOWN.
	/// terms (when given) gets the proof as JSON fields.
	static int zeroEffectVerdict(SavedBattleGame *save, BattleUnit *attacker, BattleActionType type, BattleItem *weapon, const BattleUnit *target, std::string *terms);
	/// AI2-A HONEST (bench flag OXCE_AI_ZERO_HONEST): 0 off (AI2_BASELINE_B2 verdict), 1 shadow (B2 verdict decides, the honest
	/// one and the hidden values B2 read are logged beside it), 2 the honest verdict decides (nothing hidden is read).
	static int zeroHonestMode();
	/// The verdict of AI2_BASELINE_B2, unchanged: reads the target's current armour, shield HP, resistance tags, health.
	static int zeroEffectVerdictB2(SavedBattleGame *save, BattleUnit *attacker, BattleActionType type, BattleItem *weapon, const BattleUnit *target, std::string *terms);
	/// The honest verdict: ZERO only when proven from the visible target type, the ruleset and the attacker's own weapon.
	/// full: terms get the whole proof (keys as B2), else only the "h..." fields for the shadow line.
	static int zeroEffectVerdictHonest(SavedBattleGame *save, BattleUnit *attacker, BattleActionType type, BattleItem *weapon, const BattleUnit *target, std::string *terms, bool full);
	/// The honest verdict of the last zeroEffectVerdict call in shadow and applied modes (for the fire-point line).
	static int zeroHonestLast;
	/// The hook: judges, logs [AITRACE] ai2a (mode 1 and up), true when mode 2+ rejects this attack.
	bool zeroEffectReject(const char *site, BattleActionType type, BattleItem *weapon, const BattleUnit *target);
	/// AI2-B1 (bench flag OXCE_AI_SNIPER_AOE_EFFICACY): 0 off, 1 shadow (judge and log only), 2 a sniper area attack whose
	/// explosiveEfficacy (same inputs as grenadeAction/projectileAction) is 0 is not offered.
	static int sniperAoeMode();
	/// The hook: logs [AITRACE] ai2b=sniper_aoe for a sniper area attack (mode 1 and up), true when mode 2 rejects it.
	bool sniperAoeEfficacyReject(const BattleAction &chosen, BattleUnit *target);
	/// AI2-B1 diagnostics: [AITRACE] ai2b=<site> with the explosiveEfficacy verdict and its inputs (mode 1 and up), no RNG.
	void aoeEfficacyTrace(const char *site, BattleActionType type, BattleItem *weapon, BattleItem *damageItem, BattleUnit *target,
		Position tpos, int radius, bool grenade, int eff, bool reject);
};

}
