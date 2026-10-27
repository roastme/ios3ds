#!/usr/bin/env python3
"""Unwrap S5L8900 "8900" containers and IMG2 images from iPhone OS 1.x IPSWs.

8900 header (0x800 bytes): magic "8900", version "1.0", format byte at 7
(3 = encrypted with the public 8900 key, 4 = plain), size of data at 0xC.
Data starts at 0x800 and is AES-128-CBC with a zero IV.

Usage: img8900.py IN OUT          -> writes the decrypted 8900 payload
       img8900.py --img2 IN OUT   -> also strips the IMG2 header
       img8900.py --kernel IN OUT -> also decompresses the complzss Mach-O
"""
import struct
import sys

from Crypto.Cipher import AES

KEY_8900 = bytes.fromhex("188458A6D15034DFE386F23B61D43774")


def unwrap_8900(blob):
    if blob[:4] != b"8900":
        raise ValueError("not an 8900 container")
    fmt = blob[7]
    size = struct.unpack_from("<I", blob, 0xC)[0]
    data = blob[0x800:0x800 + size]
    if fmt == 3:
        pad = (-len(data)) % 16
        data = AES.new(KEY_8900, AES.MODE_CBC, bytes(16)).decrypt(data + bytes(pad))[:size]
    elif fmt != 4:
        raise ValueError("unknown 8900 format %d" % fmt)
    return data


def unwrap_img2(blob):
    # IMG2 header: magic "2gmI", image type, ..., data offset/size in the
    # first 0x400 bytes. The payload follows the 0x400-byte header.
    if blob[:4] != b"2gmI":
        raise ValueError("not an IMG2 image: %r" % blob[:4])
    size = struct.unpack_from("<I", blob, 0x10)[0]
    return blob[0x400:0x400 + size] if size else blob[0x400:]


def lzss_decompress(src, dst_size):
    # Apple's complzss: 4 KiB ring buffer, 18-byte max match, 0x20 fill,
    # write position starts at N - F.
    N, F, THRESHOLD = 4096, 18, 2
    ring = bytearray(b" " * (N + F - 1))
    r = N - F
    out = bytearray()
    i = 0
    flags = 0
    while i < len(src) and len(out) < dst_size:
        flags >>= 1
        if not flags & 0x100:
            flags = src[i] | 0xFF00
            i += 1
            if i >= len(src):
                break
        if flags & 1:
            c = src[i]
            i += 1
            out.append(c)
            ring[r] = c
            r = (r + 1) & (N - 1)
        else:
            if i + 1 >= len(src):
                break
            lo, hi = src[i], src[i + 1]
            i += 2
            pos = lo | ((hi & 0xF0) << 4)
            length = (hi & 0x0F) + THRESHOLD
            for k in range(length + 1):
                c = ring[(pos + k) & (N - 1)]
                out.append(c)
                ring[r] = c
                r = (r + 1) & (N - 1)
    return bytes(out[:dst_size])


def unwrap_kernel(blob):
    if blob[:8] != b"complzss":
        return blob
    adler, size, csize = struct.unpack_from(">III", blob, 8)
    return lzss_decompress(blob[0x180:0x180 + csize], size)


def main():
    args = sys.argv[1:]
    mode = None
    if args and args[0].startswith("--"):
        mode = args.pop(0)
    src, dst = args
    data = unwrap_8900(open(src, "rb").read())
    if mode == "--img2":
        data = unwrap_img2(data)
    elif mode == "--kernel":
        data = unwrap_kernel(data)
    open(dst, "wb").write(data)
    print("%s: %d bytes, starts %s" % (dst, len(data), data[:16].hex()))


if __name__ == "__main__":
    main()
