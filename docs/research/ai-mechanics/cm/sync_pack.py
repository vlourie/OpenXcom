"""Pack the game data update for the work machine: send.txt (new + changed) without the HD art (user/mods/hd stays a stub,
only its metadata.yml), plus gone.txt (files to retire there) and the expected manifest of the synced folders.

  py -3.13 -I sync_pack.py <game base> <dir with send.txt gone.txt man_local.tsv> <out.zip>"""
import sys
import zipfile
from pathlib import Path

base, d, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])


def keep(rel):
    return not rel.startswith("user/mods/hd/") or rel == "user/mods/hd/metadata.yml"


send = [r for r in (d / "send.txt").read_text(encoding="utf-8").splitlines() if r and keep(r)]
gone = [r for r in (d / "gone.txt").read_text(encoding="utf-8").splitlines() if r and keep(r)]
expect = [l for l in (d / "man_local.tsv").read_text(encoding="utf-8").splitlines() if l and keep(l.split("\t")[0])]
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
    for rel in send:
        z.write(base / rel, "data/" + rel)
    z.writestr("gone.txt", "\n".join(gone) + "\n")
    z.writestr("expect.tsv", "\n".join(expect) + "\n")
print(f"send {len(send)} gone {len(gone)} expect {len(expect)} -> {out} {out.stat().st_size / 1e6:.1f} MB")
