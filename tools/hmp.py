#!/usr/bin/env python3
"""Send HMP commands to a qemu monitor unix socket: hmp.py SOCK "cmd" ["cmd" ...]"""
import socket, sys, time
s = socket.socket(socket.AF_UNIX)
s.connect(sys.argv[1])
s.settimeout(2)
def drain():
    out = b""
    try:
        while True:
            c = s.recv(65536)
            if not c:
                break
            out += c
            if out.endswith(b"(qemu) "):
                break
    except socket.timeout:
        pass
    return out.decode(errors="replace")
drain()
for cmd in sys.argv[2:]:
    s.sendall(cmd.encode() + b"\n")
    out = drain()
    print(out.replace("\r", "").rsplit("(qemu)", 1)[0])
