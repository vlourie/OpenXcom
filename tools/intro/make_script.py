#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Сценарий вступления: кадр, текст, длительность.

Берёт ту катсцену intro, которую игрок ВИДИТ, а не первую попавшуюся: проходит
активные моды установки в порядке загрузки из options.cfg и оставляет последнее
определение (русский патч Пираток свою intro объявляет заново, через delete).
Пишет два файла: docs/intro-script.md для человека и tools/intro/scenes.json для
build_intro.py.

  python tools/intro/make_script.py --pz "E:/OpenXCom/Пиратки/Dioxine_XPiratez"
"""

import argparse
import io
import json
import os
import re

ENC = "utf-8-sig"
# 14 знаков в секунду - неспешное чтение вслух по-русски, проверено на длинных кусках
CHARS_PER_SEC = 14.0


def read_text(path):
    return io.open(path, encoding="utf-8", errors="replace").read()


def active_mods(pz):
    """Папки активных модов в порядке загрузки. Порядок решает, чья intro победит."""
    cfg = os.path.join(pz, "user", "options.cfg")
    if not os.path.exists(cfg):
        raise SystemExit("нет " + cfg)
    text = read_text(cfg)
    block = text[: text.find("\noptions:")] if "\noptions:" in text else text
    order = []
    for active, mod_id in re.findall(r"- active:\s*(\w+)\s*\n\s*id:\s*(\S+)", block):
        if active == "true":
            order.append(mod_id)

    # id -> папка: у мода он задан в metadata.yml, у стандартных совпадает с именем папки
    folders = {}
    for root in (os.path.join(pz, "user", "mods"), os.path.join(pz, "standard")):
        if not os.path.isdir(root):
            continue
        for name in os.listdir(root):
            path = os.path.join(root, name)
            meta = os.path.join(path, "metadata.yml")
            if not os.path.isfile(meta):
                continue
            found = re.search(r"^id:\s*(\S+)", read_text(meta), re.M)
            folders[found.group(1) if found else name] = path
    return [folders[i] for i in order if i in folders]


def intro_block(folder):
    """Определение катсцены intro в моде, если оно там есть."""
    best = None
    for root, _dirs, files in os.walk(folder):
        for name in sorted(files):
            if not name.lower().endswith(".rul"):
                continue
            text = read_text(os.path.join(root, name))
            if "cutscenes:" not in text:
                continue
            for match in re.finditer(r"^  - type: intro\s*$", text, re.M):
                tail = text[match.start():]
                nxt = re.search(r"\n(?=  - |\S)", tail[10:])
                best = tail[: nxt.start() + 10] if nxt else tail
    return best


def parse_block(block):
    """Слайды в порядке показа плюс шапка катсцены."""
    header = re.search(r"transitionSeconds:\s*(\d+)", block)
    music = re.search(r"musicId:\s*(\S+)", block)
    slides = []
    for chunk in block.split("- imagePath:")[1:]:
        cap = re.search(r"caption:\s*(STR_\S+)", chunk)
        slides.append({"image": chunk.splitlines()[0].strip(),
                       "caption": cap.group(1) if cap else ""})
    return slides, int(header.group(1)) if header else 30, music.group(1) if music else ""


def read_captions(folders):
    """Подписи из языковых файлов активных модов. Побеждает тот мод, что грузится позже."""
    out = {}
    for folder in folders:
        lang = os.path.join(folder, "Language")
        if not os.path.isdir(lang):
            continue
        for name in ("en-US.yml", "ru.yml"):
            path = os.path.join(lang, name)
            if not os.path.exists(path):
                continue
            for key, val in re.findall(r'^\s+(STR_[0-9A-Z_]+):\s*"(.*)"\s*$', read_text(path), re.M):
                out[key] = val
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--pz", default="E:/OpenXCom/Пиратки/Dioxine_XPiratez",
                   help="установка X-Piratez")
    p.add_argument("--out", default="docs/intro-script.md")
    p.add_argument("--json", default="tools/intro/scenes.json",
                   help="те же сцены машиночитаемо - их читает build_intro.py")
    args = p.parse_args()

    folders = active_mods(args.pz)
    block, owner = None, ""
    for folder in folders:
        found = intro_block(folder)
        if found:
            block, owner = found, os.path.basename(folder)
    if not block:
        raise SystemExit("ни один активный мод не объявляет катсцену intro")
    slides, default_secs, music = parse_block(block)
    caps = read_captions(folders)

    lines = ["# Сценарий вступления X-Piratez", "",
             "Собран `tools/intro/make_script.py` из катсцены `intro` мода **%s**" % owner,
             "(она грузится последней, её игрок и видит) и языковых файлов активных модов.",
             "Правится не здесь, а в источнике: заново прогони скрипт.", "",
             "Сейчас в игре: %d слайдов по %d секунд под музыку %s — это %.1f минуты."
             % (len(slides), default_secs, music, len(slides) * default_secs / 60.0),
             "", "| # | Кадр сейчас | Секунд на голос | Текст |", "|---|---|---|---|"]
    total = 0
    scenes = []
    for i, sl in enumerate(slides, 1):
        text = caps.get(sl["caption"], "").replace("{NEWLINE}", " ").replace("{SMALLLINE}", " ")
        secs = max(3, round(len(text) / CHARS_PER_SEC)) if text else 4
        total += secs
        lines.append("| %d | `%s` | %d | %s |"
                     % (i, os.path.basename(sl["image"]), secs, text or "*(без текста)*"))
        scenes.append({"n": i, "image": sl["image"], "caption": sl["caption"], "text": text})
    lines += ["", "Итого на озвучку примерно **%d:%02d**." % (total // 60, total % 60), "",
              "## Как этим пользоваться", "",
              "1. На каждую строку — своя картинка: `photo/NN.png`, номер как в таблице.",
              "2. На каждую строку — свой файл голоса: `voice/NN.wav`.",
              "3. Длительность слайда берётся из длины файла голоса, а не из этой оценки.",
              "4. Дальше `tools/intro/build_intro.py` — он собирает мод. См. `tools/intro/README.md`.", ""]

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    io.open(args.out, "w", encoding=ENC, newline="\r\n").write("\n".join(lines))
    os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
    io.open(args.json, "w", encoding=ENC).write(json.dumps(scenes, ensure_ascii=False, indent=1))
    print("написано:", args.out, "| мод:", owner, "| сцен:", len(slides),
          "| на озвучку %d:%02d" % (total // 60, total % 60))


if __name__ == "__main__":
    main()
