OUTPUT_ARCH(arm)
ENTRY(_start)
SECTIONS
{
	. = 0xC0662000;		/* stage 0 is position independent; the stubs and dabt.c run here */
	.text : { *(.text.start) *(.text*) *(.rodata*) *(.data*) }
	.bss : { *(.bss* COMMON) }
}
