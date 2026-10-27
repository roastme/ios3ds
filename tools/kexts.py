#!/usr/bin/env python3
"""List prelinked kexts by scanning __PRELINK for kmod_info structs.

kmod_info: next, info_version(=1), id, name[64], version[64], reference_count,
reference_list, address(0x94), size(0x98), hdr_size, start(0xa0), stop(0xa4).
Usage: kexts.py KERNEL [ADDR...]
"""
import re, struct, sys
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from macho import MachO
m = MachO(sys.argv[1])
seg = [s for s in m.segments if s[0] == "__PRELINK"][0]
_, va0, vsz, fo, fsz, _ = seg
data = m.data[fo:fo + fsz]
kexts = []
for i in range(0, len(data) - 0xa8, 4):
    if struct.unpack_from("<I", data, i + 4)[0] != 1:
        continue
    name = data[i + 0xC:i + 0x4C].split(b"\0")[0]
    if not re.fullmatch(rb"[A-Za-z0-9_.\-]{6,63}", name) or b"." not in name:
        continue
    addr, size = struct.unpack_from("<II", data, i + 0x94)
    start, stop = struct.unpack_from("<II", data, i + 0xA0)
    if va0 <= addr < va0 + vsz and 0 < size < 0x400000 and addr <= start < addr + size:
        kexts.append((addr, size, start, va0 + i, name.decode()))
kexts.sort()
addrs = [int(a, 16) for a in sys.argv[2:]]
if not addrs:
    for addr, size, start, kmod, name in kexts:
        print("%08x-%08x  start %08x  kmod %08x  %s" % (addr, addr + size, start, kmod, name))
for a in addrs:
    for addr, size, start, kmod, name in kexts:
        if addr <= a < addr + size:
            print("%08x in %s +%#x" % (a, name, a - addr))
            break
    else:
        print("%08x: no kext" % a)
