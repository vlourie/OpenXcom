#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""pedia_notes.py - страница досмотра педии: оригинал игры рядом с нашей HD, текст статьи, промпт и заметка.

Зачем (Vitali 29.10): перед перекрафтом педии самому пройти картинки и дописать, что не в порядке.
На карточке: оригинал из Piratez\Resources\Pedia (индекс 0 прозрачен, как в движке, R-043), HD из
mods\hd\hd\UI и, если есть, 18+ из mods\hd\hd_18+\UI; название и текст статьи (pedia_text.json); промпт,
которым серия hd перерисовала бы картинку (pedia_batch.spec_for), - его можно переписать; что нашли
аудит 28.10 (groups.json) и проверка содержания (content_confirmed.tsv, content_check.json).
Оценка, заметка и свой промпт пишутся в art\pedia_regen\review_notes.tsv - только дописываются,
последняя строка по картинке главная. Ничего не генерирует и в мод не пишет.

    py -3.13 tools\hdart\pedia_notes.py            (http://localhost:8783)
    .claude/launch.json: pedia-notes

С --round <круг> (pedia_recraft.py) та же страница показывает только картинки круга и рядом с оригиналом
и нашей HD - кандидатов: «Беру этот», «Ещё раз» (заметка - что не так), «Оставить как было». Выбор пишется
в art\pedia_regen\<круг>\picks.tsv так же, только дописыванием; выбранные уходят из списка.

    py -3.13 tools\hdart\pedia_notes.py --round recraft_v1 --port 8785
"""
import argparse
import csv
import io
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from PIL import Image                                   # noqa: E402

import pedia_batch as pb                                # noqa: E402

ENC = "utf-8-sig"
ORIG = os.path.join(pb.PIR, "Piratez", "Resources", "Pedia")
HD = os.path.join(pb.PIR, "hd", "hd", "UI")
H18 = os.path.join(pb.PIR, "hd", "hd_18+", "UI")
AUDIT = os.path.join("art", "_review", "pedia_audit_2026-10-28")
NOTES = os.path.join(pb.ROOT, "review_notes.tsv")
NOTE_COLS = ("stem", "status", "note", "prompt", "when")
PICK_COLS = ("stem", "pick", "file", "note", "when")       # pick: e1/e2/o1/o2, again - ещё раз, keep - как было
PAGE = os.path.join(HERE, "pedia_notes.html")
GROUPS = {"A_nude": "голая в обычном режиме", "B_skipped": "пропущена как предмет, а это иллюстрация",
          "F_nohd": "нет HD", "C_subst": "подмена (аудит)", "C_review": "подмена? на разбор (аудит)",
          "D_oldpass": "старый проход, не перегенерено", "E_ships": "корабль тёмный или серый",
          "H18_broken": "18+ сломана"}
STRONG_RU = {"gender_changed": "пол", "person_added": "+человек", "person_removed": "−человек",
             "species_changed": "вид", "held_changed": "в руках", "background_changed": "фон"}
LOCK = threading.Lock()


def load_json(path, default):
    try:
        with io.open(path, encoding=ENC) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def clean(s):
    return (s or "").replace("{NEWLINE}", "\n").replace("{ALT}", "")


def by_lower(folder, exts):
    if not os.path.isdir(folder):
        return {}
    return {os.path.splitext(n)[0].lower(): n for n in os.listdir(folder) if os.path.splitext(n)[1].lower() in exts}


def read_notes():
    out = {}
    if os.path.exists(NOTES):
        with io.open(NOTES, encoding=ENC, newline="") as f:
            for r in csv.DictReader(f, delimiter="\t"):
                out[r["stem"].lower()] = r
    return out


def append_note(row):
    new = not os.path.exists(NOTES)
    with LOCK, io.open(NOTES, "a", encoding=ENC, newline="") as f:
        w = csv.DictWriter(f, NOTE_COLS, delimiter="\t", lineterminator="\n")
        if new:
            w.writeheader()
        w.writerow({k: row.get(k, "").replace("\t", " ").replace("\r", "").replace("\n", "\\n") for k in NOTE_COLS})


def build():
    """Все карточки по оригиналам педии, в порядке имён."""
    origs = by_lower(ORIG, (".png", ".gif", ".bmp"))
    hd, h18 = by_lower(HD, (".png",)), by_lower(H18, (".png",))
    text = load_json(os.path.join(pb.ROOT, "pedia_text.json"), {})
    plan = load_json(os.path.join(pb.ROOT, "plan.json"), {}).get("info", {})
    caps = load_json(os.path.join(pb.ROOT, "captions.json"), {})
    check = load_json(os.path.join(pb.ROOT, "content_check.json"), {})
    check = {k.lower(): v for k, v in check.items()}
    groups = {}
    for g, names in load_json(os.path.join(AUDIT, "groups.json"), {}).items():
        for n in names:
            groups.setdefault(n.lower(), []).append(GROUPS.get(g, g))
    found = {}
    p = os.path.join(AUDIT, "content_confirmed.tsv")
    if os.path.exists(p):
        with io.open(p, encoding=ENC, newline="") as f:
            for r in csv.DictReader(f, delimiter="\t"):
                found[r["stem"].lower()] = "%s: %s" % ("под сомнением" if r["kind"] == "doubt" else "подмена",
                                                       r["note"])
    cards = []
    for k in sorted(origs, key=lambda s: origs[s].lower()):
        stem = os.path.splitext(origs[k])[0]
        t = text.get(k, {})
        arts = [{"title": clean(a.get("title", {}).get("ru") or a.get("title", {}).get("en-US") or a.get("id", "")),
                 "text": clean(a.get("text", {}).get("ru") or a.get("text", {}).get("en-US", "")),
                 "en": clean(a.get("text", {}).get("en-US", "")), "section": a.get("section", "")}
                for a in t.get("articles", [])]
        arts += [{"title": "слайд " + s.get("caption_key", ""),
                  "text": clean(s.get("text", {}).get("ru") or s.get("text", {}).get("en-US", "")),
                  "en": clean(s.get("text", {}).get("en-US", "")), "section": "cutscene"}
                 for s in t.get("slides", [])]
        spec, why = None, ""
        if k in plan and k in caps:
            spec = pb.spec_for("hd", plan[k], caps[k])
        else:
            # без описания модели spec_for не собрать: заготовка - общие слова серии hd, что нарисовано - дописать
            spec = {"prompt": pb.PHOTO + pb.STRICT, "neg": pb.NEG_PHOTO + pb.NEG_STRICT, "strength": 0.85}
            why = ("в плане перерисовки, но нет описания картинки" if k in plan else
                   "не в плане перерисовки (серия hd считала её оружием, предметом или трофеем)") + \
                  " - ниже заготовка без описания: допишите, что на картинке и кто на ней"
        c = check.get(k, {})
        cards.append({"stem": stem, "key": k, "hd": k in hd, "h18": k in h18,
                      "articles": arts, "caption": caps.get(k, {}).get("en", ""),
                      "prompt": spec["prompt"] if spec else "", "neg": spec["neg"] if spec else "",
                      "strength": spec["strength"] if spec else None, "why": why,
                      "groups": groups.get(k, []), "found": found.get(k, ""),
                      "flags": [STRONG_RU[f] for f in c.get("verdict", {}).get("strong", [])],
                      "diff": (c.get("cmp") or [{}])[0].get("diff", "")})
    return cards, origs, hd, h18


def round_cards(cards, folder):
    """Режим круга перекрафта: только картинки из edits.json, с тем, что и с чего просили у модели."""
    d = load_json(os.path.join(folder, "edits.json"), {"edits": []})
    want = {e["stem"].lower(): e for e in d["edits"]}
    base = {"hd": "правка поверх нашей HD", "h18": "правка поверх 18+", "orig": "заново из оригинала"}
    out = []
    for c in cards:
        e = want.get(c["key"])
        if e:
            core = e.get("core", "").replace("{YOUNG}", d.get("YOUNG", ""))
            out.append(dict(c, base=e["base"], base_ru=base.get(e["base"], e["base"]), slot=e.get("slot", "normal"),
                            vnote=e.get("note", ""), core=core))
    return out


def candidates(folder, stem):
    """Готовые кандидаты круга: <имя>__<вариант>__<метка>.png (pedia_ab.py)."""
    pre = stem.lower() + "__"
    return [{"var": n.split("__")[1], "file": n} for n in sorted(os.listdir(folder))
            if n.lower().startswith(pre) and n.lower().endswith(".png") and n.count("__") == 2]


def read_picks(folder):
    out = {}
    p = os.path.join(folder, "picks.tsv")
    if os.path.exists(p):
        with io.open(p, encoding=ENC, newline="") as f:
            for r in csv.DictReader(f, delimiter="\t"):
                out[r["stem"].lower()] = r
    return out


def append_pick(folder, row):
    p = os.path.join(folder, "picks.tsv")
    new = not os.path.exists(p)
    with LOCK, io.open(p, "a", encoding=ENC, newline="") as f:
        w = csv.DictWriter(f, PICK_COLS, delimiter="\t", lineterminator="\n")
        if new:
            w.writeheader()
        w.writerow({k: row.get(k, "").replace("\t", " ").replace("\r", "").replace("\n", "\\n") for k in PICK_COLS})


def orig_png(path):
    """Оригинал как его рисует движок: индекс 0 прозрачен, даже без tRNS (R-043)."""
    im = Image.open(path)
    if im.mode == "P":
        a = im.convert("RGBA")
        a.putalpha(im.point([0] + [255] * 255, "L"))
        im = a
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store" if ctype.startswith("application") else "max-age=60")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        parts = [unquote(p) for p in u.path.strip("/").split("/")]
        if u.path in ("/", "/index.html"):
            with io.open(PAGE, encoding="utf-8") as f:
                return self.send(200, f.read(), "text/html; charset=utf-8")
        if u.path == "/api/cards":
            notes = read_notes()
            rd = S["round"]
            picks = read_picks(rd) if rd else {}
            out = []
            for c in S["cards"]:
                n = notes.get(c["key"], {})
                c = dict(c, status=n.get("status", ""), note=n.get("note", "").replace("\\n", "\n"),
                         my_prompt=n.get("prompt", "").replace("\\n", "\n"), when=n.get("when", ""))
                if rd:
                    p = picks.get(c["key"], {})
                    c.update(cands=candidates(rd, c["stem"]), pick=p.get("pick", ""),
                             pick_note=p.get("note", "").replace("\\n", "\n"), pick_when=p.get("when", ""))
                out.append(c)
            return self.send(200, json.dumps({"round": os.path.basename(rd) if rd else "", "cards": out},
                                             ensure_ascii=False))
        if len(parts) == 3 and parts[0] == "img":
            kind, k = parts[1], parts[2].lower()
            try:
                if kind == "cand" and S["round"] and parts[2] in os.listdir(S["round"]) and k.endswith(".png"):
                    with open(os.path.join(S["round"], parts[2]), "rb") as f:
                        return self.send(200, f.read(), "image/png")
                if kind == "orig" and k in S["origs"]:
                    return self.send(200, orig_png(os.path.join(ORIG, S["origs"][k])), "image/png")
                for name, folder in (("hd", HD), ("h18", H18)):
                    if kind == name and k in S[name]:
                        with open(os.path.join(folder, S[name][k]), "rb") as f:
                            return self.send(200, f.read(), "image/png")
            except OSError:
                pass
        self.send(404, '{"error":"нет"}')

    def do_POST(self):
        path = urlparse(self.path).path
        if path not in ("/api/note", "/api/pick") or (path == "/api/pick" and not S["round"]):
            return self.send(404, '{"error":"нет"}')
        n = int(self.headers.get("Content-Length") or 0)
        d = json.loads(self.rfile.read(min(n, 1 << 20)).decode("utf-8"))
        k = str(d.get("stem", "")).lower()
        if k not in S["origs"]:
            return self.send(400, '{"error":"нет такой картинки"}')
        when = time.strftime("%Y-%m-%d %H:%M:%S")
        stem = os.path.splitext(S["origs"][k])[0]
        if path == "/api/pick":
            pick = str(d.get("pick", ""))
            files = {c["var"]: c["file"] for c in candidates(S["round"], stem)}
            if pick not in files and pick not in ("again", "keep", ""):
                return self.send(400, '{"error":"нет такого кандидата"}')
            append_pick(S["round"], {"stem": stem, "pick": pick, "file": files.get(pick, ""),
                                     "note": str(d.get("note", "")), "when": when})
        else:
            append_note({"stem": stem, "status": str(d.get("status", "")), "note": str(d.get("note", "")),
                         "prompt": str(d.get("prompt", "")), "when": when})
        self.send(200, json.dumps({"ok": True, "when": when}))


S = {}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8783)
    ap.add_argument("--round", default="", help="круг перекрафта в art\\pedia_regen (recraft_v1): выбор кандидатов")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")      # консоль cp1252 без PYTHONIOENCODING
    os.chdir(ROOT)
    S["cards"], S["origs"], S["hd"], S["h18"] = build()
    S["round"] = os.path.join(pb.ROOT, a.round) if a.round else ""
    if S["round"]:
        S["cards"] = round_cards(S["cards"], S["round"])
        print("круг %s: картинок %d, выбор - %s" % (a.round, len(S["cards"]), os.path.join(S["round"], "picks.tsv")))
    print("карточек %d, с HD %d, с 18+ %d, с промптом %d; заметки - %s" % (
        len(S["cards"]), sum(c["hd"] for c in S["cards"]), sum(c["h18"] for c in S["cards"]),
        sum(1 for c in S["cards"] if c["prompt"]), NOTES), flush=True)
    print("http://localhost:%d" % a.port, flush=True)
    ThreadingHTTPServer(("127.0.0.1", a.port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
