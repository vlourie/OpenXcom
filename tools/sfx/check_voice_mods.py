"""Decode every exported voice/step file and check sound references (CPU only)."""
import concurrent.futures
import json
import hashlib
from pathlib import Path

import numpy as np
import soundfile as sf
import yaml

ROOT = Path(__file__).resolve().parents[2]
MODS = ROOT / 'Пиратки/Dioxine_XPiratez/user/mods'


def decode(path):
    x, sr = sf.read(path, dtype='float32', always_2d=True)
    if not len(x) or not np.isfinite(x).all() or np.max(np.abs(x)) < .001:
        raise ValueError(f'invalid signal: {path}')
    if sr != 22050 or x.shape[1] != 1:
        raise ValueError(f'wrong format: {path}, {sr}, {x.shape}')
    peak = float(np.max(np.abs(x)))
    clipped = float(np.mean(np.abs(x) >= 1))
    if peak > 1.02 or clipped > .001:
        raise ValueError(f'clipping: {path} peak={peak} fraction={clipped}')
    return dict(file=str(path.relative_to(ROOT)), frames=len(x), rate=sr,
                seconds=round(len(x)/sr,4), peak_db=round(20*np.log10(peak),2),
                rms_db=round(20*np.log10(max(float(np.sqrt(np.mean(x*x))),1e-10)),2),
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                bytes=path.stat().st_size)


def main():
    report = {}
    for name in ('hd_voices_ru','hd_voices_en','hd_test_steps'):
        mod = MODS / name
        meta = yaml.safe_load((mod/'metadata.yml').read_text(encoding='utf-8-sig'))
        rule = yaml.safe_load((mod/'Ruleset'/f'{name}.rul').read_text(encoding='utf-8-sig'))
        files = rule['extraSounds'][0]['files']
        if max(files) >= meta['reservedSpace']*1000:
            raise ValueError(f'{name}: sound index exceeds reservation')
        paths = [mod/f for f in files.values()]
        if len(set(paths)) != len(paths):
            raise ValueError(f'{name}: duplicate output path')
        expected = set(paths)
        if set(mod.rglob('*.ogg')) != expected:
            raise ValueError(f'{name}: unreferenced or missing audio')
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            signals = list(pool.map(decode, paths))
        sets = {s['type']:s for s in rule.get('voiceSets',[])}
        counts = {}
        for sid, s in sets.items():
            counts[sid] = {}
            for ev in ('selectUnit','startMoving','selectWeapon','annoyed'):
                indices = s.get(ev, [])
                if not indices or not set(indices) <= set(files):
                    raise ValueError(f'{name}/{sid}/{ev}: missing sound')
                counts[sid][ev] = len(indices)
        for section, fields in [('soldiers',('voiceSetsMale','voiceSetsFemale')),('units',('voiceSets',))]:
            for item in rule.get(section,[]):
                for field in fields:
                    if not set(item.get(field,[])) <= set(sets):
                        raise ValueError(f'{name}: unknown voice set in {item}')
        report[name] = dict(files=len(files), sets=len(sets), mb=round(sum(s['bytes'] for s in signals)/1024**2,2),
                            max_peak_db=max(s['peak_db'] for s in signals), events=counts, signals=signals)
        print(name, {k:v for k,v in report[name].items() if k not in ('events','signals')})
    out = ROOT/'art/sfx/voicepack/export-audit.json'
    out.write_text(json.dumps(report,ensure_ascii=False,indent=1),encoding='utf-8-sig')


if __name__ == '__main__':
    main()
