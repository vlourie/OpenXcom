"""MISSION-LEVEL TACTICS: AiProbe.h needs Node declared (a byte-level edit: the tree's files keep CRLF)."""
import pathlib
import sys

p = pathlib.Path(sys.argv[1]) / "md" / "tree" / "src" / "Battlescape" / "AiProbe.h"
b = p.read_bytes()
old = b"class Position;\r\n"
if b.count(old) != 1:
    raise SystemExit("no match")
p.write_bytes(b.replace(old, old + b"class Node;\r\n"))
print("ok")
