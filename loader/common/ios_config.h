/* iPhone OS 1.1 loader settings */
#define IOS_IMAGE_ADDR   (0x20000000)	/* boot.bin: kernel + DT + boot_args + shim (physBase) */
#define SYNC_ADDR        (0x1FFFFFF0)	/* ARM9 -> ARM11: shim entry (physical), 0 = not yet */
#define STAGE_ADDR       (0x1FFFFF00)	/* boot progress word, written by the ARM11 side */
#define L2C_STATE_ADDR   (0x1FFFFF04)	/* New 3DS L2C-310 control at ARM11 entry (~0 on Old 3DS) */

/* Boot progress values in STAGE_ADDR */
#define STAGE_ARM11_UP     0x11	/* ARM11 loader running, framebuffers set */
#define STAGE_ARM11_JUMP   0x12	/* ARM11 got the shim entry, jumping */
#define STAGE_SHIM         0x20	/* shim running (MMU/caches off) */
#define STAGE_XNU          0x21	/* shim jumping to XNU __start */

/* Exception capture: the shim's vector stubs (kernel patched by kpatch --with vectrap) write a
 * record here (shim area, physical; kernel VA = +0xA0000000) and spin. Layout in shim/start.S. */
#define TRAP_REC_ADDR    (0x20663000)
#define TRAP_REC_VA      (0xC0663000)
/* S5L I/O emulator state (shim data-abort handler); layout in shim/dabt.c */
#define IOEMU_STATE_ADDR (0x20665000)
#define IOEMU_STATE_VA   (0xC0665000)
#define IOEMU_UART_ADDR  (0x20666000)
#define IOEMU_UART_VA    (0xC0666000)
#define IOEMU_UART_SIZE  (0x1000)
#define IOEMU_SHADOW_VA  (0xC0668000)
#define IOEMU_MAGIC      (0x4D454F49)
#define TRAP_MAGIC       (0x50415254)	/* "TRAP" */

/* XNU's kernel log (msgbuf text) for this kernelcache at physBase 0x20000000 */
#define KLOG_ADDR        (0x20262000)
#define KLOG_SIZE        (0x40000)
#define KLOG_FILENAME    "ios1/klog.txt"

#define ROOT_IMG_FILENAME "ios1/root.img"	/* optional: HFS+ root disk served over the block mailbox */
#define IOS_IMAGE_FILENAME "ios1/boot.bin"
#define IOS_ENTRY_FILENAME "ios1/entry.bin"	/* 4 bytes: shim entry physical address */

/* 3DS memory layout */
#define VRAM_BASE     (0x18000000)
#define VRAM_SIZE     (0x00600000)
#define AXI_WRAM_BASE (0x1FF80000)
#define AXI_WRAM_SIZE (0x00080000)
#define FCRAM_BASE    (0x20000000)
#define FCRAM_SIZE    (0x0FF00000)
