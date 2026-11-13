"""MISSION-LEVEL TACTICS: the flag OXCE_AI_MISSION is the stand's own variable (ai_probe.py sets it to the mission's name), so the probe's flag
is OXCE_AI_MDIR, in the tree and in the block (byte-level: the tree's files keep CRLF)."""
import pathlib
import sys

S = pathlib.Path(sys.argv[1])
for p in (S / "md" / "tree" / "src" / "Battlescape" / "AiProbe.cpp", S / "md" / "tree" / "src" / "Battlescape" / "AiProbe.h", S / "md" / "mission_block.cpp"):
    b = p.read_bytes()
    print(p.name, b.count(b"OXCE_AI_MISSION"))
    p.write_bytes(b.replace(b"OXCE_AI_MISSION", b"OXCE_AI_MDIR"))
p = S / "cm" / "st" / "run_cm.py"
b = p.read_bytes()
print(p.name, b.count(b"OXCE_AI_MISSION"))
p.write_bytes(b.replace(b"OXCE_AI_MISSION", b"OXCE_AI_MDIR"))
p = S / "md" / "up_md.sh"
b = p.read_bytes()
print(p.name, b.count(b"OXCE_AI_MISSION"))
p.write_bytes(b.replace(b"OXCE_AI_MISSION", b"OXCE_AI_MDIR"))
