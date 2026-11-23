# -*- coding: utf-8 -*-
"""Read-only: print one unit's decisions in one turn with the state of the player's units at the start of the hostile phase.

Usage: py -3 case_view.py <zip> <battle> <turn> <unit>[,<unit>...]
"""
import gzip
import json
import re
import sys
import zipfile

RE_STATE = re.compile(r'\[AISTATE\] (\w+) turn=(\d+) unit=(\d+) type=(\S+) faction=(\d+) status=(\d+) pos=\((\d+),(\d+),(\d+)\) dir=(\d+) tu=(-?\d+) hp=(-?\d+)/(\d+) stun=(\d+) morale=(\d+) kneel=(\d) weapon=(\S+) spotted=(-?\d+) sniped=(-?\d+) sees=(\S+) seenby=(\d+) known=(\d+) near=(-?\d+)')
RE_DEC = re.compile(r'\[AIDECIDE\] turn=(\d+) side=(\d+) unit=(\d+) n=(-?\d+) .*? seen=(\S*)')


def main():
    zpath, battle, turn = sys.argv[1:4]
    turn = int(turn)
    want = set(int(x) for x in sys.argv[4].split(','))
    z = zipfile.ZipFile(zpath)
    member = next(n for n in z.namelist() if ('/' + battle + '/') in n and n.endswith('openxcom.log.gz'))
    text = gzip.decompress(z.read(member)).decode('utf-8', 'replace').split('\n')
    players = []
    acts = {}
    seen = {}
    printed = False
    cur = None
    for line in text:
        if '[AI' not in line:
            continue
        if '[AISTATE]' in line:
            m = RE_STATE.search(line)
            if m:
                g = m.groups()
                if g[0] == 'aistart' and int(g[1]) == turn:
                    if int(g[4]) == 0 and int(g[11]) > 0:
                        players.append('%s %s pos=(%s,%s,%s) tu=%s hp=%s/%s w=%s' % (g[2], g[3], g[6], g[7], g[8], g[10], g[11], g[12], g[16]))
                    if int(g[2]) in want:
                        print('UNIT', g[2], g[3], 'pos', (g[6], g[7], g[8]), 'tu', g[10], 'hp', g[11] + '/' + g[12], 'weapon', g[16], 'sees', g[19], 'seenby', g[20], 'known', g[21], 'near', g[22])
        elif '[AIDECIDE]' in line:
            m = RE_DEC.search(line)
            if m:
                seen[int(m.group(3))] = m.group(5)
        elif '[AICAND] acts=' in line:
            m = re.search(r'unit=(\d+) list=(\[.*\])', line)
            if m:
                try:
                    acts[int(m.group(1))] = json.loads(m.group(2))
                except Exception:
                    acts[int(m.group(1))] = []
        elif '[AIREC]' in line:
            j = json.loads(line[line.index('{'):])
            if j['turn'] == turn and j['unit'] in want:
                if not printed:
                    print('PLAYERS at aistart:')
                    for p in players:
                        print(' ', p)
                    printed = True
                b = j.get('base') or {}
                st = j.get('state', {})
                od = (b.get('reason') or {}).get('odds') or []
                cands = [dict(t=a.get('t'), u=a.get('u'), w=a.get('w'), tu=a.get('tu'), p=a.get('p'), lof=a.get('lof'), d=a.get('d')) for a in acts.get(j['unit'], []) if a.get('k') == 'a' and a.get('lof') == 1 and a.get('u', 9 ** 9) < 1000000 and a.get('tu', 9 ** 9) <= st.get('tu', 0)]
                print('REC', j['rec'], 'pos', st.get('pos'), 'tu', st.get('tu'), 'src', b.get('src'), 'type', b.get('t'), 'to', b.get('to'), 'w', b.get('w'), 'mode', b.get('mode'), 'seen', seen.get(j['unit']))
                if od:
                    print('   odds', od[-1])
                print('   legal', cands[:6], 'n=', len(cands))
                cur = j['rec']
        elif '[AIEXEC]' in line and cur is not None:
            j = json.loads(line[line.index('{'):])
            if j.get('rec') == cur:
                print('   EXEC pos', j.get('pos'), 'tu', j.get('tu'), 'spent', j.get('spent'), 'hp_lost', j.get('hp_lost'), 'dmg', j.get('dmg'), 'fdmg', j.get('fdmg'), 'downed', j.get('downed'), 'fdowned', j.get('fdowned'), 'trail', (j.get('trail') or [])[:2])
                cur = None


if __name__ == '__main__':
    main()
