"""AI FORGE WP2: the value B will be checked against, by the runner's own function, and the engine's word at that point in A1. Reads logs only."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import AIForgeCounterfactualRunner as rr

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
print("expected_chain", rr.expected_chain())
print(rr.Run("A1").branch)
