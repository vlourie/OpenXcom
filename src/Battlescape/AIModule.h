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

enum AIMode { AI_PATROL, AI_AMBUSH, AI_COMBAT, AI_ESCAPE };
enum AIAttackWeight : int
{
	/// Base scale of attack weights
	AIW_SCALE = 100,
	AIW_IGNORED = 0,
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
	/// The shot chosen by evalFireAction (OXCE_AI_EVAL): kneel for it, and whether it chose one this think.
	bool _evalKneel = false, _evalChosen = false;
	/// The bench's decision record (AiProbe::propose, docs/AI_DECISION_RECORD.md): the score the rule that ran last gave its
	/// action and, if it names itself more exactly than its caller, its name. Written, never read by play.
	int _probeScore = INT_MIN;
	const char *_probeSource = nullptr;
	/// ENERGY_PATROL_END_V2 (bench, AiProbe::patrolOutOfEnergy): the unit-turn (turn and side) its patrol walks are spent in.
	int _patrolSpent = -1;
	/// Where it stood and how much energy it had then: a unit moved or given energy (a stimulant) may walk again.
	Position _patrolSpentAt;
	int _patrolSpentEnergy = -1;
	/// This think's action is the patrol's walk to its node.
	bool _patrolWalk = false;
	/// The think after a spent patrol dropped: 1 asked for it (BA_RETHINK), 2 this think is it (no second ask).
	int _patrolRetry = 0;
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
	std::string _prClass, _prRoute, _prTrail;
	Position _prNode;
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
	void meleeActionLeeroy(bool canRun);
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
	/// count how many known XCom units are able to see this unit.
	int getSpottingUnits(const Position& pos) const;
	/// Selects the nearest target we can see, and return the number of viable targets.
	int selectNearestTarget();
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
};

}
