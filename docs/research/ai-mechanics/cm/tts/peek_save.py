"""TACTICAL TURN SOLVER: what a battle save holds at the top, read only. arg: save"""
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
L = open(sys.argv[1], encoding="utf-8", errors="replace").read().split("\n")
print("lines", len(L))
for i, s in enumerate(L):
    if re.match(r"^(---|\w+:)", s) or re.match(r"^  \w+:", s):
        if len(s) < 110:
            print(i, s)
        else:
            print(i, s[:60], "... len", len(s))
