# -*- coding: utf-8 -*-
"""Report for debate1_funnel.py: sums, per-scenario bootstrap, with and without M1. Usage: py -3 debate1_funnel_report.py <data_dir> <label>"""
import collections
import json
import os
import random
import re
import sys

data_dir, label = sys.argv[1:3]
J = json.load(open(os.path.join(data_dir, 'debate1_funnel_%s.json' % label), encoding='utf-8-sig'))
res = J['res']
ranges = J['ranges']


def scn(b):
    m = re.search(r'_([LM]\d+)_s\d+', b)
    return m.group(1) if m else b


def total(rs):
    C = collections.Counter()
    S = collections.Counter()
    D = collections.Counter()
    for r in rs:
        C.update(r['C'])
        S.update(r['S'])
        D.update(r['D'])
    return C, S, D


def show(rs, name):
    C, S, D = total(rs)
    n = C['unit_turns']
    nl = C['no_lof']
    print('\n=====', name, 'battles', len(rs), 'unit_turns', n)
    print(' attacked %.1f%%  lof_no_attack %.1f%%  no_lof %.1f%% (%d)' % (100 * C['attacked'] / n, 100 * C['lof_no_attack'] / n, 100 * nl / n, nl))
    print(' aimed damage on players', C['player_dmg'], 'no_lof after turn 20', C['no_lof_late'])
    print(' audit known (spotted this round, unit snapshot): %d = %.1f%% of unit-turns' % (C['audit_known'], 100 * C['audit_known'] / n))
    print(' modes on no_lof:', {k[5:]: '%d (%.1f%%)' % (v, 100 * v / nl) for k, v in C.items() if k.startswith('mode_')})
    for info in ('exact', 'fresh', 'stale', 'none'):
        c = C['info_' + info]
        print('  info %-5s %6d  %5.1f%% of no_lof  %5.1f%% of unit-turns' % (info, c, 100 * c / nl, 100 * c / n))
        if info == 'none' or not c:
            continue
        print('     modes', {m: C['info_%s_mode_%s' % (info, m)] for m in ('patrol', 'escape', 'ambush', 'other')})
        print('     dist', {d: C['info_%s_d%s' % (info, d)] for d in ('00-08', '09-15', '16-25', '26+')})
        print('     weapon', {w: C['info_%s_w_%s' % (info, w)] for w in ('proven', 'weak', 'melee', 'thrown', 'unknown', 'none')})
        print('     immobile', C['info_%s_immobile' % info], 'nomoves', C['info_%s_nomoves' % info], 'reach adjacent', C['info_%s_reach_adjacent' % info], 'melee on patrol', C['info_%s_melee_patrol' % info], 'of them adjacent reachable', C['info_%s_melee_patrol_adj' % info])
        for tag in ('p50', 'p90'):
            g = 'info_%s_%s_' % (info, tag)
            print('     %s: in range now %d; reach cell in range %d; +TU for a shot %d; two turns %d; patrol & reach+shot %d: proven %d (%.1f%% of unit-turns; late %d), weak %d, unknown %d, thrown %d; two-turn proven patrol %d; HP at one mean attack %d' % (tag, C[g + 'in_range_now'], C[g + 'reach_range'], C[g + 'reach_shot'], C[g + 'two_turns'], C[g + 'F2_patrol'], C[g + 'F3_proven'], 100 * C[g + 'F3_proven'] / n, C[g + 'F3_proven_late'], C[g + 'F3_weak'], C[g + 'F3_unknown'], C[g + 'F3_thrown'], C[g + 'F4_two_turns_proven_patrol'], D[g + 'F3_hp']))
    print(' targets at aistart:', {k: v for k, v in sorted(S.items()) if k.startswith('tgt_')})
    st = S['tgt_stale']
    if st:
        print(' stale age:', {k: v for k, v in sorted(S.items()) if k.startswith('stale_age')}, 'mean error cells %.1f' % (S['stale_err_sum'] / st))
        print(' stale error:', {k: v for k, v in sorted(S.items()) if k.startswith('stale_err_') and k != 'stale_err_sum'})


def boot(rs, f, B=2000):
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
        vals.append(f(pick))
    vals.sort()
    return round(vals[int(0.025 * B)], 1), round(vals[int(0.975 * B)], 1), len(keys)


show(res, 'ALL')
noM1 = [r for r in res if scn(r['battle']) != 'M1']
if len(noM1) != len(res):
    show(noM1, 'WITHOUT M1')


def share(*keys):
    def f(rs):
        C, _, _ = total(rs)
        return 100 * sum(C[k] for k in keys) / max(1, C['unit_turns'])
    return f


print('\n== Scenario bootstrap (95%), resampling scenarios')
print(' no_lof', boot(res, share('no_lof')))
print(' attacked', boot(res, share('attacked')))
print(' exact+fresh on no_lof', boot(res, share('info_exact', 'info_fresh')))
print(' F3 exact+fresh, proven, p90', boot(res, share('info_exact_p90_F3_proven', 'info_fresh_p90_F3_proven')))
print(' F3 exact+fresh, proven, p50', boot(res, share('info_exact_p50_F3_proven', 'info_fresh_p50_F3_proven')))
print('\n== Per scenario: unit-turns, attacked %, no_lof %, exact+fresh %, F3 proven p90 %, F3 proven p50 %, aimed dmg')
by = collections.defaultdict(list)
for r in res:
    by[scn(r['battle'])].append(r)
for k in sorted(by, key=lambda s: (s[0], int(s[1:]))):
    C, _, _ = total(by[k])
    n = max(1, C['unit_turns'])
    print(' %-4s %6d  att %5.1f  nolof %5.1f  known %5.1f  F3p90 %5.1f  F3p50 %5.1f  dmg %6d' % (k, n, 100 * C['attacked'] / n, 100 * C['no_lof'] / n, 100 * (C['info_exact'] + C['info_fresh']) / n, 100 * (C['info_exact_p90_F3_proven'] + C['info_fresh_p90_F3_proven']) / n, 100 * (C['info_exact_p50_F3_proven'] + C['info_fresh_p50_F3_proven']) / n, C['player_dmg']))
print('\n== Weapon table: attacks on players, HP, yield, p50 and p90 of hurting distance, typical shot cost, class')
for w, v in sorted(ranges.items(), key=lambda kv: -kv[1]['att'])[:30]:
    print(' %-30s att %5d dmg %6d y %6.1f p50 %3d p90 %3d cost %s %s' % (w, v['att'], v['dmg'], v['yield'], v['p50'], v['p90'], v['cost'], v['class']))
print(' classes', dict(collections.Counter(v['class'] for v in ranges.values())))
