"""OPERATIONAL INTELLIGENCE: from the M3 save (ci7, turn 3): each player's unit: armour name, current armour, facing, inventory; a sample of AI inventories; how many grenades the AI side holds. Read only."""
import re
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")
p = sys.argv[1]
text = open(p, encoding="utf-8", errors="replace").read()
print("size", len(text))
i = text.find("units:")
print([m.start() for m in re.finditer(r"^\s*units:", text, re.M)][:6], [m.start() for m in re.finditer(r"^\s*items:", text, re.M)][:6])
m = re.search(r"\n( *)units:\n", text)
ind = m.group(1)
start = m.end()
blocks = re.split(r"\n" + ind + r"  - id: ", text[start:start + 4000000])
print("unit blocks", len(blocks))
first = blocks[0][:1500]
print(first[:1800])
print("---- keys of a player's unit")
for b in blocks[:60]:
    head = b.split("\n")[0]
    if head.strip().isdigit() and int(head) < 1000:
        print(b[:1500])
        break
