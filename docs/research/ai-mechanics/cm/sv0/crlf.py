"""Give the listed files CRLF line ends back (patch.py wrote them with LF)."""
import pathlib
import sys

for name in sys.argv[1:]:
    p = pathlib.Path(name)
    b = p.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    p.write_bytes(b)
    print("crlf", p.name)
