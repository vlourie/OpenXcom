#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Аудит статов бойцов в сейве X-Piratez.

Отвечает на вопрос «почему у бойца отняли параметры»:
  1. чьи базовые статы ниже стартовых и какая трансформация их съела;
  2. какие награды навешивают отрицательные бонусы;
  3. какая награда только что поднялась в уровне (счётчик стоит ровно на пороге)
     и на сколько из-за этого просели статы.

Использование:
    python soldier_stat_audit.py <сейв.sav> <папка Ruleset> [--soldier ЧАСТЬ_ИМЕНИ]
"""
import argparse
import sys
from collections import defaultdict

try:
    import yaml
    from yaml import CSafeLoader as Loader
except ImportError:
    print("Нужен PyYAML:  py -3 -m pip install pyyaml")
    sys.exit(1)

STATS = ["tu", "stamina", "health", "bravery", "reactions", "firing",
         "throwing", "melee", "strength", "psiStrength", "psiSkill", "mana"]

# счётчик в дневнике -> имя критерия в правилах награды
COUNTER = {
    "totalHit5Times": "hitCounter5in1Mission",
    "totalShotAt10Times": "shotAtCounter10in1Mission",
    "totalTimesWounded": "timesWoundedTotal",
    "totalDaysWounded": "daysWoundedTotal",
    "totalMonthlyService": "monthsService",
    "totalWoundsHealed": "woundsHealedTotal",
    "totalFellUnconcious": "unconciousTotal",
    "totalShotByFriendly": "totalShotByFriendlyCounter",
    "totalShotFriendly": "totalShotFriendlyCounter",
    "totalRevives": "revivedUnitTotal",
    "totalUFOs": "ufosShotDownTotal",
}


def load_yaml(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        return yaml.load(fh, Loader=Loader)


def load_rules(ruleset_dir):
    import glob
    import os
    bonuses, commendations, transforms = {}, {}, {}
    for path in sorted(glob.glob(os.path.join(ruleset_dir, "*.rul"))):
        try:
            data = load_yaml(path)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        for b in data.get("soldierBonuses") or []:
            bonuses[b["name"]] = b.get("stats") or {}
        for c in data.get("commendations") or []:
            commendations[c["type"]] = c
        for t in data.get("soldierTransformation") or []:
            transforms[t["name"]] = t
    return bonuses, commendations, transforms


def load_soldiers(save_path):
    with open(save_path, encoding="utf-8", errors="replace") as fh:
        docs = list(yaml.load_all(fh, Loader=Loader))
    game = docs[1] if len(docs) > 1 else docs[0]
    out = []
    for base in game.get("bases") or []:
        for s in base.get("soldiers") or []:
            s["_base"] = base.get("name")
            out.append(s)
    return out


def negative_transformations(transforms):
    keys = ["flatOverallStatChange", "percentOverallStatChange",
            "percentGainedStatChange", "flatGainedStatChange"]
    bad = {}
    for name, t in transforms.items():
        found = {}
        for k in keys:
            d = t.get(k) or {}
            neg = {a: b for a, b in d.items()
                   if isinstance(b, (int, float)) and b < 0}
            if neg:
                found[k] = neg
        if found:
            bad[name] = found
    return bad


def report_base_loss(soldiers, bad_transforms):
    print("=" * 70)
    print("1. БОЙЦЫ, У КОТОРЫХ БАЗОВЫЕ СТАТЫ НИЖЕ СТАРТОВЫХ")
    print("=" * 70)
    hit = 0
    for s in soldiers:
        i, c = s.get("initialStats") or {}, s.get("currentStats") or {}
        drop = {k: (i.get(k, 0), c.get(k, 0)) for k in STATS
                if c.get(k, 0) < i.get(k, 0)}
        if not drop:
            continue
        hit += 1
        print(f"\n{s['name']}  ({s['_base']}, {s.get('type')}, миссий {s.get('missions', 0)})")
        for k, (a, b) in drop.items():
            print(f"    {k}: {a} -> {b}  ({b - a})")
        guilty = [t for t in (s.get("previousTransformations") or {})
                  if t in bad_transforms]
        for t in guilty:
            print(f"    подозреваемая трансформация: {t}")
            for k, v in bad_transforms[t].items():
                print(f"        {k}: {v}")
    if not hit:
        print("\nтаких нет")


def report_medals(soldiers, bonuses, commendations, name_filter):
    print()
    print("=" * 70)
    print("2. НАГРАДЫ СО ШТРАФОМ И ТЕ, ЧТО ТОЛЬКО ЧТО ПОДНЯЛИСЬ")
    print("=" * 70)
    for s in soldiers:
        if name_filter and name_filter.lower() not in s["name"].lower():
            continue
        diary = s.get("diary") or {}
        rows, fresh = [], []
        total = defaultdict(int)
        for c in diary.get("commendations") or []:
            rule = commendations.get(c["commendationName"])
            if not rule:
                continue
            types = rule.get("soldierBonusTypes") or []
            if not types:
                continue
            lvl = c.get("decorationLevel", 0)
            cur = bonuses.get(types[min(lvl, len(types) - 1)]) or {}
            for k, v in cur.items():
                if k in STATS:
                    total[k] += v
            if 0 < lvl <= len(types) - 1:
                prev = bonuses.get(types[lvl - 1]) or {}
                worse = {k: (prev.get(k, 0), cur.get(k, 0)) for k in STATS
                         if cur.get(k, 0) < prev.get(k, 0)}
                if worse:
                    rows.append((c["commendationName"], lvl, worse))
            # награда «свежая», если счётчик стоит ровно на пороге уровня
            crit = rule.get("criteria") or {}
            for cname, thresholds in crit.items():
                field = COUNTER.get(cname)
                if not field or field not in diary:
                    continue
                if lvl < len(thresholds) and diary[field] == thresholds[lvl]:
                    fresh.append((c["commendationName"], lvl, cname, diary[field]))
        neg = {k: v for k, v in sorted(total.items()) if v < 0}
        if not rows and not neg and not fresh:
            continue
        print(f"\n--- {s['name']} ({s['_base']}) ---")
        if neg:
            print(f"  итоговый штраф от всех наград: {neg}")
        for name, lvl, crit_name, val in fresh:
            print(f"  ВОЗМОЖНО ВЫДАНА ТОЛЬКО ЧТО: {name} ур.{lvl} "
                  f"({crit_name} = {val}, ровно порог)")
        for name, lvl, worse in rows:
            txt = ", ".join(f"{k} {a}->{b} ({b - a})" for k, (a, b) in worse.items())
            print(f"  {name} ур.{lvl}: {txt}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("save")
    ap.add_argument("ruleset")
    ap.add_argument("--soldier", default=None, help="фильтр по части имени")
    args = ap.parse_args()

    bonuses, commendations, transforms = load_rules(args.ruleset)
    soldiers = load_soldiers(args.save)
    print(f"бойцов: {len(soldiers)}, бонусов: {len(bonuses)}, "
          f"наград: {len(commendations)}, трансформаций: {len(transforms)}\n")

    report_base_loss(soldiers, negative_transformations(transforms))
    report_medals(soldiers, bonuses, commendations, args.soldier)
    return 0


if __name__ == "__main__":
    sys.exit(main())
