"""Compare two hman manifests: per top folder (common, standard, user/mods/<mod>) - new, changed, gone, same, bytes to send.
Writes the lists send.txt (new + changed, local relpaths) and gone.txt (on the target, not locally) next to the first file.

  py -3.13 -I hdiff.py <local.tsv> <target.tsv>"""
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")


def load(p):
    d = {}
    for line in Path(p).read_text(encoding="utf-8").splitlines():
        if line:
            rel, size, h = line.split("\t")
            d[rel] = (int(size), h)
    return d


def top(rel):
    parts = rel.split("/")
    return "/".join(parts[:3]) if parts[0] == "user" else parts[0]


loc, tgt = load(sys.argv[1]), load(sys.argv[2])
roots = {top(r) for r in loc}
st = defaultdict(lambda: defaultdict(int))
send, gone = [], []
for rel, (size, h) in loc.items():
    t = top(rel)
    if rel not in tgt:
        st[t]["new"] += 1
        st[t]["bytes"] += size
        send.append(rel)
    elif tgt[rel][1] != h:
        st[t]["changed"] += 1
        st[t]["bytes"] += size
        send.append(rel)
    else:
        st[t]["same"] += 1
for rel in tgt:
    t = top(rel)
    if t in roots and rel not in loc:
        st[t]["gone"] += 1
        gone.append(rel)
    elif t not in roots:
        st[t]["not_synced"] += 1
for t in sorted(st):
    v = st[t]
    print(f"{t:40s} new {v['new']:6d} changed {v['changed']:5d} gone {v['gone']:5d} same {v['same']:6d} "
          f"send {v['bytes'] / 1e6:8.1f} MB" + (f" (target only: {v['not_synced']} files)" if v["not_synced"] else ""))
print(f"total send {len(send)} files {sum(loc[r][0] for r in send) / 1e6:.1f} MB, gone {len(gone)}")
out = Path(sys.argv[1]).parent
(out / "send.txt").write_text("\n".join(sorted(send)) + "\n", encoding="utf-8")
(out / "gone.txt").write_text("\n".join(sorted(gone)) + "\n", encoding="utf-8")
