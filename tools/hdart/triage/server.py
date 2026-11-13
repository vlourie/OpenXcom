# -*- coding: utf-8 -*-
"""Ручная проверка: оригинал | генерация 1 (прежний пак) | генерация 2 (LoRA).

Локальная страница на http://127.0.0.1:8765. На каждый кадр три картинки и три блока текста:
что это по данным игры (MCD и рулсеты), как кадр видит модель со зрением (caption.py) и
промпт, который пойдёт на генерацию, - его можно править. Отметка: брак, лучше 1, лучше 2.

Всё сохраняется сразу, на каждое нажатие: art/_review/triage/decisions.json (для сервера) и
decisions.tsv (для сборки пака и датасета). Закрыть окно можно в любой момент.

    python tools/hdart/triage/server.py            # потом открыть http://127.0.0.1:8765
    python tools/hdart/triage/server.py --port 8800
"""
import argparse
import csv
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

ENC = "utf-8-sig"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join("art", "_review", "triage")
VERDICTS = {"bad": "брак", "g1": "лучше 1", "g2": "лучше 2"}
# класс от модели со зрением, который уточняет «object» из MCD
OBJECT_CLASSES = {"furniture", "machine", "container", "statue", "plant", "rock", "debris",
                  "vehicle part", "light", "roof"}

LOCK = threading.Lock()
STATE = {"items": [], "by_id": {}, "caps": {}, "caps_mtime": 0, "dec": {}}


def load_json(p, default):
    if not os.path.exists(p):
        return default
    with open(p, encoding=ENC) as f:
        return json.load(f)


def save_json(p, data):
    tmp = p + ".tmp"
    with open(tmp, "w", encoding=ENC) as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def captions(out):
    p = os.path.join(out, "captions.json")
    try:
        m = os.path.getmtime(p)
    except OSError:
        return STATE["caps"]
    if m != STATE["caps_mtime"]:
        try:
            STATE["caps"] = load_json(p, {})
            STATE["caps_mtime"] = m
        except (ValueError, OSError):
            pass                                        # caption.py как раз пишет - возьмём в следующий раз
    return STATE["caps"]


def default_prompt(it, cap):
    """Промпт по данным игры плюс то, что увидела модель. Класс клетки берём из MCD: он знает,
    где стена, где сплошной блок и где дверь, а модель по картинке 32x40 это путает. Уточнение
    от модели идёт только для «object» (статуя, мебель, машина...)."""
    cls = it["cls"]
    if cap and cls == "object" and cap.get("class") in OBJECT_CLASSES:
        cls = cap["class"]
    cls = cls.replace(" tile", "").replace(" segment", "")        # «tile» добавляем сами
    parts = ["oxcehd, X-COM isometric %s tile" % cls]
    if cap:
        if cap.get("material"):
            parts.append(cap["material"])
        en = cap.get("en", "")
        for w in ("isometric ", "pixel art ", "pixel "):              # это уже сказано в начале
            en = en.replace(w, "").replace(w.capitalize(), "")
        if en.strip():
            parts.append(en.strip())
    elif it.get("hint"):
        parts.append(it["hint"])
    return ", ".join(p.strip() for p in parts if p.strip())


def write_tsv(out):
    rows = []
    for it in STATE["items"]:
        d = STATE["dec"].get(it["id"])
        if not d:
            continue
        rows.append([it["set"] + ".PCK", it["frame"], d.get("verdict", ""),
                     VERDICTS.get(d.get("verdict", ""), ""), int(bool(d.get("edited"))),
                     d.get("prompt", ""), it["cls"], d.get("t", "")])
    tmp = os.path.join(out, "decisions.tsv.tmp")
    with open(tmp, "w", encoding=ENC, newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["набор", "кадр", "отметка", "по-русски", "промпт_правлен", "промпт", "класс", "время"])
        w.writerows(rows)
    os.replace(tmp, os.path.join(out, "decisions.tsv"))


class H(BaseHTTPRequestHandler):
    out = OUT

    def log_message(self, fmt, *args):                  # тихо: страница дёргает сервер часто
        pass

    def send(self, code, body, ctype):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store" if ctype.startswith("application/json") else "max-age=3600")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = unquote(urlparse(self.path).path)
        if path in ("/", "/index.html"):
            with open(os.path.join(HERE, "index.html"), encoding="utf-8") as f:
                return self.send(200, f.read(), "text/html; charset=utf-8")
        if path == "/api/items":
            caps = captions(self.out)
            res = []
            for it in STATE["items"]:
                cap = caps.get(it["id"])
                res.append({k: it[k] for k in ("id", "set", "frame", "kind", "cls", "facts_ru",
                                               "prompt_used", "g1", "g2")}
                           | {"cap": cap, "prompt_default": default_prompt(it, cap),
                              "dec": STATE["dec"].get(it["id"])})
            return self.send(200, json.dumps({"items": res, "captions": len(caps)}, ensure_ascii=False),
                             "application/json; charset=utf-8")
        if path.startswith("/img/"):
            try:
                _, _, which, name = path.split("/", 3)
                it = STATE["by_id"][name[:-4]]
            except (ValueError, KeyError):
                return self.send(404, "нет такого кадра", "text/plain; charset=utf-8")
            p = {"o": os.path.join(self.out, "orig", it["id"] + ".png"),
                 "1": it["img1"], "2": it["img2"]}.get(which)
            if not p or not os.path.exists(p):
                return self.send(404, "нет файла", "text/plain; charset=utf-8")
            with open(p, "rb") as f:
                return self.send(200, f.read(), "image/png")
        return self.send(404, "нет", "text/plain; charset=utf-8")

    def do_POST(self):
        if urlparse(self.path).path != "/api/mark":
            return self.send(404, "нет", "text/plain; charset=utf-8")
        try:
            n = int(self.headers.get("Content-Length", "0"))
            d = json.loads(self.rfile.read(n).decode("utf-8"))
            iid = d["id"]
            it = STATE["by_id"][iid]
        except (ValueError, KeyError):
            return self.send(400, json.dumps({"error": "плохой запрос"}), "application/json")
        verdict = d.get("verdict", "")
        if verdict and verdict not in VERDICTS:
            return self.send(400, json.dumps({"error": "нет такой отметки"}), "application/json")
        with LOCK:
            cur = dict(STATE["dec"].get(iid) or {})
            if "verdict" in d:
                cur["verdict"] = verdict
            if "prompt" in d:
                cap = captions(self.out).get(iid)
                cur["prompt"] = d["prompt"]
                cur["edited"] = d["prompt"].strip() != default_prompt(it, cap).strip()
            if "prompt" not in cur:                     # в TSV промпт есть всегда, даже непровленный
                cur["prompt"] = default_prompt(it, captions(self.out).get(iid))
                cur["edited"] = False
            cur["t"] = time.strftime("%Y-%m-%d %H:%M:%S")
            if not cur.get("verdict") and not cur.get("edited"):
                STATE["dec"].pop(iid, None)
            else:
                STATE["dec"][iid] = cur
            save_json(os.path.join(self.out, "decisions.json"), STATE["dec"])
            write_tsv(self.out)
        return self.send(200, json.dumps({"ok": True, "dec": STATE["dec"].get(iid)}, ensure_ascii=False),
                         "application/json; charset=utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args()
    H.out = a.out
    STATE["items"] = load_json(os.path.join(a.out, "items.json"), {"items": []})["items"]
    STATE["by_id"] = {it["id"]: it for it in STATE["items"]}
    STATE["dec"] = load_json(os.path.join(a.out, "decisions.json"), {})
    print("кадров %d, отмечено %d. Открыть: http://127.0.0.1:%d" % (
        len(STATE["items"]), len(STATE["dec"]), a.port), flush=True)
    ThreadingHTTPServer(("127.0.0.1", a.port), H).serve_forever()


if __name__ == "__main__":
    main()
