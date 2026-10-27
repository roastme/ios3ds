@ S5L shim, stage 0: runs at its physical address with the MMU off, acts as
@ iBoot's last step and enters XNU.  The header words are filled in by
@ tools/mkios.py.
	.arm
	.cpu mpcore
	.section .text.start
	.global _start
_start:
	b	reset
hdr_boot_args:	.word 0		@ physical address of boot_args
hdr_entry:	.word 0		@ physical address of __start
hdr_magic:	.ascii "S5LS"

#include "ios_config.h"

reset:
	cpsid	aif, #0x13

	@ Caches and MMU off (the loader left them off), clean state
	mrc	p15, 0, r4, c1, c0, 0
	bic	r4, r4, #0x1000		@ I
	bic	r4, r4, #0x0005		@ C, M
	mcr	p15, 0, r4, c1, c0, 0
	mov	r4, #0
	mcr	p15, 0, r4, c7, c5, 0	@ invalidate I-cache
	mcr	p15, 0, r4, c7, c14, 0	@ clean+invalidate D-cache
	mcr	p15, 0, r4, c7, c10, 4	@ DSB
	mcr	p15, 0, r4, c8, c7, 0	@ invalidate TLBs

	ldr	r2, =STAGE_ADDR
	mov	r3, #STAGE_SHIM
	str	r3, [r2]

	mov	r3, #STAGE_XNU
	str	r3, [r2]
	ldr	r0, hdr_boot_args
	ldr	r1, hdr_entry
	bx	r1

	.ltorg

@ ---- Exception capture stubs (run in XNU's address space, MMU on, D-cache off) ----
@ kpatch --with vectrap points XNU's undef/prefetch-abort/data-abort/IRQ vector literals at
@ SHIM_VA + 0x100 * n.  Each stub saves what the exception left behind into the record at
@ TRAP_REC_VA and spins; the ARM9 monitor shows and saves the record.  No stack is needed:
@ the banked sp of the exception mode is the pointer.
@ record: +0x00 r0..r12, +0x34 type, +0x38 lr, +0x3C spsr, +0x40 DFSR, +0x44 DFAR,
@ +0x48 IFSR, +0x4C IFAR, +0x50 SCTLR, +0x54 TTBR0, +0x58 magic, +0x5C sp_svc, +0x60 lr_svc, +0x64 trap count
	.macro trapbody type
	ldr	sp, =TRAP_REC_VA
	stmia	sp, {r0-r12}
	ldr	r0, [sp, #0x64]
	add	r0, r0, #1
	str	r0, [sp, #0x64]		@ trap count
	cmp	r0, #1
	bne	2f			@ only the first exception is recorded, later ones just spin
	mov	r0, #\type
	str	r0, [sp, #0x34]
	str	lr, [sp, #0x38]
	mrs	r0, spsr
	str	r0, [sp, #0x3C]
	mrc	p15, 0, r0, c5, c0, 0
	str	r0, [sp, #0x40]
	mrc	p15, 0, r0, c6, c0, 0
	str	r0, [sp, #0x44]
	mrc	p15, 0, r0, c5, c0, 1
	str	r0, [sp, #0x48]
	@ IFAR (c6,c0,2) is undefined on the 3DS ARM11 (run 4: the stub faulted in itself): leave +0x4C = 0
	mrc	p15, 0, r0, c1, c0, 0
	str	r0, [sp, #0x50]
	mrc	p15, 0, r0, c2, c0, 0
	str	r0, [sp, #0x54]
	mov	r0, sp
	cps	#0x13
	str	sp, [r0, #0x5C]
	str	lr, [r0, #0x60]
	ldr	r1, =TRAP_MAGIC
	str	r1, [r0, #0x58]
	mcr	p15, 0, r1, c7, c10, 4
2:	b	2b
	.endm

	.macro trapstub n, type
	.balign 0x100
	.org	0x100 * \n
	trapbody \type
	.ltorg
	.endm

	trapstub 1, 1		@ undefined instruction
	trapstub 2, 3		@ prefetch abort
	@ data abort: first try to emulate S5L I/O (dabt.c); on failure fall back to the record stub
	.balign 0x100
	.org	0x300
	ldr	sp, =IOEMU_STATE_VA	@ banked abort-mode sp: stack grows down below the state block
	stmdb	sp!, {r0-r12, lr}
	mov	r0, sp
	bl	dabt_c
	cmp	r0, #0
	ldmeqia	sp!, {r0-r12, pc}^	@ handled: dabt_c moved lr to the next instruction
	ldmia	sp!, {r0-r12, lr}
	b	dabt_trap
	.ltorg
	trapstub 4, 5		@ IRQ

	.balign 0x100
	.org	0x500
dabt_trap:
	trapbody 4
	.ltorg
