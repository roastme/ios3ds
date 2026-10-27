#!/usr/bin/env python3
"""Build the modified iPhone OS 1.1 root filesystem used for booting.

Applies the qemu-ios rootfs changes (ref/qemu-ios-generate-nand/docs/changes.md)
to a copy of the decrypted HFS+ volume, without mounting it:
  - fstab: single read-write root, no /private/var partition
  - /private/var/root/Library/{AddressBook,Lockdown,Preferences} seeded with
    the activation/lockdown records from the generator's resources/
  - SpringBoard gets LK_ENABLE_MBX2D=0 (no PowerVR MBX 2D path)
  - only the launch daemons qemu-ios keeps

Usage: mkrootfs.py IN.hfs OUT.hfs
"""
import os
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOP = os.path.dirname(HERE)
HFSPLUS = os.path.join(TOP, "ref/qemu-ios-generate-nand/xpwn/compile/hfs/hfsplus")
RES = os.path.join(TOP, "ref/qemu-ios-generate-nand/resources")

KEEP_DAEMONS = {
    "com.apple.AddressBook.plist",
    "com.apple.CommCenter.plist",
    "com.apple.configd.plist",
    "com.apple.mobile.lockdown.plist",
    "com.apple.notifyd.plist",
    "com.apple.SpringBoard.plist",
}


def hfs(img, *args, check=True):
    r = subprocess.run([HFSPLUS, img] + list(args), capture_output=True, text=True)
    if check and r.returncode:
        sys.exit("hfsplus %s failed: %s" % (args, r.stderr))
    return r.stdout


def ls_names(img, path):
    names = []
    for line in hfs(img, "ls", path).splitlines():
        m = re.match(r"^[01]\d{5}\s.*?\d{1,2}:\d{2} (.*)$", line)
        if m:
            names.append(m.group(1))
    return names


def main():
    src, dst = sys.argv[1:]
    shutil.copyfile(src, dst)
    tmp = tempfile.mkdtemp()

    fstab = os.path.join(tmp, "fstab")
    open(fstab, "w").write("/dev/disk0s1 / hfs rw 0 1\n")
    hfs(dst, "rm", "/private/etc/fstab")
    hfs(dst, "add", fstab, "/private/etc/fstab")

    lib = "/private/var/root/Library"
    for d in ("AddressBook", "Lockdown", "Lockdown/activation_records", "Preferences"):
        hfs(dst, "mkdir", lib + "/" + d, check=False)
    hfs(dst, "add", os.path.join(RES, "AddressBook.sqlitedb"), lib + "/AddressBook/AddressBook.sqlitedb")
    hfs(dst, "add", os.path.join(RES, "data_ark.plist"), lib + "/Lockdown/data_ark.plist")
    hfs(dst, "add", os.path.join(RES, "pod_record.plist"), lib + "/Lockdown/activation_records/pod_record.plist")
    hfs(dst, "add", os.path.join(RES, "com.apple.springboard.plist"), lib + "/Preferences/com.apple.springboard.plist")

    ld = "/System/Library/LaunchDaemons"
    sbp = os.path.join(tmp, "sb.plist")
    hfs(dst, "extract", ld + "/com.apple.SpringBoard.plist", sbp)
    pl = plistlib.load(open(sbp, "rb"))
    pl.setdefault("EnvironmentVariables", {})["LK_ENABLE_MBX2D"] = "0"
    plistlib.dump(pl, open(sbp, "wb"), fmt=plistlib.FMT_BINARY)
    hfs(dst, "rm", ld + "/com.apple.SpringBoard.plist")
    hfs(dst, "add", sbp, ld + "/com.apple.SpringBoard.plist")

    for name in ls_names(dst, ld):
        if name.endswith(".plist") and name not in KEEP_DAEMONS:
            hfs(dst, "rm", ld + "/" + name)
    print(hfs(dst, "ls", ld))
    print(hfs(dst, "cat", "/private/etc/fstab"))
    shutil.rmtree(tmp)
    # xpwn's hfsplus leaves some directory valence counts stale; repair them.
    for _ in range(4):
        subprocess.run(["fsck.hfsplus", "-fy", dst], capture_output=True)
        r = subprocess.run(["fsck.hfsplus", "-fn", dst], capture_output=True, text=True)
        last = r.stdout.strip().splitlines()[-1]
        if "appears to be OK" in last:
            break
    print(last)


if __name__ == "__main__":
    main()
