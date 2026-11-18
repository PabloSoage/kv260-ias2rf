#!/bin/sh
# Regenerates docs/img/hmi/hmi_<screen>.png from the real application (docs/HMI.md): kria-hmid runs the simulated
# board through scenes/tour.jsonl and dumps one snapshot per state, then kria-hmi draws every screen from those
# snapshots with Slint's software renderer, headless, at 1920 x 1080 (the 1280 x 720 layout scaled by 1.5).
# sdr/ holds kria-sdrd's last KrakenSDR and HackRF Pro outputs (docs/INTEGRATIONS.md §9, §10) for Bearing and
# Wideband. Usage, from anywhere: sw/hmi/make_images.sh
set -e
here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/../.." && pwd)"
tmp="$(mktemp -d)"
(cd "$root/sw/kria" && cargo build --release -p kria-hmid)
(cd "$here/app" && cargo build --release)
"$root/sw/kria/target/release/kria-hmid" --sim --dump "$tmp" --script "$here/scenes/tour.jsonl" --sdr-out "$here/sdr"
"$here/app/target/release/kria-hmi" --screenshots "$root/docs/img/hmi" --snapshots "$tmp" --scale 1.5
rm -rf "$tmp"
