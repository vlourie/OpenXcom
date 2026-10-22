"""Голоса по оригиналу игры (Vitali 21.10: «собирай ОРИГИНАЛЬНЫЕ»): опорный клип из речи Пираток, проба клона.

Для каждого нашего голоса, у типа бойца которого в игре есть свои английские записи, опорный клип склеивается
из речи оригинала (art/sfx/voicepack/game_clips.tsv). Где в группе несколько источников (семейства имён файлов),
кандидатов несколько - выбор на слух. Проба: 4 реплики сотни (2 выбора, 2 движения) RU+EN, VoxCPM2 управляемым
клонированием (как вариант E), из дублей - самый живой из распознанных близко к тексту.

Выход: art/sfx/voicepack/game_probe/<V###>/<кандидат>/ref.wav, <lang>_<n>.t<k>.wav, probe.json, index.html.
Только через очередь видеокарты:
    py -3 tools/gpuq.py add --name voice-game-probe -- D:/VoiceFactory/runtime/venv/Scripts/python.exe tools/sfx/game_voice_probe.py
Опорные и страница без видеокарты: ... game_voice_probe.py --refs | --page
"""
import argparse
import csv
import html
import json
import logging
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gen_voicepack as P                        # noqa: E402
import voice_script                              # noqa: E402
import numpy as np                               # noqa: E402
import soundfile as sf                           # noqa: E402

G = P.G
log = logging.getLogger("game_probe")
ROOT = P.ROOT
SND = ROOT / "Пиратки/Dioxine_XPiratez/user/mods/Piratez/Resources/Sounds"
CLIPS = P.OUT / "game_clips.tsv"
OUT = P.OUT / "game_probe"
SR = 24000
REF_MAX_S = 14.0
TAKES = 3
CLOSE_MIN = 0.75
SEED = 7300

# кандидаты опорного: имя -> клипы (папка/файл). Семейства - по префиксу имени файла (свой источник)
D = "Distress/"
CAND = {
    "gal": [D + "Gal Panic/" + f for f in ("Finish.wav", "getout.wav", "hurryup.wav", "loadshit.wav", "raynec.wav",
                                           "useme.wav", "wrthlss.wav")]
           + [D + "Gal Berserk/" + f for f in ("bon.wav", "fry.wav", "Play.wav", "tohell.wav")],
    "ss_fly": [D + "SS Panic/FlyE.wav", D + "SS Berserk/FlyZ.wav"],
    "ss_blade": [D + "SS Panic/BladeOhShit.wav", D + "SS Panic/BladeFukyou.wav", D + "SS Berserk/JonA.wav"],
    "ss_ffsm": [D + "SS Panic/ffsmindignity2.wav", D + "SS Berserk/ffsmhowdare2.wav", D + "SS Panic/Xan9.wav"],
    "pea_sb": [D + "PEA Panic/" + f for f in ("SBboring.wav", "SBohdear.wav", "SBwhatthe.wav")]
              + [D + "PEA Berserk/" + f for f in ("SBsayonara.wav", "SBlaugh.wav")],
    "pea_piss": [D + "PEA Panic/Piss2.wav", D + "PEA Panic/Piss4.wav", D + "PEA Panic/Ufemh.wav"],
    "hybm_dl": [D + "Hybrid M Panic/" + f for f in ("dlothergetalong.wav", "dlothergetangry.wav",
                                                    "dltunbelievable.wav", "dlffholyshit.wav")],
    "hybm_rev": [D + "Hybrid M Berserk/" + f for f in ("RevFrF00.wav", "RevOth08.wav", "RevTnt01.wav")],
    "hybf_taki": [D + "Hybrid F Panic/" + f for f in ("taki2.wav", "taki3.wav", "takid.wav", "takiw.wav")]
                 + [D + "Hybrid F Berserk/" + f for f in ("taki1.wav", "takip.wav")],
    "hybf_tira": [D + "Hybrid F Panic/tirat.wav", D + "Hybrid F Berserk/tirao.wav"],
    "lok_lina": [D + "Loknar Panic/linas.wav", D + "Loknar Panic/linat.wav", D + "Loknar Berserk/linav.wav"],
    "lok_alora": [D + "Loknar Panic/Alorad.wav", D + "Loknar Berserk/Aloraa.wav", D + "Loknar Panic/Alora5.wav"],
    "lok_misc": [D + "Loknar Panic/" + f for f in ("getblownup.wav", "hardwork.wav", "rubbish.wav", "sense.wav")]
                + [D + "Loknar Berserk/" + f for f in ("easinoff.wav", "smartypants.wav")],
    "gnome": [D + "Gnome Panic/Boxxybn.wav", D + "Gnome Panic/Boxxycb.wav", D + "Gnome Berserk/Boxxyrb.wav"],
    "neko": ["Catgrrrls/Neko Berserk/CGchangemind.ogg", "Catgrrrls/Neko Panic/CGhelp.ogg",
             "Catgrrrls/Neko Berserk/CGisteric2.ogg", "Catgrrrls/NekoHmmm.ogg"],
    "caleb": ["Caleb/T0253c.wav", "Caleb/T0270c.wav", "Caleb/T0286c.wav", "Caleb/T0273c.wav"],
    "kb": ["KB/" + f for f in ("KB_select1.wav", "KB_select3.wav", "KB_select4.wav", "KB_move1.wav", "KB_move2.wav",
                               "KB_move3.wav", "KB_move5.wav", "KB_aim1.wav", "KB_aim4.wav")],
    "xenf": ["XENF/" + f for f in ("XENF_aim1.ogg", "XENF_aim2.ogg", "XENF_confus.ogg", "XENF_move1.ogg",
                                   "XENF_move2.ogg", "XENF_select1.ogg", "XENF_select2.ogg", "XENF_aim3.ogg")],
}
# наш голос -> кандидаты (тип бойца в игре - tools/sfx/game_voice_match.GROUPS)
VOICES = {"V001": ["gal"], "V002": ["gal"], "V003": ["gal"], "V004": ["gal"], "V005": ["gal"],
          "V006": ["ss_fly", "ss_blade", "ss_ffsm"], "V007": ["ss_fly", "ss_blade", "ss_ffsm"],
          "V008": ["pea_sb", "pea_piss"], "V009": ["pea_sb", "pea_piss"],
          "V010": ["hybm_dl", "hybm_rev"], "V011": ["hybf_taki", "hybf_tira"],
          "V012": ["lok_lina", "lok_alora", "lok_misc"], "V013": ["gnome"],
          "V014": ["neko"], "V015": ["neko"], "V016": ["neko"], "V017": ["neko"],
          "V018": ["caleb"], "V025": ["kb"], "V026": ["xenf"]}
PICK = (0, 20)                                   # какие по счёту реплики сотни в каждом событии


def rel(path):
    return str(Path(path).relative_to(OUT)).replace("\\", "/")


def heard_text():
    t = {}
    with open(CLIPS, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            t[r["dir"] + "/" + r["file"]] = r["heard"]
    return t


def build_refs():
    """Опорные кандидатов: речь без тишины по краям, пик -1 дБ, паузы 0,3 с, не длиннее REF_MAX_S."""
    import librosa
    heard = heard_text()
    out = {}
    for name, files in CAND.items():
        parts, text, total = [], [], 0.0
        gap = np.zeros(int(SR * 0.3), dtype=np.float32)
        for fn in files:
            y, _ = librosa.load(str(SND / fn), sr=SR, mono=True)
            y, _ = librosa.effects.trim(y, top_db=35)
            if total + len(y) / SR > REF_MAX_S and parts:
                break
            y = y / (np.abs(y).max() + 1e-9) * 0.89
            parts += [y.astype(np.float32), gap]
            text.append(heard.get(fn, ""))
            total += len(y) / SR + 0.3
        dst = OUT / "refs" / f"{name}.wav"
        dst.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(dst), np.concatenate(parts[:-1]), SR, subtype="PCM_16")
        out[name] = {"file": rel(dst), "text": " ".join(text), "dur": round(total - 0.3, 2), "clips": files[:len(text)]}
        log.info("опорный %s: %.1f с из %d клипов", name, total - 0.3, len(text))
    (OUT / "refs.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8-sig")
    return out


def probe_lines():
    allv = {v["id"]: v for v in voice_script.parse(more=voice_script.MORE100)}
    out = {}
    for vid in VOICES:
        v = allv[vid]
        sel = [ln for ln in v["lines"] if ln.get("tag") and ln["part"] == "Выбор бойца"]
        mov = [ln for ln in v["lines"] if ln.get("tag") and ln["part"] == "Приказ и движение"]
        out[vid] = (v, [sel[i] for i in PICK] + [mov[i] for i in PICK])
    return out


def record(refs, items):
    from vf.engines.base import GenParams, VoiceProfile
    local = G.VF + "/models/openbmb/VoxCPM2"
    eng = G.engine(G.C.load(G.VF), "voxcpm2", local_dir=local if Path(local).is_dir() else "")
    for vid, (v, lines) in probe_lines().items():
        for cand in VOICES[vid]:
            r = refs[cand]
            prof = VoiceProfile(vid, "voxcpm2", {"neutral": [{"wav": str(OUT / r["file"]), "text": r["text"]}]})
            for ln in lines:
                for lang in ("ru", "en"):
                    for k in range(TAKES):
                        path = OUT / vid / cand / f"{lang}_{ln['n']}.t{k + 1}.wav"
                        p = GenParams(instruction=ln["tag"].strip("[]"), seed=SEED + k, cfg_value=2.0,
                                      inference_timesteps=10, style="neutral", extra={"force_controllable": True})
                        try:
                            wav, sr, _ = eng.generate(ln[lang], prof, p)
                        except Exception as e:
                            log.warning("%s %s %s %s: %s", vid, cand, lang, ln["n"], e)
                            continue
                        wav = G.post(wav, sr)
                        path.parent.mkdir(parents=True, exist_ok=True)
                        sf.write(str(path), wav, sr, subtype="PCM_16")
                        items.append(dict(id=vid, cand=cand, n=ln["n"], lang=lang, text=ln[lang], tag=ln["tag"],
                                          part=ln["part"], file=rel(path), dur=round(len(wav) / sr, 2),
                                          **P.expr(wav, sr)))
            log.info("%s %s готов", vid, cand)
    G.free(eng)


def asr_pick(items):
    from vf import qc as Q
    groups = {}
    for it in items:
        groups.setdefault((it["id"], it["cand"], it["lang"], it["n"]), []).append(it)
    for tk in groups.values():
        for t in sorted(tk, key=lambda t: -t["expr"]):
            t["heard"] = G.heard(OUT / t["file"], t["lang"])
            t["close"] = round(G.closeness(t["text"], t["heard"]), 3)
            if t["close"] >= CLOSE_MIN and t["dur"] <= P.LINE_MAX_S + 0.5:
                t["chosen"] = True
                break
        if not any(t.get("chosen") for t in tk):
            max(tk, key=lambda t: t.get("close", 0))["chosen"] = True
    Q.free_asr()


def audio(src, cap, cls=""):
    return (f'<div class="clip {cls}"><audio controls preload="none" src="{html.escape(src)}"></audio>'
            f'<span>{cap}</span></div>')


def page(items, refs):
    ch = {(it["id"], it["cand"], it["lang"], it["n"]): it for it in items if it.get("chosen")}
    body = []
    for vid, (v, lines) in probe_lines().items():
        st = json.loads((P.OUT / vid / "voice.json").read_text(encoding="utf-8-sig"))
        cur = audio(f"../{st['ref']}", "наш голос сейчас (опорный)", "ref") if st.get("ref") else ""
        cands = []
        for cand in VOICES[vid]:
            r = refs[cand]
            cells = [audio(r["file"], f"<b>оригинал «{cand}»</b> {r['dur']} с: {html.escape(r['text'][:140])}", "orig")]
            for ln in lines:
                for lang in ("ru", "en"):
                    it = ch.get((vid, cand, lang, ln["n"]))
                    if not it:
                        continue
                    bad = "" if it.get("close", 0) >= CLOSE_MIN else " bad"
                    cells.append(audio(it["file"], f"{html.escape(ln[lang])} <small>{html.escape(ln['tag'])} · "
                                                   f"{it['dur']} с · живость {it['expr']}</small>", bad))
            cands.append(f'<div class="cand"><h3>{cand}</h3>{"".join(cells)}</div>')
        body.append(f'<section><h2>{vid} — {html.escape(v["name"])}</h2>{cur}<div class="cands">{"".join(cands)}</div>'
                    f'</section>')
    doc = f"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Голоса по оригиналу</title>
<style>
:root {{ --bg:#fff; --fg:#1d1d1f; --mute:#6b6b70; --line:#e2e2e6; --ref:#eef4ff; --orig:#fff4e0; --bad:#fde8ec; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#17171a; --fg:#ececf0; --mute:#9a9aa3; --line:#2c2c31;
  --ref:#1d2636; --orig:#33281a; --bad:#3a1f26; }} }}
body {{ background:var(--bg); color:var(--fg); font:15px/1.45 system-ui, sans-serif; margin:0 auto; max-width:1300px; padding:16px; }}
h2 {{ font-size:18px; border-top:1px solid var(--line); padding-top:16px; }} h3 {{ font-size:14px; margin:8px 0 4px; }}
.cands {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(360px, 1fr)); gap:16px; }}
.clip {{ display:flex; align-items:center; gap:8px; margin:3px 0; border-radius:6px; padding:2px 4px; }}
.clip audio {{ height:30px; flex:0 0 200px; max-width:50%; }} .clip span {{ font-size:13px; }}
small {{ color:var(--mute); }} .ref {{ background:var(--ref); }} .orig {{ background:var(--orig); }} .bad {{ background:var(--bad); }}
</style></head><body>
<h1>Голоса по оригиналу игры — проба {time.strftime('%d.%m %H:%M')}</h1>
<p>Vitali 21.10: «собирай ОРИГИНАЛЬНЫЕ». Оранжевым — опорный клип, склеенный из речи Пираток; под ним — наши
реплики этим голосом (VoxCPM2, клон + подача). Где кандидатов несколько, в группе игры говорят разные люди: выбери,
чей голос брать. Синим — наш голос сейчас. Розовым — дубль распознан далеко от текста.</p>
{"".join(body)}</body></html>"""
    (OUT / "index.html").write_text(doc, encoding="utf-8")
    log.info("страница: %s", OUT / "index.html")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refs", action="store_true", help="только опорные (без видеокарты)")
    ap.add_argument("--page", action="store_true", help="только страница по probe.json")
    a = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    man = OUT / "probe.json"
    if a.page:
        page(json.loads(man.read_text(encoding="utf-8-sig")),
             json.loads((OUT / "refs.json").read_text(encoding="utf-8-sig")))
        return
    if a.refs:
        build_refs()
        return
    t0 = time.time()
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    refs = build_refs()
    items = []
    record(refs, items)
    asr_pick(items)
    man.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8-sig")
    page(items, refs)
    log.info("проба готова за %.0f мин, дублей %d", (time.time() - t0) / 60, len(items))


if __name__ == "__main__":
    main()
