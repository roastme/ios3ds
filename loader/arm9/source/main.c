#include "cache.h"
#include "common.h"
#include "draw.h"
#include "fs.h"
#include "hid.h"
#include "i2c.h"
#include "ios_config.h"

__attribute__((noreturn))
static void mcu_poweroff()
{
	i2cWriteRegister(I2C_DEV_MCU, 0x20, 1 << 0);
	while (1) ;
}

static void wait_any_key_poweroff()
{
	Debug("Press any key to poweroff.");
	while (~HID_PAD & BUTTON_NONE)
		;
	while (!(~HID_PAD & BUTTON_NONE))
		;
	mcu_poweroff();
}

static size_t load_file(const char *filename, void *addr, size_t max)
{
	size_t size;

	Debug("Loading %s...", filename);
	if (!FileOpen(filename)) {
		DebugColor(COLOR_RED, "Loading of %s failed!", filename);
		return 0;
	}
	/* 195 MB takes a while on a real card: read in 4 MB steps and show progress */
	size = 0;
	for (;;) {
		size_t want = max - size < 0x400000 ? max - size : 0x400000;
		size_t got = want ? FileRead((u8 *)addr + size, want, size) : 0;
		size += got;
		if (got < want || size >= max)
			break;
		Debug("\r    read %d MB", (int)(size >> 20));
	}
	FileClose();
	Debug("    %d bytes at %08X", size, (u32)addr);
	return size;
}

/* Framebuffers the ARM11 side points the LCDs at (see arm11/source/start.S) */
#define FB_TOP_SIZE (SCREEN_WIDTH_TOP * SCREEN_HEIGHT * 3)
#define FB_BOT_SIZE (SCREEN_WIDTH_BOT * SCREEN_HEIGHT * 3)
#define FB_TOP_1    (VRAM_BASE)
#define FB_TOP_2    (FB_TOP_1 + FB_TOP_SIZE)
#define FB_BOT_1    (FB_TOP_1 + 4 * FB_TOP_SIZE)
#define FB_BOT_2    (FB_BOT_1 + FB_BOT_SIZE)

#define TOP_COLS    ((SCREEN_WIDTH_TOP - 8) / 8)
#define TOP_ROWS    22

static char klog[KLOG_SIZE + 8192];
static u32 klog_addr = KLOG_ADDR;

/* Block mailbox ("N3DSBLK" struct in the kernel image, see pexpert/arm/pe_n3ds.c).
 * Line A (kernel writes): magic[8], req, cmd, lba, count, paddr.
 * Line B (we write):      sectors, ack, status. */
static u32 blk_addr;
static u32 blk_served;

static bool blk_service(void)
{
	vu32 *m = (vu32 *)blk_addr;
	u32 req, cmd, lba, count, paddr;
	int st;

	if (!blk_addr)
		return false;
	flushCaches();
	req = m[2];
	if (req == m[9])
		return false;
	cmd = m[3];
	lba = m[4];
	count = m[5];
	paddr = m[6];
	if (count == 0 || count > 256 || paddr < FCRAM_BASE || paddr + count * 512 > FCRAM_BASE + FCRAM_SIZE)
		st = -4;
	else if (cmd == 2)
		st = RootRW(true, lba, count, (void *)paddr);	/* source was cleaned by the ARM11 */
	else
		st = RootRW(false, lba, count, (void *)paddr);
	flushCaches();
	m[10] = (u32)st;
	m[9] = req;
	flushCaches();
	blk_served++;
	return true;
}

/* Which 128 KB blocks of the low 8 MB of FCRAM (kernel image, page tables, first
 * allocations) changed since the hand-off. With the ARM11 caches on, kernel writes
 * still leak out through evictions, so a mask of 0 means XNU never got going. */
#define SUM_BASE    (FCRAM_BASE)
#define SUM_BLOCK   (0x20000)
#define SUM_BLOCKS  64
static u32 sum_ref[SUM_BLOCKS];
static char line[64];

static void delay(u32 n)
{
	for (vu32 i = 0; i < n; i++)
		;
}

static void draw_line(u8 *fb0, u8 *fb1, int row, const char *text, int color)
{
	DrawString(fb0, text, 4, 4 + row * 10, color, COLOR_BLACK);
	DrawString(fb1, text, 4, 4 + row * 10, color, COLOR_BLACK);
}

/* Exception record written by the shim's vector stubs (see shim/start.S) */
static const char *trap_name(u32 type)
{
	switch (type) {
	case 1: return "UNDEF";
	case 3: return "PREFETCH ABORT";
	case 4: return "DATA ABORT";
	case 5: return "IRQ";
	default: return "?";
	}
}

static const vu32 *trap_rec(void)
{
	const vu32 *r = (const vu32 *)TRAP_REC_ADDR;

	/* the stub writes the type early and the magic last: a type without the magic = partial */
	return (r[0x58 / 4] == TRAP_MAGIC) ? r : NULL;	/* the XNU kernel owns this area now: no partial guesses */
}

static u32 block_sum(u32 b)
{
	const vu32 *p = (const vu32 *)(SUM_BASE + b * SUM_BLOCK);
	u32 s = 0;

	for (u32 i = 0; i < SUM_BLOCK / 4; i++)
		s = ((s << 5) | (s >> 27)) ^ p[i];
	return s;
}

static void sum_snapshot(void)
{
	flushCaches();
	for (u32 b = 0; b < SUM_BLOCKS; b++)
		sum_ref[b] = block_sum(b);
}

static u64 sum_changed(void)
{
	u64 mask = 0;

	flushCaches();
	for (u32 b = 0; b < SUM_BLOCKS; b++)
		if (block_sum(b) != sum_ref[b])
			mask |= 1ull << b;
	return mask;
}

/* Copy the kernel log text out of FCRAM. The kernel keeps the used length just in front of the
 * text; control bytes (the colour escapes of the video console banner) are shown as '.'. */
static u32 read_klog(void)
{
	const vu8 *src = (const vu8 *)klog_addr;
	u32 pos = *(const vu32 *)(klog_addr - 4);
	u32 n = 0;

	flushCaches();
	pos = *(const vu32 *)(klog_addr - 4);
	if (pos > KLOG_SIZE)
		pos = KLOG_SIZE;
	for (u32 i = 0; i < pos; i++) {
		u8 c = src[i];
		if (c == 0)
			continue;
		if (c == '\t')
			c = ' ';
		else if (c != '\n' && (c < 32 || c >= 127))
			c = '.';
		klog[n++] = (char)c;
	}
	klog[n] = 0;
	return n;
}

/* Last TOP_ROWS screen lines of the log, wrapped at TOP_COLS */
static void draw_klog(u32 len)
{
	static const char *starts[256];
	static u8 lens[256];
	u32 nlines = 0;
	u32 i = 0;

	while (i < len) {
		u32 j = i, w = 0;
		while (j < len && klog[j] != '\n' && w < TOP_COLS)
			j++, w++;
		starts[nlines % 256] = &klog[i];
		lens[nlines % 256] = w;
		nlines++;
		i = (j < len && klog[j] == '\n') ? j + 1 : j;
	}

	ClearScreen((u8 *)FB_TOP_1, SCREEN_WIDTH_TOP, COLOR_BLACK);
	ClearScreen((u8 *)FB_TOP_2, SCREEN_WIDTH_TOP, COLOR_BLACK);
	draw_line((u8 *)FB_TOP_1, (u8 *)FB_TOP_2, 0, "XNU kernel log (iOS 4.2.1 on 3DS)", COLOR_CYAN);

	u32 first = (nlines > TOP_ROWS) ? nlines - TOP_ROWS : 0;
	if (nlines - first > 256)
		first = nlines - 256;
	for (u32 k = first; k < nlines; k++) {
		u32 w = lens[k % 256];
		memcpy(line, starts[k % 256], w);
		line[w] = 0;
		draw_line((u8 *)FB_TOP_1, (u8 *)FB_TOP_2, 1 + (k - first), line, COLOR_WHITE);
	}
}

static void draw_status(u32 stage, u32 len, u32 saves, u64 mask, const char *note)
{
	u8 *b0 = (u8 *)FB_BOT_1, *b1 = (u8 *)FB_BOT_2;
	const char *what;

	switch (stage) {
	case STAGE_ARM11_UP:   what = "ARM11 waiting"; break;
	case STAGE_ARM11_JUMP: what = "ARM11 -> shim"; break;
	case STAGE_SHIM:       what = "shim running"; break;
	case STAGE_XNU:        what = "in XNU"; break;
	default:               what = "?"; break;
	}

	ClearScreen(b0, SCREEN_WIDTH_BOT, COLOR_BLACK);
	ClearScreen(b1, SCREEN_WIDTH_BOT, COLOR_BLACK);
	draw_line(b0, b1, 0, "ios3ds monitor (ARM9)", COLOR_CYAN);
	snprintf(line, sizeof(line), "stage  %02X  %s", (unsigned)stage, what);
	draw_line(b0, b1, 2, line, COLOR_WHITE);
	snprintf(line, sizeof(line), "klog   %u bytes at %08X", (unsigned)len, klog_addr);
	draw_line(b0, b1, 3, line, COLOR_WHITE);
	snprintf(line, sizeof(line), "saved  %u times to %s", (unsigned)saves, KLOG_FILENAME);
	draw_line(b0, b1, 4, line, COLOR_WHITE);
	snprintf(line, sizeof(line), "mem    %08X%08X changed", (unsigned)(mask >> 32), (unsigned)mask);
	draw_line(b0, b1, 5, line, COLOR_WHITE);
	snprintf(line, sizeof(line), "L2C    %08X at ARM11 entry", (unsigned)*(vu32 *)L2C_STATE_ADDR);
	draw_line(b0, b1, 6, line, COLOR_WHITE);
	const vu32 *e = (const vu32 *)IOEMU_STATE_ADDR;
	if (e[0] == IOEMU_MAGIC) {
		snprintf(line, sizeof(line), "IOEMU  %u faults, %u timer, %u uart B", (unsigned)e[2], (unsigned)e[3], (unsigned)e[7]);
		draw_line(b0, b1, 7, line, COLOR_WHITE);
	}
	const vu32 *t = trap_rec();
	if (t) {
		snprintf(line, sizeof(line), "TRAP%s: %s from mode %02X",
			 (t[0x58 / 4] == TRAP_MAGIC) ? "" : " (partial)", trap_name(t[0x34 / 4]),
			 (unsigned)(t[0x3C / 4] & 0x1F));
		draw_line(b0, b1, 9, line, COLOR_RED);
		snprintf(line, sizeof(line), "lr %08X  spsr %08X", (unsigned)t[0x38 / 4], (unsigned)t[0x3C / 4]);
		draw_line(b0, b1, 10, line, COLOR_WHITE);
		snprintf(line, sizeof(line), "DFSR %08X  DFAR %08X", (unsigned)t[0x40 / 4], (unsigned)t[0x44 / 4]);
		draw_line(b0, b1, 11, line, COLOR_WHITE);
		snprintf(line, sizeof(line), "IFSR %08X  IFAR %08X", (unsigned)t[0x48 / 4], (unsigned)t[0x4C / 4]);
		draw_line(b0, b1, 12, line, COLOR_WHITE);
		snprintf(line, sizeof(line), "sp_svc %08X  lr_svc %08X", (unsigned)t[0x5C / 4], (unsigned)t[0x60 / 4]);
		draw_line(b0, b1, 13, line, COLOR_WHITE);
		snprintf(line, sizeof(line), "SCTLR %08X  TTBR0 %08X", (unsigned)t[0x50 / 4], (unsigned)t[0x54 / 4]);
		draw_line(b0, b1, 14, line, COLOR_WHITE);
		for (int i = 0; i < 12; i += 4) {
			snprintf(line, sizeof(line), "%s %08X %08X %08X %08X", (i == 0) ? "r0 " : (i == 4) ? "r4 " : "r8 ", (unsigned)t[i], (unsigned)t[i + 1],
				 (unsigned)t[i + 2], (unsigned)t[i + 3]);
			draw_line(b0, b1, 15 + i / 4, line, COLOR_WHITE);
		}
	}
	if (note)
		draw_line(b0, b1, 8, note, COLOR_YELLOW);
	draw_line(b0, b1, 20, "A: save log now", COLOR_GREY);
	draw_line(b0, b1, 21, "START: power off", COLOR_GREY);
}

static bool save_klog(u32 stage, u32 len, u64 mask)
{
	static char hdr[4096];
	const vu8 *k = (const vu8 *)klog_addr;
	int n = snprintf(hdr, sizeof(hdr), "[ios3ds] stage %02X, %u bytes of kernel log\n"
			 "[ios3ds] FCRAM 128K blocks changed since hand-off: %08X%08X\n"
			 "[ios3ds] L2C ctrl at ARM11 entry: %08X\n[ios3ds] klog area:",
			 (unsigned)stage, (unsigned)len, (unsigned)(mask >> 32), (unsigned)mask,
			 (unsigned)*(vu32 *)L2C_STATE_ADDR);
	for (int i = 0; i < 16; i++)
		n += snprintf(hdr + n, sizeof(hdr) - n, " %02X", k[i]);
	n += snprintf(hdr + n, sizeof(hdr) - n, "\n");
	const vu32 *e = (const vu32 *)IOEMU_STATE_ADDR;
	if (e[0] == IOEMU_MAGIC) {
		n += snprintf(hdr + n, sizeof(hdr) - n,
			      "[ios3ds] IOEMU: %u faults, %u timer reads, %u uart bytes, twd_va %08X, hi %u last %08X,"
			      " last refusal why=%u ins=%08X pc=%08X\n[ios3ds] IOEMU last accesses (newest first: va pa pc|W val):\n",
			      (unsigned)e[2], (unsigned)e[3], (unsigned)e[7], (unsigned)e[4], (unsigned)e[5], (unsigned)e[6],
			      (unsigned)e[9], (unsigned)e[10], (unsigned)e[11]);
		u32 cnt = e[8] < 24 ? e[8] : 24;
		for (u32 i = 0; i < cnt; i++) {
			const vu32 *l = &e[16 + (((e[8] - 1 - i) & 63) * 4)];
			n += snprintf(hdr + n, sizeof(hdr) - n, "  %08X %08X %08X %08X\n", (unsigned)l[0], (unsigned)l[1],
				      (unsigned)l[2], (unsigned)l[3]);
		}
		u32 ul = e[7] < 600 ? e[7] : 600;
		if (ul) {
			const vu8 *u = (const vu8 *)IOEMU_UART_ADDR;
			n += snprintf(hdr + n, sizeof(hdr) - n, "[ios3ds] IOEMU uart text (%u bytes): ", (unsigned)e[7]);
			for (u32 i = 0; i < ul && n < (int)sizeof(hdr) - 4; i++)
				hdr[n++] = (u[i] >= 32 && u[i] < 127) || u[i] == '\n' ? (char)u[i] : '.';
			hdr[n++] = '\n';
		}
	}
	const vu32 *t = trap_rec();
	if (t) {
		n += snprintf(hdr + n, sizeof(hdr) - n, "[ios3ds] TRAP %s%s:",
			      (t[0x58 / 4] == TRAP_MAGIC) ? "" : "(partial) ", trap_name(t[0x34 / 4]));
		for (int i = 0; i < 0x68 / 4; i++)
			n += snprintf(hdr + n, sizeof(hdr) - n, "%s%08X", (i % 8) ? " " : "\n  ", (unsigned)t[i]);
		n += snprintf(hdr + n, sizeof(hdr) - n, "\n  (r0-r12 | type lr spsr | DFSR DFAR IFSR IFAR | SCTLR TTBR0 magic sp_svc lr_svc)\n");
	}

	/* the header goes in front of the text, so shift it in place */
	memmove(klog + n, klog, len + 1);
	memcpy(klog, hdr, n);
	bool ok = FileDumpData(KLOG_FILENAME, klog, n + len) == n + len;
	memmove(klog, klog + n, len + 1);
	return ok;
}

/* Raw copies of the changed 128 KB blocks, for offline diffing against the boot image
 * (ios1/bNN.bin, NN = block index = (addr - 0x20000000) / 128 KB) */
static void save_blocks(u64 mask)
{
	char name[40];

	flushCaches();
	for (u32 b = 0; b < SUM_BLOCKS; b++) {
		if (!(mask & (1ull << b)))
			continue;
		snprintf(name, sizeof(name), "ios1/b%02u.bin", (unsigned)b);
		FileDumpData(name, (void *)(SUM_BASE + b * SUM_BLOCK), SUM_BLOCK);
	}
}

/* After the hand-off the ARM9 has nothing else to do: show the ARM11 boot
 * progress and the XNU log, and write the log to the SD card when it changes. */
__attribute__((noreturn))
static void monitor(void)
{
	u32 saved_len = ~0u, saved_stage = ~0u, prev_len = ~0u, prev_stage = ~0u;
	u64 saved_mask = ~0ull, prev_mask = ~0ull;
	bool saved_trap = false, prev_trap = false;
	u32 saves = 0;
	const char *note = NULL;

	u32 round = 0;

	while (1) {
		/* serve disk requests for ~110 ms, then do the slow housekeeping */
		bool busy = false;
		for (u32 k = 0; k < 100; k++) {
			if (blk_service()) {
				busy = true;
				k = 0;
			} else {
				if (k == 20)
					RootSync();
				delay(20000);
			}
		}
		if (busy && (++round & 15))
			continue;
		u32 stage = *(vu32 *)STAGE_ADDR;
		u32 len = read_klog();
		u64 mask = sum_changed();
		bool trap = trap_rec() != NULL;
		u32 pad = HID_PAD;
		/* the kernel's display driver sets blk padA = "DISP" once it owns the LCD framebuffers */
		bool disp = blk_addr && ((vu32 *)blk_addr)[7] == 0x50534944;

		if (len != prev_len && !disp)
			draw_klog(len);

		/* save once the log has stopped changing for one round, or on A */
		bool settled = len == prev_len && stage == prev_stage && mask == prev_mask && trap == prev_trap &&
			       (len != saved_len || stage != saved_stage || mask != saved_mask || trap != saved_trap);
		if (settled || !(pad & BUTTON_A)) {
			save_blocks(mask);
			if (save_klog(stage, len, mask)) {
				saves++;
				note = NULL;
			} else {
				note = "SD write failed";
			}
			saved_len = len;
			saved_stage = stage;
			saved_mask = mask;
			saved_trap = trap;
		}
		/* START alone is the iOS Home button and SELECT is Lock: poweroff needs the START+SELECT+X chord */
		if (!(pad & BUTTON_START) && !(pad & BUTTON_SELECT) && !(pad & BUTTON_X))
			mcu_poweroff();

		if (!disp)
			draw_status(stage, len, saves, mask, note);
		prev_len = len;
		prev_stage = stage;
		prev_mask = mask;
		prev_trap = trap;
	}
}

int main(int argc, char *argv[])
{
	u32 entry = 0;

	InitScreenFbs(argc, argv);
	ClearScreenFull(true, true);
	DebugClear();

	Debug("-- iOS 4.2.1 loader (ios3ds) --");

	if (InitFS()) {
		Debug("Initializing SD card... success");
	} else {
		Debug("Initializing SD card... failed");
		wait_any_key_poweroff();
	}

	size_t image_size = load_file(IOS_IMAGE_FILENAME, (void *)IOS_IMAGE_ADDR, FCRAM_SIZE);
	if (!image_size)
		goto error;
	/* The open XNU (N3DS board) keeps its log in a struct tagged "N3DSKLOG"; text starts at +16 */
	for (u32 o = 0; o + 16 <= image_size; o += 64) {
		const u32 *w = (const u32 *)(IOS_IMAGE_ADDR + o);
		if (w[0] == 0x5344334E && w[1] == 0x474F4C4B) {	/* "N3DS" "KLOG" */
			klog_addr = IOS_IMAGE_ADDR + o + 16;
			Debug("N3DS kernel log at %08X", klog_addr);
			break;
		}
	}
	if (load_file(IOS_ENTRY_FILENAME, &entry, sizeof(entry)) != sizeof(entry))
		goto error;

	/* Optional root disk on the SD card: tell the kernel its size through the mailbox */
	for (u32 o = 0; o + 64 <= image_size; o += 64) {
		const u32 *w = (const u32 *)(IOS_IMAGE_ADDR + o);
		if (w[0] == 0x5344334E && w[1] == 0x004B4C42) {	/* "N3DS" "BLK\0" */
			blk_addr = IOS_IMAGE_ADDR + o;
			break;
		}
	}
	if (blk_addr) {
		u32 sectors = RootOpen(ROOT_IMG_FILENAME);
		*(vu32 *)(blk_addr + 32) = sectors;
		Debug("Root disk %s: %u sectors%s", ROOT_IMG_FILENAME, (unsigned)sectors,
		      RootIsFragmented() ? " (fragmented)" : "");
	}

	Debug("Starting the S5L shim at %08X", entry);
	LogWrite(NULL);
	sum_snapshot();

	/* Tell the ARM11 where to go */
	*(vu32 *)SYNC_ADDR = entry;
	flushCaches();

	/* The SD card stays mounted for the monitor (later: SD/PXI server for the NAND image) */
	monitor();

error:
	DeinitFS();
	wait_any_key_poweroff();
}
