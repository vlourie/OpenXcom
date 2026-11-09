# -*- coding: utf-8 -*-
"""Read-only scan of X-Piratez rulesets: AI-relevant unit fields and items' AI fields. Plain text scan, no YAML loader needed.
Usage: py -3 piratez_rules.py <ruleset_dir> <out.txt>
"""
import collections
import glob
import os
import re
import statistics
import sys


def blocks(text, section):
    m = re.search(r'^%s:\s*$' % section, text, re.M)
    if not m:
        return []
    rest = text[m.end():]
    n = re.search(r'^[A-Za-z]\w*:[ \t]*(#.*)?\r?$', rest, re.M)
    if n:
        rest = rest[:n.start()]
    parts = re.split(r'^(?=  - (?:type|delete|name):)', rest, flags=re.M)
    return [p for p in parts if p.strip().startswith('- ')]


def fld(b, name):
    m = re.search(r'^[\s-]+%s:\s*(\S+)' % name, b, re.M)
    return m.group(1) if m else None


def main():
    d, out = sys.argv[1:3]
    units = {}
    items = {}
    globs = []
    for fn in glob.glob(os.path.join(d, '**', '*.rul'), recursive=True):
        t = open(fn, encoding='utf-8', errors='replace').read()
        for b in blocks(t, 'units'):
            ty = fld(b, 'type')
            if ty:
                units.setdefault(ty, {}).update({k: v for k, v in dict(aggression=fld(b, 'aggression'), intelligence=fld(b, 'intelligence'), reactions=fld(b, 'reactions'), tu=fld(b, 'tu'), health=fld(b, 'health'), psi=fld(b, 'psiStrength'), sniper=fld(b, 'sniperPercentage'), spotter=fld(b, 'spotter'), sniperrole=fld(b, 'sniper'), melee=fld(b, 'melee'), leeroy=fld(b, 'isLeeroyJenkins'), armor=fld(b, 'armor'), pickup=fld(b, 'pickUpWeaponsMoreActively')).items() if v is not None})
        for b in blocks(t, 'items'):
            ty = fld(b, 'type')
            if ty:
                items.setdefault(ty, {}).update({k: v for k, v in dict(delay=fld(b, 'useDelay'), bt=fld(b, 'battleType'), target=fld(b, 'aiTargetMode'), melee=fld(b, 'aiMeleeHitCount')).items() if v is not None})
        for line in t.split('\n'):
            if re.match(r'^(ai|turnAIUseGrenade|turnAIUseBlaster|aiUseDelay\w*|aiTargetMode|maxRange|chanceToStopRetaliation|lessAliensDuringBaseDefense|noLOSAccuracyPenaltyGlobal|ai\w*|AI\w*|cheatTurn|\w*[Cc]heat\w*|surrenderMode|bughuntM\w+|\w*Reaction\w*|\w*reaction\w*)\s*:', line):
                globs.append(os.path.basename(fn) + ': ' + line.strip())
    f = open(out, 'w', encoding='utf-8-sig')
    P = lambda *a: print(*a, file=f)
    P('units', len(units), 'items', len(items))
    for fname in ('aggression', 'intelligence', 'leeroy', 'sniper', 'spotter', 'sniperrole', 'pickup'):
        P(fname, sorted(collections.Counter(u.get(fname) for u in units.values()).items(), key=lambda kv: -kv[1])[:16])
    P('item aiUseDelay', sorted(collections.Counter(i.get('delay') for i in items.values() if i.get('delay') is not None).items(), key=lambda kv: -kv[1]))
    P('items by battleType', sorted(collections.Counter(i.get('bt') for i in items.values()).items(), key=lambda kv: -kv[1]))
    for fname in ('reactions', 'tu', 'health', 'psi'):
        v = sorted(int(u[fname]) for u in units.values() if u.get(fname, '').lstrip('-').isdigit())
        if v:
            P(fname, 'n', len(v), 'median', v[len(v) // 2], 'p10', v[len(v) // 10], 'p90', v[len(v) * 9 // 10])
    P('\nGlobals'); [P(x) for x in globs[:60]]
    f.close()


if __name__ == '__main__':
    main()
