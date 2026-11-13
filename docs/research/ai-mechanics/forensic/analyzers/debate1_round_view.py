# -*- coding: utf-8 -*-
# Read-only: list hostile squads of a round for the question 4 example: units close together, what they held, what they did.
import gzip, json, math, re, sys, zipfile
Z = zipfile.ZipFile(r'E:\OXCE_AIWorker\battles_archive\commander_2026-10-29\res_d0p.zip')
battle, want = sys.argv[1], int(sys.argv[2])
text = gzip.decompress(Z.read('out/%s/openxcom.log.gz' % battle)).decode('utf-8', 'replace')
RE = re.compile(r'\[AISTATE\] (\w+) turn=(\d+) unit=(\d+) type=(\S+) faction=(\d+) status=(\d+) pos=\((\d+),(\d+),(\d+)\) dir=(\d+) tu=(-?\d+) hp=(-?\d+)/(\d+) stun=(\d+) morale=(\d+) kneel=(\d) weapon=(\S+) spotted=(-?\d+) sniped=(-?\d+) sees=(\S+) seenby=(\d+)')
H = {}
P = {}
seen = set()
acts = {}
for line in text.split('\n'):
    if '[AISTATE]' in line:
        m = RE.search(line)
        if m and m.group(1) == 'aistart' and int(m.group(2)) == want:
            g = m.groups()
            d = dict(pos=(int(g[6]), int(g[7]), int(g[8])), tu=int(g[10]), w=g[16], t=g[3], spotted=int(g[17]), seenby=int(g[20]), sees=g[19])
            (H if g[4] == '1' else P)[int(g[2])] = d
    elif '[AIREC]' in line:
        try:
            j = json.loads(line[line.index('{'):])
        except Exception:
            continue
        if j.get('turn') == want and j.get('side') == 1 and j['rec'] not in seen:
            seen.add(j['rec'])
            b = j.get('base') or {}
            acts.setdefault(j['unit'], []).append(dict(rec=j['rec'], src=b.get('src'), t=b.get('t'), to=b.get('target') or b.get('to')))
    elif '[AIEXEC]' in line:
        try:
            j = json.loads(line[line.index('{'):])
        except Exception:
            continue
        for u, L in acts.items():
            for a in L:
                if a['rec'] == j.get('rec'):
                    a['dmg'] = j.get('dmg', 0)
                    a['end'] = j.get('pos')
                    a['spent'] = j.get('spent')
print('players', len(P), 'hostiles', len(H))
known = [v['pos'] for v in P.values() if v['spotted'] == 0 or v['seenby'] > 0]
print('known cells', len(known))
for u, h in sorted(H.items()):
    dn = min((math.hypot(h['pos'][0] - c[0], h['pos'][1] - c[1]) for c in known), default=-1)
    L = acts.get(u, [])
    print(u, h['t'][:22], h['pos'], 'tu', h['tu'], h['w'][:24], 'nearest %.0f' % dn, 'seenby', h['seenby'], [(a['src'], a['t'], a.get('dmg'), a.get('end')) for a in L][:4])
