#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Карточки ассетов: опознание и состав семейства одной страницей (Pipeline v2, P1-A, раздел 23).

Человек не правит TSV и не листает 2141 пару. На карточке один ассет - канонический кадр крупно, где он
стоит на карте, что стоит в игре сейчас, члены семейства и кандидаты, и предложенное описание:
  Верно (CONFIRM) / свой текст (EDIT) / Не знаю (UNKNOWN) / Не рисовать (SKIP) / Не предмет (NOT_OBJECT);
  член AUTO - «не то» (HUMAN_REJECTED); кандидат - перекраска / зеркало / другой бок / нет.
Опознание пишется в art/objects/discovery/identity_decisions.tsv, состав - в
art/objects/families/decisions.tsv; оба журнала только дописываются, последняя запись главная.
Кнопка «Пересобрать» - obj_families + obj_generation: решения входят в семейства и очередь.

    py -3.13 tools/hdart/review_server.py            (http://localhost:8774)
    .claude/launch.json: asset-review
"""
import argparse
import csv
import io
import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for _p in (HERE, os.path.dirname(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from PIL import Image                               # noqa: E402

import map_mockup as mm                             # noqa: E402
import obj_review as orv                            # noqa: E402

ENC = "utf-8-sig"
DISC = os.path.join("art", "objects", "discovery")
ITEMS = os.path.join(DISC, "items.json")
IDENTITY = os.path.join(DISC, "asset_identity.tsv")
ID_LOG = os.path.join(DISC, "identity_decisions.tsv")
ID_LOG_COLS = ("asset_id", "decision", "identity", "who", "when", "note")
FAMS = os.path.join("art", "objects", "families", "families.json")
FAM_LOG = os.path.join("art", "objects", "families", "decisions.tsv")
FAM_LOG_COLS = ("canonical", "member", "decision", "relation", "кто", "когда", "заметка")
GEN = os.path.join("art", "objects", "generation", "generation.json")
ACCEPT = os.path.join("art", "objects", "generation", "acceptance.json")   # acceptance_batch.py
CACHE = os.path.join("art", "objects", "review_cache")
DONE = ("HUMAN_CONFIRMED", "HUMAN_EDITED", "SKIP", "NOT_OBJECT", "UNKNOWN")
IDENT_DECISIONS = ("CONFIRM", "EDIT", "UNKNOWN", "SKIP", "NOT_OBJECT")
MEMBER_DECISIONS = ("HUMAN_APPROVED", "HUMAN_REJECTED")
MODEL_COLS = ("proposed_name", "proposed_category", "proposed_material", "ambiguity", "evidence", "model_confidence",
              "model_status", "candidates", "review_level", "candidate_names")


def model_conf(row):
    try:
        return float(row.get("model_confidence") or -1)
    except ValueError:
        return -1.0
RELATIONS = ("recolor", "mirror", "alternate_view")


def read_tsv(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding=ENC, newline="") as f:
        return list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))


def append_tsv(path, cols, row):
    """Журнал только дописывается; файла нет - с заголовком (UTF-8 со спецификацией, R-001)."""
    new = not os.path.exists(path) or os.path.getsize(path) == 0
    clean = [str(row.get(c, "")).replace("\t", " ").replace("\r", " ").replace("\n", " ") for c in cols]
    with open(path, "a", encoding=ENC if new else "utf-8", newline="") as f:
        if new:
            f.write("\t".join(cols) + "\n")
        f.write("\t".join(clean) + "\n")


class Data:
    """Всё, что показывает страница; перечитывается после пересборки."""

    def __init__(self):
        self.lock = threading.Lock()
        self.load()

    def load(self):
        with open(ITEMS, encoding=ENC) as f:
            self.items = {it["rank"]: it for it in json.load(f)}
        self.rank_of = {it["keys"][0].upper(): r for r, it in self.items.items()}
        with open(FAMS, encoding=ENC) as f:
            self.fams = {fm["family_id"]: fm for fm in json.load(f)}
        self.ident = {r["asset_id"]: r for r in read_tsv(IDENTITY)}
        self.gen = {}
        if os.path.exists(GEN):
            with open(GEN, encoding=ENC) as f:
                self.gen = {r["key"]: r for r in json.load(f)}
        self.id_dec = {r["asset_id"]: r for r in read_tsv(ID_LOG)}
        self.fam_dec = {(r["canonical"].upper(), r["member"].upper()): r for r in read_tsv(FAM_LOG)}
        self.order = sorted(self.ident.values(), key=lambda r: int(r["rank"]))
        self.accept = {}
        if os.path.exists(ACCEPT):
            with open(ACCEPT, encoding=ENC) as f:
                self.accept = {a["asset_id"]: (i, a["category"]) for i, a in enumerate(json.load(f))}
        self.loaded = time.strftime("%H:%M:%S")

    def status(self, aid):
        d = self.id_dec.get(aid)
        return {"CONFIRM": "HUMAN_CONFIRMED", "EDIT": "HUMAN_EDITED",
                "REOPEN": "IDENTITY_REVIEW"}.get(d["decision"], d["decision"]) if d \
            else self.ident[aid]["status"]

    def card(self, row):
        aid = row["asset_id"]
        fm = self.fams.get(aid)
        it = self.items[int(row["rank"])]
        g = self.gen.get(aid, {})

        def mem(m, kind):
            k = m["keys"][0].upper()
            ev = m.get("evidence", {}) or {}
            hd = self.fam_dec.get((aid, k))
            return {"key": k, "rank": m["rank"], "relation": m.get("relation", ""), "decision": m.get("decision", ""),
                    "reason": m.get("reason", ""), "kind": kind, "human": hd["decision"] if hd else "",
                    "human_relation": hd["relation"] if hd else "",
                    "why": "; ".join(ev.get("why", [])[:3]) if isinstance(ev.get("why"), list) else "",
                    "score": ev.get("score", ev.get("corr", "")), "via": m.get("via", "")}
        members = [mem(m, "member") for m in (fm["members"][1:] if fm else [])]
        review = [mem(m, "review") for m in (fm["review"] if fm else [])]
        dec = self.id_dec.get(aid)
        return {"asset_id": aid, "rank": int(row["rank"]), "places": it.get("places", 0), "kind": it["kind"],
                "keys": it["keys"], "map": it.get("map", ""), "asset_class": row["asset_class"],
                "class_why": g.get("why", "") or (fm["members"][0].get("class_why", "") if fm else ""),
                "status": self.status(aid), "proposed": row["proposed"], "proposed_source": row["proposed_source"],
                "identity": (dec.get("identity") if dec and dec["decision"] == "EDIT" else row["identity"]) or "",
                "blockers": g.get("blockers", []), "members": members, "review": review,
                "hint": it.get("hint", ""), "acceptance": self.accept.get(aid, (0, ""))[1],
                "model": {k: row.get(k, "") for k in MODEL_COLS}}

    def cards(self, view, offset, limit):
        if view == "acceptance":            # приёмочная десятка: в своём порядке, отвеченные тоже
            sel = sorted((r for r in self.order if r["asset_id"] in self.accept),
                         key=lambda r: self.accept[r["asset_id"]][0])
            return len(sel), [self.card(r) for r in sel[offset:offset + limit]]

        def want(r):
            st = self.status(r["asset_id"])
            if view == "done":
                return st in DONE
            if st in DONE:
                return False
            if view == "class_check":
                return r["asset_class"] == "object_or_relief"
            if view == "proposed":
                return st == "AGENT_PROPOSED"
            if view == "none":
                return st == "NO_PROPOSAL"
            if view == "conflict":              # два ответа модели - разные предметы: решает человек с нуля
                return st == "REVIEW_REQUIRED"
            if view == "family":
                fm = self.fams.get(r["asset_id"])
                return bool(fm and (fm["review"] or len(fm["members"]) > 1))
            return True
        sel = [r for r in self.order if want(r)]
        if view in ("proposed", "none", "class_check"):     # P1-B: уверенность модели - только порядок показа
            sel.sort(key=lambda r: -model_conf(r))
        return len(sel), [self.card(r) for r in sel[offset:offset + limit]]

    def counts(self):
        c = {}
        for r in self.order:
            st = self.status(r["asset_id"])
            c[st] = c.get(st, 0) + 1
        return c


class Renders:
    """Картинки карточек: кадр ассета x4, кадр пака в игре, место на карте. На диск в review_cache."""

    def __init__(self, data):
        self.data = data
        self.lock = threading.Lock()
        self.world = None

    def w(self):
        if self.world is None:
            self.world = mm.World()
        return self.world

    def cached(self, name, make):
        p = os.path.join(CACHE, name)
        if os.path.exists(p):
            with open(p, "rb") as f:
                return f.read()
        with self.lock:
            im = make()
        if im is None:
            return None
        os.makedirs(os.path.dirname(p), exist_ok=True)
        buf = io.BytesIO()
        im.save(buf, "PNG")
        with open(p, "wb") as f:
            f.write(buf.getvalue())
        return buf.getvalue()

    def asset(self, rank):
        it = self.data.items[rank]

        def make():
            frames = [self.w().sprite(orv.key_of(k)[0].lower(), orv.key_of(k)[1], None) for k in it["src"]]
            at = it.get("at") or [[0, 0, 0]] * len(frames)
            return orv.compose(frames, at[:len(frames)] if len(at) >= len(frames) else [[0, 0, 0]] * len(frames))
        return self.cached("asset/%d.png" % rank, make)

    def pack(self, rank):
        it = self.data.items[rank]

        def make():
            frames = []
            for k in it["src"]:
                p = orv.frame_file(orv.GAME_HD, orv.key_of(k))
                frames.append(Image.open(p).convert("RGBA") if p else None)
            if not any(frames):
                return None
            at = it.get("at") or [[0, 0, 0]] * len(frames)
            return orv.compose(frames, at[:len(frames)])
        return self.cached("pack/%d.png" % rank, make)

    def context(self, rank):
        it = self.data.items[rank]

        def make():
            if not it.get("map") or "/" not in it["map"]:
                return None
            terrain, block = it["map"].split("/", 1)
            try:
                return mm.mockup(self.w(), orv.key_of(it["src"][0]), terrain, block, radius=3)
            except (SystemExit, Exception) as e:           # карта не читается - карточка без места
                print("контекст #%d %s: %s" % (rank, it["map"], e), flush=True)
                return None
        return self.cached("ctx/%d.png" % rank, make)


REBUILD = {"state": "idle", "log": "", "started": ""}


def rebuild(data):
    REBUILD.update(state="running", log="", started=time.strftime("%H:%M:%S"))
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    out = []
    for script in ("tools/hdart/obj_families.py", "tools/hdart/obj_generation.py"):
        p = subprocess.run([sys.executable, script], cwd=ROOT, env=env, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        out.append("$ %s\n%s%s" % (script, "\n".join(p.stdout.splitlines()[-8:]), p.stderr[-2000:]))
        if p.returncode:
            REBUILD.update(state="failed", log="\n".join(out))
            return
    with data.lock:
        data.load()
    REBUILD.update(state="done", log="\n".join(out))


def handler(data, renders, page):
    class H(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def send(self, code, body, ctype="application/json; charset=utf-8"):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store" if ctype.startswith("application/json") else "max-age=3600")
            self.end_headers()
            self.wfile.write(body)

        def js(self, obj, code=200):
            self.send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

        def do_GET(self):
            u = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            if u.path == "/":
                return self.send(200, page, "text/html; charset=utf-8")
            if u.path == "/api/cards":
                with data.lock:
                    total, cards = data.cards(q.get("view", "pending"), int(q.get("offset", 0)), int(q.get("limit", 30)))
                    return self.js({"total": total, "cards": cards, "counts": data.counts(), "loaded": data.loaded})
            if u.path == "/api/rebuild":
                return self.js(REBUILD)
            if u.path.startswith("/img/"):
                kind, name = u.path[5:].split("/", 1)
                rank = int(name.split(".")[0])
                if rank not in data.items or kind not in ("asset", "pack", "ctx"):
                    return self.send(404, b"")
                body = {"asset": renders.asset, "pack": renders.pack, "ctx": renders.context}[kind](rank)
                return self.send(200, body, "image/png") if body else self.send(404, b"")
            self.send(404, b"")

        def do_POST(self):
            u = urlparse(self.path)
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
            now = time.strftime("%Y-%m-%d %H:%M")
            if u.path == "/api/identity":
                if body.get("decision") not in IDENT_DECISIONS or body.get("asset_id") not in data.ident:
                    return self.js({"error": "bad decision"}, 400)
                if body["decision"] == "EDIT" and not body.get("identity", "").strip():
                    return self.js({"error": "EDIT без текста"}, 400)
                row = {"asset_id": body["asset_id"], "decision": body["decision"],
                       "identity": body.get("identity", "").strip() if body["decision"] == "EDIT" else "",
                       "who": "Vitali", "when": now, "note": body.get("note", "")}
                with data.lock:
                    append_tsv(ID_LOG, ID_LOG_COLS, row)
                    data.id_dec[row["asset_id"]] = row
                return self.js({"ok": True, "status": data.status(row["asset_id"])})
            if u.path == "/api/member":
                c, m = body.get("canonical", "").upper(), body.get("member", "").upper()
                if body.get("decision") not in MEMBER_DECISIONS or c not in data.rank_of or m not in data.rank_of:
                    return self.js({"error": "bad member decision"}, 400)
                rel = body.get("relation", "")
                if body["decision"] == "HUMAN_APPROVED" and rel not in RELATIONS:
                    return self.js({"error": "нужна связь"}, 400)
                row = {"canonical": c, "member": m, "decision": body["decision"], "relation": rel,
                       "кто": "Vitali", "когда": now, "заметка": body.get("note", "карточка ассета")}
                with data.lock:
                    append_tsv(FAM_LOG, FAM_LOG_COLS, row)
                    data.fam_dec[(c, m)] = row
                return self.js({"ok": True})
            if u.path == "/api/rebuild":
                if REBUILD["state"] == "running":
                    return self.js({"error": "уже идёт"}, 409)
                threading.Thread(target=rebuild, args=(data,), daemon=True).start()
                return self.js({"ok": True})
            self.send(404, b"")
    return H


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8774)
    ap.add_argument("--logs", default="", help="папка для журналов решений вместо настоящих (проверка страницы)")
    ap.add_argument("--accept", default="", help="список вида «десятка» вместо acceptance.json (photo_struct.py)")
    a = ap.parse_args()
    # запуск из launch.json - без PYTHONIOENCODING, stdout в cp1252 падает на кириллице (R-001)
    for s in (sys.stdout, sys.stderr):
        s.reconfigure(encoding="utf-8", errors="replace")
    os.chdir(ROOT)
    if a.logs:
        global ID_LOG, FAM_LOG
        os.makedirs(a.logs, exist_ok=True)
        ID_LOG, FAM_LOG = os.path.join(a.logs, "identity_decisions.tsv"), os.path.join(a.logs, "decisions.tsv")
        print("журналы решений - в %s (настоящие не трогаются)" % a.logs, flush=True)
    if a.accept:
        global ACCEPT
        ACCEPT = a.accept
        print("вид «десятка» - список %s" % a.accept, flush=True)
    data = Data()
    with open(os.path.join(HERE, "review_page.html"), encoding="utf-8") as f:
        page = f.read().encode("utf-8")
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), handler(data, Renders(data), page))
    print("карточки ассетов: http://localhost:%d  (ассетов %d, решений опознания %d, состава %d)"
          % (a.port, len(data.order), len(data.id_dec), len(data.fam_dec)), flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
