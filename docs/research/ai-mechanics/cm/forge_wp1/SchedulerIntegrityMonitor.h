#pragma once
/*
 * AI FORGE WP1 (bench, never in play): watches the life of the engine's AI activations and fingerprints the real state.
 * OXCE_AI_FORGE unset: every hook returns at once. OXCE_AI_FORGE=1: read only - it decides nothing, moves nothing,
 * draws no random number; it writes [FORGE] lines (numbered, chained) and [FORGEDUMP] lines (detail, outside the chain).
 * OXCE_AI_FORGE_DUMP=n,n,..: the full dump at these events. OXCE_AI_FORGE_STOP=n: the fingerprint and dump at event n, the run ends.
 */

namespace OpenXcom
{

class BattleUnit;
class SavedBattleGame;
struct BattleAction;

namespace SchedulerIntegrityMonitor
{

/// Is the monitor on in this process?
bool on();
/// A frame of the battle: attaches to the battle, notices a change of side or of the selected unit.
void frame(SavedBattleGame *save);
/// The run has reached OXCE_AI_FORGE_STOP.
bool stopRequested();
/// The mark that keeps a unit from being selected again this turn is set or cleared; by whom.
void mark(const BattleUnit *unit, bool set, const char *by, int line);
/// The unit's hiding flag changes; by whom.
void hide(const BattleUnit *unit, bool hiding, const char *by, int line);
/// The unit's time units change through an action or an effect.
void tu(const BattleUnit *unit, int before, int after, const char *kind);
/// handleAI is entered for the unit: the state left by what came before.
void tick(SavedBattleGame *save, BattleUnit *unit, int counter, bool second);
/// handleAI lets the selection go instead of deciding.
void gate(BattleUnit *unit, int counter, int maxActions);
/// The bench bot's end-of-activation turn towards a threat.
void guard(BattleUnit *unit);
/// The boundary of a decision, just before think().
void decide(SavedBattleGame *save, BattleUnit *unit, int counter, bool second);
/// What think() and the steps after it decided, before it is carried out.
void act(SavedBattleGame *save, BattleUnit *unit, const BattleAction &action);
/// The end of a walk: what the engine is about to do with the decision.
void walkEnd(BattleUnit *unit, const BattleAction &action, bool aiBranch);
/// A reaction shot was granted.
void reaction(BattleUnit *reactor, BattleUnit *target);
/// A panicking or berserk unit acts outside handleAI.
void panic(BattleUnit *unit);
/// convertUnit made a new unit out of a unit.
void converted(BattleUnit *from, BattleUnit *to);
/// A unit is out.
void casualty(const BattleUnit *victim, bool dead);
/// The run ends.
void finish(SavedBattleGame *save, const char *how);

}

}
