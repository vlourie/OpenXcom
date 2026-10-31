# -*- coding: utf-8 -*-
"""Блок 2 проверки: «как модель видит» - описание оригинала локальной моделью со зрением.

Ollama (qwen3.8 27B, vision) получает оригинал 32x40, увеличенный x8 на тёмном полу боя,
и отвечает JSON: что на картинке по-русски, коротко по-английски для промпта, класс клетки
и материал. Ответы копятся в art/_review/triage/captions.json по одному, поэтому прогон
можно прервать и продолжить: готовые не спрашиваются заново. Сервер проверки перечитывает
файл сам.

    python tools/hdart/triage/caption.py            # все из items.json
    python tools/hdart/triage/caption.py --limit 5  # проба
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
sys.path.insert(0, os.path.dirname(HERE))
from PIL import Image                                                  # noqa: E402

import tile_forge as tf                                                # noqa: E402

ENC = "utf-8-sig"
OUT = os.path.join("art", "_review", "triage")
MODEL = "orcarouter/Qwen3.8-27B-Uncensored:q5_K_M"
CLASSES = ["floor", "west wall", "north wall", "solid block", "diagonal wall", "door",
           "sliding door", "roof", "furniture", "machine", "container", "statue", "plant",
           "rock", "debris", "vehicle part", "light", "other object"]

ASK = """This is one tile from the 1994 isometric game X-COM (a mod called X-Piratez),
enlarged 8x with nearest neighbour; the dark grey around it is empty background, not part of the tile.
Game data says: {facts}.
Describe ONLY what is drawn. Answer strictly as JSON with keys:
"ru": 1-2 sentences in Russian: what the object is, its shape, materials and colours;
"en": a short English noun phrase for an image prompt, max 14 words, materials and colours, no style words;
"class": one of {classes};
"material": main material in 1-3 English words (e.g. "grey steel", "red brick", "snow", "sand", "wood planks")."""


def pic(sheets, name, i):
    sh = tf.Sheet(sheets, name)
    fr = sh.frame(i).convert("RGBA")
    fr = fr.resize((fr.width * 8, fr.height * 8), Image.NEAREST)
    bg = Image.new("RGBA", fr.size, (38, 38, 42, 255))
    b = io.BytesIO()
    Image.alpha_composite(bg, fr).convert("RGB").save(b, "PNG")
    return base64.b64encode(b.getvalue()).decode()


def ask(img, facts, host):
    body = {"model": MODEL, "stream": False, "think": False, "format": "json",
            # num_ctx обязателен: без него Ollama грузит модель с родным контекстом 262144,
            # кэш ключей раздувается до 16 ГБ, и 14 из 66 слоёв уезжают считаться на процессор.
            # Запрос с картинкой - 300-1100 токенов, 4096 хватает с запасом
            "options": {"temperature": 0.2, "num_predict": 300, "num_ctx": 4096},
            "prompt": ASK.format(facts=facts, classes=", ".join(CLASSES)), "images": [img]}
    req = urllib.request.Request(host + "/api/generate", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        txt = json.loads(r.read().decode())["response"]
    d = json.loads(txt)
    if d.get("class") not in CLASSES:
        d["class"] = "other object"
    return {k: str(d.get(k, "")).strip() for k in ("ru", "en", "class", "material")}


def save(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding=ENC) as f:
        json.dump(data, f, ensure_ascii=False, indent=0)
    os.replace(tmp, path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheets", default=os.path.join("art", "TERRAIN"))
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--host", default="http://127.0.0.1:11434")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    with open(os.path.join(a.out, "items.json"), encoding=ENC) as f:
        items = json.load(f)["items"]
    cpath = os.path.join(a.out, "captions.json")
    caps = {}
    if os.path.exists(cpath):
        with open(cpath, encoding=ENC) as f:
            caps = json.load(f)
    todo = [it for it in items if it["id"] not in caps]
    if a.limit:
        todo = todo[:a.limit]
    t0 = time.time()
    for n, it in enumerate(todo, 1):
        try:
            caps[it["id"]] = ask(pic(a.sheets, it["set"] + ".PCK", it["frame"]), it["facts_en"], a.host)
        except Exception as e:                                           # noqa: BLE001
            print("  %s: %s" % (it["id"], e), flush=True)
            continue
        if n % 5 == 0 or n == len(todo):
            save(cpath, caps)
        el = time.time() - t0
        print("  %d/%d %s  %.1f с/кадр, осталось ~%d мин" % (
            n, len(todo), it["id"], el / n, (len(todo) - n) * el / n / 60), flush=True)
    save(cpath, caps)
    print("готово: описаний %d" % len(caps))


if __name__ == "__main__":
    main()
