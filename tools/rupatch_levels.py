# Переносит наши страницы достижений «ПО УРОВНЯМ» из прежней версии XPZ RU-patch в новую.
# Автор патча их не делает: 88 страниц (+ его собственный «Бомбист») вписаны нами прямо в
# Ruleset/EX_ufopedia.rul и Language/ru.yml, и каждая новая версия патча приходит без них.
#   py -3 tools/rupatch_levels.py <прежний патч> <новый патч>   (новый правится на месте)
# Авторское не трогается: страницы встают под его же статьи, отсутствующие статьи и строки
# добавляются блоками; на совпадении ключа скрипт останавливается. Кодировку файлов сохраняет
# как есть - их читает игра, спецификация им не нужна (R-001, исключение).
import re, sys
from pathlib import Path

OLD = Path(sys.argv[1])  # 12.3.1 with our block
NEW = Path(sys.argv[2])  # 12.3.2, edited in place

def rd(p):
    return p.read_bytes().decode("utf-8")

# --- ru.yml: our block right after the author's Bomber page 2
old = rd(OLD / "Language/ru.yml").split("\n")
new = rd(NEW / "Language/ru.yml").split("\n")
start = next(i for i, l in enumerate(old) if "авто-генерация по soldierBonuses" in l)
end = start
while end + 1 < len(old) and re.match(r'  STR_MEDAL_\w+_(NAME|UFOPEDIA)_[23]:', old[end + 1]):
    end += 1
block = old[start - 1:end + 1]  # blank line before the header comment
assert block[0].strip() == "", block[0]
keys_new = {l.split(":")[0].strip() for l in new if l.startswith("  STR_")}
dup = [l.split(":")[0].strip() for l in block if l.startswith("  STR_") and l.split(":")[0].strip() in keys_new]
assert not dup, dup
at = next(i for i, l in enumerate(new) if l.startswith("  STR_MEDAL_BOMBER_UFOPEDIA_2:")) + 1
new[at:at] = block
(NEW / "Language/ru.yml").write_bytes("\n".join(new).encode("utf-8"))
print("ru.yml: +%d lines, %d keys" % (len(block), sum(l.startswith("  STR_") for l in block)))

# --- EX_ufopedia.rul: pages under the author's existing ids, then our 13.1+ block
old = rd(OLD / "Ruleset/EX_ufopedia.rul").split("\n")
new = rd(NEW / "Ruleset/EX_ufopedia.rul").split("\n")

def entries(lines):
    """id -> (index of '- id:' line, index after the entry)"""
    out = {}
    idx = [i for i, l in enumerate(lines) if re.match(r"  - id: ", l)]
    for k, i in enumerate(idx):
        j = idx[k + 1] if k + 1 < len(idx) else len(lines)
        out[lines[i].split("#")[0].split(":", 1)[1].strip()] = (i, j)
    return out

eo, en = entries(old), entries(new)
added = 0
inserts = []  # (index in new, lines)
tail = None
for eid, (i, j) in eo.items():
    if not eid.startswith("STR_MEDAL_"):
        continue
    body = old[i:j]
    try:
        p = next(k for k, l in enumerate(body) if l.strip() == "pages:")
    except StopIteration:
        continue
    q = p + 1
    while q < len(body) and (body[q].startswith("    - ") or body[q].startswith("      ")):
        q += 1
    pages = body[p:q]
    if eid in en:
        ni, nj = en[eid]
        if any(l.strip() == "pages:" for l in new[ni:nj]):
            continue  # the author has pages here (Bomber)
        # same position as in the old entry: after the line that preceded 'pages:'
        anchor = body[p - 1]
        k = next(k for k in range(ni, nj) if new[k] == anchor)
        inserts.append((k + 1, pages))
        added += 1
    else:
        tail = tail or []
        tail.append(eid)

for k, pages in sorted(inserts, reverse=True):
    new[k:k] = pages

# the "13.1+" block: entries that the author file never had
hs = next(i for i, l in enumerate(old) if l.startswith("# 13.1+ ДОСТИЖЕНИЯ"))
he = hs + 1
while he < len(old) and (old[he].startswith("  - id: STR_MEDAL_") or old[he].startswith("    ")):
    he += 1
block = old[hs:he]
ids = [l.split("#")[0].split(":", 1)[1].strip() for l in block if l.startswith("  - id: ")]
assert set(ids) == set(tail or []), (set(ids) ^ set(tail or []))
en = entries(new)
assert not set(ids) & set(en)
# put it where it stood before: after the last STR_MEDAL_ entry of the author
last = max(j for eid, (i, j) in en.items() if eid.startswith("STR_MEDAL_"))
while last > 0 and new[last - 1].strip() == "":
    last -= 1
new[last:last] = [""] + block
(NEW / "Ruleset/EX_ufopedia.rul").write_bytes("\n".join(new).encode("utf-8"))
print("EX_ufopedia.rul: pages added to %d entries, %d new entries" % (added, len(ids)))
