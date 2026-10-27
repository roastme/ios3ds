#!/usr/bin/env python3
"""Disassemble a raw binary: rawdis.py FILE BASE ADDR COUNT [arm|thumb]"""
import struct, sys, capstone
f, base, addr, n = sys.argv[1], int(sys.argv[2], 16), int(sys.argv[3], 16), int(sys.argv[4])
mode = sys.argv[5] if len(sys.argv) > 5 else "arm"
d = open(f, "rb").read()
md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB if mode == "thumb" else capstone.CS_MODE_ARM)
md.detail = True
for i, ins in enumerate(md.disasm(d[addr - base:addr - base + n * 4], addr)):
    note = ""
    if ins.mnemonic.startswith("ldr") and "[pc" in ins.op_str:
        pc = (ins.address + (4 if mode == "thumb" else 8)) & ~(3 if mode == "thumb" else 0)
        lit = pc + ins.operands[1].mem.disp
        if base <= lit < base + len(d) - 3:
            note = "  ; =%08x" % struct.unpack_from("<I", d, lit - base)[0]
    print("  %08x: %-8s %-8s %s%s" % (ins.address, ins.bytes.hex(), ins.mnemonic, ins.op_str, note))
    if i + 1 >= n:
        break
