#!/usr/bin/env python3
"""Disassemble the kernelcache: dis.py KERNEL SYM|ADDR [COUNT] [arm|thumb]

Symbols are printed as labels and branch/literal targets are annotated.
"""
import struct, sys
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from macho import MachO
import capstone

def main():
    m = MachO(sys.argv[1])
    tgt = sys.argv[2]
    count = int(sys.argv[3]) if len(sys.argv) > 3 else 64
    mode = sys.argv[4] if len(sys.argv) > 4 else None
    if tgt in m.symbols or ("_" + tgt) in m.symbols:
        name = tgt if tgt in m.symbols else "_" + tgt
        va = m.symbols[name]
        if mode is None:
            mode = "thumb" if name in m.thumb else "arm"
    else:
        va = int(tgt, 16)
    if mode is None:
        mode = "arm"
    va &= ~1
    rev = {}
    for n, v in m.symbols.items():
        rev.setdefault(v & ~1, n)
    md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB if mode == "thumb" else capstone.CS_MODE_ARM)
    md.detail = True
    code = m.read(va, count * 4)
    n = 0
    for ins in md.disasm(code, va):
        if ins.address in rev:
            print("%s:" % rev[ins.address])
        note = ""
        if ins.mnemonic.startswith("ldr") and "[pc" in ins.op_str and len(ins.operands) > 1 and ins.operands[1].type == capstone.arm.ARM_OP_MEM:
            base = (ins.address + (4 if mode == "thumb" else 8))
            if mode == "thumb":
                base &= ~3
            lit = base + ins.operands[1].mem.disp
            try:
                v = m.u32(lit)
                note = "  ; =%08x %s" % (v, rev.get(v & ~1, ""))
            except Exception:
                pass
        elif ins.mnemonic in ("bl", "blx", "b") or ins.mnemonic.startswith("b") and ins.operands and ins.operands[0].type == capstone.arm.ARM_OP_IMM:
            if ins.operands and ins.operands[0].type == capstone.arm.ARM_OP_IMM:
                note = "  ; %s" % rev.get(ins.operands[0].imm & ~1, "")
        print("  %08x: %-8s %-10s %s%s" % (ins.address, ins.bytes.hex(), ins.mnemonic, ins.op_str, note))
        n += 1
        if n >= count:
            break

main()
