# -*- coding: utf-8 -*-
import collections, json
J = json.load(open(r'E:\OpenXCom\docs\research\ai-mechanics\forensic\data\debate1_funnel_d0p.json', encoding='utf-8-sig'))
C = collections.Counter()
for r in J['res']:
    C.update(r['C'])
print('unit_turns', C['unit_turns'], 'no_lof', C['no_lof'])
for i in ('exact', 'fresh', 'stale'):
    print(i, 'kinds', {k: C['info_%s_kind_%s' % (i, k)] for k in ('patrol_only', 'firepoint')})
    for tag in ('p90', 'p50'):
        print(' ', tag, {k.split(tag + '_F3k_')[1]: v for k, v in sorted(C.items()) if k.startswith('info_%s_%s_F3k_' % (i, tag))})
