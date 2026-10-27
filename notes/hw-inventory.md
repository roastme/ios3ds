# iPhone OS 1.1 (3A101a, N45AP): hardware the kernel touches

Source data (all in `ios3ds/notes/`):
- `mmiostat-springboard.txt`: raw per-register MMIO counts from one qemu-ios boot (real bootrom,
  iBoot-204, n45ap_v1 NOR/NAND) to SpringBoard, until the guest auto-sleeps ("pmu go hib"),
  about 100 s of guest time. Recorded by the `QEMU_MMIOSTAT` patch in qemu-ios
  `accel/tcg/cputlb.c` (the pre-edit `cputlb.c` is kept locally only, it is not
  published).
- `mmio-inventory.txt`: the same data per device-tree node, with every register, values and the
  code that touched it (`tools/mmioinv.py`).
- `cp15-ops.txt`: every `MCR/MRC/MCRR/MRRC p15` word in the kernelcache's `__text`
  (`tools/cp15scan.py`).

"Kernel" accesses means the guest virtual address was >= 0xC0000000. XNU's `io_map` puts
devices at 0xE0000000+ (UART0 at 0xE0000000, VIC 0xE0097000, timer 0xE0099000) and
0xEF36E000-0xF2757000 (IOKit `IODeviceMemory` mappings). iBoot runs with VA == PA.

## Devices the kernel uses (busiest first)

| Device (DT node) | Phys base | Kernel accesses | Regs | Kernel users | Notes |
|---|---|---|---|---|---|
| timer | 0x3E200000 | 51.9M | 23 | `_s5l8900x_get_timebase`/`mach_absolute_time` (+0x80/+0x84), `_s5l8900x_set_decrementer` (+0xA4/+0xA8), `_fleh_fiq_s5l8900x`, `_pe_arm_init_interrupts` | 28M reads of +0x80, 14M of +0x84: the 64-bit timebase read (lo, hi, lo). 4.7M decrementer writes. |
| clkrstgen + clock1 | 0x38100000, 0x3C500000 | 27.4M | 17 | AppleS5L8900X DVFS routine 0xC048C474 | +0x24 RMW, 0x38100404, 0x38100008 written on every idle entry/exit (see below) |
| power (DT `power`, qemu `sysic`) / gpio | 0x39A00000 | 4.7M | 160 | AppleS5L8900X | power +0x0C (on) / +0x10 (off) with mask 3, written on every idle entry/exit; GPIO banks at 0x39A00000+ (DT gpio reg #2) |
| dmac0 (PL080) | 0x38200000 | 291K | 38 | AppleARMPL080DMAC | NAND (via ADM), LCD/audio DMA |
| uart0 | 0x3CC00000 | 196K | 11 | `_serial_getc`/`_serial_putc` (0xC01604AC/C8) | kernel console (`serial=1`); polled TX |
| adm (FMC co-processor) | 0x38800000 | 95K | 20 | AppleS5L8900XFMC | The kernel's NAND path goes through the ADM, not the FMC registers |
| vic0/vic1 (PL192) | 0x38E00000 | 82K | 91 | AppleARMPL192VIC, `_pe_arm_init_interrupts` | +0xF00 (VECTADDR ack) hottest |
| i2c1 | 0x3C900000 | 7.6K | 9 | AppleS5L8900X | accelerometer / codec |
| spi2 | 0x3D200000 | 2.9K | 10 | AppleS5L8900X | multi-touch (Zephyr) |
| clcd | 0x38900000 | 2.4K | 1595 | AppleH1CLCD | +0x18 status read 720x (IRQ status); window regs + gamma LUT |
| i2c0 | 0x3C600000 | 1.3K | 9 | AppleS5L8900X | PMU (PCF50633) |
| dmac1 (PL080) | 0x39900000 | 629 | 33 | AppleARMPL080DMAC | |
| tv-out | 0x39100000 | 585 | 137 | AppleH1CLCD | probe only (no TV connected) |
| sdio | 0x38D00000 | 230 | 16 | AppleS5L8900XSDIO | Wi-Fi (Marvell 88W8686) probe |
| spi1 | 0x3CE00000 | 150 | 12 | AppleS5L8900X | |
| aes | 0x38C00000 | 48 | 56 | AppleS5L8900XCrypto | |
| nor (CFI) | 0x24000000 | 47 | 89 | AppleARMCFIFlashController | NVRAM / syscfg reads |
| mbx | 0x3B000000 | 38 | 24 | AppleMBX | probe/power only; `LK_ENABLE_MBX2D=0` keeps SpringBoard off it |
| uart4 | 0x3CC10000 | 23 | 11 | AppleS5L8900XSerial | |
| otgphyctrl | 0x3C400000 | 21 | 6 | AppleS5L8900XUSBWrangler | |

**Boot-only (bootrom/iBoot, never touched by the kernel in this run):** chipid 0x3E500000,
usb-otg 0x38400000, spi0 0x3C300000, sha1 0x38000000, flash-controller0 (FMC) 0x38A00000,
uart 0x3CC04000 block. The shim acts as iBoot, so none of these need models (the FMC model is
only needed if the ADM model is written on top of it, as in qemu-ios).

## Hot paths and what they mean for trap-and-emulate

Polling loops (timer reads inside `delay()`, UART TX) are harmless: on faster hardware they just
spin fewer times. Per-event work is what costs. One boot shows these per-event paths:

1. **Idle hook.** `AppleARMCPU::_processorIdle` (0xC0157BA8) calls the AppleS5L8900X platform
   idle method, which on every idle entry and exit:
   - switches the CPU clock divider (DVFS) in the routine at 0xC048C474 (RMW of clock1 +0x24,
     writes to clkrstgen +0x404 and +0x08), and stamps `mach_absolute_time` for statistics;
   - toggles power-domain mask 3 through power +0x0C/+0x10 (0xC048E78C) with DSBs between;
   - reprograms the decrementer (`setPop` → `_s5l8900x_set_decrementer` 0xC0061698).
   That is about 10 MMIO accesses (10 traps) per idle cycle, about 68K cycles/s in qemu.
   **kpatch candidate:** `AppleARMCPU::_processorIdle` → `bx lr` (Thumb `70 47` at 0xC0157BA8).
   `cpu_idle` still runs its own WFI (`mcr p15,0,rX,c7,c0,4` at `_cpu_idle+0x80`).
2. **Timebase.** `mach_absolute_time` reads timer +0x80/+0x84 (3 reads per call) and the FIQ
   handler reads +0x80/+0x84/+0xA4/+0xA8/+0xB4. **kpatch candidate:** redirect
   `_s5l8900x_get_timebase` (and the `rtclock` decrementer setter) to a shim fast-path call
   that reads the MPCore private timer (TWD) and extends it to 64 bits, with no fault.
3. **Clock/power pages as plain RAM.** If 1. is not patched, map clock1, clkrstgen and power
   as ordinary writable RAM pages that the shim inspects lazily: their reads in this boot
   return the last written value or a constant (clock1 +0x24 always reads 0x06006700).
   Power +0x14 (state) is the exception and needs a trap.

## qemu-ios hacks the port must replace

- **"tvoutworkaround"** (`TVOUT_WORKAROUND_MEM_BASE 0x8a25960`, `hw/arm/ipod_touch.c`): a
  4-byte region in *DRAM* that reads 0 and drops writes, so the TV-out object can be freed
  without the TV-out protocol. It sits at kernel VA 0xC0A25960, a heap address that only stays
  fixed because the boot is deterministic. On the 3DS (`physBase` 0x20000000) this needs a
  real kernel patch in AppleH1CLCD's TV-out path instead.
- **CLCD status**: AppleH1CLCD's interrupt handler (0xC0379AE8) reads +0x18 and ANDs it with
  the enable mask at `this+0x1F0`; anything else logs "unexpected CLCD interrupt" and writes
  0xFF to +0x18. qemu-ios raises the IRQ on a timer and lowers it on that write; its status
  value makes the message spam the log but is harmless (SpringBoard draws).

## CP15: ARM1176JZF-S (iPod) vs ARM11 MPCore (New 3DS)

Real kernel uses (ARM state, named functions). Kext hits with opc1 != 0 in `cp15-ops.txt` are
Thumb code or the Marvell Wi-Fi chip firmware blob embedded in AppleMRVL868x (it is ARM code
for the Wi-Fi chip, using addresses 0x80002000+) and are not real.

| Op | Where | MPCore | Action |
|---|---|---|---|
| c1,c0,0 SCTLR | `__start`+0x15C, `_set_mmu_control`, `_reset_jmp` | ok | `__start` sets U, XP, Z, I, **V (high vectors at 0xFFFF0000)**, C, W, M. MPCore supports XP=1 and V. |
| c1,c0,2 CPACR | `_init_vfp` | ok | |
| c2,c0,0/1/2 TTBR0/TTBR1/TTBCR | `__start`, `_start_cpu`, `_set_mmu_ttb` | ok (ARMv6K) | |
| c3 DACR | `__start`, `_set_mmu_dac` | ok | |
| c5/c6 FSR/FAR, c5,c0,1 IFSR | `fleh_dataabt`, `fleh_prefabt`, `fleh_swi` | ok | shim reads these first |
| c7,c5,0 / c7,c5,1 / c7,c5,6 / c7,c6,0 / c7,c6,1 / c7,c7,0 / c7,c10,1 / c7,c14,1 | cache helpers | ok | |
| **c7,c10,2 / c7,c14,2 clean (+inv) by set/way** | `_clean_mmu_dcache` 0xC0061168, `_cleanflush_mmu_dcache` 0xC00611E0, `__start`+0x110 | **geometry** | Loops stop at set bit 12 (`tst r0,#0x1000`): 128 sets = 16 KB 4-way ARM1176 D-cache. MPCore L1D is 32 KB 4-way = 256 sets. **Patch `#0x1000` → `#0x2000` in the `tst`/`bic` pairs** (3 loops), or the upper half of the cache is never cleaned. |
| c7,c10,4 DSB, c7,c0,4 WFI | everywhere | ok | |
| c8,c7,0/1/2 TLB ops | `_flush_mmu_tlb*` | ok | |
| c13,c0,1 CONTEXTIDR | `_set_context_id` | ok | |
| c0,c0,0 MIDR, c0,c0,1 CTR, c0,c2,1 ISAR1 | `__start`, `_cpu_start`, `_cpuid_info` | values differ | stored in `BootCpuDatap+0x28`; no MIDR compare found yet, check `_cpuid_info` consumers |
| c15,c12,0..3 PMU | `_pmc_*`, `_chudxnu_*` | same encoding | CHUD only |
| **c15,c2,4 peripheral port remap** | `_Reset_low_ppmr`+0x20 | **absent** | reset/sleep path only; patch out if reached |

## Next

- Turn the three kpatch candidates above (idle hook, set/way cache loops, timebase fast path)
  and the tvout workaround into `tools/kpatch.py`.
- Phase 1: shim skeleton (trap decoder + VIC/timer/UART models) and the 3Beans loader.
