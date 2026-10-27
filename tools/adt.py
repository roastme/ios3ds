#!/usr/bin/env python3
"""Apple flattened device tree (iPhone OS 1.x) reader/writer.

Format: node = u32 nProps, u32 nChildren, props, children.
prop = char name[32], u32 length (bit 31 = placeholder flag), value padded to 4.

As a script: adt.py FILE [--all]  -> dumps the tree (reg/interrupts decoded).
"""
import struct
import sys


class Node:
    def __init__(self):
        self.props = []      # list of [name, flags, value(bytes)]
        self.children = []

    def get(self, name):
        for n, f, v in self.props:
            if n == name:
                return v
        return None

    def set(self, name, value, flags=0):
        for p in self.props:
            if p[0] == name:
                p[2] = value
                return
        self.props.append([name, flags, value])

    @property
    def name(self):
        v = self.get("name")
        return v.split(b"\0")[0].decode() if v else "?"

    def find(self, path):
        node = self
        for part in path.strip("/").split("/"):
            if not part:
                continue
            for c in node.children:
                if c.name == part:
                    node = c
                    break
            else:
                return None
        return node

    def walk(self, path=""):
        p = path + "/" + self.name if path or self.name != "device-tree" else ""
        yield p or "/", self
        for c in self.children:
            yield from c.walk(p)


def parse(data, off=0):
    node = Node()
    nprops, nchildren = struct.unpack_from("<II", data, off)
    off += 8
    for _ in range(nprops):
        name = data[off:off + 32].split(b"\0")[0].decode()
        length = struct.unpack_from("<I", data, off + 32)[0]
        flags = length & 0x80000000
        length &= 0x7FFFFFFF
        value = data[off + 36:off + 36 + length]
        node.props.append([name, flags, value])
        off += 36 + ((length + 3) & ~3)
    for _ in range(nchildren):
        child, off = parse(data, off)
        node.children.append(child)
    return node, off


def serialize(node):
    out = bytearray(struct.pack("<II", len(node.props), len(node.children)))
    for name, flags, value in node.props:
        out += name.encode().ljust(32, b"\0")[:32]
        out += struct.pack("<I", len(value) | flags)
        out += value + bytes((-len(value)) % 4)
    for c in node.children:
        out += serialize(c)
    return bytes(out)


def fmt_value(name, v):
    if name in ("reg", "interrupts", "interrupt-parent", "AAPL,phandle", "clock-gates",
                "clock-frequency", "#address-cells", "#size-cells", "timebase-frequency",
                "function-") or (len(v) % 4 == 0 and len(v) <= 32 and any(v) and not v.rstrip(b"\0").isascii()):
        return " ".join("%08x" % x for x in struct.unpack("<%dI" % (len(v) // 4), v[:len(v) // 4 * 4]))
    s = v.rstrip(b"\0")
    if s and all(32 <= c < 127 or c == 0 for c in s):
        return repr(s.replace(b"\0", b"|").decode())
    return v[:48].hex() + ("..." if len(v) > 48 else "")


def main():
    data = open(sys.argv[1], "rb").read()
    if data[:4] == b"2gmI":
        data = data[0x400:]
    root, _ = parse(data)
    show_all = "--all" in sys.argv
    for path, n in root.walk():
        print(path)
        for name, flags, v in n.props:
            if show_all or name in ("reg", "interrupts", "compatible", "device_type", "interrupt-parent", "AAPL,phandle", "clock-gates"):
                print("    %-28s%s %s" % (name, "*" if flags else " ", fmt_value(name, v)))


if __name__ == "__main__":
    main()
