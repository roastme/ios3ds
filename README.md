# ios3ds

iPhone OS 1.1 running on the New 3DS, by trap-and-emulating the iPod touch's
S5L8900 peripherals under Apple's unmodified kernel.

The 3DS ARM11 is ARMv6K, the same instruction set iPhone OS 1.1 was built for,
so the kernel and userland run natively at full speed. What is missing is the
hardware underneath: every access to an S5L8900 peripheral is made to fault, the
shim decodes the faulting load or store, runs it against a software model backed
by real 3DS hardware (SD card, screens, touch, MCU), and resumes.

## Layout

| Path | What it is |
|---|---|
| `loader/` | Luma3DS FIRM payload (ARM9 + ARM11): loads the shim and the kernelcache from the SD card |
| `shim/` | Resident S5L monitor: data-abort trap handler, device models, kernel hand-off |
| `tools/` | Analysis and image helpers: Mach-O, kernelcache, NAND/SD images, NOR, MMIO inventory |
| `notes/` | Hardware inventory and the analysis outputs behind it |
| `nokextd/` | Preincludes for the iOS 7 / `NO_KEXTD` experiment |
| `build/xnu/mk.sh` | Builds `xnu3ds` (a separate repository, see below) |
| `run/` | qemu-ios and 3Beans harness scripts |

## What is not in this repository

Apple's firmware is not redistributable, so none of it is here: no IPSW, no
kernelcache, no iBoot, no rootfs, and none of the raw extracts taken from them
(`notes/prelink-info.xml`, `notes/devicetree-ipsw*.txt` are ignored for that
reason). You need your own copy of the iPod touch 1G firmware 1.1 (3A101a).

Also excluded (see `.gitignore`):

- `dl/`, `fw/`, `ios421/` — downloaded and extracted firmware material.
- `ref/` — upstream checkouts with their own histories: `qemu-ios`,
  `qemu-ios-generate-nand`, `xnu-hd2`, `cctools-port` and friends.
- `xnu3ds/` — the XNU port. It is its own repository, not part of this one.
- Nintendo `boot9.bin`, `boot11.bin`, `ctrnand_full.bin`.
- `build/cputlb.c.orig` — QEMU's `accel/tcg/cputlb.c` with the `QEMU_MMIOSTAT`
  patch, taken from qemu-ios; fetch it from there if you need it.

`xnu3ds` is a port of Apple's XNU and stays under the Apple Public Source
License 2.0. If you publish it, publish it separately (or add it as a
submodule) with its own licence file.

## Building

The loader needs `arm-linux-gnueabi-gcc` and `firmtool`:

```sh
make -C loader            # -> loader/ios_loader.firm
make -C loader copy       # or: cp to /luma/payloads on the SD card
```

The shim, plus its host test (compiles `shim/dabt.c` with faked CP15 and memory):

```sh
make -C shim              # -> shim/shim.bin, shim/shim.elf
gcc -DHOST_TEST -Iloader/common -Itools/hosttest \
    tools/hosttest/dabt_test.c shim/dabt.c -o /tmp/dabt_test && /tmp/dabt_test
```

## Running

Two harnesses exist; both need files you supply:

- **3Beans (hardware model):** copy `run/3ds/3beans.ini.example` to
  `run/3ds/3beans.ini`, point `boot9Path` / `boot11Path` / `nandPath` at your
  own dumps, then `tools/n3run.sh`.
- **qemu-ios:** `run/qemu/run-direct.sh` and `run/real/run.sh` expect a built
  qemu-ios in `ref/qemu-ios/build/` and a NAND tree under `run/qemu/nand/`.

`tools/` are plain Python and take paths as arguments; most of them read the
kernelcache, an IPSW or the NAND tree that you provide.

## Licence

GPL-2.0-or-later — see `COPYING`.

Some of the code is third-party work with its own terms: the draw code in
`loader/arm9/` is Normmatt's GPLv2+, the SD driver is MPL-2.0 / GPL-2.0 dual,
`loader/arm9/source/fatfs/` is ChaN's FatFs (BSD-style), and parts of the
workflow follow qemu-ios (GPL-2.0). Details in `THIRD-PARTY-NOTICES.md`.
