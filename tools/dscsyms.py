#!/usr/bin/env python3
"""Resolve addresses to symbols using an iOS 4 dyld_shared_cache's per-image symbol tables.
usage: dscsyms.py CACHE IMAGE_SUBSTR ADDR..."""
import struct, sys, bisect
cache, sub, addrs = sys.argv[1], sys.argv[2], [int(a, 16) for a in sys.argv[3:]]
d = open(cache, 'rb').read()
mo, mc, io, ic = struct.unpack_from('<IIII', d, 16)
maps = [struct.unpack_from('<QQQII', d, mo + 32 * i) for i in range(mc)]
def va2off(va):
    for a, sz, fo, _, _ in maps:
        if a <= va < a + sz: return fo + va - a
    raise ValueError(hex(va))
img = None
for i in range(ic):
    a, _, _, po, _ = struct.unpack_from('<QQQII', d, io + 32 * i)
    p = d[po:d.index(b'\0', po)].decode()
    if sub in p: img = (a, p)
o = va2off(img[0])
ncmds = struct.unpack_from('<I', d, o + 16)[0]
p = o + 28
for _ in range(ncmds):
    c, cs = struct.unpack_from('<II', d, p)
    if c == 2:
        symoff, nsyms, stroff, strsize = struct.unpack_from('<IIII', d, p + 8)
    p += cs
S = []
for i in range(nsyms):
    strx, typ, sect, desc, val = struct.unpack_from('<IBBHI', d, symoff + 12 * i)
    if typ & 0xe0 or not (typ & 0xe) or val == 0: continue
    n = d[stroff + strx:d.index(b'\0', stroff + strx)].decode(errors='replace')
    S.append((val & ~1, n))
S.sort(); k = [s[0] for s in S]
print(img[1], len(S), 'symbols')
for a in addrs:
    j = bisect.bisect_right(k, a) - 1
    print('%08x %s+%#x' % (a, S[j][1], a - S[j][0]) if j >= 0 else hex(a))
