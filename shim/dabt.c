/* S5L I/O emulation for XNU on the 3DS.  XNU maps the iPhone SoC's I/O (UART, timer, VIC, ...)
 * through ml_io_map; on a 3DS those physical addresses don't exist and an access ends in a
 * precise external abort.  The data-abort stub (start.S) calls dabt_c with the saved registers.
 * We decode the faulting load/store, find the physical address with a page-table walk, model
 * the device and resume after the instruction.  Anything we don't understand returns 1 and the
 * caller falls back to the trap-record stub. */
#include <stdint.h>
#include "ios_config.h"

typedef uint32_t u32;
typedef volatile u32 vu32;

#ifdef HOST_TEST
extern u32 t_ttbr0, t_dfsr, t_dfar, t_spsr;
extern char *t_mem;			/* stands for the kernel linear map */
extern void *t_state, *t_shadow, *t_uart;
#define LINEAR(pa) ((uintptr_t)t_mem + (pa))
#define STATE_PTR ((volatile struct st *)t_state)
#define SHADOW ((vu32 *)t_shadow)
#define UARTBUF ((volatile char *)t_uart)
#define RD_TTBR0() t_ttbr0
#define RD_SPSR() t_spsr
#define RD_DFSR() t_dfsr
#define RD_DFAR() t_dfar
#define BARRIER() ((void)0)
extern u32 t_ins;
#define FETCH(pc) (t_ins)
#else
#define LINEAR(pa) ((pa) + 0xA0000000u)	/* XNU's kernel linear map: VA = PA + 0xA0000000 */
#define STATE_PTR ((volatile struct st *)IOEMU_STATE_VA)
#define SHADOW ((vu32 *)IOEMU_SHADOW_VA)
#define UARTBUF ((volatile char *)IOEMU_UART_VA)
#define FETCH(pc) (*(vu32 *)(pc))
#endif

struct st {
	u32 magic, busy, nfault, ntimer, twd_va, hi, last, uart_len;
	u32 log_n, why, ins, pc, spare[4];
	u32 log[64][4];			/* va, pa, pc | write, value */
};
#define S STATE_PTR
#define SHADOW_WORDS 0x4000

struct frame {
	u32 r[13];
	u32 lr;
};

#ifndef HOST_TEST
static inline u32 hw_ttbr0(void)
{
	u32 v;
	asm volatile("mrc p15, 0, %0, c2, c0, 0" : "=r"(v));
	return v;
}
#define RD_TTBR0() hw_ttbr0()
#define RD_SPSR() ({ u32 _v; asm volatile("mrs %0, spsr" : "=r"(_v)); _v; })
#define RD_DFSR() ({ u32 _v; asm volatile("mrc p15, 0, %0, c5, c0, 0" : "=r"(_v)); _v; })
#define RD_DFAR() ({ u32 _v; asm volatile("mrc p15, 0, %0, c6, c0, 0" : "=r"(_v)); _v; })
#define BARRIER() do { u32 _z = 0; asm volatile("mcr p15, 0, %0, c7, c10, 4\n\tmcr p15, 0, %0, c8, c7, 0\n\tmcr p15, 0, %0, c7, c10, 4" : : "r"(_z) : "memory"); } while (0)
#endif

static int va2pa(u32 va, u32 *pa)
{
	u32 d = *(vu32 *)(LINEAR(RD_TTBR0() & 0xFFFFC000u) + ((va >> 20) << 2));

	if ((d & 3) == 2) {
		if (d & (1u << 18))
			return -1;	/* supersection */
		*pa = (d & 0xFFF00000u) | (va & 0xFFFFFu);
		return 0;
	}
	if ((d & 3) == 1) {
		u32 e = *(vu32 *)(LINEAR(d & 0xFFFFFC00u) + (((va >> 12) & 0xFF) << 2));
		if ((e & 3) == 1) {
			*pa = (e & 0xFFFF0000u) | (va & 0xFFFFu);
			return 0;
		}
		if (e & 2) {
			*pa = (e & 0xFFFFF000u) | (va & 0xFFFu);
			return 0;
		}
	}
	return -1;
}

/* The S5L timebase is a 64-bit up counter.  We build it from the MPCore private timer
 * (0x17E00600, free-running 32-bit down counter), mapped by adding a section to XNU's L1 table. */
static void twd_init(void)
{
	vu32 *l1 = (vu32 *)LINEAR(RD_TTBR0() & 0xFFFFC000u);
	u32 i;

	for (i = 0xBF0; i > 0xA00; i--)
		if (l1[i] == 0)
			break;
	l1[i] = 0x17E00000u | 0x412;	/* section, AP=01 (priv rw), domain 0, strongly ordered, XN */
	BARRIER();
	S->twd_va = (i << 20) | 0x600;
	vu32 *t = (vu32 *)S->twd_va;
	t[0] = 0xFFFFFFFFu;		/* load */
	t[1] = 0xFFFFFFFFu;		/* counter */
	t[2] = (10u << 8) | 3;		/* prescaler 10 (PERIPHCLK/11 ~ 12 MHz on a 268 MHz console), auto-reload, enable */
	S->last = 0;
	S->hi = 0;
}

static u32 timer_lo(void)
{
	u32 c;

	if (!S->twd_va)
		twd_init();
	c = ~*(vu32 *)(S->twd_va + 4);
	if (c < S->last)
		S->hi++;
	S->last = c;
	return c;
}

static u32 dev_read(u32 pa)
{
	u32 base = pa & 0xFFFFF000u, off = pa & 0xFFF;

	if (base == 0x3E200000u) {			/* timer */
		S->ntimer++;
		if (off == 0x84)
			return timer_lo();
		if (off == 0x80) {
			timer_lo();
			return S->hi;
		}
		if (off == 0xF8)
			return 0;
	} else if (pa >= 0x3CC00000u && pa < 0x3CC14000u) {	/* UARTs, 0x4000 apart */
		u32 r = pa & 0x3FFF;
		if (r == 0x10)
			return 6;			/* UTRSTAT: tx buffer + transmitter empty, no rx */
		if (r == 0x18 || r == 0x24)
			return 0;			/* UFSTAT, URXH */
	}
	return SHADOW[(pa >> 2) & (SHADOW_WORDS - 1)];
}

static void dev_write(u32 pa, u32 v)
{
	if (pa >= 0x3CC00000u && pa < 0x3CC14000u && (pa & 0x3FFF) == 0x20) {	/* UTXH */
		if (S->uart_len < IOEMU_UART_SIZE)
			UARTBUF[S->uart_len++] = (char)v;
		return;
	}
	SHADOW[(pa >> 2) & (SHADOW_WORDS - 1)] = v;
}

static u32 shifted(struct frame *f, u32 ins, int *ok)
{
	u32 rm = ins & 0xF, amt = (ins >> 7) & 0x1F, v;

	if (rm > 12 || (ins & 0x10)) {
		*ok = 0;
		return 0;
	}
	v = f->r[rm];
	switch ((ins >> 5) & 3) {
	case 0: return v << amt;
	case 1: return amt ? v >> amt : 0;
	case 2: return amt ? (u32)((int32_t)v >> amt) : (u32)((int32_t)v >> 31);
	default:
		if (!amt) {
			*ok = 0;	/* RRX */
			return 0;
		}
		return (v >> amt) | (v << (32 - amt));
	}
}

static int fail(u32 why, u32 ins, u32 pc)
{
	S->why = why;
	S->ins = ins;
	S->pc = pc;
	return 1;
}

int dabt_c(struct frame *f)
{
	u32 spsr, dfsr, dfar, pc = f->lr - 8, ins, pa, mode;
	int ok = 1;

	spsr = RD_SPSR();
	dfsr = RD_DFSR();
	dfar = RD_DFAR();
	S->magic = IOEMU_MAGIC;
	S->nfault++;
	if (S->busy)
		return fail(1, 0, pc);
	if ((dfsr & 0x40F) != 8)
		return fail(2, 0, pc);
	if (spsr & 0x20)
		return fail(3, 0, pc);
	mode = spsr & 0x1F;
	if (mode != 0x13 && mode != 0x1F)
		return fail(4, 0, pc);
	S->busy = 1;

	ins = FETCH(pc);
	u32 load, size, sgn = 0, off, base, addr, val;
	u32 rn = (ins >> 16) & 15, rd = (ins >> 12) & 15;
	u32 p = ins & (1u << 24), u = ins & (1u << 23), w = ins & (1u << 21);

	load = ins & (1u << 20);
	if ((ins & 0x0C000000u) == 0x04000000u) {			/* LDR/STR/LDRB/STRB */
		size = (ins & (1u << 22)) ? 1 : 4;
		off = (ins & (1u << 25)) ? shifted(f, ins, &ok) : (ins & 0xFFF);
	} else if ((ins & 0x0E000090u) == 0x00000090u && (ins & 0x60)) {	/* LDRH/STRH/LDRSB/LDRSH */
		u32 sh = (ins >> 5) & 3;
		if (!load && sh != 1) {
			ok = 0;						/* LDRD/STRD */
		}
		size = (sh == 2) ? 1 : 2;
		sgn = sh >= 2;
		if (ins & (1u << 22)) {
			off = ((ins >> 4) & 0xF0) | (ins & 0xF);
		} else if ((ins & 0xF) > 12) {
			ok = 0;
			off = 0;
		} else {
			off = f->r[ins & 0xF];
		}
	} else {
		ok = 0;
		size = 0;
		off = 0;
	}
	if (!ok) {
		S->busy = 0;
		return fail(5, ins, pc);
	}
	if (rn > 12 || rd > 12) {
		S->busy = 0;
		return fail(6, ins, pc);
	}
	base = f->r[rn];
	addr = p ? (u ? base + off : base - off) : base;
	if (addr != dfar) {
		S->busy = 0;
		return fail(7, ins, pc);
	}
	if (va2pa(dfar, &pa) < 0) {
		S->busy = 0;
		return fail(8, ins, pc);
	}
	if (pa < 0x38000000u || pa >= 0x40000000u) {
		S->busy = 0;
		return fail(9, ins, pc);
	}

	if (load) {
		val = dev_read(pa & ~3u);
		val >>= (pa & 3) * 8;
		if (size == 1) {
			val &= 0xFF;
			if (sgn && (val & 0x80))
				val |= 0xFFFFFF00u;
		} else if (size == 2) {
			val &= 0xFFFF;
			if (sgn && (val & 0x8000))
				val |= 0xFFFF0000u;
		}
		f->r[rd] = val;
	} else {
		val = f->r[rd];
		if (size == 1)
			val = (val & 0xFF) * 0x01010101u;
		else if (size == 2)
			val = (val & 0xFFFF) * 0x00010001u;
		dev_write(pa & ~3u, val);
	}

	{
		u32 i = S->log_n++ & 63;
		S->log[i][0] = dfar;
		S->log[i][1] = pa;
		S->log[i][2] = pc | (load ? 0 : 1);
		S->log[i][3] = val;
	}
	if (!p || w)
		f->r[rn] = u ? base + off : base - off;	/* base-restored abort model assumed; addr == dfar was checked above */
	f->lr -= 4;				/* resume at the instruction after the faulting one */
	S->busy = 0;
	return 0;
}
