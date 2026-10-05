"""Split `git diff -U0 <file>` into hunks: list them, or stage a chosen set.

py -3.13 tools/git_hunks.py list <file>          - numbered hunks with their lines
py -3.13 tools/git_hunks.py stage <file> 1,3,5   - put those hunks into the index version of the file
Hunks are numbered against the diff of the WORKING TREE vs the INDEX, so list again after each stage.

Staging builds the new index blob itself (git apply --unidiff-zero puts a pure insertion at the
new-side line number, i.e. in the wrong place once earlier hunks are left out - rake R-094).
Then look at `git diff --cached -U2` and compile what the index holds, not the working tree.
"""
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
mode, path = sys.argv[1], sys.argv[2]
diff = subprocess.run(["git", "diff", "-U0", "--no-color", "--", path], capture_output=True, check=True).stdout.decode("utf-8")
hunks, cur = [], None
for l in diff.splitlines(keepends=True):
    if l.startswith("@@"):
        m = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", l)
        cur = {"head": l, "a": int(m.group(1)), "n": int(m.group(2) if m.group(2) is not None else 1), "lines": []}
        hunks.append(cur)
    elif cur is not None and l[:1] in "+-" and not l.startswith(("+++", "---")):
        cur["lines"].append(l)
    elif cur is not None and l.startswith("\\"):
        cur["lines"].append(l)
if mode == "list":
    for i, h in enumerate(hunks, 1):
        print("=== %d %s" % (i, h["head"].rstrip()))
        for l in h["lines"]:
            print("   " + l.rstrip("\r\n")[:150])
    sys.exit(0)
pick = {int(x) for x in sys.argv[3].split(",") if x}
old = subprocess.run(["git", "show", ":" + path], capture_output=True, check=True).stdout.decode("utf-8")
src = old.splitlines(keepends=True)
out, pos = [], 0   # pos: 0-based index of the next unconsumed old line
for i, h in enumerate(hunks, 1):
    if i not in pick:
        continue
    minus = [l[1:] for l in h["lines"] if l.startswith("-")]
    plus = [l[1:] for l in h["lines"] if l.startswith("+")]
    start = h["a"] if h["n"] == 0 else h["a"] - 1   # "-a,0" inserts after old line a
    if start < pos:
        sys.exit("hunk %d overlaps" % i)
    out += src[pos:start]
    got = src[start:start + h["n"]]
    if [g.rstrip("\r\n") for g in got] != [m.rstrip("\r\n") for m in minus]:
        sys.exit("hunk %d: old lines do not match" % i)
    out += plus
    pos = start + h["n"]
out += src[pos:]
data = "".join(out).encode("utf-8")
blob = subprocess.run(["git", "hash-object", "-w", "--stdin"], input=data, capture_output=True, check=True).stdout.decode().strip()
modebits = subprocess.run(["git", "ls-files", "-s", "--", path], capture_output=True, check=True).stdout.decode().split()[0]
subprocess.run(["git", "update-index", "--cacheinfo", "%s,%s,%s" % (modebits, blob, path)], check=True)
print("staged %d hunk(s) of %s" % (len(pick), path))
