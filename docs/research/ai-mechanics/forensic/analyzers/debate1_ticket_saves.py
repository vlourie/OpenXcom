# -*- coding: utf-8 -*-
import collections, glob, os, re, sys, zipfile
T = open(r'E:\OpenXCom\Пиратки\Dioxine_XPiratez\user\piratez\стрим.sav', encoding='utf-8', errors='replace').read()
i = T.find('\nbattleGame:')
b = T[i:]
u = b.find('\n  units:')
it = b.find('\n  items:', u)
print('units block', u, it, it - u)

def units(text):
    i = text.find('\nbattleGame:')
    b = text[i:]
    u = b.find('\n  units:')
    it = b.find('\n  items:', u)
    out = []
    for x in re.split(r'^    - ', b[u:it], flags=re.M)[1:]:
        g = lambda k: (re.search(r'^\s+%s: (-?\d+)' % k, x, re.M) or [None, None])[1]
        base = re.search(r'currStats:\s*\n\s+tu: (\d+)', x)
        out.append(dict(f=g('faction'), s=g('status'), tu=g('tu'), base=base.group(1) if base else None, tss=g('turnsSinceSpottedByXcom'), tsh=g('turnsSinceSpotted')))
    return out

def summary(text):
    us = units(text)
    P = [x for x in us if x['f'] == '0' and x['s'] not in ('6', '7', '8')]
    H = [x for x in us if x['f'] == '1' and x['s'] not in ('6', '7', '8')]
    sh = [int(x['tu']) / int(x['base']) for x in P if x['tu'] and x['base'] and int(x['base']) > 0]
    return dict(players=len(P), hostile=len(H), tu_share=round(sum(sh) / len(sh), 2) if sh else None, full=sum(1 for s in sh if s >= 0.99), n=len(sh))

print('стрим', summary(T))
seen = {}
rows = []
for f in glob.glob(r'E:\OpenXCom\census\tickets\**\*', recursive=True):
    if not os.path.isfile(f) or not f.lower().endswith(('.sav', '.asav')) or '_ident' in f:
        continue
    text = open(f, encoding='utf-8', errors='replace').read()
    i = text.find('\nbattleGame:')
    if i < 0:
        continue
    b = text[i:i + 300000]
    turn = re.search(r'^  turn: (\d+)', b, re.M)
    mt = re.search(r'^  missionType: (.*)$', b, re.M)
    sel = re.search(r'^  selectedUnit: (-?\d+)', b, re.M)
    tm = re.search(r'time: \{second: (\d+),minute: (\d+),hour: (\d+),weekday: \d+,day: (\d+),month: (\d+),year: (\d+)\}', text[:3000])
    key = (turn.group(1), mt.group(1), sel.group(1), tm.groups() if tm else None)
    s = summary(text)
    iron = 'ironman: true' in text[:3000]
    kind = 'auto' if 'autobattle' in f else 'snapshot' if 'snapshot' in f else 'other'
    if key in seen:
        continue
    seen[key] = f
    rows.append((int(turn.group(1)), kind, iron, mt.group(1), s, tm.group(6) + '-' + tm.group(5) if tm else '?', os.path.relpath(f, r'E:\OpenXCom\census\tickets')))
print('distinct', len(rows))
print('by kind', collections.Counter(r[1] for r in rows))
print('turn>=2', sum(1 for r in rows if r[0] >= 2), 'by kind', collections.Counter(r[1] for r in rows if r[0] >= 2))
print('years', collections.Counter(r[5][:4] for r in rows).most_common())
for r in sorted(rows, key=lambda r: (r[1], r[0])):
    print(r[0], r[1], r[2], r[3][:30], r[4], r[5], r[6][:36])
