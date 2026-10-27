#!/usr/bin/env python3
"""Convert a UDIF (.dmg, koly trailer) to a raw disk image.

Writes every blkx partition back to back, which for iPhone OS 1.x root
filesystems gives a bare HFS+ volume (the "Apple_HFS" partition) when only
that partition is selected with --hfs.

Usage: udif2raw.py [--hfs] IN OUT
"""
import base64
import bz2
import plistlib
import struct
import sys
import zlib

SECTOR = 512


def chunks(mish):
    # mish header is 0xCC bytes, then 40-byte chunk records.
    first_sector = struct.unpack_from(">Q", mish, 8)[0]
    n = struct.unpack_from(">I", mish, 0xC8)[0]
    for i in range(n):
        typ, _cmt, sec, cnt, off, ln = struct.unpack_from(">IIQQQQ", mish, 0xCC + 40 * i)
        yield typ, first_sector + sec, cnt, off, ln


def main():
    args = sys.argv[1:]
    only_hfs = args and args[0] == "--hfs"
    if only_hfs:
        args.pop(0)
    src, dst = args
    f = open(src, "rb")
    f.seek(-512, 2)
    koly = f.read(512)
    assert koly[:4] == b"koly", koly[:4]
    xml_off, xml_len = struct.unpack_from(">QQ", koly, 0xD8)
    f.seek(xml_off)
    plist = plistlib.loads(f.read(xml_len))
    parts = plist["resource-fork"]["blkx"]
    out = open(dst, "wb")
    base = None
    for p in parts:
        name = p.get("Name", "")
        print("partition:", name)
        if only_hfs and "Apple_HFS" not in name:
            continue
        mish = p["Data"] if isinstance(p["Data"], bytes) else base64.b64decode(p["Data"])
        for typ, sec, cnt, off, ln in chunks(mish):
            if typ == 0xFFFFFFFF:
                break
            if typ in (0x7FFFFFFE,):  # comment
                continue
            if base is None:
                base = sec
            out.seek((sec - base) * SECTOR)
            if typ in (0, 2):  # zero fill / ignore
                out.write(bytes(cnt * SECTOR))
                continue
            f.seek(off)
            data = f.read(ln)
            if typ == 1:
                pass
            elif typ == 0x80000005:
                data = zlib.decompress(data)
            elif typ == 0x80000006:
                data = bz2.decompress(data)
            else:
                sys.exit("unsupported chunk type %#x" % typ)
            out.write(data)
        if only_hfs:
            base = None
            break
    out.close()


if __name__ == "__main__":
    main()
