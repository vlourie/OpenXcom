"""CPU-only signal, coverage and existing ASR audit; no model or GPU is loaded."""
import argparse
import concurrent.futures
import json
import difflib
import re
from pathlib import Path

import numpy as np
import soundfile as sf

import voice_script

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / 'art/sfx/voicepack'
OUT = SRC / 'audit.json'


def normalized(text):
    text = text.lower().replace('ё', 'е')
    for words, number in [('one hundred', '100'), ('eighty', '80'),
                          ('сто процентов', '100percent'), ('восемьдесят процентов', '80percent'),
                          ('восемьсот первый', '801'), ('eight-oh-one', '801'),
                          ('8.01', '801')]:
        text = text.replace(words, number)
    text = text.replace('%', 'percent').replace(' percent', 'percent')
    text = text.replace('marsec', 'марсек')
    return re.sub(r'[^\w]', '', text)


def text_score(it):
    return max(it.get('close', 0), difflib.SequenceMatcher(
        None, normalized(it['text']), normalized(it.get('heard', '')), autojunk=False).ratio())


def signal(rel):
    try:
        path = (SRC / rel).resolve()
        if not path.is_relative_to(SRC.resolve()):
            raise ValueError('path outside voicepack')
        x, rate = sf.read(path, dtype='float32', always_2d=True)
        if not len(x) or not np.isfinite(x).all():
            raise ValueError('empty or nonfinite signal')
        y = x.mean(axis=1)
        peak = float(np.abs(y).max())
        rms = float(np.sqrt(np.mean(y ** 2)))
        dur = len(y) / rate
        clipped = float(np.mean(np.abs(y) >= .999))
        problems = []
        if peak < .01 or rms < .001: problems.append('silent')
        if dur < .15 or dur > 6: problems.append('duration')
        if clipped > .001: problems.append('clipping')
        if rate < 16000: problems.append('rate')
        st = path.stat()
        return rel, dict(duration=round(dur, 4), rate=rate, bytes=st.st_size, mtime_ns=st.st_mtime_ns,
                         peak_db=round(20*np.log10(max(peak, 1e-10)), 2),
                         rms_db=round(20*np.log10(max(rms, 1e-10)), 2),
                         clipped=clipped, problems=problems)
    except Exception as e:
        return rel, {'problems': [str(e)]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--min-close', type=float, default=.75)
    args = ap.parse_args()
    voices = voice_script.parse(more=voice_script.MORE100, only=voice_script.pinned())
    states = {v['id']: json.loads((SRC/v['id']/'voice.json').read_text(encoding='utf-8-sig')) for v in voices}
    paths = {it['file'] for s in states.values() for it in s['lines'] if 'file' in it}
    paths.update(s['ref'] for s in states.values())
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        signals = dict(pool.map(signal, sorted(paths)))
    selected, missing, rejected, swaps, flagged = [], [], [], [], []
    for v in voices:
        st = states[v['id']]
        for ln in v['lines']:
            for lang in ('ru', 'en'):
                key = dict(voice=v['id'], line=ln['n'], lang=lang, text=ln[lang])
                takes = [it for it in st['lines'] if it['lang']==lang and it['n']==ln['n']]
                good = [it for it in takes if 'file' in it and not signals[it['file']]['problems']
                        and it['text']==ln[lang] and text_score(it)>=args.min_close]
                if not takes:
                    missing.append(key)
                if not good:
                    rejected.append(dict(key, takes=[{k:it.get(k) for k in ('file','close','heard','error')} for it in takes]))
                    continue
                best = max(good, key=lambda it:(text_score(it)>=.9, it.get('band',False),
                                               it['dur']<=3.2, text_score(it), -it['dur']))
                row = dict(key, file=best['file'], close=best['close'], text_score=round(text_score(best),3), heard=best.get('heard'),
                           band=best.get('band'), signal=signals[best['file']])
                selected.append(row)
                if not best.get('chosen'): swaps.append(row)
                if not best.get('band') or best['dur']>3.2 or best['close']<.9: flagged.append(row)
    report = dict(voices=len(voices), expected=sum(len(v['lines'])*2 for v in voices),
                  files_checked=len(signals), selected=selected, rejected=rejected, missing=missing,
                  swaps=swaps, flagged=flagged,
                  bad_files={p:s for p,s in signals.items() if s['problems']})
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=1),encoding='utf-8-sig')
    print(json.dumps({k:len(val) if isinstance(val,(dict,list)) else val for k,val in report.items()},ensure_ascii=True))
    for r in rejected:
        print(json.dumps(r,ensure_ascii=True))


if __name__ == '__main__':
    main()
