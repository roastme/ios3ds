#!/bin/bash
# Dump the running 3Beans guest's klog to $TMP/klog_peek.txt without stopping it
TMP=${TMP:-${TMPDIR:-/tmp}/ios3ds}
mkdir -p "$TMP"
D=$(cd "$(dirname "$0")/.." && pwd)
KP=$(grep klog_phys $TMP/mk.log | awk '{print $2}')
python3 $D/../work/b3ctl.py dump p 0 $KP 0x100010 $TMP/klog.peek > /dev/null 2>&1
python3 - <<P
d=open("$TMP/klog.peek","rb").read()
pos=int.from_bytes(d[12:16],'little')
open("$TMP/klog_peek.txt","w").write(d[16:16+pos].decode(errors='replace'))
print("klog bytes:",pos)
P
