"""Пилот «живых» голосов: как снять монотонность с реплик набора (Vitali 19.10: «монотонно бубнят»).

4 голоса x 8 реплик x RU/EN, варианты рядом на одной странице:
  A - как сейчас в игре (выбранный дубль из voice.json, без новой записи);
  B - Fish, сильный тег по событию (выбор, ход, атака, «отстань»);
  F - Fish, свой тег каждой реплике (эмоция по смыслу фразы);
  D - то же, что F, плюс температура выборки выше (1.0 / top_p 0.9);
  C - то же, что F, но опорный клип эмоциональный: на событие свой, снят Fish с сильным тегом;
  E - VoxCPM2, управляемое клонирование: опорный голос + инструкция в скобках.
В новых вариантах из дублей берётся самый выразительный (разброс высоты в полутонах + динамика)
среди годных: в полосе высоты, не длиннее LINE_MAX_S, распознан близко к тексту.

Выход: art/sfx/voicepack/emotion_pilot/<вариант>/<V###>/<lang>_<NN>.t<k>.wav, pilot.json, index.html.
Только через очередь видеокарты:
    py -3 tools/gpuq.py add --name voice-emotion-pilot -- D:/VoiceFactory/runtime/venv/Scripts/python.exe tools/sfx/voice_emotion_pilot.py
Страница заново без видеокарты: ... voice_emotion_pilot.py --page
"""
import argparse
import html
import json
import logging
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gen_voicepack as P                        # noqa: E402  (G, judge, band_ok, состояние голосов)
import voice_script                              # noqa: E402
import numpy as np                               # noqa: E402
import soundfile as sf                           # noqa: E402
from vf.engines.base import GenParams, VoiceProfile   # noqa: E402

G = P.G
log = logging.getLogger("emotion_pilot")
OUT = P.OUT / "emotion_pilot"
TAKES = 4
VOX_TAKES = 3
REF_TAKES = 6
LINE_MAX_S = 3.5                                 # эмоция тянет слова - пилоту запас полсекунды
CLOSE_MIN = 0.75
SEED = 7100

PART_STRONG = {"Выбор бойца": "[eager, lively, grinning]",
               "Приказ и движение": "[energetic, determined, loud]",
               "Перед атакой": "[shouting, aggressive, excited]",
               "Повторные нажатия": "[annoyed, exasperated, loud sigh]"}

# реплики пилота и тег каждой (Fish S2 понимает теги словами по-английски)
LINES = {
    "V001": {"09": "[cheeky, eager, grinning]", "13": "[smug, flirty purr]",
             "21": "[shouting, energetic]", "22": "[sarcastic, lazy drawl]",
             "27": "[laughing, excited]", "33": "[shouting, aggressive]",
             "36": "[annoyed, threatening growl]", "39": "[exasperated, loud]"},
    "V033": {"08": "[gruff, impatient]", "11": "[smug, low voice]",
             "13": "[curt, determined]", "14": "[skeptical, grumbling]",
             "18": "[menacing, focused]", "19": "[cold, cruel smirk]",
             "21": "[irritated sigh]", "23": "[angry, threatening]"},
    "V099": {"07": "[playful, seductive]", "11": "[proud, teasing]",
             "13": "[giggling, teasing]", "15": "[whispering, sly]",
             "17": "[menacing, sultry]", "19": "[evil laugh, triumphant]",
             "22": "[mocking, bored]", "24": "[amused, scolding]"},
    "V140": {"09": "[apologetic, slightly amused]", "10": "[proud, cheerful]",
             "13": "[eager, polite]", "16": "[awkward, apologetic]",
             "17": "[polite but menacing]", "20": "[solemn, then shouting]",
             "22": "[strained politeness, annoyed]", "24": "[offended, huffy]"},
}
VARIANTS = [("A", "как сейчас в игре"),
            ("B", "Fish: сильный тег по событию"),
            ("F", "Fish: свой тег каждой реплике"),
            ("D", "F + температура выше"),
            ("C", "F + эмоциональный опорный на событие"),
            ("E", "VoxCPM2: опорный + инструкция")]


def expr(wav, sr):
    """Выразительность: разброс высоты (полутона, pyin) и динамика громкости (дБ, 95-й минус 20-й процентиль)."""
    import librosa
    y = np.asarray(wav, dtype=np.float32)
    f0, voiced, _ = librosa.pyin(y, fmin=60, fmax=500, sr=sr, frame_length=2048)
    f0 = f0[voiced & ~np.isnan(f0)]
    st = float(np.std(12 * np.log2(f0 / np.median(f0)))) if len(f0) > 4 else 0.0
    hop = int(sr * 0.025)
    fr = librosa.util.frame(np.pad(y, (0, hop)), frame_length=hop, hop_length=hop)
    db = 20 * np.log10(np.sqrt((fr ** 2).mean(0)) + 1e-9)
    db = db[db > db.max() - 40]
    dyn = float(np.percentile(db, 95) - np.percentile(db, 20)) if len(db) else 0.0
    return {"st": round(st, 2), "dyn": round(dyn, 1), "expr": round(st + dyn / 10, 2)}


def rel(path):
    return str(Path(path).relative_to(OUT)).replace("\\", "/")


def voices():
    allv = {v["id"]: v for v in voice_script.parse()}
    out = []
    for vid, tags in LINES.items():
        v = allv[vid]
        st = P.load_state(v)
        lines = [dict(ln, tag=tags[ln["n"]]) for ln in v["lines"] if ln["n"] in tags]
        out.append((v, st, lines))
    return out


def take(v, eng, text, prof, params, path):
    wav, sr, _ = eng.generate(text, prof, params)
    wav = G.post(wav, sr)
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), wav, sr, subtype="PCM_16")
    return dict(file=rel(path), dur=round(len(wav) / sr, 2), **P.judge(v, wav, sr), **expr(wav, sr))


def copy_current(vs, items):
    for v, st, lines in vs:
        cur = {(it["lang"], it["n"]): it for it in st["lines"] if it.get("chosen")}
        for ln in lines:
            for lang in ("ru", "en"):
                it = cur.get((lang, ln["n"]))
                if not it:
                    continue
                dst = OUT / "A" / v["id"] / f"{lang}_{ln['n']}.wav"
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(P.OUT / it["file"], dst)
                wav, sr = sf.read(str(dst), dtype="float32")
                items.append(dict(var="A", id=v["id"], n=ln["n"], lang=lang, text=ln[lang], file=rel(dst),
                                  dur=it["dur"], band=it["band"], f0=it["f0"], close=it.get("close", 0),
                                  **expr(wav, sr)))


def fish_refs(eng, vs, refs):
    """C: на каждое событие голоса - эмоциональный опорный той же фразой, Fish с сильным тегом, самый живой в полосе."""
    eng.cfg.update(temperature=0.9, top_p=0.85)
    for v, st, lines in vs:
        base = VoiceProfile(v["id"], "fish", {"neutral": [{"wav": str(P.OUT / st["ref"]), "text": st["ref_text"]}]})
        for part in sorted({ln["part"] for ln in lines}):
            best = None
            for k in range(REF_TAKES):
                path = OUT / "C" / v["id"] / "ref" / f"{list(PART_STRONG).index(part)}.t{k + 1}.wav"
                r = take(v, eng, st["ref_text"], base, GenParams(instruction=PART_STRONG[part], seed=SEED + 50 + k),
                         path)
                if r["band"] and 3.0 <= r["dur"] <= 12.0 and (best is None or r["expr"] > best["expr"]):
                    best = r
            refs[(v["id"], part)] = best
            log.info("%s %s: опорный %s", v["id"], part, best and best["file"])


def fish_pass(vs, items, refs):
    eng = G.engine(G.C.load(G.VF), "fish", compile=True)
    base_cfg = dict(eng.cfg)
    for var in ("B", "F", "D"):
        eng.cfg.clear()
        eng.cfg.update(base_cfg)
        if var == "D":
            eng.cfg.update(temperature=1.0, top_p=0.9)
        for v, st, lines in vs:
            prof = VoiceProfile(v["id"], "fish", {"neutral": [{"wav": str(P.OUT / st["ref"]), "text": st["ref_text"]}]})
            for ln in lines:
                tg = PART_STRONG[ln["part"]] if var == "B" else ln["tag"]
                for lang in ("ru", "en"):
                    for k in range(TAKES):
                        path = OUT / var / v["id"] / f"{lang}_{ln['n']}.t{k + 1}.wav"
                        r = take(v, eng, ln[lang], prof, GenParams(instruction=tg, seed=SEED + k), path)
                        items.append(dict(var=var, id=v["id"], n=ln["n"], lang=lang, text=ln[lang], tag=tg, **r))
        log.info("вариант %s готов", var)
    fish_refs(eng, vs, refs)
    eng.cfg.clear()
    eng.cfg.update(base_cfg)
    for v, st, lines in vs:
        for ln in lines:
            ref = refs.get((v["id"], ln["part"]))
            if not ref:
                continue
            prof = VoiceProfile(v["id"], "fish", {"neutral": [{"wav": str(OUT / ref["file"]), "text": st["ref_text"]}]})
            for lang in ("ru", "en"):
                for k in range(TAKES):
                    path = OUT / "C" / v["id"] / f"{lang}_{ln['n']}.t{k + 1}.wav"
                    r = take(v, eng, ln[lang], prof, GenParams(instruction=ln["tag"], seed=SEED + k), path)
                    items.append(dict(var="C", id=v["id"], n=ln["n"], lang=lang, text=ln[lang], tag=ln["tag"],
                                      **r))
    log.info("вариант C готов")
    G.free(eng)


def vox_pass(vs, items):
    local = G.VF + "/models/openbmb/VoxCPM2"
    eng = G.engine(G.C.load(G.VF), "voxcpm2", local_dir=local if Path(local).is_dir() else "")
    for v, st, lines in vs:
        prof = VoiceProfile(v["id"], "voxcpm2", {"neutral": [{"wav": str(P.OUT / st["ref"]), "text": st["ref_text"]}]})
        for ln in lines:
            ins = ln["tag"].strip("[]")
            for lang in ("ru", "en"):
                for k in range(VOX_TAKES):
                    path = OUT / "E" / v["id"] / f"{lang}_{ln['n']}.t{k + 1}.wav"
                    p = GenParams(instruction=ins, seed=SEED + k, cfg_value=2.0, inference_timesteps=10,
                                  style="neutral", extra={"force_controllable": True})
                    try:
                        r = take(v, eng, ln[lang], prof, p, path)
                    except Exception as e:
                        log.warning("E %s %s %s: %s", v["id"], lang, ln["n"], e)
                        continue
                    items.append(dict(var="E", id=v["id"], n=ln["n"], lang=lang, text=ln[lang], tag=ins, **r))
    log.info("вариант E готов")
    G.free(eng)


def asr_pick(items):
    from vf import qc as Q
    groups = {}
    for it in items:
        if it["var"] != "A":
            it["heard"] = G.heard(OUT / it["file"], it["lang"])
            it["close"] = round(G.closeness(it["text"], it["heard"]), 3)
            groups.setdefault((it["var"], it["id"], it["lang"], it["n"]), []).append(it)
        else:
            it["chosen"] = True
    for tk in groups.values():
        ok = lambda t: t["band"] and t["dur"] <= LINE_MAX_S and t["close"] >= CLOSE_MIN   # noqa: E731
        best = max(tk, key=lambda t: (ok(t), t["expr"] if ok(t) else t["close"]))
        best["chosen"] = True
    Q.free_asr()


def page(items):
    ch = {(it["var"], it["id"], it["lang"], it["n"]): it for it in items if it.get("chosen")}
    vs = voices()
    mean = {}
    for var, _ in VARIANTS:
        xs = [it["expr"] for it in ch.values() if it["var"] == var]
        mean[var] = round(sum(xs) / len(xs), 2) if xs else 0
    head = "".join(f"<th>{var}<br><small>{html.escape(d)}<br>живость {mean[var]}</small></th>" for var, d in VARIANTS)
    rows = []
    for v, st, lines in vs:
        rows.append(f"<tr class=v><td colspan={len(VARIANTS) + 1}>{v['id']} — {html.escape(v['name'])}</td></tr>")
        for ln in lines:
            for lang in ("ru", "en"):
                cells = []
                for var, _ in VARIANTS:
                    it = ch.get((var, v["id"], lang, ln["n"]))
                    if not it:
                        cells.append("<td>—</td>")
                        continue
                    warn = "" if it["band"] and it["dur"] <= LINE_MAX_S and it.get("close", 1) >= CLOSE_MIN else " bad"
                    cells.append(f"<td class='a{warn}'><audio controls preload=none src='{it['file']}'></audio>"
                                 f"<small>{it['expr']} · {it['dur']} с · {it['f0']:.0f} Гц</small></td>")
                tag = html.escape(ln["tag"]) if lang == "ru" else ""
                rows.append(f"<tr><td class=t>{ln['n']} {lang.upper()}<br><b>{html.escape(ln[lang])}</b>"
                            f"<br><small>{html.escape(ln['part'])} {tag}</small></td>{''.join(cells)}</tr>")
    doc = f"""<!doctype html><meta charset=utf-8><title>Живые голоса — пилот</title>
<style>body{{font:14px sans-serif;margin:16px;background:#fff;color:#111}}table{{border-collapse:collapse}}
td,th{{border:1px solid #ccc;padding:4px;vertical-align:top}}th{{background:#eee;position:sticky;top:0}}
tr.v td{{background:#335;color:#fff;font-weight:bold}}td.t{{max-width:220px}}audio{{width:180px;display:block}}
td.bad{{background:#fde}}small{{color:#555}}</style>
<h2>Живые голоса — пилот {time.strftime('%d.%m %H:%M')}</h2>
<p>Каждая строка — одна реплика, столбцы — способы записи. «Живость» — разброс высоты в полутонах плюс
динамика громкости/10 (больше — живее). Розовая ячейка — дубль не прошёл полосу высоты, длину или распознавание.</p>
<table><tr><th>реплика</th>{head}</tr>{''.join(rows)}</table>"""
    (OUT / "index.html").write_text(doc, encoding="utf-8-sig")
    log.info("страница: %s; живость по вариантам: %s", OUT / "index.html", mean)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--page", action="store_true", help="только страница по pilot.json")
    a = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    man = OUT / "pilot.json"
    if a.page:
        page(json.loads(man.read_text(encoding="utf-8-sig")))
        return
    t0 = time.time()
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    vs = voices()
    items, refs = [], {}
    copy_current(vs, items)
    fish_pass(vs, items, refs)
    vox_pass(vs, items)
    asr_pick(items)
    man.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8-sig")
    page(items)
    log.info("пилот готов за %.0f мин, дублей %d", (time.time() - t0) / 60, len(items))


if __name__ == "__main__":
    main()
