#!/usr/bin/env python3
"""Minimal 32-bit little-endian Mach-O reader for the iPhone OS 1.x kernelcache.

As a script: macho.py FILE  -> prints segments, sections and symbol counts.
As a module: MachO(path) gives segments, sections, symbols, va<->offset.
"""
import struct
import sys

LC_SEGMENT = 0x1
LC_SYMTAB = 0x2
LC_UNIXTHREAD = 0x5


class MachO:
    def __init__(self, path_or_bytes, base_off=0):
        data = path_or_bytes if isinstance(path_or_bytes, (bytes, bytearray)) else open(path_or_bytes, "rb").read()
        self.data = data
        self.base = base_off
        magic, cpu, sub, ftype, ncmds, sizecmds, flags = struct.unpack_from("<7I", data, base_off)
        if magic != 0xFEEDFACE:
            raise ValueError("bad magic %#x" % magic)
        self.cpu, self.subtype, self.filetype = cpu, sub, ftype
        self.segments = []   # (name, vmaddr, vmsize, fileoff, filesize, sections)
        self.symbols = {}    # name -> value
        self.thumb = set()   # names with N_ARM_THUMB_DEF
        self.entry = None
        off = base_off + 28
        for _ in range(ncmds):
            cmd, size = struct.unpack_from("<II", data, off)
            if cmd == LC_SEGMENT:
                name = data[off + 8:off + 24].split(b"\0")[0].decode()
                vmaddr, vmsize, fileoff, filesize, maxp, initp, nsects, fl = struct.unpack_from("<8I", data, off + 24)
                sects = []
                so = off + 56
                for _ in range(nsects):
                    sname = data[so:so + 16].split(b"\0")[0].decode()
                    segn = data[so + 16:so + 32].split(b"\0")[0].decode()
                    addr, ssize, soff = struct.unpack_from("<3I", data, so + 32)
                    sects.append((segn, sname, addr, ssize, soff))
                    so += 68
                self.segments.append((name, vmaddr, vmsize, fileoff, filesize, sects))
            elif cmd == LC_SYMTAB:
                symoff, nsyms, stroff, strsize = struct.unpack_from("<4I", data, off + 8)
                for i in range(nsyms):
                    strx, ntype, nsect, ndesc, value = struct.unpack_from("<IBBhI", data, base_off + symoff + 12 * i)
                    s = data[base_off + stroff + strx:].split(b"\0", 1)[0].decode(errors="replace")
                    if s and (ntype & 0xE) != 0:
                        self.symbols[s] = value
                        if ndesc & 0x8:
                            self.thumb.add(s)
            elif cmd == LC_UNIXTHREAD:
                # ARM thread state: flavor, count, r0..r15, cpsr
                self.entry = struct.unpack_from("<I", data, off + 16 + 15 * 4)[0]
            off += size

    def va2off(self, va):
        for name, vmaddr, vmsize, fileoff, filesize, _ in self.segments:
            if vmaddr <= va < vmaddr + filesize:
                return self.base + fileoff + (va - vmaddr)
        return None

    def off2va(self, off):
        off -= self.base
        for name, vmaddr, vmsize, fileoff, filesize, _ in self.segments:
            if fileoff <= off < fileoff + filesize and filesize:
                return vmaddr + off - fileoff
        return None

    def read(self, va, n):
        o = self.va2off(va)
        return self.data[o:o + n]

    def u32(self, va):
        return struct.unpack("<I", self.read(va, 4))[0]


def main():
    m = MachO(sys.argv[1])
    print("cpu %d sub %d type %d entry %s" % (m.cpu, m.subtype, m.filetype, hex(m.entry) if m.entry else None))
    for name, vmaddr, vmsize, fileoff, filesize, sects in m.segments:
        print("%-16s va %08x-%08x file %08x+%08x" % (name, vmaddr, vmaddr + vmsize, fileoff, filesize))
        for segn, sname, addr, ssize, soff in sects:
            print("    %-16s %08x+%08x off %08x" % (sname, addr, ssize, soff))
    print("%d symbols" % len(m.symbols))


if __name__ == "__main__":
    main()
