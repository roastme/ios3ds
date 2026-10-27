# HTC HD2 iOS 7 port (xnu-hd2): what it is and what it means for the 3DS

Clone: `ios3ds/ref/xnu-hd2` (github.com/Garysss123/xnu-hd2, HEAD 8137aa2, 2026-10-08). Source only; not built.

## What the repo is
- An **open-source XNU 13.0.0 (xnu-2050, the iOS 7 / OS X 10.9 era)** tree. It comes from winocm's
  "darwin-on-arm" port (2013) via imbushuo/xnu and HTC-Leo-Revival-Project/xnu (`d5c85d9`).
  Board `QSD8250_LEO` (HD2, Snapdragon, ARMv7 Thumb).
- HD2 work lives in:
  - `xnu/pexpert/arm/pe_qsd8250_leo.c` (851 lines) and `leo_qsd8250_timer.c`
  - `xnu/iokit/Drivers/KernelBuiltIn/ARM/AppleARMPlatform/IOS7Leo*`: SDCC storage, MDP display,
    HID touch, an HFS file reader and an SD-card logger
- The way it runs iOS 7 is that the userland ABI matches its kernel: iOS 7 userland is Darwin 13,
  and so is xnu-2050. It replaces Apple's kexts with its own built-in IOKit services that look
  enough like what the iOS 7 frameworks expect (display, HID). `osfmk/arm/ios7_compat.h` holds
  small ABI adapters ("vmabi").
- Dev pattern: an "IOS7Lab" target on `ARMPBA8` (the RealView PB-A8 that qemu emulates), with PL181
  SD and PS/2 pointer drivers. They brought up the iOS 7 userland in qemu first, then on the HD2.
  This is the same idea as our 3Beans-first plan.
- Boot hand-off: `pexpert/pexpert/arm/leo_handoff.h` is a 128-byte record under DT `/chosen`, with
  loader/XNU checkpoints 1..11 drawn on screen. It's the same "stage word" idea as our loader.
- **Status, by its own audit (`SOURCE-AUDIT.md`):** not shown to compile from this export.
  - It needs a Darwin Mach-O ARM toolchain and about 300 generated MIG/config headers that aren't
    included.
  - No boot was proven from this source. The demo binary and the userland are not published.
  - Press (sohu/ifeng/sina, 2026-10-08) reports the iOS 7 UI and touch working on the device.

## The important finding: this tree already supports ARMv6 and the S5L8900X
- `makedefs/MakeInc.def` has ARMv6 machine configs: `S5L8900XRB` (iPhone 2G / iPod touch 1G),
  `S5L8720X` (iPod touch 2G), `RASPBERRYPI` (BCM2835 = ARM1176, the same core as the iPod) and
  `ARM_RVEB_V6`.
- ARMv6 code: `osfmk/arm/armv/cpufunc-v6.s`, plus v6 paths in `cache.s`, `pmap.c`, `proc_reg.h`
  and `bcopy.s`.
- `pexpert/arm/pe_s5l8900x.c` (winocm, 2013) is **open source for the exact SoC our kernel
  expects**: 2 PL192 VICs at 0x38E00000/0x38E01000, edge IC 0x38E02000, the 64-bit timer at
  0x3E200000 (+0x80 COUNTHIGH, +0x84 COUNTLOW, +0x88 control, +0xA0.. timer 0
  control/command/data/prescaler/counter, +0xF8 IRQ latch), UART and clock gates.
  These match the registers Apple's 1.1 kernel touched on 3Beans (timer +0x80/+0x84/+0x88/+0xA0-AC,
  VIC +0x0C/+0x10). **Use it as the register reference for the shim's timer and VIC models,
  instead of disassembling** (see the memory rule "Disassembly is a last resort").
- Caveat: none of the sources found show that winocm's ARMv6 boards ever booted. In 2014 the
  project reached launchd on ARMv7, and launchd died after fork.

## What it means for the iOS 1.1 → New 3DS port
Two possible routes:
1. **Current route (keep):** Apple's own 1.1 kernelcache and kexts, plus the S5L shim. The userland
   ABI is guaranteed to match, and Apple's drivers (FTL, LCD, multitouch) come for free once
   their hardware is modelled. XNU already prints its banner on 3Beans.
2. **HD2-style route:** build this open XNU for a new ARMv6K "3DS" board
   (start from `RASPBERRYPI`/`S5L8900XRB`, plus GIC/TWD/PDC drivers) and write our own IOKit
   display/touch/SD services, as the HD2 did. Problems:
   - **No ARMv6 userland matches xnu-2050.** iOS 7 userland is ARMv7-only; the 3DS ARM11 can't run it.
   - The newest ARMv6 iOS is 4.2.1 (Darwin 10); 1.1 is Darwin 9. Both expect older syscall and
     Mach/IOKit user-client interfaces, so we'd add an ABI layer like `ios7_compat.h`, only much
     bigger.
   - It needs a Mach-O ARM toolchain on Linux (cctools-port/ld64 + clang) and regenerating the MIG
     headers.
   - It has no proven ARMv6 boot.
   - Much more work than route 1. It's a fallback only if the binary kernel can't be made to run.

Pieces worth borrowing for route 1:
- `pe_s5l8900x.c` register maps (timer, VIC, UART) for the shim models.
- `osfmk/arm` (pmap, trap and cache code, `cpufunc-v6.s`) to explain what the binary 933 kernel's
  `__start`/pmap/trap code is doing, without disassembling it.
- The HD2 checkpoint/hand-off and SD logger idea: log to the card from the kernel side.
