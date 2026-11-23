# -*- coding: utf-8 -*-
"""Debate R1, question 1: split the unit-turns without a line of fire into what the journal can tell apart.

Usage: py -3 debate1_funnel.py <out_dir> <label> <zip> [name_filter_regex]
Read-only for the archive. Same unit-turn definition as d0_census3.py. Line of sight from a cell the unit did not stand on is NOT
in the journal: every "reach" number here is an upper bound on a firing position, not a firing position.

Knowledge of a target at the first decision of the unit-turn (from the AISTATE snapshot of the player unit at aistart):
 exact  = seenby>0: a living hostile sees it now, the cell is legal under the contract
 fresh  = spotted==0 and seenby==0: reported this round, then out of sight; the journal has only its cell at the snapshot
 stale  = spotted>0, but a snapshot with spotted==0 or seenby>0 exists earlier in the battle: last-seen cell = that snapshot
 never  = no legal sighting in any snapshot

Weapon classes come from the whole series (attacks aimed at player units): proven >= 1 HP per attack over >= 10 attacks,
weak < 1 HP per attack over >= 10 attacks, unknown < 10 attacks, melee and thrown when the weapon has no ranged mode.
Practical range: p50 and p90 of the distance of the attacks that hurt.
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
RANGED = {7, 8, 9, 12}
RE_STATE = re.compile(r'\[AISTATE\] (\w+) turn=(\d+) unit=(\d+) type=(\S+) faction=(\d+) status=(\d+) pos=\((\d+),(\d+),(\d+)\) dir=(\d+) tu=(-?\d+) hp=(-?\d+)/(\d+) stun=(\d+) morale=(\d+) kneel=(\d) weapon=(\S+) spotted=(-?\d+) sniped=(-?\d+) sees=(\S+) seenby=(\d+) known=(\d+) near=(-?\d+)')
RE_DEC = re.compile(r'\[AIDECIDE\] turn=(\d+) side=(\d+) unit=(\d+) n=(-?\d+) .*? seen=(\S*)')
RE_MOVES = re.compile(r'\[AICAND\] moves=(\w+) unit=(\d+) list=(\S*)')


def dist2d(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def analyse(args):
    zpath, member, ranges = args
    text = gzip.decompress(zipfile.ZipFile(zpath).read(member)).decode('utf-8', 'replace')
    battle = member.split('/')[1]
    acts = {}
    moves_by_hash = {}
    recs = []
    seen = set()
    snaps = {}  # (kind, turn) -> {unit: state}
    state = {}
    sdseen = {}
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
        elif '[AICAND] moves=' in line:
            m = RE_MOVES.search(line)
            if m:
                cells = []
                for c in m.group(3).split(';'):
                    if ':' in c:
                        p, cost = c.split(':')
                        x, y, z = p.split('.')
                        cells.append((int(x), int(y), int(z), int(cost)))
                moves_by_hash[m.group(1)] = cells
        elif '[AIDECIDE]' in line:
            m = RE_DEC.search(line)
            if m:
                sdseen[int(m.group(3))] = set(int(v) for v in m.group(5).split(',') if v.isdigit())
        elif '[AISTATE]' in line:
            m = RE_STATE.search(line)
            if m:
                g = m.groups()
                u = int(g[2])
                st = dict(kind=g[0], turn=int(g[1]), u=u, type=g[3], f=int(g[4]), pos=(int(g[6]), int(g[7]), int(g[8])), tu=int(g[10]), hp=int(g[11]), w=g[16], spotted=int(g[17]), sees=g[19], seenby=int(g[20]), known=int(g[21]), near=int(g[22]))
                state[u] = st
                if g[0] in ('aistart', 'pstart'):
                    snaps.setdefault((g[0], int(g[1])), {})[u] = st
        elif '[AIREC]' in line:
            try:
                j = json.loads(line[line.index('{'):])
            except Exception:
                continue
            if j['rec'] in seen:
                continue
            seen.add(j['rec'])
            j['_acts'] = acts.pop(j['unit'], [])
            j['_st'] = state.get(j['unit'])
            j['_seen'] = sdseen.get(j['unit'], set())
            j['_moves'] = (j.get('cand') or {}).get('moves')
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
    # last legal sighting of each player unit, by snapshot order
    order = sorted(snaps.keys(), key=lambda k: (k[1], 0 if k[0] == 'pstart' else 1))
    legal_at = {}  # turn -> {player unit: (class, cell, age_turns, true cell)}
    last = {}
    for k in order:
        units = snaps[k]
        cur = {}
        for u, st in units.items():
            if st['f'] != 0:
                continue
            if st['seenby'] > 0 or st['spotted'] == 0:
                last[u] = (st['pos'], k[1])
            if k[0] == 'aistart':
                if st['seenby'] > 0:
                    cur[u] = ('exact', st['pos'], 0, st['pos'])
                elif st['spotted'] == 0:
                    cur[u] = ('fresh', st['pos'], 0, st['pos'])
                elif u in last:
                    cur[u] = ('stale', last[u][0], k[1] - last[u][1], st['pos'])
                else:
                    cur[u] = ('never', None, None, st['pos'])
        if k[0] == 'aistart':
            legal_at[k[1]] = cur
    C = collections.Counter()
    D = collections.Counter()
    ut = {}
    for r in recs:
        if r['side'] != 1:
            continue
        b = r.get('base') or {}
        ex = r.get('_exec') or {}
        st = r.get('state', {})
        tu = st.get('tu', 0)
        k = (r['turn'], r['unit'])
        x = ut.setdefault(k, dict(att=0, lof=False, srcs=[], tu0=tu, tuL=tu, first=r, w=None, mincost=None))
        x['srcs'].append(b.get('src') or 'none')
        if ex:
            x['tuL'] = ex.get('tu', x['tuL'])
        if b.get('t') in ATT:
            x['att'] += 1
            ch = next((a for a in r['_acts'] if a.get('id') == b.get('id')), None)
            if ch and ch.get('u', 9 ** 9) < 1000000:
                C['player_dmg'] += ex.get('dmg', 0)
        for a in r['_acts']:
            if a.get('k') == 'a' and a.get('t') in RANGED:
                if x['mincost'] is None or a.get('tu', 9 ** 9) < x['mincost']:
                    x['mincost'] = a.get('tu')
                    x['w'] = a.get('w') or x['w']
            if a.get('k') == 'a' and a.get('t') in (7, 8, 9, 10, 12) and a.get('lof') == 1 and a.get('u', 9 ** 9) in r['_seen'] and a.get('u', 9 ** 9) < 1000000 and a.get('tu', 9 ** 9) <= tu:
                x['lof'] = True
    for (t, u), x in ut.items():
        C['unit_turns'] += 1
        if x['att']:
            C['attacked'] += 1
            continue
        if x['lof']:
            C['lof_no_attack'] += 1
            continue
        C['no_lof'] += 1
        if t > 20:
            C['no_lof_late'] += 1
        first = x['first']
        pos0 = tuple((first.get('state') or {}).get('pos') or (0, 0, 0))
        tu0 = x['tu0']
        s0 = first.get('_st') or {}
        w = x['w'] or s0.get('w')
        # 1. what does the side legally know
        kn = legal_at.get(t, {})
        cls = {'exact': [], 'fresh': [], 'stale': [], 'never': []}
        for pu, (c, cell, age, true) in kn.items():
            cls[c].append((pu, cell, age, true))
        if cls['exact']:
            info = 'exact'
        elif cls['fresh']:
            info = 'fresh'
        elif cls['stale']:
            info = 'stale'
        else:
            info = 'none'
        C['info_' + info] += 1
        if s0.get('known', 0) > 0:
            C['audit_known'] += 1
        # 2. stated mode of the unit-turn, weapon class
        src_mode = 'other'
        srcs = x['srcs']
        if any(s.startswith('escape') for s in srcs):
            src_mode = 'escape'
        elif any(s.startswith('ambush') for s in srcs):
            src_mode = 'ambush'
        elif any(s.startswith('patrol') or s.startswith('combat') or s.startswith('firepoint') for s in srcs):
            src_mode = 'patrol'
        C['mode_' + src_mode] += 1
        C['info_%s_mode_%s' % (info, src_mode)] += 1
        # 'patrol' above holds the unit-turns with a firepoint or combat walk too: split them, and take the first decision's roll of evaluateAIMode
        src_kind = None
        if src_mode == 'patrol':
            src_kind = 'firepoint' if any(s.startswith('firepoint') or s.startswith('combat') for s in srcs) else 'patrol_only'
            C['info_%s_kind_%s' % (info, src_kind)] += 1
        reason = first.get('reason') or (first.get('base') or {}).get('reason') or {}
        odds = reason.get('odds') or []
        roll = {0: 'patrol', 1: 'ambush', 2: 'combat', 3: 'escape'}.get(odds[-1].get('mode')) if odds else 'no_roll'
        if info == 'none':
            continue
        cells = [cc[1] for key in ('exact', 'fresh') for cc in cls[key]] if info in ('exact', 'fresh') else [cc[1] for cc in cls['stale']]
        dnear = min(dist2d(pos0, c) for c in cells)
        bucket = '00-08' if dnear <= 8 else '09-15' if dnear <= 15 else '16-25' if dnear <= 25 else '26+'
        C['info_%s_d%s' % (info, bucket)] += 1
        wclass = 'none'
        if w and w != '-':
            wclass = ranges[w]['class'] if w in ranges else 'unknown'
        C['info_%s_w_%s' % (info, wclass)] += 1
        # 3. reach this turn from the first decision's move list; a cost of -1 marks a listed destination the unit cannot reach this turn
        cellsm = moves_by_hash.get(first.get('_moves') or '', None)
        if cellsm is None:
            C['info_%s_nomoves' % info] += 1
            continue
        r = ranges.get(w) or {}
        cost_shot = x['mincost'] if x['mincost'] is not None else r.get('cost')
        tags = (('p50', r.get('p50', 0)), ('p90', r.get('p90', 0)))
        flags = {tag: dict(now=pr > 0 and dnear <= pr, any=False, shot=False) for tag, pr in tags}
        adj = False
        radius = 0.0
        for (cx, cy, cz, cost) in cellsm:
            if cost < 0 or cost > tu0:
                continue
            radius = max(radius, dist2d((cx, cy), pos0))
            for c in cells:
                d = dist2d((cx, cy), c)
                if d <= 1.5:
                    adj = True
                for tag, pr in tags:
                    if pr > 0 and d <= pr:
                        flags[tag]['any'] = True
                        if cost_shot is not None and cost + cost_shot <= tu0:
                            flags[tag]['shot'] = True
        g = 'info_%s_' % info
        if radius == 0:
            C[g + 'immobile'] += 1
        for tag, pr in tags:
            fl = flags[tag]
            if fl['now']:
                C[g + tag + '_in_range_now'] += 1
            if fl['any']:
                C[g + tag + '_reach_range'] += 1
            if fl['shot']:
                C[g + tag + '_reach_shot'] += 1
            # next turn: nothing but distance, walls ignored, so an upper bound
            two = not fl['any'] and pr > 0 and dnear <= pr + 2 * radius
            if two:
                C[g + tag + '_two_turns'] += 1
            if fl['shot'] and src_mode == 'patrol':
                C[g + tag + '_F2_patrol'] += 1
                C[g + tag + '_F3_' + wclass] += 1
                if wclass == 'proven':
                    C[g + tag + '_F3k_' + src_kind] += 1
                    C[g + tag + '_F3k_%s_roll_%s' % (src_kind, roll)] += 1
                    D[g + tag + '_F3_hp'] += r.get('yield', 0)
                    if t > 20:
                        C[g + tag + '_F3_proven_late'] += 1
            if two and src_mode == 'patrol' and wclass == 'proven':
                C[g + tag + '_F4_two_turns_proven_patrol'] += 1
        if adj:
            C[g + 'reach_adjacent'] += 1
        if wclass == 'melee' and src_mode == 'patrol':
            C[g + 'melee_patrol'] += 1
            if adj:
                C[g + 'melee_patrol_adj'] += 1
    # staleness of what would be reported: last-seen cell against the true cell at aistart, all targets
    S = collections.Counter()
    for t, cur in legal_at.items():
        for pu, (c, cell, age, true) in cur.items():
            S['tgt_' + c] += 1
            if c == 'stale':
                S['stale_age_%s' % ('1' if age == 1 else '2' if age == 2 else '3+')] += 1
                dd = dist2d(cell, true)
                S['stale_err_sum'] += int(dd)
                S['stale_err_%s' % ('00-02' if dd <= 2 else '03-08' if dd <= 8 else '09-15' if dd <= 15 else '16+')] += 1
    return dict(battle=battle, C=dict(C), D={k: int(v) for k, v in D.items()}, S=dict(S))


def _weapon_scan(args):
    zpath, member = args
    text = gzip.decompress(zipfile.ZipFile(zpath).read(member)).decode('utf-8', 'replace')
    acts = {}
    recs = {}
    W = collections.defaultdict(lambda: dict(att=0, dmg=0, ds=[], melee=0, ranged=0, thrown=0, costs=[]))
    for line in text.split('\n'):
        if '[AICAND] acts=' in line:
            m = re.search(r'unit=(\d+) list=(\[.*\])', line)
            if m:
                try:
                    acts[int(m.group(1))] = json.loads(m.group(2))
                except Exception:
                    pass
        elif '[AIREC]' in line:
            try:
                j = json.loads(line[line.index('{'):])
            except Exception:
                continue
            if j['side'] != 1:
                acts.pop(j['unit'], None)
                continue
            al = acts.pop(j['unit'], [])
            for a in al:
                if a.get('k') == 'a':
                    w = a.get('w') or '?'
                    if a.get('t') in RANGED:
                        W[w]['ranged'] += 1
                        W[w]['costs'].append(a.get('tu', 0))
                    elif a.get('t') == 6:
                        W[w]['thrown'] += 1
                    elif a.get('t') == 10:
                        W[w]['melee'] += 1
            b = j.get('base') or {}
            if b.get('t') in ATT:
                ch = next((a for a in al if a.get('id') == b.get('id')), None)
                if ch and ch.get('u', 9 ** 9) < 1000000:
                    recs[j['rec']] = (b.get('w') or '?', ch.get('d', 0))
        elif '[AIEXEC]' in line:
            try:
                j = json.loads(line[line.index('{'):])
            except Exception:
                continue
            if j['rec'] in recs:
                w, d = recs.pop(j['rec'])
                W[w]['att'] += 1
                W[w]['dmg'] += j.get('dmg', 0)
                if j.get('dmg', 0) > 0:
                    W[w]['ds'].append(d)
    return {k: dict(v) for k, v in W.items()}


def build_ranges(zpath, flt):
    z = zipfile.ZipFile(zpath)
    names = [n for n in z.namelist() if n.startswith('out/') and n.endswith('openxcom.log.gz') and (not flt or flt.search(n))]
    with mp.Pool(6) as pool:
        res = pool.map(_weapon_scan, [(zpath, n) for n in names], chunksize=1)
    W = collections.defaultdict(lambda: dict(att=0, dmg=0, ds=[], melee=0, ranged=0, thrown=0, costs=[]))
    for r in res:
        for w, v in r.items():
            X = W[w]
            for key in ('att', 'dmg', 'melee', 'ranged', 'thrown'):
                X[key] += v[key]
            X['ds'] += v['ds']
            X['costs'] += v['costs']
    out = {}
    for w, v in W.items():
        ds = sorted(v['ds'])
        p90 = ds[int(0.9 * (len(ds) - 1))] if ds else 0
        p50 = ds[int(0.5 * (len(ds) - 1))] if ds else 0
        cs = sorted(v['costs'])
        cost = cs[len(cs) // 2] if cs else None
        y = v['dmg'] / v['att'] if v['att'] else 0
        if v['ranged'] == 0 and v['thrown'] > 0:
            cl = 'thrown'
        elif v['ranged'] == 0 and v['melee'] > 0:
            cl = 'melee'
        elif v['att'] >= 10 and y >= 1:
            cl = 'proven'
        elif v['att'] >= 10:
            cl = 'weak'
        else:
            cl = 'unknown'
        out[w] = dict(p90=p90, p50=p50, cost=cost, att=v['att'], dmg=v['dmg'], ranged=v['ranged'], melee=v['melee'], thrown=v['thrown'], **{'yield': y, 'class': cl})
    return out


def main():
    out_dir, label, zpath = sys.argv[1:4]
    flt = re.compile(sys.argv[4]) if len(sys.argv) > 4 else None
    ranges = build_ranges(zpath, flt)
    z = zipfile.ZipFile(zpath)
    jobs = [(zpath, n, ranges) for n in z.namelist() if n.startswith('out/') and n.endswith('openxcom.log.gz') and (not flt or flt.search(n))]
    with mp.Pool(6) as pool:
        res = pool.map(analyse, jobs, chunksize=1)
    with open(os.path.join(out_dir, 'debate1_funnel_%s.json' % label), 'w', encoding='utf-8-sig') as f:
        json.dump(dict(res=res, ranges=ranges), f, ensure_ascii=False)
    print('ok', label, len(res))


if __name__ == '__main__':
    main()
