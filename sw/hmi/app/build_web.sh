#!/bin/sh
# Builds the browser version of the screens into www/pkg (HMI.md §5).
# Needs: rustup target add wasm32-unknown-unknown, and wasm-bindgen-cli at the
# same version as the wasm-bindgen crate in Cargo.lock:
#   cargo install wasm-bindgen-cli --version 0.2.130 --locked
# Then serve it with the daemon: kria-hmid --sim --www sw/hmi/app/www
set -e
cd "$(dirname "$0")"
cargo build --release --lib --target wasm32-unknown-unknown
wasm-bindgen --target web --no-typescript --out-dir www/pkg \
    target/wasm32-unknown-unknown/release/kria_hmi.wasm
ls -l www/pkg
