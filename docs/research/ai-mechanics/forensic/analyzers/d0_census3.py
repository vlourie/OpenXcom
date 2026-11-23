# -*- coding: utf-8 -*-
"""Third pass: end-of-turn exposure, who can hurt the squad at all, upper bounds of the levers, examples for the case studies.

Usage: py -3 d0_census3.py <out_dir> <label> <zip> [name_filter_regex]
Read-only for the archive. "Effective" weapon = the unit's weapon that has done HP damage or a stun to a PLAYER unit in this battle
(known only after the fact, so bounds computed from it are upper bounds).
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
RE_CAS = re.compile(r'\[AICASUALTY\] turn=(\d+) side=(\d+) victim=(\d+) vfaction=(\d+) type=(\S+) how=(\w+) .*?killer=(-?\d+) kfaction=(-?\d+)')


def analyse(args):
    zpath, member = args
    text = gzip.decompress(zipfile.ZipFile(zpath).read(member)).decode('utf-8', 'replace')
    battle = member.split('/')[1]
    acts = {}
    recs = []
    seen = set()
    state = {}
    phases = {}
    dead_turn = {}
    types = {}
    last_seen = {}
    for line in text.split('\n'):
        if '[AI' not in line:
            continue
        if '[AIDECIDE]' in line:
            m = RE_DEC.search(line)
            if m:
                last_seen[int(m.group(3))] = set(int(v) for v in m.group(5).split(',') if v.isdigit())
        elif '[AICAND] acts=' in line:
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
                types[u] = g[3]
                st = dict(kind=g[0], turn=int(g[1]), u=u, f=int(g[4]), pos=(int(g[6]), int(g[7]), int(g[8])), tu=int(g[10]), hp=int(g[11]), hpmax=int(g[12]), w=g[16], sees=g[19], seenby=int(g[20]), known=int(g[21]), near=int(g[22]))
                state[u] = st
                if g[0] in ('aistart', 'pstart'):
                    phases.setdefault((g[0], int(g[1])), {})[u] = st
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
            j['_seen'] = last_seen.get(j['unit'], set())
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
            if m and m.group(6) == 'dead':
                dead_turn.setdefault(int(m.group(3)), int(m.group(1)))
    # 1. effective units and weapons in this battle: attacks aimed at player units that changed HP or stun
    eff_w = collections.Counter()
    eff_u = collections.Counter()
    w_att = collections.Counter()
    w_tu = collections.Counter()
    u_att = collections.Counter()
    u_tu_att = collections.Counter()
    for r in recs:
        if r['side'] != 1:
            continue
        b = r.get('base') or {}
        ex = r.get('_exec') or {}
        if b.get('t') not in ATT:
            continue
        ch = next((a for a in r['_acts'] if a.get('id') == b.get('id')), None)
        tgt = ch.get('u') if ch else None
        w = b.get('w') or '?'
        w_att[w] += 1
        w_tu[w] += ex.get('spent', 0)
        u_att[r['unit']] += 1
        u_tu_att[r['unit']] += ex.get('spent', 0)
        if tgt is not None and tgt < 1000000 and (ex.get('dmg', 0) > 0 or ex.get('stunned', 0) > 0):
            eff_w[w] += ex.get('dmg', 0) + 1
            eff_u[r['unit']] += ex.get('dmg', 0) + ex.get('stunned', 0)
    C = collections.Counter()
    C['units_attacked'] = len(u_att)
    C['units_hurt_player'] = len(eff_u)
    C['attack_tu'] = sum(u_tu_att.values())
    C['attack_tu_units_never_hurt_player'] = sum(v for u, v in u_tu_att.items() if u not in eff_u)
    C['attack_tu_weapons_never_hurt_player'] = sum(v for w, v in w_tu.items() if w not in eff_w)
    C['attacks'] = sum(w_att.values())
    C['attacks_weapons_never_hurt_player'] = sum(v for w, v in w_att.items() if w not in eff_w)
    C['player_dmg_stun'] = sum(eff_u.values())
    top = sorted(eff_u.values(), reverse=True)
    C['top3_share_x1000'] = int(1000 * sum(top[:3]) / max(1, sum(top)))
    # mean yield per attack by weapon vs players (for the upper bounds)
    yld = collections.defaultdict(lambda: [0, 0])
    for r in recs:
        if r['side'] != 1:
            continue
        b = r.get('base') or {}
        ex = r.get('_exec') or {}
        if b.get('t') in ATT:
            ch = next((a for a in r['_acts'] if a.get('id') == b.get('id')), None)
            if ch and ch.get('u', 9 ** 9) < 1000000:
                y = yld[b.get('w') or '?']
                y[0] += 1
                y[1] += ex.get('dmg', 0)
    # 2. unit turns: did a unit with a working weapon get a target; what happened with a legal attack
    ut = {}
    for r in recs:
        if r['side'] != 1:
            continue
        b = r.get('base') or {}
        ex = r.get('_exec') or {}
        st = r.get('state', {})
        tu = st.get('tu', 0)
        k = (r['turn'], r['unit'])
        x = ut.setdefault(k, dict(att=0, legal=None, srcs=[], tu0=tu, tuL=tu, w=set(), walk_closer=0, known=False, near=None))
        x['srcs'].append(b.get('src') or 'none')
        if ex:
            x['tuL'] = ex.get('tu', x['tuL'])
        s0 = r.get('_st') or {}
        sees = r['_seen']  # visibility at the decision (AIDECIDE), AISTATE only gives the start of the turn
        if s0.get('known', 0) > 0:
            x['known'] = True
            x['near'] = s0.get('near') if x['near'] is None else min(x['near'], s0.get('near'))
        if b.get('t') in ATT:
            x['att'] += 1
        for a in r['_acts']:
            # melee needs an adjacent target, so it does not count for 'could still shoot what it sees'
            if a.get('k') == 'a' and a.get('t') in (7, 8, 9, 12) and a.get('tu', 9 ** 9) < x.get('mincost', 9 ** 9):
                x['mincost'] = a.get('tu')
                x['cheap_w'] = a.get('w') or '?'
            if a.get('k') == 'a' and a.get('t') in (7, 8, 9, 10, 12) and a.get('lof') == 1 and a.get('u', 9 ** 9) in sees and a.get('u', 9 ** 9) < 1000000 and a.get('tu', 9 ** 9) <= tu:
                w = a.get('w') or '?'
                x['legal_d'] = min(x.get('legal_d', 999), a.get('d', 999))
                # AIDECIDE seen = spotted by the SIDE this round. Own vision is logged only at aistart (AISTATE sees): first decision only.
                own0 = set(int(v) for v in (s0.get('sees') or '').split(',') if v.isdigit()) if s0.get('kind') == 'aistart' and s0.get('turn') == r['turn'] else set()
                if a.get('u') in own0:
                    x['legal_own'] = True
                if x['legal'] is None or (w in eff_w and x['legal'] not in eff_w):
                    x['legal'] = w
    U = collections.Counter()
    bound_fire = 0.0
    bound_own = collections.Counter()

    def mean_yield(w):
        y = yld.get(w)
        return y[1] / y[0] if y and y[0] else 0.0
    for (t, u), x in ut.items():
        cap = u in eff_u
        key = 'hurter' if cap else 'nonhurter'
        U[key + '_unit_turns'] += 1
        # own vision at the END of the hostile turn: AISTATE pstart of the next turn; TU left after the last action
        pend = phases.get(('pstart', t + 1), {}).get(u)
        end_sees = [int(v) for v in ((pend or {}).get('sees') or '').split(',') if v.isdigit() and int(v) < 1000000]
        end_ok = bool(end_sees) and x.get('mincost', 9 ** 9) <= max(0, x['tuL'])
        if x['att']:
            if end_ok:
                U['attacked_end_sees_tu_ok'] += 1
                bound_own['more'] += mean_yield(x.get('cheap_w'))
        else:
            if end_sees:
                U['noatt_end_sees'] += 1
            if end_ok:
                U['noatt_end_sees_tu_ok'] += 1
                U['endok_lastsrc_' + x['srcs'][-1]] += 1
                bound_own['end'] += mean_yield(x.get('cheap_w'))
            if x.get('legal_own'):
                bound_own['start'] += mean_yield(x.get('legal'))
            if end_ok or x.get('legal_own'):
                U['noatt_own_any'] += 1
                bound_own['any'] += mean_yield(x.get('legal') if x.get('legal_own') else x.get('cheap_w'))
        if x['att']:
            U[key + '_attack'] += 1
        elif x['legal'] is not None:
            U[key + '_legal_no_attack'] += 1
            if x.get('legal_own'):
                U[key + '_legal_own_no_attack'] += 1
            d = x.get('legal_d', 999)
            U['legal_noatt_d' + ('00-07' if d < 8 else '08-12' if d < 13 else '13-20' if d < 21 else '21-30' if d < 31 else '31+')] += 1
            w = x['legal']
            if w in eff_w:
                U['legal_no_attack_effective_weapon'] += 1
                y = yld.get(w)
                if y and y[0]:
                    bound_fire += y[1] / y[0]
        else:
            U[key + '_no_target'] += 1
            if x['known']:
                U[key + '_no_target_known'] += 1
                if x['near'] is not None and 0 <= x['near'] <= 15:
                    U[key + '_no_target_known_near15'] += 1
            U[key + '_no_target_tu'] += max(0, x['tuL'])
    U['bound_fire_dmg'] = int(bound_fire)
    for k, v in bound_own.items():
        U['bound_own_' + k] = int(v)
    # 3. end-of-turn exposure: hostile unit standing at the next player phase, seen or not, HP lost / death in that player phase
    E = collections.defaultdict(lambda: [0, 0, 0, 0])  # (seen?) -> units, hp at start, hp lost, dead
    lastsrc = {}
    for r in recs:
        if r['side'] == 1:
            lastsrc[(r['turn'], r['unit'])] = (r.get('base') or {}).get('src') or 'none'
    Es = collections.defaultdict(lambda: [0, 0, 0, 0])
    for (kind, t), units in phases.items():
        if kind != 'pstart':
            continue
        nxt = phases.get(('aistart', t), {})
        if not nxt:
            continue
        for u, st in units.items():
            if st['f'] != 1 or st['hp'] <= 0:
                continue
            now = nxt[u]['hp'] if u in nxt else 0
            k = 'seen' if st['seenby'] > 0 else 'unseen'
            X = E[k]
            X[0] += 1
            X[1] += st['hp']
            X[2] += max(0, st['hp'] - now)
            X[3] += 1 if now <= 0 else 0
            if st['seenby'] > 0:
                Y = Es[lastsrc.get((t - 1, u), 'none')]
                Y[0] += 1
                Y[2] += max(0, st['hp'] - now)
                Y[3] += 1 if now <= 0 else 0
    # 4. life and chance: hostile who died without ever having a legal attack
    L = collections.Counter()
    had_legal = {u for (t, u), x in ut.items() if x['legal'] is not None}
    did_att = {u for (t, u), x in ut.items() if x['att']}
    decided = {u for (t, u) in ut}
    for u, tdead in dead_turn.items():
        st = state.get(u)
        if not st or st['f'] != 1:
            continue
        L['dead'] += 1
        if u not in decided:
            L['dead_never_decided'] += 1
        elif u in did_att:
            L['dead_attacked'] += 1
        elif u in had_legal:
            L['dead_had_legal_never_attacked'] += 1
        else:
            L['dead_never_had_target'] += 1
    # 5. examples for case studies: first few of each kind
    Ex = []
    picks = collections.Counter()
    for r in recs:
        if r['side'] != 1:
            continue
        b = r.get('base') or {}
        ex = r.get('_exec') or {}
        s0 = r.get('_st') or {}
        st = r.get('state', {})
        src = b.get('src')
        if src == 'patrol.node' and r['unit'] in eff_u and s0.get('known', 0) > 0 and 0 <= s0.get('near', -1) <= 12 and st.get('tu', 0) > 40 and picks['patrol'] < 2 and r['turn'] >= 2 and ex.get('spent', 0) > 0:
            picks['patrol'] += 1
            Ex.append(dict(kind='patrol_known', battle=battle, rec=r['rec'], turn=r['turn'], unit=r['unit'], type=types.get(r['unit']), w=s0.get('w'), near=s0.get('near'), known=s0.get('known'), tu=st.get('tu'), pos=st.get('pos'), to=b.get('to'), spent=ex.get('spent'), posafter=ex.get('pos'), trail=(ex.get('trail') or [])[:2]))
        if b.get('t') in (7, 8, 9) and ex.get('fdmg', 0) >= 40 and ex.get('dmg', 0) == 0 and picks['ff'] < 2:
            picks['ff'] += 1
            Ex.append(dict(kind='ff', battle=battle, rec=r['rec'], turn=r['turn'], unit=r['unit'], type=types.get(r['unit']), w=b.get('w'), mode=b.get('t'), fdmg=ex.get('fdmg'), fdowned=ex.get('fdowned'), pos=st.get('pos'), to=b.get('to')))
    return dict(battle=battle, C=dict(C), U=dict(U), E={k: v for k, v in E.items()}, Es={k: v for k, v in Es.items()}, L=dict(L), Ex=Ex)


def main():
    out_dir, label, zpath = sys.argv[1:4]
    flt = re.compile(sys.argv[4]) if len(sys.argv) > 4 else None
    z = zipfile.ZipFile(zpath)
    jobs = [(zpath, n) for n in z.namelist() if n.startswith('out/') and n.endswith('openxcom.log.gz') and (not flt or flt.search(n))]
    with mp.Pool(min(6, max(1, len(jobs)))) as pool:
        res = pool.map(analyse, jobs, chunksize=1)
    f = open(os.path.join(out_dir, 'census3_%s.txt' % label), 'w', encoding='utf-8-sig')
    P = lambda *a: print(*a, file=f)
    C = collections.Counter(); U = collections.Counter(); L = collections.Counter()
    E = collections.defaultdict(lambda: [0, 0, 0, 0]); Es = collections.defaultdict(lambda: [0, 0, 0, 0])
    for r in res:
        C.update(r['C']); U.update(r['U']); L.update(r['L'])
        for k, v in r['E'].items():
            for i in range(4):
                E[k][i] += v[i]
        for k, v in r['Es'].items():
            for i in range(4):
                Es[k][i] += v[i]
    P('battles', len(res))
    P('\n== Who can hurt the squad', dict(C))
    P(f"  attack TU by units that never hurt a player unit in the battle: {100*C['attack_tu_units_never_hurt_player']/max(1,C['attack_tu']):.1f}%")
    P(f"  attack TU by weapons that never hurt a player unit in the battle: {100*C['attack_tu_weapons_never_hurt_player']/max(1,C['attack_tu']):.1f}%; attacks {100*C['attacks_weapons_never_hurt_player']/max(1,C['attacks']):.1f}%")
    P('\n== Unit turns: hurter = unit that hurt a player unit at least once in this battle', dict(U))
    for k in ('hurter', 'nonhurter'):
        n = max(1, U[k + '_unit_turns'])
        P(f"  {k}: unit-turns {U[k+'_unit_turns']}, attack {100*U[k+'_attack']/n:.1f}%, legal but no attack {100*U[k+'_legal_no_attack']/n:.1f}%, no target {100*U[k+'_no_target']/n:.1f}% (known {100*U[k+'_no_target_known']/n:.1f}%, known within 15: {100*U[k+'_no_target_known_near15']/n:.1f}%), TU unused on no target {U[k+'_no_target_tu']}")
    P('  legal (side spotted + LOF) no attack, by distance:', {k: v for k, v in sorted(U.items()) if k.startswith('legal_noatt_d')})
    P('  of them own vision at the start of the turn: hurter', U['hurter_legal_own_no_attack'], 'nonhurter', U['nonhurter_legal_own_no_attack'])
    P(f"  upper bound of the 'fire instead of not firing' lever: {U['bound_fire_dmg']} HP against {C['player_dmg_stun']} HP+stun dealt to players by aimed attacks")
    P(f"  own vision lever (one mean attack): no attack + own vision at turn start: {U['bound_own_start']} HP; no attack + own vision at turn end with TU for the cheapest attack: {U['noatt_end_sees_tu_ok']} unit-turns (of {U['noatt_end_sees']} seeing at the end), {U['bound_own_end']} HP; either: {U['noatt_own_any']} unit-turns, {U['bound_own_any']} HP; attacked, still sees and has TU for one more: {U['attacked_end_sees_tu_ok']} unit-turns, {U['bound_own_more']} HP")
    P('  sees at turn end, TU for a ranged attack, did not attack, last decision:', sorted(((k[len('endok_lastsrc_'):], v) for k, v in U.items() if k.startswith('endok_lastsrc_')), key=lambda kv: -kv[1]))
    P('\n== End-of-turn exposure (hostile at player phase start): units, hp, hp lost, dead; loss %, death %')
    for k, v in E.items():
        P(f"  {k:7s} units={v[0]} hp={v[1]} lost={v[2]} dead={v[3]} loss={100*v[2]/max(1,v[1]):.1f}% death={100*v[3]/max(1,v[0]):.1f}%")
    P(' Seen at player phase start, by last own decision: n, lost, dead, lost/unit, death%')
    for k, v in sorted(Es.items(), key=lambda kv: -kv[1][0]):
        P(f"  {k:22s} n={v[0]:6d} lost={v[2]:6d} dead={v[3]:5d} lost/unit={v[2]/max(1,v[0]):6.1f} death={100*v[3]/max(1,v[0]):5.1f}%")
    P('\n== Life and chance of the dead', dict(L))
    P('\n== Per battle: hostiles attacked / hurt players, TU share of useless units, top3 share')
    for r in sorted(res, key=lambda r: r['battle']):
        c = r['C']
        P(r['battle'], 'attacked', c.get('units_attacked'), 'hurt', c.get('units_hurt_player'), 'uselessTU%', round(100 * c.get('attack_tu_units_never_hurt_player', 0) / max(1, c.get('attack_tu', 0))), 'dmg', c.get('player_dmg_stun'), 'top3%', round(c.get('top3_share_x1000', 0) / 10))
    P('\n== Examples')
    for r in res:
        for e in r['Ex']:
            P(json.dumps(e, ensure_ascii=False))
    f.close()
    print('ok', label, len(res))


if __name__ == '__main__':
    main()
