#!/usr/bin/env python3
"""Tiny GDB remote serial protocol client for qemu's gdbstub (ARM32).

Library: r = RSP("localhost", 1234); r.bp(addr); r.cont(); r.regs(); r.mem(a, n)
CLI:     rsp.py PORT [script.py]  (script runs with `r` bound)
"""
import socket
import struct
import sys
import time


class RSP:
    def __init__(self, host="localhost", port=1234, timeout=None):
        for _ in range(50):
            try:
                self.s = socket.create_connection((host, port))
                break
            except OSError:
                time.sleep(0.2)
        else:
            raise SystemExit("cannot connect to gdbstub")
        self.s.settimeout(timeout)
        self.buf = b""
        self.cmd("QStartNoAckMode")
        self.noack = True

    def _recv_packet(self):
        while True:
            i = self.buf.find(b"$")
            if i >= 0:
                j = self.buf.find(b"#", i)
                if j >= 0 and len(self.buf) >= j + 3:
                    pkt = self.buf[i + 1:j]
                    self.buf = self.buf[j + 3:]
                    return pkt.decode(errors="replace")
            c = self.s.recv(65536)
            if not c:
                raise EOFError
            self.buf += c

    def send(self, data):
        cs = sum(data.encode()) & 0xFF
        self.s.sendall(b"$%s#%02x" % (data.encode(), cs))
        if not getattr(self, "noack", False):
            # consume '+'
            while not self.buf.startswith(b"+"):
                self.buf += self.s.recv(1)
            self.buf = self.buf[1:]

    def cmd(self, data):
        self.send(data)
        return self._recv_packet()

    def regs(self):
        g = bytes.fromhex(self.cmd("g"))
        r = list(struct.unpack_from("<16I", g, 0))
        # qemu arm: r0-r15, then (no FPA for cortex) cpsr at index 25 in old layouts
        cpsr = struct.unpack_from("<I", g, len(g) - 4)[0]
        return r + [cpsr]

    def setreg(self, n, v):
        return self.cmd("P%x=%s" % (n, struct.pack("<I", v).hex()))

    def mem(self, addr, n):
        out = b""
        while n > 0:
            k = min(n, 0x800)
            out += bytes.fromhex(self.cmd("m%x,%x" % (addr, k)))
            addr += k
            n -= k
        return out

    def u32(self, addr):
        return struct.unpack("<I", self.mem(addr, 4))[0]

    def wmem(self, addr, data):
        return self.cmd("M%x,%x:%s" % (addr, len(data), data.hex()))

    def bp(self, addr, kind=4):
        return self.cmd("Z0,%x,%d" % (addr, kind))

    def unbp(self, addr, kind=4):
        return self.cmd("z0,%x,%d" % (addr, kind))

    def cont(self):
        return self.cmd("c")

    def step(self):
        return self.cmd("s")

    def monitor(self, text):
        return self.cmd("qRcmd," + text.encode().hex())


if __name__ == "__main__":
    r = RSP(port=int(sys.argv[1]))
    if len(sys.argv) > 2:
        exec(open(sys.argv[2]).read(), {"r": r, "struct": struct})
