# -*- coding: utf-8 -*-
"""Debate R1, questions 6 and 7: what the player's save files hold. Read-only, plain text scan, no YAML load.

Usage: py -3 debate1_saves.py <out_file>
For each save: is a battle inside; missions by stage (months since the first mission of the save, the same stages as the 2026-10 audit:
0-11, 12-35, 36+); deaths of soldiers from deadSoldiers with their cause. The kill record is BattleUnitKills: turn = battle turn * 3 + faction of
the phase, so turn mod 3 == 0 is the player's phase (reaction fire, or own fire) and 1 the enemy's; the battle turn is turn // 3; side and bodypart
describe the hit; id is the killer's or the victim's own id, it depends on the record, so this script does not lean on it.
A soldier's cause holds the killer's type, weapon and ammo.
Two more source folders are scanned for battles: the player tickets and the campaign bench.
"""
import collections
import glob
import os
import re
import sys

ROOT = r'E:\OpenXCom\Пиратки\Dioxine_XPiratez\user\piratez'
SAVES = ['GoldGalZ.sav', 'NoCodexCatZ.sav', 'NoCodexManZ.sav', 'PeasGray.sav', 'RedCatZ.sav', 'стрим.sav']
TICKETS = r'E:\OpenXCom\census\tickets'
CAUSE_RE = re.compile(r"\{type: ([^,]*),rank: ([^,]*),race: ([^,]*),weapon: ([^,]*),weaponAmmo: ([^,]*),status: (\d+),faction: (\d+),mission: (-?\d+),turn: (-?\d+),side: (-?\d+),bodypart: (-?\d+),id: (-?\d+)\}")
TIME_RE = re.compile(r"time: \{second: \d+,minute: \d+,hour: \d+,weekday: \d+,day: \d+,month: (\d+),year: (\d+)\}")


def stage(m):
    return 'early 0-11' if m < 12 else 'mid 12-35' if m < 36 else 'late 36+'


def rbin(r):
    return '1' if r <= 1 else '2' if r == 2 else '3' if r == 3 else '4-5' if r <= 5 else '6-10' if r <= 10 else '11+'


def battle_head(text, i):
    head = {}
    b = text[i:i + 8000000]
    for key in ('turn', 'missionType', 'cheatTurn', 'globalshade', 'bughuntMode', 'tuReserved', 'selectedUnit'):
        m = re.search(r'^  %s: (.*)$' % key, b, re.M)
        if m:
            head[key] = m.group(1)[:40]
    # the units block: faction and TU of each unit
    u = b.find('\n  units:')
    it = b.find('\n  items:', u)
    units = re.split(r'^  - ', b[u:it], flags=re.M)[1:] if u >= 0 and it > 0 else re.split(r'^    - ', b[u:it], flags=re.M)[1:]
    live = collections.Counter()
    tu_frac = collections.defaultdict(list)
    spotted = collections.Counter()
    for x in units:
        f = re.search(r'^\s+faction: (\d+)', x, re.M)
        st = re.search(r'^\s+status: (\d+)', x, re.M)
        tu = re.search(r'^\s+tu: (\d+)', x, re.M)
        base = re.search(r'^\s+tu: (\d+)\s*$', x[x.find('stats'):], re.M) if 'stats' in x else None
        if not f:
            continue
        f = int(f.group(1))
        s = int(st.group(1)) if st else -1
        if s in (6, 7, 8):  # dead, unconscious, ignored by the enum of BattleUnit; only the live ones counted
            continue
        live[f] += 1
        if tu and base and int(base.group(1)) > 0:
            tu_frac[f].append(int(tu.group(1)) / int(base.group(1)))
        tss = re.search(r'turnsSinceSpotted: (\d+)', x)
        if tss and f == 0:
            spotted['player_spotted_now' if int(tss.group(1)) == 0 else 'player_not_now'] += 1
    head['live_by_faction'] = dict(live)
    head['units_parsed'] = len(units)
    head['mean_tu_share'] = {k: round(sum(v) / len(v), 2) for k, v in tu_frac.items() if v}
    head['spotted'] = dict(spotted)
    return head


def main():
    out = open(sys.argv[1], 'w', encoding='utf-8-sig')
    P = lambda *a: print(*a, file=out)
    M = collections.defaultdict(collections.Counter)
    D = collections.defaultdict(collections.Counter)
    dedup = {}
    for name in SAVES:
        p = os.path.join(ROOT, name)
        text = open(p, encoding='utf-8', errors='replace').read()
        P('\n=====', name, 'bytes', len(text))
        m = re.search(r'^ironman: (.*)$', text[:3000], re.M)
        P(' ironman', m.group(1) if m else '?')
        i = text.find('\nbattleGame:')
        P(' battle inside:', battle_head(text, i) if i >= 0 else False)
        ms = text.find('\nmissionStatistics:')
        missions = {}
        if ms >= 0:
            seg = text[ms + 20:]
            nxt = re.search(r'^[a-zA-Z]', seg, re.M)
            seg = seg[:nxt.start()] if nxt else seg
            for bl in re.split(r'^  - id: ', seg, flags=re.M)[1:]:
                mid = int(re.match(r'(-?\d+)', bl).group(1))
                t = TIME_RE.search(bl)
                typ = re.search(r'^    type: (.*)$', bl, re.M)
                dl = re.search(r'^    daylight: (\d+)', bl, re.M)
                if t:
                    missions[mid] = dict(ym=int(t.group(2)) * 12 + int(t.group(1)), type=typ.group(1) if typ else '?', dl=int(dl.group(1)) if dl else 0)
        if not missions:
            P(' missions parsed 0')
            continue
        ym0 = min(v['ym'] for v in missions.values())
        # repeats of a campaign (same first 15 missions) go once, as in the 2026-10 audit
        sig = tuple((missions[k]['ym'], missions[k]['type']) for k in sorted(missions)[:15])
        repeat_of = dedup.get(sig)
        dedup.setdefault(sig, name)
        stg = {k: stage(v['ym'] - ym0) for k, v in missions.items()}
        P(' missions', len(missions), 'by stage', dict(collections.Counter(stg.values())), 'months', max(v['ym'] for v in missions.values()) - ym0, 'repeat of', repeat_of)
        if repeat_of:
            continue
        for k, v in missions.items():
            M[stg[k]]['missions'] += 1
            M[stg[k]]['night' if v['dl'] > 9 else 'day'] += 1
        ds = text.find('\ndeadSoldiers:')
        seg = text[ds:ms] if ds >= 0 and ds < ms else ''
        by_m = collections.defaultdict(int)
        for dm in re.finditer(r'^\s+death:\s*$', seg, re.M):
            s2 = seg[dm.end():dm.end() + 700]
            km = CAUSE_RE.search(s2)
            tm = TIME_RE.search(s2)
            if not tm:
                continue
            st = stage(int(tm.group(2)) * 12 + int(tm.group(1)) - ym0)
            D[st]['deaths'] += 1
            if not km or km.start() > 300:
                D[st]['no_cause'] += 1
                continue
            g = km.groups()
            D[st]['cause'] += 1
            mid = int(g[7])
            by_m[(st, mid)] += 1
            t = int(g[8])
            D[st]['phase_%d' % (t % 3)] += 1
            D[st]['round_' + rbin(t // 3)] += 1
            D[st]['w:' + g[3]] += 1
            D[st]['k:' + g[0]] += 1
            D[st]['a:' + g[4]] += 1
        for (st, _), n in by_m.items():
            D[st]['missions_with_deaths'] += 1
            D[st]['catastrophe_3plus'] += n >= 3
            D[st]['deaths_in_catastrophes'] += n if n >= 3 else 0
    P('\n===== Missions and deaths, repeats removed. NOTE: deaths from deadSoldiers include those not in missionStatistics only if the file disagrees')
    for st in ('early 0-11', 'mid 12-35', 'late 36+'):
        c = D[st]
        m = M[st]
        if not m['missions']:
            continue
        P(st, 'missions', m['missions'], 'night share %.2f' % (m['night'] / m['missions']), 'deaths', c['deaths'], 'per mission %.3f' % (c['deaths'] / m['missions']), 'with cause', c['cause'], 'no cause', c['no_cause'])
        P('  missions with deaths', c['missions_with_deaths'], '%.1f%%' % (100 * c['missions_with_deaths'] / m['missions']), 'of them 3+ deaths', c['catastrophe_3plus'], 'deaths in those', c['deaths_in_catastrophes'], '(%.0f%% of deaths)' % (100 * c['deaths_in_catastrophes'] / max(1, c['cause'])))
        P('  phase of death: player', c['phase_0'], 'hostile', c['phase_1'], 'neutral', c['phase_2'])
        P('  rounds', {k[6:]: v for k, v in sorted(c.items()) if k.startswith('round_')})
        P('  top killers', [(k[2:], v) for k, v in c.most_common(400) if k.startswith('k:')][:14])
        P('  top weapons', [(k[2:], v) for k, v in c.most_common(400) if k.startswith('w:')][:14])
    # other sources of human or bench battle saves
    P('\n===== Saves in ticket folders')
    files = [f for f in glob.glob(os.path.join(TICKETS, '**', '*'), recursive=True) if os.path.isfile(f) and f.lower().endswith(('.sav', '.asav', '.sav.txt', '.zip', '.rar', '.7z'))]
    P(' candidate files', len(files), dict(collections.Counter(os.path.splitext(f)[1].lower() for f in files)))
    with_battle = []
    for f in files:
        if not f.lower().endswith(('.sav', '.asav', '.sav.txt')):
            continue
        try:
            text = open(f, encoding='utf-8', errors='replace').read()
        except OSError:
            continue
        i = text.find('\nbattleGame:')
        if i >= 0:
            with_battle.append((f, battle_head(text, i), 'ironman: true' in text[:3000]))
    P(' with a battle inside', len(with_battle))
    types = collections.Counter(h.get('missionType', '?') for _, h, _ in with_battle)
    P(' mission types', types.most_common(20))
    for f, h, iron in with_battle[:40]:
        P(' ', os.path.relpath(f, TICKETS), 'iron', iron, h)
    out.close()


if __name__ == '__main__':
    main()
