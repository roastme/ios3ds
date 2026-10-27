#!/usr/bin/env python3
"""Decrypt an "encrcdsa" v2 FileVault image (iPhone OS 1.x root filesystem).

The 36-byte key is AES-128 key (16) + HMAC-SHA1 key (20). Each 4 KiB chunk n
is AES-128-CBC with IV = HMAC-SHA1(hmac_key, be32(n))[:16].

Usage: vfdecrypt.py IN KEYHEX OUT
"""
import hashlib
import hmac
import struct
import sys

from Crypto.Cipher import AES


def main():
    src, keyhex, dst = sys.argv[1:]
    key = bytes.fromhex(keyhex)
    aes_key, hmac_key = key[:16], key[16:36]
    f = open(src, "rb")
    hdr = f.read(0x100)
    if hdr[:8] != b"encrcdsa":
        sys.exit("not an encrcdsa image")
    blocksize = struct.unpack_from(">I", hdr, 0x34)[0]
    datasize, dataoffset = struct.unpack_from(">QQ", hdr, 0x38)
    print("blocksize %#x datasize %#x dataoffset %#x" % (blocksize, datasize, dataoffset))
    f.seek(dataoffset)
    out = open(dst, "wb")
    n = 0
    left = datasize
    while left > 0:
        chunk = f.read(blocksize)
        if len(chunk) < blocksize:
            chunk += bytes(blocksize - len(chunk))
        iv = hmac.new(hmac_key, struct.pack(">I", n), hashlib.sha1).digest()[:16]
        plain = AES.new(aes_key, AES.MODE_CBC, iv).decrypt(chunk)
        out.write(plain[:min(blocksize, left)])
        left -= blocksize
        n += 1
    out.close()


if __name__ == "__main__":
    main()
