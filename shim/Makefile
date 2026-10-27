CC	= arm-linux-gnueabi-gcc
OBJCOPY	= arm-linux-gnueabi-objcopy
ARCH	= -mcpu=mpcore -march=armv6k -marm
CFLAGS	= -Wall -O2 $(ARCH) -I../loader/common -ffreestanding -fno-pic -fno-stack-protector -U_FORTIFY_SOURCE

all: shim.bin

shim.elf: start.o dabt.o link.ld
	$(CC) -T link.ld -nostartfiles -nostdlib -no-pie -static -Wl,--build-id=none start.o dabt.o -o $@ -lgcc

shim.bin: shim.elf
	$(OBJCOPY) -O binary $< $@

%.o: %.c
	$(CC) $(CFLAGS) -mno-unaligned-access -c $< -o $@

%.o: %.S
	$(CC) $(CFLAGS) -c $< -o $@

clean:
	rm -f *.o shim.elf shim.bin
