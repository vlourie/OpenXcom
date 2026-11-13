"""Copy a diff with CRLF line ends (the tree from git archive is CRLF, the archived diffs are LF).

  py -3.13 -I crlf.py <in> <out>"""
import sys

data = open(sys.argv[1], "rb").read().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
open(sys.argv[2], "wb").write(data)
