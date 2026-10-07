# Noun-based commendations: one bonus per distinct rung, summed

A proposal for OXCE. Checked against 8.7.0.

## The behaviour

`SoldierDiary::manageCommendations` awards one `SoldierCommendations` object per noun for the
noun-based criteria (`totalMissionsInARegion`, `totalKillsByRace`, `totalKillsWithAWeapon`,
`totalKillsByRank`). Each object carries its own `decorationLevel`.

`Soldier::getBonuses()` (src/Savegame/Soldier.cpp:2124) then applies all of them:

```cpp
for (auto* commendation : *_diary->getSoldierCommendations())
{
    auto* bonusRule = commendation->getRule()->getSoldierBonus(commendation->getDecorationLevelInt());
    addSorted(bonusRule);
}
```

Because `addSorted` deduplicates by pointer, nouns sitting at the same decoration level collapse
into one, while nouns at different levels each contribute. The effective reward is therefore

```
sum over the DISTINCT decoration levels the soldier holds, of soldierBonusTypes[level]
```

which means two things worth stating out loud:

1. the ceiling of a commendation is not its top rung, it is **the sum of its entire ladder**;
2. the reward depends on how *unevenly* the nouns are spread, not on how much the soldier did.
   Ten regions at rung 3 are worth one bonus; three regions at rungs 1, 2, 3 are worth three.

Point 2 is the part I would call a defect rather than a design: no ruleset can express a preference
for uneven spreads, and no mod author would choose one.

## Is this a bug or intended?

Honest answer: I cannot tell from the code, and I did not find a comment stating intent either way.
`soldierBonusTypes` on commendations is an OXCE addition, and the noun case looks like it was simply
not considered -- the loop treats every `SoldierCommendations` object as an independent medal, which
is true for every criterion except the noun-based four.

Two facts argue it was not intended:

* mods write these ladders as *totals* (`RIBBON_5` = "5 mana", not "+5 over rung 4"), which only
  makes sense if one rung applies at a time;
* the same-level deduplication is load-bearing. Remove it and the numbers roughly double. Nothing
  in the ruleset chose that boundary; it falls out of `addSorted` being a set.

Against: a mod could in principle be built on the stacking. That is why the proposal below is
opt-in rather than a straight fix.

## What it produces in practice

X-Piratez, one campaign save, 1816 battles, 277 decorated soldiers, 196 affected. The worst case is
a soldier holding 11 region nouns, 27 race nouns and 56 weapon nouns.

For `STR_MEDAL_WEAPON_PROFICIENCY_NAME` he occupies all ten rungs, so he receives the ladder summed:

```
throwing  1+1+1+2+2+2+3+3+3+4 = 22
melee     0+1+1+1+2+2+2+3+3+4 = 19
firing    0+0+1+1+1+2+2+2+3+4 = 16
                                57 points, where the top rung is worth 12
```

Across the three noun-based commendations he receives 149 stat points where the three top rungs
together are worth 32. Population-wide: mean 10.6, median 6, 90th percentile 22.

I am not asking you to arbitrate X-Piratez balance -- the mod cannot express what it means here,
which is the actual problem.

## Why the mod side cannot fix it

Worth ruling out before asking for engine work. With rung values `v1 <= ... <= v10`, the intended
maximum is `v10` and the achievable maximum is `v1 + ... + v10`. Making those equal requires
`v1..v9` to be approximately zero, i.e. no ladder. A mod can collapse `soldierBonusTypes` to ten
copies of one name and get a bounded flat bonus, or keep the ladder and keep the overshoot. There
is no third option in data.

## Proposal

One optional integer on `RuleCommendations`, defaulting to 0, which means "unchanged":

```yaml
commendations:
  - type: STR_MEDAL_WEAPON_PROFICIENCY_NAME
    bonusNounDivisor: 3
```

When it is positive, all nouns of that commendation contribute to a **single** bonus, picked from
the existing ladder:

```
effective rung = best rung + ( sum over the other nouns of (rung + 1) ) / divisor
```

`RuleCommendations::getSoldierBonus()` already clamps to the last entry, so the ceiling is the top
rung by construction and no mod table needs rebalancing.

### Why one integer rather than an enum

The divisor covers the whole useful range on its own:

* `0` -- current behaviour, bit-for-bit;
* large (say `999`) -- degenerates to "highest noun only", since the extra term floors to zero;
* small -- breadth counts more, bounded by the ladder either way.

So a mod that just wants the obvious fix writes `bonusNounDivisor: 999` and does not need a second
field or an enum to learn. `+1` inside the sum is there so that rung 0 -- a real achievement, the
first threshold -- is not worth nothing.

The field is harmless on non-noun commendations: they hold a single `noNoun` entry, the sum over
"the others" is empty, and the result is the rung they already had.

## Patch

**src/Mod/RuleCommendations.h** -- member and getter:

```cpp
	int _bonusNounDivisor;
...
	/// Combine all nouns of this commendation into one bonus? 0 = no, apply each separately.
	int getBonusNounDivisor() const { return _bonusNounDivisor; }
```

**src/Mod/RuleCommendations.cpp** -- `_bonusNounDivisor(0)` in the constructor initialiser list and,
in `load()`:

```cpp
	reader.tryRead("bonusNounDivisor", _bonusNounDivisor);
```

**src/Savegame/Soldier.cpp:2124** -- replace the commendation loop. Single pass, no allocation
beyond one small vector whose size is the number of opted-in commendation types (in practice 0-4,
so a linear scan beats a map):

```cpp
		// Noun-based commendations (region / race / weapon / rank) are held once per
		// noun. By default each one applies its own bonus, which sums the ladder; a
		// commendation may instead ask for all its nouns to pick a single rung.
		struct NounGroup { const RuleCommendations* rule; int best; int others; };
		std::vector<NounGroup> groups;

		for (auto* commendation : *_diary->getSoldierCommendations())
		{
			const auto* rule = commendation->getRule();
			const int level = commendation->getDecorationLevelInt();
			if (!rule || rule->getBonusNounDivisor() <= 0)
			{
				addSorted(rule ? rule->getSoldierBonus(level) : nullptr);
				continue;
			}
			auto g = std::find_if(groups.begin(), groups.end(),
				[&](const NounGroup& n) { return n.rule == rule; });
			if (g == groups.end())
			{
				groups.push_back(NounGroup{ rule, level, 0 });
			}
			else if (g->best < level)
			{
				g->others += g->best + 1; // the previous best joins the others
				g->best = level;
			}
			else
			{
				g->others += level + 1;
			}
		}

		for (const auto& g : groups)
		{
			addSorted(g.rule->getSoldierBonus(g.best + g.others / g.rule->getBonusNounDivisor()));
		}
```

## Compatibility

* **No existing mod changes.** Default 0 takes the original branch, including the `addSorted`
  deduplication, so output is identical unless a mod opts in.
* **No save format change.** Soldier bonuses are recomputed in `getBonuses()`, never serialised;
  `SoldierCommendations` is untouched.
* **No UI change.** The medal list still shows one decoration per noun with its own level; only the
  stat bonus is combined.
* **No new failure mode.** `getSoldierBonus()` clamps the index, and an empty `soldierBonusTypes`
  still returns `nullptr`, which `addSorted` ignores.
* **Cost.** `getBonuses(mod)` already walks every commendation; the addition is one stack vector and
  a linear scan over at most a handful of entries, on a path that runs on stat recalculation, not
  per frame.

## Alternatives I considered and did not propose

* **Fix it unconditionally.** Cleanest code, but it silently changes numbers in every mod that has
  a noun-based commendation with a bonus, including running campaigns. Not worth it for a behaviour
  that has been shipping for years.
* **A boolean "highest noun only".** Smaller, but it makes a single weapon strictly optimal: five
  weapons at 50 kills each score rung 4, one weapon at 200 kills scores rung 9. The divisor covers
  this case anyway as its degenerate end.
* **A global option in `Options.inc.h`.** Wrong layer -- whether breadth should pay is a mod's
  decision, not a player's.

## Open questions for you

1. Field name. `bonusNounDivisor` is descriptive but clumsy; I have no attachment to it.
2. Should the combined rung be exposed to the script API, or is the resulting bonus set enough?
3. Retroactivity is worth one line in the docs: enabling the field is reversible and breaks no save,
   but veterans of a running campaign lose stats immediately. On the save above: median 1 point,
   mean 4.1, maximum 117, with 73 of 196 unaffected.

Happy to send the measurement script and the save, or to redo the numbers on another mod if you
want a second data point.
