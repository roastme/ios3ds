#!/usr/bin/env python3
"""Print kernelcache symbols matching a regex, sorted by address: syms.py KERNEL REGEX"""
import re, sys
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from macho import MachO
m = MachO(sys.argv[1])
rx = re.compile(sys.argv[2])
for n, v in sorted(m.symbols.items(), key=lambda kv: kv[1]):
    if rx.search(n):
        print("%08x %s" % (v, n))
