#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""pedia_content.py - что поменялось по СОДЕРЖАНИЮ между оригиналом педии и HD, которую показывает игра.

Зачем (Vitali 28.10): в перегенерации бывают подмены - женщина стала мужчиной, у фигуры другое оружие,
дорисован человек или предмет, сменился вид существа или фон. Контур и цвет этого не ловят.

Как: модель Ollama (та же, что для captions.json) описывает КАЖДУЮ картинку отдельным запросом - оригинал
и HD из установки (`Пиратки\...\mods\hd\hd\UI`): люди, женщины, мужчины, существа, что в руках, предметы,
фон. Потом третий запрос, только текст, сравнивает два описания и ставит флаги. Обе картинки в одном
запросе не годятся: проба 28.10 - модель описывает оригинал и копирует то же описание во вторую сторону,
подмены пола и вида не видит ни одной. Уверенности модели не верим (R-143): с --votes 2 описание HD
спрашивается второй раз при другой температуре, флаг держится, только если его дали оба сравнения.

Пишет и копит art\pedia_regen\content_check.json {stem: {...}}; описание оригинала берётся из записи,
пока md5 оригинала тот же, HD - пока тот же md5 HD. Уступает карту по флагу очереди (код 75) и продолжает.
Только через очередь:
    py -3.13 tools\gpuq.py add --name pedia_content --prio 9 --preemptible -- py -3.13 tools\hdart\pedia_content.py
Проба на списке:  ... pedia_content.py --only Devil_2,MiG --votes 2
Сводка без карты: py -3.13 tools\hdart\pedia_content.py --stats [--only ...]
"""
import argparse
import base64
import hashlib
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

GAME = os.path.join("Пиратки", "Dioxine_XPiratez", "user", "mods")
ORIG = os.path.join(GAME, "Piratez", "Resources", "Pedia")
HD = os.path.join(GAME, "hd", "hd", "UI")
# оригинал описывается по ESRGAN (как captions.json): по пиксельным 320x200 модель путает вид и пол (проба 28.10:
# синие пришельцы H_006 и кошки Pumas на оригинале стали «людьми»)
ESRGAN = os.path.join(GAME, "hd", "hd", "UI_esrgan")
STRONG = ["gender_changed", "person_added", "person_removed", "species_changed", "held_changed", "background_changed"]
OUT = os.path.join(pb.ROOT, "content_check.json")

FLAGS = ["gender_changed", "person_added", "person_removed", "species_changed", "held_changed",
         "object_added", "object_removed", "background_changed"]

DESCRIBE = """Describe this picture precisely. Look at EVERY figure, including small ones in the background.
Answer strictly as JSON:
{"people": number of human or humanoid figures,
 "figures": for each figure from left to right: sex (woman / man / unclear), species and skin colour if not an ordinary human (e.g. "red-skinned horned demon", "grey alien", "orc with green skin"), and what it holds in its hands, e.g. "1: woman, human, pistol in right hand; 2: man, green-skinned orc, nothing",
 "creatures": animals, monsters and robots that are not counted as figures, short English list, empty string if none,
 "objects": the main objects and vehicles, short English list,
 "background": the background in a few English words (plain colour, studio, city, forest, sky, interior...),
 "scene": one English sentence on what the picture shows}"""

COMPARE = """Two independent observers described two pictures. Picture A is the ORIGINAL drawing from a video game
encyclopedia, picture B is a remake that must show the same content. The observers word things differently, and
may miscount small background figures by one or name the same object with another word - that is NOT a difference.
Drawing style, realism, lighting and detail are expected to change - also NOT a difference.
Report only clear changes of CONTENT.

A: {a}
B: {b}

Answer strictly as JSON:
{{"gender_changed": true if a main figure is a woman in A and a man in B or the reverse,
 "person_added": true if B has a clearly visible extra person, "person_removed": true if a person of A is missing in B,
 "species_changed": true if a figure or creature became another species (e.g. demon or alien became an ordinary human, dinosaur became a deer),
 "held_changed": true if a figure holds a different weapon or object, or lost or gained one,
 "object_added": true if B has a notable new object, "object_removed": true if a notable object of A is missing in B,
 "background_changed": true if the background is a different place or type (e.g. plain backdrop became a city or forest, day sky became night),
 "diff": "the biggest content difference in a few English words, empty string if none"}}"""


def b64(path):
    from PIL import Image
    im = Image.open(path)
    if im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info):
        im = im.convert("RGBA")
        bg = Image.new("RGBA", im.size, (0, 0, 0, 255))
        im = Image.alpha_composite(bg, im)
    im = im.convert("RGB")
    s = 896.0 / max(im.size)
    im = im.resize((max(28, int(im.width * s)), max(28, int(im.height * s))), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()


def md5(path):
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def num(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def generate(prompt, temp, images=None, predict=500):
    body = {"model": pb.MODEL, "stream": False, "think": False, "format": "json",
            # num_ctx обязателен (R-064)
            "options": {"temperature": temp, "num_predict": predict, "num_ctx": 4096}, "prompt": prompt}
    if images:
        body["images"] = images
    req = urllib.request.Request(pb.HOST + "/api/generate", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        return json.loads(json.loads(r.read().decode())["response"])


def describe(path, temp):
    d = generate(DESCRIBE, temp, [b64(path)])
    out = {"people": num(d.get("people"))}
    for k in ("figures", "creatures", "objects", "background", "scene"):
        v = d.get(k, "")
        out[k] = "; ".join(map(str, v)) if isinstance(v, list) else str(v).strip()
    return out


def compare(a, b):
    d = generate(COMPARE.format(a=json.dumps(a, ensure_ascii=False), b=json.dumps(b, ensure_ascii=False)),
                 0.1, predict=300)
    t = lambda v: v is True or str(v).strip().lower() == "true"       # noqa: E731
    r = {k: t(d.get(k)) for k in FLAGS}
    r["diff"] = str(d.get("diff", "")).strip()
    return r


def verdict(cmps):
    """Флаг держится, если его дали все сравнения (R-143: одно «да» модели - не доказательство)."""
    v = {k: all(c[k] for c in cmps) for k in FLAGS}
    v["agree"] = all(all(c[k] == cmps[0][k] for k in FLAGS) for c in cmps)
    v["flags"] = [k for k in FLAGS if v[k]]
    v["strong"] = [k for k in STRONG if v[k]]      # object_added/removed - шум описаний, только подсказка
    return v


def pictures():
    hd = {os.path.splitext(n)[0].lower(): n for n in os.listdir(HD) if n.lower().endswith(".png")}
    esr = {os.path.splitext(n)[0].lower(): n for n in os.listdir(ESRGAN) if n.lower().endswith(".png")}
    out = []
    for n in sorted(os.listdir(ORIG)):
        stem, ext = os.path.splitext(n)
        if ext.lower() in (".png", ".gif", ".bmp") and stem.lower() in hd:
            o = os.path.join(ESRGAN, esr[stem.lower()]) if stem.lower() in esr else os.path.join(ORIG, n)
            out.append((stem, o, os.path.join(HD, hd[stem.lower()])))
    return out


def stats(done, keys):
    rows = [done[k] for k in keys if k in done]
    print("спрошено %d" % len(rows))
    for k in FLAGS:
        print("  %-18s %d" % (k, sum(1 for r in rows if r["verdict"].get(k))))
    print("  сравнения разошлись %d" % sum(1 for r in rows if not r["verdict"].get("agree", True)))
    print("  хоть один флаг      %d" % sum(1 for r in rows if r["verdict"]["flags"]))
    print("  сильный флаг        %d" % sum(1 for r in rows if r["verdict"].get("strong")))
    for k in keys:
        r = done.get(k)
        if r:
            print("%-28s %-40s %s" % (k, ",".join(r["verdict"].get("strong", [])) or "-", r["cmp"][0]["diff"][:90]))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", default="", help="имена через запятую или @файл со списком")
    ap.add_argument("--votes", type=int, default=1, help="сколько описаний HD (2 - второе при 0.7)")
    ap.add_argument("--force", action="store_true", help="спросить заново и уже спрошенное")
    ap.add_argument("--stats", action="store_true", help="только сводка по уже спрошенному, без карты")
    a = ap.parse_args()

    os.chdir(os.path.dirname(os.path.dirname(HERE)))
    only = a.only
    if only.startswith("@"):
        with io.open(only[1:], encoding=pb.ENC) as f:
            only = ",".join(l.strip() for l in f if l.strip())
    want = {s.strip().lower() for s in only.split(",") if s.strip()}
    pics = [p for p in pictures() if not want or p[0].lower() in want]
    done = pb.load(OUT, {})
    if a.stats:
        stats(done, [p[0] for p in pics])
        return 0

    temps = [0.1, 0.7, 0.4][:max(1, a.votes)]
    todo = []
    for stem, o, h in pics:
        r = done.get(stem)
        if a.force or not r or r.get("hd_md5") != md5(h) or r.get("orig_md5") != md5(o) \
                or len(r.get("hd_desc", [])) < len(temps):
            todo.append((stem, o, h))
    print("картинок с HD %d, к проверке %d, описаний HD на картинку %d" % (len(pics), len(todo), len(temps)),
          flush=True)

    t0 = time.time()
    rc = 0
    for i, (stem, o, h) in enumerate(todo, 1):
        if pb.must_yield():
            print("уступаю карту, сделано %d из %d" % (i - 1, len(todo)), flush=True)
            rc = pb.YIELD_CODE
            break
        prev = {} if a.force else done.get(stem, {})
        om, hm = md5(o), md5(h)
        try:
            od = prev["orig_desc"] if prev.get("orig_md5") == om else describe(o, 0.1)
            hds = prev.get("hd_desc", []) if prev.get("hd_md5") == hm else []
            hds = hds + [describe(h, t) for t in temps[len(hds):]]
            cmps = [compare(od, hd) for hd in hds]
        except Exception as e:                                         # noqa: BLE001
            print("  %s: %s" % (stem, e), flush=True)
            continue
        done[stem] = {"orig": o, "hd": h, "orig_md5": om, "hd_md5": hm, "orig_desc": od, "hd_desc": hds,
                      "cmp": cmps, "verdict": verdict(cmps)}
        pb.save(OUT, done)
        el = time.time() - t0
        v = done[stem]["verdict"]
        print("  %d/%d %s: %s%s | %s; %.1f с/шт, осталось ~%.0f мин" % (
            i, len(todo), stem, ",".join(v["flags"]) or "-", "" if v["agree"] else " (разошлись)",
            cmps[0]["diff"][:80], el / i, (len(todo) - i) * el / i / 60), flush=True)
    if todo:
        pb.unload_ollama()
    if rc == 0 and want:
        stats(done, [p[0] for p in pics])
    return rc


if __name__ == "__main__":
    sys.exit(main())
