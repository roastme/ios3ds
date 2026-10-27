/* Host test for shim/dabt.c: build with -m32 -DHOST_TEST.  Fakes CP15, page tables and memory. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
typedef uint32_t u32;
u32 t_ttbr0, t_dfsr, t_dfar, t_spsr;
char *t_mem;
void *t_state, *t_shadow, *t_uart;
struct frame { u32 r[13]; u32 lr; };
int dabt_c(struct frame *f);
struct st { u32 magic, busy, nfault, ntimer, twd_va, hi, last, uart_len, log_n, why, ins, pc, spare[4]; u32 log[64][4]; };

u32 t_ins;
static int checks, bad;
#define CHECK(c) do { checks++; if (!(c)) { bad++; printf("FAIL line %d: %s\n", __LINE__, #c); } } while (0)

static int run(struct frame *f, u32 ins, u32 spsr)
{
	t_ins = ins;
	f->lr = 0x1000 + 8;
	t_spsr = spsr;
	return dabt_c(f);
}

int main(void)
{
	t_mem = calloc(1, 0x1000000);	/* "PA" 0 .. 16MB */
	/* only low PAs are modelled: ttbr0 = 0x100000 (L1 at t_mem+0x100000), L2 at 0x104000 */
	t_ttbr0 = 0x100000;
	u32 *l1 = (u32 *)(t_mem + t_ttbr0);
	u32 *l2 = (u32 *)(t_mem + 0x104000);
	l1[0xE00] = 0x3CC00000 | 0x402;			/* section: VA E0000000 -> PA 3CC00000 */
	l1[0xE01] = 0x104000 | 1;			/* coarse: VA E0100000 */
	l2[0] = 0x3E200000 | 0x2 | 0x10;		/* small page: VA E0100000 -> 3E200000 */
	l1[0xE02] = 0x20000000 | 0x402;			/* real RAM section (must be refused) */
	/* TWD stand-in: ttbr table slot search takes l1[0xBEF..]; counter regs live at t_mem + 0x17E00600 ... too big; skip TWD (tested separately) */
	t_state = calloc(1, 0x1000); t_shadow = calloc(1, 0x10000); t_uart = calloc(1, 0x1000);
	struct st *S = t_state;
	struct frame f;
	int rc;

	/* STR r1, [r3] -> UART0 +0x20 (UTXH): e5831020 with r3=E0000020 */
	memset(&f, 0, sizeof f); f.r[1] = 'A'; f.r[3] = 0xE0000020; t_dfsr = 0x808; t_dfar = 0xE0000020;
	rc = run(&f, 0xE5831000, 0x60000013);
	CHECK(rc == 0); CHECK(S->uart_len == 1); CHECK(((char *)t_uart)[0] == 'A'); CHECK(f.lr == 0x1000 + 4);
	/* LDR r0, [r3, #0x10] = UTRSTAT -> 6 */
	memset(&f, 0, sizeof f); f.r[3] = 0xE0000000; t_dfar = 0xE0000010;
	rc = run(&f, 0xE5930010, 0x60000013);
	CHECK(rc == 0); CHECK(f.r[0] == 6);
	/* STR to register 0x28 then LDR back (shadow) */
	memset(&f, 0, sizeof f); f.r[1] = 0x1234; f.r[3] = 0xE0000000; t_dfar = 0xE0000028;
	rc = run(&f, 0xE5831028, 0x60000013); CHECK(rc == 0);
	memset(&f, 0, sizeof f); f.r[3] = 0xE0000000; t_dfar = 0xE0000028;
	rc = run(&f, 0xE5930028, 0x60000013); CHECK(rc == 0); CHECK(f.r[0] == 0x1234);
	/* post-index with writeback: LDR r0,[r3],#4 (e4930004), address = r3 */
	memset(&f, 0, sizeof f); f.r[3] = 0xE0000028; t_dfar = 0xE0000028;
	rc = run(&f, 0xE4930004, 0x60000013); CHECK(rc == 0); CHECK(f.r[3] == 0xE000002C); CHECK(f.r[0] == 0x1234);
	/* pre-index writeback: STR r1,[r3,#-8]! (e5231008) */
	memset(&f, 0, sizeof f); f.r[1] = 7; f.r[3] = 0xE0000030; t_dfar = 0xE0000028;
	rc = run(&f, 0xE5231008, 0x60000013); CHECK(rc == 0); CHECK(f.r[3] == 0xE0000028);
	/* register offset: LDR r0,[r3,r4,lsl #2]  e7930104 */
	memset(&f, 0, sizeof f); f.r[3] = 0xE0000000; f.r[4] = 10; t_dfar = 0xE0000028;
	rc = run(&f, 0xE7930104, 0x60000013); CHECK(rc == 0); CHECK(f.r[0] == 7);
	/* LDRB r0,[r3] from UFSTAT 0x18 -> 0 ; e5d30018 */
	memset(&f, 0, sizeof f); f.r[0] = 0xFFFFFFFF; f.r[3] = 0xE0000000; t_dfar = 0xE0000018;
	rc = run(&f, 0xE5D30018, 0x60000013); CHECK(rc == 0); CHECK(f.r[0] == 0);
	/* STRH r1,[r3,#0x28]: e1c312b8 ; shadow gets replicated half */
	memset(&f, 0, sizeof f); f.r[1] = 0xAABB; f.r[3] = 0xE0000000; t_dfar = 0xE0000028;
	rc = run(&f, 0xE1C312B8, 0x60000013); CHECK(rc == 0);
	/* LDRH r0,[r3,#0x28]: e1d302b8 */
	memset(&f, 0, sizeof f); f.r[3] = 0xE0000000; t_dfar = 0xE0000028;
	rc = run(&f, 0xE1D302B8, 0x60000013); CHECK(rc == 0); CHECK(f.r[0] == 0xAABB);
	/* coarse page mapping to the timer: LDR r0,[r3,#0x84] -> timer_lo needs TWD; skip. LDR +0xF8 -> 0 */
	memset(&f, 0, sizeof f); f.r[0] = 5; f.r[3] = 0xE0100000; t_dfar = 0xE01000F8;
	rc = run(&f, 0xE59300F8, 0x60000013); CHECK(rc == 0); CHECK(f.r[0] == 0);
	/* refusals */
	memset(&f, 0, sizeof f); f.r[3] = 0xE0200000; t_dfar = 0xE0200000;
	rc = run(&f, 0xE5930000, 0x60000013); CHECK(rc == 1); CHECK(S->why == 9);   /* real RAM PA */
	t_dfsr = 0x005; t_dfar = 0xE0000000; f.r[3] = 0xE0000000;
	rc = run(&f, 0xE5930000, 0x60000013); CHECK(rc == 1); CHECK(S->why == 2);   /* not an external abort */
	t_dfsr = 0x808;
	rc = run(&f, 0xE5930000, 0x60000033); CHECK(rc == 1); CHECK(S->why == 3);   /* thumb */
	rc = run(&f, 0xE5930000, 0x60000010); CHECK(rc == 1); CHECK(S->why == 4);   /* user mode */
	t_dfar = 0xE0000004;
	rc = run(&f, 0xE5930000, 0x60000013); CHECK(rc == 1); CHECK(S->why == 7);   /* address mismatch */
	t_dfar = 0xE0000000;
	rc = run(&f, 0xE8930003, 0x60000013); CHECK(rc == 1); CHECK(S->why == 5);   /* LDM unsupported */
	printf("%d checks, %d bad; log_n=%u nfault=%u\n", checks, bad, S->log_n, S->nfault);
	return bad != 0;
}
