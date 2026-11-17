fn main() {
    // So the linker finds r5f.ld (passed as -Tr5f.ld in .cargo/config.toml).
    println!("cargo:rustc-link-search={}", std::env::var("CARGO_MANIFEST_DIR").unwrap());
    println!("cargo:rerun-if-changed=r5f.ld");
}
