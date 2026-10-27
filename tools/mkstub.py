#!/usr/bin/env python3
"""Make a qemu-ios start stub: replay register writes, then enter the kernel.

The stub runs at IBOOT_BASE (0x18000000) with the MMU off. It writes each
(addr, value) pair from a table (the hardware state iBoot leaves behind,
from mmio-final.py), then jumps to __start with r0 = boot_args.

Usage: mkstub.py BOOT.json REGS.json OUT.bin [--devices lcd]
"""
import argparse
import json
import struct

ap = argparse.ArgumentParser()
ap.add_argument("boot")
ap.add_argument("regs")
ap.add_argument("out")
ap.add_argument("--devices", default="lcd")
a = ap.parse_args()
info = json.load(open(a.boot))
devs = set(a.devices.split(","))
pairs = [(addr, v) for addr, v, size, name in json.load(open(a.regs)) if name in devs and size == 4]

code = [
    0xE28F3020,  # add   r3, pc, #0x20      ; r3 = table (0x28)
    0xE4931004,  # ldr   r1, [r3], #4
    0xE4932004,  # ldr   r2, [r3], #4
    0xE3510000,  # cmp   r1, #0
    0x15812000,  # strne r2, [r1]
    0x1AFFFFFA,  # bne   0x04
    0xE59F0000,  # ldr   r0, [pc]           ; boot_args
    0xE59FF000,  # ldr   pc, [pc]           ; __start
    info["boot_args_phys"],
    info["entry_phys"],
]
blob = struct.pack("<%dI" % len(code), *code)
for addr, v in pairs:
    blob += struct.pack("<II", addr, v)
blob += struct.pack("<II", 0, 0)
open(a.out, "wb").write(blob)
print("%d register writes, %d bytes" % (len(pairs), len(blob)))
