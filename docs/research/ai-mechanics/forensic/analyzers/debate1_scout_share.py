# -*- coding: utf-8 -*-
# Read-only: (1) keys of the causal rows, candidate squads for question 4; (2) scout share estimated from the AI blocks of real saves.
import collections, glob, json, os, re
D = r'E:\OpenXCom\docs\research\ai-mechanics\forensic\data'
J = json.load(open(os.path.join(D, 'debate1_causal_d0p.json'), encoding='utf-8-sig'))
print('top keys', list(J)[:12] if isinstance(J, dict) else type(J))
res = J['res'] if isinstance(J, dict) and 'res' in J else J
print('res keys', list(res[0])[:30])
rows = res[0].get('rows') or []
print('row sample', rows[:1])
cand = collections.defaultdict(list)
for r in res:
    for x in r.get('rows') or []:
        if x.get('wc') or x.get('wclass') or True:
            cand[(r['battle'], x.get('turn') or x.get('t'))].append(x)
scored = []
for k, xs in cand.items():
    kinds = {x.get('w') for x in xs}
    if len(xs) >= 3 and len(kinds) >= 3 and (k[1] or 0) <= 4:
        scored.append((len(kinds), len(xs), k))
print('groups', len(scored), sorted(scored, key=lambda s: (-s[0], -s[1]))[:12])

# scout: AIModule.cpp:2029 - not base defense, not cheating, _fromNode exists with rank > 0, not in fire => scout=false
def scan(path):
    text = open(path, encoding='utf-8', errors='replace').read()
    i = text.find('\nbattleGame:')
    if i < 0:
        return None
    b = text[i:]
    mt = re.search(r'^  missionType: (.*)$', b, re.M)
    n0 = b.find('\n  nodes:')
    u0 = b.find('\n  units:')
    it = b.find('\n  items:', u0)
    if n0 < 0 or u0 < 0:
        return None
    nodes = {}
    for m in re.finditer(r'\{id: (-?\d+),position: \[[^\]]*\],type: \d+,rank: (\d+),', b[n0:u0]):
        nodes[int(m.group(1))] = int(m.group(2))
    c = collections.Counter()
    for x in re.split(r'^    - ', b[u0:it], flags=re.M)[1:]:
        f = re.search(r'^\s+faction: (\d+)', x, re.M)
        s = re.search(r'^\s+status: (\d+)', x, re.M)
        if not f or f.group(1) != '1' or (s and s.group(1) in ('6', '7', '8')):
            continue
        fn = re.search(r'fromNode: (-?\d+)', x)
        c['hostile'] += 1
        if not fn:
            c['no_ai_block'] += 1
            continue
        v = int(fn.group(1))
        if v < 0:
            c['from_none_scout'] += 1
        elif nodes.get(v, 0) == 0:
            c['rank0_scout'] += 1
        else:
            c['ranked_guard'] += 1
    t = re.search(r'^  turn: (\d+)', b, re.M)
    return mt.group(1) if mt else '?', int(t.group(1)) if t else -1, c


tot = collections.Counter()
seen = set()
paths = [r'E:\OpenXCom\Пиратки\Dioxine_XPiratez\user\piratez\стрим.sav'] + [f for f in glob.glob(r'E:\OpenXCom\census\tickets\**\*', recursive=True) if os.path.isfile(f) and f.lower().endswith(('.sav', '.asav')) and '_ident' not in f]
for p in paths:
    r = scan(p)
    if not r:
        continue
    key = (r[0], r[1], tuple(sorted(r[2].items())))
    if key in seen:
        continue
    seen.add(key)
    base = 'BASE_DEFENSE' in r[0]
    tag = 'base' if base else ('other_t1-3' if r[1] <= 3 else 'other_t4+')
    tot[tag + '_saves'] += 1
    for k, v in r[2].items():
        tot[tag + '_' + k] += v
print('scout estimate', dict(tot))
