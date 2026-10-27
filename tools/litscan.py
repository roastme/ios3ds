#!/usr/bin/env python3
"""Find 32-bit literals in a VA range inside kernelcache sections, grouped by owner.
Usage: litscan.py KERNEL KEXTS.txt LO HI"""
import re, struct, sys, collections
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from macho import MachO
m = MachO(sys.argv[1])
kexts = [(int(a[1], 16), int(a[2], 16), a[3]) for a in
         (re.match(r"([0-9a-f]+)-([0-9a-f]+) .* (\S+)$", l.strip()) for l in open(sys.argv[2])) if a]
lo, hi = int(sys.argv[3], 0), int(sys.argv[4], 0)
out = collections.defaultdict(collections.Counter)
for name, vmaddr, vmsize, fileoff, filesize, sects in m.segments:
    blob = m.data[fileoff:fileoff + filesize]
    for off in range(0, len(blob) - 3, 4):
        v = struct.unpack_from("<I", blob, off)[0]
        if lo <= v < hi:
            va = vmaddr + off
            own = next((n for a, b, n in kexts if a <= va < b), "kernel:" + name)
            out[own][v] += 1
for own in sorted(out):
    print(own)
    print("   " + " ".join("%08x%s" % (v, "x%d" % n if n > 1 else "") for v, n in sorted(out[own].items())))
