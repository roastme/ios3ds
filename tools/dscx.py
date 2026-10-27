#!/usr/bin/env python3
"""Extract one dylib from an iOS 4 dyld_shared_cache (v1) into a standalone ARM Mach-O.
usage: dscx.py CACHE list [substr]
       dscx.py CACHE extract IMAGE_PATH_SUBSTR OUT
Segments are laid out file-contiguously; LC_SEGMENT file offsets are rewritten. Pointers are not unslid
(the cache is built at its own addresses, so addresses in the output equal the cache VM addresses)."""
import struct, sys

def main():
    cache, cmd = sys.argv[1], sys.argv[2]
    d = open(cache, 'rb').read()
    assert d[:8] == b'dyld_v1 ', d[:16]
    map_off, map_cnt, img_off, img_cnt = struct.unpack_from('<IIII', d, 16)
    maps = [struct.unpack_from('<QQQII', d, map_off + 32 * i) for i in range(map_cnt)]
    imgs = []
    for i in range(img_cnt):
        addr, mt, ino, po, pad = struct.unpack_from('<QQQII', d, img_off + 32 * i)
        end = d.index(b'\0', po)
        imgs.append((addr, d[po:end].decode()))

    def va2off(va):
        for a, sz, fo, _, _ in maps:
            if a <= va < a + sz:
                return fo + va - a
        raise ValueError('va %x not mapped' % va)

    if cmd == 'list':
        sub = sys.argv[3] if len(sys.argv) > 3 else ''
        for a, p in imgs:
            if sub in p:
                print('%08x %s' % (a, p))
        return
    sub, out = sys.argv[3], sys.argv[4]
    sel = [i for i in imgs if sub in i[1]]
    assert len(sel) == 1, sel
    addr, path = sel[0]
    o = va2off(addr)
    magic, cput, cpus, ft, ncmds, sz, flags = struct.unpack_from('<IIIIIII', d, o)
    assert magic == 0xfeedface
    lcs = []
    p = o + 28
    for _ in range(ncmds):
        cmdid, cs = struct.unpack_from('<II', d, p)
        lcs.append((cmdid, p, cs))
        p += cs
    segs = []
    for cmdid, p, cs in lcs:
        if cmdid == 1:
            name = d[p + 8:p + 24].rstrip(b'\0').decode()
            vmaddr, vmsize, foff, fsize, mp, ip, nsects, fl = struct.unpack_from('<IIIIIIII', d, p + 24)
            segs.append((p, name, vmaddr, vmsize, fsize))
    hdr_size = 28 + sum(cs for _, _, cs in lcs)
    outb = bytearray(d[o:o + hdr_size])
    outb += b'\0' * (-len(outb) % 0x1000)
    for p, name, vmaddr, vmsize, fsize in segs:
        pos = len(outb)
        if name == '__TEXT':
            # header is part of __TEXT: copy TEXT whole at offset 0
            outb = bytearray(d[va2off(vmaddr):va2off(vmaddr) + fsize])
            newoff = 0
        else:
            newoff = len(outb)
            outb += d[va2off(vmaddr):va2off(vmaddr) + fsize] if fsize else b''
        outb += b'\0' * (-len(outb) % 0x1000)
        struct.pack_into('<I', outb, p - o + 32 + 0, 0) if False else None
        # patch fileoff in the (copied) load command
        base = p - o
        struct.pack_into('<I', outb, base + 32, newoff)
        sec_n = struct.unpack_from('<I', outb, base + 48)[0]
        for k in range(sec_n):
            sp = base + 56 + 68 * k
            soff = struct.unpack_from('<I', outb, sp + 40)[0]
            ssz = struct.unpack_from('<I', outb, sp + 36)[0]
            saddr = struct.unpack_from('<I', outb, sp + 32)[0]
            if soff:
                struct.pack_into('<I', outb, sp + 40, newoff + (saddr - vmaddr))
    open(out, 'wb').write(outb)
    print('wrote', out, len(outb), path)

main()
