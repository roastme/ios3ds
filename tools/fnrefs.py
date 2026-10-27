#!/usr/bin/env python3
"""Summarise what a kernel function refers to (calls, literal-pool words that name
symbols or look like constants) without printing its code: fnrefs.py KERNEL FUNC..."""
import bisect, sys, capstone
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from macho import MachO
m = MachO(sys.argv[1])
by = sorted((v, n) for n, v in m.symbols.items())
addrs = [v for v, _ in by]
def name(a):
    i = bisect.bisect_right(addrs, a & ~1) - 1
    if i < 0: return hex(a)
    v, n = by[i]; d = (a & ~1) - v
    return n if d == 0 else "%s+0x%x" % (n, d)
def end_of(a):
    i = bisect.bisect_right(addrs, a)
    while i < len(addrs) and addrs[i] == a: i += 1
    return addrs[i] if i < len(addrs) else a + 0x200
for fn in sys.argv[2:]:
    a = m.symbols[fn]; e = min(end_of(a), a + 0x1000)
    th = fn in m.thumb
    md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB if th else capstone.CS_MODE_ARM)
    md.detail = True
    calls, lits = [], []
    for ins in md.disasm(m.read(a, e - a), a):
        if ins.mnemonic in ("bl", "blx") and ins.operands and ins.operands[0].type == capstone.arm.ARM_OP_IMM:
            calls.append(name(ins.operands[0].imm & 0xFFFFFFFF))
        if ins.mnemonic.startswith("ldr") and "[pc" in ins.op_str:
            mem = ins.operands[1].mem
            la = ((ins.address + (4 if th else 8)) & ~3) + mem.disp
            if a <= la < e + 0x400:
                w = m.u32(la)
                lits.append(name(w) if 0xC0000000 <= w < 0xC1000000 else hex(w))
    print("%s %s @%08x..%08x" % (fn, "thumb" if th else "arm", a, e))
    print("  calls:", ", ".join(dict.fromkeys(calls)) or "-")
    print("  literals:", ", ".join(dict.fromkeys(lits)) or "-")
