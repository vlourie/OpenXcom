#!/usr/bin/env python3
"""
Учёт граблей проекта — docs/RAKES.md.

    python tools/rake.py list                       активные грабли
    python tools/rake.py match src/Foo/Bar.cpp      грабли, относящиеся к файлу
    python tools/rake.py hit R-007                  наступил снова: +1 к счётчику
    python tools/rake.py disarm R-007 tests/t.py    обезврежены тестом
    python tools/rake.py add --title "..." --files "src/*.cpp" \
        --symptom "..." --cause "..." --rule "..."

Формат записи описан в шапке docs/RAKES.md и парсится отсюда. Не меняй поля.
"""
from __future__ import annotations

import argparse, datetime, fnmatch, re, sys
from pathlib import Path

RAKES = Path("docs/RAKES.md")
HEAD_RE = re.compile(r"^## (R-\d{3})\s+(.*)$")
FIELDS = ("Статус", "Файлы", "Симптом", "Причина", "Правило", "Защита", "Наступал")


def load(path: Path = RAKES):
    if not path.exists():
        sys.exit(f"нет файла {path} — запусти из корня проекта")
    text = path.read_text(encoding="utf-8")
    marker = "<!-- ГРАБЛИ НИЖЕ"
    idx = text.find(marker)
    head = text[: text.find("\n", idx) + 1] if idx != -1 else text
    body = text[len(head):] if idx != -1 else ""
    return text, head, body


def parse(body: str):
    items, cur = [], None
    for line in body.splitlines():
        m = HEAD_RE.match(line)
        if m:
            cur = {"id": m.group(1), "title": m.group(2).strip(), "raw": [line]}
            items.append(cur)
            continue
        if cur is None:
            continue
        cur["raw"].append(line)
        for f in FIELDS:
            if line.startswith(f + ":"):
                cur[f] = line.split(":", 1)[1].strip()
    for it in items:
        m = re.match(r"(\d+)", it.get("Наступал", "0"))
        it["count"] = int(m.group(1)) if m else 0
        it["active"] = not it.get("Статус", "активны").startswith("обезвреж")
        it["globs"] = [g.strip() for g in it.get("Файлы", "").split(",") if g.strip()]
    return items


def norm(p: str) -> str:
    return p.replace("\\", "/").lstrip("./")


def fmt(it, full=True):
    mark = "!!" if it["count"] >= 2 and it["active"] else ("--" if not it["active"] else "  ")
    out = [f"{mark} {it['id']}  {it['title']}   (наступал: {it['count']})"]
    if full:
        for f in ("Правило", "Причина", "Защита"):
            if it.get(f):
                out.append(f"     {f}: {it[f]}")
    return "\n".join(out)


def cmd_list(a):
    items = parse(load()[2])
    act = [i for i in items if i["active"]]
    if not act:
        print("Граблей нет. Это либо хорошо, либо их просто не записывали.")
        return 0
    print(f"Активных граблей: {len(act)}")
    for it in sorted(act, key=lambda x: -x["count"]):
        print(fmt(it, full=not a.short))
    unarmed = [i for i in act if i["count"] >= 2 and (not i.get("Защита") or i["Защита"].lower() in ("нет", "-"))]
    if unarmed:
        print("\nНАСТУПАЛИ ДВАЖДЫ, ЗАЩИТЫ НЕТ — нужен тест или хук:")
        for it in unarmed:
            print(f"  {it['id']}  {it['title']}")
    return 0


def cmd_match(a):
    target = norm(a.path)
    items = [i for i in parse(load()[2]) if i["active"]]
    hits = [i for i in items
            if any(fnmatch.fnmatch(target, norm(g)) or norm(g) in target for g in i["globs"])]
    if not hits:
        return 0
    print(f"ГРАБЛИ по файлу {a.path}:")
    for it in hits:
        print(fmt(it))
    return 0


def cmd_hit(a):
    text, head, body = load()
    items = parse(body)
    it = next((i for i in items if i["id"] == a.id), None)
    if not it:
        sys.exit(f"нет граблей {a.id}")
    new = it["count"] + 1
    today = datetime.date.today().isoformat()
    old_line = f"Наступал: {it['Наступал']}"
    new_line = f"Наступал: {new}   Последний: {today}"
    block = "\n".join(it["raw"])
    text = text.replace(block, block.replace(old_line, new_line), 1)
    RAKES.write_text(text, encoding="utf-8")
    print(f"{a.id}: наступал {new} раз(а)")
    if new >= 2 and (not it.get("Защита") or it["Защита"].lower() in ("нет", "-")):
        print("\nВТОРОЙ РАЗ. Текстовое правило не сработало.")
        print("Не закрывай задачу, пока нет теста или хука, который ловит это автоматически.")
        print(f"Потом: python tools/rake.py disarm {a.id} <путь-к-тесту>")
    return 0


def cmd_disarm(a):
    text, head, body = load()
    it = next((i for i in parse(body) if i["id"] == a.id), None)
    if not it:
        sys.exit(f"нет граблей {a.id}")
    block = "\n".join(it["raw"])
    upd = block.replace(f"Статус:   {it.get('Статус','активны')}", "Статус:   обезврежены")
    upd = re.sub(r"Защита:.*", f"Защита:   {a.test}", upd, count=1)
    RAKES.write_text(text.replace(block, upd, 1), encoding="utf-8")
    print(f"{a.id}: обезврежены, защита {a.test}")
    return 0


def cmd_add(a):
    text, head, body = load()
    items = parse(body)
    nid = f"R-{max([int(i['id'][2:]) for i in items], default=0) + 1:03d}"
    entry = (
        f"\n## {nid}  {a.title}\n"
        f"Статус:   активны\n"
        f"Файлы:    {a.files}\n"
        f"Симптом:  {a.symptom}\n"
        f"Причина:  {a.cause}\n"
        f"Правило:  {a.rule}\n"
        f"Защита:   {a.guard}\n"
        f"Наступал: 1   Последний: {datetime.date.today().isoformat()}\n"
    )
    RAKES.write_text(text.rstrip("\n") + "\n" + entry, encoding="utf-8")
    print(f"Записаны грабли {nid}: {a.title}")
    return 0


def main():
    p = argparse.ArgumentParser(description="Учёт граблей проекта")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("list"); s.add_argument("--short", action="store_true"); s.set_defaults(fn=cmd_list)
    s = sub.add_parser("match"); s.add_argument("path"); s.set_defaults(fn=cmd_match)
    s = sub.add_parser("hit"); s.add_argument("id"); s.set_defaults(fn=cmd_hit)
    s = sub.add_parser("disarm"); s.add_argument("id"); s.add_argument("test"); s.set_defaults(fn=cmd_disarm)
    s = sub.add_parser("add")
    for f in ("title", "files", "symptom", "cause", "rule"):
        s.add_argument("--" + f, required=True)
    s.add_argument("--guard", default="нет")
    s.set_defaults(fn=cmd_add)

    a = p.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
