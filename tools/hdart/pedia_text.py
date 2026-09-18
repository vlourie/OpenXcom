#!/usr/bin/env python3
"""Collects, for every pedia picture of a mod, the article that shows it and the article's text.

The chain is: the picture file (Resources/Pedia/<name>.png) -> the sprite that points at it
(extraSprites: typeSingle / fileSingle) -> the Bootypedia article that shows that sprite
(ufopaedia: image_id) -> the article's title (its id) and body (its text:) in Language/<lang>.yml.
Cutscene slides (imagePath + caption) are picked up too, so a picture used only in an ending still
gets its words.

    py -3 tools\\hdart\\pedia_text.py --mod "...\\user\\mods\\Piratez" --out tools\\hdart\\pedia_text.json
    py -3 tools\\hdart\\pedia_text.py --mod "...\\user\\mods\\Piratez" --show MBT

The json is keyed by the picture's base name in lower case; --text <folder> also writes one
<name>.txt per picture, ready to read next to the picture itself.
"""
import argparse
import io
import json
import os
import re
import sys

try:
    import yaml
    try:
        from yaml import CSafeLoader as Loader
    except ImportError:
        from yaml import SafeLoader as Loader
except ImportError:
    yaml = None

ITEM = re.compile(r"^(\s*)-\s+(.*)$")
KEY = re.compile(r"^(\s*)([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$")
TOP = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):\s*$")


def unquote(v):
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        v = v[1:-1]
    return v


def sections(path):
    """Yields (section, item) for every `- key: value` list item two spaces in, with the flat
    `key: value` lines that follow it. Deeper nesting is skipped; that is all a .rul needs here."""
    section = ""
    item = None
    indent = -1
    with io.open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.rstrip("\n").rstrip("\r")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            m = TOP.match(line)
            if m:
                if item:
                    yield section, item
                    item = None
                section = m.group(1)
                continue
            if line[0] not in " \t":          # a top-level key with a value: end of the section
                if item:
                    yield section, item
                    item = None
                section = ""
                continue
            m = ITEM.match(line)
            if m and len(m.group(1)) <= 2:
                if item:
                    yield section, item
                item = {}
                indent = len(m.group(1)) + 2
                rest = m.group(2)
                k = KEY.match(rest)
                if k:
                    item[k.group(2)] = unquote(k.group(3))
                continue
            if item is None:
                continue
            k = KEY.match(line)
            if k and len(k.group(1)) == indent:
                item[k.group(2)] = unquote(k.group(3))
    if item:
        yield section, item


def slides(path):
    """Cutscene slides: `- imagePath: <file>` with the `caption:` that follows it."""
    out = []
    pending = None
    with io.open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            s = line.strip()
            if s.startswith("- imagePath:") or s.startswith("imagePath:"):
                pending = unquote(s.split(":", 1)[1])
                out.append([pending, ""])
            elif out and s.startswith("caption:") and not out[-1][1]:
                out[-1][1] = unquote(s.split(":", 1)[1])
    return out


def load_lang(path):
    with io.open(path, encoding="utf-8", errors="replace") as f:
        data = yaml.load(f, Loader=Loader)
    if not isinstance(data, dict):
        return {}
    # the file is `<lang>: { STR_...: text }`
    for v in data.values():
        if isinstance(v, dict):
            return {k: ("" if x is None else str(x)) for k, x in v.items()}
    return {}


def base(name):
    return os.path.splitext(os.path.basename(name.replace("\\", "/")))[0].lower()


def collect(mod, langs):
    rules = os.path.join(mod, "Ruleset")
    files = sorted(f for f in os.listdir(rules) if f.lower().endswith(".rul"))
    sprite_file = {}      # sprite id -> picture file (as written in the ruleset)
    articles = []         # every ufopaedia item that shows a picture
    slide_use = {}        # picture base name -> [caption keys]
    for f in files:
        path = os.path.join(rules, f)
        for section, item in sections(path):
            if section == "extraSprites":
                t, p = item.get("typeSingle"), item.get("fileSingle")
                if t and p:
                    sprite_file[t] = p
            elif section == "ufopaedia" and item.get("image_id"):
                articles.append(item)
        for pic, cap in slides(path):
            if cap:
                slide_use.setdefault(base(pic), []).append(cap)

    words = {}
    for code in langs:
        p = os.path.join(mod, "Language", code + ".yml")
        words[code] = load_lang(p) if os.path.exists(p) else {}

    by_file = {}
    for item in articles:
        sprite = item["image_id"]
        pic = sprite_file.get(sprite)
        if not pic:
            # some articles name the picture file directly
            pic = sprite if "." in sprite else None
        key = base(pic) if pic else None
        if not key:
            continue
        rec = by_file.setdefault(key, {"file": os.path.basename((pic or "").replace("\\", "/")),
                                       "sprites": [], "articles": [], "slides": []})
        if sprite not in rec["sprites"]:
            rec["sprites"].append(sprite)
        art = {"id": item.get("id", ""), "section": item.get("section", ""),
               "type_id": item.get("type_id", ""), "text_key": item.get("text", ""),
               "title": {}, "text": {}}
        for code in langs:
            w = words.get(code, {})
            if art["id"] in w:
                art["title"][code] = w[art["id"]]
            if art["text_key"] and art["text_key"] in w:
                art["text"][code] = w[art["text_key"]]
        rec["articles"].append(art)

    for key, caps in slide_use.items():
        rec = by_file.setdefault(key, {"file": key + ".png", "sprites": [], "articles": [], "slides": []})
        for cap in caps:
            s = {"caption_key": cap, "text": {}}
            for code in langs:
                if cap in words.get(code, {}):
                    s["text"][code] = words[code][cap]
            rec["slides"].append(s)
    return by_file, sprite_file


def as_text(key, rec, langs):
    out = ["# %s" % rec.get("file", key)]
    if rec.get("sprites"):
        out.append("sprite: " + ", ".join(rec["sprites"]))
    for art in rec.get("articles", []):
        out.append("")
        out.append("== %s (%s)" % (art["id"], art.get("section", "")))
        for code in langs:
            if art["title"].get(code):
                out.append("%s title: %s" % (code, art["title"][code]))
        for code in langs:
            if art["text"].get(code):
                out.append("%s text: %s" % (code, art["text"][code].replace("\n", " ")))
    for s in rec.get("slides", []):
        out.append("")
        out.append("== cutscene slide %s" % s["caption_key"])
        for code in langs:
            if s["text"].get(code):
                out.append("%s: %s" % (code, s["text"][code].replace("\n", " ")))
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mod", required=True, help="the mod folder (with Ruleset/ and Language/)")
    ap.add_argument("--lang", default="en-US,ru", help="languages to take the words from")
    ap.add_argument("--out", default="", help="where to write the json")
    ap.add_argument("--text", default="", help="folder for one <name>.txt per picture")
    ap.add_argument("--names", default="", help="only these pictures (file with one name per line, or a comma list)")
    ap.add_argument("--show", default="", help="print one picture's words and stop")
    args = ap.parse_args()

    if yaml is None:
        print("pyyaml is missing: py -3 -m pip install pyyaml")
        return 2
    langs = [c.strip() for c in args.lang.split(",") if c.strip()]
    by_file, sprite_file = collect(args.mod, langs)
    print("pictures with words: %d (sprites: %d)" % (len(by_file), len(sprite_file)))

    if args.show:
        key = base(args.show)
        if key in by_file:
            sys.stdout.write(as_text(key, by_file[key], langs))
        else:
            print("no article shows %s" % args.show)
        return 0

    wanted = None
    if args.names:
        if os.path.exists(args.names):
            wanted = [base(l) for l in io.open(args.names, encoding="utf-8") if l.strip()]
        else:
            wanted = [base(n) for n in args.names.split(",") if n.strip()]
        missing = [n for n in wanted if n not in by_file]
        print("asked for %d, without an article: %d" % (len(wanted), len(missing)))
        if missing:
            print("  " + ", ".join(missing[:20]) + (" ..." if len(missing) > 20 else ""))

    picked = {k: v for k, v in by_file.items() if wanted is None or k in wanted}
    if args.out:
        with io.open(args.out, "w", encoding="utf-8") as f:
            json.dump(picked, f, ensure_ascii=False, indent=1, sort_keys=True)
        print("json: %s (%d)" % (args.out, len(picked)))
    if args.text:
        os.makedirs(args.text, exist_ok=True)
        for k, v in picked.items():
            with io.open(os.path.join(args.text, k + ".txt"), "w", encoding="utf-8") as f:
                f.write(as_text(k, v, langs))
        print("texts: %s (%d)" % (args.text, len(picked)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
