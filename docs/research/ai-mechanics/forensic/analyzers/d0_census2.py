# -*- coding: utf-8 -*-
"""Second pass over archived battle logs: target class, fire mode by distance, target choice, HP flows by phase,
what known-but-unseen units do, walk exposure, zero-TU decisions, explosives, melee, psi, friendly fire.

Usage: py -3 d0_census2.py <out_dir> <label> <zip> [name_filter_regex]
Read-only for the archive.
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

MODE = {6: 'throw', 7: 'auto', 8: 'snap', 9: 'aimed', 10: 'melee', 11: 'psiuse', 12: 'launch', 13: 'mindctl', 14: 'panic', 16: 'cqb'}
RE_STATE = re.compile(r'\[AISTATE\] (\w+) turn=(\d+) unit=(\d+) type=(\S+) faction=(\d+) status=(\d+) pos=\((\d+),(\d+),(\d+)\) dir=(\d+) tu=(-?\d+) hp=(-?\d+)/(\d+) stun=(\d+) morale=(\d+) kneel=(\d) weapon=(\S+) spotted=(-?\d+) sniped=(-?\d+) sees=(\S+) seenby=(\d+) known=(\d+) near=(-?\d+)')
RE_CAS = re.compile(r'\[AICASUALTY\] turn=(\d+) side=(\d+) victim=(\d+) vfaction=(\d+) type=(\S+) how=(\w+) pos=\((\d+),(\d+),(\d+)\) tu=(-?\d+) kneel=(\d) seenby=(\d+) killer=(-?\d+) kfaction=(-?\d+) ktype=(\S+) dist=(-?\d+) weapon=(\S+) hit=(\S+)')
EXPL = re.compile(r'GRENADE|ROCKET|BOMB|MISSILE|MINE|RPG|LAUNCHER|EXPLOS|TNT|DYNAMITE|CHARGE|BAZOOKA|MORTAR|CANNON', re.I)


def bucket(d):
    if d < 0:
        return '?'
    for lim, name in ((3, '00-03'), (6, '04-06'), (10, '07-10'), (15, '11-15'), (20, '16-20'), (30, '21-30')):
        if d <= lim:
            return name
    return '31+'


def analyse(args):
    zpath, member = args
    text = gzip.decompress(zipfile.ZipFile(zpath).read(member)).decode('utf-8', 'replace')
    battle = member.split('/')[1]
    C = collections.Counter()
    tgt = collections.defaultdict(lambda: [0, 0, 0, 0, 0])      # class -> n, eff, dmg, down, tu
    mode_d = collections.defaultdict(lambda: [0, 0, 0, 0, 0])   # (mode, bucket) on player targets
    alt = collections.defaultdict(lambda: [0, 0, 0, 0, 0])      # (auto affordable?, chosen mode, bucket)
    srcd = collections.defaultdict(lambda: [0, 0, 0, 0, 0, 0])  # src -> n, dmg, stun, down, fdmg, tu
    rank = collections.Counter()
    know = collections.defaultdict(collections.Counter)
    walk = collections.defaultdict(lambda: [0, 0, 0, 0, 0, 0])  # src -> n moved, tu, reactions, hp_lost, down, spotted stop
    zero = collections.defaultdict(collections.Counter)
    fw = collections.Counter()
    kw_h = collections.Counter()
    kw_p = collections.Counter()
    ffkill = collections.Counter()
    psi_t = collections.defaultdict(lambda: [0, 0, 0])          # type -> decisions with option, psi chosen, other attack
    phases = {}
    seen_rec = set()
    types = {}
    faction = {}
    last_state = {}
    hp_now = {}
    acts = {}
    recs = []
    expl_events = 0
    cas = {}
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
            if not m:
                continue
            g = m.groups()
            u = int(g[2])
            types[u] = g[3]
            faction[u] = int(g[4])
            hp_now[u] = int(g[11])
            st = dict(kind=g[0], turn=int(g[1]), pos=(int(g[6]), int(g[7]), int(g[8])), tu=int(g[10]), hp=int(g[11]), known=int(g[21]), near=int(g[22]), seenby=int(g[20]), sees=g[19], f=int(g[4]))
            last_state[u] = st
            if g[0] in ('aistart', 'pstart'):
                phases.setdefault((g[0], int(g[1])), {})[u] = (int(g[11]), int(g[4]), int(g[10]))
        elif '[AIREC]' in line:
            try:
                j = json.loads(line[line.index('{'):])
            except Exception:
                continue
            if j['rec'] in seen_rec:
                continue
            seen_rec.add(j['rec'])
            j['_acts'] = acts.pop(j['unit'], [])
            j['_st'] = last_state.get(j['unit'])
            j['_hp'] = dict(hp_now)
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
        elif 'what=explosion' in line:
            expl_events += 1
        elif '[AICASUALTY]' in line:
            m = RE_CAS.search(line)
            if m:
                g = m.groups()
                cas[(g[0], g[1], g[2], g[5])] = dict(side=int(g[1]), vf=int(g[3]), kf=int(g[13]), w=g[16], ktype=g[14], vtype=g[4], how=g[5], dist=int(g[15]))
    for r in recs:
        if r['side'] != 1:
            continue
        b = r.get('base') or {}
        ex = r.get('_exec') or {}
        t = b.get('t')
        src = b.get('src') or 'none'
        spent = ex.get('spent', 0)
        S = srcd[src]
        S[0] += 1
        S[1] += ex.get('dmg', 0)
        S[2] += ex.get('stunned', 0)
        S[3] += ex.get('downed', 0)
        S[4] += ex.get('fdmg', 0)
        S[5] += spent
        st = r.get('state', {})
        tu = st.get('tu', 0)
        pos = st.get('pos')
        chosen = None
        for a in r['_acts']:
            if a.get('id') == b.get('id') and a.get('k') == 'a':
                chosen = a
                break
        # zero TU decisions: why
        if spent == 0:
            tr = ex.get('trail') or []
            key = tr[0].split(' ')[0] if tr else ('noexec' if not ex else ('none' if t in (0, None) else 'notrail'))
            zero[src][key] += 1
        # known without sight
        s0 = r.get('_st') or {}
        sees = s0.get('sees', '-')
        has_seen_enemy = any(x.isdigit() and int(x) < 1000000 for x in sees.split(','))
        if s0:
            k = 'seesEnemy' if has_seen_enemy else ('known' if s0.get('known', 0) > 0 else 'noinfo')
            nb = bucket(s0.get('near', -1)) if k != 'noinfo' else '-'
            know[k + '|' + nb][src] += 1
        # walks
        if t == 2 and ex:
            tr = ex.get('trail') or []
            W = walk[src]
            if spent > 0:
                W[0] += 1
                W[1] += spent
            W[2] += sum(1 for x in tr if x.startswith('walk.stop.reaction'))
            W[3] += ex.get('hp_lost', 0)
            W[4] += ex.get('down', 0) or 0
            W[5] += sum(1 for x in tr if x.startswith('walk.stop.spotted'))
        # psi
        ty = types.get(r['unit'], '?')
        has_psi = any(a.get('k') == 'a' and a.get('t') in (11, 13, 14) and a.get('tu', 9 ** 9) <= tu and a.get('u', 9 ** 9) < 1000000 for a in r['_acts'])
        if has_psi:
            P = psi_t[ty]
            P[0] += 1
            if t in (11, 13, 14):
                P[1] += 1
            elif t in MODE:
                P[2] += 1
        if t not in MODE:
            continue
        # attack accounting
        tuid = chosen.get('u') if chosen else None
        fac = faction.get(tuid, -1) if tuid is not None else -1
        cls = 'player' if (tuid is not None and tuid < 1000000) else ('own' if fac == 1 else ('civ' if fac == 2 else ('pos' if tuid in (None, -1) else 'other')))
        eff = 1 if (ex.get('dmg', 0) > 0 or ex.get('stunned', 0) > 0) else 0
        T = tgt[cls]
        T[0] += 1
        T[1] += eff
        T[2] += ex.get('dmg', 0)
        T[3] += ex.get('downed', 0)
        T[4] += spent
        if ex.get('fdmg', 0) or ex.get('fdowned', 0):
            C['attacks_with_ff'] += 1
            fw[(b.get('w') or '?') + '|' + MODE[t]] += ex.get('fdmg', 0)
        tp = None
        for a in r['_acts']:
            if a.get('id') == b.get('id'):
                tp = a
                break
        to = b.get('to')
        d = -1
        if pos and to and isinstance(to, list):
            d = int(round(math.hypot(pos[0] - to[0], pos[1] - to[1])))
        if cls != 'player':
            continue
        M = mode_d[(MODE[t], bucket(d))]
        M[0] += 1
        M[1] += eff
        M[2] += ex.get('dmg', 0)
        M[3] += ex.get('downed', 0)
        M[4] += spent
        # fire mode: was auto with the same weapon and target affordable?
        if t in (7, 8, 9):
            autos = [a for a in r['_acts'] if a.get('t') == 7 and a.get('w') == b.get('w') and a.get('u') == tuid and a.get('tu', 9 ** 9) <= tu]
            A = alt[('autoOK' if autos else 'noAuto', MODE[t], bucket(d))]
            A[0] += 1
            A[1] += eff
            A[2] += ex.get('dmg', 0)
            A[3] += ex.get('downed', 0)
            A[4] += spent
        # target choice among visible players with a legal attack of the same weapon
        sees_set = set(int(x) for x in sees.split(',') if x.isdigit())
        opts = {}
        for a in r['_acts']:
            if a.get('k') == 'a' and a.get('t') == t and a.get('w') == b.get('w') and a.get('lof') == 1 and a.get('tu', 9 ** 9) <= tu and a.get('u', 9 ** 9) < 1000000 and a.get('u') in sees_set:
                opts[a['u']] = a
        if len(opts) >= 2 and tuid in opts:
            C['target_choice_decisions'] += 1
            ps = sorted((a.get('p', 0) for a in opts.values()), reverse=True)
            ds = sorted(a.get('d', 0) for a in opts.values())
            hps = sorted(r['_hp'].get(u, 9 ** 9) for u in opts)
            if opts[tuid].get('p', 0) >= ps[0]:
                C['picked_best_p'] += 1
            if opts[tuid].get('d', 0) <= ds[0]:
                C['picked_nearest'] += 1
            if r['_hp'].get(tuid, 9 ** 9) <= hps[0]:
                C['picked_lowest_hp'] += 1
            C['sum_p_chosen'] += opts[tuid].get('p', 0)
            C['sum_p_best'] += ps[0]
            C['sum_options'] += len(opts)
    # hp flows by phase
    F = collections.Counter()
    turns = sorted(t for k, t in phases if k == 'aistart')
    for t in turns:
        a = phases.get(('aistart', t), {})
        p0 = phases.get(('pstart', t), {})
        p1 = phases.get(('pstart', t + 1), {})
        for u, (hp, f, tu) in p0.items():
            if u in a or True:
                now = a[u][0] if u in a else 0
                F['f%d_lost_in_player_phase' % f] += max(0, hp - now)
        for u, (hp, f, tu) in a.items():
            if t + 1 in [x for k, x in phases if k == 'pstart']:
                now = p1[u][0] if u in p1 else 0
                F['f%d_lost_in_hostile_phase' % f] += max(0, hp - now)
        for u, (hp, f, tu) in a.items():
            F['f%d_tu_at_aistart' % f] += tu
        for u, (hp, f, tu) in p1.items():
            F['f%d_tu_at_next_pstart' % f] += tu
    for c in cas.values():
        if c['kf'] == 1 and c['vf'] == 0:
            kw_p[c['w']] += 1
        if c['kf'] == 1 and c['vf'] == 1:
            ffkill[c['w']] += 1
        if c['kf'] == 0 and c['vf'] == 1:
            kw_h[c['w']] += 1
    return dict(battle=battle, C=dict(C), tgt=dict(tgt), mode_d={'|'.join(k): v for k, v in mode_d.items()}, alt={'|'.join(k): v for k, v in alt.items()}, srcd=dict(srcd), know={k: dict(v) for k, v in know.items()}, walk=dict(walk), zero={k: dict(v) for k, v in zero.items()}, fw=dict(fw), kw_p=dict(kw_p), kw_h=dict(kw_h), ffkill=dict(ffkill), psi_t=dict(psi_t), F=dict(F), expl=expl_events)


def main():
    out_dir, label, zpath = sys.argv[1:4]
    flt = re.compile(sys.argv[4]) if len(sys.argv) > 4 else None
    z = zipfile.ZipFile(zpath)
    jobs = [(zpath, n) for n in z.namelist() if n.startswith('out/') and n.endswith('openxcom.log.gz') and (not flt or flt.search(n))]
    with mp.Pool(min(6, max(1, len(jobs)))) as pool:
        res = pool.map(analyse, jobs, chunksize=1)
    T = collections.defaultdict(lambda: collections.defaultdict(lambda: None))
    def merge_list(name):
        d = {}
        for r in res:
            for k, v in r[name].items():
                if k not in d:
                    d[k] = list(v)
                else:
                    d[k] = [a + b for a, b in zip(d[k], v)]
        return d
    def merge_cnt(name):
        c = collections.Counter()
        for r in res:
            c.update(r[name])
        return c
    def merge_nested(name):
        d = collections.defaultdict(collections.Counter)
        for r in res:
            for k, v in r[name].items():
                d[k].update(v)
        return d
    f = open(os.path.join(out_dir, 'census2_%s.txt' % label), 'w', encoding='utf-8-sig')
    def P(*a):
        print(*a, file=f)
    P('battles', len(res))
    P('\n== Attacks by target class: n, %effect, dmg, downed, TU')
    for k, v in sorted(merge_list('tgt').items(), key=lambda kv: -kv[1][0]):
        P(f'{k:8s} n={v[0]:6d} eff={100*v[1]/max(1,v[0]):5.1f}% dmg={v[2]:7d} down={v[3]:5d} tu={v[4]:7d}')
    P('\n== Mode by distance, player targets: n, %effect, dmg/attack, down/100attacks, TU/attack, dmg/100TU, down/1000TU')
    md = merge_list('mode_d')
    for k in sorted(md):
        v = md[k]
        P(f'{k:16s} n={v[0]:5d} eff={100*v[1]/max(1,v[0]):5.1f}% d/a={v[2]/max(1,v[0]):6.2f} down%={100*v[3]/max(1,v[0]):5.1f} tu/a={v[4]/max(1,v[0]):5.1f} d/100tu={100*v[2]/max(1,v[4]):6.2f} down/1000tu={1000*v[3]/max(1,v[4]):5.2f}')
    P('\n== Fire mode when auto with the same weapon and target was/was not affordable')
    al = merge_list('alt')
    for k in sorted(al):
        v = al[k]
        P(f'{k:26s} n={v[0]:5d} eff={100*v[1]/max(1,v[0]):5.1f}% d/a={v[2]/max(1,v[0]):6.2f} tu/a={v[4]/max(1,v[0]):5.1f} d/100tu={100*v[2]/max(1,v[4]):6.2f}')
    P('\n== Result by decision source: n, dmg, stun, down, friendly dmg, TU, dmg/100TU, down/1000TU')
    for k, v in sorted(merge_list('srcd').items(), key=lambda kv: -kv[1][0]):
        P(f'{k:22s} n={v[0]:6d} dmg={v[1]:7d} stun={v[2]:6d} down={v[3]:5d} fdmg={v[4]:6d} tu={v[5]:7d} d/100={100*v[1]/max(1,v[5]):6.2f} dn/1000={1000*v[3]/max(1,v[5]):5.2f}')
    C = merge_cnt('C')
    P('\n== Target choice among 2+ visible legal player targets with the chosen weapon and mode', dict(C))
    n = max(1, C['target_choice_decisions'])
    P(f"  picked best p {100*C['picked_best_p']/n:.1f}%, nearest {100*C['picked_nearest']/n:.1f}%, lowest hp {100*C['picked_lowest_hp']/n:.1f}%, mean p chosen {C['sum_p_chosen']/n:.1f} vs best {C['sum_p_best']/n:.1f}, mean options {C['sum_options']/n:.2f}")
    P('\n== What does a unit do by information state (near bucket): top sources in %')
    kn = merge_nested('know')
    tot = collections.Counter()
    for k in sorted(kn):
        v = kn[k]
        s = sum(v.values())
        tot[k.split('|')[0]] += s
        P(f'{k:18s} n={s:6d} ' + ' '.join(f'{a}={100*b/s:.0f}%' for a, b in v.most_common(6)))
    P('  totals', dict(tot))
    P('\n== Walk exposure: moved n, TU, reaction stops, hp lost, downs, spotted stops, hp lost/100TU, downs/1000TU')
    for k, v in sorted(merge_list('walk').items(), key=lambda kv: -kv[1][1]):
        P(f'{k:22s} n={v[0]:6d} tu={v[1]:7d} react={v[2]:5d} hp={v[3]:6d} down={v[4]:4d} spot={v[5]:5d} hp/100={100*v[3]/max(1,v[1]):5.2f} dn/1000={1000*v[4]/max(1,v[1]):5.2f}')
    P('\n== Zero-TU decisions: reason')
    for k, v in sorted(merge_nested('zero').items(), key=lambda kv: -sum(kv[1].values())):
        P(k, dict(v.most_common(6)))
    P('\n== HP/TU flows', dict(merge_cnt('F')))
    P('\n== hostile killers of player: weapon', merge_cnt('kw_p').most_common(40))
    P('\n== hostile killing hostile: weapon', merge_cnt('ffkill').most_common(25))
    P('\n== FF dmg by weapon|mode', merge_cnt('fw').most_common(25))
    P('\n== explosion events', sum(r['expl'] for r in res), 'attacks with FF', C['attacks_with_ff'])
    P('\n== Psi by type: decisions with option, psi chosen, other attack chosen')
    for k, v in sorted(merge_list('psi_t').items(), key=lambda kv: -kv[1][0])[:25]:
        P(f'{k:36s} {v[0]:5d} {v[1]:4d} {v[2]:4d}')
    f.close()
    print('ok', label, len(res))


if __name__ == '__main__':
    main()
