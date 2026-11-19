# -*- coding: utf-8 -*-
"""Debate R1: natural experiment on patrol moves, exposure against its confounders, friendly fire by cause, baseline of concentration.

Usage: py -3 debate1_causal.py <out_dir> <label> <zip> <ranges_json> [name_filter_regex]
Read-only for the archive. ranges_json = debate1_funnel_<label>.json (weapon classes). Writes debate1_causal_<label>.json.

Natural experiment: getPatrolNode does not see the enemy (SavedBattleGame.cpp, A-08), so a patrol move ends closer to or farther from
a target the side knows for reasons unrelated to the target. Rows are unit-turns spent on patrol only, with a target spotted this round.
delta = distance from the end of the move to the known cells, minus the same from the start. Outcomes count the dead as zero.
"""
import collections
import gzip
import json
import math
import multiprocessing as mp
import os
import re
import sys
import zipfile

ATT = {6, 7, 8, 9, 10, 12, 16}
RE_STATE = re.compile(r'\[AISTATE\] (\w+) turn=(\d+) unit=(\d+) type=(\S+) faction=(\d+) status=(\d+) pos=\((\d+),(\d+),(\d+)\) dir=(\d+) tu=(-?\d+) hp=(-?\d+)/(\d+) stun=(\d+) morale=(\d+) kneel=(\d) weapon=(\S+) spotted=(-?\d+) sniped=(-?\d+) sees=(\S+) seenby=(\d+) known=(\d+) near=(-?\d+)')
RE_DEC = re.compile(r'\[AIDECIDE\] turn=(\d+) side=(\d+) unit=(\d+) n=(-?\d+) .*? seen=(\S*)')
RE_CAS = re.compile(r'\[AICASUALTY\] turn=(\d+) side=(\d+) victim=(\d+) vfaction=(\d+) type=(\S+) how=(\w+) pos=\((\d+),(\d+),(\d+)\) tu=(-?\d+) kneel=\d seenby=(\d+) killer=(-?\d+) kfaction=(-?\d+) ktype=(\S+) dist=(-?\d+) weapon=(\S+) hit=(\S+) terrain=(\d)')
RE_EV = re.compile(r'\[AIEVENT\] turn=(\d+) side=(\d+) what=(\w+) unit=(-?\d+) pos=\((\d+),(\d+),(\d+)\)')


def dist2d(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def bucket_d(d):
    return '00-08' if d <= 8 else '09-15' if d <= 15 else '16-25' if d <= 25 else '26+'


def bucket_near(d):
    return '00-05' if d <= 5 else '06-10' if d <= 10 else '11-15' if d <= 15 else '16-25' if d <= 25 else '26+'


def analyse(args):
    zpath, member, ranges = args
    text = gzip.decompress(zipfile.ZipFile(zpath).read(member)).decode('utf-8', 'replace')
    battle = member.split('/')[1]
    acts = {}
    recs = []
    seen = set()
    snaps = {}
    state = {}
    cas = []
    open_rec = None
    win = collections.defaultdict(lambda: dict(expl=[], react=0, cas=[]))
    for line in text.split('\n'):
        if '[AI' not in line:
            continue
        if '[AICAND] acts=' in line:
            m = re.search(r'unit=(\d+) list=(\[.*\])', line)
            if m:
                try:
                    acts[int(m.group(1))] = json.loads(m.group(2))
                except Exception:
                    acts[int(m.group(1))] = []
        elif '[AISTATE]' in line:
            m = RE_STATE.search(line)
            if m:
                g = m.groups()
                u = int(g[2])
                st = dict(kind=g[0], turn=int(g[1]), u=u, type=g[3], f=int(g[4]), pos=(int(g[6]), int(g[7]), int(g[8])), tu=int(g[10]), hp=int(g[11]), hpmax=int(g[12]), w=g[16], spotted=int(g[17]), seenby=int(g[20]), known=int(g[21]))
                state[u] = st
                if g[0] in ('aistart', 'pstart'):
                    snaps.setdefault((g[0], int(g[1])), {})[u] = st
        elif '[AIREC]' in line:
            try:
                j = json.loads(line[line.index('{'):])
            except Exception:
                continue
            open_rec = j['rec']
            if j['rec'] in seen:
                continue
            seen.add(j['rec'])
            j['_acts'] = acts.pop(j['unit'], [])
            j['_st'] = state.get(j['unit'])
            recs.append(j)
        elif '[AIEXEC]' in line:
            try:
                j = json.loads(line[line.index('{'):])
            except Exception:
                continue
            for r in reversed(recs[-12:]):
                if r['rec'] == j['rec']:
                    r['_exec'] = j
                    r['_win'] = win.get(j['rec'])
                    break
            open_rec = None
        elif '[AIEVENT]' in line:
            m = RE_EV.search(line)
            if m and open_rec is not None:
                if m.group(3) == 'explosion':
                    win[open_rec]['expl'].append((int(m.group(5)), int(m.group(6)), int(m.group(7))))
                elif m.group(3) == 'reaction':
                    win[open_rec]['react'] += 1
        elif '[AICASUALTY]' in line:
            m = RE_CAS.search(line)
            if m:
                g = m.groups()
                c = dict(turn=int(g[0]), side=int(g[1]), v=int(g[2]), vf=int(g[3]), type=g[4], how=g[5], seenby=int(g[10]), k=int(g[11]), kf=int(g[12]), ktype=g[13], dist=int(g[14]), w=g[15], terrain=int(g[17]), rec=open_rec)
                cas.append(c)
                if open_rec is not None:
                    win[open_rec]['cas'].append(c)
    # ---------- unit-turns
    ut = {}
    conc = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0, 0]))  # turn -> target -> [attacks, dmg, downed]; attackers apart
    conc_u = collections.defaultdict(lambda: collections.defaultdict(set))
    ff = []
    for r in recs:
        if r['side'] != 1:
            continue
        b = r.get('base') or {}
        ex = r.get('_exec') or {}
        k = (r['turn'], r['unit'])
        x = ut.setdefault(k, dict(att=0, srcs=[], first=r, dmg=0, w=None, lof=False, spent=0))
        x['srcs'].append(b.get('src') or 'none')
        x['spent'] += ex.get('spent', 0)
        if b.get('t') in ATT:
            x['att'] += 1
            ch = next((a for a in r['_acts'] if a.get('id') == b.get('id')), None)
            if ch and ch.get('u', 9 ** 9) < 1000000:
                x['dmg'] += ex.get('dmg', 0)
                c = conc[r['turn']][ch['u']]
                c[0] += 1
                c[1] += ex.get('dmg', 0)
                c[2] += ex.get('downed', 0)
                conc_u[r['turn']][ch['u']].add(r['unit'])
        for a in r['_acts']:
            if a.get('k') == 'a' and a.get('t') in (7, 8, 9, 12):
                x['w'] = x['w'] or a.get('w')
            if a.get('k') == 'a' and a.get('lof') == 1 and a.get('u', 9 ** 9) < 1000000:
                x['lof'] = True
        fd = ex.get('fdmg', 0)
        fdn = ex.get('fdowned', 0)
        if fd or fdn:
            w = r.get('_win') or dict(expl=[], react=0, cas=[])
            ff.append(dict(rec=r['rec'], turn=r['turn'], unit=r['unit'], t=b.get('t'), w=b.get('w') or '?', att=b.get('t') in ATT, src=b.get('src') or 'none', fdmg=fd, fdown=fdn, dmg=ex.get('dmg', 0), nexpl=len(w['expl']), cexpl=len(set(w['expl'])), react=w['react'], cas_own=sum(1 for c in w['cas'] if c['vf'] == 1 and c['how'] == 'dead'), cas_own_terrain=sum(1 for c in w['cas'] if c['vf'] == 1 and c['how'] == 'dead' and c['terrain']), cas_kf_own=sum(1 for c in w['cas'] if c['vf'] == 1 and c['how'] == 'dead' and c['kf'] == 1), cas_kf_player=sum(1 for c in w['cas'] if c['vf'] == 1 and c['how'] == 'dead' and c['kf'] == 0)))
    # legal cells at each aistart (exact or fresh only)
    legal = {}
    for (kind, t), units in snaps.items():
        if kind != 'aistart':
            continue
        legal[t] = [st['pos'] for u, st in units.items() if st['f'] == 0 and st['hp'] > 0 and (st['seenby'] > 0 or st['spotted'] == 0)]
    # ---------- natural experiment rows
    rows = []
    for (t, u), x in ut.items():
        if x['att'] or not x['srcs']:
            continue
        if any(not s.startswith('patrol') for s in x['srcs'] if s != 'none'):
            continue
        if not any(s.startswith('patrol') for s in x['srcs']):
            continue
        cells = legal.get(t)
        if not cells:
            continue
        first = x['first']
        p0 = tuple((first.get('state') or {}).get('pos') or (0, 0, 0))
        pend = snaps.get(('pstart', t + 1), {}).get(u)
        d0 = min(dist2d(p0, c) for c in cells)
        s0 = first.get('_st') or {}
        w = x['w'] or s0.get('w')
        wc = (ranges.get(w) or {}).get('class', 'unknown') if w and w != '-' else 'none'
        died_walk = 0 if pend else 1
        if pend:
            d1 = min(dist2d(pend['pos'], c) for c in cells)
            nxt = snaps.get(('aistart', t + 1), {}).get(u)
            died = 0 if (nxt and nxt['hp'] > 0) else 1
            lost = max(0, pend['hp'] - (nxt['hp'] if nxt else 0))
            seen_ = 1 if pend['seenby'] > 0 else 0
            sp_hp = pend['hp']
        else:
            d1 = d0
            died = 1
            lost = 0
            seen_ = 0
            sp_hp = 0
        n1 = ut.get((t + 1, u))
        n2 = ut.get((t + 2, u))
        prev = snaps.get(('pstart', t), {}).get(u)
        rows.append(dict(sc=d0, d0b=bucket_d(d0), wc=wc, delta=d1 - d0, spent=x['spent'], died_walk=died_walk, seen=seen_, died=died, lost=lost, att1=1 if n1 and n1['att'] else 0, lof1=1 if n1 and n1['lof'] else 0, dmg1=n1['dmg'] if n1 else 0, att2=1 if n2 and n2['att'] else 0, dmg2=n2['dmg'] if n2 else 0, hpf=(s0.get('hp', 0) / max(1, s0.get('hpmax', 1))), tu=(first.get('state') or {}).get('tu', 0), prevseen=1 if prev and prev['seenby'] > 0 else 0, t=t))
    # ---------- exposure rows
    expo = []
    phase = []
    for (kind, t), units in snaps.items():
        if kind != 'pstart':
            continue
        nxt = snaps.get(('aistart', t), {})
        if not nxt:
            continue
        pl = [st['pos'] for u, st in units.items() if st['f'] == 0 and st['hp'] > 0]
        hs = [st for u, st in units.items() if st['f'] == 1 and st['hp'] > 0]
        if not pl or not hs:
            continue
        V = sum(1 for st in hs if st['seenby'] > 0)
        dead_seen = dead_unseen = 0
        for st in hs:
            now = nxt[st['u']]['hp'] if st['u'] in nxt else 0
            d = min(dist2d(st['pos'], p) for p in pl)
            dead = 1 if now <= 0 else 0
            lost = max(0, st['hp'] - now)
            s = 1 if st['seenby'] > 0 else 0
            expo.append(dict(t=t, type=st['type'], db=bucket_near(d), seen=s, seenby=st['seenby'], dead=dead, lost=lost, hp=st['hp'], hpb=int(4 * st['hp'] / max(1, st['hpmax']))))
            if s:
                dead_seen += dead
            else:
                dead_unseen += dead
        phase.append(dict(t=t, V=V, N=len(hs), np=len(pl), dead_seen=dead_seen, dead_unseen=dead_unseen))
    # deaths of hostiles by phase and killer
    K = collections.Counter()
    for c in cas:
        if c['vf'] == 1 and c['how'] == 'dead':
            K['side%d_kf%d' % (c['side'], c['kf'])] += 1
            if c['terrain']:
                K['side%d_kf%d_terrain' % (c['side'], c['kf'])] += 1
            if c['side'] == 0:
                K['playerphase_seenby%s' % ('0' if c['seenby'] == 0 else '+')] += 1
    # ---------- concentration
    CC = collections.Counter()
    for t, tg in conc.items():
        for u, c in tg.items():
            n = len(conc_u[t][u])
            b = '1' if n == 1 else '2' if n == 2 else '3' if n == 3 else '4+'
            CC['targets_' + b] += 1
            CC['attacks_' + b] += c[0]
            CC['dmg_' + b] += c[1]
            CC['downed_' + b] += c[2]
    return dict(battle=battle, rows=rows, expo=expo, phase=phase, ff=ff, K=dict(K), CC=dict(CC))


def main():
    out_dir, label, zpath, rj = sys.argv[1:5]
    flt = re.compile(sys.argv[5]) if len(sys.argv) > 5 else None
    ranges = json.load(open(rj, encoding='utf-8-sig'))['ranges']
    z = zipfile.ZipFile(zpath)
    jobs = [(zpath, n, ranges) for n in z.namelist() if n.startswith('out/') and n.endswith('openxcom.log.gz') and (not flt or flt.search(n))]
    with mp.Pool(6) as pool:
        res = pool.map(analyse, jobs, chunksize=1)
    with open(os.path.join(out_dir, 'debate1_causal_%s.json' % label), 'w', encoding='utf-8-sig') as f:
        json.dump(res, f, ensure_ascii=False)
    print('ok', label, len(res), sum(len(r['rows']) for r in res))


if __name__ == '__main__':
    main()
