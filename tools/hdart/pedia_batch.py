#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""pedia_batch.py - перерисовка картинок педии X-Piratez сериями по 100 (Vitali 2026-09-25).

Что рисуем: всё из Resources\Pedia, кроме оружия и предметов (оружие кораблей type_id 2,
STR_WEAPONS_AND_EQUIPMENT, трофеи, снаряжение кораблей) и кроме того, что модель со зрением
назвала «один предмет на пустом фоне». Корабли (type_id 1, STR_UFOS) - свободно, силой 1.0;
остальное - близко к оригиналу, img2img силой 0.85 (выбрано Vitali по листу 2026-09-25).

Три серии, по порядку: hd (обычная: раздетую одеть в бельё), style (в манере художника),
18 (одетую не раздевать, а подчеркнуть; раздетую оставить). Правила - память pedia-regen-rules.

    py -3 tools\hdart\pedia_batch.py plan                       # план и число серий
    py -3 tools\hdart\pedia_batch.py run --variant hd --batch 1 # через gpuq: описания + генерация

run: описания картинок моделью Ollama (копятся в captions.json, повторно не спрашиваются),
выгрузка Ollama, задание jobs.json, pedia_ab.py новой моделью в art\pedia_regen\<серия>_NN,
лист «оригинал | вышло». В мод ничего не пишет: подключать после выбора Vitali.
"""
import argparse
import base64
import io
import json
import os
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENC = "utf-8-sig"
PIR = os.path.join("Пиратки", "Dioxine_XPiratez", "user", "mods")
ORIG = os.path.join(PIR, "Piratez", "Resources", "Pedia")
HD_IN = os.path.join(PIR, "hd", "hd", "UI_esrgan")
ROOT = os.path.join("art", "pedia_regen")
TEXT = os.path.join(ROOT, "pedia_text.json")
PY_NEW = r"E:\train\.venv-train\Scripts\python.exe"
MODEL = "orcarouter/Qwen3.8-27B-Uncensored:q5_K_M"
HOST = "http://127.0.0.1:11434"

STOCK_SECTIONS = {"STR_WEAPONS_AND_EQUIPMENT", "STR_TROPHIES_UC"}
ORDER = ["ship", "STR_LORE_UC", "STR_PIRATING_TIPS_UC", "STR_ALIEN_LIFE_FORMS",
         "STR_HEAVY_WEAPONS_PLATFORMS", "STR_ALIEN_RESEARCH_UC", "STR_UFO_COMPONENTS",
         "STR_ALIEN_ARTIFACTS", "STR_BASE_FACILITIES", "STR_COMMENDATIONS_UC", ""]

# ---------------------------------------------------------------- промпты (из пробы art/_refs/pedia_ab)
PHOTO = ("Turn this drawn illustration into a real photograph of exactly the same scene, a cinematic film still "
         "shot with a real camera: the same composition, framing, camera angle, colours, light and background. "
         "Do not add, remove or move anything; the background stays what it is and no new scenery is invented. "
         "No outlines, no cel shading, no drawing look. ")
FREE = ("Make a real cinematic film still of this machine, as if it were actually built and filmed for a "
        "big-budget science fiction movie: keep its silhouette, proportions, camera angle and position in the "
        "frame, and the setting behind it exactly as drawn. Every part keeps exactly its own colour from the "
        "drawing - the hull, the cockpit, the engines, the sky and the ground - no part is repainted in another "
        "colour, and the colours are as clear and strong as in the drawing, not greyed. Cinematic dramatic "
        "light and contrast, painted metal with fine panel lines and real materials; only light wear. ")
# прежний FREE («wear, dirt») на 1.0 выцветал в серый (серия hd_01). Пример цвета в тексте («a green hull
# stays green») нельзя: модель красит им всё (R-016). Выбор Vitali 26.09 - лист art/_refs/pedia_fix/sheet2
NEG_CINE = (", desaturated, muted colours, repainted, wrong colours, uniform green, washed out, faded paint, "
            "dull, overcast, rust, mud, dirty")
STYLE = ("Redraw this picture as a high-resolution version of the very same illustration, in the original "
         "artist's own style: the same painting technique, brushwork, shading, line work and palette, only "
         "crisp and finely detailed - it stays a hand-made illustration and does not become a photograph. "
         "The same composition, framing, camera angle, colours and background; do not add, remove or move "
         "anything. ")
PEOPLE = ("Every figure stays exactly as drawn: the same number of figures, the same faces, facial expressions "
          "and emotions, the same poses, gestures, hair and bodies. The pose and the direction of the gaze must "
          "NOT change: each head keeps its exact turn and tilt, the eyes look exactly where they look in the "
          "drawing - never at the camera unless the drawing does. The characters are fictional: do not turn "
          "anyone into a known person or a specific real animal; animal ears, tails, horns, alien skin and "
          "other non-human features stay exactly as drawn. ")
NOBODY = ("There are no people or creatures in this picture and there must be none in the result: do not add "
          "any person, pilot, figure, silhouette or creature. ")
AS_DRAWN = "Clothing stays exactly as drawn: bare skin stays bare, covered stays covered. "
UNDERWEAR = ("Wherever breasts or the groin are bare in the drawing, they are now covered by plain black "
             "underwear: a black bra whose cups fully cover the breasts, so no bare breast shows from any side, "
             "and black briefs. Everything else - body, pose, the rest of the clothing - is unchanged. ")
ALLURE = ("Make her more seductive while she stays dressed: the same outfit, only worn more revealingly - "
          "%s. She is NOT nude: her clothing stays on, no bare nipples, no bare groin. The same face, the "
          "same expression and gaze, the same pose, the same objects in her hands and the same background. ")
STRICT = ("Only what is visible in the drawing may appear: do not add any person, creature, object, weapon, "
          "vehicle or building that is not in it, and do not add hands, arms, legs, feet or fingers that are not "
          "visible - whatever the frame cuts off stays cut off at exactly the same place, and the figure is "
          "never extended to a full body. The background is not changed: exactly the background of the "
          "drawing with the same colours and light, and nothing is added to it. ")
# не называть в STRICT «здания, ориентиры»: на кораблях без города модель дорисовывала полосу города
# внизу кадра (серия hd_01, CA_11, CA_13, CA_14, Aircar)

NEG_PHOTO = ("anime, manga, cartoon, comic, illustration, drawing, painting, cel shading, outlines, lowres, "
             "blurry, deformed, extra limbs, extra fingers, text, watermark, logo")
NEG_STYLE = ("photograph, photorealistic, 3d render, cgi, film grain, depth of field, lowres, blurry, deformed, "
             "extra limbs, extra fingers, text, watermark, logo")
NEG_NOBODY = ", people, person, human, man, woman, pilot, figure, crowd, soldier, creature"
NEG_GAZE = ", looking at the camera, eye contact, looking at the viewer, changed pose, different head turn"
NEG_NUDE_HD = ", nipples, bare breasts, bare groin, nudity"
NEG_NAKED = ", nude, naked, nipples, bare breasts, bare groin"
NEG_STRICT = (", extra people, extra objects, added background details, changed background, different "
              "scenery, extra hands, extra arms, extra legs, extra fingers, full body shot, zoomed out")

ASK = """This is a picture from the encyclopedia of the game X-Piratez (a mod of the 1994 game X-COM).
The article it illustrates: {facts}
Describe ONLY what is drawn, not what the article says. Answer strictly as JSON with keys:
"item_only": true if the picture is just one object, weapon, tool, item, device, box or piece of equipment shown by itself on a plain or empty background (a catalogue picture), with no scene, no person, no creature and no place; otherwise false;
"figures": number of people, humanoids, aliens, animals or creatures drawn (0 if none);
"women": number of women or female characters among them;
"topless": true if any bare female breast or nipple is visible;
"bottomless": true if any bare genitals or bare groin are visible;
"en": 2-3 English sentences for an image prompt: what is drawn, who and what they look like (species features such as cat ears or tails, clothing, what they hold), their pose, and the background; no style words, no names from the article;
"gaze": for every figure, where the head is turned and where the eyes look, e.g. "head turned left, eyes look down to the lower left, not at the viewer"; empty string if no figures;
"clothes": what the main woman wears, a short English phrase; empty string if no women."""


def load(path, default):
    if os.path.exists(path):
        with io.open(path, encoding=ENC) as f:
            return json.load(f)
    return default


def save(path, data):
    tmp = path + ".tmp"
    with io.open(tmp, "w", encoding=ENC) as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


# ---------------------------------------------------------------- план
def classify(rec):
    arts = rec.get("articles", [])
    for a in arts:
        if a.get("type_id") == "2":
            return None, "оружие корабля"
        if a.get("section") in STOCK_SECTIONS:
            return None, "предмет: " + a["section"]
        if a.get("section") == "STR_XCOM_CRAFT_ARMAMENT" and a.get("type_id") != "1":
            return None, "снаряжение корабля"
    for a in arts:
        if a.get("type_id") == "1" or a.get("section") == "STR_UFOS":
            return "ship", ""
    return (arts[0].get("section", "") if arts else ""), ""


def plan(size):
    text = load(TEXT, {})
    have = {f.lower(): f for f in os.listdir(ORIG)}
    order, skip, info = [], {}, {}
    for key, rec in sorted(text.items()):
        f = have.get(rec["file"].lower())
        if not f:
            skip[key] = "не в Resources\\Pedia"
            continue
        kind, why = classify(rec)
        if kind is None:
            skip[key] = why
            continue
        a = (rec.get("articles") or [{}])[0]
        info[key] = {"file": f, "kind": kind,
                     "title": (a.get("title") or {}).get("en-US", ""),
                     "text": (a.get("text") or {}).get("en-US", "")[:500]}
        order.append(key)
    rank = {s: i for i, s in enumerate(ORDER)}
    order.sort(key=lambda k: (rank.get(info[k]["kind"], len(ORDER)), k))
    p = {"size": size, "order": order, "skip": skip, "info": info}
    save(os.path.join(ROOT, "plan.json"), p)
    return p


# ---------------------------------------------------------------- описания
def picture_b64(file):
    from PIL import Image
    name = os.path.splitext(file)[0]
    hd = os.path.join(HD_IN, name + ".png")
    im = Image.open(hd if os.path.exists(hd) else os.path.join(ORIG, file)).convert("RGB")
    s = 896.0 / max(im.size)
    im = im.resize((max(28, int(im.width * s)), max(28, int(im.height * s))), Image.LANCZOS)
    b = io.BytesIO()
    im.save(b, "PNG")
    return base64.b64encode(b.getvalue()).decode()


def ask(file, facts):
    body = {"model": MODEL, "stream": False, "think": False, "format": "json",
            # num_ctx обязателен (R-064): без него Ollama грузит полный контекст и уезжает на процессор
            "options": {"temperature": 0.2, "num_predict": 500, "num_ctx": 4096},
            "prompt": ASK.format(facts=facts), "images": [picture_b64(file)]}
    req = urllib.request.Request(HOST + "/api/generate", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        d = json.loads(json.loads(r.read().decode())["response"])
    b = lambda v: v is True or str(v).strip().lower() == "true"      # noqa: E731
    n = lambda v: int(v) if str(v).strip().isdigit() else 0           # noqa: E731
    return {"item_only": b(d.get("item_only")), "figures": n(d.get("figures")), "women": n(d.get("women")),
            "topless": b(d.get("topless")), "bottomless": b(d.get("bottomless")),
            "en": str(d.get("en", "")).strip(), "gaze": str(d.get("gaze", "")).strip(),
            "clothes": str(d.get("clothes", "")).strip()}


def unload_ollama():
    try:
        body = json.dumps({"model": MODEL, "keep_alive": 0}).encode()
        urllib.request.urlopen(urllib.request.Request(HOST + "/api/generate", body,
                                                      {"Content-Type": "application/json"}), timeout=60).read()
        print("Ollama выгружена", flush=True)
    except Exception as e:                                             # noqa: BLE001
        print("Ollama не выгрузилась: %s" % e, flush=True)


def caption(keys, info):
    cpath = os.path.join(ROOT, "captions.json")
    caps = load(cpath, {})
    todo = [k for k in keys if k not in caps]
    t0 = time.time()
    for i, k in enumerate(todo, 1):
        it = info[k]
        facts = "%s. %s" % (it["title"], it["text"])
        try:
            caps[k] = ask(it["file"], facts)
        except Exception as e:                                         # noqa: BLE001
            print("  описание %s: %s" % (k, e), flush=True)
            continue
        save(cpath, caps)
        el = time.time() - t0
        print("  описание %d/%d %s: %.1f с/шт, осталось ~%.0f мин" % (
            i, len(todo), it["file"], el / i, (len(todo) - i) * el / i / 60), flush=True)
    if todo:
        unload_ollama()
    return caps


# ---------------------------------------------------------------- задание
def spec_for(variant, it, c):
    """Промпт одного варианта или None, если варианту тут делать нечего."""
    who = c["figures"] > 0
    # свободно рисуем только машину без людей: с людьми действуют правила позы и взгляда (Bike_3 на 1.0
    # сменил позу, мотоцикл стал «существом» по ошибке описания)
    ship = it["kind"] == "ship" and not who
    nude = c["topless"] or c["bottomless"]
    desc = c["en"] + " " if c["en"] else ""
    if ship:
        # кораблю описания не даём вовсе, только название статьи: модель со зрением путает фон даже
        # в первой фразе (подводная сцена - «hovers in a deep blue sky», вышло ночное небо)
        desc = ("It is the %s. " % it["title"].strip().title()) if it.get("title") else ""
    if variant == "hd":
        p = (FREE if ship else PHOTO) + desc
        neg = NEG_PHOTO + (", low poly, plastic toy" + NEG_CINE if ship else "")
        strength = 0.95 if ship else 0.85
        if who:
            p += PEOPLE + (UNDERWEAR if nude else AS_DRAWN)
            neg += NEG_NUDE_HD if nude else ""
            if nude and not ship:
                # на 0.85 бельё не закрывает грудь (BloomLady, BlueWitch, Book_Keeper), на 1.0 уходят
                # лицо и кадр; 0.92 - бельё на месте, поза и фон те же (лист art/_refs/pedia_nude)
                strength = 0.92
        else:
            p += NOBODY
            neg += NEG_NOBODY
    elif variant == "style":
        p, neg, strength = STYLE + desc, NEG_STYLE, 1.0
        if who:
            p += PEOPLE + AS_DRAWN
        else:
            p += NOBODY
            neg += NEG_NOBODY
    else:                                   # 18: только там, где она отличается от обычной
        if not who or not c["women"]:
            return None
        if nude:                            # раздетая на оригинале: как нарисовано (обычная - в белье)
            p = (FREE if ship else PHOTO) + desc + PEOPLE + AS_DRAWN
            neg = NEG_PHOTO + ", bra, shirt"
        else:                               # одетая: не раздевать, подчеркнуть
            what = "unbuttoned further, a deeper neckline, the clothes fitting tighter"
            if c["clothes"]:
                what = "her %s unbuttoned or opened further, a deeper neckline, fitting tighter" % c["clothes"]
            p = (FREE if ship else PHOTO) + desc + PEOPLE + ALLURE % what
            neg = NEG_PHOTO + NEG_NAKED
        strength = 0.95 if ship else 0.85
    p += STRICT
    neg += NEG_STRICT
    if who:
        # взгляд словами из описания НЕ даём: модель со зрением путает его (Bike_3: «смотрит вправо»
        # при взгляде вниз-влево), а неверные слова уводят взгляд. Держит сила 0.85 и правило PEOPLE
        neg += NEG_GAZE
    return {"prompt": p, "neg": neg, "strength": strength}


def sheet(out_dir, keys, info, tag, variant):
    from PIL import Image, ImageDraw
    W, H, per = 480, 300, 20
    rows = [(k, os.path.join(out_dir, "%s__%s__%s.png" % (os.path.splitext(info[k]["file"])[0], variant, tag)))
            for k in keys]
    rows = [r for r in rows if os.path.exists(r[1])]
    for s in range(0, len(rows), per):
        part = rows[s:s + per]
        cols = 2
        n = (len(part) + cols - 1) // cols
        sh = Image.new("RGB", (cols * (2 * W + 30), n * (H + 22) + 10), (26, 26, 30))
        d = ImageDraw.Draw(sh)
        for i, (k, path) in enumerate(part):
            x = (i % cols) * (2 * W + 30) + 10
            y = (i // cols) * (H + 22) + 20
            o = Image.open(os.path.join(ORIG, info[k]["file"])).convert("RGB").resize((W, H), Image.NEAREST)
            g = Image.open(path).convert("RGB").resize((W, H), Image.LANCZOS)
            sh.paste(o, (x, y))
            sh.paste(g, (x + W + 4, y))
            d.text((x, y - 14), info[k]["file"], fill=(255, 220, 0))
        dst = os.path.join(out_dir, "sheet_%02d.jpg" % (s // per + 1))
        sh.save(dst, quality=88)
        print(dst, flush=True)


def run(a):
    p = load(os.path.join(ROOT, "plan.json"), None) or plan(a.size)
    size = p["size"]
    keys = p["order"][(a.batch - 1) * size:a.batch * size]
    if not keys:
        print("серии %d нет: всего картинок %d" % (a.batch, len(p["order"])))
        return 0
    info = p["info"]
    print("серия %s %d: картинок %d (%s .. %s)" % (a.variant, a.batch, len(keys), keys[0], keys[-1]), flush=True)
    caps = caption(keys, info)
    out_dir = os.path.join(ROOT, "%s_%02d" % (a.variant, a.batch))
    os.makedirs(out_dir, exist_ok=True)
    jobs, skipped = [], {}
    for k in keys:
        c = caps.get(k)
        if c is None:
            skipped[k] = "нет описания"
            continue
        if c["item_only"] and info[k]["kind"] != "ship":
            skipped[k] = "предмет на пустом фоне"
            continue
        s = spec_for(a.variant, info[k], c)
        if s is None:
            skipped[k] = "варианту нечего делать"
            continue
        jobs.append({"file": info[k]["file"], "variants": {a.variant: s}})
    jpath = os.path.join(out_dir, "jobs.json")
    save(jpath, jobs)
    save(os.path.join(out_dir, "skipped.json"), skipped)
    print("заданий %d, пропущено %d: %s" % (len(jobs), len(skipped),
                                            ", ".join("%s (%s)" % kv for kv in list(skipped.items())[:12])),
          flush=True)
    if a.no_gen or not jobs:
        return 0
    cmd = [PY_NEW, os.path.join(HERE, "pedia_ab.py"), "--model", "new", "--jobs", jpath,
           "--out", out_dir, "--tag", a.tag]
    print(" ".join(cmd), flush=True)
    rc = subprocess.call(cmd)
    sheet(out_dir, keys, info, a.tag, a.variant)
    return rc


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    pl = sub.add_parser("plan")
    pl.add_argument("--size", type=int, default=100)
    r = sub.add_parser("run")
    r.add_argument("--variant", choices=["hd", "style", "18"], required=True)
    r.add_argument("--batch", type=int, required=True, help="номер серии с 1")
    r.add_argument("--size", type=int, default=100)
    r.add_argument("--tag", default="v1")
    r.add_argument("--no-gen", dest="no_gen", action="store_true", help="только описания и задание")
    a = ap.parse_args()
    if a.cmd == "plan":
        p = plan(a.size)
        from collections import Counter
        kinds = Counter(p["info"][k]["kind"] for k in p["order"])
        whys = Counter(v.split(":")[0] for v in p["skip"].values())
        print("рисовать %d, серий по %d: %d" % (len(p["order"]), a.size, -(-len(p["order"]) // a.size)))
        for k, v in kinds.most_common():
            print("  %5d %s" % (v, k or "(без раздела)"))
        print("стоком / мимо: %d" % len(p["skip"]))
        for k, v in whys.most_common():
            print("  %5d %s" % (v, k))
        return 0
    return run(a)


if __name__ == "__main__":
    sys.exit(main())
