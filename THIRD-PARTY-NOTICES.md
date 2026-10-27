# Third-party notices

`ios3ds` as a whole is GPL-2.0-or-later (see `COPYING`), because it builds on
GPL-2.0 work. The components below keep their own copyright and terms; all of
them are compatible with that licence.

## qemu-ios — GPL-2.0

`patches-lcd-irq-status.diff` is a patch against qemu-ios
(<https://github.com/devos50/qemu-ios>, branch `ipod_touch_1g`), and the device
models and the hardware inventory in `notes/` were developed against it. qemu-ios
is GPL-2.0. Its source is not vendored here — clone it into `ref/qemu-ios`
yourself.

## loader draw code — GPL-2.0-or-later

`loader/arm9/source/draw.c` and `loader/arm9/include/draw.h` are Normmatt's,
Copyright 2013, licensed GPL-2.0-or-later. `loader/license.txt` is the GPL-2.0
text that ships with them. (`loader/arm9/include/font.h` is a bitmap generated
with devkitPro's `raw2c`.)

## SD driver — MPL-2.0 or GPL-2.0

`loader/arm9/source/fatfs/sdmmc.c`: Copyright (c) 2014-2015 Normmatt,
Mozilla Public License 2.0, alternatively GPL-2.0 or later.

## FatFs — BSD-style (ChaN)

`loader/arm9/source/fatfs/` and `loader/arm9/include/fatfs/`: FatFs R0.12,
Copyright (C) 2016 ChaN. The licence is the one-clause BSD-style text at the top
of `ff.c`/`ff.h` and in `00readme.txt`.

## xnu3ds — APSL-2.0 (separate repository)

`xnu3ds/` is a port of Apple's XNU and is **not** part of this repository or
covered by its licence. XNU is under the Apple Public Source License 2.0. Publish
it separately (or as a submodule) with its own `LICENSE`, and do not mix it into
this tree.

## Apple firmware — not distributed

No Apple code or data is in this repository. The kernelcache, iBoot, IPSW,
rootfs and the extracts derived from them (`notes/prelink-info.xml`,
`notes/devicetree-ipsw*.txt`) are excluded by `.gitignore`; running this requires
your own copy of the iPod touch 1G firmware 1.1 (3A101a), which Apple's licence
restricts to Apple hardware. The `notes/` files that remain are measurements and
address tables produced by this project, not Apple source.

## Nintendo material — not distributed

`boot9.bin`, `boot11.bin`, `ctrnand_full.bin` and other console dumps are
required to run the 3Beans harness and are never committed.
