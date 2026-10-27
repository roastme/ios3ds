#!/usr/bin/env python3
"""Map kernel addresses to symbol+offset: addr.py KERNEL ADDR [ADDR...]"""
import bisect, sys
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from macho import MachO
m = MachO(sys.argv[1])
items = sorted((v & ~1, n) for n, v in m.symbols.items())
keys = [v for v, _ in items]
for a in sys.argv[2:]:
    x = int(a, 16)
    i = bisect.bisect_right(keys, x) - 1
    print("%08x %s+%#x" % (x, items[i][1], x - items[i][0]) if i >= 0 else "%08x ?" % x)
