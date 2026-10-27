#!/usr/bin/env python3
"""Convert pre-UAL ARM mnemonics (ldmgtfd, ldrnet, ldrgebt, strgeb ...) to unified syntax in place."""
import re, sys
C = r'(?:eq|ne|cs|hs|cc|lo|mi|pl|vs|vc|hi|ls|ge|lt|gt|le|al)'
M = r'(?:fd|ed|fa|ea|ia|ib|da|db)'
rx_m = re.compile(r'^(\s*(?:\w+:\s*)?)(ldm|stm)(%s)(%s)\b' % (C, M))
rx_l = re.compile(r'^(\s*(?:\w+:\s*)?)(ldr|str)(%s)(bt|sb|sh|b|h|t|d)\b' % C)
for p in sys.argv[1:]:
    out = []
    for l in open(p).read().split('\n'):
        l = rx_m.sub(lambda m: m.group(1) + m.group(2) + m.group(4) + m.group(3), l)
        l = rx_l.sub(lambda m: m.group(1) + m.group(2) + m.group(4) + m.group(3), l)
        out.append(l)
    open(p, 'w').write('\n'.join(out))
