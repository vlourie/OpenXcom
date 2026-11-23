# -*- coding: utf-8 -*-
"""Read-only: are the D0 arms of different series the same battles? Compares the result row (seed, turn, losses, decisions) with d0p."""
import zipfile

ROOT = 'E:/OXCE_AIWorker/battles_archive/'


def table(zname, tag):
    z = zipfile.ZipFile(ROOT + zname)
    res = {}
    for n in z.namelist():
        if n.startswith('arena/') and n.endswith('.tsv') and ('_' + tag + '_') in n:
            lines = z.read(n).decode('utf-8-sig', 'replace').split('\n')
            if len(lines) < 2:
                continue
            row = dict(zip(lines[0].split('\t'), lines[1].split('\t')))
            name = n.split('/')[-1].replace('.tsv', '').split('_', 2)[2]
            res[name] = (row.get('seed'), row.get('turn'), row.get('pdead'), row.get('hdead'), row.get('hdecisions'))
    return res


def main():
    base = table('commander_2026-10-29/res_d0p.zip', 'D')
    print('d0p battles', len(base))
    for zname, tag in (('side_turn_scheduler_pilot_2026-10-30/res_scpa.zip', 'D'), ('strike_v0_2026-10-30/res_svo.zip', 'SO'), ('side_first_v0/res/res_sfF.zip', 'D')):
        other = table(zname, tag)
        print(zname, tag, 'battles', len(other), 'names in common', sum(1 for k in other if k in base), 'identical rows', sum(1 for k, v in other.items() if base.get(k) == v))


if __name__ == '__main__':
    main()
