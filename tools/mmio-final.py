#!/usr/bin/env python3
"""Reduce a qemu memory_region_ops_write trace to last-write-wins register values.

mmio-final.py TRACE OUT.json [--until NAME] [--devices a,b,c]
Stops at the first write to device NAME (default 8900engine = kernelcache decrypt,
i.e. the moment iBoot hands over, before any recovery-mode quiesce).
"""
import argparse, collections, json, re
ap = argparse.ArgumentParser()
ap.add_argument("trace"); ap.add_argument("out")
ap.add_argument("--until", default="8900engine")
ap.add_argument("--devices", default="lcd,clock,ipodtouch.sysic,gpio")
a = ap.parse_args()
keep = set(a.devices.split(","))
last = collections.OrderedDict()
for line in open(a.trace):
    m = re.search(r"addr (0x[0-9a-f]+) value (0x[0-9a-f]+) size (\d) name '([^']+)'", line)
    if not m:
        continue
    addr, v, sz, n = int(m.group(1), 16), int(m.group(2), 16), int(m.group(3)), m.group(4)
    if n == a.until:
        break
    if n in keep:
        last.pop(addr, None)
        last[addr] = (v, sz, n)
json.dump([[k, v, s, n] for k, (v, s, n) in last.items()], open(a.out, "w"))
by = collections.Counter(n for v, s, n in last.values())
print(dict(by))
for k, (v, s, n) in last.items():
    if n == "lcd" and not (0x38900400 <= k < 0x38900c00 + 0x400):
        print("%08x = %08x" % (k, v))
