#!/bin/bash
# Repackage the N3DS kernel, boot it in 3Beans, wait, dump the RAM log (klog) and a screenshot.
# usage: tools/n3run.sh [wait-seconds]   -> $TMP/klog_ram.txt, $TMP/shot.png
D=$(cd "$(dirname "$0")/.." && pwd)
TMP=${TMP:-${TMPDIR:-/tmp}/ios3ds}
mkdir -p "$TMP"
W=${1:-75}
kill -9 $(pgrep -x 3beans-headless) 2>/dev/null
cd "$D" || exit 1
nice -n 19 ~/.local/venvs/ios1/bin/python tools/mkn3ds.py out/n3ds ${RD:+--ramdisk $RD} ${SDROOT:+--args "-v debug=0x14e serial=0 cpus=1 rd=md0"} ${MEM:+--mem-size $MEM} > $TMP/mk.log 2>&1 || { cat $TMP/mk.log; exit 1; }
KP=$(grep klog_phys $TMP/mk.log | awk '{print $2}')
mdel -i out/sd.img ::ios1/klog.txt 2>/dev/null
mdel -i out/sd.img ::ios1/root.img 2>/dev/null
mcopy -o -i out/sd.img out/n3ds/ios1/boot.bin out/n3ds/ios1/entry.bin ::/ios1/ || exit 1
[ -n "$SDROOT" ] && { mcopy -o -i out/sd.img "$SDROOT" ::/ios1/root.img || exit 1; }
(nice -n 19 ../3Beans/3beans-headless --dir run/3ds --log 2 --port 4900 --system-type 2 > run/3ds/stdout.log 2>&1 &)
sleep "$W"
python3 ../work/b3ctl.py shot $TMP/shot.png both > /dev/null 2>&1
python3 ../work/b3ctl.py dump p 0 $KP 0x100010 $TMP/klog.ram > /dev/null 2>&1
python3 - <<P
d=open("$TMP/klog.ram","rb").read()
pos=int.from_bytes(d[12:16],'little')
open("$TMP/klog_ram.txt","w").write(d[16:16+pos].decode(errors='replace'))
print("klog bytes:",pos)
P
