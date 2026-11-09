# -*- coding: utf-8 -*-
"""Debate R1, the last slices over the frozen archive. Read-only.

Usage: py -3 debate1_last.py <zip> <funnel_json> [name_filter_regex]  (the report goes to stdout)
1. Battle tables (arena/*.tsv): player dead and HP by battle, with and without M1.
2. Casualty tables: hostiles killed by their own side, by weapon, terrain flag and map; players' deaths by phase and killer weapon class.
3. Exposure events: a hostile unseen at the player phase start of round T-1 and seen at that of round T. Split by whether it fired in the enemy phase
   between, whether others fired or got exposed in the same phase; outcome: killed in the player phase of round T.
4. TU the player's units keep at the start of the enemy phase (the bot spends nearly all; reaction fire depends on it).
"""
import collections
import csv
import gzip
import io
import json
import multiprocessing as mp
import random
import re
import sys
import zipfile

ATT = {6, 7, 8, 9, 10, 12, 16}
RE_STATE = re.compile(r'\[AISTATE\] (\w+) turn=(\d+) unit=(\d+) type=(\S+) faction=(\d+) status=(\d+) pos=\((\d+),(\d+),(\d+)\) dir=(\d+) tu=(-?\d+) hp=(-?\d+)/(\d+) stun=(\d+) morale=(\d+) kneel=(\d) weapon=(\S+) spotted=(-?\d+) sniped=(-?\d+) sees=(\S+) seenby=(\d+)')
RE_CAS = re.compile(r'\[AICASUALTY\] turn=(\d+) side=(\d+) victim=(\d+) vfaction=(\d+) type=(\S+) how=(\w+) pos=\((\d+),(\d+),(\d+)\) tu=(-?\d+) kneel=\d seenby=(\d+) killer=(-?\d+) kfaction=(-?\d+) ktype=(\S+) dist=(-?\d+) weapon=(\S+) hit=(\S+) terrain=(\d)')


def scn(b):
    m = re.search(r'_([LM]\d+)_s\d+', b)
    return m.group(1) if m else b


def analyse(args):
    zpath, member = args
    text = gzip.decompress(zipfile.ZipFile(zpath).read(member)).decode('utf-8', 'replace')
    battle = member.split('/')[1]
    snaps = collections.defaultdict(dict)
    tus = []
    fired = collections.defaultdict(set)   # turn -> units with an attack in the hostile phase
    dmg_by = collections.defaultdict(lambda: collections.defaultdict(int))
    seen = set()
    died_pl = collections.defaultdict(set)
    for line in text.split('\n'):
        if '[AI' not in line:
            continue
        if '[AISTATE]' in line:
            m = RE_STATE.search(line)
            if not m:
                continue
            g = m.groups()
            if g[0] == 'pstart' and int(g[4]) == 1 and int(g[5]) not in (6, 7, 8):
                snaps[int(g[1])][int(g[2])] = int(g[20])
            elif g[0] == 'pstart' and int(g[4]) == 1:
                pass
            elif g[0] == 'aistart' and int(g[4]) == 0:
                tus.append(int(g[10]))
        elif '[AIREC]' in line:
            try:
                j = json.loads(line[line.index('{'):])
            except Exception:
                continue
            if j['rec'] in seen or j.get('side') != 1:
                continue
            seen.add(j['rec'])
            b = j.get('base') or {}
            if b.get('t') in ATT:
                fired[j['turn']].add(j['unit'])
        elif '[AICASUALTY]' in line:
            m = RE_CAS.search(line)
            if m and int(m.group(2)) == 0 and int(m.group(4)) == 1:
                died_pl[int(m.group(1))].add(int(m.group(3)))
    ev = []
    for T in sorted(snaps):
        if T - 1 not in snaps:
            continue
        new = [u for u, s in snaps[T].items() if s > 0 and snaps[T - 1].get(u, 0) == 0]
        others_fired = fired.get(T - 1, set())
        for u in new:
            ev.append(dict(battle=battle, T=T, u=u, own=u in fired.get(T - 1, set()), of=len(others_fired - {u}), nnew=len(new), died=u in died_pl.get(T, set())))
    return dict(battle=battle, ev=ev, tus=tus)


def boot(ev, a, b, B=2000):
    by = collections.defaultdict(list)
    for e in ev:
        by[scn(e['battle'])].append(e)
    keys = sorted(by)
    rnd = random.Random(20261107)
    vals = []
    for _ in range(B):
        pa = pb = na = nb = 0
        for _k in keys:
            for e in by[rnd.choice(keys)]:
                if a(e):
                    na += 1
                    pa += e['died']
                elif b(e):
                    nb += 1
                    pb += e['died']
        if na and nb:
            vals.append(pa / na - pb / nb)
    vals.sort()
    return round(vals[int(0.025 * len(vals))], 3), round(vals[int(0.975 * len(vals))], 3)


def main():
    zpath, fj = sys.argv[1:3]
    rx = re.compile(sys.argv[3]) if len(sys.argv) > 3 else None
    Z = zipfile.ZipFile(zpath)
    ranges = json.load(open(fj, encoding='utf-8-sig'))['ranges']
    print('== 1. Battles')
    rows = []
    for n in Z.namelist():
        if n.startswith('arena/') and n.endswith('.tsv') and (not rx or rx.search(n)):
            t = Z.read(n).decode('utf-8-sig', 'replace')
            for r in csv.DictReader(io.StringIO(t), delimiter='\t'):
                r['battle'] = n.split('/')[1][:-4]
                rows.append(r)

    def agg(rs, tag):
        n = len(rs)
        pd = sum(int(r['pdead'] or 0) for r in rs)
        hp = sum(int(r['phplost'] or 0) for r in rs)
        wd = sum(1 for r in rs if int(r['pdead'] or 0) > 0)
        print(' %s battles %d player_units %d pdead %d per battle %.2f battles with deaths %.0f%% phplost %d per battle %.0f hdead %d turns %.1f' % (tag, n, sum(int(r['player'] or 0) for r in rs), pd, pd / n, 100 * wd / n, hp, hp / n, sum(int(r['hdead'] or 0) for r in rs), sum(int(r['turn'] or 0) for r in rs) / n))
    agg(rows, 'ALL')
    agg([r for r in rows if scn(r['battle']) != 'M1'], 'NO M1')
    agg([r for r in rows if scn(r['battle']).startswith('M')], 'M only')
    agg([r for r in rows if scn(r['battle']).startswith('L')], 'L only')
    print(' months', sorted(collections.Counter(int(r['month']) for r in rows).items()))
    print(' kinds', collections.Counter(r['kind'] for r in rows).most_common())
    print(' M1', [(r['battle'], r['want'][:32], r['player'], r['pdead'], r['phplost'], r['hostile'], r['hdead']) for r in rows if scn(r['battle']) == 'M1'])
    pd_sc = collections.Counter()
    for r in rows:
        pd_sc[scn(r['battle'])] += int(r['pdead'] or 0)
    print(' pdead by scenario', pd_sc.most_common())

    # by the campaign month of the squad: the funnel's counters per battle
    F = json.load(open(fj, encoding='utf-8-sig'))['res']
    fby = {x['battle']: x['C'] for x in F}
    print('\n== 1b. By month of the squad (funnel counters): battles, unit-turns, attacked, no line, known on no line, weak/proven/melee among known no line, HP aimed per attack, HP/battle, pdead/battle, hdead/battle')
    for mon in sorted({int(r['month']) for r in rows}):
        rs = [r for r in rows if int(r['month']) == mon]
        C = collections.Counter()
        for r in rs:
            C.update(fby.get(r['battle'], {}))
        n = max(1, C['unit_turns'])
        nl = max(1, C['no_lof'])
        kn = max(1, C['info_exact'] + C['info_fresh'])
        w = {k: C['info_exact_w_' + k] + C['info_fresh_w_' + k] for k in ('proven', 'weak', 'melee', 'unknown', 'none', 'thrown')}
        print(' month %3d scen %s battles %d ut %5d att %.1f%% nolof %.1f%% known %.1f%% | weak %.0f%% proven %.0f%% melee %.0f%% | F3p90 %.1f%% | dmg %6d /battle %.0f | pdead/b %.2f hdead/b %.1f player/b %.1f' % (
            mon, sorted({scn(r['battle']) for r in rs}), len(rs), n, 100 * C['attacked'] / n, 100 * nl / n, 100 * (C['info_exact'] + C['info_fresh']) / n,
            100 * w['weak'] / kn, 100 * w['proven'] / kn, 100 * w['melee'] / kn,
            100 * (C['info_exact_p90_F3_proven'] + C['info_fresh_p90_F3_proven']) / n,
            C['player_dmg'], C['player_dmg'] / len(rs), sum(int(r['pdead'] or 0) for r in rs) / len(rs), sum(int(r['hdead'] or 0) for r in rs) / len(rs), sum(int(r['player'] or 0) for r in rs) / len(rs)))

    print('\n== 2. Casualties')
    FF = collections.Counter()
    PL = collections.Counter()
    for n in Z.namelist():
        if not (n.startswith('arena/') and n.endswith('.casualties.txt')) or (rx and not rx.search(n)):
            continue
        b = n.split('/')[1].replace('.casualties.txt', '')
        for line in Z.read(n).decode('utf-8', 'replace').split('\n'):
            m = RE_CAS.search(line)
            if not m:
                continue
            g = m.groups()
            side, vf, kf, victim, killer, w, terrain, how = int(g[1]), int(g[3]), int(g[12]), g[2], g[11], g[15], int(g[17]), g[5]
            if vf == 1:
                FF['h_all'] += 1
                if how == 'dead':
                    FF['h_dead'] += 1
                if kf == 1:
                    FF['ff_all'] += 1
                    FF['ff_how_' + how] += 1
                    FF['ff_side_%d' % side] += 1
                    FF['ff_terrain_%d' % terrain] += 1
                    FF['ff_self' if victim == killer else 'ff_other'] += 1
                    FF['w:' + w] += 1
                    FF['b:' + scn(b)] += 1
                    if terrain:
                        FF['tb:' + scn(b)] += 1
            elif vf == 0:
                PL['all'] += 1
                PL['how_' + how] += 1
                PL['side_%d' % side] += 1
                PL['kf_%d' % kf] += 1
                c = ranges.get(w, {}).get('class', 'not_in_table')
                PL['class_' + c] += 1
                PL['w:' + w] += 1
                PL['round_%s' % ('1' if int(g[0]) == 1 else '2' if int(g[0]) == 2 else '3' if int(g[0]) == 3 else '4-5' if int(g[0]) <= 5 else '6-10' if int(g[0]) <= 10 else '11+')] += 1
    print(' hostile casualties', FF['h_all'], 'dead', FF['h_dead'], 'by own side', FF['ff_all'], {k: v for k, v in FF.items() if k.startswith('ff_')})
    print(' FF weapons', [(k[2:], v) for k, v in FF.most_common(300) if k.startswith('w:')][:14])
    print(' FF by scenario', [(k[2:], v) for k, v in FF.most_common(300) if k.startswith('b:')][:14])
    print(' FF terrain flag by scenario', [(k[3:], v) for k, v in FF.most_common(300) if k.startswith('tb:')][:10])
    print(' players', {k: v for k, v in sorted(PL.items()) if not k.startswith('w:')})
    print(' player killers', [(k[2:], v) for k, v in PL.most_common(300) if k.startswith('w:')][:14])

    members = [n for n in Z.namelist() if n.endswith('openxcom.log.gz') and (not rx or rx.search(n))]
    with mp.Pool(max(2, mp.cpu_count() - 2)) as pool:
        res = pool.map(analyse, [(zpath, m) for m in members])
    ev = [e for r in res for e in r['ev']]
    tus = [t for r in res for t in r['tus']]
    print('\n== 3. New exposures (unseen at pstart T-1, seen at pstart T):', len(ev), 'died in the next player phase', sum(e['died'] for e in ev))

    def rate(name, f):
        s = [e for e in ev if f(e)]
        print('  %-44s n %5d (%4.1f%%) died %.3f' % (name, len(s), 100 * len(s) / max(1, len(ev)), sum(e['died'] for e in s) / max(1, len(s))))
    rate('fired itself in that enemy phase', lambda e: e['own'])
    rate('did not fire itself', lambda e: not e['own'])
    rate('alone: no other fired, no other newly seen', lambda e: not e['own'] and e['of'] == 0 and e['nnew'] == 1)
    rate('did not fire, others fired', lambda e: not e['own'] and e['of'] > 0)
    rate('did not fire, others newly seen, none fired', lambda e: not e['own'] and e['of'] == 0 and e['nnew'] > 1)
    rate('fired, others also fired', lambda e: e['own'] and e['of'] > 0)
    rate('fired, alone', lambda e: e['own'] and e['of'] == 0)
    rate('not firing, others 1-2', lambda e: not e['own'] and 1 <= e['of'] <= 2)
    rate('not firing, others 3+', lambda e: not e['own'] and e['of'] >= 3)
    print('  fired itself vs not, death diff CI', boot(ev, lambda e: e['own'], lambda e: not e['own']))
    print('  alone vs others fired (both not firing), death diff CI', boot(ev, lambda e: not e['own'] and e['of'] == 0 and e['nnew'] == 1, lambda e: not e['own'] and e['of'] > 0))
    print('\n== 4. Player TU at the enemy phase start: n', len(tus), 'mean %.1f' % (sum(tus) / max(1, len(tus))), 'share <=10: %.1f%%' % (100 * sum(t <= 10 for t in tus) / max(1, len(tus))), 'share >=40: %.1f%%' % (100 * sum(t >= 40 for t in tus) / max(1, len(tus))))


if __name__ == '__main__':
    main()
