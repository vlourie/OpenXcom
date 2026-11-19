"""Stage 0B, part 2 (isolated tree only): OXCE_AI_AUTOSAVE=1 lets the harness write the player's turn autosave, the same
snapshot the player exe writes when its turn comes (before the panicking units act). usage: patch_al2.py <BattlescapeState.cpp>"""
import sys
from pathlib import Path

p = Path(sys.argv[1])
t = p.read_bytes().decode("utf-8").replace("\r\n", "\n")
old = """	// the AI test bench doesn't autosave: its generated battle has a UFO without a mission, which can't be saved
	if (_autosave > 0 && !_save->isPreview() && !AiProbe::harness())
"""
new = """	// the AI test bench doesn't autosave: its generated battle has a UFO without a mission, which can't be saved
	// (stage 0B: OXCE_AI_AUTOSAVE=1 - the same autosave as the player's game, the snapshot compared with it)
	if (_autosave > 0 && !_save->isPreview() && (!AiProbe::harness() || getenv("OXCE_AI_AUTOSAVE")))
"""
assert t.count(old) == 1
t = t.replace(old, new)
p.write_bytes(t.replace("\n", "\r\n").encode("utf-8"))
print("patched", p)
