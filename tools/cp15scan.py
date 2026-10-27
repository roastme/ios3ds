#!/usr/bin/env python3
"""List every MCR/MRC/MCRR/MRRC p15 (and CDP/LDC p15) in the kernelcache's code.

ARMv6 Thumb has no coprocessor instructions, so only ARM words are scanned; to
avoid data false positives a word must decode, and its neighbours must too.
Output: VA, owner (kernel symbol or kext), op, grouped summary at the end.
Usage: cp15scan.py KERNEL [KEXTS.txt]
"""
import bisect, collections, re, struct, sys
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from macho import MachO
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM

m = MachO(sys.argv[1])
md = Cs(CS_ARCH_ARM, CS_MODE_ARM)
kexts = []
if len(sys.argv) > 2:
    for line in open(sys.argv[2]):
        mm = re.match(r"([0-9a-f]+)-([0-9a-f]+) .* (\S+)$", line.strip())
        if mm:
            kexts.append((int(mm[1], 16), int(mm[2], 16), mm[3]))
syms = sorted((v & ~1, n) for n, v in m.symbols.items() if v >= 0xC0000000)
svals = [s[0] for s in syms]

def owner(va):
    for a, b, n in kexts:
        if a <= va < b:
            k = n
            break
    else:
        k = "kernel"
    i = bisect.bisect_right(svals, va) - 1
    s = "%s+%#x" % (syms[i][1], va - syms[i][0]) if i >= 0 and va - syms[i][0] < 0x4000 else "?"
    return k, s

def decodes(blob, off):
    return off >= 0 and off + 4 <= len(blob) and any(True for _ in md.disasm(blob[off:off + 4], 0))

summary = collections.Counter()
where = collections.defaultdict(list)
for name, vmaddr, vmsize, fileoff, filesize, sects in m.segments:
    for segn, sname, addr, ssize, soff in sects:
        if sname != "__text":
            continue
        blob = m.data[soff:soff + ssize]
        for off in range(0, len(blob) - 3, 4):
            w = struct.unpack_from("<I", blob, off)[0]
            if (w >> 28) == 0xF:
                continue
            cp = (w >> 8) & 0xF
            is_mcr = (w & 0x0F000010) == 0x0E000010 and cp == 15
            is_mcrr = (w & 0x0FE00000) == 0x0C400000 and cp == 15
            if not (is_mcr or is_mcrr):
                continue
            if not (decodes(blob, off - 4) and decodes(blob, off + 4)):
                continue
            ins = next(md.disasm(blob[off:off + 4], addr + off), None)
            if not ins:
                continue
            va = addr + off
            k, s = owner(va)
            text = "%s %s" % (ins.mnemonic, ins.op_str)
            if is_mcr:
                key = "%s p15,%d,c%d,c%d,%d" % ("mrc" if w & (1 << 20) else "mcr", (w >> 21) & 7,
                                                (w >> 16) & 0xF, w & 0xF, (w >> 5) & 7)
            else:
                key = "%s p15,%d,c%d" % ("mrrc" if w & (1 << 20) else "mcrr", (w >> 4) & 0xF, w & 0xF)
            summary[key] += 1
            where[key].append("%s:%s" % (k, s))
            print("%08x  %-28s %-34s %s" % (va, k, text, s))
print("\n# summary (op p15,opc1,CRn,CRm,opc2: count, first users)")
for key, n in sorted(summary.items()):
    users = sorted(set(where[key]))
    print("%-26s %4d  %s" % (key, n, ", ".join(users[:6]) + (" ..." if len(users) > 6 else "")))
