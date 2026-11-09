# -*- coding: utf-8 -*-
"""Report for debate1_causal.py. Usage: py -3 debate1_causal_report.py <data_dir> <label>"""
import collections
import json
import os
import random
import re
import sys

data_dir, label = sys.argv[1:3]
res = json.load(open(os.path.join(data_dir, 'debate1_causal_%s.json' % label), encoding='utf-8-sig'))


def scn(b):
    m = re.search(r'_([LM]\d+)_s\d+', b)
    return m.group(1) if m else b


OUT = ('died_walk', 'seen', 'died', 'lost', 'att1', 'lof1', 'dmg1', 'att2', 'dmg2')
BAL = ('hpf', 'tu', 'prevseen', 'sc', 'spent')


def effect(rs, key, sel=lambda r: True, thr=3):
    """Stratified difference closer minus farther: strata battle x start distance x weapon class, weights n_c n_f / (n_c + n_f)."""
    S = collections.defaultdict(lambda: [[], []])
    for b in rs:
        for r in b['rows']:
            if not sel(r):
                continue
            k = (b['battle'], r['d0b'], r['wc'])
            if r['delta'] <= -thr:
                S[k][0].append(r[key])
            elif r['delta'] >= thr:
                S[k][1].append(r[key])
    num = den = 0.0
    nc = nf = 0
    mc = mf = 0.0
    for k, (c, f) in S.items():
        if not c or not f:
            continue
        w = len(c) * len(f) / (len(c) + len(f))
        a = sum(c) / len(c)
        d = sum(f) / len(f)
        num += w * (a - d)
        den += w
        mc += w * a
        mf += w * d
        nc += len(c)
        nf += len(f)
    if not den:
        return None
    return dict(eff=num / den, c=mc / den, f=mf / den, nc=nc, nf=nf)


def boot(rs, f, B=1000):
    by = collections.defaultdict(list)
    for r in rs:
        by[scn(r['battle'])].append(r)
    keys = sorted(by)
    rnd = random.Random(20261107)
    vals = []
    for _ in range(B):
        pick = []
        for _k in keys:
            pick += by[rnd.choice(keys)]
        v = f(pick)
        if v is not None:
            vals.append(v)
    vals.sort()
    if not vals:
        return (None, None)
    return round(vals[int(0.025 * len(vals))], 3), round(vals[int(0.975 * len(vals))], 3)


print('== Rows', sum(len(b['rows']) for b in res))
d = collections.Counter()
for b in res:
    for r in b['rows']:
        d['closer' if r['delta'] <= -3 else 'farther' if r['delta'] >= 3 else 'same'] += 1
print(' delta groups (|delta|>=3)', dict(d))
print('\n== Balance before the move (should be about zero)')
for key in BAL:
    e = effect(res, key)
    print(' %-9s closer %8.3f farther %8.3f diff %7.3f' % (key, e['c'], e['f'], e['eff']))
for name, sel in (('ALL', lambda r: True), ('proven', lambda r: r['wc'] == 'proven'), ('weak', lambda r: r['wc'] == 'weak'), ('melee', lambda r: r['wc'] == 'melee'), ('unknown', lambda r: r['wc'] == 'unknown'), ('proven start<=25', lambda r: r['wc'] == 'proven' and r['sc'] <= 25), ('turn<=3', lambda r: r['t'] <= 3)):
    print('\n== Outcomes, closer minus farther:', name)
    for key in OUT:
        e = effect(res, key, sel)
        if not e:
            print(' no strata')
            break
        ci = boot(res, lambda rs: (effect(rs, key, sel) or {}).get('eff'))
        print(' %-9s closer %7.3f farther %7.3f diff %7.3f CI %s n %d/%d' % (key, e['c'], e['f'], e['eff'], ci, e['nc'], e['nf']))
noM1 = [b for b in res if scn(b['battle']) != 'M1']
print('\n== Without M1, proven')
for key in OUT:
    e = effect(noM1, key, lambda r: r['wc'] == 'proven')
    print(' %-9s closer %7.3f farther %7.3f diff %7.3f n %d/%d' % (key, e['c'], e['f'], e['eff'], e['nc'], e['nf']))


# ---------- exposure
def mh(rs, strat, outcome='dead'):
    S = collections.defaultdict(lambda: [0, 0, 0, 0, 0, 0])  # n1, a1, n0, a0, lost1, lost0
    for b in rs:
        for e in b['expo']:
            k = strat(b, e)
            X = S[k]
            if e['seen']:
                X[0] += 1
                X[1] += e[outcome]
            else:
                X[2] += 1
                X[3] += e[outcome]
    num = den = 0.0
    a1 = n1 = a0 = n0 = 0
    rd_num = rd_den = 0.0
    for k, (x1, y1, x0, y0, _, _) in S.items():
        if not x1 or not x0:
            continue
        t = x1 + x0
        num += y1 * x0 / t
        den += y0 * x1 / t
        a1 += y1
        n1 += x1
        a0 += y0
        n0 += x0
        w = x1 * x0 / t
        rd_num += w * (y1 / x1 - y0 / x0)
        rd_den += w
    return dict(rr=num / den if den else None, rd=rd_num / rd_den if rd_den else None, a1=a1, n1=n1, a0=a0, n0=n0)


print('\n== Exposure at the start of the player phase: risk of death, seen against unseen')
base = mh(res, lambda b, e: 0)
print(' crude rr %.2f rd %.3f  seen %d/%d = %.1f%% unseen %d/%d = %.1f%%' % (base['rr'], base['rd'], base['a1'], base['n1'], 100 * base['a1'] / base['n1'], base['a0'], base['n0'], 100 * base['a0'] / base['n0']))
for name, st in (('battle', lambda b, e: b['battle']),
                 ('distance', lambda b, e: e['db']),
                 ('type', lambda b, e: e['type']),
                 ('battle x distance', lambda b, e: (b['battle'], e['db'])),
                 ('battle x type', lambda b, e: (b['battle'], e['type'])),
                 ('battle x type x distance', lambda b, e: (b['battle'], e['type'], e['db'])),
                 ('battle x type x distance x hp', lambda b, e: (b['battle'], e['type'], e['db'], e['hpb'])),
                 ('battle x turn x distance', lambda b, e: (b['battle'], e['t'], e['db']))):
    m = mh(res, st)
    ci = boot(res, lambda rs: mh(rs, st)['rr'], B=300)
    print(' %-32s rr %.2f CI %s rd %+.3f  (kept seen %d/%d, unseen %d/%d)' % (name, m['rr'], ci, m['rd'], m['a1'], m['n1'], m['a0'], m['n0']))
print(' by distance bucket (crude within bucket):')
T = collections.defaultdict(lambda: [0, 0, 0, 0])
for b in res:
    for e in b['expo']:
        X = T[e['db']]
        if e['seen']:
            X[0] += 1
            X[1] += e['dead']
        else:
            X[2] += 1
            X[3] += e['dead']
for k in sorted(T):
    v = T[k]
    print('  %-6s seen %5d dead %4d = %5.1f%%   unseen %5d dead %4d = %5.1f%%' % (k, v[0], v[1], 100 * v[1] / max(1, v[0]), v[2], v[3], 100 * v[3] / max(1, v[2])))
print(' share of all units and of deaths by distance:')
tot = sum(v[0] + v[2] for v in T.values())
td = sum(v[1] + v[3] for v in T.values())
for k in sorted(T):
    v = T[k]
    print('  %-6s units %5.1f%% deaths %5.1f%%' % (k, 100 * (v[0] + v[2]) / tot, 100 * (v[1] + v[3]) / td))
print('\n== Saturation: per player phase, by number of seen hostiles V')
P = collections.defaultdict(lambda: [0, 0, 0, 0, 0])
for b in res:
    for p in b['phase']:
        k = '0' if p['V'] == 0 else '1' if p['V'] == 1 else '2' if p['V'] == 2 else '3-4' if p['V'] <= 4 else '5-8' if p['V'] <= 8 else '9+'
        X = P[k]
        X[0] += 1
        X[1] += p['V']
        X[2] += p['dead_seen']
        X[3] += p['dead_unseen']
        X[4] += p['N']
for k in ('0', '1', '2', '3-4', '5-8', '9+'):
    v = P[k]
    if v[0]:
        print(' V %-4s phases %5d  mean N %5.1f  deaths/phase seen %5.2f unseen %5.2f  death rate of a seen unit %5.1f%%' % (k, v[0], v[4] / v[0], v[2] / v[0], v[3] / v[0], 100 * v[2] / max(1, v[1])))
K = collections.Counter()
for b in res:
    K.update(b['K'])
print('\n== Hostile deaths by phase and killer faction:', sorted(K.items()))


# ---------- friendly fire
def ffcat(f):
    if not f['att']:
        return 'not_attack_window'
    if f['react'] > 0 and f['nexpl'] == 0:
        return 'attack_with_reaction_no_expl'
    if f['cexpl'] >= 3:
        return 'attack_chain_3plus_centres'
    if f['nexpl'] > 0:
        return 'attack_explosion_1_2_centres'
    return 'attack_direct_no_explosion'


FF = []
for b in res:
    for f in b['ff']:
        f2 = dict(f)
        f2['battle'] = b['battle']
        FF.append(f2)
tot = sum(f['fdmg'] for f in FF)
print('\n== Own-side HP lost inside a hostile action window: total', tot, 'windows', len(FF))
C = collections.defaultdict(lambda: [0, 0, 0, 0, 0, 0, 0])
for f in FF:
    X = C[ffcat(f)]
    X[0] += 1
    X[1] += f['fdmg']
    X[2] += f['fdown']
    X[3] += f['dmg']
    X[4] += f['cas_own']
    X[5] += f['cas_kf_own']
    X[6] += f['cas_kf_player']
for k, v in sorted(C.items(), key=lambda kv: -kv[1][1]):
    print(' %-32s windows %4d fdmg %6d (%5.1f%%) fdowned %4d dmg on players %6d own dead %4d (killer own %4d, killer player %4d)' % (k, v[0], v[1], 100 * v[1] / tot, v[2], v[3], v[4], v[5], v[6]))
print(' top single windows:')
for f in sorted(FF, key=lambda f: -f['fdmg'])[:12]:
    print('  %-22s rec %5d turn %2d %-26s t=%s fdmg %5d down %3d dmg %4d centres %3d react %d own dead %3d terrain %3d' % (f['battle'], f['rec'], f['turn'], f['w'], f['t'], f['fdmg'], f['fdown'], f['dmg'], f['cexpl'], f['react'], f['cas_own'], f['cas_own_terrain']))
s = sorted((f['fdmg'] for f in FF if f['att']), reverse=True)
sa = sum(s)
print(' attack windows only: total %d, top1 %.1f%% top5 %.1f%% top10 %.1f%% top20 %.1f%%; n %d' % (sa, 100 * sum(s[:1]) / sa, 100 * sum(s[:5]) / sa, 100 * sum(s[:10]) / sa, 100 * sum(s[:20]) / sa, len(s)))
BB = collections.defaultdict(lambda: [0, 0])
for f in FF:
    if f['att']:
        BB[f['battle']][0] += f['fdmg']
        BB[f['battle']][1] += f['cas_kf_own']
print(' by battle (attack windows):')
for k, v in sorted(BB.items(), key=lambda kv: -kv[1][0])[:12]:
    print('  %-22s fdmg %6d (%5.1f%%) own killed by own %3d' % (k, v[0], 100 * v[0] / sa, v[1]))
print('  battles with any', len(BB), 'of', len(res), ', battles with >=100 HP', sum(1 for v in BB.values() if v[0] >= 100))
W = collections.defaultdict(lambda: [0, 0, 0])
for f in FF:
    if f['att']:
        X = W[f['w']]
        X[0] += 1
        X[1] += f['fdmg']
        X[2] += f['dmg']
print(' by weapon (attack windows): windows, fdmg, dmg on players')
for k, v in sorted(W.items(), key=lambda kv: -kv[1][1])[:14]:
    print('  %-28s %4d %6d %6d' % (k, v[0], v[1], v[2]))
print(' fdmg and dmg of the same windows: fdmg', sa, 'dmg', sum(f['dmg'] for f in FF if f['att']))
# ---------- concentration
CC = collections.Counter()
for b in res:
    CC.update(b['CC'])
print('\n== Concentration: per target per AI phase, by number of distinct attackers')
for k in ('1', '2', '3', '4+'):
    print(' attackers %-3s target-phases %5d attacks %5d dmg %6d downed %4d dmg/attack %5.2f downed/target-phase %5.3f' % (k, CC['targets_' + k], CC['attacks_' + k], CC['dmg_' + k], CC['downed_' + k], CC['dmg_' + k] / max(1, CC['attacks_' + k]), CC['downed_' + k] / max(1, CC['targets_' + k])))
