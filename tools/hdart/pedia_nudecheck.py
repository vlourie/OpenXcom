#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""pedia_nudecheck.py - где в ГОТОВОЙ картинке варианта осталась нагота.

Цель (Vitali 26.09): в обычном режиме минимум обнажёнки. Модель надевает трусы, а лиф часто нет:
грудь из рисунка при силе 0.85-0.92 держится. Проход спрашивает ту же модель Ollama, что делала
captions.json, но про готовый результат (самый свежий, как его берёт pedia_push.py), и пишет:
  art\pedia_regen\nudecheck_<вариант>.json  {ключ: {"topless", "bottomless", "file"}}, копится
  art\pedia_regen\redo_<вариант>_bra.tsv    имя <TAB> - <TAB> причина - для pedia_batch.py redo
Проверяются картинки, где раздет оригинал (captions.json) - остальные модель не раздевала.

Грузит модель на карту - только через очередь:
    py -3.13 tools\gpuq.py add --name pedia_nudecheck --pos 1 -- py -3.13 tools\hdart\pedia_nudecheck.py
"""
import argparse
import base64
import io
import json
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import pedia_batch as pb                                 # noqa: E402
from pedia_push import newest                            # noqa: E402

ASK = """This picture is meant to be safe for work: every woman in it must wear a top that covers her breasts and briefs.
Look at EVERY person, including small figures in the background. Answer strictly as JSON with keys:
"topless": true if any bare female breast or nipple is visible anywhere, even partly or through sheer cloth;
"bottomless": true if any bare genitals, bare groin or bare buttocks without briefs are visible;
"where": a few English words on who is still bare, empty string if nobody."""


def b64(path):
    from PIL import Image
    im = Image.open(path).convert("RGB")
    s = 1024.0 / max(im.size)
    im = im.resize((max(28, int(im.width * s)), max(28, int(im.height * s))), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()


def ask(path):
    body = {"model": pb.MODEL, "stream": False, "think": False, "format": "json",
            # num_ctx обязателен (R-064)
            "options": {"temperature": 0.1, "num_predict": 200, "num_ctx": 4096},
            "prompt": ASK, "images": [b64(path)]}
    req = urllib.request.Request(pb.HOST + "/api/generate", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        d = json.loads(json.loads(r.read().decode())["response"])
    t = lambda v: v is True or str(v).strip().lower() == "true"       # noqa: E731
    return {"topless": t(d.get("topless")), "bottomless": t(d.get("bottomless")),
            "where": str(d.get("where", "")).strip()}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--variant", default="hd")
    ap.add_argument("--all-women", action="store_true", help="проверять все картинки с женщинами, не только раздетые")
    ap.add_argument("--force", action="store_true", help="спросить заново и то, что уже спрошено по этому файлу")
    a = ap.parse_args()

    plan = pb.load(os.path.join(pb.ROOT, "plan.json"), {})
    caps = pb.load(os.path.join(pb.ROOT, "captions.json"), {})
    res = newest(a.variant)
    out_path = os.path.join(pb.ROOT, "nudecheck_%s.json" % a.variant)
    done = pb.load(out_path, {})

    keys = []
    for k in plan["order"]:
        c = caps.get(k, {})
        if not (c.get("topless") or c.get("bottomless") or (a.all_women and c.get("women"))):
            continue
        stem = os.path.splitext(plan["info"][k]["file"])[0]
        f = res.get(stem.lower())
        if f and (a.force or done.get(k, {}).get("file") != f):
            keys.append((k, stem, f))
    print("к проверке %d картинок" % len(keys), flush=True)

    t0 = time.time()
    for i, (k, stem, f) in enumerate(keys, 1):
        try:
            r = ask(f)
        except Exception as e:                                         # noqa: BLE001
            print("  %s: %s" % (stem, e), flush=True)
            continue
        r["file"], r["name"] = f, plan["info"][k]["file"]     # имя с расширением - так его ищет redo
        done[k] = r
        pb.save(out_path, done)
        el = time.time() - t0
        print("  %d/%d %s: %s%s %s; %.1f с/шт, осталось ~%.0f мин" % (
            i, len(keys), stem, "ГРУДЬ " if r["topless"] else "", "НИЗ " if r["bottomless"] else "",
            r["where"], el / i, (len(keys) - i) * el / i / 60), flush=True)
    if keys:
        pb.unload_ollama()

    bad = [(v["name"], v) for v in done.values() if v.get("topless") or v.get("bottomless")]
    tsv = os.path.join(pb.ROOT, "redo_%s_bra.tsv" % a.variant)
    with io.open(tsv, "w", encoding=pb.ENC) as fo:
        for name, v in sorted(bad):
            why = ("голая грудь" if v["topless"] else "") + (" голый пах" if v["bottomless"] else "")
            fo.write("%s\t-\t%s: %s\n" % (name, why.strip(), v["where"]))
    print("проверено всего %d, голых осталось %d -> %s" % (len(done), len(bad), tsv), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
