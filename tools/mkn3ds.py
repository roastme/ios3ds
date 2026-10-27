#!/usr/bin/env python3
"""Pack the open-XNU N3DS kernel into the SD payload for the ios3ds loader.

  mach_kernel (xnu3ds, N3DS config) + minimal device tree + boot_args + stage-0 shim
  -> OUT/ios1/boot.bin   loaded by the ARM9 loader at physBase 0x20000000
     OUT/ios1/entry.bin  4 bytes: physical entry of the shim (it jumps to __start, r0 = boot_args)

Layout (offsets from physBase): kernel segments at (vmaddr - virtBase), device tree, boot_args,
shim, then topOfKernelData (16 KiB aligned; locore builds its bootstrap page tables there).

Usage: mkn3ds.py OUTDIR [--kernel K] [--args "..."] [--mem-size 0x07F00000]
"""
import argparse
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from macho import MachO  # noqa: E402

VIRT_BASE = 0x80000000
PHYS_BASE = 0x20000000
PAGE = 0x1000
SHIM_AREA = 0x10000


def align(x, a):
    return (x + a - 1) & ~(a - 1)


def prop(name, value):
    if isinstance(value, str):
        value = value.encode() + b"\0"
    elif isinstance(value, int):
        value = struct.pack("<I", value)
    return name.encode().ljust(32, b"\0") + struct.pack("<I", len(value)) + value + bytes((-len(value)) % 4)


def node(props, children=()):
    out = struct.pack("<II", len(props), len(children)) + b"".join(props)
    return out + b"".join(children)


def devicetree(phys_base, mem_size, args, ramdisk=None):
    mm = [prop("name", "memory-map")]
    if ramdisk:
        mm.append(prop("RAMDisk", struct.pack("<II", ramdisk[0], ramdisk[1])))
    memmap = node(mm)
    chosen = node([prop("name", "chosen"),
                   prop("firmware-version", "ios3ds-loader".ljust(32, "\0")[:32]),
                   prop("debug-enabled", 1)], [memmap])
    memory = node([prop("name", "memory"), prop("device_type", "memory"),
                   prop("reg", struct.pack("<II", phys_base, mem_size))])
    cpu0 = node([prop("name", "cpu0"), prop("device_type", "cpu"),
                 prop("timebase-frequency", 33513982)])
    cpus = node([prop("name", "cpus")], [cpu0])
    return node([prop("name", "device-tree"), prop("compatible", "N72AP\0iPod2,1\0Nintendo,New3DS\0xnu3ds"),
                 prop("model", "iPod2,1"), prop("device_type", "bootrom"),
                 prop("#address-cells", 1), prop("#size-cells", 1)],
                [chosen, memory, cpus])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--kernel", default=os.path.join(ROOT, "build/xnu/obj/DEVELOPMENT_ARM_N3DS/mach_kernel"))
    ap.add_argument("--shim", default=os.path.join(ROOT, "shim/shim.bin"))
    ap.add_argument("--mem-size", type=lambda s: int(s, 0), default=0x07F00000)
    ap.add_argument("--args", default="-v debug=0x14e serial=0 cpus=1")
    ap.add_argument("--ramdisk", help="HFS+ image placed in RAM and used as root (rd=md0)")
    a = ap.parse_args()

    k = MachO(a.kernel)
    img = bytearray()
    end_va = 0
    for name, vmaddr, vmsize, fileoff, filesize, _ in k.segments:
        if vmaddr < VIRT_BASE or not vmsize:
            continue
        off = vmaddr - VIRT_BASE
        end_va = max(end_va, vmaddr + vmsize)
        if len(img) < off + vmsize:
            img.extend(bytes(off + vmsize - len(img)))
        img[off:off + filesize] = k.data[fileoff:fileoff + filesize]
        img[off + filesize:off + vmsize] = bytes(vmsize - filesize)
    kernel_end = align(end_va - VIRT_BASE, PAGE)

    rd = open(a.ramdisk, "rb").read() if a.ramdisk else b""
    args = a.args + (" rd=md0" if rd and "rd=" not in a.args else "")
    dt_len = len(devicetree(PHYS_BASE, a.mem_size, args, (0, 0) if rd else None))
    dt_off = kernel_end
    ba_off = align(dt_off + dt_len, PAGE)
    shim_off = ba_off + PAGE
    rd_off = align(shim_off + SHIM_AREA, PAGE)
    rd_end = rd_off + len(rd)
    top_off = align(rd_end if rd else shim_off + SHIM_AREA, 0x4000)
    dt = devicetree(PHYS_BASE, a.mem_size, args, (PHYS_BASE + rd_off, len(rd)) if rd else None)
    a.args = args
    total = top_off + 0x5000
    img.extend(bytes(total - len(img)))
    img[dt_off:dt_off + len(dt)] = dt
    if rd:
        img[rd_off:rd_end] = rd

    ba = bytearray(0x38 + 256)
    struct.pack_into("<HHIIII", ba, 0, 1, 1, VIRT_BASE, PHYS_BASE, a.mem_size, PHYS_BASE + top_off)
    # Boot_Video: baseAddr, display, rowBytes, width, height, depth. The console renders into a scratch
    # 32bpp buffer in the unmanaged top 1 MB of FCRAM (240x400 = the 3DS native column-major layout).
    struct.pack_into("<6I", ba, 0x14, PHYS_BASE + a.mem_size, 0, 240 * 4, 240, 400, 32)
    struct.pack_into("<III", ba, 0x2C, 0, VIRT_BASE + dt_off, len(dt))
    cmd = a.args.encode()[:255]
    ba[0x38:0x38 + len(cmd)] = cmd
    img[ba_off:ba_off + len(ba)] = ba

    shim = bytearray(open(a.shim, "rb").read())
    if shim[12:16] != b"S5LS" or len(shim) > SHIM_AREA:
        raise SystemExit("bad shim.bin")
    entry_phys = PHYS_BASE + (k.entry - VIRT_BASE)
    struct.pack_into("<II", shim, 4, PHYS_BASE + ba_off, entry_phys)
    img[shim_off:shim_off + len(shim)] = shim

    klog = img.find(b"N3DSKLOG")
    if klog < 0:
        raise SystemExit("no N3DSKLOG magic in the kernel image")

    os.makedirs(os.path.join(a.out, "ios1"), exist_ok=True)
    open(os.path.join(a.out, "ios1/boot.bin"), "wb").write(img)
    open(os.path.join(a.out, "ios1/entry.bin"), "wb").write(struct.pack("<I", PHYS_BASE + shim_off))
    info = {"entry_phys": entry_phys, "boot_args_phys": PHYS_BASE + ba_off, "dt_phys": PHYS_BASE + dt_off,
            "shim_phys": PHYS_BASE + shim_off, "top_of_kernel_data": PHYS_BASE + top_off,
            "klog_phys": PHYS_BASE + klog, "ramdisk_phys": PHYS_BASE + rd_off if rd else 0, "image_size": len(img)}
    json.dump(info, open(os.path.join(a.out, "boot.json"), "w"), indent=1)
    for kk, v in info.items():
        print("%-20s %#x" % (kk, v))


if __name__ == "__main__":
    main()
