#!/bin/sh
# qtrace-into.sh IBOOT REGEX: run qemu-ios iBoot with exec tracing and print the
# last guest PCs before the first PC matching REGEX (8 hex digits).
cd "$(dirname "$0")/../run/qemu"
timeout 40 ../../ref/qemu-ios/build/qemu-system-arm -M iPod-Touch,bootrom=bootrom-zero.bin,iboot="$1",nand=nand \
  -cpu max -m 1G -serial file:serial.log -pflash nor.bin -display none -monitor none \
  -d exec,nochain -D trace.log > /dev/null 2>&1
grep -o -E '/[0-9a-f]{8}/' trace.log | tr -d / | awk -v re="$2" '{ if ($0 ~ re) { for (i = 0; i < n; i++) printf "%s ", buf[(k + i) % n]; print "-> " $0; exit } buf[k] = $0; k = (k + 1) % 30; if (n < 30) n++ }'
rm -f trace.log
