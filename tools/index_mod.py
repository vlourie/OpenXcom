#!/usr/bin/env python3
"""
Карта мода OpenXcom/OXCE: что в рулсетах объявлено и где это лежит.

    python tools/index_mod.py --mod "Пиратки/Dioxine_XPiratez/user/mods/Piratez"
    python tools/index_mod.py --mod <путь> --out .index/mod/piratez

Рулсеты — это YAML на десятки мегабайт: читать их целиком бессмысленно, а ctags
их не понимает. Этот скрипт даёт по моду то же, что symbols.tsv даёт по коду —
таблицу «идентификатор → файл:строка», по которой можно грепать.

Кладёт в <out>/:
    entries.tsv    раздел | id | файл | строка
    sprites.tsv    набор | одиночная | ширина | высота | кадров | первый файл
    resources.tsv  файл ресурса | байт | расширение | папка
    missing.tsv    на что рулсет ссылается, а файла нет
    INDEX.md       сводка для человека и агента
    meta.json      когда собрана, сколько чего

Разбор построчный и намеренно тупой: YAML-парсер на 6 МБ diалекта OXCE
падает или ест память, а нам нужны только заголовки записей.
"""
from __future__ import annotations

import argparse, json, os, re, sys, time
from collections import Counter, defaultdict
from pathlib import Path

# Верхний уровень: "items:", "armors:", "extraSprites:" — без отступа.
RE_SECTION = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(#.*)?$")
# Запись списка: "  - type: STR_X" (или id / name / delete).
RE_ENTRY = re.compile(r"^(\s*)-\s*(type|id|name|delete)\s*:\s*(.+?)\s*(?:#.*)?$")
# Поле внутри записи: "    width: 32"
RE_FIELD = re.compile(r"^\s+([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*?)\s*(?:#.*)?$")
# Кадр в files: "      0: Resources/Foo.png"
RE_FRAME = re.compile(r"^\s+(\d+)\s*:\s*(\S.*?)\s*(?:#.*)?$")

RES_SKIP_DIRS = {"Ruleset", ".git", "__pycache__"}

# Windows PowerShell 5.1 читает файл без BOM как cp1251: `type INDEX.md` выдаёт
# мусор вместо кириллицы. Всё, что здесь пишется, читают и человек, и агент,
# поэтому пишем со спецификацией, а читаем через utf-8-sig (грабли R-001).
ENC_W = "utf-8-sig"
ENC_R = "utf-8-sig"


def unquote(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        return s[1:-1]
    return s


def parse_ruleset(path: Path, rel: str):
    """Возвращает (entries, sprites, terrain_sets). Построчно, без YAML."""
    entries = []
    sprites = []
    terrain_sets = []   # (имя террейна, имя набора) - кто где используется
    section = None
    cur = None          # текущая запись extraSprites
    in_files = False
    terrain_name = None
    in_mds = False      # внутри mapDataSets текущего террейна
    mds_indent = None

    with path.open("r", encoding=ENC_R, errors="replace") as f:
        for n, line in enumerate(f, 1):
            line = line.rstrip("\n").rstrip("\r")
            if not line.strip() or line.lstrip().startswith("#"):
                continue

            m = RE_SECTION.match(line)
            if m:
                if cur:
                    sprites.append(cur); cur = None
                section = m.group(1)
                in_files = False
                in_mds = False
                terrain_name = None
                continue

            # Набор тайлов сам по себе не говорит, что это за место: A_PODS - это
            # база пришельцев и тюрьма, ACHURCH - готический собор. Знает об этом
            # только террейн, который их подключает.
            if section == "terrains":
                indent = len(line) - len(line.lstrip())
                if in_mds:
                    ms = line.strip()
                    if ms.startswith("- ") and indent > mds_indent:
                        terrain_sets.append((terrain_name, unquote(ms[2:])))
                        continue
                    in_mds = False
                if line.strip().startswith("mapDataSets:") and terrain_name:
                    in_mds = True
                    mds_indent = indent
                    continue

            m = RE_ENTRY.match(line)
            if m and section == "terrains" and m.group(2) == "name":
                terrain_name = unquote(m.group(3))

            if m and section:
                if cur:
                    sprites.append(cur); cur = None
                key, val = m.group(2), unquote(m.group(3))
                entries.append((section, val, rel, n, key))
                in_files = False
                if section == "extraSprites" and key in ("type", "delete"):
                    cur = {"type": val, "single": "", "w": "", "h": "",
                           "frames": 0, "first": "", "file": rel, "line": n,
                           "deleted": key == "delete"}
                continue

            if cur is not None:
                if in_files:
                    mf = RE_FRAME.match(line)
                    if mf:
                        cur["frames"] += 1
                        if not cur["first"]:
                            cur["first"] = unquote(mf.group(2))
                        continue
                    in_files = False
                mk = RE_FIELD.match(line)
                if mk:
                    k, v = mk.group(1), unquote(mk.group(2))
                    if k == "files":
                        in_files = True
                    elif k == "singleImage":
                        cur["single"] = v
                    elif k == "width":
                        cur["w"] = v
                    elif k == "height":
                        cur["h"] = v
    if cur:
        sprites.append(cur)
    return entries, sprites, terrain_sets


def scan_resources(mod: Path):
    rows = []
    for dirpath, dirnames, filenames in os.walk(mod):
        dirnames[:] = [d for d in dirnames if d not in RES_SKIP_DIRS]
        for fn in filenames:
            p = Path(dirpath) / fn
            rel = p.relative_to(mod).as_posix()
            try:
                size = p.stat().st_size
            except OSError:
                size = 0
            top = rel.split("/")[0] if "/" in rel else "."
            rows.append([rel, size, p.suffix.lower().lstrip("."), top])
    return rows


def write_tsv(path: Path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding=ENC_W, newline="\n") as f:
        f.write("\t".join(header) + "\n")
        for r in rows:
            f.write("\t".join(str(c).replace("\t", " ").replace("\n", " ") for c in r) + "\n")


def build(mod: Path, out: Path) -> int:
    t0 = time.time()
    if not mod.exists():
        sys.exit(f"нет такой папки: {mod}")

    ruls = sorted([p for p in mod.rglob("*.rul")] + [p for p in mod.glob("*.yml")])
    all_entries, all_sprites, all_ts = [], [], []
    for p in ruls:
        e, s, ts = parse_ruleset(p, p.relative_to(mod).as_posix())
        all_entries += e
        all_sprites += s
        all_ts += ts

    write_tsv(out / "entries.tsv", ["section", "id", "file", "line", "key"],
              sorted(all_entries, key=lambda r: (r[0], r[1])))

    write_tsv(out / "sprites.tsv",
              ["set", "singleImage", "width", "height", "frames", "firstFile", "file", "line"],
              [[s["type"], s["single"], s["w"], s["h"], s["frames"], s["first"], s["file"], s["line"]]
               for s in all_sprites if not s["deleted"]])

    # обратный индекс: набор -> террейны, которые его используют
    by_set = defaultdict(set)
    for terr, st in all_ts:
        if terr:
            by_set[st.upper()].add(terr)
    write_tsv(out / "set_terrains.tsv", ["set", "terrains", "count"],
              [[s, ", ".join(sorted(v)), len(v)] for s, v in sorted(by_set.items())])

    res = scan_resources(mod)
    write_tsv(out / "resources.tsv", ["file", "bytes", "ext", "top"], sorted(res))
    have = {r[0].lower() for r in res}

    # На что ссылаемся, но чего нет. Ссылки относительны корню мода.
    missing = []
    for s in all_sprites:
        if s["deleted"] or not s["first"]:
            continue
        if s["first"].lower() not in have:
            missing.append([s["type"], s["first"], s["file"], s["line"]])
    write_tsv(out / "missing.tsv", ["set", "referencedFile", "file", "line"], missing)

    by_section = Counter(e[0] for e in all_entries)
    by_top = Counter(r[3] for r in res)
    bytes_by_top = defaultdict(int)
    for r in res:
        bytes_by_top[r[3]] += r[1]
    by_ext = Counter(r[2] for r in res if r[2])

    md = [
        f"# Карта мода: {mod.name}",
        "",
        f"Собрана: {time.strftime('%Y-%m-%d %H:%M')} за {time.time()-t0:.1f} с",
        f"Рулсетов: {len(ruls)} · записей: {len(all_entries)} · "
        f"наборов спрайтов: {len([s for s in all_sprites if not s['deleted']])} · "
        f"файлов ресурсов: {len(res)} · наборов с известным местом: {len(by_set)}",
        "",
        "## Разделы рулсетов",
        "",
        "| Раздел | Записей |", "|---|---|",
        *[f"| {k} | {v} |" for k, v in by_section.most_common()],
        "",
        "## Ресурсы по папкам",
        "",
        "| Папка | Файлов | Размер, МБ |", "|---|---|---|",
        *[f"| {k} | {v} | {bytes_by_top[k]/1048576:.1f} |" for k, v in by_top.most_common()],
        "",
        "## Ресурсы по типам",
        "",
        "| Тип | Файлов |", "|---|---|",
        *[f"| {k} | {v} |" for k, v in by_ext.most_common(15)],
        "",
    ]
    if missing:
        md += [f"## Ссылки без файлов: {len(missing)}", "",
               "Рулсет ссылается на файл, которого в моде нет. Полный список — `missing.tsv`.", "",
               *[f"- `{m[0]}` -> `{m[1]}`  ({m[2]}:{m[3]})" for m in missing[:20]], ""]
    md += [
        "## Как пользоваться",
        "",
        "```",
        "# где объявлен объект",
        "grep -P '\\tSTR_PISTOL\\t' entries.tsv",
        "# все брони",
        "grep -P '^armors\\t' entries.tsv",
        "# откуда берётся набор спрайтов",
        "grep -P '^BIGOBS.PCK\\t' sprites.tsv",
        "```",
        "",
        "Это источник ФАКТОВ о том, где что объявлено. Смысл — в рулсете по указанной строке.",
    ]
    (out / "INDEX.md").write_text("\n".join(md) + "\n", encoding=ENC_W)

    (out / "meta.json").write_text(json.dumps({
        "mod": mod.as_posix(), "built_human": time.strftime("%Y-%m-%d %H:%M:%S"),
        "rulesets": len(ruls), "entries": len(all_entries),
        "sprite_sets": len([s for s in all_sprites if not s["deleted"]]),
        "resources": len(res), "missing": len(missing),
        "seconds": round(time.time() - t0, 2),
    }, ensure_ascii=False, indent=2), encoding=ENC_W)

    print(f"Карта мода {mod.name}: {len(all_entries)} записей, "
          f"{len(res)} файлов ресурсов, {len(missing)} битых ссылок, "
          f"{time.time()-t0:.1f} с -> {out}")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Карта мода OpenXcom/OXCE по рулсетам")
    ap.add_argument("--mod", required=True, help="папка мода (та, где metadata.yml)")
    ap.add_argument("--out", default="", help="куда класть (по умолчанию .index/mod/<имя>)")
    a = ap.parse_args()
    mod = Path(a.mod)
    out = Path(a.out) if a.out else Path(".index") / "mod" / mod.name
    return build(mod, out)


if __name__ == "__main__":
    sys.exit(main())
