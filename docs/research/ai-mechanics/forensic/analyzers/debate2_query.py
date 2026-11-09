# -*- coding: utf-8 -*-
"""Debate R2, the only new count over the frozen archive. Read-only.

Usage: py -3 debate2_query.py <zip> <funnel_json> [name_filter_regex]  (the report goes to stdout)
1. What a move to a fire point (the mechanism of variant C) turns into: same unit-turn attack, damage, and the unit's fate in the next player phase.
2. Hostiles killed in a player phase: could the side have known the threat before it chose the unit's last action?
   Threat = the killer. Known = at the start of the enemy phase before it the killer's cell was seen (seenby>0) or only marked (spotted==0).
3. Hostiles on view at the player phase start: are the viewers known at the start of the enemy phase before it (the player does not move in between)?
4. Friendly fire casualties other than self: geometry between the shooter, the aimed tile and the victim, at the moment of the shot.
5. Weapons: attacks, damage, TU by class; hostile units by the class of the weapon they start with.
6. Line of fire without an attack: weapon class and the source of the first decision.
"""
import collections
import gzip
import json
import math
import multiprocessing as mp
import re
import sys
import zipfile

ATT = {6, 7, 8, 9, 10, 12, 16}
RE_STATE = re.compile(r'\[AISTATE\] (\w+) turn=(\d+) unit=(\d+) type=(\S+) faction=(\d+) status=(\d+) pos=\((\d+),(\d+),(\d+)\) dir=(\d+) tu=(-?\d+) hp=(-?\d+)/(\d+) stun=(\d+) morale=(\d+) kneel=(\d) weapon=(\S+) spotted=(-?\d+) sniped=(-?\d+) sees=(\S+) seenby=(\d+) known=(\d+) near=(-?\d+) shade=(-?\d+)')
RE_CAS = re.compile(r'\[AICASUALTY\] turn=(\d+) side=(\d+) victim=(\d+) vfaction=(\d+) type=(\S+) how=(\w+) pos=\((\d+),(\d+),(\d+)\) tu=(-?\d+) kneel=\d seenby=(\d+) killer=(-?\d+) kfaction=(-?\d+) ktype=(\S+) dist=(-?\d+) weapon=(\S+) hit=(\S+) terrain=(\d)')


def seg_dist(p, a, b):
    ax, ay = a[0], a[1]
    bx, by = b[0], b[1]
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    if L == 0:
        return math.hypot(p[0] - ax, p[1] - ay)
    t = max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / L))
    return math.hypot(p[0] - (ax + t * dx), p[1] - (ay + t * dy))


def analyse(args):
    zpath, member, ranges = args
    text = gzip.decompress(zipfile.ZipFile(zpath).read(member)).decode('utf-8', 'replace')
    C = collections.Counter()
    snaps = collections.defaultdict(dict)
    recs = []
    seen_rec = set()
    cas = []
    for line in text.split('\n'):
        if '[AI' not in line:
            continue
        if '[AISTATE]' in line:
            m = RE_STATE.search(line)
            if m:
                g = m.groups()
                if g[0] in ('aistart', 'pstart'):
                    snaps[(g[0], int(g[1]))][int(g[2])] = dict(f=int(g[4]), status=int(g[5]), pos=(int(g[6]), int(g[7]), int(g[8])), w=g[16], spotted=int(g[17]), sees=set(int(v) for v in g[19].split(',') if v.isdigit()), seenby=int(g[20]), tu=int(g[10]))
        elif '[AIREC]' in line:
            try:
                j = json.loads(line[line.index('{'):])
            except Exception:
                continue
            if j['rec'] in seen_rec or j.get('side') != 1:
                continue
            seen_rec.add(j['rec'])
            recs.append(j)
        elif '[AIEXEC]' in line:
            try:
                j = json.loads(line[line.index('{'):])
            except Exception:
                continue
            for r in reversed(recs[-12:]):
                if r['rec'] == j['rec']:
                    r['_exec'] = j
                    break
        elif '[AICASUALTY]' in line:
            m = RE_CAS.search(line)
            if m:
                g = m.groups()
                cas.append(dict(turn=int(g[0]), side=int(g[1]), victim=int(g[2]), vf=int(g[3]), how=g[5], pos=(int(g[6]), int(g[7]), int(g[8])), killer=int(g[11]), kf=int(g[12]), dist=int(g[14]), w=g[15], terrain=int(g[17])))
    # unit-turns
    ut = collections.defaultdict(list)
    for r in recs:
        ut[(r['turn'], r['unit'])].append(r)
    dead_pl = collections.defaultdict(set)
    stun_pl = collections.defaultdict(set)
    for c in cas:
        if c['vf'] == 1 and c['side'] == 0:
            (dead_pl if c['how'] == 'dead' else stun_pl)[c['turn']].add(c['victim'])
    fired = collections.defaultdict(set)
    last_src = {}
    for r in recs:
        b = r.get('base') or {}
        last_src[(r['turn'], r['unit'])] = (b.get('src') or 'none').split('.')[0]
        if b.get('t') in ATT:
            fired[r['turn']].add(r['unit'])
    # 1. fire point moves, 6. line of fire without an attack comes from the funnel's definition of the source only
    for (t, u), rs in ut.items():
        srcs = [(r.get('base') or {}).get('src') or 'none' for r in rs]
        ts = [(r.get('base') or {}).get('t') for r in rs]
        att = any(x in ATT for x in ts)
        dmg = sum((r.get('_exec') or {}).get('dmg', 0) for r in rs if (r.get('base') or {}).get('t') in ATT)
        fd = sum((r.get('_exec') or {}).get('fdmg', 0) for r in rs if (r.get('base') or {}).get('t') in ATT)
        w0 = (rs[0].get('state') or {})
        kinds = [s for s in srcs if s.startswith('firepoint')]
        after = False
        if kinds:
            i = next(i for i, s in enumerate(srcs) if s.startswith('firepoint'))
            after = any(x in ATT for x in ts[i + 1:])
        tag = 'fp' if kinds else 'patrol' if any(s.startswith('patrol') for s in srcs) else 'other'
        C['ut_' + tag] += 1
        C['ut_%s_att' % tag] += att
        C['ut_%s_dmg' % tag] += dmg
        C['ut_%s_fdmg' % tag] += fd
        C['ut_%s_dead' % tag] += u in dead_pl.get(t + 1, set())
        if kinds:
            k = kinds[0]
            C['fp_%s' % k] += 1
            C['fp_%s_after' % k] += after
            C['fp_%s_moves' % k] += len(kinds)
            if not att:
                C['fp_noatt_moves_%s' % ('1' if len(kinds) == 1 else '2' if len(kinds) == 2 else '3+')] += 1
            # a fire point after a patrol-free dice result or after the fall-back: the first mode rolled
            odds = ((rs[0].get('base') or {}).get('reason') or {}).get('odds') or []
            roll = odds[-1].get('mode') if odds and isinstance(odds[-1], dict) else None
            C['fp_roll_%s' % roll] += 1
            C['fp_roll_%s_after' % roll] += after
    # 2. deaths in the player phase
    for c in cas:
        if c['vf'] != 1 or c['side'] != 0 or c['how'] != 'dead':
            continue
        C['pd_all'] += 1
        tag = 'pd_mine' if c['kf'] == 0 else 'pd_kf1' if c['kf'] == 1 else 'pd_other'
        C[tag] += 1
        if c['kf'] != 0:
            continue
        before = snaps.get(('aistart', c['turn'] - 1), {})
        k = before.get(c['killer'])
        if c['turn'] == 1 or not before:
            C['pd_k_round1'] += 1
        elif k is None:
            C['pd_k_noinfo'] += 1
        elif k['seenby'] > 0:
            C['pd_k_exact'] += 1
        elif k['spotted'] == 0:
            C['pd_k_mark'] += 1
        else:
            C['pd_k_unknown'] += 1
        if before and k is not None and c['turn'] > 1:
            # how far the killer's last known cell is from the victim, i.e. did the killer walk in
            C['pd_k_dist_%s' % ('00-05' if c['dist'] <= 5 else '06-10' if c['dist'] <= 10 else '11-20' if c['dist'] <= 20 else '21+')] += 1
    # 3. on view at the player phase start
    for (kind, T), units in snaps.items():
        if kind != 'pstart':
            continue
        before = snaps.get(('aistart', T - 1))
        if not before:
            continue
        players = {u: s for u, s in units.items() if s['f'] == 0 and s['status'] not in (6, 7, 8)}
        for u, s in units.items():
            if s['f'] != 1 or s['status'] in (6, 7, 8) or s['seenby'] == 0:
                continue
            viewers = [p for p, ps in players.items() if u in ps['sees']]
            if not viewers:
                C['view_nolist'] += 1
                continue
            known = [p for p in viewers if p in before and before[p]['seenby'] > 0]
            mark = [p for p in viewers if p in before and before[p]['spotted'] == 0 and before[p]['seenby'] == 0]
            cls = 'all_seen' if len(known) == len(viewers) else 'some_seen' if known else 'mark_only' if mark else 'none'
            C['view_' + cls] += 1
            C['view_%s_died' % cls] += u in dead_pl.get(T, set())
            C['view_%s_stun' % cls] += u in stun_pl.get(T, set())
            shot = u in fired.get(T - 1, set())
            spare = s['tu'] >= 20
            tag = '%s_%s' % ('shot' if shot else 'noshot', 'tu20' if spare else 'tu0')
            known_v = cls in ('all_seen', 'some_seen')
            C['vk_%s_%s' % ('known' if known_v else 'other', tag)] += 1
            C['vk_%s_%s_died' % ('known' if known_v else 'other', tag)] += u in dead_pl.get(T, set())
            if known_v and not shot:
                C['vk_noshot_src_' + last_src.get((T - 1, u), 'nodecision')] += 1
            was = before.get(u)
            if was is not None:
                C['view_%s_prevseen' % cls] += was['seenby'] > 0
                C['view_%s_moved' % cls] += was['pos'] != s['pos']
    # 4. friendly fire geometry
    last_att = collections.defaultdict(list)
    for r in recs:
        b = r.get('base') or {}
        if b.get('t') in ATT and b.get('to'):
            last_att[(r['turn'], r['unit'])].append(r)
    for c in cas:
        if c['vf'] != 1 or c['kf'] != 1:
            continue
        kk = 'ff_' + c['how']
        C[kk] += 1
        if c['victim'] == c['killer']:
            C['ff_self'] += 1
            continue
        if c['terrain']:
            C['ff_geo_terrain'] += 1
            continue
        rs = last_att.get((c['turn'], c['killer']))
        if not rs:
            C['ff_geo_noatt'] += 1
            continue
        r = rs[-1]
        sp = (r.get('_exec') or {}).get('pos') or (r.get('state') or {}).get('pos')
        to = r['base']['to']
        dt = math.hypot(c['pos'][0] - to[0], c['pos'][1] - to[1])
        dl = seg_dist(c['pos'], sp, to)
        cl = ranges.get(r['base'].get('w') or '', {}).get('class', '?')
        same = c['pos'][2] == to[2]
        if dt <= 1.5:
            g = 'at_target'
        elif dl <= 1.5:
            g = 'on_line'
        elif dt <= 4:
            g = 'near_target'
        else:
            g = 'elsewhere'
        C['ff_geo_' + g] += 1
        C['ff_geo_%s_%s' % (g, c['how'])] += 1
    # 5. weapons
    for r in recs:
        b = r.get('base') or {}
        if b.get('t') in ATT:
            w = b.get('w') or '?'
            cl = ranges.get(w, {}).get('class', 'not_in_table')
            ex = r.get('_exec') or {}
            C['att_' + cl] += 1
            C['att_%s_tu' % cl] += ex.get('spent', 0)
            C['att_%s_hp' % cl] += ex.get('dmg', 0)
            C['att_%s_fdmg' % cl] += ex.get('fdmg', 0)
    first = snaps.get(('aistart', 1), {})
    for u, s in first.items():
        if s['f'] == 1:
            C['unit_' + ranges.get(s['w'], {}).get('class', 'none' if s['w'] == '-' else 'not_in_table')] += 1
    return dict(battle=member.split('/')[1], C=C)


def main():
    zpath, fj = sys.argv[1:3]
    rx = re.compile(sys.argv[3]) if len(sys.argv) > 3 else None
    ranges = json.load(open(fj, encoding='utf-8-sig'))['ranges']
    Z = zipfile.ZipFile(zpath)
    members = [n for n in Z.namelist() if n.endswith('openxcom.log.gz') and (not rx or rx.search(n))]
    with mp.Pool(max(2, mp.cpu_count() - 2)) as pool:
        res = pool.map(analyse, [(zpath, m, ranges) for m in members])
    C = collections.Counter()
    for r in res:
        C.update(r['C'])
    NM = collections.Counter()
    for r in res:
        if '_M1_' not in r['battle']:
            NM.update(r['C'])
    for name, X in (('ALL', C), ('WITHOUT M1', NM)):
        print('=====', name, len(res) if name == 'ALL' else '')
        for pre in ('ut_', 'fp_', 'pd_', 'view_', 'vk_', 'ff_', 'att_', 'unit_'):
            print(pre, {k[len(pre):]: v for k, v in sorted(X.items()) if k.startswith(pre)})


if __name__ == '__main__':
    main()
