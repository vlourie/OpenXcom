"""Apply the game data update on the work machine (C:/OXCE_AIWorker/game): every file it overwrites and every retired file
is first moved into a backup folder with the same relative path; then the new files are written; then the synced folders
are checked against the expected manifest (expect.tsv: the local files, the HD art excepted).

  python -I sync_apply.py <update.zip> <game base> <backup dir>"""
import hashlib
import shutil
import sys
import zipfile
from pathlib import Path

zp, base, bak = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def backup(rel):
    p = base / rel
    if p.is_file():
        q = bak / rel
        q.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(p), str(q))
        return 1
    return 0


with zipfile.ZipFile(zp) as z:
    gone = [r for r in z.read("gone.txt").decode("utf-8").splitlines() if r]
    expect = [l.split("\t") for l in z.read("expect.tsv").decode("utf-8").splitlines() if l]
    data = [n for n in z.namelist() if n.startswith("data/") and not n.endswith("/")]
    moved = sum(backup(r) for r in gone)
    over = 0
    for n in data:
        rel = n[5:]
        over += backup(rel)
        p = base / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        with z.open(n) as src, open(p, "wb") as dst:
            shutil.copyfileobj(src, dst)
print(f"retired {moved}, overwritten (backed up) {over}, written {len(data)}")
bad = [rel for rel, size, h in expect if not (base / rel).is_file() or sha(base / rel) != h]
roots = {"/".join(rel.split("/")[:3]) if rel.startswith("user/") else rel.split("/")[0] for rel, _, _ in expect}
want = {rel for rel, _, _ in expect}
extra = []
for r in roots:
    for p in (base / r).rglob("*"):
        rel = p.relative_to(base).as_posix()
        if p.is_file() and rel not in want and not rel.startswith("user/mods/hd/"):
            extra.append(rel)
print(f"check: expected {len(expect)}, mismatched or missing {len(bad)}, extra {len(extra)}")
for r in (bad + extra)[:20]:
    print("  ", r)
