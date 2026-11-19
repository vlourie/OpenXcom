"""MISSION-LEVEL TACTICS: the last hunk of patch.py on the tree it stopped at (patch.py stopped before it), then CRLF back on the four files."""
import pathlib
import sys

S = pathlib.Path(sys.argv[1])
B = S / "md" / "tree" / "src" / "Battlescape"
t = B / "TileEngine.cpp"
text = t.read_text(encoding="utf-8")
old = "\t\t\t\ttiles[i]->getMapData(currentpart)->isBaseModule())\n\t\t\t{\n"
if text.count(old) != 1:
    raise SystemExit(f"{text.count(old)} matches")
t.write_text(text.replace(old, old + "\t\t\t\tAiProbe::missionBlastModule(_save, tiles[i]->getPosition());\n"), encoding="utf-8", newline="")
for name in ("AiProbe.h", "AiProbe.cpp", "AIModule.cpp", "TileEngine.cpp"):
    p = B / name
    p.write_bytes(p.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    print("crlf", name)
