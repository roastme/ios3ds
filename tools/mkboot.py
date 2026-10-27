#!/usr/bin/env python3
"""Build a flat iPhone OS 1.1 boot image: kernel + device tree + boot_args.

This does iBoot's job. The output is a raw image to be placed at physBase:

  physBase + 0                 kernel (VA virtBase.., segments flattened, BSS zeroed)
  physBase + dt_off            flattened device tree (filled in like iBoot does)
  physBase + ba_off            boot_args
  physBase + top_off           topOfKernelData (16 KiB aligned; bootstrap page tables
                               are built here by __start, 0x5000 bytes)

The kernel is entered at its __start physical address with r0 = boot_args
(physical), MMU off, SVC mode, IRQ/FIQ masked.

Usage: mkboot.py KERNEL DEVICETREE OUT.bin --phys-base 0x08000000 --mem-size 0x07D00000
                 --fb 0x0FE00000 [--args "..."] [--extra-top 0x...] [--info OUT.json]
"""
import argparse
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from macho import MachO  # noqa: E402
import adt  # noqa: E402

VIRT_BASE = 0xC0000000
PAGE = 0x1000


def align(x, a):
    return (x + a - 1) & ~(a - 1)


def u32(v):
    return struct.pack("<I", v & 0xFFFFFFFF)


def fill_devicetree(root, a, dt_phys_placeholder=0):
    """Set the properties iBoot fills in on a real N45 boot."""
    root.set("serial-number", b"3DS0000IOS1".ljust(32, b"\0"))
    root.set("model-number", b"MA623".ljust(32, b"\0"))
    root.set("region-info", b"LL/A".ljust(32, b"\0"))
    root.set("local-mac-address", bytes.fromhex("0016cb000001"))
    root.set("clock-frequency", u32(412000000))

    chosen = root.find("chosen")
    chosen.set("debug-enabled", u32(1))
    chosen.set("firmware-version", b"iBoot-204".ljust(256, b"\0")[:len(chosen.get("firmware-version"))])
    chosen.set("secure-boot", u32(0))
    chosen.set("system-trusted", u32(1))
    chosen.set("development-cert", u32(1))
    chosen.set("production-cert", u32(0))

    cpu = root.find("cpus/cpu0")
    cpu.set("clock-frequency", u32(412000000))
    cpu.set("bus-frequency", u32(103000000))
    cpu.set("peripheral-frequency", u32(51500000))
    cpu.set("memory-frequency", u32(137000000))
    cpu.set("fixed-frequency", u32(24000000))
    cpu.set("timebase-frequency", u32(a.timebase))
    cpu.set("cpu-version", u32(0x41))

    root.find("memory").set("reg", u32(a.phys_base) + u32(a.mem_size))
    root.find("vram").set("reg", u32(a.fb) + u32(a.fb_size))

    # memory-map: leave every entry zero so the kernel frees nothing it
    # did not allocate; the "DeviceTree" placeholder becomes (0, 0) too.
    mm = root.find("chosen/memory-map")
    for p in mm.props:
        if p[0] != "name" and p[0] != "AAPL,phandle":
            p[2] = bytes(8)
    return root


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("kernel")
    ap.add_argument("devicetree")
    ap.add_argument("out")
    ap.add_argument("--phys-base", type=lambda s: int(s, 0), required=True)
    ap.add_argument("--mem-size", type=lambda s: int(s, 0), required=True)
    ap.add_argument("--fb", type=lambda s: int(s, 0), required=True)
    ap.add_argument("--fb-size", type=lambda s: int(s, 0), default=0x100000)
    ap.add_argument("--timebase", type=lambda s: int(s, 0), default=6000000)
    ap.add_argument("--args", default="-v debug=0x8 serial=1 cpus=1 rd=disk0s1 io=0xffff8fff")
    ap.add_argument("--extra-top", type=lambda s: int(s, 0), default=0,
                    help="bytes reserved after boot_args, before topOfKernelData (shim area)")
    ap.add_argument("--info")
    a = ap.parse_args()

    k = MachO(a.kernel)
    end_va = 0
    img = bytearray()
    for name, vmaddr, vmsize, fileoff, filesize, _ in k.segments:
        if vmaddr < VIRT_BASE or not vmsize:
            continue
        off = vmaddr - VIRT_BASE
        end_va = max(end_va, vmaddr + vmsize)
        if len(img) < off + vmsize:
            img.extend(bytes(off + vmsize - len(img)))
        img[off:off + filesize] = k.data[fileoff:fileoff + filesize]
        # zero-fill the rest of the segment (BSS / common)
        img[off + filesize:off + vmsize] = bytes(vmsize - filesize)
    kernel_end = align(end_va - VIRT_BASE, PAGE)

    dt_raw = open(a.devicetree, "rb").read()
    if dt_raw[:4] == b"2gmI":
        dt_raw = dt_raw[0x400:]
    root, _ = adt.parse(dt_raw)
    fill_devicetree(root, a)
    dt = adt.serialize(root)

    dt_off = kernel_end
    ba_off = align(dt_off + len(dt), PAGE)
    shim_off = ba_off + PAGE
    top_off = align(shim_off + a.extra_top, 0x4000)
    total = top_off + 0x5000  # bootstrap L1 (16K) + L2 (4K)

    img.extend(bytes(total - len(img)))
    img[dt_off:dt_off + len(dt)] = dt

    ba = bytearray(0x38 + 256)
    struct.pack_into("<HHIIII", ba, 0, 1, 3, VIRT_BASE, a.phys_base, a.mem_size, a.phys_base + top_off)
    # Boot_Video: baseAddr, display, rowBytes, width, height, depth
    struct.pack_into("<6I", ba, 0x14, a.fb, 1, 320 * 4, 320, 480, 32)
    struct.pack_into("<III", ba, 0x2C, 0, VIRT_BASE + dt_off, len(dt))
    cmd = a.args.encode()[:255]
    ba[0x38:0x38 + len(cmd)] = cmd
    img[ba_off:ba_off + len(ba)] = ba

    open(a.out, "wb").write(img)
    entry_phys = a.phys_base + (k.entry - VIRT_BASE)
    info = {
        "phys_base": a.phys_base, "mem_size": a.mem_size,
        "entry_phys": entry_phys, "boot_args_phys": a.phys_base + ba_off,
        "dt_phys": a.phys_base + dt_off, "dt_len": len(dt),
        "shim_phys": a.phys_base + shim_off, "shim_virt": VIRT_BASE + shim_off,
        "shim_size": top_off - shim_off,
        "top_of_kernel_data": a.phys_base + top_off, "image_size": len(img),
        "fb": a.fb,
    }
    if a.info:
        json.dump(info, open(a.info, "w"), indent=1)
    for kk, v in info.items():
        print("%-20s %#x" % (kk, v))


if __name__ == "__main__":
    main()
