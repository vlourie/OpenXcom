# Noun-based commendations multiply their soldier bonuses

A note for Dioxine. X-Piratez on OXCE 8.7.0.

## Short version

Commendations awarded per noun -- `totalMissionsInARegion`, `totalKillsByRace`,
`totalKillsWithAWeapon` -- do not grant one bonus. They grant one bonus **per distinct decoration
level the soldier holds across all nouns**, and those bonuses add up.

Three of your commendations use this, and all three have ten-rung ladders authored as totals
(`RIBBON_5` means "5 mana", not "+5 on top of rung 4"). So the ceiling is not the top rung. The
ceiling is the sum of the whole ladder.

This is engine behaviour, not a mistake in your rulesets. But it is worth knowing, because the
numbers it produces are not the numbers your tables describe.

## How the engine behaves

`SoldierDiary::manageCommendations` creates one `SoldierCommendations` object per noun -- one per
region, per race, per weapon. Each carries its own `decorationLevel`.

`Soldier::getBonuses()` then walks all of them:

```cpp
for (auto* commendation : *_diary->getSoldierCommendations())
{
    auto* bonusRule = commendation->getRule()->getSoldierBonus(commendation->getDecorationLevelInt());
    addSorted(bonusRule);
}
```

`addSorted` keeps a set of pointers, so:

* nouns at the **same** decoration level return the same `RuleSoldierBonus*` and collapse into one;
* nouns at **different** decoration levels return different pointers and every one of them applies.

A soldier's reward therefore depends on how many *distinct rungs* his nouns occupy -- not on how
much he actually did. Same-level nouns are free; unevenly-spread nouns multiply.

## What it looks like in a real campaign

Save: 1816 battles, 277 soldiers holding commendations. 196 of them are affected.

The worst case, verified soldier by soldier:

| commendation | nouns | distinct rungs | best rung |
|---|---|---|---|
| `STR_MEDAL_CAMPAIGN_RIBBON_NAME` | 11 | 6 | 9 |
| `STR_MEDAL_RACE_KILLS_NAME` | 27 | 9 | 9 |
| `STR_MEDAL_WEAPON_PROFICIENCY_NAME` | 56 | 10 | 9 |

He receives `mana 59, throwing 22, melee 19, tu 18, firing 16, psiStrength 15` -- **149 stat
points**, where the three top rungs together are worth 32.

Weapon proficiency alone is the cleanest illustration. He holds all ten rungs, so he receives the
entire ladder summed:

```
throwing  1+1+1+2+2+2+3+3+3+4 = 22
melee     0+1+1+1+2+2+2+3+3+4 = 19
firing    0+0+1+1+1+2+2+2+3+4 = 16
                                57 points, where WEAPON_PROFICIENCY_10 is worth 12
```

Population-wide it is milder but not small: mean 10.6 points, median 6, 90th percentile 22.
The medal that reads as "up to +4/+4/+4" is in practice worth up to +22/+19/+16.

## Why this cannot be fixed cleanly in the ruleset

Worth stating plainly, because it is the reason I am writing rather than sending a patch.

With rung values `v1 <= v2 <= ... <= v10`, a soldier's reward is the sum of the values of the rungs
he occupies. The intended maximum is `v10`. The actual maximum is `v1 + ... + v10`. To make those
two equal you need `v1..v9` to be approximately zero -- that is, no progression at all.

So any ruleset-only fix has to give up either the ceiling or the ladder. There is no third option
in data alone.

## What you can do today

Three levers exist, all lossy. Measured on the same save.

**1. Collapse the ladder to one entry.** Repeat a single bonus name ten times:

```yaml
soldierBonusTypes: [STR_MEDAL_WEAPON_PROFICIENCY_X, ... x10]
```

Every noun then returns the same pointer, deduplication does the rest, and the soldier gets exactly
one bonus no matter how many nouns or rungs. Bounded and predictable. Cost: the ten award levels
stop meaning anything mechanically -- they remain prestige only.

**2. Group the ladder.** Repeat names in blocks, e.g. `[A,A,A,B,B,B,C,C,C,D]`. The worst case then
becomes the sum of the *four* group values rather than ten rungs. Partial progression, partial
bound; you pick the trade by choosing the block size. Cost: you must re-scale the values, because
the cap is now the sum of the groups, not the top group.

**3. Move the stat reward off the noun-based medals entirely.** You already have the correct
template: `STR_MEDAL_CARREER_KILLS_NAME` uses `killsWithCriteriaCareer`, has no noun, and its
ten-rung ladder behaves exactly as written. Leaving `CAMPAIGN_RIBBON`, `RACE_KILLS` and
`WEAPON_PROFICIENCY` as decorations without `soldierBonusTypes`, and folding their intended reward
into non-modular medals, is the only option that keeps a real ladder *and* a real ceiling.

My own preference of the three would be 3, with 1 as the cheap stopgap -- but that is a balance
call, not a technical one, so it is yours.

## What would fix it properly

This wants an engine feature, and Meridian is the one who would have to add it. If you agree the
behaviour is wrong, seconding it would carry more weight than my asking alone.

The proposal: an optional field on a commendation, defaulting to off so no existing mod changes,
that makes noun-based commendations grant **one** bonus chosen from the combined standing of all
nouns rather than one bonus per rung:

```
effective rung = best rung + ( sum over the other nouns of (rung + 1) ) / D
```

clamped to the end of the ladder, with `D` set in the ruleset. `getSoldierBonus()` already clamps,
so the ceiling is the top rung by construction, no table needs rebalancing, and breadth still pays
with diminishing returns. On the save above this caps the worst case at 32 points instead of 149
while leaving the median untouched at any `D`.

One caveat worth stating in a changelog if it ever ships: soldier bonuses are recomputed from the
diary rather than stored, so the change is reversible and breaks no save -- but it applies
retroactively, and veterans of a running campaign lose stats they already had (median 1 point,
mean 4.1, up to 117 in the worst case; 73 of the 196 lose nothing). It belongs in a new campaign,
not in the middle of someone's old one.

## Where the numbers come from

All figures were read out of a single X-Piratez campaign save and the mod's own rulesets:
`Piratez_Globals.rul` for the commendation definitions, `Piratez_Bonuses.rul` for the ladders,
and the soldiers' `commendations:` blocks for the levels actually held. Engine behaviour was read
from OXCE 8.7.0 sources -- `SoldierDiary.cpp`, `Soldier.cpp`, `RuleCommendations.cpp` -- not from
observation. Happy to share the script or the save.
