# -*- coding: utf-8 -*-
"""Read-only census of hostile-side behaviour from archived battle logs ([AIREC]/[AIEXEC]/[AICAND]/[AIDECIDE]/[AISTATE]/[AICASUALTY]).

Usage: py -3 d0_census.py <out_dir> <label> <zip> [name_filter_regex]
Reads zip members out/<battle>/openxcom.log.gz and arena/<battle>.tsv; writes nothing next to the archive.
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

ATTACK_T = {6: 'throw', 7: 'auto', 8: 'snap', 9: 'aimed', 10: 'melee', 11: 'psiuse', 12: 'launch', 13: 'mindctl', 14: 'panic', 16: 'cqb'}
RANGED = {6, 7, 8, 9, 12}
PSI = {11, 13, 14}
RE_STATE = re.compile(r'\[AISTATE\] (\w+) turn=(\d+) unit=(\d+) type=(\S+) faction=(\d+) status=(\d+) pos=\((\d+),(\d+),(\d+)\) dir=(\d+) tu=(-?\d+) hp=(-?\d+)/(\d+) stun=(\d+) morale=(\d+) kneel=(\d) weapon=(\S+) spotted=(-?\d+) sniped=(-?\d+) sees=(\S+) seenby=(\d+) known=(\d+) near=(-?\d+) shade=(-?\d+) tumax=(\d+)')
RE_CAS = re.compile(r'\[AICASUALTY\] turn=(\d+) side=(\d+) victim=(\d+) vfaction=(\d+) type=(\S+) how=(\w+) pos=\((\d+),(\d+),(\d+)\) tu=(-?\d+) kneel=(\d) seenby=(\d+) killer=(-?\d+) kfaction=(-?\d+) ktype=(\S+) dist=(-?\d+) weapon=(\S+) hit=(\S+) terrain=(\d)')
RE_DEC = re.compile(r'\[AIDECIDE\] turn=(\d+) side=(\d+) unit=(\d+) n=(-?\d+) .*? seen=(\S*)')
RE_REACT = re.compile(r'\[AIEVENT\] turn=(\d+) side=(\d+) what=reaction unit=(\d+)')
RE_TRAIL = re.compile(r'^([a-z.]+)')


def dist2(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def analyse(args):
    zpath, member, tsvname = args
    z = zipfile.ZipFile(zpath)
    text = gzip.decompress(z.read(member)).decode('utf-8', 'replace')
    battle = member.split('/')[1]
    meta = {}
    try:
        t = z.read(tsvname).decode('utf-8-sig').split('\n')
        meta = dict(zip(t[0].rstrip('\r').split('\t'), t[1].rstrip('\r').split('\t')))
    except Exception:
        pass
    recs = {}
    order = []
    acts = {}
    types = {}
    tumax = {}
    faction = {}
    cas = []
    decides = []
    react = collections.Counter()
    snaps = collections.defaultdict(dict)   # turn -> unit -> (pos, hp, tu, faction, sees)
    seen_rec = set()
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
        elif '[AIDECIDE]' in line:
            m = RE_DEC.search(line)
            if m:
                decides.append((int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)), m.group(5)))
        elif '[AIREC]' in line:
            try:
                j = json.loads(line[line.index('{'):])
            except Exception:
                continue
            if j['rec'] in seen_rec:
                continue
            seen_rec.add(j['rec'])
            j['_acts'] = acts.pop(j['unit'], [])
            recs[j['rec']] = j
            order.append(j['rec'])
        elif '[AIEXEC]' in line:
            try:
                j = json.loads(line[line.index('{'):])
            except Exception:
                continue
            if j['rec'] in recs:
                recs[j['rec']]['_exec'] = j
        elif '[AISTATE]' in line:
            m = RE_STATE.search(line)
            if m:
                g = m.groups()
                u = int(g[2])
                types[u] = g[3]
                tumax[u] = int(g[24])
                faction[u] = int(g[4])
                if g[0] == 'aistart':
                    snaps[int(g[1])][u] = dict(pos=(int(g[6]), int(g[7]), int(g[8])), hp=int(g[11]), hpmax=int(g[12]), tu=int(g[10]), f=int(g[4]), near=int(g[22]), known=int(g[21]), seenby=int(g[20]), morale=int(g[14]), stun=int(g[13]), weapon=g[16])
        elif '[AICASUALTY]' in line:
            m = RE_CAS.search(line)
            if m:
                g = m.groups()
                key = (g[0], g[1], g[2], g[5])
                cas.append(dict(turn=int(g[0]), side=int(g[1]), victim=int(g[2]), vf=int(g[3]), type=g[4], how=g[5], tu=int(g[9]), kneel=int(g[10]), seenby=int(g[11]), killer=int(g[12]), kf=int(g[13]), ktype=g[14], dist=int(g[15]), weapon=g[16], hit=g[17], terrain=int(g[18]), key=key))
        elif 'what=reaction' in line:
            m = RE_REACT.search(line)
            if m:
                react[(int(m.group(2)), faction.get(int(m.group(3)), -1))] += 1
    # dedupe casualties
    cs = {}
    for c in cas:
        cs[c['key']] = c
    cas = list(cs.values())
    # pair decide lines
    seen_of = {}
    dec_idx = 0
    for rid in order:
        r = recs[rid]
        if dec_idx < len(decides):
            d = decides[dec_idx]
            if d[2] == r['unit'] and d[0] == r['turn']:
                seen_of[rid] = set(int(x) for x in d[4].split(',') if x.isdigit())
                dec_idx += 1
            else:
                # resync
                for k in range(dec_idx, min(dec_idx + 6, len(decides))):
                    if decides[k][2] == r['unit'] and decides[k][0] == r['turn']:
                        seen_of[rid] = set(int(x) for x in decides[k][4].split(',') if x.isdigit())
                        dec_idx = k + 1
                        break

    out = dict(battle=battle, meta=meta)
    C = collections.Counter()
    src_tu = collections.Counter()
    src_n = collections.Counter()
    src_zero = collections.Counter()
    legal_vs = collections.Counter()
    legal_tu = collections.Counter()
    weap = collections.defaultdict(lambda: [0, 0.0, 0, 0, 0, 0])  # n, sum_p, n_dmg, sum_dmg, n_down, sum_tu
    ttype = collections.defaultdict(lambda: [0, 0, 0, 0, 0, 0, 0])  # n, n_dmg, sum_dmg, n_down, tu, stun, fdmg
    trail = collections.Counter()
    unit = collections.defaultdict(lambda: dict(dec=0, att=0, dmg=0, down=0, stun=0, fdmg=0, tu=0, attTu=0, turns=set(), seen=0, firstatt=None))
    uturn = {}
    move = collections.defaultdict(lambda: [0, 0, 0, 0.0])  # src -> closer, farther, same, sumdelta
    hpband = collections.defaultdict(collections.Counter)
    mode_odds = collections.Counter()
    psi_av = collections.Counter()
    gren_av = collections.Counter()
    multiw = collections.Counter()
    tgt_turn = collections.defaultdict(collections.Counter)
    first_att = None
    first_h_cas = None
    first_p_cas = None
    for rid in order:
        r = recs[rid]
        if r['side'] != 1:
            continue
        ex = r.get('_exec')
        b = r.get('base') or {}
        src = b.get('src') or ('none' if b.get('t') in (0, None) else 'other')
        t = b.get('t')
        st = r.get('state', {})
        tu = st.get('tu', 0)
        u = r['unit']
        if faction.get(u, 1) != 1:
            pass
        spent = ex.get('spent', 0) if ex else 0
        C['decisions'] += 1
        src_n[src] += 1
        src_tu[src] += spent
        if spent == 0:
            src_zero[src] += 1
        U = unit[u]
        U['dec'] += 1
        U['tu'] += spent
        U['turns'].add(r['turn'])
        key = (r['turn'], u)
        ut = uturn.setdefault(key, dict(tu0=tu, tuL=tu, att=0, legal=False, legal0=False, dec=0, attT=0, walkT=0, otherT=0, srcs=[], dmg=0))
        ut['dec'] += 1
        ut['srcs'].append(src)
        if ex:
            ut['tuL'] = ex.get('tu', ut['tuL'])
        seen = seen_of.get(rid, set())
        # legal options at this decision
        legal = []
        psi = 0
        gren = 0
        wset = set()
        for a in r['_acts']:
            if a.get('k') != 'a':
                continue
            at = a.get('t')
            if a.get('u', 9 ** 9) >= 1000000:
                continue
            if a.get('tu', 9 ** 9) > tu:
                continue
            if at in PSI:
                psi += 1
                continue
            if at == 6 and a.get('lof') == 1 and a.get('u') in seen:
                gren += 1
            if a.get('lof') == 1 and a.get('u') in seen and at in (RANGED | {10}):
                legal.append(a)
                if at in (7, 8, 9):
                    wset.add(a.get('w'))
        is_attack = t in ATTACK_T
        if psi:
            psi_av['decisions_with_psi_option'] += 1
            if t in PSI:
                psi_av['psi_chosen'] += 1
            elif is_attack:
                psi_av['other_attack_chosen'] += 1
            else:
                psi_av['no_attack_chosen'] += 1
        if gren:
            gren_av['decisions_with_grenade_lof'] += 1
            if t == 6:
                gren_av['throw_chosen'] += 1
        if len(wset) >= 2:
            multiw['decisions_with_2plus_firearms'] += 1
        if legal:
            C['decisions_with_legal_attack_on_visible_player'] += 1
            ut['legal'] = True
            if ut['dec'] == 1:
                ut['legal0'] = True
            legal_vs[src] += 1
            legal_tu[src] += spent
            od = (b.get('reason') or {}).get('odds') or []
            if od:
                o = od[-1]
                tot = max(1, o.get('p', 0) + o.get('a', 0) + o.get('c', 0) + o.get('e', 0))
                mode_odds['n'] += 1
                mode_odds['sum_c'] += o.get('c', 0) / tot
                mode_odds['sum_p'] += o.get('p', 0) / tot
                mode_odds['sum_a'] += o.get('a', 0) / tot
                mode_odds['sum_e'] += o.get('e', 0) / tot
                mode_odds['rolled_%d' % o.get('mode', -1)] += 1
        hp = st.get('hp', 0)
        hpm = (snaps.get(r['turn'], {}).get(u) or {}).get('hpmax') or 0
        band = 'hp?' if not hpm else ('hp<33' if hp * 3 < hpm else ('hp<66' if hp * 3 < 2 * hpm else 'hp>=66'))
        hpband[band][src] += 1
        if is_attack:
            if first_att is None:
                first_att = r['turn']
            ut['att'] += 1
            U['att'] += 1
            U['attTu'] += spent
            ut['attT'] += spent
            if U['firstatt'] is None:
                U['firstatt'] = r['turn']
            w = weap[(b.get('w') or '?', ATTACK_T[t])]
            w[0] += 1
            p = 0
            for a in r['_acts']:
                if a.get('k') == 'a' and a.get('t') == t and a.get('w') == b.get('w') and a.get('to') == b.get('to'):
                    p = a.get('p', 0)
                    break
            w[1] += p
            w[5] += spent
            T = ttype[ATTACK_T[t]]
            T[0] += 1
            T[4] += spent
            if ex:
                dmg = ex.get('dmg', 0)
                stun = ex.get('stunned', 0)
                U['dmg'] += dmg
                U['stun'] += stun
                U['down'] += ex.get('downed', 0)
                U['fdmg'] += ex.get('fdmg', 0)
                ut['dmg'] += dmg
                if dmg > 0 or stun > 0:
                    w[2] += 1
                    T[1] += 1
                w[3] += dmg
                T[2] += dmg
                T[5] += stun
                T[6] += ex.get('fdmg', 0)
                if ex.get('downed', 0):
                    w[4] += 1
                    T[3] += 1
                C['fdmg'] += ex.get('fdmg', 0)
                C['fdowned'] += ex.get('fdowned', 0)
            if b.get('to') and isinstance(b['to'], list):
                tgt_turn[r['turn']][tuple(b['to'])] += 1
        else:
            if t == 2:
                ut['walkT'] += spent
            else:
                ut['otherT'] += spent
            # did the walk close the distance to the nearest player unit as it stood at the turn's start?
            snap = snaps.get(r['turn'], {})
            pl = [s['pos'] for k, s in snap.items() if s['f'] == 0 and k < 1000000]
            if t == 2 and ex and pl and st.get('pos') and ex.get('pos'):
                d0 = min(dist2(st['pos'], p) for p in pl)
                d1 = min(dist2(ex['pos'], p) for p in pl)
                M = move[src]
                if d1 < d0 - 0.5:
                    M[0] += 1
                elif d1 > d0 + 0.5:
                    M[1] += 1
                else:
                    M[2] += 1
                M[3] += d1 - d0
        if ex:
            for tr in ex.get('trail') or []:
                m = RE_TRAIL.match(tr)
                if m:
                    trail[m.group(1)] += 1
            if ex.get('down'):
                C['died_during_own_decision'] += 1
                C['died_during_own_' + ('walk' if t == 2 else ('attack' if is_attack else 'other'))] += 1
            if ex.get('hp_lost', 0) > 0:
                C['hp_lost_during_own_decision'] += ex.get('hp_lost', 0)
    # unit-turn roll up
    UT = collections.Counter()
    for (turn, u), x in uturn.items():
        UT['unit_turns'] += 1
        UT['tu0'] += x['tu0']
        UT['tuLeft'] += max(0, x['tuL'])
        UT['tuAttack'] += x['attT']
        UT['tuWalk'] += x['walkT']
        UT['tuOther'] += x['otherT']
        if x['att']:
            UT['unit_turns_with_attack'] += 1
        if x['legal']:
            UT['unit_turns_with_legal_attack'] += 1
            if not x['att']:
                UT['unit_turns_legal_but_no_attack'] += 1
                UT['tuLeft_legal_no_attack'] += max(0, x['tuL'])
        if x['legal0']:
            UT['unit_turns_legal_at_first_decision'] += 1
            if not x['att']:
                UT['unit_turns_legal_first_no_attack'] += 1
    # army geometry per turn
    geom = {}
    for turn, snap in snaps.items():
        pl = [s['pos'] for k, s in snap.items() if s['f'] == 0 and k < 1000000 and s['hp'] > 0]
        ho = [s for k, s in snap.items() if s['f'] == 1 and s['hp'] > 0]
        if not pl or not ho:
            continue
        ds = sorted(min(dist2(h['pos'], p) for p in pl) for h in ho)
        geom[turn] = dict(n=len(ds), mean=sum(ds) / len(ds), le10=sum(1 for d in ds if d <= 10), le20=sum(1 for d in ds if d <= 20), seenby=sum(1 for h in ho if h['seenby'] > 0), known=sum(1 for h in ho if h['known'] > 0), pl=len(pl))
    # casualties
    K = collections.Counter()
    kw = collections.Counter()
    pkw = collections.Counter()
    distb = collections.Counter()
    tuleft = [0, 0]
    pdmg_type = collections.Counter()
    for c in cas:
        if c['vf'] == 1 or (c['victim'] >= 1000000 and c['type'] and faction.get(c['victim']) == 1):
            K['hostile_%s' % c['how']] += 1
            K['hostile_%s_side%d' % (c['how'], c['side'])] += 1
            K['hostile_by_f%d' % c['kf']] += 1
            if first_h_cas is None or c['turn'] < first_h_cas:
                first_h_cas = c['turn']
            if c['kf'] == 0:
                kw[c['weapon']] += 1
            if c['dist'] >= 0:
                distb[min(c['dist'] // 5 * 5, 40)] += 1
            mx = tumax.get(c['victim'], 0)
            if mx:
                tuleft[0] += c['tu']
                tuleft[1] += mx
            if c['turn'] == 1 and c['side'] == 0:
                K['hostile_down_before_first_ai_turn'] += 1
            K['hostile_hit_' + c['hit']] += 1
            if c['seenby'] == 0:
                K['hostile_down_unseen'] += 1
        elif c['vf'] == 0:
            K['player_%s' % c['how']] += 1
            K['player_%s_side%d' % (c['how'], c['side'])] += 1
            K['player_by_f%d' % c['kf']] += 1
            if first_p_cas is None or c['turn'] < first_p_cas:
                first_p_cas = c['turn']
            pkw[(c['ktype'], c['weapon'])] += 1
        else:
            K['civ_%s' % c['how']] += 1
            K['civ_by_f%d' % c['kf']] += 1
    # participation
    hostile_units = [u for u, f in faction.items() if f == 1]
    Pz = collections.Counter()
    typ = collections.defaultdict(lambda: [0, 0, 0, 0, 0, 0, 0])  # units, dec, att, dmg, down, dead, stunned
    dead = {c['victim'] for c in cas if c['vf'] == 1}
    dmgs = []
    for u in hostile_units:
        U = unit.get(u)
        ty = types.get(u, '?')
        T = typ[ty]
        T[0] += 1
        Pz['hostiles'] += 1
        if u in dead:
            T[5] += 1
        if not U:
            Pz['never_decided'] += 1
            dmgs.append(0)
            continue
        T[1] += U['dec']
        T[2] += U['att']
        T[3] += U['dmg']
        T[4] += U['down']
        dmgs.append(U['dmg'] + U['stun'])
        if U['att'] == 0:
            Pz['never_attacked'] += 1
            if u in dead:
                Pz['died_never_attacked'] += 1
        if U['dmg'] + U['stun'] == 0:
            Pz['never_damaged'] += 1
    dmgs.sort(reverse=True)
    tot = sum(dmgs) or 1
    top10 = max(1, len(dmgs) // 10)
    Pz['dmg_total'] = sum(dmgs)
    Pz['dmg_top10pct'] = sum(dmgs[:top10])
    # focus: how many distinct targets per side turn, among turns with 2+ attacks
    F = collections.Counter()
    for turn, ct in tgt_turn.items():
        n = sum(ct.values())
        if n >= 2:
            F['turns'] += 1
            F['attacks'] += n
            F['targets'] += len(ct)
    out.update(C=dict(C), src_n=dict(src_n), src_tu=dict(src_tu), src_zero=dict(src_zero), legal_vs=dict(legal_vs), legal_tu=dict(legal_tu),
               weap={'|'.join(k): v for k, v in weap.items()}, ttype={k: v for k, v in ttype.items()}, trail=dict(trail), UT=dict(UT),
               move={k: v for k, v in move.items()}, hpband={k: dict(v) for k, v in hpband.items()}, mode_odds=dict(mode_odds), psi=dict(psi_av), gren=dict(gren_av), multiw=dict(multiw),
               K=dict(K), kw=dict(kw), pkw={'|'.join(k): v for k, v in pkw.items()}, distb={str(k): v for k, v in distb.items()}, tuleft=tuleft, Pz=dict(Pz),
               typ={k: v for k, v in typ.items()}, F=dict(F), geom={str(k): v for k, v in geom.items()}, react={'%d|%d' % k: v for k, v in react.items()},
               first_att=first_att, first_h_cas=first_h_cas, first_p_cas=first_p_cas)
    return out


def main():
    out_dir, label, zpath = sys.argv[1:4]
    flt = re.compile(sys.argv[4]) if len(sys.argv) > 4 else None
    os.makedirs(out_dir, exist_ok=True)
    z = zipfile.ZipFile(zpath)
    names = z.namelist()
    jobs = []
    for n in names:
        if n.startswith('out/') and n.endswith('openxcom.log.gz'):
            b = n.split('/')[1]
            if flt and not flt.search(b):
                continue
            jobs.append((zpath, n, 'arena/%s.tsv' % b))
    with mp.Pool(min(6, max(1, len(jobs)))) as pool:
        res = pool.map(analyse, jobs, chunksize=1)
    with open(os.path.join(out_dir, 'census_%s.json' % label), 'w', encoding='utf-8-sig') as f:
        json.dump(res, f, ensure_ascii=False)
    print(label, len(res), 'battles')


if __name__ == '__main__':
    main()
