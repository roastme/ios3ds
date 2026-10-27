#!/bin/sh
# iPod touch 1G, iPhone OS 1.1 (3A101a): real bootrom + iBoot-204 + NOR + NAND from devos50 release n45ap_v1.
# Usage: ./run.sh [display-args]   (default headless; use "-display sdl" for a window). Monitor: mon.sock, UART: uart0.log
cd "$(dirname "$0")"; D=../../dl/n45ap_v1
exec ../../ref/qemu-ios/build/qemu-system-arm \
  -M iPod-Touch,bootrom=$D/bootrom_s5l8900,iboot=$D/iboot_204_n45ap.bin,nand=$D/nandx/nand \
  -cpu max -m 1G -pflash $D/nor_n45ap.bin \
  -serial file:uart0.log -monitor unix:mon.sock,server,nowait ${@:--display none}
