# -*- coding: utf-8 -*-
"""Rolls up census_<label>.json into a plain text report. Usage: py -3 census_report.py <census.json> [out.txt]"""
import collections
import json
import statistics
import sys


def add(dst, src):
    for k, v in (src or {}).items():
        dst[k] += v


def main():
    res = json.load(open(sys.argv[1], encoding='utf-8-sig'))
    out = open(sys.argv[2], 'w', encoding='utf-8-sig') if len(sys.argv) > 2 else sys.stdout

    def P(*a):
        print(*a, file=out)

    # A
    P('== A. Battles')
    P('battle | mission race month | P H | turns | pdead hdead hout | outcome | hdec | 1st hostile attack turn / 1st player casualty / 1st hostile casualty | hostile down before first AI turn')
    wins = collections.Counter()
    for r in sorted(res, key=lambda r: r['battle']):
        m = r['meta']
        P(r['battle'].replace('d0p_D_', ''), '|', m.get('mission'), m.get('race'), m.get('month'), '|', m.get('player'), m.get('hostile'), '|', m.get('turn'), '|', m.get('pdead'), m.get('hdead'), m.get('hout'), '|', m.get('outcome'), '|', r['C'].get('decisions'), '|', r['first_att'], r['first_p_cas'], r['first_h_cas'], '|', r['K'].get('hostile_down_before_first_ai_turn', 0))
        wins[m.get('outcome')] += 1
    P('outcomes', dict(wins))
    # aggregates
    C = collections.Counter(); srcn = collections.Counter(); srct = collections.Counter(); srcz = collections.Counter(); lv = collections.Counter(); lt = collections.Counter()
    UT = collections.Counter(); K = collections.Counter(); Pz = collections.Counter(); tr = collections.Counter(); psi = collections.Counter(); gren = collections.Counter(); mw = collections.Counter(); mo = collections.Counter(); kw = collections.Counter(); pkw = collections.Counter(); F = collections.Counter(); distb = collections.Counter(); react = collections.Counter()
    weap = collections.defaultdict(lambda: [0, 0, 0, 0, 0, 0]); tt = collections.defaultdict(lambda: [0] * 7); typ = collections.defaultdict(lambda: [0] * 7); mv = collections.defaultdict(lambda: [0, 0, 0, 0.0]); hb = collections.defaultdict(collections.Counter)
    tl = [0, 0]
    for r in res:
        add(C, r['C']); add(srcn, r['src_n']); add(srct, r['src_tu']); add(srcz, r['src_zero']); add(lv, r['legal_vs']); add(lt, r['legal_tu']); add(UT, r['UT']); add(K, r['K']); add(Pz, r['Pz']); add(tr, r['trail']); add(psi, r['psi']); add(gren, r['gren']); add(mw, r['multiw']); add(mo, r['mode_odds']); add(kw, r['kw']); add(pkw, r['pkw']); add(F, r['F']); add(distb, r['distb']); add(react, r['react'])
        for k, v in r['weap'].items():
            for i in range(6):
                weap[k][i] += v[i]
        for k, v in r['ttype'].items():
            for i in range(7):
                tt[k][i] += v[i]
        for k, v in r['typ'].items():
            for i in range(7):
                typ[k][i] += v[i]
        for k, v in r['move'].items():
            for i in range(4):
                mv[k][i] += v[i]
        for k, v in r['hpband'].items():
            add(hb[k], v)
        tl[0] += r['tuleft'][0]; tl[1] += r['tuleft'][1]
    P('\n== B. Decisions by source (n, % of n, TU spent, % of TU, zero-TU decisions)')
    tn = sum(srcn.values()); tt_ = sum(srct.values()) or 1
    for k, v in srcn.most_common():
        P(f'{k:22s} {v:7d} {100*v/tn:5.1f}% tu={srct[k]:8d} {100*srct[k]/tt_:5.1f}% zero={srcz[k]}')
    P('\n== B2. Unit-turn budget', dict(UT))
    P(f"  TU at first decision: {UT['tu0']}; attack {UT['tuAttack']} ({100*UT['tuAttack']/max(1,UT['tu0']):.1f}%); walk {UT['tuWalk']} ({100*UT['tuWalk']/max(1,UT['tu0']):.1f}%); other {UT['tuOther']}; left {UT['tuLeft']} ({100*UT['tuLeft']/max(1,UT['tu0']):.1f}%)")
    P('\n== C. Legal attack on a visible player unit available at decision')
    P(' decisions with legal:', C['decisions_with_legal_attack_on_visible_player'], 'of', C['decisions'])
    tl_ = sum(lv.values()) or 1
    for k, v in lv.most_common():
        P(f'   chose {k:22s} {v:7d} {100*v/tl_:5.1f}%  tu={lt[k]}')
    P(' unit turns:', UT['unit_turns'], 'with attack', UT['unit_turns_with_attack'], 'with legal', UT['unit_turns_with_legal_attack'], 'legal but no attack', UT['unit_turns_legal_but_no_attack'], 'legal at first decision', UT['unit_turns_legal_at_first_decision'], 'of them no attack', UT['unit_turns_legal_first_no_attack'], 'tu left on legal-no-attack', UT['tuLeft_legal_no_attack'])
    P('\n== R. Mode roll when legal attack existed', dict(mo))
    if mo['n']:
        P(f"   mean weights patrol {mo['sum_p']/mo['n']:.3f} ambush {mo['sum_a']/mo['n']:.3f} combat {mo['sum_c']/mo['n']:.3f} escape {mo['sum_e']/mo['n']:.3f}")
    P('\n== D. Attacks by type: n, n with dmg/stun, %hit, dmg, stun, downs, TU, dmg/attack, dmg/100TU, friendly dmg')
    for k, v in sorted(tt.items(), key=lambda kv: -kv[1][0]):
        P(f'{k:8s} {v[0]:6d} {v[1]:6d} {100*v[1]/max(1,v[0]):5.1f}% dmg={v[2]:7d} stun={v[5]:6d} down={v[3]:5d} tu={v[4]:7d} d/a={v[2]/max(1,v[0]):6.2f} d/100tu={100*v[2]/max(1,v[4]):6.2f} fdmg={v[6]}')
    P('\n== D2. Top weapons (mode): n, mean candidate p, %effect, dmg, dmg/attack, downs, TU, dmg/100TU')
    for k, v in sorted(weap.items(), key=lambda kv: -kv[1][0])[:40]:
        P(f'{k:42s} {v[0]:5d} p={v[1]/max(1,v[0]):5.1f} eff={100*v[2]/max(1,v[0]):5.1f}% dmg={v[3]:6d} d/a={v[3]/max(1,v[0]):6.2f} down={v[4]:4d} tu={v[5]:6d} d/100={100*v[3]/max(1,v[5]):6.2f}')
    P('\n== E. Participation', dict(Pz))
    P(f"  never attacked {100*Pz['never_attacked']/max(1,Pz['hostiles']):.1f}%; never damaged {100*Pz['never_damaged']/max(1,Pz['hostiles']):.1f}%; top10% share of dmg {100*Pz['dmg_top10pct']/max(1,Pz['dmg_total']):.1f}%")
    P('\n== F. Casualties')
    for k, v in sorted(K.items()):
        P(f'  {k:40s} {v}')
    P('  hostile TU at downing / max:', tl, f'{100*tl[0]/max(1,tl[1]):.1f}%')
    P('  distance of hostile downing (5-bins):', sorted(((int(k), v) for k, v in distb.items())))
    P('  player weapons killing hostiles top:', kw.most_common(15))
    P('  hostile killers of player top:', pkw.most_common(15))
    P('\n== G. Walk direction vs nearest player (start-of-side positions): src closer farther same meanDelta')
    for k, v in sorted(mv.items(), key=lambda kv: -sum(kv[1][:3])):
        n = sum(v[:3]) or 1
        P(f'{k:22s} {v[0]:6d} {v[1]:6d} {v[2]:6d} closer={100*v[0]/n:5.1f}% farther={100*v[1]/n:5.1f}% mean={v[3]/n:+.2f}')
    P('\n== H. Source by HP band')
    for k, v in sorted(hb.items()):
        n = sum(v.values()) or 1
        P(k, {a: f'{100*b/n:.1f}%' for a, b in v.most_common(8)}, 'n=', n)
    P('\n== I. Trail stops (first token)')
    P(tr.most_common(40))
    P('\n== J. reactions (actingSide|reactorFaction)', dict(react))
    P('  during own decision: died', C['died_during_own_decision'], 'walk', C['died_during_own_walk'], 'attack', C['died_during_own_attack'], 'other', C['died_during_own_other'], 'hp lost', C['hp_lost_during_own_decision'])
    P('\n== L. Focus: side turns with 2+ attacks', dict(F), f"attacks/turn {F['attacks']/max(1,F['turns']):.2f}, distinct targets/turn {F['targets']/max(1,F['turns']):.2f}")
    P('\n== M. Psi options', dict(psi))
    P('== N. Grenades', dict(gren))
    P('== multi-firearm', dict(mw))
    P('friendly', C['fdmg'], C['fdowned'])
    P('\n== P. Unit types: units dec att dmg downs dead | dmg/unit, dmg/att, dead%')
    for k, v in sorted(typ.items(), key=lambda kv: -kv[1][0])[:50]:
        P(f'{k:38s} {v[0]:5d} {v[1]:6d} {v[2]:5d} {v[3]:6d} {v[4]:4d} {v[5]:5d} | {v[3]/max(1,v[0]):7.1f} {v[3]/max(1,v[2]):6.2f} {100*v[5]/max(1,v[0]):5.1f}%')
    P('\n== G2. Army geometry per turn (one battle = one line; turn:n/mean distance/<=10/<=20/seenby/known)')
    for r in sorted(res, key=lambda r: r['battle']):
        g = r['geom']
        s = []
        for t in sorted(g, key=int)[:14]:
            x = g[t]
            s.append(f"{t}:{x['n']}/{x['mean']:.0f}/{x['le10']}/{x['le20']}/{x['seenby']}/{x['known']}")
        P(r['battle'].replace('d0p_D_', ''), ' '.join(s))
    if out is not sys.stdout:
        out.close()


if __name__ == '__main__':
    main()
