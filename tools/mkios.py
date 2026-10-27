#!/usr/bin/env python3
"""Build the New 3DS SD payload for iPhone OS 1.1.

  kernelcache --kpatch--> patched kernel --mkboot--> boot image at physBase 0x20000000
  + shim/shim.bin placed in the reserved area after boot_args (header filled in)
  -> OUT/ios1/boot.bin, OUT/ios1/entry.bin (shim physical entry), OUT/boot.json

Usage: mkios.py OUTDIR [--kernel K] [--args "..."] [--mem-size 0x08000000]
"""
import argparse
import json
import os
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PHYS_BASE = 0x20000000          # FCRAM
SHIM_AREA = 0x40000             # bytes reserved for the shim (code, data, stacks)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--kernel", default=os.path.join(ROOT, "fw/work/kernelcache.patched.macho"))
    ap.add_argument("--devicetree", default=os.path.join(ROOT, "fw/dec/DeviceTree.n45ap.raw"))
    ap.add_argument("--shim", default=os.path.join(ROOT, "shim/shim.bin"))
    ap.add_argument("--mem-size", default="0x08000000")
    ap.add_argument("--fb", default="0x18200000")   # VRAM, above the loader's 3DS framebuffers
    ap.add_argument("--args", default="-v debug=0x8 cpus=1 rd=disk0s1 io=0xffff8fff")
    a = ap.parse_args()

    os.makedirs(os.path.join(a.out, "ios1"), exist_ok=True)
    img = os.path.join(a.out, "ios1/boot.bin")
    info_path = os.path.join(a.out, "boot.json")
    subprocess.check_call([sys.executable, os.path.join(HERE, "mkboot.py"), a.kernel, a.devicetree, img,
                           "--phys-base", hex(PHYS_BASE), "--mem-size", a.mem_size, "--fb", a.fb,
                           "--extra-top", hex(SHIM_AREA), "--args", a.args, "--info", info_path],
                          stdout=subprocess.DEVNULL)
    info = json.load(open(info_path))

    shim = bytearray(open(a.shim, "rb").read())
    if shim[12:16] != b"S5LS":
        raise SystemExit("shim.bin has no S5LS header")
    if len(shim) > info["shim_size"]:
        raise SystemExit("shim.bin (%d bytes) does not fit in %d" % (len(shim), info["shim_size"]))
    struct.pack_into("<II", shim, 4, info["boot_args_phys"], info["entry_phys"])

    data = bytearray(open(img, "rb").read())
    off = info["shim_phys"] - PHYS_BASE
    data[off:off + len(shim)] = shim
    open(img, "wb").write(data)
    open(os.path.join(a.out, "ios1/entry.bin"), "wb").write(struct.pack("<I", info["shim_phys"]))
    for k in ("entry_phys", "boot_args_phys", "dt_phys", "shim_phys", "shim_virt", "top_of_kernel_data",
              "image_size"):
        print("%-20s %#x" % (k, info[k]))


if __name__ == "__main__":
    main()
