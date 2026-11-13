"""CONTACT_COORDINATION_V0: a run cut at the turn limit against a longer one: after the common part, what kinds of lines does the short run have left, and do they all exist in the long one (read only).
Usage: cc_tail.py <out dir short> <out dir long>"""
import gzip
import re
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
TAGS = ("[AIDECIDE]", "[AIEXEC]", "[AISTATE]", "[AICASUALTY]", "[AIREC]", "[AIPANIC]", "[AIAFTER]", "[AIPOSTWALK]", "[AIEVENT]")
timing = re.compile(r" (?:\w*us|\w*ms|\w*_ns|t|ms)=[-0-9.]+")
cfg = re.compile(r'"cfg":"[0-9a-f]+",')


def read(d):
    with gzip.open(Path(d) / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        return [cfg.sub("", timing.sub("", s)) for s in (ln.rstrip("\n").split("\t")[-1] for ln in f) if s.startswith(TAGS)]


a, b = read(sys.argv[1]), read(sys.argv[2])
i = 0
while i < min(len(a), len(b)) and a[i] == b[i]:
    i += 1
print(Path(sys.argv[1]).name, len(a), Path(sys.argv[2]).name, len(b), "common", i)
left = a[i:]
print(" kinds left over in the short run", Counter(s.split(" ")[0] for s in left).most_common())
dec = [s for s in a if s.startswith("[AIDECIDE]")]
print(" decisions in the short run", len(dec), "inside the common part", sum(1 for s in a[:i] if s.startswith("[AIDECIDE]")))
rest = set(b[i:])
print(" left-over lines also found later in the long run", sum(s in rest for s in left), "of", len(left))
