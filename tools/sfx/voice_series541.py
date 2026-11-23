"""XP-000541: серия голосов типов бойцов (46 тонов V158-V203) по пайплайну пилота (voice_pilot541.py).

Опорный тембр: 31 принятый в прошлом круге - готовый опорный из V###/voice.json (текст референса для ESpeech - с
ударениями); V173, V179, V201, V203 - опорные пилота; 11 (V166 V169 V170 V172 V174 V175 V180 V194 V197 V198 V202) -
новый опорный VoxCPM2 design по педии (docs/research/voice-types-pedia.md).
Реплики: все 42 реплики базового голоса из xp541_text.tsv (ударения_итог), ESpeech; вопрос - по критерию всей фразы
(voice_pilot541.rises), до 6 дублей ESpeech + 6 VoxCPM2 (всего не больше 12); без вопроса - до 4 дублей, пока whisper
не даст похожесть >= 0,8; микропаузы; обработка ламии и Чертовки.
Выход: art/sfx/voicepack/V###/xp541/<n>.ogg (+ <n>.proc.ogg); V201 и V203 - только proc (выбор Vitali 10.11).
Готовые реплики пропускаются (rows.json в папке xp541 пишется после каждой реплики), поэтому упавшую пачку можно
просто поставить ещё раз. Общая таблица census/tickets/XP-000541/series.tsv.

Только через очередь видеокарты:
    py -3 tools/gpuq.py add --name voices-xp541-s01 --prio 5 -- D:/VoiceFactory/runtime/venv/Scripts/python.exe -u tools/sfx/voice_series541.py --voices V158,V166
"""
import argparse
import csv
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import voice_pilot541 as P                       # noqa: E402
from voice_pilot541 import (G, GV, PZ, C, Q, SR, OUT_SR, ROOT, PAUSE_TAB, PROC, PROC_LEVELS, TIMBRE_WORD,  # noqa: E402
                            plain, to_sr, trim, finalize, write_ogg, words_of, closeness_words, mismatches,
                            question_ends, rises)
import numpy as np                               # noqa: E402
import soundfile as sf                           # noqa: E402

log = logging.getLogger("voice_series541")
PACK = ROOT / "art/sfx/voicepack"
SERIES_TSV = ROOT / "census/tickets/XP-000541/series.tsv"
PILOT = ROOT / "census/tickets/XP-000541/pilot"
CLOSE_OK = 0.80                                  # похожесть whisper < 0,8 - дубль
ESP_Q, VOX_Q, ESP_N = 6, 6, 4                    # дублей: вопрос 6+6 (<=12), без вопроса до 4

TONES = ROOT / "tools/sfx/voice_tones.tsv"
NEW_REF = "V166 V169 V170 V172 V174 V175 V180 V194 V197 V198 V202".split()
PILOT_REF = "V173 V179 V201 V203".split()
PROC_VOICE = {"V201": "lamia", "V202": "lamia", "V203": "chort"}
VARIANTS = {"V201": ["proc"], "V202": ["proc"], "V203": ["proc"]}      # выбор Vitali 10.11: ламии и Чертовка - только proc
EXTRA = False                                    # --extra: реплики 043-126 (без флага - 01-42)
SPEED = {"V201": 0.92, "V202": 0.92, "V203": 0.92, "V173": 0.95, "V174": 0.95, "V194": 0.93}
FEM = (195, 420)

DESIGN = {
    "V166": TIMBRE_WORD + ". Персонаж: Странненькая - девушка-чародейка с даром Вуду, расплатившаяся за силу. Ровный "
            "отстранённый голос, будто видит то, чего нет; о жутком говорит буднично, как о погоде; странность как дар "
            "и как шрам, без детской светлости и наивности.",
    "V169": TIMBRE_WORD + ". Персонаж: Кающаяся - молодая женщина, чьё покаяние продлится до смерти. Тихий молитвенный "
            "голос, ровный, с дрожью искренней вины; кается всерьёз, на слове про бой невольно оживляется.",
    "V170": TIMBRE_WORD + ". Персонаж: Кающаяся - женщина лет тридцати. Твёрдый строгий голос, молитвенная чеканка, каждое "
            "слово отчётливо; вина и упрямая сила вместе, радость боя прорывается коротким выдохом.",
    "V172": TIMBRE_WORD + ". Персонаж: Кающаяся - девушка лет двадцати. Горячий сбивчивый голос, фанатичная искренность; "
            "торопится покаяться и тут же рвётся в бой, срывы вины, темп быстрый; вопрос задаёт по-настоящему.",
    "V202": TIMBRE_WORD + ". Персонаж: ламия-змееженщина, зрелая величавая воительница. Спокойное достоинство, бархатный "
            "голос, ленивая угроза; шипящие и свистящие «с», «ш», «з», «щ» тянутся протяжно, но слова разборчивы; "
            "не театральное шипение на каждом слове, темп медленный.",
    "V174": "мужской голос, мужчина, голос выше среднего. Персонаж: молодой раб-солдат, мужчина лет двадцати пяти, которого "
            "дисциплиной и тренировкой пробудили к воинскому духу; поначалу слаб, но старается. Ломкий звонкий голос, "
            "короткие фразы, послушание, без бравады; не женский голос.",
    "V175": "мужской голос, мужчина. Персонаж: бывалый солдат-чистокровка, мужчина лет сорока, бывший гуманист в броне "
            "Защитник. Плотный глуховатый голос, закалка, ворчит сквозь зубы, короткие фразы, без бравады; не женский голос.",
    "V180": "мужской голос, мужчина. Персонаж: герой, живая легенда, мужчина лет сорока пяти. Бархатный баритон, пафос "
            "держится на делах, а не на хвастовстве; интонации с иронией над собой и усталостью, темп размеренный; не фальцет.",
    "V194": "мужской голос, мужчина, голос ниже среднего. Персонаж: огр-сержант, редкий подвид здоровяков, не стареет, "
            "беседует с богом разрушения о смысле жизни. Низкий гулкий голос, размеренный и рассудительный, философская "
            "неспешность, без рычания и звериного рыка; слова разборчивы.",
    "V197": "мужской голос, мужчина, голос выше среднего. Персонаж: лупоглаз, гибрид ретикулянина и человека, худой молодой "
            "мужчина. Тонкий носовой сухой голос, нервный и умный, осторожная въедливость; мужской, не женский голос.",
    "V198": "мужской голос, мужчина, голос выше среднего. Персонаж: лупоглаз, гибрид ретикулянина и человека, мужчина лет "
            "сорока. Сухой носовой голос, занудный и педантичный, поправляет чужие мысли вслух; мужской, не женский голос.",
}
Q_INSTR = {"Ж": "женский голос, вопросительная интонация, подъём тона к концу вопроса, живо",
           "М": "мужской голос, вопросительная интонация, подъём тона к концу вопроса, живо",
           "Н": "женский хриплый утробный голос чертовки, вопросительная интонация, подъём тона в конце вопроса"}


def tone_table():
    out = {}
    with open(TONES, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            out[r["id"]] = r
    return out


def config(vid, tr):
    r = tr[vid]
    cfg = dict(name=vid, base=r["base"], sex=r["sex"], speed=SPEED.get(vid, 1.0), proc=PROC_VOICE.get(vid),
               variants=VARIANTS.get(vid, ["plain"]), q_instr=Q_INSTR[r["sex"]])
    if vid in PILOT_REF:
        cfg["ref_wav"] = PILOT / vid / "_work" / "ref.chosen.wav"
        cfg["q_instr"] = P.VOICES[vid]["q_instr"]
    elif vid in NEW_REF:
        cfg["design"] = DESIGN[vid]
        if r["sex"] == "Ж":
            cfg.update(f0=FEM, f3_min=2550)
        else:
            t = float(r["f0"])
            cfg.update(f0=(t * 0.72, t * 1.35), f3_max=2500)
    else:
        d = json.loads((PACK / vid / "voice.json").read_text(encoding="utf-8-sig"))
        cfg["ref_wav"] = PACK / d["ref"]
    return cfg


class Series(P.Pilot):
    def __init__(self, cfg):
        super().__init__(cfg)
        self.tr = tone_table()
        self.ref_tex = self.refs

    def take_row_key(self, c, nq):
        sc = sum(min(max(r["peak"], 0.0), 6.0) + min(max(r["end"], -3.0), 3.0) for r in c["q"])
        return (float(np.abs(c["wav"]).max()) > 0.02, c["close"] >= CLOSE_OK, c["npass"], round(sc, 1),
                c["tag"].startswith("esp") and c["close"] >= CLOSE_OK, c["close"])

    def line2(self, vid, cfgv, n, vprof, eprof, work):
        text, acc = self.lines[(cfgv["base"], n)]
        pl = plain(acc)
        nq = len(question_ends(pl))
        takes = []

        def add(tag, wav):
            path = work / ("%s.%s.wav" % (n, tag))
            sf.write(str(path), wav, SR, subtype="PCM_16")
            words = words_of(path)
            c = {"tag": tag, "wav": wav, "path": path, "words": words, "close": closeness_words(pl, words),
                 "q": rises(wav, pl, words, acc=acc)}
            c["npass"] = sum(r["ok"] for r in c["q"])
            c["key"] = self.take_row_key(c, nq)
            takes.append(c)
            log.info("%s %s %s: близость %.2f, вопросы %s", vid, n, tag, c["close"],
                     ["%s%s %+.1f/%+.1f" % ("да" if r["ok"] else "нет", r["kind"], r["peak"], r["end"]) for r in c["q"]])
            return c

        def good(c):
            return c["close"] >= CLOSE_OK and c["npass"] == nq

        for s in range(1, (ESP_Q if nq else ESP_N) + 1):
            add("esp%d" % s, self.esp_take(eprof, acc, s, cfgv["speed"]))
            if good(takes[-1]):
                break
        first_pass = takes[0]["npass"]
        if nq and not any(good(c) for c in takes):
            for s in range(1, VOX_Q + 1):
                add("vox%d" % s, self.vox_take(vprof, pl, P.SEED_VOX + s, cfgv["q_instr"]))
                if good(takes[-1]):
                    break
        if not nq and not any(good(c) for c in takes):
            # XP-000541 (10.11): ESpeech на репликах в 1-2 слова даёт тишину (whisper «продолжение следует») - запасной VoxCPM2
            st_instr = cfgv["q_instr"].split("вопросительная")[0] + "утвердительная интонация, коротко и чётко"
            for s in range(1, VOX_Q + 1):
                add("vox%d" % s, self.vox_take(vprof, pl, P.SEED_VOX + s, st_instr))
                if good(takes[-1]):
                    break
        best = max(takes, key=lambda c: c["key"])
        return dict(n=n, text=text, acc=acc, pl=pl, nq=nq, best=best, takes=takes, first_pass=first_pass)

    def emit2(self, vid, cfgv, kind, n, acc, pl, wav, engine_tag, variant, outdir, work, extra, ndub, secs):
        words = extra["words"]
        pw, ins = PZ.apply(wav, SR, pl, words, pauses=PAUSE_TAB)
        added = int(round((len(pw) - len(wav)) / SR * 1000))
        stem = "ref" if kind == "ref" else n
        base = stem + (".proc" if variant == "proc" else "")
        chk = work / (stem + "." + variant + ".final.wav")
        plain_close = closeness_words(pl, words)
        info = "-"
        levels = PROC_LEVELS if variant == "proc" else [None]
        for li, lv in enumerate(levels):
            if lv is None:
                y, lufs = finalize(pw)
            else:
                pr, info = PROC[cfgv["proc"]](pw, lv)
                y, lufs = finalize(pr)
            sf.write(str(chk), y, OUT_SR, subtype="PCM_16")
            cj = chk.with_name(chk.name + ".words.json")
            if cj.exists():
                cj.unlink()
            fw = PZ.word_times(str(chk))
            if lv is None or closeness_words(pl, fw) >= max(0.8, plain_close - 0.08) or li == len(levels) - 1:
                break
        write_ogg(outdir / (base + ".ogg"), y)
        q = extra["q"]
        qtxt = "; ".join("%s %s %+.1f/%+.1f" % ("да" if r["ok"] else "нет", r["kind"], r["peak"], r["end"])
                         for r in q) or "-"
        return {"голос": vid, "вид": kind, "n": n, "текст_с_ударениями": acc, "вариант": variant,
                "движок": engine_tag, "f0_ср_Гц": G.pitch(y, OUT_SR), "вопросов": len(q),
                "подъём_да_нет(вид пик/конец,пт)": qtxt, "вопросов_прошло": sum(r["ok"] for r in q),
                "дублей": ndub, "время_с": round(secs, 1),
                "паузы_вставлено_мс": "%d (%d мест)" % (added, ins), "обработка": info, "LUFS": round(lufs, 1),
                "whisper": " ".join(w for w, _, _ in fw), "похожесть": round(closeness_words(pl, fw), 2),
                "расхождения": " ".join(mismatches(pl, fw)),
                "файл": str((outdir / (base + ".ogg")).relative_to(ROOT)).replace("\\", "/")}

    def ref_for(self, vid, cfgv, work):
        pf = work / "ref.chosen.wav"
        if pf.exists():
            wav, sr = sf.read(str(pf), dtype="float32")
            path = work / "ref.chosen.wav"
            words = words_of(path)
            ref_acc = self.refs[vid]
            return {"wav": wav, "path": path, "words": words, "k": 0,
                    "q": rises(wav, plain(ref_acc), words, acc=ref_acc)}
        ref_acc = self.refs[vid]
        if "ref_wav" in cfgv:
            wav, sr = sf.read(str(cfgv["ref_wav"]), dtype="float32")
            if wav.ndim > 1:
                wav = wav.mean(1)
            wav = trim(to_sr(wav, sr))
            sf.write(str(pf), wav, SR, subtype="PCM_16")
            words = words_of(pf)
            return {"wav": wav, "path": pf, "words": words, "k": 0,
                    "q": rises(wav, plain(ref_acc), words, acc=ref_acc)}
        best = self.design(vid, cfgv, work)
        sf.write(str(pf), best["wav"], SR, subtype="PCM_16")
        best["path"] = pf
        best["words"] = words_of(pf)
        best["q"] = rises(best["wav"], plain(ref_acc), best["words"], acc=ref_acc)
        return best

    def voice2(self, vid, only=None):
        cfgv = config(vid, self.tr)
        outdir = PACK / vid / "xp541"
        work = outdir / "_work"
        work.mkdir(parents=True, exist_ok=True)
        rp = outdir / "rows.json"
        rows = json.loads(rp.read_text(encoding="utf-8-sig")) if rp.exists() else []
        done = {(r["вид"], r["n"], r["вариант"]) for r in rows}
        nums = sorted(n for (b, n) in self.lines if b == cfgv["base"] and (int(n) >= 43) == EXTRA)
        if only:
            nums = [n for n in nums if n in only]
        variants = cfgv["variants"]
        todo = [n for n in nums if any(("line", n, v) not in done for v in variants)]
        need_ref = any(("ref", "", v) not in done for v in variants)
        if not todo and not need_ref:
            log.info("%s: всё готово, пропуск", vid)
            return
        t0 = time.time()
        best = self.ref_for(vid, cfgv, work)
        ref_acc = self.refs[vid]
        ref_pf = work / "ref.chosen.wav"
        eprof = P.VoiceProfile(vid, "espeech", {"neutral": [{"wav": str(ref_pf), "text": ref_acc}]})
        vprof = P.VoiceProfile(vid, "voxcpm2", {"neutral": [{"wav": str(ref_pf), "text": plain(ref_acc)}]})

        def save():
            rp.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8-sig")

        for var in variants:
            if ("ref", "", var) not in done:
                rows.append(self.emit2(vid, cfgv, "ref", "", ref_acc, plain(ref_acc), best["wav"], "ref", var, outdir, work,
                                       best, 0, 0.0))
        save()
        for n in todo:
            t1 = time.time()
            r = self.line2(vid, cfgv, n, vprof, eprof, work)
            b = r["best"]
            for var in variants:
                if ("line", n, var) in done:
                    continue
                rows.append(self.emit2(vid, cfgv, "line", n, r["acc"], r["pl"], b["wav"], b["tag"], var, outdir, work, b,
                                       len(r["takes"]), time.time() - t1))
            save()
        log.info("%s готов за %.0f с, реплик %d", vid, time.time() - t0, len(todo))


def write_series():
    rows = []
    for p in sorted(PACK.glob("V*/xp541/rows.json")):
        rows += json.loads(p.read_text(encoding="utf-8-sig"))
    if not rows:
        return
    cols = []
    for r in rows:
        for k in r:
            if k not in cols:
                cols.append(k)
    with open(SERIES_TSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter="\t")
        w.writeheader()
        w.writerows(rows)


def pilot_fix():
    """V179 реплика 07 («потОм») в папке пилота: опорный пилота, то же имя файла, строка pilot.tsv."""
    S = Series(C.load(G.VF))
    vid = "V179"
    cfgv = config(vid, S.tr)
    outdir, work = PILOT / vid, PILOT / vid / "_work"
    ref_pf = work / "ref.chosen.wav"
    ref_acc = S.refs[vid]
    eprof = P.VoiceProfile(vid, "espeech", {"neutral": [{"wav": str(ref_pf), "text": ref_acc}]})
    vprof = P.VoiceProfile(vid, "voxcpm2", {"neutral": [{"wav": str(ref_pf), "text": plain(ref_acc)}]})
    r = S.line2(vid, cfgv, "07", vprof, eprof, work)
    b = r["best"]
    row = S.emit2(vid, cfgv, "line", "07", r["acc"], r["pl"], b["wav"], b["tag"], "plain", outdir, work, b,
                  len(r["takes"]), 0.0)
    src = outdir / "07.ogg"
    (outdir / "07.plain.ogg").write_bytes(src.read_bytes())
    row["файл"] = row["файл"].replace("07.ogg", "07.plain.ogg")
    src.unlink()
    row["подъём_да_нет(пик/конец,пт)"] = row.pop("подъём_да_нет(вид пик/конец,пт)")
    row.pop("дублей"), row.pop("время_с")
    rp = outdir / "rows.json"
    rows = json.loads(rp.read_text(encoding="utf-8-sig"))
    rows = [row if (x["вид"] == "line" and x["n"] == "07" and x["вариант"] == "plain") else x for x in rows]
    rp.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8-sig")
    P.write_tsv()
    log.info("пилот V179 07: %s", row["текст_с_ударениями"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--voices", default="")
    ap.add_argument("--only", default="", help="номера реплик через запятую")
    ap.add_argument("--extra", action="store_true", help="реплики 043-126 вместо 01-42")
    ap.add_argument("--pilot-fix", action="store_true")
    a = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if a.pilot_fix:
        pilot_fix()
        Q.free_asr()
        return
    global EXTRA
    EXTRA = a.extra
    S = Series(C.load(G.VF))
    only =set(x for x in a.only.split(",") if x)
    for vid in [v for v in a.voices.split(",") if v]:
        S.voice2(vid, only or None)
        write_series()
    Q.free_asr()
    write_series()
    log.info("series.tsv: %s", SERIES_TSV)


if __name__ == "__main__":
    main()
