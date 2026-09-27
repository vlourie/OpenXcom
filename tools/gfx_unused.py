#!/usr/bin/env python3
"""
Графика мода, которую игра не грузит: файл лежит на диске, а рулсеты на него не ссылаются.

    tools/hdart/.venv/Scripts/python.exe tools/gfx_unused.py
    tools/hdart/.venv/Scripts/python.exe tools/gfx_unused.py --mod "Пиратки/Dioxine_XPiratez/user/mods/Piratez"

Нужен PyYAML (через rul_map.py): в системном py -3 его нет, в tools/hdart/.venv есть.
Сводка по-английски для человека - docs/research/piratez-unused-gfx.md.

Ссылки собираются так, как их разрешает движок:
    - строка-путь в любом поле рулсета (extraSprites files, cutscenes imagePath, ...),
      без учёта регистра, как FileMap;
    - путь с '/' на конце - папка: грузятся все картинки прямо в ней
      (ExtraSprites::loadSurfaceSet, isImageFile);
    - имя в mapDataSets - это TERRAIN/<имя>.PCK и .TAB (MapDataSet);
    - шрифты: движок читает ОДИН файл Language/<fontName> (последний fontName в
      рулсетах, файл - из мода, который грузится последним, Mod.cpp loadFonts);
      его images[].file - картинки, путь относительно Language/.
Источники: мастер-мод (standard/<master>) и все АКТИВНЫЕ моды из user/options.cfg.
Закомментированная строка ссылкой не считается - рулсеты читаются YAML-разбором.

Второй уровень - файл упомянут, но затёрт: в том же наборе extraSprites тот же кадр
позже пишет другой файл (порядок - как Mod::loadMod, rul_map.rul_files), или тот же
относительный путь лежит в моде, который грузится позже (FileMap берёт последний).
Смещение модов (Mod::getOffset) учтено грубо: затирание кадра ищется только внутри
одного мода, между модами - только для singleImage.

Не проверяется: кадры набора, на которые не ссылается ни один предмет или броня
(bigSprite, floorSprite, spriteSheet...), - это уже не файлы, а номера.

Кладёт census/gfx_unused.tsv (полный список) и печатает сводку.
"""
from __future__ import annotations

import argparse, re, sys
from collections import defaultdict, Counter
from pathlib import Path

from yaml.nodes import MappingNode, ScalarNode, SequenceNode

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rul_map import compose, rul_files  # noqa: E402  (Tolerant, R-046)

ENC_W = "utf-8-sig"   # R-001
ENC_R = "utf-8-sig"

ROOT = Path(__file__).resolve().parent.parent
INSTALL = ROOT / "Пиратки/Dioxine_XPiratez"
DEF_MOD = INSTALL / "user/mods/Piratez"
DEF_OUT = ROOT / "census/gfx_unused.tsv"

IMG = {"png", "gif", "bmp", "lbm", "iff", "pcx", "tga", "tif", "tiff"}   # isImageFile
GFX = IMG | {"pck", "tab", "spk", "scr", "bdy", "jpg", "jpeg"}


def norm(s: str) -> str:
    s = s.strip().replace(chr(92), "/").lower()
    while s.startswith("./"):
        s = s[2:]
    return s


def meta(folder: Path) -> dict:
    out = {}
    p = folder / "metadata.yml"
    if p.exists():
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.match(r"^(\w+)\s*:\s*(.*?)\s*$", line)
            if m:
                out[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return out


def active_mods(install: Path):
    """[(id, папка)] активных модов в порядке options.cfg, мастер впереди своих."""
    folders = {}
    for d in (install / "user/mods").iterdir():
        if d.is_dir():
            folders[meta(d).get("id", d.name)] = d
    ids, cur = [], None
    for line in (install / "user/options.cfg").read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"^\s*-\s*active:\s*(\w+)", line)
        if m:
            cur = m.group(1) == "true"
            continue
        m = re.match(r"^\s*id:\s*(\S+)", line)
        if m and cur is not None:
            if cur:
                ids.append(m.group(1).strip('"'))
            cur = None
        if re.match(r"^\S", line) and not line.startswith("mods:") and ids:
            break
    return [(i, folders[i]) for i in ids if i in folders]


def walk(node, key, visit):
    """visit(ключ-родитель, строка) для каждой скалярной строки."""
    if isinstance(node, ScalarNode):
        visit(key, node.value)
    elif isinstance(node, SequenceNode):
        for n in node.value:
            walk(n, key, visit)
    elif isinstance(node, MappingNode):
        for k, v in node.value:
            walk(v, k.value if isinstance(k, ScalarNode) else key, visit)


def scalar(node: MappingNode, key: str):
    for k, v in node.value:
        if isinstance(k, ScalarNode) and k.value == key and isinstance(v, ScalarNode):
            return v.value
    return None


def child(node: MappingNode, key: str):
    for k, v in node.value:
        if isinstance(k, ScalarNode) and k.value == key:
            return v
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mod", type=Path, default=DEF_MOD)
    ap.add_argument("--install", type=Path, default=INSTALL)
    ap.add_argument("--out", type=Path, default=DEF_OUT)
    a = ap.parse_args()
    mod = a.mod.resolve()

    mods = active_mods(a.install)
    master = meta(mod).get("master")
    sources = []                                  # (id, папка) в порядке загрузки
    if master and (a.install / "standard" / master).is_dir():
        sources.append((master, a.install / "standard" / master))
    sources += mods
    order = {i: n for n, (i, _) in enumerate(sources)}
    my_id = meta(mod).get("id", mod.name)

    # --- файлы на диске: всех источников (для затирания по пути) и свои
    disk = {}                                      # norm rel -> [(mod id, Path)]
    for mid, d in sources:
        for p in d.rglob("*"):
            if p.is_file() and p.suffix[1:].lower() in GFX:
                disk.setdefault(norm(str(p.relative_to(d))), []).append((mid, p))
    mine = {r: next(p for m, p in v if m == my_id) for r, v in disk.items()
            if any(m == my_id for m, _ in v)}
    folders = defaultdict(list)                    # папка/ -> картинки прямо в ней
    for r in disk:
        if r.rsplit(".", 1)[-1] in IMG:
            folders[r.rsplit("/", 1)[0] + "/" if "/" in r else ""].append(r)

    # --- ссылки
    refs = defaultdict(set)                        # norm rel -> {"mod:файл"}
    terr = defaultdict(set)                        # имя набора (lower) -> {источник}
    sprite_writes = []                             # (order, mod, file_idx, type, single, frame, rel, where)
    unresolved = defaultdict(set)                  # путь без файла в модах -> {источник}
    nfiles = 0
    font_name = ("Font.dat", "по умолчанию")
    for mid, d in sources:
        files = rul_files(d / "Ruleset") if (d / "Ruleset").is_dir() else []
        for fidx, rp in enumerate(files):
            nfiles += 1
            where = f"{mid}:{rp.relative_to(d).as_posix()}"
            try:
                root = compose(rp)
            except Exception as e:
                print(f"!! не разобран {where}: {str(e)[:120]}")
                continue
            if root is None:
                continue
            if isinstance(root, MappingNode) and scalar(root, "fontName"):
                font_name = (scalar(root, "fontName"), where)

            def visit(key, s, where=where):
                if key == "mapDataSets":
                    terr[s.strip().lower()].add(where)
                    return
                n = norm(s)
                if not n or " " in n and "/" not in n:
                    return
                if n.endswith("/"):
                    for r in folders.get(n, ()):
                        refs[r].add(where + " (папка)")
                    return
                if "." in n.rsplit("/", 1)[-1] and n.rsplit(".", 1)[-1] in GFX:
                    refs[n].add(where)
                    if n not in disk and "/" in n:      # без '/' - имя набора (MAN_0.SPK)
                        unresolved[n].add(where.split(":", 1)[0])

            walk(root, None, visit)

            # extraSprites: кто какой кадр пишет - для затирания
            if isinstance(root, MappingNode):
                es = child(root, "extraSprites")
                if isinstance(es, SequenceNode):
                    for en in es.value:
                        if not isinstance(en, MappingNode):
                            continue
                        single = scalar(en, "typeSingle")
                        typ = single or scalar(en, "type")
                        fm = child(en, "files")
                        fs = child(en, "fileSingle")           # typeSingle + fileSingle, первый ключ
                        if isinstance(fs, ScalarNode):
                            fm = MappingNode("tag:yaml.org,2002:map",
                                             [(ScalarNode("tag:yaml.org,2002:int", "0",
                                                          start_mark=fs.start_mark), fs)])
                        if not typ or not isinstance(fm, MappingNode):
                            continue
                        is_single = bool(single) or str(scalar(en, "singleImage")).lower() == "true"
                        w, h = scalar(en, "width"), scalar(en, "height")
                        sx, sy = scalar(en, "subX"), scalar(en, "subY")
                        for kn, vn in fm.value:
                            if not isinstance(vn, ScalarNode):
                                continue
                            try:
                                start = int(kn.value)
                            except ValueError:
                                continue
                            n = norm(vn.value)
                            if n.endswith("/"):
                                imgs = sorted(folders.get(n, ()), key=natural)
                                frames = [(start + i, r) for i, r in enumerate(imgs)]
                            elif sx and sy and w and h and not is_single:
                                cnt = (int(w) // int(sx)) * (int(h) // int(sy))
                                frames = [(start + i, n) for i in range(cnt)]
                            else:
                                frames = [(start, n)]
                            for fr, r in frames:
                                sprite_writes.append((order[mid], mid, fidx, typ, is_single, fr, r,
                                                      f"{where}:{kn.start_mark.line + 1}"))

    # --- шрифт: один файл, из мода, который грузится последним
    font_file = None
    for mid, d in sources:
        p = d / "Language" / font_name[0]
        if p.exists():
            font_file = (mid, p)
    if font_file:
        fwhere = f"{font_file[0]}:Language/{font_name[0]} (fontName из {font_name[1]})"

        def fvisit(key, s):
            if key == "file":
                refs["language/" + norm(s)].add(fwhere)

        walk(compose(font_file[1]), None, fvisit)
    # свой шрифт мода, если его затёр чужой: в другой установке он живой
    own_font = {}
    p = mod / "Language" / font_name[0]
    if font_file and p.exists() and font_file[1] != p:
        def ovisit(key, s):
            if key == "file":
                own_font["language/" + norm(s)] = font_file[0]
        walk(compose(p), None, ovisit)

    # --- затирание кадров: последний писатель кадра побеждает
    last = {}                                      # (mod|*, type, frame) -> rel
    for o, mid, fidx, typ, single, fr, r, w in sorted(sprite_writes, key=lambda x: (x[0], x[2])):
        scope = "*" if single else mid
        last[(scope, typ, 0 if single else fr)] = (r, w)
    shadowed = defaultdict(list)                   # rel -> [(type, frame, кто затёр)]
    alive = set()
    for o, mid, fidx, typ, single, fr, r, w in sprite_writes:
        scope = "*" if single else mid
        win = last[(scope, typ, 0 if single else fr)]
        if win[0] == r:
            alive.add(r)
        else:
            shadowed[r].append((typ, fr, win[1], win[0]))

    # --- итог по своим файлам
    rows = []
    for r, p in sorted(mine.items()):
        ext = r.rsplit(".", 1)[-1]
        size = p.stat().st_size
        rel = p.relative_to(mod).as_posix()
        top = rel.split("/", 1)[0] if "/" in rel else "."
        later = [m for m, _ in disk[r] if order[m] > order[my_id]]
        if ext in ("pck", "tab") and top.upper() == "TERRAIN":
            stem = r.rsplit("/", 1)[-1].rsplit(".", 1)[0]
            if stem in terr:
                continue
            status, why = "unused", "TERRAIN: имени нет ни в одном mapDataSets"
        elif ext == "tab" and (r[:-3] + "pck") in mine:
            continue                                  # TAB идёт за своим PCK
        elif r not in refs and r in own_font:
            status = "shadowed"
            why = (f"шрифт мода: Language/{font_name[0]} берётся из {own_font[r]}, "
                   f"без него картинка живая")
        elif r not in refs:
            status, why = "unused", "ни один рулсет не ссылается"
        elif r in shadowed and r not in alive:
            s = shadowed[r][0]
            status = "overwritten"
            why = f"{s[0]} кадр {s[1]}: позже пишет {s[3]} ({s[2]})"
            if len(shadowed[r]) > 1:
                why += f" и ещё {len(shadowed[r]) - 1}"
        else:
            if later:
                status, why = "shadowed", "тот же путь в моде " + ", ".join(later) + " (грузится позже)"
            else:
                continue
        if status != "shadowed" and later:
            why += "; путь есть и в " + ", ".join(later)
        rows.append((status, top, ext, size, rel, why))

    a.out.parent.mkdir(parents=True, exist_ok=True)
    with a.out.open("w", encoding=ENC_W, newline="\n") as f:
        f.write("status\tfolder\text\tbytes\tfile\twhy\n")
        for row in rows:
            f.write("\t".join(str(x) for x in row) + "\n")

    total = Counter((r.rsplit(".", 1)[-1]) for r in mine)
    print(f"источников: {len(sources)} ({', '.join(i for i, _ in sources)}), рулсетов и шрифтов: {nfiles}")
    print(f"графических файлов в {my_id}: {len(mine)}  {dict(total)}")
    print(f"наборов в mapDataSets: {len(terr)}, строк-путей: {len(refs)}, путей без файла: {len(unresolved)}")
    multi = Counter(("*" if s else m, t, 0 if s else fr) for _, m, _, t, s, fr, _, _ in sprite_writes)
    print(f"кадров extraSprites записано: {len(sprite_writes)}, в разные кадры: {len(multi)}, "
          f"кадр пишут дважды и больше: {sum(1 for v in multi.values() if v > 1)}")
    by_src = Counter(m for s in unresolved.values() for m in s)
    print("  путей без файла по модам (у xcom1 файлы в UFO/, это норма):", dict(by_src))
    by = Counter((s, t) for s, t, *_ in rows)
    mb = defaultdict(int)
    for s, t, e, b, *_ in rows:
        mb[(s, t)] += b
    for (s, t), n in sorted(by.items()):
        print(f"  {s:12} {t:12} {n:6}  {mb[(s, t)] / 1048576:8.1f} МБ")
    print(f"записано {len(rows)} строк -> {a.out}")


def natural(s: str):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]


if __name__ == "__main__":
    main()
