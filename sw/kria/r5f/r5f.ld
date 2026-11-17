/* Either R5F core in split mode (each core sees its own TCM at these addresses):
 * code in ATCM, data and stacks in BTCM. Linux remoteproc (zynqmp_r5) loads the ELF
 * segments there and starts the core at 0. */
MEMORY
{
    ATCM : ORIGIN = 0x00000000, LENGTH = 64K
    BTCM : ORIGIN = 0x00020000, LENGTH = 64K
}

ENTRY(_vectors)

SECTIONS
{
    .vectors : { KEEP(*(.vectors)) } > ATCM
    .text : { *(.text .text.*) } > ATCM
    .rodata : { *(.rodata .rodata.*) } > ATCM
    .resource_table : ALIGN(8) { KEEP(*(.resource_table)) } > BTCM
    .data : { *(.data .data.*) } > BTCM
    .bss (NOLOAD) : ALIGN(4) { __sbss = .; *(.bss .bss.* COMMON) . = ALIGN(4); __ebss = .; } > BTCM
    .stack (NOLOAD) : ALIGN(8) { . += 16K; _stack_top = .; . += 256; _abt_stack_top = .; } > BTCM
    /DISCARD/ : { *(.ARM.exidx .ARM.exidx.*) *(.ARM.extab*) }
}
