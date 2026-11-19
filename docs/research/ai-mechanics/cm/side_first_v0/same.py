"""SIDE-FIRST COMBAT: do two battles decide the same? The engine's record lines ([AIDECIDE], [AIEXEC], [AICASUALTY], [AISTATE]) in order, time stamps off, first difference shown. args: zip1 label1 zip2 label2"""
import gzip
import io
import re
import sys
import zipfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
TAGS = ("[AIDECIDE]", "[AIEXEC]", "[AICASUALTY]", "[AISTATE]")


def load(zip_path, label):
    with zipfile.ZipFile(zip_path) as z:
        raw = gzip.open(io.BytesIO(z.read(f"out/{label}/openxcom.log.gz")), "rt", encoding="utf-8", errors="replace").read().splitlines()
    out = []
    for s in raw:
        s = s.split("\t")[-1]
        if s.startswith(TAGS):
            out.append(re.sub(r'"(us|ms|t_us)":\d+,?', "", s))
    return out, sum(1 for s in raw if "[AISCD]" in s), sum(1 for s in raw if "rng_touched" in s)


a, sa, ra = load(sys.argv[1], sys.argv[2])
b, sb, rb = load(sys.argv[3], sys.argv[4])
print(f"{sys.argv[2]}: {len(a)} lines, SCD {sa}, rng {ra}; {sys.argv[4]}: {len(b)} lines, SCD {sb}, rng {rb}")
for i, (x, y) in enumerate(zip(a, b)):
    if x != y:
        print("first difference at line", i)
        print(" A", x[:400])
        print(" B", y[:400])
        break
else:
    print("identical" if len(a) == len(b) else f"same prefix, lengths differ: {len(a)} {len(b)}")
