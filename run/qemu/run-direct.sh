#!/bin/sh
# Boot iPhone OS 1.1 in qemu-ios with the kernel loaded directly (no iBoot).
cd "$(dirname "$0")"
exec ../../ref/qemu-ios/build/qemu-system-arm -M iPod-Touch,bootrom=bootrom-zero.bin,iboot=stub.bin,nand=nand \
  -cpu max -m 1G -pflash nor.bin \
  -device loader,file=boot.bin,addr=0x08000000,force-raw=on \
  -serial file:uart0.log -serial file:uart1.log -serial file:uart2.log -serial file:uart3.log -serial file:uart4.log \
  "$@"
