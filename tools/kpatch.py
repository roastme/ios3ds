#!/usr/bin/env python3
"""Patch the decrypted iPhone OS 1.1 (3A101a) kernelcache for the New 3DS ARM11 MPCore.

Every patch checks the original bytes first, so a wrong kernel is refused, not corrupted.
Patches (see notes/hw-inventory.md):
  idle      AppleARMCPU::_processorIdle -> bx lr (no per-idle DVFS/power-gate MMIO;
            cpu_idle still does its own WFI)
  setway    D-cache clean/flush by set/way loops: 128 sets (16 KB ARM1176) -> 256 sets
            (32 KB MPCore L1D) in __start, _clean_mmu_dcache, _cleanflush_mmu_dcache
Opt-in (--with):
  nodcache  __start enables the MMU without the D-cache (SCTLR orr #0xd -> #0x9), so every
            kernel write (the msgbuf) reaches FCRAM where the ARM9 monitor can see it
  vectrap   undef/prefetch-abort/data-abort/IRQ vector literals -> shim capture stubs at
            SHIM_VA + 0x100 * n (shim/start.S), which record the exception and spin
Usage: kpatch.py IN.macho OUT.macho [--only idle,setway] [--with nodcache]
"""
import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from macho import MachO  # noqa: E402

TST_1000_FP = 0xE31B0A01   # tst fp, #0x1000
BIC_1000_FP = 0xE3CBBA01   # bic fp, fp, #0x1000
TST_1000_R0 = 0xE3100A01   # tst r0, #0x1000
BIC_1000_R0 = 0xE3C00A01   # bic r0, r0, #0x1000


def rot(w):
    """#0x1000 is imm8=1 rot=0xA (1 ror 20); #0x2000 is imm8=2 with the same rotation."""
    assert w & 0xFFF == 0xA01
    return (w & ~0xFFF) | 0xA02


VECTRAP = []


def patches(m):
    s = m.symbols
    out = {"idle": [], "setway": [], "nodcache": [], "vectrap": []}
    # Thumb function: symbol value has no low bit in this kernelcache's symtab
    out["idle"].append((s["__ZN11AppleARMCPU14_processorIdleEb"] & ~1, "90b5", "7047"))
    for va, tst, bic in ((0xC0060904, TST_1000_FP, BIC_1000_FP),
                         (s["_clean_mmu_dcache"] + 0xC, TST_1000_R0, BIC_1000_R0),
                         (s["_cleanflush_mmu_dcache"] + 0xC, TST_1000_R0, BIC_1000_R0)):
        out["setway"].append((va, struct.pack("<I", tst).hex(), struct.pack("<I", rot(tst)).hex()))
        out["setway"].append((va + 8, struct.pack("<I", bic).hex(), struct.pack("<I", rot(bic)).hex()))
    out["nodcache"].append((0xC0060940, "0d1081e3", "091081e3"))   # orr r1, r1, #0xd -> #0x9
    out["vectrap"] = VECTRAP
    return out


SHIM_VA = 0xC0662000
# vector literals: undef, prefetch abort, data abort, IRQ (little-endian original handler addresses)
for _i, (_lit, _old) in enumerate(((0xC005F024, "f8ff05c0"), (0xC005F02C, "580206c0"),
                                    (0xC005F030, "f80206c0"), (0xC005F038, "040406c0"))):
    VECTRAP.append((_lit, _old, struct.pack("<I", SHIM_VA + 0x100 * (_i + 1)).hex()))

OPT_IN = {"nodcache", "vectrap"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inp")
    ap.add_argument("out")
    ap.add_argument("--only")
    ap.add_argument("--with", dest="extra", default="")
    a = ap.parse_args()
    m = MachO(a.inp)
    data = bytearray(m.data)
    sel = set(a.only.split(",")) if a.only else None
    n = 0
    for name, lst in patches(m).items():
        if (sel and name not in sel) or (name in OPT_IN and name not in a.extra.split(",")):
            continue
        for va, old, new in lst:
            off = m.va2off(va)
            cur = data[off:off + len(old) // 2].hex()
            if cur != old:
                sys.exit("%s @%08x: expected %s, found %s" % (name, va, old, cur))
            data[off:off + len(new) // 2] = bytes.fromhex(new)
            print("%-8s %08x  %s -> %s" % (name, va, old, new))
            n += 1
    open(a.out, "wb").write(data)
    print("%d patches -> %s" % (n, a.out))


if __name__ == "__main__":
    main()
