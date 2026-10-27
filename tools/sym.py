#!/usr/bin/env python3
"""sym.py SYMFILE ADDR... : print function+offset for each address (nm -n output)."""
import bisect, sys
syms = []
for l in open(sys.argv[1]):
    p = l.split()
    if len(p) == 3 and p[1] in "tTdDbB":
        syms.append((int(p[0], 16), p[2]))
addrs = [s[0] for s in syms]
for a in sys.argv[2:]:
    v = int(a, 16); i = bisect.bisect_right(addrs, v) - 1
    print("%08x %s+%#x" % (v, syms[i][1], v - syms[i][0]))
