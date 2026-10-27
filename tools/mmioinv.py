#!/usr/bin/env python3
"""Turn qemu-ios QEMU_MMIOSTAT output into a per-device hardware inventory.

Each register line gets: device-tree node (arm-io children are at 0x38000000 +
reg), access counts, values, and the code that touched it (kernel symbol or
kext, from the guest PC). Accesses from PCs below 0xC0000000 are bootrom/iBoot
and are listed separately.
Usage: mmioinv.py MMIOSTAT.txt DEVICETREE.raw KERNEL KEXTS.txt > inventory.txt
"""
import bisect, collections, re, struct, sys
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import adt
from macho import MachO

stat, dtpath, kpath, kxpath = sys.argv[1:5]
raw = open(dtpath, "rb").read()
if raw[:4] == b"2gmI":
    raw = raw[0x400:]
root, _ = adt.parse(raw)
ranges = []  # (lo, hi, path)
for path, n in root.walk():
    reg = n.get("reg")
    if not reg or not path.startswith("/arm-io/") or path.count("/") != 2:
        continue
    w = struct.unpack("<%dI" % (len(reg) // 4), reg[:len(reg) // 4 * 4])
    for i in range(0, len(w) - 1, 2):
        if w[i + 1]:
            ranges.append((0x38000000 + w[i], 0x38000000 + w[i] + w[i + 1], path[len("/arm-io/"):]))
ranges.sort(key=lambda r: r[1] - r[0])

def node(pa):
    for lo, hi, p in ranges:
        if lo <= pa < hi:
            return p, pa - lo
    return None, None

m = MachO(kpath)
syms = sorted((v & ~1, n) for n, v in m.symbols.items() if v >= 0xC0000000)
svals = [s[0] for s in syms]
kexts = [(int(a[1], 16), int(a[2], 16), a[3].replace("com.apple.", "")) for a in
         (re.match(r"([0-9a-f]+)-([0-9a-f]+) .* (\S+)$", l.strip()) for l in open(kxpath)) if a]

def who(pc):
    if pc < 0xC0000000:
        return "boot:%08x" % pc
    for a, b, n in kexts:
        if a <= pc < b:
            return "%s+%x" % (n, pc - a)
    i = bisect.bisect_right(svals, pc & ~1) - 1
    return "%s+%x" % (syms[i][1], (pc & ~1) - syms[i][0]) if i >= 0 else "%08x" % pc

regs = collections.defaultdict(list)
for line in open(stat):
    if line.startswith("#"):
        continue
    f = line.split()
    pa, rw, size, count, seq, v0, v1, ch, name = f[:9]
    kcount, kva = int(f[9]), int(f[10], 16)
    pcs = [int(x, 16) for x in f[11:]]
    pa = int(pa, 16)
    if 0x08000000 <= pa < 0x10000000:
        continue  # DRAM page that qemu routed through the IO path (subpage); not a device
    dev, off = node(pa)
    if dev is None:
        dev, off = "?" + name, pa & 0xFFF
    regs[dev].append((off, pa, rw, int(size), int(count), int(seq), int(v0, 16), int(v1, 16), int(ch), pcs, name, kcount, kva))

def users(rs, kernel):
    c = collections.Counter()
    for r in rs:
        for pc in r[9]:
            if (pc >= 0xC0000000) == kernel:
                c[re.sub(r"\+[0-9a-f]+$", "", who(pc))] += 1
    return ", ".join(n for n, _ in c.most_common(6))

order = sorted(regs, key=lambda d: min(r[5] for r in regs[d]))
print("# kernel-side accesses per device (VA >= 0xC0000000), busiest first:")
for dev in sorted(regs, key=lambda d: -sum(r[11] for r in regs[d])):
    k = sum(r[11] for r in regs[dev])
    if k:
        top = max(regs[dev], key=lambda r: r[11])
        print("#   %-22s %10d   hottest +%04x %s%d (%d)" % (dev, k, top[0], top[2], top[3] * 8, top[11]))
print("# S5L8900 MMIO touched during a qemu-ios boot to SpringBoard (in first-touch order)")
print("# per device: total accesses, kernel-side users, boot-side (bootrom/iBoot) only?")
for dev in order:
    rs = sorted(regs[dev])
    total = sum(r[4] for r in rs)
    ktotal = sum(r[11] for r in rs)
    kern = [r for r in rs if r[11]]
    kvas = sorted(set(r[12] - r[0] for r in kern))
    base = min(r[1] - r[0] for r in rs)
    print("\n## %s  @%08x  (qemu region %s)  accesses=%d kernel=%d  regs=%d  %s%s" % (
        dev, base, rs[0][10], total, ktotal, len(rs), "" if kern else "[boot-only]",
        "  kva=" + ",".join("%08x" % v for v in kvas[:3]) if kvas else ""))
    if kern:
        print("   kernel users: " + users(rs, True))
    if any(any(pc < 0xC0000000 for pc in r[9]) for r in rs):
        print("   boot users:   " + users(rs, False))
    for off, pa, rw, size, count, seq, v0, v1, ch, pcs, name, kc, kva in rs:
        print("   +%04x %s%d n=%-9d k=%-9d first=%08x last=%08x chg=%-6d %s" % (
            off, rw, size * 8, count, kc, v0, v1, ch, " ".join(who(p) for p in pcs[:4])))
