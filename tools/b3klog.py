#!/usr/bin/env python3
"""Print XNU's kernel log from a running 3Beans guest (reads the msgbuf from guest RAM).

Usage: b3klog.py [MSGBUF_PHYS] [SIZE]   (default 0x20262000, 0x4000; found by searching
for the "Darwin Kernel Version" banner in a RAM dump)
"""
import os
import subprocess
import sys
import tempfile

B3CTL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../work/b3ctl.py")
addr = int(sys.argv[1], 0) if len(sys.argv) > 1 else 0x20262000
size = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x4000
with tempfile.NamedTemporaryFile(dir=os.environ.get("TMPDIR")) as f:
    subprocess.check_call(["python3", B3CTL, "dump", "p", "0", hex(addr), hex(size), f.name],
                          stdout=subprocess.DEVNULL)
    d = open(f.name, "rb").read()
text = bytearray()
for c in d.replace(b"\0", b""):
    if c not in (9, 10) and not 32 <= c < 127:
        break   # end of the log text
    text.append(c)
sys.stdout.write(text.decode())
