//! Start-up shared by both R5F images: vectors, reset, the data-abort
//! handler, the resource table remoteproc expects, and the panic handler.
//!
//! Caches and the MPU are left as at reset (off), so the shared memory in DDR
//! and the PL registers are seen as they are without maintenance.
//!
//! **Data aborts.** A PL register can answer a read with SLVERR: `kria_pl_link`
//! does so for its link registers when the link's receive clock is missing,
//! which is exactly when the watchdog is looking at it. The handler counts the
//! abort in [`ABORTS`] and resumes at the next instruction (the code is A32,
//! so the faulting instruction is `lr - 8` and the next one `lr - 4`); the
//! caller compares [`aborts`] before and after the access. Imprecise aborts
//! (a write that failed) are counted the same way.

use core::panic::PanicInfo;
use core::sync::atomic::{AtomicU32, Ordering};

#[no_mangle]
pub static ABORTS: AtomicU32 = AtomicU32::new(0);

pub fn aborts() -> u32 {
    ABORTS.load(Ordering::SeqCst)
}

// Reset: an abort-mode stack, the main stack, VFP on (the eabihf code may use
// it), imprecise aborts unmasked, .bss cleared, main.
core::arch::global_asm!(
    r#"
    .section .vectors, "ax"
    .arm
    .global _vectors
_vectors:
    ldr pc, =_reset
    b .
    b .
    b .
    ldr pc, =_dabort
    b .
    b .
    b .
_reset:
    cps #0x17
    ldr sp, =_abt_stack_top
    cps #0x13
    ldr sp, =_stack_top
    mrc p15, 0, r0, c1, c0, 2
    orr r0, r0, #(0xF << 20)
    mcr p15, 0, r0, c1, c0, 2
    isb
    mov r0, #0x40000000
    vmsr fpexc, r0
    cpsie a
    ldr r0, =__sbss
    ldr r1, =__ebss
    mov r2, #0
1:
    cmp r0, r1
    strlo r2, [r0], #4
    blo 1b
    bl main_entry
    b .
_dabort:
    push {{r0, r1}}
    ldr r0, =ABORTS
    ldr r1, [r0]
    add r1, r1, #1
    str r1, [r0]
    pop {{r0, r1}}
    subs pc, lr, #4
    .ltorg
"#
);

/// The minimal resource table Linux remoteproc expects: version 1, no entries.
#[repr(C, align(8))]
pub struct ResourceTable {
    ver: u32,
    num: u32,
    reserved: [u32; 2],
}

#[no_mangle]
#[link_section = ".resource_table"]
pub static RESOURCE_TABLE: ResourceTable = ResourceTable { ver: 1, num: 0, reserved: [0; 2] };

extern "Rust" {
    /// Each image's last act before it stops on a panic (core 0: transmit off).
    fn on_panic();
}

#[panic_handler]
fn panic(_: &PanicInfo) -> ! {
    // The heartbeat stops with us, which Linux sees.
    unsafe { on_panic() };
    loop {}
}
